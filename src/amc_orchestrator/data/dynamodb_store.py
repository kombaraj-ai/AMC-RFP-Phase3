"""Quantitative fund performance data store (DynamoDB, STAGING/PROD or DEV opt-in).

Plain boto3 + dicts, no Strands dependency - mirrors `sqlite_store.py`'s shape so
`data/quant_store.py` can dispatch between the two without either caller-facing
function changing shape. Reuses `sqlite_store`'s mock fund data as the seed set so
DEV/staging/prod agree on what "the 4 mock funds" means without duplicating it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

from amc_orchestrator.data.sqlite_store import _COLUMNS, _MOCK_FUNDS


def _table(table_name: str):
    return boto3.resource("dynamodb").Table(table_name)


def ensure_seeded(table_name: str) -> None:
    """Insert any mock funds not yet present. Insert-if-missing, not overwrite -
    a `ConditionExpression` guards each `put_item` so real, since-modified data
    in the table is never clobbered by a re-seed."""
    table = _table(table_name)
    for row in _MOCK_FUNDS:
        # boto3's high-level Table resource rejects native Python `float` for
        # DynamoDB numeric attributes (`TypeError: Float types are not
        # supported. Use Decimal types instead.`) - `_MOCK_FUNDS` reuses
        # sqlite_store's plain-float literals, so convert here rather than
        # duplicate the mock data with Decimal literals.
        item = {
            key: Decimal(str(value)) if isinstance(value, float) else value
            for key, value in zip(_COLUMNS, row, strict=True)
        }
        try:
            table.put_item(Item=item, ConditionExpression="attribute_not_exists(ticker)")
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise


def fetch_fund_performance(table_name: str, ticker: str) -> dict[str, Any] | None:
    """Return the performance metrics for `ticker`, or None if not found.

    boto3's `Table` resource deserializes DynamoDB numbers as `Decimal`, which
    `json.dumps` (used by `tools/quant_tools.py`) can't serialize - converted to
    `float` here so callers see the exact same flat dict shape `sqlite_store`
    returns.
    """
    table = _table(table_name)
    response = table.get_item(Key={"ticker": ticker.strip().upper()})
    item = response.get("Item")
    if item is None:
        return None
    return {key: float(value) if isinstance(value, Decimal) else value for key, value in item.items()}
