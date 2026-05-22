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

from app.market_data_public.candidate_pool import (
    CANDIDATE_SOURCE_PHASE,
    CANDIDATE_STATE_ACTIVE,
    CANDIDATE_STATE_EXPIRED,
    CANDIDATE_STATE_WATCHING,
    Candidate,
    CandidatePool,
    CandidatePoolConfig,
    offer_snapshots,
)
from app.market_data_public.event_chain import (
    PaperEventChainDriver,
    PaperEventChainResult,
)
from app.market_data_public.ingest import (
    PublicMarketIngestor,
    PublicSymbolSnapshot,
)
from app.market_data_public.radar import (
    AllMarketRadarBuffer,
    AllMarketRadarSnapshot,
    RadarScoreConfig,
    RadarScoreResult,
    pre_anomaly_score_light,
)
from app.market_data_public.symbol_universe import (
    REASON_NOT_IN_EXCHANGE_INFO,
    SymbolUniverse,
    emit_symbol_rejected,
)
from app.market_data_public.ws_radar_chain import (
    WSRadarChainDriver,
    WSRadarChainResult,
)

__all__ = [
    "AllMarketRadarBuffer",
    "AllMarketRadarSnapshot",
    "CANDIDATE_SOURCE_PHASE",
    "CANDIDATE_STATE_ACTIVE",
    "CANDIDATE_STATE_EXPIRED",
    "CANDIDATE_STATE_WATCHING",
    "Candidate",
    "CandidatePool",
    "CandidatePoolConfig",
    "PaperEventChainDriver",
    "PaperEventChainResult",
    "PublicMarketIngestor",
    "PublicSymbolSnapshot",
    "RadarScoreConfig",
    "RadarScoreResult",
    "REASON_NOT_IN_EXCHANGE_INFO",
    "SymbolUniverse",
    "WSRadarChainDriver",
    "WSRadarChainResult",
    "emit_symbol_rejected",
    "offer_snapshots",
    "pre_anomaly_score_light",
]
