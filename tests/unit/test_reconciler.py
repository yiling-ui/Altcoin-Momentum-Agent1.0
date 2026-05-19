"""Phase 9 - Reconciler tests (Spec §31)."""

from __future__ import annotations

import sqlite3

import pytest

from app.core.enums import ExchangeConnectionState, IncidentLevel
from app.core.events import EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.execution.paper_ledger import PaperLedger, PaperPosition, PaperStop
from app.execution.models import OrderSide
from app.incidents.repository import IncidentRepository
from app.reconciliation.models import (
    EquitySnapshot,
    LinkHealth,
    LocalSnapshot,
    Mismatch,
    MismatchSeverity,
    MismatchType,
    OrderView,
    PositionView,
    RemoteSnapshot,
    StopView,
    local_snapshot_from_paper_ledger,
    remote_snapshot_from_paper_ledger,
)
from app.reconciliation.reconciler import Reconciler, ReconcilerConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def repo():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from app.database.migrations import apply_schema

    apply_schema(conn)
    return EventRepository(conn)


@pytest.fixture
def dbs(tmp_path):
    sqlite_dir = tmp_path / "sqlite"
    dbs = DatabaseSet.open(sqlite_dir, wal=True, databases=PHASE2_DATABASES)
    migrate_database_set(dbs)
    try:
        yield dbs
    finally:
        dbs.close()


@pytest.fixture
def incidents(dbs):
    repo = EventRepository(dbs.events)
    return IncidentRepository(incidents_conn=dbs.incidents, event_repo=repo), repo


def _link(connected: bool = True) -> LinkHealth:
    state = (
        ExchangeConnectionState.CONNECTED
        if connected
        else ExchangeConnectionState.DEGRADED
    )
    return LinkHealth(websocket_state=state, rest_state=state)


# ---------------------------------------------------------------------------
# Clean reconciliation
# ---------------------------------------------------------------------------
def test_clean_reconciliation_emits_started_and_resolved_only(repo):
    rec = Reconciler(event_repo=repo)
    decision = rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert decision.matched
    assert not decision.new_opens_paused
    assert not decision.has_p0
    assert decision.mismatches == ()
    types = [e.event_type for e in repo.list_events()]
    assert EventType.RECONCILIATION_STARTED in types
    assert EventType.RECONCILIATION_RESOLVED in types
    assert EventType.RECONCILIATION_MISMATCH not in types


def test_paper_ledger_helpers_round_trip_clean(repo):
    rec = Reconciler(event_repo=repo)
    ledger = PaperLedger(initial_equity=100.0)
    pos = PaperPosition(
        position_id="pos_1",
        symbol="PEPEUSDT",
        direction="long",
        qty=1.0,
        entry_price=100.0,
        stop_price=98.0,
        stop_confirmed=True,
    )
    ledger.open_position(pos)
    stop = PaperStop(
        stop_order_id="stop_1",
        position_id="pos_1",
        symbol="PEPEUSDT",
        side=OrderSide.SELL,
        qty=1.0,
        stop_price=98.0,
        reduce_only=True,
        timestamp=0,
    )
    ledger.record_stop(stop)
    local = local_snapshot_from_paper_ledger(ledger)
    remote = remote_snapshot_from_paper_ledger(ledger)
    decision = rec.reconcile(local=local, remote=remote)
    assert decision.matched


# ---------------------------------------------------------------------------
# Ghost position - P0
# ---------------------------------------------------------------------------
def test_ghost_position_fires_p0_and_pauses_new_opens(repo):
    rec = Reconciler(event_repo=repo)
    remote_pos = PositionView(
        position_id="exch_pos_1",
        symbol="PEPEUSDT",
        direction="long",
        qty=10.0,
        entry_price=0.5,
    )
    decision = rec.reconcile(
        local=LocalSnapshot(),
        remote=RemoteSnapshot(positions=(remote_pos,)),
    )
    assert decision.has_p0
    assert decision.new_opens_paused
    types = {m.mismatch_type for m in decision.mismatches}
    assert MismatchType.POSITION_MISMATCH in types
    assert MismatchType.GHOST_POSITION in types


