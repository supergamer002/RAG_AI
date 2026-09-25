"""Gestore multi-database per LanceDB.

Permette di creare, elencare, attivare, rinominare, eliminare, importare
ed esportare istanze indipendenti di LanceDB salvate in `data/databases/`.
"""

from __future__ import annotations

import json
import shutil
import uuid
import time
import zipfile
import re
import threading
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
        self._lock = threading.RLock()
        self._load_registry()

    def _load_registry(self) -> None:
        if self.registry_file.exists():
            try:
                with self.registry_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.active_id = data.get("activeDatabase", "default")
                    self.databases = data.get("databases", [])
                    if self.databases:
                        if self._migrate_legacy_paths():
                            self._save_registry()
                        return
            except Exception:
                pass

        # Inizializza registry con il database di default (usando relative folder name)
        default_db = {
            "id": "default",
            "name": "Database Primario RAG",
            "folderName": "default_lancedb",
            "createdAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "embeddingModel": "qwen3-embedding:0.6b",
            "dimension": 1024,
        }
        self.active_id = "default"
        self.databases = [default_db]
        self._save_registry()

    def _migrate_legacy_paths(self) -> bool:
        """Converte i vecchi path assoluti in folderName portabili.

        Il vecchio formato salvava, ad esempio, ``/app/data/databases/foo``.
        Quel path non è riutilizzabile dopo aver spostato il progetto su
        un'altra macchina/container. Per ogni database privo di folderName
        ricaviamo il nome della cartella dal path esistente e rimuoviamo il
        campo legacy.
        """
        changed = False
        for db_info in self.databases:
            if db_info.get("folderName"):
                continue

            legacy_path = db_info.get("path")
            if legacy_path:
                # Gestisce sia path POSIX (/app/...) sia vecchi path Windows (C:\\...).
                normalized_legacy_path = str(legacy_path).replace("\\", "/")
                folder_name = Path(normalized_legacy_path).name
            else:
                folder_name = str(db_info.get("id") or "default")

            if not folder_name or folder_name in {".", ".."}:
                folder_name = str(db_info.get("id") or "default")

            db_info["folderName"] = folder_name
            db_info.pop("path", None)
            changed = True

        return changed

    def _save_registry(self) -> None:
        data = {
            "activeDatabase": self.active_id,
            "databases": self.databases,
        }
        tmp = self.registry_file.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
        tmp.replace(self.registry_file)

    @staticmethod
    def _validate_name(name: str) -> str:
        value = str(name or "").strip()
        if not value:
            raise ValueError("Nome database non valido: vuoto.")
        if len(value) > 100:
            raise ValueError("Nome database non valido: massimo 100 caratteri.")
        if any(ord(ch) < 32 for ch in value):
            raise ValueError("Nome database non valido: contiene caratteri di controllo.")
        return value

    def _refresh_registry(self) -> None:
        """Rilegge il registry per evitare stato active_id obsoleto tra worker/processi."""
        with self._lock:
            if not self.registry_file.exists():
                return
            try:
                with self.registry_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                databases = data.get("databases", [])
                active_id = data.get("activeDatabase")
                if isinstance(databases, list) and databases:
                    self.databases = databases
                    if active_id and any(db.get("id") == active_id for db in databases):
                        self.active_id = active_id
            except (OSError, json.JSONDecodeError):
                return

    def _get_path_for_info(self, db_info: Dict[str, Any]) -> str:
        folder = db_info.get("folderName")
        if folder:
            return str((self.base_dir / folder).resolve())
        return db_info.get("path", str((self.base_dir / "default_lancedb").resolve()))

    def list_databases(self) -> List[Dict[str, Any]]:
        self._refresh_registry()
        res = []
        for db in self.databases:
            info = dict(db)
            info["path"] = self._get_path_for_info(db)
            res.append(info)
        return res

    def get_info_for_id(self, db_id: str) -> Dict[str, Any]:
        self._refresh_registry()
        for db in self.databases:
            if db["id"] == db_id:
                info = dict(db)
                info["path"] = self._get_path_for_info(db)
                return info
        raise KeyError(f"Database '{db_id}' non trovato")

    def get_active_info(self) -> Dict[str, Any]:
        self._refresh_registry()
        return self.get_info_for_id(self.active_id)

    def get_table_for_db(self, db_id: str, table_name: str = "chunks") -> lancedb.table.Table:
        info = self.get_info_for_id(db_id)
        db_path = info["path"]
        conn = connetti(db_path)
        tabella = apri_o_crea_tabella(conn, dimensione_embedding=info.get("dimension", 1024))
        try:
            crea_indice_fulltext(tabella)
        except Exception:
            pass
        return tabella

    def get_active_table(self, table_name: str = "chunks") -> lancedb.table.Table:
        return self.get_table_for_db(self.active_id, table_name)

    def create_database(self, name: str, embedding_model: str = "qwen3-embedding:0.6b", dimension: int = 1024) -> Dict[str, Any]:
        name = self._validate_name(name)
        if not isinstance(dimension, int) or dimension <= 0:
            raise ValueError("Dimensione embedding non valida.")
        self._refresh_registry()
        db_id = f"db_{uuid.uuid4().hex[:8]}"
        folder_name = db_id
        db_path = (self.base_dir / folder_name).resolve()
        db_info = {
            "id": db_id,
            "name": name,
            "folderName": folder_name,
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
        res = dict(db_info)
        res["path"] = str(db_path)
        return res

    def activate_database(self, db_id: str) -> Dict[str, Any]:
        self._refresh_registry()
        target = next((db for db in self.databases if db["id"] == db_id), None)
        if not target:
            raise KeyError(f"Database '{db_id}' non trovato")

        self.active_id = db_id
        target["updatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save_registry()
        return target

    def rename_database(self, db_id: str, new_name: str) -> Dict[str, Any]:
        new_name = self._validate_name(new_name)
        self._refresh_registry()
        target = next((db for db in self.databases if db["id"] == db_id), None)
        if not target:
            raise KeyError(f"Database '{db_id}' non trovato")

        target["name"] = new_name
        target["updatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save_registry()
        return target

    def delete_database(self, db_id: str) -> bool:
        self._refresh_registry()
        if db_id == self.active_id:
            raise ValueError("Impossibile eliminare il database attualmente attivo.")

        target = next((db for db in self.databases if db["id"] == db_id), None)
        if not target:
            return False

        # Risolvi sempre il percorso tramite la gestione centralizzata,
        # così funziona anche con il nuovo formato folderName.
        db_path = Path(self._get_path_for_info(target)).resolve()
        base_dir = self.base_dir.resolve()

        # Non consentire mai la cancellazione della directory base o di
        # percorsi esterni al contenitore dei database.
        try:
            db_path.relative_to(base_dir)
        except ValueError as exc:
            raise OSError(
                f"Percorso database non sicuro per '{db_id}': {db_path}"
            ) from exc

        if db_path == base_dir:
            raise OSError("Impossibile eliminare la directory base dei database.")

        # Se il percorso esiste, la cancellazione deve riuscire davvero.
        # In caso di errore il registry resta invariato.
        if db_path.exists():
            if not db_path.is_dir():
                raise OSError(f"Il percorso del database non è una directory: {db_path}")
            try:
                shutil.rmtree(db_path)
            except OSError as exc:
                raise OSError(
                    f"Impossibile eliminare il database '{db_id}': {exc}"
                ) from exc

            if db_path.exists():
                raise OSError(
                    f"Eliminazione del database '{db_id}' non verificata: la directory esiste ancora."
                )

        # Modifica il registry solo dopo aver verificato la rimozione fisica.
        self.databases = [db for db in self.databases if db["id"] != db_id]
        self._save_registry()
        return True

    def export_database(self, db_id: str) -> Path:
        self._refresh_registry()
        target = self.get_info_for_id(db_id)
        if not target:
            raise KeyError(f"Database '{db_id}' non trovato")

        db_path = Path(target["path"])
        export_zip = self.base_dir / f"export_{db_id}_{int(time.time())}.zip"
        shutil.make_archive(str(export_zip.with_suffix("")), "zip", db_path)
        return export_zip.with_suffix(".zip")

    def _validate_zip_members(self, archive: zipfile.ZipFile) -> None:
        """Valida i membri ZIP prima dell'estrazione.

        Blocca path traversal, symlink e archivi eccessivamente grandi/complessi.
        """
        max_members = 10000
        max_uncompressed_bytes = 10 * 1024 * 1024 * 1024  # 10 GiB
        members = archive.infolist()
        if not members:
            raise ValueError("Archivio ZIP vuoto.")
        if len(members) > max_members:
            raise ValueError(f"Archivio ZIP non valido: troppi file ({len(members)}).")

        total_size = 0
        for member in members:
            name = member.filename.replace("\\", "/")
            if not name or name.startswith("/"):
                raise ValueError("Archivio ZIP non valido: percorso assoluto.")

            parts = [part for part in name.split("/") if part not in ("", ".")]
            if ".." in parts:
                raise ValueError("Archivio ZIP non valido: path traversal rilevato.")

            # Unix mode: il bit del symlink e' 0120000. Non estrarre link
            # simbolici, che potrebbero puntare fuori dalla directory target.
            file_type = (member.external_attr >> 16) & 0o170000
            if file_type == 0o120000:
                raise ValueError("Archivio ZIP non valido: symlink non consentito.")

            total_size += member.file_size
            if total_size > max_uncompressed_bytes:
                raise ValueError("Archivio ZIP troppo grande dopo l'estrazione.")

    def _validate_imported_database(self, db_root: Path) -> int:
        """Verifica che l'archivio contenga una tabella LanceDB 'chunks'.

        Non usa apri_o_crea_tabella: un import non deve mai creare una tabella
        vuota quando l'archivio e' corrotto o non e' realmente un database RAG.
        Ritorna la dimensione del vettore presente nello schema.
        """
        chunks_dir = db_root / "chunks.lance"
        if not chunks_dir.is_dir():
            raise ValueError("Archivio non valido: tabella LanceDB 'chunks' non trovata.")

        try:
            conn = lancedb.connect(str(db_root))
            table = conn.open_table("chunks")
            schema = table.schema
            if "vector" not in schema.names:
                raise ValueError("Archivio non valido: campo 'vector' assente nello schema.")

            vector_field = schema.field("vector")
            vector_type = vector_field.type
            dimension = getattr(vector_type, "list_size", None)
            if not isinstance(dimension, int) or dimension <= 0:
                raise ValueError("Archivio non valido: dimensione del vettore non determinabile.")
            return dimension
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Archivio non valido o tabella LanceDB illeggibile: {exc}") from exc

    def import_database(self, zip_path: Path, name: str) -> Dict[str, Any]:
        name = self._validate_name(name)
        self._refresh_registry()
        db_id = f"db_{uuid.uuid4().hex[:8]}"
        folder_name = db_id
        target_dir = (self.base_dir / folder_name).resolve()
        base_dir = self.base_dir.resolve()
        target_dir.relative_to(base_dir)

        staging_dir = (self.base_dir / f".import_{uuid.uuid4().hex}").resolve()
        staging_dir.relative_to(base_dir)

        try:
            try:
                with zipfile.ZipFile(zip_path, "r") as archive:
                    if archive.testzip() is not None:
                        raise ValueError("Archivio ZIP corrotto.")
                    self._validate_zip_members(archive)
                    archive.extractall(staging_dir)
            except zipfile.BadZipFile as exc:
                raise ValueError("Archivio ZIP non valido o corrotto.") from exc

            # Supporta sia gli export attuali (chunks.lance alla radice) sia
            # eventuali archivi con un singolo contenitore esterno.
            db_root = staging_dir
            if not (db_root / "chunks.lance").is_dir():
                top_level = [p for p in db_root.iterdir()]
                dirs = [p for p in top_level if p.is_dir()]
                files = [p for p in top_level if p.is_file()]
                if len(dirs) == 1 and not files and (dirs[0] / "chunks.lance").is_dir():
                    db_root = dirs[0]
                else:
                    raise ValueError("Archivio non valido: struttura LanceDB non riconosciuta.")

            dimension = self._validate_imported_database(db_root)

            # Sposta solo il contenuto gia' validato nella destinazione finale.
            target_dir.mkdir(parents=True, exist_ok=False)
            for item in db_root.iterdir():
                shutil.move(str(item), str(target_dir / item.name))

            db_info = {
                "id": db_id,
                "name": name,
                "folderName": folder_name,
                "createdAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                "updatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                "embeddingModel": "imported/unknown",
                "dimension": dimension,
            }

            self.databases.append(db_info)
            try:
                self._save_registry()
            except Exception:
                self.databases.pop()
                shutil.rmtree(target_dir, ignore_errors=True)
                raise

            res = dict(db_info)
            res["path"] = str(target_dir)
            return res
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)


db_manager = DatabaseManager()
