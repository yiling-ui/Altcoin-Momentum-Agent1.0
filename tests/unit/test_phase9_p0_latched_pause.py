"""Phase 9 - P0 latched pause tests (Issue #9 fix-up).

Pins the Issue #9 fix-up rule: a clean reconciliation alone is NOT
sufficient to auto-resume new opens after a P0 mismatch fired. The
pause stays latched until ALL of:

  - ``has_open_p0_incident`` is False
  - ``protection_mode_active`` is False
  - ``operator_resume_confirmed`` is True
  - the most recent reconciliation pass is clean

are simultaneously satisfied. Risk Engine approval is enforced
separately by the FSM driver on the next ``submit_order`` call - this
file covers the reconciler-side state machine only.

Acceptance criteria covered:

  1. P1 mismatch: clean reconciliation clears the pause.
  2. P0 ghost-position: clean reconciliation does NOT clear the pause.
  3. P0 STOP_MISMATCH / UNATTACHED_STOP: clean reconciliation does NOT
     clear the pause.
  4. P0 fully resolved + protection exited + operator confirmation +
     clean reconciliation: pause clears, operator confirmation is
     consumed.
  5. P0 incident unresolved: pause does NOT clear even with operator
     confirmation + protection exited.
  6. protection_mode_active=True: pause does NOT clear.
  7. Reduce-only / protective-exit flow is not blocked by
     new_opens_paused (the FSM driver's protective-close path goes
     through Risk Engine with is_new_open=False, so even when
     new_opens_paused=True the exit still flows).
"""

from __future__ import annotations

import sqlite3

import pytest

from app.config.settings import get_settings
from app.core.enums import (
    Direction,
    ExecutionState,
    IncidentLevel,
    ManipulationLevel,
)
from app.core.events import EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import apply_schema, migrate_database_set
from app.database.repositories import EventRepository
from app.execution.fsm import ExecutionFSMDriver
from app.execution.models import (
    OrderIntent,
    OrderKind,
    OrderRequest,
    OrderSide,
)
from app.execution.paper_ledger import PaperLedger
from app.incidents.repository import IncidentRepository
from app.reconciliation.models import (
    LocalSnapshot,
    MismatchSeverity,
    MismatchType,
    OrderView,
    PositionView,
    RemoteSnapshot,
    StopView,
)
from app.reconciliation.reconciler import Reconciler
from app.risk.engine import RiskEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def in_memory_repo() -> EventRepository:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
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
def wired(dbs):
    """Reconciler wired to a real IncidentRepository so
    protection_mode_active is read from the canonical source."""
    repo = EventRepository(dbs.events, capital_conn=dbs.capital)
    incidents = IncidentRepository(incidents_conn=dbs.incidents, event_repo=repo)
    rec = Reconciler(event_repo=repo, protection_hook=incidents)
    return rec, incidents, repo


def _ghost_remote(symbol: str = "PEPEUSDT") -> RemoteSnapshot:
    return RemoteSnapshot(
        positions=(
            PositionView(
                position_id="exch_pos_1",
                symbol=symbol,
                direction="long",
                qty=10.0,
                entry_price=0.5,
            ),
        )
    )


# ---------------------------------------------------------------------------
# Acceptance criterion 1 - P1 clean clears pause
# ---------------------------------------------------------------------------
def test_p1_mismatch_then_clean_reconciliation_clears_pause(in_memory_repo):
    rec = Reconciler(event_repo=in_memory_repo)
    # P1: order on local, not on remote
    local_order = OrderView(order_id="o1", symbol="X", side="buy", qty=1.0)
    decision = rec.reconcile(
        local=LocalSnapshot(orders=(local_order,)),
        remote=RemoteSnapshot(),
    )
    assert decision.new_opens_paused is True
    assert all(m.severity is MismatchSeverity.P1 for m in decision.mismatches)
    assert rec.p0_latched_pause is False
    assert rec.has_open_p0_incident is False

    # Clean pass clears P1 pause without operator confirmation.
    next_decision = rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert next_decision.new_opens_paused is False
    assert rec.new_opens_paused is False
    assert rec.last_pause_reason is None


