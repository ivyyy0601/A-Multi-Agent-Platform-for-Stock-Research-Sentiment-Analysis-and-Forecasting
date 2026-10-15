#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple


DB_PATH = "/Users/ivy_ai/Desktop/IvyTrader/backend_analysis/data/stock_analysis.db"
OUT_DIR = "/Users/ivy_ai/Desktop/IvyTrader/回测/data_inventory"


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_csv(path: str, rows: List[Dict[str, object]]) -> None:
    ensure_dir(os.path.dirname(path))
    if not rows:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_price_coverage(conn: sqlite3.Connection) -> List[Dict[str, object]]:
    query = """
    SELECT code, MIN(date) AS min_date, MAX(date) AS max_date, COUNT(*) AS rows
    FROM stock_daily
    GROUP BY code
    ORDER BY rows DESC, code ASC
    """
    return [
        {
            "code": row[0],
            "min_date": row[1],
            "max_date": row[2],
            "rows": row[3],
        }
        for row in conn.execute(query)
    ]


def load_fundamental_rows(conn: sqlite3.Connection) -> List[Tuple[str, str, str]]:
    query = """
    SELECT code, created_at, payload
    FROM fundamental_snapshot
    ORDER BY code ASC, created_at ASC
    """
    return [(str(r[0]), str(r[1]), str(r[2])) for r in conn.execute(query)]


def extract_fundamental_coverage(rows: List[Tuple[str, str, str]]) -> List[Dict[str, object]]:
    grouped: Dict[str, List[Tuple[str, dict]]] = defaultdict(list)
    for code, created_at, payload_text in rows:
        try:
            payload = json.loads(payload_text)
        except Exception:
            payload = {}
        grouped[code].append((created_at, payload))

    result: List[Dict[str, object]] = []
    for code, items in grouped.items():
        first_created = items[0][0]
        last_created = items[-1][0]
        sample_payload = items[-1][1] if isinstance(items[-1][1], dict) else {}
        growth = (sample_payload.get("growth") or {}).get("data") or {}
        earnings = (sample_payload.get("earnings") or {}).get("data") or {}
        report = earnings.get("financial_report") or {}

        result.append(
            {
                "code": code,
                "rows": len(items),
                "min_created": first_created,
                "max_created": last_created,
                "has_growth": bool(growth),
                "has_earnings": bool(earnings),
                "report_date": report.get("report_date"),
                "revenue": report.get("revenue"),
                "net_profit": report.get("net_profit"),
                "operating_cash_flow": report.get("cashflow_operating"),
                "roe": report.get("roe"),
                "revenue_yoy": growth.get("revenue_yoy"),
                "net_profit_yoy": growth.get("net_profit_yoy"),
                "gross_margin": growth.get("gross_margin"),
            }
        )
    return sorted(result, key=lambda x: (-int(x["rows"]), str(x["code"])))


def build_candidate_windows(
    price_rows: List[Dict[str, object]],
    fundamental_rows: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    price_map = {str(r["code"]): r for r in price_rows}
    result: List[Dict[str, object]] = []
    for f in fundamental_rows:
        code = str(f["code"])
        price = price_map.get(code)
        if not price:
            continue
        result.append(
            {
                "code": code,
                "price_min_date": price["min_date"],
                "price_max_date": price["max_date"],
                "price_rows": price["rows"],
                "fundamental_min_created": f["min_created"],
                "fundamental_max_created": f["max_created"],
                "fundamental_rows": f["rows"],
                "recommended_replay_start": max(str(price["min_date"]), str(f["min_created"])[:10]),
                "recommended_replay_end": min(str(price["max_date"]), str(f["max_created"])[:10]),
                "has_growth": f["has_growth"],
                "has_earnings": f["has_earnings"],
            }
        )
    return sorted(result, key=lambda x: (-int(x["fundamental_rows"]), str(x["code"])))


def build_summary(price_rows: List[Dict[str, object]], fundamental_rows: List[Dict[str, object]], candidates: List[Dict[str, object]]) -> str:
    lines = [
        "# 实验数据盘点",
        "",
        f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"- Price symbols: {len(price_rows)}",
        f"- Fundamental symbols: {len(fundamental_rows)}",
        f"- Replay candidates: {len(candidates)}",
        "",
        "## 推荐优先标的",
        "",
        "| Code | Replay Start | Replay End | Price Rows | Fundamental Rows |",
        "|---|---|---|---:|---:|",
    ]
    for row in candidates[:10]:
        lines.append(
            f"| {row['code']} | {row['recommended_replay_start']} | {row['recommended_replay_end']} | "
            f"{row['price_rows']} | {row['fundamental_rows']} |"
        )
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- 第一版历史重放建议优先使用 replay candidates 里基础面快照和价格都较完整的股票。",
            "- 对当前库来说，AAPL / NVDA / AMZN / TSLA 最适合先做小样本实验。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    ensure_dir(OUT_DIR)
    conn = sqlite3.connect(DB_PATH)
    try:
        price_rows = load_price_coverage(conn)
        fundamental_raw_rows = load_fundamental_rows(conn)
        fundamental_rows = extract_fundamental_coverage(fundamental_raw_rows)
        candidates = build_candidate_windows(price_rows, fundamental_rows)

        write_csv(os.path.join(OUT_DIR, "price_coverage.csv"), price_rows)
        write_csv(os.path.join(OUT_DIR, "fundamental_coverage.csv"), fundamental_rows)
        write_csv(os.path.join(OUT_DIR, "replay_candidates.csv"), candidates)

        summary = build_summary(price_rows, fundamental_rows, candidates)
        with open(os.path.join(OUT_DIR, "summary.md"), "w", encoding="utf-8") as f:
            f.write(summary)

        print(summary)
        print(f"\nSaved inventory to: {OUT_DIR}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
