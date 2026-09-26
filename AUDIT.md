# AUDIT.md — Function-Flow Deep Code Audit

**Progetto:** RAG_AI.zip  
**Metodo:** Function-Flow Deep Code Audit  
**Audit:** 3 passate complete + verifiche dinamiche mirate  
**Data:** 2026-09-26  
**Modifiche al progetto originale:** NESSUNA

---

## 0. Executive Summary

L'audit non si è limitato alla lettura lineare dei file. Il codice è stato ricostruito come un grafo di esecuzione: entry point → funzione → callee → stato/dati → rami → uscita. Ogni ramo importante è stato seguito fino a una condizione terminale oppure marcato come non verificabile per una dipendenza mancante.

### Severità

| Severità | Quantità indicativa | Sintesi |
|---|---:|---|
| 🔴 P0/P1 | 7 | Blocchi funzionali o rischio di perdita/inconsistenza dati |
| 🟠 P2 | 13 | Funzioni che possono fallire, mentire alla UI o degradare pesantemente il comportamento |
| 🟡 P3 | 15+ | UX, osservabilità, scalabilità, test obsoleti/debolezze |
| ⚪ | 6+ | Limiti ambiente, debito tecnico o verifiche non eseguibili |

### Problemi più importanti

1. **🔴 Infinite loop confermato nel chunker** (`rag/ingest/chunker.py:101-130`). È riproducibile con un caso semplice: il processo resta oltre il timeout senza terminare. Può spiegare direttamente ingest che resta attivo senza creare nuovi chunk.
2. **🔴 FTS non viene realmente aggiornato quando esiste già**: `crea_indice_fulltext(..., replace=False)` non ricostruisce l'indice dopo l'upsert. Il nuovo contenuto può quindi restare invisibile alla ricerca sparse/hybrid.
3. **🔴 Import/export perde il modello di embedding**: il DB importato viene registrato come `imported/unknown`; query/ingest possono quindi chiedere a Ollama un modello inesistente o incompatibile.
4. **🔴 Dimensione embedding non legata in modo affidabile al DB**: il DB memorizza una dimensione, ma l'embedder usato da query/ingest viene creato senza imporre/validare quella dimensione.
5. **🔴 Le impostazioni di runtime e LanceDB sono in parte solo decorative**: `storagePath`, `hostUrl`, `portNumber`, `workerConcurrency`, `indexAlgorithm`, `distanceMetric`, ecc. non modificano sempre il comportamento reale dichiarato dalla UI.
6. **🔴 `/api/query` può usare il DB attivo per scegliere il modello anche quando riceve una tabella esplicita**. Questo rende benchmark/concorrenza e operazioni multi-database vulnerabili a mismatch modello/dimensione.
7. **🔴 `/api/query` esegue fallback troppo ampi**: errori di retrieval e reranking vengono trasformati in percorsi alternativi o risposta 200 degradate, rendendo difficile capire perché una pipeline è fallita.

---

# 1. Artefatti e ambiente di audit

## Copia analizzata

`/mnt/data/function_audit_rag/project`

## Artefatti prodotti

- `AUDIT.md` — questo report completo.
- `AUDIT_MEMORY.md` — checkpoint per riprendere l'audit senza ripetere la ricostruzione.
- `FIX_LIST.md` — lista prioritaria ordinata delle correzioni/verifiche.
- `relevant_full.txt` — estratti con numeri di riga usati durante l'analisi.
- `main_relevant.txt` — estratti mirati di `webapp/backend/main.py`.

## Verifiche eseguite

- `python -m compileall -q rag webapp/backend tests` → **PASS**
- `pytest -q tests/test_schema.py tests/test_monitoring.py` → **7 passed**
- Test esterno sul chunker con timeout → **FAIL intenzionale / riproduzione del bug: timeout 124**
- Verifica statica dei contratti frontend → eseguita
- Analisi AST di definizioni Python → eseguita
- Build/test completi → bloccati da dipendenze/runtime non disponibili nel container

## Blocchi ambientali

- `lancedb` non installato → suite backend completa non eseguibile.
- Installazione dipendenze Python non riuscita per assenza di rete/DNS nel container.
- `FlagEmbedding`, `umap-learn`, `docling` non presenti per test reali.
- Build TypeScript completo bloccato dall'ambiente `node_modules`/binding nativi presente nello ZIP.

Questi blocchi sono distinti dai bug statici/dinamici confermati nel codice.

---

# 2. Entry Point Map

## Backend

```text
webapp/backend/main.py
└── FastAPI app
    ├── /api/settings, /api/health
    ├── /api/stats
    ├── /api/databases/*
    ├── /api/documents
    ├── /api/documents/{id}/reindex
    ├── /api/chunks*
    ├── /api/ingest
    │   └── esegui_ingestion_batch_job
    │       ├── ingest_file_unita / ingest_pdf
    │       ├── chunking
    │       ├── embedding Ollama
    │       ├── upsert LanceDB
    │       └── FTS
    ├── /api/query
    │   └── _esegui_query_su_tabella
    │       ├── embedding
    │       ├── dense / sparse / hybrid retrieval
    │       ├── rerank
    │       └── generation
    ├── /api/vectors/project
    ├── /api/eval/run
    │   └── run_evaluations
    ├── /api/telemetry*
    └── /api/system/restart
```

