# MemoryOS — Project Overview & Development Status

> Last updated: May 2026

---

## What is MemoryOS?

MemoryOS is an **open-source memory middleware engine for LLM applications**.

Every LLM forgets everything when a conversation ends. MemoryOS fixes that. You drop it in front of any chatbot — Claude, GPT, Gemini, or a local model — and it silently:

1. **Extracts** structured facts from anything you tell it (text, PDFs, code, JSON, CSV)
2. **Stores** those facts intelligently across three complementary databases
3. **Retrieves** the most relevant facts using a hybrid scoring system
4. **Injects** context into your next prompt — automatically

It is not plain RAG. It does actual fact extraction, deduplication, conflict resolution, knowledge graph traversal, and hybrid retrieval across three stores simultaneously.

Inspired by [supermemory.ai](https://supermemory.ai), built as a fully local, open, studyable version.

---

## How It Works — 5-Layer Pipeline

```
Input (text · PDF · code · JSON · CSV)
         │
         ▼
Layer 1 · INPUT ROUTING
  detect type → chunk/segment → normalize
         │
         ▼
Layer 2 · INTELLIGENCE
  LLM extracts facts → {entity, attribute, value, confidence}
  dedup check → conflict resolve (ADD / UPDATE / DELETE / NOOP)
         │
         ▼
Layer 3 · STORAGE  (all three updated simultaneously)
  ┌──────────┐   ┌──────────┐   ┌──────────┐
  │  SQLite  │   │  FAISS   │   │   Kuzu   │
  │ metadata │   │ 384-dim  │   │  graph   │
  │ BM25 FTS │   │ vectors  │   │ entities │
  └──────────┘   └──────────┘   └──────────┘
         │
         ▼
Layer 4 · HYBRID RETRIEVAL
  FAISS + BM25 + Kuzu run in parallel
  score merge: 0.6×vector + 0.3×BM25 + 0.1×recency
         │
         ▼
Layer 5 · EXPOSURE
  REST API · Python SDK · MCP Server
```

---

## Storage Architecture

Every fact shares a single `memory_id` UUID across all three stores:

| Store | Role | What it holds |
|---|---|---|
| SQLite | Source of truth | entity, attribute, value, confidence, timestamps, BM25 full-text index |
| FAISS | Semantic search | 384-dim vectors (all-MiniLM-L6-v2), top-k ANN |
| Kuzu | Relationship graph | Entity nodes, Fact nodes, RELATES_TO edges with temporal validity |

If FAISS is corrupt or empty on startup, it auto-rebuilds from SQLite.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Storage | SQLite (WAL + FTS5 BM25) · FAISS IndexFlatL2 · Kuzu graph DB |
| Intelligence | Groq API / Ollama (local) / Claude API — configurable via `.env` |
| Embeddings | all-MiniLM-L6-v2 · 384-dim · CPU · LRU cache 512 |
| API | FastAPI · Pydantic v2 · uvicorn |
| SDK | Python client · exponential backoff retry |
| MCP | FastMCP — native Claude Code · Cursor · Windsurf support |

---

## REST API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/memory/add` | Store content (text · PDF · code · JSON · CSV) |
| POST | `/memory/search` | Hybrid search (vector + BM25 + graph) |
| POST | `/memory/augment` | Augment a prompt with memory context |
| POST | `/memory/should_inject` | Fast check: does this prompt need memory? (<50ms) |
| GET | `/memory/list` | Paginated list of all stored memories |
| GET | `/memory/graph` | Entity relationship subgraph |
| DELETE | `/memory/{id}` | Delete a memory from all 3 stores |
| GET | `/health` | Server health + active LLM provider |

Interactive docs at `http://localhost:8000/docs` when the server is running.

---

## Setup & Running

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure `.env`
```env
# Option A — Groq (recommended, free tier)
LLM_PROVIDER=openai_compat
OPENAI_COMPAT_KEY=gsk_your_key_here
OPENAI_COMPAT_URL=https://api.groq.com/openai/v1
OPENAI_COMPAT_MODEL=llama-3.1-8b-instant

# Option B — Claude API
# LLM_PROVIDER=claude
# CLAUDE_API_KEY=sk-ant-your_key_here

# Option C — Local Ollama
# LLM_PROVIDER=ollama
# OLLAMA_MODEL=llama3.1:7b

DB_PATH=./data
```

### 3. Start the server
```bash
python run.py
# → http://localhost:8000
# → http://localhost:8000/docs
# → http://localhost:8000/ui  (demo interface)
```

### 4. Use the Python SDK
```python
from sdk.client import MemoryClient

client = MemoryClient()

# Store something
client.add("My name is Alice. I work at Acme Corp as a backend engineer.")

# Search
result = client.search("where does Alice work?")
print(result["context"])

# Augment a prompt before sending to any LLM
augmented = client.augment("Tell me about Alice.")
print(augmented["augmented_prompt"])
```

### 5. Use the MCP tools (Claude Code / Cursor)
```bash
# Register once
claude mcp add memoryos -- python /path/to/memos/mcp_server.py
```
Then in any Claude Code session: `memory_add`, `memory_search`, `memory_augment`, `memory_delete`, `memory_graph` are available as tools.

---

## Project File Structure

```
memos/
├── run.py                   # Entry point — starts FastAPI on :8000
├── mcp_server.py            # MCP server (Claude Code / Cursor integration)
├── requirements.txt
├── .env                     # Your keys (not committed)
│
├── core/                    # Engine internals
│   ├── engine.py            # Main orchestrator — only public interface
│   ├── llm.py               # Unified LLM client (Groq / Ollama / Claude)
│   ├── extractor.py         # LLM-based fact extraction
│   ├── deduplicator.py      # Fact deduplication logic
│   ├── conflict_resolver.py # LLM-based conflict resolution
│   ├── augmenter.py         # Prompt augmentation + should_inject()
│   ├── retriever.py         # Hybrid retrieval (FAISS + BM25 + Kuzu)
│   ├── scorer.py            # Score merging (vector + BM25 + recency)
│   ├── embedder.py          # Sentence embeddings with LRU cache
│   ├── sqlite_store.py      # SQLite + FTS5 BM25
│   ├── faiss_store.py       # FAISS index management
│   ├── kuzu_store.py        # Kuzu graph DB
│   ├── graph_enricher.py    # Keeps all 3 stores in sync
│   ├── input_router.py      # Input type detection + routing
│   ├── chunker.py           # Text chunking
│   ├── code_parser.py       # Code-specific segmentation
│   └── pdf_parser.py        # PDF text extraction
│
├── api/
│   └── main.py              # FastAPI app — 7 endpoints
│
├── sdk/
│   ├── __init__.py
│   └── client.py            # Python SDK (MemoryClient)
│
├── demo/
│   ├── index.html           # Web UI (served at /ui)
│   ├── benchmark.py         # Retrieval quality benchmark
│   └── generate_test_data.py
│
└── tests/
    ├── test_phase1.py       # Core engine + API tests (54 passed)
    ├── test_phase2.py       # Augmenter + API endpoint tests
    └── test_sdk.py          # SDK unit tests (17 passed)
```

---

## Development Status

### Phase 1 — Core Engine + REST API
**Status: Complete**

- [x] SQLite store with WAL mode + FTS5 BM25 full-text search
- [x] FAISS vector store with auto-rebuild from SQLite on crash
- [x] Kuzu graph DB with temporal edges (valid_from / valid_until)
- [x] LLM fact extraction via Ollama / Claude / Groq
- [x] Deduplication — ADD / NOOP / CONFLICT detection
- [x] Conflict resolution — UPDATE / DELETE / ADD / NOOP decisions
- [x] Hybrid retrieval: FAISS + BM25 + Kuzu graph traversal in parallel
- [x] Score merging: 0.6×vector + 0.3×BM25 + 0.1×recency
- [x] Input routing: text, PDF, code, JSON, CSV
- [x] All 7 REST API endpoints (FastAPI + Pydantic v2)
- [x] `/memory/augment` and `/memory/should_inject` endpoints
- [x] Auto-fallback between LLM providers
- [x] 54 passing tests

---

### Phase 2 — Python SDK + MCP Server
**Status: Complete**

- [x] `sdk/client.py` — `MemoryClient` wrapping all API endpoints
  - `add()`, `search()`, `augment()`, `should_inject()`, `delete()`, `get_graph()`, `list()`, `health()`
  - Exponential backoff retry on connection errors (0.5s → 1s)
  - `MemoryOSError` with `.status_code` — no retry on 4xx/5xx
- [x] `mcp_server.py` — FastMCP server with 5 tools
  - `memory_add`, `memory_search`, `memory_augment`, `memory_delete`, `memory_graph`
  - Registered with Claude Code (`claude mcp add memoryos`)
  - Calls `core.engine` directly (no HTTP round-trip)
- [x] OpenAI-compatible LLM provider (Groq, Together AI, OpenRouter, etc.)
  - `LLM_PROVIDER=openai_compat` in `.env`
  - Auto-fallback chain: openai_compat → claude → ollama
- [x] `requirements.txt` fixed for Python 3.13 (kuzu, tiktoken, torch unpinned)
- [x] 17 passing SDK unit tests

---

### Phase 3 — Demo UI + Benchmark
**Status: Not started**

#### Demo UI (`demo/index.html`)
The HTML/CSS shell exists but is not wired to the live API. Needs:
- [ ] JavaScript fetch calls to `http://localhost:8000`
- [ ] Add memory panel — POST to `/memory/add`, show extracted facts
- [ ] Search panel — POST to `/memory/search`, display results with scores
- [ ] Augment panel — POST to `/memory/augment`, show before/after diff
- [ ] Knowledge graph panel — GET `/memory/graph`, render with vis-network (already imported)
- [ ] Memory list panel — GET `/memory/list`, paginated table
- [ ] Live status bar — poll `/health` every 10s, show memory count + LLM provider

#### Benchmark (`demo/benchmark.py`)
The benchmark runner exists and is functional. Needs:
- [ ] Integrate with `demo/generate_test_data.py` to auto-seed data before running
- [ ] LongMemEval dataset integration (standardized long-memory benchmark)
- [ ] Comparison mode: run against different LLM providers and report diff
- [ ] Output dashboard — render `benchmark_results.json` as an HTML report

---

## Planned Future Features

These are not started but are logical next steps:

### Core Engine
- [ ] **Session-scoped memory** — each session_id gets an isolated memory namespace
- [ ] **Memory TTL / expiry policies** — auto-expire facts older than N days
- [ ] **Confidence decay** — reduce confidence of old facts over time
- [ ] **Streaming support** — stream augmented prompts via SSE
- [ ] **Batch ingest** — `/memory/bulk_add` for ingesting many documents at once

### Intelligence
- [ ] **Richer conflict resolution** — show diff, let user approve/reject
- [ ] **Entity disambiguation** — "Alice Smith" vs "Alice Jones" treated as different people
- [ ] **Relation extraction** — extract typed relationships between entities (works_at, knows, manages)
- [ ] **Multi-language support** — non-English fact extraction

### Storage & Retrieval
- [ ] **PostgreSQL + pgvector backend** — drop-in alternative to SQLite + FAISS for production scale
- [ ] **Export / import** — dump all memories to JSON, restore from JSON
- [ ] **Memory versioning** — full history of every fact change, not just current value

### API & SDK
- [ ] **Authentication** — API key middleware for multi-tenant use
- [ ] **TypeScript SDK** — `@memoryos/sdk` npm package mirroring the Python SDK
- [ ] **Async Python SDK** — `AsyncMemoryClient` using `httpx.AsyncClient`
- [ ] **Webhooks** — fire events when facts are added, updated, or expired

### Deployment
- [ ] **Docker + docker-compose** — one-command local deployment
- [ ] **Cloud deployment guide** — Railway / Render / Fly.io setup
- [ ] **Helm chart** — Kubernetes deployment for self-hosted teams

---

## Running Tests

```bash
# Phase 1 — core engine (requires Ollama or Groq configured)
pytest tests/test_phase1.py -v

# Phase 2 — augmenter + API endpoints (mocks LLM, no external deps)
pytest tests/test_phase2.py -v

# SDK unit tests (no server needed, fully mocked)
pytest tests/test_sdk.py -v

# All tests
pytest tests/ -v
```

---

## Contributing

The codebase follows a strict layering rule:

- `api/main.py` calls `core/engine.py` only — never touches stores directly
- `core/engine.py` is the only public interface — `add()`, `search()`, `delete()`, `get_graph()`
- All LLM calls go through `core/llm.py` — nothing else talks to Ollama/Groq/Claude directly
- All three stores are always updated together — never update one without the others

When adding a feature, figure out which layer it belongs to and keep it there.
