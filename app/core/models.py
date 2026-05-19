"""Core domain models for AMA-RT (Spec §11).

Phase 1 ships the data shapes only - none of these models drive a real
trade in this phase. Models use Pydantic v2 to give us validation for
free at the seams between modules.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    AccountLifeTier,
    Direction,
    ExecutionState,
    ManipulationLevel,
    MarketRegime,
    OpportunityGrade,
    TradeConfirmationLevel,
    TradeState,
)


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


# Spec §11.1
class MarketSnapshot(_Base):
    symbol: str
    timestamp: int
    last_price: float
    mark_price: float | None = None
    bid: float
    ask: float
    spread_pct: float
    volume_1m: float = 0.0
    volume_5m: float = 0.0
    oi: float | None = None
    funding_rate: float | None = None
    cvd_1m: float | None = None
    cvd_5m: float | None = None
    atr_1m: float | None = None
    atr_5m: float | None = None
    orderbook_depth_usdt: float | None = None


# Spec §11.2
class SignalSnapshot(_Base):
    symbol: str
    timestamp: int
    regime: MarketRegime
    pre_anomaly_score: float = 0.0
    anomaly_score: float = 0.0
    liquidity_score: float = 0.0
    trade_confirmation_level: TradeConfirmationLevel = TradeConfirmationLevel.T0
    manipulation_level: ManipulationLevel = ManipulationLevel.M0
    right_tail_score: float = 0.0
    opportunity_grade: OpportunityGrade = OpportunityGrade.D
    no_trade_reason: list[str] = Field(default_factory=list)


# Spec §11.3
class TradeDecision(_Base):
    symbol: str
    timestamp: int
    action: str  # observe | scout | attack | amplify | lock_profit | exit | reject
    direction: Direction = Direction.NONE
    state: TradeState = TradeState.NO_TRADE
    grade: OpportunityGrade = OpportunityGrade.D
    entry_zone: list[float] | None = None
    stop_price: float | None = None
    take_profit_plan: dict[str, Any] = Field(default_factory=dict)
    risk_budget_pct: float = 0.0
    leverage: float = 1.0
    reasons: list[str] = Field(default_factory=list)
    reject_reasons: list[str] = Field(default_factory=list)


# Spec §11.4
class PositionState(_Base):
    position_id: str
    symbol: str
    direction: Direction
    qty: float
    entry_price: float
    mark_price: float
    stop_price: float | None = None
    stop_confirmed: bool = False
    margin_mode: str = "isolated"
    leverage: float = 1.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    tail_qty: float = 0.0
    state: ExecutionState = ExecutionState.IDLE


# Spec §11.5
class CapitalState(_Base):
    """Capital state with full External Capital Flow semantics (Issue #8 fix).

    Field semantics:
      - ``initial_capital``           : seed capital at engine construction. MUST
                                        NOT change after construction.
      - ``exchange_equity``           : current equity on the exchange.
      - ``withdrawn_profit``          : cumulative *profit* portion of all
                                        withdrawals. Pure profit, never includes
                                        principal-portion of a withdrawal.
      - ``principal_withdrawn_total`` : cumulative *principal* portion of all
                                        withdrawals (Issue #8 fix - profit and
                                        principal are tracked separately so
                                        principal withdrawals never pollute
                                        ``withdrawn_profit``).
      - ``external_deposits_total``   : cumulative external/top-up deposits
                                        recorded after construction. NOT trading
                                        profit; excluded from net_trading_pnl
                                        and from any performance metric.
      - ``lifetime_equity``           : exchange_equity + withdrawn_profit.
                                        Preserved for backwards compatibility
                                        with Phase 1-7 callers.
      - ``trading_capital``           : exchange_equity (= risk_budget_total).
      - ``risk_budget_total``         : trading_capital. Always based on the
                                        current exchange_equity, never on
                                        historical peaks or already-withdrawn
                                        profit (Spec §28.5 hard rule).

    Computed properties:
      - ``lifetime_account_value``  = exchange_equity + withdrawn_profit
                                      + principal_withdrawn_total
      - ``net_contributed_capital`` = initial_capital + external_deposits_total
                                      - principal_withdrawn_total
      - ``net_trading_pnl``         = lifetime_account_value - initial_capital
                                      - external_deposits_total
                                      (i.e. real trading P&L, with external
                                      deposits NOT counted as profit).
    """

    initial_capital: float
    exchange_equity: float
    withdrawn_profit: float = 0.0
    lifetime_equity: float = 0.0
    trading_capital: float = 0.0
    account_life_tier: AccountLifeTier = AccountLifeTier.B
    risk_budget_total: float = 0.0
    last_rebase_ts: int = 0
    # Phase 8 Issue #8 fix - External Capital Flow tracking.
    external_deposits_total: float = 0.0
    principal_withdrawn_total: float = 0.0

    def recompute(self) -> None:
        """Apply Spec §28.2 invariants.

        lifetime_equity     = exchange_equity + withdrawn_profit
        trading_capital     = exchange_equity
        risk_budget_total   = trading_capital

        ``principal_withdrawn_total`` and ``external_deposits_total`` feed the
        computed properties below; they intentionally do NOT alter
        ``risk_budget_total`` (already-withdrawn principal must not re-enter
        the risk budget; external deposits flow through ``exchange_equity``
        directly, not through ``withdrawn_profit``).
        """
        self.lifetime_equity = self.exchange_equity + self.withdrawn_profit
        self.trading_capital = self.exchange_equity
        self.risk_budget_total = self.trading_capital

    # ------------------------------------------------------------------
    # Phase 8 Issue #8 fix - External Capital Flow computed properties.
    # ------------------------------------------------------------------
    @property
    def lifetime_account_value(self) -> float:
        """Total dollars the account has ever held / disbursed.

            lifetime_account_value = exchange_equity
                                     + withdrawn_profit
                                     + principal_withdrawn_total

        This figure is invariant under withdrawals: pulling money out of the
        exchange shifts equity into ``withdrawn_profit`` /
        ``principal_withdrawn_total`` but the sum is unchanged. That is what
        makes "提现不是亏损" (withdrawal is not a loss) measurable.
        """
        return (
            self.exchange_equity
            + self.withdrawn_profit
            + self.principal_withdrawn_total
        )

    @property
    def net_contributed_capital(self) -> float:
        """Net principal injected by the operator.

            net_contributed_capital = initial_capital
                                      + external_deposits_total
                                      - principal_withdrawn_total
        """
        return (
            self.initial_capital
            + self.external_deposits_total
            - self.principal_withdrawn_total
        )

    @property
    def net_trading_pnl(self) -> float:
        """Real trading P&L, excluding external deposits and principal moves.

            net_trading_pnl = lifetime_account_value
                              - initial_capital
                              - external_deposits_total

        External deposits are NOT profit. Principal withdrawals are NOT loss.
        Profit withdrawals are NOT drawdown. ``net_trading_pnl`` is the only
        figure performance reporting must use (Issue #8 hard rule).
        """
        return (
            self.lifetime_account_value
            - self.initial_capital
            - self.external_deposits_total
        )
