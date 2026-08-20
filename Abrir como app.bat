@echo off
REM ===================================================================
REM  Asignacion de Tiempo Extra - TWR MEX
REM
REM  Sirve el programa desde esta misma computadora para poder
REM  INSTALARLO como aplicacion. El navegador no deja instalar un
REM  archivo abierto con doble clic; servido desde 127.0.0.1 si.
REM
REM  No instala nada ni pide permisos: usa el PowerShell que ya trae
REM  Windows y escucha solo en 127.0.0.1, que es esta computadora.
REM  Nada sale a la red.
REM ===================================================================
setlocal
title Tiempo Extra - lanzador
cd /d "%~dp0"

if not exist "Tiempo Extra.html" goto sin_archivo

echo.
echo  ================================================================
echo   Tiempo Extra - TWR MEX
echo  ================================================================
echo.
echo   Sirviendo en  http://127.0.0.1:8788
echo.
echo   1. Se abre solo en el navegador.
echo   2. Pulsa el boton  "Instalar"  de la barra de arriba.
echo   3. Ya instalada, se abre desde el menu de inicio y ya no
echo      hace falta este lanzador.
echo.
echo   NO CIERRES esta ventana mientras lo usas desde aqui.
echo   Para detenerlo: cierra esta ventana.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$raiz=(Get-Location).Path;" ^
  "$tipos=@{'.html'='text/html; charset=utf-8';'.js'='text/javascript; charset=utf-8';'.css'='text/css; charset=utf-8';'.webmanifest'='application/manifest+json; charset=utf-8';'.json'='application/json; charset=utf-8';'.png'='image/png';'.ico'='image/x-icon';'.txt'='text/plain; charset=utf-8'};" ^
  "$oyente=New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,8788);" ^
  "try { $oyente.Start() } catch { Write-Host '  No se pudo abrir el puerto 8788. Cierra el otro lanzador y reintenta.'; Read-Host '  Enter para salir'; exit 1 };" ^
  "Start-Process 'http://127.0.0.1:8788/';" ^
  "while ($true) {" ^
  "  $c=$oyente.AcceptTcpClient(); $f=$c.GetStream();" ^
  "  try {" ^
  "    $lec=New-Object IO.StreamReader($f); $linea=$lec.ReadLine();" ^
  "    if (-not $linea) { $c.Close(); continue };" ^
  "    $ruta=($linea -split ' ')[1]; $ruta=($ruta -split '\?')[0];" ^
  "    $rel=[Uri]::UnescapeDataString($ruta).TrimStart('/');" ^
  "    if ($rel -eq '') { $rel='Tiempo Extra.html' };" ^
  "    $full=Join-Path $raiz $rel;" ^
  "    $ok = $full.StartsWith($raiz) -and (Test-Path -LiteralPath $full -PathType Leaf);" ^
  "    if ($ok) {" ^
  "      $b=[IO.File]::ReadAllBytes($full);" ^
  "      $ext=[IO.Path]::GetExtension($full).ToLower();" ^
  "      $ct=$tipos[$ext]; if (-not $ct) { $ct='application/octet-stream' };" ^
  "      $cab=\"HTTP/1.1 200 OK`r`nContent-Type: $ct`r`nContent-Length: $($b.Length)`r`nCache-Control: no-cache`r`nConnection: close`r`n`r`n\";" ^
  "    } else {" ^
  "      $b=[Text.Encoding]::UTF8.GetBytes('No encontrado');" ^
  "      $cab=\"HTTP/1.1 404 Not Found`r`nContent-Type: text/plain; charset=utf-8`r`nContent-Length: $($b.Length)`r`nConnection: close`r`n`r`n\";" ^
  "    };" ^
  "    $cb=[Text.Encoding]::ASCII.GetBytes($cab);" ^
  "    $f.Write($cb,0,$cb.Length); $f.Write($b,0,$b.Length); $f.Flush();" ^
  "  } catch { } finally { $c.Close() }" ^
  "}"

echo.
echo  El lanzador se detuvo.
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
