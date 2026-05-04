"""
tests/test_sdk.py – SDK unit tests
Tests MemoryClient without a running server by mocking httpx.Client.

Run: pytest tests/test_sdk.py -v
"""

import json
import sys
import os
import pytest
import httpx
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sdk.client import MemoryClient, MemoryOSError


# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------

def mock_response(status: int = 200, data: dict = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = data or {}
    resp.text = json.dumps(data or {})
    return resp


@pytest.fixture
def http(monkeypatch):
    """
    Patch httpx.Client so every test gets a clean mock HTTP client.
    Yields the inner instance — set .post/.get/.delete.return_value on it.
    """
    mock_instance = MagicMock()
    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
    mock_instance.__exit__ = MagicMock(return_value=False)

    mock_cls = MagicMock(return_value=mock_instance)
    monkeypatch.setattr(httpx, "Client", mock_cls)
    yield mock_instance


# ----------------------------------------------------------------
# add()
# ----------------------------------------------------------------

class TestAdd:
    def test_success(self, http):
        http.post.return_value = mock_response(200, {
            "status": "success", "facts_added": 2, "memory_ids": ["a", "b"],
        })
        result = MemoryClient().add("My name is Alice")
        assert result["status"] == "success"
        assert result["facts_added"] == 2

    def test_payload_fields(self, http):
        http.post.return_value = mock_response(200, {"status": "success"})
        MemoryClient().add("hello", source_type="code", session_id="s1")
        payload = http.post.call_args[1]["json"]
        assert payload["source_type"] == "code"
        assert payload["session_id"] == "s1"
        assert payload["content"] == "hello"

    def test_http_error_raises(self, http):
        http.post.return_value = mock_response(500, {"error": "STORE_WRITE_FAILED"})
        with pytest.raises(MemoryOSError) as exc:
            MemoryClient(retries=1).add("hello")
        assert exc.value.status_code == 500

    def test_404_raises(self, http):
        http.post.return_value = mock_response(404, {"detail": "not found"})
        with pytest.raises(MemoryOSError) as exc:
            MemoryClient(retries=1).add("hello")
        assert exc.value.status_code == 404


# ----------------------------------------------------------------
# search()
# ----------------------------------------------------------------

class TestSearch:
    def test_returns_results_and_context(self, http):
        http.post.return_value = mock_response(200, {
            "results": [{"memory_id": "m1", "entity": "Alice"}],
            "context": "• Alice job: engineer",
            "retrieval_ms": 12,
        })
        result = MemoryClient().search("Alice's job")
        assert "results" in result
        assert "context" in result
        assert result["retrieval_ms"] == 12

    def test_payload_top_k(self, http):
        http.post.return_value = mock_response(200, {"results": [], "context": ""})
        MemoryClient().search("test", top_k=10)
        payload = http.post.call_args[1]["json"]
        assert payload["top_k"] == 10


# ----------------------------------------------------------------
# augment()
# ----------------------------------------------------------------

class TestAugment:
    def test_returns_augmented_prompt(self, http):
        http.post.return_value = mock_response(200, {
            "augmented_prompt": "[Memory Context]\n...\n\nhi",
            "injected": True,
        })
        result = MemoryClient().augment("hi", force_inject=True)
        assert result["injected"] is True
        assert "augmented_prompt" in result

    def test_force_inject_in_payload(self, http):
        http.post.return_value = mock_response(200, {"augmented_prompt": "hi", "injected": False})
        MemoryClient().augment("hi", force_inject=True)
        payload = http.post.call_args[1]["json"]
        assert payload["force_inject"] is True


# ----------------------------------------------------------------
# should_inject()
# ----------------------------------------------------------------

class TestShouldInject:
    def test_returns_inject_bool(self, http):
        http.post.return_value = mock_response(200, {
            "inject": True, "confidence": 0.8, "reason": "trigger phrase found",
        })
        result = MemoryClient().should_inject("what was my previous job?")
        assert isinstance(result["inject"], bool)
        assert 0.0 <= result["confidence"] <= 1.0


# ----------------------------------------------------------------
# delete()
# ----------------------------------------------------------------

class TestDelete:
    def test_calls_correct_url(self, http):
        http.delete.return_value = mock_response(200, {"status": "deleted"})
        MemoryClient().delete("mem_abc123")
        url = http.delete.call_args[0][0]
        assert url.endswith("/memory/mem_abc123")

    def test_returns_deleted_status(self, http):
        http.delete.return_value = mock_response(200, {"status": "deleted", "memory_id": "x"})
        result = MemoryClient().delete("x")
        assert result["status"] == "deleted"


# ----------------------------------------------------------------
# list() and health()
# ----------------------------------------------------------------

class TestListAndHealth:
    def test_list_returns_memories(self, http):
        http.get.return_value = mock_response(200, {"memories": [], "total": 0})
        result = MemoryClient().list()
        assert "memories" in result
        assert result["total"] == 0

    def test_list_passes_params(self, http):
        http.get.return_value = mock_response(200, {"memories": [], "total": 0})
        MemoryClient().list(limit=10, offset=5)
        params = http.get.call_args[1]["params"]
        assert params["limit"] == 10
        assert params["offset"] == 5

    def test_health_ok(self, http):
        http.get.return_value = mock_response(200, {"status": "ok", "version": "1.0.0"})
        result = MemoryClient().health()
        assert result["status"] == "ok"


# ----------------------------------------------------------------
# Retry logic
# ----------------------------------------------------------------

class TestRetry:
    def test_retries_on_connect_error(self, http, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        http.post.side_effect = [
            httpx.ConnectError("refused"),
            httpx.ConnectError("refused"),
            mock_response(200, {"status": "success"}),
        ]
        result = MemoryClient(retries=3).add("hello")
        assert result["status"] == "success"
        assert http.post.call_count == 3

    def test_raises_after_all_retries_exhausted(self, http, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        http.post.side_effect = httpx.ConnectError("refused")
        with pytest.raises(MemoryOSError) as exc:
            MemoryClient(retries=2).add("hello")
        assert "Cannot connect" in str(exc.value)
        assert http.post.call_count == 2

    def test_no_retry_on_client_error(self, http, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda _: None)
        http.post.return_value = mock_response(400, {"error": "EMPTY_CONTENT"})
        with pytest.raises(MemoryOSError) as exc:
            MemoryClient(retries=3).add("")
        assert exc.value.status_code == 400
        assert http.post.call_count == 1  # No retry on 4xx


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
