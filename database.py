import sqlite3
import config
from datetime import datetime, timedelta
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
            date_added DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            rack_ids TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS juki_reels (
            code TEXT PRIMARY KEY,
            itemcode TEXT NOT NULL,
            qty REAL NOT NULL,
            container_id TEXT NOT NULL,
            date_added DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS movements_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,          -- 'smartrack' or 'juki'
            target_line TEXT NOT NULL,   
            reel_codes TEXT NOT NULL,    
            item_codes TEXT DEFAULT '',
            container_id TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            urgency INTEGER DEFAULT 1,  -- 1=min, 5=urgent
            due_at DATETIME,            -- Target completion time
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Migration for item_codes if needed
        try:
            conn.execute("ALTER TABLE movements_log ADD COLUMN item_codes TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

        # Migration for stockcell if needed
        try:
            conn.execute("ALTER TABLE reels ADD COLUMN stockcell TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # Ya existe la columna

        # Migration for date_added if needed
        try:
            conn.execute("ALTER TABLE reels ADD COLUMN date_added DATETIME DEFAULT CURRENT_TIMESTAMP")
        except sqlite3.OperationalError:
            pass

        # Migration for urgency if needed
        try:
            conn.execute("ALTER TABLE movements_log ADD COLUMN urgency INTEGER DEFAULT 1")
        except sqlite3.OperationalError:
            pass

        # Migration for due_at if needed
        try:
            conn.execute("ALTER TABLE movements_log ADD COLUMN due_at DATETIME")
        except sqlite3.OperationalError:
            pass

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

def upsert_juki_reels(reels_data):
    """
    reels_data is a list of dicts: [{'code': '...', 'itemcode': '...', 'qty': 100, 'container_id': '1'}]
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        current_codes = [r['code'] for r in reels_data]
        
        for reel in reels_data:
            cursor.execute("""
                INSERT INTO juki_reels (code, itemcode, qty, container_id, last_updated)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(code) DO UPDATE SET 
                    itemcode=excluded.itemcode, 
                    qty=excluded.qty, 
                    container_id=excluded.container_id,
                    last_updated=CURRENT_TIMESTAMP
            """, (reel['code'], reel['itemcode'], reel['qty'], reel['container_id']))
            
        if current_codes:
            placeholders = ",".join("?" * len(current_codes))
            # Optional: We could limit the deletion to containers returned, but if we query all 5 containers at once, 
            # we can just delete anything not in current_codes entirely.
            cursor.execute(f"DELETE FROM juki_reels WHERE code NOT IN ({placeholders})", current_codes)
        else:
            cursor.execute("DELETE FROM juki_reels")
            
        conn.commit()
        logger.info(f"DB JUKI: Upsert de {len(reels_data)} rollos completado.")

def get_all_reels():
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM reels ORDER BY last_updated DESC")
        return [dict(r) for r in cursor.fetchall()]

def get_all_juki_reels():
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM juki_reels ORDER BY container_id ASC, last_updated DESC")
        return [dict(r) for r in cursor.fetchall()]

def create_movement_log(move_type: str, target_line: str, reel_codes: list, container_id: str = '', urgency: int = 1, item_codes: list = None):
    # Calculate due_at based on urgency
    # 5=urgent(now), 4=15m, 3=30m, 2=45m, 1=120m
    offsets = {5: 1, 4: 15, 3: 30, 2: 45, 1: 120}
    offset = offsets.get(urgency, 120)
    due_at = (datetime.now() + timedelta(minutes=offset)).strftime('%Y-%m-%d %H:%M:%S')

    items_str = ",".join(item_codes) if item_codes else ""

    with get_db_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO movements_log (type, target_line, reel_codes, item_codes, container_id, urgency, due_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (move_type, target_line, ",".join(reel_codes), items_str, container_id, urgency, due_at))
        conn.commit()
        return cursor.lastrowid

def get_pending_movements(move_type: str = None):
    with get_db_connection() as conn:
        if move_type:
            cursor = conn.execute("SELECT * FROM movements_log WHERE status = 'pending' AND type = ? ORDER BY created_at ASC", (move_type,))
        else:
            cursor = conn.execute("SELECT * FROM movements_log WHERE status = 'pending' ORDER BY created_at ASC")
        return [dict(r) for r in cursor.fetchall()]

def get_recent_movements(limit: int = 50):
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT * FROM movements_log ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cursor.fetchall()]

def update_movement_status(log_id: int, status: str):
    with get_db_connection() as conn:
        conn.execute("UPDATE movements_log SET status = ? WHERE id = ?", (status, log_id))
        conn.commit()

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
            SELECT code, itemcode, qty, rack, stockcell, date_added
            FROM reels
            WHERE UPPER(itemcode) = ?
        """
        params = [itemcode]
        
        if exclude_codes:
            placeholders = ",".join("?" * len(exclude_codes))
            query += f" AND code NOT IN ({placeholders})"
            params.extend(exclude_codes)
            
        query += " ORDER BY date_added ASC, qty ASC"

        cursor = conn.execute(query, params)
        reels = [dict(r) for r in cursor.fetchall()]


        # Priorizar el de menor cantidad/antiguedad dentro de la línea correcta
        for r in reels:
            if str(r["rack"]) in rack_ids:
                return {"status": "in_line", "reel": r}

        if reels:
            # No está en esta línea — devolver el de cualquier rack (pero no JUKI todavía)
            return {"status": "other_rack", "reel": reels[0]}

        # --- Si no está en SmartRacks, buscar en JUKI ---
        j_query = """
            SELECT code, itemcode, qty, container_id, date_added
            FROM juki_reels
            WHERE UPPER(itemcode) = ?
        """
        j_params = [itemcode]
        if exclude_codes:
            j_query += f" AND code NOT IN ({placeholders})"
            j_params.extend(exclude_codes)
            
        j_query += " ORDER BY date_added ASC, qty ASC"
        
        cursor = conn.execute(j_query, j_params)
        juki_reels = [dict(r) for r in cursor.fetchall()]
        
        if juki_reels:
            return {"status": "juki", "reel": juki_reels[0]}

        return {"status": "not_found"}
