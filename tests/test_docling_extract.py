"""Test per rag.ingest.docling_extract.

_estrai_sezioni e _ha_layer_testo sono logica pura/pypdf, testabili senza
docling/torch installati (import differito nel modulo). ingest_pdf/
ingest_cartella sono testati mockando _converti_pdf, cosi' l'intera
pipeline Docling resta fuori dal perimetro del test.
"""

from pathlib import Path

import pytest

from rag.common.schema import TipoFonte
from rag.ingest import docling_extract as de


class _FakeItem:
    def __init__(self, text="", label="text", level=1, page_no=None, table_md=None):
        self.text = text
        self.label = label
        self.level = level
        self.page_no = page_no
        self._table_md = table_md

    def export_to_markdown(self):
        return self._table_md or ""


class _FakeDoc:
    def __init__(self, items):
        self._items = items

    def iterate_items(self):
        for item in self._items:
            yield item, item.level


# --- _estrai_sezioni ----------------------------------------------------

def test_estrai_sezioni_senza_header_usa_introduzione():
    doc = _FakeDoc([_FakeItem(text="Testo senza header.", label="text", page_no=1)])
    sezioni = de._estrai_sezioni(doc)
    assert len(sezioni) == 1
    assert sezioni[0].titolo == "Introduzione"
    assert sezioni[0].testo == "Testo senza header."
    assert sezioni[0].posizione == "p. 1"


def test_estrai_sezioni_con_header_apre_nuova_sezione():
    doc = _FakeDoc([
        _FakeItem(text="Prima del titolo.", label="text", page_no=1),
        _FakeItem(text="Capitolo 1", label="section_header", level=1, page_no=2),
        _FakeItem(text="Contenuto del capitolo.", label="text", page_no=2),
    ])
    sezioni = de._estrai_sezioni(doc)
    assert len(sezioni) == 2
    assert sezioni[0].titolo == "Introduzione"
    assert sezioni[0].testo == "Prima del titolo."
    assert sezioni[1].titolo == "Capitolo 1"
    assert sezioni[1].testo == "Contenuto del capitolo."
    assert sezioni[1].posizione == "p. 2"


def test_estrai_sezioni_header_sotto_max_livello_non_apre_sezione():
    # MAX_LIVELLO_SEZIONE = 2: un header di livello 3 non deve chiudere la sezione corrente.
    doc = _FakeDoc([
        _FakeItem(text="Titolo Alto", label="section_header", level=1),
        _FakeItem(text="Sotto-paragrafo", label="section_header", level=3),
        _FakeItem(text="Testo sotto il sotto-paragrafo.", label="text"),
    ])
    sezioni = de._estrai_sezioni(doc)
    assert len(sezioni) == 1
    assert sezioni[0].titolo == "Titolo Alto"
    # Il testo del sotto-header (livello 3) confluisce come testo normale
    assert "Sotto-paragrafo" in sezioni[0].testo
    assert "Testo sotto il sotto-paragrafo." in sezioni[0].testo


def test_estrai_sezioni_tabelle_separate_dal_testo():
    doc = _FakeDoc([
        _FakeItem(text="Testo introduttivo.", label="text"),
        _FakeItem(label="table", table_md="| A | B |\n|---|---|\n| 1 | 2 |"),
        _FakeItem(text="Testo dopo la tabella.", label="text"),
    ])
    sezioni = de._estrai_sezioni(doc)
    assert len(sezioni) == 1
    assert sezioni[0].blocchi_tabella == ["| A | B |\n|---|---|\n| 1 | 2 |"]
    assert "Testo introduttivo." in sezioni[0].testo
    assert "Testo dopo la tabella." in sezioni[0].testo
    # La tabella non deve comparire nel testo narrativo
    assert "| A | B |" not in sezioni[0].testo


def test_estrai_sezioni_tabella_vuota_ignorata():
    doc = _FakeDoc([_FakeItem(label="table", table_md="   ")])
    sezioni = de._estrai_sezioni(doc)
    assert sezioni == []


def test_estrai_sezioni_documento_vuoto():
    doc = _FakeDoc([])
    assert de._estrai_sezioni(doc) == []


