#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [ -d ".venv" ]; then
  source .venv/bin/activate
else
  python3 -m venv .venv
  source .venv/bin/activate
fi

if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
fi

exec PYTHONPATH=src python -m ui.app
