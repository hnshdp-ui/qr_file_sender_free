@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" || exit /b 1

rem Probe interpreters, not just PATH entries: Windows aliases can be unusable.
for %%P in ("py -3" python python3) do (
  %%~P -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
  if not errorlevel 1 (
    set "sender_python=%%~P"
    goto download
  )
)
echo No working Python 3.10+ interpreter was found. Install Python with pip and add it to PATH.
goto setup_error

:download
%sender_python% -c "import sys; from sysconfig import get_platform; print('Preparing wheels for Python', sys.version.split()[0], 'on', get_platform())"
%sender_python% -m pip --disable-pip-version-check download --only-binary=:all: --dest wheelhouse -r requirements.txt
if errorlevel 1 goto setup_error

echo.
echo Offline wheels are ready in wheelhouse.
echo Copy the project with wheelhouse to a PC with the same Python major/minor version and architecture.
echo Leave .venv behind if present. Run run_sender.cmd on the destination PC.
popd
pause
exit /b 0

:setup_error
echo Setup failed. Check the messages above and run setup_sender.cmd again on a connected PC.
popd
pause
exit /b 1
