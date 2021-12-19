from typing import (
    TypeVar,
    Type,
    Union,
    Optional,
    Any
)

from abc import abstractmethod, ABCMeta

__all__ = [
    "NOT_PROVIDED",
    "NotProvided",
    "TypeOrCallable",
    "ISerializationContext",
    "IProvider",
    "IConverter",
    "IProviderFactory",
    "IConverterFactory",
]


class NotProvided:
    def __eq__(self, other):
        return isinstance(other, NotProvided)

    def __bool__(self) -> bool:
        return False

    def __copy__(self) -> "NotProvided":
        return self

    def __deepcopy__(self) -> "NotProvided":
        return self

    def __str__(self) -> str:
        return "<NOT_PROVIDED>"

    def __repr__(self) -> str:
        return "<NOT_PROVIDED>"


NOT_PROVIDED = NotProvided()


T = TypeVar("T")

try:
    from typing import Protocol

    class KwargsCallable(Protocol):
        def __call__(self, **kwargs: Any) -> T: ...

    TypeOrCallable = Union[Type[Any], KwargsCallable]
except ImportError:
    TypeOrCallable = Type[Any]


class ISerializationContext(metaclass=ABCMeta):
    @abstractmethod
    def get_provider(self, tp: TypeOrCallable) -> Optional['IProvider']: ...

    @abstractmethod
    def get_converter(self, tp: TypeOrCallable) -> 'IConverter': ...


class IConverter(metaclass=ABCMeta):
    @abstractmethod
    def dump(self, obj: Any, options: ISerializationContext) -> Any: ...

    @abstractmethod
    def load(self, data: Any, key: Any, options: ISerializationContext) -> Any: ...


class IConverterFactory(metaclass=ABCMeta):
    @abstractmethod
    def try_create_converter(
            self,
            tp: TypeOrCallable,
            options: ISerializationContext
    ) -> Optional[IConverter]: ...


class IProvider(metaclass=ABCMeta):
    @abstractmethod
    def provide(self, options: ISerializationContext) -> Any: ...


class IProviderFactory(metaclass=ABCMeta):
    @abstractmethod
    def can_provide(self, typ: TypeOrCallable) -> bool: ...

    @abstractmethod
    def create_provider(self, typ: TypeOrCallable, options: ISerializationContext) -> IProvider: ...
