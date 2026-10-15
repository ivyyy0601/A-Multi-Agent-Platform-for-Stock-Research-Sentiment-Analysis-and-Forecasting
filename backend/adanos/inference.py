"""Inference: generate T+1 forecast for a ticker using ensemble + cosine similarity."""

import json
import numpy as np
from pathlib import Path
import pandas as pd

import joblib

from backend.adanos.features import build_features, FEATURE_COLS
from backend.adanos.client import get_reddit_explain, get_news_explain
from backend.adanos.forecast_store import _next_weekday, get_latest_feature_dates

MODELS_DIR = Path(__file__).parent / "models"
LR_COMB_WEIGHT = 0.5
SIM_COMB_WEIGHT = 0.5
MIN_SIMILARITY = 0.1  # keep a wider but still relevant historical candidate pool
SIM_TOP_K = 7
SIM_TEMP = 1.5
CONFIDENCE_GATE = 0.57


def _load_model(ticker: str):
    """Load per-ticker model, fall back to UNIFIED."""
    for name in [ticker.upper(), "UNIFIED"]:
        path = MODELS_DIR / f"{name}_ensemble.joblib"
        meta_path = MODELS_DIR / f"{name}_meta.json"
        if path.exists():
            return joblib.load(path), json.loads(meta_path.read_text())
    return None, None


def _ensemble_predict(models: dict, X: np.ndarray) -> tuple[str, float]:
    """Get P(up) from the primary ML model."""
    model = models.get("xgb") or models["lr"]
    proba = model.predict_proba(X)[0]
    p_up = float(proba[1])
    direction = "up" if p_up >= 0.5 else "down"
    return direction, p_up


def _find_similar_days(df, current_vec: np.ndarray, top_k: int = SIM_TOP_K) -> list[dict]:
    """Find most similar historical days using z-score Euclidean distance.
    Similarity = exp(-distance / n_features), ranges 0-1.
    """
    n = len(df)
    if n < 10:
        return []

    X_hist = df[FEATURE_COLS].values.astype(np.float64)
    np.nan_to_num(X_hist, copy=False)

    # Z-score normalize so each feature contributes equally
    mean = np.mean(X_hist, axis=0)
    std  = np.std(X_hist, axis=0)
    std[std < 1e-10] = 1.0

    X_norm   = np.clip((X_hist - mean) / std, -3, 3)
    cur_norm = np.clip((current_vec - mean) / std, -3, 3)

    # Euclidean distance
    diffs = X_norm - cur_norm          # (n, features)
    dists = np.sqrt((diffs ** 2).sum(axis=1))

    # Convert to 0-1 similarity: closer = higher score
    n_feats = X_norm.shape[1]
    sims = np.exp(-dists / n_feats)

    # Exclude last 5 days (too close to current)
    sims[max(0, n - 5):] = -999

    top_idx = np.argsort(sims)[::-1][:top_k]

    close = df["close"].values
    dates = df["date"].dt.strftime("%Y-%m-%d").tolist()
    results = []
    for idx in top_idx:
        if sims[idx] < MIN_SIMILARITY:
            continue
        next_idx = idx + 1
        if next_idx >= n:
            continue
        ret_next = round((close[next_idx] / close[idx] - 1) * 100, 2)
        results.append({
            "date":       dates[idx],
            "similarity": round(float(sims[idx]), 3),
            "next_day_ret": ret_next,
            "went_up":    bool(ret_next > 0),
        })

    return results


def _compute_drivers(df, last_row, importances: list) -> list[dict]:
    """Compute top drivers: z_score × feature_importance."""
    import pandas as pd

    feat_means = df[FEATURE_COLS].mean()
    feat_stds  = df[FEATURE_COLS].std().clip(lower=1e-10)
    imp_dict   = {f["name"]: f["importance"] for f in importances}

    drivers = []
    for col in FEATURE_COLS:
        val  = float(last_row[col]) if col in last_row.index and not np.isnan(last_row[col]) else 0.0
        z    = (val - feat_means[col]) / feat_stds[col]
        imp  = imp_dict.get(col, 0.0)
        contrib = abs(float(z)) * float(imp)
        drivers.append({
            "name":        col,
            "value":       round(val, 4),
            "z_score":     round(float(z), 2),
            "importance":  round(float(imp), 4),
            "contribution": round(contrib, 4),
        })

    drivers.sort(key=lambda x: x["contribution"], reverse=True)
    return drivers[:8]


