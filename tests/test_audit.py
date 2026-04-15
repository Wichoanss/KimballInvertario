import pytest
import uuid
import datetime

def test_audit_log_created_on_extract(test_client, api_user_key):
    import main
    # Setup master key for reading logs
    mtoken = "m_audit_" + uuid.uuid4().hex
    main.config_tokens[mtoken] = datetime.datetime.now().timestamp() + 3600

    idem_key = str(uuid.uuid4())
    test_client.post("/api/extract", headers={"X-API-Key": api_user_key}, json={
        "line_name": "L_TEST_AUDIT", "item_codes": ["PN1"], "reel_codes": ["R1", "R2", "R3"], "delay_minutes": 0, "type": "smartrack",
        "idempotency_key": idem_key
    })
    
    # Leer auditoría
    res = test_client.get("/admin/audit/extractions", headers={"X-Master-Key": mtoken})
    assert res.status_code == 200
    logs = res.json()
    assert len(logs) >= 1
    # Check that at least one log exists (could be from fixture user creation too)
    assert any(log["endpoint"] == "/api/extract" for log in logs)

def test_audit_logs_pagination(test_client):
    import main
    mtoken = "m_pag_" + uuid.uuid4().hex
    main.config_tokens[mtoken] = datetime.datetime.now().timestamp() + 3600
    
    res = test_client.get("/admin/audit/extractions?limit=1", headers={"X-Master-Key": mtoken})
    assert res.status_code == 200
    assert len(res.json()) <= 1
