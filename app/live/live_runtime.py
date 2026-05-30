"""Live runtime (PR116 - 10U LIVE_LIMITED Launch Pack v0).

The single place that resolves the *active* capital profile and turns it
into the dynamic risk / execution caps every live decision must read. It
is the piece that makes the brief's "no new PR required for capital
scaling" requirement true:

  * NOTHING here hardcodes 10U. ``L1_10U_PROBE`` is only the default
    initial profile; the runtime supports switching to any profile on the
    PR110 ladder (L1_1U .. L8_10M) through persistent state / env /
    Telegram - WITHOUT a code change.
  * Every order / risk decision reads the active profile DYNAMICALLY via
    :meth:`LiveRuntime.active_profile` / :meth:`LiveRuntime.profile_caps`.
  * Profile escalation is NEVER automatic. When account equity exceeds
    the active profile band the runtime emits ``CAPITAL_PROFILE_MISMATCH``
    and CAPS usable capital at the active profile until the operator
    explicitly switches profile.
  * Deposits / withdrawals affect profile evaluation (through the truthful
    equity) but never pollute strategy PnL (PR112 funding-aware PnL keeps
    external flows separate).

It also re-asserts the PR110/PR114 live-source isolation: only
``OrderSource.LIVE`` may drive live mutation/execution, and no
simulation market source (MockExchange / HistoricalMarketStore / ...)
may ever be selected as a live market source.

This module performs ONLY local state IO (through the state store). It
never opens a market socket, never places an order, and never flips a
Phase 1 safety flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.core.clock import now_ms
from app.core.enums import LiveRuntimeMode, OrderSource
from app.core.errors import LiveSourceRejected
from app.core.events import Event, EventType
from app.live.api_config import LiveApiConfig
from app.live.capital_profile import (
    AUTO_ESCALATION_ALLOWED,
    CapitalProfile,
    CapitalProfileId,
    ProfileMismatch,
    detect_profile_mismatch,
    get_profile,
    suggest_profile_for_equity,
)
from app.live.capital_state import LiveCapitalState
from app.live.execution_gateway import ExecutionPermissionContext
from app.live.live_risk_engine import (
    CapitalProfileState,
    evaluate_capital_profile_state,
)
from app.live.path_isolation import SIM_SOURCE_MODULES
from app.live.telegram_state import (
    CapitalProfileStateRecord,
    LiveOperatorStateStore,
)

LIVE_RUNTIME_MODULE = "live.live_runtime"

# The initial default funded profile (the brief's starting point). The
# runtime does NOT special-case it beyond using it as the default.
DEFAULT_INITIAL_PROFILE = CapitalProfileId.L1_10U_PROBE

# The full set of funded profiles the runtime supports switching between
# (everything on the ladder except the shadow profile). Used so a profile
# switch never needs a code change.
SWITCHABLE_PROFILE_IDS: tuple[CapitalProfileId, ...] = tuple(
    pid for pid in CapitalProfileId if pid is not CapitalProfileId.L0_SHADOW
)

# Class names that may NEVER be used as a live market / capital source.
# (Re-uses the PR110 isolation map + a couple of explicit aliases.)
FORBIDDEN_LIVE_SOURCE_CLASSES: frozenset[str] = frozenset(
    set(SIM_SOURCE_MODULES.keys())
    | {
        "MockExchange",
        "MockExchangeClient",
        "HistoricalMarketStore",
        "ReplayFeedProvider",
        "SimulatedCapitalFlowEngine",
        "SimulatedCapitalFlow",
        "BlindWalkForwardRunner",
        "PaperShadowStrategyBridge",
    }
)


@dataclass(frozen=True)
class LiveProfileCaps:
    """The active profile's caps, read DYNAMICALLY by every live decision.

    Every field maps 1:1 onto a :class:`app.live.capital_profile.
    CapitalProfile` constraint. Order / risk code reads these caps; it
    NEVER hardcodes a 10U constant. Switching profile changes every cap
    here without a code change.
    """

    capital_profile_id: CapitalProfileId
    max_account_capital_usdt: float
    max_position_notional_usdt: float
    max_position_pct_of_equity: float
    max_active_positions: int
    max_symbol_exposure_pct: float
    max_daily_loss_usdt: float
    max_total_loss_usdt: float
    base_leverage: float
    max_leverage: float
    right_tail_boost_allowed: bool
    right_tail_max_leverage: float
    liquidity_floor_usdt: float
    max_slippage_bps: float
    kill_switch_drawdown_pct: float
    real_orders_allowed: bool

    @classmethod
    def from_profile(cls, profile: CapitalProfile) -> "LiveProfileCaps":
        return cls(
            capital_profile_id=profile.profile_id,
            max_account_capital_usdt=profile.max_account_capital_usdt,
            max_position_notional_usdt=profile.max_position_notional_usdt,
            max_position_pct_of_equity=profile.max_position_pct_of_equity,
            max_active_positions=profile.max_active_positions,
            max_symbol_exposure_pct=profile.max_symbol_exposure_pct,
            max_daily_loss_usdt=profile.max_daily_loss_usdt,
            max_total_loss_usdt=profile.max_total_loss_usdt,
            base_leverage=profile.base_leverage,
            max_leverage=profile.max_leverage,
            right_tail_boost_allowed=profile.right_tail_boost_allowed,
            right_tail_max_leverage=profile.right_tail_max_leverage,
            liquidity_floor_usdt=profile.liquidity_floor_usdt,
            max_slippage_bps=profile.max_slippage_bps,
            kill_switch_drawdown_pct=profile.kill_switch_drawdown_pct,
            real_orders_allowed=profile.real_orders_allowed,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "capital_profile_id": self.capital_profile_id.value,
            "max_account_capital_usdt": self.max_account_capital_usdt,
            "max_position_notional_usdt": self.max_position_notional_usdt,
            "max_position_pct_of_equity": self.max_position_pct_of_equity,
            "max_active_positions": self.max_active_positions,
            "max_symbol_exposure_pct": self.max_symbol_exposure_pct,
            "max_daily_loss_usdt": self.max_daily_loss_usdt,
            "max_total_loss_usdt": self.max_total_loss_usdt,
            "base_leverage": self.base_leverage,
            "max_leverage": self.max_leverage,
            "right_tail_boost_allowed": self.right_tail_boost_allowed,
            "right_tail_max_leverage": self.right_tail_max_leverage,
            "liquidity_floor_usdt": self.liquidity_floor_usdt,
            "max_slippage_bps": self.max_slippage_bps,
            "kill_switch_drawdown_pct": self.kill_switch_drawdown_pct,
            "real_orders_allowed": self.real_orders_allowed,
        }


class LiveRuntime:
    """Resolves the active capital profile + builds dynamic live caps.

    The active profile is resolved (in priority order):
      1. an explicit ``capital_profile_id`` passed to the constructor,
      2. the persisted operator state (set via Telegram ``/profile set``),
      3. the config / env (``AMA_LIVE_CAPITAL_PROFILE_ID`` / alias),
      4. the shadow profile ``L0_SHADOW`` as the safe fallback.

    The runtime mode follows the same persistent-state-first rule. A bare
    boot is always LIVE_SHADOW unless persistent state + a recorded
    confirmation say otherwise (the PR114 store enforces that fail-safe).
    """

    def __init__(
        self,
        config: LiveApiConfig | None = None,
        *,
        state_store: LiveOperatorStateStore | None = None,
        capital_profile_id: CapitalProfileId | str | None = None,
        event_repo: Any | None = None,
        clock: Callable[[], int] = now_ms,
    ) -> None:
        self._config = config
        self._store = state_store or LiveOperatorStateStore()
        self._event_repo = event_repo
        self._clock = clock
        self._explicit_profile_id = _coerce_profile(capital_profile_id)

    # ------------------------------------------------------------------
    # Active profile resolution (dynamic; no hardcoded 10U)
    # ------------------------------------------------------------------
    def active_capital_profile_id(self) -> CapitalProfileId:
        if self._explicit_profile_id is not None:
            return self._explicit_profile_id
        record, _ = self._store.load_capital_profile()
        if record.capital_profile_id is not CapitalProfileId.L0_SHADOW:
            return record.capital_profile_id
        if self._config is not None:
            return self._config.capital_profile_id
        return CapitalProfileId.L0_SHADOW

    def active_profile(self) -> CapitalProfile:
        """Return the active :class:`CapitalProfile` (resolved dynamically)."""
        return get_profile(self.active_capital_profile_id())

    def profile_caps(self) -> LiveProfileCaps:
        """Return the active profile's caps (read by every live decision)."""
        return LiveProfileCaps.from_profile(self.active_profile())

    def runtime_mode(self) -> LiveRuntimeMode:
        record, _ = self._store.load_runtime_mode()
        return record.runtime_mode

    def kill_switch_active(self) -> bool:
        """Whether the kill switch is ACTIVE (emergency halt triggered).

        When True every NEW entry is blocked. This is the persisted
        ``armed`` flag; ``armed`` historically meant "active" so the two
        are the same boolean - only the name is disambiguated here.
        """
        record, _ = self._store.load_kill_switch()
        return bool(record.armed)

    def kill_switch_ready(self) -> bool:
        """Whether the kill switch subsystem is READY / available.

        "Ready" (a.k.a. available) means the persisted kill-switch state
        is readable and the operator can trigger it through the
        confirmation workflow. It is INDEPENDENT of whether the switch is
        active: a ready switch may be inactive (normal) or active
        (emergency halt engaged). A corrupt / unreadable persisted state
        fails safe to ``ready=False`` so the operator re-checks before a
        funded launch.
        """
        _record, warnings = self._store.load_kill_switch()
        for w in warnings:
            if "CORRUPT" in str(w).upper():
                return False
        return True

    def kill_switch_armed(self) -> bool:
        """Backward-compatible alias of :meth:`kill_switch_active`.

        ``armed`` is retained only as a compatibility alias for the
        ACTIVE (emergency-halt) state; new code should use
        :meth:`kill_switch_active` / :meth:`kill_switch_ready` so the two
        distinct states are never confused.
        """
        return self.kill_switch_active()

    def live_limited_confirmed(self) -> bool:
        record, _ = self._store.load_confirmation()
        return bool(record.live_limited_confirmed)

    # ------------------------------------------------------------------
    # Profile switching (operator-initiated; NEVER automatic)
    # ------------------------------------------------------------------
    def set_capital_profile(
        self, profile_id: CapitalProfileId | str, *, by: str = "operator"
    ) -> CapitalProfileId:
        """Persist an OPERATOR-INITIATED capital-profile switch (audited).

        This is the only way the active profile changes; it is never a
        side effect of equity growth. Switching profile requires no code
        change - the caps come straight from the PR110 ladder.
        """
        target = _coerce_profile(profile_id)
        if target is None:
            raise ValueError(f"unknown capital profile id: {profile_id!r}")
        current = self.active_capital_profile_id()
        record = CapitalProfileStateRecord(
            capital_profile_id=target, updated_at=self._clock(), updated_by=by
        )
        self._store.save_capital_profile(record)
        self._explicit_profile_id = None  # let the store be authoritative
        self._emit(
            EventType.CAPITAL_PROFILE_CHANGED,
            {
                "from": current.value,
                "to": target.value,
                "by": by,
                "auto_escalation_allowed": AUTO_ESCALATION_ALLOWED,
            },
        )
        return target

    # ------------------------------------------------------------------
    # Capital profile enforcement (caps usable capital; detects mismatch)
    # ------------------------------------------------------------------
    def evaluate_capital_profile(
        self,
        capital_state: LiveCapitalState,
        *,
        daily_loss_usdt: float = 0.0,
        total_loss_usdt: float = 0.0,
        safety_equity_floor_usdt: float | None = None,
    ) -> CapitalProfileState:
        """Enforce the active profile against the real account state.

        Usable capital is capped at the active profile's
        ``max_account_capital_usdt`` (10U for L1_10U_PROBE, 50U for L2,
        and so on). Emits ``CAPITAL_PROFILE_MISMATCH`` when equity has left
        the active profile band; never auto-escalates.
        """
        state = evaluate_capital_profile_state(
            capital_state,
            self.active_profile(),
            daily_loss_usdt=daily_loss_usdt,
            total_loss_usdt=total_loss_usdt,
            safety_equity_floor_usdt=safety_equity_floor_usdt,
            kill_switch_armed=self.kill_switch_armed(),
        )
        if state.mismatch.mismatch:
            self._emit(
                EventType.CAPITAL_PROFILE_MISMATCH,
                {
                    "current_profile_id": state.capital_profile_id.value,
                    "adjusted_equity_usdt": state.account_equity_usdt,
                    "usable_capital_usdt": state.usable_capital_usdt,
                    "direction": state.mismatch.direction,
                    "recommended_next_profile_id": state.suggested_profile_id.value,
                    "requires_operator_action": state.requires_operator_action,
                    "auto_escalation_allowed": AUTO_ESCALATION_ALLOWED,
                },
            )
        return state

    def detect_mismatch(self, adjusted_equity_usdt: float) -> ProfileMismatch:
        return detect_profile_mismatch(
            self.active_capital_profile_id(), float(adjusted_equity_usdt)
        )

    def recommended_profile_for_equity(
        self, adjusted_equity_usdt: float
    ) -> CapitalProfileId:
        return suggest_profile_for_equity(float(adjusted_equity_usdt))

    # ------------------------------------------------------------------
    # Execution context (reads the active profile dynamically)
    # ------------------------------------------------------------------
    def build_execution_context(
        self,
        *,
        exchange_live_orders: bool = False,
        trade_authority: bool = False,
        ai_trade_authority: bool = False,
        private_trade_enabled: bool | None = None,
        live_limited_confirmed: bool | None = None,
        kill_switch_active: bool | None = None,
        account_equity_usdt: float | None = None,
        profile_operator_acknowledged: bool = False,
        hard_block_on_profile_mismatch: bool = True,
    ) -> ExecutionPermissionContext:
        """Build an :class:`ExecutionPermissionContext` for the ACTIVE profile.

        ``allowed_profile_ids`` is set to the *active* profile so whatever
        the operator has selected (10U, 50U, 1000U, ...) is the only
        profile the gate accepts - a switch needs no code change. The
        unsafe-enabling flags all default False.
        """
        active = self.active_capital_profile_id()
        if private_trade_enabled is None:
            private_trade_enabled = bool(
                self._config
                and self._config.binance
                and self._config.binance.enable_private_trade
            )
        if live_limited_confirmed is None:
            live_limited_confirmed = self.live_limited_confirmed()
        if kill_switch_active is None:
            kill_switch_active = self.kill_switch_active()
        return ExecutionPermissionContext(
            runtime_mode=self.runtime_mode(),
            live_limited_confirmed=bool(live_limited_confirmed),
            exchange_live_orders=bool(exchange_live_orders),
            trade_authority=bool(trade_authority),
            ai_trade_authority=bool(ai_trade_authority),
            private_trade_enabled=bool(private_trade_enabled),
            kill_switch_active=bool(kill_switch_active),
            profile_operator_acknowledged=bool(profile_operator_acknowledged),
            hard_block_on_profile_mismatch=bool(hard_block_on_profile_mismatch),
            account_equity_usdt=account_equity_usdt,
            allowed_profile_ids=(active,),
        )

    # ------------------------------------------------------------------
    # Live-source isolation (re-asserted from PR110/PR114)
    # ------------------------------------------------------------------
    @staticmethod
    def assert_live_source(source: OrderSource | str, *, action: str = "live_operation") -> None:
        """Raise :class:`LiveSourceRejected` unless ``source`` is LIVE."""
        value = source.value if isinstance(source, OrderSource) else str(source)
        if value != OrderSource.LIVE.value:
            raise LiveSourceRejected(
                f"live runtime refused a non-LIVE source ({value}) for "
                f"{action}; only OrderSource.LIVE may drive live operation."
            )

    @staticmethod
    def assert_live_market_source(obj: Any, *, action: str = "live_market_source") -> None:
        """Raise unless ``obj`` is NOT a simulation / blind / replay source.

        Refuses a MockExchange / HistoricalMarketStore / SimulatedCapital
        / ReplayFeedProvider / Blind / PaperShadow object from ever being
        used as a live market / capital source.
        """
        cls_name = type(obj).__name__
        if cls_name in FORBIDDEN_LIVE_SOURCE_CLASSES:
            raise LiveSourceRejected(
                f"live runtime refused {cls_name!r} as a {action}; "
                f"simulation / blind / replay sources can never be a live "
                f"market source."
            )

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
                    source_module=LIVE_RUNTIME_MODULE,
                    payload={
                        **payload,
                        "trade_authority": False,
                        "ai_trade_authority": False,
                        "exchange_live_orders": False,
                        "phase_12_forbidden": True,
                    },
                )
            )
        except Exception:  # pragma: no cover
            pass


def _coerce_profile(
    profile_id: CapitalProfileId | str | None,
) -> CapitalProfileId | None:
    if profile_id is None:
        return None
    if isinstance(profile_id, CapitalProfileId):
        return profile_id
    try:
        return CapitalProfileId(str(profile_id))
    except ValueError:
        return None


__all__ = [
    "LIVE_RUNTIME_MODULE",
    "DEFAULT_INITIAL_PROFILE",
    "SWITCHABLE_PROFILE_IDS",
    "FORBIDDEN_LIVE_SOURCE_CLASSES",
    "LiveProfileCaps",
    "LiveRuntime",
]
