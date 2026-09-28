"""Test estesi per rag.ingest.chunker.chunk_documento.

chunk_sezione (con e senza tabella) e' gia' coperta in tests/test_ingest.py;
la progressione dell'overlap su frasi lunghe e' coperta in
tests/test_chunker_progress.py. Qui copriamo chunk_documento su piu'
sezioni e la propagazione di fonte_path/lingua/posizione.
"""

from rag.common.schema import TipoFonte
from rag.ingest.chunker import Sezione, _split_frasi, chunk_documento


def test_chunk_documento_piu_sezioni_concatena_risultati():
    sezioni = [
        Sezione(titolo="Cap 1", testo="Prima frase del capitolo uno. Seconda frase del capitolo uno."),
        Sezione(titolo="Cap 2", testo="Prima frase del capitolo due. Seconda frase del capitolo due."),
    ]
    chunks = chunk_documento(sezioni, fonte_titolo="Libro X", tipo_fonte=TipoFonte.LIBRO)
    titoli_sezione = {c.sezione for c in chunks}
    assert titoli_sezione == {"Cap 1", "Cap 2"}
    assert all(c.fonte_titolo == "Libro X" for c in chunks)


def test_chunk_documento_propaga_fonte_path_e_lingua():
    sezioni = [Sezione(titolo="Cap 1", testo="Una frase qualsiasi per generare un chunk.")]
    chunks = chunk_documento(
        sezioni,
        fonte_titolo="Libro X",
        tipo_fonte=TipoFonte.ARTICOLO,
        fonte_path="sources/libro.json",
        lingua="en",
    )
    assert len(chunks) == 1
    assert chunks[0].fonte_path == "sources/libro.json"
    assert chunks[0].lingua == "en"
    assert chunks[0].tipo_fonte == TipoFonte.ARTICOLO


def test_chunk_documento_propaga_posizione_sezione():
    sezioni = [Sezione(titolo="Cap 1", testo="Testo con posizione nota.", posizione="p. 12-15")]
    chunks = chunk_documento(sezioni, fonte_titolo="Libro X", tipo_fonte=TipoFonte.LIBRO)
    assert chunks[0].posizione == "p. 12-15"


def test_chunk_documento_sezione_lista_vuota():
    assert chunk_documento([], fonte_titolo="Libro X", tipo_fonte=TipoFonte.LIBRO) == []


def test_chunk_documento_sezione_con_testo_vuoto_e_senza_tabelle_produce_zero_chunk():
    sezioni = [Sezione(titolo="Cap Vuoto", testo="   ")]
    chunks = chunk_documento(sezioni, fonte_titolo="Libro X", tipo_fonte=TipoFonte.LIBRO)
    assert chunks == []


def test_chunk_documento_mix_sezione_vuota_e_piena():
    sezioni = [
        Sezione(titolo="Vuota", testo=""),
        Sezione(titolo="Piena", testo="Una frase con contenuto reale."),
    ]
    chunks = chunk_documento(sezioni, fonte_titolo="Libro X", tipo_fonte=TipoFonte.LIBRO)
    assert len(chunks) == 1
    assert chunks[0].sezione == "Piena"


# --- _split_frasi ---------------------------------------------------------

def test_split_frasi_testo_vuoto():
    assert _split_frasi("") == []
    assert _split_frasi("   ") == []


def test_split_frasi_singola_frase_senza_punteggiatura_finale():
    assert _split_frasi("Una frase senza punto finale") == ["Una frase senza punto finale"]


def test_split_frasi_divide_su_punteggiatura_seguita_da_maiuscola():
    frasi = _split_frasi("Prima frase. Seconda frase! Terza frase?")
    assert frasi == ["Prima frase.", "Seconda frase!", "Terza frase?"]


def test_split_frasi_non_divide_numeri_decimali():
    # Un punto seguito da cifra non deve essere trattato come fine frase
    # (tipico nelle tabelle scientifiche: "18.02", non due frasi).
    frasi = _split_frasi("Il valore e' 18.02 g/mol in laboratorio.")
    assert len(frasi) == 1
