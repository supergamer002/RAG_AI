# AUDIT — Current architecture note

> **Current branch state: `unified-clean-app`**
>
> Sections below that reference `webapp/`, `rag/`, LanceDB, PyArrow, the old React frontend, or the old ingestion endpoints are **historical audit records** from earlier architectures. Those paths have been removed from this branch.
>
> The active runtime is now:
>
> `run.py → FastAPI (app/main.py) → SQLite + Ollama + lazy Cross-Encoder → app/static/index.html`
>
> The active GUI is the unified single-page frontend served by FastAPI. Its ingestion dashboard uses the real persistent job API and backend stage/chunk progress. The supplied Document Intelligence GUI was used as the visual/interaction reference; its mock Express server and unrelated frontend/backend modules were not copied.
>
> Removed from the active tree: legacy `rag/`, legacy `webapp/`, runtime `data/`, debug log, duplicate audit skill, stale tests tied to the legacy architecture, and other generated/runtime artifacts.
>
> Active tests retained: `tests/test_api.py` and `tests/test_app_reranker.py`.
>
> Last local validation of the active backend test subset: **10 passed**. Windows runtime GUI validation still requires the user's local test run.

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


## 14. Applied fixes — Round 5 / Windows native DLL

User runtime update: the application fixes were applied, but Windows still blocks the native `arrow_acero.dll` DLL.

### Current interpretation

The remaining blocker is now classified as a **Windows native dependency loading problem**, not as a FastAPI routing/state bug.

`arrow_acero.dll` belongs to the native Arrow/PyArrow stack used by the RAG/LanceDB dependency chain. If Windows prevents that DLL from loading, the affected Python import can still fail even though the Python packages are installed correctly.

The backend's new per-component import isolation and centralized degraded-mode handling should prevent this native failure from becoming an opaque cascade of `AttributeError`/500 responses.

### Required verification

On the same Windows Python environment used to launch the backend:

```powershell
python -c "import pyarrow; print(pyarrow.__version__)"
python -c "import pyarrow.dataset; print('pyarrow.dataset OK')"
python -c "import lancedb; print('lancedb OK')"
```

Then:

```
GET /api/health
```

The important fields are:
- `lancedb`
- `lancedb_detail`
- `startup_error`
- `component_errors`

### Windows-specific blocker

If the import still reports `arrow_acero.dll` as blocked, the next investigation must be at the Windows DLL-loading/security layer rather than in application Python code.

Do not replace the working FastAPI/RAG error handling merely to hide this condition.

### Audit state

- Python syntax blocker: CLOSED.
- `db_manager=None` cascading 500 behavior: FIXED at application-error-handling level.
- Native `arrow_acero.dll` Windows loading: **OPEN / current blocker**.
- Full LanceDB/database runtime: BLOCKED until the native dependency loads.
- Ingestion/query end-to-end: BLOCKED by the same dependency chain.

**NEXT EXACT TEST:** run the three Python import commands above and capture the first command that fails, including its complete exception text.

**STOP CONDITION:** do not continue modifying RAG query/ingestion logic while `arrow_acero.dll` cannot be loaded by the same Python interpreter running FastAPI.


## 15. Applied fixes — Round 6 / Backend debug mode and persistent error tracing

### User runtime finding

The user reports that a large portion of API requests fail at runtime. The next objective is therefore to make every relevant failure diagnosable from the same WSL process that serves FastAPI, without relying on browser-only "Failed to fetch" messages.

### Uvicorn debug-mode decision

The current Uvicorn CLI does **not** expose a `--debug` option. Its documented development/logging controls include `--reload` and `--log-level debug`. This was verified against the current Uvicorn documentation.

To keep the behavior explicit and stable, the project now uses two mechanisms:

1. launcher-level `RAG_DEBUG=1` to enable the application's debug logger deterministically;
2. Uvicorn `--log-level debug` to enable detailed server logging.

The application also recognizes an already-debug-enabled Uvicorn logger when possible, so a manual `--log-level debug` invocation can activate the same logging path.

### New diagnostic component

New file:

`webapp/backend/debug_logging.py`

Responsibilities:

- determines whether debug mode is active;
- creates/uses exactly one file handler even under Uvicorn reload;
- writes to **`log_debug.log` at the project root**;
- uses `RotatingFileHandler` with 10 MB maximum per file and 3 backups;
- never allows a logging failure to prevent application startup;
- records full Python traceback for real exceptions;
- records sanitized runtime and environment information;
- records installed package versions without importing those packages;
- records request method/path/query/client and a safe subset of headers;
- redacts token/password/API-key/cookie/credential fields and proxy URLs.

