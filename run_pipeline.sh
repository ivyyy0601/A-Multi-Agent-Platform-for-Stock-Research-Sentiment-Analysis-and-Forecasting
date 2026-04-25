#!/bin/bash
# Full pipeline: update data → Layer1 batch → collect → train models
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$ROOT/.venv311/bin/python"
LOG="$ROOT/pipeline_$(date +%Y%m%d_%H%M%S).log"

cd "$ROOT"

# Load .env
if [ -f "$ROOT/.env" ]; then
  set -a; source "$ROOT/.env"; set +a
fi

echo "=== IvyTrader Full Pipeline ===" | tee "$LOG"
echo "Started: $(date)" | tee -a "$LOG"
echo "" | tee -a "$LOG"

# ── Step 1: Update recent data (7 days) ──────────────────────────
echo "[Step 1/4] Fetching last 7 days of data..." | tee -a "$LOG"
"$PYTHON" -m backend.update_recent --days 7 2>&1 | tee -a "$LOG"
echo "[Step 1] Done." | tee -a "$LOG"
echo "" | tee -a "$LOG"

# ── Step 2: Submit batch to Anthropic API ─────────────────────────
echo "[Step 2/4] Submitting pending articles to Anthropic Batch API..." | tee -a "$LOG"
"$PYTHON" -m backend.batch_submit 2>&1 | tee -a "$LOG"
echo "[Step 2] Done." | tee -a "$LOG"
echo "" | tee -a "$LOG"

# ── Step 3: Poll until batch is complete, then collect ────────────
echo "[Step 3/4] Waiting for batch to complete (polling every 10 min)..." | tee -a "$LOG"

while true; do
  STATUS=$("$PYTHON" -m backend.batch_collect 2>&1 | tee -a "$LOG")

  if echo "$STATUS" | grep -q "All batch jobs already collected"; then
    echo "[Step 3] No pending batch (already collected or none submitted)." | tee -a "$LOG"
    break
  fi

  if echo "$STATUS" | grep -q "Batch completed\|=== Layer 1 Results ==="; then
    echo "[Step 3] Batch collected successfully." | tee -a "$LOG"
    break
  fi

  if echo "$STATUS" | grep -q "still processing\|in_progress"; then
    echo "  Batch still processing... waiting 10 minutes. ($(date '+%H:%M'))" | tee -a "$LOG"
    sleep 600
    continue
  fi

  # Any other status (ended but already collected, etc.)
  echo "[Step 3] Exiting poll loop." | tee -a "$LOG"
  break
done

echo "" | tee -a "$LOG"

# ── Step 4: Retrain ML models ─────────────────────────────────────
echo "[Step 4/4] Retraining XGBoost models for all tickers..." | tee -a "$LOG"
"$PYTHON" -m backend.ml.train 2>&1 | tee -a "$LOG"
echo "[Step 4] Done." | tee -a "$LOG"
echo "" | tee -a "$LOG"

echo "=== Pipeline Complete ===" | tee -a "$LOG"
echo "Finished: $(date)" | tee -a "$LOG"
echo "Log saved to: $LOG"
