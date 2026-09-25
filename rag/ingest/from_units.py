"""Adattatore ingestion: riuso delle unita' tematiche gia' segmentate.

Legge i JSON prodotti dalla Fase 2 della pipeline di training
(training/dataset_generation/) nel formato:

    [{"titolo": "...", "testo": "..."}, ...]

e li rispezza in chunk dimensionati per il RAG (le unita' tematiche sono
troppo larghe per la granularita' ottimale di retrieval, vedi
rag/ingest/chunker.py). Non ri-processa i PDF: nessuna dipendenza da
PyMuPDF/Docling in questo modulo.

Ignora deliberatamente i campi di metadata noti come inaffidabili
(dominio classificato, densita_formule): vedi STATO_PROGETTO.md, sezione
"Problemi noti nel corpus". Il RAG usa solo titolo libro (dal nome file)
e titolo unita' come metadata di sezione.
"""

from __future__ import annotations

import json
from pathlib import Path

from rag.common.schema import Chunk, TipoFonte
from rag.ingest.chunker import Sezione, chunk_documento

# File marcati per esclusione in STATO_PROGETTO.md: riassunto di terze
# parti, non testo originale, con encoding corrotto sui simboli matematici.
FILE_ESCLUSI = {"Calculus PDF.json"}


def _titolo_libro_da_filename(path: Path) -> str:
    return path.stem.replace("_", " ")


def carica_unita(path_json: Path) -> list[dict]:
    with path_json.open(encoding="utf-8") as f:
        unita = json.load(f)
    if not isinstance(unita, list):
        raise ValueError(f"{path_json}: atteso un array JSON di unita' tematiche")
    return unita


def ingest_file_unita(path_json: Path) -> list[Chunk]:
    """Converte un singolo file di unita' tematiche (un libro) in chunk RAG."""
    if path_json.name in FILE_ESCLUSI:
        return []

    fonte_titolo = _titolo_libro_da_filename(path_json)
    unita = carica_unita(path_json)

    sezioni = [
        Sezione(titolo=u.get("titolo", ""), testo=u.get("testo", ""))
        for u in unita
        if u.get("testo", "").strip()
    ]

    return chunk_documento(
        sezioni,
        fonte_titolo=fonte_titolo,
        tipo_fonte=TipoFonte.LIBRO,
        fonte_path=str(path_json),
    )


def ingest_cartella_unita(cartella: Path) -> list[Chunk]:
    """Applica ingest_file_unita a tutti i JSON di una cartella."""
    chunks: list[Chunk] = []
    for path_json in sorted(cartella.glob("*.json")):
        chunks.extend(ingest_file_unita(path_json))
    return chunks


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Uso: python -m rag.ingest.from_units <cartella_unita_json>")
        sys.exit(1)

    cartella = Path(sys.argv[1])
    chunks = ingest_cartella_unita(cartella)
    print(f"Chunk generati da {cartella}: {len(chunks)}")
    per_libro: dict[str, int] = {}
    for c in chunks:
        per_libro[c.fonte_titolo] = per_libro.get(c.fonte_titolo, 0) + 1
    for titolo, n in per_libro.items():
        print(f"  {titolo}: {n} chunk")
