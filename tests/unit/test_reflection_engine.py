"""Phase 10B - ReflectionEngine end-to-end (Issue #10 Part 2).

Drives the Phase 9 ExecutionFSMDriver against a real EventRepository
to produce a Phase 9 paper-trade lifecycle, then reflects on it via
the Phase 10A ReplayEngine + the Phase 10B ReflectionEngine.

The Reflection Engine is *read-only*; these tests confirm that:

  - Reflection consumes the Phase 10A Replay output.
  - mistake_tags fire on the deterministic conditions documented
    in the engine docstring.
  - MFE / MAE / tail_contribution return ``None`` plus typed reason
    codes when data is insufficient (NEVER a fabricated number).
  - ``learning_ready`` is read back when supplied.
  - The Reflection run does NOT write to events.db.
  - The result is JSON-safe.
"""

from __future__ import annotations

import dataclasses
import json
import uuid

import pytest

from app.config.settings import get_settings
from app.core.enums import (
    Direction,
    ManipulationLevel,
    TradeState,
    TradeStateTrigger,
)
from app.core.events import Event, EventType
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
from app.learning.identity import OpportunityIdentity
from app.learning.versions import ConfigVersions
from app.learning.virtual_trade import VirtualTradePlan
from app.reflection import (
    ISSUE_REQUIRED_MISTAKE_TAGS,
    MistakeTag,
    QualityScore,
    ReflectionEngine,
    ReflectionInput,
    ReflectionResult,
    TradeOutcome,
    UnknownReason,
)
from app.replay import (
    PaperTradeReplay,
    ReplayEngine,
    StateTransitionReplay,
)
from app.risk.engine import RiskEngine, RiskRequest
from app.state_machine import TradeStateMachine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def wired_set(phase2_dbs):
    from app.database.repositories import EventRepository

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
    fill_price: float | None = None,
) -> str:
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
        fill_price=fill_price if fill_price is not None else limit_price,
        stop_price=stop_price,
    )
    driver.trigger_exit(session=session, reason="test_close")
    driver.on_position_closed(session=session, realized_pnl=0.0)
    return coid


# ---------------------------------------------------------------------------
# Acceptance criterion 1: Reflection consumes ReplayEngine output
# ---------------------------------------------------------------------------
def test_reflect_paper_trade_returns_reflection_result(driver, wired_set):
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect_paper_trade(client_order_id=coid)
    assert isinstance(result, ReflectionResult)
    assert result.client_order_id == coid
    assert result.symbol == "PEPEUSDT"
    assert result.result is TradeOutcome.BREAKEVEN  # PnL = 0 in helper
    assert result.source_event_ids  # at least one id


def test_reflect_paper_trade_payload_is_json_safe(driver, wired_set):
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    payload = engine.reflect_paper_trade(client_order_id=coid).to_payload()
    json.dumps(payload, sort_keys=True)


def test_reflection_engine_can_be_built_from_event_repo(wired_set):
    repo, _, _ = wired_set
    engine = ReflectionEngine(event_repo=repo)
    assert engine.replay.event_repo is repo


def test_reflection_engine_requires_replay_or_event_repo():
    with pytest.raises(ValueError):
        ReflectionEngine()


# ---------------------------------------------------------------------------
# Acceptance criterion 2: outputs mistake_tags
# ---------------------------------------------------------------------------
def test_reflection_result_mistake_tags_drawn_from_frozen_vocabulary(
    driver, wired_set
):
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect_paper_trade(client_order_id=coid)
    for tag in result.mistake_tags:
        assert isinstance(tag, MistakeTag)


def test_clean_paper_trade_does_not_fire_issue_required_tags(driver, wired_set):
    """A clean Phase 9 paper-trade lifecycle must not fire any of the
    12 Issue-required mistake_tags. Diagnostic tags (e.g.
    insufficient_data) MAY land because the helper trade has no
    virtual_trade_plan / signal_snapshot."""
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect_paper_trade(client_order_id=coid)
    fired_required = set(result.mistake_tags) & ISSUE_REQUIRED_MISTAKE_TAGS
    assert fired_required == set()


