"""
test_api.py — Integration tests para los endpoints HTTP de FastAPI.
Usa TestClient con DB temporal y pollers mockeados.
NO hace llamadas reales al SmartRack server.
"""
import pytest
from unittest.mock import patch


# ===========================================================================
# Health
# ===========================================================================
class TestHealth:
    def test_health_ok(self, test_client):
        r = test_client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "circuit_breaker" in data

    def test_health_returns_request_id_header(self, test_client):
        r = test_client.get("/health")
        assert "x-request-id" in r.headers

    def test_circuit_breaker_status_endpoint(self, test_client):
        r = test_client.get("/api/health/circuit-breaker")
        assert r.status_code == 200
        data = r.json()
        assert "state" in data
        assert data["state"] == "CLOSED"


# ===========================================================================
# Auth Config
# ===========================================================================
class TestAuthConfig:
    def test_valid_credentials_returns_token(self, test_client):
        import config
        r = test_client.post("/api/auth/config", json={
            "username": config.CONFIG_USERNAME,
            "password": config.CONFIG_PASSWORD,
        })
        assert r.status_code == 200
        assert "token" in r.json()

    def test_invalid_credentials_returns_401(self, test_client):
        r = test_client.post("/api/auth/config", json={
            "username": "wrong",
            "password": "wrong",
        })
        assert r.status_code == 401

    def test_verify_valid_token(self, test_client):
        import config
        login = test_client.post("/api/auth/config", json={
            "username": config.CONFIG_USERNAME,
            "password": config.CONFIG_PASSWORD,
        })
        token = login.json()["token"]
        r = test_client.get("/api/auth/config/verify",
                            headers={"Authorization": f"Bearer {token}"})
        assert r.json()["valid"] is True

    def test_verify_invalid_token(self, test_client):
        r = test_client.get("/api/auth/config/verify",
                            headers={"Authorization": "Bearer invalidtoken123"})
        assert r.json()["valid"] is False

    def test_verify_no_header_returns_false(self, test_client):
        r = test_client.get("/api/auth/config/verify")
        assert r.json()["valid"] is False


