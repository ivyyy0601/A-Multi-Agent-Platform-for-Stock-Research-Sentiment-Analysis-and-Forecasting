"""
Backfill Finnhub news day-by-day with zero LLM cost.

- Fetches Finnhub /company-news day by day for all active tickers
- Skips duplicates (INSERT OR IGNORE)
- Fills layer1_results using free tools:
    relevance   → _mentions_company() keyword match
    sentiment   → FinBERT
    key_discussion → first 200 chars of description
    reason_growth / reason_decrease / chinese_summary → null

Usage:
  python -m backend.backfill_free --from 2025-06-01 --to 2026-03-19
  python -m backend.backfill_free --from 2025-06-01 --to 2026-03-19 --tickers AAPL TSLA NVDA
"""

import argparse
import json
import time
from datetime import date, timedelta

from transformers import pipeline

from backend.database import get_conn
from backend.finnhub_fetch import fetch_finnhub_news, insert_finnhub_news, _mentions_company
from backend.pipeline.alignment import align_news_for_symbol
from backend.pipeline.layer0 import run_layer0

# ── FinBERT (loaded once) ─────────────────────────────────────────────────────
print("Loading FinBERT…")
_finbert = pipeline("text-classification", model="ProsusAI/finbert", top_k=1)
print("FinBERT ready.\n")


def _sentiment(title: str, description: str) -> str:
    text = ((title or "") + ". " + (description or ""))[:512]
    result = _finbert(text, truncation=True, max_length=512)
    return result[0][0]["label"].lower()  # positive / negative / neutral


def _key_discussion(description: str) -> str:
    if not description:
        return ""
    return description[:200].rsplit(" ", 1)[0]  # trim at word boundary


def generate_days(start: str, end: str):
    cur = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    while cur <= end_d:
        yield cur.isoformat()
        cur += timedelta(days=1)


def get_active_tickers() -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT symbol FROM tickers WHERE last_ohlc_fetch IS NOT NULL ORDER BY symbol"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def process_layer1(symbol: str):
    """Fill layer1_results for any news_raw rows that have no entry yet."""
    conn = get_conn()

    rows = conn.execute("""
        SELECT nr.id, nr.title, nr.description
        FROM news_raw nr
        JOIN news_ticker nt ON nt.news_id = nr.id AND nt.symbol = ?
        LEFT JOIN layer1_results lr ON lr.news_id = nr.id AND lr.symbol = ?
        WHERE lr.news_id IS NULL
    """, (symbol, symbol)).fetchall()

    if not rows:
        conn.close()
        return 0

    texts = [
        ((title or "") + ". " + (desc or ""))[:512]
        for _, title, desc in rows
    ]

    # Batch FinBERT
    results = _finbert(texts, truncation=True, max_length=512, batch_size=64)

    inserts = []
    for (news_id, title, desc), result in zip(rows, results):
        relevant = _mentions_company(symbol, title or "", desc or "")
        relevance = "relevant" if relevant else "irrelevant"
        sentiment = result[0]["label"].lower()
        key_disc = _key_discussion(desc)
        inserts.append((news_id, symbol, relevance, key_disc, sentiment))

    conn.executemany("""
        INSERT OR IGNORE INTO layer1_results
            (news_id, symbol, relevance, key_discussion, sentiment)
        VALUES (?, ?, ?, ?, ?)
    """, inserts)
    conn.commit()
    conn.close()
    return len(inserts)


def run(tickers: list[str], date_from: str, date_to: str):
    days = list(generate_days(date_from, date_to))
    print(f"{len(tickers)} tickers × {len(days)} days = {len(tickers)*len(days)} API calls")
    print(f"Rate-limited to 60/min → ~{len(tickers)*len(days)//60+1} min for fetching\n")

    total_inserted = 0
    total_l1 = 0
    call_count = 0
    t_start = time.time()

    for day in days:
        day_inserted = 0
        for symbol in tickers:
            call_count += 1
            try:
                articles = fetch_finnhub_news(symbol, day, day)
                inserted, _ = insert_finnhub_news(symbol, articles)
                if inserted > 0:
                    align_news_for_symbol(symbol)
                    run_layer0(symbol)
                    l1 = process_layer1(symbol)
                    total_l1 += l1
                day_inserted += inserted
            except Exception as e:
                print(f"  ERROR {symbol} {day}: {e}")

            # Finnhub free tier: 60 calls/min
            time.sleep(1.05)

        total_inserted += day_inserted
        elapsed = int(time.time() - t_start)
        remaining_calls = (len(days) * len(tickers)) - call_count
        eta = int(remaining_calls * 1.05)
        print(
            f"[{day}] +{day_inserted} articles | "
            f"total: {total_inserted} news, {total_l1} layer1 | "
            f"elapsed {elapsed}s | ETA ~{eta}s"
        )

    print(f"\nDone. Inserted {total_inserted} articles, {total_l1} layer1_results entries.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="date_from", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--tickers", nargs="*", default=None,
                        help="Specific tickers (default: all active)")
    args = parser.parse_args()

    tickers = args.tickers if args.tickers else get_active_tickers()
    print(f"Tickers: {len(tickers)} | {args.date_from} → {args.date_to}\n")
    run(tickers, args.date_from, args.date_to)