### Request exception flow

A global FastAPI middleware now wraps request execution:

`request → route/middleware chain → response`

Branch A — no exception:

`response returned → normal response`

Branch B — unhandled exception:

`route → exception → debug_exception() → log_debug.log with traceback/runtime/env → exception re-raised → FastAPI/Uvicorn keeps normal HTTP error handling`

This is intentional: the logging layer observes the failure without replacing the application's error semantics.

Branch C — a route internally catches an exception and returns a controlled fallback:

The affected code paths now call `debug_exception()` before falling back or raising an HTTP error. This prevents silent failures from disappearing from the diagnostic record.

### Covered high-value failure paths

The debug logger is now explicitly connected to:

- RAG component import failures during module startup;
- unhandled HTTP request exceptions;
- query pipeline failures;
- reranking fallback failures;
- LLM generation fallback failures;
- single-file ingestion job failures;
- batch ingestion database-open failures;
- per-file ingestion failures;
- FTS rebuild failures during ingestion;
- database deletion OSError failures;
- ingestion source-storage preparation failures;
- upload save failures;
- evaluation case failures;
- evaluation job failures.

This is deliberately broader than only logging HTTP 500 responses: background jobs and swallowed pipeline fallbacks can fail without producing a request-level exception.

### Sensitive-data policy

`log_debug.log` is a local diagnostic artifact and is now explicitly ignored by Git.

The logger does **not** write the request body. This avoids dumping uploaded document contents or arbitrary JSON payloads into the debug file.

The environment snapshot is selective rather than a raw dump of all environment variables. Known secret-bearing keys are redacted, and HTTP/HTTPS proxy values are redacted completely because they can embed credentials.

### Startup launcher

A canonical root-level `start.bat` has been added.

Its backend command is:

`wsl --cd "%PROJECT_DIR%" -- env RAG_DEBUG=1 python -m uvicorn webapp.backend.main:app --host 0.0.0.0 --port 8000 --reload --log-level debug`

The Windows start/cmd invocation was also hardened to avoid nested-command quoting problems when the project path contains spaces.

Ollama and the frontend continue to run inside WSL.

This avoids depending on a nonexistent Uvicorn `--debug` flag and ensures the debug flag reaches the same Linux/WSL Python process that loads LanceDB/PyArrow.

### Stability properties

- no debug logging when debug mode is off;
- idempotent handler installation under reload;
- bounded log file growth through rotation;
- logging failures are fail-open and cannot block API startup;
- sensitive configuration values are redacted;
- background-task failures are logged separately from request failures;
- the diagnostic middleware does not alter successful responses;
- existing controlled HTTP error contracts remain intact.

### Verification status

The changes are source-level and launcher-level. They have **not** yet been runtime-verified in the user's WSL environment in this turn.

Required verification after the next startup:

1. start with `start.bat`;
2. reproduce one failing API request;
3. inspect project-root `log_debug.log`;
4. confirm the file contains:
   - timestamp;
   - endpoint/method;
   - exception type/message;
   - complete traceback;
   - Python executable/version;
   - platform/architecture;
   - relevant WSL/Python/Ollama/debug environment;
   - installed versions for key packages;
5. use the **first root exception** in the log as the next audit target.

### Current audit state

- Native Windows `arrow_acero.dll` blocker: bypassed for the application runtime by using the verified WSL environment; Windows-side native load remains irrelevant to the WSL backend path.
- Debug instrumentation: **APPLIED**.
- Persistent error traceback: **APPLIED**.
- Controlled and redacted runtime/environment snapshot: **APPLIED**.
- WSL debug launcher: **APPLIED**.
- Actual causes of the current API failures: **OPEN** until the first WSL `log_debug.log` traceback is captured.
- E2E ingestion/query/API verification: **OPEN**.

**NEXT EXACT ACTION:** run the updated `start.bat`, reproduce the first failing API call, and use the first exception/traceback in `log_debug.log` as the root-cause input.

**STOP CONDITION:** do not patch individual endpoints solely from the browser error message. The next fix should follow the first concrete traceback and its function-flow branch.


## 16. Applied fixes — Round 7 / Debug log reliability correction

### User runtime finding

After Round 6, the user reported that `log_debug.log` remained empty despite API failures.

### Root cause of the diagnostic mechanism