def _patch_weekend_sentiment(df):
    """
    If there's sentiment data newer than the last OHLC row (e.g. Saturday/Sunday),
    average all those extra days per platform and overlay onto the last row.
    Also updates derived features: delta, buzz_spike, cross-platform signals.
    Returns (patched_df, sentiment_date) where sentiment_date is the latest date used.
    """
    import pandas as pd
    from backend.database import get_conn
    from backend.adanos.features import PLATFORMS

    last_ohlc_date = df.iloc[-1]["date"].strftime("%Y-%m-%d")

    conn = get_conn()
    rows = conn.execute(
        """SELECT date, platform, buzz_score, sentiment_score, bullish_pct, bearish_pct, mentions
           FROM platform_sentiment
           WHERE ticker = ? AND date > ?
           ORDER BY date""",
        (df.iloc[-1].get("ticker", ""), last_ohlc_date),
    ).fetchall()
    conn.close()

    if not rows:
        return df, last_ohlc_date

    # Group by platform, average all post-OHLC days
    from collections import defaultdict
    by_platform: dict = defaultdict(list)
    latest_date = last_ohlc_date
    for r in rows:
        by_platform[r["platform"]].append(r)
        if r["date"] > latest_date:
            latest_date = r["date"]

    # Patch last row
    df = df.copy()
    prev_row = df.iloc[-2] if len(df) >= 2 else df.iloc[-1]

    for p in PLATFORMS:
        prows = by_platform.get(p)
        if not prows:
            continue

        def avg(key):
            vals = [r[key] for r in prows if r[key] is not None]
            return float(np.mean(vals)) if vals else None

        sent = avg("sentiment_score")
        buzz = avg("buzz_score")
        bull = avg("bullish_pct")
        bear = avg("bearish_pct")
        ment = avg("mentions")

        if sent is not None:
            df.at[df.index[-1], f"{p}_sentiment"] = sent
            df.at[df.index[-1], f"{p}_sentiment_delta"] = sent - float(prev_row.get(f"{p}_sentiment", 0))
        if buzz is not None:
            df.at[df.index[-1], f"{p}_buzz"] = buzz
            df.at[df.index[-1], f"{p}_buzz_delta"] = buzz - float(prev_row.get(f"{p}_buzz", 0))
            avg5 = float(df.iloc[-1].get(f"{p}_buzz_5d", buzz) or buzz)
            df.at[df.index[-1], f"{p}_buzz_spike"] = buzz / max(avg5, 0.1)
        if bull is not None:
            df.at[df.index[-1], f"{p}_bullish"] = bull
        if bear is not None:
            df.at[df.index[-1], f"{p}_bearish"] = bear

    # Recompute cross-platform signals
    r_sent = float(df.iloc[-1].get("reddit_sentiment", 0) or 0)
    t_sent = float(df.iloc[-1].get("twitter_sentiment", 0) or 0)
    n_sent = float(df.iloc[-1].get("news_sentiment", 0) or 0)

    def _sign(v): return 1 if v > 0.05 else (-1 if v < -0.05 else 0)
    agree = (_sign(r_sent) == _sign(t_sent) == _sign(n_sent) and _sign(r_sent) != 0)
    df.at[df.index[-1], "platform_agreement"] = int(agree)
    df.at[df.index[-1], "reddit_vs_news_diff"] = r_sent - n_sent
    df.at[df.index[-1], "avg_sentiment"] = (r_sent + t_sent + n_sent) / 3
    r_bull = float(df.iloc[-1].get("reddit_bullish", 0) or 0)
    t_bull = float(df.iloc[-1].get("twitter_bullish", 0) or 0)
    n_bull = float(df.iloc[-1].get("news_bullish", 0) or 0)
    df.at[df.index[-1], "avg_bullish"] = (r_bull + t_bull + n_bull) / 3

    return df, latest_date


