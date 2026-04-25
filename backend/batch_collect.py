"""Check and collect results from Anthropic Batch API.

Usage: python -m backend.batch_collect <batch_id>
"""

import json
import sys
import time

import anthropic

from backend.config import settings
from backend.database import get_conn


def check_status(batch_id: str) -> dict:
    """Check batch status."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    batch = client.messages.batches.retrieve(batch_id)

    conn = get_conn()
    conn.execute(
        "UPDATE batch_jobs SET status = ? WHERE batch_id = ?",
        (batch.processing_status, batch_id),
    )
    conn.commit()
    conn.close()

    return {
        "status": batch.processing_status,
        "processing": batch.request_counts.processing,
        "succeeded": batch.request_counts.succeeded,
        "errored": batch.request_counts.errored,
        "canceled": batch.request_counts.canceled,
        "expired": batch.request_counts.expired,
    }


def collect_results(batch_id: str) -> dict:
    """Collect results from a completed batch."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    conn = get_conn()

    # Load mapping
    rows = conn.execute(
        "SELECT custom_id, symbol, article_ids FROM batch_request_map WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()

    mapping = {}
    for r in rows:
        mapping[r["custom_id"]] = {
            "symbol": r["symbol"],
            "article_ids": json.loads(r["article_ids"]),
        }

    stats = {"processed": 0, "relevant": 0, "irrelevant": 0, "errors": 0}

    for result in client.messages.batches.results(batch_id):
        custom_id = result.custom_id
        info = mapping.get(custom_id)
        if not info:
            stats["errors"] += 1
            continue

        symbol = info["symbol"]
        article_ids = info["article_ids"]

        if result.result.type != "succeeded":
            stats["errors"] += len(article_ids)
            continue

        message = result.result.message
        text = message.content[0].text if message.content else "[]"

        try:
            start = text.find("[")
            end = text.rfind("]") + 1
            if start < 0 or end <= start:
                stats["errors"] += len(article_ids)
                continue

            items = json.loads(text[start:end])

            for item in items:
                idx = item.get("i")
                if idx is None or idx >= len(article_ids):
                    stats["errors"] += 1
                    continue

                is_relevant = item.get("r") in ("y", "relevant")
                raw_s = item.get("s", "0")
                up_reason = (item.get("u") or "").strip()
                down_reason = (item.get("d") or "").strip()
                # If the model can articulate a directional stock impact,
                # treat the article as relevant even if r came back inconsistent.
                if not is_relevant and (up_reason or down_reason):
                    is_relevant = True
                relevance = "relevant" if is_relevant else "irrelevant"
                sentiment = {"+": "positive", "-": "negative"}.get(raw_s, "neutral")
                # Repair inconsistent outputs:
                # if model says neutral but provides only one directional reason,
                # treat it as directional instead of neutral.
                if sentiment == "neutral":
                    has_up = bool(up_reason)
                    has_down = bool(down_reason)
                    if has_up and not has_down:
                        sentiment = "positive"
                    elif has_down and not has_up:
                        sentiment = "negative"
                if not is_relevant:
                    sentiment = "neutral"
                    up_reason = ""
                    down_reason = ""

                conn.execute(
                    """INSERT OR REPLACE INTO layer1_results
                       (news_id, symbol, relevance, key_discussion, sentiment,
                        reason_growth, reason_decrease)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        article_ids[idx],
                        symbol,
                        relevance,
                        item.get("e", ""),
                        sentiment,
                        up_reason,
                        down_reason,
                    ),
                )
                stats["processed"] += 1
                if is_relevant:
                    stats["relevant"] += 1
                else:
                    stats["irrelevant"] += 1

        except (json.JSONDecodeError, KeyError) as e:
            print(f"  Parse error for {custom_id}: {e}")
            stats["errors"] += len(article_ids)

    conn.execute(
        "UPDATE batch_jobs SET status = 'collected', completed = ?, finished_at = datetime('now') WHERE batch_id = ?",
        (stats["processed"], batch_id),
    )
    conn.commit()
    conn.close()

    return stats


def main():
    if len(sys.argv) < 2:
        # Auto-find the latest uncollected batch job
        conn = get_conn()
        jobs = conn.execute("SELECT * FROM batch_jobs ORDER BY created_at DESC").fetchall()
        conn.close()
        if not jobs:
            print("No batch jobs found. Run batch_submit first.")
            return
        print("Existing batch jobs:")
        for j in jobs:
            print(f"  {j['batch_id']}  status={j['status']}  total={j['total']}  created={j['created_at']}")

        # Pick latest uncollected
        conn = get_conn()
        job = conn.execute(
            "SELECT batch_id FROM batch_jobs WHERE status NOT IN ('collected', 'expired') ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not job:
            print("\nAll batch jobs already collected.")
            return
        batch_id = job["batch_id"]
        print(f"\nAuto-selected latest pending batch: {batch_id}")
    else:
        batch_id = sys.argv[1]

    print(f"Checking batch: {batch_id}")
    status = check_status(batch_id)
    print(f"Status: {status['status']}")
    print(f"  Succeeded: {status['succeeded']}")
    print(f"  Processing: {status['processing']}")
    print(f"  Errored: {status['errored']}")

    if status["status"] == "ended":
        print("\nBatch completed! Collecting results...")
        stats = collect_results(batch_id)
        print(f"\n=== Layer 1 Results ===")
        print(f"Processed:  {stats['processed']}")
        print(f"Relevant:   {stats['relevant']}")
        print(f"Irrelevant: {stats['irrelevant']}")
        print(f"Errors:     {stats['errors']}")

        print("\n=== Running FinBERT on recent neutral articles ===")
        try:
            from backend.finbert_reclassify_recent import reclassify_recent
            reclassify_recent(days=4)
        except ModuleNotFoundError as e:
            if e.name == "transformers":
                print("Skipping FinBERT re-check: `transformers` is not installed in this .venv.")
                print("Install it with: .venv/bin/pip install transformers torch")
            else:
                raise
    elif status["status"] == "in_progress":
        print("\nBatch still processing. Run this command again later.")
    else:
        print(f"\nBatch status: {status['status']}")


if __name__ == "__main__":
    main()
