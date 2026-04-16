# Guía de Instalación para Planta (Soporte IT)

Sigue estos pasos para desplegar SmartRack como un servicio persistente en una estación de trabajo de Windows.

## 1. Preparación de Carpeta
1. Crea una carpeta raíz, ej: `C:\SmartRack\`.
2. Coloca en ella el archivo `SmartRack.exe` y `templates/`.
3. Crea el archivo `.env` basado en la plantilla `.env.example`.

## 2. Configurar como Servicio Windows (Auto-start)
Recomendamos usar **NSSM** (Non-Sucking Service Manager) para asegurar que el programa se reinicie automáticamente si falla.

1. Descarga NSSM de [nssm.cc](https://nssm.cc/download).
2. Abre la terminal como Administrador y ejecuta:
   ```bash
   nssm install SmartRackService
   ```
3. En el panel de configuración:
   - **Path**: `C:\SmartRack\SmartRack.exe`
   - **Startup directory**: `C:\SmartRack\`
   - **App log (stdout)**: `C:\SmartRack\logs\service_console.log` (opcional)
4. Haz clic en "Install service".
5. Inicia el servicio desde `services.msc`.

## 3. Firewall y Red
- El sistema utiliza por defecto el puerto **4500**.
- Debes crear una regla de entrada en el Firewall de Windows para permitir tráfico TCP en el puerto 4500 si se accederá desde otras PCs de la red.

## 4. Verificación Inicial
Abre un navegador y visita:
- `http://localhost:4500/health`: Debe responder con `status: "ok"`.
- `http://localhost:4500/version`: Debe confirmar la versión `1.6.0`.

## 5. Backups y Mantenimiento
- El sistema realiza backups automáticos cada hora en `C:\SmartRack\data\backups\`.
- Los logs se rotan automáticamente; no es necesario borrarlos manualmente.
