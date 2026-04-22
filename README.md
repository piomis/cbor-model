# CBOR Model

`cbor-model` adds [CBOR] serialization and [CDDL] schema generation to [Pydantic]
models.

## Installation

```bash
pip install cbor-model
```

or with [uv]:

```bash
uv add cbor-model
```

## Quick start

### Map encoding

Fields are encoded as a CBOR map keyed by the integer or string supplied to
`CBORField(key=...)`.

```python
from typing import Annotated
from cbor_model import CBORModel, CBORField

class Sensor(CBORModel):
    name: Annotated[str, CBORField(key=0)]
    value: Annotated[float, CBORField(key=1)]

sensor = Sensor(name="temp", value=21.5)
data = sensor.model_dump_cbor()  # a2006474656d7001fb4035800000000000
assert Sensor.model_validate_cbor(data) == sensor
```

### Array encoding

Switch to array encoding by setting `CBORConfig(encoding="array")` and using
`CBORField(index=...)` — fields are serialized in index order.

```python
from typing import Annotated
from cbor_model import CBORModel, CBORField, CBORConfig

class Point(CBORModel):
    cbor_config = CBORConfig(encoding="array")

    x: Annotated[int, CBORField(index=0)]
    y: Annotated[int, CBORField(index=1)]

pt = Point(x=4, y=2)
data = pt.model_dump_cbor()  # 820402
assert Point.model_validate_cbor(data) == pt
```

### CBOR tags

Wrap a field's value in a CBOR tag using `CBORField(tag=...)`, or tag the entire
model with `CBORConfig(tag=...)`.

```python
from typing import Annotated
from cbor_model import CBORModel, CBORField, CBORConfig

class Reading(CBORModel):
    cbor_config = CBORConfig(tag=40001)

    sensor_id: Annotated[int, CBORField(key=0)]
    raw: Annotated[bytes, CBORField(key=1, tag=40002)]
```

### Serialization context

Pass a `CBORSerializationContext` to control `None` and empty-collection exclusion:

```python
from cbor_model import CBORSerializationContext

ctx = CBORSerializationContext(exclude_none=False, exclude_empty=False)
data = sensor.model_dump_cbor(context=ctx)
```

### Custom encoders

Register encoders for types not natively supported by [cbor2]:

```python
import decimal
from cbor_model import CBORConfig

class MyModel(CBORModel):
    cbor_config = CBORConfig(
        encoders={decimal.Decimal: lambda d: str(d)}
    )
    amount: Annotated[decimal.Decimal, CBORField(key=0)]
```

### CDDL generation

Generate a [CDDL] schema from one or more models:

```python
from cbor_model.cddl import CDDLGenerator

print(CDDLGenerator().generate(Sensor))
# sensor_name = 0
# sensor_value = 1
#
# Sensor = {
#     ? sensor_name: tstr,
#     ? sensor_value: float
# }
```

Map-encoded models always emit a per-model block of integer-key constants
(prefix is the model class name converted to `snake_case`) and reference
those constants in the map body. Use `CBORField(description=...)` to
attach a free-text comment that is rendered as `; <text>` after the
field definition, and `CBORField(override_name=...)` to override the
identifier (used verbatim).

[CBOR]: https://cbor.io/
[CDDL]: https://www.rfc-editor.org/rfc/rfc8610
[Pydantic]: https://github.com/pydantic/pydantic
[cbor2]: https://github.com/agronholm/cbor2
[uv]: https://docs.astral.sh/uv/


[pydantic]: https://github.com/pydantic/pydantic
