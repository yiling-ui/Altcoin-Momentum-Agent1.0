"""Phase 6 - PreAnomalyScanner tests (Issue #6, Spec §17)."""

from __future__ import annotations

from app.core.enums import (
    MarketRegime,
    PreAnomalyReasonTag,
    RiskPermission,
)
from app.core.events import EventType
from app.scanner import (
    PreAnomalyConfig,
    PreAnomalyDecision,
    PreAnomalyInput,
    PreAnomalyScanner,
)


def _input(**overrides):
    base = dict(
        symbol="PEPEUSDT",
        timestamp=1_700_000_000_000,
        last_price=1.05,
        prev_close_price=1.04,
        spread_pct=0.0005,
        baseline_spread_pct=0.001,
        volume_1m=120.0,
        volume_5m=500.0,
        cvd_1m=30.0,
        cvd_5m=80.0,
        oi=1010.0,
        prev_oi=1000.0,
        funding_rate=0.0001,
    )
    base.update(overrides)
    return PreAnomalyInput(**base)


# ---------------------------------------------------------------------------
# Output / score basics
# ---------------------------------------------------------------------------
def test_pre_anomaly_decision_is_frozen_value_object():
    d = PreAnomalyDecision(
        symbol="X",
        pre_anomaly_score=0.0,
        reason_tags=(),
        notes=(),
        timestamp=1,
    )
    try:
        d.symbol = "Y"
    except Exception:  # pragma: no cover - frozen
        pass
    else:  # pragma: no cover - should not happen
        raise AssertionError("PreAnomalyDecision must be frozen")


def test_returns_pre_anomaly_score_and_reason_tags():
    """Issue #6 mandate: output exposes both fields."""
    d = PreAnomalyScanner().evaluate(_input())
    assert hasattr(d, "pre_anomaly_score")
    assert hasattr(d, "reason_tags")
    assert isinstance(d.pre_anomaly_score, float)
    assert all(isinstance(t, PreAnomalyReasonTag) for t in d.reason_tags)


# ---------------------------------------------------------------------------
# Per-signal triggers (Spec §17.2)
# ---------------------------------------------------------------------------
def test_volume_base_expansion_fires_when_ratio_in_range():
    # baseline_volume_1m = volume_5m / 5 = 100; volume_1m = 130 -> 1.3x
    d = PreAnomalyScanner().evaluate(_input(volume_1m=130.0, volume_5m=500.0))
    assert PreAnomalyReasonTag.VOLUME_BASE_EXPANSION in d.reason_tags


def test_volume_base_expansion_does_not_fire_when_already_explosive():
    # baseline = 100, volume_1m = 300 -> 3x: above explosive ceiling.
    d = PreAnomalyScanner().evaluate(_input(volume_1m=300.0))
    assert PreAnomalyReasonTag.VOLUME_BASE_EXPANSION not in d.reason_tags


def test_spread_compression_fires_below_baseline_ratio():
    d = PreAnomalyScanner().evaluate(
        _input(spread_pct=0.0005, baseline_spread_pct=0.001)
    )
    assert PreAnomalyReasonTag.SPREAD_COMPRESSION in d.reason_tags


def test_spread_compression_does_not_fire_when_no_baseline_and_wide():
    d = PreAnomalyScanner().evaluate(
        _input(spread_pct=0.005, baseline_spread_pct=None)
    )
    assert PreAnomalyReasonTag.SPREAD_COMPRESSION not in d.reason_tags


def test_buy_pressure_rising_fires_when_cvd_share_is_high():
    # cvd_1m / volume_1m = 30/120 = 0.25 > 0.20 -> fire.
    d = PreAnomalyScanner().evaluate(_input(cvd_1m=30.0, volume_1m=120.0))
    assert PreAnomalyReasonTag.BUY_PRESSURE_RISING in d.reason_tags


def test_oi_soft_rise_fires_in_window():
    d = PreAnomalyScanner().evaluate(_input(oi=1010.0, prev_oi=1000.0))
    # +1% OI -> within (0.005, 0.05).
    assert PreAnomalyReasonTag.OI_SOFT_RISE in d.reason_tags


def test_oi_soft_rise_does_not_fire_above_window():
    d = PreAnomalyScanner().evaluate(_input(oi=1100.0, prev_oi=1000.0))
    assert PreAnomalyReasonTag.OI_SOFT_RISE not in d.reason_tags


def test_funding_not_overheated_fires_when_below_threshold():
    d = PreAnomalyScanner().evaluate(_input(funding_rate=0.0001))
    assert PreAnomalyReasonTag.FUNDING_NOT_OVERHEATED in d.reason_tags


def test_funding_not_overheated_does_not_fire_when_hot():
    d = PreAnomalyScanner().evaluate(_input(funding_rate=0.005))
    assert PreAnomalyReasonTag.FUNDING_NOT_OVERHEATED not in d.reason_tags


def test_minor_uptrend_fires_in_window():
    d = PreAnomalyScanner().evaluate(_input(last_price=1.005, prev_close_price=1.0))
    # +0.5% return.
    assert PreAnomalyReasonTag.MINOR_UPTREND in d.reason_tags


def test_minor_uptrend_does_not_fire_when_explosive():
    d = PreAnomalyScanner().evaluate(_input(last_price=1.10, prev_close_price=1.0))
    assert PreAnomalyReasonTag.MINOR_UPTREND not in d.reason_tags


