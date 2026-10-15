"""
Re-run news alignment for symbols touched by recently published news.

Examples:
    python -m backend.realign_recent_news --days 3
    python -m backend.realign_recent_news --date 2026-03-22
"""

from __future__ import annotations

import argparse

from backend.database import get_conn
from backend.pipeline.alignment import align_news_for_symbol


def _load_symbols(days: int | None, target_date: str | None) -> list[str]:
    conn = get_conn()
    cur = conn.cursor()

    if target_date:
        sql = """
            SELECT DISTINCT nt.symbol
            FROM news_raw nr
            JOIN news_ticker nt ON nt.news_id = nr.id
            WHERE date(substr(nr.published_utc, 1, 10)) = date(?)
            ORDER BY nt.symbol
        """
        rows = cur.execute(sql, (target_date,)).fetchall()
    else:
        sql = """
            SELECT DISTINCT nt.symbol
            FROM news_raw nr
            JOIN news_ticker nt ON nt.news_id = nr.id
            WHERE date(substr(nr.published_utc, 1, 10)) >= date('now', ?)
            ORDER BY nt.symbol
        """
        rows = cur.execute(sql, (f"-{max((days or 3) - 1, 0)} day",)).fetchall()

    conn.close()
    return [r[0] for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=3, help="Calendar days to scan, including today.")
    parser.add_argument("--date", type=str, default=None, help="Specific published date (YYYY-MM-DD).")
    args = parser.parse_args()

    symbols = _load_symbols(args.days, args.date)
    label = args.date or f"last {args.days} day(s)"
    print(f"Found {len(symbols)} symbols with news in {label}.")

    total_aligned = 0
    for i, symbol in enumerate(symbols, start=1):
        result = align_news_for_symbol(symbol)
        aligned = result.get("aligned", 0)
        total_aligned += aligned
        print(f"  {i}/{len(symbols)} {symbol}: aligned {aligned}")

    print(f"\nDone. Total newly aligned rows: {total_aligned}")


if __name__ == "__main__":
    main()
