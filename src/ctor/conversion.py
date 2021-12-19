import sys
from datetime import datetime
from enum import Enum, EnumMeta

from inspect import (
    unwrap,
    signature,
    isclass,
    isfunction,
    Parameter
)
from typing import (
    List,
    Set,
    Dict,
    Mapping,
    Optional,
    Callable,
    Sequence,
    AbstractSet,
    Tuple,
    Any,
    Union,
)

from ctor.typing_utils import (
    Annotated,
    Literal,
    ForwardRef,
    get_args,
    get_origin,
    eval_type,
    is_subclass,
    strip_annotated
)

from ctor.errors import (
    ErrorInfo,
    LoadError,
    DumpError
)

from ctor.common import (
    NOT_PROVIDED,
    IConverter,
    IProvider,
    ISerializationContext,
    IConverterFactory,
    IProviderFactory,
    TypeOrCallable
)


__all__ = [
    # Common
    "dump",
    "load",
    "JsonSerializationContext",
    "AnyLoadingPolicy",
    "AnyDumpPolicy",
    "MissingAnnotationsPolicy",

    # Annotations
    "annotate",
    "Annotated",
    "Alias",
    "Getter",

    # Converters
    "ExactConverter",
    "PrimitiveTypeConverter",
    "NoneConverter",
    "AnyConverter",
    "DatetimeTimestampConverter",
    "SetConverter",
    "ListConverter",
    "DictConverter",
    "UnionTypeConverter",
    "TupleConverter",
    "ObjectConverter",
    "EnumConverter",

    # Factories
    "DiscriminatedConverterFactory",
    "EnumConverterFactory",
    "ObjectConverterFactory"
]


def annotate(attr: str, *annotations: Any, init: bool = True) -> Callable[..., Callable[..., Any]]:
    """Annotates arguments of a callable with `annotations`.
    Annotation is based on special Annotated type-hint, introduced in PEP-593.
    Annotated was first introduced in python 3.9. In older version (3.6+) it is available
    via backport version in typing_extensions.

    This decorator allows usage of Annotated type-hints in older versions. Please use
    true Annotated if possible.

    If the decorator is used against class - an __init__ method would be annotated
    """

    def _annotate(o: Callable[..., Any]) -> None:
        o = unwrap(o)
        hints = getattr(o, '__annotations__', {})

        # noinspection PyTypeHints
        hints[attr] = Annotated[(hints.get(attr, Any), *annotations)]
        o.__annotations__ = hints

    def _decorator(fn_or_cls: Callable[..., Any]) -> Callable[..., Any]:
        _annotate(fn_or_cls)
        if isinstance(fn_or_cls, type) and init:
            _annotate(fn_or_cls.__init__)
        return fn_or_cls

    return _decorator


class AnyLoadingPolicy(Enum):
    RAISE_ERROR = 0
    LOAD_AS_IS = 1


class AnyDumpPolicy(Enum):
    RAISE_ERROR = 0
    DUMP_AS_IS = 1


class MissingAnnotationsPolicy(Enum):
    RAISE_ERROR = 0
    USE_ANY = 1
    FROM_DEFAULT = 2


class Alias:
    """Attribute annotation that specifies an addition key in data dictionary to get if original attr-name is not
    present is data. Multiple Alias allowed
    """
    __slots__ = "alias"

    def __init__(self, alias: str):
        self.alias = alias


class Getter:
    """Attribute annotation that overrides default value retrieval behavior"""
    __slots__ = "_getter"

    def __init__(self, attr_or_getter: Union[str, Callable[[Any], Any]]):
        if isinstance(attr_or_getter, str):
            self._getter = lambda o: getattr(o, attr_or_getter)
        else:
            self._getter = attr_or_getter

    def get_value(self, obj: Any) -> Any:
        return self._getter(obj)


class InjectKey:
    """Attribute annotation that hints serializer to inject the collection key into the attribute"""


