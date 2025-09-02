#!/usr/bin/env bash
set -euo pipefail

if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate || true
fi

export PYTHONUNBUFFERED=1
python -m src.main
