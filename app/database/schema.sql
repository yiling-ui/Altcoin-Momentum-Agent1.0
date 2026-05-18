-- AMA-RT events.db schema (Phase 2 - Event Sourcing and Database)
--
-- This is the substrate every other module writes to: state transitions,
-- risk decisions, capital events, incidents, telegram commands.
--
-- Phase 1 shipped the events table only. Phase 2 (Issue #2) adds:
--   * `created_at` column (mandated by Issue #2 field contract).
--   * Composite index on (event_type, timestamp) for replay-by-type queries.
--   * Schema files for trades.db, positions.db, capital.db, incidents.db
--     (see app/database/schemas/*.sql). Those four databases are created
--     and migrated by the same migration runner; their tables exist for
--     later phases (Issues #7, #8, #9) to populate.
--
-- All connections must be opened with PRAGMA journal_mode=WAL.

CREATE TABLE IF NOT EXISTS events (
    event_id      TEXT PRIMARY KEY,
    timestamp     INTEGER NOT NULL,
    event_type    TEXT    NOT NULL,
    source_module TEXT    NOT NULL,
    symbol        TEXT,
    position_id   TEXT,
    order_id      TEXT,
    payload_json  TEXT    NOT NULL DEFAULT '{}',
    created_at    INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER) * 1000)
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp        ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_event_type       ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_symbol           ON events(symbol);
CREATE INDEX IF NOT EXISTS idx_events_position_id      ON events(position_id);
CREATE INDEX IF NOT EXISTS idx_events_order_id         ON events(order_id);
CREATE INDEX IF NOT EXISTS idx_events_type_timestamp   ON events(event_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_events_symbol_timestamp ON events(symbol, timestamp);
