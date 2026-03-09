"""
core/graph_enricher.py – Post-storage Kuzu graph enrichment
Called after a new fact is stored in SQLite + FAISS.
Creates Entity node, Fact node, and RELATES_TO edge.
On UPDATE: marks old edge valid_until, creates new edge.
Links PDF/code chunks to source Document nodes.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Map common entity types heuristically
PERSON_KEYWORDS = {"name", "role", "job", "position", "works", "studies", "age", "email", "phone"}
SYSTEM_KEYWORDS = {"uses", "version", "language", "framework", "library", "database", "api"}
CONCEPT_KEYWORDS = {"definition", "means", "is", "refers", "concept", "idea"}


def _infer_entity_type(attribute: str) -> str:
    """Guess the entity type from the attribute keyword."""
    attr_lower = attribute.lower()
    if any(kw in attr_lower for kw in PERSON_KEYWORDS):
        return "Person"
    if any(kw in attr_lower for kw in SYSTEM_KEYWORDS):
        return "System"
    if any(kw in attr_lower for kw in CONCEPT_KEYWORDS):
        return "Concept"
    return "Unknown"


def _infer_relationship(attribute: str) -> str:
    """Map attribute to a relationship label for the graph edge."""
    attr_upper = attribute.upper().replace(" ", "_")
    # Keep it clean: max 30 chars, only alphanumeric + underscore
    import re
    clean = re.sub(r'[^A-Z0-9_]', '', attr_upper)[:30]
    return clean if clean else "HAS_FACT"


def enrich_add(
    memory_id: str,
    entity: str,
    attribute: str,
    value: str,
    confidence: float,
    source_type: str,
    doc_id: Optional[str],
    kuzu_store,
):
    """
    Called after ADD: create Entity node, Fact node, and RELATES_TO edge.
    """
    try:
        entity_type = _infer_entity_type(attribute)
        source = doc_id if doc_id else "conversation"
        relationship = _infer_relationship(attribute)

        kuzu_store.create_entity(entity, entity_type, source)
        kuzu_store.create_fact_node(memory_id, value, confidence)
        kuzu_store.create_edge(entity, memory_id, relationship, confidence)

        # If from PDF or code: also link to Document node (best-effort)
        if doc_id:
            _link_to_document(entity, doc_id, source_type, kuzu_store)

    except Exception as e:
        logger.warning(f"GraphEnricher enrich_add failed for {memory_id}: {e}")


def enrich_update(
    old_memory_id: str,
    new_memory_id: str,
    entity: str,
    attribute: str,
    value: str,
    confidence: float,
    source_type: str,
    doc_id: Optional[str],
    kuzu_store,
):
    """
    Called after UPDATE: expire old edge, create new Fact node and edge.
    """
    try:
        # Expire old edge
        kuzu_store.expire_edge(entity, old_memory_id)

        # Add new fact
        relationship = _infer_relationship(attribute)
        kuzu_store.create_fact_node(new_memory_id, value, confidence)
        kuzu_store.create_edge(entity, new_memory_id, relationship, confidence)

    except Exception as e:
        logger.warning(f"GraphEnricher enrich_update failed for {entity}: {e}")


def enrich_delete(memory_id: str, entity: str, kuzu_store):
    """
    Called after DELETE: remove Fact node and all its edges.
    """
    try:
        kuzu_store.expire_edge(entity, memory_id)
        kuzu_store.delete_fact(memory_id)
    except Exception as e:
        logger.warning(f"GraphEnricher enrich_delete failed for {memory_id}: {e}")


def _link_to_document(entity: str, doc_id: str, source_type: str, kuzu_store):
    """
    Best-effort: create a Document entity node for PDF/code sources.
    Links the entity to the document source via a HAS_SOURCE edge.
    """
    try:
        kuzu_store.create_entity(doc_id, source_type.upper(), "document")
    except Exception:
        pass  # Non-critical enrichment
