"""Live Order Ledger (PR113 - Live Execution v0).

An append-only ledger of LIVE order / fill / cancel rows. It is kept
strictly SEPARATE from the blind / sim / paper-shadow trade ledger
(:mod:`app.sim`): nothing from a non-live path may ever be written here,
and nothing here is shared with a simulated ledger.

The headline figure carries funding forward even though PR113 cannot yet
attribute funding to a position/trade:

    net_pnl = realized_pnl - fee + funding_usdt_attributed

``funding_usdt_attributed`` defaults to 0.0 and
``funding_attribution_status`` defaults to
``UNATTRIBUTED_PENDING_POSITION_LINK`` (a PR114 handoff). Funding is
never silently dropped from the final PnL.

PR113 boundary: writing a ledger row is descriptive accounting only. It
never places / cancels an order and never flips a safety flag.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.clock import now_ms
from app.core.events import Event, EventType
from app.live.execution_models import (
    LiveExecutionStatus,
    LiveFillEvent,
    LiveOrderIntent,
    LiveOrderRequest,
    LiveOrderResult,
    OrderIntentType,
)
from app.live.pnl_accounting import FundingAttributionStatus

LIVE_ORDER_LEDGER_MODULE = "live.order_ledger"


def compute_net_pnl(
    realized_pnl_usdt: float, fee_usdt: float, funding_usdt_attributed: float
) -> float:
    """net = realized - fee + funding (funding is carried forward in PR113)."""
    return float(realized_pnl_usdt) - float(fee_usdt) + float(funding_usdt_attributed)


@dataclass(frozen=True)
class LiveOrderLedgerRow:
    """A single append-only LIVE order/fill/cancel ledger row."""

    ledger_id: str
    order_id: str | None
    client_order_id: str | None
    symbol: str
    side: str
    order_type: str
    intent_type: str
    runtime_mode: str
    capital_profile_id: str
    is_real_order: bool
    status: str
    submitted_at: int | None = None
    filled_at: int | None = None
    canceled_at: int | None = None
    requested_qty: float = 0.0
    filled_qty: float = 0.0
    requested_price: float | None = None
    avg_fill_price: float | None = None
    notional_usdt: float = 0.0
    fee_usdt: float = 0.0
    funding_usdt_attributed: float = 0.0
    realized_pnl_usdt: float = 0.0
    net_pnl_usdt: float = 0.0
    risk_decision_id: str | None = None
    opportunity_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    error_code: str | None = None
    error_message_sanitized: str | None = None
    funding_attribution_status: str = (
        FundingAttributionStatus.UNATTRIBUTED_PENDING_POSITION_LINK
    )
    recorded_at: int = field(default_factory=now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ledger_id": self.ledger_id,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "intent_type": self.intent_type,
            "runtime_mode": self.runtime_mode,
            "capital_profile_id": self.capital_profile_id,
            "is_real_order": self.is_real_order,
            "status": self.status,
            "submitted_at": self.submitted_at,
            "filled_at": self.filled_at,
            "canceled_at": self.canceled_at,
            "requested_qty": self.requested_qty,
            "filled_qty": self.filled_qty,
            "requested_price": self.requested_price,
            "avg_fill_price": self.avg_fill_price,
            "notional_usdt": self.notional_usdt,
            "fee_usdt": self.fee_usdt,
            "funding_usdt_attributed": self.funding_usdt_attributed,
            "realized_pnl_usdt": self.realized_pnl_usdt,
            "net_pnl_usdt": self.net_pnl_usdt,
            "risk_decision_id": self.risk_decision_id,
            "opportunity_id": self.opportunity_id,
            "evidence_refs": list(self.evidence_refs),
            "error_code": self.error_code,
            "error_message_sanitized": self.error_message_sanitized,
            "funding_attribution_status": self.funding_attribution_status,
            "recorded_at": self.recorded_at,
        }


class LiveOrderLedger:
    """Append-only ledger for LIVE orders / fills / cancels (PR113)."""

    def __init__(self, *, event_repo: Any | None = None, clock: Any = now_ms) -> None:
        self._rows: list[LiveOrderLedgerRow] = []
        self._event_repo = event_repo
        self._clock = clock

    @property
    def rows(self) -> tuple[LiveOrderLedgerRow, ...]:
        return tuple(self._rows)

    def __len__(self) -> int:
        return len(self._rows)

    def rows_for(self, client_order_id: str | None) -> tuple[LiveOrderLedgerRow, ...]:
        return tuple(r for r in self._rows if r.client_order_id == client_order_id)

    def rows_of_intent(self, intent_type: OrderIntentType | str) -> tuple[LiveOrderLedgerRow, ...]:
        value = intent_type.value if isinstance(intent_type, OrderIntentType) else str(intent_type)
        return tuple(r for r in self._rows if r.intent_type == value)

    # ------------------------------------------------------------------
    # Writers
    # ------------------------------------------------------------------
    def record_order(
        self,
        intent: LiveOrderIntent,
        result: LiveOrderResult,
        *,
        request: LiveOrderRequest | None = None,
        intent_type: OrderIntentType | None = None,
        risk_decision_id: str | None = None,
    ) -> LiveOrderLedgerRow:
        """Write the ENTRY / EXIT / REDUCE order row for a submission outcome."""
        itype = intent_type or intent.intent_type
        requested_qty = request.normalized_quantity if request else intent.quantity
        requested_price = (
            request.normalized_price if request else intent.price
        )
        if requested_price is None:
            requested_price = intent.planned_entry_price
        notional = float(intent.notional_usdt)
        if notional <= 0 and requested_qty and requested_price:
            notional = float(requested_qty) * float(requested_price)
        realized = result.realized_pnl_usdt or 0.0
        fee = result.fee_usdt or 0.0
        net = compute_net_pnl(realized, fee, 0.0)
        submitted_at = result.created_at if result.is_real_order else None
        filled_at = result.updated_at if result.status.is_fill else None
        row = LiveOrderLedgerRow(
            ledger_id=_ledger_id(),
            order_id=result.exchange_order_id,
            client_order_id=result.client_order_id or intent.client_order_id,
            symbol=result.symbol or intent.symbol,
            side=result.side.value,
            order_type=result.order_type.value,
            intent_type=itype.value,
            runtime_mode=intent.runtime_mode.value,
            capital_profile_id=intent.capital_profile_id.value,
            is_real_order=result.is_real_order,
            status=result.status.value,
            submitted_at=submitted_at,
            filled_at=filled_at,
            requested_qty=float(requested_qty or 0.0),
            filled_qty=float(result.executed_qty or 0.0),
            requested_price=requested_price,
            avg_fill_price=result.avg_fill_price,
            notional_usdt=notional,
            fee_usdt=fee,
            funding_usdt_attributed=0.0,
            realized_pnl_usdt=realized,
            net_pnl_usdt=net,
            risk_decision_id=risk_decision_id or intent.risk_decision_id,
            opportunity_id=intent.opportunity_id,
            evidence_refs=tuple(intent.evidence_refs),
            error_code=result.error_code,
            error_message_sanitized=result.error_message_sanitized,
        )
        return self._append(row, EventType.LIVE_ORDER_SUBMIT_REQUESTED)

    def record_fill(
        self,
        fill: LiveFillEvent,
        *,
        intent: LiveOrderIntent | None = None,
        intent_type: OrderIntentType | None = None,
        runtime_mode: str | None = None,
        capital_profile_id: str | None = None,
        funding_usdt_attributed: float = 0.0,
        risk_decision_id: str | None = None,
        opportunity_id: str | None = None,
    ) -> LiveOrderLedgerRow:
        """Write a FILL row for an execution (carries fee + funding placeholder)."""
        itype = intent_type or (intent.intent_type if intent else OrderIntentType.ENTRY)
        realized = fill.realized_pnl_usdt or 0.0
        net = compute_net_pnl(realized, fill.fee_usdt, funding_usdt_attributed)
        is_exit = itype in (OrderIntentType.EXIT, OrderIntentType.REDUCE)
        row = LiveOrderLedgerRow(
            ledger_id=_ledger_id(),
            order_id=fill.order_id,
            client_order_id=fill.client_order_id or (intent.client_order_id if intent else None),
            symbol=fill.symbol,
            side=fill.side.value,
            order_type=(intent.order_type.value if intent else "MARKET"),
            intent_type=itype.value,
            runtime_mode=(
                runtime_mode or (intent.runtime_mode.value if intent else "LIVE_LIMITED")
            ),
            capital_profile_id=(
                capital_profile_id
                or (intent.capital_profile_id.value if intent else "L1_10U_PROBE")
            ),
            is_real_order=True,
            status=LiveExecutionStatus.FILLED.value,
            filled_at=fill.trade_time,
            requested_qty=float(intent.quantity if intent else fill.quantity),
            filled_qty=fill.quantity,
            requested_price=(intent.planned_entry_price if intent else fill.price),
            avg_fill_price=fill.price,
            notional_usdt=fill.quote_qty,
            fee_usdt=fill.fee_usdt,
            funding_usdt_attributed=float(funding_usdt_attributed),
            realized_pnl_usdt=realized,
            net_pnl_usdt=net,
            risk_decision_id=risk_decision_id or (intent.risk_decision_id if intent else None),
            opportunity_id=opportunity_id or (intent.opportunity_id if intent else None),
            evidence_refs=tuple(intent.evidence_refs) if intent else (),
            funding_attribution_status=fill.funding_attribution_status,
        )
        event_type = EventType.LIVE_EXIT_FILLED if is_exit else EventType.LIVE_ORDER_FILLED
        return self._append(row, event_type)

    def record_cancel(
        self,
        result: LiveOrderResult,
        *,
        intent: LiveOrderIntent | None = None,
        risk_decision_id: str | None = None,
    ) -> LiveOrderLedgerRow:
        """Write a CANCEL row."""
        row = LiveOrderLedgerRow(
            ledger_id=_ledger_id(),
            order_id=result.exchange_order_id,
            client_order_id=result.client_order_id or (intent.client_order_id if intent else None),
            symbol=result.symbol,
            side=result.side.value,
            order_type=result.order_type.value,
            intent_type=OrderIntentType.CANCEL.value,
            runtime_mode=(intent.runtime_mode.value if intent else "LIVE_LIMITED"),
            capital_profile_id=(intent.capital_profile_id.value if intent else "L1_10U_PROBE"),
            is_real_order=result.is_real_order,
            status=result.status.value,
            canceled_at=result.updated_at,
            requested_qty=float(result.executed_qty or 0.0),
            filled_qty=float(result.executed_qty or 0.0),
            risk_decision_id=risk_decision_id or (intent.risk_decision_id if intent else None),
            opportunity_id=(intent.opportunity_id if intent else None),
            error_code=result.error_code,
            error_message_sanitized=result.error_message_sanitized,
        )
        return self._append(row, EventType.LIVE_ORDER_CANCELED)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _append(self, row: LiveOrderLedgerRow, event_type: EventType) -> LiveOrderLedgerRow:
        self._rows.append(row)
        if self._event_repo is not None:
            try:
                self._event_repo.append(
                    Event(
                        event_type=event_type,
                        source_module=LIVE_ORDER_LEDGER_MODULE,
                        symbol=row.symbol,
                        order_id=row.order_id,
                        payload={
                            "ledger_row": row.to_dict(),
                            "is_real_order": row.is_real_order,
                            # PR113 safety markers.
                            "exchange_live_orders": False,
                            "trade_authority": False,
                            "ai_trade_authority": False,
                        },
                    )
                )
            except Exception:  # pragma: no cover - audit must not crash accounting
                pass
        return row


def _ledger_id() -> str:
    return f"live_order_{uuid.uuid4().hex[:16]}"


__all__ = [
    "LIVE_ORDER_LEDGER_MODULE",
    "compute_net_pnl",
    "LiveOrderLedgerRow",
    "LiveOrderLedger",
]
