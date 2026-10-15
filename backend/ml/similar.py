"""Find historically similar trading days using a compact single-day feature set.

Hybrid similarity: 0.65 × numeric (z-score cosine) + 0.35 × semantic (RAG ChromaDB).
Semantic component is optional — falls back to pure numeric if RAG store unavailable.
"""

import logging
import os

import numpy as np
import pandas as pd
from backend.ml.features import build_features
from backend.database import get_conn

logger = logging.getLogger(__name__)

# Path to backend_analysis RAG store (override via env var)
_RAG_DIR = os.environ.get(
    "RAG_STORE_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "backend_analysis", "data", "rag_store"),
)
_NUMERIC_WEIGHT = 0.65
_SEMANTIC_WEIGHT = 0.35

SIMILARITY_FEATURE_COLS = [
    "sentiment_score",
    "n_relevant",
    "positive_ratio",
    "negative_ratio",
    "sentiment_momentum_3d",
    "ret_1d",
    "ret_5d",
    "rsi_14",
    "ma5_vs_ma20",
    "volatility_5d",
]


def _forward_return(close_by_date: dict[str, float], ohlc_dates: list[str], d: str, days: int) -> float | None:
    if d not in ohlc_dates:
        return None
    idx = ohlc_dates.index(d)
    if idx + days >= len(ohlc_dates):
        return None
    return (close_by_date[ohlc_dates[idx + days]] / close_by_date[d] - 1) * 100


def _load_target_day_news_snapshot(symbol: str, date: str) -> dict:
    """Load exact clicked-day news stats using the same published-date basis as Day News."""
    conn = get_conn()
    row = conn.execute(
        """
        SELECT COUNT(*) AS n_articles,
               SUM(CASE WHEN l1.relevance IN ('relevant','high','medium') THEN 1 ELSE 0 END) AS n_relevant,
               SUM(CASE WHEN l1.relevance IN ('relevant','high','medium') AND l1.sentiment = 'positive' THEN 1 ELSE 0 END) AS n_positive,
               SUM(CASE WHEN l1.relevance IN ('relevant','high','medium') AND l1.sentiment = 'negative' THEN 1 ELSE 0 END) AS n_negative,
               SUM(CASE WHEN l1.relevance IN ('relevant','high','medium') AND l1.sentiment = 'neutral' THEN 1 ELSE 0 END) AS n_neutral
        FROM news_aligned na
        JOIN news_raw nr ON na.news_id = nr.id
        LEFT JOIN layer1_results l1 ON na.news_id = l1.news_id AND l1.symbol = na.symbol
        WHERE na.symbol = ? AND DATE(na.published_utc) = ?
        """,
        (symbol, date),
    ).fetchone()
    conn.close()

    n_articles = int(row["n_articles"] or 0)
    n_relevant = int(row["n_relevant"] or 0)
    n_positive = int(row["n_positive"] or 0)
    n_negative = int(row["n_negative"] or 0)
    n_neutral = int(row["n_neutral"] or 0)
    relevant_total = max(n_relevant, 1)

    return {
        "n_articles": n_articles,
        "n_relevant": n_relevant,
        "n_positive": n_positive,
        "n_negative": n_negative,
        "n_neutral": n_neutral,
        "sentiment_score": round((n_positive - n_negative) / relevant_total, 4) if n_relevant > 0 else 0.0,
        "positive_ratio": round(n_positive / relevant_total, 4) if n_relevant > 0 else 0.0,
        "negative_ratio": round(n_negative / relevant_total, 4) if n_relevant > 0 else 0.0,
    }


