"""Lazy Cross-Encoder reranker for the simplified RAG backend.

Uses BAAI/bge-reranker-v2-m3 through FlagEmbedding. The model is loaded only
on the first search that reaches the reranking stage and then kept in memory.
This keeps startup fast and avoids making the reranker a hard dependency for
basic application startup.
"""

from __future__ import annotations

MODEL_NAME = "BAAI/bge-reranker-v2-m3"
DEFAULT_CANDIDATES = 20


def _rank(candidates: list[dict], scores: list[float], top_k: int) -> list[dict]:
    if len(candidates) != len(scores):
        raise ValueError("Numero di candidati e punteggi non coincide.")
    ranked = []
    for candidate, score in zip(candidates, scores):
        item = dict(candidate)
        item["rerank_score"] = round(float(score), 4)
        ranked.append((item, float(score)))
    ranked.sort(key=lambda pair: pair[1], reverse=True)
    return [item for item, _ in ranked[:top_k]]


class CrossEncoderReranker:
    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self.model_name = model_name
        self._model = None
        self._load_error: str | None = None

    def status(self) -> dict:
        if self._model is not None:
            return {
                "status": "ready",
                "label": "Ready",
                "model": self.model_name,
                "loaded": True,
                "error": None,
            }
        if self._load_error is not None:
            return {
                "status": "error",
                "label": "Error",
                "model": self.model_name,
                "loaded": False,
                "error": self._load_error,
            }
        return {
            "status": "standby",
            "label": "Lazy Standby",
            "model": self.model_name,
            "loaded": False,
            "error": None,
        }

    def _load(self):
        if self._model is None:
            try:
                from FlagEmbedding import FlagReranker
                self._model = FlagReranker(self.model_name, use_fp16=False)
                self._load_error = None
            except Exception as exc:
                self._load_error = f"{type(exc).__name__}: {exc}"
                raise
        return self._model

    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        if not candidates:
            return []
        model = self._load()
        pairs = [[query, candidate["text"]] for candidate in candidates]
        scores = model.compute_score(pairs, normalize=True)
        if not isinstance(scores, list):
            scores = [float(scores)]
        return _rank(candidates, scores, top_k)
