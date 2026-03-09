"""
core/kuzu_store.py – Embedded Kuzu graph store
Manages Entity and Fact nodes with temporal RELATES_TO edges.
All current-fact queries filter WHERE valid_until IS NULL.
Shared memory_id UUID links every Fact node to SQLite and FAISS.
"""

import os
import time
import logging
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

# Kuzu schema
ENTITY_TABLE = "Entity"
FACT_TABLE = "Fact"
EDGE_TABLE = "RELATES_TO"


class KuzuStore:
    """
    Kuzu embedded graph database wrapper.
    Creates tables on first run. Exposes high-level methods only.
    """

    def __init__(self, db_dir: str):
        self.db_dir = db_dir
        os.makedirs(db_dir, exist_ok=True)
        self._db = None
        self._conn = None
        self._init_db()

    def _init_db(self):
        try:
            import kuzu
            self._db = kuzu.Database(self.db_dir)
            self._conn = kuzu.Connection(self._db)
            self._create_schema()
            logger.info(f"Kuzu: Opened graph at {self.db_dir}")
        except Exception as e:
            logger.error(f"Kuzu: Initialization failed: {e}. Graph features disabled.")
            self._conn = None

    def _create_schema(self):
        """Create node and edge tables if they don't exist."""
        if not self._conn:
            return
        queries = [
            f"""CREATE NODE TABLE IF NOT EXISTS {ENTITY_TABLE} (
                name STRING,
                type STRING,
                source STRING,
                PRIMARY KEY (name)
            )""",
            f"""CREATE NODE TABLE IF NOT EXISTS {FACT_TABLE} (
                memory_id STRING,
                value STRING,
                confidence DOUBLE,
                PRIMARY KEY (memory_id)
            )""",
            f"""CREATE REL TABLE IF NOT EXISTS {EDGE_TABLE} (
                FROM {ENTITY_TABLE} TO {FACT_TABLE},
                relationship STRING,
                valid_from INT64,
                valid_until INT64,
                confidence DOUBLE
            )""",
        ]
        for q in queries:
            try:
                self._conn.execute(q)
            except Exception as e:
                # Table already exists – that's fine
                if "already exists" not in str(e).lower():
                    logger.warning(f"Kuzu schema: {e}")

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def create_entity(self, name: str, entity_type: str = "Unknown", source: str = "conversation"):
        """Create Entity node if it doesn't already exist."""
        if not self._conn:
            return
        try:
            self._conn.execute(
                f"MERGE (e:{ENTITY_TABLE} {{name: $name}}) "
                f"ON CREATE SET e.type=$type, e.source=$source",
                {"name": name, "type": entity_type, "source": source}
            )
        except Exception:
            # Kuzu MERGE syntax varies – try plain insert first, ignore duplicate
            try:
                self._conn.execute(
                    f"CREATE (:{ENTITY_TABLE} {{name: $name, type: $type, source: $source}})",
                    {"name": name, "type": entity_type, "source": source}
                )
            except Exception:
                pass  # Already exists

    def create_fact_node(self, memory_id: str, value: str, confidence: float):
        """Create a Fact node."""
        if not self._conn:
            return
        try:
            self._conn.execute(
                f"CREATE (:{FACT_TABLE} {{memory_id: $mid, value: $val, confidence: $conf}})",
                {"mid": memory_id, "val": value, "conf": confidence}
            )
        except Exception as e:
            logger.warning(f"Kuzu create_fact_node: {e}")

    def create_edge(
        self,
        entity_name: str,
        memory_id: str,
        relationship: str = "HAS_FACT",
        confidence: float = 0.9,
    ):
        """Create RELATES_TO edge between Entity and Fact with valid_from=now."""
        if not self._conn:
            return
        now = int(time.time())
        try:
            self._conn.execute(
                f"""MATCH (e:{ENTITY_TABLE} {{name: $ename}}), (f:{FACT_TABLE} {{memory_id: $mid}})
                    CREATE (e)-[:{EDGE_TABLE} {{
                        relationship: $rel,
                        valid_from: $vf,
                        valid_until: -1,
                        confidence: $conf
                    }}]->(f)""",
                {
                    "ename": entity_name,
                    "mid": memory_id,
                    "rel": relationship,
                    "vf": now,
                    "conf": confidence,
                }
            )
        except Exception as e:
            logger.warning(f"Kuzu create_edge: {e}")

    def expire_edge(self, entity_name: str, memory_id: str):
        """Mark edge from entity to a specific fact as expired (valid_until = now)."""
        if not self._conn:
            return
        now = int(time.time())
        try:
            self._conn.execute(
                f"""MATCH (e:{ENTITY_TABLE} {{name: $ename}})-[r:{EDGE_TABLE}]->(f:{FACT_TABLE} {{memory_id: $mid}})
                    SET r.valid_until = $now""",
                {"ename": entity_name, "mid": memory_id, "now": now}
            )
        except Exception as e:
            logger.warning(f"Kuzu expire_edge: {e}")

    def delete_fact(self, memory_id: str):
        """Delete Fact node and all edges connected to it."""
        if not self._conn:
            return
        try:
            self._conn.execute(
                f"MATCH (f:{FACT_TABLE} {{memory_id: $mid}}) DETACH DELETE f",
                {"mid": memory_id}
            )
        except Exception as e:
            logger.warning(f"Kuzu delete_fact: {e}")

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def traverse(
        self,
        entity_name: str,
        hops: int = 2,
        include_expired: bool = False,
    ) -> List[Dict]:
        """
        Traverse from an entity node up to `hops` hops.
        Returns list of fact dicts including relationship info.
        """
        if not self._conn:
            return []
        try:
            expired_filter = "" if include_expired else "AND r.valid_until = -1"
            result = self._conn.execute(
                f"""MATCH (e:{ENTITY_TABLE} {{name: $ename}})-[r:{EDGE_TABLE}]->(f:{FACT_TABLE})
                    WHERE TRUE {expired_filter}
                    RETURN f.memory_id AS memory_id, f.value AS value,
                           r.relationship AS relationship, r.valid_from AS valid_from,
                           r.valid_until AS valid_until""",
                {"ename": entity_name}
            )
            rows = []
            while result.has_next():
                row = result.get_next()
                rows.append({
                    "memory_id": row[0],
                    "value": row[1],
                    "relationship": row[2],
                    "valid_from": row[3],
                    "valid_until": row[4],
                })
            return rows
        except Exception as e:
            logger.warning(f"Kuzu traverse: {e}")
            return []

    def bridge_detect(self, memory_ids: List[str]) -> List[Dict]:
        """
        Check if any two memory_ids share a common entity (cross-source bridge).
        Returns list of bridge connections.
        """
        if not self._conn or len(memory_ids) < 2:
            return []
        bridges = []
        try:
            for i in range(len(memory_ids)):
                for j in range(i + 1, len(memory_ids)):
                    result = self._conn.execute(
                        f"""MATCH (e:{ENTITY_TABLE})-[:{EDGE_TABLE}]->(f1:{FACT_TABLE} {{memory_id: $id1}}),
                                  (e)-[:{EDGE_TABLE}]->(f2:{FACT_TABLE} {{memory_id: $id2}})
                            RETURN e.name AS entity""",
                        {"id1": memory_ids[i], "id2": memory_ids[j]}
                    )
                    if result.has_next():
                        row = result.get_next()
                        bridges.append({
                            "entity": row[0],
                            "memory_id_1": memory_ids[i],
                            "memory_id_2": memory_ids[j],
                        })
        except Exception as e:
            logger.warning(f"Kuzu bridge_detect: {e}")
        return bridges

    def get_subgraph(self, entity_name: str, hops: int = 2) -> Dict:
        """Return nodes and edges for visualization."""
        if not self._conn:
            return {"nodes": [], "edges": []}
        try:
            result = self._conn.execute(
                f"""MATCH (e:{ENTITY_TABLE} {{name: $ename}})-[r:{EDGE_TABLE}]->(f:{FACT_TABLE})
                    RETURN e.name, e.type, f.memory_id, f.value,
                           r.relationship, r.valid_from, r.valid_until""",
                {"ename": entity_name}
            )
            nodes, edges = [], []
            seen_nodes = set()
            while result.has_next():
                row = result.get_next()
                if row[0] not in seen_nodes:
                    nodes.append({"id": row[0], "name": row[0], "type": row[1]})
                    seen_nodes.add(row[0])
                if row[2] not in seen_nodes:
                    nodes.append({"id": row[2], "name": row[3], "type": "Fact"})
                    seen_nodes.add(row[2])
                edges.append({
                    "from": row[0], "to": row[2],
                    "relationship": row[4],
                    "valid_from": row[5], "valid_until": row[6],
                })
            return {"nodes": nodes, "edges": edges}
        except Exception as e:
            logger.warning(f"Kuzu get_subgraph: {e}")
            return {"nodes": [], "edges": []}
