import typing

__all__ = [
    "UNSUPPORTED",
    "Annotated",
    "Literal",
    "ForwardRef",
    "eval_type",
    "get_origin",
    "is_subclass",
    "strip_annotated",
    "get_args",
]


# Special variable to test if specific type from future python is unsupported
UNSUPPORTED = typing.NewType("UNSUPPORTED", typing.NoReturn)


try:
    # Starting from python 3.9+
    from typing import Annotated
except ImportError:
    # Backport for older python versions
    try:
        from typing_extensions import Annotated  # type: ignore
    except ImportError:
        Annotated = UNSUPPORTED


try:
    # Starting from python 3.8+
    from typing import Literal
except ImportError:
    try:
        # Backport for older python versions
        from typing_extensions import Literal  # type: ignore
    except ImportError:
        Literal = UNSUPPORTED


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
    raise ImportError('typing.ForwardRef is not supported')


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
    return getattr(tp, "__args__", tuple())


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


if Annotated is UNSUPPORTED:
    def strip_annotated(tp) -> typing.Tuple[typing.Any, typing.Tuple[typing.Any, ...]]:
        return tp, ()
else:
    def strip_annotated(tp) -> typing.Tuple[typing.Any, typing.Tuple[typing.Any, ...]]:
        if hasattr(tp, '__metadata__') and hasattr(tp, '__origin__'):
            if tp.__origin__ is Annotated:
                return tp.__args__[0], tp.__metadata__
            return tp.__origin__, tp.__metadata__
        return tp, ()
