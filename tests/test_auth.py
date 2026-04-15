import pytest
import uuid
import datetime

def test_extract_without_api_key(test_client):
    res = test_client.post("/api/extract", json={
        "line_name": "L1", "item_codes": ["PN-123"], "reel_codes": ["R-123"], "delay_minutes": 0, "type": "smartrack"
    })
    assert res.status_code == 401
    assert "X-API-Key" in res.json()["detail"]

def test_extract_with_invalid_api_key(test_client):
    res = test_client.post("/api/extract", headers={"X-API-Key": "sr_fake_key_123"}, json={
        "line_name": "L1", "item_codes": ["PN-123"], "reel_codes": ["R-123"], "delay_minutes": 0, "type": "smartrack"
    })
    assert res.status_code == 401

def test_juki_extract_security(test_client, api_user_key):
    # Sin llave
    res1 = test_client.post("/api/juki/extract", json={"name": "test", "container_id": "C1", "reel_codes": ["R1"]})
    assert res1.status_code == 401
    
    # Con llave inválida
    res2 = test_client.post("/api/juki/extract", headers={"X-API-Key": "bad"}, json={"name": "test", "container_id": "C1", "reel_codes": ["R1"]})
    assert res2.status_code == 401

    # Con llave válida
    res3 = test_client.post("/api/juki/extract", headers={"X-API-Key": api_user_key}, json={"name": "test", "container_id": "C1", "reel_codes": ["R1"], "log_ids": [1, 2]})
    assert res3.status_code in (200, 500)

def test_admin_endpoints_without_master_key(test_client):
    res = test_client.get("/admin/users")
    assert res.status_code == 401
    assert "X-Master-Key" in res.json()["detail"]
