"""Telegram Command Center package (Spec §32, Issue #1 skeleton, Issue #10 full).

Phase 1 ships an in-process command bus only - NO outbound network calls,
NO bot token consumption. The skeleton lets us write tests today and lets
Issue #10 plug in the real `python-telegram-bot` adapter without touching
callers.
"""

from app.telegram import formatter as formatter
from app.telegram.bot import TelegramCommandCenter
from app.telegram.commands import (
    AVAILABLE_COMMANDS,
    Command,
    CommandResult,
    CommandStatus,
)

__all__ = [
    "TelegramCommandCenter",
    "Command",
    "CommandResult",
    "CommandStatus",
    "AVAILABLE_COMMANDS",
    "formatter",
]
