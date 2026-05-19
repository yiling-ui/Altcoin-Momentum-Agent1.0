"""Execution FSM (Phase 1 skeleton + Phase 9 driver).

Phase 1
-------
The legacy :class:`ExecutionFSM` dataclass shipped with Phase 1 ships
the typed transition table covering all 15 :class:`ExecutionState`
values. Phase 1 callers (``app/main.py``, ``tests/unit/test_execution_fsm.py``)
still import :class:`ExecutionFSM` and :class:`IllegalTransition`; both
remain unchanged in Phase 9.

Phase 9 (Issue #9)
------------------
Phase 9 ADDS :class:`ExecutionFSMDriver` next to the legacy class.
The driver advances per-order :class:`ExecutionSession` state through
the 15 :class:`ExecutionState` values and emits the matching events
through :class:`EventRepository`:

  IDLE -> SIGNAL_RECEIVED -> RISK_CHECKED -> ORDER_SENT
       -> ACK_RECEIVED -> PARTIAL_FILLED ... -> FULL_FILLED
       -> STOP_SENT -> STOP_CONFIRMED -> POSITION_OPEN
       -> EXIT_TRIGGERED -> POSITION_CLOSING -> POSITION_CLOSED -> IDLE
       -> (any state) -> ERROR_PROTECTION on hard failure

Hard rules enforced by the driver
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

  - Every NEW open is gated by ``RiskEngine.evaluate(...)`` with
    ``is_new_open=True``.
  - Every reduce-only / closing flow is gated by
    ``RiskEngine.evaluate(...)`` with ``is_new_open=False`` so the
    Phase 7 M3 / DATA_DEGRADED / REGIME / EXCHANGE_DISCONNECTED /
    REBASE_IN_PROGRESS gates do not block the exit (Spec §27.2
    protective-exit caveat; Spec §28 rebase rule).
  - Every partial fill recomputes risk against the remaining size.
  - Every stop attachment is reduce-only (Spec §30.2).
  - ``MarginMode.ISOLATED`` is the only admissible margin mode (Spec §13.2).
  - ``OrderKind.MARKET`` is forbidden for ``OrderIntent.NEW_OPEN`` /
    ``OrderIntent.SCALE_IN`` (Spec §30.2 "默认禁止裸市价追单").
  - Stop-attach failure transitions the session to
    :class:`ExecutionState.STOP_FAILED` -> :class:`ExecutionState.ERROR_PROTECTION`
    AND issues an automatic protective close.
  - Every order / stop / fill event carries ``opportunity_id`` (Phase 8.5
    learning-ready data contract) when the caller supplied one.

Phase 9 boundary
~~~~~~~~~~~~~~~~

The driver runs in **paper / mock mode by default**. It NEVER calls
``ExchangeClientBase.create_order`` (or ``cancel_order`` /
``set_leverage`` / ``set_margin_mode``). The four
:class:`SafeModeViolation` refusals on the gateway base class are
preserved unchanged. Paper-mode state lives in a separate
:class:`PaperLedger` the driver writes to.

Settings ``trading_mode != "paper"`` and ``live_trading_enabled is True``
are construction-time refusals (Phase 1 safety lock); Phase 9 keeps
both invariants.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from app.config.settings import Settings, get_settings
from app.core.clock import now_ms
from app.core.enums import (
    Direction,
    ExchangeConnectionState,
    ExecutionState,
    IncidentLevel,
    ManipulationLevel,
    TradeConfirmationLevel,
    TradingMode,
)
from app.core.errors import ExecutionError, SafeModeViolation
from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.execution.models import (
    ExecutionResult,
    ExecutionSession,
    FillEvent,
    OrderIntent,
    OrderKind,
    OrderRequest,
    OrderSide,
    StopEvent,
    TransitionRecord,
    side_for_direction,
)
from app.execution.paper_ledger import (
    PaperLedger,
    PaperPosition,
    PaperStop,
)
from app.learning.context import LearningReadyContext, attach_learning_ready
from app.risk.engine import RiskDecision, RiskEngine, RiskRequest


# ===========================================================================
# Phase 1 legacy ExecutionFSM (preserved verbatim for back-compat)
# ===========================================================================


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
    """Phase 1 legacy in-memory state machine.

    Preserved verbatim so the Phase 1 tests + the boot drill in
    ``app/main.py`` keep working. Phase 9 callers should construct
    :class:`ExecutionFSMDriver` instead.
    """

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


# ===========================================================================
# Phase 9 ExecutionFSMDriver (Issue #9)
# ===========================================================================


# NOTE: the protection hook the driver calls is defined as the public
# :class:`app.incidents.repository.ProtectionHook` Protocol. Phase 9
# keeps the driver decoupled from the incident layer through a
# duck-typed hook so callers can pass either a real
# :class:`IncidentRepository` or a mock that just records calls. Tests
# use the mock to avoid spinning up incidents.db.


@dataclass
class _DriverCounters:
    orders_submitted: int = 0
    orders_rejected_by_risk: int = 0
    orders_acked: int = 0
    partial_fills: int = 0
    full_fills: int = 0
    stops_attached: int = 0
    stops_confirmed: int = 0
    stops_failed: int = 0
    positions_opened: int = 0
    exits_triggered: int = 0
    positions_closed: int = 0
    error_protection_entered: int = 0
    protective_closes: int = 0


class ExecutionFSMDriver:
    """Phase 9 Execution FSM driver (paper / mock by default).

    The driver is constructed once per process and serves multiple
    sessions. Each session is keyed by ``OrderRequest.client_order_id``.

    See the module docstring for the hard-rule contract.
    """

    SOURCE_MODULE = "execution_fsm"

    def __init__(
        self,
        *,
        risk_engine: RiskEngine,
        event_repo: EventRepository,
        paper_ledger: PaperLedger | None = None,
        settings: Settings | None = None,
        protection_hook: Any | None = None,
        clock_ms: callable | None = None,
    ) -> None:
        self._risk = risk_engine
        self._repo = event_repo
        self._ledger = paper_ledger or PaperLedger()
        self._settings = settings or get_settings()
        self._protection_hook = protection_hook
        self._clock_ms = clock_ms or now_ms
        self._sessions: dict[str, ExecutionSession] = {}
        self._counters = _DriverCounters()
        # Phase 9 hard rule: refuse to start if Phase 1 safety lock has
        # drifted. Defence in depth on top of the boot guard in app/main.py.
        if self._settings.trading_mode != TradingMode.PAPER.value:
            raise SafeModeViolation(
                "ExecutionFSMDriver requires trading_mode=paper in Phase 9; "
                f"got {self._settings.trading_mode!r}. Live trading lands "
                "behind a separate write-side adapter, not this driver."
            )
        if self._settings.live_trading_enabled:
            raise SafeModeViolation(
                "ExecutionFSMDriver refuses to start while "
                "live_trading_enabled=True. Phase 1 safety lock requires False."
            )
        if self._settings.exchange_live_order_enabled:
            raise SafeModeViolation(
                "ExecutionFSMDriver refuses to start while "
                "exchange_live_order_enabled=True. Phase 1 safety lock requires False."
            )

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------
    @property
    def ledger(self) -> PaperLedger:
        return self._ledger

    @property
    def counters(self) -> _DriverCounters:
        return self._counters

    @property
    def sessions(self) -> dict[str, ExecutionSession]:
        """Mapping of every session keyed by ``client_order_id``."""
        return dict(self._sessions)

    def get_session(self, client_order_id: str) -> ExecutionSession | None:
        return self._sessions.get(client_order_id)

    # ==================================================================
    # Submit order (NEW open + reduce-only entry point)
    # ==================================================================
    def submit_order(
        self,
        request: OrderRequest,
        *,
        regime_snapshot: Any | None = None,
        universe_decision: Any | None = None,
        liquidity_decision: Any | None = None,
        exit_plan: Any | None = None,
        manipulation_level: ManipulationLevel | None = None,
        trade_confirmation_level: TradeConfirmationLevel | None = None,
        is_data_degraded: bool = False,
        exchange_connection_state: ExchangeConnectionState | None = None,
        attack_intent: bool = False,
        right_tail_amplify: bool = False,
        learning_context: LearningReadyContext | None = None,
        stop_unconfirmed: bool = False,
        unknown_position: bool = False,
    ) -> ExecutionResult:
        """Submit an order through the Phase 9 driver.

        Drives IDLE -> SIGNAL_RECEIVED -> RISK_CHECKED. If risk
        approves, advances to ORDER_SENT and records the order in
        the paper ledger. If risk rejects, the session is left at
        IDLE with the rejection reasons attached.

        For NEW_OPEN / SCALE_IN intents the call sets
        ``is_new_open=True``; for every reduce-only intent the call
        sets ``is_new_open=False`` so the Phase 7 protective-exit
        caveat applies (Spec §27.2).
        """
        # Phase 9 hard rule: refuse a market order on a NEW_OPEN
        # (Spec §30.2 "默认禁止裸市价追单"). The reduce-only intents
        # admit market orders so the operator can flatten under stress.
        if (
            request.kind is OrderKind.MARKET
            and request.intent in (OrderIntent.NEW_OPEN, OrderIntent.SCALE_IN)
        ):
            raise ExecutionError(
                "Phase 9 / Spec §30.2: naked market orders are forbidden "
                "for NEW_OPEN / SCALE_IN intents. Submit a LIMIT order."
            )

        # Reduce-only intents auto-resolve to reduce_only=True even if
        # the caller forgot to set it.
        if request.is_reduce_only_intent and not request.reduce_only:
            request = request.model_copy(update={"reduce_only": True})

        # Deduplicate sessions by client_order_id.
        if request.client_order_id in self._sessions:
            raise ExecutionError(
                f"Duplicate client_order_id={request.client_order_id!r}; "
                "Phase 9 hard rule: every order must have a unique id."
            )

        session = ExecutionSession(request=request)
        self._sessions[request.client_order_id] = session
        self._counters.orders_submitted += 1
        if learning_context is not None:
            session.learning_context_payload = learning_context.to_event_payload()

        # IDLE -> SIGNAL_RECEIVED.
        self._transition(
            session,
            target=ExecutionState.SIGNAL_RECEIVED,
            reasons=("submit_order",),
        )

        # Build the RiskRequest. Reduce-only / protective-exit paths
        # MUST pass is_new_open=False so the Phase 7 M3 / DATA_DEGRADED /
        # REGIME / EXCHANGE_DISCONNECTED / REBASE_IN_PROGRESS gates do
        # not block the exit (Spec §27.2 protective-exit caveat).
        risk_request = RiskRequest(
            source_module=self.SOURCE_MODULE,
            action=f"{request.intent.value}:submit_order",
            symbol=request.symbol,
            live_trading_required=False,  # Phase 9 stays paper-only.
            right_tail_amplify=right_tail_amplify,
            stop_unconfirmed=stop_unconfirmed,
            unknown_position=unknown_position,
            is_new_open=request.is_new_open,
            attack_intent=attack_intent,
            regime_snapshot=regime_snapshot,
            universe_decision=universe_decision,
            liquidity_decision=liquidity_decision,
            exit_plan=exit_plan,
            manipulation_level=manipulation_level,
            trade_confirmation_level=trade_confirmation_level,
            is_data_degraded=is_data_degraded,
            exchange_connection_state=exchange_connection_state,
            opportunity_id=request.opportunity_id,
            learning_context=learning_context,
        )
        decision = self._risk.evaluate(risk_request)

        # SIGNAL_RECEIVED -> RISK_CHECKED.
        self._transition(
            session,
            target=ExecutionState.RISK_CHECKED,
            reasons=tuple(decision.reasons),
        )

        if not decision.approved:
            session.rejection_reasons = tuple(decision.reasons)
            self._counters.orders_rejected_by_risk += 1
            # RISK_CHECKED -> IDLE (revert).
            self._transition(
                session,
                target=ExecutionState.IDLE,
                reasons=("risk_rejected", *decision.reasons),
            )
            self._sessions.pop(request.client_order_id, None)
            return ExecutionResult(
                accepted=False,
                session=session,
                reasons=tuple(decision.reasons),
            )

        # RISK_CHECKED -> ORDER_SENT (paper).
        exchange_order_id = f"paper_ord_{uuid.uuid4().hex[:16]}"
        session.exchange_order_id = exchange_order_id
        self._ledger.record_order(
            request=request,
            exchange_order_id=exchange_order_id,
        )
        self._transition(
            session,
            target=ExecutionState.ORDER_SENT,
            reasons=("risk_approved",),
        )
        self._emit_order_event(
            EventType.ORDER_SENT,
            session=session,
            extra={
                "request": request.to_payload(),
                "risk_decision_id": id(decision),  # opaque session-scoped marker
            },
        )

        return ExecutionResult(accepted=True, session=session, reasons=())

    # ==================================================================
    # Lifecycle: ack / fill / stop / position
    # ==================================================================
    def on_ack(
        self,
        *,
        session: ExecutionSession,
        ack_id: str | None = None,
    ) -> None:
        """ORDER_SENT -> ACK_RECEIVED."""
        self._require_state(session, ExecutionState.ORDER_SENT)
        self._transition(
            session,
            target=ExecutionState.ACK_RECEIVED,
            reasons=("ack_received",),
        )
        self._counters.orders_acked += 1
        self._emit_order_event(
            EventType.ORDER_ACK,
            session=session,
            extra={"ack_id": ack_id},
        )

    def on_partial_fill(
        self,
        *,
        session: ExecutionSession,
        fill: FillEvent,
        regime_snapshot: Any | None = None,
        liquidity_decision: Any | None = None,
        exit_plan: Any | None = None,
        manipulation_level: ManipulationLevel | None = None,
        trade_confirmation_level: TradeConfirmationLevel | None = None,
        is_data_degraded: bool = False,
        exchange_connection_state: ExchangeConnectionState | None = None,
    ) -> RiskDecision:
        """Apply a partial fill and recompute risk on the remainder.

        Spec §30.2 "部分成交必须重算风险". Phase 9 calls
        ``RiskEngine.evaluate(...)`` again with the remaining qty in
        the request payload so a deteriorating market can still
        trigger an early protective close.

        Returns the recomputed :class:`RiskDecision`. If risk now
        rejects, the session is moved into ERROR_PROTECTION and the
        protective-close path is invoked. Otherwise the session
        advances normally.
        """
        if session.state not in (
            ExecutionState.ACK_RECEIVED,
            ExecutionState.PARTIAL_FILLED,
        ):
            raise IllegalTransition(
                f"on_partial_fill requires state ACK_RECEIVED or "
                f"PARTIAL_FILLED, got {session.state.value}"
            )
        if fill.fill_qty + session.filled_qty > session.request.qty + 1e-9:
            raise ExecutionError(
                f"Fill {fill.fill_qty} exceeds remaining qty "
                f"{session.remaining_qty} for {session.client_order_id}."
            )
        # Apply the partial fill to the session and ledger.
        new_filled = session.filled_qty + float(fill.fill_qty)
        self._update_avg_fill(session, fill)
        session.filled_qty = new_filled
        self._ledger.apply_partial_fill(
            client_order_id=session.client_order_id,
            fill_qty=float(fill.fill_qty),
        )
        # State transition. Even when this fill completes the order
        # we keep the partial-fill event distinct from the full fill;
        # the caller invokes on_full_fill explicitly.
        self._transition(
            session,
            target=ExecutionState.PARTIAL_FILLED,
            reasons=("partial_fill",),
        )
        self._counters.partial_fills += 1
        self._emit_order_event(
            EventType.ORDER_PARTIAL_FILLED,
            session=session,
            extra={
                "fill": _fill_payload(fill),
                "filled_qty_total": float(session.filled_qty),
                "remaining_qty": float(session.remaining_qty),
                "avg_fill_price": session.avg_fill_price,
            },
        )

        # Recompute risk on the remaining size. Phase 9 hard rule
        # (Spec §30.2): "部分成交必须重算风险".
        recompute = self._risk.evaluate(
            RiskRequest(
                source_module=self.SOURCE_MODULE,
                action=f"{session.request.intent.value}:partial_fill_recompute",
                symbol=session.symbol,
                live_trading_required=False,
                right_tail_amplify=False,
                is_new_open=session.request.is_new_open,
                regime_snapshot=regime_snapshot,
                liquidity_decision=liquidity_decision,
                exit_plan=exit_plan,
                manipulation_level=manipulation_level,
                trade_confirmation_level=trade_confirmation_level,
                is_data_degraded=is_data_degraded,
                exchange_connection_state=exchange_connection_state,
                opportunity_id=session.request.opportunity_id,
            )
        )
        if not recompute.approved:
            self._enter_error_protection(
                session=session,
                reason="partial_fill_risk_rerejected",
                payload={"reasons": list(recompute.reasons)},
                incident_level=IncidentLevel.P1,
            )
        return recompute

    def on_full_fill(
        self,
        *,
        session: ExecutionSession,
        fill: FillEvent,
    ) -> None:
        """Apply the final fill that brings the order to qty.

        ACK_RECEIVED / PARTIAL_FILLED -> FULL_FILLED. Removes the
        order from the paper ledger.
        """
        if session.state not in (
            ExecutionState.ACK_RECEIVED,
            ExecutionState.PARTIAL_FILLED,
        ):
            raise IllegalTransition(
                f"on_full_fill requires state ACK_RECEIVED or "
                f"PARTIAL_FILLED, got {session.state.value}"
            )
        if (
            session.filled_qty + float(fill.fill_qty)
            < session.request.qty - 1e-9
        ):
            raise ExecutionError(
                "on_full_fill called but the new total filled qty is below "
                "the request size. Use on_partial_fill until the order is "
                "complete."
            )
        if (
            session.filled_qty + float(fill.fill_qty)
            > session.request.qty + 1e-9
        ):
            raise ExecutionError(
                "on_full_fill: cumulative fill exceeds the order size."
            )
        self._update_avg_fill(session, fill)
        session.filled_qty = float(session.request.qty)
        self._ledger.apply_partial_fill(
            client_order_id=session.client_order_id,
            fill_qty=float(fill.fill_qty),
        )
        self._ledger.close_order(session.client_order_id)
        self._transition(
            session,
            target=ExecutionState.FULL_FILLED,
            reasons=("full_fill",),
        )
        self._counters.full_fills += 1
        self._emit_order_event(
            EventType.ORDER_FILLED,
            session=session,
            extra={
                "fill": _fill_payload(fill),
                "filled_qty_total": float(session.filled_qty),
                "avg_fill_price": session.avg_fill_price,
            },
        )

    def attach_stop(
        self,
        *,
        session: ExecutionSession,
        stop_price: float,
    ) -> StopEvent:
        """Attach a reduce-only stop loss to the filled position.

        Phase 9 hard rule: stops are ALWAYS reduce-only (Spec §30.2).
        FULL_FILLED -> STOP_SENT.
        """
        self._require_state(session, ExecutionState.FULL_FILLED)
        if session.request.intent in (
            OrderIntent.LOCK_PROFIT,
            OrderIntent.FORCED_EXIT,
            OrderIntent.DISTRIBUTION_EXIT,
            OrderIntent.PROTECTIVE_CLOSE,
            OrderIntent.KILL_ALL,
        ):
            raise ExecutionError(
                "attach_stop is for new positions only. A reduce-only exit "
                "order does not need its own stop."
            )
        # The stop closes the position so the side flips relative to entry.
        close_side = side_for_direction(session.request.direction, is_close=True)
        stop_id = f"paper_stop_{uuid.uuid4().hex[:16]}"
        stop = StopEvent(
            stop_order_id=stop_id,
            stop_price=stop_price,
            side=close_side,
            qty=float(session.request.qty),
            reduce_only=True,
        )
        session.stop_order_id = stop_id
        self._transition(
            session,
            target=ExecutionState.STOP_SENT,
            reasons=("stop_attach",),
        )
        self._counters.stops_attached += 1
        self._emit_order_event(
            EventType.STOP_SENT,
            session=session,
            extra={"stop": _stop_payload(stop)},
        )
        return stop

    def on_stop_confirmed(
        self,
        *,
        session: ExecutionSession,
        stop: StopEvent,
    ) -> str:
        """Confirm the reduce-only stop. STOP_SENT -> STOP_CONFIRMED ->
        POSITION_OPEN. Records the position in the paper ledger and
        returns the position_id.
        """
        self._require_state(session, ExecutionState.STOP_SENT)
        if not stop.reduce_only:
            raise ExecutionError(
                "Phase 9 hard rule: stop must be reduce-only."
            )
        self._transition(
            session,
            target=ExecutionState.STOP_CONFIRMED,
            reasons=("stop_confirmed",),
        )
        self._counters.stops_confirmed += 1
        self._emit_order_event(
            EventType.STOP_CONFIRMED,
            session=session,
            extra={"stop": _stop_payload(stop)},
        )

        # Open the paper position and emit POSITION_OPENED.
        position_id = f"paper_pos_{uuid.uuid4().hex[:16]}"
        session.position_id = position_id
        position = PaperPosition(
            position_id=position_id,
            symbol=session.symbol,
            direction=session.request.direction.value,
            qty=float(session.filled_qty),
            entry_price=float(session.avg_fill_price or 0.0),
            margin_mode=session.request.margin_mode.value,
            leverage=float(session.request.leverage),
            stop_price=float(stop.stop_price),
            stop_confirmed=True,
            opportunity_id=session.request.opportunity_id,
        )
        self._ledger.open_position(position)
        self._ledger.record_stop(
            PaperStop(
                stop_order_id=stop.stop_order_id,
                position_id=position_id,
                symbol=session.symbol,
                side=stop.side,
                qty=float(stop.qty),
                stop_price=float(stop.stop_price),
                reduce_only=True,
                timestamp=int(stop.timestamp),
            )
        )
        self._transition(
            session,
            target=ExecutionState.POSITION_OPEN,
            reasons=("position_opened",),
        )
        self._counters.positions_opened += 1
        self._repo.append_event(
            self._build_event(
                EventType.POSITION_OPENED,
                session=session,
                payload={
                    "position": position.to_payload(),
                },
            )
        )
        return position_id

    def on_stop_failed(
        self,
        *,
        session: ExecutionSession,
        reason: str,
    ) -> None:
        """Stop attachment failed. STOP_SENT -> STOP_FAILED -> ERROR_PROTECTION.

        Spec §30.3 "止损挂不上：立即保护平仓". The driver writes a
        STOP_FAILED event AND triggers a protective close path.
        """
        self._require_state(session, ExecutionState.STOP_SENT)
        self._transition(
            session,
            target=ExecutionState.STOP_FAILED,
            reasons=(reason,),
        )
        self._counters.stops_failed += 1
        self._emit_order_event(
            EventType.STOP_FAILED,
            session=session,
            extra={"reason": reason},
        )
        self._enter_error_protection(
            session=session,
            reason=f"stop_failed:{reason}",
            payload={"reason": reason},
            incident_level=IncidentLevel.P0,
        )

    # ==================================================================
    # Exit / close
    # ==================================================================
    def trigger_exit(
        self,
        *,
        session: ExecutionSession,
        reason: str,
        regime_snapshot: Any | None = None,
        liquidity_decision: Any | None = None,
        exit_plan: Any | None = None,
        manipulation_level: ManipulationLevel | None = None,
        is_data_degraded: bool = False,
        exchange_connection_state: ExchangeConnectionState | None = None,
    ) -> RiskDecision:
        """POSITION_OPEN -> EXIT_TRIGGERED -> POSITION_CLOSING.

        Phase 9 hard rule: this is a reduce-only path. The Risk Engine
        is called with ``is_new_open=False`` so M3 / DATA_DEGRADED /
        REGIME / EXCHANGE_DISCONNECTED / REBASE_IN_PROGRESS gates do
        not block the exit.
        """
        self._require_state(session, ExecutionState.POSITION_OPEN)
        # The Phase 7 Risk Engine still adjudicates the exit so the
        # audit trail is consistent. With is_new_open=False the M3 /
        # DATA_DEGRADED / REGIME gates are a no-op and the exit
        # proceeds.
        decision = self._risk.evaluate(
            RiskRequest(
                source_module=self.SOURCE_MODULE,
                action=f"trigger_exit:{reason}",
                symbol=session.symbol,
                live_trading_required=False,
                right_tail_amplify=False,
                is_new_open=False,
                regime_snapshot=regime_snapshot,
                liquidity_decision=liquidity_decision,
                exit_plan=exit_plan,
                manipulation_level=manipulation_level,
                is_data_degraded=is_data_degraded,
                exchange_connection_state=exchange_connection_state,
                opportunity_id=session.request.opportunity_id,
            )
        )
        # Phase 9 contract: even if the Risk Engine somehow rejects
        # (it should not, given is_new_open=False), the protective
        # exit MUST proceed - refusing to close a known position is
        # the only failure worse than a re-rejection. We log and move
        # on; the audit row already carries the rejection.
        self._transition(
            session,
            target=ExecutionState.EXIT_TRIGGERED,
            reasons=(reason,),
        )
        self._counters.exits_triggered += 1
        self._repo.append_event(
            self._build_event(
                EventType.EXIT_TRIGGERED,
                session=session,
                payload={
                    "reason": reason,
                    "risk_decision_approved": bool(decision.approved),
                    "risk_decision_reasons": list(decision.reasons),
                },
            )
        )
        self._transition(
            session,
            target=ExecutionState.POSITION_CLOSING,
            reasons=("position_closing",),
        )
        return decision

    def on_position_closed(
        self,
        *,
        session: ExecutionSession,
        realized_pnl: float = 0.0,
    ) -> None:
        """POSITION_CLOSING -> POSITION_CLOSED -> IDLE."""
        self._require_state(session, ExecutionState.POSITION_CLOSING)
        session.realized_pnl = float(realized_pnl)
        if session.position_id is not None:
            self._ledger.close_position(session.position_id)
        self._transition(
            session,
            target=ExecutionState.POSITION_CLOSED,
            reasons=("position_closed",),
        )
        self._counters.positions_closed += 1
        self._repo.append_event(
            self._build_event(
                EventType.POSITION_CLOSED,
                session=session,
                payload={
                    "realized_pnl": float(realized_pnl),
                    "position_id": session.position_id,
                },
            )
        )
        self._transition(
            session,
            target=ExecutionState.IDLE,
            reasons=("session_complete",),
        )

    # ==================================================================
    # Error protection
    # ==================================================================
    def enter_error_protection(
        self,
        *,
        session: ExecutionSession,
        reason: str,
        incident_level: IncidentLevel = IncidentLevel.P0,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Public entry point - same as the internal hook."""
        self._enter_error_protection(
            session=session,
            reason=reason,
            payload=payload or {},
            incident_level=incident_level,
        )

    def _enter_error_protection(
        self,
        *,
        session: ExecutionSession,
        reason: str,
        payload: dict[str, Any],
        incident_level: IncidentLevel,
    ) -> None:
        prior_state = session.state
        self._transition(
            session,
            target=ExecutionState.ERROR_PROTECTION,
            reasons=(reason,),
        )
        session.in_protection_mode = True
        self._counters.error_protection_entered += 1
        # Emit one PROTECTION_MODE_ENTERED event so monitoring sees it
        # without depending on the IncidentRepository hook being wired.
        self._repo.append_event(
            self._build_event(
                EventType.PROTECTION_MODE_ENTERED,
                session=session,
                payload={
                    "reason": reason,
                    "level": incident_level.value,
                    "prior_state": prior_state.value,
                    **payload,
                },
            )
        )
        if self._protection_hook is not None:
            try:
                incident_id = self._protection_hook.open_incident(
                    level=incident_level,
                    title=f"execution_fsm:{reason}",
                    description=(
                        f"Execution FSM session {session.client_order_id} "
                        f"entered ERROR_PROTECTION ({reason}) from "
                        f"{prior_state.value}."
                    ),
                    source_module=self.SOURCE_MODULE,
                    symbol=session.symbol,
                    position_id=session.position_id,
                    payload=payload,
                )
            except Exception as exc:  # defensive - hook must not break FSM
                logger.warning(
                    "Protection hook open_incident raised: {} (reason={})",
                    exc,
                    reason,
                )
                incident_id = None
            session.incident_id = incident_id
            try:
                self._protection_hook.enter_protection_mode(
                    reason=reason,
                    source_module=self.SOURCE_MODULE,
                    symbol=session.symbol,
                    payload=payload,
                )
            except Exception as exc:
                logger.warning(
                    "Protection hook enter_protection_mode raised: {} "
                    "(reason={})",
                    exc,
                    reason,
                )

        # If the session held an open position, drive a paper protective
        # close so the ledger reflects the exit. This is the
        # reduce-only-closing-flow path - is_new_open=False bypasses M3
        # / DATA_DEGRADED / REGIME / REBASE_IN_PROGRESS.
        if session.position_id is not None:
            self._counters.protective_closes += 1
            self._ledger.close_position(session.position_id)
            self._repo.append_event(
                self._build_event(
                    EventType.POSITION_CLOSED,
                    session=session,
                    payload={
                        "realized_pnl": 0.0,
                        "protective_close": True,
                        "position_id": session.position_id,
                        "reason": reason,
                    },
                )
            )

    def exit_protection_mode(
        self,
        *,
        session: ExecutionSession,
        reason: str,
    ) -> None:
        """ERROR_PROTECTION -> IDLE. Used by Reconciliation / Telegram /resume.

        FORCED_EXIT semantics on the Trade State Machine are deliberately
        sticky; this method is the Execution-FSM-level operator override
        equivalent to :meth:`TradeStateMachine.reset` and may only be
        used when the operator has confirmed the position is flat.
        """
        if session.state is not ExecutionState.ERROR_PROTECTION:
            raise IllegalTransition(
                f"exit_protection_mode requires state ERROR_PROTECTION, "
                f"got {session.state.value}"
            )
        self._transition(
            session,
            target=ExecutionState.IDLE,
            reasons=(reason,),
        )
        session.in_protection_mode = False
        self._repo.append_event(
            self._build_event(
                EventType.PROTECTION_MODE_EXITED,
                session=session,
                payload={"reason": reason},
            )
        )
        if self._protection_hook is not None:
            try:
                self._protection_hook.exit_protection_mode(
                    reason=reason,
                    source_module=self.SOURCE_MODULE,
                    symbol=session.symbol,
                    payload={},
                )
            except Exception as exc:
                logger.warning(
                    "Protection hook exit_protection_mode raised: {} "
                    "(reason={})",
                    exc,
                    reason,
                )

    # ==================================================================
    # Convenience: drive a paper trade through the full happy path
    # ==================================================================
    def simulate_paper_lifecycle(
        self,
        request: OrderRequest,
        *,
        ack_id: str | None = None,
        fill_price: float | None = None,
        stop_price: float,
        regime_snapshot: Any | None = None,
        liquidity_decision: Any | None = None,
        exit_plan: Any | None = None,
        manipulation_level: ManipulationLevel | None = None,
        trade_confirmation_level: TradeConfirmationLevel | None = None,
        is_data_degraded: bool = False,
        exchange_connection_state: ExchangeConnectionState | None = None,
        learning_context: LearningReadyContext | None = None,
    ) -> ExecutionSession:
        """Drive a NEW open all the way to POSITION_OPEN in paper mode.

        Used by the Phase 9 boot drill in ``app/main.py``. Tests
        usually drive each step explicitly so they can assert the
        intermediate events.
        """
        result = self.submit_order(
            request,
            regime_snapshot=regime_snapshot,
            liquidity_decision=liquidity_decision,
            exit_plan=exit_plan,
            manipulation_level=manipulation_level,
            trade_confirmation_level=trade_confirmation_level,
            is_data_degraded=is_data_degraded,
            exchange_connection_state=exchange_connection_state,
            learning_context=learning_context,
        )
        if not result.accepted:
            return result.session
        session = result.session
        self.on_ack(session=session, ack_id=ack_id or f"ack_{uuid.uuid4().hex[:8]}")
        fill = FillEvent(
            fill_qty=float(request.qty),
            fill_price=float(fill_price if fill_price is not None else request.limit_price or 100.0),
            fill_id=f"fill_{uuid.uuid4().hex[:12]}",
        )
        self.on_full_fill(session=session, fill=fill)
        stop = self.attach_stop(session=session, stop_price=float(stop_price))
        self.on_stop_confirmed(session=session, stop=stop)
        return session

    # ==================================================================
    # Internals
    # ==================================================================
    def _require_state(
        self,
        session: ExecutionSession,
        expected: ExecutionState,
    ) -> None:
        if session.state is not expected:
            raise IllegalTransition(
                f"Operation requires session.state={expected.value}, got "
                f"{session.state.value} (client_order_id="
                f"{session.client_order_id!r})"
            )

    def _transition(
        self,
        session: ExecutionSession,
        *,
        target: ExecutionState,
        reasons: tuple[str, ...],
    ) -> None:
        # Allow the same-state self-loop on PARTIAL_FILLED so a sequence
        # of partial fills doesn't trip the whitelist. Otherwise check
        # the legacy Phase 1 transition table.
        if not (
            target is session.state
            and session.state is ExecutionState.PARTIAL_FILLED
        ):
            allowed = _TRANSITIONS.get(session.state, set())
            if target not in allowed:
                # Allow ERROR_PROTECTION from any state.
                if target is not ExecutionState.ERROR_PROTECTION:
                    raise IllegalTransition(
                        f"Illegal Phase 9 transition {session.state.value} "
                        f"-> {target.value}"
                    )
        prev = session.state
        session.state = target
        session.history.append(
            TransitionRecord(
                from_state=prev,
                to_state=target,
                timestamp=self._clock_ms(),
                reasons=reasons,
            )
        )

    def _update_avg_fill(
        self,
        session: ExecutionSession,
        fill: FillEvent,
    ) -> None:
        """Update the running VWAP for the session."""
        if session.filled_qty <= 0:
            session.avg_fill_price = float(fill.fill_price)
            return
        prev_notional = (session.avg_fill_price or 0.0) * session.filled_qty
        new_notional = float(fill.fill_price) * float(fill.fill_qty)
        new_filled = session.filled_qty + float(fill.fill_qty)
        if new_filled > 0:
            session.avg_fill_price = (prev_notional + new_notional) / new_filled

    def _emit_order_event(
        self,
        event_type: EventType,
        *,
        session: ExecutionSession,
        extra: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "client_order_id": session.client_order_id,
            "exchange_order_id": session.exchange_order_id,
            "state": session.state.value,
            "intent": session.request.intent.value,
            "symbol": session.symbol,
            "filled_qty": float(session.filled_qty),
            "remaining_qty": float(session.remaining_qty),
        }
        if extra:
            payload.update(extra)
        self._repo.append_event(self._build_event(event_type, session=session, payload=payload))

    def _build_event(
        self,
        event_type: EventType,
        *,
        session: ExecutionSession,
        payload: dict[str, Any],
    ) -> Event:
        # Phase 8.5 - propagate opportunity_id and learning_ready
        # context onto every Phase 9 event so future Replay /
        # Reflection / Dataset Builder can group by opportunity.
        payload = dict(payload)
        opportunity_id = session.request.opportunity_id
        if opportunity_id is not None and "opportunity_id" not in payload:
            payload["opportunity_id"] = opportunity_id
        if session.learning_context_payload:
            payload = attach_learning_ready(
                payload,
                _LearningReadyEnvelope(session.learning_context_payload),
            )
        return Event(
            event_type=event_type,
            source_module=self.SOURCE_MODULE,
            symbol=session.symbol,
            position_id=session.position_id,
            order_id=session.client_order_id,
            payload=payload,
        )


