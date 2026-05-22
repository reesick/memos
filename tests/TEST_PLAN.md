# MemoryOS Master Test Suite — Plan

## Goal
One script that validates every layer of the architecture end-to-end.
Not just "did it return 200" — tests whether the **right data** comes back,
whether memory actually **persists and updates**, and whether the
**layer-by-layer pipeline** is firing correctly.

---

## Architecture Layers Under Test

```
Layer 1 · Input      input_router.py → chunker / code_parser / pdf_parser
Layer 2 · Intel      extractor.py → deduplicator.py → conflict_resolver.py
Layer 3 · Storage    sqlite_store.py · faiss_store.py · kuzu_store.py
Layer 4 · Retrieval  retriever.py (FAISS + BM25 + Kuzu) → scorer.py
Layer 5 · Exposure   api/main.py · augmenter.py
```

---

## Test Phases

### Phase 0 · Preflight
| Check | What it validates |
|---|---|
| `/health` returns 200 with `status=ok` | Server is up |
| `ollama: true` in health response | Ollama connected |
| `model` field = configured model | Right model loaded |

---

### Phase 1 · Layer 1 — Input Routing
| Check | What it validates |
|---|---|
| text input → `facts_extracted > 0` | Text pipeline fires |
| CSV input with 3 rows → `facts_added >= 3` | CSV parsed per row |
| JSON array input → structured facts extracted | JSON parser works |
| code input (Python class) → `facts_extracted > 0` | Code parser fires |
| empty content → 400 `EMPTY_CONTENT` | Guard at input layer |
| whitespace-only → 400 | Guard at input layer |
| 200k-word content → 400 `CONTENT_TOO_LARGE` | Size guard works |
| unknown source_type → 200 (fallback to text, no crash) | Graceful fallback |
| missing `content` field → 422 | Pydantic validation |

---

### Phase 2 · Layer 2 — Fact Extraction Quality
| Check | What it validates |
|---|---|
| "Alice is 28 years old, works at Google" → entity=Alice, attribute=age/employer | LLM extracts correctly |
| All returned facts have confidence >= 0.7 | Confidence threshold applied |
| Attribute is snake_case | Normalizer in extractor |
| Entity, attribute, value all non-empty | Pydantic validators |
| `facts_extracted` count >= expected minimum | LLM not silently failing |

---

### Phase 3 · Layer 2 — Deduplication (NOOP path)
| Check | What it validates |
|---|---|
| Add identical content twice → second call `facts_noop > 0, facts_added = 0` | Dedup fires |
| SQLite count unchanged after second add | No phantom inserts |
| memory_ids from second call = empty | No new IDs issued |

---

### Phase 4 · Layer 2 — Conflict Resolution
| Check | What it validates |
|---|---|
| Add "Bob lives in Mumbai" → stored | Baseline stored |
| Add "Bob now lives in Delhi" → `facts_updated >= 1` | Conflict detected |
| Search "Where does Bob live?" → Delhi in top results | New value wins |
| Search with `include_expired=True` → Mumbai visible as expired | Old value not destroyed |
| Expired fact has `expired_at` timestamp set | SQLite expiry written |

---

### Phase 5 · Layer 2 — First-Person Entity Resolution
| Check | What it validates |
|---|---|
| Add "My name is Vedant" | Name declared |
| Add "I work as a software engineer" | Self-reference used |
| Search "Vedant role" → finds software engineer fact | Resolved to real name |
| Search "I role" → also finds it | Either entity key works |
| Stored entity != "I" or "me" | Alias replaced in SQLite |

---

### Phase 6 · Layer 3 — Triple Store Consistency
| Check | What it validates |
|---|---|
| After add, `memory_id` appears in `/memory/list` | SQLite write confirmed |
| Search by value returns same `memory_id` | FAISS vector indexed |
| `/memory/graph?entity=X` returns node for entity | Kuzu node created |
| All three stores return same `memory_id` | Shared key across stores |

---

