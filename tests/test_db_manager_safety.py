from pathlib import Path

import pytest

from rag.index.db_manager import DatabaseManager


def test_get_info_for_id_nonexistent_does_not_fallback(tmp_path: Path):
    manager = DatabaseManager(base_dir=tmp_path / "databases")

    with pytest.raises(KeyError, match="non-esistente"):
        manager.get_info_for_id("non-esistente")


def test_get_active_info_still_returns_active_database(tmp_path: Path):
    manager = DatabaseManager(base_dir=tmp_path / "databases")

    info = manager.get_active_info()

    assert info["id"] == manager.active_id == "default"
