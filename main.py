import os
import sys
import uvicorn
import csv
import io
import uuid
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import List
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError
from datetime import datetime, timedelta

import config
import database
from poller import fetch_and_update_reels, execute_extraction, fetch_juki_reels, execute_juki_extraction
from logger_setup import setup_logger

logger = setup_logger("SmartRackServer")


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------
class CodeCheckRequest(BaseModel):
    itemcode: str
    line_id: int
    exclude_codes: List[str] = []

class ExtractRequest(BaseModel):
    line_name: str
    item_codes: List[str]   # Numeros de parte originales (para el nombre)
    reel_codes: List[str]   # Codigos fisicos del reel a extraer
    delay_minutes: int = 0
    type: str = "smartrack" # 'smartrack' o 'juki'
    container_id: str = ""  # Agregado para JUKI
    urgency: int = 1        # 1-5 scale


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
scheduler = BackgroundScheduler(
    job_defaults={"misfire_grace_time": 60}   # Si el job se retrasa hasta 60s, igual lo ejecuta
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Arranque ---
    database.init_db()
    logger.info(f"SmartRack arrancando en puerto {config.SERVER_PORT}")

    scheduler.add_job(fetch_and_update_reels, 'interval', seconds=config.POLL_INTERVAL_SECONDS, id='poller')
    scheduler.add_job(fetch_juki_reels, 'interval', seconds=config.POLL_INTERVAL_SECONDS, id='poller_juki')
    scheduler.add_job(fetch_and_update_reels, id='poller_init')   # Disparo inmediato
    scheduler.add_job(fetch_juki_reels, id='poller_init_juki')
    scheduler.start()

    yield

    # --- Apagado ---
    scheduler.shutdown(wait=False)
    logger.info("SmartRack detenido.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="SmartRack Inventario", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Auth Config Global State
# ---------------------------------------------------------------------------
config_tokens = {} # token (str) -> timestamp (float)

class AuthRequest(BaseModel):
    username: str
    password: str

# ---------------------------------------------------------------------------
# Utilidad: ruta al template compatible con .exe y .py
# ---------------------------------------------------------------------------
def _template_path(filename: str) -> str:
    base = sys._MEIPASS if (getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')) \
           else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "templates", filename)


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.post("/api/auth/config")
def api_auth_config(req: AuthRequest):
    if req.username == config.CONFIG_USERNAME and req.password == config.CONFIG_PASSWORD:
        token = uuid.uuid4().hex
        config_tokens[token] = datetime.now().timestamp()
        return {"status": "ok", "token": token}
    raise HTTPException(status_code=401, detail="Credenciales incorrectas")

@app.get("/api/auth/config/verify")
def api_auth_config_verify(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        return {"valid": False}
    token = authorization.split("Bearer ")[1]
    
    # Limpiar tokens expirados (30 mins = 1800 seg)
    now = datetime.now().timestamp()
    expired = [t for t, ts in config_tokens.items() if now - ts > 1800]
    for t in expired:
        del config_tokens[t]
        
    if token in config_tokens:
        return {"valid": True}
    return {"valid": False}


@app.get("/", response_class=HTMLResponse)
async def get_index():
    with open(_template_path("index.html"), encoding="utf-8") as f:
        return f.read()

@app.get("/towers.html", response_class=HTMLResponse)
async def get_towers():
    with open(_template_path("towers.html"), encoding="utf-8") as f:
        return f.read()


@app.get("/api/reels")
def api_get_reels():
    return database.get_all_reels()

@app.get("/api/juki/reels")
def api_get_juki_reels():
    reels = database.get_all_juki_reels()
    logger.debug(f"API JUKI: Solicitados reels. Enviando {len(reels)} registros.")
    return reels

@app.get("/api/reels/export/csv")
def export_reels_csv():
    reels = database.get_all_reels()
    
    reels.sort(key=lambda r: (r.get('rack', ''), float(r.get('qty', 0.0))))
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Rack', 'Code', 'ItemCode', 'Qty', 'Stockcell', 'Last_Updated'])
    
    for r in reels:
        writer.writerow([
            r.get('rack', ''),
            r.get('code', ''),
            r.get('itemcode', ''),
            r.get('qty', 0.0),
            r.get('stockcell', ''),
            r.get('last_updated', '')
        ])
        
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="inventario_smartrack.csv"'}
    )


@app.get("/api/lines")
def api_get_lines():
    return database.get_all_lines()


@app.post("/api/lines")
def api_create_line(payload: dict):
    name     = payload.get("name", "").strip()
    rack_ids = payload.get("rack_ids", "").strip()
    if not name or not rack_ids:
        raise HTTPException(status_code=400, detail="Faltan campos: name o rack_ids")
    database.create_or_update_line(name, rack_ids)
    return {"status": "success"}


@app.delete("/api/lines/{line_id}")
def api_delete_line(line_id: int):
    database.delete_line(line_id)
    return {"status": "success"}


@app.post("/api/check_reel")
def api_check_reel(req: CodeCheckRequest):
    result = database.check_itemcode_availability(req.itemcode, req.line_id, req.exclude_codes)
    status = result.get("status")
    if status == "in_line":
        return {"found": True,  "exact": True,  "reel": result["reel"], "status": status}
    if status == "other_rack":
        return {"found": True,  "exact": False, "reel": result["reel"], "status": status}
    if status == "juki":
        return {"found": True,  "exact": False, "reel": result["reel"], "status": status}
    return {"found": False, "message": "Rollo no está en ningún rack ni torre disponible"}


@app.post("/api/extract")
def api_extract(req: ExtractRequest):
    if not req.reel_codes:
        logger.warning(f"Extracción fallida — buffer vacío. Línea: {req.line_name}")
        raise HTTPException(status_code=400, detail="No reel codes provided")

    name = (f"{req.item_codes[0]}_{req.line_name}"
            if len(req.item_codes) == 1
            else f"Multi_{req.line_name}")

    if req.type == "juki":
        # Para JUKI, solo guardamos el log de movimiento (pedido) para que el operador lo vea
        database.create_movement_log("juki", req.line_name, req.reel_codes, req.container_id, req.urgency, req.item_codes)
        logger.info(f"OPERADOR: Pedido a JUKI — {len(req.reel_codes)} rollos, línea {req.line_name}, urgencia {req.urgency}")
        return {"status": "success", "message": "Pedido encolado en el panel del operador JUKI p/ su extracción"}

    # --- Flujo SmartRack ---
    # Log movement in DB regardless of extraction type (SmartRack request)
    database.create_movement_log("smartrack", req.line_name, req.reel_codes, "", 1, req.item_codes)

    if req.delay_minutes > 0:
        run_date = datetime.now() + timedelta(minutes=req.delay_minutes)
        job_id   = f"ext_{int(datetime.now().timestamp())}"
        scheduler.add_job(
            execute_extraction,
            'date',
            run_date=run_date,
            args=[name, req.reel_codes, True],
            id=job_id,
            name=f"{name}_{run_date.strftime('%b/%d/%Y-%H:%M')}"
        )
        logger.info(f"PROGRAMADA: {name} — ejecucion a las {run_date.strftime('%H:%M:%S')}")
        return {
            "status": "success",
            "message": f"Extracción de {len(req.reel_codes)} rollos programada para las {run_date.strftime('%H:%M:%S')}"
        }

    logger.info(f"OPERADOR: Extracción INMEDIATA — {len(req.reel_codes)} rollos, línea {req.line_name}, nombre: {name}")
    success, message = execute_extraction(name, req.reel_codes, True)
    if success:
        logger.info(f"ÉXITO: {name}")
        # Could update status to 'extracted', left pending until confirmed if needed.
        return {"status": "success", "message": "Extracción inmediata solicitada con éxito"}

    logger.error(f"FALLO: {name} — {message}")
    raise HTTPException(status_code=500, detail=message)


@app.get("/api/scheduled")
def api_get_scheduled():
    return [
        {
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')
                             if job.next_run_time else "Pendiente"
        }
        for job in scheduler.get_jobs()
        if job.name not in ('fetch_and_update_reels', 'poller_init')
    ]


@app.delete("/api/scheduled/{job_id}", response_model=None)
def api_delete_scheduled(job_id: str):
    try:
        scheduler.remove_job(job_id)
        logger.info(f"CANCELADA: Extracción programada [{job_id}]")
        return {"status": "success"}
    except JobLookupError:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado o ya ejecutado")
    except Exception as e:
        logger.error(f"Error cancelando job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class JukiExtractRequest(BaseModel):
    name: str
    container_id: str
    reel_codes: List[str]
    log_ids: List[int] # To mark these logs as extracted

@app.post("/api/juki/extract")
def api_juki_extract(req: JukiExtractRequest):
    success, message = execute_juki_extraction(req.name, req.container_id, req.reel_codes)
    if success:
        for log_id in req.log_ids:
            database.update_movement_status(log_id, 'extracted')
        return {"status": "success"}
    raise HTTPException(status_code=500, detail=message)

@app.get("/api/movements/pending")
def api_get_pending_movements(type: str = None):
    moves = database.get_pending_movements(type)
    logger.debug(f"API MOVEMENTS: Solicitadas pendientes ({type}). Enviando {len(moves)} registros.")
    return moves

@app.get("/api/movements/recent")
def api_get_recent_movements():
    moves = database.get_recent_movements(25)
    return moves


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    import os
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    import multiprocessing
    multiprocessing.freeze_support()
    uvicorn.run(app, host="0.0.0.0", port=config.SERVER_PORT)