"""Phase 5 - can_exit_position tests (Issue #5 acceptance criterion 3).

Spec §19.2 mandates a function

    can_exit_position(symbol, qty, max_slippage_pct, max_seconds)

that returns whether a position of size ``qty`` can be flattened
within ``max_seconds`` at <= ``max_slippage_pct``.

This file covers:
  - True path: book has enough depth, slippage within limit, throughput
    fast enough.
  - False path: book exhausted (no exit channel) -> NO_EXIT_CHANNEL.
  - False path: slippage exceeds max -> SLIPPAGE_TOO_HIGH.
  - False path: throughput too low for max_seconds -> EXIT_TOO_SLOW.
  - False path: data degraded -> DATA_DEGRADED.
  - False path: regime BLOCK_ALL -> REGIME_BLOCKED.
  - False path: book missing -> BOOK_MISSING.
  - SHORT side walks bids (sell back into the book).
  - The free function ``app.liquidity.can_exit_position`` mirrors
    the LiquidityFilter method.
  - LIQUIDITY_CHECKED event tagging on emit.
"""

from __future__ import annotations

import pytest

from app.core.enums import (
    LiquidityRejectReason,
    MarketRegime,
    RiskPermission,
)
from app.core.events import EventType
from app.exchanges.models import OrderBook, OrderBookLevel
from app.liquidity import LiquidityFilter, Side
from app.liquidity.filter import can_exit_position as can_exit_position_fn


