"""Phase 10A - ReplayEngine end-to-end (Issue #10 Part 1).

Drives the Phase 9 Execution FSM driver, the Phase 8 Capital Flow
Engine, and the Phase 1 Telegram skeleton against a real
EventRepository, then replays the resulting events.db.

The Replay Engine is a *read-only* surface; these tests confirm that
the canonical Phase 9 paper trade lifecycle, a Phase 8 capital
rebase, a Phase 7 risk rejection, a Phase 9 P0 incident, a Phase 7
trade-state ladder, a Phase 1 Telegram command, and a Phase 8.5
learning-ready payload are all reachable through the Replay Engine
public API.
"""

from __future__ import annotations

import sqlite3
import uuid
from typing import Iterator

import pytest

from app.capital.flow import CapitalFlowEngine
from app.config.settings import get_settings
from app.core.enums import (
    Direction,
    ManipulationLevel,
    TradeConfirmationLevel,
    TradeState,
    TradeStateTrigger,
)
from app.core.events import Event, EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.execution.fsm import ExecutionFSMDriver
from app.execution.models import (
    OrderIntent,
    OrderKind,
    OrderRequest,
    side_for_direction,
)
from app.execution.paper_ledger import PaperLedger
from app.incidents.repository import IncidentRepository
from app.learning.context import LearningReadyContext
from app.learning.identity import OpportunityIdentity, make_opportunity_id
from app.learning.versions import ConfigVersions
from app.reconciliation.models import (
    LinkHealth,
    LocalSnapshot,
    PositionView,
    RemoteSnapshot,
)
from app.reconciliation.reconciler import Reconciler
from app.replay import (
    CANONICAL_CLOSED_PAPER_TRADE_CHAIN,
    CapitalRebaseReplay,
    LearningReadyReplay,
    P0LatchedPauseInvariantReport,
    PaperTradeReplay,
    ReplayDiffReport,
    ReplayEngine,
)
from app.risk.engine import RiskEngine, RiskRequest
from app.state_machine import TradeStateContext, TradeStateMachine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def wired_set(phase2_dbs: DatabaseSet):
    """Phase 2 DatabaseSet with EventRepository + IncidentRepository wired."""
    repo = EventRepository(phase2_dbs.events, capital_conn=phase2_dbs.capital)
    incidents = IncidentRepository(
        incidents_conn=phase2_dbs.incidents, event_repo=repo
    )
    return repo, incidents, phase2_dbs


@pytest.fixture
def driver(wired_set):
    repo, incidents, _ = wired_set
    settings = get_settings()
    risk = RiskEngine(settings=settings, event_repo=repo)
    paper_ledger = PaperLedger(initial_equity=10_000.0)
    return ExecutionFSMDriver(
        risk_engine=risk,
        event_repo=repo,
        paper_ledger=paper_ledger,
        settings=settings,
        protection_hook=incidents,
    )


def _drive_paper_trade(
    driver: ExecutionFSMDriver,
    *,
    symbol: str = "PEPEUSDT",
    client_order_id: str | None = None,
    opportunity_id: str = "opp_test",
    qty: float = 1.0,
    limit_price: float = 100.0,
    stop_price: float = 98.0,
) -> str:
    """Drive a paper order from IDLE -> POSITION_CLOSED. Returns coid."""
    coid = client_order_id or f"coid_{uuid.uuid4().hex[:12]}"
    request = OrderRequest(
        client_order_id=coid,
        symbol=symbol,
        side=side_for_direction(Direction.LONG, is_close=False),
        kind=OrderKind.LIMIT,
        qty=qty,
        limit_price=limit_price,
        intent=OrderIntent.NEW_OPEN,
        direction=Direction.LONG,
        leverage=1.0,
        stop_price=stop_price,
        opportunity_id=opportunity_id,
    )
    session = driver.simulate_paper_lifecycle(
        request,
        ack_id=f"ack_{coid}",
        fill_price=limit_price,
        stop_price=stop_price,
    )
    driver.trigger_exit(session=session, reason="test_close")
    driver.on_position_closed(session=session, realized_pnl=0.0)
    return coid


