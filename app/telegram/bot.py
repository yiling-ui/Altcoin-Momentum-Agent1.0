"""Telegram Command Center skeleton.

Phase 1 implements *only*:
    - command parsing via the `Command` value object
    - allow-list check (unknown commands -> CommandStatus.UNKNOWN)
    - admin allow-list check (non-admin user -> CommandStatus.DENIED)
    - second-confirmation flag for `/resume` and `/change_config`
    - audit-log emission via EventRepository (TELEGRAM_COMMAND_RECEIVED)

There is NO outbound network call and NO real bot token usage. Issue #10
(Phase 10) replaces this with the real `python-telegram-bot` adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config.settings import Settings, get_settings
from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.telegram.commands import (
    AVAILABLE_COMMANDS,
    Command,
    CommandResult,
    CommandStatus,
)


@dataclass
class TelegramCommandCenter:
    settings: Settings = field(default_factory=get_settings)
    admin_user_ids: frozenset[str] = field(default_factory=frozenset)
    event_repo: EventRepository | None = None

    # Commands that require a second confirmation per Spec §32.2.
    _CONFIRM_REQUIRED: frozenset[str] = frozenset({"/resume", "/change_config"})

    def handle(self, command: Command, *, confirmed: bool = False) -> CommandResult:
        """Dispatch a command. Phase 1 returns a stub result only."""
        self._audit(command)

        if command.name not in AVAILABLE_COMMANDS and command.name != "/change_config":
            return CommandResult(CommandStatus.UNKNOWN, f"Unknown command: {command.name}")

        if self.admin_user_ids and command.user_id not in self.admin_user_ids:
            return CommandResult(
                CommandStatus.DENIED,
                f"User {command.user_id} is not an authorised admin.",
            )

        if command.name in self._CONFIRM_REQUIRED and not confirmed:
            return CommandResult(
                CommandStatus.NEEDS_CONFIRMATION,
                f"{command.name} requires explicit confirmation.",
            )

        # Phase 1 does not implement side-effects. Each command returns a
        # paper-mode acknowledgement with a description of what Phase X will
        # plug in.
        return CommandResult(
            CommandStatus.OK,
            f"{command.name} acknowledged in Phase 1 paper mode (no side-effect).",
            metadata={"phase": "1", "trading_mode": self.settings.trading_mode},
        )

    # ------------------------------------------------------------------
    def _audit(self, command: Command) -> None:
        if self.event_repo is None:
            return
        self.event_repo.append(
            Event(
                event_type=EventType.TELEGRAM_COMMAND_RECEIVED,
                source_module="telegram",
                payload={
                    "name": command.name,
                    "user_id": command.user_id,
                    "args": list(command.args),
                },
            )
        )
