"""
core/input_router.py – Input type detection and routing
Routes each input to the correct preprocessing pipeline.
Returns a list of text segments ready for the extraction layer.
"""

from typing import List, Dict, Any
import json
import csv
import io
import tiktoken

# Token counting encoder (cl100k_base ≈ GPT-4 tokenizer, close enough for budgeting)
_enc = None

def _get_encoder():
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding("cl100k_base")
    return _enc


def count_tokens(text: str) -> int:
    """Count tokens in a string using tiktoken."""
    return len(_get_encoder().encode(text))


MAX_TOKENS = 50_000


class InputTooLargeError(Exception):
    def __init__(self, actual: int):
        self.actual = actual
        super().__init__(f"CONTENT_TOO_LARGE: {actual} tokens (max {MAX_TOKENS})")


class EmptyContentError(Exception):
    pass


class InvalidSourceTypeError(Exception):
    pass


VALID_SOURCE_TYPES = {"text", "pdf", "code", "json", "csv"}


def route(content: str, source_type: str = "text", metadata: Dict[str, Any] = None) -> List[str]:
    """
    Main routing entry point.
    Returns list of text segments ready for extraction.
    Raises InputTooLargeError, EmptyContentError, InvalidSourceTypeError on bad input.
    """
    if not content or not content.strip():
        raise EmptyContentError("EMPTY_CONTENT: No content provided.")

    source_type = source_type.lower().strip()
    if source_type not in VALID_SOURCE_TYPES:
        # Default unknown to text
        source_type = "text"

    token_count = count_tokens(content)
    if token_count > MAX_TOKENS:
        raise InputTooLargeError(token_count)

    if source_type == "pdf":
        from core.pdf_parser import parse_pdf
        return parse_pdf(content, metadata or {})
    elif source_type == "code":
        from core.code_parser import parse_code
        return parse_code(content, metadata or {})
    elif source_type == "json":
        return _route_json(content)
    elif source_type == "csv":
        return _route_csv(content)
    else:
        # Plain text or voice transcript
        from core.chunker import chunk_text
        return chunk_text(content)


def _route_json(content: str) -> List[str]:
    """Parse JSON and convert each record/key-value to a text segment."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Fall back to plain text chunking
        from core.chunker import chunk_text
        return chunk_text(content)

    segments = []
    if isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                parts = [f"{k}: {v}" for k, v in item.items()]
                segments.append(f"Record {i+1}: " + ", ".join(parts))
            else:
                segments.append(f"Item {i+1}: {str(item)}")
    elif isinstance(data, dict):
        for k, v in data.items():
            segments.append(f"{k}: {v}")
    else:
        segments.append(str(data))

    return [s for s in segments if s.strip()]


def _route_csv(content: str) -> List[str]:
    """Parse CSV and convert each row to a text segment."""
    segments = []
    try:
        reader = csv.DictReader(io.StringIO(content))
        for i, row in enumerate(reader):
            parts = [f"{k}: {v}" for k, v in row.items() if v and v.strip()]
            if parts:
                segments.append(f"Row {i+1}: " + ", ".join(parts))
    except Exception:
        # Fall back to plain text
        from core.chunker import chunk_text
        return chunk_text(content)

    if not segments:
        from core.chunker import chunk_text
        return chunk_text(content)

    return segments
