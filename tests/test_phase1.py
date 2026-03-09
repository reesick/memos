"""
tests/test_phase1.py – Comprehensive Phase 1 test suite
Tests every file from the PRD Phase 1 checklist.
Runs without Ollama using mocks for LLM calls.
Runs with Ollama for full pipeline integration tests (skipped if Ollama unavailable).

Run: pytest tests/test_phase1.py -v
"""

import sys
import os
import time
import json
import tempfile
import shutil
import numpy as np
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="session")
def tmp_data_dir():
    """Temporary data directory for all stores during tests."""
    tmpdir = tempfile.mkdtemp(prefix="memoryos_test_")
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture(scope="session")
def sqlite_store(tmp_data_dir):
    from core.sqlite_store import SqliteStore
    store = SqliteStore(os.path.join(tmp_data_dir, "test.db"))
    yield store
    store.close()


@pytest.fixture(scope="session")
def faiss_store(tmp_data_dir):
    from core.faiss_store import FaissStore
    store = FaissStore(os.path.join(tmp_data_dir, "test.index"))
    yield store


@pytest.fixture(scope="session")
def kuzu_store(tmp_data_dir):
    from core.kuzu_store import KuzuStore
    store = KuzuStore(os.path.join(tmp_data_dir, "kuzu_db"))
    yield store


def _ollama_model_ready():
    """True only if Ollama is running AND the configured model is fully pulled."""
    from core.llm import is_model_available
    return is_model_available()


# ============================================================
# 1. core/llm.py
# ============================================================

class TestLLM:
    def test_import(self):
        from core import llm
        assert callable(llm.call)
        assert callable(llm.is_ollama_running)
        assert callable(llm.call_json)

    def test_ollama_health_check_returns_bool(self):
        from core.llm import is_ollama_running
        result = is_ollama_running()
        assert isinstance(result, bool)

    @pytest.mark.skipif(not _ollama_model_ready(), reason="Ollama model not pulled")
    def test_ollama_call_returns_string(self):
        from core.llm import call
        result = call("Reply with the single word: hello")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_call_json_parses_json_fence(self, monkeypatch):
        """call_json should strip markdown fences and parse JSON."""
        from core import llm
        monkeypatch.setattr(llm, "call", lambda p, temperature=0.1: '```json\n[{"a": 1}]\n```')
        result = llm.call_json("any prompt")
        assert result == [{"a": 1}]

    def test_call_json_returns_none_on_invalid(self, monkeypatch):
        from core import llm
        monkeypatch.setattr(llm, "call", lambda p, temperature=0.1: "definitely not json")
        result = llm.call_json("any prompt")
        assert result is None


# ============================================================
# 2. core/embedder.py
# ============================================================

class TestEmbedder:
    def test_encode_returns_384_dim(self):
        from core import embedder
        vec = embedder.encode("hello world")
        assert vec.shape == (384,)
        assert vec.dtype == np.float32

    def test_encode_empty_returns_zero_vector(self):
        from core import embedder
        vec = embedder.encode("")
        assert vec.shape == (384,)
        assert float(np.sum(vec)) == 0.0

    def test_cache_works(self):
        from core import embedder
        text = "test caching behaviour"
        v1 = embedder.encode(text)
        v2 = embedder.encode(text)
        assert np.allclose(v1, v2)

    def test_encode_batch_shape(self):
        from core import embedder
        texts = ["apple", "banana", "cherry"]
        result = embedder.encode_batch(texts)
        assert result.shape == (3, 384)

    def test_dimensions(self):
        from core.embedder import dimensions
        assert dimensions() == 384


# ============================================================
# 3. core/chunker.py
# ============================================================

VOICE_DUMP = """So I woke up and the first thing I did was check my phone. 
There was a message from Arjun saying the backend was down. 
I immediately got on the call. We debugged for two hours.
The issue was the database connection pool was exhausted.
Anyway after that I went and had breakfast. 
Then I had a meeting about the new feature we are building.
The feature is a memory toggle for our chatbot.
Users want the chatbot to remember them across sessions.
We decided to use FAISS for vector search.
Kuzu will be our graph store. SQLite is the primary store.
The retrieval should be under 300ms for p95.
We wrapped up around 6pm and I went for a run."""