def _get_news_text_for_dates(symbol: str, dates: list) -> dict:
    """
    Load news text (titles + key_discussion) per date from DB.
    Returns {date_str: combined_text}.
    """
    if not dates:
        return {}
    placeholders = ",".join("?" * len(dates))
    conn = get_conn()
    rows = conn.execute(
        f"""
        SELECT na.trade_date, nr.title, l1.key_discussion
        FROM news_aligned na
        JOIN news_raw nr ON na.news_id = nr.id
        LEFT JOIN layer1_results l1 ON na.news_id = l1.news_id AND l1.symbol = na.symbol
        WHERE na.symbol = ?
          AND (na.trade_date IN ({placeholders}) OR DATE(na.published_utc) IN ({placeholders}))
          AND l1.key_discussion IS NOT NULL
        ORDER BY na.trade_date, na.published_utc DESC
        """,
        [symbol] + list(dates) + list(dates),
    ).fetchall()
    conn.close()

    by_date: dict = {}
    for r in rows:
        d = r["trade_date"]
        if d not in by_date:
            by_date[d] = []
        if r["title"]:
            by_date[d].append(r["title"])
        if r["key_discussion"]:
            by_date[d].append(r["key_discussion"])

    return {d: " | ".join(parts[:12]) for d, parts in by_date.items()}


def _get_semantic_similarities(symbol: str, target_text: str, candidate_dates: list) -> dict:
    """
    Compute semantic similarity between target day's news and each candidate date's news.

    Embeds target + each candidate's news text, computes cosine similarity directly.
    Returns dict of {date_str: semantic_sim (0-1)}.
    Silently returns {} if RAG unavailable or no news found.
    """
    if not target_text.strip() or not candidate_dates:
        return {}
    try:
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

        rag_dir = os.path.abspath(_RAG_DIR)
        if not os.path.exists(rag_dir):
            return {}

        # Load candidate news texts from DB
        date_texts = _get_news_text_for_dates(symbol, candidate_dates)
        if not date_texts:
            return {}

        ef = ONNXMiniLM_L6_V2()

        # Embed target + all candidates in one batch
        dates_with_text = [d for d in candidate_dates if d in date_texts and date_texts[d].strip()]
        if not dates_with_text:
            return {}

        all_texts = [target_text] + [date_texts[d] for d in dates_with_text]
        embeddings = np.array(ef(all_texts), dtype=np.float64)

        # Normalise
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms < 1e-10] = 1.0
        embeddings = embeddings / norms

        target_vec = embeddings[0]
        candidate_vecs = embeddings[1:]

        # Cosine similarity = dot product of normalised vectors
        cosine_sims = candidate_vecs @ target_vec

        return {
            d: round(float(max(0.0, sim)), 4)
            for d, sim in zip(dates_with_text, cosine_sims)
        }

    except Exception as exc:
        logger.debug("[hybrid] Semantic similarity failed: %s", exc)
        return {}


