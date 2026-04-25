from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import requests

from backend.config import settings

BASE = "https://data.alpaca.markets/v2"


def has_credentials() -> bool:
    return bool(settings.alpaca_api_key_id and settings.alpaca_api_secret_key)


def _headers() -> Dict[str, str]:
    return {
        "APCA-API-KEY-ID": settings.alpaca_api_key_id,
        "APCA-API-SECRET-KEY": settings.alpaca_api_secret_key,
    }


def fetch_intraday_ohlc_from_minutes(ticker: str, date: str) -> Optional[Dict[str, Any]]:
    """Build a provisional daily OHLC row from Alpaca 1-minute bars for a single date."""
    if not has_credentials():
        return None

    start = f"{date}T09:30:00-04:00"
    end = f"{date}T16:15:00-04:00"
    url = f"{BASE}/stocks/{ticker.upper()}/bars"
    params = {
        "timeframe": "1Min",
        "start": start,
        "end": end,
        "adjustment": "all",
        "feed": "iex",
        "limit": 10000,
        "sort": "asc",
    }
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    bars = data.get("bars") or []
    if not bars:
        return None

    first = bars[0]
    last = bars[-1]
    total_volume = sum(float(b.get("v") or 0) for b in bars)
    weighted_vwap_num = sum(float(b.get("vw") or 0) * float(b.get("v") or 0) for b in bars if b.get("vw") is not None)
    total_transactions = sum(int(b.get("n") or 0) for b in bars)

    return {
        "date": date,
        "open": first.get("o"),
        "high": max(float(b.get("h") or 0) for b in bars),
        "low": min(float(b.get("l") or 0) for b in bars),
        "close": last.get("c"),
        "volume": total_volume,
        "vwap": (weighted_vwap_num / total_volume) if total_volume > 0 else last.get("vw"),
        "transactions": total_transactions,
        "source": "alpaca",
    }
