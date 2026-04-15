# ruff: noqa: ANN401
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import NoneType
from typing import TYPE_CHECKING, Any, Self, get_args, get_origin
from uuid import UUID

from annotated_types import BaseMetadata, Ge, Gt, Le, Lt, MaxLen, MinLen

from cbor_model._util import is_optional, is_union_type

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo


def numeric_modifier_from_metadata(metadata: list[BaseMetadata]) -> str:
    lowers: list[tuple[Any, bool]] = []
    uppers: list[tuple[Any, bool]] = []
    for c in metadata:
        if isinstance(c, Gt):
            lowers.append((c.gt, False))
        elif isinstance(c, Ge):
            lowers.append((c.ge, True))
        elif isinstance(c, Lt):
            uppers.append((c.lt, False))
        elif isinstance(c, Le):
            uppers.append((c.le, True))

    if lowers:
        max_lower, _ = max(lowers, key=lambda t: t[0])
        if max_lower >= 0:
            return "uint"

    if uppers:
        min_upper, incl = min(uppers, key=lambda t: t[0])
        if min_upper < 0 or (min_upper == 0 and not incl):
            return "nint"

    return "int"


@dataclass
class RangeConstraint:
    """Represents min/max length constraints for CDDL types."""

    min_length: int | None = None
    max_length: int | None = None

    @classmethod
    def from_metadata(
        cls,
        metadata: list[BaseMetadata],
    ) -> Self:
        """Extract min and max length constraints from metadata."""
        min_len = max_len = None
        for constraint in metadata:
            if isinstance(constraint, MinLen):
                min_len = constraint.min_length
            elif isinstance(constraint, MaxLen):
                max_len = constraint.max_length
        return cls(min_length=min_len, max_length=max_len)

    def __bool__(self) -> bool:
        """Return True if any constraints are set."""
        return self.min_length is not None or self.max_length is not None

    def to_size(self) -> str:
        """Convert to CDDL size constraint string."""
        if not self:
            return ""
        if self.min_length is not None and self.max_length is not None:
            constraint = (
                str(self.min_length)
                if self.min_length == self.max_length
                else f"({self.min_length}..{self.max_length})"
            )
        elif self.min_length is not None:
            constraint = f"{self.min_length}.."
        elif self.max_length is not None:
            constraint = f"..{self.max_length}"
        else:
            return ""
        return f".size {constraint}"

    def to_list(self, cddl_type: str) -> str:
        """Convert to CDDL list constraint string."""
        if self.min_length == 1 and self.max_length is None:
            constraint = "+"
        elif self.min_length is not None and self.max_length is not None:
            constraint = f"{self.min_length}*{self.max_length}"
        elif self.min_length is not None:
            constraint = f"{self.min_length}*"
        elif self.max_length is not None:
            constraint = f"*{self.max_length}"
        else:
            constraint = "*"
        return f"[{constraint} {cddl_type}]"


DEFAULT_TYPE_MAP = {
    str: "tstr",
    bytes: "bstr",
    int: "int",
    bool: "bool",
    float: "float",
    datetime: "tdate",
    UUID: "#6.37(bstr)",
    Any: "any",
}


class TypeConverter:
    """Converts Python type annotations to CDDL types."""

    def __init__(
        self,
        type_map: dict[type, str] | None = None,
    ) -> None:
        self.type_map = type_map or DEFAULT_TYPE_MAP.copy()

    def convert(self, annotation: type[Any], field_info: FieldInfo) -> str:
        """Convert a Python type annotation to CDDL type string."""
        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is not None:
            if is_union_type(annotation):
                return self._convert_union(args, field_info)
            if origin is list:
                return self._convert_list(args, field_info)
            if origin is dict:
                return self._convert_dict(args, field_info)

        if annotation in self.type_map:
            return self._apply_constraints(
                self.type_map[annotation],
                field_info,
                annotation,
            )

        return annotation.__name__

    def _convert_union(
        self,
        args: tuple[Any, ...],
        field_info: FieldInfo,
    ) -> str:
        """Convert Union type to CDDL union syntax."""
        non_none_args = [arg for arg in args if arg is not NoneType]
        if len(non_none_args) == 1:
            return self.convert(non_none_args[0], field_info)
        return " / ".join(self.convert(arg, field_info) for arg in non_none_args)

    def _convert_list(
        self,
        args: tuple[Any, ...],
        field_info: FieldInfo,
    ) -> str:
        """Convert list type to CDDL array syntax."""
        constraints = RangeConstraint.from_metadata(field_info.metadata)
        item_type = self.convert(args[0], field_info) if args else "any"
        return constraints.to_list(item_type)

    def _convert_dict(
        self,
        args: tuple[Any, ...],
        field_info: FieldInfo,
    ) -> str:
        """Convert dict type to CDDL map syntax."""
        key_type = self.convert(args[0], field_info) if len(args) > 0 else "any"
        val_type = self.convert(args[1], field_info) if len(args) > 1 else "any"
        return f"{{* {key_type} => {val_type}}}"

    def _apply_constraints(
        self,
        base_type: str,
        field_info: FieldInfo,
        annotation: Any,
    ) -> str:
        """Apply Pydantic Field constraints to CDDL type."""
        field_ann = field_info.annotation
        if is_union_type(field_ann) and is_optional(field_ann):
            non_none = [a for a in get_args(field_ann) if a is not NoneType]
            if len(non_none) == 1:
                field_ann = non_none[0]
        if annotation != field_ann:
            return base_type

        metadata = field_info.metadata

        if base_type == "int":
            return numeric_modifier_from_metadata(metadata)

        if base_type in ("tstr", "bstr") and (
            constraints := RangeConstraint.from_metadata(metadata)
        ):
            return f"{base_type} {constraints.to_size()}"

        return base_type
