"""Live kill switch (PR116 - 10U LIVE_LIMITED Launch Pack v0).

A thin, persisted, audited kill switch built on top of the PR114
:class:`app.live.telegram_state.LiveOperatorStateStore`. It strengthens
the PR114 ``/kill_all`` + ``/confirm_kill`` handshake into a reusable
component the readiness checker, the LIVE_SHADOW runner, the arming
workflow, and the Telegram console all share.

What the kill switch CAN do in PR116
------------------------------------
  * Block every NEW entry immediately when armed (a hard, in-process
    gate consulted by the execution permission context).
  * Surface its armed state in ``/status``, ``/kill_status`` and the
    readiness report.
  * Persist its armed state across a restart (atomic file write).
  * Optionally route a CONTROLLED reduce-only / emergency cancel-exit
    through the :class:`app.live.execution_gateway.LiveExecutionGateway`
    when (and only when) an execution callback is wired.

What the kill switch CANNOT do in PR116 (documented limit)
----------------------------------------------------------
  * It does NOT, by itself, guarantee real open positions are closed.
    Real cancel / exit only happens through the LiveExecutionGateway and
    only if a controlled-exit callback is wired AND the runtime is armed
    for live orders. When no callback is wired the kill switch ARMS +
    HALTS new entries and tells the operator, in plain language, that
    open positions must be closed manually on the exchange.
  * It NEVER claims a position is closed / an order is cancelled unless
    the exchange actually confirmed it (the gateway result is surfaced
    verbatim; an unwired kill switch reports ``manual_action_required``).

This module performs ONLY local state IO + (optionally) a gateway call.
It never opens a market socket itself and never flips a Phase 1 safety
flag.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable

from app.core.clock import now_ms
from app.core.events import Event, EventType
from app.live.telegram_state import (
    ConfirmationState,
    KillSwitchState,
    LiveOperatorStateStore,
)

LIVE_KILL_SWITCH_MODULE = "live.live_kill_switch"

DEFAULT_KILL_CONFIRMATION_TTL_MS = 5 * 60 * 1000  # 5 minutes

# Sentinels surfaced when a controlled exit cannot be executed.
KILL_EXIT_MANUAL_ACTION_REQUIRED = "manual_action_required_close_on_exchange"
KILL_EXIT_NO_GATEWAY_WIRED = "no_controlled_exit_callback_wired"


@dataclass(frozen=True)
class KillSwitchStatus:
    """Read-only kill switch status surfaced to the operator."""

    armed: bool
    blocks_new_entries: bool
    armed_at: int | None
    armed_by: str | None
    reason: str | None
    controlled_exit_supported: bool
    can_close_positions: bool
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "armed": self.armed,
            "blocks_new_entries": self.blocks_new_entries,
            "armed_at": self.armed_at,
            "armed_by": self.armed_by,
            "reason": self.reason,
            "controlled_exit_supported": self.controlled_exit_supported,
            "can_close_positions": self.can_close_positions,
            "note": self.note,
            # PR116 safety markers.
            "real_order": False,
            "trade_authority": False,
            "ai_trade_authority": False,
            "exchange_live_orders": False,
            "phase_12_forbidden": True,
        }

    def telegram_card(self) -> dict[str, Any]:
        card = {"card_type": "LIVE_KILL_STATUS"}
        card.update(self.to_dict())
        return card


class LiveKillSwitch:
    """Persisted, audited kill switch (PR116).

    Wraps a :class:`LiveOperatorStateStore`. ``controlled_exit_callback``
    is OPTIONAL: when supplied it MUST route any real cancel / reduce /
    exit through the PR113 execution gateway and return a result dict.
    When omitted the kill switch only arms + halts new entries and tells
    the operator that open positions need manual action.
    """

    def __init__(
        self,
        *,
        state_store: LiveOperatorStateStore | None = None,
        event_repo: Any | None = None,
        clock: Callable[[], int] = now_ms,
        confirmation_ttl_ms: int = DEFAULT_KILL_CONFIRMATION_TTL_MS,
        controlled_exit_callback: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._store = state_store or LiveOperatorStateStore()
        self._event_repo = event_repo
        self._clock = clock
        self._ttl = int(confirmation_ttl_ms)
        self._controlled_exit_callback = controlled_exit_callback

    # ------------------------------------------------------------------
    # Read state
    # ------------------------------------------------------------------
    @property
    def is_armed(self) -> bool:
        state, _ = self._store.load_kill_switch()
        return bool(state.armed)

    @property
    def controlled_exit_supported(self) -> bool:
        return self._controlled_exit_callback is not None

    def status(self) -> KillSwitchStatus:
        state, _ = self._store.load_kill_switch()
        supported = self.controlled_exit_supported
        note = (
            "Kill switch armed: new entries are blocked. A controlled "
            "reduce/exit is wired through the LiveExecutionGateway."
            if (state.armed and supported)
            else (
                "Kill switch armed: new entries are blocked. PR116 does "
                "NOT auto-close open positions; close them manually on the "
                "exchange (no controlled-exit callback wired)."
                if state.armed
                else "Kill switch ready (not armed). New entries permitted "
                "subject to all other gates."
            )
        )
        return KillSwitchStatus(
            armed=bool(state.armed),
            blocks_new_entries=bool(state.armed),
            armed_at=state.armed_at,
            armed_by=state.armed_by,
            reason=state.reason,
            controlled_exit_supported=supported,
            can_close_positions=bool(state.armed and supported),
            note=note,
        )

    # ------------------------------------------------------------------
    # Confirmation handshake (mirrors /kill_all -> /confirm_kill)
    # ------------------------------------------------------------------
    def request_arm(self, *, by: str = "operator") -> str:
        """Begin an arm request: returns a one-shot confirmation code."""
        code = "KILL-" + uuid.uuid4().hex[:8].upper()
        now = self._clock()
        conf, _ = self._store.load_confirmation()
        conf = ConfirmationState(
            pending_code=conf.pending_code,
            pending_target=conf.pending_target,
            pending_issued_at=conf.pending_issued_at,
            pending_expires_at=conf.pending_expires_at,
            live_limited_confirmed=conf.live_limited_confirmed,
            live_limited_confirmed_at=conf.live_limited_confirmed_at,
            pending_kill_code=code,
            pending_kill_expires_at=now + self._ttl,
        )
        self._store.save_confirmation(conf)
        self._emit(EventType.LIVE_KILL_SWITCH_ARM_REQUESTED, {"requested_by": by})
        return code

    def confirm_arm(self, code: str, *, by: str = "operator") -> dict[str, Any]:
        """Confirm + arm the kill switch iff the code matches and is fresh."""
        now = self._clock()
        conf, _ = self._store.load_confirmation()
        reject: list[str] = []
        if not conf.pending_kill_code:
            reject.append("no_pending_kill_request")
        elif code != conf.pending_kill_code:
            reject.append("kill_confirmation_code_mismatch")
        elif (
            conf.pending_kill_expires_at is not None
            and now > conf.pending_kill_expires_at
        ):
            reject.append("kill_confirmation_code_expired")

        if reject:
            return {"armed": self.is_armed, "ok": False, "reject_reasons": reject}

        result = self.arm(by=by, reason="operator_kill_all")
        # Clear the pending kill code.
        conf = ConfirmationState(
            pending_code=conf.pending_code,
            pending_target=conf.pending_target,
            pending_issued_at=conf.pending_issued_at,
            pending_expires_at=conf.pending_expires_at,
            live_limited_confirmed=conf.live_limited_confirmed,
            live_limited_confirmed_at=conf.live_limited_confirmed_at,
            pending_kill_code=None,
            pending_kill_expires_at=None,
        )
        self._store.save_confirmation(conf)
        return result

    # ------------------------------------------------------------------
    # Arm / disarm
    # ------------------------------------------------------------------
    def arm(self, *, by: str = "operator", reason: str = "operator_kill_all") -> dict[str, Any]:
        """Arm the kill switch + pause the runtime + run a controlled exit.

        New entries are blocked immediately (the persisted armed flag is
        the source of truth consulted by the execution context). If a
        controlled-exit callback is wired it is invoked (it MUST route
        through the LiveExecutionGateway); otherwise the result records
        that open positions need manual action.
        """
        now = self._clock()
        state = KillSwitchState(armed=True, armed_at=now, armed_by=by, reason=reason)
        self._store.save_kill_switch(state)

        # Pause the runtime as a belt-and-braces halt of new entries.
        runtime, _ = self._store.load_runtime_mode()
        runtime.paused = True
        runtime.updated_at = now
        runtime.updated_by = by
        self._store.save_runtime_mode(runtime)

        controlled_action = self.controlled_exit()
        self._emit(
            EventType.LIVE_KILL_SWITCH,
            {"by": by, "reason": reason, "controlled_action": controlled_action},
        )
        return {
            "armed": True,
            "ok": True,
            "blocks_new_entries": True,
            "controlled_action": controlled_action,
        }

    def disarm(self, *, by: str = "operator") -> dict[str, Any]:
        """Disarm the kill switch (operator-only, audited).

        Disarming does NOT itself resume scanning; the operator still has
        to ``/resume``. It only clears the emergency-halt flag.
        """
        state = KillSwitchState(armed=False, armed_at=None, armed_by=by, reason="operator_disarm")
        self._store.save_kill_switch(state)
        self._emit(EventType.LIVE_KILL_SWITCH, {"by": by, "reason": "disarm", "armed": False})
        return {"armed": False, "ok": True}

    # ------------------------------------------------------------------
    # Controlled exit (only through the gateway, never silent)
    # ------------------------------------------------------------------
    def controlled_exit(self) -> dict[str, Any]:
        """Run the wired controlled-exit callback, or report manual action.

        NEVER claims a position closed / order cancelled unless the
        callback (which routes through the LiveExecutionGateway) actually
        confirms it. With no callback wired this returns a clear
        ``manual_action_required`` result.
        """
        if self._controlled_exit_callback is None:
            return {
                "executed": False,
                "reason": KILL_EXIT_NO_GATEWAY_WIRED,
                "operator_action": KILL_EXIT_MANUAL_ACTION_REQUIRED,
                "positions_closed_claimed": False,
            }
        try:
            result = self._controlled_exit_callback()
        except Exception:  # pragma: no cover - kill must never crash
            return {
                "executed": False,
                "reason": "controlled_exit_callback_failed",
                "operator_action": KILL_EXIT_MANUAL_ACTION_REQUIRED,
                "positions_closed_claimed": False,
            }
        out = {"executed": True, "positions_closed_claimed": False}
        if isinstance(result, dict):
            out.update(result)
        return out

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def _emit(self, event_type: EventType, payload: dict[str, Any]) -> None:
        if self._event_repo is None:
            return
        try:
            self._event_repo.append(
                Event(
                    event_type=event_type,
                    source_module=LIVE_KILL_SWITCH_MODULE,
                    payload={
                        **payload,
                        "trade_authority": False,
                        "ai_trade_authority": False,
                        "exchange_live_orders": False,
                        "phase_12_forbidden": True,
                    },
                )
            )
        except Exception:  # pragma: no cover - audit must never crash a kill
            pass


__all__ = [
    "LIVE_KILL_SWITCH_MODULE",
    "DEFAULT_KILL_CONFIRMATION_TTL_MS",
    "KILL_EXIT_MANUAL_ACTION_REQUIRED",
    "KILL_EXIT_NO_GATEWAY_WIRED",
    "KillSwitchStatus",
    "LiveKillSwitch",
]
