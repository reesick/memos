"""
sdk/client.py – Python SDK for MemoryOS
Wraps the REST API with retry logic, typed errors, and a clean interface.

Usage:
    from sdk.client import MemoryClient
    client = MemoryClient()
    client.add("My name is Alice and I work at Acme Corp.")
    result = client.search("what is Alice's job?")
    augmented = client.augment("Tell me about Alice.")["augmented_prompt"]
"""

import time
import httpx
from typing import Any, Dict, List, Optional


class MemoryOSError(Exception):
    """Raised when a MemoryOS API call fails."""
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class MemoryClient:
    """
    Python client for the MemoryOS REST API.

    Args:
        base_url:  URL of the running MemoryOS server.
        timeout:   Per-request timeout in seconds.
        retries:   Number of retry attempts on connection errors (exponential backoff).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
        retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    # ----------------------------------------------------------------
    # Internal
    # ----------------------------------------------------------------

    def _request(self, method: str, path: str, **kwargs) -> Dict:
        url = f"{self.base_url}{path}"
        last_exc: Exception = RuntimeError("No attempts made")

        for attempt in range(self.retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = getattr(client, method)(url, **kwargs)
                    if response.status_code >= 400:
                        try:
                            detail = response.json()
                        except Exception:
                            detail = response.text
                        raise MemoryOSError(
                            f"HTTP {response.status_code}: {detail}",
                            status_code=response.status_code,
                        )
                    return response.json()
            except MemoryOSError:
                raise  # 4xx/5xx — don't retry
            except httpx.ConnectError as e:
                last_exc = e
            except Exception as e:
                last_exc = e

            if attempt < self.retries - 1:
                time.sleep(0.5 * (2 ** attempt))  # 0.5s → 1s backoff

        raise MemoryOSError(
            f"Cannot connect to MemoryOS at {self.base_url} after {self.retries} attempts: {last_exc}"
        )

    # ----------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------

    def add(
        self,
        content: str,
        source_type: str = "text",
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Dict:
        """
        Store content in memory.
        Returns facts_extracted, facts_added, facts_updated, memory_ids, processing_ms.
        """
        return self._request("post", "/memory/add", json={
            "content": content,
            "source_type": source_type,
            "session_id": session_id,
            "metadata": metadata or {},
        })

    def search(
        self,
        query: str,
        top_k: int = 5,
        include_expired: bool = False,
        source_filter: Optional[str] = None,
        session_filter: Optional[str] = None,
    ) -> Dict:
        """
        Hybrid search (FAISS + BM25 + Kuzu graph).
        Returns results list and assembled context string.
        """
        return self._request("post", "/memory/search", json={
            "query": query,
            "top_k": top_k,
            "include_expired": include_expired,
            "source_filter": source_filter,
            "session_filter": session_filter,
        })

    def augment(
        self,
        prompt: str,
        top_k: int = 3,
        force_inject: bool = False,
    ) -> Dict:
        """
        Augment a prompt with relevant memory context.
        Returns augmented_prompt, injected bool, context_added list.
        """
        return self._request("post", "/memory/augment", json={
            "prompt": prompt,
            "top_k": top_k,
            "force_inject": force_inject,
        })

    def should_inject(self, prompt: str) -> Dict:
        """
        Lightweight check: does this prompt need memory context? (< 50ms, no LLM).
        Returns inject bool, confidence float, reason string.
        """
        return self._request("post", "/memory/should_inject", json={"prompt": prompt})

    def delete(self, memory_id: str) -> Dict:
        """Delete a specific memory from all three stores by memory_id."""
        return self._request("delete", f"/memory/{memory_id}")

    def get_graph(self, entity: str, hops: int = 2) -> Dict:
        """Return entity relationship subgraph from Kuzu (up to 4 hops)."""
        return self._request("get", "/memory/graph", params={"entity": entity, "hops": hops})

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        include_expired: bool = False,
        source_filter: Optional[str] = None,
        session_filter: Optional[str] = None,
    ) -> Dict:
        """List stored memories, paginated newest-first."""
        params: Dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "include_expired": include_expired,
        }
        if source_filter:
            params["source_filter"] = source_filter
        if session_filter:
            params["session_filter"] = session_filter
        return self._request("get", "/memory/list", params=params)

    def health(self) -> Dict:
        """Check if the MemoryOS server is running and which LLM provider is active."""
        return self._request("get", "/health")
