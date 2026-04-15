import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_frontend_has_users_management():
    res = client.get("/")
    assert res.status_code == 200
    html = res.text
    
    assert 'Gestión de Usuarios y API Keys' in html
    assert '<h3>Crear Nuevo Usuario</h3>' in html
    assert 'id="conf-user-name"' in html
    assert 'onclick="createApiUser()"' in html
    assert 'id="users-tbody"' in html
    
    assert "async function loadApiUsers()" in html
    assert "async function createApiUser()" in html
    assert "async function deleteApiUser(username)" in html
    assert "async function regenerateApiKey(username)" in html
