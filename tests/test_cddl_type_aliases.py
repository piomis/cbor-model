# ruff: noqa: D
"""Tests for PEP 695 ``type X = ...`` alias handling in CDDL generation.

The contract under test:

* When a field annotation references a :class:`typing.TypeAliasType`, the
  alias body is emitted as a **top-level** CDDL rule named after the alias,
  and the parent field type references the alias by name.
* When the same alias is referenced from multiple parent models, the
  top-level rule is emitted exactly once.
* :class:`~cbor_model.CBORModel` and :class:`enum.Enum` dependencies hidden
  behind a type alias are still discovered (so they are emitted before the
  alias rule that needs them).
* Plain ``Union[A, B]`` / bare ``dict[K, V]`` annotations keep the existing
  inline behavior (back-compat).
"""

from enum import IntEnum
from typing import Annotated

from pydantic import Field

from cbor_model import CBORConfig, CBORField, CBORModel, CDDLGenerator


class ChoiceA(CBORModel):
    cbor_config = CBORConfig(encoding="map", canonical=True)
    proto: Annotated[int, CBORField(key=0)]


class ChoiceB(CBORModel):
    cbor_config = CBORConfig(encoding="map", canonical=True)
    proto: Annotated[int, CBORField(key=0)]


type Choices = ChoiceA | ChoiceB


class _Network(IntEnum):
    A = 0
    B = 1


class _NetworkInterface(IntEnum):
    X = 0
    Y = 1


type _NetworksMap = dict[_Network, list[_NetworkInterface]]


class TestTypeAliasUnions:
    def test_union_alias_becomes_named_rule(self) -> None:
        class Parent(CBORModel):
            cbor_config = CBORConfig(encoding="map", canonical=True)
            choices: Annotated[
                list[Choices],
                CBORField(key=0),
                Field(min_length=1, max_length=2),
            ]

        cddl = CDDLGenerator().generate(Parent)

        assert "Choices = ChoiceA / ChoiceB" in cddl
        # Parent references the alias by bare name, not the inlined union body.
        assert "parent_choices: [1*2 Choices]" in cddl
        assert "ChoiceA / ChoiceB]" not in cddl

    def test_alias_dependencies_are_emitted_before_alias(self) -> None:
        class Parent(CBORModel):
            cbor_config = CBORConfig(encoding="map", canonical=True)
            choices: Annotated[list[Choices], CBORField(key=0)]

        cddl = CDDLGenerator().generate(Parent)
        choice_a = cddl.index("ChoiceA = {")
        choice_b = cddl.index("ChoiceB = {")
        alias = cddl.index("Choices = ChoiceA / ChoiceB")
        parent = cddl.index("Parent = {")
        assert choice_a < alias
        assert choice_b < alias
        assert alias < parent

    def test_shared_alias_emitted_once(self) -> None:
        class A(CBORModel):
            cbor_config = CBORConfig(encoding="map", canonical=True)
            pick: Annotated[Choices, CBORField(key=0)]

        class B(CBORModel):
            cbor_config = CBORConfig(encoding="map", canonical=True)
            pick: Annotated[Choices, CBORField(key=0)]

        cddl = CDDLGenerator().generate([A, B])

        assert cddl.count("Choices = ChoiceA / ChoiceB") == 1
        assert "a_pick: Choices" in cddl
        assert "b_pick: Choices" in cddl

    def test_array_encoded_parent(self) -> None:
        class Parent(CBORModel):
            cbor_config = CBORConfig(encoding="array", canonical=True)
            t: Annotated[Choices, CBORField(index=0)]

        cddl = CDDLGenerator().generate(Parent)
        assert "Choices = ChoiceA / ChoiceB" in cddl
        assert "t: Choices" in cddl


class TestTypeAliasDicts:
    def test_dict_alias_becomes_named_rule(self) -> None:
        class Parent(CBORModel):
            cbor_config = CBORConfig(encoding="map", canonical=True)
            networks: Annotated[_NetworksMap, CBORField(key=0)]

        cddl = CDDLGenerator().generate(Parent)

        assert "_NetworksMap = {* _Network => [* _NetworkInterface]}" in cddl
        assert "parent_networks: _NetworksMap" in cddl
        # The dict body must NOT also be inlined in the parent field.
        assert "parent_networks: {*" not in cddl

    def test_alias_enum_dependencies_emitted_first(self) -> None:
        class Parent(CBORModel):
            cbor_config = CBORConfig(encoding="map", canonical=True)
            networks: Annotated[_NetworksMap, CBORField(key=0)]

        cddl = CDDLGenerator().generate(Parent)
        network = cddl.index("_Network = &(")
        network_interface = cddl.index("_NetworkInterface = &(")
        alias = cddl.index("_NetworksMap = {*")
        parent = cddl.index("Parent = {")
        assert network < alias
        assert network_interface < alias
        assert alias < parent


class TestBackCompat:
    """Annotations that are *not* PEP 695 aliases keep the inline shape."""

    def test_plain_union_is_still_inlined(self) -> None:
        class Parent(CBORModel):
            cbor_config = CBORConfig(encoding="map", canonical=True)
            t: Annotated[ChoiceA | ChoiceB, CBORField(key=0)]

        cddl = CDDLGenerator().generate(Parent)
        # No top-level alias rule is invented for an inline Union.
        assert "= ChoiceA / ChoiceB" not in cddl
        # The Union is still inlined into the parent field type.
        assert "parent_t: ChoiceA / ChoiceB" in cddl

    def test_plain_dict_is_still_inlined(self) -> None:
        class Parent(CBORModel):
            cbor_config = CBORConfig(encoding="map", canonical=True)
            networks: Annotated[
                dict[_Network, list[_NetworkInterface]],
                CBORField(key=0),
            ]

        cddl = CDDLGenerator().generate(Parent)
        # No top-level alias rule for an anonymous dict.
        assert "= {* _Network => [* _NetworkInterface]}" not in cddl.replace(
            "parent_networks: {* _Network => [* _NetworkInterface]}", ""
        )
        # But the inlined form is still produced for the field itself.
        assert "parent_networks: {* _Network => [* _NetworkInterface]}" in cddl


class TestReset:
    """``CDDLGenerator.reset()`` must drop alias bookkeeping too."""

    def test_reset_clears_alias_state(self) -> None:
        class Parent(CBORModel):
            cbor_config = CBORConfig(encoding="map", canonical=True)
            t: Annotated[Choices, CBORField(key=0)]

        gen = CDDLGenerator()
        first = gen.generate(Parent)
        # generate() resets at the start of the call, so a second invocation
        # on the same instance must produce identical output (alias re-emitted).
        second = gen.generate(Parent)
        assert first == second
        assert first.count("Choices = ChoiceA / ChoiceB") == 1
        assert second.count("Choices = ChoiceA / ChoiceB") == 1
