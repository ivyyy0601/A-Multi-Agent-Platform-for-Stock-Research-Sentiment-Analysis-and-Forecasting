"""Reclassify recent neutral+relevant layer1 rows using reason consistency.

Rules:
- neutral + only reason_growth  => positive
- neutral + only reason_decrease => negative
- both/non-empty or both empty => keep neutral
"""

from __future__ import annotations

import argparse

from backend.database import get_conn


def reclassify_recent(days: int = 4, symbol: str | None = None) -> dict:
    conn = get_conn()

    sql = """
        SELECT DISTINCT
            lr.rowid,
            lr.symbol,
            COALESCE(lr.reason_growth, '') AS reason_growth,
            COALESCE(lr.reason_decrease, '') AS reason_decrease,
            COALESCE(na.trade_date, substr(nr.published_utc, 1, 10)) AS ref_date
        FROM layer1_results lr
        JOIN news_raw nr ON nr.id = lr.news_id
        LEFT JOIN news_aligned na
          ON na.news_id = lr.news_id
         AND na.symbol = lr.symbol
        WHERE lower(COALESCE(lr.relevance, '')) IN ('relevant', 'high', 'medium')
          AND lower(COALESCE(lr.sentiment, '')) = 'neutral'
          AND date(COALESCE(na.trade_date, substr(nr.published_utc, 1, 10))) >= date('now', ?)
    """
    params: list[object] = [f"-{max(days - 1, 0)} day"]
    if symbol:
        sql += " AND lr.symbol = ?"
        params.append(symbol.upper())

    rows = conn.execute(sql, params).fetchall()

    updates: list[tuple[str, int]] = []
    kept = 0
    for row in rows:
        up_reason = (row["reason_growth"] or "").strip()
        down_reason = (row["reason_decrease"] or "").strip()
        has_up = bool(up_reason)
        has_down = bool(down_reason)
        if has_up and not has_down:
            updates.append(("positive", row["rowid"]))
        elif has_down and not has_up:
            updates.append(("negative", row["rowid"]))
        else:
            kept += 1

    if updates:
        conn.executemany(
            "UPDATE layer1_results SET sentiment = ? WHERE rowid = ?",
            updates,
        )
        conn.commit()

    conn.close()
    return {
        "scanned": len(rows),
        "updated": len(updates),
        "kept": kept,
        "days": days,
        "symbol": symbol.upper() if symbol else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=4)
    parser.add_argument("--symbol", type=str, default=None)
    args = parser.parse_args()
    stats = reclassify_recent(days=args.days, symbol=args.symbol)
    print(
        f"Scanned {stats['scanned']} neutral+relevant rows, "
        f"updated {stats['updated']}, kept {stats['kept']}."
    )


if __name__ == "__main__":
    main()
