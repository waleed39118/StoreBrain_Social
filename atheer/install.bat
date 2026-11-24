@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ============================================
echo   Atheer - installation
echo ============================================

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
%PY% -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>nul
if errorlevel 1 (
  echo [!] Python 3.11 or newer is required. Install it from https://www.python.org/downloads/
  echo     and tick "Add Python to PATH" during setup. Then run this file again.
  pause
  exit /b 1
)

if not exist .venv (
  echo Creating virtual environment...
  %PY% -m venv .venv || goto :fail
)
echo Installing Atheer and its libraries (first time takes a few minutes)...
call .venv\Scripts\python.exe -m pip install --upgrade pip >nul
call .venv\Scripts\python.exe -m pip install -e ".[dev]" || goto :fail

call .venv\Scripts\python.exe scripts\setup_env.py || goto :fail

choice /c YN /m "Add demo data (doctor, patients, two appointments today)?"
if errorlevel 2 goto :done
call .venv\Scripts\atheer-admin.exe seed-demo --with-appointments

:done
echo.
echo Done. Run start.bat to launch Atheer.
pause
exit /b 0

:fail
echo [!] Installation failed. Copy the messages above and send them to support.
pause
exit /b 1
