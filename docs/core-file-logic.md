# Core Folder Logic Reference

## Purpose

This file explains the logic and function of every file inside the `core/` folder in a direct, file-by-file format.

The `core/` folder is the actual engine of MemoryOS. It contains the full memory pipeline:

1. Accept input
2. Parse or chunk it
3. Extract facts
4. Deduplicate or resolve conflicts
5. Store memory
6. Retrieve memory later
7. Assemble context for LLM use

## High-Level Flow

The most important execution path is:

```text
input
-> input_router
-> chunker / code_parser / pdf_parser
-> extractor
-> deduplicator
-> conflict_resolver
-> sqlite_store + faiss_store + kuzu_store
-> retriever
-> scorer
-> augmenter
```

## `core/__init__.py`

### Function

This marks `core/` as a Python package.

### Logic

There is no business logic here. Its job is just to allow imports like:

```python
import core.engine
from core import llm
```

## `core/engine.py`

### Function

This is the main orchestrator of the entire memory system.

### Main logic

It exposes the main public functions:

- `add(...)`
- `search(...)`
- `delete(...)`
- `get_graph(...)`

It also manages singleton store instances:

- `_sqlite`
- `_faiss`
- `_kuzu`

### What `add()` does

`add()` runs the full ingestion pipeline:

1. Initialize stores if needed.
2. Route and segment input using `input_router`.
3. Extract facts using `extractor`.
4. Deduplicate facts using `deduplicator`.
5. If conflict exists, resolve it using `conflict_resolver`.
6. Save accepted facts in SQLite.
7. Save embeddings in FAISS.
8. Update graph in Kuzu through `graph_enricher`.
9. Return a summary like number of facts added or updated.

### What `search()` does

`search()` runs the retrieval pipeline:

1. Initialize stores.
2. Call `retriever.retrieve(...)`.
3. Get ranked memory results.
4. Assemble a context string from those results.
5. Return formatted search output.

### Important design point

This file is the central coordinator. The API layer calls this instead of directly touching stores.

## `core/input_router.py`

### Function

This decides how incoming content should be processed depending on input type.

### Main logic

It supports:

- `text`
- `pdf`
- `code`
- `json`
- `csv`

### Routing logic

- Text goes to `chunker.chunk_text()`
- PDF goes to `pdf_parser.parse_pdf()`
- Code goes to `code_parser.parse_code()`
- JSON gets flattened into text segments
- CSV gets converted row-by-row into text segments

### Important helpers

- `_get_encoder()` loads the tokenizer for token counting
- `count_tokens()` measures approximate prompt size
- `_route_json()` converts JSON into segment strings
- `_route_csv()` converts CSV rows into segment strings

### Why this file matters

The rest of the pipeline expects clean text segments. This file ensures every kind of input gets converted into that format first.

## `core/chunker.py`

### Function

This splits long plain text into meaningful chunks.

### Main logic

It tries to preserve semantic meaning instead of splitting blindly.

### How it works

1. Split input into sentences.
2. Generate embeddings for each sentence.
3. Compare each sentence to the previous one.
4. If semantic distance becomes large, treat that as a topic shift.
5. Start a new chunk.
6. Keep overlap between chunks so some context carries forward.

### Important helpers

- `_split_sentences()` breaks text into sentence-like units
- `_estimate_tokens()` estimates token count
- `chunk_text()` is the main semantic chunker
- `chunk_with_overlap()` is the fallback fixed-size chunker
- `_split_by_words()` handles giant unstructured sentences

### Why this file matters

If chunks are too random, the extractor gets low-quality context. Good chunking improves extraction quality.

## `core/code_parser.py`

### Function

This processes code input before it goes into extraction.

### Main logic

It tries to split code according to code structure instead of plain text structure.

### How it works

1. Detect programming language with `_detect_language()`.
2. If Python, parse with AST.
3. Extract imports, classes, methods, and top-level functions.
4. If not Python, try regex-based function detection.
5. If that also fails, use generic chunking.

### Important helpers

