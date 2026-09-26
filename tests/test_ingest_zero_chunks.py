import pytest
from fastapi.testclient import TestClient
from webapp.backend import main
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock

# Mock embedder
main.embedder = MagicMock()
main.embedder.embed.side_effect = lambda texts: [[0.1]*1024 for _ in texts]

client = TestClient(main.app)

def test_ingest_zero_chunks_fails():
    test_dir = Path("test_zero_chunks")
    test_dir.mkdir(exist_ok=True)
    test_file = test_dir / "empty.json"
    # JSON that produces no chunks (empty list or empty text)
    test_file.write_text("[]")

    with open(test_file, 'rb') as f:
        files = [('files', ('empty.json', f, 'application/json'))]
        response = client.post("/api/ingest", files=files)
    
    assert response.status_code == 200
    job_id = response.json()["jobId"]
    
    # Wait for job
    import time
    for _ in range(20):
        status_res = client.get(f"/api/ingest/status/{job_id}")
        status_data = status_res.json()
        if status_data["status"] == "failed":
            # This is the EXPECTED behavior after the fix
            break
        if status_data["status"] == "completed":
            # CURRENT behavior: it's marked as completed even if 0 chunks
            pytest.fail("Job should have failed due to zero chunks created")
        time.sleep(0.5)
    
    assert status_res.json()["status"] == "failed"
    shutil.rmtree(test_dir, ignore_errors=True)
