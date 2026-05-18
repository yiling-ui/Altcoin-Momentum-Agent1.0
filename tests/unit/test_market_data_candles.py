"""Phase 4 - CandleBuilder tests."""

from __future__ import annotations

import pytest

from app.exchanges.models import RecentTrade, TradeSide
from app.market_data.candles import CandleBuilder, bucket_start_ms
from app.market_data.models import BarInterval


# 2026-05-18T00:00:00Z in ms; arbitrary deterministic anchor.
T0 = 1_779_062_400_000


def trade(
    *,
    ts: int,
    price: float,
    qty: float,
    side: TradeSide = TradeSide.BUY,
    is_buyer_maker: bool = False,
    symbol: str = "BTCUSDT",
    trade_id: str | None = None,
) -> RecentTrade:
    return RecentTrade(
        symbol=symbol,
        trade_id=trade_id or f"t-{ts}",
        timestamp=ts,
        price=price,
        qty=qty,
        side=side,
        is_buyer_maker=is_buyer_maker,
    )


def test_bucket_start_ms_aligns_to_minute():
    width = BarInterval.M1.width_ms
    assert bucket_start_ms(T0, width_ms=width) == T0
    assert bucket_start_ms(T0 + 5_000, width_ms=width) == T0
    assert bucket_start_ms(T0 + 60_000, width_ms=width) == T0 + 60_000
    assert bucket_start_ms(T0 + 60_001, width_ms=width) == T0 + 60_000


def test_bucket_start_ms_rejects_negative():
    with pytest.raises(ValueError):
        bucket_start_ms(-1, width_ms=60_000)
    with pytest.raises(ValueError):
        bucket_start_ms(0, width_ms=0)


def test_first_trade_opens_live_bar():
    cb = CandleBuilder("BTCUSDT", interval=BarInterval.M1)
    closed = cb.feed(trade(ts=T0 + 1_000, price=100.0, qty=2.0))
    assert closed is None
    live = cb.live_bar
    assert live is not None
    assert live.open_ts == T0
    assert live.close_ts == T0 + 60_000
    assert live.open == live.high == live.low == live.close == 100.0
    assert live.volume == 2.0
    assert live.trade_count == 1
    assert live.closed is False


def test_same_bucket_updates_in_place():
    cb = CandleBuilder("BTCUSDT", interval=BarInterval.M1)
    cb.feed(trade(ts=T0 + 1_000, price=100.0, qty=1.0))
    cb.feed(trade(ts=T0 + 5_000, price=99.5, qty=2.0))
    cb.feed(trade(ts=T0 + 30_000, price=101.0, qty=0.5))
    live = cb.live_bar
    assert live is not None
    assert live.open == 100.0
    assert live.high == 101.0
    assert live.low == 99.5
    assert live.close == 101.0
    assert live.volume == 3.5
    assert live.trade_count == 3


def test_new_bucket_closes_previous():
    cb = CandleBuilder("BTCUSDT", interval=BarInterval.M1)
    cb.feed(trade(ts=T0 + 1_000, price=100.0, qty=1.0))
    closed = cb.feed(trade(ts=T0 + 60_500, price=102.0, qty=2.0))
    assert closed is not None
    assert closed.closed is True
    assert closed.open_ts == T0
    assert closed.close == 100.0
    live = cb.live_bar
    assert live is not None
    assert live.open_ts == T0 + 60_000
    assert live.open == 102.0


def test_gap_filled_with_flat_synthetic_bars():
    """A 3-minute gap between the first and second trade should leave
    two flat bars between them so ATR doesn't see a missing slot."""
    cb = CandleBuilder("BTCUSDT", interval=BarInterval.M1)
    cb.feed(trade(ts=T0 + 1_000, price=100.0, qty=1.0))
    cb.feed(trade(ts=T0 + 3 * 60_000 + 5_000, price=120.0, qty=2.0))
    closed = cb.closed_bars
    # Three closed bars: the original plus 2 flat fillers.
    assert len(closed) == 3
    assert closed[0].close == 100.0
    assert closed[1].open == closed[1].close == 100.0  # flat
    assert closed[1].volume == 0.0
    assert closed[2].open == closed[2].close == 100.0  # flat
    assert closed[2].volume == 0.0
    # Live bar opened at minute 3 with the new trade.
    assert cb.live_bar is not None
    assert cb.live_bar.open_ts == T0 + 3 * 60_000
    assert cb.live_bar.open == 120.0


def test_late_trade_is_dropped_not_back_filled():
    cb = CandleBuilder("BTCUSDT", interval=BarInterval.M1)
    cb.feed(trade(ts=T0 + 1_000, price=100.0, qty=1.0))
    cb.feed(trade(ts=T0 + 60_500, price=102.0, qty=2.0))  # closes bar 0
    out = cb.feed(trade(ts=T0 + 30_000, price=999.0, qty=999.0))  # late
    assert out is None
    assert cb.dropped_late_trades == 1
    assert cb.closed_bars[0].close == 100.0  # unchanged


def test_buy_sell_volume_split_via_is_buyer_maker():
    cb = CandleBuilder("BTCUSDT", interval=BarInterval.M1)
    cb.feed(trade(ts=T0, price=100.0, qty=1.0, is_buyer_maker=False))  # BUY taker
    cb.feed(trade(ts=T0 + 1_000, price=100.0, qty=2.0, is_buyer_maker=True))  # SELL taker
    live = cb.live_bar
    assert live is not None
    assert live.buy_volume == pytest.approx(1.0)
    assert live.sell_volume == pytest.approx(2.0)


def test_buy_sell_volume_falls_back_to_side_when_is_buyer_maker_unset():
    cb = CandleBuilder("BTCUSDT", interval=BarInterval.M1)
    cb.feed(
        trade(
            ts=T0,
            price=100.0,
            qty=1.0,
            side=TradeSide.SELL,
            is_buyer_maker=False,  # default; mock fixtures sometimes do this
        )
    )
    live = cb.live_bar
    assert live is not None
    # Honour ``side`` when ``is_buyer_maker`` is the default False.
    assert live.sell_volume == pytest.approx(1.0)
    assert live.buy_volume == pytest.approx(0.0)


def test_force_close_pads_with_flat_bars():
    cb = CandleBuilder("BTCUSDT", interval=BarInterval.M1)
    cb.feed(trade(ts=T0 + 1_000, price=100.0, qty=1.0))
    cb.force_close(at_ts=T0 + 3 * 60_000)
    closed = cb.closed_bars
    assert len(closed) == 3
    assert all(b.closed for b in closed)
    assert all(b.close == 100.0 for b in closed)
    assert cb.live_bar is None


def test_history_bound_evicts_oldest():
    cb = CandleBuilder("BTCUSDT", interval=BarInterval.M1, history=3)
    for i in range(6):
        cb.feed(trade(ts=T0 + i * 60_000 + 1_000, price=100.0 + i, qty=1.0))
    # Force close the live bar so we have 6 closed in total but
    # history capped at 3.
    cb.force_close()
    assert len(cb.closed_bars) == 3


def test_wrong_symbol_rejected():
    cb = CandleBuilder("BTCUSDT", interval=BarInterval.M1)
    with pytest.raises(ValueError):
        cb.feed(trade(ts=T0, price=1.0, qty=1.0, symbol="ETHUSDT"))
