"""Ricerca ibrida: dense (vettoriale) + full-text (BM25 via Tantivy, nativo
LanceDB), fusi con Reciprocal Rank Fusion.

Il solo embedding perde spesso termini esatti (nomi di composti, simboli,
sigle) su testo tecnico; il solo full-text perde la similarita' semantica.
RRF combina i due ranking senza dover normalizzare punteggi di scala
diversa (cosine similarity vs BM25 score), che non sono confrontabili
direttamente.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING
import lancedb
from lancedb.index import FTS

if TYPE_CHECKING:
    from rag.common.monitoring import TracciatoreLatenza

RRF_K = 60  # costante standard RRF: smorza il peso delle posizioni in coda
TOP_K_CANDIDATI = 20  # candidati passati al reranker (rag/retrieve/rerank.py)


def crea_indice_fulltext(
    tabella: lancedb.table.Table, campo: str = "testo", replace: bool = False
) -> None:
    """Crea o aggiorna l'indice full-text sul campo testo.

    Va richiamata dopo ogni batch di ingest significativo (l'indice FTS di
    LanceDB non si aggiorna automaticamente ad ogni singolo insert).
    Se replace=True, ricrea l'indice per includere i nuovi documenti.
    """
    indici_esistenti = {idx.name for idx in tabella.list_indices()}
    if replace or f"{campo}_idx" not in indici_esistenti:
        tabella.create_index(campo, config=FTS(), replace=replace)


def aggiorna_indice_fts_in_background(
    tabella: lancedb.table.Table, campo: str = "testo", callback: callable | None = None
) -> threading.Thread:
    """Avvia un job in background (thread) per la ricreazione/aggiornamento
    dell'indice FTS post-ingestion.

    Ritorna l'oggetto Thread avviato, consentendo all'invocante di proseguire
    o attenderne il completamento via .join().
    """
    def _worker() -> None:
        crea_indice_fulltext(tabella, campo=campo, replace=True)
        if callback:
            callback()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread


def _ricerca_vettoriale(
    tabella: lancedb.table.Table, vettore_query: list[float], k: int
) -> list[str]:
    """Ritorna i chunk_id in ordine di similarita' vettoriale decrescente."""
    righe = (
        tabella.search(vettore_query, vector_column_name="vector")
        .limit(k)
        .select(["chunk_id"])
        .to_list()
    )
    return [r["chunk_id"] for r in righe]


def _ricerca_fulltext(
    tabella: lancedb.table.Table, query_testo: str, k: int
) -> list[str]:
    """Ritorna i chunk_id in ordine di rilevanza BM25 decrescente."""
    righe = (
        tabella.search(query_testo, query_type="fts")
        .limit(k)
        .select(["chunk_id"])
        .to_list()
    )
    return [r["chunk_id"] for r in righe]


def _rrf_fusion(*ranking: list[str], k: int = RRF_K) -> list[str]:
    """Fonde N liste ordinate di chunk_id in un'unica classifica RRF.

    score(id) = somma su ogni lista di 1 / (k + rank), rank a partire da 1.
    Un id assente da una lista non contribuisce da quella lista (non viene
    penalizzato oltre il non ricevere il suo punteggio).
    """
    punteggi: dict[str, float] = {}
    for lista in ranking:
        for rank, chunk_id in enumerate(lista, start=1):
            punteggi[chunk_id] = punteggi.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(punteggi, key=punteggi.get, reverse=True)


def ricerca_ibrida(
    tabella: lancedb.table.Table,
    vettore_query: list[float],
    query_testo: str,
    top_k: int = TOP_K_CANDIDATI,
    tracciatore: TracciatoreLatenza | None = None,
) -> list[dict]:
    """Esegue dense + full-text, fonde con RRF, ritorna i record completi
    dei top_k chunk (da passare al reranker).

    Nota: LanceDB puo' emettere un DeprecationWarning su _distance/_score
    non richiesti esplicitamente nelle select(); e' un warning innocuo sul
    comportamento futuro della libreria, non influisce sul risultato.
    """
    def _esegui():
        k_candidati = top_k * 2  # margine sopra top_k prima della fusione
        id_dense = _ricerca_vettoriale(tabella, vettore_query, k_candidati)
        id_fts = _ricerca_fulltext(tabella, query_testo, k_candidati)

        id_fusi = _rrf_fusion(id_dense, id_fts)[:top_k]
        if not id_fusi:
            return []

        lista_sql = ", ".join(f"'{cid.replace('\'', '\'\'')}'" for cid in id_fusi)
        righe = tabella.search().where(f"chunk_id IN ({lista_sql})").to_list()

        # to_list() non garantisce l'ordine del filtro IN: riordina secondo id_fusi.
        per_id = {r["chunk_id"]: r for r in righe}
        return [per_id[cid] for cid in id_fusi if cid in per_id]

    if tracciatore:
        with tracciatore.misura("hybrid_search"):
            return _esegui()
    return _esegui()


if __name__ == "__main__":
    import shutil
    import tempfile

    from rag.common.schema import Chunk, TipoFonte
    from rag.index.store import apri_o_crea_tabella, connetti, upsert_chunks

    tmp = tempfile.mkdtemp()
    try:
        db = connetti(tmp)
        tabella = apri_o_crea_tabella(db, dimensione_embedding=3)

        dati = [
            ("Il legame ionico nasce da trasferimento di elettroni tra atomi.", [1.0, 0.0, 0.0]),
            ("La teoria VSEPR predice la geometria molecolare.", [0.0, 1.0, 0.0]),
            ("L'entropia misura il disordine in un sistema termodinamico.", [0.0, 0.0, 1.0]),
        ]
        chunks = [
            Chunk(testo=t, fonte_titolo="Chimica Generale", tipo_fonte=TipoFonte.LIBRO, sezione="Cap. X")
            for t, _ in dati
        ]
        upsert_chunks(tabella, chunks, [emb for _, emb in dati])
        crea_indice_fulltext(tabella)

        # Query vettoriale allineata al chunk sull'entropia (indice 2);
        # query testuale che matcha esattamente "ionico" (indice 0).
        # Ci si aspetta che entrambi emergano nei risultati fusi.
        risultati = ricerca_ibrida(
            tabella,
            vettore_query=[0.0, 0.0, 1.0],
            query_testo="legame ionico",
            top_k=3,
        )
        testi_trovati = [r["testo"] for r in risultati]
        assert any("entropia" in t for t in testi_trovati), "atteso il chunk sull'entropia (match vettoriale)"
        assert any("ionico" in t for t in testi_trovati), "atteso il chunk sul legame ionico (match full-text)"
        print(f"OK — ricerca ibrida verificata, {len(risultati)} risultati fusi:")
        for r in risultati:
            print(f"  {r['testo'][:60]}...")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
