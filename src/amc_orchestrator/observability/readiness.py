"""Operational readiness checks - can this process serve a request right now.

Distinct from liveness (`GET /health`, "is the process alive"): readiness
answers "can it currently reach the dependencies it needs" - Ollama, when it's
the effective model provider, and the SQLite/Chroma data directories always -
so an orchestrator can route traffic away from an instance whose LLM backend
is unreachable instead of letting it return graph-invocation failures to
clients.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from amc_orchestrator.config.settings import Settings


def ollama_reachable(host: str, timeout: float = 1.0) -> bool:
    """Check whether an Ollama server is accepting TCP connections at `host`."""
    parsed = urlparse(host)
    hostname = parsed.hostname or "localhost"
    port = parsed.port or 11434
    try:
        with socket.create_connection((hostname, port), timeout=timeout):
            return True
    except OSError:
        return False


def _directory_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    checks: dict[str, bool]


def check_readiness(settings: Settings) -> ReadinessReport:
    """Run all readiness checks relevant to `settings.effective_model_provider`."""
    checks: dict[str, bool] = {}

    if settings.effective_model_provider == "ollama":
        checks["ollama_reachable"] = ollama_reachable(settings.ollama_host)

    checks["sqlite_dir_writable"] = _directory_writable(settings.sqlite_full_path.parent)
    checks["chroma_dir_writable"] = _directory_writable(settings.chroma_full_path)

    return ReadinessReport(ready=all(checks.values()), checks=checks)
