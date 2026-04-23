# ruff: noqa: ANN401
import sys
from types import NoneType
from typing import Any, TypeAliasType, TypeGuard, Union, get_args, get_origin

if sys.version_info >= (3, 14):
    _UNION_ORIGINS: tuple[Any, ...] = (Union,)
else:
    from types import UnionType

    _UNION_ORIGINS = (Union, UnionType)


def is_type_alias(annotation: Any) -> TypeGuard[TypeAliasType]:
    """Return True when ``annotation`` is a PEP 695 ``type X = ...`` alias."""
    return isinstance(annotation, TypeAliasType)


def is_union_type(annotation: Any) -> bool:
    """Return True when ``annotation`` is a typing.Union or types.UnionType (<3.14)."""
    return annotation in _UNION_ORIGINS or get_origin(annotation) in _UNION_ORIGINS


def is_optional(annotation: Any) -> bool:
    """Return True when ``annotation`` is Optional[...] (Union[..., None])."""
    return is_union_type(annotation) and NoneType in get_args(annotation)


def extract_type_aliases(annotation: Any) -> list[TypeAliasType]:
    """Return all PEP 695 TypeAliasType instances found directly in ``annotation``."""
    if is_type_alias(annotation):
        return [annotation]
    return [a for arg in get_args(annotation) for a in extract_type_aliases(arg)]


def is_type_of[T](annotation: Any, target: type[T]) -> TypeGuard[type[T]]:
    return isinstance(annotation, type) and issubclass(annotation, target)


def extract_types_matching[T](
    annotation: Any,
    predicate: type[T],
) -> list[type[T]]:
    types: list[type[T]] = []
    if is_type_alias(annotation):
        return extract_types_matching(annotation.__value__, predicate)

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is not None:
        for arg in args:
            types.extend(extract_types_matching(arg, predicate))
    elif is_type_of(annotation, predicate):
        types.append(annotation)

    return types
