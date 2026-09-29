"""Test end-to-end del backend con un Ollama simulato (nessun modello reale richiesto)."""

import hashlib
import json
import os
import re
import tempfile
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

DIM = 64


def wait_job(client, job_id, timeout=5):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = client.get(f"/api/ingest/jobs/{job_id}").json()
        if last["status"] in {"ready", "partial", "failed"}:
            return last
        time.sleep(0.02)
    raise AssertionError(f"Job non completato: {last}")


def fake_embed(text: str) -> list[float]:
    v = [0.0] * DIM
    for w in re.findall(r"\w+", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0
    return v


class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._json({"models": [{"name": "qwen3:8b"}, {"name": "qwen3-embedding:0.6b"}]})

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/embed":
            self._json({"embeddings": [fake_embed(t) for t in data["input"]]})
        elif self.path == "/api/chat":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for piece in ["<think>ragiono</think>", "Risposta ", "di prova [1]."]:
                self.wfile.write((json.dumps({"message": {"content": piece}, "done": False}) + "\n").encode())
            self.wfile.write((json.dumps({"message": {"content": ""}, "done": True}) + "\n").encode())
        else:
            self._json({}, 404)


@pytest.fixture(scope="module")
def client():
    server = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ["RAG_DATA_DIR"] = tempfile.mkdtemp()
    os.environ["RAG_AUTOSETUP"] = "0"
    os.environ["OLLAMA_URL"] = f"http://127.0.0.1:{server.server_port}"
    from fastapi.testclient import TestClient

    from app import main

    with TestClient(main.app) as c:
        main.STATE.update(ollama_up=True, installed=["qwen3:8b", "qwen3-embedding:0.6b"])
        yield c
    server.shutdown()


def test_health_and_index(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert "RAG" in client.get("/").text


def test_status_ready(client):
    st = client.get("/api/status").json()
    assert st["ready"] is True and st["documents"] == 0


def test_upload_search_chat_flow(client):
    files = [
        ("files", ("gatti.txt", b"I gatti dormono molte ore al giorno e amano il sole.", "text/plain")),
        ("files", ("spazio.md", b"Marte e' il quarto pianeta del sistema solare.", "text/plain")),
        ("files", ("bin.dat", b"\x00\x01\x02", "application/octet-stream")),
    ]
    res = client.post("/api/documents", files=files)
    assert res.status_code == 202
    job = wait_job(client, res.json()["job_id"])
    assert job["status"] == "partial"
    assert [f["status"] for f in job["files"]] == ["ready", "ready", "failed"]
    assert len(client.get("/api/documents").json()) == 2

    hits = client.post("/api/search", json={"query": "quanto dormono i gatti", "top_k": 1}).json()["results"]
    assert hits[0]["document"] == "gatti.txt"

    ans = client.post("/api/chat", json={"message": "Come dormono i gatti?", "stream": False}).json()
    assert ans["answer"] == "Risposta di prova [1]."
    assert ans["sources"] and ans["conversation_id"]

    with client.stream("POST", "/api/chat", json={"message": "E Marte?", "conversation_id": ans["conversation_id"]}) as r:
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    types = [e["type"] for e in events]
    assert types[0] == "meta" and "sources" in types and types[-1] == "done"
    assert "".join(e["content"] for e in events if e["type"] == "token") == "Risposta di prova [1]."

    conv = client.get(f"/api/conversations/{ans['conversation_id']}").json()
    assert len(conv["messages"]) == 4
    client.patch(f"/api/conversations/{ans['conversation_id']}", json={"title": "Gatti"})
    assert client.get("/api/conversations").json()[0]["title"] == "Gatti"
    assert client.delete(f"/api/conversations/{ans['conversation_id']}").status_code == 200


def test_reupload_replaces_and_delete(client):
    res = client.post("/api/documents", files=[("files", ("gatti.txt", b"Nuovo testo sui gatti.", "text/plain"))])
    wait_job(client, res.json()["job_id"])
    docs = client.get("/api/documents").json()
    assert sum(d["name"] == "gatti.txt" for d in docs) == 1
    assert client.delete(f"/api/documents/{docs[0]['id']}").status_code == 200
    assert client.delete("/api/documents/nope").status_code == 404
    assert client.delete("/api/documents").json()["deleted"] == 1


def test_folder_paths_are_preserved(client):
    files = [
        ("files", ("corso\\capitolo1\\lezione.txt", b"Contenuto uno.", "text/plain")),
        ("files", ("corso\\capitolo2\\lezione.txt", b"Contenuto due.", "text/plain")),
    ]
    res = client.post("/api/documents", files=files)
    job = wait_job(client, res.json()["job_id"])
    assert job["status"] == "ready"
    names = {d["name"] for d in client.get("/api/documents").json()}
    assert "corso/capitolo1/lezione.txt" in names or "corso\\capitolo1\\lezione.txt" in names
    assert "corso/capitolo2/lezione.txt" in names or "corso\\capitolo2\\lezione.txt" in names


def test_empty_kb_chat_and_settings(client):
    client.delete("/api/documents")
    ans = client.post("/api/chat", json={"message": "ciao", "stream": False}).json()
    assert "non hai ancora caricato" in ans["answer"].lower()
    assert client.put("/api/settings", json={"top_k": 8}).json()["top_k"] == 8
    assert client.put("/api/settings", json={"chunk_size": 300, "chunk_overlap": 400}).status_code == 422
    assert client.post("/api/settings/reset").json()["top_k"] == 5
    assert client.post("/api/reindex").json()["reindexed_chunks"] == 0


def test_pdf_structural_extraction_and_segmentation():
    import pymupdf
    from app.main import extract_pages, chunk_text

    doc = pymupdf.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"CHAPTER {i + 1}", fontsize=18)
        page.insert_text((72, 110), " ".join(f"Heat transfer process engineering and mass balance analysis, sentence {j}, page {i}." for j in range(20)), fontsize=12)
    data = doc.tobytes()
    doc.close()

    pages = extract_pages("sample.pdf", data)
    assert len(pages) == 3
    assert any("##H1##" in text for _, text in pages)
    chunks = chunk_text("\n".join(text for _, text in pages), 1000, 150)
    assert chunks
    assert all(chunk.strip() for chunk in chunks)
