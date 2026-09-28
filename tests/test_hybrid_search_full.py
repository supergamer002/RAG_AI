"""Test estesi per rag.retrieve.hybrid_search.

tests/test_retrieve_and_generate.py copre gia' _rrf_fusion e un giro
completo in modalita' 'hybrid'. Qui copriamo le modalita' 'dense' e
'sparse'/'bm25', il caso senza risultati, e l'idempotenza di
crea_indice_fulltext.
"""

import shutil
import tempfile

import pytest

from rag.common.schema import Chunk, TipoFonte
from rag.index.store import apri_o_crea_tabella, connetti, upsert_chunks
from rag.retrieve.hybrid_search import (
    _rrf_fusion,
    crea_indice_fulltext,
    ricerca_ibrida,
)


@pytest.fixture
def tabella_popolata():
    tmp = tempfile.mkdtemp()
    try:
        db = connetti(tmp)
        tabella = apri_o_crea_tabella(db, dimensione_embedding=3)
        dati = [
            ("Il legame ionico nasce da trasferimento di elettroni.", [1.0, 0.0, 0.0]),
            ("La teoria VSEPR predice la geometria molecolare.", [0.0, 1.0, 0.0]),
            ("L'entropia misura il disordine di un sistema.", [0.0, 0.0, 1.0]),
        ]
        chunks = [
            Chunk(testo=t, fonte_titolo="Chimica", tipo_fonte=TipoFonte.LIBRO)
            for t, _ in dati
        ]
        upsert_chunks(tabella, chunks, [emb for _, emb in dati])
        crea_indice_fulltext(tabella)
        yield tabella
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ricerca_ibrida_modalita_dense(tabella_popolata):
    risultati = ricerca_ibrida(
        tabella_popolata,
        vettore_query=[0.0, 0.0, 1.0],
        query_testo="query ignorata in modalita dense",
        top_k=1,
        search_mode="dense",
    )
    assert len(risultati) == 1
    assert "entropia" in risultati[0]["testo"]
    assert risultati[0]["bm25Score"] == 0.0
    assert risultati[0]["denseScore"] > 0


def test_ricerca_ibrida_modalita_sparse(tabella_popolata):
    risultati = ricerca_ibrida(
        tabella_popolata,
        vettore_query=[0.0, 0.0, 0.0],  # ignorato in modalita sparse
        query_testo="ionico",
        top_k=1,
        search_mode="sparse",
    )
    assert len(risultati) == 1
    assert "ionico" in risultati[0]["testo"]
    assert risultati[0]["denseScore"] == 0.0
    assert risultati[0]["bm25Score"] > 0


def test_ricerca_ibrida_modalita_bm25_alias(tabella_popolata):
    """'bm25' e 'fts' sono alias di 'sparse'."""
    risultati_bm25 = ricerca_ibrida(
        tabella_popolata, vettore_query=[0, 0, 0], query_testo="ionico", top_k=1, search_mode="bm25"
    )
    risultati_fts = ricerca_ibrida(
        tabella_popolata, vettore_query=[0, 0, 0], query_testo="ionico", top_k=1, search_mode="fts"
    )
    assert risultati_bm25[0]["chunk_id"] == risultati_fts[0]["chunk_id"]


def test_ricerca_ibrida_search_mode_case_insensitive(tabella_popolata):
    r1 = ricerca_ibrida(tabella_popolata, [0, 0, 1.0], "entropia", top_k=1, search_mode="DENSE")
    r2 = ricerca_ibrida(tabella_popolata, [0, 0, 1.0], "entropia", top_k=1, search_mode="dense")
    assert r1[0]["chunk_id"] == r2[0]["chunk_id"]


def test_ricerca_ibrida_tabella_vuota_ritorna_lista_vuota():
    """Con una tabella senza righe, sia dense sia fts non trovano nulla:
    l'id_fusi list resta vuota e la funzione ritorna [] senza errori.
    """
    tmp = tempfile.mkdtemp()
    try:
        db = connetti(tmp)
        tabella_vuota = apri_o_crea_tabella(db, dimensione_embedding=3)
        crea_indice_fulltext(tabella_vuota)
        risultati = ricerca_ibrida(
            tabella_vuota, vettore_query=[1.0, 0.0, 0.0], query_testo="qualsiasi", top_k=5
        )
        assert risultati == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ricerca_ibrida_top_k_zero_solleva_value_error(tabella_popolata):
    """Comportamento attuale: top_k=0 non e' gestito esplicitamente e la ricerca
    vettoriale sottostante di LanceDB richiede un limit positivo per query
    ANN/KNN. Documentato qui come comportamento noto (non un crash silenzioso:
    l'endpoint /api/query lo trasforma in un 503 tramite il gestore generico
    di eccezioni in webapp/backend/main.py).
    """
    with pytest.raises(ValueError, match="Limit is required"):
        ricerca_ibrida(
            tabella_popolata, vettore_query=[1.0, 0.0, 0.0], query_testo="qualsiasi", top_k=0
        )


def test_crea_indice_fulltext_idempotente_senza_replace(tabella_popolata):
    """Richiamare crea_indice_fulltext senza replace non deve fallire ne' duplicare l'indice."""
    nomi_prima = {idx.name for idx in tabella_popolata.list_indices()}
    crea_indice_fulltext(tabella_popolata)  # replace=False di default
    nomi_dopo = {idx.name for idx in tabella_popolata.list_indices()}
    assert nomi_prima == nomi_dopo


def test_crea_indice_fulltext_replace_ricrea_indice(tabella_popolata):
    crea_indice_fulltext(tabella_popolata, replace=True)
    nomi = {idx.name for idx in tabella_popolata.list_indices()}
    assert "testo_idx" in nomi


# --- _rrf_fusion: casi aggiuntivi rispetto a test_retrieve_and_generate ---

def test_rrf_fusion_alpha_zero_ignora_dense():
    dense = ["d1", "d2"]
    fts = ["f1", "f2"]
    fusi = _rrf_fusion(dense, fts, alpha=0.0)
    # Con alpha=0 solo fts contribuisce al punteggio: i doc solo-dense hanno punteggio 0.
    assert fusi[0] == "f1"
    assert fusi[1] == "f2"


def test_rrf_fusion_alpha_uno_ignora_fts():
    dense = ["d1", "d2"]
    fts = ["f1", "f2"]
    fusi = _rrf_fusion(dense, fts, alpha=1.0)
    assert fusi[0] == "d1"
    assert fusi[1] == "d2"


def test_rrf_fusion_liste_vuote():
    assert _rrf_fusion([], []) == []
