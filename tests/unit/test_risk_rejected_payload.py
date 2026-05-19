"""Phase 8.5 - RiskRejectedLearningPayload tests (Issue #8.5).

Includes the Risk Engine integration: a request that supplies any
of the new optional fields must produce a RISK_APPROVED /
RISK_REJECTED audit event with the ``learning_ready.risk_decision``
sub-block populated.
"""

from __future__ import annotations

import sqlite3

import pytest

from app.config.settings import get_settings
from app.core.enums import (
    AccountLifeTier,
    Direction,
    ManipulationLevel,
    MarketRegime,
    TradeConfirmationLevel,
)
from app.core.events import EventType
from app.database.migrations import apply_schema
from app.database.repositories import EventRepository
from app.learning import (
    ConfigVersions,
    OpportunityIdentity,
    RiskRejectedLearningPayload,
    VirtualTradePlan,
    risk_rejected_to_payload,
)
from app.learning.risk_payload import reject_reasons_as_strings
from app.risk.engine import RiskEngine, RiskRequest


def _open_repo():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_schema(conn)
    return EventRepository(conn)


def test_risk_rejected_payload_renders_enums_as_strings():
    payload = RiskRejectedLearningPayload(
        opportunity_id="opp_1",
        reject_reasons=("manipulation_m3", "live_trading_disabled"),
        account_life_tier=AccountLifeTier.E,
        regime=MarketRegime.SYSTEMIC_RISK,
        universe_eligible=False,
        liquidity_state="no_exit_channel",
        trade_confirmation_level=TradeConfirmationLevel.T1,
        manipulation_level=ManipulationLevel.M3,
        capital_state_version="capital-2026",
        risk_config_version="risk-2026",
    )
    out = risk_rejected_to_payload(payload)
    assert out["opportunity_id"] == "opp_1"
    assert out["reject_reasons"] == ["manipulation_m3", "live_trading_disabled"]
    assert out["account_life_tier"] == "E"
    assert out["regime"] == "SYSTEMIC_RISK"
    assert out["universe_eligible"] is False
    assert out["liquidity_state"] == "no_exit_channel"
    assert out["trade_confirmation_level"] == "T1"
    assert out["manipulation_level"] == "M3"
    assert out["capital_state_version"] == "capital-2026"
    assert out["risk_config_version"] == "risk-2026"


def test_reject_reasons_as_strings_handles_typed_enums():
    from app.core.enums import RiskRejectReason

    out = reject_reasons_as_strings(
        [RiskRejectReason.LIVE_TRADING_DISABLED, "stop_unconfirmed", None]
    )
    assert out == ("live_trading_disabled", "stop_unconfirmed")


def test_risk_engine_rejected_event_carries_learning_ready_block_when_request_supplies_it():
    repo = _open_repo()
    engine = RiskEngine(settings=get_settings(), event_repo=repo)
    opportunity = OpportunityIdentity.create(
        symbol="PEPEUSDT", source_phase="risk_engine"
    )
    plan = VirtualTradePlan(
        virtual_entry=100.0, virtual_stop=95.0, virtual_tp1=110.0,
        direction=Direction.LONG, setup_type="attack_paper",
    )
    versions = ConfigVersions(
        strategy_version="strat-X",
        risk_config_version="risk-X",
        scoring_version="score-X",
        capital_state_version="capital-X",
        state_machine_version="state-X",
        llm_prompt_version="n/a",
    )
    request = RiskRequest(
        source_module="phase8_5_test",
        action="paper_open_attack",
        symbol="PEPEUSDT",
        live_trading_required=True,  # forces a rejection
        opportunity=opportunity,
        virtual_trade_plan=plan,
        config_versions=versions,
    )
    decision = engine.evaluate(request)
    assert decision.rejected
    rejects = repo.list_events(event_type=EventType.RISK_REJECTED)
    assert len(rejects) == 1
    payload = rejects[0].payload
    # Legacy keys still present.
    assert "reasons" in payload
    assert "live_trading_disabled" in payload["reasons"]
    # Phase 8.5 enrichment present.
    assert "learning_ready" in payload
    learn = payload["learning_ready"]
    assert learn["opportunity"]["opportunity_id"] == opportunity.opportunity_id
    assert learn["opportunity"]["symbol"] == "PEPEUSDT"
    assert learn["virtual_trade_plan"]["virtual_entry"] == 100.0
    assert learn["config_versions"]["strategy_version"] == "strat-X"
    risk_dec = learn["risk_decision"]
    assert risk_dec["opportunity_id"] == opportunity.opportunity_id
    assert "live_trading_disabled" in risk_dec["reject_reasons"]
    assert risk_dec["capital_state_version"] == "capital-X"
    assert risk_dec["risk_config_version"] == "risk-X"


def test_risk_engine_legacy_request_does_not_emit_learning_ready_block():
    repo = _open_repo()
    engine = RiskEngine(settings=get_settings(), event_repo=repo)
    request = RiskRequest(
        source_module="phase1_legacy",
        action="paper_open",
        symbol="BTCUSDT",
    )
    engine.evaluate(request)
    approved = repo.list_events(event_type=EventType.RISK_APPROVED)
    assert len(approved) == 1
    # No learning-ready block when no Phase 8.5 input was provided -
    # legacy callers see byte-compatible payloads.
    assert "learning_ready" not in approved[0].payload


def test_risk_engine_approved_event_carries_learning_ready_when_opportunity_id_provided():
    repo = _open_repo()
    engine = RiskEngine(settings=get_settings(), event_repo=repo)
    request = RiskRequest(
        source_module="phase8_5_test",
        action="paper_observe",
        symbol="ETHUSDT",
        is_new_open=False,
        opportunity_id="opp_explicit",
    )
    decision = engine.evaluate(request)
    assert decision.approved
    approved = repo.list_events(event_type=EventType.RISK_APPROVED)
    payload = approved[0].payload
    assert "learning_ready" in payload
    risk_dec = payload["learning_ready"]["risk_decision"]
    assert risk_dec["opportunity_id"] == "opp_explicit"
    # paper_only_skeleton_approval is the canonical "approved" reason.
    assert "paper_only_skeleton_approval" in risk_dec["reject_reasons"]


def test_risk_engine_explicit_learning_context_takes_precedence():
    from app.learning import LearningReadyContext

    repo = _open_repo()
    engine = RiskEngine(settings=get_settings(), event_repo=repo)
    explicit_versions = ConfigVersions(
        strategy_version="EXPLICIT_STRAT",
        risk_config_version="EXPLICIT_RISK",
        scoring_version="x",
        capital_state_version="x",
        state_machine_version="x",
        llm_prompt_version="n/a",
    )
    ctx = LearningReadyContext(
        config_versions=explicit_versions,
        source_phase="explicit_caller",
    )
    request = RiskRequest(
        source_module="phase8_5_test",
        action="paper_open",
        symbol="PEPEUSDT",
        is_new_open=False,
        learning_context=ctx,
    )
    engine.evaluate(request)
    payload = repo.list_events(event_type=EventType.RISK_APPROVED)[0].payload
    learn = payload["learning_ready"]
    assert learn["config_versions"]["strategy_version"] == "EXPLICIT_STRAT"
    assert learn["source_phase"] == "explicit_caller"
