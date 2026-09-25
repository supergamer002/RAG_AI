#!/usr/bin/env bash
set -e
PROJECT_ROOT="/mnt/c/Users/diego/OneDrive/Documenti/GitHub/ygdbsjh-gsaydg93-sdja_sahdad262/RAG_AI"
cd "$PROJECT_ROOT"

# Create virtualenv if missing
if [ ! -d .venv2 ]; then
  echo "[Backend] Creazione virtualenv .venv2"
  python3 -m venv .venv2
fi
source .venv2/bin/activate

echo "[Backend] Verifico e installo le dipendenze Python del backend..."
python -m pip install --upgrade pip
python -m pip install --break-system-packages -r webapp/backend/requirements.txt

echo "[Backend] Avvio UVicorn (in background)"
nohup uvicorn webapp.backend.main:app --host 0.0.0.0 --port 8000 --reload > backend.log 2>&1 &
