from rag.common.schema import TipoFonte
from rag.ingest.chunker import Sezione, chunk_sezione


def test_long_sentence_overlap_always_terminates():
    text = " ".join(["Parola"] * 70) + ". " + " ".join(["Altra"] * 70) + "."
    chunks = chunk_sezione(
        Sezione(titolo="x", testo=text),
        fonte_titolo="doc",
        tipo_fonte=TipoFonte.LIBRO,
        target_token=50,
        overlap_ratio=0.5,
    )
    assert len(chunks) == 2
    assert all(c.testo for c in chunks)


def test_normal_overlap_preserves_progress():
    sentences = [f"Frase {i} contiene alcune parole utili per il contesto." for i in range(30)]
    chunks = chunk_sezione(
        Sezione(titolo="x", testo=" ".join(sentences)),
        fonte_titolo="doc",
        tipo_fonte=TipoFonte.LIBRO,
        target_token=30,
        overlap_ratio=0.2,
    )
    assert len(chunks) >= 2
    assert all(c.testo for c in chunks)
