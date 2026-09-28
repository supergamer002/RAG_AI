# AUDIT.md — Function-Flow Deep Audit (Round 2)

## Audit scope
Second full audit of current main after the latest fix series.

Methodology: Function-Flow Deep Audit — entry point → function → inputs/preconditions → callees → side effects/state → outputs → success/failure/exception branches → terminal states.

Latest commits inspected include native dependency startup diagnostics, removal of production mock data, frontend API error normalization, evaluation API error surfacing, telemetry SSE diagnostics, and removal of hardcoded profile data.

**Important:** this is a source-level audit against GitHub main. No successful Windows runtime/build is claimed unless directly verified.

## 1. Current status

The previous P0/P1 issues around generic frontend errors, hardcoded profile data and production mockData.ts are addressed in the current repository.

NEW P0: webapp/backend/main.py contains this source line in mappa_chunk_item():

    "dimensions": (f"{len(c.get("vector", []))}d" if c.get("vector") is not None and len(c.get("vector", [])) else None),

The inner double quotes conflict with the outer f-string quoting. If this is the literal executed source, Python compilation fails before FastAPI can start.

Therefore the audit remains OPEN until py_compile and backend import succeed.

## 2. Severity summary

| Severity | Finding | Status |
|---|---|---|
| P0 | Invalid f-string quoting in mappa_chunk_item() | Confirmed by source inspection; compile test required |
| P0 | Native PyArrow/LanceDB startup failure | Mitigated diagnostically; runtime verification required |
| P0 | Cascading frontend Failed to fetch | Diagnostics improved; runtime verification required |
| P1 | Notification icon has no panel/handler but remains visually interactive | Still present; UX inconsistency |
| P1 | SSE error handling | Improved; runtime connection required |
| P1 | Evaluation API errors | Improved |
| P1 | Evaluation worker DB capture | Implemented |
| P1 | Health dependency diagnostics | Implemented |
| P1 | Export/import embedding metadata | Previously implemented; runtime verification required |
| P1 | Long-lived API token in SSE query string when auth is enabled | Security/design weakness |
| P2 | Full pytest/build/runtime suite | Not verified in this audit environment |

## 3. Entry points and function flow

### Backend startup
main.py → standard imports → RAG import block → config → FastAPI → middleware → reranker wrapper → generator wrapper → routes.

The RAG imports are now wrapped in a try/except and store RAG_IMPORT_ERROR so /api/health can report native dependency failures.

Important limitation: this only protects the explicit RAG import block. Syntax errors or exceptions during later global initialization still prevent startup.

CrossEncoderReranker itself loads FlagEmbedding lazily; its constructor stores the model name and actual heavy model loading occurs on first rerank.

### Health
/api/health → Ollama HTTP probe → active DB embedding model → /api/embed probe → LanceDB dependency state → active table → vector dimension → JSON response.

Response exposes fastapi, lancedb, lancedb_detail, ollama, ollama_detail, startup_error and timestamp.

This is materially better than collapsing native dependency failures into browser-level Failed to fetch.

### API layer
apiFetch adds optional Bearer auth, AbortController, 15-second timeout and ApiError classification: network, timeout, http, malformed.

apiJson parses JSON, reports malformed successful responses and converts non-2xx responses into structured ApiError.

### Telemetry
PipelineTelemetryView → getApiToken → EventSource(/api/telemetry/stream) → connecting → connected → telemetry event → JSON parse → logs.

Invalid SSE JSON becomes visible error state. EventSource errors now expose the stream URL instead of a generic failure.

Remaining issue: onerror immediately closes the source and there is no reconnect/backoff loop.

### Evaluation
POST /api/eval/run → capture db_manager.active_id → create job → worker thread → get_table_for_db(captured_db_id) → document check → query on captured DB → captured DB embedding model → metrics → terminal job.

Database identity is consistently carried through the worker, removing the previous active-DB race.

Terminal states: completed, completed_with_errors, failed; individual cases can be Skipped, Found, Not found or Error.

### Ingestion
/api/ingest → validation → captured database → async worker → extraction → chunking → incremental embedding batches → LanceDB upsert → FTS → terminal state.

Confirmed protections: target DB is explicit, embedding model follows target DB, vector dimensions are checked before commit, and batch progress is preserved when a later batch fails.

### Query
/api/query → validation → active table → target DB embedding → dense/sparse/hybrid retrieval → rerank → generation → source mapping.

Fallbacks exist for retrieval, reranker and generation. The broad retrieval except Exception currently rebuilds the FTS index for any retrieval exception; this can hide unrelated failures and cause unnecessary work.

