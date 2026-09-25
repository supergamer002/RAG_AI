"""Test per rag.ingest.chunker e rag.ingest.from_units"""

from pathlib import Path
import json
import pytest
from rag.common.schema import TipoFonte
from rag.ingest.chunker import Sezione, chunk_sezione, chunk_documento
from rag.ingest.from_units import ingest_file_unita, FILE_ESCLUSI


def test_chunk_sezione_basic():
    sez = Sezione(
        titolo="Intro",
        testo="Prima frase. Seconda frase. Terza frase. Quarta frase. Quinta frase.",
    )
    chunks = chunk_sezione(sez, fonte_titolo="Libro 1", tipo_fonte=TipoFonte.LIBRO, target_token=10)
    assert len(chunks) >= 1
    assert all(c.fonte_titolo == "Libro 1" for c in chunks)
    assert all(c.sezione == "Intro" for c in chunks)


def test_chunk_sezione_con_tabella():
    tabella = "| A | B |\n|---|---|\n| 1 | 2 |"
    sez = Sezione(
        titolo="Tabella Cap",
        testo="Ecco la tabella.",
        blocchi_tabella=[tabella],
    )
    chunks = chunk_sezione(sez, fonte_titolo="Libro 1", tipo_fonte=TipoFonte.LIBRO)
    assert len(chunks) == 2
    assert chunks[0].testo == tabella


def test_ingest_file_unita_escluso(tmp_path: Path):
    path_escluso = tmp_path / "Calculus PDF.json"
    path_escluso.write_text("[]", encoding="utf-8")
    chunks = ingest_file_unita(path_escluso)
    assert chunks == []


def test_ingest_file_unita_valido(tmp_path: Path):
    path_json = tmp_path / "Chimica_Generale.json"
    data = [
        {"titolo": "Unita 1", "testo": "Testo dell'unita 1 per testare l'ingest file unita."},
        {"titolo": "Unita 2", "testo": "Testo dell'unita 2 con altro contenuto significativo."}
    ]
    path_json.write_text(json.dumps(data), encoding="utf-8")

    chunks = ingest_file_unita(path_json)
    assert len(chunks) == 2
    assert chunks[0].fonte_titolo == "Chimica Generale"
    assert chunks[0].sezione == "Unita 1"
