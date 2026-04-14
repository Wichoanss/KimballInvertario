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

# Rutas de archivos — siempre junto al .exe o main.py
DB_NAME  = os.path.join(BASE_DIR, os.getenv("DB_NAME",  "inventory.db"))
LOG_FILE = os.path.join(BASE_DIR, os.getenv("LOG_FILE", "smartrack.log"))

# Acceso a Configuracion de Lineas
CONFIG_USERNAME = os.getenv("CONFIG_USERNAME", "admin")
CONFIG_PASSWORD = os.getenv("CONFIG_PASSWORD", "admin1234")