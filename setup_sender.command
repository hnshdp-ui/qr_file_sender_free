#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  print -u2 "Python 3.10 or newer is required for QR File Sender Free."
  print -u2 "Install Python from https://www.python.org/downloads/macos/ and run this again."
  exit 1
fi

if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
  print -u2 "Python 3.10 or newer is required."
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  print "Creating repository-local virtual environment..."
  python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
print "Setup complete. Run run_sender.command next."
