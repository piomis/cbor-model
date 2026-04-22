from __future__ import annotations

from typing import Annotated

from pydantic import Field

Int1 = Annotated[int, Field(ge=-128, le=127)]
UInt = Annotated[int, Field(ge=0)]
UInt1 = Annotated[int, Field(ge=0, le=0xFF)]
UInt2 = Annotated[int, Field(ge=0, le=0xFFFF)]
UInt4 = Annotated[int, Field(ge=0, le=0xFFFFFFFF)]
