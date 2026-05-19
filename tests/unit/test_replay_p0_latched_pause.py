"""Phase 10A - P0 latched-pause invariant verifier (Issue #10 Part 1).

Phase 9 fix-up rule (PR #22): after a P0 mismatch lands, the
``new_opens_paused`` flag is **latched**. A subsequent CLEAN
reconciliation alone must NOT auto-clear the pause - the operator
must also resolve the incident in :class:`IncidentRepository`, exit
protection mode, and confirm resume. Phase 10A's
:meth:`ReplayEngine.verify_p0_latched_pause_invariant` audits the
event trail for any pass that violates this rule.
"""

from __future__ import annotations

import pytest

from app.core.enums import IncidentLevel
from app.core.events import Event, EventType
from app.database.connection import DatabaseSet
from app.database.repositories import EventRepository
from app.incidents.repository import IncidentRepository
from app.reconciliation.models import (
    LocalSnapshot,
    PositionView,
    RemoteSnapshot,
)
from app.reconciliation.reconciler import Reconciler
from app.replay import ReplayEngine, P0LatchedPauseInvariantReport


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def wired(phase2_dbs: DatabaseSet):
    """Phase 9 reconciler + IncidentRepository + EventRepository wired."""
    repo = EventRepository(phase2_dbs.events, capital_conn=phase2_dbs.capital)
    incidents = IncidentRepository(
        incidents_conn=phase2_dbs.incidents, event_repo=repo
    )
    rec = Reconciler(event_repo=repo, protection_hook=incidents)
    return rec, incidents, repo


def _ghost_remote(symbol: str = "PEPEUSDT") -> RemoteSnapshot:
    """Snapshot that triggers a P0 ghost-position mismatch."""
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
# Held invariants (clean event trails)
# ---------------------------------------------------------------------------
def test_invariant_holds_when_no_reconciliation_passes(wired):
    """An empty event trail trivially satisfies the invariant."""
    _, _, repo = wired
    engine = ReplayEngine(event_repo=repo)
    report = engine.verify_p0_latched_pause_invariant()
    assert isinstance(report, P0LatchedPauseInvariantReport)
    assert report.held is True
    assert report.pass_count == 0


def test_invariant_holds_after_only_clean_passes(wired):
    """Repeated clean passes never violate the invariant."""
    rec, _, repo = wired
    rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    engine = ReplayEngine(event_repo=repo)
    report = engine.verify_p0_latched_pause_invariant()
    assert report.held is True
    assert report.pass_count == 2


def test_invariant_holds_when_p0_latched_and_pause_kept(wired):
    """A P0 fires + every subsequent clean pass keeps the pause."""
    rec, _, repo = wired
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    # Subsequent clean passes WITHOUT operator resume / incident
    # resolution / protection exit must keep the pause latched.
    rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())
    rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())

    engine = ReplayEngine(event_repo=repo)
    report = engine.verify_p0_latched_pause_invariant()
    assert report.held is True
    assert report.pass_count == 3
    assert len(report.p0_latched_passes) >= 1
    assert report.every_clean_pass_with_open_p0_kept_pause is True


def test_invariant_holds_after_full_resume_protocol(wired):
    """Once operator resolved + protection exited + confirmed,
    the next clean pass legitimately clears the pause."""
    rec, incidents, repo = wired
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    # Operator does the full work.
    for inc in incidents.list_open_incidents(level=IncidentLevel.P0):
        incidents.resolve_incident(
            incident_id=inc.incident_id, resolution="operator_resolved"
        )
    rec.mark_p0_incidents_resolved()
    rec.exit_protection_mode(reason="operator_resume")
    rec.confirm_operator_resume(reason="operator_resume")
    rec.reconcile(local=LocalSnapshot(), remote=RemoteSnapshot())

    engine = ReplayEngine(event_repo=repo)
    report = engine.verify_p0_latched_pause_invariant()
    assert report.held is True


