"""Phase 6 Manipulation Detector value objects (Issue #6, Spec §21)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.confirmation.models import ConfirmationBarSummary
from app.core.enums import (
    ManipulationLevel,
    ManipulationReasonTag,
    MarketRegime,
    RiskPermission,
)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Mutable(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ManipulationConfig(_Mutable):
    """Tunable thresholds for :class:`ManipulationDetector` (Spec §21)."""

    # CVD up + price flat (CVD-price divergence): cvd_1m strongly
    # positive but |return_pct_1m| below epsilon.
    cvd_strength_min: float = 0.10  # cvd_1m / volume_1m
    flat_return_pct: float = 0.001  # +/- 0.1% counts as "flat"
    # Volume up + price no move.
    volume_up_ratio: float = 1.50
    # OI up + price flat.
    oi_up_pct: float = 0.005   # +0.5% in window
    # Funding hot + price weak.
    funding_hot_pct: float = 0.0010  # 0.10% / 8h
    weak_return_pct: float = 0.001
    # Upper-wick growth: average upper wick over last N closed bars
    # exceeds this fraction of the bar range.
    upper_wick_min_fraction: float = 0.55
    upper_wick_window: int = 3
    # Buy pressure but no push: CVD strong AND |return| flat -> bonus
    # tag (this is the "主动买很多但价格推不动" case).
    buy_pressure_no_push_cvd_min: float = 0.20
    # Book wall flicker: caller-supplied flicker count must reach
    # this minimum to fire.
    book_wall_flicker_min: int = 3
    # M-tier mapping by fired-signal count.
    # 0 -> M0, 1 -> M1, 2 -> M2, 3+ -> M3.
    event_emit_enabled: bool = True


class ManipulationInput(_Frozen):
    """Per-symbol input."""

    symbol: str
    timestamp: int | None = None
    last_price: float | None = None
    prev_close_price: float | None = None
    return_pct_1m: float | None = None
    return_pct_5m: float | None = None
    spread_pct: float | None = None
    volume_1m: float = 0.0
    volume_5m: float = 0.0
    cvd_1m: float | None = None
    cvd_5m: float | None = None
    oi: float | None = None
    prev_oi: float | None = None
    funding_rate: float | None = None
    last_n_closed_bars: tuple[ConfirmationBarSummary, ...] = Field(
        default_factory=tuple
    )
    # Narrative-after-pump signal (computed by the caller / Issue #10
    # Reflection): True when price moved first and narrative followed.
    narrative_after_pump: bool = False
    # Optional book-wall flicker count (REST/WS aggregator's count of
    # large-size bid/ask placement+cancel within window).
    book_wall_flicker_count: int = 0
    is_data_degraded: bool = False
    market_regime: MarketRegime | None = None
    risk_permission: RiskPermission | None = None


class ManipulationDecision(_Frozen):
    """Output. Recorded as one ``MANIPULATION_DETECTED`` event."""

    symbol: str
    level: ManipulationLevel
    fired_signals: int
    reason_tags: tuple[ManipulationReasonTag, ...] = Field(default_factory=tuple)
    notes: tuple[str, ...] = Field(default_factory=tuple)
    timestamp: int | None = None