def test_ghost_position_opens_p0_incident_via_hook(incidents):
    repo_obj, ev_repo = incidents
    rec = Reconciler(event_repo=ev_repo, protection_hook=repo_obj)
    remote_pos = PositionView(
        position_id="exch_pos_1",
        symbol="PEPEUSDT",
        direction="long",
        qty=10.0,
        entry_price=0.5,
    )
    decision = rec.reconcile(
        local=LocalSnapshot(),
        remote=RemoteSnapshot(positions=(remote_pos,)),
    )
    assert decision.has_p0
    assert decision.protection_mode_entered is True
    assert repo_obj.in_protection_mode is True
    open_p0 = repo_obj.list_open_incidents(level=IncidentLevel.P0)
    assert len(open_p0) >= 1
    assert any(i.symbol == "PEPEUSDT" for i in open_p0)


# ---------------------------------------------------------------------------
# Missing remote position - P0
# ---------------------------------------------------------------------------
def test_missing_remote_position_fires_p0(repo):
    rec = Reconciler(event_repo=repo)
    local_pos = PositionView(
        position_id="local_pos_1",
        symbol="PEPEUSDT",
        direction="long",
        qty=1.0,
        entry_price=100.0,
    )
    decision = rec.reconcile(
        local=LocalSnapshot(positions=(local_pos,)),
        remote=RemoteSnapshot(),
    )
    types = {m.mismatch_type for m in decision.mismatches}
    assert MismatchType.MISSING_REMOTE_POSITION in types
    assert decision.has_p0


# ---------------------------------------------------------------------------
# Position qty / direction disagreement
# ---------------------------------------------------------------------------
def test_position_qty_disagreement_fires_p0(repo):
    rec = Reconciler(event_repo=repo)
    local_pos = PositionView(
        position_id="pos_1",
        symbol="PEPEUSDT",
        direction="long",
        qty=1.0,
        entry_price=100.0,
    )
    remote_pos = PositionView(
        position_id="pos_1",
        symbol="PEPEUSDT",
        direction="long",
        qty=2.0,  # disagreement
        entry_price=100.0,
    )
    decision = rec.reconcile(
        local=LocalSnapshot(positions=(local_pos,)),
        remote=RemoteSnapshot(positions=(remote_pos,)),
    )
    assert decision.has_p0


# ---------------------------------------------------------------------------
# Unattached stop - P0
# ---------------------------------------------------------------------------
def test_unattached_stop_fires_p0_when_local_has_remote_doesnt(repo):
    rec = Reconciler(event_repo=repo)
    local_stop = StopView(
        stop_order_id="stop_1",
        position_id="pos_1",
        symbol="PEPEUSDT",
        qty=1.0,
        stop_price=98.0,
        side="sell",
    )
    decision = rec.reconcile(
        local=LocalSnapshot(stops=(local_stop,)),
        remote=RemoteSnapshot(),
    )
    types = {m.mismatch_type for m in decision.mismatches}
    assert MismatchType.UNATTACHED_STOP in types
    assert decision.has_p0


# ---------------------------------------------------------------------------
# Order mismatches - P1
# ---------------------------------------------------------------------------
def test_order_local_only_fires_p1(repo):
    rec = Reconciler(event_repo=repo)
    local_order = OrderView(
        order_id="ord_1",
        symbol="PEPEUSDT",
        side="buy",
        qty=1.0,
    )
    decision = rec.reconcile(
        local=LocalSnapshot(orders=(local_order,)),
        remote=RemoteSnapshot(),
    )
    assert any(
        m.mismatch_type is MismatchType.ORDER_MISMATCH
        and m.severity is MismatchSeverity.P1
        for m in decision.mismatches
    )
    assert decision.new_opens_paused


def test_order_qty_disagreement_fires_mismatch(repo):
    rec = Reconciler(event_repo=repo)
    lo = OrderView(order_id="o1", symbol="X", side="buy", qty=1.0, filled_qty=0.5)
    ro = OrderView(order_id="o1", symbol="X", side="buy", qty=2.0, filled_qty=0.5)
    decision = rec.reconcile(
        local=LocalSnapshot(orders=(lo,)),
        remote=RemoteSnapshot(orders=(ro,)),
    )
    assert decision.mismatches
    assert any(
        m.mismatch_type is MismatchType.ORDER_MISMATCH for m in decision.mismatches
    )