### Phase 7 · Layer 4 — Hybrid Retrieval Quality
| Check | What it validates |
|---|---|
| Semantic query (rephrased) → correct entity returned | FAISS embeddings work |
| Exact name query → BM25 hit in results | BM25 keyword path fires |
| Graph query → entity with relationships has edges | Kuzu traversal works |
| Results sorted by score descending | scorer.py ordering correct |
| Top result score > 0.4 for known entity queries | Relevance signal real |
| `context` field is non-empty string | Context assembly works |

---

### Phase 8 · Layer 4 — Filters & Pagination
| Check | What it validates |
|---|---|
| `source_filter=text` → all results have `source_type=text` | Filter respected |
| `session_filter=SESSION_A` → only session A results | Session isolation |
| `/memory/list?limit=3` → max 3 results | Pagination respected |
| `/memory/list?offset=3` → different page | Offset works |
| `include_expired=False` → no expired facts | Default hides expired |
| `include_expired=True` → expired facts visible | Flag works |

---

### Phase 9 · Layer 5 — Augmenter
| Check | What it validates |
|---|---|
| `should_inject`: "Do you remember Alice?" → `inject=True` | Trigger detection |
| `should_inject`: "Write a sort function" → `inject=False` | No false positives |
| `should_inject` response time < 100ms | Latency SLA (heuristic only) |
| `augment` with trigger → `injected=True`, `[Memory Context]` in prompt | Injection works |
| `augment` with `force_inject=True` on neutral prompt → injects if context exists | Force flag works |
| `augment` with pure code question → `injected=False` | Not injecting irrelevant |

---

### Phase 10 · Layer 5 — Full API Surface
| Endpoint | Golden path check |
|---|---|
| `GET /health` | 200, fields present |
| `POST /memory/add` | 200, stats fields present |
| `POST /memory/search` | 200, results + context |
| `POST /memory/should_inject` | 200, inject + check_ms |
| `POST /memory/augment` | 200, augmented_prompt |
| `GET /memory/graph` | 200, nodes + edges |
| `GET /memory/list` | 200, memories + total |
| `DELETE /memory/{id}` | 200, removed_from has sqlite |
| `GET /docs` | 200, Swagger HTML |

---

### Phase 11 · User Memory Lifecycle (E2E)
Full simulation of one user's memory across a conversation:
1. User says their name → stored under real name
2. User shares 3 more facts → all stored
3. User gives contradicting fact → old expired, new stored
4. User queries → correct current state returned
5. User deletes a fact → gone from search, gone from list
6. Final state verified

---

### Phase 12 · Multi-User Isolation
| Check | What it validates |
|---|---|
| User A adds fact about Alice | Stored under session A |
| User B adds fact about Bob | Stored under session B |
| User A searches with `session_filter=A` → no Bob | No cross-contamination |
| User B searches with `session_filter=B` → no Alice | Isolation works both ways |

---

### Phase 13 · Performance Assertions
| Operation | SLA |
|---|---|
| `/memory/should_inject` | < 100ms |
| `/memory/search` (warm) | < 2000ms |
| `/memory/list` | < 500ms |
| `/memory/graph` | < 1000ms |

---

### Phase 14 · Delete Cascade
| Check | What it validates |
|---|---|
| DELETE returns `removed_from` containing `sqlite` | SQLite row deleted |
| DELETE returns `removed_from` containing `faiss` | FAISS vector deleted |
| DELETE returns `removed_from` containing `kuzu` | Kuzu node removed |
| Search after delete → memory_id not in results | Not findable by FAISS |
| List after delete → memory_id not in list | Not in SQLite |
| Second DELETE → 404 | Idempotent delete |

---

### Phase 15 · Cleanup
- Delete all test-session memories via list + bulk delete
- Print final fact count (should match pre-test count)
- Print full pass/fail/warn/skip summary

---

## Scoring Philosophy
- **PASS** — correct behavior confirmed with real data check
- **FAIL** — wrong behavior, missing data, or wrong HTTP status
- **WARN** — behavior was acceptable but not ideal (soft assertion)
- **SKIP** — dependency failed so this case can't run

## Script Design Principles
- Hits the **live server** — no mocks
- Uses a unique `session_id` per run so tests don't pollute existing data
- Each phase is independent — a failure in phase 3 doesn't skip phase 7
- Cleans up all test data at the end
- Shows **timing** for every operation
- Final summary is the single source of truth: pass %, fail list
