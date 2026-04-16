import pytest
import xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock
from poller import login, parse_stockcell, fetch_and_update_reels
from resilience import smartrack_cb, CBState, CircuitBreakerOpenError

def test_fmt_stockcell_edge_cases():
    # Caso 1: Formato corto
    assert parse_stockcell("12") == "12"
    
    # Caso 2: Formato estándar Rack 1
    # "10523" -> clean[:5]="10523" -> side="Left", row=05(E), cell=23 -> "Left E/23"
    assert parse_stockcell("10523") == "Left E/23"
    
    # Caso 3: Formato estándar Rack 2
    # "21005" -> row=10(J), cell=5 -> "Right J/5"
    assert parse_stockcell("21005") == "Right J/5"

def test_login_circuit_breaker_open():
    # Forzar el circuito a OPEN
    smartrack_cb.reset()
    for _ in range(10):
        try:
            with smartrack_cb:
                raise Exception("Fail")
        except:
            pass
    
    assert smartrack_cb.state == CBState.OPEN
    
    with patch("poller.logger") as mock_logger:
        token = login()
        assert token is None
        mock_logger.warning.assert_called()
    
    smartrack_cb.reset()

def test_login_malformed_xml():
    # Simular XML que ET no puede parsear
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"NOT XML"
        
        token = login()
        assert token is None

def test_fetch_reels_token_failure():
    # Simular que el login falla durante el polling inicial
    with patch("poller.login", return_value=None):
        res = fetch_and_update_reels()
        assert res is None

def test_login_missing_token_tag():
    # XML válido pero sin tag <token>
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"<root err='0'></root>"
        
        token = login()
        assert token is None

def test_login_error_from_api():
    # API responde con error explícito
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.content = b"<root err='1' errdesc='Invalid User'></root>"
        
        token = login()
        assert token is None
