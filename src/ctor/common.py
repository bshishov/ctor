from typing import TypeVar, Type, Union, Optional, Any, Callable, Generic

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
    def __eq__(self, other: Any) -> bool:
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


_T = TypeVar("_T")

TypeOrCallable = Union[Type[_T], Callable[..., _T]]


class ISerializationContext(metaclass=ABCMeta):
    @abstractmethod
    def get_provider(self, tp: TypeOrCallable[_T]) -> Optional["IProvider[_T]"]:
        ...

    @abstractmethod
    def get_converter(self, tp: TypeOrCallable[_T]) -> "IConverter[_T]":
        ...


class IConverter(Generic[_T], metaclass=ABCMeta):
    @abstractmethod
    def dump(self, obj: _T, context: ISerializationContext) -> Any:
        ...

    @abstractmethod
    def load(self, data: Any, key: Any, context: ISerializationContext) -> _T:
        ...


class IConverterFactory(Generic[_T], metaclass=ABCMeta):
    @abstractmethod
    def try_create_converter(
        self, tp: TypeOrCallable[Any], context: ISerializationContext
    ) -> Optional[IConverter[_T]]:
        ...


class IProvider(Generic[_T], metaclass=ABCMeta):
    @abstractmethod
    def provide(self, context: ISerializationContext) -> _T:
        ...


class IProviderFactory(Generic[_T], metaclass=ABCMeta):
    @abstractmethod
    def can_provide(self, typ: TypeOrCallable[_T]) -> bool:
        ...

    @abstractmethod
    def create_provider(
        self, typ: TypeOrCallable[_T], context: ISerializationContext
    ) -> IProvider[_T]:
        ...
