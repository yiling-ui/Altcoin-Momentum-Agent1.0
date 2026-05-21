"""Phase 11C.1B - All-Market Radar Buffer + Light Pre-Anomaly Scoring.

The radar consumes :class:`app.exchanges.binance_public_ws.WSMessage`
envelopes from the public WebSocket streams and produces, per symbol,
an :class:`AllMarketRadarSnapshot` summarising the last few seconds /
minute of activity. The snapshots are then fed to
:func:`pre_anomaly_score_light` which returns a small dataclass with
a numeric ``radar_score``, a deterministic list of ``reason_tags``
and the ``source_streams`` that contributed.

Phase 11C.1B boundary
---------------------

This module is pure-Python (stdlib + loguru + pydantic + the
existing ``app.*`` modules). It opens NO socket, calls NO LLM, reads
NO ``os.environ``, defines NO write surface, and never imports a
third-party HTTP / WebSocket / SDK package.

The radar is **descriptive**: a high ``radar_score`` is NOT a trade
authorisation. It is an *early warning signal* the
:class:`CandidatePool` consumes to decide which symbols deserve a
per-loop REST detail call (and a Phase 8.5 SignalSnapshot /
LearningReadyContext / RISK_REJECTED audit chain). Every Phase 1
safety flag remains in force regardless of how high a radar score
goes; the existing :class:`RiskEngine` is the only trade-decision
gate.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Iterable

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from app.core.clock import now_ms
from app.exchanges.binance_public_ws import WSMessage, assert_public_ws_stream_allowed


# ---------------------------------------------------------------------------
# Source-stream tags
# ---------------------------------------------------------------------------

#: Bit-flag-style source-stream tags recorded on every
#: :class:`AllMarketRadarSnapshot` so consumers can tell which
#: WebSocket streams contributed to the snapshot. Stored as a
#: ``frozenset[str]`` on the model so the on-disk representation is
#: a sorted list of tag strings (deterministic across processes).
SOURCE_STREAM_TICKER_ARR: str = "ticker_arr"
SOURCE_STREAM_MINI_TICKER_ARR: str = "mini_ticker_arr"
SOURCE_STREAM_BOOK_TICKER: str = "book_ticker"
SOURCE_STREAM_MARK_PRICE_ARR: str = "mark_price_arr"
SOURCE_STREAM_FORCE_ORDER_ARR: str = "force_order_arr"

ALL_SOURCE_STREAM_TAGS: frozenset[str] = frozenset(
    {
        SOURCE_STREAM_TICKER_ARR,
        SOURCE_STREAM_MINI_TICKER_ARR,
        SOURCE_STREAM_BOOK_TICKER,
        SOURCE_STREAM_MARK_PRICE_ARR,
        SOURCE_STREAM_FORCE_ORDER_ARR,
    }
)


def _stream_to_source_tag(stream: str) -> str | None:
    """Map a WebSocket stream name to its canonical source-stream tag.

    Returns ``None`` for streams that do not contribute to the radar.
    Per-symbol streams (``btcusdt@bookTicker`` / ``btcusdt@markPrice``)
    map to the same tag as the array variant.
    """
    text = (stream or "").strip().lower()
    if not text:
        return None
    if text == "!ticker@arr" or text.endswith("@ticker"):
        return SOURCE_STREAM_TICKER_ARR
    if text == "!miniticker@arr" or text.endswith("@miniticker"):
        return SOURCE_STREAM_MINI_TICKER_ARR
    if text == "!bookticker" or text.endswith("@bookticker"):
        return SOURCE_STREAM_BOOK_TICKER
    if text == "!markprice@arr" or text.endswith("@markprice"):
        return SOURCE_STREAM_MARK_PRICE_ARR
    if (
        text == "!forceorder@arr"
        or text.endswith("@forceorder")
        or text.endswith("@forceorder@1s")
    ):
        return SOURCE_STREAM_FORCE_ORDER_ARR
    return None


# ---------------------------------------------------------------------------
# Reason tags
# ---------------------------------------------------------------------------
RADAR_REASON_PRICE_ACCEL_15S: str = "price_acceleration_15s"
RADAR_REASON_PRICE_ACCEL_60S: str = "price_acceleration_60s"
RADAR_REASON_QUOTE_VOLUME_DELTA_60S: str = "quote_volume_delta_60s"
RADAR_REASON_VOLUME_RANK_JUMP: str = "volume_rank_jump"
RADAR_REASON_SPREAD_COMPRESSION: str = "spread_compression"
RADAR_REASON_MARK_PRICE_ALIGNMENT: str = "mark_price_alignment"
RADAR_REASON_LIQUIDATION_EVENT: str = "liquidation_event"
RADAR_REASON_FUNDING_NOT_OVERHEATED: str = "funding_not_overheated"
RADAR_REASON_INSUFFICIENT_HISTORY: str = "insufficient_history"


# ---------------------------------------------------------------------------
# Radar snapshot
# ---------------------------------------------------------------------------
class AllMarketRadarSnapshot(BaseModel):
    """Per-symbol radar snapshot derived from public WS streams.

    Every field is JSON-safe so the snapshot can be persisted directly
    in an event payload via :meth:`to_payload`. The model is frozen
    once constructed; updates produce a new instance via
    :meth:`model_copy`.

    Field semantics:

      - ``last_price`` / ``price_change_pct_24h`` come from
        ``!ticker@arr`` (or its per-symbol variant).
      - ``price_acceleration_15s`` / ``price_acceleration_60s`` are the
        absolute price change between *now* and the price recorded
        15 / 60 seconds ago, divided by that historical price (i.e.
        a return). The radar buffer maintains the rolling history
        per symbol.
      - ``quote_volume`` / ``quote_volume_delta_60s`` come from
        ``!ticker@arr`` rolling 24h quote volume; the delta is the
        difference between *now* and the value cached 60 s ago.
      - ``volume_rank`` is the per-batch rank of this symbol by
        ``quote_volume`` (1 = largest). ``volume_rank_jump`` is the
        positive integer improvement vs. the previous batch (i.e.
        old_rank - new_rank). ``None`` when no previous rank exists.
      - ``bid`` / ``ask`` / ``spread_pct`` / ``best_bid_qty`` /
        ``best_ask_qty`` come from ``!bookTicker``.
      - ``mark_price`` / ``funding_rate`` come from ``!markPrice@arr``.
      - ``liquidation_event`` is True iff a ``!forceOrder@arr`` event
        for the symbol landed in the current radar window;
        ``liquidation_notional`` is the matched notional of that
        liquidation (sum across all liquidations in the window).
      - ``ws_source_flags`` records which WebSocket streams
        contributed to the snapshot (a sorted list of the
        ``SOURCE_STREAM_*`` tags above).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    timestamp: int
    last_price: float = 0.0
    price_change_pct_24h: float | None = None
    price_acceleration_15s: float | None = None
    price_acceleration_60s: float | None = None
    quote_volume: float | None = None
    quote_volume_delta_60s: float | None = None
    volume_rank: int | None = None
    volume_rank_jump: int | None = None
    bid: float | None = None
    ask: float | None = None
    spread_pct: float | None = None
    best_bid_qty: float | None = None
    best_ask_qty: float | None = None
    mark_price: float | None = None
    funding_rate: float | None = None
    liquidation_event: bool = False
    liquidation_notional: float = 0.0
    ws_source_flags: tuple[str, ...] = Field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        """Render a JSON-safe dict for event payloads."""
        return {
            "symbol": self.symbol,
            "timestamp": int(self.timestamp),
            "last_price": float(self.last_price),
            "price_change_pct_24h": (
                float(self.price_change_pct_24h)
                if self.price_change_pct_24h is not None
                else None
            ),
            "price_acceleration_15s": (
                float(self.price_acceleration_15s)
                if self.price_acceleration_15s is not None
                else None
            ),
            "price_acceleration_60s": (
                float(self.price_acceleration_60s)
                if self.price_acceleration_60s is not None
                else None
            ),
            "quote_volume": (
                float(self.quote_volume)
                if self.quote_volume is not None
                else None
            ),
            "quote_volume_delta_60s": (
                float(self.quote_volume_delta_60s)
                if self.quote_volume_delta_60s is not None
                else None
            ),
            "volume_rank": (
                int(self.volume_rank) if self.volume_rank is not None else None
            ),
            "volume_rank_jump": (
                int(self.volume_rank_jump)
                if self.volume_rank_jump is not None
                else None
            ),
            "bid": float(self.bid) if self.bid is not None else None,
            "ask": float(self.ask) if self.ask is not None else None,
            "spread_pct": (
                float(self.spread_pct)
                if self.spread_pct is not None
                else None
            ),
            "best_bid_qty": (
                float(self.best_bid_qty)
                if self.best_bid_qty is not None
                else None
            ),
            "best_ask_qty": (
                float(self.best_ask_qty)
                if self.best_ask_qty is not None
                else None
            ),
            "mark_price": (
                float(self.mark_price)
                if self.mark_price is not None
                else None
            ),
            "funding_rate": (
                float(self.funding_rate)
                if self.funding_rate is not None
                else None
            ),
            "liquidation_event": bool(self.liquidation_event),
            "liquidation_notional": float(self.liquidation_notional),
            "ws_source_flags": list(self.ws_source_flags),
        }


