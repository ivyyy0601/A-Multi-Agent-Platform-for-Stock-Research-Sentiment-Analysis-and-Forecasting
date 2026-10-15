#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
import requests


PROJECT_ROOT = "/Users/ivy_ai/Desktop/IvyTrader"
BACKEND_ROOT = os.path.join(PROJECT_ROOT, "backend_analysis")
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from src.stock_analyzer import StockTrendAnalyzer  # noqa: E402


DEFAULT_DB = "/Users/ivy_ai/Desktop/IvyTrader/backend_analysis/data/stock_analysis.db"
DEFAULT_OUT_DIR = "/Users/ivy_ai/Desktop/IvyTrader/回测/replay_output"
DEFAULT_CODES = ("AAPL", "NVDA", "AMZN", "TSLA")
DEFAULT_START_DATE = "2026-03-19"
DEFAULT_END_DATE = "2026-03-23"
DEFAULT_ADANOS_URL = "https://api.adanos.org"
HORIZONS = (1, 3, 5)
SCORE_BUCKETS: Sequence[Tuple[int, int]] = (
    (0, 20),
    (20, 40),
    (40, 60),
    (60, 80),
    (80, 101),
)


@dataclass
class ReplayRecord:
    code: str
    analysis_date: str
    final_score: float
    technical_score: float
    fundamental_score: float
    sentiment_score_raw: float
    risk_score: float
    forecast_score: float
    operation_advice: str
    decision_type: str
    trend_prediction: str
    confidence_level: str
    fundamental_snapshot_time: str


def clamp(value: Optional[float], low: float = 0.0, high: float = 100.0) -> float:
    if value is None:
        return low
    return max(low, min(high, float(value)))


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    try:
        text = str(value).strip().replace("%", "")
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def average(values: Sequence[Optional[float]], default: float) -> float:
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return default
    return sum(nums) / len(nums)


