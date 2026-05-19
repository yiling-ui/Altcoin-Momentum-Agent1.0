"""Phase 9 Incident value objects (Issue #9, Spec §38)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.clock import now_ms
from app.core.enums import IncidentLevel


# Lowercase string constants used by the ``incident_log.state`` column
# and by the typed callers in Phase 9. Phase 2's incidents.sql commits
# to lowercase ``opened`` / ``updated`` / ``resolved``; we mirror the
# spelling here so the writer and the schema agree.
INCIDENT_STATE_OPENED: str = "opened"
INCIDENT_STATE_UPDATED: str = "updated"
INCIDENT_STATE_RESOLVED: str = "resolved"

INCIDENT_LIFECYCLE_STATES: tuple[str, ...] = (
    INCIDENT_STATE_OPENED,
    INCIDENT_STATE_UPDATED,
    INCIDENT_STATE_RESOLVED,
)


@dataclass
class Incident:
    """In-process incident record returned by :class:`IncidentRepository`.

    Phase 9 keeps this small: the on-disk row in ``incidents.db`` carries
    the canonical state, this dataclass is for callers that want a
    typed handle in memory.
    """

    incident_id: str
    level: IncidentLevel
    title: str
    description: str
    source_module: str
    symbol: str | None
    position_id: str | None
    opened_at: int
    resolved_at: int | None = None
    resolution: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "level": self.level.value,
            "title": self.title,
            "description": self.description,
            "source_module": self.source_module,
            "symbol": self.symbol,
            "position_id": self.position_id,
            "opened_at": int(self.opened_at),
            "resolved_at": (
                int(self.resolved_at) if self.resolved_at is not None else None
            ),
            "resolution": self.resolution,
            "payload": dict(self.payload),
        }


@dataclass
class IncidentRecord:
    """One row from the ``incident_log`` table (lifecycle history).

    The repository writes one row per incident state change; tests use
    this dataclass to assert what landed on disk.
    """

    log_id: int
    incident_id: str
    timestamp: int
    state: str
    note: str | None
    payload: dict[str, Any] = field(default_factory=dict)


def make_incident_id() -> str:
    """Return a deterministic incident identifier ``inc_<hex>``."""
    import uuid

    return f"inc_{uuid.uuid4().hex[:16]}"


def utc_ms() -> int:
    """Wrapper around :func:`now_ms` so callers don't import core/clock."""
    return now_ms()


__all__ = [
    "INCIDENT_STATE_OPENED",
    "INCIDENT_STATE_UPDATED",
    "INCIDENT_STATE_RESOLVED",
    "INCIDENT_LIFECYCLE_STATES",
    "Incident",
    "IncidentRecord",
    "make_incident_id",
    "utc_ms",
]
