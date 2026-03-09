"""
core/faiss_store.py – FAISS vector store
IndexFlatL2 wrapped in IndexIDMap for named lookups.
Exact L2 distance. 100% recall. No training needed.
Persists to disk after every add. Reloads on startup.
"""

import os
import logging
import numpy as np
import faiss
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

DIMS = 384         # all-MiniLM-L6-v2 output dimensions
INDEX_FILE = None  # Set during initialization


class FaissStore:
    """
    FAISS vector store backed by IndexFlatL2 + IndexIDMap.
    Thread-safe for reads; writes should be serialized by the calling engine.
    """

    def __init__(self, index_path: str):
        self.index_path = index_path
        self._memory_id_to_int: dict = {}   # memory_id (str) → FAISS integer ID
        self._int_to_memory_id: dict = {}   # FAISS integer ID → memory_id (str)
        self._next_id: int = 0
        self._index: faiss.IndexIDMap = None
        self._load_or_create()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _load_or_create(self):
        """Load existing index from disk or create a fresh one."""
        if os.path.exists(self.index_path):
            try:
                flat = faiss.read_index(self.index_path)
                self._index = flat
                logger.info(f"FAISS: Loaded index from {self.index_path} ({self._index.ntotal} vectors)")
                # Mapping file
                map_path = self.index_path + ".map.npy"
                if os.path.exists(map_path):
                    data = np.load(map_path, allow_pickle=True).item()
                    self._memory_id_to_int = data.get("m2i", {})
                    self._int_to_memory_id = data.get("i2m", {})
                    self._next_id = data.get("next_id", 0)
                return
            except Exception as e:
                logger.warning(f"FAISS: Could not load index ({e}), creating new.")

        self._create_fresh()

    def _create_fresh(self):
        flat_index = faiss.IndexFlatL2(DIMS)
        self._index = faiss.IndexIDMap(flat_index)
        logger.info("FAISS: Created new IndexFlatL2 + IndexIDMap")

    def _save(self):
        """Persist index and ID mapping to disk."""
        os.makedirs(os.path.dirname(self.index_path), exist_ok=True)
        faiss.write_index(self._index, self.index_path)
        map_path = self.index_path + ".map.npy"
        np.save(map_path, {
            "m2i": self._memory_id_to_int,
            "i2m": self._int_to_memory_id,
            "next_id": self._next_id,
        })

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_vector(self, memory_id: str, embedding: np.ndarray):
        """Add a single vector to the index. Writes to disk immediately."""
        if memory_id in self._memory_id_to_int:
            # Already exists – skip (deduplicator should have caught this)
            return

        int_id = self._next_id
        self._next_id += 1

        vec = embedding.reshape(1, DIMS).astype(np.float32)
        ids = np.array([int_id], dtype=np.int64)
        self._index.add_with_ids(vec, ids)

        self._memory_id_to_int[memory_id] = int_id
        self._int_to_memory_id[int_id] = memory_id

        try:
            self._save()
        except Exception as e:
            logger.critical(f"FAISS: write_index failed: {e}. Index is in-memory only until next successful write.")

    def delete_vector(self, memory_id: str):
        """Remove a vector from the index by memory_id."""
        if memory_id not in self._memory_id_to_int:
            return
        int_id = self._memory_id_to_int[memory_id]
        ids = np.array([int_id], dtype=np.int64)
        self._index.remove_ids(ids)
        del self._memory_id_to_int[memory_id]
        del self._int_to_memory_id[int_id]
        self._save()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Search for top_k nearest vectors.
        Returns list of (memory_id, normalized_score) sorted by score DESC.
        Score = 1 - (L2_distance / max_L2), normalized to 0.0-1.0.
        """
        if self._index.ntotal == 0:
            return []

        k = min(top_k, self._index.ntotal)
        query = query_embedding.reshape(1, DIMS).astype(np.float32)

        distances, int_ids = self._index.search(query, k)
        distances = distances[0]
        int_ids = int_ids[0]

        # Normalize distances
        max_dist = float(np.max(distances)) if np.max(distances) > 0 else 1.0
        results = []
        for dist, int_id in zip(distances, int_ids):
            if int_id == -1:
                continue
            mem_id = self._int_to_memory_id.get(int(int_id))
            if mem_id:
                score = 1.0 - (float(dist) / max_dist)
                results.append((mem_id, round(score, 4)))

        return results

    def total(self) -> int:
        """Total number of vectors in index."""
        return self._index.ntotal

    def rebuild_from_records(self, records: List[Tuple[str, np.ndarray]]):
        """
        Rebuild index from scratch given list of (memory_id, embedding).
        Used for recovery after crash.
        """
        logger.warning(f"FAISS: Rebuilding index from {len(records)} records...")
        self._create_fresh()
        self._memory_id_to_int = {}
        self._int_to_memory_id = {}
        self._next_id = 0
        for memory_id, embedding in records:
            self.add_vector(memory_id, embedding)
        logger.info("FAISS: Rebuild complete.")
