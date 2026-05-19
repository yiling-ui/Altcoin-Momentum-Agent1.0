"""Phase 8 - Capital Flow Engine tests (Issue #8).

Acceptance scenario from Issue #8:
    Initial capital = 100
    Account grows to 200
    User withdraws 80
    Exchange equity = 120

System must identify:
    - Lifetime Equity = 200
    - Trading Capital = 120
    - Withdrawn Profit = 80
    - This is NOT a -40% drawdown
    - Risk budget based on 120
    - Performance based on 200

Additional tests:
    - Rebase blocks new opens
    - Rebase after withdrawal recalculates correctly
    - Profit harvest suggestion rules (2x/5x/10x)
    - Deposit flow
    - Capital events are persisted and replayable
    - Risk Engine integration (REBASE_IN_PROGRESS rejection)
    - WithdrawalRequest validation
    - Failed rebase (positions not clear)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.capital.flow import CapitalFlowEngine
from app.capital.models import (
    HarvestSuggestion,
    RebaseResult,
    RebaseState,
    WithdrawalRequest,
)
from app.capital.profit_harvest import suggest_harvest
from app.capital.rebase import execute_rebase, persist_capital_snapshot
from app.core.enums import AccountLifeTier, RiskRejectReason
from app.core.events import EventType
from app.core.models import CapitalState
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.risk.engine import RiskEngine, RiskRequest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def capital_dbs(tmp_path: Path) -> DatabaseSet:
    """Fully migrated DatabaseSet for capital tests."""
    sqlite_dir = tmp_path / "sqlite"
    dbs = DatabaseSet.open(sqlite_dir, wal=True, databases=PHASE2_DATABASES)
    migrate_database_set(dbs)
    yield dbs
    dbs.close()


@pytest.fixture
def event_repo(capital_dbs: DatabaseSet) -> EventRepository:
    """EventRepository wired to events.db and capital.db."""
    return EventRepository(capital_dbs.events, capital_conn=capital_dbs.capital)


@pytest.fixture
def capital_engine(event_repo: EventRepository, capital_dbs: DatabaseSet) -> CapitalFlowEngine:
    """CapitalFlowEngine with initial_capital=100, equity=100."""
    return CapitalFlowEngine(
        initial_capital=100.0,
        exchange_equity=100.0,
        event_repo=event_repo,
        capital_conn=capital_dbs.capital,
    )


# ---------------------------------------------------------------------------
# Core Acceptance Scenario: 100 → 200 → withdraw 80 → 120
# ---------------------------------------------------------------------------


class TestAcceptanceScenario:
    """Issue #8 primary acceptance scenario."""

    def test_full_withdrawal_flow(self, capital_engine: CapitalFlowEngine):
        """Initial=100, grow to 200, withdraw 80, remaining=120.

        Verifications:
          - Lifetime Equity = 200
          - Trading Capital = 120
          - Withdrawn Profit = 80
          - NOT a -40% drawdown
          - Risk budget = 120
          - Performance = 200
        """
        # Step 1: Account grows to 200 via trading
        capital_engine.update_equity(new_exchange_equity=200.0)
        assert capital_engine.state.exchange_equity == 200.0
        assert capital_engine.state.lifetime_equity == 200.0
        assert capital_engine.state.trading_capital == 200.0

        # Step 2: Withdraw 80 (exchange equity drops to 120)
        result = capital_engine.withdraw(
            amount=80.0,
            new_exchange_equity=120.0,
            note="Test withdrawal",
            positions_clear=True,
        )

        # Verify rebase succeeded
        assert result.success is True
        assert result.state == RebaseState.COMPLETED

        # Verify core invariants
        state = capital_engine.state
        assert state.lifetime_equity == 200.0  # 120 + 80
        assert state.trading_capital == 120.0
        assert state.withdrawn_profit == 80.0
        assert state.exchange_equity == 120.0
        assert state.risk_budget_total == 120.0

        # NOT a drawdown: lifetime equity is preserved
        assert state.lifetime_equity == 200.0  # Performance = 200

        # Risk budget based on 120 (exchange equity), not 200
        assert state.risk_budget_total == 120.0

        # Account tier: 120 / 100 = 1.2x → tier B
        assert state.account_life_tier == AccountLifeTier.B

    def test_withdrawal_not_misidentified_as_loss(
        self, capital_engine: CapitalFlowEngine
    ):
        """Spec §28.5: 提现不是亏损."""
        capital_engine.update_equity(new_exchange_equity=200.0)

        # Before withdrawal
        lifetime_before = capital_engine.state.lifetime_equity

        # Withdraw
        capital_engine.withdraw(
            amount=80.0,
            new_exchange_equity=120.0,
            positions_clear=True,
        )

        # After withdrawal: lifetime equity unchanged (200 = 120 + 80)
        lifetime_after = capital_engine.state.lifetime_equity
        assert lifetime_after == lifetime_before

        # The engine confirms this is not a loss
        assert capital_engine.is_withdrawal_not_loss(
            previous_lifetime_equity=lifetime_before,
            current_lifetime_equity=lifetime_after,
        )

    def test_risk_budget_based_on_exchange_equity(
        self, capital_engine: CapitalFlowEngine
    ):
        """Risk budget = trading_capital = exchange_equity.
        Withdrawn profit is excluded from risk budget."""
        capital_engine.update_equity(new_exchange_equity=200.0)
        capital_engine.withdraw(
            amount=80.0,
            new_exchange_equity=120.0,
            positions_clear=True,
        )

        # Risk budget is 120 (exchange equity), NOT 200 (lifetime)
        assert capital_engine.risk_budget == 120.0
        # Withdrawn profit is NOT in risk budget
        assert capital_engine.state.withdrawn_profit == 80.0
        assert capital_engine.risk_budget == capital_engine.trading_capital

    def test_performance_based_on_lifetime_equity(
        self, capital_engine: CapitalFlowEngine
    ):
        """Performance = Lifetime Equity = exchange_equity + withdrawn_profit."""
        capital_engine.update_equity(new_exchange_equity=200.0)
        capital_engine.withdraw(
            amount=80.0,
            new_exchange_equity=120.0,
            positions_clear=True,
        )

        assert capital_engine.lifetime_equity == 200.0
        assert capital_engine.multiplier == 2.0  # 200 / 100


