"""Live Capital Service (PR112 - Live Capital / Risk / Funding-Aware PnL v0).

Orchestrates the PR112 read-only live capital / risk layer:

  1. Build a :class:`app.live.capital_state.LiveCapitalState` from a
     PR111 Binance private-read account snapshot (+ open-order count).
  2. Build a funding-aware :class:`app.live.pnl_accounting.LivePnlSummary`
     from classified income events.
  3. Enforce the active capital profile
     (:func:`app.live.live_risk_engine.evaluate_capital_profile_state`).
  4. Run a deterministic *dry* live order risk pre-check
     (:func:`app.live.live_risk_engine.evaluate_live_order_risk`).
  5. Produce Telegram **operator payloads** (LIVE_ACCOUNT_STATUS,
     LIVE_CAPITAL_PROFILE_STATUS, LIVE_PNL_SUMMARY, LIVE_RISK_REJECT,
     CAPITAL_PROFILE_MISMATCH, FUNDING_EVENT_SUMMARY) - it builds the
     payloads only; it does NOT open a Telegram socket or send anything.

PR112 boundary (hard): this service READS real account state and emits
descriptive payloads. It NEVER places / cancels an order, changes
leverage / margin, switches runtime mode, auto-escalates a profile, or
sends real Telegram outbound. Every payload carries the PR112 safety
markers (``real_order=False`` / ``trade_authority=False`` /
``ai_trade_authority=False``).
"""

from __future__ import annotations

from typing import Any

from app.core.enums import LiveRuntimeMode
from app.live.binance_income import BinanceIncomeEvent
from app.live.binance_models import BinanceAccountSnapshot
from app.live.capital_profile import CapitalProfileId
from app.live.capital_state import LiveCapitalState
from app.live.live_risk_engine import (
    CapitalProfileState,
    LiveOrderIntent,
    LiveRiskDecision,
    evaluate_capital_profile_state,
    evaluate_live_order_risk,
)
from app.live.pnl_accounting import LivePnlSummary, build_live_pnl_summary

# Operator payload type tags (Telegram operating-desk contract, PR112).
PAYLOAD_LIVE_ACCOUNT_STATUS = "LIVE_ACCOUNT_STATUS"
PAYLOAD_LIVE_CAPITAL_PROFILE_STATUS = "LIVE_CAPITAL_PROFILE_STATUS"
PAYLOAD_LIVE_PNL_SUMMARY = "LIVE_PNL_SUMMARY"
PAYLOAD_LIVE_RISK_REJECT = "LIVE_RISK_REJECT"
PAYLOAD_CAPITAL_PROFILE_MISMATCH = "CAPITAL_PROFILE_MISMATCH"
PAYLOAD_FUNDING_EVENT_SUMMARY = "FUNDING_EVENT_SUMMARY"

# Human display for the runtime mode (matches PR110 operator contract).
_MODE_DISPLAY: dict[LiveRuntimeMode, str] = {
    LiveRuntimeMode.LIVE_SHADOW: "空盘跑",
    LiveRuntimeMode.LIVE_LIMITED: "有资金跑",
}

PLACEHOLDER = "--"


def _safety_markers() -> dict[str, Any]:
    """Safety markers stamped on EVERY operator payload (PR112)."""
    return {
        "real_order": False,
        "real_capital_changed": False,
        "trade_authority": False,
        "ai_trade_authority": False,
        "exchange_live_orders": False,
        "live_trading": False,
        "binance_private_trade_enabled_by_config": False,
        "phase_12_forbidden": True,
    }


def _mode_display(mode: LiveRuntimeMode) -> str:
    return _MODE_DISPLAY.get(mode, _MODE_DISPLAY[LiveRuntimeMode.LIVE_SHADOW])


