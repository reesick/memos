# MemoryOS Core Functionality Notes

## What This Project Does

MemoryOS is a memory engine for LLM applications.

Normally, an LLM answers based only on the current prompt. When the session ends, that context is effectively gone.

MemoryOS fixes that by:

1. Taking incoming content such as text, code, PDF, JSON, or CSV.
2. Extracting structured facts from it.
3. Storing those facts in multiple storage systems optimized for different retrieval styles.
4. Retrieving the most relevant facts later.
5. Injecting that retrieved context back into future prompts.

In short:

- Input comes in.
- Facts are extracted.
- Facts are stored.
- Relevant facts are retrieved later.
- The next prompt gets better context.

## One-Line Summary

MemoryOS is a hybrid long-term memory engine for LLMs that extracts facts from input, stores them in SQLite, FAISS, and Kuzu, then retrieves and injects relevant context into future prompts.

## End-to-End Flow

Example input:

```text
Arjun is the backend lead. He prefers FastAPI. The project uses SQLite and FAISS.
```

What happens:

1. `input_router` sees this is plain text.
2. `chunker` splits the content into sensible chunks.
3. `extractor` sends each chunk to the LLM and extracts facts.
4. `deduplicator` checks if those facts already exist.
5. `conflict_resolver` is used if the same entity and attribute already exist with a different value.
6. `sqlite_store` stores the fact as the source of truth.
7. `faiss_store` stores the embedding for semantic search.
8. `kuzu_store` stores graph relationships.
9. Later, `retriever` queries all stores in parallel.
10. `scorer` combines the results into one ranking.
11. `augmenter` can prepend the found memory to a future prompt.

Possible extracted facts:

```json
[
  {"entity":"Arjun","attribute":"role","value":"backend lead","confidence":0.95},
  {"entity":"Arjun","attribute":"preference","value":"FastAPI","confidence":0.90},
  {"entity":"project","attribute":"database","value":"SQLite","confidence":0.92},
  {"entity":"project","attribute":"technology","value":"FAISS","confidence":0.91}
]
```

## Core Folder Overview

### `core/engine.py`

This is the main orchestrator.

Main responsibilities:

- Initializes all stores.
- Runs the full ingestion pipeline through `add()`.
- Runs the full retrieval pipeline through `search()`.
- Deletes facts across all stores.
- Exposes graph lookup.

Example:

```python
engine.add("Priya knows React.", source_type="text")
engine.search("Priya skills")
```

Edge case:

- If FAISS is empty but SQLite already has facts, the engine rebuilds FAISS from SQLite on startup.

### `core/input_router.py`

This decides how to process input based on the `source_type`.

Supported types:

- `text`
- `pdf`
- `code`
- `json`
- `csv`

Examples:

- Text input goes to the text chunker.
- PDF input goes to the PDF parser.
- JSON input is flattened into text-like segments.
- CSV rows are converted into text segments.

Example:

```json
{"name":"Arjun","role":"backend lead"}
```

becomes segments like:

```text
name: Arjun
role: backend lead
```

Edge cases:

- Empty content raises `EmptyContentError`.
- Very large input above 50,000 tokens raises `InputTooLargeError`.
- Unknown source type does not crash; it falls back to plain text handling.

### `core/chunker.py`

This splits long text into semantically coherent chunks.

How it works:

- Splits text into sentences.
- Embeds the sentences.
- Detects topic shifts using embedding distance.
- Creates overlap between chunks so context is not lost.

Example:

If a meeting note starts with team updates and then shifts into database design, the chunker may split at that topic boundary.

Edge cases:

- Empty text returns an empty list.
- Very short text returns one chunk.
- If a single sentence is too long or has no punctuation, the fallback chunker splits it by words.

### `core/extractor.py`

This is the fact extraction layer.

It sends a text segment to the LLM and asks for facts in structured JSON form.

Expected fact format:

```json
{
  "entity": "Arjun",
  "attribute": "role",
  "value": "backend lead",
  "confidence": 0.95
}
```

Example:

```text
Vedant studies at VIT Pune.
```

can become:

```json
{"entity":"Vedant","attribute":"university","value":"VIT Pune","confidence":0.95}
```

Important behavior:

- Attributes are normalized to snake_case.
- Facts with confidence below `0.7` are dropped.
- If the LLM returns invalid JSON, it retries once with a stricter prompt.

Edge cases:

- If both LLM attempts fail, it returns an empty list instead of crashing.
- If the content is a question and contains no stable fact, extraction may legitimately return `[]`.

### `core/deduplicator.py`

This checks whether a new fact is actually new.

It uses two layers:

