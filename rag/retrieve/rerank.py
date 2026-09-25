"""Reranking dei candidati della ricerca ibrida con un cross-encoder.

Fuori da Ollama (che non espone reranking nativo): un cross-encoder fa un
solo forward pass per coppia query-candidato, non generazione autoregressiva,
quindi resta sostenibile su CPU anche con l'hardware target del progetto.

Import di FlagEmbedding differito nella classe, cosi' rag/retrieve/ resta
importabile e la logica di selezione (_ordina_per_punteggio) testabile
senza scaricare il modello (~1.1GB, torch incluso).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag.common.monitoring import TracciatoreLatenza

MODELLO_RERANKER = "BAAI/bge-reranker-v2-m3"
TOP_N_DEFAULT = 6


def _ordina_per_punteggio(
    candidati: list[dict], punteggi: list[float], top_n: int
) -> list[dict]:
    """Ordina i candidati per punteggio decrescente e tronca a top_n.

    Arricchisce ciascun record candidato con il campo 'rerankScore'.
    Isolata dalla chiamata al modello per essere testabile senza
    FlagEmbedding/torch: qui si verifica solo la logica di selezione, non
    la qualita' dei punteggi (quella richiede il modello reale).
    """
    if len(candidati) != len(punteggi):
        raise ValueError(
            f"candidati ({len(candidati)}) e punteggi ({len(punteggi)}) devono avere la stessa lunghezza"
        )
    risultati = []
    for cand, score in zip(candidati, punteggi):
        c = dict(cand)
        c["rerankScore"] = round(float(score), 4)
        risultati.append((c, score))

    accoppiati = sorted(risultati, key=lambda cp: cp[1], reverse=True)
    return [c for c, _ in accoppiati[:top_n]]


class CrossEncoderReranker:
    """Wrapper minimale su BAAI/bge-reranker-v2-m3 (FlagEmbedding)."""

    def __init__(self, modello: str = MODELLO_RERANKER) -> None:
        self.modello_nome = modello
        self._modello = None  # caricato lazy al primo uso

    def _carica_modello(self):
        if self._modello is None:
            from FlagEmbedding import FlagReranker

            # use_fp16=True: dimezza la memoria a fronte di una perdita di
            # precisione trascurabile per il reranking, importante con il
            # vincolo di RAM del progetto.
            self._modello = FlagReranker(self.modello_nome, use_fp16=True)
        return self._modello

    def _calcola_punteggi(self, query: str, testi: list[str]) -> list[float]:
        modello = self._carica_modello()
        coppie = [[query, testo] for testo in testi]
        return modello.compute_score(coppie, normalize=True)

    def rerank(
        self,
        query: str,
        candidati: list[dict],
        top_n: int = TOP_N_DEFAULT,
        tracciatore: TracciatoreLatenza | None = None,
    ) -> list[dict]:
        """Riordina i candidati della ricerca ibrida per rilevanza rispetto
        alla query e ritorna i top_n (i record passano invariati, arricchiti
        solo dall'ordinamento).
        """
        if not candidati:
            return []

        def _esegui():
            testi = [c["testo"] for c in candidati]
            punteggi = self._calcola_punteggi(query, testi)
            return _ordina_per_punteggio(candidati, punteggi, top_n)

        if tracciatore:
            with tracciatore.misura("rerank"):
                return _esegui()
        return _esegui()


if __name__ == "__main__":
    # Smoke test della sola logica di selezione: nessuna dipendenza da
    # FlagEmbedding/torch. Il test contro il modello reale (qualita' dei
    # punteggi) va fatto nel tuo ambiente con FlagEmbedding installato.
    candidati_prova = [
        {"chunk_id": "a", "testo": "La teoria VSEPR predice la geometria molecolare."},
        {"chunk_id": "b", "testo": "Il legame ionico nasce da trasferimento di elettroni."},
        {"chunk_id": "c", "testo": "L'entropia misura il disordine di un sistema."},
    ]
    punteggi_finti = [0.2, 0.9, 0.5]  # simula il candidato "b" come piu' rilevante

    top2 = _ordina_per_punteggio(candidati_prova, punteggi_finti, top_n=2)
    assert [c["chunk_id"] for c in top2] == ["b", "c"], "attesi b poi c in base ai punteggi finti"
    print(f"OK — selezione top_n verificata: {[c['chunk_id'] for c in top2]} (atteso ['b', 'c'])")
