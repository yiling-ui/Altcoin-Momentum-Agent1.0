"""Phase 4 Market Data Buffer value objects (Spec §11.1, §14).

Phase 4 keeps every model frozen and forbids extra fields, so the
contract between the Buffer and its callers is auditable. The
``MarketSnapshot`` itself lives in :mod:`app.core.models` (Phase 1
ships the Spec §11.1 shape); this module ships only the supporting
types that the Buffer needs internally.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------------------
# Bar / candle representation
# ---------------------------------------------------------------------------
class BarInterval(str, Enum):
    """Bar widths supported in Phase 4.

    Phase 4 requires 1-minute bars (Spec §14, Issue #4). 5-minute bars
    are computed by aggregating 1-minute bars in :class:`CandleBuilder`.
    No higher timeframe is shipped; Issue #5 / #6 will add 15m / 1h as
    needed.
    """

    M1 = "1m"
    M5 = "5m"

    @property
    def width_ms(self) -> int:
        if self is BarInterval.M1:
            return 60 * 1000
        if self is BarInterval.M5:
            return 5 * 60 * 1000
        raise ValueError(f"Unsupported BarInterval {self}")


class Bar(_Frozen):
    """One OHLCV bar produced by :class:`CandleBuilder`.

    The bar is *closed* once the next bar's open timestamp is observed.
    The `closed` flag is True only for closed bars; the live bar that
    is still receiving trades has `closed=False`.
    """

    symbol: str
    interval: BarInterval
    open_ts: int  # ms; bar start (inclusive)
    close_ts: int  # ms; bar end (exclusive)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    # Aggregate buy / sell volume (taker side). Used by CVD.
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    trade_count: int = 0
    closed: bool = False

    @field_validator("close_ts")
    @classmethod
    def _validate_close_after_open(cls, v: int, info) -> int:
        open_ts = info.data.get("open_ts")
        if open_ts is not None and v <= open_ts:
            raise ValueError("close_ts must be strictly greater than open_ts")
        return v


# ---------------------------------------------------------------------------
# Liquidation feed (skeleton, Issue #4 §"liquidation.py")
# ---------------------------------------------------------------------------
class LiquidationSide(str, Enum):
    LONG = "long"
    SHORT = "short"


class LiquidationEvent(_Frozen):
    """A single liquidation event from the exchange.

    Phase 4 does NOT subscribe to a real liquidation stream. This model
    exists so test fixtures and later phases (Issue #6 - Liquidation
    Spike anomaly, Issue #7 - circuit breaker) have a stable shape to
    consume. Only callers that explicitly hand the buffer a
    `LiquidationEvent` will see one in the buffer state.
    """

    symbol: str
    timestamp: int
    side: LiquidationSide
    price: float
    qty: float
    notional: float | None = None


# ---------------------------------------------------------------------------
# Buffer configuration
# ---------------------------------------------------------------------------
class MarketDataStalenessConfig(_Frozen):
    """How long each data surface may be silent before the buffer
    declares itself ``degraded``.

    All thresholds are in milliseconds. The defaults are deliberately
    generous; tests override them with much smaller values to exercise
    transitions deterministically.
    """

    trades_max_silence_ms: int = 60 * 1000  # 1 minute
    orderbook_max_silence_ms: int = 30 * 1000
    oi_max_silence_ms: int = 10 * 60 * 1000  # 10 minutes
    funding_max_silence_ms: int = 10 * 60 * 1000


class MarketDataBufferConfig(_Frozen):
    """Top-level Phase 4 buffer configuration.

    Only fields actually used by the buffer are exposed; we avoid
    leaking strategy-level thresholds (those land with Issue #5 / #6
    config blocks).
    """

    # Rolling-window widths in milliseconds.
    trades_window_1m_ms: int = 60 * 1000
    trades_window_5m_ms: int = 5 * 60 * 1000
    trades_window_15m_ms: int = 15 * 60 * 1000

    # Number of closed 1m bars retained for ATR / aggregation.
    bar_history_size: int = 240  # 4 hours at 1m

    # ATR window (in number of closed 1m bars).
    atr_window_1m: int = 14
    atr_window_5m: int = 14

    # Liquidation history retained for downstream consumers.
    liquidation_history_size: int = 256

    # Whether ``MarketDataBuffer.snapshot()`` should APPEND a
    # ``MARKET_SNAPSHOT`` event to ``events.db`` by default. Phase 4
    # callers (boot self-check, ad-hoc tests) snapshot at most a handful
    # of times so the default is True. Phase 5+ consumers (anomaly
    # scanner, regime engine) may call ``snapshot()`` at a high cadence;
    # they should either pass ``emit_event=False`` per call OR construct
    # the buffer with this flag set to False. This is the throttle hook
    # the Phase 4 review asked for - it lets ``events.db`` stay
    # bounded under high-frequency snapshotting without changing the
    # MarketSnapshot return type.
    market_snapshot_event_emit_enabled: bool = True

    staleness: MarketDataStalenessConfig = Field(
        default_factory=MarketDataStalenessConfig
    )


# ---------------------------------------------------------------------------
# Buffer book-keeping
# ---------------------------------------------------------------------------
class MarketDataDegradedReason(str, Enum):
    """Why a per-symbol view of the buffer is currently ``degraded``.

    Multiple reasons can be active at once; the buffer reports the set.
    Spec §14.2 + §31 mandate that a degraded view must NOT feed any
    decision module by default.
    """

    NEVER_INITIALISED = "never_initialised"
    EXCHANGE_DISCONNECTED = "exchange_disconnected"
    EXCHANGE_DEGRADED = "exchange_degraded"
    TRADES_STALE = "trades_stale"
    ORDERBOOK_STALE = "orderbook_stale"
    OI_STALE = "oi_stale"
    FUNDING_STALE = "funding_stale"
    REST_WS_CONFLICT = "rest_ws_conflict"
    EXPLICIT_MARK = "explicit_mark"


class BufferStats(_Frozen):
    """Lightweight observability snapshot.

    Exposed via :meth:`MarketDataBuffer.stats` so the entrypoint banner
    and the monitoring skeleton can show at a glance how many symbols
    are tracked, how many are currently degraded, and how many
    DATA_UNRELIABLE events have been emitted since boot.
    """

    symbols_tracked: int = 0
    symbols_degraded: int = 0
    data_unreliable_events_emitted: int = 0
    market_snapshot_events_emitted: int = 0
    market_snapshot_events_skipped: int = 0
    rest_ws_conflicts_total: int = 0
    # Cumulative count of trades the CandleBuilder rejected because
    # their bucket had already closed. Spec §14.2 forbids silent
    # back-filling; a non-zero value here is a leading indicator of an
    # out-of-order tape (mis-ordered REST replay, inverted aggTrade
    # delivery, or a clock-skew bug in the producer). Issue #5 / #6
    # monitoring will alert on this.
    late_trades_dropped_total: int = 0
