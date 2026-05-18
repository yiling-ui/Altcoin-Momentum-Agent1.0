"""Market Data Buffer (Phase 4 - Issue #4).

This package builds the in-process Market Data Buffer described in
Spec §11.1, §14 and Issue #4. It is the first layer above the Phase 3
read-only Exchange Gateway and the last layer below the Regime / Universe
/ Scanner stacks (Issues #5 and #6).

Phase 4 hard boundary
---------------------

The Phase 4 boundary, set by Issue #4 and the user-facing review of
PR #14, is:

  1. Market Data Buffer ONLY. No Regime / Universe / Liquidity engine,
     no Scanner, no Confirmation, no Manipulation Detector. Issue #4
     deliberately ships only the substrate that those phases need.
  2. The buffer is fed by ``MockExchangeClient`` / fixture data by
     default. The boot path in ``python -m app.main`` continues to use
     the deterministic mock; tests use deterministic fixtures.
  3. **No real Binance WebSocket and no real REST** in this package.
     ``BinanceClient.get_*`` continues to raise ``NotImplementedError``
     for every read method and ``get_account_snapshot`` continues to
     refuse outright (no API key, no authenticated read).
  4. **No API key** is read, accepted, persisted or referenced anywhere
     in this package.
  5. **No write surface** is added. The four ``SafeModeViolation``
     refusals on ``ExchangeClientBase`` (`create_order`, `cancel_order`,
     `set_leverage`, `set_margin_mode`) are not touched.
  6. **No auto-connect** to the real exchange. The buffer never opens a
     socket; it only receives data when callers feed it.
  7. **Tests do not depend on real network**. The repo-wide
     ``test_phase3_no_network.py`` plus the new
     ``test_phase4_no_network.py`` enforce the constraint.
  8. ``BinanceClient.get_account_snapshot`` remains mock-only / skeleton-
     only in Phase 3 *and* Phase 4. Real account snapshots require an
     authenticated REST call and an API key, both forbidden until the
     limited-live phase.

The buffer's only outward effects are:

  - reading from ``app.exchanges.models`` value objects passed in by the
    caller (``RecentTrade``, ``OrderBook``, ``FundingRate``,
    ``OpenInterest``);
  - emitting ``DATA_UNRELIABLE`` and ``MARKET_SNAPSHOT`` events through
    the existing ``EventRepository`` (``app.database.repositories``);
  - exposing a ``MarketSnapshot`` (Spec §11.1) shaped query API that
    later phases can read without touching the gateway directly.
"""

from app.market_data.atr import compute_atr, true_range
from app.market_data.buffer import MarketDataBuffer
from app.market_data.candles import CandleBuilder, bucket_start_ms
from app.market_data.cvd import compute_cvd, signed_volume
from app.market_data.funding import FundingSnapshotState
from app.market_data.liquidation import LiquidationFeedState
from app.market_data.models import (
    Bar,
    BarInterval,
    BufferStats,
    LiquidationEvent,
    LiquidationSide,
    MarketDataBufferConfig,
    MarketDataDegradedReason,
    MarketDataStalenessConfig,
)
from app.market_data.oi import OpenInterestSnapshotState

__all__ = [
    "Bar",
    "BarInterval",
    "BufferStats",
    "CandleBuilder",
    "FundingSnapshotState",
    "LiquidationEvent",
    "LiquidationFeedState",
    "LiquidationSide",
    "MarketDataBuffer",
    "MarketDataBufferConfig",
    "MarketDataDegradedReason",
    "MarketDataStalenessConfig",
    "OpenInterestSnapshotState",
    "bucket_start_ms",
    "compute_atr",
    "compute_cvd",
    "signed_volume",
    "true_range",
]
