# AUDIT.md — Function-Flow Deep Audit

## 0. Audit scope

Audit eseguito con metodologia **Function-Flow Deep Code Audit**: il codice viene ricostruito come grafo di esecuzione partendo dagli entry point, seguendo funzioni chiamate, rami di successo/fallimento/eccezione, side effect, stato e terminal outcomes.

Baseline: branch `main` del repository `supergamer002/RAG_AI`, integrata con i fix già effettuati nel ciclo locale di audit e con le evidenze runtime riferite dall'utente durante il test umano del 28/09/2026.

Il criterio operativo è:

`Caller → Function → Inputs → Preconditions → Internal steps → Called functions → State changes → Output → Exit branches`

Ogni ramo importante deve avere un'uscita determinata; i problemi vengono separati in **confermati**, **probabili/da verificare runtime** e **design weakness**.

---

# 1. Executive severity summary

| Severity | Finding | Status |
|---|---|---|
| P0 | Backend potenzialmente non avviabile per PyArrow/DLL bloccata da Windows App Control | **Runtime reported / da verificare** |
| P0 | Tutte le chiamate frontend osservate terminano con `Failed to fetch` | **Confermato come sintomo runtime** |
| P0 | Prima verifica necessaria: `/api/health` deve essere raggiungibile prima di testare i servizi secondari | **Coda immediata** |
| P1 | Pannello notifiche non ha un handler di apertura | **Confermato dal codice** |
| P1 | Widget profilo in alto a destra contiene identità/cluster hardcoded e non ha azione click | **Confermato dal codice** |
| P1 | `mockData.ts` è nuovamente presente nella baseline GitHub | **Confermato dal repository** |
| P1 | Telemetry SSE termina con `error` nel test umano | **Runtime reported / da verificare con backend vivo** |
| P1 | Evaluations restituisce `Failed to fetch` nel test umano | **Runtime reported / da verificare con backend vivo** |
| P1 | Gestione frontend degli errori di rete troppo generica (`Failed to fetch`) | **Design weakness / da verificare nei componenti API** |
| P1 | Benchmark deve operare sul database catturato all'avvio, non sul DB attivo mutato successivamente | **Fix già in coda/applicato nel ciclo locale; verifica GitHub da mantenere** |
| P1 | Health deve usare modello embedding e dimensione del DB attivo | **Fix già in coda/applicato nel ciclo locale; verifica GitHub da mantenere** |
| P1 | Export/import deve preservare e validare metadata embedding | **Fix già in coda; runtime da verificare** |
| P2 | Full pytest non verificabile nell'ambiente precedente per assenza di `lancedb`/`pyarrow` e rete indisponibile | **Bloccato** |
| P2 | Build TypeScript/Vite non verificata nell'ambiente precedente per assenza di `node_modules` | **Bloccato** |
| P2 | Benchmark con casi statici dipende dalla presenza dei documenti fixture | **Design limitation** |

---

# 2. Entry-point map

## Backend

### Processo FastAPI
`webapp/backend/main.py`

Entry point applicativo:

`python webapp/backend/main.py`
→ `uvicorn.run("webapp.backend.main:app", host="0.0.0.0", port=8000, reload=True)`
→ import del modulo
→ costruzione di configurazione, database manager, servizi e route
→ server HTTP.

**Critical precondition:** gli import Python/LanceDB/PyArrow devono completarsi.

Un errore DLL durante l'import può terminare il processo prima che qualsiasi route sia raggiungibile.

### Health
`GET /api/health`

Percorso concettuale:

`HTTP request → auth/rate middleware → health handler → DB active table → vector schema → Ollama embedding check → response`

Terminal states:
- backend raggiungibile + controlli riusciti → JSON health;
- backend raggiungibile + dipendenza non disponibile → JSON/errore controllato;
- eccezione interna → errore HTTP;
- processo non avviato → frontend `Failed to fetch`.

### Query
`POST /api/query`

`request → validation → active DB/table → embedding model del target DB → dense/BM25/hybrid retrieval → reranking/generation → response`

### Ingestion
`POST /api/ingest`

`multipart upload → payload validation → file validation → persist upload → create job → asyncio task → thread worker → extraction → chunking → embedding → LanceDB upsert → FTS → terminal job state`

Terminal states:
- invalid payload/file → HTTP validation error;
- zero processed/chunks → failed job;
- partial errors → job records errors;
- successful chunks → completed job;
- unexpected worker exception → failed job.

### Evaluations
`POST /api/eval/run`

