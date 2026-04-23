# ruff: noqa: ANN401
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import NoneType
from typing import (
    Any,
    Literal,
    Self,
    get_args,
    get_origin,
)
from uuid import UUID

from annotated_types import BaseMetadata, Ge, Gt, Le, Lt, MaxLen, MinLen
from pydantic.fields import FieldInfo

from cbor_model._util import is_optional, is_union_type


def numeric_modifier_from_metadata(metadata: list[BaseMetadata]) -> str:
    return NumericConstraint.from_metadata(metadata).to_cddl("int")


def _is_integral_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    return False


def _as_int(value: Any) -> int | None:
    return int(value) if _is_integral_number(value) else None


@dataclass
class NumericConstraint:
    """Represents numeric bounds for integer CDDL types."""

    lower: tuple[Any, bool] | None = None
    upper: tuple[Any, bool] | None = None

    @classmethod
    def from_metadata(
        cls,
        metadata: list[BaseMetadata],
    ) -> Self:
        """Extract the strongest numeric bounds from metadata."""
        lower: tuple[Any, bool] | None = None
        upper: tuple[Any, bool] | None = None

        for constraint in metadata:
            if isinstance(constraint, Gt):
                candidate = (constraint.gt, False)
                if lower is None or cls._is_stronger_lower(candidate, lower):
                    lower = candidate
            elif isinstance(constraint, Ge):
                candidate = (constraint.ge, True)
                if lower is None or cls._is_stronger_lower(candidate, lower):
                    lower = candidate
            elif isinstance(constraint, Lt):
                candidate = (constraint.lt, False)
                if upper is None or cls._is_stronger_upper(candidate, upper):
                    upper = candidate
            elif isinstance(constraint, Le):
                candidate = (constraint.le, True)
                if upper is None or cls._is_stronger_upper(candidate, upper):
                    upper = candidate

        return cls(lower=lower, upper=upper)

    @staticmethod
    def _is_stronger_lower(
        candidate: tuple[Any, bool],
        current: tuple[Any, bool],
    ) -> bool:
        if candidate[0] != current[0]:
            return candidate[0] > current[0]
        return not candidate[1] and current[1]

    @staticmethod
    def _is_stronger_upper(
        candidate: tuple[Any, bool],
        current: tuple[Any, bool],
    ) -> bool:
        if candidate[0] != current[0]:
            return candidate[0] < current[0]
        return not candidate[1] and current[1]

    def __bool__(self) -> bool:
        return self.lower is not None or self.upper is not None

    def to_cddl(self, base_type: str) -> str:
        """Convert numeric bounds to RFC 8610 CDDL."""
        if not self:
            return base_type

        if self.lower == (0, True) and self.upper is None:
            return "uint"

        if self.upper is not None and self.lower is None:
            upper_value, upper_inclusive = self.upper
            if upper_value < 0 or (upper_value == 0 and not upper_inclusive):
                return "nint"

        if closed_range := self.to_closed_range():
            lower_bound, upper_bound = closed_range
            if lower_bound == upper_bound:
                return str(lower_bound)
            return f"{lower_bound}..{upper_bound}"

        if self.lower is not None and self.upper is not None:
            return (
                f"({base_type} {self._lower_operator()} {self.lower[0]}) "
                f".and ({base_type} {self._upper_operator()} {self.upper[0]})"
            )

        if self.lower is not None:
            return f"{base_type} {self._lower_operator()} {self.lower[0]}"

        return f"{base_type} {self._upper_operator()} {self.upper[0]}"

    def to_closed_range(self) -> tuple[int, int] | None:
        """Normalize integer bounds to an inclusive range when possible."""
        if self.lower is None or self.upper is None:
            return None

        lower_value = _as_int(self.lower[0])
        upper_value = _as_int(self.upper[0])
        if lower_value is None or upper_value is None:
            return None

        lower_bound = lower_value if self.lower[1] else lower_value + 1
        upper_bound = upper_value if self.upper[1] else upper_value - 1
        return (lower_bound, upper_bound)

    def _lower_operator(self) -> str:
        return ".ge" if self.lower is not None and self.lower[1] else ".gt"

    def _upper_operator(self) -> str:
        return ".le" if self.upper is not None and self.upper[1] else ".lt"


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
        else:
            err = (
                "RFC 8610 requires .size constraints for strings and bytes "
                "to specify both min_length and max_length, or an exact size "
                "(min_length == max_length)."
            )
            raise ValueError(err)
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

    def convert(
        self,
        annotation: type[Any],
        field_info: FieldInfo | None = None,
    ) -> str:
        """Convert a Python type annotation to CDDL type string."""
        if field_info is None:
            field_info = FieldInfo()
        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is not None:
            if is_union_type(annotation):
                return self._convert_union(args, field_info)
            if origin is list:
                return self._convert_list(args, field_info)
            if origin is dict:
                return self._convert_dict(args, field_info)
            if origin is Literal:
                return self._convert_literal(args)

        if annotation in self.type_map:
            return self._apply_constraints(
                self.type_map[annotation],
                field_info,
                annotation,
            )

        return annotation.__name__

    def _convert_literal(
        self,
        args: tuple[Any, ...],
    ) -> str:
        """Convert Literal type to CDDL literal syntax."""
        parts: list[str] = []
        for arg in args:
            if isinstance(arg, bool):
                parts.append("true" if arg else "false")
            elif isinstance(arg, (int, float)):
                parts.append(str(arg))
            elif isinstance(arg, str):
                parts.append(f'"{arg}"')
            else:
                err = f"Unsupported Literal value type {type(arg).__name__!r} for CDDL generation"
                raise TypeError(err)
        return " / ".join(parts)

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
