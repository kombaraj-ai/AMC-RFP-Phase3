"""Qualitative fund-manager commentary store (persistent on-disk ChromaDB in DEV).

Plain wrapper functions, no Strands dependency, so the data layer is
unit-testable in isolation and the eventual STAGING/PROD swap to Amazon
OpenSearch only needs to preserve `search_commentary`'s signature.
"""

from __future__ import annotations

from pathlib import Path

import chromadb

# Deterministic IDs so re-running `ensure_seeded` never duplicates documents.
_MOCK_COMMENTARY: list[tuple[str, str]] = [
    (
        "doc_eqg1",
        "Global Equity Growth Fund (EQG1): We maintain a structural overweight in "
        "mega-cap technology and secular growth vectors. The fund's R-squared of 0.92 "
        "reflects our tight correlation with benchmark leaders, while our focused stock "
        "selection drove a positive Alpha of 1.20.",
    ),
    (
        "doc_smc3",
        "Alpha Prime Smallcap Direct Fund (SMC3): The fund exhibits high volatility "
        "(Standard Deviation: 22.80%) due to tactical allocations in early-stage "
        "manufacturing and defense micro-caps. However, our strong focus on "
        "high-cash-flow companies yields a high Sortino Ratio of 1.68, successfully "
        "mitigating severe downside risk.",
    ),
    (
        "doc_inc2",
        "Fixed Income Core Bond Fund (INC2): We have actively reduced duration risk "
        "across the portfolio in response to central bank updates. The exceptionally "
        "low Beta of 0.35 demonstrates the fund's capacity to serve as an absolute "
        "defensive ballast during equity market corrections.",
    ),
    (
        "doc_bln4",
        "Balanced Conservative Wealth Fund (BLN4): A multi-asset dynamic allocation "
        "framework. We recently rebalanced 5% out of cyclical equities into short-term "
        "corporate bonds to lock in yields, stabilizing our Sharpe ratio near 1.05.",
    ),
]


def _get_client(persist_dir: Path) -> chromadb.ClientAPI:
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def ensure_seeded(persist_dir: Path, collection_name: str) -> None:
    """Create the collection if needed and upsert any mock commentary missing."""
    client = _get_client(persist_dir)
    collection = client.get_or_create_collection(name=collection_name)
    if collection.count() == 0:
        ids = [doc_id for doc_id, _ in _MOCK_COMMENTARY]
        documents = [text for _, text in _MOCK_COMMENTARY]
        collection.upsert(ids=ids, documents=documents)


def search_commentary(
    persist_dir: Path, collection_name: str, query: str, n_results: int = 2
) -> list[str]:
    """Return the most relevant commentary passages for `query`, best first."""
    client = _get_client(persist_dir)
    collection = client.get_or_create_collection(name=collection_name)
    if collection.count() == 0:
        return []
    results = collection.query(query_texts=[query], n_results=min(n_results, collection.count()))
    documents = results.get("documents") or [[]]
    return list(documents[0])
