"""Submit pending articles to Anthropic Batch API for Layer 1 analysis.

Usage: python -m backend.batch_submit [--top 100]

After submission, wait a few hours, then run:
    python -m backend.batch_collect
"""

import json
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any

import anthropic

from backend.config import settings
from backend.database import get_conn
from backend.pipeline.layer1 import get_pending_articles, _build_batch_prompt, BATCH_SIZE

MODEL = "claude-haiku-4-5-20251001"


def get_top_tickers(n: int = 100) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT l0.symbol, t.name,
               SUM(CASE WHEN l0.passed=1 THEN 1 ELSE 0 END) as passed
        FROM layer0_results l0
        JOIN tickers t ON l0.symbol = t.symbol
        GROUP BY l0.symbol
        ORDER BY passed DESC
        LIMIT ?
    """, (n,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def submit_pending_batch(top_n: int = 100) -> dict:
    tickers = get_top_tickers(top_n)
    symbols = [t["symbol"] for t in tickers]

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    requests = []
    mapping = []
    total_articles = 0

    for symbol in symbols:
        articles = get_pending_articles(symbol)
        if not articles:
            continue

        print(f"[{symbol}] {len(articles)} pending articles")
        total_articles += len(articles)

        for i in range(0, len(articles), BATCH_SIZE):
            chunk = articles[i:i + BATCH_SIZE]
            prompt = _build_batch_prompt(symbol, chunk)
            custom_id = f"{symbol}_{i}_{len(chunk)}"

            requests.append({
                "custom_id": custom_id,
                "params": {
                    "model": MODEL,
                    "max_tokens": 4096,
                    "messages": [{"role": "user", "content": prompt}],
                },
            })
            mapping.append({
                "custom_id": custom_id,
                "symbol": symbol,
                "article_ids": [a["id"] for a in chunk],
            })

    if not requests:
        return {
            "submitted": False,
            "batch_id": None,
            "total_articles": 0,
            "request_count": 0,
            "status": "noop",
        }

    batch = client.messages.batches.create(requests=requests)
    batch_id = batch.id

    conn = get_conn()
    conn.execute(
        """INSERT INTO batch_jobs (batch_id, symbol, status, total, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (batch_id, "all", batch.processing_status, total_articles,
         datetime.now(timezone.utc).isoformat()),
    )
    for m in mapping:
        conn.execute(
            """INSERT INTO batch_request_map (batch_id, custom_id, symbol, article_ids)
               VALUES (?, ?, ?, ?)""",
            (batch_id, m["custom_id"], m["symbol"], json.dumps(m["article_ids"])),
    )
    conn.commit()
    conn.close()

    return {
        "submitted": True,
        "batch_id": batch_id,
        "total_articles": total_articles,
        "request_count": len(requests),
        "status": batch.processing_status,
    }


def main():
    top_n = 100
    if "--top" in sys.argv:
        idx = sys.argv.index("--top")
        if idx + 1 < len(sys.argv):
            top_n = int(sys.argv[idx + 1])

    print(f"=== Layer 1 Batch Submit (Anthropic Haiku, top {top_n} tickers) ===\n")
    result = submit_pending_batch(top_n=top_n)
    if not result["submitted"]:
        print("No pending articles found.")
        return

    print(f"\nTotal: {result['total_articles']} articles → {result['request_count']} batch requests")
    print("Submitting to Anthropic Batch API...")
    print(f"\nSubmitted! Batch ID: {result['batch_id']}")
    print(f"Status: {result['status']}")
    print(f"\nRun later to collect results:")
    print(f"  python -m backend.batch_collect")


if __name__ == "__main__":
    main()
