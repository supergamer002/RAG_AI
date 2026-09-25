"""Schema condiviso per i chunk indicizzati nel sistema RAG.

Ogni fonte (libri già segmentati, PDF nuovi via Docling, trascrizioni video)
converge su questa struttura prima di passare a embedding + LanceDB.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum


class TipoFonte(str, Enum):
    LIBRO = "libro"
    ARTICOLO = "articolo"
    VIDEO = "video"


@dataclass
class Chunk:
    """Unita' minima indicizzata: testo + metadata per citazione e filtro."""

    testo: str
    fonte_titolo: str          # titolo libro / articolo / video
    tipo_fonte: TipoFonte
    sezione: str = ""          # capitolo, sezione del paper, o "" se non nota
    posizione: str = ""        # pagina ("p. 42") o timestamp ("12:34") o ""
    fonte_path: str = ""       # percorso file o URL originale
    lingua: str = "it"
    chunk_id: str = field(default="", init=False)

    def __post_init__(self) -> None:
        # id deterministico: stesso testo + stessa fonte => stesso id.
        # Permette upsert idempotenti in LanceDB (re-ingest senza duplicati).
        base = f"{self.fonte_titolo}|{self.sezione}|{self.posizione}|{self.testo}"
        self.chunk_id = hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]

    def to_record(self) -> dict:
        """Dizionario pronto per l'inserimento in LanceDB."""
        record = asdict(self)
        record["tipo_fonte"] = self.tipo_fonte.value
        return record


_TOKENIZER_CACHE = None


def conta_token_esatto(testo: str, modello_tokenizer: str = "Qwen/Qwen2.5-0.5B") -> int | None:
    """Tenta di calcolare il numero esatto di token usando HuggingFace AutoTokenizer.

    Ritorna None se transformers o il modello specificato non sono disponibili.
    """
    global _TOKENIZER_CACHE
    if _TOKENIZER_CACHE is None:
        try:
            from transformers import AutoTokenizer
            _TOKENIZER_CACHE = AutoTokenizer.from_pretrained(modello_tokenizer, trust_remote_code=True)
        except Exception:
            _TOKENIZER_CACHE = False

    if _TOKENIZER_CACHE is False or _TOKENIZER_CACHE is None:
        return None

    try:
        return len(_TOKENIZER_CACHE.encode(testo))
    except Exception:
        return None


def stima_token(testo: str, usa_tokenizer_esatto: bool = True) -> int:
    """Stima o calcola il numero di token per il testo dato.

    Se `usa_tokenizer_esatto` e' True, tenta prima il conteggio esatto tramite
    tokenizer Qwen/HuggingFace. Se fallisce o se non installato, ricade sulla
    stima euristica word-based (1 parola ~= 1.3 token).
    """
    if usa_tokenizer_esatto:
        conteggio = conta_token_esatto(testo)
        if conteggio is not None:
            return conteggio

    parole = testo.split()
    return int(len(parole) * 1.3)
