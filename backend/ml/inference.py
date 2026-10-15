"""Forecast module: 1D / 7D / 14D market-state forecast."""

import json
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import joblib

from backend.database import get_conn
from backend.ml.features import build_features, FEATURE_COLS
from backend.ml.features_v2 import build_features_v2, FEATURE_COLS_V2_MARKET, FEATURE_COLS_V2_CANDLE
from backend.ml.model import DETAIL_HORIZON_CONFIG
from backend.ml.similar import compute_similar_day_bundle

INFERENCE_FEATURE_SETS = {
    "v1_base": FEATURE_COLS,
    "v2_market": FEATURE_COLS_V2_MARKET,
    "v2_candle": FEATURE_COLS_V2_CANDLE,
}

MODELS_DIR = Path(__file__).parent / "models"


def _load_recent_news(symbol: str, window_days: int, ref_date: str | None = None) -> list[dict]:
    """Load recent news articles within the window.

    Args:
        ref_date: Reference date (YYYY-MM-DD). If None, uses the latest
                  available trade_date for this symbol in the database.
    """
    conn = get_conn()
    if ref_date is None:
        row = conn.execute(
            "SELECT MAX(trade_date) FROM news_aligned WHERE symbol = ?", (symbol,)
        ).fetchone()
        if row and row[0]:
            ref_date = row[0]
        else:
            ref_date = datetime.now().strftime("%Y-%m-%d")
    ref_dt = datetime.strptime(ref_date, "%Y-%m-%d") if isinstance(ref_date, str) else ref_date
    cutoff = (ref_dt - timedelta(days=window_days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        """SELECT na.news_id, na.trade_date, nr.title,
                  l1.sentiment, l1.chinese_summary,
                  l1.relevance, l1.key_discussion,
                  na.ret_t0, na.ret_t1,
                  nr.article_url
           FROM news_aligned na
           JOIN news_raw nr ON na.news_id = nr.id
           LEFT JOIN layer1_results l1 ON na.news_id = l1.news_id AND l1.symbol = na.symbol
           WHERE na.symbol = ? AND na.trade_date >= ? AND na.trade_date <= ?
           ORDER BY na.trade_date DESC""",
        (symbol, cutoff, ref_date),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _compute_window_features(df: pd.DataFrame, window_days: int) -> np.ndarray | None:
    """Build a compact state vector for the latest 1D / 7D / 14D horizon."""
    if df.empty:
        return None
    if window_days <= 1:
        vec = df.iloc[-1][FEATURE_COLS].values.astype(np.float64)
        np.nan_to_num(vec, copy=False)
        return vec

    n_rows = min(window_days, len(df))
    window_df = df.iloc[-n_rows:]
    last_row = window_df.iloc[-1]

    vec = np.array([
        float(window_df["sentiment_score"].mean()),
        float(window_df["n_relevant"].sum()),
        float(window_df["positive_ratio"].mean()),
        float(window_df["negative_ratio"].mean()),
        float(window_df["sentiment_momentum_3d"].iloc[-1]),
        float(last_row["ret_1d"]),
        float(last_row["ret_5d"]),
        float(((last_row["close"] / window_df.iloc[0]["close"]) - 1) if window_df.iloc[0]["close"] else 0.0),
        float(window_df["volatility_5d"].mean()),
        float(last_row["ma5_vs_ma20"]),
        float(last_row["rsi_14"]),
    ], dtype=np.float64)
    np.nan_to_num(vec, copy=False)
    return vec


def _find_similar_periods(
    df: pd.DataFrame, window_vec: np.ndarray, window_days: int, horizon_days: int, top_k: int = 10
) -> list[dict]:
    """Compare the current 1D / 7D / 14D state to historical states."""
    n = len(df)
    if n < window_days + horizon_days + 10:
        return []

    state_vecs = []
    dates = df["trade_date"].dt.strftime("%Y-%m-%d").tolist()
    max_start = n - window_days + 1
    for start in range(max_start):
        end = start + window_days
        window_df = df.iloc[start:end]
        last_row = window_df.iloc[-1]
        if window_days <= 1:
            vec = window_df.iloc[-1][FEATURE_COLS].values.astype(np.float64)
        else:
            vec = np.array([
                float(window_df["sentiment_score"].mean()),
                float(window_df["n_relevant"].sum()),
                float(window_df["positive_ratio"].mean()),
                float(window_df["negative_ratio"].mean()),
                float(window_df["sentiment_momentum_3d"].iloc[-1]),
                float(last_row["ret_1d"]),
                float(last_row["ret_5d"]),
                float(((last_row["close"] / window_df.iloc[0]["close"]) - 1) if window_df.iloc[0]["close"] else 0.0),
                float(window_df["volatility_5d"].mean()),
                float(last_row["ma5_vs_ma20"]),
                float(last_row["rsi_14"]),
            ], dtype=np.float64)
        np.nan_to_num(vec, copy=False)
        state_vecs.append(vec)
    window_vecs = np.vstack(state_vecs)

    # Normalize all vectors (including the target)
    all_vecs = np.vstack([window_vecs, window_vec.reshape(1, -1)])
    mean = np.mean(all_vecs, axis=0)
    std = np.std(all_vecs, axis=0)
    std[std < 1e-10] = 1.0
    all_norm = (all_vecs - mean) / std

    target_norm = all_norm[-1]
    history_norm = all_norm[:-1]

    # Cosine similarity
    norms = np.linalg.norm(history_norm, axis=1)
    norms[norms < 1e-10] = 1.0
    target_n = np.linalg.norm(target_norm)
    if target_n < 1e-10:
        target_n = 1.0
    sims = history_norm @ target_norm / (norms * target_n)

    # Exclude windows that overlap with the current period.
    exclude_start = max(0, len(sims) - window_days - 5)
    sims[exclude_start:] = -999

    # Top K
    top_indices = np.argsort(sims)[::-1][:top_k]

    results = []
    for idx in top_indices:
        if sims[idx] < -900:
            continue
        period_start = dates[idx]
        period_end = dates[min(idx + window_days - 1, n - 1)]
        after_start = idx + window_days
        after_end = min(after_start + horizon_days, n)

        if after_start >= n:
            continue

        close_vals = df["close"].values
        period_close = close_vals[min(idx + window_days - 1, n - 1)]

        ret_after_horizon = None
        if after_end > after_start:
            ret_after_horizon = round((close_vals[after_end - 1] / period_close - 1) * 100, 2)

        window_slice = df.iloc[idx:idx + window_days]
        avg_sentiment = float(window_slice["sentiment_score"].mean())

        results.append({
            "period_start": period_start,
            "period_end": period_end,
            "similarity": round(float(sims[idx]), 4),
            "avg_sentiment": round(avg_sentiment, 3),
            "n_relevant": int(window_slice["n_relevant"].sum()),
            "ret_after_horizon": ret_after_horizon,
        })
    return results


def generate_forecast(symbol: str, window_days: int = 7, ref_date: str | None = None) -> dict:
    """Generate a complete forecast report for a symbol.

    Args:
        symbol: Ticker symbol
        window_days: Horizon-aligned look-back window (1, 7, or 14)

    Returns:
        Complete forecast with prediction, similar periods, recent news, conclusion.
    """
    symbol = symbol.upper()
    df = build_features_v2(symbol, use_text=False)
    if df.empty:
        return {"error": f"No feature data for {symbol}"}

    if ref_date:
        cutoff = pd.to_datetime(ref_date).normalize()
        df = df[df["trade_date"] <= cutoff].copy()
        if df.empty:
            return {"error": f"No feature data for {symbol} on or before {ref_date}"}

    # Use last available trade date as reference (not today's date)
    last_date = df.iloc[-1]["trade_date"].strftime("%Y-%m-%d")

    if window_days not in {1, 7, 14}:
        return {"error": "window must be one of 1, 7, 14"}

    horizon_key = f"t{window_days}"

    # 1. Recent news
    recent_news = _load_recent_news(symbol, window_days, ref_date=last_date)
    relevant_news = [
        n for n in recent_news
        if n.get("relevance") in {"relevant", "high", "medium"}
    ]
    n_pos = sum(1 for n in relevant_news if n.get("sentiment") == "positive")
    n_neg = sum(1 for n in relevant_news if n.get("sentiment") == "negative")
    n_neu = sum(1 for n in relevant_news if n.get("sentiment") == "neutral")
    n_total = len(relevant_news)

    # Match sentiment to price direction: up day → positive news, down day → negative news
    def _impact_score(n):
        score = 0.0
        ret = n.get("ret_t0")
        sent = n.get("sentiment")
        # Sentiment matches price direction → high score
        if ret is not None and sent is not None:
            if ret > 0 and sent == "positive":
                score += 3.0
            elif ret < 0 and sent == "negative":
                score += 3.0
            elif sent == "neutral":
                score += 0.3
            else:
                score += 0.5  # mismatched sentiment/direction
        # Relevance boost
        if n.get("relevance") == "relevant":
            score += 2.0
        return score

    # Per day: only output if there's a sentiment-direction match, pick highest relevance
    from collections import defaultdict
    daily_candidates = defaultdict(list)
    for n in recent_news:
        ret = n.get("ret_t0")
        sent = n.get("sentiment")
        if ret is None or sent is None:
            continue
        # Only keep articles where sentiment matches price direction
        if (ret > 0 and sent == "positive") or (ret < 0 and sent == "negative"):
            daily_candidates[n["trade_date"]].append(n)

    def _relevance_score(n):
        return 1 if n.get("relevance") == "relevant" else 0

    impact_sorted = [
        max(articles, key=_relevance_score)
        for date, articles in sorted(daily_candidates.items(), reverse=True)
    ]

    news_summary = {
        "total": n_total,
        "positive": n_pos,
        "negative": n_neg,
        "neutral": n_neu,
        "sentiment_ratio": round((n_pos - n_neg) / max(n_total, 1), 3),
        # Top headlines (most recent)
        "top_headlines": [
            {
                "date": n["trade_date"],
                "title": (n["title"] or "")[:100],
                "sentiment": n.get("sentiment", "unknown"),
                "summary": (n.get("chinese_summary") or "")[:120],
            }
            for n in relevant_news[:10]
        ],
        # Most impactful articles (by price move magnitude)
        "top_impact": [
            {
                "news_id": n["news_id"],
                "date": n["trade_date"],
                "title": (n["title"] or "")[:120],
                "sentiment": n.get("sentiment", "unknown"),
                "relevance": n.get("relevance"),
                "key_discussion": (n.get("key_discussion") or "")[:150],
                "ret_t0": round(n["ret_t0"] * 100, 2) if n.get("ret_t0") else None,
                "ret_t1": round(n["ret_t1"] * 100, 2) if n.get("ret_t1") else None,
                "article_url": n.get("article_url"),
            }
            for n in impact_sorted[:window_days]
        ],
    }

    # 2. Window feature vector (average of last N trading days)
    window_vec = _compute_window_features(df, window_days)
    if window_vec is None:
        return {"error": "Cannot compute features"}

    # 3. Model predictions
    prediction = None

    # 3a. Check for LSTM model (best for some tickers like TSLA)
    try:
        from backend.ml.lstm_model import predict_lstm
        lstm_result = predict_lstm(symbol)
    except ImportError:
        lstm_result = None
    if lstm_result is not None:
        h = lstm_result["horizon"]  # e.g. "t3"
        if prediction is None:
            prediction = {}
        prediction[h] = {
            "direction": lstm_result["direction"],
            "confidence": lstm_result["confidence"],
            "model_type": "LSTM",
            "top_drivers": [],  # LSTM doesn't have per-feature importances
            "model_accuracy": None,
            "baseline_accuracy": None,
        }

    # 3b. XGBoost predictions for t1/t7/t14
    for horizon in ["t1", "t7", "t14"]:
        model_path = MODELS_DIR / f"{symbol}_{horizon}.joblib"
        meta_path = MODELS_DIR / f"{symbol}_{horizon}_meta.json"
        if not model_path.exists():
            continue

        model = joblib.load(model_path)
        meta = json.loads(meta_path.read_text())
        feature_set = meta.get("feature_set", "v1_base")
        feature_cols = [c for c in INFERENCE_FEATURE_SETS.get(feature_set, FEATURE_COLS) if c in df.columns]

        last_row = df.iloc[-1]
        X = last_row[feature_cols].values.reshape(1, -1).astype(np.float64)
        np.nan_to_num(X, copy=False)

        proba = model.predict_proba(X)[0]
        pred_class = int(np.argmax(proba))
        confidence = float(proba[pred_class])

        # Instance-level feature contribution (deviation from training mean)
        feature_means = df[FEATURE_COLS].mean()
        feature_stds = df[FEATURE_COLS].std().clip(lower=1e-10)
        if hasattr(model, "feature_importances_"):
            importances = np.asarray(model.feature_importances_, dtype=float)
        elif hasattr(model, "named_steps"):
            clf = model.named_steps["clf"]
            if hasattr(clf, "feature_importances_"):
                importances = np.asarray(clf.feature_importances_, dtype=float)
            elif hasattr(clf, "coef_"):
                coef = np.asarray(clf.coef_)
                if coef.ndim == 2:
                    coef = coef[0]
                importances = np.abs(coef)
            else:
                importances = np.zeros(len(feature_cols), dtype=float)
        else:
            importances = np.zeros(len(feature_cols), dtype=float)

        contributions = []
        feature_means = df[feature_cols].mean()
        feature_stds = df[feature_cols].std().clip(lower=1e-10)
        for i, col in enumerate(feature_cols):
            val = float(last_row[col]) if pd.notna(last_row[col]) else 0.0
            z = (val - feature_means[col]) / feature_stds[col]
            contrib = abs(z) * importances[i]
            contributions.append({
                "name": col,
                "value": round(val, 4),
                "importance": round(float(importances[i]), 4),
                "z_score": round(float(z), 2),
                "contribution": round(float(contrib), 4),
            })
        contributions.sort(key=lambda x: x["contribution"], reverse=True)

        if prediction is None:
            prediction = {}
        prediction[horizon] = {
            "direction": "up" if pred_class == 1 else "down",
            "confidence": round(confidence, 4),
            "model_type": meta.get("selected_family", meta.get("model_type", "model")).upper(),
            "top_drivers": contributions[:6],
            "model_accuracy": meta.get("accuracy", 0),
            "baseline_accuracy": meta.get("baseline", 0),
            "feature_set": meta.get("feature_set"),
        }

    if prediction is None:
        return {"error": f"No trained model for {symbol}"}

    # 4. Similar historical days using the same single-day method as the Similar Days panel
    similar_bundle = compute_similar_day_bundle(symbol, last_date, top_k=10, horizon_days=window_days)
    if "error" in similar_bundle:
        similar_periods = []
        similar_stats = {
            "count": 0,
            "horizon_days": window_days,
            "up_ratio": None,
            "avg_ret": None,
            "weighted_up_ratio": None,
            "weighted_avg_ret": None,
        }
    else:
        similar_periods = [
            {
                "period_start": day["date"],
                "period_end": day["date"],
                "similarity": day["similarity"],
                "avg_sentiment": day["sentiment_score"],
                "n_relevant": day["n_relevant"],
                "ret_after_horizon": day["ret_after_horizon"],
            }
            for day in similar_bundle["similar_days"]
        ]
        stats_h = similar_bundle["stats"]
        similar_stats = {
            "count": stats_h["count"],
            "horizon_days": window_days,
            "up_ratio": stats_h["up_ratio_h"],
            "avg_ret": stats_h["avg_ret_h"],
            "weighted_up_ratio": stats_h["weighted_up_ratio_h"],
            "weighted_avg_ret": stats_h["weighted_avg_ret_h"],
        }

    # 5. Generate conclusion (pure statistics, no AI API)
    conclusion = _build_conclusion(
        symbol, window_days, news_summary, prediction, similar_stats
    )

    last_date = df.iloc[-1]["trade_date"].strftime("%Y-%m-%d")

    return {
        "symbol": symbol,
        "window_days": window_days,
        "horizon_key": horizon_key,
        "forecast_date": last_date,
        "news_summary": news_summary,
        "prediction": prediction,
        "similar_periods": similar_periods,
        "similar_stats": similar_stats,
        "conclusion": conclusion,
    }


def _build_conclusion(
    symbol: str,
    window_days: int,
    news_summary: dict,
    prediction: dict,
    similar_stats: dict,
) -> str:
    """Build an English-language conclusion from statistical signals."""
    parts = []

    window_label = f"past {window_days} trading day" if window_days == 1 else f"past {window_days} trading days"
    n = news_summary["total"]
    ratio = news_summary["sentiment_ratio"]

    # News summary
    if n == 0:
        parts.append(f"{symbol} has no related news in the {window_label}.")
    else:
        tone = "leaning positive" if ratio > 0.1 else "leaning negative" if ratio < -0.1 else "neutral"
        parts.append(
            f"{symbol} had {n} related news in the {window_label}, "
            f"{news_summary['positive']} positive / {news_summary['negative']} negative, "
            f"overall sentiment {tone} ({ratio:+.2f})."
        )

    # Model prediction
    horizon_labels = [
        ("1D", "t1"), ("7D", "t7"), ("14D", "t14"),
    ]
    for h_label, h_key in horizon_labels:
        p = prediction.get(h_key)
        if not p:
            continue
        d = "bullish" if p["direction"] == "up" else "bearish"
        conf = p["confidence"] * 100
        model_tag = f"[{p.get('model_type', 'XGBoost')}]" if p.get("model_type") else ""
        parts.append(f"{model_tag} Model {h_label} prediction: {d}, confidence {conf:.0f}%.")

    # Similar periods
    if similar_stats["count"] > 0:
        ur = similar_stats.get("weighted_up_ratio") or similar_stats.get("up_ratio")
        ar = similar_stats.get("weighted_avg_ret") or similar_stats.get("avg_ret")
        if ur is not None and ar is not None:
            parts.append(
                f"Among {similar_stats['count']} historically similar periods, "
                f"{ur*100:.0f}% rose over the following {window_days} trading days, "
                f"with an average return of {ar:+.1f}%."
            )

    # Overall judgment
    signals = []
    for h in ("t1", "t7", "t14"):
        p = prediction.get(h, {})
        if p:
            signals.append(1 if p["direction"] == "up" else -1)
    similarity_signal = similar_stats.get("weighted_up_ratio")
    if similarity_signal is None:
        similarity_signal = similar_stats.get("up_ratio")
    if similarity_signal is not None:
        signals.append(1 if similarity_signal > 0.5 else -1)
    if ratio > 0.1:
        signals.append(1)
    elif ratio < -0.1:
        signals.append(-1)

    if signals:
        avg_signal = sum(signals) / len(signals)
        if avg_signal > 0.3:
            parts.append("Multi-signal assessment: leaning bullish.")
        elif avg_signal < -0.3:
            parts.append("Multi-signal assessment: leaning bearish.")
        else:
            parts.append("Multi-signal assessment: direction unclear, recommend holding.")

    return " ".join(parts)
