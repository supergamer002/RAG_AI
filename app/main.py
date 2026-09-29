"""RAG AI - backend unico.

Un solo file, zero configurazione: FastAPI + SQLite + Ollama.
Serve anche il frontend (app/static/index.html), quindi basta avviare
questo server e aprire http://localhost:8000.

Tutti i dati stanno in data/rag.db (documenti, chunk, embedding, chat, impostazioni).
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from html import unescape
from pathlib import Path
from typing import Iterator

import numpy as np
import requests
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .reranker import CrossEncoderReranker

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RAG_DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "rag.db"
INGEST_DIR = DATA_DIR / "ingest_jobs"
STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MAX_BATCH_FILES = 500
MAX_BATCH_BYTES = 2 * 1024 * 1024 * 1024
INGEST_WORKERS = 2

DEFAULT_SETTINGS: dict = {
    "ollama_url": os.environ.get("OLLAMA_URL", "http://localhost:11434"),
    "chat_model": "qwen3:8b",
    "embed_model": "qwen3-embedding:0.6b",
    "top_k": 5,
    "chunk_size": 1000,
    "chunk_overlap": 150,
}

SYSTEM_PROMPT = (
    "Sei un assistente che risponde in base ai documenti forniti dall'utente.\n"
    "Regole:\n"
    "1. Usa SOLO il contesto fornito. Se non contiene la risposta, dillo chiaramente "
    "(\"Nei documenti caricati non trovo questa informazione\") invece di rispondere a memoria.\n"
    "2. Dopo ogni affermazione tecnica cita la fonte con il suo numero tra parentesi quadre, es. [1] o [2][3].\n"
    "3. Rispondi nella lingua della domanda, in modo chiaro e diretto, senza preamboli."
)


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #

@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with tx() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, size INTEGER NOT NULL,
                n_chunks INTEGER NOT NULL, embed_model TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                idx INTEGER NOT NULL, page INTEGER, text TEXT NOT NULL, embedding BLOB NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
            CREATE TABLE IF NOT EXISTS ingest_jobs (
                id TEXT PRIMARY KEY, status TEXT NOT NULL, total_files INTEGER NOT NULL,
                completed_files INTEGER NOT NULL DEFAULT 0, failed_files INTEGER NOT NULL DEFAULT 0,
                current_file TEXT, message TEXT, stage TEXT NOT NULL DEFAULT 'queued',
                stage_progress REAL NOT NULL DEFAULT 0, total_chunks INTEGER NOT NULL DEFAULT 0,
                processed_chunks INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL, updated_at REAL NOT NULL,
                finished_at REAL, total_bytes INTEGER NOT NULL DEFAULT 0, processed_bytes INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS ingest_job_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES ingest_jobs(id) ON DELETE CASCADE,
                name TEXT NOT NULL, size INTEGER NOT NULL, status TEXT NOT NULL, error TEXT, document_id TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_ingest_job_files_job ON ingest_job_files(job_id);
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conv_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL, content TEXT NOT NULL, sources TEXT, created_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conv_id);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        existing = {r[1] for r in c.execute("PRAGMA table_info(ingest_jobs)").fetchall()}
        migrations = {
            "stage": "ALTER TABLE ingest_jobs ADD COLUMN stage TEXT NOT NULL DEFAULT 'queued'",
            "stage_progress": "ALTER TABLE ingest_jobs ADD COLUMN stage_progress REAL NOT NULL DEFAULT 0",
            "total_chunks": "ALTER TABLE ingest_jobs ADD COLUMN total_chunks INTEGER NOT NULL DEFAULT 0",
            "processed_chunks": "ALTER TABLE ingest_jobs ADD COLUMN processed_chunks INTEGER NOT NULL DEFAULT 0",
        }
        for column, sql in migrations.items():
            if column not in existing:
                c.execute(sql)


def get_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    with tx() as c:
        for row in c.execute("SELECT key, value FROM settings"):
            if row["key"] in s:
                try:
                    s[row["key"]] = json.loads(row["value"])
                except ValueError:
                    pass
    return s


def save_settings(values: dict) -> dict:
    with tx() as c:
        for k, v in values.items():
            c.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, json.dumps(v)),
            )
    return get_settings()


# --------------------------------------------------------------------------- #
# Ollama
# --------------------------------------------------------------------------- #

class OllamaError(RuntimeError):
    pass


def _model_hint(model: str) -> str:
    return f"Modello '{model}' non disponibile: verrà scaricato automaticamente, riprova tra poco."


def embed(texts: list[str], s: dict, progress=None) -> np.ndarray:
    """Embedding normalizzati (righe a norma 1), a batch."""
    out: list[list[float]] = []
    total = len(texts)
    for i in range(0, total, 16):
        batch = texts[i : i + 16]
        try:
            r = requests.post(
                f"{s['ollama_url']}/api/embed",
                json={"model": s["embed_model"], "input": batch, "keep_alive": "10m"},
                timeout=300,
            )
        except requests.RequestException as exc:
            raise OllamaError(f"Ollama non raggiungibile su {s['ollama_url']}. Avvialo e riprova.") from exc
        if r.status_code == 404:
            raise OllamaError(_model_hint(s["embed_model"]))
        if r.status_code != 200:
            raise OllamaError(f"Errore embedding (HTTP {r.status_code}): {r.text[:200]}")
        out.extend(r.json()["embeddings"])
        if progress:
            progress(min(i + len(batch), total), total)
    arr = np.asarray(out, dtype=np.float32)
    if arr.ndim != 2 or len(arr) != len(texts):
        raise OllamaError("Risposta embedding non valida da Ollama.")
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


def chat_stream(messages: list[dict], s: dict) -> Iterator[str]:
    payload = {"model": s["chat_model"], "messages": messages, "stream": True, "think": False, "keep_alive": "10m"}
    try:
        r = requests.post(f"{s['ollama_url']}/api/chat", json=payload, stream=True, timeout=(5, 600))
    except requests.RequestException as exc:
        raise OllamaError(f"Ollama non raggiungibile su {s['ollama_url']}. Avvialo e riprova.") from exc
    if r.status_code == 404:
        raise OllamaError(_model_hint(s["chat_model"]))
    if r.status_code != 200:
        raise OllamaError(f"Errore generazione (HTTP {r.status_code}): {r.text[:200]}")
    for line in r.iter_lines():
        if not line:
            continue
        obj = json.loads(line)
        if obj.get("error"):
            raise OllamaError(str(obj["error"]))
        piece = obj.get("message", {}).get("content", "")
        if piece:
            yield piece
        if obj.get("done"):
            break


def strip_think(pieces: Iterator[str]) -> Iterator[str]:
    """Rimuove eventuali blocchi <think>...</think> dallo stream."""
    buf, in_think = "", False
    for p in pieces:
        buf += p
        while True:
            if in_think:
                j = buf.find("</think>")
                if j == -1:
                    buf = buf[-8:]
                    break
                buf, in_think = buf[j + 8 :].lstrip(), False
            else:
                j = buf.find("<think>")
                if j == -1:
                    keep = 0
                    for n in range(min(6, len(buf)), 0, -1):
                        if "<think>".startswith(buf[-n:]):
                            keep = n
                            break
                    out, buf = buf[: len(buf) - keep], buf[len(buf) - keep :]
                    if out:
                        yield out
                    break
                if j > 0:
                    yield buf[:j]
                buf, in_think = buf[j + 7 :], True
    if not in_think and buf:
        yield buf


# --------------------------------------------------------------------------- #
# Setup automatico di Ollama e dei modelli (thread in background)
# --------------------------------------------------------------------------- #

STATE: dict = {"ollama_up": False, "installed": [], "pulling": None, "progress": 0.0, "error": None}


def _has_model(installed: list[str], name: str) -> bool:
    return name in installed or (":" not in name and f"{name}:latest" in installed)


def _pull(model: str, url: str) -> None:
    STATE.update(pulling=model, progress=0.0, error=None)
    try:
        with requests.post(f"{url}/api/pull", json={"model": model, "stream": True}, stream=True, timeout=(5, None)) as r:
            if r.status_code != 200:
                raise OllamaError(f"pull di '{model}' fallito (HTTP {r.status_code}): {r.text[:200]}")
            for line in r.iter_lines():
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("error"):
                    raise OllamaError(str(obj["error"]))
                if obj.get("total"):
                    STATE["progress"] = round(obj.get("completed", 0) / obj["total"], 3)
    except Exception as exc:  # noqa: BLE001
        STATE["error"] = f"Download del modello '{model}' non riuscito: {exc}"
        time.sleep(30)
    finally:
        STATE["pulling"] = None


def _bootstrap_loop() -> None:
    started_local = False
    while True:
        s = get_settings()
        url = s["ollama_url"]
        try:
            r = requests.get(f"{url}/api/tags", timeout=3)
            r.raise_for_status()
            installed = [m["name"] for m in r.json().get("models", [])]
            STATE.update(ollama_up=True, installed=installed)
        except Exception:  # noqa: BLE001
            STATE.update(ollama_up=False)
            if not started_local and shutil.which("ollama") and ("localhost" in url or "127.0.0.1" in url):
                started_local = True
                try:
                    flags = 0x08000000 if os.name == "nt" else 0
                    subprocess.Popen(
                        ["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags
                    )
                except OSError:
                    pass
            time.sleep(3)
            continue
        for model in (s["embed_model"], s["chat_model"]):
            if not _has_model(installed, model):
                _pull(model, url)
                break
        else:
            STATE["error"] = None
        time.sleep(5)


# --------------------------------------------------------------------------- #
# Estrazione testo e chunking
# --------------------------------------------------------------------------- #

def extract_pages(name: str, data: bytes) -> list[tuple[int | None, str]]:
    """Estrae testo preservando la struttura dei PDF quando disponibile."""
    ext = Path(name).suffix.lower()
    if ext == ".pdf":
        import pymupdf as fitz
        from .headings import calcola_statistiche_font, estrai_testo_con_intestazioni, rileva_righe_boilerplate

        with fitz.open(stream=data, filetype="pdf") as doc:
            stats = calcola_statistiche_font(doc)
            boilerplate = rileva_righe_boilerplate(doc)
            pages: list[tuple[int | None, str]] = []
            for i in range(len(doc)):
                page = doc.load_page(i)
                text = estrai_testo_con_intestazioni(page, stats, boilerplate)
                # Pulizia leggera, senza introdurre una dipendenza OCR obbligatoria.
                lines = []
                for line in text.splitlines():
                    line = re.sub(r"[ \t]+", " ", line).strip()
                    if line:
                        lines.append(line)
                cleaned = "\n".join(lines)
                if cleaned:
                    cleaned = f"=== PAGINA {i + 1} ===\n{cleaned}"
                pages.append((i + 1, cleaned))
            return pages
    if ext == ".docx":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        xml = re.sub(r"</w:p>", "\n\n", xml)
        xml = re.sub(r"<w:tab/>", "\t", xml)
        return [(None, unescape(re.sub(r"<[^>]+>", "", xml)))]
    if b"\x00" in data[:4096]:
        raise ValueError(f"Formato non supportato: {ext or 'sconosciuto'}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    if ext in (".html", ".htm"):
        text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
        text = unescape(re.sub(r"<[^>]+>", " ", text))
    return [(None, text)]


def _hard_cut(text: str, size: int) -> list[str]:
    parts = []
    while len(text) > size:
        cut = text.rfind(" ", 0, size)
        cut = cut if cut > size // 2 else size
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts.append(text)
    return parts


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Segmentazione ibrida: struttura H1/H2 prima, semantica come fallback."""
    text = text.replace("\r", "")
    if not text.strip():
        return []
    try:
        from .segment import segmenta_strutturato, segmenta_semantico, ha_marcatori, densita_titoli_sufficiente, _applica_soglia_minima
        if ha_marcatori(text) and densita_titoli_sufficiente(text):
            units = segmenta_strutturato(text, min_parole=max(60, min(size // 5, 300)), max_parole=max(300, min(size // 2, 1500)))
        else:
            units = segmenta_semantico(text, min_parole=max(60, min(size // 5, 150)), target_parole=max(250, min(size // 2, 600)))
        units = _applica_soglia_minima(units)
        chunks = [u["testo"].strip() for u in units if u.get("testo", "").strip()]
        if chunks:
            return chunks
    except Exception:
        # Fallback conservativo al chunker precedente: l'errore del segmentatore
        # non deve rendere inutilizzabile l'ingestion.
        pass
    units: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = re.sub(r"\s+", " ", para).strip()
        if not para:
            continue
        for sent in re.split(r"(?<=[.!?])\s+", para) if len(para) > size else [para]:
            units.extend(_hard_cut(sent, size) if len(sent) > size else [sent])
    chunks: list[str] = []
    cur = ""
    for u in units:
        if cur and len(cur) + 1 + len(u) > size:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap else ""
            if tail:
                sp = tail.find(" ")
                tail = tail[sp + 1 :] if sp != -1 else ""
            cur = f"{tail} {u}".strip() if tail else u
        else:
            cur = f"{cur} {u}" if cur else u
    if cur:
        chunks.append(cur)
    return chunks


# --------------------------------------------------------------------------- #
# Indice in memoria + ricerca ibrida (semantica + parole chiave, fusione RRF)
# --------------------------------------------------------------------------- #

_cache: dict = {"model": None, "matrix": None, "meta": [], "lower": []}
_cache_lock = threading.Lock()
RERANKER = CrossEncoderReranker()


def invalidate_cache() -> None:
    with _cache_lock:
        _cache.update(model=None, matrix=None, meta=[], lower=[])


def _load_index(model: str) -> dict:
    with _cache_lock:
        if _cache["matrix"] is not None and _cache["model"] == model:
            return _cache
        with tx() as c:
            rows = c.execute(
                "SELECT c.id, c.doc_id, d.name, c.page, c.text, c.embedding FROM chunks c "
                "JOIN documents d ON d.id = c.doc_id WHERE d.embed_model = ? ORDER BY c.id",
                (model,),
            ).fetchall()
        matrix = (
            np.vstack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
            if rows
            else np.zeros((0, 0), dtype=np.float32)
        )
        _cache.update(
            model=model,
            matrix=matrix,
            meta=[
                {"chunk_id": r["id"], "document_id": r["doc_id"], "document": r["name"], "page": r["page"], "text": r["text"]}
                for r in rows
            ],
            lower=[r["text"].lower() for r in rows],
        )
        return _cache


def search(query: str, top_k: int, s: dict) -> list[dict]:
    idx = _load_index(s["embed_model"])
    n = len(idx["meta"])
    if n == 0:
        return []
    qv = embed([query], s)[0]
    dense = idx["matrix"] @ qv
    k = min(n, max(top_k * 4, 20))
    scores: dict[int, float] = {}
    for rank, i in enumerate(np.argsort(-dense)[:k]):
        scores[int(i)] = scores.get(int(i), 0.0) + 1.0 / (60 + rank)
    terms = set(re.findall(r"\w{3,}", query.lower()))
    if terms:
        kw = np.array([sum(1 for t in terms if t in txt) for txt in idx["lower"]], dtype=np.float32) / len(terms)
        for rank, i in enumerate(np.argsort(-kw)[:k]):
            if kw[i] > 0:
                scores[int(i)] = scores.get(int(i), 0.0) + 1.0 / (60 + rank)
    # Il retrieval ibrido genera un pool piu' ampio; il Cross-Encoder
    # valuta poi le coppie query/chunk e seleziona i risultati finali.
    candidate_indices = sorted(scores, key=scores.get, reverse=True)[: min(n, max(top_k * 4, 20))]
    candidates = [
        {**idx["meta"][i], "score": round(float(dense[i]), 4)}
        for i in candidate_indices
    ]
    try:
        return RERANKER.rerank(query, candidates, top_k)
    except Exception:
        # Il reranking non deve rendere indisponibile il RAG se il modello
        # non e' ancora scaricato, manca una dipendenza o il caricamento fallisce.
        return candidates[:top_k]


# --------------------------------------------------------------------------- #
# Ingest jobs
# --------------------------------------------------------------------------- #

INGEST_EXECUTOR = ThreadPoolExecutor(max_workers=INGEST_WORKERS, thread_name_prefix="rag-ingest")


def _job_update(job_id: str, **values) -> None:
    values["updated_at"] = time.time()
    assignments = ", ".join(f"{k} = ?" for k in values)
    with tx() as c:
        c.execute(f"UPDATE ingest_jobs SET {assignments} WHERE id = ?", [*values.values(), job_id])


def _job_file_update(file_id: int, **values) -> None:
    values["updated_at"] = time.time()
    assignments = ", ".join(f"{k} = ?" for k in values)
    with tx() as c:
        c.execute(f"UPDATE ingest_job_files SET {assignments} WHERE id = ?", [*values.values(), file_id])


def _job_dict(job_id: str) -> dict:
    with tx() as c:
        job = c.execute("SELECT * FROM ingest_jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Job di ingest non trovato.")
        files = c.execute("SELECT * FROM ingest_job_files WHERE job_id = ? ORDER BY id", (job_id,)).fetchall()
    total = max(1, job["total_files"])
    return {
        "id": job["id"], "status": job["status"], "total_files": job["total_files"],
        "completed_files": job["completed_files"], "failed_files": job["failed_files"],
        "current_file": job["current_file"], "message": job["message"],
        "stage": job["stage"], "stage_progress": round(job["stage_progress"], 4),
        "total_chunks": job["total_chunks"], "processed_chunks": job["processed_chunks"],
        "created_at": job["created_at"], "updated_at": job["updated_at"], "finished_at": job["finished_at"],
        "total_bytes": job["total_bytes"], "processed_bytes": job["processed_bytes"],
        "progress": round((job["completed_files"] + job["failed_files"]) / total, 4),
        "files": [{"id": f["id"], "name": f["name"], "size": f["size"], "status": f["status"],
                   "error": f["error"], "document_id": f["document_id"]} for f in files],
    }


def _job_payloads(job_id: str) -> list[tuple[int, str, Path, int]]:
    with tx() as c:
        rows = c.execute("SELECT id, name, size FROM ingest_job_files WHERE job_id = ? ORDER BY id", (job_id,)).fetchall()
    return [(r["id"], r["name"], INGEST_DIR / job_id / f"{r['id']}.bin", r["size"]) for r in rows]


def _run_ingest_job(job_id: str, settings: dict) -> None:
    _job_update(job_id, status="processing", stage="queued", stage_progress=0,
                message="Job avviato")
    for file_id, name, path, size in _job_payloads(job_id):
        with tx() as c:
            state = c.execute("SELECT status FROM ingest_job_files WHERE id = ?", (file_id,)).fetchone()
        if not state or state["status"] == "ready":
            continue
        _job_update(job_id, current_file=name, stage="extraction", stage_progress=0,
                    message=f"Preparo {name}")
        _job_file_update(file_id, status="processing")
        try:
            data = path.read_bytes()

            def report(stage, pct, message, **extra):
                values = {"stage": stage, "stage_progress": pct, "message": message}
                if "total_chunks" in extra:
                    values["total_chunks"] = extra["total_chunks"]
                if "processed_chunks" in extra:
                    values["processed_chunks"] = extra["processed_chunks"]
                _job_update(job_id, **values)

            doc = ingest(name, data, settings, progress=report)
            _job_file_update(file_id, status="ready", document_id=doc["id"], error=None)
            with tx() as c:
                c.execute("UPDATE ingest_jobs SET completed_files = completed_files + 1, processed_bytes = processed_bytes + ? WHERE id = ?",
                          (size, job_id))
            _job_update(job_id, stage="done", stage_progress=1,
                        message=f"Pronto: {name}", processed_chunks=0)
        except Exception as exc:
            _job_file_update(file_id, status="failed", error=str(exc))
            with tx() as c:
                c.execute("UPDATE ingest_jobs SET failed_files = failed_files + 1, processed_bytes = processed_bytes + ? WHERE id = ?",
                          (size, job_id))
            _job_update(job_id, stage="error", stage_progress=1,
                        message=f"Errore in {name}: {exc}")

    with tx() as c:
        counts = c.execute("SELECT SUM(status = 'ready') AS ready, SUM(status = 'failed') AS failed, COUNT(*) AS total FROM ingest_job_files WHERE job_id = ?",
                           (job_id,)).fetchone()
    ready_count = int(counts["ready"] or 0)
    failed_count = int(counts["failed"] or 0)
    status = "ready" if ready_count == counts["total"] else ("partial" if ready_count else "failed")
    _job_update(job_id, completed_files=ready_count, failed_files=failed_count,
                status=status, stage="done" if status == "ready" else "error",
                stage_progress=1, current_file=None,
                message=("Ingestion completata" if status == "ready" else "Ingestion completata con errori"),
                finished_at=time.time())
    shutil.rmtree(INGEST_DIR / job_id, ignore_errors=True)


def create_ingest_job(files: list[tuple[str, bytes]], settings: dict) -> str:
    if not files:
        raise HTTPException(422, "Nessun file ricevuto.")
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(413, f"Troppi file: massimo {MAX_BATCH_FILES} per ingest.")
    total_bytes = sum(len(data) for _, data in files)
    if total_bytes > MAX_BATCH_BYTES:
        raise HTTPException(413, "Batch troppo grande: massimo 2 GB.")
    for name, data in files:
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"File troppo grande: massimo 200 MB ({name}).")
    job_id = uuid.uuid4().hex[:16]
    now = time.time()
    job_dir = INGEST_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tx() as c:
            c.execute("INSERT INTO ingest_jobs(id,status,total_files,created_at,updated_at,total_bytes) VALUES(?,?,?,?,?,?)",
                      (job_id, "queued", len(files), now, now, total_bytes))
            rows = []
            for name, data in files:
                rows.append((job_id, name, len(data), "queued", now, now))
            c.executemany("INSERT INTO ingest_job_files(job_id,name,size,status,created_at,updated_at) VALUES(?,?,?,?,?,?)", rows)
            ids = [r[0] for r in c.execute("SELECT id FROM ingest_job_files WHERE job_id = ? ORDER BY id", (job_id,)).fetchall()]
        for fid, (_, data) in zip(ids, files):
            (job_dir / f"{fid}.bin").write_bytes(data)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        with tx() as c:
            c.execute("DELETE FROM ingest_jobs WHERE id = ?", (job_id,))
        raise
    INGEST_EXECUTOR.submit(_run_ingest_job, job_id, dict(settings))
    return job_id


def recent_ingest_jobs(limit: int = 10) -> list[dict]:
    with tx() as c:
        rows = c.execute("SELECT id FROM ingest_jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_job_dict(r["id"]) for r in rows]


def resume_ingest_jobs() -> None:
    with tx() as c:
        rows = c.execute("SELECT id FROM ingest_jobs WHERE status IN ('queued', 'processing') ORDER BY created_at").fetchall()
    if not rows:
        return
    settings = get_settings()
    for row in rows:
        INGEST_EXECUTOR.submit(_run_ingest_job, row["id"], dict(settings))

# --------------------------------------------------------------------------- #
# Ingest
# --------------------------------------------------------------------------- #

def _delete_document(doc_id: str) -> None:
    with tx() as c:
        c.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    invalidate_cache()


def ingest(name: str, data: bytes, s: dict, progress=None) -> dict:
    """Ingestione osservabile: estrazione -> segmentazione -> embedding -> salvataggio."""
    def report(stage, pct, message, **extra):
        if progress:
            progress(stage, max(0.0, min(1.0, pct)), message, **extra)

    report("extraction", 0.0, f"Estrazione testo: {name}")
    pages = extract_pages(name, data)
    report("extraction", 1.0, f"Testo estratto: {name}")

    pieces = []
    total_pages = max(1, len(pages))
    for idx, (page, text) in enumerate(pages, 1):
        pieces.extend((page, ch) for ch in chunk_text(text, s["chunk_size"], s["chunk_overlap"]))
        report("segmentation", idx / total_pages,
               f"Segmentazione: {idx}/{len(pages)} pagine", total_chunks=len(pieces))

    if not pieces:
        raise ValueError("Nessun testo estraibile dal file (PDF scansionato?).")

    report("embedding", 0.0, f"Embedding: 0/{len(pieces)} chunk", total_chunks=len(pieces))
    vecs = embed(
        [t for _, t in pieces], s,
        progress=lambda done, total: report(
            "embedding", done / max(1, total), f"Embedding: {done}/{total} chunk",
            total_chunks=total, processed_chunks=done
        ),
    )

    report("saving", 0.0, f"Salvataggio: {len(pieces)} chunk")
    with tx() as c:
        for row in c.execute("SELECT id FROM documents WHERE name = ?", (name,)).fetchall():
            c.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
        doc_id = uuid.uuid4().hex[:12]
        c.execute(
            "INSERT INTO documents(id, name, size, n_chunks, embed_model, created_at) VALUES(?,?,?,?,?,?)",
            (doc_id, name, len(data), len(pieces), s["embed_model"], time.time()),
        )
        c.executemany(
            "INSERT INTO chunks(doc_id, idx, page, text, embedding) VALUES(?,?,?,?,?)",
            [(doc_id, i, pg, tx_, vecs[i].tobytes()) for i, (pg, tx_) in enumerate(pieces)],
        )
    report("saving", 1.0, f"Salvati {len(pieces)} chunk")
    invalidate_cache()
    report("done", 1.0, f"File pronto: {name}")
    return _doc_dict(doc_id)


def _doc_dict(doc_id: str) -> dict:
    with tx() as c:
        r = c.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Documento non trovato.")
    return {"id": r["id"], "name": r["name"], "size": r["size"], "chunks": r["n_chunks"],
            "embed_model": r["embed_model"], "created_at": r["created_at"]}


# --------------------------------------------------------------------------- #
# Chat
# --------------------------------------------------------------------------- #

def _build_messages(question: str, sources: list[dict], history: list[dict]) -> list[dict]:
    blocks = []
    for n, src in enumerate(sources, 1):
        where = src["document"] + (f", p. {src['page']}" if src.get("page") else "")
        blocks.append(f"[{n}] ({where})\n{src['text']}")
    context = "\n\n".join(blocks)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": f"Contesto:\n\n{context}\n\nDomanda: {question}"},
    ]


def run_chat(message: str, conversation_id: str | None) -> Iterator[dict]:
    s = get_settings()
    now = time.time()
    with tx() as c:
        if conversation_id:
            if not c.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone():
                yield {"type": "error", "message": "Conversazione non trovata."}
                return
        else:
            conversation_id = uuid.uuid4().hex[:12]
            title = (message[:60] + "…") if len(message) > 60 else message
            c.execute("INSERT INTO conversations VALUES(?,?,?,?)", (conversation_id, title, now, now))
        history = [
            {"role": r["role"], "content": r["content"]}
            for r in reversed(
                c.execute(
                    "SELECT role, content FROM messages WHERE conv_id = ? ORDER BY id DESC LIMIT 6", (conversation_id,)
                ).fetchall()
            )
        ]
        c.execute("INSERT INTO messages(conv_id, role, content, created_at) VALUES(?,?,?,?)",
                  (conversation_id, "user", message, now))
    yield {"type": "meta", "conversation_id": conversation_id}

    answer = ""
    sources: list[dict] = []
    try:
        with tx() as c:
            total = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        if total == 0:
            answer = "Non hai ancora caricato documenti. Aggiungine uno dalla barra laterale e poi rifai la domanda."
            yield {"type": "sources", "sources": []}
            yield {"type": "token", "content": answer}
        else:
            sources = search(message, s["top_k"], s)
            yield {"type": "sources", "sources": sources}
            for piece in strip_think(chat_stream(_build_messages(message, sources, history), s)):
                answer += piece
                yield {"type": "token", "content": piece}
    except OllamaError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    with tx() as c:
        c.execute("INSERT INTO messages(conv_id, role, content, sources, created_at) VALUES(?,?,?,?,?)",
                  (conversation_id, "assistant", answer, json.dumps(sources), time.time()))
        c.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (time.time(), conversation_id))
    yield {"type": "done", "conversation_id": conversation_id}


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    INGEST_DIR.mkdir(parents=True, exist_ok=True)
    resume_ingest_jobs()
    if os.environ.get("RAG_AUTOSETUP", "1") != "0":
        threading.Thread(target=_bootstrap_loop, daemon=True).start()
    yield


app = FastAPI(title="RAG AI", lifespan=lifespan)


class SettingsUpdate(BaseModel):
    ollama_url: str | None = None
    chat_model: str | None = None
    embed_model: str | None = None
    top_k: int | None = Field(None, ge=1, le=20)
    chunk_size: int | None = Field(None, ge=200, le=4000)
    chunk_overlap: int | None = Field(None, ge=0, le=1000)


class SearchRequest(BaseModel):
    query: str
    top_k: int | None = Field(None, ge=1, le=50)


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    stream: bool = True


class RenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "ollama": bool(STATE["ollama_up"])}


@app.get("/api/status")
def status() -> dict:
    s = get_settings()
    installed = STATE["installed"]
    chat_ok, embed_ok = _has_model(installed, s["chat_model"]), _has_model(installed, s["embed_model"])
    with tx() as c:
        docs = c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        chunks = c.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        stale = c.execute("SELECT COUNT(*) FROM documents WHERE embed_model != ?", (s["embed_model"],)).fetchone()[0]
    with tx() as c:
        active_jobs = c.execute("SELECT COUNT(*) FROM ingest_jobs WHERE status IN ('queued', 'processing')").fetchone()[0]
        ready_jobs = c.execute("SELECT COUNT(*) FROM ingest_jobs WHERE status = 'ready'").fetchone()[0]
    return {
        "ready": bool(STATE["ollama_up"] and chat_ok and embed_ok),
        "ollama": bool(STATE["ollama_up"]),
        "chat_model": {"name": s["chat_model"], "available": chat_ok},
        "embed_model": {"name": s["embed_model"], "available": embed_ok},
        "pulling": STATE["pulling"],
        "progress": STATE["progress"],
        "error": STATE["error"],
        "documents": docs,
        "chunks": chunks,
        "stale_documents": stale,
        "active_ingest_jobs": active_jobs,
        "ready_ingest_jobs": ready_jobs,
        "cross_encoder": RERANKER.status(),
    }


@app.get("/api/settings")
def read_settings() -> dict:
    return get_settings()


@app.put("/api/settings")
def update_settings(body: SettingsUpdate) -> dict:
    values = {k: (v.strip() if isinstance(v, str) else v) for k, v in body.model_dump().items() if v is not None}
    if any(v == "" for v in values.values()):
        raise HTTPException(422, "I campi di testo non possono essere vuoti.")
    if "ollama_url" in values:
        values["ollama_url"] = values["ollama_url"].rstrip("/")
    merged = {**get_settings(), **values}
    if merged["chunk_overlap"] >= merged["chunk_size"]:
        raise HTTPException(422, "L'overlap deve essere minore della dimensione del chunk.")
    return save_settings(values)


@app.post("/api/settings/reset")
def reset_settings() -> dict:
    with tx() as c:
        c.execute("DELETE FROM settings")
    return get_settings()


@app.get("/api/documents")
def list_documents() -> list[dict]:
    with tx() as c:
        rows = c.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
    return [{"id": r["id"], "name": r["name"], "size": r["size"], "chunks": r["n_chunks"],
             "embed_model": r["embed_model"], "created_at": r["created_at"]} for r in rows]


@app.post("/api/documents", status_code=202)
async def upload_documents(files: list[UploadFile] = File(...)) -> dict:
    payloads: list[tuple[str, bytes]] = []
    for f in files:
        raw_name = f.filename or "senza-nome"
        # Browser directory uploads expose a relative path; keep it, but prevent path traversal.
        name = str(Path(raw_name.replace("\\", "/"))).replace("..", "_").lstrip("/\\")
        data = await f.read()
        payloads.append((name, data))
    job_id = create_ingest_job(payloads, get_settings())
    return {"job_id": job_id, "status": "queued", "job": _job_dict(job_id)}


@app.get("/api/ingest/jobs")
def ingest_jobs() -> dict:
    return {"jobs": recent_ingest_jobs()}


@app.get("/api/ingest/jobs/{job_id}")
def ingest_job(job_id: str) -> dict:
    return _job_dict(job_id)


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str) -> dict:
    doc = _doc_dict(doc_id)
    with tx() as c:
        rows = c.execute("SELECT idx, page, text FROM chunks WHERE doc_id = ? ORDER BY idx LIMIT 50", (doc_id,)).fetchall()
    return {**doc, "preview": [{"index": r["idx"], "page": r["page"], "text": r["text"]} for r in rows]}


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str) -> dict:
    _doc_dict(doc_id)
    _delete_document(doc_id)
    return {"deleted": doc_id}


@app.delete("/api/documents")
def delete_all_documents() -> dict:
    with tx() as c:
        n = c.execute("DELETE FROM documents").rowcount
    invalidate_cache()
    return {"deleted": n}


@app.post("/api/reindex")
def reindex() -> dict:
    """Rigenera gli embedding di tutti i documenti con il modello corrente."""
    s = get_settings()
    with tx() as c:
        rows = c.execute("SELECT id, text FROM chunks ORDER BY id").fetchall()
    if not rows:
        return {"reindexed_chunks": 0}
    try:
        vecs = embed([r["text"] for r in rows], s)
    except OllamaError as exc:
        raise HTTPException(503, str(exc)) from exc
    with tx() as c:
        c.executemany("UPDATE chunks SET embedding = ? WHERE id = ?", [(vecs[i].tobytes(), r["id"]) for i, r in enumerate(rows)])
        c.execute("UPDATE documents SET embed_model = ?", (s["embed_model"],))
    invalidate_cache()
    return {"reindexed_chunks": len(rows)}


@app.post("/api/search")
def search_endpoint(body: SearchRequest) -> dict:
    s = get_settings()
    if not body.query.strip():
        raise HTTPException(422, "La query è vuota.")
    try:
        return {"results": search(body.query, body.top_k or s["top_k"], s)}
    except OllamaError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.post("/api/chat")
def chat(body: ChatRequest):
    message = body.message.strip()
    if not message:
        raise HTTPException(422, "Il messaggio è vuoto.")
    events = run_chat(message, body.conversation_id)
    if body.stream:
        def sse() -> Iterator[str]:
            for ev in events:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        return StreamingResponse(sse(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
    answer, sources, conv = "", [], body.conversation_id
    for ev in events:
        if ev["type"] == "error":
            raise HTTPException(503 if "Ollama" in ev["message"] or "Modello" in ev["message"] else 404, ev["message"])
        if ev["type"] == "meta":
            conv = ev["conversation_id"]
        elif ev["type"] == "sources":
            sources = ev["sources"]
        elif ev["type"] == "token":
            answer += ev["content"]
    return {"conversation_id": conv, "answer": answer, "sources": sources}


@app.get("/api/conversations")
def list_conversations() -> list[dict]:
    with tx() as c:
        rows = c.execute("SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


@app.get("/api/conversations/{conv_id}")
def get_conversation(conv_id: str) -> dict:
    with tx() as c:
        conv = c.execute("SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?", (conv_id,)).fetchone()
        if not conv:
            raise HTTPException(404, "Conversazione non trovata.")
        msgs = c.execute("SELECT role, content, sources, created_at FROM messages WHERE conv_id = ? ORDER BY id", (conv_id,)).fetchall()
    return {**dict(conv), "messages": [
        {"role": m["role"], "content": m["content"], "sources": json.loads(m["sources"]) if m["sources"] else [],
         "created_at": m["created_at"]} for m in msgs]}


@app.patch("/api/conversations/{conv_id}")
def rename_conversation(conv_id: str, body: RenameRequest) -> dict:
    with tx() as c:
        if not c.execute("UPDATE conversations SET title = ? WHERE id = ?", (body.title.strip(), conv_id)).rowcount:
            raise HTTPException(404, "Conversazione non trovata.")
    return {"id": conv_id, "title": body.title.strip()}


@app.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: str) -> dict:
    with tx() as c:
        if not c.execute("DELETE FROM conversations WHERE id = ?", (conv_id,)).rowcount:
            raise HTTPException(404, "Conversazione non trovata.")
    return {"deleted": conv_id}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
