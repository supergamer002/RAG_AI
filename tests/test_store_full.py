"""Test estesi per rag.index.store (upsert_chunks/apri_o_crea_tabella/conta_chunk).

tests/test_retrieve_and_generate.py copre gia' un ciclo base
store+search; qui ci concentriamo sui casi di errore e sull'idempotenza
che nel modulo originale erano verificati solo dallo smoke test in
__main__, non da pytest.
"""

import shutil
import tempfile

import pytest

from rag.common.schema import Chunk, TipoFonte
from rag.index.store import apri_o_crea_tabella, connetti, conta_chunk, upsert_chunks


@pytest.fixture
def tabella():
    tmp = tempfile.mkdtemp()
    try:
        db = connetti(tmp)
        yield apri_o_crea_tabella(db, dimensione_embedding=4)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _chunk(testo="testo di prova"):
    return Chunk(testo=testo, fonte_titolo="Fonte", tipo_fonte=TipoFonte.LIBRO)


def test_upsert_chunks_lista_vuota(tabella):
    assert upsert_chunks(tabella, [], []) == 0
    assert conta_chunk(tabella) == 0


def test_upsert_chunks_lunghezze_diverse_solleva(tabella):
    with pytest.raises(ValueError, match="stessa lunghezza"):
        upsert_chunks(tabella, [_chunk(), _chunk("altro")], [[0.1, 0.2, 0.3, 0.4]])


def test_upsert_chunks_dimensione_embedding_incompatibile_solleva(tabella):
    with pytest.raises(ValueError, match="Dimensione embedding incompatibile"):
        upsert_chunks(tabella, [_chunk()], [[0.1, 0.2]])  # tabella creata con dim=4


def test_upsert_chunks_idempotente_stesso_chunk_id(tabella):
    c = _chunk("Testo identico")
    upsert_chunks(tabella, [c], [[0.1, 0.2, 0.3, 0.4]])
    assert conta_chunk(tabella) == 1

    # Stesso chunk_id (stesso testo/fonte): l'upsert non deve duplicare la riga.
    upsert_chunks(tabella, [c], [[0.9, 0.9, 0.9, 0.9]])
    assert conta_chunk(tabella) == 1


def test_upsert_chunks_aggiorna_contenuto_su_stesso_id(tabella):
    c = _chunk("Testo originale")
    upsert_chunks(tabella, [c], [[0.1, 0.1, 0.1, 0.1]])

    # Stesso chunk_id, embedding diverso: il merge_insert deve aggiornare il vettore.
    upsert_chunks(tabella, [c], [[0.5, 0.5, 0.5, 0.5]])
    riga = tabella.search().where(f"chunk_id = '{c.chunk_id}'").to_list()[0]
    assert list(riga["vector"]) == pytest.approx([0.5, 0.5, 0.5, 0.5])


def test_upsert_chunks_chunk_diverso_aggiunge_riga(tabella):
    upsert_chunks(tabella, [_chunk("Primo")], [[0.1, 0.1, 0.1, 0.1]])
    upsert_chunks(tabella, [_chunk("Secondo")], [[0.2, 0.2, 0.2, 0.2]])
    assert conta_chunk(tabella) == 2


def test_apri_o_crea_tabella_riapre_tabella_esistente():
    tmp = tempfile.mkdtemp()
    try:
        db1 = connetti(tmp)
        tabella1 = apri_o_crea_tabella(db1, dimensione_embedding=4)
        upsert_chunks(tabella1, [_chunk("Persistente")], [[0.1, 0.1, 0.1, 0.1]])

        # Nuova connessione allo stesso path: deve riaprire la tabella esistente
        # (con i dati gia' presenti), non ricrearla vuota.
        db2 = connetti(tmp)
        tabella2 = apri_o_crea_tabella(db2, dimensione_embedding=4)
        assert conta_chunk(tabella2) == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_conta_chunk_tabella_vuota(tabella):
    assert conta_chunk(tabella) == 0