## 4. UI audit

### Notifications
The previous fake notification panel bug has not been replaced by a real notification feature. Header.tsx now renders a notification-looking div with no handler.

Current classification: P1 UX inconsistency. If this is a status indicator, remove cursor-pointer and notification affordance. If it is meant to be a feature, implement state, panel and data source.

### Top-right runtime widget
The previous synthetic username/cluster/avatar has been removed. The widget now represents runtime RAG state with hub/cloud-off icon and runtime-status tooltip.

### Mock data
webapp/frontend/src/data/mockData.ts is absent from current main. Previous production mock-data finding is CLOSED.

## 5. Security audit

API middleware applies rate limiting and optional Bearer token validation.

SSE accepts token query parameter because native EventSource cannot set arbitrary Authorization headers.

This works functionally but a long-lived API token in a URL can leak into browser/proxy/history logs. Prefer a short-lived stream credential or cookie/session mechanism when auth is enabled.

## 6. Dead/disconnected code

- Production mockData.ts: removed.
- Fake profile identity: removed.
- Notification UI: disconnected from a real feature.
- run_evaluations(background_tasks): parameter is unused because the worker is explicitly scheduled with asyncio.to_thread.
- EvaluationsView.tsx declares API_BASE_URL but does not use it.

## 7. Confirmed P0

BUG-P0-001 — invalid f-string in mappa_chunk_item.

Location: webapp/backend/main.py.

Current expression:

    f"{len(c.get("vector", []))}d"

Expected safe form:

    f"{len(c.get('vector', []))}d"

Impact if literal: main.py cannot compile/import, FastAPI cannot start, /api/health cannot run, and frontend runtime testing is blocked.

Required verification:

    python -m py_compile webapp/backend/main.py
    python -c "import webapp.backend.main"

Only after these pass should runtime testing continue.

## 8. Remaining P1/P2 queue

P1 runtime sequence:
1. py_compile and backend import.
2. PyArrow import and pyarrow.dataset.
3. LanceDB import.
4. Uvicorn startup.
5. /api/health.
6. Ollama embedding probe.
7. telemetry SSE.
8. evaluation start/status.
9. ingestion.
10. query.

P1 UX:
1. Decide notification status-only vs real feature.
2. Add SSE reconnect/backoff.

P1/P2 robustness:
1. Narrow retrieval exception handling.
2. Log fallback activation and original exception.
3. Avoid long-lived API token in SSE query string when auth is enabled.
4. Remove unused variables/parameters.

## 9. Test status

Source tests required:
- python -m py_compile webapp/backend/main.py
- import webapp.backend.main
- import pyarrow
- import pyarrow.dataset
- import lancedb
- frontend TypeScript/Vite build.

Runtime sequence:
startup → health → dependencies → frontend → telemetry → evaluation → ingestion → query → database management.

Full runtime/build success has NOT been verified in this audit.

## 10. Audit memory checkpoint

CURRENT HEAD: main after startup diagnostics, API error normalization, telemetry diagnostics, mock/profile cleanup.

LAST CRITICAL FINDING: P0 source-level f-string syntax defect in main.py::mappa_chunk_item.

CLOSED SINCE PREVIOUS AUDIT:
- hardcoded profile/cluster/avatar
- production mockData.ts
- generic API fetch diagnostics
- generic evaluation errors
- opaque telemetry SSE errors
- native dependency failures now have a diagnostic path
- evaluation target DB race
- target DB embedding selection
- vector dimension validation
- chunker non-progress branch.

OPEN:
- P0 compile/import verification
- PyArrow/LanceDB Windows runtime verification
- /api/health runtime
- Ollama health
- SSE real connection/reconnect
- evaluation real execution
- ingestion/query end-to-end
- notification UX decision
- narrow retrieval exception
- SSE token handling when auth is enabled.

NEXT EXACT FUNCTION: webapp/backend/main.py::mappa_chunk_item().

NEXT EXACT TEST: python -m py_compile webapp/backend/main.py.

STOP CONDITION: do not continue to high-level RAG runtime testing until backend source compilation/import is confirmed.

## 11. Conclusion

The repository is materially improved compared with the previous audit: fake profile data and production mock data are gone, API failures are diagnosable, telemetry failures are visible, and evaluation/database context is more robust.

However, the current source must first pass Python compilation. The mappa_chunk_item f-string is therefore the immediate blocker.

**Audit status: OPEN — P0 source verification required.**