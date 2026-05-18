"""Liquidation feed state (Phase 4 - Issue #4 §"liquidation.py").

Phase 4 keeps a deque of :class:`LiquidationEvent` instances per
symbol. The Liquidation Spike anomaly scorer (Issue #6) and the
Liquidation Reversal strategy (Issue #6 / Phase 6) will consume this
list. Phase 4 deliberately ships only the data structure - no
``get_liquidations`` method on the gateway, no real-time feed - because
Issue #4's boundary forbids reading from any real network surface.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from app.market_data.models import LiquidationEvent


@dataclass
class LiquidationFeedState:
    """Bounded deque of recent liquidations for one symbol."""

    symbol: str
    capacity: int = 256
    history: deque[LiquidationEvent] = field(default_factory=deque)

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        # Replace the default deque with a bounded one of the right
        # capacity. Tests rely on the maxlen semantics (FIFO eviction).
        existing = list(self.history)
        self.history = deque(existing[-self.capacity :], maxlen=self.capacity)

    def push(self, event: LiquidationEvent) -> None:
        if event.symbol != self.symbol:
            raise ValueError(
                f"LiquidationFeedState({self.symbol}) "
                f"received liquidation for {event.symbol}"
            )
        self.history.append(event)

    def recent(self, *, since_ts: int | None = None) -> tuple[LiquidationEvent, ...]:
        if since_ts is None:
            return tuple(self.history)
        return tuple(e for e in self.history if e.timestamp >= since_ts)

    @property
    def last_update_ts(self) -> int | None:
        if not self.history:
            return None
        return self.history[-1].timestamp

    def __len__(self) -> int:
        return len(self.history)
