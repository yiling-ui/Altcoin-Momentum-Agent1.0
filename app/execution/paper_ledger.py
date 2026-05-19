"""Phase 9 in-memory paper ledger (Issue #9).

Phase 9 runs the Execution FSM driver in **paper / mock mode** by
default. There is NO real exchange call, NO real ``create_order``,
NO real ``cancel_order``, NO real ``set_leverage``, NO real
``set_margin_mode``. The four ``ExchangeClientBase`` write surfaces
continue to raise :class:`SafeModeViolation`; Phase 9 must NEVER
override them.

Instead, the driver writes the same shape of state into this
in-process :class:`PaperLedger`. The ledger is a transient,
per-process store; nothing here touches the filesystem or the
network. ``trades.db`` and ``positions.db`` remain unwritten in
Phase 9 - those become writable when a real exchange adapter lands
behind the Risk Engine in a future PR.

The :class:`Reconciliation <app.reconciliation.reconciler.Reconciler>`
loop reads two snapshots: a *local* one constructed from this ledger
and a *remote* one constructed from the exchange's view (in paper
mode the same ledger; in tests, hand-crafted divergent snapshots).

Phase 9 boundary
----------------

Nothing in this module:

  - imports an exchange SDK or HTTP / WebSocket library
  - opens a network socket
  - reads ``os.environ``
  - calls an LLM
  - subclasses :class:`ExchangeClientBase`
  - defines ``create_order``, ``cancel_order``, ``set_leverage``, or
    ``set_margin_mode``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.clock import now_ms
from app.execution.models import OrderRequest, OrderSide


@dataclass
class PaperOrder:
    """One open order tracked by the paper ledger."""

    client_order_id: str
    exchange_order_id: str
    symbol: str
    side: OrderSide
    qty: float
    filled_qty: float
    limit_price: float | None
    intent: str
    reduce_only: bool
    opportunity_id: str | None
    timestamp: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "client_order_id": self.client_order_id,
            "exchange_order_id": self.exchange_order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "qty": float(self.qty),
            "filled_qty": float(self.filled_qty),
            "limit_price": (
                float(self.limit_price) if self.limit_price is not None else None
            ),
            "intent": self.intent,
            "reduce_only": bool(self.reduce_only),
            "opportunity_id": self.opportunity_id,
            "timestamp": int(self.timestamp),
        }


@dataclass
class PaperStop:
    """One open reduce-only stop tracked by the paper ledger."""

    stop_order_id: str
    position_id: str
    symbol: str
    side: OrderSide
    qty: float
    stop_price: float
    reduce_only: bool
    timestamp: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "stop_order_id": self.stop_order_id,
            "position_id": self.position_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "qty": float(self.qty),
            "stop_price": float(self.stop_price),
            "reduce_only": bool(self.reduce_only),
            "timestamp": int(self.timestamp),
        }


@dataclass
class PaperPosition:
    """One open paper position."""

    position_id: str
    symbol: str
    direction: str  # "long" | "short"
    qty: float
    entry_price: float
    margin_mode: str = "isolated"
    leverage: float = 1.0
    stop_price: float | None = None
    stop_confirmed: bool = False
    opportunity_id: str | None = None
    opened_at: int = field(default_factory=now_ms)

    def to_payload(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "qty": float(self.qty),
            "entry_price": float(self.entry_price),
            "margin_mode": self.margin_mode,
            "leverage": float(self.leverage),
            "stop_price": (
                float(self.stop_price) if self.stop_price is not None else None
            ),
            "stop_confirmed": bool(self.stop_confirmed),
            "opportunity_id": self.opportunity_id,
            "opened_at": int(self.opened_at),
        }


@dataclass
class PaperEquity:
    """Aggregate equity snapshot tracked by the paper ledger.

    Phase 9 keeps this minimal; Issue #10 will extend with realised /
    unrealised PnL. The reconciliation loop only needs a single number
    to compare against the exchange snapshot.
    """

    total_equity: float
    timestamp: int = field(default_factory=now_ms)


class PaperLedger:
    """In-memory paper ledger.

    Holds three dictionaries plus an equity snapshot. All mutations
    are explicit method calls; the ledger never side-effects (no
    auto-fill, no auto-close).

    Counters expose how many operations have been performed since
    construction so tests / monitoring can verify the wiring without
    inspecting private state.
    """

    def __init__(self, *, initial_equity: float = 0.0) -> None:
        self._open_orders: dict[str, PaperOrder] = {}
        self._open_stops: dict[str, PaperStop] = {}
        self._positions: dict[str, PaperPosition] = {}
        self._equity = PaperEquity(total_equity=float(initial_equity))
        self._orders_recorded: int = 0
        self._stops_recorded: int = 0
        self._positions_opened: int = 0
        self._positions_closed: int = 0

    # ------------------------------------------------------------------
    # Counters / observability
    # ------------------------------------------------------------------
    @property
    def orders_recorded(self) -> int:
        return self._orders_recorded

    @property
    def stops_recorded(self) -> int:
        return self._stops_recorded

    @property
    def positions_opened(self) -> int:
        return self._positions_opened

    @property
    def positions_closed(self) -> int:
        return self._positions_closed

    @property
    def open_orders(self) -> tuple[PaperOrder, ...]:
        return tuple(self._open_orders.values())

    @property
    def open_stops(self) -> tuple[PaperStop, ...]:
        return tuple(self._open_stops.values())

    @property
    def open_positions(self) -> tuple[PaperPosition, ...]:
        return tuple(self._positions.values())

    @property
    def equity(self) -> PaperEquity:
        return self._equity

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def record_order(
        self,
        *,
        request: OrderRequest,
        exchange_order_id: str,
    ) -> PaperOrder:
        """Record an open order keyed by ``client_order_id``."""
        order = PaperOrder(
            client_order_id=request.client_order_id,
            exchange_order_id=exchange_order_id,
            symbol=request.symbol,
            side=request.side,
            qty=float(request.qty),
            filled_qty=0.0,
            limit_price=request.limit_price,
            intent=request.intent.value,
            reduce_only=bool(request.reduce_only),
            opportunity_id=request.opportunity_id,
            timestamp=int(request.timestamp),
        )
        self._open_orders[request.client_order_id] = order
        self._orders_recorded += 1
        return order

    def get_order(self, client_order_id: str) -> PaperOrder | None:
        return self._open_orders.get(client_order_id)

    def apply_partial_fill(
        self,
        *,
        client_order_id: str,
        fill_qty: float,
    ) -> PaperOrder:
        order = self._open_orders.get(client_order_id)
        if order is None:
            raise KeyError(
                f"PaperLedger.apply_partial_fill: unknown "
                f"client_order_id={client_order_id!r}"
            )
        order.filled_qty = min(order.qty, order.filled_qty + float(fill_qty))
        return order

    def close_order(self, client_order_id: str) -> PaperOrder | None:
        return self._open_orders.pop(client_order_id, None)

    # ------------------------------------------------------------------
    # Stops
    # ------------------------------------------------------------------
    def record_stop(self, stop: PaperStop) -> PaperStop:
        self._open_stops[stop.stop_order_id] = stop
        self._stops_recorded += 1
        return stop

    def get_stop(self, stop_order_id: str) -> PaperStop | None:
        return self._open_stops.get(stop_order_id)

    def remove_stop(self, stop_order_id: str) -> PaperStop | None:
        return self._open_stops.pop(stop_order_id, None)

    def stops_for_position(self, position_id: str) -> tuple[PaperStop, ...]:
        return tuple(
            s for s in self._open_stops.values() if s.position_id == position_id
        )

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------
    def open_position(self, position: PaperPosition) -> PaperPosition:
        self._positions[position.position_id] = position
        self._positions_opened += 1
        return position

    def get_position(self, position_id: str) -> PaperPosition | None:
        return self._positions.get(position_id)

    def position_for_symbol(self, symbol: str) -> PaperPosition | None:
        for pos in self._positions.values():
            if pos.symbol == symbol:
                return pos
        return None

    def confirm_position_stop(
        self,
        *,
        position_id: str,
        stop_price: float,
    ) -> PaperPosition:
        pos = self._positions.get(position_id)
        if pos is None:
            raise KeyError(
                f"PaperLedger.confirm_position_stop: unknown "
                f"position_id={position_id!r}"
            )
        pos.stop_price = float(stop_price)
        pos.stop_confirmed = True
        return pos

    def close_position(self, position_id: str) -> PaperPosition | None:
        pos = self._positions.pop(position_id, None)
        if pos is not None:
            self._positions_closed += 1
            # Remove any stops attached to this position so the
            # reconciliation snapshot doesn't dangle.
            for stop_id in list(self._open_stops.keys()):
                if self._open_stops[stop_id].position_id == position_id:
                    self._open_stops.pop(stop_id, None)
        return pos

    # ------------------------------------------------------------------
    # Equity
    # ------------------------------------------------------------------
    def set_equity(self, total_equity: float, *, timestamp: int | None = None) -> None:
        self._equity = PaperEquity(
            total_equity=float(total_equity),
            timestamp=int(timestamp) if timestamp is not None else now_ms(),
        )


__all__ = [
    "PaperOrder",
    "PaperStop",
    "PaperPosition",
    "PaperEquity",
    "PaperLedger",
]
