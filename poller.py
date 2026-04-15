import re
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

import config
from database import upsert_reels, upsert_juki_reels, get_db_connection
from logger_setup import setup_logger
from resilience import smartrack_cb, CircuitBreakerOpenError, retry_with_backoff
from metrics import metrics

logger = setup_logger("SmartRackPoller")
auth_token = None

# Params que NUNCA deben aparecer en logs
_SENSITIVE_PARAMS = frozenset({"tkn", "token", "password", "passwd", "api_key"})


def _safe_url(url: str, params: dict | None = None) -> str:
    """Devuelve la URL con parametros sensibles reemplazados por [REDACTED]."""
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        if params:
            for k, v in params.items():
                if k not in _SENSITIVE_PARAMS:
                    qs[k] = [v]
        sanitized = {k: (v if k not in _SENSITIVE_PARAMS else ["[REDACTED]"]) for k, v in qs.items()}
        safe = parsed._replace(query=urlencode(sanitized, doseq=True))
        return urlunparse(safe)
    except Exception:
        return "[URL no disponible]"



# ---------------------------------------------------------------------------
# Decodificador de posicion en rack
# Formato: XRRCC
#   X  = lado    (1=Left, 2=Right)
#   RR = fila    (01->A, 02->B, ... 26->Z)
#   CC = celda   (numero, se quita el cero inicial)
# Ejemplo: 10123 -> Left A/23
#          20312 -> Right C/12
# ---------------------------------------------------------------------------
def parse_stockcell(val: str) -> str:
    if not val:
        return ""
    clean = re.sub(r'[^0-9]', '', val)
    if len(clean) < 5:
        return val  # formato desconocido, devolver original
    clean = clean[:5]

    side = "Left" if clean[0] == "1" else ("Right" if clean[0] == "2" else clean[0])

    try:
        row_num = int(clean[1:3])
        letter  = chr(64 + row_num) if 1 <= row_num <= 26 else str(row_num).zfill(2)
    except ValueError:
        letter = clean[1:3]

    cell = str(int(clean[3:5]))  # quitar cero inicial: 05->5, 23->23
    return f"{side} {letter}/{cell}"


# ---------------------------------------------------------------------------
# Autenticacion
# ---------------------------------------------------------------------------
@retry_with_backoff(max_attempts=3, base_delay=5.0, max_delay=30.0)
def _do_login() -> str | None:
    """Llamada HTTP de login envuelta en circuit breaker. Lanza en fallo."""
    global auth_token
    with smartrack_cb:
        response = requests.get(
            f"{config.API_BASE_URL}/",
            params={"f": "login", "username": config.API_USERNAME, "password": config.API_PASSWORD},
            timeout=10
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)

        if root.get("err", "1") != "0":
            raise RuntimeError(f"Login fallido: {root.get('errdesc', 'Error desconocido')}")

        token_el = root.find(".//token")
        if token_el is None or not token_el.text:
            raise RuntimeError("Token no encontrado en respuesta")

        auth_token = token_el.text.strip()
        return auth_token


def login() -> str | None:
    """Intenta autenticar contra la API. Respeta el circuit breaker."""
    try:
        token = _do_login()
        logger.info("Token de autenticacion obtenido correctamente.")
        return token
    except CircuitBreakerOpenError as e:
        logger.warning(f"Login omitido — {e}")
        return None
    except Exception as e:
        logger.error(f"Login fallido tras todos los reintentos: {e}")
        return None


