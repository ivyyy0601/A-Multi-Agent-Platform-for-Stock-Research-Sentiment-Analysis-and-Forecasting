"""Feature engineering for adanos-based model.

One row per (ticker, trading day).
Features: sentiment (today + rolling + delta + cross-platform) + technicals.
"""

import numpy as np
import pandas as pd
from backend.database import get_conn


PLATFORMS = ["reddit", "twitter", "news"]


def _load_platform_sentiment(ticker: str) -> pd.DataFrame:
    """Load platform_sentiment and pivot to wide format: one row per date."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT date, platform, buzz_score, sentiment_score,
                  bullish_pct, bearish_pct, mentions, source_count
           FROM platform_sentiment
           WHERE ticker = ?
           ORDER BY date""",
        (ticker,),
    ).fetchall()
    conn.close()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])

    # Pivot: one row per date, columns = platform_metric
    pivoted = df.pivot_table(
        index="date", columns="platform",
        values=["buzz_score", "sentiment_score", "bullish_pct", "bearish_pct", "mentions", "source_count"],
        aggfunc="first",
    )
    pivoted.columns = [f"{metric}_{plat}" for metric, plat in pivoted.columns]
    pivoted = pivoted.reset_index()
    return pivoted


def _load_ohlc(ticker: str) -> pd.DataFrame:
    conn = get_conn()
    rows = conn.execute(
        "SELECT date, open, high, low, close, volume FROM ohlc WHERE symbol = ? ORDER BY date",
        (ticker,),
    ).fetchall()
    conn.close()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df


