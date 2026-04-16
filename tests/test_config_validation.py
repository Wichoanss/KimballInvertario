import pytest
import sys
import config
from unittest.mock import patch, MagicMock

def test_validate_production_config_with_errors_not_blocking(monkeypatch, caplog):
    """Verifica que se detecten errores pero no bloquee si SAFE_MODE=False."""
    # Habilitar propagación para que caplog capture el log personalizado
    import logging
    from logger_setup import setup_logger
    logger = setup_logger("SecurityValidator")
    logger.propagate = True
    
    monkeypatch.setattr(config, "SAFE_MODE", False)
    monkeypatch.setattr(config, "API_USERNAME", "USER")
    monkeypatch.setattr(config, "API_PASSWORD", "AUTOSMD")
    monkeypatch.setattr(config, "CONFIG_USERNAME", "admin")
    monkeypatch.setattr(config, "CONFIG_PASSWORD", "admin1234")
    monkeypatch.setattr(config, "LOG_LEVEL", "DEBUG")
    monkeypatch.setattr(config, "API_BASE_URL", "not-a-url")

    # Debería emitir warnings pero no salir
    with caplog.at_level(logging.WARNING, logger="SecurityValidator"):
        config.validate_production_config()
    
    # Usar .messages para evitar problemas de codificación/formato en la comparación
    assert any("Credenciales usadas en API SmartRack son las de fábrica" in m for m in caplog.messages)
    assert any("Credenciales por defecto en Panel Config" in m for m in caplog.messages)
    assert any("LOG_LEVEL configurado como DEBUG" in m for m in caplog.messages)
    assert any("API_BASE_URL inválida" in m for m in caplog.messages)
    assert any("SAFE_MODE desactivado. Iniciando sistema bajo propio riesgo" in m for m in caplog.messages)

def test_validate_production_config_short_passwords(monkeypatch, caplog):
    """Verifica detección de passwords cortos."""
    import logging
    from logger_setup import setup_logger
    logger = setup_logger("SecurityValidator")
    logger.propagate = True

    monkeypatch.setattr(config, "SAFE_MODE", False)
    monkeypatch.setattr(config, "API_PASSWORD", "12")
    monkeypatch.setattr(config, "CONFIG_PASSWORD", "12345")
    
    with caplog.at_level(logging.WARNING, logger="SecurityValidator"):
        config.validate_production_config()
    
    # El SensitiveDataFilter redacta automáticamente partes que parecen passwords
    assert any("API_PASSWORD" in m and "inferior a 3 caracteres" in m for m in caplog.messages)
    assert any("CONFIG_PASSWORD" in m and "débil" in m for m in caplog.messages)

def test_validate_production_config_blocking_safe_mode(monkeypatch):
    """Verifica que el sistema se detenga si SAFE_MODE=True y hay errores."""
    monkeypatch.setattr(config, "SAFE_MODE", True)
    monkeypatch.setattr(config, "LOG_LEVEL", "DEBUG") # Trigger err

    # Capturar la salida de sys.exit(1)
    with pytest.raises(SystemExit) as excinfo:
        # Mocking print to avoid polluting test output
        with patch('sys.stderr', new=MagicMock()):
             config.validate_production_config()
    
    assert excinfo.value.code == 1

def test_validate_production_config_clean(monkeypatch, caplog):
    """Verifica que no hay warnings si la config es robusta."""
    monkeypatch.setattr(config, "API_USERNAME", "real_user")
    monkeypatch.setattr(config, "API_PASSWORD", "robust_password_123")
    monkeypatch.setattr(config, "CONFIG_USERNAME", "admin_real")
    monkeypatch.setattr(config, "CONFIG_PASSWORD", "very_strong_password_secure")
    monkeypatch.setattr(config, "LOG_LEVEL", "INFO")
    monkeypatch.setattr(config, "API_BASE_URL", "http://192.168.1.50:8081")
    
    caplog.clear()
    config.validate_production_config()
    
    # No debería haber errores de seguridad en el log
    assert "Riesgo de seguridad" not in caplog.text