- `_detect_language()` guesses code language
- `_parse_python()` handles Python AST parsing
- `_is_top_level()` checks whether a function is top-level
- `_extract_node_source()` pulls source text for AST nodes
- `_parse_regex()` handles non-Python code
- `parse_code()` is the main entry point

### Why this file matters

For code memory, preserving function boundaries and class structure gives the extractor better context than naive text splitting.

## `core/pdf_parser.py`

### Function

This handles PDF input.

### Main logic

It tries to extract text from a PDF, detect structure, and create prioritized chunks.

### How it works

1. Decode input as base64 PDF bytes.
2. Extract page text using `PyPDF2`.
3. Detect whether the document looks like a paper, report, or book.
4. Try to split by sections.
5. Tag chunks by priority such as `HIGH`, `MED`, or `LOW`.
6. If structure is unclear, fall back to normal chunking.

### Important helpers

- `_extract_text_from_pdf_bytes()` extracts text page-by-page
- `_detect_structure()` uses the LLM to classify the document type
- `_tag_section_priority()` marks sections by importance
- `_split_by_sections()` finds section-like headers
- `_chunk_section()` chunks each section
- `parse_pdf()` is the main entry point

### Why this file matters

Not all PDF content is equally useful. This file tries to preserve higher-value sections like abstract or conclusion more carefully.

## `core/extractor.py`

### Function

This converts text segments into structured facts.

### Main logic

It asks the LLM to extract facts in a strict JSON format.

### What a fact looks like

A fact has:

- `entity`
- `attribute`
- `value`
- `confidence`

### How it works

1. Build extraction prompt.
2. Send prompt to `core.llm.call(...)`.
3. Parse the response as JSON.
4. Validate every item using the `Fact` Pydantic model.
5. Normalize attributes to snake_case.
6. Drop low-confidence or invalid facts.
7. Retry once with a stricter prompt if parsing fails.

### Important helpers

- `Fact` is the schema for extracted facts
- `_parse_fact_response()` parses raw LLM output
- `_validate_facts()` validates parsed facts
- `extract()` extracts facts from one segment
- `extract_all()` loops over all segments

### Why this file matters

This is where unstructured text becomes structured memory.

## `core/deduplicator.py`

### Function

This decides whether a newly extracted fact is:

- new
- already known
- conflicting

### Main logic

It uses a two-layer approach:

1. Exact entity + attribute match
2. Semantic similarity match on attributes

### Possible outcomes

- `ADD`
- `NOOP`
- `CONFLICT`
- `SKIP`

### How it works

1. For each extracted fact, check SQLite for exact active match.
2. If found:
   - same value -> `NOOP`
   - different value -> `CONFLICT`
3. If no exact match:
   - fetch all facts for the same entity
   - compare attribute embeddings
   - if similar enough, treat as same attribute
4. Otherwise return `ADD`

### Important helpers

- `DedupAction` defines the action enum
- `DedupResult` stores the result of one dedup check
- `deduplicate()` is the main entry point
- `_make_result()` creates `NOOP` or `CONFLICT`
- `_find_semantic_match()` finds semantically similar attributes
- `_cosine()` calculates cosine similarity
- `_normalize()` normalizes values before comparison
- `_is_negation()` detects negation-like values

### Why this file matters

Without deduplication, the system would keep storing the same fact again and again.

## `core/conflict_resolver.py`

### Function

This decides what to do when the same entity and attribute appear with a different value.

### Main logic

It uses the LLM to classify the conflict into one of four actions:

- `UPDATE`
- `ADD`
- `DELETE`
- `NOOP`

### How it works

1. Build a conflict prompt with the existing value and new value.
2. Ask the LLM to classify the relationship.
3. Parse the JSON response.
4. Return a `ConflictResult`.
5. If the LLM fails, fall back safely.

### Important helpers

- `ConflictAction` is the enum
- `ConflictResult` stores the decision
- `resolve()` handles one conflict
- `resolve_batch()` handles many conflicts

### Why this file matters

Simple string comparison cannot tell whether a changed fact means replacement, coexistence, or deletion. This file handles that reasoning step.

## `core/embedder.py`

### Function

This converts text into vector embeddings.

### Main logic

It uses the `all-MiniLM-L6-v2` sentence-transformer model and caches results.

