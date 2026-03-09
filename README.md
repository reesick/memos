# MemoryOS
> open memory middleware engine for LLM applications

every LLM forgets everything when the conversation ends. MemoryOS fixes that. drop it in front of any chatbot — Claude, GPT, Gemini, local model — and it silently injects relevant context into every prompt and stores what was said for future recall.

not plain RAG. actual fact extraction, conflict resolution, a knowledge graph, and hybrid retrieval across three stores simultaneously.

---

## how it works

```
                        ┌─────────────────────────────────────────┐
                        │              ANY INPUT                   │
                        │   text · PDF · code · JSON · CSV         │
                        └──────────────────┬──────────────────────┘
                                           │
                                           ▼
                        ┌─────────────────────────────────────────┐
                        │           LAYER 1 · INPUT               │
                        │   type detect → route → chunk/segment   │
                        └──────────────────┬──────────────────────┘
                                           │
                                           ▼
                        ┌─────────────────────────────────────────┐
                        │        LAYER 2 · INTELLIGENCE           │
                        │   extract facts → dedup → conflict      │
                        │   resolve (ADD / UPDATE / DELETE / NOOP)│
                        └──────────────────┬──────────────────────┘
                                           │
                                           ▼
                        ┌─────────────────────────────────────────┐
                        │          LAYER 3 · STORAGE              │
                        │                                         │
                        │  ┌──────────┐ ┌───────┐ ┌──────────┐  │
                        │  │  SQLite  │ │ FAISS │ │   Kuzu   │  │
                        │  │ metadata │ │vectors│ │  graph   │  │
                        │  │ BM25 FTS │ │384-dim│ │ entities │  │
                        │  └──────────┘ └───────┘ └──────────┘  │
                        │    source of     vector    relationship │
                        │      truth       search      traversal  │
                        └──────────────────┬──────────────────────┘
                                           │
                                           ▼
                        ┌─────────────────────────────────────────┐
                        │         LAYER 4 · RETRIEVAL             │
                        │  FAISS + BM25 + Kuzu run in parallel    │
                        │  hybrid score merge → context assemble  │
                        │  0.6×vector + 0.3×BM25 + 0.1×recency   │
                        └──────────────────┬──────────────────────┘
                                           │
                                           ▼
                        ┌─────────────────────────────────────────┐
                        │         LAYER 5 · EXPOSURE              │
                        │                                         │
                        │  ┌─────────┐ ┌────────┐ ┌──────────┐  │
                        │  │REST API │ │   SDK  │ │   MCP    │  │
                        │  │FastAPI  │ │ Python │ │ Claude   │  │
                        │  │         │ │ client │ │ Code /   │  │
                        │  │         │ │        │ │ Cursor   │  │
                        │  └─────────┘ └────────┘ └──────────┘  │
                        └─────────────────────────────────────────┘
```

---

## storage architecture

```
                    every fact shares one memory_id UUID

          ┌────────────────────────────────────────────────┐
          │                   SQLite                       │
          │         source of truth · WAL mode             │
          │  entity | attribute | value | confidence       │
          │  source | session | timestamp | expired_at     │
          │  raw_chunk (BM25 FTS5 full-text search)        │
          └───────────────┬────────────────────────────────┘
                          │ memory_id shared key
              ┌───────────┼───────────────┐
              ▼           ▼               ▼
        ┌──────────┐ ┌─────────┐  ┌────────────────────┐
        │  FAISS   │ │ rebuilt │  │       Kuzu          │
        │IndexFlat │ │  from   │  │  Entity nodes       │
        │   L2     │ │ SQLite  │  │  Fact nodes         │
        │384 dims  │ │  if     │  │  RELATES_TO edges   │
        │top-k ANN │ │corrupt  │  │  valid_from/until   │
        └──────────┘ └─────────┘  │  temporal graph     │
                                  └────────────────────┘
```

---

## intelligence pipeline

