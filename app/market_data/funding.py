"""Funding-rate snapshot state (Phase 4 - Issue #4 §"Funding snapshot").

Mirrors :mod:`app.market_data.oi` for funding rates. The buffer keeps
the latest and previous :class:`FundingRate` so anomaly scoring (Issue
#6) can compare them without going back to the exchange.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.exchanges.models import FundingRate


@dataclass
class FundingSnapshotState:
    """Tracks the latest and previous :class:`FundingRate` for one
    symbol. Out-of-order updates are rejected.
    """

    symbol: str
    latest: FundingRate | None = None
    previous: FundingRate | None = None

    def update(self, funding: FundingRate) -> bool:
        if funding.symbol != self.symbol:
            raise ValueError(
                f"FundingSnapshotState({self.symbol}) "
                f"received funding for {funding.symbol}"
            )
        if self.latest is not None and funding.timestamp < self.latest.timestamp:
            return False
        self.previous = self.latest
        self.latest = funding
        return True

    @property
    def last_update_ts(self) -> int | None:
        return self.latest.timestamp if self.latest is not None else None

    def delta(self) -> float | None:
        if self.latest is None or self.previous is None:
            return None
        return self.latest.rate - self.previous.rate