`request → capture active DB id → background worker → retrieve/evaluate cases against captured DB → metrics → eval job terminal state`

Il DB deve restare quello catturato anche se l'utente cambia DB mentre il benchmark è in esecuzione.

### Telemetry
`GET /api/telemetry`

`HTTP → telemetry state → JSON`

`GET /api/telemetry/stream`

`HTTP → SSE stream → event publication → browser EventSource → telemetry console`

Terminal states:
- stream attivo;
- client disconnesso;
- server/stream error.

---

# 3. Frontend entry-point map

### Application shell
`webapp/frontend/src`

Flusso:

`React app → layout/navigation → Header + views → api service → FastAPI`

### Header
Responsabilità:
- health polling;
- navigazione;
- database manager;
- ingest;
- terminale telemetry;
- notifiche;
- profilo.

Il polling health usa:

`Header → apiFetch("/api/health") → state health → status indicators`

Se la fetch fallisce:

`catch → fastapi=false, lancedb=false, ollama=false`

Questo è un terminal state UI coerente, ma non comunica la causa.

### Notification control

Il controllo notifiche presente in `Header.tsx` è un `div` con icona e titolo, senza callback `onClick`.

Flow reale:

`user click → DOM div → nessun handler → nessun state change → nessun panel`

**Terminal state:** nessuna azione.

È quindi un bug frontend confermato, indipendente dalla connettività backend.

### Profile widget

Flow reale:

`render → static image → hover → static tooltip`

Il tooltip contiene:
- `Dev & Telemetry Ops`
- `supergamerfailer002`
- `Cluster: europe-west2`

Non risultano derivati da una risposta backend.

**Terminal state:** hover-only presentation; click non produce un'azione applicativa.

---

# 4. Function/dependency map

## Ingestion

`/api/ingest`
→ file validation
→ storage
→ job creation
→ `esegui_ingestion_job`
→ extraction
→ `chunk_documento`
→ embedding
→ `_indicizza_chunks_incrementale`
→ `store.upsert_chunks`
→ FTS/index maintenance
→ job status.

### Chunker

`chunk_documento`
→ `chunk_sezione`
→ `_split_frasi`
→ chunk emission.

Fix già effettuato:
- garantisce avanzamento di `i`;
- evita che una frase molto lunga venga reinserita indefinitamente nell'overlap;
- mantiene tabelle come blocchi separati.

### Store

`upsert_chunks`
→ length validation
→ schema vector dimension check
→ record creation
→ LanceDB `merge_insert`.

Fix già effettuato:
- mismatch di dimensione embedding rilevato prima del commit;
- errore esplicito invece di errore LanceDB poco leggibile.

## Query

`execute_query`
→ `_esegui_query_su_tabella`
→ target DB info
→ embedding
→ retrieval
→ reranking
→ generation.

Fix già effettuato:
- il modello embedding viene scelto in base al database target/catturato, non implicitamente dal database globale.

## Evaluation

`run_evaluations`
→ cattura `databaseId`
→ worker asincrono/thread
→ casi benchmark
→ query sul database catturato
→ answer embedding sul database catturato
→ metriche
→ terminal state.

Fix già effettuato/localmente in coda:
- eliminare qualsiasi uso del DB attivo mutabile dopo la cattura del job.

---

# 5. Branch map

## Startup

```text
START
├─ import dependencies OK
│  └─ create app/services → server starts → HTTP available
└─ import dependency fails
   ├─ DLL/PyArrow blocked → process exits
   └─ frontend remains visible → fetch calls fail
```

## Health

```text
/api/health
├─ backend unreachable → browser Failed to fetch
└─ backend reachable
   ├─ DB OK
   │  ├─ Ollama OK → healthy response
   │  └─ Ollama fail → degraded response/error
   └─ DB fail → degraded/error response
```

## Ingestion

```text
/api/ingest
├─ invalid payload → 4xx → exit
├─ valid upload
│  ├─ file rejected → validation result
│  └─ accepted
│     ├─ extraction fail → job error
│     ├─ zero chunks → failed terminal state
│     ├─ embedding fail → failed/partial state
│     ├─ vector dimension mismatch → explicit error
│     └─ successful upsert → FTS → completed
└─ unexpected exception → failed terminal state
```

## Chunker

```text
chunk_sezione
├─ empty text → return
├─ normal sentence sequence → accumulate
├─ target exceeded → emit chunk → overlap → continue
├─ very long sentence → emit directly → increment i → continue
└─ end → emit residual chunk → return
```

The long-sentence branch was previously capable of non-progress/infinite looping; the explicit progress guard fixes that.

