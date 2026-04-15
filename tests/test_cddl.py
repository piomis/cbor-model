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

        expected = """Person = {
    0: tstr,  ; name,
    1: uint,  ; age
}"""
        assert cddl == expected

    def test_optional_fields(self) -> None:
        """Test CDDL generation with optional fields."""

        class Contact(CBORModel):
            email: Annotated[str, CBORField(key=0)]
            phone: Annotated[str | None, CBORField(key=1)]

        generator = CDDLGenerator()
        cddl = generator.generate(Contact)

        expected = """Contact = {
    0: tstr,  ; email,
    ? 1: tstr,  ; phone
}"""
        assert cddl == expected

    def test_list_fields(self) -> None:
        """Test CDDL generation with list fields."""

        class Team(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            members: Annotated[list[str], CBORField(key=1)]

        generator = CDDLGenerator()
        cddl = generator.generate(Team)

        expected = """Team = {
    0: tstr,  ; name,
    1: [* tstr],  ; members
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

        expected = f"""Team = {{
    0: tstr,  ; name,
    1: {expected_type},  ; members
}}"""
        assert cddl == expected

    @pytest.mark.parametrize(
        ("min_length", "max_length", "expected_type"),
        [
            (None, None, "tstr"),
            (5, None, "tstr .size 5.."),
            (None, 10, "tstr .size ..10"),
            (1, 50, "tstr .size (1..50)"),
        ],
        ids=[
            "no_constraints",
            "min_length_only",
            "max_length_only",
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

        expected = f"""Person = {{
    0: {expected_type},  ; name
}}"""
        assert cddl == expected

    @pytest.mark.parametrize(
        ("min_length", "max_length", "expected_type"),
        [
            (None, None, "bstr"),
            (5, None, "bstr .size 5.."),
            (None, 10, "bstr .size ..10"),
            (1, 50, "bstr .size (1..50)"),
            (32, 32, "bstr .size 32"),
        ],
        ids=[
            "no_constraints",
            "min_length_only",
            "max_length_only",
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

        expected = f"""Packet = {{
    0: {expected_type},  ; data
}}"""
        assert cddl == expected

    @pytest.mark.parametrize(
        ("min_length", "max_length", "expected_type"),
        [
            (None, None, "tstr"),
            (5, None, "tstr .size 5.."),
            (None, 10, "tstr .size ..10"),
            (1, 50, "tstr .size (1..50)"),
        ],
        ids=[
            "no_constraints",
            "min_length_only",
            "max_length_only",
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

        expected = f"""Person = {{
    ? 0: {expected_type},  ; name
}}"""
        assert cddl == expected

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

        expected = """Address = {
    0: tstr,  ; street,
    1: tstr,  ; city
}

Company = {
    0: tstr,  ; name,
    1: Address,  ; address
}"""
        assert cddl == expected

    def test_recursive_model(self) -> None:
        """Test CDDL generation with recursive type."""

        class Node(CBORModel):
            value: Annotated[int, CBORField(key=0)]
            children: Annotated[list["Node"] | None, CBORField(key=1)]

        generator = CDDLGenerator()
        cddl = generator.generate(Node)

        expected = """Node = {
    0: int,  ; value,
    ? 1: [* Node],  ; children
}"""
        assert cddl == expected

    def test_override_name(self) -> None:
        """Test CDDL generation with override_name."""

        class Product(CBORModel):
            internal_id: Annotated[
                str,
                CBORField(key=0, override_name="product_id"),
            ]

        generator = CDDLGenerator()
        cddl = generator.generate(Product)

        expected = """Product = {
    0: tstr,  ; product_id
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

        expected = """Config = {
    0: bstr .size 32,  ; data
}"""
        assert cddl == expected

    def test_cbor_tag(self) -> None:
        """Test CDDL generation with CBOR tag."""

        class Tagged(CBORModel):
            value: Annotated[str, CBORField(key=0, tag=123)]

        generator = CDDLGenerator()
        cddl = generator.generate(Tagged)

        expected = """Tagged = {
    0: #6.123(tstr),  ; value
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

        expected = """Types = {
    0: tstr,  ; text,
    1: bstr,  ; data,
    2: int,  ; count,
    3: bool,  ; flag,
    4: float,  ; ratio
}"""
        assert cddl == expected

    def test_uint_constraint(self) -> None:
        """Test that int with ge=0 or gt=0 becomes uint."""

        class Numbers(CBORModel):
            positive_gt: Annotated[int, CBORField(key=0), Field(gt=0)]
            positive_ge: Annotated[int, CBORField(key=1), Field(ge=0)]
            any_int: Annotated[int, CBORField(key=2)]

        generator = CDDLGenerator()
        cddl = generator.generate(Numbers)

        expected = """Numbers = {
    0: uint,  ; positive_gt,
    1: uint,  ; positive_ge,
    2: int,  ; any_int
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

        expected = """Example = {
    0: tstr,  ; required_with_default,
    ? 1: [* tstr],  ; explicit_optional
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

Palette = {
    0: Color,  ; primary,
    ? 1: Color,  ; secondary
}"""
        assert cddl == expected

    def test_dict_field(self) -> None:
        """Test CDDL generation for dict fields."""

        class Config(CBORModel):
            metadata: Annotated[dict[str, str], CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Config)

        expected = """Config = {
    0: {* tstr => tstr},  ; metadata
}"""
        assert cddl == expected

    def test_dict_field_any_value(self) -> None:
        """Test CDDL for dict with heterogeneous values."""

        class Config(CBORModel):
            data: Annotated[dict[str, Any], CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Config)

        expected = """Config = {
    0: {* tstr => any},  ; data
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

        expected = """Numbers = {
    0: uint,  ; positive_gt,
    1: uint,  ; positive_ge,
    2: int,  ; any_int,
    3: nint,  ; negative_lt,
    4: nint,  ; negative_le,
    5: int -10..10,  ; custom
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

MapModel = {
    0: tstr,  ; value,
    1: ArrayModel,  ; nested
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

        expected = """Model = {
    0: tstr,  ; name,
    1: tstr,  ; name_upper
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

        expected = """Model = {
    0: tstr,  ; name
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

        expected = """Inner = {
    0: int,  ; value
}

Outer = {
    0: tstr,  ; name,
    1: Inner,  ; derived
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

        expected = """A = {
    0: tstr,  ; x
}

B = {
    0: int,  ; y
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
        assert "0: 1," in cddl

    def test_literal_str(self) -> None:

        class Msg(CBORModel):
            kind: Annotated[Literal["ping"], CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Msg)
        assert '0: "ping",' in cddl

    def test_literal_bool(self) -> None:

        class Msg(CBORModel):
            flag: Annotated[Literal[True], CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Msg)
        assert "0: true," in cddl

    def test_literal_multi_value(self) -> None:

        class Msg(CBORModel):
            code: Annotated[Literal[1, 2, 3], CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Msg)
        assert "0: 1 / 2 / 3," in cddl

    def test_literal_optional(self) -> None:

        class Msg(CBORModel):
            code: Annotated[Literal[7] | None, CBORField(key=0)]

        generator = CDDLGenerator()
        cddl = generator.generate(Msg)
        assert "? 0: 7," in cddl

    def test_literal_unsupported_type_raises(self) -> None:

        class Msg(CBORModel):
            val: Annotated[Literal[b"x"], CBORField(key=0)]  # type: ignore[valid-type]

        generator = CDDLGenerator()
        with pytest.raises(TypeError, match="Unsupported Literal value type"):
            generator.generate(Msg)
