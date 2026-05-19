"""Phase 9 IncidentRepository (Issue #9, Spec §38).

Writes:

  - rows into ``incidents.db.incidents`` and ``incidents.db.incident_log``
  - ``INCIDENT_OPENED`` / ``INCIDENT_RESOLVED`` events through
    :class:`EventRepository`
  - ``PROTECTION_MODE_ENTERED`` / ``PROTECTION_MODE_EXITED`` events
    through :class:`EventRepository`

The repository implements the duck-typed ``ProtectionHook`` interface
the :class:`ExecutionFSMDriver` and :class:`Reconciler` consume. Tests
can substitute a stand-alone mock without instantiating SQLite.

Phase 9 boundary
----------------

This module:

  - opens NO socket
  - imports NO exchange SDK / HTTP / WebSocket / LLM client
  - reads NO ``os.environ``
  - defines NO ``create_order`` / ``cancel_order`` / ``set_leverage``
    / ``set_margin_mode``
  - is a write surface ONLY for ``incidents.db`` and ``events.db``
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Protocol

from loguru import logger

from app.core.clock import now_ms
from app.core.enums import IncidentLevel
from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.incidents.models import (
    INCIDENT_LIFECYCLE_STATES,
    INCIDENT_STATE_OPENED,
    INCIDENT_STATE_RESOLVED,
    INCIDENT_STATE_UPDATED,
    Incident,
    IncidentRecord,
    make_incident_id,
)


# ---------------------------------------------------------------------------
# Protection hook protocol (consumed by Phase 9 callers)
# ---------------------------------------------------------------------------
class ProtectionHook(Protocol):
    """Duck-typed callback the Execution FSM driver and the Reconciler
    use to open incidents and toggle protection mode.

    :class:`IncidentRepository` is the canonical implementation. Tests
    substitute their own mock to assert the call surface without
    persisting to ``incidents.db``.
    """

    def open_incident(
        self,
        *,
        level: IncidentLevel,
        title: str,
        description: str,
        source_module: str,
        symbol: str | None,
        position_id: str | None,
        payload: dict[str, Any],
    ) -> str:
        ...

    def enter_protection_mode(
        self,
        *,
        reason: str,
        source_module: str,
        symbol: str | None,
        payload: dict[str, Any],
    ) -> None:
        ...

    def exit_protection_mode(
        self,
        *,
        reason: str,
        source_module: str,
        symbol: str | None,
        payload: dict[str, Any],
    ) -> None:
        ...


# ---------------------------------------------------------------------------
# Concrete repository
# ---------------------------------------------------------------------------
@dataclass
class IncidentRepository:
    """Writer for ``incidents.db`` + ``events.db`` incident events.

    Construct with the two SQLite connections from
    :class:`app.database.connection.DatabaseSet`. The repository never
    touches any other database.
    """

    incidents_conn: sqlite3.Connection
    event_repo: EventRepository
    _opened_count: int = 0
    _resolved_count: int = 0
    _protection_entered_count: int = 0
    _protection_exited_count: int = 0
    _last_protection_reason: str | None = None
    _in_protection_mode: bool = False

    # ------------------------------------------------------------------
    # Counters / observability
    # ------------------------------------------------------------------
    @property
    def opened_count(self) -> int:
        return self._opened_count

    @property
    def resolved_count(self) -> int:
        return self._resolved_count

    @property
    def protection_entered_count(self) -> int:
        return self._protection_entered_count

    @property
    def protection_exited_count(self) -> int:
        return self._protection_exited_count

    @property
    def last_protection_reason(self) -> str | None:
        return self._last_protection_reason

    @property
    def in_protection_mode(self) -> bool:
        return self._in_protection_mode

    # ------------------------------------------------------------------
    # Open / update / resolve
    # ------------------------------------------------------------------
    def open_incident(
        self,
        *,
        level: IncidentLevel,
        title: str,
        description: str,
        source_module: str,
        symbol: str | None = None,
        position_id: str | None = None,
        payload: dict[str, Any] | None = None,
        incident_id: str | None = None,
        timestamp: int | None = None,
    ) -> str:
        """Open a new incident.

        Writes one row into ``incidents`` plus one row into
        ``incident_log`` with state=``opened``. Emits one
        ``INCIDENT_OPENED`` event.

        Returns the new ``incident_id``.
        """
        ts = int(timestamp) if timestamp is not None else now_ms()
        incident = Incident(
            incident_id=incident_id or make_incident_id(),
            level=level,
            title=title,
            description=description,
            source_module=source_module,
            symbol=symbol,
            position_id=position_id,
            opened_at=ts,
            payload=dict(payload or {}),
        )
        try:
            with self.incidents_conn:
                self.incidents_conn.execute(
                    """
                    INSERT INTO incidents (
                        incident_id, level, title, description,
                        source_module, symbol, position_id,
                        opened_at, payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        incident.incident_id,
                        incident.level.value,
                        incident.title,
                        incident.description,
                        incident.source_module,
                        incident.symbol,
                        incident.position_id,
                        incident.opened_at,
                        json.dumps(incident.payload, separators=(",", ":"), sort_keys=True),
                    ),
                )
                self.incidents_conn.execute(
                    """
                    INSERT INTO incident_log (
                        incident_id, timestamp, state, note, payload_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        incident.incident_id,
                        incident.opened_at,
                        INCIDENT_STATE_OPENED,
                        f"opened: {title}",
                        json.dumps(incident.payload, separators=(",", ":"), sort_keys=True),
                    ),
                )
        except sqlite3.Error as exc:
            logger.error(
                "IncidentRepository.open_incident failed: {} (level={}, title={})",
                exc,
                level.value,
                title,
            )
            raise
        self._opened_count += 1
        # Emit the INCIDENT_OPENED event so reflection / replay can
        # rebuild the timeline from events.db alone (Spec §12 / §38).
        self.event_repo.append_event(
            Event(
                event_type=EventType.INCIDENT_OPENED,
                source_module=source_module,
                symbol=symbol,
                position_id=position_id,
                payload={
                    "incident_id": incident.incident_id,
                    "level": level.value,
                    "title": title,
                    "description": description,
                    **incident.payload,
                },
                timestamp=ts,
            )
        )
        return incident.incident_id

    def update_incident(
        self,
        *,
        incident_id: str,
        note: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp: int | None = None,
    ) -> None:
        """Append an ``updated`` row to ``incident_log`` for an existing incident."""
        ts = int(timestamp) if timestamp is not None else now_ms()
        try:
            with self.incidents_conn:
                self.incidents_conn.execute(
                    """
                    INSERT INTO incident_log (
                        incident_id, timestamp, state, note, payload_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        incident_id,
                        ts,
                        INCIDENT_STATE_UPDATED,
                        note,
                        json.dumps(payload or {}, separators=(",", ":"), sort_keys=True),
                    ),
                )
        except sqlite3.Error as exc:
            logger.error(
                "IncidentRepository.update_incident failed: {} (incident_id={})",
                exc,
                incident_id,
            )
            raise

    def resolve_incident(
        self,
        *,
        incident_id: str,
        resolution: str,
        source_module: str = "incidents",
        symbol: str | None = None,
        position_id: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp: int | None = None,
    ) -> None:
        """Resolve an open incident.

        Updates the ``incidents`` row's ``resolved_at`` / ``resolution``
        columns, appends a ``resolved`` row to ``incident_log``, and
        emits one ``INCIDENT_RESOLVED`` event.
        """
        ts = int(timestamp) if timestamp is not None else now_ms()
        try:
            with self.incidents_conn:
                self.incidents_conn.execute(
                    """
                    UPDATE incidents
                       SET resolved_at = ?, resolution = ?
                     WHERE incident_id = ?
                    """,
                    (ts, resolution, incident_id),
                )
                self.incidents_conn.execute(
                    """
                    INSERT INTO incident_log (
                        incident_id, timestamp, state, note, payload_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        incident_id,
                        ts,
                        INCIDENT_STATE_RESOLVED,
                        resolution,
                        json.dumps(payload or {}, separators=(",", ":"), sort_keys=True),
                    ),
                )
        except sqlite3.Error as exc:
            logger.error(
                "IncidentRepository.resolve_incident failed: {} (incident_id={})",
                exc,
                incident_id,
            )
            raise
        self._resolved_count += 1
        self.event_repo.append_event(
            Event(
                event_type=EventType.INCIDENT_RESOLVED,
                source_module=source_module,
                symbol=symbol,
                position_id=position_id,
                payload={
                    "incident_id": incident_id,
                    "resolution": resolution,
                    **(payload or {}),
                },
                timestamp=ts,
            )
        )

    # ------------------------------------------------------------------
    # Read-only queries
    # ------------------------------------------------------------------
    def get_incident(self, incident_id: str) -> Incident | None:
        cursor = self.incidents_conn.execute(
            "SELECT * FROM incidents WHERE incident_id = ?",
            (incident_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return Incident(
            incident_id=row["incident_id"],
            level=IncidentLevel(row["level"]),
            title=row["title"],
            description=row["description"] or "",
            source_module=row["source_module"],
            symbol=row["symbol"],
            position_id=row["position_id"],
            opened_at=int(row["opened_at"]),
            resolved_at=(
                int(row["resolved_at"]) if row["resolved_at"] is not None else None
            ),
            resolution=row["resolution"],
            payload=json.loads(row["payload_json"] or "{}"),
        )

    def list_open_incidents(
        self,
        *,
        level: IncidentLevel | None = None,
        symbol: str | None = None,
    ) -> list[Incident]:
        sql = "SELECT * FROM incidents WHERE resolved_at IS NULL"
        params: list[Any] = []
        if level is not None:
            sql += " AND level = ?"
            params.append(level.value)
        if symbol is not None:
            sql += " AND symbol = ?"
            params.append(symbol)
        sql += " ORDER BY opened_at ASC, incident_id ASC"
        cursor = self.incidents_conn.execute(sql, params)
        out: list[Incident] = []
        for row in cursor.fetchall():
            out.append(
                Incident(
                    incident_id=row["incident_id"],
                    level=IncidentLevel(row["level"]),
                    title=row["title"],
                    description=row["description"] or "",
                    source_module=row["source_module"],
                    symbol=row["symbol"],
                    position_id=row["position_id"],
                    opened_at=int(row["opened_at"]),
                    resolved_at=None,
                    resolution=None,
                    payload=json.loads(row["payload_json"] or "{}"),
                )
            )
        return out

    def list_log_for(self, incident_id: str) -> list[IncidentRecord]:
        cursor = self.incidents_conn.execute(
            "SELECT * FROM incident_log WHERE incident_id = ? "
            "ORDER BY timestamp ASC, log_id ASC",
            (incident_id,),
        )
        out: list[IncidentRecord] = []
        for row in cursor.fetchall():
            state_value = row["state"]
            if state_value not in INCIDENT_LIFECYCLE_STATES:  # pragma: no cover
                logger.warning(
                    "incident_log row has unknown state={!r} (incident_id={})",
                    state_value,
                    incident_id,
                )
            out.append(
                IncidentRecord(
                    log_id=int(row["log_id"]),
                    incident_id=row["incident_id"],
                    timestamp=int(row["timestamp"]),
                    state=state_value,
                    note=row["note"],
                    payload=json.loads(row["payload_json"] or "{}"),
                )
            )
        return out

    # ------------------------------------------------------------------
    # Protection mode
    # ------------------------------------------------------------------
    def enter_protection_mode(
        self,
        *,
        reason: str,
        source_module: str = "incidents",
        symbol: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp: int | None = None,
    ) -> None:
        """Emit ``PROTECTION_MODE_ENTERED`` and record the latched flag."""
        ts = int(timestamp) if timestamp is not None else now_ms()
        self._in_protection_mode = True
        self._last_protection_reason = reason
        self._protection_entered_count += 1
        self.event_repo.append_event(
            Event(
                event_type=EventType.PROTECTION_MODE_ENTERED,
                source_module=source_module,
                symbol=symbol,
                payload={
                    "reason": reason,
                    **(payload or {}),
                },
                timestamp=ts,
            )
        )

    def exit_protection_mode(
        self,
        *,
        reason: str,
        source_module: str = "incidents",
        symbol: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp: int | None = None,
    ) -> None:
        """Emit ``PROTECTION_MODE_EXITED`` and clear the latched flag.

        Phase 9 hard rule: Telegram /resume + the Reconciliation loop
        are the only two callers that should drive this; the operator
        must have confirmed every position / stop is in a known state
        before the call lands.
        """
        ts = int(timestamp) if timestamp is not None else now_ms()
        self._in_protection_mode = False
        self._last_protection_reason = None
        self._protection_exited_count += 1
        self.event_repo.append_event(
            Event(
                event_type=EventType.PROTECTION_MODE_EXITED,
                source_module=source_module,
                symbol=symbol,
                payload={
                    "reason": reason,
                    **(payload or {}),
                },
                timestamp=ts,
            )
        )


__all__ = [
    "IncidentRepository",
    "ProtectionHook",
]
