"""Database migration runner for AMA-RT (Phase 2 - Event Sourcing and Database).

Phase 2 introduces five separate SQLite databases (Spec §33.1):

    events.db      <- app/database/schema.sql
    trades.db      <- app/database/schemas/trades.sql
    positions.db   <- app/database/schemas/positions.sql
    capital.db     <- app/database/schemas/capital.sql
    incidents.db   <- app/database/schemas/incidents.sql

Every migration uses `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT
EXISTS` so the runner is idempotent. For the events table we additionally
detect a Phase-1 schema (no `created_at` column) and ALTER it in place,
which is the only schema delta Phase 2 introduces to a live table.

`apply_schema(conn)` keeps backwards compatibility with the Phase 1 call
sites in `app/main.py` and `scripts/init_db.py` (those scripts are updated
in this PR but the public function name is preserved).

`migrate_database_set(dbs)` migrates every database in a `DatabaseSet`
in one call. This is what Phase 2 callers should use.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.constants import (
    DB_CAPITAL,
    DB_EVENTS,
    DB_INCIDENTS,
    DB_POSITIONS,
    DB_TRADES,
)
from app.database.connection import DatabaseSet

SCHEMAS_DIR = Path(__file__).resolve().parent / "schemas"
EVENTS_SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"

# Mapping: db filename -> schema file. `events.db` keeps its top-level
# location for backwards compatibility with Phase 1 imports.
DB_SCHEMA_FILES: dict[str, Path] = {
    DB_EVENTS: EVENTS_SCHEMA_FILE,
    DB_TRADES: SCHEMAS_DIR / "trades.sql",
    DB_POSITIONS: SCHEMAS_DIR / "positions.sql",
    DB_CAPITAL: SCHEMAS_DIR / "capital.sql",
    DB_INCIDENTS: SCHEMAS_DIR / "incidents.sql",
}


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _migrate_events_created_at(conn: sqlite3.Connection) -> None:
    """Add the `created_at` column to a Phase-1 events table if missing.

    Spec §12.1 + Issue #2 require `created_at` on every event row. SQLite
    cannot use a non-constant default in `ALTER TABLE ... ADD COLUMN`, so
    we add the column with a constant 0 default and backfill it from the
    existing `timestamp` column. Subsequent inserts use the table-level
    default expression in `schema.sql`.
    """
    if not _table_exists(conn, "events"):
        return
    cols = _table_columns(conn, "events")
    if "created_at" in cols:
        return
    with conn:
        conn.execute("ALTER TABLE events ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE events SET created_at = timestamp WHERE created_at = 0")


def apply_schema(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    """Apply the SQL DDL in `schema_path` (or the bundled events schema).

    Phase-1-compatible entrypoint: callers that pass no `schema_path` get
    the events.db DDL. The `created_at` column delta is handled here so
    that an upgrade from a Phase 1 events.db is transparent.
    """
    target = schema_path or EVENTS_SCHEMA_FILE
    sql = target.read_text(encoding="utf-8")
    with conn:
        conn.executescript(sql)
    if target == EVENTS_SCHEMA_FILE:
        _migrate_events_created_at(conn)


def migrate_database(name: str, conn: sqlite3.Connection) -> None:
    """Migrate one database identified by file name (e.g. 'events.db')."""
    schema = DB_SCHEMA_FILES.get(name)
    if schema is None:
        raise ValueError(f"No schema registered for database {name!r}")
    apply_schema(conn, schema)


def migrate_database_set(dbs: DatabaseSet) -> dict[str, str]:
    """Migrate every database in a DatabaseSet.

    Returns a mapping `{db_name: applied_schema_path}` for logging /
    test inspection. Idempotent: running twice is a no-op.
    """
    applied: dict[str, str] = {}
    for name, conn in dbs:
        migrate_database(name, conn)
        applied[name] = str(DB_SCHEMA_FILES[name])
    return applied
