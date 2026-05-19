"""Telegram command vocabulary (Phase 10D - Issue #10 Part 4).

Phase 10D extends the Phase 1 skeleton (Spec §32.1) with the full
command set the Issue #10 Part 4 brief requires. The operator-facing
commands fall into three groups:

  - Read-only status: ``/status`` ``/positions`` ``/pnl`` ``/risk``
                      ``/capital`` ``/incidents``
  - Operator action:  ``/pause`` ``/resume`` ``/kill_all`` ``/rebase``
  - File export:      ``/export_test_data`` ``/export_events``
                      ``/export_rejections`` ``/export_capital``
                      ``/export_report`` ``/export_learning_dataset``

Each command is dispatched by :class:`app.telegram.bot.TelegramCommandCenter`.
The Issue contract:

  - Every command writes ``TELEGRAM_COMMAND_RECEIVED``.
  - Unauthorised users get ``TELEGRAM_COMMAND_REJECTED`` and a
    rejection reply.
  - ``/resume`` and ``/rebase`` require explicit second confirmation.
  - ``/kill_all`` may run without a second confirmation but MUST be
    audited and MUST NOT place any real exchange order in Phase 10D.
  - No command bypasses the Risk Engine or modifies the Phase 1
    safety lock.
  - No command triggers a real exchange write surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Command sets (Spec §32.1 + Issue #10 Part 4)
# ---------------------------------------------------------------------------
STATUS_COMMANDS: tuple[str, ...] = (
    "/status",
    "/positions",
    "/pnl",
    "/risk",
    "/capital",
    "/incidents",
)

OPERATOR_COMMANDS: tuple[str, ...] = (
    "/pause",
    "/resume",
    "/kill_all",
    "/rebase",
)

EXPORT_COMMANDS: tuple[str, ...] = (
    "/export_test_data",
    "/export_events",
    "/export_rejections",
    "/export_capital",
    "/export_report",
    "/export_learning_dataset",
)

AVAILABLE_COMMANDS: tuple[str, ...] = (
    *STATUS_COMMANDS,
    *OPERATOR_COMMANDS,
    *EXPORT_COMMANDS,
)

# Commands that REQUIRE explicit second confirmation per Issue brief.
CONFIRM_REQUIRED: frozenset[str] = frozenset(
    {
        "/resume",
        "/rebase",
        # Phase 1 also required this, kept for backwards compatibility.
        "/change_config",
    }
)

# Commands that MAY run without confirmation but MUST be audited
# loudly. The Issue brief: "/kill_all may execute quickly but must
# be recorded".
LOUD_AUDIT_COMMANDS: frozenset[str] = frozenset(
    {
        "/kill_all",
        "/pause",
    }
)

# Export commands - dispatched via the Phase 8.5 TestDataExportService.
EXPORT_COMMAND_SET: frozenset[str] = frozenset(EXPORT_COMMANDS)


class CommandStatus(str, Enum):
    OK = "ok"
    DENIED = "denied"
    UNKNOWN = "unknown"
    NEEDS_CONFIRMATION = "needs_confirmation"
    INVALID_ARGUMENT = "invalid_argument"
    EXECUTION_ERROR = "execution_error"


@dataclass(frozen=True)
class Command:
    name: str
    user_id: str
    args: tuple[str, ...] = ()
    chat_id: str | None = None
    raw_text: str | None = None


@dataclass(frozen=True)
class CommandResult:
    status: CommandStatus
    message: str
    metadata: dict = field(default_factory=dict)


__all__ = [
    "STATUS_COMMANDS",
    "OPERATOR_COMMANDS",
    "EXPORT_COMMANDS",
    "EXPORT_COMMAND_SET",
    "AVAILABLE_COMMANDS",
    "CONFIRM_REQUIRED",
    "LOUD_AUDIT_COMMANDS",
    "Command",
    "CommandResult",
    "CommandStatus",
]
