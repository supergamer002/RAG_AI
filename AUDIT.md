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
