"""Phase 8.5 - LearningReadyContext + attach_learning_ready tests
(Issue #8.5)."""

from __future__ import annotations

import json

from app.core.enums import (
    AccountLifeTier,
    Direction,
    ManipulationLevel,
    MarketRegime,
    TradeConfirmationLevel,
)
from app.core.events import EventType
from app.core.models import SignalSnapshot
from app.learning import (
    LEARNING_READY_EVENT_TYPES,
    LEARNING_READY_KEY,
    ConfigVersions,
    LearningReadyContext,
    OpportunityIdentity,
    RiskRejectedLearningPayload,
    VirtualTradePlan,
    attach_learning_ready,
)
from app.learning.context import is_learning_ready_event_type


def test_learning_ready_event_types_include_all_eleven_spec_types():
    expected = {
        EventType.PRE_ANOMALY_DETECTED,
        EventType.ANOMALY_DETECTED,
        EventType.TRADE_CONFIRMED,
        EventType.MANIPULATION_DETECTED,
        EventType.UNIVERSE_FILTERED,
        EventType.LIQUIDITY_CHECKED,
        EventType.RISK_APPROVED,
        EventType.RISK_REJECTED,
        EventType.STATE_TRANSITION,
        EventType.CAPITAL_REBASE,
        EventType.RISK_BUDGET_RECALCULATED,
    }
    assert set(LEARNING_READY_EVENT_TYPES) == expected
    assert len(LEARNING_READY_EVENT_TYPES) == 11


def test_is_learning_ready_event_type_predicate():
    for et in LEARNING_READY_EVENT_TYPES:
        assert is_learning_ready_event_type(et)
    # ORDER_SENT is NOT in the learning-ready set per Issue #8.5.
    assert not is_learning_ready_event_type(EventType.ORDER_SENT)


def test_learning_ready_key_constant_is_stable():
    assert LEARNING_READY_KEY == "learning_ready"


def test_attach_learning_ready_with_none_returns_copy_of_payload():
    payload = {"foo": 1, "bar": ["a"]}
    out = attach_learning_ready(payload, None)
    assert out == payload
    out["foo"] = 2
    assert payload["foo"] == 1  # original unmutated


def test_attach_learning_ready_does_not_mutate_input_payload():
    payload = {"foo": 1}
    ctx = LearningReadyContext(
        opportunity=OpportunityIdentity.create(
            symbol="ETHUSDT", source_phase="anomaly"
        )
    )
    out = attach_learning_ready(payload, ctx)
    assert "learning_ready" in out
    assert "learning_ready" not in payload  # original unmutated


def test_attach_learning_ready_preserves_existing_keys():
    payload = {"reasons": ["live_trading_disabled"], "is_new_open": True}
    ctx = LearningReadyContext(
        config_versions=ConfigVersions.defaults(),
    )
    merged = attach_learning_ready(payload, ctx)
    assert merged["reasons"] == ["live_trading_disabled"]
    assert merged["is_new_open"] is True
    assert "config_versions" in merged["learning_ready"]


def test_learning_ready_context_to_event_payload_handles_full_context():
    snap = SignalSnapshot(
        symbol="PEPEUSDT", timestamp=1_700_000_000_000,
        regime=MarketRegime.MEME_RISK_ON,
    )
    ctx = LearningReadyContext(
        opportunity=OpportunityIdentity.create(
            symbol="PEPEUSDT", source_phase="risk_engine"
        ),
        signal_snapshot=snap,
        virtual_trade_plan=VirtualTradePlan(
            virtual_entry=1.0, virtual_stop=0.9, virtual_tp1=1.5,
            direction=Direction.LONG, setup_type="scout_breakout",
        ),
        config_versions=ConfigVersions.defaults(),
        risk_decision=RiskRejectedLearningPayload(
            opportunity_id="opp_1",
            reject_reasons=("manipulation_m3",),
            account_life_tier=AccountLifeTier.B,
            regime=MarketRegime.MEME_RISK_ON,
            universe_eligible=False,
            liquidity_state="rejected",
            trade_confirmation_level=TradeConfirmationLevel.T3,
            manipulation_level=ManipulationLevel.M3,
            capital_state_version="capital-x",
            risk_config_version="risk-x",
            is_new_open=True,
            attack_intent=True,
        ),
        source_phase="risk_engine",
    )
    body = ctx.to_event_payload()
    assert "opportunity" in body
    assert "signal_snapshot" in body
    assert "virtual_trade_plan" in body
    assert "config_versions" in body
    assert "risk_decision" in body
    assert body["source_phase"] == "risk_engine"
    # JSON safe
    json.dumps(body, sort_keys=True)


def test_learning_ready_context_omits_empty_fields():
    ctx = LearningReadyContext()
    body = ctx.to_event_payload()
    assert body == {}


def test_learning_ready_context_extra_field_round_trip():
    ctx = LearningReadyContext(extra={"note": "phase8_5_boot"})
    body = ctx.to_event_payload()
    assert body["extra"] == {"note": "phase8_5_boot"}
