"""Phase 3 (Issue #3) - MockExchangeClient.

The mock client is the deterministic in-memory implementation used by
the entrypoint and the test suite. It must:

  - return data without opening a network socket
  - autostart into CONNECTED and emit EXCHANGE_CONNECTED
  - drive disconnect / reconnect / degraded state transitions
  - refuse tier-A reads while disconnected
  - allow REST tier-B reads (symbols, account snapshot) while DEGRADED
  - inherit SafeModeViolation refusal for every write surface
  - honour an explicit MockExchangeSeed for full determinism

These tests are also the closest thing Phase 3 has to integration
coverage: they exercise the gateway end-to-end against the EventRepository.
"""

from __future__ import annotations

import inspect

import pytest

from app.core.enums import DataReliability, ExchangeConnectionState
from app.core.errors import ExchangeConnectionError, SafeModeViolation
from app.core.events import EventType
from app.exchanges.base import WRITE_SURFACE_METHODS
from app.exchanges.mock import MockExchangeClient, MockExchangeSeed
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
# Boot lifecycle
# ---------------------------------------------------------------------------
def test_mock_autostart_emits_exchange_connected(events_repo):
    client = MockExchangeClient(event_repo=events_repo, autostart=True)
    assert client.health.state is ExchangeConnectionState.CONNECTED
    assert client.health.is_data_trustworthy()
    assert events_repo.count_events(event_type=EventType.EXCHANGE_CONNECTED) == 1


def test_mock_no_autostart_stays_uninitialised(events_repo):
    client = MockExchangeClient(event_repo=events_repo, autostart=False)
    assert client.health.state is ExchangeConnectionState.UNINITIALISED
    assert events_repo.count_events(event_type=EventType.EXCHANGE_CONNECTED) == 0


# ---------------------------------------------------------------------------
# Read-only API (Issue #3 acceptance criteria 1-3)
# ---------------------------------------------------------------------------
def test_mock_get_symbols_returns_default_set():
    client = MockExchangeClient()
    symbols = client.get_symbols()
    names = {s.symbol for s in symbols}
    # Phase 3 default seed includes BTCUSDT, ETHUSDT, PEPEUSDT.
    assert {"BTCUSDT", "ETHUSDT", "PEPEUSDT"}.issubset(names)


def test_mock_get_orderbook_returns_well_formed_book():
    client = MockExchangeClient()
    book = client.get_orderbook("BTCUSDT", depth=3)
    assert book.symbol == "BTCUSDT"
    assert len(book.bids) == 3
    assert len(book.asks) == 3
    # Bids descending, asks ascending - the model validates this too.
    assert book.bids[0].price > book.bids[-1].price
    assert book.asks[0].price < book.asks[-1].price
    assert book.spread is not None and book.spread > 0


def test_mock_get_recent_trades_returns_deterministic_tape():
    client = MockExchangeClient()
    trades = client.get_recent_trades("BTCUSDT", limit=5)
    assert len(trades) == 5
    assert all(t.symbol == "BTCUSDT" for t in trades)
    # Trades alternate side BUY/SELL by construction.
    assert {t.side for t in trades} == {TradeSide.BUY, TradeSide.SELL}


def test_mock_get_funding_rate_default():
    client = MockExchangeClient()
    f = client.get_funding_rate("BTCUSDT")
    assert f.symbol == "BTCUSDT"
    assert f.rate == 0.0001
    assert f.reliability is DataReliability.B


def test_mock_get_open_interest_default():
    client = MockExchangeClient()
    oi = client.get_open_interest("BTCUSDT")
    assert oi.symbol == "BTCUSDT"
    assert oi.reliability is DataReliability.B


def test_mock_get_account_snapshot_default():
    client = MockExchangeClient()
    snap = client.get_account_snapshot()
    assert snap.total_equity == 0.0
    assert snap.reliability is DataReliability.B


