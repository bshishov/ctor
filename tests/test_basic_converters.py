import pytest
import math
import datetime
from collections import Counter
import enum

from src.ctor import (
    NOT_PROVIDED,
    JsonSerializationContext,
    AnyLoadingPolicy,
    AnyDumpPolicy,
    IConverter,
    AnyConverter,
    ExactConverter,
    PrimitiveTypeConverter,
    NoneConverter,
    DatetimeTimestampConverter,
    SetConverter,
    DictConverter,
    ListConverter,
    TupleConverter,
    UnionTypeConverter,
    EnumConverter,
    LoadError,
)


DIFFERENT_TYPED_DATA = [
    None,
    42,
    True,
    1.0,
    "string",
    [1, 2, 3],
    {"foo": "bar"},
    {1, 2, 3},
    object(),
    int,
]

VALID_STRING_VALUES = ("", "long", "\u1234")
INVALID_STRING_VALUES = (1, True, {}, (), set(), object())
DEFAULT_SERIALIZATION_OPTIONS = JsonSerializationContext()


@pytest.fixture
def context():
    return JsonSerializationContext()


def converter_load_produces_same_result(converter: IConverter, value):
    assert (
        converter.load(value, key=NOT_PROVIDED, context=DEFAULT_SERIALIZATION_OPTIONS)
        == value
    )


def converter_dump_produces_same_result(converter: IConverter, value):
    assert converter.dump(value, context=DEFAULT_SERIALIZATION_OPTIONS) == value


def converter_load_raises_load_error(converter: IConverter, value):
    with pytest.raises(LoadError):
        assert converter.load(
            value, key=NOT_PROVIDED, context=DEFAULT_SERIALIZATION_OPTIONS
        )


@pytest.mark.parametrize("data", DIFFERENT_TYPED_DATA)
def test_exact_converter_dump(data, context):
    converter = ExactConverter()
    assert converter.dump(data, context=context) == data


@pytest.mark.parametrize("data", DIFFERENT_TYPED_DATA)
def test_exact_converter_load(data, context):
    converter = ExactConverter()
    assert converter.load(data, key=NOT_PROVIDED, context=context) == data


@pytest.mark.parametrize("data", DIFFERENT_TYPED_DATA)
def test_any_converter_dump_as_is(data, context):
    converter = AnyConverter(AnyLoadingPolicy.LOAD_AS_IS, AnyDumpPolicy.DUMP_AS_IS)
    assert converter.dump(data, context=context) == data


@pytest.mark.parametrize("data", DIFFERENT_TYPED_DATA)
def test_any_converter_load_as_is(data, context):
    converter = AnyConverter(AnyLoadingPolicy.LOAD_AS_IS, AnyDumpPolicy.DUMP_AS_IS)
    assert converter.load(data, key=NOT_PROVIDED, context=context) == data


@pytest.mark.parametrize("data", DIFFERENT_TYPED_DATA)
def test_any_converter_load_raises_if_any_load_raise_enabled(
    data, context
):
    converter = AnyConverter(AnyLoadingPolicy.RAISE_ERROR, AnyDumpPolicy.DUMP_AS_IS)
    with pytest.raises(TypeError):
        converter.load(data, key=NOT_PROVIDED, context=context)


@pytest.mark.parametrize("data", DIFFERENT_TYPED_DATA)
def test_any_converter_dump_raises_if_any_dump_raise_enabled(
    data, context
):
    converter = AnyConverter(AnyLoadingPolicy.LOAD_AS_IS, AnyDumpPolicy.RAISE_ERROR)
    with pytest.raises(TypeError):
        converter.dump(data, context=context)


@pytest.mark.parametrize("s", VALID_STRING_VALUES)
def test_primitive_string_converter_load_as_is(s):
    converter_load_produces_same_result(converter=PrimitiveTypeConverter(str), value=s)


@pytest.mark.parametrize("s", VALID_STRING_VALUES)
def test_primitive_string_converter_dump_as_is(s):
    converter_dump_produces_same_result(converter=PrimitiveTypeConverter(str), value=s)


@pytest.mark.parametrize("s", INVALID_STRING_VALUES)
def test_primitive_string_converter_load_raises_if_invalid_type(s):
    converter_load_raises_load_error(converter=PrimitiveTypeConverter(str), value=s)


@pytest.mark.parametrize(
    "x,expected",
    [
        (0, 0),
        (1, 1),
        (1e-4, 0),
        (42.456, 42),
    ],
)
def test_primitive_number_converter_load_as_int(
    x, expected: int, context
):
    int_converter = PrimitiveTypeConverter(int, float)
    assert int_converter.load(x, key=NOT_PROVIDED, context=context) == expected


@pytest.mark.parametrize(
    "x,expected",
    [
        (0, 0.0),
        (1, 1.0),
        (0.0, 0.0),
        (1e-4, 1e-4),
        (42.456, 42.456),
        (math.inf, math.inf),
    ],
)
def test_primitive_number_converter_load_as_float(
    x, expected: float, context
):
    float_converter = PrimitiveTypeConverter(float, int)
    assert float_converter.load(x, key=NOT_PROVIDED, context=context) == expected


