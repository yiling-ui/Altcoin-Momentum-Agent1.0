"""Phase 11C - Public-market ingestion adapter.

The :class:`PublicMarketIngestor` pulls real Binance public-market
data through :class:`BinancePublicClient` and feeds it to the existing
Phase 4 :class:`MarketDataBuffer`. It then produces a Phase 1 §11.1
:class:`MarketSnapshot` enriched with the Phase 11C extras the buffer
itself does not know about (mark price, fresh book ticker).

Phase 11C boundary
------------------

  - never opens an exchange WRITE surface
  - never reads or stores ``api_key`` / ``api_secret``
  - all REST URLs go through
    :func:`app.exchanges.binance_public.assert_public_endpoint_allowed`
  - all data flows through :class:`MarketDataBuffer` so the Phase 4
    DATA_UNRELIABLE behaviour and Phase 5 No-Trade Gate inputs stay
    consistent
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from loguru import logger

from app.core.clock import now_ms
from app.core.errors import ExchangeError
from app.core.events import Event, EventType
from app.core.models import MarketSnapshot
from app.database.repositories import EventRepository
from app.exchanges.binance_public import BinancePublicClient, PublicMarkPrice
from app.market_data.buffer import MarketDataBuffer


@dataclass(frozen=True)
class PublicSymbolSnapshot:
    """Bundled per-symbol output of one ingestion tick.

    Carries the Phase 1 :class:`MarketSnapshot` plus the
    Phase 11C-only ``mark_price`` envelope so downstream consumers
    have the raw mark-price details for diagnostics without losing
    the canonical :class:`MarketSnapshot` shape.
    """

    symbol: str
    snapshot: MarketSnapshot
    mark_price: PublicMarkPrice | None
    is_degraded: bool
    degraded_reasons: tuple[str, ...]


class PublicMarketIngestor:
    """Drive REST polling against :class:`BinancePublicClient`.

    Each :meth:`ingest_symbol` call:

      - pulls trades, depth, funding, OI, mark-price, book-ticker
      - feeds them to the :class:`MarketDataBuffer`
      - builds a :class:`MarketSnapshot` enriched with mark_price + book
      - optionally emits ONE ``MARKET_SNAPSHOT`` event (the buffer
        itself emits a separate one when its config flag is on; we
        keep that surface untouched and let the runner toggle the
        per-call ``emit_event`` knob).

    The class is deliberately simple: no threading, no asyncio, no
    background loops. The runner orchestrates cadence; the ingestor
    is a per-tick translator.
    """

    SOURCE_MODULE = "market_data_public.ingest"

    def __init__(
        self,
        *,
        client: BinancePublicClient,
        buffer: MarketDataBuffer,
        event_repo: EventRepository | None = None,
        emit_market_snapshot_event: bool = True,
        depth_limit: int = 20,
        trades_limit: int = 100,
        klines_enabled: bool = False,
    ) -> None:
        self._client = client
        self._buffer = buffer
        self._event_repo = event_repo
        self._emit_market_snapshot_event = bool(emit_market_snapshot_event)
        self._depth_limit = int(depth_limit)
        self._trades_limit = int(trades_limit)
        self._klines_enabled = bool(klines_enabled)
        self._mark_prices: dict[str, PublicMarkPrice] = {}
        self._book_tickers: dict[str, tuple[float, float, int]] = {}
        self._snapshots_emitted = 0
        self._snapshots_skipped = 0
        self._ingestion_errors = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def client(self) -> BinancePublicClient:
        return self._client

    @property
    def buffer(self) -> MarketDataBuffer:
        return self._buffer

    @property
    def snapshots_emitted(self) -> int:
        return self._snapshots_emitted

    @property
    def snapshots_skipped(self) -> int:
        return self._snapshots_skipped

    @property
    def ingestion_errors(self) -> int:
        return self._ingestion_errors

    @property
    def mark_prices(self) -> dict[str, PublicMarkPrice]:
        """Latest mark-price envelope per symbol (read-only view)."""
        return dict(self._mark_prices)

    # ------------------------------------------------------------------
    # Single-symbol ingestion
    # ------------------------------------------------------------------
    def ingest_symbol(
        self,
        symbol: str,
        *,
        emit_event: bool | None = None,
    ) -> PublicSymbolSnapshot:
        """Run one full read pass for ``symbol`` and return a snapshot."""
        self._buffer.track(symbol)
        any_failure = False

        try:
            trades = self._client.get_recent_trades(
                symbol, limit=self._trades_limit
            )
            for tr in trades:
                self._buffer.ingest_trade(tr)
        except ExchangeError as exc:
            any_failure = True
            logger.warning(
                "[phase11c] ingest_symbol({}).trades failed: {}", symbol, exc
            )

        try:
            book = self._client.get_orderbook(symbol, depth=self._depth_limit)
            self._buffer.ingest_orderbook(book)
        except ExchangeError as exc:
            any_failure = True
            logger.warning(
                "[phase11c] ingest_symbol({}).book failed: {}", symbol, exc
            )

        try:
            funding = self._client.get_funding_rate(symbol)
            self._buffer.ingest_funding(funding)
        except ExchangeError as exc:
            any_failure = True
            logger.warning(
                "[phase11c] ingest_symbol({}).funding failed: {}",
                symbol,
                exc,
            )

        try:
            oi = self._client.get_open_interest(symbol)
            self._buffer.ingest_open_interest(oi)
        except ExchangeError as exc:
            any_failure = True
            logger.warning(
                "[phase11c] ingest_symbol({}).oi failed: {}", symbol, exc
            )

        mark = None
        try:
            mark = self._client.get_mark_price(symbol)
            self._mark_prices[symbol] = mark
        except ExchangeError as exc:
            any_failure = True
            logger.warning(
                "[phase11c] ingest_symbol({}).mark failed: {}", symbol, exc
            )

        try:
            self._book_tickers[symbol] = self._client.get_book_ticker(symbol)
        except ExchangeError as exc:
            # The book-ticker endpoint is supplemental; the order-book
            # snapshot already carries best bid/ask. We log but do not
            # mark the whole tick as failed.
            logger.debug(
                "[phase11c] ingest_symbol({}).book_ticker failed: {}",
                symbol,
                exc,
            )

        if any_failure:
            self._ingestion_errors += 1

        snapshot = self._build_snapshot(symbol, emit_event=emit_event)
        if snapshot is None:
            self._snapshots_skipped += 1
            # We still build a degenerate result so the runner can
            # account for the symbol; the snapshot itself is not
            # emitted.
            empty = MarketSnapshot(
                symbol=symbol,
                timestamp=now_ms(),
                last_price=0.0,
                bid=0.0,
                ask=0.0,
                spread_pct=0.0,
            )
            return PublicSymbolSnapshot(
                symbol=symbol,
                snapshot=empty,
                mark_price=mark,
                is_degraded=True,
                degraded_reasons=("snapshot_unavailable",),
            )

        return PublicSymbolSnapshot(
            symbol=symbol,
            snapshot=snapshot,
            mark_price=mark,
            is_degraded=self._buffer.is_degraded(symbol),
            degraded_reasons=tuple(
                r.value for r in self._buffer.degraded_reasons(symbol)
            ),
        )

    def ingest_many(
        self,
        symbols: Iterable[str],
        *,
        emit_event: bool | None = None,
    ) -> list[PublicSymbolSnapshot]:
        """Ingest a list of symbols in order. Errors per symbol are
        logged but do NOT raise; the runner is expected to keep
        running across transient REST hiccups."""
        out: list[PublicSymbolSnapshot] = []
        for sym in symbols:
            try:
                out.append(self.ingest_symbol(sym, emit_event=emit_event))
            except Exception as exc:  # pragma: no cover - defensive
                self._ingestion_errors += 1
                logger.warning(
                    "[phase11c] ingest_symbol({}) raised: {}", sym, exc
                )
        return out

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_snapshot(
        self,
        symbol: str,
        *,
        emit_event: bool | None = None,
    ) -> MarketSnapshot | None:
        # Build via the buffer first so the standard Phase 4 contract
        # (CVD / ATR / OI / funding / volume / depth) is preserved.
        try:
            base = self._buffer.snapshot(
                symbol,
                emit_event=False,  # we re-emit below with mark price
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "[phase11c] _build_snapshot({}) failed: {}", symbol, exc
            )
            return None

        mark = self._mark_prices.get(symbol)
        bid_ask_ts = self._book_tickers.get(symbol)
        bid = base.bid
        ask = base.ask
        if bid_ask_ts is not None:
            fresh_bid, fresh_ask, _ = bid_ask_ts
            # Prefer fresh book-ticker over the depth snapshot's best
            # bid/ask if and only if we have non-zero values.
            if fresh_bid > 0:
                bid = fresh_bid
            if fresh_ask > 0:
                ask = fresh_ask

        spread_pct = base.spread_pct
        if bid > 0 and ask > 0:
            spread_pct = max((ask - bid) / ask, 0.0)

        enriched = base.model_copy(
            update={
                "bid": bid,
                "ask": ask,
                "spread_pct": spread_pct,
                "mark_price": mark.mark_price if mark is not None else None,
            }
        )

        if emit_event is None:
            emit_event = self._emit_market_snapshot_event
        if emit_event and self._event_repo is not None:
            self._event_repo.append(
                Event(
                    event_type=EventType.MARKET_SNAPSHOT,
                    source_module=self.SOURCE_MODULE,
                    symbol=symbol,
                    timestamp=enriched.timestamp,
                    payload={
                        "last_price": enriched.last_price,
                        "mark_price": enriched.mark_price,
                        "bid": enriched.bid,
                        "ask": enriched.ask,
                        "spread_pct": enriched.spread_pct,
                        "volume_1m": enriched.volume_1m,
                        "volume_5m": enriched.volume_5m,
                        "oi": enriched.oi,
                        "funding_rate": enriched.funding_rate,
                        "cvd_1m": enriched.cvd_1m,
                        "cvd_5m": enriched.cvd_5m,
                        "atr_1m": enriched.atr_1m,
                        "atr_5m": enriched.atr_5m,
                        "orderbook_depth_usdt": enriched.orderbook_depth_usdt,
                        "degraded": self._buffer.is_degraded(symbol),
                        "degraded_reasons": [
                            r.value for r in self._buffer.degraded_reasons(symbol)
                        ],
                        "phase": "11C",
                        "provider": "binance_public",
                    },
                )
            )
            self._snapshots_emitted += 1
        else:
            self._snapshots_skipped += 1
        return enriched


__all__ = [
    "PublicMarketIngestor",
    "PublicSymbolSnapshot",
]