class Extras:
    """Attribute annotation that hints serializer to inject extra data into the attribute"""
    __slots__ = "include", "exclude"

    def __init__(self, include: Optional[Set[str]] = None, exclude: Optional[Set[str]] = None):
        if include and exclude:
            raise AttributeError("Specify \"include\" or \"exclude\" attributes, but not both")

        self.include = include
        self.exclude = exclude


class ExactConverter(IConverter):
    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        return obj

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        return data


class DatetimeTimestampConverter(IConverter):
    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        return obj.timestamp()

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        try:
            return datetime.fromtimestamp(data)
        except (TypeError, ValueError) as e:
            raise LoadError(
                ErrorInfo(
                    message="Invalid datetime",
                    code="invalid_datetime",
                    target=str(key) if key is not NOT_PROVIDED else None,
                    details=[ErrorInfo.from_builtin_error(e)]
                )
            ).with_traceback(e.__traceback__)


class AttributeDefinition:
    __slots__ = (
        "name",
        "data_key",
        "aliases",
        "extras",
        "inject_key",
        "provider",
        "converter",
        "getter"
    )

    def __init__(
            self,
            name: str,
            data_key: str,
            aliases: List[str],
            extras: bool,
            inject_key: bool,
            provider: Optional[IProvider],
            converter: Optional[IConverter],
            value_getter: Optional[Callable],
    ):
        self.name = name
        self.data_key = data_key
        self.aliases = aliases
        self.extras = extras
        self.inject_key = inject_key
        self.provider = provider
        self.converter = converter
        self.getter = value_getter


def lookup_dict(data, *keys):
    for k in keys:
        if k in data:
            return data[k]
    return NOT_PROVIDED


class ObjectConverter(IConverter):
    __slots__ = "attributes", "target", "dump_none_values", "_data_keys", "_extra_attributes"

    def __init__(
            self,
            attributes: List[AttributeDefinition],
            target: TypeOrCallable,
            dump_none_values: bool = True
    ):
        self.attributes = attributes
        self.target = target
        self.dump_none_values = dump_none_values

        self._data_keys: Set[str] = set()
        self._extra_attributes: Set[str] = set()

        for a in self.attributes:
            self._data_keys.add(a.data_key)
            self._data_keys.update(a.aliases)
            if a.extras:
                self._extra_attributes.add(a.name)

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        if data is None:
            raise LoadError(
                ErrorInfo(
                    message="Cannot load a None object",
                    code="none_load",
                    target=str(key) if key is not NOT_PROVIDED else None
                )
            )

        if not isinstance(data, Mapping):
            raise LoadError(
                ErrorInfo(
                    message=f"Expected mapping, got {type(data)}",
                    code="invalid_type",
                    target=str(key) if key is not NOT_PROVIDED else None
                )
            )

        kwargs = {}
        for attr in self.attributes:
            raw_value = lookup_dict(data, attr.data_key, *attr.aliases)
            if raw_value is not NOT_PROVIDED and attr.converter is not None:
                try:
                    value = attr.converter.load(raw_value, attr.name, options)
                except LoadError as e:
                    e.info = ErrorInfo(
                        message=f"Failed to load object attribute {attr.name}",
                        code="attr_load_error",
                        target=str(key) if key is not NOT_PROVIDED else None,
                        details=[e.info]
                    )
                    raise
            elif attr.provider:
                value = attr.provider.provide(options)
            elif attr.inject_key and key is not NOT_PROVIDED:
                value = key
            else:
                # Can't resolve a value for the attribute, skipping
                # Later a default from ctor call will be used, or a native missing attribute will
                # be raised
                continue
            kwargs[attr.name] = value

        extra_data = {}
        for k, value in data.items():
            if k not in self._data_keys:
                extra_data[k] = value

        for attr_name in self._extra_attributes:
            kwargs[attr_name] = extra_data

        try:
            return self.target(**kwargs)
        except LoadError as e:
            e.info = ErrorInfo(
                message=f"Failed to load object",
                code="object_load_error",
                target=self.target.__qualname__,
                details=[e.info]
            )
            raise
        except Exception as e:
            raise LoadError(
                ErrorInfo(
                    message="Failed to load object",
                    code="object_load_error",
                    target=self.target.__qualname__,
                    details=[ErrorInfo.from_builtin_error(e)]
                )
            ).with_traceback(e.__traceback__)

    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        if obj is None:
            raise DumpError(
                ErrorInfo(
                    message="Expected object, got None",
                    code="none_dump",
                    target=obj
                )
            )

        data = {}
        for attr in self.attributes:
            if not attr.getter and not attr.converter:
                # Unable to get a value for the attribute (might be a load-only attr), skipping
                continue
            value = attr.getter(obj)
            if value is NOT_PROVIDED:
                continue
            try:
                raw_value = attr.converter.dump(value, options)
            except DumpError as e:
                e.info = ErrorInfo(
                    message=f"Failed to dump object attr {obj!r}",
                    code="attribute_dump_error",
                    target=attr.name,
                    details=[e.info]
                )
                raise

            if raw_value is None and not self.dump_none_values:
                continue
            data[attr.data_key] = raw_value
        return data