# ---------------------------------------------------------------------------
# Telegram operator payload builders (build only; never send)
# ---------------------------------------------------------------------------
def build_live_account_status_payload(
    capital_state: LiveCapitalState,
    *,
    kill_switch_armed: bool = False,
    profile_state: CapitalProfileState | None = None,
) -> dict[str, Any]:
    """LIVE_ACCOUNT_STATUS - the operator account snapshot card."""
    payload: dict[str, Any] = {
        "payload_type": PAYLOAD_LIVE_ACCOUNT_STATUS,
        "mode_display": _mode_display(capital_state.runtime_mode),
        "runtime_mode": capital_state.runtime_mode.value,
        "capital_profile_id": capital_state.capital_profile_id.value,
        "account_id_masked": capital_state.account_id_masked,
        "wallet_balance_usdt": capital_state.wallet_balance_usdt,
        "available_balance_usdt": capital_state.available_balance_usdt,
        "account_equity_usdt": capital_state.account_equity_usdt,
        "unrealized_pnl_usdt": capital_state.unrealized_pnl_usdt,
        "used_margin_usdt": capital_state.used_margin_usdt,
        "free_margin_usdt": capital_state.free_margin_usdt,
        "open_position_count": capital_state.open_position_count,
        "open_order_count": capital_state.open_order_count,
        "positions": [p.to_dict() for p in capital_state.open_positions],
        "real_orders_allowed": capital_state.real_orders_allowed,
        "kill_switch_armed": bool(kill_switch_armed),
        "source": capital_state.source,
        "fetched_at": capital_state.fetched_at,
    }
    if profile_state is not None:
        payload["profile_status"] = profile_state.profile_status
        payload["risk_halt_active"] = profile_state.risk_halt_active
        payload["usable_capital_usdt"] = profile_state.usable_capital_usdt
    payload.update(_safety_markers())
    return payload


def build_live_capital_profile_status_payload(
    profile_state: CapitalProfileState,
) -> dict[str, Any]:
    """LIVE_CAPITAL_PROFILE_STATUS - the active-profile enforcement card."""
    payload = {
        "payload_type": PAYLOAD_LIVE_CAPITAL_PROFILE_STATUS,
        "capital_profile_id": profile_state.capital_profile_id.value,
        "account_equity_usdt": profile_state.account_equity_usdt,
        "available_balance_usdt": profile_state.available_balance_usdt,
        "usable_capital_usdt": profile_state.usable_capital_usdt,
        "profile_max_account_capital_usdt": (
            profile_state.profile_max_account_capital_usdt
        ),
        "open_position_count": profile_state.open_position_count,
        "profile_status": profile_state.profile_status,
        "flags": list(profile_state.flags),
        "risk_halt_active": profile_state.risk_halt_active,
        "kill_switch_required": profile_state.kill_switch_required,
        "requires_operator_action": profile_state.requires_operator_action,
        "suggested_profile_id": profile_state.suggested_profile_id.value,
        "auto_escalation_allowed": profile_state.auto_escalation_allowed,
    }
    payload.update(_safety_markers())
    return payload


def build_live_pnl_summary_payload(pnl: LivePnlSummary) -> dict[str, Any]:
    """LIVE_PNL_SUMMARY - funding-aware PnL card (includes commission+funding)."""
    payload = {
        "payload_type": PAYLOAD_LIVE_PNL_SUMMARY,
        "gross_realized_pnl_usdt": pnl.gross_realized_pnl_usdt,
        "commission_total_usdt": pnl.commission_total_usdt,
        "funding_total_usdt": pnl.funding_total_usdt,
        "net_strategy_pnl_usdt": pnl.net_strategy_pnl_usdt,
        "external_deposit_total_usdt": pnl.external_deposit_total_usdt,
        "external_withdrawal_total_usdt": pnl.external_withdrawal_total_usdt,
        "transfer_in_total_usdt": pnl.transfer_in_total_usdt,
        "transfer_out_total_usdt": pnl.transfer_out_total_usdt,
        "adjusted_strategy_equity_usdt": pnl.adjusted_strategy_equity_usdt,
        "performance_equity_excluding_external_flows": (
            pnl.performance_equity_excluding_external_flows
        ),
        "unknown_income_total_usdt": pnl.unknown_income_total_usdt,
        "funding_attribution_status": pnl.funding_attribution_status,
    }
    payload.update(_safety_markers())
    return payload


