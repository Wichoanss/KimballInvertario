"""
test_database.py — Integration tests para database.py con SQLite temporal.
Verifica CRUD real, migraciones, validación de filas y lógica de idempotencia.
"""
import pytest
import time


# ===========================================================================
# init_db — estructura de tablas
# ===========================================================================
class TestInitDb:
    def test_creates_all_tables(self, temp_db):
        import sqlite3
        conn = sqlite3.connect(temp_db)
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        for t in ("reels", "lines", "juki_reels", "movements_log", "idempotency_keys"):
            assert t in tables, f"Tabla '{t}' no encontrada"

    def test_creates_default_lines(self, temp_db):
        import database
        lines = database.get_all_lines()
        assert len(lines) >= 1

    def test_idempotent_init(self, temp_db):
        """Llamar init_db dos veces no debe fallar ni duplicar líneas."""
        import database
        database.init_db()
        database.init_db()
        lines = database.get_all_lines()
        names = [l["name"] for l in lines]
        assert len(names) == len(set(names)), "Líneas duplicadas tras doble init"


# ===========================================================================
# Reels — upsert y lectura
# ===========================================================================
class TestReels:
    def _sample(self, code="R001", itemcode="ABC", qty=100.0, rack="1"):
        return {"code": code, "itemcode": itemcode, "qty": qty,
                "rack": rack, "stockcell": "Left A/1"}

    def test_upsert_inserts_new_reel(self, temp_db):
        import database
        database.upsert_reels([self._sample()], "1")
        reels = database.get_all_reels()
        assert any(r["code"] == "R001" for r in reels)

    def test_upsert_updates_existing_reel(self, temp_db):
        import database
        database.upsert_reels([self._sample(qty=100.0)], "1")
        database.upsert_reels([self._sample(qty=50.5)], "1")
        reels = database.get_all_reels()
        reel = next(r for r in reels if r["code"] == "R001")
        assert reel["qty"] == 50.5

    def test_upsert_removes_stale_reels(self, temp_db):
        import database
        database.upsert_reels([self._sample("R001"), self._sample("R002")], "1")
        # Segunda llamada solo devuelve R001 → R002 debe borrarse
        database.upsert_reels([self._sample("R001")], "1")
        reels = database.get_all_reels()
        codes = {r["code"] for r in reels}
        assert "R002" not in codes

    def test_get_all_reels_validates_rows(self, temp_db):
        """Filas con qty negativa deben ser coercionadas a 0."""
        import database
        database.upsert_reels([self._sample(qty=-10.0)], "1")
        reels = database.get_all_reels()
        reel = next((r for r in reels if r["code"] == "R001"), None)
        assert reel is not None
        assert reel["qty"] >= 0.0


# ===========================================================================
# Líneas — CRUD
# ===========================================================================
class TestLines:
    def test_create_and_get_line(self, temp_db):
        import database
        database.create_or_update_line("TEST-L", "10,11")
        lines = database.get_all_lines()
        assert any(l["name"] == "TEST-L" for l in lines)

    def test_update_existing_line(self, temp_db):
        import database
        database.create_or_update_line("TEST-L", "10")
        database.create_or_update_line("TEST-L", "10,11,12")
        lines = database.get_all_lines()
        line = next(l for l in lines if l["name"] == "TEST-L")
        assert "12" in line["rack_ids"]

    def test_delete_line(self, temp_db):
        import database
        database.create_or_update_line("DEL-L", "99")
        lines = database.get_all_lines()
        line_id = next(l["id"] for l in lines if l["name"] == "DEL-L")
        database.delete_line(line_id)
        lines_after = database.get_all_lines()
        assert not any(l["name"] == "DEL-L" for l in lines_after)


# ===========================================================================
# MovementsLog — creación y lectura
# ===========================================================================
class TestMovementsLog:
    def test_create_and_get_pending(self, temp_db):
        import database
        database.create_movement_log("smartrack", "L1", ["R001", "R002"], "", 3, ["ABC"])
        pending = database.get_pending_movements("smartrack")
        assert len(pending) >= 1
        assert pending[0]["target_line"] == "L1"

    def test_filter_by_type(self, temp_db):
        import database
        database.create_movement_log("smartrack", "L1", ["R1"], "", 1, [])
        database.create_movement_log("juki",      "L2", ["R2"], "C1", 5, [])
        smartrack = database.get_pending_movements("smartrack")
        juki      = database.get_pending_movements("juki")
        assert all(m["type"] == "smartrack" for m in smartrack)
        assert all(m["type"] == "juki"      for m in juki)

    def test_update_status(self, temp_db):
        import database
        log_id = database.create_movement_log("smartrack", "L1", ["R1"], "", 1, [])
        database.update_movement_status(log_id, "extracted")
        pending = database.get_pending_movements("smartrack")
        assert not any(m["id"] == log_id for m in pending)

    def test_get_recent_movements(self, temp_db):
        import database
        for i in range(5):
            database.create_movement_log("smartrack", f"L{i}", [f"R{i}"], "", 1, [])
        recent = database.get_recent_movements(3)
        assert len(recent) == 3


# ===========================================================================
# Idempotencia
# ===========================================================================
class TestIdempotency:
    def test_new_key_returns_none(self, temp_db):
        import database
        result = database.check_idempotency("new-key-123")
        assert result is None

    def test_begin_marks_processing(self, temp_db):
        import database
        import sqlite3
        database.begin_idempotency("key-abc", "/api/extract")
        conn = sqlite3.connect(temp_db)
        row = conn.execute(
            "SELECT status FROM idempotency_keys WHERE idem_key = ?", ("key-abc",)
        ).fetchone()
        conn.close()
        assert row[0] == "processing"

    def test_processing_raises_runtime_error(self, temp_db):
        import database
        database.begin_idempotency("key-dup", "/api/extract")
        with pytest.raises(RuntimeError, match="duplicate_in_flight"):
            database.check_idempotency("key-dup")

    def test_complete_stores_response(self, temp_db):
        import database
        database.begin_idempotency("key-done", "/api/extract")
        database.complete_idempotency("key-done", {"status": "success"}, success=True)
        cached = database.check_idempotency("key-done")
        assert cached == {"status": "success"}

    def test_failed_key_allows_retry(self, temp_db):
        import database
        database.begin_idempotency("key-fail", "/api/extract")
        database.complete_idempotency("key-fail", {"status": "error"}, success=False)
        result = database.check_idempotency("key-fail")
        assert result is None   # 'failed' permite reintentar

    def test_begin_is_idempotent(self, temp_db):
        """Llamar begin dos veces con la misma key no lanza excepción."""
        import database
        database.begin_idempotency("key-x", "/test")
        database.begin_idempotency("key-x", "/test")   # INSERT OR IGNORE → no falla
