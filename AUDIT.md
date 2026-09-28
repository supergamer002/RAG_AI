# AUDIT.md — Function-Flow Deep Audit (Round 3)

## Audit scope

Third Function-Flow Deep Audit after the user runtime test.

Methodology: entry point → function → preconditions → callees → state/side effects → outputs → exception branches → terminal state.

Evidence used:
- current `main` source on GitHub;
- current `rag/index/db_manager.py`;
- latest user runtime log (`Pasted text.txt`).

No claim of a successful full Windows RAG runtime is made beyond what the supplied runtime log demonstrates.

## 1. Executive status

The previous P0 syntax finding is CLOSED in the current `main`: `mappa_chunk_item()` now uses safe single quotes inside the f-string.

The user runtime test demonstrates that **Uvicorn/FastAPI starts and several endpoints respond**, but the database-dependent API surface is broken because the module-level `db_manager` is `None`.

The runtime log shows:
- `GET /api/settings` → 200;
- `GET /api/telemetry` → 200;
- `GET /api/eval` → 200;
- `GET /api/documents` → 500;
- `GET /api/chunks?page=1&pageSize=20` → 500;
- `GET /api/stats` → 500.

The document endpoint fails at `_get_documents_for_db(db_manager.active_id)` because `db_manager` is `None`. fileciteturn59file0L85-L91

The chunks endpoint fails when `get_chunks()` calls `db_manager.get_active_table()`. fileciteturn59file0L171-L179

The stats endpoint fails for the same reason. fileciteturn59file0L262-L270

The same failures repeat later in the log, confirming this is persistent state/initialization failure rather than a transient request. fileciteturn59file0L359-L447

## 2. Severity summary

| Severity | Finding | Status |
|---|---|---|
| P0 | `db_manager` becomes `None` when the RAG import block fails, while DB-dependent routes remain enabled | Confirmed runtime |
| P0 | Native PyArrow/LanceDB/RAG import failure is not preventing FastAPI startup but leaves a partially functional backend | Confirmed architecture/runtime behavior |
| P0 | DB-dependent frontend surface cascades into repeated HTTP 500 responses | Confirmed runtime |
| P1 | `/api/health` detects `db_manager is None`, but other DB routes do not share the same dependency guard | Confirmed source |
| P1 | Notification icon remains disconnected from a real feature | Open |
| P1 | SSE has visible error handling but no reconnect/backoff | Open |
| P1 | SSE token may be exposed in URL when authentication is enabled | Open |
| P2 | Full pytest/frontend build/runtime suite | Not fully verified |

## 3. Critical function-flow: startup → db_manager

### 3.1 Current startup chain

`webapp/backend/main.py` imports the RAG dependency block inside:

`try: from rag.index.db_manager import db_manager ...`

If **any** import in that single block raises an exception, execution enters the broad `except Exception`.

The except branch explicitly assigns:

`db_manager = None`

and also replaces the other RAG dependencies with `None`.

This design intentionally keeps FastAPI importable for diagnostic mode, but it has an important consequence: **the application can start in a degraded state while DB routes still execute code that assumes `db_manager` exists.**

### 3.2 DatabaseManager construction

Current `rag/index/db_manager.py` ends with:

`db_manager = DatabaseManager()`

`DatabaseManager.__init__()`:
1. stores the base directory;
2. creates the directory;
3. creates the registry path;
4. creates the lock;
5. calls `_load_registry()`.

`_load_registry()` either loads the registry or creates a default database entry and writes the registry.

Therefore, when `rag.index.db_manager` imports successfully, `db_manager` should be a real `DatabaseManager` instance.

### 3.3 Root cause reconstructed

The runtime state `db_manager is None` is therefore not produced by normal database activation logic.

It is produced by the **exception branch of the broad RAG import block in `main.py`**.

That means the next root-cause target is the exact exception stored in:

`RAG_IMPORT_ERROR`

Likely candidates include native dependency loading/import errors (PyArrow/LanceDB), but the exact exception must be read from `/api/health` or startup output before assigning a more specific cause.

## 4. Runtime branch map

### Branch A — RAG imports succeed

`main.py`
→ import `db_manager`
→ `DatabaseManager()`
→ registry load/create
→ routes receive valid manager
→ DB endpoints can call `active_id`, `get_active_table()`, etc.

