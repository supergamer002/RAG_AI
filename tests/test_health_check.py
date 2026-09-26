import pytest
from fastapi.testclient import TestClient
from webapp.backend import main
from unittest.mock import patch, MagicMock

client = TestClient(main.app)

def test_health_ollama_ok():
    with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
        mock_get.return_value.status_code = 200
        mock_post.return_value.status_code = 200
        
        response = client.get("/api/health")
        data = response.json()
        assert response.status_code == 200
        assert data["ollama"] is True
        assert data["ollama_detail"] == "OK"

def test_health_ollama_unreachable():
    with patch('requests.get') as mock_get:
        mock_get.side_effect = Exception("Connection refused")
        
        response = client.get("/api/health")
        data = response.json()
        assert response.status_code == 200
        assert data["ollama"] is False
        assert "Errore connessione" in data["ollama_detail"]

def test_health_embedding_model_missing():
    with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
        mock_get.return_value.status_code = 200
        mock_post.return_value.status_code = 404
        
        response = client.get("/api/health")
        data = response.json()
        assert response.status_code == 200
        assert data["ollama"] is False
        assert "non disponibile" in data["ollama_detail"]
