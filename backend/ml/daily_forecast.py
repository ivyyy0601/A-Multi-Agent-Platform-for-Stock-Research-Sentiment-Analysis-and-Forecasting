"""Generate cached detail forecasts for all tickers and 1D/7D/14D windows."""

from __future__ import annotations

import argparse

from backend.database import get_conn, init_db
from backend.ml.forecast_store import save_forecast
from backend.ml.inference import generate_forecast

WINDOWS = (1, 7, 14)


def _db_symbols() -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT symbol FROM tickers WHERE last_ohlc_fetch IS NOT NULL ORDER BY symbol"
    ).fetchall()
    conn.close()
    return [str(r["symbol"]).upper() for r in rows]


def run(symbol: str | None = None) -> dict:
    init_db(verbose=False)
    symbols = [symbol.upper()] if symbol else _db_symbols()
    success = 0
    errors: dict[str, dict[str, str]] = {}

    for sym in symbols:
        for window in WINDOWS:
            result = generate_forecast(sym, window)
            if "error" in result:
                errors.setdefault(sym, {})[str(window)] = str(result["error"])
                continue
            save_forecast(result)
            success += 1

    summary = {
        "symbols": len(symbols),
        "windows_per_symbol": len(WINDOWS),
        "success": success,
        "errors": errors,
    }
    print(summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, default=None)
    args = parser.parse_args()
    run(args.symbol)


if __name__ == "__main__":
    main()
