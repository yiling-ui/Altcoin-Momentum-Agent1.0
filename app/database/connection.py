"""SQLite connection helpers for AMA-RT (Phase 2 - Event Sourcing and Database).

Always opens databases with WAL journal mode (Spec §33). Non-existent
parent directories are created on demand.

Phase 2 additions
-----------------
- `open_sqlite(path, wal=True)` is unchanged in semantics; behaviour is
  reused by every database (events, trades, positions, capital, incidents).
- `DatabaseSet` is a small container that opens / closes a known set of
  databases atomically, so callers like `python -m app.main` and
  `scripts/init_db.py` can iterate them with one statement.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from app.core.constants import (
    DB_CAPITAL,
    DB_EVENTS,
    DB_INCIDENTS,
    DB_POSITIONS,
    DB_TRADES,
)

# Phase 2 manages exactly these five databases. The remaining databases
# listed in `app/core/constants.py` (market.db, orders.db, reflection.db,
# llm_cache.db) are intentionally NOT created here - they belong to later
# phases (#3, #9, #10).
PHASE2_DATABASES: tuple[str, ...] = (
    DB_EVENTS,
    DB_TRADES,
    DB_POSITIONS,
    DB_CAPITAL,
    DB_INCIDENTS,
)


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


def journal_mode(conn: sqlite3.Connection) -> str:
    """Return the active journal mode (e.g. 'wal', 'delete', 'memory')."""
    row = conn.execute("PRAGMA journal_mode").fetchone()
    if row is None:
        return ""
    # row is sqlite3.Row or tuple depending on row_factory.
    try:
        return str(row[0]).lower()
    except (IndexError, KeyError):
        return ""


@dataclass
class DatabaseSet:
    """A bag of opened SQLite connections keyed by file name.

    Use `DatabaseSet.open(sqlite_dir)` to open the Phase 2 set in WAL mode,
    `set.events`, `set.trades`, etc. to access the typed handles, and
    `set.close()` (or the context-manager form) to close them all.
    """

    sqlite_dir: Path
    connections: dict[str, sqlite3.Connection]
    wal: bool = True

    @classmethod
    def open(
        cls,
        sqlite_dir: Path,
        *,
        wal: bool = True,
        databases: tuple[str, ...] = PHASE2_DATABASES,
    ) -> "DatabaseSet":
        sqlite_dir.mkdir(parents=True, exist_ok=True)
        conns: dict[str, sqlite3.Connection] = {}
        try:
            for name in databases:
                conns[name] = open_sqlite(sqlite_dir / name, wal=wal)
        except Exception:
            for c in conns.values():
                try:
                    c.close()
                except sqlite3.Error:
                    pass
            raise
        return cls(sqlite_dir=sqlite_dir, connections=conns, wal=wal)

    @property
    def events(self) -> sqlite3.Connection:
        return self.connections[DB_EVENTS]

    @property
    def trades(self) -> sqlite3.Connection:
        return self.connections[DB_TRADES]

    @property
    def positions(self) -> sqlite3.Connection:
        return self.connections[DB_POSITIONS]

    @property
    def capital(self) -> sqlite3.Connection:
        return self.connections[DB_CAPITAL]

    @property
    def incidents(self) -> sqlite3.Connection:
        return self.connections[DB_INCIDENTS]

    def get(self, name: str) -> sqlite3.Connection:
        return self.connections[name]

    def __iter__(self) -> Iterator[tuple[str, sqlite3.Connection]]:
        return iter(self.connections.items())

    def close(self) -> None:
        for c in self.connections.values():
            try:
                c.close()
            except sqlite3.Error:
                # closing must be best-effort; the caller is shutting down.
                pass


@contextmanager
def open_database_set(
    sqlite_dir: Path,
    *,
    wal: bool = True,
    databases: tuple[str, ...] = PHASE2_DATABASES,
) -> Iterator[DatabaseSet]:
    """Context-managed `DatabaseSet`."""
    dbs = DatabaseSet.open(sqlite_dir, wal=wal, databases=databases)
    try:
        yield dbs
    finally:
        dbs.close()
