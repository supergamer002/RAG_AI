"""Test per rag.index, rag.retrieve e rag.generate"""

import tempfile
import shutil
from pathlib import Path
import pytest

from rag.common.schema import Chunk, TipoFonte
from rag.index.store import connetti, apri_o_crea_tabella, upsert_chunks, conta_chunk
from rag.retrieve.hybrid_search import (
    crea_indice_fulltext,
    ricerca_ibrida,
    _rrf_fusion,
    aggiorna_indice_fts_in_background,
)
from rag.retrieve.rerank import _ordina_per_punteggio
from rag.generate.answer import costruisci_messaggi, rispondi
from rag.common.monitoring import TracciatoreLatenza


def test_rrf_fusion():
    lista1 = ["doc1", "doc2", "doc3"]
    lista2 = ["doc2", "doc1", "doc4"]

    fusi = _rrf_fusion(lista1, lista2, k=60)
    # doc1 e doc2 devono essere in cima poiche' presenti in entrambe
    assert fusi[0] in ("doc1", "doc2")
    assert fusi[1] in ("doc1", "doc2")
    assert set(fusi) == {"doc1", "doc2", "doc3", "doc4"}


def test_ordina_per_punteggio():
    candidati = [
        {"chunk_id": "1", "testo": "A"},
        {"chunk_id": "2", "testo": "B"},
        {"chunk_id": "3", "testo": "C"},
    ]
    punteggi = [0.1, 0.9, 0.4]
    ordinati = _ordina_per_punteggio(candidati, punteggi, top_n=2)
    assert len(ordinati) == 2
    assert ordinati[0]["chunk_id"] == "2"
    assert ordinati[1]["chunk_id"] == "3"


def test_costruisci_messaggi():
    chunks = [
        {"fonte_titolo": "F1", "sezione": "S1", "posizione": "p. 1", "testo": "Contesto 1"}
    ]
    msg = costruisci_messaggi("Domanda?", chunks)
    assert len(msg) == 2
    assert msg[0]["role"] == "system"
    assert "F1, S1 (p. 1)" in msg[1]["content"]
    assert "Contesto 1" in msg[1]["content"]


def test_lancedb_store_and_search():
    tmp = tempfile.mkdtemp()
    try:
        db = connetti(tmp)
        tabella = apri_o_crea_tabella(db, dimensione_embedding=3)

        c1 = Chunk(testo="Il gatto e' un felino domestico.", fonte_titolo="Zoologia", tipo_fonte=TipoFonte.LIBRO)
        c2 = Chunk(testo="Il cane e' un canide domestico.", fonte_titolo="Zoologia", tipo_fonte=TipoFonte.LIBRO)

        emb1 = [1.0, 0.0, 0.0]
        emb2 = [0.0, 1.0, 0.0]

        n = upsert_chunks(tabella, [c1, c2], [emb1, emb2])
        assert n == 2
        assert conta_chunk(tabella) == 2

        crea_indice_fulltext(tabella)

        tracciatore = TracciatoreLatenza(log_automatico=False)
        risultati = ricerca_ibrida(
            tabella,
            vettore_query=[1.0, 0.0, 0.0],
            query_testo="gatto",
            top_k=2,
            tracciatore=tracciatore,
        )
        assert len(risultati) >= 1
        assert any("gatto" in r["testo"] for r in risultati)
        assert "hybrid_search" in tracciatore.get_statistiche()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_aggiorna_indice_fts_in_background():
    tmp = tempfile.mkdtemp()
    try:
        db = connetti(tmp)
        tabella = apri_o_crea_tabella(db, dimensione_embedding=2)

        c1 = Chunk(testo="Doc iniziale", fonte_titolo="F1", tipo_fonte=TipoFonte.LIBRO)
        upsert_chunks(tabella, [c1], [[1.0, 0.0]])
        crea_indice_fulltext(tabella)

        c2 = Chunk(testo="Nuovo doc aggiunto", fonte_titolo="F1", tipo_fonte=TipoFonte.LIBRO)
        upsert_chunks(tabella, [c2], [[0.0, 1.0]])

        callback_eseguita = []
        thread = aggiorna_indice_fts_in_background(
            tabella, callback=lambda: callback_eseguita.append(True)
        )
        thread.join(timeout=5)

        assert len(callback_eseguita) == 1
        # Verifica che il nuovo documento sia ora trovabile con ricerca FTS
        ris = tabella.search("Nuovo", query_type="fts").to_list()
        assert len(ris) >= 1
        assert "Nuovo doc" in ris[0]["testo"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
