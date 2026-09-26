"""Generazione della risposta finale: costruisce il prompt dai chunk
rerankati e chiama qwen3:8b via Ollama.

Policy esplicita, coerente con quella gia' adottata per gli Impiegati nel
progetto principale: se il contesto recuperato non basta a rispondere, il
modello deve dichiararlo invece di allucinare. Ogni affermazione va
ancorata a una fonte citata (titolo + sezione/posizione), non generata a
memoria.
"""

from __future__ import annotations

import requests
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag.common.monitoring import TracciatoreLatenza

OLLAMA_URL = "http://localhost:11434/api/chat"
MODELLO_GENERAZIONE = "qwen3:8b"

SYSTEM_PROMPT = """Sei un assistente che risponde SOLO in base al contesto fornito qui sotto, estratto da libri e articoli scientifici.

Regole:
1. Se il contesto non contiene l'informazione richiesta, dichiaralo esplicitamente ("Il materiale a disposizione non copre questo punto") invece di rispondere a memoria.
2. Ogni affermazione tecnica deve essere riconducibile a un passaggio del contesto: cita la fonte tra parentesi nel formato (Fonte, Sezione) dopo l'affermazione che supporta.
3. Non mescolare informazioni da fonti diverse in un'unica affermazione senza distinguerle.
4. Rispondi in italiano, in modo tecnico e diretto, senza preamboli."""


def _formatta_contesto(chunk: list[dict]) -> str:
    """Un blocco per chunk, con l'etichetta fonte da riusare nella citazione."""
    blocchi = []
    for c in chunk:
        etichetta = c["fonte_titolo"]
        if c.get("sezione"):
            etichetta += f", {c['sezione']}"
        if c.get("posizione"):
            etichetta += f" ({c['posizione']})"
        blocchi.append(f"[Fonte: {etichetta}]\n{c['testo']}")
    return "\n\n".join(blocchi)


def costruisci_messaggi(query: str, chunk: list[dict]) -> list[dict]:
    """Costruisce i messaggi chat (system/user) pronti per Ollama.

    Isolata dalla chiamata di rete per essere testabile senza Ollama
    in esecuzione.
    """
    contesto = _formatta_contesto(chunk)
    messaggio_utente = f"Contesto:\n\n{contesto}\n\nDomanda: {query}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": messaggio_utente},
    ]


class OllamaGenerator:
    """Wrapper minimale sull'endpoint /api/chat di Ollama."""

    def __init__(
        self,
        modello: str = MODELLO_GENERAZIONE,
        url: str = OLLAMA_URL,
        timeout: int = 180,
    ) -> None:
        self.modello = modello
        self.url = url
        self.timeout = timeout

    def genera(self, messaggi: list[dict]) -> str:
        payload = {"model": self.modello, "messages": messaggi, "stream": False}
        try:
            risposta = requests.post(self.url, json=payload, timeout=self.timeout)
            risposta.raise_for_status()
        except requests.RequestException as exc:
            base = self.url.rsplit("/api/chat", 1)[0]
            raise RuntimeError(
                f"Ollama generazione non raggiungibile o modello '{self.modello}' non disponibile "
                f"({base}). Dettaglio: {exc}"
            ) from exc
        try:
            corpo = risposta.json()
        except ValueError as exc:
            raise RuntimeError(f"Ollama generazione ha restituito una risposta non JSON: {risposta.text[:300]}") from exc

        messaggio = corpo.get("message", {}).get("content")
        if not messaggio:
            raise ValueError(f"Risposta Ollama senza contenuto: {corpo}")
        return messaggio


def rispondi(
    query: str,
    chunk_rerankati: list[dict],
    generatore: OllamaGenerator | None = None,
    tracciatore: TracciatoreLatenza | None = None,
) -> str:
    """Punto di ingresso: chunk gia' passati da hybrid_search + rerank,
    query utente in ingresso, risposta finale in uscita.
    """
    if not chunk_rerankati:
        return "Il materiale a disposizione non copre questo punto: nessun passaggio pertinente trovato."

    generatore = generatore or OllamaGenerator()
    messaggi = costruisci_messaggi(query, chunk_rerankati)

    if tracciatore:
        with tracciatore.misura("generation"):
            return generatore.genera(messaggi)
    return generatore.genera(messaggi)


if __name__ == "__main__":
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    # 1) Test puro della costruzione del prompt, senza rete.
    chunk_prova = [
        {
            "fonte_titolo": "Chimica Generale",
            "sezione": "Cap. 2 - Legame chimico",
            "posizione": "p. 30",
            "testo": "Il legame ionico nasce da trasferimento di elettroni tra atomi.",
        }
    ]
    messaggi = costruisci_messaggi("Cos'e' il legame ionico?", chunk_prova)
    assert messaggi[0]["role"] == "system"
    assert "Chimica Generale, Cap. 2 - Legame chimico (p. 30)" in messaggi[1]["content"]
    assert "Cos'e' il legame ionico?" in messaggi[1]["content"]
    print("OK — costruzione prompt verificata (system prompt, citazione fonte, query incluse)")

    # 2) Test del client contro un mock Ollama: verifica solo il contratto
    # richiesta/risposta, non la qualita' reale della generazione — richiede
    # Ollama in esecuzione con qwen3:8b per un test end-to-end vero.
    class MockOllamaHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            lunghezza = int(self.headers["Content-Length"])
            corpo = json.loads(self.rfile.read(lunghezza))
            assert corpo["model"] == MODELLO_GENERAZIONE
            assert corpo["stream"] is False
            risposta = json.dumps(
                {"message": {"role": "assistant", "content": "Risposta di prova dal mock."}}
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(risposta)

    server = HTTPServer(("localhost", 11498), MockOllamaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    generatore = OllamaGenerator(url="http://localhost:11498/api/chat")
    esito = rispondi("Cos'e' il legame ionico?", chunk_prova, generatore)
    assert esito == "Risposta di prova dal mock."
    print(f"OK — client Ollama verificato, risposta ricevuta: {esito!r}")

    # 3) Caso senza chunk: nessuna chiamata di rete, risposta di fallback.
    esito_vuoto = rispondi("Domanda senza contesto disponibile", [])
    assert "non copre questo punto" in esito_vuoto
    print("OK — fallback senza chunk verificato (nessuna chiamata di rete)")

    server.shutdown()
