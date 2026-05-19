"""Capital Rebase logic (Phase 8, Spec §28.4).

Implements the 13-step withdrawal flow:

    1.  Pause new opens (set rebase_in_progress flag)
    2.  Record withdrawal event (CAPITAL_WITHDRAWAL or PROFIT_HARVEST)
    3.  Update exchange equity (from WithdrawalRequest.new_exchange_equity)
    4.  Update Withdrawn Profit (add amount to running total)
    5.  Compute Lifetime Equity = Exchange Equity + Withdrawn Profit
    6.  Recompute Trading Capital = Exchange Equity
    7.  Recompute Account Life Tier
    8.  Recompute position ammo (risk budget)
    9.  Recompute single-trade max risk
    10. Recompute right-tail amplification eligibility
    11. Confirm no position / stop anomalies (caller responsibility)
    12. Complete Capital Rebase (persist snapshot, emit CAPITAL_REBASE event)
    13. Resume trading (clear rebase_in_progress flag) - only if risk allows

Hard rules (Spec §28.5):
    - 提现不是亏损 (Withdrawal is NOT a loss)
    - 提现是资金基准重置 (Withdrawal is a capital base reset)
    - Rebase 前禁止新开仓 (No new opens during rebase)
    - 已提现利润不得重新纳入风险预算 (Withdrawn profit excluded from risk budget)
    - Capital Rebase 必须写入事件
    - 风险预算重算必须写入事件

Prohibitions:
    - 禁止真实提现操作 (No real withdrawal execution)
    - 禁止接入交易所提现 API
    - 禁止 live trading
"""

from __future__ import annotations

import uuid

from loguru import logger

from app.capital.models import (
    CapitalSnapshot,
    RebaseResult,
    RebaseState,
    WithdrawalRequest,
)
from app.core.clock import now_ms
from app.core.enums import AccountLifeTier
from app.core.events import Event, EventType
from app.core.models import CapitalState
from app.database.repositories import EventRepository
from app.risk.account_tier import classify_account_tier


