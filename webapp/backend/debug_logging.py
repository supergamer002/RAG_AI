"""Debug logging indipendente dalla configurazione di Uvicorn.

Il file viene scritto direttamente dal processo applicativo. Questo evita che
Uvicorn/reload possa rimuovere o riconfigurare un handler e lasciare il log vuoto.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import threading
import traceback
from importlib import metadata
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEBUG_LOG_PATH = PROJECT_ROOT / "log_debug.log"
_MAX_LOG_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 3
_WRITE_LOCK = threading.Lock()

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
    """Debug applicativo attivo solo quando RAG_DEBUG è esplicitamente true."""
    return os.getenv("RAG_DEBUG", "").strip().lower() in _TRUTHY


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
        if key in _ENV_EXACT or any(key.startswith(prefix) for prefix in _ENV_PREFIXES):
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
        safe_query = {
            str(key): _redact(key, value)
            for key, value in request.query_params.multi_items()
        }
        safe_headers = {}
        for key in (
            "content-type",
            "content-length",
            "user-agent",
            "origin",
            "referer",
        ):
            value = request.headers.get(key)
            if value is not None:
                safe_headers[key] = _redact(key, value)
        return {
            "method": request.method,
            "path": request.url.path,
            "query": safe_query,
            "headers": safe_headers,
            "client": request.client.host if request.client else None,
        }
    except Exception as exc:
        return {"snapshotError": f"{type(exc).__name__}: {exc}"}


def _sanitize_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    return {str(key): _redact(str(key), item) for key, item in value.items()}


def _rotate_if_needed() -> None:
    try:
        if not DEBUG_LOG_PATH.exists() or DEBUG_LOG_PATH.stat().st_size < _MAX_LOG_BYTES:
            return

        oldest = DEBUG_LOG_PATH.with_name(f"{DEBUG_LOG_PATH.name}.{_BACKUP_COUNT}")
        oldest.unlink(missing_ok=True)

        for index in range(_BACKUP_COUNT - 1, 0, -1):
            src = DEBUG_LOG_PATH.with_name(f"{DEBUG_LOG_PATH.name}.{index}")
            dst = DEBUG_LOG_PATH.with_name(f"{DEBUG_LOG_PATH.name}.{index + 1}")
            if src.exists():
                src.replace(dst)

        DEBUG_LOG_PATH.replace(DEBUG_LOG_PATH.with_name(f"{DEBUG_LOG_PATH.name}.1"))
    except Exception:
        # La rotazione non deve impedire la scrittura del nuovo evento.
        pass


def _write_event(payload: dict[str, Any]) -> None:
    """Scrive direttamente sul file: non dipende dagli handler di logging."""
    if not debug_enabled():
        return

    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = (
            "\n" + "=" * 100 + "\n"
            + json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            + "\n"
        )
        with _WRITE_LOCK:
            _rotate_if_needed()
            with DEBUG_LOG_PATH.open("a", encoding="utf-8", errors="replace") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
    except Exception:
        # Il debug logger è sempre fail-open.
        pass


def configure_debug_logging() -> bool:
    """Crea subito il file e registra un marker di avvio del processo."""
    if not debug_enabled():
        return False

    _write_event(
        {
            "event": "debug_startup",
            "message": "Debug logging attivo",
            "runtime": _runtime_snapshot(),
        }
    )
    return True


def debug_message(
    message: str,
    *,
    extra: Mapping[str, Any] | None = None,
) -> None:
    if not debug_enabled():
        return
    _write_event(
        {
            "event": "debug",
            "message": message,
            "extra": _sanitize_mapping(extra),
            "runtime": _runtime_snapshot(),
        }
    )


def debug_exception(
    message: str,
    exc: BaseException,
    *,
    request: Any | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    """Registra sempre traceback completo + contesto runtime redatto."""
    if not debug_enabled():
        return

    payload = {
        "event": "exception",
        "message": message,
        "exceptionType": type(exc).__name__,
        "exceptionMessage": str(exc),
        "traceback": "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ),
        "request": _request_snapshot(request),
        "extra": _sanitize_mapping(extra),
        "runtime": _runtime_snapshot(),
    }
    _write_event(payload)
