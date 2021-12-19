import pytest
import typing
from datetime import datetime as dtime
import enum

from attr import dataclass, attrib

import ctor


@pytest.fixture(scope='module')
def obj_converter_factory() -> ctor.ObjectConverterFactory:
    return ctor.ObjectConverterFactory()


@pytest.fixture
def options():
    return ctor.JsonSerializationContext()


@pytest.fixture
def converter_factory(obj_converter_factory) -> typing.Callable[[typing.Type, ctor.JsonSerializationContext], ctor.IConverter]:
    return obj_converter_factory.try_create_converter


class EmptyClass:
    pass


def test_load_empty_object(converter_factory, options):
    converter = converter_factory(EmptyClass, options)
    assert isinstance(converter.load({}, key=ctor.NOT_PROVIDED, context=options), EmptyClass)


def test_dump_empty_object(converter_factory, options):
    converter = converter_factory(EmptyClass, options)
    assert converter.dump(EmptyClass(), context=options) == {}


@dataclass
class ClassWithIntAttr:
    attr: int
    type: typing.ClassVar[str] = "int_attr"


@dataclass
class ClassWithDefaultAttr:
    attr: int = 42
    type: typing.ClassVar[str] = "default_attr"


@dataclass
class ClassWithOptionalAttr:
    attr: typing.Optional[int]
    type: typing.ClassVar[str] = "optional_attr"


@dataclass
class NestedClass:
    attr: ClassWithIntAttr


@dataclass
class NestedClassForwardRef:
    attr: 'ClassWithIntAttr'


@dataclass
class RecursiveClass:
    attr: typing.Optional['RecursiveClass']


@dataclass
class ClassWithDiscriminatedUnionAttr:
    attr: typing.Union[ClassWithOptionalAttr, ClassWithDefaultAttr, ClassWithIntAttr]


@pytest.fixture(scope='module')
def discriminated_converter_factory() -> ctor.DiscriminatedConverterFactory:
    discriminator_type_map = {
        "optional_attr": ClassWithOptionalAttr,
        "default_attr": ClassWithDefaultAttr,
        "int_attr": ClassWithIntAttr
    }
    return ctor.DiscriminatedConverterFactory(
        discriminator_key="type",
        discriminator_type_map=discriminator_type_map,
        converter_factory=ctor.ObjectConverterFactory()
    )


@pytest.mark.parametrize('data, expected', [
    ({"attr": {"type": "optional_attr", "attr": 1}}, ClassWithOptionalAttr(1)),
    ({"attr": {"type": "default_attr", "attr": 1}}, ClassWithDefaultAttr(1)),
    ({"attr": {"type": "int_attr", "attr": 1}}, ClassWithIntAttr(1))
])
def test_discriminated_union_class_load(data, expected, discriminated_converter_factory, options):
    options.converter_factories.insert(0, discriminated_converter_factory)
    obj = ctor.load(ClassWithDiscriminatedUnionAttr, data=data, context=options)
    assert obj.attr == expected


@pytest.mark.parametrize('cls,data,expected', [
    (ClassWithIntAttr, {'attr': 1}, ClassWithIntAttr(1)),
    (ClassWithIntAttr, {'attr': 1.0}, ClassWithIntAttr(1)),
    (ClassWithIntAttr, {'attr': 1.0}, ClassWithIntAttr(1)),
    (ClassWithIntAttr, {'attr': 1, 'not_used_data': 'kek'}, ClassWithIntAttr(1)),
    (ClassWithDefaultAttr, {'attr': 1}, ClassWithDefaultAttr(1)),
    (ClassWithDefaultAttr, {'attr': 42}, ClassWithDefaultAttr()),
    (ClassWithDefaultAttr, {}, ClassWithDefaultAttr()),
    (ClassWithDefaultAttr, {}, ClassWithDefaultAttr(42)),
    (ClassWithOptionalAttr, {'attr': None}, ClassWithOptionalAttr(None)),
    (ClassWithOptionalAttr, {'attr': 1}, ClassWithOptionalAttr(1)),
    (NestedClass, {'attr': {'attr': 1}}, NestedClass(ClassWithIntAttr(1))),
    (NestedClassForwardRef, {'attr': {'attr': 1}}, NestedClassForwardRef(ClassWithIntAttr(1))),
    (RecursiveClass, {'attr': None}, RecursiveClass(None)),
    (RecursiveClass, {'attr': {'attr': None}}, RecursiveClass(RecursiveClass(None))),
    (RecursiveClass, {'attr': {'attr': {'attr': None}}}, RecursiveClass(RecursiveClass(RecursiveClass(None)))),
])
def test_load_class(cls, data, expected, converter_factory, options):
    converter = converter_factory(cls, options)
    obj = converter.load(data, key=ctor.NOT_PROVIDED, context=options)
    assert obj == expected


@pytest.mark.parametrize('cls,data', [
    (ClassWithIntAttr, {}),
    (ClassWithOptionalAttr, {}),
    (ClassWithIntAttr, None),
    (ClassWithIntAttr, 'wrong type'),
    (ClassWithIntAttr, {'attr': 'not int'}),
    (ClassWithOptionalAttr, {'attr': 'not int'}),
    (NestedClass, {'attr': 'not obj'}),
    (NestedClass, {'attr': None}),
    (NestedClass, {'attr': {}}),
    (NestedClass, {}),
    (NestedClassForwardRef, {'attr': 'not obj'}),
    (NestedClassForwardRef, {'attr': None}),
    (NestedClassForwardRef, {'attr': {}}),
    (NestedClassForwardRef, {}),
])
def test_load_invalid_class_raises(cls, data, converter_factory, options):
    converter = converter_factory(cls, options)
    with pytest.raises(ctor.LoadError):
        converter.load(data, key=ctor.NOT_PROVIDED, context=options)