Expected terminal states:
- successful DB API response;
- controlled HTTP error for invalid DB operation.

### Branch B — any RAG import fails

`main.py`
→ broad import exception
→ `RAG_IMPORT_ERROR = ...`
→ `db_manager = None`
→ FastAPI still starts
→ non-DB endpoints may respond
→ DB endpoints dereference `None`
→ unhandled `AttributeError`
→ HTTP 500.

This branch is **confirmed by the supplied runtime log**.

### Branch C — health endpoint in degraded mode

`/api/health`
→ detects `db_manager is None`
→ returns `lancedb=false`
→ includes database/import diagnostic information instead of crashing.

This is a good diagnostic branch, but it is not propagated to the rest of the API surface.

## 5. Confirmed broken flows

### Documents

`GET /api/documents`
→ `get_documents()`
→ `_get_documents_for_db(db_manager.active_id)`
→ `db_manager is None`
→ `AttributeError`
→ HTTP 500.

Runtime evidence: fileciteturn59file0L85-L88

### Chunks

`GET /api/chunks`
→ `get_chunks()`
→ `db_manager.get_active_table()`
→ `db_manager is None`
→ `AttributeError`
→ HTTP 500.

Runtime evidence: fileciteturn59file0L171-L179

### Stats

`GET /api/stats`
→ `get_stats()`
→ `db_manager.get_active_table()`
→ `db_manager is None`
→ `AttributeError`
→ HTTP 500.

Runtime evidence: fileciteturn59file0L262-L270

### Repetition

The same DB-dependent failures recur later in the runtime log, while settings/evaluation/telemetry continue to answer. This demonstrates a stable degraded backend state rather than an isolated request failure. fileciteturn59file0L359-L447

## 6. Important distinction: startup succeeds, application does not

The test disproves the previous assumption that a source-level startup blocker is still preventing Uvicorn.

The backend process is alive enough to serve multiple routes.

However, this is a **partial-start/degraded-start condition**, not a healthy application startup.

The current diagnostic architecture deliberately allows this condition, but it must expose a controlled dependency-unavailable response for DB routes instead of raw `AttributeError`/500.

## 7. Correct fix direction

Do **not** simply add unrelated `if db_manager is None` checks to every route.

First establish the exact import failure:

1. call `/api/health`;
2. inspect `startup_error`;
3. identify the failing RAG/native import;
4. verify `import pyarrow`, `import pyarrow.dataset`, and `import lancedb` in the same environment;
5. fix the dependency/import failure if possible.

Then add a centralized dependency guard for the intentional diagnostic/degraded mode so DB routes return a structured **503 Service Unavailable** with the real dependency error rather than an internal `AttributeError`.

Desired semantic contract:

- FastAPI available + RAG dependencies available + DB available → normal operation.
- FastAPI available + RAG dependency unavailable → health reports degraded state; DB-dependent routes return controlled 503.
- DB exists but operation fails → route-specific 4xx/5xx with preserved root exception.
- No silent conversion of dependency failures into generic browser `Failed to fetch`.

## 8. Other current findings

### Notification UI — P1

The notification-looking header element remains disconnected from a real notification state/panel.

Recommended behavior must be chosen explicitly:
- status-only indicator: remove interactive affordance;
- real notification feature: connect state, panel and data source.

### Telemetry SSE — P1

Error state is now visible, but there is no reconnect/backoff strategy.

### Query retrieval fallback — P1/P2

The current source narrows the fallback to `ValueError`, `KeyError`, and `RuntimeError`, which is better than the previous broad `Exception` branch. It still rebuilds FTS for errors that may not actually be FTS failures. The fallback reason should be classified more precisely.

### SSE authentication — P1/P2

When API authentication is enabled, SSE may receive the token through a query parameter because native EventSource cannot set an Authorization header. A long-lived token in a URL can leak through logs/history/proxies. Prefer a short-lived stream credential or session/cookie approach.

### Dead/disconnected code

- production `mockData.ts`: CLOSED;
- hardcoded profile/cluster/avatar: CLOSED;
- `run_evaluations(background_tasks)`: CLOSED/cleaned in current source; no unused parameter remains;
- `EvaluationsView.tsx` unused `API_BASE_URL`: still inspect/clean;
- notification UI: still disconnected.

