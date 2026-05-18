"""Event Sourcing repository tests (Phase 2 - Event Sourcing and Database).

Covers Issue #2 mandates:
    - append_event / append_many
    - list_events / replay_events / count_events
    - filters by time range, symbol, event_type
    - persistence failure path raises EventPersistenceError + logs
    - capital event helpers (deposit / withdrawal / harvest / rebase / risk
      budget recalculated)
    - capital_events_index mirror in capital.db
    - phase-1 method aliases (append/list/replay/count) keep working
"""

from __future__ import annotations

import sqlite3

import pytest

from app.core.errors import EventPersistenceError
from app.core.events import CAPITAL_EVENT_TYPES, Event, EventType
from app.database.repositories import EventRepository


# ---------------------------------------------------------------------------
# Basic write / read
# ---------------------------------------------------------------------------
def test_append_event_returns_event_with_created_at(events_repo):
    persisted = events_repo.append_event(
        Event(
            event_type=EventType.STATE_TRANSITION,
            source_module="test",
            payload={"from": "idle", "to": "idle"},
        )
    )
    assert persisted.created_at is not None
    assert events_repo.count_events() == 1


def test_required_field_contract(events_repo):
    """Spec §12.1 + Issue #2 field contract: every event must carry the same field set."""
    events_repo.append_event(
        Event(
            event_type=EventType.RISK_APPROVED,
            source_module="risk_engine",
            symbol="BTCUSDT",
            position_id="pos-1",
            order_id="ord-1",
            payload={"reasons": ["paper_only_skeleton_approval"]},
        )
    )
    [event] = events_repo.list_events()
    assert event.symbol == "BTCUSDT"
    assert event.position_id == "pos-1"
    assert event.order_id == "ord-1"
    assert event.event_type is EventType.RISK_APPROVED
    assert event.payload == {"reasons": ["paper_only_skeleton_approval"]}
    assert event.event_id  # uuid4 generated
    assert event.timestamp > 0
    assert event.created_at is not None


def test_append_many_atomic(events_repo):
    persisted = events_repo.append_many(
        [
            Event(event_type=EventType.STATE_TRANSITION, source_module="t", timestamp=300),
            Event(event_type=EventType.STATE_TRANSITION, source_module="t", timestamp=100),
            Event(event_type=EventType.STATE_TRANSITION, source_module="t", timestamp=200),
        ]
    )
    assert len(persisted) == 3
    assert events_repo.count_events() == 3


def test_append_many_empty_is_noop(events_repo):
    out = events_repo.append_many([])
    assert out == []
    assert events_repo.count_events() == 0


# ---------------------------------------------------------------------------
# Replay ordering
# ---------------------------------------------------------------------------
def test_replay_events_ordered_by_timestamp(events_repo):
    events_repo.append_many(
        [
            Event(event_type=EventType.STATE_TRANSITION, source_module="t", timestamp=300),
            Event(event_type=EventType.STATE_TRANSITION, source_module="t", timestamp=100),
            Event(event_type=EventType.STATE_TRANSITION, source_module="t", timestamp=200),
        ]
    )
    timestamps = [e.timestamp for e in events_repo.replay_events()]
    assert timestamps == [100, 200, 300]