## Frontend

```text
App.tsx
├── SettingsView
├── QueryWorkbenchView
├── KnowledgeNodesView
├── VectorExplorerView
├── PipelineTelemetryView
└── EvaluationsView

Modali / azioni trasversali
├── IngestModal
├── DatabaseManagerModal
└── ChunkModal
```

Il percorso API è centralizzato in `apiFetch()` / `apiJson()` (`src/api.ts`), che aggiungono automaticamente il Bearer token se presente.

---

# 3. Function-Flow Pass 1 — Ingest

## 3.1 Entry: `POST /api/ingest`

**File:** `webapp/backend/main.py:754+`

### Input

- file singolo
- lista di file
- path/form
- `chunkSize`
- `chunkOverlap`
- `ocrEnabled`

### Flusso

```text
POST /api/ingest
├── nessun file/path
│   └── validation error → EXIT
├── troppi file
│   └── 413/400 → EXIT
├── estensione non supportata
│   └── file scartato → continua
│       └── nessun file supportato → EXIT
├── file > limite
│   └── 413 → EXIT
├── totale > limite
│   └── 413 → EXIT
└── almeno un file valido
    ├── salva in sources/upload_UUID
    ├── crea ingestion_jobs[job_id]
    └── schedule esegui_ingestion_batch_job
        └── return jobId → EXIT HTTP
```

### Osservazione

Il job è corretto concettualmente come lavoro asincrono, ma la sua fase CPU/parser/chunker dipende dalle funzioni chiamate e può quindi restare attiva indefinitamente. Il problema reale viene trovato nel chunker, non nel polling frontend.

---

## 3.2 `esegui_ingestion_batch_job`

**File:** `main.py:663-752`

### Flusso

```text
JOB
├── apertura DB target
│   ├── OK → continua
│   └── errore → status=failed → EXIT
│
├── per ogni file
│   ├── .json → ingest_file_unita
│   ├── .pdf  → ingest_pdf
│   └── altro → ValueError
│
│   risultato chunks
│   ├── chunks > 0
│   │   └── normalizza fonte_path
│   │       ├── ricalcola_id
│   │       └── _indicizza_chunks_incrementale
│   │           ├── embedding OK → upsert
│   │           └── embedding fail → eccezione file
│   └── chunks == 0
│       └── file segnato processato senza dati
│
│   FTS
│   ├── creazione OK
│   └── errore FTS → record error, job continua
│
└── fine ciclo
    ├── filesProcessed == 0 OR total_chunks == 0
    │   └── failed
    └── almeno un chunk
        └── completed (+warning se errors)
```

### 🟥 P1 — Stato `completed` non implica necessariamente successo pieno

Un job può finire `completed` anche con errori parziali. Questo è intenzionale nel commento, ma la semantica UI deve distinguere chiaramente:

- completamente riuscito
- parzialmente riuscito
- riuscito con FTS fallito

Oggi `completed` è usato come stato primario anche quando `job["error"]` contiene una stringa di errore/warning.

**Raccomandazione:** introdurre `completed_with_errors` oppure campi espliciti `partialSuccess`, `ftsHealthy`, `filesFailed`.

---

## 3.3 `ingest_file_unita`

**File:** `rag/ingest/from_units.py:44+`

```text
Path JSON
└── carica_unita
    ├── JSON valido → unità
    ├── struttura non valida → errore
    └── file illeggibile → errore
└── chunk_documento
```

La funzione è semplice e raggiungibile; il rischio principale è downstream, nel chunking.

---

## 3.4 `chunk_documento` → `chunk_sezione`

**File:** `rag/ingest/chunker.py:52-159`

### Branch map

```text
chunk_sezione
├── aggiungi blocchi tabella
│   └── un chunk per tabella
├── testo vuoto
│   └── return risultato
└── split frasi
    └── while i < len(frasi)
        ├── frase già >= target
        │   └── emetti → i++ → continua
        ├── chunk corrente + frase > target
        │   ├── emetti chunk corrente
        │   ├── calcola overlap
        │   └── CONTINUE senza incrementare i
        └── append frase
            └── i++
```

### 🔴 P0 — Infinite loop confermato

**File:** `rag/ingest/chunker.py:113-126`

La condizione:

```text
chunk_parole + n_parole > chunk_target_parole
```

può essere vera dopo che `chunk_frasi` è stata sostituita con l'overlap. Se l'overlap stesso contiene una frase quasi grande quanto il target, il ramo viene ripetuto:

```text
emit overlap
→ stesso i
→ stesso overlap
→ stessa frase corrente
→ stesso test
→ emit overlap
→ ...
```

