# -*- mode: python ; coding: utf-8 -*-
# ============================================================
#  main.spec — Build de produccion para maquila
#  Genera: dist/SmartRack.exe  (onefile, sin Python requerido)
#
#  IMPORTANTE:
#    - Compilar SIEMPRE en Python 32-bit si la maquina destino es 32-bit
#    - Usar: pyinstaller --clean main.spec
# ============================================================

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Recolectar todos los submódulos de uvicorn y starlette automáticamente
uvicorn_imports   = collect_submodules('uvicorn')
starlette_imports = collect_submodules('starlette')
fastapi_imports   = collect_submodules('fastapi')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates')    # HTML del panel web
    ],
    hiddenimports=[
        # --- uvicorn (dinámico, PyInstaller no lo detecta solo) ---
        *uvicorn_imports,
        # --- starlette / fastapi internals ---
        *starlette_imports,
        *fastapi_imports,
        # --- apscheduler ---
        'apscheduler',
        'apscheduler.triggers.interval',
        'apscheduler.triggers.date',
        'apscheduler.jobstores.memory',
        'apscheduler.executors.pool',
        'apscheduler.schedulers.background',
        # --- pydantic ---
        'pydantic',
        'pydantic.deprecated.class_validators',
        'pydantic_core',
        # --- stdlib que PyInstaller puede omitir ---
        'multiprocessing',
        'multiprocessing.freeze_support',
        'logging.handlers',
        'sqlite3',
        'email.mime.text',
        'email.mime.multipart',
        'xml.etree.ElementTree',
        'contextvars',
        'uuid',
        # --- módulos propios ---
        'resilience',
        'schemas',
        'schemas.requests',
        'schemas.responses',
        'schemas.db',
        'logger_setup',
        'database',
        'poller',
        'config',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dev-only — nunca al .exe
        'tests',
        'pytest',
        'pytest_cov',
        'httpx',
        'coverage',
        # Innecesarios en producción
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
    ],
    noarchive=False,
    optimize=1,   # elimina docstrings — reduce el tamaño ~5%
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SmartRack',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # Desactivado: UPX puede disparar AV corporativos
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # REQUERIDO: uvicorn necesita stdout/stderr
                        # Para ocultar la ventana: crear acceso directo
                        # con "Ejecutar: Minimizada" o usar nssm como servicio
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,          # Reemplazar con 'assets/icon.ico' si se tiene
)
