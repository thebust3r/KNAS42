@echo off
rem KNAS Break Clips: double-click this on the Windows PC that runs ErsatzTV.
rem It sets everything up: gets the clip copier from KNAS, copies the break clips, and keeps
rem them fresh (checked every 5 minutes). Running it again is safe (it just refreshes everything).
title KNAS Break Clips
set "KNAS_URL=http://YOUR_NAS_IP:8642"
set "KNAS_HERE=%~dp0"
set "KNAS_SETUP=%TEMP%\knas-clip-install.ps1"
echo Connecting to KNAS at %KNAS_URL% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -UseBasicParsing -Uri ($env:KNAS_URL + '/api/setup/download/clip-install.ps1') -OutFile $env:KNAS_SETUP -TimeoutSec 30 } catch { exit 1 }"
if errorlevel 1 (
  echo.
  echo Can't reach KNAS at %KNAS_URL%.
  echo Make sure the NAS is on and this PC is on the same network, then run this again.
  echo.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%KNAS_SETUP%" -NAS "%KNAS_URL%" -Here "%KNAS_HERE%."
echo.
pause