def build_live_risk_reject_payload(decision: LiveRiskDecision) -> dict[str, Any]:
    """LIVE_RISK_REJECT - the rejected (or dry-approved) order risk card."""
    payload = {
        "payload_type": PAYLOAD_LIVE_RISK_REJECT,
        "approved": decision.approved,
        "symbol": _extract_symbol(decision),
        "planned_notional_usdt": decision.planned_notional_usdt,
        "planned_leverage": decision.planned_leverage,
        "reject_reason": decision.reject_reason,
        "reject_reasons": list(decision.reject_reasons),
        "max_allowed_notional_usdt": decision.max_allowed_notional_usdt,
        "max_allowed_leverage": decision.max_allowed_leverage,
        "account_equity_usdt": decision.account_equity_usdt,
        "capital_profile_id": decision.capital_profile_id.value,
        "runtime_mode": decision.runtime_mode.value,
        "risk_halt_active": decision.risk_halt_active,
        "real_order_allowed": decision.real_order_allowed,
        "audit_event_type": decision.audit_event_type,
    }
    payload.update(_safety_markers())
    return payload


def _extract_symbol(decision: LiveRiskDecision) -> str:
    for ref in decision.evidence_refs:
        if ref.startswith("symbol:"):
            return ref.split(":", 1)[1]
    return PLACEHOLDER


def build_capital_profile_mismatch_payload(
    profile_state: CapitalProfileState,
) -> dict[str, Any]:
    """CAPITAL_PROFILE_MISMATCH - operator warning, never an auto-upgrade."""
    mismatch = profile_state.mismatch
    payload = {
        "payload_type": PAYLOAD_CAPITAL_PROFILE_MISMATCH,
        "current_equity_usdt": profile_state.account_equity_usdt,
        "current_profile_id": profile_state.capital_profile_id.value,
        "profile_status": profile_state.profile_status,
        "mismatch": mismatch.mismatch,
        "direction": mismatch.direction,
        "recommended_next_profile_id": profile_state.suggested_profile_id.value,
        "requires_operator_action": profile_state.requires_operator_action,
        "auto_escalation_allowed": profile_state.auto_escalation_allowed,
        "reason": mismatch.reason,
        "note": (
            "No automatic upgrade/downgrade. Operator must explicitly "
            "reselect the capital profile."
        ),
    }
    payload.update(_safety_markers())
    return payload


