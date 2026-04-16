import pytest
import sqlite3
from datetime import datetime, timedelta
import database
from database import get_db_connection

def test_check_itemcode_availability_other_rack(temp_db):
    """Verifica que si no hay stock en la línea actual, lo encuentre en otro rack."""
    with get_db_connection() as conn:
        conn.execute("INSERT INTO reels (code, itemcode, qty, rack, stockcell) VALUES (?, ?, ?, ?, ?)",
                     ("REEL_OTHER", "PART_OTHER", 10.0, "99", "990101"))
        conn.commit()

    result = database.check_itemcode_availability("PART_OTHER", 1)
    assert result["status"] == "other_rack"
    assert result["reel"]["code"] == "REEL_OTHER"

def test_check_itemcode_availability_juki(temp_db):
    """Verifica que si no hay stock en SmartRacks, lo busque en JUKI."""
    with get_db_connection() as conn:
        conn.execute("INSERT INTO juki_reels (code, itemcode, qty, container_id) VALUES (?, ?, ?, ?)",
                     ("REEL_JUKI", "PART_JUKI", 5.0, "CT-100"))
        conn.commit()

    result = database.check_itemcode_availability("PART_JUKI", 1)
    assert result["status"] == "juki"
    assert result["reel"]["code"] == "REEL_JUKI"

def test_check_itemcode_availability_not_found(temp_db):
    result = database.check_itemcode_availability("NON_EXISTENT", 1)
    assert result["status"] == "not_found"

def test_database_cleanup_logic(temp_db):
    with get_db_connection() as conn:
        old_date = (datetime.now() - timedelta(days=35)).strftime('%Y-%m-%d %H:%M:%S')
        conn.execute("INSERT INTO movements_log (type, target_line, reel_codes, created_at) VALUES (?, ?, ?, ?)",
                     ("smartrack", "L1", "REEL_OLD", old_date))
        conn.commit()

    database.cleanup_database(keep_logs_days=30)

    with get_db_connection() as conn:
        log_count = conn.execute("SELECT COUNT(*) FROM movements_log WHERE reel_codes='REEL_OLD'").fetchone()[0]
    assert log_count == 0

def test_cleanup_database_exception_handling(monkeypatch):
    def mock_get_db_connection():
        raise Exception("DB Down")
    monkeypatch.setattr(database, "get_db_connection", mock_get_db_connection)
    database.cleanup_database() # No debe fallar