### Riproduzione

Test usato nell'ambiente di audit:

- frase 1 ≈ 70 parole
- frase 2 ≈ 70 parole
- `target_token=100` → target parole ≈ 76
- `overlap_ratio=0.5`

Risultato: il processo supera 3 secondi e `timeout` restituisce **124**.

### Impatto

Questo può bloccare un job di ingest prima dell'upsert LanceDB. È compatibile con il sintomo osservato in precedenza: **upload presenti, database senza nuovi chunk**.

### Fix concettuale

L'overlap non deve poter rimettere il loop in uno stato dal quale il prossimo passo non consuma almeno una frase. Possibili strategie:

1. dopo il nuovo overlap, se `frase corrente` non può entrare, forzarne l'emissione come chunk singolo;
2. garantire `i += 1` in ogni iterazione produttiva;
3. aggiungere una guardia anti-stallo: se `(i, chunk_frasi)` non cambia per due iterazioni, emettere e avanzare.

La strategia migliore deve preservare la semantica di non spezzare le frasi senza lasciare un possibile loop.

---

# 4. Embedding / Persistence Flow

## 4.1 `_indicizza_chunks_incrementale`

**File:** `main.py:627-660`

```text
chunks
└── batch 32
    ├── get_active_info()
    ├── sceglie embeddingModel
    ├── prende ollamaUrl globale
    ├── get_embedder
    ├── embed(batch)
    │   ├── OK → upsert_chunks
    │   └── errore → RuntimeError → EXIT batch/job
    └── aggiorna progress
```

### 🔴 P1 — Il modello è legato al DB attivo, non al DB target catturato

La funzione riceve `tabella` del database target, ma dentro usa:

```text
active_info = db_manager.get_active_info()
```

Quindi:

```text
DB A catturato all'inizio
+ user cambia DB → DB B
+ worker continua
→ tabella = A
→ modello scelto = B
```

È una violazione del contratto della funzione: il calcolo dovrebbe essere determinato dallo stesso database target della tabella.

### Fix

Passare `database_id` e risolvere modello/endpoint/dimensione esclusivamente dal DB target.

---

## 4.2 Dimensione embedding

**File:** `rag/index/store.py:25-37`, `db_manager.py:193-214`, `embed_manager.py`

Il DB registra `dimension`, ma l'embedder costruito nella pipeline non riceve la dimensione del DB e non c'è una validazione esplicita:

```text
DB schema dimension = D
       ↓
Ollama embedder → produce vettori di dimensione M
       ↓
upsert
```

Se `D != M`, l'operazione può fallire o diventare incompatibile.

### 🔴 P1 — Dimensione non vincolata al database

**Fix:**

- usare `dimension` del DB nel percorso embedding;
- validare `len(embedding) == db.dimension` prima di `upsert_chunks`;
- impedire creazione/import con incompatibilità;
- registrare modello + dimensione con ogni DB.

---

# 5. FTS / Retrieval Flow

## 5.1 `crea_indice_fulltext`

**File:** `rag/retrieve/hybrid_search.py:25+`

Il default è `replace=False`.

Il worker ingest chiama:

```text
crea_indice_fulltext(tabella)
```

sia in `main.py:605` sia in `main.py:734`.

### 🔴 P1 — Indice FTS esistente non viene ricostruito dopo l'upsert

Se l'indice esiste, il nuovo contenuto può non essere incluso.

Esiste `aggiorna_indice_fts_in_background(... replace=True)`, ma non è il percorso normale dell'ingest.

### Impatto

```text
nuovo documento → LanceDB OK
              ↘ FTS vecchio
```

Dense search può funzionare mentre sparse/hybrid perde i nuovi documenti.

**Fix:** refresh/rebuild FTS dopo ogni batch o, meglio, usare un meccanismo incrementalmente supportato da LanceDB se disponibile nella versione utilizzata.

---

# 6. Query Flow

## 6.1 `/api/query`

**File:** `main.py:339-360`

```text
POST /api/query
├── query vuota → 400
├── DB vuoto → 200 {answer:"", chunks:[]}
└── _esegui_query_su_tabella
    ├── tutto OK → 200
    └── eccezione non gestita → 503
```

### Nota positiva

Il backend ora include nel 503 il tipo e il messaggio dell'eccezione, quindi il server non nasconde completamente la causa.

### 🟠 P2 — UI perde la causa

`apiJson()` la conserva, ma `QueryWorkbenchView` nel catch la sostituisce con un messaggio generico. Quindi il server può dire:

```text
Pipeline RAG non disponibile: X: modello/dimension mismatch
```

mentre la UI mostra solo un errore generico.

**Fix:** mostrare `Error.message` nella UI e mantenere status code + detail.

---

## 6.2 `_esegui_query_su_tabella`

**File:** `main.py:1244-1332`

