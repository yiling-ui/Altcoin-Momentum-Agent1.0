"""Runtime Mode Guard (PR110 - Live Foundation v0).

Two live-preparation operating modes:

  - ``LIVE_SHADOW`` (*空盘跑*) - read-only live context. Reads market
    data / balance / positions / exchangeInfo and produces a shadow
    plan + Telegram push. ``real_order=False``,
    ``real_capital_changed=False``. NEVER places / cancels an order,
    changes leverage, or changes margin mode.

  - ``LIVE_LIMITED`` (*有资金跑*) - real small-capital trading is
    permitted IN PRINCIPLE. PR110 does NOT implement real orders.
    Arming ``LIVE_LIMITED`` requires:
      1. a persisted operator confirmation state,
      2. a capital profile that allows real orders + the LIVE_LIMITED
         mode (the PR110 initial profile is ``L1_10U_PROBE``),
      3. an armed kill switch.

Hard rules (PR110):
  - The DEFAULT mode is ``LIVE_SHADOW``.
  - A bare restart / default config can NEVER silently enter
    ``LIVE_LIMITED``. :meth:`LiveModeGuard.from_config` always boots in
    ``LIVE_SHADOW`` regardless of what the config says.
  - Without a completed confirmation handshake, every real order
    attempt is refused.
  - Every switch / arm / disarm is audited.

PR110 boundary: nothing here places a real order. Even a fully-armed
``LIVE_LIMITED`` still refuses real orders because no live execution
adapter exists yet (:class:`LiveExecutionGateway`).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from app.core.clock import now_ms
from app.core.enums import LiveRuntimeMode
from app.core.errors import LiveModeViolation
from app.core.events import Event, EventType
from app.live.capital_profile import (
    CapitalProfileId,
    get_profile,
)

LIVE_RUNTIME_MODE_MODULE = "live.runtime_mode"

# The only capital profile PR110 permits a LIVE_LIMITED arm to use.
PR110_INITIAL_LIVE_LIMITED_PROFILE = CapitalProfileId.L1_10U_PROBE


@dataclass
class LiveModeState:
    """Persisted live-mode state (``live_mode_persisted_state``).

    Serialisable to / from a plain dict so a future PR can persist it
    to a database. PR110 keeps it in process.

    NOTE: ``runtime_mode`` is included for completeness, but
    :meth:`LiveModeGuard.from_state` deliberately refuses to *resume*
    into an armed ``LIVE_LIMITED`` on construction - a restart always
    requires a fresh confirmation handshake. The persisted
    ``confirmation_state`` records only that the operator has *ever*
    confirmed; it is not sufficient to arm on its own.
    """

    runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_SHADOW
    capital_profile_id: CapitalProfileId = CapitalProfileId.L0_SHADOW
    live_limited_confirmation_state: bool = False
    live_limited_armed: bool = False
    live_limited_armed_at: int | None = None
    live_limited_armed_by: str | None = None
    kill_switch_armed: bool = False
    pending_confirmation_code: str | None = None
    pending_target_mode: LiveRuntimeMode | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["runtime_mode"] = self.runtime_mode.value
        d["capital_profile_id"] = self.capital_profile_id.value
        d["pending_target_mode"] = (
            self.pending_target_mode.value
            if self.pending_target_mode is not None
            else None
        )
        return d


@dataclass(frozen=True)
class LiveModeSwitchRequest:
    """The risk summary + confirmation code returned for a switch request.

    The operator sees this after ``/mode live_limited`` and must reply
    ``/confirm_live <confirmation_code>`` to proceed.
    """

    confirmation_code: str
    target_mode: LiveRuntimeMode
    current_mode: LiveRuntimeMode
    capital_profile_id: CapitalProfileId
    account_equity_usdt: float
    max_account_capital_usdt: float
    max_position_notional_usdt: float
    max_daily_loss_usdt: float
    max_total_loss_usdt: float
    max_leverage: float
    kill_switch_armed: bool
    real_orders_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "confirmation_code": self.confirmation_code,
            "target_mode": self.target_mode.value,
            "current_mode": self.current_mode.value,
            "capital_profile_id": self.capital_profile_id.value,
            "account_equity_usdt": self.account_equity_usdt,
            "max_account_capital_usdt": self.max_account_capital_usdt,
            "max_position_notional_usdt": self.max_position_notional_usdt,
            "max_daily_loss_usdt": self.max_daily_loss_usdt,
            "max_total_loss_usdt": self.max_total_loss_usdt,
            "max_leverage": self.max_leverage,
            "kill_switch_armed": self.kill_switch_armed,
            "real_orders_allowed": self.real_orders_allowed,
        }


@dataclass(frozen=True)
class LiveModeSwitchResult:
    """Outcome of a confirm / disarm attempt."""

    success: bool
    runtime_mode: LiveRuntimeMode
    reason: str
    reject_reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "runtime_mode": self.runtime_mode.value,
            "reason": self.reason,
            "reject_reasons": list(self.reject_reasons),
        }


class LiveModeGuard:
    """Owns and protects the live runtime mode + confirmation handshake."""

    def __init__(
        self,
        *,
        state: LiveModeState | None = None,
        event_repo: Any | None = None,
    ) -> None:
        self._state = state or LiveModeState()
        # Hard safety floor on construction: never come up armed.
        self._state.runtime_mode = LiveRuntimeMode.LIVE_SHADOW
        self._state.live_limited_armed = False
        self._state.pending_confirmation_code = None
        self._state.pending_target_mode = None
        self._event_repo = event_repo
        self._emit(EventType.LIVE_SHADOW_ACTIVE, reason="boot_default_shadow")

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @classmethod
    def from_config(cls, live_config: Any, *, event_repo: Any | None = None) -> "LiveModeGuard":
        """Build a guard from a ``LiveConfig``-like object.

        ALWAYS boots in ``LIVE_SHADOW`` regardless of the configured
        ``runtime_mode`` - a restart can never silently enter
        ``LIVE_LIMITED``. The configured capital profile + kill-switch
        flag are read, but arming still requires the runtime handshake.
        """
        profile_id = getattr(live_config, "capital_profile_id", "L0_SHADOW")
        try:
            profile_id = CapitalProfileId(profile_id)
        except ValueError:
            profile_id = CapitalProfileId.L0_SHADOW
        state = LiveModeState(
            runtime_mode=LiveRuntimeMode.LIVE_SHADOW,
            capital_profile_id=profile_id,
            kill_switch_armed=bool(getattr(live_config, "kill_switch_armed", False)),
            live_limited_confirmation_state=bool(
                getattr(live_config, "live_limited_confirmation_state", False)
            ),
        )
        return cls(state=state, event_repo=event_repo)

    # ------------------------------------------------------------------
    # Read-only introspection
    # ------------------------------------------------------------------
    @property
    def runtime_mode(self) -> LiveRuntimeMode:
        return self._state.runtime_mode

    @property
    def state(self) -> LiveModeState:
        return self._state

    @property
    def is_live_limited_armed(self) -> bool:
        return (
            self._state.runtime_mode is LiveRuntimeMode.LIVE_LIMITED
            and self._state.live_limited_armed
            and self._state.live_limited_confirmation_state
        )

    @property
    def real_orders_allowed(self) -> bool:
        """True only when LIVE_LIMITED is fully armed AND the profile
        allows real orders. Still does NOT mean PR110 will place an
        order - the live adapter does not exist."""
        if not self.is_live_limited_armed:
            return False
        return get_profile(self._state.capital_profile_id).real_orders_allowed

    # ------------------------------------------------------------------
    # Kill switch (operator-armed; real API health checks land later)
    # ------------------------------------------------------------------
    def arm_kill_switch(self, *, by: str = "operator") -> None:
        """Arm the kill switch.

        PR110 models operator arming only. The real arming gate (API
        health check, reconciliation ready, etc.) lands in a later PR;
        the default config keeps ``kill_switch_armed=False``.
        """
        self._state.kill_switch_armed = True
        self._state.live_limited_armed_by = by

    def disarm_kill_switch(self) -> None:
        self._state.kill_switch_armed = False

    # ------------------------------------------------------------------
    # Switch handshake
    # ------------------------------------------------------------------
    def request_live_limited(
        self,
        *,
        account_equity_usdt: float = 0.0,
        requested_by: str = "operator",
    ) -> LiveModeSwitchRequest:
        """Begin a LIVE_SHADOW -> LIVE_LIMITED switch.

        Returns a risk summary + a confirmation code. The switch is NOT
        applied here; the operator must call :meth:`confirm_live` with
        the returned code.
        """
        profile = get_profile(self._state.capital_profile_id)
        code = "LIVE-" + uuid.uuid4().hex[:8].upper()
        self._state.pending_confirmation_code = code
        self._state.pending_target_mode = LiveRuntimeMode.LIVE_LIMITED
        summary = LiveModeSwitchRequest(
            confirmation_code=code,
            target_mode=LiveRuntimeMode.LIVE_LIMITED,
            current_mode=self._state.runtime_mode,
            capital_profile_id=self._state.capital_profile_id,
            account_equity_usdt=float(account_equity_usdt),
            max_account_capital_usdt=profile.max_account_capital_usdt,
            max_position_notional_usdt=profile.max_position_notional_usdt,
            max_daily_loss_usdt=profile.max_daily_loss_usdt,
            max_total_loss_usdt=profile.max_total_loss_usdt,
            max_leverage=profile.max_leverage,
            kill_switch_armed=self._state.kill_switch_armed,
            real_orders_allowed=profile.real_orders_allowed,
        )
        self._emit(
            EventType.LIVE_MODE_SWITCH_REQUESTED,
            reason="operator_requested_live_limited",
            extra={"requested_by": requested_by, "summary": summary.to_dict()},
        )
        return summary

    def confirm_live(self, confirmation_code: str, *, by: str = "operator") -> LiveModeSwitchResult:
        """Complete the handshake and arm LIVE_LIMITED if all gates pass.

        Gates:
          - a switch must have been requested (pending code present),
          - the code must match,
          - the active profile must allow real orders + LIVE_LIMITED,
          - the kill switch must be armed.

        On success: confirmation_state=True, armed=True,
        runtime_mode=LIVE_LIMITED. On failure: stays LIVE_SHADOW and a
        ``LIVE_MODE_SWITCH_REJECTED`` event is emitted.
        """
        reject: list[str] = []
        if not self._state.pending_confirmation_code:
            reject.append("no_pending_switch_request")
        elif confirmation_code != self._state.pending_confirmation_code:
            reject.append("confirmation_code_mismatch")

        profile = get_profile(self._state.capital_profile_id)
        if not profile.real_orders_allowed:
            reject.append("profile_does_not_allow_real_orders")
        if LiveRuntimeMode.LIVE_LIMITED not in profile.mode_allowed:
            reject.append("profile_does_not_allow_live_limited")
        if not self._state.kill_switch_armed:
            reject.append("kill_switch_not_armed")

        if reject:
            self._clear_pending()
            self._emit(
                EventType.LIVE_MODE_SWITCH_REJECTED,
                reason="confirm_live_rejected",
                extra={"reject_reasons": reject, "by": by},
            )
            return LiveModeSwitchResult(
                success=False,
                runtime_mode=self._state.runtime_mode,
                reason="confirm_live_rejected",
                reject_reasons=tuple(reject),
            )

        # All gates passed - arm LIVE_LIMITED.
        self._state.live_limited_confirmation_state = True
        self._state.live_limited_armed = True
        self._state.runtime_mode = LiveRuntimeMode.LIVE_LIMITED
        self._state.live_limited_armed_at = now_ms()
        self._state.live_limited_armed_by = by
        self._clear_pending()
        self._emit(EventType.LIVE_MODE_SWITCH_CONFIRMED, reason="confirm_live_ok", extra={"by": by})
        self._emit(EventType.LIVE_LIMITED_ARMED, reason="live_limited_armed", extra={"by": by})
        self._emit(EventType.LIVE_LIMITED_ACTIVE, reason="live_limited_active")
        return LiveModeSwitchResult(
            success=True,
            runtime_mode=self._state.runtime_mode,
            reason="live_limited_armed",
        )

    def disarm_live_limited(self, *, reason: str = "operator_disarm", by: str = "operator") -> LiveModeSwitchResult:
        """Return to LIVE_SHADOW and disarm LIVE_LIMITED."""
        was_armed = self._state.live_limited_armed
        self._state.live_limited_armed = False
        self._state.runtime_mode = LiveRuntimeMode.LIVE_SHADOW
        self._clear_pending()
        if was_armed:
            self._emit(EventType.LIVE_LIMITED_DISARMED, reason=reason, extra={"by": by})
        self._emit(EventType.LIVE_SHADOW_ACTIVE, reason=reason)
        return LiveModeSwitchResult(
            success=True,
            runtime_mode=self._state.runtime_mode,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Enforcement
    # ------------------------------------------------------------------
    def assert_live_orders_allowed(self) -> None:
        """Raise unless LIVE_LIMITED is fully armed.

        In LIVE_SHADOW, or in LIVE_LIMITED without a completed
        confirmation handshake, every real order attempt is refused.
        """
        if self._state.runtime_mode is LiveRuntimeMode.LIVE_SHADOW:
            raise LiveModeViolation(
                "real orders are forbidden in LIVE_SHADOW (空盘跑); the "
                "runtime must be in armed LIVE_LIMITED."
            )
        if not self.is_live_limited_armed:
            raise LiveModeViolation(
                "LIVE_LIMITED is not armed; a persisted operator "
                "confirmation handshake is required before any real "
                "order attempt is permitted."
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _clear_pending(self) -> None:
        self._state.pending_confirmation_code = None
        self._state.pending_target_mode = None

    def _emit(self, event_type: EventType, *, reason: str, extra: dict[str, Any] | None = None) -> None:
        if self._event_repo is None:
            return
        payload: dict[str, Any] = {
            "reason": reason,
            "runtime_mode": self._state.runtime_mode.value,
            "capital_profile_id": self._state.capital_profile_id.value,
            "live_limited_armed": self._state.live_limited_armed,
            "live_limited_confirmation_state": self._state.live_limited_confirmation_state,
            "kill_switch_armed": self._state.kill_switch_armed,
            # PR110 safety markers:
            "live_trading": False,
            "exchange_live_orders": False,
            "binance_private_api_enabled": False,
            "phase_12_forbidden": True,
        }
        if extra:
            payload.update(extra)
        self._event_repo.append(
            Event(
                event_type=event_type,
                source_module=LIVE_RUNTIME_MODE_MODULE,
                payload=payload,
            )
        )


__all__ = [
    "LIVE_RUNTIME_MODE_MODULE",
    "PR110_INITIAL_LIVE_LIMITED_PROFILE",
    "LiveModeState",
    "LiveModeSwitchRequest",
    "LiveModeSwitchResult",
    "LiveModeGuard",
]