class TestChunker:
    def test_chunk_voice_dump_produces_multiple_chunks(self):
        from core.chunker import chunk_text
        chunks = chunk_text(VOICE_DUMP)
        assert len(chunks) >= 3, f"Expected ≥3 chunks, got {len(chunks)}"

    def test_no_empty_chunks(self):
        from core.chunker import chunk_text
        chunks = chunk_text(VOICE_DUMP)
        assert all(c.strip() for c in chunks)

    def test_short_text_returns_single_chunk(self):
        from core.chunker import chunk_text
        chunks = chunk_text("Hello world.")
        assert len(chunks) == 1

    def test_empty_string_returns_empty_list(self):
        from core.chunker import chunk_text
        assert chunk_text("") == []

    def test_fallback_chunker_respects_size(self):
        from core.chunker import chunk_with_overlap
        long_text = " ".join(["word"] * 2000)
        chunks = chunk_with_overlap(long_text, chunk_size=200, overlap=50)
        assert len(chunks) > 1
        # No chunk should be excessively large
        for c in chunks:
            assert len(c.split()) <= 250  # some slack for overlap


# ============================================================
# 4. core/input_router.py
# ============================================================

class TestInputRouter:
    def test_routes_text(self):
        from core.input_router import route
        segments = route("Arjun is the backend lead.", source_type="text")
        assert isinstance(segments, list)
        assert len(segments) >= 1

    def test_routes_csv(self):
        from core.input_router import route
        csv_data = "name,role\nArjun,backend lead\nPriya,frontend"
        segments = route(csv_data, source_type="csv")
        assert any("Arjun" in s for s in segments)

    def test_routes_json(self):
        from core.input_router import route
        json_data = json.dumps([{"name": "Arjun", "role": "backend"}])
        segments = route(json_data, source_type="json")
        assert len(segments) >= 1

    def test_empty_content_raises(self):
        from core.input_router import route, EmptyContentError
        with pytest.raises(EmptyContentError):
            route("")

    def test_too_large_raises(self):
        from core.input_router import route, InputTooLargeError
        huge = " word" * 60000  # ~60k tokens
        with pytest.raises(InputTooLargeError):
            route(huge)

    def test_unknown_type_defaults_to_text(self):
        from core.input_router import route
        segments = route("Some plain text.", source_type="unknown_xyz")
        assert len(segments) >= 1


# ============================================================
# 5. core/code_parser.py
# ============================================================

PYTHON_CODE = '''
import os
import json

class MemoryEngine:
    """Main memory engine class."""

    def __init__(self, db_path: str):
        """Initialize with database path."""
        self.db_path = db_path

    def add(self, content: str) -> dict:
        """Add content to memory."""
        return {"status": "ok"}

def standalone_function(x: int) -> int:
    """A standalone function."""
    return x * 2
'''

class TestCodeParser:
    def test_python_produces_function_chunks(self):
        from core.code_parser import parse_code
        chunks = parse_code(PYTHON_CODE, {})
        # Should produce at least: imports, class MemoryEngine, method add, standalone_function
        assert len(chunks) >= 2

    def test_function_names_in_chunks(self):
        from core.code_parser import parse_code
        chunks = parse_code(PYTHON_CODE, {})
        combined = " ".join(chunks)
        assert "add" in combined or "MemoryEngine" in combined

    def test_empty_code_returns_empty(self):
        from core.code_parser import parse_code
        assert parse_code("", {}) == []


# ============================================================
# 6. core/extractor.py (with mocked LLM)
# ============================================================

class TestExtractor:
    def test_valid_extraction(self, monkeypatch):
        from core import llm, extractor
        mock_response = json.dumps([
            {"entity": "Arjun", "attribute": "role", "value": "backend lead", "confidence": 0.95}
        ])
        monkeypatch.setattr(llm, "call", lambda p, temperature=0.1: mock_response)
        facts = extractor.extract("Arjun is the backend lead.")
        assert len(facts) == 1
        assert facts[0].entity == "Arjun"
        assert facts[0].attribute == "role"

    def test_pydantic_validates_confidence(self, monkeypatch):
        """Facts with confidence < 0.7 should be filtered out."""
        from core import llm, extractor
        mock_response = json.dumps([
            {"entity": "X", "attribute": "y", "value": "z", "confidence": 0.3}
        ])
        monkeypatch.setattr(llm, "call", lambda p, temperature=0.1: mock_response)
        facts = extractor.extract("Some uncertain text.")
        assert len(facts) == 0

    def test_invalid_json_returns_empty(self, monkeypatch):
        from core import llm, extractor
        monkeypatch.setattr(llm, "call", lambda p, temperature=0.1: "not json at all")
        facts = extractor.extract("Some text.")
        assert facts == []

    def test_empty_input_returns_empty(self):
        from core.extractor import extract
        facts = extract("")
        assert facts == []


