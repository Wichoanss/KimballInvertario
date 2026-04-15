import os
import sys
import uuid
import uvicorn
import csv
import io
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.base import JobLookupError
from datetime import datetime, timedelta

import time

import config
import database
from database import check_idempotency, begin_idempotency, complete_idempotency
from poller import fetch_and_update_reels, execute_extraction, fetch_juki_reels, execute_juki_extraction
from logger_setup import setup_logger, set_request_id
from resilience import smartrack_cb
from metrics import metrics
from schemas import (
    AuthRequest, CodeCheckRequest, ExtractRequest, JukiExtractRequest, CreateLineRequest,
    HealthResponse, StatusResponse, CheckReelResponse, ScheduledJobResponse,
)

logger = setup_logger("SmartRackServer")


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------
scheduler = BackgroundScheduler(
    job_defaults={"misfire_grace_time": 60}
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Arranque ---
    config.validate_production_config()  # Validar seguridad SAFE_MODE antes de tocar DB
    database.init_db()
    database.cleanup_database()  # Ejecutar limpieza al iniciar
    logger.info(
        "SmartRack arrancando",
        extra={"port": config.SERVER_PORT, "log_level": config.LOG_LEVEL, "db": config.DB_NAME}
    )

    scheduler.add_job(fetch_and_update_reels, 'interval', seconds=config.POLL_INTERVAL_SECONDS, id='poller')
    scheduler.add_job(fetch_juki_reels, 'interval', seconds=config.POLL_INTERVAL_SECONDS, id='poller_juki')
    scheduler.add_job(database.cleanup_database, 'interval', hours=1, id='db_cleanup')
    scheduler.add_job(fetch_and_update_reels, id='poller_init')
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
# Middleware — inyecta request_id en cada peticion HTTP
# Aparece en TODOS los logs JSON emitidos durante ese request (campo "rid")
# ---------------------------------------------------------------------------
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
        process_time_ms = (time.perf_counter() - start_time) * 1000
        is_error = response.status_code >= 400
        metrics.inc_requests(process_time_ms, is_error)
        return response
    except Exception:
        process_time_ms = (time.perf_counter() - start_time) * 1000
        metrics.inc_requests(process_time_ms, is_error=True)
        raise

# ---------------------------------------------------------------------------
# Middleware — inyecta request_id en cada peticion HTTP
# Aparece en TODOS los logs JSON emitidos durante ese request (campo "rid")
# ---------------------------------------------------------------------------
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
    set_request_id(rid)
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid   # cliente puede correlacionar
    return response


# ---------------------------------------------------------------------------
# Manejador global de errores de validacion (Pydantic)
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"campo": " -> ".join(str(loc) for loc in err["loc"]), "error": err["msg"]}
        for err in exc.errors()
    ]
    logger.warning(
        f"Validacion fallida en {request.url.path}",
        extra={"path": request.url.path, "errors": errors, "method": request.method}
    )
    return JSONResponse(
        status_code=422,
        content={"status": "error", "detail": "Datos de entrada inválidos", "errores": errors},
    )


# ---------------------------------------------------------------------------
# Auth Config Global State
# ---------------------------------------------------------------------------
config_tokens = {}  # token (str) -> timestamp (float)

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
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "circuit_breaker": smartrack_cb.status(),
    }


@app.get("/metrics")
def api_get_metrics():
    """Expone métricas internas del sistema para observabilidad."""
    return metrics.get_metrics_snapshot()


