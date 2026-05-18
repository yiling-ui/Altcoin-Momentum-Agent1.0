"""Exchange Gateway package (Phase 3 - Issue #3).

Phase 3 ships the **read-only** abstraction:

    ExchangeClientBase   - abstract base class; methods are read-only,
                           write surfaces raise SafeModeViolation.
    BinanceClient        - skeleton subclass; no real network in Phase 3
                           (Issue #3 forbids real exchange calls).
    MockExchangeClient   - deterministic in-memory implementation used
                           by the entrypoint and the test suite.

The package never imports an exchange SDK and never opens an outbound
socket. The Phase 1 safety lock and the Phase 3 SafeModeViolation guards
are the only paths through which a real order could ever be placed; both
are unit-tested.

Spec references:
    §13   Exchange Gateway 交易所接入层
    §13.3 Data reliability tiers A/B/C/D
    §14.2 WebSocket / REST health behaviour
    §31   Reconciliation (uses the connection state from this package)
"""

from app.exchanges.base import (
    ExchangeClientBase,
    ExchangeHealth,
    WebSocketManager,
)
from app.exchanges.binance import BinanceClient
from app.exchanges.mock import MockExchangeClient
from app.exchanges.models import (
    AccountSnapshot,
    ExchangeSymbol,
    FundingRate,
    OpenInterest,
    OrderBook,
    OrderBookLevel,
    RecentTrade,
    TradeSide,
)

__all__ = [
    "ExchangeClientBase",
    "ExchangeHealth",
    "WebSocketManager",
    "BinanceClient",
    "MockExchangeClient",
    "AccountSnapshot",
    "ExchangeSymbol",
    "FundingRate",
    "OpenInterest",
    "OrderBook",
    "OrderBookLevel",
    "RecentTrade",
    "TradeSide",
]
