==========================================
   SMARTRACK INSTALLATION INSTRUCTIONS
==========================================

1. REQUISITOS PREVIOS
-------------
- Windows 10 (Recomendado) o superior (64-bit).
- Esta PC debe estar conectada a la red de acceso de las lineas JUKI/SmartRack.

2. CONFIGURACION (.env)
-------------
Antes de iniciar `SmartRack.exe` por primera vez, DEBES abrir el archivo que se llama exactamente `.env` con el Bloc de Notas de Windows, y llenar los siguientes datos esenciales:

- API_BASE_URL: La IP del servidor real de la fabrica (Ej: http://192.168.1.100).
- API_USERNAME: Tu usuario administrador provisto.
- API_PASSWORD: La password de API.
- MASTER_KEY: La llave maestra de administracion. (Crea una cadena larga usando letras y num.)
- SAFE_MODE: Asegurate de que este en "true" en produccion.

Ojo: SI NO ACTUALIZAS LAS CREDENCIALES POR DEFECTO, EL SAFE_MODE BLOQUEARA EL ACCESO POR SEGURIDAD.

3. ARRANQUE
-------------
Simplemente da doble clic a `SmartRack.exe`. Este escaneara licencias sin instalar nada en tu sistema, y montara un servidor. Veras una ventana de consola negra, ¡NO la cierres! El servicio web ya arranco.

Abre el navegador Chrome/Edge e ingresa a:
--> http://localhost:4500 (O http://[TU_IP]:4500 desde otra terminal)

4. INICIAR SEGURIDAD EN TABLETS / PCs OPERADOR (Obligatorio)
-------------
Al haber endurecido el sistema, toda extraccion queda auditada para responsabilizar a quien saca material.
1. Usa el navegador del Jefe de Linea y entra a [Configuración] (te pedira la MASTER_KEY).
2. Ve a [Usuarios API] y genera usuarios para tus operadores (Ej: "Operador_Linea_A", "Tablet_JUKI_1").
3. Copia la llave "X-API-Key" que te entregara el panel.
4. Cuando el operador entre a la pestaña [Operador] e intente pedir un rollo por primera vez, el navegador le arrojara un cartel transparente pidiendole su "Llave Magica (X-API-Key)".
5. Pegan esa llave y listo, el navegador la dejara guardada. Cada movimiento quedara registrado a ese nombre.

------------------------------------------
Si por alguna razon falla o no abre la interfaz web, revisa el archivo de registro en: \logs\smartrack.log
