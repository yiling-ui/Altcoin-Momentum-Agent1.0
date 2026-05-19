"""Phase 7 - Trade State Machine tests (Issue #7, Spec §26).

Covers:

  - Issue #7 acceptance criterion 1: OBSERVE cannot directly become
    RIGHT_TAIL_AMPLIFY.
  - Issue #7 acceptance criterion 2: SCOUT cannot directly become
    ATTACK; must go through CONFIRM.
  - Phase 7 hard rules: no level skipping; CONFIRM-failure downgrades
    to SCOUT; DISTRIBUTION_ALERT cannot promote; FORCED_EXIT is
    sticky; right-tail must come from floating profit.
  - Spec §26.4 timeouts: OBSERVE -> NO_TRADE after 30 min, SCOUT
    -> NO_TRADE after 12 min, ATTACK -> LOCK_PROFIT on cvd_weakening,
    RIGHT_TAIL_AMPLIFY -> LOCK_PROFIT on core failure.
  - Issue #7 acceptance criterion 14: state transitions are written
    to events.db.
"""

from __future__ import annotations

import pytest

from app.core.enums import (
    ManipulationLevel,
    TradeConfirmationLevel,
    TradeState,
    TradeStateTrigger,
)
from app.core.events import EventType
from app.state_machine import (
    IllegalStateTransition,
    TimeoutConfig,
    TradeStateContext,
    TradeStateMachine,
)


# ---------------------------------------------------------------------------
# Acceptance criterion 1: OBSERVE cannot directly become RIGHT_TAIL_AMPLIFY
# ---------------------------------------------------------------------------
def test_observe_cannot_directly_become_right_tail_amplify():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    sm.transition_to(
        TradeState.OBSERVE, trigger=TradeStateTrigger.SIGNAL, reasons=("seed",)
    )
    with pytest.raises(IllegalStateTransition):
        sm.transition_to(
            TradeState.RIGHT_TAIL_AMPLIFY,
            trigger=TradeStateTrigger.PROMOTE,
            reasons=("attempt_skip",),
        )


def test_observe_promote_only_walks_to_scout_not_attack_or_amplify():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    sm.transition_to(
        TradeState.OBSERVE, trigger=TradeStateTrigger.SIGNAL, reasons=("seed",)
    )
    decision = sm.promote(
        TradeStateContext(
            symbol="PEPEUSDT",
            confirmation_level=TradeConfirmationLevel.T4,
            manipulation_level=ManipulationLevel.M0,
            unrealized_pnl=10.0,
        )
    )
    assert decision.accepted
    assert decision.from_state is TradeState.OBSERVE
    assert decision.to_state is TradeState.SCOUT


# ---------------------------------------------------------------------------
# Acceptance criterion 2: SCOUT cannot directly become ATTACK
# ---------------------------------------------------------------------------
def test_scout_cannot_directly_become_attack():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    sm.transition_to(
        TradeState.OBSERVE, trigger=TradeStateTrigger.SIGNAL, reasons=("seed",)
    )
    sm.transition_to(
        TradeState.SCOUT, trigger=TradeStateTrigger.PROMOTE, reasons=("seed",)
    )
    with pytest.raises(IllegalStateTransition):
        sm.transition_to(
            TradeState.ATTACK,
            trigger=TradeStateTrigger.PROMOTE,
            reasons=("attempt_skip",),
        )


def test_scout_promote_walks_to_confirm_not_attack():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    sm.transition_to(
        TradeState.OBSERVE, trigger=TradeStateTrigger.SIGNAL, reasons=("seed",)
    )
    sm.transition_to(
        TradeState.SCOUT, trigger=TradeStateTrigger.PROMOTE, reasons=("seed",)
    )
    decision = sm.promote(
        TradeStateContext(
            symbol="PEPEUSDT",
            confirmation_level=TradeConfirmationLevel.T3,
            manipulation_level=ManipulationLevel.M0,
            unrealized_pnl=0.0,
        )
    )
    assert decision.accepted
    assert decision.to_state is TradeState.CONFIRM


def test_scout_promote_refused_with_low_confirmation():
    """SCOUT -> CONFIRM requires T2+: T0/T1 cannot graduate."""
    sm = TradeStateMachine(symbol="PEPEUSDT")
    sm.transition_to(
        TradeState.OBSERVE, trigger=TradeStateTrigger.SIGNAL
    )
    sm.transition_to(
        TradeState.SCOUT, trigger=TradeStateTrigger.PROMOTE
    )
    decision = sm.promote(
        TradeStateContext(
            symbol="PEPEUSDT",
            confirmation_level=TradeConfirmationLevel.T1,
            manipulation_level=ManipulationLevel.M0,
        )
    )
    assert not decision.accepted
    assert decision.to_state is TradeState.SCOUT
    assert "trade_confirmation_too_low_for_confirm" in decision.reasons


