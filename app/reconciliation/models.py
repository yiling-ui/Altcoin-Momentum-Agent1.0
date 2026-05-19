"""Phase 9 Reconciliation data models (Issue #9, Spec §31).

The reconciler operates purely on value objects passed in by the
caller. This module ships the value objects + helpers that build a
``LocalSnapshot`` / ``RemoteSnapshot`` from the in-process paper
ledger.

Phase 9 boundary
----------------

Nothing in this module:

  - imports an exchange SDK / HTTP / WebSocket / LLM client
  - opens a network socket
  - reads ``os.environ`` for credentials
  - subclasses :class:`ExchangeClientBase`
  - defines ``create_order``, ``cancel_order``, ``set_leverage``,
    or ``set_margin_mode``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.clock import now_ms
from app.core.enums import ExchangeConnectionState
from app.execution.paper_ledger import PaperLedger


# ---------------------------------------------------------------------------
# Mismatch vocabulary
# ---------------------------------------------------------------------------
class MismatchType(str, Enum):
    """The five reconciliation classes mandated by the Issue brief.

    Each value matches the Spec §31.2 / Issue #9 wording:

      - ``ORDER_MISMATCH``     local order set ≠ remote order set
      - ``POSITION_MISMATCH``  local position set ≠ remote position set
      - ``STOP_MISMATCH``      local stop set ≠ remote stop set
      - ``EQUITY_DRIFT``       local equity ≠ remote equity above tolerance
      - ``WS_REST_CONFLICT``   WebSocket and REST disagree on link state

    Plus three sub-types Issue #9 hard rules promote to P0:

      - ``GHOST_POSITION``     local empty + remote has a position
      - ``MISSING_REMOTE_POSITION``  local has a position + remote empty
      - ``UNATTACHED_STOP``    local thinks stop is attached + remote has no stop

    These sub-types are children of the parent ``POSITION_MISMATCH``
    / ``STOP_MISMATCH`` checks; the reconciler emits them in addition
    to (not instead of) the parent type so the parent counts also
    fire.
    """

    ORDER_MISMATCH = "order_mismatch"
    POSITION_MISMATCH = "position_mismatch"
    STOP_MISMATCH = "stop_mismatch"
    EQUITY_DRIFT = "equity_drift"
    WS_REST_CONFLICT = "ws_rest_conflict"
    GHOST_POSITION = "ghost_position"
    MISSING_REMOTE_POSITION = "missing_remote_position"
    UNATTACHED_STOP = "unattached_stop"


class MismatchSeverity(str, Enum):
    """How severe a mismatch is.

    ``P0`` is a "could lose money right now" condition - ghost position,
    unattached stop, kill_all failed-to-flatten. ``P1`` is "trade flow
    is unsafe but not actively losing money" - equity drift, order set
    mismatch on a small qty. ``P2`` is informational only.
    """

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


# Mapping from mismatch type to its **canonical** severity. The
# reconciler may upgrade a P1 to P0 when the affected symbol carries a
# known position that's now uncovered, but never downgrades.
_DEFAULT_SEVERITY: dict[MismatchType, MismatchSeverity] = {
    MismatchType.ORDER_MISMATCH: MismatchSeverity.P1,
    MismatchType.POSITION_MISMATCH: MismatchSeverity.P0,
    MismatchType.STOP_MISMATCH: MismatchSeverity.P0,
    MismatchType.EQUITY_DRIFT: MismatchSeverity.P1,
    MismatchType.WS_REST_CONFLICT: MismatchSeverity.P1,
    MismatchType.GHOST_POSITION: MismatchSeverity.P0,
    MismatchType.MISSING_REMOTE_POSITION: MismatchSeverity.P0,
    MismatchType.UNATTACHED_STOP: MismatchSeverity.P0,
}


def default_severity_for(mismatch_type: MismatchType) -> MismatchSeverity:
    return _DEFAULT_SEVERITY[mismatch_type]


# ---------------------------------------------------------------------------
# Snapshot value objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OrderView:
    """One open order as seen by either side of the reconciliation.

    Phase 9 keeps the schema deliberately narrow: order_id (canonical
    identifier the reconciler matches on - in paper mode this is the
    ``client_order_id``), symbol, side, qty, filled_qty.
    """

    order_id: str
    symbol: str
    side: str  # "buy" | "sell"
    qty: float
    filled_qty: float = 0.0
    intent: str | None = None
    reduce_only: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": float(self.qty),
            "filled_qty": float(self.filled_qty),
            "intent": self.intent,
            "reduce_only": bool(self.reduce_only),
        }


@dataclass(frozen=True)
class PositionView:
    """One open position as seen by either side."""

    position_id: str
    symbol: str
    direction: str  # "long" | "short"
    qty: float
    entry_price: float
    stop_price: float | None = None
    stop_confirmed: bool = False
    margin_mode: str = "isolated"
    leverage: float = 1.0

    def to_payload(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "qty": float(self.qty),
            "entry_price": float(self.entry_price),
            "stop_price": (
                float(self.stop_price) if self.stop_price is not None else None
            ),
            "stop_confirmed": bool(self.stop_confirmed),
            "margin_mode": self.margin_mode,
            "leverage": float(self.leverage),
        }


@dataclass(frozen=True)
class StopView:
    """One open reduce-only stop order as seen by either side."""

    stop_order_id: str
    position_id: str
    symbol: str
    qty: float
    stop_price: float
    side: str  # "buy" | "sell"
    reduce_only: bool = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "stop_order_id": self.stop_order_id,
            "position_id": self.position_id,
            "symbol": self.symbol,
            "qty": float(self.qty),
            "stop_price": float(self.stop_price),
            "side": self.side,
            "reduce_only": bool(self.reduce_only),
        }


@dataclass(frozen=True)
class EquitySnapshot:
    """Equity figure used for the equity-drift check."""

    total_equity: float
    timestamp: int = field(default_factory=now_ms)


@dataclass(frozen=True)
class LinkHealth:
    """The two link states the reconciler compares against each other."""

    websocket_state: ExchangeConnectionState
    rest_state: ExchangeConnectionState
    timestamp: int = field(default_factory=now_ms)

    @property
    def conflicts(self) -> bool:
        """True when WS and REST disagree on the trustworthy view.

        Phase 9 treats CONNECTED on one side and not-CONNECTED on the
        other as a conflict that pauses new opens. Two not-CONNECTED
        states are also flagged (the link is fully down).
        """
        ws_ok = self.websocket_state is ExchangeConnectionState.CONNECTED
        rest_ok = self.rest_state is ExchangeConnectionState.CONNECTED
        if ws_ok and rest_ok:
            return False
        return ws_ok != rest_ok or (not ws_ok and not rest_ok)


@dataclass(frozen=True)
class LocalSnapshot:
    """The local view of orders / positions / stops / equity / link.

    Built from the paper ledger + the in-process FSM driver state in
    Phase 9; tests can construct one directly.
    """

    orders: tuple[OrderView, ...] = field(default_factory=tuple)
    positions: tuple[PositionView, ...] = field(default_factory=tuple)
    stops: tuple[StopView, ...] = field(default_factory=tuple)
    equity: EquitySnapshot | None = None
    link: LinkHealth | None = None


@dataclass(frozen=True)
class RemoteSnapshot:
    """The exchange's view of orders / positions / stops / equity / link.

    In Phase 9 paper mode the boot drill uses a snapshot built from the
    same paper ledger so the boot reconciliation is always clean.
    Tests can construct divergent remote snapshots to exercise the
    mismatch paths.
    """

    orders: tuple[OrderView, ...] = field(default_factory=tuple)
    positions: tuple[PositionView, ...] = field(default_factory=tuple)
    stops: tuple[StopView, ...] = field(default_factory=tuple)
    equity: EquitySnapshot | None = None
    link: LinkHealth | None = None


# ---------------------------------------------------------------------------
# Mismatch + decision
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Mismatch:
    """One concrete mismatch the reconciler found."""

    mismatch_type: MismatchType
    severity: MismatchSeverity
    symbol: str | None
    summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "mismatch_type": self.mismatch_type.value,
            "severity": self.severity.value,
            "symbol": self.symbol,
            "summary": self.summary,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class ReconciliationDecision:
    """Result of one reconciliation pass.

    ``new_opens_paused=True`` means the operator should not open any
    new positions until the mismatches are resolved. The Phase 9
    reduce-only / protective-exit paths remain allowed (Spec §31.3).
    """

    started_at: int
    finished_at: int
    mismatches: tuple[Mismatch, ...] = field(default_factory=tuple)
    incidents_opened: tuple[str, ...] = field(default_factory=tuple)
    new_opens_paused: bool = False
    protection_mode_entered: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def matched(self) -> bool:
        return not self.mismatches

    @property
    def severities(self) -> tuple[MismatchSeverity, ...]:
        return tuple(m.severity for m in self.mismatches)

    @property
    def has_p0(self) -> bool:
        return any(s is MismatchSeverity.P0 for s in self.severities)


# ---------------------------------------------------------------------------
# Helpers - build snapshots from a paper ledger
# ---------------------------------------------------------------------------
def local_snapshot_from_paper_ledger(
    ledger: PaperLedger,
    *,
    websocket_state: ExchangeConnectionState | None = None,
    rest_state: ExchangeConnectionState | None = None,
) -> LocalSnapshot:
    """Build a :class:`LocalSnapshot` from the paper ledger.

    Phase 9 paper mode keeps the local view in this object; the remote
    view (from the exchange's READ surfaces) is built separately. The
    boot drill happens to use the same source for both, which is the
    desired behaviour: paper-mode reconciliation should always match.
    """
    orders = tuple(
        OrderView(
            order_id=o.client_order_id,
            symbol=o.symbol,
            side=o.side.value,
            qty=float(o.qty),
            filled_qty=float(o.filled_qty),
            intent=o.intent,
            reduce_only=bool(o.reduce_only),
        )
        for o in ledger.open_orders
    )
    positions = tuple(
        PositionView(
            position_id=p.position_id,
            symbol=p.symbol,
            direction=p.direction,
            qty=float(p.qty),
            entry_price=float(p.entry_price),
            stop_price=p.stop_price,
            stop_confirmed=bool(p.stop_confirmed),
            margin_mode=p.margin_mode,
            leverage=float(p.leverage),
        )
        for p in ledger.open_positions
    )
    stops = tuple(
        StopView(
            stop_order_id=s.stop_order_id,
            position_id=s.position_id,
            symbol=s.symbol,
            qty=float(s.qty),
            stop_price=float(s.stop_price),
            side=s.side.value,
            reduce_only=bool(s.reduce_only),
        )
        for s in ledger.open_stops
    )
    equity = EquitySnapshot(
        total_equity=float(ledger.equity.total_equity),
        timestamp=int(ledger.equity.timestamp),
    )
    link = None
    if websocket_state is not None or rest_state is not None:
        link = LinkHealth(
            websocket_state=websocket_state or ExchangeConnectionState.UNINITIALISED,
            rest_state=rest_state or ExchangeConnectionState.UNINITIALISED,
        )
    return LocalSnapshot(
        orders=orders,
        positions=positions,
        stops=stops,
        equity=equity,
        link=link,
    )


def remote_snapshot_from_paper_ledger(
    ledger: PaperLedger,
    *,
    websocket_state: ExchangeConnectionState | None = None,
    rest_state: ExchangeConnectionState | None = None,
) -> RemoteSnapshot:
    """Build a :class:`RemoteSnapshot` from the same paper ledger.

    In paper mode there is no separate "exchange" - the local ledger is
    the system of record. The boot drill uses this helper to assemble
    a remote snapshot identical to the local one so the reconciliation
    pass writes a clean ``RECONCILIATION_RESOLVED`` event.

    Tests that want to exercise the mismatch paths build a divergent
    :class:`RemoteSnapshot` directly instead of calling this helper.
    """
    local = local_snapshot_from_paper_ledger(
        ledger,
        websocket_state=websocket_state,
        rest_state=rest_state,
    )
    return RemoteSnapshot(
        orders=local.orders,
        positions=local.positions,
        stops=local.stops,
        equity=local.equity,
        link=local.link,
    )


__all__ = [
    "MismatchType",
    "MismatchSeverity",
    "default_severity_for",
    "OrderView",
    "PositionView",
    "StopView",
    "EquitySnapshot",
    "LinkHealth",
    "LocalSnapshot",
    "RemoteSnapshot",
    "Mismatch",
    "ReconciliationDecision",
    "local_snapshot_from_paper_ledger",
    "remote_snapshot_from_paper_ledger",
]
