import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Dict

import requests

logger = logging.getLogger(__name__)

RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline"


def fetch(ticker: str, limit: int = 30) -> List[Dict]:
    ticker = ticker.upper().strip()
    try:
        resp = requests.get(
            RSS_URL,
            params={"s": ticker, "region": "US", "lang": "en-US"},
            headers={"User-Agent": "news-crawler/1.0"},
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
        for item in channel.findall("item")[:limit]:
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            pub = item.findtext("pubDate") or ""
            try:
                published_at = parsedate_to_datetime(pub).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
            except Exception:
                published_at = now
            uid = hashlib.md5(f"yf_{ticker}_{link or title}".encode()).hexdigest()
            results.append({
                "id": uid,
                "ticker": ticker,
                "title": title,
                "summary": desc if desc != title else None,
                "url": link,
                "source": "Yahoo Finance",
                "published_at": published_at,
                "fetched_at": now,
            })
        return results
    except Exception as e:
        logger.debug("[Yahoo] %s: %s", ticker, e)
        return []