def build_features(ticker: str) -> pd.DataFrame:
    """Build full feature matrix. Returns empty DataFrame if insufficient data."""
    ohlc = _load_ohlc(ticker)
    sent = _load_platform_sentiment(ticker)

    if ohlc.empty or len(ohlc) < 20:
        return pd.DataFrame()

    # Merge on date
    df = ohlc.merge(sent, on="date", how="left")
    df = df.sort_values("date").reset_index(drop=True)

    close = df["close"]

    # ── TECHNICAL FEATURES (computed on full OHLC history first) ─────────────
    df["ret_1d"]  = close.pct_change(1).shift(1)
    df["ret_3d"]  = close.pct_change(3).shift(1)
    df["ret_5d"]  = close.pct_change(5).shift(1)
    df["volatility_5d"]  = close.pct_change().rolling(5).std().shift(1)
    avg_vol_5 = df["volume"].rolling(5).mean().shift(1)
    df["volume_ratio_5d"] = df["volume"].shift(1) / avg_vol_5.clip(lower=1)
    df["gap"] = (df["open"] / close.shift(1) - 1).shift(1)
    ma5  = close.rolling(5).mean().shift(1)
    ma20 = close.rolling(20).mean().shift(1)
    df["ma5_vs_ma20"] = (ma5 / ma20.clip(lower=0.01) - 1)
    for period in [5, 14]:
        delta = close.diff().shift(1)
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss.clip(lower=1e-10)
        df[f"rsi_{period}"] = 100 - 100 / (1 + rs)
    day_range = (df["high"] - df["low"]).shift(1).clip(lower=1e-6)
    df["close_position"] = ((close.shift(1) - df["low"].shift(1)) / day_range)
    df["day_of_week"] = df["date"].dt.dayofweek
    df["target_t1"] = close.shift(-1) / close - 1  # next day return (e.g. +0.012 or -0.008)

    # Forward-fill sentiment (昨天的情绪今天还有效), then fill remaining with 0
    sent_cols = [c for c in df.columns if any(c.endswith(f"_{p}") for p in PLATFORMS)]
    df[sent_cols] = df[sent_cols].ffill().fillna(0)

    # Only keep rows where we have at least some sentiment data (last 90 days)
    has_sentiment = df[sent_cols].any(axis=1)
    first_sentiment_idx = has_sentiment.idxmax() if has_sentiment.any() else len(df)
    df = df.iloc[first_sentiment_idx:].reset_index(drop=True)

    # Redefine close after slice
    close = df["close"]

    # ── TODAY'S SENTIMENT (per platform) ─────────────────────────────────────
    #
    # Raw buzz is heavy-tailed and can explode after z-scoring, especially when
    # several highly correlated buzz features all move together. Compress buzz
    # with log1p before rolling features, then cap the derived spike signal.
    for p in PLATFORMS:
        df[f"{p}_sentiment"] = df.get(f"sentiment_score_{p}", pd.Series(0, index=df.index))
        raw_buzz = df.get(f"buzz_score_{p}", pd.Series(0, index=df.index)).clip(lower=0)
        df[f"{p}_buzz_raw"]  = raw_buzz
        df[f"{p}_buzz"]      = np.log1p(raw_buzz)
        df[f"{p}_bullish"]   = df.get(f"bullish_pct_{p}",     pd.Series(0, index=df.index))
        df[f"{p}_bearish"]   = df.get(f"bearish_pct_{p}",     pd.Series(0, index=df.index))
        df[f"{p}_mentions"]  = df.get(f"mentions_{p}",        pd.Series(0, index=df.index))

    # ── ROLLING AVERAGES (3d / 5d / 10d) ─────────────────────────────────────
    for p in PLATFORMS:
        for w in [3, 5, 10]:
            df[f"{p}_sentiment_{w}d"] = df[f"{p}_sentiment"].rolling(w, min_periods=1).mean()
            df[f"{p}_buzz_{w}d"]      = df[f"{p}_buzz"].rolling(w, min_periods=1).mean()

    # ── DELTA (today vs yesterday) ────────────────────────────────────────────
    for p in PLATFORMS:
        df[f"{p}_sentiment_delta"] = df[f"{p}_sentiment"].diff(1)

    # ── SENTIMENT MOMENTUM (3d mean - 10d mean) ───────────────────────────────
    for p in PLATFORMS:
        df[f"{p}_momentum"] = df[f"{p}_sentiment_3d"] - df[f"{p}_sentiment_10d"]

    # ── BUZZ SPIKE (today / 5d avg) ───────────────────────────────────────────
    for p in PLATFORMS:
        raw_avg5 = df[f"{p}_buzz_raw"].rolling(5, min_periods=1).mean().clip(lower=1.0)
        raw_spike = (df[f"{p}_buzz_raw"] / raw_avg5).clip(lower=0, upper=5)
        df[f"{p}_buzz_spike"] = np.log1p(raw_spike)

    # ── CROSS-PLATFORM SIGNALS ────────────────────────────────────────────────
    # Sentiment agreement: all 3 platforms same direction
    def _sign(s): return (s > 0.05).astype(int) - (s < -0.05).astype(int)
    r_sign = _sign(df["reddit_sentiment"])
    t_sign = _sign(df["twitter_sentiment"])
    n_sign = _sign(df["news_sentiment"])
    df["platform_agreement"] = ((r_sign == t_sign) & (t_sign == n_sign) & (r_sign != 0)).astype(int)

    # Reddit vs News divergence (散户 vs 媒体)
    df["reddit_vs_news_diff"] = df["reddit_sentiment"] - df["news_sentiment"]

    # Average sentiment across platforms
    df["avg_sentiment"] = (df["reddit_sentiment"] + df["twitter_sentiment"] + df["news_sentiment"]) / 3
    df["avg_bullish"]   = (df["reddit_bullish"]   + df["twitter_bullish"]   + df["news_bullish"])   / 3

    # Drop rows with insufficient history
    df = df.dropna(subset=["ret_5d", "rsi_14", "close_position"]).reset_index(drop=True)

    return df


FEATURE_COLS = [
    # Today's sentiment
    "reddit_sentiment", "reddit_buzz", "reddit_bullish", "reddit_bearish",
    "twitter_sentiment", "twitter_buzz", "twitter_bullish", "twitter_bearish",
    "news_sentiment", "news_buzz", "news_bullish", "news_bearish",
    # Rolling 3d/5d/10d
    "reddit_sentiment_3d", "reddit_sentiment_5d", "reddit_sentiment_10d",
    "twitter_sentiment_3d", "twitter_sentiment_5d", "twitter_sentiment_10d",
    "news_sentiment_3d", "news_sentiment_5d", "news_sentiment_10d",
    "reddit_buzz_3d", "reddit_buzz_5d",
    "news_buzz_3d", "news_buzz_5d",
    # Delta
    "reddit_sentiment_delta", "twitter_sentiment_delta", "news_sentiment_delta",
    # Momentum
    "reddit_momentum", "twitter_momentum", "news_momentum",
    # Buzz spike
    "reddit_buzz_spike", "twitter_buzz_spike", "news_buzz_spike",
    # Cross-platform
    "platform_agreement", "reddit_vs_news_diff", "avg_sentiment", "avg_bullish",
    # Technicals
    "ret_1d", "ret_3d", "ret_5d",
    "volatility_5d", "volume_ratio_5d",
    "gap", "ma5_vs_ma20", "rsi_5", "rsi_14",
    "close_position", "day_of_week",
]
