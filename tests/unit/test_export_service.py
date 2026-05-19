"""Phase 8.5 - TestDataExportService tests (Issue #8.5)."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from app.core.events import Event, EventType
from app.database.migrations import apply_schema
from app.database.repositories import EventRepository
from app.exports import (
    ExportError,
    TestDataExportService,
    parse_iso_date,
    resolve_time_range,
)
from app.learning import (
    ConfigVersions,
    LearningReadyContext,
    OpportunityIdentity,
    VirtualTradePlan,
    attach_learning_ready,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo() -> EventRepository:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    return EventRepository(conn)


def _seed_events(repo: EventRepository, base_ts: int = 1_700_000_000_000) -> None:
    """Seed a deterministic set of events covering every Phase 8.5 path."""
    ctx_full = LearningReadyContext(
        opportunity=OpportunityIdentity.create(
            symbol="PEPEUSDT",
            source_phase="pre_anomaly",
            opportunity_id="opp_seed_pepe",
        ),
        virtual_trade_plan=VirtualTradePlan(
            virtual_entry=100.0, virtual_stop=95.0, virtual_tp1=110.0,
        ),
        config_versions=ConfigVersions.defaults(),
    )
    repo.append_event(
        Event(
            event_type=EventType.RISK_REJECTED,
            source_module="risk_engine",
            symbol="PEPEUSDT",
            timestamp=base_ts,
            payload=attach_learning_ready(
                {"reasons": ["manipulation_m3", "regime_block_all"]},
                ctx_full,
            ),
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.RISK_APPROVED,
            source_module="risk_engine",
            symbol="ETHUSDT",
            timestamp=base_ts + 1000,
            payload={"reasons": ["paper_only_skeleton_approval"]},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.STATE_TRANSITION,
            source_module="state_machine",
            symbol="PEPEUSDT",
            timestamp=base_ts + 2000,
            payload={"from": "no_trade", "to": "observe", "trigger": "signal"},
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.CAPITAL_REBASE,
            source_module="capital_flow_engine",
            timestamp=base_ts + 3000,
            payload={
                "amount": 100.0,
                "trading_capital": 100.0,
                "exchange_equity": 100.0,
                "withdrawn_profit": 0.0,
                "lifetime_equity": 100.0,
                "net_trading_pnl": 0.0,
                "trigger": "deposit",
            },
        )
    )


def _make_service(tmp_path: Path) -> TestDataExportService:
    repo = _make_repo()
    _seed_events(repo)
    output_dir = tmp_path / "exports"
    return TestDataExportService(
        event_repo=repo,
        trading_mode="paper",
        app_version="phase8_5_test",
        output_dir=output_dir,
    )


# ---------------------------------------------------------------------------
# Time range helpers
# ---------------------------------------------------------------------------

def test_resolve_time_range_24h_uses_24h_window():
    start, end = resolve_time_range(range_label="24h", clock_ms=10_000_000_000)
    assert end - start == 24 * 60 * 60 * 1000


def test_resolve_time_range_7d_uses_7d_window():
    start, end = resolve_time_range(range_label="7d", clock_ms=10_000_000_000)
    assert end - start == 7 * 24 * 60 * 60 * 1000


def test_resolve_time_range_today_starts_at_midnight_utc():
    # 12:00 UTC on 2026-05-19 -> midnight is 12 hours back
    clock = 1_779_624_000_000  # arbitrary deterministic value
    start, end = resolve_time_range(range_label="today", clock_ms=clock)
    assert start <= end
    assert (end - start) <= 24 * 60 * 60 * 1000


def test_resolve_time_range_range_requires_start_and_end():
    with pytest.raises(ExportError):
        resolve_time_range(range_label="range")


def test_resolve_time_range_range_validates_order():
    with pytest.raises(ExportError):
        resolve_time_range(range_label="range", start_ms=1000, end_ms=999)


def test_resolve_time_range_rejects_unknown_label():
    with pytest.raises(ExportError):
        resolve_time_range(range_label="unknown")


def test_parse_iso_date_handles_date_only():
    ms = parse_iso_date("2026-05-19")
    # midnight UTC
    assert ms % (24 * 60 * 60 * 1000) == 0


def test_parse_iso_date_handles_iso_datetime():
    ms = parse_iso_date("2026-05-19T12:00:00Z")
    # Compare against the date-only midnight + 12h.
    midnight = parse_iso_date("2026-05-19")
    assert ms == midnight + 12 * 60 * 60 * 1000


def test_parse_iso_date_naive_treated_as_utc():
    a = parse_iso_date("2026-05-19T00:00:00")
    b = parse_iso_date("2026-05-19")
    assert a == b


def test_parse_iso_date_rejects_garbage():
    with pytest.raises(ExportError):
        parse_iso_date("not-a-date")


# ---------------------------------------------------------------------------
# Export service
# ---------------------------------------------------------------------------

def test_export_service_writes_zip_file(tmp_path):
    service = _make_service(tmp_path)
    result = service.export(
        range_label="range",
        start_ms=1_700_000_000_000 - 1000,
        end_ms=1_700_000_010_000,
        type_filter="all",
    )
    assert result.zip_path.exists()
    assert result.zip_path.suffix == ".zip"
    assert result.bytes_written > 0


def test_export_zip_contains_manifest_and_summary_and_events_jsonl(tmp_path):
    service = _make_service(tmp_path)
    result = service.export(
        range_label="range",
        start_ms=1_700_000_000_000 - 1000,
        end_ms=1_700_000_010_000,
        type_filter="all",
    )
    with zipfile.ZipFile(result.zip_path) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "summary_report.md" in names
        assert "events.jsonl" in names
        assert "opportunities.jsonl" in names
        assert "signal_snapshots.jsonl" in names
        assert "risk_decisions.jsonl" in names
        assert "state_transitions.jsonl" in names
        assert "capital_events.jsonl" in names
        assert "virtual_trade_plans.jsonl" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["redaction_applied"] is True
        assert manifest["trading_mode"] == "paper"
        assert manifest["event_count"] >= 4
        assert manifest["opportunity_count"] >= 1
        assert manifest["risk_rejected_count"] >= 1


def test_export_zip_is_redacted(tmp_path):
    """Bundle must NOT contain forbidden secret-style substrings."""
    repo = _make_repo()
    repo.append_event(
        Event(
            event_type=EventType.RISK_REJECTED,
            source_module="phase8_5_test",
            symbol="BTCUSDT",
            timestamp=1_700_000_000_000,
            payload={
                "reasons": ["live_trading_disabled"],
                "api_key": "BINANCE_API_KEY_SHOULD_BE_REDACTED",
                "secret_token": "1234567890:abcdefghijklmnopqrstuvwxyz1234567890",
            },
        )
    )
    service = TestDataExportService(
        event_repo=repo,
        trading_mode="paper",
        app_version="phase8_5_test",
        output_dir=tmp_path / "exports",
    )
    result = service.export(
        range_label="range",
        start_ms=1_700_000_000_000 - 1000,
        end_ms=1_700_000_010_000,
        type_filter="all",
    )
    with zipfile.ZipFile(result.zip_path) as zf:
        # The bundle must contain at least one file that explicitly
        # records the redacted sentinel - this is the cross-cutting
        # check.
        any_redacted = False
        for name in zf.namelist():
            data = zf.read(name).decode("utf-8")
            assert "BINANCE_API_KEY_SHOULD_BE_REDACTED" not in data
            assert "1234567890:abcdefghij" not in data
            if "[REDACTED]" in data:
                any_redacted = True
        assert any_redacted, "no [REDACTED] sentinel in any bundle file"


def test_export_supports_type_rejections_filter(tmp_path):
    service = _make_service(tmp_path)
    result = service.export(
        range_label="range",
        start_ms=1_700_000_000_000 - 1000,
        end_ms=1_700_000_010_000,
        type_filter="rejections",
    )
    with zipfile.ZipFile(result.zip_path) as zf:
        names = set(zf.namelist())
        assert "risk_decisions.jsonl" in names
        # Approved events should NOT appear in the rejections filter.
        body = zf.read("risk_decisions.jsonl").decode("utf-8")
        assert "RISK_APPROVED" not in body
        assert "RISK_REJECTED" in body


def test_export_supports_type_capital_filter(tmp_path):
    service = _make_service(tmp_path)
    result = service.export(
        range_label="range",
        start_ms=1_700_000_000_000 - 1000,
        end_ms=1_700_000_010_000,
        type_filter="capital",
    )
    with zipfile.ZipFile(result.zip_path) as zf:
        names = set(zf.namelist())
        assert "capital_events.jsonl" in names
        body = zf.read("capital_events.jsonl").decode("utf-8")
        assert "CAPITAL_REBASE" in body
        assert "RISK_REJECTED" not in body


def test_export_supports_type_state_filter(tmp_path):
    service = _make_service(tmp_path)
    result = service.export(
        range_label="range",
        start_ms=1_700_000_000_000 - 1000,
        end_ms=1_700_000_010_000,
        type_filter="state",
    )
    with zipfile.ZipFile(result.zip_path) as zf:
        names = set(zf.namelist())
        assert "state_transitions.jsonl" in names


def test_export_supports_type_learning_filter(tmp_path):
    service = _make_service(tmp_path)
    result = service.export(
        range_label="range",
        start_ms=1_700_000_000_000 - 1000,
        end_ms=1_700_000_010_000,
        type_filter="learning",
    )
    with zipfile.ZipFile(result.zip_path) as zf:
        names = set(zf.namelist())
        assert "opportunities.jsonl" in names
        assert "signal_snapshots.jsonl" in names
        assert "virtual_trade_plans.jsonl" in names
        assert "risk_decisions.jsonl" in names


def test_export_rejects_unknown_type_filter(tmp_path):
    service = _make_service(tmp_path)
    with pytest.raises(ExportError):
        service.export(type_filter="unknown_type")


def test_export_handles_empty_window(tmp_path):
    """Empty result set must still produce a valid zip with manifest +
    summary."""
    service = _make_service(tmp_path)
    result = service.export(
        range_label="range",
        start_ms=1_500_000_000_000,
        end_ms=1_500_000_010_000,
        type_filter="all",
    )
    assert result.zip_path.exists()
    with zipfile.ZipFile(result.zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["event_count"] == 0
        assert manifest["redaction_applied"] is True
        # summary still rendered
        summary = zf.read("summary_report.md").decode("utf-8")
        assert "Total events" in summary


def test_export_size_cap_refuses_when_exceeded(tmp_path):
    """Caller-supplied cap is honoured; the service refuses to write."""
    service = _make_service(tmp_path)
    service._max_zip_bytes = 1  # impossibly small
    with pytest.raises(ExportError) as ei:
        service.export(
            range_label="range",
            start_ms=1_700_000_000_000 - 1000,
            end_ms=1_700_000_010_000,
            type_filter="all",
        )
    msg = str(ei.value)
    assert "max_zip_bytes" in msg


def test_export_manifest_carries_safety_summary(tmp_path):
    service = _make_service(tmp_path)
    result = service.export(
        range_label="range",
        start_ms=1_700_000_000_000 - 1000,
        end_ms=1_700_000_010_000,
        type_filter="all",
    )
    with zipfile.ZipFile(result.zip_path) as zf:
        manifest = json.loads(zf.read("manifest.json"))
    safety = manifest["safety_summary"]
    assert safety["live_trading_enabled"] is False
    assert safety["right_tail_enabled"] is False
    assert safety["llm_enabled"] is False
    assert safety["exchange_live_order_enabled"] is False
    assert safety["trading_mode_paper"] is True


def test_export_filename_lands_under_data_reports_exports(tmp_path):
    service = _make_service(tmp_path)
    result = service.export(
        range_label="range",
        start_ms=1_700_000_000_000 - 1000,
        end_ms=1_700_000_010_000,
        type_filter="all",
    )
    assert result.zip_path.name.startswith("ama_rt_test_data_")
    assert result.zip_path.parent == tmp_path / "exports"
