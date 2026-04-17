"""
main.py – FastAPI Backend (slim entry point)
============================================
All routes are organized into the `routers/` package.
Domain modules: chat, students, faculty, timetable, arrears, subjects.
Upload routes are served from the `upload/` package.

Start server:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# Validate required env vars at startup
_REQUIRED_ENV = ["DB_USER", "DB_PASS", "DB_HOST", "DB_PORT", "DB_NAME"]
_missing = [v for v in _REQUIRED_ENV if not os.getenv(v) and not os.getenv("DATABASE_URL")]
if _missing:
    raise RuntimeError(
        f"Missing required environment variables: {', '.join(_missing)}\n"
        "Set them in your .env file (see .env.example)."
    )

from core.rag_engine   import get_rag_engine      # NEW: RAG engine
from core.sql_executor import get_executor
from upload            import upload_router

# Domain routers
from routers import chat, students, faculty, timetable, arrears, subjects, auth, users, departments, stats

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

USE_RAG = os.getenv("USE_RAG", "true").lower() == "true"   # set USE_RAG=false to disable


# ── App lifecycle ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI server…")

    # DB pool
    executor = get_executor()
    await executor.init_pool()
    logger.info("✓ DB pool ready")

    if USE_RAG:
        # RAG engine (Qdrant + embeddings + SQLCoder)
        rag = get_rag_engine()
        try:
            model = await rag.detect_available_model()
            logger.info(f"✓ RAG model ready: {model}")
            await rag.index_examples()
            logger.info("✓ Qdrant RAG index populated")
            # Pre-load model into VRAM so first real query is instant
            await rag.warm_up()
            # Swap the engine used by the chat router
            app.state.nl_engine = rag
        except Exception as e:
            logger.warning(
                f"⚠  RAG engine not ready: {e}\n"
                "   Chat will fail until Ollama starts."
            )
            # Fallback to schema-only mode within the rag_engine
            app.state.nl_engine = rag
    else:
        # If RAG is disabled, still use the rag_engine but bypass Qdrant (it gracefully degrades)
        rag = get_rag_engine()
        app.state.nl_engine = rag

    yield

    await get_executor().close()
    logger.info("Server shut down cleanly")


# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="DCS Monitoring System – AI API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restrict to your college domain in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount routers ─────────────────────────────────────────────────────────────
app.include_router(upload_router,     prefix="/api/upload", tags=["Upload"])
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(students.router)
app.include_router(faculty.router)
app.include_router(timetable.router)
app.include_router(arrears.router)
app.include_router(subjects.router)
app.include_router(users.router)
app.include_router(departments.router)
app.include_router(stats.router)