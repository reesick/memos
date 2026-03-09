"""
core/embedder.py – Local sentence embedding
Uses all-MiniLM-L6-v2 (384-dim). Downloaded once (~90MB), runs fully offline after that.
LRU cache of 512 to avoid re-embedding repeated text.
"""

import numpy as np
from cachetools import LRUCache
from functools import lru_cache
from typing import List

# Global model instance – loaded once on first use
_model = None
_cache: LRUCache = LRUCache(maxsize=512)


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def encode(text: str) -> np.ndarray:
    """
    Encode a single text string into a 384-dim float32 numpy vector.
    Cache hit: returns cached vector instantly.
    Cache miss: runs model inference, caches result.
    """
    if not text or not text.strip():
        # Return zero vector for empty text
        return np.zeros(384, dtype=np.float32)

    key = text.strip()
    if key in _cache:
        return _cache[key]

    model = _get_model()
    vector = model.encode(key, convert_to_numpy=True, normalize_embeddings=True)
    vector = vector.astype(np.float32)
    _cache[key] = vector
    return vector


def encode_batch(texts: List[str]) -> np.ndarray:
    """
    Encode a list of texts in a single batch pass.
    Returns array of shape (len(texts), 384).
    Uses cache for each individual element.
    """
    results = []
    uncached_texts = []
    uncached_indices = []

    for i, text in enumerate(texts):
        key = text.strip() if text else ""
        if key in _cache:
            results.append((i, _cache[key]))
        else:
            uncached_texts.append(key)
            uncached_indices.append(i)
            results.append((i, None))

    if uncached_texts:
        model = _get_model()
        batch_vectors = model.encode(
            uncached_texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=32,
        ).astype(np.float32)
        for j, idx in enumerate(uncached_indices):
            vec = batch_vectors[j]
            _cache[uncached_texts[j]] = vec
            results[idx] = (idx, vec)

    # Sort by original index and stack
    results.sort(key=lambda x: x[0])
    return np.stack([r[1] for r in results])


def dimensions() -> int:
    """Return embedding dimension (384 for all-MiniLM-L6-v2)."""
    return 384
