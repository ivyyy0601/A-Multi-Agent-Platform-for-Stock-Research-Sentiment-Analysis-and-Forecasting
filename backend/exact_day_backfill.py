from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

import requests

from backend.database import get_conn
from backend.finnhub_fetch import fetch_finnhub_news, insert_finnhub_news
from backend.pipeline.alignment import align_news_for_symbol
from backend.pipeline.layer0 import run_layer0
from backend.update_recent import (
    REDDIT_HEADERS,
    REDDIT_LIMIT,
    REDDIT_MAX_PAGES,
    REDDIT_SUBREDDITS,
    _build_ticker_pattern,
    _get_tickers,
    update_polygon_news,
)


def backfill_exact_day(target_date: str, reddit_only: bool = False) -> None:
    conn = get_conn()
    tickers = [r[0] for r in conn.execute(
        "SELECT symbol FROM tickers WHERE last_ohlc_fetch IS NOT NULL ORDER BY symbol"
    ).fetchall()]
    conn.close()

    print(f"=== Exact-day backfill for {target_date} ===")
    print(f"Tickers: {len(tickers)}")

    poly_total = 0
    fh_total = 0
    if not reddit_only:
        for i, symbol in enumerate(tickers, 1):
            poly = update_polygon_news(symbol, target_date)
            try:
                articles = fetch_finnhub_news(symbol, target_date, target_date)
                fh, _ = insert_finnhub_news(symbol, articles)
            except Exception:
                fh = 0
            if poly or fh:
                print(f"[{i}/{len(tickers)}] {symbol}: Polygon +{poly}, Finnhub +{fh}")
            poly_total += poly
            fh_total += fh
            time.sleep(0.15)

    conn = get_conn()
    ticker_set = set(_get_tickers())
    pattern = _build_ticker_pattern(list(ticker_set))
    reddit_total = 0

    for subreddit in REDDIT_SUBREDDITS:
        after = None
        inserted_sub = 0
        for _page in range(REDDIT_MAX_PAGES):
            params = {"limit": REDDIT_LIMIT}
            if after:
                params["after"] = after
            try:
                resp = requests.get(
                    f"https://www.reddit.com/r/{subreddit}/new.json",
                    headers=REDDIT_HEADERS,
                    params=params,
                    timeout=15,
                )
                if resp.status_code != 200:
                    break
                data = resp.json().get("data", {}) or {}
            except Exception:
                break

            children = data.get("children", [])
            if not children:
                break

            page_had_target = False
            for item in children:
                p = item.get("data", {})
                created = p.get("created_utc", 0)
                date_str = datetime.fromtimestamp(float(created), tz=timezone.utc).date().isoformat()
                if date_str != target_date:
                    continue
                page_had_target = True

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
                       (id, title, description, publisher, author, published_utc, article_url, tickers_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        news_id,
                        title,
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

            after = data.get("after")
            if not after or not page_had_target:
                break
            time.sleep(0.5)

        if inserted_sub:
            print(f"r/{subreddit}: +{inserted_sub} exact-day posts")
        reddit_total += inserted_sub
        time.sleep(0.3)

    conn.commit()
    conn.close()

    print("Running alignment + Layer 0 ...")
    for symbol in tickers:
        try:
            align_news_for_symbol(symbol)
            run_layer0(symbol)
        except Exception as e:
            print(f"  {symbol} error: {e}")

    print("=== Exact-day backfill done ===")
    if not reddit_only:
        print(f"Polygon News: +{poly_total}")
        print(f"Finnhub:      +{fh_total}")
    print(f"Reddit:       +{reddit_total}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="Exact UTC date, e.g. 2026-03-28")
    parser.add_argument("--reddit-only", action="store_true")
    args = parser.parse_args()
    backfill_exact_day(args.date, reddit_only=args.reddit_only)


if __name__ == "__main__":
    main()
