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
    initial_capital: float
    exchange_equity: float
    withdrawn_profit: float = 0.0
    lifetime_equity: float = 0.0
    trading_capital: float = 0.0
    account_life_tier: AccountLifeTier = AccountLifeTier.B
    risk_budget_total: float = 0.0
    last_rebase_ts: int = 0

    def recompute(self) -> None:
        """Apply Spec §28.2 invariants.

        lifetime_equity = exchange_equity + withdrawn_profit
        trading_capital = exchange_equity
        risk_budget_total = trading_capital
        """
        self.lifetime_equity = self.exchange_equity + self.withdrawn_profit
        self.trading_capital = self.exchange_equity
        self.risk_budget_total = self.trading_capital