1. Exact entity + attribute match.
2. Semantic attribute similarity match.

Possible outcomes:

- `ADD`
- `NOOP`
- `CONFLICT`

Example:

Existing fact:

```text
Arjun role = backend lead
```

New fact:

```text
Arjun role = backend lead
```

Result:

- `NOOP`

Another example:

Existing fact:

```text
Arjun technology_preference = FastAPI
```

New fact:

```text
Arjun preferred_technology = FastAPI
```

Result:

- likely treated as the same attribute through semantic deduplication

Edge cases:

- Exact same value becomes `NOOP`.
- Same entity plus logically same attribute but different value becomes `CONFLICT`.
- If semantic matching fails internally, it safely falls back toward treating the fact as new.

### `core/conflict_resolver.py`

This is used only when there is a conflict.

Conflict means:

- same entity
- same attribute
- different value

Possible actions:

- `UPDATE`
- `ADD`
- `DELETE`
- `NOOP`

Example:

Existing:

```text
Arjun role = backend lead
```

New:

```text
Arjun role = platform lead
```

Likely result:

- `UPDATE`

Another example:

Existing:

```text
Arjun skill = Python
```

New:

```text
Arjun skill = FastAPI
```

Possible result:

- `ADD`

because both may be valid at the same time.

Edge cases:

- If the LLM fails, the fallback action is `ADD`, because keeping both facts is safer than deleting one incorrectly.

### `core/embedder.py`

This converts text into embeddings using `all-MiniLM-L6-v2`.

Embedding dimension:

- 384

Why it exists:

- semantic search
- semantic deduplication
- chunk comparison

Example:

- `"backend lead"` and `"engineering lead"` may end up close in vector space.

Edge cases:

- Empty text returns a zero vector.
- Repeated text is served from cache for speed.

### `core/faiss_store.py`

This stores embeddings for vector similarity search.

Why it exists:

- find semantically similar memories even when the wording is different

Example:

Query:

```text
Who handles backend?
```

Stored fact:

```text
Arjun is the backend lead.
```

FAISS helps match these even if the exact words differ.

Edge cases:

- If a memory ID already exists, duplicate insertion is skipped.
- If the on-disk index cannot be loaded, a fresh one is created.

### `core/sqlite_store.py`

This is the source of truth.

It stores:

- `memory_id`
- `entity`
- `attribute`
- `value`
- `confidence`
- `source_type`
- `doc_id`
- `session_id`
- `timestamp`
- `expired_at`
- `raw_chunk`

It also supports BM25-style full-text search through SQLite FTS5.

Example:

Searching for:

```text
middleware LLMs
```

can match a stored row whose `raw_chunk` contains those words.

Edge cases:

- FTS search syntax can break on raw punctuation, so the code sanitizes user queries first.
- Expired facts are usually filtered out unless the caller explicitly asks to include them.

### `core/kuzu_store.py`

This is the graph database layer.

What it stores:

- Entity nodes
- Fact nodes
- edges connecting them

Why it exists:

- relation traversal
- bridge detection
- graph-style queries

Example:

- Entity node: `Alice`
- Fact node: `senior engineer`
- Edge: `Alice -> senior engineer`

Edge cases:

- If Kuzu initialization fails, graph features are disabled gracefully instead of breaking the whole app.

### `core/graph_enricher.py`

This updates the graph after facts are stored or changed.

On add:

- create entity node
- create fact node
- create edge

On update:

- expire old edge
- create new fact node
- create new edge

On delete:

- expire edge
- remove fact node

Example:

If `Arjun role = backend lead` is updated to `Arjun role = platform lead`, graph enrichment expires the old link and creates the new one.

Edge cases:

- Document linking is best-effort. If it fails, the main storage path still succeeds.

### `core/retriever.py`

This handles hybrid retrieval.

It runs these in parallel:

- FAISS vector search
- SQLite BM25 search
- Kuzu graph traversal

Then it collects candidate memory IDs, fetches their full records from SQLite, and sends everything to the scoring layer.

Example:

Query:

```text
Priya React
```

Possible hits:

- vector similarity from FAISS
- keyword hits from BM25
- graph-related entity hits from Kuzu

Edge cases:

- If one retrieval backend times out, the others can still provide results.
- Expired facts are filtered unless `include_expired=True`.

### `core/scorer.py`

This combines retrieval scores into one hybrid score.

Signals used:

- vector similarity
- BM25 score
- recency score

Why recency matters:

- newer facts can matter more than stale ones

Example:

- A recent medium-similarity fact can outrank an old low-value exact match depending on the combined score.

Edge cases:

- Short queries like `"Priya?"` use different score weights because vector embeddings on extremely short queries can be noisy.

