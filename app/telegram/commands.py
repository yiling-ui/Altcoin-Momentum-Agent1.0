"""Telegram command vocabulary (Spec §32.1).

Phase 1 only declares the shape of commands and their results. The actual
side-effects (pause / resume / kill_all) are implemented in later phases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# Spec §32.1
AVAILABLE_COMMANDS: tuple[str, ...] = (
    "/status",
    "/positions",
    "/pnl",
    "/pause",
    "/resume",
    "/kill_all",
    "/risk",
    "/capital",
    "/rebase",
    "/incidents",
)


class CommandStatus(str, Enum):
    OK = "ok"
    DENIED = "denied"
    UNKNOWN = "unknown"
    NEEDS_CONFIRMATION = "needs_confirmation"


@dataclass(frozen=True)
class Command:
    name: str
    user_id: str
    args: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandResult:
    status: CommandStatus
    message: str
    metadata: dict = field(default_factory=dict)
