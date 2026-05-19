-- AMA-RT capital.db schema (Phase 2 - Event Sourcing and Database)
--
-- Spec §28 (Capital Flow Engine). Two tables:
--
--   capital_snapshots
--     A point-in-time materialised view of the four account scalars:
--       initial_capital, exchange_equity, withdrawn_profit, lifetime_equity,
--       trading_capital, account_life_tier, risk_budget_total.
--     One row per Rebase / Profit Harvest / external event.
--
--   capital_events_index
--     A denormalised index of capital-related events that already live in
--     events.db, kept here so that the Capital Flow Engine (Issue #8) can
--     answer "which deposit/withdrawal/harvest happened in window X?"
--     without scanning the whole events table.
--
-- Phase 2 creates the tables and ships the writer for `capital_events_index`
-- via the EventRepository helper. Materialised snapshots are deferred to
-- Issue #8 (Capital Flow Engine).

CREATE TABLE IF NOT EXISTS capital_snapshots (
    snapshot_id               TEXT PRIMARY KEY,
    timestamp                 INTEGER NOT NULL,
    initial_capital           REAL NOT NULL,
    exchange_equity           REAL NOT NULL,
    withdrawn_profit          REAL NOT NULL DEFAULT 0,
    lifetime_equity           REAL NOT NULL,
    trading_capital           REAL NOT NULL,
    account_life_tier         TEXT NOT NULL,
    risk_budget_total         REAL NOT NULL,
    -- Phase 8 Issue #8 fix - External Capital Flow tracking. Default 0
    -- preserves backwards compatibility with Phase 1-7 capital.db files.
    -- When upgrading an existing capital.db, idempotent ALTER TABLE in
    -- app/database/migrations.py adds the columns in place.
    external_deposits_total   REAL NOT NULL DEFAULT 0,
    principal_withdrawn_total REAL NOT NULL DEFAULT 0,
    note                      TEXT,
    created_at                INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER) * 1000)
);

CREATE INDEX IF NOT EXISTS idx_capital_snapshots_timestamp
    ON capital_snapshots(timestamp);

CREATE TABLE IF NOT EXISTS capital_events_index (
    event_id     TEXT PRIMARY KEY,            -- references events.db events.event_id
    timestamp    INTEGER NOT NULL,
    event_type   TEXT NOT NULL,               -- CAPITAL_DEPOSIT | CAPITAL_WITHDRAWAL
                                              -- | PROFIT_HARVEST | CAPITAL_REBASE
                                              -- | RISK_BUDGET_RECALCULATED
    amount       REAL NOT NULL DEFAULT 0,     -- amount in account currency
    currency     TEXT NOT NULL DEFAULT 'USDT',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at   INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER) * 1000)
);

CREATE INDEX IF NOT EXISTS idx_capital_events_timestamp  ON capital_events_index(timestamp);
CREATE INDEX IF NOT EXISTS idx_capital_events_event_type ON capital_events_index(event_type);
