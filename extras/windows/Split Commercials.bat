@echo off
rem KNAS Commercial Splitter: drag long commercial videos (or a folder of them) onto this file.
rem Each one is cut into separate commercials at the fades to black. Your originals aren't changed.
rem Double-click instead to pick the videos from a list.
title KNAS Commercial Splitter
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0knas-split-commercials.ps1" %*
echo.
pause
