"""Phase 9 paper-mode lifecycle reconstruction helper (Issue #9 fix-up).

A **narrow** read-only summariser that walks events.db for one paper
trade and rebuilds a high-level lifecycle summary. The helper exists
only to prove the EventRepository carries enough information to
rebuild a paper trade lifecycle from the event stream alone.

This is **NOT** a full Replay Engine. The Replay Engine, with its
diff reports / Reflection / Dataset Builder, is Issue #10's
responsibility. This module deliberately does the minimum:

  - Read events filtered by ``order_id`` (Phase 9 sets this to the
    ``client_order_id``) or by ``opportunity_id`` (scanned from the
    event payload).
  - Walk the events in their natural ``(timestamp, event_id)`` order.
  - Produce a single :class:`PaperLifecycleSummary` describing the
    most-progressed lifecycle state and a few count fields.

Phase 9 boundary
----------------

This module:

  - opens NO socket
  - imports NO exchange SDK / HTTP / WebSocket / LLM client
  - reads NO ``os.environ``
  - calls NO Telegram outbound surface
  - defines NO ``create_order`` / ``cancel_order`` / ``set_leverage``
    / ``set_margin_mode``
  - WRITES nothing - it is purely a read helper over events.db.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.events import Event, EventType
from app.database.repositories import EventRepository


# ---------------------------------------------------------------------------
# Lifecycle event vocabulary
# ---------------------------------------------------------------------------
# The paper-mode order lifecycle event types Phase 9 emits, in the
# canonical happy-path order. ``ORDER_PARTIAL_FILLED`` may repeat;
# every other event appears at most once per session.
LIFECYCLE_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.ORDER_SENT,
    EventType.ORDER_ACK,
    EventType.ORDER_PARTIAL_FILLED,
    EventType.ORDER_FILLED,
    EventType.STOP_SENT,
    EventType.STOP_CONFIRMED,
    EventType.POSITION_OPENED,
    EventType.EXIT_TRIGGERED,
    EventType.POSITION_CLOSED,
)

# Optional event types that may appear off the happy path. Their
# presence is reported in the summary but does not block
# reconstruction.
OPTIONAL_LIFECYCLE_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.STOP_FAILED,
    EventType.PROTECTION_MODE_ENTERED,
    EventType.PROTECTION_MODE_EXITED,
    EventType.INCIDENT_OPENED,
    EventType.INCIDENT_RESOLVED,
    EventType.RECONCILIATION_MISMATCH,
)

# Final-status vocabulary returned in the summary. The value reflects
# the most-progressed state observed in the event stream.
FINAL_STATUS_CLOSED: str = "closed"
FINAL_STATUS_OPEN: str = "open"
FINAL_STATUS_PROTECTED: str = "protected"
FINAL_STATUS_IN_PROGRESS: str = "in_progress"
FINAL_STATUS_REJECTED: str = "rejected"


# ---------------------------------------------------------------------------
# Summary value object
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PaperLifecycleSummary:
    """One paper-trade lifecycle as reconstructed from events.db.

    The fields mirror the Issue #9 fix-up acceptance criterion: every
    field can be filled in from the events alone, without consulting
    the live :class:`PaperLedger` or the :class:`ExecutionFSMDriver`.
    """

    client_order_id: str | None
    opportunity_id: str | None
    symbol: str | None
    side: str | None
    qty: float | None
    entry_state: str | None
    exit_state: str | None
    stop_confirmed: bool
    partial_fills: int
    final_status: str
    learning_ready_present: bool
    event_chain: tuple[str, ...] = field(default_factory=tuple)
    incident_opened: bool = False
    reconciliation_mismatch: bool = False
    protective_close: bool = False

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe payload for monitoring / tests / debugging."""
        return {
            "client_order_id": self.client_order_id,
            "opportunity_id": self.opportunity_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": (float(self.qty) if self.qty is not None else None),
            "entry_state": self.entry_state,
            "exit_state": self.exit_state,
            "stop_confirmed": bool(self.stop_confirmed),
            "partial_fills": int(self.partial_fills),
            "final_status": self.final_status,
            "learning_ready_present": bool(self.learning_ready_present),
            "event_chain": list(self.event_chain),
            "incident_opened": bool(self.incident_opened),
            "reconciliation_mismatch": bool(self.reconciliation_mismatch),
            "protective_close": bool(self.protective_close),
        }


