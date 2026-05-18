"""ATR calculation.

Phase 4 - Issue #4 §"ATR calculation". Implements Wilder's True Range
and an SMA-based Average True Range over closed bars. Two SMA-based
approximations are good enough for Phase 4 because the buffer is
deterministic: ATR enters Spec §18 (anomaly scoring) and Spec §27
(stop-distance sizing), and both consumers will replace this with a
properly-warmed Wilder smoother once Issue #6 / #7 land.

ATR is undefined for fewer than two closed bars; we return ``None`` in
that case rather than zero, so callers can distinguish "no signal" from
"a real zero".
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.market_data.models import Bar


def true_range(bar: Bar, prev_close: float | None) -> float:
    """Wilder's True Range for a single closed bar.

    With no previous close (i.e. the very first bar in the window) the
    True Range collapses to ``high - low``.
    """
    high_low = bar.high - bar.low
    if prev_close is None:
        return high_low
    return max(
        high_low,
        abs(bar.high - prev_close),
        abs(bar.low - prev_close),
    )


def compute_atr(bars: Sequence[Bar], *, window: int = 14) -> float | None:
    """SMA-of-True-Range over the last ``window`` *closed* bars.

    Returns ``None`` when fewer than two closed bars are available, or
    when the window is non-positive. We use SMA-of-TR, not Wilder's EMA,
    because Phase 4 does not yet need a warm-up sequence: the No-Trade
    Gate readers compare ATR(window) against itself across symbols, and
    SMA is robust enough for that comparison.
    """
    if window <= 0:
        return None
    closed = [b for b in bars if b.closed]
    if len(closed) < 2:
        return None
    take = closed[-window:]
    trs: list[float] = []
    prev_close: float | None = None
    # We need the close BEFORE the first bar in the window to compute
    # TR(window[0]). If we have history, use it.
    if len(closed) > len(take):
        prev_close = closed[-len(take) - 1].close
    for bar in take:
        trs.append(true_range(bar, prev_close))
        prev_close = bar.close
    if not trs:
        return None
    return sum(trs) / len(trs)


def compute_true_ranges(bars: Iterable[Bar]) -> list[float]:
    """Helper exposed for tests: TR(b_i) for each bar in order."""
    out: list[float] = []
    prev_close: float | None = None
    for bar in bars:
        out.append(true_range(bar, prev_close))
        prev_close = bar.close
    return out
