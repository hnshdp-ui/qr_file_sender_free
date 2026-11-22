@echo off
setlocal
cd /d "%~dp0"
if not exist "wheelhouse\*.whl" (
  echo Offline dependency wheels are missing from wheelhouse.
  echo On a preparation PC with the same Python version and architecture, run:
  echo   python -m pip download --only-binary=:all: -r requirements.txt -d wheelhouse
  echo Copy wheelhouse and the project to this PC, then run this script again.
  pause
  exit /b 1
)
rem Resolve dependencies from the local wheelhouse only.
set "PIP_NO_INDEX=1"
set "PIP_FIND_LINKS=%~dp0wheelhouse"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
call "%~dp0setup_sender.cmd"
exit /b %errorlevel%
