@echo off
REM Double-click helper that runs build.ps1 (the real build script).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
pause
