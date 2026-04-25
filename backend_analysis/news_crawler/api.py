import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

import database
import config
import crawler

logger = logging.getLogger(__name__)
app = FastAPI(title="News Crawler API", version="1.0")


# ── News ──────────────────────────────────────────────────────────────────────

@app.get("/news/{ticker}")
def get_news(ticker: str, days: int = 3, limit: int = 50):
    """Get cached news for a ticker."""
    items = database.get_news(ticker.upper(), days=days, limit=limit)
    return {"ticker": ticker.upper(), "count": len(items), "items": items}


@app.get("/news")
def get_news_multi(tickers: str, days: int = 3, limit: int = 20):
    """Get news for multiple tickers (comma-separated)."""
    result = {}
    for t in tickers.upper().split(","):
        t = t.strip()
        if t:
            result[t] = database.get_news(t, days=days, limit=limit)
    return result


# ── Watchlist ─────────────────────────────────────────────────────────────────

@app.get("/watchlist")
def get_watchlist():
    return {"tickers": database.get_watchlist()}


class TickerList(BaseModel):
    tickers: List[str]


@app.post("/watchlist")
def add_tickers(body: TickerList):
    database.add_to_watchlist(body.tickers)
    return {"added": [t.upper() for t in body.tickers]}


@app.delete("/watchlist/{ticker}")
def remove_ticker(ticker: str):
    database.remove_from_watchlist(ticker)
    return {"removed": ticker.upper()}


# ── Manual trigger ────────────────────────────────────────────────────────────

@app.post("/crawl")
def trigger_crawl(background_tasks: BackgroundTasks, ticker: Optional[str] = None):
    """Manually trigger a crawl. If ticker specified, crawl just that one."""
    if ticker:
        background_tasks.add_task(crawler.crawl_ticker, ticker.upper())
        return {"message": f"Crawling {ticker.upper()}"}
    else:
        tickers = database.get_watchlist() or config.WATCHLIST
        background_tasks.add_task(crawler.crawl_all, tickers)
        return {"message": f"Crawling {len(tickers)} tickers in background"}


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    watchlist = database.get_watchlist()
    return {
        "status": "ok",
        "watchlist_count": len(watchlist),
        "crawl_interval_minutes": config.CRAWL_INTERVAL,
        "retention_days": config.NEWS_RETENTION_DAYS,
    }
