"""Lazy Cross-Encoder reranker without SciPy/FlagEmbedding.

Uses Hugging Face Transformers + PyTorch directly with
BAAI/bge-reranker-v2-m3. The model is loaded only on first use.
"""

from __future__ import annotations

import math

MODEL_NAME = "BAAI/bge-reranker-v2-m3"
DEFAULT_CANDIDATES = 20


def _rank(candidates: list[dict], scores, top_k: int) -> list[dict]:
    scores = list(scores)
    if len(candidates) != len(scores):
        raise ValueError("Numero di candidati e punteggi non coincide.")
    ranked = []
    for candidate, score in zip(candidates, scores):
        value = float(score)
        item = dict(candidate)
        item["rerank_score"] = round(value, 4)
        ranked.append((item, value))
    ranked.sort(key=lambda pair: pair[1], reverse=True)
    return [item for item, _ in ranked[:top_k]]


class CrossEncoderReranker:
    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self.model_name = model_name
        self._tokenizer = None
        self._model = None
        self._torch = None
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
                import torch
                from transformers import AutoModelForSequenceClassification, AutoTokenizer

                self._torch = torch
                self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
                self._model.eval()
                self._model.to("cpu")
                self._load_error = None
            except Exception as exc:
                self._load_error = f"{type(exc).__name__}: {exc}"
                raise
        return self._model

    def rerank(self, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        if not candidates:
            return []

        model = self._load()
        tokenizer = self._tokenizer
        torch = self._torch
        pairs = [(query, candidate["text"]) for candidate in candidates]

        encoded = tokenizer(
            [q for q, _ in pairs],
            [text for _, text in pairs],
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )

        with torch.no_grad():
            logits = model(**encoded).logits

        raw = logits.reshape(-1).detach().cpu().tolist()
        # BGE reranker emits one relevance logit per pair. Sigmoid gives
        # a stable [0, 1] score comparable to the previous normalized API.
        scores = [1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, float(x))))) for x in raw]
        return _rank(candidates, scores, top_k)