## Query

```text
/api/query
├─ invalid request → validation error
├─ empty DB → empty/controlled response
└─ populated DB
   ├─ embedding fail → error
   ├─ dense/BM25 retrieval fail → error
   ├─ reranker unavailable/fail → fallback/error according to service
   └─ generation → answer + sources
```

## Telemetry SSE

```text
EventSource
├─ endpoint reachable → stream open → events → console
├─ endpoint unavailable → SSE error
└─ connection closes → browser reconnect/error lifecycle
```

Runtime evidence currently reports the second branch.

## Notification

```text
notification icon
└─ click → NO HANDLER → NO STATE CHANGE → NO PANEL
```

This branch currently has no functional terminal success path.

---

# 6. Dead/unreachable or disconnected code

## Confirmed / high confidence

### Notification UI
The visible notification control is not connected to a handler. It is therefore a disconnected UI element rather than a complete feature.

### Profile tooltip
The profile widget is presentation-only. No functional click path exists.

### `mockData.ts`
The repository currently contains `webapp/frontend/src/data/mockData.ts` with:
- sample settings;
- sample documents;
- sample chunks;
- synthetic telemetry/evaluation-oriented data.

This file must be traced to every importer before deletion. Its presence alone does not prove all consumers are active, but it violates the previous "remove demo/hardcoded data" objective and requires a fresh dependency scan.

---

# 7. Data/state flow

## Configuration

`config.json`
→ `caricaconfig()`
→ backend global config
→ settings validation/update
→ routes/services.

Default upload payload:
`maxPayloadMB = 2048`

Hard upload constraints remain:
- max 500 files;
- max 250 MB/file;
- max 2 GB total.

A lower reverse-proxy/server limit can still produce a 413 before application-level validation.

## Database identity

`databaseId`
→ captured at job start
→ ingestion/evaluation/query helper
→ DB manager lookup
→ table/model selection.

Important invariant:
**a background job must not silently switch to whichever DB becomes active later.**

## Embedding compatibility

`database embeddingModel`
+
`database vector dimension`
→ embedding selection
→ vector generation
→ store schema validation
→ LanceDB.

A mismatch must terminate before writing incompatible vectors.

## Telemetry

`backend telemetry state`
→ REST/SSE
→ EventSource
→ telemetry UI.

Current runtime test indicates the UI receives no usable SSE stream.

---

# 8. Confirmed bugs

## BUG-001 — Notification panel has no functional opening path

**Severity:** P1

**Location:** `webapp/frontend/src/components/Header.tsx`

**Observed behavior:** clicking the notification icon does nothing.

**Expected behavior:** click should update UI state and render/open the notification panel, or the icon should not be presented as an interactive feature.

**Root cause:** the icon is rendered as a `div`; no `onClick`, state transition or panel connection exists.

**Impact:** visible UI feature is non-functional.

**Recommended fix:** connect it to an actual notification state/panel or remove the affordance until implemented.

**Verification:** click icon; verify state transition, panel render, close path, empty state and notification data source.

---

## BUG-002 — Top-right profile widget is hardcoded

**Severity:** P1

**Location:** `webapp/frontend/src/components/Header.tsx`

**Observed behavior:** tooltip shows static identity/cluster data and avatar; clicking does nothing.

**Expected behavior:** either real runtime/user data and an actual action, or a neutral non-interactive status indicator.

**Root cause:** static JSX values and static image path.

**Impact:** misleading application state and reintroduced hardcoded/demo presentation.

**Recommended fix:** remove synthetic identity/cluster claims; replace with actual backend/runtime state or remove the widget action entirely.

**Verification:** source scan for the hardcoded values and click/keyboard interaction test.

---

## BUG-003 — Demo/mock data file reintroduced

**Severity:** P1

**Location:** `webapp/frontend/src/data/mockData.ts`

**Observed behavior:** synthetic documents/settings/chunks are present in the repository.

**Expected behavior:** production UI must obtain application data from real API/state sources.

**Root cause:** demo dataset remains in source tree.

**Impact:** risk of stale UI, false data, hidden fallback behavior and divergence between UI and backend.

**Recommended fix:** trace all imports; remove unused consumers; delete file if no legitimate test-only use remains.

**Verification:** repository-wide import search + runtime startup with empty DB.

---

# 9. Probable bugs / runtime verification required

## BUG-PROB-001 — PyArrow DLL blocks backend startup

**Severity:** P0

**Observed:** Windows reports a PyArrow installation/DLL problem, including lack of `dataset` support and DLL origin blocked by an application-control policy.

