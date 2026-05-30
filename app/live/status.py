"""Shared health-status vocabulary for the Live API Integration Pack (PR111)."""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class HealthStatus(str, Enum):
    """Tri-state health status for a live API surface."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIPPED = "SKIPPED"

    @property
    def rank(self) -> int:
        # Higher rank = worse. SKIPPED is treated as neutral (does not
        # by itself fail the overall status).
        return {
            HealthStatus.PASS: 0,
            HealthStatus.SKIPPED: 0,
            HealthStatus.WARN: 1,
            HealthStatus.FAIL: 2,
        }[self]


def worst_of(statuses: Iterable[HealthStatus]) -> HealthStatus:
    """Return the worst (most severe) status in ``statuses``.

    An empty / all-SKIPPED collection yields ``PASS`` (nothing failed).
    """
    worst = HealthStatus.PASS
    saw_any_non_skipped = False
    for s in statuses:
        if s != HealthStatus.SKIPPED:
            saw_any_non_skipped = True
        if s.rank > worst.rank:
            worst = s
    if not saw_any_non_skipped:
        return HealthStatus.PASS
    return worst


# Sentinel status strings used by per-surface results (kept as plain
# strings so they can be embedded verbatim in JSON output / events).
TRADE_API_BLOCKED_BY_PR111 = "TRADE_API_BLOCKED_BY_PR111"
TELEGRAM_OUTBOUND_DISABLED = "TELEGRAM_OUTBOUND_DISABLED"


__all__ = [
    "HealthStatus",
    "worst_of",
    "TRADE_API_BLOCKED_BY_PR111",
    "TELEGRAM_OUTBOUND_DISABLED",
]
