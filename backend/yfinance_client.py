from __future__ import annotations

from typing import Any, Dict, Optional


def _scalar(row, key: str):
    value = row.get(key)
    if value is None:
        return None
    # yfinance may return a MultiIndex-column row where selecting a label still yields a Series.
    if hasattr(value, "iloc"):
        if len(value) == 0:
            return None
        value = value.iloc[0]
    return value


def fetch_daily_ohlc(ticker: str, date: str) -> Optional[Dict[str, Any]]:
    """Fetch a single-day daily OHLC bar via yfinance."""
    try:
        import yfinance as yf
        import pandas as pd
    except Exception:
        return None

    start = date
    end = date
    # yfinance end is exclusive for daily downloads; use +1 day window.
    dt = pd.Timestamp(date)
    end_exclusive = (dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    df = yf.download(
        ticker.upper(),
        start=start,
        end=end_exclusive,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if df is None or df.empty:
        return None

    if getattr(df.columns, "nlevels", 1) > 1:
        df.columns = df.columns.get_level_values(0)
    if df.empty:
        return None

    row = df.iloc[-1]
    row_date = df.index[-1].strftime("%Y-%m-%d")
    if row_date != date:
        return None

    volume = _scalar(row, "Volume")
    open_ = _scalar(row, "Open")
    high = _scalar(row, "High")
    low = _scalar(row, "Low")
    close = _scalar(row, "Close")
    return {
        "date": date,
        "open": float(open_) if open_ is not None else None,
        "high": float(high) if high is not None else None,
        "low": float(low) if low is not None else None,
        "close": float(close) if close is not None else None,
        "volume": float(volume) if volume is not None else None,
        "vwap": None,
        "transactions": None,
        "source": "yfinance",
    }
