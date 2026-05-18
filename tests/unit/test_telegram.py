"""Telegram Command Center skeleton tests."""

from __future__ import annotations

from app.core.events import EventType
from app.telegram.bot import TelegramCommandCenter
from app.telegram.commands import Command, CommandStatus


def test_unknown_command(phase1_settings, events_repo):
    bot = TelegramCommandCenter(settings=phase1_settings, event_repo=events_repo)
    res = bot.handle(Command(name="/launch_nukes", user_id="u1"))
    assert res.status is CommandStatus.UNKNOWN
    [audit] = events_repo.list(event_type=EventType.TELEGRAM_COMMAND_RECEIVED)
    assert audit.payload["name"] == "/launch_nukes"


def test_non_admin_denied_when_admins_configured(phase1_settings):
    bot = TelegramCommandCenter(settings=phase1_settings, admin_user_ids=frozenset({"alice"}))
    res = bot.handle(Command(name="/status", user_id="bob"))
    assert res.status is CommandStatus.DENIED


def test_resume_requires_confirmation(phase1_settings):
    bot = TelegramCommandCenter(settings=phase1_settings)
    res = bot.handle(Command(name="/resume", user_id="alice"))
    assert res.status is CommandStatus.NEEDS_CONFIRMATION

    res2 = bot.handle(Command(name="/resume", user_id="alice"), confirmed=True)
    assert res2.status is CommandStatus.OK


def test_status_acknowledged_in_paper_mode(phase1_settings):
    bot = TelegramCommandCenter(settings=phase1_settings)
    res = bot.handle(Command(name="/status", user_id="alice"))
    assert res.status is CommandStatus.OK
    assert res.metadata["trading_mode"] == "paper"
