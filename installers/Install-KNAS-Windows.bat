@echo off
setlocal
title KNAS 42 installer
rem Installs (or updates) KNAS 42 in Docker Desktop with the right settings, then opens the setup page.
rem Double-click it again any time to update KNAS. Your settings stay.

set "IMAGE=ghcr.io/thebust3r/knas42:latest"
set "KNASDIR=%USERPROFILE%\KNAS42"

echo.
echo   KNAS 42 installer
echo   -----------------
echo.

docker info >nul 2>&1
if errorlevel 1 (
  echo   Docker isn't running.
  echo   Open Docker Desktop, wait until the bottom-left corner says "Engine running",
  echo   then double-click this file again.
  echo.
  pause
  exit /b 1
)

echo   Downloading the newest KNAS 42...
docker pull %IMAGE%
if errorlevel 1 (
  echo.
  echo   The download didn't work. Check your internet connection and try again.
  echo.
  pause
  exit /b 1
)

echo.
echo   Starting KNAS 42 (your files are kept in %KNASDIR%)...
docker rm -f knas42 >nul 2>&1
docker run -d --name knas42 --restart unless-stopped -p 8642:8642 -p 8645:8645 -v "%KNASDIR%:/knas" %IMAGE% >nul
if errorlevel 1 (
  echo.
  echo   KNAS didn't start. Another program may be using port 8642.
  echo   Here's what Docker said:
  docker logs --tail 20 knas42
  echo.
  pause
  exit /b 1
)

echo   Waiting for KNAS to come on the air...
set /a tries=0
:wait
set /a tries+=1
curl -s -o nul http://localhost:8642/setup >nul 2>&1
if not errorlevel 1 goto ready
if %tries% geq 60 goto slow
timeout /t 2 /nobreak >nul
goto wait

:slow
echo.
echo   KNAS is taking longer than usual. Give it another minute, then open
echo   http://localhost:8642/setup in your browser.
echo.
pause
exit /b 0

:ready
set "LANIP="
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.PrefixOrigin -eq 'Dhcp' -or $_.PrefixOrigin -eq 'Manual' } | Where-Object { $_.IPAddress -notlike '169.*' -and $_.IPAddress -notlike '172.*' -and $_.IPAddress -ne '127.0.0.1' } | Select-Object -First 1).IPAddress"`) do set "LANIP=%%i"

echo.
echo   KNAS 42 is on the air!
echo.
echo   Setup page (this computer):  http://localhost:8642/setup
if defined LANIP (
  echo   Cable box on a TV or phone:  http://%LANIP%:8642/tv
) else (
  echo   Cable box on a TV or phone:  http://THIS-PC'S-IP:8642/tv
)
echo.
echo   If Windows asks about the firewall, click Allow so your TVs can reach it.
echo   KNAS starts by itself whenever Docker Desktop is running.
echo   To update later, just double-click this file again.
echo.
start "" http://localhost:8642/setup
pause