def build_attr_definition(
        param_name: str,
        param_type: TypeOrCallable,
        options: ISerializationContext
) -> AttributeDefinition:
    aliases = set()
    is_extras = False
    inject_key = False
    converter: Optional[IConverter] = None
    provider: Optional[IProvider] = None
    getter = None

    # Parameter annotations handling
    # Annotated types must have the __metadata__ field
    param_type, annotations = strip_annotated(param_type)
    for annotation in annotations:
        if isinstance(annotation, Alias):
            aliases.add(annotation.alias)
        elif isinstance(annotation, InjectKey):
            inject_key = True
        elif isinstance(annotation, Extras):
            is_extras = True
        elif isinstance(annotation, Getter):
            getter = annotation.get_value

    getter = getter or (lambda o: getattr(o, param_name, NOT_PROVIDED))
    provider = provider or options.get_provider(param_type)

    if not provider:
        converter = converter or options.get_converter(param_type)

    return AttributeDefinition(
        name=param_name,
        data_key=param_name,
        aliases=list(aliases),
        extras=is_extras,
        inject_key=inject_key,
        converter=converter,
        provider=provider,
        value_getter=getter
    )


class DiscriminatedConverter(IConverter):
    def __init__(
            self,
            converters: List[Tuple[str, TypeOrCallable, IConverter]],
            discriminator_key: str = 'type'
    ):
        self.discriminator_key = discriminator_key
        self.load_map = {}
        self.dump_map = {}

        for discriminator_value, typ, converter in converters:
            self.load_map[discriminator_value] = converter
            self.dump_map[typ] = (discriminator_value, converter)

    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        tp = type(obj)
        try:
            discriminator_value, converter = self.dump_map[tp]
        except KeyError:
            raise TypeError(f'Cannot dump object {obj}. '
                            f'Cant determine discriminator value for type: {tp}')
        return {**converter.dump(obj, options), self.discriminator_key: discriminator_value}

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        if data is None:
            data = {}
        discriminator_value = data.get(self.discriminator_key)
        if discriminator_value not in self.load_map:
            raise TypeError(f'No registered converter found for discriminator '
                            f'{self.discriminator_key}={discriminator_value}')
        converter = self.load_map[discriminator_value]
        return converter.load(data, key, options)