```text
query
├── searchMode != sparse
│   └── get_active_info → embed query
│
├── dense
│   └── vector search
│
├── sparse
│   └── FTS
│
└── hybrid / altro
    └── ricerca_ibrida

retrieval exception
└── ricrea FTS
    └── nuova ricerca ibrida

rerank
├── disabled → top_n
└── enabled
    ├── OK → rerank
    └── fail → candidati[:top_n]

generation
├── OK → answer
└── fail → risposta fallback
```

### 🔴 P1 — Ricerca esplicita della tabella ma configurazione presa dal DB attivo

Il docstring dichiara:

> “senza dipendere dal DB attivo”

ma `get_active_info()` viene chiamato per il modello di embedding.

È quindi falsa l'invariante dichiarata dalla funzione.

### 🟠 P2 — Catch retrieval troppo ampio

Il blocco:

```text
except Exception:
    crea_indice_fulltext(tabella)
    candidati = ricerca_ibrida(...)
```

tratta allo stesso modo:

- errore FTS
- errore embedding
- dimension mismatch
- errore LanceDB
- bug di programmazione

Questo rende il secondo errore quello visibile e può nascondere la causa primaria.

### 🟠 P2 — Errore reranker convertito in successo silenzioso

Se il reranker fallisce, il backend prende i primi `top_n` e restituisce 200.

È accettabile come degradazione solo se viene dichiarato alla UI:

```text
retrieval = ok
rerank = failed
```

Altrimenti il sistema presenta un risultato come se fosse stato realmente rerankato.

### 🟠 P2 — Errore generator convertito in risposta 200

Se `rispondi()` fallisce, viene prodotta una risposta fallback basata sul contesto. La UI quindi può mostrare una risposta valida quando in realtà la generazione LLM non è riuscita.

**Fix:** campo `degraded=true`, `generationError`, e indicazione chiara nella UI. Per benchmark seri è necessario distinguere risposta LLM da fallback.

---

# 7. Query UI — Fake / stale data

## `QueryWorkbenchView.tsx`

### 🔴 P1 — Risposta dimostrativa hardcoded

Riga ~321:

```text
Nell'architettura di Nexus RAG...
```

Quando `realAnswer` è vuota, la UI mostra testo dimostrativo.

### 🔴 P1 — Citazioni dimostrative hardcoded

Righe ~339-345:

- `Manuale_Architettura_RAG_v2.pdf`
- `FastAPI_Uvicorn_Orchestration_Guide.md`

Vengono visualizzate come “Citazioni Verificate”.

Questo non è solo un placeholder estetico: è una **falsificazione del risultato visibile** durante una query fallita o senza risultato.

**Fix obbligatorio:** nessun contenuto demo nel percorso operativo. Mostrare `—`, “Nessuna risposta disponibile” o stato diagnostico.

### 🟠 P2 — Chunk vecchi mostrati dopo una query senza risultati

La logica `visibleChunks` usa fallback ai `chunks` precedenti quando `realChunks.length === 0`.

Quindi:

```text
query A → chunks presenti
query B → API risponde []
→ realChunks = []
→ visibleChunks ricade sui chunks precedenti
```

La UI mostra risultati vecchi come se appartenessero alla query corrente.

### 🟡 P3 — Errori possono lasciare stato precedente

Dopo una query fallita la schermata può conservare lo stato visivo precedente. Serve una politica esplicita:

```text
running → clear current result
failed → show failure state
completed → show current result
```

---

# 8. Data Ingest / document metadata flow

## `store.py`

Schema LanceDB:

```text
chunk_id
 testo
 vector
 fonte_titolo
 tipo_fonte
 sezione
 posizione
 fonte_path
 lingua
```

Non esistono:

- `ingestedAt`
- `embeddingModel`
- `parser`
- `overlapPct`
- metadata file persistente

### 🔴 P1 — “Data Ingest” non può essere realmente una data di ingest

`mappa_chunk_item()` legge `ingestedAt`, ma il campo non viene scritto nello schema.

### 🔴 P1 — `get_documents()` usa mtime del file sorgente come `indexedDate`

Questo valore è:

```text
source file modification time
```

non:

```text
ingestion timestamp
```

Se la sorgente non esiste più, il dato può diventare vuoto.

Questo spiega il sintomo riferito dall'utente: **“data non viene compilato”**.

### 🟠 P2 — File size non persistente

`fileSize` viene ricavato dal filesystem della sorgente. Dopo export/import o cancellazione della sorgente, il dato può sparire.

### 🟠 P2 — parser non persistente

Il backend restituisce `parser` ma il record non lo contiene.

### 🟠 P2 — doclingAstNodes sempre `None`

`get_documents()` inizializza:

```text
doclingAstNodes = None
```

e non ricava realmente il numero dei nodi.

---

# 9. Re-index Flow

## `/api/documents/{document_id}/reindex`

```text
get_documents
└── exact document ID
    ├── non trovato → 404
    └── trovato
        ├── source missing → 409
        └── source present
            └── job
                └── esegui_ingestion_job(... hardcoded 512,15,True)
```

### 🟠 P2 — Reindex non usa la configurazione/storia del documento

