import logging
from typing import List, Optional
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel

import database
import config
import crawler

logger = logging.getLogger(__name__)
app = FastAPI(title="Reddit Crawler API", version="1.0")


@app.get("/posts/{ticker}")
def get_posts(ticker: str, days: int = 3, limit: int = 50):
    items = database.get_posts(ticker.upper(), days=days, limit=limit)
    return {"ticker": ticker.upper(), "count": len(items), "items": items}


@app.get("/posts")
def get_posts_multi(tickers: str, days: int = 3, limit: int = 20):
    result = {}
    for t in tickers.upper().split(","):
        t = t.strip()
        if t:
            result[t] = database.get_posts(t, days=days, limit=limit)
    return result


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


@app.post("/crawl")
def trigger_crawl(background_tasks: BackgroundTasks):
    background_tasks.add_task(crawler.crawl_all)
    return {"message": "Crawl triggered in background"}


@app.get("/health")
def health():
    watchlist = database.get_watchlist()
    return {
        "status": "ok",
        "watchlist_count": len(watchlist),
        "crawl_interval_minutes": config.CRAWL_INTERVAL,
        "retention_days": config.POST_RETENTION_DAYS,
    }
