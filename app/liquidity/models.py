"""Liquidity Filter value objects (Phase 5 - Issue #5).

Spec §19. The Liquidity Filter is the last gate before the Strategy
Engine (Issue #6) and the Risk Engine (Issue #7) consider opening a
position. It DOES NOT trade. It only emits a decision and records it.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    LiquidityRejectReason,
    MarketRegime,
    RiskPermission,
)
from app.exchanges.models import OrderBook


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Mutable(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Side(str, Enum):
    """Direction the position would take or is being unwound from.

    For ``can_exit_position(qty, ...)`` the side describes which side
    of the book we walk:

      - ``LONG``  -> exit hits bids (we sell)
      - ``SHORT`` -> exit hits asks (we buy back)
    """

    LONG = "long"
    SHORT = "short"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
class LiquidityConfig(_Mutable):
    """Tunable thresholds for :class:`LiquidityFilter` (Spec §19.1).

    Defaults align with the YAML defaults in ``app/config/risk.yaml``.
    """

    max_spread_pct: float = 0.003
    max_slippage_pct: float = 0.005
    # Multiplier the order book depth must clear vs the planned-order
    # size. Phase 5 keeps the Spec §10.2 default of 5x.
    min_depth_multiplier: float = 5.0
    # Maximum acceptable seconds to flatten a position at
    # ``max_slippage_pct``. Spec §19.2 mentions "30-60 秒"; the default
    # below sits at 60 to give Issue #6 room to tune downward.
    max_exit_seconds: float = 60.0
    # Throughput estimate (base-asset quantity / second) used to derive
    # exit time. Phase 5 derives this from the rolling 5-minute volume
    # if the caller does not pass one explicitly.
    default_throughput_qty_per_sec: float = 0.0
    # Allowed regime risk_permissions. SYSTEMIC_RISK always blocks.
    blocking_risk_permissions: tuple[RiskPermission, ...] = (
        RiskPermission.BLOCK_ALL,
    )


# ---------------------------------------------------------------------------
# Inputs / outputs
# ---------------------------------------------------------------------------
class LiquidityInput(_Frozen):
    """One liquidity check (Phase 5 - Issue #5)."""

    symbol: str
    side: Side = Side.LONG
    planned_qty: float = 0.0
    last_price: float | None = None
    spread_pct: float | None = None
    orderbook: OrderBook | None = None
    volume_5m: float = 0.0
    is_data_degraded: bool = False
    market_regime: MarketRegime | None = None
    risk_permission: RiskPermission | None = None
    # Optional override for throughput (qty/sec) used by the exit
    # estimator. When ``None`` we derive it from ``volume_5m`` divided
    # by the 5-minute window length in seconds.
    throughput_qty_per_sec: float | None = None
    timestamp: int | None = None


class ExitPlan(_Frozen):
    """Output of :meth:`LiquidityFilter.can_exit_position` (Spec §19.2).

    All scalar metrics are populated when an order book is available.
    They are advisory only - the binary :attr:`feasible` is what the
    Risk Engine consults.
    """

    symbol: str
    side: Side
    qty: float
    feasible: bool
    estimated_slippage_pct: float | None
    estimated_exit_seconds: float | None
    cleared_qty: float
    weighted_avg_fill_price: float | None
    reject_reasons: tuple[LiquidityRejectReason, ...] = Field(default_factory=tuple)
    notes: tuple[str, ...] = Field(default_factory=tuple)
    timestamp: int | None = None


class LiquidityDecision(_Frozen):
    """Output of :meth:`LiquidityFilter.evaluate` (Spec §19.1)."""

    symbol: str
    side: Side
    passed: bool
    spread_score: float
    depth_score: float
    estimated_slippage_pct: float | None
    estimated_exit_seconds: float | None
    reject_reasons: tuple[LiquidityRejectReason, ...] = Field(default_factory=tuple)
    notes: tuple[str, ...] = Field(default_factory=tuple)
    exit_plan: ExitPlan | None = None
    timestamp: int | None = None
