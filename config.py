import os
import sys

# ---------------------------------------------------------------------------
# BASE_DIR — carpeta del .exe en produccion, carpeta del script en desarrollo
# ---------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Directorios de trabajo — se crean automaticamente si no existen
# Esto garantiza que el .exe funcione en una maquina limpia sin configuracion
# ---------------------------------------------------------------------------
LOGS_DIR = os.path.join(BASE_DIR, "logs")
DATA_DIR  = os.path.join(BASE_DIR, "data")

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(DATA_DIR,  exist_ok=True)


# ---------------------------------------------------------------------------
# Lector de .env manual (stdlib pura, sin dependencias externas)
# Busca el archivo .env junto al .exe o junto a config.py
# Formato soportado:
#   CLAVE=valor
#   CLAVE="valor con espacios"
#   # esto es un comentario
#   CLAVE=           <- valor vacio valido
# Las variables ya definidas en el entorno del sistema NO se sobreescriben,
# asi el operador de IT puede forzar valores via variables de entorno si lo necesita.
# ---------------------------------------------------------------------------
def _load_env(path: str) -> None:
    try:
        with open(path, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except FileNotFoundError:
        pass  # .env opcional — si no existe, se usan los defaults


_load_env(os.path.join(BASE_DIR, ".env"))


# ---------------------------------------------------------------------------
# Configuracion — cada valor puede sobreescribirse en el .env
# ---------------------------------------------------------------------------

# URL del servidor SmartRack
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8081")

# Credenciales SmartRack
API_USERNAME = os.getenv("API_USERNAME", "USER")
API_PASSWORD = os.getenv("API_PASSWORD", "AUTOSMD")

# Intervalo de polling en segundos
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", 5))

# Intervalo de re-login en segundos (default 24 horas)
LOGIN_INTERVAL_SECONDS = int(os.getenv("LOGIN_INTERVAL_SECONDS", 86400))

# Puerto del servidor FastAPI
SERVER_PORT = int(os.getenv("SERVER_PORT", 4500))

# Nivel de log: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Modo Seguro en Producción (Fail-Fast activo por defecto)
SAFE_MODE = os.getenv("SAFE_MODE", "true").lower() in ("true", "1", "yes")

# Rutas de archivos
# DB junto al .exe (facil de respaldar); log dentro de logs/
DB_NAME  = os.path.join(BASE_DIR, os.getenv("DB_NAME",  "inventory.db"))
LOG_FILE = os.path.join(LOGS_DIR,  os.getenv("LOG_FILE", "smartrack.log"))

# Acceso a Configuracion de Lineas
CONFIG_USERNAME = os.getenv("CONFIG_USERNAME", "admin")
CONFIG_PASSWORD = os.getenv("CONFIG_PASSWORD", "admin1234")

# ---------------------------------------------------------------------------
# Validacion de Seguridad
# ---------------------------------------------------------------------------
from urllib.parse import urlparse

def validate_production_config() -> None:
    """
    Bloquea el arranque o advierte si se detectan configuraciones altamente vulnerables.
    Asegura que el sistema no se exponga pasivamente en la maquila.
    """
    from logger_setup import setup_logger
    logger = setup_logger("SecurityValidator")
    
    errors = []
    
    # 1. URL Válida
    parsed = urlparse(API_BASE_URL)
    if not parsed.scheme or not parsed.netloc:
        errors.append(f"API_BASE_URL inválida (falta http/ip): {API_BASE_URL}")

    # 2. Credenciales por defecto SmartRack
    if API_USERNAME == "USER" and API_PASSWORD == "AUTOSMD":
        errors.append("Credenciales usadas en API SmartRack son las de fábrica (USER/AUTOSMD)")
        
    if not API_PASSWORD or len(API_PASSWORD) < 3:
        errors.append("API_PASSWORD vacío o inferior a 3 caracteres")

    # 3. Credenciales de configuración inseguras
    if CONFIG_USERNAME == "admin" and CONFIG_PASSWORD == "admin1234":
        errors.append("Credenciales por defecto en Panel Config (admin/admin1234)")
        
    if not CONFIG_PASSWORD or len(CONFIG_PASSWORD) < 6:
        errors.append("CONFIG_PASSWORD muy débil (mínimo 6 caracteres requeridos)")

    # 4. Modo Debug en Producción
    if LOG_LEVEL == "DEBUG":
        errors.append("LOG_LEVEL configurado como DEBUG (ruidoso/riesgo rendimiento)")

    if errors:
        for err in errors:
            logger.warning(f"Riesgo de seguridad: {err}")
            
        if SAFE_MODE:
            logger.critical("SAFE_MODE=true activo: Bloqueando arranque por reglas de seguridad de producción.")
            print("\n" + "="*70, file=sys.stderr)
            print("❌ ERROR CRÍTICO: PROTECCIÓN DE PRODUCCIÓN (SAFE_MODE)", file=sys.stderr)
            print("El sistema rehusó iniciar para evitar un despliegue vulnerable:", file=sys.stderr)
            for err in errors:
                print(f"   - {err}", file=sys.stderr)
            print("\nEdite su archivo .env con valores robustos y reinicie la aplicación.", file=sys.stderr)
            print("="*70 + "\n", file=sys.stderr)
            sys.exit(1)
        else:
            logger.warning("SAFE_MODE desactivado. Iniciando sistema bajo propio riesgo.")