@pytest.mark.parametrize('cls,data,expected', [
    (ClassWithIntAttr, ClassWithIntAttr(1), {'attr': 1}),
    (ClassWithDefaultAttr, ClassWithDefaultAttr(1), {'attr': 1}),
    (ClassWithDefaultAttr, ClassWithDefaultAttr(), {'attr': 42}),
    (ClassWithOptionalAttr, ClassWithOptionalAttr(None), {'attr': None}),
    (ClassWithOptionalAttr, ClassWithOptionalAttr(1), {'attr': 1}),
    (NestedClass, NestedClass(ClassWithIntAttr(1)), {'attr': {'attr': 1}}),
    (NestedClassForwardRef, NestedClassForwardRef(ClassWithIntAttr(1)), {'attr': {'attr': 1}}),
    (RecursiveClass, RecursiveClass(None), {'attr': None}),
    (RecursiveClass, RecursiveClass(RecursiveClass(None)), {'attr': {'attr': None}}),
])
def test_dump_class(cls, data, expected, converter_factory, options):
    converter = converter_factory(cls, options)
    obj = converter.dump(data, context=options)
    assert obj == expected


def attr_factory():
    return 42


def obj_attr_factory():
    return ClassWithIntAttr(42)


@dataclass
class AttrsWithAttrFactory:
    attr: int = attrib(factory=attr_factory)


@dataclass
class AttrsWithOptionalAttrFactory:
    attr: typing.Optional[int] = attrib(factory=attr_factory)


@dataclass
class AttrsWithOptionalObjAttrFactory:
    attr: typing.Optional[ClassWithIntAttr] = attrib(factory=obj_attr_factory)


def test_load_obj_with_optional_attr_factory(options: ctor.JsonSerializationContext):
    obj = ctor.load(AttrsWithOptionalAttrFactory, {}, key=ctor.NOT_PROVIDED, context=options)
    assert obj == AttrsWithOptionalAttrFactory()
    assert obj.attr == 42


def test_load_obj_with_obj_optional_attr_factory(options: ctor.JsonSerializationContext):
    obj = ctor.load(AttrsWithOptionalObjAttrFactory, {}, key=ctor.NOT_PROVIDED, context=options)
    assert obj == AttrsWithOptionalObjAttrFactory()
    assert obj.attr == ClassWithIntAttr(42)


def test_load_obj_with_attr_factory(options: ctor.JsonSerializationContext):
    obj = ctor.load(AttrsWithAttrFactory, {}, key=ctor.NOT_PROVIDED, context=options)
    assert obj == AttrsWithAttrFactory()
    assert obj.attr == 42


@dataclass
class ClassWithOptionalAny:
    attr: typing.Optional[typing.Any] = None


def test_load_obj_with_optional_any_default(options: ctor.JsonSerializationContext):
    obj = ctor.load(ClassWithOptionalAny, {}, key=ctor.NOT_PROVIDED, context=options)
    assert obj == ClassWithOptionalAny()


def test_load_obj_with_optional_any(options: ctor.JsonSerializationContext):
    obj = ctor.load(ClassWithOptionalAny, {'attr': 'not default'}, key=ctor.NOT_PROVIDED, context=options)
    assert obj == ClassWithOptionalAny('not default')


class ExampleOption(enum.IntEnum):
    DO_NOTHING = 0
    DO_USEFUL_STUFF = 1


@dataclass
class Child:
    value: int


@dataclass
class DummyClass:
    no_default: int
    tp: typing.Tuple[int, str] = (1, 'hello')
    default: str = 'hello'
    attrib_default: float = attrib(default=4.5)
    datetime: dtime = attrib(factory=lambda: dtime(2020, 11, 14))
    option: ExampleOption = ExampleOption.DO_USEFUL_STUFF
    child: Child = Child(value=42)
    list_of_child: typing.List[Child] = [Child(1), Child(2)]
    dict_of_child: typing.Dict[str, Child] = {
        'a': Child(1),
        'b': Child(2)
    }


def test_load():
    obj = ctor.load(DummyClass, {'no_default': 10})
    assert obj.no_default == 10


def test_dump():
    obj = DummyClass(no_default=10)
    data = ctor.dump(obj)

    assert data == {
        'no_default': 10,
        'tp': [1, 'hello'],
        'default': 'hello',
        'attrib_default': 4.5,
        'datetime': dtime(2020, 11, 14).timestamp(),
        'dict_of_child': {'a': {'value': 1}, 'b': {'value': 2}},
        'list_of_child': [{'value': 1}, {'value': 2}],
        'child': {
            'value': 42
        },
        'option': 1
    }


@dataclass
class AnyDummy:
    foo: typing.Any


def test_any_dump(options: ctor.JsonSerializationContext):
    obj = AnyDummy(foo=[1, 'hello', {}])
    data = ctor.dump(obj, context=options)
    assert data == {'foo': [1, 'hello', {}]}


def test_any_load(options: ctor.JsonSerializationContext):
    data = {'foo': [1, 'hello', {}]}
    obj = ctor.load(AnyDummy, data, context=options)
    assert obj.foo == [1, 'hello', {}]
