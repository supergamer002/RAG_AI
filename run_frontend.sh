#!/usr/bin/env bash
set -e
PROJECT_ROOT="/mnt/c/Users/diego/OneDrive/Documenti/GitHub/ygdbsjh-gsaydg93-sdja_sahdad262/RAG_AI"
cd "$PROJECT_ROOT/webapp/frontend"

if [ ! -d node_modules ]; then
  echo "[Frontend] Prima esecuzione: installo le dipendenze npm..."
  npm install
fi

echo "[Frontend] Avvio della dashboard frontend su http://localhost:3000 ..."
npm run dev
