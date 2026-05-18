-- AMA-RT trades.db schema (Phase 2 - Event Sourcing and Database)
--
-- Records every fill (real or paper) that lands in the system. Fills are
-- write-once: an `UPDATE` on a trade row is a programming error.
--
-- Phase 2 only ships the table shape and indexes. The repository that
-- writes/reads these rows is implemented in Issue #9 (Execution FSM /
-- Reconciliation). Phase 2 must not call INSERT into this table.
--
-- WAL mode is set by the connection helper.

CREATE TABLE IF NOT EXISTS trades (
    trade_id        TEXT PRIMARY KEY,        -- exchange trade id or paper UUID
    order_id        TEXT NOT NULL,           -- parent order id
    position_id     TEXT,                    -- linked position (nullable for paper)
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,           -- 'buy' | 'sell'
    qty             REAL NOT NULL,
    price           REAL NOT NULL,
    fee             REAL NOT NULL DEFAULT 0,
    fee_asset       TEXT,
    is_maker        INTEGER NOT NULL DEFAULT 0,
    is_paper        INTEGER NOT NULL DEFAULT 1,
    timestamp       INTEGER NOT NULL,        -- exchange timestamp (ms)
    payload_json    TEXT NOT NULL DEFAULT '{}',
    created_at      INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER) * 1000)
);

CREATE INDEX IF NOT EXISTS idx_trades_symbol      ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_order_id    ON trades(order_id);
CREATE INDEX IF NOT EXISTS idx_trades_position_id ON trades(position_id);
CREATE INDEX IF NOT EXISTS idx_trades_timestamp   ON trades(timestamp);
