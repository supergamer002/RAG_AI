"""Test per rag.index.embed (OllamaEmbedder) e rag.index.embed_manager.

Nessuna dipendenza da un vero server Ollama: le chiamate HTTP sono mockate
con monkeypatch su requests.post, seguendo lo stesso pattern gia' usato in
tests/test_health_check.py.
"""

import pytest
import requests

from rag.index.embed import OllamaEmbedder, DIMENSIONE_OUTPUT
from rag.index.embed_manager import EmbedderManager
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


def test_embed_empty_list_nessuna_chiamata(monkeypatch):
    chiamato = []
    monkeypatch.setattr(requests, "post", lambda *a, **kw: chiamato.append(1) or _FakeResponse())
    embedder = OllamaEmbedder()
    assert embedder.embed([]) == []
    assert chiamato == []


def test_embed_singolo_batch(monkeypatch):
    def fake_post(url, json, timeout):
        assert json["model"] == "qwen3-embedding:0.6b"
        assert json["dimensions"] == DIMENSIONE_OUTPUT
        n = len(json["input"])
        return _FakeResponse({"embeddings": [[0.1] * DIMENSIONE_OUTPUT for _ in range(n)]})

    monkeypatch.setattr(requests, "post", fake_post)
    embedder = OllamaEmbedder()
    out = embedder.embed(["a", "b", "c"])
    assert len(out) == 3
    assert all(len(v) == DIMENSIONE_OUTPUT for v in out)


def test_embed_rispetta_batch_size(monkeypatch):
    chiamate = []

    def fake_post(url, json, timeout):
        chiamate.append(len(json["input"]))
        return _FakeResponse({"embeddings": [[0.0] * 4 for _ in json["input"]]})

    monkeypatch.setattr(requests, "post", fake_post)
    embedder = OllamaEmbedder(batch_size=2, dimensione=4)
    out = embedder.embed(["a", "b", "c", "d", "e"])
    assert len(out) == 5
    # 5 testi / batch_size 2 -> chiamate da 2, 2, 1
    assert chiamate == [2, 2, 1]


def test_embed_uno(monkeypatch):
    monkeypatch.setattr(
        requests, "post",
        lambda url, json, timeout: _FakeResponse({"embeddings": [[9.0, 9.0]]})
    )
    embedder = OllamaEmbedder(dimensione=2)
    assert embedder.embed_uno("ciao") == [9.0, 9.0]


def test_embed_con_tracciatore(monkeypatch):
    monkeypatch.setattr(
        requests, "post",
        lambda url, json, timeout: _FakeResponse({"embeddings": [[1.0]]})
    )
    embedder = OllamaEmbedder(dimensione=1)
    tracciatore = TracciatoreLatenza(log_automatico=False)
    out = embedder.embed(["x"], tracciatore=tracciatore)
    assert out == [[1.0]]
    assert "embedding" in tracciatore.get_statistiche()


def test_embed_connessione_fallita(monkeypatch):
    def fake_post(*a, **kw):
        raise requests.ConnectionError("connection refused")

    monkeypatch.setattr(requests, "post", fake_post)
    embedder = OllamaEmbedder()
    with pytest.raises(RuntimeError, match="non raggiungibile"):
        embedder.embed(["testo"])


def test_embed_risposta_non_json(monkeypatch):
    monkeypatch.setattr(
        requests, "post",
        lambda *a, **kw: _FakeResponse(json_data=None, text="<html>errore</html>")
    )
    embedder = OllamaEmbedder()
    with pytest.raises(RuntimeError, match="non JSON"):
        embedder.embed(["testo"])


def test_embed_numero_embedding_inatteso(monkeypatch):
    # Il server ritorna meno embedding di quanti testi inviati.
    monkeypatch.setattr(
        requests, "post",
        lambda *a, **kw: _FakeResponse({"embeddings": [[0.1]]})
    )
    embedder = OllamaEmbedder(dimensione=1)
    with pytest.raises(ValueError, match="attesi 2"):
        embedder.embed(["a", "b"])


def test_embed_http_error_status(monkeypatch):
    monkeypatch.setattr(
        requests, "post",
        lambda *a, **kw: _FakeResponse(status_code=500, text="internal error")
    )
    embedder = OllamaEmbedder()
    with pytest.raises(RuntimeError, match="non raggiungibile"):
        embedder.embed(["testo"])


# --- EmbedderManager --------------------------------------------------

def test_embedder_manager_cache_stesso_embedder():
    manager = EmbedderManager()
    e1 = manager.get_embedder("modelloA", "http://host1/api/embed")
    e2 = manager.get_embedder("modelloA", "http://host1/api/embed")
    assert e1 is e2


def test_embedder_manager_chiavi_diverse_per_modello():
    manager = EmbedderManager()
    e1 = manager.get_embedder("modelloA", "http://host1/api/embed")
    e2 = manager.get_embedder("modelloB", "http://host1/api/embed")
    assert e1 is not e2
    assert e1.modello == "modelloA"
    assert e2.modello == "modelloB"


def test_embedder_manager_chiavi_diverse_per_url():
    manager = EmbedderManager()
    e1 = manager.get_embedder("modelloA", "http://host1/api/embed")
    e2 = manager.get_embedder("modelloA", "http://host2/api/embed")
    assert e1 is not e2
    assert e1.url != e2.url
