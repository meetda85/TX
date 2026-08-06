@echo off
REM ===================================================================
REM  Asignacion de Tiempo Extra - TWR MEX
REM  Doble clic en este archivo para abrir el sistema.
REM ===================================================================
setlocal
title Tiempo Extra TWR MEX
cd /d "%~dp0"

REM -- Buscar Python. El lanzador "py" es el mas confiable en Windows;
REM -- "python" a secas puede ser el atajo que abre la Microsoft Store.
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (
    where python >nul 2>nul && set PY=python
)

if not defined PY goto sin_python

REM -- Comprobar que la version alcance. El programa necesita 3.9 o mas.
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if errorlevel 1 goto version_vieja

REM -- Comprobar que no sea el atajo de la Microsoft Store, que no ejecuta nada.
%PY% -c "print()" >nul 2>nul
if errorlevel 1 goto sin_python

%PY% -m tx
if errorlevel 1 (
    echo.
    echo  El programa se cerro con un error. Copia el texto de arriba
    echo  si necesitas reportarlo.
    echo.
    pause
)
goto :eof

:version_vieja
echo.
echo  ================================================================
echo   La version de Python instalada es demasiado vieja.
echo  ================================================================
echo.
%PY% -V
echo.
echo   Hace falta Python 3.9 o mas nuevo.
echo   Descarga la version actual de:
echo.
echo       https://www.python.org/downloads/
echo.
echo   Durante la instalacion MARCA la casilla
echo   "Add python.exe to PATH" (abajo del todo).
echo.
pause
goto :eof

:sin_python
echo.
echo  ================================================================
echo   No se encontro Python en esta computadora.
echo  ================================================================
echo.
echo   1. Entra a  https://www.python.org/downloads/
echo   2. Pulsa el boton amarillo "Download Python"
echo   3. Abre el archivo descargado
echo   4. IMPORTANTE: marca la casilla "Add python.exe to PATH"
echo      que aparece hasta abajo, ANTES de pulsar "Install Now"
echo   5. Termina la instalacion y vuelve a dar doble clic aqui
echo.
echo   No hace falta instalar nada mas: el programa usa solo lo que
echo   Python trae de fabrica.
echo.
pause
goto :eof