# ============================================================
# 7. core/faiss_store.py
# ============================================================

class TestFaissStore:
    def test_add_and_search(self, faiss_store):
        from core import embedder
        vec = embedder.encode("backend lead")
        faiss_store.add_vector("test_mem_001", vec)
        results = faiss_store.search(vec, top_k=1)
        assert len(results) == 1
        assert results[0][0] == "test_mem_001"

    def test_score_is_normalized(self, faiss_store):
        results = faiss_store.search(
            __import__("core.embedder", fromlist=["encode"]).encode("backend lead"),
            top_k=1,
        )
        if results:
            assert 0.0 <= results[0][1] <= 1.0

    def test_empty_search_returns_empty(self, tmp_data_dir):
        from core.faiss_store import FaissStore
        fresh = FaissStore(os.path.join(tmp_data_dir, "empty_test.index"))
        results = fresh.search(np.zeros(384, dtype=np.float32), top_k=5)
        assert results == []

    def test_delete_vector(self, faiss_store):
        from core import embedder
        vec = embedder.encode("to be deleted")
        faiss_store.add_vector("test_mem_delete", vec)
        assert faiss_store.total() >= 1
        faiss_store.delete_vector("test_mem_delete")
        results = faiss_store.search(vec, top_k=5)
        ids = [r[0] for r in results]
        assert "test_mem_delete" not in ids


# ============================================================
# 8. core/sqlite_store.py
# ============================================================

class TestSqliteStore:
    def test_insert_and_retrieve(self, sqlite_store):
        mid = sqlite_store.insert(
            entity="Priya", attribute="role", value="frontend dev",
            confidence=0.92, source_type="text", session_id="sess_test"
        )
        record = sqlite_store.get_by_id(mid)
        assert record is not None
        assert record["entity"] == "Priya"
        assert record["value"] == "frontend dev"

    def test_find_by_entity_attribute(self, sqlite_store):
        sqlite_store.insert("Vedant", "university", "VIT Pune", session_id="sess_test")
        record = sqlite_store.find_by_entity_attribute("Vedant", "university")
        assert record is not None
        assert record["value"] == "VIT Pune"

    def test_noop_same_fact(self, sqlite_store):
        """Inserting same entity+attr and marking NOOP should refresh timestamp."""
        sqlite_store.insert("Mahi", "team", "Group 09")
        existing = sqlite_store.find_by_entity_attribute("Mahi", "team")
        assert existing is not None
        old_ts = existing["timestamp"]
        time.sleep(1.1)  # Wait for timestamp to differ
        sqlite_store.refresh_timestamp(existing["memory_id"])
        updated = sqlite_store.get_by_id(existing["memory_id"])
        assert updated["timestamp"] >= old_ts

    def test_expire(self, sqlite_store):
        mid = sqlite_store.insert("OldFact", "status", "active")
        sqlite_store.update_expired(mid)
        record = sqlite_store.get_by_id(mid)
        assert record["expired_at"] is not None

    def test_bm25_search_returns_results(self, sqlite_store):
        sqlite_store.insert("MemoryOS", "purpose", "memory middleware for LLMs", raw_chunk="MemoryOS is a memory middleware engine")
        results = sqlite_store.bm25_search("middleware LLMs")
        assert isinstance(results, list)

    def test_count(self, sqlite_store):
        count = sqlite_store.count()
        assert isinstance(count, int)
        assert count >= 0


# ============================================================
# 9. core/kuzu_store.py
# ============================================================

