"""MockExchangeClient (Phase 3 - Issue #3).

Deterministic, in-memory implementation of :class:`ExchangeClientBase`
used by:

  - the Phase 3 boot self-check in ``app/main.py``
  - the Phase 3 / Phase 4 / Phase 5 unit tests

The mock NEVER opens a network socket, NEVER imports an exchange SDK,
NEVER reads an environment variable, NEVER consumes any credential. All
data is generated from a tiny seed payload supplied at construction
time. This is exactly what Issue #3 mandates: "可以 mock symbols / 可以
mock orderbook / 可以 mock recent trades / 测试不依赖真实 API".

Inherits the four ``SafeModeViolation`` write-surface refusals from
:class:`ExchangeClientBase`; this is asserted by the test suite.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from app.core.clock import now_ms
from app.core.enums import DataReliability, ExchangeConnectionState
from app.core.errors import ExchangeConnectionError
from app.exchanges.base import ExchangeClientBase, WebSocketManager
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


def _default_symbols() -> list[ExchangeSymbol]:
    """A tiny representative set used when no seed is supplied."""
    return [
        ExchangeSymbol(
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            price_tick=0.1,
            qty_step=0.001,
            min_notional=5.0,
        ),
        ExchangeSymbol(
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            price_tick=0.01,
            qty_step=0.001,
            min_notional=5.0,
        ),
        ExchangeSymbol(
            symbol="PEPEUSDT",
            base_asset="PEPE",
            quote_asset="USDT",
            price_tick=0.0000001,
            qty_step=1.0,
            min_notional=5.0,
        ),
    ]


@dataclass
class MockExchangeSeed:
    """Optional deterministic input bundle for `MockExchangeClient`.

    Tests supply a `MockExchangeSeed` to make read calls fully
    predictable. The boot self-check in `app/main.py` uses the
    constructor defaults instead.
    """

    symbols: list[ExchangeSymbol] = field(default_factory=_default_symbols)
    orderbooks: dict[str, OrderBook] = field(default_factory=dict)
    trades: dict[str, list[RecentTrade]] = field(default_factory=dict)
    funding_rates: dict[str, FundingRate] = field(default_factory=dict)
    open_interest: dict[str, OpenInterest] = field(default_factory=dict)
    account: AccountSnapshot | None = None


class MockExchangeClient(ExchangeClientBase):
    """In-memory deterministic exchange client.

    Read calls return data from the supplied :class:`MockExchangeSeed`
    (or sensible defaults). Write calls inherit ``SafeModeViolation``
    refusal from the base class. The connection state can be driven
    explicitly via ``simulate_disconnect`` / ``simulate_reconnect`` for
    test scenarios that exercise the No-Trade Gate path.
    """

    name = "mock"

    def __init__(
        self,
        *,
        seed: MockExchangeSeed | None = None,
        event_repo=None,
        ws_manager: WebSocketManager | None = None,
        autostart: bool = True,
    ) -> None:
        self._seed = seed or MockExchangeSeed()
        super().__init__(event_repo=event_repo, ws_manager=ws_manager)
        self._trade_id_counter = itertools.count(1)
        if autostart:
            self.start()

    # ------------------------------------------------------------------
    # Test-only helpers
    # ------------------------------------------------------------------
    def simulate_disconnect(self, *, reason: str = "simulated_disconnect") -> None:
        """Simulate a WS drop. Marks data as DATA_UNRELIABLE."""
        self.ws.disconnect(reason=reason)
        self._mark_disconnected(reason=reason)

    def simulate_reconnect(self, *, reason: str = "simulated_reconnect") -> None:
        """Simulate a WS reconnect."""
        self._mark_reconnecting(reason=reason)
        self.ws.connect()
        self._mark_connected(reason=reason)

    def simulate_degraded(self, *, reason: str = "rest_only") -> None:
        """Simulate a WS-down-but-REST-up state."""
        self._mark_degraded(reason=reason)

    # ------------------------------------------------------------------
    # Read-only API (Issue #3 acceptance criteria 1-3)
    # ------------------------------------------------------------------
    def get_symbols(self) -> list[ExchangeSymbol]:
        # `get_symbols` is a low-frequency REST call. We allow it even
        # when the WS link is degraded - the Universe Filter still needs
        # the symbol vocabulary - but refuse when fully disconnected.
        self._require_at_least_degraded(surface="get_symbols")
        return list(self._seed.symbols)

    def get_orderbook(self, symbol: str, *, depth: int = 20) -> OrderBook:
        self._require_trustworthy(surface="get_orderbook")
        if symbol in self._seed.orderbooks:
            book = self._seed.orderbooks[symbol]
        else:
            # Build a deterministic synthetic book centred at 100. The
            # mock is an in-memory analogue of a WS-maintained depth-diff
            # book, so it advertises tier A by default. Tests that want
            # to model a REST fallback can supply a tier-B `OrderBook`
            # via `MockExchangeSeed.orderbooks`.
            mid = 100.0
            tick = 0.1
            bids = tuple(
                OrderBookLevel(price=mid - tick * (i + 1), qty=1.0 + i)
                for i in range(min(depth, 5))
            )
            asks = tuple(
                OrderBookLevel(price=mid + tick * (i + 1), qty=1.0 + i)
                for i in range(min(depth, 5))
            )
            book = OrderBook(
                symbol=symbol,
                timestamp=now_ms(),
                bids=bids,
                asks=asks,
                reliability=DataReliability.A,
            )
        if depth and depth < len(book.bids):
            book = book.model_copy(
                update={
                    "bids": book.bids[:depth],
                    "asks": book.asks[:depth],
                }
            )
        return book

    def get_recent_trades(self, symbol: str, *, limit: int = 100) -> list[RecentTrade]:
        self._require_trustworthy(surface="get_recent_trades")
        if symbol in self._seed.trades:
            trades = self._seed.trades[symbol]
        else:
            # Build a tiny deterministic tape.
            now = now_ms()
            trades = [
                RecentTrade(
                    symbol=symbol,
                    trade_id=f"mock-{next(self._trade_id_counter)}",
                    timestamp=now - (limit - i) * 1000,
                    price=100.0 + (i % 5) * 0.1,
                    qty=1.0 + (i % 3) * 0.5,
                    side=TradeSide.BUY if i % 2 == 0 else TradeSide.SELL,
                    is_buyer_maker=(i % 2 == 1),
                    reliability=DataReliability.A,
                )
                for i in range(min(limit, 5))
            ]
        return list(trades[:limit]) if limit else list(trades)

    def get_funding_rate(self, symbol: str) -> FundingRate:
        self._require_trustworthy(surface="get_funding_rate")
        if symbol in self._seed.funding_rates:
            return self._seed.funding_rates[symbol]
        now = now_ms()
        return FundingRate(
            symbol=symbol,
            timestamp=now,
            rate=0.0001,
            next_funding_ts=now + 8 * 60 * 60 * 1000,
            reliability=DataReliability.B,
        )

    def get_open_interest(self, symbol: str) -> OpenInterest:
        self._require_trustworthy(surface="get_open_interest")
        if symbol in self._seed.open_interest:
            return self._seed.open_interest[symbol]
        return OpenInterest(
            symbol=symbol,
            timestamp=now_ms(),
            open_interest=0.0,
            open_interest_value=0.0,
            reliability=DataReliability.B,
        )

    def get_account_snapshot(self) -> AccountSnapshot:
        # Phase 3 deliberately permits the account snapshot in DEGRADED
        # mode: the Reconciliation loop (Issue #9) needs to keep polling
        # equity/positions even when the WS link is flapping. We refuse
        # outright only when the link is fully DOWN.
        self._require_at_least_degraded(surface="get_account_snapshot")
        if self._seed.account is not None:
            return self._seed.account
        return AccountSnapshot(
            timestamp=now_ms(),
            total_equity=0.0,
            available_balance=0.0,
            margin_balance=0.0,
            unrealized_pnl=0.0,
            open_position_count=0,
            reliability=DataReliability.B,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _require_at_least_degraded(self, *, surface: str) -> None:
        """Refuse only when DISCONNECTED / UNINITIALISED.

        DEGRADED still has a working REST channel per Spec §13.3, so
        REST-only surfaces (symbols, account snapshot) remain usable.
        Tier-A surfaces use `_require_trustworthy` instead.
        """
        if self.health.state in (
            ExchangeConnectionState.DISCONNECTED,
            ExchangeConnectionState.UNINITIALISED,
        ):
            raise ExchangeConnectionError(
                f"{self.name}.{surface}() refused: connection state is "
                f"{self.health.state.value} (reason={self.health.reason})"
            )
