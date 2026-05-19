"""Phase 7 Trade State Machine (Issue #7, Spec §26).

The state machine tracks the trade-level intent for a single
candidate or position. It does NOT trade. It does NOT call any
exchange surface. It does NOT amplify or reduce a position. It
emits ``STATE_TRANSITION`` events through the supplied
:class:`EventRepository` so Replay (Issue #10) can rebuild the
ladder from events.db alone.

The transition table (whitelisted) and timeout policy are
documented in :mod:`app.state_machine` and the docstrings below.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.clock import now_ms
from app.core.enums import (
    ManipulationLevel,
    TradeConfirmationLevel,
    TradeState,
    TradeStateTrigger,
)
from app.core.errors import ExecutionError
from app.core.events import Event, EventType
from app.database.repositories import EventRepository


# ---------------------------------------------------------------------------
# Transition table (Spec §26.2 + §26.3)
# ---------------------------------------------------------------------------
# Phase 7 hard rule: NO LEVEL SKIPPING. Every entry below is a
# whitelisted transition; any attempt outside this graph raises
# IllegalStateTransition.
#
# Notes:
#   - SCOUT -> ATTACK is NOT in this table. SCOUT must go through
#     CONFIRM first.
#   - OBSERVE -> RIGHT_TAIL_AMPLIFY is NOT in this table. The only
#     way to reach RIGHT_TAIL_AMPLIFY is from ATTACK.
#   - CONFIRM downgrades to SCOUT (not directly to NO_TRADE) so the
#     caller still has a chance to re-confirm; SCOUT downgrades to
#     NO_TRADE when its own timeout fires.
#   - DISTRIBUTION_ALERT can only step *down* (to LOCK_PROFIT or
#     FORCED_EXIT); promoting back is forbidden.
#   - FORCED_EXIT is sticky: only ``reset()`` can clear it.
ALLOWED_TRANSITIONS: dict[TradeState, frozenset[TradeState]] = {
    TradeState.NO_TRADE: frozenset({TradeState.OBSERVE}),
    TradeState.OBSERVE: frozenset(
        {TradeState.SCOUT, TradeState.NO_TRADE, TradeState.FORCED_EXIT}
    ),
    TradeState.SCOUT: frozenset(
        {
            TradeState.CONFIRM,
            TradeState.OBSERVE,
            TradeState.NO_TRADE,
            TradeState.LOCK_PROFIT,
            TradeState.FORCED_EXIT,
        }
    ),
    TradeState.CONFIRM: frozenset(
        {
            TradeState.ATTACK,
            TradeState.SCOUT,
            TradeState.LOCK_PROFIT,
            TradeState.FORCED_EXIT,
            TradeState.DISTRIBUTION_ALERT,
        }
    ),
    TradeState.ATTACK: frozenset(
        {
            TradeState.RIGHT_TAIL_AMPLIFY,
            TradeState.LOCK_PROFIT,
            TradeState.DISTRIBUTION_ALERT,
            TradeState.FORCED_EXIT,
        }
    ),
    TradeState.RIGHT_TAIL_AMPLIFY: frozenset(
        {
            TradeState.LOCK_PROFIT,
            TradeState.DISTRIBUTION_ALERT,
            TradeState.FORCED_EXIT,
        }
    ),
    TradeState.LOCK_PROFIT: frozenset(
        {
            TradeState.NO_TRADE,
            TradeState.DISTRIBUTION_ALERT,
            TradeState.FORCED_EXIT,
        }
    ),
    TradeState.DISTRIBUTION_ALERT: frozenset(
        {
            TradeState.LOCK_PROFIT,
            TradeState.FORCED_EXIT,
        }
    ),
    # FORCED_EXIT is sticky: only reset() clears it.
    TradeState.FORCED_EXIT: frozenset(),
}


# Promotion ladder (the "normal happy path"). Used by ``promote()`` to
# decide what the next ladder step is given the current state. A state
# missing from this map cannot be promoted (DISTRIBUTION_ALERT,
# LOCK_PROFIT, FORCED_EXIT, RIGHT_TAIL_AMPLIFY).
PROMOTION_LADDER: dict[TradeState, TradeState] = {
    TradeState.NO_TRADE: TradeState.OBSERVE,
    TradeState.OBSERVE: TradeState.SCOUT,
    TradeState.SCOUT: TradeState.CONFIRM,
    TradeState.CONFIRM: TradeState.ATTACK,
    TradeState.ATTACK: TradeState.RIGHT_TAIL_AMPLIFY,
}


# Downgrade ladder. CONFIRM downgrades to SCOUT, SCOUT to OBSERVE,
# OBSERVE to NO_TRADE.
DOWNGRADE_LADDER: dict[TradeState, TradeState] = {
    TradeState.CONFIRM: TradeState.SCOUT,
    TradeState.SCOUT: TradeState.OBSERVE,
    TradeState.OBSERVE: TradeState.NO_TRADE,
}


# ---------------------------------------------------------------------------
# Timeout configuration (Spec §26.4)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TimeoutConfig:
    """Phase 7 timeout policy (Spec §26.4).

    All values are in milliseconds. Defaults match the spec text:

      - OBSERVE超过 30 分钟未确认 -> 移出候选池
      - SCOUT 10-15 分钟无成交推动 -> 平仓 / 降级
      - CONFIRM 连续 2 次突破失败 -> 降级
      - ATTACK 盈利未延续且 CVD 转弱 -> LOCK_PROFIT
      - DISTRIBUTION_ALERT 持续 3 根 K -> 减仓或退出
      - RIGHT_TAIL_AMPLIFY 任一核心条件失效 -> LOCK_PROFIT

    Issue #6 / Issue #7 calibration may tune these values; Phase 7
    keeps the values explicit so they can be overridden via YAML in
    a later PR without changing the engine surface.
    """

    observe_timeout_ms: int = 30 * 60 * 1000  # 30 min
    scout_timeout_ms: int = 12 * 60 * 1000  # 12 min (mid of 10-15)
    confirm_failure_downgrade_threshold: int = 2  # 2 failed breakouts
    attack_lock_profit_on_weakening: bool = True
    distribution_alert_bars_until_exit: int = 3
    right_tail_lock_profit_on_core_failure: bool = True


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class IllegalStateTransition(ExecutionError):
    """Raised when a caller attempts a TradeState transition that is
    not in :data:`ALLOWED_TRANSITIONS`. Phase 7 hard rule: no level
    skipping."""


# ---------------------------------------------------------------------------
# Context + decision
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TradeStateContext:
    """Inputs the state machine consults on transition attempts.

    Phase 7 keeps this object explicit so tests do not need to wire a
    full Phase 4 buffer / Phase 5 regime / Phase 6 confirmation /
    manipulation pipeline to drive the ladder.
    """

    symbol: str
    confirmation_level: TradeConfirmationLevel | None = None
    manipulation_level: ManipulationLevel | None = None
    cvd_weakening: bool = False
    unrealized_pnl: float = 0.0
    distribution_alert_bars: int = 0
    breakout_failures: int = 0


@dataclass(frozen=True)
class StateMachineDecision:
    """Result of a transition attempt."""

    accepted: bool
    from_state: TradeState
    to_state: TradeState
    trigger: TradeStateTrigger
    reasons: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Trade State Machine
# ---------------------------------------------------------------------------
class TradeStateMachine:
    """Per-symbol Trade State Machine (Spec §26).

    The machine exposes a small set of operations; every successful
    transition writes one ``STATE_TRANSITION`` event. Issue #7 routes
    Phase 5 + Phase 6 outputs in through ``promote(...)`` /
    ``downgrade(...)`` / ``tick(...)``.
    """

    SOURCE_MODULE = "state_machine"

    def __init__(
        self,
        *,
        symbol: str,
        timeout_config: TimeoutConfig | None = None,
        event_repo: EventRepository | None = None,
        initial_state: TradeState = TradeState.NO_TRADE,
        clock_ms: int | None = None,
    ) -> None:
        self._symbol = symbol
        self._config = timeout_config or TimeoutConfig()
        self._event_repo = event_repo
        self._state: TradeState = initial_state
        # Wall-clock ms when we entered the current state. Used by
        # tick() to enforce timeouts.
        self._entered_at_ms: int = clock_ms if clock_ms is not None else now_ms()
        # Counter for SCOUT confirm-failure downgrades.
        self._breakout_failures: int = 0
        # Counter for distribution-alert bars elapsed.
        self._distribution_bars: int = 0
        # Cumulative observability counters.
        self._transitions: int = 0
        self._timeouts_fired: int = 0
        self._refusals: int = 0

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------
    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def state(self) -> TradeState:
        return self._state

    @property
    def entered_at_ms(self) -> int:
        return self._entered_at_ms

    @property
    def transitions(self) -> int:
        return self._transitions

    @property
    def timeouts_fired(self) -> int:
        return self._timeouts_fired

    @property
    def refusals(self) -> int:
        return self._refusals

    @property
    def breakout_failures(self) -> int:
        return self._breakout_failures

    @property
    def distribution_bars(self) -> int:
        return self._distribution_bars

    @property
    def config(self) -> TimeoutConfig:
        return self._config

    # ------------------------------------------------------------------
    # Core transition primitive
    # ------------------------------------------------------------------
    def transition_to(
        self,
        target: TradeState,
        *,
        trigger: TradeStateTrigger,
        reasons: tuple[str, ...] = (),
        clock_ms: int | None = None,
    ) -> StateMachineDecision:
        """Attempt a direct transition. Refuses if not in
        :data:`ALLOWED_TRANSITIONS`; raises :class:`IllegalStateTransition`."""
        if target not in ALLOWED_TRANSITIONS.get(self._state, frozenset()):
            self._refusals += 1
            raise IllegalStateTransition(
                f"Trade-state transition forbidden: "
                f"{self._state.value} -> {target.value} "
                f"(symbol={self._symbol})"
            )
        return self._commit(
            target,
            trigger=trigger,
            reasons=reasons,
            clock_ms=clock_ms,
        )

    # ------------------------------------------------------------------
    # Promote / downgrade with Phase 7 guards
    # ------------------------------------------------------------------
    def promote(
        self,
        context: TradeStateContext,
        *,
        clock_ms: int | None = None,
    ) -> StateMachineDecision:
        """Promote one rung up the ladder if the guards pass.

        Phase 7 hard rules enforced here:

          - NO_TRADE -> OBSERVE: always allowed (regime gate above).
          - OBSERVE -> SCOUT:    always allowed.
          - SCOUT -> CONFIRM:    requires confirmation_level >= T2.
          - CONFIRM -> ATTACK:   requires confirmation_level >= T2 and
                                 manipulation_level not in (M2, M3).
          - ATTACK -> RIGHT_TAIL_AMPLIFY:
                                 requires unrealized_pnl > 0,
                                 manipulation_level not in (M2, M3),
                                 CVD not weakening.
          - DISTRIBUTION_ALERT promotion: REFUSED.
          - LOCK_PROFIT promotion:        REFUSED.
          - RIGHT_TAIL_AMPLIFY promotion: REFUSED (already at top of
                                          attack ladder).
          - FORCED_EXIT promotion:        REFUSED (sticky).
        """
        reasons: list[str] = []

        if self._state in (
            TradeState.DISTRIBUTION_ALERT,
            TradeState.LOCK_PROFIT,
            TradeState.RIGHT_TAIL_AMPLIFY,
            TradeState.FORCED_EXIT,
        ):
            reasons.append(f"cannot_promote_from_{self._state.value}")
            self._refusals += 1
            return StateMachineDecision(
                accepted=False,
                from_state=self._state,
                to_state=self._state,
                trigger=TradeStateTrigger.PROMOTE,
                reasons=tuple(reasons),
            )

        target = PROMOTION_LADDER.get(self._state)
        if target is None:
            reasons.append(f"no_promotion_target_from_{self._state.value}")
            self._refusals += 1
            return StateMachineDecision(
                accepted=False,
                from_state=self._state,
                to_state=self._state,
                trigger=TradeStateTrigger.PROMOTE,
                reasons=tuple(reasons),
            )

        # Phase 6 hard rule: M3 blocks any new opening.
        if context.manipulation_level is ManipulationLevel.M3:
            reasons.append("manipulation_m3")
        # Phase 6 hard rule: M2 blocks ATTACK / RIGHT_TAIL_AMPLIFY only.
        if (
            context.manipulation_level is ManipulationLevel.M2
            and target in (TradeState.ATTACK, TradeState.RIGHT_TAIL_AMPLIFY)
        ):
            reasons.append("manipulation_m2_attack")
        # Phase 6 hard rule: T0 / T1 cannot promote into ATTACK / above.
        if target in (TradeState.ATTACK, TradeState.RIGHT_TAIL_AMPLIFY):
            if context.confirmation_level in (
                None,
                TradeConfirmationLevel.T0,
                TradeConfirmationLevel.T1,
            ):
                reasons.append("trade_confirmation_too_low_for_attack")
        # Phase 6 hard rule: T0 / T1 cannot graduate SCOUT -> CONFIRM
        # because CONFIRM is the gateway to ATTACK and we want the T2
        # threshold to apply at the rung where the size scale changes.
        if (
            self._state is TradeState.SCOUT
            and target is TradeState.CONFIRM
            and context.confirmation_level
            in (None, TradeConfirmationLevel.T0, TradeConfirmationLevel.T1)
        ):
            reasons.append("trade_confirmation_too_low_for_confirm")
        # Phase 7 right-tail: must come from floating profit, not principal.
        if target is TradeState.RIGHT_TAIL_AMPLIFY:
            if context.unrealized_pnl <= 0:
                reasons.append("losing_position_cannot_amplify")
            if context.cvd_weakening:
                reasons.append("cvd_weakening")

        if reasons:
            self._refusals += 1
            return StateMachineDecision(
                accepted=False,
                from_state=self._state,
                to_state=self._state,
                trigger=TradeStateTrigger.PROMOTE,
                reasons=tuple(reasons),
            )

        return self._commit(
            target,
            trigger=TradeStateTrigger.PROMOTE,
            reasons=("promote",),
            clock_ms=clock_ms,
        )

    def downgrade(
        self,
        *,
        reason: str,
        clock_ms: int | None = None,
    ) -> StateMachineDecision:
        """Step one rung down the ladder.

        Used by the CONFIRM-failure handler and by the SCOUT timeout
        path. Refuses cleanly when the current state has no downgrade
        target (e.g. NO_TRADE, ATTACK, RIGHT_TAIL_AMPLIFY,
        DISTRIBUTION_ALERT, LOCK_PROFIT, FORCED_EXIT). The caller
        should pick the right exit primitive (lock_profit / forced_exit)
        for those states explicitly.
        """
        target = DOWNGRADE_LADDER.get(self._state)
        if target is None:
            self._refusals += 1
            return StateMachineDecision(
                accepted=False,
                from_state=self._state,
                to_state=self._state,
                trigger=TradeStateTrigger.DOWNGRADE,
                reasons=(f"no_downgrade_target_from_{self._state.value}",),
            )
        return self._commit(
            target,
            trigger=TradeStateTrigger.DOWNGRADE,
            reasons=(reason,),
            clock_ms=clock_ms,
        )

    # ------------------------------------------------------------------
    # Failure / timeout helpers (Spec §26.4)
    # ------------------------------------------------------------------
    def record_breakout_failure(
        self, *, clock_ms: int | None = None
    ) -> StateMachineDecision | None:
        """Record one failed breakout while in CONFIRM. After
        :attr:`TimeoutConfig.confirm_failure_downgrade_threshold`
        consecutive failures, downgrade SCOUT.

        Returns the downgrade decision when the threshold is crossed,
        otherwise ``None``.
        """
        if self._state is not TradeState.CONFIRM:
            return None
        self._breakout_failures += 1
        if (
            self._breakout_failures
            >= self._config.confirm_failure_downgrade_threshold
        ):
            self._breakout_failures = 0
            return self._commit(
                TradeState.SCOUT,
                trigger=TradeStateTrigger.DOWNGRADE,
                reasons=("confirm_breakout_failed",),
                clock_ms=clock_ms,
            )
        return None

    def record_distribution_bar(
        self, *, clock_ms: int | None = None
    ) -> StateMachineDecision | None:
        """Record one bar that confirmed distribution while in
        DISTRIBUTION_ALERT. After the configured number of bars,
        transition to FORCED_EXIT (Spec §26.4: "持续 3 根 K -> 减仓或退出"
        - we choose FORCED_EXIT because the caller has the knowledge
        of "reduce or exit"; Phase 7 ships the exit branch and Phase 9
        will add a "reduce" fork)."""
        if self._state is not TradeState.DISTRIBUTION_ALERT:
            return None
        self._distribution_bars += 1
        if (
            self._distribution_bars
            >= self._config.distribution_alert_bars_until_exit
        ):
            self._distribution_bars = 0
            return self._commit(
                TradeState.FORCED_EXIT,
                trigger=TradeStateTrigger.DISTRIBUTION_ALERT,
                reasons=("distribution_alert_bars_exceeded",),
                clock_ms=clock_ms,
            )
        return None

    def lock_profit(
        self,
        *,
        reason: str = "lock_profit_requested",
        clock_ms: int | None = None,
    ) -> StateMachineDecision:
        """Transition into LOCK_PROFIT from any state where it is
        allowed. Used by Phase 7 to enforce the "ATTACK weakens ->
        LOCK_PROFIT" and "RIGHT_TAIL_AMPLIFY core failed -> LOCK_PROFIT"
        transitions in :meth:`tick`.
        """
        return self.transition_to(
            TradeState.LOCK_PROFIT,
            trigger=TradeStateTrigger.LOCK_PROFIT,
            reasons=(reason,),
            clock_ms=clock_ms,
        )

    def distribution_alert(
        self,
        *,
        reason: str = "distribution_alert_signal",
        clock_ms: int | None = None,
    ) -> StateMachineDecision:
        """Transition into DISTRIBUTION_ALERT (Spec §26.1)."""
        return self.transition_to(
            TradeState.DISTRIBUTION_ALERT,
            trigger=TradeStateTrigger.DISTRIBUTION_ALERT,
            reasons=(reason,),
            clock_ms=clock_ms,
        )

    def forced_exit(
        self,
        *,
        reason: str = "forced_exit_requested",
        clock_ms: int | None = None,
    ) -> StateMachineDecision:
        """Sticky transition to FORCED_EXIT. Always accepted (every
        state has FORCED_EXIT in its transition set EXCEPT
        FORCED_EXIT itself, which is no-op).

        Phase 7 rule 7: FORCED_EXIT cannot be cancelled by LLM or
        human ordinary command - the State Machine itself only
        leaves it via :meth:`reset` (Reconciliation / human, Issue
        #9 / #10).
        """
        if self._state is TradeState.FORCED_EXIT:
            return StateMachineDecision(
                accepted=True,
                from_state=self._state,
                to_state=self._state,
                trigger=TradeStateTrigger.FORCED_EXIT,
                reasons=("already_forced_exit",),
            )
        return self.transition_to(
            TradeState.FORCED_EXIT,
            trigger=TradeStateTrigger.FORCED_EXIT,
            reasons=(reason,),
            clock_ms=clock_ms,
        )

    def reset(
        self,
        *,
        reason: str = "operator_reset",
        clock_ms: int | None = None,
    ) -> StateMachineDecision:
        """Hard reset to NO_TRADE. The only way to leave FORCED_EXIT.

        Phase 7 reserves this entry point for Reconciliation
        (Issue #9) and authorised Telegram /resume flow (Issue #10).
        It bypasses the transition whitelist deliberately because it
        is the operator override.
        """
        prev = self._state
        self._state = TradeState.NO_TRADE
        self._entered_at_ms = clock_ms if clock_ms is not None else now_ms()
        self._breakout_failures = 0
        self._distribution_bars = 0
        decision = StateMachineDecision(
            accepted=True,
            from_state=prev,
            to_state=TradeState.NO_TRADE,
            trigger=TradeStateTrigger.RESET,
            reasons=(reason,),
        )
        self._transitions += 1
        self._emit(decision)
        return decision

    # ------------------------------------------------------------------
    # Tick: deterministic timeout enforcement (Spec §26.4)
    # ------------------------------------------------------------------
    def tick(
        self,
        *,
        clock_ms: int,
        cvd_weakening: bool = False,
        right_tail_core_failed: bool = False,
    ) -> StateMachineDecision | None:
        """Advance state if a deadline has been crossed.

        Phase 7 enforces:

          - OBSERVE timeout -> NO_TRADE.
          - SCOUT timeout -> NO_TRADE (Spec §26.4 says "平仓 / 降级"
            but the Phase 7 trade-level state has no scout-position
            concept yet - Issue #9 will add the position-level fork).
          - ATTACK + ``cvd_weakening=True`` -> LOCK_PROFIT.
          - RIGHT_TAIL_AMPLIFY + ``right_tail_core_failed=True``
            -> LOCK_PROFIT.
        """
        elapsed = clock_ms - self._entered_at_ms

        if (
            self._state is TradeState.OBSERVE
            and elapsed >= self._config.observe_timeout_ms
        ):
            self._timeouts_fired += 1
            return self._commit(
                TradeState.NO_TRADE,
                trigger=TradeStateTrigger.TIMEOUT,
                reasons=("observe_timeout",),
                clock_ms=clock_ms,
            )

        if (
            self._state is TradeState.SCOUT
            and elapsed >= self._config.scout_timeout_ms
        ):
            self._timeouts_fired += 1
            return self._commit(
                TradeState.NO_TRADE,
                trigger=TradeStateTrigger.TIMEOUT,
                reasons=("scout_timeout",),
                clock_ms=clock_ms,
            )

        if (
            self._state is TradeState.ATTACK
            and self._config.attack_lock_profit_on_weakening
            and cvd_weakening
        ):
            self._timeouts_fired += 1
            return self._commit(
                TradeState.LOCK_PROFIT,
                trigger=TradeStateTrigger.LOCK_PROFIT,
                reasons=("attack_cvd_weakening",),
                clock_ms=clock_ms,
            )

        if (
            self._state is TradeState.RIGHT_TAIL_AMPLIFY
            and self._config.right_tail_lock_profit_on_core_failure
            and right_tail_core_failed
        ):
            self._timeouts_fired += 1
            return self._commit(
                TradeState.LOCK_PROFIT,
                trigger=TradeStateTrigger.LOCK_PROFIT,
                reasons=("right_tail_core_failed",),
                clock_ms=clock_ms,
            )

        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _commit(
        self,
        target: TradeState,
        *,
        trigger: TradeStateTrigger,
        reasons: tuple[str, ...],
        clock_ms: int | None,
    ) -> StateMachineDecision:
        if target not in ALLOWED_TRANSITIONS.get(self._state, frozenset()):
            self._refusals += 1
            raise IllegalStateTransition(
                f"Trade-state transition forbidden: "
                f"{self._state.value} -> {target.value}"
            )
        prev = self._state
        self._state = target
        self._entered_at_ms = clock_ms if clock_ms is not None else now_ms()
        # Counters that depend on the new state.
        if target is TradeState.CONFIRM:
            self._breakout_failures = 0
        if target is TradeState.DISTRIBUTION_ALERT:
            self._distribution_bars = 0
        decision = StateMachineDecision(
            accepted=True,
            from_state=prev,
            to_state=target,
            trigger=trigger,
            reasons=reasons,
        )
        self._transitions += 1
        self._emit(decision)
        return decision

    def _emit(self, decision: StateMachineDecision) -> None:
        if self._event_repo is None:
            return
        payload: dict[str, Any] = {
            "symbol": self._symbol,
            "from": decision.from_state.value,
            "to": decision.to_state.value,
            "trigger": decision.trigger.value,
            "reasons": list(decision.reasons),
            "entered_at_ms": self._entered_at_ms,
        }
        self._event_repo.append_event(
            Event(
                event_type=EventType.STATE_TRANSITION,
                source_module=self.SOURCE_MODULE,
                symbol=self._symbol,
                payload=payload,
            )
        )
