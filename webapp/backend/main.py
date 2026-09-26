"""Backend FastAPI per la webapp RAG.

Interfaccia tra il frontend React e la pipeline RAG (ingest, store, hybrid search,
rerank, generation, telemetry).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
import time
import os
import tempfile
import shutil
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel

from rag.common.monitoring import tracciatore_globale
from rag.common.schema import Chunk, TipoFonte, stima_token
from rag.index.db_manager import db_manager
from rag.index.embed import OllamaEmbedder
from rag.index.embed_manager import embedder_manager
from rag.index.store import upsert_chunks, conta_chunk
from rag.retrieve.hybrid_search import ricerca_ibrida, crea_indice_fulltext
from rag.retrieve.rerank import CrossEncoderReranker
from rag.generate.answer import rispondi, OllamaGenerator
from rag.ingest.from_units import ingest_file_unita, ingest_cartella_unita
from rag.ingest.docling_extract import ingest_pdf

CONFIG_PATH = Path("webapp/backend/config.json")


def caricaconfig() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "corsOrigins": "http://localhost:3000",
        "storagePath": "rag/index/store/lancedb",
        "tableName": "chunks",
        "ollamaUrl": "http://localhost:11434",
        "embeddingModel": "qwen3-embedding:0.6b",
        "crossEncoderModel": "BAAI/bge-reranker-v2-m3",
        "topKCandidates": 20,
        "topNRerank": 6,
    }


def salvaconfig(cfg: Dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


app = FastAPI(title="RAG AI Backend", version="1.0.0")

config = caricaconfig()

# Protezione API opzionale: se apiToken e' configurato, tutte le API operative
# richiedono Bearer token. Il rate limit resta attivo anche senza token.
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)
_RATE_EXEMPT = {"/", "/api/health", "/api/auth/status"}
_AUTH_EXEMPT = {"/", "/api/health", "/api/auth/status", "/api/settings/defaults"}

@app.middleware("http")
async def api_security(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)

    client = request.client.host if request.client else "unknown"
    now = time.time()
    limit = int(config.get("rateLimitMax", 100) or 100)
    bucket = _rate_buckets[client]
    while bucket and now - bucket[0] >= 60:
        bucket.popleft()
    if path not in _RATE_EXEMPT and len(bucket) >= limit:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=429, content={"detail": "Rate limit superato. Riprova tra poco."}, headers={"Retry-After": "60"})
    bucket.append(now)

    configured_token = str(config.get("apiToken") or "").strip()
    auth_exempt = path in _AUTH_EXEMPT or (path == "/api/settings" and request.method == "GET")
    if configured_token and not auth_exempt:
        auth = request.headers.get("authorization", "")
        supplied = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        # EventSource non supporta header custom: accetta token query solo per lo stream SSE.
        if path == "/api/telemetry/stream" and not supplied:
            supplied = request.query_params.get("token", "")
        if supplied != configured_token:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=401, content={"detail": "API token mancante o non valido."})

    return await call_next(request)

cors_origins = [orig.strip() for orig in config.get("corsOrigins", "http://localhost:3000").split(",") if orig.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins if cors_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inizializzazione risorse
# L'embedder e' ora gestito dinamicamente per database via embedder_manager
reranker = CrossEncoderReranker(modello=config.get("crossEncoderModel", "BAAI/bge-reranker-v2-m3"))
generatore_url = f"{config.get('ollamaUrl', 'http://localhost:11434').rstrip('/')}/api/chat"
generatore = OllamaGenerator(url=generatore_url)

ingestion_jobs: Dict[str, Dict[str, Any]] = {}
_ingestion_tasks: set[asyncio.Task] = set()
MAX_INGEST_FILES = 500
MAX_INGEST_FILE_BYTES = 250 * 1024 * 1024
MAX_INGEST_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
SUPPORTED_INGEST_EXTENSIONS = {".pdf", ".json"}


class QueryRequest(BaseModel):
    query: str
    topK: Optional[int] = 20
    topN: Optional[int] = 6
    searchMode: Optional[str] = "hybrid"  # "hybrid" | "dense" | "sparse"
    hybridAlpha: Optional[float] = 0.7
    enableRerank: Optional[bool] = True


def mappa_chunk_item(c: Dict[str, Any], idx: int, initial_rank_map: Dict[str, int]) -> Dict[str, Any]:
    cid = c.get("chunk_id", str(idx))
    init_rank = initial_rank_map.get(cid, idx)
    rank_delta = init_rank - idx

    testo = c.get("testo", "")
    tipo_str = c.get("tipo_fonte", "libro").lower()
    tipo_map = {
        "libro": "Libro",
        "articolo": "Ricerca",
        "video": "Manuale",
    }
    doc_type = tipo_map.get(tipo_str, "Libro")

    return {
        "id": cid,
        "chunkNum": idx + 1,
        "docTitle": c.get("fonte_titolo", "Sconosciuto"),
        "docType": doc_type,
        "section": c.get("sezione", "Sezione Generale"),
        "text": testo,
        "highlightSnippet": testo[:160] + "..." if len(testo) > 160 else testo,
        "denseScore": c.get("denseScore", 0.0),
        "bm25Score": c.get("bm25Score", 0.0),
        "rerankScore": c.get("rerankScore", 0.0),
        "rankDelta": rank_delta,
        "tokenCount": stima_token(testo),
        "overlapPct": c.get("overlapPct"),
        "embeddingModel": c.get("embeddingModel") or config.get("embeddingModel", "qwen3-embedding:0.6b"),
        "dimensions": (f"{len(c.get("vector", []))}d" if c.get("vector") is not None and len(c.get("vector", [])) else None),
        "charOffset": c.get("posizione", ""),
        "timestamp": c.get("ingestedAt", ""),
        "vectorTable": config.get("tableName", "chunks"),
        "parser": c.get("parser", ""),
    }


@app.get("/")
def read_root():
    return {"status": "ok", "service": "RAG AI Backend"}


@app.get("/api/health")
def get_health():
    ollama_ok = False
    ollama_detail = "Non raggiungibile"
    try:
        import requests
        r = requests.get(config.get("ollamaUrl", "http://localhost:11434"), timeout=2)
        if r.status_code == 200:
            ollama_ok = True
            ollama_detail = "OK"
            # Verifica modello embedding
            try:
                emb_model = config.get("embeddingModel", "qwen3-embedding:0.6b")
                # Chiamata minima a /api/embed per verificare modello e connessione
                emb_res = requests.post(
                    f"{config.get('ollamaUrl', 'http://localhost:11434').rstrip('/')}/api/embed",
                    json={"model": emb_model, "input": "health check"},
                    timeout=2
                )
                if emb_res.status_code != 200:
                    ollama_ok = False
                    ollama_detail = f"Modello embedding {emb_model} non disponibile ({emb_res.status_code})"
            except Exception as e:
                ollama_ok = False
                ollama_detail = f"Errore verifica embedding: {str(e)}"
        else:
            ollama_detail = f"Risposta HTTP {r.status_code}"
    except Exception as e:
        ollama_detail = f"Errore connessione: {str(e)}"

    lancedb_ok = True
    try:
        tabella = db_manager.get_active_table()
        tabella.count_rows()
    except Exception:
        lancedb_ok = False

    return {
        "fastapi": True,
        "lancedb": lancedb_ok,
        "ollama": ollama_ok,
        "ollama_detail": ollama_detail,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/stats")
def get_stats():
    tabella = db_manager.get_active_table()
    doc_list = get_documents()
    active_info = db_manager.get_active_info()
    storage_bytes = 0
    db_path = Path(active_info["path"])
    if db_path.exists():
        try:
            storage_bytes = sum(p.stat().st_size for p in db_path.rglob("*") if p.is_file())
        except OSError:
            storage_bytes = None
    return {
        "chunks": tabella.count_rows(),
        "documents": len(doc_list),
        "databases": len(db_manager.list_databases()),
        "storageBytes": storage_bytes,
        "activeDatabase": active_info,
    }


class CreateDatabaseRequest(BaseModel):
    name: str


@app.get("/api/databases")
def get_databases():
    return {
        "activeDatabase": db_manager.active_id,
        "databases": db_manager.list_databases(),
    }


@app.post("/api/databases")
def create_database(req: CreateDatabaseRequest):
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="Nome database non valido")
    return db_manager.create_database(req.name.strip())


@app.post("/api/databases/{database_id}/activate")
def activate_database(database_id: str):
    try:
        res = db_manager.activate_database(database_id)
        return {"status": "activated", "database": res}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/api/databases/{database_id}")
def rename_database(database_id: str, req: CreateDatabaseRequest):
    try:
        return db_manager.rename_database(database_id, req.name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/databases/{database_id}")
def delete_database(database_id: str):
    try:
        ok = db_manager.delete_database(database_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Database non trovato")
        return {"status": "deleted", "databaseId": database_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/databases/{database_id}/export")
def export_database(database_id: str):
    try:
        zip_path = db_manager.export_database(database_id)
        return FileResponse(
            path=zip_path,
            filename=f"database_{database_id}.zip",
            media_type="application/zip",
            background=BackgroundTask(lambda p: Path(p).unlink(missing_ok=True), zip_path),
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/databases/import")
def import_database(file: UploadFile = File(...), name: Optional[str] = Form(None)):
    temp_dir = Path("rag/index/temp_uploads")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_zip = temp_dir / f"upload_{uuid.uuid4().hex}.zip"

    try:
        # Non usare mai il nome file fornito dal client come percorso locale.
        with temp_zip.open("wb") as f:
            shutil.copyfileobj(file.file, f)

        original_name = file.filename or "database.zip"
        db_name = (name or Path(original_name).stem).strip()
        if not db_name:
            raise HTTPException(status_code=400, detail="Nome database non valido")

        return db_manager.import_database(temp_zip, db_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        try:
            temp_zip.unlink(missing_ok=True)
        except OSError:
            pass


@app.post("/api/query")
def execute_query(req: QueryRequest):
    query = (req.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="La query non puo' essere vuota.")

    try:
        tabella = db_manager.get_active_table()
        if tabella.count_rows() == 0:
            return {"answer": "", "chunks": []}

        risultato = _esegui_query_su_tabella(req, tabella)
        risultato.pop("queryEmbedding", None)
        return risultato
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("Query RAG fallita")
        raise HTTPException(
            status_code=503,
            detail=f"Pipeline RAG non disponibile: {type(e).__name__}: {e}",
        ) from e


def _format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    units = ["KB", "MB", "GB", "TB"]
    value = float(size_bytes)
    for unit in units:
        value /= 1024.0
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
    return f"{value:.2f} TB"


@app.get("/api/documents")
def get_documents():
    tabella = db_manager.get_active_table()
    totale_righe = tabella.count_rows()
    if totale_righe == 0:
        return []

    righe = tabella.search().select(["chunk_id", "fonte_titolo", "tipo_fonte", "sezione", "fonte_path"]).to_list()
    per_doc: Dict[str, Dict[str, Any]] = {}
    active_info = db_manager.get_active_info()
    embedding_dim = active_info.get("dimension")
    table_name = config.get("tableName", "chunks")

    for r in righe:
        titolo = r.get("fonte_titolo", "Documento")
        path_str = r.get("fonte_path", "")
        doc_key = path_str or titolo
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{active_info['id']}::{doc_key}"))

        if doc_id not in per_doc:
            ext = Path(path_str).suffix.upper().replace(".", "") if path_str else "PDF"
            doc_type = ext if ext in ["PDF", "DOCX", "PYTHON", "YAML", "MARKDOWN", "JSON"] else "PDF"

            per_doc[doc_id] = {
                "id": doc_id,
                "name": titolo,
                "sourcePath": path_str or titolo,
                "type": doc_type,
                "fileSize": None,
                "chunksCount": 0,
                "sectionsSet": set(),
                "status": "Indicizzato",
                "indexedDate": "",
                "vectorTable": table_name,
                "embeddingDim": embedding_dim,
                "doclingAstNodes": None,
            }

        source_candidate = None
        if path_str:
            candidate = Path(path_str)
            if not candidate.is_absolute():
                candidate = Path(active_info["path"]) / candidate
            source_candidate = candidate
        if source_candidate and source_candidate.exists() and source_candidate.is_file():
            try:
                per_doc[doc_id]["fileSize"] = _format_file_size(source_candidate.stat().st_size)
                per_doc[doc_id]["indexedDate"] = time.strftime("%Y-%m-%d", time.localtime(source_candidate.stat().st_mtime))
            except OSError:
                pass

        per_doc[doc_id]["chunksCount"] += 1
        if r.get("sezione"):
            per_doc[doc_id]["sectionsSet"].add(r["sezione"])

    docs = []
    for doc in per_doc.values():
        doc["sectionsCount"] = len(doc.pop("sectionsSet"))
        docs.append(doc)

    return docs


@app.post("/api/documents/{document_id}/reindex")
def reindex_document(document_id: str, background_tasks: BackgroundTasks):
    docs = get_documents()
    target_doc = next((d for d in docs if d["id"] == document_id), None)
    if not target_doc:
        raise HTTPException(status_code=404, detail="Documento non trovato per il re-indexing")

    source_path = target_doc.get("sourcePath") or target_doc.get("name")
    target_path = Path(source_path)
    if not target_path.is_absolute():
        target_path = Path(db_manager.get_info_for_id(db_manager.active_id)["path"]) / target_path
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=409, detail="Sorgente originale non disponibile per il re-indexing")

    job_id = str(uuid.uuid4())
    captured_db_id = db_manager.active_id
    ingestion_jobs[job_id] = {
        "status": "pending", "chunksCreated": 0, "filesTotal": 1, "filesProcessed": 0,
        "filesFailed": 0, "databaseId": captured_db_id, "error": None, "errors": [],
        "currentFile": target_doc["name"], "startedAt": time.time(), "updatedAt": time.time(),
    }

    if target_path.exists():
        _schedule_ingestion_task(
            esegui_ingestion_job(job_id, target_path, target_path.is_dir(), 512, 15, True, captured_db_id)
        )
    else:
        tabella = db_manager.get_active_table()
        background_tasks.add_task(crea_indice_fulltext, tabella)
        ingestion_jobs[job_id]["status"] = "completed"

    return {
        "jobId": job_id,
        "documentId": document_id,
        "databaseId": captured_db_id,
        "message": f"Re-indexing avviato per {target_doc['name']}",
    }


@app.get("/api/chunks")
def get_chunks(
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    fonte_titolo: Optional[str] = None,
    tipo_fonte: Optional[str] = None,
    sezione: Optional[str] = None,
):
    tabella = db_manager.get_active_table()
    search_builder = tabella.search()
    where_clauses = []
    if fonte_titolo:
        where_clauses.append(f"fonte_titolo = '{fonte_titolo.replace('\'', '\'\'')}'")
    if tipo_fonte:
        where_clauses.append(f"tipo_fonte = '{tipo_fonte.replace('\'', '\'\'')}'")
    if sezione:
        where_clauses.append(f"sezione = '{sezione.replace('\'', '\'\'')}'")

    if where_clauses:
        search_builder = search_builder.where(" AND ".join(where_clauses))

    tutti = search_builder.to_list()
    total = len(tutti)
    start = (page - 1) * pageSize
    end = start + pageSize
    slice_righe = tutti[start:end]

    mapped = [mappa_chunk_item(r, idx + start, {}) for idx, r in enumerate(slice_righe)]
    return {
        "items": mapped,
        "total": total,
        "page": page,
        "pageSize": pageSize,
    }


@app.get("/api/chunks/{chunk_id}/vector")
def get_chunk_vector(chunk_id: str):
    tabella = db_manager.get_active_table()
    cid_escaped = chunk_id.replace("'", "''")
    righe = tabella.search().where(f"chunk_id = '{cid_escaped}'").limit(1).to_list()
    if not righe:
        raise HTTPException(status_code=404, detail="Chunk non trovato")

    vector = righe[0].get("vector", [])
    if hasattr(vector, "tolist"):
        vector = vector.tolist()

    return {
        "chunkId": chunk_id,
        "dimension": len(vector),
        "vector": [round(float(v), 5) for v in vector[:100]],
        "fullVector": [float(v) for v in vector],
    }


@app.get("/api/chunks/sample")
def get_chunks_sample(sampleSize: int = Query(500, ge=1, le=1000)):
    """Restituisce un campione di chunk per la proiezione vettoriale.
    Include tutti i metadati necessari per evitare chiamate multiple.
    """
    tabella = db_manager.get_active_table()
    righe = tabella.search().limit(sampleSize).to_list()

    mapped = [mappa_chunk_item(r, idx, {}) for idx, r in enumerate(righe)]
    return {
        "items": mapped,
        "total": len(righe),
    }


def _schedule_ingestion_task(coro) -> None:
    task = asyncio.create_task(coro)
    _ingestion_tasks.add(task)
    task.add_done_callback(_ingestion_tasks.discard)


def _esegui_ingestion_job_sync(
    job_id: str,
    filepath: Path,
    is_directory: bool,
    chunk_tokens: int = 512,
    overlap_pct: int = 15,
    ocr_enabled: bool = True,
    database_id: Optional[str] = None,
):
    ingestion_jobs[job_id]["status"] = "in_progress"

    try:
        if is_directory:
            chunks = ingest_cartella_unita(
                filepath,
                target_token=chunk_tokens,
                overlap_ratio=overlap_pct / 100.0,
            )
        elif filepath.suffix.lower() == ".json":
            chunks = ingest_file_unita(
                filepath,
                target_token=chunk_tokens,
                overlap_ratio=overlap_pct / 100.0,
            )
        else:
            chunks = ingest_pdf(
                filepath,
                TipoFonte.LIBRO,
                target_token=chunk_tokens,
                overlap_ratio=overlap_pct / 100.0,
                ocr_enabled=ocr_enabled,
            )

        if chunks:
            # Per gli upload web conserviamo nel metadata un path relativo al database.
            # Cosi' il re-index continua a funzionare anche dopo export/import.
            if not is_directory:
                try:
                    db_root = Path(db_manager.get_info_for_id(database_id or db_manager.active_id)["path"]).resolve()
                    source_root = db_root / "sources"
                    source_root.mkdir(parents=True, exist_ok=True)
                    source_path = filepath.resolve()
                    relative_source = source_path.relative_to(source_root.resolve())
                    for chunk in chunks:
                        chunk.fonte_path = str(Path("sources") / relative_source)
                        chunk.ricalcola_id()
                except (KeyError, OSError, ValueError):
                    pass
            target_db_id = database_id or db_manager.active_id
            tabella = db_manager.get_table_for_db(target_db_id)
            _indicizza_chunks_incrementale(tabella, chunks, ingestion_jobs[job_id])
            crea_indice_fulltext(tabella)

        ingestion_jobs[job_id]["status"] = "completed"
        ingestion_jobs[job_id]["chunksCreated"] = len(chunks)
        ingestion_jobs[job_id]["filesProcessed"] = 1
        ingestion_jobs[job_id]["currentFile"] = None
        ingestion_jobs[job_id]["updatedAt"] = time.time()
    except Exception as e:
        ingestion_jobs[job_id]["status"] = "failed"
        ingestion_jobs[job_id]["error"] = str(e)
        ingestion_jobs[job_id]["filesFailed"] = 1
        ingestion_jobs[job_id]["currentFile"] = None
        ingestion_jobs[job_id]["updatedAt"] = time.time()



async def esegui_ingestion_job(*args, **kwargs):
    await asyncio.to_thread(_esegui_ingestion_job_sync, *args, **kwargs)




def _indicizza_chunks_incrementale(
    tabella: Any,
    chunks: Sequence[Chunk],
    job: Dict[str, Any],
    batch_size: int = 32,
) -> int:
    """Genera embedding e salva i chunk a piccoli batch.

    In questo modo un errore Ollama dopo N batch non annulla il lavoro già
    scritto in LanceDB: i chunk gia' indicizzati restano disponibili.
    """
    totale = 0
    for start in range(0, len(chunks), batch_size):
        batch = list(chunks[start:start + batch_size])
        if not batch:
            continue
        try:
            # Use embedder tied to the active database
            active_info = db_manager.get_active_info()
            emb_model = active_info.get("embeddingModel", config.get("embeddingModel", "qwen3-embedding:0.6b"))
            emb_url = f"{config.get('ollamaUrl', 'http://localhost:11434').rstrip('/')}/api/embed"
            current_embedder = embedder_manager.get_embedder(emb_model, emb_url)

            embeddings = current_embedder.embed([c.testo for c in batch])
            inseriti = upsert_chunks(tabella, batch, embeddings)
        except Exception as exc:
            raise RuntimeError(
                f"Embedding/indicizzazione fallita al batch "
                f"{start + 1}-{start + len(batch)} di {len(chunks)}: {exc}"
            ) from exc
        totale += inseriti
        job["chunksCreated"] = job.get("chunksCreated", 0) + inseriti
        job["updatedAt"] = time.time()
    return totale


def esegui_ingestion_batch_job(
    job_id: str,
    filepaths: Sequence[Path],
    batch_root: Path,
    chunk_tokens: int = 512,
    overlap_pct: int = 15,
    ocr_enabled: bool = True,
    database_id: Optional[str] = None,
):
    """Processa in sequenza tutti i file di un upload singolo o di una cartella.

    Un file fallito non blocca gli altri. Il job termina ``completed`` se almeno
    un file e' stato processato; se tutti falliscono termina ``failed``.
    """
    job = ingestion_jobs[job_id]
    job["status"] = "in_progress"
    job["startedAt"] = job.get("startedAt") or time.time()
    job["updatedAt"] = time.time()
    target_db_id = database_id or db_manager.active_id

    try:
        db_root = Path(db_manager.get_info_for_id(target_db_id)["path"]).resolve()
        source_root = db_root / "sources"
        tabella = db_manager.get_table_for_db(target_db_id)
    except Exception as exc:
        job["status"] = "failed"
        job["error"] = f"Impossibile aprire il database target: {exc}"
        shutil.rmtree(batch_root, ignore_errors=True)
        return

    total_chunks = 0
    errors: List[Dict[str, str]] = []

    for filepath in filepaths:
        job["currentFile"] = str(filepath.relative_to(batch_root))
        job["updatedAt"] = time.time()
        try:
            suffix = filepath.suffix.lower()
            if suffix == ".json":
                chunks = ingest_file_unita(filepath, target_token=chunk_tokens, overlap_ratio=overlap_pct / 100.0)
            elif suffix == ".pdf":
                chunks = ingest_pdf(
                    filepath,
                    TipoFonte.LIBRO,
                    target_token=chunk_tokens,
                    overlap_ratio=overlap_pct / 100.0,
                    ocr_enabled=ocr_enabled,
                )
            else:
                raise ValueError(f"Formato non supportato: {suffix or '(nessuna estensione)'}")

            # Il path indicizzato e' relativo al database, mai assoluto.
            relative_source = filepath.resolve().relative_to(source_root.resolve())
            for chunk in chunks:
                chunk.fonte_path = str(Path("sources") / relative_source).replace("\\", "/")
                chunk.ricalcola_id()

            if chunks:
                indicizzati = _indicizza_chunks_incrementale(tabella, chunks, job)
                total_chunks += indicizzati

            job["filesProcessed"] += 1
            job["chunksCreated"] = total_chunks
            job["currentFile"] = None
            job["updatedAt"] = time.time()
        except Exception as exc:
            job["filesFailed"] += 1
            errors.append({"file": str(filepath.relative_to(batch_root)), "error": str(exc)})
            job["errors"] = errors

        try:
            crea_indice_fulltext(tabella)
        except Exception as exc:
            errors.append({"file": "<fts>", "error": str(exc)})
            job["errors"] = errors

    job["chunksCreated"] = total_chunks
    if job["filesProcessed"] == 0 or total_chunks == 0:
        job["status"] = "failed"
        job["currentFile"] = None
        job["updatedAt"] = time.time()
        job["error"] = "Nessun chunk è stato generato dai file elaborati. Controlla i contenuti dei documenti." if total_chunks == 0 else "Nessun file e' stato indicizzato. Controlla gli errori del job."
    else:
        job["status"] = "completed"
        job["currentFile"] = None
        job["updatedAt"] = time.time()
        if errors:
            job["error"] = f"{len(errors)} file/eventi hanno prodotto errori; gli altri file sono stati processati."

    # Le sorgenti restano nel database per permettere il re-index.

@app.post("/api/ingest")
async def process_ingest(
    background_tasks: BackgroundTasks,
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None),
    path: Optional[str] = Form(None),
    chunkSize: Optional[int] = Form(512),
    chunkOverlap: Optional[int] = Form(15),
    ocrEnabled: Optional[bool] = Form(True),
    relativePaths: Optional[str] = Form(None),
):
    """Avvia ingest di uno o piu' file caricati dal browser.

    Il campo ``files`` supporta anche la selezione di un'intera cartella
    tramite ``webkitdirectory``: il browser invia tutti i file e, quando
    disponibile, ``webkitRelativePath`` conserva la struttura delle
    sottocartelle.

    ``path`` resta intenzionalmente vietato via HTTP: non si accettano path
    arbitrari del filesystem del server.
    """
    uploaded: List[UploadFile] = list(files or [])
    if file is not None and not uploaded:
        uploaded = [file]

    if path:
        raise HTTPException(status_code=400, detail="L'ingest via API richiede il caricamento dei file.")
    if not uploaded:
        raise HTTPException(status_code=400, detail="Seleziona almeno un file o una cartella.")

    # Enforce maxPayloadMB from config
    total_payload_size = 0
    for f in uploaded:
        # UploadFile has a file object with a seekable stream
        f.file.seek(0, os.SEEK_END)
        total_payload_size += f.file.tell()
        f.file.seek(0)

    max_mb = config.get("maxPayloadMB", 50)
    if total_payload_size > max_mb * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"La dimensione totale del payload ({total_payload_size // (1024*1024)} MB) supera il limite massimo configurato di {max_mb} MB."
        )

    if len(uploaded) > MAX_INGEST_FILES:
        raise HTTPException(status_code=413, detail=f"Troppi file: massimo {MAX_INGEST_FILES} per ingest.")

    captured_db_id = db_manager.active_id
    try:
        db_root = Path(db_manager.get_info_for_id(captured_db_id)["path"]).resolve()
        source_root = db_root / "sources"
        source_root.mkdir(parents=True, exist_ok=True)
    except (KeyError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Impossibile preparare lo storage delle sorgenti: {exc}") from exc

    job_id = str(uuid.uuid4())
    ingestion_jobs[job_id] = {
        "status": "pending",
        "chunksCreated": 0,
        "filesTotal": len(uploaded),
        "filesProcessed": 0,
        "filesFailed": 0,
        "databaseId": captured_db_id,
        "error": None,
        "errors": [],
        "currentFile": None,
        "startedAt": time.time(),
        "updatedAt": time.time(),
    }

    batch_root = source_root / f"upload_{uuid.uuid4().hex}"
    batch_root.mkdir(parents=True, exist_ok=True)

    saved_files: List[Path] = []
    total_bytes = 0
    try:
        try:
            relative_map = json.loads(relativePaths) if relativePaths else []
            if not isinstance(relative_map, list):
                relative_map = []
        except json.JSONDecodeError as exc:
            shutil.rmtree(batch_root, ignore_errors=True)
            raise HTTPException(status_code=400, detail=f"relativePaths non valido: {exc}") from exc

        if relative_map and len(relative_map) != len(uploaded):
            shutil.rmtree(batch_root, ignore_errors=True)
            raise HTTPException(status_code=400, detail="Numero di relativePaths diverso dal numero di file.")

        for index, item in enumerate(uploaded):
            # webkitRelativePath e' disponibile nei browser moderni quando
            # l'input usa webkitdirectory. Non fidarsi comunque del path:
            # vengono conservati solo componenti normali e senza '..'.
            raw_relative = (relative_map[index] if relative_map else None) or getattr(item, "filename", None) or "upload.bin"
            relative = Path(str(raw_relative).replace("\\", "/"))
            safe_parts = [part for part in relative.parts if part not in ("", ".", "..")]
            if not safe_parts:
                safe_parts = [f"upload_{uuid.uuid4().hex}.bin"]
            safe_name = Path(*safe_parts)
            if safe_name.is_absolute() or ".." in safe_name.parts:
                raise HTTPException(status_code=400, detail=f"Percorso file non valido: {raw_relative}")

            suffix = Path(str(raw_relative)).suffix.lower()
            if suffix not in SUPPORTED_INGEST_EXTENSIONS:
                continue
            declared_size = getattr(item, "size", None)
            if isinstance(declared_size, int) and declared_size > MAX_INGEST_FILE_BYTES:
                raise HTTPException(status_code=413, detail=f"File troppo grande: {raw_relative}")
            target_path = batch_root / safe_name
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                target_path = target_path.with_name(f"{target_path.stem}_{uuid.uuid4().hex[:8]}{target_path.suffix}")

            with target_path.open("wb") as out:
                shutil.copyfileobj(item.file, out)
            size = target_path.stat().st_size
            if size > MAX_INGEST_FILE_BYTES:
                target_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"File troppo grande: {raw_relative}")
            total_bytes += size
            if total_bytes > MAX_INGEST_TOTAL_BYTES:
                raise HTTPException(status_code=413, detail=f"Dimensione totale ingest superiore a {MAX_INGEST_TOTAL_BYTES // (1024*1024)} MB")
            saved_files.append(target_path)
    except HTTPException:
        shutil.rmtree(batch_root, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(batch_root, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Impossibile salvare i file caricati: {exc}") from exc

    if not saved_files:
        shutil.rmtree(batch_root, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Nessun file supportato trovato. Sono supportati PDF e JSON.")

    ingestion_jobs[job_id]["filesTotal"] = len(saved_files)
    _schedule_ingestion_task(asyncio.to_thread(
        esegui_ingestion_batch_job, job_id, saved_files, batch_root,
        chunkSize or 512, chunkOverlap or 15, bool(ocrEnabled), captured_db_id
    ))

    return {
        "jobId": job_id,
        "status": "pending",
        "filesTotal": len(saved_files),
        "databaseId": captured_db_id,
        "message": f"Ingest avviato per {len(saved_files)} file.",
    }


@app.get("/api/ingest/status/{job_id}")
def get_ingest_status(job_id: str):
    if job_id not in ingestion_jobs:
        raise HTTPException(status_code=404, detail="Job non trovato")
    job = ingestion_jobs[job_id]
    job["ageSeconds"] = max(0, int(time.time() - job.get("startedAt", time.time())))
    job["lastUpdateAgeSeconds"] = max(0, int(time.time() - job.get("updatedAt", time.time())))
    return job


def _build_telemetry_snapshot() -> List[Dict[str, Any]]:
    """Costruisce uno snapshot coerente della telemetria aggregata."""
    stats = tracciatore_globale.get_statistiche()
    logs: List[Dict[str, Any]] = []

    comp_map = {
        "embedding": "Ollama",
        "hybrid_search": "LanceDB",
        "rerank": "CrossEncoder",
        "generation": "Ollama",
    }

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    for idx, (fase, data) in enumerate(stats.items(), start=1):
        logs.append({
            "id": f"telemetry-{fase}",
            "timestamp": timestamp,
            "level": "INFO",
            "component": comp_map.get(fase, "FastAPI"),
            "message": f"Fase '{fase}' completata ({int(data['conteggio'])} chiamate)",
            "durationMs": int(data["media_s"] * 1000),
        })

    if not logs:
        logs.append({
            "id": "telemetry-system",
            "timestamp": timestamp,
            "level": "INFO",
            "component": "FastAPI",
            "message": "Sistema RAG pronto e in ascolto.",
            "durationMs": 0,
        })

    return logs


@app.get("/api/telemetry")
def get_telemetry():
    return _build_telemetry_snapshot()


@app.get("/api/telemetry/stream")
async def stream_telemetry():
    """Stream SSE di snapshot telemetrici, con chiusura automatica alla disconnessione."""
    async def event_generator():
        last_payload: str | None = None
        try:
            while True:
                payload = json.dumps(_build_telemetry_snapshot(), ensure_ascii=False)
                if payload != last_payload:
                    yield f"event: telemetry\ndata: {payload}\n\n"
                    last_payload = payload
                else:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(1)
        except (asyncio.CancelledError, GeneratorExit):
            return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/api/telemetry")
def clear_telemetry():
    tracciatore_globale._misure.clear()
    return {"status": "cleared", "message": "Buffer telemetria svuotato con successo"}


@app.post("/api/system/restart")
def restart_runtime():
    """Ricarica configurazione e risorse RAG nel processo FastAPI corrente.

    Questo endpoint NON riavvia il processo FastAPI né invia segnali al worker:
    aggiorna solamente gli oggetti runtime che dipendono dalla configurazione.
    """
    global config, reranker, generatore
    config = caricaconfig()
    # Aggiorna il DatabaseManager per riflettere eventuali modifiche a storagePath
    db_manager._load_registry()
    # L'embedder e' ora gestito dinamicamente per database via embedder_manager
    # Non è più necessaria l'istanza globale embedder a livello di modulo
    reranker = CrossEncoderReranker(modello=config.get("crossEncoderModel", "BAAI/bge-reranker-v2-m3"))
    generatore_url = f"{config.get('ollamaUrl', 'http://localhost:11434').rstrip('/')}/api/chat"
    generatore = OllamaGenerator(url=generatore_url)
    return {
        "status": "reloaded",
        "message": "Configurazione e risorse RAG ricaricate nel processo FastAPI corrente",
    }


class VectorProjectRequest(BaseModel):
    method: Optional[str] = "umap"
    sampleSize: Optional[int] = 500


@app.post("/api/vectors/project")
def project_vectors(req: VectorProjectRequest):
    tabella = db_manager.get_active_table()
    sample_size = req.sampleSize or 500
    method = (req.method or "umap").lower().replace("-", "").replace("_", "")

    if method not in {"umap", "tsne", "pca"}:
        raise HTTPException(
            status_code=400,
            detail="Metodo di proiezione non valido. Usare: umap, tsne o pca.",
        )

    righe = tabella.search().limit(sample_size).to_list()
    if not righe:
        return {"method": method, "points": []}

    vectors = []
    for r in righe:
        vec = r.get("vector", [])
        if hasattr(vec, "tolist"):
            vec = vec.tolist()
        vectors.append(vec)

    import numpy as np
    X = np.array(vectors, dtype=np.float32)

    if X.shape[0] >= 2 and X.shape[1] >= 2:
        if method == "umap":
            try:
                from umap import UMAP
            except ImportError as exc:
                raise HTTPException(
                    status_code=503,
                    detail="UMAP non disponibile: installare la dipendenza 'umap-learn'.",
                ) from exc

            # UMAP requires n_neighbors < number of samples. Keep the value
            # useful for both small and large projections while remaining
            # deterministic for reproducible UI results.
            n_neighbors = min(15, X.shape[0] - 1)
            reducer = UMAP(
                n_components=2,
                n_neighbors=max(2, n_neighbors),
                min_dist=0.1,
                metric="cosine",
                random_state=42,
            )
            coords = reducer.fit_transform(X)
        elif method == "tsne":
            from sklearn.manifold import TSNE
            perplexity = min(30, max(2, X.shape[0] - 1))
            # Current scikit-learn requires perplexity < n_samples.
            perplexity = min(perplexity, X.shape[0] - 1)
            tsne = TSNE(n_components=2, perplexity=perplexity, random_state=42)
            coords = tsne.fit_transform(X)
        elif method == "pca":
            from sklearn.decomposition import PCA
            pca = PCA(n_components=2, random_state=42)
            coords = pca.fit_transform(X)
        else:
            raise HTTPException(
                status_code=400,
                detail="Metodo di proiezione non valido. Usare: umap, tsne o pca.",
            )

        # Scale coordinates into percentage range 10..90 for UI canvas rendering
        x_min, x_max = coords[:, 0].min(), coords[:, 0].max()
        y_min, y_max = coords[:, 1].min(), coords[:, 1].max()
        x_norm = (coords[:, 0] - x_min) / (x_max - x_min + 1e-6) * 70.0 + 15.0
        y_norm = (coords[:, 1] - y_min) / (y_max - y_min + 1e-6) * 70.0 + 15.0

        n_clusters = min(4, X.shape[0])
        from sklearn.cluster import KMeans
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
        labels = kmeans.fit_predict(X)
    else:
        x_norm = np.array([50.0] * len(righe))
        y_norm = np.array([50.0] * len(righe))
        labels = np.array([0] * len(righe))

    points = []
    for idx, r in enumerate(righe):
        cid = r.get("chunk_id", str(idx))
        label_idx = int(labels[idx]) if idx < len(labels) else 0

        points.append({
            "id": cid,
            "title": r.get("fonte_titolo", "Documento"),
            "section": r.get("sezione", "Generale"),
            # KMeans provides numeric cluster membership only; do not attach
            # invented semantic labels to the clusters.
            "clusterId": label_idx,
            "cluster": f"Cluster {label_idx}",
            "x": round(float(x_norm[idx]), 2),
            "y": round(float(y_norm[idx]), 2),
            "method": method,
        })

    return {"method": method, "sampleSize": len(points), "dimensions": int(X.shape[1]), "points": points}


eval_results_cache: List[Dict[str, Any]] = []
eval_jobs: Dict[str, Dict[str, Any]] = {}
_eval_tasks: set[asyncio.Task] = set()

EVAL_TEST_CASES: List[Dict[str, str]] = [
    {
        "id": "tc-1",
        "query": "Come si configura il lock della memoria VRAM in Ollama?",
        "expectedDoc": "Ollama_Local_Inference_VRAM_Benchmark.md",
    },
    {
        "id": "tc-2",
        "query": "Qual è il numero di centroidi Voronoi raccomandato in LanceDB?",
        "expectedDoc": "LanceDB_IVF_PQ_Quantization_Whitepaper.pdf",
    },
    {
        "id": "tc-3",
        "query": "In che modo Docling gestisce il chunking semantico senza tagliare tabelle?",
        "expectedDoc": "Docling_Layout_AST_Specification.pdf",
    },
    {
        "id": "tc-4",
        "query": "Come funziona l'integrazione tra threadpool UVicorn e libuv?",
        "expectedDoc": "FastAPI_Uvicorn_Orchestration_Guide.md",
    },
]


def _normalizza_nome_documento(value: Any) -> str:
    """Normalizza titolo/percorso per il confronto con il documento atteso."""
    if not value:
        return ""
    raw = str(value).replace("\\", "/")
    nome = Path(raw).name
    stem = Path(nome).stem
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in stem).strip("_")


def _documento_corrisponde(actual: Any, expected: str) -> bool:
    a = _normalizza_nome_documento(actual)
    e = _normalizza_nome_documento(expected)
    return bool(a and e and (a == e or a.endswith(e) or e.endswith(a)))


def _context_precision(relevant_flags: List[bool]) -> float:
    """Context precision document-level: media della precisione ai rank rilevanti."""
    relevant_seen = 0
    precision_sum = 0.0
    for rank, is_relevant in enumerate(relevant_flags, start=1):
        if is_relevant:
            relevant_seen += 1
            precision_sum += relevant_seen / rank
    return round(precision_sum / relevant_seen, 4) if relevant_seen else 0.0


def _context_recall(relevant_flags: List[bool]) -> float:
    """Recall document-level: il solo ground truth disponibile è il documento atteso."""
    return 1.0 if any(relevant_flags) else 0.0


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    import math

    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    norm_a = math.sqrt(sum(float(x) * float(x) for x in a))
    norm_b = math.sqrt(sum(float(y) * float(y) for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    # Converte cosine [-1, 1] in un intervallo leggibile [0, 1].
    return max(0.0, min(1.0, (dot / (norm_a * norm_b) + 1.0) / 2.0))


def _estrai_json_oggetto(raw: str) -> Dict[str, Any]:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()
    try:
        value = json.loads(raw)
        if isinstance(value, dict):
            return value
    except Exception:
        pass

    inizio = raw.find("{")
    fine = raw.rfind("}")
    if inizio >= 0 and fine > inizio:
        value = json.loads(raw[inizio : fine + 1])
        if isinstance(value, dict):
            return value
    raise ValueError("Il giudice LLM non ha restituito un JSON valido")


def _valuta_faithfulness(query: str, answer: str, contexts: List[str]) -> float:
    """Valuta la fedeltà con un giudice LLM: affermazioni supportate / totali."""
    if not answer.strip():
        return 0.0

    contesto = "\n\n".join(contexts)[:24000]
    messaggi = [
        {
            "role": "system",
            "content": (
                "Sei un valutatore RAG rigoroso. Devi stabilire se la risposta è supportata "
                "dal contesto fornito. Restituisci SOLO JSON valido con i campi "
                "supported_claims e total_claims, entrambi interi. Conta le affermazioni "
                "tecniche verificabili; un'affermazione è supported solo se è direttamente "
                "supportata dal contesto. Non premiare informazioni esterne."
            ),
        },
        {
            "role": "user",
            "content": (
                f"DOMANDA:\n{query}\n\nRISPOSTA:\n{answer[:12000]}\n\n"
                f"CONTESTO:\n{contesto}"
            ),
        },
    ]
    raw = generatore.genera(messaggi)
    valutazione = _estrai_json_oggetto(raw)
    total = max(0, int(valutazione.get("total_claims", 0)))
    supported = max(0, min(total, int(valutazione.get("supported_claims", 0))))
    return round(supported / total, 4) if total else 0.0


def _esegui_query_su_tabella(req: QueryRequest, tabella: Any) -> Dict[str, Any]:
    """Esegue la pipeline RAG su una tabella esplicita, senza dipendere dal DB attivo."""
    top_k = req.topK or config.get("topKCandidates", 20)
    top_n = req.topN or config.get("topNRerank", 6)
    search_mode = (req.searchMode or "hybrid").lower()
    hybrid_alpha = req.hybridAlpha if req.hybridAlpha is not None else 0.7

    query_emb = None
    if search_mode != "sparse":
        # Use embedder tied to the active database
        active_info = db_manager.get_active_info()
        emb_model = active_info.get("embeddingModel", config.get("embeddingModel", "qwen3-embedding:0.6b"))
        emb_url = f"{config.get('ollamaUrl', 'http://localhost:11434').rstrip('/')}/api/embed"
        current_embedder = embedder_manager.get_embedder(emb_model, emb_url)
        query_emb = current_embedder.embed_uno(req.query)

    try:
        if search_mode == "dense":
            righe = tabella.search(query_emb, vector_column_name="vector").limit(top_k).to_list()
            candidati = []
            for r in righe:
                dist = r.get("_distance", 1.0)
                score = max(0.0, round(1.0 - float(dist), 4)) if dist <= 1.0 else round(1.0 / (1.0 + float(dist)), 4)
                candidati.append({**r, "denseScore": score, "bm25Score": 0.0})
        elif search_mode == "sparse":
            righe = tabella.search(req.query, query_type="fts").limit(top_k).to_list()
            candidati = []
            for r in righe:
                score = round(float(r.get("_score", 0.0)), 4)
                candidati.append({**r, "denseScore": 0.0, "bm25Score": score})
        else:
            candidati = ricerca_ibrida(
                tabella,
                vettore_query=query_emb,
                query_testo=req.query,
                top_k=top_k,
                tracciatore=tracciatore_globale,
                search_mode=search_mode,
                hybrid_alpha=hybrid_alpha,
            )
    except Exception:
        crea_indice_fulltext(tabella)
        candidati = ricerca_ibrida(
            tabella,
            vettore_query=query_emb,
            query_testo=req.query,
            top_k=top_k,
            tracciatore=tracciatore_globale,
        )

    initial_rank_map = {c.get("chunk_id", str(i)): i for i, c in enumerate(candidati)}

    try:
        if req.enableRerank is False:
            candidati_rerankati = candidati[:top_n]
            for c in candidati_rerankati:
                c["rerankScore"] = c.get("denseScore", 0.0)
        else:
            candidati_rerankati = reranker.rerank(
                query=req.query,
                candidati=candidati,
                top_n=top_n,
                tracciatore=tracciatore_globale,
            )
    except Exception:
        candidati_rerankati = candidati[:top_n]

    try:
        answer_text = rispondi(
            query=req.query,
            chunk_rerankati=candidati_rerankati,
            generatore=generatore,
            tracciatore=tracciatore_globale,
        )
    except Exception as e:
        answer_text = (
            f"Errore durante la generazione LLM ({e}). "
            "Ecco i passaggi principali trovati nel contesto:\n"
            + "\n".join(f"- [{c.get('fonte_titolo')}] {c.get('testo')[:120]}..." for c in candidati_rerankati)
        )

    chunk_items = [
        mappa_chunk_item(c, idx, initial_rank_map)
        for idx, c in enumerate(candidati_rerankati)
    ]
    return {"answer": answer_text, "chunks": chunk_items, "queryEmbedding": query_emb}


@app.get("/api/eval")
def get_evaluations():
    return eval_results_cache


@app.get("/api/eval/status/{job_id}")
def get_eval_status(job_id: str):
    if job_id not in eval_jobs:
        raise HTTPException(status_code=404, detail="Job di valutazione non trovato")
    return eval_jobs[job_id]


@app.post("/api/eval/run")
async def run_evaluations(background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    captured_db_id = db_manager.active_id
    eval_jobs[job_id] = {
        "status": "running",
        "results": [],
        "testCases": [],
        "databaseId": captured_db_id,
        "error": None,
    }

    def _worker():
        try:
            tabella = db_manager.get_table_for_db(captured_db_id)
            case_results: List[Dict[str, Any]] = []

            for test_case in EVAL_TEST_CASES:
                try:
                    # Verify if the expected document actually exists in the active database
                    # If it doesn't, mark the case as 'Skipped' to avoid misleading 'Not found' results
                    doc_exists = any(test_case["expectedDoc"] in d["sourcePath"] for d in db_manager.get_documents())
                    if not doc_exists:
                        case_res = {
                            **test_case,
                            "status": "Skipped",
                            "error": "Documento atteso non presente nel database attivo.",
                            "retrievedDocs": [],
                            "contextPrecision": None,
                            "contextRecall": None,
                            "answerRelevance": None,
                            "faithfulness": None,
                            "retrievalMatch": 0.0,
                        }
                        case_results.append(case_res)
                        # Update progress as completed but skipped
                        eval_jobs[job_id]["testCases"].append({
                            "id": test_case["id"],
                            "query": test_case["query"],
                            "status": "completed",
                            "result": "Skipped"
                        })
                        eval_jobs[job_id]["updatedAt"] = time.time()
                        continue

                    # PROGRESS UPDATE: update the job state for each case
                    eval_jobs[job_id]["testCases"].append({
                        "id": test_case["id"],
                        "query": test_case["query"],
                        "status": "running"
                    })
                    eval_jobs[job_id]["updatedAt"] = time.time()

                    risultato = _esegui_query_su_tabella(
                        QueryRequest(query=test_case["query"], topK=20, topN=6, searchMode="hybrid", hybridAlpha=0.7, enableRerank=True),
                        tabella,
                    )
                    chunks = risultato.get("chunks", [])
                    flags = [
                        _documento_corrisponde(c.get("docTitle"), test_case["expectedDoc"])
                        for c in chunks
                    ]
                    precision = _context_precision(flags)
                    recall = _context_recall(flags)
                    query_embedding = risultato.get("queryEmbedding") or []

                    # Use embedder tied to the active database
                    active_info = db_manager.get_active_info()
                    emb_model = active_info.get("embeddingModel", config.get("embeddingModel", "qwen3-embedding:0.6b"))
                    emb_url = f"{config.get('ollamaUrl', 'http://localhost:11434').rstrip('/')}/api/embed"
                    current_embedder = embedder_manager.get_embedder(emb_model, emb_url)
                    answer_embedding = current_embedder.embed_uno(risultato.get("answer", ""))

                    relevance = round(_cosine_similarity(query_embedding, answer_embedding), 4)
                    faithfulness = _valuta_faithfulness(
                        test_case["query"],
                        risultato.get("answer", ""),
                        [c.get("text", "") for c in chunks if c.get("text")],
                    )
                    found = any(flags)
                    case_res = {
                        **test_case,
                        "retrievedDocs": list(dict.fromkeys(c.get("docTitle", "Documento") for c in chunks)),
                        "contextPrecision": precision,
                        "contextRecall": recall,
                        "answerRelevance": relevance,
                        "faithfulness": faithfulness,
                        "retrievalMatch": round((precision + recall) / 2.0, 4),
                        "status": "Found" if found else "Not found",
                        "error": None,
                    }
                    case_results.append(case_res)

                    # PROGRESS UPDATE: mark case as completed
                    for tc in eval_jobs[job_id]["testCases"]:
                        if tc["id"] == test_case["id"]:
                            tc["status"] = "completed"
                            tc["result"] = case_res["status"]
                            break
                    eval_jobs[job_id]["updatedAt"] = time.time()
                except Exception as exc:
                    case_results.append({
                        **test_case,
                        "retrievedDocs": [],
                        "contextPrecision": None,
                        "contextRecall": None,
                        "answerRelevance": None,
                        "faithfulness": None,
                        "retrievalMatch": 0.0,
                        "status": "Error",
                        "error": str(exc),
                    })

            metric_defs = [
                ("eval-1", "Fedeltà (LLM Judge)", "faithfulness", 0.90, "Quota di affermazioni della risposta supportate dal contesto recuperato."),
                ("eval-2", "Rilevanza Query-Risposta", "answerRelevance", 0.80, "Similarità coseno tra embedding della query e della risposta generata."),
                ("eval-3", "Precisione del Contesto", "contextPrecision", 0.80, "Context precision a livello di documento atteso, calcolata sui chunk realmente recuperati."),
                ("eval-4", "Richiamo del Contesto", "contextRecall", 0.80, "Recall a livello di documento atteso: 1 se il documento ground-truth compare nei chunk recuperati, altrimenti 0."),
            ]
            metrics: List[Dict[str, Any]] = []
            for metric_id, name, field, target, description in metric_defs:
                values = [c[field] for c in case_results if isinstance(c.get(field), (int, float))]
                if not values:
                    continue
                score = round(sum(values) / len(values), 4)
                metrics.append({
                    "id": metric_id,
                    "name": name,
                    "score": score,
                    "benchmarkTarget": target,
                    "description": description,
                    "delta": f"{score * 100:.1f}% su {len(values)}/{len(case_results)} casi",
                })

            errors = [c for c in case_results if c.get("status") == "Error"]
            eval_results_cache.clear()
            eval_results_cache.extend(metrics)
            eval_jobs[job_id] = {
                "status": "completed_with_errors" if errors else "completed",
                "results": metrics,
                "testCases": case_results,
                "databaseId": captured_db_id,
                "error": f"{len(errors)} casi non valutabili" if errors else None,
            }
        except Exception as exc:
            eval_jobs[job_id] = {
                "status": "failed",
                "results": [],
                "testCases": [],
                "databaseId": captured_db_id,
                "error": str(exc),
            }

    task = asyncio.create_task(asyncio.to_thread(_worker))
    _eval_tasks.add(task)
    task.add_done_callback(_eval_tasks.discard)
    return {
        "jobId": job_id,
        "status": "running",
        "databaseId": captured_db_id,
        "message": "Valutazione RAG reale avviata in background",
    }


SETTINGS_DEFAULTS: Dict[str, Any] = {
    "themeMode": "dark",
    "hostUrl": "127.0.0.1",
    "portNumber": 8000,
    "workerConcurrency": 2,
    "logLevel": "INFO",
    "corsOrigins": "http://localhost:3000,http://127.0.0.1:3000",
    "storagePath": "data/databases",
    "tableName": "chunks",
    "indexAlgorithm": "IVF-PQ",
    "numCentroids": 256,
    "subVectorsPQ": 16,
    "distanceMetric": "Cosine",
    "autoCompaction": True,
    "chunkSize": 512,
    "chunkOverlap": 15,
    "ocrTablesExtraction": True,
    "splitMode": "ast",
    "ollamaUrl": "http://localhost:11434",
    "embeddingModel": "qwen3-embedding:0.6b",
    "crossEncoderModel": "BAAI/bge-reranker-v2-m3",
    "keepAliveSeconds": 300,
    "topKCandidates": 20,
    "topNRerank": 6,
    "apiToken": "",
    "rateLimitMax": 100,
    "maxPayloadMB": 50,
}

def _validate_settings(cfg: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(SETTINGS_DEFAULTS)
    current = caricaconfig()
    out.update(current)
    out.update(cfg)
    numeric_ranges = {
        "portNumber": (1, 65535), "workerConcurrency": (1, 64),
        "numCentroids": (1, 100000), "subVectorsPQ": (1, 1024),
        "chunkSize": (1, 100000), "chunkOverlap": (0, 99),
        "keepAliveSeconds": (0, 86400), "topKCandidates": (1, 1000),
        "topNRerank": (1, 1000), "rateLimitMax": (1, 100000),
        "maxPayloadMB": (1, 2048),
    }
    for key, (low, high) in numeric_ranges.items():
        value = out.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            raise HTTPException(status_code=400, detail=f"Impostazione '{key}' non valida")
    if out["chunkOverlap"] >= 100:
        raise HTTPException(status_code=400, detail="chunkOverlap deve essere inferiore a 100")
    if out.get("distanceMetric") not in {"Cosine", "L2", "Dot"}:
        raise HTTPException(status_code=400, detail="distanceMetric non valida")
    if out.get("indexAlgorithm") not in {"IVF-PQ", "FLAT"}:
        raise HTTPException(status_code=400, detail="indexAlgorithm non valido")
    return out

@app.get("/api/auth/status")
def auth_status():
    return {"configured": bool(str(config.get("apiToken") or "").strip())}

@app.get("/api/settings")
def get_settings():
    data = caricaconfig()
    # Il token non deve essere restituito dal backend al browser.
    data["apiToken"] = ""
    return data

@app.get("/api/settings/defaults")
def get_default_settings():
    return dict(SETTINGS_DEFAULTS)

@app.put("/api/settings")
def update_settings(new_cfg: Dict[str, Any]):
    global config
    safe = _validate_settings(new_cfg)
    # Non consentire di cancellare accidentalmente un token gia' configurato
    # inviando il campo redatto dal frontend.
    current = caricaconfig()
    if not new_cfg.get("apiToken") and current.get("apiToken"):
        safe["apiToken"] = current["apiToken"]
    salvaconfig(safe)
    config = safe
    return {**safe, "apiToken": ""}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("webapp.backend.main:app", host="0.0.0.0", port=8000, reload=True)
