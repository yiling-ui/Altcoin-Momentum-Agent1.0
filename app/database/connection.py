"""SQLite connection helper for AMA-RT.

Always opens databases with WAL journal mode (Spec §33). Non-existent
parent directories are created on demand.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def open_sqlite(path: Path, *, wal: bool = True) -> sqlite3.Connection:
    """Open a SQLite database in WAL mode by default.

    Returns a `sqlite3.Connection` with `row_factory` set to `sqlite3.Row`.
    Caller is responsible for closing the connection.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn
