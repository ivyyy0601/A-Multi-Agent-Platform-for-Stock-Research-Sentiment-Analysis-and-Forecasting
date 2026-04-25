"""Adanos API routes — sentiment data, posts, forecast."""

from fastapi import APIRouter, HTTPException, Query
from backend.database import get_conn
from backend.adanos.client import (
    get_all_platforms, get_reddit_explain, get_news_explain, TICKERS
)
from backend.adanos.forecast_store import load_latest_forecast, get_latest_feature_dates
from backend.adanos.inference import generate_forecast

router = APIRouter()


@router.get("/tickers")
def list_tickers():
    return {"tickers": TICKERS}


@router.get("/{ticker}/forecast")
def forecast(ticker: str, date: str | None = Query(None)):
    ticker = ticker.upper()
    result = load_latest_forecast(ticker) if not date else None
    if result:
        return result

    latest_dates = get_latest_feature_dates(ticker)
    if not latest_dates["max_ohlc_date"]:
        raise HTTPException(status_code=404, detail=f"No OHLC data for {ticker}")
    if not latest_dates["max_sentiment_date"]:
        raise HTTPException(status_code=404, detail=f"No sentiment data for {ticker}")

    result = generate_forecast(ticker, ref_date=date)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{ticker}/sentiment")
def sentiment_history(ticker: str, days: int = 90):
    """Return daily sentiment history for all 3 platforms — used for chart overlay."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT date, platform, buzz_score, sentiment_score,
                  bullish_pct, bearish_pct, mentions
           FROM platform_sentiment
           WHERE ticker = ?
           ORDER BY date DESC
           LIMIT ?""",
        (ticker.upper(), days * 3),
    ).fetchall()
    conn.close()

    # Group by date
    by_date: dict = {}
    for r in rows:
        d = r["date"]
        if d not in by_date:
            by_date[d] = {"date": d}
        p = r["platform"]
        by_date[d][p] = {
            "buzz":      r["buzz_score"],
            "sentiment": r["sentiment_score"],
            "bullish":   r["bullish_pct"],
            "bearish":   r["bearish_pct"],
            "mentions":  r["mentions"],
        }

    result = sorted(by_date.values(), key=lambda x: x["date"])
    return result


@router.get("/{ticker}/posts")
def get_posts(ticker: str, platform: str = "all"):
    """Return latest top posts/tweets/articles from adanos API (live)."""
    ticker = ticker.upper()
    days = 7

    data = get_all_platforms(ticker, days=days)

    posts = []

    # Reddit top mentions
    if platform in ("all", "reddit") and data.get("reddit"):
        for m in (data["reddit"].get("top_mentions") or [])[:10]:
            posts.append({
                "platform":  "reddit",
                "text":      m.get("text_snippet", ""),
                "sentiment": m.get("sentiment_label", "neutral"),
                "score":     m.get("sentiment_score"),
                "source":    m.get("source", "Reddit"),
                "created_at": m.get("created_utc"),
                "likes":     None,
                "retweets":  None,
                "views":     None,
                "author":    None,
            })

    # Twitter top tweets
    if platform in ("all", "twitter") and data.get("twitter"):
        for t in (data["twitter"].get("top_tweets") or [])[:10]:
            posts.append({
                "platform":  "twitter",
                "text":      t.get("text", t.get("text_snippet", "")),
                "sentiment": None,
                "score":     None,
                "source":    "Twitter/X",
                "created_at": t.get("created_at"),
                "likes":     t.get("likes"),
                "retweets":  t.get("retweets"),
                "views":     t.get("views"),
                "author":    t.get("author"),
            })

    # News top mentions
    if platform in ("all", "news") and data.get("news"):
        for m in (data["news"].get("top_mentions") or [])[:10]:
            posts.append({
                "platform":  "news",
                "text":      m.get("text_snippet", ""),
                "sentiment": m.get("sentiment_label", "neutral"),
                "score":     m.get("sentiment_score"),
                "source":    m.get("source", "News"),
                "created_at": m.get("created_utc"),
                "likes":     None,
                "retweets":  None,
                "views":     None,
                "author":    None,
            })

    return {"ticker": ticker, "posts": posts}


@router.get("/{ticker}/day/{date}")
def day_detail(ticker: str, date: str):
    """Return posts from all platforms for a specific ticker + date."""
    ticker = ticker.upper()
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, platform, text, sentiment_label, sentiment_score,
                  upvotes, likes, retweets, subreddit, author, source, created_utc
           FROM platform_posts
           WHERE ticker = ? AND date = ?
           ORDER BY platform, upvotes DESC NULLS LAST, likes DESC NULLS LAST
           LIMIT 60""",
        (ticker, date),
    ).fetchall()
    conn.close()
    return {
        "ticker": ticker,
        "date": date,
        "posts": [
            {
                "id":              r["id"],
                "platform":        r["platform"],
                "text":            r["text"],
                "sentiment_label": r["sentiment_label"],
                "sentiment_score": r["sentiment_score"],
                "upvotes":         r["upvotes"],
                "likes":           r["likes"],
                "retweets":        r["retweets"],
                "subreddit":       r["subreddit"],
                "author":          r["author"],
                "source":          r["source"],
                "created_utc":     r["created_utc"],
            }
            for r in rows
        ],
    }


@router.get("/{ticker}/explain")
def explain(ticker: str):
    """AI explanation of why stock is trending (from adanos)."""
    ticker = ticker.upper()
    reddit_exp = get_reddit_explain(ticker)
    news_exp   = get_news_explain(ticker)
    return {
        "ticker":  ticker,
        "reddit":  reddit_exp,
        "news":    news_exp,
    }
