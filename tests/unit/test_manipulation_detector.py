"""Phase 6 - ManipulationDetector tests (Issue #6, Spec §21).

Issue #6 acceptance criteria covered here:

    2. mock 派发数据能触发 M2/M3
    4. Volume Up + Price No Move 有测试
    5. OI Up + Price Flat 有测试

The CVD-divergence and Funding-Hot-Price-Weak signals are also tested
because Issue #6 lists them explicitly in the must-implement set.
"""

from __future__ import annotations

from app.confirmation import ConfirmationBarSummary
from app.core.enums import (
    ManipulationLevel,
    ManipulationReasonTag,
    MarketRegime,
    RiskPermission,
)
from app.core.events import EventType
from app.manipulation import (
    ManipulationConfig,
    ManipulationDecision,
    ManipulationDetector,
    ManipulationInput,
)


def _bar(open_=1.0, high=1.0, low=1.0, close=1.0):
    return ConfirmationBarSummary(
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=10.0,
        buy_volume=5.0,
        sell_volume=5.0,
        trade_count=10,
    )


def _input(**overrides):
    base = dict(
        symbol="PEPEUSDT",
        timestamp=1_700_000_000_000,
        last_price=1.0,
        return_pct_1m=0.0,
        return_pct_5m=0.0,
        volume_1m=10.0,
        volume_5m=50.0,
        cvd_1m=0.0,
        cvd_5m=0.0,
        oi=1000.0,
        prev_oi=1000.0,
        funding_rate=0.0,
    )
    base.update(overrides)
    return ManipulationInput(**base)