# ---------------------------------------------------------------------------
# Rebase blocks new opens
# ---------------------------------------------------------------------------


class TestRebaseBlocksNewOpens:
    """Spec §28.4: Rebase 前禁止新开仓."""

    def test_rebase_in_progress_blocks_risk_engine(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        """When rebase is in progress, Risk Engine rejects new opens."""
        risk_engine = RiskEngine(
            event_repo=event_repo,
            capital_flow_engine=capital_engine,
        )

        # Manually set rebase in progress
        capital_engine._rebase_in_progress = True

        decision = risk_engine.evaluate(
            RiskRequest(
                source_module="test",
                action="scout",
                symbol="PEPEUSDT",
                is_new_open=True,
            )
        )

        assert decision.rejected is True
        assert RiskRejectReason.REBASE_IN_PROGRESS.value in decision.reasons

    def test_rebase_in_progress_does_not_block_exit(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        """Rebase should NOT block position exits (is_new_open=False)."""
        risk_engine = RiskEngine(
            event_repo=event_repo,
            capital_flow_engine=capital_engine,
        )

        capital_engine._rebase_in_progress = True

        decision = risk_engine.evaluate(
            RiskRequest(
                source_module="test",
                action="exit",
                symbol="PEPEUSDT",
                is_new_open=False,
            )
        )

        # Should NOT contain REBASE_IN_PROGRESS
        assert RiskRejectReason.REBASE_IN_PROGRESS.value not in decision.reasons

    def test_successful_rebase_clears_flag(
        self, capital_engine: CapitalFlowEngine
    ):
        """After successful rebase, is_rebase_in_progress should be False."""
        capital_engine.update_equity(new_exchange_equity=200.0)
        assert capital_engine.is_rebase_in_progress is False

        result = capital_engine.withdraw(
            amount=50.0,
            new_exchange_equity=150.0,
            positions_clear=True,
        )

        assert result.success is True
        assert capital_engine.is_rebase_in_progress is False

    def test_failed_rebase_keeps_flag(
        self, capital_engine: CapitalFlowEngine
    ):
        """If rebase fails (positions not clear), flag stays True."""
        capital_engine.update_equity(new_exchange_equity=200.0)

        result = capital_engine.withdraw(
            amount=50.0,
            new_exchange_equity=150.0,
            positions_clear=False,  # Positions NOT confirmed safe
        )

        assert result.success is False
        assert result.state == RebaseState.FAILED
        assert capital_engine.is_rebase_in_progress is True


# ---------------------------------------------------------------------------
# Capital events are persisted and replayable
# ---------------------------------------------------------------------------


class TestCapitalEventsPersistence:
    """Capital events can be replayed from events.db."""

    def test_withdrawal_creates_events(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        """Withdrawal emits CAPITAL_WITHDRAWAL + PROFIT_HARVEST +
        CAPITAL_REBASE + RISK_BUDGET_RECALCULATED events."""
        capital_engine.update_equity(new_exchange_equity=200.0)
        capital_engine.withdraw(
            amount=80.0,
            new_exchange_equity=120.0,
            positions_clear=True,
        )

        # Query all capital events
        from app.core.events import CAPITAL_EVENT_TYPES

        events = event_repo.list_events(event_types=CAPITAL_EVENT_TYPES)

        # Should have at least: WITHDRAWAL, PROFIT_HARVEST, REBASE, RISK_BUDGET
        event_types = [e.event_type for e in events]
        assert EventType.CAPITAL_WITHDRAWAL in event_types
        assert EventType.PROFIT_HARVEST in event_types
        assert EventType.CAPITAL_REBASE in event_types
        assert EventType.RISK_BUDGET_RECALCULATED in event_types

    def test_deposit_creates_event(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        """Deposit emits a CAPITAL_DEPOSIT event."""
        capital_engine.deposit(amount=50.0, note="Test deposit")

        events = event_repo.list_events(event_type=EventType.CAPITAL_DEPOSIT)
        assert len(events) == 1
        assert events[0].payload["amount"] == 50.0

    def test_events_replayable_in_order(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        """Events maintain temporal ordering for replay."""
        capital_engine.deposit(amount=50.0)
        capital_engine.update_equity(new_exchange_equity=250.0)
        capital_engine.withdraw(
            amount=100.0,
            new_exchange_equity=150.0,
            positions_clear=True,
        )

        from app.core.events import CAPITAL_EVENT_TYPES

        events = list(event_repo.replay_events(event_types=CAPITAL_EVENT_TYPES))
        # Events should be in ascending timestamp order
        for i in range(1, len(events)):
            assert events[i].timestamp >= events[i - 1].timestamp

    def test_capital_snapshot_persisted(
        self, capital_engine: CapitalFlowEngine, capital_dbs: DatabaseSet
    ):
        """Capital snapshots are persisted to capital.db."""
        capital_engine.update_equity(new_exchange_equity=200.0)
        capital_engine.withdraw(
            amount=80.0,
            new_exchange_equity=120.0,
            positions_clear=True,
        )

        # Check capital.db capital_snapshots table
        rows = capital_dbs.capital.execute(
            "SELECT * FROM capital_snapshots ORDER BY timestamp DESC"
        ).fetchall()
        assert len(rows) >= 1

        latest = rows[0]
        assert latest["exchange_equity"] == 120.0
        assert latest["withdrawn_profit"] == 80.0
        assert latest["lifetime_equity"] == 200.0
        assert latest["trading_capital"] == 120.0
        assert latest["risk_budget_total"] == 120.0


# ---------------------------------------------------------------------------
# Profit Harvest Suggestions
# ---------------------------------------------------------------------------


class TestProfitHarvestSuggestions:
    """Spec §28.5 profit harvest suggestion rules."""

    def test_no_suggestion_below_2x(self):
        """No suggestion when account is below 2x."""
        result = suggest_harvest(
            current_equity=150.0,
            initial_capital=100.0,
            withdrawn_profit=0.0,
        )
        assert result is None

    def test_suggestion_at_2x(self):
        """At 2x: suggest 30%-50% of profit."""
        result = suggest_harvest(
            current_equity=200.0,
            initial_capital=100.0,
            withdrawn_profit=0.0,
        )
        assert result is not None
        assert result.multiplier == 2.0
        assert result.suggested_min_pct == 0.30
        assert result.suggested_max_pct == 0.50
        assert result.profit == 100.0
        # 30% of 100 = 30, 50% of 100 = 50
        assert result.suggested_min_amount == pytest.approx(30.0, abs=1.0)
        assert result.suggested_max_amount == pytest.approx(50.0, abs=1.0)

    def test_suggestion_at_5x(self):
        """At 5x: suggest 50%-70% of profit."""
        result = suggest_harvest(
            current_equity=500.0,
            initial_capital=100.0,
            withdrawn_profit=0.0,
        )
        assert result is not None
        assert result.multiplier == 5.0
        assert result.suggested_min_pct == 0.50
        assert result.suggested_max_pct == 0.70
        assert result.profit == 400.0
        assert result.suggested_min_amount == pytest.approx(200.0, abs=1.0)
        assert result.suggested_max_amount == pytest.approx(280.0, abs=1.0)

    def test_suggestion_at_10x(self):
        """At 10x: suggest most principal + some profit."""
        result = suggest_harvest(
            current_equity=1000.0,
            initial_capital=100.0,
            withdrawn_profit=0.0,
        )
        assert result is not None
        assert result.multiplier == 10.0
        assert result.suggested_min_pct == 0.70
        assert result.suggested_max_pct == 0.90

    def test_suggestion_with_prior_withdrawals(self):
        """Suggestion accounts for already-withdrawn profit."""
        # lifetime_equity = 300 + 200 = 500 → 5x
        result = suggest_harvest(
            current_equity=300.0,
            initial_capital=100.0,
            withdrawn_profit=200.0,
        )
        assert result is not None
        assert result.multiplier == 5.0
        assert result.suggested_min_pct == 0.50

    def test_capital_engine_get_harvest_suggestion(
        self, capital_engine: CapitalFlowEngine
    ):
        """CapitalFlowEngine.get_harvest_suggestion() integration."""
        # At 1x: no suggestion
        assert capital_engine.get_harvest_suggestion() is None

        # Grow to 2x
        capital_engine.update_equity(new_exchange_equity=200.0)
        suggestion = capital_engine.get_harvest_suggestion()
        assert suggestion is not None
        assert suggestion.multiplier == 2.0


# ---------------------------------------------------------------------------
# Deposit Flow
# ---------------------------------------------------------------------------


class TestDeposit:
    """Capital deposit recording."""

    def test_deposit_increases_equity(self, capital_engine: CapitalFlowEngine):
        """Deposit increases exchange equity and recomputes state."""
        capital_engine.deposit(amount=50.0)
        assert capital_engine.state.exchange_equity == 150.0
        assert capital_engine.state.trading_capital == 150.0
        assert capital_engine.state.lifetime_equity == 150.0
        assert capital_engine.state.risk_budget_total == 150.0

    def test_deposit_with_explicit_equity(self, capital_engine: CapitalFlowEngine):
        """Deposit with explicit new_exchange_equity."""
        capital_engine.deposit(amount=50.0, new_exchange_equity=155.0)
        assert capital_engine.state.exchange_equity == 155.0

    def test_deposit_invalid_amount(self, capital_engine: CapitalFlowEngine):
        """Deposit with amount <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="must be > 0"):
            capital_engine.deposit(amount=-10.0)

    def test_deposit_updates_tier(self, capital_engine: CapitalFlowEngine):
        """Deposit that pushes equity past 1.5x should upgrade tier."""
        capital_engine.deposit(amount=60.0)  # 100 + 60 = 160 → 1.6x → tier A
        assert capital_engine.account_tier == AccountLifeTier.A


# ---------------------------------------------------------------------------
# WithdrawalRequest validation
# ---------------------------------------------------------------------------


class TestWithdrawalRequest:
    """WithdrawalRequest model validation."""

    def test_valid_request(self):
        req = WithdrawalRequest(amount=50.0, new_exchange_equity=150.0)
        assert req.amount == 50.0
        assert req.new_exchange_equity == 150.0

    def test_negative_amount_raises(self):
        with pytest.raises(ValueError, match="must be > 0"):
            WithdrawalRequest(amount=-10.0, new_exchange_equity=100.0)

    def test_zero_amount_raises(self):
        with pytest.raises(ValueError, match="must be > 0"):
            WithdrawalRequest(amount=0.0, new_exchange_equity=100.0)

    def test_negative_equity_raises(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            WithdrawalRequest(amount=50.0, new_exchange_equity=-10.0)


# ---------------------------------------------------------------------------
# Risk Engine auto-populates from CapitalFlowEngine
# ---------------------------------------------------------------------------


class TestRiskEngineCapitalIntegration:
    """Risk Engine uses CapitalFlowEngine for tier classification."""

    def test_tier_auto_populated(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        """Risk Engine auto-resolves tier from capital engine state."""
        risk_engine = RiskEngine(
            event_repo=event_repo,
            capital_flow_engine=capital_engine,
        )

        # Initial: 100/100 = 1.0x → tier B
        decision = risk_engine.evaluate(
            RiskRequest(
                source_module="test",
                action="scout",
                symbol="TESTUSDT",
                is_new_open=True,
            )
        )
        assert decision.account_tier == AccountLifeTier.B

    def test_tier_updates_after_growth(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        """Tier reflects equity growth."""
        risk_engine = RiskEngine(
            event_repo=event_repo,
            capital_flow_engine=capital_engine,
        )

        # Grow to 160 → 1.6x → tier A
        capital_engine.update_equity(new_exchange_equity=160.0)

        decision = risk_engine.evaluate(
            RiskRequest(
                source_module="test",
                action="scout",
                symbol="TESTUSDT",
                is_new_open=True,
            )
        )
        assert decision.account_tier == AccountLifeTier.A

    def test_tier_after_withdrawal(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        """Tier based on exchange equity after withdrawal, not lifetime."""
        risk_engine = RiskEngine(
            event_repo=event_repo,
            capital_flow_engine=capital_engine,
        )

        capital_engine.update_equity(new_exchange_equity=200.0)
        capital_engine.withdraw(
            amount=80.0,
            new_exchange_equity=120.0,
            positions_clear=True,
        )

        # 120/100 = 1.2x → tier B (NOT based on lifetime 200)
        decision = risk_engine.evaluate(
            RiskRequest(
                source_module="test",
                action="scout",
                symbol="TESTUSDT",
                is_new_open=True,
            )
        )
        assert decision.account_tier == AccountLifeTier.B


# ---------------------------------------------------------------------------
# CapitalState model invariants
# ---------------------------------------------------------------------------


class TestCapitalStateInvariants:
    """CapitalState.recompute() enforces Spec §28.2 invariants."""

    def test_recompute_basic(self):
        state = CapitalState(
            initial_capital=100.0,
            exchange_equity=200.0,
            withdrawn_profit=50.0,
        )
        state.recompute()
        assert state.lifetime_equity == 250.0  # 200 + 50
        assert state.trading_capital == 200.0  # = exchange_equity
        assert state.risk_budget_total == 200.0  # = trading_capital

    def test_recompute_after_withdrawal(self):
        """Simulate: started 100, grew to 200, withdrew 80, left 120."""
        state = CapitalState(
            initial_capital=100.0,
            exchange_equity=120.0,
            withdrawn_profit=80.0,
        )
        state.recompute()
        assert state.lifetime_equity == 200.0
        assert state.trading_capital == 120.0
        assert state.risk_budget_total == 120.0


# ---------------------------------------------------------------------------
# Phase 8 boundary / safety tests
# ---------------------------------------------------------------------------


class TestPhase8Safety:
    """Phase 8 does NOT enable live trading or right-tail."""

    def test_live_trading_still_disabled(self, capital_engine: CapitalFlowEngine, event_repo: EventRepository):
        """Phase 8 does not enable live trading."""
        risk_engine = RiskEngine(
            event_repo=event_repo,
            capital_flow_engine=capital_engine,
        )

        decision = risk_engine.evaluate(
            RiskRequest(
                source_module="test",
                action="attack",
                symbol="TESTUSDT",
                live_trading_required=True,
            )
        )
        assert decision.rejected is True
        assert RiskRejectReason.LIVE_TRADING_DISABLED.value in decision.reasons

    def test_right_tail_still_disabled(self, capital_engine: CapitalFlowEngine, event_repo: EventRepository):
        """Phase 8 does not enable right-tail amplification."""
        risk_engine = RiskEngine(
            event_repo=event_repo,
            capital_flow_engine=capital_engine,
        )

        decision = risk_engine.evaluate(
            RiskRequest(
                source_module="test",
                action="amplify",
                symbol="TESTUSDT",
                right_tail_amplify=True,
            )
        )
        assert decision.rejected is True
        assert RiskRejectReason.RIGHT_TAIL_DISABLED.value in decision.reasons

    def test_initial_capital_must_be_positive(self, event_repo: EventRepository):
        """CapitalFlowEngine rejects non-positive initial capital."""
        with pytest.raises(ValueError, match="must be > 0"):
            CapitalFlowEngine(
                initial_capital=0.0,
                event_repo=event_repo,
            )

    def test_no_real_withdrawal_execution(self, capital_engine: CapitalFlowEngine):
        """System only RECORDS withdrawals; never executes them."""
        # The withdraw() method doesn't call any exchange API.
        # It only updates internal state and emits events.
        # This is verified by the absence of any exchange interaction
        # in the CapitalFlowEngine implementation.
        capital_engine.update_equity(new_exchange_equity=200.0)
        result = capital_engine.withdraw(
            amount=50.0,
            new_exchange_equity=150.0,
            positions_clear=True,
        )
        assert result.success is True
        # No exchange calls, just state updates + events



# ===========================================================================
# Phase 8 Issue #8 fix - External Capital Flow scenarios
# ===========================================================================
#
# Mandatory scenarios from the Issue #8 fix brief. Each scenario is one
# end-to-end pass through CapitalFlowEngine.
#
# Hard rules these tests pin down:
#   1. external deposit is NOT trading profit
#   2. principal withdrawal is NOT a drawdown and never lands in
#      withdrawn_profit
#   3. profit withdrawal is NOT a drawdown
#   4. risk_budget is always = exchange_equity (= trading_capital)
#   5. initial_capital is immutable after construction
#   6. capital events alone are sufficient to rebuild the snapshot
#   7. rebase_in_progress blocks new opens; clearing it does NOT
#      authorise a new open - the Risk Engine is still the gate.


class TestIssue8ProfitWithdrawalScenario:
    """Test 1: pure profit withdrawal does NOT shrink lifetime account value
    and does NOT touch principal_withdrawn_total."""

    def test_profit_only_withdrawal(self, capital_engine: CapitalFlowEngine):
        # initial_capital = 100, exchange_equity = 200, withdrawal = 80
        capital_engine.update_equity(new_exchange_equity=200.0)
        result = capital_engine.withdraw(
            amount=80.0,
            new_exchange_equity=120.0,
            positions_clear=True,
        )
        assert result.success is True
        assert result.withdrawal_type == "profit"
        assert result.profit_part == 80.0
        assert result.principal_part == 0.0

        s = capital_engine.state
        assert s.withdrawn_profit == 80.0
        assert s.principal_withdrawn_total == 0.0
        assert s.external_deposits_total == 0.0
        assert s.lifetime_account_value == 200.0
        assert capital_engine.trading_capital == 120.0
        assert capital_engine.risk_budget == 120.0
        assert s.net_trading_pnl == 100.0
        # initial_capital is preserved
        assert capital_engine.initial_capital == 100.0
        assert s.initial_capital == 100.0


class TestIssue8MixedWithdrawalScenario:
    """Test 2: mixed withdrawal must split into profit + principal.

    Setup:
        initial_capital      = 100
        exchange_equity      = 120
        withdrawal           = 50
        exchange_equity_after = 70

        available_profit = 20
        => withdrawn_profit          += 20
        => principal_withdrawn_total += 30
    """

    def test_mixed_withdrawal_splits_profit_and_principal(
        self, capital_engine: CapitalFlowEngine
    ):
        capital_engine.update_equity(new_exchange_equity=120.0)
        result = capital_engine.withdraw(
            amount=50.0,
            new_exchange_equity=70.0,
            positions_clear=True,
        )
        assert result.success is True
        assert result.withdrawal_type == "mixed"
        assert result.available_profit_before == 20.0
        assert result.profit_part == 20.0
        assert result.principal_part == 30.0

        s = capital_engine.state
        # Issue #8 hard rule - principal MUST NOT pollute withdrawn_profit
        assert s.withdrawn_profit == 20.0
        assert s.principal_withdrawn_total == 30.0
        assert s.lifetime_account_value == 120.0  # 70 + 20 + 30
        assert s.net_trading_pnl == 20.0
        assert capital_engine.risk_budget == 70.0
        assert capital_engine.initial_capital == 100.0
        assert s.initial_capital == 100.0

    def test_pure_principal_withdrawal_no_profit_pollution(
        self, capital_engine: CapitalFlowEngine
    ):
        """Withdraw when account is at-or-below initial: 100% principal."""
        # exchange_equity stays at 100 (no profit yet)
        result = capital_engine.withdraw(
            amount=30.0,
            new_exchange_equity=70.0,
            positions_clear=True,
        )
        assert result.success is True
        assert result.withdrawal_type == "principal"
        assert result.profit_part == 0.0
        assert result.principal_part == 30.0

        s = capital_engine.state
        assert s.withdrawn_profit == 0.0
        assert s.principal_withdrawn_total == 30.0
        assert s.net_trading_pnl == 0.0


class TestIssue8MidStreamDeposit:
    """Test 3: mid-stream external deposit must NOT count as profit.

    Setup:
        initial_capital      = 100
        exchange_equity      = 100
        deposit              = 50
        exchange_equity_after = 150
    """

    def test_external_deposit_is_not_profit(
        self, capital_engine: CapitalFlowEngine
    ):
        capital_engine.deposit(amount=50.0)

        s = capital_engine.state
        assert s.external_deposits_total == 50.0
        assert capital_engine.trading_capital == 150.0
        assert capital_engine.risk_budget == 150.0
        assert s.lifetime_account_value == 150.0
        assert s.net_contributed_capital == 150.0
        # The crucial assertion - net_trading_pnl is 0, NOT 50.
        assert s.net_trading_pnl == 0.0
        # External deposit must NEVER show up as withdrawn_profit either.
        assert s.withdrawn_profit == 0.0
        assert s.principal_withdrawn_total == 0.0
        assert capital_engine.initial_capital == 100.0


class TestIssue8DepositThenProfit:
    """Test 4: deposit followed by trading profit must show only the
    trading portion as P&L (not the deposit).

    Setup:
        initial_capital            = 100
        external_deposits_total    = 50
        exchange_equity            = 200
    """

    def test_pnl_after_deposit_excludes_deposit(
        self, capital_engine: CapitalFlowEngine
    ):
        capital_engine.deposit(amount=50.0)  # equity now 150
        capital_engine.update_equity(new_exchange_equity=200.0)

        s = capital_engine.state
        assert s.lifetime_account_value == 200.0
        assert s.net_contributed_capital == 150.0
        # Crucial: gain over net_contributed_capital is 50, NOT 100.
        assert s.net_trading_pnl == 50.0


class TestIssue8DepositThenWithdraw:
    """Test 5: deposit then partial profit withdrawal.

    Setup:
        initial_capital              = 100
        deposit                      = 50
        exchange_equity              = 220
        withdrawal                   = 60
        exchange_equity_after        = 160
        available_profit             = 70  (220 - 100 - 50)
    """

    def test_deposit_then_profit_withdrawal(
        self, capital_engine: CapitalFlowEngine
    ):
        capital_engine.deposit(amount=50.0)
        capital_engine.update_equity(new_exchange_equity=220.0)

        result = capital_engine.withdraw(
            amount=60.0,
            new_exchange_equity=160.0,
            positions_clear=True,
        )
        assert result.success is True
        assert result.withdrawal_type == "profit"
        assert result.available_profit_before == 70.0
        assert result.profit_part == 60.0
        assert result.principal_part == 0.0

        s = capital_engine.state
        assert s.withdrawn_profit == 60.0
        assert s.principal_withdrawn_total == 0.0
        assert s.external_deposits_total == 50.0
        assert s.lifetime_account_value == 220.0
        assert s.net_trading_pnl == 70.0
        assert capital_engine.risk_budget == 160.0


class TestIssue8WithdrawalExceedsAvailableProfit:
    """Test 6: a withdrawal that exceeds available_profit must NOT be
    fully booked as profit.

    Setup:
        initial_capital              = 100
        deposit                      = 50
        exchange_equity              = 160
        withdrawal                   = 80
        exchange_equity_after        = 80
        available_profit             = 10  (160 - 100 - 50)
    """

    def test_over_profit_withdrawal_splits(
        self, capital_engine: CapitalFlowEngine
    ):
        capital_engine.deposit(amount=50.0)
        capital_engine.update_equity(new_exchange_equity=160.0)

        result = capital_engine.withdraw(
            amount=80.0,
            new_exchange_equity=80.0,
            positions_clear=True,
        )
        assert result.success is True
        assert result.withdrawal_type == "mixed"
        assert result.available_profit_before == 10.0
        assert result.profit_part == 10.0
        assert result.principal_part == 70.0

        s = capital_engine.state
        # withdrawn_profit MUST NOT contain the 70 principal portion.
        assert s.withdrawn_profit == 10.0
        assert s.principal_withdrawn_total == 70.0
        assert s.external_deposits_total == 50.0
        assert s.net_trading_pnl == 10.0
        assert capital_engine.risk_budget == 80.0


class TestIssue8RebaseGating:
    """Test 7: Rebase-in-progress blocks new opens; clearing it does NOT
    authorise a new open while other No-Trade Gate conditions are alive.
    """

    def test_rebase_in_progress_blocks_open(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        risk_engine = RiskEngine(
            event_repo=event_repo,
            capital_flow_engine=capital_engine,
        )
        capital_engine._rebase_in_progress = True
        decision = risk_engine.evaluate(
            RiskRequest(
                source_module="test",
                action="scout",
                symbol="PEPEUSDT",
                is_new_open=True,
            )
        )
        assert decision.rejected
        assert RiskRejectReason.REBASE_IN_PROGRESS.value in decision.reasons

    def test_rebase_completed_still_subject_to_stop_unconfirmed(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        """After the rebase clears, a stop_unconfirmed open MUST still be
        rejected by the Risk Engine."""
        risk_engine = RiskEngine(
            event_repo=event_repo,
            capital_flow_engine=capital_engine,
        )
        capital_engine.update_equity(new_exchange_equity=200.0)
        capital_engine.withdraw(
            amount=80.0, new_exchange_equity=120.0, positions_clear=True
        )
        assert capital_engine.is_rebase_in_progress is False

        decision = risk_engine.evaluate(
            RiskRequest(
                source_module="test",
                action="scout",
                symbol="PEPEUSDT",
                is_new_open=True,
                stop_unconfirmed=True,
            )
        )
        assert decision.rejected
        assert RiskRejectReason.STOP_UNCONFIRMED.value in decision.reasons

    def test_rebase_completed_still_subject_to_unknown_position(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        """unknown_position MUST still block opening after a rebase."""
        risk_engine = RiskEngine(
            event_repo=event_repo,
            capital_flow_engine=capital_engine,
        )
        capital_engine.deposit(amount=50.0)
        assert capital_engine.is_rebase_in_progress is False

        decision = risk_engine.evaluate(
            RiskRequest(
                source_module="test",
                action="scout",
                symbol="PEPEUSDT",
                is_new_open=True,
                unknown_position=True,
            )
        )
        assert decision.rejected
        assert RiskRejectReason.UNKNOWN_POSITION.value in decision.reasons

    def test_deposit_blocks_new_opens_during_rebase(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        """Issue #8 hard rule: a deposit-triggered rebase must also gate
        new opens via REBASE_IN_PROGRESS while it is running."""
        # We can't easily race the deposit, but we can pin the contract
        # by manually flipping the flag the way the deposit() method
        # does and re-checking the Risk Engine.
        risk_engine = RiskEngine(
            event_repo=event_repo,
            capital_flow_engine=capital_engine,
        )
        capital_engine._rebase_in_progress = True
        try:
            decision = risk_engine.evaluate(
                RiskRequest(
                    source_module="test",
                    action="scout",
                    symbol="PEPEUSDT",
                    is_new_open=True,
                )
            )
            assert decision.rejected
            assert (
                RiskRejectReason.REBASE_IN_PROGRESS.value in decision.reasons
            )
        finally:
            capital_engine._rebase_in_progress = False


class TestIssue8EventReconstruction:
    """Test 8: capital events alone must be enough to rebuild the
    current CapitalSnapshot (Spec §12 + Issue #8 hard rule)."""

    def test_replay_pure_profit_withdrawal(
        self, capital_engine: CapitalFlowEngine
    ):
        capital_engine.update_equity(new_exchange_equity=200.0)
        capital_engine.withdraw(
            amount=80.0, new_exchange_equity=120.0, positions_clear=True
        )

        rebuilt = capital_engine.reconstruct_current_snapshot()
        live = capital_engine.state
        assert rebuilt.exchange_equity == live.exchange_equity
        assert rebuilt.withdrawn_profit == live.withdrawn_profit
        assert rebuilt.principal_withdrawn_total == live.principal_withdrawn_total
        assert rebuilt.external_deposits_total == live.external_deposits_total
        assert rebuilt.lifetime_account_value == live.lifetime_account_value
        assert rebuilt.net_trading_pnl == live.net_trading_pnl
        assert rebuilt.initial_capital == live.initial_capital

    def test_replay_mixed_withdrawal(
        self, capital_engine: CapitalFlowEngine
    ):
        capital_engine.update_equity(new_exchange_equity=120.0)
        capital_engine.withdraw(
            amount=50.0, new_exchange_equity=70.0, positions_clear=True
        )

        rebuilt = capital_engine.reconstruct_current_snapshot()
        live = capital_engine.state
        assert rebuilt.withdrawn_profit == live.withdrawn_profit == 20.0
        assert (
            rebuilt.principal_withdrawn_total
            == live.principal_withdrawn_total
            == 30.0
        )
        assert rebuilt.exchange_equity == live.exchange_equity == 70.0
        assert (
            rebuilt.lifetime_account_value
            == live.lifetime_account_value
            == 120.0
        )
        assert rebuilt.net_trading_pnl == live.net_trading_pnl == 20.0

    def test_replay_deposit_then_withdrawal(
        self, capital_engine: CapitalFlowEngine
    ):
        capital_engine.deposit(amount=50.0)
        capital_engine.update_equity(new_exchange_equity=220.0)
        capital_engine.withdraw(
            amount=60.0, new_exchange_equity=160.0, positions_clear=True
        )

        rebuilt = capital_engine.reconstruct_current_snapshot()
        live = capital_engine.state
        assert rebuilt.external_deposits_total == 50.0
        assert rebuilt.withdrawn_profit == 60.0
        assert rebuilt.principal_withdrawn_total == 0.0
        assert rebuilt.exchange_equity == 160.0
        assert rebuilt.lifetime_account_value == 220.0
        assert rebuilt.net_trading_pnl == 70.0
        # The rebuilt state must match the live state.
        assert rebuilt.exchange_equity == live.exchange_equity
        assert rebuilt.withdrawn_profit == live.withdrawn_profit
        assert (
            rebuilt.principal_withdrawn_total
            == live.principal_withdrawn_total
        )
        assert rebuilt.external_deposits_total == live.external_deposits_total
        assert rebuilt.net_trading_pnl == live.net_trading_pnl

    def test_replay_over_profit_withdrawal(
        self, capital_engine: CapitalFlowEngine
    ):
        """The replay must produce exactly the same split the live engine
        produced for a withdrawal that exceeded available_profit."""
        capital_engine.deposit(amount=50.0)
        capital_engine.update_equity(new_exchange_equity=160.0)
        capital_engine.withdraw(
            amount=80.0, new_exchange_equity=80.0, positions_clear=True
        )

        rebuilt = capital_engine.reconstruct_current_snapshot()
        assert rebuilt.withdrawn_profit == 10.0
        assert rebuilt.principal_withdrawn_total == 70.0
        assert rebuilt.external_deposits_total == 50.0
        assert rebuilt.exchange_equity == 80.0
        assert rebuilt.net_trading_pnl == 10.0


class TestIssue8InitialCapitalImmutable:
    """Issue #8 hard rule: ``initial_capital`` is set once at construction
    and MUST NOT change after a withdrawal or rebase."""

    def test_initial_capital_setter_rejects_assignment(
        self, capital_engine: CapitalFlowEngine
    ):
        with pytest.raises(AttributeError, match="immutable"):
            capital_engine.initial_capital = 999.0

    def test_initial_capital_unchanged_after_deposit(
        self, capital_engine: CapitalFlowEngine
    ):
        original = capital_engine.initial_capital
        capital_engine.deposit(amount=50.0)
        assert capital_engine.initial_capital == original
        assert capital_engine.state.initial_capital == original

    def test_initial_capital_unchanged_after_withdraw(
        self, capital_engine: CapitalFlowEngine
    ):
        original = capital_engine.initial_capital
        capital_engine.update_equity(new_exchange_equity=200.0)
        capital_engine.withdraw(
            amount=80.0, new_exchange_equity=120.0, positions_clear=True
        )
        assert capital_engine.initial_capital == original
        assert capital_engine.state.initial_capital == original

    def test_initial_capital_unchanged_after_mixed_withdraw(
        self, capital_engine: CapitalFlowEngine
    ):
        original = capital_engine.initial_capital
        capital_engine.update_equity(new_exchange_equity=120.0)
        capital_engine.withdraw(
            amount=50.0, new_exchange_equity=70.0, positions_clear=True
        )
        assert capital_engine.initial_capital == original
        assert capital_engine.state.initial_capital == original


class TestIssue8DepositEvents:
    """Issue #8 hard rule: a deposit emits CAPITAL_DEPOSIT,
    CAPITAL_REBASE, and RISK_BUDGET_RECALCULATED in that order."""

    def test_deposit_emits_full_event_trio(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        capital_engine.deposit(amount=50.0)

        deposit_events = event_repo.list_events(
            event_type=EventType.CAPITAL_DEPOSIT
        )
        rebase_events = event_repo.list_events(
            event_type=EventType.CAPITAL_REBASE
        )
        risk_events = event_repo.list_events(
            event_type=EventType.RISK_BUDGET_RECALCULATED
        )

        assert len(deposit_events) == 1
        assert len(rebase_events) == 1
        assert len(risk_events) == 1
        assert deposit_events[0].payload["external_deposits_total"] == 50.0
        assert rebase_events[0].payload["trigger"] == "deposit"
        assert (
            risk_events[0].payload["new_risk_budget"]
            == capital_engine.risk_budget
        )

    def test_deposit_does_not_emit_profit_harvest(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        """An external deposit is NOT a harvest. PROFIT_HARVEST events
        must only fire when profit is actually being withdrawn."""
        capital_engine.deposit(amount=50.0)
        harvest_events = event_repo.list_events(
            event_type=EventType.PROFIT_HARVEST
        )
        assert len(harvest_events) == 0


class TestIssue8WithdrawalPayloadSemantics:
    """The CAPITAL_WITHDRAWAL payload must always carry withdrawal_type
    and the profit/principal split so a Replay engine cannot mis-attribute
    principal as profit."""

    def test_profit_payload(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        capital_engine.update_equity(new_exchange_equity=200.0)
        capital_engine.withdraw(
            amount=80.0, new_exchange_equity=120.0, positions_clear=True
        )
        events = event_repo.list_events(event_type=EventType.CAPITAL_WITHDRAWAL)
        assert len(events) == 1
        p = events[0].payload
        assert p["withdrawal_type"] == "profit"
        assert p["profit_part"] == 80.0
        assert p["principal_part"] == 0.0

    def test_mixed_payload(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        capital_engine.update_equity(new_exchange_equity=120.0)
        capital_engine.withdraw(
            amount=50.0, new_exchange_equity=70.0, positions_clear=True
        )
        events = event_repo.list_events(event_type=EventType.CAPITAL_WITHDRAWAL)
        p = events[0].payload
        assert p["withdrawal_type"] == "mixed"
        assert p["profit_part"] == 20.0
        assert p["principal_part"] == 30.0
        assert p["available_profit_before"] == 20.0

    def test_principal_payload(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        capital_engine.withdraw(
            amount=30.0, new_exchange_equity=70.0, positions_clear=True
        )
        events = event_repo.list_events(event_type=EventType.CAPITAL_WITHDRAWAL)
        p = events[0].payload
        assert p["withdrawal_type"] == "principal"
        assert p["profit_part"] == 0.0
        assert p["principal_part"] == 30.0

    def test_principal_only_does_not_emit_profit_harvest(
        self, capital_engine: CapitalFlowEngine, event_repo: EventRepository
    ):
        """A pure-principal withdrawal must NOT emit PROFIT_HARVEST -
        otherwise harvest analytics get polluted."""
        capital_engine.withdraw(
            amount=30.0, new_exchange_equity=70.0, positions_clear=True
        )
        harvest = event_repo.list_events(event_type=EventType.PROFIT_HARVEST)
        assert len(harvest) == 0
