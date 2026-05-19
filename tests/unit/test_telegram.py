"""Phase 10D - TelegramCommandCenter tests (Issue #10 Part 4).

Replaces the Phase 1 skeleton tests. The new contract:

  - All 16 commands accepted (10 status/operator + 6 export).
  - Operator allow-list: unauthorised user -> DENIED + audit.
  - Two-step confirmation for ``/resume`` AND ``/rebase``.
  - ``/kill_all`` runs without confirmation but is loudly audited
    AND does NOT touch any real exchange surface.
  - ``/rebase`` does NOT execute a real withdrawal.
  - Every command writes ``TELEGRAM_COMMAND_RECEIVED``; rejected
    commands ALSO write ``TELEGRAM_COMMAND_REJECTED``.
  - Export commands route through the ``export_handler`` callback.
"""

from __future__ import annotations

import pytest

from app.core.events import EventType
from app.telegram.bot import TelegramCommandCenter
from app.telegram.commands import (
    AVAILABLE_COMMANDS,
    CONFIRM_REQUIRED,
    EXPORT_COMMAND_SET,
    LOUD_AUDIT_COMMANDS,
    Command,
    CommandStatus,
)


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------
def test_available_commands_pinned():
    """The 16 Issue-mandated commands must be reachable through
    AVAILABLE_COMMANDS."""
    expected = {
        "/status",
        "/positions",
        "/pnl",
        "/risk",
        "/capital",
        "/incidents",
        "/pause",
        "/resume",
        "/kill_all",
        "/rebase",
        "/export_test_data",
        "/export_events",
        "/export_rejections",
        "/export_capital",
        "/export_report",
        "/export_learning_dataset",
    }
    assert set(AVAILABLE_COMMANDS) == expected


def test_confirm_required_includes_resume_and_rebase():
    assert "/resume" in CONFIRM_REQUIRED
    assert "/rebase" in CONFIRM_REQUIRED


def test_export_command_set_pinned():
    assert EXPORT_COMMAND_SET == frozenset(
        {
            "/export_test_data",
            "/export_events",
            "/export_rejections",
            "/export_capital",
            "/export_report",
            "/export_learning_dataset",
        }
    )


def test_loud_audit_commands_pinned():
    assert "/kill_all" in LOUD_AUDIT_COMMANDS
    assert "/pause" in LOUD_AUDIT_COMMANDS


# ---------------------------------------------------------------------------
# Whitelist
# ---------------------------------------------------------------------------
def test_unknown_command_writes_received_AND_rejected_and_returns_unknown(
    phase1_settings, events_repo
):
    bot = TelegramCommandCenter(
        settings=phase1_settings, event_repo=events_repo
    )
    res = bot.handle(Command(name="/launch_nukes", user_id="u1"))
    assert res.status is CommandStatus.UNKNOWN
    received = events_repo.list(event_type=EventType.TELEGRAM_COMMAND_RECEIVED)
    rejected = events_repo.list(event_type=EventType.TELEGRAM_COMMAND_REJECTED)
    assert len(received) == 1
    assert len(rejected) == 1
    assert rejected[0].payload["reason"] == "unknown_command"


def test_non_admin_denied_when_allow_list_configured(phase1_settings, events_repo):
    bot = TelegramCommandCenter(
        settings=phase1_settings,
        admin_user_ids=frozenset({"alice"}),
        event_repo=events_repo,
    )
    res = bot.handle(Command(name="/status", user_id="bob"))
    assert res.status is CommandStatus.DENIED
    rejected = events_repo.list(event_type=EventType.TELEGRAM_COMMAND_REJECTED)
    assert len(rejected) == 1
    assert rejected[0].payload["reason"] == "unauthorised_user"


def test_admin_allowed_when_in_allow_list(phase1_settings):
    bot = TelegramCommandCenter(
        settings=phase1_settings,
        admin_user_ids=frozenset({"alice"}),
    )
    res = bot.handle(Command(name="/status", user_id="alice"))
    assert res.status is CommandStatus.OK


