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


def test_stop_unconfirmed_request_is_rejected(events_repo, phase1_settings):
    """Spec §4.2 + §27.2: no new positions while stop is unconfirmed."""
    engine = RiskEngine(settings=phase1_settings, event_repo=events_repo)
    decision = engine.evaluate(
        RiskRequest(
            source_module="execution_fsm",
            action="open_position",
            symbol="ETHUSDT",
            stop_unconfirmed=True,
        )
    )
    assert decision.approved is False
    assert "stop_unconfirmed" in decision.reasons
    [event] = events_repo.list(event_type=EventType.RISK_REJECTED)
    assert event.payload["stop_unconfirmed"] is True


def test_unknown_position_request_is_rejected(events_repo, phase1_settings):
    """Spec §31.3: position state unknown -> trading forbidden."""
    engine = RiskEngine(settings=phase1_settings, event_repo=events_repo)
    decision = engine.evaluate(
        RiskRequest(
            source_module="reconciliation",
            action="open_position",
            symbol="SOLUSDT",
            unknown_position=True,
        )
    )
    assert decision.approved is False
    assert "unknown_position" in decision.reasons


def test_multiple_rejection_reasons_accumulate(events_repo, phase1_settings):
    """All applicable rejection reasons should appear together."""
    engine = RiskEngine(settings=phase1_settings, event_repo=events_repo)
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="amplify",
            symbol="PEPEUSDT",
            live_trading_required=True,
            right_tail_amplify=True,
            stop_unconfirmed=True,
            unknown_position=True,
        )
    )
    assert decision.approved is False
    for r in (
        "live_trading_disabled",
        "right_tail_disabled",
        "stop_unconfirmed",
        "unknown_position",
    ):
        assert r in decision.reasons
