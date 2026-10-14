@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup-JobPraapti.cmd first to install JobPraapti.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" tools\launch.py
if errorlevel 1 pause