# ---------------------------------------------------------------------------
# CONFIRM -> ATTACK requires T2+ AND M0/M1
# ---------------------------------------------------------------------------
def _walk_to(sm, target):
    """Helper: walk the ladder rung by rung up to ``target``."""
    ladder = [
        TradeState.OBSERVE,
        TradeState.SCOUT,
        TradeState.CONFIRM,
        TradeState.ATTACK,
        TradeState.RIGHT_TAIL_AMPLIFY,
    ]
    triggers = {
        TradeState.OBSERVE: TradeStateTrigger.SIGNAL,
    }
    for state in ladder:
        if sm.state == target:
            return
        sm.transition_to(
            state,
            trigger=triggers.get(state, TradeStateTrigger.PROMOTE),
            reasons=("seed",),
        )
        if state == target:
            return


def test_confirm_promote_to_attack_requires_t2_or_above():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    _walk_to(sm, TradeState.CONFIRM)
    decision = sm.promote(
        TradeStateContext(
            symbol="PEPEUSDT",
            confirmation_level=TradeConfirmationLevel.T1,
            manipulation_level=ManipulationLevel.M0,
        )
    )
    assert not decision.accepted
    assert "trade_confirmation_too_low_for_attack" in decision.reasons


def test_confirm_promote_to_attack_blocked_by_m2():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    _walk_to(sm, TradeState.CONFIRM)
    decision = sm.promote(
        TradeStateContext(
            symbol="PEPEUSDT",
            confirmation_level=TradeConfirmationLevel.T3,
            manipulation_level=ManipulationLevel.M2,
        )
    )
    assert not decision.accepted
    assert "manipulation_m2_attack" in decision.reasons


def test_confirm_promote_to_attack_blocked_by_m3():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    _walk_to(sm, TradeState.CONFIRM)
    decision = sm.promote(
        TradeStateContext(
            symbol="PEPEUSDT",
            confirmation_level=TradeConfirmationLevel.T3,
            manipulation_level=ManipulationLevel.M3,
        )
    )
    assert not decision.accepted
    assert "manipulation_m3" in decision.reasons


def test_confirm_promote_to_attack_succeeds_when_clean():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    _walk_to(sm, TradeState.CONFIRM)
    decision = sm.promote(
        TradeStateContext(
            symbol="PEPEUSDT",
            confirmation_level=TradeConfirmationLevel.T3,
            manipulation_level=ManipulationLevel.M0,
        )
    )
    assert decision.accepted
    assert decision.to_state is TradeState.ATTACK


# ---------------------------------------------------------------------------
# ATTACK -> RIGHT_TAIL_AMPLIFY requires floating profit, no CVD weakening
# ---------------------------------------------------------------------------
def test_losing_position_cannot_promote_to_right_tail_amplify():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    _walk_to(sm, TradeState.ATTACK)
    decision = sm.promote(
        TradeStateContext(
            symbol="PEPEUSDT",
            confirmation_level=TradeConfirmationLevel.T4,
            manipulation_level=ManipulationLevel.M0,
            unrealized_pnl=-1.0,
        )
    )
    assert not decision.accepted
    assert "losing_position_cannot_amplify" in decision.reasons


def test_attack_with_cvd_weakening_cannot_amplify():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    _walk_to(sm, TradeState.ATTACK)
    decision = sm.promote(
        TradeStateContext(
            symbol="PEPEUSDT",
            confirmation_level=TradeConfirmationLevel.T4,
            manipulation_level=ManipulationLevel.M0,
            unrealized_pnl=10.0,
            cvd_weakening=True,
        )
    )
    assert not decision.accepted
    assert "cvd_weakening" in decision.reasons


def test_attack_with_floating_profit_promotes_to_right_tail_amplify():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    _walk_to(sm, TradeState.ATTACK)
    decision = sm.promote(
        TradeStateContext(
            symbol="PEPEUSDT",
            confirmation_level=TradeConfirmationLevel.T4,
            manipulation_level=ManipulationLevel.M0,
            unrealized_pnl=10.0,
        )
    )
    assert decision.accepted
    assert decision.to_state is TradeState.RIGHT_TAIL_AMPLIFY