def test_replay_events_iterates_lazily(events_repo):
    events_repo.append_many(
        [Event(event_type=EventType.STATE_TRANSITION, source_module="t", timestamp=i) for i in range(5)]
    )
    iterator = events_repo.replay_events()
    first = next(iterator)
    assert first.timestamp == 0
    rest = list(iterator)
    assert [e.timestamp for e in rest] == [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
def test_filter_by_event_type(events_repo):
    events_repo.append_many(
        [
            Event(event_type=EventType.RISK_APPROVED, source_module="r"),
            Event(event_type=EventType.RISK_REJECTED, source_module="r"),
            Event(event_type=EventType.RISK_REJECTED, source_module="r"),
        ]
    )
    rejects = events_repo.list_events(event_type=EventType.RISK_REJECTED)
    assert len(rejects) == 2
    assert all(e.event_type is EventType.RISK_REJECTED for e in rejects)


def test_filter_by_event_type_string(events_repo):
    events_repo.append_event(
        Event(event_type=EventType.ORDER_SENT, source_module="exec"),
    )
    out = events_repo.list_events(event_type="ORDER_SENT")
    assert len(out) == 1


def test_filter_by_event_types_iterable(events_repo):
    events_repo.append_many(
        [
            Event(event_type=EventType.ORDER_SENT, source_module="e"),
            Event(event_type=EventType.ORDER_FILLED, source_module="e"),
            Event(event_type=EventType.RISK_APPROVED, source_module="r"),
        ]
    )
    order_events = events_repo.list_events(
        event_types=[EventType.ORDER_SENT, EventType.ORDER_FILLED]
    )
    assert len(order_events) == 2


def test_filter_by_event_types_empty_iterable_returns_nothing(events_repo):
    events_repo.append_event(Event(event_type=EventType.ORDER_SENT, source_module="e"))
    assert events_repo.list_events(event_types=[]) == []


def test_filter_by_symbol(events_repo):
    events_repo.append_many(
        [
            Event(event_type=EventType.ANOMALY_DETECTED, source_module="s", symbol="PEPEUSDT"),
            Event(event_type=EventType.ANOMALY_DETECTED, source_module="s", symbol="DOGEUSDT"),
            Event(event_type=EventType.ANOMALY_DETECTED, source_module="s", symbol="PEPEUSDT"),
        ]
    )
    pepe = events_repo.list_events(symbol="PEPEUSDT")
    assert len(pepe) == 2
    assert all(e.symbol == "PEPEUSDT" for e in pepe)


def test_filter_by_time_range(events_repo):
    events_repo.append_many(
        [
            Event(event_type=EventType.STATE_TRANSITION, source_module="t", timestamp=100),
            Event(event_type=EventType.STATE_TRANSITION, source_module="t", timestamp=200),
            Event(event_type=EventType.STATE_TRANSITION, source_module="t", timestamp=300),
            Event(event_type=EventType.STATE_TRANSITION, source_module="t", timestamp=400),
        ]
    )
    window = events_repo.list_events(since_ts=200, until_ts=300)
    assert [e.timestamp for e in window] == [200, 300]


def test_filter_by_source_module(events_repo):
    events_repo.append_many(
        [
            Event(event_type=EventType.STATE_TRANSITION, source_module="risk_engine"),
            Event(event_type=EventType.STATE_TRANSITION, source_module="execution"),
        ]
    )
    out = events_repo.list_events(source_module="risk_engine")
    assert len(out) == 1


def test_filter_by_position_id_and_order_id(events_repo):
    events_repo.append_many(
        [
            Event(event_type=EventType.ORDER_SENT, source_module="e",
                  position_id="P1", order_id="O1"),
            Event(event_type=EventType.ORDER_FILLED, source_module="e",
                  position_id="P1", order_id="O1"),
            Event(event_type=EventType.ORDER_SENT, source_module="e",
                  position_id="P2", order_id="O2"),
        ]
    )
    p1 = events_repo.list_events(position_id="P1")
    assert len(p1) == 2
    o2 = events_repo.list_events(order_id="O2")
    assert len(o2) == 1


def test_combined_filters_and_together(events_repo):
    events_repo.append_many(
        [
            Event(event_type=EventType.RISK_REJECTED, source_module="r",
                  symbol="X", timestamp=100),
            Event(event_type=EventType.RISK_REJECTED, source_module="r",
                  symbol="Y", timestamp=150),
            Event(event_type=EventType.RISK_APPROVED, source_module="r",
                  symbol="X", timestamp=200),
        ]
    )
    out = events_repo.list_events(
        event_type=EventType.RISK_REJECTED,
        symbol="X",
        since_ts=50,
        until_ts=150,
    )
    assert len(out) == 1
    assert out[0].timestamp == 100


def test_count_events_with_filters(events_repo):
    events_repo.append_many(
        [
            Event(event_type=EventType.RISK_REJECTED, source_module="r"),
            Event(event_type=EventType.RISK_REJECTED, source_module="r"),
            Event(event_type=EventType.RISK_APPROVED, source_module="r"),
        ]
    )
    assert events_repo.count_events() == 3
    assert events_repo.count_events(event_type=EventType.RISK_REJECTED) == 2
    assert events_repo.count_events(event_type=EventType.RISK_APPROVED) == 1


def test_limit_and_offset(events_repo):
    events_repo.append_many(
        [Event(event_type=EventType.STATE_TRANSITION, source_module="t", timestamp=i) for i in range(10)]
    )
    page = events_repo.list_events(limit=3, offset=2)
    assert [e.timestamp for e in page] == [2, 3, 4]


# ---------------------------------------------------------------------------
# Phase 1 backwards-compat aliases
# ---------------------------------------------------------------------------
def test_phase1_method_aliases_still_work(events_repo):
    events_repo.append(Event(event_type=EventType.STATE_TRANSITION, source_module="t"))
    assert events_repo.count() == 1
    assert len(events_repo.list()) == 1
    assert len(list(events_repo.replay())) == 1


# ---------------------------------------------------------------------------
# Persistence failure path
# ---------------------------------------------------------------------------
def test_append_failure_raises_event_persistence_error(events_repo):
    """Drop the events table to provoke a sqlite OperationalError.

    The repository must wrap it in EventPersistenceError, NOT silently
    swallow the failure (Issue #2 §"事件写入失败时必须有错误处理和日志").
    """
    events_repo.conn.execute("DROP TABLE events")
    with pytest.raises(EventPersistenceError):
        events_repo.append_event(
            Event(event_type=EventType.STATE_TRANSITION, source_module="t")
        )
    assert events_repo.failed_appends == 1


def test_list_events_failure_raises(events_repo):
    events_repo.conn.execute("DROP TABLE events")
    with pytest.raises(EventPersistenceError):
        events_repo.list_events()


def test_count_events_failure_raises(events_repo):
    events_repo.conn.execute("DROP TABLE events")
    with pytest.raises(EventPersistenceError):
        events_repo.count_events()


def test_payload_must_be_json_serialisable_raises(events_repo):
    """Non-JSON-safe payload at insert time -> EventPersistenceError."""

    class NonSerialisable:
        pass

    with pytest.raises(EventPersistenceError):
        events_repo.append_event(
            Event(
                event_type=EventType.STATE_TRANSITION,
                source_module="t",
                payload={"bad": NonSerialisable()},
            )
        )


# ---------------------------------------------------------------------------
# Capital event helpers (Issue #2 mandate + Spec §28.3)
# ---------------------------------------------------------------------------
def test_record_capital_deposit(events_repo):
    ev = events_repo.record_capital_deposit(amount=100.0, note="seed")
    assert ev.event_type is EventType.CAPITAL_DEPOSIT
    assert ev.payload["amount"] == 100.0
    assert ev.payload["currency"] == "USDT"
    assert ev.payload["note"] == "seed"


def test_record_capital_withdrawal(events_repo):
    ev = events_repo.record_capital_withdrawal(amount=80.0)
    assert ev.event_type is EventType.CAPITAL_WITHDRAWAL
    assert ev.payload["amount"] == 80.0


def test_record_profit_harvest(events_repo):
    ev = events_repo.record_profit_harvest(amount=42.5)
    assert ev.event_type is EventType.PROFIT_HARVEST
    assert ev.payload["amount"] == 42.5


def test_record_capital_rebase_carries_rebase_payload(events_repo):
    ev = events_repo.record_capital_rebase(
        exchange_equity=120.0,
        withdrawn_profit=80.0,
        lifetime_equity=200.0,
        trading_capital=120.0,
        note="post_withdrawal",
    )
    assert ev.event_type is EventType.CAPITAL_REBASE
    assert ev.payload == {
        "amount": 120.0,
        "currency": "USDT",
        "exchange_equity": 120.0,
        "withdrawn_profit": 80.0,
        "lifetime_equity": 200.0,
        "trading_capital": 120.0,
        "note": "post_withdrawal",
    }


def test_record_risk_budget_recalculated(events_repo):
    ev = events_repo.record_risk_budget_recalculated(
        new_risk_budget=120.0,
        previous_risk_budget=200.0,
    )
    assert ev.event_type is EventType.RISK_BUDGET_RECALCULATED
    assert ev.payload["new_risk_budget"] == 120.0
    assert ev.payload["previous_risk_budget"] == 200.0


def test_record_capital_deposit_negative_amount_rejected(events_repo):
    with pytest.raises(ValueError):
        events_repo.record_capital_deposit(amount=-1.0)


def test_capital_event_types_constant_matches_spec():
    # Spec §28.3 + Issue #2 list five capital event types.
    assert {e.value for e in CAPITAL_EVENT_TYPES} == {
        "CAPITAL_DEPOSIT",
        "CAPITAL_WITHDRAWAL",
        "PROFIT_HARVEST",
        "CAPITAL_REBASE",
        "RISK_BUDGET_RECALCULATED",
    }


# ---------------------------------------------------------------------------
# Capital index mirror (cross-database write to capital.db)
# ---------------------------------------------------------------------------
def test_capital_events_mirror_into_capital_index(events_repo_with_capital, phase2_dbs):
    events_repo_with_capital.record_capital_deposit(amount=100.0)
    events_repo_with_capital.record_capital_withdrawal(amount=80.0, note="harvest")
    events_repo_with_capital.record_profit_harvest(amount=42.0)
    events_repo_with_capital.record_capital_rebase(
        exchange_equity=120.0,
        withdrawn_profit=80.0,
        lifetime_equity=200.0,
        trading_capital=120.0,
    )
    events_repo_with_capital.record_risk_budget_recalculated(new_risk_budget=120.0)

    cur = phase2_dbs.capital.execute(
        "SELECT event_type, amount, currency FROM capital_events_index "
        "ORDER BY timestamp ASC, event_id ASC"
    )
    rows = cur.fetchall()
    assert len(rows) == 5
    types = [r["event_type"] for r in rows]
    assert "CAPITAL_DEPOSIT" in types
    assert "CAPITAL_WITHDRAWAL" in types
    assert "PROFIT_HARVEST" in types
    assert "CAPITAL_REBASE" in types
    assert "RISK_BUDGET_RECALCULATED" in types


def test_non_capital_events_do_not_touch_capital_index(events_repo_with_capital, phase2_dbs):
    events_repo_with_capital.append_event(
        Event(event_type=EventType.STATE_TRANSITION, source_module="t")
    )
    rows = phase2_dbs.capital.execute(
        "SELECT COUNT(*) AS n FROM capital_events_index"
    ).fetchone()
    assert rows["n"] == 0


# ---------------------------------------------------------------------------
# created_at column is populated
# ---------------------------------------------------------------------------
def test_created_at_column_populated_on_insert(events_repo):
    events_repo.append_event(
        Event(event_type=EventType.STATE_TRANSITION, source_module="t")
    )
    [event] = events_repo.list_events()
    assert event.created_at is not None
    assert event.created_at > 0


# ---------------------------------------------------------------------------
# Direct sqlite verification of the schema (Issue #2 acceptance #1, #5, #6)
# ---------------------------------------------------------------------------
def test_events_table_columns_match_issue2_contract(in_memory_conn: sqlite3.Connection):
    cols = [
        row[1]
        for row in in_memory_conn.execute("PRAGMA table_info(events)").fetchall()
    ]
    required = {
        "event_id",
        "timestamp",
        "event_type",
        "source_module",
        "symbol",
        "position_id",
        "order_id",
        "payload_json",
        "created_at",
    }
    assert required.issubset(set(cols))



# ---------------------------------------------------------------------------
# Production-safety regression tests added during Phase 2 PR self-audit.
#
# These three tests guard behaviours that were claimed in commit messages /
# code comments but were not previously asserted. They exist to make
# Issue #8 (Capital Flow Engine) safe to build on top of Phase 2.
# ---------------------------------------------------------------------------
def test_capital_mirror_failure_does_not_roll_back_events(
    events_repo_with_capital, phase2_dbs
):
    """If capital_events_index is corrupted, the events.db write must still succeed.

    The repository's docstring promises that a capital-mirror failure is
    logged but does NOT roll back the events.db write (the index is
    rebuildable from events.db on demand). A regression here would mean a
    silent data-loss path: a CAPITAL_DEPOSIT could be visible in the
    capital index but missing from the canonical event log, OR vice
    versa, depending on which side of the rollback failed.
    """
    # Drop the mirror table to force a sqlite OperationalError on the
    # mirror INSERT. The events.db write must still go through.
    phase2_dbs.capital.execute("DROP TABLE capital_events_index")
    phase2_dbs.capital.commit()

    ev = events_repo_with_capital.record_capital_deposit(amount=100.0)

    # 1. The event was persisted into events.db.
    assert events_repo_with_capital.count_events(
        event_type=EventType.CAPITAL_DEPOSIT
    ) == 1
    [persisted] = events_repo_with_capital.list_events(
        event_type=EventType.CAPITAL_DEPOSIT
    )
    assert persisted.event_id == ev.event_id
    assert persisted.payload["amount"] == 100.0

    # 2. The mirror is gone (table dropped) but the repository did not
    # raise and did not increment failed_appends - the events write
    # itself succeeded.
    assert events_repo_with_capital.failed_appends == 0


def test_capital_rebase_never_emits_withdrawal_event(events_repo_with_capital):
    """Spec §28 hard rule: 'Withdrawal is NOT a loss; rebase resets the basis'.

    The Capital Flow Engine in Issue #8 will rely on these event types
    being distinct. A regression here (e.g. CAPITAL_REBASE accidentally
    typed as CAPITAL_WITHDRAWAL) would cause the engine to subtract
    rebased capital from PnL. We assert here that the rebase helper
    emits exactly one CAPITAL_REBASE event and zero CAPITAL_WITHDRAWAL
    events.
    """
    events_repo_with_capital.record_capital_rebase(
        exchange_equity=120.0,
        withdrawn_profit=80.0,
        lifetime_equity=200.0,
        trading_capital=120.0,
        note="post_withdrawal_rebase",
    )
    assert events_repo_with_capital.count_events(
        event_type=EventType.CAPITAL_REBASE
    ) == 1
    assert events_repo_with_capital.count_events(
        event_type=EventType.CAPITAL_WITHDRAWAL
    ) == 0
    # And the rebase payload preserves the four scalars Spec §28.2 requires.
    [rebase] = events_repo_with_capital.list_events(
        event_type=EventType.CAPITAL_REBASE
    )
    assert rebase.payload["exchange_equity"] == 120.0
    assert rebase.payload["withdrawn_profit"] == 80.0
    assert rebase.payload["lifetime_equity"] == 200.0
    assert rebase.payload["trading_capital"] == 120.0


def test_withdrawal_amount_zero_is_allowed_but_negative_is_not(events_repo):
    """Withdrawals are recorded as positive amounts; the direction is
    encoded by event_type. A negative amount is a programming error and
    must be rejected at the helper boundary so it cannot reach the
    capital index.
    """
    # zero is allowed (e.g. a 'no-op confirmation' marker).
    events_repo.record_capital_withdrawal(amount=0.0)
    # negative is not.
    with pytest.raises(ValueError):
        events_repo.record_capital_withdrawal(amount=-1.0)
    with pytest.raises(ValueError):
        events_repo.record_profit_harvest(amount=-0.01)



# ---------------------------------------------------------------------------
# Phase 2 PR self-audit (round 2) - rebuild contract for capital_events_index
#
# Item #2 of the audit: events.db is source of truth; capital_events_index
# is a derived, rebuildable mirror. The repository ships an executable
# `rebuild_capital_events_index()` so that contract is enforced by code,
# not just by docs.
# ---------------------------------------------------------------------------
def test_rebuild_capital_events_index_from_events_db(
    events_repo_with_capital, phase2_dbs
):
    """If capital.db is wiped, rebuild() must reproduce the index from events.db."""
    events_repo_with_capital.record_capital_deposit(amount=100.0, note="seed")
    events_repo_with_capital.record_capital_withdrawal(amount=80.0, note="harvest")
    events_repo_with_capital.record_profit_harvest(amount=42.0)
    events_repo_with_capital.record_capital_rebase(
        exchange_equity=120.0,
        withdrawn_profit=80.0,
        lifetime_equity=200.0,
        trading_capital=120.0,
    )
    events_repo_with_capital.record_risk_budget_recalculated(new_risk_budget=120.0)

    # Wipe the mirror (simulates capital.db restored from older backup).
    phase2_dbs.capital.execute("DELETE FROM capital_events_index")
    phase2_dbs.capital.commit()
    assert phase2_dbs.capital.execute(
        "SELECT COUNT(*) FROM capital_events_index"
    ).fetchone()[0] == 0

    # Rebuild from events.db (source of truth).
    written = events_repo_with_capital.rebuild_capital_events_index()
    assert written == 5

    types = [
        r["event_type"]
        for r in phase2_dbs.capital.execute(
            "SELECT event_type FROM capital_events_index "
            "ORDER BY timestamp ASC, event_id ASC"
        ).fetchall()
    ]
    assert set(types) == {
        "CAPITAL_DEPOSIT",
        "CAPITAL_WITHDRAWAL",
        "PROFIT_HARVEST",
        "CAPITAL_REBASE",
        "RISK_BUDGET_RECALCULATED",
    }


def test_rebuild_capital_events_index_is_idempotent(events_repo_with_capital, phase2_dbs):
    events_repo_with_capital.record_capital_deposit(amount=10.0)
    events_repo_with_capital.record_capital_withdrawal(amount=3.0)

    first = events_repo_with_capital.rebuild_capital_events_index()
    second = events_repo_with_capital.rebuild_capital_events_index()
    assert first == second == 2
    assert phase2_dbs.capital.execute(
        "SELECT COUNT(*) FROM capital_events_index"
    ).fetchone()[0] == 2


def test_rebuild_capital_events_index_no_capital_conn_returns_zero(events_repo):
    """An EventRepository without `capital_conn` cannot rebuild but must not crash."""
    assert events_repo.rebuild_capital_events_index() == 0


def test_rebuild_after_mirror_failure_recovers_full_index(
    events_repo_with_capital, phase2_dbs
):
    """End-to-end: a logged-but-skipped mirror failure can be recovered later."""
    # Drop the mirror table to force a write failure on the next CAPITAL_*.
    phase2_dbs.capital.execute("DROP TABLE capital_events_index")
    phase2_dbs.capital.commit()

    # Two capital events go into events.db; mirror writes are silently
    # logged-and-skipped (the table is gone). Use explicit timestamps so
    # the rebuild's `ORDER BY timestamp, event_id` is deterministic and
    # does not fall back to UUID4 tie-breaker.
    events_repo_with_capital.record_capital_deposit(amount=100.0, timestamp=1000)
    events_repo_with_capital.record_capital_withdrawal(amount=80.0, timestamp=2000)

    # Operator notices and re-creates capital.db from the schema.
    from app.database.migrations import migrate_database
    from app.core.constants import DB_CAPITAL
    migrate_database(DB_CAPITAL, phase2_dbs.capital)
    assert phase2_dbs.capital.execute(
        "SELECT COUNT(*) FROM capital_events_index"
    ).fetchone()[0] == 0

    # Rebuild reproduces the index in full from events.db (source of truth).
    written = events_repo_with_capital.rebuild_capital_events_index()
    assert written == 2
    rows = phase2_dbs.capital.execute(
        "SELECT event_type, amount FROM capital_events_index ORDER BY timestamp ASC"
    ).fetchall()
    assert [(r["event_type"], r["amount"]) for r in rows] == [
        ("CAPITAL_DEPOSIT", 100.0),
        ("CAPITAL_WITHDRAWAL", 80.0),
    ]
