"""Chunking per il RAG: diverso dal chunking per fine-tuning.

Il fine-tuning usa unita' tematiche larghe (300-1500 parole) per generare
domanda/risposta. Il RAG ha bisogno di granularita' piu' fine con overlap,
per massimizzare la precisione del retrieval senza perdere contesto ai
bordi del chunk.

Input atteso: una lista di "sezioni" gia' delimitate a monte (per Docling,
gli header rilevati; per le unita' gia' segmentate, l'unita' stessa e'
la sezione). Il chunker non spezza mai a meta' frase: satura per frasi
fino al target, poi apre un nuovo chunk con overlap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.common.schema import Chunk, TipoFonte, stima_token

TARGET_TOKEN = 600
OVERLAP_RATIO = 0.12

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀÈÉÌÒÙ0-9])")


@dataclass
class Sezione:
    """Una sezione/capitolo/unita' con testo continuo da spezzare in chunk.

    blocchi_tabella: contenuto tabellare (Markdown/HTML) individuato a monte
    dall'estrattore (Docling: item.label == "table"). Ogni blocco diventa
    un chunk a se', mai passato allo splitter a frasi: spezzare una riga
    di tabella a meta' corrompe la struttura e rende il chunk inutile per
    il retrieval.
    """

    titolo: str
    testo: str
    posizione: str = ""  # pagina, timestamp o range pagine, se noto
    blocchi_tabella: list[str] = field(default_factory=list)


def _split_frasi(testo: str) -> list[str]:
    testo = testo.strip()
    if not testo:
        return []
    frasi = _SENTENCE_SPLIT.split(testo)
    return [f.strip() for f in frasi if f.strip()]


def chunk_sezione(
    sezione: Sezione,
    fonte_titolo: str,
    tipo_fonte: TipoFonte,
    fonte_path: str = "",
    lingua: str = "it",
    target_token: int = TARGET_TOKEN,
    overlap_ratio: float = OVERLAP_RATIO,
) -> list[Chunk]:
    """Spezza una sezione in chunk da ~target_token, con overlap tra chunk
    consecutivi. Non spezza mai a meta' frase ne' a meta' tabella.
    """
    risultato: list[Chunk] = []

    def emetti_semplice(testo_chunk: str) -> None:
        risultato.append(
            Chunk(
                testo=testo_chunk,
                fonte_titolo=fonte_titolo,
                tipo_fonte=tipo_fonte,
                sezione=sezione.titolo,
                posizione=sezione.posizione,
                fonte_path=fonte_path,
                lingua=lingua,
            )
        )

    # Tabelle: un chunk per blocco, nessuno split. Vengono prima del testo
    # narrativo cosi' l'ordine riflette la posizione tipica nel documento
    # (tabella introdotta e poi commentata), non e' un requisito stretto.
    for blocco in sezione.blocchi_tabella:
        if blocco.strip():
            emetti_semplice(blocco.strip())

    frasi = _split_frasi(sezione.testo)
    if not frasi:
        return risultato

    chunk_target_parole = int(target_token / 1.3)
    overlap_parole = int(chunk_target_parole * overlap_ratio)

    chunk_frasi: list[str] = []
    chunk_parole = 0

    def emetti(frasi_correnti: list[str]) -> None:
        if not frasi_correnti:
            return
        emetti_semplice(" ".join(frasi_correnti))

    i = 0
    while i < len(frasi):
        frase = frasi[i]
        n_parole = len(frase.split())

        # Frase singola gia' oltre il target (es. tabella linearizzata):
        # emessa come chunk a se', non spezzata ulteriormente.
        if not chunk_frasi and n_parole >= chunk_target_parole:
            emetti([frase])
            i += 1
            continue

        if chunk_parole + n_parole > chunk_target_parole and chunk_frasi:
            emetti(chunk_frasi)
            # overlap: riparti dalle ultime frasi del chunk appena chiuso,
            # non da zero, cosi' il chunk successivo mantiene contesto.
            parole_accumulate = 0
            frasi_overlap: list[str] = []
            for f in reversed(chunk_frasi):
                parole_accumulate += len(f.split())
                frasi_overlap.insert(0, f)
                if parole_accumulate >= overlap_parole:
                    break
            chunk_frasi = frasi_overlap
            chunk_parole = parole_accumulate
            continue  # non avanza i: la frase corrente entra nel nuovo chunk

        chunk_frasi.append(frase)
        chunk_parole += n_parole
        i += 1

    emetti(chunk_frasi)
    return risultato


def chunk_documento(
    sezioni: list[Sezione],
    fonte_titolo: str,
    tipo_fonte: TipoFonte,
    fonte_path: str = "",
    lingua: str = "it",
    target_token: int = TARGET_TOKEN,
    overlap_ratio: float = OVERLAP_RATIO,
) -> list[Chunk]:
    """Applica chunk_sezione a tutte le sezioni di un documento."""
    chunks: list[Chunk] = []
    for sezione in sezioni:
        chunks.extend(
            chunk_sezione(
                sezione,
                fonte_titolo,
                tipo_fonte,
                fonte_path,
                lingua,
                target_token=target_token,
                overlap_ratio=overlap_ratio,
            )
        )
    return chunks


if __name__ == "__main__":
    # Smoke test manuale: nessuna dipendenza esterna necessaria.
    testo_prova = (
        "La termodinamica chimica studia gli scambi di energia nelle "
        "reazioni. Il primo principio afferma che l'energia non si crea "
        "ne' si distrugge. Il secondo principio introduce l'entropia come "
        "misura del disordine. In un sistema isolato l'entropia non puo' "
        "diminuire nel tempo. Questo vincola la direzione spontanea delle "
        "trasformazioni chimiche. La funzione di Gibbs combina entalpia ed "
        "entropia per prevedere la spontaneita' a pressione costante. "
    ) * 8  # forza piu' chunk

    sez = Sezione(titolo="Cap. 3 - Termodinamica", testo=testo_prova, posizione="p. 40-45")
    out = chunk_documento([sez], "Chimica Generale", TipoFonte.LIBRO)
    print(f"Frasi totali: {len(_split_frasi(testo_prova))}")
    print(f"Chunk generati: {len(out)}")
    for c in out:
        print(f"  [{stima_token(c.testo):>4} tok stimati] {c.testo[:70]}...")

    # Test dedicato: blocco tabella non deve essere spezzato dallo splitter
    # a frasi, anche se contiene punteggiatura che assomiglia a fine frase
    # (es. numeri decimali con punto, tipici nelle tabelle scientifiche).
    tabella_prova = (
        "| Composto | Massa molare (g/mol) | Stato |\n"
        "|---|---|---|\n"
        "| H2O | 18.02 | Liquido |\n"
        "| CO2 | 44.01 | Gas |\n"
        "| NaCl | 58.44 | Solido |"
    )
    sez_con_tabella = Sezione(
        titolo="Cap. 4 - Proprieta' composti",
        testo="Segue una tabella riassuntiva delle proprieta' principali.",
        blocchi_tabella=[tabella_prova],
    )
    out_tabella = chunk_documento([sez_con_tabella], "Chimica Generale", TipoFonte.LIBRO)
    assert len(out_tabella) == 2, f"attesi 2 chunk (1 tabella + 1 narrativo), ottenuti {len(out_tabella)}"
    chunk_tabella = next(c for c in out_tabella if "H2O" in c.testo)
    assert chunk_tabella.testo == tabella_prova, "la tabella deve restare intatta, non spezzata dallo splitter a frasi"
    print(f"OK — blocco tabella preservato intatto ({len(chunk_tabella.testo)} caratteri, nessuno split)")