## 9. Verification status

### Confirmed by current source

- `mappa_chunk_item()` f-string syntax is corrected.
- `DatabaseManager()` is constructed at module import when `rag.index.db_manager` imports successfully.
- `main.py` intentionally falls back to `db_manager = None` on any RAG import exception.
- `/api/health` contains a specific `db_manager is None` diagnostic branch.
- DB-dependent routes do not consistently guard that degraded state.

### Confirmed by runtime log

- FastAPI/Uvicorn serves requests.
- settings/telemetry/evaluation endpoints can return 200.
- documents/chunks/stats endpoints return 500 due to `db_manager is None`.

### Not yet confirmed

- exact `RAG_IMPORT_ERROR` value in the tested runtime;
- successful `import pyarrow`;
- successful `import pyarrow.dataset`;
- successful `import lancedb`;
- successful creation/loading of `DatabaseManager` in the user's Windows environment;
- successful `/api/health` response from the current tested process;
- end-to-end ingestion;
- end-to-end query;
- frontend production build.

## 10. Next exact actions

### P0 — root cause

1. Read `/api/health` from the same running backend.
2. Capture `startup_error` and `lancedb_detail`.
3. Test the failing native import directly.
4. Repair the dependency/import problem.
5. Restart backend.
6. Re-test `/api/health`, `/api/documents`, `/api/chunks`, `/api/stats`.

### P0 — degraded-mode safety

After the root dependency issue is fixed, add one centralized DB dependency helper/guard and route all DB-dependent endpoints through it.

Expected failure response when dependency is unavailable:

HTTP 503 with structured JSON containing:
- `detail`;
- dependency/startup error;
- retry/action hint.

No raw `AttributeError: 'NoneType' object has no attribute ...` should reach the client.

### P1

Then continue:

`health → databases → documents → chunks → stats → telemetry SSE → evaluation → ingestion → query`

## 11. Audit memory checkpoint

**CURRENT STATE:** backend source compiles sufficiently for the user's runtime test; previous f-string P0 is CLOSED.

**CURRENT CRITICAL FINDING:** intentional diagnostic import fallback leaves `db_manager=None`, while DB routes dereference it without a centralized guard.

**ROOT-CAUSE LOCATION:** `webapp/backend/main.py` RAG import `try/except`.

**DEPENDENCY INITIALIZER:** `rag/index/db_manager.py::db_manager = DatabaseManager()`.

**RUNTIME PROOF:** documents/chunks/stats 500 with `AttributeError` on `db_manager`; settings/telemetry/eval return 200.

**NEXT EXACT FUNCTION:** startup RAG import block in `webapp/backend/main.py`, then `DatabaseManager.__init__()` only after the import failure is identified.

**NEXT EXACT TEST:** `GET /api/health` on the same running backend and capture `startup_error`.

**STOP CONDITION:** do not mask the root native dependency/import problem with per-route patches before identifying the exact import exception.

## 12. Conclusion

The current test has moved the investigation past the previous syntax blocker.

The backend is now able to start, but it starts in a degraded state because the RAG import block has fallen into its diagnostic exception branch. The resulting `db_manager=None` state is confirmed to break the document, chunk and statistics flows.

The correct next step is therefore **root-cause the RAG import failure first**, then enforce a centralized 503 degraded-mode contract for DB-dependent routes.

**Audit status: OPEN — P0 native RAG import/dependency failure and degraded DB state.**


## 13. Applied fixes — Round 4

- Global RAG imports are now isolated per component; secondary import failures no longer disable a working database manager.
- Database-unavailable mode is centralized as HTTP 503 instead of raw `AttributeError`/500.
- `/api/health` now separates database import status from other component import errors and exposes `component_errors`.
- SSE reconnect uses a self-contained exponential-backoff loop.
- Authenticated SSE uses a one-time 60-second ticket instead of the long-lived API token in the URL.
- The SSE frontend no longer references an undefined `connectStream()`.
- `BackgroundTasks` is explicitly imported for the re-index route.
- `requirements.txt` now declares LanceDB, PyArrow, Requests, pypdf and Docling dependencies explicitly.

### Still open

- Exact native import failure in the user's environment remains unverified.
- Successful LanceDB/PyArrow initialization, DB endpoints, ingestion and query remain unverified.
