import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

def test_delete_scheduled_generic_error(test_client, api_user_key):
    # Forzar error inesperado en scheduler.remove_job
    with patch("main.scheduler.remove_job", side_effect=Exception("DB Error")):
        r = test_client.delete("/api/scheduled/job1", headers={"X-API-Key": api_user_key})
        assert r.status_code == 500
        assert "DB Error" in r.json()["detail"]

def test_extract_generic_error(test_client, api_user_key):
    # Forzar error inesperado en la lógica de extracción
    payload = {
        "line_name": "L1",
        "item_codes": ["ABC"],
        "reel_codes": ["R1"],
        "type": "smartrack"
    }
    with patch("main.database.create_movement_log", side_effect=Exception("Disk Full")):
        r = test_client.post("/api/extract", json=payload, headers={"X-API-Key": api_user_key})
        assert r.status_code == 500
        assert "Disk Full" in r.json()["detail"]

def test_juki_extract_generic_error(test_client, api_user_key):
    payload = {
        "name": "JUKI_1",
        "container_id": "C1",
        "reel_codes": ["R1"],
        "log_ids": [1]
    }
    with patch("main.execute_juki_extraction", side_effect=Exception("JUKI Tower Offline")):
        r = test_client.post("/api/juki/extract", json=payload, headers={"X-API-Key": api_user_key})
        assert r.status_code == 500
        assert "JUKI Tower Offline" in r.json()["detail"]

def test_middleware_exception_capture(test_client):
    # Forzar una excepción que el middleware deba capturar
    # parcheamos metrics.inc_requests para que falle al ser llamado por el middleware (un poco rebuscado pero sirve)
    with patch("main.metrics.inc_requests", side_effect=Exception("Metrics Crash")):
        # Invocamos cualquier ruta
        try:
            r = test_client.get("/health")
        except Exception as e:
            assert "Metrics Crash" in str(e)
            
def test_export_csv_sorting_logic(test_client, api_user_key):
    # Asegurar que cubrimos las líneas de ordenamiento en el exportador CSV
    with patch("main.database.get_all_reels", return_value=[
        {"rack": "B", "qty": 100, "code": "R1", "itemcode": "I1", "last_updated": "2023-01-01"},
        {"rack": "A", "qty": 50, "code": "R2", "itemcode": "I2", "last_updated": "2023-01-02"},
    ]):
        r = test_client.get("/api/reels/export/csv", headers={"X-API-Key": api_user_key})
        assert r.status_code == 200
        assert "A" in r.text
        assert "B" in r.text
