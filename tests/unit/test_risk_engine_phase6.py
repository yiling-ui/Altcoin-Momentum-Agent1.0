"""Phase 6 - Risk Engine integration tests (Issue #6).

Issue #6 hard rules covered here:

  - M3 -> reject every new opening (Spec §21.3 hard rule "M3 禁止交易")
  - M2 -> reject ATTACK / RIGHT_TAIL_AMPLIFY (Spec §21.3 "M2 禁止进攻")
  - T0 / T1 -> reject ATTACK candidates ("T0/T1 不允许进攻")
"""

from __future__ import annotations

from app.core.enums import (
    ManipulationLevel,
    TradeConfirmationLevel,
)
from app.core.events import EventType
from app.risk.engine import RiskEngine, RiskRequest


# ---------------------------------------------------------------------------
# M3 -> reject EVERY new opening
# ---------------------------------------------------------------------------
def test_m3_rejects_observation_request():
    """Issue #6 acceptance criterion 3: M3 时 Risk Engine 必须拒绝."""
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="test",
            action="open_attack",
            attack_intent=False,
            manipulation_level=ManipulationLevel.M3,
        )
    )
    assert decision.rejected
    assert "manipulation_m3" in decision.reasons


def test_m3_rejects_attack_request():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="test",
            action="open_attack",
            attack_intent=True,
            manipulation_level=ManipulationLevel.M3,
        )
    )
    assert decision.rejected
    assert "manipulation_m3" in decision.reasons


def test_m3_rejection_writes_audit_event(events_repo_with_capital):
    engine = RiskEngine(event_repo=events_repo_with_capital)
    engine.evaluate(
        RiskRequest(
            source_module="test",
            action="open_attack",
            manipulation_level=ManipulationLevel.M3,
        )
    )
    rejected = events_repo_with_capital.list_events(
        event_type=EventType.RISK_REJECTED
    )
    assert len(rejected) == 1
    payload = rejected[0].payload
    assert "manipulation_m3" in payload["reasons"]
    assert payload["manipulation_level"] == ManipulationLevel.M3.value


# ---------------------------------------------------------------------------
# M2 -> reject ATTACK / RIGHT_TAIL_AMPLIFY only
# ---------------------------------------------------------------------------
def test_m2_rejects_attack_intent():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="test",
            action="open_attack",
            attack_intent=True,
            manipulation_level=ManipulationLevel.M2,
        )
    )
    assert decision.rejected
    assert "manipulation_m2_attack" in decision.reasons


def test_m2_does_not_block_observe():
    """M2 forbids ATTACK only; SCOUT / OBSERVE actions remain allowed
    (the regime gate / scoring layer decide whether they actually
    proceed)."""
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="test",
            action="observe",
            attack_intent=False,
            manipulation_level=ManipulationLevel.M2,
        )
    )
    assert decision.approved
    assert decision.reasons == ["paper_only_skeleton_approval"]


def test_right_tail_amplify_implies_attack_intent_under_m2():
    """``right_tail_amplify=True`` always means attack-intent for the
    Phase 6 gate. Even before Phase 1's right-tail rejection fires
    (which it always will in Phase 1+) the M2 gate must also fire."""
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="test",
            action="amplify",
            right_tail_amplify=True,
            attack_intent=False,  # implicitly True via right_tail_amplify
            manipulation_level=ManipulationLevel.M2,
        )
    )
    assert decision.rejected
    assert "manipulation_m2_attack" in decision.reasons
    assert "right_tail_disabled" in decision.reasons  # Phase 1 still fires


# ---------------------------------------------------------------------------
# T0 / T1 -> reject ATTACK candidates
# ---------------------------------------------------------------------------
def test_t0_rejects_attack_intent():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="test",
            action="open_attack",
            attack_intent=True,
            trade_confirmation_level=TradeConfirmationLevel.T0,
        )
    )
    assert decision.rejected
    assert "trade_confirmation_too_low_for_attack" in decision.reasons


def test_t1_rejects_attack_intent():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="test",
            action="open_attack",
            attack_intent=True,
            trade_confirmation_level=TradeConfirmationLevel.T1,
        )
    )
    assert decision.rejected
    assert "trade_confirmation_too_low_for_attack" in decision.reasons


def test_t2_does_not_block_attack_by_itself():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="test",
            action="open_attack",
            attack_intent=True,
            trade_confirmation_level=TradeConfirmationLevel.T2,
        )
    )
    assert decision.approved


def test_t1_does_not_block_observe():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="test",
            action="observe",
            attack_intent=False,
            trade_confirmation_level=TradeConfirmationLevel.T1,
        )
    )
    assert decision.approved


# ---------------------------------------------------------------------------
# Phase 6 gates compose correctly with Phase 1 hard rejections
# ---------------------------------------------------------------------------
def test_m3_and_phase1_flags_accumulate():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="test",
            action="open_attack",
            live_trading_required=True,
            stop_unconfirmed=True,
            attack_intent=True,
            manipulation_level=ManipulationLevel.M3,
            trade_confirmation_level=TradeConfirmationLevel.T0,
        )
    )
    assert decision.rejected
    for reason in (
        "live_trading_disabled",
        "stop_unconfirmed",
        "manipulation_m3",
        "trade_confirmation_too_low_for_attack",
    ):
        assert reason in decision.reasons


def test_clean_request_with_t3_m0_is_approved():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="test",
            action="open_attack",
            attack_intent=True,
            manipulation_level=ManipulationLevel.M0,
            trade_confirmation_level=TradeConfirmationLevel.T3,
        )
    )
    assert decision.approved
    assert decision.reasons == ["paper_only_skeleton_approval"]


def test_no_phase6_levels_supplied_is_backwards_compatible():
    """Existing Phase 1-5 callers do not have to set the new fields."""
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(source_module="legacy", action="self_check")
    )
    assert decision.approved
    # Audit payload still records the new fields with safe defaults.


def test_audit_payload_includes_new_fields(events_repo_with_capital):
    engine = RiskEngine(event_repo=events_repo_with_capital)
    engine.evaluate(
        RiskRequest(
            source_module="test",
            action="observe",
            attack_intent=False,
            manipulation_level=ManipulationLevel.M1,
            trade_confirmation_level=TradeConfirmationLevel.T2,
        )
    )
    approved = events_repo_with_capital.list_events(event_type=EventType.RISK_APPROVED)
    assert len(approved) == 1
    payload = approved[0].payload
    assert payload["manipulation_level"] == "M1"
    assert payload["trade_confirmation_level"] == "T2"
    assert payload["attack_intent"] is False