# ---------------------------------------------------------------------------
# Acceptance criterion 3: MFE / MAE / tail_contribution: data insufficient
# ---------------------------------------------------------------------------
def test_clean_paper_trade_returns_none_mfe_mae_with_typed_reason(
    driver, wired_set
):
    """Phase 9 paper-mode keeps only entry / fill / stop / exit
    landmarks. Without continuous price observations or favourable /
    adverse movement Phase 10B reports None + INSUFFICIENT_PRICE_PATH."""
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect_paper_trade(client_order_id=coid)
    assert result.mfe is None
    assert result.mae is None
    # Some flavour of the typed UnknownReason vocabulary MUST be
    # attached - the engine never invents a free-form reason.
    assert all(isinstance(r, UnknownReason) for r in result.data_quality_notes)
    assert UnknownReason.INSUFFICIENT_PRICE_PATH in result.data_quality_notes


def test_tail_contribution_is_zero_when_plan_present_and_no_rta(
    driver, wired_set
):
    """When a virtual_trade_plan is supplied AND no RTA was reached we
    can confidently say tail_contribution == 0."""
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    paper_trade = ReplayEngine(event_repo=repo).replay_paper_trade(
        client_order_id=coid
    )
    plan = VirtualTradePlan(
        virtual_entry=100.0,
        virtual_stop=98.0,
        virtual_tp1=110.0,
        virtual_tp2=120.0,
        suggested_leverage=1.0,
        risk_budget_pct=0.01,
        direction=Direction.LONG,
        setup_type="breakout_momentum",
    )
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect(
        ReflectionInput(
            paper_trade=paper_trade,
            risk_decisions=(),
            state_transitions=None,
            incidents=(),
            learning_ready={
                "virtual_trade_plan": plan.to_payload(),
                "config_versions": ConfigVersions().to_payload(),
            },
        )
    )
    assert result.tail_contribution == 0.0
    assert UnknownReason.NO_VIRTUAL_TRADE_PLAN not in result.data_quality_notes


def test_tail_contribution_unknown_when_no_plan_and_no_rta(driver, wired_set):
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect_paper_trade(client_order_id=coid)
    assert result.tail_contribution is None
    assert (
        UnknownReason.NO_VIRTUAL_TRADE_PLAN in result.data_quality_notes
        or UnknownReason.NO_RIGHT_TAIL_AMPLIFY_LIFECYCLE
        in result.data_quality_notes
    )


# ---------------------------------------------------------------------------
# Acceptance criterion 4: read learning_ready payload
# ---------------------------------------------------------------------------
def test_reflection_consumes_caller_supplied_learning_ready(driver, wired_set):
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    paper_trade = ReplayEngine(event_repo=repo).replay_paper_trade(
        client_order_id=coid
    )
    opp = OpportunityIdentity(
        opportunity_id="opp_test",
        scan_batch_id="batch_test",
        symbol="PEPEUSDT",
        first_seen_ts=12345,
        source_phase="test",
    )
    plan = VirtualTradePlan(
        virtual_entry=100.0,
        virtual_stop=98.0,
        virtual_tp1=110.0,
        virtual_tp2=120.0,
        suggested_leverage=1.0,
        risk_budget_pct=0.01,
        direction=Direction.LONG,
        setup_type="breakout_momentum",
    )
    ctx = LearningReadyContext(
        opportunity=opp,
        virtual_trade_plan=plan,
        config_versions=ConfigVersions(),
        source_phase="test",
    )
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect(
        ReflectionInput(
            paper_trade=paper_trade,
            learning_ready=ctx.to_event_payload(),
        )
    )
    assert result.learning_ready is not None
    assert "virtual_trade_plan" in result.learning_ready
    assert result.setup == "breakout_momentum"


# ---------------------------------------------------------------------------
# Acceptance criterion 5: read virtual_trade_plan
# ---------------------------------------------------------------------------
def test_late_entry_fires_when_fill_diverges_from_virtual_entry(driver, wired_set):
    """fill_price = 105 vs virtual_entry = 100 -> 5% above the default
    0.5% threshold."""
    repo, _, _ = wired_set
    coid = _drive_paper_trade(
        driver,
        limit_price=105.0,
        fill_price=105.0,
    )
    paper_trade = ReplayEngine(event_repo=repo).replay_paper_trade(
        client_order_id=coid
    )
    plan = VirtualTradePlan(
        virtual_entry=100.0,
        virtual_stop=98.0,
        virtual_tp1=110.0,
        virtual_tp2=120.0,
        direction=Direction.LONG,
        setup_type="breakout_momentum",
    )
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect(
        ReflectionInput(
            paper_trade=paper_trade,
            learning_ready={"virtual_trade_plan": plan.to_payload()},
        )
    )
    assert MistakeTag.LATE_ENTRY in result.mistake_tags


