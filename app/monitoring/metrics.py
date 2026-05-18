"""In-process metrics registry (Spec §36).

Phase 1 ships a tiny registry: counters and gauges only, no Prometheus
exporter. This is enough to write deterministic unit tests. Phase 4+ may
swap this for `prometheus-client`.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class MetricsRegistry:
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    gauges: dict[str, float] = field(default_factory=dict)

    def incr(self, name: str, value: int = 1) -> None:
        self.counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        self.gauges[name] = value

    def snapshot(self) -> dict[str, dict]:
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
        }
