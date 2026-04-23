from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Literal

from pydantic.fields import FieldInfo

from cbor_model import CBORModel
from cbor_model._util import extract_type_aliases, extract_types_matching

from ._field_processor import FieldProcessor, ProcessedField
from ._naming import to_snake
from ._type_converter import TypeConverter

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import TypeAliasType

    from cbor_model import CBORField


type EnumStyle = Literal["union", "choices"]


class CDDLGenerator:
    """Generates CDDL schemas from :class:`~cbor_model.CBORModel` subclasses.

    Walks the model graph — including nested models and :class:`~enum.Enum`
    types — and emits a complete CDDL document. Each model is emitted at most
    once even when referenced by multiple parents.

    Use :meth:`generate` to produce a CDDL string for one or more root models.
    Call :meth:`reset` if you need to reuse the same instance across independent
    generation runs.

    Examples:
        ```python
        from typing import Annotated
        from cbor_model import CBORModel, CBORField
        from cbor_model.cddl import CDDLGenerator

        class Point(CBORModel):
            x: Annotated[int, CBORField(key=0)]
            y: Annotated[int, CBORField(key=1)]

        print(CDDLGenerator().generate(Point))
        # point_x = 0
        # point_y = 1
        #
        # Point = {
        #     point_x: int,
        #     point_y: int,
        # }
        ```

    """

    def __init__(
        self,
        type_converter: TypeConverter | None = None,
        *,
        enum_style: EnumStyle = "union",
    ) -> None:
        """Initialize the generator.

        Args:
            type_converter: Custom :class:`TypeConverter` instance used to map
                Python types to CDDL type names.  When ``None``, a default
                :class:`TypeConverter` is used.
            enum_style: Controls how :class:`~enum.Enum` types are emitted.
                ``"union"`` (default) produces a CDDL control operator union
                ``&(...)``; ``"choices"`` produces individual value constants
                with ``/=`` choice assignments, as expected by tools like
                zcbor.

        """
        self._generated_types: set[type] = set()
        self._generated_enums: set[type[Enum]] = set()
        self._generated_aliases: set[str] = set()
        self._type_converter = type_converter or TypeConverter()
        self._field_processor = FieldProcessor(self._type_converter)
        self._enum_style: EnumStyle = enum_style

    def reset(self) -> None:
        """Reset the generator state to allow for fresh generation."""
        self._generated_types.clear()
        self._generated_enums.clear()
        self._generated_aliases.clear()

    def generate(
        self,
        model_or_models: type[CBORModel] | Iterable[type[CBORModel]],
    ) -> str:
        """Generate a CDDL document for one or more root models.

        When multiple models are given, shared type definitions are emitted only
        once. The generator state is always reset at the start of the call;
        use `reset()` followed by direct `_generate_struct` calls if
        incremental accumulation is needed.

        Args:
            model_or_models: A single :class:`~cbor_model.CBORModel` subclass
                or an iterable of subclasses to generate definitions for.

        """
        models = (
            [model_or_models] if isinstance(model_or_models, type) else model_or_models
        )
        for model in models:
            if not issubclass(model, CBORModel):
                err = f"{model.__name__} must be a subclass of CBORModel"
                raise TypeError(err)

        self.reset()
        parts = [self._generate_struct(model) for model in models]
        return "\n\n".join(p for p in parts if p)

    def _generate_struct[T: CBORModel](self, model: type[T]) -> str:
        """Generate the struct definition."""
        if model in self._generated_types:
            return ""

        self._generated_types.add(model)

        # Collect dependencies and generate them first
        model_deps, enum_deps = self._collect_dependencies(model)

        enum_defs = [
            d for enum_type in enum_deps if (d := self._generate_enum(enum_type))
        ]
        dep_defs = [
            d for dep_type in model_deps if (d := self._generate_struct(dep_type))
        ]

        fields = self._generate_fields(model)
        fields_str = "\n    ".join(self._format_field_lines(fields))
        if model.cbor_config.encoding == "array":
            body = f"[\n    {fields_str}\n]"
        else:
            body = f"{{\n    {fields_str}\n}}"
        if tag := model.cbor_config.tag:
            body = f"#6.{tag}({body})"
        struct_def = f"{model.__name__} = {body}"

        alias_defs = [
            d
            for _, fi, _ in self._iter_cbor_fields(model)
            if fi.annotation is not None
            for alias in extract_type_aliases(fi.annotation)
            if (d := self._generate_alias(alias))
        ]

        key_defs = [d] if (d := self._generate_key_definitions(model)) else []

        all_defs = enum_defs + dep_defs + alias_defs + key_defs
        return "\n\n".join([*all_defs, struct_def]) if all_defs else struct_def

    def _generate_alias(self, alias: TypeAliasType) -> str:
        """Generate a top-level CDDL rule for a PEP 695 type alias.

        Emits nested aliases depth-first so each is defined before it is
        referenced. Already-seen aliases are skipped.
        """
        name = alias.__name__
        if name in self._generated_aliases:
            return ""
        self._generated_aliases.add(name)
        nested = [
            d
            for a in extract_type_aliases(alias.__value__)
            if (d := self._generate_alias(a))
        ]
        body = self._type_converter.convert(alias.__value__)
        return "\n\n".join([*nested, f"{name} = {body}"])

    def _format_field_lines(self, fields: list[ProcessedField]) -> list[str]:
        """Add field separators while keeping comment formatting consistent."""
        if not fields:
            return []

        formatted: list[str] = []
        for i, field in enumerate(fields):
            is_last = i == len(fields) - 1
            text = field.text + "," if not is_last else field.text
            if field.description:
                formatted.append(f"{text}  ; {field.description}")
            else:
                formatted.append(text)

        return formatted

    def _generate_key_definitions[T: CBORModel](self, model: type[T]) -> str:
        """Generate the per-model integer-key constant block.

        Returns an empty string when the model is not map-encoded or has no
        integer-keyed fields. Identifiers are formatted as
        ``<snake_model>_<suffix>`` where the suffix is ``override_name``
        verbatim when set, else ``to_snake(field_name)``.
        """
        config = model.cbor_config
        if config.encoding != "map":
            return ""

        prefix = to_snake(model.__name__)
        entries: list[tuple[int, str]] = []
        for field_name, _, cbor_field in self._iter_cbor_fields(model):
            if isinstance(cbor_field.key, int):
                suffix = cbor_field.override_name or to_snake(field_name)
                entries.append((cbor_field.key, suffix))

        if not entries:
            return ""

        entries.sort(key=lambda item: item[0])
        return "\n".join(f"{prefix}_{suffix} = {key}" for key, suffix in entries)

    def _iter_cbor_fields(
        self,
        model: type[CBORModel],
    ) -> Iterable[tuple[str, FieldInfo, CBORField]]:
        """Yield (field_name, field_info, cbor_field) for every serializable field."""
        for field_name, field_info in model.model_fields.items():
            cbor_field = model.get_cbor_field(field_name)
            if cbor_field is not None:
                yield field_name, field_info, cbor_field
        for field_name, computed_field_info in model.model_computed_fields.items():
            cbor_field = model.get_cbor_field(field_name)
            if cbor_field is not None:
                return_type = computed_field_info.return_type
                yield field_name, FieldInfo.from_annotation(return_type), cbor_field

    def _collect_dependencies[T: CBORModel](
        self,
        model: type[T],
    ) -> tuple[list[type[CBORModel]], list[type[Enum]]]:
        """Collect model and enum dependencies from all fields."""
        models = [
            dep
            for _, field_info, _ in self._iter_cbor_fields(model)
            for dep in extract_types_matching(field_info.annotation, CBORModel)
            if dep not in self._generated_types
        ]
        enums = [
            enum
            for _, field_info, _ in self._iter_cbor_fields(model)
            for enum in extract_types_matching(field_info.annotation, Enum)
            if enum not in self._generated_enums
        ]
        return models, enums

    def _generate_fields[T: CBORModel](self, model: type[T]) -> list[ProcessedField]:
        """Generate CDDL field definitions for a model."""
        is_array = model.cbor_config.encoding == "array"
        model_prefix = None if is_array else to_snake(model.__name__)
        fields = [
            (
                cbor_field.index if is_array else cbor_field.key,
                self._field_processor.process_field(
                    field_name,
                    field_info,
                    cbor_field,
                    model.cbor_config,
                    model_prefix=model_prefix,
                ),
            )
            for field_name, field_info, cbor_field in self._iter_cbor_fields(model)
        ]
        fields.sort(key=lambda x: (x[0] is None, x[0]))
        return [field_def for _, field_def in fields]

    def _generate_enum(self, enum_type: type[Enum]) -> str:
        """Generate CDDL definition for an Enum."""
        if enum_type in self._generated_enums:
            return ""

        self._generated_enums.add(enum_type)

        if self._enum_style == "choices":
            prefix = to_snake(enum_type.__name__)
            member_defs = "\n".join(
                f"{prefix}_{member.name.lower()} = {member.value}"
                for member in enum_type
            )
            choice_defs = "\n".join(
                f"{enum_type.__name__} /= {prefix}_{member.name.lower()}"
                for member in enum_type
            )
            return f"{member_defs}\n\n{choice_defs}"

        members = (f"    {member.name}: {member.value}" for member in enum_type)
        members_str = ",\n".join(members)
        return f"{enum_type.__name__} = &(\n{members_str}\n)"
