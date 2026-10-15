#!/bin/zsh
set -e

ROOT="/Users/ivy_ai/Desktop/IvyTrader"
OPENBB_PYTHON="/Users/ivy_ai/OpenBB/conda/envs/openbb/bin/python"

cd "$ROOT"
"$OPENBB_PYTHON" -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 &
MAIN_PID=$!

cd "$ROOT/backend_analysis"
"$ROOT/backend_analysis/venv/bin/uvicorn" server:app --host 127.0.0.1 --port 8001 &
ANALYSIS_PID=$!

cd "$ROOT/frontend"
node node_modules/vite/dist/node/cli.js &
FRONTEND_PID=$!

cleanup() {
  echo
  echo "Stopping local services..."
  kill "$MAIN_PID" "$ANALYSIS_PID" "$FRONTEND_PID" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

echo "main backend:     http://127.0.0.1:8000"
echo "analysis backend: http://127.0.0.1:8001"
echo "frontend:         http://127.0.0.1:7777"
echo
echo "Press Ctrl+C to stop all services."

wait
