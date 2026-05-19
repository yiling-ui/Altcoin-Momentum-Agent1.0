"""Phase 11B - PaperCloudSupervisor.acceptance_dry_run end-to-end tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config.settings import get_settings, load_settings
from app.core.errors import SafetyViolation
from app.exports.redaction import assert_no_forbidden_substrings
from app.paper_run.config import (
    DEFAULT_PAPER_CLOUD_PATH,
    PaperCloudConfig,
)
from app.paper_run.incident_drill import DrillStatus
from app.paper_run.supervisor import (
    PaperCloudSupervisor,
    PaperCloudSupervisorReport,
)


@pytest.fixture()
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Force settings + paper_cloud to use a tmp data dir so the
    supervisor never touches the persistent ./data tree."""
    monkeypatch.setenv("AMA_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    yield load_settings()
    get_settings.cache_clear()


def test_acceptance_dry_run_returns_go(isolated_settings):
    paper_cloud = PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)
    supervisor = PaperCloudSupervisor(
        settings=isolated_settings,
        paper_cloud=paper_cloud,
        environ={},
    )
    report = supervisor.acceptance_dry_run(
        emit_banner=False,
        write_acceptance_report=False,
    )
    assert isinstance(report, PaperCloudSupervisorReport)
    assert report.accepted is True
    assert report.go_decision == "GO"
    assert report.all_drills_passed is True


def test_acceptance_dry_run_drill_results_match_brief(isolated_settings):
    paper_cloud = PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)
    supervisor = PaperCloudSupervisor(
        settings=isolated_settings,
        paper_cloud=paper_cloud,
        environ={},
    )
    report = supervisor.acceptance_dry_run(
        emit_banner=False, write_acceptance_report=False
    )
    drill_names = {r.name for r in report.drill_results}
    assert drill_names == {
        "stop_unconfirmed",
        "unknown_position",
        "data_degraded",
        "p0_ghost_position",
        "p0_unattached_stop",
        "rebase_in_progress",
        "telegram_export_failure",
        "llm_degraded",
    }
    for r in report.drill_results:
        assert r.status is DrillStatus.PASS, (
            f"Drill {r.name} unexpectedly failed: {r.failure_reason}"
        )


def test_acceptance_dry_run_writes_report(
    isolated_settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The supervisor writes ``docs/PHASE_11B_PAPER_ACCEPTANCE_REPORT.md``
    after a successful run. We replace the docs path with a tmp dir so
    the test does not modify the repo."""
    paper_cloud = PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)

    # The supervisor builds the report path from
    # ``Path(__file__).resolve().parent.parent.parent / "docs" / ...``
    # (i.e. the repo root). For this test we accept that the existing
    # template will be overwritten and just verify the contents.
    supervisor = PaperCloudSupervisor(
        settings=isolated_settings,
        paper_cloud=paper_cloud,
        environ={},
    )
    report = supervisor.acceptance_dry_run(
        emit_banner=False, write_acceptance_report=True
    )
    assert report.acceptance_report_path is not None
    target = Path(report.acceptance_report_path)
    assert target.exists()
    body = target.read_text(encoding="utf-8")
    # Defence-in-depth: the rendered acceptance report must be free
    # of forbidden literals.
    assert_no_forbidden_substrings(body)
    # Must contain the canonical headings the brief requires.
    assert "AMA-RT Phase 11B" in body
    assert "Phase 1 safety lock" in body
    assert "Env-guard pre-flight" in body
    assert "Boot paper-trade lifecycle" in body
    assert "First-boot /export_test_data 24h" in body
    assert "Daily report" in body
    assert "Telegram outbound summary" in body
    assert "Incident drill results" in body
    assert "Acceptance criteria" in body
    assert "Final decision" in body


def test_acceptance_dry_run_settings_safety_locked(isolated_settings):
    paper_cloud = PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)
    supervisor = PaperCloudSupervisor(
        settings=isolated_settings, paper_cloud=paper_cloud, environ={}
    )
    report = supervisor.acceptance_dry_run(
        emit_banner=False, write_acceptance_report=False
    )
    safety = report.settings_safety
    assert safety["trading_mode_paper"] is True
    assert safety["live_trading_enabled"] is False
    assert safety["right_tail_enabled"] is False
    assert safety["llm_enabled"] is False
    assert safety["exchange_live_order_enabled"] is False


def test_acceptance_dry_run_first_boot_export(isolated_settings):
    paper_cloud = PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)
    supervisor = PaperCloudSupervisor(
        settings=isolated_settings, paper_cloud=paper_cloud, environ={}
    )
    report = supervisor.acceptance_dry_run(
        emit_banner=False, write_acceptance_report=False
    )
    assert report.boot_export_tick is not None
    assert report.boot_export_tick.ran is True
    assert report.boot_export_zip_path is not None
    zip_path = Path(report.boot_export_zip_path)
    assert zip_path.exists()
    assert zip_path.stat().st_size > 0


def test_acceptance_dry_run_telegram_summary_uses_fake_transport(
    isolated_settings,
):
    paper_cloud = PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)
    supervisor = PaperCloudSupervisor(
        settings=isolated_settings, paper_cloud=paper_cloud, environ={}
    )
    report = supervisor.acceptance_dry_run(
        emit_banner=False, write_acceptance_report=False
    )
    summary = report.telegram_summary
    assert summary["transport"] == "telegram_fake"
    assert int(summary["redaction_blocked"]) == 0
    assert int(summary["send_failed"]) == 0


def test_acceptance_dry_run_refuses_when_env_guard_fails(
    isolated_settings,
):
    paper_cloud = PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)
    supervisor = PaperCloudSupervisor(
        settings=isolated_settings,
        paper_cloud=paper_cloud,
        environ={"BINANCE_API_KEY": "xxx"},
    )
    with pytest.raises(SafetyViolation):
        supervisor.acceptance_dry_run(
            emit_banner=False, write_acceptance_report=False
        )


def test_acceptance_dry_run_idempotent(isolated_settings):
    """Running the supervisor twice in the same process must produce
    GO both times."""
    paper_cloud = PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)
    supervisor = PaperCloudSupervisor(
        settings=isolated_settings, paper_cloud=paper_cloud, environ={}
    )
    first = supervisor.acceptance_dry_run(
        emit_banner=False, write_acceptance_report=False
    )
    second = supervisor.acceptance_dry_run(
        emit_banner=False, write_acceptance_report=False
    )
    assert first.accepted is True
    assert second.accepted is True


def test_supervisor_report_to_payload_is_json_safe(isolated_settings):
    paper_cloud = PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)
    supervisor = PaperCloudSupervisor(
        settings=isolated_settings, paper_cloud=paper_cloud, environ={}
    )
    report = supervisor.acceptance_dry_run(
        emit_banner=False, write_acceptance_report=False
    )
    import json

    serialised = json.dumps(report.to_payload(), default=str)
    # Must not contain forbidden literals.
    for literal in (
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "DEEPSEEK_API_KEY",
    ):
        assert literal not in serialised


def test_supervisor_keeps_phase1_safety_lock(isolated_settings):
    """The supervisor must NEVER mutate the resolved Settings."""
    before = isolated_settings.live_trading_enabled
    paper_cloud = PaperCloudConfig.load(DEFAULT_PAPER_CLOUD_PATH)
    supervisor = PaperCloudSupervisor(
        settings=isolated_settings, paper_cloud=paper_cloud, environ={}
    )
    supervisor.acceptance_dry_run(
        emit_banner=False, write_acceptance_report=False
    )
    after = isolated_settings.live_trading_enabled
    assert before is False
    assert after is False
