# ruff: noqa: PLR2004

from typing import Annotated, Any

import cbor2
import pytest
from pydantic import ConfigDict, HttpUrl, PrivateAttr, computed_field
from pydantic.alias_generators import to_camel

from cbor_model import CBORField, CBORModel, CBORSerializationContext
from cbor_model._config import CBORConfig


class TestCustomTags:
    def test_custom_tag_application(self) -> None:

        class TestModel(CBORModel):
            plain_str: Annotated[str, CBORField(key=0)]
            tagged_str: Annotated[str, CBORField(key=1, tag=999)]
            plain_int: Annotated[int, CBORField(key=2)]
            tagged_int: Annotated[int, CBORField(key=3, tag=888)]

        obj = TestModel(
            plain_str="hello",
            tagged_str="world",
            plain_int=42,
            tagged_int=99,
        )

        data_dict: dict[int, Any] = obj.model_dump(
            context=CBORSerializationContext(),
        )

        assert sorted(data_dict.keys()) == [0, 1, 2, 3]
        assert isinstance(data_dict[1], cbor2.CBORTag)
        assert data_dict[1].tag == 999
        assert data_dict[1].value == "world"
        assert isinstance(data_dict[3], cbor2.CBORTag)
        assert data_dict[3].tag == 888
        assert data_dict[3].value == 99
        assert not isinstance(data_dict[0], cbor2.CBORTag)
        assert not isinstance(data_dict[2], cbor2.CBORTag)

        cbor_bytes = obj.model_dump_cbor()
        decoded = cbor2.loads(cbor_bytes)

        assert isinstance(decoded[1], cbor2.CBORTag)
        assert decoded[1].tag == 999
        assert isinstance(decoded[3], cbor2.CBORTag)
        assert decoded[3].tag == 888

        restored = TestModel.model_validate_cbor(cbor_bytes)

        assert restored.plain_str == "hello"
        assert restored.tagged_str == "world"
        assert restored.plain_int == 42
        assert restored.tagged_int == 99

    def test_nested_model_tags(self) -> None:

        class Inner(CBORModel):
            value: Annotated[str, CBORField(key=0, tag=50000)]

        class Outer(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            inner: Annotated[Inner, CBORField(key=1)]
            tagged_inner: Annotated[Inner, CBORField(key=2, tag=50001)]

        obj = Outer(
            name="outer",
            inner=Inner(value="inner1"),
            tagged_inner=Inner(value="inner2"),
        )

        data_dict: dict[int, Any] = obj.model_dump(
            context=CBORSerializationContext(),
        )

        assert sorted(data_dict.keys()) == [0, 1, 2]
        assert isinstance(data_dict[1], dict)
        assert isinstance(data_dict[1][0], cbor2.CBORTag)
        assert data_dict[1][0].tag == 50000
        assert isinstance(data_dict[2], cbor2.CBORTag)
        assert data_dict[2].tag == 50001
        assert isinstance(data_dict[2].value, dict)
        assert isinstance(data_dict[2].value[0], cbor2.CBORTag)
        assert data_dict[2].value[0].tag == 50000

        cbor_bytes = obj.model_dump_cbor()
        restored = Outer.model_validate_cbor(cbor_bytes)

        assert restored.name == "outer"
        assert restored.inner.value == "inner1"
        assert restored.tagged_inner.value == "inner2"

        decoded = cbor2.loads(cbor_bytes)

        assert isinstance(decoded, dict)
        assert sorted(decoded.keys()) == [0, 1, 2]
        assert isinstance(decoded[1], dict)
        assert isinstance(decoded[1][0], cbor2.CBORTag)
        assert decoded[1][0].tag == 50000
        assert isinstance(decoded[2], cbor2.CBORTag)
        assert decoded[2].tag == 50001


class TestCBORFieldValidation:
    def test_reserved_tag_validation(self) -> None:
        with pytest.raises(
            ValueError,
            match=r"CBOR tag 37 conflicts with cbor2 reserved tags",
        ):
            CBORField(key=0, tag=37)

        with pytest.raises(
            ValueError,
            match=r"CBOR tag 1 conflicts with cbor2 reserved tags",
        ):
            CBORField(key=0, tag=1)

        with pytest.raises(
            ValueError,
            match=r"CBOR tag 100 conflicts with cbor2 reserved tags",
        ):
            CBORField(key=0, tag=100)

    def test_unreserved_tags_allowed(self) -> None:
        field = CBORField(key=0, tag=1000)
        assert field.tag == 1000

        field = CBORField(key=0, tag=50000)
        assert field.tag == 50000

        field = CBORField(key=0, tag=999)
        assert field.tag == 999

    def test_negative_tag_rejected_on_cbor_field(self) -> None:
        with pytest.raises(ValueError, match="Tags must be non-negative"):
            CBORField(key=0, tag=-1)

        with pytest.raises(ValueError, match="Tags must be non-negative"):
            CBORField(key=0, tag=-100)

    def test_negative_tag_rejected_on_cbor_config(self) -> None:
        with pytest.raises(ValueError, match="Tags must be non-negative"):
            CBORConfig(tag=-1)


class TestTag24Nesting:
    def test_tag24_nested_cbor(self) -> None:

        class Container(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            nested_cbor: Annotated[bytes, CBORField(key=1, tag=24)]

        inner_data = {"message": "hello", "count": 123}
        inner_cbor = cbor2.dumps(inner_data)

        container = Container(name="wrapper", nested_cbor=inner_cbor)

        cbor_bytes = container.model_dump_cbor()
        data_dict: dict[int, Any] = container.model_dump(
            context=CBORSerializationContext(),
        )

        assert isinstance(data_dict[1], cbor2.CBORTag)
        assert data_dict[1].tag == 24
        assert isinstance(data_dict[1].value, bytes)

        restored = Container.model_validate_cbor(cbor_bytes)

        assert restored.name == "wrapper"
        assert restored.nested_cbor == inner_cbor

        decoded_inner = cbor2.loads(restored.nested_cbor)
        assert decoded_inner == inner_data
        assert decoded_inner["message"] == "hello"
        assert decoded_inner["count"] == 123

    def test_tag24_with_nested_model(self) -> None:

        class InnerModel(CBORModel):
            value: Annotated[str, CBORField(key=0)]
            number: Annotated[int, CBORField(key=1)]

        class OuterModel(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            embedded: Annotated[bytes, CBORField(key=1, tag=24)]

        inner = InnerModel(value="test", number=42)
        inner_cbor = inner.model_dump_cbor()

        outer = OuterModel(name="container", embedded=inner_cbor)

        cbor_bytes = outer.model_dump_cbor()
        restored = OuterModel.model_validate_cbor(cbor_bytes)

        assert restored.name == "container"
        assert restored.embedded == inner_cbor

        restored_inner = InnerModel.model_validate_cbor(restored.embedded)
        assert restored_inner.value == "test"
        assert restored_inner.number == 42

    def test_tag24_raw_structure(self) -> None:

        class TestModel(CBORModel):
            data: Annotated[bytes, CBORField(key=0, tag=24)]

        inner_cbor = cbor2.dumps({"nested": "value"})
        obj = TestModel(data=inner_cbor)

        cbor_bytes = obj.model_dump_cbor()
        decoded = cbor2.loads(cbor_bytes)

        assert isinstance(decoded, dict)
        assert 0 in decoded
        assert isinstance(decoded[0], cbor2.CBORTag)
        assert decoded[0].tag == 24
        assert isinstance(decoded[0].value, bytes)

        nested = cbor2.loads(decoded[0].value)
        assert nested == {"nested": "value"}


class TestModelLevelTag:
    def test_model_tag_wraps_output(self) -> None:

        class Tagged(CBORModel):
            cbor_config = CBORConfig(tag=50100)
            value: Annotated[str, CBORField(key=0)]

        obj = Tagged(value="hello")
        cbor_bytes = obj.model_dump_cbor()
        decoded = cbor2.loads(cbor_bytes)

        assert isinstance(decoded, cbor2.CBORTag)
        assert decoded.tag == 50100
        assert decoded.value == {0: "hello"}

    def test_model_tag_roundtrip(self) -> None:

        class Tagged(CBORModel):
            cbor_config = CBORConfig(tag=50100)
            value: Annotated[str, CBORField(key=0)]
            count: Annotated[int, CBORField(key=1)]

        obj = Tagged(value="test", count=42)
        cbor_bytes = obj.model_dump_cbor()
        restored = Tagged.model_validate_cbor(cbor_bytes)

        assert restored.value == "test"
        assert restored.count == 42

    def test_model_tag_wrong_tag_raises(self) -> None:

        class Tagged(CBORModel):
            cbor_config = CBORConfig(tag=50100)
            value: Annotated[str, CBORField(key=0)]

        wrong_tag_bytes = cbor2.dumps(cbor2.CBORTag(99999, {0: "hello"}))

        with pytest.raises(ValueError, match="Expected CBOR tag 50100"):
            Tagged.model_validate_cbor(wrong_tag_bytes)

    def test_model_tag_missing_tag_raises(self) -> None:

        class Tagged(CBORModel):
            cbor_config = CBORConfig(tag=50100)
            value: Annotated[str, CBORField(key=0)]

        untagged_bytes = cbor2.dumps({0: "hello"})

        with pytest.raises(ValueError, match="Expected CBOR tag 50100"):
            Tagged.model_validate_cbor(untagged_bytes)


class TestSerializationContext:
    def test_model_dump_cbor_ignores_json_aliases(self) -> None:

        class AliasModel(CBORModel):
            model_config = ConfigDict(
                populate_by_name=True,
                alias_generator=to_camel,
                serialize_by_alias=True,
            )

            serial_number: Annotated[str, CBORField(key=2)]
            model_identifier: Annotated[str, CBORField(key=3)]

        obj = AliasModel(
            serial_number="123456789",
            model_identifier="COMPUTRONIUM-2000",
        )

        decoded = cbor2.loads(obj.model_dump_cbor())

        assert decoded == {
            2: "123456789",
            3: "COMPUTRONIUM-2000",
        }

    def test_exclude_none_false_preserves_none_fields(self) -> None:

        class Opt(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            maybe: Annotated[str | None, CBORField(key=1)] = None

        obj = Opt(name="x")
        data: dict[int, Any] = obj.model_dump(
            context=CBORSerializationContext(exclude_none=False),
        )

        assert 1 in data
        assert data[1] is None

    def test_exclude_none_true_omits_none_fields(self) -> None:

        class Opt(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            maybe: Annotated[str | None, CBORField(key=1)] = None

        obj = Opt(name="x")
        data: dict[int, Any] = obj.model_dump(
            context=CBORSerializationContext(exclude_none=True),
        )

        assert 1 not in data

    def test_exclude_empty_true_omits_empty_lists(self) -> None:

        class Model(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            tags: Annotated[list[str], CBORField(key=1)]

        obj = Model(name="x", tags=[])
        data: dict[int, Any] = obj.model_dump(
            context=CBORSerializationContext(exclude_empty=True),
        )

        assert 1 not in data

    def test_exclude_empty_false_preserves_empty_lists(self) -> None:

        class Model(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            tags: Annotated[list[str], CBORField(key=1)]

        obj = Model(name="x", tags=[])
        data: dict[int, Any] = obj.model_dump(
            context=CBORSerializationContext(exclude_empty=False),
        )

        assert 1 in data
        assert data[1] == []

    def test_exclude_if_callable(self) -> None:

        class Model(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            score: Annotated[
                int,
                CBORField(key=1, exclude_if=lambda v: v < 0),
            ]

        positive = Model(name="a", score=10)
        negative = Model(name="b", score=-1)

        positive_data: dict[int, Any] = positive.model_dump(
            context=CBORSerializationContext(),
        )
        negative_data: dict[int, Any] = negative.model_dump(
            context=CBORSerializationContext(),
        )

        assert 1 in positive_data
        assert positive_data[1] == 10
        assert 1 not in negative_data


class TestCustomEncoders:
    def test_custom_encoder_for_http_url(self) -> None:

        class Model(CBORModel):
            cbor_config = CBORConfig(encoders={HttpUrl: str})
            url: Annotated[HttpUrl, CBORField(key=0)]

        obj = Model(url=HttpUrl("https://example.com"))
        cbor_bytes = obj.model_dump_cbor()
        decoded = cbor2.loads(cbor_bytes)

        assert isinstance(decoded[0], str)
        assert "example.com" in decoded[0]

    def test_missing_encoder_raises(self) -> None:

        class Model(CBORModel):
            url: Annotated[HttpUrl, CBORField(key=0)]

        obj = Model(url=HttpUrl("https://example.com"))

        with pytest.raises(TypeError, match="No encoder registered"):
            obj.model_dump_cbor()

    def test_nested_model_encoder_used_by_outer(self) -> None:
        """Encoder declared on a nested model is inherited when serializing from outer."""

        class Inner(CBORModel):
            cbor_config = CBORConfig(encoders={HttpUrl: str})
            url: Annotated[HttpUrl, CBORField(key=0)]

        class Outer(CBORModel):
            name: Annotated[str, CBORField(key=0)]
            inner: Annotated[Inner, CBORField(key=1)]

        obj = Outer(name="test", inner=Inner(url=HttpUrl("https://example.com")))
        decoded = cbor2.loads(obj.model_dump_cbor())

        assert isinstance(decoded[1][0], str)
        assert "example.com" in decoded[1][0]

    def test_outer_encoder_overrides_nested(self) -> None:
        """Encoder on the outer (root) model takes priority over nested model encoders."""

        class Inner(CBORModel):
            cbor_config = CBORConfig(encoders={HttpUrl: lambda u: f"inner:{u}"})
            url: Annotated[HttpUrl, CBORField(key=0)]

        class Outer(CBORModel):
            cbor_config = CBORConfig(encoders={HttpUrl: lambda u: f"outer:{u}"})
            inner: Annotated[Inner, CBORField(key=0)]

        obj = Outer(inner=Inner(url=HttpUrl("https://example.com")))
        decoded = cbor2.loads(obj.model_dump_cbor())

        assert decoded[0][0].startswith("outer:")

    def test_encoder_missing_on_outer_raises(self) -> None:
        """No encoder on any model in the hierarchy raises TypeError."""

        class Inner(CBORModel):
            url: Annotated[HttpUrl, CBORField(key=0)]

        class Outer(CBORModel):
            inner: Annotated[Inner, CBORField(key=0)]

        obj = Outer(inner=Inner(url=HttpUrl("https://example.com")))
        with pytest.raises(TypeError, match="No encoder registered"):
            obj.model_dump_cbor()


class TestInheritance:
    def test_subclass_includes_parent_fields(self) -> None:

        class Base(CBORModel):
            id: Annotated[str, CBORField(key=0)]

        class Child(Base):
            name: Annotated[str, CBORField(key=1)]

        obj = Child(id="abc", name="Alice")
        cbor_bytes = obj.model_dump_cbor()
        decoded = cbor2.loads(cbor_bytes)

        assert decoded == {0: "abc", 1: "Alice"}

        restored = Child.model_validate_cbor(cbor_bytes)
        assert restored.id == "abc"
        assert restored.name == "Alice"

    def test_subclass_mapping_does_not_contaminate_parent(self) -> None:

        class Base(CBORModel):
            id: Annotated[str, CBORField(key=0)]

        class Child(Base):
            name: Annotated[str, CBORField(key=1)]

        _ = Child(id="x", name="y").model_dump_cbor()
        base_obj = Base(id="z")
        cbor_bytes = base_obj.model_dump_cbor()
        decoded = cbor2.loads(cbor_bytes)

        assert decoded == {0: "z"}
        assert 1 not in decoded


class TestCanonicalEncoding:
    def test_canonical_flag_produces_deterministic_output(self) -> None:

        class Model(CBORModel):
            cbor_config = CBORConfig(canonical=True)
            b: Annotated[str, CBORField(key=1)]
            a: Annotated[str, CBORField(key=0)]

        obj = Model(b="second", a="first")
        cbor1 = obj.model_dump_cbor()
        cbor2_ = obj.model_dump_cbor()

        assert cbor1 == cbor2_

        decoded = cbor2.loads(cbor1)
        assert decoded[0] == "first"
        assert decoded[1] == "second"


class TestArrayEncoding:
    def test_basic_array_roundtrip(self) -> None:

        class Point(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            x: Annotated[float, CBORField(index=0)]
            y: Annotated[float, CBORField(index=1)]
            z: Annotated[float, CBORField(index=2)]

        obj = Point(x=1.0, y=2.0, z=3.0)
        cbor_bytes = obj.model_dump_cbor()
        decoded = cbor2.loads(cbor_bytes)

        assert isinstance(decoded, list)
        assert decoded == [1.0, 2.0, 3.0]

        restored = Point.model_validate_cbor(cbor_bytes)
        assert restored.x == 1.0
        assert restored.y == 2.0
        assert restored.z == 3.0

    def test_array_serialization_context_produces_list(self) -> None:

        class Model(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            a: Annotated[str, CBORField(index=0)]
            b: Annotated[int, CBORField(index=1)]

        obj = Model(a="hello", b=42)
        result = obj.model_dump(context=CBORSerializationContext())

        assert isinstance(result, list)
        assert result == ["hello", 42]

    def test_optional_tail_omitted_when_none(self) -> None:

        class Msg(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            required: Annotated[str, CBORField(index=0)]
            optional: Annotated[str | None, CBORField(index=1)] = None

        obj_with = Msg(required="hello", optional="world")
        obj_without = Msg(required="hello")

        data_with: list[Any] = obj_with.model_dump(
            context=CBORSerializationContext(exclude_none=True),
        )
        data_without: list[Any] = obj_without.model_dump(
            context=CBORSerializationContext(exclude_none=True),
        )

        assert data_with == ["hello", "world"]
        assert data_without == ["hello"]

    def test_optional_tail_included_when_exclude_none_false(self) -> None:

        class Msg(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            required: Annotated[str, CBORField(index=0)]
            optional: Annotated[str | None, CBORField(index=1)] = None

        obj = Msg(required="hello")
        data: list[Any] = obj.model_dump(
            context=CBORSerializationContext(exclude_none=False),
        )

        assert data == ["hello", None]

    def test_short_array_deserialization_fills_optional_with_defaults(
        self,
    ) -> None:

        class Msg(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            required: Annotated[str, CBORField(index=0)]
            opt_a: Annotated[str | None, CBORField(index=1)] = None
            opt_b: Annotated[int | None, CBORField(index=2)] = None

        short_array = cbor2.dumps(["hello"])
        restored = Msg.model_validate_cbor(short_array)

        assert restored.required == "hello"
        assert restored.opt_a is None
        assert restored.opt_b is None

    def test_full_array_deserialization(self) -> None:

        class Msg(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            required: Annotated[str, CBORField(index=0)]
            opt_a: Annotated[str | None, CBORField(index=1)] = None
            opt_b: Annotated[int | None, CBORField(index=2)] = None

        full_array = cbor2.dumps(["hello", "world", 99])
        restored = Msg.model_validate_cbor(full_array)

        assert restored.required == "hello"
        assert restored.opt_a == "world"
        assert restored.opt_b == 99

    def test_multiple_optional_tail_fields(self) -> None:

        class Msg(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            a: Annotated[str, CBORField(index=0)]
            b: Annotated[str, CBORField(index=1)]
            c: Annotated[str | None, CBORField(index=2)] = None
            d: Annotated[str | None, CBORField(index=3)] = None

        obj_full = Msg(a="a", b="b", c="c", d="d")
        obj_c_only = Msg(a="a", b="b", c="c")
        obj_none = Msg(a="a", b="b")

        assert obj_full.model_dump(context=CBORSerializationContext()) == [
            "a",
            "b",
            "c",
            "d",
        ]
        assert obj_c_only.model_dump(context=CBORSerializationContext()) == [
            "a",
            "b",
            "c",
        ]
        assert obj_none.model_dump(context=CBORSerializationContext()) == [
            "a",
            "b",
        ]

    def test_array_with_field_level_tag(self) -> None:

        class Msg(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            name: Annotated[str, CBORField(index=0)]
            blob: Annotated[bytes, CBORField(index=1, tag=50001)]

        obj = Msg(name="test", blob=b"\x01\x02")
        cbor_bytes = obj.model_dump_cbor()
        decoded = cbor2.loads(cbor_bytes)

        assert isinstance(decoded, list)
        assert decoded[0] == "test"
        assert isinstance(decoded[1], cbor2.CBORTag)
        assert decoded[1].tag == 50001
        assert decoded[1].value == b"\x01\x02"

        restored = Msg.model_validate_cbor(cbor_bytes)
        assert restored.name == "test"
        assert restored.blob == b"\x01\x02"

    def test_array_with_model_level_tag(self) -> None:

        class Record(CBORModel):
            cbor_config = CBORConfig(encoding="array", tag=50200)
            a: Annotated[str, CBORField(index=0)]
            b: Annotated[int, CBORField(index=1)]

        obj = Record(a="hello", b=42)
        cbor_bytes = obj.model_dump_cbor()
        decoded = cbor2.loads(cbor_bytes)

        assert isinstance(decoded, cbor2.CBORTag)
        assert decoded.tag == 50200
        assert decoded.value == ["hello", 42]

        restored = Record.model_validate_cbor(cbor_bytes)
        assert restored.a == "hello"
        assert restored.b == 42

    def test_invalid_gap_in_indices_raises(self) -> None:
        class BadModel(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            a: Annotated[str, CBORField(index=0)]
            c: Annotated[str, CBORField(index=2)]

        b = BadModel(a="x", c="y")

        with pytest.raises(ValueError, match="Index 1 is missing"):
            b.model_dump_cbor()

    def test_invalid_optional_before_required_raises(self) -> None:

        class BadModel(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            a: Annotated[str, CBORField(index=0)]
            b: Annotated[str | None, CBORField(index=1)] = None
            c: Annotated[str, CBORField(index=2)]

        b = BadModel(a="x", c="y")

        with pytest.raises(
            ValueError,
            match=r"Non-optional field .+ cannot appear after",
        ):
            b.model_dump_cbor()

    def test_invalid_duplicate_index_raises(self) -> None:
        class BadModel(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            a: Annotated[str, CBORField(index=0)]
            b: Annotated[str, CBORField(index=0)]

        b = BadModel(a="x", b="y")
        with pytest.raises(ValueError, match="Duplicate CBORField index"):
            b.model_dump_cbor()

    def test_invalid_key_in_array_model_raises(self) -> None:
        class BadModel(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            a: Annotated[str, CBORField(key=0)]

        b = BadModel(a="x")
        with pytest.raises(ValueError, match=r"must use CBORField\(index="):
            b.model_dump_cbor()

    def test_exclude_if_in_array_model_raises(self) -> None:
        class BadModel(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            a: Annotated[str, CBORField(index=0)]
            b: Annotated[int, CBORField(index=1, exclude_if=lambda v: v < 0)]

        obj = BadModel(a="x", b=1)
        with pytest.raises(
            ValueError,
            match=r"exclude_if is not supported for array-encoded",
        ):
            obj.model_dump_cbor()


class TestComputedFields:
    def test_computed_field_map_encoding(self) -> None:
        class Model(CBORModel):
            name: Annotated[str, CBORField(key=0)]

            @computed_field
            @property
            def name_upper(self) -> Annotated[str, CBORField(key=1)]:
                return self.name.upper()

        obj = Model(name="hello")
        data: dict[int, Any] = obj.model_dump(context=CBORSerializationContext())
        assert data == {0: "hello", 1: "HELLO"}

        cbor_bytes = obj.model_dump_cbor()
        decoded = cbor2.loads(cbor_bytes)
        assert decoded == {0: "hello", 1: "HELLO"}

    def test_computed_field_not_settable_externally(self) -> None:
        class Model(CBORModel):
            _counter: int = PrivateAttr(default=0)
            name: Annotated[str, CBORField(key=0)]

            def increment(self) -> None:
                self._counter += 1

            @computed_field
            @property
            def counter(self) -> Annotated[int, CBORField(key=1)]:
                return self._counter

        obj = Model(name="test")
        obj.increment()
        obj.increment()

        data: dict[int, Any] = obj.model_dump(context=CBORSerializationContext())
        assert data == {0: "test", 1: 2}

        cbor_bytes = obj.model_dump_cbor()
        assert cbor2.loads(cbor_bytes) == {0: "test", 1: 2}

    def test_computed_field_without_cbor_field_is_excluded(self) -> None:
        class Model(CBORModel):
            name: Annotated[str, CBORField(key=0)]

            @computed_field
            @property
            def name_upper(self) -> str:
                return self.name.upper()

        obj = Model(name="hello")
        data: dict[int, Any] = obj.model_dump(
            context=CBORSerializationContext(),
        )
        assert data == {0: "hello"}

    def test_computed_field_array_encoding(self) -> None:
        class Model(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            name: Annotated[str, CBORField(index=0)]

            @computed_field
            @property
            def name_upper(self) -> Annotated[str, CBORField(index=1)]:
                return self.name.upper()

        obj = Model(name="hello")
        cbor_bytes = obj.model_dump_cbor()
        assert cbor2.loads(cbor_bytes) == ["hello", "HELLO"]


class TestBstrWrap:
    def test_bstr_wrap_map_encoding_round_trip(self) -> None:
        class Inner(CBORModel):
            x: Annotated[int, CBORField(key=0)]

        class Outer(CBORModel):
            inner: Annotated[Inner, CBORField(key=0, bstr_wrap=True)]

        obj = Outer(inner=Inner(x=42))
        cbor_bytes = obj.model_dump_cbor()

        raw = cbor2.loads(cbor_bytes)
        assert isinstance(raw[0], bytes)
        assert cbor2.loads(raw[0]) == {0: 42}

        restored = Outer.model_validate_cbor(cbor_bytes)
        assert restored == obj

    def test_bstr_wrap_primitive_round_trip(self) -> None:
        class Packet(CBORModel):
            data: Annotated[int, CBORField(key=0, bstr_wrap=True)]

        obj = Packet(data=99)
        cbor_bytes = obj.model_dump_cbor()

        raw = cbor2.loads(cbor_bytes)
        assert isinstance(raw[0], bytes)
        assert cbor2.loads(raw[0]) == 99

        restored = Packet.model_validate_cbor(cbor_bytes)
        assert restored == obj

    def test_bstr_wrap_with_tag_round_trip(self) -> None:
        class Packet(CBORModel):
            payload: Annotated[int, CBORField(key=0, bstr_wrap=True, tag=1001)]

        obj = Packet(payload=7)
        cbor_bytes = obj.model_dump_cbor()

        raw = cbor2.loads(cbor_bytes)
        assert isinstance(raw[0], cbor2.CBORTag)
        assert raw[0].tag == 1001
        assert isinstance(raw[0].value, bytes)
        assert cbor2.loads(raw[0].value) == 7

        restored = Packet.model_validate_cbor(cbor_bytes)
        assert restored == obj

    def test_bstr_wrap_array_encoding_round_trip(self) -> None:
        class Inner(CBORModel):
            v: Annotated[str, CBORField(key=0)]

        class Outer(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            inner: Annotated[Inner, CBORField(index=0, bstr_wrap=True)]

        obj = Outer(inner=Inner(v="hi"))
        cbor_bytes = obj.model_dump_cbor()

        raw = cbor2.loads(cbor_bytes)
        assert isinstance(raw, list)
        assert isinstance(raw[0], bytes)
        assert cbor2.loads(raw[0]) == {0: "hi"}

        restored = Outer.model_validate_cbor(cbor_bytes)
        assert restored == obj

    def test_bstr_wrap_nested_model_uses_nested_cbor_config(self) -> None:
        """Nested model's own CBOR config (encoding, tag) must be respected."""

        class Inner(CBORModel):
            cbor_config = CBORConfig(encoding="array")
            a: Annotated[int, CBORField(index=0)]
            b: Annotated[str, CBORField(index=1)]

        class Outer(CBORModel):
            inner: Annotated[Inner, CBORField(key=0, bstr_wrap=True)]

        obj = Outer(inner=Inner(a=1, b="x"))
        cbor_bytes = obj.model_dump_cbor()

        raw = cbor2.loads(cbor_bytes)
        assert isinstance(raw[0], bytes)
        # Inner used array encoding, so the bstr contains a CBOR array
        inner_decoded = cbor2.loads(raw[0])
        assert isinstance(inner_decoded, list)
        assert inner_decoded == [1, "x"]

        restored = Outer.model_validate_cbor(cbor_bytes)
        assert restored == obj