# ---------------------------------------------------------------------------
# Seed determinism
# ---------------------------------------------------------------------------
def test_mock_honours_supplied_seed():
    seed = MockExchangeSeed(
        symbols=[
            ExchangeSymbol(
                symbol="DOGEUSDT", base_asset="DOGE", quote_asset="USDT"
            ),
        ],
        orderbooks={
            "DOGEUSDT": OrderBook(
                symbol="DOGEUSDT",
                timestamp=1_000_000,
                bids=(OrderBookLevel(price=0.10, qty=10.0),),
                asks=(OrderBookLevel(price=0.11, qty=10.0),),
            ),
        },
        trades={
            "DOGEUSDT": [
                RecentTrade(
                    symbol="DOGEUSDT",
                    trade_id="seed-1",
                    timestamp=1_000_000,
                    price=0.105,
                    qty=100.0,
                    side=TradeSide.BUY,
                ),
            ],
        },
        funding_rates={
            "DOGEUSDT": FundingRate(
                symbol="DOGEUSDT",
                timestamp=1_000_000,
                rate=0.001,
                next_funding_ts=2_000_000,
            ),
        },
        open_interest={
            "DOGEUSDT": OpenInterest(
                symbol="DOGEUSDT",
                timestamp=1_000_000,
                open_interest=42.0,
                open_interest_value=4.2,
            ),
        },
        account=AccountSnapshot(
            timestamp=1_000_000,
            total_equity=100.0,
            available_balance=80.0,
            margin_balance=20.0,
            unrealized_pnl=5.0,
            open_position_count=1,
        ),
    )
    client = MockExchangeClient(seed=seed)
    assert client.get_symbols()[0].symbol == "DOGEUSDT"
    book = client.get_orderbook("DOGEUSDT")
    assert book.best_bid == 0.10
    assert book.best_ask == 0.11
    [trade] = client.get_recent_trades("DOGEUSDT")
    assert trade.trade_id == "seed-1"
    f = client.get_funding_rate("DOGEUSDT")
    assert f.rate == 0.001
    oi = client.get_open_interest("DOGEUSDT")
    assert oi.open_interest == 42.0
    snap = client.get_account_snapshot()
    assert snap.total_equity == 100.0


# ---------------------------------------------------------------------------
# Disconnect / reconnect / degraded scenarios
# ---------------------------------------------------------------------------
def test_disconnect_marks_data_unreliable_and_emits_events(events_repo):
    client = MockExchangeClient(event_repo=events_repo)
    client.simulate_disconnect(reason="test_drop")
    assert client.health.state is ExchangeConnectionState.DISCONNECTED
    assert not client.health.is_data_trustworthy()
    assert events_repo.count_events(event_type=EventType.EXCHANGE_DISCONNECTED) == 1
    assert events_repo.count_events(event_type=EventType.DATA_UNRELIABLE) == 1


def test_orderbook_refused_when_disconnected():
    client = MockExchangeClient()
    client.simulate_disconnect()
    with pytest.raises(ExchangeConnectionError):
        client.get_orderbook("BTCUSDT")


def test_recent_trades_refused_when_disconnected():
    client = MockExchangeClient()
    client.simulate_disconnect()
    with pytest.raises(ExchangeConnectionError):
        client.get_recent_trades("BTCUSDT")


def test_funding_rate_refused_when_disconnected():
    client = MockExchangeClient()
    client.simulate_disconnect()
    with pytest.raises(ExchangeConnectionError):
        client.get_funding_rate("BTCUSDT")


def test_open_interest_refused_when_disconnected():
    client = MockExchangeClient()
    client.simulate_disconnect()
    with pytest.raises(ExchangeConnectionError):
        client.get_open_interest("BTCUSDT")


def test_symbols_refused_when_disconnected():
    """Even tier-B surfaces refuse when the connection is fully down."""
    client = MockExchangeClient()
    client.simulate_disconnect()
    with pytest.raises(ExchangeConnectionError):
        client.get_symbols()


def test_account_snapshot_refused_when_disconnected():
    client = MockExchangeClient()
    client.simulate_disconnect()
    with pytest.raises(ExchangeConnectionError):
        client.get_account_snapshot()


