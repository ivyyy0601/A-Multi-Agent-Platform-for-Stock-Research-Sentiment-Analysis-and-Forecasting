"""
Update recent data (last N days) from all sources:
  - Polygon OHLC + News
  - Finnhub
  - Reddit (public API, no auth)

Usage:
  python -m backend.update_recent          # last 3 days
  python -m backend.update_recent --days 7
  DATABASE_PATH=/path/to/db python -m backend.update_recent
"""

import argparse
import hashlib
import json
import re
import time
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

# ── DB ────────────────────────────────────────────────────────────────────────
from backend.database import get_conn
from backend.polygon.client import (
    http_get,
    BASE,
    fetch_ohlc,
    fetch_intraday_ohlc_from_minutes,
    should_try_provisional_daily_bar,
)
from backend.alpaca.client import (
    fetch_intraday_ohlc_from_minutes as fetch_intraday_ohlc_from_minutes_alpaca,
    has_credentials as has_alpaca_credentials,
)
from backend.yfinance_client import fetch_daily_ohlc as fetch_daily_ohlc_yfinance
from backend.finnhub_fetch import fetch_finnhub_news, insert_finnhub_news
from backend.pipeline.alignment import align_news_for_symbol
from backend.pipeline.layer0 import run_layer0

# ── Config ────────────────────────────────────────────────────────────────────
TODAY = datetime.now(timezone.utc).date().isoformat()

REDDIT_HEADERS = {"User-Agent": "pokieticker-bot/1.0 (finance data collection)"}
REDDIT_SUBREDDITS = [
    "stocks", "investing", "StockMarket", "wallstreetbets",
    "ValueInvesting", "Daytrading", "swingtrading", "options",
    "Trading", "wallstreet", "quant", "algotrading",
]
REDDIT_LIMIT = 100
REDDIT_MAX_PAGES = 3

POLYGON_RATE = []
MAX_PER_MIN = 5


# ── Polygon helpers ───────────────────────────────────────────────────────────

def _polygon_rate_limit():
    global POLYGON_RATE
    now = time.time()
    POLYGON_RATE = [t for t in POLYGON_RATE if now - t < 60]
    if len(POLYGON_RATE) >= MAX_PER_MIN:
        wait = 60 - (now - POLYGON_RATE[0]) + 0.5
        if wait > 0:
            print(f"    [Polygon] rate limit, waiting {wait:.1f}s...")
            time.sleep(wait)
    POLYGON_RATE.append(time.time())


def update_polygon_ohlc(symbol: str, start: str) -> int:
    if start > TODAY:
        return 0
    _polygon_rate_limit()
    try:
        rows = fetch_ohlc(symbol, start, TODAY)
    except Exception as e:
        print(f"    OHLC error: {e}")
        return 0
    latest_date = max((row["date"] for row in rows), default=None)
    if latest_date != TODAY and should_try_provisional_daily_bar(TODAY):
        provisional = None
        _polygon_rate_limit()
        try:
            provisional = fetch_intraday_ohlc_from_minutes(symbol, TODAY)
            if provisional:
                print("    Provisional daily bar from Polygon minute aggregates applied")
        except Exception as e:
            print(f"    Polygon provisional OHLC error: {e}")

        if provisional is None and has_alpaca_credentials():
            try:
                provisional = fetch_intraday_ohlc_from_minutes_alpaca(symbol, TODAY)
                if provisional:
                    print("    Provisional daily bar from Alpaca minute aggregates applied")
            except Exception as e:
                print(f"    Alpaca provisional OHLC error: {e}")

        if provisional is None:
            try:
                provisional = fetch_daily_ohlc_yfinance(symbol, TODAY)
                if provisional:
                    print("    Provisional daily bar from yfinance daily data applied")
            except Exception as e:
                print(f"    yfinance provisional OHLC error: {e}")

        if provisional:
            rows = [row for row in rows if row["date"] != TODAY]
            rows.append(provisional)
            latest_date = TODAY

    if not rows:
        return 0
    conn = get_conn()
    for row in rows:
        conn.execute(
            """INSERT INTO ohlc
               (symbol, date, open, high, low, close, volume, vwap, transactions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(symbol, date) DO UPDATE SET
                 open=excluded.open,
                 high=excluded.high,
                 low=excluded.low,
                 close=excluded.close,
                 volume=excluded.volume,
                 vwap=excluded.vwap,
                 transactions=excluded.transactions""",
            (symbol, row["date"], row["open"], row["high"], row["low"],
                row["close"], row["volume"], row["vwap"], row["transactions"]),
        )
    latest_date = max(row["date"] for row in rows)
    conn.execute("UPDATE tickers SET last_ohlc_fetch = ? WHERE symbol = ?", (latest_date, symbol))
    conn.commit()
    conn.close()
    return len(rows)


