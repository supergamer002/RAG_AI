"""Test avversari su /api/query e sulla ricerca ibrida.

Nessuna modifica al programma. Embedder, reranker e LLM sono finti; il DB e'
uno scratch creato via API e ripulito sempre a fine test.
Un test rosso = possibile bug reale nel programma.
"""

import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from rag.common.schema import Chunk, TipoFonte
from rag.index.store import apri_o_crea_tabella, connetti, upsert_chunks
from rag.retrieve.hybrid_search import crea_indice_fulltext, ricerca_ibrida
from webapp.backend import main

client = TestClient(main.app)
DIM = 1024


class _FakeEmbedder:
    def __init__(self, errore=None):
        self.errore = errore

    def embed_uno(self, testo):
        if self.errore:
            raise self.errore
        return [0.5] * DIM


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    main._rate_buckets.clear()
    monkeypatch.setattr(main.embedder_manager, "get_embedder", lambda m, u: _FakeEmbedder())
    monkeypatch.setattr(main.reranker, "rerank",
                        lambda query, candidati, top_n=6, tracciatore=None: [
                            {**c, "rerankScore": 0.9 - i * 0.1} for i, c in enumerate(candidati[:top_n])])
    monkeypatch.setattr(main.generatore, "genera", lambda messaggi: "risposta finta")
    yield
    main._rate_buckets.clear()


@pytest.fixture
def db_scratch():
    """DB scratch con 3 chunk. Nessun indice FTS creato di proposito."""
    info = client.post("/api/databases", json={"name": "Scratch Adversarial"}).json()
    tab = main.db_manager.get_table_for_db(info["id"])
    testi = [
        "Il legame ionico nasce dal trasferimento di elettroni.",
        "La teoria VSEPR predice la geometria molecolare.",
        "L'entropia misura il disordine di un sistema termodinamico.",
    ]
    chunks = [Chunk(testo=t, fonte_titolo="Chimica", tipo_fonte=TipoFonte.LIBRO) for t in testi]
    upsert_chunks(tab, chunks, [[0.5] * DIM for _ in chunks])
    client.post(f"/api/databases/{info['id']}/activate")
    try:
        yield info
    finally:
        client.post("/api/databases/default/activate")
        client.delete(f"/api/databases/{info['id']}")


def _q(**kw):
    return client.post("/api/query", json={"query": "legame ionico", **kw})


# ------------------------------------------------------------ input ----

def test_query_solo_spazi_400():
    assert client.post("/api/query", json={"query": "   \n\t "}).status_code == 400


def test_query_campo_mancante_422():
    assert client.post("/api/query", json={}).status_code == 422


def test_query_tipo_errato_422():
    assert client.post("/api/query", json={"query": 123}).status_code in (400, 422)


def test_query_topk_negativo_rifiutato(db_scratch):
    assert _q(topK=-5).status_code in (400, 422)


def test_query_topn_negativo_rifiutato(db_scratch):
    assert _q(topN=-1).status_code in (400, 422)


def test_query_hybrid_alpha_fuori_range_rifiutato(db_scratch):
    assert _q(hybridAlpha=5).status_code in (400, 422)
    assert _q(hybridAlpha=-1).status_code in (400, 422)


def test_query_search_mode_sconosciuto_rifiutato(db_scratch):
    assert _q(searchMode="banana").status_code in (400, 422)


def test_query_topk_enorme_non_esplode(db_scratch):
    assert _q(topK=10_000_000).status_code in (200, 400, 422)


def test_query_molto_lunga_non_500(db_scratch):
    r = client.post("/api/query", json={"query": "parola " * 20000})
    assert r.status_code != 500


# ---------------------------------------------------- modalita' di ricerca ----

def test_query_hybrid_ok(db_scratch):
    r = _q(searchMode="hybrid")
    assert r.status_code == 200, r.text
    assert r.json()["chunks"]


def test_query_dense_ok(db_scratch):
    r = _q(searchMode="dense")
    assert r.status_code == 200, r.text
    assert r.json()["chunks"]


def test_query_sparse_senza_indice_fts_funziona(db_scratch):
    """In modalita' sparse non c'e' embedding (query_emb=None): se la prima
    ricerca fallisce (indice FTS assente) il fallback richiama ricerca_ibrida
    in modalita' hybrid con vettore None. Deve comunque rispondere 200."""
    r = _q(searchMode="sparse")
    assert r.status_code == 200, r.text


def test_query_sparse_ripetuta_dopo_creazione_indice(db_scratch):
    _q(searchMode="sparse")
    r = _q(searchMode="sparse")
    assert r.status_code == 200, r.text


def test_query_risposta_non_espone_query_embedding(db_scratch):
    r = _q(searchMode="dense")
    assert "queryEmbedding" not in r.json()


def test_query_dense_non_richiama_embedder_in_sparse(db_scratch, monkeypatch):
    chiamate = []
    monkeypatch.setattr(main.embedder_manager, "get_embedder",
                        lambda m, u: chiamate.append(1) or _FakeEmbedder())
    _q(searchMode="sparse")
    assert chiamate == []


# ------------------------------------------------------ errori a cascata ----

def test_query_embedder_giu_da_503_con_dettaglio(db_scratch, monkeypatch):
    monkeypatch.setattr(main.embedder_manager, "get_embedder",
                        lambda m, u: _FakeEmbedder(RuntimeError("ollama giu")))
    r = _q(searchMode="dense")
    assert r.status_code == 503
    assert "ollama giu" in r.json()["detail"]


