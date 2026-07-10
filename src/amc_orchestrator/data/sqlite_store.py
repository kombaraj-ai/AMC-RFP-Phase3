"""Quantitative fund performance data store (SQLite in DEV).

Deliberately dependency-free of Strands: this module is plain sqlite3 + dicts
so it is unit-testable without an LLM, and so the eventual STAGING/PROD swap to
a Snowflake/Redshift-backed implementation only needs to preserve
`fetch_fund_performance`'s signature, not its internals.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fund_performance (
    ticker TEXT PRIMARY KEY,
    fund_name TEXT NOT NULL,
    fund_category TEXT NOT NULL,
    nav REAL NOT NULL,
    alpha REAL NOT NULL,
    beta REAL NOT NULL,
    sharpe_ratio REAL NOT NULL,
    standard_deviation REAL NOT NULL,
    sortino_ratio REAL NOT NULL,
    r_squared REAL NOT NULL,
    returns_1y REAL NOT NULL,
    returns_3y REAL NOT NULL
)
"""

# (ticker, fund_name, fund_category, nav, alpha, beta, sharpe_ratio,
#  standard_deviation, sortino_ratio, r_squared, returns_1y, returns_3y)
_MOCK_FUNDS: list[tuple[Any, ...]] = [
    ("EQG1", "Global Equity Growth Fund", "Largecap", 145.20, 1.20, 1.05, 1.15, 14.20, 1.45, 0.92, 15.4, 12.1),
    ("SMC3", "Alpha Prime Smallcap Direct Fund", "Smallcap", 88.40, 4.50, 1.35, 1.30, 22.80, 1.68, 0.78, 28.6, 18.4),
    ("INC2", "Fixed Income Core Bond Fund", "Debt/Conservative", 52.10, 0.40, 0.35, 0.95, 4.10, 1.10, 0.15, 6.2, 5.8),
    ("BLN4", "Balanced Conservative Wealth Fund", "Hybrid", 112.75, 0.85, 0.75, 1.05, 9.50, 1.25, 0.85, 11.2, 9.5),
]

_COLUMNS = (
    "ticker", "fund_name", "fund_category", "nav", "alpha", "beta", "sharpe_ratio",
    "standard_deviation", "sortino_ratio", "r_squared", "returns_1y", "returns_3y",
)


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def ensure_seeded(db_path: Path) -> None:
    """Create the schema if needed and insert any mock funds not yet present.

    Insert-if-missing (not delete-and-recreate): this backs a persistent file
    reused across CLI runs, the API process, and tests.
    """
    conn = _connect(db_path)
    try:
        conn.execute(_SCHEMA)
        existing = {row[0] for row in conn.execute("SELECT ticker FROM fund_performance")}
        missing = [row for row in _MOCK_FUNDS if row[0] not in existing]
        if missing:
            placeholders = ", ".join(["?"] * len(_COLUMNS))
            conn.executemany(
                f"INSERT INTO fund_performance ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                missing,
            )
            conn.commit()
    finally:
        conn.close()


def fetch_fund_performance(db_path: Path, ticker: str) -> dict[str, Any] | None:
    """Return the performance metrics for `ticker`, or None if not found."""
    conn = _connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM fund_performance WHERE ticker = ?", (ticker.strip().upper(),)
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()
