@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" || exit /b 1

set "venv_python=.venv\Scripts\python.exe"
set "check_dependencies=import tkinter; from PIL import Image, ImageTk; import qrcode; from zxingcpp import create_barcode"
if exist "%venv_python%" (
  "%venv_python%" -c "import sys; %check_dependencies%; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
  if not errorlevel 1 goto launch
)

if not exist "wheelhouse\*.whl" (
  echo Offline dependency files are missing. Run setup_sender.cmd on a connected PC and copy wheelhouse with the project.
  goto setup_error
)

if exist "%venv_python%" goto check_venv

rem Probe interpreters, not just PATH entries: Windows aliases can be unusable.
for %%P in ("py -3" python python3) do (
  %%~P -c "import sys, tkinter; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
  if not errorlevel 1 (
    set "sender_python=%%~P"
    goto create_venv
  )
)
echo No working Python 3.10+ with Tkinter was found. Install Python with Tcl/Tk and add it to PATH.
goto setup_error

:create_venv
echo Creating the local Python environment...
%sender_python% -m venv .venv
if errorlevel 1 goto setup_error

:check_venv
"%venv_python%" -c "import sys, tkinter; from sysconfig import get_platform; print('Using Python', sys.version.split()[0], 'on', get_platform()); raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo The local .venv is unusable. If copied from another PC, rename it and run this script again.
  goto setup_error
)
"%venv_python%" -m pip --version >nul 2>nul
if errorlevel 1 (
  "%venv_python%" -m ensurepip
  if errorlevel 1 goto setup_error
)

echo Installing sender dependencies from wheelhouse...
set "PIP_CONFIG_FILE=NUL"
"%venv_python%" -m pip --isolated --disable-pip-version-check install --no-index --find-links=wheelhouse --only-binary=:all: -r requirements.txt
if errorlevel 1 (
  echo Check that wheelhouse is complete and matches the Python version and architecture shown above.
  goto setup_error
)
"%venv_python%" -c "%check_dependencies%"
if errorlevel 1 goto setup_error

:launch
"%venv_python%" -m sender %*
set "sender_result=%errorlevel%"
popd
if not "%sender_result%"=="0" pause
exit /b %sender_result%

:setup_error
popd
pause
exit /b 1
