"""Universe Filter package (Phase 5 - Issue #5).

Spec §16. Decides whether a symbol is eligible for further signal
evaluation. Reads from :class:`MarketSnapshot` (Phase 4) +
:class:`ExchangeSymbol` (Phase 3) + an optional
:class:`RegimeSnapshot` (Phase 5). Writes one ``UNIVERSE_FILTERED``
event per evaluated symbol. Never trades.
"""

from app.universe.filter import UniverseFilter
from app.universe.models import UniverseConfig, UniverseDecision, UniverseInput

__all__ = [
    "UniverseConfig",
    "UniverseDecision",
    "UniverseFilter",
    "UniverseInput",
]
