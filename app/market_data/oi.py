"""Open-Interest snapshot state (Phase 4 - Issue #4 §"OI snapshot").

The Phase 4 Buffer keeps the latest :class:`OpenInterest` per symbol
plus the previous value, so consumers can compute deltas without
re-querying the exchange. Real OI ingestion is a Phase 5+ concern; this
state object is fed by callers (mock fixtures or, eventually, an
adapter that the Phase 4 boundary explicitly forbids in this PR).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.exchanges.models import OpenInterest


@dataclass
class OpenInterestSnapshotState:
    """Tracks the latest and previous :class:`OpenInterest` for one
    symbol. Out-of-order updates are rejected (the *previous* slot
    keeps the older value)."""

    symbol: str
    latest: OpenInterest | None = None
    previous: OpenInterest | None = None

    def update(self, oi: OpenInterest) -> bool:
        """Apply an OI update. Returns True if accepted, False if
        rejected (out-of-order)."""
        if oi.symbol != self.symbol:
            raise ValueError(
                f"OpenInterestSnapshotState({self.symbol}) "
                f"received OI for {oi.symbol}"
            )
        if self.latest is not None and oi.timestamp < self.latest.timestamp:
            return False
        self.previous = self.latest
        self.latest = oi
        return True

    @property
    def last_update_ts(self) -> int | None:
        return self.latest.timestamp if self.latest is not None else None

    def delta(self) -> float | None:
        """Absolute change between previous and latest open interest.

        Returns None when there is fewer than two snapshots.
        """
        if self.latest is None or self.previous is None:
            return None
        return self.latest.open_interest - self.previous.open_interest

    def percent_change(self) -> float | None:
        """Relative change as a fraction of the previous OI.

        Returns None when there is fewer than two snapshots, or when
        the previous OI is exactly zero.
        """
        if self.latest is None or self.previous is None:
            return None
        if self.previous.open_interest == 0:
            return None
        return (
            self.latest.open_interest - self.previous.open_interest
        ) / self.previous.open_interest
