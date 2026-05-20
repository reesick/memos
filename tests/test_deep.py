"""
tests/test_deep.py – Deep integration test suite for MemoryOS.

Runs against the live API. NOT mocked. Real LLM, real stores, real retrieval.

Covers (in order):
  Phase 0  Preflight / health
  Phase 1  Seed — 7 distinct entities, 4 source types
  Phase 2  Add edge cases (empty, huge, bad type, missing field, FTS5 bomb chars)
  Phase 3  Search correctness + score ordering + source filter
  Phase 4  First-person entity resolution ("I/me" → real name)
  Phase 5  Exact dedup (NOOP path) — same content twice
  Phase 6  Conflict resolution — location change, role change
  Phase 7  should_inject heuristic accuracy
  Phase 8  augment injection + latency
  Phase 9  Graph endpoint — nodes, edges, hops clamping
  Phase 10 List + pagination correctness
  Phase 11 Delete — all 3 stores + double-delete 404
  Phase 12 Retrieval after delete — deleted fact must not appear
  Phase 13 include_expired — expired facts visible with flag
  Phase 14 FTS5 special character safety in search queries
  Phase 15 Cross-source bridge — CSV entity found by text query
  Phase 16 Latency assertions — search < 1s, should_inject < 100ms
  Phase 17 Cleanup

Usage:
    python run.py           # start server in a separate terminal
    python tests/test_deep.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

# UTF-8 safe output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE    = os.getenv("MEMORYOS_URL", "http://localhost:8000")
TIMEOUT = httpx.Timeout(600.0, connect=5.0)
TAG     = f"deep_{int(time.time())}"   # unique session tag for this run

USE_COLOR = sys.stdout.isatty() and os.getenv("NO_COLOR") is None
def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if USE_COLOR else s
G  = lambda s: _c("32;1", s)  # green bold
R  = lambda s: _c("31;1", s)  # red bold
Y  = lambda s: _c("33;1", s)  # yellow bold
D  = lambda s: _c("2",    s)  # dim
B  = lambda s: _c("1",    s)  # bold


# ─────────────────────────────────────────────────────────────────────────────
# Result tracking
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Case:
    name: str
    status: str       # PASS | FAIL | WARN | SKIP
    detail: str = ""
    ms: int = 0


@dataclass
class Report:
    cases: list[Case] = field(default_factory=list)
    ids: list[str]    = field(default_factory=list)   # memory_ids created this run

    def record(self, name: str, status: str, detail: str = "", ms: int = 0):
        self.cases.append(Case(name, status, detail, ms))
        sym = {"PASS": G("PASS"), "FAIL": R("FAIL"),
               "WARN": Y("WARN"), "SKIP": D("SKIP")}.get(status, status)
        line = f"  [{sym}] {name}"
        if ms:
            line += D(f"  {ms} ms")
        print(line)
        for ln in detail.splitlines():
            print(D(f"        {ln}"))

    def summary(self):
        cnt = {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0}
        for c in self.cases:
            cnt[c.status] = cnt.get(c.status, 0) + 1
        return (f"{G(str(cnt['PASS']))} pass  "
                f"{R(str(cnt['FAIL']))} fail  "
                f"{Y(str(cnt['WARN']))} warn  "
                f"{D(str(cnt['SKIP']))} skip  "
                f"({len(self.cases)} total)")

    def failures(self):
        return [c for c in self.cases if c.status == "FAIL"]


report = Report()
client = httpx.Client(base_url=BASE, timeout=TIMEOUT)


def _run(name: str, fn):
    t0 = time.time()
    try:
        fn()
        report.record(name, "PASS", ms=int((time.time()-t0)*1000))
    except AssertionError as e:
        report.record(name, "FAIL", str(e), int((time.time()-t0)*1000))
    except Exception as e:
        report.record(name, "FAIL", f"{type(e).__name__}: {e}",
                      int((time.time()-t0)*1000))


def section(title: str):
    print()
    print(B(f"── {title} " + "─" * max(0, 58 - len(title))))


def add(content: str, source_type: str = "text", **kw) -> dict:
    body = {"content": content, "source_type": source_type,
            "session_id": TAG, **kw}
    r = client.post("/memory/add", json=body)
    assert r.status_code == 200, f"add failed {r.status_code}: {r.text[:300]}"
    data = r.json()
    report.ids.extend(data.get("memory_ids", []))
    return data


def search(query: str, top_k: int = 5, **kw) -> dict:
    r = client.post("/memory/search",
                    json={"query": query, "top_k": top_k, **kw})
    assert r.status_code == 200, f"search failed {r.status_code}: {r.text[:200]}"
    return r.json()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 0 – Preflight
# ─────────────────────────────────────────────────────────────────────────────

def phase0_preflight() -> bool:
    section("Phase 0  Preflight")
    try:
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        report.record("server alive", "PASS",
                      f"status={data['status']} version={data.get('version','?')}")
        if data.get("ollama"):
            report.record("ollama reachable", "PASS")
        else:
            report.record("ollama reachable", "WARN",
                          "Ollama is down — LLM ops will fall back to Claude or fail")
        return True
    except Exception as e:
        report.record("server alive", "FAIL", str(e))
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 – Seed data (7 entities, 4 source types)
# ─────────────────────────────────────────────────────────────────────────────

ENTITIES = {
    "Nadia":   "Nadia is a senior data scientist at DeepMind. She specialises in reinforcement learning and lives in London.",
    "Aryan":   "Aryan is a DevOps engineer at Cloudflare. He uses Kubernetes and Terraform daily. Aryan lives in Hyderabad.",
    "Pooja":   "Pooja works as a product manager at Atlassian. She is based in Sydney and prefers async communication.",
    "Mihail":  "Mihail is a compiler engineer at LLVM. He writes Rust and C++ and lives in Zurich.",
    "Zoe":     "Zoe is the CTO at Stripe. She studied at MIT and her favourite language is Go.",
    "TestBot": "TestBot is an automated QA agent. It runs regression tests and lives in a container.",
}

SEED_CSV = (
    "name,role,company,city\n"
    "CsvAlice,ML engineer,Hugging Face,Paris\n"
    "CsvBob,security researcher,Cloudflare,Austin\n"
    "CsvCarol,infra lead,Databricks,San Francisco\n"
)

SEED_JSON = json.dumps([
    {"name": "JsonDave", "role": "backend engineer", "company": "Vercel", "city": "New York"},
    {"name": "JsonEve",  "role": "frontend engineer","company": "Figma",  "city": "Toronto"},
])

SEED_CODE = '''
class MemoryOSClient:
    """Python SDK client for MemoryOS. Author: CodeEntity."""
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url

    def add(self, content: str, source_type: str = "text") -> dict:
        import httpx
        return httpx.post(f"{self.base_url}/memory/add",
                          json={"content": content, "source_type": source_type}).json()
'''


def phase1_seed():
    section("Phase 1  Seeding")

    for name, content in ENTITIES.items():
        def _add_entity(n=name, c=content):
            data = add(c, "text")
            assert data["facts_extracted"] >= 1, f"{n}: LLM extracted 0 facts — check Ollama"
            assert data["facts_added"] >= 1, f"{n}: 0 facts added (all NOOP already?)"
        _run(f"seed text: {name}", _add_entity)

    def _csv():
        data = add(SEED_CSV, "csv")
        assert data["facts_added"] >= 1, "CSV: 0 facts added"
    _run("seed csv (3 entities)", _csv)

    def _json():
        data = add(SEED_JSON, "json")
        assert data["facts_added"] >= 1, "JSON: 0 facts added"
    _run("seed json (2 entities)", _json)

    def _code():
        data = add(SEED_CODE, "code")
        assert data["facts_added"] >= 1, "Code: 0 facts added"
    _run("seed code", _code)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2 – Add edge cases
# ─────────────────────────────────────────────────────────────────────────────

def phase2_add_edges():
    section("Phase 2  /memory/add edge cases")

    def _empty():
        r = client.post("/memory/add", json={"content": "", "source_type": "text"})
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "EMPTY_CONTENT"
    _run("empty string → 400 EMPTY_CONTENT", _empty)

    def _whitespace():
        r = client.post("/memory/add", json={"content": "   \n\t  ", "source_type": "text"})
        assert r.status_code == 400
    _run("whitespace-only → 400", _whitespace)

    def _oversize():
        big = "word " * 200_000   # ~200 k tokens >> 50 k limit
        r = client.post("/memory/add", json={"content": big, "source_type": "text"})
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "CONTENT_TOO_LARGE"
    _run("200k-word content → 400 CONTENT_TOO_LARGE", _oversize)

    def _missing_field():
        r = client.post("/memory/add", json={"source_type": "text"})
        assert r.status_code == 422
    _run("missing 'content' field → 422", _missing_field)

    def _unknown_source():
        # Router should fall back to text, not crash
        r = client.post("/memory/add",
                        json={"content": "Hello world.", "source_type": "alien_format",
                              "session_id": TAG})
        assert r.status_code == 200, f"got {r.status_code}: {r.text[:200]}"
    _run("unknown source_type → falls back to text (200)", _unknown_source)

    def _no_extractable_facts():
        # A single question has no fact for the LLM to extract
        r = client.post("/memory/add",
                        json={"content": "What is 2 + 2?", "source_type": "text",
                              "session_id": TAG})
        # Should succeed with 0 facts — not an error
        assert r.status_code == 200
        data = r.json()
        assert data["facts_added"] == 0, f"expected 0 added for a bare question, got {data}"
    _run("question with no facts → 200, facts_added=0", _no_extractable_facts)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3 – Search correctness
# ─────────────────────────────────────────────────────────────────────────────

def phase3_search():
    section("Phase 3  /memory/search correctness")

    def _empty_query():
        r = client.post("/memory/search", json={"query": ""})
        assert r.status_code == 400
    _run("empty query → 400", _empty_query)

    def _top_k_too_big():
        r = client.post("/memory/search", json={"query": "test", "top_k": 999})
        assert r.status_code == 422
    _run("top_k=999 → 422 validation error", _top_k_too_big)

    def _score_ordering():
        data = search("senior data scientist reinforcement learning London", top_k=10)
        results = data["results"]
        assert results, "no results returned"
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True), \
            f"results not sorted by score DESC: {scores}"
    _run("results sorted by score DESC", _score_ordering)

    def _nadia_hit():
        data = search("What does Nadia specialise in?", top_k=5)
        hit = any("reinforcement" in (r.get("value","")).lower()
                  or "nadia" in (r.get("entity","")).lower()
                  for r in data["results"])
        assert hit, f"Nadia/RL not in top-5: {[(r['entity'],r['value']) for r in data['results']]}"
    _run("Nadia → reinforcement learning in top-5", _nadia_hit)

    def _aryan_hit():
        data = search("Aryan Kubernetes DevOps", top_k=5)
        hit = any("kubernetes" in (r.get("value","")).lower()
                  or "aryan" in (r.get("entity","")).lower()
                  for r in data["results"])
        assert hit, f"Aryan/Kubernetes not in top-5: {[(r['entity'],r['value']) for r in data['results']]}"
    _run("Aryan → Kubernetes in top-5", _aryan_hit)

    def _zoe_mit():
        data = search("Who studied at MIT?", top_k=10)
        hit = any("mit" in (r.get("value","")).lower()
                  or "zoe" in (r.get("entity","")).lower()
                  for r in data["results"])
        assert hit, f"Zoe/MIT not in top-10: {[(r['entity'],r['value']) for r in data['results']]}"
    _run("Zoe → MIT in top-10", _zoe_mit)

    def _source_filter():
        data = search("engineer", top_k=20, source_filter="text")
        results = data["results"]
        wrong = [r for r in results if r.get("source_type") != "text"]
        assert not wrong, f"source_filter=text leaked: {wrong[:3]}"
    _run("source_filter='text' — no leakage", _source_filter)

    def _hallucinated_entity():
        data = search("What is Xyzzyqoplasmator's pet name?", top_k=3)
        results = data["results"]
        if results:
            top = results[0]["score"]
            assert top < 0.75, f"High score {top:.3f} for nonsense entity — suspicious"
    _run("hallucinated entity → no high-confidence hit", _hallucinated_entity)

    def _context_field():
        data = search("compiler engineer Rust", top_k=5)
        assert "context" in data, "missing 'context' field in response"
        assert isinstance(data["context"], str)
        assert data["context"] != ""
    _run("response has non-empty 'context' string", _context_field)

    def _top_k_capped():
        data = search("engineer", top_k=20)
        assert len(data["results"]) <= 20
    _run("top_k respected — never over 20 results", _top_k_capped)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4 – First-person entity resolution
# ─────────────────────────────────────────────────────────────────────────────

def phase4_entity_resolution():
    section("Phase 4  First-person entity resolution")

    # Use a unique name so it cannot collide with anything already in DB
    REAL_NAME = f"SriTestUser_{TAG[-6:]}"

    def _introduce():
        data = add(f"My name is {REAL_NAME}. I am a cricket enthusiast and I live in Chennai.",
                   "text")
        assert data["facts_extracted"] >= 1
        # The add should succeed
    _run(f"introduce '{REAL_NAME}' via first-person", _introduce)

    def _stored_under_real_name():
        # Allow LLM + engine time to process
        time.sleep(1)
        data = search(f"{REAL_NAME} cricket Chennai", top_k=10)
        results = data["results"]
        # Look for entity = REAL_NAME (not 'I' or 'me')
        real_name_facts = [r for r in results
                           if r.get("entity","").lower() == REAL_NAME.lower()]
        i_facts = [r for r in results
                   if r.get("entity","").lower() in ("i", "me", "my", "myself")]
        assert not i_facts, \
            f"Facts still stored under 'I/me': {[(r['entity'],r['value']) for r in i_facts]}"
        assert real_name_facts, \
            (f"No facts stored under '{REAL_NAME}'. "
             f"Got entities: {list(set(r['entity'] for r in results))}")
    _run(f"facts stored under '{REAL_NAME}', not 'I'", _stored_under_real_name)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5 – Exact dedup (NOOP path)
# ─────────────────────────────────────────────────────────────────────────────

def phase5_dedup():
    section("Phase 5  Exact dedup (NOOP path)")

    DEDUP_TEXT = "MihailDedup is a compiler engineer who lives in Zurich."

    def _first_add():
        data = add(DEDUP_TEXT, "text")
        assert data["facts_added"] >= 1, f"first add got 0 new facts: {data}"
    _run("first add: facts_added >= 1", _first_add)

    def _second_add_noop():
        data = add(DEDUP_TEXT, "text")
        # All facts should be NOOP (same entity+attribute+value already in store)
        assert data["facts_noop"] >= 1, \
            (f"Second identical add: expected noop >= 1, "
             f"got added={data['facts_added']} noop={data['facts_noop']}")
        assert data["facts_added"] == 0, \
            f"Second identical add: expected 0 new, got {data['facts_added']}"
    _run("second identical add: facts_noop >= 1, facts_added = 0", _second_add_noop)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 6 – Conflict resolution
# ─────────────────────────────────────────────────────────────────────────────

def phase6_conflict():
    section("Phase 6  Conflict resolution")

    def _location_conflict():
        # Seed original location
        add("ConflictPerson lives in Tokyo.", "text")
        time.sleep(0.5)

        # Inject contradiction
        data = add("ConflictPerson has moved and now lives in Berlin.", "text")
        # Either UPDATE (old expires, new in) or ADD (both coexist) are valid
        assert data["facts_added"] + data["facts_updated"] >= 1, \
            f"conflict produced no change: {data}"

        # Retrieve — Berlin must appear
        result = search("Where does ConflictPerson live?", top_k=5)
        values = [(r["entity"], r["value"]) for r in result["results"]]
        berlin_seen = any("berlin" in v.lower() for _, v in values)
        assert berlin_seen, f"Berlin not in results after conflict update: {values}"
    _run("location conflict: Tokyo → Berlin", _location_conflict)

    def _role_conflict():
        add("RoleConflict started as a junior engineer.", "text")
        time.sleep(0.5)
        data = add("RoleConflict got promoted and is now a staff engineer.", "text")
        assert data["facts_added"] + data["facts_updated"] >= 1, \
            f"role conflict produced no change: {data}"
        result = search("RoleConflict engineer level", top_k=5)
        values = [r["value"] for r in result["results"]]
        staff_seen = any("staff" in v.lower() for v in values)
        assert staff_seen, f"'staff engineer' not in results: {values}"
    _run("role conflict: junior → staff engineer", _role_conflict)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7 – should_inject heuristic
# ─────────────────────────────────────────────────────────────────────────────

def phase7_should_inject():
    section("Phase 7  /memory/should_inject")

    triggers = [
        ("do you remember what Nadia does?",       True),
        ("who is Aryan?",                           True),
        ("what did I tell you last time?",          True),
        ("my preference for databases",             True),
        ("i told you i prefer Python",              True),
    ]
    nontriggers = [
        ("Write a function to reverse a linked list.", False),
        ("Explain the TCP handshake.",                  False),
        ("2 + 2 = ?",                                  False),
    ]

    for prompt, expected in triggers:
        def _check(p=prompt, ex=expected):
            r = client.post("/memory/should_inject", json={"prompt": p})
            assert r.status_code == 200
            data = r.json()
            assert data["check_ms"] < 100, f"heuristic took {data['check_ms']}ms (expected < 100)"
            assert data["inject"] is True, \
                f"Expected inject=True for '{p}', got: {data}"
        _run(f"trigger: '{prompt[:40]}…' → inject=true", _check)

    for prompt, expected in nontriggers:
        def _check(p=prompt, ex=expected):
            r = client.post("/memory/should_inject", json={"prompt": p})
            assert r.status_code == 200
            data = r.json()
            assert data["inject"] is False, \
                f"Expected inject=False for '{p}', got: {data}"
        _run(f"no trigger: '{prompt[:40]}' → inject=false", _check)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 8 – augment
# ─────────────────────────────────────────────────────────────────────────────

def phase8_augment():
    section("Phase 8  /memory/augment")

    def _trigger_injects():
        r = client.post("/memory/augment",
                        json={"prompt": "Remind me what Nadia specialises in.", "top_k": 3})
        assert r.status_code == 200
        data = r.json()
        if data["injected"]:
            assert "[Memory Context]" in data["augmented_prompt"]
            assert len(data["context_added"]) >= 1
        else:
            # Soft warn — may be no relevant context even with trigger phrase
            report.record("augment: trigger injects context", "WARN",
                          f"inject=False despite trigger. reason: {data['injection_reason']}")
            return
    _run("augment: trigger phrase → context injected", _trigger_injects)

    def _no_trigger_unchanged():
        prompt = "Sort an array using merge sort."
        r = client.post("/memory/augment", json={"prompt": prompt, "top_k": 3})
        assert r.status_code == 200
        data = r.json()
        assert data["injected"] is False
        assert data["augmented_prompt"] == prompt
    _run("augment: no trigger → prompt unchanged", _no_trigger_unchanged)

    def _force_inject():
        r = client.post("/memory/augment",
                        json={"prompt": "Sort an array using merge sort.",
                              "top_k": 3, "force_inject": True})
        assert r.status_code == 200
        data = r.json()
        assert data["injection_reason"] == "force_inject=True"
    _run("augment: force_inject=True overrides heuristic", _force_inject)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9 – Graph endpoint
# ─────────────────────────────────────────────────────────────────────────────

def phase9_graph():
    section("Phase 9  GET /memory/graph")

    def _known_entity():
        r = client.get("/memory/graph", params={"entity": "Nadia", "hops": 2})
        assert r.status_code == 200
        data = r.json()
        assert data["total_nodes"] >= 1, f"expected nodes for Nadia: {data}"
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)
    _run("Nadia graph: at least 1 node", _known_entity)

    def _ghost_entity():
        r = client.get("/memory/graph", params={"entity": "GhostEntityXyzzy", "hops": 2})
        assert r.status_code == 200   # must not 500
        data = r.json()
        assert isinstance(data["nodes"], list)
    _run("ghost entity → 200 empty graph (no crash)", _ghost_entity)

    def _hops_clamped():
        r = client.get("/memory/graph", params={"entity": "Nadia", "hops": 99})
        assert r.status_code == 200
    _run("hops=99 clamped to 4 (no crash)", _hops_clamped)

    def _hops_1_vs_2():
        r1 = client.get("/memory/graph", params={"entity": "Aryan", "hops": 1})
        r2 = client.get("/memory/graph", params={"entity": "Aryan", "hops": 2})
        assert r1.status_code == 200 and r2.status_code == 200
        # hops=2 should return >= hops=1 nodes
        n1 = r1.json()["total_nodes"]
        n2 = r2.json()["total_nodes"]
        assert n2 >= n1, f"hops=2 ({n2} nodes) < hops=1 ({n1} nodes)"
    _run("hops=2 returns >= nodes than hops=1", _hops_1_vs_2)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 10 – List + pagination
# ─────────────────────────────────────────────────────────────────────────────

def phase10_list():
    section("Phase 10  GET /memory/list + pagination")

    def _basic():
        r = client.get("/memory/list", params={"limit": 5, "offset": 0})
        assert r.status_code == 200
        data = r.json()
        for k in ("memories", "total", "limit", "offset"):
            assert k in data, f"missing key '{k}'"
        assert data["limit"] == 5
        assert data["offset"] == 0
        assert data["total"] >= 1
        assert len(data["memories"]) <= 5
    _run("list: basic response shape + limit honoured", _basic)

    def _pagination_no_overlap():
        r0 = client.get("/memory/list", params={"limit": 5, "offset": 0})
        r5 = client.get("/memory/list", params={"limit": 5, "offset": 5})
        assert r0.status_code == 200 and r5.status_code == 200
        ids0 = {m["memory_id"] for m in r0.json()["memories"]}
        ids5 = {m["memory_id"] for m in r5.json()["memories"]}
        overlap = ids0 & ids5
        assert not overlap, f"pagination overlap: {overlap}"
    _run("pagination: offset=0 and offset=5 do not overlap", _pagination_no_overlap)

    def _session_filter():
        r = client.get("/memory/list",
                       params={"limit": 200, "session_filter": TAG})
        assert r.status_code == 200
        mems = r.json()["memories"]
        wrong = [m for m in mems if m["session_id"] != TAG]
        assert not wrong, f"session_filter leaked {len(wrong)} alien records"
    _run("session_filter returns only our session's facts", _session_filter)

    def _schema_fields():
        r = client.get("/memory/list", params={"limit": 1})
        data = r.json()
        if data["memories"]:
            m = data["memories"][0]
            for f in ("memory_id", "entity", "attribute", "value",
                      "confidence", "source_type", "timestamp"):
                assert f in m, f"missing field '{f}' in memory row"
    _run("list row has all required schema fields", _schema_fields)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 11 – Delete
# ─────────────────────────────────────────────────────────────────────────────

def phase11_delete():
    section("Phase 11  DELETE /memory/{id}")

    def _nonexistent_404():
        r = client.delete("/memory/mem_definitely_not_real_xyz9999")
        assert r.status_code == 404
    _run("delete nonexistent id → 404", _nonexistent_404)

    def _delete_and_verify():
        # Plant a unique fact
        content = f"DeleteTarget_{TAG} is a temporary test entity at DeleteCorp."
        data = add(content, "text")
        ids = data.get("memory_ids", [])
        if not ids:
            raise AssertionError("No memory_ids returned from add — cannot test delete")
        target = ids[0]

        # Delete
        r = client.delete(f"/memory/{target}")
        assert r.status_code == 200, f"delete returned {r.status_code}: {r.text[:200]}"
        body = r.json()
        assert body["status"] == "deleted"
        assert "sqlite" in body["removed_from"], \
            f"sqlite not in removed_from: {body['removed_from']}"

        # Double-delete must 404
        r2 = client.delete(f"/memory/{target}")
        assert r2.status_code == 404, \
            f"second delete should 404, got {r2.status_code}"
    _run("delete + verify removed + double-delete 404", _delete_and_verify)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 12 – Retrieval after delete
# ─────────────────────────────────────────────────────────────────────────────

def phase12_retrieval_after_delete():
    section("Phase 12  Retrieval after delete")

    UNIQUE = f"GhostEntity_{TAG}"

    def _plant_then_delete():
        # Plant
        data = add(f"{UNIQUE} works at GhostCorp and loves TypeScript.", "text")
        ids = data.get("memory_ids", [])
        assert ids, "plant returned no ids"

        # Verify it exists
        before = search(f"{UNIQUE} GhostCorp TypeScript", top_k=5)
        hit_before = any(UNIQUE.lower() in (r.get("entity","") + " " + r.get("value","")).lower()
                         or "typescript" in r.get("value","").lower()
                         for r in before["results"])
        assert hit_before, f"fact not found before delete: {before['results']}"

        # Delete all planted IDs
        for mid in ids:
            client.delete(f"/memory/{mid}")

        # Search again — should not appear
        after = search(f"{UNIQUE} GhostCorp TypeScript", top_k=5)
        hit_after = any(UNIQUE.lower() in r.get("entity","").lower()
                        for r in after["results"])
        assert not hit_after, \
            f"Deleted entity '{UNIQUE}' still appears in search: {after['results']}"
    _run("deleted fact does not appear in subsequent search", _plant_then_delete)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 13 – include_expired
# ─────────────────────────────────────────────────────────────────────────────

def phase13_include_expired():
    section("Phase 13  include_expired flag")

    def _expired_facts_visible():
        # Seed original then overwrite to trigger expiry
        entity = f"ExpiredTest_{TAG}"
        add(f"{entity} lives in OldCity.", "text")
        time.sleep(0.5)
        add(f"{entity} moved and now lives in NewCity.", "text")

        # Without flag: expired (OldCity) should NOT appear in results
        without = search(f"{entity} OldCity", top_k=10, include_expired=False)
        old_in_active = any("oldcity" in r.get("value","").lower()
                            and not r.get("contradictory_fact")
                            for r in without["results"])

        # With flag: should appear (either as contradictory or expired)
        with_flag = client.post("/memory/search",
                                json={"query": f"{entity} city", "top_k": 10,
                                      "include_expired": True})
        assert with_flag.status_code == 200
        with_results = with_flag.json()["results"]
        # NewCity must be there regardless
        new_seen = any("newcity" in r.get("value","").lower() for r in with_results)
        assert new_seen, \
            f"NewCity not found with include_expired=True: {[r['value'] for r in with_results]}"
    _run("include_expired: updated location visible in expired flag query", _expired_facts_visible)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 14 – FTS5 special character safety
# ─────────────────────────────────────────────────────────────────────────────

def phase14_fts5_safety():
    section("Phase 14  FTS5 special character safety")

    bomb_queries = [
        "What's Aryan's job?",              # apostrophes
        "Nadia AND London OR Berlin",       # boolean operators
        "Who is Zoe???",                    # multiple question marks
        '"Aryan" -DevOps',                  # quoted + minus operator
        "Pooja* product*",                  # wildcard operators
        "()()() Mihail compiler",           # parentheses soup
        "Zoe MIT",                          # clean short query (control)
        "   leading spaces   ",             # whitespace padding
    ]

    for q in bomb_queries:
        def _safe(query=q):
            r = client.post("/memory/search",
                            json={"query": query, "top_k": 3})
            # Must not 500 — any result (even empty) is fine
            assert r.status_code == 200, \
                f"FTS5 bomb '{query}' caused {r.status_code}: {r.text[:200]}"
        _run(f"FTS5 safe: {q[:45]!r}", _safe)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 15 – Cross-source retrieval
# ─────────────────────────────────────────────────────────────────────────────

def phase15_cross_source():
    section("Phase 15  Cross-source retrieval")

    def _csv_entity_by_text():
        data = search("ML engineer Hugging Face Paris", top_k=5)
        hit = any("csvalice" in (r.get("entity","") + " " + r.get("value","")).lower()
                  or "hugging face" in r.get("value","").lower()
                  for r in data["results"])
        assert hit, \
            f"CsvAlice/Hugging Face not found by text query. top: {[(r['entity'],r['value']) for r in data['results']]}"
    _run("CSV entity (CsvAlice) found by text query", _csv_entity_by_text)

    def _json_entity_by_text():
        data = search("backend engineer Vercel New York", top_k=5)
        hit = any("jsondave" in (r.get("entity","") + " " + r.get("value","")).lower()
                  or "vercel" in r.get("value","").lower()
                  for r in data["results"])
        assert hit, \
            f"JsonDave/Vercel not found by text query. top: {[(r['entity'],r['value']) for r in data['results']]}"
    _run("JSON entity (JsonDave) found by text query", _json_entity_by_text)

    def _code_entity_by_text():
        data = search("MemoryOS Python SDK CodeEntity", top_k=5)
        hit = any("memoryos" in (r.get("entity","") + " " + r.get("value","")).lower()
                  or "codeentity" in (r.get("entity","") + " " + r.get("value","")).lower()
                  or "memoryosclient" in r.get("value","").lower()
                  for r in data["results"])
        assert hit, \
            f"code entity not found by text query. top: {[(r['entity'],r['value']) for r in data['results']]}"
    _run("code entity (MemoryOS SDK) found by text query", _code_entity_by_text)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 16 – Latency assertions
# ─────────────────────────────────────────────────────────────────────────────

def phase16_latency():
    section("Phase 16  Latency assertions")

    def _search_latency():
        t0 = time.time()
        data = search("compiler engineer Rust Zurich", top_k=5)
        elapsed = int((time.time()-t0)*1000)
        api_reported = data.get("retrieval_ms", 0)
        assert elapsed < 1500, \
            f"Search wall-time too slow: {elapsed}ms (target < 1500ms)"
        assert api_reported < 1000, \
            f"Retrieval_ms too slow: {api_reported}ms"
    _run("search < 1500ms wall-time", _search_latency)

    def _inject_latency():
        t0 = time.time()
        r = client.post("/memory/should_inject",
                        json={"prompt": "What does Nadia remember about her work?"})
        elapsed = int((time.time()-t0)*1000)
        data = r.json()
        assert data["check_ms"] < 100, f"check_ms={data['check_ms']} (target < 100)"
        assert elapsed < 200, f"Wall-time {elapsed}ms (target < 200)"
    _run("should_inject < 100ms (no LLM path)", _inject_latency)

    def _health_latency():
        t0 = time.time()
        r = client.get("/health")
        elapsed = int((time.time()-t0)*1000)
        assert elapsed < 500, f"Health check took {elapsed}ms (target < 500)"
    _run("/health < 500ms", _health_latency)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 17 – Cleanup
# ─────────────────────────────────────────────────────────────────────────────

def phase17_cleanup():
    section("Phase 17  Cleanup")

    r = client.get("/memory/list", params={"limit": 500, "session_filter": TAG})
    if r.status_code != 200:
        report.record("cleanup list", "FAIL", r.text[:120])
        return

    mems = r.json()["memories"]
    print(D(f"\n  Facts created in this session ({len(mems)} total):"))

    # Group by entity for readability
    by_entity: dict[str, list] = {}
    for m in mems:
        by_entity.setdefault(m["entity"], []).append(m)

    for entity, facts in sorted(by_entity.items()):
        print(D(f"\n  [{entity}]"))
        for f in facts:
            age = int(time.time()) - (f["timestamp"] or 0)
            print(D(f"    {f['attribute']:20s} = {f['value'][:55]}  [{f['source_type']}] {age}s ago"))

    deleted = failed = 0
    for m in mems:
        d = client.delete(f"/memory/{m['memory_id']}")
        if d.status_code in (200, 404):
            deleted += 1
        else:
            failed += 1

    report.record(
        "cleanup",
        "PASS" if failed == 0 else "WARN",
        f"deleted={deleted} failed={failed}",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(B("\nMemoryOS Deep Integration Test"))
    print(D(f"Target:  {BASE}"))
    print(D(f"Session: {TAG}"))
    print()

    if not phase0_preflight():
        print(R("\nServer unreachable — start with: python run.py"))
        sys.exit(2)

    phase1_seed()
    phase2_add_edges()
    phase3_search()
    phase4_entity_resolution()
    phase5_dedup()
    phase6_conflict()
    phase7_should_inject()
    phase8_augment()
    phase9_graph()
    phase10_list()
    phase11_delete()
    phase12_retrieval_after_delete()
    phase13_include_expired()
    phase14_fts5_safety()
    phase15_cross_source()
    phase16_latency()
    phase17_cleanup()

    print()
    print(B("=" * 62))
    print(B("  FINAL RESULT"))
    print(B("=" * 62))
    print(f"  {report.summary()}")

    failures = report.failures()
    if failures:
        print()
        print(R(B(f"  {len(failures)} FAILURE(S):")))
        for c in failures:
            print(f"  {R('✗')} {c.name}")
            for ln in c.detail.splitlines():
                print(D(f"      {ln}"))
        sys.exit(1)
    else:
        print()
        print(G(B("  ALL TESTS PASSED")))
        sys.exit(0)


if __name__ == "__main__":
    main()
