import pytest
import uuid
import datetime

def test_idempotency_ignores_auth_on_cached(test_client, api_user_key):
    idem_key = str(uuid.uuid4())
    
    payload = {
        "line_name": "L1", "item_codes": ["PN-TEST"], "reel_codes": ["R-T1"], "delay_minutes": 5, "type": "smartrack",
        "idempotency_key": idem_key
    }
    
    # 1. First call with valid key
    res1 = test_client.post("/api/extract", headers={"X-API-Key": api_user_key}, json=payload)
    assert res1.status_code == 200
    
    # 2. Call WITHOUT key (should fail auth before idempotency)
    res2 = test_client.post("/api/extract", json=payload)
    assert res2.status_code == 401
    
    # 3. Call with valid key again (should return cached)
    res3 = test_client.post("/api/extract", headers={"X-API-Key": api_user_key}, json=payload)
    assert res3.status_code == 200
    assert res3.json() == res1.json()
