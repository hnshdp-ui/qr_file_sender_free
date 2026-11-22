@echo off
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" receiver_server.py %*
  goto finished
)
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 (
  py -3 receiver_server.py %*
  goto finished
)
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 (
  python receiver_server.py %*
  goto finished
)
echo Python 3.10+ is required on the receiver server PC.
exit /b 1
:finished
if errorlevel 1 (
  pause
  exit /b 1
)
exit /b 0
