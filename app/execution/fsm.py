"""Execution FSM skeleton.

Spec §30.1 lists the full state vocabulary; we ship the transition table
in Phase 1 so that future phases can extend rather than redefine. No real
order is sent in Phase 1 - the FSM advances purely as in-memory state and
is exercised only through tests.

Hard rules implemented even at Phase 1
--------------------------------------
- Transitions are restricted to a whitelist; an illegal transition raises
  `IllegalTransition` (subclass of `ExecutionError`).
- Every `request_send_order` MUST be preceded by a `RiskDecision`, and the
  caller must pass `risk_approved=True`. Without it, the FSM refuses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.enums import ExecutionState
from app.core.errors import ExecutionError

# Allowed transitions. Lifted from Spec §30.1 + Issue #9. Phase 1 keeps the
# graph permissive enough for tests but never permits skipping risk checks.
_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
    ExecutionState.IDLE: {ExecutionState.SIGNAL_RECEIVED},
    ExecutionState.SIGNAL_RECEIVED: {ExecutionState.RISK_CHECKED, ExecutionState.IDLE},
    ExecutionState.RISK_CHECKED: {ExecutionState.ORDER_SENT, ExecutionState.IDLE},
    ExecutionState.ORDER_SENT: {
        ExecutionState.ACK_RECEIVED,
        ExecutionState.ERROR_PROTECTION,
    },
    ExecutionState.ACK_RECEIVED: {
        ExecutionState.PARTIAL_FILLED,
        ExecutionState.FULL_FILLED,
        ExecutionState.ERROR_PROTECTION,
    },
    ExecutionState.PARTIAL_FILLED: {
        ExecutionState.PARTIAL_FILLED,
        ExecutionState.FULL_FILLED,
        ExecutionState.ERROR_PROTECTION,
    },
    ExecutionState.FULL_FILLED: {
        ExecutionState.STOP_SENT,
        ExecutionState.ERROR_PROTECTION,
    },
    ExecutionState.STOP_SENT: {
        ExecutionState.STOP_CONFIRMED,
        ExecutionState.STOP_FAILED,
        ExecutionState.ERROR_PROTECTION,
    },
    ExecutionState.STOP_CONFIRMED: {
        ExecutionState.POSITION_OPEN,
        ExecutionState.ERROR_PROTECTION,
    },
    ExecutionState.STOP_FAILED: {ExecutionState.ERROR_PROTECTION},
    ExecutionState.POSITION_OPEN: {
        ExecutionState.EXIT_TRIGGERED,
        ExecutionState.ERROR_PROTECTION,
    },
    ExecutionState.EXIT_TRIGGERED: {
        ExecutionState.POSITION_CLOSING,
        ExecutionState.ERROR_PROTECTION,
    },
    ExecutionState.POSITION_CLOSING: {
        ExecutionState.POSITION_CLOSED,
        ExecutionState.ERROR_PROTECTION,
    },
    ExecutionState.POSITION_CLOSED: {ExecutionState.IDLE},
    ExecutionState.ERROR_PROTECTION: {ExecutionState.IDLE},
}


class IllegalTransition(ExecutionError):
    """Raised when the FSM is asked to perform a transition not in the table."""


@dataclass
class ExecutionFSM:
    """Tiny in-memory state machine used as a Phase 1 placeholder."""

    state: ExecutionState = ExecutionState.IDLE
    history: list[tuple[ExecutionState, ExecutionState]] = field(default_factory=list)

    def can_transition(self, target: ExecutionState) -> bool:
        return target in _TRANSITIONS.get(self.state, set())

    def transition(self, target: ExecutionState) -> None:
        if not self.can_transition(target):
            raise IllegalTransition(
                f"Illegal transition {self.state.value} -> {target.value}"
            )
        self.history.append((self.state, target))
        self.state = target

    # Convenience helpers that document the contract.
    def request_send_order(self, *, risk_approved: bool, **_: Any) -> None:
        """Move from RISK_CHECKED to ORDER_SENT. Refuses if risk not approved."""
        if self.state is not ExecutionState.RISK_CHECKED:
            raise IllegalTransition(
                f"request_send_order requires state RISK_CHECKED, got {self.state.value}"
            )
        if not risk_approved:
            raise ExecutionError("Order send refused: risk decision not approved.")
        self.transition(ExecutionState.ORDER_SENT)

    def report_stop_failed(self) -> None:
        """Force the FSM into ERROR_PROTECTION."""
        if self.state is not ExecutionState.STOP_SENT:
            raise IllegalTransition(
                f"report_stop_failed requires state STOP_SENT, got {self.state.value}"
            )
        self.transition(ExecutionState.STOP_FAILED)
        self.transition(ExecutionState.ERROR_PROTECTION)