@pytest.mark.parametrize("value", [[], list(DIFFERENT_TYPED_DATA)])
def test_list_converter_load(value):
    converter_load_produces_same_result(
        converter=ListConverter(ExactConverter()), value=value
    )


@pytest.mark.parametrize("value", [[], list(DIFFERENT_TYPED_DATA)])
def test_list_converter_dump(value):
    converter_dump_produces_same_result(
        converter=ListConverter(ExactConverter()), value=value
    )


def test_list_converter_raises_if_item_converter_raises():
    converter_load_raises_load_error(
        converter=ListConverter(PrimitiveTypeConverter(int)), value=[1, "INVALID", 3]
    )


@pytest.mark.parametrize("value", [{}, {"foo": "bar"}])
def test_dict_converter_load(value):
    converter_load_produces_same_result(
        converter=DictConverter(ExactConverter()), value=value
    )


@pytest.mark.parametrize("value", [{}, {"foo": "bar"}])
def test_dict_converter_dump(value):
    converter_dump_produces_same_result(
        converter=DictConverter(ExactConverter()), value=value
    )


def test_dict_converter_raises_if_item_converter_raises():
    converter_load_raises_load_error(
        converter=DictConverter(PrimitiveTypeConverter(int)),
        value={"valid_key": 1, "invalid_key": "not an int"},
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        (set(), set()),
        ({"foo", 42}, {"foo", 42}),
        ([1, 2], {1, 2}),
        ([1, 1], {1}),
    ],
)
def test_set_converter_load(value, expected, context):
    converter = SetConverter(ExactConverter())
    assert converter.load(value, key=NOT_PROVIDED, context=context) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (set(), []),
        ({"foo", 42}, ["foo", 42]),
        ({1, 2}, [1, 2]),
        ({1}, [1]),
    ],
)
def test_set_converter_dump(value, expected, context):
    converter = SetConverter(ExactConverter())
    # Order-invariant collection equality check
    assert Counter(converter.dump(value, context=context)) == Counter(expected)


def test_set_converter_raises_if_item_converter_raises():
    converter_load_raises_load_error(
        converter=SetConverter(PrimitiveTypeConverter(int)), value={1, "not an int", 2}
    )


@pytest.mark.parametrize(
    "types,value,expected",
    [
        ((), (), ()),
        ((), [], ()),
        ((str, int), ("foo", 42), ("foo", 42)),
        ((int, int), [1, 2], (1, 2)),
        ((int,), [1], (1,)),
    ],
)
def test_tuple_converter_load(
    types, value, expected, context
):
    converter = TupleConverter(*map(PrimitiveTypeConverter, types))
    assert converter.load(value, key=NOT_PROVIDED, context=context) == expected


@pytest.mark.parametrize(
    "types,value,expected",
    [
        ((), (), []),
        ((str, int), ("foo", 42), ["foo", 42]),
        ((int, int), (1, 2), [1, 2]),
        ((int, int), (1,), [1]),
    ],
)
def test_tuple_converter_dump(
    types, value, expected, context
):
    converter = TupleConverter(*map(PrimitiveTypeConverter, types))
    # Order-invariant collection equality check
    assert Counter(converter.dump(value, context=context)) == Counter(expected)


@pytest.mark.parametrize(
    "types,value",
    [
        ((), (1,)),
        ((str,), (1,)),
        ((int, int), (1, "non int")),
        ((int,), (1, "non int")),
    ],
)
def test_tuple_converter_raises_on_load(
    types, value, context
):
    converter = TupleConverter(*map(PrimitiveTypeConverter, types))
    with pytest.raises(LoadError):
        converter.load(value, key=NOT_PROVIDED, context=context)


@pytest.mark.parametrize("value", [0, 1, True, False])
def test_union_converter_load(value, context):
    converter = UnionTypeConverter(
        PrimitiveTypeConverter(int),
        PrimitiveTypeConverter(bool),
    )
    assert converter.load(value, key=NOT_PROVIDED, context=context) == value


@pytest.mark.parametrize("value", [0, 1, True, False])
def test_union_converter_dump(value, context):
    converter = UnionTypeConverter(
        PrimitiveTypeConverter(int),
        PrimitiveTypeConverter(bool),
    )
    assert converter.dump(value, context=context) == value


@pytest.mark.parametrize(
    "value,expected", [(0, 0), (1, 1), (True, 1), (False, 0), ("string", "string")]
)
def test_union_converter_load_first_suitable(
    value, expected, context
):
    converter = UnionTypeConverter(
        PrimitiveTypeConverter(int, bool),
        PrimitiveTypeConverter(bool),
        PrimitiveTypeConverter(str),
    )
    assert converter.load(value, key=NOT_PROVIDED, context=context) == expected