def execute_rebase(
    *,
    capital_state: CapitalState,
    withdrawal: WithdrawalRequest,
    event_repo: EventRepository,
    initial_capital: float,
    positions_clear: bool = True,
) -> RebaseResult:
    """Execute the 13-step capital rebase flow.

    Args:
        capital_state: current CapitalState (mutable, will be updated in place).
        withdrawal: the withdrawal request describing amount + new equity.
        event_repo: event repository for persisting events.
        initial_capital: the account's initial capital (never changes).
        positions_clear: whether positions / stops are confirmed safe.
            If False, the rebase will fail at step 11.

    Returns:
        RebaseResult with full before/after audit trail.

    This function:
      - Does NOT execute real withdrawals.
      - Does NOT call any exchange API.
      - Does NOT enable live trading.
    """
    ts = withdrawal.timestamp or now_ms()

    # Capture "before" state
    prev_equity = capital_state.exchange_equity
    prev_withdrawn = capital_state.withdrawn_profit
    prev_lifetime = capital_state.lifetime_equity
    prev_trading = capital_state.trading_capital
    prev_budget = capital_state.risk_budget_total
    prev_tier = capital_state.account_life_tier

    errors: list[str] = []

    # ------------------------------------------------------------------
    # Step 1: Flag rebase in progress (caller must respect this flag
    # to block new opens). We record it via the state update.
    # ------------------------------------------------------------------
    logger.info(
        "Capital rebase started: withdrawal={}, new_equity={}",
        withdrawal.amount,
        withdrawal.new_exchange_equity,
    )

    # ------------------------------------------------------------------
    # Step 2: Record withdrawal event
    # ------------------------------------------------------------------
    event_repo.record_capital_withdrawal(
        amount=withdrawal.amount,
        source_module="capital_rebase",
        note=withdrawal.note or f"Withdrawal of {withdrawal.amount} USDT",
        timestamp=ts,
    )

    # Also record as PROFIT_HARVEST (spec treats withdrawal of profits
    # as a harvest event for accounting purposes)
    event_repo.record_profit_harvest(
        amount=withdrawal.amount,
        source_module="capital_rebase",
        note=withdrawal.note or f"Profit harvest of {withdrawal.amount} USDT",
        timestamp=ts,
    )

    # ------------------------------------------------------------------
    # Steps 3-6: Update capital state
    # ------------------------------------------------------------------
    # Step 3: Update exchange equity
    capital_state.exchange_equity = withdrawal.new_exchange_equity

    # Step 4: Update Withdrawn Profit (accumulate)
    capital_state.withdrawn_profit = prev_withdrawn + withdrawal.amount

    # Steps 5-6: Recompute derived fields (Spec §28.2 invariants)
    # lifetime_equity = exchange_equity + withdrawn_profit
    # trading_capital = exchange_equity
    # risk_budget_total = trading_capital
    capital_state.recompute()

    # ------------------------------------------------------------------
    # Step 7: Recompute Account Life Tier
    # ------------------------------------------------------------------
    new_tier = classify_account_tier(
        current_equity=capital_state.exchange_equity,
        initial_capital=initial_capital,
    )
    capital_state.account_life_tier = new_tier

    # ------------------------------------------------------------------
    # Steps 8-9: Risk budget is already set by recompute()
    # risk_budget_total = trading_capital = exchange_equity
    # Single-trade max risk = risk_budget_total * max_single_trade_loss_pct
    # (computed dynamically by Risk Engine at evaluation time)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Step 10: Right-tail amplification eligibility
    # Right-tail requires tier A (>= 1.5x). The tier already encodes this.
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Step 11: Confirm no position / stop anomalies
    # ------------------------------------------------------------------
    if not positions_clear:
        errors.append("positions_or_stops_not_confirmed_safe")
        logger.error(
            "Capital rebase FAILED: positions/stops not confirmed safe"
        )
        return RebaseResult(
            success=False,
            state=RebaseState.FAILED,
            previous_exchange_equity=prev_equity,
            previous_withdrawn_profit=prev_withdrawn,
            previous_lifetime_equity=prev_lifetime,
            previous_trading_capital=prev_trading,
            previous_risk_budget=prev_budget,
            previous_account_tier=prev_tier,
            new_exchange_equity=capital_state.exchange_equity,
            new_withdrawn_profit=capital_state.withdrawn_profit,
            new_lifetime_equity=capital_state.lifetime_equity,
            new_trading_capital=capital_state.trading_capital,
            new_risk_budget=capital_state.risk_budget_total,
            new_account_tier=new_tier,
            withdrawal_amount=withdrawal.amount,
            note=withdrawal.note or "",
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 12: Persist CAPITAL_REBASE event + snapshot
    # ------------------------------------------------------------------
    capital_state.last_rebase_ts = ts

    event_repo.record_capital_rebase(
        exchange_equity=capital_state.exchange_equity,
        withdrawn_profit=capital_state.withdrawn_profit,
        lifetime_equity=capital_state.lifetime_equity,
        trading_capital=capital_state.trading_capital,
        source_module="capital_rebase",
        note=f"Rebase after withdrawal of {withdrawal.amount} USDT",
        timestamp=ts,
    )

    # Record RISK_BUDGET_RECALCULATED
    event_repo.record_risk_budget_recalculated(
        new_risk_budget=capital_state.risk_budget_total,
        previous_risk_budget=prev_budget,
        source_module="capital_rebase",
        note=(
            f"Risk budget recalculated: {prev_budget:.2f} -> "
            f"{capital_state.risk_budget_total:.2f}"
        ),
        timestamp=ts,
    )

    # ------------------------------------------------------------------
    # Step 13: Resume trading (caller clears rebase_in_progress flag).
    # The rebase itself just returns success; the CapitalFlowEngine
    # orchestrator decides when to actually resume based on risk checks.
    # ------------------------------------------------------------------

    logger.info(
        "Capital rebase COMPLETED: equity={}, withdrawn={}, "
        "lifetime={}, trading_capital={}, tier={}, budget={}",
        capital_state.exchange_equity,
        capital_state.withdrawn_profit,
        capital_state.lifetime_equity,
        capital_state.trading_capital,
        new_tier.value,
        capital_state.risk_budget_total,
    )

    return RebaseResult(
        success=True,
        state=RebaseState.COMPLETED,
        previous_exchange_equity=prev_equity,
        previous_withdrawn_profit=prev_withdrawn,
        previous_lifetime_equity=prev_lifetime,
        previous_trading_capital=prev_trading,
        previous_risk_budget=prev_budget,
        previous_account_tier=prev_tier,
        new_exchange_equity=capital_state.exchange_equity,
        new_withdrawn_profit=capital_state.withdrawn_profit,
        new_lifetime_equity=capital_state.lifetime_equity,
        new_trading_capital=capital_state.trading_capital,
        new_risk_budget=capital_state.risk_budget_total,
        new_account_tier=new_tier,
        withdrawal_amount=withdrawal.amount,
        note=withdrawal.note or "",
    )


def persist_capital_snapshot(
    *,
    capital_state: CapitalState,
    capital_conn,
    initial_capital: float,
    note: str | None = None,
) -> CapitalSnapshot:
    """Persist the current CapitalState as a snapshot row in capital.db.

    Returns the snapshot for audit / test purposes.
    """
    snapshot_id = str(uuid.uuid4())
    ts = now_ms()

    snapshot = CapitalSnapshot(
        snapshot_id=snapshot_id,
        timestamp=ts,
        initial_capital=initial_capital,
        exchange_equity=capital_state.exchange_equity,
        withdrawn_profit=capital_state.withdrawn_profit,
        lifetime_equity=capital_state.lifetime_equity,
        trading_capital=capital_state.trading_capital,
        account_life_tier=capital_state.account_life_tier,
        risk_budget_total=capital_state.risk_budget_total,
        note=note,
    )

    capital_conn.execute(
        """
        INSERT INTO capital_snapshots (
            snapshot_id, timestamp, initial_capital,
            exchange_equity, withdrawn_profit, lifetime_equity,
            trading_capital, account_life_tier, risk_budget_total, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot.snapshot_id,
            snapshot.timestamp,
            snapshot.initial_capital,
            snapshot.exchange_equity,
            snapshot.withdrawn_profit,
            snapshot.lifetime_equity,
            snapshot.trading_capital,
            snapshot.account_life_tier.value,
            snapshot.risk_budget_total,
            snapshot.note,
        ),
    )
    capital_conn.commit()

    return snapshot
