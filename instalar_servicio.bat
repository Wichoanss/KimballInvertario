@echo off
echo ====================================================
echo  SmartRack Server - Servicio de Inicio Automatico
echo ====================================================
echo.
echo Este script configurara el archivo principal 'main.exe'
echo (ubicado en la carpeta actual / dist) para que inicie de forma
echo silenciosa cada vez que Windows arranque.
echo.
echo Presiona cualquier tecla para continuar o cierra esta ventana para cancelar...
pause >nul

set "EXE_PATH=%~dp0dist\main.exe"

if not exist "%EXE_PATH%" (
    echo.
    echo ERROR: No se encontro el archivo %EXE_PATH%
    echo Asegurate de haber corrido PyInstaller primero.
    pause
    exit /b
)

echo.
echo Creando Tarea Programada...
schtasks /query /tn "SmartRackServer" >nul 2>&1
if %errorlevel% equ 0 (
    echo.
    echo ADVERTENCIA: La tarea SmartRackServer ya existe.
    set /p RESP=Deseas reemplazarla? (S/N): 
    if /i "%RESP%"=="S" (
        schtasks /delete /tn "SmartRackServer" /f
        echo Tarea anterior eliminada. Creando nueva...
    ) else (
        echo Instalacion cancelada por el usuario.
        pause
        exit /b
    )
)
schtasks /create /tn "SmartRackServer" /tr "\"%EXE_PATH%\"" /sc onlogon /rl highest /f

if %errorlevel% equ 0 (
    echo.
    echo [EXITO] El servidor iniciara automaticamente de fondo al prender la PC.
    echo Si deseas detenerlo manualmente algun dia, usa el Administrador de Tareas.
) else (
    echo.
    echo [ERROR] No se pudo crear la tarea. Debes ejecutar este archivo .bat como Administrador.
)
echo.
pause
