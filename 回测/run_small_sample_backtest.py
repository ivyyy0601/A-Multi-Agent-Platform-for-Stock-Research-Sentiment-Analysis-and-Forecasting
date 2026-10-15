#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_DB = "/Users/ivy_ai/Desktop/IvyTrader/backend_analysis/data/stock_analysis.db"
DEFAULT_OUT_DIR = "/Users/ivy_ai/Desktop/IvyTrader/回测/output"
HORIZONS = (1, 3, 5)
SCORE_BUCKETS: Sequence[Tuple[int, int]] = (
    (0, 20),
    (20, 40),
    (40, 60),
    (60, 80),
    (80, 101),
)


@dataclass
class AnalysisRow:
    id: int
    code: str
    name: str
    created_at: str
    sentiment_score: int
    operation_advice: str
    trend_prediction: str


@dataclass
class CoverageStats:
    max_price_date: str
    total_analyses: int
    eligible_samples: int
    pending_future_data: int
    missing_price_series: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Small-sample score backtest experiment.")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to stock_analysis.db")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="Directory for output files")
    return parser.parse_args()


def load_analysis_rows(conn: sqlite3.Connection) -> List[AnalysisRow]:
    query = """
    SELECT id, code, COALESCE(name, code), created_at,
           COALESCE(sentiment_score, 50),
           COALESCE(operation_advice, ''),
           COALESCE(trend_prediction, '')
    FROM analysis_history
    ORDER BY created_at ASC, id ASC
    """
    rows = []
    for row in conn.execute(query):
        rows.append(
            AnalysisRow(
                id=int(row[0]),
                code=str(row[1]),
                name=str(row[2]),
                created_at=str(row[3]),
                sentiment_score=int(row[4]),
                operation_advice=str(row[5]),
                trend_prediction=str(row[6]),
            )
        )
    return rows


def get_trading_dates_and_closes(conn: sqlite3.Connection, code: str, start_date: str) -> List[Tuple[str, float]]:
    query = """
    SELECT date, close
    FROM stock_daily
    WHERE code = ? AND date >= ? AND close IS NOT NULL
    ORDER BY date ASC
    """
    return [(str(r[0]), float(r[1])) for r in conn.execute(query, (code, start_date))]