The previous implementation wrote through the Python logging subsystem. Under Uvicorn/reload, logging configuration can be re-applied after the application module installs its handlers. Therefore the application could remain healthy while the custom file handler was absent or disconnected from the root logger.

This made the diagnostic mechanism itself insufficiently deterministic.

### Corrected architecture

`webapp/backend/debug_logging.py` no longer depends on Uvicorn/Python logging handlers to persist the debug file.

The write path is now:

`exception/event → debug_exception()/debug_message() → _write_event() → direct file append → flush → fsync`

The debug logger creates:

`<project root>/log_debug.log`

directly from the module location, independently of the current working directory.

### Startup proof

When `RAG_DEBUG=1` is present, `configure_debug_logging()` immediately writes a `debug_startup` event.

Therefore the next startup provides a binary diagnostic:

- `log_debug.log` created/contains `debug_startup` → debug flag reached the Python process and file writing works;
- no file/no marker → the problem is in launcher/environment/path before request handling.

### Exception proof

`debug_exception()` now serializes the traceback explicitly with:

`traceback.format_exception(...)`

and stores it in the JSON event.

It no longer relies on `exc_info` formatting by a third-party logger.

### Reliability controls

- direct append with UTF-8 and replacement for malformed output;
- explicit `flush()`;
- explicit `os.fsync()`;
- per-process write lock;
- bounded log rotation at 10 MB with three backups;
- rotation failures are non-fatal;
- write failures are non-fatal;
- secret/proxy redaction remains active;
- request body remains excluded.

### Debug mode contract

The application debug file is now controlled by exactly one explicit runtime switch:

`RAG_DEBUG=1`

The launcher already sets this variable before starting Uvicorn in WSL.

`--log-level debug` remains useful for Uvicorn console diagnostics, but it is no longer required for writing `log_debug.log`.

### Current audit state

- Debug file generation mechanism: **REPLACED WITH DIRECT WRITER**.
- Startup marker: **APPLIED**.
- Full traceback serialization: **APPLIED**.
- Runtime/environment snapshot: **APPLIED**.
- Current API root causes: **OPEN**.
- E2E API verification: **OPEN**.

**NEXT EXACT TEST:** start the current `start.bat`. Before reproducing any API request, verify that the project-root `log_debug.log` exists and contains a `debug_startup` event. Then reproduce one failing request and inspect the first `exception` event.

**STOP CONDITION:** if the startup marker is absent, investigate the WSL launcher/environment variable propagation before changing API code.


## 17. Applied fix — Round 8 / Ollama WSL launcher

### User runtime finding

The debug backend launcher starts through WSL, but the Ollama server did not start reliably.

### Failure path

The previous launcher used:

`start → cmd.exe → wsl.exe → ollama serve`

This introduced an unnecessary Windows command-shell layer around a long-running Linux process.

### Corrected flow

The launcher now uses:

`start → wsl.exe → bash -lc → Ollama`

with a process guard:

`pgrep -x ollama`

Branch A — Ollama already running:

`pgrep → true → no second server → terminal reports already active`

Branch B — Ollama not running:

`pgrep → false → exec ollama serve`

Using `exec` makes the WSL command process become the Ollama server process instead of leaving an extra shell process supervising it.

### Stability objective

This removes the previous `cmd /k` wrapper from the Ollama path and avoids accidental duplicate Ollama instances on repeated launcher executions.

### Current verification status

Source/launcher fix applied, but actual Ollama process startup has not yet been runtime-verified in the user's WSL environment.

**NEXT EXACT TEST:** run `start.bat` and inspect the dedicated Ollama WSL terminal. It must show either `Ollama server gia attivo.` or the normal Ollama server startup output.

**STOP CONDITION:** if the WSL terminal still exits immediately, capture its exact console error. The next fix must target that concrete WSL/Ollama error rather than changing FastAPI code.


## 18. Applied fix — Round 9 / Ollama health semantics

### User runtime evidence

The uploaded debug log confirms that the backend runs inside WSL2 with:
- Python `/usr/bin/python`;
- Linux/WSL2 x86_64;
- LanceDB `0.39.0`;
- PyArrow `25.0.1`;
- `RAG_DEBUG=1`.

The log currently contains startup diagnostics but no request exception from the health check. fileciteturn122file0L5-L25

The user also reports that opening `127.0.0.1:11434` in the browser returns the Ollama running response.

### Confirmed source defect

The old `/api/health` implementation conflated two different states:

1. Ollama server reachability;
2. embedding-model availability.