# ---------------------------------------------------------------------------
# Score result
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RadarScoreResult:
    """Output of :func:`pre_anomaly_score_light`."""

    radar_score: float
    reason_tags: tuple[str, ...]
    source_streams: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "radar_score": float(self.radar_score),
            "reason_tags": list(self.reason_tags),
            "source_streams": list(self.source_streams),
        }


# ---------------------------------------------------------------------------
# Default scoring thresholds
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RadarScoreConfig:
    """Light scoring thresholds.

    The defaults are conservative: the score caps at 100 and a single
    threshold is just enough to pass the relevant reason tag. The
    Phase 11C.1B brief calls these out as inputs / tunables; the
    runner reads them from settings (Phase 11C.1B does NOT add a
    YAML section yet to keep the schema stable, so the defaults
    below are the load-bearing values).
    """

    price_acceleration_15s_threshold: float = 0.005  # 0.5% in 15 s
    price_acceleration_60s_threshold: float = 0.010  # 1.0% in 60 s
    quote_volume_delta_60s_threshold_usdt: float = 100_000.0
    volume_rank_jump_threshold: int = 3
    spread_compression_threshold: float = 0.0008
    mark_price_alignment_tolerance: float = 0.005
    funding_not_overheated_max_abs: float = 0.0005


# ---------------------------------------------------------------------------
# Per-symbol rolling state for the radar buffer
# ---------------------------------------------------------------------------
@dataclass
class _SymbolRadarState:
    """Mutable per-symbol state inside :class:`AllMarketRadarBuffer`."""

    symbol: str
    # (ts_ms, last_price) entries used for price acceleration windows.
    price_history: deque[tuple[int, float]] = field(default_factory=deque)
    # (ts_ms, quote_volume) entries used for quote-volume delta.
    volume_history: deque[tuple[int, float]] = field(default_factory=deque)
    last_price: float = 0.0
    price_change_pct_24h: float | None = None
    quote_volume: float | None = None
    bid: float | None = None
    ask: float | None = None
    spread_pct: float | None = None
    best_bid_qty: float | None = None
    best_ask_qty: float | None = None
    mark_price: float | None = None
    funding_rate: float | None = None
    liquidation_event: bool = False
    liquidation_notional: float = 0.0
    last_message_ts_ms: int = 0
    source_flags: set[str] = field(default_factory=set)
    last_volume_rank: int | None = None
    current_volume_rank: int | None = None


