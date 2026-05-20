"""
core/engine.py – Main orchestrator (ONLY public interface)
add() and search() are the ONLY two public methods.
Everything else is private. api/main.py calls ONLY this file.

Startup: initializes all three stores once. They persist across requests.
"""

import os
import time
import logging
import uuid
from typing import List, Dict, Optional, Any

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------
# Store singletons – initialized once on engine startup
# ----------------------------------------------------------------
_sqlite: Any = None
_faiss: Any = None
_kuzu: Any = None
_initialized = False


def _init_stores():
    global _sqlite, _faiss, _kuzu, _initialized
    if _initialized:
        return

    db_path = os.getenv("DB_PATH", "./data/")
    # Normalize path
    db_path = os.path.abspath(db_path)
    os.makedirs(db_path, exist_ok=True)

    sqlite_file = os.path.join(db_path, "memoryos.db")
    faiss_file = os.path.join(db_path, "faiss.index")
    kuzu_dir = os.path.join(db_path, "kuzu_db")

    from core.sqlite_store import SqliteStore
    from core.faiss_store import FaissStore
    from core.kuzu_store import KuzuStore

    _sqlite = SqliteStore(sqlite_file)
    _faiss = FaissStore(faiss_file)
    _kuzu = KuzuStore(kuzu_dir)

    # Check if FAISS needs rebuild (e.g., after crash)
    if _faiss.total() == 0 and _sqlite.count() > 0:
        _rebuild_faiss()

    _initialized = True
    logger.info("Engine: all stores initialized.")


def _rebuild_faiss():
    """Rebuild FAISS index from SQLite records. Called on startup if index missing."""
    from core import embedder
    logger.warning("Engine: FAISS index empty, rebuilding from SQLite...")
    records = _sqlite.get_all_for_rebuild()
    rebuild_data = []
    for r in records:
        vec = embedder.encode(r["value"])
        rebuild_data.append((r["memory_id"], vec))
    _faiss.rebuild_from_records(rebuild_data)
    logger.info(f"Engine: FAISS rebuilt with {len(rebuild_data)} vectors.")


def _new_session_id() -> str:
    return f"sess_{int(time.time())}"


# First-person aliases the extractor emits when it doesn't know the speaker's name
_SELF_ALIASES = {'i', 'me', 'my', 'myself', 'the user', 'user', 'speaker', 'unknown'}


def _lookup_user_name(sqlite) -> Optional[str]:
    """Check SQLite for a stored name fact whose entity is a first-person alias."""
    for alias in list(_SELF_ALIASES) + ['I', 'Me', 'User', 'Speaker']:
        row = sqlite.find_by_entity_attribute(alias, 'name')
        if row:
            return row['value'].strip()
    return None


def _resolve_self_entity(facts: List, sqlite) -> List:
    """
    Replace first-person entity references ('I', 'me', 'myself' …) with the
    speaker's real name so facts are indexed under a stable entity key.

    Resolution order:
      1. Current batch contains a name declaration  → use that value
      2. SQLite already has a name fact stored       → use that value
      3. No name known yet                          → leave facts unchanged
    """
    from core.extractor import Fact as ExtractedFact

    # 1. Check the current batch first (handles "My name is Sri" in the same message)
    user_name: Optional[str] = None
    for fact in facts:
        if fact.attribute == 'name' and fact.entity.lower().strip() in _SELF_ALIASES:
            user_name = fact.value.strip()
            break

    # 2. Fall back to the stored name
    if not user_name:
        user_name = _lookup_user_name(sqlite)

    if not user_name:
        return facts

    resolved = []
    for fact in facts:
        if fact.entity.lower().strip() in _SELF_ALIASES:
            fact = fact.model_copy(update={'entity': user_name})
        resolved.append(fact)
    return resolved


# ================================================================
# PUBLIC API
# ================================================================