def has_required_us_fundamentals(fundamental_context: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(fundamental_context, dict):
        return False
    growth = ((fundamental_context.get("growth") or {}).get("data") or {}) if isinstance(fundamental_context.get("growth"), dict) else {}
    earnings = ((fundamental_context.get("earnings") or {}).get("data") or {}) if isinstance(fundamental_context.get("earnings"), dict) else {}
    financial_report = (earnings.get("financial_report") or {}) if isinstance(earnings, dict) else {}
    dividend = (earnings.get("dividend") or {}) if isinstance(earnings, dict) else {}
    growth_required = ("revenue_yoy", "net_profit_yoy", "roe", "gross_margin")
    report_required = ("report_date", "revenue", "net_profit_parent", "operating_cash_flow", "roe")
    dividend_required = ("ttm_cash_dividend_per_share", "ttm_dividend_yield_pct", "ttm_event_count")

    def present(v: Any) -> bool:
        if v is None:
            return False
        if isinstance(v, str):
            return bool(v.strip())
        return True

    return (
        all(present(growth.get(field)) for field in growth_required)
        and all(present(financial_report.get(field)) for field in report_required)
        and all(present(dividend.get(field)) for field in dividend_required)
    )


def map_alignment_score(text: Any) -> float:
    norm = str(text or "").lower()
    if "strong bullish" in norm:
        return 95.0
    if "bullish alignment" in norm:
        return 90.0
    if "bearish alignment" in norm:
        return 20.0
    if "short-term improving" in norm:
        return 65.0
    if "short-term weakening" in norm:
        return 35.0
    if "range-bound" in norm or "mixed" in norm or "tangled" in norm or "consolidation" in norm:
        return 50.0
    if "weak bullish" in norm:
        return 60.0
    if "weak bearish" in norm:
        return 35.0
    return 50.0


def compute_technical_score(enhanced_context: Dict[str, Any]) -> float:
    trend = enhanced_context.get("trend_analysis", {}) if isinstance(enhanced_context, dict) else {}
    realtime = enhanced_context.get("realtime", {}) if isinstance(enhanced_context, dict) else {}
    ma_score = map_alignment_score(trend.get("ma_alignment") or trend.get("trend_status") or enhanced_context.get("ma_status"))
    bias = abs(to_float(trend.get("bias_ma5")) or 0.0)
    if bias <= 2:
        bias_score = 90.0
    elif bias <= 5:
        bias_score = 65.0
    elif bias <= 8:
        bias_score = 35.0
    else:
        bias_score = 15.0
    volume_ratio = to_float(realtime.get("volume_ratio"))
    if volume_ratio is None:
        volume_ratio = to_float(enhanced_context.get("volume_change_ratio"))
    if volume_ratio is None:
        volume_score = 50.0
    elif volume_ratio >= 1.5:
        volume_score = 85.0
    elif volume_ratio >= 1.0:
        volume_score = 65.0
    elif volume_ratio >= 0.8:
        volume_score = 50.0
    elif volume_ratio >= 0.5:
        volume_score = 35.0
    else:
        volume_score = 20.0
    signal_score = clamp(to_float(trend.get("signal_score")) or 50.0)
    return clamp(0.35 * ma_score + 0.25 * bias_score + 0.20 * volume_score + 0.20 * signal_score)


def compute_fundamental_score(fundamental_context: Optional[Dict[str, Any]], enhanced_context: Dict[str, Any]) -> float:
    fc = fundamental_context if isinstance(fundamental_context, dict) else {}
    growth = ((fc.get("growth") or {}).get("data") or {}) if isinstance(fc.get("growth"), dict) else {}
    earnings = ((fc.get("earnings") or {}).get("data") or {}) if isinstance(fc.get("earnings"), dict) else {}
    financial = earnings.get("financial_report", {}) if isinstance(earnings.get("financial_report"), dict) else {}
    realtime = enhanced_context.get("realtime", {}) if isinstance(enhanced_context, dict) else {}

    revenue_yoy = to_float(growth.get("revenue_yoy"))
    profit_yoy = to_float(growth.get("net_profit_yoy"))
    growth_avg = average([revenue_yoy, profit_yoy], default=50.0)
    if growth_avg >= 20:
        growth_score = 92.0
    elif growth_avg >= 10:
        growth_score = 82.0
    elif growth_avg >= 0:
        growth_score = 62.0
    elif growth_avg >= -10:
        growth_score = 35.0
    else:
        growth_score = 15.0

    roe = to_float(financial.get("roe"))
    gross_margin = to_float(growth.get("gross_margin"))
    roe_score = 50.0 if roe is None else (95.0 if roe >= 30 else 85.0 if roe >= 20 else 70.0 if roe >= 10 else 50.0 if roe >= 0 else 20.0)
    margin_score = 50.0 if gross_margin is None else (90.0 if gross_margin >= 50 else 75.0 if gross_margin >= 35 else 60.0 if gross_margin >= 20 else 45.0 if gross_margin >= 0 else 20.0)
    profitability_score = average([roe_score, margin_score], default=50.0)

    op_cf = to_float(financial.get("operating_cash_flow"))
    net_profit = to_float(financial.get("net_profit_parent"))
    if op_cf is None:
        cashflow_score = 50.0
    elif op_cf > 0 and (net_profit is None or net_profit <= 0 or op_cf >= 0.5 * net_profit):
        cashflow_score = 82.0
    elif op_cf > 0:
        cashflow_score = 65.0
    else:
        cashflow_score = 20.0

    pe = to_float(realtime.get("pe_ratio"))
    pb = to_float(realtime.get("pb_ratio"))
    if pe is None:
        valuation_support = 55.0
    elif growth_avg >= 15 and pe < 40:
        valuation_support = 76.0
    elif growth_avg >= 15 and pe < 70:
        valuation_support = 64.0
    elif growth_avg < 5 and pe > 30:
        valuation_support = 25.0
    elif pe > 50:
        valuation_support = 30.0
    elif pe < 20:
        valuation_support = 78.0
    else:
        valuation_support = 55.0
    if pb is not None and pb > 10:
        valuation_support = max(15.0, valuation_support - 10.0)

    return clamp(0.30 * growth_score + 0.25 * profitability_score + 0.20 * cashflow_score + 0.25 * valuation_support)


def compute_risk_score(enhanced_context: Dict[str, Any], fundamental_context: Optional[Dict[str, Any]]) -> float:
    trend = enhanced_context.get("trend_analysis", {}) if isinstance(enhanced_context, dict) else {}
    realtime = enhanced_context.get("realtime", {}) if isinstance(enhanced_context, dict) else {}
    ma_alignment = str(trend.get("ma_alignment") or trend.get("trend_status") or "").lower()

    technical_risk = 85.0
    if "bearish alignment" in ma_alignment or "strong bearish" in ma_alignment:
        technical_risk = 20.0
    elif "bullish alignment" in ma_alignment or "strong bullish" in ma_alignment:
        technical_risk = 82.0
    elif "weakening" in ma_alignment or "weak bearish" in ma_alignment:
        technical_risk = 35.0

    bias = abs(to_float(trend.get("bias_ma5")) or 0.0)
    if bias > 5:
        technical_risk = max(10.0, technical_risk - 15.0)

    volume_ratio = to_float(realtime.get("volume_ratio"))
    if volume_ratio is not None and volume_ratio < 0.8:
        technical_risk = max(10.0, technical_risk - 10.0)

    fc = fundamental_context if isinstance(fundamental_context, dict) else {}
    growth = ((fc.get("growth") or {}).get("data") or {}) if isinstance(fc.get("growth"), dict) else {}
    pe = to_float(realtime.get("pe_ratio"))
    pb = to_float(realtime.get("pb_ratio"))
    growth_avg = average([to_float(growth.get("revenue_yoy")), to_float(growth.get("net_profit_yoy"))], default=50.0)

    valuation_risk = 75.0
    if pe is not None and pe > 50:
        valuation_risk = 30.0
    elif pe is not None and pe > 30 and growth_avg < 10:
        valuation_risk = 35.0
    elif pe is not None and pe < 20:
        valuation_risk = 80.0
    if pb is not None and pb > 10:
        valuation_risk = max(15.0, valuation_risk - 12.0)

    risk_factors = trend.get("risk_factors") if isinstance(trend, dict) else None
    event_risk = 90.0
    if isinstance(risk_factors, list):
        event_risk -= min(20.0, 5.0 * len(risk_factors))
    event_risk = clamp(event_risk)

    completeness_checks = [
        isinstance(enhanced_context.get("today"), dict) and bool(enhanced_context.get("today")),
        isinstance(enhanced_context.get("realtime"), dict) and bool(enhanced_context.get("realtime")),
        isinstance(enhanced_context.get("trend_analysis"), dict) and bool(enhanced_context.get("trend_analysis")),
        has_required_us_fundamentals(fundamental_context),
    ]
    data_quality = 100.0 * sum(1 for ok in completeness_checks if ok) / len(completeness_checks)

    return clamp(0.35 * technical_risk + 0.25 * valuation_risk + 0.30 * event_risk + 0.10 * data_quality)


def derive_scored_signal(final_score: float, technical_score: float) -> Tuple[int, str, str, str]:
    score_int = int(round(clamp(final_score)))
    if score_int >= 80:
        operation_advice = "Buy"
        decision_type = "buy"
    elif score_int >= 65:
        operation_advice = "Add"
        decision_type = "buy"
    elif score_int >= 45:
        operation_advice = "Watch"
        decision_type = "hold"
    elif score_int >= 25:
        operation_advice = "Reduce"
        decision_type = "sell"
    else:
        operation_advice = "Sell"
        decision_type = "sell"

    if technical_score >= 85:
        trend_prediction = "Strong Bullish"
    elif technical_score >= 65:
        trend_prediction = "Bullish"
    elif technical_score >= 45:
        trend_prediction = "Neutral"
    elif technical_score >= 25:
        trend_prediction = "Bearish"
    else:
        trend_prediction = "Strong Bearish"
    return score_int, operation_advice, decision_type, trend_prediction


def derive_confidence_level(scores: Dict[str, float]) -> str:
    dispersion = abs(scores["technical_score"] - scores["fundamental_score"])
    conviction = abs(scores["final_score"] - 50.0)
    if conviction >= 22 and dispersion <= 35:
        return "High"
    if conviction >= 10:
        return "Medium"
    return "Low"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Historical replay experiment for structured scoring.")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to stock_analysis.db")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="Directory for output files")
    parser.add_argument("--codes", default=",".join(DEFAULT_CODES), help="Comma-separated tickers")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE, help="Replay start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=DEFAULT_END_DATE, help="Replay end date (YYYY-MM-DD)")
    parser.add_argument("--sentiment-mode", choices=("static", "adanos"), default="static", help="Use static neutral sentiment or Adanos 30-day historical sentiment")
    parser.add_argument("--sentiment-default", type=float, default=50.0, help="Neutral placeholder sentiment score")
    parser.add_argument("--forecast-default", type=float, default=50.0, help="Neutral placeholder forecast score")
    parser.add_argument("--social-days", type=int, default=30, help="Adanos historical sentiment lookback window")
    parser.add_argument("--adanos-url", default=DEFAULT_ADANOS_URL, help="Base URL for Adanos API")
    parser.add_argument("--adanos-api-key", default=os.getenv("SOCIAL_SENTIMENT_API_KEY", ""), help="Adanos API key, defaults to env SOCIAL_SENTIMENT_API_KEY")
    return parser.parse_args()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def write_csv(path: str, rows: List[Dict[str, Any]]) -> None:
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


