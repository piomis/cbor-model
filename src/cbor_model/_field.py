from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

CBOR2_RESERVED_TAGS = frozenset(
    {0, 1, 2, 3, 4, 5, 25, 28, 29, 30, 35, 36, 37, 100, 256, 258, 260, 261},
)
"""CBOR tags reserved by cbor2 library with semantic decoders."""


@dataclass(frozen=True, slots=True)
class CBORField:
    """Marks a :class:`~pydantic.BaseModel` field for CBOR serialization.

    Exactly one of `key` or `index` must be provided. Attach a `CBORField` to a
    field via :data:`typing.Annotated`:

    ```python
    from typing import Annotated
    from cbor_model import CBORModel, CBORField

    class MyModel(CBORModel):
        name: Annotated[str, CBORField(key=0)]
        value: Annotated[int, CBORField(key=1)]
    ```

    Attributes:
        key: Map key used when the parent model uses `encoding="map"`. May be
            an integer or a string.
        index: Zero-based position used when the parent model uses
            `encoding="array"`. Indices must be contiguous starting from 0,
            with optional fields at the tail.
        tag: CBOR tag number to wrap this field's value in on serialization.
            Use values above 1000 to avoid conflicts with standard tags. See
            `CBOR2_RESERVED_TAGS` for tags reserved by cbor2.
        override_type: Override the CDDL type name emitted by
            :class:`CDDLGenerator` for this field.
        override_name: Override the CDDL field name emitted by
            :class:`CDDLGenerator` for this field.
        optional: Mark the field as optional in CDDL output regardless of
            its Python type annotation.
        bstr_wrap: Encode the field value as embedded CBOR bytes (``bstr``).
            The value is serialized to CBOR bytes on encoding and decoded
            back on deserialization. In CDDL the type is rendered as
            ``bstr .cbor <inner_type>``. When combined with ``tag``, the
            tag wraps the ``bstr``: ``#6.N(bstr .cbor <inner_type>)``.
            For :class:`CBORModel` fields the nested model's own
            :meth:`~CBORModel.model_dump_cbor` is used so that its
            ``cbor_config`` is respected.
        exclude_if: A callable that receives the field value and returns
            `True` if the field should be omitted from the serialized output.
            Useful for custom exclusion logic beyond `None` or empty values.

    """

    key: int | str | None = None
    index: int | None = None
    tag: int | None = None
    """Custom CBOR tag number. Use values >1000 to avoid conflicts with
    standard tags.

    See `CBOR2_RESERVED_TAGS` for tags reserved by cbor2 library.
    """
    override_type: str | None = None
    override_name: str | None = None
    optional: bool = False
    bstr_wrap: bool = False
    exclude_if: Callable[[Any], bool] | None = None

    @property
    def identifier(self) -> int | str:
        """The CBOR map key or array index used to identify this field.

        Returns `key` when the field belongs to a map-encoded model, or
        `index` when it belongs to an array-encoded model.
        """
        return self.key if self.key is not None else cast("int", self.index)

    def __post_init__(self) -> None:
        if self.key is not None and self.index is not None:
            err = "Cannot specify both key and index for CBORField"
            raise ValueError(err)
        if self.key is None and self.index is None:
            err = "Must specify either key or index for CBORField"
            raise ValueError(err)
        if self.tag is not None:
            if self.tag < 0:
                err = f"CBOR tag {self.tag} is invalid. Tags must be non-negative integers."
                raise ValueError(err)
            if self.tag in CBOR2_RESERVED_TAGS:
                err = (
                    f"CBOR tag {self.tag} conflicts with cbor2 reserved tags. "
                    f"Use tag values > 1000 to avoid conflicts with standard CBOR tags."
                )
                raise ValueError(err)
