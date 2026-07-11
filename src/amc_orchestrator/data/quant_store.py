"""Facade dispatching quant-data calls to SQLite (local) or DynamoDB (aws).

Mirrors `config.model_factory.get_model`'s pattern: this is the only place that
chooses between the two concrete stores, so `tools/quant_tools.py` and `cli.py`/
`api/main.py`'s seeding never branch on `effective_data_backend` themselves.
"""

from __future__ import annotations

from typing import Any

from amc_orchestrator.config.settings import Settings
from amc_orchestrator.data import dynamodb_store, sqlite_store


def ensure_seeded(settings: Settings) -> None:
    if settings.effective_data_backend == "local":
        sqlite_store.ensure_seeded(settings.sqlite_full_path)
    else:
        dynamodb_store.ensure_seeded(settings.dynamodb_table_name)


def fetch_fund_performance(settings: Settings, ticker: str) -> dict[str, Any] | None:
    if settings.effective_data_backend == "local":
        return sqlite_store.fetch_fund_performance(settings.sqlite_full_path, ticker)
    return dynamodb_store.fetch_fund_performance(settings.dynamodb_table_name, ticker)