def _book(*, bids=None, asks=None) -> OrderBook:
    bids = bids if bids is not None else [(100.0, 5.0), (99.9, 5.0), (99.8, 10.0)]
    asks = asks if asks is not None else [(100.1, 5.0), (100.2, 5.0), (100.3, 10.0)]
    return OrderBook(
        symbol="BTCUSDT",
        timestamp=1,
        bids=tuple(OrderBookLevel(price=p, qty=q) for p, q in bids),
        asks=tuple(OrderBookLevel(price=p, qty=q) for p, q in asks),
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_can_exit_position_returns_feasible_for_a_well_formed_book(events_repo):
    f = LiquidityFilter(event_repo=events_repo)
    plan = f.can_exit_position(
        "BTCUSDT",
        qty=0.5,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        side=Side.LONG,
        orderbook=_book(),
        volume_5m=10_000.0,
    )
    assert plan.feasible is True
    assert plan.reject_reasons == ()
    assert plan.cleared_qty == pytest.approx(0.5)
    assert plan.estimated_slippage_pct is not None
    assert plan.estimated_slippage_pct <= 0.01
    assert plan.estimated_exit_seconds is not None
    assert plan.estimated_exit_seconds <= 60.0


# ---------------------------------------------------------------------------
# False path: book exhausted -> NO_EXIT_CHANNEL
# ---------------------------------------------------------------------------
def test_can_exit_position_rejects_when_book_exhausted():
    f = LiquidityFilter()
    plan = f.can_exit_position(
        "BTCUSDT",
        qty=10.0,
        max_slippage_pct=0.10,
        max_seconds=600.0,
        side=Side.LONG,
        orderbook=_book(asks=[(100.0, 0.5)]),
        volume_5m=10_000.0,
        emit_event=False,
    )
    assert plan.feasible is False
    assert LiquidityRejectReason.NO_EXIT_CHANNEL in plan.reject_reasons
    assert plan.cleared_qty == 0.5


# ---------------------------------------------------------------------------
# False path: slippage too high -> SLIPPAGE_TOO_HIGH
# ---------------------------------------------------------------------------
def test_can_exit_position_rejects_when_slippage_too_high():
    f = LiquidityFilter()
    plan = f.can_exit_position(
        "BTCUSDT",
        qty=1.0,
        max_slippage_pct=0.0001,  # extremely tight ceiling
        max_seconds=60.0,
        side=Side.LONG,
        orderbook=_book(asks=[(100.0, 0.1), (105.0, 100.0)]),
        volume_5m=10_000.0,
        emit_event=False,
    )
    assert plan.feasible is False
    assert LiquidityRejectReason.SLIPPAGE_TOO_HIGH in plan.reject_reasons


# ---------------------------------------------------------------------------
# False path: throughput too low -> EXIT_TOO_SLOW
# ---------------------------------------------------------------------------
def test_can_exit_position_rejects_when_max_seconds_too_short():
    f = LiquidityFilter()
    plan = f.can_exit_position(
        "BTCUSDT",
        qty=1.0,
        max_slippage_pct=0.10,
        max_seconds=0.001,  # impossible window
        side=Side.LONG,
        orderbook=_book(),
        volume_5m=10_000.0,
        emit_event=False,
    )
    assert plan.feasible is False
    assert LiquidityRejectReason.EXIT_TOO_SLOW in plan.reject_reasons


def test_can_exit_position_uses_throughput_qty_per_sec_override():
    f = LiquidityFilter()
    # 1 qty / 0.1 qty per sec = 10 sec, well under 60.
    plan = f.can_exit_position(
        "BTCUSDT",
        qty=1.0,
        max_slippage_pct=0.10,
        max_seconds=60.0,
        side=Side.LONG,
        orderbook=_book(),
        throughput_qty_per_sec=0.1,
        emit_event=False,
    )
    assert plan.feasible is True
    assert plan.estimated_exit_seconds == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# False path: data degraded -> DATA_DEGRADED
# ---------------------------------------------------------------------------
def test_can_exit_position_rejects_when_data_degraded():
    f = LiquidityFilter()
    plan = f.can_exit_position(
        "BTCUSDT",
        qty=0.5,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        side=Side.LONG,
        orderbook=_book(),
        volume_5m=10_000.0,
        is_data_degraded=True,
        emit_event=False,
    )
    assert plan.feasible is False
    assert LiquidityRejectReason.DATA_DEGRADED in plan.reject_reasons


# ---------------------------------------------------------------------------
# False path: regime block -> REGIME_BLOCKED
# ---------------------------------------------------------------------------
def test_can_exit_position_rejects_when_regime_blocks():
    f = LiquidityFilter()
    plan = f.can_exit_position(
        "BTCUSDT",
        qty=0.5,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        side=Side.LONG,
        orderbook=_book(),
        volume_5m=10_000.0,
        risk_permission=RiskPermission.BLOCK_ALL,
        market_regime=MarketRegime.SYSTEMIC_RISK,
        emit_event=False,
    )
    assert plan.feasible is False
    assert LiquidityRejectReason.REGIME_BLOCKED in plan.reject_reasons


# ---------------------------------------------------------------------------
# False path: book missing -> BOOK_MISSING
# ---------------------------------------------------------------------------
def test_can_exit_position_rejects_when_book_missing():
    f = LiquidityFilter()
    plan = f.can_exit_position(
        "BTCUSDT",
        qty=0.5,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        side=Side.LONG,
        orderbook=None,
        volume_5m=10_000.0,
        emit_event=False,
    )
    assert plan.feasible is False
    assert LiquidityRejectReason.BOOK_MISSING in plan.reject_reasons
    assert plan.cleared_qty == 0.0


# ---------------------------------------------------------------------------
# SHORT side walks bids
# ---------------------------------------------------------------------------
def test_short_side_walks_bids():
    f = LiquidityFilter()
    plan = f.can_exit_position(
        "BTCUSDT",
        qty=1.0,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        side=Side.SHORT,
        orderbook=_book(),
        volume_5m=10_000.0,
        emit_event=False,
    )
    # Default _book has 5+5+10 bid qty, so 1.0 short clears at the
    # best bid only with no slippage.
    assert plan.feasible is True
    assert plan.weighted_avg_fill_price == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Free function alias
# ---------------------------------------------------------------------------
def test_module_level_can_exit_position_matches_method():
    plan = can_exit_position_fn(
        "BTCUSDT",
        qty=0.5,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        orderbook=_book(),
        side=Side.LONG,
        volume_5m=10_000.0,
        emit_event=False,
    )
    assert plan.feasible is True


# ---------------------------------------------------------------------------
# Phase 5 hard rule 6: persisted as LIQUIDITY_CHECKED event with the
# can_exit_position tag.
# ---------------------------------------------------------------------------
def test_can_exit_position_persists_as_liquidity_checked_event(events_repo):
    f = LiquidityFilter(event_repo=events_repo)
    f.can_exit_position(
        "BTCUSDT",
        qty=0.5,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        side=Side.LONG,
        orderbook=_book(),
        volume_5m=10_000.0,
    )
    events = events_repo.list_events(event_type=EventType.LIQUIDITY_CHECKED)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["check"] == "can_exit_position"
    assert payload["feasible"] is True
    assert payload["max_slippage_pct"] == 0.01
    assert payload["max_seconds"] == 60.0
    assert payload["side"] == "long"
    assert payload["qty"] == 0.5


def test_can_exit_position_emit_event_false_skips_persistence(events_repo):
    f = LiquidityFilter(event_repo=events_repo)
    f.can_exit_position(
        "BTCUSDT",
        qty=0.5,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        side=Side.LONG,
        orderbook=_book(),
        volume_5m=10_000.0,
        emit_event=False,
    )
    assert events_repo.count_events(event_type=EventType.LIQUIDITY_CHECKED) == 0


# ---------------------------------------------------------------------------
# Zero qty -> trivially feasible (no exit needed).
# ---------------------------------------------------------------------------
def test_can_exit_position_zero_qty_is_trivially_feasible():
    f = LiquidityFilter()
    plan = f.can_exit_position(
        "BTCUSDT",
        qty=0.0,
        max_slippage_pct=0.01,
        max_seconds=60.0,
        side=Side.LONG,
        orderbook=_book(),
        volume_5m=10_000.0,
        emit_event=False,
    )
    assert plan.feasible is True
    assert plan.estimated_exit_seconds == pytest.approx(0.0)
    assert plan.reject_reasons == ()
