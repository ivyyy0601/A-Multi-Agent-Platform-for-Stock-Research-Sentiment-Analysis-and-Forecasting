"""Adanos API client — Reddit, Twitter/X, News sentiment for stocks."""

import time
import requests
from typing import Optional

import os

BASE_URL = "https://api.adanos.org"
API_KEY = os.environ.get("ADANOS_API_KEY", "")

HEADERS = {"X-API-Key": API_KEY}

TICKERS = [
    "GOOGL", "AAPL", "AMZN", "MSFT", "NVDA", "TSLA", "META",
    "AVGO", "TXN", "COHR", "INTC", "ASML", "SNDK", "XYZ",
]


def _get(path: str, params: dict = None, retries: int = 3) -> Optional[dict]:
    url = f"{BASE_URL}{path}"
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt == retries - 1:
                print(f"  API error {path}: {e}")
            time.sleep(1)
    return None


def get_reddit_stock(ticker: str, days: int = 90) -> Optional[dict]:
    return _get(f"/reddit/stocks/v1/stock/{ticker}", {"days": days})


def get_twitter_stock(ticker: str, days: int = 90) -> Optional[dict]:
    return _get(f"/x/stocks/v1/stock/{ticker}", {"days": days})


def get_news_stock(ticker: str, days: int = 90) -> Optional[dict]:
    return _get(f"/news/stocks/v1/stock/{ticker}", {"days": days})


def get_reddit_explain(ticker: str) -> Optional[str]:
    data = _get(f"/reddit/stocks/v1/stock/{ticker}/explain")
    return data.get("explanation") if data else None


def get_news_explain(ticker: str) -> Optional[str]:
    data = _get(f"/news/stocks/v1/stock/{ticker}/explain")
    return data.get("explanation") if data else None


def get_all_platforms(ticker: str, days: int = 90) -> dict:
    """Fetch all 3 platforms for a ticker. Returns dict with reddit/twitter/news keys."""
    return {
        "reddit":  get_reddit_stock(ticker, days),
        "twitter": get_twitter_stock(ticker, days),
        "news":    get_news_stock(ticker, days),
    }
