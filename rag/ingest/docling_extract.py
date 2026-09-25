"""Adattatore ingestion: PDF nuovi (articoli scientifici, libri non ancora
processati) via Docling.

Non sostituisce la pipeline PyMuPDF della Fase 1 di training: quella resta
per l'estrazione destinata al fine-tuning. Questo modulo serve solo il RAG,
dove la fedelta' su tabelle e formule ha un impatto diretto sulla qualita'
delle risposte.

Richiede `pip install docling` (pesante: torch + modelli layout/OCR).
Import differito dentro le funzioni cosi' il resto del pacchetto rag/ non
dipende da docling per essere importato o testato.
"""

from __future__ import annotations

from pathlib import Path

from rag.common.schema import Chunk, TipoFonte
from rag.ingest.chunker import Sezione, chunk_documento

# Livelli di header Docling considerati "sezione": sotto questo livello il
# testo confluisce nella sezione padre invece di aprirne una nuova troppo
# fine (es. sotto-paragrafi senza titolo proprio).
MAX_LIVELLO_SEZIONE = 2

# Limite thread CPU per Docling/torch: su 8GB RAM CPU-only, lasciare torch
# libero di usare tutti i core porta a thrashing di memoria durante il
# parsing del layout. Va impostato PRIMA di importare torch, altrimenti
# l'impostazione viene ignorata.
THREAD_LIMIT = int(__import__("os").environ.get("RAG_DOCLING_THREADS", "2"))


def _ha_layer_testo(path_pdf: Path, soglia_caratteri: int = 200) -> bool:
    """Controllo rapido con pypdf: se le prime pagine hanno gia' testo
    estraibile, il PDF non e' uno scan e l'OCR di Docling e' superfluo
    (costa tempo/RAM senza guadagno di qualita').
    """
    import pypdf

    reader = pypdf.PdfReader(str(path_pdf))
    testo = ""
    for pagina in reader.pages[:3]:
        testo += pagina.extract_text() or ""
        if len(testo) >= soglia_caratteri:
            return True
    return len(testo) >= soglia_caratteri


def _converti_pdf(path_pdf: Path, ocr_enabled: bool = True):
    """Esegue la conversione Docling. Isolata per poter essere mockata nei test."""
    import torch

    torch.set_num_threads(THREAD_LIMIT)

    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat

    opzioni = PdfPipelineOptions()
    opzioni.do_ocr = bool(ocr_enabled) and not _ha_layer_testo(path_pdf)

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opzioni)}
    )
    risultato = converter.convert(str(path_pdf))
    return risultato.document


def _estrai_sezioni(doc) -> list[Sezione]:
    """Percorre l'albero del documento Docling e accumula testo per sezione,
    usando gli header come delimitatori (analogo alla logica di
    training/dataset_generation per i libri, ma guidata dalla struttura
    riconosciuta da Docling invece che da regex su pattern di titolo).

    Le tabelle (item.label == "table") vengono raccolte separatamente dal
    testo narrativo: finiscono in Sezione.blocchi_tabella e il chunker le
    emette intatte, senza applicare lo splitting a frasi che le spezzerebbe.
    """
    sezioni: list[Sezione] = []
    titolo_corrente = "Introduzione"
    pagina_corrente: int | None = None
    buffer: list[str] = []
    buffer_tabelle: list[str] = []

    def chiudi_sezione() -> None:
        testo = " ".join(buffer).strip()
        if testo or buffer_tabelle:
            posizione = f"p. {pagina_corrente}" if pagina_corrente else ""
            sezioni.append(
                Sezione(
                    titolo=titolo_corrente,
                    testo=testo,
                    posizione=posizione,
                    blocchi_tabella=list(buffer_tabelle),
                )
            )
        buffer.clear()
        buffer_tabelle.clear()

    # doc.iterate_items() e' l'API Docling per scorrere gli elementi nel
    # reading order ricostruito (testo, header, tabelle esportate come
    # markdown, formule come LaTeX).
    for item, _level in doc.iterate_items():
        tipo = getattr(item, "label", "")
        pagina_corrente = getattr(item, "page_no", pagina_corrente)

        if tipo in ("section_header", "title") and getattr(item, "level", 1) <= MAX_LIVELLO_SEZIONE:
            chiudi_sezione()
            titolo_corrente = (item.text or "").strip() or titolo_corrente
            continue

        if tipo == "table":
            md = getattr(item, "export_to_markdown", lambda: "")()
            if md.strip():
                buffer_tabelle.append(md.strip())
            continue

        testo_item = getattr(item, "text", None) or getattr(item, "export_to_markdown", lambda: "")()
        if testo_item:
            buffer.append(testo_item.strip())

    chiudi_sezione()
    return sezioni


def ingest_pdf(
    path_pdf: Path,
    tipo_fonte: TipoFonte,
    fonte_titolo: str | None = None,
    target_token: int = 600,
    overlap_ratio: float = 0.12,
    ocr_enabled: bool = True,
) -> list[Chunk]:
    """Estrae un PDF con Docling e lo trasforma in chunk RAG.

    tipo_fonte va passato esplicitamente (LIBRO o ARTICOLO): la cartella di
    provenienza (data/libri/ vs data/articoli/) lo determina a monte, vedi
    ingest_cartella.
    """
    doc = _converti_pdf(path_pdf, ocr_enabled=ocr_enabled)
    sezioni = _estrai_sezioni(doc)
    titolo = fonte_titolo or path_pdf.stem.replace("_", " ")

    return chunk_documento(
        sezioni,
        fonte_titolo=titolo,
        tipo_fonte=tipo_fonte,
        fonte_path=str(path_pdf),
        target_token=target_token,
        overlap_ratio=overlap_ratio,
    )


def ingest_cartella(
    cartella: Path,
    tipo_fonte: TipoFonte,
    target_token: int = 600,
    overlap_ratio: float = 0.12,
    ocr_enabled: bool = True,
) -> list[Chunk]:
    """Applica ingest_pdf a tutti i PDF di una cartella (es. data/articoli/)."""
    chunks: list[Chunk] = []
    for path_pdf in sorted(cartella.glob("*.pdf")):
        chunks.extend(
            ingest_pdf(
                path_pdf,
                tipo_fonte,
                target_token=target_token,
                overlap_ratio=overlap_ratio,
                ocr_enabled=ocr_enabled,
            )
        )
    return chunks


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3 or sys.argv[2] not in ("libro", "articolo"):
        print("Uso: python -m rag.ingest.docling_extract <file_o_cartella.pdf> <libro|articolo>")
        sys.exit(1)

    target = Path(sys.argv[1])
    tipo = TipoFonte.LIBRO if sys.argv[2] == "libro" else TipoFonte.ARTICOLO

    chunks = ingest_pdf(target, tipo) if target.is_file() else ingest_cartella(target, tipo)
    print(f"Chunk generati: {len(chunks)}")
    for c in chunks[:5]:
        print(f"  [{c.sezione} | {c.posizione}] {c.testo[:80]}...")
