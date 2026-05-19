"""Capital Flow Engine (Phase 8, Spec §28).

Orchestrates the full capital lifecycle:
  - Deposits
  - Withdrawals (profit harvest)
  - Capital Rebase
  - Risk budget recalculation
  - Account life tier updates
  - Integration with Risk Engine

Core invariants (Spec §28.2):
  - lifetime_equity = exchange_equity + withdrawn_profit
  - trading_capital = exchange_equity
  - risk_budget = trading_capital
  - performance = lifetime_equity

Hard rules:
  - Withdrawal is NOT a loss
  - Withdrawal is a capital base reset
  - No new opens during rebase
  - Withdrawn profit excluded from risk budget
  - All capital events must be persisted
  - Risk budget recalculation must be persisted

Prohibitions:
  - No real withdrawal execution
  - No exchange withdrawal API calls
  - No live trading
  - No right-tail amplification with principal
"""

from __future__ import annotations

import sqlite3

from loguru import logger

from app.capital.models import (
    CapitalSnapshot,
    HarvestSuggestion,
    RebaseResult,
    RebaseState,
    WithdrawalRequest,
)
from app.capital.profit_harvest import suggest_harvest
from app.capital.rebase import execute_rebase, persist_capital_snapshot
from app.core.clock import now_ms
from app.core.enums import AccountLifeTier
from app.core.events import EventType
from app.core.models import CapitalState
from app.database.repositories import EventRepository
from app.risk.account_tier import classify_account_tier


