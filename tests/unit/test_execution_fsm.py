"""Execution FSM skeleton tests."""

from __future__ import annotations

import pytest

from app.core.enums import ExecutionState
from app.core.errors import ExecutionError
from app.execution.fsm import ExecutionFSM, IllegalTransition


def _drive_to(fsm: ExecutionFSM, target: ExecutionState) -> None:
    """Drive the FSM through a legal sequence to a target state."""
    sequence = [
        ExecutionState.SIGNAL_RECEIVED,
        ExecutionState.RISK_CHECKED,
        ExecutionState.ORDER_SENT,
        ExecutionState.ACK_RECEIVED,
        ExecutionState.FULL_FILLED,
        ExecutionState.STOP_SENT,
        ExecutionState.STOP_CONFIRMED,
        ExecutionState.POSITION_OPEN,
        ExecutionState.EXIT_TRIGGERED,
        ExecutionState.POSITION_CLOSING,
        ExecutionState.POSITION_CLOSED,
        ExecutionState.IDLE,
    ]
    for state in sequence:
        fsm.transition(state)
        if state is target:
            return


def test_initial_state_idle():
    fsm = ExecutionFSM()
    assert fsm.state is ExecutionState.IDLE


def test_legal_full_lifecycle():
    fsm = ExecutionFSM()
    _drive_to(fsm, ExecutionState.IDLE)
    assert fsm.state is ExecutionState.IDLE
    assert (ExecutionState.POSITION_CLOSED, ExecutionState.IDLE) in fsm.history


def test_illegal_jump_raises():
    fsm = ExecutionFSM()
    # IDLE -> POSITION_OPEN is not in the transition table.
    with pytest.raises(IllegalTransition):
        fsm.transition(ExecutionState.POSITION_OPEN)


def test_no_skip_to_attack_or_right_tail():
    """Spec §26.2: SCOUT cannot skip to RIGHT_TAIL_AMPLIFY (TradeState
    machine, not Execution FSM, but the principle applies here too).

    For the Execution FSM the equivalent rule is: cannot ORDER_SENT from IDLE.
    """
    fsm = ExecutionFSM()
    with pytest.raises(IllegalTransition):
        fsm.transition(ExecutionState.ORDER_SENT)


def test_request_send_order_requires_risk_approved():
    fsm = ExecutionFSM()
    fsm.transition(ExecutionState.SIGNAL_RECEIVED)
    fsm.transition(ExecutionState.RISK_CHECKED)
    with pytest.raises(ExecutionError):
        fsm.request_send_order(risk_approved=False)
    # State unchanged after rejection.
    assert fsm.state is ExecutionState.RISK_CHECKED

    fsm.request_send_order(risk_approved=True)
    assert fsm.state is ExecutionState.ORDER_SENT


def test_stop_failed_drives_to_error_protection():
    fsm = ExecutionFSM()
    for s in (
        ExecutionState.SIGNAL_RECEIVED,
        ExecutionState.RISK_CHECKED,
        ExecutionState.ORDER_SENT,
        ExecutionState.ACK_RECEIVED,
        ExecutionState.FULL_FILLED,
        ExecutionState.STOP_SENT,
    ):
        fsm.transition(s)
    fsm.report_stop_failed()
    assert fsm.state is ExecutionState.ERROR_PROTECTION
