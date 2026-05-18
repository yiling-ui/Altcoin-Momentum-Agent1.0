"""Phase 4 - CVD calculator tests (Issue #4 acceptance criterion 1)."""

from __future__ import annotations

import pytest

from app.exchanges.models import RecentTrade, TradeSide
from app.market_data.cvd import compute_cvd, signed_volume


T0 = 1_779_062_400_000


def buy_taker(qty: float, ts: int = T0) -> RecentTrade:
    """Aggressor was a buyer -> +qty."""
    return RecentTrade(
        symbol="BTCUSDT",
        trade_id=f"buy-{ts}-{qty}",
        timestamp=ts,
        price=100.0,
        qty=qty,
        side=TradeSide.BUY,
        is_buyer_maker=False,
    )


def sell_taker(qty: float, ts: int = T0) -> RecentTrade:
    """Aggressor was a seller -> -qty."""
    return RecentTrade(
        symbol="BTCUSDT",
        trade_id=f"sell-{ts}-{qty}",
        timestamp=ts,
        price=100.0,
        qty=qty,
        side=TradeSide.SELL,
        is_buyer_maker=True,
    )


def test_signed_volume_for_buy_taker_is_positive():
    assert signed_volume(buy_taker(1.5)) == pytest.approx(1.5)


def test_signed_volume_for_sell_taker_is_negative():
    assert signed_volume(sell_taker(2.5)) == pytest.approx(-2.5)


def test_compute_cvd_empty_is_zero():
    assert compute_cvd([]) == 0.0


def test_compute_cvd_buys_minus_sells():
    trades = [buy_taker(1.0), sell_taker(0.5), buy_taker(2.0), sell_taker(2.0)]
    # +1 - 0.5 + 2 - 2 = 0.5
    assert compute_cvd(trades) == pytest.approx(0.5)


def test_compute_cvd_pure_buys():
    assert compute_cvd([buy_taker(1.0), buy_taker(2.0)]) == pytest.approx(3.0)


def test_compute_cvd_pure_sells():
    assert compute_cvd([sell_taker(1.0), sell_taker(2.0)]) == pytest.approx(-3.0)


def test_acceptance_criterion_1_mock_trades_compute_cvd():
    """Issue #4 acceptance criterion 1: 'given mock trades, compute CVD'."""
    # 30 buys of 0.1, 10 sells of 0.5 -> CVD = 30*0.1 - 10*0.5 = -2.0
    trades: list[RecentTrade] = []
    for i in range(30):
        trades.append(buy_taker(0.1, ts=T0 + i * 1000))
    for i in range(10):
        trades.append(sell_taker(0.5, ts=T0 + 30_000 + i * 1000))
    assert compute_cvd(trades) == pytest.approx(-2.0)
