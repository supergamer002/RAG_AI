"""Test per gli endpoint backend FastAPI in webapp/backend/main.py"""

import pytest
from fastapi.testclient import TestClient
from webapp.backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_root_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "RAG AI Backend"}


def test_health_endpoint(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert "fastapi" in data
    assert "lancedb" in data
    assert "ollama" in data


def test_settings_endpoints(client):
    res_get = client.get("/api/settings")
    assert res_get.status_code == 200
    cfg = res_get.json()
    assert "tableName" in cfg

    res_put = client.put("/api/settings", json={"logLevel": "DEBUG"})
    assert res_put.status_code == 200
    assert res_put.json()["logLevel"] == "DEBUG"


def test_telemetry_endpoint(client):
    res = client.get("/api/telemetry")
    assert res.status_code == 200
    logs = res.json()
    assert isinstance(logs, list)
    assert len(logs) >= 1


def test_eval_endpoint(client):
    res = client.get("/api/eval")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_documents_and_chunks_endpoints(client):
    res_docs = client.get("/api/documents")
    assert res_docs.status_code == 200
    assert isinstance(res_docs.json(), list)

    res_chunks = client.get("/api/chunks?page=1&pageSize=5")
    assert res_chunks.status_code == 200
    data = res_chunks.json()
    assert "items" in data
    assert "total" in data


def test_query_endpoint(client, monkeypatch):
    monkeypatch.setattr("webapp.backend.main.embedder.embed_uno", lambda q: [0.1] * 1024)
    res = client.post("/api/query", json={"query": "Test chimica legame ionico", "topK": 5, "topN": 2})
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "chunks" in data


def test_query_endpoint_modes(client, monkeypatch):
    monkeypatch.setattr("webapp.backend.main.embedder.embed_uno", lambda q: [0.1] * 1024)
    res_dense = client.post("/api/query", json={"query": "Test dense", "searchMode": "dense", "enableRerank": False})
    assert res_dense.status_code == 200

    res_sparse = client.post("/api/query", json={"query": "Test sparse", "searchMode": "sparse", "enableRerank": False})
    assert res_sparse.status_code == 200