Parametri hardcoded:

```text
512 token
15 overlap
OCR=true
```

Il documento può essere stato indicizzato con impostazioni completamente diverse.

### 🟠 P2 — ramo `else` morto

Subito prima viene verificata l'esistenza del file con `raise`.

Il ramo:

```text
if target_path.exists(): ...
else: ...
```

ha quindi un `else` non raggiungibile nella pratica.

La chiamata `background_tasks.add_task(...)` in quel ramo è codice morto.

### 🟠 P2 — Directory reindex/source path

Il percorso relativo al DB viene ricalcolato per file singolo, ma il ramo directory di `_esegui_ingestion_job_sync()` non normalizza allo stesso modo ogni `fonte_path`. Con dati provenienti da una directory, sono possibili path assoluti persistenti.

---

# 10. Multi-database Flow

## Create

```text
POST /api/databases
→ validate name
→ create DB schema
→ append registry
→ save
```

Questo percorso è sostanzialmente coerente.

## Activate

```text
id valido
→ active_id = id
→ save registry
```

### 🟠 P2 — Non verifica che DB/table fisici siano realmente apribili

Un elemento del registry può essere attivato anche se il percorso è mancante o corrotto. Più avanti `apri_o_crea_tabella()` può creare una tabella vuota in certe condizioni.

## Import / Export

### 🔴 P1 — Metadata di embedding persi nell'export

`export_database()` comprime la directory fisica del DB ma non aggiunge metadata di registro.

`import_database()` assegna:

```text
embeddingModel = imported/unknown
```

Questo rende l'importato non interrogabile in modo affidabile se la query ha bisogno del modello registrato.

**Fix:** includere nel file ZIP un `database_meta.json` con:

```text
id logical
name
embeddingModel
dimension
tableName
createdAt
version/schema
```

Al momento dell'import bisogna ricreare il registry usando quei valori e validare la dimensione dello schema.

---

# 11. Storage / corruption flow

## `apri_o_crea_tabella()`

**File:** `rag/index/store.py:46-58`

```text
list_tables
├── chunks presente → open_table
└── errore / assente
    └── open_table
        ├── OK → return
        └── errore → create_table
```

### 🟠 P2 — Corruzione potenzialmente mascherata come DB vuoto

Un errore di apertura di una tabella esistente può trasformarsi in `create_table()`.

Questo è pericoloso: un DB corrotto o incompatibile può sembrare un database nuovo e vuoto.

**Fix:** distinguere:

```text
NOT_FOUND → create
OPEN_ERROR → fail loudly
SCHEMA_MISMATCH → fail loudly
```

---

# 12. Settings Flow

## `/api/settings`

Validazione numerica buona in linea generale.

### Contratti non coerenti

#### 🔴 P1 — `indexAlgorithm`

Frontend permette:

```text
IVF-PQ | Flat | HNSW
```

Backend accetta:

```text
IVF-PQ | FLAT
```

Quindi `Flat`/`HNSW` possono essere proposti dalla UI ma non sono realmente supportati dal backend.

#### 🔴 P1 — `storagePath`

`restart_runtime()` ricarica la configurazione ma `DatabaseManager` conserva il `base_dir` costruito all'import del modulo.

Quindi cambiare `storagePath` e fare “restart” logico non riallinea necessariamente il gestore DB al nuovo path.

#### 🟠 P2 — host/port

La UI suggerisce che le impostazioni runtime siano applicate senza downtime, ma:

- host
- port
- worker
- log level

non riavviano realmente il server Uvicorn.

#### 🟠 P2 — CORS

Gli origin sono configurati all'avvio e non vengono completamente riallineati con `restart_runtime()`.

#### 🟠 P2 — `distanceMetric`

È validata, ma non è usata in modo coerente nella creazione/search dell'indice.

#### 🟠 P2 — `numCentroids`, `subVectorsPQ`

Sono presenti nella UI/config ma non risultano collegati fino al reale processo di indicizzazione LanceDB.

#### 🟠 P2 — `tableName`

`DatabaseManager.get_table_for_db(db_id, table_name)` riceve un nome ma usa di fatto la tabella costante `chunks`.

#### 🟠 P2 — Settings ingest non applicate al modal

`SettingsView` salva chunk size/overlap/OCR/split mode, ma `IngestModal` mantiene propri valori/stati invece di riflettere sempre la configurazione persistita.

#### 🟠 P2 — `maxPayloadMB`

Il controllo applicativo avviene dopo che la richiesta multipart è stata già parsata. Quindi non è una vera protezione contro un 413 generato prima dell'handler.

Questo è rilevante rispetto all'errore precedente:

```text
POST /api/ingest → 413 Content Too Large
```

Se il 413 arriva dal parser/proxy/runtime prima dell'handler, questa impostazione non può evitarlo.

---

# 13. Vector Explorer Flow

## Backend `project_vectors`

**File:** `main.py:1016-1113`

