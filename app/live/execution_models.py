"""Order models for the Live Execution Gateway (PR113 - Live Execution v0).

The order lifecycle's data contract:

    Signal / Strategy Plan
      -> LiveOrderIntent          (what we WANT to do; carries provenance)
      -> LiveRiskDecision         (PR112 dry risk pre-check)
      -> LiveExecutionGateway     (the single real-order entry point)
      -> LiveOrderRequest         (normalised, exchange-ready)
      -> BinanceExecutionAdapter  (compose + send, or refuse)
      -> LiveOrderResult / LiveFillEvent
      -> LiveOrderLedger
      -> Telegram payload

Every model here is a frozen dataclass with a ``to_dict`` that is safe
for logs (no key / secret / signature). PR113 hard markers
(``is_real_order`` defaults False; ``real_order_allowed`` must be passed
explicitly) keep the safe-by-default posture visible.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.clock import now_ms
from app.core.enums import LiveRuntimeMode, OrderSource
from app.live.capital_profile import CapitalProfileId
from app.live.pnl_accounting import FundingAttributionStatus

# Prefix for client order ids minted by the gateway. Binance limits the
# newClientOrderId to ^[\.A-Z\:/a-z0-9_-]{1,36}$.
CLIENT_ORDER_ID_PREFIX = "amart"


def generate_client_order_id(prefix: str = CLIENT_ORDER_ID_PREFIX) -> str:
    """Mint a unique, idempotency-safe client order id (<=36 chars)."""
    return f"{prefix}-{uuid.uuid4().hex[:24]}"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class OrderSide(str, Enum):
    """Binance order side."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Supported Binance USDT-M futures order types (PR113)."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"

    @property
    def needs_price(self) -> bool:
        return self is OrderType.LIMIT

    @property
    def needs_stop_price(self) -> bool:
        return self in (OrderType.STOP_MARKET, OrderType.TAKE_PROFIT_MARKET)


