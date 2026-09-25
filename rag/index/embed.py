"""Client per generare embedding via Ollama (qwen3-embedding:0.6b).

Isolato in un client minimale (solo `requests`, nessun SDK Ollama) cosi'
il resto del pacchetto non acquisisce dipendenze pesanti per una singola
chiamata HTTP. Endpoint: POST /api/embed, che accetta un batch di stringhe
in un'unica chiamata (piu' efficiente di una richiesta per chunk).
"""

from __future__ import annotations

import requests
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag.common.monitoring import TracciatoreLatenza

OLLAMA_URL = "http://localhost:11434/api/embed"
MODELLO_EMBEDDING = "qwen3-embedding:0.6b"
DIMENSIONE_OUTPUT = 1024  # ridotta rispetto al default del modello, vedi planning
BATCH_SIZE = 32


class OllamaEmbedder:
    """Wrapper minimale sull'endpoint /api/embed di Ollama."""

    def __init__(
        self,
        modello: str = MODELLO_EMBEDDING,
        url: str = OLLAMA_URL,
        dimensione: int = DIMENSIONE_OUTPUT,
        batch_size: int = BATCH_SIZE,
        timeout: int = 120,
    ) -> None:
        self.modello = modello
        self.url = url
        self.dimensione = dimensione
        self.batch_size = batch_size
        self.timeout = timeout

    def _chiama_ollama(self, testi: list[str]) -> list[list[float]]:
        payload = {
            "model": self.modello,
            "input": testi,
            "dimensions": self.dimensione,
        }
        risposta = requests.post(self.url, json=payload, timeout=self.timeout)
        risposta.raise_for_status()
        corpo = risposta.json()

        embeddings = corpo.get("embeddings")
        if embeddings is None or len(embeddings) != len(testi):
            raise ValueError(
                f"Risposta Ollama inattesa: attesi {len(testi)} embedding, "
                f"ricevuti {len(embeddings) if embeddings is not None else 'nessuno'}"
            )
        return embeddings

    def embed(
        self, testi: list[str], tracciatore: TracciatoreLatenza | None = None
    ) -> list[list[float]]:
        """Genera un embedding per ogni testo, a batch di self.batch_size.

        L'ordine dei risultati corrisponde all'ordine di `testi`.
        """
        if not testi:
            return []

        def _esegui():
            risultati: list[list[float]] = []
            for inizio in range(0, len(testi), self.batch_size):
                batch = testi[inizio : inizio + self.batch_size]
                risultati.extend(self._chiama_ollama(batch))
            return risultati

        if tracciatore:
            with tracciatore.misura("embedding"):
                return _esegui()
        return _esegui()

    def embed_uno(self, testo: str) -> list[float]:
        """Comodo per l'embedding della query a runtime (un solo testo)."""
        return self.embed([testo])[0]


if __name__ == "__main__":
    # Smoke test contro un mock HTTP locale: verifica solo il contratto
    # richiesta/risposta (payload inviato, parsing della risposta, batching),
    # non la qualita' reale degli embedding — richiede Ollama in esecuzione
    # con qwen3-embedding:0.6b scaricato per un test end-to-end vero.
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class MockOllamaHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            lunghezza = int(self.headers["Content-Length"])
            corpo = json.loads(self.rfile.read(lunghezza))
            n = len(corpo["input"])
            dim = corpo["dimensions"]
            finti = [[0.1] * dim for _ in range(n)]
            risposta = json.dumps({"embeddings": finti}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(risposta)

    server = HTTPServer(("localhost", 11499), MockOllamaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    embedder = OllamaEmbedder(url="http://localhost:11499/api/embed", batch_size=2)
    out = embedder.embed(["frase uno", "frase due", "frase tre"])
    assert len(out) == 3, f"attesi 3 embedding, ottenuti {len(out)}"
    assert len(out[0]) == DIMENSIONE_OUTPUT, f"dimensione errata: {len(out[0])}"
    print(f"OK — {len(out)} embedding generati, dimensione {len(out[0])}, batching verificato (batch_size=2 su 3 testi)")

    server.shutdown()
