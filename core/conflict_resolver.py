"""
core/conflict_resolver.py – LLM-driven conflict resolution
Called ONLY when deduplicator finds entity+attribute match with different value.
Sends both facts to Ollama and gets back: ADD / UPDATE / DELETE / NOOP.
"""

import logging
from enum import Enum
from typing import List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ConflictAction(str, Enum):
    ADD = "ADD"        # New fact coexists with old (e.g., two valid phone numbers)
    UPDATE = "UPDATE"  # New fact replaces old (role changed, city moved)
    DELETE = "DELETE"  # New fact explicitly negates old
    NOOP = "NOOP"      # Cannot decide, keep both, log warning


@dataclass
class ConflictResult:
    action: ConflictAction
    memory_id_to_expire: str   # Existing fact's memory_id
    reason: str                # LLM's explanation


CONFLICT_PROMPT = """You are resolving a memory conflict. Two facts describe the same entity and attribute but have different values.

Existing fact: "{existing_value}"
New fact: "{new_value}"

Decide the correct action:
- UPDATE: The new fact replaces the old (e.g., person changed job, moved cities)
- ADD: Both facts are valid simultaneously (e.g., person has two phone numbers, multiple skills)
- DELETE: The new fact explicitly negates or invalidates the old (e.g., "no longer works there")
- NOOP: Cannot determine which is correct; keep both

Reply with EXACTLY this JSON (no other text):
{{"action": "UPDATE|ADD|DELETE|NOOP", "reason": "one sentence explanation"}}"""


def resolve(
    new_value: str,
    existing_value: str,
    existing_memory_id: str,
) -> ConflictResult:
    """
    Ask the LLM to resolve a single conflict.
    Returns ConflictResult with the action and which memory_id to expire.
    Falls back to ADD (both coexist) if LLM fails.
    """
    from core import llm

    prompt = CONFLICT_PROMPT.format(
        existing_value=existing_value,
        new_value=new_value,
    )

    try:
        raw = llm.call(prompt, temperature=0.0)
        parsed = llm.call_json(prompt)

        if parsed and isinstance(parsed, dict):
            action_str = parsed.get("action", "ADD").upper()
            reason = parsed.get("reason", "LLM decision")
            try:
                action = ConflictAction(action_str)
            except ValueError:
                action = ConflictAction.ADD
                reason = f"Invalid action from LLM: {action_str}. Defaulted to ADD."

            return ConflictResult(
                action=action,
                memory_id_to_expire=existing_memory_id,
                reason=reason,
            )

    except Exception as e:
        logger.warning(f"ConflictResolver: LLM call failed: {e}. Defaulting to ADD.")

    # Safe fallback: ADD (both coexist, user can delete old manually)
    return ConflictResult(
        action=ConflictAction.ADD,
        memory_id_to_expire=existing_memory_id,
        reason="LLM unavailable or returned invalid response. Both facts coexist.",
    )


def resolve_batch(conflicts: List[Tuple[str, str, str]]) -> List[ConflictResult]:
    """
    Resolve multiple conflicts.
    Each tuple: (new_value, existing_value, existing_memory_id)
    """
    return [resolve(nv, ev, mid) for nv, ev, mid in conflicts]