**Expected:** Python process imports PyArrow/LanceDB successfully.

**Root cause:** not yet proven. Candidate causes:
- blocked native DLL;
- incompatible PyArrow wheel;
- partial/corrupt installation;
- Windows application-control policy;
- architecture/runtime mismatch.

**Impact:** potentially prevents FastAPI from importing and makes every frontend fetch fail.

**Verification:** run backend directly from terminal and capture the first Python traceback; run:
`python -c "import pyarrow; import pyarrow.dataset; print(pyarrow.__version__)"`
and separately import `lancedb`.

---

## BUG-PROB-002 — Backend unreachable causes cascading frontend failures

**Severity:** P0

**Observed:** telemetry, evaluations and connection test all show `Failed to fetch`.

**Expected:** frontend distinguishes unreachable backend from HTTP/application errors.

**Root cause:** backend availability has not yet been proven during the human test.

**Impact:** prevents meaningful downstream feature testing.

**Verification:** first test `GET http://localhost:8000/api/health` directly; then inspect browser Network status codes.

---

## BUG-PROB-003 — Telemetry SSE failure

**Severity:** P1

**Observed:** telemetry/log console reports SSE `error`, zero logs and zero latency.

**Expected:** stream connects and publishes telemetry events.

**Verification:** test endpoint directly with a real FastAPI process; inspect HTTP status, headers and first SSE event; then inspect EventSource lifecycle in browser.

---

## BUG-PROB-004 — Evaluation fetch failure

**Severity:** P1

**Observed:** evaluation view reports `Failed to fetch`.

**Expected:** GET/run evaluation endpoints are reachable and report structured backend errors.

**Verification:** call evaluation endpoint directly and inspect status/body before debugging React rendering.

---

# 10. Fixes already completed / in queue

## Completed in the preceding local audit cycle

### Chunker progress guarantee
Fixed the long-sentence/overlap non-progress path.

Regression tests:
- long sentence terminates;
- normal overlap preserves progress.

Previously verified targeted result: **10 tests passed**.

### Vector dimension validation
`rag/index/store.py` validates incoming embedding dimension against the LanceDB table schema before commit.

### Target-DB embedding model
Query/ingestion/evaluation paths were changed so the embedding model follows the target/captured database.

### Upload payload default
Application default `maxPayloadMB` raised to 2048 MB while retaining hard per-file and total limits.

### Mock data cleanup
A previous local cycle removed unused `mockData.ts`; the current GitHub baseline has reintroduced it and therefore requires a new import/dependency audit.

---

## Fixes already queued from the current audit

### QUEUED-001 — Benchmark DB capture hardening
Ensure every evaluation worker uses `captured_db_id` for:
- document existence;
- query table;
- embedding model;
- answer embedding;
- final result metadata.

No lookup may fall back to mutable `active_id`.

### QUEUED-002 — Health endpoint DB-aware diagnostics
Health must report:
- FastAPI availability;
- active DB availability;
- actual vector dimension;
- embedding model associated with active DB;
- Ollama availability/model compatibility.

The result should distinguish degraded dependencies rather than collapsing everything into a generic failure.

### QUEUED-003 — Export/import embedding metadata
Export must preserve embedding model + vector dimension.

Import must:
- restore metadata when present;
- validate actual table vector dimension;
- mark old/imported unknown metadata explicitly;
- avoid silently assuming compatibility.

### QUEUED-004 — Network error diagnostics
Frontend fetch failures should distinguish:
- backend unreachable;
- timeout;
- HTTP 401/403;
- HTTP 4xx validation;
- HTTP 5xx;
- malformed response.

The user-facing message must include the endpoint/operation where useful.

### QUEUED-005 — Notification functionality
Implement the actual notification state/data flow or remove the non-functional affordance.

### QUEUED-006 — Remove hardcoded profile/demo identity
Remove:
- synthetic username;
- synthetic cluster;
- unexplained avatar;
- dead click affordance.

### QUEUED-007 — Re-audit `mockData.ts`
Trace every import first. If it is not test-only, remove the source and replace consumers with API-backed state.

### QUEUED-008 — Runtime startup diagnostic
The startup path should expose a clear actionable error when a native dependency such as PyArrow cannot load. Do not mask the root exception with a generic frontend `Failed to fetch`.

---

# 11. Design / architecture improvements

1. **Health must be a diagnostic endpoint, not just a boolean ping.**
   It should expose dependency-level state and useful failure detail.

2. **Background jobs must capture immutable execution context.**
   Database id, embedding model, table identity and relevant configuration should be captured once and passed explicitly.

