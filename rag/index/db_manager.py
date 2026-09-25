"""Gestore multi-database per LanceDB.

Permette di creare, elencare, attivare, rinominare, eliminare, importare
ed esportare istanze indipendenti di LanceDB salvate in `data/databases/`.
"""

from __future__ import annotations

import json
import shutil
import uuid
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import lancedb

from rag.index.store import connetti, apri_o_crea_tabella
from rag.retrieve.hybrid_search import crea_indice_fulltext

BASE_DB_DIR = Path("data/databases")
REGISTRY_PATH = BASE_DB_DIR / "registry.json"


class DatabaseManager:
    def __init__(self, base_dir: Path = BASE_DB_DIR) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.base_dir / "registry.json"
        self._load_registry()

    def _load_registry(self) -> None:
        if self.registry_file.exists():
            try:
                with self.registry_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.active_id = data.get("activeDatabase", "default")
                    self.databases = data.get("databases", [])
                    if self.databases:
                        return
            except Exception:
                pass

        # Inizializza registry con il database di default
        default_db = {
            "id": "default",
            "name": "Database Primario RAG",
            "path": str((self.base_dir / "default_lancedb").resolve()),
            "createdAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "embeddingModel": "qwen3-embedding:0.6b",
            "dimension": 1024,
        }
        self.active_id = "default"
        self.databases = [default_db]
        self._save_registry()

    def _save_registry(self) -> None:
        data = {
            "activeDatabase": self.active_id,
            "databases": self.databases,
        }
        with self.registry_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def list_databases(self) -> List[Dict[str, Any]]:
        return self.databases

    def get_active_info(self) -> Dict[str, Any]:
        for db in self.databases:
            if db["id"] == self.active_id:
                return db
        return self.databases[0]

    def get_active_table(self, table_name: str = "chunks") -> lancedb.table.Table:
        active_info = self.get_active_info()
        db_path = active_info["path"]
        conn = connetti(db_path)
        tabella = apri_o_crea_tabella(conn, dimensione_embedding=active_info.get("dimension", 1024))
        try:
            crea_indice_fulltext(tabella)
        except Exception:
            pass
        return tabella

    def create_database(self, name: str, embedding_model: str = "qwen3-embedding:0.6b", dimension: int = 1024) -> Dict[str, Any]:
        db_id = f"db_{uuid.uuid4().hex[:8]}"
        db_path = (self.base_dir / db_id).resolve()
        db_info = {
            "id": db_id,
            "name": name,
            "path": str(db_path),
            "createdAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "embeddingModel": embedding_model,
            "dimension": dimension,
        }

        # Inizializza tabella vuota
        conn = connetti(str(db_path))
        apri_o_crea_tabella(conn, dimensione_embedding=dimension)

        self.databases.append(db_info)
        self._save_registry()
        return db_info

    def activate_database(self, db_id: str) -> Dict[str, Any]:
        target = next((db for db in self.databases if db["id"] == db_id), None)
        if not target:
            raise KeyError(f"Database '{db_id}' non trovato")

        self.active_id = db_id
        target["updatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save_registry()
        return target

    def rename_database(self, db_id: str, new_name: str) -> Dict[str, Any]:
        target = next((db for db in self.databases if db["id"] == db_id), None)
        if not target:
            raise KeyError(f"Database '{db_id}' non trovato")

        target["name"] = new_name
        target["updatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save_registry()
        return target

    def delete_database(self, db_id: str) -> bool:
        if db_id == self.active_id:
            raise ValueError("Impossibile eliminare il database attualmente attivo.")

        target = next((db for db in self.databases if db["id"] == db_id), None)
        if not target:
            return False

        db_path = Path(target["path"])
        if db_path.exists():
            shutil.rmtree(db_path, ignore_errors=True)

        self.databases = [db for db in self.databases if db["id"] != db_id]
        self._save_registry()
        return True

    def export_database(self, db_id: str) -> Path:
        target = next((db for db in self.databases if db["id"] == db_id), None)
        if not target:
            raise KeyError(f"Database '{db_id}' non trovato")

        db_path = Path(target["path"])
        export_zip = self.base_dir / f"export_{db_id}_{int(time.time())}.zip"
        shutil.make_archive(str(export_zip.with_suffix("")), "zip", db_path)
        return export_zip.with_suffix(".zip")


db_manager = DatabaseManager()
