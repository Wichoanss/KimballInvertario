import pytest
import uuid
import datetime

def test_full_e2e_user_flow(test_client):
    import main
    # 0. Setup master key
    master_token = "m_e2e_" + uuid.uuid4().hex
    main.config_tokens[master_token] = datetime.datetime.now().timestamp() + 3600

    # 1. Administrator creates a new API user
    username = f"machine_x_{uuid.uuid4().hex[:4]}"
    api_key_str = f"emp_{uuid.uuid4().hex[:6]}"
    res_create = test_client.post("/admin/users", json={"username": username, "api_key": api_key_str}, headers={"X-Master-Key": master_token})
    assert res_create.status_code == 200
    api_key = res_create.json()["api_key"]
    
    # 2. Machine X attempts to extract WITHOUT the API Key
    extract_payload = {"line_name": "L_TEST_E2E", "item_codes": ["PN"], "reel_codes": ["R1"], "delay_minutes": 0, "type": "smartrack"}
    res_fail = test_client.post("/api/extract", json=extract_payload)
    assert res_fail.status_code == 401
    
    # 3. Machine X sends request WITH the valid API Key
    from unittest.mock import patch
    with patch("main.execute_extraction", return_value=(True, "Success")):
        res_success = test_client.post("/api/extract", headers={"X-API-Key": api_key}, json=extract_payload)
    assert res_success.status_code == 200
    
    # 4. IT Supervisor checks audit logs
    res_audit = test_client.get(f"/admin/audit/extractions?username={username}", headers={"X-Master-Key": master_token})
    assert res_audit.status_code == 200
    logs = res_audit.json()
    assert len(logs) >= 1
    assert logs[0]["username"] == username
    assert logs[0]["success"] == 1

    # 5. Admin regenerates it
    res_rotate = test_client.post(f"/admin/users/{username}/regenerate", headers={"X-Master-Key": master_token})
    assert res_rotate.status_code == 200
    new_api_key = res_rotate.json()["api_key"]
    assert new_api_key != api_key
    
    # 6. Attacker uses old key
    res_hack = test_client.post("/api/extract", headers={"X-API-Key": api_key}, json=extract_payload)
    assert res_hack.status_code == 401
    
    # 7. Machine X is updated with new key
    with patch("main.execute_extraction", return_value=(True, "Success")):
        res_valid2 = test_client.post("/api/extract", headers={"X-API-Key": new_api_key}, json={**extract_payload, "idempotency_key": str(uuid.uuid4())})
    assert res_valid2.status_code == 200
    
    # 8. Admin deletes user
    res_del = test_client.delete(f"/admin/users/{username}", headers={"X-Master-Key": master_token})
    assert res_del.status_code == 200
    
    # 9. Key should not work anymore
    res_dead = test_client.post("/api/extract", headers={"X-API-Key": new_api_key}, json={**extract_payload, "idempotency_key": str(uuid.uuid4())})
    assert res_dead.status_code == 401
