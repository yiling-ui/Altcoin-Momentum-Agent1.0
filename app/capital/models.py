"""Capital Flow Engine models (Phase 8, Spec §28).

Defines:
  - RebaseResult: outcome of a capital rebase operation
  - WithdrawalRequest: input to the withdrawal flow
  - HarvestSuggestion: profit harvest recommendation
  - CapitalSnapshot: point-in-time snapshot persisted to capital.db
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.core.enums import AccountLifeTier


class RebaseState(str, Enum):
    """State of a capital rebase operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class WithdrawalRequest:
    """Input to the withdrawal / profit-harvest flow.

    Spec §28.4 requires 13 steps. This request initiates the flow.
    The actual withdrawal is NOT executed by the system (禁止接入
    交易所提现 API); this is a RECORD of a withdrawal that the user
    has already performed externally.

    Attributes:
        amount: positive USDT amount withdrawn.
        new_exchange_equity: exchange equity AFTER withdrawal.
        note: optional human-readable note.
        timestamp: optional explicit timestamp (ms); defaults to now.
    """

    amount: float
    new_exchange_equity: float
    note: str | None = None
    timestamp: int | None = None

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise ValueError(f"Withdrawal amount must be > 0; got {self.amount}")
        if self.new_exchange_equity < 0:
            raise ValueError(
                f"new_exchange_equity cannot be negative; got {self.new_exchange_equity}"
            )


@dataclass(frozen=True)
class RebaseResult:
    """Outcome of a capital rebase operation.

    Contains the full before/after snapshot so callers can audit
    the transition.
    """

    success: bool
    state: RebaseState

    # Before
    previous_exchange_equity: float
    previous_withdrawn_profit: float
    previous_lifetime_equity: float
    previous_trading_capital: float
    previous_risk_budget: float
    previous_account_tier: AccountLifeTier

    # After
    new_exchange_equity: float
    new_withdrawn_profit: float
    new_lifetime_equity: float
    new_trading_capital: float
    new_risk_budget: float
    new_account_tier: AccountLifeTier

    withdrawal_amount: float = 0.0
    deposit_amount: float = 0.0
    note: str = ""
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HarvestSuggestion:
    """Profit harvest recommendation (Spec §28.5).

    Rules:
      - Account 2x: suggest 30%-50% of profit
      - Account 5x: suggest 50%-70% of profit
      - Account 10x: suggest most of principal + some profit

    This is a SUGGESTION only. The system never executes real
    withdrawals.
    """

    current_equity: float
    initial_capital: float
    lifetime_equity: float
    multiplier: float
    suggested_min_pct: float
    suggested_max_pct: float
    suggested_min_amount: float
    suggested_max_amount: float
    profit: float
    message: str


@dataclass(frozen=True)
class CapitalSnapshot:
    """Point-in-time capital state persisted to capital.db.

    Maps 1:1 to the ``capital_snapshots`` table.
    """

    snapshot_id: str
    timestamp: int
    initial_capital: float
    exchange_equity: float
    withdrawn_profit: float
    lifetime_equity: float
    trading_capital: float
    account_life_tier: AccountLifeTier
    risk_budget_total: float
    note: str | None = None
