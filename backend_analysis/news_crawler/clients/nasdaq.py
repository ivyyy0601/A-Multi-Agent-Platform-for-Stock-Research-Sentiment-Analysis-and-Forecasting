import hashlib
import html
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Dict

import requests

logger = logging.getLogger(__name__)

RSS_URL = "https://www.nasdaq.com/feed/rssoutbound"


def fetch(ticker: str, limit: int = 20) -> List[Dict]:
    ticker = ticker.upper().strip()
    try:
        resp = requests.get(
            RSS_URL,
            params={"symbol": ticker},
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        results = []
        seen = set()
        for item in root.findall(".//item")[:limit]:
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
            uid = hashlib.md5(f"nasdaq_{ticker}_{link or title}".encode()).hexdigest()
            results.append({
                "id": uid,
                "ticker": ticker,
                "title": title,
                "summary": None,
                "url": link,
                "source": "Nasdaq",
                "published_at": published_at,
                "fetched_at": now,
            })
        return results
    except Exception as e:
        logger.debug("[Nasdaq] %s: %s", ticker, e)
        return []
