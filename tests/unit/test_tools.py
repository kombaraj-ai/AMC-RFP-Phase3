"""Unit tests for the thin @tool wrappers.

Settings are monkeypatched to point at tmp_path-scoped data stores so these
tests never touch (or depend on) the developer's real local_dev.db / data/chroma.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amc_orchestrator.config.settings import Settings
from amc_orchestrator.data import chroma_store, sqlite_store


@pytest.fixture
def isolated_settings(
    monkeypatch: pytest.MonkeyPatch, sqlite_db_path: Path, chroma_dir: Path
) -> Settings:
    settings = Settings(
        sqlite_path=str(sqlite_db_path),
        chroma_persist_dir=str(chroma_dir),
        chroma_collection_name="test_fund_manager_commentary",
    )
    sqlite_store.ensure_seeded(settings.sqlite_full_path)
    chroma_store.ensure_seeded(settings.chroma_full_path, settings.chroma_collection_name)

    # Both tool modules import get_settings directly into their namespace,
    # so patch it at each call site rather than at the source module.
    monkeypatch.setattr("amc_orchestrator.tools.quant_tools.get_settings", lambda: settings)
    monkeypatch.setattr("amc_orchestrator.tools.qual_tools.get_settings", lambda: settings)
    return settings


def test_get_fund_performance_returns_json_metrics(isolated_settings: Settings) -> None:
    from amc_orchestrator.tools.quant_tools import get_fund_performance

    payload = json.loads(get_fund_performance("SMC3"))
    assert payload["ticker"] == "SMC3"
    assert payload["standard_deviation"] == 22.80


def test_get_fund_performance_unknown_ticker_returns_error_payload(isolated_settings: Settings) -> None:
    from amc_orchestrator.tools.quant_tools import get_fund_performance

    payload = json.loads(get_fund_performance("ZZZZ"))
    assert "error" in payload


def test_search_fund_commentary_returns_relevant_text(isolated_settings: Settings) -> None:
    from amc_orchestrator.tools.qual_tools import search_fund_commentary

    result = search_fund_commentary("smallcap volatility and downside risk")
    assert "SMC3" in result


def test_search_fund_commentary_handles_no_match_gracefully(
    monkeypatch: pytest.MonkeyPatch, sqlite_db_path: Path, chroma_dir: Path
) -> None:
    empty_settings = Settings(
        chroma_persist_dir=str(chroma_dir), chroma_collection_name="never_seeded_collection"
    )
    monkeypatch.setattr("amc_orchestrator.tools.qual_tools.get_settings", lambda: empty_settings)

    from amc_orchestrator.tools.qual_tools import search_fund_commentary

    result = search_fund_commentary("anything")
    assert "No relevant" in result