def test_equity_drift_p1_clears_on_clean(in_memory_repo):
    from app.reconciliation.models import EquitySnapshot
    from app.reconciliation.reconciler import ReconcilerConfig

    rec = Reconciler(
        event_repo=in_memory_repo,
        config=ReconcilerConfig(
            equity_drift_tolerance_abs=0.01,
            equity_drift_tolerance_rel=0.001,
        ),
    )
    rec.reconcile(
        local=LocalSnapshot(equity=EquitySnapshot(total_equity=100.0)),
        remote=RemoteSnapshot(equity=EquitySnapshot(total_equity=110.0)),
    )
    assert rec.new_opens_paused is True
    assert rec.p0_latched_pause is False
    rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert rec.new_opens_paused is False


# ---------------------------------------------------------------------------
# Acceptance criterion 2 - P0 ghost position keeps pause across clean pass
# ---------------------------------------------------------------------------
def test_p0_ghost_position_keeps_pause_across_clean_reconciliation(wired):
    rec, incidents, _ = wired
    decision = rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    assert decision.has_p0
    assert rec.new_opens_paused is True
    assert rec.p0_latched_pause is True
    assert rec.has_open_p0_incident is True
    assert rec.protection_mode_active is True

    # Clean pass without any operator action: pause MUST remain.
    next_decision = rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert len(next_decision.mismatches) == 0
    assert next_decision.new_opens_paused is True
    assert rec.new_opens_paused is True
    assert rec.p0_latched_pause is True
    assert "p0_latched" in (rec.last_pause_reason or "")


# ---------------------------------------------------------------------------
# Acceptance criterion 3 - P0 stop / unattached stop keep pause
# ---------------------------------------------------------------------------
def test_p0_unattached_stop_keeps_pause_across_clean_reconciliation(wired):
    rec, _, _ = wired
    local_stop = StopView(
        stop_order_id="stop_1",
        position_id="pos_1",
        symbol="PEPEUSDT",
        qty=1.0,
        stop_price=98.0,
        side="sell",
    )
    rec.reconcile(
        local=LocalSnapshot(stops=(local_stop,)),
        remote=RemoteSnapshot(),
    )
    assert rec.p0_latched_pause is True

    # Clean pass: pause remains.
    rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert rec.new_opens_paused is True
    assert rec.p0_latched_pause is True


def test_p0_stop_mismatch_keeps_pause_across_clean_reconciliation(wired):
    rec, _, _ = wired
    # Both sides have a stop on the same id but with diverging qty AND
    # price, which the reconciler classifies as a P0 STOP_MISMATCH.
    local_stop = StopView(
        stop_order_id="stop_1",
        position_id="pos_1",
        symbol="PEPEUSDT",
        qty=1.0,
        stop_price=98.0,
        side="sell",
    )
    remote_stop = StopView(
        stop_order_id="stop_1",
        position_id="pos_1",
        symbol="PEPEUSDT",
        qty=2.0,  # diverges
        stop_price=80.0,  # diverges
        side="sell",
    )
    decision = rec.reconcile(
        local=LocalSnapshot(stops=(local_stop,)),
        remote=RemoteSnapshot(stops=(remote_stop,)),
    )
    assert decision.has_p0
    assert rec.p0_latched_pause is True
    rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert rec.new_opens_paused is True
    assert rec.p0_latched_pause is True


# ---------------------------------------------------------------------------
# Acceptance criterion 4 - all conditions cleared -> pause clears
# ---------------------------------------------------------------------------
def test_all_conditions_satisfied_then_clean_reconciliation_clears_pause(wired):
    rec, incidents, _ = wired
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    assert rec.p0_latched_pause is True
    assert rec.protection_mode_active is True

    # Operator resolves every open P0 incident on the IncidentRepository.
    open_p0 = incidents.list_open_incidents(level=IncidentLevel.P0)
    assert len(open_p0) >= 1
    for inc in open_p0:
        incidents.resolve_incident(
            incident_id=inc.incident_id,
            resolution="operator confirmed flat",
        )
    rec.mark_p0_incidents_resolved(note="operator review")
    # Operator drives protection mode out and stages a resume.
    rec.exit_protection_mode(reason="operator_resume")
    rec.confirm_operator_resume(reason="operator_command_resume")

    # Clean pass: NOW the latch may clear.
    next_decision = rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert next_decision.new_opens_paused is False
    assert rec.new_opens_paused is False
    assert rec.p0_latched_pause is False
    assert rec.has_open_p0_incident is False
    assert rec.protection_mode_active is False
    # The operator confirmation was consumed once the latch cleared,
    # so a future P0 cannot ride a stale resume.
    assert rec.operator_resume_confirmed is False


