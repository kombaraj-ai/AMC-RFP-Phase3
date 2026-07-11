"""Unit tests for `data.dynamodb_store`, mocked boto3 - no real AWS.

Mirrors `test_sqlite_store.py`'s intent (seed behavior, lookup behavior) but
also covers the two things unique to a DynamoDB-backed implementation:
insert-if-missing via a ConditionExpression (not a SELECT-then-INSERT check),
and Decimal -> float conversion so `tools/quant_tools.py`'s `json.dumps(row)`
keeps working unchanged.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from amc_orchestrator.data import dynamodb_store


def _fake_table() -> MagicMock:
    return MagicMock()


def test_ensure_seeded_puts_all_mock_funds_when_table_empty() -> None:
    table = _fake_table()
    with patch("amc_orchestrator.data.dynamodb_store._table", return_value=table):
        dynamodb_store.ensure_seeded("test-table")

    assert table.put_item.call_count == 4
    tickers = {call.kwargs["Item"]["ticker"] for call in table.put_item.call_args_list}
    assert tickers == {"EQG1", "SMC3", "INC2", "BLN4"}


def test_ensure_seeded_skips_items_already_present() -> None:
    table = _fake_table()
    table.put_item.side_effect = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem"
    )

    with patch("amc_orchestrator.data.dynamodb_store._table", return_value=table):
        dynamodb_store.ensure_seeded("test-table")  # must not raise

    assert table.put_item.call_count == 4


def test_ensure_seeded_reraises_unexpected_client_errors() -> None:
    table = _fake_table()
    table.put_item.side_effect = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException"}}, "PutItem"
    )

    with patch("amc_orchestrator.data.dynamodb_store._table", return_value=table), pytest.raises(
        ClientError
    ):
        dynamodb_store.ensure_seeded("test-table")


def test_fetch_fund_performance_converts_decimal_to_float() -> None:
    table = _fake_table()
    table.get_item.return_value = {
        "Item": {
            "ticker": "SMC3",
            "fund_name": "Alpha Prime Smallcap Direct Fund",
            "nav": Decimal("88.40"),
            "standard_deviation": Decimal("22.80"),
        }
    }

    with patch("amc_orchestrator.data.dynamodb_store._table", return_value=table):
        row = dynamodb_store.fetch_fund_performance("test-table", "smc3")

    assert row is not None
    assert row["ticker"] == "SMC3"
    assert isinstance(row["nav"], float)
    assert row["nav"] == 88.40
    table.get_item.assert_called_once_with(Key={"ticker": "SMC3"})


def test_fetch_fund_performance_returns_none_when_missing() -> None:
    table = _fake_table()
    table.get_item.return_value = {}

    with patch("amc_orchestrator.data.dynamodb_store._table", return_value=table):
        assert dynamodb_store.fetch_fund_performance("test-table", "ZZZZ") is None
