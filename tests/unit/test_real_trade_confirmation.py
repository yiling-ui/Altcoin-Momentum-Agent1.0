"""Phase 6 - RealTradeConfirmation tests (Issue #6, Spec §20).

The Issue #6 acceptance criterion 1 lives here: mock data MUST be
able to trigger T3.
"""

from __future__ import annotations

from app.confirmation import (
    ConfirmationBarSummary,
    ConfirmationConfig,
    ConfirmationDecision,
    ConfirmationInput,
    RealTradeConfirmation,
)
from app.core.enums import (
    ConfirmationReasonTag,
    MarketRegime,
    RiskPermission,
    TradeConfirmationLevel,
)
from app.core.events import EventType


def _bar(
    open_=1.0,
    high=1.0,
    low=1.0,
    close=1.0,
    volume=10.0,
    buy_volume=5.0,
    sell_volume=5.0,
    trade_count=10,
):
    return ConfirmationBarSummary(
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        buy_volume=buy_volume,
        sell_volume=sell_volume,
        trade_count=trade_count,
    )


def _t3_input(**overrides):
    """Mock data calibrated to fire 3 signals -> T3."""
    bars = (
        _bar(open_=1.00, high=1.02, low=0.99, close=1.01),
        _bar(open_=1.01, high=1.03, low=1.005, close=1.02),
        _bar(open_=1.02, high=1.04, low=1.015, close=1.03),
    )
    base = dict(
        symbol="PEPEUSDT",
        timestamp=1_700_000_000_000,
        last_price=1.04,
        prev_close_price=1.03,
        cvd_1m=30.0,
        cvd_5m=50.0,
        volume_1m=120.0,
        volume_5m=400.0,
        return_pct_1m=0.01,  # +1%
        return_pct_5m=0.04,
        breakout_level=1.005,  # all 3 bars close above
        last_n_closed_bars=bars,
        # Below the large-trade threshold (1.0) so T3 is exactly
        # 3 signals: cvd-price + breakout-hold + volume-up-price-move.
        largest_trade_qty_1m=0.5,
        historical_efficiency_mean=None,  # disable to keep T3 deterministic
    )
    base.update(overrides)
    return ConfirmationInput(**base)


def _t4_input():
    """4+ signals -> T4: T3 base PLUS trade-efficiency-high."""
    bars = (
        _bar(open_=1.00, high=1.02, low=0.99, close=1.01),
        _bar(open_=1.01, high=1.03, low=1.005, close=1.02),
        _bar(open_=1.02, high=1.04, low=1.015, close=1.03),
    )
    return ConfirmationInput(
        symbol="PEPEUSDT",
        timestamp=1_700_000_000_000,
        last_price=1.04,
        prev_close_price=1.03,
        cvd_1m=30.0,
        cvd_5m=50.0,
        volume_1m=120.0,
        volume_5m=400.0,
        return_pct_1m=0.01,
        return_pct_5m=0.04,
        breakout_level=1.005,
        last_n_closed_bars=bars,
        largest_trade_qty_1m=2.0,
        # current_eff = 0.01 / 120 = 8.33e-5; mean = 5e-5 -> ratio 1.66x.
        historical_efficiency_mean=5e-5,
    )


# ---------------------------------------------------------------------------
# Output shape + Issue #6 acceptance criterion 1: T3 from mock data
# ---------------------------------------------------------------------------
def test_decision_is_frozen_value_object():
    d = ConfirmationDecision(
        symbol="X",
        level=TradeConfirmationLevel.T0,
        fired_signals=0,
        reason_tags=(),
        notes=(),
        timestamp=1,
    )
    try:
        d.symbol = "Y"
    except Exception:  # pragma: no cover - frozen
        pass
    else:  # pragma: no cover - should not happen
        raise AssertionError("ConfirmationDecision must be frozen")


def test_mock_input_triggers_t3():
    """Issue #6 acceptance criterion 1: 'mock 数据能触发 T3'."""
    d = RealTradeConfirmation().evaluate(_t3_input())
    assert d.level is TradeConfirmationLevel.T3, (
        f"expected T3 with 3 fired signals, got {d.level} fired={d.fired_signals}"
        f" tags={d.reason_tags}"
    )
    assert d.fired_signals == 3
    # The three signals must be the Spec §20.4 T3 example set.
    assert ConfirmationReasonTag.CVD_PRICE_AGREEMENT in d.reason_tags
    assert ConfirmationReasonTag.BREAKOUT_HELD in d.reason_tags
    assert ConfirmationReasonTag.VOLUME_UP_PRICE_MOVE in d.reason_tags


def test_mock_input_can_trigger_t4_when_efficiency_above_mean():
    d = RealTradeConfirmation().evaluate(_t4_input())
    assert d.level is TradeConfirmationLevel.T4
    assert d.fired_signals >= 4
    assert ConfirmationReasonTag.TRADE_EFFICIENCY_HIGH in d.reason_tags


def test_zero_signal_input_is_t0():
    inp = ConfirmationInput(
        symbol="ABCUSDT",
        last_price=1.0,
        prev_close_price=1.0,
        cvd_1m=0.0,
        volume_1m=10.0,
        volume_5m=50.0,
        return_pct_1m=0.0,
        breakout_level=None,
        last_n_closed_bars=(),
    )
    d = RealTradeConfirmation().evaluate(inp)
    assert d.level is TradeConfirmationLevel.T0
    assert d.fired_signals == 0


