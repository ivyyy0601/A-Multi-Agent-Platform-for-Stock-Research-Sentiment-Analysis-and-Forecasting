import logging
import time
from typing import List

import database
import config
from clients import yahoo_finance, nasdaq, google_news

logger = logging.getLogger(__name__)

# 公司名映射（Google News 搜索用，提升准确度）
TICKER_TO_NAME = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "GOOGL": "Google Alphabet",
    "AMZN": "Amazon", "META": "Meta Facebook", "TSLA": "Tesla", "AVGO": "Broadcom",
    "AMD": "AMD Advanced Micro", "MU": "Micron", "TSM": "TSMC Taiwan Semiconductor",
    "ASML": "ASML", "INTC": "Intel", "QCOM": "Qualcomm", "AMAT": "Applied Materials",
    "LRCX": "Lam Research", "ADI": "Analog Devices", "NXPI": "NXP Semiconductors",
    "ARM": "ARM Holdings", "TXN": "Texas Instruments", "ORCL": "Oracle",
    "CRM": "Salesforce", "NOW": "ServiceNow", "ADBE": "Adobe", "PLTR": "Palantir",
    "PANW": "Palo Alto Networks", "CRWD": "CrowdStrike", "SNOW": "Snowflake",
    "MDB": "MongoDB", "SHOP": "Shopify", "JPM": "JPMorgan Chase", "BAC": "Bank of America",
    "GS": "Goldman Sachs", "MS": "Morgan Stanley", "WFC": "Wells Fargo", "C": "Citigroup",
    "V": "Visa", "MA": "Mastercard", "PYPL": "PayPal", "AXP": "American Express",
    "BRK.B": "Berkshire Hathaway", "SQ": "Block Square", "SOFI": "SoFi",
    "BLK": "BlackRock", "CME": "CME Group", "ICE": "Intercontinental Exchange",
    "SCHW": "Charles Schwab", "LLY": "Eli Lilly", "NVO": "Novo Nordisk",
    "JNJ": "Johnson Johnson", "PFE": "Pfizer", "MRK": "Merck", "ABBV": "AbbVie",
    "BMY": "Bristol Myers Squibb", "UNH": "UnitedHealth", "ISRG": "Intuitive Surgical",
    "TMO": "Thermo Fisher", "DHR": "Danaher", "MDT": "Medtronic", "ABT": "Abbott",
    "WMT": "Walmart", "COST": "Costco", "HD": "Home Depot", "TGT": "Target",
    "LOW": "Lowes", "NKE": "Nike", "MCD": "McDonald's", "KO": "Coca-Cola",
    "PEP": "PepsiCo", "SBUX": "Starbucks", "LULU": "Lululemon", "BKNG": "Booking Holdings",
    "ABNB": "Airbnb", "UBER": "Uber", "DASH": "DoorDash", "XOM": "ExxonMobil",
    "CVX": "Chevron", "COP": "ConocoPhillips", "SLB": "Schlumberger",
    "OXY": "Occidental Petroleum", "GE": "GE Aerospace", "CAT": "Caterpillar",
    "BA": "Boeing", "LMT": "Lockheed Martin", "HON": "Honeywell", "DE": "John Deere",
    "UPS": "United Parcel Service", "FDX": "FedEx", "F": "Ford", "GM": "General Motors",
    "VZ": "Verizon", "T": "AT&T", "NFLX": "Netflix", "DIS": "Disney",
    "CMCSA": "Comcast", "AMT": "American Tower", "PLD": "Prologis", "EQIX": "Equinix",
}


def crawl_ticker(ticker: str, backfill: bool = False) -> int:
    """Crawl news for one ticker from all sources.
    backfill=True fetches larger limits to cover the full 3-day window on first run.
    """
    company_name = TICKER_TO_NAME.get(ticker, "")
    all_items = []

    if backfill:
        yf_limit, nq_limit, gn_limit = 100, 50, 50
    else:
        yf_limit, nq_limit, gn_limit = 30, 20, 20

    # Yahoo Finance
    items = yahoo_finance.fetch(ticker, limit=yf_limit)
    all_items.extend(items)
    time.sleep(0.3)

    # Nasdaq
    items = nasdaq.fetch(ticker, limit=nq_limit)
    all_items.extend(items)
    time.sleep(0.3)

    # Google News
    items = google_news.fetch(ticker, company_name=company_name, limit=gn_limit)
    all_items.extend(items)
    time.sleep(0.3)

    database.upsert_news(all_items)
    return len(all_items)


def crawl_all(tickers: List[str], backfill: bool = False):
    """Crawl all tickers. Logs progress. Cleans up old news after each run."""
    total = len(tickers)
    mode = "backfill" if backfill else "update"
    logger.info("Starting %s crawl for %d tickers", mode, total)
    saved = 0
    for i, ticker in enumerate(tickers, 1):
        try:
            count = crawl_ticker(ticker, backfill=backfill)
            saved += count
            if i % 20 == 0:
                logger.info("Progress: %d/%d tickers done", i, total)
        except Exception as e:
            logger.warning("Error crawling %s: %s", ticker, e)
    # Delete news older than NEWS_RETENTION_DAYS after every run
    database.cleanup_old_news()
    logger.info("Crawl complete: %d tickers, %d items fetched", total, saved)
