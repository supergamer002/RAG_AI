import json
from pathlib import Path

from rag.index.db_manager import DatabaseManager


def test_legacy_absolute_paths_are_migrated(tmp_path: Path):
    base_dir = tmp_path / "databases"
    base_dir.mkdir(parents=True)
    registry = base_dir / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "activeDatabase": "default",
                "databases": [
                    {
                        "id": "default",
                        "name": "Database Primario RAG",
                        "path": "/app/data/databases/default_lancedb",
                        "createdAt": "2026-09-25 14:51:44",
                        "updatedAt": "2026-09-25 14:51:44",
                        "embeddingModel": "qwen3-embedding:0.6b",
                        "dimension": 1024,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manager = DatabaseManager(base_dir=base_dir)
    info = manager.get_info_for_id("default")

    assert info["folderName"] == "default_lancedb"
    assert "path" not in next(iter(manager.databases))
    assert info["path"] == str((base_dir / "default_lancedb").resolve())

    saved = json.loads(registry.read_text(encoding="utf-8"))
    saved_db = saved["databases"][0]
    assert saved_db["folderName"] == "default_lancedb"
    assert "path" not in saved_db
