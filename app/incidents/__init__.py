"""Phase 9 Incident package (Issue #9, Spec §38).

Phase 9 is the first phase that writes to ``incidents.db``. The
Phase 2 schema (`app/database/schemas/incidents.sql`) declared the
``incidents`` and ``incident_log`` tables; Phase 9 ships the
:class:`IncidentRepository` writer that:

  - opens new incidents (P0 / P1 / P2 / P3)
  - records every state change in ``incident_log``
  - emits ``INCIDENT_OPENED`` / ``INCIDENT_RESOLVED`` events through
    :class:`EventRepository`
  - emits ``PROTECTION_MODE_ENTERED`` / ``PROTECTION_MODE_EXITED``
    events when the operator drives the system into / out of
    protection mode

Phase 9 callers (the Execution FSM driver and the Reconciliation
loop) speak to this repository through a duck-typed
:class:`ProtectionHook` interface; tests can supply a mock that
records calls without spinning up incidents.db.

Phase 9 boundary
----------------

This package does NOT:

  - import an exchange SDK / HTTP / WebSocket / LLM library
  - open a network socket
  - call ``ExchangeClientBase.create_order`` (or any other write surface)
  - read ``os.environ`` for credentials
"""

from app.incidents.models import (
    INCIDENT_STATE_OPENED,
    INCIDENT_STATE_RESOLVED,
    INCIDENT_STATE_UPDATED,
    Incident,
    IncidentRecord,
)
from app.incidents.repository import IncidentRepository, ProtectionHook

__all__ = [
    "Incident",
    "IncidentRecord",
    "IncidentRepository",
    "ProtectionHook",
    "INCIDENT_STATE_OPENED",
    "INCIDENT_STATE_UPDATED",
    "INCIDENT_STATE_RESOLVED",
]
