"""Event types and Event dataclass for AMA-RT Event Sourcing.

Spec references:
    §12  Event Sourcing
    §12.1 Required event fields
    §12.2 Event type vocabulary
    §28.3 Capital events
    §38   Incident events

Phase 1 ships the full vocabulary plus the `DATA_UNRELIABLE` event flagged
in Issue #4 as a Phase-4 concern, so future phases can append events
without amending this file.

CRITICAL
--------
The persistence layer for events lives in `app.database.repositories`.
This module only defines the canonical event TYPE strings and the
in-memory `Event` payload object.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.clock import now_ms


class EventType(str, Enum):
    # ---- Market data ------------------------------------------------------
    MARKET_SNAPSHOT = "MARKET_SNAPSHOT"
    DATA_UNRELIABLE = "DATA_UNRELIABLE"  # Issue #4 - Phase 4 concern, declared early

    # ---- Regime / Universe ------------------------------------------------
    REGIME_UPDATED = "REGIME_UPDATED"
    UNIVERSE_FILTERED = "UNIVERSE_FILTERED"

    # ---- Scanners ---------------------------------------------------------
    PRE_ANOMALY_DETECTED = "PRE_ANOMALY_DETECTED"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"

    # ---- Confirmation / Manipulation -------------------------------------
    LIQUIDITY_CHECKED = "LIQUIDITY_CHECKED"
    TRADE_CONFIRMED = "TRADE_CONFIRMED"
    MANIPULATION_DETECTED = "MANIPULATION_DETECTED"

    # ---- LLM / Scoring ----------------------------------------------------
    LLM_INTERPRETED = "LLM_INTERPRETED"
    RIGHT_TAIL_SCORED = "RIGHT_TAIL_SCORED"
    OPPORTUNITY_GRADED = "OPPORTUNITY_GRADED"

    # ---- State machine / Risk --------------------------------------------
    STATE_TRANSITION = "STATE_TRANSITION"
    RISK_APPROVED = "RISK_APPROVED"
    RISK_REJECTED = "RISK_REJECTED"

    # ---- Orders -----------------------------------------------------------
    ORDER_SENT = "ORDER_SENT"
    ORDER_ACK = "ORDER_ACK"
    ORDER_PARTIAL_FILLED = "ORDER_PARTIAL_FILLED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELLED = "ORDER_CANCELLED"

    # ---- Stops ------------------------------------------------------------
    STOP_SENT = "STOP_SENT"
    STOP_CONFIRMED = "STOP_CONFIRMED"
    STOP_FAILED = "STOP_FAILED"

    # ---- Positions --------------------------------------------------------
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_UPDATED = "POSITION_UPDATED"
    POSITION_CLOSED = "POSITION_CLOSED"
    EXIT_TRIGGERED = "EXIT_TRIGGERED"

    # ---- Capital flow (Spec §28.3) ---------------------------------------
    CAPITAL_DEPOSIT = "CAPITAL_DEPOSIT"
    CAPITAL_WITHDRAWAL = "CAPITAL_WITHDRAWAL"
    PROFIT_HARVEST = "PROFIT_HARVEST"
    CAPITAL_REBASE = "CAPITAL_REBASE"
    RISK_BUDGET_RECALCULATED = "RISK_BUDGET_RECALCULATED"

    # ---- Reconciliation --------------------------------------------------
    RECONCILIATION_STARTED = "RECONCILIATION_STARTED"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    RECONCILIATION_RESOLVED = "RECONCILIATION_RESOLVED"

    # ---- Protection / Incidents ------------------------------------------
    PROTECTION_MODE_ENTERED = "PROTECTION_MODE_ENTERED"
    PROTECTION_MODE_EXITED = "PROTECTION_MODE_EXITED"
    INCIDENT_OPENED = "INCIDENT_OPENED"
    INCIDENT_RESOLVED = "INCIDENT_RESOLVED"

    # ---- Telegram --------------------------------------------------------
    TELEGRAM_COMMAND_RECEIVED = "TELEGRAM_COMMAND_RECEIVED"


# Capital-flow event types per Issue #2 / Spec §28.3.
CAPITAL_EVENT_TYPES = frozenset(
    {
        EventType.CAPITAL_DEPOSIT,
        EventType.CAPITAL_WITHDRAWAL,
        EventType.PROFIT_HARVEST,
        EventType.CAPITAL_REBASE,
        EventType.RISK_BUDGET_RECALCULATED,
    }
)


@dataclass(frozen=True)
class Event:
    """Canonical event payload (Spec §12.1).

    `event_id` is generated lazily; `timestamp` defaults to wall-clock ms.
    `payload` MUST be JSON-serialisable - the repository layer enforces
    this on append.
    """

    event_type: EventType
    source_module: str
    payload: dict[str, Any] = field(default_factory=dict)
    symbol: str | None = None
    position_id: str | None = None
    order_id: str | None = None
    timestamp: int = field(default_factory=now_ms)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "source_module": self.source_module,
            "symbol": self.symbol,
            "position_id": self.position_id,
            "order_id": self.order_id,
            "payload": self.payload,
        }

    def serialise_payload(self) -> str:
        """Return a JSON string of `payload`. Raises if payload is not JSON-safe."""
        return json.dumps(self.payload, separators=(",", ":"), sort_keys=True)