# ---------------------------------------------------------------------------
# Acceptance criterion 6: stop_not_confirmed
# ---------------------------------------------------------------------------
def test_stop_not_confirmed_fires_when_stop_failed_event_lands(wired_set):
    """Synthesise a paper-trade event chain with STOP_FAILED. The
    engine MUST fire stop_not_confirmed."""
    repo, _, _ = wired_set
    coid = "coid_synth_stop_fail"
    opp = "opp_synth"
    base_ts = 1_000_000
    events_written: list[Event] = []
    for offset, et in enumerate(
        [
            EventType.ORDER_SENT,
            EventType.ORDER_ACK,
            EventType.ORDER_FILLED,
            EventType.STOP_SENT,
            EventType.STOP_FAILED,
        ]
    ):
        if et is EventType.ORDER_SENT:
            payload = {
                "client_order_id": coid,
                "opportunity_id": opp,
                "symbol": "PEPEUSDT",
                "intent": "new_open",
                "request": {
                    "client_order_id": coid,
                    "symbol": "PEPEUSDT",
                    "side": "buy",
                    "kind": "limit",
                    "qty": 1.0,
                    "limit_price": 100.0,
                    "max_slippage_pct": 0.005,
                    "direction": "long",
                },
            }
        elif et is EventType.ORDER_FILLED:
            payload = {
                "client_order_id": coid,
                "opportunity_id": opp,
                "avg_fill_price": 100.0,
            }
        else:
            payload = {"client_order_id": coid, "opportunity_id": opp}
        events_written.append(
            repo.append_event(
                Event(
                    event_type=et,
                    source_module="test",
                    payload=payload,
                    symbol="PEPEUSDT",
                    order_id=coid,
                    timestamp=base_ts + offset,
                )
            )
        )
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect_paper_trade(client_order_id=coid)
    assert MistakeTag.STOP_NOT_CONFIRMED in result.mistake_tags


# ---------------------------------------------------------------------------
# Acceptance criterion 7: ignored_no_trade_gate
# ---------------------------------------------------------------------------
def test_ignored_no_trade_gate_fires_when_risk_rejected_then_order_sent(
    wired_set,
):
    """A RISK_REJECTED for the same opportunity_id followed by an
    ORDER_SENT for the same opportunity is a hard contract violation;
    the engine fires `ignored_no_trade_gate`."""
    repo, _, _ = wired_set
    opp = "opp_gate_violation"
    coid = "coid_gate_violation"
    base_ts = 1_000_000
    repo.append_event(
        Event(
            event_type=EventType.RISK_REJECTED,
            source_module="risk_engine",
            payload={
                "reasons": ["manipulation_m3"],
                "manipulation_level": "M3",
                "is_new_open": True,
                "attack_intent": True,
                "opportunity_id": opp,
            },
            symbol="PEPEUSDT",
            timestamp=base_ts,
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.ORDER_SENT,
            source_module="execution",
            payload={
                "client_order_id": coid,
                "opportunity_id": opp,
                "intent": "new_open",
                "request": {
                    "client_order_id": coid,
                    "symbol": "PEPEUSDT",
                    "side": "buy",
                    "kind": "limit",
                    "qty": 1.0,
                    "limit_price": 100.0,
                    "max_slippage_pct": 0.005,
                    "direction": "long",
                },
            },
            symbol="PEPEUSDT",
            order_id=coid,
            timestamp=base_ts + 1_000,
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.ORDER_FILLED,
            source_module="execution",
            payload={
                "client_order_id": coid,
                "opportunity_id": opp,
                "avg_fill_price": 100.0,
            },
            symbol="PEPEUSDT",
            order_id=coid,
            timestamp=base_ts + 2_000,
        )
    )
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect_paper_trade(client_order_id=coid)
    assert MistakeTag.IGNORED_NO_TRADE_GATE in result.mistake_tags


