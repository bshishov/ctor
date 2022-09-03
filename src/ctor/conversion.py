import sys
from datetime import datetime
from enum import Enum, EnumMeta
from inspect import signature, isclass, isfunction, Parameter
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
    Generic,
    TypeVar,
    Type,
    overload,
)

from ctor.typing_utils import (
    ForwardRef,
    get_args,
    get_origin,
    eval_type,
    is_subclass,
    strip_annotated,
)

from ctor.errors import ErrorInfo, LoadError, DumpError

from ctor.common import (
    NotProvided,
    NOT_PROVIDED,
    IConverter,
    IProvider,
    ISerializationContext,
    IConverterFactory,
    IProviderFactory,
    TypeOrCallable,
)


if sys.version_info >= (3, 8):
    from typing import Literal

    _LITERAL_SUPPORTED = True
else:
    try:
        # Backport for older python versions
        # noinspection PyUnresolvedReferences
        from typing_extensions import Literal

        _LITERAL_SUPPORTED = True
    except ImportError:
        _LITERAL_SUPPORTED = False


__all__ = [
    # Common
    "dump",
    "load",
    "JsonSerializationContext",
    "AnyLoadingPolicy",
    "AnyDumpPolicy",
    "MissingAnnotationsPolicy",
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
    "ObjectConverterFactory",
]