def compute_similar_day_bundle(symbol: str, date: str, top_k: int = 10, horizon_days: int = 1) -> dict:
    """Core single-day similarity engine used by both Similar Days panel and Forecast similarity."""
    df = build_features(symbol)
    if df.empty:
        return {"error": f"No feature data for {symbol}"}

    df["date_str"] = df["trade_date"].dt.strftime("%Y-%m-%d")

    target_mask = df["date_str"] == date
    if not target_mask.any():
        return {"error": f"No trading-day features available for {symbol} on {date}"}

    target_idx = df[target_mask].index[0]
    target_row = df.loc[target_idx]

    X = df[SIMILARITY_FEATURE_COLS].values.astype(np.float64)
    np.nan_to_num(X, copy=False)

    # Normalize features (z-score)
    mean = np.mean(X, axis=0)
    std = np.std(X, axis=0)
    std[std < 1e-10] = 1.0
    X_norm = (X - mean) / std

    target_vec = X_norm[target_idx]

    # Cosine similarity
    norms = np.linalg.norm(X_norm, axis=1)
    norms[norms < 1e-10] = 1.0
    target_norm = np.linalg.norm(target_vec)
    if target_norm < 1e-10:
        target_norm = 1.0

    numeric_similarities = X_norm @ target_vec / (norms * target_norm)

    # Exclude the target itself and nearby days (within 5 days)
    for i in range(max(0, target_idx - 5), min(len(df), target_idx + 6)):
        numeric_similarities[i] = -999

    # ── Hybrid: numeric first-pass → semantic re-rank ────────────────────────
    # Step 1: numeric top pool (larger than top_k to give semantic room to re-rank)
    pool_size = top_k * 4
    pool_indices = np.argsort(numeric_similarities)[::-1][:pool_size]
    pool_indices = [i for i in pool_indices if numeric_similarities[i] > -999]
    pool_dates = [df.iloc[i]["date_str"] for i in pool_indices]

    # Step 2: get semantic similarity for pool only
    # Try target date first; if no relevant news, fall back to nearest prior days
    target_texts = _get_news_text_for_dates(symbol, [date])
    target_text = target_texts.get(date, "")
    if not target_text.strip():
        # Look up to 3 prior trading days for news
        prior_dates = [df.iloc[max(0, target_idx - i)]["date_str"] for i in range(1, 4)]
        prior_texts = _get_news_text_for_dates(symbol, prior_dates)
        for pdate in prior_dates:
            if prior_texts.get(pdate, "").strip():
                target_text = prior_texts[pdate]
                break
    semantic_map = _get_semantic_similarities(symbol, target_text, pool_dates)
    use_hybrid = bool(semantic_map)

    # Step 3: combined score within pool, then pick top_k
    if use_hybrid:
        pool_scores = []
        for i in pool_indices:
            d = df.iloc[i]["date_str"]
            n = float(numeric_similarities[i])
            s = semantic_map.get(d)
            combined = _NUMERIC_WEIGHT * n + _SEMANTIC_WEIGHT * s if s is not None else n
            pool_scores.append((i, combined))
        pool_scores.sort(key=lambda x: -x[1])
        top_indices = [i for i, _ in pool_scores[:top_k]]
    else:
        top_indices = pool_indices[:top_k]

    # Get OHLC returns for context
    conn = get_conn()
    ohlc_rows = conn.execute(
        "SELECT date, close FROM ohlc WHERE symbol = ? ORDER BY date",
        (symbol,),
    ).fetchall()

    # Fetch news titles grouped by trade_date for similar days
    news_rows = conn.execute(
        """SELECT na.trade_date, nr.title, l1.sentiment
           FROM news_aligned na
           JOIN news_raw nr ON na.news_id = nr.id
           LEFT JOIN layer1_results l1 ON na.news_id = l1.news_id AND l1.symbol = ?
           WHERE na.symbol = ?
           ORDER BY na.trade_date, na.published_utc DESC""",
        (symbol, symbol),
    ).fetchall()
    conn.close()

    # Build lookup: date -> list of {title, sentiment}
    news_by_date: dict[str, list[dict]] = {}
    for r in news_rows:
        d = r["trade_date"]
        if d not in news_by_date:
            news_by_date[d] = []
        news_by_date[d].append({
            "title": (r["title"] or "")[:100],
            "sentiment": r["sentiment"],
        })

    close_by_date = {r["date"]: r["close"] for r in ohlc_rows}
    ohlc_dates = [r["date"] for r in ohlc_rows]

    # Build target day info
    target_date_str = df.loc[target_idx, "date_str"]
    target_day_news = _load_target_day_news_snapshot(symbol, date)
    target_features = {
        "sentiment_score": float(target_day_news["sentiment_score"]),
        "n_articles": int(target_day_news["n_articles"]),
        "n_relevant": int(target_day_news["n_relevant"]),
        "positive_ratio": float(target_day_news["positive_ratio"]),
        "negative_ratio": float(target_day_news["negative_ratio"]),
        "sentiment_momentum_3d": round(float(target_row["sentiment_momentum_3d"]), 4),
        "ret_1d": round(float(target_row["ret_1d"]), 4) if pd.notna(target_row["ret_1d"]) else None,
        "ret_5d": round(float(target_row["ret_5d"]), 4) if pd.notna(target_row["ret_5d"]) else None,
        "volatility_5d": round(float(target_row["volatility_5d"]), 4) if pd.notna(target_row["volatility_5d"]) else None,
        "ma5_vs_ma20": round(float(target_row["ma5_vs_ma20"]), 4) if pd.notna(target_row["ma5_vs_ma20"]) else None,
        "rsi_14": round(float(target_row["rsi_14"]), 4),
    }
    target_features["ret_t1_actual"] = _forward_return(close_by_date, ohlc_dates, target_date_str, 1)
    target_features["ret_t5_actual"] = _forward_return(close_by_date, ohlc_dates, target_date_str, 5)
    target_features["ret_t7_actual"] = _forward_return(close_by_date, ohlc_dates, target_date_str, 7)
    target_features["ret_t14_actual"] = _forward_return(close_by_date, ohlc_dates, target_date_str, 14)
    target_features["news"] = news_by_date.get(target_date_str, [])[:5]

    # Build similar days
    similar = []
    up_count_t1 = 0
    up_count_t5 = 0
    valid_t1 = 0
    valid_t5 = 0
    weighted_up_t1_num = 0.0
    weighted_up_t1_den = 0.0
    weighted_ret_t1_num = 0.0
    weighted_ret_t1_den = 0.0
    weighted_up_t5_num = 0.0
    weighted_up_t5_den = 0.0
    weighted_ret_t5_num = 0.0
    weighted_ret_t5_den = 0.0
    up_count_h = 0
    valid_h = 0
    weighted_up_h_num = 0.0
    weighted_up_h_den = 0.0
    weighted_ret_h_num = 0.0
    weighted_ret_h_den = 0.0

    # Build a score lookup for top_indices
    if use_hybrid:
        combined_scores = {i: s for i, s in pool_scores[:top_k]}
    else:
        combined_scores = {i: float(numeric_similarities[i]) for i in top_indices}

    for idx in top_indices:
        row = df.iloc[idx]
        d = row["date_str"]
        sim_score = combined_scores.get(idx, float(numeric_similarities[idx]))
        numeric_sim = float(numeric_similarities[idx])
        semantic_sim = semantic_map.get(d) if use_hybrid else None

        ret_t1 = _forward_return(close_by_date, ohlc_dates, d, 1)
        ret_t5 = _forward_return(close_by_date, ohlc_dates, d, 5)
        ret_h = _forward_return(close_by_date, ohlc_dates, d, horizon_days)

        if ret_t1 is not None:
            valid_t1 += 1
            if ret_t1 > 0:
                up_count_t1 += 1
            weight = max(sim_score, 0.0)
            weighted_up_t1_num += weight * (1.0 if ret_t1 > 0 else 0.0)
            weighted_up_t1_den += weight
            weighted_ret_t1_num += weight * ret_t1
            weighted_ret_t1_den += weight
        if ret_t5 is not None:
            valid_t5 += 1
            if ret_t5 > 0:
                up_count_t5 += 1
            weight = max(sim_score, 0.0)
            weighted_up_t5_num += weight * (1.0 if ret_t5 > 0 else 0.0)
            weighted_up_t5_den += weight
            weighted_ret_t5_num += weight * ret_t5
            weighted_ret_t5_den += weight
        if ret_h is not None:
            valid_h += 1
            if ret_h > 0:
                up_count_h += 1
            weight = max(sim_score, 0.0)
            weighted_up_h_num += weight * (1.0 if ret_h > 0 else 0.0)
            weighted_up_h_den += weight
            weighted_ret_h_num += weight * ret_h
            weighted_ret_h_den += weight

        similar.append({
            "date": d,
            "similarity": round(sim_score, 4),          # combined score (or numeric if no RAG)
            "numeric_sim": round(numeric_sim, 4),        # pure numeric cosine similarity
            "semantic_sim": round(semantic_sim, 4) if semantic_sim is not None else None,
            "sentiment_score": round(float(row["sentiment_score"]), 4),
            "n_relevant": int(row["n_relevant"]),
            "n_articles": int(row["n_articles"]),
            "ret_1d": round(float(row["ret_1d"]), 4) if pd.notna(row["ret_1d"]) else None,
            "ret_5d": round(float(row["ret_5d"]), 4) if pd.notna(row["ret_5d"]) else None,
            "rsi_14": round(float(row["rsi_14"]), 1),
            "volatility_5d": round(float(row["volatility_5d"]), 4) if pd.notna(row["volatility_5d"]) else None,
            "ma5_vs_ma20": round(float(row["ma5_vs_ma20"]), 4) if pd.notna(row["ma5_vs_ma20"]) else None,
            "ret_t1_after": round(ret_t1, 2) if ret_t1 is not None else None,
            "ret_t5_after": round(ret_t5, 2) if ret_t5 is not None else None,
            "ret_after_horizon": round(ret_h, 2) if ret_h is not None else None,
            "news": news_by_date.get(d, [])[:5],  # top 5 news for this day
        })

    # Aggregate stats
    avg_ret_t1 = np.mean([s["ret_t1_after"] for s in similar if s["ret_t1_after"] is not None]) if valid_t1 else None
    avg_ret_t5 = np.mean([s["ret_t5_after"] for s in similar if s["ret_t5_after"] is not None]) if valid_t5 else None
    avg_ret_h = np.mean([s["ret_after_horizon"] for s in similar if s["ret_after_horizon"] is not None]) if valid_h else None
    weighted_up_ratio_t1 = (weighted_up_t1_num / weighted_up_t1_den) if weighted_up_t1_den > 0 else None
    weighted_avg_ret_t1 = (weighted_ret_t1_num / weighted_ret_t1_den) if weighted_ret_t1_den > 0 else None
    weighted_up_ratio_t5 = (weighted_up_t5_num / weighted_up_t5_den) if weighted_up_t5_den > 0 else None
    weighted_avg_ret_t5 = (weighted_ret_t5_num / weighted_ret_t5_den) if weighted_ret_t5_den > 0 else None
    weighted_up_ratio_h = (weighted_up_h_num / weighted_up_h_den) if weighted_up_h_den > 0 else None
    weighted_avg_ret_h = (weighted_ret_h_num / weighted_ret_h_den) if weighted_ret_h_den > 0 else None

    return {
        "symbol": symbol,
        "target_date": target_date_str,
        "target_features": target_features,
        "similar_days": similar,
        "hybrid": use_hybrid,  # True = combined numeric+semantic, False = numeric only
        "stats": {
            "up_ratio_t1": round(up_count_t1 / valid_t1, 2) if valid_t1 else None,
            "up_ratio_t5": round(up_count_t5 / valid_t5, 2) if valid_t5 else None,
            "avg_ret_t1": round(float(avg_ret_t1), 2) if avg_ret_t1 is not None else None,
            "avg_ret_t5": round(float(avg_ret_t5), 2) if avg_ret_t5 is not None else None,
            "weighted_up_ratio_t1": round(float(weighted_up_ratio_t1), 2) if weighted_up_ratio_t1 is not None else None,
            "weighted_avg_ret_t1": round(float(weighted_avg_ret_t1), 2) if weighted_avg_ret_t1 is not None else None,
            "weighted_up_ratio_t5": round(float(weighted_up_ratio_t5), 2) if weighted_up_ratio_t5 is not None else None,
            "weighted_avg_ret_t5": round(float(weighted_avg_ret_t5), 2) if weighted_avg_ret_t5 is not None else None,
            "up_ratio_h": round(up_count_h / valid_h, 2) if valid_h else None,
            "avg_ret_h": round(float(avg_ret_h), 2) if avg_ret_h is not None else None,
            "weighted_up_ratio_h": round(float(weighted_up_ratio_h), 2) if weighted_up_ratio_h is not None else None,
            "weighted_avg_ret_h": round(float(weighted_avg_ret_h), 2) if weighted_avg_ret_h is not None else None,
            "horizon_days": horizon_days,
            "count": len(similar),
        },
    }


def find_similar_days(symbol: str, date: str, top_k: int = 10) -> dict:
    """Find days with the most similar single-day feature vectors to the target date."""
    return compute_similar_day_bundle(symbol, date, top_k=top_k, horizon_days=1)