### How it works

1. Load the model lazily on first use.
2. Encode text into a normalized NumPy vector.
3. Cache repeated inputs.
4. Support batch encoding for efficiency.

### Important helpers

- `_get_model()` lazily loads the model
- `encode()` embeds one text string
- `encode_batch()` embeds many strings together
- `dimensions()` returns the embedding size

### Why this file matters

Embeddings are used by:

- chunking
- semantic deduplication
- vector search

## `core/faiss_store.py`

### Function

This manages the FAISS vector index.

### Main logic

It stores and searches embeddings for semantic retrieval.

### How it works

1. Load FAISS index from disk if available.
2. If missing or broken, create a fresh index.
3. Convert each `memory_id` into an internal integer ID.
4. Add vectors to FAISS.
5. Save the index and ID mappings to disk.
6. Search nearest vectors during retrieval.

### Important helpers

- `_load_or_create()` loads or initializes the index
- `_create_fresh()` creates a new FAISS index
- `_save()` persists index and mappings
- `add_vector()` inserts a vector
- `delete_vector()` removes a vector
- `search()` retrieves nearest matches
- `total()` returns vector count
- `rebuild_from_records()` recreates the index from SQLite data

### Why this file matters

It enables semantic search over memory, which is useful when user wording does not exactly match stored wording.

## `core/sqlite_store.py`

### Function

This is the main persistent fact store and the source of truth.

### Main logic

It stores structured memory records and provides exact lookup plus BM25 full-text search.

### How it works

1. Open SQLite database.
2. Enable WAL mode.
3. Create schema if needed.
4. Insert, update, expire, delete, or fetch facts.
5. Keep the FTS table synchronized through triggers.
6. Support BM25 search on stored chunks.

### Important helpers

- `_sanitize_fts_query()` cleans user text for safe FTS matching
- `_new_memory_id()` generates IDs like `mem_xxxxxxxx`
- `SqliteStore` is the main storage class

Important methods on `SqliteStore`:

- `insert()`
- `update_expired()`
- `refresh_timestamp()`
- `delete()`
- `find_by_entity_attribute()`
- `get_all_for_entity()`
- `get_by_id()`
- `bm25_search()`
- `get_all_for_rebuild()`
- `count()`
- `close()`

### Why this file matters

Everything else depends on this file because SQLite holds the actual memory records.

## `core/kuzu_store.py`

### Function

This manages the Kuzu graph database layer.

### Main logic

It stores entities and fact nodes, along with edges representing relationships.

### How it works

1. Initialize the Kuzu database.
2. Create node and edge schema.
3. Insert entities.
4. Insert fact nodes.
5. Connect entities to facts.
6. Expire or delete graph links as memory changes.
7. Traverse the graph and detect bridges.

### Important helpers

- `_init_db()` opens Kuzu
- `_create_schema()` creates graph tables
- `create_entity()` creates or merges an entity node
- `create_fact_node()` creates fact nodes
- `create_edge()` creates entity-to-fact relationships
- `expire_edge()` marks an edge outdated
- `delete_fact()` removes a fact node
- `traverse()` reads graph-linked facts
- `bridge_detect()` checks cross-linked memory IDs
- `get_subgraph()` returns graph data for visualization

### Why this file matters

This adds relationship awareness beyond plain keyword or vector matching.

## `core/graph_enricher.py`

### Function

This updates Kuzu after memory changes.

### Main logic

It converts stored facts into graph structures.

### How it works

On add:

1. Infer entity type.
2. Infer relationship label from the attribute.
3. Create entity node.
4. Create fact node.
5. Create edge between them.

On update:

1. Expire old edge.
2. Add new fact node.
3. Add new edge.

On delete:

1. Expire edge.
2. Delete fact node.

### Important helpers

- `_infer_entity_type()` guesses whether the entity is a person, system, or concept
- `_infer_relationship()` turns attribute names into graph edge labels
- `enrich_add()`
- `enrich_update()`
- `enrich_delete()`
- `_link_to_document()` adds best-effort document linking

### Why this file matters

This is the bridge between plain stored facts and graph-based retrieval.