def update_polygon_news(symbol: str, start: str) -> int:
    if start > TODAY:
        return 0
    articles = []
    seen_ids = set()
    url = f"{BASE}/v2/reference/news"
    params = {
        "ticker": symbol,
        "published_utc.gte": start,
        "published_utc.lte": TODAY,
        "limit": 50,
        "order": "asc",
    }
    next_url = None
    while True:
        _polygon_rate_limit()
        try:
            resp = http_get(next_url or url, params=None if next_url else params)
        except Exception as e:
            print(f"    News error: {e}")
            break
        data = resp.json()
        for r in data.get("results") or []:
            rid = r.get("id")
            if rid and rid not in seen_ids:
                articles.append(r)
                seen_ids.add(rid)
        next_url = data.get("next_url")
        if not next_url:
            break

    if not articles:
        return 0

    conn = get_conn()
    for r in articles:
        rid = r.get("id")
        tickers = r.get("tickers") or []
        conn.execute(
            """INSERT OR IGNORE INTO news_raw
               (id, title, description, publisher, author,
                published_utc, article_url, amp_url, tickers_json, insights_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rid, r.get("title"), r.get("description"),
             (r.get("publisher") or {}).get("name"), r.get("author"),
             r.get("published_utc"), r.get("article_url"), r.get("amp_url"),
             json.dumps(tickers),
             json.dumps(r.get("insights")) if r.get("insights") else None),
        )
        for tk in tickers:
            conn.execute(
                "INSERT OR IGNORE INTO news_ticker (news_id, symbol) VALUES (?, ?)",
                (rid, tk),
            )
    conn.execute("UPDATE tickers SET last_news_fetch = ? WHERE symbol = ?", (TODAY, symbol))
    conn.commit()
    conn.close()
    return len(articles)


# ── Finnhub ───────────────────────────────────────────────────────────────────

def update_finnhub(symbol: str, start: str) -> int:
    try:
        articles = fetch_finnhub_news(symbol, start, TODAY)
        inserted, _ = insert_finnhub_news(symbol, articles)
        return inserted
    except Exception as e:
        print(f"    Finnhub error: {e}")
        return 0


# ── Reddit ────────────────────────────────────────────────────────────────────

def _reddit_get(url: str, params: dict) -> Optional[dict]:
    for i in range(4):
        try:
            resp = requests.get(url, headers=REDDIT_HEADERS, params=params, timeout=15)
            if resp.status_code == 429:
                time.sleep((2 ** i) + random.random() * 2)
                continue
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            time.sleep((2 ** i) + 1)
    return None


def _get_tickers() -> list[str]:
    conn = get_conn()
    rows = conn.execute("SELECT symbol FROM tickers WHERE last_ohlc_fetch IS NOT NULL").fetchall()
    conn.close()
    return [r[0] for r in rows]


def _build_ticker_pattern(tickers: list[str]) -> re.Pattern:
    symbols = sorted(tickers, key=len, reverse=True)
    pattern = r'\b(?:\$?)(' + '|'.join(re.escape(s) for s in symbols) + r')\b'
    return re.compile(pattern, re.IGNORECASE)


def fetch_reddit(days: int) -> int:
    tickers = _get_tickers()
    ticker_set = set(tickers)
    pattern = _build_ticker_pattern(tickers)
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()

    total_inserted = 0
    conn = get_conn()

    for subreddit in REDDIT_SUBREDDITS:
        url = f"https://www.reddit.com/r/{subreddit}/new.json"
        inserted_sub = 0
        after = None
        for _page in range(REDDIT_MAX_PAGES):
            params = {"limit": REDDIT_LIMIT}
            if after:
                params["after"] = after
            data = _reddit_get(url, params)
            if not data:
                break

            payload = data.get("data", {}) or {}
            children = payload.get("children", [])
            if not children:
                break

            page_had_recent = False
            for item in children:
                p = item.get("data", {})
                created = p.get("created_utc", 0)
                if created < cutoff_ts:
                    continue
                page_had_recent = True

                title = (p.get("title") or "").strip()
                text = (p.get("selftext") or "").strip()
                if not title:
                    continue

                combined = f"{title} {text}"
                matched = list({m.upper() for m in pattern.findall(combined) if m.upper() in ticker_set})
                if not matched:
                    continue

                reddit_id = p.get("id") or p.get("name", "")
                news_id = f"reddit_{reddit_id}"
                permalink = p.get("permalink", "")
                article_url = f"https://www.reddit.com{permalink}" if permalink else ""
                published_utc = datetime.fromtimestamp(float(created), tz=timezone.utc).isoformat()

                result = conn.execute(
                    """INSERT OR IGNORE INTO news_raw
                       (id, title, description, publisher, author,
                        published_utc, article_url, tickers_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        news_id, title,
                        text[:2000] if text else None,
                        f"Reddit r/{subreddit}",
                        p.get("author"),
                        published_utc,
                        article_url,
                        json.dumps(matched),
                    ),
                )

                if result.rowcount > 0:
                    for tk in matched:
                        conn.execute(
                            "INSERT OR IGNORE INTO news_ticker (news_id, symbol) VALUES (?, ?)",
                            (news_id, tk),
                        )
                    inserted_sub += 1

            after = payload.get("after")
            if not after or not page_had_recent:
                break
            time.sleep(0.6)

        if inserted_sub > 0:
            print(f"    r/{subreddit}: +{inserted_sub} posts")
        total_inserted += inserted_sub
        time.sleep(0.6)

    conn.commit()
    conn.close()
    return total_inserted


