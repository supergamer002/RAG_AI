"""Test aggiuntivi per endpoint di webapp/backend/main.py non coperti da
tests/test_backend.py: stats, CRUD /api/databases, chunks/sample,
chunks/{id}/vector, eval/status, ingest/status, settings/defaults,
auth/status, telemetry DELETE, mappa_chunk_item.

Le operazioni di scrittura (create/import database) usano un database di
scratch dedicato, sempre ripulito a fine test tramite fixture con
try/finally, per non alterare lo stato reale del db_manager globale
condiviso con l'app (stesso pattern gia' adottato altrove nella suite,
es. tests/test_fonte_path.py, che scrive/legge sull'app dal vivo).
"""

import pytest
from fastapi.testclient import TestClient

from webapp.backend import main
from webapp.backend.main import app, mappa_chunk_item
from rag.index.store import upsert_chunks
from rag.common.schema import Chunk, TipoFonte

client = TestClient(app)


# --- mappa_chunk_item (funzione pura) -------------------------------------

def test_mappa_chunk_item_campi_base():
    record = {
        "chunk_id": "abc123",
        "testo": "Un testo di prova non troppo lungo.",
        "tipo_fonte": "articolo",
        "fonte_titolo": "Fonte X",
        "sezione": "Sezione 1",
        "denseScore": 0.8,
        "bm25Score": 0.3,
    }
    item = mappa_chunk_item(record, idx=0, initial_rank_map={})
    assert item["id"] == "abc123"
    assert item["chunkNum"] == 1
    assert item["docTitle"] == "Fonte X"
    assert item["docType"] == "Ricerca"  # tipo_fonte "articolo" -> "Ricerca"
    assert item["denseScore"] == 0.8
    assert item["bm25Score"] == 0.3


def test_mappa_chunk_item_tipo_fonte_sconosciuto_fallback_libro():
    record = {"chunk_id": "x", "testo": "t", "tipo_fonte": "boh"}
    item = mappa_chunk_item(record, idx=0, initial_rank_map={})
    assert item["docType"] == "Libro"


def test_mappa_chunk_item_highlight_snippet_troncato():
    testo_lungo = "a" * 200
    record = {"chunk_id": "x", "testo": testo_lungo, "tipo_fonte": "libro"}
    item = mappa_chunk_item(record, idx=0, initial_rank_map={})
    assert item["highlightSnippet"] == "a" * 160 + "..."


def test_mappa_chunk_item_highlight_snippet_testo_corto_non_troncato():
    record = {"chunk_id": "x", "testo": "corto", "tipo_fonte": "libro"}
    item = mappa_chunk_item(record, idx=0, initial_rank_map={})
    assert item["highlightSnippet"] == "corto"


def test_mappa_chunk_item_rank_delta():
    record = {"chunk_id": "x", "testo": "t", "tipo_fonte": "libro"}
    # posizione iniziale 5, posizione finale (idx) 1 -> e' salito di 4 posizioni
    item = mappa_chunk_item(record, idx=1, initial_rank_map={"x": 5})
    assert item["rankDelta"] == 4


def test_mappa_chunk_item_valori_default_se_assenti():
    item = mappa_chunk_item({"chunk_id": "x", "testo": "t"}, idx=0, initial_rank_map={})
    assert item["denseScore"] == 0.0
    assert item["bm25Score"] == 0.0
    assert item["rerankScore"] == 0.0
    assert item["section"] == "Sezione Generale"
    assert item["docTitle"] == "Sconosciuto"


# --- endpoint generici ------------------------------------------------

def test_stats_endpoint():
    res = client.get("/api/stats")
    assert res.status_code == 200
    data = res.json()
    for campo in ("chunks", "documents", "databases", "storageBytes", "activeDatabase"):
        assert campo in data


def test_settings_defaults_endpoint():
    res = client.get("/api/settings/defaults")
    assert res.status_code == 200
    assert isinstance(res.json(), dict)
    assert "apiToken" not in res.json() or res.json().get("apiToken") == ""


def test_auth_status_endpoint():
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    assert "configured" in res.json()


def test_ingest_status_job_inesistente_404():
    res = client.get("/api/ingest/status/job-che-non-esiste")
    assert res.status_code == 404


def test_eval_status_job_inesistente_404():
    res = client.get("/api/eval/status/job-che-non-esiste")
    assert res.status_code == 404


