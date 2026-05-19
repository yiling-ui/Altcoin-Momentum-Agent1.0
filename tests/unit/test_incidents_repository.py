"""Phase 9 - IncidentRepository tests (Spec §38)."""

from __future__ import annotations

import sqlite3

import pytest

from app.core.enums import IncidentLevel
from app.core.events import EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.incidents.models import (
    INCIDENT_STATE_OPENED,
    INCIDENT_STATE_RESOLVED,
    INCIDENT_STATE_UPDATED,
)
from app.incidents.repository import IncidentRepository


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
def repo(dbs) -> EventRepository:
    return EventRepository(dbs.events, capital_conn=dbs.capital)


@pytest.fixture
def incidents(dbs, repo) -> IncidentRepository:
    return IncidentRepository(incidents_conn=dbs.incidents, event_repo=repo)


def test_open_incident_writes_row_and_log_and_event(incidents, repo, dbs):
    incident_id = incidents.open_incident(
        level=IncidentLevel.P0,
        title="ghost_position",
        description="exchange has open position, local does not",
        source_module="reconciler",
        symbol="PEPEUSDT",
        position_id=None,
        payload={"qty": 1000.0},
    )
    assert incident_id.startswith("inc_")
    assert incidents.opened_count == 1

    # incidents row landed
    row = dbs.incidents.execute(
        "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
    ).fetchone()
    assert row["level"] == "P0"
    assert row["title"] == "ghost_position"

    # one incident_log row, state=opened
    logs = dbs.incidents.execute(
        "SELECT * FROM incident_log WHERE incident_id = ?", (incident_id,)
    ).fetchall()
    assert len(logs) == 1
    assert logs[0]["state"] == INCIDENT_STATE_OPENED

    # INCIDENT_OPENED event landed
    events = repo.list_events(event_type=EventType.INCIDENT_OPENED)
    assert len(events) == 1
    assert events[0].payload["incident_id"] == incident_id
    assert events[0].payload["level"] == "P0"
    assert events[0].payload["qty"] == 1000.0


def test_update_incident_appends_log_row_only(incidents, dbs):
    incident_id = incidents.open_incident(
        level=IncidentLevel.P1,
        title="order_drift",
        description="qty disagreement",
        source_module="reconciler",
    )
    incidents.update_incident(
        incident_id=incident_id, note="qty resolved by re-poll", payload={"new_qty": 1.0}
    )
    log = incidents.list_log_for(incident_id)
    assert len(log) == 2
    assert log[0].state == INCIDENT_STATE_OPENED
    assert log[1].state == INCIDENT_STATE_UPDATED
    assert log[1].note == "qty resolved by re-poll"


def test_resolve_incident_updates_row_and_writes_event(incidents, repo, dbs):
    incident_id = incidents.open_incident(
        level=IncidentLevel.P0,
        title="stop_failed",
        description="exchange rejected stop",
        source_module="execution_fsm",
        position_id="pos_x",
    )
    incidents.resolve_incident(
        incident_id=incident_id,
        resolution="position flattened by protective close",
        position_id="pos_x",
    )
    assert incidents.resolved_count == 1
    row = dbs.incidents.execute(
        "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
    ).fetchone()
    assert row["resolved_at"] is not None
    assert row["resolution"] == "position flattened by protective close"
    log = incidents.list_log_for(incident_id)
    assert any(r.state == INCIDENT_STATE_RESOLVED for r in log)
    events = repo.list_events(event_type=EventType.INCIDENT_RESOLVED)
    assert len(events) == 1
    assert events[0].payload["incident_id"] == incident_id


def test_get_incident_round_trip(incidents):
    incident_id = incidents.open_incident(
        level=IncidentLevel.P2,
        title="warning",
        description="",
        source_module="reconciler",
    )
    inc = incidents.get_incident(incident_id)
    assert inc is not None
    assert inc.level is IncidentLevel.P2
    assert inc.resolved_at is None
    assert incidents.get_incident("missing") is None


def test_list_open_incidents_filters_by_level_and_symbol(incidents):
    a = incidents.open_incident(
        level=IncidentLevel.P0,
        title="a",
        description="",
        source_module="reconciler",
        symbol="BTCUSDT",
    )
    b = incidents.open_incident(
        level=IncidentLevel.P1,
        title="b",
        description="",
        source_module="reconciler",
        symbol="ETHUSDT",
    )
    incidents.resolve_incident(incident_id=a, resolution="ok")

    open_only = incidents.list_open_incidents()
    assert {i.incident_id for i in open_only} == {b}

    p1_only = incidents.list_open_incidents(level=IncidentLevel.P1)
    assert {i.incident_id for i in p1_only} == {b}

    eth_only = incidents.list_open_incidents(symbol="ETHUSDT")
    assert {i.incident_id for i in eth_only} == {b}


def test_enter_protection_mode_emits_event_and_sets_flag(incidents, repo):
    incidents.enter_protection_mode(
        reason="reconciliation_p0", payload={"incident_count": 1}
    )
    assert incidents.in_protection_mode is True
    assert incidents.protection_entered_count == 1
    pme = repo.list_events(event_type=EventType.PROTECTION_MODE_ENTERED)
    assert len(pme) == 1
    assert pme[0].payload["reason"] == "reconciliation_p0"
    assert pme[0].payload["incident_count"] == 1


def test_exit_protection_mode_emits_event_and_clears_flag(incidents, repo):
    incidents.enter_protection_mode(reason="r1")
    incidents.exit_protection_mode(reason="resume")
    assert incidents.in_protection_mode is False
    assert incidents.protection_exited_count == 1
    pmx = repo.list_events(event_type=EventType.PROTECTION_MODE_EXITED)
    assert len(pmx) == 1


def test_repository_implements_protection_hook_protocol(incidents):
    """Static check: IncidentRepository satisfies the ProtectionHook
    typing.Protocol that ExecutionFSMDriver and Reconciler depend on."""
    from app.incidents.repository import ProtectionHook

    # Protocol membership is structural so isinstance works only when
    # @runtime_checkable is set; instead, we just verify the surface.
    for method in ("open_incident", "enter_protection_mode", "exit_protection_mode"):
        assert callable(getattr(incidents, method))
