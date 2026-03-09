"""
tests/test_phase2.py – Phase 2 test suite
Tests augmenter (core/augmenter.py) and the two API endpoints it powers.
No MCP, no SDK — skipped per user request.

Run: pytest tests/test_phase2.py -v
"""

import sys
import os
import json
import time
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def reset_engine(tmp_path, monkeypatch):
    """Fresh stores + mocked LLM for every test."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "p2_test"))
    from core import llm
    monkeypatch.setattr(llm, "call", lambda p, temperature=0.1: json.dumps([
        {"entity": "User", "attribute": "interest", "value": "machine learning", "confidence": 0.9}
    ]))
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


# ============================================================
# 1. core/augmenter.py – should_inject()
# ============================================================

class TestShouldInject:
    def test_returns_dict_with_inject_key(self):
        from core.augmenter import should_inject
        result = should_inject("hello")
        assert "inject" in result
        assert isinstance(result["inject"], bool)

    def test_injects_on_memory_triggers(self):
        from core.augmenter import should_inject
        result = should_inject("what was my favorite project?")
        assert result["inject"] is True

    def test_no_inject_on_simple_greeting(self):
        from core.augmenter import should_inject
        result = should_inject("2 + 2")
        assert result["inject"] is False

    def test_confidence_is_float_in_range(self):
        from core.augmenter import should_inject
        result = should_inject("what did we talk about before?")
        assert 0.0 <= result["confidence"] <= 1.0

    def test_runs_under_50ms(self):
        from core.augmenter import should_inject
        start = time.time()
        should_inject("who is my frontend lead?")
        elapsed_ms = (time.time() - start) * 1000
        assert elapsed_ms < 50, f"should_inject took {elapsed_ms:.1f}ms (limit: 50ms)"

    def test_reason_is_string(self):
        from core.augmenter import should_inject
        result = should_inject("what was my previous role?")
        assert isinstance(result.get("reason"), str)
        assert len(result["reason"]) > 0


# ============================================================
# 2. core/augmenter.py – augment()
# ============================================================

class TestAugment:
    def test_returns_augmented_prompt_key(self):
        from core.augmenter import augment
        result = augment("what do I like?")
        assert "augmented_prompt" in result
        assert isinstance(result["augmented_prompt"], str)

    def test_no_inject_returns_original_prompt(self):
        from core.augmenter import augment
        prompt = "2 + 2"
        result = augment(prompt)
        assert result["augmented_prompt"] == prompt
        assert result["injected"] is False

    def test_force_inject_always_injects(self, monkeypatch):
        """force_inject=True should always inject even if prompt is boring."""
        import core.engine as eng
        monkeypatch.setattr(eng, "search", lambda *a, **kw: {
            "context": "User likes machine learning.",
            "results": [{"memory_id": "mem_test", "entity": "User"}],
        })
        from core.augmenter import augment
        result = augment("hello", force_inject=True)
        assert result["injected"] is True
        assert "[Memory Context]" in result["augmented_prompt"]

    def test_context_added_is_list(self):
        from core.augmenter import augment
        result = augment("what do I like?")
        assert isinstance(result.get("context_added"), list)

    def test_augment_ms_is_int(self):
        from core.augmenter import augment
        result = augment("who am I?")
        assert isinstance(result.get("augment_ms"), int)


# ============================================================
# 3. API endpoints
# ============================================================

class TestAugmentAPI:
    @pytest.fixture(autouse=True)
    def client(self):
        from fastapi.testclient import TestClient
        from api.main import app
        self.client = TestClient(app)

    def test_should_inject_endpoint_ok(self):
        r = self.client.post("/memory/should_inject", json={"prompt": "what was my job last year?"})
        assert r.status_code == 200
        data = r.json()
        assert "inject" in data
        assert isinstance(data["inject"], bool)

    def test_augment_endpoint_ok(self):
        r = self.client.post("/memory/augment", json={"prompt": "tell me about myself"})
        assert r.status_code == 200
        data = r.json()
        assert "augmented_prompt" in data
        assert "injected" in data

    def test_augment_with_force_inject(self):
        r = self.client.post("/memory/augment", json={"prompt": "hi", "force_inject": True})
        assert r.status_code == 200

    def test_should_inject_requires_prompt(self):
        r = self.client.post("/memory/should_inject", json={})
        assert r.status_code == 422  # Pydantic validation error

    def test_list_endpoint_exists(self):
        r = self.client.get("/memory/list")
        assert r.status_code == 200
        data = r.json()
        assert "memories" in data
        assert "total" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
