"""Middleware e utilita' di monitoring per tracciare la latenza delle fasi RAG:
embedding, hybrid search, rerank, generation.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Callable, Any, Generator, Dict, List

logger = logging.getLogger("rag.monitoring")


class TracciatoreLatenza:
    """Raccoglie e calcola statistiche sulle latenze delle varie fasi del sistema RAG."""

    def __init__(self, log_automatico: bool = True) -> None:
        self.log_automatico = log_automatico
        self._misure: Dict[str, List[float]] = {}

    def registra_latenza(self, fase: str, durata_secondi: float) -> None:
        """Registra manualmente la durata in secondi per una specifica fase."""
        if fase not in self._misure:
            self._misure[fase] = []
        self._misure[fase].append(durata_secondi)
        if self.log_automatico:
            logger.info("Fase RAG [%s] completata in %.3f secondi", fase, durata_secondi)

    @contextmanager
    def misura(self, fase: str) -> Generator[None, None, None]:
        """Context manager per misurare la durata di un blocco di codice."""
        inizio = time.perf_counter()
        try:
            yield
        finally:
            durata = time.perf_counter() - inizio
            self.registra_latenza(fase, durata)

    def traccia(self, fase: str) -> Callable:
        """Decoratore per misurare l'esecuzione di una funzione."""
        def decorator(func: Callable) -> Callable:
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with self.misura(fase):
                    return func(*args, **kwargs)
            return wrapper
        return decorator

    def get_statistiche(self, fase: str | None = None) -> Dict[str, Dict[str, float]]:
        """Ritorna statistiche (media, min, max, totale, conteggio) per fase o per tutte le fasi."""
        fasi_da_calcolare = [fase] if fase and fase in self._misure else list(self._misure.keys())
        stats: Dict[str, Dict[str, float]] = {}

        for f in fasi_da_calcolare:
            valori = self._misure.get(f, [])
            if not valori:
                continue
            stats[f] = {
                "conteggio": float(len(valori)),
                "totale_s": sum(valori),
                "media_s": sum(valori) / len(valori),
                "min_s": min(valori),
                "max_s": max(valori),
            }
        return stats

    def report(self) -> str:
        """Genera un report testuale formattato con le statistiche di latenza."""
        stats = self.get_statistiche()
        if not stats:
            return "Nessuna misurazione registrata."

        righe = ["=== Report Latenza RAG ==="]
        for f, s in stats.items():
            righe.append(
                f"Fase: {f:<15} | Conteggio: {int(s['conteggio']):<3} | "
                f"Media: {s['media_s']:.3f}s | Min: {s['min_s']:.3f}s | Max: {s['max_s']:.3f}s | "
                f"Totale: {s['totale_s']:.3f}s"
            )
        return "\n".join(righe)

    def reset(self) -> None:
        """Cancella tutte le misurazioni accumulatene finora."""
        self._misure.clear()


# Istanza globale predefinita per comoda condivisione nel sistema
tracciatore_globale = TracciatoreLatenza()
