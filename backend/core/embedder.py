"""
core/embedder.py
────────────────
Thin wrapper around Ollama's /api/embeddings endpoint.
Uses nomic-embed-text — 768-dim, fast, runs on CPU.
"""

import logging
from typing import List

import httpx

log = logging.getLogger(__name__)

OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL      = "nomic-embed-text"
TIMEOUT          = 20.0


async def embed(text: str) -> List[float]:
    """Return embedding vector for a single text string."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(OLLAMA_EMBED_URL, json={
            "model":  EMBED_MODEL,
            "prompt": text,
        })
        if resp.status_code != 200:
            raise RuntimeError(
                f"Ollama embed error {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()["embedding"]


async def embed_batch(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts sequentially (Ollama has no native batch endpoint)."""
    results = []
    for i, text in enumerate(texts):
        vec = await embed(text)
        results.append(vec)
        if (i + 1) % 10 == 0:
            log.info("Embedded %d / %d", i + 1, len(texts))
    return results


# ── sync wrapper for the seed script ─────────────────────────────────────────
def embed_sync(text: str) -> List[float]:
    import asyncio
    return asyncio.run(embed(text))
