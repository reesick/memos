"""
core/sqlite_store.py – SQLite storage with WAL and FTS5 BM25
Source of truth for all facts. FAISS and Kuzu are derived indexes.
WAL mode enabled for crash safety.
FTS5 virtual table for BM25 keyword search on raw_chunk.
"""

import os
import re
import sqlite3
import time
import uuid
import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    memory_id   TEXT PRIMARY KEY,
    entity      TEXT NOT NULL,
    attribute   TEXT NOT NULL,
    value       TEXT NOT NULL,
    confidence  REAL NOT NULL DEFAULT 0.9,
    source_type TEXT NOT NULL DEFAULT 'text',
    doc_id      TEXT,
    session_id  TEXT,
    timestamp   INTEGER NOT NULL,
    expired_at  INTEGER,
    raw_chunk   TEXT
);

CREATE INDEX IF NOT EXISTS idx_entity_attr ON memories (entity, attribute);
CREATE INDEX IF NOT EXISTS idx_session ON memories (session_id);
CREATE INDEX IF NOT EXISTS idx_timestamp ON memories (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_expired ON memories (expired_at);

-- FTS5 for BM25 keyword search on raw_chunk
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    memory_id UNINDEXED,
    entity,
    attribute,
    value,
    raw_chunk,
    content=memories,
    content_rowid=rowid
);

-- Keep FTS in sync with main table
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, memory_id, entity, attribute, value, raw_chunk)
    VALUES (new.rowid, new.memory_id, new.entity, new.attribute, new.value, new.raw_chunk);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, memory_id, entity, attribute, value, raw_chunk)
    VALUES ('delete', old.rowid, old.memory_id, old.entity, old.attribute, old.value, old.raw_chunk);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, memory_id, entity, attribute, value, raw_chunk)
    VALUES ('delete', old.rowid, old.memory_id, old.entity, old.attribute, old.value, old.raw_chunk);
    INSERT INTO memories_fts(rowid, memory_id, entity, attribute, value, raw_chunk)
    VALUES (new.rowid, new.memory_id, new.entity, new.attribute, new.value, new.raw_chunk);