class ObjectConverterFactory(IConverterFactory):
    __slots__ = "missing_annotations_policy", "dump_none_values"

    def __init__(
            self,
            missing_annotations_policy: MissingAnnotationsPolicy = MissingAnnotationsPolicy.RAISE_ERROR,
            dump_none_values: bool = True
    ):
        self.missing_annotations_policy = missing_annotations_policy
        self.dump_none_values = dump_none_values

    def try_create_converter(
            self,
            tp: TypeOrCallable,
            options: ISerializationContext
    ) -> Optional[IConverter]:
        if not isclass(tp) and not isfunction(tp):
            return None

        type_hints = {}
        definitions = []
        for param_name, param in signature(tp).parameters.items():
            param_type = param.annotation
            if param_type is Parameter.empty:
                param_type = None
            if param_type is None:
                if self.missing_annotations_policy == MissingAnnotationsPolicy.RAISE_ERROR:
                    raise TypeError(
                        f"Missing type annotation for type '{tp}' for parameter '{param_name}'"
                    )
                elif self.missing_annotations_policy == MissingAnnotationsPolicy.USE_ANY:
                    param_type = Any
                elif (
                        self.missing_annotations_policy == MissingAnnotationsPolicy.FROM_DEFAULT
                        and param.default is not Parameter.empty
                ):
                    param_type = type(param.default)
                else:
                    raise RuntimeError(f'Invalid MissingAnnotationsPolicy: '
                                       f'{self.missing_annotations_policy}')
            if isinstance(param_type, str):
                param_type = ForwardRef(param_type)

            param_type = eval_type(param_type, globals(), sys.modules[tp.__module__].__dict__)
            type_hints[param_name] = param_type
            definitions.append(build_attr_definition(param_name, param_type, options))

        return ObjectConverter(
            attributes=definitions,
            target=tp,
            dump_none_values=self.dump_none_values
        )


class DiscriminatedConverterFactory(IConverterFactory):
    __slots__ = "discriminator_type_map", "converter_factory", "discriminator_key"

    def __init__(
            self,
            discriminator_type_map: Dict[str, TypeOrCallable],
            converter_factory: IConverterFactory,
            discriminator_key: str = "type"
    ):
        self.discriminator_type_map = discriminator_type_map
        self.converter_factory = converter_factory
        self.discriminator_key = discriminator_key

    def try_create_converter(
            self,
            tp: TypeOrCallable,
            options: ISerializationContext
    ) -> Optional[IConverter]:
        if tp not in self.discriminator_type_map.values():
            return None

        converters = []
        for discriminator, tp in self.discriminator_type_map.items():
            converter = self.converter_factory.try_create_converter(tp, options)
            converters.append((discriminator, tp, converter))
        return DiscriminatedConverter(converters, discriminator_key=self.discriminator_key)


class ListConverter(IConverter):
    __slots__ = 'item_converter'

    def __init__(self, item_converter: IConverter):
        self.item_converter = item_converter

    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        return [self.item_converter.dump(v, options) for v in obj]

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        if data is None:
            raise LoadError(
                ErrorInfo(
                    message="Expected list, got None",
                    code="none_loading",
                    target=str(key) if key is not NOT_PROVIDED else None
                )
            )

        def _try_load(value, index):
            try:
                return self.item_converter.load(value, index, options)
            except LoadError as e:
                e.info = ErrorInfo(
                    message="Failed to load list",
                    target=str(key) if key is not NOT_PROVIDED else None,
                    code="list_load_error",
                    details=[
                        ErrorInfo(
                            message=f"Failed to load list element at index {index}",
                            code="list_element_load_error",
                            target=str(index),
                            details=[e.info]
                        )
                    ]
                )
                raise

        return [_try_load(value, index) for index, value in enumerate(data)]


class SetConverter(IConverter):
    __slots__ = 'item_converter'

    def __init__(self, item_converter: IConverter):
        self.item_converter = item_converter

    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        return [self.item_converter.dump(v, options) for v in obj]

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        return {self.item_converter.load(value, index, options) for index, value in enumerate(data)}


