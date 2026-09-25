"""Test per rag.common.monitoring e l'integrazione del tracciatore di latenza nelle varie fasi RAG."""

import time
from rag.common.monitoring import TracciatoreLatenza, tracciatore_globale
from rag.common.schema import Chunk, TipoFonte


def test_tracciatore_misura_e_statistiche():
    tracciatore = TracciatoreLatenza(log_automatico=False)

    with tracciatore.misura("fase_test"):
        time.sleep(0.01)

    with tracciatore.misura("fase_test"):
        time.sleep(0.02)

    stats = tracciatore.get_statistiche("fase_test")
    assert "fase_test" in stats
    s = stats["fase_test"]
    assert s["conteggio"] == 2.0
    assert s["min_s"] > 0
    assert s["max_s"] >= s["min_s"]
    assert s["totale_s"] >= 0.03

    report = tracciatore.report()
    assert "=== Report Latenza RAG ===" in report
    assert "fase_test" in report


def test_tracciatore_decoratore():
    tracciatore = TracciatoreLatenza(log_automatico=False)

    @tracciatore.traccia("funzione_decorata")
    def calcola():
        time.sleep(0.01)
        return 42

    res = calcola()
    assert res == 42
    stats = tracciatore.get_statistiche("funzione_decorata")
    assert stats["funzione_decorata"]["conteggio"] == 1.0


def test_tracciatore_reset():
    tracciatore = TracciatoreLatenza(log_automatico=False)
    with tracciatore.misura("fase_1"):
        pass

    assert "fase_1" in tracciatore.get_statistiche()
    tracciatore.reset()
    assert tracciatore.get_statistiche() == {}
    assert tracciatore.report() == "Nessuna misurazione registrata."
