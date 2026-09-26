import pytest
from fastapi.testclient import TestClient
from webapp.backend import main
import os
import shutil
from pathlib import Path
import time
import json
from unittest.mock import MagicMock

# Patch the embedder
main.embedder = MagicMock()
def mock_embed(texts):
    return [[0.1] * 1024] * len(texts)
main.embedder.embed.side_effect = mock_embed

client = TestClient(main.app)

def test_batch_ingest_fonte_path():
    test_dir = Path("test_sources")
    test_dir.mkdir(exist_ok=True)
    test_file = test_dir / "test.json"
    content = [{"titolo": "Test Doc", "testo": "This is a test sentence. It has punctuation. It should be a chunk."}, 
               {"titolo": "Test Doc", "testo": "Another sentence here. This is a second unit. It must produce chunks."}]
    test_file.write_text(json.dumps(content))

    with open(test_file, 'rb') as f:
        files = [('files', ('test.json', f, 'application/json'))]
        response = client.post("/api/ingest", files=files)
    
    assert response.status_code == 200
    job_id = response.json()["jobId"]
    for _ in range(20):
        status_res = client.get(f"/api/ingest/status/{job_id}")
        status_data = status_res.json()
        if status_data["status"] == "completed":
            break
        if status_data["status"] == "failed":
            print(f"Job failed: {status_data}")
            pytest.fail("Ingest job failed")
        time.sleep(0.5)
    
    docs_res = client.get("/api/documents")
    docs = docs_res.json()
    print(f"Available docs: {docs}")
    
    doc = next((d for d in docs if "test.json" in d["sourcePath"]), None)
    assert doc is not None, f"Document not found. Available docs: {docs}"
    assert doc["sourcePath"].startswith("sources/"), f"Got {doc['sourcePath']}"
    shutil.rmtree(test_dir, ignore_errors=True)