The code first received HTTP 200 from Ollama and set `ollama_ok=True`, but then performed `/api/embed`. Any model error, missing model, or embedding timeout changed `ollama_ok=False`.

The frontend displayed only `health.ollama`, so a model-level failure appeared as **Ollama offline/KO**, even when the Ollama server itself was reachable.

### Corrected contract

The health API now exposes separate fields:

- `ollama`: Ollama server is reachable;
- `ollama_detail`: server status;
- `ollamaEmbedding`: embedding-model check result;
- `ollamaEmbeddingDetail`: exact embedding-model diagnostic.

The server health check remains a short 2-second HTTP reachability test.

The embedding check now has a 10-second timeout because model loading can legitimately take longer than a simple server-connectivity check.

### Corrected frontend flow

The Header now renders:

- `Online` when the Ollama server is reachable;
- `Online / Model Error` when the server is reachable but the configured embedding model failed;
- `Offline` only when the Ollama server itself is unreachable.

The tooltip distinguishes server availability from model availability.

### Diagnostic improvement

When the embedding check fails with an exception, `debug_exception()` records:
- route;
- phase;
- Ollama URL;
- exception type/message;
- traceback;
- runtime/environment snapshot.

This gives the next runtime test enough evidence to distinguish:
`server unavailable` vs `model unavailable` vs `model load timeout`.

### Current status

- Ollama WSL process startup: **USER-OBSERVED RUNNING**.
- Ollama HTTP server reachability from browser: **USER-OBSERVED OK**.
- Backend health semantics: **FIXED**.
- Embedding model availability: **OPEN / must be verified by `/api/health`**.
- Current API failure root causes: **OPEN**.
- Debug log mechanism: **FIXED AND SOURCE-VERIFIED**.
- Full E2E API flow: **OPEN**.

**NEXT EXACT TEST:** open `http://localhost:8000/api/health` and inspect `ollama`, `ollama_detail`, `ollamaEmbedding`, and `ollamaEmbeddingDetail`. Then reproduce one failing API request.

**STOP CONDITION:** do not classify an Ollama server outage from an embedding-model failure alone.


## 19. Applied fix — Round 10 / CrossEncoder runtime state

### User runtime finding

The only remaining header status shown as:

`CrossEncoder: Lazy Standby`

was hardcoded in the React header and did not reflect the actual runtime object.

### Reconstructed backend flow

`CrossEncoderReranker.__init__() → self._modello=None`

The CrossEncoder is intentionally lazy. The model is not loaded during application startup.

First real reranking:

`_carica_modello() → FlagReranker(...) → self._modello=<loaded model>`

Therefore the meaningful runtime states are:

- `standby`: object initialized, model not loaded yet;
- `ready`: model successfully loaded;
- `error`: a previous model-load attempt failed.

### Backend change

`CrossEncoderReranker.stato()` now exposes the runtime state without forcing model loading.

It returns:
- status;
- user-facing label;
- configured model name;
- loaded flag;
- last load error, when present.

A model-load failure is retained for diagnostics, then re-raised to the existing query fallback path.

### Health API change

`/api/health` now returns `crossEncoder` with the live state of the global reranker instance.

Health inspection does **not** instantiate/download the model merely to display its status.

### Frontend change

The Header no longer contains a hardcoded `Lazy Standby`.

It consumes `data.crossEncoder` from `/api/health` and displays:

- `Lazy Standby` before the first successful model load;
- `Ready` once the model has actually loaded;
- `Error` if model initialization failed;
- `Unavailable` only when the component itself could not be initialized.

The model name and load error are available through the tooltip.

### Stability rationale

This preserves the intended lazy-loading architecture. The header reports state; it does not cause a heavyweight model load.

It also avoids incorrectly presenting a model as ready merely because its Python wrapper object exists.

### Verification status

Source flow is now connected end-to-end:

`CrossEncoderReranker → /api/health → Header`

Actual `Ready` state requires one real query path with reranking enabled, because only that path loads the model.

**NEXT EXACT TEST:** after startup, `CrossEncoder` should initially show `Lazy Standby`. Execute one query with reranking enabled; after successful model loading, refresh/observe health and the header should change to `Ready`.

**STOP CONDITION:** do not eagerly load the CrossEncoder at startup just to change the label.


## 20. Function-Flow Deep Audit — Round 11 / Ingestion, whole-folder ingestion, job visibility and light GUI

**Scope:** audit-only. No source-code fix has been applied in this round.

