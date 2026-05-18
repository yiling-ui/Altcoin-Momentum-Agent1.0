"""Universe Filter value objects (Phase 5 - Issue #5).

Spec §16. The Universe Filter decides whether a symbol is *eligible*
for further signal evaluation. It does NOT decide whether to trade -
that is the Strategy Engine's job (Issue #6 / #7) and the Risk
Engine's final word (Issue #7).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    DataReliability,
    MarketRegime,
    RiskPermission,
    UniverseRejectReason,
)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Mutable(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
class UniverseConfig(_Mutable):
    """Tunable thresholds for :class:`UniverseFilter` (Spec §16.2).

    Defaults align with the YAML defaults in ``app/config/risk.yaml``
    so a future YAML pull-through is transparent.
    """

    # Spread / depth gates (mirror LiquidityThresholds defaults).
    max_spread_pct: float = 0.003
    # Minimum aggregate book notional (USDT) the order book must
    # advertise on each side. Phase 5 uses a coarse absolute threshold;
    # Issue #7 will scale this by planned-order-size.
    min_orderbook_depth_usdt: float = 5_000.0
    # Trade continuity: minimum number of trades over the rolling 5m
    # window. A fully silent symbol is rejected.
    min_trade_count_5m: int = 5
    # Minimum 5-minute volume (in base currency) before a symbol is
    # allowed through. Strategy-level mins (e.g. min daily volume) are
    # Issue #7's job, not ours.
    min_volume_5m: float = 0.0
    # Reliability tier the snapshot must claim. Spec §13.3 + §16.2.
    min_reliability: DataReliability = DataReliability.B
    # Allowed exchange contract statuses. ``ExchangeSymbol.status``
    # uses Binance-style strings; we keep a small allow-list rather
    # than rejecting every non-TRADING value because Issue #6 may need
    # AUCTION_MATCH-only candidates.
    allowed_contract_statuses: tuple[str, ...] = ("TRADING",)
    # Allowed regime risk_permissions for new openings. SYSTEMIC_RISK
    # always blocks (Phase 5 hard rule 1). OBSERVE_ONLY blocks attack
    # candidates by default; the consumer can override per call.
    blocking_risk_permissions: tuple[RiskPermission, ...] = (
        RiskPermission.BLOCK_ALL,
    )


# ---------------------------------------------------------------------------
# Inputs / outputs
# ---------------------------------------------------------------------------
class UniverseInput(_Frozen):
    """Aggregate per-symbol state the filter consults.

    The filter accepts this object directly so tests do not need to
    spin up a full Phase 4 buffer to drive every reject path.
    """

    symbol: str
    contract_status: str = "TRADING"
    spread_pct: float | None = None
    orderbook_depth_usdt: float | None = None
    trade_count_5m: int = 0
    volume_5m: float = 0.0
    reliability: DataReliability | None = None
    is_data_degraded: bool = False
    abnormal_data_flag: bool = False
    # Optional regime context. When present, blocking_risk_permissions
    # in the config decide whether the regime alone rejects the symbol.
    market_regime: MarketRegime | None = None
    risk_permission: RiskPermission | None = None
    timestamp: int | None = None


class UniverseDecision(_Frozen):
    """Output for one symbol. Recorded as one ``UNIVERSE_FILTERED`` event."""

    symbol: str
    eligible: bool
    reject_reasons: tuple[UniverseRejectReason, ...] = Field(default_factory=tuple)
    # Free-form reason notes for human reviewers and the Reflection
    # engine (Issue #10).
    notes: tuple[str, ...] = Field(default_factory=tuple)
    timestamp: int | None = None
