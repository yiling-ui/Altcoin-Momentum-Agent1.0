"""Cumulative Volume Delta (CVD) calculator.

Phase 4 - Issue #4 §"CVD calculator". CVD is the running sum of signed
taker volume:

    + buy-side volume     when the aggressor is a buyer
    - sell-side volume    when the aggressor is a seller

Spec §14 / §18 / §20 use the 1-minute, 5-minute and 15-minute CVD as
inputs to the anomaly scanner, the Real Trade Confirmation engine and
the Manipulation Detector. We deliberately keep the calculator pure so
that the same function works inside the live Buffer and inside the
Replay Engine (Issue #10).
"""

from __future__ import annotations

from collections.abc import Iterable

from app.exchanges.models import RecentTrade
from app.market_data.candles import _split_volume


def signed_volume(trade: RecentTrade) -> float:
    """Return the signed taker volume of a trade."""
    buy_vol, sell_vol = _split_volume(trade)
    return buy_vol - sell_vol


def compute_cvd(trades: Iterable[RecentTrade]) -> float:
    """Sum the signed taker volume across the iterable.

    Empty iterable returns 0.0. The caller is responsible for filtering
    by symbol or by time window before passing the trades in.
    """
    total = 0.0
    for tr in trades:
        total += signed_volume(tr)
    return total
