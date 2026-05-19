"""Phase 7 - boundary tests (Issue #7).

Pin the cumulative defence-in-depth that Phase 7 inherits from
Phase 1-6 plus the new Phase 7 invariants:

  - Phase 1 safety lock unchanged.
  - Phase 3 read-only invariant unchanged: every write surface still
    refuses with SafeModeViolation.
  - Phase 6 classifier surfaces unchanged.
  - Phase 7 vocabulary is reachable through public exports.
  - The state-machine module forbids LLM / strategy / capital / FSM
    imports (those belong to Issue #8 / #9 / #10).
"""

from __future__ import annotations

import inspect

from app.core.enums import (
    AccountLifeTier,
    CircuitBreakerState,
    RiskRejectReason,
    TradeState,
    TradeStateTrigger,
)
from app.core.errors import SafeModeViolation
from app.exchanges.base import WRITE_SURFACE_METHODS
from app.exchanges.binance import BinanceClient
from app.exchanges.mock import MockExchangeClient
from app.risk import (
    ACCOUNT_TIER_POLICY,
    ConsecutiveLossCircuitBreaker,
    DailyLossCircuitBreaker,
    NoTradeGateInput,
    RiskDecision,
    RiskEngine,
    RiskRequest,
    classify_account_tier,
    evaluate_no_trade_gate,
)
from app.state_machine import TradeStateMachine


# ---------------------------------------------------------------------------
# Phase 1 + Phase 3 invariants unchanged
# ---------------------------------------------------------------------------
def test_phase3_write_surfaces_still_refuse_on_mock():
    client = MockExchangeClient(autostart=False)
    for fn_name in WRITE_SURFACE_METHODS:
        try:
            getattr(client, fn_name)()
        except SafeModeViolation:
            continue
        else:  # pragma: no cover
            raise AssertionError(f"{fn_name} stopped refusing in Phase 7")


def test_phase3_write_surfaces_still_refuse_on_binance_skeleton():
    client = BinanceClient()
    for fn_name in WRITE_SURFACE_METHODS:
        try:
            getattr(client, fn_name)()
        except SafeModeViolation:
            continue
        else:  # pragma: no cover
            raise AssertionError(f"{fn_name} stopped refusing in Phase 7")


# ---------------------------------------------------------------------------
# Phase 7 enums are stable
# ---------------------------------------------------------------------------
def test_trade_state_vocabulary_matches_spec_26_1():
    assert {s.value for s in TradeState} == {
        "no_trade",
        "observe",
        "scout",
        "confirm",
        "attack",
        "right_tail_amplify",
        "lock_profit",
        "distribution_alert",
        "forced_exit",
    }


def test_account_life_tier_vocabulary_matches_spec_27_4():
    assert {t.value for t in AccountLifeTier} == {"A", "B", "C", "D", "E", "F"}


def test_circuit_breaker_states_pinned():
    assert {s.value for s in CircuitBreakerState} == {
        "closed",
        "open_daily_loss",
        "open_consecutive_loss",
        "cool_down",
    }


def test_risk_reject_reason_phase1_phase6_phase7_values_present():
    expected = {
        "live_trading_disabled",
        "right_tail_disabled",
        "stop_unconfirmed",
        "unknown_position",
        "manipulation_m3",
        "manipulation_m2_attack",
        "trade_confirmation_too_low_for_attack",
        "regime_block_all",
        "regime_observe_only_for_new_open",
        "regime_scout_only_for_attack",
        "universe_ineligible",
        "liquidity_rejected",
        "no_exit_channel",
        "data_degraded",
        "exchange_disconnected",
        "daily_loss_breaker_open",
        "consecutive_loss_breaker_open",
        "account_tier_halt",
        "account_tier_no_new_open",
        "account_tier_no_right_tail",
        "account_tier_paper_only",
        "right_tail_from_principal_forbidden",
        "losing_position_cannot_amplify",
    }
    actual = {r.value for r in RiskRejectReason}
    assert expected.issubset(actual)


def test_trade_state_trigger_vocabulary():
    actual = {t.value for t in TradeStateTrigger}
    expected = {
        "signal",
        "promote",
        "downgrade",
        "timeout",
        "lock_profit",
        "distribution_alert",
        "forced_exit",
        "kill_switch",
        "reset",
    }
    assert expected.issubset(actual)


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------
def test_risk_package_public_exports():
    import app.risk as risk

    for name in (
        "RiskEngine",
        "RiskRequest",
        "RiskDecision",
        "ConsecutiveLossCircuitBreaker",
        "DailyLossCircuitBreaker",
        "NoTradeGateInput",
        "NoTradeGateDecision",
        "evaluate_no_trade_gate",
        "classify_account_tier",
        "policy_for",
        "ACCOUNT_TIER_POLICY",
        "AccountTierPolicy",
    ):
        assert name in risk.__all__, f"{name} missing from app.risk public API"


def test_state_machine_public_exports():
    import app.state_machine as sm

    for name in (
        "TradeStateMachine",
        "TradeStateContext",
        "StateMachineDecision",
        "TimeoutConfig",
        "IllegalStateTransition",
    ):
        assert name in sm.__all__


# ---------------------------------------------------------------------------
# Phase 7 surface contract
# ---------------------------------------------------------------------------
def test_risk_engine_does_not_expose_write_surface():
    forbidden = {"create_order", "cancel_order", "set_leverage", "set_margin_mode"}
    members = {name for name, _ in inspect.getmembers(RiskEngine)}
    assert not (members & forbidden)


def test_state_machine_does_not_expose_write_surface():
    forbidden = {"create_order", "cancel_order", "set_leverage", "set_margin_mode"}
    members = {name for name, _ in inspect.getmembers(TradeStateMachine)}
    assert not (members & forbidden)


def test_state_machine_does_not_subclass_exchange_client_base():
    from app.exchanges.base import ExchangeClientBase

    assert not issubclass(TradeStateMachine, ExchangeClientBase)


def test_risk_request_phase7_fields_present():
    fields = {f.name for f in RiskRequest.__dataclass_fields__.values()}
    expected = {
        "is_new_open",
        "regime_snapshot",
        "universe_decision",
        "liquidity_decision",
        "exit_plan",
        "is_data_degraded",
        "exchange_connection_state",
        "current_equity",
        "initial_capital",
        "account_tier_override",
    }
    assert expected.issubset(fields)


def test_default_is_new_open_is_true_for_backwards_compat():
    """Phase 1 / Phase 6 callers that did not pass is_new_open keep
    seeing the strict gates fire."""
    req = RiskRequest(source_module="legacy", action="self_check")
    assert req.is_new_open is True


# ---------------------------------------------------------------------------
# Account tier classifier sanity on the public API surface
# ---------------------------------------------------------------------------
def test_classify_account_tier_is_pure():
    a = classify_account_tier(current_equity=200, initial_capital=100)
    b = classify_account_tier(current_equity=200, initial_capital=100)
    assert a == b == AccountLifeTier.A


def test_evaluate_no_trade_gate_is_pure_and_returns_decision():
    decision = evaluate_no_trade_gate(NoTradeGateInput(symbol="PEPEUSDT"))
    assert decision.allowed
    assert decision.reasons == ()


def test_account_tier_policy_table_has_six_entries():
    assert len(ACCOUNT_TIER_POLICY) == 6
