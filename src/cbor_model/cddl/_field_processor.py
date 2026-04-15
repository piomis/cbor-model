from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo

    from cbor_model import CBORConfig, CBORField

    from ._type_converter import TypeConverter

from cbor_model._util import is_optional


class FieldProcessor:
    """Processes individual fields to generate CDDL field definitions."""

    def __init__(self, type_converter: TypeConverter) -> None:
        self.type_converter = type_converter

    def process_field(
        self,
        field_name: str,
        field_info: FieldInfo,
        cbor_field: CBORField,
        config: CBORConfig,
    ) -> str:
        """Generate CDDL field definition from Pydantic FieldInfo and CBORField."""
        if field_info.annotation is None:
            err = f"Field {field_name!r} must have a type annotation"
            raise TypeError(err)

        display_name = cbor_field.override_name or field_name
        key = cbor_field.key if config.encoding == "map" else cbor_field.index
        optional = cbor_field.optional or is_optional(field_info.annotation)
        optional_prefix = "? " if optional else ""

        cddl_type = cbor_field.override_type or self.type_converter.convert(
            field_info.annotation,
            field_info,
        )

        if cbor_field.bstr_wrap and not cbor_field.override_type:
            cddl_type = f"bstr .cbor {cddl_type}"

        if cbor_field.tag is not None:
            cddl_type = f"#6.{cbor_field.tag}({cddl_type})"

        if config.encoding == "array":
            return f"{optional_prefix}{display_name}: {cddl_type}"
        return f"{optional_prefix}{key}: {cddl_type},  ; {display_name}"