class DictConverter(IConverter):
    __slots__ = 'value_converter',

    def __init__(self, value_converter: IConverter):
        self.value_converter = value_converter

    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        return {k: self.value_converter.dump(v, options) for k, v in obj.items()}

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        def _try_load(value, k):
            try:
                return self.value_converter.load(value, k, options)
            except LoadError as e:
                e.info = ErrorInfo(
                    message="Failed to load dict",
                    code="dict_load_error",
                    target=str(key) if key is not NOT_PROVIDED else None,
                    details=[
                        ErrorInfo(
                            message="Failed to load dict value",
                            code="dict_value_load_error",
                            target=str(k),
                            details=[e.info],
                        )
                    ]
                )
                raise

        return {k: _try_load(v, k) for k, v in data.items()}


class TupleConverter(IConverter):
    __slots__ = 'converters'

    def __init__(self, *converters: IConverter):
        self.converters = converters

    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        return [
            converter.dump(value, options)
            for converter, value
            in zip(self.converters, obj)
        ]

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        if len(self.converters) != len(data):
            raise LoadError(
                ErrorInfo(
                    message=f"Expected {len(self.converters)} values in tuple, got {len(data)}",
                    code="invalid_tuple_len",
                    target=str(key) if key is not NOT_PROVIDED else None
                )
            )
        return tuple(
            converter.load(value, key=i, options=options)
            for i, (converter, value)
            in enumerate(zip(self.converters, data))
        )


class AnyConverter(IConverter):
    __slots__ = "any_dump_policy", "any_load_policy"

    def __init__(self, any_load_policy: AnyLoadingPolicy, any_dump_policy: AnyDumpPolicy):
        self.any_load_policy = any_load_policy
        self.any_dump_policy = any_dump_policy

    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        if self.any_dump_policy == AnyDumpPolicy.RAISE_ERROR:
            raise TypeError('Cannot dump "Any" type. Make sure you specified types correctly.')
        elif self.any_dump_policy == AnyDumpPolicy.DUMP_AS_IS:
            return obj
        raise RuntimeError(f'Unknown AnyDumpPolicy: {self.any_dump_policy}')
        # Get converter of object at runtime
        # converter = options.get_converter(type(obj))
        # return converter.dump(obj, options)

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        if self.any_load_policy == AnyLoadingPolicy.RAISE_ERROR:
            raise TypeError('Loading Any type is restricted')
        elif self.any_load_policy == AnyLoadingPolicy.LOAD_AS_IS:
            return data
        raise RuntimeError(f'Unknown AnyLoadingPolicy: {self.any_load_policy}')


class ListConverterFactory(IConverterFactory):
    def try_create_converter(
            self,
            tp: TypeOrCallable,
            options: ISerializationContext
    ) -> Optional[IConverter]:
        if not is_subclass(tp, Sequence):
            return None
        args = get_args(tp)
        if args:
            item_type = args[0]
            item_converter = options.get_converter(item_type)
            return ListConverter(item_converter)
        return None


class TupleConverterFactory(IConverterFactory):
    def try_create_converter(
            self,
            tp: TypeOrCallable,
            options: ISerializationContext
    ) -> Optional[IConverter]:
        if not is_subclass(tp, Tuple):
            return None

        args = get_args(tp)
        if args:
            converters = []
            for arg in args:
                converters.append(options.get_converter(arg))
            return TupleConverter(*converters)
        raise TypeError(f'Non-generic Tuple expected, got {tp}')


class SetConverterFactory(IConverterFactory):
    def try_create_converter(
            self,
            tp: TypeOrCallable,
            options: ISerializationContext
    ) -> Optional[IConverter]:
        if not is_subclass(tp, AbstractSet):
            return None

        args = get_args(tp)
        if args:
            item_type = args[0]
            item_converter = options.get_converter(item_type)
            return SetConverter(item_converter)
        raise TypeError(f'Non-generic type expected, got {tp}')


class DictConverterFactory(IConverterFactory):
    def try_create_converter(
            self,
            tp: TypeOrCallable,
            options: ISerializationContext
    ) -> Optional[IConverter]:
        if not is_subclass(tp, Mapping):
            return None

        args = get_args(tp)
        if args:
            value_type = args[1]  # e.g. typing.Dict[str, T]
            value_converter = options.get_converter(value_type)
            return DictConverter(value_converter)
        raise TypeError(f'Non-generic type expected, got {tp}')


