# MemoryOS

Open memory middleware engine for LLM applications.

## What is it?

MemoryOS gives your LLM a persistent, queryable memory graph. Drop it in front of any LLM and your app automatically remembers facts across sessions — without changing your prompts.

## Architecture

```
Input → Chunk → Extract → Dedup → Store → Retrieve → Augment → LLM
                              ↓
                  SQLite (source of truth)
                  FAISS  (vector search)
                  Kuzu   (graph relationships)
```

## Quick start

```bash
pip install -r requirements.txt
python run.py                    # starts API on http://localhost:8000
```

## API

```
POST /memory/add            – Store content (text, PDF, code, JSON, CSV)
POST /memory/search         – Hybrid search (vector + BM25 + graph)
POST /memory/augment        – Augment a prompt with memory context
POST /memory/should_inject  – Check if a prompt needs memory (< 10ms)
GET  /memory/list           – Browse all stored memories
GET  /memory/graph          – Entity relationship subgraph
DELETE /memory/{id}         – Delete a specific memory
```

Interactive docs: `http://localhost:8000/docs`

## Tech stack

- **Storage**: SQLite (WAL + FTS5 BM25) · FAISS · Kuzu graph
- **Intelligence**: Ollama (local) · Claude (fallback)
- **Embeddings**: `all-MiniLM-L6-v2` (384-dim, runs on CPU)
- **Dedup**: 2-layer — snake_case normalization + cosine embedding similarity
- **API**: FastAPI · Pydantic v2

## .env

```
LLM_PROVIDER=ollama           # or claude
OLLAMA_MODEL=llama3.1:7b
OLLAMA_URL=http://localhost:11434
CLAUDE_API_KEY=sk-ant-xxx     # optional fallback
DB_PATH=./data
```

## Run tests

```bash
pytest tests/test_phase1.py -v   # 54 passed, 1 skipped (Ollama model)
```