# ---------------------------------------------------------------------------
# Acceptance criterion 8: Reflection does not write to events.db
# ---------------------------------------------------------------------------
def test_reflection_run_does_not_append_events(driver, wired_set):
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    pre = repo.count_events()
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    engine.reflect_paper_trade(client_order_id=coid)
    post = repo.count_events()
    assert post == pre


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_reflection_is_deterministic_across_runs(driver, wired_set):
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    a = engine.reflect_paper_trade(client_order_id=coid).to_payload()
    b = engine.reflect_paper_trade(client_order_id=coid).to_payload()
    # generated_at lands at now_ms() so we strip it before comparing.
    a.pop("generated_at", None)
    b.pop("generated_at", None)
    assert a == b


# ---------------------------------------------------------------------------
# slippage_error
# ---------------------------------------------------------------------------
def test_slippage_error_fires_when_fill_diverges_beyond_max_slippage(
    wired_set,
):
    repo, _, _ = wired_set
    coid = "coid_slippage"
    base_ts = 2_000_000
    repo.append_event(
        Event(
            event_type=EventType.ORDER_SENT,
            source_module="execution",
            payload={
                "client_order_id": coid,
                "intent": "new_open",
                "request": {
                    "client_order_id": coid,
                    "symbol": "PEPEUSDT",
                    "side": "buy",
                    "kind": "limit",
                    "qty": 1.0,
                    "limit_price": 100.0,
                    "max_slippage_pct": 0.005,
                    "direction": "long",
                },
            },
            symbol="PEPEUSDT",
            order_id=coid,
            timestamp=base_ts,
        )
    )
    # Fill price 102.0 vs limit 100.0 -> 2% slippage, well above 0.5%.
    repo.append_event(
        Event(
            event_type=EventType.ORDER_FILLED,
            source_module="execution",
            payload={
                "client_order_id": coid,
                "avg_fill_price": 102.0,
            },
            symbol="PEPEUSDT",
            order_id=coid,
            timestamp=base_ts + 1,
        )
    )
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect_paper_trade(client_order_id=coid)
    assert MistakeTag.SLIPPAGE_ERROR in result.mistake_tags
    # entry_quality is LOW because slippage_error fired.
    assert result.entry_quality is QualityScore.LOW


# ---------------------------------------------------------------------------
# execution_delay
# ---------------------------------------------------------------------------
def test_execution_delay_fires_when_ack_lags_send(wired_set):
    repo, _, _ = wired_set
    coid = "coid_exec_delay"
    repo.append_event(
        Event(
            event_type=EventType.ORDER_SENT,
            source_module="execution",
            payload={
                "client_order_id": coid,
                "intent": "new_open",
                "request": {
                    "client_order_id": coid,
                    "symbol": "PEPEUSDT",
                    "side": "buy",
                    "kind": "limit",
                    "qty": 1.0,
                    "limit_price": 100.0,
                    "max_slippage_pct": 0.005,
                    "direction": "long",
                },
            },
            symbol="PEPEUSDT",
            order_id=coid,
            timestamp=3_000_000,
        )
    )
    # ACK arrives 5_000ms later - well above the 1500ms threshold.
    repo.append_event(
        Event(
            event_type=EventType.ORDER_ACK,
            source_module="execution",
            payload={"client_order_id": coid},
            symbol="PEPEUSDT",
            order_id=coid,
            timestamp=3_000_000 + 5_000,
        )
    )
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect_paper_trade(client_order_id=coid)
    assert MistakeTag.EXECUTION_DELAY in result.mistake_tags


# ---------------------------------------------------------------------------
# weak_volume / high_trap_score (signal_snapshot driven)
# ---------------------------------------------------------------------------
def test_weak_volume_fires_when_signal_snapshot_anomaly_below_threshold(
    driver, wired_set
):
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    paper_trade = ReplayEngine(event_repo=repo).replay_paper_trade(
        client_order_id=coid
    )
    learning_ready = {
        "signal_snapshot": {
            "symbol": "PEPEUSDT",
            "anomaly_score": 10.0,
            "no_trade_reason": [],
        },
    }
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect(
        ReflectionInput(
            paper_trade=paper_trade, learning_ready=learning_ready
        )
    )
    assert MistakeTag.WEAK_VOLUME in result.mistake_tags