Sources inspected:
- current `main` branch backend;
- current React frontend;
- current ingestion modules;
- supplied `frontend.zip` used **only as a visual/reference implementation** for the light GUI and ingestion UX;
- previous audit state.

The reference frontend is not treated as an authority for API contracts, constants, model names, storage paths, timeouts, or other runtime values. Its hardcoded values are excluded from the target implementation.

---

### 20.1 Executive status

The reported symptoms are consistent with multiple independent issues:

1. **The ingestion job is already executed in the background**, but its progress model is too coarse for long-running work.
2. The frontend displays a **synthetic animated bar** rather than a progress value derived from backend state.
3. The frontend stops monitoring after 30 minutes or after five consecutive polling failures, even though the backend job may still be running.
4. A batch/folder ingest rebuilds the full-text index **after every file**, creating a potentially very expensive repeated operation.
5. The job registry is process-memory-only. There is no persistent queue/job registry and no startup recovery.
6. The current document API exposes indexed documents reconstructed from LanceDB rows and assigns them the status `Indicizzato`; it does not represent queued/processing/ready/failed ingestion state.
7. Whole-folder upload is implemented at source level, but its browser → multipart → backend → background-job path has **not been proven end-to-end in the current runtime**. The user's observation that folder ingestion does not start is therefore an open runtime finding, not a source-level closed issue.
8. The light theme architecture is incomplete because most React components use Tailwind arbitrary hexadecimal color utilities directly. The current `theme-light` CSS overrides only a subset of generic semantic class names and therefore cannot consistently recolor those arbitrary utilities.

---

## 20.2 Severity summary

| Severity | Finding | Classification |
|---|---|---|
| P0 candidate | Whole-folder ingestion can become impractically slow because full-text index creation is executed after every file in the batch | Confirmed source-level performance defect; runtime impact not yet measured |
| P1 | Long file ingestion reports no meaningful progress until the whole file finishes embedding/indexing | Confirmed source |
| P1 | Progress bar is animated but not data-driven; it does not represent actual completion | Confirmed source |
| P1 | Frontend gives up after 30 minutes or five polling errors while the backend job may continue | Confirmed source |
| P1 | Ingestion state exists only in process memory; restart/reload loses job visibility/recovery | Confirmed source |
| P1 | No persistent queue / global job list / "ready for use" surface exists | Confirmed source |
| P1 | Multiple ingestion jobs can be scheduled without an explicit concurrency governor | Confirmed source |
| P1 | Whole-folder upload path exists but browser/runtime E2E failure is still unresolved | User-observed runtime issue; root cause open |
| P2 | Unsupported files inside a folder are silently skipped before job creation result is explained clearly to the user | Confirmed source/UX |
| P2 | Document status model contains states such as `In Elaborazione` and `In Coda`, but current backend document reconstruction reports `Indicizzato` for stored documents | Confirmed source contract gap |
| P1/P2 | Light theme uses many hardcoded hexadecimal utilities across major components, bypassing current theme tokens | Confirmed source |
| P2 | Supplied reference GUI contains hardcoded values and mock data; those must remain reference-only | Design constraint |

---

## 20.3 Ingestion entry point — complete flow

### Frontend entry point

`IngestModal.handleStartIngest()`

Flow:

`fileObjects → FormData → POST /api/ingest → jobId → polling /api/ingest/status/{jobId}`

The frontend always creates a single multipart request containing all selected files.

The request also sends:
- `chunkSize`;
- `chunkOverlap`;
- `ocrEnabled`;
- `relativePaths`.

### Backend entry point

`process_ingest()`

Flow:

`UploadFile[] → payload validation → active DB capture → source directory creation → file persistence → background task scheduling → jobId response`

Important state capture:

`captured_db_id = db_manager.active_id`

This is correct with respect to database-switch races: the job is tied to the database active at submission time.

### Background execution

The request does **not** perform the heavy parsing/embedding synchronously.

It schedules:

`asyncio.to_thread(esegui_ingestion_batch_job, ... captured_db_id)`

Therefore the reported "background" proposal is partly already implemented at execution level.

The missing part is **durable job management and user-facing job observability**, not simply moving the current function to a background thread.

---

## 20.4 Progress-flow defect

Current backend job fields include:
- `filesTotal`;
- `filesProcessed`;
- `filesFailed`;
- `chunksCreated`;
- `currentFile`;
- `startedAt`;
- `updatedAt`;
- `errors`.

However, the state transition is too coarse.

For each file:

`parse file → generate chunks → embed chunks in batches → write chunks → increment filesProcessed`

