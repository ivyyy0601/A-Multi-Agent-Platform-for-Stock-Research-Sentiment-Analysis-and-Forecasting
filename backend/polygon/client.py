import time
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional
import requests

from backend.config import settings

BASE = "https://api.polygon.io"
EASTERN = ZoneInfo("America/New_York")


def _headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {settings.polygon_api_key}"}


def http_get(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    max_retries: int = 8,
    backoff: float = 2.0,
) -> requests.Response:
    """HTTP GET with exponential backoff and 429 handling."""
    for i in range(max_retries):
        try:
            resp = requests.get(
                url, params=params or {}, headers=_headers(), timeout=30
            )
        except requests.RequestException:
            time.sleep((backoff**i) + 0.5)
            if i == max_retries - 1:
                raise
            continue

        if resp.status_code == 429:
            ra = resp.headers.get("Retry-After")
            wait = float(ra) if (ra and ra.isdigit()) else min((backoff**i) + 1.0, 60.0)
            time.sleep(wait)
            if i == max_retries - 1:
                resp.raise_for_status()
            continue

        if 500 <= resp.status_code < 600:
            time.sleep(min((backoff**i) + 1.0, 60.0))
            if i == max_retries - 1:
                resp.raise_for_status()
            continue

        resp.raise_for_status()
        return resp
    raise RuntimeError("Unreachable")


def fetch_ohlc(ticker: str, start: str, end: str) -> List[Dict[str, Any]]:
    """Fetch daily OHLC data from Polygon."""
    url = f"{BASE}/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000}
    resp = http_get(url, params=params)
    results = resp.json().get("results") or []
    rows = []
    for r in results:
        d = datetime.fromtimestamp(int(r["t"]) / 1000, tz=timezone.utc).date().isoformat()
        rows.append(
            {
                "date": d,
                "open": r.get("o"),
                "high": r.get("h"),
                "low": r.get("l"),
                "close": r.get("c"),
                "volume": r.get("v"),
                "vwap": r.get("vw"),
                "transactions": r.get("n"),
            }
        )
    return rows


def fetch_intraday_ohlc_from_minutes(ticker: str, date: str) -> Optional[Dict[str, Any]]:
    """Build a provisional daily OHLC row from 1-minute aggregates for a single date."""
    url = f"{BASE}/v2/aggs/ticker/{ticker}/range/1/minute/{date}/{date}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000}
    resp = http_get(url, params=params)
    results = resp.json().get("results") or []
    if not results:
        return None

    first = results[0]
    last = results[-1]
    total_volume = sum(float(r.get("v") or 0) for r in results)
    weighted_vwap_num = sum(float(r.get("vw") or 0) * float(r.get("v") or 0) for r in results if r.get("vw") is not None)
    total_transactions = sum(int(r.get("n") or 0) for r in results)

    return {
        "date": date,
        "open": first.get("o"),
        "high": max(float(r.get("h") or 0) for r in results),
        "low": min(float(r.get("l") or 0) for r in results),
        "close": last.get("c"),
        "volume": total_volume,
        "vwap": (weighted_vwap_num / total_volume) if total_volume > 0 else last.get("vw"),
        "transactions": total_transactions,
    }


def should_try_provisional_daily_bar(date_str: str) -> bool:
    """Return True when it's reasonable to expect today's bar from intraday minute data."""
    target = datetime.fromisoformat(date_str).date()
    now_et = datetime.now(EASTERN)
    if target != now_et.date():
        return False
    if now_et.weekday() >= 5:
        return False
    # Wait a bit past the close so late minute bars have time to settle.
    return (now_et.hour, now_et.minute) >= (16, 15)


def fetch_news(
    ticker: str,
    start: str,
    end: str,
    per_page: int = 50,
    page_sleep: float = 1.2,
    max_pages: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch all news for a ticker from Polygon, with pagination."""
    url = f"{BASE}/v2/reference/news"
    params = {
        "ticker": ticker,
        "published_utc.gte": start,
        "published_utc.lte": end,
        "limit": per_page,
        "order": "asc",
    }
    all_articles: List[Dict[str, Any]] = []
    seen_ids: set = set()
    pages = 0
    next_url: Optional[str] = None

    while True:
        resp = http_get(next_url or url, params=None if next_url else params)
        data = resp.json()
        for r in data.get("results", []) or []:
            rid = r.get("id")
            if rid and rid in seen_ids:
                continue
            article = {
                "id": rid,
                "publisher": (r.get("publisher") or {}).get("name"),
                "title": r.get("title"),
                "author": r.get("author"),
                "published_utc": r.get("published_utc"),
                "amp_url": r.get("amp_url"),
                "article_url": r.get("article_url"),
                "tickers": r.get("tickers"),
                "description": r.get("description"),
                "insights": r.get("insights"),
            }
            all_articles.append(article)
            if rid:
                seen_ids.add(rid)

        next_url = data.get("next_url")
        pages += 1
        if max_pages is not None and pages >= max_pages:
            break
        if not next_url:
            break
        time.sleep(page_sleep)

    return all_articles


def search_tickers(query: str, limit: int = 20) -> List[Dict[str, str]]:
    """Search tickers from Polygon reference endpoint."""
    url = f"{BASE}/v3/reference/tickers"
    params = {"search": query, "active": "true", "limit": limit, "market": "stocks"}
    resp = http_get(url, params=params)
    results = resp.json().get("results") or []
    return [
        {
            "symbol": r.get("ticker", ""),
            "name": r.get("name", ""),
            "sector": r.get("sic_description", ""),
        }
        for r in results
    ]
