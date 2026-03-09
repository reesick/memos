"""
core/scorer.py – Hybrid scoring formula
Merges FAISS vector score + BM25 keyword score + recency weight.
Pure math – no LLM, no I/O.
"""

import math
import time
from typing import List, Dict, Tuple


# Default weights (standard query)
W_VECTOR = 0.6
W_BM25   = 0.3
W_RECENCY = 0.1

# Short query weights (<3 words)
W_VECTOR_SHORT = 0.4
W_BM25_SHORT   = 0.5
W_RECENCY_SHORT = 0.1

# Recency decay constant: e^(-k * days). k=0.05 → 2-week-old fact scores ~0.75
RECENCY_DECAY_K = 0.05


def _recency_weight(timestamp: int) -> float:
    """
    Exponential decay based on age in days.
    Today = 1.0. 14 days ago ≈ 0.75. Never reaches 0.
    """
    now = int(time.time())
    days_old = max(0, (now - timestamp) / 86400)
    return math.exp(-RECENCY_DECAY_K * days_old)


def _normalize_bm25(scores: Dict[str, float]) -> Dict[str, float]:
    """
    Root fix: log+softmax normalization for BM25 scores.
    FTS5 rank values are negative (more negative = better).
    We negate to get positive values, apply log1p to compress extremes,
    then softmax so relative magnitude is preserved (not collapsed to 0/1).
    This prevents a single very-good BM25 match from scoring 1.0 while
    a slightly-worse match drops to 0.0, which distorted rankings.
    """
    if not scores:
        return {}

    # Higher positive value = better match (after negating FTS5 rank)
    pos = {mid: abs(v) for mid, v in scores.items()}

    # Log-compress to reduce extreme outlier effect
    log_pos = {mid: math.log1p(v) for mid, v in pos.items()}

    # Softmax for proper probability-style distribution
    max_val = max(log_pos.values()) if log_pos else 0.0
    exp_vals = {mid: math.exp(v - max_val) for mid, v in log_pos.items()}
    total = sum(exp_vals.values())

    if total == 0:
        return {mid: 0.0 for mid in scores}

    return {mid: v / total for mid, v in exp_vals.items()}


def is_short_query(query: str) -> bool:
    """Detect if query is short (<3 words). Short queries have noisy embeddings."""
    return len(query.strip().split()) < 3


def merge_scores(
    query: str,
    faiss_results: List[Tuple[str, float]],    # [(memory_id, vector_score)]
    bm25_results: List[Dict],                   # [{memory_id, rank, ...}]
    all_records: Dict[str, Dict],               # memory_id → full SQLite record
    top_k: int = 5,
) -> List[Dict]:
    """
    Merge FAISS, BM25, and recency scores into a single ranked list.

    Args:
        query: Original search query (used to detect short queries)
        faiss_results: [(memory_id, normalized_vector_score)]
        bm25_results: [{memory_id, rank}] from FTS5 (lower rank = better)
        all_records: Full fact records from SQLite, keyed by memory_id
        top_k: Number of results to return

    Returns:
        Sorted list of fact dicts with 'score' field added.
    """
    short = is_short_query(query)
    wv = W_VECTOR_SHORT if short else W_VECTOR
    wb = W_BM25_SHORT if short else W_BM25
    wr = W_RECENCY_SHORT if short else W_RECENCY

    # Build lookup dicts
    faiss_map: Dict[str, float] = {mid: score for mid, score in faiss_results}

    # BM25: FTS5 rank is negative (more negative = better).
    # _normalize_bm25 handles sign flip + log-softmax normalization.
    bm25_raw = {r["memory_id"]: r.get("rank", 0.0) for r in bm25_results}
    bm25_map: Dict[str, float] = _normalize_bm25(bm25_raw) if bm25_raw else {}

    # Collect all candidate memory_ids
    candidates = set(faiss_map.keys()) | set(bm25_map.keys())

    scored = []
    for mid in candidates:
        record = all_records.get(mid)
        if not record:
            continue  # Skip if no SQLite record (shouldn't happen)

        v_score = faiss_map.get(mid, 0.0)
        b_score = bm25_map.get(mid, 0.0)
        r_score = _recency_weight(record.get("timestamp", 0))

        hybrid = wv * v_score + wb * b_score + wr * r_score

        result = dict(record)
        result["score"] = round(hybrid, 4)
        result["vector_score"] = round(v_score, 4)
        result["bm25_score"] = round(b_score, 4)
        result["recency_score"] = round(r_score, 4)
        scored.append(result)

    # Sort by hybrid score DESC
    scored.sort(key=lambda x: x["score"], reverse=True)

    # Diversity cap: max 3 results from same session_id in top-5
    final = _apply_diversity(scored, max_per_session=3)

    return final[:top_k]


def _apply_diversity(scored: List[Dict], max_per_session: int = 3) -> List[Dict]:
    """
    Enforce diversity: no more than max_per_session results from the same session.
    Prevents one noisy session dominating results.
    """
    session_count: Dict[str, int] = {}
    result = []
    overflow = []

    for item in scored:
        sid = item.get("session_id") or "__none__"
        count = session_count.get(sid, 0)
        if count < max_per_session:
            result.append(item)
            session_count[sid] = count + 1
        else:
            overflow.append(item)

    return result + overflow
