import pytest
from fastapi.testclient import TestClient
from webapp.backend import main
from unittest.mock import MagicMock, patch

client = TestClient(main.app)

def test_query_endpoint(monkeypatch):
    mock_embedder = MagicMock()
    mock_embedder.embed_uno.return_value = [0.1] * 1024
    mock_embedder.embed.side_effect = lambda texts: [[0.1] * 1024] * len(texts)
    
    # Patch the manager's get_embedder method
    monkeypatch.setattr("webapp.backend.main.embedder_manager.get_embedder", lambda m, u: mock_embedder)
    
    res = client.post("/api/query", json={"query": "Test chimica legame ionico", "topK": 5, "topN": 2})
    assert res.status_code == 200

def test_query_endpoint_modes(monkeypatch):
    mock_embedder = MagicMock()
    mock_embedder.embed_uno.return_value = [0.1] * 1024
    mock_embedder.embed.side_effect = lambda texts: [[0.1] * 1024] * len(texts)
    
    monkeypatch.setattr("webapp.backend.main.embedder_manager.get_embedder", lambda m, u: mock_embedder)
    
    res_dense = client.post("/api/query", json={"query": "Test dense", "searchMode": "dense", "enableRerank": False})
    assert res_dense.status_code == 200

    res_sparse = client.post("/api/query", json={"query": "Test sparse", "searchMode": "sparse", "enableRerank": False})
    assert res_sparse.status_code == 200