def score_bucket(score: float) -> str:
    score_int = int(round(score))
    for low, high in SCORE_BUCKETS:
        if low <= score_int < high:
            upper = 100 if high == 101 else high
            return f"{low}-{upper}"
    return "unknown"


def normalize_advice(advice: str) -> str:
    text = (advice or "").strip().lower()
    if any(k in text for k in ("buy", "add")):
        return "buy/add"
    if any(k in text for k in ("sell", "reduce")):
        return "sell/reduce"
    if any(k in text for k in ("watch", "hold")):
        return "watch/hold"
    return text or "unknown"


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
    return sum(1 for v in vals if v > 0) / len(vals) * 100.0


def summarize_group(rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row[key]), []).append(row)

    result: List[Dict[str, Any]] = []
    for group_key, items in sorted(groups.items(), key=lambda x: x[0]):
        summary: Dict[str, Any] = {key: group_key, "count": len(items)}
        for horizon in HORIZONS:
            vals = [float(it[f"t{horizon}_ret_pct"]) for it in items if it.get(f"t{horizon}_ret_pct") is not None]
            summary[f"t{horizon}_avg_pct"] = round(avg(vals), 4) if vals else None
            summary[f"t{horizon}_median_pct"] = round(med(vals), 4) if vals else None
            summary[f"t{horizon}_win_rate_pct"] = round(win_rate(vals), 2) if vals else None
        result.append(summary)
    return result


