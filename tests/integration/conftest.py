"""Fixtures shared by integration tests, which exercise the real graph against
a locally running Ollama server (no mocking of the LLM)."""

from __future__ import annotations

from pathlib import Path

import pytest

from amc_orchestrator.config.settings import Settings, get_settings
from amc_orchestrator.data import chroma_store, sqlite_store
from amc_orchestrator.observability.readiness import ollama_reachable


@pytest.fixture(autouse=True)
def _skip_integration_if_ollama_unreachable(request: pytest.FixtureRequest) -> None:
    if "integration" not in {marker.name for marker in request.node.iter_markers()}:
        return
    settings = get_settings()
    if not ollama_reachable(settings.ollama_host):
        pytest.skip(f"Ollama not reachable at {settings.ollama_host}; skipping integration test.")


def _build_isolated_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **extra_env: str
) -> Settings:
    """Point the process-wide cached Settings at tmp_path-scoped data stores.

    `get_settings()` is an `lru_cache`-d singleton read by both `graph_build`
    (via the `settings` object passed to agent constructors) and the
    `@tool`-wrapped data functions (which call `get_settings()` independently).
    To keep both in agreement without touching real DEV data, we monkeypatch
    the environment variables `get_settings()` reads and clear its cache,
    rather than constructing a second, disconnected `Settings` instance.
    """
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "integration_test.db"))
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("CHROMA_COLLECTION_NAME", "integration_test_commentary")
    for key, value in extra_env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()

    settings = get_settings()
    sqlite_store.ensure_seeded(settings.sqlite_full_path)
    chroma_store.ensure_seeded(settings.chroma_full_path, settings.chroma_collection_name)
    return settings


@pytest.fixture
def isolated_graph_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    settings = _build_isolated_settings(monkeypatch, tmp_path)
    yield settings
    get_settings.cache_clear()


@pytest.fixture
def isolated_graph_settings_single_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Settings:
    """Same as `isolated_graph_settings`, but with `MAX_COMPLIANCE_ATTEMPTS` forced
    to 1 - for the M10 forced-escalation hardening test."""
    settings = _build_isolated_settings(monkeypatch, tmp_path, MAX_COMPLIANCE_ATTEMPTS="1")
    yield settings
    get_settings.cache_clear()
