#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build / rebuild the IvyTrader RAG vector store.

Usage:
    python build_rag.py                     # incremental (skip if already indexed)
    python build_rag.py --force             # full rebuild
    python build_rag.py --force --symbols AAPL,NVDA,TSLA   # rebuild specific tickers in news
"""

import argparse
import logging
import os
import sys

# Make sure project root is in path
sys.path.insert(0, os.path.dirname(__file__))

# Load env from .env
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("build_rag")


def main():
    parser = argparse.ArgumentParser(description="Build IvyTrader RAG vector store")
    parser.add_argument("--force", action="store_true", help="Force full rebuild")
    parser.add_argument("--symbols", default="", help="Comma-separated tickers for news collection")
    parser.add_argument("--days-back", type=int, default=0, help="Days of news to index (0 = all history)")
    parser.add_argument("--collection", choices=["all", "reports", "analysis", "news"], default="all")
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None

    from src.rag.store import index_reports, index_analysis_history, index_labeled_news

    counts = {}

    if args.collection in ("all", "reports"):
        logger.info("Indexing research reports…")
        counts["reports"] = index_reports(force=args.force)

    if args.collection in ("all", "analysis"):
        logger.info("Indexing analysis history…")
        counts["analysis"] = index_analysis_history(force=args.force)

    if args.collection in ("all", "news"):
        logger.info("Indexing labeled news (days_back=%d)…", args.days_back)
        counts["news"] = index_labeled_news(
            symbols=symbols,
            days_back=args.days_back,
            force=args.force,
        )

    logger.info("Done. Indexed: %s", counts)
    print("\n✓ RAG build complete:")
    for k, v in counts.items():
        print(f"  {k:12s}: {v:,d} chunks")


if __name__ == "__main__":
    main()
