"""Monotonic and wall-clock helpers.

A single Clock abstraction makes deterministic replay (Issue #10) easy in
later phases. Phase 1 only ships the system clock implementation.
"""

from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def now_ms(self) -> int: ...
    def monotonic(self) -> float: ...


class SystemClock:
    """Default real-time clock."""

    def now_ms(self) -> int:
        return int(time.time() * 1000)

    def monotonic(self) -> float:
        return time.monotonic()


_default_clock: Clock = SystemClock()


def now_ms() -> int:
    return _default_clock.now_ms()


def monotonic() -> float:
    return _default_clock.monotonic()
