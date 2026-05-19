"""Phase 11B - cadence-driven Test Data Export scheduler tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.exports.service import ExportError, TestDataExportService
from app.paper_run.export_scheduler import ExportScheduler, ExportTick


@pytest.fixture()
def export_service(tmp_path: Path):
    sqlite_dir = tmp_path / "sqlite"
    sqlite_dir.mkdir(parents=True, exist_ok=True)
    dbs = DatabaseSet.open(sqlite_dir, wal=True, databases=PHASE2_DATABASES)
    migrate_database_set(dbs)
    repo = EventRepository(dbs.events, capital_conn=dbs.capital)
    out = tmp_path / "exports"
    out.mkdir(parents=True, exist_ok=True)
    service = TestDataExportService(
        event_repo=repo, trading_mode="paper", output_dir=out
    )
    yield service
    dbs.close()


def test_force_run_fires_immediately(export_service: TestDataExportService):
    sched = ExportScheduler(
        service=export_service,
        interval_hours=24,
        run_on_first_call=False,  # would normally NOT fire on tick(0)
    )
    tick = sched.force_run(clock_ms=1)
    assert tick.ran is True
    assert tick.result is not None
    assert tick.result.zip_path.exists()
    assert sched.last_run_ms == 1
    assert sched.success_count == 1


def test_first_tick_fires_when_run_on_first_call_true(
    export_service: TestDataExportService,
):
    sched = ExportScheduler(
        service=export_service,
        interval_hours=24,
        run_on_first_call=True,
    )
    tick = sched.tick(clock_ms=1)
    assert tick.ran is True


def test_first_tick_skips_when_run_on_first_call_false(
    export_service: TestDataExportService,
):
    sched = ExportScheduler(
        service=export_service,
        interval_hours=24,
        run_on_first_call=False,
    )
    tick = sched.tick(clock_ms=1)
    assert tick.ran is False
    assert tick.reason == "not_due"


def test_cadence_blocks_until_interval_elapses(
    export_service: TestDataExportService,
):
    sched = ExportScheduler(
        service=export_service,
        interval_hours=24,
        run_on_first_call=True,
    )
    tick1 = sched.tick(clock_ms=1)
    assert tick1.ran is True
    # 1 hour later - still within cadence.
    tick2 = sched.tick(clock_ms=1 + 3600_000)
    assert tick2.ran is False
    # 24h + 1ms later - cadence elapsed.
    tick3 = sched.tick(clock_ms=1 + 24 * 3600_000 + 1)
    assert tick3.ran is True
    assert sched.success_count == 2


def test_force_run_overrides_cadence(export_service: TestDataExportService):
    sched = ExportScheduler(
        service=export_service,
        interval_hours=24,
        run_on_first_call=True,
    )
    sched.tick(clock_ms=1)
    assert sched.success_count == 1
    forced = sched.force_run(clock_ms=2)
    assert forced.ran is True
    assert sched.success_count == 2


def test_zero_or_negative_interval_refused(
    export_service: TestDataExportService,
):
    with pytest.raises(ValueError):
        ExportScheduler(service=export_service, interval_hours=0)
    with pytest.raises(ValueError):
        ExportScheduler(service=export_service, interval_hours=-3)


def test_export_error_is_recorded(tmp_path: Path):
    """When the underlying service raises ExportError, the scheduler
    captures it as a failure tick and never raises into the caller."""
    sqlite_dir = tmp_path / "sqlite"
    sqlite_dir.mkdir(parents=True, exist_ok=True)
    dbs = DatabaseSet.open(sqlite_dir, wal=True, databases=PHASE2_DATABASES)
    migrate_database_set(dbs)
    repo = EventRepository(dbs.events, capital_conn=dbs.capital)
    out = tmp_path / "exports"
    out.mkdir(parents=True, exist_ok=True)
    service = TestDataExportService(
        event_repo=repo, trading_mode="paper", output_dir=out
    )
    sched = ExportScheduler(
        service=service,
        interval_hours=24,
        # Force an invalid range so service.export raises ExportError.
        range_label="not-a-valid-range",
    )
    try:
        tick = sched.force_run(clock_ms=1)
        assert tick.ran is False
        assert tick.reason == "export_error"
        assert tick.error is not None
        assert sched.failure_count == 1
        assert sched.success_count == 0
    finally:
        dbs.close()


def test_export_tick_payload_is_json_safe(
    export_service: TestDataExportService,
):
    sched = ExportScheduler(
        service=export_service, interval_hours=24, run_on_first_call=True
    )
    tick = sched.tick(clock_ms=1)
    import json

    serialised = json.dumps(tick.to_payload())
    assert "ran" in serialised
    assert "result_zip" in serialised