### `core/augmenter.py`

This decides whether memory should be injected into the prompt, and if so, it prepends retrieved context.

Current behavior:

- heuristic-based `should_inject()`
- search-based `augment()`

Example:

Prompt:

```text
What did I tell you before about my project?
```

Likely result:

- memory injection happens

Prompt:

```text
2 + 2
```

Likely result:

- no memory injection

Edge cases:

- If retrieval finds no relevant memory, the original prompt is returned unchanged.
- This module is functional but still simpler than the rest of the architecture.

### `core/llm.py`

This is the unified LLM access layer.

Supported providers:

- Ollama
- Claude fallback

Why it exists:

- keep the rest of the code independent from provider-specific details

Example:

- `extractor` calls this for fact extraction
- `conflict_resolver` calls this for conflict reasoning

Edge cases:

- If Ollama is running but the configured model is not pulled, it raises a specific error.
- If fallback credentials exist, Claude can be used instead.

### `core/code_parser.py`

This parses code inputs before extraction.

How it works:

- Python uses AST parsing.
- Other languages use regex-based function detection.
- Final fallback is generic chunking.

Example:

A Python file might be split into:

- imports
- class summary
- each method
- each top-level function

Edge cases:

- If Python source has syntax errors, AST parsing fails and the parser falls back safely.

### `core/pdf_parser.py`

This parses PDF input and converts it into chunks.

How it works:

- extracts text from the PDF
- tries to detect section structure
- tags chunks as `HIGH`, `MED`, or `LOW` priority
- falls back to fixed chunking if structure is unclear

Example:

A research paper may produce chunks like:

```text
[HIGH] Abstract: ...
[MED] Methods: ...
[LOW] References: ...
```

Edge cases:

- Scanned PDFs without a text layer are rejected with an explicit error.
- If base64 decoding fails, content is treated as plain text instead.

## Data Folder Explanation

The `data/` folder stores the persistent state of the memory engine.

Current files:

- `memoryos.db`
- `memoryos.db-wal`
- `memoryos.db-shm`
- `faiss.index`
- `faiss.index.map.npy`
- `kuzu_db/`

### `memoryos.db`

This is the main SQLite database.

It is the source of truth for stored memories.

### `memoryos.db-wal`

This is the SQLite write-ahead log file.

Purpose:

- improves durability
- improves concurrency
- normal part of SQLite WAL mode

### `memoryos.db-shm`

This is the SQLite shared memory file used along with WAL mode.

Purpose:

- helps coordinate database access
- normal runtime file

### `faiss.index`

This is the saved FAISS vector index.

Purpose:

- stores embeddings for semantic search

### `faiss.index.map.npy`

This stores the mapping between:

- string `memory_id`
- internal FAISS integer ID

Because FAISS uses integer IDs internally, the project needs this mapping to connect FAISS entries back to real memories.

### `kuzu_db/`

This folder stores the Kuzu graph database files.

Purpose:

- entity graph
- fact graph nodes
- relationships for traversal and bridge detection

## How the Three Stores Relate

Every fact has a shared `memory_id`.

That `memory_id` ties together:

- SQLite row
- FAISS vector entry
- Kuzu fact node

So if someone asks where the real memory is stored, the best answer is:

- SQLite is the source of truth.
- FAISS and Kuzu are supporting indexes optimized for retrieval.

## Typical Questions You May Be Asked

### Why use three stores instead of one?

Because each solves a different problem well:

- SQLite for truth, metadata, and persistence
- FAISS for semantic similarity
- Kuzu for relationship traversal

### Why not use only a vector database?

A vector store is great for semantic similarity, but weaker for exact metadata filtering, full truth storage, and graph relationships.

### Why keep expired facts?

Because history matters. A fact can be superseded without being erased from memory forever.

### Why is conflict resolution LLM-based?

Because differences between facts are not always simple string mismatches. Sometimes the new fact replaces the old one, sometimes both are valid, and sometimes the new one negates the old one.

### What happens if extraction fails?

The extractor returns an empty list instead of crashing the pipeline.

### What happens if graph storage fails?

Graph features degrade gracefully, while SQLite and FAISS can still support the main memory system.

### What is the weakest part of the current repo?

The augmentation layer is still simpler than the rest, and the `sdk/`, `mcp/`, and `docs/` feature areas are not implemented deeply in this repository yet.

## Fast Verbal Explanation

If you need to explain it quickly:

MemoryOS takes user input, breaks it into chunks, extracts facts with an LLM, deduplicates and resolves conflicts, stores facts in SQLite, FAISS, and Kuzu, then later retrieves the most relevant memories and injects them into future prompts.
