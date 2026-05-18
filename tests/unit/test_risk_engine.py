"""Phase 1 Risk Engine skeleton tests."""

from __future__ import annotations

from app.core.events import EventType
from app.risk.engine import RiskEngine, RiskRequest


def test_paper_request_is_approved(events_repo, phase1_settings):
    engine = RiskEngine(settings=phase1_settings, event_repo=events_repo)
    decision = engine.evaluate(
        RiskRequest(source_module="strategy", action="observe", symbol="PEPEUSDT")
    )
    assert decision.approved is True
    assert decision.reasons == ["paper_only_skeleton_approval"]
    [event] = events_repo.list(event_type=EventType.RISK_APPROVED)
    assert event.symbol == "PEPEUSDT"


def test_live_required_request_is_rejected_in_phase1(events_repo, phase1_settings):
    engine = RiskEngine(settings=phase1_settings, event_repo=events_repo)
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_position",
            symbol="BTCUSDT",
            live_trading_required=True,
        )
    )
    assert decision.approved is False
    assert "live_trading_disabled" in decision.reasons
    rejections = events_repo.list(event_type=EventType.RISK_REJECTED)
    assert len(rejections) == 1


def test_right_tail_request_is_rejected_in_phase1(events_repo, phase1_settings):
    engine = RiskEngine(settings=phase1_settings, event_repo=events_repo)
    decision = engine.evaluate(
        RiskRequest(
            source_module="tail_manager",
            action="amplify",
            right_tail_amplify=True,
        )
    )
    assert decision.approved is False
    assert "right_tail_disabled" in decision.reasons


def test_event_repo_optional(phase1_settings):
    """Engine must work without a repository (boot order)."""
    engine = RiskEngine(settings=phase1_settings)
    decision = engine.evaluate(RiskRequest(source_module="x", action="observe"))
    assert decision.approved is True
