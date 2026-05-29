"""Historical Data Ingestion / Backfill v0 for Phase 11C.1D-D-H
(PR101).

Strict blind walk-forward historical-data ingestion substrate. This
module is the parser / engine half of the **eighth**
anti-future-lookahead infrastructure block of the strict blind
walk-forward stack defined by Phase 11C.1D-D (the *Strict Blind
Walk-forward Sim-Live Constitution*, PR93). It builds strictly on top
of the PR94 / PR95 substrate and is the data feeder for the PR100
:class:`BlindWalkForwardRunner` (it produces the records that a
:class:`HistoricalMarketStore` consumes and the manifests that the
:class:`BlindRunManifest` pins via ``data_manifest_hash`` /
``universe_manifest_hash``).

Responsibility (v0):

  * Convert **local file** rows into the PR95 record types
    (:class:`HistoricalKlineRecord`,
    :class:`HistoricalMarketRecord`, :class:`SymbolStatusRecord`).
  * Compute ``event_time`` / ``available_at`` / ``ingested_at`` and
    enforce the four-timestamp record-time model of Constitution §5.
  * NEVER substitute ``ingested_at`` for ``available_at``.
  * Validate timezone-aware UTC; reject naive / malformed time
    fields.
  * Preserve ``data_quality_flags`` / late-arrival / revision
    metadata.
  * Build a :class:`HistoricalDataManifest` (record counts, per-symbol
    coverage, data-gap summary) and a :class:`UniverseManifest`
    (as-of universe, no survivorship bias).
  * Emit a coverage / data-gap report and a ``records.jsonl`` dump.

NON-responsibility (v0):

  * It does NOT download data and does NOT reach any network. It reads
    **public / file** sources only.
  * It does NOT implement the 30D / 60D / 90D / 2Y runner.
  * It does NOT tune any parameter or rule.
  * A coverage report is NOT a strategy-effectiveness conclusion.

If ``input_root`` does not exist or carries no data, the engine
returns ``INSUFFICIENT_EVIDENCE`` and NEVER fabricates real market
data. A deterministic fixture is produced ONLY when ``fixture_mode``
is explicitly enabled, and every fixture record / output is clearly
marked synthetic.

Hard safety boundary (Phase 11C.1D-D-H / PR101):

  - mode = historical_blind_sim_live
  - sandbox_only = True
  - simulated_only = True
  - no_live_order = True
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
  - emit any runtime_config_patch / threshold_patch /
    symbol_limit_patch / candidate_pool_patch / regime_weight_patch /
    strategy_parameter_patch / signal_to_trade / should_buy /
    should_short / apply_change / deploy_change / enable_live /
    live_ready / trading_approved
  - emit an api key / api secret / listenKey / signed-endpoint
    reference / private-websocket reference / real exchange order id /
    real account id
  - present a coverage report as a strategy-effectiveness conclusion
  - authorise live trading or auto-tuning
  - enter Phase 12

Successful PR101 acceptance only authorises a **historical data
coverage checkpoint / short-window no-lookahead trial preparation**.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from app.sim.historical_data_manifest import (
    PHASE_NAME,
    DataIngestionStatus,
    HistoricalDataManifest,
    HistoricalDataSourceType,
    UniverseManifest,
    compute_artefact_hash,
    safety_payload,
)
from app.sim.historical_market_store import (
    DataCompletenessState,
    DataQualityFlag,
    HistoricalKlineRecord,
    HistoricalMarketRecord,
    HistoricalMarketRecordType,
    HistoricalMarketStore,
    SymbolStatus,
    SymbolStatusRecord,
)
from app.sim.simulation_clock import (
    ensure_utc_aware,
    parse_interval_seconds,
)
from app.sim.time_wall_guard import assert_no_forbidden_fields


# ---------------------------------------------------------------------------
# v0 supported intervals
# ---------------------------------------------------------------------------

SUPPORTED_KLINE_INTERVALS: Tuple[str, ...] = ("1m", "5m")

# Module-level coverage thresholds. These are Python constants - they
# are NOT runtime knobs, NOT loaded from config, NOT loaded from an
# LLM, NOT exposed via CLI, and NOT auto-tuned. Changing them is a
# docs / brief / new-PR concern.
_COMPLETE_RATIO: float = 0.999
_PARTIAL_RATIO: float = 0.90

_AnyRecord = Union[
    HistoricalMarketRecord, HistoricalKlineRecord, SymbolStatusRecord
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IngestionSchemaError(ValueError):
    """Raised when a row fails schema validation."""


class IngestionTimeFieldError(IngestionSchemaError):
    """Raised when a row carries an invalid / naive / malformed time
    field, or would require ``available_at < event_time``."""


# ---------------------------------------------------------------------------
# Internal time / number helpers
# ---------------------------------------------------------------------------


def _parse_time_field(
    value: Any, name: str, *, allow_none: bool = False
) -> Optional[datetime]:
    """Parse a single time field into a timezone-aware UTC datetime.

    Accepted: timezone-aware :class:`datetime`, epoch milliseconds
    (int / float, Binance public convention), or an ISO-8601 string
    that carries an explicit UTC offset (a trailing ``Z`` is accepted).

    Rejected (raising :class:`IngestionTimeFieldError`): ``None`` when
    not ``allow_none``, naive datetimes, ISO strings without a
    timezone, and malformed strings. ``ingested_at`` is NEVER inferred
    from any other field here.
    """
    if value is None:
        if allow_none:
            return None
        raise IngestionTimeFieldError(f"{name} is required")
    if isinstance(value, bool):
        raise IngestionTimeFieldError(
            f"{name} must not be a bool"
        )
    if isinstance(value, datetime):
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise IngestionTimeFieldError(
                f"{name} must be timezone-aware UTC; naive datetimes "
                "are forbidden as historical record time"
            )
        return ensure_utc_aware(value, name)
    if isinstance(value, (int, float)):
        # Epoch milliseconds (Binance public files use ms).
        try:
            return datetime.fromtimestamp(
                float(value) / 1000.0, tz=timezone.utc
            )
        except (OverflowError, OSError, ValueError) as exc:
            raise IngestionTimeFieldError(
                f"{name} epoch-ms value {value!r} is out of range"
            ) from exc
    if isinstance(value, str):
        s = value.strip()
        if not s:
            raise IngestionTimeFieldError(f"{name} is an empty string")
        if s.endswith("Z") or s.endswith("z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError as exc:
            raise IngestionTimeFieldError(
                f"{name} is not a valid ISO-8601 datetime: {value!r}"
            ) from exc
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            raise IngestionTimeFieldError(
                f"{name} must be timezone-aware UTC; naive ISO "
                f"datetime forbidden: {value!r}"
            )
        return ensure_utc_aware(dt, name)
    raise IngestionTimeFieldError(
        f"{name} must be datetime / epoch-ms / ISO-8601 string, got "
        f"{type(value)!r}"
    )


def _num(row: Mapping[str, Any], *keys: str) -> float:
    for k in keys:
        if k in row and row[k] is not None:
            v = row[k]
            if isinstance(v, bool):
                raise IngestionSchemaError(f"{k} must not be a bool")
            try:
                return float(v)
            except (TypeError, ValueError) as exc:
                raise IngestionSchemaError(
                    f"{k} must be numeric, got {v!r}"
                ) from exc
    raise IngestionSchemaError(
        f"required numeric field {keys[0]!r} is missing"
    )


def _opt_num(
    row: Mapping[str, Any], *keys: str
) -> Optional[float]:
    for k in keys:
        if k in row and row[k] is not None:
            v = row[k]
            if isinstance(v, bool):
                raise IngestionSchemaError(f"{k} must not be a bool")
            try:
                return float(v)
            except (TypeError, ValueError) as exc:
                raise IngestionSchemaError(
                    f"{k} must be numeric, got {v!r}"
                ) from exc
    return None


def _quality_flags(row: Mapping[str, Any]) -> Tuple[str, ...]:
    raw = row.get("data_quality_flags") or ()
    if isinstance(raw, str):
        raw = [raw]
    out: List[str] = []
    for f in raw:
        if not isinstance(f, str):
            raise IngestionSchemaError(
                "data_quality_flags entries must be strings"
            )
        if f not in DataQualityFlag.ALLOWED:
            raise IngestionSchemaError(
                f"data_quality_flag {f!r} not in closed taxonomy"
            )
        out.append(f)
    return tuple(out)


def _revision_fields(
    row: Mapping[str, Any],
) -> Tuple[bool, Optional[datetime], Optional[str]]:
    late = bool(row.get("late_arrival", False))
    rev_time = _parse_time_field(
        row.get("revision_time"), "revision_time", allow_none=True
    )
    rev_from = row.get("revised_from_record_id")
    if rev_from is not None and (
        not isinstance(rev_from, str) or not rev_from
    ):
        raise IngestionSchemaError(
            "revised_from_record_id must be a non-empty string or null"
        )
    return late, rev_time, rev_from


def _availability_lag(default_availability_lag_seconds: float) -> timedelta:
    lag = float(default_availability_lag_seconds)
    if lag < 0:
        raise ValueError(
            "default_availability_lag_seconds must be >= 0"
        )
    return timedelta(seconds=lag)


# ---------------------------------------------------------------------------
# Row parsers (pure / deterministic)
# ---------------------------------------------------------------------------


def parse_kline_row(
    row: Union[Mapping[str, Any], Sequence[Any]],
    *,
    symbol: str,
    interval: str,
    source: Optional[str] = None,
    default_availability_lag_seconds: float = 0.0,
) -> HistoricalKlineRecord:
    """Parse one kline row into a :class:`HistoricalKlineRecord`.

    Accepts either a dict row (``open_time`` / ``open`` / ``high`` /
    ``low`` / ``close`` / ``volume`` + optional ``available_at`` /
    ``ingested_at`` / ``data_quality_flags`` / revision metadata) or a
    Binance public-kline array row (``[open_time_ms, open, high, low,
    close, volume, close_time_ms, ...]``).

    ``available_at`` defaults to ``close_time + lag`` (Constitution §6:
    final OHLCV is invisible before candle close). ``ingested_at`` is
    NEVER substituted for ``available_at``.
    """
    if interval not in SUPPORTED_KLINE_INTERVALS:
        raise IngestionSchemaError(
            f"v0 kline interval must be one of "
            f"{list(SUPPORTED_KLINE_INTERVALS)}, got {interval!r}"
        )
    lag = _availability_lag(default_availability_lag_seconds)
    seconds = parse_interval_seconds(interval)

    explicit_available_at: Any = None
    explicit_close_time: Any = None
    ingested_raw: Any = None
    flags: Tuple[str, ...] = ()
    late = False
    rev_time: Optional[datetime] = None
    rev_from: Optional[str] = None

    if isinstance(row, Mapping):
        open_time = _parse_time_field(
            row.get("open_time", row.get("openTime")), "open_time"
        )
        o = _num(row, "open", "o")
        h = _num(row, "high", "h")
        low_ = _num(row, "low", "l")
        c = _num(row, "close", "c")
        v = _num(row, "volume", "vol", "v")
        explicit_available_at = row.get("available_at")
        explicit_close_time = row.get("close_time", row.get("closeTime"))
        ingested_raw = row.get("ingested_at")
        flags = _quality_flags(row)
        late, rev_time, rev_from = _revision_fields(row)
    elif isinstance(row, (list, tuple)):
        if len(row) < 6:
            raise IngestionSchemaError(
                "Binance kline array row must have at least 6 fields "
                "[open_time, open, high, low, close, volume, ...]"
            )
        open_time = _parse_time_field(row[0], "open_time")
        try:
            o = float(row[1])
            h = float(row[2])
            low_ = float(row[3])
            c = float(row[4])
            v = float(row[5])
        except (TypeError, ValueError) as exc:
            raise IngestionSchemaError(
                f"Binance kline array OHLCV must be numeric: {exc}"
            ) from exc
        if len(row) >= 7 and row[6] is not None:
            explicit_close_time = row[6]
    else:
        raise IngestionSchemaError(
            f"kline row must be a Mapping or array, got {type(row)!r}"
        )

    close_time = open_time + timedelta(seconds=seconds)
    if explicit_close_time is not None:
        parsed_close = _parse_time_field(
            explicit_close_time, "close_time"
        )
        # Binance close_time is conventionally the last ms of the
        # candle (open_time + interval - 1ms). Normalise to the
        # canonical close instant the record type expects.
        delta = abs((parsed_close - close_time).total_seconds())
        if delta > 1.0:
            raise IngestionTimeFieldError(
                "close_time must equal open_time + interval "
                f"(±1s); expected {close_time.isoformat()}, got "
                f"{parsed_close.isoformat()}"
            )

    if explicit_available_at is not None:
        available_at = _parse_time_field(
            explicit_available_at, "available_at"
        )
    else:
        # NEVER use ingested_at as available_at: derive it from the
        # candle close time plus the configured publication lag.
        available_at = close_time + lag

    ingested_at = _parse_time_field(
        ingested_raw, "ingested_at", allow_none=True
    )

    try:
        return HistoricalKlineRecord(
            symbol=symbol,
            interval=interval,
            open_time=open_time,
            open=o,
            high=h,
            low=low_,
            close=c,
            volume=v,
            available_at=available_at,
            close_time=close_time,
            ingested_at=ingested_at,
            source=source,
            data_quality_flags=flags,
            revision_time=rev_time,
            revised_from_record_id=rev_from,
            late_arrival=late,
        )
    except ValueError as exc:
        msg = str(exc)
        if "available_at" in msg or "event_time" in msg or (
            "close_time" in msg
        ):
            raise IngestionTimeFieldError(msg) from exc
        raise IngestionSchemaError(msg) from exc


def _parse_market_row(
    row: Mapping[str, Any],
    *,
    record_type: str,
    symbol: Optional[str],
    source: Optional[str],
    default_availability_lag_seconds: float,
    event_time_keys: Tuple[str, ...],
    payload_builder,
    record_id_prefix: str,
) -> HistoricalMarketRecord:
    if not isinstance(row, Mapping):
        raise IngestionSchemaError(
            f"{record_type} row must be a Mapping, got {type(row)!r}"
        )
    lag = _availability_lag(default_availability_lag_seconds)
    event_time = _parse_time_field(
        _first_present(row, event_time_keys), "event_time"
    )
    explicit_available_at = row.get("available_at")
    if explicit_available_at is not None:
        available_at = _parse_time_field(
            explicit_available_at, "available_at"
        )
    else:
        # NEVER use ingested_at as available_at.
        available_at = event_time + lag
    ingested_at = _parse_time_field(
        row.get("ingested_at"), "ingested_at", allow_none=True
    )
    flags = _quality_flags(row)
    late, rev_time, rev_from = _revision_fields(row)
    sym = symbol or row.get("symbol")
    if sym is not None and (not isinstance(sym, str) or not sym):
        raise IngestionSchemaError(
            "symbol must be a non-empty string or null"
        )
    payload = payload_builder(row)
    record_id = (
        row.get("record_id")
        or f"{record_id_prefix}:{sym}:{event_time.isoformat()}"
    )
    try:
        return HistoricalMarketRecord(
            record_id=record_id,
            record_type=record_type,
            symbol=sym,
            event_time=event_time,
            available_at=available_at,
            ingested_at=ingested_at,
            source=source,
            payload=payload,
            data_quality_flags=flags,
            revision_time=rev_time,
            revised_from_record_id=rev_from,
            late_arrival=late,
        )
    except ValueError as exc:
        msg = str(exc)
        if "available_at" in msg or "event_time" in msg:
            raise IngestionTimeFieldError(msg) from exc
        raise IngestionSchemaError(msg) from exc


def _first_present(row: Mapping[str, Any], keys: Tuple[str, ...]) -> Any:
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return None


def parse_funding_row(
    row: Mapping[str, Any],
    *,
    symbol: Optional[str] = None,
    source: Optional[str] = None,
    default_availability_lag_seconds: float = 0.0,
) -> HistoricalMarketRecord:
    """Parse one funding-rate row into a :class:`HistoricalMarketRecord`."""

    def _payload(r: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "funding_rate": _num(
                r, "funding_rate", "fundingRate", "rate"
            ),
            "funding_interval_hours": _opt_num(
                r, "funding_interval_hours", "fundingIntervalHours"
            ),
        }

    return _parse_market_row(
        row,
        record_type=HistoricalMarketRecordType.FUNDING_RATE,
        symbol=symbol,
        source=source,
        default_availability_lag_seconds=default_availability_lag_seconds,
        event_time_keys=(
            "event_time",
            "funding_time",
            "fundingTime",
            "timestamp",
        ),
        payload_builder=_payload,
        record_id_prefix="funding",
    )


def parse_open_interest_row(
    row: Mapping[str, Any],
    *,
    symbol: Optional[str] = None,
    source: Optional[str] = None,
    default_availability_lag_seconds: float = 0.0,
) -> HistoricalMarketRecord:
    """Parse one open-interest row into a :class:`HistoricalMarketRecord`."""

    def _payload(r: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "open_interest": _num(
                r, "open_interest", "openInterest", "oi"
            ),
            "open_interest_value": _opt_num(
                r, "open_interest_value", "openInterestValue"
            ),
        }

    return _parse_market_row(
        row,
        record_type=HistoricalMarketRecordType.OPEN_INTEREST,
        symbol=symbol,
        source=source,
        default_availability_lag_seconds=default_availability_lag_seconds,
        event_time_keys=(
            "event_time",
            "timestamp",
            "time",
        ),
        payload_builder=_payload,
        record_id_prefix="oi",
    )


def parse_ticker_24h_row(
    row: Mapping[str, Any],
    *,
    symbol: Optional[str] = None,
    source: Optional[str] = None,
    default_availability_lag_seconds: float = 0.0,
) -> HistoricalMarketRecord:
    """Parse one 24h ticker row into a :class:`HistoricalMarketRecord`."""

    def _payload(r: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "last_price": _opt_num(
                r, "last_price", "lastPrice", "close"
            ),
            "price_change_percent": _opt_num(
                r, "price_change_percent", "priceChangePercent"
            ),
            "quote_volume": _opt_num(
                r, "quote_volume", "quoteVolume"
            ),
            "volume": _opt_num(r, "volume"),
            "high_price": _opt_num(r, "high_price", "highPrice"),
            "low_price": _opt_num(r, "low_price", "lowPrice"),
        }

    return _parse_market_row(
        row,
        record_type=HistoricalMarketRecordType.TICKER_24H,
        symbol=symbol,
        source=source,
        default_availability_lag_seconds=default_availability_lag_seconds,
        event_time_keys=(
            "event_time",
            "timestamp",
            "close_time",
            "closeTime",
            "time",
        ),
        payload_builder=_payload,
        record_id_prefix="ticker24h",
    )


def parse_symbol_status_row(
    row: Mapping[str, Any],
    *,
    source: Optional[str] = None,
    default_availability_lag_seconds: float = 0.0,
) -> SymbolStatusRecord:
    """Parse one exchangeInfo / symbol-status row into a
    :class:`SymbolStatusRecord` (no survivorship bias)."""
    if not isinstance(row, Mapping):
        raise IngestionSchemaError(
            f"symbol-status row must be a Mapping, got {type(row)!r}"
        )
    lag = _availability_lag(default_availability_lag_seconds)
    symbol = row.get("symbol")
    if not isinstance(symbol, str) or not symbol:
        raise IngestionSchemaError(
            "symbol-status row requires a non-empty 'symbol'"
        )
    market_type = row.get("market_type") or row.get("contractType") or (
        "UNKNOWN"
    )
    status = row.get("status", SymbolStatus.UNKNOWN)
    if status not in SymbolStatus.ALLOWED:
        raise IngestionSchemaError(
            f"symbol status {status!r} not in closed taxonomy"
        )
    listed_at = _parse_time_field(
        _first_present(row, ("listed_at", "onboardDate", "listedAt")),
        "listed_at",
    )
    delisted_at = _parse_time_field(
        _first_present(row, ("delisted_at", "delistedAt")),
        "delisted_at",
        allow_none=True,
    )
    explicit_available_at = row.get("available_at")
    if explicit_available_at is not None:
        available_at = _parse_time_field(
            explicit_available_at, "available_at"
        )
    else:
        available_at = listed_at + lag
    ingested_at = _parse_time_field(
        row.get("ingested_at"), "ingested_at", allow_none=True
    )
    event_time = _parse_time_field(
        row.get("event_time"), "event_time", allow_none=True
    )
    completeness = row.get(
        "data_completeness_state", DataCompletenessState.OK
    )
    if completeness not in DataCompletenessState.ALLOWED:
        raise IngestionSchemaError(
            f"data_completeness_state {completeness!r} not allowed"
        )
    flags = _quality_flags(row)
    late, rev_time, rev_from = _revision_fields(row)
    try:
        return SymbolStatusRecord(
            symbol=symbol,
            market_type=str(market_type),
            listed_at=listed_at,
            status=status,
            available_at=available_at,
            delisted_at=delisted_at,
            min_notional=_opt_num(row, "min_notional", "minNotional"),
            tick_size=_opt_num(row, "tick_size", "tickSize"),
            step_size=_opt_num(row, "step_size", "stepSize"),
            contract_type=row.get("contract_type")
            or row.get("contractType"),
            data_completeness_state=completeness,
            source=source,
            ingested_at=ingested_at,
            event_time=event_time,
            data_quality_flags=flags,
            revision_time=rev_time,
            revised_from_record_id=rev_from,
            late_arrival=late,
        )
    except ValueError as exc:
        msg = str(exc)
        if "available_at" in msg or "event_time" in msg or (
            "listed_at" in msg
        ) or "delisted_at" in msg:
            raise IngestionTimeFieldError(msg) from exc
        raise IngestionSchemaError(msg) from exc


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoricalDataIngestionConfig:
    """Frozen configuration for one historical-data ingestion run."""

    input_root: str
    output_root: str
    start_time: datetime
    end_time: datetime
    symbols: Tuple[str, ...] = ()
    intervals: Tuple[str, ...] = SUPPORTED_KLINE_INTERVALS
    include_funding: bool = True
    include_open_interest: bool = True
    include_ticker_24h: bool = True
    include_exchange_info: bool = True
    include_symbol_status: bool = True
    default_availability_lag_seconds: float = 0.0
    source_type: str = HistoricalDataSourceType.MANUAL_FIXTURE_FILE
    strict_utc: bool = True
    strict_available_at: bool = True
    sandbox_only: bool = True
    phase_12_forbidden: bool = True
    fixture_mode: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.input_root, str) or not self.input_root:
            raise ValueError("input_root must be a non-empty string")
        if not isinstance(self.output_root, str) or not (
            self.output_root
        ):
            raise ValueError("output_root must be a non-empty string")
        st = ensure_utc_aware(self.start_time, "start_time")
        et = ensure_utc_aware(self.end_time, "end_time")
        if et < st:
            raise ValueError("end_time must be >= start_time")
        symbols = tuple(self.symbols)
        for s in symbols:
            if not isinstance(s, str) or not s:
                raise ValueError("symbols entries must be non-empty")
        intervals: List[str] = []
        for iv in self.intervals:
            if iv not in SUPPORTED_KLINE_INTERVALS:
                raise ValueError(
                    f"v0 intervals must be a subset of "
                    f"{list(SUPPORTED_KLINE_INTERVALS)}, got {iv!r}"
                )
            if iv not in intervals:
                intervals.append(iv)
        if not intervals:
            raise ValueError("intervals must be non-empty")
        if self.source_type not in HistoricalDataSourceType.ALLOWED:
            raise ValueError(
                f"source_type must be one of "
                f"{sorted(HistoricalDataSourceType.ALLOWED)}"
            )
        if float(self.default_availability_lag_seconds) < 0:
            raise ValueError(
                "default_availability_lag_seconds must be >= 0"
            )
        # Hard-pinned safety flags cannot be flipped.
        if self.sandbox_only is not True:
            raise ValueError("sandbox_only must be True")
        if self.phase_12_forbidden is not True:
            raise ValueError("phase_12_forbidden must be True")
        object.__setattr__(self, "start_time", st)
        object.__setattr__(self, "end_time", et)
        object.__setattr__(self, "symbols", symbols)
        object.__setattr__(self, "intervals", tuple(intervals))

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "input_root": self.input_root,
            "output_root": self.output_root,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "symbols": list(self.symbols),
            "intervals": list(self.intervals),
            "include_funding": bool(self.include_funding),
            "include_open_interest": bool(self.include_open_interest),
            "include_ticker_24h": bool(self.include_ticker_24h),
            "include_exchange_info": bool(self.include_exchange_info),
            "include_symbol_status": bool(self.include_symbol_status),
            "default_availability_lag_seconds": float(
                self.default_availability_lag_seconds
            ),
            "source_type": self.source_type,
            "strict_utc": bool(self.strict_utc),
            "strict_available_at": bool(self.strict_available_at),
            "fixture_mode": bool(self.fixture_mode),
            "is_historical_data_ingestion_config": True,
        }
        out.update(safety_payload())
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoricalDataIngestionResult:
    """Frozen result of one historical-data ingestion run."""

    status: str
    ingested_record_count: int
    skipped_record_count: int
    rejected_record_count: int
    manifest: Optional[HistoricalDataManifest] = None
    universe_manifest: Optional[UniverseManifest] = None
    coverage_report_path: Optional[str] = None
    data_gap_report_path: Optional[str] = None
    records_path: Optional[str] = None
    warnings: Tuple[str, ...] = ()
    next_allowed_step: str = (
        "historical_data_coverage_checkpoint_or_short_window_"
        "no_lookahead_trial_preparation"
    )

    def __post_init__(self) -> None:
        if self.status not in DataIngestionStatus.ALLOWED:
            raise ValueError(
                f"status must be one of "
                f"{sorted(DataIngestionStatus.ALLOWED)}, got "
                f"{self.status!r}"
            )
        for fname in (
            "ingested_record_count",
            "skipped_record_count",
            "rejected_record_count",
        ):
            v = getattr(self, fname)
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise ValueError(f"{fname} must be a non-negative int")
        if self.manifest is not None and not isinstance(
            self.manifest, HistoricalDataManifest
        ):
            raise TypeError(
                "manifest must be HistoricalDataManifest or None"
            )
        if self.universe_manifest is not None and not isinstance(
            self.universe_manifest, UniverseManifest
        ):
            raise TypeError(
                "universe_manifest must be UniverseManifest or None"
            )
        object.__setattr__(
            self, "warnings", tuple(str(w) for w in self.warnings)
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "status": self.status,
            "ingested_record_count": int(self.ingested_record_count),
            "skipped_record_count": int(self.skipped_record_count),
            "rejected_record_count": int(self.rejected_record_count),
            "manifest": (
                self.manifest.to_dict()
                if self.manifest is not None
                else None
            ),
            "universe_manifest": (
                self.universe_manifest.to_dict()
                if self.universe_manifest is not None
                else None
            ),
            "coverage_report_path": self.coverage_report_path,
            "data_gap_report_path": self.data_gap_report_path,
            "records_path": self.records_path,
            "warnings": list(self.warnings),
            "next_allowed_step": self.next_allowed_step,
            "this_authorises_live_trading": False,
            "this_authorises_auto_tuning": False,
            "this_authorises_real_telegram": False,
            "this_authorises_binance_private_api": False,
            "this_authorises_30d_60d_90d_2y_runner": False,
            "this_authorises_phase_12": False,
            "is_strategy_effectiveness_conclusion": False,
            "is_historical_data_ingestion_result": True,
        }
        out.update(safety_payload())
        out["is_strategy_effectiveness_conclusion"] = False
        assert_no_forbidden_fields(out)
        return out


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------


def _load_rows(path: Path) -> List[Any]:
    """Load rows from a ``.json`` (single array) or ``.jsonl``
    (one JSON value per line) file. Returns ``[]`` for an empty file.
    """
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return []
    if stripped[0] == "[":
        data = json.loads(stripped)
        if not isinstance(data, list):
            raise IngestionSchemaError(
                f"{path} top-level JSON must be an array"
            )
        return list(data)
    rows: List[Any] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _discover_file(root: Path, *candidates: str) -> Optional[Path]:
    for c in candidates:
        p = root / c
        if p.is_file():
            return p
    return None


# ---------------------------------------------------------------------------
# Coverage / gap audit
# ---------------------------------------------------------------------------


def _completeness_state(actual: int, expected: int) -> str:
    if expected <= 0:
        return (
            DataCompletenessState.OK
            if actual > 0
            else DataCompletenessState.UNKNOWN
        )
    if actual <= 0:
        return DataCompletenessState.INCOMPLETE
    ratio = actual / expected
    if ratio >= _COMPLETE_RATIO:
        return DataCompletenessState.OK
    if ratio >= _PARTIAL_RATIO:
        return DataCompletenessState.DEGRADED
    return DataCompletenessState.INCOMPLETE


def _completeness_bucket(actual: int, expected: int) -> str:
    """Map to the brief's COMPLETE / PARTIAL / DEGRADED / INSUFFICIENT
    completeness bucket."""
    if expected <= 0:
        return "COMPLETE" if actual > 0 else "INSUFFICIENT"
    if actual <= 0:
        return "INSUFFICIENT"
    ratio = actual / expected
    if ratio >= _COMPLETE_RATIO:
        return "COMPLETE"
    if ratio >= _PARTIAL_RATIO:
        return "PARTIAL"
    return "DEGRADED"


def _expected_open_times(
    start: datetime, end: datetime, interval: str
) -> List[datetime]:
    seconds = parse_interval_seconds(interval)
    step = timedelta(seconds=seconds)
    out: List[datetime] = []
    cur = start
    while cur < end:
        out.append(cur)
        cur = cur + step
    return out


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class HistoricalDataIngestion:
    """Strict blind walk-forward historical-data ingestion engine.

    The engine reads local files only, parses them into PR95 records,
    builds the data / universe manifests + coverage / gap reports, and
    (optionally) writes deterministic outputs under ``output_root``.
    It NEVER reaches a network, NEVER fabricates real market data, and
    NEVER tunes a parameter. A coverage report is NOT a
    strategy-effectiveness conclusion.
    """

    def __init__(
        self,
        config: HistoricalDataIngestionConfig,
        *,
        generated_at_utc: Optional[datetime] = None,
    ) -> None:
        if not isinstance(config, HistoricalDataIngestionConfig):
            raise TypeError(
                "config must be a HistoricalDataIngestionConfig"
            )
        self.config = config
        self._generated_at = (
            ensure_utc_aware(generated_at_utc, "generated_at_utc")
            if generated_at_utc is not None
            else None
        )
        # Defensive tripwires.
        self.sandbox_only = True
        self.live_trading = False
        self.exchange_live_orders = False
        self.binance_private_api_enabled = False
        self.telegram_outbound_enabled = False
        self.ai_trade_authority = False
        self.trade_authority = False
        self.auto_tuning_allowed = False
        self.phase_12_forbidden = True
        # Populated by ingest().
        self._klines: List[HistoricalKlineRecord] = []
        self._market_records: List[HistoricalMarketRecord] = []
        self._symbol_status: List[SymbolStatusRecord] = []
        self._source_files: List[str] = []
        self._warnings: List[str] = []
        self._rejected = 0
        self._skipped = 0
        self._time_field_error_seen = False
        self._schema_error_seen = False

    # ----- public API -----

    def safety_payload(self) -> Dict[str, Any]:
        return safety_payload()

    def ingest(self) -> HistoricalDataIngestionResult:
        """Parse the configured inputs and build manifests + reports.

        Pure with respect to file inputs; deterministic given the same
        files (and the same fixed ``generated_at_utc`` if provided).
        """
        cfg = self.config
        self._reset()

        if cfg.fixture_mode:
            self._generate_fixture_records()
        else:
            self._load_from_files()

        ingested_count = (
            len(self._klines)
            + len(self._market_records)
            + len(self._symbol_status)
        )

        # Determine status.
        if self._time_field_error_seen:
            status = DataIngestionStatus.INVALIDATED_TIME_FIELDS
        elif self._schema_error_seen and ingested_count == 0:
            status = DataIngestionStatus.FAILED_SCHEMA_VALIDATION
        elif ingested_count == 0:
            status = DataIngestionStatus.INSUFFICIENT_EVIDENCE
            self._warn(
                "no_records_ingested_input_missing_or_empty; "
                "NOT fabricating real market data"
            )
        else:
            status = None  # decided after coverage audit

        manifest = self._build_manifest()
        universe = self._build_universe_manifest()

        if status is None:
            buckets = self._coverage_buckets(manifest)
            if any(
                b in ("PARTIAL", "DEGRADED", "INSUFFICIENT")
                for b in buckets
            ) or self._schema_error_seen:
                status = DataIngestionStatus.PARTIAL_EVIDENCE
            else:
                status = DataIngestionStatus.EVIDENCE_GENERATED

        return HistoricalDataIngestionResult(
            status=status,
            ingested_record_count=ingested_count,
            skipped_record_count=self._skipped,
            rejected_record_count=self._rejected,
            manifest=manifest,
            universe_manifest=universe,
            coverage_report_path=None,
            data_gap_report_path=None,
            records_path=None,
            warnings=tuple(self._warnings),
        )

    def build_store(self) -> HistoricalMarketStore:
        """Build a :class:`HistoricalMarketStore` from ingested records.

        The store is the strict ``available_at <= simulated_time``
        gate that the downstream blind runner uses; this method simply
        loads the parsed records into it (no time-wall bypass).
        """
        store = HistoricalMarketStore()
        store.add_records(self._klines)
        store.add_records(self._market_records)
        store.add_records(self._symbol_status)
        return store

    @property
    def records(self) -> Tuple[_AnyRecord, ...]:
        return (
            tuple(self._klines)
            + tuple(self._market_records)
            + tuple(self._symbol_status)
        )

    def coverage_report(self) -> Dict[str, Any]:
        manifest = self._build_manifest()
        out: Dict[str, Any] = {
            "manifest_id": manifest.manifest_id,
            "data_manifest_hash": manifest.data_manifest_hash,
            "start_time": manifest.start_time.isoformat(),
            "end_time": manifest.end_time.isoformat(),
            "record_counts_by_type": dict(
                manifest.record_counts_by_type
            ),
            "coverage_by_symbol": copy.deepcopy(
                dict(manifest.coverage_by_symbol)
            ),
            "late_arrival_count": manifest.late_arrival_count,
            "revised_record_count": manifest.revised_record_count,
            "warnings": list(manifest.warnings),
            "is_coverage_report": True,
        }
        out.update(safety_payload())
        out["is_strategy_effectiveness_conclusion"] = False
        assert_no_forbidden_fields(out)
        return out

    def data_gap_report(self) -> Dict[str, Any]:
        manifest = self._build_manifest()
        out: Dict[str, Any] = {
            "manifest_id": manifest.manifest_id,
            "data_manifest_hash": manifest.data_manifest_hash,
            "start_time": manifest.start_time.isoformat(),
            "end_time": manifest.end_time.isoformat(),
            "data_gap_summary": copy.deepcopy(
                dict(manifest.data_gap_summary)
            ),
            "warnings": list(manifest.warnings),
            "is_data_gap_report": True,
        }
        out.update(safety_payload())
        out["is_strategy_effectiveness_conclusion"] = False
        assert_no_forbidden_fields(out)
        return out

    def write_outputs(self) -> HistoricalDataIngestionResult:
        """Run :meth:`ingest` and write all artefacts under
        ``output_root``. Returns the result with output paths filled."""
        result = self.ingest()
        out_root = Path(self.config.output_root)
        out_root.mkdir(parents=True, exist_ok=True)

        manifest_path = out_root / "historical_data_manifest.json"
        universe_path = out_root / "universe_manifest.json"
        coverage_path = out_root / "coverage_report.json"
        gap_path = out_root / "data_gap_report.json"
        records_path = out_root / "records.jsonl"

        _write_json(
            manifest_path,
            result.manifest.to_dict()
            if result.manifest is not None
            else {"manifest": None},
        )
        _write_json(
            universe_path,
            result.universe_manifest.to_dict()
            if result.universe_manifest is not None
            else {"universe_manifest": None},
        )
        _write_json(coverage_path, self.coverage_report())
        _write_json(gap_path, self.data_gap_report())
        self._write_records_jsonl(records_path)

        return HistoricalDataIngestionResult(
            status=result.status,
            ingested_record_count=result.ingested_record_count,
            skipped_record_count=result.skipped_record_count,
            rejected_record_count=result.rejected_record_count,
            manifest=result.manifest,
            universe_manifest=result.universe_manifest,
            coverage_report_path=str(coverage_path),
            data_gap_report_path=str(gap_path),
            records_path=str(records_path),
            warnings=result.warnings,
        )

    # ----- internals: state -----

    def _reset(self) -> None:
        self._klines = []
        self._market_records = []
        self._symbol_status = []
        self._source_files = []
        self._warnings = []
        self._rejected = 0
        self._skipped = 0
        self._time_field_error_seen = False
        self._schema_error_seen = False

    def _warn(self, msg: str) -> None:
        if msg not in self._warnings:
            self._warnings.append(msg)

    def _in_window(self, event_time: datetime) -> bool:
        return self.config.start_time <= event_time < self.config.end_time

    def _record_parse_error(self, context: str, exc: Exception) -> None:
        self._rejected += 1
        if isinstance(exc, IngestionTimeFieldError):
            self._time_field_error_seen = True
        elif isinstance(exc, IngestionSchemaError):
            self._schema_error_seen = True
        else:
            self._schema_error_seen = True
        self._warn(f"rejected_row[{context}]: {exc}")

    def _add_kline(self, rec: HistoricalKlineRecord) -> None:
        if self._in_window(rec.open_time):
            self._klines.append(rec)
        else:
            self._skipped += 1

    def _add_market(self, rec: HistoricalMarketRecord) -> None:
        if self._in_window(rec.event_time):
            self._market_records.append(rec)
        else:
            self._skipped += 1

    def _add_symbol_status(self, rec: SymbolStatusRecord) -> None:
        # Symbol-status records describe listing timelines that may
        # predate the window; always retain them (no survivorship
        # bias) but only count those relevant to the window symbols.
        self._symbol_status.append(rec)

    # ----- internals: loading -----

    def _load_from_files(self) -> None:
        cfg = self.config
        root = Path(cfg.input_root)
        if not root.exists() or not root.is_dir():
            self._warn(
                f"input_root_not_found_or_not_a_directory: "
                f"{cfg.input_root}"
            )
            return

        symbols = list(cfg.symbols)
        if not symbols:
            symbols = self._discover_symbols(root)
            if not symbols:
                self._warn(
                    "no_symbols_configured_and_none_discovered_under_"
                    "input_root"
                )

        for symbol in symbols:
            for interval in cfg.intervals:
                self._load_klines(root, symbol, interval)
            if cfg.include_funding:
                self._load_market(
                    root,
                    "funding",
                    symbol,
                    parse_funding_row,
                    DataQualityFlag.FUNDING_MISSING,
                )
            if cfg.include_open_interest:
                self._load_market(
                    root,
                    "open_interest",
                    symbol,
                    parse_open_interest_row,
                    DataQualityFlag.OI_MISSING,
                )
            if cfg.include_ticker_24h:
                self._load_market(
                    root,
                    "ticker_24h",
                    symbol,
                    parse_ticker_24h_row,
                    DataQualityFlag.TICKER_MISSING,
                )

        if cfg.include_symbol_status or cfg.include_exchange_info:
            self._load_symbol_status(root)

    def _discover_symbols(self, root: Path) -> List[str]:
        symbols: set = set()
        klines_dir = root / "klines"
        if klines_dir.is_dir():
            for p in sorted(klines_dir.glob("*")):
                if p.is_dir():
                    symbols.add(p.name)
                elif p.suffix in (".json", ".jsonl"):
                    # filename like BTCUSDT_1m.jsonl
                    stem = p.stem
                    if "_" in stem:
                        symbols.add(stem.rsplit("_", 1)[0])
        return sorted(symbols)

    def _load_klines(
        self, root: Path, symbol: str, interval: str
    ) -> None:
        path = _discover_file(
            root,
            f"klines/{symbol}/{interval}.jsonl",
            f"klines/{symbol}/{interval}.json",
            f"klines/{symbol}_{interval}.jsonl",
            f"klines/{symbol}_{interval}.json",
        )
        if path is None:
            return
        self._source_files.append(str(path))
        try:
            rows = _load_rows(path)
        except (json.JSONDecodeError, IngestionSchemaError) as exc:
            self._record_parse_error(f"klines:{symbol}:{interval}", exc)
            return
        for idx, row in enumerate(rows):
            try:
                rec = parse_kline_row(
                    row,
                    symbol=symbol,
                    interval=interval,
                    source=self.config.source_type,
                    default_availability_lag_seconds=(
                        self.config.default_availability_lag_seconds
                    ),
                )
            except (IngestionSchemaError, ValueError, TypeError) as exc:
                self._record_parse_error(
                    f"klines:{symbol}:{interval}:{idx}", exc
                )
                continue
            self._add_kline(rec)

    def _load_market(
        self,
        root: Path,
        kind: str,
        symbol: str,
        parser,
        missing_flag: str,
    ) -> None:
        path = _discover_file(
            root,
            f"{kind}/{symbol}.jsonl",
            f"{kind}/{symbol}.json",
            f"{kind}/{symbol}/data.jsonl",
        )
        if path is None:
            self._warn(f"{kind}_missing_for_symbol:{symbol}")
            return
        self._source_files.append(str(path))
        try:
            rows = _load_rows(path)
        except (json.JSONDecodeError, IngestionSchemaError) as exc:
            self._record_parse_error(f"{kind}:{symbol}", exc)
            return
        for idx, row in enumerate(rows):
            try:
                rec = parser(
                    row,
                    symbol=symbol,
                    source=self.config.source_type,
                    default_availability_lag_seconds=(
                        self.config.default_availability_lag_seconds
                    ),
                )
            except (IngestionSchemaError, ValueError, TypeError) as exc:
                self._record_parse_error(f"{kind}:{symbol}:{idx}", exc)
                continue
            self._add_market(rec)

    def _load_symbol_status(self, root: Path) -> None:
        path = _discover_file(
            root,
            "symbol_status.jsonl",
            "symbol_status.json",
            "exchange_info.jsonl",
            "exchange_info.json",
        )
        if path is None:
            self._warn("symbol_status_file_missing")
            return
        self._source_files.append(str(path))
        try:
            rows = _load_rows(path)
        except (json.JSONDecodeError, IngestionSchemaError) as exc:
            self._record_parse_error("symbol_status", exc)
            return
        for idx, row in enumerate(rows):
            try:
                rec = parse_symbol_status_row(
                    row,
                    source=self.config.source_type,
                    default_availability_lag_seconds=(
                        self.config.default_availability_lag_seconds
                    ),
                )
            except (IngestionSchemaError, ValueError, TypeError) as exc:
                self._record_parse_error(f"symbol_status:{idx}", exc)
                continue
            self._add_symbol_status(rec)

    # ----- internals: fixture mode -----

    def _generate_fixture_records(self) -> None:
        """Generate a small, deterministic, clearly-synthetic dataset.

        Fixtures carry ``source_type=MANUAL_FIXTURE_FILE``-derived
        sources and a ``SYNTHETIC_FIXTURE_NOT_REAL_MARKET_DATA``
        warning so they can never be confused with real market data.
        """
        cfg = self.config
        self._warn(
            "SYNTHETIC_FIXTURE_NOT_REAL_MARKET_DATA: deterministic "
            "fixture generated because fixture_mode=True; this is NOT "
            "real market data and proves nothing about strategy "
            "effectiveness"
        )
        symbols = list(cfg.symbols) or ["BTCUSDT", "ETHUSDT"]
        source = "MANUAL_FIXTURE_FILE:synthetic"
        for sym_index, symbol in enumerate(symbols):
            base_price = 100.0 + 10.0 * sym_index
            # Symbol-status fixture (listed before the window).
            try:
                self._add_symbol_status(
                    parse_symbol_status_row(
                        {
                            "symbol": symbol,
                            "market_type": "PERP",
                            "status": SymbolStatus.TRADING,
                            "listed_at": (
                                cfg.start_time - timedelta(days=1)
                            ).isoformat(),
                            "available_at": (
                                cfg.start_time - timedelta(days=1)
                            ).isoformat(),
                            "contract_type": "PERPETUAL",
                        },
                        source=source,
                    )
                )
            except (IngestionSchemaError, ValueError) as exc:
                self._record_parse_error(
                    f"fixture_symbol_status:{symbol}", exc
                )
            for interval in cfg.intervals:
                seconds = parse_interval_seconds(interval)
                step = timedelta(seconds=seconds)
                open_times = _expected_open_times(
                    cfg.start_time, cfg.end_time, interval
                )
                for i, ot in enumerate(open_times):
                    price = base_price + float(i)
                    row = {
                        "open_time": ot.isoformat(),
                        "open": price,
                        "high": price + 1.0,
                        "low": price - 1.0,
                        "close": price + 0.5,
                        "volume": 1000.0 + float(i),
                    }
                    try:
                        rec = parse_kline_row(
                            row,
                            symbol=symbol,
                            interval=interval,
                            source=source,
                            default_availability_lag_seconds=(
                                cfg.default_availability_lag_seconds
                            ),
                        )
                    except (IngestionSchemaError, ValueError) as exc:
                        self._record_parse_error(
                            f"fixture_kline:{symbol}:{interval}:{i}",
                            exc,
                        )
                        continue
                    self._add_kline(rec)
                _ = step  # silence unused in case open_times empty
            # One funding / OI / ticker fixture at window start.
            if cfg.include_funding:
                self._safe_add_market_fixture(
                    parse_funding_row,
                    {
                        "symbol": symbol,
                        "event_time": cfg.start_time.isoformat(),
                        "funding_rate": 0.0001,
                        "funding_interval_hours": 8.0,
                    },
                    source,
                    f"fixture_funding:{symbol}",
                )
            if cfg.include_open_interest:
                self._safe_add_market_fixture(
                    parse_open_interest_row,
                    {
                        "symbol": symbol,
                        "event_time": cfg.start_time.isoformat(),
                        "open_interest": 1_000_000.0,
                        "open_interest_value": 1_000_000.0 * base_price,
                    },
                    source,
                    f"fixture_oi:{symbol}",
                )
            if cfg.include_ticker_24h:
                self._safe_add_market_fixture(
                    parse_ticker_24h_row,
                    {
                        "symbol": symbol,
                        "event_time": cfg.start_time.isoformat(),
                        "last_price": base_price,
                        "price_change_percent": 1.5,
                        "quote_volume": 5_000_000.0,
                    },
                    source,
                    f"fixture_ticker:{symbol}",
                )
        self._source_files.append("<deterministic-fixture>")

    def _safe_add_market_fixture(
        self, parser, row, source, context
    ) -> None:
        try:
            rec = parser(
                row,
                symbol=row["symbol"],
                source=source,
                default_availability_lag_seconds=(
                    self.config.default_availability_lag_seconds
                ),
            )
        except (IngestionSchemaError, ValueError) as exc:
            self._record_parse_error(context, exc)
            return
        self._add_market(rec)

    # ----- internals: manifests + coverage -----

    def _record_counts_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for rec in self._klines:
            counts[rec.record_type] = counts.get(rec.record_type, 0) + 1
        for rec in self._market_records:
            counts[rec.record_type] = counts.get(rec.record_type, 0) + 1
        for rec in self._symbol_status:
            counts[rec.record_type] = counts.get(rec.record_type, 0) + 1
        return dict(sorted(counts.items()))

    def _window_symbols(self) -> List[str]:
        cfg = self.config
        if cfg.symbols:
            return list(cfg.symbols)
        symbols: set = set()
        for rec in self._klines:
            symbols.add(rec.symbol)
        for rec in self._market_records:
            if rec.symbol:
                symbols.add(rec.symbol)
        for rec in self._symbol_status:
            symbols.add(rec.symbol)
        return sorted(symbols)

    def _build_coverage_and_gaps(
        self,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], int, int]:
        cfg = self.config
        symbols = self._window_symbols()
        coverage_by_symbol: Dict[str, Any] = {}
        gaps_by_symbol_interval: Dict[str, List[str]] = {}
        symbol_status_gaps: List[str] = []
        funding_missing: List[str] = []
        oi_missing: List[str] = []
        ticker_missing: List[str] = []
        total_missing_kline = 0

        late_count = 0
        revised_count = 0
        for rec in self.records:
            if getattr(rec, "late_arrival", False):
                late_count += 1
            if getattr(rec, "revised_from_record_id", None):
                revised_count += 1

        for symbol in symbols:
            sym_counts: Dict[str, int] = {}
            kline_coverage: Dict[str, Any] = {}
            sym_states: List[str] = []
            for interval in cfg.intervals:
                rtype = (
                    HistoricalMarketRecordType.KLINE_1M
                    if interval == "1m"
                    else HistoricalMarketRecordType.KLINE_5M
                )
                actual_open_times = sorted(
                    {
                        rec.open_time
                        for rec in self._klines
                        if rec.symbol == symbol
                        and rec.interval == interval
                    }
                )
                actual = len(actual_open_times)
                sym_counts[rtype] = actual
                expected_times = _expected_open_times(
                    cfg.start_time, cfg.end_time, interval
                )
                expected = len(expected_times)
                actual_set = set(actual_open_times)
                missing = [
                    t.isoformat()
                    for t in expected_times
                    if t not in actual_set
                ]
                if missing:
                    gaps_by_symbol_interval[
                        f"{symbol}|{interval}"
                    ] = missing
                    total_missing_kline += len(missing)
                    self._warn(
                        f"kline_gap[{symbol}|{interval}]: "
                        f"{len(missing)} missing of {expected}"
                    )
                bucket = _completeness_bucket(actual, expected)
                state = _completeness_state(actual, expected)
                sym_states.append(state)
                kline_coverage[interval] = {
                    "expected": expected,
                    "actual": actual,
                    "missing_count": len(missing),
                    "completeness_bucket": bucket,
                    "completeness_state": state,
                }

            funding_n = sum(
                1
                for rec in self._market_records
                if rec.symbol == symbol
                and rec.record_type
                == HistoricalMarketRecordType.FUNDING_RATE
            )
            oi_n = sum(
                1
                for rec in self._market_records
                if rec.symbol == symbol
                and rec.record_type
                == HistoricalMarketRecordType.OPEN_INTEREST
            )
            ticker_n = sum(
                1
                for rec in self._market_records
                if rec.symbol == symbol
                and rec.record_type
                == HistoricalMarketRecordType.TICKER_24H
            )
            sym_counts[
                HistoricalMarketRecordType.FUNDING_RATE
            ] = funding_n
            sym_counts[
                HistoricalMarketRecordType.OPEN_INTEREST
            ] = oi_n
            sym_counts[HistoricalMarketRecordType.TICKER_24H] = ticker_n
            status_n = sum(
                1
                for rec in self._symbol_status
                if rec.symbol == symbol
            )
            sym_counts[
                HistoricalMarketRecordType.SYMBOL_STATUS
            ] = status_n

            if cfg.include_funding and funding_n == 0:
                funding_missing.append(symbol)
                self._warn(f"funding_missing_warning:{symbol}")
            if cfg.include_open_interest and oi_n == 0:
                oi_missing.append(symbol)
                self._warn(f"open_interest_missing_warning:{symbol}")
            if cfg.include_ticker_24h and ticker_n == 0:
                ticker_missing.append(symbol)
                self._warn(f"ticker_missing_warning:{symbol}")
            if status_n == 0:
                symbol_status_gaps.append(symbol)
                self._warn(f"symbol_status_gap:{symbol}")

            # Overall symbol completeness = worst kline bucket, or
            # INSUFFICIENT if there are no klines at all.
            if sym_states:
                if DataCompletenessState.INCOMPLETE in sym_states:
                    overall = DataCompletenessState.INCOMPLETE
                elif DataCompletenessState.DEGRADED in sym_states:
                    overall = DataCompletenessState.DEGRADED
                elif DataCompletenessState.UNKNOWN in sym_states:
                    overall = DataCompletenessState.UNKNOWN
                else:
                    overall = DataCompletenessState.OK
            else:
                overall = DataCompletenessState.UNKNOWN

            coverage_by_symbol[symbol] = {
                "record_counts_by_type": dict(
                    sorted(sym_counts.items())
                ),
                "kline_coverage": kline_coverage,
                "completeness_state": overall,
            }

        data_gap_summary = {
            "total_missing_kline_count": total_missing_kline,
            "gaps_by_symbol_interval": dict(
                sorted(gaps_by_symbol_interval.items())
            ),
            "symbol_status_gaps": sorted(symbol_status_gaps),
            "funding_missing_symbols": sorted(funding_missing),
            "open_interest_missing_symbols": sorted(oi_missing),
            "ticker_missing_symbols": sorted(ticker_missing),
        }
        return (
            coverage_by_symbol,
            data_gap_summary,
            late_count,
            revised_count,
        )

    def _coverage_buckets(
        self, manifest: HistoricalDataManifest
    ) -> List[str]:
        out: List[str] = []
        for sym_cov in manifest.coverage_by_symbol.values():
            for iv_cov in sym_cov.get("kline_coverage", {}).values():
                out.append(iv_cov.get("completeness_bucket", ""))
        return out

    def _build_manifest(self) -> HistoricalDataManifest:
        cfg = self.config
        (
            coverage_by_symbol,
            data_gap_summary,
            late_count,
            revised_count,
        ) = self._build_coverage_and_gaps()
        return HistoricalDataManifest(
            input_root=cfg.input_root,
            start_time=cfg.start_time,
            end_time=cfg.end_time,
            symbols=tuple(self._window_symbols()),
            intervals=cfg.intervals,
            source_type=cfg.source_type,
            record_counts_by_type=self._record_counts_by_type(),
            coverage_by_symbol=coverage_by_symbol,
            data_gap_summary=data_gap_summary,
            late_arrival_count=late_count,
            revised_record_count=revised_count,
            source_files=tuple(sorted(set(self._source_files))),
            warnings=tuple(self._warnings),
            generated_at_utc=self._generated_at,
        )

    def _build_universe_manifest(self) -> UniverseManifest:
        cfg = self.config
        warnings: List[str] = []
        if not self._symbol_status:
            warnings.append(
                "no_symbol_status_records_universe_empty_no_"
                "survivorship_inference"
            )
        return UniverseManifest(
            start_time=cfg.start_time,
            end_time=cfg.end_time,
            symbol_status_records=tuple(self._symbol_status),
            warnings=tuple(warnings),
            generated_at_utc=self._generated_at,
        )

    def _write_records_jsonl(self, path: Path) -> None:
        lines: List[str] = []
        for rec in self.records:
            lines.append(
                json.dumps(rec.to_dict(), sort_keys=True)
            )
        path.write_text(
            ("\n".join(lines) + ("\n" if lines else "")),
            encoding="utf-8",
        )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2),
        encoding="utf-8",
    )


__all__ = [
    "PHASE_NAME",
    "SUPPORTED_KLINE_INTERVALS",
    "HistoricalDataSourceType",
    "DataIngestionStatus",
    "HistoricalDataIngestionConfig",
    "HistoricalDataIngestionResult",
    "HistoricalDataIngestion",
    "HistoricalDataManifest",
    "UniverseManifest",
    "IngestionSchemaError",
    "IngestionTimeFieldError",
    "parse_kline_row",
    "parse_funding_row",
    "parse_open_interest_row",
    "parse_ticker_24h_row",
    "parse_symbol_status_row",
    "compute_artefact_hash",
    "safety_payload",
]
