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

    Phase 8 Issue #8 fix: a withdrawal is now classified before the
    rebase runs. ``profit_part`` and ``principal_part`` always sum to
    ``withdrawal_amount``. ``withdrawal_type`` is one of:

      - ``"profit"``    : withdrawal_amount <= available_profit
      - ``"principal"`` : available_profit == 0
      - ``"mixed"``     : withdrawal exceeds available_profit but
                          available_profit > 0
      - ``""``          : not a withdrawal (e.g. a deposit-triggered rebase)

    The rebase NEVER mis-classifies principal withdrawal as
    ``withdrawn_profit`` (Issue #8 hard rule).
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

    # Phase 8 Issue #8 fix - External Capital Flow.
    profit_part: float = 0.0
    principal_part: float = 0.0
    withdrawal_type: str = ""
    available_profit_before: float = 0.0
    previous_principal_withdrawn_total: float = 0.0
    new_principal_withdrawn_total: float = 0.0
    previous_external_deposits_total: float = 0.0
    new_external_deposits_total: float = 0.0
    previous_lifetime_account_value: float = 0.0
    new_lifetime_account_value: float = 0.0
    previous_net_trading_pnl: float = 0.0
    new_net_trading_pnl: float = 0.0


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
    # Phase 8 Issue #8 fix - External Capital Flow tracking.
    external_deposits_total: float = 0.0
    principal_withdrawn_total: float = 0.0

    @property
    def lifetime_account_value(self) -> float:
        """exchange_equity + withdrawn_profit + principal_withdrawn_total."""
        return (
            self.exchange_equity
            + self.withdrawn_profit
            + self.principal_withdrawn_total
        )

    @property
    def net_contributed_capital(self) -> float:
        """initial_capital + external_deposits_total - principal_withdrawn_total."""
        return (
            self.initial_capital
            + self.external_deposits_total
            - self.principal_withdrawn_total
        )

    @property
    def net_trading_pnl(self) -> float:
        """lifetime_account_value - initial_capital - external_deposits_total."""
        return (
            self.lifetime_account_value
            - self.initial_capital
            - self.external_deposits_total
        )
