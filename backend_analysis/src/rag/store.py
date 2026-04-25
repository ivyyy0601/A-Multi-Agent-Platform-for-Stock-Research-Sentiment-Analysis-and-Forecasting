# -*- coding: utf-8 -*-
"""
IvyTrader RAG vector store.

Three collections:
  - iv_reports      : research_reports from pokieticker.db (full memos)
  - iv_analysis     : analysis_history from stock_analysis.db (daily analysis summaries)
  - iv_news         : recent labeled news from layer1_results + news_aligned
                      (includes ret_t1/t3/t5 outcome labels)

Persistence: ChromaDB on disk at  backend_analysis/data/rag_store/
"""

import logging
import os
import sqlite3
from typing import List, Optional

import chromadb
from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(__file__)
_DATA_DIR = os.path.join(_HERE, "..", "..", "data")
_RAG_DIR = os.path.join(_DATA_DIR, "rag_store")

_ANALYSIS_DB = os.path.join(_DATA_DIR, "stock_analysis.db")
_MAIN_DB = os.environ.get("POKIETICKER_DB", os.path.join(_DATA_DIR, "..", "..", "pokieticker.db"))

# ChromaDB client (singleton)
_CLIENT: Optional[chromadb.PersistentClient] = None
_EF: Optional[ONNXMiniLM_L6_V2] = None


def _get_client() -> chromadb.PersistentClient:
    global _CLIENT, _EF
    if _CLIENT is None:
        os.makedirs(_RAG_DIR, exist_ok=True)
        _EF = ONNXMiniLM_L6_V2()  # local ONNX all-MiniLM-L6-v2, no API key needed
        _CLIENT = chromadb.PersistentClient(path=_RAG_DIR)
        logger.info("[RAG] ChromaDB client initialised at %s", _RAG_DIR)
    return _CLIENT


def _get_ef() -> ONNXMiniLM_L6_V2:
    _get_client()  # ensures _EF is set
    return _EF


# ── Helpers ────────────────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> list:
    """Split text into overlapping chunks of ~chunk_size characters."""
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def _upsert_batch(collection, ids, documents, metadatas):
    """Upsert in batches of 100 to avoid payload limits."""
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        collection.upsert(
            ids=ids[i:i + batch_size],
            documents=documents[i:i + batch_size],
            metadatas=metadatas[i:i + batch_size],
        )
    logger.info("[RAG] Upserted %d docs into '%s'", len(ids), collection.name)


# ── Index functions ────────────────────────────────────────────────────────────

def index_reports(force: bool = False) -> int:
    """
    Index research_reports from pokieticker.db.
    Returns number of documents indexed.
    """
    client = _get_client()
    col = client.get_or_create_collection("iv_reports", embedding_function=_get_ef())

    if col.count() > 0 and not force:
        logger.info("[RAG] iv_reports already has %d docs, skipping.", col.count())
        return col.count()

    if not os.path.exists(_MAIN_DB):
        logger.warning("[RAG] pokieticker.db not found at %s", _MAIN_DB)
        return 0

    conn = sqlite3.connect(_MAIN_DB)
    rows = conn.execute(
        "SELECT id, symbol, company, report_type, content, created_at FROM research_reports"
    ).fetchall()
    conn.close()

    if not rows:
        return 0

    ids, docs, metas = [], [], []
    for rid, symbol, company, rtype, content, created_at in rows:
        # Chunk long reports into ~2000-char segments
        chunks = _chunk_text(content, chunk_size=2000, overlap=200)
        for i, chunk in enumerate(chunks):
            ids.append(f"{rid}__chunk{i}")
            docs.append(chunk)
            metas.append({
                "source": "research_reports",
                "symbol": symbol or "",
                "company": company or "",
                "report_type": rtype or "",
                "created_at": (created_at or "")[:10],
                "chunk_index": i,
            })

    _upsert_batch(col, ids, docs, metas)
    return len(ids)


