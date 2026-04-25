import hashlib
import html
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Dict

import requests

logger = logging.getLogger(__name__)

RSS_URL = "https://news.google.com/rss/search"


def fetch(ticker: str, company_name: str = "", limit: int = 20) -> List[Dict]:
    ticker = ticker.upper().strip()
    # Use company name if available for better results, else just ticker
    query = f"{company_name} {ticker} stock" if company_name else f"{ticker} stock"
    try:
        resp = requests.get(
            RSS_URL,
            params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
            headers={"User-Agent": "Mozilla/5.0 (compatible; news-crawler/1.0)"},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        channel = root.find("channel")
        if channel is None:
            return []
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        results = []
        seen = set()
        for item in channel.findall("item")[:limit]:
            title = html.unescape((item.findtext("title") or "").strip())
            link = (item.findtext("link") or "").strip()
            if not title or link in seen:
                continue
            seen.add(link)
            pub = item.findtext("pubDate") or ""
            try:
                published_at = parsedate_to_datetime(pub).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            except Exception:
                published_at = now
            uid = hashlib.md5(f"gn_{ticker}_{link or title}".encode()).hexdigest()
            results.append({
                "id": uid,
                "ticker": ticker,
                "title": title,
                "summary": None,
                "url": link,
                "source": "Google News",
                "published_at": published_at,
                "fetched_at": now,
            })
        return results
    except Exception as e:
        logger.debug("[Google] %s: %s", ticker, e)
        return []
