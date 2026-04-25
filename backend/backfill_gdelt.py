"""
Backfill historical news from GDELT (2024-08-01 to 2025-03-19).

GDELT has no description/summary — only title is available.
Relevance: GDELT query-level repeat filter + ASCII English check + title mention.
Sentiment: FinBERT on title only.
key_discussion: title (no summary available).

Rate limit: 1 request / 5 seconds (enforced by sleep).

Usage:
  python -m backend.backfill_gdelt --from 2024-08-01 --to 2025-03-19
  python -m backend.backfill_gdelt --from 2024-08-01 --to 2025-03-19 --tickers AAPL NVDA
"""

import argparse
import hashlib
import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from langdetect import detect, LangDetectException
from transformers import pipeline

from backend.database import get_conn
from backend.pipeline.alignment import align_news_for_symbol
from backend.pipeline.layer0 import run_layer0

# ── Config ────────────────────────────────────────────────────────────────────
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_SLEEP = 6       # seconds between requests (limit: 1/5s, use 6 for safety)
BATCH_SIZE = 64       # FinBERT batch size

# Tickers that need extra financial keywords to reduce ambiguity
HIGH_AMBIGUITY = {"AAPL", "AMZN", "GOLD", "REAL", "MAIN", "GOOD"}
FINANCIAL_TERMS = "(stock OR earnings OR shares OR investor OR revenue OR nasdaq OR NYSE)"

# Financial keywords — at least one must appear in title (strict, unambiguous)
FINANCE_KEYWORDS = re.compile(
    r'\b(stock|stocks|shares|earnings|revenue|profit|loss|investor|investors|'
    r'nasdaq|nyse|ipo|dividend|analyst|forecast|quarter|q[1-4]|eps|guidance|'
    r'etf|hedge|valuation|price.target|downgrade|rally|outperform|underperform|'
    r'market.cap|short.sell|buyback|share.price|stock.price|wall.street|'
    r'bull|bear|overweight|underweight|billion|million|trillion|\$[0-9])\b',
    re.IGNORECASE
)

# ── Load ticker names ─────────────────────────────────────────────────────────
_NAMES_PATH = Path(__file__).parent / "ticker_names.json"
TICKER_NAMES: dict[str, list[str]] = json.loads(_NAMES_PATH.read_text())

# ── FinBERT ───────────────────────────────────────────────────────────────────
print("Loading FinBERT…")
_finbert = pipeline("text-classification", model="ProsusAI/finbert", top_k=1)
print("FinBERT ready.\n")


# ── Helpers ───────────────────────────────────────────────────────────────────

def build_query(symbol: str) -> str:
    names = TICKER_NAMES.get(symbol, [symbol])
    primary = names[0]
    query = f'{primary} repeat3:"{primary}"'
    if symbol in HIGH_AMBIGUITY:
        query += f" {FINANCIAL_TERMS}"
    return query


def is_english(text: str) -> bool:
    if not text:
        return False
    try:
        return detect(text) == 'en'
    except LangDetectException:
        return False


def mentions_company(symbol: str, title: str) -> bool:
    names = TICKER_NAMES.get(symbol.upper(), [symbol])
    text = title.lower()
    for name in names:
        if re.search(r"\b" + re.escape(name.lower()) + r"\b", text):
            return True
    return False


def make_id(url: str) -> str:
    return "gdelt_" + hashlib.md5(url.encode()).hexdigest()


def gdelt_fetch(query: str, day: str) -> list[dict]:
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": 250,
        "startdatetime": day.replace("-", "") + "000000",
        "enddatetime": day.replace("-", "") + "235959",
        "format": "json",
    }
    for attempt in range(3):
        try:
            r = requests.get(GDELT_URL, params=params, timeout=15)
            if r.status_code == 429:
                time.sleep(15)
                continue
            if not r.text.strip():
                return []
            return r.json().get("articles", []) or []
        except Exception:
            time.sleep(10)
    return []


def filter_articles(symbol: str, articles: list[dict]) -> list[dict]:
    seen_urls = set()
    seen_titles = set()
    kept = []
    for a in articles:
        url = a.get("url", "")
        title = a.get("title", "")
        if not url or not title:
            continue
        # Dedup by URL
        if url in seen_urls:
            continue
        # Dedup by title (normalised)
        title_key = re.sub(r'\s+', ' ', title.lower().strip())
        if title_key in seen_titles:
            continue
        # Must be English
        if not is_english(title):
            continue
        # Title must mention the company
        if not mentions_company(symbol, title):
            continue
        # Title must contain at least one financial keyword
        if not FINANCE_KEYWORDS.search(title):
            continue
        seen_urls.add(url)
        seen_titles.add(title_key)
        kept.append(a)
    return kept