def test_telemetry_delete_svuota_buffer():
    res = client.delete("/api/telemetry")
    assert res.status_code == 200
    assert res.json()["status"] == "cleared"
    # Dopo la pulizia, /api/telemetry deve ricadere sul messaggio di sistema di default.
    res2 = client.get("/api/telemetry")
    logs = res2.json()
    assert len(logs) == 1
    assert logs[0]["id"] == "telemetry-system"


def test_system_restart_endpoint():
    res = client.post("/api/system/restart")
    assert res.status_code == 200
    assert res.json()["status"] == "reloaded"


def test_chunks_vector_chunk_inesistente_404():
    res = client.get("/api/chunks/chunk-id-che-non-esiste-di-sicuro/vector")
    assert res.status_code == 404


def test_vectors_project_metodo_non_valido():
    res = client.post("/api/vectors/project", json={"method": "metodo-invalido"})
    assert res.status_code == 400


# --- CRUD /api/databases su un database di scratch -----------------------

@pytest.fixture
def scratch_database():
    """Crea un database via API e lo elimina sempre a fine test, senza
    mai lasciarlo attivo (protezione delete_database sul DB attivo).
    """
    res = client.post("/api/databases", json={"name": "Scratch Test DB"})
    assert res.status_code == 200
    info = res.json()
    try:
        yield info
    finally:
        if main.db_manager.active_id == info["id"]:
            main.db_manager.activate_database("default")
        client.delete(f"/api/databases/{info['id']}")


def test_create_database_endpoint(scratch_database):
    assert scratch_database["name"] == "Scratch Test DB"
    res = client.get("/api/databases")
    assert res.status_code == 200
    ids = [db["id"] for db in res.json()["databases"]]
    assert scratch_database["id"] in ids


def test_create_database_nome_vuoto_400():
    res = client.post("/api/databases", json={"name": "   "})
    assert res.status_code == 400


def test_activate_and_rename_database_endpoint(scratch_database):
    db_id = scratch_database["id"]

    res_activate = client.post(f"/api/databases/{db_id}/activate")
    assert res_activate.status_code == 200
    assert res_activate.json()["status"] == "activated"
    assert main.db_manager.active_id == db_id

    res_rename = client.put(f"/api/databases/{db_id}", json={"name": "Nome Rinominato"})
    assert res_rename.status_code == 200
    assert res_rename.json()["name"] == "Nome Rinominato"

    # riattiva il default cosi' il teardown della fixture puo' eliminare lo scratch db
    client.post("/api/databases/default/activate")


def test_activate_database_inesistente_404():
    res = client.post("/api/databases/non-esiste-di-sicuro/activate")
    assert res.status_code == 404


def test_rename_database_inesistente_404():
    res = client.put("/api/databases/non-esiste-di-sicuro", json={"name": "X"})
    assert res.status_code == 404


def test_delete_database_attivo_400():
    active_id = main.db_manager.active_id
    res = client.delete(f"/api/databases/{active_id}")
    assert res.status_code == 400


def test_export_database_endpoint(scratch_database):
    db_id = scratch_database["id"]
    res = client.get(f"/api/databases/{db_id}/export")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"


def test_export_database_inesistente_404():
    res = client.get("/api/databases/non-esiste-di-sicuro/export")
    assert res.status_code == 404


# --- chunks/sample e chunks/{id}/vector su dati reali dello scratch db ---

def test_chunks_sample_e_vector_endpoint(scratch_database):
    db_id = scratch_database["id"]
    tabella = main.db_manager.get_table_for_db(db_id)
    chunk = Chunk(testo="Testo per il test del vettore.", fonte_titolo="F", tipo_fonte=TipoFonte.LIBRO)
    upsert_chunks(tabella, [chunk], [[0.25] * 1024])

    client.post(f"/api/databases/{db_id}/activate")
    try:
        res_sample = client.get("/api/chunks/sample?sampleSize=10")
        assert res_sample.status_code == 200
        assert res_sample.json()["total"] == 1

        res_vector = client.get(f"/api/chunks/{chunk.chunk_id}/vector")
        assert res_vector.status_code == 200
        vdata = res_vector.json()
        assert vdata["dimension"] == 1024
        assert len(vdata["fullVector"]) == 1024
    finally:
        client.post("/api/databases/default/activate")
