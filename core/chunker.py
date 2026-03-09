"""
core/chunker.py – Semantic text segmentation
Splits plain text into topic-coherent segments using embedding distance delta.
Never splits mid-sentence. Handles overlap between chunks.
"""

import re
from typing import List
from core import embedder
import numpy as np


# Tunable thresholds
DISTANCE_THRESHOLD = 0.35   # Cosine distance above this = topic shift
MIN_CHUNK_SENTENCES = 2     # Minimum sentences per chunk
MAX_CHUNK_TOKENS = 800      # Approximate token limit per chunk
OVERLAP_SENTENCES = 2       # Sentences to repeat at start of next chunk


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences. Handles common abbreviations."""
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    # Further split on newlines that look like new paragraphs
    result = []
    for s in sentences:
        for line in s.split("\n\n"):
            line = line.strip()
            if line:
                result.append(line)
    return result


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 chars."""
    return len(text) // 4


def chunk_text(text: str) -> List[str]:
    """
    Split text into semantically coherent chunks.
    Returns list of chunk strings, each ≤ MAX_CHUNK_TOKENS tokens.
    """
    if not text or not text.strip():
        return []

    sentences = _split_sentences(text)
    if len(sentences) <= MIN_CHUNK_SENTENCES:
        return [text.strip()]

    # Embed all sentences in one batch
    embeddings = embedder.encode_batch(sentences)

    chunks = []
    current_chunk: List[str] = []
    current_tokens = 0

    for i, sentence in enumerate(sentences):
        sentence_tokens = _estimate_tokens(sentence)

        if not current_chunk:
            current_chunk.append(sentence)
            current_tokens += sentence_tokens
            continue

        # Check token limit
        if current_tokens + sentence_tokens > MAX_CHUNK_TOKENS and len(current_chunk) >= MIN_CHUNK_SENTENCES:
            chunks.append(" ".join(current_chunk))
            # Overlap: keep last OVERLAP_SENTENCES
            current_chunk = current_chunk[-OVERLAP_SENTENCES:] + [sentence]
            current_tokens = sum(_estimate_tokens(s) for s in current_chunk)
            continue

        # Check semantic distance to previous sentence
        if i > 0:
            prev_emb = embeddings[i - 1]
            curr_emb = embeddings[i]
            # Cosine distance (vectors are already normalized)
            cos_sim = float(np.dot(prev_emb, curr_emb))
            distance = 1.0 - cos_sim

            if distance > DISTANCE_THRESHOLD and len(current_chunk) >= MIN_CHUNK_SENTENCES:
                chunks.append(" ".join(current_chunk))
                # Overlap
                current_chunk = current_chunk[-OVERLAP_SENTENCES:] + [sentence]
                current_tokens = sum(_estimate_tokens(s) for s in current_chunk)
                continue

        current_chunk.append(sentence)
        current_tokens += sentence_tokens

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return [c.strip() for c in chunks if c.strip()]


def chunk_with_overlap(text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
    """
    Fallback chunking: fixed token size with overlap.
    Used when semantic structure is absent (e.g., unstructured text dump).
    Never splits mid-sentence. Falls back to word-level splitting when
    a single sentence itself exceeds chunk_size (e.g., no punctuation at all).
    """
    sentences = _split_sentences(text)

    # Root fix: if any sentence alone exceeds chunk_size, word-split it first
    expanded: List[str] = []
    for s in sentences:
        if _estimate_tokens(s) > chunk_size:
            expanded.extend(_split_by_words(s, chunk_size, overlap))
        else:
            expanded.append(s)
    sentences = expanded

    chunks = []
    current: List[str] = []
    current_tokens = 0

    i = 0
    while i < len(sentences):
        s = sentences[i]
        s_tokens = _estimate_tokens(s)

        if current_tokens + s_tokens > chunk_size and current:
            chunks.append(" ".join(current))
            # Roll back by overlap tokens
            rollback: List[str] = []
            rollback_tokens = 0
            for s_prev in reversed(current):
                t = _estimate_tokens(s_prev)
                if rollback_tokens + t <= overlap:
                    rollback.insert(0, s_prev)
                    rollback_tokens += t
                else:
                    break
            current = rollback
            current_tokens = rollback_tokens
        else:
            current.append(s)
            current_tokens += s_tokens
            i += 1

    if current:
        chunks.append(" ".join(current))

    return [c.strip() for c in chunks if c.strip()]


def _split_by_words(text: str, chunk_size: int, overlap: int) -> List[str]:
    """
    Force-split a single long string at word boundaries.
    Used when a 'sentence' has no punctuation and exceeds chunk_size tokens.
    """
    words = text.split()
    chunks = []
    current: List[str] = []
    current_tokens = 0
    overlap_words = max(1, (overlap * 4) // 5)  # rough word count for overlap

    for word in words:
        word_tokens = _estimate_tokens(word + " ")
        if current_tokens + word_tokens > chunk_size and current:
            chunks.append(" ".join(current))
            # Keep last N words as overlap
            current = current[-overlap_words:] + [word]
            current_tokens = sum(_estimate_tokens(w + " ") for w in current)
        else:
            current.append(word)
            current_tokens += word_tokens

    if current:
        chunks.append(" ".join(current))

    return chunks
