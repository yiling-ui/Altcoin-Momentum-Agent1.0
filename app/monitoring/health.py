"""Health-check skeleton (Spec §36)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass
class HealthChecker:
    """Aggregates named probes into an overall health status."""

    probes: dict[str, Callable[[], HealthStatus]] = field(default_factory=dict)

    def register(self, name: str, probe: Callable[[], HealthStatus]) -> None:
        self.probes[name] = probe

    def evaluate(self) -> tuple[HealthStatus, dict[str, HealthStatus]]:
        results: dict[str, HealthStatus] = {}
        worst = HealthStatus.OK
        for name, probe in self.probes.items():
            try:
                results[name] = probe()
            except Exception:
                results[name] = HealthStatus.DOWN
            if results[name] is HealthStatus.DOWN:
                worst = HealthStatus.DOWN
            elif results[name] is HealthStatus.DEGRADED and worst is not HealthStatus.DOWN:
                worst = HealthStatus.DEGRADED
        return worst, results
