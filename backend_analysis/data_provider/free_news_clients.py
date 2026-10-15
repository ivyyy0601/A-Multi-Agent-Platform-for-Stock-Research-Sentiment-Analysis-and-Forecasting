# -*- coding: utf-8 -*-
"""
Free news clients for US stocks — no API key required.
Sources: Yahoo Finance RSS, Google News RSS, CNBC RSS, Nasdaq RSS, SEC EDGAR.
"""

import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Dict

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _parse_rfc2822(date_str: str) -> str:
    try:
        return parsedate_to_datetime(date_str).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    except Exception:
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')


def _make_session(user_agent: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent})
    return s


# ---------------------------------------------------------------------------
# Yahoo Finance News (RSS, ticker-specific)
# ---------------------------------------------------------------------------

class YahooFinanceNewsClient:
    RSS_URL = "https://feeds.finance.yahoo.com/rss/2.0/headline"

    def __init__(self):
        self.session = _make_session("finance-sentiment-dashboard/1.0")

    def fetch(self, ticker: str, limit: int = 20) -> List[Dict]:
        ticker = ticker.upper().strip()
        try:
            resp = self.session.get(self.RSS_URL, params={"s": ticker, "region": "US", "lang": "en-US"}, timeout=10)
            if resp.status_code != 200:
                logger.debug("[YahooNews] HTTP %s for %s", resp.status_code, ticker)
                return []
            root = ET.fromstring(resp.content)
            channel = root.find("channel")
            if channel is None:
                return []
            results = []
            for item in channel.findall("item")[:limit]:
                title = (item.findtext("title") or "").strip()
                if not title:
                    continue
                desc = (item.findtext("description") or "").strip()
                link = (item.findtext("link") or "").strip()
                text = f"{title}. {desc}" if desc and desc != title else title
                results.append({
                    "title": title,
                    "text": text,
                    "url": link,
                    "source": "Yahoo Finance",
                    "published_date": _parse_rfc2822(item.findtext("pubDate") or ""),
                })
            return results
        except Exception as e:
            logger.debug("[YahooNews] Error for %s: %s", ticker, e)
            return []


# ---------------------------------------------------------------------------
# Google News RSS (free, aggregates many sources)
# ---------------------------------------------------------------------------

class GoogleNewsClient:
    RSS_URL = "https://news.google.com/rss/search"

    def __init__(self):
        self.session = _make_session("Mozilla/5.0 (compatible; finance-sentiment-bot/1.0)")

    def fetch(self, ticker: str, limit: int = 30) -> List[Dict]:
        ticker = ticker.upper().strip()
        queries = [f"{ticker} stock", f"${ticker} earnings"]
        results = []
        seen = set()
        per_query = max(limit // len(queries), 5)
        for q in queries:
            try:
                resp = self.session.get(self.RSS_URL, params={"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"}, timeout=10)
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.content)
                channel = root.find("channel")
                if channel is None:
                    continue
                for item in channel.findall("item")[:per_query]:
                    title = html.unescape((item.findtext("title") or "").strip())
                    link = (item.findtext("link") or "").strip()
                    if not title or link in seen:
                        continue
                    seen.add(link)
                    results.append({
                        "title": title,
                        "text": title,
                        "url": link,
                        "source": "Google News",
                        "published_date": _parse_rfc2822(item.findtext("pubDate") or ""),
                    })
            except Exception as e:
                logger.debug("[GoogleNews] Error query '%s': %s", q, e)
        return results[:limit]


# ---------------------------------------------------------------------------
# CNBC RSS (free, finance/earnings feeds)
# ---------------------------------------------------------------------------

