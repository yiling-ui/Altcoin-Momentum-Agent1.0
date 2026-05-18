"""Phase 3 (Issue #3) - ExchangeClientBase + WebSocketManager + ExchangeHealth.

These tests pin the abstract contract every concrete client must obey:

  - read-only methods are abstract (a client missing them cannot be
    instantiated)
  - the four write surfaces are CONCRETE on the base class and refuse
    with `SafeModeViolation` regardless of subclass behaviour
  - WebSocketManager.connect / disconnect drives `is_connected` and
    emits a `DATA_UNRELIABLE` event with the right payload
  - ExchangeHealth state transitions emit the expected EXCHANGE_*
    events through the `EventRepository`
  - `_require_trustworthy` refuses tier-A reads when the link is not
    CONNECTED.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from app.core.enums import DataReliability, ExchangeConnectionState
from app.core.errors import (
    AMARTError,
    ExchangeConnectionError,
    ExchangeError,
    SafeModeViolation,
    SafetyViolation,
)
from app.core.events import EventType
from app.exchanges.base import (
    READ_ONLY_METHODS,
    WRITE_SURFACE_METHODS,
    ExchangeClientBase,
    ExchangeHealth,
    WebSocketManager,
)
from app.exchanges.models import (
    AccountSnapshot,
    ExchangeSymbol,
    FundingRate,
    OpenInterest,
    OrderBook,
    OrderBookLevel,
    RecentTrade,
    TradeSide,
)


# ---------------------------------------------------------------------------
# A minimal subclass used to exercise the base class without relying on
# the BinanceClient / MockExchangeClient implementations.
# ---------------------------------------------------------------------------
class _FakeReadOnlyClient(ExchangeClientBase):
    """Tiny subclass that satisfies the abstract contract with no-ops."""

    name = "fake"

    def get_symbols(self) -> list[ExchangeSymbol]:
        self._require_trustworthy(surface="get_symbols")
        return [ExchangeSymbol(symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT")]

    def get_orderbook(self, symbol: str, *, depth: int = 20) -> OrderBook:
        self._require_trustworthy(surface="get_orderbook")
        return OrderBook(
            symbol=symbol,
            timestamp=0,
            bids=(OrderBookLevel(price=99.9, qty=1.0),),
            asks=(OrderBookLevel(price=100.1, qty=1.0),),
        )

    def get_recent_trades(self, symbol: str, *, limit: int = 100) -> list[RecentTrade]:
        self._require_trustworthy(surface="get_recent_trades")
        return []

    def get_funding_rate(self, symbol: str) -> FundingRate:
        self._require_trustworthy(surface="get_funding_rate")
        return FundingRate(symbol=symbol, timestamp=0, rate=0.0001, next_funding_ts=1)

    def get_open_interest(self, symbol: str) -> OpenInterest:
        self._require_trustworthy(surface="get_open_interest")
        return OpenInterest(symbol=symbol, timestamp=0, open_interest=10.0)

    def get_account_snapshot(self) -> AccountSnapshot:
        self._require_trustworthy(surface="get_account_snapshot")
        return AccountSnapshot(
            timestamp=0,
            total_equity=100.0,
            available_balance=80.0,
            margin_balance=20.0,
        )


# ---------------------------------------------------------------------------
# Abstract contract
# ---------------------------------------------------------------------------
def test_cannot_instantiate_base_class_directly():
    with pytest.raises(TypeError):
        ExchangeClientBase()  # type: ignore[abstract]


def test_read_only_methods_are_all_abstract():
    """Every entry in READ_ONLY_METHODS must be on the abstract method set."""
    abstracts = ExchangeClientBase.__abstractmethods__
    for name in READ_ONLY_METHODS:
        assert name in abstracts, f"{name} is not marked abstract"


def test_write_surface_methods_are_concrete_and_live_on_base():
    for name in WRITE_SURFACE_METHODS:
        attr = getattr(ExchangeClientBase, name)
        assert callable(attr)
        # The function must be defined on ExchangeClientBase itself, not
        # inherited from a mixin or subclass.
        assert attr.__qualname__.startswith("ExchangeClientBase.")


def test_subclass_missing_a_read_method_cannot_be_instantiated():
    class _Incomplete(ExchangeClientBase):
        # deliberately missing get_orderbook
        def get_symbols(self) -> list[ExchangeSymbol]:
            return []

        def get_recent_trades(self, symbol: str, *, limit: int = 100):
            return []

        def get_funding_rate(self, symbol: str):
            return FundingRate(symbol=symbol, timestamp=0, rate=0.0, next_funding_ts=0)

        def get_open_interest(self, symbol: str):
            return OpenInterest(symbol=symbol, timestamp=0, open_interest=0.0)

        def get_account_snapshot(self):
            return AccountSnapshot(timestamp=0, total_equity=0.0, available_balance=0.0, margin_balance=0.0)

    with pytest.raises(TypeError):
        _Incomplete()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Write-surface refusal
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fn_name", WRITE_SURFACE_METHODS)
def test_every_write_surface_refuses_with_safe_mode_violation(fn_name):
    client = _FakeReadOnlyClient()
    fn = getattr(client, fn_name)
    with pytest.raises(SafeModeViolation):
        fn()


def test_safe_mode_violation_is_a_safety_violation():
    """Phase 1 handlers that catch SafetyViolation must still catch the Phase 3 narrowing."""
    assert issubclass(SafeModeViolation, SafetyViolation)
    assert issubclass(SafetyViolation, AMARTError)


def test_exchange_error_hierarchy():
    assert issubclass(ExchangeConnectionError, ExchangeError)
    assert issubclass(ExchangeError, AMARTError)
    # ExchangeError is intentionally NOT a SafetyViolation: a transport
    # failure is recoverable, a write attempt is not.
    assert not issubclass(ExchangeError, SafetyViolation)


def test_assert_read_only_passes_when_live_orders_disabled():
    client = _FakeReadOnlyClient()
    # In Phase 3 every concrete client must construct with live orders
    # disabled. assert_read_only() must therefore succeed.
    client.assert_read_only()


def test_assert_read_only_refuses_when_live_orders_enabled():
    client = _FakeReadOnlyClient()
    client._live_orders_enabled = True  # simulate drift
    with pytest.raises(SafeModeViolation):
        client.assert_read_only()


# ---------------------------------------------------------------------------
# WebSocketManager
# ---------------------------------------------------------------------------
def test_ws_connect_disconnect_lifecycle():
    ws = WebSocketManager(owner_name="t.ws")
    assert not ws.is_connected
    ws.connect()
    assert ws.is_connected
    assert ws.connect_count == 1
    # double connect is a no-op
    ws.connect()
    assert ws.connect_count == 1
    ws.disconnect(reason="t")
    assert not ws.is_connected
    assert ws.disconnect_count == 1
    # double disconnect is a no-op
    ws.disconnect(reason="t")
    assert ws.disconnect_count == 1


def test_ws_disconnect_emits_data_unreliable(events_repo):
    ws = WebSocketManager(owner_name="t.ws", event_repo=events_repo)
    ws.connect()
    ws.subscribe("trades.BTCUSDT")
    assert events_repo.count_events(event_type=EventType.DATA_UNRELIABLE) == 0
    ws.disconnect(reason="link_drop")
    assert events_repo.count_events(event_type=EventType.DATA_UNRELIABLE) == 1
    [event] = events_repo.list_events(event_type=EventType.DATA_UNRELIABLE)
    assert event.payload["reason"] == "link_drop"
    assert event.payload["disconnect_count"] == 1
    assert "trades.BTCUSDT" in event.payload["subscriptions"]


def test_ws_subscribe_and_unsubscribe():
    ws = WebSocketManager()
    ws.subscribe("trades.X")
    ws.subscribe("book.X")
    assert ws.subscriptions == frozenset({"trades.X", "book.X"})
    ws.unsubscribe("trades.X")
    assert ws.subscriptions == frozenset({"book.X"})


# ---------------------------------------------------------------------------
# ExchangeHealth
# ---------------------------------------------------------------------------
def test_exchange_health_starts_uninitialised():
    h = ExchangeHealth()
    assert h.state is ExchangeConnectionState.UNINITIALISED
    assert not h.is_data_trustworthy()


def test_exchange_health_set_state_returns_change_flag():
    h = ExchangeHealth()
    assert h.set_state(ExchangeConnectionState.CONNECTED, reason="up") is True
    assert h.is_data_trustworthy()
    # No-op transition still returns False.
    assert h.set_state(ExchangeConnectionState.CONNECTED, reason="still_up") is False


def test_exchange_health_counters():
    h = ExchangeHealth()
    h.set_state(ExchangeConnectionState.CONNECTED, reason="up")
    h.set_state(ExchangeConnectionState.DEGRADED, reason="rest_only")
    h.set_state(ExchangeConnectionState.RECONNECTING, reason="ws_back")
    h.set_state(ExchangeConnectionState.DISCONNECTED, reason="hard_down")
    assert h.degraded_count == 1
    assert h.reconnect_count == 1
    assert h.disconnect_count == 1


# ---------------------------------------------------------------------------
# Health transitions emit events through the EventRepository
# ---------------------------------------------------------------------------
def test_start_emits_exchange_connected(events_repo):
    client = _FakeReadOnlyClient(event_repo=events_repo)
    client.start()
    [event] = events_repo.list_events(event_type=EventType.EXCHANGE_CONNECTED)
    assert event.payload["reason"] == "start"
    assert event.payload["health"]["state"] == "connected"
    assert event.source_module == "exchange.fake"


def test_stop_emits_exchange_disconnected_and_data_unreliable(events_repo):
    client = _FakeReadOnlyClient(event_repo=events_repo)
    client.start()
    client.stop(reason="bye")
    assert events_repo.count_events(event_type=EventType.EXCHANGE_DISCONNECTED) == 1
    assert events_repo.count_events(event_type=EventType.DATA_UNRELIABLE) == 1


def test_mark_degraded_emits_exchange_degraded_event(events_repo):
    client = _FakeReadOnlyClient(event_repo=events_repo)
    client.start()
    client._mark_degraded(reason="rest_only")
    assert events_repo.count_events(event_type=EventType.EXCHANGE_DEGRADED) == 1


# ---------------------------------------------------------------------------
# Read-time gating (Spec §14.2 + §31)
# ---------------------------------------------------------------------------
def test_reads_refused_when_uninitialised():
    client = _FakeReadOnlyClient()
    with pytest.raises(ExchangeConnectionError):
        client.get_orderbook("BTCUSDT")


def test_reads_refused_when_disconnected():
    client = _FakeReadOnlyClient()
    client.start()
    client.stop(reason="t")
    with pytest.raises(ExchangeConnectionError):
        client.get_orderbook("BTCUSDT")


def test_reads_succeed_when_connected():
    client = _FakeReadOnlyClient()
    client.start()
    book = client.get_orderbook("BTCUSDT")
    assert book.symbol == "BTCUSDT"


# ---------------------------------------------------------------------------
# reliability_tiers contract (Spec §13.3)
# ---------------------------------------------------------------------------
def test_reliability_tiers_contract():
    """Phase 3 reviewer-mandated tier table (Issue #3 review fix).

    Locks the canonical, healthy-link tier each surface returns:
      get_recent_trades     A
      get_orderbook         A
      get_funding_rate      B
      get_open_interest     B
      get_symbols           B
      get_account_snapshot  B (mock-only / skeleton-only in Phase 3+4)
    """
    client = _FakeReadOnlyClient()
    tiers = client.reliability_tiers
    assert tiers == {
        "get_symbols": DataReliability.B,
        "get_orderbook": DataReliability.A,
        "get_recent_trades": DataReliability.A,
        "get_funding_rate": DataReliability.B,
        "get_open_interest": DataReliability.B,
        "get_account_snapshot": DataReliability.B,
    }


def test_reliability_tiers_lists_all_six_read_methods():
    """Every entry in READ_ONLY_METHODS has a tier; no extras."""
    client = _FakeReadOnlyClient()
    assert set(client.reliability_tiers.keys()) == set(READ_ONLY_METHODS)


def test_orderbook_default_reliability_is_a_at_model_level():
    """A bare-default OrderBook (no explicit reliability) is tier A.

    This pins the model-level contract that backs `reliability_tiers`.
    A REST-fallback snapshot must override this explicitly via
    `OrderBook(..., reliability=DataReliability.B)`.
    """
    book = OrderBook(symbol="BTCUSDT", timestamp=0)
    assert book.reliability is DataReliability.A


def test_read_only_methods_constant_matches_abstract_set():
    """READ_ONLY_METHODS is what the entrypoint and tests rely on; it
    must be exactly the abstract set on ExchangeClientBase."""
    assert set(READ_ONLY_METHODS) == set(ExchangeClientBase.__abstractmethods__)


def test_write_surface_methods_constant_lists_four():
    assert set(WRITE_SURFACE_METHODS) == {
        "create_order",
        "cancel_order",
        "set_leverage",
        "set_margin_mode",
    }


# ---------------------------------------------------------------------------
# No accidental network surface in app.exchanges.base
# ---------------------------------------------------------------------------
def test_base_module_imports_no_network_libraries():
    import app.exchanges.base as base_mod

    src = inspect.getsource(base_mod)
    # We allow `loguru` and stdlib `dataclasses`. Anything that opens a
    # socket must NOT appear as an actual import. The Phase 1 review
    # fix used the same pattern for app/telegram/formatter.py.
    forbidden = ("aiohttp", "websockets", "websocket", "requests", "httpx", "ccxt")
    for line in src.splitlines():
        stripped = line.strip()
        for token in forbidden:
            assert not stripped.startswith(f"import {token}"), (
                f"app.exchanges.base imports {token}"
            )
            assert not stripped.startswith(f"from {token}"), (
                f"app.exchanges.base imports from {token}"
            )
