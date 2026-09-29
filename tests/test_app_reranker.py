from app.reranker import CrossEncoderReranker, _rank


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


def test_rank_orders_and_truncates():
    out = _rank(candidates(), [0.1, 0.9, 0.5], 2)
    assert [x["chunk_id"] for x in out] == ["b", "c"]
    assert out[0]["rerank_score"] == 0.9


def test_reranker_loads_model_once(monkeypatch):
    loads = []

    class FakeTokenizer:
        def __call__(self, qs, texts, **kwargs):
            return {"input_ids": "fake"}

    class FakeTensor:
        def reshape(self, *_):
            return self
        def detach(self):
            return self
        def cpu(self):
            return self
        def tolist(self):
            return [0.1, 0.9, 0.5]

    class FakeModel:
        def eval(self):
            return self
        def to(self, *_):
            return self
        def __call__(self, **_):
            return type("Output", (), {"logits": FakeTensor()})()

    class FakeTorch:
        class no_grad:
            def __enter__(self): return self
            def __exit__(self, *args): return False
    fake_torch = FakeTorch()

    class FakeAutoTokenizer:
        @staticmethod
        def from_pretrained(name):
            loads.append(("tokenizer", name))
            return FakeTokenizer()

    class FakeAutoModel:
        @staticmethod
        def from_pretrained(name):
            loads.append(("model", name))
            return FakeModel()

    import sys, types
    transformers = types.ModuleType("transformers")
    transformers.AutoTokenizer = FakeAutoTokenizer
    transformers.AutoModelForSequenceClassification = FakeAutoModel
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    r = CrossEncoderReranker()
    r.rerank("query", candidates(), 3)
    r.rerank("query", candidates(), 3)
    assert len(loads) == 2
