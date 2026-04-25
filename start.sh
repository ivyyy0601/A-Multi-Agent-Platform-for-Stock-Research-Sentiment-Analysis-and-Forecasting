#!/bin/bash
# IvyTrader — Unified Start Script
# Starts all services: main backend, analysis backend, frontend

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
MAIN_PYTHON="$ROOT/.venv311/bin/python"
if [ ! -x "$MAIN_PYTHON" ]; then
  MAIN_PYTHON="$ROOT/.venv/bin/python"
fi

echo "=== IvyTrader Starting ==="

# Load .env
if [ -f "$ROOT/.env" ]; then
  set -a
  source "$ROOT/.env"
  set +a
fi

# ── 1. Main backend (PokieTicker — port 8000) ────────────────────
echo "[1/3] Starting main backend (port 8000)..."
cd "$ROOT"
"$MAIN_PYTHON" -m uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 &
MAIN_BACKEND_PID=$!

# ── 2. Analysis backend (port 8001) ──────────────────────────────
echo "[2/3] Starting analysis backend (port 8001)..."
cd "$ROOT/backend_analysis"
venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001 &
ANALYSIS_BACKEND_PID=$!

# ── 3. Frontend (Vite — port 7777) ───────────────────────────────
echo "[3/3] Starting frontend (port 7777)..."
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "=== All services started ==="
echo "  Frontend:          http://localhost:7777"
echo "  Main backend:      http://localhost:8000"
echo "  Analysis backend:  http://localhost:8001"
echo ""
echo "Press Ctrl+C to stop all services."

# Cleanup on exit
trap "echo 'Stopping...'; kill $MAIN_BACKEND_PID $ANALYSIS_BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

wait
