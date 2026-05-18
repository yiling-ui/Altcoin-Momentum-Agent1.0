"""Risk Engine skeleton (Spec §27, Issue #1; extended in Issue #6).

Phase 1 contract
----------------
The Risk Engine has *final authority*. No module may bypass it. In Phase 1
we ship a minimal but real implementation that:

    1. Refuses any action whose `live_trading_required` flag is True while
       the system is not in a live mode (always the case in Phase 1).
    2. Refuses any action requesting `right_tail_amplify=True` while
       `right_tail_enabled` is False (always the case in Phase 1).
    3. Approves anything else with a `paper_only` annotation, and writes
       a `RISK_APPROVED` or `RISK_REJECTED` event when an `EventRepository`
       is supplied.

This skeleton is intentionally conservative: no thresholds, no portfolio
heat, no circuit breaker. Those land with Issue #7.

Phase 6 extension (Issue #6)
----------------------------
Issue #6 requires the Risk Engine to honour the manipulation level and
the real-trade confirmation level produced by the Phase 6 classifiers:

    - ManipulationLevel.M3 -> reject ALL **new** openings (Spec §21.3
      hard rule "M3 禁止交易"). M3 is a hard wall on new openings.

      **IMPORTANT - Phase 6 only implements the new-opening
      protection semantic.** Phase 7 (State Machine + full Risk
      Engine) and Phase 9 (Execution FSM + Reconciliation) MUST
      preserve protective-exit and reduce-only closing flows under
      M3:

        * `LOCK_PROFIT`, `FORCED_EXIT`, `DISTRIBUTION_ALERT` -> exit
          transitions and stop-confirmation routing must remain
          allowed when manipulation_level=M3. Refusing them would
          trap a live position when manipulation is detected and is
          a P0 incident, not a safety win.
        * `kill_all` and reduce-only closing orders must remain
          allowed regardless of manipulation_level - they shrink
          exposure, never grow it.
        * Reconciliation (Issue #9) must be allowed to read /
          re-attach stop-loss state under M3.

      Phase 7 will add an explicit `is_protective_exit=True` (or
      equivalent) flag on `RiskRequest` so the M3 branch can
      distinguish "open" from "close / reduce / protect". Phase 6
      does NOT ship that flag because Phase 6 has no exit path of
      its own - every Phase 6 caller is a non-attack self-check or
      a forward-looking opening adjudication.
    - ManipulationLevel.M2 -> reject ATTACK / RIGHT_TAIL_AMPLIFY
      candidates (Spec §21.3 hard rule "M2 禁止进攻"). Smaller scout /
      observe candidates may continue.
    - TradeConfirmationLevel.T0 / T1 -> reject ATTACK candidates
      (Issue #6 hard rule "T0/T1 不允许进攻"). T0 / T1 + scout /
      observe is allowed; the scanner output is also captured in the
      RISK_REJECTED audit payload regardless.

The new check is gated by ``attack_intent`` so a non-attack action
(e.g. observe, scout, exit, kill_all) is never blocked by an M2 or
T0/T1 reading. ``right_tail_amplify=True`` always implies
``attack_intent`` for the purposes of this gate.

Issue #7 will replace these point-checks with a real No-Trade Gate.
The Phase 6 hooks here are deliberately additive: they extend the
Phase 1 hard rejection set without removing or weakening any of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.config.settings import Settings, get_settings
from app.core.enums import (
    ManipulationLevel,
    TradeConfirmationLevel,
    TradingMode,
)
from app.core.events import Event, EventType
from app.database.repositories import EventRepository


@dataclass(frozen=True)
class RiskRequest:
    """Request submitted to the Risk Engine for adjudication.

    The Phase 1 skeleton recognises four hard-rejection flags drawn from
    Spec §27.2 (No-Trade Gate) and Spec §31.3 (Reconciliation):

        - live_trading_required: caller wants a real exchange order.
          Always rejected in Phase 1 (live_trading_enabled=False).
        - right_tail_amplify:    caller wants right-tail amplification.
          Always rejected in Phase 1 (right_tail_enabled=False).
        - stop_unconfirmed:      stop-loss state is not confirmed.
          Spec §4.2 + §27.2: forbid new positions until confirmed.
        - unknown_position:      local/exchange position state unknown.
          Spec §31.3: 'positions unknown -> trading forbidden'.

    Phase 6 (Issue #6) adds three optional fields that let the engine
    honour the manipulation level and the real-trade confirmation level
    produced by the Phase 6 classifiers:

        - manipulation_level: result of Spec §21 ManipulationDetector.
        - trade_confirmation_level: result of Spec §20
          RealTradeConfirmation.
        - attack_intent: caller intends an ATTACK / RIGHT_TAIL_AMPLIFY
          transition (or any action that opens / scales an attack
          position). When False, the M2 / T0 / T1 attack guards do
          NOT fire because they are size-class gates, not blanket
          bans. Setting ``right_tail_amplify=True`` implicitly raises
          ``attack_intent`` for the duration of the call.

    Issue #7 will replace these point-checks with a real No-Trade Gate.
    """

    source_module: str
    action: str
    symbol: str | None = None
    live_trading_required: bool = False
    right_tail_amplify: bool = False
    stop_unconfirmed: bool = False
    unknown_position: bool = False
    # Phase 6 hooks (Issue #6).
    manipulation_level: ManipulationLevel | None = None
    trade_confirmation_level: TradeConfirmationLevel | None = None
    attack_intent: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def effective_attack_intent(self) -> bool:
        """``right_tail_amplify=True`` always implies attack intent."""
        return bool(self.attack_intent or self.right_tail_amplify)


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reasons: list[str]
    request: RiskRequest

    @property
    def rejected(self) -> bool:
        return not self.approved


class RiskEngine:
    """Phase 1 skeleton with hard-coded safety checks."""

    def __init__(
        self,
        settings: Settings | None = None,
        event_repo: EventRepository | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._event_repo = event_repo

    @property
    def settings(self) -> Settings:
        return self._settings

    def evaluate(self, request: RiskRequest) -> RiskDecision:
        reasons: list[str] = []

        if request.live_trading_required and not self._settings.live_trading_enabled:
            reasons.append("live_trading_disabled")
        if request.right_tail_amplify and not self._settings.right_tail_enabled:
            reasons.append("right_tail_disabled")
        if request.stop_unconfirmed:
            # Spec §4.2 + §27.2: do not open new positions while stop is unconfirmed.
            reasons.append("stop_unconfirmed")
        if request.unknown_position:
            # Spec §31.3: position state unknown -> trading forbidden.
            reasons.append("unknown_position")
        if self._settings.trading_mode != TradingMode.PAPER.value and not (
            self._settings.live_trading_enabled
        ):
            # Defence in depth: trading_mode promoted but live still off.
            reasons.append("trading_mode_inconsistent")

        # Phase 6 hard rules (Issue #6, Spec §21.3 + §20.4).
        # IMPORTANT: the M3 branch below blocks NEW openings only.
        # Phase 7 (State Machine + full Risk Engine) and Phase 9
        # (Execution FSM + Reconciliation) MUST preserve protective
        # exit and reduce-only closing flows under M3 - LOCK_PROFIT,
        # FORCED_EXIT, DISTRIBUTION_ALERT, kill_all, and stop-loss
        # re-attachment paths must remain allowed when
        # manipulation_level=M3. Phase 6 ships only the new-opening
        # protection semantic; Phase 7 will add an explicit flag on
        # RiskRequest so the M3 branch can distinguish "open" from
        # "close / reduce / protect".
        attack_intent = request.effective_attack_intent
        if request.manipulation_level is ManipulationLevel.M3:
            # M3 is a hard wall: no new opening, no scout, no amplify.
            reasons.append("manipulation_m3")
        elif (
            request.manipulation_level is ManipulationLevel.M2
            and attack_intent
        ):
            # M2: forbid attack-class candidates only.
            reasons.append("manipulation_m2_attack")
        if attack_intent and request.trade_confirmation_level in (
            TradeConfirmationLevel.T0,
            TradeConfirmationLevel.T1,
        ):
            reasons.append(
                "trade_confirmation_too_low_for_attack"
            )

        approved = not reasons
        if approved:
            reasons = ["paper_only_skeleton_approval"]

        decision = RiskDecision(approved=approved, reasons=reasons, request=request)
        self._record(decision)
        return decision

    # ------------------------------------------------------------------
    def _record(self, decision: RiskDecision) -> None:
        if self._event_repo is None:
            return
        ev_type = EventType.RISK_APPROVED if decision.approved else EventType.RISK_REJECTED
        self._event_repo.append(
            Event(
                event_type=ev_type,
                source_module="risk_engine",
                symbol=decision.request.symbol,
                payload={
                    "action": decision.request.action,
                    "source_module": decision.request.source_module,
                    "reasons": list(decision.reasons),
                    "live_trading_required": decision.request.live_trading_required,
                    "right_tail_amplify": decision.request.right_tail_amplify,
                    "stop_unconfirmed": decision.request.stop_unconfirmed,
                    "unknown_position": decision.request.unknown_position,
                    "attack_intent": decision.request.effective_attack_intent,
                    "manipulation_level": (
                        decision.request.manipulation_level.value
                        if decision.request.manipulation_level is not None
                        else None
                    ),
                    "trade_confirmation_level": (
                        decision.request.trade_confirmation_level.value
                        if decision.request.trade_confirmation_level is not None
                        else None
                    ),
                },
            )
        )