_T = TypeVar("_T")
_TKey = TypeVar("_TKey")
_TVal = TypeVar("_TVal")


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
    present is data. Multiple Alias annotations are allowed
    """

    __slots__ = "alias"

    def __init__(self, alias: str):
        self.alias = alias


class Getter(Generic[_T]):
    """Attribute annotation that overrides default value retrieval behavior"""

    __slots__ = "_getter"

    def __init__(self, fn: Callable[[object], _T]):
        self._getter = fn

    def __call__(self, obj: object) -> _T:
        return self._getter(obj)


class AttrGetter:
    """Attribute annotation that overrides default value retrieval behavior"""

    __slots__ = "_attr"

    def __init__(self, attr: str):
        self._attr = attr

    def __call__(self, obj: object) -> Any:
        return getattr(obj, self._attr, NOT_PROVIDED)


class InjectKey:
    """Attribute annotation that hints serializer to inject the collection key into the attribute"""


class Extras:
    """Attribute annotation that hints serializer to inject extra data into the attribute"""

    __slots__ = "include", "exclude"

    def __init__(
        self, include: Optional[Set[str]] = None, exclude: Optional[Set[str]] = None
    ):
        if include and exclude:
            raise AttributeError(
                'Specify "include" or "exclude" attributes, but not both'
            )

        self.include = include
        self.exclude = exclude


class ExactConverter(IConverter[Any]):
    def dump(self, obj: Any, context: ISerializationContext) -> Any:
        return obj

    def load(self, data: Any, key: Any, context: ISerializationContext) -> Any:
        return data


class DatetimeTimestampConverter(IConverter[datetime]):
    def dump(self, obj: datetime, context: ISerializationContext) -> Any:
        return obj.timestamp()

    def load(self, data: Any, key: Any, context: ISerializationContext) -> datetime:
        try:
            return datetime.fromtimestamp(data)
        except (TypeError, ValueError) as e:
            raise LoadError(
                ErrorInfo(
                    message="Invalid datetime",
                    code="invalid_datetime",
                    target=str(key) if key is not NOT_PROVIDED else None,
                    details=[ErrorInfo.from_builtin_error(e)],
                )
            ).with_traceback(e.__traceback__)


class AttributeDefinition(Generic[_T]):
    __slots__ = (
        "name",
        "data_key",
        "aliases",
        "extras",
        "inject_key",
        "provider",
        "converter",
        "getter",
    )

    def __init__(
        self,
        name: str,
        data_key: str,
        aliases: List[str],
        extras: bool,
        inject_key: bool,
        provider: Optional[IProvider[_T]],
        converter: Optional[IConverter[_T]],
        getter: Callable[[object], Any],
    ):
        self.name = name
        self.data_key = data_key
        self.aliases = aliases
        self.extras = extras
        self.inject_key = inject_key
        self.provider = provider
        self.converter = converter
        self.getter = getter


def lookup_dict(data: Mapping[_TKey, _TVal], *keys: _TKey) -> Union[_TVal, NotProvided]:
    for k in keys:
        if k in data:
            return data[k]
    return NOT_PROVIDED


class ObjectConverter(Generic[_T], IConverter[_T]):
    __slots__ = (
        "attributes",
        "target",
        "dump_none_values",
        "_data_keys",
        "_extra_attributes",
    )

    def __init__(
        self,
        attributes: List[AttributeDefinition[Any]],
        target: Callable[..., _T],
        dump_none_values: bool = True,
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

    def load(self, data: Any, key: Any, context: ISerializationContext) -> _T:
        if data is None:
            raise LoadError(
                ErrorInfo(
                    message="Cannot load a None object",
                    code="none_load",
                    target=str(key) if key is not NOT_PROVIDED else None,
                )
            )

        if not isinstance(data, Mapping):
            raise LoadError(
                ErrorInfo(
                    message=f"Expected mapping, got {type(data)}",
                    code="invalid_type",
                    target=str(key) if key is not NOT_PROVIDED else None,
                )
            )

        kwargs = {}
        for attr in self.attributes:
            raw_value = lookup_dict(data, attr.data_key, *attr.aliases)
            if raw_value is not NOT_PROVIDED and attr.converter is not None:
                try:
                    value = attr.converter.load(raw_value, attr.name, context)
                except LoadError as e:
                    e.info = ErrorInfo(
                        message=f"Failed to load object attribute {attr.name}",
                        code="attr_load_error",
                        target=str(key) if key is not NOT_PROVIDED else None,
                        details=[e.info],
                    )
                    raise
            elif attr.provider:
                value = attr.provider.provide(context)
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
                details=[e.info],
            )
            raise
        except Exception as e:
            raise LoadError(
                ErrorInfo(
                    message="Failed to load object",
                    code="object_load_error",
                    target=self.target.__qualname__,
                    details=[ErrorInfo.from_builtin_error(e)],
                )
            ).with_traceback(e.__traceback__)

    def dump(self, obj: object, context: ISerializationContext) -> Any:
        if obj is None:
            raise DumpError(
                ErrorInfo(
                    message="Expected object, got None", code="none_dump", target=obj
                )
            )

        data = {}
        for attr in self.attributes:
            if not attr.converter:
                # No converter for the attribute (load-only attr), skipping
                continue

            value = attr.getter(obj)
            if value is NOT_PROVIDED:
                continue

            try:
                raw_value = attr.converter.dump(value, context)
            except DumpError as e:
                e.info = ErrorInfo(
                    message=f"Failed to dump object attr {obj!r}",
                    code="attribute_dump_error",
                    target=attr.name,
                    details=[e.info],
                )
                raise

            if raw_value is None and not self.dump_none_values:
                continue
            data[attr.data_key] = raw_value
        return data


def _default_attr_getter(obj: object, attr: str) -> Any:
    return getattr(obj, attr, NOT_PROVIDED)


def build_attr_definition(
    param_name: str, param_type: TypeOrCallable[_T], context: ISerializationContext
) -> AttributeDefinition[_T]:
    aliases = set()
    is_extras = False
    inject_key = False
    converter: Optional[IConverter[_T]] = None
    provider: Optional[IProvider[_T]] = context.get_provider(param_type)
    getter: Callable[[object], Any] = AttrGetter(param_name)

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
        elif isinstance(annotation, (Getter, AttrGetter)):
            getter = annotation

    if not provider:
        converter = converter or context.get_converter(param_type)

    return AttributeDefinition(
        name=param_name,
        data_key=param_name,
        aliases=list(aliases),
        extras=is_extras,
        inject_key=inject_key,
        converter=converter,
        provider=provider,
        getter=getter,
    )


class DiscriminatedConverter(Generic[_T], IConverter[_T]):
    def __init__(
        self,
        converters: List[Tuple[str, TypeOrCallable[_T], IConverter[_T]]],
        discriminator_key: str = "type",
    ):
        self.discriminator_key = discriminator_key
        self.load_map = {}
        self.dump_map = {}

        for discriminator_value, typ, converter in converters:
            self.load_map[discriminator_value] = converter
            self.dump_map[typ] = (discriminator_value, converter)

    def dump(self, obj: _T, context: ISerializationContext) -> Any:
        tp = type(obj)
        try:
            discriminator_value, converter = self.dump_map[tp]
        except KeyError:
            raise TypeError(
                f"Cannot dump object {obj}. "
                f"Cant determine discriminator value for type: {tp}"
            )
        return {
            **converter.dump(obj, context),
            self.discriminator_key: discriminator_value,
        }

    def load(self, data: Any, key: Any, context: ISerializationContext) -> _T:
        if data is None:
            data = {}
        discriminator_value = data.get(self.discriminator_key)
        if discriminator_value not in self.load_map:
            raise TypeError(
                f"No registered converter found for discriminator "
                f"{self.discriminator_key}={discriminator_value}"
            )
        converter = self.load_map[discriminator_value]
        return converter.load(data, key, context)


class ObjectConverterFactory(IConverterFactory[Any]):
    __slots__ = "missing_annotations_policy", "dump_none_values"

    def __init__(
        self,
        missing_annotations_policy: MissingAnnotationsPolicy = MissingAnnotationsPolicy.RAISE_ERROR,
        dump_none_values: bool = True,
    ):
        self.missing_annotations_policy = missing_annotations_policy
        self.dump_none_values = dump_none_values

    def try_create_converter(
        self, tp: TypeOrCallable[Any], context: ISerializationContext
    ) -> Optional[ObjectConverter[Any]]:
        if not isclass(tp) and not isfunction(tp):
            return None

        type_hints = {}
        definitions = []
        for param_name, param in signature(tp).parameters.items():
            param_type = param.annotation
            if param_type is Parameter.empty:
                param_type = None
            if param_type is None:
                if (
                    self.missing_annotations_policy
                    == MissingAnnotationsPolicy.RAISE_ERROR
                ):
                    raise TypeError(
                        f"Missing type annotation for type '{tp}' for parameter '{param_name}'"
                    )
                elif (
                    self.missing_annotations_policy == MissingAnnotationsPolicy.USE_ANY
                ):
                    param_type = Any
                elif (
                    self.missing_annotations_policy
                    == MissingAnnotationsPolicy.FROM_DEFAULT
                    and param.default is not Parameter.empty
                ):
                    param_type = type(param.default)
                else:
                    raise RuntimeError(
                        f"Invalid MissingAnnotationsPolicy: "
                        f"{self.missing_annotations_policy}"
                    )
            if isinstance(param_type, str):
                param_type = ForwardRef(param_type)

            param_type = eval_type(
                param_type, globals(), sys.modules[tp.__module__].__dict__
            )
            type_hints[param_name] = param_type
            definitions.append(build_attr_definition(param_name, param_type, context))

        return ObjectConverter(
            attributes=definitions, target=tp, dump_none_values=self.dump_none_values
        )


class DiscriminatedConverterFactory(IConverterFactory[_T]):
    __slots__ = "discriminator_type_map", "converter_factory", "discriminator_key"

    def __init__(
        self,
        discriminator_type_map: Dict[str, TypeOrCallable[_T]],
        converter_factory: IConverterFactory[_T],
        discriminator_key: str = "type",
    ):
        self.discriminator_type_map = discriminator_type_map
        self.converter_factory = converter_factory
        self.discriminator_key = discriminator_key

    def try_create_converter(
        self, tp: TypeOrCallable[Any], context: ISerializationContext
    ) -> Optional[IConverter[_T]]:
        if tp not in self.discriminator_type_map.values():
            return None

        converters = []
        for discriminator, tp in self.discriminator_type_map.items():
            converter = self.converter_factory.try_create_converter(tp, context)
            if converter:
                converters.append((discriminator, tp, converter))
        return DiscriminatedConverter(
            converters, discriminator_key=self.discriminator_key
        )


class ListConverter(Generic[_T], IConverter[List[_T]]):
    __slots__ = "item_converter"

    def __init__(self, item_converter: IConverter[_T]):
        self.item_converter = item_converter

    def dump(self, obj: List[_T], context: ISerializationContext) -> Any:
        return [self.item_converter.dump(v, context) for v in obj]

    def load(self, data: Any, key: Any, context: ISerializationContext) -> List[_T]:
        if data is None:
            raise LoadError(
                ErrorInfo(
                    message="Expected list, got None",
                    code="none_loading",
                    target=str(key) if key is not NOT_PROVIDED else None,
                )
            )

        def _try_load(value: Any, index: int) -> Any:
            try:
                return self.item_converter.load(value, index, context)
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
                            details=[e.info],
                        )
                    ],
                )
                raise

        return [_try_load(value, index) for index, value in enumerate(data)]


class SetConverter(Generic[_T], IConverter[Set[_T]]):
    __slots__ = "item_converter"

    def __init__(self, item_converter: IConverter[_T]):
        self.item_converter = item_converter

    def dump(self, obj: Set[_T], context: ISerializationContext) -> Any:
        return [self.item_converter.dump(v, context) for v in obj]

    def load(self, data: Any, key: Any, context: ISerializationContext) -> Set[_T]:
        return {
            self.item_converter.load(value, index, context)
            for index, value in enumerate(data)
        }


class DictConverter(Generic[_TKey, _TVal], IConverter[Dict[_TKey, _TVal]]):
    __slots__ = "value_converter"

    def __init__(self, value_converter: IConverter[_TVal]):
        self.value_converter = value_converter

    def dump(self, obj: Dict[_TKey, _TVal], context: ISerializationContext) -> Any:
        return {k: self.value_converter.dump(v, context) for k, v in obj.items()}

    def load(
        self, data: Any, key: Any, context: ISerializationContext
    ) -> Dict[_TKey, _TVal]:
        def _try_load(value: Any, k: Any) -> Any:
            try:
                return self.value_converter.load(value, k, context)
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
                    ],
                )
                raise

        return {k: _try_load(v, k) for k, v in data.items()}


class TupleConverter(IConverter[Tuple[Any, ...]]):
    __slots__ = "converters"

    def __init__(self, *converters: IConverter[Any]):
        self.converters = converters

    def dump(self, obj: Tuple[Any, ...], context: ISerializationContext) -> Any:
        return [
            converter.dump(value, context)
            for converter, value in zip(self.converters, obj)
        ]

    def load(
        self, data: Any, key: Any, context: ISerializationContext
    ) -> Tuple[Any, ...]:
        if len(self.converters) != len(data):
            raise LoadError(
                ErrorInfo(
                    message=f"Expected {len(self.converters)} values in tuple, got {len(data)}",
                    code="invalid_tuple_len",
                    target=str(key) if key is not NOT_PROVIDED else None,
                )
            )
        return tuple(
            converter.load(value, key=i, context=context)
            for i, (converter, value) in enumerate(zip(self.converters, data))
        )


class AnyConverter(IConverter[Any]):
    __slots__ = "any_dump_policy", "any_load_policy"

    def __init__(
        self, any_load_policy: AnyLoadingPolicy, any_dump_policy: AnyDumpPolicy
    ):
        self.any_load_policy = any_load_policy
        self.any_dump_policy = any_dump_policy

    def dump(self, obj: Any, context: ISerializationContext) -> Any:
        if self.any_dump_policy == AnyDumpPolicy.RAISE_ERROR:
            raise TypeError(
                'Cannot dump "Any" type. Make sure you specified types correctly.'
            )
        elif self.any_dump_policy == AnyDumpPolicy.DUMP_AS_IS:
            return obj
        raise RuntimeError(f"Unknown AnyDumpPolicy: {self.any_dump_policy}")

    def load(self, data: Any, key: Any, context: ISerializationContext) -> Any:
        if self.any_load_policy == AnyLoadingPolicy.RAISE_ERROR:
            raise TypeError("Loading Any type is restricted")
        elif self.any_load_policy == AnyLoadingPolicy.LOAD_AS_IS:
            return data
        raise RuntimeError(f"Unknown AnyLoadingPolicy: {self.any_load_policy}")


class ListConverterFactory(IConverterFactory[List[_T]]):
    def try_create_converter(
        self, tp: TypeOrCallable[Any], context: ISerializationContext
    ) -> Optional[ListConverter[_T]]:
        if not is_subclass(tp, Sequence):
            return None
        args = get_args(tp)
        if args:
            item_type = args[0]
            item_converter = context.get_converter(item_type)
            return ListConverter(item_converter)
        return None


class TupleConverterFactory(IConverterFactory[Tuple[Any, ...]]):
    def try_create_converter(
        self, tp: TypeOrCallable[Any], context: ISerializationContext
    ) -> Optional[TupleConverter]:
        if not is_subclass(tp, tuple):
            return None

        args = get_args(tp)
        if args:
            converters = []
            for arg in args:
                converters.append(context.get_converter(arg))
            return TupleConverter(*converters)
        raise TypeError(f"Non-generic Tuple expected, got {tp}")


class SetConverterFactory(IConverterFactory[Set[_T]]):
    def try_create_converter(
        self, tp: TypeOrCallable[Any], context: ISerializationContext
    ) -> Optional[SetConverter[_T]]:
        if not is_subclass(tp, AbstractSet):
            return None

        args = get_args(tp)
        if args:
            item_type = args[0]
            item_converter = context.get_converter(item_type)
            return SetConverter(item_converter)
        raise TypeError(f"Non-generic type expected, got {tp}")


class DictConverterFactory(IConverterFactory[Dict[_TKey, _TVal]]):
    def try_create_converter(
        self, tp: TypeOrCallable[Any], context: ISerializationContext
    ) -> Optional[DictConverter[_TKey, _TVal]]:
        if not is_subclass(tp, Mapping):
            return None

        args = get_args(tp)
        if args:
            value_type = args[1]  # e.g. typing.Dict[str, T]
            value_converter = context.get_converter(value_type)
            return DictConverter(value_converter)
        raise TypeError(f"Non-generic type expected, got {tp}")


class UnionTypeConverter(IConverter[Any]):
    __slots__ = "converters"

    def __init__(self, *converters: IConverter[Any]):
        self.converters = converters

    def dump(self, obj: Any, context: ISerializationContext) -> Any:
        errors = []

        try:
            # First, try dump object by getting a converter of its exact type
            converter = context.get_converter(type(obj))
            return converter.dump(obj, context)
        except TypeError as e:
            errors.append(ErrorInfo.from_builtin_error(e))
        except DumpError as e:
            errors.append(e.info)

        # Second, try all Union converters
        for converter in self.converters:
            try:
                return converter.dump(obj, context)
            except DumpError as e:
                errors.append(e.info)

        raise DumpError(
            ErrorInfo(
                message=f"Unable to dump union type: no suitable converter found",
                code="union_dump_error",
                details=errors,
            )
        )

    def load(self, data: Any, key: Any, context: ISerializationContext) -> Any:
        errors = []
        for converter in self.converters:
            try:
                return converter.load(data, key, context)
            except LoadError as e:
                errors.append(e.info)

        raise LoadError(
            ErrorInfo(
                message=f"Unable to load union type: no suitable converter found",
                code="union_load_error",
                details=errors,
                target=str(key),
            )
        )


class UnionTypeConverterFactory(IConverterFactory[Any]):
    def try_create_converter(
        self, tp: TypeOrCallable[Any], context: ISerializationContext
    ) -> Optional[UnionTypeConverter]:
        if not get_origin(tp) == Union:
            return None

        args = get_args(tp)
        if args:
            converters = []
            for arg in args:
                converters.append(context.get_converter(arg))
            return UnionTypeConverter(*converters)

        return None


_TEnum = TypeVar("_TEnum", bound=Enum)


class EnumConverter(Generic[_TEnum], IConverter[_TEnum]):
    __slots__ = "enum_class"

    def __init__(self, enum_class: Callable[[Any], _TEnum]):
        self.enum_class = enum_class

    def dump(self, obj: _TEnum, context: ISerializationContext) -> Any:
        return obj.value

    def load(self, data: Any, key: Any, context: ISerializationContext) -> _TEnum:
        try:
            return self.enum_class(data)
        except ValueError as err:
            raise LoadError(ErrorInfo.from_builtin_error(err)).with_traceback(
                err.__traceback__
            )


class EnumConverterFactory(IConverterFactory[_TEnum]):
    def try_create_converter(
        self, tp: TypeOrCallable[Any], context: ISerializationContext
    ) -> Optional[EnumConverter[_TEnum]]:
        if isinstance(tp, EnumMeta):
            return EnumConverter(tp)
        return None


if _LITERAL_SUPPORTED:

    class LiteralConverter(IConverter[Any]):
        __slots__ = "_value"

        def __init__(self, value: Any):
            self._value = value

        def dump(self, obj: Any, context: ISerializationContext) -> Any:
            return obj

        def load(self, data: Any, key: Any, context: ISerializationContext) -> Any:
            if data != self._value:
                raise LoadError(
                    ErrorInfo(
                        message=f"Invalid literal value: expected {self._value}, got {data}",
                        code="invalid_literal",
                        target=str(key),
                    )
                )
            return data

    class LiteralConverterFactory(IConverterFactory[Any]):
        def try_create_converter(
            self, tp: TypeOrCallable[Any], context: ISerializationContext
        ) -> Optional[LiteralConverter]:
            if get_origin(tp) is Literal:
                value = get_args(tp)[0]
                return LiteralConverter(value)
            return None


class PrimitiveTypeConverter(IConverter[Any]):
    __slots__ = "tp", "fallback"

    def __init__(self, tp: type, *fallback: type):
        self.tp = tp
        self.fallback = fallback

    def dump(self, obj: Any, context: ISerializationContext) -> Any:
        return obj

    def load(self, data: Any, key: Any, context: ISerializationContext) -> Any:
        if isinstance(data, self.tp):
            return data

        if isinstance(data, self.fallback):
            return self.tp(data)

        raise LoadError(
            ErrorInfo.invalid_type(expected=self.tp, actual=type(data), target=str(key))
        )


class NoneConverter(IConverter[None]):
    def dump(self, obj: None, context: ISerializationContext) -> None:
        if obj is not None:
            raise DumpError(
                ErrorInfo.invalid_type(expected=type(None), actual=type(obj))
            )
        return None

    def load(self, data: Any, key: Any, context: ISerializationContext) -> None:
        if data is not None:
            raise LoadError(
                ErrorInfo.invalid_type(
                    expected=type(None), actual=type(data), target=str(key)
                )
            )
        return None


class BytesConverter(IConverter[bytes]):
    __slots__ = "encoding", "errors"

    def __init__(self, encoding: str = "utf-8", errors: str = "strict"):
        self.encoding = encoding
        self.errors = errors

    def dump(self, obj: bytes, context: ISerializationContext) -> Any:
        return obj.decode(encoding=self.encoding, errors=self.errors)

    def load(self, data: Any, key: Any, context: ISerializationContext) -> bytes:
        if isinstance(data, str):
            return bytes(data, encoding=self.encoding)
        raise LoadError(
            ErrorInfo.invalid_type(expected=str, actual=type(data), target=str(key))
        )


def default_converter_factories(
    missing_annotations_policy: MissingAnnotationsPolicy = MissingAnnotationsPolicy.RAISE_ERROR,
    dump_none_values: bool = True,
) -> List[IConverterFactory[Any]]:
    converter_factories: List[IConverterFactory[Any]] = [
        TupleConverterFactory(),
        ListConverterFactory(),
        DictConverterFactory(),
        SetConverterFactory(),
        EnumConverterFactory(),
        ObjectConverterFactory(missing_annotations_policy, dump_none_values),
        UnionTypeConverterFactory(),
    ]

    if _LITERAL_SUPPORTED:
        converter_factories.append(LiteralConverterFactory())

    return converter_factories


class JsonSerializationContext(ISerializationContext):
    __slots__ = (
        "_converters",
        "converter_factories",
        "providers",
        "provider_factories",
        "_request_stack",
    )

    def __init__(self) -> None:
        self._converters: Dict[TypeOrCallable[Any], IConverter[Any]] = {}
        self.converter_factories: List[
            IConverterFactory[Any]
        ] = default_converter_factories()
        self.providers: Dict[TypeOrCallable[Any], IProvider[Any]] = {}
        self.provider_factories: List[IProviderFactory[Any]] = []

        # Annotation resolution stack required to handle recursive types
        self._request_stack: Set[TypeOrCallable[Any]] = set()

        self.add_converter(int, PrimitiveTypeConverter(int, float))
        self.add_converter(float, PrimitiveTypeConverter(float, int))
        self.add_converter(str, PrimitiveTypeConverter(str))
        self.add_converter(bool, PrimitiveTypeConverter(bool))
        self.add_converter(bytes, BytesConverter())
        self.add_converter(type(None), NoneConverter())
        self.add_converter(datetime, DatetimeTimestampConverter())

        self._any_converter = AnyConverter(
            AnyLoadingPolicy.LOAD_AS_IS, AnyDumpPolicy.DUMP_AS_IS
        )

    def add_converter(self, t: TypeOrCallable[_T], converter: IConverter[_T]) -> None:
        self._converters[t] = converter

    def get_converter(self, tp: TypeOrCallable[_T]) -> IConverter[_T]:
        if tp == Any:
            return self._any_converter

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
        raise KeyError(f"No converter found for type: {tp}")

    def get_provider(self, tp: TypeOrCallable[_T]) -> Optional[IProvider[_T]]:
        provider = self.providers.get(tp)

        if provider is not None:
            return provider

        for factory in self.provider_factories:
            if factory.can_provide(tp):
                provider = factory.create_provider(tp, self)
                self.providers[tp] = provider
                return provider

        return None


class _ProxyConverter(Generic[_T], IConverter[_T]):
    """Special-case converter to support recursive types"""

    __slots__ = "tp"

    def __init__(self, tp: TypeOrCallable[_T]):
        self.tp = tp

    def dump(self, obj: _T, context: ISerializationContext) -> Any:
        converter = context.get_converter(self.tp)
        setattr(self, "dump", converter.dump)  # method replacement
        return converter.dump(obj, context)

    def load(self, data: Any, key: Any, context: ISerializationContext) -> _T:
        converter = context.get_converter(self.tp)
        setattr(self, "load", converter.load)  # method replacement
        return converter.load(data, key, context)


# Default serialization context
_JSON_CONTEXT: ISerializationContext = JsonSerializationContext()


@overload
def load(
    typ: Type[_T],
    data: Any,
    *,
    key: Any = NOT_PROVIDED,
    context: ISerializationContext = _JSON_CONTEXT,
) -> _T:
    ...


@overload
def load(
    typ: Callable[..., _T],
    data: Any,
    *,
    key: Any = NOT_PROVIDED,
    context: ISerializationContext = _JSON_CONTEXT,
) -> _T:
    ...


def load(
    typ: TypeOrCallable[_T],
    data: Any,
    *,
    key: Any = NOT_PROVIDED,
    context: ISerializationContext = _JSON_CONTEXT,
) -> _T:
    converter = context.get_converter(typ)
    return converter.load(data, key=key, context=context)


def dump(obj: _T, context: ISerializationContext = _JSON_CONTEXT) -> Any:
    converter = context.get_converter(type(obj))
    return converter.dump(obj, context)
