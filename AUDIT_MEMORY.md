# AUDIT_MEMORY.md — Function-Flow Deep Audit Checkpoint

## STATUS

COMPLETED — 3 passate eseguite sul progetto `RAG_AI.zip`.

## Project Copy

`/mnt/data/function_audit_rag/project`

## Source

`/mnt/data/RAG_AI.zip`

## No Source Modifications

L'audit non ha modificato i file del progetto.

## Method

Function-first:

`Caller → Function → Input → Preconditions → Internal Logic → Callees → State → Output → Exit branches`

Ogni ramo importante è stato seguito fino a un'uscita terminale oppure marcato come blocked.

---

# Entry Points Completed

```text
FastAPI
├── /api/ingest
├── /api/query
├── /api/documents/{id}/reindex
├── /api/databases/*
├── /api/vectors/project
├── /api/eval/run
├── /api/settings
├── /api/telemetry*
└── /api/system/restart

React
├── App
├── IngestModal
├── QueryWorkbenchView
├── KnowledgeNodesView
├── VectorExplorerView
├── EvaluationsView
├── SettingsView
├── PipelineTelemetryView
├── DatabaseManagerModal
└── ChunkModal
```

# Critical Branches Mapped

## Ingest

```text
POST ingest
├── invalid input → HTTP error → EXIT
├── size/count violation → HTTP error → EXIT
├── supported files → save → job
└── job
    ├── target DB open fail → failed → EXIT
    ├── PDF → Docling/chunk
    ├── JSON → unit ingest/chunk
    ├── chunk empty → continue
    ├── embedding fail → file error
    ├── upsert → progress
    ├── FTS fail → warning
    └── final
        ├── zero chunks → failed
        └── chunks > 0 → completed
```

### Important deadlock state

`chunk_sezione` can enter:

```text
same i
same overlap
same current phrase
same branch
→ no progress
```

Confirmed with timeout test.

## Query

```text
POST query
├── empty → 400
├── empty DB → 200 empty
└── retrieval
    ├── dense
    ├── sparse
    └── hybrid
        └── retrieval exception → FTS rebuild → retry
    ├── rerank
    │   ├── success
    │   └── fallback top_n
    └── generation
        ├── success
        └── fallback answer
```

Important inconsistency:
`_esegui_query_su_tabella()` docstring says independent from active DB, but embedding model comes from `get_active_info()`.

## Benchmark

```text
start
→ capture DB id
→ 4 hardcoded test cases
→ check expected docs
→ query
→ retrieval metrics
→ answer similarity
→ LLM faithfulness
→ final results
```

Important inconsistency:
worker captures DB A but some helpers read active DB B.

## Vector Explorer

```text
sample rows
→ vector matrix
→ projection
   ├── UMAP
   ├── t-SNE
   └── PCA
→ KMeans
→ normalized points
→ UI
```

Known blockers:
- `umap-learn` missing from requirements.
- n=2 UMAP `n_neighbors=2` invalid.

## Settings

```text
GET settings
→ redacted token
PUT settings
→ merge defaults/current/new
→ validate
→ save config
→ replace global config
```

Important issue:
logical restart does not reconstruct DatabaseManager with new storage path.

# Data State Map

```text
Source file
→ temporary/upload source
→ parser
→ Section
→ Chunk
→ embedding
→ LanceDB row
→ FTS/index
→ retrieval
→ rerank
→ answer
→ UI
```

Missing persistent metadata at chunk row level:
- ingest timestamp
- parser
- original file size
- embedding model
- overlap setting

# Confirmed High Severity Findings

1. Chunker infinite loop — P0.
2. FTS refresh not guaranteed — P1.
3. Imported DB embedding model becomes `imported/unknown` — P1.
4. Embedding dimension not enforced against DB — P1.
5. Query table and embedder can belong to different DBs — P1.
6. Query UI has hardcoded demo answer/citations — P1.
7. Corrupt DB can be treated as new empty table — P2.
8. Vector Explorer default dependency missing — P1.
9. Benchmark hardcoded to four specific docs — P1.
10. Settings backend/frontend contracts drift — P1/P2.

# Runtime Evidence

PASS:
- Python compileall
- pure schema tests
- telemetry tests
- 7 pytest tests total

BLOCKED:
- full pytest: lancedb missing
- real reranker: FlagEmbedding missing
- real UMAP: umap-learn missing
- full frontend build: native node_modules/toolchain issue

REPRODUCED:
- chunker timeout 124 with two ~70-word sentences, target 100 tokens, overlap 0.5.

# Next Session Resume Point

No additional mapping is required before fixing the critical pipeline issues.
Start from:

1. `rag/ingest/chunker.py:101-130`
2. `_indicizza_chunks_incrementale()` DB/model binding
3. embedding dimension validation
4. FTS lifecycle
5. DB export/import metadata
6. query degraded/error states
7. UI removal of demo data
8. benchmark parametrization
9. settings application contract

After those fixes, repeat the same function-flow audit and then run the full integration suite with real dependencies.