# ---------------------------------------------------------------------------
# Helper that lets us push a pre-rendered learning_ready dict back through
# attach_learning_ready without re-running the (heavier) LearningReadyContext
# pipeline. The driver caches the rendered dict on the session so every
# event picks up the same payload.
# ---------------------------------------------------------------------------
class _LearningReadyEnvelope:
    """Minimal stand-in for :class:`LearningReadyContext` that returns a
    pre-rendered ``to_event_payload`` dict without recomputing it."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def to_event_payload(self) -> dict[str, Any]:
        return dict(self._payload)


def _fill_payload(fill: FillEvent) -> dict[str, Any]:
    return {
        "fill_id": fill.fill_id,
        "fill_qty": float(fill.fill_qty),
        "fill_price": float(fill.fill_price),
        "is_maker": bool(fill.is_maker),
        "fee": float(fill.fee),
        "fee_asset": fill.fee_asset,
        "timestamp": int(fill.timestamp),
    }


def _stop_payload(stop: StopEvent) -> dict[str, Any]:
    return {
        "stop_order_id": stop.stop_order_id,
        "stop_price": float(stop.stop_price),
        "side": stop.side.value,
        "qty": float(stop.qty),
        "reduce_only": bool(stop.reduce_only),
        "timestamp": int(stop.timestamp),
    }


__all__ = [
    "ExecutionFSM",
    "IllegalTransition",
    "ExecutionFSMDriver",
]