# ---------------------------------------------------------------------------
# Radar buffer
# ---------------------------------------------------------------------------
class AllMarketRadarBuffer:
    """Rolling per-symbol buffer of radar inputs from public WS streams.

    The buffer is single-threaded; the runner calls
    :meth:`ingest_messages` on every loop tick to push the freshly-
    polled WS messages into the buffer, then :meth:`snapshot` to read
    a per-symbol :class:`AllMarketRadarSnapshot`. The buffer trims
    rolling histories per call so long-running deployments do not
    grow unbounded.

    Phase 11C.1B contract:

      - the buffer ACCEPTS only public WS streams (every stream is
        validated through :func:`assert_public_ws_stream_allowed`);
      - the buffer NEVER opens a socket;
      - the buffer NEVER mutates :class:`MarketDataBuffer` (Phase 4).
        Detail / depth / oi / funding still come from REST gated on
        the candidate pool; the radar is a *discovery layer* only.
    """

    DEFAULT_HISTORY_WINDOW_SECONDS: int = 120
    DEFAULT_HISTORY_MAX_SAMPLES: int = 200
    LIQUIDATION_WINDOW_MS: int = 60_000

    def __init__(
        self,
        *,
        history_window_seconds: int = DEFAULT_HISTORY_WINDOW_SECONDS,
        history_max_samples: int = DEFAULT_HISTORY_MAX_SAMPLES,
        clock_fn=now_ms,
    ) -> None:
        if history_window_seconds <= 0:
            raise ValueError("history_window_seconds must be > 0")
        if history_max_samples <= 0:
            raise ValueError("history_max_samples must be > 0")
        self._history_window_ms: int = history_window_seconds * 1000
        self._history_max_samples: int = history_max_samples
        self._clock_fn = clock_fn
        self._state: dict[str, _SymbolRadarState] = {}
        self._messages_consumed: int = 0
        self._liquidation_events_seen: int = 0
        self._last_volume_ranks: dict[str, int] = {}

    # ------------------------------------------------------------------
    @property
    def messages_consumed(self) -> int:
        return self._messages_consumed

    @property
    def liquidation_events_seen(self) -> int:
        return self._liquidation_events_seen

    def known_symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._state.keys()))

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    def ingest_messages(self, messages: Iterable[WSMessage]) -> None:
        """Ingest a batch of :class:`WSMessage`. Order is preserved."""
        for msg in messages:
            self.ingest_message(msg)

    def ingest_message(self, message: WSMessage) -> None:
        """Ingest one :class:`WSMessage`.

        Refuses messages whose ``stream`` is not on the public WS
        allowlist (defence-in-depth: the client already filters but
        the buffer pins the same rule).
        """
        stream = assert_public_ws_stream_allowed(message.stream)
        tag = _stream_to_source_tag(stream)
        if tag is None:
            return
        ts = int(message.received_at_ms or self._clock_fn())
        self._messages_consumed += 1
        if tag == SOURCE_STREAM_TICKER_ARR:
            self._ingest_ticker_arr(message.data, ts=ts)
        elif tag == SOURCE_STREAM_MINI_TICKER_ARR:
            self._ingest_mini_ticker_arr(message.data, ts=ts)
        elif tag == SOURCE_STREAM_BOOK_TICKER:
            self._ingest_book_ticker(message.data, ts=ts)
        elif tag == SOURCE_STREAM_MARK_PRICE_ARR:
            self._ingest_mark_price_arr(message.data, ts=ts)
        elif tag == SOURCE_STREAM_FORCE_ORDER_ARR:
            self._ingest_force_order_arr(message.data, ts=ts)

    # ------------------------------------------------------------------
    # Per-stream parsers (Binance public WS schema)
    # ------------------------------------------------------------------
    def _ingest_ticker_arr(self, data: Any, *, ts: int) -> None:
        rows = data if isinstance(data, list) else [data]
        # We capture the per-batch ranking by quote volume so we can
        # diff against the previous batch and surface ``volume_rank_jump``.
        ranked: list[tuple[str, float]] = []
        for row in rows:
            try:
                symbol = str(row.get("s") or row.get("symbol") or "").upper()
                if not symbol:
                    continue
                last_price = _safe_float(row.get("c") or row.get("lastPrice"))
                price_change_pct = _safe_float(row.get("P"))
                # ``q`` = total traded quote asset volume (24h).
                quote_volume = _safe_float(row.get("q") or row.get("quoteVolume"))
                state = self._get_state(symbol)
                if last_price is not None and last_price > 0:
                    state.last_price = last_price
                    state.price_history.append((ts, last_price))
                    self._trim_history(state.price_history, ts=ts)
                if price_change_pct is not None:
                    # Binance reports as percentage e.g. "1.234"; we
                    # normalise to a fraction (0.01234) so the
                    # snapshot field is a *fraction*, not a percent.
                    state.price_change_pct_24h = price_change_pct / 100.0
                if quote_volume is not None:
                    state.quote_volume = quote_volume
                    state.volume_history.append((ts, quote_volume))
                    self._trim_history(state.volume_history, ts=ts)
                    ranked.append((symbol, quote_volume))
                state.source_flags.add(SOURCE_STREAM_TICKER_ARR)
                state.last_message_ts_ms = ts
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "[phase11c.1b] _ingest_ticker_arr row dropped: {}", exc
                )
        if ranked:
            self._update_volume_ranks(ranked)

    def _ingest_mini_ticker_arr(self, data: Any, *, ts: int) -> None:
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            try:
                symbol = str(row.get("s") or row.get("symbol") or "").upper()
                if not symbol:
                    continue
                last_price = _safe_float(row.get("c"))
                quote_volume = _safe_float(row.get("q"))
                state = self._get_state(symbol)
                if last_price is not None and last_price > 0:
                    state.last_price = last_price
                    state.price_history.append((ts, last_price))
                    self._trim_history(state.price_history, ts=ts)
                if quote_volume is not None:
                    state.quote_volume = quote_volume
                    state.volume_history.append((ts, quote_volume))
                    self._trim_history(state.volume_history, ts=ts)
                state.source_flags.add(SOURCE_STREAM_MINI_TICKER_ARR)
                state.last_message_ts_ms = ts
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "[phase11c.1b] _ingest_mini_ticker_arr row dropped: {}",
                    exc,
                )

    def _ingest_book_ticker(self, data: Any, *, ts: int) -> None:
        # ``!bookTicker`` is a single object per push; per-symbol
        # ``btcusdt@bookTicker`` is also a single object. We accept
        # both shapes and a list-wrapped variant for robustness.
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            try:
                symbol = str(row.get("s") or row.get("symbol") or "").upper()
                if not symbol:
                    continue
                bid = _safe_float(row.get("b") or row.get("bidPrice"))
                ask = _safe_float(row.get("a") or row.get("askPrice"))
                bid_qty = _safe_float(row.get("B"))
                ask_qty = _safe_float(row.get("A"))
                state = self._get_state(symbol)
                if bid is not None and bid > 0:
                    state.bid = bid
                if ask is not None and ask > 0:
                    state.ask = ask
                if state.bid is not None and state.ask is not None and state.ask > 0:
                    state.spread_pct = max(
                        (state.ask - state.bid) / state.ask, 0.0
                    )
                if bid_qty is not None and bid_qty >= 0:
                    state.best_bid_qty = bid_qty
                if ask_qty is not None and ask_qty >= 0:
                    state.best_ask_qty = ask_qty
                state.source_flags.add(SOURCE_STREAM_BOOK_TICKER)
                state.last_message_ts_ms = ts
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "[phase11c.1b] _ingest_book_ticker row dropped: {}", exc
                )

    def _ingest_mark_price_arr(self, data: Any, *, ts: int) -> None:
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            try:
                symbol = str(row.get("s") or row.get("symbol") or "").upper()
                if not symbol:
                    continue
                mark = _safe_float(row.get("p") or row.get("markPrice"))
                funding = _safe_float(
                    row.get("r") or row.get("lastFundingRate")
                )
                state = self._get_state(symbol)
                if mark is not None and mark > 0:
                    state.mark_price = mark
                if funding is not None:
                    state.funding_rate = funding
                state.source_flags.add(SOURCE_STREAM_MARK_PRICE_ARR)
                state.last_message_ts_ms = ts
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "[phase11c.1b] _ingest_mark_price_arr row dropped: {}",
                    exc,
                )

    def _ingest_force_order_arr(self, data: Any, *, ts: int) -> None:
        # ``!forceOrder@arr`` ships a single object with an inner ``o``
        # block. Per-symbol ``btcusdt@forceOrder@1s`` is the same shape.
        rows = data if isinstance(data, list) else [data]
        for row in rows:
            try:
                inner = row.get("o") if isinstance(row, dict) else None
                if not isinstance(inner, dict):
                    inner = row if isinstance(row, dict) else {}
                symbol = str(inner.get("s") or inner.get("symbol") or "").upper()
                if not symbol:
                    continue
                price = _safe_float(inner.get("p") or inner.get("price"))
                qty = _safe_float(inner.get("q") or inner.get("origQty"))
                notional = 0.0
                if price is not None and qty is not None:
                    notional = float(price) * float(qty)
                state = self._get_state(symbol)
                state.liquidation_event = True
                state.liquidation_notional += notional
                state.source_flags.add(SOURCE_STREAM_FORCE_ORDER_ARR)
                state.last_message_ts_ms = ts
                self._liquidation_events_seen += 1
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "[phase11c.1b] _ingest_force_order_arr row dropped: {}",
                    exc,
                )

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------
    def snapshot(self, symbol: str) -> AllMarketRadarSnapshot | None:
        state = self._state.get(symbol.upper())
        if state is None:
            return None
        ts = int(self._clock_fn())
        # Roll the liquidation event off after the configured window.
        if state.liquidation_event and (
            ts - state.last_message_ts_ms > self.LIQUIDATION_WINDOW_MS
        ):
            state.liquidation_event = False
            state.liquidation_notional = 0.0
        accel_15s = self._compute_acceleration(state.price_history, ts=ts, lookback_ms=15_000)
        accel_60s = self._compute_acceleration(state.price_history, ts=ts, lookback_ms=60_000)
        qv_delta_60s = self._compute_volume_delta(state.volume_history, ts=ts, lookback_ms=60_000)
        rank_jump: int | None = None
        if state.last_volume_rank is not None and state.current_volume_rank is not None:
            rank_jump = int(state.last_volume_rank - state.current_volume_rank)
        return AllMarketRadarSnapshot(
            symbol=state.symbol,
            timestamp=ts,
            last_price=float(state.last_price or 0.0),
            price_change_pct_24h=state.price_change_pct_24h,
            price_acceleration_15s=accel_15s,
            price_acceleration_60s=accel_60s,
            quote_volume=state.quote_volume,
            quote_volume_delta_60s=qv_delta_60s,
            volume_rank=state.current_volume_rank,
            volume_rank_jump=rank_jump,
            bid=state.bid,
            ask=state.ask,
            spread_pct=state.spread_pct,
            best_bid_qty=state.best_bid_qty,
            best_ask_qty=state.best_ask_qty,
            mark_price=state.mark_price,
            funding_rate=state.funding_rate,
            liquidation_event=state.liquidation_event,
            liquidation_notional=float(state.liquidation_notional),
            ws_source_flags=tuple(sorted(state.source_flags)),
        )

    def all_snapshots(self) -> list[AllMarketRadarSnapshot]:
        out: list[AllMarketRadarSnapshot] = []
        for sym in sorted(self._state.keys()):
            snap = self.snapshot(sym)
            if snap is not None:
                out.append(snap)
        return out

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_state(self, symbol: str) -> _SymbolRadarState:
        symbol = symbol.upper()
        state = self._state.get(symbol)
        if state is None:
            state = _SymbolRadarState(symbol=symbol)
            self._state[symbol] = state
        return state

    def _trim_history(
        self,
        history: deque[tuple[int, float]],
        *,
        ts: int,
    ) -> None:
        cutoff = ts - self._history_window_ms
        while history and history[0][0] < cutoff:
            history.popleft()
        while len(history) > self._history_max_samples:
            history.popleft()

    def _compute_acceleration(
        self,
        history: deque[tuple[int, float]],
        *,
        ts: int,
        lookback_ms: int,
    ) -> float | None:
        if len(history) < 2:
            return None
        target_ts = ts - int(lookback_ms)
        # Find the most recent sample at-or-before ``target_ts``: that
        # is the price ``lookback_ms`` ms ago. We iterate forward
        # because the deque is ordered oldest-to-newest.
        baseline_price: float | None = None
        for sample_ts, price in history:
            if sample_ts <= target_ts:
                baseline_price = price
            else:
                break
        if baseline_price is None:
            # No sample is old enough to anchor the lookback. Use the
            # oldest sample we have IF it is at least half the
            # lookback old; otherwise return None (insufficient
            # history). This keeps short-burst tests deterministic
            # without inventing acceleration out of thin air.
            oldest_ts, oldest_price = history[0]
            if ts - oldest_ts >= int(lookback_ms) // 2:
                baseline_price = oldest_price
        if baseline_price is None or baseline_price <= 0:
            return None
        latest_price = history[-1][1]
        if latest_price <= 0:
            return None
        return float((latest_price - baseline_price) / baseline_price)

    def _compute_volume_delta(
        self,
        history: deque[tuple[int, float]],
        *,
        ts: int,
        lookback_ms: int,
    ) -> float | None:
        if len(history) < 2:
            return None
        target_ts = ts - int(lookback_ms)
        baseline_volume: float | None = None
        for sample_ts, vol in history:
            if sample_ts <= target_ts:
                baseline_volume = vol
            else:
                break
        if baseline_volume is None:
            oldest_ts, oldest_volume = history[0]
            if ts - oldest_ts >= int(lookback_ms) // 2:
                baseline_volume = oldest_volume
        if baseline_volume is None:
            return None
        latest_volume = history[-1][1]
        return float(latest_volume - baseline_volume)

    def _update_volume_ranks(self, ranked: list[tuple[str, float]]) -> None:
        ranked_sorted = sorted(ranked, key=lambda r: r[1], reverse=True)
        # We rank only the symbols in *this* batch; symbols absent from
        # the batch keep their previous rank so a flicker does not
        # spuriously flag a rank jump.
        for index, (symbol, _vol) in enumerate(ranked_sorted, start=1):
            state = self._get_state(symbol)
            state.last_volume_rank = state.current_volume_rank
            state.current_volume_rank = index


