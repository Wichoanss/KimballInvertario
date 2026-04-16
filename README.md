# SmartRack Inventario (v1.6.0)

Sistema de gestión y extracción de inventarios para racks automáticos SmartRack y torres JUKI. Diseñado para alta disponibilidad en entornos industriales.

## Requisitos de Sistema
- **SO**: Windows 10/11 o Windows Server 2016+ (64-bit).
- **RAM**: 4GB mínimo (el proceso consume ~150MB).
- **Disco**: 2GB libres (para base de datos y logs rotativos).
- **Red**: Acceso vía TCP/IP a la API de SmartRack (puerto 8081 por defecto).
- **Runtime**: Si usas el `.exe`, no requiere dependencias. Si usas el código fuente, requiere Python 3.10+.

## Cómo Compilar el .exe
El proyecto incluye un archivo `.spec` optimizado para PyInstaller que genera un binario único:

1. Instalar dependencias: `pip install -r requirements-dev.txt`
2. Ejecutar compilación: `pyinstaller --clean main.spec`
3. El archivo resultante estará en `dist/SmartRack.exe`.

## Configuración en Planta
Crea un archivo `.env` en la misma carpeta que el `.exe`:

```ini
API_BASE_URL=http://[IP_SMARTRACK]:8081
API_USERNAME=TuUsuario
API_PASSWORD=TuPassword
SERVER_PORT=4500
SAFE_MODE=true        # Bloquea el arranque si las credenciales son inseguras
POLL_INTERVAL_SECONDS=5
```

## Seguridad Industrial (SAFE_MODE)
Si `SAFE_MODE=true`, el sistema se negará a iniciar si detecta:
- Contraseñas de fábrica (`admin1234`, `AUTOSMD`).
- Usuarios genéricos (`admin`, `USER`).
Esto obliga al equipo de IT a configurar credenciales únicas por planta.

## Monitoreo
- **Salud**: `GET /health` (Verifica DB, Disco y Conexión API).
- **Métricas**: `GET /metrics` (Latencias y contador de extracciones).
- **Versión**: `GET /version`.
