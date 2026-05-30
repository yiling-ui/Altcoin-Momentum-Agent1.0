"""LIVE_LIMITED arming + controlled real-order smoke (PR116).

Two pieces:

  1. :func:`evaluate_arming` - a compact, deterministic view of whether
     the runtime is armed for a real order. It rolls up the persisted
     operator state (mode / confirmation / kill switch / profile) and the
     env-driven flags (exchange_live_orders / trade_authority / private
     trade) into an :class:`ArmingStatus` whose ``fully_armed`` is True
     only when EVERY gate is satisfied.

  2. :class:`LiveLimitedSmoke` - a tiny, heavily-gated real-order smoke.
     ``--dry-run`` (the default) validates + runs the deterministic gate
     but NEVER submits. The real-order path requires the explicit
     acknowledgement flag + a matching confirmation code + a notional
     within the profile cap, an armed LIVE_LIMITED, and every execution
     gate; it then routes through the SINGLE
     :class:`app.live.execution_gateway.LiveExecutionGateway` (which is
     the only thing that may ever send a real order), writes the ledger,
     and surfaces the exact order status. No silent retry; no duplicate.

Hard boundary: the default posture never sends a real order
(``no_real_order_sent=True``). Only the fully-gated, operator-confirmed
real-order path can flip it, and the gateway STILL re-checks every flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.core.clock import now_ms
from app.core.enums import LiveRuntimeMode, OrderSource
from app.live.api_config import LiveApiConfig
from app.live.binance_execution_adapter import BinanceExecutionAdapter
from app.live.binance_models import BinanceAccountSnapshot
from app.live.capital_profile import CapitalProfile
from app.live.capital_state import LiveCapitalState
from app.live.execution_gateway import (
    LiveExecutionGateway,
    authorize_real_order,
    evaluate_execution_permission,
)
from app.live.execution_models import (
    LiveExecutionStatus,
    LiveOrderIntent,
    OrderSide,
    OrderType,
    generate_client_order_id,
)
from app.live.live_launch_models import SmokeResult
from app.live.live_risk_engine import (
    LiveOrderIntent as RiskIntent,
    LiveRiskDecision,
    evaluate_live_order_risk,
)
from app.live.live_runtime import LiveRuntime
from app.live.order_ledger import compute_net_pnl

LIVE_LIMITED_ARMING_MODULE = "live.live_limited_arming"


# ---------------------------------------------------------------------------
# Arming status
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ArmingStatus:
    """Compact roll-up of whether the runtime is armed for a real order."""

    runtime_mode: str
    capital_profile_id: str
    live_limited_armed: bool
    live_limited_confirmed: bool
    exchange_live_orders: bool
    trade_authority: bool
    private_trade_enabled: bool
    ai_trade_authority: bool
    kill_switch_ready: bool
    kill_switch_active: bool
    profile_allows_real_orders: bool

    @property
    def fully_armed(self) -> bool:
        """True only when EVERY gate is satisfied for a real order.

        Note the kill switch contributes only through ``kill_switch_active``
        (an ACTIVE emergency halt blocks a real order). The kill switch
        being READY/available is NOT a requirement for arming - it is a
        separate launch-readiness gate.
        """
        return (
            self.runtime_mode == LiveRuntimeMode.LIVE_LIMITED.value
            and self.live_limited_confirmed
            and self.exchange_live_orders
            and self.trade_authority
            and self.private_trade_enabled
            and not self.ai_trade_authority
            and not self.kill_switch_active
            and self.profile_allows_real_orders
        )

    def missing_gates(self) -> tuple[str, ...]:
        gaps: list[str] = []
        if self.runtime_mode != LiveRuntimeMode.LIVE_LIMITED.value:
            gaps.append("runtime_mode_not_live_limited")
        if not self.live_limited_confirmed:
            gaps.append("live_limited_not_confirmed")
        if not self.exchange_live_orders:
            gaps.append("exchange_live_orders_disabled")
        if not self.trade_authority:
            gaps.append("trade_authority_disabled")
        if not self.private_trade_enabled:
            gaps.append("private_trade_disabled")
        if self.ai_trade_authority:
            gaps.append("ai_trade_authority_forbidden")
        if self.kill_switch_active:
            gaps.append("kill_switch_active")
        if not self.profile_allows_real_orders:
            gaps.append("profile_real_orders_not_allowed")
        return tuple(gaps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_type": "LIVE_LIMITED_ARMED",
            "mode_display": "有资金跑",
            "runtime_mode": self.runtime_mode,
            "capital_profile_id": self.capital_profile_id,
            "live_limited_armed": self.live_limited_armed,
            "live_limited_confirmed": self.live_limited_confirmed,
            "exchange_live_orders": self.exchange_live_orders,
            "trade_authority": self.trade_authority,
            "private_trade_enabled": self.private_trade_enabled,
            "ai_trade_authority": self.ai_trade_authority,
            "kill_switch_ready": self.kill_switch_ready,
            "kill_switch_active": self.kill_switch_active,
            # Compatibility alias (== active); never used ambiguously.
            "kill_switch_armed": self.kill_switch_active,
            "profile_allows_real_orders": self.profile_allows_real_orders,
            "fully_armed": self.fully_armed,
            "missing_gates": list(self.missing_gates()),
            "warning": (
                "Armed LIVE_LIMITED still requires the execution gate; a "
                "real order is never sent unless every gate passes."
            ),
            "phase_12_forbidden": True,
        }


def evaluate_arming(
    config: LiveApiConfig,
    runtime: LiveRuntime,
    *,
    exchange_live_orders: bool = False,
    trade_authority: bool = False,
    ai_trade_authority: bool = False,
) -> ArmingStatus:
    """Roll up persisted state + env flags into an :class:`ArmingStatus`."""
    profile = runtime.active_profile()
    return ArmingStatus(
        runtime_mode=runtime.runtime_mode().value,
        capital_profile_id=profile.profile_id.value,
        live_limited_armed=runtime.runtime_mode() is LiveRuntimeMode.LIVE_LIMITED,
        live_limited_confirmed=runtime.live_limited_confirmed(),
        exchange_live_orders=bool(exchange_live_orders),
        trade_authority=bool(trade_authority),
        private_trade_enabled=bool(config.binance.enable_private_trade),
        ai_trade_authority=bool(ai_trade_authority),
        kill_switch_ready=runtime.kill_switch_ready(),
        kill_switch_active=runtime.kill_switch_active(),
        profile_allows_real_orders=profile.real_orders_allowed,
    )


# ---------------------------------------------------------------------------
# Controlled real-order smoke
# ---------------------------------------------------------------------------
class LiveLimitedSmoke:
    """A heavily-gated 10U (or active-profile) live smoke (PR116).

    Default posture: ``--dry-run`` validates + runs the gate but NEVER
    submits. The real-order path requires the explicit acknowledgement
    flag + a matching confirmation code + a notional within the profile
    cap, and routes through :class:`LiveExecutionGateway`.
    """

    def __init__(
        self,
        config: LiveApiConfig,
        *,
        runtime: LiveRuntime,
        adapter: BinanceExecutionAdapter | None = None,
        gateway: LiveExecutionGateway | None = None,
        event_repo: Any | None = None,
        clock: Callable[[], int] = now_ms,
    ) -> None:
        self._config = config
        self._runtime = runtime
        self._adapter = adapter
        self._gateway = gateway
        if self._gateway is None and adapter is not None:
            self._gateway = LiveExecutionGateway(adapter=adapter, event_repo=event_repo)
        self._event_repo = event_repo
        self._clock = clock

    @property
    def gateway(self) -> LiveExecutionGateway | None:
        return self._gateway

    def run(
        self,
        *,
        symbol: str,
        notional_usdt: float,
        leverage: float = 1.0,
        side: str = "BUY",
        real_order: bool = False,
        i_understand_this_places_real_order: bool = False,
        confirm_code: str = "",
        expected_confirm_code: str | None = None,
        max_notional_usdt: float | None = None,
        exchange_live_orders: bool = False,
        trade_authority: bool = False,
        ai_trade_authority: bool = False,
        account_snapshot: BinanceAccountSnapshot | None = None,
        account_equity_usdt: float | None = None,
        planned_entry_price: float | None = None,
        planned_stop_price: float | None = None,
        planned_take_profit_price: float | None = None,
        quantity: float = 0.0,
        environ: dict[str, str] | None = None,
    ) -> SmokeResult:
        """Run the smoke. ``real_order=False`` (default) never submits."""
        profile = self._runtime.active_profile()

        intent = self._build_intent(
            symbol=symbol,
            notional_usdt=notional_usdt,
            leverage=leverage,
            side=side,
            planned_entry_price=planned_entry_price,
            planned_stop_price=planned_stop_price,
            planned_take_profit_price=planned_take_profit_price,
            quantity=quantity,
            profile=profile,
        )

        # Build the (dry) risk decision + execution context.
        capital_state = self._capital_state(account_snapshot)
        if account_equity_usdt is None and capital_state is not None:
            account_equity_usdt = capital_state.account_equity_usdt

        validation = None
        if self._adapter is not None and self._adapter.exchange_info is not None:
            validation = self._adapter.validate_order_against_exchange_info(intent)
        symbol_tradable = validation.symbol_tradable if validation is not None else None

        risk_decision = self._risk_decision(intent, capital_state, profile, symbol_tradable)
        context = self._runtime.build_execution_context(
            exchange_live_orders=exchange_live_orders,
            trade_authority=trade_authority,
            ai_trade_authority=ai_trade_authority,
            account_equity_usdt=account_equity_usdt,
        )
        risk_decision = authorize_real_order(risk_decision, context)

        # ---- DRY RUN: validate + gate, never submit -------------------
        if not real_order:
            decision = evaluate_execution_permission(
                intent, risk_decision, context, validation=validation, profile=profile
            )
            return self._dry_result(intent, decision, validation)

        # ---- REAL ORDER: triple confirmation + full gate + gateway ----
        blocked_reason = self._real_order_precheck(
            i_understand_this_places_real_order,
            confirm_code,
            expected_confirm_code,
            notional_usdt,
            max_notional_usdt,
            profile,
            environ,
        )
        if blocked_reason is not None:
            decision = evaluate_execution_permission(
                intent, risk_decision, context, validation=validation, profile=profile
            )
            return self._blocked_result(intent, decision, validation, blocked_reason)

        if self._gateway is None:
            decision = evaluate_execution_permission(
                intent, risk_decision, context, validation=validation, profile=profile
            )
            return self._blocked_result(intent, decision, validation, "no_execution_gateway")

        # The gateway is the SINGLE real-order entry point: it re-runs the
        # full 15-point gate, isolation + AI refusal, and only the adapter
        # may open a socket. No silent retry (the adapter sends once).
        ledger_before = len(self._gateway.ledger)
        result = self._gateway.submit_order(
            intent, risk_decision, context, validation=validation
        )
        ledger_after = len(self._gateway.ledger)
        return self._real_result(intent, result, ledger_after > ledger_before)

    # ------------------------------------------------------------------
    # Intent / risk / capital builders
    # ------------------------------------------------------------------
    def _build_intent(
        self,
        *,
        symbol: str,
        notional_usdt: float,
        leverage: float,
        side: str,
        planned_entry_price: float | None,
        planned_stop_price: float | None,
        planned_take_profit_price: float | None,
        quantity: float,
        profile: CapitalProfile,
    ) -> LiveOrderIntent:
        order_side = OrderSide(side.upper()) if isinstance(side, str) else side
        qty = float(quantity)
        if qty <= 0 and planned_entry_price and planned_entry_price > 0 and notional_usdt > 0:
            qty = float(notional_usdt) / float(planned_entry_price)
        return LiveOrderIntent(
            symbol=symbol,
            side=order_side,
            order_type=OrderType.MARKET,
            quantity=qty,
            notional_usdt=float(notional_usdt),
            planned_entry_price=planned_entry_price,
            planned_stop_price=planned_stop_price,
            planned_take_profit_price=planned_take_profit_price,
            planned_leverage=float(leverage),
            exit_plan_present=planned_take_profit_price is not None,
            stop_plan_present=planned_stop_price is not None,
            client_order_id=generate_client_order_id("smoke"),
            source=OrderSource.LIVE,
            runtime_mode=self._runtime.runtime_mode(),
            capital_profile_id=profile.profile_id,
            opportunity_id="live_limited_smoke",
            risk_decision_id="live_limited_smoke",
        )

    def _capital_state(
        self, account_snapshot: BinanceAccountSnapshot | None
    ) -> LiveCapitalState | None:
        if account_snapshot is None:
            return None
        return LiveCapitalState.from_account_snapshot(
            account_snapshot,
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
            capital_profile_id=self._runtime.active_capital_profile_id(),
        )

    def _risk_decision(
        self,
        intent: LiveOrderIntent,
        capital_state: LiveCapitalState | None,
        profile: CapitalProfile,
        symbol_tradable: bool | None,
    ) -> LiveRiskDecision:
        risk_intent = RiskIntent(
            symbol=intent.symbol,
            side="LONG" if intent.side is OrderSide.BUY else "SHORT",
            planned_entry_price=float(intent.planned_entry_price or 0.0),
            planned_notional_usdt=float(intent.notional_usdt),
            planned_leverage=float(intent.planned_leverage),
            planned_stop_price=intent.planned_stop_price,
            planned_take_profit_price=intent.planned_take_profit_price,
            exit_plan_present=intent.exit_plan_present,
            stop_plan_present=intent.stop_plan_present,
            candidate_stage="smoke",
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
            source=OrderSource.LIVE,
        )
        return evaluate_live_order_risk(
            risk_intent,
            capital_state,
            profile,
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
            symbol_tradable=symbol_tradable,
        )

    # ------------------------------------------------------------------
    # Real-order pre-check (CLI-level confirmation gates)
    # ------------------------------------------------------------------
    def _real_order_precheck(
        self,
        i_understand: bool,
        confirm_code: str,
        expected_confirm_code: str | None,
        notional_usdt: float,
        max_notional_usdt: float | None,
        profile: CapitalProfile,
        environ: dict[str, str] | None,
    ) -> str | None:
        if not i_understand:
            return "missing_i_understand_flag"
        expected = expected_confirm_code
        if expected is None:
            import os

            src = environ if environ is not None else os.environ
            expected = (src.get("AMA_LIVE_EXECUTION_CONFIRM_CODE") or "").strip()
        if not confirm_code or not expected or confirm_code != expected:
            return "invalid_or_missing_confirmation_code"
        # Notional must be within the operator-supplied max AND the profile.
        if max_notional_usdt is not None and float(notional_usdt) > float(max_notional_usdt):
            return "notional_exceeds_max_notional_arg"
        if (
            profile.max_position_notional_usdt > 0
            and float(notional_usdt) > profile.max_position_notional_usdt
        ):
            return "notional_exceeds_profile_max"
        if not self._runtime.live_limited_confirmed():
            return "live_limited_not_armed"
        return None

    # ------------------------------------------------------------------
    # Result builders
    # ------------------------------------------------------------------
    def _dry_result(self, intent, decision, validation) -> SmokeResult:
        return SmokeResult(
            mode="dry_run",
            symbol=intent.symbol,
            side=intent.side.value,
            notional_usdt=float(intent.notional_usdt),
            leverage=float(intent.planned_leverage),
            client_order_id=intent.client_order_id,
            allowed=decision.allowed,
            reject_reason=decision.reject_reason,
            reject_reasons=tuple(decision.reject_reasons),
            order_status=None,
            exchange_order_id=None,
            fill_price=None,
            fee_usdt=None,
            funding_attribution_status=None,
            net_pnl_usdt=None,
            validation_ok=bool(validation.ok) if validation is not None else False,
            dry_run=True,
            real_order=False,
            no_real_order_sent=True,
            blocked_reason=None,
            ledger_recorded=False,
        )

    def _blocked_result(self, intent, decision, validation, blocked_reason) -> SmokeResult:
        return SmokeResult(
            mode="real_order",
            symbol=intent.symbol,
            side=intent.side.value,
            notional_usdt=float(intent.notional_usdt),
            leverage=float(intent.planned_leverage),
            client_order_id=intent.client_order_id,
            allowed=False,
            reject_reason=blocked_reason or decision.reject_reason,
            reject_reasons=tuple(decision.reject_reasons),
            order_status=None,
            exchange_order_id=None,
            fill_price=None,
            fee_usdt=None,
            funding_attribution_status=None,
            net_pnl_usdt=None,
            validation_ok=bool(validation.ok) if validation is not None else False,
            dry_run=False,
            real_order=False,
            no_real_order_sent=True,
            blocked_reason=blocked_reason,
            ledger_recorded=False,
        )

    def _real_result(self, intent, result, ledger_recorded: bool) -> SmokeResult:
        is_real = bool(result.is_real_order) and result.status not in (
            LiveExecutionStatus.BLOCKED,
            LiveExecutionStatus.FAILED,
        )
        realized = result.realized_pnl_usdt
        fee = result.fee_usdt
        net = None
        if result.status.is_fill and fee is not None:
            net = compute_net_pnl(realized or 0.0, fee or 0.0, 0.0)
        funding_status = None
        if result.status.is_fill:
            from app.live.pnl_accounting import FundingAttributionStatus

            funding_status = FundingAttributionStatus.UNATTRIBUTED_PENDING_POSITION_LINK
        return SmokeResult(
            mode="real_order",
            symbol=intent.symbol,
            side=intent.side.value,
            notional_usdt=float(intent.notional_usdt),
            leverage=float(intent.planned_leverage),
            client_order_id=result.client_order_id or intent.client_order_id,
            allowed=is_real,
            reject_reason=result.error_code,
            reject_reasons=(),
            order_status=result.status.value,
            exchange_order_id=result.exchange_order_id,
            fill_price=result.avg_fill_price,
            fee_usdt=fee,
            funding_attribution_status=funding_status,
            net_pnl_usdt=net,
            validation_ok=True,
            dry_run=False,
            real_order=is_real,
            no_real_order_sent=not is_real,
            blocked_reason=(None if is_real else result.error_code),
            ledger_recorded=ledger_recorded,
        )


__all__ = [
    "LIVE_LIMITED_ARMING_MODULE",
    "ArmingStatus",
    "evaluate_arming",
    "LiveLimitedSmoke",
]