`filesProcessed` is incremented only after the complete file has finished.

For a single very large PDF:

`0 / 1 file`

can therefore remain visible for a long time even while:
- Docling is actively parsing;
- embeddings are being generated;
- chunks are being written to LanceDB.

The backend already increments `chunksCreated` after embedding/upsert batches, but the frontend ignores this signal.

### UX consequence

A legitimate active job looks indistinguishable from a stalled job.

This directly explains the user observation that ingestion "seems to last forever" and that it is impossible to tell whether it is blocked.

---

## 20.5 Frontend progress bar is not real progress

Current `IngestModal.tsx` renders:

`w-2/3 + animate-pulse`

instead of computing width from job state.

Therefore:

- it is not a percentage;
- it does not represent chunks processed;
- it does not represent files processed;
- it does not represent current stage;
- it cannot distinguish parsing, embedding, indexing or FTS rebuild.

The text `processed/total file` is more trustworthy than the bar, but remains coarse for large files.

### Required future contract

The backend should eventually expose explicit stage/state information, for example conceptually:

`queued → reading → parsing → chunking → embedding → indexing → finalizing → ready`

The exact enum and data model must be designed from the actual pipeline, not copied from the reference frontend.

---

## 20.6 False-failure conditions in the frontend

### 30-minute client cutoff

Current frontend stops polling after:

`30 * 60 * 1000 ms`

and reports that ingestion is taking too long.

The backend job itself is **not cancelled**.

Therefore the user receives a frontend error state while the backend may continue processing.

This creates an inconsistent state:

`UI = failed/stopped monitoring`

while:

`backend job = still running`

### Five polling errors

After five consecutive polling failures, the frontend also stops monitoring and reports an error.

Again, the backend job is not cancelled.

This is another false-negative path.

### Function-flow conclusion

The frontend currently treats **loss of observability** as **failure of ingestion**.

These are not equivalent states and must be separated in the future job model.

---

## 20.7 Whole-folder flow

### Source support confirmed

The frontend provides:
- multi-file selection;
- a separate folder input using browser directory-selection attributes;
- extraction of `webkitRelativePath`;
- `relativePaths` JSON sent to the backend.

The backend:
- accepts multiple `UploadFile` objects;
- validates file count and payload size;
- accepts `relativePaths`;
- sanitizes path components;
- reconstructs the relative source tree under the database `sources` directory;
- schedules a batch ingestion job.

Therefore **whole-folder capability exists in source code**.

### Why the user's "folder doesn't start" remains OPEN

No browser/runtime trace was provided for this specific action in this audit.

The following branches can terminate before actual ingestion:

1. browser produces no files;
2. folder contains no supported PDF/JSON files;
3. file count exceeds the backend limit;
4. total payload exceeds the backend limit;
5. a malformed `relativePaths` payload is rejected;
6. upload persistence fails;
7. background database preparation fails;
8. first file parsing fails.

The frontend does not expose these branches distinctly enough.

A future E2E test must therefore inspect:
`browser selection → multipart request → HTTP response → jobId → status polling → first file → first chunk → first DB write`.

---

## 20.8 Confirmed folder-ingest performance defect: FTS rebuild per file

In `esegui_ingestion_batch_job()`, after each file iteration the backend calls:

`crea_indice_fulltext(tabella)`

This happens **inside the file loop**.

Therefore for `N` files:

`N × full-text-index rebuild`

instead of a single final rebuild (or another explicitly incremental strategy).

This is particularly important for whole-folder ingestion because the number of files can be large.

### Expected failure symptom

The user can observe:
- first files processing;
- progressively longer pauses;
- apparent infinite ingestion;
- high CPU/disk activity;
- API responsiveness degradation if the index operation is expensive.

This is the strongest source-level explanation currently found for why folder ingestion can become dramatically slower than expected.

**No code change is applied in this round.**

---

## 20.9 Ingestion concurrency and resource management

`_ingestion_tasks` is a set used to retain asyncio tasks, but there is no explicit semaphore or worker queue enforcing `workerConcurrency`.

The application therefore has no clear runtime contract connecting the user-facing `workerConcurrency` setting with ingestion parallelism.

Multiple jobs can be scheduled.

Potential consequences:
- multiple Docling/torch workloads competing for CPU/RAM;
- simultaneous embedding calls to Ollama;
- multiple LanceDB writes;
- memory pressure;
- reduced API responsiveness;
- unpredictable progress behavior.

This is a design-level issue independent of the single-job progress defect.