def insert_articles(symbol: str, articles: list[dict]) -> tuple[int, int]:
    """Insert into news_raw + news_ticker. Returns (inserted, skipped_dup)."""
    if not articles:
        return 0, 0

    conn = get_conn()
    inserted = 0
    skipped = 0

    for a in articles:
        news_id = make_id(a["url"])
        # seendate format: 20250117T020000Z → 2025-01-17T02:00:00Z
        raw_date = a.get("seendate", "")
        try:
            published_utc = (
                raw_date[:4] + "-" + raw_date[4:6] + "-" + raw_date[6:8]
                + "T" + raw_date[9:11] + ":" + raw_date[11:13] + ":" + raw_date[13:15] + "Z"
            )
        except Exception:
            published_utc = None

        result = conn.execute(
            """INSERT OR IGNORE INTO news_raw
               (id, title, description, publisher, author,
                published_utc, article_url, tickers_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                news_id,
                a.get("title"),
                None,
                a.get("domain"),
                None,
                published_utc,
                a.get("url"),
                json.dumps([symbol]),
            ),
        )
        if result.rowcount > 0:
            conn.execute(
                "INSERT OR IGNORE INTO news_ticker (news_id, symbol) VALUES (?, ?)",
                (news_id, symbol),
            )
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()
    return inserted, skipped


def process_layer1(symbol: str):
    """Run FinBERT on title for any news_raw rows missing layer1_results."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT nr.id, nr.title
        FROM news_raw nr
        JOIN news_ticker nt ON nt.news_id = nr.id AND nt.symbol = ?
        LEFT JOIN layer1_results lr ON lr.news_id = nr.id AND lr.symbol = ?
        WHERE lr.news_id IS NULL AND nr.id LIKE 'gdelt_%'
    """, (symbol, symbol)).fetchall()

    if not rows:
        conn.close()
        return 0

    texts = [(title or "")[:512] for _, title in rows]
    results = _finbert(texts, truncation=True, max_length=512, batch_size=BATCH_SIZE)

    inserts = []
    for (news_id, title), result in zip(rows, results):
        sentiment = result[0]["label"].lower()
        inserts.append((news_id, symbol, "relevant", title or "", sentiment))

    conn.executemany("""
        INSERT OR IGNORE INTO layer1_results
            (news_id, symbol, relevance, key_discussion, sentiment)
        VALUES (?, ?, ?, ?, ?)
    """, inserts)
    conn.commit()
    conn.close()
    return len(inserts)


def generate_days(start: str, end: str, reverse: bool = False, skip_weekends: bool = False):
    cur = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    days = []
    while cur <= end_d:
        if not skip_weekends or cur.weekday() < 5:  # 0-4 = Mon-Fri
            days.append(cur.isoformat())
        cur += timedelta(days=1)
    if reverse:
        days = list(reversed(days))
    for d in days:
        yield d


def get_active_tickers() -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT symbol FROM tickers WHERE last_ohlc_fetch IS NOT NULL ORDER BY symbol"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


# ── Main ──────────────────────────────────────────────────────────────────────

def run(tickers: list[str], date_from: str, date_to: str):
    days = list(generate_days(date_from, date_to, reverse=True, skip_weekends=True))
    total_calls = len(tickers) * len(days)
    est_hours = total_calls * GDELT_SLEEP / 3600

    print(f"{len(tickers)} tickers × {len(days)} days = {total_calls} API calls")
    print(f"Rate limited to 1/{GDELT_SLEEP}s → ~{est_hours:.1f} hours\n")

    total_inserted = 0
    total_l1 = 0
    t_start = time.time()

    for day in days:
        day_inserted = 0
        for symbol in tickers:
            query = build_query(symbol)
            articles = gdelt_fetch(query, day)
            filtered = filter_articles(symbol, articles)
            inserted, _ = insert_articles(symbol, filtered)

            if inserted > 0:
                try:
                    align_news_for_symbol(symbol)
                    run_layer0(symbol)
                    l1 = process_layer1(symbol)
                    total_l1 += l1
                except Exception as e:
                    print(f"  WARNING {symbol}: {e}")

            day_inserted += inserted
            print(f"  {symbol}: raw={len(articles)} kept={len(filtered)} inserted={inserted}", flush=True)
            time.sleep(GDELT_SLEEP)

        total_inserted += day_inserted
        elapsed = int(time.time() - t_start)
        remaining = (len(days) * len(tickers) - (days.index(day) + 1) * len(tickers)) * GDELT_SLEEP
        print(
            f"[{day}] +{day_inserted} articles | "
            f"total: {total_inserted} news, {total_l1} layer1 | "
            f"elapsed {elapsed}s | ETA ~{remaining}s"
        )

    print(f"\nDone. Inserted {total_inserted} articles, {total_l1} layer1_results entries.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="date_from", required=True)
    parser.add_argument("--to", dest="date_to", required=True)
    parser.add_argument("--tickers", nargs="*", default=None)
    args = parser.parse_args()

    tickers = args.tickers if args.tickers else get_active_tickers()
    print(f"Tickers: {len(tickers)} | {args.date_from} → {args.date_to}\n")
    run(tickers, args.date_from, args.date_to)