# ---------------------------------------------------------------------------
# Reconstruction
# ---------------------------------------------------------------------------
def _events_for_order(
    *,
    event_repo: EventRepository,
    client_order_id: str,
) -> list[Event]:
    """Return every event keyed to a paper order_id.

    Phase 9 sets :attr:`Event.order_id` to the ``client_order_id`` for
    every order/stop/position event the FSM driver emits. We rely on
    that direct column rather than scanning payloads.
    """
    return event_repo.list_events(order_id=client_order_id)


def _events_for_opportunity(
    *,
    event_repo: EventRepository,
    opportunity_id: str,
) -> list[Event]:
    """Return every event whose payload carries this ``opportunity_id``.

    The ``opportunity_id`` is not a top-level column on events.db, so
    we list every event in the event types the FSM driver emits and
    filter in Python. This is acceptable for the Phase 9 fix-up
    helper because it is a debugging surface, not a hot path.
    """
    relevant_types = list(LIFECYCLE_EVENT_TYPES) + list(OPTIONAL_LIFECYCLE_EVENT_TYPES)
    candidates = event_repo.list_events(event_types=relevant_types)
    return [
        ev
        for ev in candidates
        if ev.payload.get("opportunity_id") == opportunity_id
    ]


def reconstruct_paper_lifecycle(
    *,
    event_repo: EventRepository,
    client_order_id: str | None = None,
    opportunity_id: str | None = None,
) -> PaperLifecycleSummary:
    """Walk events.db and rebuild the lifecycle summary for one paper trade.

    Exactly one of ``client_order_id`` / ``opportunity_id`` must be
    supplied. The helper reads the event stream, follows the
    canonical Phase 9 lifecycle, and reports the most-progressed
    state observed.

    Note
    ----

    This helper is **NOT** the full Replay Engine - that is the
    responsibility of Issue #10. We pin only the read-side contract:

      - The lifecycle event types Phase 9 writes (``ORDER_SENT`` ->
        ``POSITION_CLOSED``) are reachable through
        :class:`EventRepository`.
      - The Phase 8.5 learning-ready data contract is preserved: the
        ``opportunity_id`` and ``learning_ready`` payload survive on
        every Phase 9 event.

    Raises
    ------

    ValueError
        If neither or both lookup keys are supplied, or if no events
        match the supplied key.
    """
    if (client_order_id is None) == (opportunity_id is None):
        raise ValueError(
            "reconstruct_paper_lifecycle requires exactly one of "
            "client_order_id / opportunity_id"
        )

    if client_order_id is not None:
        events = _events_for_order(
            event_repo=event_repo, client_order_id=client_order_id
        )
    else:
        assert opportunity_id is not None  # narrowing for mypy
        events = _events_for_opportunity(
            event_repo=event_repo, opportunity_id=opportunity_id
        )

    if not events:
        raise ValueError(
            f"reconstruct_paper_lifecycle: no events found for "
            f"client_order_id={client_order_id!r} / "
            f"opportunity_id={opportunity_id!r}"
        )

    # Walk the events in time order (EventRepository already returns
    # them sorted). Capture the most-progressed lifecycle marker plus
    # the auxiliary counts.
    resolved_client_order_id: str | None = client_order_id
    resolved_opportunity_id: str | None = opportunity_id
    symbol: str | None = None
    side: str | None = None
    qty: float | None = None
    entry_state: str | None = None
    exit_state: str | None = None
    stop_confirmed: bool = False
    partial_fills: int = 0
    learning_ready_present: bool = False
    incident_opened: bool = False
    reconciliation_mismatch: bool = False
    protective_close: bool = False
    saw_protection_entered: bool = False
    saw_protection_exited: bool = False
    event_chain: list[str] = []

    for ev in events:
        event_chain.append(ev.event_type.value)
        payload = ev.payload or {}

        # Stable identifiers / descriptors gleaned from any event.
        if resolved_client_order_id is None:
            resolved_client_order_id = payload.get("client_order_id") or ev.order_id
        if resolved_opportunity_id is None:
            resolved_opportunity_id = payload.get("opportunity_id")
        if symbol is None:
            symbol = ev.symbol or payload.get("symbol")
        # The original ORDER_SENT carries the request descriptor.
        if ev.event_type is EventType.ORDER_SENT:
            request_payload = payload.get("request") or {}
            if side is None:
                side = request_payload.get("side") or payload.get("side")
            if qty is None:
                qty_value = request_payload.get("qty")
                if qty_value is not None:
                    qty = float(qty_value)
        if "learning_ready" in payload:
            learning_ready_present = True

        if ev.event_type is EventType.POSITION_CLOSED and payload.get(
            "protective_close"
        ) is True:
            protective_close = True

        # Track per-event flags that don't participate in the most-
        # progressed marker logic (which is computed below using
        # progression-rank tables, not first-seen order).
        if ev.event_type is EventType.STOP_CONFIRMED:
            stop_confirmed = True
        if ev.event_type is EventType.ORDER_PARTIAL_FILLED:
            partial_fills += 1
        if ev.event_type is EventType.INCIDENT_OPENED:
            incident_opened = True
        if ev.event_type is EventType.RECONCILIATION_MISMATCH:
            reconciliation_mismatch = True
        if ev.event_type is EventType.PROTECTION_MODE_ENTERED:
            saw_protection_entered = True
        if ev.event_type is EventType.PROTECTION_MODE_EXITED:
            saw_protection_exited = True

    # Most-progressed entry / exit markers, computed from the SET of
    # observed event types using a progression-rank table. We do not
    # rely on event-stream ordering because EventRepository sorts by
    # ``(timestamp, event_id)`` and Phase 9 events emitted within the
    # same millisecond tie on the timestamp, so a random-UUID
    # event_id would otherwise drive the answer non-deterministically.
    observed_types: set[str] = set(event_chain)
    entry_progression: list[EventType] = [
        EventType.ORDER_SENT,
        EventType.ORDER_ACK,
        EventType.ORDER_PARTIAL_FILLED,
        EventType.ORDER_FILLED,
        EventType.STOP_SENT,
        EventType.STOP_CONFIRMED,
        EventType.POSITION_OPENED,
    ]
    for marker in entry_progression:
        if marker.value in observed_types:
            entry_state = marker.value
    exit_progression: list[EventType] = [
        EventType.EXIT_TRIGGERED,
        EventType.POSITION_CLOSED,
    ]
    for marker in exit_progression:
        if marker.value in observed_types:
            exit_state = marker.value

    # Final-status priority: closed > open > protected > in_progress.
    # A protective close still counts as ``closed`` because the
    # position is no longer on the books; the ``protective_close``
    # flag captures the nuance separately.
    if exit_state == EventType.POSITION_CLOSED.value:
        final_status = FINAL_STATUS_CLOSED
    elif (
        saw_protection_entered
        and not saw_protection_exited
        and exit_state is None
    ):
        final_status = FINAL_STATUS_PROTECTED
    elif entry_state == EventType.POSITION_OPENED.value and exit_state is None:
        final_status = FINAL_STATUS_OPEN
    elif entry_state is None and exit_state is None:
        # No lifecycle event landed at all (e.g. risk-rejected order
        # whose ORDER_SENT was never written). Should be unreachable
        # because the event filter found something, but defensive.
        final_status = FINAL_STATUS_REJECTED
    else:
        final_status = FINAL_STATUS_IN_PROGRESS

    return PaperLifecycleSummary(
        client_order_id=resolved_client_order_id,
        opportunity_id=resolved_opportunity_id,
        symbol=symbol,
        side=side,
        qty=qty,
        entry_state=entry_state,
        exit_state=exit_state,
        stop_confirmed=stop_confirmed,
        partial_fills=partial_fills,
        final_status=final_status,
        learning_ready_present=learning_ready_present,
        event_chain=tuple(event_chain),
        incident_opened=incident_opened,
        reconciliation_mismatch=reconciliation_mismatch,
        protective_close=protective_close,
    )


__all__ = [
    "LIFECYCLE_EVENT_TYPES",
    "OPTIONAL_LIFECYCLE_EVENT_TYPES",
    "FINAL_STATUS_CLOSED",
    "FINAL_STATUS_OPEN",
    "FINAL_STATUS_PROTECTED",
    "FINAL_STATUS_IN_PROGRESS",
    "FINAL_STATUS_REJECTED",
    "PaperLifecycleSummary",
    "reconstruct_paper_lifecycle",
]
