"""
core/qdrant_store.py
────────────────────
Qdrant vector store for DCS few-shot Q→SQL examples.

Collection schema:
  vector : 768-dim float  (nomic-embed-text embedding of the *question*)
  payload:
    question : str   — the natural-language question
    sql      : str   — the gold-standard SQL for this schema
    tags     : list  — topic labels
    id_str   : str   — stable string ID (hash of question)

All operations are synchronous — called from the seed script.
The search() helper is async-compatible (used at inference time).
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import List, Optional

from qdrant_client import QdrantClient
import qdrant_client
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchAny,
)

log = logging.getLogger(__name__)

COLLECTION   = "dcs_few_shots"
VECTOR_SIZE  = 768          # nomic-embed-text output dimension
QDRANT_URL   = os.getenv("QDRANT_URL", "").strip()
QDRANT_PATH  = os.getenv(
    "QDRANT_PATH",
    str((Path(__file__).resolve().parent.parent / ".qdrant_data").resolve()),
)


def _make_id(question: str) -> int:
    """Stable int ID from question text (Qdrant needs int or UUID)."""
    return int(hashlib.md5(question.encode()).hexdigest(), 16) % (2**63)


def _content_hash(example: dict) -> str:
    """Stable hash for payload content to detect SQL/tag edits for a question."""
    q = (example.get("question") or "").strip()
    sql = (example.get("sql") or "").strip()
    tags = ",".join(sorted(str(t) for t in (example.get("tags") or [])))
    raw = f"{q}\n---\n{sql}\n---\n{tags}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


# ── Client singleton ──────────────────────────────────────────────────────────
_client: Optional[QdrantClient] = None

def get_client() -> QdrantClient:
    global _client
    if _client is None:
        if QDRANT_URL:
            _client = QdrantClient(url=QDRANT_URL, timeout=10)
            log.info("Qdrant client ready (remote): %s", QDRANT_URL)
        else:
            Path(QDRANT_PATH).mkdir(parents=True, exist_ok=True)
            _client = QdrantClient(path=QDRANT_PATH, timeout=10)
            log.info("Qdrant client ready (local path): %s", QDRANT_PATH)
    return _client


# ── Collection management ─────────────────────────────────────────────────────
def ensure_collection(recreate: bool = False) -> None:
    """Create the collection if it doesn't exist. Pass recreate=True to wipe."""
    client = get_client()
    exists = any(c.name == COLLECTION for c in client.get_collections().collections)

    if exists and recreate:
        log.info("Dropping existing collection '%s'", COLLECTION)
        client.delete_collection(COLLECTION)
        exists = False

    if not exists:
        log.info("Creating collection '%s' (dim=%d)", COLLECTION, VECTOR_SIZE)
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def upsert_examples(examples: List[dict], vectors: List[List[float]]) -> int:
    """
    Upsert (question, sql, tags) pairs with their pre-computed embeddings.
    Returns count of upserted points.
    """
    client = get_client()
    points = [
        PointStruct(
            id      = _make_id(ex["question"]),
            vector  = vec,
            payload = {
                "question": ex["question"],
                "sql":      ex["sql"],
                "tags":     ex.get("tags", []),
                "id_str":   ex["question"][:60],
                "content_hash": _content_hash(ex),
            },
        )
        for ex, vec in zip(examples, vectors)
    ]
    client.upsert(collection_name=COLLECTION, points=points)
    log.info("Upserted %d points into '%s'", len(points), COLLECTION)
    return len(points)


def collection_info() -> dict:
    """Return basic stats about the collection."""
    client = get_client()
    info   = client.get_collection(COLLECTION)
    return {
        "points_count":  info.points_count,
        "vector_size":   VECTOR_SIZE,
        "collection":    COLLECTION,
        "qdrant_url":    QDRANT_URL or None,
        "qdrant_path":   None if QDRANT_URL else QDRANT_PATH,
    }


def _existing_point_ids() -> set[int]:
    """Return all existing integer point IDs in the collection."""
    client = get_client()
    ids: set[int] = set()
    offset = None

    while True:
        points, next_offset = client.scroll(
            collection_name=COLLECTION,
            limit=256,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )

        for p in points:
            try:
                ids.add(int(p.id))
            except Exception:
                continue

        if next_offset is None:
            break
        offset = next_offset

    return ids


def filter_missing_examples(examples: List[dict]) -> List[dict]:
    """Return examples whose question-hash IDs are not present in Qdrant."""
    existing_ids = _existing_point_ids()
    return [ex for ex in examples if _make_id(ex["question"]) not in existing_ids]


def _existing_content_hashes() -> dict[int, str]:
    """Return current content_hash by point id for existing Qdrant payloads."""
    client = get_client()
    hashes: dict[int, str] = {}
    offset = None

    while True:
        points, next_offset = client.scroll(
            collection_name=COLLECTION,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        for p in points:
            try:
                pid = int(p.id)
            except Exception:
                continue
            payload = p.payload or {}
            h = str(payload.get("content_hash") or "")
            hashes[pid] = h

        if next_offset is None:
            break
        offset = next_offset

    return hashes


def filter_new_or_changed_examples(examples: List[dict]) -> List[dict]:
    """Return only examples that are missing OR whose content has changed."""
    existing_hashes = _existing_content_hashes()
    changed: List[dict] = []
    for ex in examples:
        eid = _make_id(ex["question"])
        new_hash = _content_hash(ex)
        old_hash = existing_hashes.get(eid)
        if old_hash != new_hash:
            changed.append(ex)
    return changed


# ── Inference-time search ─────────────────────────────────────────────────────
def search(
    query_vector: List[float],
    top_k: int = 4,
    tag_filter: Optional[List[str]] = None,
) -> List[dict]:
    client = get_client()

    query = query_vector

    # Apply filter ONLY if exists
    if tag_filter:
        query = {
            "vector": query_vector,
            "filter": {
                "must": [
                    {
                        "key": "tags",
                        "match": {"any": tag_filter}
                    }
                ]
            }
        }

    response = client.query_points(
        collection_name=COLLECTION,
        query=query,      # ✅ ALWAYS use this
        limit=top_k,
        with_payload=True,
    )

    hits = response.points  # ✅ REQUIRED

    return [
        {
            "question": h.payload["question"],
            "sql": h.payload["sql"],
            "tags": h.payload.get("tags", []),
            "score": round(h.score, 4),
        }
        for h in hits
    ]