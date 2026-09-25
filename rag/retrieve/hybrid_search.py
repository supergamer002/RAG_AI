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
) -> tuple[list[str], dict[str, float]]:
    """Ritorna i chunk_id in ordine di similarita' e un dizionario id -> denseScore."""
    righe = (
        tabella.search(vettore_query, vector_column_name="vector")
        .limit(k)
        .select(["chunk_id", "_distance"])
        .to_list()
    )
    id_list = []
    punteggi = {}
    for r in righe:
        cid = r["chunk_id"]
        id_list.append(cid)
        # Converti _distance (distanza L2/Cosine) in score di similarita' 0..1
        dist = r.get("_distance", 1.0)
        punteggi[cid] = max(0.0, round(1.0 - float(dist), 4)) if dist <= 1.0 else round(1.0 / (1.0 + float(dist)), 4)
    return id_list, punteggi


def _ricerca_fulltext(
    tabella: lancedb.table.Table, query_testo: str, k: int
) -> tuple[list[str], dict[str, float]]:
    """Ritorna i chunk_id in ordine di rilevanza BM25 e un dizionario id -> bm25Score."""
    righe = (
        tabella.search(query_testo, query_type="fts")
        .limit(k)
        .select(["chunk_id", "_score"])
        .to_list()
    )
    id_list = []
    punteggi = {}
    for r in righe:
        cid = r["chunk_id"]
        id_list.append(cid)
        punteggi[cid] = round(float(r.get("_score", 0.0)), 4)
    return id_list, punteggi


def _rrf_fusion(
    ranking_dense: list[str],
    ranking_fts: list[str],
    k: int = RRF_K,
    alpha: float = 0.5,
) -> list[str]:
    """Fonde le due liste ordinate (dense e fts) pesando dense con alpha e fts con (1 - alpha).

    score(id) = alpha * (1 / (k + rank_dense)) + (1 - alpha) * (1 / (k + rank_fts))
    """
    punteggi: dict[str, float] = {}
    for rank, chunk_id in enumerate(ranking_dense, start=1):
        punteggi[chunk_id] = punteggi.get(chunk_id, 0.0) + alpha * (1.0 / (k + rank))
    for rank, chunk_id in enumerate(ranking_fts, start=1):
        punteggi[chunk_id] = punteggi.get(chunk_id, 0.0) + (1.0 - alpha) * (1.0 / (k + rank))
    return sorted(punteggi, key=punteggi.get, reverse=True)


def ricerca_ibrida(
    tabella: lancedb.table.Table,
    vettore_query: list[float],
    query_testo: str,
    top_k: int = TOP_K_CANDIDATI,
    tracciatore: TracciatoreLatenza | None = None,
    search_mode: str = "hybrid",
    hybrid_alpha: float = 0.5,
) -> list[dict]:
    """Esegue ricerca secondo search_mode ('hybrid', 'dense', 'sparse'/'bm25'),
    applica hybrid_alpha per bilanciare RRF, e ritorna i top_k chunk.
    """
    def _esegui():
        k_candidati = top_k * 2  # margine sopra top_k prima della fusione
        mode = (search_mode or "hybrid").lower()

        if mode == "dense":
            id_fusi, punteggi_dense = _ricerca_vettoriale(tabella, vettore_query, top_k)
            punteggi_fts = {}
        elif mode in ("sparse", "bm25", "fts"):
            id_fusi, punteggi_fts = _ricerca_fulltext(tabella, query_testo, top_k)
            punteggi_dense = {}
        else:
            id_dense, punteggi_dense = _ricerca_vettoriale(tabella, vettore_query, k_candidati)
            id_fts, punteggi_fts = _ricerca_fulltext(tabella, query_testo, k_candidati)
            id_fusi = _rrf_fusion(id_dense, id_fts, alpha=hybrid_alpha)[:top_k]

        if not id_fusi:
            return []

        lista_sql = ", ".join(f"'{cid.replace('\'', '\'\'')}'" for cid in id_fusi)
        righe = tabella.search().where(f"chunk_id IN ({lista_sql})").to_list()

        # to_list() non garantisce l'ordine del filtro IN: riordina secondo id_fusi e arricchisci con i punteggi.
        per_id = {r["chunk_id"]: r for r in righe}
        risultati = []
        for cid in id_fusi:
            if cid in per_id:
                record = dict(per_id[cid])
                record["denseScore"] = punteggi_dense.get(cid, 0.0)
                record["bm25Score"] = punteggi_fts.get(cid, 0.0)
                risultati.append(record)
        return risultati

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