class CapitalFlowEngine:
    """Phase 8 Capital Flow Engine (Spec §28).

    Manages the authoritative CapitalState and exposes operations:
      - deposit()
      - withdraw() / profit_harvest()
      - get_state()
      - get_harvest_suggestion()
      - is_rebase_in_progress

    The engine ensures:
      - Rebase blocks new opens (via is_rebase_in_progress flag)
      - All mutations are event-sourced
      - Risk budget is always consistent with exchange equity
      - Performance is computed from lifetime equity
      - Withdrawn profit never re-enters risk budget
    """

    def __init__(
        self,
        *,
        initial_capital: float,
        exchange_equity: float | None = None,
        withdrawn_profit: float = 0.0,
        event_repo: EventRepository,
        capital_conn: sqlite3.Connection | None = None,
    ) -> None:
        if initial_capital <= 0:
            raise ValueError(
                f"initial_capital must be > 0; got {initial_capital}"
            )

        self._initial_capital = initial_capital
        self._event_repo = event_repo
        self._capital_conn = capital_conn
        self._rebase_in_progress = False

        # Initialise CapitalState
        equity = exchange_equity if exchange_equity is not None else initial_capital
        self._state = CapitalState(
            initial_capital=initial_capital,
            exchange_equity=equity,
            withdrawn_profit=withdrawn_profit,
        )
        self._state.recompute()

        # Set initial tier
        self._state.account_life_tier = classify_account_tier(
            current_equity=self._state.exchange_equity,
            initial_capital=self._initial_capital,
        )

        logger.info(
            "CapitalFlowEngine initialised: initial={}, equity={}, "
            "withdrawn={}, lifetime={}, tier={}",
            initial_capital,
            self._state.exchange_equity,
            self._state.withdrawn_profit,
            self._state.lifetime_equity,
            self._state.account_life_tier.value,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def state(self) -> CapitalState:
        """Current capital state (read-only view)."""
        return self._state

    @property
    def initial_capital(self) -> float:
        return self._initial_capital

    @property
    def is_rebase_in_progress(self) -> bool:
        """True while a rebase is in progress. No new opens allowed."""
        return self._rebase_in_progress

    @property
    def lifetime_equity(self) -> float:
        """Performance metric: exchange_equity + withdrawn_profit."""
        return self._state.lifetime_equity

    @property
    def trading_capital(self) -> float:
        """Risk budget base: exchange_equity."""
        return self._state.trading_capital

    @property
    def risk_budget(self) -> float:
        """Current risk budget = trading_capital."""
        return self._state.risk_budget_total

    @property
    def account_tier(self) -> AccountLifeTier:
        """Current account life tier."""
        return self._state.account_life_tier

    @property
    def multiplier(self) -> float:
        """Current account multiplier (lifetime_equity / initial_capital)."""
        if self._initial_capital <= 0:
            return 0.0
        return self._state.lifetime_equity / self._initial_capital

    # ------------------------------------------------------------------
    # Deposit
    # ------------------------------------------------------------------
    def deposit(
        self,
        *,
        amount: float,
        new_exchange_equity: float | None = None,
        note: str | None = None,
    ) -> None:
        """Record a capital deposit.

        Args:
            amount: positive USDT amount deposited.
            new_exchange_equity: explicit new equity (if known from exchange).
                If None, we add amount to current exchange_equity.
            note: optional note.
        """
        if amount <= 0:
            raise ValueError(f"Deposit amount must be > 0; got {amount}")

        ts = now_ms()

        if new_exchange_equity is not None:
            self._state.exchange_equity = new_exchange_equity
        else:
            self._state.exchange_equity += amount

        self._state.recompute()
        self._state.account_life_tier = classify_account_tier(
            current_equity=self._state.exchange_equity,
            initial_capital=self._initial_capital,
        )

        self._event_repo.record_capital_deposit(
            amount=amount,
            source_module="capital_flow_engine",
            note=note or f"Deposit of {amount} USDT",
            timestamp=ts,
        )

        self._persist_snapshot(note=f"After deposit of {amount} USDT")

        logger.info(
            "Deposit recorded: amount={}, equity={}, tier={}",
            amount,
            self._state.exchange_equity,
            self._state.account_life_tier.value,
        )

    # ------------------------------------------------------------------
    # Withdrawal / Profit Harvest
    # ------------------------------------------------------------------
    def withdraw(
        self,
        *,
        amount: float,
        new_exchange_equity: float,
        note: str | None = None,
        positions_clear: bool = True,
        timestamp: int | None = None,
    ) -> RebaseResult:
        """Execute a withdrawal with full 13-step capital rebase.

        This is the PRIMARY interface for recording a withdrawal. It:
          1. Sets rebase_in_progress = True (blocks new opens)
          2. Executes the rebase flow (13 steps)
          3. Persists capital snapshot
          4. Clears rebase_in_progress (if rebase succeeded and risk allows)

        Args:
            amount: positive USDT amount withdrawn.
            new_exchange_equity: equity on exchange after withdrawal.
            note: optional note.
            positions_clear: caller confirms positions/stops are safe.
            timestamp: optional explicit timestamp.

        Returns:
            RebaseResult with full audit trail.
        """
        # Step 1: Block new opens
        self._rebase_in_progress = True

        try:
            request = WithdrawalRequest(
                amount=amount,
                new_exchange_equity=new_exchange_equity,
                note=note,
                timestamp=timestamp,
            )

            result = execute_rebase(
                capital_state=self._state,
                withdrawal=request,
                event_repo=self._event_repo,
                initial_capital=self._initial_capital,
                positions_clear=positions_clear,
            )

            if result.success:
                self._persist_snapshot(
                    note=f"Rebase after withdrawal of {amount} USDT"
                )

            return result
        finally:
            # Step 13: Resume trading only if rebase succeeded
            # If failed, keep rebase_in_progress = True so system stays paused
            if result.success:
                self._rebase_in_progress = False
            else:
                logger.warning(
                    "Rebase failed; rebase_in_progress remains True. "
                    "Manual intervention required."
                )

    def profit_harvest(
        self,
        *,
        amount: float,
        new_exchange_equity: float,
        note: str | None = None,
        positions_clear: bool = True,
        timestamp: int | None = None,
    ) -> RebaseResult:
        """Alias for withdraw() with profit-harvest semantics.

        Identical to withdraw() but the note defaults to a harvest message.
        """
        return self.withdraw(
            amount=amount,
            new_exchange_equity=new_exchange_equity,
            note=note or f"Profit harvest of {amount} USDT",
            positions_clear=positions_clear,
            timestamp=timestamp,
        )

    # ------------------------------------------------------------------
    # Equity update (without withdrawal - e.g. from trading P&L)
    # ------------------------------------------------------------------
    def update_equity(self, *, new_exchange_equity: float) -> None:
        """Update exchange equity from trading P&L (not a deposit/withdrawal).

        This does NOT trigger a rebase. It simply updates the equity and
        recomputes derived fields. Used by the system to reflect trading
        gains/losses.
        """
        self._state.exchange_equity = new_exchange_equity
        self._state.recompute()
        self._state.account_life_tier = classify_account_tier(
            current_equity=self._state.exchange_equity,
            initial_capital=self._initial_capital,
        )

    # ------------------------------------------------------------------
    # Harvest suggestion
    # ------------------------------------------------------------------
    def get_harvest_suggestion(self) -> HarvestSuggestion | None:
        """Get a profit-harvest suggestion based on current state.

        Returns None if account is below 2x (no suggestion).
        """
        return suggest_harvest(
            current_equity=self._state.exchange_equity,
            initial_capital=self._initial_capital,
            withdrawn_profit=self._state.withdrawn_profit,
        )

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------
    def get_state(self) -> CapitalState:
        """Return current CapitalState."""
        return self._state

    def is_withdrawal_not_loss(
        self,
        *,
        previous_lifetime_equity: float,
        current_lifetime_equity: float,
    ) -> bool:
        """Verify that a decrease in exchange equity after withdrawal
        is NOT a loss.

        Spec §28.5 hard rule: "提现不是亏损".
        If lifetime_equity is maintained or increased, the decrease
        in exchange_equity is a withdrawal, not a loss.
        """
        return current_lifetime_equity >= previous_lifetime_equity

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _persist_snapshot(self, note: str | None = None) -> CapitalSnapshot | None:
        """Persist current state to capital.db if connection available."""
        if self._capital_conn is None:
            return None
        return persist_capital_snapshot(
            capital_state=self._state,
            capital_conn=self._capital_conn,
            initial_capital=self._initial_capital,
            note=note,
        )
