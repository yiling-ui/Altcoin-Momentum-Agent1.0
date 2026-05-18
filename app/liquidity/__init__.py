"""Liquidity Filter package (Phase 5 - Issue #5).

Spec §19. Computes:

  - estimated slippage (book walk against an incoming order)
  - depth_score (planned-order-size vs available depth)
  - spread_score (current spread vs the configured ceiling)
  - exit_time_estimate (seconds to flatten ``qty`` at the configured
    max slippage)
  - :func:`can_exit_position` (Spec §19.2 - mandatory function)

Phase 5 hard rules enforced here (per Issue #5):

  - 1: SYSTEMIC_RISK -> reject every can_exit / liquidity check.
  - 2: insufficient liquidity -> reject (with reasons).
  - 3: no exit channel -> reject the attack candidate.
  - 4: data degraded -> reject.
  - 5 / 6: every reject carries reasons and is persisted as one
    ``LIQUIDITY_CHECKED`` event.
"""

from app.liquidity.filter import LiquidityFilter
from app.liquidity.models import (
    ExitPlan,
    LiquidityConfig,
    LiquidityDecision,
    LiquidityInput,
    Side,
)
from app.liquidity.slippage import (
    estimate_book_walk,
    estimated_slippage_pct,
    walk_book_for_quote_notional,
)

__all__ = [
    "ExitPlan",
    "LiquidityConfig",
    "LiquidityDecision",
    "LiquidityFilter",
    "LiquidityInput",
    "Side",
    "estimate_book_walk",
    "estimated_slippage_pct",
    "walk_book_for_quote_notional",
]
