"""Phase 6 - AnomalyScanner tests (Issue #6, Spec §18)."""

from __future__ import annotations

from app.core.enums import (
    AnomalyReasonTag,
    MarketRegime,
    RiskPermission,
)
from app.core.events import EventType
from app.scanner import AnomalyConfig, AnomalyInput, AnomalyScanner


def _input(**overrides):
    base = dict(
        symbol="PEPEUSDT",
        timestamp=1_700_000_000_000,
        last_price=1.05,
        spread_pct=0.001,
        volume_1m=300.0,
        volume_5m=500.0,
        cvd_1m=80.0,
        cvd_5m=80.0,
        atr_1m=0.05,
        atr_5m=0.02,
        oi=1100.0,
        prev_oi=1000.0,
        funding_rate=0.002,
        liquidations_qty_1m=200.0,
        sweep_legs=2,
        high_5m=1.04,
        high_15m=1.03,
        high_1h=1.02,
    )
    base.update(overrides)
    return AnomalyInput(**base)


# ---------------------------------------------------------------------------
# Score range + Spec §18.2 weights
# ---------------------------------------------------------------------------
def test_anomaly_score_in_range():
    d = AnomalyScanner().evaluate(_input())
    assert 0.0 <= d.anomaly_score <= 100.0


def test_zero_input_yields_zero_score():
    d = AnomalyScanner().evaluate(
        _input(
            volume_1m=0.0,
            volume_5m=0.0,
            cvd_1m=0.0,
            cvd_5m=0.0,
            oi=None,
            prev_oi=None,
            atr_1m=None,
            atr_5m=None,
            funding_rate=None,
            liquidations_qty_1m=0.0,
            sweep_legs=0,
            high_5m=None,
            high_15m=None,
            high_1h=None,
        )
    )
    assert d.anomaly_score == 0.0
    assert d.reason_tags == ()


def test_spec_18_2_weights_sum_to_one():
    cfg = AnomalyConfig()
    weighted = (
        cfg.weight_oi
        + cfg.weight_cvd
        + cfg.weight_volume
        + cfg.weight_atr
        + cfg.weight_funding
        + cfg.weight_liquidation
    )
    assert abs(weighted - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Per-signal triggers (Spec §18.1)
# ---------------------------------------------------------------------------
def test_oi_spike_fires_at_threshold():
    d = AnomalyScanner().evaluate(_input(oi=1100.0, prev_oi=1000.0))
    assert AnomalyReasonTag.OI_SPIKE in d.reason_tags


def test_oi_spike_does_not_fire_below_threshold():
    d = AnomalyScanner().evaluate(_input(oi=1010.0, prev_oi=1000.0))
    assert AnomalyReasonTag.OI_SPIKE not in d.reason_tags


def test_cvd_spike_fires_at_ratio():
    # cvd_5m baseline = 16 (80/5); cvd_1m = 80 -> 5x ratio.
    d = AnomalyScanner().evaluate(_input(cvd_1m=80.0, cvd_5m=80.0))
    assert AnomalyReasonTag.CVD_SPIKE in d.reason_tags


def test_volume_spike_fires_at_ratio():
    d = AnomalyScanner().evaluate(_input(volume_1m=300.0, volume_5m=500.0))
    assert AnomalyReasonTag.VOLUME_SPIKE in d.reason_tags


def test_atr_expansion_fires_at_ratio():
    d = AnomalyScanner().evaluate(_input(atr_1m=0.05, atr_5m=0.02))
    assert AnomalyReasonTag.ATR_EXPANSION in d.reason_tags


def test_funding_extreme_fires_at_threshold():
    d = AnomalyScanner().evaluate(_input(funding_rate=0.002))
    assert AnomalyReasonTag.FUNDING_EXTREME in d.reason_tags


def test_funding_extreme_fires_for_negative_funding():
    d = AnomalyScanner().evaluate(_input(funding_rate=-0.005))
    assert AnomalyReasonTag.FUNDING_EXTREME in d.reason_tags


def test_liquidation_spike_fires_at_threshold():
    d = AnomalyScanner().evaluate(_input(liquidations_qty_1m=200.0))
    assert AnomalyReasonTag.LIQUIDATION_SPIKE in d.reason_tags


def test_sweep_bonus_fires_at_min_legs():
    d = AnomalyScanner().evaluate(_input(sweep_legs=2))
    assert AnomalyReasonTag.SWEEP in d.reason_tags


def test_multi_timeframe_breakout_requires_topping_every_high():
    d = AnomalyScanner().evaluate(
        _input(last_price=1.05, high_5m=1.04, high_15m=1.03, high_1h=1.02)
    )
    assert AnomalyReasonTag.MULTI_TIMEFRAME_BREAKOUT in d.reason_tags


def test_multi_timeframe_breakout_does_not_fire_below_a_high():
    d = AnomalyScanner().evaluate(
        _input(last_price=1.025, high_5m=1.04, high_15m=1.03)
    )
    assert AnomalyReasonTag.MULTI_TIMEFRAME_BREAKOUT not in d.reason_tags


# ---------------------------------------------------------------------------
# Hard guards
# ---------------------------------------------------------------------------
def test_systemic_risk_blocks_score():
    d = AnomalyScanner().evaluate(
        _input(
            risk_permission=RiskPermission.BLOCK_ALL,
            market_regime=MarketRegime.SYSTEMIC_RISK,
        )
    )
    assert d.anomaly_score == 0.0
    assert AnomalyReasonTag.REGIME_BLOCKED in d.reason_tags


def test_data_degraded_blocks_score():
    d = AnomalyScanner().evaluate(_input(is_data_degraded=True))
    assert d.anomaly_score == 0.0
    assert AnomalyReasonTag.DATA_DEGRADED in d.reason_tags


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------
def test_emits_anomaly_event_with_component_scores(events_repo):
    scanner = AnomalyScanner(event_repo=events_repo)
    d = scanner.evaluate(_input())
    events = events_repo.list_events(event_type=EventType.ANOMALY_DETECTED)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["symbol"] == d.symbol
    assert payload["anomaly_score"] == d.anomaly_score
    assert "component_scores" in payload
    assert set(payload["component_scores"].keys()) >= {
        "oi",
        "cvd",
        "volume",
        "atr",
        "funding",
        "liquidation",
    }
    assert "weights" in payload


def test_per_call_emit_event_false_skips(events_repo):
    scanner = AnomalyScanner(event_repo=events_repo)
    scanner.evaluate(_input(), emit_event=False)
    assert scanner.anomaly_events_emitted == 0
    assert scanner.anomaly_events_skipped == 1
    assert events_repo.count_events(event_type=EventType.ANOMALY_DETECTED) == 0


def test_config_event_emit_enabled_false_can_be_overridden(events_repo):
    cfg = AnomalyConfig(event_emit_enabled=False)
    scanner = AnomalyScanner(config=cfg, event_repo=events_repo)
    scanner.evaluate(_input())
    assert scanner.anomaly_events_emitted == 0
    scanner.evaluate(_input(), emit_event=True)
    assert scanner.anomaly_events_emitted == 1
