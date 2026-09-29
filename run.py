"""Avvia RAG AI e apre il browser: python run.py"""
import os
import threading
import time
import webbrowser

import uvicorn

PORT = int(os.environ.get("RAG_PORT", "8000"))


def _open_browser() -> None:
    time.sleep(2)
    webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, log_level="info")
