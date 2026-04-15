"""
test_logger.py — Unit tests para SensitiveDataFilter y JsonFormatter.
"""
import json
import logging
import pytest

from logger_setup import SensitiveDataFilter, JsonFormatter, set_request_id, get_request_id


# ===========================================================================
# SensitiveDataFilter — redacción de datos sensibles
# ===========================================================================
class TestSensitiveDataFilter:

    def _make_record(self, msg: str) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="", lineno=0, msg=msg,
            args=(), exc_info=None
        )
        return record

    def _apply(self, msg: str) -> str:
        f = SensitiveDataFilter()
        record = self._make_record(msg)
        f.filter(record)
        return record.getMessage()

    def test_redacts_password_query_param(self):
        result = self._apply("login?password=supersecret&user=admin")
        assert "supersecret" not in result
        assert "[REDACTED]" in result

    def test_redacts_tkn_param(self):
        result = self._apply("f=getlist&tkn=abc123xyz999")
        assert "abc123xyz999" not in result
        assert "[REDACTED]" in result

    def test_redacts_bearer_token(self):
        result = self._apply("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload")
        assert "eyJhbGciOiJIUzI1NiJ9" not in result
        assert "[REDACTED]" in result

    def test_redacts_32char_hex_token(self):
        hex_token = "a" * 32
        result = self._apply(f"token del sistema: {hex_token}")
        assert hex_token not in result
        assert "[TOKEN]" in result

    def test_safe_message_unchanged(self):
        msg = "Polling rack 3: encontrados 25 rollos"
        result = self._apply(msg)
        assert result == msg

    def test_always_returns_true(self):
        """El filtro nunca debe suprimir registros, solo sanitizarlos."""
        f = SensitiveDataFilter()
        record = self._make_record("cualquier mensaje")
        assert f.filter(record) is True

    def test_args_cleared_after_redaction(self):
        """Si redacta, args debe quedar vacío para evitar re-interpolación."""
        f = SensitiveDataFilter()
        record = self._make_record("password=%s")
        record.msg  = "password=%s"
        record.args = ("secreto",)
        f.filter(record)
        assert record.args == ()


# ===========================================================================
# JsonFormatter
# ===========================================================================
class TestJsonFormatter:

    def _format(self, msg: str, level=logging.INFO, extra=None) -> dict:
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="TestMod", level=level,
            pathname="", lineno=0, msg=msg,
            args=(), exc_info=None
        )
        if extra:
            for k, v in extra.items():
                setattr(record, k, v)
        line = formatter.format(record)
        return json.loads(line)   # Debe ser JSON válido

    def test_output_is_valid_json(self):
        data = self._format("Mensaje de prueba")
        assert isinstance(data, dict)

    def test_has_required_fields(self):
        data = self._format("Test")
        for field in ("ts", "lvl", "mod", "rid", "msg"):
            assert field in data, f"Campo '{field}' ausente en JSON"

    def test_level_name_correct(self):
        data = self._format("test", level=logging.WARNING)
        assert data["lvl"] == "WARNING"

    def test_module_name_correct(self):
        data = self._format("test")
        assert data["mod"] == "TestMod"

    def test_message_correct(self):
        data = self._format("Hola mundo")
        assert data["msg"] == "Hola mundo"

    def test_timestamp_format(self):
        data = self._format("test")
        ts = data["ts"]
        assert ts.endswith("Z"), f"Timestamp debe terminar en Z: {ts}"
        assert "T" in ts

    def test_extra_fields_included(self):
        data = self._format("test", extra={"rack": "3", "reels": 25})
        assert "extra" in data
        assert data["extra"]["rack"] == "3"
        assert data["extra"]["reels"] == 25

    def test_exception_info_included(self):
        formatter = JsonFormatter()
        try:
            raise ValueError("error de prueba")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="T", level=logging.ERROR,
            pathname="", lineno=0, msg="fallo",
            args=(), exc_info=exc_info
        )
        line = formatter.format(record)
        data = json.loads(line)
        assert "exc" in data
        assert "ValueError" in data["exc"]


# ===========================================================================
# request_id context propagation
# ===========================================================================
class TestRequestId:
    def test_default_is_dash(self):
        # Resetear a valor por defecto
        set_request_id("-")
        assert get_request_id() == "-"

    def test_set_and_get(self):
        set_request_id("abc-123")
        assert get_request_id() == "abc-123"

    def test_request_id_in_json_output(self):
        set_request_id("test-rid-99")
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="T", level=logging.INFO,
            pathname="", lineno=0, msg="x",
            args=(), exc_info=None
        )
        data = json.loads(formatter.format(record))
        assert data["rid"] == "test-rid-99"
