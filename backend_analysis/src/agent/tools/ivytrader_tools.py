# -*- coding: utf-8 -*-
"""
IvyTrader internal tools — exposes main backend APIs as agent-callable tools.

Tools:
- get_iv_forecast:      ML model prediction (1D/7D/14D) from pokieticker.db
- get_iv_news:          Recent relevant news with sentiment + actual returns
- get_iv_similar_days:  Historical similar market days for a symbol
- get_iv_library:       Search historical research reports
- get_iv_social:        Social sentiment signal (Reddit/Twitter) via adanos
"""

import logging
import os
from typing import Optional

import requests

from src.agent.tools.registry import ToolParameter, ToolDefinition

logger = logging.getLogger(__name__)

# Main backend base URL (port 8000)
_BASE = os.environ.get("IVYTRADER_API_URL", "http://127.0.0.1:8000")
_TIMEOUT = 15


def _get(path: str, params: dict | None = None) -> dict | list:
    """GET request to main backend."""
    resp = requests.get(f"{_BASE}{path}", params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, body: dict) -> dict | list:
    """POST request to main backend."""
    resp = requests.post(f"{_BASE}{path}", json=body, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ── Tool 1: ML Forecast ───────────────────────────────────────────────────────

def _handle_get_iv_forecast(symbol: str, horizon: str = "7") -> dict:
    """Get ML forecast for a US stock via /api/predict/{symbol}/forecast."""
    try:
        window = int(horizon)  # 1, 7, or 14
        data = _get(f"/api/predict/{symbol.upper()}/forecast", params={"window": window})
        if not data:
            return {"error": f"No forecast available for {symbol}"}

        # Extract the specific horizon prediction (t1 / t7 / t14)
        horizon_key = f"t{window}"
        prediction = data.get("prediction", {})
        pred = prediction.get(horizon_key, {})

        # Similar-period stats
        stats = data.get("similar_stats", {})
        news = data.get("news_summary", {})

        return {
            "symbol": symbol.upper(),
            "horizon_days": window,
            "forecast_date": data.get("forecast_date"),
            "direction": pred.get("direction"),          # "up" | "down"
            "confidence": pred.get("confidence"),        # 0.0 – 1.0
            "model_type": pred.get("model_type"),        # "XGB" | "RF" | "LR"
            "model_accuracy": pred.get("model_accuracy"),
            "top_drivers": pred.get("top_drivers", [])[:4],  # top 4 feature drivers
            "similar_periods": {
                "count": stats.get("count"),
                "up_ratio": stats.get("up_ratio"),       # % of similar periods that went up
                "avg_ret_pct": stats.get("avg_ret"),     # average return after similar setups
            },
            "news_context": {
                "positive": news.get("positive"),
                "negative": news.get("negative"),
                "sentiment_ratio": news.get("sentiment_ratio"),
            },
            "conclusion": data.get("conclusion", ""),
            "note": "ML prediction based on news sentiment + technical features. Not financial advice.",
        }
    except Exception as e:
        return {"error": f"Forecast fetch failed: {e}"}


get_iv_forecast_tool = ToolDefinition(
    name="get_iv_forecast",
    description=(
        "Get IvyTrader's ML model prediction for a US stock. "
        "Returns direction (up/down), confidence score, and similar historical days. "
        "Use this when asked about stock outlook or price direction."
    ),
    parameters=[
        ToolParameter(
            name="symbol",
            type="string",
            description="US stock ticker symbol (e.g. AAPL, NVDA, TSLA)",
            required=True,
        ),
        ToolParameter(
            name="horizon",
            type="string",
            description="Forecast horizon in days: '1' (next day), '7' (next week), '14' (next 2 weeks)",
            required=False,
            default="1",
            enum=["1", "7", "14"],
        ),
    ],
    handler=_handle_get_iv_forecast,
    category="analysis",
)


# ── Tool 2: Recent News with Sentiment + Returns ──────────────────────────────

def _handle_get_iv_news(symbol: str, date: Optional[str] = None, limit: int = 15) -> dict:
    """Get recent relevant news with Layer1 sentiment analysis and actual price returns."""
    try:
        params: dict = {}
        if date:
            params["date"] = date

        data = _get(f"/api/news/{symbol.upper()}", params=params)
        if not data:
            return {"error": f"No news found for {symbol}"}

        articles = data if isinstance(data, list) else data.get("articles", [])

        # Filter to relevant only, limit count
        relevant = [a for a in articles if a.get("relevance") == "relevant"]
        if not relevant:
            relevant = articles  # fallback: return all if none marked relevant
        relevant = relevant[:limit]

        result = []
        for a in relevant:
            result.append({
                "date": a.get("trade_date") or a.get("published_utc", "")[:10],
                "title": a.get("title", ""),
                "publisher": a.get("publisher", ""),
                "sentiment": a.get("sentiment"),          # positive / negative / neutral
                "key_discussion": a.get("key_discussion", ""),
                "reason_growth": a.get("reason_growth", ""),
                "reason_decrease": a.get("reason_decrease", ""),
                "ret_t1": a.get("ret_t1"),   # actual next-day return
                "ret_t3": a.get("ret_t3"),   # actual 3-day return
                "url": a.get("article_url", ""),
            })

        return {
            "symbol": symbol.upper(),
            "total_articles": len(result),
            "articles": result,
        }
    except Exception as e:
        return {"error": f"News fetch failed: {e}"}


get_iv_news_tool = ToolDefinition(
    name="get_iv_news",
    description=(
        "Get recent news for a US stock from IvyTrader's database. "
        "Includes AI-analyzed sentiment, key discussion points, and actual historical price returns "
        "after each news event (ret_t1 = next day, ret_t3 = 3 days later). "
        "Use this to understand what's driving a stock and how similar news affected price historically."
    ),
    parameters=[
        ToolParameter(
            name="symbol",
            type="string",
            description="US stock ticker symbol (e.g. AAPL, NVDA, TSLA)",
            required=True,
        ),
        ToolParameter(
            name="date",
            type="string",
            description="Specific trade date YYYY-MM-DD to fetch news for. If omitted, returns most recent news.",
            required=False,
            default="",
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="Maximum number of articles to return (default 15)",
            required=False,
            default=15,
        ),
    ],
    handler=_handle_get_iv_news,
    category="data",
)


# ── Tool 3: Similar Historical Days ──────────────────────────────────────────

def _handle_get_iv_similar_days(symbol: str, top_k: int = 5) -> dict:
    """Find historical days with similar news+technical pattern for a stock."""
    try:
        # Use the most recent available forecast date as reference
        forecast_data = _get(f"/api/predict/{symbol.upper()}/forecast", params={"window": 7})
        ref_date = forecast_data.get("forecast_date") if forecast_data else None
        if not ref_date:
            return {"error": f"Could not determine reference date for {symbol}"}

        data = _get(
            f"/api/predict/{symbol.upper()}/similar-days",
            params={"date": ref_date, "top_k": top_k},
        )
        if not data:
            return {"error": f"No similar days found for {symbol}"}

        similar = data.get("similar_days", [])
        # Summarise key return fields for the agent
        summary = []
        for d in similar[:top_k]:
            summary.append({
                "date": d.get("date"),
                "similarity": d.get("similarity"),
                "ret_1d_pct": round(d.get("ret_1d", 0) * 100, 2) if d.get("ret_1d") is not None else None,
                "ret_5d_pct": round(d.get("ret_5d", 0) * 100, 2) if d.get("ret_5d") is not None else None,
                "ret_t1_pct": round(d.get("ret_t1", 0) * 100, 2) if d.get("ret_t1") is not None else None,
                "sentiment_score": d.get("sentiment_score"),
            })

        return {
            "symbol": symbol.upper(),
            "reference_date": ref_date,
            "similar_days": summary,
            "note": "Historical dates with similar news/technical patterns. ret_t1_pct = next-day return after that date.",
        }
    except Exception as e:
        return {"error": f"Similar days fetch failed: {e}"}


get_iv_similar_days_tool = ToolDefinition(
    name="get_iv_similar_days",
    description=(
        "Find historical dates where a US stock had similar news sentiment patterns to today. "
        "Returns past dates and what happened to the stock price afterwards. "
        "Use this for historical context and pattern-based reasoning."
    ),
    parameters=[
        ToolParameter(
            name="symbol",
            type="string",
            description="US stock ticker symbol (e.g. AAPL, NVDA, TSLA)",
            required=True,
        ),
        ToolParameter(
            name="top_k",
            type="integer",
            description="Number of similar days to return (default 5)",
            required=False,
            default=5,
        ),
    ],
    handler=_handle_get_iv_similar_days,
    category="analysis",
)


# ── Tool 4: Library — Search Historical Research Reports ─────────────────────

def _handle_get_iv_library(query: str, symbol: Optional[str] = None, limit: int = 5) -> dict:
    """Search historical research reports in IvyTrader library."""
    try:
        params: dict = {"q": query, "limit": limit}
        if symbol:
            params["symbol"] = symbol.upper()

        data = _get("/api/library/reports", params=params)
        if not data:
            return {"error": "No reports found matching query"}

        reports = data if isinstance(data, list) else data.get("reports", [])
        result = []
        for r in reports[:limit]:
            result.append({
                "id": r.get("id"),
                "title": r.get("title", ""),
                "symbol": r.get("symbol", ""),
                "created_at": r.get("created_at", "")[:10],
                "summary": (r.get("content") or r.get("summary") or "")[:500],
            })

        return {
            "query": query,
            "total": len(result),
            "reports": result,
        }
    except Exception as e:
        return {"error": f"Library search failed: {e}"}


get_iv_library_tool = ToolDefinition(
    name="get_iv_library",
    description=(
        "Search IvyTrader's historical research report library. "
        "Returns past analysis reports, memos, and notes for US stocks. "
        "Use this to retrieve previous analysis and avoid repeating work, "
        "or to find historical context on a company or theme."
    ),
    parameters=[
        ToolParameter(
            name="query",
            type="string",
            description="Search query (e.g. 'NVDA earnings', 'AI capex', 'TSLA delivery')",
            required=True,
        ),
        ToolParameter(
            name="symbol",
            type="string",
            description="Filter by stock ticker (optional)",
            required=False,
            default="",
        ),
        ToolParameter(
            name="limit",
            type="integer",
            description="Number of reports to return (default 5)",
            required=False,
            default=5,
        ),
    ],
    handler=_handle_get_iv_library,
    category="analysis",
)


# ── Tool 5: Social Sentiment (Adanos) ────────────────────────────────────────

def _handle_get_iv_social(symbol: str) -> dict:
    """Get social media sentiment signal for a US stock."""
    try:
        data = _get(f"/api/adanos/forecast/{symbol.upper()}")
        if not data:
            return {"error": f"No social signal for {symbol}"}

        return {
            "symbol": symbol.upper(),
            "direction": data.get("direction"),       # "up" | "down"
            "confidence": data.get("confidence"),
            "reddit_sentiment": data.get("reddit_sentiment"),
            "news_sentiment": data.get("news_sentiment"),
            "forecast_date": data.get("forecast_date"),
            "note": "Based on Reddit/news sentiment model (Adanos).",
        }
    except Exception as e:
        return {"error": f"Social signal fetch failed: {e}"}


get_iv_social_tool = ToolDefinition(
    name="get_iv_social",
    description=(
        "Get IvyTrader's social sentiment signal for a US stock. "
        "Based on Reddit and news sentiment analysis (Adanos model). "
        "Use this to understand retail investor sentiment alongside ML forecast."
    ),
    parameters=[
        ToolParameter(
            name="symbol",
            type="string",
            description="US stock ticker symbol (e.g. AAPL, NVDA, TSLA)",
            required=True,
        ),
    ],
    handler=_handle_get_iv_social,
    category="data",
)


# ── Export all tools ──────────────────────────────────────────────────────────

IVYTRADER_TOOLS = [
    get_iv_forecast_tool,
    get_iv_news_tool,
    get_iv_similar_days_tool,
    get_iv_library_tool,
    get_iv_social_tool,
]
