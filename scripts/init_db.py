"""Initialise AMA-RT SQLite databases for Phase 1.

Usage:

    python -m scripts.init_db

What it does:
    - Creates `<data_dir>/sqlite/` if missing
    - Opens (or creates) `events.db` in WAL mode
    - Applies `app/database/schema.sql`
    - Prints a one-line summary so CI can detect success

It does NOT touch any exchange or network resource.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running both as `python scripts/init_db.py` and `python -m scripts.init_db`.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import get_settings  # noqa: E402
from app.core.constants import DB_EVENTS  # noqa: E402
from app.database.connection import open_sqlite  # noqa: E402
from app.database.migrations import apply_schema  # noqa: E402


def main() -> int:
    settings = get_settings()
    sqlite_dir = settings.sqlite_dir
    sqlite_dir.mkdir(parents=True, exist_ok=True)

    events_path = sqlite_dir / DB_EVENTS
    conn = open_sqlite(events_path, wal=settings.defaults.database.wal_mode)
    try:
        apply_schema(conn)
    finally:
        conn.close()

    print(
        f"[ama-rt][init_db] OK trading_mode={settings.trading_mode} "
        f"events_db={events_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
