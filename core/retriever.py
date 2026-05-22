"""
core/retriever.py – Hybrid retrieval orchestrator
Runs FAISS + BM25 + Kuzu graph queries in parallel threads.
Passes results to scorer.py for final merge.
Target: p50 < 100ms, p95 < 300ms.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from typing import List, Dict, Optional, Tuple

from core import embedder, scorer

logger = logging.getLogger(__name__)

QUERY_TIMEOUT_SEC = 0.5   # Hard timeout per store query thread


def retrieve(
    query: str,
    faiss_store,
    sqlite_store,
    kuzu_store,
    top_k: int = 5,
    include_expired: bool = False,
    source_filter: Optional[str] = None,
    session_filter: Optional[str] = None,
) -> Tuple[List[Dict], bool, int]:
    """
    Orchestrates hybrid retrieval.

    Returns:
        (results, cross_source, graph_bridges)
        results: List of scored fact dicts sorted by hybrid score
        cross_source: True if facts from multiple sources were found
        graph_bridges: Number of cross-source bridges found in Kuzu
    """
    start = time.time()

    # Embed the query locally (no LLM)
    query_vec = embedder.encode(query)

    # When a session_filter is active, session facts are a tiny fraction of the total
    # FAISS index. Over-sample aggressively so they survive the session pruning step.
    faiss_top_k = top_k * 2
    if session_filter:
        faiss_top_k = min(top_k * 20, max(faiss_store.total(), top_k * 2))

    # ----------------------------------------------------------------
    # Parallel queries: FAISS + BM25 + graph traversal
    # ----------------------------------------------------------------
    faiss_results: List[Tuple[str, float]] = []
    bm25_results: List[Dict] = []
    graph_results: List[Dict] = []
    all_records: Dict[str, Dict] = {}

    def _faiss_query():
        return faiss_store.search(query_vec, top_k=faiss_top_k)

    def _bm25_query():
        return sqlite_store.bm25_search(
            query, top_k=top_k * 2,
            include_expired=include_expired,
            source_filter=source_filter,
            session_filter=session_filter,
        )

    def _graph_query():
        """Extract named entity from query for graph traversal."""
        words = query.strip().split()
        if not words:
            return []
        # Prefer the first capitalized word; normalize to lowercase to match stored entities.
        entity = next((w for w in words if w[0].isupper()), words[0]).lower()
        return kuzu_store.traverse(entity, hops=2, include_expired=include_expired)

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_faiss_query): "faiss",
            executor.submit(_bm25_query): "bm25",
            executor.submit(_graph_query): "graph",
        }
        for future in as_completed(futures, timeout=QUERY_TIMEOUT_SEC * 3):
            name = futures[future]
            try:
                result = future.result(timeout=QUERY_TIMEOUT_SEC)
                if name == "faiss":
                    faiss_results = result
                elif name == "bm25":
                    bm25_results = result
                elif name == "graph":
                    graph_results = result
            except TimeoutError:
                logger.warning(f"Retriever: {name} query timed out")
            except Exception as e:
                logger.warning(f"Retriever: {name} query failed: {e}")

    # ----------------------------------------------------------------
    # Fetch full records from SQLite for all candidate memory_ids
    # ----------------------------------------------------------------
    candidate_ids = set()
    for mid, _ in faiss_results:
        candidate_ids.add(mid)
    for row in bm25_results:
        candidate_ids.add(row["memory_id"])
    for row in graph_results:
        candidate_ids.add(row["memory_id"])

    for mid in candidate_ids:
        record = sqlite_store.get_by_id(mid)
        if record:
            if not include_expired and record.get("expired_at"):
                continue  # Skip expired
            if source_filter and record.get("source_type") != source_filter:
                continue
            if session_filter and record.get("session_id") != session_filter:
                continue
            all_records[mid] = record

    # ----------------------------------------------------------------
    # Score merge
    # ----------------------------------------------------------------
    results = scorer.merge_scores(
        query=query,
        faiss_results=faiss_results,
        bm25_results=bm25_results,
        all_records=all_records,
        top_k=top_k,
    )

    # ----------------------------------------------------------------
    # Cross-source bridge detection
    # ----------------------------------------------------------------
    result_ids = [r["memory_id"] for r in results]
    bridges = kuzu_store.bridge_detect(result_ids)
    cross_source = len(bridges) > 0

    elapsed_ms = int((time.time() - start) * 1000)
    logger.debug(f"Retriever: {len(results)} results in {elapsed_ms}ms")

    # Check for contradictions in top-k
    _flag_contradictions(results)

    return results, cross_source, len(bridges)


def _flag_contradictions(results: List[Dict]):
    """
    Detect entity+attribute overlap in top-k results.
    Flags result with contradictory_fact=True if another result has same entity+attribute.
    """
    seen: Dict[str, str] = {}  # (entity, attribute) → memory_id
    for item in results:
        key = (item.get("entity", ""), item.get("attribute", ""))
        if key in seen:
            item["contradictory_fact"] = True
        else:
            seen[key] = item.get("memory_id", "")
            item["contradictory_fact"] = False
