"""Quantitative Analyst Agent - pulls exact fund performance metrics."""

from __future__ import annotations

from strands import Agent

from amc_orchestrator.config.model_factory import get_model
from amc_orchestrator.config.settings import Settings
from amc_orchestrator.observability.hooks import LoggingHookProvider
from amc_orchestrator.tools.quant_tools import get_fund_performance

NODE_NAME = "quant_data_pull"

SYSTEM_PROMPT = """\
You are the Quantitative Analyst Agent for a Mutual Fund AMC.

Your job is to pull exact numerical performance metrics using the
`get_fund_performance` tool: NAV, Alpha, Beta, Sharpe Ratio, Standard
Deviation, Sortino Ratio, R-Squared, and 1-year/3-year trailing returns.

Rules:
- Identify every fund ticker mentioned or implied in the request and call the
  tool for each one.
- Report the values exactly as returned by the tool. Never estimate, round
  beyond what the tool returned, or recall figures from memory.
- If the tool reports no data for a ticker, state that plainly instead of
  guessing.
- Do not comment on compliance, strategy, or narrative - that is not your job.
"""


def get_quant_agent(settings: Settings) -> Agent:
    """Build the Quantitative Analyst Agent for the given environment settings."""
    model = get_model(settings, temperature=settings.model_temperature_worker)
    return Agent(
        model=model,
        tools=[get_fund_performance],
        system_prompt=SYSTEM_PROMPT,
        name=NODE_NAME,
        hooks=[LoggingHookProvider(NODE_NAME)],
    )
