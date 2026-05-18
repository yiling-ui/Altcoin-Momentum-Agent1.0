"""Regime Engine value objects and the regime -> risk_permission map.

Spec §15.1 fixes the output schema and §15.3 fixes the mapping; both
are encoded here as data so tests can reason about them without
depending on the engine implementation. Phase 7's Risk Engine reads
:data:`REGIME_TO_RISK_PERMISSION` directly.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    AltLiquidity,
    BtcTrend,
    BtcVolatility,
    MarketRegime,
    RiskPermission,
)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Mutable(BaseModel):
    """Base for runtime-tunable config (still validated, not frozen)."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Spec §15.3: regime -> risk permission map.
#
# This is the source of truth that Phase 7's Risk Engine and the
# Universe / Liquidity filters all consult. We expose it as a frozen
# dict at module level so tests can assert it directly.
# ---------------------------------------------------------------------------
REGIME_TO_RISK_PERMISSION: dict[MarketRegime, RiskPermission] = {
    MarketRegime.MEME_RISK_ON: RiskPermission.ALLOW_ATTACK,
    MarketRegime.SECTOR_ROTATION: RiskPermission.ALLOW_ATTACK,
    MarketRegime.BTC_ABSORPTION: RiskPermission.OBSERVE_ONLY,
    MarketRegime.ALT_RISK_OFF: RiskPermission.ALLOW_SCOUT,
    MarketRegime.SYSTEMIC_RISK: RiskPermission.BLOCK_ALL,
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
class RegimeConfig(_Mutable):
    """Tunable thresholds for :class:`RegimeEngine`.

    Phase 5 keeps the classifier deliberately simple - it is a *gate*
    not a forecaster. The numbers below pin the regime labels at the
    boundaries Spec §15 describes; later phases (Issue #6 / #7) can
    refine them via YAML without touching the engine signature.

    All thresholds are dimensionless ratios (0.0 - 1.0+) unless
    otherwise stated.
    """

    # BTC trend: |1m return| over the analysis window
    btc_trend_up_pct: float = 0.005       # +0.5% -> UP
    btc_trend_down_pct: float = -0.005    # -0.5% -> DOWN

    # BTC volatility: realised ATR / price
    btc_vol_low_pct: float = 0.005        # below -> LOW
    btc_vol_high_pct: float = 0.015       # above -> HIGH
    btc_vol_extreme_pct: float = 0.030    # above -> EXTREME

    # Altcoin aggregate liquidity: sum_alt_volume_5m / sum_alt_volume_1h
    # Phase 5 lets the caller pass the ratio directly; the engine does
    # not compute it from per-symbol histories (that is Issue #6 work).
    alt_liquidity_expanding_ratio: float = 1.20   # >= -> EXPANDING
    alt_liquidity_stable_low: float = 0.80        # >= -> STABLE
    alt_liquidity_contracting_low: float = 0.40   # >= -> CONTRACTING (else DRY)

    # SYSTEMIC_RISK gate: the caller can pass an explicit boolean which
    # always overrides everything else.
    systemic_risk_btc_drop_pct: float = -0.05     # <= 5% drop -> SYSTEMIC_RISK
    systemic_risk_btc_extreme_vol_pct: float = 0.040
    # Number of consecutive 1m closes required to confirm DOWN before
    # flagging ALT_RISK_OFF.
    alt_risk_off_min_btc_down_streak: int = 2


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
class RegimeInput(_Frozen):
    """Aggregate market state the Regime Engine evaluates.

    Phase 5 ships :meth:`RegimeEngine.evaluate_input` taking this object
    directly; the higher-level :meth:`RegimeEngine.evaluate` builds it
    from a Phase 4 :class:`MarketDataBuffer`. Tests use this object so
    they don't need to pre-load a buffer for every scenario.
    """

    # BTC reference symbol metrics (per Spec §15 - BTC drives the gate).
    btc_symbol: str = "BTCUSDT"
    btc_last_price: float | None = None
    btc_return_pct_window: float | None = None  # signed return over window
    btc_atr_pct: float | None = None  # ATR / last_price
    btc_down_streak: int = 0
    # Aggregate altcoin liquidity (sum_alt_volume_short / sum_alt_volume_long).
    alt_liquidity_ratio: float | None = None
    # Optional exogenous overrides.
    systemic_risk_override: bool = False
    data_degraded: bool = False
    timestamp: int | None = None


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
class RegimeSnapshot(_Frozen):
    """Spec §15.1 output. The single immutable value object Phase 5
    hands to Phase 7 (Risk Engine), Phase 6 (Scanner), and Phase 10
    (Reflection / Telegram).

    Issue #5 mandates the field set:
        - market_regime
        - btc_trend
        - btc_volatility
        - alt_liquidity
        - risk_permission
        - reason_tags
    """

    market_regime: MarketRegime
    btc_trend: BtcTrend
    btc_volatility: BtcVolatility
    alt_liquidity: AltLiquidity
    risk_permission: RiskPermission
    reason_tags: tuple[str, ...] = Field(default_factory=tuple)
    # Auxiliary observability - Issue #5 does not require these but
    # they are cheap to keep and Issue #10 (Reflection) will consume
    # them. They are documented as advisory, not contractual.
    btc_return_pct_window: float | None = None
    btc_atr_pct: float | None = None
    alt_liquidity_ratio: float | None = None
    timestamp: int | None = None
