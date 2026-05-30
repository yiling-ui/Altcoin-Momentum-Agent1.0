"""Execution Telegram payloads (PR113 - Live Execution v0).

Builds operator-card PAYLOADS for the live order lifecycle. PR113 does
NOT need a full Telegram command console; it only needs the structured,
auditable payloads so a later PR can render / send them.

Every payload follows one stable schema (planned + actual fields) so an
operator can compare what was planned to what really happened:

  - 空盘跑 (LIVE_SHADOW) / blocked / rejected payloads:
      real_order=False, real_capital_changed=False, order_id="--",
      actual_entry_price / actual_exit_price = "--".
  - 有资金跑 (LIVE_LIMITED) payloads:
      real_order becomes True ONLY after an actual fill on a real order,
      and the actual order / fill fields are populated.

This module builds payloads only. It never opens a Telegram socket, never
sends a message, never places an order, and never flips a safety flag.
``telegram_outbound_enabled`` stays False.
"""

from __future__ import annotations

from typing import Any

from app.core.enums import LiveRuntimeMode
from app.core.events import EventType
from app.live.execution_models import (
    LiveFillEvent,
    LiveOrderIntent,
    LiveOrderResult,
)

PLACEHOLDER = "--"

# Payload type tags == the PR113 event type values.
PAYLOAD_LIVE_ORDER_SUBMIT_REQUESTED = EventType.LIVE_ORDER_SUBMIT_REQUESTED.value
PAYLOAD_LIVE_ORDER_SUBMITTED = EventType.LIVE_ORDER_SUBMITTED.value
PAYLOAD_LIVE_ORDER_FILLED = EventType.LIVE_ORDER_FILLED.value
PAYLOAD_LIVE_ORDER_PARTIALLY_FILLED = EventType.LIVE_ORDER_PARTIALLY_FILLED.value
PAYLOAD_LIVE_ORDER_CANCELED = EventType.LIVE_ORDER_CANCELED.value
PAYLOAD_LIVE_ORDER_REJECTED = EventType.LIVE_ORDER_REJECTED.value
PAYLOAD_LIVE_ORDER_FAILED = EventType.LIVE_ORDER_FAILED.value
PAYLOAD_LIVE_EXECUTION_BLOCKED = EventType.LIVE_EXECUTION_BLOCKED.value
PAYLOAD_LIVE_EXIT_FILLED = EventType.LIVE_EXIT_FILLED.value

EXECUTION_PAYLOAD_TYPES: frozenset[str] = frozenset(
    {
        PAYLOAD_LIVE_ORDER_SUBMIT_REQUESTED,
        PAYLOAD_LIVE_ORDER_SUBMITTED,
        PAYLOAD_LIVE_ORDER_FILLED,
        PAYLOAD_LIVE_ORDER_PARTIALLY_FILLED,
        PAYLOAD_LIVE_ORDER_CANCELED,
        PAYLOAD_LIVE_ORDER_REJECTED,
        PAYLOAD_LIVE_ORDER_FAILED,
        PAYLOAD_LIVE_EXECUTION_BLOCKED,
        PAYLOAD_LIVE_EXIT_FILLED,
    }
)

# Payload types that represent an actual fill (exit context).
_EXIT_PAYLOAD_TYPES: frozenset[str] = frozenset({PAYLOAD_LIVE_EXIT_FILLED})

# Payload types that can ever carry real_order=True (an order actually
# left / filled on the exchange).
_REAL_ORDER_CAPABLE_TYPES: frozenset[str] = frozenset(
    {
        PAYLOAD_LIVE_ORDER_SUBMITTED,
        PAYLOAD_LIVE_ORDER_FILLED,
        PAYLOAD_LIVE_ORDER_PARTIALLY_FILLED,
        PAYLOAD_LIVE_ORDER_CANCELED,
        PAYLOAD_LIVE_EXIT_FILLED,
    }
)

MODE_DISPLAY: dict[LiveRuntimeMode, str] = {
    LiveRuntimeMode.LIVE_SHADOW: "空盘跑",
    LiveRuntimeMode.LIVE_LIMITED: "有资金跑",
}


