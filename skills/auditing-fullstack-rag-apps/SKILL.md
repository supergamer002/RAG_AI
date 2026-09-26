---
name: auditing-fullstack-rag-apps
description: Use when performing a full‑stack audit of a FastAPI + React RAG application, mapping UI buttons to backend endpoints and recording live evidence in AUDIT.md.
---

# Auditing Full‑Stack RAG Applications

## Overview
This skill encodes the methodology for a systematic, live‑environment audit of a FastAPI + React RAG app.  It maps every interactive UI element to its corresponding backend API call, exercises each flow with real data (including the JSON and PDF samples), captures concrete evidence, and records anomalies in a structured `AUDIT.md` file.

## When to Use
- **Use when** you need to verify that the UI‑to‑backend contract works end‑to‑end rather than relying on static code reading alone.
- **Do not use** for pure code‑style refactoring or UI redesign that does not require live verification.

## High‑Level Audit Pipeline
| Step | Action | Artefacts |
|------|--------|-----------|
| **0️⃣ Setup** | Install missing backend deps, start `uvicorn` on `127.0.0.1:8000` and `npm run dev` for the frontend. | Running services, `settings.json` snapshot |
| **1️⃣ Initialise AUDIT.md** | Copy `AUDIT_parziale.md` → `AUDIT.md` preserving existing entries. | Baseline audit file |
| **2️⃣ Static Mapping** | Parse `webapp/frontend/src/**/*.tsx` to extract every button/handler and the FastAPI route it invokes. | Mapping table (UI → API) |
| **3️⃣ Live Verification** | For each mapping entry: trigger the UI action (Playwright or `curl`), send realistic payloads (including ingestion of the two sample files), capture response, DB changes, UI feedback, and any error codes. | Per‑action evidence (curl output, Playwright logs, DB snapshots) |
| **4️⃣ Edge‑Case Testing** | Run the special scenarios from the brief (empty DB, single‑chunk DB, duplicate title handling, settings validation, etc.). | Additional anomaly entries |
| **5️⃣ Dependency Check** | Record any missing Python packages or version mismatches that prevent the app from starting. | “Missing dependency” anomalies |
| **6️⃣ Summarise** | Prepend a severity summary (🔴 / 🟠 / 🟡 / ⚪) and list of fully‑tested vs. blocked areas (e.g. Ollama unavailable). | Updated header in `AUDIT.md` |
| **7️⃣ Export Skill** | Commit this `SKILL.md` and the one‑page cheat‑sheet `quick‑reference.md`. | Skill artefacts |

## Red‑Flags (stop and restart)
- **Skipping live verification** – add a ⚪ “Live verification skipped – audit incomplete”.
- **Ignoring missing dependencies** – add a 🔴 “Missing fastapi → backend cannot start”.
- **Accepting generic “Error 409” without source** – add a 🟡 “Error 409 without detailed cause – UI should surface backend message”.

## Quick Reference (see `quick-reference.md`)
- **Start services**: `uvicorn webapp.backend.main:app --host 127.0.0.1 --port 8000 --reload &` then `cd webapp/frontend && npm install && npm run dev &`
- **Copy audit file**: `cp AUDIT_parziale.md AUDIT.md`
- **Run ingest**: `curl -X POST -F "file=@<path>" http://127.0.0.1:8000/api/ingest`
- **Check status**: `curl http://127.0.0.1:8000/api/ingest/status/<jobId>`
- **Query DB**: `curl -X POST -H "Content-Type: application/json" -d '{"query":"…"}' http://127.0.0.1:8000/api/query`
- **Update settings**: `curl -X PUT -H "Content-Type: application/json" -d '{"chunkOverlap":50}' http://127.0.0.1:8000/api/settings`

## Common Mistakes
1. **Running the backend before installing FastAPI** – leads to a 🔴 missing‑dependency anomaly.
2. **Using the wrong storage path** – UI shows the new path but DB stays under `data/databases` (🟠 dead setting).
3. **Assuming JSON files appear as PDFs** – UI labels JSON as “PDF” (🟡 doc‑type typo).
4. **Running a query on an empty DB** – receives generic 409 error (🟡 poor UX).

## Implementation Notes
- The skill purposefully limits code to **one excellent example** (the `run‑audit.sh` wrapper in `example‑run/`).  All reusable scripts live there; the core skill stays under 500 words for cheap discovery.
- For heavy reference (Playwright scripts, full API docs) see the `example‑run/` sub‑folder; they are **not** loaded by default.

---

*End of skill.*