# ---------------------------------------------------------------------------
# Acceptance criterion 5 - unresolved P0 keeps pause
# ---------------------------------------------------------------------------
def test_unresolved_p0_incident_keeps_pause_even_with_operator_confirmation(wired):
    rec, _, _ = wired
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    assert rec.has_open_p0_incident is True

    # Operator confirmation + protection-exit, but the P0 incident is
    # NOT marked resolved.
    rec.exit_protection_mode(reason="operator_resume_premature")
    rec.confirm_operator_resume(reason="operator_command_resume")
    assert rec.protection_mode_active is False
    assert rec.has_open_p0_incident is True

    # Clean pass: pause MUST remain because P0 is unresolved.
    decision = rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert decision.new_opens_paused is True
    assert rec.p0_latched_pause is True


# ---------------------------------------------------------------------------
# Acceptance criterion 6 - active protection mode keeps pause
# ---------------------------------------------------------------------------
def test_active_protection_mode_keeps_pause(wired):
    rec, incidents, _ = wired
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    # Operator marks every P0 incident resolved AND stages a resume,
    # but DOES NOT exit protection mode.
    for inc in incidents.list_open_incidents(level=IncidentLevel.P0):
        incidents.resolve_incident(
            incident_id=inc.incident_id, resolution="resolved"
        )
    rec.mark_p0_incidents_resolved()
    rec.confirm_operator_resume()
    assert rec.protection_mode_active is True

    decision = rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert decision.new_opens_paused is True
    assert rec.p0_latched_pause is True


def test_missing_operator_confirmation_keeps_pause(wired):
    rec, incidents, _ = wired
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    for inc in incidents.list_open_incidents(level=IncidentLevel.P0):
        incidents.resolve_incident(
            incident_id=inc.incident_id, resolution="resolved"
        )
    rec.mark_p0_incidents_resolved()
    rec.exit_protection_mode(reason="operator_resume")
    # No confirm_operator_resume() call.
    decision = rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert decision.new_opens_paused is True
    assert rec.p0_latched_pause is True
    assert rec.operator_resume_confirmed is False


# ---------------------------------------------------------------------------
# Acceptance criterion 7 - reduce-only / protective exit not blocked
# ---------------------------------------------------------------------------
def test_protective_exit_still_allowed_while_p0_latched(wired):
    """Even while the reconciler has latched new_opens_paused=True after
    a P0 ghost-position incident, a reduce-only / protective-close
    OrderRequest is still admissible: the FSM driver routes it through
    Risk Engine with is_new_open=False, so M3 / DATA_DEGRADED /
    REGIME / EXCHANGE_DISCONNECTED / REBASE_IN_PROGRESS gates do not
    block the exit. ``new_opens_paused`` is advisory and applies only
    to NEW_OPEN / SCALE_IN intents.
    """
    rec, incidents, repo = wired
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    assert rec.p0_latched_pause is True

    # Build a paper-mode FSM driver and submit a protective-close order
    # in the same paused state. The order MUST be accepted.
    settings = get_settings()
    risk = RiskEngine(settings=settings, event_repo=repo)
    driver = ExecutionFSMDriver(
        risk_engine=risk,
        event_repo=repo,
        paper_ledger=PaperLedger(),
        settings=settings,
        protection_hook=incidents,
    )
    req = OrderRequest(
        client_order_id="exit_p0",
        symbol="PEPEUSDT",
        side=OrderSide.SELL,
        kind=OrderKind.MARKET,
        qty=1.0,
        intent=OrderIntent.PROTECTIVE_CLOSE,
        direction=Direction.LONG,
        reduce_only=True,
    )
    result = driver.submit_order(
        req,
        manipulation_level=ManipulationLevel.M3,  # M3 must not block exits
        is_data_degraded=True,
    )
    assert result.accepted is True
    assert result.session.state is ExecutionState.ORDER_SENT


