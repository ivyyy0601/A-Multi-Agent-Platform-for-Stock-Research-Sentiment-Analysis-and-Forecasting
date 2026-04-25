"""Repair inconsistent relevance labels in layer1_results.

Rules:
- irrelevant + any non-empty reason => relevant
- irrelevant rows that remain irrelevant => neutral sentiment and empty reasons
"""

from __future__ import annotations

from backend.database import get_conn


def repair() -> dict:
    conn = get_conn()

    rows = conn.execute(
        """
        SELECT rowid,
               lower(coalesce(relevance, '')) AS relevance,
               trim(coalesce(reason_growth, '')) AS reason_growth,
               trim(coalesce(reason_decrease, '')) AS reason_decrease
        FROM layer1_results
        """
    ).fetchall()

    promote: list[tuple[int]] = []
    normalize: list[tuple[int]] = []

    for r in rows:
        if r["relevance"] != "irrelevant":
            continue
        has_up = bool(r["reason_growth"])
        has_down = bool(r["reason_decrease"])
        if has_up or has_down:
            promote.append((r["rowid"],))
        else:
            normalize.append((r["rowid"],))

    if promote:
        conn.executemany(
            "UPDATE layer1_results SET relevance = 'relevant' WHERE rowid = ?",
            promote,
        )
    if normalize:
        conn.executemany(
            "UPDATE layer1_results SET sentiment = 'neutral', reason_growth = '', reason_decrease = '' WHERE rowid = ?",
            normalize,
        )
    conn.commit()
    conn.close()

    return {
        "promoted_to_relevant": len(promote),
        "normalized_irrelevant": len(normalize),
        "scanned_irrelevant": len(promote) + len(normalize),
    }


def main() -> None:
    stats = repair()
    print(
        f"Promoted {stats['promoted_to_relevant']} irrelevant rows to relevant; "
        f"normalized {stats['normalized_irrelevant']} irrelevant rows."
    )


if __name__ == "__main__":
    main()
