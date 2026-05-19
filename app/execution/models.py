"""Phase 9 Execution FSM data models (Spec §30, Issue #9).

Phase 9 ships the Execution FSM **driver** that turns risk-approved
trade decisions into paper-mode order lifecycle events. The driver
operates ENTIRELY in paper / mock mode in Phase 9. It does NOT call
any of the four ``ExchangeClientBase`` write surfaces (those still
raise :class:`SafeModeViolation` and Phase 9 must NEVER override
them). The execution flow lives instead in an in-memory
:class:`PaperLedger` that future phases will replace with a real
exchange adapter behind the Risk Engine.

Phase 9 models are deliberately narrow:

  - Frozen Pydantic v2 value objects for the **immutable** descriptors
    every event payload needs (``OrderRequest``, ``FillEvent``,
    ``StopEvent``).
  - A mutable :class:`ExecutionSession` dataclass for the per-order
    lifecycle state the driver advances.
  - Typed enums (``OrderKind``, ``OrderSide``, ``TimeInForce``,
    ``MarginMode``, ``OrderIntent``) so Phase 9 callers cannot pass
    free-form strings into a write-shaped surface.

Hard rules enforced at the model level:

  - ``MarginMode`` only admits ``ISOLATED``. Cross margin is a
    construction-time refusal (Spec §13.2 + Spec §30.2 "禁止 cross
    margin").
  - ``qty`` must be > 0.
  - Reduce-only intents (``LOCK_PROFIT``, ``FORCED_EXIT``,
    ``DISTRIBUTION_EXIT``, ``PROTECTIVE_CLOSE``, ``KILL_ALL``,
    ``STOP_ATTACH``) auto-resolve to ``reduce_only=True`` /
    ``is_new_open=False`` for the Risk Engine.
  - The ``OrderRequest`` does NOT carry an ``api_key`` /
    ``api_secret`` field anywhere, ever (Phase 8.5 boundary).

Phase 9 boundary
----------------

Nothing in this module:

  - imports an exchange SDK
  - opens a network socket
  - reads ``os.environ``
  - calls an LLM
  - subclasses :class:`ExchangeClientBase`
  - defines ``create_order``, ``cancel_order``, ``set_leverage`` or
    ``set_margin_mode``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.clock import now_ms
from app.core.enums import Direction, ExecutionState


# ---------------------------------------------------------------------------
# Order vocabulary
# ---------------------------------------------------------------------------
class OrderKind(str, Enum):
    """Phase 9 order types.

    ``LIMIT`` is the Phase 9 default (Spec §30.2 "优先限价单"). ``MARKET``
    is admissible only for protective-close / forced-exit / kill_all
    intents - the driver rejects a ``MARKET`` ``OrderRequest`` whose
    intent is :class:`OrderIntent.NEW_OPEN` (Spec §30.2 "默认禁止裸市
    价追单").
    """

    LIMIT = "limit"
    MARKET = "market"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"


class OrderSide(str, Enum):
    """Order side. Maps to :class:`Direction` via :func:`side_for_direction`."""

    BUY = "buy"
    SELL = "sell"


class TimeInForce(str, Enum):
    """Time-in-force. Phase 9 default is GTC for limits, IOC for protective
    market exits. FOK is reserved for Issue #10."""

    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class MarginMode(str, Enum):
    """Margin mode. Phase 9 ONLY admits ``ISOLATED``.

    Cross margin is forbidden by Spec §13.2 + Spec §30.2 ("必须 isolated
    margin" / "禁止 cross margin"). The enum deliberately does NOT
    declare a ``CROSS`` member so that even a typo cannot construct one.
    """

    ISOLATED = "isolated"


class OrderIntent(str, Enum):
    """Why this order is being placed.

    The intent decides three downstream behaviours:

      - ``is_new_open`` for the Risk Engine call (Phase 7 hard rule:
        protective / reduce-only paths must pass ``is_new_open=False``
        so the M3 / DATA_DEGRADED / REGIME / EXCHANGE_DISCONNECTED /
        REBASE_IN_PROGRESS gates do not block the exit).
      - ``reduce_only`` flag on the order itself (the Phase 9 default
        for every reduce-only intent is ``True``; the driver enforces
        this).
      - Whether ``OrderKind.MARKET`` is admissible. ``NEW_OPEN`` and
        ``SCALE_IN`` reject market orders ("默认禁止裸市价追单"); the
        protective / forced-exit / kill_all intents allow them so the
        operator can flatten under stress.
    """

    NEW_OPEN = "new_open"
    SCALE_IN = "scale_in"
    LOCK_PROFIT = "lock_profit"
    FORCED_EXIT = "forced_exit"
    DISTRIBUTION_EXIT = "distribution_exit"
    PROTECTIVE_CLOSE = "protective_close"
    KILL_ALL = "kill_all"
    STOP_ATTACH = "stop_attach"


# Intents that are NEW openings (Risk Engine receives is_new_open=True).
NEW_OPEN_INTENTS: frozenset[OrderIntent] = frozenset(
    {OrderIntent.NEW_OPEN, OrderIntent.SCALE_IN}
)

# Intents that are REDUCE-ONLY closing flows. Risk Engine receives
# is_new_open=False so M3 / DATA_DEGRADED / REGIME / EXCHANGE_DISCONNECTED
# / REBASE_IN_PROGRESS do not block the exit.
REDUCE_ONLY_INTENTS: frozenset[OrderIntent] = frozenset(
    {
        OrderIntent.LOCK_PROFIT,
        OrderIntent.FORCED_EXIT,
        OrderIntent.DISTRIBUTION_EXIT,
        OrderIntent.PROTECTIVE_CLOSE,
        OrderIntent.KILL_ALL,
        OrderIntent.STOP_ATTACH,
    }
)


def side_for_direction(direction: Direction, *, is_close: bool) -> OrderSide:
    """Resolve the :class:`OrderSide` for a given direction.

    LONG opens with BUY, closes with SELL. SHORT opens with SELL,
    closes with BUY. NONE raises - the caller must specify a direction
    before submitting.
    """
    if direction is Direction.LONG:
        return OrderSide.SELL if is_close else OrderSide.BUY
    if direction is Direction.SHORT:
        return OrderSide.BUY if is_close else OrderSide.SELL
    raise ValueError(
        f"Cannot resolve OrderSide for direction={direction.value!r}; "
        "supply Direction.LONG or Direction.SHORT."
    )


# ---------------------------------------------------------------------------
# OrderRequest
# ---------------------------------------------------------------------------
class OrderRequest(BaseModel):
    """Caller-supplied descriptor for one Phase 9 order.

    Frozen / Pydantic v2. Every field is JSON-safe so the Phase 8.5
    learning-ready data contract can serialise it without further
    work.

    The ``client_order_id`` is the stable identifier the Phase 9
    driver uses to key its sessions; callers MUST supply a
    deterministic value (a UUID is fine). Spec §13.2: every order
    must carry a ``client_order_id``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    client_order_id: str
    symbol: str
    side: OrderSide
    kind: OrderKind = OrderKind.LIMIT
    qty: float
    limit_price: float | None = None
    intent: OrderIntent = OrderIntent.NEW_OPEN
    direction: Direction = Direction.LONG
    time_in_force: TimeInForce = TimeInForce.GTC
    margin_mode: MarginMode = MarginMode.ISOLATED
    leverage: float = 1.0
    reduce_only: bool = False
    stop_price: float | None = None
    invalid_price: float | None = None
    max_slippage_pct: float = 0.005
    opportunity_id: str | None = None
    timestamp: int = Field(default_factory=now_ms)
    notes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("qty")
    @classmethod
    def _check_qty(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"OrderRequest.qty must be > 0; got {value}")
        return float(value)

    @field_validator("leverage")
    @classmethod
    def _check_leverage(cls, value: float) -> float:
        if value < 1.0:
            raise ValueError(
                f"OrderRequest.leverage must be >= 1.0; got {value}"
            )
        return float(value)

    @field_validator("margin_mode")
    @classmethod
    def _check_margin_mode(cls, value: MarginMode) -> MarginMode:
        if value is not MarginMode.ISOLATED:
            raise ValueError(
                "OrderRequest.margin_mode must be ISOLATED. "
                "Cross margin is forbidden in Phase 9 (Spec §13.2 + §30.2)."
            )
        return value

    @field_validator("max_slippage_pct")
    @classmethod
    def _check_slippage(cls, value: float) -> float:
        if not (0.0 < value <= 0.10):
            raise ValueError(
                "OrderRequest.max_slippage_pct must be in (0, 0.10]; "
                f"got {value}. Phase 9 forbids unbounded slippage."
            )
        return float(value)

    @property
    def is_new_open(self) -> bool:
        """Whether this order is opening / scaling INTO a position.

        Phase 7 hard rule: every protective / reduce-only / forced-exit
        path must call ``RiskEngine.evaluate(...)`` with
        ``is_new_open=False`` so the M3 / DATA_DEGRADED / REGIME /
        EXCHANGE_DISCONNECTED / REBASE_IN_PROGRESS gates do not trap
        the exit (Spec §27.2 protective-exit caveat). Phase 9 derives
        the flag from the intent vocabulary so callers cannot
        accidentally swap the polarity.
        """
        return self.intent in NEW_OPEN_INTENTS

    @property
    def is_reduce_only_intent(self) -> bool:
        """Whether the intent is a reduce-only / closing flow."""
        return self.intent in REDUCE_ONLY_INTENTS

    def to_payload(self) -> dict[str, Any]:
        """JSON-safe payload for ``ORDER_SENT`` events."""
        return {
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "kind": self.kind.value,
            "qty": float(self.qty),
            "limit_price": (
                float(self.limit_price) if self.limit_price is not None else None
            ),
            "intent": self.intent.value,
            "direction": self.direction.value,
            "time_in_force": self.time_in_force.value,
            "margin_mode": self.margin_mode.value,
            "leverage": float(self.leverage),
            "reduce_only": bool(self.reduce_only),
            "stop_price": (
                float(self.stop_price) if self.stop_price is not None else None
            ),
            "invalid_price": (
                float(self.invalid_price) if self.invalid_price is not None else None
            ),
            "max_slippage_pct": float(self.max_slippage_pct),
            "opportunity_id": self.opportunity_id,
            "is_new_open": self.is_new_open,
            "timestamp": int(self.timestamp),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# FillEvent / StopEvent
# ---------------------------------------------------------------------------
class FillEvent(BaseModel):
    """One fill applied to an :class:`ExecutionSession`.

    Phase 9 paper-mode produces synthetic FillEvents at a deterministic
    price; tests construct FillEvents directly to drive the lifecycle.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    fill_qty: float
    fill_price: float
    fill_id: str
    is_maker: bool = False
    fee: float = 0.0
    fee_asset: str = "USDT"
    timestamp: int = Field(default_factory=now_ms)

    @field_validator("fill_qty")
    @classmethod
    def _check_fill_qty(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"FillEvent.fill_qty must be > 0; got {value}")
        return float(value)

    @field_validator("fill_price")
    @classmethod
    def _check_fill_price(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"FillEvent.fill_price must be > 0; got {value}")
        return float(value)


class StopEvent(BaseModel):
    """A stop-loss attachment descriptor.

    Phase 9 stops are ALWAYS reduce-only; the driver refuses any stop
    where ``reduce_only=False`` (Spec §30.2 "止盈止损必须 reduce-only").
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    stop_order_id: str
    stop_price: float
    side: OrderSide
    qty: float
    reduce_only: bool = True
    timestamp: int = Field(default_factory=now_ms)

    @field_validator("reduce_only")
    @classmethod
    def _enforce_reduce_only(cls, value: bool) -> bool:
        if not value:
            raise ValueError(
                "StopEvent.reduce_only MUST be True. Phase 9 / Spec §30.2: "
                "every stop attachment must be reduce-only."
            )
        return True

    @field_validator("stop_price")
    @classmethod
    def _check_stop_price(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"StopEvent.stop_price must be > 0; got {value}")
        return float(value)

    @field_validator("qty")
    @classmethod
    def _check_qty(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(f"StopEvent.qty must be > 0; got {value}")
        return float(value)


# ---------------------------------------------------------------------------
# ExecutionSession (mutable, per-order state)
# ---------------------------------------------------------------------------
@dataclass
class TransitionRecord:
    """One row in the per-session transition history."""

    from_state: ExecutionState
    to_state: ExecutionState
    timestamp: int
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class ExecutionSession:
    """Per-order lifecycle state advanced by the Phase 9 driver.

    The session is the **single source of truth** for one order. Every
    Phase 9 event written about this order carries the
    ``client_order_id`` from here.
    """

    request: OrderRequest
    state: ExecutionState = ExecutionState.IDLE
    exchange_order_id: str | None = None
    stop_order_id: str | None = None
    position_id: str | None = None
    filled_qty: float = 0.0
    avg_fill_price: float | None = None
    realized_pnl: float = 0.0
    history: list[TransitionRecord] = field(default_factory=list)
    last_risk_decision_id: str | None = None
    learning_context_payload: dict[str, Any] | None = None
    incident_id: str | None = None
    in_protection_mode: bool = False
    rejection_reasons: tuple[str, ...] = field(default_factory=tuple)

    # ------------------------------------------------------------------
    @property
    def client_order_id(self) -> str:
        return self.request.client_order_id

    @property
    def symbol(self) -> str:
        return self.request.symbol

    @property
    def remaining_qty(self) -> float:
        return max(0.0, self.request.qty - self.filled_qty)

    @property
    def is_terminal(self) -> bool:
        return self.state in {
            ExecutionState.IDLE,
            ExecutionState.POSITION_CLOSED,
        }

    @property
    def is_protected(self) -> bool:
        return self.in_protection_mode or self.state is ExecutionState.ERROR_PROTECTION


@dataclass(frozen=True)
class ExecutionResult:
    """Return value of :meth:`ExecutionFSMDriver.submit_order`."""

    accepted: bool
    session: ExecutionSession
    reasons: tuple[str, ...] = field(default_factory=tuple)


__all__ = [
    "OrderKind",
    "OrderSide",
    "TimeInForce",
    "MarginMode",
    "OrderIntent",
    "NEW_OPEN_INTENTS",
    "REDUCE_ONLY_INTENTS",
    "side_for_direction",
    "OrderRequest",
    "FillEvent",
    "StopEvent",
    "TransitionRecord",
    "ExecutionSession",
    "ExecutionResult",
]