# ---------------------------------------------------------------------------
# Acceptance criterion: replay one paper trade
# ---------------------------------------------------------------------------
def test_replay_paper_trade_returns_summary_and_clean_diff(driver, wired_set):
    """Issue #10 Part 10A acceptance: Replay can rebuild one paper trade."""
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)

    engine = ReplayEngine(event_repo=repo)
    replay = engine.replay_paper_trade(client_order_id=coid)

    assert isinstance(replay, PaperTradeReplay)
    assert replay.client_order_id == coid
    assert replay.summary.final_status == "closed"
    # Diff against the canonical closed paper-trade chain MUST be a
    # clean match: every canonical event must be present and the
    # normalised order matches the canonical chain.
    assert replay.diff_against_canonical.matched is True
    assert (
        tuple(replay.diff_against_canonical.expected_chain)
        == CANONICAL_CLOSED_PAPER_TRADE_CHAIN
    )


def test_replay_paper_trade_by_opportunity_id_works(driver, wired_set):
    repo, _, _ = wired_set
    opp_id = make_opportunity_id(opportunity_id="opp_eth_test")
    coid = _drive_paper_trade(
        driver, symbol="ETHUSDT", opportunity_id=opp_id
    )

    engine = ReplayEngine(event_repo=repo)
    replay = engine.replay_paper_trade(opportunity_id=opp_id)
    assert replay.client_order_id == coid


def test_replay_paper_trade_payload_is_json_safe(driver, wired_set):
    import json

    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    engine = ReplayEngine(event_repo=repo)
    payload = engine.replay_paper_trade(client_order_id=coid).to_payload()
    json.dumps(payload, sort_keys=True)  # round-trip


def test_replay_paper_trade_requires_exactly_one_key(driver, wired_set):
    repo, _, _ = wired_set
    engine = ReplayEngine(event_repo=repo)
    with pytest.raises(ValueError):
        engine.replay_paper_trade()
    with pytest.raises(ValueError):
        engine.replay_paper_trade(client_order_id="x", opportunity_id="y")


def test_replay_paper_trade_unknown_id_raises(driver, wired_set):
    repo, _, _ = wired_set
    engine = ReplayEngine(event_repo=repo)
    with pytest.raises(ValueError):
        engine.replay_paper_trade(client_order_id="missing_coid")


# ---------------------------------------------------------------------------
# Acceptance criterion: replay capital rebase
# ---------------------------------------------------------------------------
def test_replay_capital_rebase_after_deposit(wired_set):
    """Issue #10 Part 10A acceptance: Replay can rebuild a capital rebase."""
    repo, _, dbs = wired_set
    capital_engine = CapitalFlowEngine(
        initial_capital=100.0,
        exchange_equity=100.0,
        event_repo=repo,
        capital_conn=dbs.capital,
    )
    capital_engine.deposit(amount=50.0, note="test_top_up")

    engine = ReplayEngine(event_repo=repo)
    rebases = repo.list_events(event_type=EventType.CAPITAL_REBASE)
    assert len(rebases) == 1
    replay = engine.replay_capital_rebase(rebase_event_id=rebases[0].event_id)
    assert isinstance(replay, CapitalRebaseReplay)
    assert replay.trigger == "deposit"
    assert replay.new_exchange_equity == 150.0
    # The related-events window MUST include the CAPITAL_DEPOSIT plus
    # the RISK_BUDGET_RECALCULATED follower.
    related_types = {ev.event_type for ev in replay.related_events}
    assert EventType.CAPITAL_DEPOSIT in related_types
    assert EventType.RISK_BUDGET_RECALCULATED in related_types


def test_replay_capital_rebase_by_timestamp(wired_set):
    repo, _, dbs = wired_set
    cap = CapitalFlowEngine(
        initial_capital=100.0,
        exchange_equity=100.0,
        event_repo=repo,
        capital_conn=dbs.capital,
    )
    cap.deposit(amount=25.0)
    rebase = repo.list_events(event_type=EventType.CAPITAL_REBASE)[0]
    engine = ReplayEngine(event_repo=repo)
    replay = engine.replay_capital_rebase(timestamp=rebase.timestamp)
    assert replay.rebase_event.event_id == rebase.event_id