# ---------------------------------------------------------------------------
# Light pre-anomaly score
# ---------------------------------------------------------------------------
def pre_anomaly_score_light(
    snapshot: AllMarketRadarSnapshot,
    *,
    config: RadarScoreConfig | None = None,
) -> RadarScoreResult:
    """Return a light pre-anomaly score for ``snapshot``.

    The score is additive and capped at 100. Each contributing tag
    adds a deterministic weight; tags whose threshold is not crossed
    are NOT included in the result. The function is a *pure* function
    of the snapshot + the threshold config so the same snapshot
    always produces the same score.

    Inputs the brief calls out:

      - price_acceleration_15s
      - price_acceleration_60s
      - quote_volume_delta_60s
      - volume_rank_jump
      - spread_compression
      - mark_price_alignment
      - liquidation_event
      - funding_not_overheated
    """
    cfg = config or RadarScoreConfig()
    score = 0.0
    tags: list[str] = []

    accel_15s = snapshot.price_acceleration_15s
    accel_60s = snapshot.price_acceleration_60s
    if accel_15s is not None and abs(accel_15s) >= cfg.price_acceleration_15s_threshold:
        tags.append(RADAR_REASON_PRICE_ACCEL_15S)
        score += min(40.0, abs(accel_15s) * 1000.0)
    if accel_60s is not None and abs(accel_60s) >= cfg.price_acceleration_60s_threshold:
        tags.append(RADAR_REASON_PRICE_ACCEL_60S)
        score += min(20.0, abs(accel_60s) * 500.0)
    if (
        snapshot.quote_volume_delta_60s is not None
        and snapshot.quote_volume_delta_60s
        >= cfg.quote_volume_delta_60s_threshold_usdt
    ):
        tags.append(RADAR_REASON_QUOTE_VOLUME_DELTA_60S)
        score += 15.0
    if (
        snapshot.volume_rank_jump is not None
        and snapshot.volume_rank_jump >= cfg.volume_rank_jump_threshold
    ):
        tags.append(RADAR_REASON_VOLUME_RANK_JUMP)
        score += min(20.0, float(snapshot.volume_rank_jump) * 2.0)
    if (
        snapshot.spread_pct is not None
        and snapshot.spread_pct > 0.0
        and snapshot.spread_pct <= cfg.spread_compression_threshold
    ):
        tags.append(RADAR_REASON_SPREAD_COMPRESSION)
        score += 5.0
    if (
        snapshot.mark_price is not None
        and snapshot.last_price is not None
        and snapshot.last_price > 0
    ):
        diff = abs(snapshot.mark_price - snapshot.last_price) / snapshot.last_price
        if diff <= cfg.mark_price_alignment_tolerance:
            tags.append(RADAR_REASON_MARK_PRICE_ALIGNMENT)
            score += 5.0
    if snapshot.liquidation_event:
        tags.append(RADAR_REASON_LIQUIDATION_EVENT)
        score += 10.0
    if (
        snapshot.funding_rate is not None
        and abs(snapshot.funding_rate) <= cfg.funding_not_overheated_max_abs
    ):
        tags.append(RADAR_REASON_FUNDING_NOT_OVERHEATED)
        score += 5.0
    if not tags:
        tags.append(RADAR_REASON_INSUFFICIENT_HISTORY)
    score = max(0.0, min(score, 100.0))
    return RadarScoreResult(
        radar_score=float(score),
        reason_tags=tuple(tags),
        source_streams=tuple(snapshot.ws_source_flags),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "ALL_SOURCE_STREAM_TAGS",
    "AllMarketRadarBuffer",
    "AllMarketRadarSnapshot",
    "RADAR_REASON_FUNDING_NOT_OVERHEATED",
    "RADAR_REASON_INSUFFICIENT_HISTORY",
    "RADAR_REASON_LIQUIDATION_EVENT",
    "RADAR_REASON_MARK_PRICE_ALIGNMENT",
    "RADAR_REASON_PRICE_ACCEL_15S",
    "RADAR_REASON_PRICE_ACCEL_60S",
    "RADAR_REASON_QUOTE_VOLUME_DELTA_60S",
    "RADAR_REASON_SPREAD_COMPRESSION",
    "RADAR_REASON_VOLUME_RANK_JUMP",
    "RadarScoreConfig",
    "RadarScoreResult",
    "SOURCE_STREAM_BOOK_TICKER",
    "SOURCE_STREAM_FORCE_ORDER_ARR",
    "SOURCE_STREAM_MARK_PRICE_ARR",
    "SOURCE_STREAM_MINI_TICKER_ARR",
    "SOURCE_STREAM_TICKER_ARR",
    "pre_anomaly_score_light",
]
