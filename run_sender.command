#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR"

if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python -m sender "$@"
fi

print -u2 "QR File Sender Free is not set up yet."
print -u2 "Run setup_sender.command first."
exit 1
