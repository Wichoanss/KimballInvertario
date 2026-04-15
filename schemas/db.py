"""
Schemas de BASE DE DATOS — validan filas crudas de SQLite al convertirlas a dict.
Se usan en database.py para garantizar que los datos en memoria son siempre válidos.
"""
from __future__ import annotations
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ReelModel(BaseModel):
    """Fila de la tabla `reels`."""
    code:         str   = Field(..., min_length=1)
    itemcode:     str   = Field(..., min_length=1)
    qty:          float = Field(..., ge=0.0)
    rack:         str   = Field(..., min_length=1)
    stockcell:    str   = Field(default="")
    date_added:   Optional[str] = None
    last_updated: Optional[str] = None

    @field_validator("itemcode", "code", mode="before")
    @classmethod
    def strip_str(cls, v: str) -> str:
        return str(v).strip() if v else ""

    @field_validator("qty", mode="before")
    @classmethod
    def coerce_qty(cls, v) -> float:
        try:
            return max(0.0, float(v))
        except (TypeError, ValueError):
            return 0.0


class JukiReelModel(BaseModel):
    """Fila de la tabla `juki_reels`."""
    code:         str   = Field(..., min_length=1)
    itemcode:     str   = Field(..., min_length=1)
    qty:          float = Field(..., ge=0.0)
    container_id: str   = Field(..., min_length=1)
    date_added:   Optional[str] = None
    last_updated: Optional[str] = None

    @field_validator("qty", mode="before")
    @classmethod
    def coerce_qty(cls, v) -> float:
        try:
            return max(0.0, float(v))
        except (TypeError, ValueError):
            return 0.0


class LineModel(BaseModel):
    """Fila de la tabla `lines`."""
    id:       int = Field(..., ge=1)
    name:     str = Field(..., min_length=1, max_length=64)
    rack_ids: str = Field(..., min_length=1)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return str(v).strip()


class MovementLogModel(BaseModel):
    """Fila de la tabla `movements_log`."""
    id:           int  = Field(..., ge=1)
    type:         str  = Field(..., pattern=r"^(smartrack|juki)$")
    target_line:  str  = Field(..., min_length=1)
    reel_codes:   str  = Field(..., min_length=1)
    item_codes:   str  = Field(default="")
    container_id: str  = Field(default="")
    status:       str  = Field(..., pattern=r"^(pending|extracted|cancelled)$")
    urgency:      int  = Field(..., ge=1, le=5)
    due_at:       Optional[str] = None
    created_at:   str  = Field(..., min_length=1)
