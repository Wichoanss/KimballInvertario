"""
Schemas de RESPONSE — garantizan que la API nunca devuelva datos malformados.
FastAPI serializa automáticamente usando estos modelos.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status:    str = Field(..., examples=["ok"])
    timestamp: str


class StatusResponse(BaseModel):
    status:  str           = Field(..., examples=["success", "error"])
    message: Optional[str] = None


class AuthResponse(BaseModel):
    status: str
    token:  str


class AuthVerifyResponse(BaseModel):
    valid: bool


# ---------------------------------------------------------------------------
# Check reel
# ---------------------------------------------------------------------------
class ReelInfo(BaseModel):
    code:         str
    itemcode:     str
    qty:          float
    rack:         Optional[str] = None
    stockcell:    Optional[str] = None
    container_id: Optional[str] = None
    date_added:   Optional[str] = None


class CheckReelResponse(BaseModel):
    found:   bool
    exact:   Optional[bool]    = None
    status:  Optional[str]     = None
    reel:    Optional[ReelInfo] = None
    message: Optional[str]     = None


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------
class ScheduledJobResponse(BaseModel):
    id:            str
    name:          str
    next_run_time: str


# ---------------------------------------------------------------------------
# Movements
# ---------------------------------------------------------------------------
class MovementResponse(BaseModel):
    id:           int
    type:         str
    target_line:  str
    reel_codes:   str
    item_codes:   Optional[str] = ""
    container_id: Optional[str] = ""
    status:       str
    urgency:      int
    due_at:       Optional[str] = None
    created_at:   str