def test_query_llm_giu_risponde_comunque_con_chunk(db_scratch, monkeypatch):
    def boom(messaggi):
        raise RuntimeError("llm giu")
    monkeypatch.setattr(main.generatore, "genera", boom)
    r = _q(searchMode="dense")
    assert r.status_code == 200
    assert "llm giu" in r.json()["answer"]
    assert r.json()["chunks"]


def test_query_reranker_giu_ripiega_su_candidati(db_scratch, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("reranker giu")
    monkeypatch.setattr(main.reranker, "rerank", boom)
    r = _q(searchMode="dense", topN=2)
    assert r.status_code == 200
    assert 1 <= len(r.json()["chunks"]) <= 2


def test_query_enable_rerank_false_non_chiama_reranker(db_scratch, monkeypatch):
    chiamate = []
    monkeypatch.setattr(main.reranker, "rerank", lambda *a, **k: chiamate.append(1) or [])
    r = _q(searchMode="dense", enableRerank=False)
    assert r.status_code == 200
    assert chiamate == []
    assert r.json()["chunks"]


def test_query_top_n_limita_i_chunk(db_scratch):
    r = _q(searchMode="dense", topN=1)
    assert len(r.json()["chunks"]) == 1


def test_query_llm_errore_con_testo_none_nel_fallback(db_scratch, monkeypatch):
    """Il messaggio di fallback fa c.get('testo')[:120]: con testo None crasherebbe."""
    def boom(messaggi):
        raise RuntimeError("llm giu")
    monkeypatch.setattr(main.generatore, "genera", boom)
    monkeypatch.setattr(main.reranker, "rerank",
                        lambda query, candidati, top_n=6, tracciatore=None: [
                            {"chunk_id": "x", "testo": None, "fonte_titolo": "F"}])
    r = _q(searchMode="dense")
    assert r.status_code == 200


def test_query_tabella_vuota_risposta_vuota():
    info = client.post("/api/databases", json={"name": "Scratch Vuoto"}).json()
    client.post(f"/api/databases/{info['id']}/activate")
    try:
        r = _q()
        assert r.status_code == 200
        assert r.json() == {"answer": "", "chunks": []}
    finally:
        client.post("/api/databases/default/activate")
        client.delete(f"/api/databases/{info['id']}")


# ---------------------------------- ricerca_ibrida con testo ostile ----

@pytest.fixture
def tabella_fts():
    tmp = tempfile.mkdtemp()
    try:
        tab = apri_o_crea_tabella(connetti(tmp), dimensione_embedding=3)
        chunks = [Chunk(testo=t, fonte_titolo="F", tipo_fonte=TipoFonte.LIBRO)
                  for t in ["linguaggio C++ e Python", "operatore AND e OR", "campo foo:bar"]]
        upsert_chunks(tab, chunks, [[1.0, 0.0, 0.0]] * 3)
        crea_indice_fulltext(tab)
        yield tab
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.parametrize("query", [
    'virgolette "non chiuse',
    "(parentesi",
    "C++",
    "foo:bar",
    "AND OR NOT",
    "*",
    "?",
    "a\\b",
    "'; DROP TABLE chunks; --",
    "😀 emoji",
    "   ",
    "",
    "x" * 5000,
])
def test_ricerca_ibrida_query_testuale_ostile_non_crasha(tabella_fts, query):
    ricerca_ibrida(tabella_fts, [1.0, 0.0, 0.0], query, top_k=3)


def test_ricerca_ibrida_chunk_id_con_apice_non_rompe_where():
    """chunk_id con apice: l'escape SQL nel where deve reggere."""
    tmp = tempfile.mkdtemp()
    try:
        tab = apri_o_crea_tabella(connetti(tmp), dimensione_embedding=3)
        c = Chunk(testo="testo qualsiasi", fonte_titolo="F", tipo_fonte=TipoFonte.LIBRO)
        c.chunk_id = "id'con'apici"
        upsert_chunks(tab, [c], [[1.0, 0.0, 0.0]])
        crea_indice_fulltext(tab)
        ris = ricerca_ibrida(tab, [1.0, 0.0, 0.0], "testo", top_k=3)
        assert ris and ris[0]["chunk_id"] == "id'con'apici"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_ricerca_ibrida_vettore_dimensione_sbagliata_errore_chiaro(tabella_fts):
    with pytest.raises(Exception):
        ricerca_ibrida(tabella_fts, [1.0, 0.0], "python", top_k=3, search_mode="dense")


def test_ricerca_ibrida_sparse_senza_indice_fts_non_crasha_con_typeerror():
    tmp = tempfile.mkdtemp()
    try:
        tab = apri_o_crea_tabella(connetti(tmp), dimensione_embedding=3)
        c = Chunk(testo="testo qualsiasi", fonte_titolo="F", tipo_fonte=TipoFonte.LIBRO)
        upsert_chunks(tab, [c], [[1.0, 0.0, 0.0]])
        try:
            ricerca_ibrida(tab, None, "testo", top_k=3, search_mode="sparse")
        except (TypeError, AttributeError) as exc:
            pytest.fail(f"errore non gestito in sparse senza indice: {exc!r}")
        except Exception:
            pass  # errore esplicito di LanceDB per indice mancante: accettabile
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
