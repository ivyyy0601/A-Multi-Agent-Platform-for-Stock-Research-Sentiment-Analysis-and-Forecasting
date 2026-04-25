# -*- coding: utf-8 -*-
"""
Local Search Service — reads from locally-crawled SQLite databases.

Replaces external search APIs (Bocha/Tavily/Brave/SerpAPI) with data
from the project's own news_crawler and reddit_crawler.

Databases:
  news_crawler/data/news.db    — table: news
  reddit_crawler/data/reddit.db — table: posts
"""

import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from src.search_service import SearchResponse, SearchResult

logger = logging.getLogger(__name__)

# Resolve DB paths relative to this file (backend/src/ → backend/)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NEWS_DB = os.path.join(_BACKEND_DIR, "news_crawler", "news_crawler", "data", "news.db")
_REDDIT_DB = os.path.join(_BACKEND_DIR, "reddit_crawler", "reddit_crawler", "data", "reddit.db")


def _query_news(ticker: str, days: int = 3, limit: int = 20) -> List[dict]:
    """Read recent news articles for a ticker from local news.db."""
    if not os.path.exists(_NEWS_DB):
        logger.warning("news.db not found at %s", _NEWS_DB)
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%S')
    try:
        conn = sqlite3.connect(_NEWS_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT ticker, title, summary, url, source, published_at
            FROM news
            WHERE ticker = ? AND published_at >= ?
            ORDER BY published_at DESC
            LIMIT ?
            """,
            (ticker.upper(), cutoff, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("news.db query failed: %s", exc)
        return []


def _query_reddit(ticker: str, days: int = 3, limit: int = 20) -> List[dict]:
    """Read recent Reddit posts for a ticker from local reddit.db."""
    if not os.path.exists(_REDDIT_DB):
        logger.warning("reddit.db not found at %s", _REDDIT_DB)
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%S')
    try:
        conn = sqlite3.connect(_REDDIT_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT ticker, subreddit, title, text, url, author, score, num_comments, published_at
            FROM posts
            WHERE ticker = ? AND published_at >= ?
            ORDER BY score DESC, published_at DESC
            LIMIT ?
            """,
            (ticker.upper(), cutoff, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("reddit.db query failed: %s", exc)
        return []


class LocalSearchService:
    """
    Drop-in replacement for SearchService that reads from local SQLite DBs.

    DISABLED — intelligence now comes exclusively from Adanos API.
    is_available always returns False so no data is injected from local DBs.
    """

    news_window_days: int = 3

    @property
    def is_available(self) -> bool:
        return False  # Permanently disabled — use Adanos API instead

    # ------------------------------------------------------------------
    # search_stock_news
    # ------------------------------------------------------------------

    def search_stock_news(
        self,
        stock_code: str,
        stock_name: str,
        max_results: int = 5,
        focus_keywords: Optional[List[str]] = None,
    ) -> SearchResponse:
        """Search latest news for a stock from local news.db."""
        ticker = stock_code.upper()
        rows = _query_news(ticker, days=self.news_window_days, limit=max_results)

        results = [
            SearchResult(
                title=r["title"],
                snippet=r.get("summary") or "",
                url=r.get("url") or "",
                source=r.get("source") or "news_crawler",
                published_date=r.get("published_at", "")[:10],
            )
            for r in rows
        ]

        if not results:
            return SearchResponse(
                query=f"{stock_code} {stock_name} news",
                results=[],
                provider="local_news_db",
                success=False,
                error_message="No local news found",
            )

        return SearchResponse(
            query=f"{stock_code} {stock_name} news",
            results=results,
            provider="local_news_db",
            success=True,
        )

    # ------------------------------------------------------------------
    # search_comprehensive_intel
    # ------------------------------------------------------------------

    def search_comprehensive_intel(
        self,
        stock_code: str,
        stock_name: str,
        max_searches: int = 5,
    ) -> Dict[str, SearchResponse]:
        """Return multi-dimensional intel from local DBs."""
        ticker = stock_code.upper()
        intel: Dict[str, SearchResponse] = {}

        # 1. Latest news (from news.db)
        news_rows = _query_news(ticker, days=self.news_window_days, limit=10)
        intel["latest_news"] = SearchResponse(
            query=f"{ticker} latest news",
            results=[
                SearchResult(
                    title=r["title"],
                    snippet=r.get("summary") or "",
                    url=r.get("url") or "",
                    source=r.get("source") or "news_crawler",
                    published_date=r.get("published_at", "")[:10],
                )
                for r in news_rows
            ],
            provider="local_news_db",
            success=bool(news_rows),
            error_message=None if news_rows else "No news found",
        )

        # 2. Reddit / social discussion (from reddit.db)
        reddit_rows = _query_reddit(ticker, days=self.news_window_days, limit=10)
        intel["market_analysis"] = SearchResponse(
            query=f"{ticker} reddit discussion",
            results=[
                SearchResult(
                    title=r["title"],
                    snippet=(r.get("text") or "")[:300],
                    url=r.get("url") or "",
                    source=f"r/{r['subreddit']}" if r.get("subreddit") else "reddit",
                    published_date=r.get("published_at", "")[:10],
                )
                for r in reddit_rows
            ],
            provider="local_reddit_db",
            success=bool(reddit_rows),
            error_message=None if reddit_rows else "No Reddit posts found",
        )

        return intel

    # ------------------------------------------------------------------
    # format_intel_report
    # ------------------------------------------------------------------

    def format_intel_report(
        self,
        intel_results: Dict[str, SearchResponse],
        stock_name: str,
    ) -> str:
        """Format local intel results as a prompt-ready English report."""
        lines = [f"[{stock_name} Intelligence Report — Local Data]"]

        dim_labels = {
            "latest_news": "📰 Latest News",
            "market_analysis": "💬 Reddit / Social Discussion",
            "risk_check": "⚠️ Risk Check",
            "earnings": "📊 Earnings Outlook",
            "industry": "🏭 Industry Trends",
        }

        for dim_name, resp in intel_results.items():
            label = dim_labels.get(dim_name, dim_name)
            lines.append(f"\n{label} (source: {resp.provider}):")
            if resp.success and resp.results:
                for i, r in enumerate(resp.results[:5], 1):
                    date_str = f" [{r.published_date}]" if r.published_date else ""
                    lines.append(f"  {i}. {r.title}{date_str}")
                    if r.snippet:
                        snippet = r.snippet[:200]
                        lines.append(f"     {snippet}")
            else:
                lines.append("  No data available")

        return "\n".join(lines)


# Singleton
_local_search_service: Optional[LocalSearchService] = None


def get_local_search_service() -> LocalSearchService:
    global _local_search_service
    if _local_search_service is None:
        _local_search_service = LocalSearchService()
        logger.info("LocalSearchService initialized (news_db=%s, reddit_db=%s)", _NEWS_DB, _REDDIT_DB)
    return _local_search_service
