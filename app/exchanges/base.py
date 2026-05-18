"""Abstract Exchange Gateway (Phase 3 - Issue #3).

Spec references:
    §13   Exchange Gateway 交易所接入层
    §13.2 Mandatory rules (no real orders without RiskEngine + ExecutionFSM)
    §13.3 Data reliability tiers A/B/C/D
    §14   Market Data Buffer health behaviour
    §31   Reconciliation (uses connection state from this module)

Phase 3 contract
----------------
1. **Read-only**. Only the methods listed in `READ_ONLY_METHODS` are
   abstract. The four write surfaces - `create_order`, `cancel_order`,
   `set_leverage`, `set_margin_mode` - are concrete on the base class
   and **always raise `SafeModeViolation`**. Subclasses (BinanceClient,
   MockExchangeClient, future ones) inherit that refusal automatically.
2. **No real network from this file**. Subclasses are responsible for
   making the read-only calls real; Phase 3 explicitly forbids that
   too, so `BinanceClient` raises `NotImplementedError` and
   `MockExchangeClient` returns deterministic in-memory data.
3. **Connection state is observable**. Every client owns an
   `ExchangeHealth` object; consumers query `client.health` to drive
   No-Trade Gate decisions and `DATA_UNRELIABLE` events.
4. **Audit-friendly**. Every health transition emits an
   EXCHANGE_CONNECTED / EXCHANGE_DISCONNECTED / EXCHANGE_DEGRADED /
   DATA_UNRELIABLE event when an `EventRepository` is attached. This is
   how the Phase 2 event-sourcing substrate observes Phase 3 behaviour.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.core.clock import now_ms
from app.core.enums import DataReliability, ExchangeConnectionState
from app.core.errors import ExchangeConnectionError, SafeModeViolation
from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.exchanges.models import (
    AccountSnapshot,
    ExchangeSymbol,
    FundingRate,
    OpenInterest,
    OrderBook,
    RecentTrade,
)

# Read-only methods that every concrete client must implement. Tests use
# this tuple to assert the abstract contract; the BinanceClient skeleton
# uses it to drive its NotImplementedError raises.
READ_ONLY_METHODS: tuple[str, ...] = (
    "get_symbols",
    "get_orderbook",
    "get_recent_trades",
    "get_funding_rate",
    "get_open_interest",
    "get_account_snapshot",
)

# Write surfaces that MUST raise SafeModeViolation in Phase 3. The base
# class implements them; subclasses inherit the refusal.
WRITE_SURFACE_METHODS: tuple[str, ...] = (
    "create_order",
    "cancel_order",
    "set_leverage",
    "set_margin_mode",
)


@dataclass
class ExchangeHealth:
    """Observable health snapshot for an `ExchangeClientBase`.

    The state transitions are deliberately small: `set_state` is the
    only write entry point. The state has the consequences described in
    Spec §14.2 and §31:

      CONNECTED      -> data is trustworthy at the WS tier (A)
      DEGRADED       -> only REST tier B is trustworthy
      RECONNECTING   -> data is stale; do not open new positions
      DISCONNECTED   -> no data is trustworthy
      UNINITIALISED  -> client has never been started

    Use `is_data_trustworthy()` instead of comparing the state directly
    so callers don't accidentally gate on the wrong predicate.
    """

    state: ExchangeConnectionState = ExchangeConnectionState.UNINITIALISED
    last_change_ts: int = field(default_factory=now_ms)
    reason: str = "boot"
    # Counters useful for monitoring (Spec §36).
    disconnect_count: int = 0
    reconnect_count: int = 0
    degraded_count: int = 0

    def set_state(self, new_state: ExchangeConnectionState, *, reason: str) -> bool:
        """Transition to a new state. Returns True if the state changed."""
        if new_state is self.state:
            # Even no-op state changes update the reason so consumers can
            # see why a heartbeat fired without churning counters.
            self.reason = reason
            return False
        if new_state is ExchangeConnectionState.DISCONNECTED:
            self.disconnect_count += 1
        elif new_state is ExchangeConnectionState.RECONNECTING:
            self.reconnect_count += 1
        elif new_state is ExchangeConnectionState.DEGRADED:
            self.degraded_count += 1
        self.state = new_state
        self.last_change_ts = now_ms()
        self.reason = reason
        return True

    def is_data_trustworthy(self) -> bool:
        """Spec §14.2: only CONNECTED counts as trustworthy."""
        return self.state.is_trustworthy

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "last_change_ts": self.last_change_ts,
            "reason": self.reason,
            "disconnect_count": self.disconnect_count,
            "reconnect_count": self.reconnect_count,
            "degraded_count": self.degraded_count,
        }


class WebSocketManager:
    """Phase 3 WebSocket lifecycle skeleton.

    Issue #3 mandates a "WebSocket management skeleton". Phase 3 ships
    state-tracking and disconnect handling only - no real socket is ever
    opened.

    Phase 4 (Issue #4 - Market Data Buffer) drives the buffer from
    `MockExchangeClient` / fixture data by default. Any public read-only
    WS adapter that Phase 4 adds must be **opt-in** (off by default),
    must not require an API key, must not expose any write surface,
    and must not auto-connect to the real exchange. The
    authenticated user-data stream needed for order events
    (Issue #9 - Reconciliation) is forbidden until the limited-live
    phase.

    The manager exists so Phase 4 has a stable surface to extend rather
    than a constructor it must invent. Until then, every subscribe /
    unsubscribe is a recorded intent that influences the
    `ExchangeHealth` exposed by the parent client.
    """

    def __init__(
        self,
        *,
        owner_name: str = "WebSocketManager",
        event_repo: EventRepository | None = None,
    ) -> None:
        self.owner_name = owner_name
        self._event_repo = event_repo
        self._subscriptions: set[str] = set()
        self._connected: bool = False
        self._disconnect_count: int = 0
        self._connect_count: int = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def subscriptions(self) -> frozenset[str]:
        return frozenset(self._subscriptions)

    @property
    def disconnect_count(self) -> int:
        return self._disconnect_count

    @property
    def connect_count(self) -> int:
        return self._connect_count

    def connect(self) -> None:
        """Mark the WS as connected. Phase 3 does NOT open a real socket."""
        if self._connected:
            return
        self._connected = True
        self._connect_count += 1
        logger.debug("[{}] WS connect (skeleton)", self.owner_name)

    def disconnect(self, *, reason: str = "manual") -> None:
        """Mark the WS as disconnected and emit a DATA_UNRELIABLE event."""
        if not self._connected:
            return
        self._connected = False
        self._disconnect_count += 1
        logger.warning(
            "[{}] WS disconnect (skeleton): reason={}", self.owner_name, reason
        )
        self._emit_data_unreliable(reason=reason)

    def subscribe(self, stream: str) -> None:
        self._subscriptions.add(stream)

    def unsubscribe(self, stream: str) -> None:
        self._subscriptions.discard(stream)

    def _emit_data_unreliable(self, *, reason: str) -> None:
        if self._event_repo is None:
            return
        self._event_repo.append(
            Event(
                event_type=EventType.DATA_UNRELIABLE,
                source_module=self.owner_name,
                payload={
                    "reason": reason,
                    "subscriptions": sorted(self._subscriptions),
                    "disconnect_count": self._disconnect_count,
                },
            )
        )


class ExchangeClientBase(ABC):
    """Abstract Exchange Gateway client.

    Subclasses must implement the read-only methods listed in
    `READ_ONLY_METHODS`. The four write surfaces are *concrete on this
    class* and always raise `SafeModeViolation` - that is the Phase 3
    contract, and the only way to add a real implementation is to
    override the method explicitly in a Phase 9+ subclass AND clear the
    Phase 1 safety lock. Tests assert both halves of that.
    """

    #: Exchange name, e.g. ``"binance"``. Subclasses override.
    name: str = "exchange"

    def __init__(
        self,
        *,
        event_repo: EventRepository | None = None,
        ws_manager: WebSocketManager | None = None,
    ) -> None:
        self._event_repo = event_repo
        self.health = ExchangeHealth()
        # Phase 3 hard rule: any concrete client refuses live writes.
        # We expose this as an attribute so test fixtures and the boot
        # path can introspect it without instantiating private state.
        self._live_orders_enabled: bool = False
        self.ws = ws_manager or WebSocketManager(
            owner_name=f"{self.name}.ws",
            event_repo=event_repo,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start the client. Phase 3 only flips state to CONNECTED."""
        self.ws.connect()
        self._mark_connected(reason="start")

    def stop(self, *, reason: str = "stop") -> None:
        """Stop the client. Phase 3 only flips state to DISCONNECTED."""
        self.ws.disconnect(reason=reason)
        self._mark_disconnected(reason=reason)

    # ------------------------------------------------------------------
    # Health transitions
    # ------------------------------------------------------------------
    def _mark_connected(self, *, reason: str) -> None:
        if self.health.set_state(
            ExchangeConnectionState.CONNECTED, reason=reason
        ):
            self._emit(EventType.EXCHANGE_CONNECTED, reason=reason)

    def _mark_disconnected(self, *, reason: str) -> None:
        if self.health.set_state(
            ExchangeConnectionState.DISCONNECTED, reason=reason
        ):
            self._emit(EventType.EXCHANGE_DISCONNECTED, reason=reason)

    def _mark_degraded(self, *, reason: str) -> None:
        if self.health.set_state(
            ExchangeConnectionState.DEGRADED, reason=reason
        ):
            self._emit(EventType.EXCHANGE_DEGRADED, reason=reason)

    def _mark_reconnecting(self, *, reason: str) -> None:
        self.health.set_state(
            ExchangeConnectionState.RECONNECTING, reason=reason
        )

    def _emit(self, event_type: EventType, *, reason: str) -> None:
        if self._event_repo is None:
            return
        self._event_repo.append(
            Event(
                event_type=event_type,
                source_module=f"exchange.{self.name}",
                payload={
                    "reason": reason,
                    "health": self.health.to_dict(),
                },
            )
        )

    # ------------------------------------------------------------------
    # Helpers used by both base and subclasses
    # ------------------------------------------------------------------
    def _require_trustworthy(self, *, surface: str) -> None:
        """Refuse a read call when the connection is untrustworthy.

        Spec §14.2 + §31: data must not be returned to upstream while
        the link is anything other than CONNECTED. Returning stale data
        would break the No-Trade Gate (Issue #7) and the Reconciliation
        loop (Issue #9).
        """
        if not self.health.is_data_trustworthy():
            raise ExchangeConnectionError(
                f"{self.name}.{surface}() refused: connection state is "
                f"{self.health.state.value} (reason={self.health.reason})"
            )

    # ------------------------------------------------------------------
    # Read-only abstract methods (Issue #3 mandate)
    # ------------------------------------------------------------------
    @abstractmethod
    def get_symbols(self) -> list[ExchangeSymbol]:
        """Return tradable symbols. Tier B (REST)."""

    @abstractmethod
    def get_orderbook(self, symbol: str, *, depth: int = 20) -> OrderBook:
        """Return a snapshot of the order book.

        Default tier is A: a WS-maintained order book reconstructed from
        the depth diff stream is the canonical Phase 4+ source and counts
        as raw exchange data. A REST-only snapshot taken as a fallback
        when the WS link is degraded should be tagged tier B by the
        adapter that produced it; the model accepts either tier.
        """

    @abstractmethod
    def get_recent_trades(self, symbol: str, *, limit: int = 100) -> list[RecentTrade]:
        """Return recent trades. Tier A when streamed, tier B when REST."""

    @abstractmethod
    def get_funding_rate(self, symbol: str) -> FundingRate:
        """Return the latest funding rate. Tier B."""

    @abstractmethod
    def get_open_interest(self, symbol: str) -> OpenInterest:
        """Return the latest open interest. Tier B."""

    @abstractmethod
    def get_account_snapshot(self) -> AccountSnapshot:
        """Return a read-only account snapshot. Tier B."""

    # ------------------------------------------------------------------
    # Write surfaces - ALWAYS REFUSED IN PHASE 3
    #
    # These are concrete and final. They DO NOT have an @abstractmethod
    # marker and they DO NOT call super(). A subclass may attempt to
    # override them, but the Phase 1 safety lock + the Risk Engine's
    # `live_trading_required=True` rejection will still block any real
    # order. We keep these here so a Python attribute lookup of e.g.
    # `MockExchangeClient.create_order` returns this refusal even when
    # the subclass forgets to override.
    # ------------------------------------------------------------------
    def create_order(self, *args: Any, **kwargs: Any) -> Any:
        raise SafeModeViolation(
            "create_order is forbidden in Phase 3 (Exchange Gateway is "
            "read-only). The Phase 1 safety lock requires "
            "live_trading_enabled=False; this call would attempt a real "
            "order. Real order placement lands in Issue #9 with the "
            "Execution FSM, behind the Risk Engine."
        )

    def cancel_order(self, *args: Any, **kwargs: Any) -> Any:
        raise SafeModeViolation(
            "cancel_order is forbidden in Phase 3 (Exchange Gateway is "
            "read-only). Real cancellation lands in Issue #9 with the "
            "Execution FSM."
        )

    def set_leverage(self, *args: Any, **kwargs: Any) -> Any:
        raise SafeModeViolation(
            "set_leverage is forbidden in Phase 3 (Exchange Gateway is "
            "read-only). Leverage management lands in Issue #7 / #9, "
            "behind the Risk Engine."
        )

    def set_margin_mode(self, *args: Any, **kwargs: Any) -> Any:
        raise SafeModeViolation(
            "set_margin_mode is forbidden in Phase 3 (Exchange Gateway "
            "is read-only). Phase 3 keeps isolated-margin-only as the "
            "only allowed mode (Spec §13.2); changing it is forbidden."
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    @property
    def live_orders_enabled(self) -> bool:
        """Return False in Phase 3. Reserved for Phase 9+."""
        return self._live_orders_enabled

    def assert_read_only(self) -> None:
        """Boot-time assertion: refuse to operate if live orders are on.

        Called by `app/main.py` after the Phase 1 safety lock check, so
        Phase 3 has its own safety net independent of the config layer.
        """
        if self._live_orders_enabled:
            raise SafeModeViolation(
                f"{self.name}: live order placement was enabled but Phase 3 "
                f"only ships the read-only gateway. Refusing to start."
            )

    @property
    def reliability_tiers(self) -> dict[str, DataReliability]:
        """Default reliability tier each surface returns (Spec §13.3).

        Phase 3 contract, locked by `tests/unit/test_exchange_base.py
        ::test_reliability_tiers_contract`:

          - `get_recent_trades`     -> A (WS aggTrade / trade stream)
          - `get_orderbook`         -> A (WS depth-diff maintained book)
          - `get_funding_rate`      -> B (REST)
          - `get_open_interest`     -> B (REST)
          - `get_symbols`           -> B (REST exchangeInfo)
          - `get_account_snapshot`  -> B - mock / skeleton only in
            Phase 3 and Phase 4. Real account snapshots require an
            authenticated REST call and an API key, both of which are
            forbidden until the limited-live phase. A concrete
            implementation lives only in `MockExchangeClient`; the
            `BinanceClient` skeleton refuses with `NotImplementedError`.

        Adapters that fall back to a tier-B REST orderbook snapshot when
        the WS link is degraded should tag *that specific response*
        with `DataReliability.B` on the model. The default mapping here
        documents the canonical, healthy-link tier - not the worst case.
        """
        return {
            "get_symbols": DataReliability.B,
            "get_orderbook": DataReliability.A,
            "get_recent_trades": DataReliability.A,
            "get_funding_rate": DataReliability.B,
            "get_open_interest": DataReliability.B,
            "get_account_snapshot": DataReliability.B,
        }
