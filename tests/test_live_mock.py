import pytest
import os
import sqlite3
from unittest.mock import patch
import config
import database
import poller
import main
from resilience import smartrack_cb, CBState

pytestmark = [
    pytest.mark.usefixtures("mock_server"),
    pytest.mark.integration
]

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Base de datos limpia y configuración para tests de integración."""
    # Configurar para hablar con el mock real en localhost:8081
    monkeypatch.setattr(config, "API_BASE_URL", "http://127.0.0.1:8081")
    monkeypatch.setattr(config, "API_USERNAME", "admin")
    monkeypatch.setattr(config, "API_PASSWORD", "admin")
    monkeypatch.setattr(config, "SAFE_MODE", False)
    
    # Resetear circuit breaker para tests de integracion
    with smartrack_cb._lock:
        smartrack_cb._state = CBState.CLOSED
        smartrack_cb._failure_count = 0
        smartrack_cb._success_count = 0
        smartrack_cb._opened_at = 0.0
    poller.auth_token = None
    
    db_path = str(tmp_path / "integration_test.db")
    monkeypatch.setattr(config, "DB_NAME", db_path)
    database.init_db()
    yield db_path

@pytest.mark.usefixtures("mock_server")
@pytest.mark.integration
def test_poller_fetch_from_mock():
    """
    Verifica que el poller realmente puede conectarse al mock, 
    obtener el XML y guardarlo en la DB local temporal.
    """
    # 1. Preparar la DB local con un rack ID válido
    with database.get_db_connection() as conn:
        conn.execute("INSERT INTO lines (name, rack_ids) VALUES (?, ?)", ("LINE-TEST", "1"))
        conn.commit()

    # 2. Ejecutar el poller (sin patches en las funciones de red)
    poller.fetch_and_update_reels()
    
    # 3. Verificar la base de datos local
    with database.get_db_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM reels WHERE rack = ?", ("1",)).fetchone()[0]
    
    print(f"\n[Test] Encontrados {count} rollos en la DB local para el rack 1")
    assert count == 410

@pytest.mark.usefixtures("mock_server")
@pytest.mark.integration
def test_poller_extract_to_mock():
    """
    Verifica que el comando de extraccion llega al mock y este responde OK.
    """
    result, msg = poller.execute_extraction(
        name="INTEGRATION-TEST",
        reel_codes=["REEL-001", "REEL-002"]
    )
    
    assert result is True
    assert "Success" in msg

@pytest.mark.usefixtures("mock_server")
@pytest.mark.integration
def test_juki_poller_fetch_from_mock():
    """
    Verifica el polling de torres JUKI contra el mock.
    """
    # fetch_juki_reels consulta containers 1,2,3,4,5 por defecto
    poller.fetch_juki_reels()
    
    # Verificamos que se hayan cargado datos (el mock devuelve containers 1-5)
    with database.get_db_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM juki_reels").fetchone()[0]
    
    assert count > 0
    print(f"\n[Test] Encontrados {count} rollos JUKI en la DB local")


def test_login_with_mock_server():
    """Verifica que el poller pueda autenticarse y obtener token del mock."""
    poller.auth_token = None
    token = poller.login()
    assert token is not None and token.strip() != ""
    assert isinstance(token, str)


def test_execute_extraction_with_timestamp():
    """Verifica que la extraccion al mock acepte el nombre con timestamp."""
    poller.auth_token = None
    success, message = poller.execute_extraction(
        name="TIMESTAMP-TEST",
        reel_codes=["REEL-001", "REEL-002"],
        append_timestamp=True
    )
    assert success is True
    assert "Success" in message


def test_execute_juki_extraction_success():
    """Verifica que la extraccion JUKI funcione contra el mock."""
    poller.auth_token = None
    success, message = poller.execute_juki_extraction(
        name="JUKI-EXTRACT",
        container_id="1",
        reel_codes=["REEL-010", "REEL-011"]
    )
    assert success is True
    assert "Success" in message
