"""Phase 5 - Regime Engine tests (Issue #5).

Covers:

  - The five regimes from Spec §15.2 (one test per regime).
  - The Spec §15.3 regime -> risk_permission map.
  - SYSTEMIC_RISK overrides: explicit flag, BTC drop, BTC extreme vol.
  - Data degraded fallback (Phase 5 hard rule 4).
  - REGIME_UPDATED event emission and payload contract.
  - Frozen value-object contract on RegimeInput / RegimeSnapshot.
"""

from __future__ import annotations

import pytest

from app.core.enums import (
    AltLiquidity,
    BtcTrend,
    BtcVolatility,
    MarketRegime,
    RiskPermission,
)
from app.core.events import EventType
from app.regime import (
    REGIME_TO_RISK_PERMISSION,
    RegimeConfig,
    RegimeEngine,
    RegimeInput,
    RegimeSnapshot,
)


# ---------------------------------------------------------------------------
# Spec §15.3 mapping
# ---------------------------------------------------------------------------
def test_regime_to_risk_permission_map_is_complete():
    assert set(REGIME_TO_RISK_PERMISSION.keys()) == set(MarketRegime)


def test_regime_to_risk_permission_systemic_blocks_all():
    assert (
        REGIME_TO_RISK_PERMISSION[MarketRegime.SYSTEMIC_RISK]
        is RiskPermission.BLOCK_ALL
    )


def test_regime_to_risk_permission_meme_allows_attack():
    assert (
        REGIME_TO_RISK_PERMISSION[MarketRegime.MEME_RISK_ON]
        is RiskPermission.ALLOW_ATTACK
    )


def test_regime_to_risk_permission_sector_allows_attack():
    assert (
        REGIME_TO_RISK_PERMISSION[MarketRegime.SECTOR_ROTATION]
        is RiskPermission.ALLOW_ATTACK
    )


def test_regime_to_risk_permission_btc_absorption_observe_only():
    assert (
        REGIME_TO_RISK_PERMISSION[MarketRegime.BTC_ABSORPTION]
        is RiskPermission.OBSERVE_ONLY
    )


def test_regime_to_risk_permission_alt_risk_off_allow_scout():
    assert (
        REGIME_TO_RISK_PERMISSION[MarketRegime.ALT_RISK_OFF]
        is RiskPermission.ALLOW_SCOUT
    )


# ---------------------------------------------------------------------------
# Frozen value objects
# ---------------------------------------------------------------------------
def test_regime_input_is_frozen():
    request = RegimeInput()
    with pytest.raises(Exception):
        request.btc_symbol = "ETHUSDT"  # type: ignore[misc]


def test_regime_snapshot_is_frozen():
    snapshot = RegimeSnapshot(
        market_regime=MarketRegime.MEME_RISK_ON,
        btc_trend=BtcTrend.UP,
        btc_volatility=BtcVolatility.NORMAL,
        alt_liquidity=AltLiquidity.EXPANDING,
        risk_permission=RiskPermission.ALLOW_ATTACK,
    )
    with pytest.raises(Exception):
        snapshot.market_regime = MarketRegime.SYSTEMIC_RISK  # type: ignore[misc]


# ---------------------------------------------------------------------------
# The five regimes (Spec §15.2)
# ---------------------------------------------------------------------------
def test_meme_risk_on_btc_up_alt_expanding(events_repo):
    engine = RegimeEngine(event_repo=events_repo)
    snap = engine.evaluate_input(
        RegimeInput(
            btc_return_pct_window=0.01,
            btc_atr_pct=0.01,
            alt_liquidity_ratio=1.5,
        )
    )
    assert snap.market_regime is MarketRegime.MEME_RISK_ON
    assert snap.risk_permission is RiskPermission.ALLOW_ATTACK
    assert snap.btc_trend is BtcTrend.UP
    assert snap.alt_liquidity is AltLiquidity.EXPANDING
    assert "btc_up_alt_expanding" in snap.reason_tags


def test_sector_rotation_btc_sideways_stable(events_repo):
    engine = RegimeEngine(event_repo=events_repo)
    snap = engine.evaluate_input(
        RegimeInput(
            btc_return_pct_window=0.001,
            btc_atr_pct=0.008,
            alt_liquidity_ratio=0.95,
        )
    )
    assert snap.market_regime is MarketRegime.SECTOR_ROTATION
    assert snap.risk_permission is RiskPermission.ALLOW_ATTACK
    assert snap.btc_trend is BtcTrend.SIDEWAYS
    assert snap.alt_liquidity is AltLiquidity.STABLE


