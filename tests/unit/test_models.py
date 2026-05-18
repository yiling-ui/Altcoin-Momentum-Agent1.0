"""Phase 1 sanity tests for `app.core.models`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums import (
    Direction,
    ExecutionState,
    ManipulationLevel,
    MarketRegime,
    OpportunityGrade,
    TradeConfirmationLevel,
    TradeState,
)
from app.core.models import (
    CapitalState,
    MarketSnapshot,
    PositionState,
    SignalSnapshot,
    TradeDecision,
)


def test_market_snapshot_required_fields():
    snap = MarketSnapshot(
        symbol="PEPEUSDT",
        timestamp=1,
        last_price=1.0,
        bid=0.99,
        ask=1.01,
        spread_pct=0.02,
    )
    assert snap.symbol == "PEPEUSDT"
    assert snap.volume_1m == 0.0


def test_market_snapshot_rejects_unknown_field():
    with pytest.raises(ValidationError):
        MarketSnapshot(
            symbol="X",
            timestamp=1,
            last_price=1,
            bid=1,
            ask=1,
            spread_pct=0,
            unknown_field="evil",
        )


def test_signal_snapshot_defaults_are_safe():
    sig = SignalSnapshot(
        symbol="X",
        timestamp=1,
        regime=MarketRegime.SYSTEMIC_RISK,
    )
    assert sig.opportunity_grade is OpportunityGrade.D
    assert sig.manipulation_level is ManipulationLevel.M0
    assert sig.trade_confirmation_level is TradeConfirmationLevel.T0


def test_trade_decision_is_observe_friendly():
    d = TradeDecision(
        symbol="X",
        timestamp=1,
        action="observe",
        state=TradeState.OBSERVE,
    )
    assert d.direction is Direction.NONE
    assert d.leverage == 1.0


def test_position_state_defaults_to_isolated():
    p = PositionState(
        position_id="p1",
        symbol="X",
        direction=Direction.LONG,
        qty=10,
        entry_price=1,
        mark_price=1,
    )
    assert p.margin_mode == "isolated"
    assert p.stop_confirmed is False
    assert p.state is ExecutionState.IDLE


def test_capital_state_recompute_invariants():
    cap = CapitalState(initial_capital=100, exchange_equity=120, withdrawn_profit=80)
    cap.recompute()
    assert cap.lifetime_equity == 200
    assert cap.trading_capital == 120
    assert cap.risk_budget_total == 120
