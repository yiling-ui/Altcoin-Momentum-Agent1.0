"""Phase 10D - TelegramExportBridge tests (Issue #10 Part 4).

Pin the contract for ``/export_*`` -> Phase 8.5 service path:

  - SHORT generating-summary caption + sendDocument (single
    outbound call), NEVER chat dump.
  - DATA_EXPORT_GENERATED on success.
  - DATA_EXPORT_FAILED on every failure path (size cap exceeded,
    transport drop, redaction gate caught a leak, invalid arg).
  - Refusal when trading_mode != paper.
  - All bytes go through Phase 8.5 redactor (the service guarantees
    this and the bridge consumes the redacted zip).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.events import EventType
from app.exports.service import TestDataExportService
from app.telegram.alerts import AlertDispatcher
from app.telegram.bot import TelegramCommandCenter
from app.telegram.commands import Command, CommandStatus
from app.telegram.exports import TelegramExportBridge
from app.telegram.outbound import FakeTelegramClient


@pytest.fixture
def export_dir(tmp_path: Path) -> Path:
    return tmp_path / "exports"


@pytest.fixture
def bridge_setup(events_repo, export_dir):
    """Build the full Phase 10D wiring against a real on-disk export
    service and an in-memory FakeTelegramClient."""
    fake = FakeTelegramClient(outbound_enabled=True)
    dispatcher = AlertDispatcher(
        outbound=fake, event_repo=events_repo, outbound_enabled=True
    )
    service = TestDataExportService(
        event_repo=events_repo,
        trading_mode="paper",
        app_version="1.4.0a10d",
        output_dir=export_dir,
    )
    bridge = TelegramExportBridge(
        service=service,
        dispatcher=dispatcher,
        event_repo=events_repo,
    )
    return fake, dispatcher, service, bridge


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_export_test_data_24h_produces_zip_and_sends_document(
    bridge_setup, events_repo, phase1_settings
):
    fake, dispatcher, _service, bridge = bridge_setup
    cmd = Command(
        name="/export_test_data",
        user_id="phase10d-admin",
        args=("24h",),
    )
    safety_snapshot = {
        "trading_mode": "paper",
        "live_trading_enabled": False,
        "right_tail_enabled": False,
        "llm_enabled": False,
        "exchange_live_order_enabled": False,
    }
    res = bridge.handle(cmd, phase1_settings, safety_snapshot)
    assert res.status is CommandStatus.OK
    # Phase 8.5 export_id propagated to the bot reply.
    assert "export_id=" in res.message
    # DATA_EXPORT_GENERATED audit event written.
    audits = events_repo.list(event_type=EventType.DATA_EXPORT_GENERATED)
    assert len(audits) == 1
    payload = audits[0].payload
    assert payload["command"] == "/export_test_data"
    assert payload["range_label"] == "24h"
    assert payload["type_filter"] == "all"
    assert payload["redaction_applied"] is True
    # Exactly one send_document call.
    assert dispatcher.documents_sent == 1
    [call] = fake.calls
    assert call.surface.value == "send_document"
    assert call.text.startswith("[ama-rt:export]")
    assert "mode=paper" in call.text
    assert "status=ready" in call.text
    # NO raw chat dump - the message is a SHORT caption.
    assert len(call.text) < 1024


@pytest.mark.parametrize(
    "command_name,expected_type_filter",
    [
        ("/export_events", "events"),
        ("/export_rejections", "rejections"),
        ("/export_capital", "capital"),
        ("/export_report", "all"),
        ("/export_learning_dataset", "learning"),
    ],
)
def test_each_export_command_uses_correct_type_filter(
    bridge_setup, events_repo, phase1_settings, command_name, expected_type_filter
):
    _fake, _dispatcher, _service, bridge = bridge_setup
    cmd = Command(name=command_name, user_id="admin")
    res = bridge.handle(
        cmd,
        phase1_settings,
        {
            "trading_mode": "paper",
            "live_trading_enabled": False,
            "right_tail_enabled": False,
            "llm_enabled": False,
            "exchange_live_order_enabled": False,
        },
    )
    assert res.status is CommandStatus.OK
    audits = events_repo.list(event_type=EventType.DATA_EXPORT_GENERATED)
    assert any(
        a.payload["command"] == command_name
        and a.payload["type_filter"] == expected_type_filter
        for a in audits
    )


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------
def test_export_refuses_when_trading_mode_is_not_paper(
    bridge_setup, events_repo, phase1_settings
):
    _fake, _dispatcher, _service, bridge = bridge_setup
    cmd = Command(name="/export_test_data", user_id="admin", args=("24h",))
    res = bridge.handle(
        cmd,
        phase1_settings,
        {"trading_mode": "live"},  # Drift!
    )
    assert res.status is CommandStatus.EXECUTION_ERROR
    audits = events_repo.list(event_type=EventType.DATA_EXPORT_FAILED)
    assert len(audits) == 1
    assert audits[0].payload["reason"] == "refused_non_paper_mode"


def test_export_invalid_range_writes_failed_event(
    bridge_setup, events_repo, phase1_settings
):
    _fake, _dispatcher, _service, bridge = bridge_setup
    cmd = Command(
        name="/export_test_data", user_id="admin", args=("17h",)  # invalid
    )
    res = bridge.handle(
        cmd,
        phase1_settings,
        {"trading_mode": "paper"},
    )
    assert res.status is CommandStatus.EXECUTION_ERROR
    audits = events_repo.list(event_type=EventType.DATA_EXPORT_FAILED)
    assert any(a.payload["reason"] == "invalid_argument" for a in audits)


def test_export_size_cap_exceeded_writes_failed_event(
    events_repo, export_dir, phase1_settings
):
    """When the service refuses with ExportError (size cap), the
    bridge MUST emit DATA_EXPORT_FAILED + EXECUTION_ERROR + a SHORT
    reply that suggests narrowing the range."""
    fake = FakeTelegramClient(outbound_enabled=True)
    dispatcher = AlertDispatcher(
        outbound=fake, event_repo=events_repo, outbound_enabled=True
    )
    # Build a service with an absurdly tight cap so ANY zip exceeds it.
    service = TestDataExportService(
        event_repo=events_repo,
        trading_mode="paper",
        app_version="1.4.0a10d",
        output_dir=export_dir,
        max_zip_bytes=10,  # 10 bytes - guaranteed too small
    )
    bridge = TelegramExportBridge(
        service=service,
        dispatcher=dispatcher,
        event_repo=events_repo,
    )
    cmd = Command(name="/export_test_data", user_id="admin", args=("24h",))
    res = bridge.handle(
        cmd,
        phase1_settings,
        {"trading_mode": "paper"},
    )
    assert res.status is CommandStatus.EXECUTION_ERROR
    audits = events_repo.list(event_type=EventType.DATA_EXPORT_FAILED)
    assert any(a.payload["reason"] == "export_error" for a in audits)
    assert "smaller range" in res.message.lower() or "single type" in res.message.lower()


def test_export_does_not_send_document_on_failure(
    bridge_setup, events_repo, phase1_settings
):
    _fake, dispatcher, _service, bridge = bridge_setup
    res = bridge.handle(
        Command(name="/export_test_data", user_id="admin", args=("not_real",)),
        phase1_settings,
        {"trading_mode": "paper"},
    )
    assert res.status is CommandStatus.EXECUTION_ERROR
    # No document was sent.
    assert dispatcher.documents_sent == 0


def test_export_transport_drop_writes_failed_event(
    events_repo, export_dir, phase1_settings
):
    fake = FakeTelegramClient(outbound_enabled=True, failure_mode="drop")
    dispatcher = AlertDispatcher(
        outbound=fake, event_repo=events_repo, outbound_enabled=True
    )
    service = TestDataExportService(
        event_repo=events_repo,
        trading_mode="paper",
        app_version="1.4.0a10d",
        output_dir=export_dir,
    )
    bridge = TelegramExportBridge(
        service=service,
        dispatcher=dispatcher,
        event_repo=events_repo,
    )
    res = bridge.handle(
        Command(name="/export_test_data", user_id="admin", args=("24h",)),
        phase1_settings,
        {"trading_mode": "paper"},
    )
    assert res.status is CommandStatus.EXECUTION_ERROR
    audits = events_repo.list(event_type=EventType.DATA_EXPORT_FAILED)
    assert any(
        a.payload["reason"] in {"send_document_failed"} for a in audits
    )


# ---------------------------------------------------------------------------
# End-to-end through TelegramCommandCenter
# ---------------------------------------------------------------------------
def test_command_center_routes_export_through_bridge(
    bridge_setup, events_repo, phase1_settings
):
    fake, dispatcher, _service, bridge = bridge_setup
    bot = TelegramCommandCenter(
        settings=phase1_settings,
        event_repo=events_repo,
        export_handler=bridge.handle,
    )
    res = bot.handle(
        Command(name="/export_test_data", user_id="admin", args=("24h",))
    )
    assert res.status is CommandStatus.OK
    assert dispatcher.documents_sent == 1
    assert events_repo.count(event_type=EventType.DATA_EXPORT_GENERATED) == 1


# ---------------------------------------------------------------------------
# The bridge does NOT chat-dump raw .jsonl content
# ---------------------------------------------------------------------------
def test_no_chat_dump_of_jsonl_content(bridge_setup, events_repo, phase1_settings):
    fake, _dispatcher, _service, bridge = bridge_setup
    cmd = Command(name="/export_test_data", user_id="admin", args=("24h",))
    bridge.handle(
        cmd,
        phase1_settings,
        {"trading_mode": "paper"},
    )
    # The single fake call is a sendDocument; the caption is a SHORT
    # text. NEVER a JSONL line.
    [call] = fake.calls
    assert call.surface.value == "send_document"
    # JSONL-shaped content (a brace at the start of a line) must not
    # be in the caption.
    assert not call.text.lstrip().startswith("{")
    assert not call.text.lstrip().startswith("[{")
    # Raw events.jsonl rows would carry an "event_id" key; the
    # caption is a SHORT summary.
    assert "event_id" not in call.text


# ---------------------------------------------------------------------------
# Manifest stays redacted
# ---------------------------------------------------------------------------
def test_audit_payload_marks_redaction_applied(
    bridge_setup, events_repo, phase1_settings
):
    _fake, _dispatcher, _service, bridge = bridge_setup
    bridge.handle(
        Command(name="/export_test_data", user_id="admin", args=("24h",)),
        phase1_settings,
        {"trading_mode": "paper"},
    )
    [audit] = events_repo.list(event_type=EventType.DATA_EXPORT_GENERATED)
    assert audit.payload["redaction_applied"] is True