def test_union_converter_raises_if_no_converter_matches(
        context,
):
    converter = UnionTypeConverter(
        PrimitiveTypeConverter(int), PrimitiveTypeConverter(bool)
    )
    with pytest.raises(LoadError):
        converter.load("non an or bool", key=NOT_PROVIDED, context=context)


@pytest.mark.parametrize("value", [True, "foo"])
def test_union_converter_not_raises_if_no_converter_matches_in_first_nested_union(
    value, context
):
    converter = UnionTypeConverter(
        UnionTypeConverter(PrimitiveTypeConverter(int)),
        UnionTypeConverter(PrimitiveTypeConverter(bool)),
        UnionTypeConverter(PrimitiveTypeConverter(str)),
    )
    assert converter.load(value, key=NOT_PROVIDED, context=context) == value


def test_union_as_optional_converter(context):
    converter = UnionTypeConverter(PrimitiveTypeConverter(int), NoneConverter())
    assert converter.load(None, key=NOT_PROVIDED, context=context) is None


def test_union_as_optional_converter_raises_if_no_match(
        context,
):
    converter = UnionTypeConverter(PrimitiveTypeConverter(int), NoneConverter())
    with pytest.raises(LoadError):
        converter.load("non int", key=NOT_PROVIDED, context=context)


def test_datetime_iso_converter_load(context):
    # value = 1611429688.704779
    expected = datetime.datetime(2021, 1, 23, 19, 21, 28, 704779)
    converter = DatetimeTimestampConverter()
    assert (
        converter.load(expected.timestamp(), key=NOT_PROVIDED, context=context)
        == expected
    )


def test_datetime_iso_converter_dump(context):
    value = datetime.datetime(2021, 1, 23, 19, 21, 28, 704779)
    # expected = 1611429688.704779
    converter = DatetimeTimestampConverter()
    assert converter.dump(value, context=context) == value.timestamp()


def test_datetime_iso_converter_load_raises_if_invalid_format(
        context,
):
    value = "2021.01.23"
    converter = DatetimeTimestampConverter()
    with pytest.raises(LoadError):
        assert converter.load(value, key=NOT_PROVIDED, context=context)


class _ExampleEnum(enum.Enum):
    A = 1
    B = "2"


class _ExampleIntEnum(enum.IntEnum):
    A = 1
    B = 2


class _ExampleFlag(enum.Flag):
    RED = enum.auto()
    BLUE = enum.auto()
    GREEN = enum.auto()
    WHITE = RED | BLUE | GREEN


class _ExampleIntFlag(enum.IntFlag):
    R = 1
    W = 2
    X = 4


@pytest.mark.parametrize(
    "enum_type,value,expected",
    [
        (_ExampleEnum, 1, _ExampleEnum.A),
        (_ExampleEnum, "2", _ExampleEnum.B),
        (_ExampleIntEnum, 1, _ExampleIntEnum.A),
        (_ExampleIntEnum, 2, _ExampleIntEnum.B),
        (_ExampleIntFlag, 1, _ExampleIntFlag.R),
        (_ExampleIntFlag, 2, _ExampleIntFlag.W),
        (_ExampleIntFlag, 4, _ExampleIntFlag.X),
        (_ExampleIntFlag, 7, _ExampleIntFlag.R | _ExampleIntFlag.W | _ExampleIntFlag.X),
        (_ExampleFlag, 7, _ExampleFlag.WHITE),
        (_ExampleFlag, 1, _ExampleFlag.RED),
    ],
)
def test_enum_load(context, enum_type, value, expected):
    converter = EnumConverter(enum_type)
    value = converter.load(value, key=NOT_PROVIDED, context=context)
    assert value == expected
    assert isinstance(value, enum_type)


@pytest.mark.parametrize(
    "enum_type,value,expected",
    [
        (_ExampleEnum, _ExampleEnum.A, 1),
        (_ExampleEnum, _ExampleEnum.B, "2"),
        (_ExampleIntEnum, _ExampleIntEnum.A, 1),
        (_ExampleIntEnum, _ExampleIntEnum.B, 2),
        (_ExampleIntFlag, _ExampleIntFlag.R, 1),
        (_ExampleIntFlag, _ExampleIntFlag.W, 2),
        (_ExampleIntFlag, _ExampleIntFlag.X, 4),
        (_ExampleIntFlag, _ExampleIntFlag.R | _ExampleIntFlag.W | _ExampleIntFlag.X, 7),
        (_ExampleFlag, _ExampleFlag.WHITE, 7),
        (_ExampleFlag, _ExampleFlag.RED, 1),
    ],
)
def test_enum_dump(context, enum_type, value, expected):
    converter = EnumConverter(enum_type)
    assert converter.dump(value, context=context) == expected


@pytest.mark.parametrize("enum_type", [_ExampleEnum, _ExampleIntEnum])
def test_enum_converter_load_error_if_invalid_value(
        context, enum_type
):
    value = "this is non valid value"
    converter = EnumConverter(enum_type)
    with pytest.raises(LoadError):
        assert converter.load(value, key=NOT_PROVIDED, context=context)
