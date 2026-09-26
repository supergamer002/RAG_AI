#!/usr/bin/env bash
set -euo pipefail

# -------------------------------------------------
# run-audit.sh – Minimal wrapper for the full audit
# -------------------------------------------------
# 1. Ensure backend deps are installed (fastapi, uvicorn, etc.)
#    (Assumes the environment already has the required Python packages.)
# 2. Start backend & frontend (background) – adjust as needed.
# 3. Initialise AUDIT.md from the partial file.
# 4. Ingest the JSON and PDF samples.
# 5. Run a set of sanity queries.
# 6. Summarise results.
# -------------------------------------------------

# Helper to start a service in background and capture its PID
start_service() {
  local cmd="$1"
  eval "$cmd" &
  echo $!  # return PID
}

# --- Step 0: start services ---------------------------------------------------
backend_pid=$(start_service "uvicorn webapp.backend.main:app --host 127.0.0.1 --port 8000 --reload")
# Give it a moment to bind
sleep 2
frontend_pid=$(start_service "cd webapp/frontend && npm run dev")
# Give it a moment to bind
sleep 5

echo "✅ Services started (backend PID $backend_pid, frontend PID $frontend_pid)"

# --- Step 1: initialise AUDIT.md -------------------------------------------
cp -n AUDIT_parziale.md AUDIT.md || true

echo "✅ AUDIT.md initialised"

# --- Step 2: ingest JSON ----------------------------------------------------
json_job=$(curl -s -X POST -F "file=@test-samples/CAK_BREF_102014.json" http://127.0.0.1:8000/api/ingest | jq -r .jobId)
# poll until done (simple loop, max 30 attempts)
for i in {1..30}; do
  status=$(curl -s http://127.0.0.1:8000/api/ingest/status/${json_job} | jq -r .status)
  if [[ "$status" == "completed" ]]; then
    echo "✅ JSON ingest completed"
    break
  elif [[ "$status" == "failed" ]]; then
    echo "❌ JSON ingest failed"
    break
  fi
  sleep 2
done

# --- Step 3: ingest PDF -----------------------------------------------------
pdf_job=$(curl -s -X POST -F "file=@test-samples/CAK_BREF_102014.pdf" http://127.0.0.1:8000/api/ingest | jq -r .jobId)
for i in {1..60}; do
  status=$(curl -s http://127.0.0.1:8000/api/ingest/status/${pdf_job} | jq -r .status)
  if [[ "$status" == "completed" ]]; then
    echo "✅ PDF ingest completed"
    break
  elif [[ "$status" == "failed" ]]; then
    echo "❌ PDF ingest failed"
    break
  fi
  sleep 5
done

# --- Step 4: sanity query ---------------------------------------------------
query_resp=$(curl -s -X POST -H "Content-Type: application/json" -d '{"query":"diaframma","topK":5}' http://127.0.0.1:8000/api/query)
echo "🧪 Sample query result (truncated):"
echo "$query_resp" | jq . | head -n 20

# --- Step 5: cleanup --------------------------------------------------------
kill $backend_pid $frontend_pid 2>/dev/null || true

echo "✅ Audit run completed. Review AUDIT.md for recorded anomalies."
