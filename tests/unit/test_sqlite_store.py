from pathlib import Path

from amc_orchestrator.data import sqlite_store


def test_ensure_seeded_creates_all_mock_funds(sqlite_db_path: Path) -> None:
    sqlite_store.ensure_seeded(sqlite_db_path)

    for ticker in ("EQG1", "SMC3", "INC2", "BLN4"):
        row = sqlite_store.fetch_fund_performance(sqlite_db_path, ticker)
        assert row is not None
        assert row["ticker"] == ticker


def test_fetch_fund_performance_is_case_insensitive(sqlite_db_path: Path) -> None:
    sqlite_store.ensure_seeded(sqlite_db_path)

    assert sqlite_store.fetch_fund_performance(sqlite_db_path, "smc3") is not None
    assert sqlite_store.fetch_fund_performance(sqlite_db_path, "  SMC3  ") is not None


def test_fetch_fund_performance_returns_none_for_unknown_ticker(sqlite_db_path: Path) -> None:
    sqlite_store.ensure_seeded(sqlite_db_path)

    assert sqlite_store.fetch_fund_performance(sqlite_db_path, "ZZZZ") is None


def test_smc3_has_expected_high_risk_metrics(sqlite_db_path: Path) -> None:
    sqlite_store.ensure_seeded(sqlite_db_path)

    row = sqlite_store.fetch_fund_performance(sqlite_db_path, "SMC3")
    assert row is not None
    assert row["fund_category"] == "Smallcap"
    assert row["standard_deviation"] == 22.80
    assert row["returns_1y"] == 28.6


def test_ensure_seeded_is_idempotent(sqlite_db_path: Path) -> None:
    sqlite_store.ensure_seeded(sqlite_db_path)
    sqlite_store.ensure_seeded(sqlite_db_path)  # must not raise / duplicate

    import sqlite3

    conn = sqlite3.connect(sqlite_db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM fund_performance").fetchone()[0]
        assert count == 4
    finally:
        conn.close()
