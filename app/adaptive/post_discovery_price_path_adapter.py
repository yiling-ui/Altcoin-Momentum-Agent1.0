"""Phase 11C.1C-C-B-B-B-D-B.1 - Post-Discovery Outcome Price Path
Adapter v0 / *Kline Path Adapter v0*.

This module is paper / report / evidence ONLY. It does NOT and
CANNOT:

    * authorise a real trade,
    * modify a real position,
    * read a private exchange API,
    * sign a request,
    * call an LLM, DeepSeek, or Telegram outbound transport,
    * change ``symbol_limit``, candidate-pool capacity, anomaly
      thresholds, Regime weights, runtime config, or any other
      runtime knob,
    * recommend a direction (long / short / entry / exit /
      stop / target / position size / leverage).

Phase 12 remains FORBIDDEN. The Risk Engine remains the single
trade-decision gate.

Purpose
-------
The Phase 11C.1C-C-B-B-B-D-B (Post-Discovery Outcome Metrics v0)
evaluator needs two anchors per audited mover to compute anything
other than ``INSUFFICIENT_PRICE_PATH``:

    * ``first_seen_price`` - a positive price observed AT or
      BEFORE ``first_seen_time_utc_ms``,
    * ``price_path_after_first_seen`` - a sequence of price
      observations whose timestamps are strictly AFTER
      ``first_seen_time_utc_ms``.

The Phase 11C.1C-C-B-B-B-D-A v0 audit records do **not** carry
either anchor. On the operator VPS this surfaces as 195 / 300
records labelled ``INSUFFICIENT_PRICE_PATH`` because the D-B
runner has nothing to evaluate.

This adapter closes that gap by reading the local Historical
Market Store (``data/historical_market_store/top_movers/*.jsonl``)
that Phase 11C.1C-C-B-B-B-D-A.1 already builds and synthesising a
daily-resolution price path per symbol.

Lookahead Guard
---------------
Strictly enforced:

    1. ``first_seen_time_utc_ms`` is **never** modified - it is a
       read-only input.
    2. ``first_seen_price`` is taken **only** from the open of the
       day-bucket whose ``day_start <= first_seen_time < day_end``.
       The open's timestamp is the day's ``mover_window_start_utc_ms``
       which is by construction <= ``first_seen_time``.
    3. ``price_path_after_first_seen`` only contains points whose
       timestamps are strictly AFTER ``first_seen_time_utc_ms``.
       For the containing day, only the close at
       ``mover_window_end_utc_ms`` is emitted (close is by
       construction > ``first_seen_time``); the day's open / high
       / low are dropped because their precise intra-day timing is
       unknown and may have been before ``first_seen_time``.
       For days that begin strictly after the containing day, open
       (at ``mover_window_start_utc_ms``) and close (at
       ``mover_window_end_utc_ms``) are both lookahead-safe; the
       day's high / low are also emitted but stamped at
       ``mover_window_end_utc_ms`` because the local store does not
       record their intra-day timestamps. This is descriptively
       conservative for ``time_to_peak_seconds`` and is recorded
       on the resolution as ``approximate_intra_day_timestamps``.
    4. The price path NEVER feeds the live radar score, candidate
       promotion, Risk Engine, Execution FSM, or any runtime knob.
    5. ``OutcomeLabel`` derived from this path is descriptive
       only; it never modifies a runtime parameter.

The adapter never calls a network endpoint, never reads a private
API, and never signs a request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from app.adaptive.historical_mover_coverage_backfill import (
    HistoricalMarketStoreSnapshot,
    load_historical_market_store,
)
from app.adaptive.post_discovery_outcome_metrics import PricePoint


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


POST_DISCOVERY_PRICE_PATH_ADAPTER_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_b_1.post_discovery_price_path_adapter.v0"
)
POST_DISCOVERY_PRICE_PATH_ADAPTER_SOURCE_PHASE: str = (
    "phase_11c_1c_c_b_b_b_d_b_1_post_discovery_price_path_adapter_v0"
)
POST_DISCOVERY_PRICE_PATH_ADAPTER_SCHEMA_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_b_1.post_discovery_price_path_adapter.v1"
)


# ---------------------------------------------------------------------------
# Closed taxonomies
# ---------------------------------------------------------------------------


class PricePathSource:
    """Closed enumeration describing where a resolved price path
    came from. Descriptive only - never an input to any runtime
    knob.
    """

    HISTORICAL_MARKET_STORE_DAILY_TOP_MOVERS: str = (
        "historical_market_store_daily_top_movers"
    )
    OPERATOR_SUPPLIED_PATH: str = "operator_supplied_path"
    ABSENT: str = "absent"

    ALL: tuple[str, ...] = (
        HISTORICAL_MARKET_STORE_DAILY_TOP_MOVERS,
        OPERATOR_SUPPLIED_PATH,
        ABSENT,
    )


class PricePathMissingReason:
    """Closed enumeration describing *why* a price path could not be
    constructed.

    Descriptive only - the runner surfaces these reasons in
    ``price_path_missing_reason_summary`` so an operator can act
    on the data gap without the runner needing to invent prices.
    """

    NONE: str = "none"

    HISTORICAL_STORE_DIR_NOT_PROVIDED: str = (
        "historical_store_dir_not_provided"
    )
    HISTORICAL_STORE_DIR_MISSING: str = "historical_store_dir_missing"
    HISTORICAL_STORE_EMPTY: str = "historical_store_empty"

    SYMBOL_NOT_IN_HISTORICAL_STORE: str = "symbol_not_in_historical_store"

    NO_FIRST_SEEN_TIME: str = "no_first_seen_time"
    NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME: str = (
        "no_top_mover_row_covering_first_seen_time"
    )
    INSUFFICIENT_POST_FIRST_SEEN_POINTS: str = (
        "insufficient_post_first_seen_points"
    )
    INVALID_FIRST_SEEN_PRICE_FROM_STORE: str = (
        "invalid_first_seen_price_from_store"
    )

    ALL: tuple[str, ...] = (
        NONE,
        HISTORICAL_STORE_DIR_NOT_PROVIDED,
        HISTORICAL_STORE_DIR_MISSING,
        HISTORICAL_STORE_EMPTY,
        SYMBOL_NOT_IN_HISTORICAL_STORE,
        NO_FIRST_SEEN_TIME,
        NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME,
        INSUFFICIENT_POST_FIRST_SEEN_POINTS,
        INVALID_FIRST_SEEN_PRICE_FROM_STORE,
    )


#: Default kline interval label emitted by the v0 adapter. The
#: local Historical Market Store assembles per-day buckets from 1h
#: candles, so the adapter's effective resolution is daily ("1d").
DEFAULT_KLINE_INTERVAL_USED: str = "1d"


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PricePathResolution:
    """Result of resolving a price path for one (symbol,
    first_seen_time) pair. Descriptive only.

    ``first_seen_price`` is None when the adapter could not find a
    lookahead-safe anchor. ``price_path`` is empty when the
    adapter could not assemble at least one post-first-seen point.
    ``source`` records which loader produced the path.
    ``missing_reason`` is :attr:`PricePathMissingReason.NONE`
    when the resolution is complete; otherwise it explains exactly
    why the path could not be assembled so an operator can fix
    the data gap.
    """

    symbol: str
    first_seen_time_utc_ms: int | None
    first_seen_price: float | None
    price_path: tuple[PricePoint, ...]
    source: str
    missing_reason: str
    kline_interval_used: str = DEFAULT_KLINE_INTERVAL_USED
    approximate_intra_day_timestamps: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def is_loaded(self) -> bool:
        """A resolution counts as loaded when at least one
        post-first-seen point is present (i.e. the evaluator can
        compute SOMETHING). The minimum-points guard belongs to
        the evaluator, not the adapter; the adapter's job is to
        report whether there was data to feed in at all.
        """

        return bool(self.price_path) and self.first_seen_price is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": str(self.symbol),
            "first_seen_time_utc_ms": (
                int(self.first_seen_time_utc_ms)
                if self.first_seen_time_utc_ms is not None
                else None
            ),
            "first_seen_price": (
                float(self.first_seen_price)
                if self.first_seen_price is not None
                else None
            ),
            "price_path": [p.to_dict() for p in self.price_path],
            "source": str(self.source),
            "missing_reason": str(self.missing_reason),
            "kline_interval_used": str(self.kline_interval_used),
            "approximate_intra_day_timestamps": bool(
                self.approximate_intra_day_timestamps
            ),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_pos_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out <= 0.0:
        return None
    return out


@dataclass(frozen=True)
class _DailyRow:
    """Internal view of one Historical Market Store daily mover row.

    All attributes are derived from the lookahead-guarded
    ``top_movers/*.jsonl`` rows produced by Phase
    11C.1C-C-B-B-B-D-A.1's
    :func:`scripts.build_historical_mover_reference_store.run_build`.
    """

    symbol: str
    day_start_utc_ms: int
    day_end_utc_ms: int
    open_price: float | None
    high_price: float | None
    low_price: float | None
    close_price: float | None


def _row_from_mapping(raw: Mapping[str, Any]) -> _DailyRow | None:
    symbol_raw = raw.get("symbol")
    if not isinstance(symbol_raw, str) or not symbol_raw:
        return None
    day_start = _coerce_int(raw.get("mover_window_start_utc_ms"))
    day_end = _coerce_int(raw.get("mover_window_end_utc_ms"))
    if day_start is None or day_end is None:
        return None
    if day_end <= day_start:
        return None
    open_price = _coerce_pos_float(raw.get("open_price"))
    high_price = _coerce_pos_float(raw.get("high_price"))
    low_price = _coerce_pos_float(raw.get("low_price"))
    close_price = _coerce_pos_float(raw.get("close_price"))
    return _DailyRow(
        symbol=str(symbol_raw),
        day_start_utc_ms=int(day_start),
        day_end_utc_ms=int(day_end),
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
    )


class HistoricalPricePathAdapter:
    """Resolve price-path inputs for the Phase 11C.1C-C-B-B-B-D-B
    evaluator from the local Historical Market Store.

    The adapter is constructed with either:

      * ``historical_store_dir`` - a Path to a directory in the
        ``load_historical_market_store`` layout, OR
      * ``snapshot`` - a pre-loaded
        :class:`HistoricalMarketStoreSnapshot` (for tests / when
        the caller already loaded the store).

    Either argument may be ``None``; the adapter then resolves
    every symbol with ``source = ABSENT`` and a clear missing
    reason, never fabricates a price.

    The adapter never opens a network socket and never reads a
    private API.
    """

    def __init__(
        self,
        *,
        historical_store_dir: Path | None = None,
        snapshot: HistoricalMarketStoreSnapshot | None = None,
        kline_interval_used: str = DEFAULT_KLINE_INTERVAL_USED,
    ) -> None:
        self._kline_interval_used = str(kline_interval_used)
        self._initial_missing_reason: str = PricePathMissingReason.NONE
        self._available: bool = False
        self._rows_by_symbol: dict[str, list[_DailyRow]] = {}

        loaded_snapshot: HistoricalMarketStoreSnapshot | None = None

        if snapshot is not None:
            loaded_snapshot = snapshot
        elif historical_store_dir is None:
            self._initial_missing_reason = (
                PricePathMissingReason.HISTORICAL_STORE_DIR_NOT_PROVIDED
            )
        else:
            store_path = Path(historical_store_dir)
            if not store_path.is_dir():
                self._initial_missing_reason = (
                    PricePathMissingReason.HISTORICAL_STORE_DIR_MISSING
                )
            else:
                try:
                    loaded_snapshot = load_historical_market_store(store_path)
                except Exception:
                    # Defence-in-depth: a malformed store file
                    # raises a HistoricalMoverLookaheadGuardError;
                    # the runner expects an unconditional
                    # resolution stream so we surface the failure
                    # via missing_reason instead of letting it
                    # crash the runner.
                    self._initial_missing_reason = (
                        PricePathMissingReason.HISTORICAL_STORE_EMPTY
                    )
                    loaded_snapshot = None

        if loaded_snapshot is not None:
            self._index_snapshot(loaded_snapshot)
            if not self._rows_by_symbol:
                self._initial_missing_reason = (
                    PricePathMissingReason.HISTORICAL_STORE_EMPTY
                )
            else:
                self._available = True

    # ------------------------------------------------------------------
    # Read-only accessors
    # ------------------------------------------------------------------
    @property
    def kline_interval_used(self) -> str:
        return self._kline_interval_used

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def initial_missing_reason(self) -> str:
        return self._initial_missing_reason

    @property
    def indexed_symbol_count(self) -> int:
        return len(self._rows_by_symbol)

    def has_symbol(self, symbol: str) -> bool:
        return str(symbol) in self._rows_by_symbol

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------
    def _index_snapshot(
        self, snapshot: HistoricalMarketStoreSnapshot
    ) -> None:
        index: dict[str, list[_DailyRow]] = {}
        for raw in snapshot.top_mover_rows:
            row = _row_from_mapping(raw)
            if row is None:
                continue
            index.setdefault(row.symbol, []).append(row)
        # Sort each symbol's rows by day_start_utc_ms ascending
        # so containing-day lookup is deterministic.
        for symbol in index:
            index[symbol].sort(key=lambda r: r.day_start_utc_ms)
        self._rows_by_symbol = index

    # ------------------------------------------------------------------
    # Resolve
    # ------------------------------------------------------------------
    def resolve(
        self,
        *,
        symbol: str,
        first_seen_time_utc_ms: int | None,
        reference_window_end_utc_ms: int | None = None,
    ) -> PricePathResolution:
        """Resolve a price path for one (symbol, first_seen_time)
        pair. The returned resolution is paper / report / evidence
        only.

        ``reference_window_end_utc_ms`` is an optional upper bound
        that clips post-first-seen rows so the path does not
        stretch past the audit window. When ``None``, the adapter
        emits every post-first-seen row it has on disk.
        """

        sym = str(symbol or "")
        first_seen = first_seen_time_utc_ms
        notes: list[str] = []

        if not self._available:
            return PricePathResolution(
                symbol=sym,
                first_seen_time_utc_ms=first_seen,
                first_seen_price=None,
                price_path=(),
                source=PricePathSource.ABSENT,
                missing_reason=self._initial_missing_reason,
                kline_interval_used=self._kline_interval_used,
                approximate_intra_day_timestamps=False,
                notes=tuple(notes),
            )

        if first_seen is None:
            return PricePathResolution(
                symbol=sym,
                first_seen_time_utc_ms=None,
                first_seen_price=None,
                price_path=(),
                source=PricePathSource.ABSENT,
                missing_reason=PricePathMissingReason.NO_FIRST_SEEN_TIME,
                kline_interval_used=self._kline_interval_used,
                approximate_intra_day_timestamps=False,
                notes=tuple(notes),
            )

        rows = self._rows_by_symbol.get(sym)
        if not rows:
            return PricePathResolution(
                symbol=sym,
                first_seen_time_utc_ms=first_seen,
                first_seen_price=None,
                price_path=(),
                source=PricePathSource.ABSENT,
                missing_reason=(
                    PricePathMissingReason.SYMBOL_NOT_IN_HISTORICAL_STORE
                ),
                kline_interval_used=self._kline_interval_used,
                approximate_intra_day_timestamps=False,
                notes=tuple(notes),
            )

        # Lookahead Guard: containing-day = first row whose
        # day_start <= first_seen_time < day_end. The store may
        # have multiple snapshots per day (rare); we use the
        # first matching row for determinism.
        containing_row: _DailyRow | None = None
        for row in rows:
            if row.day_start_utc_ms <= first_seen < row.day_end_utc_ms:
                containing_row = row
                break

        if containing_row is None:
            return PricePathResolution(
                symbol=sym,
                first_seen_time_utc_ms=first_seen,
                first_seen_price=None,
                price_path=(),
                source=PricePathSource.ABSENT,
                missing_reason=(
                    PricePathMissingReason
                    .NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME
                ),
                kline_interval_used=self._kline_interval_used,
                approximate_intra_day_timestamps=False,
                notes=tuple(notes),
            )

        first_seen_price = containing_row.open_price
        if first_seen_price is None or first_seen_price <= 0.0:
            return PricePathResolution(
                symbol=sym,
                first_seen_time_utc_ms=first_seen,
                first_seen_price=None,
                price_path=(),
                source=PricePathSource.ABSENT,
                missing_reason=(
                    PricePathMissingReason.INVALID_FIRST_SEEN_PRICE_FROM_STORE
                ),
                kline_interval_used=self._kline_interval_used,
                approximate_intra_day_timestamps=False,
                notes=tuple(notes),
            )

        # Build the post-first-seen path.
        path_points: list[PricePoint] = []
        approximate_timestamps: bool = False
        upper_bound = (
            int(reference_window_end_utc_ms)
            if reference_window_end_utc_ms is not None
            else None
        )

        # Containing day: only include the close at day_end
        # (timestamp is by construction strictly > first_seen_time
        # because day_start <= first_seen_time < day_end). The
        # day's open / high / low timestamps are not necessarily
        # > first_seen_time and are dropped for lookahead safety.
        if containing_row.close_price is not None and (
            upper_bound is None
            or containing_row.day_end_utc_ms <= upper_bound
        ):
            path_points.append(
                PricePoint(
                    timestamp_utc_ms=int(containing_row.day_end_utc_ms),
                    price=float(containing_row.close_price),
                )
            )

        # Subsequent days: every row whose entire span is strictly
        # AFTER the containing day.
        for row in rows:
            if row.day_start_utc_ms <= containing_row.day_start_utc_ms:
                continue
            if upper_bound is not None and row.day_start_utc_ms > upper_bound:
                break
            # Open at day_start (lookahead-safe: day_start >
            # first_seen_time).
            if row.open_price is not None:
                path_points.append(
                    PricePoint(
                        timestamp_utc_ms=int(row.day_start_utc_ms),
                        price=float(row.open_price),
                    )
                )
            # High / Low: stored at day_end_ms because the
            # Historical Market Store does not record their
            # intra-day timestamps. This is descriptively
            # conservative for time_to_peak_seconds; record the
            # approximation so a downstream auditor can see it.
            close_ts = int(row.day_end_utc_ms)
            if upper_bound is not None and close_ts > upper_bound:
                close_ts = upper_bound
            if row.high_price is not None:
                approximate_timestamps = True
                path_points.append(
                    PricePoint(
                        timestamp_utc_ms=close_ts,
                        price=float(row.high_price),
                    )
                )
            if row.low_price is not None:
                approximate_timestamps = True
                path_points.append(
                    PricePoint(
                        timestamp_utc_ms=close_ts,
                        price=float(row.low_price),
                    )
                )
            if row.close_price is not None:
                path_points.append(
                    PricePoint(
                        timestamp_utc_ms=close_ts,
                        price=float(row.close_price),
                    )
                )

        if len(path_points) < 1:
            return PricePathResolution(
                symbol=sym,
                first_seen_time_utc_ms=first_seen,
                first_seen_price=None,
                price_path=(),
                source=PricePathSource.ABSENT,
                missing_reason=(
                    PricePathMissingReason.INSUFFICIENT_POST_FIRST_SEEN_POINTS
                ),
                kline_interval_used=self._kline_interval_used,
                approximate_intra_day_timestamps=False,
                notes=tuple(notes),
            )

        if approximate_timestamps:
            notes.append("intra_day_high_low_stamped_at_day_end")

        return PricePathResolution(
            symbol=sym,
            first_seen_time_utc_ms=first_seen,
            first_seen_price=float(first_seen_price),
            price_path=tuple(path_points),
            source=(
                PricePathSource.HISTORICAL_MARKET_STORE_DAILY_TOP_MOVERS
            ),
            missing_reason=PricePathMissingReason.NONE,
            kline_interval_used=self._kline_interval_used,
            approximate_intra_day_timestamps=approximate_timestamps,
            notes=tuple(notes),
        )


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------


def summarise_price_path_resolutions(
    resolutions: Iterable[PricePathResolution],
) -> dict[str, Any]:
    """Aggregate ``resolutions`` into the evidence-only summary
    dict surfaced by the runner.

    Output shape::

        {
          "price_path_records_loaded": <int>,
          "price_path_records_missing": <int>,
          "price_path_source_summary": {<source>: <count>, ...},
          "price_path_missing_reason_summary":
              {<reason>: <count>, ...},
          "kline_interval_used": <str>,
          "approximate_intra_day_timestamp_count": <int>,
        }

    Every counter is descriptive paper / report / evidence only.
    """

    loaded = 0
    missing = 0
    source_summary: dict[str, int] = {}
    reason_summary: dict[str, int] = {}
    intervals: dict[str, int] = {}
    approx_count = 0

    for res in resolutions:
        if res.is_loaded():
            loaded += 1
        else:
            missing += 1
        source_summary[res.source] = source_summary.get(res.source, 0) + 1
        if res.missing_reason != PricePathMissingReason.NONE:
            reason_summary[res.missing_reason] = (
                reason_summary.get(res.missing_reason, 0) + 1
            )
        intervals[res.kline_interval_used] = (
            intervals.get(res.kline_interval_used, 0) + 1
        )
        if res.approximate_intra_day_timestamps:
            approx_count += 1

    if intervals:
        kline_interval_used = max(
            intervals.items(), key=lambda kv: kv[1]
        )[0]
    else:
        kline_interval_used = DEFAULT_KLINE_INTERVAL_USED

    return {
        "price_path_records_loaded": int(loaded),
        "price_path_records_missing": int(missing),
        "price_path_source_summary": dict(sorted(source_summary.items())),
        "price_path_missing_reason_summary": dict(
            sorted(reason_summary.items())
        ),
        "kline_interval_used": str(kline_interval_used),
        "approximate_intra_day_timestamp_count": int(approx_count),
    }


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


__all__ = [
    "POST_DISCOVERY_PRICE_PATH_ADAPTER_VERSION",
    "POST_DISCOVERY_PRICE_PATH_ADAPTER_SOURCE_PHASE",
    "POST_DISCOVERY_PRICE_PATH_ADAPTER_SCHEMA_VERSION",
    "DEFAULT_KLINE_INTERVAL_USED",
    "PricePathSource",
    "PricePathMissingReason",
    "PricePathResolution",
    "HistoricalPricePathAdapter",
    "summarise_price_path_resolutions",
]
