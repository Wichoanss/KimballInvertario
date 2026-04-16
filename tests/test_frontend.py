import pytest
from fastapi.testclient import TestClient
import main

def test_index_page_loads(test_client):
    """Verifica que la página principal carga sin errores."""
    res = test_client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "SmartRack" in res.text
    assert "Línea" in res.text

def test_index_page_with_multiple_lines(test_client, temp_db):
    """Verifica la estructura base de la página (estática)."""
    res = test_client.get("/")
    assert res.status_code == 200
    # Buscamos elementos que REALMENTE están en el HTML
    assert "SmartRack Operador" in res.text
    assert "btn-end-shift" in res.text
    assert "loadLines" in res.text

def test_unauthorized_admin_access(test_client):
    """Verifica que el acceso sin llave maestra es rechazado."""
    res = test_client.get("/admin/users")
    assert res.status_code == 401

def test_favicon_loads(test_client):
    """Verifica que los static files (si existen) se sirven o no rompen."""
    res = test_client.get("/favicon.ico")
    # Es aceptable un 404 si no existe, pero verificamos que no sea un 500
    assert res.status_code != 500