# ===========================================================================
# Reels
# ===========================================================================
class TestReels:
    def test_get_all_reels_empty(self, test_client):
        r = test_client.get("/api/reels")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_juki_reels_empty(self, test_client):
        r = test_client.get("/api/juki/reels")
        assert r.status_code == 200

    def test_export_csv(self, test_client):
        r = test_client.get("/api/reels/export/csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        assert "Rack" in r.text


# ===========================================================================
# Lines
# ===========================================================================
class TestLines:
    def test_get_lines(self, test_client):
        r = test_client.get("/api/lines")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_line(self, test_client):
        r = test_client.post("/api/lines", json={"name": "TEST-API", "rack_ids": "10,11"})
        assert r.status_code == 200
        assert r.json()["status"] == "success"

    def test_create_line_invalid_rack_id(self, test_client):
        r = test_client.post("/api/lines", json={"name": "BAD", "rack_ids": "abc,def"})
        assert r.status_code == 422

    def test_create_line_missing_fields(self, test_client):
        r = test_client.post("/api/lines", json={"name": ""})
        assert r.status_code == 422

    def test_delete_line(self, test_client):
        # Crear primero
        test_client.post("/api/lines", json={"name": "DEL-TEST", "rack_ids": "99"})
        lines = test_client.get("/api/lines").json()
        line_id = next(l["id"] for l in lines if l["name"] == "DEL-TEST")
        r = test_client.delete(f"/api/lines/{line_id}")
        assert r.status_code == 200


# ===========================================================================
# Check Reel
# ===========================================================================
class TestCheckReel:
    def test_reel_not_found(self, test_client):
        lines = test_client.get("/api/lines").json()
        line_id = lines[0]["id"]
        r = test_client.post("/api/check_reel", json={
            "itemcode": "NONEXISTENT-PART",
            "line_id": line_id,
        })
        assert r.status_code == 200
        assert r.json()["found"] is False

    def test_invalid_line_id_fails(self, test_client):
        r = test_client.post("/api/check_reel", json={
            "itemcode": "ABC",
            "line_id": 0,  # inválido
        })
        assert r.status_code == 422


# ===========================================================================
# Extract (SmartRack)
# ===========================================================================
class TestExtract:
    def _payload(self, **overrides):
        base = {
            "line_name": "L1",
            "item_codes": ["ABC123"],
            "reel_codes": ["R001"],
            "type": "smartrack",
        }
        base.update(overrides)
        return base

    def test_immediate_extraction_success(self, test_client, api_user_key):
        with patch("main.execute_extraction", return_value=(True, "Success")):
            r = test_client.post("/api/extract", 
                                 json=self._payload(),
                                 headers={"X-API-Key": api_user_key})
        assert r.status_code == 200
        assert r.json()["status"] == "success"

    def test_extraction_failure_returns_500(self, test_client, api_user_key):
        with patch("main.execute_extraction", return_value=(False, "API Error")):
            r = test_client.post("/api/extract", 
                                 json=self._payload(),
                                 headers={"X-API-Key": api_user_key})
        assert r.status_code == 500

    def test_idempotency_same_key_returns_cached(self, test_client, api_user_key):
        key = "idem-test-key-001"
        with patch("main.execute_extraction", return_value=(True, "Success")):
            r1 = test_client.post("/api/extract", 
                                  json=self._payload(idempotency_key=key),
                                  headers={"X-API-Key": api_user_key})
        assert r1.status_code == 200
        # Segundo request con misma key → resultado cacheado, execute_extraction NO se llama
        with patch("main.execute_extraction", side_effect=Exception("NO DEBE LLAMARSE")) as mock_exec:
            r2 = test_client.post("/api/extract", 
                                  json=self._payload(idempotency_key=key),
                                  headers={"X-API-Key": api_user_key})
        assert r2.status_code == 200
        assert r2.json()["status"] == "success"
        mock_exec.assert_not_called()

    def test_empty_reel_codes_fails_validation(self, test_client, api_user_key):
        r = test_client.post("/api/extract", 
                             json=self._payload(reel_codes=[]),
                             headers={"X-API-Key": api_user_key})
        assert r.status_code == 422

    def test_invalid_urgency_fails_validation(self, test_client, api_user_key):
        r = test_client.post("/api/extract", 
                             json=self._payload(urgency=10),
                             headers={"X-API-Key": api_user_key})
        assert r.status_code == 422

    def test_juki_request_enqueued(self, test_client, api_user_key):
        r = test_client.post("/api/extract", 
                             json=self._payload(type="juki", container_id="C1"),
                             headers={"X-API-Key": api_user_key})
        assert r.status_code == 200

    def test_scheduled_extraction(self, test_client, api_user_key):
        with patch.object(
            __import__("main", fromlist=["scheduler"]).scheduler, "add_job"
        ):
            r = test_client.post("/api/extract", 
                                 json=self._payload(delay_minutes=5),
                                 headers={"X-API-Key": api_user_key})
        assert r.status_code == 200


# ===========================================================================
# Scheduled jobs
# ===========================================================================
class TestScheduled:
    def test_get_scheduled_empty(self, test_client):
        r = test_client.get("/api/scheduled")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_delete_nonexistent_job(self, test_client):
        r = test_client.delete("/api/scheduled/nonexistent-job-id")
        assert r.status_code == 404


# ===========================================================================
# Movements
# ===========================================================================
class TestMovements:
    def test_get_pending_movements(self, test_client):
        r = test_client.get("/api/movements/pending")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_recent_movements(self, test_client):
        r = test_client.get("/api/movements/recent")
        assert r.status_code == 200

    def test_pending_filtered_by_type(self, test_client):
        r = test_client.get("/api/movements/pending?type=juki")
        assert r.status_code == 200


# ===========================================================================
# Global validation error handler
# ===========================================================================
class TestValidationErrorHandler:
    def test_returns_structured_error(self, test_client):
        r = test_client.post("/api/check_reel", json={"line_id": "not-a-number"})
        assert r.status_code == 422
        body = r.json()
        assert body["status"] == "error"
        assert "errores" in body
