from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic.fields import FieldInfo

from cbor_model import CBORModel
from cbor_model._util import extract_types_matching

from ._field_processor import FieldProcessor
from ._naming import to_snake
from ._type_converter import TypeConverter

if TYPE_CHECKING:
    from collections.abc import Iterable

    from cbor_model import CBORField


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
    ) -> None:
        """Initialize the generator.

        Args:
            type_converter: Custom :class:`TypeConverter` instance used to map
                Python types to CDDL type names.  When ``None``, a default
                :class:`TypeConverter` is used.

        """
        self._generated_types: set[type] = set()
        self._generated_enums: set[type[Enum]] = set()
        self._type_converter = type_converter or TypeConverter()
        self._field_processor = FieldProcessor(self._type_converter)

    def reset(self) -> None:
        """Reset the generator state to allow for fresh generation."""
        self._generated_types.clear()
        self._generated_enums.clear()

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
        fields_str = ",\n    ".join(fields)
        if model.cbor_config.encoding == "array":
            struct_def = f"{model.__name__} = [\n    {fields_str}\n]"
        else:
            struct_def = f"{model.__name__} = {{\n    {fields_str}\n}}"

        key_defs = (
            [d] if (d := self._generate_key_definitions(model)) else []
        )

        all_defs = enum_defs + dep_defs + key_defs
        return "\n\n".join([*all_defs, struct_def]) if all_defs else struct_def

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
        return "\n".join(
            f"{prefix}_{suffix} = {key}" for key, suffix in entries
        )

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

    def _generate_fields[T: CBORModel](self, model: type[T]) -> list[str]:
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

        members = (f"    {member.name}: {member.value}" for member in enum_type)
        members_str = ",\n".join(members)
        return f"{enum_type.__name__} = &(\n{members_str}\n)"
