"""Single-import indirection for snake_case conversion used by the CDDL layer.

All identifier-name conversions emitted by :mod:`cbor_model.cddl` go through
this module so the conversion rule lives in exactly one place.
"""

from pydantic.alias_generators import to_snake

__all__ = ["to_snake"]