# ---------------------------------------------------------------------------
# Decision frozen-ness + tier ladder
# ---------------------------------------------------------------------------
def test_decision_is_frozen():
    d = ManipulationDecision(
        symbol="X",
        level=ManipulationLevel.M0,
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
        raise AssertionError("ManipulationDecision must be frozen")


def test_no_signals_is_m0():
    d = ManipulationDetector().evaluate(_input())
    assert d.level is ManipulationLevel.M0
    assert d.fired_signals == 0


# ---------------------------------------------------------------------------
# Issue #6 acceptance criterion 4: Volume Up + Price No Move
# ---------------------------------------------------------------------------
def test_volume_up_price_no_move_signal_fires():
    """Issue #6 acceptance criterion 4."""
    # baseline_volume_1m = 50 / 5 = 10; volume_1m = 30 -> 3x ratio.
    # return_pct_1m = 0.0 (no move).
    d = ManipulationDetector().evaluate(
        _input(volume_1m=30.0, volume_5m=50.0, return_pct_1m=0.0)
    )
    assert ManipulationReasonTag.VOLUME_UP_PRICE_NO_MOVE in d.reason_tags
    assert d.level is ManipulationLevel.M1


def test_volume_up_price_no_move_does_not_fire_when_price_actually_moves():
    d = ManipulationDetector().evaluate(
        _input(volume_1m=30.0, volume_5m=50.0, return_pct_1m=0.01)
    )
    assert ManipulationReasonTag.VOLUME_UP_PRICE_NO_MOVE not in d.reason_tags


# ---------------------------------------------------------------------------
# Issue #6 acceptance criterion 5: OI Up + Price Flat
# ---------------------------------------------------------------------------
def test_oi_up_price_flat_signal_fires():
    """Issue #6 acceptance criterion 5."""
    d = ManipulationDetector().evaluate(
        _input(oi=1010.0, prev_oi=1000.0, return_pct_1m=0.0)
    )
    assert ManipulationReasonTag.OI_UP_PRICE_FLAT in d.reason_tags
    assert d.level is ManipulationLevel.M1


def test_oi_up_price_flat_does_not_fire_when_price_moves():
    d = ManipulationDetector().evaluate(
        _input(oi=1010.0, prev_oi=1000.0, return_pct_1m=0.02)
    )
    assert ManipulationReasonTag.OI_UP_PRICE_FLAT not in d.reason_tags


# ---------------------------------------------------------------------------
# Other Spec §21 signals
# ---------------------------------------------------------------------------
def test_cvd_up_price_flat_signal_fires():
    """Spec §21 'CVD divergence': cvd up but price flat."""
    d = ManipulationDetector().evaluate(
        _input(cvd_1m=5.0, volume_1m=20.0, return_pct_1m=0.0)
    )
    # cvd_strength = 0.25 >= 0.10
    assert ManipulationReasonTag.CVD_UP_PRICE_FLAT in d.reason_tags


def test_buy_pressure_no_push_fires_at_higher_cvd_threshold():
    d = ManipulationDetector().evaluate(
        _input(cvd_1m=10.0, volume_1m=20.0, return_pct_1m=0.0)
    )
    assert ManipulationReasonTag.BUY_PRESSURE_NO_PUSH in d.reason_tags


def test_funding_hot_price_weak_fires():
    d = ManipulationDetector().evaluate(
        _input(funding_rate=0.002, return_pct_1m=0.0)
    )
    assert ManipulationReasonTag.FUNDING_HOT_PRICE_WEAK in d.reason_tags


def test_upper_wick_growth_fires_when_average_wick_large():
    bars = (
        _bar(open_=1.0, high=1.20, low=0.99, close=1.05),  # upper wick = 0.15
        _bar(open_=1.0, high=1.20, low=0.99, close=1.05),
        _bar(open_=1.0, high=1.20, low=0.99, close=1.05),
    )
    d = ManipulationDetector().evaluate(_input(last_n_closed_bars=bars))
    assert ManipulationReasonTag.UPPER_WICK_GROWTH in d.reason_tags


def test_book_wall_flicker_fires_at_min_count():
    d = ManipulationDetector().evaluate(_input(book_wall_flicker_count=3))
    assert ManipulationReasonTag.BOOK_WALL_FLICKER in d.reason_tags


def test_narrative_after_pump_fires_when_flag_set():
    d = ManipulationDetector().evaluate(_input(narrative_after_pump=True))
    assert ManipulationReasonTag.NARRATIVE_AFTER_PUMP in d.reason_tags


# ---------------------------------------------------------------------------
# Issue #6 acceptance criterion 2: mock 派发数据能触发 M2/M3
# ---------------------------------------------------------------------------
def test_distribution_mock_data_triggers_m2():
    """Two stacked manipulation signals -> M2 (Spec §21.3 'no attack')."""
    d = ManipulationDetector().evaluate(
        _input(
            volume_1m=30.0,
            volume_5m=50.0,
            return_pct_1m=0.0,
            oi=1010.0,
            prev_oi=1000.0,
        )
    )
    assert d.level is ManipulationLevel.M2
    assert d.fired_signals == 2


def test_distribution_mock_data_triggers_m3():
    """Three stacked manipulation signals -> M3 (Spec §21.3 'no trading').

    Distribution-style mock: high volume on a flat tape, OI grinding
    higher, funding running hot -> classic 派发 signature.
    """
    d = ManipulationDetector().evaluate(
        _input(
            volume_1m=30.0,
            volume_5m=50.0,
            return_pct_1m=0.0,
            oi=1010.0,
            prev_oi=1000.0,
            funding_rate=0.002,
        )
    )
    assert d.level is ManipulationLevel.M3, (
        f"distribution mock should trigger M3; got {d.level}"
        f" fired={d.fired_signals} tags={d.reason_tags}"
    )
    assert d.fired_signals >= 3


def test_full_distribution_with_wick_and_flicker_triggers_m3():
    """Even more stacked: wick growth + book-wall flicker on top of
    the distribution mock -> M3 with >= 5 signals."""
    bars = (
        _bar(open_=1.0, high=1.20, low=0.99, close=1.05),
        _bar(open_=1.0, high=1.20, low=0.99, close=1.05),
        _bar(open_=1.0, high=1.20, low=0.99, close=1.05),
    )
    d = ManipulationDetector().evaluate(
        _input(
            volume_1m=30.0,
            volume_5m=50.0,
            return_pct_1m=0.0,
            oi=1010.0,
            prev_oi=1000.0,
            funding_rate=0.002,
            last_n_closed_bars=bars,
            book_wall_flicker_count=5,
        )
    )
    assert d.level is ManipulationLevel.M3
    assert d.fired_signals >= 5


# ---------------------------------------------------------------------------
# Hard guards
# ---------------------------------------------------------------------------
def test_systemic_risk_forces_m0():
    d = ManipulationDetector().evaluate(
        _input(
            volume_1m=30.0,
            volume_5m=50.0,
            return_pct_1m=0.0,
            risk_permission=RiskPermission.BLOCK_ALL,
            market_regime=MarketRegime.SYSTEMIC_RISK,
        )
    )
    # Regime block short-circuits the classifier - manipulation is not
    # promoted because trading is already halted by the regime gate.
    assert d.level is ManipulationLevel.M0
    assert ManipulationReasonTag.REGIME_BLOCKED in d.reason_tags


def test_data_degraded_forces_m0():
    d = ManipulationDetector().evaluate(
        _input(
            volume_1m=30.0,
            volume_5m=50.0,
            return_pct_1m=0.0,
            is_data_degraded=True,
        )
    )
    assert d.level is ManipulationLevel.M0
    assert ManipulationReasonTag.DATA_DEGRADED in d.reason_tags


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------
def test_emits_manipulation_detected_event(events_repo):
    detector = ManipulationDetector(event_repo=events_repo)
    d = detector.evaluate(
        _input(volume_1m=30.0, volume_5m=50.0, return_pct_1m=0.0)
    )
    events = events_repo.list_events(event_type=EventType.MANIPULATION_DETECTED)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["symbol"] == d.symbol
    assert payload["level"] == d.level.value
    assert payload["fired_signals"] == d.fired_signals
    assert isinstance(payload["reason_tags"], list)


def test_per_call_emit_event_false_skips(events_repo):
    detector = ManipulationDetector(event_repo=events_repo)
    detector.evaluate(_input(), emit_event=False)
    assert detector.manipulation_events_emitted == 0
    assert detector.manipulation_events_skipped == 1
    assert events_repo.count_events(event_type=EventType.MANIPULATION_DETECTED) == 0


def test_event_emit_enabled_default_is_true():
    cfg = ManipulationConfig()
    assert cfg.event_emit_enabled is True