class CNBCNewsClient:
    FEEDS = [
        "https://www.cnbc.com/id/10000664/device/rss/rss.html",  # Finance
        "https://www.cnbc.com/id/15839135/device/rss/rss.html",  # Earnings
    ]

    def __init__(self):
        self.session = _make_session(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

    def fetch(self, ticker: str, limit: int = 20) -> List[Dict]:
        ticker = ticker.upper().strip()
        results = []
        seen = set()
        for feed_url in self.FEEDS:
            try:
                resp = self.session.get(feed_url, timeout=10)
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item")[:limit]:
                    title = html.unescape((item.findtext("title") or "").strip())
                    link = (item.findtext("link") or "").strip()
                    if not title or link in seen:
                        continue
                    # Only keep articles mentioning the ticker
                    if ticker not in title.upper() and f"${ticker}" not in title.upper():
                        continue
                    seen.add(link)
                    results.append({
                        "title": title,
                        "text": title,
                        "url": link,
                        "source": "CNBC",
                        "published_date": _parse_rfc2822(item.findtext("pubDate") or ""),
                    })
            except Exception as e:
                logger.debug("[CNBC] Error: %s", e)
        return results[:limit]


# ---------------------------------------------------------------------------
# Nasdaq News RSS (ticker-specific)
# ---------------------------------------------------------------------------

class NasdaqNewsClient:
    RSS_URL = "https://www.nasdaq.com/feed/rssoutbound"

    def __init__(self):
        self.session = _make_session(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

    def fetch(self, ticker: str, limit: int = 20) -> List[Dict]:
        ticker = ticker.upper().strip()
        try:
            resp = self.session.get(self.RSS_URL, params={"symbol": ticker}, timeout=10)
            if resp.status_code != 200:
                logger.debug("[NasdaqNews] HTTP %s for %s", resp.status_code, ticker)
                return []
            root = ET.fromstring(resp.content)
            results = []
            seen = set()
            for item in root.findall(".//item")[:limit]:
                title = html.unescape((item.findtext("title") or "").strip())
                link = (item.findtext("link") or "").strip()
                if not title or link in seen:
                    continue
                seen.add(link)
                results.append({
                    "title": title,
                    "text": title,
                    "url": link,
                    "source": "Nasdaq",
                    "published_date": _parse_rfc2822(item.findtext("pubDate") or ""),
                })
            return results
        except Exception as e:
            logger.debug("[NasdaqNews] Error for %s: %s", ticker, e)
            return []


# ---------------------------------------------------------------------------
# SEC EDGAR (8-K filings, official announcements)
# ---------------------------------------------------------------------------

_TICKER_TO_CIK = {
    'AAPL':  '0000320193',
    'MSFT':  '0000789019',
    'GOOG':  '0001652044',
    'GOOGL': '0001652044',
    'AMZN':  '0001018724',
    'NVDA':  '0001045810',
    'META':  '0001326801',
    'TSLA':  '0001318605',
    'NFLX':  '0001065280',
    'AMD':   '0000002488',
    'INTC':  '0000050863',
    'QCOM':  '0000804328',
    'AVGO':  '0001730168',
    'CRM':   '0001108524',
    'ORCL':  '0001341439',
    'IBM':   '0000051143',
    'JPM':   '0000019617',
    'BAC':   '0000070858',
    'GS':    '0000886982',
    'MS':    '0000895421',
    'XOM':   '0000034088',
    'CVX':   '0000093410',
    'SPY':   None,   # ETF, no 8-K
    'QQQ':   None,
}

_ATOM_NS = 'http://www.w3.org/2005/Atom'


class SECEdgarClient:
    BASE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"

    def __init__(self):
        self.session = _make_session("FinanceSentimentBot/1.0 (research@example.com)")

    def fetch(self, ticker: str, limit: int = 10) -> List[Dict]:
        ticker = ticker.upper().strip()
        cik = _TICKER_TO_CIK.get(ticker)
        if not cik:
            return []
        try:
            resp = self.session.get(self.BASE_URL, params={
                "action": "getcompany", "CIK": cik,
                "type": "8-K", "dateb": "", "owner": "include",
                "count": limit, "output": "atom",
            }, timeout=10)
            if resp.status_code != 200:
                return []
            root = ET.fromstring(resp.content)
            ns = {'atom': _ATOM_NS}
            results = []
            for entry in root.findall('atom:entry', ns):
                title = (entry.findtext('atom:title', '', ns) or '').strip()
                link_el = entry.find('atom:link', ns)
                link = link_el.attrib.get('href', '') if link_el is not None else ''
                updated = entry.findtext('atom:updated', '', ns)
                if not title:
                    continue
                try:
                    dt = datetime.fromisoformat(updated.replace('Z', '+00:00'))
                    pub = dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
                except Exception:
                    pub = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
                results.append({
                    "title": f"[SEC 8-K] {ticker}: {title}",
                    "text": f"{ticker} SEC Filing: {title}",
                    "url": link,
                    "source": "SEC EDGAR",
                    "published_date": pub,
                })
            return results
        except Exception as e:
            logger.debug("[SEC EDGAR] Error for %s: %s", ticker, e)
            return []


# ---------------------------------------------------------------------------
# Utility: extract ticker symbol from a search query string
# ---------------------------------------------------------------------------

_COMMON_WORDS = {'STOCK', 'NEWS', 'LATEST', 'EARNINGS', 'AND', 'THE', 'FOR', 'INC', 'CORP', 'LTD'}


def extract_ticker_from_query(query: str) -> str:
    """
    Try to extract a US stock ticker from a query like
    "Apple Inc. AAPL stock latest news" → "AAPL"
    Falls back to the first uppercase token if no clear match.
    """
    tokens = re.findall(r'\b[A-Z]{1,5}\b', query)
    for token in tokens:
        if token not in _COMMON_WORDS and len(token) >= 1:
            return token
    return tokens[0] if tokens else query.split()[0].upper()
