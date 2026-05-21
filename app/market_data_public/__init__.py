"""Phase 11C - Public-market ingestion + paper event-chain driver.

This package wires :class:`app.exchanges.binance_public.BinancePublicClient`
into the existing Phase 4 :class:`MarketDataBuffer`, the Phase 6
scanners, the Phase 7 Risk Engine, and the Phase 8.5 learning-ready
contract WITHOUT introducing any new write surface and WITHOUT
opening a path to a real order.

Modules
-------

- :mod:`app.market_data_public.ingest`
  Pulls public REST data from :class:`BinancePublicClient` and feeds
  it to the buffer. Produces :class:`MarketSnapshot` objects with the
  Phase 11C extra fields populated (``mark_price``, fresh
  ``bid``/``ask``, etc.).

- :mod:`app.market_data_public.event_chain`
  Drives ONE end-to-end event chain per snapshot:
  ``MARKET_SNAPSHOT`` -> ``PRE_ANOMALY_DETECTED`` ->
  ``ANOMALY_DETECTED`` -> ``LIQUIDITY_CHECKED`` -> ``TRADE_CONFIRMED``
  -> ``MANIPULATION_DETECTED`` -> ``RISK_APPROVED`` /
  ``RISK_REJECTED`` -> ``STATE_TRANSITION``. Every ``RISK_REJECTED``
  event carries a Phase 8.5 :class:`LearningReadyContext` with the
  real :class:`OpportunityIdentity` / :class:`SignalSnapshot` /
  :class:`VirtualTradePlan` / :class:`ConfigVersions`.

Boundary
--------

  - No live trading.
  - No real exchange order.
  - No Binance API key.
  - No Binance signed endpoint.
  - No DeepSeek call.
  - No Telegram outbound.
  - The four ExchangeClientBase write surfaces remain refused.
  - The Phase 1 safety lock remains in force.
"""

from app.market_data_public.event_chain import (
    PaperEventChainDriver,
    PaperEventChainResult,
)
from app.market_data_public.ingest import (
    PublicMarketIngestor,
    PublicSymbolSnapshot,
)

__all__ = [
    "PaperEventChainDriver",
    "PaperEventChainResult",
    "PublicMarketIngestor",
    "PublicSymbolSnapshot",
]
