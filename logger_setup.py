"""
logger_setup.py — Logger de producción con JSON estructurado
============================================================
Arquitectura de dos canales:
  · Archivo → JSON compacto (machine-readable, parseable por ELK/Splunk/etc.)
  · Consola  → texto legible (para el operador que ve la ventana del .exe)

Contexto de request_id:
  Usar set_request_id("uuid") en middleware para que aparezca en TODOS
  los logs emitidos durante ese request, sin pasarlo manualmente.

Ejemplo de línea en smartrack.log:
  {"ts":"2026-04-14T21:30:00.123","lvl":"INFO","mod":"SmartRackPoller",
   "rid":"a1b2c3d4","msg":"Token de autenticacion obtenido correctamente."}
"""

from __future__ import annotations

import re
import json
import logging
import logging.handlers
import traceback
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

import config

# ---------------------------------------------------------------------------
# Context variable — propagación de request_id por contexto async/threading
# ---------------------------------------------------------------------------
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(rid: str) -> None:
    """Llamar en el middleware de FastAPI al inicio de cada request."""
    _request_id_var.set(rid)


def get_request_id() -> str:
    return _request_id_var.get()


# ---------------------------------------------------------------------------
# Redacción de datos sensibles (heredada y mejorada)
# ---------------------------------------------------------------------------
_REDACT_PATTERNS = [
    (re.compile(r'(?i)(password["\s:=]+)[^\s&"\'<,;]+'),       r'\1[REDACTED]'),
    (re.compile(r'(?i)(tkn["\s:=]+|token["\s:=]+)[^\s&"\'<,;]+'), r'\1[REDACTED]'),
    (re.compile(r'(?i)(bearer\s+)[A-Za-z0-9\-._~+/]+=*'),      r'\1[REDACTED]'),
    (re.compile(r'(?i)(api[_-]?key["\s:=]+)[^\s&"\'<,;]+'),    r'\1[REDACTED]'),
    (re.compile(r'(?i)(authorization["\s:=]+)[^\s&"\'<,;]+'),   r'\1[REDACTED]'),
    (re.compile(r'\b[0-9a-f]{32}\b'),                           '[TOKEN]'),
]


def _redact(text: str) -> str:
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class SensitiveDataFilter(logging.Filter):
    """Redacta credenciales/tokens antes de que lleguen a cualquier handler."""
    def filter(self, record: logging.LogRecord) -> bool:
        original = record.getMessage()
        sanitized = _redact(original)
        if sanitized != original:
            record.msg  = sanitized
            record.args = ()
        return True


# ---------------------------------------------------------------------------
# Formatter JSON — una línea por evento, parseable por cualquier SIEM
# ---------------------------------------------------------------------------
class JsonFormatter(logging.Formatter):
    """
    Formatea cada LogRecord como un objeto JSON en una sola línea.
    Campos emitidos:
      ts    — ISO-8601 con ms y timezone UTC
      lvl   — INFO | WARNING | ERROR | DEBUG | CRITICAL
      mod   — nombre del logger (módulo)
      rid   — request_id del contexto actual
      msg   — mensaje sanitizado
      exc   — traceback completo (solo si hay excepción)
      extra — campos adicionales pasados con extra={...}
    """
    # Campos internos de LogRecord que NO queremos en "extra"
    # (incluye todos los que Python puede rechazar con "Attempt to overwrite")
    _STD_ATTRS = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message",
        "taskName", "asctime",
    })

    def format(self, record: logging.LogRecord) -> str:
        # Mensaje ya sanitizado por SensitiveDataFilter
        message = record.getMessage()

        entry: dict[str, Any] = {
            "ts":  datetime.fromtimestamp(record.created, tz=timezone.utc)
                         .strftime("%Y-%m-%dT%H:%M:%S.") +
                   f"{int(record.msecs):03d}Z",
            "lvl": record.levelname,
            "mod": record.name,
            "rid": get_request_id(),
            "msg": message,
        }

        # Traceback si hay excepción
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        elif record.exc_text:
            entry["exc"] = record.exc_text

        # Campos extra pasados por el caller: logger.info("...", extra={"rack": "3"})
        extra = {
            k: v for k, v in record.__dict__.items()
            if k not in self._STD_ATTRS and not k.startswith("_")
        }
        if extra:
            entry["extra"] = extra

        return json.dumps(entry, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Formatter consola — legible para operador humano
# ---------------------------------------------------------------------------
_CONSOLE_FORMATTER = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ---------------------------------------------------------------------------
# Factory de loggers
# ---------------------------------------------------------------------------
def setup_logger(name: str) -> logging.Logger:
    """
    Retorna un logger configurado con:
      · Archivo rotante → JSON (5 MB × 3 backups) en logs/smartrack.log
      · Consola         → texto human-friendly (INFO+)
      · SensitiveDataFilter en ambos handlers
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.INFO))

    if not logger.handlers:
        sensitive_filter = SensitiveDataFilter()

        # --- Handler: archivo JSON rotante ---
        file_handler = logging.handlers.RotatingFileHandler(
            config.LOG_FILE,
            maxBytes=5 * 1024 * 1024,   # 5 MB por archivo
            backupCount=5,               # smartrack.log.1 / .2 ... .5
            encoding="utf-8",
        )
        file_handler.setFormatter(JsonFormatter())
        file_handler.addFilter(sensitive_filter)

        # --- Handler: consola (ventana del .exe / terminal de desarrollo) ---
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(_CONSOLE_FORMATTER)
        stream_handler.setLevel(logging.INFO)
        stream_handler.addFilter(sensitive_filter)

        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
        logger.propagate = False   # evitar doble log si el root logger tiene handlers

    return logger
