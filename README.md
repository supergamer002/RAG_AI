# RAG AI

Assistente RAG locale con FastAPI, SQLite, Ollama, Cross-Encoder lazy e ingestion persistente in background.

## Struttura attiva

- `app/` — unico backend Python e pipeline di ingestion.
- `app/static/index.html` — unica GUI web servita dal backend.
- `tests/` — test dell'app attiva.
- `skills/auditing-fullstack-rag-apps/` — skill per gli audit.

Non esiste più un secondo backend Express/Node né una seconda applicazione FastAPI/React parallela.

## Funzionamento

Upload → job persistente → Estrazione → Segmentazione → Embedding → Salvataggio → Pronto/Parziale/Errore.

La GUI mostra il progresso reale della fase corrente e dei chunk durante l'embedding. File e cartelle usano le stesse API del backend.

## Modelli Ollama

I modelli restano fissati ai valori stabiliti per il progetto:

- `qwen3:8b`
- `qwen3-embedding:0.6b`

La GUI non permette di sostituirli.

## Avvio

- Windows: `start.bat`
- Linux/macOS/WSL: `start.sh`

Servizio: `http://localhost:8000`.

Ollama viene avviato/controllato dal backend quando configurato per l'auto-setup.

## Dipendenze

Il runtime attivo usa Python, FastAPI, SQLite, NumPy, Requests, PyMuPDF, fontTools, PyTorch e Transformers.
Non vengono usati LanceDB, PyArrow, SciPy, FlagEmbedding o un frontend Node separato.

## Test

```
pip install -r requirements-dev.txt
pytest
```
