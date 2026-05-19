"""Phase 10A - Replay loaders (Issue #10 Part 1)."""

from __future__ import annotations

import pytest

from app.core.events import Event, EventType
from app.replay.loaders import (
    CAPITAL_FLOW_EVENT_TYPES,
    INCIDENT_LIFECYCLE_EVENT_TYPES,
    PAPER_LIFECYCLE_EVENT_TYPES,
    RECONCILIATION_EVENT_TYPES,
    RISK_DECISION_EVENT_TYPES,
    extract_learning_ready,
    has_learning_ready,
    load_all_events,
    load_capital_flow_events,
    load_events_for_opportunity,
    load_events_for_order,
    load_events_for_position,
    load_events_for_symbol,
    load_incident_lifecycle_events,
    load_reconciliation_events,
    load_risk_decision_events,
    load_state_transition_events,
    load_telegram_command_events,
    opportunity_id_for,
    pair_reconciliation_passes,
    stream_events,
)


# ---------------------------------------------------------------------------
# Helpers (event-stream constructors for tests)
# ---------------------------------------------------------------------------
def _ev(
    *,
    event_type: EventType,
    timestamp: int,
    source_module: str = "test",
    symbol: str | None = None,
    position_id: str | None = None,
    order_id: str | None = None,
    payload: dict | None = None,
) -> Event:
    return Event(
        event_type=event_type,
        source_module=source_module,
        symbol=symbol,
        position_id=position_id,
        order_id=order_id,
        payload=payload or {},
        timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# Event-type vocabulary tuples
# ---------------------------------------------------------------------------
def test_paper_lifecycle_event_types_complete():
    expected = {
        EventType.ORDER_SENT,
        EventType.ORDER_ACK,
        EventType.ORDER_PARTIAL_FILLED,
        EventType.ORDER_FILLED,
        EventType.ORDER_CANCELLED,
        EventType.STOP_SENT,
        EventType.STOP_CONFIRMED,
        EventType.STOP_FAILED,
        EventType.POSITION_OPENED,
        EventType.POSITION_UPDATED,
        EventType.POSITION_CLOSED,
        EventType.EXIT_TRIGGERED,
    }
    assert set(PAPER_LIFECYCLE_EVENT_TYPES) == expected


def test_capital_flow_event_types_match_phase8():
    expected = {
        EventType.CAPITAL_DEPOSIT,
        EventType.CAPITAL_WITHDRAWAL,
        EventType.PROFIT_HARVEST,
        EventType.CAPITAL_REBASE,
        EventType.RISK_BUDGET_RECALCULATED,
    }
    assert set(CAPITAL_FLOW_EVENT_TYPES) == expected


def test_incident_event_types_match_phase9():
    expected = {
        EventType.INCIDENT_OPENED,
        EventType.INCIDENT_RESOLVED,
        EventType.PROTECTION_MODE_ENTERED,
        EventType.PROTECTION_MODE_EXITED,
    }
    assert set(INCIDENT_LIFECYCLE_EVENT_TYPES) == expected


def test_reconciliation_event_types_match_phase9():
    expected = {
        EventType.RECONCILIATION_STARTED,
        EventType.RECONCILIATION_MISMATCH,
        EventType.RECONCILIATION_RESOLVED,
    }
    assert set(RECONCILIATION_EVENT_TYPES) == expected


def test_risk_event_types_complete():
    expected = {EventType.RISK_APPROVED, EventType.RISK_REJECTED}
    assert set(RISK_DECISION_EVENT_TYPES) == expected


# ---------------------------------------------------------------------------
# Generic loaders
# ---------------------------------------------------------------------------
def test_load_all_events_returns_window(events_repo):
    for ts, et in (
        (1000, EventType.ORDER_SENT),
        (2000, EventType.ORDER_ACK),
        (3000, EventType.ORDER_FILLED),
    ):
        events_repo.append_event(_ev(event_type=et, timestamp=ts))
    loaded = load_all_events(events_repo, since_ts=1500, until_ts=2500)
    assert len(loaded) == 1
    assert loaded[0].event_type is EventType.ORDER_ACK


def test_stream_events_is_lazy(events_repo):
    events_repo.append_event(
        _ev(event_type=EventType.ORDER_SENT, timestamp=1000)
    )
    events_repo.append_event(
        _ev(event_type=EventType.ORDER_FILLED, timestamp=2000)
    )
    stream = stream_events(events_repo)
    # Iterator, not a list.
    assert hasattr(stream, "__iter__")
    types = [ev.event_type for ev in stream]
    assert types == [EventType.ORDER_SENT, EventType.ORDER_FILLED]


def test_stream_events_event_types_filter(events_repo):
    events_repo.append_event(
        _ev(event_type=EventType.ORDER_SENT, timestamp=1000)
    )
    events_repo.append_event(
        _ev(event_type=EventType.ORDER_ACK, timestamp=2000)
    )
    events_repo.append_event(
        _ev(event_type=EventType.RISK_APPROVED, timestamp=3000)
    )
    out = list(
        stream_events(
            events_repo,
            event_types=(EventType.ORDER_SENT, EventType.ORDER_ACK),
        )
    )
    assert {ev.event_type for ev in out} == {
        EventType.ORDER_SENT,
        EventType.ORDER_ACK,
    }


def test_load_events_for_order_uses_order_id_column(events_repo):
    events_repo.append_event(
        _ev(
            event_type=EventType.ORDER_SENT,
            timestamp=1000,
            order_id="ord_a",
            symbol="PEPEUSDT",
        )
    )
    events_repo.append_event(
        _ev(
            event_type=EventType.ORDER_ACK,
            timestamp=2000,
            order_id="ord_b",
            symbol="PEPEUSDT",
        )
    )
    out = load_events_for_order(events_repo, client_order_id="ord_a")
    assert len(out) == 1
    assert out[0].order_id == "ord_a"


def test_load_events_for_position_uses_position_id_column(events_repo):
    events_repo.append_event(
        _ev(
            event_type=EventType.POSITION_OPENED,
            timestamp=1000,
            position_id="pos_a",
        )
    )
    events_repo.append_event(
        _ev(
            event_type=EventType.POSITION_UPDATED,
            timestamp=2000,
            position_id="pos_b",
        )
    )
    out = load_events_for_position(events_repo, position_id="pos_a")
    assert len(out) == 1


def test_load_events_for_symbol_filters_correctly(events_repo):
    for sym in ("PEPEUSDT", "BTCUSDT", "ETHUSDT"):
        events_repo.append_event(
            _ev(event_type=EventType.MARKET_SNAPSHOT, timestamp=1000, symbol=sym)
        )
    out = load_events_for_symbol(events_repo, symbol="PEPEUSDT")
    assert len(out) == 1
    assert out[0].symbol == "PEPEUSDT"


def test_load_events_for_opportunity_scans_payload(events_repo):
    events_repo.append_event(
        _ev(
            event_type=EventType.ORDER_SENT,
            timestamp=1000,
            payload={"opportunity_id": "opp_a"},
        )
    )
    events_repo.append_event(
        _ev(
            event_type=EventType.ORDER_SENT,
            timestamp=2000,
            payload={"opportunity_id": "opp_b"},
        )
    )
    events_repo.append_event(
        _ev(
            event_type=EventType.RISK_APPROVED,
            timestamp=3000,
            payload={
                "learning_ready": {
                    "opportunity": {"opportunity_id": "opp_a"}
                }
            },
        )
    )
    out = load_events_for_opportunity(
        events_repo,
        opportunity_id="opp_a",
        event_types=(EventType.ORDER_SENT, EventType.RISK_APPROVED),
    )
    assert {ev.event_type for ev in out} == {
        EventType.ORDER_SENT,
        EventType.RISK_APPROVED,
    }


# ---------------------------------------------------------------------------
# Specialised loaders
# ---------------------------------------------------------------------------
def test_load_capital_flow_events_returns_only_capital_types(events_repo):
    events_repo.append_event(
        _ev(
            event_type=EventType.CAPITAL_DEPOSIT,
            timestamp=1000,
            payload={"amount": 100.0},
        )
    )
    events_repo.append_event(
        _ev(event_type=EventType.ORDER_SENT, timestamp=2000)
    )
    events_repo.append_event(
        _ev(
            event_type=EventType.CAPITAL_REBASE,
            timestamp=3000,
            payload={"amount": 100.0, "exchange_equity": 200.0},
        )
    )
    out = load_capital_flow_events(events_repo)
    assert {ev.event_type for ev in out} == {
        EventType.CAPITAL_DEPOSIT,
        EventType.CAPITAL_REBASE,
    }


def test_load_risk_decision_events_filters_approved_rejected(events_repo):
    events_repo.append_event(
        _ev(
            event_type=EventType.RISK_APPROVED,
            timestamp=1000,
            payload={"reasons": ["paper_only_skeleton_approval"]},
        )
    )
    events_repo.append_event(
        _ev(
            event_type=EventType.RISK_REJECTED,
            timestamp=2000,
            payload={"reasons": ["manipulation_m3"]},
        )
    )
    rejected = load_risk_decision_events(events_repo, only_rejected=True)
    assert len(rejected) == 1
    assert rejected[0].event_type is EventType.RISK_REJECTED
    approved = load_risk_decision_events(events_repo, only_approved=True)
    assert len(approved) == 1
    assert approved[0].event_type is EventType.RISK_APPROVED
    both = load_risk_decision_events(events_repo)
    assert len(both) == 2


def test_load_risk_decision_events_mutex_only_flags(events_repo):
    with pytest.raises(ValueError):
        load_risk_decision_events(
            events_repo, only_approved=True, only_rejected=True
        )


def test_load_incident_lifecycle_events_optional_filter(events_repo):
    events_repo.append_event(
        _ev(
            event_type=EventType.INCIDENT_OPENED,
            timestamp=1000,
            payload={"incident_id": "inc_a", "level": "P0"},
        )
    )
    events_repo.append_event(
        _ev(
            event_type=EventType.INCIDENT_RESOLVED,
            timestamp=2000,
            payload={"incident_id": "inc_a", "resolution": "ok"},
        )
    )
    events_repo.append_event(
        _ev(
            event_type=EventType.INCIDENT_OPENED,
            timestamp=3000,
            payload={"incident_id": "inc_b", "level": "P1"},
        )
    )
    out_a = load_incident_lifecycle_events(events_repo, incident_id="inc_a")
    assert len(out_a) == 2
    assert {ev.event_type for ev in out_a} == {
        EventType.INCIDENT_OPENED,
        EventType.INCIDENT_RESOLVED,
    }
    all_events = load_incident_lifecycle_events(events_repo)
    assert len(all_events) == 3


def test_load_state_transition_events(events_repo):
    events_repo.append_event(
        _ev(
            event_type=EventType.STATE_TRANSITION,
            timestamp=1000,
            symbol="PEPEUSDT",
            payload={"from": "no_trade", "to": "observe"},
        )
    )
    events_repo.append_event(
        _ev(
            event_type=EventType.STATE_TRANSITION,
            timestamp=2000,
            symbol="BTCUSDT",
            payload={"from": "no_trade", "to": "observe"},
        )
    )
    pepe = load_state_transition_events(events_repo, symbol="PEPEUSDT")
    assert len(pepe) == 1


def test_load_telegram_command_events_filter_by_name_and_user(events_repo):
    events_repo.append_event(
        _ev(
            event_type=EventType.TELEGRAM_COMMAND_RECEIVED,
            timestamp=1000,
            payload={"name": "/status", "user_id": "u1", "args": []},
        )
    )
    events_repo.append_event(
        _ev(
            event_type=EventType.TELEGRAM_COMMAND_RECEIVED,
            timestamp=2000,
            payload={"name": "/pnl", "user_id": "u2", "args": []},
        )
    )
    by_name = load_telegram_command_events(events_repo, name="/status")
    assert len(by_name) == 1
    by_user = load_telegram_command_events(events_repo, user_id="u2")
    assert len(by_user) == 1
    none = load_telegram_command_events(events_repo, name="/missing")
    assert none == []


def test_load_reconciliation_events(events_repo):
    events_repo.append_event(
        _ev(
            event_type=EventType.RECONCILIATION_STARTED,
            timestamp=1000,
            payload={"started_at": 1000},
        )
    )
    events_repo.append_event(
        _ev(
            event_type=EventType.RECONCILIATION_RESOLVED,
            timestamp=1010,
            payload={"started_at": 1000, "finished_at": 1010},
        )
    )
    events_repo.append_event(
        _ev(event_type=EventType.ORDER_SENT, timestamp=2000)
    )
    out = load_reconciliation_events(events_repo)
    assert {ev.event_type for ev in out} == {
        EventType.RECONCILIATION_STARTED,
        EventType.RECONCILIATION_RESOLVED,
    }


# ---------------------------------------------------------------------------
# Phase 8.5 learning-ready helpers
# ---------------------------------------------------------------------------
def test_has_learning_ready_only_for_listed_event_types(events_repo):
    # MARKET_SNAPSHOT is NOT a learning-ready event type even if a
    # block landed on the payload (defensive).
    bogus = _ev(
        event_type=EventType.MARKET_SNAPSHOT,
        timestamp=1000,
        payload={"learning_ready": {"opportunity": {}}},
    )
    assert has_learning_ready(bogus) is False
    # RISK_APPROVED IS a learning-ready event type.
    real = _ev(
        event_type=EventType.RISK_APPROVED,
        timestamp=1000,
        payload={"learning_ready": {"opportunity": {"opportunity_id": "opp_a"}}},
    )
    assert has_learning_ready(real) is True


def test_extract_learning_ready_returns_shallow_copy(events_repo):
    block = {"opportunity": {"opportunity_id": "opp_a"}, "extra": {"k": 1}}
    ev = _ev(
        event_type=EventType.RISK_APPROVED,
        timestamp=1000,
        payload={"learning_ready": block},
    )
    extracted = extract_learning_ready(ev)
    assert extracted == block
    # Shallow copy: mutating the returned dict does not change the
    # source payload.
    extracted["mutated"] = True  # type: ignore[index]
    assert "mutated" not in ev.payload["learning_ready"]


def test_extract_learning_ready_returns_none_when_absent(events_repo):
    ev = _ev(event_type=EventType.RISK_APPROVED, timestamp=1000, payload={})
    assert extract_learning_ready(ev) is None


def test_opportunity_id_for_payload_top_level():
    ev = _ev(
        event_type=EventType.ORDER_SENT,
        timestamp=1000,
        payload={"opportunity_id": "opp_a"},
    )
    assert opportunity_id_for(ev) == "opp_a"


def test_opportunity_id_for_nested_in_learning_ready():
    ev = _ev(
        event_type=EventType.RISK_REJECTED,
        timestamp=1000,
        payload={
            "learning_ready": {
                "opportunity": {"opportunity_id": "opp_b"}
            }
        },
    )
    assert opportunity_id_for(ev) == "opp_b"


def test_opportunity_id_for_returns_none_when_absent():
    ev = _ev(event_type=EventType.MARKET_SNAPSHOT, timestamp=1000, payload={})
    assert opportunity_id_for(ev) is None


# ---------------------------------------------------------------------------
# Reconciliation pass pairing
# ---------------------------------------------------------------------------
def test_pair_reconciliation_passes_groups_by_started_at(events_repo):
    started = _ev(
        event_type=EventType.RECONCILIATION_STARTED,
        timestamp=1000,
        payload={"started_at": 1000},
    )
    mismatch = _ev(
        event_type=EventType.RECONCILIATION_MISMATCH,
        timestamp=1005,
        payload={
            "mismatch_type": "ghost_position",
            "severity": "P0",
        },
    )
    resolved = _ev(
        event_type=EventType.RECONCILIATION_RESOLVED,
        timestamp=1010,
        payload={
            "started_at": 1000,
            "finished_at": 1010,
            "mismatch_count": 1,
            "p0_count": 1,
            "p1_count": 0,
            "new_opens_paused": True,
        },
    )
    passes = pair_reconciliation_passes([started, mismatch, resolved])
    assert len(passes) == 1
    p = passes[0]
    assert p["started_at"] == 1000
    assert p["finished_at"] == 1010
    assert p["started"] is started
    assert p["resolved"] is resolved
    assert p["mismatches"] == (mismatch,)


def test_pair_reconciliation_passes_handles_open_pass():
    """An incomplete pass (no resolved event) is still surfaced so
    callers can see it."""
    started = _ev(
        event_type=EventType.RECONCILIATION_STARTED,
        timestamp=1000,
        payload={"started_at": 1000},
    )
    passes = pair_reconciliation_passes([started])
    assert len(passes) == 1
    assert passes[0]["resolved"] is None
    assert passes[0]["finished_at"] is None


def test_pair_reconciliation_passes_handles_multiple_passes():
    s1 = _ev(
        event_type=EventType.RECONCILIATION_STARTED,
        timestamp=1000,
        payload={"started_at": 1000},
    )
    r1 = _ev(
        event_type=EventType.RECONCILIATION_RESOLVED,
        timestamp=1010,
        payload={"started_at": 1000, "finished_at": 1010},
    )
    s2 = _ev(
        event_type=EventType.RECONCILIATION_STARTED,
        timestamp=2000,
        payload={"started_at": 2000},
    )
    r2 = _ev(
        event_type=EventType.RECONCILIATION_RESOLVED,
        timestamp=2010,
        payload={"started_at": 2000, "finished_at": 2010},
    )
    passes = pair_reconciliation_passes([s1, r1, s2, r2])
    assert len(passes) == 2
    assert passes[0]["started_at"] == 1000
    assert passes[1]["started_at"] == 2000
