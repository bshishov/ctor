import typing
from attr import attrs
import pytest

import ctor

try:
    # Starting from python 3.9+
    from typing import Annotated

    _ANNOTATED_SUPPORTED = True
except ImportError:
    # Backport for older python versions
    try:
        from typing_extensions import Annotated  # type: ignore

        _ANNOTATED_SUPPORTED = True
    except ImportError:
        _ANNOTATED_SUPPORTED = False


def assert_has_annotated(obj, param: str, annotation):
    try:
        # Python 3.9. PEP-593
        hints = typing.get_type_hints(obj, include_extras=True)
    except TypeError:
        hints = typing.get_type_hints(obj)
    hint = hints[param]
    assert annotation in hint.__metadata__


@pytest.mark.skipif(not _ANNOTATED_SUPPORTED, reason="Annotations unsupported")
def test_annotation_in_annotated_metadata():
    annotation = object()
    assert Annotated[int, annotation].__metadata__ == (annotation,)


@pytest.mark.skipif(not _ANNOTATED_SUPPORTED, reason="Annotations unsupported")
def test_param_annotation_simple_class():
    annotation = object()

    @ctor.annotate("x", annotation)
    class MyClass:
        def __init__(self, x: int):
            self.x = x

    assert_has_annotated(MyClass, "x", annotation)
    assert_has_annotated(MyClass.__init__, "x", annotation)


@pytest.mark.skipif(not _ANNOTATED_SUPPORTED, reason="Annotations unsupported")
def test_param_annotation_attrs():
    annotation = object()

    @ctor.annotate("x", annotation)
    @attrs(auto_attribs=True, slots=True)
    class MyClass:
        x: int

    assert_has_annotated(MyClass, "x", annotation)
    assert_has_annotated(MyClass.__init__, "x", annotation)


@pytest.mark.skipif(not _ANNOTATED_SUPPORTED, reason="Annotations unsupported")
def test_param_annotation_namedtuple():
    annotation = object()

    @ctor.annotate("x", annotation, init=False)
    class MyClass(typing.NamedTuple):
        x: int

    assert_has_annotated(MyClass, "x", annotation)


@pytest.mark.skipif(not _ANNOTATED_SUPPORTED, reason="Annotations unsupported")
def test_annotated_simple_class():
    annotation = object()

    class MyClass:
        x: Annotated[int, annotation]

        def __init__(self, x: Annotated[int, annotation]):
            self.x = x

    assert_has_annotated(MyClass, "x", annotation)
    assert_has_annotated(MyClass.__init__, "x", annotation)


@pytest.mark.skipif(not _ANNOTATED_SUPPORTED, reason="Annotations unsupported")
def test_annotated_attrs():
    annotation = object()

    @attrs(auto_attribs=True, slots=True)
    class MyClass:
        x: Annotated[int, annotation]

    assert_has_annotated(MyClass, "x", annotation)
    assert_has_annotated(MyClass.__init__, "x", annotation)


@pytest.mark.skipif(not _ANNOTATED_SUPPORTED, reason="Annotations unsupported")
def test_annotated_namedtuple():
    annotation = object()

    class MyClass(typing.NamedTuple):
        x: Annotated[int, annotation]

    assert_has_annotated(MyClass, "x", annotation)