```text
sample rows
└── numpy matrix
    ├── <2 rows / <2 dims → center all points
    └── normal
        ├── UMAP
        ├── t-SNE
        └── PCA
    └── KMeans
        └── points
```

### 🔴 P1 — UMAP mancante nelle dipendenze

Il default è UMAP, ma `requirements.txt` non contiene `umap-learn`.

Su installazione pulita:

```text
/api/vectors/project → 503
```

### 🔴 P1 — UMAP con 2 campioni

Il codice fa:

```text
n_neighbors = min(15, n-1)
n_neighbors = max(2, n_neighbors)
```

Per `n=2` ottiene:

```text
2
```

ma UMAP richiede `n_neighbors < n_samples`.

Quindi il caso 2 punti è logicamente invalido.

### 🟠 P2 — UI filtra ma il render usa un'altra lista

`visibleScatterPoints` viene calcolata ma il render usa `scatterPoints`.

La ricerca globale quindi non filtra realmente i punti del grafico.

### 🟠 P2 — Event listener iniziale ridondante

`handleSelectAlgorithm()` effettua una richiesta a `/api/chunks/sample?sampleSize=500`, ma i dati ottenuti non sono realmente usati per la proiezione che viene poi eseguita.

### 🟡 P3 — coordinate non semanticamente interpretabili

x/y sono normalizzate in un intervallo 15..85/90 e non hanno unità. La UI dovrebbe chiarire che sono coordinate di proiezione relativa, non metriche fisiche.

### 🟡 P3 — “Voronoi 256” decorativo

La UI mostra una risoluzione “Voronoi 256”, ma non esiste un algoritmo Voronoi corrispondente nel backend.

### 🟡 P3 — Rerank score nel viewer non sempre reale

Il backend della proiezione non fornisce un rerank score. Mostrare 0 come se fosse uno score reale può confondere.

---

# 14. Benchmark / Evaluation Flow

## Entry

`POST /api/eval/run` → `run_evaluations()`

### Branch

```text
eval start
├── capture db id
├── per test case
│   ├── expected document presente
│   │   └── query
│   │       ├── retrieval metrics
│   │       ├── answer similarity
│   │       └── faithfulness judge
│   └── expected document mancante
│       └── Skipped
└── complete
```

### 🔴 P1 — Test suite hardcoded su 4 documenti specifici

`EVAL_TEST_CASES` contiene nomi reali fissi:

- `Ollama_Local_Inference_VRAM_Benchmark.md`
- `LanceDB_IVF_PQ_Quantization_Whitepaper.pdf`
- `Docling_Layout_AST_Specification.pdf`
- `FastAPI_Uvicorn_Orchestration_Guide.md`

Su un database diverso il benchmark può risultare quasi interamente `Skipped`.

Non è una suite generale del corpus attivo.

### 🔴 P1 — Benchmark usa active DB invece del DB catturato in più punti

Il job cattura `captured_db_id`, ma alcune verifiche intermedie usano `db_manager.get_documents()` / `get_active_info()`.

Se il DB cambia durante il benchmark:

```text
job → database A
user → activate B
worker → controlla documenti/modello di B
query → tabella A
```

Questo rende i risultati non riproducibili.

### 🟠 P2 — Caso in errore non aggiorna subito sempre lo stato del singolo test

Durante il polling, la riga relativa al test può restare “running” fino al completamento dell'intero job, anche se la funzione ha già registrato un errore internamente.

### 🟠 P2 — Tutti i test skipped ≠ benchmark realmente riuscito

Il job può chiudersi `completed` senza metriche utili se nessuno dei documenti attesi esiste.

**Fix:** stato `completed_no_valid_cases` oppure stato di warning esplicito.

### 🟠 P2 — Faithfulness judge dipende da LLM e JSON strict

Un errore del judge può far fallire il caso anche se retrieval e risposta sono corretti. Va riportato come `metric unavailable`, non confuso con un errore della RAG principale.

---

# 15. Telemetry Flow

## `stream_telemetry`

SSE continuo: il flusso base è valido.

### 🟡 P3 — Disconnect senza reconnessione

Il frontend apre `EventSource` e, su errore, può restare in stato di errore senza una riconnessione automatica fino a remount/riattivazione.

### 🟡 P3 — Snapshot aggregato, non cronologia di eventi

Il backend restituisce statistiche aggregate per fase.

La UI però presenta il contenuto come “telemetria real-time”, mentre non esiste una vera traccia evento-per-evento di ogni query/ingest.

### 🔵 Nota positiva

Gestione stop/cancel SSE e DELETE telemetria sono presenti.

---

# 16. Frontend Ingest Flow

## `IngestModal.tsx`

```text
select files/folder
├── filtro estensione PDF/JSON
├── POST multipart
│   ├── HTTP error → mostra errore
│   └── jobId
└── polling ricorsivo setTimeout
    ├── completed
    ├── failed
    ├── transient poll error → retry
    └── 30 min client timeout
```

### 🟠 P2 — 413 non viene diagnosticato chiaramente