# ── Main ──────────────────────────────────────────────────────────────────────

def main(days: int = 3):
    start = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    print(f"=== Update Recent Data: {start} → {TODAY} (last {days} days) ===\n")

    # Get active tickers
    conn = get_conn()
    tickers = [r[0] for r in conn.execute(
        "SELECT symbol FROM tickers WHERE last_ohlc_fetch IS NOT NULL ORDER BY symbol"
    ).fetchall()]
    conn.close()
    print(f"Tickers: {len(tickers)}\n")

    # ── Polygon ──
    print("── Polygon OHLC + News ──")
    total_ohlc = total_news = 0
    for i, symbol in enumerate(tickers, 1):
        ohlc = update_polygon_ohlc(symbol, start)
        news = update_polygon_news(symbol, start)
        if ohlc > 0 or news > 0:
            print(f"  [{i}/{len(tickers)}] {symbol}: OHLC +{ohlc}, News +{news}")
        total_ohlc += ohlc
        total_news += news
    print(f"  Done: OHLC +{total_ohlc} rows, News +{total_news} articles\n")

    # ── Finnhub ──
    print("── Finnhub ──")
    total_fh = 0
    for i, symbol in enumerate(tickers, 1):
        inserted = update_finnhub(symbol, start)
        if inserted > 0:
            print(f"  [{i}/{len(tickers)}] {symbol}: +{inserted}")
        total_fh += inserted
        time.sleep(1.05)  # Finnhub free: 60 calls/min
    print(f"  Done: +{total_fh} articles\n")

    # ── Reddit ──
    print("── Reddit ──")
    total_reddit = fetch_reddit(days)
    print(f"  Done: +{total_reddit} posts\n")

    # ── Layer 0 + Alignment ──
    print("── Running alignment + Layer 0 ──")
    for symbol in tickers:
        try:
            align_news_for_symbol(symbol)
            run_layer0(symbol)
        except Exception as e:
            print(f"  {symbol} error: {e}")
    print("  Done\n")

    print("=== All sources updated! ===")
    print(f"  Polygon OHLC: +{total_ohlc}")
    print(f"  Polygon News: +{total_news}")
    print(f"  Finnhub:      +{total_fh}")
    print(f"  Reddit:       +{total_reddit}")
    print(f"\nNext step: run 'python -m backend.batch_submit' to process new articles through Layer 1")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=3, help="Number of days to backfill (default: 3)")
    args = parser.parse_args()
    main(days=args.days)
