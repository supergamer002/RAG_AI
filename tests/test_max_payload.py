import pytest
from fastapi.testclient import TestClient
from webapp.backend import main
from pathlib import Path
import json

client = TestClient(main.app)

def test_max_payload_enforcement():
    main.config["maxPayloadMB"] = 1 # 1 MB
    test_file = Path("large_test.json")
    content = [{"text": "0" * 2000000, "title": "Big"}]
    test_file.write_text(json.dumps(content))
    
    try:
        with open(test_file, 'rb') as f:
            files = [('files', ('large.json', f, 'application/json'))]
            response = client.post("/api/ingest", files=files)
        
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
        assert response.status_code == 413
    finally:
        test_file.unlink(missing_ok=True)

def test_max_payload_allowed():
    main.config["maxPayloadMB"] = 10
    test_file = Path("small_test.json")
    test_file.write_text(json.dumps([{"text": "small", "title": "Small"}]))
    
    try:
        with open(test_file, 'rb') as f:
            files = [('files', ('small.json', f, 'application/json'))]
            response = client.post("/api/ingest", files=files)
        
        assert response.status_code == 200
    finally:
        test_file.unlink(missing_ok=True)
