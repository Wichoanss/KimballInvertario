import pytest
import uuid
import database
from fastapi.testclient import TestClient
import main
import schemas.db
from pydantic import ValidationError

def test_extract_idempotency_conflict(test_client, api_user_key):
    """
    Simula un conflicto de idempotencia (operación ya en vuelo).
    """
    idem_key = f"idem_{uuid.uuid4().hex}"
    
    # Marcamos la llave como en vuelo manualmente en la DB
    database.begin_idempotency(idem_key, "/api/extract")
    
    # Intentamos la misma petición
    payload = {
        "item_codes": ["P1"],
        "line_name": "L1",
        "reel_codes": ["R1"],
        "idempotency_key": idem_key
    }
    res = test_client.post("/api/extract", json=payload, headers={"X-API-Key": api_user_key})
    
    # Debe devolver 409 Conflict
    assert res.status_code == 409
    assert "operación duplicada" in res.json()["detail"].lower()

def test_schema_db_validation_error_handling():
    """Prueba que los modelos de DB manejan datos corruptos."""
    # qty inválido (string no convertible) -> debe caer en el except pragma-ed antes
    # Pero ahora sin pragmas, el coerce_qty lo maneja devolviendo 0.0
    
    raw_data = {
        "code": "R1",
        "itemcode": "P1",
        "qty": "BASURA", # fallará float()
        "rack": "1",
        "stockcell": "10101"
    }
    reel = schemas.db.ReelModel.model_validate(raw_data)
    assert reel.qty == 0.0

def test_main_metrics_endpoint_unauthorized(test_client):
    """Verifica que el endpoint de métricas responde (era una de las líneas missing)."""
    # Depende de cómo esté configurado, si no tiene auth debe devolver 200
    res = test_client.get("/metrics")
    assert res.status_code == 200
    assert "requests_total" in res.json()
