# Quick reference for auditing a FastAPI + React RAG app

| Action | Command | Notes |
|--------|---------|-------|
| **Start backend** | `uvicorn webapp.backend.main:app --host 127.0.0.1 --port 8000 --reload &` | Runs on localhost; ensure Python 3.12+ and FastAPI deps are installed. |
| **Start frontend** | `cd webapp/frontend && npm install && npm run dev &` | Vite dev server on http://localhost:3000. |
| **Initialise AUDIT.md** | `cp AUDIT_parziale.md AUDIT.md` | Preserves existing entries. |
| **Ingest a file** | `curl -X POST -F "file=@<path>" http://127.0.0.1:8000/api/ingest` | Returns a `jobId`; monitor with the next command. |
| **Check ingest status** | `curl http://127.0.0.1:8000/api/ingest/status/<jobId>` | Poll until `status` is `completed` or `failed`. |
| **Run a query** | `curl -X POST -H "Content-Type: application/json" -d '{"query":"<text>","topK":20}' http://127.0.0.1:8000/api/query` | Returns retrieved chunks and generated answer. |
| **Update a setting** | `curl -X PUT -H "Content-Type: application/json" -d '{"chunkOverlap":50}' http://127.0.0.1:8000/api/settings` | Example: change default chunk overlap from 72 % to 50 %. |
| **Activate a database** | `curl -X POST http://127.0.0.1:8000/api/databases/<dbId>/activate` | Needed after creating a new DB via the API. |
| **Export a DB** | `curl -X GET http://127.0.0.1:8000/api/databases/<dbId>/export -o <file>.zip` | Saves a zip containing sources and chunks. |
| **Import a DB** | `curl -X POST -F "file=@<file>.zip" http://127.0.0.1:8000/api/databases/import` | Restores a previously exported DB. |

---

**Tip:** After each step, verify the action’s effect by checking the relevant UI feedback or API JSON response. Any missing or unexpected behaviour should be logged as an anomaly in `AUDIT.md` following the severity legend.