## `core/retriever.py`

### Function

This runs the hybrid retrieval pipeline.

### Main logic

It queries multiple backends in parallel and merges their candidates.

### How it works

1. Embed the query using `embedder`.
2. Run in parallel:
   - FAISS vector search
   - SQLite BM25 search
   - Kuzu graph traversal
3. Collect all candidate memory IDs.
4. Fetch full records from SQLite.
5. Filter out expired or disallowed records.
6. Send candidates to `scorer.merge_scores(...)`.
7. Detect graph bridges.
8. Flag contradictions in top results.

### Important helpers

- `retrieve()` is the main entry point
- `_flag_contradictions()` marks repeated entity+attribute cases in result sets

### Why this file matters

This is where the three storage systems become one unified retrieval result.

## `core/scorer.py`

### Function

This computes final hybrid ranking scores.

### Main logic

It combines:

- vector similarity score
- BM25 score
- recency score

### How it works

1. Detect whether the query is short.
2. Use weight values based on query length.
3. Normalize BM25 scores.
4. Compute recency decay.
5. Combine all signals into one hybrid score.
6. Sort by score.
7. Apply diversity by limiting over-dominance from one session.

### Important helpers

- `_recency_weight()` computes age decay
- `_normalize_bm25()` converts FTS scores into normalized values
- `is_short_query()` changes behavior for short queries
- `merge_scores()` creates the final ranked results
- `_apply_diversity()` caps too many results from one session

### Why this file matters

Retrieval is only useful if ranking is smart. This file decides which memories appear first.

## `core/augmenter.py`

### Function

This prepares retrieved memory for prompt injection.

### Main logic

It answers two questions:

1. Does this prompt need memory?
2. If yes, what memory should be inserted?

### How it works

For `should_inject()`:

1. Lowercase the prompt.
2. Look for memory-trigger phrases.
3. Return a boolean with confidence and reason.

For `augment()`:

1. Decide whether to inject.
2. If injection is needed, call `engine.search(...)`.
3. Build a prompt that prepends memory context.
4. Return the augmented prompt and metadata.

### Important helpers

- `MEMORY_TRIGGER_PHRASES` contains heuristic trigger text
- `should_inject()` does lightweight memory detection
- `augment()` performs context injection

### Why this file matters

Storing memory is not enough. This file makes the stored memory usable during future prompting.

## `core/llm.py`

### Function

This is the unified interface for calling language models.

### Main logic

It hides the difference between Ollama and Claude behind one common API.

### How it works

1. Read provider config from environment variables.
2. If using Ollama, call local Ollama API.
3. If configured, use Claude as fallback.
4. Provide health and model-availability helpers.
5. Provide JSON-specific parsing helper.

### Important helpers

- `_call_ollama()` handles Ollama requests
- `_call_claude()` handles Claude requests
- `call()` is the main model call method
- `is_ollama_running()` performs health check
- `is_model_available()` verifies the Ollama model is actually pulled
- `call_json()` calls the model and parses JSON-like output

### Why this file matters

Many other core files rely on an LLM. This file centralizes that dependency and fallback logic.

## Quick File Dependency View

The rough dependency structure looks like this:

```text
engine
-> input_router
-> extractor
-> deduplicator
-> conflict_resolver
-> embedder
-> sqlite_store
-> faiss_store
-> kuzu_store
-> graph_enricher
-> retriever
-> scorer
-> augmenter
-> llm
```

Some direct relationships:

- `input_router` uses `chunker`, `code_parser`, and `pdf_parser`
- `chunker`, `deduplicator`, and `retriever` use `embedder`
- `extractor` and `conflict_resolver` use `llm`
- `retriever` uses `faiss_store`, `sqlite_store`, `kuzu_store`, and `scorer`
- `graph_enricher` writes to `kuzu_store`

## Best Short Explanation

If you need to explain the `core/` folder in one shot:

The `core/` folder is the memory engine. It routes input, chunks or parses it, extracts facts with an LLM, removes duplicates, resolves conflicts, stores memory in SQLite, FAISS, and Kuzu, retrieves memory using hybrid search, ranks it, and optionally injects it back into future prompts.
