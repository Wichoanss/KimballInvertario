import os
import sys

# Detect if running as PyInstaller bundle or script
if getattr(sys, 'frozen', False):
    # Running as compiled .exe - use the directory of the .exe
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Running as a .py script - use the directory of this file
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# API Server Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8081")

# SmartRack Authentication
API_USERNAME = "USER"
API_PASSWORD = "AUTOSMD"

# Polling Settings
POLL_INTERVAL_SECONDS = 5
LOGIN_INTERVAL_SECONDS = 86400  # Token re-fetch (24 hours or on error)

# Database - always next to the .exe or main.py
DB_NAME = os.path.join(BASE_DIR, "inventory.db")

# Log file - always next to the .exe or main.py
LOG_FILE = os.path.join(BASE_DIR, "smartrack.log")
