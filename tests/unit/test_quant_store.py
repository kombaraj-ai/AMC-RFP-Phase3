"""Unit tests for `data.quant_store`'s dispatch logic only.

Not re-testing sqlite_store/dynamodb_store's own behavior (covered in their
own test modules) - just that `effective_data_backend` picks the right one.
"""

from __future__ import annotations

from unittest.mock import patch

from amc_orchestrator.config.settings import Settings
from amc_orchestrator.data import quant_store


def test_local_backend_dispatches_to_sqlite_store() -> None:
    settings = Settings(environment="dev", data_backend="local")

    with patch(
        "amc_orchestrator.data.quant_store.sqlite_store.fetch_fund_performance",
        return_value={"ticker": "EQG1"},
    ) as mocked:
        row = quant_store.fetch_fund_performance(settings, "EQG1")

    mocked.assert_called_once_with(settings.sqlite_full_path, "EQG1")
    assert row == {"ticker": "EQG1"}


def test_aws_backend_dispatches_to_dynamodb_store() -> None:
    settings = Settings(environment="dev", data_backend="aws", dynamodb_table_name="tbl")

    with patch(
        "amc_orchestrator.data.quant_store.dynamodb_store.fetch_fund_performance",
        return_value={"ticker": "EQG1"},
    ) as mocked:
        row = quant_store.fetch_fund_performance(settings, "EQG1")

    mocked.assert_called_once_with("tbl", "EQG1")
    assert row == {"ticker": "EQG1"}


def test_staging_always_dispatches_to_dynamodb_store_regardless_of_data_backend() -> None:
    settings = Settings(environment="staging", data_backend="local", dynamodb_table_name="tbl")

    with patch(
        "amc_orchestrator.data.quant_store.dynamodb_store.fetch_fund_performance",
        return_value=None,
    ) as mocked:
        quant_store.fetch_fund_performance(settings, "EQG1")

    mocked.assert_called_once()


def test_ensure_seeded_dispatches_by_backend() -> None:
    local_settings = Settings(environment="dev", data_backend="local")
    aws_settings = Settings(environment="dev", data_backend="aws", dynamodb_table_name="tbl")

    with patch("amc_orchestrator.data.quant_store.sqlite_store.ensure_seeded") as local_mock:
        quant_store.ensure_seeded(local_settings)
    local_mock.assert_called_once_with(local_settings.sqlite_full_path)

    with patch("amc_orchestrator.data.quant_store.dynamodb_store.ensure_seeded") as aws_mock:
        quant_store.ensure_seeded(aws_settings)
    aws_mock.assert_called_once_with("tbl")
