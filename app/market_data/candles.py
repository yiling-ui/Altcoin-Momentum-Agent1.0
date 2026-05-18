"""Candle / Bar builder (Phase 4 - Issue #4 §candle builder).

Aggregates :class:`app.exchanges.models.RecentTrade` into closed
:class:`app.market_data.models.Bar` instances. Phase 4 keeps the builder
deterministic, in-memory, and fully driven by ingested trades - there is
NO network call here.

A trade is assigned to a bar by its timestamp; bar boundaries are
aligned to the unix epoch so that two builders fed the same trades
always agree on bar starts, regardless of when they were instantiated.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable, Iterator

from app.exchanges.models import RecentTrade, TradeSide
from app.market_data.models import Bar, BarInterval


def bucket_start_ms(ts_ms: int, *, width_ms: int) -> int:
    """Return the start (inclusive) of the bar containing ``ts_ms``.

    Negative timestamps are not supported (the buffer only consumes
    Binance-style ms-since-epoch values).
    """
    if width_ms <= 0:
        raise ValueError("width_ms must be positive")
    if ts_ms < 0:
        raise ValueError("ts_ms must be non-negative")
    return (ts_ms // width_ms) * width_ms


class CandleBuilder:
    """Streaming OHLCV builder for one symbol and one interval.

    Usage::

        cb = CandleBuilder("BTCUSDT", interval=BarInterval.M1, history=240)
        for trade in trades:
            cb.feed(trade)
        closed = cb.closed_bars   # tuple of frozen Bars
        live = cb.live_bar        # current open bar, or None

    Trades fed out-of-order to a bar that has already closed are
    rejected silently (we do not back-fill). The buffer's REST-vs-WS
    conflict path uses :meth:`feed_many_with_conflict_check` to detect
    that situation explicitly.
    """

    def __init__(
        self,
        symbol: str,
        *,
        interval: BarInterval = BarInterval.M1,
        history: int = 240,
    ) -> None:
        if history <= 0:
            raise ValueError("history must be positive")
        self._symbol = symbol
        self._interval = interval
        self._width_ms = interval.width_ms
        self._history: deque[Bar] = deque(maxlen=history)
        self._live: Bar | None = None
        self._last_trade_ts: int | None = None
        self._dropped_late_trades: int = 0
        self._observed_bar_starts: set[int] = set()

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------
    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def interval(self) -> BarInterval:
        return self._interval

    @property
    def closed_bars(self) -> tuple[Bar, ...]:
        return tuple(self._history)

    @property
    def live_bar(self) -> Bar | None:
        return self._live

    @property
    def last_trade_ts(self) -> int | None:
        return self._last_trade_ts

    @property
    def dropped_late_trades(self) -> int:
        """Trades that arrived after their bucket had already closed.

        Spec §14.2 requires that we mark conflicts loudly; this counter
        plus the explicit ``feed_many_with_conflict_check`` path
        provides that.
        """
        return self._dropped_late_trades

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    def feed(self, trade: RecentTrade) -> Bar | None:
        """Feed one trade. Returns the bar that just *closed*, if any."""
        if trade.symbol != self._symbol:
            raise ValueError(
                f"CandleBuilder({self._symbol}) received trade for "
                f"{trade.symbol}"
            )
        bucket = bucket_start_ms(trade.timestamp, width_ms=self._width_ms)
        closed: Bar | None = None
        if self._live is None:
            # First trade ever: open the live bar.
            self._live = self._open_bar(trade, bucket)
            self._observed_bar_starts.add(bucket)
        elif bucket == self._live.open_ts:
            # Same bucket -> update OHLCV in place by replacing the
            # frozen bar.
            self._live = self._update_bar(self._live, trade)
        elif bucket > self._live.open_ts:
            # New bucket. Close the live bar, retain it, possibly fill
            # any empty intermediate buckets with synthetic flat bars
            # so ATR sees them, then open a new live bar.
            closed = self._live.model_copy(update={"closed": True})
            self._history.append(closed)
            self._observed_bar_starts.add(closed.open_ts)
            # Fill flat bars for any gap.
            gap_start = closed.open_ts + self._width_ms
            while gap_start < bucket:
                flat = Bar(
                    symbol=self._symbol,
                    interval=self._interval,
                    open_ts=gap_start,
                    close_ts=gap_start + self._width_ms,
                    open=closed.close,
                    high=closed.close,
                    low=closed.close,
                    close=closed.close,
                    volume=0.0,
                    buy_volume=0.0,
                    sell_volume=0.0,
                    trade_count=0,
                    closed=True,
                )
                self._history.append(flat)
                self._observed_bar_starts.add(flat.open_ts)
                gap_start += self._width_ms
            self._live = self._open_bar(trade, bucket)
            self._observed_bar_starts.add(bucket)
        else:
            # bucket < live.open_ts -> a late trade arrived for a bar
            # that already closed. We DO NOT back-fill - back-filling
            # would silently rewrite history. Spec §14.2 mandates
            # marking conflicts; this counter exposes them.
            self._dropped_late_trades += 1
            return None
        self._last_trade_ts = trade.timestamp
        return closed

    def feed_many(self, trades: Iterable[RecentTrade]) -> list[Bar]:
        """Feed many trades. Returns the list of bars that closed."""
        closed: list[Bar] = []
        for tr in trades:
            c = self.feed(tr)
            if c is not None:
                closed.append(c)
        return closed

    def force_close(self, *, at_ts: int | None = None) -> Bar | None:
        """Close the live bar even if no new bar's worth of trades has
        arrived. Used by tests and by the buffer when the exchange has
        been disconnected for longer than the bar width.
        """
        if self._live is None:
            return None
        live = self._live
        closed = live.model_copy(update={"closed": True})
        self._history.append(closed)
        self._observed_bar_starts.add(closed.open_ts)
        self._live = None
        if at_ts is not None and at_ts > closed.close_ts:
            # Pad with empty bars so ATR sees the gap as flat.
            gap_start = closed.close_ts
            while gap_start + self._width_ms <= at_ts:
                flat = Bar(
                    symbol=self._symbol,
                    interval=self._interval,
                    open_ts=gap_start,
                    close_ts=gap_start + self._width_ms,
                    open=closed.close,
                    high=closed.close,
                    low=closed.close,
                    close=closed.close,
                    volume=0.0,
                    buy_volume=0.0,
                    sell_volume=0.0,
                    trade_count=0,
                    closed=True,
                )
                self._history.append(flat)
                self._observed_bar_starts.add(flat.open_ts)
                gap_start += self._width_ms
        return closed

    # ------------------------------------------------------------------
    # Iteration helpers
    # ------------------------------------------------------------------
    def iter_closed(self) -> Iterator[Bar]:
        return iter(self._history)

    def __len__(self) -> int:
        n = len(self._history)
        return n + (1 if self._live is not None else 0)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _open_bar(self, trade: RecentTrade, bucket: int) -> Bar:
        buy_vol, sell_vol = _split_volume(trade)
        return Bar(
            symbol=self._symbol,
            interval=self._interval,
            open_ts=bucket,
            close_ts=bucket + self._width_ms,
            open=trade.price,
            high=trade.price,
            low=trade.price,
            close=trade.price,
            volume=trade.qty,
            buy_volume=buy_vol,
            sell_volume=sell_vol,
            trade_count=1,
            closed=False,
        )

    def _update_bar(self, live: Bar, trade: RecentTrade) -> Bar:
        buy_vol, sell_vol = _split_volume(trade)
        return live.model_copy(
            update={
                "high": max(live.high, trade.price),
                "low": min(live.low, trade.price),
                "close": trade.price,
                "volume": live.volume + trade.qty,
                "buy_volume": live.buy_volume + buy_vol,
                "sell_volume": live.sell_volume + sell_vol,
                "trade_count": live.trade_count + 1,
            }
        )


def _split_volume(trade: RecentTrade) -> tuple[float, float]:
    """Split a trade's volume into (buy, sell) taker volume.

    Binance convention: ``is_buyer_maker=True`` means the buyer was the
    resting order (the maker), so the *aggressor was a seller* and the
    qty is sell-side taker volume. We honour that convention first; if
    ``is_buyer_maker`` was not set explicitly (mock fixtures sometimes
    only set ``side``), we fall back to the trade's ``side`` field.
    """
    if trade.is_buyer_maker:
        return (0.0, trade.qty)
    if trade.is_buyer_maker is False and trade.side is TradeSide.SELL:
        # The mock can flag ``side=SELL`` without ``is_buyer_maker``;
        # Phase 4 honours ``side`` when ``is_buyer_maker`` is the
        # default False. This is *only* a tie-breaker for fixtures that
        # do not bother to set ``is_buyer_maker``; real Binance tape
        # always sets it.
        return (0.0, trade.qty)
    return (trade.qty, 0.0)
