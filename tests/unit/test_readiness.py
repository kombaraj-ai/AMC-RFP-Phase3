"""Unit tests for observability/readiness.py - no real Ollama or network needed."""

from __future__ import annotations

import socket
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from amc_orchestrator.config.settings import Settings
from amc_orchestrator.observability.readiness import check_readiness, ollama_reachable


def test_ollama_reachable_true_when_socket_connects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "create_connection", lambda addr, timeout: MagicMock())
    assert ollama_reachable("http://localhost:11434") is True


def test_ollama_reachable_false_when_connection_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(addr: tuple[str, int], timeout: float) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(socket, "create_connection", _raise)
    assert ollama_reachable("http://localhost:11434") is False


def test_check_readiness_dev_includes_ollama_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(socket, "create_connection", lambda addr, timeout: MagicMock())
    settings = Settings(
        environment="dev",
        sqlite_path=str(tmp_path / "sub" / "local.db"),
        chroma_persist_dir=str(tmp_path / "chroma"),
    )

    report = check_readiness(settings)

    assert report.checks["ollama_reachable"] is True
    assert report.checks["sqlite_dir_writable"] is True
    assert report.checks["chroma_dir_writable"] is True
    assert report.ready is True


def test_check_readiness_not_ready_when_ollama_unreachable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def _raise(addr: tuple[str, int], timeout: float) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(socket, "create_connection", _raise)
    settings = Settings(
        environment="dev",
        sqlite_path=str(tmp_path / "local.db"),
        chroma_persist_dir=str(tmp_path / "chroma"),
    )

    report = check_readiness(settings)

    assert report.checks["ollama_reachable"] is False
    assert report.ready is False


def test_check_readiness_staging_skips_ollama_check(tmp_path: Path) -> None:
    settings = Settings(
        environment="staging",
        sqlite_path=str(tmp_path / "local.db"),
        chroma_persist_dir=str(tmp_path / "chroma"),
    )

    report = check_readiness(settings)

    assert "ollama_reachable" not in report.checks
    assert report.ready is True


def test_check_readiness_dev_with_bedrock_provider_skips_ollama_check(tmp_path: Path) -> None:
    settings = Settings(
        environment="dev",
        model_provider="bedrock",
        sqlite_path=str(tmp_path / "local.db"),
        chroma_persist_dir=str(tmp_path / "chroma"),
    )

    report = check_readiness(settings)

    assert "ollama_reachable" not in report.checks
    assert report.ready is True
