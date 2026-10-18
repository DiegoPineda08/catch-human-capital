@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title DINAMO Analytics

rem ---- 1. Buscar Python 3 ----
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY (
  echo No encontre Python 3. Instalalo desde https://www.python.org/downloads/ ^(marca "Add python.exe to PATH"^).
  pause
  exit /b 1
)

rem ---- 2. Entorno virtual con las dependencias minimas (solo la primera vez) ----
if not exist ".venv\Scripts\python.exe" (
  echo Preparando el entorno por primera vez. Puede tardar unos minutos...
  %PY% -m venv .venv || (echo No se pudo crear el entorno virtual. & pause & exit /b 1)
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
  ".venv\Scripts\python.exe" -m pip install -r requirements-servidor.txt || (echo Fallo la instalacion de dependencias. & pause & exit /b 1)
)

rem ---- 3. Configuracion ----
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Se creo el archivo .env. Puedes agregar claves de API ahi ^(opcional^).
)

rem ---- 4. Arrancar (el servidor abre el navegador) ----
echo.
echo Iniciando DINAMO Analytics... Para cerrarlo, cierra esta ventana o pulsa Ctrl+C.
".venv\Scripts\python.exe" -m dinamo.servidor
pause
endlocal
