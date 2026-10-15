"""Historical Finnhub backfill — fetches all months, submits Layer 1, polls and collects.

Usage: python -m backend.backfill_finnhub
"""

import json
import time
from datetime import date, timedelta
import calendar

import anthropic

from backend.config import settings
from backend.database import get_conn
from backend.finnhub_fetch import fetch_finnhub_news, insert_finnhub_news
from backend.pipeline.alignment import align_news_for_symbol
from backend.pipeline.layer0 import run_layer0
from backend.batch_submit import build_batch_requests, submit_batch, get_top_tickers


def generate_months(start: str, end: str):
    """Yield (month_start, month_end) pairs from start to end date."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    cur = date(s.year, s.month, 1)
    while cur <= e:
        month_start = max(cur, s).isoformat()
        last_day = calendar.monthrange(cur.year, cur.month)[1]
        month_end = min(date(cur.year, cur.month, last_day), e).isoformat()
        yield month_start, month_end
        # Next month
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)


def fetch_all(tickers: list[str], start: str, end: str):
    """Fetch all historical Finnhub data month by month."""
    months = list(generate_months(start, end))
    total_inserted = 0
    total_calls = len(tickers) * len(months)
    call_count = 0

    print(f"\n=== STEP 1: Fetching Finnhub data ===")
    print(f"{len(tickers)} tickers × {len(months)} months = {total_calls} API calls (~{total_calls//60+1} min)\n")

    for month_start, month_end in months:
        month_inserted = 0
        for symbol in tickers:
            call_count += 1
            try:
                articles = fetch_finnhub_news(symbol, month_start, month_end)
                inserted, skipped = insert_finnhub_news(symbol, articles)
                if inserted > 0:
                    align_news_for_symbol(symbol)
                    run_layer0(symbol)
                month_inserted += inserted
            except Exception as e:
                print(f"  ERROR {symbol} {month_start}: {e}")
            time.sleep(1.1)  # 60 calls/min rate limit

        total_inserted += month_inserted
        print(f"[{month_start[:7]}] inserted {month_inserted} articles  (total so far: {total_inserted})")

    print(f"\nFetch complete. Total inserted: {total_inserted}")
    return total_inserted


def submit_and_collect():
    """Submit Layer 1 batch and poll until done."""
    print(f"\n=== STEP 2: Submitting Layer 1 batch ===")

    tickers_info = get_top_tickers(100)
    symbols = [t["symbol"] for t in tickers_info]

    requests_list, mapping = build_batch_requests(symbols)
    if not requests_list:
        print("No pending articles — already all analyzed.")
        return

    total_articles = sum(len(v[1]) for v in mapping.values())
    est_cost = (total_articles * 300 / 1_000_000 * 0.5) + (total_articles * 80 / 1_000_000 * 2.5)
    print(f"Submitting {total_articles} articles, estimated cost ~${est_cost:.2f}")

    batch_id = submit_batch(requests_list, mapping)
    print(f"Batch ID: {batch_id}")

    # Poll every 5 minutes
    print(f"\n=== STEP 3: Waiting for results (polling every 5 min) ===")
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        print(f"  [{time.strftime('%H:%M:%S')}] status={batch.processing_status} "
              f"succeeded={counts.succeeded} processing={counts.processing} errored={counts.errored}")
        if batch.processing_status == "ended":
            break
        time.sleep(300)  # 5 minutes

    # Collect
    print(f"\n=== STEP 4: Collecting results ===")
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "-m", "backend.batch_collect", batch_id],
        capture_output=False
    )
    print("Collection done.")


def main():
    # Get all active tickers
    conn = get_conn()
    tickers = [r[0] for r in conn.execute(
        "SELECT symbol FROM tickers WHERE last_ohlc_fetch IS NOT NULL ORDER BY symbol"
    ).fetchall()]
    conn.close()

    # Date range: Polygon starts 2023-11-06, skip already-done 2026-03-18/19
    FETCH_START = "2025-06-01"
    FETCH_END   = "2026-03-17"

    print(f"=== Finnhub Historical Backfill ===")
    print(f"Tickers: {len(tickers)}")
    print(f"Date range: {FETCH_START} → {FETCH_END}")

    # Step 1: Fetch
    fetch_all(tickers, FETCH_START, FETCH_END)

    # Step 2-4: Submit + poll + collect
    submit_and_collect()

    print("\n=== All done! ===")


if __name__ == "__main__":
    main()
