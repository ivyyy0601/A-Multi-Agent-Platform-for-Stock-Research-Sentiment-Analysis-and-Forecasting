#!/bin/bash
# Collect Anthropic Batch results, then retrain ML models.
# Scheduled ~4 hours after daily_update.sh (e.g. 9PM).
# If batch not done yet, retries every 30 min up to 3 times.

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
set -euo pipefail

export DATABASE_PATH="$ROOT/pokieticker.db"
export PYTHONUNBUFFERED=1
if [ -f "$ROOT/.env" ]; then
  set -a
  . "$ROOT/.env"
  set +a
fi
MAIN_PYTHON="$ROOT/.venv311/bin/python"
if [ ! -x "$MAIN_PYTHON" ]; then
  MAIN_PYTHON="$ROOT/.venv/bin/python"
fi

RUN_ID=""
mark_failed() {
  local line_no="${1:-unknown}"
  local exit_code="${2:-1}"
  if [ -n "${RUN_ID}" ]; then
    "$MAIN_PYTHON" -m backend.automation.status fail \
      --run-id "$RUN_ID" \
      --message "batch_collect failed at line ${line_no} (exit ${exit_code})" >/dev/null 2>&1 || true
  fi
}
trap 'mark_failed ${LINENO} $?' ERR

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/collect_$(date +%Y%m%d).log"

echo "=== $(date) ===" >> "$LOG_FILE"
RUN_ID=$("$MAIN_PYTHON" -m backend.automation.status start --pipeline batch_collect --step check_batch --message "Checking batch status")

MAX_RETRIES=3
RETRY_INTERVAL=1800  # 30 minutes

for i in $(seq 1 $MAX_RETRIES); do
    echo "[attempt $i/$MAX_RETRIES] Checking batch status..." >> "$LOG_FILE"
    "$MAIN_PYTHON" -m backend.automation.status update --run-id "$RUN_ID" --step check_batch --message "Checking batch status (attempt $i/$MAX_RETRIES)" >/dev/null

    # Run batch_collect — exits cleanly if still in_progress
    OUTPUT=$("$MAIN_PYTHON" -m backend.batch_collect 2>&1)
    echo "$OUTPUT" >> "$LOG_FILE"

    if echo "$OUTPUT" | grep -q "All batch jobs already collected\|Batch completed"; then
        break
    fi

    if echo "$OUTPUT" | grep -q "still processing"; then
        if [ $i -lt $MAX_RETRIES ]; then
            echo "Batch still processing. Retrying in 30 min..." >> "$LOG_FILE"
            sleep $RETRY_INTERVAL
        fi
    else
        break
    fi
done

# Check if collect actually succeeded before training
if "$MAIN_PYTHON" -c "
from backend.database import get_conn
conn = get_conn()
job = conn.execute(\"SELECT status FROM batch_jobs ORDER BY created_at DESC LIMIT 1\").fetchone()
conn.close()
exit(0 if job and job['status'] == 'collected' else 1)
" 2>/dev/null; then
    echo "[ML] Retraining XGBoost models..." >> "$LOG_FILE"
    "$MAIN_PYTHON" -m backend.automation.status update --run-id "$RUN_ID" --step train_detail --message "Training detail models" >/dev/null
    "$MAIN_PYTHON" -m backend.ml.train >> "$LOG_FILE" 2>&1
    echo "[ML] Training complete." >> "$LOG_FILE"

    echo "[ML] Retraining adanos social model..." >> "$LOG_FILE"
    "$MAIN_PYTHON" -m backend.automation.status update --run-id "$RUN_ID" --step train_social --message "Training social model" >/dev/null
    "$MAIN_PYTHON" -m backend.adanos.model >> "$LOG_FILE" 2>&1
    echo "[ML] Adanos model complete." >> "$LOG_FILE"

    echo "[ML] Generating cached adanos forecasts..." >> "$LOG_FILE"
    "$MAIN_PYTHON" -m backend.automation.status update --run-id "$RUN_ID" --step cache_social_forecast --message "Caching social forecasts" >/dev/null
    "$MAIN_PYTHON" -m backend.adanos.daily_forecast >> "$LOG_FILE" 2>&1
    echo "[ML] Adanos forecast cache complete." >> "$LOG_FILE"
    "$MAIN_PYTHON" -m backend.automation.status finish --run-id "$RUN_ID" --message "Batch collect and model training completed" >/dev/null
else
    echo "[ML] Skipping training — batch not yet collected." >> "$LOG_FILE"
    "$MAIN_PYTHON" -m backend.automation.status finish --run-id "$RUN_ID" --message "Batch not collected yet; training skipped" >/dev/null
fi

echo "=== Done $(date) ===" >> "$LOG_FILE"