@app.get("/api/health/circuit-breaker")
def api_circuit_breaker_status():
    """Estado actual del Circuit Breaker para monitoreo por operaciones de IT."""
    return smartrack_cb.status()


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
def api_create_line(req: CreateLineRequest):
    database.create_or_update_line(req.name, req.rack_ids)
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
    # --- Idempotencia ---
    idem_key = req.idempotency_key or str(uuid.uuid4())  # auto si cliente no envía
    try:
        cached = check_idempotency(idem_key)
        if cached is not None:
            return cached
    except RuntimeError:
        raise HTTPException(status_code=409, detail="Operación duplicada en vuelo. Reintenta en unos segundos.")

    begin_idempotency(idem_key, "/api/extract")

    name = (f"{req.item_codes[0]}_{req.line_name}"
            if len(req.item_codes) == 1
            else f"MULTIPLE_{req.line_name}")

    try:
        if req.type == "juki":
            database.create_movement_log("juki", req.line_name, req.reel_codes, req.container_id, req.urgency, req.item_codes)
            metrics.inc_extractions(len(req.reel_codes))
            logger.info(
                "Pedido JUKI encolado",
                extra={"line": req.line_name, "reels": len(req.reel_codes), "urgency": req.urgency, "idem_key": idem_key[:8]}
            )
            result = {"status": "success", "message": "Pedido encolado en el panel del operador JUKI p/ su extracción"}
            complete_idempotency(idem_key, result)
            return result

        # --- Flujo SmartRack ---
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
            logger.info(
                "Extraccion programada",
                extra={"ext_name": name, "reels": len(req.reel_codes), "run_at": run_date.strftime('%H:%M:%S'), "job_id": job_id}
            )
            result = {
                "status": "success",
                "message": f"Extracción de {len(req.reel_codes)} rollos programada para las {run_date.strftime('%H:%M:%S')}"
            }
            complete_idempotency(idem_key, result)
            return result

        logger.info(
            "Extraccion inmediata solicitada",
            extra={"ext_name": name, "reels": len(req.reel_codes), "line": req.line_name}
        )
        success, message = execute_extraction(name, req.reel_codes, True)
        if success:
            metrics.inc_extractions(len(req.reel_codes))
            logger.info("Extraccion completada con exito", extra={"ext_name": name})
            result = {"status": "success", "message": "Extracción inmediata solicitada con éxito"}
            complete_idempotency(idem_key, result)
            return result

        logger.error("Extraccion fallida", extra={"ext_name": name, "reason": message})
        complete_idempotency(idem_key, {"status": "error", "message": message}, success=False)
        raise HTTPException(status_code=500, detail=message)

    except HTTPException:
        raise  # re-lanzar HTTPExceptions sin marcar como 'failed'
    except Exception as e:
        complete_idempotency(idem_key, {"status": "error", "message": str(e)}, success=False)
        logger.error(f"Error inesperado en /api/extract: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

@app.post("/api/juki/extract")
def api_juki_extract(req: JukiExtractRequest):
    # --- Idempotencia ---
    idem_key = req.idempotency_key or str(uuid.uuid4())
    try:
        cached = check_idempotency(idem_key)
        if cached is not None:
            return cached
    except RuntimeError:
        raise HTTPException(status_code=409, detail="Operación JUKI duplicada en vuelo. Reintenta en unos segundos.")

    begin_idempotency(idem_key, "/api/juki/extract")

    try:
        success, message = execute_juki_extraction(req.name, req.container_id, req.reel_codes)
        if success:
            metrics.inc_extractions(len(req.reel_codes))
            for log_id in req.log_ids:
                database.update_movement_status(log_id, 'extracted')
            result = {"status": "success"}
            complete_idempotency(idem_key, result)
            return result

        complete_idempotency(idem_key, {"status": "error", "message": message}, success=False)
        raise HTTPException(status_code=500, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        complete_idempotency(idem_key, {"status": "error", "message": str(e)}, success=False)
        logger.error(f"Error inesperado en /api/juki/extract: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
    import multiprocessing
    multiprocessing.freeze_support()   # MUST be first — necesario para PyInstaller

    # Cuando el .exe se compila con console=False no hay consola:
    # redirigir stdout/stderr a devnull para evitar errores internos de uvicorn
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    uvicorn.run(app, host="0.0.0.0", port=config.SERVER_PORT, log_level="warning")