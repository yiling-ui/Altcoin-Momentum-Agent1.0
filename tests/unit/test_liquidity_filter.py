"""Phase 5 - Liquidity Filter tests (Issue #5).

Acceptance criterion 1 (流动性不足时返回 reject) and the slippage / depth
/ spread / exit-time scoring is covered here.
The mandatory ``can_exit_position`` function has its own dedicated
test file (``test_can_exit_position.py``).
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
from app.liquidity import (
    LiquidityConfig,
    LiquidityDecision,
    LiquidityFilter,
    LiquidityInput,
    Side,
    estimate_book_walk,
    estimated_slippage_pct,
    walk_book_for_quote_notional,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _book(
    *,
    bids: list[tuple[float, float]] | None = None,
    asks: list[tuple[float, float]] | None = None,
    symbol: str = "BTCUSDT",
    timestamp: int = 1,
) -> OrderBook:
    bids = bids if bids is not None else [(100.0, 5.0), (99.9, 5.0), (99.8, 10.0)]
    asks = asks if asks is not None else [(100.1, 5.0), (100.2, 5.0), (100.3, 10.0)]
    return OrderBook(
        symbol=symbol,
        timestamp=timestamp,
        bids=tuple(OrderBookLevel(price=p, qty=q) for p, q in bids),
        asks=tuple(OrderBookLevel(price=p, qty=q) for p, q in asks),
    )


def _good_input(**overrides) -> LiquidityInput:
    base = dict(
        symbol="BTCUSDT",
        side=Side.LONG,
        planned_qty=1.0,
        last_price=100.0,
        spread_pct=0.0001,
        orderbook=_book(),
        volume_5m=10_000.0,
        is_data_degraded=False,
        market_regime=MarketRegime.MEME_RISK_ON,
        risk_permission=RiskPermission.ALLOW_ATTACK,
    )
    base.update(overrides)
    return LiquidityInput(**base)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def test_estimate_book_walk_long_consumes_asks():
    book = _book(asks=[(100.0, 1.0), (100.5, 1.0)])
    result = estimate_book_walk(book, qty=1.5, side="long")
    assert result.cleared_qty == pytest.approx(1.5)
    # VWAP = (1.0*100.0 + 0.5*100.5) / 1.5
    assert result.weighted_avg_fill_price == pytest.approx(
        (1.0 * 100.0 + 0.5 * 100.5) / 1.5
    )
    assert result.worst_fill_price == 100.5
    assert result.reference_price == 100.0
    assert result.slippage_pct == pytest.approx((100.5 - 100.0) / 100.0)
    assert result.exhausted is False


def test_estimate_book_walk_short_consumes_bids():
    book = _book(bids=[(100.0, 1.0), (99.5, 1.0)])
    result = estimate_book_walk(book, qty=1.5, side="short")
    assert result.cleared_qty == pytest.approx(1.5)
    assert result.worst_fill_price == 99.5
    assert result.reference_price == 100.0
    assert result.slippage_pct == pytest.approx((100.0 - 99.5) / 100.0)
    assert result.exhausted is False


def test_estimate_book_walk_exhausted_sets_flag():
    book = _book(asks=[(100.0, 0.5)])
    result = estimate_book_walk(book, qty=1.0, side="long")
    assert result.cleared_qty == 0.5
    assert result.exhausted is True


def test_estimate_book_walk_zero_qty_returns_zero_cleared():
    book = _book()
    result = estimate_book_walk(book, qty=0.0, side="long")
    assert result.cleared_qty == 0.0
    assert result.exhausted is True


def test_estimate_book_walk_empty_book_returns_exhausted():
    book = _book(asks=[])
    result = estimate_book_walk(book, qty=1.0, side="long")
    assert result.cleared_qty == 0.0
    assert result.weighted_avg_fill_price is None
    assert result.exhausted is True


def test_estimate_book_walk_rejects_unknown_side():
    book = _book()
    with pytest.raises(ValueError):
        estimate_book_walk(book, qty=1.0, side="WHATEVER")


def test_estimated_slippage_pct_helper_returns_same_value():
    book = _book(asks=[(100.0, 1.0), (100.5, 1.0)])
    walk = estimate_book_walk(book, qty=1.5, side="long")
    assert estimated_slippage_pct(book, qty=1.5, side="long") == pytest.approx(
        walk.slippage_pct
    )


def test_walk_book_for_quote_notional_long():
    book = _book(asks=[(100.0, 1.0), (100.5, 1.0)])
    result = walk_book_for_quote_notional(book, quote_notional=120.0, side="long")
    # 100.0 * 1.0 = 100 USDT consumed at level 1, then 20 USDT at level 2
    # -> 0.198... base qty cleared. Slippage > 0.
    assert result.cleared_qty > 1.0
    assert result.exhausted is False
    assert result.slippage_pct > 0.0


# ---------------------------------------------------------------------------
# LiquidityFilter.evaluate - happy path
# ---------------------------------------------------------------------------
def test_evaluate_passes_with_good_book(events_repo):
    f = LiquidityFilter(event_repo=events_repo)
    decision = f.evaluate(_good_input(planned_qty=0.001))
    assert isinstance(decision, LiquidityDecision)
    assert decision.passed is True
    assert decision.reject_reasons == ()
    assert decision.exit_plan is not None
    assert decision.exit_plan.feasible is True


# ---------------------------------------------------------------------------
# LiquidityFilter.evaluate - reject paths
# ---------------------------------------------------------------------------
def test_evaluate_rejects_when_book_missing(events_repo):
    f = LiquidityFilter(event_repo=events_repo)
    decision = f.evaluate(_good_input(orderbook=None))
    assert decision.passed is False
    assert LiquidityRejectReason.BOOK_MISSING in decision.reject_reasons


def test_evaluate_rejects_when_spread_too_wide(events_repo):
    f = LiquidityFilter(event_repo=events_repo)
    decision = f.evaluate(_good_input(spread_pct=0.05, planned_qty=0.001))
    assert decision.passed is False
    assert LiquidityRejectReason.SPREAD_TOO_WIDE in decision.reject_reasons


def test_evaluate_rejects_when_depth_insufficient(events_repo):
    f = LiquidityFilter(event_repo=events_repo)
    # Tiny book vs a planned qty 5x larger than its total depth.
    book = _book(asks=[(100.0, 0.5)], bids=[(99.99, 1.0), (99.95, 1.0)])
    decision = f.evaluate(
        _good_input(orderbook=book, planned_qty=10.0)
    )
    assert decision.passed is False
    assert LiquidityRejectReason.DEPTH_INSUFFICIENT in decision.reject_reasons
    assert LiquidityRejectReason.NO_EXIT_CHANNEL in decision.reject_reasons


def test_evaluate_rejects_when_slippage_too_high(events_repo):
    f = LiquidityFilter(
        config=LiquidityConfig(max_slippage_pct=0.0005),
        event_repo=events_repo,
    )
    book = _book(asks=[(100.0, 0.1), (105.0, 100.0)])
    decision = f.evaluate(
        _good_input(orderbook=book, planned_qty=1.0)
    )
    assert decision.passed is False
    assert LiquidityRejectReason.SLIPPAGE_TOO_HIGH in decision.reject_reasons


def test_evaluate_rejects_when_data_degraded(events_repo):
    """Phase 5 hard rule 4."""
    f = LiquidityFilter(event_repo=events_repo)
    decision = f.evaluate(_good_input(is_data_degraded=True, planned_qty=0.001))
    assert decision.passed is False
    assert LiquidityRejectReason.DATA_DEGRADED in decision.reject_reasons


def test_evaluate_rejects_when_regime_blocks(events_repo):
    """Phase 5 hard rule 1."""
    f = LiquidityFilter(event_repo=events_repo)
    decision = f.evaluate(
        _good_input(
            market_regime=MarketRegime.SYSTEMIC_RISK,
            risk_permission=RiskPermission.BLOCK_ALL,
            planned_qty=0.001,
        )
    )
    assert decision.passed is False
    assert LiquidityRejectReason.REGIME_BLOCKED in decision.reject_reasons


def test_evaluate_rejects_when_exit_too_slow(events_repo):
    f = LiquidityFilter(
        config=LiquidityConfig(max_exit_seconds=0.01),
        event_repo=events_repo,
    )
    decision = f.evaluate(_good_input(planned_qty=0.001, volume_5m=1.0))
    assert decision.passed is False
    assert LiquidityRejectReason.EXIT_TOO_SLOW in decision.reject_reasons


# ---------------------------------------------------------------------------
# Spread / depth scoring math
# ---------------------------------------------------------------------------
def test_spread_score_falls_to_zero_when_at_limit():
    f = LiquidityFilter(
        config=LiquidityConfig(max_spread_pct=0.001),
    )
    decision = f.evaluate(
        _good_input(spread_pct=0.001, planned_qty=0.001),
        emit_event=False,
    )
    # Spread exactly at the limit -> score 0 but not rejected.
    assert decision.spread_score == pytest.approx(0.0, abs=1e-9)


def test_depth_score_full_when_book_clears_5x_planned():
    f = LiquidityFilter(
        config=LiquidityConfig(min_depth_multiplier=5.0),
    )
    book = _book(
        asks=[(100.0, 100.0)], bids=[(99.99, 100.0)]
    )
    decision = f.evaluate(
        _good_input(orderbook=book, planned_qty=1.0),
        emit_event=False,
    )
    assert decision.depth_score == pytest.approx(1.0)


def test_depth_score_partial_when_book_clears_only_half():
    f = LiquidityFilter(
        config=LiquidityConfig(min_depth_multiplier=5.0),
    )
    book = _book(
        asks=[(100.0, 2.5)], bids=[(99.99, 100.0)]
    )
    decision = f.evaluate(
        _good_input(orderbook=book, planned_qty=1.0),
        emit_event=False,
    )
    # cleared 2.5 / required 5 -> score 0.5
    assert decision.depth_score == pytest.approx(0.5, abs=1e-9)


# ---------------------------------------------------------------------------
# Phase 5 hard rule 6: persisted as event
# ---------------------------------------------------------------------------
def test_evaluate_persists_one_liquidity_checked_event(events_repo):
    f = LiquidityFilter(event_repo=events_repo)
    f.evaluate(_good_input(planned_qty=0.001))
    events = events_repo.list_events(event_type=EventType.LIQUIDITY_CHECKED)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["check"] == "evaluate"
    assert payload["symbol"] == "BTCUSDT"
    assert payload["passed"] is True


def test_evaluate_reject_event_contains_reasons(events_repo):
    f = LiquidityFilter(event_repo=events_repo)
    f.evaluate(_good_input(spread_pct=0.05, planned_qty=0.001))
    events = events_repo.list_events(event_type=EventType.LIQUIDITY_CHECKED)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["passed"] is False
    assert (
        LiquidityRejectReason.SPREAD_TOO_WIDE.value in payload["reject_reasons"]
    )


def test_emit_event_false_skips_persistence(events_repo):
    f = LiquidityFilter(event_repo=events_repo)
    f.evaluate(_good_input(planned_qty=0.001), emit_event=False)
    assert events_repo.count_events(event_type=EventType.LIQUIDITY_CHECKED) == 0


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------
def test_counters_accumulate_across_calls(events_repo):
    f = LiquidityFilter(event_repo=events_repo)
    f.evaluate(_good_input(planned_qty=0.001))
    f.evaluate(_good_input(symbol="ETHUSDT", planned_qty=0.001))
    assert f.evaluations == 2
    assert f.liquidity_checked_events_emitted == 2
