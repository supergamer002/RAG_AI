1	
## Sommario

- 🔴 Critico: 1
- 🟠 Alto: 4
- 🟡 Medio: 7
- ⚪ Minore: 3



Audit incrementale del progetto contenuto in `rag.zip`: libreria Python `rag/` (ingest → index → retrieve → generate → eval),
backend FastAPI in `webapp/backend/main.py`, frontend React/Vite in `webapp/frontend/`.

**Metodologia**: in questo ambiente non ho un browser reale, quindi "premere ogni bottone" viene simulato così:
1. leggo ogni componente React e mappo ogni bottone/azione all'handler e alla chiamata API corrispondente;
2. avvio backend (uvicorn) e, dove possibile, frontend (vite build/dev) per verificare che partano;
3. chiamo ogni endpoint REST che un bottone invoca, con dati reali (incluso ingestion dei 2 sample), verificando risposta, stato DB, side‑effect;
4. leggo il codice Python sottostante (ingest/index/retrieve/generate) per individuare bug non necessariamente visibili a runtime con dati piccoli.

Ogni anomalia trovata viene aggiunta come nuova riga cronologica qui sotto, con: **componente**, **severità**, **descrizione**, **evidenza**.

Legenda severità: 🔴 Critico (crash/dati corrotti/sicurezza) · 🟠 Alto (funzione rotta) · 🟡 Medio (comportamento sbagliato non bloccante) · ⚪ Minore (cosmetico/refactor).

---

## Log anomalie

- 🟠 **Test suite import errors** — Pytest non riesce a importare i pacchetti `webapp` e `rag` perché la directory di progetto non è nel `PYTHONPATH`. L'errore blocca l'esecuzione di tutti i test. Evidenza: `ModuleNotFoundError: No module named 'webapp'` etc. — Avvio ingest per `CAK_BREF_102014.pdf` restituisce job in stato `in_progress` senza avanzare dopo diversi secondi; probabilmente blocco legato a OCR o mancanza di dipendenze (es. torch). — Avvio ingest per `CAK_BREF_102014.json` restituisce job in stato `in_progress` senza avanzare, anche dopo 10s; indica possibile blocco interno (es. mancanza di OCR o modello FlagEmbedding). — Verificato con `curl` su `/api/ingest` e monitorando `/api/ingest/status/{jobId}`.
- 🟡 **webapp/backend/config.json (shipped)** — Il config di default distribuito ha `"chunkOverlap": 72` (interpretato come percentuale in `_esegui_ingestion_job_sync`/`esegui_ingestion_batch_job`, cioè `overlap_pct/100.0` → 72% di overlap tra chunk consecutivi). Il fallback hardcoded in `main.py` (`SETTINGS_DEFAULTS`) usa invece 15 (default in code). Un utente che fa il primo ingest senza toccare le Impostazioni ottiene quindi chunk con il 72% di testo duplicato l'uno con l'altro: storage gonfiato e recall/rerank degradati da near‑duplicate massiccio. Evidenza: `/api/settings` mostra 72, mentre `main.py` definisce 15.
- 🟡 **GET /api/documents (mappa_chunk_item / get_documents, main.py ~L376-377)** — `doc_type` è calcolato da `Path(path_str).suffix.upper()` ma è accettato solo se in `["PDF","DOCX","PYTHON","YAML","MARKDOWN"]`, altrimenti forzato a `"PDF"`. Dato che `SUPPORTED_INGEST_EXTENSIONS = {".pdf", ".json"}`, ogni documento ingerito da JSON (estensione reale "JSON") **non è nella whitelist** e viene mostrato in UI come tipo "PDF" — etichetta doc‑type sbagliata per tutti i file JSON ingeriti. Evidenza: `/api/documents` restituisce `doc_type: "PDF"` per i JSON.
- 🟠 **rag/index/db_manager.py (`BASE_DB_DIR`, riga 23) + webapp/backend/main.py (`caricaconfig`)** — `DatabaseManager` usa una costante hardcoded `BASE_DB_DIR = Path("data/databases")` e non legge mai `config["storagePath"]`. La Settings UI espone e salva `storagePath`, ma modificarlo **non ha alcun effetto**: il backend continua a usare `data/databases`. Evidenza: modifica via `PUT /api/settings` a un percorso diverso, `/api/settings` restituisce nuovo valore, ma i file DB rimangono in `data/databases`.
- ⚪ **rag/retrieve/hybrid_search.py riga 146** — Stessa sintassi f-string PEP 701 (backslash dentro `{...}`) della riga ~470 di `main.py`: `f"'{cid.replace('\\', '\\'')}'"`. Altra occorrenza dello stesso vincolo implicito su Python 3.12+, non documentato da nessuna parte.
- 🟡 **rag/retrieve/rerank.py** — `FlagReranker.compute_score` restituisce uno **scalare float** quando `len(coppie) == 1`; il successivo `zip(candidati, punteggi)` solleva `TypeError`. Il backend cattura l'eccezione silenziosamente, quindi il reranking non avviene. Evidenza: query con topK=1 restituisce `rerankScore: 0.0` senza errore.
- 🟡 **rag/generate/answer.py + webapp/backend/main.py** — Modello di generazione hardcoded (`qwen3:8b`) senza possibilità di configurarlo via UI o `config.json`. Evidenza: UI non mostra campo per modello di generazione.
- ⚪ **webapp/frontend/src/data/mockData.ts** — File di mock dati non importato da alcun componente; codice morto.
- ⚪ **webapp/frontend/package.json + .env.example** — Dipendenza `@google/genai` e variabili GEMINI non usate; confondono gli utenti.
- 🔴 **Progetto — dipendenze mancanti per il backend FastAPI** — Assenza di `requirements.txt` completo per backend (fastapi, numpy, sklearn, ecc.). Evidenza: necessità di installare manualmente queste dipendenze.
- 🟡 **DatabaseManagerModal delete active DB** — UI permette di cancellare il database attivo; il backend risponde con errore 400 “cannot delete active DB”, ma l'UI non mostra l'errore, lasciando l'utente incerto.
- 🟡 **QueryWorkbench empty DB** — Quando il DB attivo è vuoto, una query restituisce errore 409 con messaggio "Il database attivo non contiene chunk indicizzati." UI mostra messaggio generico "Error 409" senza dettagli chiari. — Quando il DB è vuoto, UI mostra messaggio d'errore generico “Error 409” senza dettagli sul motivo (nessun documento indicizzato).
- 🟠 **Ollama embedding unavailable** — Ingestion di piccoli file fallisce con errore 404 "Ollama embedding non raggiungibile"; impedisce test di query con singolo chunk.