def index_analysis_history(force: bool = False) -> int:
    """
    Index analysis_history from stock_analysis.db.
    Returns number of documents indexed.
    """
    client = _get_client()
    col = client.get_or_create_collection("iv_analysis", embedding_function=_get_ef())

    if col.count() > 0 and not force:
        logger.info("[RAG] iv_analysis already has %d docs, skipping.", col.count())
        return col.count()

    if not os.path.exists(_ANALYSIS_DB):
        logger.warning("[RAG] stock_analysis.db not found at %s", _ANALYSIS_DB)
        return 0

    conn = sqlite3.connect(_ANALYSIS_DB)
    rows = conn.execute("""
        SELECT id, code, name, report_type, sentiment_score,
               operation_advice, trend_prediction, analysis_summary,
               ideal_buy, stop_loss, take_profit, created_at
        FROM analysis_history
        WHERE analysis_summary IS NOT NULL AND analysis_summary != ''
    """).fetchall()
    conn.close()

    if not rows:
        return 0

    ids, docs, metas = [], [], []
    for (row_id, code, name, rtype, sentiment, advice,
         trend, summary, ideal_buy, stop_loss, take_profit, created_at) in rows:

        text = (
            f"Stock: {code} ({name or ''})\n"
            f"Report Type: {rtype}\n"
            f"Sentiment Score: {sentiment}\n"
            f"Operation Advice: {advice}\n"
            f"Trend Prediction: {trend}\n"
            f"Analysis: {summary}"
        )
        ids.append(str(row_id))
        docs.append(text)
        metas.append({
            "source": "analysis_history",
            "symbol": code or "",
            "report_type": rtype or "",
            "operation_advice": advice or "",
            "trend_prediction": trend or "",
            "ideal_buy": float(ideal_buy) if ideal_buy else 0.0,
            "stop_loss": float(stop_loss) if stop_loss else 0.0,
            "take_profit": float(take_profit) if take_profit else 0.0,
            "created_at": str(created_at or "")[:10],
        })

    _upsert_batch(col, ids, docs, metas)
    return len(ids)


