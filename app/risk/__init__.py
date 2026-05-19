"""Risk Engine package (Spec §27).

Phase 7 (Issue #7) ships the full No-Trade Gate, Account Life Tier
classifier, Daily-Loss + Consecutive-Loss Circuit Breakers, and the
Risk Engine that composes them with the Phase 1 hard flags + Phase 6
manipulation / confirmation rules.
"""

from app.risk.account_tier import (
    ACCOUNT_TIER_POLICY,
    AccountTierPolicy,
    classify_account_tier,
    policy_for,
)
from app.risk.circuit_breaker import (
    ConsecutiveLossCircuitBreaker,
    DailyLossCircuitBreaker,
)
from app.risk.engine import RiskDecision, RiskEngine, RiskRequest
from app.risk.no_trade_gate import (
    NoTradeGateDecision,
    NoTradeGateInput,
    evaluate_no_trade_gate,
)

__all__ = [
    "ACCOUNT_TIER_POLICY",
    "AccountTierPolicy",
    "ConsecutiveLossCircuitBreaker",
    "DailyLossCircuitBreaker",
    "NoTradeGateDecision",
    "NoTradeGateInput",
    "RiskDecision",
    "RiskEngine",
    "RiskRequest",
    "classify_account_tier",
    "evaluate_no_trade_gate",
    "policy_for",
]
