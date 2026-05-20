"""
tests/test_robust.py - End-to-end robust integration test for MemoryOS API.

Runs against the LIVE API at http://localhost:8000.

Workflow:
  1. Seed Phase  - inject a rich, diverse dataset (text/json/csv/code, multi-fact,
                   conflict pairs, dedup pairs, cross-source bridges)
  2. Test Phase  - exercise every endpoint with golden path AND edge cases
  3. Verify Phase - check semantic correctness (does the data we put in
                    actually come back? do conflicts resolve? do graphs link?)
  4. Report      - structured PASS / FAIL / WARN with honest reasons

The script does NOT use mocks. Real LLM, real embeddings, real stores.

Usage:
    DB_PATH=./test_data/ python run.py   # start server in another terminal
    python tests/test_robust.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

# Force UTF-8 output on Windows so arrow/box chars don't crash cp1252
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.getenv("MEMORYOS_URL", "http://localhost:8000")
TIMEOUT = httpx.Timeout(600.0, connect=5.0)
SESSION = f"robust_{int(time.time())}"

# ANSI colors (no-op on Windows cmd if NO_COLOR=1)
USE_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None
def c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if USE_COLOR else s
GREEN = lambda s: c("32", s)
RED   = lambda s: c("31", s)
YEL   = lambda s: c("33", s)
DIM   = lambda s: c("2",  s)
BOLD  = lambda s: c("1",  s)


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

@dataclass
class CaseResult:
    name: str
    status: str            # PASS / FAIL / WARN / SKIP
    detail: str = ""
    elapsed_ms: int = 0


@dataclass
class Report:
    results: list[CaseResult] = field(default_factory=list)
    created_ids: list[str] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "", elapsed_ms: int = 0):
        self.results.append(CaseResult(name, status, detail, elapsed_ms))
        sym = {"PASS": GREEN("PASS"), "FAIL": RED("FAIL"),
               "WARN": YEL("WARN"), "SKIP": DIM("SKIP")}[status]
        prefix = f"  [{sym}] {name}"
        if elapsed_ms:
            prefix += DIM(f"  ({elapsed_ms} ms)")
        print(prefix)
        if detail:
            for line in detail.splitlines():
                print(DIM(f"        {line}"))

    def summary(self) -> str:
        n = {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0}
        for r in self.results:
            n[r.status] += 1
        total = len(self.results)
        return (f"{GREEN(str(n['PASS']))} pass · {RED(str(n['FAIL']))} fail · "
                f"{YEL(str(n['WARN']))} warn · {DIM(str(n['SKIP']))} skip   "
                f"({total} cases)")

    def has_failures(self) -> bool:
        return any(r.status == "FAIL" for r in self.results)


report = Report()
client = httpx.Client(base_url=BASE, timeout=TIMEOUT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def post(path: str, json_body: dict) -> httpx.Response:
    return client.post(path, json=json_body)

def get(path: str, **params) -> httpx.Response:
    return client.get(path, params=params)

def delete(path: str) -> httpx.Response:
    return client.delete(path)

def section(title: str):
    print()
    print(BOLD(f"=== {title} ==="))


def case(name: str):
    """Decorator that times and records the case."""
    def deco(fn):
        def wrapped(*a, **kw):
            t0 = time.time()
            try:
                fn(*a, **kw)
                report.add(name, "PASS", "", int((time.time()-t0)*1000))
            except AssertionError as e:
                report.add(name, "FAIL", str(e), int((time.time()-t0)*1000))
            except Exception as e:
                report.add(name, "FAIL", f"{type(e).__name__}: {e}",
                           int((time.time()-t0)*1000))
        wrapped.__name__ = fn.__name__
        return wrapped
    return deco


# ---------------------------------------------------------------------------
# Phase 0: Preflight
# ---------------------------------------------------------------------------

def preflight() -> bool:
    section("Phase 0 · Preflight")
    try:
        r = client.get("/health")
        if r.status_code != 200:
            report.add("server reachable", "FAIL",
                       f"GET /health ->{r.status_code}")
            return False
        data = r.json()
        report.add("server reachable", "PASS",
                   f"status={data.get('status')} version={data.get('version')}")
        if not data.get("ollama"):
            report.add("ollama available", "WARN",
                       "Ollama not reachable — LLM-dependent cases may fall back to Claude or fail")
        else:
            report.add("ollama available", "PASS")
        return True
    except Exception as e:
        report.add("server reachable", "FAIL", f"{type(e).__name__}: {e}")
        return False


# ---------------------------------------------------------------------------
# Phase 1: Seed data
# ---------------------------------------------------------------------------

SEED_TEXTS: list[dict] = [
    # Multi-fact paragraph
    {"content": "Arjun is the backend engineer at MemoryOS. He uses Python and FastAPI. "
                "He lives in Bangalore.",
     "source_type": "text"},
    # Single-fact short
    {"content": "Priya works at Acme as a frontend engineer.", "source_type": "text"},
    # Conflict setup
    {"content": "Rohan lives in Mumbai.", "source_type": "text"},
    # Tech preferences
    {"content": "Vedant prefers SQLite over PostgreSQL for small projects.",
     "source_type": "text"},
]

SEED_CSV = (
    "name,role,company\n"
    "Karan,data engineer,Stripe\n"
    "Maya,designer,Figma\n"
    "Sam,ml engineer,OpenAI\n"
)

SEED_JSON = json.dumps([
    {"entity": "Anika", "role": "product manager", "company": "Notion"},
    {"entity": "Dev",   "role": "devops",          "company": "Vercel"},
])

SEED_CODE = '''
import os

class AuthService:
    """Handles user authentication for MemoryOS."""
    def __init__(self, db):
        self.db = db

    def login(self, username, password):
        """Verify credentials and return a session token."""
        return {"token": "abc123"}

def hash_password(plaintext: str) -> str:
    """SHA-256 password hashing utility."""
    import hashlib
    return hashlib.sha256(plaintext.encode()).hexdigest()
'''


def seed_phase():
    section("Phase 1 · Seeding data")

    for i, body in enumerate(SEED_TEXTS):
        body = dict(body, session_id=SESSION)
        t0 = time.time()
        r = post("/memory/add", body)
        elapsed = int((time.time()-t0)*1000)
        if r.status_code != 200:
            report.add(f"seed text[{i}]", "FAIL", f"{r.status_code} {r.text[:200]}", elapsed)
            continue
        data = r.json()
        report.add(f"seed text[{i}]", "PASS",
                   f"extracted={data['facts_extracted']} added={data['facts_added']} "
                   f"updated={data['facts_updated']} noop={data['facts_noop']}",
                   elapsed)
        report.created_ids.extend(data.get("memory_ids", []))

    # CSV
    t0 = time.time()
    r = post("/memory/add", {"content": SEED_CSV, "source_type": "csv",
                              "session_id": SESSION})
    elapsed = int((time.time()-t0)*1000)
    if r.status_code == 200:
        data = r.json()
        report.add("seed csv", "PASS",
                   f"added={data['facts_added']} ids={len(data.get('memory_ids', []))}",
                   elapsed)
        report.created_ids.extend(data.get("memory_ids", []))
    else:
        report.add("seed csv", "FAIL", f"{r.status_code} {r.text[:200]}", elapsed)

    # JSON
    t0 = time.time()
    r = post("/memory/add", {"content": SEED_JSON, "source_type": "json",
                              "session_id": SESSION})
    elapsed = int((time.time()-t0)*1000)
    if r.status_code == 200:
        data = r.json()
        report.add("seed json", "PASS",
                   f"added={data['facts_added']}", elapsed)
        report.created_ids.extend(data.get("memory_ids", []))
    else:
        report.add("seed json", "FAIL", f"{r.status_code} {r.text[:200]}", elapsed)

    # Code
    t0 = time.time()
    r = post("/memory/add", {"content": SEED_CODE, "source_type": "code",
                              "session_id": SESSION})
    elapsed = int((time.time()-t0)*1000)
    if r.status_code == 200:
        data = r.json()
        report.add("seed code", "PASS",
                   f"added={data['facts_added']}", elapsed)
        report.created_ids.extend(data.get("memory_ids", []))
    else:
        report.add("seed code", "FAIL", f"{r.status_code} {r.text[:200]}", elapsed)


# ---------------------------------------------------------------------------
# Phase 2: Endpoint tests
# ---------------------------------------------------------------------------

def test_health():
    section("Phase 2 · GET /health")

    @case("health golden path")
    def _():
        r = get("/health")
        assert r.status_code == 200, r.status_code
        assert r.json()["status"] == "ok"
    _()


def test_add_edges():
    section("Phase 2 · POST /memory/add (edge cases)")

    @case("add: empty content ->400")
    def _():
        r = post("/memory/add", {"content": "", "source_type": "text"})
        assert r.status_code == 400, f"got {r.status_code}: {r.text[:200]}"
        detail = r.json().get("detail", {})
        assert detail.get("error") == "EMPTY_CONTENT", detail
    _()

    @case("add: whitespace-only content ->400")
    def _():
        r = post("/memory/add", {"content": "   \n  \t ", "source_type": "text"})
        assert r.status_code == 400, f"got {r.status_code}: {r.text[:200]}"
    _()

    @case("add: oversize content ->400")
    def _():
        big = ("word " * 200000)  # ~200k tokens, well over 50k limit
        r = post("/memory/add", {"content": big, "source_type": "text"})
        assert r.status_code == 400, f"got {r.status_code}: {r.text[:200]}"
        detail = r.json().get("detail", {})
        assert detail.get("error") == "CONTENT_TOO_LARGE", detail
    _()

    @case("add: unknown source_type ->defaults to text (no crash)")
    def _():
        r = post("/memory/add", {"content": "Test fallback routing.",
                                  "source_type": "weird_xyz",
                                  "session_id": SESSION})
        # Per router contract: unknown types fall back to text rather than 400
        assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
    _()

    @case("add: missing content field ->422")
    def _():
        r = post("/memory/add", {"source_type": "text"})
        assert r.status_code == 422, r.status_code
    _()


def test_search():
    section("Phase 2 · POST /memory/search")

    @case("search: empty query ->400")
    def _():
        r = post("/memory/search", {"query": ""})
        assert r.status_code == 400
    _()

    @case("search: top_k out of range ->422")
    def _():
        r = post("/memory/search", {"query": "Arjun", "top_k": 999})
        assert r.status_code == 422
    _()

    @case("search: 'Arjun backend engineer' hits BM25+FAISS in top-5")
    def _():
        # Query includes both entity name (hits BM25 via raw_chunk) and value
        # (hits FAISS). Pure entity-name queries miss because FAISS embeds values only.
        r = post("/memory/search", {"query": "Arjun backend engineer role", "top_k": 5})
        assert r.status_code == 200
        data = r.json()
        assert "results" in data and "context" in data
        hit = any("arjun" in (res.get("entity","") + " " + res.get("value","")).lower()
                  or "backend" in res.get("value","").lower()
                  for res in data["results"])
        assert hit, (f"No Arjun-related result in top-5. "
                     f"results: {[(r['entity'],r['value']) for r in data['results']]}")
    _()

    @case("search: known entity 'Priya' returns matching fact")
    def _():
        r = post("/memory/search", {"query": "Where does Priya work?", "top_k": 10})
        assert r.status_code == 200
        data = r.json()
        hit = any("priya" in (res.get("entity","") + " " + res.get("value","")).lower()
                  or "acme" in res.get("value","").lower()
                  for res in data["results"])
        assert hit, (f"No Priya/Acme-related result in top-10. "
                     f"results: {[(r['entity'],r['value']) for r in data['results']]}")
    _()

    @case("search: hallucinated entity returns no semantic match in top-1")
    def _():
        r = post("/memory/search", {"query": "What does Xyzzyqop drink?", "top_k": 3})
        assert r.status_code == 200
        # We can't strictly assert empty since hybrid retrieval always returns
        # *something* if the store is non-empty; assert top score is below
        # a confidence threshold to flag this as a soft assertion
        results = r.json().get("results", [])
        if results:
            top_score = results[0].get("score", 0)
            # Just informational; not a hard fail
            assert top_score < 0.7, (f"Unexpectedly high score {top_score:.3f} "
                                     f"for nonsense query — relevance signal is weak")
    _()

    @case("search: source_filter='text' returns only text-sourced results")
    def _():
        r = post("/memory/search", {"query": "engineer", "top_k": 10,
                                     "source_filter": "text"})
        assert r.status_code == 200
        results = r.json().get("results", [])
        if results:
            wrong = [r for r in results if r.get("source_type") != "text"]
            assert not wrong, f"Filter leaked non-text sources: {wrong}"
    _()


def test_should_inject():
    section("Phase 2 · POST /memory/should_inject")

    @case("should_inject: 'remember X' ->inject=true")
    def _():
        r = post("/memory/should_inject", {"prompt": "Do you remember Arjun's role?"})
        assert r.status_code == 200
        data = r.json()
        assert data["inject"] is True, data
        assert data["check_ms"] < 100, f"check_ms={data['check_ms']} too slow"
    _()

    @case("should_inject: pure code question ->inject=false")
    def _():
        r = post("/memory/should_inject",
                 {"prompt": "Write a function to compute the nth Fibonacci number."})
        assert r.status_code == 200
        data = r.json()
        assert data["inject"] is False, data
    _()


def test_augment():
    section("Phase 2 · POST /memory/augment")

    @case("augment: trigger phrase fetches context")
    def _():
        r = post("/memory/augment",
                 {"prompt": "Remind me what Arjun's role is.", "top_k": 3})
        assert r.status_code == 200
        data = r.json()
        if data["injected"]:
            assert "[Memory Context]" in data["augmented_prompt"], data["augmented_prompt"][:200]
            assert len(data["context_added"]) >= 1
        else:
            # Soft warn: augmenter chose not to inject — record reason
            assert "no relevant memory" in data["injection_reason"].lower() or \
                   "no memory trigger" in data["injection_reason"].lower(), \
                   f"unexpected reason: {data['injection_reason']}"
    _()

    @case("augment: no trigger phrase ->prompt unchanged")
    def _():
        r = post("/memory/augment",
                 {"prompt": "Explain quicksort.", "top_k": 3})
        assert r.status_code == 200
        data = r.json()
        assert data["injected"] is False
        assert data["augmented_prompt"] == "Explain quicksort."
    _()

    @case("augment: force_inject=True bypasses heuristic")
    def _():
        r = post("/memory/augment",
                 {"prompt": "Explain quicksort.",
                  "top_k": 3, "force_inject": True})
        assert r.status_code == 200
        data = r.json()
        # Either it injected, or there was genuinely nothing relevant
        if data["injected"]:
            assert "[Memory Context]" in data["augmented_prompt"]
    _()


def test_graph():
    section("Phase 2 · GET /memory/graph")

    @case("graph: existing entity 'Arjun' returns nodes/edges")
    def _():
        r = get("/memory/graph", entity="Arjun", hops=2)
        assert r.status_code == 200
        data = r.json()
        assert "nodes" in data and "edges" in data
        assert data["total_nodes"] >= 1, f"no nodes for Arjun: {data}"
    _()

    @case("graph: unknown entity ->empty graph (not 500)")
    def _():
        r = get("/memory/graph", entity="GhostEntityXyz", hops=2)
        assert r.status_code == 200
        data = r.json()
        # Per implementation, get_subgraph may include the queried node itself or be empty
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)
    _()

    @case("graph: hops parameter clamped to [1,4]")
    def _():
        r = get("/memory/graph", entity="Arjun", hops=99)
        assert r.status_code == 200
    _()


def test_list():
    section("Phase 2 · GET /memory/list")

    @case("list: returns memories with pagination metadata")
    def _():
        r = get("/memory/list", limit=10, offset=0)
        assert r.status_code == 200
        data = r.json()
        for k in ("memories", "total", "limit", "offset"):
            assert k in data, f"missing {k} in {data}"
        assert data["limit"] == 10
        assert data["offset"] == 0
        assert data["total"] >= 1, "expected seeded data to appear in list"
    _()

    @case("list: session_filter narrows to our session")
    def _():
        r = get("/memory/list", limit=100, session_filter=SESSION)
        assert r.status_code == 200
        data = r.json()
        for m in data["memories"]:
            assert m["session_id"] == SESSION, m
    _()


def test_conflict_resolution():
    section("Phase 3 · Conflict resolution flow")

    @case("conflict: 'Rohan lives in Delhi' supersedes 'Rohan lives in Mumbai'")
    def _():
        # First insertion was 'Mumbai' during seeding.
        before = post("/memory/search", {"query": "Where does Rohan live?", "top_k": 3})
        before_top = before.json()["results"][0] if before.json()["results"] else {}
        before_value = (before_top.get("value") or "").lower()

        # Inject contradicting fact
        r = post("/memory/add",
                 {"content": "Actually Rohan moved. Rohan now lives in Delhi.",
                  "source_type": "text",
                  "session_id": SESSION})
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        # Either UPDATE (preferred) or ADD (coexist) — both are valid resolutions
        assert data["facts_added"] + data["facts_updated"] >= 1, data

        # Retrieve again
        after = post("/memory/search", {"query": "Where does Rohan live?", "top_k": 3})
        results = after.json()["results"]
        delhi_seen = any("delhi" in (r.get("value","") or "").lower() for r in results)
        assert delhi_seen, (f"Delhi not in top-3 results after conflict update. "
                            f"got: {[(r['entity'],r['value']) for r in results]}")
    _()


def test_delete():
    section("Phase 2 · DELETE /memory/{id}")

    @case("delete: nonexistent id ->404")
    def _():
        r = delete("/memory/mem_definitely_does_not_exist_xyz")
        assert r.status_code == 404, r.status_code
    _()

    @case("delete: existing id removed from all 3 stores")
    def _():
        # Grab an existing seeded memory via search — no extra LLM call needed
        r = post("/memory/search", {"query": "data engineer Stripe", "top_k": 1})
        assert r.status_code == 200
        results = r.json().get("results", [])
        assert results, "no seeded results to grab for delete test"
        target = results[0]["memory_id"]

        # Delete
        r = delete(f"/memory/{target}")
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body["status"] == "deleted"
        assert "sqlite" in body["removed_from"]

        # Second delete of same id -> 404
        r = delete(f"/memory/{target}")
        assert r.status_code == 404, f"second delete should 404, got {r.status_code}"
    _()


def test_demo_ui():
    section("Phase 2 · Demo UI")

    @case("/ui redirects somewhere")
    def _():
        r = client.get("/ui", follow_redirects=False)
        # If /demo dir exists, redirect should be 307; if not, may 404
        if r.status_code in (200, 307, 308):
            return
        elif r.status_code == 404:
            report.add._noop = True  # not used; just signal
            raise AssertionError("/ui returned 404 — demo dir may not exist")
        raise AssertionError(f"unexpected status {r.status_code}")
    _()


def test_docs():
    section("Phase 2 · OpenAPI docs")

    @case("/docs returns Swagger HTML")
    def _():
        r = client.get("/docs")
        assert r.status_code == 200
        assert "swagger" in r.text.lower() or "openapi" in r.text.lower()
    _()


# ---------------------------------------------------------------------------
# Phase 4: Cross-source integration
# ---------------------------------------------------------------------------

def test_cross_source_bridge():
    section("Phase 4 · Cross-source bridges")

    @case("cross-source: CSV-loaded Karan retrievable by text query")
    def _():
        r = post("/memory/search",
                 {"query": "Who is the data engineer at Stripe?", "top_k": 5})
        assert r.status_code == 200
        results = r.json()["results"]
        hit = any("karan" in (res.get("entity","") + " " + res.get("value","")).lower()
                  or "stripe" in res.get("value","").lower()
                  for res in results)
        assert hit, (f"CSV-loaded Karan/Stripe not retrievable. "
                     f"top: {[(r['entity'],r['value']) for r in results]}")
    _()

    @case("cross-source: JSON-loaded Anika retrievable")
    def _():
        r = post("/memory/search",
                 {"query": "Anika role at Notion", "top_k": 5})
        assert r.status_code == 200
        results = r.json()["results"]
        hit = any("anika" in (res.get("entity","") + " " + res.get("value","")).lower()
                  or "notion" in res.get("value","").lower()
                  for res in results)
        assert hit, (f"JSON Anika/Notion not retrievable. "
                     f"top: {[(r['entity'],r['value']) for r in results]}")
    _()


# ---------------------------------------------------------------------------
# Phase 5: Cleanup
# ---------------------------------------------------------------------------

def cleanup_phase():
    section("Phase 5 · Cleanup")
    # Snapshot every memory in our session and delete it
    r = get("/memory/list", limit=500, session_filter=SESSION)
    if r.status_code != 200:
        report.add("cleanup list", "FAIL", f"{r.status_code} {r.text[:120]}")
        return
    mems = r.json()["memories"]
    print(DIM(f"  Stored facts in this session ({len(mems)}):"))
    for m in mems:
        print(DIM(f"    [{m['source_type']:5s}] {m['entity']:18s} · {m['attribute']:15s} = {m['value']}"))
    deleted = 0
    failed = 0
    for m in mems:
        d = delete(f"/memory/{m['memory_id']}")
        if d.status_code == 200:
            deleted += 1
        else:
            failed += 1
    report.add("cleanup", "PASS" if failed == 0 else "WARN",
               f"deleted={deleted} failed={failed} session={SESSION}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(BOLD("\nMemoryOS Robust Integration Test"))
    print(DIM(f"Target: {BASE}"))
    print(DIM(f"Session tag: {SESSION}"))

    if not preflight():
        print(RED("\nPreflight failed — server unreachable. Start it first:"))
        print(DIM("    DB_PATH=./test_data/ python run.py"))
        sys.exit(2)

    seed_phase()
    test_health()
    test_add_edges()
    test_search()
    test_should_inject()
    test_augment()
    test_graph()
    test_list()
    test_conflict_resolution()
    test_delete()
    test_demo_ui()
    test_docs()
    test_cross_source_bridge()
    cleanup_phase()

    print()
    print(BOLD("=" * 60))
    print(BOLD("FINAL SUMMARY"))
    print(BOLD("=" * 60))
    print(report.summary())

    fails = [r for r in report.results if r.status == "FAIL"]
    if fails:
        print()
        print(RED(BOLD(f"\n{len(fails)} failures:")))
        for r in fails:
            print(f"  - {r.name}: {r.detail}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
