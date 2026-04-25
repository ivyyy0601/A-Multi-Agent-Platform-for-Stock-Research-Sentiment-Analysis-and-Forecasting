# -*- coding: utf-8 -*-
"""
RAG tool for the IvyTrader agent.

Exposes `get_iv_rag_search` — semantic search over:
  - Past research reports (iv_reports)
  - Daily analysis history (iv_analysis)
  - Labeled historical news with actual return outcomes (iv_news)

The tool returns the top-k most relevant passages so the agent can
ground its reasoning in prior research and historical news outcomes.
"""

import logging

from src.agent.tools.registry import ToolDefinition, ToolParameter

logger = logging.getLogger(__name__)


def _handle_get_iv_rag_search(
    query: str,
    symbol: str = "",
    collection: str = "all",
    top_k: int = 5,
) -> dict:
    """Semantic search over IvyTrader's vector store."""
    try:
        from src.rag.store import search

        # Map collection argument to list
        if collection == "reports":
            cols = ["iv_reports"]
        elif collection == "analysis":
            cols = ["iv_analysis"]
        elif collection == "news":
            cols = ["iv_news"]
        else:
            cols = None  # all

        results = search(
            query=query,
            collection_names=cols,
            symbol=symbol.upper() if symbol else None,
            top_k=top_k,
        )

        if not results:
            return {
                "query": query,
                "results": [],
                "note": "No relevant documents found. The vector store may not be indexed yet.",
            }

        formatted = []
        for r in results:
            meta = r.get("metadata", {})
            formatted.append({
                "source": meta.get("source", r.get("collection", "")),
                "symbol": meta.get("symbol", ""),
                "date": meta.get("created_at") or meta.get("trade_date", ""),
                "score": r.get("score"),
                "text": r.get("text", "")[:1500],  # cap text length
                "extra": {
                    k: v for k, v in meta.items()
                    if k not in ("source", "symbol", "created_at", "trade_date")
                },
            })

        return {
            "query": query,
            "symbol_filter": symbol.upper() if symbol else None,
            "total_results": len(formatted),
            "results": formatted,
        }

    except Exception as exc:
        logger.exception("[RAG] get_iv_rag_search failed")
        return {"error": f"RAG search failed: {exc}"}


get_iv_rag_search_tool = ToolDefinition(
    name="get_iv_rag_search",
    description=(
        "Semantic search over IvyTrader's knowledge base: past research reports, "
        "daily analysis summaries, and labeled historical news with actual price outcome data. "
        "Use this to retrieve relevant past analysis before writing new research, "
        "or to find historical news events similar to the current situation. "
        "The 'news' collection includes how the stock actually moved after each event (ret_t1, ret_t3)."
    ),
    parameters=[
        ToolParameter(
            name="query",
            type="string",
            description=(
                "Natural language search query. Be specific — "
                "e.g. 'NVDA AI data center earnings beat', 'AAPL tariff risk China', "
                "'Fed rate decision tech stocks sell-off'"
            ),
            required=True,
        ),
        ToolParameter(
            name="symbol",
            type="string",
            description="Filter results to a specific stock ticker (optional, e.g. 'NVDA')",
            required=False,
            default="",
        ),
        ToolParameter(
            name="collection",
            type="string",
            description=(
                "Which knowledge base to search: "
                "'reports' (research memos), "
                "'analysis' (daily analysis history), "
                "'news' (labeled historical news with return outcomes), "
                "'all' (search all three)"
            ),
            required=False,
            default="all",
            enum=["all", "reports", "analysis", "news"],
        ),
        ToolParameter(
            name="top_k",
            type="integer",
            description="Number of results to return (default 5, max 10)",
            required=False,
            default=5,
        ),
    ],
    handler=_handle_get_iv_rag_search,
    category="analysis",
)

RAG_TOOLS = [get_iv_rag_search_tool]
