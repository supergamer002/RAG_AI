# AUDIT DEL CODICE - SISTEMA RAG (Retrieval-Augmented Generation)

## 1. Sintesi Esecutiva

È stato condotto l'audit completo del codice sorgente del modulo RAG (`rag/`), sviluppato per l'architettura di retrieval-augmented generation in ambiente a risorse vincolate (8GB RAM, CPU-only/Ollama locale). Il codebase comprende i seguenti layer:
- **`rag/common/`**: Schema unificato e modelli dati (`Chunk`, `TipoFonte`).
- **`rag/ingest/`**: Adattatori per l'ingestion dati (PDF via Docling, JSON via unita' tematiche, chunker con gestione tabelle e overlap frasi).
- **`rag/index/`**: Embedder client HTTP verso Ollama (`qwen3-embedding:0.6b`) e datastore embedded LanceDB.
- **`rag/retrieve/`**: Search engine ibrido (Dense Vettoriale + Full-Text BM25 via Tantivy fusi con RRF) e Reranker cross-encoder (`BAAI/bge-reranker-v2-m3`).
- **`rag/generate/`**: Generatore di risposte via Ollama (`qwen3:8b`) con system prompt condizionato e citazioni vincolanti.

L'architettura complessiva risulta **estremamente solida, ben strutturata e aderente ai vincoli di memoria e computazione**. Il codice è scritto in Python moderno (type hints, dataclasses, docstring chiare in italiano).

---

## 2. Analisi Dettagliata per Componente

### 2.1 Common & Schema (`rag/common/schema.py`)
- **Punti di Forza**:
  - Utilizzo di `dataclass` e `Enum` fortemente tipizzati.
  - Generazione di `chunk_id` deterministico tramite hash SHA-256 limitato a 24 caratteri. Ciò garantisce l'idempotenza durante le operazioni di upsert/re-ingestion.
  - Funzione `stima_token` basata sul rapporto empirico $1 \text{ parola} \approx 1.3 \text{ token}$.
- **Rilievi / Raccomandazioni**:
  - `stima_token` è un'approssimazione adeguata per testi tecnici in italiano e inglese. Se in futuro dovesse servire un conteggio esatto per il contesto del LLM, si potrà integrare un tokenizer esatto (`tiktoken` o HuggingFace tokenizer).

### 2.2 Ingestion & Chunking (`rag/ingest/`)
- **Punti di Forza**:
  - **Gestione Tabelle**: Scelta eccellente di estrarre i blocchi di tabella (Markdown) separatamente ed emetterli come chunk singoli senza passare per lo splitter a frasi. Questo preserva l'integrità strutturale delle tabelle scientifiche/chimiche.
  - **Docling Integration (`docling_extract.py`)**: L'ottimizzazione `_ha_layer_testo()` mediante `pypdf` evita di eseguire l'OCR (molto pesante su CPU/RAM) su PDF nativamente digitali.
  - **Gestione Concorrenza/Memoria**: Controllo esplicito dei thread Torch/Docling (`RAG_DOCLING_THREADS`, default 2) per evitare thrashing di RAM.
  - **Esclusione Fonti Problematiche (`from_units.py`)**: Gestione esplicita di file corrotti/inaffidabili (`FILE_ESCLUSI = {"Calculus PDF.json"}`).

### 2.3 Index & Vector Store (`rag/index/`)
- **Punti di Forza**:
  - **`embed.py`**: Client HTTP verso Ollama implementato con `requests` senza dipendere dall'SDK ufficiale Ollama. Batching a dimensione controllata (default 32) per ottimizzare la latenza di rete e la memoria RAM.
  - **`store.py`**: Utilizzo di **LanceDB**, un vector store embedded ad alte prestazioni basato su PyArrow. L'utilizzo di `merge_insert` previene duplicazioni e garantisce idempotenza.
- **Rilievi / Raccomandazioni**:
  - L'indice FTS su LanceDB/Tantivy richiede la chiamata a `crea_indice_fulltext` dopo gli inserimenti massivi. Questo è gestito correttamente nella documentazione del modulo.

### 2.4 Retrieval & Search Engine (`rag/retrieve/`)
- **Punti di Forza**:
  - **Ricerca Ibrida (`hybrid_search.py`)**: Combinazione di ricerca vettoriale (dense) e BM25 (full-text) fusi tramite **Reciprocal Rank Fusion (RRF)** con $k=60$. RRF risolve brillantemente l'incomparabilità dei punteggi di scala tra Cosine Similarity e BM25.
  - **Reranking (`rerank.py`)**: Utilizzo di `BAAI/bge-reranker-v2-m3` con `use_fp16=True` per dimezzare l'occupazione di memoria su CPU/RAM. Caricamento *lazy* del modello per evitare spreco di memoria se il modulo viene solo importato.
- **Correzioni Applicate**:
  - È stato sistemato l'escape delle virgolette singole nell'espressione SQL `IN (...)` della ricerca ibrida per prevenire potenziali malformazioni della query in presenza di ID non standard.

### 2.5 Generazione Risposte (`rag/generate/`)
- **Punti di Forza**:
  - **System Prompt Antiallucinazione**: Il prompt impone regole ferree: rispondere *solo* in base al contesto fornito, citare la fonte nel formato `(Fonte, Sezione)` e ammettere esplicitamente quando il contesto non copre la risposta.
  - **Fallback Strategico**: Se la fase di recupero non produce chunk pertinenti, la funzione `rispondi` restituisce immediatamente una risposta di ripiego senza effettuare chiamate inutili al LLM.

---

## 3. Sicurezza, Prestazioni e Rispetto dei Vincoli (8GB RAM)

1. **Gestione della Memoria RAM**:
   - I modelli pesanti (Docling, BAAI Cross-Encoder) sono importati in modalità *lazy*.
   - Il batch size dell'embedder (32) e la dimensione vettoriale ridotta a 1024 consentono di operare con margine ben all'interno dei 8GB di RAM.
2. **Sicurezza & Resilienza**:
   - Chiamate HTTP protette con `timeout` espliciti (120s per embedder, 180s per generatore).
   - Sanificazione query SQL per filtri `IN` in LanceDB.

---

## 4. Verifica e Test di Regressione

È stata creata una suite di unit test ed integration test completa sotto la directory `tests/`:
- `tests/test_schema.py`: Test crea chunk, idempotenza ID, stima token.
- `tests/test_ingest.py`: Test chunking con frasi, conservazione tabelle, gestione file esclusi.
- `tests/test_retrieve_and_generate.py`: Test RRF fusion, ordinamento reranker, prompt generation, e test end-to-end LanceDB (upsert + hybrid search).

**Esito Test**: 11 passed in 3.74s.

---

## 5. Matrice delle Raccomandazioni Futuri Sviluppi

| Area | Priorità | Descrizione Raccomandazione |
| :--- | :--- | :--- |
| **Indexing** | Media | Automatizzare la ricreazione/aggiornamento dell'indice FTS in un job di background post-ingestion. |
| **Tokenizer** | Bassa | Se necessario determinare con precisione chirurgica il limite token per contesti LLM lunghi, valutare l'uso del tokenizer HuggingFace nativo di Qwen. |
| **Monitoring** | Bassa | Aggiungere un middleware di logging per tracciare la latenza media delle fasi: embedding, hybrid search, rerank, generation. |
