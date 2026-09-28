"""Test estesi per rag.index.db_manager.DatabaseManager.

tests/test_db_manager_safety.py e tests/test_registry_migration.py coprono
gia' get_info_for_id/get_active_info e la migrazione dei path legacy. Qui
copriamo il resto del ciclo di vita: create/activate/rename/delete,
export/import (incluse le validazioni di sicurezza sullo zip) e
_validate_name.

Ogni test usa un DatabaseManager isolato con base_dir=tmp_path, senza
toccare mai il registry reale dell'app.
"""

import json
import zipfile
from pathlib import Path

import pytest

from rag.index.db_manager import DatabaseManager
from rag.index.store import apri_o_crea_tabella, connetti, upsert_chunks
from rag.common.schema import Chunk, TipoFonte


@pytest.fixture
def manager(tmp_path: Path) -> DatabaseManager:
    return DatabaseManager(base_dir=tmp_path / "databases")


# --- _validate_name -------------------------------------------------------

def test_validate_name_vuoto_solleva():
    with pytest.raises(ValueError, match="vuoto"):
        DatabaseManager._validate_name("   ")


def test_validate_name_troppo_lungo_solleva():
    with pytest.raises(ValueError, match="100 caratteri"):
        DatabaseManager._validate_name("x" * 101)


def test_validate_name_caratteri_di_controllo_solleva():
    with pytest.raises(ValueError, match="controllo"):
        DatabaseManager._validate_name("nome\x00cattivo")


def test_validate_name_valido_viene_trimmato():
    assert DatabaseManager._validate_name("  Nome Buono  ") == "Nome Buono"


# --- init / registry -------------------------------------------------------

def test_init_crea_database_default(manager: DatabaseManager):
    assert manager.active_id == "default"
    assert len(manager.databases) == 1
    assert manager.databases[0]["id"] == "default"
    assert manager.registry_file.exists()


def test_init_ricarica_registry_esistente(tmp_path: Path):
    base = tmp_path / "databases"
    m1 = DatabaseManager(base_dir=base)
    m1.create_database("Secondo DB")
    m2 = DatabaseManager(base_dir=base)
    assert len(m2.databases) == 2
    assert any(db["name"] == "Secondo DB" for db in m2.databases)


# --- create_database ---------------------------------------------------

def test_create_database_dimensione_invalida_solleva(manager: DatabaseManager):
    with pytest.raises(ValueError, match="Dimensione"):
        manager.create_database("DB", dimension=0)
    with pytest.raises(ValueError, match="Dimensione"):
        manager.create_database("DB", dimension=-5)


def test_create_database_ritorna_info_e_registra(manager: DatabaseManager):
    info = manager.create_database("Nuovo DB", embedding_model="modelloX", dimension=8)
    assert info["name"] == "Nuovo DB"
    assert info["embeddingModel"] == "modelloX"
    assert info["dimension"] == 8
    assert Path(info["path"]).exists()
    assert len(manager.list_databases()) == 2


def test_create_database_inizializza_tabella_vuota(manager: DatabaseManager):
    info = manager.create_database("DB Vuoto", dimension=4)
    conn = connetti(info["path"])
    tabella = apri_o_crea_tabella(conn, dimensione_embedding=4)
    assert tabella.count_rows() == 0


# --- activate_database ---------------------------------------------------

def test_activate_database_inesistente_solleva(manager: DatabaseManager):
    with pytest.raises(KeyError):
        manager.activate_database("non-esiste")


def test_activate_database_cambia_active_id(manager: DatabaseManager):
    info = manager.create_database("DB2")
    manager.activate_database(info["id"])
    assert manager.active_id == info["id"]


# --- rename_database -------------------------------------------------------

def test_rename_database_inesistente_solleva(manager: DatabaseManager):
    with pytest.raises(KeyError):
        manager.rename_database("non-esiste", "Nuovo Nome")


def test_rename_database_valido(manager: DatabaseManager):
    info = manager.create_database("Nome Vecchio")
    aggiornato = manager.rename_database(info["id"], "Nome Nuovo")
    assert aggiornato["name"] == "Nome Nuovo"
    assert manager.get_info_for_id(info["id"])["name"] == "Nome Nuovo"


def test_rename_database_nome_invalido_solleva(manager: DatabaseManager):
    info = manager.create_database("DB")
    with pytest.raises(ValueError):
        manager.rename_database(info["id"], "")


# --- delete_database -------------------------------------------------------

def test_delete_database_attivo_solleva(manager: DatabaseManager):
    with pytest.raises(ValueError, match="attualmente attivo"):
        manager.delete_database("default")


def test_delete_database_inesistente_ritorna_false(manager: DatabaseManager):
    assert manager.delete_database("non-esiste") is False


def test_delete_database_rimuove_cartella_e_registro(manager: DatabaseManager):
    info = manager.create_database("Da Cancellare")
    db_path = Path(info["path"])
    assert db_path.exists()

    ok = manager.delete_database(info["id"])
    assert ok is True
    assert not db_path.exists()
    assert not any(db["id"] == info["id"] for db in manager.databases)


def test_delete_database_percorso_esterno_bloccato(manager: DatabaseManager, tmp_path):
    """Un folderName manomesso che punta fuori da base_dir non deve mai essere cancellato."""
    info = manager.create_database("DB Malevolo")
    esterno = tmp_path / "fuori_dalla_base"
    esterno.mkdir()
    (esterno / "marker.txt").write_text("non toccarmi")

    for db in manager.databases:
        if db["id"] == info["id"]:
            db["folderName"] = None
            db["path"] = str(esterno)
    manager._save_registry()  # persiste la manomissione, altrimenti _refresh_registry() la annullerebbe

    with pytest.raises(OSError, match="non sicuro"):
        manager.delete_database(info["id"])
    assert esterno.exists()
    assert (esterno / "marker.txt").exists()


