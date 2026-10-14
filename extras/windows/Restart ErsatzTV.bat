@echo off
title Restart ErsatzTV
echo Closing ErsatzTV and anything it left running...
taskkill /F /T /IM ErsatzTV-Windows.exe >nul 2>&1
taskkill /F /T /IM ErsatzTV.exe >nul 2>&1
taskkill /F /T /IM ErsatzTV.Scanner.exe >nul 2>&1
taskkill /F /T /IM ffprobe.exe >nul 2>&1
taskkill /F /T /IM ffmpeg.exe >nul 2>&1
echo Waiting a few seconds...
timeout /t 5 /nobreak >nul
echo Starting ErsatzTV...
if exist "%~dp0ErsatzTV-Windows.exe" (
  start "" "%~dp0ErsatzTV-Windows.exe"
) else if exist "%~dp0ErsatzTV.exe" (
  start "" "%~dp0ErsatzTV.exe"
) else (
  echo.
  echo Couldn't find ErsatzTV in this folder.
  echo Put this file in the same folder as ErsatzTV.exe and run it again.
  pause
  exit /b
)
echo Done. Give it a minute, then open http://localhost:8409
timeout /t 5 >nul
