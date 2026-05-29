"""Historical Market Store v0 for Phase 11C.1D-D-B (PR95).

Strict blind walk-forward historical market data store. This module is
the **second** anti-future-lookahead infrastructure block of the strict
blind walk-forward stack defined by Phase 11C.1D-D (the *Strict Blind
Walk-forward Sim-Live Constitution*, PR93). It builds on top of the
PR94 substrate (:class:`SimulationClock`,
:class:`HistoricalRecordTime`, :class:`TimeWallGuard`,
:class:`CandleVisibilityGuard`, :class:`NoLookaheadViolation`).

Constitution §5: every historical record MUST distinguish four
timestamps - ``event_time`` / ``available_at`` / ``ingested_at`` /
``source``. At simulated time ``T``, the system MAY only read records
whose ``available_at <= T``. ``ingested_at`` is NEVER a substitute for
``available_at``.

Constitution §6: a 1m / 5m / longer-period candle's final OHLCV
(``high`` / ``low`` / ``close`` / ``volume``) is fully visible only
after that candle has closed. The Historical Market Store rejects
final-OHLCV reads on unclosed candles.

Constitution §9: as-of universe queries MUST NOT use the *current*
symbol list to reconstruct the past. Survivorship bias is forbidden.
A symbol is in the as-of universe at ``T`` iff it has a
:class:`SymbolStatusRecord` with ``listed_at <= T`` AND
(``delisted_at is None`` OR ``delisted_at > T``) AND
``available_at <= T`` AND a tradable / monitorable ``status``.

Hard safety boundary (Phase 11C.1D-D-B / PR95):

  - mode = paper
  - sandbox_only = True
  - live_trading = False
  - exchange_live_orders = False
  - binance_private_api_enabled = False
  - signed_endpoint_reachable = False
  - private_websocket_reachable = False
  - account_endpoint_reachable = False
  - order_endpoint_reachable = False
  - position_endpoint_reachable = False
  - leverage_endpoint_reachable = False
  - margin_endpoint_reachable = False
  - real_exchange_order_path = False
  - real_capital = False
  - telegram_outbound_enabled = False
  - telegram_live_command_authority = False
  - ai_trade_authority = False
  - trade_authority = False
  - auto_tuning_allowed = False
  - phase_12_forbidden = True

This module MUST NOT and CANNOT:

  - import app.risk / app.execution / app.exchanges / app.telegram /
    app.config
  - call DeepSeek / LLM / Telegram / Binance private API / any
    network
  - place an order
  - emit buy / sell / long / short / direction / entry / exit /
    position_size / leverage / stop / stop_loss / target /
    take_profit / risk_budget / order / execution_command
  - emit any runtime_config_patch / threshold_patch /
    symbol_limit_patch / candidate_pool_patch / regime_weight_patch /
    strategy_parameter_patch / signal_to_trade / should_buy /
    should_short / apply_change / deploy_change / enable_live /
    live_ready / trading_approved
  - authorize live trading or auto-tuning
  - enter Phase 12

This module does NOT and CANNOT:

  - implement the ReplayFeedProvider (PR96's responsibility),
  - implement the MockExchange + Pessimistic Fill Model (PR97's
    responsibility),
  - implement the Simulated Capital Flow + Trade Ledger (PR98's
    responsibility),
  - implement the Telegram Sandbox Outbox (PR99's responsibility),
  - implement the Blind Walk-forward Runner (PR100's responsibility),
  - read real market network,
  - tune any parameter or rule.

PR95 acceptance only authorises **PR96 - ReplayFeedProvider** to
begin its own gate. It does NOT authorise PR97 / PR98 / PR99 / PR100,
live trading, auto-tuning, the DeepSeek hot path, Telegram live
outbound, or Phase 12. Phase 12 remains FORBIDDEN.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import (
    Any,
    Dict,
    FrozenSet,
    Iterable,
    List,
    Mapping,
    Optional,
    Tuple,
    Union,
)

from app.sim.simulation_clock import (
    HistoricalRecordTime,
    ensure_utc_aware,
    parse_interval_seconds,
)
from app.sim.time_wall_guard import (
    CandleVisibilityGuard,
    NoLookaheadViolation,
    NoLookaheadViolationReason,
    TimeWallGuard,
    assert_no_forbidden_fields,
)


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

PHASE_NAME: str = (
    "Phase 11C.1D-D-B / PR95 / Historical Market Store v0"
)


# ---------------------------------------------------------------------------
# Closed taxonomies
# ---------------------------------------------------------------------------


class HistoricalMarketRecordType:
    """Closed taxonomy of historical market record types (v0).

    Constitution §10: v0 minimum scope is 1m / 5m kline, funding rate,
    open interest, 24h ticker, exchangeInfo, listing / delisting
    timeline. High-fidelity tick / orderbook is deferred.
    """

    KLINE_1M: str = "KLINE_1M"
    KLINE_5M: str = "KLINE_5M"
    FUNDING_RATE: str = "FUNDING_RATE"
    OPEN_INTEREST: str = "OPEN_INTEREST"
    TICKER_24H: str = "TICKER_24H"
    EXCHANGE_INFO: str = "EXCHANGE_INFO"
    SYMBOL_STATUS: str = "SYMBOL_STATUS"
    LISTING_STATUS: str = "LISTING_STATUS"
    DELISTING_STATUS: str = "DELISTING_STATUS"

    ALLOWED: FrozenSet[str] = frozenset(
        {
            KLINE_1M,
            KLINE_5M,
            FUNDING_RATE,
            OPEN_INTEREST,
            TICKER_24H,
            EXCHANGE_INFO,
            SYMBOL_STATUS,
            LISTING_STATUS,
            DELISTING_STATUS,
        }
    )

    KLINE_TYPES: FrozenSet[str] = frozenset({KLINE_1M, KLINE_5M})

    SYMBOL_STATUS_TYPES: FrozenSet[str] = frozenset(
        {SYMBOL_STATUS, LISTING_STATUS, DELISTING_STATUS}
    )


# Mapping from kline interval string to record_type. v0 supports only
# 1m and 5m kline record types (Constitution §10).
_INTERVAL_TO_KLINE_RECORD_TYPE: Dict[str, str] = {
    "1m": HistoricalMarketRecordType.KLINE_1M,
    "5m": HistoricalMarketRecordType.KLINE_5M,
}


class DataQualityFlag:
    """Closed taxonomy of historical record data-quality flags."""

    DATA_GAP: str = "DATA_GAP"
    LATE_ARRIVAL: str = "LATE_ARRIVAL"
    REVISED_RECORD: str = "REVISED_RECORD"
    INCOMPLETE_KLINE: str = "INCOMPLETE_KLINE"
    SYMBOL_STATUS_UNKNOWN: str = "SYMBOL_STATUS_UNKNOWN"
    FUNDING_MISSING: str = "FUNDING_MISSING"
    OI_MISSING: str = "OI_MISSING"
    TICKER_MISSING: str = "TICKER_MISSING"

    ALLOWED: FrozenSet[str] = frozenset(
        {
            DATA_GAP,
            LATE_ARRIVAL,
            REVISED_RECORD,
            INCOMPLETE_KLINE,
            SYMBOL_STATUS_UNKNOWN,
            FUNDING_MISSING,
            OI_MISSING,
            TICKER_MISSING,
        }
    )


class SymbolStatus:
    """Closed taxonomy of symbol statuses recognised by the as-of
    universe query.

    The ``TRADABLE_OR_MONITORABLE`` subset is the set of statuses that
    qualify a symbol for inclusion in the as-of universe. ``DELISTED``
    is explicitly excluded from the as-of universe; a delisted symbol
    is recorded for audit but is never tradable / monitorable.
    """

    TRADING: str = "TRADING"
    BREAK: str = "BREAK"
    HALT: str = "HALT"
    DELISTED: str = "DELISTED"
    SETTLING: str = "SETTLING"
    PRE_TRADING: str = "PRE_TRADING"
    UNKNOWN: str = "UNKNOWN"

    ALLOWED: FrozenSet[str] = frozenset(
        {
            TRADING,
            BREAK,
            HALT,
            DELISTED,
            SETTLING,
            PRE_TRADING,
            UNKNOWN,
        }
    )

    TRADABLE_OR_MONITORABLE: FrozenSet[str] = frozenset(
        {TRADING, BREAK, HALT, SETTLING, PRE_TRADING}
    )


class DataCompletenessState:
    """Closed taxonomy of symbol-level data completeness states."""

    OK: str = "OK"
    DEGRADED: str = "DEGRADED"
    INCOMPLETE: str = "INCOMPLETE"
    UNKNOWN: str = "UNKNOWN"

    ALLOWED: FrozenSet[str] = frozenset(
        {OK, DEGRADED, INCOMPLETE, UNKNOWN}
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _maybe_utc_aware(
    value: Optional[datetime], name: str
) -> Optional[datetime]:
    if value is None:
        return None
    return ensure_utc_aware(value, name)


def _check_data_quality_flags(flags: Iterable[str]) -> Tuple[str, ...]:
    out: List[str] = []
    for f in flags:
        if not isinstance(f, str):
            raise TypeError(
                f"data_quality_flag must be a string, got {type(f)!r}"
            )
        if f not in DataQualityFlag.ALLOWED:
            raise ValueError(
                f"data_quality_flag {f!r} not in closed taxonomy "
                f"{sorted(DataQualityFlag.ALLOWED)}"
            )
        out.append(f)
    # Deterministic, order-preserving (no duplicates).
    seen = set()
    deduped: List[str] = []
    for f in out:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    return tuple(deduped)


def _check_evidence_refs(refs: Iterable[Any]) -> Tuple[str, ...]:
    out: List[str] = []
    for r in refs:
        if not isinstance(r, str):
            raise TypeError(
                f"evidence_refs entries must be strings, got "
                f"{type(r)!r}"
            )
        out.append(r)
    return tuple(out)


def _validated_payload(payload: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise TypeError(
            f"payload must be a Mapping or None, got {type(payload)!r}"
        )
    pl: Dict[str, Any] = copy.deepcopy(dict(payload))
    # Defensive: refuse any forbidden field name at any nesting depth.
    assert_no_forbidden_fields(pl)
    # JSON-serialisable.
    try:
        json.dumps(pl, sort_keys=True, default=_json_default)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"payload must be JSON serialisable: {exc}"
        ) from exc
    return pl


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(
        f"Object of type {type(obj)!r} is not JSON serialisable"
    )


def _safety_payload() -> Dict[str, Any]:
    """Return the project-wide safety boundary payload.

    This payload is re-pinned on every record / store ``to_dict()``
    boundary so that no payload can ever be misread as authorising
    live trading, auto-tuning, or Phase 12.
    """
    return {
        "phase": PHASE_NAME,
        "mode": "paper",
        "sandbox_only": True,
        "live_trading": False,
        "exchange_live_orders": False,
        "binance_private_api_enabled": False,
        "signed_endpoint_reachable": False,
        "private_websocket_reachable": False,
        "account_endpoint_reachable": False,
        "order_endpoint_reachable": False,
        "position_endpoint_reachable": False,
        "leverage_endpoint_reachable": False,
        "margin_endpoint_reachable": False,
        "real_exchange_order_path": False,
        "real_capital": False,
        "telegram_outbound_enabled": False,
        "telegram_live_command_authority": False,
        "ai_trade_authority": False,
        "trade_authority": False,
        "auto_tuning_allowed": False,
        "phase_12_forbidden": True,
        # Defensive non-trade markers:
        "is_historical_market_store_payload": True,
        "is_trade": False,
        "is_runtime_patch": False,
    }


# ---------------------------------------------------------------------------
# HistoricalMarketRecord
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoricalMarketRecord:
    """A single historical market record (non-kline shape).

    Carries the four-timestamp record-time model of Constitution §5
    and a typed payload. Kline records have their own dedicated type
    (:class:`HistoricalKlineRecord`); symbol metadata records have
    their own dedicated type (:class:`SymbolStatusRecord`).

    Hard rules:

      * ``event_time`` / ``available_at`` are required and timezone-
        aware UTC. ``ingested_at`` and ``revision_time`` are optional
        and, when set, also timezone-aware UTC.
      * ``available_at >= event_time`` is enforced at construction
        time. ``ingested_at`` is NEVER a substitute for
        ``available_at`` (see :class:`TimeWallGuard`).
      * ``record_type`` must be one of
        :data:`HistoricalMarketRecordType.ALLOWED`.
      * ``data_quality_flags`` must be a subset of the closed
        :class:`DataQualityFlag` taxonomy.
      * ``payload`` MUST be JSON-serialisable AND MUST NOT contain any
        of :data:`FORBIDDEN_OUTPUT_FIELDS` at any nesting depth.
    """

    record_id: str
    record_type: str
    symbol: Optional[str]
    event_time: datetime
    available_at: datetime
    ingested_at: Optional[datetime] = None
    source: Optional[str] = None
    interval: Optional[str] = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    data_quality_flags: Tuple[str, ...] = ()
    evidence_refs: Tuple[str, ...] = ()
    revision_time: Optional[datetime] = None
    revised_from_record_id: Optional[str] = None
    late_arrival: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, str) or not self.record_id:
            raise ValueError("record_id must be a non-empty string")
        if self.record_type not in HistoricalMarketRecordType.ALLOWED:
            raise ValueError(
                f"record_type must be one of "
                f"{sorted(HistoricalMarketRecordType.ALLOWED)}, got "
                f"{self.record_type!r}"
            )
        if self.symbol is not None and (
            not isinstance(self.symbol, str) or not self.symbol
        ):
            raise ValueError("symbol must be a non-empty string or None")
        ev = ensure_utc_aware(self.event_time, "event_time")
        avail = ensure_utc_aware(self.available_at, "available_at")
        ing = _maybe_utc_aware(self.ingested_at, "ingested_at")
        rev = _maybe_utc_aware(self.revision_time, "revision_time")
        if avail < ev:
            raise ValueError(
                "available_at must be >= event_time (a record cannot "
                "be available before its event_time)"
            )
        if self.interval is not None:
            parse_interval_seconds(self.interval)
        flags = _check_data_quality_flags(self.data_quality_flags)
        refs = _check_evidence_refs(self.evidence_refs)
        pl = _validated_payload(self.payload)
        if not isinstance(self.late_arrival, bool):
            raise TypeError(
                f"late_arrival must be bool, got {type(self.late_arrival)!r}"
            )
        if self.revised_from_record_id is not None and (
            not isinstance(self.revised_from_record_id, str)
            or not self.revised_from_record_id
        ):
            raise ValueError(
                "revised_from_record_id must be a non-empty string or None"
            )
        object.__setattr__(self, "event_time", ev)
        object.__setattr__(self, "available_at", avail)
        object.__setattr__(self, "ingested_at", ing)
        object.__setattr__(self, "revision_time", rev)
        object.__setattr__(self, "data_quality_flags", flags)
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "payload", pl)

    def to_record_time(self) -> HistoricalRecordTime:
        """Build a :class:`HistoricalRecordTime` from this record.

        The :class:`HistoricalMarketStore` consumes this when calling
        :class:`TimeWallGuard` to enforce the
        ``available_at <= simulated_time`` rule.
        """
        return HistoricalRecordTime(
            event_time=self.event_time,
            available_at=self.available_at,
            ingested_at=self.ingested_at,
            source=self.source,
            record_id=self.record_id,
            symbol=self.symbol,
            interval=self.interval,
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "symbol": self.symbol,
            "event_time": self.event_time.isoformat(),
            "available_at": self.available_at.isoformat(),
            "ingested_at": (
                self.ingested_at.isoformat()
                if self.ingested_at is not None
                else None
            ),
            "source": self.source,
            "interval": self.interval,
            "payload": copy.deepcopy(dict(self.payload)),
            "data_quality_flags": list(self.data_quality_flags),
            "evidence_refs": list(self.evidence_refs),
            "revision_time": (
                self.revision_time.isoformat()
                if self.revision_time is not None
                else None
            ),
            "revised_from_record_id": self.revised_from_record_id,
            "late_arrival": self.late_arrival,
            "is_historical_market_record": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# HistoricalKlineRecord
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoricalKlineRecord:
    """A single historical OHLCV kline record.

    Constitution §6: a 1m / 5m / longer-period candle's final OHLCV
    (``high`` / ``low`` / ``close`` / ``volume``) is fully visible
    only after that candle has closed. The record's ``available_at``
    therefore MUST be >= ``close_time``. The
    :class:`HistoricalMarketStore` cross-checks this against
    :class:`CandleVisibilityGuard` on every kline query.
    """

    symbol: str
    interval: str
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    available_at: datetime
    close_time: Optional[datetime] = None
    event_time: Optional[datetime] = None
    ingested_at: Optional[datetime] = None
    source: Optional[str] = None
    record_id: Optional[str] = None
    data_quality_flags: Tuple[str, ...] = ()
    evidence_refs: Tuple[str, ...] = ()
    revision_time: Optional[datetime] = None
    revised_from_record_id: Optional[str] = None
    late_arrival: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("symbol must be a non-empty string")
        if self.interval not in _INTERVAL_TO_KLINE_RECORD_TYPE:
            raise ValueError(
                f"v0 kline interval must be one of "
                f"{sorted(_INTERVAL_TO_KLINE_RECORD_TYPE)}, got "
                f"{self.interval!r}"
            )
        seconds = parse_interval_seconds(self.interval)
        ot = ensure_utc_aware(self.open_time, "open_time")
        expected_close = ot + timedelta(seconds=seconds)
        if self.close_time is None:
            ct = expected_close
        else:
            ct = ensure_utc_aware(self.close_time, "close_time")
            if ct != expected_close:
                raise ValueError(
                    f"close_time must equal open_time + interval "
                    f"({expected_close.isoformat()}), got "
                    f"{ct.isoformat()}"
                )
        avail = ensure_utc_aware(self.available_at, "available_at")
        ev = (
            ensure_utc_aware(self.event_time, "event_time")
            if self.event_time is not None
            else ot
        )
        if ev > ct:
            raise ValueError(
                "kline event_time must be within the candle window "
                "[open_time, close_time]"
            )
        # Constitution §6: the final OHLCV is invisible before close.
        # Therefore available_at MUST be >= close_time.
        if avail < ct:
            raise ValueError(
                "kline available_at must be >= close_time (final "
                "OHLCV is invisible before candle close; Constitution "
                f"§6); got available_at={avail.isoformat()} "
                f"close_time={ct.isoformat()}"
            )
        if avail < ev:
            raise ValueError(
                "kline available_at must be >= event_time"
            )
        ing = _maybe_utc_aware(self.ingested_at, "ingested_at")
        rev = _maybe_utc_aware(self.revision_time, "revision_time")
        for fname, fval in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
            ("volume", self.volume),
        ):
            if isinstance(fval, bool):
                # bool is a subclass of int; refuse it here.
                raise TypeError(
                    f"kline {fname} must be int / float, got bool"
                )
            if not isinstance(fval, (int, float)):
                raise TypeError(
                    f"kline {fname} must be int / float, got "
                    f"{type(fval)!r}"
                )
        # OHLC sanity: high >= max(open, close), low <= min(open, close),
        # high >= low. Volume must be >= 0.
        h = float(self.high)
        l = float(self.low)
        o = float(self.open)
        c = float(self.close)
        v = float(self.volume)
        if h < l:
            raise ValueError("kline high must be >= low")
        if h < max(o, c):
            raise ValueError(
                "kline high must be >= max(open, close)"
            )
        if l > min(o, c):
            raise ValueError(
                "kline low must be <= min(open, close)"
            )
        if v < 0:
            raise ValueError("kline volume must be >= 0")
        flags = _check_data_quality_flags(self.data_quality_flags)
        refs = _check_evidence_refs(self.evidence_refs)
        if not isinstance(self.late_arrival, bool):
            raise TypeError(
                f"late_arrival must be bool, got {type(self.late_arrival)!r}"
            )
        if self.revised_from_record_id is not None and (
            not isinstance(self.revised_from_record_id, str)
            or not self.revised_from_record_id
        ):
            raise ValueError(
                "revised_from_record_id must be a non-empty string or None"
            )
        rid = (
            self.record_id
            if self.record_id is not None and self.record_id
            else f"kline:{self.symbol}:{self.interval}:{ot.isoformat()}"
        )
        if not isinstance(rid, str) or not rid:
            raise ValueError("record_id must be a non-empty string")
        object.__setattr__(self, "open_time", ot)
        object.__setattr__(self, "close_time", ct)
        object.__setattr__(self, "available_at", avail)
        object.__setattr__(self, "event_time", ev)
        object.__setattr__(self, "ingested_at", ing)
        object.__setattr__(self, "revision_time", rev)
        object.__setattr__(self, "open", o)
        object.__setattr__(self, "high", h)
        object.__setattr__(self, "low", l)
        object.__setattr__(self, "close", c)
        object.__setattr__(self, "volume", v)
        object.__setattr__(self, "data_quality_flags", flags)
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "record_id", rid)

    @property
    def record_type(self) -> str:
        return _INTERVAL_TO_KLINE_RECORD_TYPE[self.interval]

    def to_record_time(self) -> HistoricalRecordTime:
        return HistoricalRecordTime(
            event_time=self.event_time,
            available_at=self.available_at,
            ingested_at=self.ingested_at,
            source=self.source,
            record_id=self.record_id,
            symbol=self.symbol,
            interval=self.interval,
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "symbol": self.symbol,
            "interval": self.interval,
            "open_time": self.open_time.isoformat(),
            "close_time": self.close_time.isoformat(),
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": float(self.volume),
            "event_time": self.event_time.isoformat(),
            "available_at": self.available_at.isoformat(),
            "ingested_at": (
                self.ingested_at.isoformat()
                if self.ingested_at is not None
                else None
            ),
            "source": self.source,
            "data_quality_flags": list(self.data_quality_flags),
            "evidence_refs": list(self.evidence_refs),
            "revision_time": (
                self.revision_time.isoformat()
                if self.revision_time is not None
                else None
            ),
            "revised_from_record_id": self.revised_from_record_id,
            "late_arrival": self.late_arrival,
            "is_historical_kline_record": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# SymbolStatusRecord
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SymbolStatusRecord:
    """A single symbol-level status record for the as-of universe.

    Constitution §9: as-of universe queries MUST NOT use the *current*
    symbol list to reconstruct the past. A symbol qualifies for
    inclusion at simulated time ``T`` iff ``listed_at <= T`` AND
    (``delisted_at is None`` OR ``delisted_at > T``) AND
    ``available_at <= T`` AND ``status`` is in
    :data:`SymbolStatus.TRADABLE_OR_MONITORABLE`.

    ``event_time`` defaults to ``listed_at`` but MAY be overridden for
    pre-listing-announcement records (the brief's "special metadata
    and explicit reason" exception to ``available_at >= event_time``).
    Even with the override, ``available_at >= event_time`` is enforced
    at construction time.
    """

    symbol: str
    market_type: str
    listed_at: datetime
    status: str
    available_at: datetime
    delisted_at: Optional[datetime] = None
    min_notional: Optional[float] = None
    tick_size: Optional[float] = None
    step_size: Optional[float] = None
    contract_type: Optional[str] = None
    data_completeness_state: str = DataCompletenessState.OK
    source: Optional[str] = None
    ingested_at: Optional[datetime] = None
    record_id: Optional[str] = None
    event_time: Optional[datetime] = None
    data_quality_flags: Tuple[str, ...] = ()
    evidence_refs: Tuple[str, ...] = ()
    revision_time: Optional[datetime] = None
    revised_from_record_id: Optional[str] = None
    late_arrival: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("symbol must be a non-empty string")
        if not isinstance(self.market_type, str) or not self.market_type:
            raise ValueError(
                "market_type must be a non-empty string"
            )
        if self.status not in SymbolStatus.ALLOWED:
            raise ValueError(
                f"status must be one of "
                f"{sorted(SymbolStatus.ALLOWED)}, got {self.status!r}"
            )
        if self.data_completeness_state not in DataCompletenessState.ALLOWED:
            raise ValueError(
                f"data_completeness_state must be one of "
                f"{sorted(DataCompletenessState.ALLOWED)}, got "
                f"{self.data_completeness_state!r}"
            )
        listed = ensure_utc_aware(self.listed_at, "listed_at")
        delisted = _maybe_utc_aware(self.delisted_at, "delisted_at")
        if delisted is not None and delisted < listed:
            raise ValueError(
                "delisted_at must be >= listed_at"
            )
        avail = ensure_utc_aware(self.available_at, "available_at")
        ing = _maybe_utc_aware(self.ingested_at, "ingested_at")
        rev = _maybe_utc_aware(self.revision_time, "revision_time")
        ev = (
            ensure_utc_aware(self.event_time, "event_time")
            if self.event_time is not None
            else listed
        )
        if avail < ev:
            raise ValueError(
                "available_at must be >= event_time (a record cannot "
                "be available before its event_time)"
            )
        # If the status is DELISTED, delisted_at MUST be set (and must
        # be <= available_at: the delisting cannot be visible before it
        # happened relative to the record's own event_time).
        if self.status == SymbolStatus.DELISTED and delisted is None:
            raise ValueError(
                "DELISTED status requires delisted_at to be set"
            )
        for fname, fval in (
            ("min_notional", self.min_notional),
            ("tick_size", self.tick_size),
            ("step_size", self.step_size),
        ):
            if fval is None:
                continue
            if isinstance(fval, bool):
                raise TypeError(
                    f"{fname} must be int / float / None, got bool"
                )
            if not isinstance(fval, (int, float)):
                raise TypeError(
                    f"{fname} must be int / float / None, got "
                    f"{type(fval)!r}"
                )
            if float(fval) < 0:
                raise ValueError(f"{fname} must be >= 0")
        flags = _check_data_quality_flags(self.data_quality_flags)
        refs = _check_evidence_refs(self.evidence_refs)
        if not isinstance(self.late_arrival, bool):
            raise TypeError(
                f"late_arrival must be bool, got {type(self.late_arrival)!r}"
            )
        if self.revised_from_record_id is not None and (
            not isinstance(self.revised_from_record_id, str)
            or not self.revised_from_record_id
        ):
            raise ValueError(
                "revised_from_record_id must be a non-empty string or None"
            )
        rid = (
            self.record_id
            if self.record_id is not None and self.record_id
            else (
                f"symstat:{self.symbol}:{self.market_type}:"
                f"{listed.isoformat()}:{ev.isoformat()}"
            )
        )
        if not isinstance(rid, str) or not rid:
            raise ValueError("record_id must be a non-empty string")
        object.__setattr__(self, "listed_at", listed)
        object.__setattr__(self, "delisted_at", delisted)
        object.__setattr__(self, "available_at", avail)
        object.__setattr__(self, "ingested_at", ing)
        object.__setattr__(self, "revision_time", rev)
        object.__setattr__(self, "event_time", ev)
        object.__setattr__(self, "data_quality_flags", flags)
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "record_id", rid)

    @property
    def record_type(self) -> str:
        return HistoricalMarketRecordType.SYMBOL_STATUS

    def to_record_time(self) -> HistoricalRecordTime:
        return HistoricalRecordTime(
            event_time=self.event_time,
            available_at=self.available_at,
            ingested_at=self.ingested_at,
            source=self.source,
            record_id=self.record_id,
            symbol=self.symbol,
        )

    def is_tradable_or_monitorable_at(
        self, simulated_time: datetime
    ) -> bool:
        """Return True iff this symbol qualifies for the as-of universe
        at ``simulated_time``.

        Required: ``available_at <= simulated_time`` AND
        ``listed_at <= simulated_time`` AND
        (``delisted_at is None`` OR ``delisted_at > simulated_time``)
        AND ``status`` in :data:`SymbolStatus.TRADABLE_OR_MONITORABLE`.
        """
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        if self.available_at > sim:
            return False
        if self.listed_at > sim:
            return False
        if self.delisted_at is not None and self.delisted_at <= sim:
            return False
        if self.status not in SymbolStatus.TRADABLE_OR_MONITORABLE:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "record_id": self.record_id,
            "record_type": self.record_type,
            "symbol": self.symbol,
            "market_type": self.market_type,
            "listed_at": self.listed_at.isoformat(),
            "delisted_at": (
                self.delisted_at.isoformat()
                if self.delisted_at is not None
                else None
            ),
            "status": self.status,
            "available_at": self.available_at.isoformat(),
            "min_notional": (
                float(self.min_notional)
                if self.min_notional is not None
                else None
            ),
            "tick_size": (
                float(self.tick_size)
                if self.tick_size is not None
                else None
            ),
            "step_size": (
                float(self.step_size)
                if self.step_size is not None
                else None
            ),
            "contract_type": self.contract_type,
            "data_completeness_state": self.data_completeness_state,
            "source": self.source,
            "ingested_at": (
                self.ingested_at.isoformat()
                if self.ingested_at is not None
                else None
            ),
            "event_time": self.event_time.isoformat(),
            "data_quality_flags": list(self.data_quality_flags),
            "evidence_refs": list(self.evidence_refs),
            "revision_time": (
                self.revision_time.isoformat()
                if self.revision_time is not None
                else None
            ),
            "revised_from_record_id": self.revised_from_record_id,
            "late_arrival": self.late_arrival,
            "is_symbol_status_record": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# HistoricalMarketStore
# ---------------------------------------------------------------------------


_AnyRecord = Union[
    HistoricalMarketRecord, HistoricalKlineRecord, SymbolStatusRecord
]


class HistoricalMarketStore:
    """Strict blind walk-forward in-memory historical market store.

    The store keeps :class:`HistoricalMarketRecord`,
    :class:`HistoricalKlineRecord`, and :class:`SymbolStatusRecord`
    rows. Every query is gated by :class:`TimeWallGuard`: at simulated
    time ``T``, the store returns ONLY records whose
    ``available_at <= T``. Future records are NEVER silently dropped;
    they produce :class:`NoLookaheadViolation` audit objects accessible
    via :pyattr:`violations`.

    The store has no I/O, no network, no LLM, no Telegram, no Binance
    private API path, and no authority over the Risk Engine, the
    Execution FSM, or the Capital Flow Engine.
    """

    def __init__(
        self,
        *,
        time_wall_guard: Optional[TimeWallGuard] = None,
        candle_visibility_guard: Optional[CandleVisibilityGuard] = None,
    ) -> None:
        self._tw: TimeWallGuard = time_wall_guard or TimeWallGuard()
        self._cv: CandleVisibilityGuard = (
            candle_visibility_guard or CandleVisibilityGuard()
        )
        self._records: List[HistoricalMarketRecord] = []
        self._klines: List[HistoricalKlineRecord] = []
        self._symbol_status: List[SymbolStatusRecord] = []
        self._violations: List[NoLookaheadViolation] = []
        # Defensive tripwires (mirrors PR94 guards):
        self.sandbox_only: bool = True
        self.live_trading: bool = False
        self.exchange_live_orders: bool = False
        self.binance_private_api_enabled: bool = False
        self.telegram_outbound_enabled: bool = False
        self.ai_trade_authority: bool = False
        self.trade_authority: bool = False
        self.auto_tuning_allowed: bool = False
        self.phase_12_forbidden: bool = True

    # ----- public API: introspection -----

    @property
    def time_wall_guard(self) -> TimeWallGuard:
        return self._tw

    @property
    def candle_visibility_guard(self) -> CandleVisibilityGuard:
        return self._cv

    @property
    def violations(self) -> Tuple[NoLookaheadViolation, ...]:
        return tuple(self._violations)

    def clear_violations(self) -> None:
        self._violations.clear()

    @property
    def record_count(self) -> int:
        return (
            len(self._records)
            + len(self._klines)
            + len(self._symbol_status)
        )

    @property
    def kline_count(self) -> int:
        return len(self._klines)

    @property
    def symbol_status_count(self) -> int:
        return len(self._symbol_status)

    # ----- public API: ingestion -----

    def add_record(self, record: _AnyRecord) -> None:
        """Add a single record to the store.

        Accepts :class:`HistoricalMarketRecord`,
        :class:`HistoricalKlineRecord`, or
        :class:`SymbolStatusRecord`.
        """
        if isinstance(record, HistoricalKlineRecord):
            self._klines.append(record)
        elif isinstance(record, SymbolStatusRecord):
            self._symbol_status.append(record)
        elif isinstance(record, HistoricalMarketRecord):
            self._records.append(record)
        else:
            raise TypeError(
                f"record must be HistoricalMarketRecord / "
                f"HistoricalKlineRecord / SymbolStatusRecord, got "
                f"{type(record)!r}"
            )

    def add_records(self, records: Iterable[_AnyRecord]) -> None:
        for r in records:
            self.add_record(r)

    # ----- public API: queries -----

    def query_records(
        self,
        record_type: str,
        *,
        symbol: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        simulated_time: datetime,
    ) -> List[_AnyRecord]:
        """Return records of ``record_type`` visible at ``simulated_time``.

        Records are filtered by ``available_at <= simulated_time``;
        future records produce :class:`NoLookaheadViolation` audit
        entries appended to :pyattr:`violations`. The result is sorted
        deterministically by
        ``(event_time, available_at, symbol, record_id)``.
        """
        if record_type not in HistoricalMarketRecordType.ALLOWED:
            raise ValueError(
                f"record_type must be one of "
                f"{sorted(HistoricalMarketRecordType.ALLOWED)}, got "
                f"{record_type!r}"
            )
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        st = (
            ensure_utc_aware(start_time, "start_time")
            if start_time is not None
            else None
        )
        et = (
            ensure_utc_aware(end_time, "end_time")
            if end_time is not None
            else None
        )
        if st is not None and et is not None and et < st:
            raise ValueError("end_time must be >= start_time")

        candidates: List[_AnyRecord] = []
        if record_type in HistoricalMarketRecordType.KLINE_TYPES:
            interval_for_type = next(
                k
                for k, v in _INTERVAL_TO_KLINE_RECORD_TYPE.items()
                if v == record_type
            )
            for k in self._klines:
                if k.interval != interval_for_type:
                    continue
                if symbol is not None and k.symbol != symbol:
                    continue
                if st is not None and k.event_time < st:
                    continue
                if et is not None and k.event_time > et:
                    continue
                candidates.append(k)
        elif record_type == HistoricalMarketRecordType.SYMBOL_STATUS:
            for s in self._symbol_status:
                if symbol is not None and s.symbol != symbol:
                    continue
                if st is not None and s.event_time < st:
                    continue
                if et is not None and s.event_time > et:
                    continue
                candidates.append(s)
        else:
            for r in self._records:
                if r.record_type != record_type:
                    continue
                if symbol is not None and r.symbol != symbol:
                    continue
                if st is not None and r.event_time < st:
                    continue
                if et is not None and r.event_time > et:
                    continue
                candidates.append(r)

        return self._apply_time_wall_and_sort(candidates, sim)

    def query_latest(
        self,
        record_type: str,
        symbol: Optional[str],
        simulated_time: datetime,
    ) -> Optional[_AnyRecord]:
        """Return the latest record of ``record_type`` visible at
        ``simulated_time``, or ``None`` if no record is visible.

        "Latest" is defined as the record with the largest
        ``event_time``; ties broken by ``available_at`` then by
        ``record_id`` (deterministic).
        """
        rs = self.query_records(
            record_type, symbol=symbol, simulated_time=simulated_time
        )
        if not rs:
            return None
        return max(
            rs,
            key=lambda r: (
                r.event_time,
                r.available_at,
                getattr(r, "record_id", "") or "",
            ),
        )

    def query_klines(
        self,
        symbol: str,
        interval: str,
        *,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        simulated_time: datetime,
    ) -> List[HistoricalKlineRecord]:
        """Return klines for ``symbol`` / ``interval`` visible at
        ``simulated_time``.

        Filters on:

          * ``available_at <= simulated_time`` (TimeWallGuard),
          * ``CandleVisibilityGuard.is_candle_closed(open_time,
            interval, simulated_time)`` (Constitution §6:
            final OHLCV invisible before close).

        Future klines (open candles) produce
        :class:`NoLookaheadViolation` audit entries; they are NEVER
        silently returned with their final OHLCV stripped. Result is
        sorted by ``(open_time, available_at, record_id)``.
        """
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("symbol must be a non-empty string")
        if interval not in _INTERVAL_TO_KLINE_RECORD_TYPE:
            raise ValueError(
                f"v0 kline interval must be one of "
                f"{sorted(_INTERVAL_TO_KLINE_RECORD_TYPE)}, got "
                f"{interval!r}"
            )
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        st = (
            ensure_utc_aware(start_time, "start_time")
            if start_time is not None
            else None
        )
        et = (
            ensure_utc_aware(end_time, "end_time")
            if end_time is not None
            else None
        )
        if st is not None and et is not None and et < st:
            raise ValueError("end_time must be >= start_time")

        results: List[HistoricalKlineRecord] = []
        for k in self._klines:
            if k.symbol != symbol or k.interval != interval:
                continue
            if st is not None and k.open_time < st:
                continue
            if et is not None and k.open_time > et:
                continue
            # First gate: time wall.
            v = self._tw.validate_no_lookahead(k.to_record_time(), sim)
            if v is not None:
                self._violations.append(v)
                continue
            # Second gate: closed-candle visibility.
            if not self._cv.is_candle_closed(
                k.open_time, k.interval, sim
            ):
                cv_violation = (
                    self._tw.make_unclosed_candle_field_access_violation(
                        simulated_time=sim,
                        field_name="close",
                        candle_open_time=k.open_time,
                        interval=k.interval,
                        record_id=k.record_id,
                        symbol=k.symbol,
                        source=k.source,
                    )
                )
                self._violations.append(cv_violation)
                continue
            results.append(k)
        results.sort(
            key=lambda r: (
                r.open_time,
                r.available_at,
                r.record_id or "",
            )
        )
        return results

    def query_symbol_status(
        self,
        symbol: str,
        simulated_time: datetime,
    ) -> Optional[SymbolStatusRecord]:
        """Return the latest visible :class:`SymbolStatusRecord` for
        ``symbol`` at ``simulated_time``, or ``None`` if no such record
        is visible.
        """
        if not isinstance(symbol, str) or not symbol:
            raise ValueError("symbol must be a non-empty string")
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        latest: Optional[SymbolStatusRecord] = None
        for s in self._symbol_status:
            if s.symbol != symbol:
                continue
            v = self._tw.validate_no_lookahead(s.to_record_time(), sim)
            if v is not None:
                self._violations.append(v)
                continue
            if latest is None or (
                s.event_time,
                s.available_at,
                s.record_id or "",
            ) > (
                latest.event_time,
                latest.available_at,
                latest.record_id or "",
            ):
                latest = s
        return latest

    def query_asof_universe(
        self, simulated_time: datetime
    ) -> List[SymbolStatusRecord]:
        """Return the as-of universe at ``simulated_time``.

        Constitution §9: a symbol qualifies iff its latest visible
        :class:`SymbolStatusRecord` has ``listed_at <= simulated_time``
        AND (``delisted_at is None`` OR ``delisted_at >
        simulated_time``) AND ``status`` is tradable / monitorable.
        The store NEVER substitutes the *current* symbol list; if no
        :class:`SymbolStatusRecord` is visible at ``simulated_time``,
        the symbol is simply absent from the universe at that
        simulated time.

        Result is sorted by ``(symbol, listed_at, record_id)``.
        """
        sim = ensure_utc_aware(simulated_time, "simulated_time")
        per_symbol: Dict[str, SymbolStatusRecord] = {}
        for s in self._symbol_status:
            v = self._tw.validate_no_lookahead(s.to_record_time(), sim)
            if v is not None:
                self._violations.append(v)
                continue
            cur = per_symbol.get(s.symbol)
            key_new = (
                s.event_time,
                s.available_at,
                s.record_id or "",
            )
            if cur is None or key_new > (
                cur.event_time,
                cur.available_at,
                cur.record_id or "",
            ):
                per_symbol[s.symbol] = s
        out: List[SymbolStatusRecord] = [
            s
            for s in per_symbol.values()
            if s.is_tradable_or_monitorable_at(sim)
        ]
        out.sort(
            key=lambda r: (
                r.symbol,
                r.listed_at,
                r.record_id or "",
            )
        )
        return out

    # ----- public API: serialisation -----

    def safety_payload(self) -> Dict[str, Any]:
        """Return the project-wide safety boundary payload.

        Used by tests and downstream tooling to verify that the store
        cannot accidentally advertise capabilities it MUST NOT have.
        """
        out = _safety_payload()
        assert_no_forbidden_fields(out)
        return out

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "record_count": self.record_count,
            "kline_count": self.kline_count,
            "symbol_status_count": self.symbol_status_count,
            "violation_count": len(self._violations),
            "is_historical_market_store": True,
        }
        out.update(_safety_payload())
        assert_no_forbidden_fields(out)
        return out

    # ----- internal helpers -----

    def _apply_time_wall_and_sort(
        self,
        candidates: List[_AnyRecord],
        simulated_time: datetime,
    ) -> List[_AnyRecord]:
        results: List[_AnyRecord] = []
        for c in candidates:
            v = self._tw.validate_no_lookahead(
                c.to_record_time(), simulated_time
            )
            if v is not None:
                self._violations.append(v)
                continue
            results.append(c)
        results.sort(
            key=lambda r: (
                r.event_time,
                r.available_at,
                getattr(r, "symbol", "") or "",
                getattr(r, "record_id", "") or "",
            )
        )
        return results


__all__ = [
    "PHASE_NAME",
    "DataCompletenessState",
    "DataQualityFlag",
    "HistoricalKlineRecord",
    "HistoricalMarketRecord",
    "HistoricalMarketRecordType",
    "HistoricalMarketStore",
    "SymbolStatus",
    "SymbolStatusRecord",
]
