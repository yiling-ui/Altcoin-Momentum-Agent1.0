"""Phase 11B - incident drill harness tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config.settings import Settings, get_settings, load_settings
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.incidents.repository import IncidentRepository
from app.paper_run.config import DEFAULT_INCIDENT_DRILLS
from app.paper_run.incident_drill import (
    DrillStatus,
    IncidentDrillHarness,
    IncidentDrillResult,
)


@pytest.fixture()
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AMA_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    settings = load_settings()
    settings.sqlite_dir.mkdir(parents=True, exist_ok=True)
    dbs = DatabaseSet.open(
        settings.sqlite_dir, wal=True, databases=PHASE2_DATABASES
    )
    migrate_database_set(dbs)
    repo = EventRepository(dbs.events, capital_conn=dbs.capital)
    incidents = IncidentRepository(
        incidents_conn=dbs.incidents, event_repo=repo
    )
    yield IncidentDrillHarness(
        settings=settings, event_repo=repo, incident_repo=incidents
    )
    dbs.close()
    get_settings.cache_clear()


def test_run_drill_handles_unknown_name(harness: IncidentDrillHarness):
    result = harness.run_drill("not_a_real_drill")
    assert isinstance(result, IncidentDrillResult)
    assert result.status is DrillStatus.SKIPPED
    assert result.failure_reason == "unknown_drill"


def test_drill_stop_unconfirmed(harness: IncidentDrillHarness):
    result = harness.drill_stop_unconfirmed()
    assert result.passed is True
    assert any("stop_unconfirmed" in obs for obs in result.observations)


def test_drill_unknown_position(harness: IncidentDrillHarness):
    result = harness.drill_unknown_position()
    assert result.passed is True
    assert any("unknown_position" in obs for obs in result.observations)


def test_drill_data_degraded(harness: IncidentDrillHarness):
    result = harness.drill_data_degraded()
    assert result.passed is True


def test_drill_p0_ghost_position(harness: IncidentDrillHarness):
    result = harness.drill_p0_ghost_position()
    assert result.passed is True
    # The drill confirms the latch clears AFTER operator confirm.
    obs = ", ".join(result.observations)
    assert "p0_latched_pause_after_resume=False" in obs


def test_drill_p0_unattached_stop(harness: IncidentDrillHarness):
    result = harness.drill_p0_unattached_stop()
    assert result.passed is True
    obs = ", ".join(result.observations)
    assert "unattached_stop" in obs


def test_drill_rebase_in_progress(harness: IncidentDrillHarness):
    result = harness.drill_rebase_in_progress()
    assert result.passed is True
    obs = ", ".join(result.observations)
    assert "rebase_in_progress" in obs
    assert "protective_exit_approved" in obs


def test_drill_telegram_export_failure(harness: IncidentDrillHarness):
    result = harness.drill_telegram_export_failure()
    assert result.passed is True
    obs = ", ".join(result.observations)
    assert "command_status=execution_error" in obs


def test_drill_llm_degraded(harness: IncidentDrillHarness):
    result = harness.drill_llm_degraded()
    assert result.passed is True
    obs = ", ".join(result.observations)
    assert "llm_disabled" in obs
    assert "fake_client_calls=0" in obs


def test_run_all_default_drills_pass(harness: IncidentDrillHarness):
    """Running every drill in the default list against a fresh
    EventRepository must produce all-pass results."""
    results = harness.run_drills(DEFAULT_INCIDENT_DRILLS)
    assert len(results) == len(DEFAULT_INCIDENT_DRILLS)
    failed = [r for r in results if not r.passed]
    assert not failed, f"Failed drills: {[r.name for r in failed]}"


def test_drill_results_are_idempotent(harness: IncidentDrillHarness):
    """The drills must be safe to re-run against the same harness."""
    first = harness.run_drills(DEFAULT_INCIDENT_DRILLS)
    second = harness.run_drills(DEFAULT_INCIDENT_DRILLS)
    assert all(r.passed for r in first)
    assert all(r.passed for r in second)


def test_drill_result_to_payload_is_json_safe(harness: IncidentDrillHarness):
    result = harness.drill_stop_unconfirmed()
    import json

    payload = result.to_payload()
    serialised = json.dumps(payload)
    assert "stop_unconfirmed" in serialised


def test_run_drill_catches_unexpected_exceptions(
    harness: IncidentDrillHarness,
):
    """If a drill handler raises, the harness must catch the exception
    and return a FAIL result rather than letting the supervisor crash."""

    # Monkeypatch one drill to raise.
    def boom():
        raise RuntimeError("boom")

    harness.drill_stop_unconfirmed = boom  # type: ignore[assignment]
    result = harness.run_drill("stop_unconfirmed")
    assert result.status is DrillStatus.FAIL
    assert "RuntimeError" in (result.observations[0] if result.observations else "")
    assert result.failure_reason == "boom"
