import pytest
from fastapi.testclient import TestClient
from webapp.backend import main
from unittest.mock import patch

from rag.index.store import upsert_chunks
from rag.common.schema import Chunk, TipoFonte

client = TestClient(main.app)


@pytest.fixture
def scratch_db_con_un_chunk():
    """L'endpoint /api/query ritorna subito {"answer": "", "chunks": []} con
    tabella vuota, prima ancora di chiamare _esegui_query_su_tabella: senza
    almeno una riga il mock qui sotto non verrebbe mai raggiunto e il test
    passerebbe per il motivo sbagliato (o fallirebbe se il DB attivo reale
    era vuoto, come effettivamente osservato). Usiamo un database di
    scratch dedicato invece di scrivere nel DB attivo reale.
    """
    res = client.post("/api/databases", json={"name": "Scratch Query Error Test"})
    info = res.json()
    tabella = main.db_manager.get_table_for_db(info["id"])
    chunk = Chunk(testo="Contenuto qualsiasi", fonte_titolo="F", tipo_fonte=TipoFonte.LIBRO)
    upsert_chunks(tabella, [chunk], [[0.1] * 1024])
    client.post(f"/api/databases/{info['id']}/activate")
    try:
        yield info
    finally:
        client.post("/api/databases/default/activate")
        client.delete(f"/api/databases/{info['id']}")


def test_query_error_detail(scratch_db_con_un_chunk):
    # Mock _esegui_query_su_tabella to raise an exception
    with patch('webapp.backend.main._esegui_query_su_tabella') as mock_query:
        mock_query.side_effect = RuntimeError("Something went wrong in the pipeline")

        response = client.post("/api/query", json={"query": "test query"})

        assert response.status_code == 503
        detail = response.json()["detail"]
        assert "RuntimeError" in detail
        assert "Something went wrong in the pipeline" in detail
