import argparse
import time
from datetime import datetime, timedelta, timezone

from backend.database import get_conn
from backend.update_recent import update_polygon_ohlc


def main(days_back: int = 5, retries: int = 2, sleep_seconds: float = 1.5):
    conn = get_conn()
    target_row = conn.execute("SELECT MAX(date) AS max_date FROM ohlc").fetchone()
    target_date = target_row["max_date"] if target_row else None
    if not target_date:
        print("No OHLC data found.")
        conn.close()
        return

    tracked = [
        r["symbol"]
        for r in conn.execute(
            "SELECT symbol FROM tickers WHERE last_ohlc_fetch IS NOT NULL ORDER BY symbol"
        ).fetchall()
    ]
    missing = []
    for symbol in tracked:
        row = conn.execute(
            "SELECT MAX(date) AS max_date FROM ohlc WHERE symbol = ?",
            (symbol,),
        ).fetchone()
        last_date = row["max_date"] if row else None
        if last_date != target_date:
            missing.append((symbol, last_date))
    conn.close()

    print(f"Target trading day: {target_date}")
    print(f"Tracked tickers: {len(tracked)}")
    print(f"Missing latest OHLC: {len(missing)}")
    if not missing:
        return

    start = (datetime.now(timezone.utc).date() - timedelta(days=days_back)).isoformat()
    for idx, (symbol, last_date) in enumerate(missing, 1):
        updated = 0
        for attempt in range(1, retries + 2):
            updated = update_polygon_ohlc(symbol, start)
            conn = get_conn()
            row = conn.execute(
                "SELECT MAX(date) AS max_date FROM ohlc WHERE symbol = ?",
                (symbol,),
            ).fetchone()
            current = row["max_date"] if row else None
            conn.close()
            if current == target_date:
                print(
                    f"[{idx}/{len(missing)}] {symbol}: fixed to {current} "
                    f"(rows +{updated}, attempt {attempt})"
                )
                break
            if attempt <= retries:
                time.sleep(sleep_seconds)
        else:
            print(
                f"[{idx}/{len(missing)}] {symbol}: still at {last_date} "
                f"after retries"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-back", type=int, default=5)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep-seconds", type=float, default=1.5)
    args = parser.parse_args()
    main(days_back=args.days_back, retries=args.retries, sleep_seconds=args.sleep_seconds)
