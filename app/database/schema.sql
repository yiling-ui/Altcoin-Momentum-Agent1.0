-- AMA-RT database schema (Phase 1 - Safety Foundation)
--
-- Phase 1 only defines the events table. This is the substrate every other
-- module writes to: state transitions, risk decisions, capital events,
-- incidents, telegram commands. Phase 2 (Issue #2) will add trades.db,
-- positions.db, capital.db, incidents.db schemas.
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
    payload_json  TEXT    NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp   ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_event_type  ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_symbol      ON events(symbol);
CREATE INDEX IF NOT EXISTS idx_events_position_id ON events(position_id);