def test_replay_capital_rebase_requires_exactly_one_key(wired_set):
    repo, _, _ = wired_set
    engine = ReplayEngine(event_repo=repo)
    with pytest.raises(ValueError):
        engine.replay_capital_rebase()
    with pytest.raises(ValueError):
        engine.replay_capital_rebase(rebase_event_id="x", timestamp=1)


def test_replay_capital_rebase_unknown_event_raises(wired_set):
    repo, _, _ = wired_set
    engine = ReplayEngine(event_repo=repo)
    with pytest.raises(ValueError):
        engine.replay_capital_rebase(rebase_event_id="missing")


# ---------------------------------------------------------------------------
# Acceptance criterion: replay risk rejection
# ---------------------------------------------------------------------------
def test_replay_risk_rejection_under_m3(wired_set):
    """Issue #10 Part 10A acceptance: Replay can rebuild risk rejections."""
    repo, _, _ = wired_set
    settings = get_settings()
    risk = RiskEngine(settings=settings, event_repo=repo)

    decision = risk.evaluate(
        RiskRequest(
            source_module="test_replay",
            action="attack_under_m3",
            symbol="PEPEUSDT",
            attack_intent=True,
            is_new_open=True,
            manipulation_level=ManipulationLevel.M3,
        )
    )
    assert decision.rejected
    rejected_events = repo.list_events(event_type=EventType.RISK_REJECTED)
    assert len(rejected_events) >= 1

    engine = ReplayEngine(event_repo=repo)
    replays = engine.replay_risk_rejections(symbol="PEPEUSDT")
    assert len(replays) >= 1
    target = replays[-1]
    assert target.rejected is True
    assert "manipulation_m3" in target.reasons
    assert target.manipulation_level == "M3"
    assert target.is_new_open is True


def test_replay_risk_decision_by_event_id(wired_set):
    repo, _, _ = wired_set
    settings = get_settings()
    risk = RiskEngine(settings=settings, event_repo=repo)
    risk.evaluate(
        RiskRequest(
            source_module="test_replay",
            action="approval",
            symbol="BTCUSDT",
            is_new_open=False,
        )
    )
    approved = repo.list_events(event_type=EventType.RISK_APPROVED)
    target_id = approved[0].event_id

    engine = ReplayEngine(event_repo=repo)
    replay = engine.replay_risk_decision(event_id=target_id)
    assert replay.approved is True
    assert replay.event.event_id == target_id


def test_replay_risk_decision_unknown_event_id_raises(wired_set):
    repo, _, _ = wired_set
    engine = ReplayEngine(event_repo=repo)
    with pytest.raises(ValueError):
        engine.replay_risk_decision(event_id="missing")


# ---------------------------------------------------------------------------
# Acceptance criterion: replay P0 incident
# ---------------------------------------------------------------------------
def test_replay_p0_incident_reconstructs_open_and_resolve(wired_set):
    """Issue #10 Part 10A acceptance: Replay can rebuild P0 incident timeline."""
    from app.core.enums import IncidentLevel

    repo, incidents, _ = wired_set
    incident_id = incidents.open_incident(
        level=IncidentLevel.P0,
        title="ghost_position",
        description="local empty + remote has position",
        source_module="reconciliation",
        symbol="PEPEUSDT",
        payload={"side": "remote_only"},
    )
    incidents.enter_protection_mode(
        reason="reconciliation_p0_mismatch",
        source_module="reconciliation",
    )
    incidents.exit_protection_mode(
        reason="operator_resume",
        source_module="reconciliation",
    )
    incidents.resolve_incident(
        incident_id=incident_id,
        resolution="position_flattened",
        source_module="reconciliation",
    )

    engine = ReplayEngine(event_repo=repo)
    replay = engine.replay_incident(incident_id=incident_id)
    assert replay.incident_id == incident_id
    assert replay.level == "P0"
    assert replay.title == "ghost_position"
    assert replay.open is False
    assert replay.resolution == "position_flattened"
    assert replay.protection_mode_entered is True
    assert replay.protection_mode_exited is True


