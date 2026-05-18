"""Market Data Buffer (Phase 4 - Issue #4).

The Buffer is the in-process aggregator that feeds Spec §11.1
``MarketSnapshot`` views to every later phase. It owns:

  - rolling windows of recent trades (1m / 5m / 15m);
  - a :class:`CandleBuilder` per symbol for 1-minute and 5-minute bars;
  - the latest :class:`OrderBook` per symbol (with reliability tier);
  - the latest / previous :class:`FundingRate` per symbol;
  - the latest / previous :class:`OpenInterest` per symbol;
  - a bounded deque of :class:`LiquidationEvent` per symbol.

It exposes:

  - :meth:`is_degraded` and :meth:`degraded_reasons` so a future
    No-Trade Gate (Issue #7) can refuse new openings while data is
    untrustworthy;
  - :meth:`snapshot` returning a Spec §11.1 ``MarketSnapshot``;
  - :meth:`stats` for the entrypoint banner and monitoring.

It emits, through the existing :class:`EventRepository`:

  - ``DATA_UNRELIABLE`` whenever a symbol view degrades (Issue #4
    acceptance criterion 4);
  - ``MARKET_SNAPSHOT`` whenever a snapshot is produced (Spec §12).

It NEVER opens a network socket, NEVER imports an exchange SDK, NEVER
reads a credential, NEVER calls a write surface. The Phase 1 safety
lock and the Phase 3 read-only invariant are unchanged.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

from loguru import logger

from app.core.clock import now_ms
from app.core.enums import DataReliability, ExchangeConnectionState
from app.core.events import Event, EventType
from app.core.models import MarketSnapshot
from app.database.repositories import EventRepository
from app.exchanges.base import ExchangeClientBase
from app.exchanges.models import (
    FundingRate,
    OpenInterest,
    OrderBook,
    RecentTrade,
)
from app.market_data.atr import compute_atr
from app.market_data.candles import CandleBuilder
from app.market_data.cvd import compute_cvd
from app.market_data.funding import FundingSnapshotState
from app.market_data.liquidation import LiquidationFeedState
from app.market_data.models import (
    Bar,
    BarInterval,
    BufferStats,
    LiquidationEvent,
    MarketDataBufferConfig,
    MarketDataDegradedReason,
)
from app.market_data.oi import OpenInterestSnapshotState


@dataclass
class _SymbolState:
    """Per-symbol state held inside :class:`MarketDataBuffer`."""

    symbol: str
    config: MarketDataBufferConfig

    trades_1m: deque[RecentTrade] = field(default_factory=deque)
    trades_5m: deque[RecentTrade] = field(default_factory=deque)
    trades_15m: deque[RecentTrade] = field(default_factory=deque)

    candle_1m: CandleBuilder = field(init=False)
    candle_5m: CandleBuilder = field(init=False)

    orderbook: OrderBook | None = None
    orderbook_last_ts: int | None = None
    orderbook_source_tier: DataReliability | None = None

    funding: FundingSnapshotState = field(init=False)
    oi: OpenInterestSnapshotState = field(init=False)
    liquidations: LiquidationFeedState = field(init=False)

    last_trade_ts: int | None = None
    explicit_degraded_reasons: set[MarketDataDegradedReason] = field(
        default_factory=set
    )
    cached_reasons: tuple[MarketDataDegradedReason, ...] = ()

    def __post_init__(self) -> None:
        self.candle_1m = CandleBuilder(
            self.symbol,
            interval=BarInterval.M1,
            history=self.config.bar_history_size,
        )
        self.candle_5m = CandleBuilder(
            self.symbol,
            interval=BarInterval.M5,
            history=max(self.config.bar_history_size // 5, 1),
        )
        self.funding = FundingSnapshotState(symbol=self.symbol)
        self.oi = OpenInterestSnapshotState(symbol=self.symbol)
        self.liquidations = LiquidationFeedState(
            symbol=self.symbol,
            capacity=self.config.liquidation_history_size,
        )

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------
    def push_trade(self, trade: RecentTrade) -> tuple[Bar | None, Bar | None]:
        """Append a trade to all rolling windows + candle builders.

        Returns the (1m, 5m) bars that closed because of this trade.
        """
        if trade.symbol != self.symbol:
            raise ValueError(
                f"_SymbolState({self.symbol}) received trade for {trade.symbol}"
            )
        self.trades_1m.append(trade)
        self.trades_5m.append(trade)
        self.trades_15m.append(trade)
        self.last_trade_ts = trade.timestamp
        closed_1m = self.candle_1m.feed(trade)
        closed_5m = self.candle_5m.feed(trade)
        self._evict_old_trades()
        return closed_1m, closed_5m

    def _evict_old_trades(self) -> None:
        """Drop trades that have fallen out of each rolling window.

        We use the latest known trade timestamp rather than ``now_ms()``
        so the buffer is fully deterministic when fed historical /
        replay data.
        """
        if self.last_trade_ts is None:
            return
        cutoff_1m = self.last_trade_ts - self.config.trades_window_1m_ms
        cutoff_5m = self.last_trade_ts - self.config.trades_window_5m_ms
        cutoff_15m = self.last_trade_ts - self.config.trades_window_15m_ms
        while self.trades_1m and self.trades_1m[0].timestamp < cutoff_1m:
            self.trades_1m.popleft()
        while self.trades_5m and self.trades_5m[0].timestamp < cutoff_5m:
            self.trades_5m.popleft()
        while self.trades_15m and self.trades_15m[0].timestamp < cutoff_15m:
            self.trades_15m.popleft()

    # ------------------------------------------------------------------
    # Volumes
    # ------------------------------------------------------------------
    def volume(self, *, window: BarInterval | None = None) -> float:
        if window is None or window is BarInterval.M1:
            return sum(t.qty for t in self.trades_1m)
        if window is BarInterval.M5:
            return sum(t.qty for t in self.trades_5m)
        raise ValueError(f"Unsupported window {window}")

    def cvd(self, *, window_ms: int) -> float:
        if window_ms <= 0:
            return 0.0
        if window_ms == self.config.trades_window_1m_ms:
            return compute_cvd(self.trades_1m)
        if window_ms == self.config.trades_window_5m_ms:
            return compute_cvd(self.trades_5m)
        if window_ms == self.config.trades_window_15m_ms:
            return compute_cvd(self.trades_15m)
        # Arbitrary window: filter from the largest deque.
        if self.last_trade_ts is None:
            return 0.0
        cutoff = self.last_trade_ts - window_ms
        return compute_cvd(t for t in self.trades_15m if t.timestamp >= cutoff)


class MarketDataBuffer:
    """Per-symbol Market Data Buffer.

    Phase 4 hard boundary
    ---------------------

    The buffer is a *passive consumer* of data. It does not pull from
    any exchange, it does not maintain a WebSocket, it does not own a
    credential. It receives data only via the :meth:`ingest_*` methods
    and the optional :meth:`refresh_from_exchange` helper used by the
    bootstrap path; even that helper is documented and tested to use
    the deterministic :class:`MockExchangeClient` only.

    The buffer holds a reference to an :class:`ExchangeClientBase` so
    that exchange-level health (`UNINITIALISED / DEGRADED /
    DISCONNECTED`) automatically maps onto the per-symbol degraded
    state. Spec §14.2 + §31 require that downstream modules treat both
    "exchange link is down" and "data window is stale" identically.
    """

    def __init__(
        self,
        *,
        exchange: ExchangeClientBase | None = None,
        event_repo: EventRepository | None = None,
        config: MarketDataBufferConfig | None = None,
        source_module: str = "market_data.buffer",
    ) -> None:
        self._exchange = exchange
        self._event_repo = event_repo
        self._config = config or MarketDataBufferConfig()
        self._source_module = source_module
        self._symbols: dict[str, _SymbolState] = {}
        self._data_unreliable_emitted: int = 0
        self._market_snapshot_emitted: int = 0
        self._market_snapshot_skipped: int = 0
        self._rest_ws_conflicts: int = 0
        # When > 0, ingest_* methods skip per-call _refresh_degraded
        # emission. The caller is then responsible for calling
        # _refresh_degraded() once after the batch. Used by
        # refresh_from_exchange() to avoid emitting one DATA_UNRELIABLE
        # event per surface as the buffer is filled in turn.
        self._batch_depth: int = 0

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------
    @property
    def config(self) -> MarketDataBufferConfig:
        return self._config

    @property
    def exchange(self) -> ExchangeClientBase | None:
        return self._exchange

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._symbols.keys()))

    @property
    def data_unreliable_events_emitted(self) -> int:
        return self._data_unreliable_emitted

    @property
    def market_snapshot_events_emitted(self) -> int:
        return self._market_snapshot_emitted

    @property
    def market_snapshot_events_skipped(self) -> int:
        """Snapshots produced while the per-call or config-level
        ``emit_event`` flag was off. Useful for confirming the Phase 4
        throttle hook is doing what it claims to do."""
        return self._market_snapshot_skipped

    @property
    def rest_ws_conflicts_total(self) -> int:
        return self._rest_ws_conflicts

    @property
    def late_trades_dropped_total(self) -> int:
        """Trades that the per-symbol :class:`CandleBuilder` rejected
        because their bucket had already closed. Spec §14.2 forbids
        silent back-filling, so the buffer drops them; a non-zero value
        is a leading indicator of an out-of-order tape and the
        future Issue #5 / #6 monitoring will alert on it.
        """
        return sum(
            st.candle_1m.dropped_late_trades + st.candle_5m.dropped_late_trades
            for st in self._symbols.values()
        )

    # ------------------------------------------------------------------
    # Symbol registration
    # ------------------------------------------------------------------
    def track(self, symbol: str) -> None:
        """Begin tracking a symbol. Subsequent ingest_* calls for an
        un-tracked symbol auto-track it as well; this method exists so
        the entrypoint can declare the universe up-front and so tests
        can assert symbol membership without ingesting anything yet.
        """
        if symbol not in self._symbols:
            self._symbols[symbol] = _SymbolState(symbol=symbol, config=self._config)

    def _state_for(self, symbol: str) -> _SymbolState:
        st = self._symbols.get(symbol)
        if st is None:
            st = _SymbolState(symbol=symbol, config=self._config)
            self._symbols[symbol] = st
        return st

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    def ingest_trade(self, trade: RecentTrade) -> None:
        """Push one trade through the rolling windows + candle builders."""
        st = self._state_for(trade.symbol)
        st.push_trade(trade)
        self._refresh_degraded(st, prev_reasons=st.cached_reasons)

    def ingest_trades(self, trades: Iterable[RecentTrade]) -> None:
        for tr in trades:
            self.ingest_trade(tr)

    def ingest_orderbook(self, book: OrderBook) -> None:
        """Update the latest order book.

        Spec §14.2: REST and WS data must NEVER silently overwrite each
        other when they disagree. This method enforces that:

          - if the new book's reliability tier is *strictly weaker*
            than the existing book's tier (e.g. REST after WS), the
            buffer keeps the strong-tier book and emits a REST/WS
            conflict event so the discrepancy is auditable;
          - if the tiers match, the newer book wins;
          - if the new book's tier is strictly stronger, it always
            wins and the conflict counter is incremented.
        """
        st = self._state_for(book.symbol)
        prev_reasons = st.cached_reasons
        existing = st.orderbook
        accepted = True
        if existing is not None and existing.reliability != book.reliability:
            self._rest_ws_conflicts += 1
            st.explicit_degraded_reasons.add(
                MarketDataDegradedReason.REST_WS_CONFLICT
            )
            self._emit_data_unreliable(
                symbol=book.symbol,
                reasons=(MarketDataDegradedReason.REST_WS_CONFLICT,),
                extra={
                    "previous_reliability": existing.reliability.value,
                    "incoming_reliability": book.reliability.value,
                },
            )
            # Now treat REST_WS_CONFLICT as already-known so the
            # post-mutation `_refresh_degraded` does NOT emit a second
            # event for the same reason.
            prev_reasons = tuple(
                list(prev_reasons) + [MarketDataDegradedReason.REST_WS_CONFLICT]
            )
            if existing.reliability.is_at_least(book.reliability):
                accepted = False
        if accepted:
            st.orderbook = book
            st.orderbook_last_ts = book.timestamp
            st.orderbook_source_tier = book.reliability
        self._refresh_degraded(st, prev_reasons=prev_reasons)

    def ingest_funding(self, funding: FundingRate) -> None:
        st = self._state_for(funding.symbol)
        prev_reasons = st.cached_reasons
        st.funding.update(funding)
        self._refresh_degraded(st, prev_reasons=prev_reasons)

    def ingest_open_interest(self, oi: OpenInterest) -> None:
        st = self._state_for(oi.symbol)
        prev_reasons = st.cached_reasons
        st.oi.update(oi)
        self._refresh_degraded(st, prev_reasons=prev_reasons)

    def ingest_liquidation(self, event: LiquidationEvent) -> None:
        st = self._state_for(event.symbol)
        prev_reasons = st.cached_reasons
        st.liquidations.push(event)
        self._refresh_degraded(st, prev_reasons=prev_reasons)

    def mark_degraded(
        self,
        symbol: str,
        *,
        reason: MarketDataDegradedReason = MarketDataDegradedReason.EXPLICIT_MARK,
        note: str | None = None,
    ) -> None:
        """Force a symbol view into the degraded set.

        Used by the WebSocket-disconnect handler in the entrypoint, by
        the future Reconciliation loop (Issue #9), and by tests.
        """
        st = self._state_for(symbol)
        prev_reasons = st.cached_reasons
        st.explicit_degraded_reasons.add(reason)
        self._refresh_degraded(
            st, prev_reasons=prev_reasons, note=note, force_emit_reason=reason
        )

    def clear_explicit_degraded(self, symbol: str) -> None:
        """Clear all `EXPLICIT_MARK`-style reasons. Stale-window reasons
        are recomputed from the underlying state and may stay set.
        """
        st = self._state_for(symbol)
        prev_reasons = st.cached_reasons
        st.explicit_degraded_reasons.clear()
        self._refresh_degraded(st, prev_reasons=prev_reasons)

    # ------------------------------------------------------------------
    # WebSocket / connection lifecycle
    # ------------------------------------------------------------------
    def on_websocket_disconnect(
        self, *, reason: str = "ws_disconnect"
    ) -> None:
        """Handle a WebSocket drop.

        Issue #4 acceptance criterion 4 mandates that this writes a
        DATA_UNRELIABLE event. We mark every tracked symbol as degraded
        and emit ONE batched DATA_UNRELIABLE event with the full symbol
        list so consumers can pause new openings cheaply.
        """
        symbols = sorted(self._symbols.keys())
        for sym in symbols:
            st = self._symbols[sym]
            st.explicit_degraded_reasons.add(
                MarketDataDegradedReason.EXCHANGE_DISCONNECTED
            )
            # Keep cached_reasons fresh so subsequent is_degraded calls
            # are O(1) without recomputing.
            st.cached_reasons = self._compute_reasons(st)
        if self._event_repo is not None:
            self._event_repo.append(
                Event(
                    event_type=EventType.DATA_UNRELIABLE,
                    source_module=self._source_module,
                    payload={
                        "scope": "all_symbols",
                        "reason": reason,
                        "symbols": symbols,
                        "trigger": "websocket_disconnect",
                    },
                )
            )
            self._data_unreliable_emitted += 1

    def on_websocket_reconnect(self, *, reason: str = "ws_reconnect") -> None:
        """Clear the EXCHANGE_DISCONNECTED / EXCHANGE_DEGRADED reasons.

        Stale-window reasons are recomputed and may remain set until
        fresh data arrives.
        """
        for st in self._symbols.values():
            prev = st.cached_reasons
            st.explicit_degraded_reasons.discard(
                MarketDataDegradedReason.EXCHANGE_DISCONNECTED
            )
            st.explicit_degraded_reasons.discard(
                MarketDataDegradedReason.EXCHANGE_DEGRADED
            )
            self._refresh_degraded(st, prev_reasons=prev, note=reason)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def is_degraded(self, symbol: str) -> bool:
        """True if the symbol view should NOT be used for decisions.

        Issue #4 acceptance criterion 3: data missing -> degraded.
        Spec §14.2 + §31: untrustworthy data must not feed openings.
        Issue #7's No-Trade Gate will call this directly.
        """
        return bool(self.degraded_reasons(symbol))

    def degraded_reasons(
        self, symbol: str
    ) -> tuple[MarketDataDegradedReason, ...]:
        """The set of reasons currently keeping the symbol degraded.

        Recomputes on every call so timestamp-based reasons (stale
        windows) do not lag behind a clock that has moved forward.
        """
        st = self._symbols.get(symbol)
        if st is None:
            return (MarketDataDegradedReason.NEVER_INITIALISED,)
        reasons = self._compute_reasons(st)
        st.cached_reasons = reasons
        return reasons

    def degraded_symbols(self) -> tuple[str, ...]:
        return tuple(sym for sym in self.symbols if self.is_degraded(sym))

    def snapshot(
        self,
        symbol: str,
        *,
        emit_event: bool | None = None,
        timestamp_override: int | None = None,
    ) -> MarketSnapshot:
        """Build a Spec §11.1 :class:`MarketSnapshot` for one symbol.

        Always succeeds: degraded symbols still get a snapshot, but
        callers should consult :meth:`is_degraded` first if they intend
        to act on it. The snapshot is appended as a ``MARKET_SNAPSHOT``
        event when (a) an :class:`EventRepository` is wired in, AND
        (b) ``emit_event`` resolves to ``True``.

        ``emit_event`` resolution rules (Phase 4 review fix):

          - explicit ``True``  -> always emit
          - explicit ``False`` -> never emit (skip counter increments)
          - ``None`` (default) -> use
            ``MarketDataBufferConfig.market_snapshot_event_emit_enabled``

        Phase 4 callers (boot self-check, ad-hoc tests) snapshot at most
        a handful of times so the default is "emit". Phase 5+ consumers
        that snapshot at high cadence (anomaly scanner, regime engine)
        should either pass ``emit_event=False`` per call OR construct
        the buffer with the config flag set to ``False`` - this prevents
        ``events.db`` from growing unbounded.
        """
        if emit_event is None:
            emit_event = self._config.market_snapshot_event_emit_enabled
        st = self._state_for(symbol)
        ts = timestamp_override if timestamp_override is not None else now_ms()
        last_price = self._latest_price(st)
        bid, ask, spread_pct, depth = self._book_metrics(st)
        snapshot = MarketSnapshot(
            symbol=symbol,
            timestamp=ts,
            last_price=last_price if last_price is not None else 0.0,
            bid=bid if bid is not None else 0.0,
            ask=ask if ask is not None else 0.0,
            spread_pct=spread_pct,
            volume_1m=st.volume(window=BarInterval.M1),
            volume_5m=st.volume(window=BarInterval.M5),
            oi=st.oi.latest.open_interest if st.oi.latest is not None else None,
            funding_rate=(
                st.funding.latest.rate if st.funding.latest is not None else None
            ),
            cvd_1m=st.cvd(window_ms=self._config.trades_window_1m_ms),
            cvd_5m=st.cvd(window_ms=self._config.trades_window_5m_ms),
            atr_1m=compute_atr(
                st.candle_1m.closed_bars, window=self._config.atr_window_1m
            ),
            atr_5m=compute_atr(
                st.candle_5m.closed_bars, window=self._config.atr_window_5m
            ),
            orderbook_depth_usdt=depth,
        )
        if emit_event and self._event_repo is not None:
            self._event_repo.append(
                Event(
                    event_type=EventType.MARKET_SNAPSHOT,
                    source_module=self._source_module,
                    symbol=symbol,
                    timestamp=ts,
                    payload={
                        "last_price": snapshot.last_price,
                        "spread_pct": snapshot.spread_pct,
                        "volume_1m": snapshot.volume_1m,
                        "volume_5m": snapshot.volume_5m,
                        "cvd_1m": snapshot.cvd_1m,
                        "cvd_5m": snapshot.cvd_5m,
                        "atr_1m": snapshot.atr_1m,
                        "atr_5m": snapshot.atr_5m,
                        "oi": snapshot.oi,
                        "funding_rate": snapshot.funding_rate,
                        "orderbook_depth_usdt": snapshot.orderbook_depth_usdt,
                        "degraded": self.is_degraded(symbol),
                        "degraded_reasons": [
                            r.value for r in self.degraded_reasons(symbol)
                        ],
                    },
                )
            )
            self._market_snapshot_emitted += 1
        elif self._event_repo is not None:
            # Tracked separately so observability can confirm the
            # throttle is doing what it claims to do.
            self._market_snapshot_skipped += 1
        return snapshot

    def cvd_15m(self, symbol: str) -> float:
        st = self._state_for(symbol)
        return st.cvd(window_ms=self._config.trades_window_15m_ms)

    def stats(self) -> BufferStats:
        return BufferStats(
            symbols_tracked=len(self._symbols),
            symbols_degraded=len(self.degraded_symbols()),
            data_unreliable_events_emitted=self._data_unreliable_emitted,
            market_snapshot_events_emitted=self._market_snapshot_emitted,
            market_snapshot_events_skipped=self._market_snapshot_skipped,
            rest_ws_conflicts_total=self._rest_ws_conflicts,
            late_trades_dropped_total=self.late_trades_dropped_total,
        )

    # ------------------------------------------------------------------
    # Optional helper: pull fixture data from a MockExchangeClient.
    # ------------------------------------------------------------------
    def refresh_from_exchange(
        self,
        symbol: str,
        *,
        trades_limit: int = 100,
    ) -> None:
        """Pull a deterministic snapshot of (trades, book, funding, OI)
        from the attached exchange client.

        Phase 4 hard rule (declared in Issue #4 + the user-facing
        review of PR #14 + the Phase 4 review of this PR):

          - The default and ONLY supported caller for this helper is
            :class:`MockExchangeClient` / a fixture-driven client.
          - **Phase 4 does NOT allow auto-connecting to a real public
            adapter.** Any real public read-only WS / REST adapter must
            be opt-in (off by default), require no API key, expose no
            write surface (no write surface, period), and not be wired
            here without an explicit review checkpoint.
          - **Tests must NOT depend on real network.** The repo-wide
            ``test_phase3_no_network.py`` and ``test_phase4_no_network``
            scans enforce this by reading every ``app/`` source file
            and rejecting forbidden imports.

        Defence-in-depth: if a future caller mistakenly wires a real
        :class:`BinanceClient` here, the underlying
        ``NotImplementedError`` from each Phase 3 read method propagates
        out of this helper rather than being silently swallowed - the
        Phase 3 test suite asserts that contract and
        ``test_refresh_from_exchange_propagates_notimplementederror_from_binance``
        confirms this helper preserves it.
        """
        if self._exchange is None:
            raise RuntimeError(
                "MarketDataBuffer.refresh_from_exchange called without an "
                "exchange client. Phase 4 wires this only on the boot "
                "path with MockExchangeClient."
            )
        client = self._exchange
        # Honour the gateway's connection state: if it has explicitly
        # marked itself degraded / disconnected, propagate that.
        state = client.health.state
        st = self._state_for(symbol)
        prev_reasons = st.cached_reasons
        if state is ExchangeConnectionState.DISCONNECTED:
            st.explicit_degraded_reasons.add(
                MarketDataDegradedReason.EXCHANGE_DISCONNECTED
            )
            self._refresh_degraded(st, prev_reasons=prev_reasons)
            return
        if state is ExchangeConnectionState.DEGRADED:
            st.explicit_degraded_reasons.add(
                MarketDataDegradedReason.EXCHANGE_DEGRADED
            )
        else:
            st.explicit_degraded_reasons.discard(
                MarketDataDegradedReason.EXCHANGE_DEGRADED
            )
            st.explicit_degraded_reasons.discard(
                MarketDataDegradedReason.EXCHANGE_DISCONNECTED
            )

        self._batch_depth += 1
        try:
            try:
                trades = client.get_recent_trades(symbol, limit=trades_limit)
                for tr in trades:
                    self.ingest_trade(tr)
            except NotImplementedError:
                # Real BinanceClient skeleton was wired in: surface the
                # error so the caller cannot rely on silently-empty data.
                raise
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "[market_data] refresh_from_exchange.trades({}) failed: {}",
                    symbol,
                    exc,
                )

            try:
                book = client.get_orderbook(symbol)
                self.ingest_orderbook(book)
            except NotImplementedError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "[market_data] refresh_from_exchange.book({}) failed: {}",
                    symbol,
                    exc,
                )

            try:
                funding = client.get_funding_rate(symbol)
                self.ingest_funding(funding)
            except NotImplementedError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "[market_data] refresh_from_exchange.funding({}) failed: {}",
                    symbol,
                    exc,
                )

            try:
                oi = client.get_open_interest(symbol)
                self.ingest_open_interest(oi)
            except NotImplementedError:
                raise
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "[market_data] refresh_from_exchange.oi({}) failed: {}",
                    symbol,
                    exc,
                )
        finally:
            self._batch_depth -= 1
        self._refresh_degraded(st, prev_reasons=prev_reasons)

    # ------------------------------------------------------------------
    # Internal degraded-state computation
    # ------------------------------------------------------------------
    def _compute_reasons(
        self, st: _SymbolState
    ) -> tuple[MarketDataDegradedReason, ...]:
        reasons: set[MarketDataDegradedReason] = set(
            st.explicit_degraded_reasons
        )
        # Map the gateway's connection state in.
        if self._exchange is not None:
            state = self._exchange.health.state
            if state is ExchangeConnectionState.DISCONNECTED:
                reasons.add(MarketDataDegradedReason.EXCHANGE_DISCONNECTED)
            elif state is ExchangeConnectionState.DEGRADED:
                reasons.add(MarketDataDegradedReason.EXCHANGE_DEGRADED)
            elif state is ExchangeConnectionState.UNINITIALISED:
                reasons.add(MarketDataDegradedReason.NEVER_INITIALISED)
        if (
            st.last_trade_ts is None
            and st.orderbook is None
            and st.funding.latest is None
            and st.oi.latest is None
        ):
            # Genuinely never received any data.
            reasons.add(MarketDataDegradedReason.NEVER_INITIALISED)

        # Stale-window checks. We anchor the staleness check to the
        # *latest observed timestamp across all surfaces*, NOT to
        # ``now_ms()``, because Phase 4 must remain fully deterministic
        # under replay. If the buffer hasn't moved forward in time, the
        # window can't be stale.
        anchor = self._latest_observed_ts(st)
        cfg = self._config.staleness
        if anchor is not None:
            if (
                st.last_trade_ts is None
                or anchor - st.last_trade_ts > cfg.trades_max_silence_ms
            ):
                reasons.add(MarketDataDegradedReason.TRADES_STALE)
            if (
                st.orderbook_last_ts is None
                or anchor - st.orderbook_last_ts > cfg.orderbook_max_silence_ms
            ):
                reasons.add(MarketDataDegradedReason.ORDERBOOK_STALE)
            if (
                st.oi.last_update_ts is None
                or anchor - st.oi.last_update_ts > cfg.oi_max_silence_ms
            ):
                reasons.add(MarketDataDegradedReason.OI_STALE)
            if (
                st.funding.last_update_ts is None
                or anchor - st.funding.last_update_ts > cfg.funding_max_silence_ms
            ):
                reasons.add(MarketDataDegradedReason.FUNDING_STALE)
        # Stable order: by enum declaration.
        order = list(MarketDataDegradedReason)
        return tuple(r for r in order if r in reasons)

    def _latest_observed_ts(self, st: _SymbolState) -> int | None:
        candidates = [
            st.last_trade_ts,
            st.orderbook_last_ts,
            st.oi.last_update_ts,
            st.funding.last_update_ts,
        ]
        non_null = [c for c in candidates if c is not None]
        return max(non_null) if non_null else None

    def _refresh_degraded(
        self,
        st: _SymbolState,
        *,
        prev_reasons: tuple[MarketDataDegradedReason, ...],
        note: str | None = None,
        force_emit_reason: MarketDataDegradedReason | None = None,
    ) -> None:
        """Recompute reasons after a state mutation; emit a
        DATA_UNRELIABLE event if the symbol crossed into the degraded
        set or if an explicit reason was added that wasn't there
        before.
        """
        new_reasons = self._compute_reasons(st)
        st.cached_reasons = new_reasons
        if self._batch_depth > 0 and force_emit_reason is None:
            # Inside a batched ingest call - defer the emission until
            # the batch finishes.
            return
        prev_set = set(prev_reasons)
        new_set = set(new_reasons)
        crossed_into_degraded = bool(new_set) and not bool(prev_set)
        added = new_set - prev_set
        if force_emit_reason is not None:
            # Always emit when an explicit reason was added.
            added.add(force_emit_reason)
        if crossed_into_degraded or added:
            self._emit_data_unreliable(
                symbol=st.symbol,
                reasons=tuple(r for r in new_reasons if r in added or crossed_into_degraded),
                extra=({"note": note} if note else None),
            )

    def _emit_data_unreliable(
        self,
        *,
        symbol: str,
        reasons: tuple[MarketDataDegradedReason, ...],
        extra: dict[str, object] | None = None,
    ) -> None:
        if self._event_repo is None:
            return
        if not reasons:
            return
        payload: dict[str, object] = {
            "scope": "symbol",
            "symbol": symbol,
            "reasons": [r.value for r in reasons],
        }
        if extra:
            payload.update(extra)
        self._event_repo.append(
            Event(
                event_type=EventType.DATA_UNRELIABLE,
                source_module=self._source_module,
                symbol=symbol,
                payload=payload,
            )
        )
        self._data_unreliable_emitted += 1

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _latest_price(st: _SymbolState) -> float | None:
        live = st.candle_1m.live_bar
        if live is not None:
            return live.close
        if st.candle_1m.closed_bars:
            return st.candle_1m.closed_bars[-1].close
        if st.last_trade_ts is not None and st.trades_1m:
            return st.trades_1m[-1].price
        if st.orderbook is not None:
            mid = st.orderbook.mid_price
            if mid is not None:
                return mid
        return None

    @staticmethod
    def _book_metrics(
        st: _SymbolState,
    ) -> tuple[float | None, float | None, float, float | None]:
        book = st.orderbook
        if book is None:
            return None, None, 0.0, None
        bid = book.best_bid
        ask = book.best_ask
        spread_pct = 0.0
        if bid is not None and ask is not None and ask > 0:
            spread_pct = max((ask - bid) / ask, 0.0)
        depth_usdt: float | None = None
        if bid is not None and ask is not None:
            mid = (bid + ask) / 2.0
            depth_usdt = sum(lvl.qty * mid for lvl in book.bids) + sum(
                lvl.qty * mid for lvl in book.asks
            )
        return bid, ask, spread_pct, depth_usdt