class TimeInForce(str, Enum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    GTX = "GTX"


class OrderIntentType(str, Enum):
    """Ledger-level intent classification."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REDUCE = "REDUCE"
    CANCEL = "CANCEL"


class LiveExecutionStatus(str, Enum):
    """Internal order/result status taxonomy (superset of Binance status)."""

    # Internal lifecycle states.
    SUBMIT_REQUESTED = "SUBMIT_REQUESTED"
    SUBMITTED = "SUBMITTED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    DRY_RUN = "DRY_RUN"
    # Exchange order states (mirror Binance).
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

    @property
    def is_terminal(self) -> bool:
        return self in (
            LiveExecutionStatus.FILLED,
            LiveExecutionStatus.CANCELED,
            LiveExecutionStatus.REJECTED,
            LiveExecutionStatus.EXPIRED,
            LiveExecutionStatus.BLOCKED,
            LiveExecutionStatus.FAILED,
        )

    @property
    def is_fill(self) -> bool:
        return self in (
            LiveExecutionStatus.PARTIALLY_FILLED,
            LiveExecutionStatus.FILLED,
        )


# Map a raw Binance order ``status`` string to our taxonomy.
_BINANCE_STATUS_MAP: dict[str, LiveExecutionStatus] = {
    "NEW": LiveExecutionStatus.NEW,
    "PARTIALLY_FILLED": LiveExecutionStatus.PARTIALLY_FILLED,
    "FILLED": LiveExecutionStatus.FILLED,
    "CANCELED": LiveExecutionStatus.CANCELED,
    "CANCELLED": LiveExecutionStatus.CANCELED,
    "REJECTED": LiveExecutionStatus.REJECTED,
    "EXPIRED": LiveExecutionStatus.EXPIRED,
    "EXPIRED_IN_MATCH": LiveExecutionStatus.EXPIRED,
    "NEW_INSURANCE": LiveExecutionStatus.NEW,
    "NEW_ADL": LiveExecutionStatus.NEW,
}


def map_binance_status(raw_status: str | None) -> LiveExecutionStatus:
    """Map a raw Binance status to :class:`LiveExecutionStatus` (safe default)."""
    if not raw_status:
        return LiveExecutionStatus.NEW
    return _BINANCE_STATUS_MAP.get(str(raw_status).strip().upper(), LiveExecutionStatus.NEW)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_side(side: Any) -> OrderSide:
    if isinstance(side, OrderSide):
        return side
    return OrderSide(str(side).strip().upper())


def _as_order_type(order_type: Any) -> OrderType:
    if isinstance(order_type, OrderType):
        return order_type
    return OrderType(str(order_type).strip().upper())


# ---------------------------------------------------------------------------
# LiveOrderIntent - what we WANT to do (carries provenance + plan)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LiveOrderIntent:
    """A request to place a real order, carrying its full plan + provenance.

    This is the PR113 *execution* intent. It is distinct from PR110's
    :class:`app.live.path_isolation.LiveOrderIntent` (provenance only) and
    PR112's :class:`app.live.live_risk_engine.LiveOrderIntent` (risk
    pre-check geometry). The execution intent carries everything the
    gateway + adapter need to compose an exchange-ready request and to
    write an auditable ledger row.
    """

    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float = 0.0
    notional_usdt: float = 0.0
    price: float | None = None
    stop_price: float | None = None
    reduce_only: bool = False
    time_in_force: TimeInForce = TimeInForce.GTC
    planned_entry_price: float | None = None
    planned_stop_price: float | None = None
    planned_take_profit_price: float | None = None
    planned_leverage: float = 1.0
    exit_plan_present: bool = False
    stop_plan_present: bool = False
    client_order_id: str | None = None
    source: OrderSource = OrderSource.LIVE
    runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_SHADOW
    capital_profile_id: CapitalProfileId = CapitalProfileId.L0_SHADOW
    opportunity_id: str | None = None
    risk_decision_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    # An opening order normally requires a stop + exit plan. A documented
    # emergency / specific order-type exception may waive that (e.g. a
    # reduce-only emergency close). Defaults to no exception.
    emergency_exception: bool = False
    emergency_exception_reason: str | None = None

    def __post_init__(self) -> None:
        # Normalise enum-ish fields passed as plain strings.
        object.__setattr__(self, "side", _as_side(self.side))
        object.__setattr__(self, "order_type", _as_order_type(self.order_type))
        if not isinstance(self.time_in_force, TimeInForce):
            object.__setattr__(
                self, "time_in_force", TimeInForce(str(self.time_in_force).strip().upper())
            )
        if isinstance(self.source, str) and not isinstance(self.source, OrderSource):
            object.__setattr__(self, "source", OrderSource(self.source))
        if isinstance(self.runtime_mode, str) and not isinstance(
            self.runtime_mode, LiveRuntimeMode
        ):
            object.__setattr__(self, "runtime_mode", LiveRuntimeMode(self.runtime_mode))
        if isinstance(self.capital_profile_id, str) and not isinstance(
            self.capital_profile_id, CapitalProfileId
        ):
            object.__setattr__(
                self, "capital_profile_id", CapitalProfileId(self.capital_profile_id)
            )

    @property
    def is_opening_order(self) -> bool:
        """True for an order that opens / adds exposure (needs stop+exit plan)."""
        return not self.reduce_only and self.intent_type is OrderIntentType.ENTRY

    @property
    def intent_type(self) -> OrderIntentType:
        """Ledger-level intent type derived from reduce_only."""
        if self.reduce_only:
            return OrderIntentType.REDUCE
        return OrderIntentType.ENTRY

    @property
    def has_stop_and_exit_plan(self) -> bool:
        return bool(self.stop_plan_present and self.exit_plan_present)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "notional_usdt": self.notional_usdt,
            "price": self.price,
            "stop_price": self.stop_price,
            "reduce_only": self.reduce_only,
            "time_in_force": self.time_in_force.value,
            "planned_entry_price": self.planned_entry_price,
            "planned_stop_price": self.planned_stop_price,
            "planned_take_profit_price": self.planned_take_profit_price,
            "planned_leverage": self.planned_leverage,
            "exit_plan_present": self.exit_plan_present,
            "stop_plan_present": self.stop_plan_present,
            "client_order_id": self.client_order_id,
            "source": self.source.value,
            "runtime_mode": self.runtime_mode.value,
            "capital_profile_id": self.capital_profile_id.value,
            "opportunity_id": self.opportunity_id,
            "risk_decision_id": self.risk_decision_id,
            "evidence_refs": list(self.evidence_refs),
            "emergency_exception": self.emergency_exception,
            "emergency_exception_reason": self.emergency_exception_reason,
            "intent_type": self.intent_type.value,
        }


# ---------------------------------------------------------------------------
# LiveOrderRequest - normalised, exchange-ready
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LiveOrderRequest:
    """A normalised, exchange-ready order request.

    ``dry_run`` and ``real_order_allowed`` are explicit. ``dry_run=True``
    or ``real_order_allowed=False`` means the adapter MUST NOT open a
    socket (it returns a blocked / dry result).
    """

    normalized_symbol: str
    normalized_quantity: float
    normalized_price: float | None
    normalized_stop_price: float | None
    order_type: OrderType
    side: OrderSide
    reduce_only: bool
    client_order_id: str
    time_in_force: TimeInForce = TimeInForce.GTC
    dry_run: bool = True
    real_order_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_symbol": self.normalized_symbol,
            "normalized_quantity": self.normalized_quantity,
            "normalized_price": self.normalized_price,
            "normalized_stop_price": self.normalized_stop_price,
            "order_type": self.order_type.value,
            "side": self.side.value,
            "reduce_only": self.reduce_only,
            "client_order_id": self.client_order_id,
            "time_in_force": self.time_in_force.value,
            "dry_run": self.dry_run,
            "real_order_allowed": self.real_order_allowed,
        }


# ---------------------------------------------------------------------------
# LiveOrderResult - outcome of a submit / cancel / status read
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LiveOrderResult:
    """Outcome of a submit / cancel / status read.

    ``is_real_order`` is True ONLY when a real HTTP order request actually
    left the system. A blocked / dry result keeps ``is_real_order=False``.
    """

    status: LiveExecutionStatus
    client_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    exchange_order_id: str | None = None
    submitted_price: float | None = None
    avg_fill_price: float | None = None
    executed_qty: float = 0.0
    cum_quote: float = 0.0
    fee_usdt: float | None = None
    realized_pnl_usdt: float | None = None
    raw_status: str | None = None
    error_code: str | None = None
    error_message_sanitized: str | None = None
    reduce_only: bool = False
    created_at: int = field(default_factory=now_ms)
    updated_at: int = field(default_factory=now_ms)
    is_real_order: bool = False
    audit_event: str | None = None

    @property
    def is_filled(self) -> bool:
        return self.status is LiveExecutionStatus.FILLED

    @property
    def is_partial(self) -> bool:
        return self.status is LiveExecutionStatus.PARTIALLY_FILLED

    @property
    def is_blocked(self) -> bool:
        return self.status is LiveExecutionStatus.BLOCKED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "exchange_order_id": self.exchange_order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "submitted_price": self.submitted_price,
            "avg_fill_price": self.avg_fill_price,
            "executed_qty": self.executed_qty,
            "cum_quote": self.cum_quote,
            "fee_usdt": self.fee_usdt,
            "realized_pnl_usdt": self.realized_pnl_usdt,
            "raw_status": self.raw_status,
            "error_code": self.error_code,
            "error_message_sanitized": self.error_message_sanitized,
            "reduce_only": self.reduce_only,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_real_order": self.is_real_order,
            "audit_event": self.audit_event,
        }


# ---------------------------------------------------------------------------
# LiveFillEvent - a single execution / trade
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LiveFillEvent:
    """A single fill (execution) on an order.

    ``funding_attribution_status`` defaults to
    ``UNATTRIBUTED_PENDING_POSITION_LINK`` (PR113 carries funding forward;
    position-level attribution is a PR114 handoff).
    """

    fill_id: str
    order_id: str | None
    client_order_id: str | None
    symbol: str
    side: OrderSide
    price: float
    quantity: float
    quote_qty: float
    fee_asset: str = "USDT"
    fee_amount: float = 0.0
    fee_usdt: float = 0.0
    trade_time: int | None = None
    liquidity_side: str | None = None
    realized_pnl_usdt: float | None = None
    funding_attribution_status: str = (
        FundingAttributionStatus.UNATTRIBUTED_PENDING_POSITION_LINK
    )

    @classmethod
    def from_user_trade(cls, row: dict[str, Any]) -> "LiveFillEvent":
        """Parse a Binance ``/fapi/v1/userTrades`` row into a fill event."""
        price = _to_float(row.get("price"))
        qty = _to_float(row.get("qty"))
        quote_qty = _to_float(row.get("quoteQty")) or (price * qty)
        commission = _to_float(row.get("commission"))
        fee_asset = str(row.get("commissionAsset", "USDT") or "USDT")
        # Only treat the commission as USDT-denominated when it is paid in
        # USDT; otherwise keep fee_usdt 0.0 and carry the raw amount/asset
        # forward (a later PR converts non-USDT fees).
        fee_usdt = commission if fee_asset.upper() == "USDT" else 0.0
        liquidity = "MAKER" if bool(row.get("maker", False)) else "TAKER"
        side_raw = row.get("side")
        if side_raw is None:
            # Some userTrades rows use buyer/maker booleans only; default BUY.
            side = OrderSide.BUY if bool(row.get("buyer", True)) else OrderSide.SELL
        else:
            side = _as_side(side_raw)
        trade_time = None
        if row.get("time") is not None:
            try:
                trade_time = int(row.get("time"))
            except (TypeError, ValueError):
                trade_time = None
        return cls(
            fill_id=str(row.get("id", "") or generate_client_order_id("fill")),
            order_id=(str(row.get("orderId")) if row.get("orderId") is not None else None),
            client_order_id=(
                str(row.get("clientOrderId")) if row.get("clientOrderId") else None
            ),
            symbol=str(row.get("symbol", "") or ""),
            side=side,
            price=price,
            quantity=qty,
            quote_qty=quote_qty,
            fee_asset=fee_asset,
            fee_amount=commission,
            fee_usdt=fee_usdt,
            trade_time=trade_time,
            liquidity_side=liquidity,
            realized_pnl_usdt=(
                _to_float(row.get("realizedPnl")) if "realizedPnl" in row else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "price": self.price,
            "quantity": self.quantity,
            "quote_qty": self.quote_qty,
            "fee_asset": self.fee_asset,
            "fee_amount": self.fee_amount,
            "fee_usdt": self.fee_usdt,
            "trade_time": self.trade_time,
            "liquidity_side": self.liquidity_side,
            "realized_pnl_usdt": self.realized_pnl_usdt,
            "funding_attribution_status": self.funding_attribution_status,
        }


# ---------------------------------------------------------------------------
# OrderValidationResult - exchangeInfo / profile validation
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OrderValidationResult:
    """Result of validating an order against exchangeInfo + profile bounds."""

    ok: bool
    reasons: tuple[str, ...]
    normalized_symbol: str
    normalized_quantity: float
    normalized_price: float | None
    normalized_stop_price: float | None
    effective_notional_usdt: float
    tick_size: float = 0.0
    step_size: float = 0.0
    min_qty: float = 0.0
    min_notional: float = 0.0
    symbol_tradable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reasons": list(self.reasons),
            "normalized_symbol": self.normalized_symbol,
            "normalized_quantity": self.normalized_quantity,
            "normalized_price": self.normalized_price,
            "normalized_stop_price": self.normalized_stop_price,
            "effective_notional_usdt": self.effective_notional_usdt,
            "tick_size": self.tick_size,
            "step_size": self.step_size,
            "min_qty": self.min_qty,
            "min_notional": self.min_notional,
            "symbol_tradable": self.symbol_tradable,
        }


class OrderValidationReason:
    """Closed taxonomy of order-validation reject reasons (PR113)."""

    SYMBOL_NOT_TRADABLE = "symbol_not_tradable"
    SYMBOL_FILTER_MISSING = "symbol_filter_missing"
    QUANTITY_NON_POSITIVE = "quantity_non_positive"
    QUANTITY_BELOW_MIN_QTY = "quantity_below_min_qty"
    QUANTITY_PRECISION_INVALID = "quantity_precision_invalid"
    PRICE_REQUIRED_FOR_LIMIT = "price_required_for_limit"
    PRICE_PRECISION_INVALID = "price_precision_invalid"
    STOP_PRICE_REQUIRED = "stop_price_required"
    MIN_NOTIONAL_NOT_MET = "min_notional_not_met"
    REDUCE_ONLY_REQUIRES_QUANTITY = "reduce_only_requires_quantity"


__all__ = [
    "CLIENT_ORDER_ID_PREFIX",
    "generate_client_order_id",
    "OrderSide",
    "OrderType",
    "TimeInForce",
    "OrderIntentType",
    "LiveExecutionStatus",
    "map_binance_status",
    "LiveOrderIntent",
    "LiveOrderRequest",
    "LiveOrderResult",
    "LiveFillEvent",
    "OrderValidationResult",
    "OrderValidationReason",
]
