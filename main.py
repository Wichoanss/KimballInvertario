import os
import sys
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta

import config
import database
from poller import fetch_and_update_reels, execute_extraction
from logger_setup import setup_logger

logger = setup_logger("SmartRackServer")


# Models
class CodeCheckRequest(BaseModel):
    itemcode: str
    line_id: int
    exclude_codes: List[str] = []

class ExtractRequest(BaseModel):
    line_name: str
    item_codes: List[str]  # These are the original part numbers/itemcodes, for naming
    reel_codes: List[str]  # The actual reel codes to extract
    delay_minutes: int = 0

# Setup Scheduler Lifecycle
scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    database.init_db()
    
    # Start Polling
    scheduler.add_job(fetch_and_update_reels, 'interval', seconds=config.POLL_INTERVAL_SECONDS)
    # Fire once immediately
    scheduler.add_job(fetch_and_update_reels)
    scheduler.start()
    
    yield
    
    # Shutdown
    scheduler.shutdown()

app = FastAPI(title="SmartRack Inventario", lifespan=lifespan)

# Return the HTML template
@app.get("/", response_class=HTMLResponse)
async def get_index():
    # Detect if we are running in a PyInstaller bundle
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
        
    template_path = os.path.join(base_path, "templates", "index.html")
    
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

# APIs
@app.get("/api/reels")
def api_get_reels():
    return database.get_all_reels()

@app.get("/api/lines")
def api_get_lines():
    return database.get_all_lines()

@app.post("/api/lines")
def api_create_line(payload: dict):
    name = payload.get("name")
    rack_ids = payload.get("rack_ids")
    if not name or not rack_ids:
        raise HTTPException(status_code=400, detail="Missing name or rack_ids")
    database.create_or_update_line(name, rack_ids)
    return {"status": "success"}

@app.delete("/api/lines/{line_id}")
def api_delete_line(line_id: int):
    database.delete_line(line_id)
    return {"status": "success"}

@app.post("/api/check_reel")
def api_check_reel(req: CodeCheckRequest):
    result = database.check_itemcode_availability(req.itemcode, req.line_id, req.exclude_codes)
    if result.get("status") == "in_line":
        return {"found": True, "exact": True, "reel": result["reel"]}
    elif result.get("status") == "other_rack":
        return {"found": True, "exact": False, "reel": result["reel"]}
    else:
        return {"found": False, "message": "Rollo no está en ningún rack disponible"}

@app.post("/api/extract")
def api_extract(req: ExtractRequest):
    if not req.reel_codes:
        logger.warning(f"Intento de extracción fallido por buffer vacío. Línea: {req.line_name}")
        raise HTTPException(status_code=400, detail="No reel codes provided")
    
    # Name format logic
    current_time = datetime.now().strftime("%b/%d/%Y-%H:%M")
    
    if len(req.item_codes) == 1:
        name = f"{req.item_codes[0]}_{req.line_name}_{current_time}"
    else:
        name = f"Multi_{req.line_name}_{current_time}"
        
    delay_mins = req.delay_minutes
    if delay_mins > 0:
        run_date = datetime.now() + timedelta(minutes=delay_mins)
        job_id = f"ext_{name}_{int(datetime.now().timestamp())}"
        
        # Schedule it
        scheduler.add_job(
            execute_extraction, 
            'date', 
            run_date=run_date, 
            args=[name, req.reel_codes],
            id=job_id,
            name=name
        )
        logger.info(f"PROGRAMADA: Extracción para {name} a las {run_date}")
        return {"status": "success", "message": f"Extracción de {len(req.reel_codes)} rollos programada para las {run_date.strftime('%H:%M:%S')}"}
        
    logger.info(f"OPERADOR: Solicitando extracción INMEDIATA de {len(req.reel_codes)} rollos. Línea: {req.line_name}. Nombre API: {name}.")
    
    success, message = execute_extraction(name, req.reel_codes)
    if success:
        logger.info(f"ÉXITO: Extracción lanzada correctamente ({name}).")
        return {"status": "success", "message": "Extracción Inmediata solicitada con éxito"}
    else:
        logger.error(f"FALLO en Extracción ({name}): {message}")
        raise HTTPException(status_code=500, detail=message)

@app.get("/api/scheduled")
def api_get_scheduled():
    jobs = scheduler.get_jobs()
    job_list = []
    for job in jobs:
        # Ignore the internal polling job
        if job.name == 'fetch_and_update_reels': continue
        
        job_list.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.strftime('%Y-%m-%d %H:%M:%S') if job.next_run_time else "Pendiente"
        })
    return job_list

@app.delete("/api/scheduled/{job_id}")
def api_delete_scheduled(job_id: str):
    try:
        scheduler.remove_job(job_id)
        logger.info(f"CANCELADA: Extracción programada {job_id} fue cancelada por el usuario.")
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail="Trabajo no encontrado o ya ejecutado")

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    uvicorn.run(app, host="0.0.0.0", port=4500)
