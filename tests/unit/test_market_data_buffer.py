"""Phase 4 - MarketDataBuffer integration tests.

Covers Issue #4 acceptance criteria 3 and 4:

  - 数据缺失时返回 degraded.
  - WebSocket 断线时写入 DATA_UNRELIABLE event.

Plus the REST/WS conflict path (Spec §14.2 + §31).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

import pytest

from app.core.enums import DataReliability
from app.core.errors import ExchangeError
from app.core.events import EventType
from app.core.models import MarketSnapshot
from app.database.migrations import apply_schema
from app.database.repositories import EventRepository
from app.exchanges import MockExchangeClient
from app.exchanges.binance import BinanceClient
from app.exchanges.mock import MockExchangeSeed
from app.exchanges.models import (
    ExchangeSymbol,
    FundingRate,
    OpenInterest,
    OrderBook,
    OrderBookLevel,
    RecentTrade,
    TradeSide,
)
from app.market_data import MarketDataBuffer
from app.market_data.models import (
    LiquidationEvent,
    LiquidationSide,
    MarketDataBufferConfig,
    MarketDataDegradedReason,
    MarketDataStalenessConfig,
)


T0 = 1_779_062_400_000


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def repo() -> EventRepository:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    yield EventRepository(conn)
    conn.close()


@pytest.fixture
def fresh_seed() -> MockExchangeSeed:
    """A deterministic in-process tape anchored at T0."""
    syms = [
        ExchangeSymbol(
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            price_tick=0.1,
            qty_step=0.001,
            min_notional=5.0,
        )
    ]
    trades = {
        "BTCUSDT": [
            RecentTrade(
                symbol="BTCUSDT",
                trade_id=f"t-{i}",
                timestamp=T0 + i * 1000,
                price=100.0 + i * 0.1,
                qty=1.0,
                side=TradeSide.BUY if i % 2 == 0 else TradeSide.SELL,
                is_buyer_maker=(i % 2 == 1),
            )
            for i in range(5)
        ]
    }
    book = OrderBook(
        symbol="BTCUSDT",
        timestamp=T0 + 4_000,
        bids=tuple(OrderBookLevel(price=100 - 0.1 * (i + 1), qty=1.0) for i in range(3)),
        asks=tuple(OrderBookLevel(price=100 + 0.1 * (i + 1), qty=1.0) for i in range(3)),
    )
    return MockExchangeSeed(
        symbols=syms,
        trades=trades,
        orderbooks={"BTCUSDT": book},
        funding_rates={
            "BTCUSDT": FundingRate(
                symbol="BTCUSDT",
                timestamp=T0 + 4_000,
                rate=0.0001,
                next_funding_ts=T0 + 100_000_000,
            )
        },
        open_interest={
            "BTCUSDT": OpenInterest(
                symbol="BTCUSDT",
                timestamp=T0 + 4_000,
                open_interest=1_000_000.0,
                open_interest_value=1.0e8,
            )
        },
    )


def buy_taker(*, ts: int, qty: float = 1.0, price: float = 100.0) -> RecentTrade:
    return RecentTrade(
        symbol="BTCUSDT",
        trade_id=f"buy-{ts}-{qty}",
        timestamp=ts,
        price=price,
        qty=qty,
        side=TradeSide.BUY,
        is_buyer_maker=False,
    )


def sell_taker(*, ts: int, qty: float = 1.0, price: float = 100.0) -> RecentTrade:
    return RecentTrade(
        symbol="BTCUSDT",
        trade_id=f"sell-{ts}-{qty}",
        timestamp=ts,
        price=price,
        qty=qty,
        side=TradeSide.SELL,
        is_buyer_maker=True,
    )


def _data_unreliable_events(repo: EventRepository) -> list:
    return repo.list_events(event_type=EventType.DATA_UNRELIABLE)


def _market_snapshot_events(repo: EventRepository) -> list:
    return repo.list_events(event_type=EventType.MARKET_SNAPSHOT)


# ---------------------------------------------------------------------------
# Basic ingestion + snapshot
# ---------------------------------------------------------------------------
def test_track_creates_symbol_state_lazily():
    buf = MarketDataBuffer()
    assert buf.symbols == ()
    buf.track("BTCUSDT")
    assert buf.symbols == ("BTCUSDT",)
    # is_degraded is True for never-initialised symbols.
    assert buf.is_degraded("BTCUSDT") is True
    assert MarketDataDegradedReason.NEVER_INITIALISED in buf.degraded_reasons(
        "BTCUSDT"
    )


def test_unknown_symbol_is_never_initialised():
    buf = MarketDataBuffer()
    assert buf.is_degraded("DOESNOTEXIST") is True
    assert buf.degraded_reasons("DOESNOTEXIST") == (
        MarketDataDegradedReason.NEVER_INITIALISED,
    )


def test_ingest_trades_populates_rolling_windows():
    cfg = MarketDataBufferConfig(
        trades_window_1m_ms=60_000,
        trades_window_5m_ms=300_000,
        trades_window_15m_ms=900_000,
    )
    buf = MarketDataBuffer(config=cfg)
    for i in range(20):
        buf.ingest_trade(buy_taker(ts=T0 + i * 30_000))
    snap = buf.snapshot("BTCUSDT", emit_event=False)
    # Newest 60s window: only the last 3 trades fit (T0+18*30s, T0+19*30s, plus the t=T0 anchor).
    # Specifically: cutoff = (T0 + 19*30_000) - 60_000 = T0 + 510_000
    # Trades surviving: 30s ts in [510_000, 570_000] -> 18*30, 19*30 = 2 trades
    # but we keep ts >= cutoff, so timestamps T0+510_000 and T0+540_000 and T0+570_000 = 3 trades.
    assert snap.volume_1m == pytest.approx(3.0)
    # 5m window: cutoff = T0+570_000 - 300_000 = T0+270_000 -> 11 trades survive.
    assert snap.volume_5m == pytest.approx(11.0)


def test_snapshot_returns_marketsnapshot_with_spec_fields(repo, fresh_seed):
    client = MockExchangeClient(seed=fresh_seed, autostart=True)
    buf = MarketDataBuffer(exchange=client, event_repo=repo)
    buf.track("BTCUSDT")
    buf.refresh_from_exchange("BTCUSDT")
    snap = buf.snapshot("BTCUSDT", emit_event=True, timestamp_override=T0 + 5_000)
    assert isinstance(snap, MarketSnapshot)
    assert snap.symbol == "BTCUSDT"
    assert snap.bid is not None and snap.ask is not None and snap.bid < snap.ask
    assert snap.spread_pct >= 0
    assert snap.cvd_1m is not None
    assert snap.cvd_5m is not None
    assert snap.oi == pytest.approx(1_000_000.0)
    assert snap.funding_rate == pytest.approx(0.0001)
    assert snap.orderbook_depth_usdt is not None
    # MARKET_SNAPSHOT event was written.
    snaps = _market_snapshot_events(repo)
    assert len(snaps) == 1
    assert snaps[0].symbol == "BTCUSDT"


def test_cvd_helpers_match_compute_cvd(repo):
    cfg = MarketDataBufferConfig()
    buf = MarketDataBuffer(config=cfg, event_repo=repo)
    # 5 buys + 3 sells in the 1m window
    trades = [buy_taker(ts=T0 + i) for i in range(5)] + [
        sell_taker(ts=T0 + 30_000 + i) for i in range(3)
    ]
    buf.ingest_trades(trades)
    snap = buf.snapshot("BTCUSDT", emit_event=False)
    assert snap.cvd_1m == pytest.approx(2.0)  # 5 - 3
    assert snap.cvd_5m == pytest.approx(2.0)
    assert buf.cvd_15m("BTCUSDT") == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Issue #4 acceptance criterion 3: data missing -> degraded
# ---------------------------------------------------------------------------
def test_no_data_is_degraded():
    buf = MarketDataBuffer()
    buf.track("BTCUSDT")
    assert buf.is_degraded("BTCUSDT") is True


def test_partial_data_is_degraded_until_all_surfaces_arrive():
    cfg = MarketDataBufferConfig(
        staleness=MarketDataStalenessConfig(
            trades_max_silence_ms=60_000,
            orderbook_max_silence_ms=60_000,
            oi_max_silence_ms=60_000,
            funding_max_silence_ms=60_000,
        )
    )
    buf = MarketDataBuffer(config=cfg)
    buf.track("BTCUSDT")
    buf.ingest_trade(buy_taker(ts=T0))
    # After only trades have arrived, orderbook/oi/funding are all stale.
    reasons = set(buf.degraded_reasons("BTCUSDT"))
    assert MarketDataDegradedReason.ORDERBOOK_STALE in reasons
    assert MarketDataDegradedReason.OI_STALE in reasons
    assert MarketDataDegradedReason.FUNDING_STALE in reasons
    assert MarketDataDegradedReason.TRADES_STALE not in reasons


def test_full_fresh_data_is_not_degraded(fresh_seed):
    client = MockExchangeClient(seed=fresh_seed, autostart=True)
    buf = MarketDataBuffer(exchange=client)
    buf.track("BTCUSDT")
    buf.refresh_from_exchange("BTCUSDT")
    assert buf.is_degraded("BTCUSDT") is False
    assert buf.degraded_reasons("BTCUSDT") == ()


def test_stale_window_recomputed_on_each_query(fresh_seed):
    """Spec §14.2: staleness must be a *live* check, not cached.

    We feed fresh data, then advance the buffer's clock anchor by
    feeding a brand-new trade that crosses every staleness threshold.
    The buffer should re-detect staleness for the surfaces that didn't
    update.
    """
    client = MockExchangeClient(seed=fresh_seed, autostart=True)
    cfg = MarketDataBufferConfig(
        staleness=MarketDataStalenessConfig(
            trades_max_silence_ms=10_000,
            orderbook_max_silence_ms=10_000,
            oi_max_silence_ms=10_000,
            funding_max_silence_ms=10_000,
        )
    )
    buf = MarketDataBuffer(config=cfg, exchange=client)
    buf.track("BTCUSDT")
    buf.refresh_from_exchange("BTCUSDT")
    assert buf.is_degraded("BTCUSDT") is False
    # New trade 5 minutes after the seed; orderbook/oi/funding are not
    # updated, so they should now be stale.
    buf.ingest_trade(buy_taker(ts=T0 + 5 * 60_000))
    reasons = set(buf.degraded_reasons("BTCUSDT"))
    assert MarketDataDegradedReason.ORDERBOOK_STALE in reasons
    assert MarketDataDegradedReason.OI_STALE in reasons
    assert MarketDataDegradedReason.FUNDING_STALE in reasons


# ---------------------------------------------------------------------------
# Issue #4 acceptance criterion 4: WS disconnect -> DATA_UNRELIABLE event
# ---------------------------------------------------------------------------
def test_websocket_disconnect_writes_data_unreliable_event(repo):
    buf = MarketDataBuffer(event_repo=repo)
    buf.track("BTCUSDT")
    buf.track("ETHUSDT")
    buf.on_websocket_disconnect(reason="ws_drop")
    events = _data_unreliable_events(repo)
    # One batched event for the WS drop. The "track" calls above were
    # never-initialised which already emitted on first state recompute,
    # but the disconnect path emits one batch with scope=all_symbols.
    ws_drops = [e for e in events if e.payload.get("scope") == "all_symbols"]
    assert len(ws_drops) == 1
    assert ws_drops[0].payload["trigger"] == "websocket_disconnect"
    assert sorted(ws_drops[0].payload["symbols"]) == ["BTCUSDT", "ETHUSDT"]
    # Both symbols are now degraded with EXCHANGE_DISCONNECTED.
    assert MarketDataDegradedReason.EXCHANGE_DISCONNECTED in buf.degraded_reasons(
        "BTCUSDT"
    )
    assert MarketDataDegradedReason.EXCHANGE_DISCONNECTED in buf.degraded_reasons(
        "ETHUSDT"
    )
    assert buf.data_unreliable_events_emitted >= 1


def test_websocket_reconnect_clears_explicit_disconnect_reason(repo, fresh_seed):
    client = MockExchangeClient(seed=fresh_seed, autostart=True)
    buf = MarketDataBuffer(exchange=client, event_repo=repo)
    buf.track("BTCUSDT")
    buf.refresh_from_exchange("BTCUSDT")
    assert buf.is_degraded("BTCUSDT") is False
    buf.on_websocket_disconnect(reason="ws_drop")
    assert buf.is_degraded("BTCUSDT") is True
    buf.on_websocket_reconnect(reason="ws_back")
    # After reconnect, the explicit disconnect reason is gone. Stale
    # window reasons may remain depending on timestamps, but for the
    # fresh-seed fixture there is no staleness yet.
    reasons = buf.degraded_reasons("BTCUSDT")
    assert MarketDataDegradedReason.EXCHANGE_DISCONNECTED not in reasons


def test_mark_degraded_emits_data_unreliable(repo):
    buf = MarketDataBuffer(event_repo=repo)
    buf.track("BTCUSDT")
    n_before = len(_data_unreliable_events(repo))
    buf.mark_degraded("BTCUSDT", note="manual")
    after = _data_unreliable_events(repo)
    assert len(after) > n_before
    assert MarketDataDegradedReason.EXPLICIT_MARK in buf.degraded_reasons(
        "BTCUSDT"
    )
    last = after[-1]
    assert last.symbol == "BTCUSDT"
    assert MarketDataDegradedReason.EXPLICIT_MARK.value in last.payload["reasons"]


def test_clear_explicit_does_not_clear_stale_reasons():
    cfg = MarketDataBufferConfig(
        staleness=MarketDataStalenessConfig(
            trades_max_silence_ms=10_000,
            orderbook_max_silence_ms=10_000,
            oi_max_silence_ms=10_000,
            funding_max_silence_ms=10_000,
        )
    )
    buf = MarketDataBuffer(config=cfg)
    buf.track("BTCUSDT")
    buf.mark_degraded("BTCUSDT")
    buf.clear_explicit_degraded("BTCUSDT")
    # The buffer is still NEVER_INITIALISED; clear_explicit only drops
    # the EXPLICIT_MARK reason.
    reasons = buf.degraded_reasons("BTCUSDT")
    assert MarketDataDegradedReason.EXPLICIT_MARK not in reasons
    assert MarketDataDegradedReason.NEVER_INITIALISED in reasons


# ---------------------------------------------------------------------------
# REST vs WS conflict (Spec §14.2)
# ---------------------------------------------------------------------------
def test_rest_book_does_not_silently_overwrite_ws_book(repo):
    buf = MarketDataBuffer(event_repo=repo)
    buf.track("BTCUSDT")
    ws_book = OrderBook(
        symbol="BTCUSDT",
        timestamp=T0,
        bids=(OrderBookLevel(price=99.0, qty=1.0),),
        asks=(OrderBookLevel(price=101.0, qty=1.0),),
        reliability=DataReliability.A,
    )
    rest_book = OrderBook(
        symbol="BTCUSDT",
        timestamp=T0 + 1_000,
        bids=(OrderBookLevel(price=50.0, qty=1.0),),
        asks=(OrderBookLevel(price=200.0, qty=1.0),),
        reliability=DataReliability.B,
    )
    buf.ingest_orderbook(ws_book)
    buf.ingest_orderbook(rest_book)
    # WS book wins; conflict is flagged.
    snap = buf.snapshot("BTCUSDT", emit_event=False)
    assert snap.bid == pytest.approx(99.0)
    assert snap.ask == pytest.approx(101.0)
    assert buf.rest_ws_conflicts_total == 1
    conflicts = [
        e
        for e in _data_unreliable_events(repo)
        if MarketDataDegradedReason.REST_WS_CONFLICT.value in e.payload.get("reasons", [])
    ]
    assert len(conflicts) == 1
    assert conflicts[0].payload["previous_reliability"] == "A"
    assert conflicts[0].payload["incoming_reliability"] == "B"


def test_higher_tier_book_overwrites_lower_tier(repo):
    buf = MarketDataBuffer(event_repo=repo)
    buf.track("BTCUSDT")
    rest_book = OrderBook(
        symbol="BTCUSDT",
        timestamp=T0,
        bids=(OrderBookLevel(price=50.0, qty=1.0),),
        asks=(OrderBookLevel(price=200.0, qty=1.0),),
        reliability=DataReliability.B,
    )
    ws_book = OrderBook(
        symbol="BTCUSDT",
        timestamp=T0 + 1_000,
        bids=(OrderBookLevel(price=99.0, qty=1.0),),
        asks=(OrderBookLevel(price=101.0, qty=1.0),),
        reliability=DataReliability.A,
    )
    buf.ingest_orderbook(rest_book)
    buf.ingest_orderbook(ws_book)
    snap = buf.snapshot("BTCUSDT", emit_event=False)
    assert snap.bid == pytest.approx(99.0)
    assert snap.ask == pytest.approx(101.0)
    # Conflict still recorded so the audit trail captures the upgrade.
    assert buf.rest_ws_conflicts_total == 1


def test_same_tier_newer_book_wins():
    buf = MarketDataBuffer()
    buf.track("BTCUSDT")
    a = OrderBook(
        symbol="BTCUSDT",
        timestamp=T0,
        bids=(OrderBookLevel(price=99.0, qty=1.0),),
        asks=(OrderBookLevel(price=101.0, qty=1.0),),
        reliability=DataReliability.A,
    )
    b = OrderBook(
        symbol="BTCUSDT",
        timestamp=T0 + 1_000,
        bids=(OrderBookLevel(price=98.0, qty=1.0),),
        asks=(OrderBookLevel(price=102.0, qty=1.0),),
        reliability=DataReliability.A,
    )
    buf.ingest_orderbook(a)
    buf.ingest_orderbook(b)
    snap = buf.snapshot("BTCUSDT", emit_event=False)
    assert snap.bid == pytest.approx(98.0)
    assert buf.rest_ws_conflicts_total == 0


# ---------------------------------------------------------------------------
# Exchange health propagation
# ---------------------------------------------------------------------------
def test_exchange_disconnected_propagates_to_buffer(repo, fresh_seed):
    client = MockExchangeClient(seed=fresh_seed, autostart=True)
    buf = MarketDataBuffer(exchange=client, event_repo=repo)
    buf.track("BTCUSDT")
    buf.refresh_from_exchange("BTCUSDT")
    assert buf.is_degraded("BTCUSDT") is False
    client.simulate_disconnect(reason="test")
    # Spec §14.2: a disconnected gateway turns the per-symbol view degraded.
    assert MarketDataDegradedReason.EXCHANGE_DISCONNECTED in buf.degraded_reasons(
        "BTCUSDT"
    )


def test_exchange_degraded_is_treated_as_degraded(repo, fresh_seed):
    client = MockExchangeClient(seed=fresh_seed, autostart=True)
    buf = MarketDataBuffer(exchange=client, event_repo=repo)
    buf.track("BTCUSDT")
    buf.refresh_from_exchange("BTCUSDT")
    client.simulate_degraded(reason="ws_lag")
    assert MarketDataDegradedReason.EXCHANGE_DEGRADED in buf.degraded_reasons(
        "BTCUSDT"
    )


# ---------------------------------------------------------------------------
# Liquidations
# ---------------------------------------------------------------------------
def test_liquidation_event_is_stored_per_symbol():
    buf = MarketDataBuffer()
    buf.track("PEPEUSDT")
    buf.ingest_liquidation(
        LiquidationEvent(
            symbol="PEPEUSDT",
            timestamp=T0,
            side=LiquidationSide.LONG,
            price=1.0,
            qty=10.0,
        )
    )
    st = buf._symbols["PEPEUSDT"]  # noqa: SLF001 - state inspection in test
    assert len(st.liquidations) == 1


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------
def test_stats_reflects_state(repo, fresh_seed):
    client = MockExchangeClient(seed=fresh_seed, autostart=True)
    buf = MarketDataBuffer(exchange=client, event_repo=repo)
    buf.track("BTCUSDT")
    buf.refresh_from_exchange("BTCUSDT")
    snap = buf.snapshot("BTCUSDT", emit_event=True)
    assert isinstance(snap, MarketSnapshot)
    stats = buf.stats()
    assert stats.symbols_tracked == 1
    assert stats.symbols_degraded == 0
    assert stats.market_snapshot_events_emitted == 1


# ---------------------------------------------------------------------------
# refresh_from_exchange safety
# ---------------------------------------------------------------------------
def test_refresh_from_exchange_requires_a_client():
    buf = MarketDataBuffer()
    with pytest.raises(RuntimeError):
        buf.refresh_from_exchange("BTCUSDT")


def test_refresh_from_exchange_propagates_notimplementederror_from_binance(repo):
    """Phase 4 hard rule: BinanceClient must remain a skeleton.

    If a future caller mistakenly wires a BinanceClient into the
    buffer, refresh_from_exchange must SURFACE the
    ``NotImplementedError`` rather than silently sitting on empty data.
    Otherwise the No-Trade Gate (Issue #7) would be tricked into
    thinking it had fresh data.
    """
    client = BinanceClient()
    # The skeleton's start() simply marks state as CONNECTED via the
    # WebSocketManager skeleton; no network is touched.
    client.start()
    buf = MarketDataBuffer(exchange=client, event_repo=repo)
    buf.track("BTCUSDT")
    with pytest.raises(NotImplementedError):
        buf.refresh_from_exchange("BTCUSDT")


def test_refresh_from_exchange_short_circuits_on_disconnected_client(repo, fresh_seed):
    client = MockExchangeClient(seed=fresh_seed, autostart=True)
    buf = MarketDataBuffer(exchange=client, event_repo=repo)
    buf.track("BTCUSDT")
    client.simulate_disconnect(reason="test")
    # Should NOT call get_recent_trades / get_orderbook (the Phase 3
    # tier-A guard would refuse them anyway). The buffer just records
    # the disconnect.
    buf.refresh_from_exchange("BTCUSDT")
    assert MarketDataDegradedReason.EXCHANGE_DISCONNECTED in buf.degraded_reasons(
        "BTCUSDT"
    )


# ---------------------------------------------------------------------------
# Phase 4 invariant: the buffer must not hold or accept credentials.
# ---------------------------------------------------------------------------
def test_buffer_constructor_takes_no_api_key():
    """Phase 4 boundary: no API key path. The constructor exposes no
    such parameter; trying to inject one should fail loudly."""
    with pytest.raises(TypeError):
        MarketDataBuffer(api_key="should_not_exist")  # type: ignore[call-arg]


def test_binance_client_still_refuses_credentials_at_construction():
    """Phase 4 must NOT loosen the Phase 3 anti-leak rule."""
    with pytest.raises(ExchangeError):
        BinanceClient(api_key="x", api_secret="y")
