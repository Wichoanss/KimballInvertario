import sqlite3
import config
from logger_setup import setup_logger

logger = setup_logger("SmartRackDatabase")

def get_db_connection():
    conn = sqlite3.connect(config.DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def init_db():
    with get_db_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS reels (
            code TEXT PRIMARY KEY,
            itemcode TEXT NOT NULL,
            qty REAL NOT NULL,
            rack TEXT NOT NULL,
            stockcell TEXT DEFAULT '',
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            rack_ids TEXT NOT NULL
        );
        """)
        
        # Migration for stockcell if needed
        try:
            conn.execute("ALTER TABLE reels ADD COLUMN stockcell TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Ya existe la columna

        # Insert some default lines if empty
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM lines")
        if cursor.fetchone()["count"] == 0:
            lines = [("L1", "1"), ("L2", "2"), ("L3", "3"), ("L4-R", "4"), ("L4-L", "5")]
            conn.executemany("INSERT INTO lines (name, rack_ids) VALUES (?, ?)", lines)
        
        conn.commit()

def upsert_reels(reels_data, rack_id):
    """
    reels_data is a list of dicts: [{'code': '...', 'itemcode': '...', 'qty': 100}]
    This function will update/insert the reels for this rack, 
    and REMOVE any reel in this rack that was not found in the reels_data.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        current_codes = [r['code'] for r in reels_data]
        
        # 1. Start Transaction & Upsert updated/new reels
        for reel in reels_data:
            cursor.execute("""
                INSERT INTO reels (code, itemcode, qty, rack, stockcell, last_updated)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(code) DO UPDATE SET 
                    itemcode=excluded.itemcode, 
                    qty=excluded.qty, 
                    rack=excluded.rack,
                    stockcell=excluded.stockcell,
                    last_updated=CURRENT_TIMESTAMP
            """, (reel['code'], reel['itemcode'], reel['qty'], rack_id, reel.get('stockcell', '')))
            
        # 2. Delete reels in THIS rack that are no longer present
        if current_codes:
            placeholders = ",".join("?" * len(current_codes))
            # Delete from reels where rack = rack_id AND code NOT IN (current_codes)
            cursor.execute(f"DELETE FROM reels WHERE rack = ? AND code NOT IN ({placeholders})", [rack_id] + current_codes)
        else:
            # If empty, delete all reels from this rack
            cursor.execute("DELETE FROM reels WHERE rack = ?", (rack_id,))
            
        conn.commit()

def get_all_reels():
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM reels ORDER BY last_updated DESC")
        return [dict(r) for r in cursor.fetchall()]

def get_all_lines():
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM lines ORDER BY name ASC")
        return [dict(r) for r in cursor.fetchall()]

def create_or_update_line(name, rack_ids):
    with get_db_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO lines (name, rack_ids) VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET rack_ids=excluded.rack_ids
        """, (name, rack_ids))
        conn.commit()
        logger.info(f"Línea configurada/actualizada: {name} -> Racks: {rack_ids}")
        return cursor.lastrowid

def delete_line(id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM lines WHERE id = ?", (id,))
        conn.commit()
        logger.info(f"Línea con ID [{id}] fue eliminada del sistema.")

def check_itemcode_availability(itemcode: str, line_id: int, exclude_codes: list = None):
    """
    Busca un itemcode en la BD. Devuelve el de MENOR cantidad primero.
    Excluye los códigos físicos indicados en exclude_codes.
    """
    if exclude_codes is None:
        exclude_codes = []
    
    # Normalizar búsqueda
    itemcode = itemcode.strip().upper()

    with get_db_connection() as conn:
        cursor = conn.execute("SELECT rack_ids FROM lines WHERE id = ?", (line_id,))
        line = cursor.fetchone()
        if not line:
            return {"status": "error", "message": "Línea no encontrada"}

        rack_ids = [str(r).strip() for r in line["rack_ids"].split(",")]

        # Query base: buscar por itemcode ignorando mayúsculas/minúsculas
        # y excluyendo los ya añadidos al buffer
        query = """
            SELECT code, itemcode, qty, rack, stockcell
            FROM reels
            WHERE UPPER(itemcode) = ?
        """
        params = [itemcode]
        
        if exclude_codes:
            placeholders = ",".join("?" * len(exclude_codes))
            query += f" AND code NOT IN ({placeholders})"
            params.extend(exclude_codes)
            
        query += " ORDER BY qty ASC"

        cursor = conn.execute(query, params)
        reels = [dict(r) for r in cursor.fetchall()]

        if not reels:
            return {"status": "not_found"}

        # Priorizar el de menor cantidad dentro de la línea correcta
        for r in reels:
            if str(r["rack"]) in rack_ids:
                return {"status": "in_line", "reel": r}

        # No está en esta línea — devolver el de menor qty de cualquier rack
        return {"status": "other_rack", "reel": reels[0]}
