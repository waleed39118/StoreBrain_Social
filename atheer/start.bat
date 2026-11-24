@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\atheer-server.exe (
  echo Atheer is not installed yet. Run install.bat first.
  pause
  exit /b 1
)
echo Starting Atheer... keep this window open. Close it to stop Atheer.
start "" http://127.0.0.1:8000/
.venv\Scripts\atheer-server.exe
pause