class UnionTypeConverter(IConverter):
    __slots__ = 'converters',

    def __init__(self, *converters: IConverter):
        self.converters = converters

    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        errors = []
        for converter in self.converters:
            try:
                return converter.dump(obj, options)
            except DumpError as e:
                errors.append(e.info)
                pass

        raise DumpError(
            ErrorInfo(
                message=f"Unable to dump union type: no suitable converter found",
                code="union_dump_error",
                details=errors
            )
        )

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        errors = []
        for converter in self.converters:
            try:
                return converter.load(data, key, options)
            except LoadError as e:
                errors.append(e.info)

        raise LoadError(
            ErrorInfo(
                message=f"Unable to load union type: no suitable converter found",
                code="union_load_error",
                details=errors,
                target=str(key)
            )
        )


class UnionTypeConverterFactory(IConverterFactory):
    def try_create_converter(
            self,
            tp: TypeOrCallable,
            options: ISerializationContext
    ) -> Optional[IConverter]:
        if not get_origin(tp) == Union:
            return None

        args = get_args(tp)
        if args:
            converters = []
            for arg in args:
                converters.append(options.get_converter(arg))
            return UnionTypeConverter(*converters)

        return None


class EnumConverterFactory(IConverterFactory):
    def try_create_converter(
            self,
            tp: TypeOrCallable,
            options: ISerializationContext
    ) -> Optional[IConverter]:
        if isinstance(tp, EnumMeta):
            return EnumConverter(tp)
        return None


class EnumConverter(IConverter):
    __slots__ = 'enum_class'

    def __init__(self, enum_class: EnumMeta):
        self.enum_class = enum_class

    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        return obj.value

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        try:
            return self.enum_class(data)
        except ValueError as err:
            raise LoadError(ErrorInfo.from_builtin_error(err)).with_traceback(err.__traceback__)


class LiteralConverterFactory(IConverterFactory):
    def try_create_converter(
            self,
            tp: TypeOrCallable,
            options: ISerializationContext
    ) -> Optional[IConverter]:
        if get_origin(tp) is Literal:
            value = get_args(tp)[0]
            return LiteralConverter(value)
        return None


class LiteralConverter(IConverter):
    def __init__(self, value: Any):
        self._value = value

    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        return obj

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        if data != self._value:
            raise LoadError(
                ErrorInfo(
                    message=f"Invalid literal value: expected {self._value}, got {data}",
                    code="invalid_literal",
                    target=str(key)
                )
            )
        return data


class PrimitiveTypeConverter(IConverter):
    __slots__ = "tp", "fallback"

    def __init__(self, tp: TypeOrCallable, *fallback: TypeOrCallable):
        self.tp = tp
        self.fallback = fallback

    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        return obj

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        if isinstance(data, self.tp):
            return data

        if isinstance(data, self.fallback):
            return self.tp(data)

        raise LoadError(ErrorInfo.invalid_type(expected=self.tp, actual=type(data), target=str(key)))


class NoneConverter(IConverter):
    def dump(self, obj: None, options: ISerializationContext) -> None:
        return obj

    def load(self, data: Any, key: Any, options: ISerializationContext) -> None:
        if data is not None:
            raise LoadError(ErrorInfo.invalid_type(expected=type(None), actual=type(data), target=str(key)))
        return None


class BytesConverter(IConverter):
    __slots__ = "encoding", "errors"

    def __init__(self, encoding: str = "utf-8", errors: str = "strict"):
        self.encoding = encoding
        self.errors = errors

    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        return obj.decode(encoding=self.encoding, errors=self.errors)

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        if isinstance(data, str):
            return bytes(data, encoding=self.encoding)
        raise LoadError(ErrorInfo.invalid_type(expected=str, actual=type(data), target=str(key)))


