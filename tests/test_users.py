import pytest
import uuid
import datetime

def test_create_user_success(test_client):
    # Setup master key
    import main
    mtoken = "m_" + uuid.uuid4().hex
    main.config_tokens[mtoken] = datetime.datetime.now().timestamp() + 3600
    
    username = f"new_op_{uuid.uuid4().hex[:6]}"
    res = test_client.post("/admin/users", json={"username": username}, headers={"X-Master-Key": mtoken})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["username"] == username
    assert data["api_key"].startswith("sr_")

def test_create_user_short_name(test_client):
    import main
    mtoken = "m_" + uuid.uuid4().hex
    main.config_tokens[mtoken] = datetime.datetime.now().timestamp() + 3600

    res = test_client.post("/admin/users", json={"username": "ab"}, headers={"X-Master-Key": mtoken})
    assert res.status_code == 400

def test_create_user_duplicate(test_client):
    import main
    mtoken = "m_" + uuid.uuid4().hex
    main.config_tokens[mtoken] = datetime.datetime.now().timestamp() + 3600

    username = "duplicate_user"
    test_client.post("/admin/users", json={"username": username}, headers={"X-Master-Key": mtoken})
    res = test_client.post("/admin/users", json={"username": username}, headers={"X-Master-Key": mtoken})
    assert res.status_code == 400
    assert "ya existe" in res.json()["detail"].lower()

def test_get_users(test_client, api_user_key):
    # api_user_key already creates a user
    import main
    mtoken = "m_" + uuid.uuid4().hex
    main.config_tokens[mtoken] = datetime.datetime.now().timestamp() + 3600

    res = test_client.get("/admin/users", headers={"X-Master-Key": mtoken})
    assert res.status_code == 200
    users = res.json()
    assert len(users) >= 1
    # Check if the user from api_user_key (or any user) exists
    assert any(u["username"].startswith("test_fixture_user_") for u in users)

def test_delete_user(test_client):
    import main
    mtoken = "m_" + uuid.uuid4().hex
    main.config_tokens[mtoken] = datetime.datetime.now().timestamp() + 3600
    
    username = "to_delete"
    test_client.post("/admin/users", json={"username": username}, headers={"X-Master-Key": mtoken})
    res = test_client.delete(f"/admin/users/{username}", headers={"X-Master-Key": mtoken})
    assert res.status_code == 200
    
    # Verify soft delete (filtered in get_api_users)
    res_list = test_client.get("/admin/users", headers={"X-Master-Key": mtoken})
    users = res_list.json()
    assert username not in [u["username"] for u in users]

def test_regenerate_api_key(test_client):
    import main
    mtoken = "m_" + uuid.uuid4().hex
    main.config_tokens[mtoken] = datetime.datetime.now().timestamp() + 3600
    
    username = "regen_user"
    create_res = test_client.post("/admin/users", json={"username": username}, headers={"X-Master-Key": mtoken})
    old_key = create_res.json()["api_key"]
    
    res = test_client.post(f"/admin/users/{username}/regenerate", headers={"X-Master-Key": mtoken})
    assert res.status_code == 200
    data = res.json()
    new_key = data["api_key"]
    
    assert new_key != old_key
    assert new_key.startswith("sr_")
