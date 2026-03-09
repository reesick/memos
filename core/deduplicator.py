"""
core/deduplicator.py – Semantic fact deduplication

Two-layer dedup strategy:
  Layer 1 (fast, O(1)): Exact entity + attribute string match.
  Layer 2 (semantic, O(n_entity_facts)): If no exact match, compare the incoming
          attribute against all existing attributes for the same entity using
          embedding cosine similarity. If similarity > SEMANTIC_THRESHOLD, treat
          as the same attribute with a different name → NOOP or CONFLICT.

This prevents "technology preference" and "preferred_technology" from both being
stored when they clearly mean the same thing. The Fact.normalize_attribute validator
in extractor.py handles obvious cases (snake_case normalization), but LLMs can still
produce semantically equivalent but lexically different strings. This layer catches
those by comparing embeddings rather than strings.

Returns: ADD (new), NOOP (exact or semantic duplicate, same value), or CONFLICT
         (exact or semantic duplicate, different value → needs LLM resolution).
"""

import logging
import numpy as np
from enum import Enum
from typing import List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Cosine similarity threshold for "same attribute" judgment.
# 0.82 chosen empirically: "technology preference" ≈ "preferred_technology" > 0.82
# "role" and "employer" < 0.82 (genuinely different attributes).
SEMANTIC_THRESHOLD = 0.82


class DedupAction(str, Enum):
    ADD = "ADD"
    NOOP = "NOOP"
    CONFLICT = "CONFLICT"
    SKIP = "SKIP"


@dataclass
class DedupResult:
    action: DedupAction
    new_fact: object                # Fact from extractor
    existing_id: Optional[str]      # memory_id of existing fact (if any)
    existing_value: Optional[str]   # value of existing fact (if any)
    matched_attribute: Optional[str] = None   # actual stored attribute name if semantic match


def deduplicate(facts: List, sqlite_store) -> List[DedupResult]:
    """
    Deduplicate a list of extracted Facts against the SQLite store.

    Rules (from PRD 9.2 + semantic extension):
    - entity+attribute exact match, SAME value      → NOOP (refresh timestamp)
    - entity+attribute exact match, DIFFERENT value → CONFLICT → conflict_resolver
    - No exact match, semantic attribute sim > 0.82 → same logic (NOOP or CONFLICT)
      with the matched attribute name used for the conflict check
    - No match at all                               → ADD

    Args:
        facts: List of Fact objects from extractor.py
        sqlite_store: Initialized SqliteStore instance.

    Returns:
        List of DedupResult, one per input fact.
    """
    results = []

    for fact in facts:

        # ── Layer 1: fast exact attribute match ──────────────────────────────
        existing = sqlite_store.find_by_entity_attribute(fact.entity, fact.attribute)

        if existing is not None:
            results.append(_make_result(fact, existing, fact.attribute))
            continue

        # ── Layer 2: semantic attribute similarity ────────────────────────────
        entity_facts = sqlite_store.get_all_for_entity(fact.entity)

        if entity_facts:
            best_match, best_sim = _find_semantic_match(
                fact.attribute, entity_facts
            )
            if best_match is not None:
                logger.info(
                    f"Semantic dedup: '{fact.attribute}' ~ '{best_match['attribute']}' "
                    f"(sim={best_sim:.3f}) for entity '{fact.entity}'"
                )
                results.append(
                    _make_result(fact, best_match, matched_attribute=best_match["attribute"])
                )
                continue

        # ── No match: new fact ────────────────────────────────────────────────
        results.append(DedupResult(
            action=DedupAction.ADD,
            new_fact=fact,
            existing_id=None,
            existing_value=None,
        ))

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_result(fact, existing: dict, matched_attribute: str = "") -> DedupResult:
    """Create NOOP or CONFLICT result given an existing matching record."""
    existing_id = existing["memory_id"]
    existing_value = existing["value"]

    if _normalize(fact.value) == _normalize(existing_value):
        try:
            # Reach into the sqlite store via the existing record's store reference
            # (sqlite_store is not passed here — refresh is done by engine.py after NOOP)
            pass
        except Exception:
            pass
        return DedupResult(
            action=DedupAction.NOOP,
            new_fact=fact,
            existing_id=existing_id,
            existing_value=existing_value,
            matched_attribute=matched_attribute,
        )
    else:
        return DedupResult(
            action=DedupAction.CONFLICT,
            new_fact=fact,
            existing_id=existing_id,
            existing_value=existing_value,
            matched_attribute=matched_attribute,
        )


def _find_semantic_match(
    attribute: str,
    entity_facts: List[dict],
) -> tuple:
    """
    Find the entity fact whose attribute is semantically closest to `attribute`.
    Uses embedder.encode() for cosine similarity.

    Returns (best_matching_fact_dict, similarity) or (None, 0.0).
    Only active (non-expired) facts are candidates.
    """
    try:
        from core.embedder import encode

        query_vec = encode(attribute)
        best_sim = 0.0
        best_fact = None

        for ef in entity_facts:
            if ef.get("expired_at") is not None:
                continue  # Skip superseded facts
            stored_attr = ef.get("attribute", "")
            if not stored_attr:
                continue
            stored_vec = encode(stored_attr)
            sim = _cosine(query_vec, stored_vec)
            if sim > best_sim:
                best_sim = sim
                best_fact = ef

        if best_sim >= SEMANTIC_THRESHOLD:
            return best_fact, best_sim

        return None, 0.0

    except Exception as e:
        logger.warning(f"Semantic dedup failed (falling back to ADD): {e}")
        return None, 0.0


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two numpy vectors. Safe against zero-vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _normalize(value: str) -> str:
    """Normalize a fact value for comparison: lowercase, strip whitespace."""
    return value.lower().strip()


def _is_negation(value: str) -> bool:
    """
    Detect if a value is an explicit negation (DELETE candidate).
    e.g. "no longer works at X", "not using Y anymore", "left Z"
    """
    negation_phrases = [
        "no longer", "not anymore", "stopped", "left", "quit",
        "removed", "deleted", "cancelled", "doesn't", "does not",
        "is not", "isn't", "never"
    ]
    return any(phrase in value.lower() for phrase in negation_phrases)
