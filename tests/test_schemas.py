"""
test_schemas.py — Unit tests para todos los schemas Pydantic.
Verifican validación de tipos, rangos y normalización de datos de entrada.
"""
import pytest
from pydantic import ValidationError

from schemas.requests import (
    AuthRequest, CodeCheckRequest, ExtractRequest,
    JukiExtractRequest, CreateLineRequest, ExtractionType,
)


# ===========================================================================
# AuthRequest
# ===========================================================================
class TestAuthRequest:
    def test_valid(self):
        r = AuthRequest(username="admin", password="secret")
        assert r.username == "admin"

    def test_strips_username_whitespace(self):
        r = AuthRequest(username="  admin  ", password="x")
        assert r.username == "admin"

    def test_empty_username_fails(self):
        with pytest.raises(ValidationError):
            AuthRequest(username="", password="x")

    def test_empty_password_fails(self):
        with pytest.raises(ValidationError):
            AuthRequest(username="admin", password="")


# ===========================================================================
# CodeCheckRequest
# ===========================================================================
class TestCodeCheckRequest:
    def test_normalizes_itemcode_uppercase(self):
        r = CodeCheckRequest(itemcode="  abc123  ", line_id=1)
        assert r.itemcode == "ABC123"

    def test_line_id_must_be_positive(self):
        with pytest.raises(ValidationError):
            CodeCheckRequest(itemcode="ABC", line_id=0)

    def test_exclude_codes_strips_whitespace(self):
        r = CodeCheckRequest(itemcode="A", line_id=1, exclude_codes=["  X1  ", "Y2"])
        assert r.exclude_codes == ["X1", "Y2"]

    def test_exclude_codes_drops_blank_entries(self):
        r = CodeCheckRequest(itemcode="A", line_id=1, exclude_codes=["", "  ", "Z"])
        assert r.exclude_codes == ["Z"]

    def test_empty_itemcode_fails(self):
        with pytest.raises(ValidationError):
            CodeCheckRequest(itemcode="", line_id=1)


# ===========================================================================
# ExtractRequest
# ===========================================================================
class TestExtractRequest:
    def _valid(self, **overrides):
        base = dict(
            line_name="L1",
            item_codes=["ABC"],
            reel_codes=["R001"],
            type="smartrack",
        )
        base.update(overrides)
        return ExtractRequest(**base)

    def test_valid_smartrack(self):
        r = self._valid()
        assert r.type == ExtractionType.smartrack

    def test_urgency_bounds(self):
        self._valid(urgency=1)
        self._valid(urgency=5)
        with pytest.raises(ValidationError):
            self._valid(urgency=0)
        with pytest.raises(ValidationError):
            self._valid(urgency=6)

    def test_delay_minutes_max(self):
        self._valid(delay_minutes=1440)
        with pytest.raises(ValidationError):
            self._valid(delay_minutes=1441)

    def test_delay_minutes_negative_fails(self):
        with pytest.raises(ValidationError):
            self._valid(delay_minutes=-1)

    def test_empty_reel_codes_fails(self):
        with pytest.raises(ValidationError):
            self._valid(reel_codes=[])

    def test_blank_reel_codes_fail(self):
        with pytest.raises(ValidationError):
            self._valid(reel_codes=["  ", ""])

    def test_empty_item_codes_fails(self):
        with pytest.raises(ValidationError):
            self._valid(item_codes=[])

    def test_invalid_type_fails(self):
        with pytest.raises(ValidationError):
            self._valid(type="unknown")

    def test_juki_requires_container_id(self):
        with pytest.raises(ValidationError):
            self._valid(type="juki", container_id="")

    def test_juki_with_container_id_succeeds(self):
        r = self._valid(type="juki", container_id="C1")
        assert r.container_id == "C1"

    def test_strips_line_name(self):
        r = self._valid(line_name="  L2  ")
        assert r.line_name == "L2"

    def test_idempotency_key_optional(self):
        r = self._valid()
        assert r.idempotency_key is None
        r2 = self._valid(idempotency_key="abc-123")
        assert r2.idempotency_key == "abc-123"


# ===========================================================================
# JukiExtractRequest
# ===========================================================================
class TestJukiExtractRequest:
    def test_valid(self):
        r = JukiExtractRequest(
            name="EXT-001", container_id="C1",
            reel_codes=["R1", "R2"], log_ids=[1, 2]
        )
        assert len(r.reel_codes) == 2

    def test_empty_reel_codes_fails(self):
        with pytest.raises(ValidationError):
            JukiExtractRequest(name="X", container_id="C1", reel_codes=[], log_ids=[1])

    def test_invalid_log_id_fails(self):
        with pytest.raises(ValidationError):
            JukiExtractRequest(name="X", container_id="C1", reel_codes=["R1"], log_ids=[0])

    def test_negative_log_id_fails(self):
        with pytest.raises(ValidationError):
            JukiExtractRequest(name="X", container_id="C1", reel_codes=["R1"], log_ids=[-1])


# ===========================================================================
# CreateLineRequest
# ===========================================================================
class TestCreateLineRequest:
    def test_valid(self):
        r = CreateLineRequest(name="L1", rack_ids="1,2,3")
        assert r.rack_ids == "1,2,3"

    def test_strips_and_normalizes_rack_ids(self):
        r = CreateLineRequest(name="L1", rack_ids=" 1 , 2 , 3 ")
        assert r.rack_ids == "1,2,3"

    def test_non_numeric_rack_id_fails(self):
        with pytest.raises(ValidationError):
            CreateLineRequest(name="L1", rack_ids="1,abc,3")

    def test_empty_rack_ids_fails(self):
        with pytest.raises(ValidationError):
            CreateLineRequest(name="L1", rack_ids="")

    def test_empty_name_fails(self):
        with pytest.raises(ValidationError):
            CreateLineRequest(name="", rack_ids="1")
