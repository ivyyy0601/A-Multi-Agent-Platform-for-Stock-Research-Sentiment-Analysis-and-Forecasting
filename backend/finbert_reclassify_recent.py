"""
Re-classify recent neutral+relevant articles in layer1_results using FinBERT.

Default scope:
- last 4 calendar days (today included)
- all symbols

Examples:
    python -m backend.finbert_reclassify_recent
    python -m backend.finbert_reclassify_recent --days 4
    python -m backend.finbert_reclassify_recent --days 4 --symbol AAPL
    python -m backend.finbert_reclassify_recent --days 3 --dry-run
"""

from __future__ import annotations

import argparse
import time

from transformers import pipeline

from backend.database import get_conn

BATCH_SIZE = 64

print("Loading FinBERT model (ProsusAI/finbert)...")
finbert = pipeline("text-classification", model="ProsusAI/finbert", top_k=1)
print("Model loaded.\n")


def _load_targets(days: int, symbol: str | None) -> list[tuple[int, str, str, str, str]]:
    conn = get_conn()
    cur = conn.cursor()

    sql = """
        SELECT DISTINCT
            lr.rowid,
            lr.symbol,
            n.title,
            lr.key_discussion,
            COALESCE(na.trade_date, substr(n.published_utc, 1, 10)) AS ref_date
        FROM layer1_results lr
        JOIN news_raw n
          ON n.id = lr.news_id
        LEFT JOIN news_aligned na
          ON na.news_id = lr.news_id
         AND na.symbol = lr.symbol
        WHERE lower(COALESCE(lr.sentiment, '')) = 'neutral'
          AND lower(COALESCE(lr.relevance, '')) = 'relevant'
          AND date(COALESCE(na.trade_date, substr(n.published_utc, 1, 10))) >= date('now', ?)
    """
    params: list[object] = [f"-{max(days - 1, 0)} day"]

    if symbol:
        sql += " AND lr.symbol = ?"
        params.append(symbol.upper())

    sql += """
        ORDER BY date(ref_date) DESC, lr.symbol, lr.rowid
    """

    rows = cur.execute(sql, params).fetchall()
    conn.close()
    return [(r[0], r[1], r[2] or "", r[3] or "", r[4] or "") for r in rows]


def reclassify_recent(days: int = 4, symbol: str | None = None, dry_run: bool = False) -> None:
    rows = _load_targets(days=days, symbol=symbol)
    total = len(rows)
    scope = f"last {days} day(s)"
    if symbol:
        scope += f", symbol={symbol.upper()}"
    print(f"Found {total} neutral+relevant articles to re-classify ({scope}).\n")

    if total == 0:
        return

    conn = None if dry_run else get_conn()
    cur = None if dry_run else conn.cursor()

    updated = 0
    kept = 0
    start = time.time()

    for batch_start in range(0, total, BATCH_SIZE):
        batch = rows[batch_start: batch_start + BATCH_SIZE]

        texts = [
            ((title or "") + ". " + (key_discussion or ""))[:512]
            for _, _, title, key_discussion, _ in batch
        ]

        results = finbert(texts, truncation=True, max_length=512, batch_size=BATCH_SIZE)

        updates: list[tuple[str, int]] = []
        for i, result in enumerate(results):
            rowid = batch[i][0]
            top_label = result[0]["label"].lower()
            if top_label != "neutral":
                updates.append((top_label, rowid))
                updated += 1
            else:
                kept += 1

        if updates and not dry_run and cur is not None:
            cur.executemany(
                "UPDATE layer1_results SET sentiment = ? WHERE rowid = ?",
                updates,
            )
            conn.commit()

        done = batch_start + len(batch)
        elapsed = time.time() - start
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        print(
            f"  {done}/{total} | updated so far: {updated} | "
            f"elapsed: {elapsed:.0f}s | ETA: {eta:.0f}s"
        )

    if conn is not None:
        conn.close()

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s.")
    print(f"  Updated (neutral -> positive/negative): {updated}")
    print(f"  Kept neutral:                           {kept}")
    print(f"  Total processed:                        {total}")
    if dry_run:
        print("  Dry run: no database rows were updated.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=4, help="Calendar days to scan, including today.")
    parser.add_argument("--symbol", type=str, default=None, help="Optional ticker filter.")
    parser.add_argument("--dry-run", action="store_true", help="Run FinBERT without writing updates.")
    args = parser.parse_args()
    reclassify_recent(days=args.days, symbol=args.symbol, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
