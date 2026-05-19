"""Phase 11B - daily Markdown paper-report builder tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.events import Event, EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.exports.redaction import assert_no_forbidden_substrings
from app.paper_run.daily_report import DailyReportBuilder, DailyReportSnapshot


@pytest.fixture()
def event_repo(tmp_path: Path):
    sqlite_dir = tmp_path / "sqlite"
    sqlite_dir.mkdir(parents=True, exist_ok=True)
    dbs = DatabaseSet.open(sqlite_dir, wal=True, databases=PHASE2_DATABASES)
    migrate_database_set(dbs)
    repo = EventRepository(dbs.events, capital_conn=dbs.capital)
    yield repo
    dbs.close()


def _seed_baseline(repo: EventRepository) -> None:
    """Seed a deterministic event mix for the daily report aggregator."""
    repo.append_event(
        Event(
            event_type=EventType.RISK_APPROVED,
            source_module="risk_engine",
            symbol="BTCUSDT",
            payload={"reasons": ["paper_only_skeleton_approval"]},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.RISK_REJECTED,
            source_module="risk_engine",
            symbol="ETHUSDT",
            payload={"reasons": ["stop_unconfirmed", "manipulation_m3"]},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.RISK_REJECTED,
            source_module="risk_engine",
            symbol="ETHUSDT",
            payload={"reasons": ["stop_unconfirmed"]},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.STATE_TRANSITION,
            source_module="state_machine",
            symbol="BTCUSDT",
            payload={"from": "no_trade", "to": "observe"},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.POSITION_CLOSED,
            source_module="execution_fsm",
            symbol="BTCUSDT",
            payload={"realized_pnl": 1.5},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.POSITION_CLOSED,
            source_module="execution_fsm",
            symbol="ETHUSDT",
            payload={"realized_pnl": -0.5},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.INCIDENT_OPENED,
            source_module="reconciliation",
            payload={"level": "P0", "title": "ghost_position"},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.INCIDENT_OPENED,
            source_module="execution_fsm",
            payload={"level": "P1", "title": "stop_failed"},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.PROTECTION_MODE_ENTERED,
            source_module="reconciliation",
            payload={"reason": "p0_ghost_position"},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.RECONCILIATION_RESOLVED,
            source_module="reconciliation",
            payload={
                "p0_count": 1,
                "p1_count": 0,
                "new_opens_paused": True,
                "p0_latched_pause": True,
                "has_open_p0_incident": True,
            },
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.TELEGRAM_MESSAGE_SENT,
            source_module="telegram.alerts",
            payload={"tag": "system_status", "severity": "info"},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.DATA_EXPORT_GENERATED,
            source_module="telegram.exports",
            payload={"export_id": "export_xx"},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.LLM_DEGRADED,
            source_module="llm.interpreter",
            payload={"degraded_reasons": ["llm_disabled"]},
        )
    )


def test_daily_report_aggregates_baseline_counters(
    tmp_path: Path, event_repo: EventRepository
):
    _seed_baseline(event_repo)
    builder = DailyReportBuilder(
        event_repo=event_repo,
        output_dir=tmp_path / "reports" / "daily",
    )
    snap = builder.build(
        started_at_ms=1,
        finished_at_ms=2_000_000_000_000,
        write_to_disk=False,
        safety_summary={
            "trading_mode_paper": True,
            "live_trading_enabled": False,
            "right_tail_enabled": False,
            "llm_enabled": False,
            "exchange_live_order_enabled": False,
        },
        paper_cloud_summary={"trading_mode": "paper"},
    )
    assert snap.risk_approved_count == 1
    assert snap.risk_rejected_count == 2
    assert snap.state_transition_count == 1
    assert snap.paper_trade_count == 2
    assert snap.paper_realized_pnl == pytest.approx(1.0)
    assert snap.incidents_p0_count == 1
    assert snap.incidents_p1_count == 1
    assert snap.protection_mode_entered_count == 1
    assert snap.telegram_messages_sent_count == 1
    assert snap.data_export_generated_count == 1
    assert snap.llm_degraded_count == 1
    assert snap.new_opens_paused is True
    # Top reject reasons in count order
    top = dict(snap.top_reject_reasons)
    assert top.get("stop_unconfirmed") == 2
    assert top.get("manipulation_m3") == 1


def test_daily_report_markdown_passes_redaction_gate(
    tmp_path: Path, event_repo: EventRepository
):
    _seed_baseline(event_repo)
    builder = DailyReportBuilder(
        event_repo=event_repo,
        output_dir=tmp_path / "reports" / "daily",
    )
    snap = builder.build(
        started_at_ms=1,
        finished_at_ms=2_000_000_000_000,
        write_to_disk=False,
        safety_summary={"trading_mode_paper": True},
        paper_cloud_summary={
            "trading_mode": "paper",
            "env_guard": {
                "enabled": True,
                "inspected_env_var_count": 5,
                "forbidden_credential_env_var_count": 10,
            },
        },
    )
    # The gate raises on any forbidden literal; if this passes the
    # markdown is clean.
    assert_no_forbidden_substrings(snap.markdown)


def test_daily_report_writes_markdown_file(
    tmp_path: Path, event_repo: EventRepository
):
    out_dir = tmp_path / "reports" / "daily"
    builder = DailyReportBuilder(
        event_repo=event_repo,
        output_dir=out_dir,
    )
    snap = builder.build(
        started_at_ms=1,
        finished_at_ms=2_000_000_000_000,
        write_to_disk=True,
        safety_summary={},
        paper_cloud_summary={},
    )
    target = out_dir / f"{snap.date}-paper-report.md"
    assert target.exists()
    body = target.read_text(encoding="utf-8")
    assert "AMA-RT Phase 11B" in body
    assert snap.date in body


def test_daily_report_handles_empty_window(
    tmp_path: Path, event_repo: EventRepository
):
    """An empty events.db window must still produce a valid report
    with zero counters everywhere."""
    builder = DailyReportBuilder(
        event_repo=event_repo,
        output_dir=tmp_path / "reports" / "daily",
    )
    snap = builder.build(
        started_at_ms=1,
        finished_at_ms=2,
        write_to_disk=False,
        safety_summary={"trading_mode_paper": True},
        paper_cloud_summary={"trading_mode": "paper"},
    )
    assert snap.event_count == 0
    assert snap.risk_approved_count == 0
    assert snap.risk_rejected_count == 0
    assert snap.paper_trade_count == 0
    assert snap.top_reject_reasons == ()
    assert snap.top_symbols == ()


def test_to_payload_is_json_safe(tmp_path: Path, event_repo: EventRepository):
    _seed_baseline(event_repo)
    builder = DailyReportBuilder(
        event_repo=event_repo,
        output_dir=tmp_path / "reports" / "daily",
    )
    snap = builder.build(
        started_at_ms=1,
        finished_at_ms=2_000_000_000_000,
        write_to_disk=False,
        safety_summary={"trading_mode_paper": True},
        paper_cloud_summary={"trading_mode": "paper"},
    )
    import json

    payload = snap.to_payload()
    serialised = json.dumps(payload)
    assert "stop_unconfirmed" in serialised  # reject reason name OK
    # No credential literals.
    for literal in (
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "DEEPSEEK_API_KEY",
    ):
        assert literal not in serialised
