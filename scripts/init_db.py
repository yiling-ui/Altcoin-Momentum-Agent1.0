"""Initialise AMA-RT SQLite databases.

Phase 2 (Issue #2 - Event Sourcing and Database).

Usage:

    python -m scripts.init_db

What it does:
    - Creates `<data_dir>/sqlite/` if missing.
    - Opens (or creates) the five Phase 2 databases in WAL mode:
        events.db, trades.db, positions.db, capital.db, incidents.db
    - Applies each database's schema (idempotent).
    - Prints a multi-line summary so CI can detect success.

It does NOT touch any exchange or network resource. It does NOT insert
any rows. Running it twice on the same data dir is a no-op.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running both as `python scripts/init_db.py` and `python -m scripts.init_db`.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import get_settings  # noqa: E402
from app.database.connection import (  # noqa: E402
    PHASE2_DATABASES,
    DatabaseSet,
    journal_mode,
)
from app.database.migrations import migrate_database_set  # noqa: E402


def main() -> int:
    settings = get_settings()
    sqlite_dir = settings.sqlite_dir
    sqlite_dir.mkdir(parents=True, exist_ok=True)

    dbs = DatabaseSet.open(
        sqlite_dir,
        wal=settings.defaults.database.wal_mode,
        databases=PHASE2_DATABASES,
    )
    try:
        applied = migrate_database_set(dbs)
        print(
            f"[ama-rt][init_db] OK trading_mode={settings.trading_mode} "
            f"sqlite_dir={sqlite_dir}"
        )
        for name in PHASE2_DATABASES:
            jm = journal_mode(dbs.get(name))
            schema = applied.get(name, "?")
            print(
                f"[ama-rt][init_db]   {name:<14} journal={jm:<6} "
                f"schema={Path(schema).name}"
            )
    finally:
        dbs.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
