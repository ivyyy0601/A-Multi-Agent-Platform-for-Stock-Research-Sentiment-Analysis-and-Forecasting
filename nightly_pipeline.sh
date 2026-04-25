#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export DATABASE_PATH="${DATABASE_PATH:-$ROOT/pokieticker.db}"
export PYTHONUNBUFFERED=1

if [ -f "$ROOT/.env" ]; then
  set -a
  . "$ROOT/.env"
  set +a
fi

export MAIN_PYTHON="${MAIN_PYTHON:-/Users/ivy_ai/OpenBB/conda/envs/openbb/bin/python}"
export FINBERT_PYTHON="${FINBERT_PYTHON:-$MAIN_PYTHON}"

exec "$MAIN_PYTHON" -m backend.automation.nightly
