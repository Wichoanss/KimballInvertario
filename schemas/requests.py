"""
Schemas de REQUEST — validan datos de entrada antes de procesarlos.
Toda sanitización/normalización ocurre en los validators,
así el resto del código recibe datos ya limpios y garantizados.
"""
from __future__ import annotations
import uuid
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enum de tipos de extracción
# ---------------------------------------------------------------------------
class ExtractionType(str, Enum):
    smartrack = "smartrack"
    juki      = "juki"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class AuthRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, v: str) -> str:
        return v.strip()


# ---------------------------------------------------------------------------
# Check reel
# ---------------------------------------------------------------------------
class CodeCheckRequest(BaseModel):
    itemcode:      str       = Field(..., min_length=1, max_length=100)
    line_id:       int       = Field(..., ge=1)
    exclude_codes: List[str] = Field(default_factory=list)

    @field_validator("itemcode", mode="before")
    @classmethod
    def normalize_itemcode(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("exclude_codes", mode="before")
    @classmethod
    def clean_exclude(cls, v: list) -> list:
        return [str(c).strip() for c in v if str(c).strip()]


# ---------------------------------------------------------------------------
# Extract (SmartRack y JUKI)
# ---------------------------------------------------------------------------
class ExtractRequest(BaseModel):
    line_name:       str            = Field(..., min_length=1, max_length=64)
    item_codes:      List[str]      = Field(..., min_length=1)
    reel_codes:      List[str]      = Field(..., min_length=1)
    delay_minutes:   int            = Field(default=0, ge=0, le=1440)
    type:            ExtractionType = Field(default=ExtractionType.smartrack)
    container_id:    str            = Field(default="", max_length=32)
    urgency:         int            = Field(default=1, ge=1, le=5)
    idempotency_key: Optional[str]  = Field(
        default=None,
        description="UUID generado por el cliente para evitar extracciones duplicadas en reintentos."
    )

    @field_validator("line_name", mode="before")
    @classmethod
    def strip_line_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("item_codes", "reel_codes", mode="before")
    @classmethod
    def clean_code_lists(cls, v: list) -> list:
        cleaned = [str(c).strip() for c in v if str(c).strip()]
        if not cleaned:
            raise ValueError("La lista no puede estar vacía o contener solo espacios")
        return cleaned

    @model_validator(mode="after")
    def juki_requires_container(self) -> "ExtractRequest":
        if self.type == ExtractionType.juki and not self.container_id:
            raise ValueError("container_id es obligatorio para extracciones de tipo 'juki'")
        return self


# ---------------------------------------------------------------------------
# JUKI extract (operador)
# ---------------------------------------------------------------------------
class JukiExtractRequest(BaseModel):
    name:            str            = Field(..., min_length=1, max_length=128)
    container_id:    str            = Field(..., min_length=1, max_length=32)
    reel_codes:      List[str]      = Field(..., min_length=1)
    log_ids:         List[int]      = Field(..., min_length=1)
    idempotency_key: Optional[str]  = Field(
        default=None,
        description="UUID generado por el cliente para evitar extracciones JUKI duplicadas."
    )

    @field_validator("reel_codes", mode="before")
    @classmethod
    def clean_reels(cls, v: list) -> list:
        cleaned = [str(c).strip() for c in v if str(c).strip()]
        if not cleaned:
            raise ValueError("reel_codes no puede estar vacío")
        return cleaned

    @field_validator("log_ids", mode="before")
    @classmethod
    def validate_log_ids(cls, v: list) -> list:
        parsed = []
        for item in v:
            try:
                n = int(item)
                if n < 1:
                    raise ValueError(f"log_id inválido: {item}")
                parsed.append(n)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"log_id debe ser entero positivo: {item}") from exc
        if not parsed:
            raise ValueError("log_ids no puede estar vacío")
        return parsed


# ---------------------------------------------------------------------------
# Crear / actualizar línea
# ---------------------------------------------------------------------------
class CreateLineRequest(BaseModel):
    name:     str = Field(..., min_length=1, max_length=64)
    rack_ids: str = Field(..., min_length=1, max_length=256)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("rack_ids", mode="before")
    @classmethod
    def validate_rack_ids(cls, v: str) -> str:
        """Valida que rack_ids sea una lista de enteros separados por coma."""
        parts = [p.strip() for p in str(v).split(",") if p.strip()]
        if not parts:
            raise ValueError("rack_ids debe contener al menos un ID")
        for p in parts:
            if not p.isdigit():
                raise ValueError(f"rack_id inválido: '{p}' — debe ser número entero")
        return ",".join(parts)