def _mode_display(mode: LiveRuntimeMode) -> str:
    return MODE_DISPLAY.get(mode, MODE_DISPLAY[LiveRuntimeMode.LIVE_SHADOW])


def _safety_markers() -> dict[str, Any]:
    return {
        "trade_authority": False,
        "ai_trade_authority": False,
        "exchange_live_orders_default": False,
        "telegram_outbound_enabled": False,
        "phase_12_forbidden": True,
    }


def _or_placeholder(value: Any) -> Any:
    return PLACEHOLDER if value is None else value


def build_execution_telegram_payload(
    payload_type: str,
    *,
    intent: LiveOrderIntent | None = None,
    result: LiveOrderResult | None = None,
    fill: LiveFillEvent | None = None,
    risk_decision: Any | None = None,
    reject_reason: str | None = None,
    runtime_mode: LiveRuntimeMode | None = None,
    leverage: float | None = None,
    balance_before: float | None = None,
    balance_after: float | None = None,
    funding_usdt: float = 0.0,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Build a single execution operator payload following the PR113 schema."""
    if payload_type not in EXECUTION_PAYLOAD_TYPES:
        raise ValueError(f"unknown execution payload_type: {payload_type!r}")

    # Resolve runtime mode (intent > explicit > shadow default).
    mode = runtime_mode
    if mode is None and intent is not None:
        mode = intent.runtime_mode
    if mode is None:
        mode = LiveRuntimeMode.LIVE_SHADOW

    is_exit = payload_type in _EXIT_PAYLOAD_TYPES or bool(
        (result is not None and result.reduce_only)
        or (intent is not None and intent.reduce_only)
    )

    # Decide real_order: only a real, filled/submitted order on a funded
    # (LIVE_LIMITED) runtime may ever be real_order=True.
    real_order = False
    if (
        payload_type in _REAL_ORDER_CAPABLE_TYPES
        and result is not None
        and result.is_real_order
        and mode is LiveRuntimeMode.LIVE_LIMITED
    ):
        # A SUBMITTED/CANCELED real order counts; a FILLED/PARTIAL needs a fill.
        if payload_type in (
            PAYLOAD_LIVE_ORDER_FILLED,
            PAYLOAD_LIVE_ORDER_PARTIALLY_FILLED,
            PAYLOAD_LIVE_EXIT_FILLED,
        ):
            real_order = result.status.is_fill or (fill is not None)
        else:
            real_order = True

    # Symbol / side / order_type.
    symbol = (
        (result.symbol if result else None)
        or (fill.symbol if fill else None)
        or (intent.symbol if intent else PLACEHOLDER)
    )
    side = (
        (result.side.value if result else None)
        or (fill.side.value if fill else None)
        or (intent.side.value if intent else PLACEHOLDER)
    )
    order_type = (
        (result.order_type.value if result else None)
        or (intent.order_type.value if intent else PLACEHOLDER)
    )

    # Leverage.
    lev = leverage
    if lev is None and intent is not None:
        lev = intent.planned_leverage

    # Actual fill prices.
    actual_fill_price = None
    if result is not None and result.avg_fill_price:
        actual_fill_price = result.avg_fill_price
    elif fill is not None:
        actual_fill_price = fill.price

    actual_entry_price = PLACEHOLDER
    actual_exit_price = PLACEHOLDER
    if real_order and actual_fill_price is not None:
        if is_exit:
            actual_exit_price = actual_fill_price
        else:
            actual_entry_price = actual_fill_price

    # Quantity / notional / fee / pnl.
    quantity = None
    if result is not None and result.executed_qty:
        quantity = result.executed_qty
    elif fill is not None:
        quantity = fill.quantity
    elif intent is not None:
        quantity = intent.quantity

    notional = None
    if result is not None and result.cum_quote:
        notional = result.cum_quote
    elif fill is not None:
        notional = fill.quote_qty
    elif intent is not None and intent.notional_usdt:
        notional = intent.notional_usdt

    fee_usdt = None
    if result is not None and result.fee_usdt is not None:
        fee_usdt = result.fee_usdt
    elif fill is not None:
        fee_usdt = fill.fee_usdt

    gross_pnl = None
    if result is not None and result.realized_pnl_usdt is not None:
        gross_pnl = result.realized_pnl_usdt
    elif fill is not None and fill.realized_pnl_usdt is not None:
        gross_pnl = fill.realized_pnl_usdt

    net_pnl = None
    if gross_pnl is not None:
        net_pnl = float(gross_pnl) - float(fee_usdt or 0.0) + float(funding_usdt or 0.0)

    pnl_pct = None
    if gross_pnl is not None and notional:
        try:
            pnl_pct = float(gross_pnl) / float(notional)
        except ZeroDivisionError:  # pragma: no cover
            pnl_pct = None

    # Order id (always "--" when not a real order).
    order_id = PLACEHOLDER
    if real_order and result is not None and result.exchange_order_id:
        order_id = result.exchange_order_id
    client_order_id = (
        (result.client_order_id if result else None)
        or (fill.client_order_id if fill else None)
        or (intent.client_order_id if intent else PLACEHOLDER)
    )

    risk_decision_repr: Any = PLACEHOLDER
    if risk_decision is not None:
        if hasattr(risk_decision, "approved"):
            risk_decision_repr = {
                "approved": bool(getattr(risk_decision, "approved")),
                "reject_reason": getattr(risk_decision, "reject_reason", None),
                "real_order_allowed": getattr(risk_decision, "real_order_allowed", False),
            }
        else:
            risk_decision_repr = risk_decision

    payload: dict[str, Any] = {
        "payload_type": payload_type,
        "event_type": payload_type,
        "mode_display": _mode_display(mode),
        "runtime_mode": mode.value,
        "real_order": real_order,
        "real_capital_changed": real_order and payload_type in (
            PAYLOAD_LIVE_ORDER_FILLED,
            PAYLOAD_LIVE_ORDER_PARTIALLY_FILLED,
            PAYLOAD_LIVE_EXIT_FILLED,
        ),
        "symbol": symbol,
        "side": side,
        "order_type": order_type,
        "leverage": _or_placeholder(lev),
        "planned_entry_price": _or_placeholder(intent.planned_entry_price if intent else None),
        "actual_entry_price": actual_entry_price,
        "planned_exit_price": _or_placeholder(
            intent.planned_take_profit_price if intent else None
        ),
        "actual_exit_price": actual_exit_price,
        "planned_stop_price": _or_placeholder(intent.planned_stop_price if intent else None),
        "planned_take_profit_price": _or_placeholder(
            intent.planned_take_profit_price if intent else None
        ),
        "quantity": _or_placeholder(quantity),
        "notional_usdt": _or_placeholder(notional),
        "fee_usdt": _or_placeholder(fee_usdt),
        "funding_usdt": funding_usdt,
        "gross_pnl": _or_placeholder(gross_pnl),
        "net_pnl": _or_placeholder(net_pnl),
        "pnl_pct": _or_placeholder(pnl_pct),
        "balance_before": _or_placeholder(balance_before),
        "balance_after": _or_placeholder(balance_after),
        "order_id": order_id,
        "client_order_id": _or_placeholder(client_order_id),
        "risk_decision": risk_decision_repr,
        "reject_reason": _or_placeholder(reject_reason),
        "event_id": _or_placeholder(event_id),
    }
    payload.update(_safety_markers())
    return payload


__all__ = [
    "PLACEHOLDER",
    "EXECUTION_PAYLOAD_TYPES",
    "MODE_DISPLAY",
    "PAYLOAD_LIVE_ORDER_SUBMIT_REQUESTED",
    "PAYLOAD_LIVE_ORDER_SUBMITTED",
    "PAYLOAD_LIVE_ORDER_FILLED",
    "PAYLOAD_LIVE_ORDER_PARTIALLY_FILLED",
    "PAYLOAD_LIVE_ORDER_CANCELED",
    "PAYLOAD_LIVE_ORDER_REJECTED",
    "PAYLOAD_LIVE_ORDER_FAILED",
    "PAYLOAD_LIVE_EXECUTION_BLOCKED",
    "PAYLOAD_LIVE_EXIT_FILLED",
    "build_execution_telegram_payload",
]
