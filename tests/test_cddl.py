# ruff: noqa: FBT001

from enum import Enum, IntEnum
from typing import Annotated, Any, Literal, get_origin

import pytest
from pydantic import BaseModel, Field, computed_field

from cbor_model import CBORField, CBORModel, CDDLGenerator
from cbor_model._config import CBORConfig
from cbor_model._util import (
    extract_types_matching,
    is_optional,
    is_type_of,
    is_union_type,
)

from .conftest import Contact, Item, TaggedItem


class TestCDDLGenerator:
    """Test the CDDL generator."""

    def test_simple_map_structure(self) -> None:
        """Test CDDL generation for a simple map structure."""

        class Person(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            age: Annotated[int, CBORField(key=1), Field(gt=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Person)

        expected = """person_name = 0
person_age = 1

Person = {
    person_name: tstr,
    person_age: int .gt 0
}"""
        assert cddl == expected

    def test_optional_fields(self) -> None:
        """Test CDDL generation with optional fields."""

        class Contact(CBORModel):
            email: Annotated[str, CBORField(key=0)]
            phone: Annotated[str | None, CBORField(key=1)]

        generator = CDDLGenerator()
        cddl = generator.generate(Contact)

        expected = """contact_email = 0
contact_phone = 1

Contact = {
    contact_email: tstr,
    ? contact_phone: tstr
}"""
        assert cddl == expected

    def test_list_fields(self) -> None:
        """Test CDDL generation with list fields."""

        class Team(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            members: Annotated[list[str], CBORField(key=1)]

        generator = CDDLGenerator()
        cddl = generator.generate(Team)

        expected = """team_name = 0
team_members = 1

Team = {
    team_name: tstr,
    team_members: [* tstr]
}"""
        assert cddl == expected

    @pytest.mark.parametrize(
        ("min_length", "max_length", "expected_type"),
        [
            (None, None, "[* tstr]"),
            (5, None, "[5* tstr]"),
            (None, 10, "[*10 tstr]"),
            (1, 3, "[1*3 tstr]"),
            (1, None, "[+ tstr]"),
        ],
        ids=[
            "no_constraints",
            "min_length_only",
            "max_length_only",
            "min_and_max_length",
            "one_or_more",
        ],
    )
    def test_list_with_constraints(
        self,
        min_length: int | None,
        max_length: int | None,
        expected_type: str,
    ) -> None:
        """Test CDDL generation with list fields having length constraints."""

        class Team(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            members: Annotated[
                list[str],
                CBORField(key=1),
                Field(
                    min_length=min_length,
                    max_length=max_length,
                ),
            ]

        generator = CDDLGenerator()
        cddl = generator.generate(Team)

        expected = f"""team_name = 0
team_members = 1

Team = {{
    team_name: tstr,
    team_members: {expected_type}
}}"""
        assert cddl == expected

    @pytest.mark.parametrize(
        ("min_length", "max_length", "expected_type"),
        [
            (None, None, "tstr"),
            (1, 50, "tstr .size (1..50)"),
        ],
        ids=[
            "no_constraints",
            "min_and_max_length",
        ],
    )
    def test_str_with_constraints(
        self,
        min_length: int | None,
        max_length: int | None,
        expected_type: str,
    ) -> None:
        """Test CDDL generation with str fields having constraints."""

        class Person(CBORModel):
            name: Annotated[
                str,
                CBORField(key=0),
                Field(min_length=min_length, max_length=max_length),
            ]

        generator = CDDLGenerator()
        cddl = generator.generate(Person)

        expected = f"""person_name = 0

Person = {{
    person_name: {expected_type}
}}"""
        assert cddl == expected

    @pytest.mark.parametrize(
        ("min_length", "max_length"),
        [
            (5, None),
            (None, 10),
        ],
        ids=[
            "min_length_only",
            "max_length_only",
        ],
    )
    def test_str_with_one_sided_constraints_raises(
        self,
        min_length: int | None,
        max_length: int | None,
    ) -> None:
        """Test RFC 8610 compliance for string size constraints."""

        class Person(CBORModel):
            name: Annotated[
                str,
                CBORField(key=0),
                Field(min_length=min_length, max_length=max_length),
            ]

        generator = CDDLGenerator()
        with pytest.raises(
            ValueError,
            match=r"RFC 8610 requires \.size constraints",
        ):
            generator.generate(Person)

    @pytest.mark.parametrize(
        ("min_length", "max_length", "expected_type"),
        [
            (None, None, "bstr"),
            (1, 50, "bstr .size (1..50)"),
            (32, 32, "bstr .size 32"),
        ],
        ids=[
            "no_constraints",
            "min_and_max_length",
            "exact_length",
        ],
    )
    def test_bytes_with_constraints(
        self,
        min_length: int | None,
        max_length: int | None,
        expected_type: str,
    ) -> None:
        """Test CDDL generation with bytes fields having constraints."""

        class Packet(CBORModel):
            data: Annotated[
                bytes,
                CBORField(key=0),
                Field(min_length=min_length, max_length=max_length),
            ]

        generator = CDDLGenerator()
        cddl = generator.generate(Packet)

        expected = f"""packet_data = 0

Packet = {{
    packet_data: {expected_type}
}}"""
        assert cddl == expected

    @pytest.mark.parametrize(
        ("min_length", "max_length"),
        [
            (5, None),
            (None, 10),
        ],
        ids=[
            "min_length_only",
            "max_length_only",
        ],
    )
    def test_bytes_with_one_sided_constraints_raises(
        self,
        min_length: int | None,
        max_length: int | None,
    ) -> None:
        """Test RFC 8610 compliance for byte string size constraints."""

        class Packet(CBORModel):
            data: Annotated[
                bytes,
                CBORField(key=0),
                Field(min_length=min_length, max_length=max_length),
            ]

        generator = CDDLGenerator()
        with pytest.raises(
            ValueError,
            match=r"RFC 8610 requires \.size constraints",
        ):
            generator.generate(Packet)

    @pytest.mark.parametrize(
        ("min_length", "max_length", "expected_type"),
        [
            (None, None, "tstr"),
            (1, 50, "tstr .size (1..50)"),
        ],
        ids=[
            "no_constraints",
            "min_and_max_length",
        ],
    )
    def test_optional_str_with_constraints(
        self,
        min_length: int | None,
        max_length: int | None,
        expected_type: str,
    ) -> None:
        """Test that constraints on Optional[str] fields are not silently dropped."""

        class Person(CBORModel):
            name: Annotated[
                str | None,
                CBORField(key=0),
                Field(min_length=min_length, max_length=max_length),
            ] = None

        generator = CDDLGenerator()
        cddl = generator.generate(Person)

        expected = f"""person_name = 0

Person = {{
    ? person_name: {expected_type}
}}"""
        assert cddl == expected

    @pytest.mark.parametrize(
        ("min_length", "max_length"),
        [
            (5, None),
            (None, 10),
        ],
        ids=[
            "min_length_only",
            "max_length_only",
        ],
    )
    def test_optional_str_with_one_sided_constraints_raises(
        self,
        min_length: int | None,
        max_length: int | None,
    ) -> None:
        """Test RFC 8610 compliance for optional string size constraints."""

        class Person(CBORModel):
            name: Annotated[
                str | None,
                CBORField(key=0),
                Field(min_length=min_length, max_length=max_length),
            ] = None

        generator = CDDLGenerator()
        with pytest.raises(
            ValueError,
            match=r"RFC 8610 requires \.size constraints",
        ):
            generator.generate(Person)

    def test_nested_models(self) -> None:
        """Test CDDL generation with nested CBORModel classes."""

        class Address(CBORModel):
            street: Annotated[str, CBORField(key=0)]
            city: Annotated[str, CBORField(key=1)]

        class Company(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            address: Annotated[Address, CBORField(key=1)]

        generator = CDDLGenerator()
        cddl = generator.generate(Company)

        expected = """address_street = 0
address_city = 1

Address = {
    address_street: tstr,
    address_city: tstr
}

company_name = 0
company_address = 1

Company = {
    company_name: tstr,
    company_address: Address
}"""
        assert cddl == expected

    def test_recursive_model(self) -> None:
        """Test CDDL generation with recursive type."""

        class Node(CBORModel):
            value: Annotated[int, CBORField(key=0)]
            children: Annotated[list["Node"] | None, CBORField(key=1)]

        generator = CDDLGenerator()
        cddl = generator.generate(Node)

        expected = """node_value = 0
node_children = 1

Node = {
    node_value: int,
    ? node_children: [* Node]
}"""
        assert cddl == expected

    def test_override_name(self) -> None:
        """Test CDDL generation with override_name (used verbatim)."""

        class Product(CBORModel):
            internal_id: Annotated[
                str,
                CBORField(key=0, override_name="product_id"),
            ]

        generator = CDDLGenerator()
        cddl = generator.generate(Product)

        expected = """product_product_id = 0

Product = {
    product_product_id: tstr
}"""
        assert cddl == expected

    def test_override_type(self) -> None:
        """Test CDDL generation with override_type."""

        class Config(CBORModel):
            data: Annotated[
                bytes,
                CBORField(key=0, override_type="bstr .size 32"),
            ]

        generator = CDDLGenerator()
        cddl = generator.generate(Config)

        expected = """config_data = 0

Config = {
    config_data: bstr .size 32
}"""
        assert cddl == expected

    def test_cbor_tag(self) -> None:
        """Test CDDL generation with CBOR tag."""

        class Tagged(CBORModel):
            value: Annotated[str, CBORField(key=0, tag=123)]

        generator = CDDLGenerator()
        cddl = generator.generate(Tagged)

        expected = """tagged_value = 0

Tagged = {
    tagged_value: #6.123(tstr)
}"""
        assert cddl == expected

    def test_type_mapping(self) -> None:
        """Test CDDL type mappings for basic Python types."""

        class Types(CBORModel):
            text: Annotated[str, CBORField(key=0)]
            data: Annotated[bytes, CBORField(key=1)]
            count: Annotated[int, CBORField(key=2)]
            flag: Annotated[bool, CBORField(key=3)]
            ratio: Annotated[float, CBORField(key=4)]

        generator = CDDLGenerator()
        cddl = generator.generate(Types)

        expected = """types_text = 0
types_data = 1
types_count = 2
types_flag = 3
types_ratio = 4

Types = {
    types_text: tstr,
    types_data: bstr,
    types_count: int,
    types_flag: bool,
    types_ratio: float
}"""
        assert cddl == expected

    def test_uint_constraint(self) -> None:
        """Test precise CDDL generation for lower-bound integer constraints."""

        class Numbers(CBORModel):
            positive_gt: Annotated[int, CBORField(key=0), Field(gt=0)]
            positive_ge: Annotated[int, CBORField(key=1), Field(ge=0)]
            any_int: Annotated[int, CBORField(key=2)]

        generator = CDDLGenerator()
        cddl = generator.generate(Numbers)

        expected = """numbers_positive_gt = 0
numbers_positive_ge = 1
numbers_any_int = 2

Numbers = {
    numbers_positive_gt: int .gt 0,
    numbers_positive_ge: uint,
    numbers_any_int: int
}"""
        assert cddl == expected

    def test_int_upper_and_range_constraints(self) -> None:
        """Test that int bounds emit RFC 8610 controls and ranges."""

        class Numbers(CBORModel):
            upper_only: Annotated[int, CBORField(key=0), Field(le=10)]
            exclusive_upper: Annotated[int, CBORField(key=1), Field(lt=10)]
            bounded_uint: Annotated[int, CBORField(key=2), Field(ge=0, le=255)]
            bounded_signed: Annotated[int, CBORField(key=3), Field(ge=-10, le=10)]
            normalized_range: Annotated[int, CBORField(key=4), Field(gt=0, lt=10)]

        generator = CDDLGenerator()
        cddl = generator.generate(Numbers)

        expected = """numbers_upper_only = 0
numbers_exclusive_upper = 1
numbers_bounded_uint = 2
numbers_bounded_signed = 3
numbers_normalized_range = 4

Numbers = {
    numbers_upper_only: int .le 10,
    numbers_exclusive_upper: int .lt 10,
    numbers_bounded_uint: 0..255,
    numbers_bounded_signed: -10..10,
    numbers_normalized_range: 1..9
}"""
        assert cddl == expected

    def test_explicit_optional(self) -> None:
        """Test that explicit optional=True in CBORField works."""

        class Example(CBORModel):
            required_with_default: Annotated[str, CBORField(key=0)] = "default"
            explicit_optional: Annotated[
                list[str],
                CBORField(key=1, optional=True),
            ] = Field(default_factory=list)

        generator = CDDLGenerator()
        cddl = generator.generate(Example)

        expected = """example_required_with_default = 0
example_explicit_optional = 1

Example = {
    example_required_with_default: tstr,
    ? example_explicit_optional: [* tstr]
}"""
        assert cddl == expected

    def test_enum_generation(self) -> None:
        """Test CDDL generation for IntEnum types."""

        class Color(IntEnum):
            RED = 1
            GREEN = 2
            BLUE = 3

        class Palette(CBORModel):
            primary: Annotated[Color, CBORField(key=0)]
            secondary: Annotated[Color | None, CBORField(key=1)] = None

        generator = CDDLGenerator()
        cddl = generator.generate(Palette)

        expected = """Color = &(
    RED: 1,
    GREEN: 2,
    BLUE: 3
)

palette_primary = 0
palette_secondary = 1

Palette = {
    palette_primary: Color,
    ? palette_secondary: Color
}"""
        assert cddl == expected

    def test_enum_generation_choices(self) -> None:
        """Test CDDL generation for IntEnum types with choices style."""

        class Color(IntEnum):
            RED = 1
            GREEN = 2
            BLUE = 3

        class Palette(CBORModel):
            primary: Annotated[Color, CBORField(key=0)]
            secondary: Annotated[Color | None, CBORField(key=1)] = None

        generator = CDDLGenerator(enum_style="choices")
        cddl = generator.generate(Palette)

        expected = """color_red = 1
color_green = 2
color_blue = 3

Color /= color_red
Color /= color_green
Color /= color_blue

palette_primary = 0
palette_secondary = 1

Palette = {
    palette_primary: Color,
    ? palette_secondary: Color
}"""
        assert cddl == expected

    def test_dict_field(self) -> None:
        """Test CDDL generation for dict fields."""

        class Config(CBORModel):
            metadata: Annotated[dict[str, str], CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Config)

        expected = """config_metadata = 0

Config = {
    config_metadata: {* tstr => tstr}
}"""
        assert cddl == expected

    def test_dict_field_any_value(self) -> None:
        """Test CDDL for dict with heterogeneous values."""

        class Config(CBORModel):
            data: Annotated[dict[str, Any], CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Config)

        expected = """config_data = 0

Config = {
    config_data: {* tstr => any}
}"""
        assert cddl == expected


class TestCDDLUtilities:
    """Test utility functions used by CDDL generator."""

    @pytest.mark.parametrize(
        ("type_annotation", "expected"),
        [
            (str | int, True),
            (str | int | float, True),
            (str, False),
            (int, False),
            (list[str], False),
            (dict[str, int], False),
        ],
        ids=[
            "union_two_types",
            "union_three_types",
            "simple_str",
            "simple_int",
            "list_type",
            "dict_type",
        ],
    )
    def test_is_union_type(
        self,
        type_annotation: type,
        expected: bool,
    ) -> None:
        """Test is_union_type detection."""
        origin = get_origin(type_annotation)
        assert is_union_type(type_annotation) == expected
        assert is_union_type(origin) == expected

    @pytest.mark.parametrize(
        ("type_annotation", "expected"),
        [
            (str | None, True),
            (int | None, True),
            (list[str] | None, True),
            (CBORModel | None, True),
            (str | int | None, True),
            (str, False),
            (int, False),
            (list[str], False),
            (CBORModel, False),
            (str | int, False),
            (str | int | float, False),
        ],
        ids=[
            "optional_str",
            "optional_int",
            "optional_list",
            "optional_basemodel",
            "multi_union_with_none",
            "simple_str",
            "simple_int",
            "list_type",
            "basemodel",
            "union_without_none",
            "multi_union_without_none",
        ],
    )
    def test_is_optional(
        self,
        type_annotation: type,
        expected: bool,
    ) -> None:
        """Test is_optional detection."""
        assert is_optional(type_annotation) == expected

    @pytest.mark.parametrize(
        ("annotation", "target", "expected"),
        [
            (CBORModel, CBORModel, True),
            (str, str, True),
            (int, int, True),
            (str, CBORModel, False),
            (int, CBORModel, False),
            (list, CBORModel, False),
            (CBORModel, str, False),
            ("string", str, False),
            (123, int, False),
        ],
        ids=[
            "exact_cbormodel",
            "exact_str",
            "exact_int",
            "str_not_basemodel",
            "int_not_basemodel",
            "list_not_basemodel",
            "basemodel_not_str",
            "string_instance_not_type",
            "int_instance_not_type",
        ],
    )
    def test_is_type_of(
        self,
        annotation: type,
        target: type,
        expected: bool,
    ) -> None:
        """Test is_type_of with various type checks."""
        assert is_type_of(annotation, target) == expected

    @pytest.mark.parametrize(
        ("annotation", "predicate", "expected_types"),
        [
            (Contact, CBORModel, [Contact]),
            (Contact | None, CBORModel, [Contact]),
            (list[Contact], CBORModel, [Contact]),
            (
                Contact | Item,
                CBORModel,
                [Contact, Item],
            ),
            (
                list[Contact | Item],
                CBORModel,
                [Contact, Item],
            ),
            (
                list[TaggedItem | Item] | Contact | None,
                CBORModel,
                [Contact, TaggedItem, Item],
            ),
            (str, CBORModel, []),
            (list[str], CBORModel, []),
        ],
        ids=[
            "simple_type",
            "optional_type",
            "list_type",
            "union_type",
            "nested_union_in_list",
            "complex_nested",
            "non_matching_str",
            "non_matching_list",
        ],
    )
    def test_extract_types_matching(
        self,
        annotation: type,
        predicate: type,
        expected_types: list[type],
    ) -> None:
        """Test extract_types_matching with various type structures."""
        results: list[type] = extract_types_matching(annotation, predicate)
        assert len(results) == len(expected_types)
        for expected_type in expected_types:
            assert expected_type in results

    def test_extract_types_matching_enum_types(self) -> None:
        """Test extract_types_matching can find Enum types."""

        class Color(IntEnum):
            RED = 1
            GREEN = 2
            BLUE = 3

        results = extract_types_matching(Color, Enum)
        assert len(results) == 1
        assert Color in results

        results = extract_types_matching(Color | None, Enum)
        assert len(results) == 1
        assert Color in results

        results = extract_types_matching(list[Color], Enum)
        assert len(results) == 1
        assert Color in results

    def test_numeric_constraints(self) -> None:
        """Test that numeric constraints are correctly applied in CDDL generation."""

        class Numbers(CBORModel):
            positive_gt: Annotated[int, CBORField(key=0), Field(gt=0)]
            positive_ge: Annotated[int, CBORField(key=1), Field(ge=0)]
            any_int: Annotated[int, CBORField(key=2)]
            negative_lt: Annotated[int, CBORField(key=3), Field(lt=0)]
            negative_le: Annotated[int, CBORField(key=4), Field(le=-1)]
            custom: Annotated[
                int,
                CBORField(key=5, override_type="int -10..10"),
            ]

        generator = CDDLGenerator()
        cddl = generator.generate(Numbers)

        expected = """numbers_positive_gt = 0
numbers_positive_ge = 1
numbers_any_int = 2
numbers_negative_lt = 3
numbers_negative_le = 4
numbers_custom = 5

Numbers = {
    numbers_positive_gt: int .gt 0,
    numbers_positive_ge: uint,
    numbers_any_int: int,
    numbers_negative_lt: nint,
    numbers_negative_le: nint,
    numbers_custom: int -10..10
}"""
        assert cddl == expected


class TestCDDLArrayEncoding:
    """Test CDDL generation for array-encoded models."""

    def test_basic_array_struct(self) -> None:
        """Array-encoded model generates bracketed CDDL."""

        class Point(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            x: Annotated[float, CBORField(index=0)]
            y: Annotated[float, CBORField(index=1)]
            z: Annotated[float, CBORField(index=2)]

        generator = CDDLGenerator()
        cddl = generator.generate(Point)

        expected = """Point = [
    x: float,
    y: float,
    z: float
]"""
        assert cddl == expected

    def test_optional_tail_fields_marked_optional(self) -> None:

        class Msg(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            required: Annotated[str, CBORField(index=0)]
            opt_a: Annotated[str | None, CBORField(index=1)] = None
            opt_b: Annotated[int | None, CBORField(index=2)] = None

        generator = CDDLGenerator()
        cddl = generator.generate(Msg)

        expected = """Msg = [
    required: tstr,
    ? opt_a: tstr,
    ? opt_b: int
]"""
        assert cddl == expected

    def test_explicit_optional_flag(self) -> None:

        class Msg(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            a: Annotated[str, CBORField(index=0)]
            b: Annotated[str, CBORField(index=1, optional=True)] = "default"

        generator = CDDLGenerator()
        cddl = generator.generate(Msg)

        expected = """Msg = [
    a: tstr,
    ? b: tstr
]"""
        assert cddl == expected

    def test_array_with_field_tag(self) -> None:

        class Msg(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            name: Annotated[str, CBORField(index=0)]
            blob: Annotated[bytes, CBORField(index=1, tag=50001)]

        generator = CDDLGenerator()
        cddl = generator.generate(Msg)

        expected = """Msg = [
    name: tstr,
    blob: #6.50001(bstr)
]"""
        assert cddl == expected

    def test_array_with_override_name(self) -> None:

        class Msg(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            internal_name: Annotated[
                str,
                CBORField(index=0, override_name="public_name"),
            ]

        generator = CDDLGenerator()
        cddl = generator.generate(Msg)

        expected = """Msg = [
    public_name: tstr
]"""
        assert cddl == expected

    def test_nested_array_model_dependency(self) -> None:

        class Inner(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            x: Annotated[int, CBORField(index=0)]
            y: Annotated[int, CBORField(index=1)]

        class Outer(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            label: Annotated[str, CBORField(index=0)]
            point: Annotated[Inner, CBORField(index=1)]

        generator = CDDLGenerator()
        cddl = generator.generate(Outer)

        expected = """Inner = [
    x: int,
    y: int
]

Outer = [
    label: tstr,
    point: Inner
]"""
        assert cddl == expected

    def test_map_and_array_models_can_coexist(self) -> None:

        class ArrayModel(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            a: Annotated[str, CBORField(index=0)]

        class MapModel(CBORModel):
            value: Annotated[str, CBORField(key=0)]
            nested: Annotated[ArrayModel, CBORField(key=1)]

        gen = CDDLGenerator()
        map_cddl = gen.generate(MapModel)

        expected = """ArrayModel = [
    a: tstr
]

map_model_value = 0
map_model_nested = 1

MapModel = {
    map_model_value: tstr,
    map_model_nested: ArrayModel
}"""
        assert map_cddl == expected


class TestCDDLComputedFields:
    """Test CDDL generation includes computed fields."""

    def test_computed_field_included_in_map_cddl(self) -> None:

        class Model(CBORModel):
            name: Annotated[str, CBORField(key=0)]

            @computed_field
            @property
            def name_upper(self) -> Annotated[str, CBORField(key=1)]:
                return self.name.upper()

        generator = CDDLGenerator()
        cddl = generator.generate(Model)

        expected = """model_name = 0
model_name_upper = 1

Model = {
    model_name: tstr,
    model_name_upper: tstr
}"""
        assert cddl == expected

    def test_computed_field_included_in_array_cddl(self) -> None:
        class Model(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            name: Annotated[str, CBORField(index=0)]

            @computed_field
            @property
            def name_upper(self) -> Annotated[str, CBORField(index=1)]:
                return self.name.upper()

        generator = CDDLGenerator()
        cddl = generator.generate(Model)

        expected = """Model = [
    name: tstr,
    name_upper: tstr
]"""
        assert cddl == expected

    def test_computed_field_without_cbor_field_excluded_from_cddl(self) -> None:
        class Model(CBORModel):
            name: Annotated[str, CBORField(key=0)]

            @computed_field
            @property
            def name_upper(self) -> str:
                return self.name.upper()

        generator = CDDLGenerator()
        cddl = generator.generate(Model)

        expected = """model_name = 0

Model = {
    model_name: tstr
}"""
        assert cddl == expected

    def test_computed_field_dependency_collected(self) -> None:
        class Inner(CBORModel):
            value: Annotated[int, CBORField(key=0)]

        class Outer(CBORModel):
            name: Annotated[str, CBORField(key=0)]

            @computed_field
            @property
            def derived(self) -> Annotated[Inner, CBORField(key=1)]:
                return Inner(value=len(self.name))

        generator = CDDLGenerator()
        cddl = generator.generate(Outer)

        expected = """inner_value = 0

Inner = {
    inner_value: int
}

outer_name = 0
outer_derived = 1

Outer = {
    outer_name: tstr,
    outer_derived: Inner
}"""
        assert cddl == expected


class TestGenerateMultiple:
    """Test CDDLGenerator.generate with multiple root models."""

    def test_two_independent_models(self) -> None:
        class A(CBORModel):
            x: Annotated[str, CBORField(key=0)]

        class B(CBORModel):
            y: Annotated[int, CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate([A, B])

        expected = """a_x = 0

A = {
    a_x: tstr
}

b_y = 0

B = {
    b_y: int
}"""
        assert cddl == expected

    def test_shared_dependency_emitted_once(self) -> None:
        class Shared(CBORModel):
            value: Annotated[str, CBORField(key=0)]

        class Root1(CBORModel):
            a: Annotated[Shared, CBORField(key=0)]

        class Root2(CBORModel):
            b: Annotated[Shared, CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate([Root1, Root2])

        assert cddl.count("Shared =") == 1
        assert "Root1 =" in cddl
        assert "Root2 =" in cddl

    def test_generate_resets_between_calls(self) -> None:
        class M(CBORModel):
            x: Annotated[str, CBORField(key=0)]

        generator = CDDLGenerator()
        first = generator.generate([M])
        second = generator.generate([M])

        assert first == second

    def test_generate_non_cbor_model_raises(self) -> None:
        class NotCBOR(BaseModel):
            x: str

        generator = CDDLGenerator()
        with pytest.raises(TypeError, match="must be a subclass of CBORModel"):
            generator.generate([NotCBOR])  # type: ignore[invalid-argument-type]

    def test_generate_empty_list(self) -> None:
        generator = CDDLGenerator()
        assert generator.generate([]) == ""


class TestLiteralCDDL:
    """Test CDDL generation for Literal type annotations."""

    def test_literal_int(self) -> None:

        class Msg(CBORModel):
            type: Annotated[Literal[1], CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Msg)
        assert "msg_type: 1" in cddl

    def test_literal_str(self) -> None:

        class Msg(CBORModel):
            kind: Annotated[Literal["ping"], CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Msg)
        assert 'msg_kind: "ping"' in cddl

    def test_literal_bool(self) -> None:

        class Msg(CBORModel):
            flag: Annotated[Literal[True], CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Msg)
        assert "msg_flag: true" in cddl

    def test_literal_multi_value(self) -> None:

        class Msg(CBORModel):
            code: Annotated[Literal[1, 2, 3], CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Msg)
        assert "msg_code: 1 / 2 / 3" in cddl

    def test_literal_optional(self) -> None:

        class Msg(CBORModel):
            code: Annotated[Literal[7] | None, CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Msg)
        assert "? msg_code: 7" in cddl

    def test_literal_unsupported_type_raises(self) -> None:

        class Msg(CBORModel):
            val: Annotated[Literal[b"x"], CBORField(key=0)]  # type: ignore[valid-type]

        generator = CDDLGenerator()
        with pytest.raises(TypeError, match="Unsupported Literal value type"):
            generator.generate(Msg)


class TestBstrWrapCDDL:
    """Test CDDL generation for bstr_wrap fields."""

    def test_bstr_wrap_simple_type(self) -> None:
        class Wrapper(CBORModel):
            payload: Annotated[dict[str, int], CBORField(key=0, bstr_wrap=True)]

        generator = CDDLGenerator()
        cddl = generator.generate(Wrapper)
        assert "bstr .cbor" in cddl

    def test_bstr_wrap_nested_model(self) -> None:
        class Inner(CBORModel):
            x: Annotated[int, CBORField(key=0)]

        class Outer(CBORModel):
            inner: Annotated[Inner, CBORField(key=0, bstr_wrap=True)]

        generator = CDDLGenerator()
        cddl = generator.generate(Outer)
        assert "outer_inner: bstr .cbor Inner" in cddl

    def test_bstr_wrap_with_tag(self) -> None:
        class Wrapper(CBORModel):
            payload: Annotated[int, CBORField(key=0, bstr_wrap=True, tag=1001)]

        generator = CDDLGenerator()
        cddl = generator.generate(Wrapper)
        assert "wrapper_payload: #6.1001(bstr .cbor int)" in cddl

    def test_bstr_wrap_override_type_skips_cbor_annotation(self) -> None:
        class Wrapper(CBORModel):
            payload: Annotated[
                int,
                CBORField(key=0, bstr_wrap=True, override_type="my-type"),
            ]

        generator = CDDLGenerator()
        cddl = generator.generate(Wrapper)
        assert "my-type" in cddl
        assert "bstr .cbor" not in cddl


class TestCDDLNamedKeysAlwaysOn:
    """Test that map-encoded models always emit a named-key constant block."""

    def test_basic_named_keys_block(self) -> None:
        """Map model emits a snake_cased definitions block by default."""

        class Person(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            age: Annotated[int, CBORField(key=1)]

        generator = CDDLGenerator()
        cddl = generator.generate(Person)

        expected = """person_name = 0
person_age = 1

Person = {
    person_name: tstr,
    person_age: int
}"""
        assert cddl == expected

    def test_nested_both_emit_blocks(self) -> None:
        """Each map-encoded model gets its own prefixed block."""

        class Inner(CBORModel):
            x: Annotated[int, CBORField(key=0)]
            y: Annotated[int, CBORField(key=1)]

        class Outer(CBORModel):
            label: Annotated[str, CBORField(key=0)]
            point: Annotated[Inner, CBORField(key=1)]

        generator = CDDLGenerator()
        cddl = generator.generate(Outer)

        expected = """inner_x = 0
inner_y = 1

Inner = {
    inner_x: int,
    inner_y: int
}

outer_label = 0
outer_point = 1

Outer = {
    outer_label: tstr,
    outer_point: Inner
}"""
        assert cddl == expected

    def test_optional_field_named_key(self) -> None:
        """Optional fields render with ``? `` before the named key."""

        class Msg(CBORModel):
            required: Annotated[str, CBORField(key=0)]
            maybe: Annotated[str | None, CBORField(key=1)] = None

        generator = CDDLGenerator()
        cddl = generator.generate(Msg)

        expected = """msg_required = 0
msg_maybe = 1

Msg = {
    msg_required: tstr,
    ? msg_maybe: tstr
}"""
        assert cddl == expected

    def test_tag_and_bstr_wrap_modifiers(self) -> None:
        """Type modifiers (tag, bstr_wrap) still apply to the right-hand side."""

        class Inner(CBORModel):
            v: Annotated[int, CBORField(key=0)]

        class Wrapper(CBORModel):
            tagged: Annotated[bytes, CBORField(key=0, tag=24)]
            wrapped: Annotated[Inner, CBORField(key=1, bstr_wrap=True)]
            tagged_wrapped: Annotated[
                int,
                CBORField(key=2, bstr_wrap=True, tag=1001),
            ]

        generator = CDDLGenerator()
        cddl = generator.generate(Wrapper)

        expected = """inner_v = 0

Inner = {
    inner_v: int
}

wrapper_tagged = 0
wrapper_wrapped = 1
wrapper_tagged_wrapped = 2

Wrapper = {
    wrapper_tagged: #6.24(bstr),
    wrapper_wrapped: bstr .cbor Inner,
    wrapper_tagged_wrapped: #6.1001(bstr .cbor int)
}"""
        assert cddl == expected

    def test_string_keys_stay_inlined(self) -> None:
        """String keys are not indirected through a definitions block."""

        class StrOnly(CBORModel):
            alpha: Annotated[str, CBORField(key="a")]
            beta: Annotated[int, CBORField(key="b")]

        generator = CDDLGenerator()
        cddl = generator.generate(StrOnly)

        expected = """StrOnly = {
    a: tstr,
    b: int
}"""
        assert cddl == expected

    def test_array_encoding_unchanged(self) -> None:
        """Array-encoded models do not produce a constant block."""

        class Point(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            x: Annotated[float, CBORField(index=0)]
            y: Annotated[float, CBORField(index=1)]

        generator = CDDLGenerator()
        cddl = generator.generate(Point)

        expected = """Point = [
    x: float,
    y: float
]"""
        assert cddl == expected

    def test_override_name_kept_verbatim(self) -> None:
        """``override_name`` is used verbatim (no snake conversion)."""

        class Product(CBORModel):
            internal_id: Annotated[
                str,
                CBORField(key=0, override_name="ProductID"),
            ]

        generator = CDDLGenerator()
        cddl = generator.generate(Product)

        expected = """product_ProductID = 0

Product = {
    product_ProductID: tstr
}"""
        assert cddl == expected

    def test_pascal_class_name_snake_cased_in_helper(self) -> None:
        """The model class name is snake_cased only as the helper prefix."""

        class HTTPResponse(CBORModel):
            status_code: Annotated[int, CBORField(key=0)]
            body: Annotated[str, CBORField(key=1)]

        generator = CDDLGenerator()
        cddl = generator.generate(HTTPResponse)

        expected = """http_response_status_code = 0
http_response_body = 1

HTTPResponse = {
    http_response_status_code: int,
    http_response_body: tstr
}"""
        assert cddl == expected


class TestCDDLDescription:
    """Test ``CBORField.description`` rendering."""

    def test_description_emits_semicolon_in_map(self) -> None:
        """A description appears as ``; <text>`` after a map field."""

        class Person(CBORModel):
            name: Annotated[str, CBORField(key=0, description="full name")]
            age: Annotated[int, CBORField(key=1)]

        generator = CDDLGenerator()
        cddl = generator.generate(Person)

        expected = """person_name = 0
person_age = 1

Person = {
    person_name: tstr,  ; full name
    person_age: int
}"""
        assert cddl == expected

    def test_description_in_last_field(self) -> None:
        """A description on the last field of a map does not include leading comma."""

        class Person(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            age: Annotated[int, CBORField(key=1, description="age in years")]

        generator = CDDLGenerator()
        cddl = generator.generate(Person)

        expected = """person_name = 0
person_age = 1

Person = {
    person_name: tstr,
    person_age: int  ; age in years
}"""
        assert cddl == expected

    def test_description_emits_semicolon_in_array(self) -> None:
        """A description appears as ``; <text>`` after an array field."""

        class Point(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            x: Annotated[float, CBORField(index=0, description="x coordinate")]
            y: Annotated[float, CBORField(index=1)]

        generator = CDDLGenerator()
        cddl = generator.generate(Point)

        expected = """Point = [
    x: float,  ; x coordinate
    y: float
]"""
        assert cddl == expected

    def test_no_description_means_no_semicolon(self) -> None:
        """Fields without ``description`` produce no trailing comment."""

        class Person(CBORModel):
            name: Annotated[str, CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Person)

        assert ";" not in cddl

    def test_description_on_string_keyed_map(self) -> None:
        """Descriptions also apply to string-keyed map fields."""

        class Cfg(CBORModel):
            alpha: Annotated[str, CBORField(key="a", description="the alpha value")]

        generator = CDDLGenerator()
        cddl = generator.generate(Cfg)

        expected = """Cfg = {
    a: tstr  ; the alpha value
}"""
        assert cddl == expected
