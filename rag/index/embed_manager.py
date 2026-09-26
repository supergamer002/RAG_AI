from __future__ import annotations
from typing import Dict
from rag.index.embed import OllamaEmbedder

class EmbedderManager:
    def __init__(self):
        self._cache: Dict[str, OllamaEmbedder] = {}

    def get_embedder(self, model_name: str, url: str) -> OllamaEmbedder:
        cache_key = f"{url}:{model_name}"
        if cache_key not in self._cache:
            self._cache[cache_key] = OllamaEmbedder(url=url, modello=model_name)
        return self._cache[cache_key]

# Global instance
embedder_manager = EmbedderManager()
