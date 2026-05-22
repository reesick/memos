"""
api/main.py – FastAPI REST API
6 endpoints defined in PRD Section 8.
Calls core/engine.py ONLY – never touches stores directly.
Auto-generates /docs at localhost:8000/docs.
"""

import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Absolute project root — works regardless of how uvicorn imports this module
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEMO_DIR = _PROJECT_ROOT / "demo"

import core.engine as engine
from core.input_router import EmptyContentError, InputTooLargeError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="MemoryOS",
    description="Open memory middleware engine for LLM applications. REST API · Python SDK · MCP Server",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Root fix: CORS for local dev — allows file://, localhost:*, and any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------
# Request/Response models
# ----------------------------------------------------------------

class AddRequest(BaseModel):
    content: str = Field(..., description="Content to store in memory")
    source_type: str = Field("text", description="Input type: text|pdf|code|json|csv")
    session_id: Optional[str] = Field(None, description="Session identifier")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    top_k: int = Field(5, ge=1, le=20, description="Number of results")
    include_expired: bool = Field(False, description="Include expired/superseded facts")
    source_filter: Optional[str] = Field(None, description="Filter by source_type")
    session_filter: Optional[str] = Field(None, description="Filter by session_id")


class AugmentRequest(BaseModel):
    prompt: str = Field(..., description="Prompt to augment with memory context")
    top_k: int = Field(3, ge=1, le=20)
    force_inject: bool = Field(False, description="Skip should_inject check and always inject")


class ShouldInjectRequest(BaseModel):
    prompt: str = Field(..., description="Prompt to check")


# ----------------------------------------------------------------
# Global exception handler
# ----------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "message": str(exc)},
    )


# ----------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------

@app.on_event("startup")
async def _startup():
    """Pre-warm embedder + migrate first-person entity aliases on startup."""
    import asyncio
    from core import embedder

    # Pre-warm the embedding model in a thread so the first /memory/add is fast.
    # Without this, cold start on first request pings HuggingFace (~20s timeout)
    # and loads the model from disk (~5s) — totalling ~25s added latency.
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, embedder.warmup)
        logger.info("Embedder pre-warmed.")
    except Exception as e:
        logger.warning(f"Embedder warmup skipped: {e}")

    try:
        result = engine.migrate_self_entity()
        if result.get("renamed", 0) > 0:
            logger.info(f"Startup migration: {result}")
    except Exception as e:
        logger.warning(f"Startup migration skipped: {e}")


@app.get("/health")
async def health():
    """Health check. Also shows Ollama status."""
    from core.llm import is_ollama_running, OLLAMA_MODEL
    return {
        "status": "ok",
        "ollama": is_ollama_running(),
        "model": OLLAMA_MODEL,
        "version": "1.0.0",
    }


@app.post("/memory/add")
async def add_memory(req: AddRequest):
    """
    Add content to memory.
    Full pipeline: route → segment → extract → dedup → store → graph enrich.
    """
    try:
        result = engine.add(
            content=req.content,
            source_type=req.source_type,
            session_id=req.session_id,
            metadata=req.metadata,
        )
        return result

    except EmptyContentError:
        raise HTTPException(status_code=400, detail={
            "error": "EMPTY_CONTENT",
            "message": "Content cannot be empty.",
        })
    except InputTooLargeError as e:
        raise HTTPException(status_code=400, detail={
            "error": "CONTENT_TOO_LARGE",
            "message": f"Content too large: {e.actual} tokens (max 50,000).",
            "actual_tokens": e.actual,
        })
    except ValueError as e:
        msg = str(e)
        if "scanned image" in msg.lower():
            raise HTTPException(status_code=400, detail={
                "error": "PDF_SCANNED",
                "message": msg,
            })
        raise HTTPException(status_code=400, detail={
            "error": "INVALID_SOURCE_TYPE",
            "message": msg,
        })
    except Exception as e:
        error_str = str(e)
        if "LLM_UNAVAILABLE" in error_str:
            raise HTTPException(status_code=500, detail={
                "error": "LLM_UNAVAILABLE",
                "message": error_str,
                "fallback_used": False,
            })
        raise HTTPException(status_code=500, detail={
            "error": "STORE_WRITE_FAILED",
            "message": error_str,
            "fallback_used": False,
        })


