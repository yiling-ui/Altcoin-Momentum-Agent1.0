"""Tests for `app.database.connection.DatabaseSet` and migrations.

Phase 2 - Event Sourcing and Database (Issue #2). The DatabaseSet is the
multi-database connection container that powers `python -m app.main` and
`scripts/init_db.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.constants import (
    DB_CAPITAL,
    DB_EVENTS,
    DB_INCIDENTS,
    DB_POSITIONS,
    DB_TRADES,
)
from app.database.connection import (
    PHASE2_DATABASES,
    DatabaseSet,
    journal_mode,
    open_database_set,
    open_sqlite,
)
from app.database.migrations import (
    DB_SCHEMA_FILES,
    migrate_database,
    migrate_database_set,
)


def test_phase2_databases_constant_lists_five_dbs():
    assert PHASE2_DATABASES == (
        DB_EVENTS,
        DB_TRADES,
        DB_POSITIONS,
        DB_CAPITAL,
        DB_INCIDENTS,
    )


def test_database_set_open_creates_directory(tmp_path: Path):
    sqlite_dir = tmp_path / "fresh"
    assert not sqlite_dir.exists()
    dbs = DatabaseSet.open(sqlite_dir)
    try:
        assert sqlite_dir.exists()
        assert (sqlite_dir / "events.db").exists()
        assert (sqlite_dir / "trades.db").exists()
        assert (sqlite_dir / "positions.db").exists()
        assert (sqlite_dir / "capital.db").exists()
        assert (sqlite_dir / "incidents.db").exists()
    finally:
        dbs.close()


def test_database_set_typed_accessors(phase2_dbs: DatabaseSet):
    assert phase2_dbs.events is phase2_dbs.connections[DB_EVENTS]
    assert phase2_dbs.trades is phase2_dbs.connections[DB_TRADES]
    assert phase2_dbs.positions is phase2_dbs.connections[DB_POSITIONS]
    assert phase2_dbs.capital is phase2_dbs.connections[DB_CAPITAL]
    assert phase2_dbs.incidents is phase2_dbs.connections[DB_INCIDENTS]


def test_open_database_set_context_manager(tmp_path: Path):
    sqlite_dir = tmp_path / "ctx"
    with open_database_set(sqlite_dir) as dbs:
        # Connections are opened and the dir was created.
        assert sqlite_dir.exists()
        assert dbs.events is not None
    # No assertion on connection state after close: SQLite raises
    # ProgrammingError on use-after-close, which is the desired behaviour.


def test_database_set_iter_yields_name_conn_pairs(phase2_dbs: DatabaseSet):
    names = [name for name, _conn in phase2_dbs]
    assert names == list(PHASE2_DATABASES)


def test_database_set_close_is_idempotent(phase2_dbs: DatabaseSet):
    phase2_dbs.close()
    # second close must not raise
    phase2_dbs.close()


def test_wal_mode_is_active_on_each_database(phase2_dbs: DatabaseSet):
    """Spec §33: every database must be opened in WAL mode."""
    for name, conn in phase2_dbs:
        assert journal_mode(conn) == "wal", f"{name} is not in WAL mode"


def test_wal_can_be_disabled_for_in_memory(tmp_path: Path):
    """`wal=False` must be honoured (used for in-memory tests etc.)."""
    p = tmp_path / "no_wal.db"
    conn = open_sqlite(p, wal=False)
    try:
        # Without WAL the default is `delete` (rollback journal).
        mode = journal_mode(conn)
        assert mode != "wal"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------
def test_migrate_database_set_creates_all_tables(phase2_dbs: DatabaseSet):
    expected = {
        DB_EVENTS:    {"events"},
        DB_TRADES:    {"trades"},
        DB_POSITIONS: {"positions"},
        DB_CAPITAL:   {"capital_snapshots", "capital_events_index"},
        DB_INCIDENTS: {"incidents", "incident_log"},
    }
    for name, conn in phase2_dbs:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        actual = {r[0] for r in rows}
        for table in expected[name]:
            assert table in actual, f"{table} missing from {name}; got {actual}"


def test_migrate_database_set_is_idempotent(phase2_dbs: DatabaseSet):
    """Re-running the migrator on already-migrated dbs is a no-op."""
    applied = migrate_database_set(phase2_dbs)
    assert set(applied.keys()) == set(PHASE2_DATABASES)


def test_migrate_database_unknown_name_raises(tmp_path: Path):
    conn = open_sqlite(tmp_path / "x.db")
    try:
        with pytest.raises(ValueError):
            migrate_database("market.db", conn)  # not in DB_SCHEMA_FILES
    finally:
        conn.close()


def test_db_schema_files_cover_all_phase2_databases():
    assert set(DB_SCHEMA_FILES.keys()) == set(PHASE2_DATABASES)
    for path in DB_SCHEMA_FILES.values():
        assert path.exists(), f"Schema file {path} missing"


# ---------------------------------------------------------------------------
# Phase 1 -> Phase 2 events table upgrade path
# ---------------------------------------------------------------------------
def test_phase1_events_table_gets_created_at_on_migrate(tmp_path: Path):
    """A Phase 1 events.db without `created_at` must be upgraded in place."""
    db_path = tmp_path / "events.db"
    conn = open_sqlite(db_path)
    try:
        # Re-create the Phase 1 events table shape (no created_at).
        conn.executescript(
            """
            CREATE TABLE events (
                event_id      TEXT PRIMARY KEY,
                timestamp     INTEGER NOT NULL,
                event_type    TEXT    NOT NULL,
                source_module TEXT    NOT NULL,
                symbol        TEXT,
                position_id   TEXT,
                order_id      TEXT,
                payload_json  TEXT    NOT NULL DEFAULT '{}'
            );
            """
        )
        conn.execute(
            "INSERT INTO events (event_id, timestamp, event_type, source_module) "
            "VALUES (?, ?, ?, ?)",
            ("legacy-1", 12345, "STATE_TRANSITION", "legacy"),
        )
        conn.commit()

        from app.database.migrations import apply_schema

        apply_schema(conn)

        cols = [
            row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()
        ]
        assert "created_at" in cols

        legacy = conn.execute(
            "SELECT created_at FROM events WHERE event_id='legacy-1'"
        ).fetchone()
        # Backfill: legacy rows get created_at = timestamp.
        assert legacy[0] == 12345
    finally:
        conn.close()