---

## 20.10 Job durability / "files ready" proposal analysis

The user's proposal is structurally sound, but the current implementation is not durable enough to support it.

Current job state:

`ingestion_jobs: Dict[str, Dict[str, Any]]`

This is in-memory process state.

Consequences:
- restart loses job list;
- `--reload` can interrupt running background work;
- browser refresh loses the direct job context;
- there is no global list of active/completed jobs;
- there is no persisted "ready" state;
- there is no reliable restart/resume checkpoint.

### Required future architecture

A stable implementation should separate:

**Job state**
`queued / running / completed / completed_with_errors / failed / cancelled`

from:

**Document state**
`queued / processing / ready / failed`

from:

**Pipeline stage**
`upload / parse / chunk / embed / index / finalize`

and expose an authoritative job list to the frontend.

The "ready for use" menu should be based on backend persistence, not local React state.

---

## 20.11 Document status contract gap

`KnowledgeDocument.status` already defines:
- `Indicizzato`;
- `In Elaborazione`;
- `In Coda`;
- `Verificato`.

But `_get_documents_for_db()` currently reconstructs stored documents and assigns:

`status = "Indicizzato"`

This means the type system anticipates richer lifecycle state while the backend currently has no corresponding persistent lifecycle model.

The future implementation should not synthesize these statuses in React. The backend/database layer should become authoritative.

---

## 20.12 Supplied light-GUI reference — allowed use

The attached `frontend.zip` is useful as **visual reference only**.

The following aspects are reasonable design references for a future implementation:
- clearer light/dark surface hierarchy;
- card-based grouping;
- stronger separation between primary action and secondary actions;
- clearer ingestion progress block;
- more readable text hierarchy;
- explicit folder-selection affordance;
- structured runtime notifications.

The following must **not** be copied as runtime truth:
- hardcoded model names;
- hardcoded URLs;
- hardcoded storage paths;
- fixed limits;
- mock data;
- default values that should come from backend configuration.

---

## 20.13 Light theme audit

The current frontend has a token layer in `index.css`:

`--bg-surface`, `--bg-surface-low`, `--text-on-surface`, etc.

However, the actual components predominantly use arbitrary hexadecimal Tailwind utilities directly.

Static scan of the current main components found numerous hexadecimal literals in all major views, including:
- `SettingsView.tsx`;
- `PipelineTelemetryView.tsx`;
- `VectorExplorerView.tsx`;
- `DatabaseManagerModal.tsx`;
- `ChunkModal.tsx`;
- `Header.tsx`;
- `Sidebar.tsx`;
- `KnowledgeNodesView.tsx`;
- `QueryWorkbenchView.tsx`;
- `IngestModal.tsx`.

Therefore the CSS selectors such as:

`html.theme-light .bg-surface-container-low`

cannot reliably recolor elements that are actually rendered with values such as:

`bg-[#171b26]`

because those are separate generated utilities.

### Consequence

The light theme currently changes some global elements but leaves many cards, borders, text and action surfaces visually tied to the dark palette.

This is a structural theming issue, not merely a choice of nicer colors.

### Required future direction

The codebase should converge on semantic theme tokens/classes for:
- surfaces;
- surface elevations;
- text primary/secondary/muted;
- borders;
- primary action;
- danger/error;
- status indicators;
- overlays.

The actual token values should live in one theme system. The reference GUI can inform hierarchy but not supply the literal values.

---

## 20.14 Additional frontend hygiene findings

### IngestModal imports/constants

Current `IngestModal.tsx` contains unused imports/constants such as:
- `apiJson`;
- `apiUrl`;
- `getApiToken`;
- `setApiToken`;
- `API_BASE_URL`.

These do not cause ingestion failure but indicate stale code paths and increase audit surface.

### App-level API_BASE_URL

`App.tsx` defines `API_BASE_URL` but current calls use `apiFetch()`. This is another disconnected constant.

### Settings/theme persistence

The quick theme toggle updates React/local state, while persistent configuration ownership remains partly in the settings flow. This should be unified in a later cleanup to avoid divergent theme state.

---

## 20.15 Branch map

### Normal single-file ingest

`select file → POST /api/ingest → save source → create job → background parse → chunk → embed → upsert → FTS → completed`

### Long single-file ingest

`select file → job created → parse/embedding runs → filesProcessed remains 0 → frontend shows synthetic animated bar → user cannot distinguish active work from stall`

### Folder ingest

