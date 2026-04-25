import logging
import time
from typing import List

import database
import config
from clients import reddit_search
from ticker_matcher import find_tickers_in_text, TICKER_ALIASES

logger = logging.getLogger(__name__)

# Ticker-specific subreddits (posts here are directly mapped to the ticker)
TICKER_SUBREDDITS = {
    "AAPL":  ["apple", "AAPL"],
    "MSFT":  ["microsoft", "MSFT"],
    "GOOGL": ["google", "alphabet"],
    "AMZN":  ["amazon", "AMZN"],
    "TSLA":  ["teslamotors", "TSLA", "teslainvestorsclub"],
    "META":  ["facebook"],
    "NVDA":  ["nvidia", "NVDA"],
    "INTC":  ["intel", "INTC"],
    "AVGO":  ["broadcom"],
    "TXN":   ["TexasInstruments"],
    "ASML":  ["ASML"],
    "NFLX":  ["netflix"],
    "COIN":  ["CoinBase"],
}


def crawl_main_subreddits(backfill: bool = False) -> int:
    """Fetch latest posts from main subreddits and match to tickers."""
    watchlist = set(database.get_watchlist() or config.WATCHLIST)
    limit = 100 if backfill else 50
    total = 0

    for subreddit in config.MAIN_SUBREDDITS:
        try:
            posts = reddit_search.fetch_subreddit_new(subreddit, limit=limit)
            to_save = []
            for post in posts:
                combined = f"{post['title']} {post.get('text') or ''}"
                tickers = [t for t in find_tickers_in_text(combined) if t in watchlist]
                for ticker in tickers:
                    item = dict(post)
                    item["ticker"] = ticker
                    # unique id per ticker+post combo
                    import hashlib
                    item["id"] = hashlib.md5(f"{post['id']}_{ticker}".encode()).hexdigest()
                    to_save.append(item)
            database.upsert_posts(to_save)
            total += len(to_save)
            time.sleep(0.5)
        except Exception as e:
            logger.warning("Error crawling r/%s: %s", subreddit, e)

    return total


def crawl_ticker_subreddits(backfill: bool = False) -> int:
    """Fetch posts from ticker-specific subreddits."""
    watchlist = set(database.get_watchlist() or config.WATCHLIST)
    limit = 100 if backfill else 50
    total = 0

    for ticker, subreddits in TICKER_SUBREDDITS.items():
        if ticker not in watchlist:
            continue
        for subreddit in subreddits:
            try:
                posts = reddit_search.fetch_subreddit_new(subreddit, limit=limit)
                for post in posts:
                    post["ticker"] = ticker
                    import hashlib
                    post["id"] = hashlib.md5(f"{post['id']}_{ticker}".encode()).hexdigest()
                database.upsert_posts(posts)
                total += len(posts)
                time.sleep(0.5)
            except Exception as e:
                logger.warning("Error crawling r/%s (ticker %s): %s", subreddit, ticker, e)

    return total


def crawl_all(backfill: bool = False):
    """Full crawl: main subreddits + ticker subreddits."""
    mode = "backfill" if backfill else "update"
    logger.info("Starting %s crawl", mode)

    n1 = crawl_main_subreddits(backfill=backfill)
    n2 = crawl_ticker_subreddits(backfill=backfill)

    database.cleanup_old_posts()
    logger.info("Crawl complete: %d posts from main subreddits, %d from ticker subreddits", n1, n2)
