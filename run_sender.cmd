@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo QR File Sender Free is not set up yet.
  echo Run setup_sender.cmd first.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m sender %*
set "sender_result=%errorlevel%"
if not "%sender_result%"=="0" pause
exit /b %sender_result%
