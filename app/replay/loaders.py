"""Phase 10A Replay Engine - event-stream loaders (Issue #10 Part 1).

Pure read-only helpers around :class:`EventRepository`. The Replay
Engine consumes events.db through the same public read API every other
phase already uses; nothing here adds, mutates, or reorders rows.

Phase 10A boundary (per Issue #10 Part 10A):

  - opens NO socket
  - imports NO exchange SDK / HTTP / WebSocket / LLM client / Telegram
    bot library
  - reads NO ``os.environ``
  - defines NO ``create_order`` / ``cancel_order`` / ``set_leverage``
    / ``set_margin_mode``
  - touches NO trading state, NO capital state, NO risk state
  - is a write surface for **NOTHING** - replay is read-only

Implementation notes:

  - The Phase 8.5 learning-ready payload lives at ``payload['learning_ready']``
    on the 11 event types listed in
    :data:`app.learning.LEARNING_READY_EVENT_TYPES`.
  - The Phase 9 paper trade lifecycle keys every order/stop/position
    event to ``Event.order_id == client_order_id``.
  - The Phase 9 reconciliation lifecycle uses ``RECONCILIATION_STARTED``
    / ``RECONCILIATION_MISMATCH`` / ``RECONCILIATION_RESOLVED`` paired
    by ``payload['started_at']``.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.learning.context import LEARNING_READY_EVENT_TYPES, LEARNING_READY_KEY


# ---------------------------------------------------------------------------
# Generic loaders
# ---------------------------------------------------------------------------
def load_all_events(
    event_repo: EventRepository,
    *,
    since_ts: int | None = None,
    until_ts: int | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[Event]:
    """Return every event in the (since_ts, until_ts) window."""
    return event_repo.list_events(
        since_ts=since_ts,
        until_ts=until_ts,
        limit=limit,
        offset=offset,
    )


def stream_events(
    event_repo: EventRepository,
    *,
    event_types: Iterable[EventType] | None = None,
    symbol: str | None = None,
    source_module: str | None = None,
    since_ts: int | None = None,
    until_ts: int | None = None,
) -> Iterator[Event]:
    """Lazy iterator over events ordered by ``(timestamp, event_id)``.

    Mirrors :meth:`EventRepository.replay_events` but accepts an iterable
    ``event_types`` for the multi-type filter every Phase 10A replay
    needs.
    """
    return event_repo.replay_events(
        event_types=event_types,
        symbol=symbol,
        source_module=source_module,
        since_ts=since_ts,
        until_ts=until_ts,
    )


def load_events_for_order(
    event_repo: EventRepository,
    *,
    client_order_id: str,
) -> list[Event]:
    """Every event Phase 9 keyed to a paper order (Event.order_id)."""
    return event_repo.list_events(order_id=client_order_id)


def load_events_for_position(
    event_repo: EventRepository,
    *,
    position_id: str,
) -> list[Event]:
    return event_repo.list_events(position_id=position_id)


def load_events_for_symbol(
    event_repo: EventRepository,
    *,
    symbol: str,
    event_types: Iterable[EventType] | None = None,
    since_ts: int | None = None,
    until_ts: int | None = None,
) -> list[Event]:
    return event_repo.list_events(
        symbol=symbol,
        event_types=event_types,
        since_ts=since_ts,
        until_ts=until_ts,
    )


def load_events_for_opportunity(
    event_repo: EventRepository,
    *,
    opportunity_id: str,
    event_types: Iterable[EventType] | None = None,
) -> list[Event]:
    """Filter the event stream by Phase 8.5 ``opportunity_id`` payload key.

    ``opportunity_id`` is not a top-level column on events.db, so we
    list candidates by event-type and filter in Python. Phase 8.5
    attaches ``opportunity_id`` to ORDER_*, STOP_*, POSITION_*,
    RISK_APPROVED, RISK_REJECTED, STATE_TRANSITION, and the 11
    learning-ready event types.
    """
    candidates = event_repo.list_events(event_types=event_types)
    return [
        ev
        for ev in candidates
        if _opportunity_id_for(ev) == opportunity_id
    ]


# ---------------------------------------------------------------------------
# Lifecycle loaders
# ---------------------------------------------------------------------------
PAPER_LIFECYCLE_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.ORDER_SENT,
    EventType.ORDER_ACK,
    EventType.ORDER_PARTIAL_FILLED,
    EventType.ORDER_FILLED,
    EventType.ORDER_CANCELLED,
    EventType.STOP_SENT,
    EventType.STOP_CONFIRMED,
    EventType.STOP_FAILED,
    EventType.POSITION_OPENED,
    EventType.POSITION_UPDATED,
    EventType.POSITION_CLOSED,
    EventType.EXIT_TRIGGERED,
)

CAPITAL_FLOW_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.CAPITAL_DEPOSIT,
    EventType.CAPITAL_WITHDRAWAL,
    EventType.PROFIT_HARVEST,
    EventType.CAPITAL_REBASE,
    EventType.RISK_BUDGET_RECALCULATED,
)

INCIDENT_LIFECYCLE_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.INCIDENT_OPENED,
    EventType.INCIDENT_RESOLVED,
    EventType.PROTECTION_MODE_ENTERED,
    EventType.PROTECTION_MODE_EXITED,
)

RECONCILIATION_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.RECONCILIATION_STARTED,
    EventType.RECONCILIATION_MISMATCH,
    EventType.RECONCILIATION_RESOLVED,
)

RISK_DECISION_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.RISK_APPROVED,
    EventType.RISK_REJECTED,
)


def load_capital_flow_events(
    event_repo: EventRepository,
    *,
    since_ts: int | None = None,
    until_ts: int | None = None,
) -> list[Event]:
    return event_repo.list_events(
        event_types=CAPITAL_FLOW_EVENT_TYPES,
        since_ts=since_ts,
        until_ts=until_ts,
    )


def load_risk_decision_events(
    event_repo: EventRepository,
    *,
    only_rejected: bool = False,
    only_approved: bool = False,
    symbol: str | None = None,
    since_ts: int | None = None,
    until_ts: int | None = None,
) -> list[Event]:
    if only_rejected and only_approved:
        raise ValueError(
            "load_risk_decision_events: only_rejected and only_approved "
            "are mutually exclusive."
        )
    if only_rejected:
        types: tuple[EventType, ...] = (EventType.RISK_REJECTED,)
    elif only_approved:
        types = (EventType.RISK_APPROVED,)
    else:
        types = RISK_DECISION_EVENT_TYPES
    return event_repo.list_events(
        event_types=types,
        symbol=symbol,
        since_ts=since_ts,
        until_ts=until_ts,
    )


def load_incident_lifecycle_events(
    event_repo: EventRepository,
    *,
    incident_id: str | None = None,
    since_ts: int | None = None,
    until_ts: int | None = None,
) -> list[Event]:
    """Return every incident-lifecycle event, optionally scoped to one ID.

    Notes on the ``incident_id`` filter:
      - ``INCIDENT_OPENED`` / ``INCIDENT_RESOLVED`` events carry
        ``incident_id`` in their payload and are matched directly.
      - ``PROTECTION_MODE_ENTERED`` / ``PROTECTION_MODE_EXITED`` events
        do NOT carry ``incident_id`` (they are system-level), so they
        are included when their timestamp falls inside the incident's
        opened-to-resolved window. If the incident is still open the
        window extends to ``until_ts`` (or to the latest event in the
        stream when ``until_ts`` is None).
    """
    candidates = event_repo.list_events(
        event_types=INCIDENT_LIFECYCLE_EVENT_TYPES,
        since_ts=since_ts,
        until_ts=until_ts,
    )
    if incident_id is None:
        return candidates
    # Bound the protection window from the matching INCIDENT_OPENED /
    # INCIDENT_RESOLVED events.
    open_ts: int | None = None
    resolved_ts: int | None = None
    for ev in candidates:
        if ev.payload.get("incident_id") != incident_id:
            continue
        if ev.event_type is EventType.INCIDENT_OPENED:
            open_ts = int(ev.timestamp)
        elif ev.event_type is EventType.INCIDENT_RESOLVED:
            resolved_ts = int(ev.timestamp)
    out: list[Event] = []
    for ev in candidates:
        if ev.event_type in {
            EventType.INCIDENT_OPENED,
            EventType.INCIDENT_RESOLVED,
        }:
            if ev.payload.get("incident_id") == incident_id:
                out.append(ev)
            continue
        # PROTECTION_MODE_*: include if inside the incident window.
        ts = int(ev.timestamp)
        if open_ts is not None and ts >= open_ts and (
            resolved_ts is None or ts <= resolved_ts
        ):
            out.append(ev)
    return out


def load_state_transition_events(
    event_repo: EventRepository,
    *,
    symbol: str | None = None,
    since_ts: int | None = None,
    until_ts: int | None = None,
) -> list[Event]:
    return event_repo.list_events(
        event_type=EventType.STATE_TRANSITION,
        symbol=symbol,
        since_ts=since_ts,
        until_ts=until_ts,
    )


def load_telegram_command_events(
    event_repo: EventRepository,
    *,
    name: str | None = None,
    user_id: str | None = None,
    since_ts: int | None = None,
    until_ts: int | None = None,
) -> list[Event]:
    """Telegram command events filtered by command-name / user.

    The Phase 1 :class:`TelegramCommandCenter` writes
    ``TELEGRAM_COMMAND_RECEIVED`` with ``payload={'name', 'user_id',
    'args'}``. Phase 10D will extend; this loader works against either
    shape.
    """
    candidates = event_repo.list_events(
        event_type=EventType.TELEGRAM_COMMAND_RECEIVED,
        since_ts=since_ts,
        until_ts=until_ts,
    )
    out: list[Event] = []
    for ev in candidates:
        payload = ev.payload or {}
        if name is not None and payload.get("name") != name:
            continue
        if user_id is not None and str(payload.get("user_id")) != str(user_id):
            continue
        out.append(ev)
    return out


def load_reconciliation_events(
    event_repo: EventRepository,
    *,
    since_ts: int | None = None,
    until_ts: int | None = None,
) -> list[Event]:
    return event_repo.list_events(
        event_types=RECONCILIATION_EVENT_TYPES,
        since_ts=since_ts,
        until_ts=until_ts,
    )


# ---------------------------------------------------------------------------
# Phase 8.5 learning-ready payload helpers
# ---------------------------------------------------------------------------
def has_learning_ready(event: Event) -> bool:
    """True if the event payload carries a Phase 8.5 ``learning_ready`` block."""
    if event.event_type not in LEARNING_READY_EVENT_TYPES:
        return False
    return isinstance(event.payload.get(LEARNING_READY_KEY), dict)


def extract_learning_ready(event: Event) -> dict[str, Any] | None:
    """Return the ``learning_ready`` block from an event payload, or None.

    Phase 10A treats the block as opaque - we read it back exactly as
    Phase 8.5 wrote it. The dict is shallow-copied so callers cannot
    mutate the source event's payload.
    """
    if not has_learning_ready(event):
        return None
    block = event.payload.get(LEARNING_READY_KEY)
    if not isinstance(block, dict):
        return None
    return dict(block)


def _opportunity_id_for(event: Event) -> str | None:
    """Best-effort extraction of ``opportunity_id`` from an event.

    Phase 8.5 attaches ``opportunity_id`` either at the payload top
    level (Phase 9 ORDER_* / POSITION_* events) or nested inside the
    ``learning_ready.opportunity`` block (Phase 8.5 risk / scanner /
    confirmation events).
    """
    payload = event.payload or {}
    direct = payload.get("opportunity_id")
    if isinstance(direct, str):
        return direct
    block = payload.get(LEARNING_READY_KEY)
    if isinstance(block, dict):
        opp = block.get("opportunity")
        if isinstance(opp, dict):
            opp_id = opp.get("opportunity_id")
            if isinstance(opp_id, str):
                return opp_id
    return None


def opportunity_id_for(event: Event) -> str | None:
    """Public wrapper of :func:`_opportunity_id_for`."""
    return _opportunity_id_for(event)


# ---------------------------------------------------------------------------
# Reconciliation pairing helpers
# ---------------------------------------------------------------------------
def pair_reconciliation_passes(
    events: Iterable[Event],
) -> list[dict[str, Any]]:
    """Group ``RECONCILIATION_*`` events into one dict per pass.

    Phase 9 emits a triplet per pass:
      ``RECONCILIATION_STARTED`` -> N x ``RECONCILIATION_MISMATCH``
      -> ``RECONCILIATION_RESOLVED``

    The triplets are paired by ``payload['started_at']``: the
    ``RECONCILIATION_STARTED`` event contributes its own timestamp; the
    ``RECONCILIATION_RESOLVED`` event carries the same ``started_at`` in
    its payload so we can match. ``RECONCILIATION_MISMATCH`` events do
    NOT carry ``started_at`` but always sit between the open / close,
    so we attach them in event-stream order.

    Returns a list of dicts, one per pass:
        {
          "started_at": int,
          "finished_at": int | None,
          "started": Event,
          "resolved": Event | None,
          "mismatches": tuple[Event, ...],
        }
    """
    passes: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for ev in events:
        if ev.event_type is EventType.RECONCILIATION_STARTED:
            if current is not None:
                # Nest closed (orphan) - keep it.
                passes.append(current)
            current = {
                "started_at": int(
                    ev.payload.get("started_at", ev.timestamp)
                ),
                "finished_at": None,
                "started": ev,
                "resolved": None,
                "mismatches": (),
            }
        elif ev.event_type is EventType.RECONCILIATION_MISMATCH:
            if current is None:
                # Orphan mismatch (shouldn't happen but accept defensively).
                continue
            current["mismatches"] = current["mismatches"] + (ev,)
        elif ev.event_type is EventType.RECONCILIATION_RESOLVED:
            if current is None:
                continue
            current["finished_at"] = int(
                ev.payload.get("finished_at", ev.timestamp)
            )
            current["resolved"] = ev
            passes.append(current)
            current = None
    if current is not None:
        passes.append(current)
    return passes


__all__ = [
    "PAPER_LIFECYCLE_EVENT_TYPES",
    "CAPITAL_FLOW_EVENT_TYPES",
    "INCIDENT_LIFECYCLE_EVENT_TYPES",
    "RECONCILIATION_EVENT_TYPES",
    "RISK_DECISION_EVENT_TYPES",
    "load_all_events",
    "stream_events",
    "load_events_for_order",
    "load_events_for_position",
    "load_events_for_symbol",
    "load_events_for_opportunity",
    "load_capital_flow_events",
    "load_risk_decision_events",
    "load_incident_lifecycle_events",
    "load_state_transition_events",
    "load_telegram_command_events",
    "load_reconciliation_events",
    "has_learning_ready",
    "extract_learning_ready",
    "opportunity_id_for",
    "pair_reconciliation_passes",
]
