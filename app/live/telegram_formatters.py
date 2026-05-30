"""Operator card formatters for the Telegram console (PR114).

Builds short, readable, redacted operator cards for the live operating
desk. Every card is a plain dict (stable schema, auditable) plus a
``render_card`` one-line text view. Cards NEVER carry a secret (every
payload is routed through the Phase 8.5 redactor before it leaves), and
every card pins the PR114 safety markers.

Card families (the brief):

  - Shadow plan cards : ``SHADOW_ENTRY_PLAN`` / ``SHADOW_EXIT_PLAN`` /
    ``SHADOW_RISK_REJECT`` - planned entry / stop / take-profit, with
    ``real_order=false`` / ``order_id=--`` / ``real_capital_changed=false``.
  - Live order cards   : built on top of PR113's
    :func:`app.live.execution_telegram.build_execution_telegram_payload`
    (``LIVE_ORDER_SUBMITTED`` / ``LIVE_ORDER_FILLED`` /
    ``LIVE_ORDER_PARTIALLY_FILLED`` / ``LIVE_EXIT_FILLED`` /
    ``LIVE_ORDER_REJECTED`` / ``LIVE_EXECUTION_BLOCKED`` ...). Re-exported
    here so the console has a single import surface.
  - Status / account cards : ``LIVE_ACCOUNT_STATUS`` / ``LIVE_PNL_SUMMARY``
    / ``LIVE_RISK_SUMMARY`` / ``LIVE_CAPITAL_SUMMARY`` /
    ``LIVE_PROFILE_SUMMARY`` / ``LIVE_MODE_STATUS``.
  - Operator workflow cards : ``LIVE_MODE_CHANGED`` /
    ``CAPITAL_PROFILE_CHANGED`` / ``CAPITAL_PROFILE_MISMATCH`` /
    ``CAPITAL_EVENT_DETECTED`` / ``FUNDING_EVENT_ATTRIBUTED`` /
    ``LIVE_KILL_SWITCH`` / ``LIVE_PAUSED`` / ``LIVE_RESUMED`` /
    ``LIVE_MODE_SWITCH_REQUESTED``.

This module builds + renders cards only. It NEVER opens a Telegram
socket, places an order, or flips a safety flag.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.core.enums import LiveRuntimeMode
from app.exports.redaction import redact

# Re-export the PR113 execution payload builder + its payload-type tags so
# the operator console has one import surface for live order cards.
from app.live.execution_telegram import (  # noqa: F401
    PAYLOAD_LIVE_EXECUTION_BLOCKED,
    PAYLOAD_LIVE_EXIT_FILLED,
    PAYLOAD_LIVE_ORDER_CANCELED,
    PAYLOAD_LIVE_ORDER_FAILED,
    PAYLOAD_LIVE_ORDER_FILLED,
    PAYLOAD_LIVE_ORDER_PARTIALLY_FILLED,
    PAYLOAD_LIVE_ORDER_REJECTED,
    PAYLOAD_LIVE_ORDER_SUBMITTED,
    build_execution_telegram_payload,
)

TELEGRAM_FORMATTERS_MODULE = "live.telegram_formatters"

PLACEHOLDER = "--"

MODE_DISPLAY: dict[LiveRuntimeMode, str] = {
    LiveRuntimeMode.LIVE_SHADOW: "空盘跑",
    LiveRuntimeMode.LIVE_LIMITED: "有资金跑",
}


# ---------------------------------------------------------------------------
# Card-type taxonomy
# ---------------------------------------------------------------------------
class CardType:
    """Closed taxonomy of PR114 operator card types."""

    # Shadow plan cards.
    SHADOW_ENTRY_PLAN = "SHADOW_ENTRY_PLAN"
    SHADOW_EXIT_PLAN = "SHADOW_EXIT_PLAN"
    SHADOW_RISK_REJECT = "SHADOW_RISK_REJECT"
    # Live order lifecycle (delegated to execution_telegram).
    LIVE_ORDER_SUBMIT_REQUESTED = "LIVE_ORDER_SUBMIT_REQUESTED"
    LIVE_ORDER_SUBMITTED = "LIVE_ORDER_SUBMITTED"
    LIVE_ORDER_FILLED = "LIVE_ORDER_FILLED"
    LIVE_ORDER_PARTIALLY_FILLED = "LIVE_ORDER_PARTIALLY_FILLED"
    LIVE_ORDER_CANCELED = "LIVE_ORDER_CANCELED"
    LIVE_ORDER_REJECTED = "LIVE_ORDER_REJECTED"
    LIVE_ORDER_FAILED = "LIVE_ORDER_FAILED"
    LIVE_EXECUTION_BLOCKED = "LIVE_EXECUTION_BLOCKED"
    LIVE_EXIT_FILLED = "LIVE_EXIT_FILLED"
    # Status / account cards.
    LIVE_ACCOUNT_STATUS = "LIVE_ACCOUNT_STATUS"
    LIVE_PNL_SUMMARY = "LIVE_PNL_SUMMARY"
    LIVE_RISK_SUMMARY = "LIVE_RISK_SUMMARY"
    LIVE_CAPITAL_SUMMARY = "LIVE_CAPITAL_SUMMARY"
    LIVE_PROFILE_SUMMARY = "LIVE_PROFILE_SUMMARY"
    LIVE_MODE_STATUS = "LIVE_MODE_STATUS"
    LIVE_POSITIONS = "LIVE_POSITIONS"
    LIVE_HELP = "LIVE_HELP"
    # Operator workflow cards.
    LIVE_MODE_SWITCH_REQUESTED = "LIVE_MODE_SWITCH_REQUESTED"
    LIVE_MODE_CHANGED = "LIVE_MODE_CHANGED"
    CAPITAL_PROFILE_CHANGED = "CAPITAL_PROFILE_CHANGED"
    CAPITAL_PROFILE_MISMATCH = "CAPITAL_PROFILE_MISMATCH"
    PROFILE_CHANGE_REJECTED = "PROFILE_CHANGE_REJECTED"
    CAPITAL_EVENT_DETECTED = "CAPITAL_EVENT_DETECTED"
    FUNDING_EVENT_ATTRIBUTED = "FUNDING_EVENT_ATTRIBUTED"
    LIVE_KILL_SWITCH = "LIVE_KILL_SWITCH"
    LIVE_KILL_SWITCH_ARM_REQUESTED = "LIVE_KILL_SWITCH_ARM_REQUESTED"
    LIVE_PAUSED = "LIVE_PAUSED"
    LIVE_RESUMED = "LIVE_RESUMED"


def mode_display(mode: LiveRuntimeMode | str | None) -> str:
    """Human display string for a runtime mode (空盘跑 / 有资金跑)."""
    if isinstance(mode, str):
        try:
            mode = LiveRuntimeMode(mode)
        except ValueError:
            mode = LiveRuntimeMode.LIVE_SHADOW
    if mode is None:
        mode = LiveRuntimeMode.LIVE_SHADOW
    return MODE_DISPLAY.get(mode, MODE_DISPLAY[LiveRuntimeMode.LIVE_SHADOW])


def _mode_value(mode: LiveRuntimeMode | str | None) -> str:
    if isinstance(mode, LiveRuntimeMode):
        return mode.value
    if isinstance(mode, str):
        return mode
    return LiveRuntimeMode.LIVE_SHADOW.value


def _safety_markers() -> dict[str, Any]:
    """Safety markers stamped on EVERY operator card (PR114)."""
    return {
        "trade_authority": False,
        "ai_trade_authority": False,
        "exchange_live_orders": False,
        "live_trading": False,
        "phase_12_forbidden": True,
    }


def _or(value: Any) -> Any:
    return PLACEHOLDER if value is None else value


def _finalize(card: dict[str, Any]) -> dict[str, Any]:
    """Redact card CONTENT, then stamp the fixed safety markers.

    Redaction runs first so any secret a caller accidentally put in the
    card payload is scrubbed. The constant safety-marker booleans are
    added AFTER redaction so they stay visible (the redactor would
    otherwise mask the ``*_authority`` keys, hiding the safety posture).
    The marker values are fixed booleans, never credentials.
    """
    safe = redact(card)
    safe.update(_safety_markers())
    return safe


# ---------------------------------------------------------------------------
# Shadow plan cards
# ---------------------------------------------------------------------------
def build_shadow_entry_plan_card(plan: Mapping[str, Any]) -> dict[str, Any]:
    """SHADOW_ENTRY_PLAN - 空盘跑 entry plan; real_order=false, order_id=--.

    Mandatory planned fields: entry zone / entry / stop / tp1 / tp2 /
    notional / leverage. Real-order fields are forced placeholders.
    """
    card = {
        "card_type": CardType.SHADOW_ENTRY_PLAN,
        "mode_display": MODE_DISPLAY[LiveRuntimeMode.LIVE_SHADOW],
        "runtime_mode": LiveRuntimeMode.LIVE_SHADOW.value,
        "signal_type": CardType.SHADOW_ENTRY_PLAN,
        "symbol": _or(plan.get("symbol")),
        "side": _or(plan.get("side")),
        "candidate_stage": _or(plan.get("candidate_stage")),
        "opportunity_score": _or(plan.get("opportunity_score")),
        "planned_entry_zone": _or(plan.get("planned_entry_zone")),
        "planned_entry_price": _or(plan.get("planned_entry_price")),
        "planned_stop_price": _or(plan.get("planned_stop_price")),
        "planned_take_profit_1": _or(plan.get("planned_take_profit_1")),
        "planned_take_profit_2": _or(plan.get("planned_take_profit_2")),
        "planned_notional_usdt": _or(plan.get("planned_notional_usdt")),
        "planned_leverage": _or(plan.get("planned_leverage")),
        "risk_decision": _or(plan.get("risk_decision")),
        # Hard shadow markers.
        "real_order": False,
        "real_capital_changed": False,
        "order_id": PLACEHOLDER,
        "fill_price": PLACEHOLDER,
        "event_id": _or(plan.get("event_id")),
    }
    return _finalize(card)


def build_shadow_exit_plan_card(plan: Mapping[str, Any]) -> dict[str, Any]:
    """SHADOW_EXIT_PLAN - 空盘跑 exit plan; real_order=false."""
    card = {
        "card_type": CardType.SHADOW_EXIT_PLAN,
        "mode_display": MODE_DISPLAY[LiveRuntimeMode.LIVE_SHADOW],
        "runtime_mode": LiveRuntimeMode.LIVE_SHADOW.value,
        "signal_type": CardType.SHADOW_EXIT_PLAN,
        "symbol": _or(plan.get("symbol")),
        "side": _or(plan.get("side")),
        "planned_exit_price": _or(plan.get("planned_exit_price")),
        "planned_stop_price": _or(plan.get("planned_stop_price")),
        "planned_take_profit_1": _or(plan.get("planned_take_profit_1")),
        "planned_take_profit_2": _or(plan.get("planned_take_profit_2")),
        "planned_exit_reason": _or(plan.get("planned_exit_reason")),
        "risk_decision": _or(plan.get("risk_decision")),
        "real_order": False,
        "real_capital_changed": False,
        "order_id": PLACEHOLDER,
        "fill_price": PLACEHOLDER,
        "event_id": _or(plan.get("event_id")),
    }
    return _finalize(card)


def build_shadow_risk_reject_card(decision: Mapping[str, Any]) -> dict[str, Any]:
    """SHADOW_RISK_REJECT - a planned (shadow) order rejected by risk."""
    return _finalize(
        {
            "card_type": CardType.SHADOW_RISK_REJECT,
            "mode_display": MODE_DISPLAY[LiveRuntimeMode.LIVE_SHADOW],
            "runtime_mode": LiveRuntimeMode.LIVE_SHADOW.value,
            "symbol": _or(decision.get("symbol")),
            "planned_notional": _or(decision.get("planned_notional_usdt")),
            "planned_leverage": _or(decision.get("planned_leverage")),
            "reject_reason": _or(decision.get("reject_reason")),
            "reject_reasons": list(decision.get("reject_reasons", []) or []),
            "max_allowed_notional": _or(decision.get("max_allowed_notional_usdt")),
            "max_allowed_leverage": _or(decision.get("max_allowed_leverage")),
            "profile": _or(decision.get("capital_profile_id")),
            "real_order": False,
            "event_id": _or(decision.get("event_id")),
        }
    )


def build_live_risk_reject_card(
    decision: Mapping[str, Any],
    *,
    runtime_mode: LiveRuntimeMode | str | None = None,
    blocked: bool = False,
) -> dict[str, Any]:
    """LIVE_RISK_REJECT / LIVE_EXECUTION_BLOCKED operator card.

    Shows symbol, planned notional/leverage, reject reason, the profile
    max ceilings, runtime mode, and ``real_order=false``.
    """
    card_type = (
        CardType.LIVE_EXECUTION_BLOCKED if blocked else CardType.LIVE_ORDER_REJECTED
    )
    return _finalize(
        {
            "card_type": card_type,
            "mode_display": mode_display(runtime_mode),
            "runtime_mode": _mode_value(runtime_mode),
            "symbol": _or(decision.get("symbol")),
            "planned_notional": _or(decision.get("planned_notional_usdt")),
            "planned_leverage": _or(decision.get("planned_leverage")),
            "reject_reason": _or(decision.get("reject_reason")),
            "reject_reasons": list(decision.get("reject_reasons", []) or []),
            "max_allowed_notional": _or(decision.get("max_allowed_notional_usdt")),
            "max_allowed_leverage": _or(decision.get("max_allowed_leverage")),
            "profile": _or(decision.get("capital_profile_id")),
            "real_order": False,
            "event_id": _or(decision.get("event_id")),
        }
    )


# ---------------------------------------------------------------------------
# Status / account cards
# ---------------------------------------------------------------------------
def build_status_card(status: Mapping[str, Any]) -> dict[str, Any]:
    """LIVE_ACCOUNT_STATUS - the /status card.

    Surfaces runtime mode + profile + all safety state + API health
    snapshots + open positions count + equity, plus the current source
    label (always LIVE_SHADOW or LIVE_LIMITED, never a sim/blind mix).
    """
    mode = status.get("runtime_mode")
    return _finalize(
        {
            "card_type": CardType.LIVE_ACCOUNT_STATUS,
            "mode_display": mode_display(mode),
            "runtime_mode": _mode_value(mode),
            "source_label": _mode_value(mode),
            "capital_profile_id": _or(status.get("capital_profile_id")),
            "live_limited_armed": bool(status.get("live_limited_armed", False)),
            "exchange_live_orders": bool(status.get("exchange_live_orders", False)),
            "trade_authority_flag": bool(status.get("trade_authority_flag", False)),
            "private_trade_enabled": bool(status.get("private_trade_enabled", False)),
            "paused": bool(status.get("paused", False)),
            "kill_switch_armed": bool(status.get("kill_switch_armed", False)),
            "binance_public_status": _or(status.get("binance_public_status")),
            "binance_private_read_status": _or(status.get("binance_private_read_status")),
            "telegram_outbound_status": _or(status.get("telegram_outbound_status")),
            "deepseek_status": _or(status.get("deepseek_status")),
            "open_position_count": _or(status.get("open_position_count")),
            "account_equity_usdt": _or(status.get("account_equity_usdt")),
            "funding_attribution_status": _or(status.get("funding_attribution_status")),
            "real_order": False,
        }
    )


def build_positions_card(
    positions: list[Mapping[str, Any]],
    *,
    runtime_mode: LiveRuntimeMode | str | None = None,
    funding_attribution_status: str | None = None,
) -> dict[str, Any]:
    """LIVE_POSITIONS - one row per open position, with funding status."""
    rows = []
    for p in positions or []:
        rows.append(
            {
                "symbol": _or(p.get("symbol")),
                "side": _or(p.get("side")),
                "size": _or(p.get("position_amt", p.get("size"))),
                "entry_price": _or(p.get("entry_price")),
                "mark_price": _or(p.get("mark_price")),
                "unrealized_pnl": _or(p.get("unrealized_pnl")),
                "notional": _or(p.get("notional_usdt", p.get("notional"))),
                "leverage": _or(p.get("leverage")),
                "liquidation_price": _or(p.get("liquidation_price")),
                "funding_attribution_status": _or(
                    p.get("funding_attribution_status", funding_attribution_status)
                ),
            }
        )
    return _finalize(
        {
            "card_type": CardType.LIVE_POSITIONS,
            "mode_display": mode_display(runtime_mode),
            "runtime_mode": _mode_value(runtime_mode),
            "position_count": len(rows),
            "positions": rows,
            "funding_attribution_status": _or(funding_attribution_status),
            "real_order": False,
        }
    )


def build_pnl_card(pnl: Mapping[str, Any]) -> dict[str, Any]:
    """LIVE_PNL_SUMMARY - gross / commission / funding / net + flows."""
    return _finalize(
        {
            "card_type": CardType.LIVE_PNL_SUMMARY,
            "gross_realized_pnl": _or(pnl.get("gross_realized_pnl_usdt")),
            "commission_total": _or(pnl.get("commission_total_usdt")),
            "funding_total": _or(pnl.get("funding_total_usdt")),
            "net_strategy_pnl": _or(pnl.get("net_strategy_pnl_usdt")),
            "unrealized_pnl": _or(pnl.get("unrealized_pnl_usdt")),
            "deposits": _or(pnl.get("external_deposit_total_usdt")),
            "withdrawals": _or(pnl.get("external_withdrawal_total_usdt")),
            "adjusted_equity": _or(pnl.get("adjusted_strategy_equity_usdt")),
            "funding_attribution_status": _or(pnl.get("funding_attribution_status")),
            "real_order": False,
        }
    )


def build_risk_card(risk: Mapping[str, Any]) -> dict[str, Any]:
    """LIVE_RISK_SUMMARY - profile limits + loss state + halts + kill switch."""
    return _finalize(
        {
            "card_type": CardType.LIVE_RISK_SUMMARY,
            "capital_profile_id": _or(risk.get("capital_profile_id")),
            "max_account_capital_usdt": _or(risk.get("max_account_capital_usdt")),
            "used_profile_capital_usdt": _or(risk.get("used_profile_capital_usdt")),
            "max_position_notional_usdt": _or(risk.get("max_position_notional_usdt")),
            "max_leverage": _or(risk.get("max_leverage")),
            "daily_loss_state": _or(risk.get("daily_loss_state")),
            "total_loss_state": _or(risk.get("total_loss_state")),
            "risk_halt_active": bool(risk.get("risk_halt_active", False)),
            "kill_switch_state": _or(risk.get("kill_switch_state")),
            "real_order": False,
        }
    )


def build_capital_card(capital: Mapping[str, Any]) -> dict[str, Any]:
    """LIVE_CAPITAL_SUMMARY - wallet / available / equity + flows + mismatch."""
    return _finalize(
        {
            "card_type": CardType.LIVE_CAPITAL_SUMMARY,
            "wallet_balance_usdt": _or(capital.get("wallet_balance_usdt")),
            "available_balance_usdt": _or(capital.get("available_balance_usdt")),
            "account_equity_usdt": _or(capital.get("account_equity_usdt")),
            "external_deposits_usdt": _or(capital.get("external_deposits_usdt")),
            "external_withdrawals_usdt": _or(capital.get("external_withdrawals_usdt")),
            "profit_harvest_usdt": _or(capital.get("profit_harvest_usdt")),
            "rebase_usdt": _or(capital.get("rebase_usdt")),
            "profile_mismatch_warning": _or(capital.get("profile_mismatch_warning")),
            "real_order": False,
        }
    )


def build_profile_card(profile: Mapping[str, Any]) -> dict[str, Any]:
    """LIVE_PROFILE_SUMMARY - current profile + recommended profile."""
    return _finalize(
        {
            "card_type": CardType.LIVE_PROFILE_SUMMARY,
            "capital_profile_id": _or(profile.get("capital_profile_id")),
            "recommended_profile_id": _or(profile.get("recommended_profile_id")),
            "account_equity_usdt": _or(profile.get("account_equity_usdt")),
            "max_account_capital_usdt": _or(profile.get("max_account_capital_usdt")),
            "auto_escalation_allowed": False,
            "real_order": False,
        }
    )


def build_mode_status_card(
    mode: LiveRuntimeMode | str,
    *,
    real_order_allowed: bool = False,
    live_limited_armed: bool = False,
    paused: bool = False,
) -> dict[str, Any]:
    """LIVE_MODE_STATUS - the /mode card (explains real_order permission)."""
    return _finalize(
        {
            "card_type": CardType.LIVE_MODE_STATUS,
            "mode_display": mode_display(mode),
            "runtime_mode": _mode_value(mode),
            "source_label": _mode_value(mode),
            "live_limited_armed": bool(live_limited_armed),
            "paused": bool(paused),
            "real_order_allowed": bool(real_order_allowed),
            "real_order_explanation": (
                "real orders may be sent only when LIVE_LIMITED is armed AND "
                "exchange_live_orders + trade_authority + private trade are all "
                "enabled AND the risk + execution gate pass."
            ),
            "real_order": False,
        }
    )


def build_help_card(commands: list[str], *, mode: LiveRuntimeMode | str) -> dict[str, Any]:
    """LIVE_HELP - the /help card (command list + current mode)."""
    return _finalize(
        {
            "card_type": CardType.LIVE_HELP,
            "mode_display": mode_display(mode),
            "runtime_mode": _mode_value(mode),
            "commands": list(commands),
            "real_order": False,
        }
    )


# ---------------------------------------------------------------------------
# Operator workflow cards
# ---------------------------------------------------------------------------
def build_mode_switch_requested_card(summary: Mapping[str, Any]) -> dict[str, Any]:
    """LIVE_MODE_SWITCH_REQUESTED - the /mode live_limited risk summary + code."""
    return _finalize(
        {
            "card_type": CardType.LIVE_MODE_SWITCH_REQUESTED,
            "confirmation_code": _or(summary.get("confirmation_code")),
            "current_runtime_mode": _or(summary.get("current_mode")),
            "target_runtime_mode": _or(summary.get("target_mode")),
            "capital_profile_id": _or(summary.get("capital_profile_id")),
            "account_equity_usdt": _or(summary.get("account_equity_usdt")),
            "max_account_capital_usdt": _or(summary.get("max_account_capital_usdt")),
            "max_position_notional_usdt": _or(summary.get("max_position_notional_usdt")),
            "max_active_positions": _or(summary.get("max_active_positions")),
            "max_daily_loss_usdt": _or(summary.get("max_daily_loss_usdt")),
            "max_total_loss_usdt": _or(summary.get("max_total_loss_usdt")),
            "max_leverage": _or(summary.get("max_leverage")),
            "exchange_live_orders": bool(summary.get("exchange_live_orders", False)),
            "trade_authority_flag": bool(summary.get("trade_authority_flag", False)),
            "private_trade_enabled": bool(summary.get("private_trade_enabled", False)),
            "kill_switch_armed": bool(summary.get("kill_switch_armed", False)),
            "funding_attribution_status": _or(summary.get("funding_attribution_status")),
            "warning": (
                "Arming LIVE_LIMITED does NOT itself enable real orders. Real "
                "orders are still gated by exchange_live_orders + trade_authority "
                "+ private trade + the risk / execution gate."
            ),
            "real_order": False,
        }
    )


def build_mode_changed_card(
    *,
    from_mode: LiveRuntimeMode | str,
    to_mode: LiveRuntimeMode | str,
    reason: str = "",
    real_order_allowed: bool = False,
) -> dict[str, Any]:
    """LIVE_MODE_CHANGED - the mode actually changed (persisted)."""
    return _finalize(
        {
            "card_type": CardType.LIVE_MODE_CHANGED,
            "from_runtime_mode": _mode_value(from_mode),
            "to_runtime_mode": _mode_value(to_mode),
            "mode_display": mode_display(to_mode),
            "reason": reason,
            "real_order_allowed": bool(real_order_allowed),
            "real_order": False,
        }
    )


def build_capital_profile_changed_card(
    *,
    from_profile: str,
    to_profile: str,
    is_escalation: bool,
    requested_by: str = "operator",
) -> dict[str, Any]:
    """CAPITAL_PROFILE_CHANGED - operator changed the active profile."""
    return _finalize(
        {
            "card_type": CardType.CAPITAL_PROFILE_CHANGED,
            "from_profile_id": from_profile,
            "to_profile_id": to_profile,
            "is_escalation": bool(is_escalation),
            "requested_by": requested_by,
            "auto_escalation_allowed": False,
            "warning": (
                "Higher-risk profile selected." if is_escalation else ""
            ),
            "real_order": False,
        }
    )


def build_profile_change_rejected_card(
    *, to_profile: str, reject_reason: str
) -> dict[str, Any]:
    """PROFILE_CHANGE_REJECTED - a /profile set was refused."""
    return _finalize(
        {
            "card_type": CardType.PROFILE_CHANGE_REJECTED,
            "to_profile_id": to_profile,
            "reject_reason": reject_reason,
            "real_order": False,
        }
    )


def build_capital_profile_mismatch_card(mismatch: Mapping[str, Any]) -> dict[str, Any]:
    """CAPITAL_PROFILE_MISMATCH - equity left the profile band (no auto-fix)."""
    return _finalize(
        {
            "card_type": CardType.CAPITAL_PROFILE_MISMATCH,
            "current_profile_id": _or(mismatch.get("current_profile_id")),
            "current_equity_usdt": _or(mismatch.get("current_equity_usdt")),
            "direction": _or(mismatch.get("direction")),
            "recommended_next_profile_id": _or(mismatch.get("recommended_next_profile_id")),
            "requires_operator_action": bool(mismatch.get("requires_operator_action", True)),
            "auto_escalation_allowed": False,
            "real_order": False,
        }
    )


def build_capital_event_detected_card(event: Mapping[str, Any]) -> dict[str, Any]:
    """CAPITAL_EVENT_DETECTED - deposit not pnl / withdrawal not loss.

    The card MUST mark is_trading_pnl / is_external_capital_flow /
    affects_performance_stats and explain that a deposit is not strategy
    profit and a withdrawal is not strategy loss.
    """
    event_type = str(event.get("event_type", "") or "")
    is_deposit = "DEPOSIT" in event_type.upper()
    is_withdrawal = "WITHDRAWAL" in event_type.upper()
    explanation = ""
    if is_deposit:
        explanation = "deposit is NOT strategy profit (external capital flow)."
    elif is_withdrawal:
        explanation = "withdrawal is NOT strategy loss (external capital flow)."
    return _finalize(
        {
            "card_type": CardType.CAPITAL_EVENT_DETECTED,
            "event_type": _or(event.get("event_type")),
            "amount": _or(event.get("amount_usdt", event.get("amount"))),
            "balance_before": _or(event.get("balance_before")),
            "balance_after": _or(event.get("balance_after")),
            "is_trading_pnl": bool(event.get("is_trading_pnl", False)),
            "is_external_capital_flow": bool(event.get("is_external_capital_flow", False)),
            "affects_performance_stats": bool(event.get("affects_performance_stats", False)),
            "explanation": explanation or _or(event.get("explanation")),
            "real_order": False,
        }
    )


def build_funding_event_attributed_card(attribution: Mapping[str, Any]) -> dict[str, Any]:
    """FUNDING_EVENT_ATTRIBUTED - funding/commission attribution roll-up."""
    return _finalize(
        {
            "card_type": CardType.FUNDING_EVENT_ATTRIBUTED,
            "attributed_funding_usdt": _or(attribution.get("attributed_funding_usdt")),
            "account_level_funding_usdt": _or(attribution.get("account_level_funding_usdt")),
            "total_funding_usdt": _or(attribution.get("total_funding_usdt")),
            "commission_total_usdt": _or(attribution.get("commission_total_usdt")),
            "attributed_commission_usdt": _or(attribution.get("attributed_commission_usdt")),
            "unattributed_funding_count": _or(attribution.get("unattributed_funding_count")),
            "ambiguous_funding_count": _or(attribution.get("ambiguous_funding_count")),
            "attribution_status": _or(attribution.get("attribution_status")),
            "real_order": False,
        }
    )


def build_kill_switch_card(
    *,
    armed: bool,
    arm_requested: bool = False,
    confirmation_code: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """LIVE_KILL_SWITCH (or arm-requested) operator card."""
    card_type = (
        CardType.LIVE_KILL_SWITCH_ARM_REQUESTED
        if arm_requested
        else CardType.LIVE_KILL_SWITCH
    )
    return _finalize(
        {
            "card_type": card_type,
            "kill_switch_armed": bool(armed),
            "arm_requested": bool(arm_requested),
            "confirmation_code": _or(confirmation_code),
            "reason": reason,
            "note": (
                "Second confirmation (/confirm_kill CODE) required."
                if arm_requested
                else "Kill switch armed; new entries blocked. Cancels/exits, if "
                "wired, route through the execution gateway + safety gate."
            ),
            "real_order": False,
        }
    )


def build_paused_card(*, paused: bool, reason: str = "") -> dict[str, Any]:
    """LIVE_PAUSED / LIVE_RESUMED operator card."""
    return _finalize(
        {
            "card_type": CardType.LIVE_PAUSED if paused else CardType.LIVE_RESUMED,
            "paused": bool(paused),
            "reason": reason,
            "note": (
                "New entries are paused; existing positions are not force-closed."
                if paused
                else "Scanning / new signals resumed; mode / risk / order gates "
                "are NOT bypassed."
            ),
            "real_order": False,
        }
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_card(card: Mapping[str, Any]) -> str:
    """Render a short, redacted one-line text view of a card.

    Defence-in-depth: re-redacts before building the string so a secret
    can never reach a Telegram message body.
    """
    c = redact(dict(card))
    ctype = c.get("card_type", "?")
    parts = [f"[ama-rt:live:{ctype}]"]
    mode = c.get("mode_display") or c.get("runtime_mode")
    if mode:
        parts.append(f"mode={mode}")
    for key in (
        "symbol",
        "side",
        "planned_entry_price",
        "planned_stop_price",
        "planned_take_profit_1",
        "planned_leverage",
        "net_pnl",
        "net_strategy_pnl",
        "gross_pnl",
        "commission_total",
        "funding_total",
        "reject_reason",
        "confirmation_code",
        "capital_profile_id",
        "attribution_status",
        "kill_switch_armed",
        "paused",
    ):
        if key in c and c[key] not in (None, PLACEHOLDER):
            parts.append(f"{key}={c[key]}")
    if "real_order" in c:
        parts.append(f"real_order={c['real_order']}")
    if c.get("order_id", PLACEHOLDER) != PLACEHOLDER:
        parts.append(f"order_id={c['order_id']}")
    return " ".join(str(p) for p in parts)


__all__ = [
    "TELEGRAM_FORMATTERS_MODULE",
    "PLACEHOLDER",
    "MODE_DISPLAY",
    "CardType",
    "mode_display",
    "build_execution_telegram_payload",
    "PAYLOAD_LIVE_ORDER_SUBMITTED",
    "PAYLOAD_LIVE_ORDER_FILLED",
    "PAYLOAD_LIVE_ORDER_PARTIALLY_FILLED",
    "PAYLOAD_LIVE_ORDER_CANCELED",
    "PAYLOAD_LIVE_ORDER_REJECTED",
    "PAYLOAD_LIVE_ORDER_FAILED",
    "PAYLOAD_LIVE_EXECUTION_BLOCKED",
    "PAYLOAD_LIVE_EXIT_FILLED",
    "build_shadow_entry_plan_card",
    "build_shadow_exit_plan_card",
    "build_shadow_risk_reject_card",
    "build_live_risk_reject_card",
    "build_status_card",
    "build_positions_card",
    "build_pnl_card",
    "build_risk_card",
    "build_capital_card",
    "build_profile_card",
    "build_mode_status_card",
    "build_help_card",
    "build_mode_switch_requested_card",
    "build_mode_changed_card",
    "build_capital_profile_changed_card",
    "build_profile_change_rejected_card",
    "build_capital_profile_mismatch_card",
    "build_capital_event_detected_card",
    "build_funding_event_attributed_card",
    "build_kill_switch_card",
    "build_paused_card",
    "render_card",
]