Il backend può fornire `detail`, ma la UI deve farlo emergere esplicitamente. Il testo “Content Too Large” deve includere dimensione, limite applicato e sorgente dell'errore quando possibile.

### 🟡 P3 — Directory input con proprietà browser non standard

Esistono due `@ts-expect-error`, uno per `webkitdirectory` e uno per `directory`. Il build completo non è stato possibile in questo ambiente; il secondo potrebbe essere inutile/obsoleto rispetto alla definizione DOM usata dalla versione TypeScript installata.

---

# 17. Knowledge Nodes / Data view

## Frontend/backend type drift

`KnowledgeDocument.type` frontend non include `JSON`, mentre il backend può costruire `JSON`.

### 🟠 P2 — Contratto tipo documento incoerente

Può causare:

- filtro JSON che non si comporta come previsto
- rendering fallback
- errori TS futuri

### 🟠 P2 — Filtri UI incompleti

Sono presenti filtri per all/PDF/Markdown/YAML, mentre l'ingest attuale supporta PDF/JSON.

### 🟠 P2 — Claim “100% Parsed con Docling AST” non generalizzabile

I JSON non passano necessariamente da Docling. La label è quindi falsa per parte del corpus.

### 🟠 P2 — “Re-index with Docling” anche per JSON

Per un JSON la pipeline va in `ingest_file_unita`, non necessariamente in Docling.

---

# 18. Scalability / Data Flow

## `get_chunks()`

Recupera tutte le righe e poi esegue lo slicing Python:

```text
tabella.search().to_list()
→ tutti i chunk in RAM
→ [start:end]
```

### 🟠 P2 — Paginazione non reale

Con un corpus grande, `/api/chunks?page=N` carica comunque tutto in memoria.

Lo stesso problema compare in `get_documents()`, che materializza tutte le righe per raggruppare i documenti.

### 🟠 P2 — `get_stats()` richiama `get_documents()`

Quindi una chiamata alle statistiche può rileggere un intero corpus solo per contare i documenti.

Per l'obiettivo 8 GB RAM questo è un punto importante.

---

# 19. Config Drift

Sono presenti almeno tre fonti di default:

1. `webapp/backend/config.json`
2. `SETTINGS_DEFAULTS` in `main.py`
3. `frontend/src/data/defaultSettings.ts`

Esempi osservati:

| Campo | backend config.json | frontend default | backend SETTINGS_DEFAULTS |
|---|---|---|---|
| `chunkSize` | 600 | 512 | 512 |
| `splitMode` | sentences | ast | config/default mix |
| `logLevel` | DEBUG | INFO | INFO |
| `hostUrl` | http://localhost | 127.0.0.1 | altro default |

### 🟠 P2 — Drift dei default

Reset/config startup possono dare valori diversi a seconda del percorso usato.

### 🟠 P2 — fallback `caricaconfig()` vs DatabaseManager

Il fallback di `caricaconfig()` e il fallback di `DatabaseManager._load_storage_path()` non usano lo stesso default storico. Se il config file manca, due componenti possono divergere sul path.

---

# 20. Security / Robustness

## Aspetti positivi

- path relativi dei file upload normalizzati nel percorso batch.
- token API redatto in `/api/settings`.
- Bearer token centralizzato in frontend `apiFetch()`.
- validazione ZIP con path traversal e symlink check presente.
- delete DB verifica che il path sia dentro la base directory.

## Rischi

### 🟡 P3 — Token in localStorage

Il token frontend è in `localStorage`. Un XSS potrebbe leggerlo. Per un'app locale è un trade-off, ma va documentato.

### 🟡 P3 — token SSE nella query string

`EventSource` porta il token come `?token=...`. Query string e access log possono esporlo.

Per un'app locale il rischio è limitato, ma non è il pattern più sicuro.

---

# 21. Test Suite Audit

### 🟠 P2 — `tests/test_backend.py` usa `MagicMock` senza import corretto

Se eseguito integralmente, questo può produrre `NameError`.

### 🟠 P2 — `tests/test_fonte_path.py` patcha l'oggetto sbagliato

La pipeline reale usa `embedder_manager`; il test patcha un riferimento diverso. Il test quindi rischia di non verificare la vera integrazione.

### 🟡 P3 — test max payload con job asincroni potenzialmente lasciati attivi

Un test che avvia un ingest senza attenderne la fine può lasciare stato/temp file/lavori concorrenti tra test.

---

# 22. Dead / Unreachable / Redundant Code

## Confermati

1. `reindex_document()` — `else` dopo un check di esistenza già trasformato in `HTTPException`.
2. Richiesta a `/api/chunks/sample` in `VectorExplorerView.handleSelectAlgorithm()`: dati caricati ma non utilizzati per la proiezione successiva.
3. Variabili/import API ridondanti in alcuni componenti (`API_BASE_URL` quando si usa `apiFetch`, ecc.), da pulire dopo il fix funzionale.
4. Hardcoded demo answer/citations: ramo che sostituisce dati reali con dati dimostrativi.