def get_max_price_date(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT COALESCE(MAX(date), '') FROM stock_daily").fetchone()
    return str(row[0] or "")


def resolve_entry_and_forward(closes: List[Tuple[str, float]], horizon: int) -> Optional[Tuple[str, float, str, float, float]]:
    if len(closes) <= horizon:
        return None
    entry_date, entry_close = closes[0]
    exit_date, exit_close = closes[horizon]
    ret = (exit_close - entry_close) / entry_close * 100.0
    return entry_date, entry_close, exit_date, exit_close, ret


def score_bucket(score: int) -> str:
    for low, high in SCORE_BUCKETS:
        if low <= score < high:
            upper = 100 if high == 101 else high
            return f"{low}-{upper}"
    return "unknown"


def normalize_advice(advice: str) -> str:
    text = (advice or "").strip().lower()
    if not text:
        return "unknown"
    if any(k in text for k in ("buy", "买")):
        return "buy"
    if any(k in text for k in ("sell", "减", "卖")):
        return "sell"
    if any(k in text for k in ("watch", "hold", "观望", "持有")):
        return "hold/watch"
    return text


def avg(values: Iterable[float]) -> Optional[float]:
    vals = list(values)
    if not vals:
        return None
    return sum(vals) / len(vals)


def med(values: Iterable[float]) -> Optional[float]:
    vals = list(values)
    if not vals:
        return None
    return median(vals)


def win_rate(values: Iterable[float]) -> Optional[float]:
    vals = list(values)
    if not vals:
        return None
    wins = sum(1 for v in vals if v > 0)
    return wins / len(vals) * 100.0


def summarize_group(records: List[Dict[str, object]], key: str) -> List[Dict[str, object]]:
    groups: Dict[str, List[Dict[str, object]]] = {}
    for record in records:
        group_key = str(record[key])
        groups.setdefault(group_key, []).append(record)

    rows: List[Dict[str, object]] = []
    for group_key, items in sorted(groups.items(), key=lambda x: x[0]):
        row: Dict[str, object] = {
            key: group_key,
            "count": len(items),
        }
        for horizon in HORIZONS:
            values = [float(it[f"t{horizon}_ret_pct"]) for it in items if it.get(f"t{horizon}_ret_pct") is not None]
            row[f"t{horizon}_avg_pct"] = round(avg(values), 4) if values else None
            row[f"t{horizon}_median_pct"] = round(med(values), 4) if values else None
            row[f"t{horizon}_win_rate_pct"] = round(win_rate(values), 2) if values else None
        rows.append(row)
    return rows


def write_csv(path: str, rows: List[Dict[str, object]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not rows:
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_markdown(
    record_rows: List[Dict[str, object]],
    score_summary: List[Dict[str, object]],
    advice_summary: List[Dict[str, object]],
    coverage: CoverageStats,
) -> str:
    lines = [
        "# 小样本回测实验结果",
        "",
        f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"- Samples: {len(record_rows)}",
        f"- Total analyses in DB: {coverage.total_analyses}",
        f"- Latest price date in DB: {coverage.max_price_date or 'N/A'}",
        "",
        "## 覆盖情况",
        "",
        f"- Eligible samples: {coverage.eligible_samples}",
        f"- Waiting for future price data: {coverage.pending_future_data}",
        f"- Missing price series: {coverage.missing_price_series}",
        "",
        "## 分数分桶",
        "",
        "| Bucket | Count | T+1 Avg% | T+3 Avg% | T+5 Avg% | T+5 Win Rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in score_summary:
        lines.append(
            f"| {row['score_bucket']} | {row['count']} | "
            f"{row.get('t1_avg_pct', 'N/A')} | {row.get('t3_avg_pct', 'N/A')} | "
            f"{row.get('t5_avg_pct', 'N/A')} | {row.get('t5_win_rate_pct', 'N/A')} |"
        )
    lines.extend([
        "",
        "## 操作建议分组",
        "",
        "| Advice | Count | T+1 Avg% | T+3 Avg% | T+5 Avg% | T+5 Win Rate |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for row in advice_summary:
        lines.append(
            f"| {row['advice_group']} | {row['count']} | "
            f"{row.get('t1_avg_pct', 'N/A')} | {row.get('t3_avg_pct', 'N/A')} | "
            f"{row.get('t5_avg_pct', 'N/A')} | {row.get('t5_win_rate_pct', 'N/A')} |"
        )
    lines.extend([
        "",
        "## 说明",
        "",
        "- 本实验使用分析日之后第一个可用交易日收盘价作为起点。",
        "- 主要目标是看高分组未来收益是否系统性优于低分组。",
        "- 样本少时只能做方向性观察，不做统计显著性结论。",
        "- 如果 Samples 为 0，优先检查分析记录日期是否已经拥有足够的未来交易日价格。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    conn = sqlite3.connect(args.db)
    try:
        analysis_rows = load_analysis_rows(conn)
        record_rows: List[Dict[str, object]] = []
        pending_rows: List[Dict[str, object]] = []
        max_price_date = get_max_price_date(conn)
        pending_future_data = 0
        missing_price_series = 0

        for analysis in analysis_rows:
            analysis_date = analysis.created_at[:10]
            forward = get_trading_dates_and_closes(conn, analysis.code, analysis_date)
            if not forward:
                missing_price_series += 1
                pending_rows.append(
                    {
                        "analysis_id": analysis.id,
                        "code": analysis.code,
                        "created_at": analysis.created_at,
                        "score": analysis.sentiment_score,
                        "status": "missing_price_series",
                        "detail": f"No price rows on or after {analysis_date}",
                    }
                )
                continue
            if len(forward) < max(HORIZONS) + 1:
                pending_future_data += 1
                pending_rows.append(
                    {
                        "analysis_id": analysis.id,
                        "code": analysis.code,
                        "created_at": analysis.created_at,
                        "score": analysis.sentiment_score,
                        "status": "waiting_future_data",
                        "detail": f"Have {len(forward)} trading rows from {forward[0][0]} to {forward[-1][0]}, need {max(HORIZONS) + 1}",
                    }
                )
                continue

            row: Dict[str, object] = {
                "analysis_id": analysis.id,
                "code": analysis.code,
                "name": analysis.name,
                "created_at": analysis.created_at,
                "score": analysis.sentiment_score,
                "score_bucket": score_bucket(analysis.sentiment_score),
                "operation_advice": analysis.operation_advice,
                "advice_group": normalize_advice(analysis.operation_advice),
                "trend_prediction": analysis.trend_prediction,
            }

            for horizon in HORIZONS:
                resolved = resolve_entry_and_forward(forward, horizon)
                if resolved is None:
                    row[f"t{horizon}_entry_date"] = None
                    row[f"t{horizon}_entry_close"] = None
                    row[f"t{horizon}_exit_date"] = None
                    row[f"t{horizon}_exit_close"] = None
                    row[f"t{horizon}_ret_pct"] = None
                    continue
                entry_date, entry_close, exit_date, exit_close, ret = resolved
                row[f"t{horizon}_entry_date"] = entry_date
                row[f"t{horizon}_entry_close"] = round(entry_close, 4)
                row[f"t{horizon}_exit_date"] = exit_date
                row[f"t{horizon}_exit_close"] = round(exit_close, 4)
                row[f"t{horizon}_ret_pct"] = round(ret, 4)

            record_rows.append(row)

        score_summary = summarize_group(record_rows, "score_bucket")
        advice_summary = summarize_group(record_rows, "advice_group")
        coverage = CoverageStats(
            max_price_date=max_price_date,
            total_analyses=len(analysis_rows),
            eligible_samples=len(record_rows),
            pending_future_data=pending_future_data,
            missing_price_series=missing_price_series,
        )

        os.makedirs(args.out_dir, exist_ok=True)
        write_csv(os.path.join(args.out_dir, "record_level_returns.csv"), record_rows)
        write_csv(os.path.join(args.out_dir, "score_bucket_summary.csv"), score_summary)
        write_csv(os.path.join(args.out_dir, "advice_summary.csv"), advice_summary)
        write_csv(os.path.join(args.out_dir, "pending_samples.csv"), pending_rows)

        summary_md = build_markdown(record_rows, score_summary, advice_summary, coverage)
        with open(os.path.join(args.out_dir, "summary.md"), "w", encoding="utf-8") as f:
            f.write(summary_md)

        print(summary_md)
        print(f"\nSaved outputs to: {args.out_dir}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
