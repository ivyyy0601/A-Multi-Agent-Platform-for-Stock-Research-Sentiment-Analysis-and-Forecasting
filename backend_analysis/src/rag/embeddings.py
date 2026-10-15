# -*- coding: utf-8 -*-
"""
Gemini-based embedding function for ChromaDB.

Uses Google's text-embedding-004 model (free tier, 1536 dims).
Falls back to a simple TF-IDF-style hash embedding if the API call fails.
"""

import hashlib
import logging
import os
from typing import List

import requests

logger = logging.getLogger(__name__)

GEMINI_EMBED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "text-embedding-004:embedContent"
)
EMBED_DIM = 768  # text-embedding-004 output dimension


def _gemini_embed_one(text: str, api_key: str) -> List[float]:
    """Embed a single text with Gemini text-embedding-004."""
    resp = requests.post(
        GEMINI_EMBED_URL,
        params={"key": api_key},
        json={"model": "models/text-embedding-004", "content": {"parts": [{"text": text}]}},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["embedding"]["values"]


def _fallback_embed(text: str) -> List[float]:
    """
    Deterministic pseudo-embedding from MD5 hash (768 floats in [-1, 1]).
    Only used when Gemini API is unavailable — not semantically meaningful.
    """
    digest = hashlib.md5(text.encode()).digest()
    # Expand 16 bytes to 768 floats by repeating and normalising
    cycle = list(digest) * (768 // 16 + 1)
    return [(b / 127.5 - 1.0) for b in cycle[:768]]


class GeminiEmbeddingFunction:
    """
    ChromaDB-compatible embedding function.

    Usage::

        ef = GeminiEmbeddingFunction(api_key="…")
        collection = client.get_or_create_collection("name", embedding_function=ef)
    """

    def name(self) -> str:  # required by ChromaDB >= 1.0
        return "GeminiEmbeddingFunction"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self._api_key:
            logger.warning("[RAG] No GEMINI_API_KEY — will use fallback hash embeddings (not semantic).")

    def __call__(self, input: List[str]) -> List[List[float]]:  # noqa: A002
        results = []
        for text in input:
            truncated = text[:8000]  # stay within token limits
            if self._api_key:
                try:
                    results.append(_gemini_embed_one(truncated, self._api_key))
                    continue
                except Exception as exc:
                    logger.warning("[RAG] Gemini embed failed (%s), using fallback.", exc)
            results.append(_fallback_embed(truncated))
        return results