Una ricerca testuale grezza sulle 137 definizioni Python non ha trovato funzioni completamente prive di riferimenti; ciò non dimostra che ogni ramo sia raggiungibile a runtime. Per questo le voci sopra sono state determinate con analisi del contesto e del flusso.

---

# 23. Expected Behavior vs Actual Behavior

## Ingest

**Atteso:** file → parse → chunk → embed → persist → FTS → stato completo.  
**Attuale:** un bug del chunker può impedire l'uscita; inoltre FTS può restare vecchio e metadata di ingest non vengono persistiti.

## Query

**Atteso:** query → embed/search → rerank → generation → citazioni reali.  
**Attuale:** retrieval può fallire e fare fallback; rerank/generation possono fallire senza esporre chiaramente la degradazione; UI contiene dati demo.

## Multi-DB

**Atteso:** ogni DB mantiene proprio schema + modello + dimensione + sorgenti.  
**Attuale:** modello e dimensione non sono completamente ancorati al DB target; import perde il modello; alcune funzioni usano `active_id` invece del DB catturato.

## Settings

**Atteso:** cambiare un'impostazione cambia il comportamento corrispondente.  
**Attuale:** alcune sono solo configurazione visualizzata/persistita, ma non applicata al runtime o alla pipeline reale.

## Vector Explorer

**Atteso:** scegliere algoritmo → proiettare vettori → filtrare/leggere punti reali.  
**Attuale:** UMAP non è installato per default, il caso 2 punti è invalido, il filtro globale non controlla il rendering reale, alcuni valori UI sono decorativi.

## Benchmark

**Atteso:** valutare il DB/corpus attivo in modo riproducibile.  
**Attuale:** suite hardcoded a 4 documenti, con riferimenti al DB attivo in un job che dovrebbe essere ancorato al DB catturato.

---

# 24. Recommended Architecture Direction

Ordine tecnico consigliato:

```text
1. Stabilizzare chunker e state machine ingest
2. Rendere database_id una dipendenza esplicita ovunque
3. Ancorare embedding model + dimensione al database
4. Persist metadata documento/chunk (ingestedAt, parser, source size, model)
5. Rendere FTS parte del commit logico di ingest
6. Separare errori reali da fallback degradati
7. Eliminare ogni mock/demo dal percorso operativo
8. Rendere benchmark parametrico sul corpus
9. Applicare realmente le Settings oppure eliminarle dalla UI
10. Rendere pagination / aggregation nativa LanceDB
11. Completare test d'integrazione con dipendenze reali
```

---

# 25. Final Priority List

### 🔴 P0 — da correggere prima di altro

1. Infinite loop `chunk_sezione()`.
2. Verifica dimensione embedding prima dell'upsert.
3. Legare embedding/model/dimensione al `database_id` target.
4. Correggere import/export metadata.
5. Rimuovere fake answer/citations dal QueryWorkbench.
6. Correggere FTS refresh dopo ingest.
7. Eliminare fallback di apertura tabella che trasforma corruzione in DB vuoto.

### 🟠 P2 — subito dopo

8. Query: conservare e visualizzare `detail`.
9. Query: separare retrieval failure / rerank failure / generation fallback.
10. Reindex: usare configurazione storica del documento.
11. Fix storagePath a runtime oppure dichiararlo “requires process restart”.
12. Uniformare settings frontend/backend.
13. Aggiungere `umap-learn` o cambiare default vector projection a PCA.
14. Fix UMAP n=2.
15. Parametrizzare benchmark e renderlo corpus-aware.
16. Ancorare benchmark al DB catturato per tutta la durata.
17. Persistere metadata documento.
18. Correggere `KnowledgeDocument.type` / filtri JSON.
19. Rendere pagination realmente paginata.
20. Verifica DB fisico al momento dell'activate.

### 🟡 P3 — qualità

21. Riconnessione SSE.
22. Eliminare “Voronoi 256” non implementato.
23. Distinguere coordinate proiettate da metriche.
24. Ripulire import/variabili frontend ridondanti.
25. Aggiornare test obsoleti/stale patch.
26. Rendere test ingest isolati e cleanup-safe.
27. Documentare token localStorage/SSE.
28. Unificare sorgenti dei default config.

---

# 26. Audit Completion / Stopping Point

**Mappatura function-first completata per i principali entry point applicativi:**

- Ingest
- Query
- Reindex
- Multi-database
- Document/Data view
- Vector Explorer
- Benchmark
- Settings
- Telemetry

**Rami importanti:** mappati fino a uscita/errore o bloccati da dipendenza mancante.  
**Dead-code scan:** completato a livello statico e contestuale.  
**Data/state flow:** completato per DB, chunk, embedding, query, eval e telemetry.  
**Runtime verification:** parziale per dipendenze mancanti; completa sui moduli puri disponibili.

**Non è stato modificato alcun file del progetto auditato.**