def generate_forecast(ticker: str, ref_date: str | None = None) -> dict:
    ticker = ticker.upper()
    latest_dates = get_latest_feature_dates(ticker)
    if not latest_dates["max_ohlc_date"]:
        return {"error": f"No OHLC data for {ticker}"}
    if not latest_dates["max_sentiment_date"]:
        return {"error": f"No sentiment data for {ticker}"}

    df = build_features(ticker)

    if df.empty or len(df) < 10:
        return {"error": f"Not enough data for {ticker}"}

    if ref_date:
        cutoff = pd.to_datetime(ref_date).normalize()
        df = df[df["date"] <= cutoff].copy()
        if df.empty or len(df) < 10:
            return {"error": f"Not enough data for {ticker} on or before {ref_date}"}

    models, meta = _load_model(ticker)
    if models is None:
        return {"error": f"No trained model found. Run: python -m backend.adanos.model"}

    # Add ticker column so _patch_weekend_sentiment can query DB
    df["ticker"] = ticker

    last_row = df.iloc[-1]
    last_date = df.iloc[-1]["date"].strftime("%Y-%m-%d")

    base_vec = last_row[FEATURE_COLS].values.astype(np.float64)

    if "xgb" in models and meta.get("feature_columns"):
        xgb_row = {col: float(last_row.get(col, 0) or 0) for col in FEATURE_COLS}
        xgb_row["ticker"] = ticker
        X_df = pd.get_dummies(pd.DataFrame([xgb_row]), columns=["ticker"])
        X_df = X_df.reindex(columns=meta["feature_columns"], fill_value=0)
        X = X_df.values.astype(np.float64)
    else:
        X = last_row[FEATURE_COLS].values.reshape(1, -1).astype(np.float64)
    np.nan_to_num(X, copy=False)

    model_direction, p_up = _ensemble_predict(models, X)

    # Cosine similarity - similar historical days
    current_vec = base_vec
    similar_days = _find_similar_days(df.iloc[:-1], current_vec, top_k=SIM_TOP_K)

    # Similar days stats
    sim_up = sum(1 for d in similar_days if d["went_up"])
    sim_total = len(similar_days)
    sim_avg_ret  = round(float(np.mean([d["next_day_ret"] for d in similar_days])), 2) if similar_days else None
    if similar_days:
        total_weight = float(sum(d["similarity"] for d in similar_days))
        weighted_avg_ret = round(
            float(sum(d["similarity"] * d["next_day_ret"] for d in similar_days) / max(total_weight, 1e-9)),
            2,
        )
        # Convert weighted average next-day return into a bounded pseudo-probability.
        # Around 0% => 50/50; larger absolute returns push confidence smoothly, not abruptly.
        sim_p_up = float(0.5 + 0.5 * np.tanh(weighted_avg_ret / SIM_TEMP))
        sim_up_ratio = round(sim_p_up, 4)
    else:
        weighted_avg_ret = None
        sim_up_ratio = None

    # Combine final signal.
    # Latest internal backtest currently favors the similarity leg over the raw LR output,
    # so the final page-level signal follows the similarity-adjusted probability.
    if sim_up_ratio is not None:
        combined_p_up = LR_COMB_WEIGHT * p_up + SIM_COMB_WEIGHT * sim_up_ratio
    else:
        combined_p_up = p_up
    direction  = "up" if combined_p_up >= 0.5 else "down"
    confidence = combined_p_up if direction == "up" else (1 - combined_p_up)
    actionable = confidence >= CONFIDENCE_GATE

    # Top drivers
    drivers = _compute_drivers(df, last_row, meta.get("top_features", []))

    # Current sentiment snapshot
    sentiment_now = {
        "reddit":  {"sentiment": round(float(last_row.get("reddit_sentiment", 0)), 3),
                    "buzz":      round(float(last_row.get("reddit_buzz", 0)), 1),
                    "bullish":   int(last_row.get("reddit_bullish", 0) or 0)},
        "twitter": {"sentiment": round(float(last_row.get("twitter_sentiment", 0)), 3),
                    "buzz":      round(float(last_row.get("twitter_buzz", 0)), 1),
                    "bullish":   int(last_row.get("twitter_bullish", 0) or 0)},
        "news":    {"sentiment": round(float(last_row.get("news_sentiment", 0)), 3),
                    "buzz":      round(float(last_row.get("news_buzz", 0)), 1),
                    "bullish":   int(last_row.get("news_bullish", 0) or 0)},
    }
    platform_agreement = bool(last_row.get("platform_agreement", 0))

    # Multi-signal conclusion
    signals = []
    signals.append(1 if direction == "up" else -1)
    if sim_up_ratio is not None:
        signals.append(1 if sim_up_ratio > 0.5 else -1)
    avg_sent = float(last_row.get("avg_sentiment", 0))
    if avg_sent > 0.05:
        signals.append(1)
    elif avg_sent < -0.05:
        signals.append(-1)

    avg_signal = sum(signals) / len(signals) if signals else 0
    if not actionable:
        overall = "unclear"
    elif avg_signal > 0.3:
        overall = "bullish"
    elif avg_signal < -0.3:
        overall = "bearish"
    else:
        overall = "unclear"

    return {
        "ticker":       ticker,
        "forecast_date": last_date,
        "target_date":   _next_weekday(last_date),
        "prediction": {
            "direction":       direction,
            "confidence":      round(confidence, 4),
            "lr_p_up":          round(p_up, 4),         # frontend ML signal field, now may come from XGB
        "cosine_up_ratio":  round(sim_up_ratio, 4) if sim_up_ratio is not None else None,
        "cosine_avg_ret":   sim_avg_ret,
        "cosine_weighted_ret": weighted_avg_ret,
            "model_accuracy":    meta.get("walkforward_dir_accuracy") or meta.get("walkforward_accuracy"),
            "baseline_accuracy": meta.get("baseline"),
            "actionable":      actionable,
        },
        "platform_agreement": platform_agreement,
        "sentiment_now":  sentiment_now,
        "similar_days":   similar_days,
        "similar_stats": {
            "count":       sim_total,
            "up_ratio":    sim_up_ratio,
            "avg_ret":     sim_avg_ret,
            "weighted_avg_ret": weighted_avg_ret,
        },
        "top_drivers":   drivers,
        "overall":       overall,
    }