def test_estrai_sezioni_header_senza_testo_mantiene_titolo_precedente():
    doc = _FakeDoc([
        _FakeItem(text="Titolo Iniziale", label="section_header", level=1),
        _FakeItem(text="", label="section_header", level=1),  # header vuoto: non sovrascrive
        _FakeItem(text="Corpo.", label="text"),
    ])
    sezioni = de._estrai_sezioni(doc)
    assert len(sezioni) == 1
    assert sezioni[0].titolo == "Titolo Iniziale"


# --- _ha_layer_testo -----------------------------------------------------

def _crea_pdf_con_testo(path: Path, testo: str) -> None:
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path))
    y = 750
    # drawString non fa wrapping: spezziamo manualmente su piu' righe cosi'
    # anche un testo lungo resta interamente dentro la pagina ed estraibile.
    for i in range(0, len(testo), 90):
        c.drawString(50, y, testo[i:i + 90])
        y -= 15
    c.save()


def _crea_pdf_vuoto(path: Path) -> None:
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(path))
    c.showPage()
    c.save()


def test_ha_layer_testo_pdf_con_testo(tmp_path):
    pdf_path = tmp_path / "con_testo.pdf"
    testo_lungo = (
        "Questo e' un testo estraibile lungo abbastanza da superare la soglia di "
        "200 caratteri impostata come default nella funzione di controllo rapido, "
        "quindi deve essere sicuramente rilevato come testo utile dall'estrattore."
    )
    assert len(testo_lungo) >= 200
    _crea_pdf_con_testo(pdf_path, testo_lungo)
    assert de._ha_layer_testo(pdf_path) is True


def test_ha_layer_testo_pdf_scansionato_senza_testo(tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    _crea_pdf_vuoto(pdf_path)
    assert de._ha_layer_testo(pdf_path) is False


def test_ha_layer_testo_soglia_alta_forza_false(tmp_path):
    pdf_path = tmp_path / "corto.pdf"
    _crea_pdf_con_testo(pdf_path, "Testo corto.")
    assert de._ha_layer_testo(pdf_path, soglia_caratteri=10_000) is False


# --- ingest_pdf / ingest_cartella (con _converti_pdf mockato) -------------

def test_ingest_pdf_usa_titolo_da_filename(monkeypatch, tmp_path):
    pdf_path = tmp_path / "Il_Mio_Libro.pdf"
    pdf_path.write_bytes(b"%PDF-fake")

    fake_doc = _FakeDoc([_FakeItem(text="Un paragrafo di prova sufficientemente lungo.", label="text", page_no=1)])
    monkeypatch.setattr(de, "_converti_pdf", lambda path, ocr_enabled=True: fake_doc)

    chunks = de.ingest_pdf(pdf_path, TipoFonte.ARTICOLO)
    assert len(chunks) >= 1
    assert chunks[0].fonte_titolo == "Il Mio Libro"
    assert chunks[0].tipo_fonte == TipoFonte.ARTICOLO
    assert chunks[0].fonte_path == str(pdf_path)


def test_ingest_pdf_titolo_esplicito_ha_precedenza(monkeypatch, tmp_path):
    pdf_path = tmp_path / "originale.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    fake_doc = _FakeDoc([_FakeItem(text="Testo qualsiasi per generare un chunk.", label="text")])
    monkeypatch.setattr(de, "_converti_pdf", lambda path, ocr_enabled=True: fake_doc)

    chunks = de.ingest_pdf(pdf_path, TipoFonte.LIBRO, fonte_titolo="Titolo Personalizzato")
    assert chunks[0].fonte_titolo == "Titolo Personalizzato"


def test_ingest_cartella_processa_solo_pdf_in_ordine(monkeypatch, tmp_path):
    (tmp_path / "b.pdf").write_bytes(b"%PDF-fake")
    (tmp_path / "a.pdf").write_bytes(b"%PDF-fake")
    (tmp_path / "note.txt").write_text("ignorami")

    ordine_processati = []

    def fake_converti(path, ocr_enabled=True):
        ordine_processati.append(path.name)
        return _FakeDoc([_FakeItem(text="Testo del documento numero " + path.stem, label="text")])

    monkeypatch.setattr(de, "_converti_pdf", fake_converti)
    chunks = de.ingest_cartella(tmp_path, TipoFonte.LIBRO)

    assert ordine_processati == ["a.pdf", "b.pdf"]  # sorted()
    assert len(chunks) == 2
