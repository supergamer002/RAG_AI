"""Test aggiuntivi per rag.common.schema, a complemento di tests/test_schema.py."""

import rag.common.schema as schema
from rag.common.schema import Chunk, TipoFonte, conta_token_esatto


def test_conta_token_esatto_fallback_a_none_se_transformers_assente(monkeypatch):
    """Se il tokenizer non e' disponibile (import fallito o modello non
    scaricabile), conta_token_esatto deve ritornare None invece di sollevare.
    """
    monkeypatch.setattr(schema, "_TOKENIZER_CACHE", False)
    assert conta_token_esatto("qualsiasi testo") is None


def test_conta_token_esatto_usa_tokenizer_quando_disponibile(monkeypatch):
    class FakeTokenizer:
        def encode(self, testo):
            return testo.split()  # tokenizzazione finta: una parola = un token

    monkeypatch.setattr(schema, "_TOKENIZER_CACHE", FakeTokenizer())
    assert conta_token_esatto("uno due tre") == 3


def test_conta_token_esatto_encode_fallisce_ritorna_none(monkeypatch):
    class FakeTokenizerRotto:
        def encode(self, testo):
            raise RuntimeError("tokenizer rotto")

    monkeypatch.setattr(schema, "_TOKENIZER_CACHE", FakeTokenizerRotto())
    assert conta_token_esatto("testo qualsiasi") is None


def test_chunk_id_diverso_per_fonte_path_diverso():
    """Stesso testo/titolo/sezione ma fonte_path diversa: chunk_id deve
    differire, altrimenti un upsert su LanceDB sovrascriverebbe per errore
    chunk provenienti da file diversi con contenuto identico.
    """
    c1 = Chunk(
        testo="Testo identico",
        fonte_titolo="Stesso Titolo",
        tipo_fonte=TipoFonte.LIBRO,
        fonte_path="sources/file1.json",
    )
    c2 = Chunk(
        testo="Testo identico",
        fonte_titolo="Stesso Titolo",
        tipo_fonte=TipoFonte.LIBRO,
        fonte_path="sources/file2.json",
    )
    assert c1.chunk_id != c2.chunk_id


def test_ricalcola_id_riflette_modifiche_successive():
    c = Chunk(testo="Originale", fonte_titolo="F", tipo_fonte=TipoFonte.LIBRO)
    id_originale = c.chunk_id
    c.testo = "Modificato"
    c.ricalcola_id()
    assert c.chunk_id != id_originale


def test_tipo_fonte_valori_enum():
    assert TipoFonte.LIBRO.value == "libro"
    assert TipoFonte.ARTICOLO.value == "articolo"
    assert TipoFonte.VIDEO.value == "video"