END;
"""


def _sanitize_fts_query(query: str) -> str:
    """
    Root fix for FTS5 syntax errors from raw user input.

    FTS5 MATCH treats these as syntax: ? * " - AND OR NOT ( )
    Strategy: strip punctuation/operators, extract clean alpha-numeric tokens,
    and wrap each in double-quotes so FTS5 treats them as literal phrase terms.

    Examples:
        "who is Arjun?"  → "who" "is" "Arjun"
        "backend lead"   → "backend" "lead"
        "what's going?"  → "what" "s" "going"
    """
    if not query or not query.strip():
        return ""

    # Remove FTS5 operators and special chars, keep letters/numbers/spaces
    cleaned = re.sub(r'[^\w\s]', ' ', query)

    # Extract non-empty words of length >= 2 (skip single chars like "a", "I")
    tokens = [w for w in cleaned.split() if len(w) >= 2]

    if not tokens:
        return ""

    # Wrap each token in double-quotes → treated as literal by FTS5
    return " ".join(f'"{t}"' for t in tokens)


def _new_memory_id() -> str:
    return "mem_" + uuid.uuid4().hex[:8]


class SqliteStore:
    """
    SQLite-backed fact store.
    Single connection in WAL mode. Thread-safe for reads, serialized writes.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self):
        """Enable WAL mode and create schema."""
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()
        logger.info(f"SQLite: Opened {self.db_path} (WAL mode, FTS5 ready)")

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def insert(
        self,
        entity: str,
        attribute: str,
        value: str,
        confidence: float = 0.9,
        source_type: str = "text",
        doc_id: Optional[str] = None,
        session_id: Optional[str] = None,
        raw_chunk: Optional[str] = None,
        memory_id: Optional[str] = None,
    ) -> str:
        """Insert a new fact. Returns memory_id."""
        mid = memory_id or _new_memory_id()
        now = int(time.time())
        self._conn.execute(
            """INSERT INTO memories
               (memory_id, entity, attribute, value, confidence, source_type,
                doc_id, session_id, timestamp, expired_at, raw_chunk)
               VALUES (?,?,?,?,?,?,?,?,?,NULL,?)""",
            (mid, entity, attribute, value, confidence, source_type,
             doc_id, session_id, now, raw_chunk or value),
        )
        self._conn.commit()
        return mid

    def update_expired(self, memory_id: str):
        """Mark a fact as expired (superseded). Sets expired_at = now."""
        now = int(time.time())
        self._conn.execute(
            "UPDATE memories SET expired_at=? WHERE memory_id=?",
            (now, memory_id),
        )
        self._conn.commit()

    def refresh_timestamp(self, memory_id: str):
        """Update timestamp for recency (NOOP case)."""
        now = int(time.time())
        self._conn.execute(
            "UPDATE memories SET timestamp=? WHERE memory_id=?",
            (now, memory_id),
        )
        self._conn.commit()

    def delete(self, memory_id: str) -> bool:
        """Permanently delete a fact. Returns True if deleted."""
        cursor = self._conn.execute(
            "DELETE FROM memories WHERE memory_id=?", (memory_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def find_by_entity_attribute(self, entity: str, attribute: str) -> Optional[Dict]:
        """
        Find current (non-expired) fact by entity+attribute.
        Returns dict or None.
        """
        row = self._conn.execute(
            """SELECT * FROM memories
               WHERE entity=? AND attribute=? AND expired_at IS NULL
               ORDER BY timestamp DESC LIMIT 1""",
            (entity, attribute),
        ).fetchone()
        return dict(row) if row else None

    def get_all_for_entity(self, entity: str, include_expired: bool = False) -> List[Dict]:
        """
        Return all facts for a given entity.
        Used by the semantic deduplicator (Layer 2) to find semantically
        equivalent attributes that may have different string names.
        """
        q = "SELECT * FROM memories WHERE entity=?"
        params = [entity]
        if not include_expired:
            q += " AND expired_at IS NULL"
        q += " ORDER BY timestamp DESC"
        rows = self._conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]

    def get_by_id(self, memory_id: str) -> Optional[Dict]:
        """Fetch a single fact by memory_id."""
        row = self._conn.execute(
            "SELECT * FROM memories WHERE memory_id=?", (memory_id,)
        ).fetchone()
        return dict(row) if row else None

    def bm25_search(
        self,
        query: str,
        top_k: int = 10,
        include_expired: bool = False,
        source_filter: Optional[str] = None,
        session_filter: Optional[str] = None,
    ) -> List[Dict]:
        """
        BM25 keyword search via FTS5.
        Returns list of fact dicts sorted by BM25 rank.
        """
        # Root fix: sanitize query before passing to FTS5 MATCH.
        # FTS5 treats ?, *, ", -, AND, OR, NOT as operators.
        # We extract clean tokens and quote each one so they're treated literally.
        safe_query = _sanitize_fts_query(query)
        if not safe_query:
            return []

        fts_query = f"""
            SELECT m.*, rank
            FROM memories_fts f
            JOIN memories m ON m.memory_id = f.memory_id
            WHERE memories_fts MATCH ?
        """
        params: List[Any] = [safe_query]

        if not include_expired:
            fts_query += " AND m.expired_at IS NULL"
        if source_filter:
            fts_query += " AND m.source_type = ?"
            params.append(source_filter)
        if session_filter:
            fts_query += " AND m.session_id = ?"
            params.append(session_filter)

        fts_query += " ORDER BY rank LIMIT ?"
        params.append(top_k)

        try:
            rows = self._conn.execute(fts_query, params).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError as e:
            logger.warning(f"BM25 search failed: {e}")
            return []

    def get_all_for_rebuild(self) -> List[Dict]:
        """Return all non-expired facts. Used for FAISS/Kuzu rebuild."""
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE expired_at IS NULL ORDER BY timestamp"
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self, include_expired: bool = False) -> int:
        """Count facts in store."""
        q = "SELECT COUNT(*) FROM memories"
        if not include_expired:
            q += " WHERE expired_at IS NULL"
        return self._conn.execute(q).fetchone()[0]

    def rename_entity(self, old_entity: str, new_entity: str) -> int:
        """Rename all facts from old_entity to new_entity. Returns count updated."""
        cursor = self._conn.execute(
            "UPDATE memories SET entity=? WHERE entity=?",
            (new_entity, old_entity),
        )
        self._conn.commit()
        return cursor.rowcount

    def get_distinct_entities(self) -> List[str]:
        rows = self._conn.execute("SELECT DISTINCT entity FROM memories").fetchall()
        return [r[0] for r in rows]

    def close(self):
        self._conn.close()
