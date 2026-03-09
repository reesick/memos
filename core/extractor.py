"""
core/extractor.py – Fact extraction from text segments via LLM
Sends each segment to Ollama with a structured extraction prompt.
Validates response against Pydantic schema.
Retries once with stricter prompt on invalid JSON.
Never crashes on bad LLM output – skips and logs instead.
"""

import json
import logging
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class Fact(BaseModel):
    """A single atomic fact extracted from text."""
    entity: str = Field(..., description="Subject of the fact (person, concept, system)")
    attribute: str = Field(..., description="What aspect of the entity this describes")
    value: str = Field(..., description="The actual fact value")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence 0.0-1.0")

    @field_validator("entity", "attribute", "value")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

    @field_validator("attribute")
    @classmethod
    def normalize_attribute(cls, v: str) -> str:
        """
        Root fix Layer 1: normalize attribute names to snake_case at parse time.
        Converts 'technology preference', 'TechnologyPreference', 'Technology Preference'
        all to 'technology_preference' → consistent key for dedup lookup.
        """
        import re
        # CamelCase → snake_case
        s = re.sub(r'(?<=[a-z0-9])([A-Z])', r'_\1', v.strip()).lower()
        # Replace spaces/hyphens/dots with underscore
        s = re.sub(r'[\s\-\.]+', '_', s)
        # Collapse multiple underscores
        s = re.sub(r'_+', '_', s).strip('_')
        return s

    @field_validator("confidence")
    @classmethod
    def valid_confidence(cls, v: float) -> float:
        return round(max(0.0, min(1.0, v)), 3)


EXTRACTION_PROMPT = """You are a fact extraction engine. Extract ALL factual statements from the text below.

Rules:
- Extract ONLY what is explicitly stated. Never infer or add information not in the text.
- Each fact must have: entity (who/what), attribute (which property), value (the fact itself).
- Confidence: 1.0 = explicitly stated, 0.8 = clearly implied, 0.7 = somewhat implied, below 0.7 = skip.
- If text has no extractable facts (e.g., it's a question), return an empty array [].
- CRITICAL: attribute MUST be snake_case. Use the shortest canonical name.
  Preferred vocabulary: role, language, location, skill, technology, status, team,
  university, employer, age, preference, experience, project, framework, database.
  Examples: "technology preference" → "technology", "works at" → "employer",
  "studied at" → "university", "knows how to use" → "skill".

Output ONLY valid JSON array, no explanation, no markdown. Example:
[
  {{"entity": "Alice", "attribute": "role", "value": "backend engineer", "confidence": 0.95}},
  {{"entity": "Project X", "attribute": "language", "value": "Python", "confidence": 1.0}},
  {{"entity": "Bob", "attribute": "technology", "value": "React", "confidence": 0.9}}
]

Text to extract from:
{text}

JSON array:"""

STRICT_EXTRACTION_PROMPT = """Extract facts as a JSON array from this text. Be strict.
Output ONLY a JSON array starting with [ and ending with ].
Each item: {{"entity": "...", "attribute": "snake_case_name", "value": "...", "confidence": 0.0-1.0}}
Attributes must be snake_case (e.g. role, technology, employer, university, skill).
If no facts, output: []

Text:
{text}

Output:"""


def _parse_fact_response(raw: str) -> Optional[List[dict]]:
    """Parse LLM response into list of fact dicts. Returns None on failure."""
    raw = raw.strip()
    # Strip markdown code fences
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(l for l in lines if not l.startswith("```")).strip()

    # Find JSON array boundaries
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        data = json.loads(raw[start:end + 1])
        if isinstance(data, list):
            return data
        return None
    except json.JSONDecodeError:
        return None


def _validate_facts(raw_facts: List[dict]) -> List[Fact]:
    """Validate raw dicts against Pydantic schema. Silently skip invalid."""
    validated = []
    for item in raw_facts:
        try:
            fact = Fact(**item)
            if fact.confidence >= 0.7:  # Confidence threshold from PRD
                validated.append(fact)
        except Exception:
            pass  # Skip malformed fact
    return validated


def extract(segment: str) -> List[Fact]:
    """
    Extract facts from a single text segment.
    Returns validated list of Fact objects (may be empty).
    Never raises – logs and returns [] on any LLM/parse failure.
    """
    if not segment or not segment.strip():
        return []

    from core import llm

    # First attempt
    try:
        prompt = EXTRACTION_PROMPT.format(text=segment.strip())
        raw = llm.call(prompt, temperature=0.1)
        parsed = _parse_fact_response(raw)

        if parsed is not None:
            return _validate_facts(parsed)

        # Retry with stricter prompt
        logger.warning("Extractor: first attempt returned invalid JSON, retrying with strict prompt.")
        strict_prompt = STRICT_EXTRACTION_PROMPT.format(text=segment.strip())
        raw2 = llm.call(strict_prompt, temperature=0.0)
        parsed2 = _parse_fact_response(raw2)

        if parsed2 is not None:
            return _validate_facts(parsed2)

        logger.warning(f"Extractor: both attempts failed for segment: {segment[:80]}...")
        return []

    except Exception as e:
        logger.error(f"Extractor: LLM call failed: {e}")
        return []


def extract_all(segments: List[str]) -> List[Fact]:
    """
    Extract facts from all segments sequentially.
    Returns combined list of all validated facts.
    """
    all_facts = []
    for seg in segments:
        facts = extract(seg)
        all_facts.extend(facts)
    return all_facts
