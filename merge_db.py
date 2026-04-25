"""Merge two pokieticker databases into one, no duplicates."""
import sqlite3
import shutil
import os

DB_NEWS   = "/Users/ivy_ai/Desktop/真的最后了/pokieticker.db"
DB_REDDIT = "/Users/ivy_ai/Desktop/PokieTicker_reddit/pokieticker.db"
DB_OUT    = "/Users/ivy_ai/Desktop/pokieticker_merged.db"

TABLES = [
    "tickers",
    "news_raw",
    "news_ticker",
    "ohlc",
    "news_aligned",
    "layer0_results",
    "layer1_results",
    "layer2_results",
    "batch_jobs",
    "batch_request_map",
]

# Start from a fresh copy of the news db
if os.path.exists(DB_OUT):
    os.remove(DB_OUT)
shutil.copy2(DB_NEWS, DB_OUT)
print(f"Base copied from news db → {DB_OUT}")

conn = sqlite3.connect(DB_OUT)
conn.execute("ATTACH DATABASE ? AS reddit", (DB_REDDIT,))

for table in TABLES:
    before = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    conn.execute(f"INSERT OR IGNORE INTO {table} SELECT * FROM reddit.{table}")
    after = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    added = after - before
    print(f"  {table:20s}: {before:>8,} → {after:>8,}  (+{added:,})")

conn.commit()
conn.close()
print("\nDone! Saved to:", DB_OUT)
