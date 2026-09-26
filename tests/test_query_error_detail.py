import pytest
from fastapi.testclient import TestClient
from webapp.backend import main
from unittest.mock import patch

client = TestClient(main.app)

def test_query_error_detail():
    # Mock _esegui_query_su_tabella to raise an exception
    with patch('webapp.backend.main._esegui_query_su_tabella') as mock_query:
        mock_query.side_effect = RuntimeError("Something went wrong in the pipeline")
        
        response = client.post("/api/query", json={"query": "test query"})
        
        assert response.status_code == 503
        detail = response.json()["detail"]
        assert "RuntimeError" in detail
        assert "Something went wrong in the pipeline" in detail
