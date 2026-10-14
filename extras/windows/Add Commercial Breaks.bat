@echo off
rem KNAS Commercial Breaks: drag a show's folder (or some episodes) onto this file.
rem It adds chapter markers where the commercial breaks used to be, for ErsatzTV's Mid-Roll filler.
rem Nothing is re-encoded. Double-click instead to pick a folder.
title KNAS Commercial Breaks
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0knas-add-breaks.ps1" %*
echo.
pause
