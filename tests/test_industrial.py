import pytest

def test_version_endpoint(test_client):
    r = test_client.get("/version")
    assert r.status_code == 200
    assert "version" in r.json()
    assert r.json()["version"] == "1.6.0"

def test_enhanced_health_endpoint(test_client):
    r = test_client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "checks" in data
    assert "disk_space_gb" in data["checks"]
    assert "database" in data["checks"]
    assert "smartrack_api" in data["checks"]

def test_audit_export_endpoint(test_client):
    # Necesitamos master key para este
    import config
    login = test_client.post("/api/auth/config", json={
        "username": config.CONFIG_USERNAME,
        "password": config.CONFIG_PASSWORD
    })
    token = login.json()["token"]
    
    r = test_client.get("/admin/audit/export", headers={"X-Master-Key": token})
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "auditoria_smartrack" in r.headers["content-disposition"]