def test_replay_p0_incidents_lists_only_p0(wired_set):
    from app.core.enums import IncidentLevel

    repo, incidents, _ = wired_set
    incidents.open_incident(
        level=IncidentLevel.P0,
        title="p0_a",
        description="d",
        source_module="t",
    )
    incidents.open_incident(
        level=IncidentLevel.P1,
        title="p1_a",
        description="d",
        source_module="t",
    )
    incidents.open_incident(
        level=IncidentLevel.P0,
        title="p0_b",
        description="d",
        source_module="t",
    )

    engine = ReplayEngine(event_repo=repo)
    replays = engine.replay_p0_incidents()
    assert len(replays) == 2
    assert all(r.level == "P0" for r in replays)


def test_replay_incident_unknown_id_raises(wired_set):
    repo, _, _ = wired_set
    engine = ReplayEngine(event_repo=repo)
    with pytest.raises(ValueError):
        engine.replay_incident(incident_id="missing")


# ---------------------------------------------------------------------------
# Acceptance criterion: replay STATE_TRANSITION
# ---------------------------------------------------------------------------
def test_replay_state_transitions_preserves_chain(wired_set):
    repo, _, _ = wired_set
    sm = TradeStateMachine(symbol="PEPEUSDT", event_repo=repo)
    sm.transition_to(
        TradeState.OBSERVE,
        trigger=TradeStateTrigger.SIGNAL,
        reasons=("test_observe",),
    )
    sm.transition_to(
        TradeState.SCOUT,
        trigger=TradeStateTrigger.PROMOTE,
        reasons=("test_scout",),
    )

    engine = ReplayEngine(event_repo=repo)
    replay = engine.replay_state_transitions(symbol="PEPEUSDT")
    assert "observe" in replay.chain
    assert "scout" in replay.chain
    assert ("no_trade", "observe") in replay.transitions
    assert ("observe", "scout") in replay.transitions


def test_replay_state_transitions_unscoped_returns_all(wired_set):
    repo, _, _ = wired_set
    sm_a = TradeStateMachine(symbol="PEPEUSDT", event_repo=repo)
    sm_b = TradeStateMachine(symbol="BTCUSDT", event_repo=repo)
    sm_a.transition_to(TradeState.OBSERVE, trigger=TradeStateTrigger.SIGNAL)
    sm_b.transition_to(TradeState.OBSERVE, trigger=TradeStateTrigger.SIGNAL)
    engine = ReplayEngine(event_repo=repo)
    replay = engine.replay_state_transitions()
    assert len(replay.events) == 2


# ---------------------------------------------------------------------------
# Acceptance criterion: replay TELEGRAM_COMMAND_RECEIVED
# ---------------------------------------------------------------------------
def test_replay_telegram_commands_filters_correctly(wired_set):
    repo, _, _ = wired_set
    # Emit a few TG command events directly via EventRepository so we
    # don't depend on the bot skeleton's exact wording.
    for name, user in [("/status", "u1"), ("/pnl", "u2"), ("/status", "u3")]:
        repo.append_event(
            Event(
                event_type=EventType.TELEGRAM_COMMAND_RECEIVED,
                source_module="telegram",
                payload={"name": name, "user_id": user, "args": []},
            )
        )

    engine = ReplayEngine(event_repo=repo)
    all_replays = engine.replay_telegram_commands()
    assert len(all_replays) == 3
    status_replays = engine.replay_telegram_commands(name="/status")
    assert len(status_replays) == 2
    user_replays = engine.replay_telegram_commands(user_id="u1")
    assert len(user_replays) == 1
    assert user_replays[0].name == "/status"


