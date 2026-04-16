import pytest
import requests
from unittest.mock import Mock
import poller
import config

def test_fetch_and_update_reels_token_refresh(temp_db, monkeypatch):
    """Prueba que el poller renueva el token si la API devuelve error 2."""
    def mock_login():
        poller.auth_token = "NEW_VALID_TOKEN"
        return "NEW_VALID_TOKEN"
    
    # Simular respuestas: 1ero falla Token (err='2'), 2do Éxito
    # La API SmartRack devuelve 'v2_reellist'
    responses = [
        Mock(status_code=200, content=b"<v2_reellist err='2' errdesc='Token Expired'/>"),
        Mock(status_code=200, content=b"<v2_reellist count='0' err='0'/>"), # Reintento rack 1
        Mock(status_code=200, content=b"<v2_reellist count='0' err='0'/>"), # Rack 2
        Mock(status_code=200, content=b"<v2_reellist count='0' err='0'/>"), # Rack 3
        Mock(status_code=200, content=b"<v2_reellist count='0' err='0'/>"), # Rack 4
        Mock(status_code=200, content=b"<v2_reellist count='0' err='0'/>"), # Rack 5
    ]
    mock_get = Mock(side_effect=responses)
    
    monkeypatch.setattr(requests, "get", mock_get)
    monkeypatch.setattr(poller, "login", mock_login)
    
    poller.fetch_and_update_reels()
    
    # Debe haber hecho 6 llamadas
    assert mock_get.call_count == 6
    assert poller.auth_token == "NEW_VALID_TOKEN"

def test_poller_juki_xml_error(temp_db, monkeypatch):
    mock_get = Mock(return_value=Mock(status_code=200, content=b"INVALID XML"))
    monkeypatch.setattr(requests, "get", mock_get)
    poller.fetch_juki_reels() # No debe fallar

def test_execute_extraction_api_error(temp_db, monkeypatch):
    # Simular: 1ero Login Éxito, 2do Extracción Error
    responses = [
        Mock(status_code=200, content=b"<root err='0'><token>TEST_TOKEN</token></root>"),
        Mock(status_code=200, content=b"<v3_extractresult err='5' errdesc='Blocked'/>")
    ]
    mock_get = Mock(side_effect=responses)
    monkeypatch.setattr(requests, "get", mock_get)
    
    success, msg = poller.execute_extraction("JOB1", ["R1"], True)
    assert success is False
    assert msg == "Blocked"

def test_poller_network_timeout(temp_db, monkeypatch):
    """Simula un timeout de red y verifica que el poller lo maneja."""
    mock_get = Mock(side_effect=requests.exceptions.Timeout("Read timed out"))
    monkeypatch.setattr(requests, "get", mock_get)
    
    # Debe capturar el error y no explotar
    poller.fetch_and_update_reels()
    assert mock_get.called

def test_poller_network_connection_error(temp_db, monkeypatch):
    """Simula un fallo total de conexión (cable desconectado)."""
    from resilience import smartrack_cb
    smartrack_cb.reset() # Asegurar que empezamos con el circuito CERRADO
    
    mock_get = Mock(side_effect=requests.exceptions.ConnectionError("Failed to establish connection"))
    monkeypatch.setattr(requests, "get", mock_get)
    
    # Probar JUKI directamente
    poller.fetch_juki_reels()
    assert mock_get.called
