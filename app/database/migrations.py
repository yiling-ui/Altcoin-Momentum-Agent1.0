"""Database migration runner for AMA-RT.

Phase 1 applies a single migration: `schema.sql`. The runner is
idempotent - running it twice is a no-op because every statement uses
`CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def apply_schema(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    """Apply the SQL DDL in `schema_path` (or the bundled schema.sql)."""
    sql = (schema_path or SCHEMA_FILE).read_text(encoding="utf-8")
    with conn:
        conn.executescript(sql)
