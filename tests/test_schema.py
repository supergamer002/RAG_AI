"""Test per rag.common.schema"""

import pytest
from rag.common.schema import Chunk, TipoFonte, stima_token


def test_chunk_creation_and_deterministic_id():
    chunk1 = Chunk(
        testo="Testo di prova per il chunk",
        fonte_titolo="Libro di Test",
        tipo_fonte=TipoFonte.LIBRO,
        sezione="Capitolo 1",
        posizione="p. 10",
    )
    chunk2 = Chunk(
        testo="Testo di prova per il chunk",
        fonte_titolo="Libro di Test",
        tipo_fonte=TipoFonte.LIBRO,
        sezione="Capitolo 1",
        posizione="p. 10",
    )
    chunk3 = Chunk(
        testo="Testo differente",
        fonte_titolo="Libro di Test",
        tipo_fonte=TipoFonte.LIBRO,
        sezione="Capitolo 1",
        posizione="p. 10",
    )

    assert chunk1.chunk_id != ""
    assert len(chunk1.chunk_id) == 24
    assert chunk1.chunk_id == chunk2.chunk_id
    assert chunk1.chunk_id != chunk3.chunk_id


def test_chunk_to_record():
    chunk = Chunk(
        testo="Testo di prova",
        fonte_titolo="Articolo Test",
        tipo_fonte=TipoFonte.ARTICOLO,
    )
    rec = chunk.to_record()
    assert rec["tipo_fonte"] == "articolo"
    assert rec["testo"] == "Testo di prova"
    assert rec["chunk_id"] == chunk.chunk_id


def test_stima_token():
    testo = "Uno due tre quattro cinque"
    # 5 parole * 1.3 = 6.5 -> int(6.5) = 6
    assert stima_token(testo, usa_tokenizer_esatto=False) == 6
    assert stima_token("", usa_tokenizer_esatto=False) == 0


def test_stima_token_con_fallback(monkeypatch):
    testo = "Uno due tre quattro cinque"
    # Se conta_token_esatto ritorna None (come quando transformers non e' presente),
    # stima_token ricade sul calcolo euristico.
    monkeypatch.setattr("rag.common.schema.conta_token_esatto", lambda t: None)
    assert stima_token(testo, usa_tokenizer_esatto=True) == 6

    # Se conta_token_esatto ritorna un valore, viene usato quello.
    monkeypatch.setattr("rag.common.schema.conta_token_esatto", lambda t: 10)
    assert stima_token(testo, usa_tokenizer_esatto=True) == 10
