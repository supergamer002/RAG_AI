"""Test per rag.generate.answer (costruisci_messaggi gia' coperto in
tests/test_retrieve_and_generate.py; qui copriamo OllamaGenerator e rispondi).
"""

import pytest
import requests

from rag.generate.answer import (
    OllamaGenerator,
    rispondi,
    _formatta_contesto,
    MODELLO_GENERAZIONE,
)
from rag.common.monitoring import TracciatoreLatenza


class _FakeResponse:
    def __init__(self, json_data=None, status_code=200, text=""):
        self._json_data = json_data
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self._json_data is None:
            raise ValueError("no json")
        return self._json_data


def test_formatta_contesto_senza_sezione_ne_posizione():
    chunk = [{"fonte_titolo": "Solo Titolo", "testo": "Contenuto puro"}]
    out = _formatta_contesto(chunk)
    assert out == "[Fonte: Solo Titolo]\nContenuto puro"


def test_formatta_contesto_multi_chunk():
    chunk = [
        {"fonte_titolo": "A", "testo": "primo"},
        {"fonte_titolo": "B", "sezione": "Cap 1", "testo": "secondo"},
    ]
    out = _formatta_contesto(chunk)
    assert "[Fonte: A]\nprimo" in out
    assert "[Fonte: B, Cap 1]\nsecondo" in out
    assert out.count("\n\n") == 1


def test_genera_payload_corretto(monkeypatch):
    catturato = {}

    def fake_post(url, json, timeout):
        catturato["url"] = url
        catturato["json"] = json
        return _FakeResponse({"message": {"role": "assistant", "content": "risposta"}})

    monkeypatch.setattr(requests, "post", fake_post)
    gen = OllamaGenerator(url="http://host/api/chat")
    out = gen.genera([{"role": "user", "content": "ciao"}])
    assert out == "risposta"
    assert catturato["json"]["model"] == MODELLO_GENERAZIONE
    assert catturato["json"]["stream"] is False
    assert catturato["url"] == "http://host/api/chat"


def test_genera_connessione_fallita(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("boom")))
    gen = OllamaGenerator()
    with pytest.raises(RuntimeError, match="non raggiungibile"):
        gen.genera([{"role": "user", "content": "ciao"}])


def test_genera_risposta_non_json(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: _FakeResponse(json_data=None, text="oops"))
    gen = OllamaGenerator()
    with pytest.raises(RuntimeError, match="non JSON"):
        gen.genera([])


def test_genera_senza_contenuto(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: _FakeResponse({"message": {}}))
    gen = OllamaGenerator()
    with pytest.raises(ValueError, match="senza contenuto"):
        gen.genera([])


def test_rispondi_senza_chunk_nessuna_chiamata_rete(monkeypatch):
    chiamato = []
    monkeypatch.setattr(requests, "post", lambda *a, **kw: chiamato.append(1))
    esito = rispondi("Domanda?", [])
    assert "non copre questo punto" in esito
    assert chiamato == []


def test_rispondi_con_chunk_usa_generatore_fornito(monkeypatch):
    monkeypatch.setattr(
        requests, "post",
        lambda *a, **kw: _FakeResponse({"message": {"content": "Risposta finale"}})
    )
    chunk = [{"fonte_titolo": "F", "testo": "contesto"}]
    gen = OllamaGenerator(url="http://host/api/chat")
    esito = rispondi("Domanda?", chunk, generatore=gen)
    assert esito == "Risposta finale"


def test_rispondi_con_tracciatore(monkeypatch):
    monkeypatch.setattr(
        requests, "post",
        lambda *a, **kw: _FakeResponse({"message": {"content": "ok"}})
    )
    chunk = [{"fonte_titolo": "F", "testo": "contesto"}]
    gen = OllamaGenerator()
    tracciatore = TracciatoreLatenza(log_automatico=False)
    rispondi("Domanda?", chunk, generatore=gen, tracciatore=tracciatore)
    assert "generation" in tracciatore.get_statistiche()


def test_rispondi_propaga_errore_generazione(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError("no")))
    chunk = [{"fonte_titolo": "F", "testo": "contesto"}]
    with pytest.raises(RuntimeError):
        rispondi("Domanda?", chunk, generatore=OllamaGenerator())