def test_high_trap_score_fires_on_explicit_trap_score(driver, wired_set):
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    paper_trade = ReplayEngine(event_repo=repo).replay_paper_trade(
        client_order_id=coid
    )
    learning_ready = {
        "signal_snapshot": {
            "symbol": "PEPEUSDT",
            "anomaly_score": 80.0,
            "trap_score": 0.9,
        },
    }
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect(
        ReflectionInput(
            paper_trade=paper_trade, learning_ready=learning_ready
        )
    )
    assert MistakeTag.HIGH_TRAP_SCORE in result.mistake_tags


def test_high_trap_score_fires_on_no_trade_reason_substring(driver, wired_set):
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    paper_trade = ReplayEngine(event_repo=repo).replay_paper_trade(
        client_order_id=coid
    )
    learning_ready = {
        "signal_snapshot": {
            "symbol": "PEPEUSDT",
            "anomaly_score": 80.0,
            "no_trade_reason": ["trap_distribution_alert"],
        },
    }
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect(
        ReflectionInput(
            paper_trade=paper_trade, learning_ready=learning_ready
        )
    )
    assert MistakeTag.HIGH_TRAP_SCORE in result.mistake_tags


# ---------------------------------------------------------------------------
# fake_breakout (state-chain driven)
# ---------------------------------------------------------------------------
def test_fake_breakout_fires_on_confirm_then_observe_state_chain(
    driver, wired_set
):
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    paper_trade = ReplayEngine(event_repo=repo).replay_paper_trade(
        client_order_id=coid
    )
    state_replay = StateTransitionReplay(
        symbol="PEPEUSDT",
        events=(),
        chain=("scout", "confirm", "observe"),
        transitions=(("scout", "confirm"), ("confirm", "observe")),
    )
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect(
        ReflectionInput(
            paper_trade=paper_trade, state_transitions=state_replay
        )
    )
    assert MistakeTag.FAKE_BREAKOUT in result.mistake_tags


# ---------------------------------------------------------------------------
# tail tags (right_tail_amplify driven)
# ---------------------------------------------------------------------------
def test_tail_saved_trade_fires_when_rta_reached_and_pnl_positive(wired_set):
    """Synthesise a closed paper trade with realized_pnl>0 + RTA in the
    state chain."""
    repo, _, _ = wired_set
    coid = "coid_rta_win"
    base = 4_000_000
    repo.append_event(
        Event(
            event_type=EventType.ORDER_SENT,
            source_module="execution",
            payload={
                "client_order_id": coid,
                "intent": "new_open",
                "request": {
                    "client_order_id": coid,
                    "symbol": "PEPEUSDT",
                    "side": "buy",
                    "kind": "limit",
                    "qty": 1.0,
                    "limit_price": 100.0,
                    "max_slippage_pct": 0.005,
                    "direction": "long",
                },
            },
            symbol="PEPEUSDT",
            order_id=coid,
            timestamp=base,
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.ORDER_FILLED,
            source_module="execution",
            payload={"client_order_id": coid, "avg_fill_price": 100.0},
            symbol="PEPEUSDT",
            order_id=coid,
            timestamp=base + 1,
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.STOP_SENT,
            source_module="execution",
            payload={"client_order_id": coid},
            symbol="PEPEUSDT",
            order_id=coid,
            timestamp=base + 2,
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.STOP_CONFIRMED,
            source_module="execution",
            payload={"client_order_id": coid, "stop_price": 98.0},
            symbol="PEPEUSDT",
            order_id=coid,
            timestamp=base + 3,
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.POSITION_OPENED,
            source_module="execution",
            payload={"client_order_id": coid, "entry_price": 100.0},
            symbol="PEPEUSDT",
            order_id=coid,
            timestamp=base + 4,
        )
    )
    repo.append_event(
        Event(
            event_type=EventType.POSITION_CLOSED,
            source_module="execution",
            payload={
                "client_order_id": coid,
                "exit_price": 130.0,
                "realized_pnl": 30.0,
                "tail_pnl": 20.0,
            },
            symbol="PEPEUSDT",
            order_id=coid,
            timestamp=base + 5,
        )
    )
    paper_trade = ReplayEngine(event_repo=repo).replay_paper_trade(
        client_order_id=coid
    )
    state_replay = StateTransitionReplay(
        symbol="PEPEUSDT",
        events=(),
        chain=("attack", "right_tail_amplify", "lock_profit"),
        transitions=(
            ("attack", "right_tail_amplify"),
            ("right_tail_amplify", "lock_profit"),
        ),
    )
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect(
        ReflectionInput(
            paper_trade=paper_trade,
            state_transitions=state_replay,
            learning_ready={
                "virtual_trade_plan": {
                    "virtual_entry": 100.0,
                    "virtual_stop": 98.0,
                    "virtual_tp1": 110.0,
                    "virtual_tp2": 125.0,
                    "direction": "long",
                    "setup_type": "right_tail_amplify",
                }
            },
        )
    )
    assert MistakeTag.TAIL_SAVED_TRADE in result.mistake_tags
    # And the explicit tail_pnl is read directly.
    assert result.tail_contribution == 20.0
    # Right-tail target of 125 hit by exit 130.
    assert MistakeTag.RIGHT_TAIL_SUCCESS in result.mistake_tags