# ---------------------------------------------------------------------------
# Polling principal
# ---------------------------------------------------------------------------
def fetch_and_update_reels() -> None:
    """Consulta la API por cada rack y actualiza la base de datos."""
    metrics.inc_poller_runs()
    global auth_token
    if not auth_token and not login():
        logger.warning("Ciclo de polling omitido — login fallido.")
        return

    # Leer racks dinamicamente desde las lineas configuradas en BD
    with get_db_connection() as conn:
        rows = conn.execute("SELECT rack_ids FROM lines").fetchall()
    ids = {r.strip() for row in rows for r in row["rack_ids"].split(",")}
    target_racks = sorted(ids) if ids else ["1", "2", "3", "4", "5"]

    for rack_id in target_racks:
        try:
            params = {
                "f": "V2_reel_getlist",
                "filter_smartrackidlist": rack_id,
                "tkn": auth_token
            }
            with smartrack_cb:
                response = requests.get(f"{config.API_BASE_URL}/", params=params, timeout=10)
                response.raise_for_status()
            root = ET.fromstring(response.content)

            # Renovar token si expiro
            if root.get("err") != "0":
                errdesc = root.get("errdesc", "").lower()
                if "token" in errdesc or "auth" in errdesc:
                    logger.warning(f"Token expirado/invalido: {errdesc} — renovando...")
                    if not login():
                        continue
                    params["tkn"] = auth_token
                    with smartrack_cb:
                        response = requests.get(f"{config.API_BASE_URL}/", params=params, timeout=10)
                        response.raise_for_status()
                    root = ET.fromstring(response.content)
                else:
                    logger.error(f"Error de API en rack {rack_id}: {errdesc}")
                    metrics.inc_poller_errors()
                    continue

            reels_data = []
            for reel_info in root.findall(".//v2_reelinfo"):
                code_el     = reel_info.find("code")
                itemcode_el = reel_info.find("itemcode")
                qty_el      = reel_info.find("quantity")
                stockcell_el= reel_info.find("stockcell")

                if code_el is None or not code_el.text:
                    continue

                try:
                    qty_val = float(qty_el.text) if qty_el is not None and qty_el.text else 0.0
                except ValueError:
                    qty_val = 0.0

                stockcell_raw = stockcell_el.text.strip() if stockcell_el is not None and stockcell_el.text else ""

                reels_data.append({
                    "code":      code_el.text.strip(),
                    "itemcode":  itemcode_el.text.strip() if itemcode_el is not None and itemcode_el.text else "",
                    "qty":       qty_val,
                    "stockcell": parse_stockcell(stockcell_raw)
                })

            upsert_reels(reels_data, rack_id)

        except CircuitBreakerOpenError as e:
            logger.warning(f"Polling rack {rack_id} omitido — {e}")
            metrics.inc_poller_errors()
            break  # Si el CB está abierto, no intentar los demás racks
        except Exception as e:
            logger.error(f"Error consultando rack {rack_id}: {e} | URL: {_safe_url(config.API_BASE_URL, {'f': 'V2_reel_getlist', 'filter_smartrackidlist': rack_id})}")
            metrics.inc_poller_errors()


def fetch_juki_reels() -> None:
    """Consulta la API por las torres JUKI y actualiza la base de datos."""
    metrics.inc_poller_runs()
    global auth_token
    if not auth_token and not login():
        logger.warning("Ciclo de polling JUKI omitido — login fallido.")
        return

    try:
        params = {
            "f": "V2_reel_getlist",
            "filter_containeridlist": "1,2,3,4,5",
            "filter_showactive": "true",
            "filter_showusable": "true",
            "tkn": auth_token
        }
        with smartrack_cb:
            response = requests.get(f"{config.API_BASE_URL}/", params=params, timeout=15)
            response.raise_for_status()
        root = ET.fromstring(response.content)

        if root.get("err") != "0":
            errdesc = root.get("errdesc", "").lower()
            if "token" in errdesc or "auth" in errdesc:
                logger.warning(f"Token expirado/invalido JUKI: {errdesc} — renovando...")
                if not login():
                    return
                params["tkn"] = auth_token
                with smartrack_cb:
                    response = requests.get(f"{config.API_BASE_URL}/", params=params, timeout=15)
                    response.raise_for_status()
                root = ET.fromstring(response.content)
            else:
                logger.error(f"Error de API en JUKI: {errdesc}")
                # Log XML for debugging if needed (only if error)
                logger.debug(f"XML Response on error: {response.text[:500]}...")
                return

        def get_text(el, tags):
            """Busca el primer tag que coincida (case-insensitive) y devuelve su texto."""
            for tag in tags:
                # Intentamos buscar el tag exacto y versiones variadas
                found = el.find(tag)
                if found is None: found = el.find(tag.lower())
                if found is None: found = el.find(tag.upper())
                if found is None: found = el.find(tag.capitalize())
                
                if found is not None and found.text:
                    return found.text.strip()
            return ""

        reels_data = []
        # v2_reelinfo suele ser minusculas, pero buscamos flexible
        items = root.findall(".//v2_reelinfo")
        if not items:
            # Reintentamos con un patron mas generico si no encuentra nada
            items = root.findall(".//*") 
            items = [i for i in items if 'reel' in i.tag.lower()]

        for reel_info in items:
            code = get_text(reel_info, ["code", "Code", "UID"])
            itemcode = get_text(reel_info, ["itemcode", "ItemCode", "PartNumber"])
            qty_str = get_text(reel_info, ["quantity", "Quantity", "qty", "Qty", "QtAvailable"])
            container_id = get_text(reel_info, ["container", "containerid", "ContainerID", "container_id", "TowerID"])

            if not code:
                continue
                
            try:
                qty_val = float(qty_str) if qty_str else 0.0
            except ValueError:
                qty_val = 0.0

            reels_data.append({
                "code": code,
                "itemcode": itemcode,
                "qty": qty_val,
                "container_id": container_id
            })

        if reels_data:
            logger.info(f"JUKI Poller: Encontrados {len(reels_data)} rollos en las torres.")
            upsert_juki_reels(reels_data)
        else:
            logger.warning("JUKI Poller: No se encontraron rollos en la respuesta de la API.")
            # Si no hay nada, podria ser que el XML cambio de estructura
            logger.debug(f"Estructura XML recibida (primeros 500 chars): {response.text[:500]}")

    except CircuitBreakerOpenError as e:
        logger.warning(f"Polling JUKI omitido — {e}")
        metrics.inc_poller_errors()
    except Exception as e:
        logger.error(f"Error consultando JUKI: {e}")
        metrics.inc_poller_errors()  # URL no se loggea — contiene tkn