# ---------------------------------------------------------------------------
# CONFIRM-failure downgrade
# ---------------------------------------------------------------------------
def test_confirm_failures_downgrade_to_scout_after_threshold():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    _walk_to(sm, TradeState.CONFIRM)
    # Default threshold is 2.
    first = sm.record_breakout_failure()
    assert first is None
    second = sm.record_breakout_failure()
    assert second is not None
    assert second.accepted
    assert second.from_state is TradeState.CONFIRM
    assert second.to_state is TradeState.SCOUT
    assert "confirm_breakout_failed" in second.reasons


# ---------------------------------------------------------------------------
# DISTRIBUTION_ALERT cannot add size
# ---------------------------------------------------------------------------
def test_distribution_alert_cannot_promote():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    _walk_to(sm, TradeState.CONFIRM)
    sm.distribution_alert()
    decision = sm.promote(
        TradeStateContext(
            symbol="PEPEUSDT",
            confirmation_level=TradeConfirmationLevel.T4,
            manipulation_level=ManipulationLevel.M0,
            unrealized_pnl=10.0,
        )
    )
    assert not decision.accepted
    assert any(
        r.startswith("cannot_promote_from") for r in decision.reasons
    )


def test_distribution_alert_three_bars_triggers_forced_exit():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    _walk_to(sm, TradeState.CONFIRM)
    sm.distribution_alert()
    assert sm.record_distribution_bar() is None
    assert sm.record_distribution_bar() is None
    final = sm.record_distribution_bar()
    assert final is not None and final.accepted
    assert final.to_state is TradeState.FORCED_EXIT


# ---------------------------------------------------------------------------
# FORCED_EXIT is sticky
# ---------------------------------------------------------------------------
def test_forced_exit_is_sticky_no_promotion_no_lock_profit():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    sm.transition_to(TradeState.OBSERVE, trigger=TradeStateTrigger.SIGNAL)
    sm.forced_exit()
    # Cannot promote.
    decision = sm.promote(
        TradeStateContext(
            symbol="PEPEUSDT",
            confirmation_level=TradeConfirmationLevel.T4,
            manipulation_level=ManipulationLevel.M0,
            unrealized_pnl=10.0,
        )
    )
    assert not decision.accepted
    # Cannot transition out except via reset().
    with pytest.raises(IllegalStateTransition):
        sm.transition_to(
            TradeState.NO_TRADE, trigger=TradeStateTrigger.RESET
        )


def test_forced_exit_can_only_be_cleared_by_reset():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    sm.transition_to(TradeState.OBSERVE, trigger=TradeStateTrigger.SIGNAL)
    sm.forced_exit()
    decision = sm.reset(reason="reconciliation_clean")
    assert decision.accepted
    assert decision.to_state is TradeState.NO_TRADE
    assert sm.state is TradeState.NO_TRADE


# ---------------------------------------------------------------------------
# Timeouts (Spec §26.4)
# ---------------------------------------------------------------------------
def test_observe_timeout_after_thirty_minutes():
    sm = TradeStateMachine(symbol="PEPEUSDT", clock_ms=1_000)
    sm.transition_to(
        TradeState.OBSERVE,
        trigger=TradeStateTrigger.SIGNAL,
        clock_ms=1_000,
    )
    # Just under 30 min: no timeout.
    assert sm.tick(clock_ms=1_000 + 29 * 60 * 1000) is None
    # Past 30 min: timeout fires.
    decision = sm.tick(clock_ms=1_000 + 31 * 60 * 1000)
    assert decision is not None and decision.accepted
    assert decision.to_state is TradeState.NO_TRADE
    assert "observe_timeout" in decision.reasons


def test_scout_timeout_after_twelve_minutes():
    sm = TradeStateMachine(symbol="PEPEUSDT", clock_ms=1_000)
    sm.transition_to(
        TradeState.OBSERVE,
        trigger=TradeStateTrigger.SIGNAL,
        clock_ms=1_000,
    )
    sm.transition_to(
        TradeState.SCOUT,
        trigger=TradeStateTrigger.PROMOTE,
        clock_ms=1_000,
    )
    assert sm.tick(clock_ms=1_000 + 11 * 60 * 1000) is None
    decision = sm.tick(clock_ms=1_000 + 13 * 60 * 1000)
    assert decision is not None
    assert decision.to_state is TradeState.NO_TRADE


def test_attack_cvd_weakening_locks_profit():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    _walk_to(sm, TradeState.ATTACK)
    decision = sm.tick(clock_ms=sm.entered_at_ms + 1_000, cvd_weakening=True)
    assert decision is not None
    assert decision.to_state is TradeState.LOCK_PROFIT


