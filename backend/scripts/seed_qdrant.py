#!/usr/bin/env python3
"""
scripts/seed_qdrant.py
──────────────────────
One-time script: embed all Q→SQL examples and store them in Qdrant.

Run this after:
  1. Qdrant is running   (docker run -p 6333:6333 qdrant/qdrant)
  2. Ollama is running with nomic-embed-text  (ollama pull nomic-embed-text)

Usage:
    cd dcs-backend
    python scripts/seed_qdrant.py            # normal upsert (skips existing)
    python scripts/seed_qdrant.py --recreate # wipe and re-seed from scratch

IMPORTANT — {DEPT} placeholder:
  The SQL strings in data/few_shot.py use {DEPT} wherever a real department
  code would appear (e.g. WHERE d.department_code = '{DEPT}').

  DO NOT replace {DEPT} before inserting into Qdrant.  The placeholder is
  intentional — core/rag_engine.py substitutes it with the real department
  code at query time, after the examples are retrieved from Qdrant.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Make sure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.few_shot      import FEW_SHOTS
from core.embedder      import embed_batch
from core.qdrant_store  import ensure_collection, upsert_examples, collection_info

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt = "%H:%M:%S",
)
log = logging.getLogger("seed")


def _validate_examples() -> None:
    """Warn if any example SQL is missing the {DEPT} placeholder where expected."""
    issues = []
    for ex in FEW_SHOTS:
        if "department_code" in ex["sql"] and "{DEPT}" not in ex["sql"]:
            issues.append(ex["question"][:70])
    if issues:
        log.warning(
            "%d example(s) reference department_code but are missing {DEPT} placeholder:\n  %s",
            len(issues),
            "\n  ".join(issues),
        )
    else:
        log.info("✓ All examples with department_code use the {DEPT} placeholder correctly.")


async def main():
    recreate = "--recreate" in sys.argv

    log.info("══ College Monitoring — Qdrant Seeder ══")
    log.info("Examples to embed  : %d", len(FEW_SHOTS))
    log.info("Recreate collection: %s", recreate)
    log.info(
        "NOTE: {DEPT} placeholders in SQL are stored as-is — "
        "substitution happens at query time in rag_engine.py"
    )

    # 0. Validate examples
    _validate_examples()

    # 1. Ensure collection exists
    ensure_collection(recreate=recreate)

    # 2. Embed questions only (NOT the SQL — we embed the question text so
    #    similarity search works on natural language, not SQL keywords)
    log.info("Embedding questions with nomic-embed-text …")
    questions = [ex["question"] for ex in FEW_SHOTS]
    vectors   = await embed_batch(questions)
    log.info(
        "Embedding complete — %d vectors of dim %d",
        len(vectors),
        len(vectors[0]) if vectors else 0,
    )

    # 3. Upsert (questions + SQL with {DEPT} intact + tags)
    n = upsert_examples(FEW_SHOTS, vectors)

    # 4. Verify
    info = collection_info()
    log.info(
        "✓ Done — collection '%s' now has %d points",
        info["collection"],
        info["points_count"],
    )
    log.info("Qdrant dashboard: http://localhost:6333/dashboard")


if __name__ == "__main__":
    asyncio.run(main())