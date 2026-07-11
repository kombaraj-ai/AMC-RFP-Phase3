"""Strands tool wrappers around the quantitative data layer.

Kept intentionally thin - all real logic lives in `data.sqlite_store`/
`data.dynamodb_store` (dispatched via `data.quant_store`) and is unit-tested
there without any Strands/LLM dependency.
"""

from __future__ import annotations

import json

from strands import tool

from amc_orchestrator.config.settings import get_settings
from amc_orchestrator.data import quant_store


@tool
def get_fund_performance(ticker: str) -> str:
    """Retrieve quantitative performance metrics for a mutual fund by ticker.

    Returns NAV, Alpha, Beta, Sharpe Ratio, Standard Deviation, Sortino Ratio,
    R-Squared, and 1-year/3-year trailing returns as a JSON object. Use this
    tool whenever a question requires exact numerical fund data - never
    estimate or recall these figures from memory.

    Args:
        ticker: The fund ticker symbol, e.g. "SMC3".
    """
    settings = get_settings()
    row = quant_store.fetch_fund_performance(settings, ticker)
    if row is None:
        return json.dumps({"error": f"No performance data found for ticker '{ticker}'."})
    return json.dumps(row)