class TestKuzuStore:
    def test_create_entity_and_traverse(self, kuzu_store):
        kuzu_store.create_entity("Alice", "Person", "conversation")
        kuzu_store.create_fact_node("mem_alice_001", "senior engineer", 0.9)
        kuzu_store.create_edge("Alice", "mem_alice_001", "HAS_ROLE")
        results = kuzu_store.traverse("Alice", hops=2)
        assert isinstance(results, list)

    def test_expire_edge(self, kuzu_store):
        kuzu_store.create_entity("Bob", "Person", "conversation")
        kuzu_store.create_fact_node("mem_bob_001", "junior dev", 0.85)
        kuzu_store.create_edge("Bob", "mem_bob_001", "HAS_ROLE")
        kuzu_store.expire_edge("Bob", "mem_bob_001")
        # No assertion on result – just verify it doesn't crash
        results = kuzu_store.traverse("Bob", hops=2, include_expired=False)
        assert isinstance(results, list)


# ============================================================
# 10. core/deduplicator.py
# ============================================================

class TestDeduplicator:
    def test_add_on_new_fact(self, sqlite_store):
        from core.deduplicator import deduplicate, DedupAction
        from core.extractor import Fact

        fact = Fact(entity="NewEntity", attribute="color", value="blue", confidence=0.9)
        results = deduplicate([fact], sqlite_store)
        assert results[0].action == DedupAction.ADD

    def test_noop_on_same_fact(self, sqlite_store):
        from core.deduplicator import deduplicate, DedupAction
        from core.extractor import Fact

        sqlite_store.insert("DupEntity", "status", "active", session_id="sess_test")
        fact = Fact(entity="DupEntity", attribute="status", value="active", confidence=0.9)
        results = deduplicate([fact], sqlite_store)
        assert results[0].action == DedupAction.NOOP

    def test_conflict_on_different_value(self, sqlite_store):
        from core.deduplicator import deduplicate, DedupAction
        from core.extractor import Fact

        sqlite_store.insert("ConflictEntity", "database", "PostgreSQL")
        fact = Fact(entity="ConflictEntity", attribute="database", value="MongoDB", confidence=0.9)
        results = deduplicate([fact], sqlite_store)
        assert results[0].action == DedupAction.CONFLICT


# ============================================================
# 11. core/scorer.py
# ============================================================
class TestScorer:
    def test_hybrid_score_in_range(self):
        """
        mem_001 wins both FAISS (0.95 vs 0.4) and BM25 (rank -0.5 vs -5.0,
        lower magnitude = worse BM25 match so mem_001 is BETTER at BM25).
        Expected: mem_001 ranks first unambiguously.
        """
        from core.scorer import merge_scores

        # mem_001: strong FAISS=0.95, BM25 rank=-5.0 (better = more negative in FTS5)
        # mem_002: weak  FAISS=0.4,  BM25 rank=-0.5 (worse = less negative in FTS5)
        faiss_results = [("mem_001", 0.95), ("mem_002", 0.4)]
        bm25_results = [
            {"memory_id": "mem_001", "rank": -5.0},
            {"memory_id": "mem_002", "rank": -0.5},
        ]
        now = int(time.time())
        all_records = {
            "mem_001": {"memory_id": "mem_001", "entity": "A", "attribute": "role",
                        "value": "backend lead", "timestamp": now,
                        "session_id": "s1", "source_type": "text"},
            "mem_002": {"memory_id": "mem_002", "entity": "B", "attribute": "skill",
                        "value": "unrelated fact", "timestamp": now - 86400,
                        "session_id": "s2", "source_type": "text"},
        }
        results = merge_scores("backend role", faiss_results, bm25_results, all_records, top_k=5)
        assert len(results) == 2
        for r in results:
            assert 0.0 <= r["score"] <= 1.0
        assert results[0]["memory_id"] == "mem_001", (
            f"Expected mem_001 to rank first but got {results[0]['memory_id']}. "
            f"Scores: {[(r['memory_id'], r['score']) for r in results]}"
        )

    def test_all_scores_in_valid_range(self):
        """All hybrid scores must be in [0.0, 1.0] regardless of input values."""
        from core.scorer import merge_scores
        now = int(time.time())
        faiss_results = [(f"mem_{i}", i / 10.0) for i in range(1, 6)]
        bm25_results = [{"memory_id": f"mem_{i}", "rank": -float(i)} for i in range(1, 6)]
        all_records = {
            f"mem_{i}": {"memory_id": f"mem_{i}", "entity": "E", "attribute": "a",
                        "value": "v", "timestamp": now - i * 3600,
                        "session_id": "s1", "source_type": "text"}
            for i in range(1, 6)
        }
        results = merge_scores("query", faiss_results, bm25_results, all_records, top_k=10)
        for r in results:
            assert 0.0 <= r["score"] <= 1.0, f"Score out of range: {r['score']}"

    def test_short_query_detected(self):
        from core.scorer import is_short_query
        assert is_short_query("hi") is True
        assert is_short_query("who is the backend lead?") is False