def test_kill_all_intent_admissible_while_p0_latched(wired):
    rec, incidents, repo = wired
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    settings = get_settings()
    risk = RiskEngine(settings=settings, event_repo=repo)
    driver = ExecutionFSMDriver(
        risk_engine=risk,
        event_repo=repo,
        paper_ledger=PaperLedger(),
        settings=settings,
        protection_hook=incidents,
    )
    req = OrderRequest(
        client_order_id="kill_all_p0",
        symbol="PEPEUSDT",
        side=OrderSide.SELL,
        kind=OrderKind.MARKET,
        qty=1.0,
        intent=OrderIntent.KILL_ALL,
        direction=Direction.LONG,
        reduce_only=True,
    )
    result = driver.submit_order(req)
    assert result.accepted is True
    assert result.session.request.is_new_open is False


# ---------------------------------------------------------------------------
# Resume confirmation cannot survive across multiple P0 events
# ---------------------------------------------------------------------------
def test_operator_confirmation_consumed_on_pause_clear(wired):
    rec, incidents, _ = wired
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    for inc in incidents.list_open_incidents(level=IncidentLevel.P0):
        incidents.resolve_incident(
            incident_id=inc.incident_id, resolution="resolved"
        )
    rec.mark_p0_incidents_resolved()
    rec.exit_protection_mode(reason="operator_resume")
    rec.confirm_operator_resume()

    # First clean pass clears the pause AND consumes the confirmation.
    rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert rec.operator_resume_confirmed is False

    # A second P0 lands. The previously-staged confirmation is gone -
    # the operator must re-confirm before another resume is admissible.
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    assert rec.p0_latched_pause is True

    for inc in incidents.list_open_incidents(level=IncidentLevel.P0):
        incidents.resolve_incident(
            incident_id=inc.incident_id, resolution="resolved"
        )
    rec.mark_p0_incidents_resolved()
    rec.exit_protection_mode(reason="operator_resume_2")
    decision = rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    # No fresh confirm_operator_resume(), so pause stays latched.
    assert decision.new_opens_paused is True
    assert rec.p0_latched_pause is True


# ---------------------------------------------------------------------------
# RECONCILIATION_RESOLVED event payload carries the latch state
# ---------------------------------------------------------------------------
def test_resolved_event_payload_carries_latch_state(wired):
    rec, _, repo = wired
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    resolved = repo.list_events(event_type=EventType.RECONCILIATION_RESOLVED)
    # Two passes -> two RECONCILIATION_RESOLVED events.
    assert len(resolved) == 2
    payload = resolved[-1].payload
    assert payload["new_opens_paused"] is True
    assert payload["p0_latched_pause"] is True
    assert payload["has_open_p0_incident"] is True
    assert payload["protection_mode_active"] is True
    assert payload["operator_resume_confirmed"] is False


# ---------------------------------------------------------------------------
# Without protection_hook the local fallback still works
# ---------------------------------------------------------------------------
def test_p0_latch_works_without_protection_hook(in_memory_repo):
    rec = Reconciler(event_repo=in_memory_repo)
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    assert rec.p0_latched_pause is True
    # Without a hook, protection_mode_latched is the fallback source.
    assert rec.protection_mode_active is True

    # Clean pass: pause stays.
    rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert rec.new_opens_paused is True

    # Operator drives the local fallback out + stages confirmation.
    rec.mark_p0_incidents_resolved()
    rec.exit_protection_mode(reason="operator_resume")
    rec.confirm_operator_resume()
    rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert rec.new_opens_paused is False
    assert rec.p0_latched_pause is False



# ---------------------------------------------------------------------------
# Production-safety hardening (post-audit)
# ---------------------------------------------------------------------------
def test_pre_emptive_operator_confirmation_is_invalidated_by_new_p0(wired):
    """Hole #1: a confirmation staged BEFORE any P0 (or for a previous
    P0) must NOT survive into a fresh P0 event. The operator must
    re-confirm AFTER inspecting the new P0 - otherwise a single
    pre-emptive ``confirm_operator_resume()`` could silently auto-
    resume new opens after every future P0.
    """
    rec, _, _ = wired
    # Operator confirms BEFORE any P0 lands (e.g. responding to a
    # P1 false alarm, or pre-emptively).
    rec.confirm_operator_resume(reason="pre_emptive")
    assert rec.operator_resume_confirmed is True

    # Now a P0 lands.
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    assert rec.p0_latched_pause is True
    # The pre-emptive confirmation MUST be invalidated by the new P0.
    assert rec.operator_resume_confirmed is False


