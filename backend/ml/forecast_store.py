"""Persistence helpers for cached detail forecasts."""

from __future__ import annotations

import json
from datetime import datetime

from backend.database import get_conn


def save_forecast(result: dict) -> None:
    symbol = str(result["symbol"]).upper()
    window_days = int(result["window_days"])
    forecast_date = str(result["forecast_date"])
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO detail_forecasts (
            symbol, window_days, forecast_date, created_at, raw_json
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(symbol, window_days, forecast_date) DO UPDATE SET
            created_at=excluded.created_at,
            raw_json=excluded.raw_json
        """,
        (
            symbol,
            window_days,
            forecast_date,
            datetime.utcnow().isoformat(),
            json.dumps(result, ensure_ascii=True, sort_keys=True),
        ),
    )
    conn.commit()
    conn.close()


def load_latest_forecast(symbol: str, window_days: int) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        """
        SELECT raw_json
        FROM detail_forecasts
        WHERE symbol = ? AND window_days = ?
        ORDER BY forecast_date DESC
        LIMIT 1
        """,
        (symbol.upper(), int(window_days)),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return json.loads(row["raw_json"])


def load_forecast_on_or_before(symbol: str, window_days: int, ref_date: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        """
        SELECT raw_json
        FROM detail_forecasts
        WHERE symbol = ? AND window_days = ? AND forecast_date <= ?
        ORDER BY forecast_date DESC
        LIMIT 1
        """,
        (symbol.upper(), int(window_days), str(ref_date)),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return json.loads(row["raw_json"])
