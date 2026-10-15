"""Persistence helpers for cached adanos forecasts and model runs."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from backend.database import get_conn


def _next_weekday(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    dt += timedelta(days=1)
    while dt.weekday() >= 5:
        dt += timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def save_model_run(meta: dict) -> None:
    run_date = str(meta.get("run_date") or meta.get("trained_at", "")[:10])
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO adanos_model_runs (
            run_date, ticker_scope, model_type, selected_params_json,
            lr_accuracy, walkforward_accuracy, baseline, n_rows,
            trained_at, meta_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_date) DO UPDATE SET
            ticker_scope=excluded.ticker_scope,
            model_type=excluded.model_type,
            selected_params_json=excluded.selected_params_json,
            lr_accuracy=excluded.lr_accuracy,
            walkforward_accuracy=excluded.walkforward_accuracy,
            baseline=excluded.baseline,
            n_rows=excluded.n_rows,
            trained_at=excluded.trained_at,
            meta_json=excluded.meta_json
        """,
        (
            run_date,
            str(meta.get("name", "UNIFIED")),
            str(meta.get("model_type", "logistic_regression")),
            json.dumps(meta.get("selected_params", {}), ensure_ascii=True, sort_keys=True),
            meta.get("lr_accuracy"),
            meta.get("walkforward_accuracy"),
            meta.get("baseline"),
            meta.get("n_rows"),
            str(meta.get("trained_at", "")),
            json.dumps(meta, ensure_ascii=True, sort_keys=True),
        ),
    )
    conn.commit()
    conn.close()


def save_forecast(result: dict) -> None:
    forecast_date = str(result["forecast_date"])
    target_date = str(result.get("target_date") or _next_weekday(forecast_date))
    prediction = result.get("prediction", {})
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO adanos_forecasts (
            ticker, forecast_date, target_date, created_at,
            direction, confidence, lr_p_up, cosine_up_ratio,
            cosine_avg_ret, cosine_weighted_ret, overall, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, forecast_date) DO UPDATE SET
            target_date=excluded.target_date,
            created_at=excluded.created_at,
            direction=excluded.direction,
            confidence=excluded.confidence,
            lr_p_up=excluded.lr_p_up,
            cosine_up_ratio=excluded.cosine_up_ratio,
            cosine_avg_ret=excluded.cosine_avg_ret,
            cosine_weighted_ret=excluded.cosine_weighted_ret,
            overall=excluded.overall,
            raw_json=excluded.raw_json
        """,
        (
            str(result["ticker"]),
            forecast_date,
            target_date,
            datetime.utcnow().isoformat(),
            str(prediction.get("direction", "")),
            prediction.get("confidence"),
            prediction.get("lr_p_up"),
            prediction.get("cosine_up_ratio"),
            prediction.get("cosine_avg_ret"),
            prediction.get("cosine_weighted_ret"),
            result.get("overall"),
            json.dumps({**result, "target_date": target_date}, ensure_ascii=True, sort_keys=True),
        ),
    )
    conn.commit()
    conn.close()


def get_latest_feature_dates(ticker: str) -> dict:
    ticker = ticker.upper()
    conn = get_conn()
    row = conn.execute(
        """
        SELECT
          (SELECT MAX(date) FROM ohlc WHERE symbol = ?) AS max_ohlc_date,
          (SELECT MAX(date) FROM platform_sentiment WHERE ticker = ?) AS max_sentiment_date
        """,
        (ticker, ticker),
    ).fetchone()
    conn.close()

    max_ohlc_date = row["max_ohlc_date"] if row else None
    max_sentiment_date = row["max_sentiment_date"] if row else None
    common_date = None
    if max_ohlc_date and max_sentiment_date:
        common_date = min(max_ohlc_date, max_sentiment_date)

    return {
        "ticker": ticker,
        "max_ohlc_date": max_ohlc_date,
        "max_sentiment_date": max_sentiment_date,
        "common_date": common_date,
        "aligned": bool(max_ohlc_date and max_sentiment_date and max_ohlc_date == max_sentiment_date),
    }


def load_latest_forecast(ticker: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        """
        SELECT raw_json
        FROM adanos_forecasts
        WHERE ticker = ?
        ORDER BY forecast_date DESC
        LIMIT 1
        """,
        (ticker.upper(),),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return json.loads(row["raw_json"])