def test_right_tail_amplify_core_failure_locks_profit():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    _walk_to(sm, TradeState.RIGHT_TAIL_AMPLIFY)
    decision = sm.tick(
        clock_ms=sm.entered_at_ms + 1_000, right_tail_core_failed=True
    )
    assert decision is not None
    assert decision.to_state is TradeState.LOCK_PROFIT


# ---------------------------------------------------------------------------
# STATE_TRANSITION events are emitted (replay / reflection)
# ---------------------------------------------------------------------------
def test_state_transition_event_persisted(events_repo):
    sm = TradeStateMachine(symbol="PEPEUSDT", event_repo=events_repo)
    sm.transition_to(
        TradeState.OBSERVE,
        trigger=TradeStateTrigger.SIGNAL,
        reasons=("seed",),
    )
    events = events_repo.list(event_type=EventType.STATE_TRANSITION)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["from"] == TradeState.NO_TRADE.value
    assert payload["to"] == TradeState.OBSERVE.value
    assert payload["trigger"] == TradeStateTrigger.SIGNAL.value
    assert payload["symbol"] == "PEPEUSDT"


def test_full_ladder_writes_all_transition_events(events_repo):
    sm = TradeStateMachine(symbol="PEPEUSDT", event_repo=events_repo)
    sm.transition_to(TradeState.OBSERVE, trigger=TradeStateTrigger.SIGNAL)
    sm.transition_to(TradeState.SCOUT, trigger=TradeStateTrigger.PROMOTE)
    sm.transition_to(TradeState.CONFIRM, trigger=TradeStateTrigger.PROMOTE)
    sm.transition_to(TradeState.ATTACK, trigger=TradeStateTrigger.PROMOTE)
    events = events_repo.list(event_type=EventType.STATE_TRANSITION)
    assert len(events) == 4
    pairs = {(e.payload["from"], e.payload["to"]) for e in events}
    assert pairs == {
        ("no_trade", "observe"),
        ("observe", "scout"),
        ("scout", "confirm"),
        ("confirm", "attack"),
    }


# ---------------------------------------------------------------------------
# Counters + observability
# ---------------------------------------------------------------------------
def test_refusal_counter_increments_on_illegal_transition():
    sm = TradeStateMachine(symbol="PEPEUSDT")
    sm.transition_to(TradeState.OBSERVE, trigger=TradeStateTrigger.SIGNAL)
    with pytest.raises(IllegalStateTransition):
        sm.transition_to(
            TradeState.RIGHT_TAIL_AMPLIFY,
            trigger=TradeStateTrigger.PROMOTE,
        )
    assert sm.refusals == 1


def test_lock_profit_promotion_refused():
    """LOCK_PROFIT cannot promote back up the ladder."""
    sm = TradeStateMachine(symbol="PEPEUSDT")
    _walk_to(sm, TradeState.ATTACK)
    sm.lock_profit()
    decision = sm.promote(
        TradeStateContext(
            symbol="PEPEUSDT",
            confirmation_level=TradeConfirmationLevel.T4,
            manipulation_level=ManipulationLevel.M0,
            unrealized_pnl=10.0,
        )
    )
    assert not decision.accepted


def test_no_trade_can_only_become_observe():
    """Phase 7 hard rule: NO_TRADE -> OBSERVE is the ONLY legal first step."""
    sm = TradeStateMachine(symbol="PEPEUSDT")
    forbidden = [
        TradeState.SCOUT,
        TradeState.CONFIRM,
        TradeState.ATTACK,
        TradeState.RIGHT_TAIL_AMPLIFY,
        TradeState.LOCK_PROFIT,
        TradeState.DISTRIBUTION_ALERT,
    ]
    for target in forbidden:
        with pytest.raises(IllegalStateTransition):
            sm.transition_to(target, trigger=TradeStateTrigger.PROMOTE)


def test_custom_timeout_config_is_honoured():
    cfg = TimeoutConfig(observe_timeout_ms=1_000, scout_timeout_ms=2_000)
    sm = TradeStateMachine(
        symbol="PEPEUSDT", timeout_config=cfg, clock_ms=0
    )
    sm.transition_to(
        TradeState.OBSERVE, trigger=TradeStateTrigger.SIGNAL, clock_ms=0
    )
    # With custom 1s timeout, tick at 1_001 ms fires.
    decision = sm.tick(clock_ms=1_001)
    assert decision is not None
    assert decision.to_state is TradeState.NO_TRADE
