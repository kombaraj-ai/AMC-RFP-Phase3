from pathlib import Path

from amc_orchestrator.data import chroma_store

_COLLECTION = "test_fund_manager_commentary"


def test_ensure_seeded_populates_four_documents(chroma_dir: Path) -> None:
    chroma_store.ensure_seeded(chroma_dir, _COLLECTION)

    results = chroma_store.search_commentary(chroma_dir, _COLLECTION, "fund", n_results=4)
    assert len(results) == 4


def test_search_commentary_returns_relevant_smallcap_doc(chroma_dir: Path) -> None:
    chroma_store.ensure_seeded(chroma_dir, _COLLECTION)

    results = chroma_store.search_commentary(
        chroma_dir, _COLLECTION, "smallcap volatility and downside risk", n_results=1
    )
    assert len(results) == 1
    assert "SMC3" in results[0]


def test_search_commentary_on_empty_collection_returns_empty_list(chroma_dir: Path) -> None:
    # Collection created but never seeded.
    results = chroma_store.search_commentary(chroma_dir, "empty_collection", "anything", n_results=1)
    assert results == []


def test_ensure_seeded_is_idempotent(chroma_dir: Path) -> None:
    chroma_store.ensure_seeded(chroma_dir, _COLLECTION)
    chroma_store.ensure_seeded(chroma_dir, _COLLECTION)  # must not duplicate

    results = chroma_store.search_commentary(chroma_dir, _COLLECTION, "fund", n_results=10)
    assert len(results) == 4
