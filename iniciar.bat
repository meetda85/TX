@echo off
REM ===================================================================
REM  Asignacion de Tiempo Extra - TWR MEX
REM  Doble clic en este archivo para abrir el sistema.
REM ===================================================================
title Tiempo Extra TWR MEX
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m tx
    goto fin
)

where python >nul 2>nul
if %errorlevel%==0 (
    python -m tx
    goto fin
)

echo.
echo  No se encontro Python en esta computadora.
echo.
echo  Descargalo de https://www.python.org/downloads/
echo  y durante la instalacion marca la casilla
echo  "Add Python to PATH".
echo.
pause

:fin
if errorlevel 1 pause
