@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto check_venv

rem Probe interpreters, not just PATH entries: Windows aliases can be unusable.
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 goto create_with_py
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 goto create_with_python
python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 goto create_with_python3
echo No working Python 3.10+ interpreter was found.
echo Install Python from https://www.python.org/downloads/windows/
echo Enable the Python launcher or add Python to PATH, then run this script again.
pause
exit /b 1

:create_with_py
echo Creating repository-local virtual environment...
py -3 -m venv .venv
goto venv_created
:create_with_python
echo Creating repository-local virtual environment...
python -m venv .venv
goto venv_created
:create_with_python3
echo Creating repository-local virtual environment...
python3 -m venv .venv
:venv_created
if errorlevel 1 goto setup_error

:check_venv
".venv\Scripts\python.exe" -c "import sys; print('Using Python', sys.version.split()[0]); raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo The existing .venv is unusable or uses Python older than 3.10.
  echo Rename .venv, then run this script again to create a new environment.
  goto setup_error
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto setup_error
".venv\Scripts\python.exe" -m pip install --only-binary=Pillow,zxing-cpp -r requirements.txt
if errorlevel 1 goto setup_error
".venv\Scripts\python.exe" -c "import tkinter; from PIL import Image, ImageTk; import qrcode, zxingcpp; print('Sender dependencies are ready: ZXing-C++ native encoder.')"
if errorlevel 1 goto setup_error
echo.
echo Setup complete. Run run_sender.cmd next.
pause
exit /b 0
:setup_error
echo Setup failed. Check the Python and dependency installation messages above.
pause
exit /b 1
