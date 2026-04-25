"""Generate cached daily adanos forecasts for all tickers."""

from __future__ import annotations

import argparse

from backend.adanos.forecast_store import save_forecast
from backend.adanos.inference import generate_forecast
from backend.database import get_conn


def _db_tickers() -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT ticker FROM platform_sentiment ORDER BY ticker"
    ).fetchall()
    conn.close()
    return [str(r["ticker"]) for r in rows]


def run(ticker: str | None = None) -> dict:
    tickers = [ticker.upper()] if ticker else _db_tickers()
    success = 0
    errors: dict[str, str] = {}

    for symbol in tickers:
        result = generate_forecast(symbol)
        if "error" in result:
            errors[symbol] = str(result["error"])
            continue
        save_forecast(result)
        success += 1

    summary = {
        "tickers": len(tickers),
        "success": success,
        "errors": errors,
    }
    print(summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", type=str, default=None)
    args = parser.parse_args()
    run(args.ticker)


if __name__ == "__main__":
    main()
