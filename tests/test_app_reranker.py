import sys
import types

from app.reranker import CrossEncoderReranker


def candidates():
    return [
        {"chunk_id": "a", "text": "aaa"},
        {"chunk_id": "b", "text": "bbb"},
        {"chunk_id": "c", "text": "ccc"},
    ]


def test_reranker_lazy_status():
    r = CrossEncoderReranker()
    assert r.status()["status"] == "standby"
    assert r.status()["loaded"] is False


def test_reranker_orders_and_truncates(monkeypatch):
    r = CrossEncoderReranker()
    class FakeFlagReranker:
        def __init__(self, name, use_fp16=False):
            self.name = name
        def compute_score(self, pairs, normalize=True):
            return [0.1, 0.9, 0.5]
    fake = types.ModuleType("FlagEmbedding")
    fake.FlagReranker = FakeFlagReranker
    monkeypatch.setitem(sys.modules, "FlagEmbedding", fake)

    out = r.rerank("query", candidates(), 2)
    assert [x["chunk_id"] for x in out] == ["b", "c"]
    assert out[0]["rerank_score"] == 0.9
    assert r.status()["status"] == "ready"


def test_reranker_caches_model(monkeypatch):
    loads = []
    class FakeFlagReranker:
        def __init__(self, name, use_fp16=False):
            loads.append(name)
        def compute_score(self, pairs, normalize=True):
            return [0.5 for _ in pairs]
    fake = types.ModuleType("FlagEmbedding")
    fake.FlagReranker = FakeFlagReranker
    monkeypatch.setitem(sys.modules, "FlagEmbedding", fake)

    r = CrossEncoderReranker()
    r.rerank("query", candidates(), 3)
    r.rerank("query", candidates(), 3)
    assert len(loads) == 1
