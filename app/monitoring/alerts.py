"""Alert sink skeleton (Spec §36, §38).

Phase 1 ships an in-memory alert sink. No outbound calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.enums import IncidentLevel


@dataclass(frozen=True)
class Alert:
    level: IncidentLevel
    title: str
    detail: str = ""


@dataclass
class AlertSink:
    """Collects alerts into an in-memory list. Replace in Issue #10."""

    alerts: list[Alert] = field(default_factory=list)

    def emit(self, alert: Alert) -> None:
        self.alerts.append(alert)

    def drain(self) -> list[Alert]:
        out, self.alerts = self.alerts, []
        return out
