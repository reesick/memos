"""
core/augmenter.py – Phase 2 stub (functional passthrough)
Full implementation comes in Phase 2. This stub allows Phase 1 API
to expose /memory/augment and /memory/should_inject endpoints that
return valid responses without crashing.

should_inject():  Heuristic-only check (no LLM). Looks for memory
                  trigger phrases to decide if context injection is needed.
augment():        Fetches context via engine.search() and prepends it to
                  the prompt. A proper LLM-based injection decision and
                  formatting will be added in Phase 2.
"""

import time
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Phrases that signal the prompt likely needs memory context
MEMORY_TRIGGER_PHRASES = [
    "remember", "recall", "what did", "what was", "who is", "who was",
    "last time", "previously", "earlier", "before", "you know",
    "my ", "i told", "we discussed", "as i said",
]

CONTEXT_HEADER = "[Memory Context]\n"
CONTEXT_FOOTER = "\n[End of Memory Context]\n\n"


def should_inject(
    prompt: str,
    *,
    confidence_threshold: float = 0.5,
) -> dict:
    """
    Lightweight heuristic check: does this prompt need memory context?
    Target: < 10ms (no LLM, no embeddings).

    Returns:
        {"inject": bool, "confidence": float, "reason": str, "check_ms": int}
    """
    start = time.time()
    prompt_lower = prompt.lower()

    matched = [phrase for phrase in MEMORY_TRIGGER_PHRASES if phrase in prompt_lower]

    if matched:
        confidence = min(0.5 + len(matched) * 0.1, 1.0)
        inject = confidence >= confidence_threshold
        reason = f"Trigger phrases found: {matched[:3]}"
    else:
        confidence = 0.1
        inject = False
        reason = "No memory trigger phrases detected"

    check_ms = int((time.time() - start) * 1000)
    return {
        "inject": inject,
        "confidence": round(confidence, 3),
        "reason": reason,
        "check_ms": check_ms,
    }


def augment(
    prompt: str,
    *,
    top_k: int = 3,
    force_inject: bool = False,
) -> dict:
    """
    Augment a prompt with relevant memory context.
    Phase 1 behaviour: always fetches context via engine.search(),
    injects if should_inject() returns True or force_inject=True.
    Phase 2 will add smarter injection formatting and session awareness.

    Returns:
        {
          "augmented_prompt": str,
          "injected": bool,
          "context_added": list of memory_ids used,
          "injection_reason": str,
          "augment_ms": int,
        }
    """
    start = time.time()

    # Decide whether to inject
    if force_inject:
        inject = True
        injection_reason = "force_inject=True"
    else:
        check = should_inject(prompt)
        inject = check["inject"]
        injection_reason = check["reason"]

    if not inject:
        return {
            "augmented_prompt": prompt,
            "injected": False,
            "context_added": [],
            "injection_reason": injection_reason,
            "augment_ms": int((time.time() - start) * 1000),
        }

    # Fetch context
    try:
        import core.engine as engine
        search_result = engine.search(prompt, top_k=top_k)
        context = search_result.get("context", "")
        memory_ids = [r["memory_id"] for r in search_result.get("results", [])]
    except Exception as e:
        logger.warning(f"Augmenter: search failed: {e}")
        context = ""
        memory_ids = []

    if context and context != "No relevant memory found.":
        augmented = CONTEXT_HEADER + context + CONTEXT_FOOTER + prompt
        injected = True
    else:
        augmented = prompt
        injected = False
        injection_reason = "No relevant memory found for this prompt"

    return {
        "augmented_prompt": augmented,
        "injected": injected,
        "context_added": memory_ids,
        "injection_reason": injection_reason,
        "augment_ms": int((time.time() - start) * 1000),
    }