`select folder → File[] + relativePaths → POST /api/ingest → save files → batch job → file 1 → embed/upsert → FTS rebuild → file 2 → embed/upsert → FTS rebuild → ... → completed`

This branch is the main performance concern.

### Frontend monitoring timeout

`job running → 30 minutes reached → UI stops polling → UI reports timeout → backend job may continue`

### Frontend transient polling loss

`job running → 5 polling failures → UI reports failure → backend job may continue`

### Process restart/reload

`job running → process reload/restart → in-memory ingestion_jobs lost → browser cannot recover authoritative state`

---

## 20.16 Dead/disconnected or misleading state

- Fake progress bar: **DISCONNECTED FROM REAL PROGRESS**.
- `KnowledgeDocument.status` richer than backend lifecycle: **PARTIALLY DISCONNECTED**.
- `workerConcurrency` setting vs actual ingestion scheduling: **NOT PROVEN CONNECTED**.
- Folder-selection UI vs E2E runtime behavior: **OPEN**.
- Theme tokens vs actual component color utilities: **PARTIALLY DISCONNECTED**.
- Reference frontend mock/default values: **REFERENCE ONLY, NOT TARGET STATE**.

---

## 20.17 Required future test matrix

No implementation change is requested in this round. Before fixing, the audit should reproduce:

| Test | Required evidence |
|---|---|
| Single small PDF | jobId, every status transition, final chunk count |
| Single large PDF | status/stage changes before first file completes |
| Multi-file selection | per-file progress and failures |
| Whole folder | multipart file count + relativePaths + job state |
| Folder with unsupported files | clear supported/skipped counts |
| >500 files | HTTP response and user-visible reason |
| >2 GB payload | HTTP response and user-visible reason |
| Long-running >30 min job | verify UI does not falsely mark backend job failed |
| 5 transient status failures | verify observability loss is distinct from job failure |
| Backend reload during job | determine desired recovery semantics |
| Two simultaneous ingests | CPU/RAM/API responsiveness and concurrency behavior |
| Light theme | every major surface must switch from dark tokens to light tokens |
| Browser refresh during ingest | job must remain discoverable from authoritative backend state |

---

## 20.18 Audit conclusion

The ingestion problem is **not one bug**.

The strongest confirmed source-level problem is the batch-folder path rebuilding the full-text index after every file. The strongest UX problem is that the frontend has no trustworthy progress representation for long-running stages and can report failure merely because monitoring stopped.

The user's idea of moving long ingestion into a background workflow and exposing a persistent "files ready" area is compatible with the current architecture, but it should be implemented as a **durable ingestion/job state model**, not as another polling timer around the existing in-memory dictionary.

The light GUI should be redesigned around semantic theme tokens. The supplied reference can guide hierarchy and visual treatment, but its hardcoded values and mock/runtime data must not enter the application.

**Current audit status: OPEN — ingestion lifecycle, folder ingestion runtime behavior, persistent job visibility, and light-theme architecture.**

**No source-code fixes applied in Round 11.**

**NEXT EXACT ROOT-CAUSE TARGET:** reproduce one folder ingest while observing the network request and `/api/ingest/status/{jobId}`, then correlate that runtime trace with the per-file FTS rebuild path.

**STOP CONDITION:** do not start GUI polishing or background-job refactoring by guessing at the folder failure. First capture the folder request/job transition and establish whether the observed failure is upload validation, job creation, first-file processing, embedding, or FTS finalization.


## 21. Applied fixes — Round 12

- Batch ingestion now rebuilds the FTS index once at the end instead of once per file.
- Ingestion jobs now expose `stage`, `progressPercent`, `chunksTotal` and `filesSkipped`.
- Large single-file jobs can report embedding progress before the file completes.
- Ingestion monitoring no longer treats 30 minutes or five transient polling errors as ingestion failure.
- Ingestion jobs are persisted locally and exposed through `GET /api/ingest/jobs`; interrupted jobs are marked explicitly after backend restart.
- `workerConcurrency` is connected to a process-level ingestion semaphore; runtime reload recreates the semaphore from current settings.
- Re-index jobs use the same concurrency/lifecycle flow.
- Unsupported folder files are reported instead of being silently ignored.
- Knowledge Nodes now displays recent persistent ingestion jobs and their backend progress.
- Retrieval fallback now rebuilds FTS only for errors whose message indicates an FTS/index failure.
- Frontend ingestion code removed stale API imports/constants.
- Light theme now maps the legacy arbitrary dark palette utilities onto the semantic light-theme tokens.