@app.post("/memory/search")
async def search_memory(req: SearchRequest):
    """
    Retrieve relevant facts using hybrid scoring (FAISS + BM25 + Kuzu graph).
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail={
            "error": "EMPTY_QUERY",
            "message": "Query cannot be empty.",
        })
    result = engine.search(
        query=req.query,
        top_k=req.top_k,
        include_expired=req.include_expired,
        source_filter=req.source_filter,
        session_filter=req.session_filter,
    )
    return result


@app.post("/memory/augment")
async def augment_memory(req: AugmentRequest):
    """
    Middleware endpoint: decides if prompt needs context, fetches it, returns augmented prompt.
    """
    from core.augmenter import augment
    result = augment(req.prompt, top_k=req.top_k, force_inject=req.force_inject)
    return result


@app.post("/memory/should_inject")
async def should_inject(req: ShouldInjectRequest):
    """
    Lightweight check: does this prompt need memory context?
    Target: < 10ms (heuristic only, no LLM).
    """
    from core.augmenter import should_inject as _should_inject
    result = _should_inject(req.prompt)
    return result


@app.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str):
    """
    Delete a specific fact from all three stores simultaneously.
    """
    result = engine.delete(memory_id)
    if "error" in result and result["error"] == "MEMORY_NOT_FOUND":
        raise HTTPException(status_code=404, detail=result)
    return result


@app.get("/memory/graph")
async def get_graph(entity: str, hops: int = 2):
    """
    Return entity relationship subgraph from Kuzu graph store.
    """
    hops = min(max(hops, 1), 4)
    result = engine.get_graph(entity, hops)
    return result


@app.get("/memory/list")
async def list_memories(
    limit: int = 50,
    offset: int = 0,
    include_expired: bool = False,
    source_filter: Optional[str] = None,
    session_filter: Optional[str] = None,
):
    """
    List all stored memories with their memory_ids.
    Paginate with limit/offset. Sorted newest first.
    """
    engine._init_stores()
    conn = engine._sqlite._conn
    import sqlite3

    q = "SELECT memory_id, entity, attribute, value, confidence, source_type, session_id, timestamp, expired_at FROM memories WHERE 1=1"
    params = []

    if not include_expired:
        q += " AND expired_at IS NULL"
    if source_filter:
        q += " AND source_type = ?"
        params.append(source_filter)
    if session_filter:
        q += " AND session_id = ?"
        params.append(session_filter)

    q += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(q, params).fetchall()

    # Count must respect the same filters as the rows query
    count_q = "SELECT COUNT(*) FROM memories WHERE 1=1"
    count_params: list = []
    if not include_expired:
        count_q += " AND expired_at IS NULL"
    if source_filter:
        count_q += " AND source_type = ?"
        count_params.append(source_filter)
    if session_filter:
        count_q += " AND session_id = ?"
        count_params.append(session_filter)
    total = conn.execute(count_q, count_params).fetchone()[0]

    return {
        "memories": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ----------------------------------------------------------------
# Demo UI – served at /demo/  (must come LAST, after all API routes)
# Root fix: use _DEMO_DIR (Path.resolve absolute path) so this works
# regardless of what CWD uvicorn starts from.
# ----------------------------------------------------------------

@app.get("/ui")
async def ui_redirect():
    """Convenience redirect: /ui → /demo/index.html"""
    return RedirectResponse(url="/demo/index.html")

if _DEMO_DIR.is_dir():
    app.mount("/demo", StaticFiles(directory=str(_DEMO_DIR), html=True), name="demo")
