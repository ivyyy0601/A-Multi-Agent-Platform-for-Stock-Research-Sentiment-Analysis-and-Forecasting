# -*- coding: utf-8 -*-
"""
===================================
Social Sentiment Intelligence Service
===================================

Fetches Reddit / X (Twitter) / Polymarket social sentiment data
from api.adanos.org for US stock tickers.

Optional — requires SOCIAL_SENTIMENT_API_KEY.
Only activates for US stock codes (AAPL, TSLA, etc.).
"""

import logging
import time
from typing import Any, Dict, List, Optional

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

_TRANSIENT_EXCEPTIONS = (
    requests.exceptions.SSLError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
)

_REQUEST_TIMEOUT = 8  # seconds


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    retry=retry_if_exception_type(_TRANSIENT_EXCEPTIONS),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
def _get_with_retry(url: str, *, headers: Dict[str, str], params: Optional[Dict[str, Any]] = None,
                    timeout: int = _REQUEST_TIMEOUT) -> requests.Response:
    """GET with retry on transient network errors."""
    return requests.get(url, headers=headers, params=params or {}, timeout=timeout)


class SocialSentimentService:
    """
    Social Sentiment Intelligence — Reddit / X / Polymarket.

    Fetches social-media sentiment data from api.adanos.org and formats
    it as a text block suitable for injection into the LLM analysis prompt.

    Usage::

        svc = SocialSentimentService(api_key="sk_live_...", api_url="https://api.adanos.org")
        if svc.is_available:
            context = svc.get_social_context("TSLA")
    """

    # Cache TTL for trending endpoints (seconds)
    _TRENDING_CACHE_TTL = 600  # 10 minutes

    def __init__(self, api_key: Optional[str] = None, api_url: str = "https://api.adanos.org"):
        self._api_key = (api_key or "").strip() or None
        self._api_url = (api_url or "https://api.adanos.org").rstrip("/")
        # Simple in-memory cache: {"key": (timestamp, data)}
        self._cache: Dict[str, tuple] = {}

    @property
    def is_available(self) -> bool:
        return self._api_key is not None

    @property
    def _headers(self) -> Dict[str, str]:
        return {"X-API-Key": self._api_key or "", "Accept": "application/json"}

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------

    def _fetch_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Fetch JSON from API, return None on any error."""
        try:
            resp = _get_with_retry(url, headers=self._headers, params=params)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("Social sentiment API %s returned %s", url, resp.status_code)
        except _TRANSIENT_EXCEPTIONS as e:
            logger.warning("Social sentiment API %s network error: %s", url, e)
        except Exception as e:
            logger.warning("Social sentiment API %s unexpected error: %s", url, e)
        return None

    def _fetch_cached(self, cache_key: str, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """Fetch with simple TTL cache (for trending endpoints)."""
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached and (now - cached[0]) < self._TRENDING_CACHE_TTL:
            return cached[1]
        data = self._fetch_json(url, params)
        if data is not None:
            self._cache[cache_key] = (now, data)
        return data

    SOCIAL_DAYS = 3  # Window size fed to LLM (matches frontend default)

    def fetch_stock_data(self, platform: str, ticker: str) -> Optional[Dict]:
        """Fetch per-ticker stock data from a platform using the /stock/ endpoint (days=3)."""
        url = f"{self._api_url}/{platform}/stocks/v1/stock/{ticker.upper()}"
        return self._fetch_json(url, params={"days": self.SOCIAL_DAYS})

    def fetch_explain(self, platform: str, ticker: str) -> Optional[str]:
        """Fetch AI explanation summary from the /explain endpoint (Reddit and News only)."""
        url = f"{self._api_url}/{platform}/stocks/v1/stock/{ticker.upper()}/explain"
        data = self._fetch_json(url)
        if data and data.get("explanation"):
            return data["explanation"]
        return None

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def get_social_context(self, ticker: str) -> Optional[str]:
        """
        Fetch social sentiment (Reddit / X / News) for the last 3 days
        and return a formatted text block for the LLM prompt.
        Returns None if no data found on any platform.
        """
        if not self.is_available:
            return None

        ticker_upper = ticker.upper()

        reddit_data = self.fetch_stock_data("reddit", ticker_upper)
        x_data      = self.fetch_stock_data("x",      ticker_upper)
        news_data   = self.fetch_stock_data("news",    ticker_upper)

        # AI explain summaries (Reddit + News only, X has no explain endpoint)
        reddit_explain = self.fetch_explain("reddit", ticker_upper)
        news_explain   = self.fetch_explain("news",   ticker_upper)

        # Treat found=False as no data
        def has_data(d: Optional[Dict]) -> bool:
            return bool(d) and d.get("found") is not False

        if not has_data(reddit_data) and not has_data(x_data) and not has_data(news_data):
            return None

        return self._format_social_intel(
            ticker_upper, reddit_data, x_data, news_data,
            reddit_explain=reddit_explain, news_explain=news_explain,
        )

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _coalesce(*values):
        """Return the first non-None value (preserves 0 and 0.0)."""
        for v in values:
            if v is not None:
                return v
        return None

    @staticmethod
    def _format_platform(label: str, icon: str, data: Optional[Dict], lines: List[str]) -> None:
        """Append one platform block (Reddit / X / News) to lines list."""
        if not data or data.get("found") is False:
            lines.append(f"\n{icon} {label}: No data for this period")
            return

        lines.append(f"\n{icon} {label}:")

        buzz      = data.get("buzz_score")
        sentiment = data.get("sentiment_score")
        trend     = data.get("trend", "")
        mentions  = data.get("mentions")
        bullish   = data.get("bullish_pct")
        bearish   = data.get("bearish_pct")
        pos       = data.get("positive_count", 0)
        neu       = data.get("neutral_count", 0)
        neg       = data.get("negative_count", 0)

        if buzz is not None:
            lines.append(f"  Buzz Score: {buzz:.1f}  Trend: {trend}")
        if sentiment is not None:
            lines.append(f"  Sentiment Score: {sentiment:+.3f}  (positive={pos}, neutral={neu}, negative={neg})")
        if mentions is not None:
            bull_str = f"  Bullish: {bullish}%  Bearish: {bearish}%" if bullish is not None else ""
            lines.append(f"  Mentions: {mentions}{bull_str}")

        # Top subreddits / news sources
        top_subs = data.get("top_subreddits", [])
        if top_subs:
            subs_str = ", ".join(f"r/{s['subreddit']}({s['count']})" for s in top_subs[:5])
            lines.append(f"  Top subreddits: {subs_str}")
        top_srcs = data.get("top_sources", [])
        if top_srcs:
            srcs_str = ", ".join(f"{s['source']}({s['count']})" for s in top_srcs[:5])
            lines.append(f"  Top news sources: {srcs_str}")

        # Daily trend (last 3 days)
        daily = data.get("daily_trend", [])
        if daily:
            lines.append("  Daily trend (recent → oldest):")
            for d in reversed(daily[-3:]):
                lines.append(
                    f"    {d.get('date','?')}: {d.get('mentions','?')} mentions, "
                    f"sentiment {d.get('sentiment_score', '?'):+.3f}"
                    if isinstance(d.get("sentiment_score"), (int, float))
                    else f"    {d.get('date','?')}: {d.get('mentions','?')} mentions"
                )

        # Top posts/mentions (up to 5)
        top = data.get("top_mentions") or data.get("top_tweets") or []
        top_sorted = sorted(top, key=lambda m: (m.get("upvotes") or m.get("likes") or 0), reverse=True)
        if top_sorted:
            lines.append("  Top posts:")
            for i, m in enumerate(top_sorted[:5], 1):
                snippet  = (m.get("text_snippet") or m.get("text") or "")[:140]
                score    = m.get("sentiment_label", "")
                upvotes  = SocialSentimentService._coalesce(m.get("upvotes"), m.get("likes"))
                sub      = m.get("subreddit", "")
                author   = m.get("author", "")
                date     = (m.get("created_utc") or m.get("created_at") or "")[:10]
                meta_parts = []
                if score:
                    meta_parts.append(score)
                if upvotes is not None:
                    meta_parts.append(f"↑{upvotes}")
                if sub:
                    meta_parts.append(f"r/{sub}")
                if author:
                    meta_parts.append(f"@{author}")
                if date:
                    meta_parts.append(date)
                meta = f" ({', '.join(meta_parts)})" if meta_parts else ""
                lines.append(f"    {i}. \"{snippet}\"{meta}")

    @staticmethod
    def _format_social_intel(
        ticker: str,
        reddit_data: Optional[Dict],
        x_data: Optional[Dict],
        news_data: Optional[Dict],
        reddit_explain: Optional[str] = None,
        news_explain: Optional[str] = None,
    ) -> str:
        """Format 3-day Adanos social sentiment data as a prompt-ready text block."""
        lines = [f"📱 Social Sentiment Intelligence for {ticker} — last 3 days (Reddit / X / News)"]
        lines.append("=" * 60)

        # AI summaries first — most useful for catalyst/risk extraction
        if reddit_explain or news_explain:
            lines.append("\n🤖 AI Summaries (why this stock is trending):")
            if reddit_explain:
                lines.append(f"  Reddit: {reddit_explain}")
            if news_explain:
                lines.append(f"  News:   {news_explain}")

        SocialSentimentService._format_platform("Reddit",     "👾", reddit_data, lines)
        SocialSentimentService._format_platform("X/Twitter",  "𝕏",  x_data,     lines)
        SocialSentimentService._format_platform("News",       "📰", news_data,   lines)

        lines.append("\nSource: Adanos API (api.adanos.org) — 3-day social sentiment window")
        return "\n".join(lines)