# ---------------------------------------------------------------------------
# Acceptance criterion: read Phase 8.5 learning-ready payload
# ---------------------------------------------------------------------------
def test_replay_reads_learning_ready_block(wired_set):
    repo, _, _ = wired_set
    settings = get_settings()
    risk = RiskEngine(settings=settings, event_repo=repo)
    opp = OpportunityIdentity(
        opportunity_id="opp_z",
        scan_batch_id="batch_z",
        symbol="ETHUSDT",
        first_seen_ts=12345,
        source_phase="test_replay",
    )
    versions = ConfigVersions()
    ctx = LearningReadyContext(
        opportunity=opp,
        config_versions=versions,
        source_phase="test",
    )
    risk.evaluate(
        RiskRequest(
            source_module="test_replay",
            action="approval",
            symbol="ETHUSDT",
            is_new_open=False,
            opportunity=opp,
            opportunity_id="opp_z",
            config_versions=versions,
            learning_context=ctx,
        )
    )
    approved = repo.list_events(event_type=EventType.RISK_APPROVED)
    target = approved[-1]
    assert "learning_ready" in target.payload

    engine = ReplayEngine(event_repo=repo)
    replay = engine.extract_learning_ready_for(event_id=target.event_id)
    assert isinstance(replay, LearningReadyReplay)
    assert replay.has_opportunity is True
    assert replay.has_config_versions is True
    assert replay.opportunity_id == "opp_z"


def test_extract_learning_ready_returns_none_for_event_without_block(wired_set):
    repo, _, _ = wired_set
    repo.append_event(
        Event(
            event_type=EventType.MARKET_SNAPSHOT,
            source_module="test",
            payload={},
        )
    )
    target = repo.list_events()[0]
    engine = ReplayEngine(event_repo=repo)
    assert engine.extract_learning_ready_for(event_id=target.event_id) is None


def test_extract_learning_ready_returns_none_for_unknown_event_id(wired_set):
    repo, _, _ = wired_set
    engine = ReplayEngine(event_repo=repo)
    assert engine.extract_learning_ready_for(event_id="missing") is None


def test_find_learning_ready_events_filters_correctly(wired_set):
    repo, _, _ = wired_set
    repo.append_event(
        Event(
            event_type=EventType.RISK_APPROVED,
            source_module="risk_engine",
            payload={
                "learning_ready": {
                    "opportunity": {"opportunity_id": "opp_z"}
                }
            },
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.RISK_APPROVED,
            source_module="risk_engine",
            payload={"reasons": ["paper_only_skeleton_approval"]},
        )
    )
    engine = ReplayEngine(event_repo=repo)
    out = engine.find_learning_ready_events(event_type=EventType.RISK_APPROVED)
    assert len(out) == 1


# ---------------------------------------------------------------------------
# Acceptance criterion: Replay does not trigger trading actions
# ---------------------------------------------------------------------------
def test_replay_does_not_write_to_events_db(driver, wired_set):
    """Replay is read-only: no event is appended during a replay run."""
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    pre_count = repo.count_events()

    engine = ReplayEngine(event_repo=repo)
    engine.replay_paper_trade(client_order_id=coid)
    engine.replay_state_transitions()
    engine.replay_telegram_commands()
    engine.replay_p0_incidents()
    engine.verify_p0_latched_pause_invariant()

    post_count = repo.count_events()
    assert post_count == pre_count


def test_replay_engine_does_not_instantiate_state_mutating_components():
    """Replay must not touch CapitalFlowEngine / ExecutionFSMDriver / etc.

    The :class:`ReplayEngine` constructor takes only an EventRepository
    and exposes no setter for any state-mutating component. This pin
    prevents future drift.
    """
    import inspect

    sig = inspect.signature(ReplayEngine.__init__)
    # Constructor accepts (self, *, event_repo) only.
    params = list(sig.parameters)
    assert params[0] == "self"
    assert "event_repo" in params
    # No other parameter exists (besides *self*).
    assert len(params) == 2


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_replay_paper_trade_is_deterministic_across_runs(driver, wired_set):
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    engine = ReplayEngine(event_repo=repo)
    a = engine.replay_paper_trade(client_order_id=coid)
    b = engine.replay_paper_trade(client_order_id=coid)
    assert a.to_payload() == b.to_payload()


# ---------------------------------------------------------------------------
# diff_event_chains static helper
# ---------------------------------------------------------------------------
def test_diff_event_chains_static_helper_works():
    diff = ReplayEngine.diff_event_chains(["A", "B"], ["A", "B"])
    assert isinstance(diff, ReplayDiffReport)
    assert diff.matched is True
