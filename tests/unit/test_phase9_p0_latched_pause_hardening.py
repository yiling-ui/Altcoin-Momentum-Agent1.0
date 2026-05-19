"""Phase 9 - P0 latched-pause production-safety hardening (post-merge).

Pins two safety holes that were left open by PR #21:

Hole #1 - Stale operator confirmation could survive a new P0
============================================================
A confirmation staged BEFORE any P0 (or for a previous P0) was NOT
invalidated when a fresh P0 latched. An operator could pre-emptively
call ``confirm_operator_resume()`` and have a future P0 silently
auto-resume on the next clean pass without a fresh acknowledgement.

Hole #2 - ``has_open_p0_incident`` was decoupled from on-disk truth
==================================================================
The property tracked only P0s opened by THIS reconciler in THIS
process - decoupled from the canonical
:meth:`IncidentRepository.list_open_incidents`. An operator who
called ``mark_p0_incidents_resolved()`` locally without ALSO
resolving the incidents in the repository could prematurely clear
the latch.

Both holes are now closed; this file is the regression suite.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.core.enums import IncidentLevel
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import apply_schema, migrate_database_set
from app.database.repositories import EventRepository
from app.incidents.repository import IncidentRepository
from app.reconciliation.models import (
    LocalSnapshot,
    PositionView,
    RemoteSnapshot,
)
from app.reconciliation.reconciler import Reconciler


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
# Hole #1 - stale operator confirmation invalidated by new P0
# ---------------------------------------------------------------------------
def test_pre_emptive_operator_confirmation_is_invalidated_by_new_p0(wired):
    """A confirmation staged BEFORE any P0 ever fires must not survive
    into a fresh P0 event. The operator has to re-confirm AFTER they
    have inspected the new P0.
    """
    rec, _, _ = wired
    # Operator confirms before any P0 lands (e.g. responding to a P1
    # false alarm, or pre-emptively).
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
    when the operator has already done the work for #1 but a fresh P0
    fires before the latch clears.
    """
    rec, incidents, _ = wired
    # P0 #1 fires.
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote("ALPHAUSDT"))
    # Operator does the full work for #1 - resolve in repo + confirm.
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


# ---------------------------------------------------------------------------
# Hole #2 - has_open_p0_incident reads canonical IncidentRepository
# ---------------------------------------------------------------------------
def test_has_open_p0_incident_reads_from_incident_repository_when_wired(wired):
    """The property MUST read from the wired ``IncidentRepository``
    (the on-disk source of truth), NOT from a process-local boolean.
    This prevents an operator who calls ``mark_p0_incidents_resolved()``
    without ALSO resolving the incidents in the repository from
    prematurely clearing the latch.
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

    # Now genuinely resolve the incidents in the repository.
    for inc in incidents.list_open_incidents(level=IncidentLevel.P0):
        incidents.resolve_incident(
            incident_id=inc.incident_id, resolution="genuine_resolution"
        )
    # Now the canonical source is empty.
    assert rec.has_open_p0_incident is False


def test_premature_mark_p0_resolved_does_not_clear_pause_when_repo_still_open(wired):
    """End-to-end: an operator who lies about resolving the P0 cannot
    use the latch-clear API to silently resume new opens.
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

    Validates the cross-product of the three conditions: open P0,
    protection mode, operator confirmation. Only when all three
    blockers are simultaneously cleared does the helper return True.
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
    # protection / confirmation still missing.
    assert rec.can_clear_pause_after_clean_reconciliation() is False

    # Add protection-mode exit.
    rec.exit_protection_mode(reason="op_resume")
    # confirmation still missing.
    assert rec.can_clear_pause_after_clean_reconciliation() is False

    # Add operator confirmation.
    rec.confirm_operator_resume()
    assert rec.can_clear_pause_after_clean_reconciliation() is True
