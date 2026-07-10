"""Shared pytest fixtures.

Tests never touch the real DEV `local_dev.db` / `data/chroma` - each test gets
its own tmp_path-scoped copies, so running the suite never mutates the
developer's actual local data.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def sqlite_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_fund_performance.db"


@pytest.fixture
def chroma_dir(tmp_path: Path) -> Path:
    return tmp_path / "test_chroma"
