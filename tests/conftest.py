"""
conftest.py — Fixtures compartidos por todos los tests.

IMPORTANTE: Los tests usan una DB SQLite temporal (en memoria o tmp_path),
nunca tocan inventory.db de producción.
"""
import os
import sys
import pytest
import threading
import time
import socket
from contextlib import closing

# ---------------------------------------------------------------------------
# Asegurar que el directorio raíz del proyecto esté en sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Fixture: Mock Server para tests de integración
# ---------------------------------------------------------------------------
def is_port_open(host='127.0.0.1', port=8081):
    """Verifica si el puerto está disponible."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        return sock.connect_ex((host, port)) == 0


@pytest.fixture(scope="session", autouse=True)
def mock_server():
    """Inicia el mock server en un thread separado para los tests de integración."""
    PORT = 8081
    
    # Si el servidor ya está corriendo, usarlo
    if is_port_open():
        yield
        return
    
    # Iniciar el mock server en un thread daemon
    def run_server():
        try:
            from http.server import HTTPServer
            from mock_smartrack_server import MockHandler
            
            server = HTTPServer(('127.0.0.1', PORT), MockHandler)
            server.serve_forever()
        except Exception as e:
            print(f"Error iniciando mock server: {e}", file=sys.stderr)
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Esperar a que el servidor esté listo
    max_attempts = 20
    for _ in range(max_attempts):
        if is_port_open():
            break
        time.sleep(0.5)
    else:
        raise RuntimeError("No se pudo iniciar el mock server en http://127.0.0.1:8081")
    
    yield


# ---------------------------------------------------------------------------
# Fixture: base de datos SQLite temporal
# Se aplica automáticamente a todo test que use `temp_db`
# ---------------------------------------------------------------------------
@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """
    Redirige config.DB_NAME a un archivo temporal, inicializa las tablas
    y devuelve la ruta. La DB se borra al terminar el test.
    """
    import config
    import database

    db_path = str(tmp_path / "test_inventory.db")
    monkeypatch.setattr(config, "DB_NAME", db_path)

    # Reconstruir la conexión con la nueva ruta
    database.init_db()
    yield db_path


# ---------------------------------------------------------------------------
# Fixture: cliente HTTP de FastAPI (sin scheduler ni pollers reales)
# ---------------------------------------------------------------------------
@pytest.fixture()
def test_client(temp_db, monkeypatch):
    """
    TestClient de FastAPI con DB temporal.
    Los jobs del scheduler se reemplazan con mocks para no hacer
    llamadas reales a la API de SmartRack.
    """
    from unittest.mock import MagicMock, patch

    # Desactivar SAFE_MODE para tests para permitir credenciales de prueba/mock
    import config
    monkeypatch.setattr(config, "SAFE_MODE", False)

    # Parchear execute_extraction y fetch_and_update_reels antes de importar main
    with patch("poller.fetch_and_update_reels", return_value=None), \
         patch("poller.fetch_juki_reels",       return_value=None), \
         patch("poller.execute_extraction",      return_value=(True, "Success")), \
         patch("poller.execute_juki_extraction", return_value=(True, "Success")):

        from fastapi.testclient import TestClient
        import main as app_module

        # Asegurar que el scheduler no arranque pollers reales
        with patch.object(app_module.scheduler, "add_job", return_value=MagicMock()), \
             patch.object(app_module.scheduler, "start",   return_value=None), \
             patch.object(app_module.scheduler, "shutdown",return_value=None):

            with TestClient(app_module.app, raise_server_exceptions=True) as client:
                yield client

@pytest.fixture(autouse=True)
def reset_global_state():
    """Limpia el estado global entre tests para evitar polución."""
    import poller
    from resilience import smartrack_cb
    poller.auth_token = None
    smartrack_cb.reset()
    yield


@pytest.fixture()
def api_user_key(test_client):
    """Crea un usuario API de prueba y devuelve su llave."""
    import main
    import uuid
    import datetime
    
    # Bypass master key login for fixture setup
    token = "test_master_token_" + uuid.uuid4().hex
    main.config_tokens[token] = datetime.datetime.now().timestamp() + 3600
    
    username = f"test_fixture_user_{uuid.uuid4().hex[:6]}"
    res = test_client.post("/admin/users", 
                           json={"username": username, "api_key": "fixture-key-" + uuid.uuid4().hex[:4]}, 
                           headers={"X-Master-Key": token})
    return res.json()["api_key"]