def test_btc_absorption_btc_up_alt_contracting(events_repo):
    engine = RegimeEngine(event_repo=events_repo)
    snap = engine.evaluate_input(
        RegimeInput(
            btc_return_pct_window=0.012,
            btc_atr_pct=0.008,
            alt_liquidity_ratio=0.50,
        )
    )
    assert snap.market_regime is MarketRegime.BTC_ABSORPTION
    assert snap.risk_permission is RiskPermission.OBSERVE_ONLY
    assert snap.btc_trend is BtcTrend.UP
    assert snap.alt_liquidity is AltLiquidity.CONTRACTING


def test_alt_risk_off_btc_down_streak(events_repo):
    engine = RegimeEngine(event_repo=events_repo)
    snap = engine.evaluate_input(
        RegimeInput(
            btc_return_pct_window=-0.012,
            btc_atr_pct=0.008,
            alt_liquidity_ratio=0.85,
            btc_down_streak=3,
        )
    )
    assert snap.market_regime is MarketRegime.ALT_RISK_OFF
    assert snap.risk_permission is RiskPermission.ALLOW_SCOUT
    assert snap.btc_trend is BtcTrend.DOWN
    assert "btc_down_streak" in snap.reason_tags


def test_systemic_risk_explicit_override(events_repo):
    engine = RegimeEngine(event_repo=events_repo)
    snap = engine.evaluate_input(
        RegimeInput(
            btc_return_pct_window=0.005,
            btc_atr_pct=0.005,
            alt_liquidity_ratio=1.0,
            systemic_risk_override=True,
        )
    )
    assert snap.market_regime is MarketRegime.SYSTEMIC_RISK
    assert snap.risk_permission is RiskPermission.BLOCK_ALL
    assert "systemic_risk_override" in snap.reason_tags


def test_systemic_risk_btc_crash_triggers_systemic(events_repo):
    engine = RegimeEngine(event_repo=events_repo)
    snap = engine.evaluate_input(
        RegimeInput(
            btc_return_pct_window=-0.07,
            btc_atr_pct=0.008,
            alt_liquidity_ratio=0.85,
        )
    )
    assert snap.market_regime is MarketRegime.SYSTEMIC_RISK
    assert snap.risk_permission is RiskPermission.BLOCK_ALL
    assert "btc_drop_systemic" in snap.reason_tags


def test_systemic_risk_extreme_volatility_triggers_systemic(events_repo):
    engine = RegimeEngine(event_repo=events_repo)
    snap = engine.evaluate_input(
        RegimeInput(
            btc_return_pct_window=0.001,
            btc_atr_pct=0.05,
            alt_liquidity_ratio=1.0,
        )
    )
    assert snap.market_regime is MarketRegime.SYSTEMIC_RISK
    assert snap.risk_permission is RiskPermission.BLOCK_ALL
    assert snap.btc_volatility is BtcVolatility.EXTREME
    assert "btc_extreme_volatility" in snap.reason_tags


# ---------------------------------------------------------------------------
# Phase 5 hard rule 4: data degraded -> downgrade
# ---------------------------------------------------------------------------
def test_degraded_data_falls_back_to_alt_risk_off(events_repo):
    engine = RegimeEngine(event_repo=events_repo)
    snap = engine.evaluate_input(
        RegimeInput(
            btc_return_pct_window=0.02,
            btc_atr_pct=0.01,
            alt_liquidity_ratio=1.5,
            data_degraded=True,
        )
    )
    # Even though the trend looks risk-on, degraded data forces the
    # gate to a risk-off classification.
    assert snap.market_regime is MarketRegime.ALT_RISK_OFF
    assert snap.risk_permission is RiskPermission.ALLOW_SCOUT
    assert "data_degraded" in snap.reason_tags
    # alt_liquidity is set to UNKNOWN under degraded data so consumers
    # don't accidentally trust the (potentially stale) ratio.
    assert snap.alt_liquidity is AltLiquidity.UNKNOWN


# ---------------------------------------------------------------------------
# Output schema (Spec §15.1)
# ---------------------------------------------------------------------------
def test_snapshot_has_all_spec_fields():
    engine = RegimeEngine()
    snap = engine.evaluate_input(
        RegimeInput(
            btc_return_pct_window=0.01,
            btc_atr_pct=0.008,
            alt_liquidity_ratio=1.3,
        ),
        emit_event=False,
    )
    # Every Spec §15.1 field is populated and typed.
    assert isinstance(snap.market_regime, MarketRegime)
    assert isinstance(snap.btc_trend, BtcTrend)
    assert isinstance(snap.btc_volatility, BtcVolatility)
    assert isinstance(snap.alt_liquidity, AltLiquidity)
    assert isinstance(snap.risk_permission, RiskPermission)
    assert isinstance(snap.reason_tags, tuple)
    assert all(isinstance(t, str) for t in snap.reason_tags)
    assert len(snap.reason_tags) >= 1


