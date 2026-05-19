"""Phase 7 - Trade State Machine (Issue #7, Spec §26).

The Trade State Machine is the *trade-level intent* state, distinct
from the order-level :class:`app.execution.fsm.ExecutionFSM`. It
tracks where a candidate / position sits in the Spec §26.1 ladder:

    NO_TRADE
       ↓ promote (signal)
    OBSERVE                  (timeout 30 min if not promoted)
       ↓ promote (signal)
    SCOUT                    (timeout 10-15 min if no follow-through)
       ↓ promote (confirmation T2+)
    CONFIRM                  (downgrade after 2 failed breakouts)
       ↓ promote (full attack permission from Risk Engine)
    ATTACK                   (-> LOCK_PROFIT on weakening, -> RIGHT_TAIL_AMPLIFY
       ↓ promote (right-tail conditions)        on confirmed continuation)
    RIGHT_TAIL_AMPLIFY       (-> LOCK_PROFIT if any core condition fails)
       ↓
    LOCK_PROFIT
       ↓
    DISTRIBUTION_ALERT       (-> FORCED_EXIT after 3 confirming bars)
       ↓
    FORCED_EXIT              (cannot be cancelled by LLM or operator)

Phase 7 hard rules (Issue #7):

  1. **No level skipping.** OBSERVE cannot transition directly to
     RIGHT_TAIL_AMPLIFY, SCOUT cannot transition directly to ATTACK,
     and so on. The transition table is a strict whitelist; every
     attempt outside the table raises :class:`IllegalTransition`.
  2. **CONFIRM failures must downgrade.** ``record_confirm_failure``
     drops back to SCOUT after the configured number of consecutive
     failures.
  3. **DISTRIBUTION_ALERT cannot add size.** A promote attempt while
     the state is DISTRIBUTION_ALERT is refused.
  4. **FORCED_EXIT is sticky.** It can only be cleared by a hard
     ``reset()`` (Reconciliation / human, Issue #9 / #10).
  5. **A losing position cannot enter RIGHT_TAIL_AMPLIFY.** Phase 7
     refuses the transition when ``unrealized_pnl <= 0``.
  6. **Right-tail amplification must come from floating profit, not
     principal.** Refused when ``unrealized_pnl <= 0`` even if
     somehow elevated in tier A.
  7. **Every transition writes one ``STATE_TRANSITION`` event** with
     the trigger + reason payload; Replay (Issue #10) reconstructs
     the ladder from events.db alone.
  8. **Timeouts are deterministic.** :meth:`tick(now_ms)` advances
     state automatically when a configured deadline is crossed
     (OBSERVE -> NO_TRADE, SCOUT -> NO_TRADE, ATTACK -> LOCK_PROFIT
     when CVD weakens, etc).

This package ships the value objects + transition table; the wiring
between the State Machine and the Risk Engine lives in
:mod:`app.risk.engine` (Phase 7).
"""

from app.state_machine.machine import (
    IllegalStateTransition,
    StateMachineDecision,
    TimeoutConfig,
    TradeStateContext,
    TradeStateMachine,
)

__all__ = [
    "IllegalStateTransition",
    "StateMachineDecision",
    "TimeoutConfig",
    "TradeStateContext",
    "TradeStateMachine",
]
