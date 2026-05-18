"""BinanceClient skeleton (Phase 3 - Issue #3).

Phase 3 contract
----------------
This module declares the Binance USDT-M perpetual gateway. **Phase 3
ships the skeleton ONLY.** Issue #3 forbids:

  - real ``create_order`` / ``cancel_order`` / ``set_leverage`` calls
  - any outbound HTTP / WebSocket connection
  - any dependency on an exchange SDK (``ccxt``, ``binance-connector``,
    ``python-binance`` are intentionally absent from ``requirements.txt``)

So every read-only method here raises ``NotImplementedError`` with a
pointer to the Phase that will plug in the real adapter (Phase 4 -
Market Data Buffer; Phase 9 - Execution FSM / Reconciliation). The four
write surfaces inherit ``SafeModeViolation`` from the base class.

The class still exists in Phase 3 because:

  1. Static type checkers can resolve the import.
  2. Tests can confirm that ``BinanceClient`` is read-only-by-construction
     (write surfaces refuse, read surfaces don't open a network socket).
  3. The Phase 4 PR has a stable target to extend.
"""

from __future__ import annotations

from app.core.errors import ExchangeError
from app.exchanges.base import ExchangeClientBase, WebSocketManager
from app.exchanges.models import (
    AccountSnapshot,
    ExchangeSymbol,
    FundingRate,
    OpenInterest,
    OrderBook,
    RecentTrade,
)


class BinanceClient(ExchangeClientBase):
    """Binance USDT-M perpetual exchange client - Phase 3 skeleton.

    All read-only methods raise :class:`NotImplementedError`. All write
    methods (``create_order``, ``cancel_order``, ``set_leverage``,
    ``set_margin_mode``) raise :class:`SafeModeViolation` via the base
    class. Phase 3 does NOT make any network call.
    """

    name = "binance"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool = False,
        event_repo=None,
        ws_manager: WebSocketManager | None = None,
    ) -> None:
        # Phase 3 explicitly does NOT consume credentials, even if they
        # were supplied. Subclassing this class with credentials would
        # still fail to place an order because the SafeModeViolation
        # block sits above any HTTP signing logic.
        if api_key is not None or api_secret is not None:
            # Defence in depth: refuse to even cache the secret.
            # Phase 3 must never persist a real key in process memory.
            raise ExchangeError(
                "Phase 3 BinanceClient must not be instantiated with API "
                "credentials. Live trading is disabled by the Phase 1 "
                "safety lock; credentials land with the Phase 9 "
                "Execution FSM PR. Refusing."
            )
        self._testnet = testnet
        super().__init__(event_repo=event_repo, ws_manager=ws_manager)

    @property
    def is_testnet(self) -> bool:
        return self._testnet

    # ------------------------------------------------------------------
    # Read-only API - skeleton only in Phase 3
    # ------------------------------------------------------------------
    def get_symbols(self) -> list[ExchangeSymbol]:
        raise NotImplementedError(
            "BinanceClient.get_symbols is a Phase 4 concern (Market Data "
            "Buffer). Phase 3 only ships the skeleton; use "
            "MockExchangeClient for tests and the boot self-check."
        )

    def get_orderbook(self, symbol: str, *, depth: int = 20) -> OrderBook:
        raise NotImplementedError(
            "BinanceClient.get_orderbook is a Phase 4 concern (Market "
            "Data Buffer). Phase 3 only ships the skeleton; use "
            "MockExchangeClient for tests."
        )

    def get_recent_trades(self, symbol: str, *, limit: int = 100) -> list[RecentTrade]:
        raise NotImplementedError(
            "BinanceClient.get_recent_trades is a Phase 4 concern "
            "(Market Data Buffer). Phase 3 only ships the skeleton; use "
            "MockExchangeClient for tests."
        )

    def get_funding_rate(self, symbol: str) -> FundingRate:
        raise NotImplementedError(
            "BinanceClient.get_funding_rate is a Phase 4 concern "
            "(Market Data Buffer). Phase 3 only ships the skeleton; use "
            "MockExchangeClient for tests."
        )

    def get_open_interest(self, symbol: str) -> OpenInterest:
        raise NotImplementedError(
            "BinanceClient.get_open_interest is a Phase 4 concern "
            "(Market Data Buffer). Phase 3 only ships the skeleton; use "
            "MockExchangeClient for tests."
        )

    def get_account_snapshot(self) -> AccountSnapshot:
        raise NotImplementedError(
            "BinanceClient.get_account_snapshot is a Phase 8 / 9 concern "
            "(Capital Flow Engine + Reconciliation). Phase 3 only ships "
            "the skeleton; use MockExchangeClient for tests."
        )