def test_stale_confirmation_invalidated_when_second_p0_lands_after_first_resolved(
    wired,
):
    """Confirmation for P0 #1 must not carry forward to P0 #2 even
    when the operator has already done the work for #1 but not #2.
    """
    rec, incidents, _ = wired
    # P0 #1 fires.
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote("ALPHAUSDT"))
    # Operator does the full work for #1.
    for inc in incidents.list_open_incidents(level=IncidentLevel.P0):
        incidents.resolve_incident(
            incident_id=inc.incident_id, resolution="resolved"
        )
    rec.mark_p0_incidents_resolved()
    rec.exit_protection_mode(reason="operator_resume_1")
    rec.confirm_operator_resume(reason="operator_resume_1")
    assert rec.operator_resume_confirmed is True

    # P0 #2 fires BEFORE the latch clears (e.g. another ghost
    # position pops up on a different symbol).
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote("BETAUSDT"))
    # The stale confirmation from #1 MUST NOT survive.
    assert rec.operator_resume_confirmed is False
    assert rec.p0_latched_pause is True


def test_has_open_p0_incident_reads_from_incident_repository_when_wired(wired):
    """Hole #2: ``has_open_p0_incident`` must read from the wired
    :class:`IncidentRepository` (the on-disk source of truth), NOT
    from a process-local boolean. This prevents an operator who
    calls ``mark_p0_incidents_resolved()`` without ALSO resolving
    the incidents in the repository from prematurely clearing the
    latch.
    """
    rec, incidents, _ = wired
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    assert rec.has_open_p0_incident is True

    # Operator calls mark_p0_incidents_resolved on the reconciler
    # but does NOT actually resolve the incidents in the repository.
    rec.mark_p0_incidents_resolved()
    # Canonical source still shows open P0 -> has_open_p0_incident
    # MUST still be True.
    assert rec.has_open_p0_incident is True

    # Now genuinely resolve the incidents.
    for inc in incidents.list_open_incidents(level=IncidentLevel.P0):
        incidents.resolve_incident(
            incident_id=inc.incident_id, resolution="genuine_resolution"
        )
    # Now the canonical source is empty.
    assert rec.has_open_p0_incident is False


def test_premature_mark_p0_resolved_does_not_clear_pause_when_repo_still_open(wired):
    """End-to-end: an operator who lies about resolving the P0
    cannot use the latch-clear API to silently resume new opens.
    """
    rec, incidents, _ = wired
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    # Operator skips the actual repo resolution.
    rec.mark_p0_incidents_resolved(note="i swear i fixed it")
    rec.exit_protection_mode(reason="operator_resume")
    rec.confirm_operator_resume(reason="operator_resume")

    # Even with the local boolean cleared, the canonical source still
    # holds open P0 incidents, so the next clean pass keeps the latch.
    decision = rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    assert decision.new_opens_paused is True
    assert rec.p0_latched_pause is True
    assert rec.has_open_p0_incident is True


def test_can_clear_pause_helper_returns_true_only_when_all_conditions_met(wired):
    """Direct unit test for ``can_clear_pause_after_clean_reconciliation()``.
    """
    rec, incidents, _ = wired
    # Initially no latch -> always clearable.
    assert rec.can_clear_pause_after_clean_reconciliation() is True

    # Latch a P0.
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    # All three blockers active -> not clearable.
    assert rec.can_clear_pause_after_clean_reconciliation() is False

    # Resolve P0 only.
    for inc in incidents.list_open_incidents(level=IncidentLevel.P0):
        incidents.resolve_incident(
            incident_id=inc.incident_id, resolution="resolved"
        )
    rec.mark_p0_incidents_resolved()
    assert rec.can_clear_pause_after_clean_reconciliation() is False  # protection / confirmation

    # Add protection-mode exit.
    rec.exit_protection_mode(reason="op_resume")
    assert rec.can_clear_pause_after_clean_reconciliation() is False  # confirmation still missing

    # Add operator confirmation.
    rec.confirm_operator_resume()
    assert rec.can_clear_pause_after_clean_reconciliation() is True
