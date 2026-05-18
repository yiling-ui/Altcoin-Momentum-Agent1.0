"""Phase 4 - OI / Funding / Liquidation snapshot tests."""

from __future__ import annotations

import pytest

from app.exchanges.models import FundingRate, OpenInterest
from app.market_data.funding import FundingSnapshotState
from app.market_data.liquidation import LiquidationFeedState
from app.market_data.models import LiquidationEvent, LiquidationSide
from app.market_data.oi import OpenInterestSnapshotState


T0 = 1_779_062_400_000


# ---------------------------------------------------------------------------
# OI
# ---------------------------------------------------------------------------
def test_open_interest_snapshot_initial_state():
    st = OpenInterestSnapshotState(symbol="BTCUSDT")
    assert st.latest is None
    assert st.previous is None
    assert st.last_update_ts is None
    assert st.delta() is None
    assert st.percent_change() is None


def test_open_interest_snapshot_update_advances_previous():
    st = OpenInterestSnapshotState(symbol="BTCUSDT")
    a = OpenInterest(symbol="BTCUSDT", timestamp=T0, open_interest=1000.0)
    b = OpenInterest(symbol="BTCUSDT", timestamp=T0 + 60_000, open_interest=1100.0)
    assert st.update(a) is True
    assert st.latest == a
    assert st.update(b) is True
    assert st.latest == b
    assert st.previous == a
    assert st.delta() == pytest.approx(100.0)
    assert st.percent_change() == pytest.approx(0.1)


def test_open_interest_snapshot_rejects_out_of_order():
    st = OpenInterestSnapshotState(symbol="BTCUSDT")
    a = OpenInterest(symbol="BTCUSDT", timestamp=T0 + 60_000, open_interest=1100.0)
    b = OpenInterest(symbol="BTCUSDT", timestamp=T0, open_interest=999.0)
    st.update(a)
    assert st.update(b) is False
    assert st.latest == a
    assert st.previous is None


def test_open_interest_snapshot_rejects_other_symbol():
    st = OpenInterestSnapshotState(symbol="BTCUSDT")
    bad = OpenInterest(symbol="ETHUSDT", timestamp=T0, open_interest=1.0)
    with pytest.raises(ValueError):
        st.update(bad)


def test_open_interest_percent_change_handles_zero_baseline():
    st = OpenInterestSnapshotState(symbol="BTCUSDT")
    st.update(OpenInterest(symbol="BTCUSDT", timestamp=T0, open_interest=0.0))
    st.update(OpenInterest(symbol="BTCUSDT", timestamp=T0 + 1, open_interest=10.0))
    assert st.percent_change() is None  # division-by-zero guard


# ---------------------------------------------------------------------------
# Funding
# ---------------------------------------------------------------------------
def test_funding_snapshot_initial_state():
    st = FundingSnapshotState(symbol="BTCUSDT")
    assert st.latest is None
    assert st.delta() is None


def test_funding_snapshot_update_advances_previous():
    st = FundingSnapshotState(symbol="BTCUSDT")
    a = FundingRate(symbol="BTCUSDT", timestamp=T0, rate=0.0001, next_funding_ts=T0 + 1)
    b = FundingRate(
        symbol="BTCUSDT", timestamp=T0 + 60_000, rate=0.0002, next_funding_ts=T0 + 2
    )
    st.update(a)
    st.update(b)
    assert st.latest == b
    assert st.previous == a
    assert st.delta() == pytest.approx(0.0001)


def test_funding_snapshot_rejects_other_symbol():
    st = FundingSnapshotState(symbol="BTCUSDT")
    bad = FundingRate(
        symbol="ETHUSDT", timestamp=T0, rate=0.0, next_funding_ts=T0 + 1
    )
    with pytest.raises(ValueError):
        st.update(bad)


# ---------------------------------------------------------------------------
# Liquidations
# ---------------------------------------------------------------------------
def test_liquidation_feed_capacity_evicts_oldest():
    feed = LiquidationFeedState(symbol="PEPEUSDT", capacity=3)
    for i in range(5):
        feed.push(
            LiquidationEvent(
                symbol="PEPEUSDT",
                timestamp=T0 + i,
                side=LiquidationSide.LONG,
                price=1.0,
                qty=1.0 + i,
            )
        )
    assert len(feed) == 3
    qtys = [e.qty for e in feed.history]
    assert qtys == [3.0, 4.0, 5.0]


def test_liquidation_feed_recent_filters_by_ts():
    feed = LiquidationFeedState(symbol="PEPEUSDT")
    for i in range(5):
        feed.push(
            LiquidationEvent(
                symbol="PEPEUSDT",
                timestamp=T0 + i * 1000,
                side=LiquidationSide.SHORT,
                price=1.0,
                qty=1.0,
            )
        )
    out = feed.recent(since_ts=T0 + 3000)
    assert [e.timestamp for e in out] == [T0 + 3000, T0 + 4000]


def test_liquidation_feed_rejects_other_symbol():
    feed = LiquidationFeedState(symbol="PEPEUSDT")
    bad = LiquidationEvent(
        symbol="BTCUSDT",
        timestamp=T0,
        side=LiquidationSide.LONG,
        price=1.0,
        qty=1.0,
    )
    with pytest.raises(ValueError):
        feed.push(bad)


def test_liquidation_feed_capacity_must_be_positive():
    with pytest.raises(ValueError):
        LiquidationFeedState(symbol="X", capacity=0)