# ---------------------------------------------------------------------------
# Two-step confirmation
# ---------------------------------------------------------------------------
def test_resume_requires_confirmation(phase1_settings):
    bot = TelegramCommandCenter(settings=phase1_settings)
    res = bot.handle(Command(name="/resume", user_id="alice"))
    assert res.status is CommandStatus.NEEDS_CONFIRMATION

    res2 = bot.handle(Command(name="/resume", user_id="alice"), confirmed=True)
    assert res2.status is CommandStatus.OK


def test_rebase_requires_confirmation(phase1_settings):
    bot = TelegramCommandCenter(settings=phase1_settings)
    res = bot.handle(Command(name="/rebase", user_id="alice"))
    assert res.status is CommandStatus.NEEDS_CONFIRMATION

    res2 = bot.handle(Command(name="/rebase", user_id="alice"), confirmed=True)
    assert res2.status is CommandStatus.OK


def test_kill_all_does_not_require_confirmation(phase1_settings):
    bot = TelegramCommandCenter(settings=phase1_settings)
    res = bot.handle(Command(name="/kill_all", user_id="alice"))
    assert res.status is CommandStatus.OK


# ---------------------------------------------------------------------------
# Read-only commands
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name",
    ["/status", "/positions", "/pnl", "/risk", "/capital", "/incidents"],
)
def test_read_only_commands_return_ok(phase1_settings, name):
    bot = TelegramCommandCenter(settings=phase1_settings)
    res = bot.handle(Command(name=name, user_id="alice"))
    assert res.status is CommandStatus.OK
    assert res.metadata["trading_mode"] == "paper"
    assert res.metadata["live_trading_enabled"] is False


# ---------------------------------------------------------------------------
# /pause /resume /kill_all /rebase
# ---------------------------------------------------------------------------
def test_pause_sets_in_process_pause_flag(phase1_settings, events_repo):
    bot = TelegramCommandCenter(
        settings=phase1_settings, event_repo=events_repo
    )
    assert bot.new_opens_paused is False
    res = bot.handle(Command(name="/pause", user_id="alice"))
    assert res.status is CommandStatus.OK
    assert bot.new_opens_paused is True


def test_resume_clears_pause_flag(phase1_settings):
    bot = TelegramCommandCenter(settings=phase1_settings)
    bot.handle(Command(name="/pause", user_id="alice"))
    assert bot.new_opens_paused is True
    bot.handle(Command(name="/resume", user_id="alice"), confirmed=True)
    assert bot.new_opens_paused is False
    assert bot.resume_invocations == 1


def test_kill_all_records_invocation_and_pauses_new_opens(
    phase1_settings, events_repo
):
    bot = TelegramCommandCenter(
        settings=phase1_settings, event_repo=events_repo
    )
    res = bot.handle(Command(name="/kill_all", user_id="alice"))
    assert res.status is CommandStatus.OK
    assert bot.kill_all_invocations == 1
    assert bot.new_opens_paused is True
    # A "loud audit" appends an extra TELEGRAM_COMMAND_RECEIVED entry
    # tagged with loud=True.
    received = events_repo.list(event_type=EventType.TELEGRAM_COMMAND_RECEIVED)
    assert any(ev.payload.get("loud") is True for ev in received)


def test_rebase_records_intent_only(phase1_settings):
    """Phase 10D: /rebase records intent but does NOT execute a real
    withdrawal. The Phase 8 Capital Flow Engine remains the entry
    point for actual rebases."""
    bot = TelegramCommandCenter(settings=phase1_settings)
    res = bot.handle(Command(name="/rebase", user_id="alice"), confirmed=True)
    assert res.status is CommandStatus.OK
    assert bot.rebase_invocations == 1
    assert "no real withdrawal" in res.message.lower()


