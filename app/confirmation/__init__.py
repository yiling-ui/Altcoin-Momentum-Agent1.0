"""Phase 6 - Real Trade Confirmation package (Issue #6, Spec §20).

A pure stateless classifier that takes a :class:`MarketSnapshot` plus
optional bar history and outputs a :class:`TradeConfirmationLevel`
(T0..T4). Phase 6 ships the classifier ONLY; it does not place an
order, does not call an LLM, does not amplify a position.
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
