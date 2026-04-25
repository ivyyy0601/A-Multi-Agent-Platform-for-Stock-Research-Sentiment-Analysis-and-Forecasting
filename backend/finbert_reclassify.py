"""
Re-classify neutral+relevant articles in layer1_results using FinBERT.
Overwrites sentiment with whichever label FinBERT scores highest.
"""

import time
from transformers import pipeline

from backend.config import settings
from backend.database import get_conn

BATCH_SIZE = 64

print("Loading FinBERT model (ProsusAI/finbert)...")
finbert = pipeline("text-classification", model="ProsusAI/finbert", top_k=1)
print("Model loaded.\n")


def reclassify():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT lr.rowid, n.title, lr.key_discussion
        FROM layer1_results lr
        JOIN news_raw n ON n.id = lr.news_id
        WHERE lr.sentiment = 'neutral' AND lr.relevance = 'relevant'
    """)
    rows = cur.fetchall()
    total = len(rows)
    print(f"Found {total} neutral+relevant articles to re-classify.\n")

    updated = 0
    kept = 0
    start = time.time()

    for batch_start in range(0, total, BATCH_SIZE):
        batch = rows[batch_start: batch_start + BATCH_SIZE]

        texts = [
            ((title or "") + ". " + (key_discussion or ""))[:512]
            for _, title, key_discussion in batch
        ]

        results = finbert(texts, truncation=True, max_length=512)

        updates = []
        for i, result in enumerate(results):
            rowid = batch[i][0]
            top_label = result[0]["label"].lower()

            if top_label != "neutral":
                updates.append((top_label, rowid))
                updated += 1
            else:
                kept += 1

        if updates:
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

    conn.close()
    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s.")
    print(f"  Updated (neutral → positive/negative): {updated}")
    print(f"  Kept neutral:                           {kept}")
    print(f"  Total processed:                        {total}")


if __name__ == "__main__":
    reclassify()