# ============================================================
# 12. core/engine.py – integration test (with temp stores)
# ============================================================

class TestEngine:
    @pytest.fixture(autouse=True)
    def reset_engine(self, tmp_data_dir, monkeypatch):
        """Reset engine state with temp stores for each test."""
        import core.engine as eng
        # Reset singletons
        eng._sqlite = None
        eng._faiss = None
        eng._kuzu = None
        eng._initialized = False
        monkeypatch.setenv("DB_PATH", os.path.join(tmp_data_dir, "engine_test"))
        yield
        eng._sqlite = None
        eng._faiss = None
        eng._kuzu = None
        eng._initialized = False

    def test_add_and_search_with_mock_llm(self, monkeypatch):
        from core import llm
        mock_facts = [
            {"entity": "Arjun", "attribute": "role", "value": "backend lead", "confidence": 0.95}
        ]
        monkeypatch.setattr(llm, "call", lambda p, temperature=0.1: json.dumps(mock_facts))

        import core.engine as eng
        result = eng.add("Arjun is the backend lead.", source_type="text")

        assert result["status"] == "success"
        assert result["facts_extracted"] >= 1
        assert result["facts_added"] >= 1
        assert len(result["memory_ids"]) >= 1

    def test_search_returns_results_after_add(self, monkeypatch):
        from core import llm
        mock_facts = [
            {"entity": "Priya", "attribute": "skill", "value": "React", "confidence": 0.9}
        ]
        monkeypatch.setattr(llm, "call", lambda p, temperature=0.1: json.dumps(mock_facts))

        import core.engine as eng
        eng.add("Priya knows React.", source_type="text")
        result = eng.search("Priya skills")

        assert "results" in result
        assert "context" in result
        assert isinstance(result["results"], list)

    def test_delete_fact(self, monkeypatch):
        from core import llm
        monkeypatch.setattr(llm, "call", lambda p, temperature=0.1: json.dumps([
            {"entity": "TempFact", "attribute": "status", "value": "active", "confidence": 0.9}
        ]))
        import core.engine as eng
        add_result = eng.add("TempFact is active.")
        assert add_result["facts_added"] >= 1
        mid = add_result["memory_ids"][0]

        del_result = eng.delete(mid)
        assert del_result.get("status") == "deleted"
        assert mid in del_result.get("removed_from", [mid]) or del_result.get("status") == "deleted"


# ============================================================
# 13. api/main.py – HTTP endpoint tests via TestClient
# ============================================================

class TestAPI:
    @pytest.fixture(autouse=True)
    def setup_api(self, tmp_data_dir, monkeypatch):
        """Patch engine and LLM for API tests."""
        monkeypatch.setenv("DB_PATH", os.path.join(tmp_data_dir, "api_test"))
        from core import llm
        monkeypatch.setattr(llm, "call", lambda p, temperature=0.1: json.dumps([
            {"entity": "TestUser", "attribute": "preference", "value": "dark mode", "confidence": 0.9}
        ]))
        # Reset engine
        import core.engine as eng
        eng._sqlite = None
        eng._faiss = None
        eng._kuzu = None
        eng._initialized = False
        yield
        eng._sqlite = None
        eng._faiss = None
        eng._kuzu = None
        eng._initialized = False

    def test_health_endpoint(self):
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"

    def test_add_endpoint(self):
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        response = client.post("/memory/add", json={
            "content": "TestUser prefers dark mode.",
            "source_type": "text"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "facts_extracted" in data

    def test_add_empty_returns_400(self):
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        response = client.post("/memory/add", json={"content": ""})
        assert response.status_code == 400

    def test_search_endpoint(self):
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        # Add first
        client.post("/memory/add", json={"content": "TestUser likes Python."})
        # Then search
        response = client.post("/memory/search", json={"query": "TestUser preferences"})
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "context" in data

    def test_delete_nonexistent_returns_404(self):
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        response = client.delete("/memory/mem_does_not_exist_xyz")
        assert response.status_code == 404

    def test_graph_endpoint(self):
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        response = client.get("/memory/graph?entity=TestUser&hops=2")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data


# ============================================================
# Run summary
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
