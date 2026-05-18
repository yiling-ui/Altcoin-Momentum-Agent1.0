"""Cover every enum in `app.core.enums`."""

from __future__ import annotations

from app.core.enums import (
    AccountLifeTier,
    DataReliability,
    Direction,
    ExecutionState,
    IncidentLevel,
    ManipulationLevel,
    MarketRegime,
    OpportunityGrade,
    TradeConfirmationLevel,
    TradeState,
    TradingMode,
)


def test_trade_state_vocabulary():
    expected = {
        "no_trade", "observe", "scout", "confirm", "attack",
        "right_tail_amplify", "lock_profit", "distribution_alert", "forced_exit",
    }
    assert {s.value for s in TradeState} == expected


def test_execution_state_includes_phase9_states():
    # Spec §30.1 + Issue #9
    required = {
        "order_sent", "ack_received", "partial_filled", "full_filled",
        "stop_sent", "stop_confirmed", "stop_failed", "position_open",
        "exit_triggered", "position_closed", "error_protection",
    }
    assert required.issubset({s.value for s in ExecutionState})


def test_market_regime_matches_spec_15_2():
    assert {r.value for r in MarketRegime} == {
        "MEME_RISK_ON", "SECTOR_ROTATION", "BTC_ABSORPTION",
        "ALT_RISK_OFF", "SYSTEMIC_RISK",
    }


def test_manipulation_levels():
    assert [m.value for m in ManipulationLevel] == ["M0", "M1", "M2", "M3"]


def test_trade_confirmation_levels():
    assert [t.value for t in TradeConfirmationLevel] == ["T0", "T1", "T2", "T3", "T4"]


def test_opportunity_grade():
    assert [g.value for g in OpportunityGrade] == ["S", "A", "B", "C", "D"]


def test_account_life_tier():
    assert [t.value for t in AccountLifeTier] == ["A", "B", "C", "D", "E", "F"]


def test_trading_mode_default_safe():
    assert TradingMode.PAPER.value == "paper"


def test_data_reliability():
    assert [d.value for d in DataReliability] == ["A", "B", "C", "D"]


def test_incident_level():
    assert [i.value for i in IncidentLevel] == ["P0", "P1", "P2", "P3"]


def test_direction():
    assert [d.value for d in Direction] == ["long", "short", "none"]
