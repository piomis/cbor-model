# ruff: noqa: ANN401

from dataclasses import dataclass
from threading import Lock
from typing import (
    Annotated,
    Any,
    ClassVar,
    NamedTuple,
    Self,
    cast,
    get_args,
    get_origin,
)

import cbor2
from pydantic import (
    BaseModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    ValidationInfo,
    ValidatorFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from ._config import CBORConfig, CBOREncoders
from ._field import CBORField
from ._util import is_optional as _is_optional_annotation

type _CborValue = (
    int | float | str | bytes | bool | None | list[Any] | dict[Any, Any] | cbor2.CBORTag
)


@dataclass(frozen=True, slots=True)
class CBORSerializationContext:
    """Controls serialization behavior when encoding a :class:`CBORModel`.

    Pass an instance as the `context` argument to :meth:`CBORModel.model_dump_cbor`
    or :meth:`CBORModel.model_validate_cbor` to override the defaults.

    Attributes:
        exclude_none: Omit fields whose value is `None` from the serialized
            output. Defaults to `True`.
        exclude_empty: Omit fields whose value is an empty collection
            (`list`, `tuple`, `dict`, or `set`) from the serialized output.
            Defaults to `True`.

    """

    exclude_none: bool = True
    exclude_empty: bool = True


class MapCBORMapping(NamedTuple):
    to_cbor: dict[str, int | str]
    from_cbor: dict[int | str, str]


class ArrayCBORMapping(NamedTuple):
    array_order: list[str]


class CBORModel(BaseModel):
    """Base class for CBOR-serializable models.

    Subclass `CBORModel` and declare fields using Pydantic's standard field
    syntax, annotating each field that should be included in CBOR output with
    a :class:`CBORField`.

    Serialization and deserialization are performed with
    :meth:`model_dump_cbor` and :meth:`model_validate_cbor` respectively.

    Attributes:
        cbor_config: A :class:`CBORConfig` instance that controls encoding
            behavior for the model. See :class:`CBORConfig` for the full
            list of options.

    Examples:
        Map encoding (default):

        ```python
        from typing import Annotated
        from cbor_model import CBORModel, CBORField, CBORConfig

        class Sensor(CBORModel):
            cbor_config = CBORConfig(encoding="map")

            name: Annotated[str, CBORField(key=0)]
            value: Annotated[float, CBORField(key=1)]

        sensor = Sensor(name="temp", value=21.5)
        data = sensor.model_dump_cbor()
        data.hex()  # a2006474656d7001fb4035800000000000
        assert Sensor.model_validate_cbor(data) == sensor
        ```

        Array encoding:

        ```python
        from typing import Annotated
        from cbor_model import CBORModel, CBORField, CBORConfig

        class Point(CBORModel):
            cbor_config = CBORConfig(encoding="array")

            x: Annotated[int, CBORField(index=0)]
            y: Annotated[int, CBORField(index=1)]

        pt = Point(x=4, y=2)
        data = pt.model_dump_cbor()
        data.hex()  # 820402
        assert Point.model_validate_cbor(data) == pt
        ```

    """

    cbor_config: ClassVar[CBORConfig] = CBORConfig()

    __cbor_lock__: ClassVar[Lock] = Lock()
    __cbor_mapping__: ClassVar[
        dict[type[BaseModel], MapCBORMapping | ArrayCBORMapping]
    ] = {}
    __cbor_encoders__: ClassVar[dict[type, CBOREncoders]] = {}
    __default_ctx__: ClassVar[CBORSerializationContext] = CBORSerializationContext()

    @classmethod
    def _get_merged_encoders(cls) -> CBOREncoders:
        """Return encoders merged from this model and all reachable nested CBORModel types.

        The root model's encoders take priority over those of nested models.
        Result is cached per class after the first call.
        """
        if cached := cls.__cbor_encoders__.get(cls):
            return cached
        with cls.__cbor_lock__:
            if cached := cls.__cbor_encoders__.get(cls):
                return cached
            merged: CBOREncoders = {}
            visited: set[type] = set()
            queue: list[type[CBORModel]] = [cls]
            while queue:
                model = queue.pop()
                if model in visited:
                    continue
                visited.add(model)
                merged.update(model.cbor_config.encoders)
                for field_info in model.model_fields.values():
                    queue.extend(_nested_cbor_models(field_info.annotation))
            merged.update(cls.cbor_config.encoders)
            cls.__cbor_encoders__[cls] = merged
        return cls.__cbor_encoders__[cls]

    @classmethod
    def _cbor_encode(
        cls,
        encoder: cbor2.CBOREncoder,
        obj: Any,
    ) -> None:
        handler = cls._get_merged_encoders().get(type(obj))
        if handler is None:
            err = f"No encoder registered for type {type(obj)}"
            raise TypeError(err)
        encoder.encode(handler(obj))

    @classmethod
    def _get_field_annotation[T](
        cls,
        field_name: str,
        annotation_type: type[T],
    ) -> T | None:
        metadata = cls.model_fields[field_name].metadata
        return next(
            (m for m in metadata if isinstance(m, annotation_type)),
            None,
        )

    @classmethod
    def _cbor_mapping(cls) -> MapCBORMapping | ArrayCBORMapping:
        if mapping := cls.__cbor_mapping__.get(cls):
            return mapping
        with cls.__cbor_lock__:
            if mapping := cls.__cbor_mapping__.get(cls):
                return mapping
            mapping = (
                cls._build_array_mapping()
                if cls.cbor_config.encoding == "array"
                else cls._build_map_mapping()
            )
            cls.__cbor_mapping__[cls] = mapping
        return cls.__cbor_mapping__[cls]

    @classmethod
    def _collect_cbor_fields(cls, *, by_key: bool) -> dict[int | str, str]:
        result: dict[int | str, str] = {}
        for field_name in (*cls.model_fields, *cls.model_computed_fields):
            cbor_field = cls.get_cbor_field(field_name)
            if not cbor_field:
                continue
            if by_key and cbor_field.key is None:
                err = (
                    f"Field {field_name!r} in map-encoded model {cls.__name__!r} "
                    f"must use CBORField(key=...), not index="
                )
                raise ValueError(err)
            if not by_key and cbor_field.index is None:
                err = (
                    f"Field {field_name!r} in array-encoded model {cls.__name__!r} "
                    f"must use CBORField(index=...), not key="
                )
                raise ValueError(err)
            slot = cbor_field.identifier
            if slot in result:
                err = (
                    f"Duplicate CBORField {'key' if by_key else 'index'} {slot} "
                    f"in {cls.__name__!r} for fields "
                    f"{result[slot]!r} and {field_name!r}"
                )
                raise ValueError(err)
            result[slot] = field_name
        return result

    @classmethod
    def _build_map_mapping(cls) -> MapCBORMapping:
        from_cbor = cls._collect_cbor_fields(by_key=True)
        to_cbor = {v: k for k, v in from_cbor.items()}
        return MapCBORMapping(to_cbor=to_cbor, from_cbor=from_cbor)

    @classmethod
    def _is_optional_field(
        cls,
        field_name: str,
        cbor_field: CBORField | None,
    ) -> bool:
        if cbor_field is not None and cbor_field.optional:
            return True
        if field_name in cls.model_fields:
            ann = cls.model_fields[field_name].annotation
        else:
            ann = cls.model_computed_fields[field_name].return_type
            if get_origin(ann) is Annotated:
                ann = get_args(ann)[0]
        return _is_optional_annotation(ann)

    @classmethod
    def _build_array_mapping(cls) -> ArrayCBORMapping:
        indexed = cast("dict[int, str]", cls._collect_cbor_fields(by_key=False))
        if not indexed:
            return ArrayCBORMapping(array_order=[])
        max_index = max(indexed)
        for i in range(max_index + 1):
            if i not in indexed:
                err = (
                    f"Index {i} is missing in array-encoded model {cls.__name__!r}. "
                    f"Indices must be contiguous starting from 0."
                )
                raise ValueError(err)
        array_order = [indexed[i] for i in range(max_index + 1)]
        seen_optional = False
        for field_name in array_order:
            cbor_field = cls.get_cbor_field(field_name)
            if cbor_field and cbor_field.exclude_if is not None:
                err = (
                    f"CBORField.exclude_if is not supported for array-encoded models "
                    f"(field {field_name!r} in {cls.__name__!r}). "
                    f"Use an Optional type with a None default instead."
                )
                raise ValueError(err)
            is_opt = cls._is_optional_field(field_name, cbor_field)
            if seen_optional and not is_opt:
                err = (
                    f"Non-optional field {field_name!r} cannot appear after an optional "
                    f"field in array-encoded model {cls.__name__!r}. "
                    f"Optional fields must be at the tail."
                )
                raise ValueError(err)
            if is_opt:
                seen_optional = True
        return ArrayCBORMapping(array_order=array_order)

    @classmethod
    def get_cbor_field(cls, field_name: str) -> CBORField | None:
        """Return the :class:`CBORField` annotation for *field_name*, or ``None``.

        Args:
            field_name: Name of the model field to look up.

        Looks up both regular and computed model fields.
        """
        if field_name in cls.model_fields:
            return cls._get_field_annotation(field_name, CBORField)
        if field_name in cls.model_computed_fields:
            return_type = cls.model_computed_fields[field_name].return_type
            if get_origin(return_type) is Annotated:
                return next(
                    (a for a in get_args(return_type)[1:] if isinstance(a, CBORField)),
                    None,
                )
        return None

    @classmethod
    def _unwrap_field(cls, value: _CborValue, field_name: str) -> _CborValue:
        cbor_field = cls.get_cbor_field(field_name)
        if cbor_field is None:
            return value
        if cbor_field.tag is not None:
            if not isinstance(value, cbor2.CBORTag):
                err = (
                    f"Expected CBORTag for field {field_name!r}, "
                    f"got {type(value).__name__}"
                )
                raise ValueError(err)
            if value.tag != cbor_field.tag:
                err = (
                    f"Tag mismatch for field {field_name!r}: "
                    f"expected {cbor_field.tag}, got {value.tag}"
                )
                raise ValueError(err)
            value = value.value
        if cbor_field.bstr_wrap:
            if not isinstance(value, bytes):
                err = (
                    f"Expected bstr for bstr_wrap field {field_name!r}, "
                    f"got {type(value).__name__}"
                )
                raise ValueError(err)
            value = cbor2.loads(value)
        return value

    @classmethod
    def _wrap_field(cls, field_name: str, value: Any) -> _CborValue:
        cbor_field = cls.get_cbor_field(field_name)
        if cbor_field is None or value is None:
            return value
        if cbor_field.bstr_wrap:
            if isinstance(value, CBORModel):
                value = value.model_dump_cbor()
            else:
                value = cbor2.dumps(
                    value,
                    default=cls._cbor_encode,
                    canonical=cls.cbor_config.canonical,
                )
        if cbor_field.tag is not None:
            value = cbor2.CBORTag(cbor_field.tag, value)
        return value

    @classmethod
    def model_validate_cbor(
        cls,
        data: bytes,
        context: CBORSerializationContext | None = None,
    ) -> Self:
        """Deserialize CBOR bytes to an instance of the model.

        Args:
            data: Raw CBOR-encoded bytes to decode.
            context: Serialization context controlling exclusion behavior.
                Defaults to the model's ``__default_ctx__``.
        """
        context = context or cls.__default_ctx__
        decoded = cbor2.loads(data)
        if cls.cbor_config.tag is not None:
            if (
                not isinstance(decoded, cbor2.CBORTag)
                or decoded.tag != cls.cbor_config.tag
            ):
                err = (
                    f"Expected CBOR tag {cls.cbor_config.tag}, "
                    f"got {decoded.tag if isinstance(decoded, cbor2.CBORTag) else type(decoded).__name__}"
                )
                raise ValueError(err)
            decoded = decoded.value
        return cls.model_validate(decoded, context=context)

    @model_validator(mode="wrap")
    @classmethod
    def validate_model(
        cls,
        value: Any,
        handler: ValidatorFunctionWrapHandler,
        info: ValidationInfo,
    ) -> Self:
        """Pydantic model validator that maps CBOR-decoded structures to model fields.

        When the validation context is a :class:`CBORSerializationContext`,
        translates CBOR array or map representations back to field names before
        delegating to the standard Pydantic validator.
        """
        if not isinstance(info.context, CBORSerializationContext):
            return cast("Self", handler(value))
        if isinstance(value, list):
            array_order = cast(
                "ArrayCBORMapping",
                cls._cbor_mapping(),
            ).array_order
            mapped: dict[str, Any] = {
                field_name: cls._unwrap_field(value[i], field_name)
                for i, field_name in enumerate(array_order)
                if i < len(value)
            }
            return cast("Self", handler(mapped))
        if isinstance(value, dict):
            from_cbor = cast("MapCBORMapping", cls._cbor_mapping()).from_cbor
            value = {
                from_cbor.get(k, k): cls._unwrap_field(v, from_cbor.get(k, ""))
                for k, v in value.items()
            }
        return cast("Self", handler(value))

    @model_serializer(mode="wrap")
    def serialize_model(
        self,
        handler: SerializerFunctionWrapHandler,
        info: SerializationInfo,
    ) -> dict[str, Any] | dict[int | str, Any] | list[Any]:
        """Pydantic model serializer that converts model fields to CBOR-encodable structures.

        When the serialization context is a :class:`CBORSerializationContext`,
        remaps field names to their CBOR keys or indices and applies
        exclusion rules before delegating to the standard Pydantic serializer.
        """
        data: dict[str, Any] = handler(self)

        if not isinstance(info.context, CBORSerializationContext):
            return data
        if self.cbor_config.encoding == "array":
            return self._serialize_as_array(data, info.context)
        return self._serialize_as_map(data, info.context)

    def _serialize_as_map(
        self,
        data: dict[str, Any],
        context: CBORSerializationContext,
    ) -> dict[int | str, Any]:
        to_cbor = cast("MapCBORMapping", self._cbor_mapping()).to_cbor
        result: dict[int | str, Any] = {}
        for field_name, value in data.items():
            cbor_field = self.get_cbor_field(field_name)
            if (
                not cbor_field
                or (value is None and context.exclude_none)
                or (cbor_field.exclude_if and cbor_field.exclude_if(value))
                or (
                    isinstance(value, (list, tuple, dict, set))
                    and not value
                    and context.exclude_empty
                )
            ):
                continue
            result[to_cbor[field_name]] = self._wrap_field(field_name, value)
        return result

    def _serialize_as_array(
        self,
        data: dict[str, Any],
        context: CBORSerializationContext,
    ) -> list[Any]:
        array_order = cast("ArrayCBORMapping", self._cbor_mapping()).array_order
        result = [self._wrap_field(f, data.get(f)) for f in array_order]
        if context.exclude_none:
            while result and result[-1] is None:
                result.pop()
        return result

    def model_dump_cbor(
        self,
        *,
        context: CBORSerializationContext | None = None,
    ) -> bytes:
        """Serialize the model to CBOR bytes.

        Args:
            context: Serialization context controlling exclusion behavior.
                Defaults to the model's ``__default_ctx__``.

        """
        context = context or self.__default_ctx__
        payload = self.model_dump(
            context=context,
            by_alias=False,
            exclude_none=self.cbor_config.encoding != "array" and context.exclude_none,
        )
        if self.cbor_config.tag is not None:
            payload = cbor2.CBORTag(self.cbor_config.tag, payload)
        return cbor2.dumps(
            payload,
            default=self._cbor_encode,
            canonical=self.cbor_config.canonical,
        )


def _nested_cbor_models(annotation: Any) -> list[type[CBORModel]]:
    """Return all CBORModel subclasses directly reachable in a type annotation."""
    origin = get_origin(annotation)
    if origin is not None:
        return [t for a in get_args(annotation) for t in _nested_cbor_models(a)]
    if isinstance(annotation, type) and issubclass(annotation, CBORModel):
        return [annotation]
    return []
