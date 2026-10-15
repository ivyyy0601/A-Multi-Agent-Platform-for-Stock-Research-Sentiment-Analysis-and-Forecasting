"""Finnhub company news fetcher — supplements Polygon news data.

Fetches ticker-specific news from Finnhub and inserts into the same
news_raw / news_ticker tables, then runs alignment + layer0.

Usage:
  python -m backend.finnhub_fetch --symbol AAPL --from 2026-03-01 --to 2026-03-18
  python -m backend.finnhub_fetch --symbol AAPL  # defaults to last 7 days
"""

import json
import re
import argparse
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.config import settings
from backend.database import get_conn
from backend.pipeline.alignment import align_news_for_symbol
from backend.pipeline.layer0 import run_layer0

# Load ticker → name mapping
_NAMES_PATH = Path(__file__).parent / "ticker_names.json"
with open(_NAMES_PATH) as f:
    TICKER_NAMES: dict[str, list[str]] = json.load(f)


def _mentions_company(symbol: str, headline: str, summary: str) -> bool:
    """Return True if headline or summary mentions the company by any known name."""
    names = TICKER_NAMES.get(symbol.upper(), [symbol])
    text = f"{headline} {summary}".lower()
    for name in names:
        # Word-boundary match, case-insensitive
        if re.search(r'\b' + re.escape(name.lower()) + r'\b', text):
            return True
    return False

FINNHUB_BASE = "https://finnhub.io/api/v1"
FINNHUB_KEY = "d6ue079r01qp1k9c6lg0d6ue079r01qp1k9c6lgg"


def fetch_finnhub_news(symbol: str, date_from: str, date_to: str) -> list[dict]:
    """Call Finnhub /company-news and return raw results."""
    resp = requests.get(
        f"{FINNHUB_BASE}/company-news",
        params={
            "symbol": symbol,
            "from": date_from,
            "to": date_to,
            "token": FINNHUB_KEY,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json() or []


def unix_to_utc(ts: int) -> str:
    """Convert UNIX timestamp to ISO 8601 UTC string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_finnhub_news(symbol: str, articles: list[dict]) -> tuple[int, int]:
    """Insert Finnhub articles into news_raw + news_ticker, skip duplicates.
    Returns (inserted, skipped_no_mention).
    """
    if not articles:
        return 0, 0

    conn = get_conn()
    inserted = 0
    skipped_mention = 0

    for art in articles:
        fh_id = art.get("id")
        if not fh_id:
            continue

        # Filter: headline or summary must mention the company
        headline = art.get("headline") or ""
        summary = art.get("summary") or ""
        if not _mentions_company(symbol, headline, summary):
            skipped_mention += 1
            continue

        # Prefix to avoid collision with Polygon IDs
        news_id = f"finnhub_{fh_id}"

        published_utc = unix_to_utc(art["datetime"]) if art.get("datetime") else None
        tickers = [symbol]  # Finnhub company-news is ticker-specific

        result = conn.execute(
            """INSERT OR IGNORE INTO news_raw
               (id, title, description, publisher, author,
                published_utc, article_url, amp_url, tickers_json, insights_json, image_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                news_id,
                art.get("headline"),
                art.get("summary"),
                art.get("source"),
                None,                          # Finnhub doesn't provide author
                published_utc,
                art.get("url"),
                None,                          # no amp_url
                json.dumps(tickers),
                None,                          # no insights
                art.get("image"),
            ),
        )

        if result.rowcount > 0:
            conn.execute(
                "INSERT OR IGNORE INTO news_ticker (news_id, symbol) VALUES (?, ?)",
                (news_id, symbol),
            )
            inserted += 1

    conn.commit()
    conn.close()
    return inserted, skipped_mention


def run(symbol: str, date_from: str, date_to: str):
    symbol = symbol.upper()
    print(f"Fetching Finnhub news for {symbol}: {date_from} → {date_to}")

    articles = fetch_finnhub_news(symbol, date_from, date_to)
    print(f"  Received {len(articles)} articles from Finnhub")

    inserted, skipped_mention = insert_finnhub_news(symbol, articles)
    skipped_dup = len(articles) - inserted - skipped_mention
    print(f"  Inserted {inserted} | Filtered (no mention) {skipped_mention} | Duplicates {skipped_dup}")

    if inserted > 0:
        align_news_for_symbol(symbol)
        l0 = run_layer0(symbol)
        print(f"  Layer0: {l0.get('passed', 0)} passed filter")

    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--from", dest="date_from", default=None)
    parser.add_argument("--to", dest="date_to", default=None)
    args = parser.parse_args()

    today = datetime.now(timezone.utc).date().isoformat()
    date_from = args.date_from or (datetime.now(timezone.utc).date() - timedelta(days=7)).isoformat()
    date_to = args.date_to or today

    run(args.symbol, date_from, date_to)
