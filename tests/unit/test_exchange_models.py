"""Phase 3 (Issue #3) - read-only data model contracts.

Covers the Pydantic shapes shipped by `app.exchanges.models` plus the
data-reliability tier ordering enforced by
`DataReliability.is_at_least`. These models are the only types Phase 4
(Market Data Buffer) will receive from the gateway, so the schema
contract must be locked here.
"""

from __future__ import annotations

import pytest

from app.core.enums import DataReliability, ExchangeConnectionState
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
# DataReliability ordering (Spec §13.3)
# ---------------------------------------------------------------------------
def test_data_reliability_a_is_strongest():
    assert DataReliability.A.is_at_least(DataReliability.A)
    assert DataReliability.A.is_at_least(DataReliability.B)
    assert DataReliability.A.is_at_least(DataReliability.C)
    assert DataReliability.A.is_at_least(DataReliability.D)


def test_data_reliability_d_is_weakest():
    assert DataReliability.D.is_at_least(DataReliability.D)
    assert not DataReliability.D.is_at_least(DataReliability.A)
    assert not DataReliability.D.is_at_least(DataReliability.B)
    assert not DataReliability.D.is_at_least(DataReliability.C)


@pytest.mark.parametrize(
    ("higher", "lower"),
    [
        (DataReliability.A, DataReliability.B),
        (DataReliability.B, DataReliability.C),
        (DataReliability.C, DataReliability.D),
    ],
)
def test_data_reliability_strict_ordering(higher, lower):
    assert higher.is_at_least(lower)
    assert not lower.is_at_least(higher)


# ---------------------------------------------------------------------------
# ExchangeConnectionState
# ---------------------------------------------------------------------------
def test_only_connected_is_trustworthy():
    assert ExchangeConnectionState.CONNECTED.is_trustworthy
    assert not ExchangeConnectionState.UNINITIALISED.is_trustworthy
    assert not ExchangeConnectionState.DEGRADED.is_trustworthy
    assert not ExchangeConnectionState.RECONNECTING.is_trustworthy
    assert not ExchangeConnectionState.DISCONNECTED.is_trustworthy


# ---------------------------------------------------------------------------
# ExchangeSymbol
# ---------------------------------------------------------------------------
def test_exchange_symbol_is_frozen():
    s = ExchangeSymbol(symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT")
    with pytest.raises(Exception):
        # Pydantic v2 frozen -> mutating raises.
        s.symbol = "ETHUSDT"  # type: ignore[misc]


def test_exchange_symbol_extra_fields_forbidden():
    with pytest.raises(Exception):
        ExchangeSymbol(
            symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT", side="long"
        )


# ---------------------------------------------------------------------------
# OrderBook
# ---------------------------------------------------------------------------
def test_orderbook_best_bid_ask_and_spread():
    book = OrderBook(
        symbol="BTCUSDT",
        timestamp=0,
        bids=(OrderBookLevel(price=99.9, qty=1), OrderBookLevel(price=99.8, qty=1)),
        asks=(OrderBookLevel(price=100.1, qty=1), OrderBookLevel(price=100.2, qty=1)),
    )
    assert book.best_bid == 99.9
    assert book.best_ask == 100.1
    assert book.spread == pytest.approx(0.2)
    assert book.mid_price == pytest.approx(100.0)


def test_orderbook_rejects_unsorted_bids():
    with pytest.raises(Exception):
        OrderBook(
            symbol="BTCUSDT",
            timestamp=0,
            bids=(OrderBookLevel(price=99.8, qty=1), OrderBookLevel(price=99.9, qty=1)),
            asks=(OrderBookLevel(price=100.1, qty=1),),
        )


def test_orderbook_rejects_unsorted_asks():
    with pytest.raises(Exception):
        OrderBook(
            symbol="BTCUSDT",
            timestamp=0,
            bids=(OrderBookLevel(price=99.9, qty=1),),
            asks=(OrderBookLevel(price=100.2, qty=1), OrderBookLevel(price=100.1, qty=1)),
        )


def test_orderbook_default_reliability_is_a():
    """Issue #3 review fix: a WS-maintained book is tier A; REST
    fallbacks must opt into tier B explicitly.
    """
    book = OrderBook(symbol="BTCUSDT", timestamp=0)
    assert book.reliability is DataReliability.A


def test_orderbook_can_be_tagged_tier_b_for_rest_fallback():
    """Adapters that fall back to a REST snapshot when the WS link is
    degraded must be able to tag the response tier B."""
    book = OrderBook(
        symbol="BTCUSDT", timestamp=0, reliability=DataReliability.B
    )
    assert book.reliability is DataReliability.B


def test_orderbook_empty_book_has_no_best_levels():
    book = OrderBook(symbol="X", timestamp=0)
    assert book.best_bid is None
    assert book.best_ask is None
    assert book.spread is None
    assert book.mid_price is None


# ---------------------------------------------------------------------------
# RecentTrade
# ---------------------------------------------------------------------------
def test_recent_trade_default_reliability_is_a():
    t = RecentTrade(
        symbol="BTCUSDT",
        trade_id="1",
        timestamp=0,
        price=100.0,
        qty=1.0,
        side=TradeSide.BUY,
    )
    assert t.reliability is DataReliability.A
    assert t.is_buyer_maker is False


# ---------------------------------------------------------------------------
# FundingRate / OpenInterest
# ---------------------------------------------------------------------------
def test_funding_rate_is_tier_b_by_default():
    f = FundingRate(symbol="BTCUSDT", timestamp=0, rate=0.0001, next_funding_ts=1)
    assert f.reliability is DataReliability.B


def test_open_interest_is_tier_b_by_default():
    oi = OpenInterest(symbol="BTCUSDT", timestamp=0, open_interest=10.0)
    assert oi.reliability is DataReliability.B


# ---------------------------------------------------------------------------
# AccountSnapshot
# ---------------------------------------------------------------------------
def test_account_snapshot_defaults():
    snap = AccountSnapshot(
        timestamp=0,
        total_equity=100.0,
        available_balance=80.0,
        margin_balance=20.0,
    )
    assert snap.unrealized_pnl == 0.0
    assert snap.open_position_count == 0
    assert snap.reliability is DataReliability.B
