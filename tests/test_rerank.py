"""Test per rag.retrieve.rerank.CrossEncoderReranker.

_ordina_per_punteggio e' gia' coperta in tests/test_retrieve_and_generate.py;
qui copriamo la classe CrossEncoderReranker (rerank, caricamento lazy,
gestione punteggio singolo) mockando _calcola_punteggi cosi' da non
richiedere FlagEmbedding/torch.
"""

import pytest

from rag.retrieve.rerank import CrossEncoderReranker, TOP_N_DEFAULT
from rag.common.monitoring import TracciatoreLatenza


def _candidati():
    return [
        {"chunk_id": "a", "testo": "aaa"},
        {"chunk_id": "b", "testo": "bbb"},
        {"chunk_id": "c", "testo": "ccc"},
    ]


def test_rerank_lista_vuota_nessuna_chiamata_modello(monkeypatch):
    chiamato = []
    reranker = CrossEncoderReranker()
    monkeypatch.setattr(
        reranker, "_calcola_punteggi", lambda q, t: chiamato.append(1)
    )
    assert reranker.rerank("query", []) == []
    assert chiamato == []


def test_rerank_ordina_e_tronca(monkeypatch):
    reranker = CrossEncoderReranker()
    monkeypatch.setattr(
        reranker, "_calcola_punteggi", lambda query, testi: [0.1, 0.9, 0.5]
    )
    out = reranker.rerank("query", _candidati(), top_n=2)
    assert [c["chunk_id"] for c in out] == ["b", "c"]
    assert out[0]["rerankScore"] == 0.9


def test_rerank_top_n_default():
    reranker = CrossEncoderReranker()
    reranker._calcola_punteggi = lambda query, testi: [0.1, 0.2, 0.3]
    out = reranker.rerank("query", _candidati())
    assert len(out) == min(TOP_N_DEFAULT, 3)


def test_rerank_punteggio_singolo_float_non_lista(monkeypatch):
    """FlagEmbedding puo' ritornare un float nudo con un solo candidato."""
    reranker = CrossEncoderReranker()
    monkeypatch.setattr(reranker, "_calcola_punteggi", lambda q, t: 0.42)
    out = reranker.rerank("query", [_candidati()[0]])
    assert len(out) == 1
    assert out[0]["rerankScore"] == 0.42


def test_rerank_con_tracciatore(monkeypatch):
    reranker = CrossEncoderReranker()
    monkeypatch.setattr(reranker, "_calcola_punteggi", lambda q, t: [0.5, 0.5, 0.5])
    tracciatore = TracciatoreLatenza(log_automatico=False)
    reranker.rerank("query", _candidati(), tracciatore=tracciatore)
    assert "rerank" in tracciatore.get_statistiche()


def test_carica_modello_lazy_e_cache(monkeypatch):
    """Il modello va caricato una sola volta e riusato tra chiamate."""
    reranker = CrossEncoderReranker()
    assert reranker._modello is None

    caricamenti = []

    class FakeFlagReranker:
        def __init__(self, nome, use_fp16=True):
            caricamenti.append(nome)

        def compute_score(self, coppie, normalize=True):
            return [0.5 for _ in coppie]

    import sys
    import types

    fake_module = types.ModuleType("FlagEmbedding")
    fake_module.FlagReranker = FakeFlagReranker
    monkeypatch.setitem(sys.modules, "FlagEmbedding", fake_module)

    reranker.rerank("query", _candidati())
    reranker.rerank("query", _candidati())

    assert len(caricamenti) == 1  # caricato una volta sola, poi cache in self._modello
    assert reranker._modello is not None
