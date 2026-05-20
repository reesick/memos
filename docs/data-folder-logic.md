# Data Folder Logic Reference

## Purpose

This file explains the logic and function of the files inside the `data/` folder.

The `data/` folder is where MemoryOS keeps its persistent memory state on disk.

It is not source code. It is runtime data created and used by the memory engine.

## What the `data/` Folder Contains

At a high level, the folder stores three kinds of persistence:

1. SQLite database files
2. FAISS vector index files
3. Kuzu graph database files

That means the `data/` folder is the storage layer backing the memory pipeline.

## High-Level Storage Idea

When MemoryOS stores a fact, it is represented in multiple places:

- SQLite stores the full structured fact
- FAISS stores the fact embedding
- Kuzu stores graph relationships around that fact

All of them are connected through the same `memory_id`.

So the storage model is:

```text
one fact
-> SQLite row
-> FAISS vector entry
-> Kuzu graph fact node
```

## Files in `data/`

The current folder contains:

- `memoryos.db`
- `memoryos.db-wal`
- `memoryos.db-shm`
- `faiss.index`
- `faiss.index.map.npy`
- `kuzu_db/`

## `data/memoryos.db`

### Function

This is the main SQLite database file.

### Logic

This is the source of truth for stored memory.

If someone asks, "Where is the real memory stored?" this is the most correct answer.

### What it stores

Each memory record includes fields such as:

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

### Why it matters

Even if FAISS or Kuzu are missing or need rebuild, SQLite still contains the actual facts.

### Example

A fact like:

```text
Arjun role = backend lead
```

would exist in SQLite as a proper structured row with metadata.

## `data/memoryos.db-wal`

### Function

This is the SQLite WAL file.

WAL means write-ahead log.

### Logic

SQLite in WAL mode does not always write changes directly into the main `.db` file first.

Instead:

1. Changes are written to the WAL log
2. SQLite later merges them into the main database

### Why it exists

It improves:

- crash safety
- concurrency
- write performance

### Important note

This file is normal. It is not corruption and not an error.

## `data/memoryos.db-shm`

### Function

This is the SQLite shared memory file.

### Logic

It works together with the WAL file to coordinate database access.

### Why it exists

It helps SQLite manage state when WAL mode is enabled.

### Important note

This is also normal and expected when using SQLite WAL mode.

## `data/faiss.index`

### Function

This is the saved FAISS vector index.

### Logic

Whenever a memory fact is accepted, its text value is embedded into a vector.

That vector gets stored in FAISS so the system can later do semantic similarity search.

### Why it matters

This file enables queries like:

```text
Who handles backend?
```

to match a stored fact like:

```text
Arjun is the backend lead.
```

even if the wording is not identical.

### Important note

This file stores vectors, not full fact records.

The actual fact text still lives in SQLite.

## `data/faiss.index.map.npy`

### Function

This stores the ID mapping for the FAISS index.

### Logic

FAISS internally uses integer IDs, but MemoryOS uses string-based IDs like:

```text
mem_ab12cd34
```

So this file maps:

- MemoryOS `memory_id`
- FAISS internal integer ID

### Why it matters

Without this mapping, FAISS could return a vector match but the system would not know which memory record it belongs to.

### Example

Possible internal relationship:

```text
mem_9a7b3c11 -> 42
```

where:

- `mem_9a7b3c11` is the MemoryOS ID
- `42` is the FAISS internal ID

## `data/kuzu_db/`

### Function

This directory contains the Kuzu graph database files.

### Logic

Kuzu stores graph-based memory structure.

That includes:

- entity nodes
- fact nodes
- edges between them

### Why it matters

It lets MemoryOS do graph-style retrieval such as:

- entity relationship lookup
- subgraph visualization
- bridge detection between related memories

### Example

If SQLite stores:

```text
Alice role = senior engineer
Alice team = platform
```

then Kuzu can represent that as:

- entity node: `Alice`
- fact node: `senior engineer`
- fact node: `platform`
- relationship edges from `Alice` to both facts

## How Data Gets Written

When `engine.add(...)` stores a new fact, the following usually happens:

1. SQLite inserts the full record into `memoryos.db`
2. FAISS stores the vector in `faiss.index`
3. The FAISS ID mapping is saved in `faiss.index.map.npy`
4. Kuzu creates the fact node and graph edge in `kuzu_db/`

So one accepted fact produces synchronized entries across the full `data/` layer.

## Which Data File Is Most Important

If you need to rank importance:

1. `memoryos.db`
2. `faiss.index`
3. `faiss.index.map.npy`
4. `kuzu_db/`
5. `memoryos.db-wal`
6. `memoryos.db-shm`

### Why SQLite is first

SQLite is the primary store and source of truth.

FAISS and Kuzu are derived indexes optimized for retrieval.

That means:

- SQLite is essential
- FAISS can be rebuilt from SQLite
- Kuzu can also be recreated from stored facts if needed

## Relationship Between Core and Data

The `/core` folder is the logic.

The `/data` folder is the persistent state produced by that logic.

Direct mapping:

- `core/sqlite_store.py` manages `memoryos.db`
- `core/faiss_store.py` manages `faiss.index` and `faiss.index.map.npy`
- `core/kuzu_store.py` manages `kuzu_db/`

So you can think of it like:

```text
core = brain and logic
data = saved memory state
```

## What Happens During Search

When a user searches memory:

1. FAISS checks vector similarity using `faiss.index`
2. SQLite checks keyword matches using `memoryos.db`
3. Kuzu checks graph relations using `kuzu_db/`
4. Results are merged into one final output

So the `data/` folder is not passive storage only. It actively supports retrieval behavior.

## What Happens During Update or Conflict Resolution

If an old fact is replaced:

1. SQLite marks the old fact as expired
2. A new SQLite row is inserted for the updated fact
3. FAISS removes the old vector and adds a new one
4. Kuzu expires old graph edges and creates new ones

So the `data/` folder reflects both current memory and memory history.

## What Happens During Delete

If a memory is deleted:

1. SQLite deletes the record
2. FAISS removes the vector
3. Kuzu removes or expires graph data for that fact

This keeps all storage layers aligned.

## Typical Questions You May Be Asked

### Is `data/` source code?

No. It is runtime storage created by the application.

### Why are there multiple storage files for one system?

Because the project uses a hybrid memory architecture:

- SQLite for truth and metadata
- FAISS for semantic similarity
- Kuzu for graph relationships

### Why are there three SQLite files?

Because SQLite is running in WAL mode:

- `.db` is the main database
- `.db-wal` is the write-ahead log
- `.db-shm` is the shared memory coordination file

### Can FAISS be reconstructed?

Yes, because the actual facts still exist in SQLite and embeddings can be recreated.

### Can Kuzu be reconstructed?

Yes, in principle, because graph facts come from the stored memory records.

### Which file should be called the source of truth?

`memoryos.db`

### Why is `faiss.index.map.npy` needed?

Because FAISS uses integer IDs internally, while the application uses string memory IDs.

## Best Short Explanation

If you need to explain the `data/` folder quickly:

The `data/` folder stores MemoryOS runtime memory state. SQLite stores the real facts, FAISS stores semantic vectors, and Kuzu stores graph relationships. All of them are connected through a shared `memory_id`, with SQLite acting as the source of truth.
