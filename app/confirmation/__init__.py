"""Phase 6 - Real Trade Confirmation package (Issue #6, Spec §20).

A pure stateless classifier that takes a :class:`MarketSnapshot` plus
optional bar history and outputs a :class:`TradeConfirmationLevel`
(T0..T4). Phase 6 ships the classifier ONLY; it does not place an
order, does not call an LLM, does not amplify a position.

**T3/T4 is a trade-confirmation LEVEL only, NOT a trade approval.**
The classifier returns a typed level + reason tags; it does not emit
:class:`app.core.models.TradeDecision`, does not enqueue an order,
and does not mutate any position state. Whether a real opening is
allowed remains the conjunction of:

  - the Phase 5 regime gate (`RegimeSnapshot.risk_permission`),
  - the Phase 5 universe / liquidity decisions (Universe.eligible,
    LiquidityDecision.passed, can_exit_position.feasible),
  - the Phase 6 confirmation tier (T2+ required for ATTACK candidates),
  - the Phase 6 manipulation tier (M0 / M1 only for ATTACK candidates),
  - the Phase 7 No-Trade Gate + Risk Engine final adjudication, and
  - the Phase 9 Execution FSM transition.

A T3 reading on its own authorises nothing. The Risk Engine hooks
in Phase 6 only *reject* candidates that fail this contract; they do
not promote anything. The non-generation invariant is pinned by
``tests/unit/test_real_trade_confirmation.py`` (level + reason tags
in the decision shape, no TradeDecision / order / position fields).
"""

from app.confirmation.models import (
    ConfirmationConfig,
    ConfirmationDecision,
    ConfirmationInput,
    ConfirmationBarSummary,
)
from app.confirmation.real_trade import RealTradeConfirmation

__all__ = [
    "ConfirmationBarSummary",
    "ConfirmationConfig",
    "ConfirmationDecision",
    "ConfirmationInput",
    "RealTradeConfirmation",
]
