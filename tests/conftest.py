"""Pytest fixtures shared across AMA-RT tests.

We build:
    - `events_repo`: an in-memory SQLite EventRepository (no disk IO)
    - `phase1_settings`: the cached Settings object loaded from
      `app/config/defaults.yaml` with the Phase 1 safety lock applied.
    - `phase2_dbs`: a `DatabaseSet` opened against a temp directory with
      all five Phase 2 databases migrated and ready (events, trades,
      positions, capital, incidents).
    - `events_repo_with_capital`: an EventRepository wired to a real
      capital.db so capital_events_index is exercised end-to-end.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import load_settings  # noqa: E402
from app.database.connection import DatabaseSet, PHASE2_DATABASES  # noqa: E402
from app.database.migrations import apply_schema, migrate_database_set  # noqa: E402
from app.database.repositories import EventRepository  # noqa: E402


@pytest.fixture
def in_memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    apply_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def events_repo(in_memory_conn: sqlite3.Connection) -> EventRepository:
    return EventRepository(in_memory_conn)


@pytest.fixture
def phase1_settings():
    return load_settings()


@pytest.fixture
def phase2_dbs(tmp_path: Path) -> DatabaseSet:
    """A migrated, on-disk DatabaseSet for the five Phase 2 databases."""
    sqlite_dir = tmp_path / "sqlite"
    dbs = DatabaseSet.open(sqlite_dir, wal=True, databases=PHASE2_DATABASES)
    migrate_database_set(dbs)
    try:
        yield dbs
    finally:
        dbs.close()


@pytest.fixture
def events_repo_with_capital(phase2_dbs: DatabaseSet) -> EventRepository:
    """An EventRepository wired to events.db AND capital.db.

    Use this fixture whenever you need to exercise the capital_events_index
    mirror table (e.g. in capital event tests).
    """
    return EventRepository(phase2_dbs.events, capital_conn=phase2_dbs.capital)
