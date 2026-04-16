# Troubleshooting & FAQ (SmartRack)

Guía rápida para resolver problemas comunes en la operación de planta.

## 1. El servicio no arranca (SAFE_MODE)
**Síntoma:** El programa se cierra inmediatamente al intentar abrirlo.
- **Causa:** Tienes credenciales inseguras por defecto en tu `.env`.
- **Solución:** Abre tu archivo `.env` y cambia `API_PASSWORD` y `CONFIG_PASSWORD` por valores robustos (no `admin1234` ni `AUTOSMD`).

## 2. Circuit Breaker "OPEN"
**Síntoma:** Las extracciones fallan inmediatamente con un mensaje de "Reintenta en Xs".
- **Causa:** El servidor de SmartRack (API externa) ha fallado 5 veces seguidas. El sistema se protege bloqueando intentos nuevos.
- **Solución:** Verifica que el servidor SmartRack esté encendido y que el cable de red esté conectado. El circuito se cerrará automáticamente tras 60 segundos de estabilidad.

## 3. Discrepancia de Inventario
**Síntoma:** No se encuentran partes que deberían estar en el rack.
- **Causa:** El poller podría estar detenido o sin conexión.
- **Solución:** Revisa `http://localhost:4500/health`. Si `database` o `smartrack_api` reportan error, el inventario local no se actualizará.

## 4. Reinicio de Base de Datos Corrupta
**Síntoma:** Error de "database image is malformed".
- **Causa:** Corte de energía repentino o disco duro dañado.
- **Solución:**
  1. Detén el servicio SmartRack.
  2. Ve a `data/backups/`.
  3. Toma el archivo más reciente (ej. `inventory_14.db`).
  4. Cámbiale el nombre a `inventory.db` y muévelo a la carpeta raíz.
  5. Inicia el servicio.

## 5. Puerto en Uso (4500)
**Síntoma:** Error `[Errno 98] Address already in use`.
- **Causa:** Otra instancia de SmartRack u otro programa usa el puerto 4500.
- **Solución:** Cambia `SERVER_PORT` en el `.env` a `4501` o similar y reinicia.