```
  new input arrives
        │
        ▼
  ┌─────────────┐
  │   extract   │  Ollama 7B → [{entity, attribute, value, confidence}]
  │   facts     │  Pydantic validation · retry once on bad JSON
  └──────┬──────┘
         │
         ▼
  ┌─────────────┐     entity+attribute
  │    dedup    │────── not in SQLite ──→ ADD
  │   check     │────── same value ──────→ NOOP (refresh timestamp)
  └──────┬──────┘────── diff value ──────→ conflict resolver ──┐
         │                                                       │
         │              ┌────────────────────────────────────┐  │
         │              │       conflict resolver            │◄─┘
         │              │  Ollama compares old vs new fact   │
         │              │  UPDATE · ADD · DELETE · NOOP      │
         │              └────────────────────────────────────┘
         │
         ▼
  ┌─────────────┐
  │    store    │  SQLite + FAISS + Kuzu updated simultaneously
  │  all three  │  shared memory_id across all stores
  └─────────────┘
```

---

## retrieval & augmentation

```
  user sends prompt
        │
        ▼
  ┌──────────────────┐
  │  should_inject?  │  lightweight Ollama check · < 50ms
  └────────┬─────────┘
           │ yes
           ▼
  ┌──────────────────────────────────────────┐
  │            hybrid retrieval              │
  │                                          │
  │  embed query (all-MiniLM-L6-v2, 30ms)   │
  │       ┌──────────────────────┐           │
  │       │  parallel execution  │           │
  │  ┌────┴───┐ ┌───────┐ ┌─────┴──┐        │
  │  │ FAISS  │ │  BM25 │ │  Kuzu  │        │
  │  │ top-k  │ │keyword│ │ graph  │        │
  │  │ vector │ │ match │ │ 2-hop  │        │
  │  └────┬───┘ └───┬───┘ └─────┬──┘        │
  │       └─────────┴───────────┘           │
  │              merge + score              │
  │    0.6×vector + 0.3×BM25 + 0.1×recency │
  └──────────────────┬───────────────────────┘
                     │
                     ▼
  ┌──────────────────────────────────────────┐
  │         assemble context string          │
  │  max 500 tokens · most recent first      │
  │  flags cross-source bridges if found     │
  └──────────────────┬───────────────────────┘
                     │
                     ▼
             augmented prompt
                     │
                     ▼
              any LLM you use
```

---

## quick start

```bash
pip install -r requirements.txt
python run.py          # starts API on http://localhost:8000
```

requires Ollama running locally with `llama3.1:7b` pulled.

---

## API

```
POST   /memory/add            store content (text · PDF · code · JSON · CSV)
POST   /memory/search         hybrid search (vector + BM25 + graph)
POST   /memory/augment        augment a prompt with memory context
POST   /memory/should_inject  check if a prompt needs memory (< 50ms)
GET    /memory/graph          entity relationship subgraph
DELETE /memory/{id}           delete a specific memory from all 3 stores
```

interactive docs at `http://localhost:8000/docs`

---

## tech stack

| layer | tech |
|---|---|
| storage | SQLite (WAL + FTS5 BM25) · FAISS IndexFlatL2 · Kuzu graph |
| intelligence | Ollama llama3.1:7b (local) · Claude haiku (fallback) |
| embeddings | all-MiniLM-L6-v2 · 384-dim · CPU · LRU cache 512 |
| api | FastAPI · Pydantic v2 · uvicorn |
| sdk | Python client · retry logic built in |
| mcp | native Claude Code · Cursor · Windsurf support |

---

## .env

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1:7b
OLLAMA_URL=http://localhost:11434
CLAUDE_API_KEY=sk-ant-xxx     # optional fallback
DB_PATH=./data
```

---

## run tests

```bash
pytest tests/test_phase1.py -v   # 54 passed, 1 skipped (Ollama model)
```

---

## status

- [x] phase 1 · core engine + REST API
- [ ] phase 2 · Python SDK + MCP server (in progress, squashing bugs)
- [ ] phase 3 · demo UI + LongMemEval benchmark

---

inspired by [supermemory](https://supermemory.ai). wanted the open version i could actually study and build on. (copied the ui directly ;) )

---

*VIT Pune · CSE(AI)-D · 2025-26*