def build_funding_event_summary_payload(pnl: LivePnlSummary) -> dict[str, Any]:
    """FUNDING_EVENT_SUMMARY - funding / commission attribution card."""
    payload = {
        "payload_type": PAYLOAD_FUNDING_EVENT_SUMMARY,
        "funding_total_usdt": pnl.funding_total_usdt,
        "commission_total_usdt": pnl.commission_total_usdt,
        "funding_event_count": pnl.funding_event_count,
        "unattributed_funding_count": pnl.unattributed_funding_count,
        "funding_attribution_status": pnl.funding_attribution_status,
        "funding_attribution_handoff": pnl.funding_attribution_handoff,
    }
    payload.update(_safety_markers())
    return payload


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
class LiveCapitalService:
    """Read-only orchestration of the PR112 live capital / risk layer."""

    def __init__(
        self,
        *,
        runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_SHADOW,
        capital_profile_id: CapitalProfileId | str = CapitalProfileId.L0_SHADOW,
        kill_switch_armed: bool = False,
        safety_equity_floor_usdt: float | None = None,
    ) -> None:
        self.runtime_mode = runtime_mode
        if isinstance(capital_profile_id, str) and not isinstance(
            capital_profile_id, CapitalProfileId
        ):
            capital_profile_id = CapitalProfileId(capital_profile_id)
        self.capital_profile_id = capital_profile_id
        self.kill_switch_armed = bool(kill_switch_armed)
        self.safety_equity_floor_usdt = safety_equity_floor_usdt

    # -- builders ------------------------------------------------------
    def build_capital_state(
        self,
        account: BinanceAccountSnapshot,
        *,
        open_order_count: int = 0,
        account_id: str | None = None,
        mark_prices: dict[str, float] | None = None,
        liquidation_prices: dict[str, float] | None = None,
    ) -> LiveCapitalState:
        return LiveCapitalState.from_account_snapshot(
            account,
            runtime_mode=self.runtime_mode,
            capital_profile_id=self.capital_profile_id,
            open_order_count=open_order_count,
            account_id=account_id,
            mark_prices=mark_prices,
            liquidation_prices=liquidation_prices,
        )

    def build_pnl_summary(
        self,
        income_events: list[BinanceIncomeEvent],
        *,
        account_equity_usdt: float = 0.0,
    ) -> LivePnlSummary:
        return build_live_pnl_summary(
            income_events, account_equity_usdt=account_equity_usdt
        )

    def evaluate_profile(
        self,
        capital_state: LiveCapitalState,
        *,
        daily_loss_usdt: float = 0.0,
        total_loss_usdt: float = 0.0,
    ) -> CapitalProfileState:
        return evaluate_capital_profile_state(
            capital_state,
            self.capital_profile_id,
            daily_loss_usdt=daily_loss_usdt,
            total_loss_usdt=total_loss_usdt,
            safety_equity_floor_usdt=self.safety_equity_floor_usdt,
            kill_switch_armed=self.kill_switch_armed,
        )

    def evaluate_order(
        self,
        intent: LiveOrderIntent,
        capital_state: LiveCapitalState,
        *,
        leverage_gate: Any | None = None,
        daily_loss_usdt: float = 0.0,
        total_loss_usdt: float = 0.0,
        symbol_tradable: bool | None = None,
    ) -> LiveRiskDecision:
        return evaluate_live_order_risk(
            intent,
            capital_state,
            self.capital_profile_id,
            leverage_gate=leverage_gate,
            runtime_mode=self.runtime_mode,
            daily_loss_usdt=daily_loss_usdt,
            total_loss_usdt=total_loss_usdt,
            symbol_tradable=symbol_tradable,
        )

    # -- combined status report ---------------------------------------
    def build_status_report(
        self,
        account: BinanceAccountSnapshot,
        income_events: list[BinanceIncomeEvent] | None = None,
        *,
        open_order_count: int = 0,
        account_id: str | None = None,
        mark_prices: dict[str, float] | None = None,
        daily_loss_usdt: float = 0.0,
        total_loss_usdt: float = 0.0,
    ) -> dict[str, Any]:
        """Build the full read-only status report + all operator payloads."""
        capital_state = self.build_capital_state(
            account,
            open_order_count=open_order_count,
            account_id=account_id,
            mark_prices=mark_prices,
        )
        profile_state = self.evaluate_profile(
            capital_state,
            daily_loss_usdt=daily_loss_usdt,
            total_loss_usdt=total_loss_usdt,
        )
        pnl = self.build_pnl_summary(
            income_events or [],
            account_equity_usdt=capital_state.account_equity_usdt,
        )

        payloads: dict[str, Any] = {
            PAYLOAD_LIVE_ACCOUNT_STATUS: build_live_account_status_payload(
                capital_state,
                kill_switch_armed=self.kill_switch_armed,
                profile_state=profile_state,
            ),
            PAYLOAD_LIVE_CAPITAL_PROFILE_STATUS: (
                build_live_capital_profile_status_payload(profile_state)
            ),
            PAYLOAD_LIVE_PNL_SUMMARY: build_live_pnl_summary_payload(pnl),
            PAYLOAD_FUNDING_EVENT_SUMMARY: build_funding_event_summary_payload(pnl),
        }
        if profile_state.mismatch.mismatch:
            payloads[PAYLOAD_CAPITAL_PROFILE_MISMATCH] = (
                build_capital_profile_mismatch_payload(profile_state)
            )

        return {
            "runtime_mode": self.runtime_mode.value,
            "capital_profile_id": self.capital_profile_id.value,
            "capital_state": capital_state.to_dict(),
            "capital_profile_state": profile_state.to_dict(),
            "pnl_summary": pnl.to_dict(),
            "telegram_payloads": payloads,
            "safety_flags": _safety_markers(),
        }


__all__ = [
    "PAYLOAD_LIVE_ACCOUNT_STATUS",
    "PAYLOAD_LIVE_CAPITAL_PROFILE_STATUS",
    "PAYLOAD_LIVE_PNL_SUMMARY",
    "PAYLOAD_LIVE_RISK_REJECT",
    "PAYLOAD_CAPITAL_PROFILE_MISMATCH",
    "PAYLOAD_FUNDING_EVENT_SUMMARY",
    "LiveCapitalService",
    "build_live_account_status_payload",
    "build_live_capital_profile_status_payload",
    "build_live_pnl_summary_payload",
    "build_live_risk_reject_payload",
    "build_capital_profile_mismatch_payload",
    "build_funding_event_summary_payload",
]