def test_score_is_zero_when_no_signals_fire():
    d = PreAnomalyScanner().evaluate(
        _input(
            volume_1m=0.001,
            volume_5m=10.0,
            spread_pct=0.005,
            baseline_spread_pct=None,
            cvd_1m=0.0,
            oi=1000.0,
            prev_oi=1000.0,
            funding_rate=0.01,
            last_price=10.0,
            prev_close_price=1.0,
        )
    )
    assert d.pre_anomaly_score == 0.0


def test_score_is_capped_at_ceiling():
    d = PreAnomalyScanner().evaluate(_input())
    assert 0.0 <= d.pre_anomaly_score <= PreAnomalyConfig().points_ceiling


# ---------------------------------------------------------------------------
# Hard guards (Phase 6 Issue #6 hard rules)
# ---------------------------------------------------------------------------
def test_systemic_risk_blocks_with_regime_blocked_tag():
    d = PreAnomalyScanner().evaluate(
        _input(
            risk_permission=RiskPermission.BLOCK_ALL,
            market_regime=MarketRegime.SYSTEMIC_RISK,
        )
    )
    assert d.pre_anomaly_score == 0.0
    assert PreAnomalyReasonTag.REGIME_BLOCKED in d.reason_tags
    # Other tags are NOT computed once the regime gate fires.
    assert PreAnomalyReasonTag.VOLUME_BASE_EXPANSION not in d.reason_tags


def test_data_degraded_blocks_with_data_degraded_tag():
    d = PreAnomalyScanner().evaluate(_input(is_data_degraded=True))
    assert d.pre_anomaly_score == 0.0
    assert PreAnomalyReasonTag.DATA_DEGRADED in d.reason_tags


def test_insufficient_history_when_volume_5m_zero():
    d = PreAnomalyScanner().evaluate(_input(volume_5m=0.0))
    assert PreAnomalyReasonTag.INSUFFICIENT_HISTORY in d.reason_tags
    assert d.pre_anomaly_score == 0.0


# ---------------------------------------------------------------------------
# Event emission (PRE_ANOMALY_DETECTED)
# ---------------------------------------------------------------------------
def test_emits_pre_anomaly_event_with_full_payload(events_repo):
    scanner = PreAnomalyScanner(event_repo=events_repo)
    d = scanner.evaluate(_input())
    events = events_repo.list_events(event_type=EventType.PRE_ANOMALY_DETECTED)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["symbol"] == d.symbol
    assert payload["pre_anomaly_score"] == d.pre_anomaly_score
    assert isinstance(payload["reason_tags"], list)
    for key in (
        "last_price",
        "prev_close_price",
        "spread_pct",
        "volume_1m",
        "volume_5m",
        "cvd_1m",
        "oi",
        "prev_oi",
        "funding_rate",
    ):
        assert key in payload


def test_event_emit_enabled_default_is_true(events_repo):
    cfg = PreAnomalyConfig()
    assert cfg.event_emit_enabled is True
    scanner = PreAnomalyScanner(event_repo=events_repo)
    scanner.evaluate(_input())
    assert scanner.pre_anomaly_events_emitted == 1
    assert scanner.pre_anomaly_events_skipped == 0


def test_per_call_emit_event_false_skips_with_counter(events_repo):
    scanner = PreAnomalyScanner(event_repo=events_repo)
    scanner.evaluate(_input(), emit_event=False)
    assert events_repo.count_events(event_type=EventType.PRE_ANOMALY_DETECTED) == 0
    assert scanner.pre_anomaly_events_emitted == 0
    assert scanner.pre_anomaly_events_skipped == 1


def test_config_event_emit_enabled_false_can_be_overridden_per_call(events_repo):
    cfg = PreAnomalyConfig(event_emit_enabled=False)
    scanner = PreAnomalyScanner(config=cfg, event_repo=events_repo)
    scanner.evaluate(_input())  # emit_event=None -> follows config
    assert scanner.pre_anomaly_events_emitted == 0
    assert scanner.pre_anomaly_events_skipped == 1
    scanner.evaluate(_input(), emit_event=True)  # explicit override
    assert scanner.pre_anomaly_events_emitted == 1


# ---------------------------------------------------------------------------
# evaluate_snapshot helper
# ---------------------------------------------------------------------------
def test_evaluate_snapshot_builds_input_from_market_snapshot(events_repo):
    from app.core.models import MarketSnapshot

    snapshot = MarketSnapshot(
        symbol="DOGEUSDT",
        timestamp=1_700_000_000_000,
        last_price=0.105,
        bid=0.104,
        ask=0.106,
        spread_pct=0.001,
        volume_1m=130.0,
        volume_5m=500.0,
        cvd_1m=30.0,
        cvd_5m=80.0,
        oi=1010.0,
        funding_rate=0.0001,
        atr_1m=0.001,
        atr_5m=0.001,
    )
    scanner = PreAnomalyScanner(event_repo=events_repo)
    d = scanner.evaluate_snapshot(
        snapshot,
        prev_close_price=0.104,
        prev_oi=1000.0,
        baseline_spread_pct=0.002,
    )
    assert d.symbol == "DOGEUSDT"
    assert d.pre_anomaly_score > 0.0
    # The convenience helper still produces ONE event.
    assert (
        events_repo.count_events(event_type=EventType.PRE_ANOMALY_DETECTED) == 1
    )
