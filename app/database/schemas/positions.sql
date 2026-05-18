-- AMA-RT positions.db schema (Phase 2 - Event Sourcing and Database)
--
-- Tracks the lifecycle of every position. A position row is created when a
-- POSITION_OPENED event lands and is updated by POSITION_UPDATED and
-- POSITION_CLOSED events. The actual updater lives in Issue #9.
--
-- Phase 2 ships the schema only; no repository writes to this table yet.

CREATE TABLE IF NOT EXISTS positions (
    position_id      TEXT PRIMARY KEY,
    symbol           TEXT NOT NULL,
    direction        TEXT NOT NULL,           -- 'long' | 'short'
    qty              REAL NOT NULL,
    entry_price      REAL NOT NULL,
    mark_price       REAL,
    stop_price       REAL,
    stop_confirmed   INTEGER NOT NULL DEFAULT 0,
    margin_mode      TEXT NOT NULL DEFAULT 'isolated',
    leverage         REAL NOT NULL DEFAULT 1.0,
    unrealized_pnl   REAL NOT NULL DEFAULT 0,
    realized_pnl     REAL NOT NULL DEFAULT 0,
    tail_qty         REAL NOT NULL DEFAULT 0,
    state            TEXT NOT NULL,           -- ExecutionState.value
    opened_at        INTEGER NOT NULL,        -- ms
    closed_at        INTEGER,
    payload_json     TEXT NOT NULL DEFAULT '{}',
    created_at       INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER) * 1000),
    updated_at       INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER) * 1000)
);

CREATE INDEX IF NOT EXISTS idx_positions_symbol     ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_state      ON positions(state);
CREATE INDEX IF NOT EXISTS idx_positions_opened_at  ON positions(opened_at);
CREATE INDEX IF NOT EXISTS idx_positions_closed_at  ON positions(closed_at);