# ---------------------------------------------------------------------------
# Equity drift
# ---------------------------------------------------------------------------
def test_equity_within_tolerance_does_not_fire(repo):
    rec = Reconciler(event_repo=repo)
    local = LocalSnapshot(equity=EquitySnapshot(total_equity=100.0))
    remote = RemoteSnapshot(equity=EquitySnapshot(total_equity=100.005))  # 0.005 < 0.01 abs
    decision = rec.reconcile(local=local, remote=remote)
    assert decision.matched


def test_equity_drift_above_tolerance_fires_p1(repo):
    rec = Reconciler(event_repo=repo, config=ReconcilerConfig(
        equity_drift_tolerance_abs=0.01,
        equity_drift_tolerance_rel=0.001,  # tighten so the diff fires
    ))
    local = LocalSnapshot(equity=EquitySnapshot(total_equity=100.0))
    remote = RemoteSnapshot(equity=EquitySnapshot(total_equity=110.0))
    decision = rec.reconcile(local=local, remote=remote)
    assert any(
        m.mismatch_type is MismatchType.EQUITY_DRIFT
        and m.severity is MismatchSeverity.P1
        for m in decision.mismatches
    )
    assert decision.new_opens_paused


# ---------------------------------------------------------------------------
# WS / REST conflict
# ---------------------------------------------------------------------------
def test_ws_rest_conflict_fires_p1(repo):
    rec = Reconciler(event_repo=repo)
    link = LinkHealth(
        websocket_state=ExchangeConnectionState.DEGRADED,
        rest_state=ExchangeConnectionState.CONNECTED,
    )
    decision = rec.reconcile(
        local=LocalSnapshot(link=link),
        remote=RemoteSnapshot(link=link),
    )
    assert any(
        m.mismatch_type is MismatchType.WS_REST_CONFLICT for m in decision.mismatches
    )
    assert decision.new_opens_paused


def test_ws_rest_both_connected_does_not_fire(repo):
    rec = Reconciler(event_repo=repo)
    link = _link(connected=True)
    decision = rec.reconcile(
        local=LocalSnapshot(link=link),
        remote=RemoteSnapshot(link=link),
    )
    assert decision.matched


# ---------------------------------------------------------------------------
# new_opens_paused state machine
# ---------------------------------------------------------------------------
def test_new_opens_paused_clears_on_clean_reconciliation(repo):
    rec = Reconciler(event_repo=repo)
    # First pass: bad
    rec.reconcile(
        local=LocalSnapshot(),
        remote=RemoteSnapshot(positions=(
            PositionView(
                position_id="exch_1",
                symbol="X",
                direction="long",
                qty=1.0,
                entry_price=10.0,
            ),
        )),
    )
    assert rec.new_opens_paused is True
    # Second pass: clean
    rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert rec.new_opens_paused is False


# ---------------------------------------------------------------------------
# Event payload contract
# ---------------------------------------------------------------------------
def test_reconciliation_resolved_payload_carries_counts(repo):
    rec = Reconciler(event_repo=repo)
    rec.reconcile(
        local=LocalSnapshot(),
        remote=RemoteSnapshot(positions=(
            PositionView(
                position_id="exch_1",
                symbol="X",
                direction="long",
                qty=1.0,
                entry_price=10.0,
            ),
        )),
    )
    resolved = repo.list_events(event_type=EventType.RECONCILIATION_RESOLVED)
    assert len(resolved) == 1
    payload = resolved[0].payload
    assert payload["mismatch_count"] >= 1
    assert payload["p0_count"] >= 1
    assert payload["new_opens_paused"] is True


def test_reconciliation_mismatch_event_per_mismatch(repo):
    rec = Reconciler(event_repo=repo)
    rec.reconcile(
        local=LocalSnapshot(orders=(
            OrderView(order_id="o1", symbol="X", side="buy", qty=1),
            OrderView(order_id="o2", symbol="X", side="buy", qty=1),
        )),
        remote=RemoteSnapshot(),
    )
    mismatches = repo.list_events(event_type=EventType.RECONCILIATION_MISMATCH)
    assert len(mismatches) == 2
