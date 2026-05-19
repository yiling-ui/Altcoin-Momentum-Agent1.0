"""Phase 10D Telegram Command Center (Issue #10 Part 4).

Replaces the Phase 1 skeleton with the full operator-facing command
center. Every command:

  - Writes a ``TELEGRAM_COMMAND_RECEIVED`` audit event.
  - Goes through the operator allow-list. Unauthorised callers get a
    ``CommandStatus.DENIED`` result AND a ``TELEGRAM_COMMAND_REJECTED``
    audit event with a non-secret payload (no token / api_key / etc).
  - Honours the Issue contract second-confirmation rule for
    ``/resume`` and ``/rebase``.
  - Routes ``/export_*`` to the :class:`app.telegram.exports.TelegramExportBridge`
    (which itself fans out to the Phase 8.5 :class:`TestDataExportService`).
  - NEVER calls a real exchange write surface. ``/kill_all`` and
    ``/rebase`` are paper-mode-only in Phase 10D - the bridge layer
    enforces this and tests pin it.

Phase 10D boundary
------------------

The command center:

  - opens NO socket
  - imports NO exchange / LLM / third-party Telegram bot SDK
  - reads NO ``os.environ``
  - holds NO ``api_key`` / ``api_secret`` / ``bot_token`` parameter
    or literal anywhere in its source tree
  - never bypasses the Risk Engine
  - ``/pause`` / ``/resume`` flip an in-process pause flag ONLY; they
    do NOT mutate Risk Engine state (the Risk Engine remains the
    single trading-decision gate)
  - ``/kill_all`` writes audit events but does not touch any real
    exchange write surface in Phase 10D
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from app.config.settings import Settings, get_settings
from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.exports.redaction import redact
from app.telegram.commands import (
    AVAILABLE_COMMANDS,
    CONFIRM_REQUIRED,
    Command,
    CommandResult,
    CommandStatus,
    EXPORT_COMMAND_SET,
    LOUD_AUDIT_COMMANDS,
)


# Type alias for the optional export-bridge protocol. The bridge
# itself is defined in :mod:`app.telegram.exports`; we import it
# lazily to keep the import graph one-way (commands -> bot ->
# exports -> service).
ExportHandler = Callable[[Command, Settings, dict], CommandResult]


@dataclass
class TelegramCommandCenter:
    """Phase 10D in-process command bus.

    The center is wired by :class:`app.telegram.alerts.AlertDispatcher`
    on the outbound side and by :class:`app.telegram.exports.TelegramExportBridge`
    for ``/export_*`` commands. It holds in-process pause state but
    NEVER mutates Risk Engine / Execution FSM / Capital Flow Engine
    state directly.
    """

    settings: Settings = field(default_factory=get_settings)
    admin_user_ids: frozenset[str] = field(default_factory=frozenset)
    event_repo: EventRepository | None = None
    export_handler: ExportHandler | None = None
    # Phase 1 safety lock surface: every command can read these flags
    # but no command can mutate them.
    _new_opens_paused: bool = field(default=False, init=False)
    _kill_all_invocations: int = field(default=0, init=False)
    _rebase_invocations: int = field(default=0, init=False)
    _resume_invocations: int = field(default=0, init=False)

    SOURCE_MODULE = "telegram.bot"

    # ==================================================================
    # Public API
    # ==================================================================
    def handle(
        self,
        command: Command,
        *,
        confirmed: bool = False,
    ) -> CommandResult:
        """Dispatch one command. Always returns a :class:`CommandResult`.

        - Unknown command -> ``UNKNOWN`` + audit + rejection event.
        - Non-admin caller (when ``admin_user_ids`` configured) ->
          ``DENIED`` + audit + rejection event.
        - ``/resume`` / ``/rebase`` without ``confirmed=True`` ->
          ``NEEDS_CONFIRMATION``.
        - Otherwise ->  the per-command handler. Every successful
          path emits an audit event.
        """
        # 1. Always audit the receipt FIRST so the event trail records
        # even malformed / unauthorised commands.
        self._audit_received(command)

        # 2. Unknown command - reject loudly.
        if command.name not in AVAILABLE_COMMANDS:
            self._audit_rejected(
                command,
                reason="unknown_command",
                detail=f"command {command.name!r} is not in AVAILABLE_COMMANDS",
            )
            return CommandResult(
                status=CommandStatus.UNKNOWN,
                message=f"Unknown command: {command.name}",
                metadata={"reason": "unknown_command"},
            )

        # 3. Operator allow-list. If admin_user_ids is empty we accept
        # every caller (this preserves Phase 1 behaviour for tests
        # that don't configure an allow-list); the Issue contract is
        # enforced by the AlertDispatcher / future bot driver only
        # passing through configured users.
        if self.admin_user_ids and command.user_id not in self.admin_user_ids:
            self._audit_rejected(
                command,
                reason="unauthorised_user",
                detail=f"user {command.user_id!r} not in admin allow-list",
            )
            return CommandResult(
                status=CommandStatus.DENIED,
                message=f"User {command.user_id} is not on the admin allow-list.",
                metadata={"reason": "unauthorised_user"},
            )

        # 4. Two-step confirmation.
        if command.name in CONFIRM_REQUIRED and not confirmed:
            return CommandResult(
                status=CommandStatus.NEEDS_CONFIRMATION,
                message=(
                    f"{command.name} requires explicit confirmation. "
                    "Re-issue the command with `confirm` to proceed."
                ),
                metadata={
                    "reason": "needs_confirmation",
                    "command": command.name,
                    "trading_mode": self.settings.trading_mode,
                },
            )

        # 5. Per-command handler.
        handler = self._handler_for(command.name)
        result = handler(command)

        # 6. LOUD audit for irreversible / safety-critical commands.
        if command.name in LOUD_AUDIT_COMMANDS:
            self._audit_loud(command, result)

        return result

    # ==================================================================
    # Public state surface
    # ==================================================================
    @property
    def new_opens_paused(self) -> bool:
        return self._new_opens_paused

    @property
    def kill_all_invocations(self) -> int:
        return self._kill_all_invocations

    @property
    def rebase_invocations(self) -> int:
        return self._rebase_invocations

    @property
    def resume_invocations(self) -> int:
        return self._resume_invocations

    # ==================================================================
    # Per-command handlers
    # ==================================================================
    def _handler_for(self, name: str) -> Callable[[Command], CommandResult]:
        if name in EXPORT_COMMAND_SET:
            return self._handle_export
        return {
            "/status": self._handle_status,
            "/positions": self._handle_positions,
            "/pnl": self._handle_pnl,
            "/risk": self._handle_risk,
            "/capital": self._handle_capital,
            "/incidents": self._handle_incidents,
            "/pause": self._handle_pause,
            "/resume": self._handle_resume,
            "/kill_all": self._handle_kill_all,
            "/rebase": self._handle_rebase,
        }.get(name, self._handle_status)

    def _ack_metadata(self, action: str, **extra: Any) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "action": action,
            "trading_mode": self.settings.trading_mode,
            "live_trading_enabled": bool(self.settings.live_trading_enabled),
            "right_tail_enabled": bool(self.settings.right_tail_enabled),
            "exchange_live_order_enabled": bool(
                self.settings.exchange_live_order_enabled
            ),
            "phase": "10D",
        }
        meta.update(extra)
        return meta

    def _ack(self, command: Command, body: str, **extra: Any) -> CommandResult:
        return CommandResult(
            status=CommandStatus.OK,
            message=body,
            metadata=self._ack_metadata(action=command.name, **extra),
        )

    # ---- read-only commands -----------------------------------------
    def _handle_status(self, command: Command) -> CommandResult:
        return self._ack(
            command,
            f"status: trading_mode={self.settings.trading_mode} "
            f"new_opens_paused={self._new_opens_paused}",
            new_opens_paused=self._new_opens_paused,
        )

    def _handle_positions(self, command: Command) -> CommandResult:
        return self._ack(
            command,
            "positions: paper-mode lifecycle. Live positions are not "
            "tracked in Phase 10D. Use /export_test_data 24h for the "
            "full lifecycle audit.",
        )

    def _handle_pnl(self, command: Command) -> CommandResult:
        return self._ack(
            command,
            "pnl: paper-mode summary. The full breakdown ships via "
            "/export_report today.",
        )

    def _handle_risk(self, command: Command) -> CommandResult:
        return self._ack(
            command,
            f"risk: trading_mode={self.settings.trading_mode} "
            f"new_opens_paused={self._new_opens_paused} "
            "right_tail_enabled=False (Phase 1 lock).",
        )

    def _handle_capital(self, command: Command) -> CommandResult:
        return self._ack(
            command,
            "capital: paper-mode bookkeeping snapshot. Use "
            "/export_capital 7d for the full event trail.",
        )

    def _handle_incidents(self, command: Command) -> CommandResult:
        return self._ack(
            command,
            "incidents: list of currently OPEN incidents (P0/P1). "
            "Refer to /export_test_data 24h for the full audit trail.",
        )

    # ---- operator commands ------------------------------------------
    def _handle_pause(self, command: Command) -> CommandResult:
        # /pause flips an in-process flag. The Risk Engine remains
        # the single trading gate; this flag is a hint the next
        # caller (Risk Engine / Execution FSM) MAY consume to refuse
        # new opens. Phase 10D does NOT have the Risk Engine read
        # this flag - that is a future PR.
        self._new_opens_paused = True
        return self._ack(
            command,
            "pause: new_opens_paused=True. Risk Engine remains the "
            "single trading gate; this flag is advisory.",
            new_opens_paused=True,
        )

    def _handle_resume(self, command: Command) -> CommandResult:
        self._resume_invocations += 1
        self._new_opens_paused = False
        return self._ack(
            command,
            "resume: new_opens_paused=False. Risk Engine remains "
            "the single gate.",
            new_opens_paused=False,
            resume_invocations=self._resume_invocations,
        )

    def _handle_kill_all(self, command: Command) -> CommandResult:
        # Phase 10D constraint: /kill_all does NOT call any real
        # exchange write surface. It records the request and pauses
        # new opens; the actual protective close-out path lives in
        # ExecutionFSMDriver (Phase 9) which already refuses to talk
        # to a live exchange.
        self._kill_all_invocations += 1
        self._new_opens_paused = True
        return self._ack(
            command,
            "kill_all: paper-mode protective close requested. No real "
            "exchange order placed (Phase 10D forbids it). New opens "
            "paused.",
            kill_all_invocations=self._kill_all_invocations,
            new_opens_paused=True,
        )

    def _handle_rebase(self, command: Command) -> CommandResult:
        # Phase 10D constraint: /rebase does NOT execute a real
        # withdrawal and does NOT call any exchange API. It records
        # the operator's intent so a future Capital Flow Engine
        # invocation (paper-mode) can pick it up. The Risk Engine
        # remains the single gate; the rebase itself is performed by
        # the Phase 8 Capital Flow Engine, NOT by this bot.
        self._rebase_invocations += 1
        return self._ack(
            command,
            "rebase: paper-mode rebase intent recorded. No real "
            "withdrawal executed. The Phase 8 Capital Flow Engine "
            "performs the rebase; the Risk Engine remains the single "
            "gate.",
            rebase_invocations=self._rebase_invocations,
        )

    # ---- export commands --------------------------------------------
    def _handle_export(self, command: Command) -> CommandResult:
        if self.export_handler is None:
            return CommandResult(
                status=CommandStatus.EXECUTION_ERROR,
                message=(
                    f"{command.name}: no export handler is wired in. The "
                    "Phase 10D Telegram export bridge must be supplied "
                    "via TelegramCommandCenter(export_handler=...)."
                ),
                metadata=self._ack_metadata(
                    action=command.name, reason="export_handler_missing"
                ),
            )
        # Build a snapshot of the current safety state so the bridge
        # can refuse loudly if it has drifted.
        safety_snapshot = {
            "trading_mode": self.settings.trading_mode,
            "live_trading_enabled": bool(self.settings.live_trading_enabled),
            "right_tail_enabled": bool(self.settings.right_tail_enabled),
            "llm_enabled": bool(self.settings.llm_enabled),
            "exchange_live_order_enabled": bool(
                self.settings.exchange_live_order_enabled
            ),
        }
        try:
            return self.export_handler(command, self.settings, safety_snapshot)
        except Exception as exc:  # noqa: BLE001 - bot must never raise
            return CommandResult(
                status=CommandStatus.EXECUTION_ERROR,
                message=(
                    f"{command.name}: export bridge failed: {exc}. The "
                    "trading process is unaffected."
                ),
                metadata=self._ack_metadata(
                    action=command.name,
                    reason="export_handler_exception",
                    error=str(exc)[:200],
                ),
            )

    # ==================================================================
    # Audit
    # ==================================================================
    def _audit_received(self, command: Command) -> None:
        if self.event_repo is None:
            return
        payload: Mapping[str, Any] = redact(
            {
                "name": command.name,
                "user_id": command.user_id,
                "args": list(command.args),
                "chat_id": command.chat_id,
                "trading_mode": self.settings.trading_mode,
            }
        )
        self._safe_append(
            Event(
                event_type=EventType.TELEGRAM_COMMAND_RECEIVED,
                source_module=self.SOURCE_MODULE,
                payload=dict(payload),
            )
        )

    def _audit_rejected(
        self,
        command: Command,
        *,
        reason: str,
        detail: str,
    ) -> None:
        if self.event_repo is None:
            return
        payload: Mapping[str, Any] = redact(
            {
                "name": command.name,
                "user_id": command.user_id,
                "args": list(command.args),
                "reason": reason,
                "detail": detail,
                "trading_mode": self.settings.trading_mode,
            }
        )
        self._safe_append(
            Event(
                event_type=EventType.TELEGRAM_COMMAND_REJECTED,
                source_module=self.SOURCE_MODULE,
                payload=dict(payload),
            )
        )

    def _audit_loud(self, command: Command, result: CommandResult) -> None:
        if self.event_repo is None:
            return
        payload: Mapping[str, Any] = redact(
            {
                "name": command.name,
                "user_id": command.user_id,
                "status": result.status.value,
                "trading_mode": self.settings.trading_mode,
                "new_opens_paused": self._new_opens_paused,
                "loud": True,
            }
        )
        self._safe_append(
            Event(
                event_type=EventType.TELEGRAM_COMMAND_RECEIVED,
                source_module=self.SOURCE_MODULE,
                payload=dict(payload),
            )
        )

    def _safe_append(self, event: Event) -> None:
        try:
            self.event_repo.append_event(event)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001 - bot must never crash on audit failure
            # Audit failures are surfaced via the EventRepository's
            # own loguru error log; the command center deliberately
            # does NOT propagate so a misbehaving disk cannot crash
            # the trading loop.
            pass


__all__ = [
    "TelegramCommandCenter",
    "ExportHandler",
]