def add(
    content: str,
    source_type: str = "text",
    session_id: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> Dict:
    """
    Add content to memory. Full pipeline:
    route → segment → extract → dedup → resolve conflicts → store → enrich graph.

    Returns summary dict:
        facts_extracted, facts_added, facts_updated, facts_noop, memory_ids, processing_ms
    """
    _init_stores()
    start = time.time()

    session_id = session_id or _new_session_id()
    metadata = metadata or {}

    # ---- Step 1: Route and segment ----
    from core.input_router import route, EmptyContentError, InputTooLargeError, InvalidSourceTypeError
    segments = route(content, source_type, metadata)

    # ---- Step 2: Extract facts ----
    from core.extractor import extract_all
    facts = extract_all(segments)

    # ---- Step 2b: Resolve first-person entities → real name ----
    facts = _resolve_self_entity(facts, _sqlite)

    # ---- Step 3: Dedup ----
    from core.deduplicator import deduplicate, DedupAction
    dedup_results = deduplicate(facts, _sqlite)

    # ---- Step 4: Store and resolve conflicts ----
    from core import embedder
    from core.conflict_resolver import resolve, ConflictAction
    from core import graph_enricher

    memory_ids = []
    stats = {"added": 0, "updated": 0, "noop": 0}
    doc_id = metadata.get("doc_id")

    for result in dedup_results:
        fact = result.new_fact

        if result.action == DedupAction.ADD:
            mid = _sqlite.insert(
                entity=fact.entity,
                attribute=fact.attribute,
                value=fact.value,
                confidence=fact.confidence,
                source_type=source_type,
                doc_id=doc_id,
                session_id=session_id,
                raw_chunk=content[:500],  # Store truncated chunk for BM25
            )
            vec = embedder.encode(fact.value)
            _faiss.add_vector(mid, vec)
            graph_enricher.enrich_add(
                mid, fact.entity, fact.attribute, fact.value,
                fact.confidence, source_type, doc_id, _kuzu
            )
            memory_ids.append(mid)
            stats["added"] += 1

        elif result.action == DedupAction.NOOP:
            # Refresh timestamp so recency score stays accurate
            if result.existing_id:
                try:
                    _sqlite.refresh_timestamp(result.existing_id)
                except Exception as e:
                    logger.warning(f"Could not refresh timestamp for {result.existing_id}: {e}")
            stats["noop"] += 1

        elif result.action == DedupAction.CONFLICT:
            conflict_result = resolve(
                new_value=fact.value,
                existing_value=result.existing_value,
                existing_memory_id=result.existing_id,
            )

            if conflict_result.action == ConflictAction.UPDATE:
                _sqlite.update_expired(result.existing_id)
                _faiss.delete_vector(result.existing_id)
                new_mid = _sqlite.insert(
                    entity=fact.entity,
                    attribute=fact.attribute,
                    value=fact.value,
                    confidence=fact.confidence,
                    source_type=source_type,
                    doc_id=doc_id,
                    session_id=session_id,
                    raw_chunk=content[:500],
                )
                vec = embedder.encode(fact.value)
                _faiss.add_vector(new_mid, vec)
                graph_enricher.enrich_update(
                    result.existing_id, new_mid,
                    fact.entity, fact.attribute, fact.value,
                    fact.confidence, source_type, doc_id, _kuzu
                )
                memory_ids.append(new_mid)
                stats["updated"] += 1

            elif conflict_result.action == ConflictAction.DELETE:
                _sqlite.update_expired(result.existing_id)
                _faiss.delete_vector(result.existing_id)
                graph_enricher.enrich_delete(result.existing_id, fact.entity, _kuzu)
                stats["updated"] += 1  # Count DELETE as UPDATE for stats

            elif conflict_result.action == ConflictAction.ADD:
                # Both coexist
                mid = _sqlite.insert(
                    entity=fact.entity,
                    attribute=fact.attribute,
                    value=fact.value,
                    confidence=fact.confidence,
                    source_type=source_type,
                    doc_id=doc_id,
                    session_id=session_id,
                    raw_chunk=content[:500],
                )
                vec = embedder.encode(fact.value)
                _faiss.add_vector(mid, vec)
                graph_enricher.enrich_add(
                    mid, fact.entity, fact.attribute, fact.value,
                    fact.confidence, source_type, doc_id, _kuzu
                )
                memory_ids.append(mid)
                stats["added"] += 1

            else:  # NOOP
                stats["noop"] += 1

    processing_ms = int((time.time() - start) * 1000)

    return {
        "status": "success",
        "facts_extracted": len(facts),
        "facts_added": stats["added"],
        "facts_updated": stats["updated"],
        "facts_noop": stats["noop"],
        "memory_ids": memory_ids,
        "processing_ms": processing_ms,
    }


def search(
    query: str,
    top_k: int = 5,
    include_expired: bool = False,
    source_filter: Optional[str] = None,
    session_filter: Optional[str] = None,
) -> Dict:
    """
    Retrieve relevant facts using hybrid scoring (FAISS + BM25 + Kuzu).

    Returns:
        results list, assembled context string, graph bridge count, cross_source flag, timing.
    """
    _init_stores()
    start = time.time()

    from core.retriever import retrieve

    results, cross_source, graph_bridges = retrieve(
        query=query,
        faiss_store=_faiss,
        sqlite_store=_sqlite,
        kuzu_store=_kuzu,
        top_k=min(top_k, 20),
        include_expired=include_expired,
        source_filter=source_filter,
        session_filter=session_filter,
    )

    context = _assemble_context(results, include_expired)
    retrieval_ms = int((time.time() - start) * 1000)

    # Format results for API response
    formatted = []
    for r in results:
        formatted.append({
            "memory_id": r.get("memory_id"),
            "entity": r.get("entity"),
            "attribute": r.get("attribute"),
            "value": r.get("value"),
            "score": r.get("score"),
            "source_type": r.get("source_type"),
            "timestamp": r.get("timestamp"),
            "contradictory_fact": r.get("contradictory_fact", False),
        })

    return {
        "results": formatted,
        "context": context,
        "graph_bridges": graph_bridges,
        "cross_source": cross_source,
        "retrieval_ms": retrieval_ms,
    }


def migrate_self_entity() -> Dict:
    """
    One-time migration: rename all first-person entity aliases ('I', 'me' …)
    to the user's real name across SQLite + Kuzu.
    Call this after the server starts if old 'I' facts exist.
    """
    _init_stores()
    user_name = _lookup_user_name(_sqlite)
    if not user_name:
        return {"status": "skipped", "reason": "No user name found in DB yet"}

    total = 0
    for alias in list(_SELF_ALIASES) + ['I', 'Me', 'User', 'Speaker']:
        if alias.lower() == user_name.lower():
            continue
        count = _sqlite.rename_entity(alias, user_name)
        if count:
            total += count
            try:
                from core import graph_enricher
                graph_enricher.rename_entity(_kuzu, alias, user_name)
            except Exception:
                pass  # Kuzu rename is best-effort; rebuild handles it

    logger.info(f"migrate_self_entity: renamed {total} facts → '{user_name}'")
    return {"status": "done", "renamed": total, "user_name": user_name}


def delete(memory_id: str) -> Dict:
    """Delete a specific fact from all three stores."""
    _init_stores()

    record = _sqlite.get_by_id(memory_id)
    if not record:
        return {"error": "MEMORY_NOT_FOUND", "memory_id": memory_id}

    removed_from = []
    _sqlite.delete(memory_id)
    removed_from.append("sqlite")

    try:
        _faiss.delete_vector(memory_id)
        removed_from.append("faiss")
    except Exception:
        pass

    try:
        from core import graph_enricher
        graph_enricher.enrich_delete(memory_id, record["entity"], _kuzu)
        removed_from.append("kuzu")
    except Exception:
        pass

    return {"status": "deleted", "memory_id": memory_id, "removed_from": removed_from}


def get_graph(entity: str, hops: int = 2) -> Dict:
    """Return entity relationship subgraph from Kuzu."""
    _init_stores()
    hops = min(hops, 4)
    graph = _kuzu.get_subgraph(entity, hops)
    return {
        "nodes": graph["nodes"],
        "edges": graph["edges"],
        "total_nodes": len(graph["nodes"]),
        "total_edges": len(graph["edges"]),
    }


# ----------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------

MAX_CONTEXT_TOKENS = 500


def _assemble_context(results: List[Dict], include_expired: bool = False) -> str:
    """
    Assemble a clean, bulleted context string from top-k results.
    Format: plain text bullets, most recent first, max ~500 tokens.
    """
    if not results:
        return "No relevant memory found."

    lines = []
    token_budget = MAX_CONTEXT_TOKENS

    for r in results:
        entity = r.get("entity", "")
        attr = r.get("attribute", "")
        value = r.get("value", "")
        is_expired = bool(r.get("expired_at"))
        is_contradiction = r.get("contradictory_fact", False)

        if not include_expired and is_expired:
            continue

        line = f"• {entity} {attr}: {value}"

        if is_expired:
            line += " [expired]"
        if is_contradiction:
            line += " ⚠ [may have changed]"

        # Rough token count
        token_budget -= len(line) // 4
        if token_budget <= 0:
            break

        lines.append(line)

    return "\n".join(lines) if lines else "No relevant memory found."
