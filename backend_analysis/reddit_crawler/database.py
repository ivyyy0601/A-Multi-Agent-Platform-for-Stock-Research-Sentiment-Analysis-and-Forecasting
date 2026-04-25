import os
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict

import config

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(config.DATABASE_PATH)), exist_ok=True)
    conn = sqlite3.connect(config.DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id           TEXT PRIMARY KEY,
                ticker       TEXT NOT NULL,
                subreddit    TEXT,
                title        TEXT NOT NULL,
                text         TEXT,
                url          TEXT,
                author       TEXT,
                score        INTEGER DEFAULT 0,
                num_comments INTEGER DEFAULT 0,
                published_at TEXT NOT NULL,
                fetched_at   TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_ticker ON posts(ticker)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published_at)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                ticker   TEXT PRIMARY KEY,
                added_at TEXT NOT NULL
            )
        """)
        conn.commit()
    logger.info("Database initialized: %s", config.DATABASE_PATH)


def upsert_posts(items: List[Dict]):
    if not items:
        return
    with _get_conn() as conn:
        conn.executemany("""
            INSERT OR IGNORE INTO posts
                (id, ticker, subreddit, title, text, url, author, score, num_comments, published_at, fetched_at)
            VALUES
                (:id, :ticker, :subreddit, :title, :text, :url, :author, :score, :num_comments, :published_at, :fetched_at)
        """, items)
        conn.commit()


def cleanup_old_posts():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=config.POST_RETENTION_DAYS)).strftime('%Y-%m-%dT%H:%M:%S')
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM posts WHERE published_at < ?", (cutoff,))
        conn.commit()
        if cur.rowcount:
            logger.info("Cleaned up %d old posts", cur.rowcount)


def get_posts(ticker: str, days: int = 3, limit: int = 50) -> List[Dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%S')
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT ticker, subreddit, title, text, url, author, score, num_comments, published_at
            FROM posts
            WHERE ticker = ? AND published_at >= ?
            ORDER BY published_at DESC
            LIMIT ?
        """, (ticker.upper(), cutoff, limit)).fetchall()
    return [dict(r) for r in rows]


def get_watchlist() -> List[str]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT ticker FROM watchlist ORDER BY ticker").fetchall()
    return [r["ticker"] for r in rows]


def add_to_watchlist(tickers: List[str]):
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    with _get_conn() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO watchlist (ticker, added_at) VALUES (?, ?)",
            [(t.upper(), now) for t in tickers]
        )
        conn.commit()


def remove_from_watchlist(ticker: str):
    with _get_conn() as conn:
        conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker.upper(),))
        conn.commit()
