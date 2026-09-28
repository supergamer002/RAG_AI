"""Debug logging robusto per il backend RAG.

Quando il debug è attivo, registra gli errori con traceback completo e un
snapshot selettivo dell'ambiente/runtime nel file log_debug.log alla radice
del progetto. I valori sensibili vengono sempre redatti.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import sys
from importlib import metadata
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEBUG_LOG_PATH = PROJECT_ROOT / "log_debug.log"

_TRUTHY = {"1", "true", "yes", "on", "debug"}
_SENSITIVE_PARTS = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "private_key",
)
_ENV_EXACT = {
    "PATH",
    "PYTHONPATH",
    "PYTHONHOME",
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "CONDA_DEFAULT_ENV",
    "LD_LIBRARY_PATH",
    "LIBRARY_PATH",
    "LANG",
    "LC_ALL",
    "HOME",
    "USER",
    "SHELL",
    "WSL_DISTRO_NAME",
    "WSL_INTEROP",
    "WSLENV",
    "WSL2_GUI_APPS_ENABLED",
    "CUDA_VISIBLE_DEVICES",
    "OMP_NUM_THREADS",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
}
_ENV_PREFIXES = (
    "RAG_",
    "UVICORN_",
    "OLLAMA_",
    "PYTHON",
    "PIP_",
    "VIRTUAL_ENV",
    "CONDA_",
    "WSL_",
    "CUDA_",
    "TORCH_",
    "HF_",
)


def debug_enabled() -> bool:
    """True quando il debug applicativo è richiesto esplicitamente o da Uvicorn."""
    raw = os.getenv("RAG_DEBUG", "").strip().lower()
    if raw in _TRUTHY:
        return True
    # Uvicorn configura normalmente i propri logger prima di importare l'app.
    # Questo permette di attivare il file anche con log-level debug.
    try:
        return logging.getLogger("uvicorn.error").isEnabledFor(logging.DEBUG)
    except Exception:
        return False


def configure_debug_logging() -> bool:
    """Configura una sola volta un handler rotante sul root logger."""
    if not debug_enabled():
        return False

    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        for handler in root.handlers:
            if getattr(handler, "_rag_debug_file_handler", False):
                return True

        handler = RotatingFileHandler(
            DEBUG_LOG_PATH,
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler._rag_debug_file_handler = True  # type: ignore[attr-defined]
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                "%Y-%m-%d %H:%M:%S",
            )
        )
        root.addHandler(handler)

        logging.getLogger("rag.debug").info(
            "Debug logging attivo; file=%s",
            DEBUG_LOG_PATH,
        )
        return True
    except Exception:
        # Il logging di debug non deve mai impedire l'avvio dell'app.
        return False


def _redact(key: str, value: Any) -> Any:
    key_l = str(key).lower()
    if key_l in {"http_proxy", "https_proxy", "all_proxy"}:
        return "<REDACTED_PROXY>"
    if any(part in key_l for part in _SENSITIVE_PARTS):
        return "<REDACTED>"
    if value is None:
        return None
    text = str(value)
    if len(text) > 4096:
        return text[:4096] + "...<truncated>"
    return value


def _environment_snapshot() -> dict[str, Any]:
    env: dict[str, Any] = {}
    for key, value in sorted(os.environ.items()):
        if (
            key in _ENV_EXACT
            or any(key.startswith(prefix) for prefix in _ENV_PREFIXES)
        ):
            env[key] = _redact(key, value)
    return env


def _installed_versions() -> dict[str, str]:
    packages = (
        "fastapi",
        "uvicorn",
        "pydantic",
        "requests",
        "lancedb",
        "pyarrow",
        "numpy",
        "scikit-learn",
        "docling",
        "torch",
    )
    result: dict[str, str] = {}
    for package in packages:
        try:
            result[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            result[package] = "<not-installed>"
        except Exception as exc:
            result[package] = f"<version-error:{type(exc).__name__}>"
    return result


def _runtime_snapshot() -> dict[str, Any]:
    return {
        "projectRoot": str(PROJECT_ROOT),
        "debugLogPath": str(DEBUG_LOG_PATH),
        "cwd": os.getcwd(),
        "pythonExecutable": sys.executable,
        "pythonVersion": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "implementation": platform.python_implementation(),
        "sysPath": list(sys.path),
        "packages": _installed_versions(),
        "environment": _environment_snapshot(),
    }


def _request_snapshot(request: Any | None) -> dict[str, Any] | None:
    if request is None:
        return None

    try:
        query_params = {
            str(key): _redact(key, value)
            for key, value in request.query_params.multi_items()
        }
        safe_headers = {}
        for key in ("content-type", "content-length", "user-agent", "origin", "referer"):
            value = request.headers.get(key)
            if value is not None:
                safe_headers[key] = _redact(key, value)

        client = request.client
        return {
            "method": request.method,
            "path": request.url.path,
            "query": query_params,
            "headers": safe_headers,
            "client": client.host if client else None,
        }
    except Exception as exc:
        return {"snapshotError": f"{type(exc).__name__}: {exc}"}


def _sanitize_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    return {str(key): _redact(str(key), item) for key, item in value.items()}


def debug_message(
    message: str,
    *,
    extra: Mapping[str, Any] | None = None,
) -> None:
    """Scrive un evento diagnostico senza richiedere un'eccezione."""
    if not configure_debug_logging():
        return
    payload = {
        "event": "debug",
        "message": message,
        "extra": _sanitize_mapping(extra),
        "runtime": _runtime_snapshot(),
    }
    logging.getLogger("rag.debug").debug(
        "DEBUG_EVENT\n%s",
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
    )


def debug_exception(
    message: str,
    exc: BaseException,
    *,
    request: Any | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    """Scrive traceback completo + request/runtime/env in modo redatto."""
    if not configure_debug_logging():
        return

    payload = {
        "event": "exception",
        "message": message,
        "exception": {
            "type": type(exc).__name__,
            "message": str(exc),
        },
        "request": _request_snapshot(request),
        "extra": _sanitize_mapping(extra),
        "runtime": _runtime_snapshot(),
    }

    logging.getLogger("rag.debug").error(
        "DEBUG_EXCEPTION\n%s",
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        exc_info=(type(exc), exc, exc.__traceback__),
    )