3. **Frontend API layer should normalize errors.**
   Components should not each invent their own interpretation of `fetch` failures.

4. **No production UI should contain synthetic operational identity.**
   Runtime telemetry must come from runtime state.

5. **Demo data should live only in explicit test fixtures.**
   It should never silently populate the production application.

6. **SSE should have explicit lifecycle state.**
   `connecting → open → event → reconnecting → terminal failure` should be visible to the UI.

7. **Native dependency checks belong in startup diagnostics.**
   PyArrow/LanceDB failures should be surfaced before the browser is asked to diagnose them.

---

# 12. Tests required / currently blocked

## Required next runtime test sequence

### A. Python dependency test
1. Start backend from terminal.
2. Capture first traceback.
3. Import `pyarrow`.
4. Import `pyarrow.dataset`.
5. Import `lancedb`.
6. Start FastAPI.

### B. HTTP baseline
1. `GET /api/health`
2. `GET /api/auth/status`
3. `GET /api/settings`
4. `GET /api/telemetry`
5. Open `/api/telemetry/stream`.

### C. Frontend
1. Verify health indicators.
2. Verify connection test.
3. Verify telemetry.
4. Verify evaluations.
5. Verify notification click.
6. Verify top-right widget.
7. Verify database manager.
8. Verify ingest.

### D. RAG functional path
1. Ingest one small PDF.
2. Verify job status reaches terminal state.
3. Verify chunks exist in LanceDB.
4. Run sparse/dense/hybrid query.
5. Verify source attribution.
6. Run evaluation against the actual DB.

### E. Full test suite
Previously blocked because the audit environment lacked `lancedb`/`pyarrow` and network access prevented installation.

### F. Frontend build
Previously blocked because the audit environment lacked installed `node_modules` / TypeScript tooling.

---

# 13. Exact audit stopping point

The audit is **not closed**.

Last confirmed source-level state:
- chunker progress fix exists;
- vector dimension validation exists;
- target-database embedding selection exists;
- upload default is 2048 MB;
- benchmark/database capture hardening is in the fix queue;
- health DB-aware diagnostics are in the fix queue;
- export/import embedding metadata validation is in the fix queue;
- current GitHub baseline contains a non-functional notification control;
- current GitHub baseline contains hardcoded profile/cluster/avatar presentation;
- current GitHub baseline contains `mockData.ts`;
- runtime human test reports PyArrow/DLL failure and cascading `Failed to fetch` symptoms;
- SSE runtime state is reported as error;
- full dependency-complete runtime verification remains pending.

### Next function/branch to analyze

**First:** process startup/import path around `webapp.backend.main` → `rag.index.store` → PyArrow/LanceDB.

**Then:** `GET /api/health` complete branch tree.

**Then:** frontend `apiFetch`/error normalization and telemetry EventSource lifecycle.

Only after those paths are operational should query, ingestion, evaluation and secondary UI tests continue.

---

# 14. Audit memory checkpoint

```text
LAST ENTRY POINT:
FastAPI process startup + frontend Header health polling

LAST FUNCTION:
Header.checkHealth → GET /api/health
Backend import chain must be verified before route execution.

COMPLETED BRANCHES:
- chunk_sezione long-sentence progress branch
- vector dimension validation
- target DB embedding selection
- upload validation limits
- benchmark DB capture design
- notification/profile source inspection

PENDING BRANCHES:
- PyArrow native DLL startup failure
- /api/health runtime branches
- telemetry SSE open/error/reconnect
- evaluation endpoint runtime
- notification implementation
- profile widget replacement
- mockData dependency tree
- full RAG runtime path
- full pytest
- frontend build

IMPORTANT RELATIONSHIPS:
Header → apiFetch → /api/health
Header → onOpenTerminal → telemetry UI
Header notification → NO HANDLER
Header profile → static tooltip/image
/api/eval/run → captured database context
/api/query → target database embedding context
ingestion → chunker → embedding → LanceDB upsert

DISCOVERED BUGS:
P0/P1 items documented above.

QUESTIONS STILL OPEN:
- Is the PyArrow DLL failure caused by installation corruption, Windows App Control, wheel/runtime mismatch, or another native dependency?
- Does FastAPI actually reach /api/health on the user's machine?
- Is SSE failing because backend is down or because stream implementation has a separate defect?
- Which modules still import mockData.ts?
- Are queued benchmark/health/export fixes present in the current GitHub commit?

NEXT FUNCTION TO ANALYZE:
Python import/startup path, then /api/health.
```