def test_unknown_inputs_default_to_alt_risk_off():
    engine = RegimeEngine()
    snap = engine.evaluate_input(RegimeInput(), emit_event=False)
    # No trend, no atr, no liquidity -> classifier cannot prove ALLOW
    # so it falls back to ALT_RISK_OFF (Issue #5 conservative default).
    assert snap.market_regime is MarketRegime.ALT_RISK_OFF
    assert snap.btc_trend is BtcTrend.UNKNOWN
    assert snap.btc_volatility is BtcVolatility.UNKNOWN
    assert snap.alt_liquidity is AltLiquidity.UNKNOWN


# ---------------------------------------------------------------------------
# Volatility classifier
# ---------------------------------------------------------------------------
def test_volatility_low_normal_high_extreme_thresholds():
    engine = RegimeEngine()
    cases = [
        (0.001, BtcVolatility.LOW),
        (0.010, BtcVolatility.NORMAL),
        (0.020, BtcVolatility.HIGH),
        (0.045, BtcVolatility.EXTREME),
    ]
    for atr, expected in cases:
        snap = engine.evaluate_input(
            RegimeInput(
                btc_return_pct_window=0.0,
                btc_atr_pct=atr,
                alt_liquidity_ratio=0.85,
            ),
            emit_event=False,
        )
        # EXTREME triggers the systemic override; LOW/NORMAL/HIGH do
        # not, so we only assert the volatility label here.
        if expected is BtcVolatility.EXTREME:
            assert snap.btc_volatility is BtcVolatility.EXTREME
        else:
            assert snap.btc_volatility is expected


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------
def test_evaluate_emits_one_regime_updated_event(events_repo):
    engine = RegimeEngine(event_repo=events_repo)
    before = events_repo.count_events(event_type=EventType.REGIME_UPDATED)
    engine.evaluate_input(
        RegimeInput(
            btc_return_pct_window=0.01,
            btc_atr_pct=0.008,
            alt_liquidity_ratio=1.3,
        )
    )
    after = events_repo.count_events(event_type=EventType.REGIME_UPDATED)
    assert after - before == 1
    assert engine.regime_updated_events_emitted == 1


def test_emit_event_false_skips_event(events_repo):
    engine = RegimeEngine(event_repo=events_repo)
    before = events_repo.count_events(event_type=EventType.REGIME_UPDATED)
    engine.evaluate_input(
        RegimeInput(
            btc_return_pct_window=0.01,
            btc_atr_pct=0.008,
            alt_liquidity_ratio=1.3,
        ),
        emit_event=False,
    )
    after = events_repo.count_events(event_type=EventType.REGIME_UPDATED)
    assert after == before
    assert engine.regime_updated_events_emitted == 0


def test_regime_updated_event_payload_contract(events_repo):
    engine = RegimeEngine(event_repo=events_repo)
    engine.evaluate_input(
        RegimeInput(
            btc_symbol="BTCUSDT",
            btc_return_pct_window=0.01,
            btc_atr_pct=0.008,
            alt_liquidity_ratio=1.3,
        )
    )
    events = events_repo.list_events(event_type=EventType.REGIME_UPDATED)
    assert len(events) == 1
    payload = events[0].payload
    # Spec §15.1 mandates these six fields plus the symbol context.
    for key in (
        "market_regime",
        "btc_trend",
        "btc_volatility",
        "alt_liquidity",
        "risk_permission",
        "reason_tags",
    ):
        assert key in payload
    assert payload["btc_symbol"] == "BTCUSDT"
    assert isinstance(payload["reason_tags"], list)


# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------
def test_custom_config_changes_systemic_threshold():
    cfg = RegimeConfig(systemic_risk_btc_drop_pct=-0.20)
    engine = RegimeEngine(config=cfg)
    # 7% drop is no longer enough at the looser threshold.
    snap = engine.evaluate_input(
        RegimeInput(
            btc_return_pct_window=-0.07,
            btc_atr_pct=0.008,
            alt_liquidity_ratio=0.85,
        ),
        emit_event=False,
    )
    assert snap.market_regime is not MarketRegime.SYSTEMIC_RISK


def test_evaluate_rejects_request_and_buffer_set_simultaneously():
    engine = RegimeEngine()
    with pytest.raises(ValueError):
        engine.evaluate(
            request=RegimeInput(),
            buffer=object(),
        )


def test_evaluate_requires_one_of_request_or_buffer():
    engine = RegimeEngine()
    with pytest.raises(ValueError):
        engine.evaluate()