# ---- Degraded mode (REST up, WS down) keeps tier-B surfaces usable -------
def test_symbols_allowed_when_degraded():
    """Spec §13.3: REST tier B is still trustworthy when WS is down."""
    client = MockExchangeClient()
    client.simulate_degraded(reason="ws_down")
    assert client.health.state is ExchangeConnectionState.DEGRADED
    # symbols + account_snapshot are REST-only surfaces; they keep working.
    assert client.get_symbols()


def test_account_snapshot_allowed_when_degraded():
    client = MockExchangeClient()
    client.simulate_degraded(reason="ws_down")
    snap = client.get_account_snapshot()
    assert snap.reliability is DataReliability.B


def test_orderbook_refused_when_degraded():
    """Tier-A surfaces (orderbook, trades) need a healthy WS link."""
    client = MockExchangeClient()
    client.simulate_degraded(reason="ws_down")
    with pytest.raises(ExchangeConnectionError):
        client.get_orderbook("BTCUSDT")


def test_recent_trades_refused_when_degraded():
    client = MockExchangeClient()
    client.simulate_degraded(reason="ws_down")
    with pytest.raises(ExchangeConnectionError):
        client.get_recent_trades("BTCUSDT")


# ---- Reconnect path -------------------------------------------------------
def test_simulate_reconnect_restores_trustworthy_state(events_repo):
    client = MockExchangeClient(event_repo=events_repo)
    client.simulate_disconnect(reason="drop")
    client.simulate_reconnect(reason="recovered")
    assert client.health.state is ExchangeConnectionState.CONNECTED
    assert client.health.is_data_trustworthy()
    # We start CONNECTED (autostart), drop to DISCONNECTED,
    # then reconnect -> a 2nd EXCHANGE_CONNECTED is logged.
    assert events_repo.count_events(event_type=EventType.EXCHANGE_CONNECTED) == 2


# ---------------------------------------------------------------------------
# Write surfaces refuse on the mock too
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fn_name", WRITE_SURFACE_METHODS)
def test_mock_write_surfaces_refuse(fn_name):
    client = MockExchangeClient()
    fn = getattr(client, fn_name)
    with pytest.raises(SafeModeViolation):
        fn()


def test_mock_does_not_override_write_surfaces():
    """The mock must inherit the base refusal; subclassing the write
    surfaces would bypass Spec §13.2."""
    for name in WRITE_SURFACE_METHODS:
        assert getattr(MockExchangeClient, name).__qualname__.startswith(
            "ExchangeClientBase."
        ), f"MockExchangeClient.{name} must NOT override base refusal"


# ---------------------------------------------------------------------------
# No network surface
# ---------------------------------------------------------------------------
def test_mock_module_imports_no_network_libraries():
    import app.exchanges.mock as mock_mod

    src = inspect.getsource(mock_mod)
    forbidden = ("aiohttp", "websockets", "websocket", "requests", "httpx", "ccxt")
    for line in src.splitlines():
        stripped = line.strip()
        for token in forbidden:
            assert not stripped.startswith(f"import {token}"), (
                f"app.exchanges.mock imports {token}"
            )
            assert not stripped.startswith(f"from {token}"), (
                f"app.exchanges.mock imports from {token}"
            )


def test_full_lifecycle_smoke(events_repo):
    """One-shot smoke: start -> read -> disconnect -> read refused ->
    reconnect -> read works again. Mirrors the boot path in app/main.py."""
    client = MockExchangeClient(event_repo=events_repo)
    assert len(client.get_symbols()) >= 1
    assert client.get_orderbook("BTCUSDT").best_bid is not None

    client.simulate_disconnect(reason="ci_test")
    with pytest.raises(ExchangeConnectionError):
        client.get_orderbook("BTCUSDT")

    client.simulate_reconnect(reason="ci_test_recovered")
    assert client.get_orderbook("BTCUSDT").best_bid is not None
