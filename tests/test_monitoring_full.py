"""Test estesi per rag.common.monitoring.TracciatoreLatenza.

registra_latenza/misura/traccia/reset sono gia' coperti in
tests/test_monitoring.py. Qui copriamo report() e get_statistiche(fase=...).
"""

from rag.common.monitoring import TracciatoreLatenza


def test_get_statistiche_nessuna_misura():
    t = TracciatoreLatenza(log_automatico=False)
    assert t.get_statistiche() == {}


def test_get_statistiche_filtra_per_fase():
    t = TracciatoreLatenza(log_automatico=False)
    t.registra_latenza("embedding", 0.1)
    t.registra_latenza("rerank", 0.2)

    solo_embedding = t.get_statistiche(fase="embedding")
    assert set(solo_embedding.keys()) == {"embedding"}
    assert solo_embedding["embedding"]["conteggio"] == 1.0


def test_get_statistiche_fase_inesistente_ritorna_tutte():
    """Se la fase richiesta non e' presente, il filtro ricade su tutte le fasi."""
    t = TracciatoreLatenza(log_automatico=False)
    t.registra_latenza("embedding", 0.1)
    stats = t.get_statistiche(fase="fase-mai-vista")
    assert set(stats.keys()) == {"embedding"}


def test_get_statistiche_calcoli_corretti():
    t = TracciatoreLatenza(log_automatico=False)
    for durata in (1.0, 2.0, 3.0):
        t.registra_latenza("fase", durata)
    stats = t.get_statistiche()["fase"]
    assert stats["conteggio"] == 3.0
    assert stats["totale_s"] == 6.0
    assert stats["media_s"] == 2.0
    assert stats["min_s"] == 1.0
    assert stats["max_s"] == 3.0


def test_report_senza_misure():
    t = TracciatoreLatenza(log_automatico=False)
    assert t.report() == "Nessuna misurazione registrata."


def test_report_con_misure_contiene_intestazione_e_fasi():
    t = TracciatoreLatenza(log_automatico=False)
    t.registra_latenza("embedding", 0.5)
    t.registra_latenza("rerank", 0.25)
    report = t.report()
    assert "=== Report Latenza RAG ===" in report
    assert "embedding" in report
    assert "rerank" in report
    assert "Conteggio: 1" in report


def test_report_dopo_reset_torna_vuoto():
    t = TracciatoreLatenza(log_automatico=False)
    t.registra_latenza("embedding", 0.1)
    t.reset()
    assert t.report() == "Nessuna misurazione registrata."
    assert t.get_statistiche() == {}
