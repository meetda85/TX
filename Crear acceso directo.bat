@echo off
REM ===================================================================
REM  Pone un acceso directo en el Escritorio, con el icono TX, que abre
REM  el programa en su propia ventana: sin barra de direcciones y sin
REM  pestañas, como cualquier otro programa.
REM
REM  Se corre una sola vez. No instala nada ni pide permisos: lo unico
REM  que hace es crear un acceso directo.
REM ===================================================================
setlocal
title Acceso directo a Tiempo Extra

set "APP=%~dp0Tiempo Extra.html"
set "ICONO=%~dp0TX.ico"

if not exist "%APP%" goto sin_archivo

REM -- Los parentesis de "Program Files (x86)" rompen un bloque FOR, asi
REM -- que la variable se copia antes de entrar al bloque.
set "PF86=%ProgramFiles(x86)%"

REM -- Se busca Edge o Chrome para abrirlo en ventana propia. Si no
REM -- aparece ninguno el acceso directo apunta al archivo y lo abre el
REM -- navegador que este por omision, que tambien funciona.
set "NAV="
for %%R in (
  "%PF86%\Microsoft\Edge\Application\msedge.exe"
  "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
  "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
  "%PF86%\Google\Chrome\Application\chrome.exe"
  "%LocalAppData%\Google\Chrome\Application\chrome.exe"
) do if not defined NAV if exist %%R set "NAV=%%~R"

echo.
if defined NAV (
  echo  Navegador encontrado:
  echo    %NAV%
) else (
  echo  No se encontro Edge ni Chrome en las rutas de siempre.
  echo  El acceso directo va a abrir el archivo con el navegador
  echo  que tengas por omision.
)
echo.

REM -- GetFolderPath en vez de SpecialFolders: da con el Escritorio aunque
REM -- OneDrive se lo haya llevado a otra ruta, y no depende de COM.
powershell -NoProfile -Command "$sh = New-Object -ComObject WScript.Shell; $destino = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Tiempo Extra.lnk'; $l = $sh.CreateShortcut($destino); if ($env:NAV) { $l.TargetPath = $env:NAV; $l.Arguments = '--app=file:///' + ($env:APP -replace '\\','/' -replace ' ','%%20') } else { $l.TargetPath = $env:APP }; $l.WorkingDirectory = Split-Path $env:APP; $l.Description = 'Asignacion de Tiempo Extra - TWR MEX'; if (Test-Path $env:ICONO) { $l.IconLocation = $env:ICONO }; $l.Save(); Write-Host ('  Listo: ' + $destino)"

if errorlevel 1 goto no_pudo

echo.
echo  Ya tienes el icono TX en el Escritorio. Doble clic y abre.
echo.
echo  Si lo mueves de carpeta, vuelve a correr este archivo para
echo  que el acceso directo apunte al lugar nuevo.
echo.
pause
goto :eof

:sin_archivo
echo.
echo  ================================================================
echo   No encontre "Tiempo Extra.html"
echo  ================================================================
echo.
echo   Este archivo tiene que estar en la MISMA carpeta que
echo   "Tiempo Extra.html". Ponlos juntos y vuelve a intentar.
echo.
pause
goto :eof

:no_pudo
echo.
echo  ================================================================
echo   No se pudo crear el acceso directo
echo  ================================================================
echo.
echo   Seguramente la politica del equipo no deja correr PowerShell.
echo   Hazlo a mano, que tarda lo mismo:
echo.
echo     1. Clic derecho sobre "Tiempo Extra.html"
echo     2. "Enviar a"  ^>  "Escritorio (crear acceso directo)"
echo.
echo   Te queda el icono en el Escritorio. Se abre en una pestaña
echo   normal del navegador en vez de en ventana propia, que es la
echo   unica diferencia.
echo.
pause
goto :eof
