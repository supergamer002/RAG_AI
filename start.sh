#!/usr/bin/env bash
# Avvio di RAG AI su Linux / macOS / WSL
set -e
cd "$(dirname "$0")"

command -v python3 >/dev/null || { echo "Python 3.10+ non trovato."; exit 1; }
command -v ollama >/dev/null || echo "[ATTENZIONE] Ollama non trovato: installalo da https://ollama.com/download"

[ -d .venv ] || { echo "Prima esecuzione: creo l'ambiente Python..."; python3 -m venv .venv; }
. .venv/bin/activate
python -m pip install -q -r requirements.txt

echo "Avvio su http://localhost:8000  (Ctrl+C per chiudere)"
python run.py
