@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Install Python 3.11 or newer from python.org, then run this file again.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m jobpilot init
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m jobpilot install-browser
if errorlevel 1 goto failed
echo Setup complete. Open Start-JobPraapti.cmd to use your private website.
pause
exit /b 0
:failed
echo Setup could not finish. Review the error above and try again.
pause
exit /b 1