def test_one_signal_is_t1():
    bars = (
        _bar(open_=1.0, high=1.0, low=1.0, close=1.01),
        _bar(open_=1.0, high=1.0, low=1.0, close=1.02),
        _bar(open_=1.0, high=1.0, low=1.0, close=1.03),
    )
    inp = ConfirmationInput(
        symbol="ABCUSDT",
        last_price=1.04,
        prev_close_price=1.03,
        cvd_1m=0.0,
        volume_1m=10.0,
        volume_5m=50.0,
        return_pct_1m=0.0,
        breakout_level=1.0,  # held -> 1 signal
        last_n_closed_bars=bars,
    )
    d = RealTradeConfirmation().evaluate(inp)
    assert d.level is TradeConfirmationLevel.T1
    assert d.fired_signals == 1


# ---------------------------------------------------------------------------
# Per-signal triggers
# ---------------------------------------------------------------------------
def test_cvd_price_agreement_fires_when_aligned():
    d = RealTradeConfirmation().evaluate(_t3_input(cvd_1m=30.0, return_pct_1m=0.01))
    assert ConfirmationReasonTag.CVD_PRICE_AGREEMENT in d.reason_tags


def test_cvd_price_agreement_does_not_fire_when_opposite_direction():
    d = RealTradeConfirmation().evaluate(_t3_input(cvd_1m=30.0, return_pct_1m=-0.01))
    assert ConfirmationReasonTag.CVD_PRICE_AGREEMENT not in d.reason_tags


def test_breakout_hold_fires_when_all_n_bars_close_above_level():
    d = RealTradeConfirmation().evaluate(_t3_input())
    assert ConfirmationReasonTag.BREAKOUT_HELD in d.reason_tags


def test_breakout_hold_does_not_fire_when_one_bar_drops_below():
    bars = (
        _bar(open_=1.0, close=1.01),
        _bar(open_=1.0, close=0.99),  # below
        _bar(open_=1.0, close=1.02),
    )
    d = RealTradeConfirmation().evaluate(
        _t3_input(last_n_closed_bars=bars)
    )
    assert ConfirmationReasonTag.BREAKOUT_HELD not in d.reason_tags


def test_volume_up_price_move_fires_when_both_conditions_met():
    d = RealTradeConfirmation().evaluate(_t3_input())
    assert ConfirmationReasonTag.VOLUME_UP_PRICE_MOVE in d.reason_tags


def test_volume_up_price_move_does_not_fire_when_price_flat():
    d = RealTradeConfirmation().evaluate(_t3_input(return_pct_1m=0.00005))
    assert ConfirmationReasonTag.VOLUME_UP_PRICE_MOVE not in d.reason_tags


def test_large_trade_followthrough_fires_with_higher_highs():
    bars = (
        _bar(open_=1.0, high=1.0, low=1.0, close=1.01),
        _bar(open_=1.0, high=1.05, low=1.0, close=1.04),
        _bar(open_=1.0, high=1.10, low=1.0, close=1.09),
    )
    d = RealTradeConfirmation().evaluate(
        _t3_input(largest_trade_qty_1m=5.0, last_n_closed_bars=bars)
    )
    assert ConfirmationReasonTag.LARGE_TRADE_FOLLOW_THROUGH in d.reason_tags


# ---------------------------------------------------------------------------
# Hard guards
# ---------------------------------------------------------------------------
def test_systemic_risk_forces_t0():
    d = RealTradeConfirmation().evaluate(
        _t3_input(
            risk_permission=RiskPermission.BLOCK_ALL,
            market_regime=MarketRegime.SYSTEMIC_RISK,
        )
    )
    assert d.level is TradeConfirmationLevel.T0
    assert ConfirmationReasonTag.REGIME_BLOCKED in d.reason_tags


def test_data_degraded_forces_t0():
    d = RealTradeConfirmation().evaluate(_t3_input(is_data_degraded=True))
    assert d.level is TradeConfirmationLevel.T0
    assert ConfirmationReasonTag.DATA_DEGRADED in d.reason_tags


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------
def test_emits_trade_confirmed_event(events_repo):
    rt = RealTradeConfirmation(event_repo=events_repo)
    d = rt.evaluate(_t3_input())
    events = events_repo.list_events(event_type=EventType.TRADE_CONFIRMED)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["level"] == d.level.value
    assert payload["fired_signals"] == d.fired_signals
    assert isinstance(payload["reason_tags"], list)


def test_per_call_emit_event_false_skips(events_repo):
    rt = RealTradeConfirmation(event_repo=events_repo)
    rt.evaluate(_t3_input(), emit_event=False)
    assert rt.trade_confirmed_events_emitted == 0
    assert rt.trade_confirmed_events_skipped == 1
    assert events_repo.count_events(event_type=EventType.TRADE_CONFIRMED) == 0


def test_event_emit_enabled_default_is_true():
    cfg = ConfirmationConfig()
    assert cfg.event_emit_enabled is True