# ---------------------------------------------------------------------------
# Audit events
# ---------------------------------------------------------------------------
def test_every_handle_writes_telegram_command_received(
    phase1_settings, events_repo
):
    bot = TelegramCommandCenter(
        settings=phase1_settings, event_repo=events_repo
    )
    bot.handle(Command(name="/status", user_id="u1"))
    received = events_repo.list(event_type=EventType.TELEGRAM_COMMAND_RECEIVED)
    assert len(received) == 1
    assert received[0].payload["name"] == "/status"
    assert received[0].payload["user_id"] == "u1"


def test_audit_payload_redacts_credential_keys(phase1_settings, events_repo):
    bot = TelegramCommandCenter(
        settings=phase1_settings, event_repo=events_repo
    )
    cmd = Command(
        name="/status",
        user_id="u1",
        # Args may carry an arbitrary token-shaped string (the Issue
        # contract: tokens must never appear on disk).
        args=("A" * 64,),
    )
    bot.handle(cmd)
    received = events_repo.list(event_type=EventType.TELEGRAM_COMMAND_RECEIVED)
    audit = received[0]
    # The 64-char token-shaped string lands as [REDACTED] in the
    # audit row.
    assert "A" * 64 not in str(audit.payload)


# ---------------------------------------------------------------------------
# Export command routing
# ---------------------------------------------------------------------------
def test_export_command_without_handler_returns_execution_error(phase1_settings):
    bot = TelegramCommandCenter(settings=phase1_settings)
    res = bot.handle(
        Command(name="/export_test_data", user_id="u1", args=("24h",))
    )
    assert res.status is CommandStatus.EXECUTION_ERROR
    assert res.metadata["reason"] == "export_handler_missing"


def test_export_command_invokes_handler_callback(phase1_settings):
    captured = []

    def handler(command, settings, safety_snapshot):
        captured.append((command.name, command.args, settings, safety_snapshot))
        return type(
            "FakeResult",
            (),
            {
                "status": CommandStatus.OK,
                "message": "fake",
                "metadata": {},
            },
        )()

    bot = TelegramCommandCenter(
        settings=phase1_settings,
        export_handler=handler,
    )
    res = bot.handle(
        Command(name="/export_test_data", user_id="u1", args=("24h",))
    )
    assert res.status is CommandStatus.OK
    assert len(captured) == 1
    assert captured[0][0] == "/export_test_data"
    assert captured[0][1] == ("24h",)
    snapshot = captured[0][3]
    # Phase 1 safety lock is reflected in the snapshot.
    assert snapshot["trading_mode"] == "paper"
    assert snapshot["live_trading_enabled"] is False
    assert snapshot["llm_enabled"] is False


def test_export_handler_exception_does_not_raise(phase1_settings):
    def broken_handler(command, settings, safety_snapshot):
        raise RuntimeError("upstream failure")

    bot = TelegramCommandCenter(
        settings=phase1_settings,
        export_handler=broken_handler,
    )
    # MUST NOT raise into the caller.
    res = bot.handle(
        Command(name="/export_events", user_id="u1", args=("24h",))
    )
    assert res.status is CommandStatus.EXECUTION_ERROR
    assert res.metadata["reason"] == "export_handler_exception"


# ---------------------------------------------------------------------------
# /kill_all does NOT call any real exchange surface
# ---------------------------------------------------------------------------
def test_kill_all_metadata_marks_no_real_order(phase1_settings):
    bot = TelegramCommandCenter(settings=phase1_settings)
    res = bot.handle(Command(name="/kill_all", user_id="alice"))
    assert res.status is CommandStatus.OK
    # The Phase 10D contract is captured in the message text.
    assert "no real exchange order" in res.message.lower()
    # The command center NEVER imports ExchangeClientBase.create_order.
    import app.telegram.bot as bot_mod

    src = bot_mod.__file__
    text = open(src, encoding="utf-8").read()
    assert ".create_order" not in text
    assert ".cancel_order" not in text
    assert ".set_leverage" not in text
    assert ".set_margin_mode" not in text
