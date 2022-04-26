import typing
import sys

__all__ = [
    "ForwardRef",
    "eval_type",
    "get_origin",
    "is_subclass",
    "get_args",
    "strip_annotated",
    "annotate",
]


if sys.version_info >= (3, 9):
    from typing import Annotated

    _ANNOTATED_SUPPORTED = True
else:
    try:
        # Backport for older python versions
        # noinspection PyUnresolvedReferences
        from typing_extensions import Annotated

        _ANNOTATED_SUPPORTED = True
    except ImportError:
        _ANNOTATED_SUPPORTED = False


# Dynamic forward ref imports / declarations
# 3.6  : https://github.com/python/cpython/blob/3.6/Lib/typing.py#L216
# 3.7  : https://github.com/python/cpython/blob/3.7/Lib/typing.py#L438
# 3.8  : https://github.com/python/cpython/blob/3.8/Lib/typing.py#L489
# 3.9  : https://github.com/python/cpython/blob/3.9/Lib/typing.py#L516
# 3.10 : https://github.com/python/cpython/blob/3.10/Lib/typing.py#L653
if hasattr(typing, "ForwardRef"):
    ForwardRef = getattr(typing, "ForwardRef")
elif hasattr(typing, "_ForwardRef"):
    # Python 3.5, 3.6
    ForwardRef = getattr(typing, "_ForwardRef")
else:
    raise ImportError("typing.ForwardRef is not supported")


# Evaluates meta types recursively including ForwardRef
# 3.6  : https://github.com/python/cpython/blob/3.6/Lib/typing.py#L348
# 3.7  : https://github.com/python/cpython/blob/3.7/Lib/typing.py#L258
# 3.8  : https://github.com/python/cpython/blob/3.8/Lib/typing.py#L265
# 3.9  : https://github.com/python/cpython/blob/3.9/Lib/typing.py#L285
# 3.10 : https://github.com/python/cpython/blob/3.10/Lib/typing.py#L319
eval_type = getattr(typing, "_eval_type")


def get_origin(tp: typing.Any) -> typing.Any:
    """Get unsubscribed version of `tp`.

        get_origin(int) is None
        get_origin(typing.Any) is None
        get_origin(typing.List[int]) is list
        get_origin(typing.Literal[123]) is typing.Literal
        get_origin(typing.Generic[T]) is typing.Generic
        get_origin(typing.Generic) is typing.Generic
        get_origin(typing.Annotated[int, "some"]) is int

    NOTE: This method intentionally allows Annotated to proxy __origin__
    """
    if tp is typing.Generic:  # Special case
        return tp
    return getattr(tp, "__origin__", None)


def get_args(tp: typing.Any) -> typing.Tuple[typing.Any, ...]:
    """Get type arguments with all substitutions performed.
    For unions, basic simplifications used by Union constructor are performed.

    Examples:

        get_args(Dict[str, int]) == (str, int)
        get_args(int) == ()
        get_args(Union[int, Union[T, int], str][int]) == (int, str)
        get_args(Union[int, Tuple[T, int]][str]) == (int, Tuple[str, int])
        get_args(Callable[[], T][int]) == ([], int)

    """
    if hasattr(tp, "__args__"):
        return tp.__args__  # type: ignore
    return tuple()


def is_subclass(left: typing.Any, right: type) -> bool:
    """Modified `issubclass` to support generics and other types.
    __origin__ is being tested for generics
    right value should be a class

    Examples:

        is_subclass(typing.List[int], collections.abc.Sequence) == True
        is_subclass(typing.List, collections.abc.Sequence) == True
        is_subclass(typing.Tuple, collections.abc.Sequence) == True
        is_subclass(typing.Any, collections.abc.Sequence) == False
        is_subclass(int, collections.abc.Sequence) == False

    """
    try:
        return issubclass(getattr(left, "__origin__", left), right)
    except TypeError:
        return False


if _ANNOTATED_SUPPORTED:

    def strip_annotated(
        tp: typing.Any,
    ) -> typing.Tuple[typing.Any, typing.Tuple[typing.Any, ...]]:
        if hasattr(tp, "__metadata__") and hasattr(tp, "__origin__"):
            if tp.__origin__ is Annotated:
                return tp.__args__[0], tp.__metadata__
            return tp.__origin__, tp.__metadata__
        return tp, ()

    def annotate(
        attr: str, *annotations: typing.Any, init: bool = True
    ) -> typing.Callable[..., typing.Callable[..., typing.Any]]:
        """Annotates arguments of a callable with `annotations`.

        Annotation is based on special Annotated type-hint, introduced in PEP-593.
        Annotated was first introduced in python 3.9. In older version (3.6+) it is available
        via backport version in typing_extensions.

        This decorator allows usage of Annotated type-hints in older versions. Please use
        true Annotated if possible.

        If the decorator is used against class - an __init__ method would be annotated
        """

        from inspect import unwrap

        def _annotate(o: typing.Callable[..., typing.Any]) -> None:
            o = unwrap(o)
            hints = getattr(o, "__annotations__", {})

            # noinspection PyTypeHints
            hints[attr] = Annotated[(hints.get(attr, typing.Any), *annotations)]
            o.__annotations__ = hints

        def _decorator(
            fn_or_cls: typing.Callable[..., typing.Any]
        ) -> typing.Callable[..., typing.Any]:
            _annotate(fn_or_cls)
            if isinstance(fn_or_cls, type) and init and hasattr(fn_or_cls, "__init__"):
                _annotate(getattr(fn_or_cls, "__init__"))
            return fn_or_cls

        return _decorator

else:

    def strip_annotated(
        tp: typing.Any,
    ) -> typing.Tuple[typing.Any, typing.Tuple[typing.Any, ...]]:
        return tp, ()

    def annotate(
        attr: str, *annotations: typing.Any, init: bool = True
    ) -> typing.Callable[..., typing.Callable[..., typing.Any]]:
        raise RuntimeError("Annotations are not supported")
