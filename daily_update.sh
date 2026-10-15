#!/bin/bash
# Daily update: run after US market close (5 PM ET)
# Step 1: fetch latest OHLC + news, submit Anthropic Batch
# Step 2 (next morning): collect batch results
# Step 3: retrain ML models (optional, can skip if running weekly)

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
set -euo pipefail

export DATABASE_PATH="$ROOT/pokieticker.db"
export PYTHONUNBUFFERED=1
MIN_OHLC_COVERAGE="${MIN_OHLC_COVERAGE:-100}"
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
      --message "daily_update failed at line ${line_no} (exit ${exit_code})" >/dev/null 2>&1 || true
  fi
}
trap 'mark_failed ${LINENO} $?' ERR

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_$(date +%Y%m%d).log"

echo "=== $(date) ===" >> "$LOG_FILE"
RUN_ID=$("$MAIN_PYTHON" -m backend.automation.status start --pipeline daily_update --step start --message "Daily update started")

echo "[1/2] Fetching latest data..." >> "$LOG_FILE"
"$MAIN_PYTHON" -m backend.automation.status update --run-id "$RUN_ID" --step fetch_recent --message "Fetching latest OHLC and news" >/dev/null
"$MAIN_PYTHON" -m backend.update_recent --days 2 >> "$LOG_FILE" 2>&1

echo "[1.5/2] Verifying latest OHLC coverage and retrying missing tickers..." >> "$LOG_FILE"
"$MAIN_PYTHON" -m backend.automation.status update --run-id "$RUN_ID" --step ensure_ohlc --message "Verifying OHLC coverage" >/dev/null
"$MAIN_PYTHON" -m backend.ensure_recent_ohlc >> "$LOG_FILE" 2>&1

COVERAGE_INFO=$("$MAIN_PYTHON" - <<'PYEOF'
from backend.database import get_conn
conn = get_conn()
target = conn.execute("SELECT MAX(date) AS max_date FROM ohlc").fetchone()["max_date"]
tracked = conn.execute("SELECT COUNT(*) AS c FROM tickers").fetchone()["c"]
covered = conn.execute(
    "SELECT COUNT(DISTINCT symbol) AS c FROM ohlc WHERE date = ?",
    (target,),
).fetchone()["c"]
conn.close()
print(f"{target}|{tracked}|{covered}")
PYEOF
)
TARGET_DATE=$(echo "$COVERAGE_INFO" | cut -d'|' -f1)
TRACKED_COUNT=$(echo "$COVERAGE_INFO" | cut -d'|' -f2)
COVERED_COUNT=$(echo "$COVERAGE_INFO" | cut -d'|' -f3)
echo "[1.6/2] OHLC coverage for ${TARGET_DATE}: ${COVERED_COUNT}/${TRACKED_COUNT} (threshold ${MIN_OHLC_COVERAGE})" >> "$LOG_FILE"
"$MAIN_PYTHON" -m backend.automation.status update \
  --run-id "$RUN_ID" \
  --step ensure_ohlc \
  --message "OHLC coverage ${COVERED_COUNT}/${TRACKED_COUNT} for ${TARGET_DATE}" \
  --details-json "{\"target_date\":\"${TARGET_DATE}\",\"tracked\":${TRACKED_COUNT},\"covered\":${COVERED_COUNT},\"threshold\":${MIN_OHLC_COVERAGE}}" >/dev/null

if [ "$COVERED_COUNT" -lt "$MIN_OHLC_COVERAGE" ]; then
  "$MAIN_PYTHON" -m backend.automation.status fail \
    --run-id "$RUN_ID" \
    --message "OHLC coverage below threshold: ${COVERED_COUNT}/${TRACKED_COUNT} for ${TARGET_DATE} (min ${MIN_OHLC_COVERAGE})" \
    --details-json "{\"target_date\":\"${TARGET_DATE}\",\"tracked\":${TRACKED_COUNT},\"covered\":${COVERED_COUNT},\"threshold\":${MIN_OHLC_COVERAGE}}" >/dev/null
  echo "=== Stopped: OHLC coverage below threshold (${COVERED_COUNT}/${TRACKED_COUNT}, min ${MIN_OHLC_COVERAGE}) ===" >> "$LOG_FILE"
  exit 1
fi

echo "[2/2] Submitting to Anthropic Batch API..." >> "$LOG_FILE"
"$MAIN_PYTHON" -m backend.automation.status update --run-id "$RUN_ID" --step submit_batch --message "Submitting Anthropic batch" >/dev/null
"$MAIN_PYTHON" -m backend.batch_submit >> "$LOG_FILE" 2>&1

"$MAIN_PYTHON" -m backend.automation.status finish \
  --run-id "$RUN_ID" \
  --message "Daily update completed" \
  --details-json "{\"target_date\":\"${TARGET_DATE}\",\"tracked\":${TRACKED_COUNT},\"covered\":${COVERED_COUNT},\"threshold\":${MIN_OHLC_COVERAGE}}" >/dev/null
echo "=== Done $(date) — batch_collect will auto-run ~midnight and train ML after ===" >> "$LOG_FILE"
