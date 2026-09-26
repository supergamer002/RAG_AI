# FIX_LIST.md — Prioritized Fix / Verification List

## 🔴 P0 — Blockers

| ID | Problem | Where | What to do | Verify |
|---|---|---|---|---|
| P0-01 | Infinite loop in chunker | `rag/ingest/chunker.py:101-130` | Guarantee progress of `i`; guard against unchanged `(i, overlap)`; emit/advance oversized-overlap case | Regression test with 2 long normal sentences + 50% overlap; assert termination |
| P0-02 | New chunks can be invisible to FTS | `main.py:605,734`, `hybrid_search.py` | Rebuild/refresh FTS after ingest or use supported incremental FTS update | Ingest new file then sparse/hybrid query must find it |
| P0-03 | Embedding vector dimension unchecked | `embed_manager.py`, `main.py`, `store.py` | Compare vector length with DB dimension before upsert/query | DB dimension 384/768/1024 tests |
| P0-04 | Embedding uses active DB instead of target DB | `main.py:645-648`, query path | Pass `database_id` and resolve model/URL/dimension from target DB only | Switch DB during job; target remains internally consistent |
| P0-05 | Import loses embedding model | `db_manager.py:292-365+` | Export metadata JSON and restore `embeddingModel`, `dimension`, schema version | Export → import → query without manual reconfiguration |
| P0-06 | Query UI displays fake answer/citations | `QueryWorkbenchView.tsx:315-347` | Remove demo fallback from operational state | Empty/failing query must never show fake docs/answer |
| P0-07 | Corrupt/unopenable table may become empty new table | `store.py:46-58` | Distinguish NOT_FOUND from OPEN_ERROR/SCHEMA_ERROR | Corrupt/incompatible DB must return explicit error |

## 🟠 P2 — High priority

| ID | Problem | Where | What to do |
|---|---|---|---|
| P2-01 | Query hides backend detail in UI | `QueryWorkbenchView.tsx` | Display API `detail` / `Error.message` |
| P2-02 | Retrieval catch is too broad | `_esegui_query_su_tabella` | Catch specific exceptions; preserve primary error |
| P2-03 | Reranker failure looks successful | `_esegui_query_su_tabella` | Add degraded state + diagnostics |
| P2-04 | Generator failure looks successful | `_esegui_query_su_tabella` | Distinguish LLM answer from fallback answer |
| P2-05 | Query uses active DB model with explicit table | `_esegui_query_su_tabella` | Derive all config from same DB as table |
| P2-06 | Reindex hardcodes chunk/OCR settings | `reindex_document()` | Persist document ingestion settings or use explicit current settings |
| P2-07 | Reindex dead else branch | `reindex_document()` | Remove unreachable branch / simplify flow |
| P2-08 | storagePath not applied by logical restart | `restart_runtime`, `DatabaseManager` | Reconstruct manager or require full process restart |
| P2-09 | `indexAlgorithm` UI/backend mismatch | Settings | Use same enum and actual LanceDB implementation |
| P2-10 | distanceMetric/config values not wired | Settings/store/search | Make settings operational or remove them |
| P2-11 | UMAP dependency missing | `requirements.txt` | Add `umap-learn` or set PCA as safe default |
| P2-12 | UMAP n=2 invalid | `project_vectors()` | Special-case `n < 3` |
| P2-13 | Benchmark hardcoded to 4 documents | `EVAL_TEST_CASES` | Make dataset/cases configurable or corpus-derived |
| P2-14 | Benchmark DB race | `run_evaluations()` | Capture table/model/doc metadata and never re-read active DB |
| P2-15 | No document ingest metadata persistence | `store.py` schema | Add ingestion metadata record/side table |
| P2-16 | `KnowledgeDocument` omits JSON | frontend types | Add JSON and align actual backend types |
| P2-17 | JSON filter absent | `KnowledgeNodesView` | Add JSON filter |
| P2-18 | “Docling AST” claim too broad | `KnowledgeNodesView` | Display actual parser/type-specific metadata |
| P2-19 | Real pagination absent | `get_chunks/get_documents` | Push pagination/filtering into LanceDB queries |
| P2-20 | Activate DB does not validate physical DB | `DatabaseManager.activate_database` | Open/validate before activation |

## 🟡 P3 — Medium / Quality

| ID | Problem | Where | What to do |
|---|---|---|---|
| P3-01 | Global vector filter not applied to rendered points | `VectorExplorerView` | Render `visibleScatterPoints` |
| P3-02 | Redundant chunk sample fetch | `VectorExplorerView` | Remove unused fetch |
| P3-03 | Voronoi 256 has no backend implementation | Vector UI | Remove or implement |
| P3-04 | Rerank score 0 can be misleading in Vector UI | Vector UI | Show N/A when unavailable |
| P3-05 | SSE no reconnect | `PipelineTelemetryView` | Exponential backoff reconnect |
| P3-06 | Telemetry is aggregate, not event stream | backend telemetry | Clarify UI or implement events |
| P3-07 | Default config drift | config/backend/frontend | Single source of truth |
| P3-08 | CORS origin mismatch | config/frontend | Normalize localhost/127.0.0.1 policy |
| P3-09 | fallback config storage path mismatch | `caricaconfig`/DB manager | Single default path |
| P3-10 | localStorage token risk | `src/api.ts` | Document or move to safer storage where applicable |
| P3-11 | SSE token query-string exposure | telemetry stream | Short-lived stream token/cookie if needed |
| P3-12 | stale frontend test directive | `IngestModal.tsx` | Keep only necessary TS suppression/declaration |
| P3-13 | stale test patch | `tests/test_fonte_path.py` | Patch actual embedder path |
| P3-14 | `test_backend.py` missing `MagicMock` import | tests | Add import |
| P3-15 | async test jobs may leak state | max payload tests | Await/cleanup jobs/files |

## ⚪ Runtime Verification Required

1. Run full pytest with `lancedb` installed.
2. Run frontend lint/build with clean `npm ci`.
3. Run actual Ollama embedding model used by the DB.
4. Run actual Docling PDF ingestion.
5. Run actual FlagEmbedding reranker.
6. Run actual UMAP projection.
7. Perform a real end-to-end upload → query → benchmark cycle on a clean DB.

## Acceptance Criteria After Fix

```text
INGEST
upload → parse → chunk → embed → upsert → FTS → completed

DATA
real ingest timestamp + size + parser + model + dimension

QUERY
query → retrieval → rerank → generation
with explicit degraded/error states

MULTI-DB
DB A uses only A metadata/config
DB B uses only B metadata/config

VECTOR
PCA works without optional deps
UMAP works when dependency installed
n=1/n=2 safe

BENCHMARK
configurable corpus/cases
stable target DB
no hardcoded demo docs

UI
never display fake results as verified results
```