# --- export_database / import_database --------------------------------

def _popola_db(path: str, dimensione: int = 4) -> None:
    conn = connetti(path)
    tabella = apri_o_crea_tabella(conn, dimensione_embedding=dimensione)
    chunk = Chunk(testo="Contenuto di prova", fonte_titolo="Fonte", tipo_fonte=TipoFonte.LIBRO)
    upsert_chunks(tabella, [chunk], [[0.1] * dimensione])


def test_export_import_round_trip(manager: DatabaseManager):
    info = manager.create_database("Originale", embedding_model="modelloY", dimension=4)
    _popola_db(info["path"], dimensione=4)

    zip_path = manager.export_database(info["id"])
    assert zip_path.exists()

    with zipfile.ZipFile(zip_path) as archive:
        assert "rag_database_metadata.json" in archive.namelist()

    imported = manager.import_database(zip_path, "Importato")
    assert imported["embeddingModel"] == "modelloY"
    assert imported["dimension"] == 4
    assert imported["id"] != info["id"]

    conn = connetti(imported["path"])
    tabella = apri_o_crea_tabella(conn, dimensione_embedding=4)
    assert tabella.count_rows() == 1


def test_export_database_inesistente_solleva(manager: DatabaseManager):
    with pytest.raises(KeyError):
        manager.export_database("non-esiste")


def test_import_database_zip_corrotto_solleva(manager: DatabaseManager, tmp_path):
    fake_zip = tmp_path / "corrotto.zip"
    fake_zip.write_bytes(b"non e' uno zip valido")
    with pytest.raises(ValueError, match="non valido o corrotto"):
        manager.import_database(fake_zip, "Corrotto")


def test_import_database_zip_vuoto_solleva(manager: DatabaseManager, tmp_path):
    empty_zip = tmp_path / "vuoto.zip"
    with zipfile.ZipFile(empty_zip, "w"):
        pass
    with pytest.raises(ValueError, match="vuoto"):
        manager.import_database(empty_zip, "Vuoto")


def test_import_database_senza_tabella_chunks_solleva(manager: DatabaseManager, tmp_path):
    bad_zip = tmp_path / "senza_chunks.zip"
    with zipfile.ZipFile(bad_zip, "w") as archive:
        archive.writestr("qualche_file.txt", "contenuto a caso")
    with pytest.raises(ValueError, match="struttura LanceDB non riconosciuta|tabella LanceDB"):
        manager.import_database(bad_zip, "Senza Chunks")


def test_import_database_path_traversal_bloccato(manager: DatabaseManager, tmp_path):
    evil_zip = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil_zip, "w") as archive:
        archive.writestr("../../evil.txt", "tentativo di path traversal")
    with pytest.raises(ValueError, match="path traversal"):
        manager.import_database(evil_zip, "Evil")


def test_import_database_path_assoluto_bloccato(manager: DatabaseManager, tmp_path):
    evil_zip = tmp_path / "evil_abs.zip"
    with zipfile.ZipFile(evil_zip, "w") as archive:
        archive.writestr("/etc/passwd_finto", "contenuto")
    with pytest.raises(ValueError, match="percorso assoluto"):
        manager.import_database(evil_zip, "EvilAbs")


def test_import_database_dimensione_metadata_incoerente_solleva(manager: DatabaseManager, tmp_path):
    info = manager.create_database("Sorgente", dimension=4)
    _popola_db(info["path"], dimensione=4)
    zip_path = manager.export_database(info["id"])

    # Riscrive il metadato con una dimensione diversa da quella reale dello schema.
    contenuto = zip_path.read_bytes()
    tmp_zip = tmp_path / "manomesso.zip"
    tmp_zip.write_bytes(contenuto)
    with zipfile.ZipFile(tmp_zip, "a") as archive:
        # Rimuoviamo e riscriviamo non e' supportato direttamente da ZipFile;
        # ricostruiamo l'archivio da zero sostituendo solo il metadato.
        pass

    # Ricostruzione manuale: copia tutti i membri tranne il metadato, poi
    # riscrive il metadato con dimension errata.
    ricostruito = tmp_path / "ricostruito.zip"
    with zipfile.ZipFile(tmp_zip) as src, zipfile.ZipFile(ricostruito, "w") as dst:
        for item in src.infolist():
            if item.filename == "rag_database_metadata.json":
                continue
            dst.writestr(item, src.read(item.filename))
        dst.writestr(
            "rag_database_metadata.json",
            json.dumps({"format": "rag-database-metadata-v1", "embeddingModel": "modelloY", "dimension": 999}),
        )

    with pytest.raises(ValueError, match="dimensione metadati"):
        manager.import_database(ricostruito, "Incoerente")


def test_import_database_metadata_assente_usa_unknown(manager: DatabaseManager, tmp_path):
    info = manager.create_database("SenzaMetadata", dimension=4)
    _popola_db(info["path"], dimensione=4)

    # Costruisce uno zip del contenuto della cartella del DB senza il metadata
    # extra (equivalente a un export "vecchio formato" o di terze parti).
    plain_zip = tmp_path / "plain.zip"
    db_root = Path(info["path"])
    with zipfile.ZipFile(plain_zip, "w") as archive:
        for f in db_root.rglob("*"):
            if f.is_file():
                archive.write(f, f.relative_to(db_root))

    imported = manager.import_database(plain_zip, "Senza Metadata")
    assert imported["embeddingModel"] == "imported/unknown"
    assert imported["dimension"] == 4
