"""One-time backfill: fetch 90 days of sentiment for all tickers from all 3 platforms.

Usage:
    python -m backend.adanos.backfill
    python -m backend.adanos.backfill --ticker NVDA   # single ticker
    python -m backend.adanos.backfill --days 30       # shorter window
"""

import argparse
import hashlib
import time
from datetime import datetime, timezone
from typing import Optional

from backend.adanos.client import get_all_platforms, TICKERS
from backend.database import get_conn, init_db


def _utc_to_date(ts) -> Optional[str]:
    """Convert unix timestamp or ISO string to YYYY-MM-DD."""
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        # ISO string
        return str(ts)[:10]
    except Exception:
        return None


def _make_id(platform: str, ticker: str, text: str, created_utc) -> str:
    """Generate a deterministic ID for a post."""
    raw = f"{platform}:{ticker}:{text[:80]}:{created_utc}"
    return hashlib.md5(raw.encode()).hexdigest()


def upsert_posts(ticker: str, platform: str, posts: list[dict], date: str):
    """Store individual posts into platform_posts table."""
    if not posts:
        return 0
    conn = get_conn()
    count = 0
    for p in posts:
        text = p.get("text_snippet") or p.get("text") or ""
        created_utc = p.get("created_utc")
        post_date = _utc_to_date(created_utc) or date
        post_id = _make_id(platform, ticker, text, created_utc)
        conn.execute(
            """INSERT OR IGNORE INTO platform_posts
               (id, ticker, date, platform, text, sentiment_label, sentiment_score,
                upvotes, likes, retweets, subreddit, author, source, created_utc)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                post_id, ticker, post_date, platform,
                text,
                p.get("sentiment_label"),
                p.get("sentiment_score"),
                p.get("upvotes"),
                p.get("likes"),
                p.get("retweets"),
                p.get("subreddit"),
                p.get("author"),
                p.get("source"),
                str(created_utc) if created_utc else None,
            ),
        )
        count += 1
    conn.commit()
    conn.close()
    return count


def _parse_daily_trend(data: dict, platform: str) -> list[dict]:
    """Extract daily_trend array from API response into list of {date, buzz, sentiment, bullish, bearish, mentions}."""
    if not data or not data.get("found", True) is not False:
        return []

    daily = data.get("daily_trend") or []
    rows = []
    for day in daily:
        date = day.get("date")
        if not date:
            continue
        rows.append({
            "date":            date,
            "buzz_score":      day.get("buzz_score"),
            "sentiment_score": day.get("sentiment_score"),
            "bullish_pct":     None,   # daily_trend doesn't have per-day bullish_pct
            "bearish_pct":     None,
            "mentions":        day.get("mentions"),
            "source_count":    None,
        })

    # Overlay top-level bullish/bearish/source_count onto the most recent day
    # (the API gives aggregate-level stats for the full period)
    if rows:
        rows[-1]["bullish_pct"]  = data.get("bullish_pct")
        rows[-1]["bearish_pct"]  = data.get("bearish_pct")
        rows[-1]["source_count"] = data.get("source_count") or data.get("subreddit_count")

    return rows


def upsert_rows(ticker: str, platform: str, rows: list[dict]):
    if not rows:
        return
    conn = get_conn()
    for row in rows:
        conn.execute(
            """INSERT OR REPLACE INTO platform_sentiment
               (ticker, date, platform, buzz_score, sentiment_score,
                bullish_pct, bearish_pct, mentions, source_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticker, row["date"], platform,
                row["buzz_score"], row["sentiment_score"],
                row["bullish_pct"], row["bearish_pct"],
                row["mentions"], row["source_count"],
            ),
        )
    conn.commit()
    conn.close()


def backfill_ticker(ticker: str, days: int = 90):
    print(f"  [{ticker}] fetching {days}d from all platforms...")
    data = get_all_platforms(ticker, days=days)

    for platform, resp in data.items():
        if resp is None:
            print(f"    {platform}: no data")
            continue
        rows = _parse_daily_trend(resp, platform)
        upsert_rows(ticker, platform, rows)

        # Also store individual posts
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if platform == "reddit":
            posts = resp.get("top_mentions") or []
        elif platform == "twitter":
            posts = resp.get("top_tweets") or []
        else:
            posts = resp.get("top_mentions") or []
        n_posts = upsert_posts(ticker, platform, posts, today)
        print(f"    {platform}: {len(rows)} days, {n_posts} posts stored")

    time.sleep(0.3)  # light rate limiting


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", type=str, help="Single ticker to backfill")
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()

    init_db()

    tickers = [args.ticker.upper()] if args.ticker else TICKERS
    print(f"=== Adanos Backfill: {len(tickers)} tickers, {args.days} days ===\n")

    for ticker in tickers:
        backfill_ticker(ticker, days=args.days)

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
