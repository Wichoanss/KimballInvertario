@echo off
echo ==========================================
echo    SMARTRACK - COMPILACION DE PRODUCCION
echo ==========================================
echo.

echo [1/4] Limpiando carpetas de compilacion previas...
if exist "build" rmdir /s /q "build"
if exist "dist\SmartRack" rmdir /s /q "dist\SmartRack"
if exist "dist\SmartRack.exe" del /q "dist\SmartRack.exe"
if exist "SmartRack_Planta.zip" del /q "SmartRack_Planta.zip"

echo [2/4] Ejecutando PyInstaller...
python -m PyInstaller --clean main.spec
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Fallo la compilacion con PyInstaller.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [3/4] Preparando carpeta de distribucion para Planta...
mkdir "dist\SmartRack_Planta\logs" 2>nul
mkdir "dist\SmartRack_Planta\data" 2>nul

echo     - Copiando ejecutable...
copy /y "dist\SmartRack.exe" "dist\SmartRack_Planta\SmartRack.exe" >nul

echo     - Copiando plantilla de configuracion (.env.example -^> .env)...
copy /y ".env.example" "dist\SmartRack_Planta\.env" >nul

echo     - Copiando instrucciones de despliegue...
copy /y "README_PLANTA.txt" "dist\SmartRack_Planta\README_PLANTA.txt" >nul

echo.
echo [4/4] Proceso finalizado con exito.
echo.
echo La carpeta lista para enviar a produccion esta en:
echo -^> dist\SmartRack_Planta\
echo.
echo ==========================================
pause
