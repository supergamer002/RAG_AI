"""Test estesi per rag.ingest.from_units.

ingest_file_unita (caso escluso e caso valido) e' gia' coperto in
tests/test_ingest.py e tests/test_fonte_path.py. Qui copriamo carica_unita
direttamente (incl. il caso di errore) e ingest_cartella_unita.
"""

import json
from pathlib import Path

import pytest

from rag.common.schema import TipoFonte
from rag.ingest.from_units import carica_unita, ingest_cartella_unita, ingest_file_unita


def test_carica_unita_valido(tmp_path: Path):
    path = tmp_path / "unita.json"
    dati = [{"titolo": "U1", "testo": "Testo uno."}]
    path.write_text(json.dumps(dati), encoding="utf-8")
    assert carica_unita(path) == dati


def test_carica_unita_non_lista_solleva(tmp_path: Path):
    path = tmp_path / "non_lista.json"
    path.write_text(json.dumps({"titolo": "non e' una lista"}), encoding="utf-8")
    with pytest.raises(ValueError, match="array JSON"):
        carica_unita(path)


def test_ingest_file_unita_ignora_unita_con_testo_vuoto(tmp_path: Path):
    path = tmp_path / "Con_Vuote.json"
    dati = [
        {"titolo": "Valida", "testo": "Un testo con contenuto reale sufficiente."},
        {"titolo": "Vuota", "testo": "   "},
        {"titolo": "SenzaChiaveTesto"},
    ]
    path.write_text(json.dumps(dati), encoding="utf-8")
    chunks = ingest_file_unita(path)
    sezioni = {c.sezione for c in chunks}
    assert sezioni == {"Valida"}


def test_ingest_cartella_unita_applica_a_tutti_i_json_in_ordine(tmp_path: Path):
    sotto = tmp_path / "sotto"
    sotto.mkdir()
    (tmp_path / "B_Libro.json").write_text(
        json.dumps([{"titolo": "U1", "testo": "Testo del libro B."}]), encoding="utf-8"
    )
    (tmp_path / "A_Libro.json").write_text(
        json.dumps([{"titolo": "U1", "testo": "Testo del libro A."}]), encoding="utf-8"
    )
    (sotto / "C_Libro.json").write_text(
        json.dumps([{"titolo": "U1", "testo": "Testo del libro C in sottocartella."}]), encoding="utf-8"
    )

    chunks = ingest_cartella_unita(tmp_path)
    titoli = [c.fonte_titolo for c in chunks]
    # rglob ordinato alfabeticamente per path completo: A_Libro, B_Libro, poi sotto/C_Libro
    assert titoli == ["A Libro", "B Libro", "C Libro"]


def test_ingest_cartella_unita_rispetta_file_esclusi(tmp_path: Path):
    (tmp_path / "Calculus PDF.json").write_text(json.dumps([{"titolo": "X", "testo": "escluso"}]), encoding="utf-8")
    (tmp_path / "Altro.json").write_text(
        json.dumps([{"titolo": "U1", "testo": "Testo non escluso, valido."}]), encoding="utf-8"
    )
    chunks = ingest_cartella_unita(tmp_path)
    assert all(c.fonte_titolo != "Calculus PDF" for c in chunks)
    assert any(c.fonte_titolo == "Altro" for c in chunks)


def test_ingest_cartella_unita_cartella_vuota(tmp_path: Path):
    assert ingest_cartella_unita(tmp_path) == []


def test_ingest_cartella_unita_propaga_target_token_e_overlap(tmp_path: Path):
    testo_lungo = ("Questa e' una frase di riempimento. " * 40).strip()
    (tmp_path / "Libro.json").write_text(
        json.dumps([{"titolo": "U1", "testo": testo_lungo}]), encoding="utf-8"
    )
    chunks_target_basso = ingest_cartella_unita(tmp_path, target_token=20)
    chunks_target_alto = ingest_cartella_unita(tmp_path, target_token=2000)
    assert len(chunks_target_basso) > len(chunks_target_alto)
