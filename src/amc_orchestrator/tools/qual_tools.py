"""Strands tool wrappers around the qualitative (RAG) data layer.

Kept intentionally thin - all real logic lives in `data.chroma_store`/
`data.knowledge_base_store` (dispatched via `data.qual_store`) and is
unit-tested there without any Strands/LLM dependency.
"""

from __future__ import annotations

from strands import tool

from amc_orchestrator.config.settings import get_settings
from amc_orchestrator.data import qual_store


@tool
def search_fund_commentary(query: str) -> str:
    """Search the vector knowledge base for qualitative fund manager commentary.

    Use this to find manager strategy notes, investment committee commentary,
    and macroeconomic outlook explaining *why* a fund's numbers look the way
    they do. Do not invent strategic positions that are not returned here.

    Args:
        query: A natural-language description of the commentary you need,
            e.g. "Alpha Prime Smallcap Direct Fund volatility explanation".
    """
    settings = get_settings()
    results = qual_store.search_commentary(settings, query, n_results=2)
    if not results:
        return "No relevant fund manager commentary found for this query."
    return "\n\n".join(results)
