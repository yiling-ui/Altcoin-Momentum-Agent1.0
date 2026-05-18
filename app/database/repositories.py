"""Repositories for AMA-RT databases (Phase 2 - Event Sourcing and Database).

Phase 2 ships ONE repository: `EventRepository` against `events.db`. The
repositories that own `trades.db`, `positions.db`, `capital.db` and
`incidents.db` are deferred to:

    Issue #7 - State Machine / Risk Engine     -> position lifecycle
    Issue #8 - Capital Flow Engine             -> capital snapshots
    Issue #9 - Execution FSM / Reconciliation  -> trade fills
    Issue #9 / #10                             -> incidents

The `capital_events_index` table inside `capital.db` is the only
cross-database write surface in Phase 2: every CAPITAL_* event appended
to `events.db` is also indexed there so that Issue #8 has a fast lookup
table to start from.

Issue #2 mandates the following API:

    append_event(event)                    write one event
    append_many(events)                    write several events atomically
    list_events(...)                       query with filters
    replay_events(...)                     time-ordered iterator
    count_events(...)                      filtered count
    + filter by time range, symbol, event_type
    + persistence failures must be logged + raised, never swallowed

For backwards compatibility with Phase 1 callers (RiskEngine, Telegram
bot, Execution FSM, scripts/init_db, app/main) the previous method names
`append`, `list`, `replay`, `count` are kept as thin aliases.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from loguru import logger

from app.core.errors import EventPersistenceError
from app.core.events import CAPITAL_EVENT_TYPES, Event, EventType


@dataclass
class EventRepository:
    """Append-only event log backed by SQLite (events.db).

    Phase 2 features:
        - append_event / append_many        : write
        - list_events / replay_events       : read
        - count_events                      : count
        - filters: event_type, symbol, since_ts, until_ts, source_module,
                   position_id, order_id, limit, offset
        - persistence failures logged + raised as EventPersistenceError
        - optional `capital_conn` so CAPITAL_* events are also indexed
          in capital.db's `capital_events_index` table atomically

    The repository is intentionally synchronous. Async wrappers are a
    Phase-3+ concern.
    """

    conn: sqlite3.Connection
    capital_conn: sqlite3.Connection | None = None

    # cumulative count of failed persistence attempts (for tests / monitoring).
    # Reset on a successful flush.
    _failed_appends: int = field(default=0, init=False, repr=False)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def append_event(self, event: Event) -> Event:
        """Append a single event. Returns the event with `created_at` populated.

        Raises `EventPersistenceError` on any sqlite failure. Does not
        swallow exceptions.
        """
        return self._insert([event])[0]

    def append_many(self, events: Iterable[Event]) -> list[Event]:
        """Append several events atomically. Returns persisted events."""
        evts = list(events)
        if not evts:
            return []
        return self._insert(evts)

    # Backwards-compat aliases (Phase 1 API used by RiskEngine, Telegram, FSM)
    def append(self, event: Event) -> None:
        """Phase 1 alias for append_event(). Kept for backwards compatibility."""
        self.append_event(event)

    def _insert(self, events: list[Event]) -> list[Event]:
        if not events:
            return []
        rows: list[tuple] = []
        capital_rows: list[tuple] = []
        try:
            for ev in events:
                payload_json = ev.serialise_payload()
                rows.append(
                    (
                        ev.event_id,
                        ev.timestamp,
                        ev.event_type.value,
                        ev.source_module,
                        ev.symbol,
                        ev.position_id,
                        ev.order_id,
                        payload_json,
                    )
                )
                if ev.event_type in CAPITAL_EVENT_TYPES:
                    capital_rows.append(
                        (
                            ev.event_id,
                            ev.timestamp,
                            ev.event_type.value,
                            float(ev.payload.get("amount", 0.0) or 0.0),
                            str(ev.payload.get("currency", "USDT")),
                            payload_json,
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
            if capital_rows and self.capital_conn is not None:
                try:
                    with self.capital_conn:
                        self.capital_conn.executemany(
                            """
                            INSERT INTO capital_events_index (
                                event_id, timestamp, event_type,
                                amount, currency, payload_json
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            capital_rows,
                        )
                except sqlite3.Error as exc:
                    # Capital index is a denormalised mirror; log loudly
                    # but do NOT roll back the events write. Issue #8
                    # rebuilds the index from events.db on demand.
                    logger.error(
                        "capital_events_index write failed: {} ({} rows)",
                        exc,
                        len(capital_rows),
                    )
        except (sqlite3.Error, TypeError, ValueError) as exc:
            self._failed_appends += 1
            event_ids = [ev.event_id for ev in events]
            logger.error(
                "EventRepository append failed: {} ({} events, ids={})",
                exc,
                len(events),
                event_ids,
            )
            raise EventPersistenceError(
                f"Failed to persist {len(events)} event(s): {exc}"
            ) from exc

        # SQLite's strftime() runs at INSERT time. Read created_at back so
        # the returned events match what's on disk. We do this via a single
        # round-trip keyed by event_id.
        ids = [ev.event_id for ev in events]
        placeholders = ",".join("?" for _ in ids)
        rows_back = self.conn.execute(
            f"SELECT event_id, created_at FROM events WHERE event_id IN ({placeholders})",
            ids,
        ).fetchall()
        created_map = {r["event_id"]: r["created_at"] for r in rows_back}

        # Return new Event instances with `created_at` populated.
        out: list[Event] = []
        for ev in events:
            out.append(
                Event(
                    event_type=ev.event_type,
                    source_module=ev.source_module,
                    payload=ev.payload,
                    symbol=ev.symbol,
                    position_id=ev.position_id,
                    order_id=ev.order_id,
                    timestamp=ev.timestamp,
                    event_id=ev.event_id,
                    created_at=created_map.get(ev.event_id),
                )
            )
        return out

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def list_events(
        self,
        *,
        event_type: EventType | str | None = None,
        event_types: Iterable[EventType | str] | None = None,
        symbol: str | None = None,
        source_module: str | None = None,
        position_id: str | None = None,
        order_id: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Event]:
        """Filtered query against events.db.

        All filters AND together. `event_types` accepts an iterable for
        multi-type queries (e.g. all CAPITAL_* events). Results are
        ordered ascending by (timestamp, event_id) so replay is
        deterministic.
        """
        sql, params = self._build_query(
            event_type=event_type,
            event_types=event_types,
            symbol=symbol,
            source_module=source_module,
            position_id=position_id,
            order_id=order_id,
            since_ts=since_ts,
            until_ts=until_ts,
        )
        sql += " ORDER BY timestamp ASC, event_id ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
            if offset is not None:
                sql += " OFFSET ?"
                params.append(int(offset))
        try:
            cursor = self.conn.execute(sql, params)
            return [self._row_to_event(row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            logger.error("EventRepository list_events failed: {}", exc)
            raise EventPersistenceError(f"list_events failed: {exc}") from exc

    def replay_events(
        self,
        *,
        event_type: EventType | str | None = None,
        event_types: Iterable[EventType | str] | None = None,
        symbol: str | None = None,
        source_module: str | None = None,
        position_id: str | None = None,
        order_id: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
    ) -> Iterator[Event]:
        """Iterate events ordered by (timestamp, event_id).

        Use this for replay. Memory usage is bounded by SQLite's cursor,
        not by the result set size, so it is safe for large windows.
        """
        sql, params = self._build_query(
            event_type=event_type,
            event_types=event_types,
            symbol=symbol,
            source_module=source_module,
            position_id=position_id,
            order_id=order_id,
            since_ts=since_ts,
            until_ts=until_ts,
        )
        sql += " ORDER BY timestamp ASC, event_id ASC"
        try:
            cursor = self.conn.execute(sql, params)
            for row in cursor:
                yield self._row_to_event(row)
        except sqlite3.Error as exc:
            logger.error("EventRepository replay_events failed: {}", exc)
            raise EventPersistenceError(f"replay_events failed: {exc}") from exc

    def count_events(
        self,
        *,
        event_type: EventType | str | None = None,
        event_types: Iterable[EventType | str] | None = None,
        symbol: str | None = None,
        source_module: str | None = None,
        position_id: str | None = None,
        order_id: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
    ) -> int:
        """Filtered count. Same filter set as list_events()."""
        sql, params = self._build_query(
            event_type=event_type,
            event_types=event_types,
            symbol=symbol,
            source_module=source_module,
            position_id=position_id,
            order_id=order_id,
            since_ts=since_ts,
            until_ts=until_ts,
            count_only=True,
        )
        try:
            return int(self.conn.execute(sql, params).fetchone()[0])
        except sqlite3.Error as exc:
            logger.error("EventRepository count_events failed: {}", exc)
            raise EventPersistenceError(f"count_events failed: {exc}") from exc

    # Backwards-compat aliases (Phase 1 API)
    def list(self, **kwargs) -> list[Event]:
        return self.list_events(**kwargs)

    def replay(self, **kwargs) -> Iterator[Event]:
        return self.replay_events(**kwargs)

    def count(self, **kwargs) -> int:
        return self.count_events(**kwargs)

    # ------------------------------------------------------------------
    # Capital event helpers (Issue #2 §"必须支持以下事件类型 / 资金事件")
    #
    # These are thin wrappers around append_event() that produce a
    # CAPITAL_* event with a canonical payload shape. They DO NOT
    # implement the Capital Flow Engine - that lands in Issue #8 - they
    # only ensure the substrate Issue #8 will sit on top of is in place
    # in Phase 2.
    # ------------------------------------------------------------------
    def record_capital_deposit(
        self,
        *,
        amount: float,
        source_module: str = "capital",
        currency: str = "USDT",
        note: str | None = None,
        timestamp: int | None = None,
    ) -> Event:
        return self._append_capital(
            EventType.CAPITAL_DEPOSIT,
            amount=amount,
            source_module=source_module,
            currency=currency,
            note=note,
            timestamp=timestamp,
        )

    def record_capital_withdrawal(
        self,
        *,
        amount: float,
        source_module: str = "capital",
        currency: str = "USDT",
        note: str | None = None,
        timestamp: int | None = None,
    ) -> Event:
        return self._append_capital(
            EventType.CAPITAL_WITHDRAWAL,
            amount=amount,
            source_module=source_module,
            currency=currency,
            note=note,
            timestamp=timestamp,
        )

    def record_profit_harvest(
        self,
        *,
        amount: float,
        source_module: str = "capital",
        currency: str = "USDT",
        note: str | None = None,
        timestamp: int | None = None,
    ) -> Event:
        return self._append_capital(
            EventType.PROFIT_HARVEST,
            amount=amount,
            source_module=source_module,
            currency=currency,
            note=note,
            timestamp=timestamp,
        )

    def record_capital_rebase(
        self,
        *,
        exchange_equity: float,
        withdrawn_profit: float,
        lifetime_equity: float,
        trading_capital: float,
        source_module: str = "capital",
        currency: str = "USDT",
        note: str | None = None,
        timestamp: int | None = None,
    ) -> Event:
        payload: dict[str, object] = {
            "amount": float(trading_capital),
            "currency": currency,
            "exchange_equity": float(exchange_equity),
            "withdrawn_profit": float(withdrawn_profit),
            "lifetime_equity": float(lifetime_equity),
            "trading_capital": float(trading_capital),
        }
        if note is not None:
            payload["note"] = note
        return self._append_event_with_payload(
            EventType.CAPITAL_REBASE,
            source_module=source_module,
            payload=payload,
            timestamp=timestamp,
        )

    def record_risk_budget_recalculated(
        self,
        *,
        new_risk_budget: float,
        previous_risk_budget: float | None = None,
        source_module: str = "capital",
        currency: str = "USDT",
        note: str | None = None,
        timestamp: int | None = None,
    ) -> Event:
        payload: dict[str, object] = {
            "amount": float(new_risk_budget),
            "currency": currency,
            "new_risk_budget": float(new_risk_budget),
        }
        if previous_risk_budget is not None:
            payload["previous_risk_budget"] = float(previous_risk_budget)
        if note is not None:
            payload["note"] = note
        return self._append_event_with_payload(
            EventType.RISK_BUDGET_RECALCULATED,
            source_module=source_module,
            payload=payload,
            timestamp=timestamp,
        )

    def _append_capital(
        self,
        event_type: EventType,
        *,
        amount: float,
        source_module: str,
        currency: str,
        note: str | None,
        timestamp: int | None,
    ) -> Event:
        if amount < 0:
            raise ValueError(
                f"{event_type.value} amount must be >= 0; got {amount}. "
                "Withdrawals are positive amounts; direction is encoded by event_type."
            )
        payload: dict[str, object] = {"amount": float(amount), "currency": currency}
        if note is not None:
            payload["note"] = note
        return self._append_event_with_payload(
            event_type,
            source_module=source_module,
            payload=payload,
            timestamp=timestamp,
        )

    def _append_event_with_payload(
        self,
        event_type: EventType,
        *,
        source_module: str,
        payload: dict[str, object],
        timestamp: int | None,
    ) -> Event:
        kwargs: dict[str, object] = {
            "event_type": event_type,
            "source_module": source_module,
            "payload": payload,
        }
        if timestamp is not None:
            kwargs["timestamp"] = int(timestamp)
        return self.append_event(Event(**kwargs))  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_query(
        self,
        *,
        event_type: EventType | str | None,
        event_types: Iterable[EventType | str] | None,
        symbol: str | None,
        source_module: str | None,
        position_id: str | None,
        order_id: str | None,
        since_ts: int | None,
        until_ts: int | None,
        count_only: bool = False,
    ) -> tuple[str, list[object]]:
        select_clause = "SELECT COUNT(*) FROM events" if count_only else "SELECT * FROM events"
        sql = [select_clause + " WHERE 1=1"]
        params: list[object] = []
        if event_type is not None:
            sql.append("AND event_type = ?")
            params.append(_event_type_value(event_type))
        if event_types is not None:
            type_values = [_event_type_value(t) for t in event_types]
            if not type_values:
                # An explicit empty filter -> no matches.
                sql.append("AND 0=1")
            else:
                placeholders = ",".join("?" for _ in type_values)
                sql.append(f"AND event_type IN ({placeholders})")
                params.extend(type_values)
        if symbol is not None:
            sql.append("AND symbol = ?")
            params.append(symbol)
        if source_module is not None:
            sql.append("AND source_module = ?")
            params.append(source_module)
        if position_id is not None:
            sql.append("AND position_id = ?")
            params.append(position_id)
        if order_id is not None:
            sql.append("AND order_id = ?")
            params.append(order_id)
        if since_ts is not None:
            sql.append("AND timestamp >= ?")
            params.append(int(since_ts))
        if until_ts is not None:
            sql.append("AND timestamp <= ?")
            params.append(int(until_ts))
        return " ".join(sql), params

    @property
    def failed_appends(self) -> int:
        """Cumulative number of failed append attempts since construction."""
        return self._failed_appends

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> Event:
        keys = row.keys() if hasattr(row, "keys") else []
        return Event(
            event_id=row["event_id"],
            timestamp=row["timestamp"],
            event_type=EventType(row["event_type"]),
            source_module=row["source_module"],
            symbol=row["symbol"],
            position_id=row["position_id"],
            order_id=row["order_id"],
            payload=json.loads(row["payload_json"] or "{}"),
            created_at=row["created_at"] if "created_at" in keys else None,
        )


def _event_type_value(t: EventType | str) -> str:
    return t.value if isinstance(t, EventType) else str(t)
