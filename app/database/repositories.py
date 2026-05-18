"""Repositories for AMA-RT databases.

Phase 1 only ships `EventRepository`. Spec §12.1 mandates the field
contract; we serialise `payload` as compact JSON.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from app.core.events import Event, EventType


@dataclass
class EventRepository:
    """Append-only event log backed by SQLite.

    Phase 1 supports:
        - append(event)              : write one event
        - append_many(events)        : write several events atomically
        - list(...)                  : query events with simple filters
        - replay(...)                : iterate events in timestamp order

    Phase 2 (Issue #2) will extend this with stronger replay semantics
    (e.g. replay between two timestamps with deterministic ordering).
    """

    conn: sqlite3.Connection

    # -- writes -----------------------------------------------------------
    def append(self, event: Event) -> None:
        self._insert([event])

    def append_many(self, events: Iterable[Event]) -> None:
        self._insert(list(events))

    def _insert(self, events: list[Event]) -> None:
        if not events:
            return
        rows = []
        for ev in events:
            rows.append(
                (
                    ev.event_id,
                    ev.timestamp,
                    ev.event_type.value,
                    ev.source_module,
                    ev.symbol,
                    ev.position_id,
                    ev.order_id,
                    ev.serialise_payload(),
                )
            )
        with self.conn:
            self.conn.executemany(
                """
                INSERT INTO events (
                    event_id, timestamp, event_type, source_module,
                    symbol, position_id, order_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    # -- reads ------------------------------------------------------------
    def list(
        self,
        *,
        event_type: EventType | None = None,
        symbol: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        sql = ["SELECT * FROM events WHERE 1=1"]
        params: list[object] = []
        if event_type is not None:
            sql.append("AND event_type = ?")
            params.append(event_type.value)
        if symbol is not None:
            sql.append("AND symbol = ?")
            params.append(symbol)
        if since_ts is not None:
            sql.append("AND timestamp >= ?")
            params.append(since_ts)
        if until_ts is not None:
            sql.append("AND timestamp <= ?")
            params.append(until_ts)
        sql.append("ORDER BY timestamp ASC, event_id ASC")
        if limit is not None:
            sql.append("LIMIT ?")
            params.append(limit)
        cursor = self.conn.execute(" ".join(sql), params)
        return [self._row_to_event(row) for row in cursor.fetchall()]

    def replay(
        self,
        *,
        since_ts: int | None = None,
        until_ts: int | None = None,
    ) -> Iterator[Event]:
        sql = "SELECT * FROM events WHERE 1=1"
        params: list[object] = []
        if since_ts is not None:
            sql += " AND timestamp >= ?"
            params.append(since_ts)
        if until_ts is not None:
            sql += " AND timestamp <= ?"
            params.append(until_ts)
        sql += " ORDER BY timestamp ASC, event_id ASC"
        cursor = self.conn.execute(sql, params)
        for row in cursor:
            yield self._row_to_event(row)

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> Event:
        return Event(
            event_id=row["event_id"],
            timestamp=row["timestamp"],
            event_type=EventType(row["event_type"]),
            source_module=row["source_module"],
            symbol=row["symbol"],
            position_id=row["position_id"],
            order_id=row["order_id"],
            payload=json.loads(row["payload_json"] or "{}"),
        )
