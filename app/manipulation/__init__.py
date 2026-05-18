"""Phase 6 - Manipulation Detector package (Issue #6, Spec §21).

A pure stateless classifier that takes a :class:`MarketSnapshot` plus
optional bar history / book + narrative context and outputs a
:class:`ManipulationLevel` (M0..M3). The Risk Engine reads the
result and enforces:

  - M3 -> reject every new opening (Phase 6 hard rule).
  - M2 -> reject ATTACK / RIGHT_TAIL_AMPLIFY (Phase 6 hard rule).
  - M0 / M1 -> non-blocking by themselves, still consulted by the
    No-Trade Gate.
"""

from app.manipulation.detector import ManipulationDetector
from app.manipulation.models import (
    ManipulationConfig,
    ManipulationDecision,
    ManipulationInput,
)

__all__ = [
    "ManipulationConfig",
    "ManipulationDecision",
    "ManipulationDetector",
    "ManipulationInput",
]
