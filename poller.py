import re
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

import config
from database import upsert_reels, get_db_connection
from logger_setup import setup_logger

logger = setup_logger("SmartRackPoller")
auth_token = None


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
def login() -> str | None:
    """Obtiene token de autenticacion. Reintenta una vez si falla."""
    global auth_token
    for attempt in range(2):
        try:
            response = requests.get(
                f"{config.API_BASE_URL}/",
                params={"f": "login", "username": config.API_USERNAME, "password": config.API_PASSWORD},
                timeout=10
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)

            if root.get("err", "1") != "0":
                logger.warning(f"Login fallido: {root.get('errdesc', 'Error desconocido')} (intento {attempt + 1})")
            else:
                token_el = root.find(".//token")
                if token_el is not None and token_el.text:
                    auth_token = token_el.text.strip()
                    logger.info("Token de autenticacion obtenido correctamente.")
                    return auth_token
                logger.warning(f"Token no encontrado en respuesta (intento {attempt + 1})")

        except Exception as e:
            logger.warning(f"Error durante login: {e} (intento {attempt + 1})")

        if attempt == 0:
            time.sleep(5)

    return None


# ---------------------------------------------------------------------------
# Polling principal
# ---------------------------------------------------------------------------
def fetch_and_update_reels() -> None:
    """Consulta la API por cada rack y actualiza la base de datos."""
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
                    response = requests.get(f"{config.API_BASE_URL}/", params=params, timeout=10)
                    response.raise_for_status()
                    root = ET.fromstring(response.content)
                else:
                    logger.error(f"Error de API en rack {rack_id}: {errdesc}")
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

        except Exception as e:
            logger.error(f"Error consultando rack {rack_id}: {e}")


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

    except Exception as e:
        logger.error(f"Error durante extraccion: {e}")
        return False, str(e)