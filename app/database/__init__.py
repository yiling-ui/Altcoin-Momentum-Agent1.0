"""SQLite persistence layer for AMA-RT.

Phase 2 (Issue #2 - Event Sourcing and Database) ships:

    - schema.sql                -- events.db DDL (with created_at column)
    - schemas/trades.sql        -- trades.db DDL
    - schemas/positions.sql     -- positions.db DDL
    - schemas/capital.sql       -- capital.db DDL
                                   (tables: capital_snapshots,
                                    capital_events_index)
    - schemas/incidents.sql     -- incidents.db DDL
    - connection.py             -- WAL helper + DatabaseSet for the 5 dbs
    - migrations.py             -- migrate_database / migrate_database_set
    - repositories.EventRepository
        * append_event / append_many
        * list_events / replay_events / count_events
        * record_capital_deposit / withdrawal / harvest / rebase
          / risk_budget_recalculated
        * persistence failures logged + raised (no silent loss)

The remaining databases listed in Spec §33.1 (`market.db`, `orders.db`,
`reflection.db`, `llm_cache.db`) are deliberately deferred to later
phases (Issues #3, #9, #10) so Phase 2 cannot accidentally bring in
exchange / LLM code paths.
"""

from app.database.connection import (  # noqa: F401
    PHASE2_DATABASES,
    DatabaseSet,
    journal_mode,
    open_database_set,
    open_sqlite,
)
from app.database.migrations import (  # noqa: F401
    DB_SCHEMA_FILES,
    apply_schema,
    migrate_database,
    migrate_database_set,
)
from app.database.repositories import EventRepository  # noqa: F401
