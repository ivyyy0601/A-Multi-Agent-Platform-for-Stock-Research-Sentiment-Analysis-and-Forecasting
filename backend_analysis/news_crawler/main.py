import logging
import threading
import time
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler

import config
import database
import crawler
from api import app

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def scheduled_crawl(backfill: bool = False):
    tickers = database.get_watchlist()
    if not tickers:
        tickers = config.WATCHLIST
    crawler.crawl_all(tickers, backfill=backfill)


def main():
    # Init DB
    database.init_db()

    # Seed watchlist from .env if empty
    if not database.get_watchlist() and config.WATCHLIST:
        database.add_to_watchlist(config.WATCHLIST)
        logger.info("Seeded watchlist with %d tickers from .env", len(config.WATCHLIST))

    # First run: backfill mode (larger limits to cover full 3-day window)
    t = threading.Thread(target=scheduled_crawl, kwargs={"backfill": True}, daemon=True)
    t.start()

    # Schedule recurring crawl
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        scheduled_crawl,
        "interval",
        minutes=config.CRAWL_INTERVAL,
        id="news_crawl",
    )
    scheduler.start()
    logger.info("Scheduler started: crawling every %d minutes", config.CRAWL_INTERVAL)

    # Start API server
    logger.info("API server starting at http://%s:%d", config.API_HOST, config.API_PORT)
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT, log_level="warning")


if __name__ == "__main__":
    main()
