"""Phase 4 - ATR tests (Issue #4 acceptance criterion 2)."""

from __future__ import annotations

import pytest

from app.market_data.atr import compute_atr, compute_true_ranges, true_range
from app.market_data.models import Bar, BarInterval


T0 = 1_779_062_400_000


def make_bar(*, idx: int, open_: float, high: float, low: float, close: float) -> Bar:
    open_ts = T0 + idx * 60_000
    return Bar(
        symbol="BTCUSDT",
        interval=BarInterval.M1,
        open_ts=open_ts,
        close_ts=open_ts + 60_000,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1.0,
        closed=True,
    )


def test_true_range_with_no_prev_close_is_high_low():
    bar = make_bar(idx=0, open_=100, high=105, low=95, close=102)
    assert true_range(bar, prev_close=None) == 10.0


def test_true_range_uses_max_of_three_components():
    # high-low = 5, |high - prev_close| = 8, |low - prev_close| = 3 -> 8
    bar = make_bar(idx=1, open_=100, high=110, low=105, close=108)
    assert true_range(bar, prev_close=102) == 8.0


def test_compute_atr_returns_none_for_too_few_bars():
    assert compute_atr([], window=14) is None
    one = [make_bar(idx=0, open_=100, high=105, low=95, close=102)]
    assert compute_atr(one, window=14) is None


def test_compute_atr_returns_none_for_zero_window():
    bars = [
        make_bar(idx=i, open_=100, high=101, low=99, close=100) for i in range(5)
    ]
    assert compute_atr(bars, window=0) is None


def test_compute_atr_simple_average():
    bars = [
        make_bar(idx=0, open_=100, high=105, low=95, close=102),
        make_bar(idx=1, open_=102, high=110, low=101, close=108),
        make_bar(idx=2, open_=108, high=112, low=106, close=110),
    ]
    # TR(0) = 10, TR(1) = max(9, 8, 1) = 9, TR(2) = max(6, 4, 2) = 6.
    trs = compute_true_ranges(bars)
    assert trs == pytest.approx([10.0, 9.0, 6.0])
    # SMA(window=3) over closed bars uses TR for each bar in the window
    # with prev_close = closed[-window-1].close. Here we have only 3
    # bars, so prev_close is None for the first.
    assert compute_atr(bars, window=3) == pytest.approx(
        sum([10.0, 9.0, 6.0]) / 3
    )


def test_compute_atr_uses_history_for_window_prev_close():
    """When the window is smaller than the number of available bars,
    the bar BEFORE the window should be used as ``prev_close`` for the
    first bar in the window.
    """
    bars = [
        make_bar(idx=0, open_=100, high=101, low=99, close=100),
        make_bar(idx=1, open_=100, high=102, low=98, close=101),
        make_bar(idx=2, open_=101, high=110, low=100, close=108),
    ]
    # With window=2, take last 2 bars; prev_close before window = bars[0].close = 100
    # TR(bars[1]) = max(4, |102-100|, |98-100|) = max(4, 2, 2) = 4
    # TR(bars[2]) = max(10, |110-101|, |100-101|) = max(10, 9, 1) = 10
    # ATR(2) = (4 + 10) / 2 = 7.0
    assert compute_atr(bars, window=2) == pytest.approx(7.0)


def test_compute_atr_skips_unclosed_bars():
    closed = make_bar(idx=0, open_=100, high=110, low=90, close=95)
    live = make_bar(idx=1, open_=95, high=200, low=10, close=100).model_copy(
        update={"closed": False}
    )
    assert compute_atr([closed, live], window=2) is None


def test_acceptance_criterion_2_mock_candles_compute_atr():
    """Issue #4 acceptance criterion 2: 'given mock candles, compute ATR'."""
    bars = [
        make_bar(idx=i, open_=100, high=100 + i, low=100 - i, close=100)
        for i in range(15)
    ]
    atr = compute_atr(bars, window=14)
    assert atr is not None
    assert atr > 0