# ---------------------------------------------------------------------------
# Violations (synthesised event trails)
# ---------------------------------------------------------------------------
def _emit_synthetic_resolved(
    repo: EventRepository,
    *,
    timestamp: int,
    started_at: int,
    new_opens_paused: bool,
    p0_latched_pause: bool,
    has_open_p0_incident: bool,
    protection_mode_active: bool,
    operator_resume_confirmed: bool,
    mismatch_count: int = 0,
    p0_count: int = 0,
) -> None:
    """Write a synthetic RECONCILIATION_STARTED + RESOLVED pair."""
    repo.append_event(
        Event(
            event_type=EventType.RECONCILIATION_STARTED,
            source_module="reconciliation",
            payload={"started_at": started_at},
            timestamp=started_at,
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.RECONCILIATION_RESOLVED,
            source_module="reconciliation",
            payload={
                "started_at": started_at,
                "finished_at": timestamp,
                "mismatch_count": mismatch_count,
                "p0_count": p0_count,
                "p1_count": 0,
                "new_opens_paused": new_opens_paused,
                "p0_latched_pause": p0_latched_pause,
                "has_open_p0_incident": has_open_p0_incident,
                "protection_mode_active": protection_mode_active,
                "operator_resume_confirmed": operator_resume_confirmed,
                "protection_mode_entered": False,
                "incident_ids": [],
                "notes": [],
            },
            timestamp=timestamp,
        )
    )


def test_invariant_flags_violation_when_open_p0_but_unpaused(wired):
    """A clean pass that reports has_open_p0_incident=True AND
    new_opens_paused=False is a violation."""
    _, _, repo = wired
    _emit_synthetic_resolved(
        repo,
        timestamp=1000,
        started_at=900,
        new_opens_paused=False,
        p0_latched_pause=False,
        has_open_p0_incident=True,
        protection_mode_active=False,
        operator_resume_confirmed=False,
        mismatch_count=0,
    )
    engine = ReplayEngine(event_repo=repo)
    report = engine.verify_p0_latched_pause_invariant()
    assert report.held is False
    assert any(
        v["rule"] == "blocker_active_but_unpaused" for v in report.violations
    )
    assert report.every_clean_pass_with_open_p0_kept_pause is False


def test_invariant_flags_violation_when_protection_active_but_unpaused(wired):
    _, _, repo = wired
    _emit_synthetic_resolved(
        repo,
        timestamp=1000,
        started_at=900,
        new_opens_paused=False,
        p0_latched_pause=False,
        has_open_p0_incident=False,
        protection_mode_active=True,
        operator_resume_confirmed=False,
        mismatch_count=0,
    )
    engine = ReplayEngine(event_repo=repo)
    report = engine.verify_p0_latched_pause_invariant()
    assert report.held is False
    rules = {v["rule"] for v in report.violations}
    assert "blocker_active_but_unpaused" in rules


def test_invariant_flags_violation_when_latched_but_unpaused(wired):
    """``p0_latched_pause=True`` with any blocker active and
    ``new_opens_paused=False`` is a violation."""
    _, _, repo = wired
    _emit_synthetic_resolved(
        repo,
        timestamp=1000,
        started_at=900,
        new_opens_paused=False,
        p0_latched_pause=True,
        has_open_p0_incident=False,
        protection_mode_active=False,
        operator_resume_confirmed=False,
        mismatch_count=0,
    )
    engine = ReplayEngine(event_repo=repo)
    report = engine.verify_p0_latched_pause_invariant()
    assert report.held is False
    rules = {v["rule"] for v in report.violations}
    assert "latched_but_unpaused" in rules


def test_invariant_payload_round_trips_to_json(wired):
    import json

    rec, _, repo = wired
    rec.reconcile(local=LocalSnapshot(), remote=_ghost_remote())
    engine = ReplayEngine(event_repo=repo)
    report = engine.verify_p0_latched_pause_invariant()
    payload = report.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)
    assert decoded["held"] is report.held
    assert decoded["pass_count"] == report.pass_count


# ---------------------------------------------------------------------------
# Window filters
# ---------------------------------------------------------------------------
def test_invariant_window_filters_passes(wired):
    _, _, repo = wired
    # Pass A at t=1000 - clean.
    _emit_synthetic_resolved(
        repo,
        timestamp=1000,
        started_at=900,
        new_opens_paused=False,
        p0_latched_pause=False,
        has_open_p0_incident=False,
        protection_mode_active=False,
        operator_resume_confirmed=False,
    )
    # Pass B at t=5000 - latched + unpaused (would be a violation).
    _emit_synthetic_resolved(
        repo,
        timestamp=5000,
        started_at=4900,
        new_opens_paused=False,
        p0_latched_pause=True,
        has_open_p0_incident=True,
        protection_mode_active=False,
        operator_resume_confirmed=False,
    )

    engine = ReplayEngine(event_repo=repo)
    # Window before pass B: invariant holds.
    report_before = engine.verify_p0_latched_pause_invariant(until_ts=2000)
    assert report_before.held is True
    # Window including pass B: invariant violated.
    report_full = engine.verify_p0_latched_pause_invariant()
    assert report_full.held is False