def test_tail_failed_fires_when_rta_reached_and_pnl_negative(wired_set):
    repo, _, _ = wired_set
    coid = "coid_rta_loss"
    base = 5_000_000
    for offset, ev_type, payload in [
        (0, EventType.ORDER_SENT, {
            "client_order_id": coid, "intent": "new_open",
            "request": {
                "client_order_id": coid, "symbol": "PEPEUSDT", "side": "buy",
                "kind": "limit", "qty": 1.0, "limit_price": 100.0,
                "max_slippage_pct": 0.005, "direction": "long",
            },
        }),
        (1, EventType.ORDER_FILLED, {"client_order_id": coid, "avg_fill_price": 100.0}),
        (2, EventType.STOP_SENT, {"client_order_id": coid}),
        (3, EventType.STOP_CONFIRMED, {"client_order_id": coid, "stop_price": 98.0}),
        (4, EventType.POSITION_OPENED, {"client_order_id": coid, "entry_price": 100.0}),
        (5, EventType.POSITION_CLOSED, {
            "client_order_id": coid, "exit_price": 95.0, "realized_pnl": -5.0
        }),
    ]:
        repo.append_event(
            Event(
                event_type=ev_type,
                source_module="execution",
                payload=payload,
                symbol="PEPEUSDT",
                order_id=coid,
                timestamp=base + offset,
            )
        )
    paper_trade = ReplayEngine(event_repo=repo).replay_paper_trade(
        client_order_id=coid
    )
    state_replay = StateTransitionReplay(
        symbol="PEPEUSDT",
        events=(),
        chain=("attack", "right_tail_amplify"),
        transitions=(("attack", "right_tail_amplify"),),
    )
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect(
        ReflectionInput(
            paper_trade=paper_trade,
            state_transitions=state_replay,
        )
    )
    assert MistakeTag.TAIL_FAILED in result.mistake_tags
    assert MistakeTag.RIGHT_TAIL_SUCCESS not in result.mistake_tags


# ---------------------------------------------------------------------------
# Setup label / source events
# ---------------------------------------------------------------------------
def test_setup_label_falls_back_to_unknown_when_no_plan_or_signal(
    driver, wired_set
):
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect_paper_trade(client_order_id=coid)
    assert result.setup == "unknown"


def test_source_event_ids_match_paper_trade_replay_events(driver, wired_set):
    repo, _, _ = wired_set
    coid = _drive_paper_trade(driver)
    replay = ReplayEngine(event_repo=repo).replay_paper_trade(
        client_order_id=coid
    )
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    result = engine.reflect(
        ReflectionInput(paper_trade=replay)
    )
    assert result.source_event_ids == tuple(ev.event_id for ev in replay.events)


# ---------------------------------------------------------------------------
# Type-guard
# ---------------------------------------------------------------------------
def test_reflect_rejects_non_paper_trade_replay_input(wired_set):
    repo, _, _ = wired_set
    engine = ReflectionEngine(replay=ReplayEngine(event_repo=repo))
    with pytest.raises(TypeError):
        engine.reflect(ReflectionInput(paper_trade="not a replay"))