def load_price_history(conn: sqlite3.Connection, code: str) -> pd.DataFrame:
    query = """
    SELECT date, open, high, low, close, volume, pct_chg, ma5, ma10, ma20
    FROM stock_daily
    WHERE code = ?
    ORDER BY date ASC
    """
    rows = conn.execute(query, (code,)).fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        rows,
        columns=["date", "open", "high", "low", "close", "volume", "pct_chg", "ma5", "ma10", "ma20"],
    )


def load_latest_fundamental_snapshot(conn: sqlite3.Connection, code: str, as_of_date: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    query = """
    SELECT created_at, payload
    FROM fundamental_snapshot
    WHERE code = ? AND created_at <= ?
    ORDER BY created_at DESC
    LIMIT 1
    """
    row = conn.execute(query, (code, f"{as_of_date} 23:59:59.999999")).fetchone()
    if not row:
        return None, None
    try:
        payload = json.loads(str(row[1]))
    except Exception:
        payload = None
    return payload, str(row[0])


def fetch_platform_sentiment(
    platform: str,
    code: str,
    as_of_date: str,
    *,
    base_url: str,
    api_key: str,
    days: int,
) -> Optional[Dict[str, Any]]:
    if not api_key:
        return None
    try:
        resp = requests.get(
            f"{base_url.rstrip('/')}/{platform}/stocks/v1/stock/{code.upper()}",
            headers={"X-API-Key": api_key, "Accept": "application/json"},
            params={"days": days, "end_date": as_of_date},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not isinstance(data, dict) or data.get("found") is False:
            return None
        return data
    except Exception:
        return None


def compute_sentiment_score_from_api(
    code: str,
    as_of_date: str,
    *,
    base_url: str,
    api_key: str,
    days: int,
    default: float,
) -> Tuple[float, str]:
    reddit = fetch_platform_sentiment("reddit", code, as_of_date, base_url=base_url, api_key=api_key, days=days)
    x_data = fetch_platform_sentiment("x", code, as_of_date, base_url=base_url, api_key=api_key, days=days)
    news = fetch_platform_sentiment("news", code, as_of_date, base_url=base_url, api_key=api_key, days=days)

    def platform_score(data: Optional[Dict[str, Any]]) -> Optional[float]:
        if not isinstance(data, dict):
            return None
        sent = to_float(data.get("sentiment_score"))
        if sent is None:
            return None
        return clamp((sent + 1.0) * 50.0)

    reddit_score = platform_score(reddit)
    x_score = platform_score(x_data)
    news_score = platform_score(news)

    signs: List[int] = []
    values: List[float] = []
    for score in (reddit_score, x_score, news_score):
        if score is None:
            continue
        values.append(score)
        signs.append(1 if score > 55 else -1 if score < 45 else 0)

    if len(values) >= 2:
        spread = max(values) - min(values)
        non_zero = [s for s in signs if s != 0]
        if non_zero and len(set(non_zero)) == 1:
            agreement_score = 85.0 if spread < 15 else 72.0
        elif spread < 20:
            agreement_score = 62.0
        else:
            agreement_score = 38.0
    else:
        agreement_score = default

    weighted = []
    total_weight = 0.0
    for weight, score in ((0.35, news_score), (0.30, x_score), (0.20, reddit_score)):
        if score is not None:
            weighted.append(weight * score)
            total_weight += weight
    if total_weight <= 0:
        return float(default), "static_fallback"
    social_core = sum(weighted) / total_weight
    return clamp(0.85 * social_core + 0.15 * agreement_score), "adanos"


def build_enhanced_context(code: str, df_slice: pd.DataFrame, trend_result: Dict[str, Any]) -> Dict[str, Any]:
    latest = df_slice.iloc[-1]
    yesterday = df_slice.iloc[-2] if len(df_slice) >= 2 else None
    volume_ratio = trend_result.get("volume_ratio_5d")
    change_60d = None
    if len(df_slice) >= 60:
        old_close = float(df_slice.iloc[-60]["close"])
        if old_close:
            change_60d = (float(latest["close"]) - old_close) / old_close * 100.0
    elif len(df_slice) >= 20:
        old_close = float(df_slice.iloc[0]["close"])
        if old_close:
            change_60d = (float(latest["close"]) - old_close) / old_close * 100.0

    return {
        "code": code,
        "date": str(latest["date"]),
        "today": {
            "open": float(latest["open"]),
            "high": float(latest["high"]),
            "low": float(latest["low"]),
            "close": float(latest["close"]),
            "volume": float(latest["volume"]),
            "pct_chg": float(latest["pct_chg"]) if latest["pct_chg"] is not None else None,
            "ma5": float(latest["ma5"]) if latest["ma5"] is not None else None,
            "ma10": float(latest["ma10"]) if latest["ma10"] is not None else None,
            "ma20": float(latest["ma20"]) if latest["ma20"] is not None else None,
        },
        "yesterday": {
            "close": float(yesterday["close"]),
            "volume": float(yesterday["volume"]),
        } if yesterday is not None else {},
        "price_change_ratio": (
            (float(latest["close"]) - float(yesterday["close"])) / float(yesterday["close"]) * 100.0
            if yesterday is not None and float(yesterday["close"]) != 0
            else None
        ),
        "volume_change_ratio": (
            float(latest["volume"]) / float(yesterday["volume"])
            if yesterday is not None and float(yesterday["volume"]) != 0
            else None
        ),
        "realtime": {
            "price": float(latest["close"]),
            "volume_ratio": float(volume_ratio) if volume_ratio is not None else None,
            "turnover_rate": None,
            "pe_ratio": None,
            "pb_ratio": None,
            "total_mv": None,
            "circ_mv": None,
            "change_60d": change_60d,
        },
        "trend_analysis": {
            "trend_status": trend_result.get("trend_status"),
            "ma_alignment": trend_result.get("ma_alignment"),
            "trend_strength": trend_result.get("trend_strength"),
            "bias_ma5": trend_result.get("bias_ma5"),
            "bias_ma10": trend_result.get("bias_ma10"),
            "volume_status": trend_result.get("volume_status"),
            "volume_trend": trend_result.get("volume_trend"),
            "buy_signal": trend_result.get("buy_signal"),
            "signal_score": trend_result.get("signal_score"),
            "signal_reasons": trend_result.get("signal_reasons"),
            "risk_factors": trend_result.get("risk_factors"),
            "rsi_6": trend_result.get("rsi_6"),
            "rsi_status": trend_result.get("rsi_status"),
        },
    }


def add_forward_returns(row: Dict[str, Any], full_df: pd.DataFrame, analysis_idx: int) -> None:
    for horizon in HORIZONS:
        future_idx = analysis_idx + horizon
        if future_idx >= len(full_df):
            row[f"t{horizon}_date"] = None
            row[f"t{horizon}_close"] = None
            row[f"t{horizon}_ret_pct"] = None
            continue
        entry_close = float(full_df.iloc[analysis_idx]["close"])
        exit_close = float(full_df.iloc[future_idx]["close"])
        ret = (exit_close - entry_close) / entry_close * 100.0 if entry_close else None
        row[f"t{horizon}_date"] = str(full_df.iloc[future_idx]["date"])
        row[f"t{horizon}_close"] = round(exit_close, 4)
        row[f"t{horizon}_ret_pct"] = round(ret, 4) if ret is not None else None


def build_markdown(
    records: List[Dict[str, Any]],
    score_summary: List[Dict[str, Any]],
    advice_summary: List[Dict[str, Any]],
    args: argparse.Namespace,
) -> str:
    lines = [
        "# 历史重放评分实验",
        "",
        f"- Generated at: {datetime.now().isoformat(timespec='seconds')}",
        f"- Codes: {args.codes}",
        f"- Date range: {args.start_date} -> {args.end_date}",
        f"- Replay samples: {len(records)}",
        f"- Sentiment score mode: {args.sentiment_mode}",
        f"- Forecast score mode: static {args.forecast_default}",
        "",
        "## 分数分桶",
        "",
        "| Bucket | Count | T+1 Avg% | T+3 Avg% | T+5 Avg% | T+5 Win Rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in score_summary:
        lines.append(
            f"| {row['score_bucket']} | {row['count']} | {row.get('t1_avg_pct', 'N/A')} | "
            f"{row.get('t3_avg_pct', 'N/A')} | {row.get('t5_avg_pct', 'N/A')} | "
            f"{row.get('t5_win_rate_pct', 'N/A')} |"
        )
    lines.extend(
        [
            "",
            "## 操作建议分组",
            "",
            "| Advice | Count | T+1 Avg% | T+3 Avg% | T+5 Avg% | T+5 Win Rate |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in advice_summary:
        lines.append(
            f"| {row['advice_group']} | {row['count']} | {row.get('t1_avg_pct', 'N/A')} | "
            f"{row.get('t3_avg_pct', 'N/A')} | {row.get('t5_avg_pct', 'N/A')} | "
            f"{row.get('t5_win_rate_pct', 'N/A')} |"
        )
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- 这版实验优先复用本地 `stock_daily` 和 `fundamental_snapshot`。",
            "- forecast 分当前使用中性占位，不参与方向性放大。",
            "- 目标先验证结构化评分在小样本下是否具备排序能力。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    ensure_dir(args.out_dir)
    codes = [c.strip().upper() for c in args.codes.split(",") if c.strip()]
    analyzer = StockTrendAnalyzer()
    conn = sqlite3.connect(args.db)

    try:
        records: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        for code in codes:
            full_df = load_price_history(conn, code)
            if full_df.empty:
                skipped.append({"code": code, "analysis_date": None, "reason": "missing_price_history"})
                continue

            mask = (full_df["date"] >= args.start_date) & (full_df["date"] <= args.end_date)
            replay_dates = full_df.loc[mask, "date"].tolist()
            if not replay_dates:
                skipped.append({"code": code, "analysis_date": None, "reason": "no_dates_in_range"})
                continue

            for analysis_date in replay_dates:
                analysis_idx = int(full_df.index[full_df["date"] == analysis_date][0])
                df_slice = full_df.iloc[: analysis_idx + 1].copy()
                if len(df_slice) < 20:
                    skipped.append({"code": code, "analysis_date": analysis_date, "reason": "insufficient_price_history"})
                    continue

                fundamental_context, snapshot_time = load_latest_fundamental_snapshot(conn, code, str(analysis_date))
                if not fundamental_context:
                    skipped.append({"code": code, "analysis_date": analysis_date, "reason": "missing_fundamental_snapshot"})
                    continue

                trend_result = analyzer.analyze(df_slice[["date", "open", "high", "low", "close", "volume"]].copy(), code).to_dict()
                enhanced_context = build_enhanced_context(code, df_slice, trend_result)

                technical_score = compute_technical_score(enhanced_context)
                fundamental_score = compute_fundamental_score(fundamental_context, enhanced_context)
                risk_score = compute_risk_score(enhanced_context, fundamental_context)
                if args.sentiment_mode == "adanos":
                    sentiment_score_raw, sentiment_source = compute_sentiment_score_from_api(
                        code,
                        str(analysis_date),
                        base_url=args.adanos_url,
                        api_key=args.adanos_api_key,
                        days=args.social_days,
                        default=float(args.sentiment_default),
                    )
                else:
                    sentiment_score_raw, sentiment_source = float(args.sentiment_default), "static"
                forecast_score = float(args.forecast_default)
                final_score = clamp(
                    0.45 * technical_score
                    + 0.25 * fundamental_score
                    + 0.15 * sentiment_score_raw
                    + 0.12 * risk_score
                    + 0.03 * forecast_score
                )
                score_int, operation_advice, decision_type, trend_prediction = derive_scored_signal(
                    final_score,
                    technical_score,
                )
                confidence_level = derive_confidence_level(
                    {
                        "technical_score": technical_score,
                        "fundamental_score": fundamental_score,
                        "sentiment_score_raw": sentiment_score_raw,
                        "risk_score": risk_score,
                        "forecast_score": forecast_score,
                        "final_score": final_score,
                    }
                )

                row: Dict[str, Any] = {
                    "code": code,
                    "analysis_date": str(analysis_date),
                    "close": round(float(df_slice.iloc[-1]["close"]), 4),
                    "score_bucket": score_bucket(score_int),
                    "final_score": round(final_score, 2),
                    "technical_score": round(technical_score, 2),
                    "fundamental_score": round(fundamental_score, 2),
                    "sentiment_score_raw": round(sentiment_score_raw, 2),
                    "risk_score": round(risk_score, 2),
                    "forecast_score": round(forecast_score, 2),
                    "sentiment_source": sentiment_source,
                    "operation_advice": operation_advice,
                    "advice_group": normalize_advice(operation_advice),
                    "decision_type": decision_type,
                    "trend_prediction": trend_prediction,
                    "confidence_level": confidence_level,
                    "ma_alignment": trend_result.get("ma_alignment"),
                    "bias_ma5": round(float(trend_result.get("bias_ma5") or 0.0), 4),
                    "signal_score": trend_result.get("signal_score"),
                    "volume_ratio": round(float(trend_result.get("volume_ratio_5d") or 0.0), 4),
                    "fundamental_snapshot_time": snapshot_time,
                }
                add_forward_returns(row, full_df, analysis_idx)
                records.append(row)

        score_summary = summarize_group(records, "score_bucket")
        advice_summary = summarize_group(records, "advice_group")

        write_csv(os.path.join(args.out_dir, "replay_scores.csv"), records)
        write_csv(os.path.join(args.out_dir, "score_bucket_summary.csv"), score_summary)
        write_csv(os.path.join(args.out_dir, "advice_summary.csv"), advice_summary)
        write_csv(os.path.join(args.out_dir, "skipped_samples.csv"), skipped)

        summary_md = build_markdown(records, score_summary, advice_summary, args)
        with open(os.path.join(args.out_dir, "summary.md"), "w", encoding="utf-8") as f:
            f.write(summary_md)

        print(summary_md)
        print(f"\nSaved replay outputs to: {args.out_dir}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
