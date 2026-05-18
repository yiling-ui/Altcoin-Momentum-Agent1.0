"""Phase 6 scanner value objects (Spec §17 / §18, Issue #6).

Pure value objects + tunable configs. Frozen Pydantic v2 so the
contract between the Scanner and its callers (RegimeEngine output
+ MarketDataBuffer snapshot) is auditable.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    AnomalyReasonTag,
    MarketRegime,
    PreAnomalyReasonTag,
    RiskPermission,
)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Mutable(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Pre-Anomaly Scanner (Spec §17)
# ---------------------------------------------------------------------------
class PreAnomalyConfig(_Mutable):
    """Tunable thresholds for :class:`PreAnomalyScanner`.

    The Pre-Anomaly Scanner is intentionally permissive on each
    individual signal. It looks for *gentle* expansion across a basket
    of signals; the heavy lifting belongs to the Anomaly Scanner.
    """

    # Volume base-expansion: volume_1m vs (volume_5m / 5).
    # Phase 6 uses a 1.20x ratio threshold (Spec §17.2: "温和放大").
    volume_base_expansion_ratio: float = 1.20
    # Hard ceiling above which we say the move is no longer "pre" - the
    # Anomaly Scanner takes over.
    volume_explosive_ratio: float = 2.50
    # Spread compression: spread_pct must be at most this fraction of
    # a longer-window baseline. Phase 6 keeps the helper conservative
    # by accepting ``baseline_spread_pct`` from the caller (defaulting
    # to 1.5x current spread when not supplied).
    spread_compression_ratio: float = 0.75
    # Buy-pressure: cvd_1m / max(volume_1m, eps) > threshold. Phase 6
    # treats CVD as a unit-less ratio so the threshold is dimensionless.
    buy_pressure_ratio: float = 0.20
    # OI soft rise: oi_now / oi_prev - 1.0 within (0, max].
    oi_soft_rise_min: float = 0.005
    oi_soft_rise_max: float = 0.05
    # Funding overheating ceiling (absolute value, sigmoid-of-sign).
    funding_overheating_pct: float = 0.0008  # 0.08% / 8h
    # Minor uptrend: short-window return must be in (0, max].
    minor_uptrend_min_return_pct: float = 0.001  # +0.1%
    minor_uptrend_max_return_pct: float = 0.020  # +2.0%
    # Each tag adds this many points up to a ceiling of 100.
    points_per_tag: float = 15.0
    points_ceiling: float = 100.0
    # Construct-time throttle: Phase 6 mirrors the Phase 5 PR #16
    # review-fix shape so a future Top-200 scanner can flip this off.
    event_emit_enabled: bool = True


class PreAnomalyInput(_Frozen):
    """Per-symbol input. Phase 6 keeps inputs explicit so tests do
    not need to instantiate a full Phase 4 buffer."""

    symbol: str
    timestamp: int | None = None
    last_price: float | None = None
    prev_close_price: float | None = None
    spread_pct: float | None = None
    baseline_spread_pct: float | None = None
    volume_1m: float = 0.0
    volume_5m: float = 0.0
    cvd_1m: float | None = None
    cvd_5m: float | None = None
    oi: float | None = None
    prev_oi: float | None = None
    funding_rate: float | None = None
    is_data_degraded: bool = False
    market_regime: MarketRegime | None = None
    risk_permission: RiskPermission | None = None


class PreAnomalyDecision(_Frozen):
    """Output. Recorded as one ``PRE_ANOMALY_DETECTED`` event.

    Issue #6 mandate: ``pre_anomaly_score`` + ``reason_tags``.
    """

    symbol: str
    pre_anomaly_score: float
    reason_tags: tuple[PreAnomalyReasonTag, ...] = Field(default_factory=tuple)
    notes: tuple[str, ...] = Field(default_factory=tuple)
    timestamp: int | None = None


# ---------------------------------------------------------------------------
# Anomaly Scanner (Spec §18)
# ---------------------------------------------------------------------------
class AnomalyConfig(_Mutable):
    """Tunable thresholds + Spec §18.2 weights for :class:`AnomalyScanner`.

    Spec §18.2 initial formula:

        anomaly_score =
              OI_score        * 0.25
            + CVD_score       * 0.25
            + Volume_score    * 0.20
            + ATR_score       * 0.10
            + Funding_score   * 0.10
            + Liquidation_score * 0.10
    """

    # Trigger thresholds (each contributes a unit-score in [0, 1]).
    oi_spike_pct: float = 0.05            # +5% in window
    cvd_spike_ratio: float = 1.50         # cvd_1m vs cvd_5m baseline
    volume_spike_ratio: float = 2.50      # volume_1m vs volume_5m baseline
    atr_expansion_ratio: float = 1.50     # atr_1m vs atr_5m
    funding_extreme_pct: float = 0.0015   # 0.15% / 8h
    liquidation_spike_qty: float = 100.0  # cumulative qty in window
    sweep_min_legs: int = 2
    multi_timeframe_breakout_required: bool = True
    # Spec §18.2 weights
    weight_oi: float = 0.25
    weight_cvd: float = 0.25
    weight_volume: float = 0.20
    weight_atr: float = 0.10
    weight_funding: float = 0.10
    weight_liquidation: float = 0.10
    # Sweep + multi-tf breakout are bonuses on top of the weighted sum.
    weight_sweep_bonus: float = 5.0
    weight_breakout_bonus: float = 5.0
    # Final score scale.
    score_ceiling: float = 100.0
    event_emit_enabled: bool = True


class AnomalyInput(_Frozen):
    symbol: str
    timestamp: int | None = None
    last_price: float | None = None
    prev_close_price: float | None = None
    high_5m: float | None = None
    high_15m: float | None = None
    high_1h: float | None = None
    spread_pct: float | None = None
    volume_1m: float = 0.0
    volume_5m: float = 0.0
    cvd_1m: float | None = None
    cvd_5m: float | None = None
    atr_1m: float | None = None
    atr_5m: float | None = None
    oi: float | None = None
    prev_oi: float | None = None
    funding_rate: float | None = None
    liquidations_qty_1m: float = 0.0
    sweep_legs: int = 0
    is_data_degraded: bool = False
    market_regime: MarketRegime | None = None
    risk_permission: RiskPermission | None = None


class AnomalyDecision(_Frozen):
    symbol: str
    anomaly_score: float
    reason_tags: tuple[AnomalyReasonTag, ...] = Field(default_factory=tuple)
    notes: tuple[str, ...] = Field(default_factory=tuple)
    timestamp: int | None = None
