"""Schema-level tests for the four new Phase 2 databases.

Phase 2 ships only the schemas (tables + indexes) for trades, positions,
capital and incidents. Repositories that write to these tables land in
Issues #7, #8, #9. These tests guard the column contract so later phases
can rely on it.
"""

from __future__ import annotations

from app.core.events import EventType
from app.database.connection import DatabaseSet


def _table_columns(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def test_trades_table_required_columns(phase2_dbs: DatabaseSet):
    cols = _table_columns(phase2_dbs.trades, "trades")
    required = {
        "trade_id", "order_id", "position_id", "symbol", "side",
        "qty", "price", "fee", "fee_asset", "is_maker", "is_paper",
        "timestamp", "payload_json", "created_at",
    }
    assert required.issubset(cols)


def test_positions_table_required_columns(phase2_dbs: DatabaseSet):
    cols = _table_columns(phase2_dbs.positions, "positions")
    required = {
        "position_id", "symbol", "direction", "qty", "entry_price",
        "mark_price", "stop_price", "stop_confirmed", "margin_mode",
        "leverage", "unrealized_pnl", "realized_pnl", "tail_qty",
        "state", "opened_at", "closed_at", "payload_json",
        "created_at", "updated_at",
    }
    assert required.issubset(cols)


def test_capital_snapshots_table_required_columns(phase2_dbs: DatabaseSet):
    cols = _table_columns(phase2_dbs.capital, "capital_snapshots")
    required = {
        "snapshot_id", "timestamp", "initial_capital", "exchange_equity",
        "withdrawn_profit", "lifetime_equity", "trading_capital",
        "account_life_tier", "risk_budget_total", "note", "created_at",
    }
    assert required.issubset(cols)


def test_capital_events_index_table_required_columns(phase2_dbs: DatabaseSet):
    cols = _table_columns(phase2_dbs.capital, "capital_events_index")
    required = {
        "event_id", "timestamp", "event_type", "amount",
        "currency", "payload_json", "created_at",
    }
    assert required.issubset(cols)


def test_incidents_table_required_columns(phase2_dbs: DatabaseSet):
    cols = _table_columns(phase2_dbs.incidents, "incidents")
    required = {
        "incident_id", "level", "title", "description", "source_module",
        "symbol", "position_id", "opened_at", "resolved_at", "resolution",
        "payload_json", "created_at",
    }
    assert required.issubset(cols)


def test_incident_log_table_required_columns(phase2_dbs: DatabaseSet):
    cols = _table_columns(phase2_dbs.incidents, "incident_log")
    required = {
        "log_id", "incident_id", "timestamp", "state", "note", "payload_json",
    }
    assert required.issubset(cols)


def test_phase2_does_not_create_market_db(tmp_path):
    """Issue #3 (Market) must not leak into Phase 2."""
    sqlite_dir = tmp_path / "sqlite"
    dbs = DatabaseSet.open(sqlite_dir)
    try:
        # market.db should NOT have been touched by DatabaseSet.open default.
        assert not (sqlite_dir / "market.db").exists()
        assert not (sqlite_dir / "orders.db").exists()
        assert not (sqlite_dir / "reflection.db").exists()
        assert not (sqlite_dir / "llm_cache.db").exists()
    finally:
        dbs.close()


def test_phase2_event_types_required_by_issue2_present():
    """Issue #2 mandates this exact set of event types in the vocabulary."""
    required = {
        # Capital events
        "CAPITAL_DEPOSIT", "CAPITAL_WITHDRAWAL", "PROFIT_HARVEST",
        "CAPITAL_REBASE", "RISK_BUDGET_RECALCULATED",
        # Order / system events
        "ORDER_SENT", "ORDER_ACK", "ORDER_FILLED",
        "STOP_CONFIRMED", "STOP_FAILED",
        "POSITION_OPENED", "POSITION_CLOSED",
        "RISK_APPROVED", "RISK_REJECTED",
        "PROTECTION_MODE_ENTERED", "PROTECTION_MODE_EXITED",
        "INCIDENT_OPENED", "INCIDENT_RESOLVED",
        "DATA_UNRELIABLE",
    }
    actual = {e.value for e in EventType}
    missing = required - actual
    assert not missing, f"Missing event types: {missing}"