# ---------------------------------------------------------------------------
# Extraccion
# ---------------------------------------------------------------------------
def execute_extraction(name: str, reel_codes: list, append_timestamp: bool = False) -> tuple[bool, str]:
    """Ejecuta V3_extractreels en la API del SmartRack."""
    global auth_token
    if not auth_token and not login():
        return False, "Auth error"

    if append_timestamp:
        name = f"{name}_{datetime.now().strftime('%b/%d/%Y-%H:%M')}"

    try:
        with smartrack_cb:
            response = requests.get(
                f"{config.API_BASE_URL}/",
                params={
                    "f":               "V3_extractreels",
                    "name":            name,
                    "reelrequestlist": ",".join(reel_codes),
                    "autostart":       "Y",
                    "force_start":     "Y",
                    "tkn":             auth_token
                },
                timeout=15
            )
            response.raise_for_status()

        root = ET.fromstring(response.content)
        if root.get("err", "1") != "0":
            return False, root.get("errdesc", "Unknown Error")
        return True, "Success"

    except CircuitBreakerOpenError as e:
        logger.warning(f"Extraccion SmartRack rechazada — {e}")
        return False, f"Servicio SmartRack no disponible. Reintenta en {e.retry_after:.0f}s"
    except Exception as e:
        logger.error(f"Error durante extraccion: {e}")
        return False, str(e)

def execute_juki_extraction(name: str, container_id: str, reel_codes: list) -> tuple[bool, str]:
    """Ejecuta V3_extractreels en la API de JUKI (Torres)."""
    global auth_token
    if not auth_token and not login():
        return False, "Auth error"

    try:
        with smartrack_cb:
            response = requests.get(
                f"{config.API_BASE_URL}/",
                params={
                    "f":               "V3_extractreels",
                    "name":            name,
                    "container_id":    container_id,
                    "reelrequestlist": ",".join(reel_codes),
                    "autostart":       "y",
                    "tkn":             auth_token
                },
                timeout=15
            )
            response.raise_for_status()

        # Parse XML
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as pe:
            logger.error(f"JUKI API Error - Invalid XML: {response.content}")
            return False, f"Invalid XML from JUKI API: {pe}"

        if root.get("err", "1") != "0":
            err_desc = root.get("errdesc", "Unknown Error")
            logger.error(f"JUKI API Error - Code {root.get('err')}: {err_desc} | Full body: {response.content}")
            return False, err_desc

        return True, "Success"

    except CircuitBreakerOpenError as e:
        logger.warning(f"Extraccion JUKI rechazada — {e}")
        return False, f"Servicio JUKI no disponible. Reintenta en {e.retry_after:.0f}s"
    except Exception as e:
        logger.error(f"Error durante extraccion JUKI: {e}")
        return False, str(e)