def default_dynamic_converters(
        missing_annotations_policy: MissingAnnotationsPolicy = MissingAnnotationsPolicy.RAISE_ERROR,
        dump_none_values: bool = True
) -> List[IConverterFactory]:
    return [
        TupleConverterFactory(),
        ListConverterFactory(),
        DictConverterFactory(),
        SetConverterFactory(),
        EnumConverterFactory(),
        ObjectConverterFactory(missing_annotations_policy, dump_none_values),
        UnionTypeConverterFactory(),
        LiteralConverterFactory()
    ]


class JsonSerializationContext(ISerializationContext):
    __slots__ = (
        "_converters",
        "converter_factories",
        "providers",
        "provider_factories",
        "_request_stack"
    )

    def __init__(self) -> None:
        self._converters: Dict[TypeOrCallable, IConverter] = {}
        self.converter_factories: List[IConverterFactory] = default_dynamic_converters()
        self.providers: Dict[TypeOrCallable, IProvider] = {}
        self.provider_factories: List[IProviderFactory] = []

        # Annotation resolution stack required to handle recursive types
        self._request_stack: Set[TypeOrCallable] = set()

        self.add_converter(int, PrimitiveTypeConverter(int, float))
        self.add_converter(float, PrimitiveTypeConverter(float, int))
        self.add_converter(str, PrimitiveTypeConverter(str))
        self.add_converter(bool, PrimitiveTypeConverter(bool))
        self.add_converter(bytes, BytesConverter())
        self.add_converter(type(None), NoneConverter())
        self.add_converter(datetime, DatetimeTimestampConverter())
        self.add_converter(Any, AnyConverter(AnyLoadingPolicy.LOAD_AS_IS, AnyDumpPolicy.DUMP_AS_IS))

    def add_converter(self, t: TypeOrCallable, converter: IConverter) -> None:
        self._converters[t] = converter

    def get_converter(self, tp: TypeOrCallable) -> IConverter:
        converter = self._converters.get(tp)

        if converter:
            return converter

        if tp in self._request_stack:
            # Returning proxy converter to avoid recursively creating same converter
            # in case of recursive types like:
            #    class A:
            #       a: A
            return _ProxyConverter(tp)
        self._request_stack.add(tp)

        for factory in self.converter_factories:
            converter = factory.try_create_converter(tp, self)
            if converter:
                self._converters[tp] = converter
                return converter

        self._request_stack.remove(tp)
        raise KeyError(f'No converter found for type: {tp}')

    def get_provider(self, tp: TypeOrCallable) -> Optional[IProvider]:
        provider = self.providers.get(tp)

        if provider is not None:
            return provider

        for factory in self.provider_factories:
            if factory.can_provide(tp):
                provider = factory.create_provider(tp, self)
                self.providers[tp] = provider
                return provider

        return None


class _ProxyConverter(IConverter):
    """Special-case converter to support recursive types"""
    __slots__ = "tp"

    def __init__(self, tp: TypeOrCallable):
        self.tp = tp

    def dump(self, obj: Any, options: ISerializationContext) -> Any:
        converter = options.get_converter(self.tp)
        setattr(self, 'dump', converter.dump)  # method replacement
        return converter.dump(obj, options)

    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any:
        converter = options.get_converter(self.tp)
        setattr(self, 'load', converter.load)  # method replacement
        return converter.load(data, key, options)


# Default serialization context
_JSON_CONTEXT: ISerializationContext = JsonSerializationContext()


def dump(obj: Any, options: ISerializationContext = _JSON_CONTEXT) -> Any:
    converter = options.get_converter(type(obj))
    return converter.dump(obj, options)


def load(
        typ: TypeOrCallable,
        data: Any,
        *,
        key: Any = NOT_PROVIDED,
        options: ISerializationContext = _JSON_CONTEXT
) -> Any:
    converter = options.get_converter(typ)
    return converter.load(data, key=key, options=options)