def index_labeled_news(
    symbols: Optional[list] = None,
    days_back: int = 0,
    force: bool = False,
    limit_per_symbol: int = 0,
) -> int:
    """
    Index labeled news (layer1_results + news_aligned) from pokieticker.db.
    Only indexes news that has actual return data (ret_t1 is not null).

    Args:
        symbols:            List of tickers to index. None = top 30 by volume.
        days_back:          How many calendar days of news to include.
        force:              Re-index even if collection already populated.
        limit_per_symbol:   Cap per ticker to keep store size manageable.
    Returns:
        Number of documents indexed.
    """
    client = _get_client()
    col = client.get_or_create_collection("iv_news", embedding_function=_get_ef())

    if col.count() > 0 and not force:
        logger.info("[RAG] iv_news already has %d docs, skipping.", col.count())
        return col.count()

    if not os.path.exists(_MAIN_DB):
        logger.warning("[RAG] pokieticker.db not found at %s", _MAIN_DB)
        return 0

    conn = sqlite3.connect(_MAIN_DB)

    # Determine which symbols to index
    if not symbols:
        rows_sym = conn.execute("""
            SELECT symbol, COUNT(*) AS cnt FROM news_aligned
            WHERE ret_t1 IS NOT NULL
            GROUP BY symbol ORDER BY cnt DESC LIMIT 30
        """).fetchall()
        symbols = [r[0] for r in rows_sym]

    if not symbols:
        conn.close()
        return 0

    placeholders = ",".join("?" * len(symbols))
    date_filter = f"AND na.trade_date >= date('now', '-{days_back} days')" if days_back > 0 else ""
    query = f"""
        SELECT
            na.news_id, na.symbol, na.trade_date,
            nr.title, nr.publisher, nr.article_url,
            l1.key_discussion, l1.sentiment,
            l1.reason_growth, l1.reason_decrease,
            na.ret_t1, na.ret_t3, na.ret_t5
        FROM news_aligned na
        JOIN layer1_results l1 ON l1.news_id = na.news_id AND l1.symbol = na.symbol
        LEFT JOIN news_raw nr ON nr.id = na.news_id
        WHERE na.symbol IN ({placeholders})
          AND na.ret_t1 IS NOT NULL
          {date_filter}
          AND l1.key_discussion IS NOT NULL
        ORDER BY na.symbol, na.trade_date DESC
    """

    all_rows = conn.execute(query, symbols).fetchall()
    conn.close()

    if not all_rows:
        return 0

    # Apply per-symbol limit (0 = no limit)
    from collections import defaultdict
    by_symbol: dict = defaultdict(list)
    for row in all_rows:
        sym = row[1]
        if limit_per_symbol == 0 or len(by_symbol[sym]) < limit_per_symbol:
            by_symbol[sym].append(row)

    ids, docs, metas = [], [], []
    for rows in by_symbol.values():
        for (news_id, symbol, trade_date, title, publisher, url,
             key_discussion, sentiment, reason_growth, reason_decrease,
             ret_t1, ret_t3, ret_t5) in rows:

            # Build rich text for embedding
            parts = []
            if title:
                parts.append(f"Title: {title}")
            if key_discussion:
                parts.append(f"Discussion: {key_discussion}")
            if reason_growth:
                parts.append(f"Bull case: {reason_growth}")
            if reason_decrease:
                parts.append(f"Bear case: {reason_decrease}")

            # Append outcome label so the model can learn return patterns
            outcome = "neutral"
            if ret_t1 is not None:
                if ret_t1 > 0.01:
                    outcome = f"next-day +{ret_t1:.1%}"
                elif ret_t1 < -0.01:
                    outcome = f"next-day {ret_t1:.1%}"

            parts.append(f"Actual outcome: {outcome}")
            doc_text = "\n".join(parts)

            ids.append(f"{news_id}__{symbol}")
            docs.append(doc_text)
            metas.append({
                "source": "news_labeled",
                "symbol": symbol,
                "trade_date": trade_date or "",
                "sentiment": sentiment or "",
                "ret_t1": float(ret_t1) if ret_t1 is not None else 0.0,
                "ret_t3": float(ret_t3) if ret_t3 is not None else 0.0,
                "ret_t5": float(ret_t5) if ret_t5 is not None else 0.0,
                "publisher": publisher or "",
                "url": url or "",
            })

    _upsert_batch(col, ids, docs, metas)
    return len(ids)


# ── Search ─────────────────────────────────────────────────────────────────────

def search(
    query: str,
    collection_names: Optional[List[str]] = None,
    symbol: Optional[str] = None,
    top_k: int = 5,
) -> list:
    """
    Search across one or more collections.

    Args:
        query:            Natural language query.
        collection_names: Which collections to search. None = all three.
        symbol:           If provided, filter results to this ticker.
        top_k:            Max results per collection.

    Returns:
        List of result dicts sorted by relevance score.
    """
    client = _get_client()
    ef = _get_ef()

    if collection_names is None:
        collection_names = ["iv_reports", "iv_analysis", "iv_news"]

    results = []
    for name in collection_names:
        try:
            col = client.get_collection(name, embedding_function=ef)
        except Exception:
            continue  # collection doesn't exist yet

        where = {"symbol": symbol.upper()} if symbol else None
        try:
            resp = col.query(
                query_texts=[query],
                n_results=min(top_k, max(col.count(), 1)),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.warning("[RAG] Query failed on %s: %s", name, exc)
            continue

        docs_list = resp.get("documents", [[]])[0]
        meta_list = resp.get("metadatas", [[]])[0]
        dist_list = resp.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs_list, meta_list, dist_list):
            results.append({
                "collection": name,
                "text": doc,
                "metadata": meta,
                "score": round(1.0 - float(dist), 4),  # convert distance → similarity
            })

    # Sort by score descending, return top_k overall
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


# ── Public rebuild helper ──────────────────────────────────────────────────────

def rebuild_all(symbols: Optional[list] = None) -> dict:
    """Full rebuild of all three collections. Returns counts."""
    counts = {
        "reports": index_reports(force=True),
        "analysis": index_analysis_history(force=True),
        "news": index_labeled_news(symbols=symbols, force=True),
    }
    logger.info("[RAG] Rebuild complete: %s", counts)
    return counts
