"""Phase 6 Real-Trade Confirmation value objects (Issue #6, Spec §20)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    ConfirmationReasonTag,
    MarketRegime,
    RiskPermission,
    TradeConfirmationLevel,
)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Mutable(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConfirmationBarSummary(_Frozen):
    """Minimal closed-bar summary the confirmation classifier consumes.

    Phase 6 keeps the bar shape narrow so Issue #7 / #9 can substitute
    a different builder without rewriting the classifier. Compatible
    with :class:`app.market_data.models.Bar` (the classifier reads only
    these fields)."""

    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    trade_count: int = 0


class ConfirmationConfig(_Mutable):
    """Tunable thresholds for :class:`RealTradeConfirmation` (Spec §20)."""

    # CVD-price agreement: cvd_1m and last_price both moving in the
    # same direction.
    cvd_alignment_min_strength: float = 0.10  # cvd / volume
    # Breakout hold: how many of the last N closed bars must close
    # above ``breakout_level``.
    breakout_hold_min_bars: int = 3
    # Large trade follow-through: at least one large trade in the
    # window followed by N consecutive bars of higher highs.
    large_trade_qty_threshold: float = 1.0
    large_trade_followthrough_bars: int = 2
    # Trade efficiency: |return_in_window| / volume_in_window > mean.
    trade_efficiency_relative_min: float = 1.20
    # Volume up + price move: volume_1m >= ratio * baseline AND price
    # moved at least min_price_move_pct since prev close.
    volume_up_ratio: float = 1.50
    min_price_move_pct: float = 0.001  # +/- 0.1%
    # Tier mapping: number of fired signals -> level.
    # 0 -> T0, 1 -> T1, 2 -> T2, 3 -> T3, 4+ -> T4.
    event_emit_enabled: bool = True


class ConfirmationInput(_Frozen):
    symbol: str
    timestamp: int | None = None
    last_price: float | None = None
    prev_close_price: float | None = None
    cvd_1m: float | None = None
    cvd_5m: float | None = None
    volume_1m: float = 0.0
    volume_5m: float = 0.0
    return_pct_1m: float | None = None
    return_pct_5m: float | None = None
    breakout_level: float | None = None
    last_n_closed_bars: tuple[ConfirmationBarSummary, ...] = Field(
        default_factory=tuple
    )
    largest_trade_qty_1m: float = 0.0
    historical_efficiency_mean: float | None = None
    is_data_degraded: bool = False
    market_regime: MarketRegime | None = None
    risk_permission: RiskPermission | None = None


class ConfirmationDecision(_Frozen):
    symbol: str
    level: TradeConfirmationLevel
    fired_signals: int
    reason_tags: tuple[ConfirmationReasonTag, ...] = Field(default_factory=tuple)
    notes: tuple[str, ...] = Field(default_factory=tuple)
    timestamp: int | None = None
