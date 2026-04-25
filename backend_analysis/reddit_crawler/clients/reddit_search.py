import hashlib
import logging
import time
import random
from datetime import datetime, timezone
from typing import List, Dict, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.reddit.com"
HEADERS = {"User-Agent": "reddit-crawler/1.0 (finance data collection)"}


def _get_with_backoff(url: str, params: dict, max_retries: int = 4) -> Optional[requests.Response]:
    for i in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if resp.status_code == 429:
                wait = (2 ** i) + random.random() * 2
                logger.debug("Rate limited, waiting %.1fs", wait)
                time.sleep(wait)
                continue
            if resp.status_code in (500, 502, 503):
                time.sleep((2 ** i) + 1)
                continue
            if resp.status_code == 200:
                return resp
        except Exception as e:
            logger.debug("Request error: %s", e)
            time.sleep((2 ** i) + 1)
    return None


def search_subreddit(ticker: str, subreddit: str, limit: int = 25, days: int = 3) -> List[Dict]:
    """Search a subreddit for posts mentioning the ticker."""
    url = f"{BASE_URL}/r/{subreddit}/search.json"
    params = {
        "q": f"${ticker} OR {ticker}",
        "restrict_sr": "on",
        "sort": "new",
        "t": "week",
        "limit": min(limit, 100),
    }
    resp = _get_with_backoff(url, params)
    if not resp:
        return []
    try:
        children = resp.json().get("data", {}).get("children", [])
    except Exception:
        return []
    return _parse_children(children, ticker, subreddit)


def fetch_subreddit_new(subreddit: str, limit: int = 50) -> List[Dict]:
    """Fetch latest posts from a subreddit (no ticker filter)."""
    url = f"{BASE_URL}/r/{subreddit}/new.json"
    params = {"limit": min(limit, 100)}
    resp = _get_with_backoff(url, params)
    if not resp:
        return []
    try:
        children = resp.json().get("data", {}).get("children", [])
    except Exception:
        return []
    # ticker=None means caller will do ticker matching
    return _parse_children(children, ticker=None, subreddit=subreddit)


def _parse_children(children: list, ticker: Optional[str], subreddit: str) -> List[Dict]:
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    results = []
    for item in children:
        p = item.get("data", {})
        title = (p.get("title") or "").strip()
        if not title:
            continue
        created_utc = p.get("created_utc")
        if created_utc:
            published_at = datetime.fromtimestamp(float(created_utc), tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        else:
            published_at = now
        reddit_id = p.get("id") or p.get("name", "")
        permalink = p.get("permalink", "")
        url = f"{BASE_URL}{permalink}" if permalink else (p.get("url") or "")
        uid = hashlib.md5(f"reddit_{reddit_id}".encode()).hexdigest()
        results.append({
            "id": uid,
            "ticker": ticker or "",
            "subreddit": p.get("subreddit") or subreddit,
            "title": title,
            "text": (p.get("selftext") or "").strip() or None,
            "url": url,
            "author": p.get("author") or "unknown",
            "score": int(p.get("score") or 0),
            "num_comments": int(p.get("num_comments") or 0),
            "published_at": published_at,
            "fetched_at": now,
        })
    return results
