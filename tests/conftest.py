"""Pytest fixtures shared across AMA-RT tests.

We build:
    - `events_repo`: an in-memory SQLite EventRepository (no disk IO)
    - `phase1_settings`: the cached Settings object loaded from
      `app/config/defaults.yaml` with the Phase 1 safety lock applied.
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
from app.database.migrations import apply_schema  # noqa: E402
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
