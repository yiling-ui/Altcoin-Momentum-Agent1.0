"""Phase 11C.1C-C-B-B-B-D-A - Historical 60D Mover Coverage Backfill
Audit v0.

This module implements a paper-only / report-only / evidence-only
DISCOVERY-LAYER historical coverage audit that answers the seven
operator questions enumerated in the Phase 11C.1C-C-B-B-B-D-A brief:

    1. Of the eligible USDT-perpetual top movers in the trailing 60
       days, did AMA-RT discover them?
    2. If discovered, when did AMA-RT first see the symbol?
    3. What was the first observed capture event?
    4. How far down the discovery chain did the candidate travel
       (anomaly -> label queue -> tail label -> strategy validation
       sample)?
    5. If missed, why?
    6. Was a missed mover a universe-coverage problem, or a
       discovery-layer warning (eligible-but-not-detected)?
    7. Which movers were captured but rejected by the Risk Engine?
       Which movers were only partially captured?

This audit is **NOT**:

    * a strategy blind replay
    * a PnL backtest
    * a trading module
    * AI Learning, automatic parameter optimisation, or
      reinforcement learning
    * the small-money live-trading pre-validation gate
    * Phase 12

Boundary (carried in every emitted event payload, the docs, and
the lookahead guard helpers below):

    * Every artefact this module produces is paper / report /
      evidence only.
    * The audit MUST NEVER trigger a real trade, modify position
      size, leverage, stop-loss, target price, the Risk Engine,
      the Execution FSM, ``symbol_limit``, candidate-pool capacity,
      anomaly thresholds, Regime weights, or any other runtime
      knob.
    * Lookahead Guard:
        - ``completed_tail_label`` MUST NOT drive reference
          selection.
        - future return / final max gain MUST NOT pollute the
          simulated live-radar score.
        - replay label MUST NOT contaminate ``first_seen_time``.
        - reflection / report text / LLM narrative MUST NEVER serve
          as a capture event source.
        - ``first_seen_time_utc`` MUST come from the timestamp of
          an event that already existed at audit time.
        - the top-mover reference set MUST only be used for
          post-hoc audit; it cannot rewrite past decisions.

The module emits two new event types, both paper / report /
evidence only:

    * :data:`EventType.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED`
    * :data:`EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`

Phase 12 remains FORBIDDEN.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from app.core.clock import now_ms
from app.core.events import Event, EventType
from app.database.repositories import EventRepository

#: Phase / module identity. Bumped only by an explicit phase brief
#: that changes the on-disk shape of any artefact the module
#: produces.
HISTORICAL_MOVER_COVERAGE_BACKFILL_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_a.historical_mover_coverage_backfill.v0"
)
HISTORICAL_MOVER_COVERAGE_BACKFILL_SOURCE_PHASE: str = (
    "phase_11c_1c_c_b_b_b_d_a"
)

#: Schema version label carried in every audit / event /
#: export-replay payload.
HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_a.historical_mover_coverage_backfill.v1"
)
KNOWN_HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSIONS: tuple[str, ...] = (
    HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION,
)

#: Default reference window length, in days. The brief explicitly
#: names "trailing 60 days" but the runtime accepts any positive
#: integer so a smaller dry-run window can be exercised.
DEFAULT_REFERENCE_WINDOW_DAYS: int = 60

#: Cap on top movers retained per day. The audit is a coverage
#: signal, not an exhaustive enumeration; capping per-day mover
#: rows keeps the report compact and avoids reading too much from
#: the local Historical Market Store.
DEFAULT_TOP_MOVERS_PER_DAY: int = 5

#: Minimum number of distinct trading-day snapshots the Historical
#: Market Store must contain for the runtime to emit a ``READY``
#: status. Below this threshold the runtime emits
#: ``INSUFFICIENT_HISTORY`` and the daily report flags a coverage
#: warning.
DEFAULT_MIN_HISTORY_DAYS: int = 14

#: Maximum number of records embedded in the daily-report sample.
#: Larger record sets remain available in ``records`` of the
#: report payload and via export / replay; the daily report only
#: surfaces the top-N for human review.
DEFAULT_DAILY_REPORT_RECORD_LIMIT: int = 20


# ---------------------------------------------------------------------------
# Status / classification taxonomies
# ---------------------------------------------------------------------------


class HistoricalMoverCoverageBackfillStatus:
    """Top-level descriptive status for a Historical 60D Mover
    Coverage Backfill audit.

    The runtime emits exactly one status per :class:`HistoricalMoverCoverageBackfillReport`.
    The status is descriptive only - **NEVER** an input to a trade-decision
    pipeline, the Risk Engine, the Execution FSM, ``symbol_limit``,
    candidate-pool capacity, anomaly thresholds, or Regime weights.
    """

    #: All inputs available, history >= ``min_history_days``, every
    #: reference row has the bare-minimum identity columns.
    READY: str = "READY"
    #: At least one reference row is missing optional columns (rank /
    #: max gain), or the audit observed a small subset of expected
    #: events.
    PARTIAL: str = "PARTIAL"
    #: The audit ran but at least one structural problem warrants a
    #: coverage warning (e.g. exchange_info subset missing, replay
    #: incomplete).
    DEGRADED: str = "DEGRADED"
    #: The Historical Market Store covers fewer days than
    #: ``min_history_days``.
    INSUFFICIENT_HISTORY: str = "INSUFFICIENT_HISTORY"
    #: The reference data on disk is unreadable / malformed; no
    #: report could be assembled.
    FAILED_REFERENCE_DATA: str = "FAILED_REFERENCE_DATA"

    ALL: tuple[str, ...] = (
        READY,
        PARTIAL,
        DEGRADED,
        INSUFFICIENT_HISTORY,
        FAILED_REFERENCE_DATA,
    )


class HistoricalMoverCoverageStatus:
    """Per-mover descriptive coverage status."""

    CAPTURED: str = "CAPTURED"
    PARTIALLY_CAPTURED: str = "PARTIALLY_CAPTURED"
    MISSED: str = "MISSED"
    EXCLUDED: str = "EXCLUDED"

    ALL: tuple[str, ...] = (CAPTURED, PARTIALLY_CAPTURED, MISSED, EXCLUDED)


class HistoricalMoverMissReason:
    """Closed taxonomy of miss reasons.

    Every reason is descriptive. None of them feed back into the
    Risk Engine, Execution FSM, ``symbol_limit``, candidate-pool
    capacity, anomaly thresholds, or Regime weights.
    """

    NOT_IN_FUTURES_UNIVERSE: str = "not_in_futures_universe"
    SYMBOL_NOT_IN_EXCHANGE_INFO: str = "symbol_not_in_exchange_info"
    NOT_USDT_PERPETUAL: str = "not_usdt_perpetual"
    MISSING_HISTORICAL_REFERENCE_DATA: str = "missing_historical_reference_data"
    MISSING_EVENT_HISTORY: str = "missing_event_history"
    BELOW_LIQUIDITY_THRESHOLD: str = "below_liquidity_threshold"
    SYMBOL_LIMIT_EXCLUDED: str = "symbol_limit_excluded"
    CANDIDATE_POOL_EVICTED: str = "candidate_pool_evicted"
    INSUFFICIENT_WS_DATA: str = "insufficient_ws_data"
    STALE_DATA: str = "stale_data"
    DATA_UNRELIABLE: str = "data_unreliable"
    NO_ANOMALY_THRESHOLD_CROSS: str = "no_anomaly_threshold_cross"
    RISK_REJECTED: str = "risk_rejected"
    NO_COMPLETED_TAIL_LABEL_YET: str = "no_completed_tail_label_yet"
    UNKNOWN: str = "unknown"

    EXCLUSION_REASONS: frozenset[str] = frozenset(
        {
            NOT_IN_FUTURES_UNIVERSE,
            SYMBOL_NOT_IN_EXCHANGE_INFO,
            NOT_USDT_PERPETUAL,
        }
    )

    ALL: tuple[str, ...] = (
        NOT_IN_FUTURES_UNIVERSE,
        SYMBOL_NOT_IN_EXCHANGE_INFO,
        NOT_USDT_PERPETUAL,
        MISSING_HISTORICAL_REFERENCE_DATA,
        MISSING_EVENT_HISTORY,
        BELOW_LIQUIDITY_THRESHOLD,
        SYMBOL_LIMIT_EXCLUDED,
        CANDIDATE_POOL_EVICTED,
        INSUFFICIENT_WS_DATA,
        STALE_DATA,
        DATA_UNRELIABLE,
        NO_ANOMALY_THRESHOLD_CROSS,
        RISK_REJECTED,
        NO_COMPLETED_TAIL_LABEL_YET,
        UNKNOWN,
    )


# ---------------------------------------------------------------------------
# Capture-path event-type ordering
# ---------------------------------------------------------------------------


#: Event types the audit walks for each historical mover, ordered
#: from "first observable" to "deepest". The ``capture_path_depth``
#: emitted in every record reflects how far down this chain the
#: mover travelled before the audit stopped seeing events for it.
HISTORICAL_CAPTURE_EVENT_ORDER: tuple[EventType, ...] = (
    EventType.MARKET_SNAPSHOT,
    EventType.PRE_ANOMALY_DETECTED,
    EventType.ANOMALY_DETECTED,
    EventType.MARKET_REGIME_ASSESSED,
    EventType.CANDIDATE_STAGE_CLASSIFIED,
    EventType.OPPORTUNITY_SCORED,
    EventType.STRATEGY_MODE_SELECTED,
    EventType.CLUSTER_CONTEXT_ATTACHED,
    EventType.LABEL_QUEUE_ENQUEUED,
    EventType.LABEL_TRACKING_STARTED,
    EventType.LABEL_WINDOW_COMPLETED,
    EventType.TAIL_LABEL_ASSIGNED,
    EventType.STRATEGY_VALIDATION_SAMPLE_CREATED,
)

#: Event types the audit also reads from the per-symbol stream but
#: that do **not** count toward ``capture_path_depth``. Their
#: presence affects ``risk_rejected`` and the miss-reason
#: classifier but never the descriptive depth integer.
HISTORICAL_NEGATIVE_SIGNAL_EVENTS: tuple[EventType, ...] = (
    EventType.RISK_REJECTED,
    EventType.DATA_UNRELIABLE,
)


# ---------------------------------------------------------------------------
# Lookahead Guard
# ---------------------------------------------------------------------------


#: Field names that, if present in a reference / capture-source
#: payload, indicate a future-knowledge leak and **must** be
#: rejected by the lookahead guard. The list is intentionally
#: conservative: it is easier to add a new "forbidden" field name
#: in a follow-up brief than to silently let one slip through.
LOOKAHEAD_FORBIDDEN_FIELDS: tuple[str, ...] = (
    "completed_tail_label",
    "tail_label_completed",
    "final_max_gain",
    "future_return",
    "future_max_gain",
    "future_max_window_gain",
    "future_max_24h_gain",
    "post_window_return",
    "post_window_max_gain",
    "lookahead_return",
    "lookahead_max_gain",
    "settled_tail_outcome",
    "primary_window_completed",
)


class HistoricalMoverLookaheadGuardError(ValueError):
    """Raised when a reference / capture-source payload contains a
    forbidden lookahead field, or when a capture event timestamp
    falls outside the reference window."""


def validate_no_lookahead_fields(
    payload: Mapping[str, Any] | None,
    *,
    forbidden_fields: Sequence[str] = LOOKAHEAD_FORBIDDEN_FIELDS,
    context: str = "",
) -> None:
    """Raise :class:`HistoricalMoverLookaheadGuardError` if ``payload``
    contains any of ``forbidden_fields``.

    The guard scans only one level deep; nested completed-window
    fixtures should be flattened by the caller before being handed
    to the runtime. The audit module never recurses into freeform
    LLM narrative or reflection text.
    """

    if payload is None:
        return
    if not isinstance(payload, Mapping):
        return
    forbidden = set(forbidden_fields)
    leaked = sorted(k for k in payload.keys() if k in forbidden)
    if leaked:
        raise HistoricalMoverLookaheadGuardError(
            f"lookahead guard: payload {context or '<unnamed>'} contains "
            f"forbidden lookahead fields {leaked}; the historical mover "
            "coverage audit is post-hoc and MUST NOT consume future return "
            "/ completed_tail_label / settled outcome columns as a "
            "reference or capture-source signal"
        )


def assert_capture_event_is_past_or_equal_reference_window(
    *,
    event_timestamp_ms: int,
    reference_window_start_ms: int,
    reference_window_end_ms: int,
    grace_seconds_before: int = 60 * 60 * 24 * 7,
    grace_seconds_after: int = 60 * 60 * 24 * 14,
    context: str = "",
) -> None:
    """Assert that ``event_timestamp_ms`` falls within the reference
    window (with a small grace period on either side).

    The audit accepts events that pre-date the window (a candidate
    might have been flagged earlier and still counted) but never
    events that post-date the window beyond the configured grace
    window. The grace defaults are paper-only operational
    tolerance, not strategy parameters.
    """

    window_start_with_grace = (
        reference_window_start_ms - grace_seconds_before * 1000
    )
    window_end_with_grace = (
        reference_window_end_ms + grace_seconds_after * 1000
    )
    if event_timestamp_ms < window_start_with_grace:
        raise HistoricalMoverLookaheadGuardError(
            f"lookahead guard: capture event {context or '<unnamed>'} "
            f"timestamp {event_timestamp_ms} predates window start "
            f"{reference_window_start_ms} by more than the configured "
            f"grace ({grace_seconds_before}s)"
        )
    if event_timestamp_ms > window_end_with_grace:
        raise HistoricalMoverLookaheadGuardError(
            f"lookahead guard: capture event {context or '<unnamed>'} "
            f"timestamp {event_timestamp_ms} postdates window end "
            f"{reference_window_end_ms} by more than the configured "
            f"grace ({grace_seconds_after}s); the audit MUST NOT consume "
            "events from after the reference window as the mover's "
            "first_seen evidence"
        )


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoricalMoverReference:
    """One row in the trailing-60D historical top-mover reference
    set.

    The reference set is built from local Historical Market Store
    snapshots (``data/historical_market_store/top_movers/*.jsonl``);
    no field on this row may be derived from a future return,
    completed tail label, or settled outcome.
    """

    symbol: str
    reference_timestamp_utc_ms: int
    mover_window_start_utc_ms: int
    mover_window_end_utc_ms: int
    eligible_usdt_perpetual: bool
    not_eligible_reason: str | None = None
    top_mover_rank: int | None = None
    max_window_gain: float | None = None
    max_24h_gain: float | None = None
    quote_volume_usdt: float | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "reference_timestamp_utc_ms": int(self.reference_timestamp_utc_ms),
            "mover_window_start_utc_ms": int(self.mover_window_start_utc_ms),
            "mover_window_end_utc_ms": int(self.mover_window_end_utc_ms),
            "eligible_usdt_perpetual": bool(self.eligible_usdt_perpetual),
            "not_eligible_reason": self.not_eligible_reason,
            "top_mover_rank": (
                int(self.top_mover_rank)
                if self.top_mover_rank is not None
                else None
            ),
            "max_window_gain": (
                float(self.max_window_gain)
                if self.max_window_gain is not None
                else None
            ),
            "max_24h_gain": (
                float(self.max_24h_gain)
                if self.max_24h_gain is not None
                else None
            ),
            "quote_volume_usdt": (
                float(self.quote_volume_usdt)
                if self.quote_volume_usdt is not None
                else None
            ),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class HistoricalMoverReferenceSet:
    """Container for the trailing-window historical top-mover
    reference rows + window-level metadata."""

    reference_window_days: int
    window_start_utc_ms: int
    window_end_utc_ms: int
    references: tuple[HistoricalMoverReference, ...]
    history_days_observed: int
    schema_version: str = HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION

    @property
    def total_count(self) -> int:
        return len(self.references)

    @property
    def eligible_count(self) -> int:
        return sum(1 for r in self.references if r.eligible_usdt_perpetual)

    @property
    def excluded_count(self) -> int:
        return sum(
            1 for r in self.references if not r.eligible_usdt_perpetual
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "reference_window_days": int(self.reference_window_days),
            "window_start_utc_ms": int(self.window_start_utc_ms),
            "window_end_utc_ms": int(self.window_end_utc_ms),
            "history_days_observed": int(self.history_days_observed),
            "total_count": int(self.total_count),
            "eligible_count": int(self.eligible_count),
            "excluded_count": int(self.excluded_count),
            "references": [r.to_dict() for r in self.references],
        }


@dataclass(frozen=True)
class HistoricalMoverCapturePath:
    """Per-mover capture-path evidence row.

    Records WHEN the mover first appeared in the event log, WHICH
    event type carried that first appearance, and how far down the
    discovery chain (anomaly -> label queue -> tail label ->
    strategy validation sample) the candidate travelled. Every
    timestamp is the timestamp of an event that already existed at
    audit time; no field is derived from a settled outcome / future
    return.
    """

    symbol: str
    first_seen_time_utc_ms: int | None
    first_seen_event_type: str | None
    first_seen_latency_seconds: float | None
    capture_path_depth: int
    reached_anomaly: bool
    reached_label_queue: bool
    reached_tail_label: bool
    reached_strategy_validation_sample: bool
    risk_rejected: bool
    data_unreliable: bool
    observed_event_types: tuple[str, ...]
    observed_event_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "first_seen_time_utc_ms": (
                int(self.first_seen_time_utc_ms)
                if self.first_seen_time_utc_ms is not None
                else None
            ),
            "first_seen_event_type": self.first_seen_event_type,
            "first_seen_latency_seconds": (
                float(self.first_seen_latency_seconds)
                if self.first_seen_latency_seconds is not None
                else None
            ),
            "capture_path_depth": int(self.capture_path_depth),
            "reached_anomaly": bool(self.reached_anomaly),
            "reached_label_queue": bool(self.reached_label_queue),
            "reached_tail_label": bool(self.reached_tail_label),
            "reached_strategy_validation_sample": bool(
                self.reached_strategy_validation_sample
            ),
            "risk_rejected": bool(self.risk_rejected),
            "data_unreliable": bool(self.data_unreliable),
            "observed_event_types": list(self.observed_event_types),
            "observed_event_count": int(self.observed_event_count),
        }


@dataclass(frozen=True)
class HistoricalMoverCoverageRecord:
    """Per-mover audit row.

    Carries the reference identity columns, the capture-path
    evidence, the descriptive coverage status (one of
    ``CAPTURED`` / ``PARTIALLY_CAPTURED`` / ``MISSED`` /
    ``EXCLUDED``), and the miss-reason taxonomy (single ``primary``
    + ordered ``reasons`` list). Paper / evidence only - **MUST
    NEVER** trigger orders or modify any runtime knob.
    """

    symbol: str
    coverage_status: str
    reference: HistoricalMoverReference
    capture_path: HistoricalMoverCapturePath
    miss_reason: str | None
    miss_reasons: tuple[str, ...]
    notes: str | None = None
    schema_version: str = HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION

    @property
    def first_seen_time_utc_ms(self) -> int | None:
        return self.capture_path.first_seen_time_utc_ms

    @property
    def first_seen_event_type(self) -> str | None:
        return self.capture_path.first_seen_event_type

    @property
    def first_seen_latency_seconds(self) -> float | None:
        return self.capture_path.first_seen_latency_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "coverage_status": self.coverage_status,
            "miss_reason": self.miss_reason,
            "miss_reasons": list(self.miss_reasons),
            "notes": self.notes,
            "reference": self.reference.to_dict(),
            "capture_path": self.capture_path.to_dict(),
        }


@dataclass(frozen=True)
class HistoricalMoverCoverageBackfillInput:
    """Inputs passed to one Historical 60D Mover Coverage Backfill
    Audit run.

    The runtime is a pure consumer; it does not reach for any
    ambient state. Every field below is descriptive paper /
    evidence only.
    """

    reference_set: HistoricalMoverReferenceSet
    audit_window_end_utc_ms: int
    reference_window_days: int
    exchange_info_symbols: frozenset[str] = frozenset()
    eligible_quote_assets: frozenset[str] = frozenset({"USDT"})
    grace_seconds_before: int = 60 * 60 * 24 * 7
    grace_seconds_after: int = 60 * 60 * 24 * 14
    history_days_observed: int = 0
    min_history_days: int = DEFAULT_MIN_HISTORY_DAYS
    coverage_warnings_in: tuple[str, ...] = ()
    notes: str | None = None
    schema_version: str = HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "audit_window_end_utc_ms": int(self.audit_window_end_utc_ms),
            "reference_window_days": int(self.reference_window_days),
            "exchange_info_symbol_count": int(len(self.exchange_info_symbols)),
            "eligible_quote_assets": sorted(self.eligible_quote_assets),
            "grace_seconds_before": int(self.grace_seconds_before),
            "grace_seconds_after": int(self.grace_seconds_after),
            "history_days_observed": int(self.history_days_observed),
            "min_history_days": int(self.min_history_days),
            "coverage_warnings_in": list(self.coverage_warnings_in),
            "notes": self.notes,
            "reference_set": self.reference_set.to_dict(),
        }


@dataclass(frozen=True)
class HistoricalMoverCoverageBackfillReport:
    """Top-level Historical 60D Mover Coverage Backfill audit
    report payload.

    Carries the descriptive backfill status, every mover's
    coverage record, and the metric roll-up.
    """

    backfill_status: str
    reference_window_days: int
    window_start_utc_ms: int
    window_end_utc_ms: int
    history_days_observed: int

    top_mover_count: int
    eligible_top_mover_count: int
    captured_top_mover_count: int
    partially_captured_top_mover_count: int
    missed_top_mover_count: int
    excluded_top_mover_count: int

    capture_recall_rate: float
    partial_capture_rate: float
    miss_rate: float

    anomaly_detected_rate: float
    label_tracking_rate: float
    tail_label_assigned_rate: float
    strategy_validation_sample_rate: float

    risk_rejected_mover_count: int
    not_in_universe_count: int
    missing_event_history_count: int
    data_unreliable_count: int

    median_first_seen_latency_seconds: float | None
    p90_first_seen_latency_seconds: float | None

    records: tuple[HistoricalMoverCoverageRecord, ...]
    miss_reason_summary: dict[str, int]
    coverage_warnings: tuple[str, ...]
    lookahead_guard_warnings: tuple[str, ...]

    generated_at_ms: int = 0
    schema_version: str = HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION
    source_phase: str = HISTORICAL_MOVER_COVERAGE_BACKFILL_SOURCE_PHASE

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "backfill_status": self.backfill_status,
            "reference_window_days": int(self.reference_window_days),
            "window_start_utc_ms": int(self.window_start_utc_ms),
            "window_end_utc_ms": int(self.window_end_utc_ms),
            "history_days_observed": int(self.history_days_observed),
            "top_mover_count": int(self.top_mover_count),
            "eligible_top_mover_count": int(self.eligible_top_mover_count),
            "captured_top_mover_count": int(self.captured_top_mover_count),
            "partially_captured_top_mover_count": int(
                self.partially_captured_top_mover_count
            ),
            "missed_top_mover_count": int(self.missed_top_mover_count),
            "excluded_top_mover_count": int(self.excluded_top_mover_count),
            "capture_recall_rate": float(self.capture_recall_rate),
            "partial_capture_rate": float(self.partial_capture_rate),
            "miss_rate": float(self.miss_rate),
            "anomaly_detected_rate": float(self.anomaly_detected_rate),
            "label_tracking_rate": float(self.label_tracking_rate),
            "tail_label_assigned_rate": float(self.tail_label_assigned_rate),
            "strategy_validation_sample_rate": float(
                self.strategy_validation_sample_rate
            ),
            "risk_rejected_mover_count": int(self.risk_rejected_mover_count),
            "not_in_universe_count": int(self.not_in_universe_count),
            "missing_event_history_count": int(
                self.missing_event_history_count
            ),
            "data_unreliable_count": int(self.data_unreliable_count),
            "median_first_seen_latency_seconds": self.median_first_seen_latency_seconds,
            "p90_first_seen_latency_seconds": self.p90_first_seen_latency_seconds,
            "records": [r.to_dict() for r in self.records],
            "miss_reason_summary": dict(self.miss_reason_summary),
            "coverage_warnings": list(self.coverage_warnings),
            "lookahead_guard_warnings": list(self.lookahead_guard_warnings),
            "generated_at_ms": int(self.generated_at_ms),
        }


# ---------------------------------------------------------------------------
# Historical Market Store discipline
# ---------------------------------------------------------------------------


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Return the JSONL rows in ``path`` as dicts. Skips empty lines.

    Raises :class:`HistoricalMoverLookaheadGuardError` if a row
    contains a forbidden lookahead field.
    """

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise HistoricalMoverLookaheadGuardError(
                    f"historical market store: {path} line {line_number} is "
                    f"not valid JSON: {exc}"
                ) from exc
            if not isinstance(row, dict):
                continue
            validate_no_lookahead_fields(
                row,
                context=f"{path.name}:line{line_number}",
            )
            rows.append(row)
    return rows


@dataclass(frozen=True)
class HistoricalMarketStoreSnapshot:
    """In-memory view of one Historical Market Store load.

    The store is intentionally small: only the columns the
    Historical 60D Mover Coverage Backfill audit needs to derive a
    reference set + audit miss reasons. Heavier OHLCV / liquidation
    / open-interest data is allowed on disk but only the columns
    the audit consumes are kept in memory.
    """

    top_mover_rows: tuple[dict[str, Any], ...]
    exchange_info_symbols: frozenset[str]
    history_days_observed: int
    source_files: tuple[str, ...]
    notes: str | None = None


def load_historical_market_store(
    root: Path | str,
    *,
    top_movers_subdir: str = "top_movers",
    exchange_info_subdir: str = "exchange_info",
) -> HistoricalMarketStoreSnapshot:
    """Read the local Historical Market Store from ``root``.

    The expected layout is::

        <root>/
          top_movers/*.jsonl       # one row per top mover snapshot
          exchange_info/*.jsonl    # bootstrap symbol catalogue
          candles/*.jsonl          # optional - not consumed here
          funding/*.jsonl          # optional - not consumed here
          open_interest/*.jsonl    # optional - not consumed here

    Missing subdirectories are tolerated; the audit downgrades to
    ``INSUFFICIENT_HISTORY`` / ``DEGRADED`` rather than raising.
    """

    root_path = Path(root)
    top_mover_rows: list[dict[str, Any]] = []
    source_files: list[str] = []
    seen_dates: set[str] = set()

    top_dir = root_path / top_movers_subdir
    if top_dir.is_dir():
        for path in sorted(top_dir.glob("*.jsonl")):
            rows = _load_jsonl(path)
            if not rows:
                continue
            top_mover_rows.extend(rows)
            source_files.append(str(path.relative_to(root_path)))
            for row in rows:
                snapshot_date = row.get("snapshot_date") or row.get("date")
                if isinstance(snapshot_date, str) and snapshot_date:
                    seen_dates.add(snapshot_date)

    exchange_symbols: set[str] = set()
    ex_dir = root_path / exchange_info_subdir
    if ex_dir.is_dir():
        for path in sorted(ex_dir.glob("*.jsonl")):
            rows = _load_jsonl(path)
            for row in rows:
                symbols = row.get("symbols")
                if isinstance(symbols, list):
                    for sym in symbols:
                        if isinstance(sym, str) and sym:
                            exchange_symbols.add(sym)
                        elif isinstance(sym, dict):
                            sym_name = sym.get("symbol")
                            if isinstance(sym_name, str) and sym_name:
                                exchange_symbols.add(sym_name)
                elif isinstance(row.get("symbol"), str):
                    exchange_symbols.add(row["symbol"])
            source_files.append(str(path.relative_to(root_path)))

    return HistoricalMarketStoreSnapshot(
        top_mover_rows=tuple(top_mover_rows),
        exchange_info_symbols=frozenset(exchange_symbols),
        history_days_observed=len(seen_dates),
        source_files=tuple(source_files),
    )


# ---------------------------------------------------------------------------
# Reference set construction
# ---------------------------------------------------------------------------


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_eligible_usdt_perpetual(
    symbol: str,
    *,
    quote_asset: str | None,
    contract_type: str | None,
    eligible_quote_assets: frozenset[str],
    exchange_info_symbols: frozenset[str],
) -> tuple[bool, str | None]:
    """Return ``(eligible, not_eligible_reason)``."""

    if exchange_info_symbols and symbol not in exchange_info_symbols:
        return False, HistoricalMoverMissReason.SYMBOL_NOT_IN_EXCHANGE_INFO
    if quote_asset is not None and quote_asset.upper() not in eligible_quote_assets:
        return False, HistoricalMoverMissReason.NOT_USDT_PERPETUAL
    if contract_type is not None and contract_type.upper() not in {
        "PERPETUAL",
        "PERP",
    }:
        return False, HistoricalMoverMissReason.NOT_USDT_PERPETUAL
    if quote_asset is None and contract_type is None:
        # If the row carries neither an explicit quote asset nor a
        # contract type, fall back to the symbol-suffix convention -
        # a Binance USDT perpetual symbol always ends in ``USDT``.
        if not symbol.endswith("USDT"):
            return False, HistoricalMoverMissReason.NOT_USDT_PERPETUAL
    return True, None


def build_historical_60d_mover_reference_set(
    *,
    top_mover_rows: Iterable[Mapping[str, Any]],
    audit_window_end_utc_ms: int,
    reference_window_days: int = DEFAULT_REFERENCE_WINDOW_DAYS,
    exchange_info_symbols: frozenset[str] | None = None,
    eligible_quote_assets: frozenset[str] = frozenset({"USDT"}),
    top_movers_per_day: int = DEFAULT_TOP_MOVERS_PER_DAY,
    history_days_observed: int | None = None,
) -> HistoricalMoverReferenceSet:
    """Pure function that builds a Historical 60D top-mover reference
    set from raw mover snapshot rows.

    Each input row should look approximately like::

        {
          "symbol": "FOOUSDT",
          "snapshot_date": "2026-04-15",
          "reference_timestamp_utc_ms": 1713187200000,
          "mover_window_start_utc_ms": 1713100800000,
          "mover_window_end_utc_ms": 1713187200000,
          "top_mover_rank": 1,
          "max_window_gain": 5.2,
          "max_24h_gain": 0.45,
          "quote_volume_usdt": 81234567.0,
          "quote_asset": "USDT",
          "contract_type": "PERPETUAL"
        }

    Missing optional columns are tolerated; the row is downgraded
    to PARTIAL or marked excluded as appropriate. Forbidden
    lookahead columns (``completed_tail_label`` / ``final_max_gain``
    / ``future_return`` / ...) raise :class:`HistoricalMoverLookaheadGuardError`.
    """

    if reference_window_days <= 0:
        raise ValueError(
            f"reference_window_days must be positive, got {reference_window_days}"
        )

    window_end_ms = int(audit_window_end_utc_ms)
    window_start_ms = window_end_ms - reference_window_days * 24 * 60 * 60 * 1000

    exchange_info_set: frozenset[str] = (
        exchange_info_symbols
        if exchange_info_symbols is not None
        else frozenset()
    )

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    seen_dates: set[str] = set()

    for raw in top_mover_rows:
        if not isinstance(raw, Mapping):
            continue
        validate_no_lookahead_fields(raw, context="top_mover_row")
        symbol = raw.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            continue
        snapshot_date = raw.get("snapshot_date") or raw.get("date") or ""
        if isinstance(snapshot_date, str) and snapshot_date:
            seen_dates.add(snapshot_date)
        # Only keep rows whose reference timestamp falls inside the
        # configured window (with a small grace).
        ref_ts = _coerce_int(raw.get("reference_timestamp_utc_ms"))
        if ref_ts is None:
            ref_ts = _coerce_int(raw.get("timestamp"))
        if ref_ts is None:
            continue
        if ref_ts < window_start_ms - 24 * 60 * 60 * 1000:
            continue
        if ref_ts > window_end_ms + 24 * 60 * 60 * 1000:
            continue
        grouped.setdefault(str(snapshot_date or "_unbinned"), []).append(
            {**raw, "reference_timestamp_utc_ms": ref_ts}
        )

    references: list[HistoricalMoverReference] = []
    for _date_key, day_rows in sorted(grouped.items()):
        # Per-day cap: keep the top-N by rank (asc) or by max_window_gain
        # (desc) when rank is missing.
        def _sort_key(row: Mapping[str, Any]) -> tuple[int, float]:
            rank = _coerce_int(row.get("top_mover_rank"))
            if rank is None:
                rank = 1_000
            gain = _coerce_float(row.get("max_window_gain"))
            if gain is None:
                gain = _coerce_float(row.get("max_24h_gain")) or 0.0
            return (rank, -gain)

        day_rows_sorted = sorted(day_rows, key=_sort_key)
        for row in day_rows_sorted[: max(0, int(top_movers_per_day))]:
            symbol = str(row["symbol"])
            quote_asset = row.get("quote_asset")
            contract_type = row.get("contract_type")
            eligible, reason = _is_eligible_usdt_perpetual(
                symbol,
                quote_asset=(
                    str(quote_asset) if isinstance(quote_asset, str) else None
                ),
                contract_type=(
                    str(contract_type)
                    if isinstance(contract_type, str)
                    else None
                ),
                eligible_quote_assets=eligible_quote_assets,
                exchange_info_symbols=exchange_info_set,
            )
            ref_ts = int(row["reference_timestamp_utc_ms"])
            mover_start = (
                _coerce_int(row.get("mover_window_start_utc_ms"))
                or ref_ts - 24 * 60 * 60 * 1000
            )
            mover_end = (
                _coerce_int(row.get("mover_window_end_utc_ms")) or ref_ts
            )
            references.append(
                HistoricalMoverReference(
                    symbol=symbol,
                    reference_timestamp_utc_ms=ref_ts,
                    mover_window_start_utc_ms=mover_start,
                    mover_window_end_utc_ms=mover_end,
                    eligible_usdt_perpetual=eligible,
                    not_eligible_reason=reason,
                    top_mover_rank=_coerce_int(row.get("top_mover_rank")),
                    max_window_gain=_coerce_float(row.get("max_window_gain")),
                    max_24h_gain=_coerce_float(row.get("max_24h_gain")),
                    quote_volume_usdt=_coerce_float(
                        row.get("quote_volume_usdt")
                    ),
                    notes=(
                        str(row.get("notes"))
                        if isinstance(row.get("notes"), str)
                        else None
                    ),
                )
            )

    observed_days = (
        history_days_observed
        if history_days_observed is not None
        else len(seen_dates)
    )

    return HistoricalMoverReferenceSet(
        reference_window_days=int(reference_window_days),
        window_start_utc_ms=int(window_start_ms),
        window_end_utc_ms=int(window_end_ms),
        references=tuple(references),
        history_days_observed=int(observed_days),
    )


# ---------------------------------------------------------------------------
# Capture path audit
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SymbolEventStream:
    """Events for one symbol within the audit window."""

    symbol: str
    events: tuple[Event, ...]


def _collect_symbol_event_streams(
    *,
    event_repo: EventRepository,
    symbols: Iterable[str],
    window_start_ms: int,
    window_end_ms: int,
    grace_seconds_before: int,
    grace_seconds_after: int,
) -> dict[str, tuple[Event, ...]]:
    """Return ``{symbol: events}`` for every symbol of interest."""

    requested = {s for s in symbols if isinstance(s, str) and s}
    if not requested:
        return {}

    relevant_event_types = (
        list(HISTORICAL_CAPTURE_EVENT_ORDER)
        + list(HISTORICAL_NEGATIVE_SIGNAL_EVENTS)
    )

    accum: dict[str, list[Event]] = {sym: [] for sym in requested}
    grace_start = window_start_ms - grace_seconds_before * 1000
    grace_end = window_end_ms + grace_seconds_after * 1000

    # NOTE: ``EventRepository.list_events`` is the authoritative
    # read surface; the audit never reaches into a raw SQLite cursor.
    # We pull per-event-type because the repository indexes by
    # ``event_type``; pulling everything would duplicate the
    # in-memory rows for symbols we do not care about.
    for event_type in relevant_event_types:
        rows = event_repo.list_events(event_type=event_type)
        for ev in rows:
            sym = ev.symbol
            if not isinstance(sym, str):
                continue
            if sym not in accum:
                continue
            ts = int(ev.timestamp)
            if ts < grace_start or ts > grace_end:
                continue
            accum[sym].append(ev)

    return {sym: tuple(sorted(events, key=lambda e: e.timestamp))
            for sym, events in accum.items()}


def audit_historical_mover_capture_path(
    *,
    reference: HistoricalMoverReference,
    events: Sequence[Event],
    window_start_utc_ms: int,
    window_end_utc_ms: int,
    grace_seconds_before: int = 60 * 60 * 24 * 7,
    grace_seconds_after: int = 60 * 60 * 24 * 14,
) -> HistoricalMoverCapturePath:
    """Pure function that builds a :class:`HistoricalMoverCapturePath`
    for one historical mover.

    The walker:
      * sorts ``events`` by timestamp;
      * records the EARLIEST observed event as ``first_seen``;
      * counts per-event-type presence flags;
      * computes ``capture_path_depth`` as the deepest rung in
        :data:`HISTORICAL_CAPTURE_EVENT_ORDER` reached.

    Lookahead guard:
      * every event timestamp is checked against the reference
        window with the configured grace; an event from far in the
        future raises :class:`HistoricalMoverLookaheadGuardError`.
      * the walker reads the event timestamp ONLY; payload columns
        that look like a settled outcome are ignored.
    """

    sorted_events = sorted(events, key=lambda e: e.timestamp)

    first_seen_event: Event | None = None
    observed_types: list[str] = []
    type_set: set[str] = set()
    risk_rejected = False
    data_unreliable = False
    reached_anomaly = False
    reached_label_queue = False
    reached_tail_label = False
    reached_strategy_validation_sample = False
    deepest_index = -1

    for ev in sorted_events:
        assert_capture_event_is_past_or_equal_reference_window(
            event_timestamp_ms=int(ev.timestamp),
            reference_window_start_ms=window_start_utc_ms,
            reference_window_end_ms=window_end_utc_ms,
            grace_seconds_before=grace_seconds_before,
            grace_seconds_after=grace_seconds_after,
            context=f"{reference.symbol}/{ev.event_type.value}",
        )
        if first_seen_event is None and ev.event_type in HISTORICAL_CAPTURE_EVENT_ORDER:
            first_seen_event = ev
        observed_types.append(ev.event_type.value)
        type_set.add(ev.event_type.value)
        if ev.event_type is EventType.ANOMALY_DETECTED:
            reached_anomaly = True
        if ev.event_type is EventType.LABEL_QUEUE_ENQUEUED:
            reached_label_queue = True
        if ev.event_type is EventType.TAIL_LABEL_ASSIGNED:
            reached_tail_label = True
        if ev.event_type is EventType.STRATEGY_VALIDATION_SAMPLE_CREATED:
            reached_strategy_validation_sample = True
        if ev.event_type is EventType.RISK_REJECTED:
            risk_rejected = True
        if ev.event_type is EventType.DATA_UNRELIABLE:
            data_unreliable = True
        try:
            idx = HISTORICAL_CAPTURE_EVENT_ORDER.index(ev.event_type)
        except ValueError:
            idx = -1
        if idx > deepest_index:
            deepest_index = idx

    first_seen_time = (
        int(first_seen_event.timestamp) if first_seen_event is not None else None
    )
    first_seen_type = (
        first_seen_event.event_type.value
        if first_seen_event is not None
        else None
    )
    first_seen_latency: float | None = None
    if first_seen_time is not None:
        first_seen_latency = (
            first_seen_time - reference.reference_timestamp_utc_ms
        ) / 1000.0

    capture_path_depth = deepest_index + 1 if deepest_index >= 0 else 0

    return HistoricalMoverCapturePath(
        symbol=reference.symbol,
        first_seen_time_utc_ms=first_seen_time,
        first_seen_event_type=first_seen_type,
        first_seen_latency_seconds=first_seen_latency,
        capture_path_depth=capture_path_depth,
        reached_anomaly=reached_anomaly,
        reached_label_queue=reached_label_queue,
        reached_tail_label=reached_tail_label,
        reached_strategy_validation_sample=reached_strategy_validation_sample,
        risk_rejected=risk_rejected,
        data_unreliable=data_unreliable,
        observed_event_types=tuple(observed_types),
        observed_event_count=len(observed_types),
    )


def classify_historical_miss_reason(
    *,
    reference: HistoricalMoverReference,
    capture_path: HistoricalMoverCapturePath,
) -> tuple[str | None, tuple[str, ...]]:
    """Return ``(primary_reason, ordered_reasons)`` for one record.

    Only the ``EXCLUDED`` / ``MISSED`` / ``PARTIALLY_CAPTURED`` /
    ``CAPTURED`` axis is decided here; the caller is responsible
    for the coverage status. Returns ``(None, ())`` for a fully
    captured mover.
    """

    reasons: list[str] = []

    # Exclusion reasons take precedence and short-circuit the walk.
    if not reference.eligible_usdt_perpetual:
        primary = (
            reference.not_eligible_reason
            or HistoricalMoverMissReason.NOT_IN_FUTURES_UNIVERSE
        )
        return primary, (primary,)

    # If the audit observed zero events for the symbol, it is a
    # MISSED mover with the most informative reason being either
    # MISSING_EVENT_HISTORY or UNKNOWN.
    if capture_path.observed_event_count == 0:
        return (
            HistoricalMoverMissReason.MISSING_EVENT_HISTORY,
            (HistoricalMoverMissReason.MISSING_EVENT_HISTORY,),
        )

    if capture_path.data_unreliable:
        reasons.append(HistoricalMoverMissReason.DATA_UNRELIABLE)

    if capture_path.risk_rejected:
        reasons.append(HistoricalMoverMissReason.RISK_REJECTED)

    if not capture_path.reached_anomaly:
        reasons.append(HistoricalMoverMissReason.NO_ANOMALY_THRESHOLD_CROSS)
    elif not capture_path.reached_label_queue:
        # The chain saw the anomaly but never enqueued the candidate;
        # most often a CANDIDATE_POOL_EVICTED / SYMBOL_LIMIT_EXCLUDED
        # situation. We tag the most-conservative bucket -
        # ``UNKNOWN`` - and leave the operator to drill in.
        reasons.append(HistoricalMoverMissReason.UNKNOWN)
    elif not capture_path.reached_tail_label:
        reasons.append(HistoricalMoverMissReason.NO_COMPLETED_TAIL_LABEL_YET)

    if not reasons:
        return None, ()
    return reasons[0], tuple(reasons)


def _coverage_status(
    *,
    reference: HistoricalMoverReference,
    capture_path: HistoricalMoverCapturePath,
) -> str:
    if not reference.eligible_usdt_perpetual:
        return HistoricalMoverCoverageStatus.EXCLUDED
    if capture_path.observed_event_count == 0:
        return HistoricalMoverCoverageStatus.MISSED
    if (
        capture_path.reached_anomaly
        and capture_path.reached_label_queue
        and (
            capture_path.reached_tail_label
            or capture_path.reached_strategy_validation_sample
        )
    ):
        return HistoricalMoverCoverageStatus.CAPTURED
    return HistoricalMoverCoverageStatus.PARTIALLY_CAPTURED


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def _safe_div(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _percentile(sorted_values: Sequence[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = rank - lower
    return float(
        sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight
    )


def _median(sorted_values: Sequence[float]) -> float | None:
    if not sorted_values:
        return None
    n = len(sorted_values)
    mid = n // 2
    if n % 2 == 1:
        return float(sorted_values[mid])
    return float((sorted_values[mid - 1] + sorted_values[mid]) / 2.0)


def build_historical_mover_coverage_backfill_report(
    *,
    audit_input: HistoricalMoverCoverageBackfillInput,
    records: Sequence[HistoricalMoverCoverageRecord],
    coverage_warnings: Sequence[str] = (),
    lookahead_guard_warnings: Sequence[str] = (),
    generated_at_ms: int | None = None,
) -> HistoricalMoverCoverageBackfillReport:
    """Pure function that turns a list of records into a top-level
    report payload.

    Computes capture-recall / partial-capture / miss / chain-depth
    rates, the median + p90 first-seen latency over CAPTURED +
    PARTIALLY_CAPTURED records, and the top-level descriptive
    backfill status.
    """

    total = len(records)
    captured = [
        r for r in records
        if r.coverage_status == HistoricalMoverCoverageStatus.CAPTURED
    ]
    partial = [
        r for r in records
        if r.coverage_status == HistoricalMoverCoverageStatus.PARTIALLY_CAPTURED
    ]
    missed = [
        r for r in records
        if r.coverage_status == HistoricalMoverCoverageStatus.MISSED
    ]
    excluded = [
        r for r in records
        if r.coverage_status == HistoricalMoverCoverageStatus.EXCLUDED
    ]
    eligible = [
        r for r in records
        if r.coverage_status != HistoricalMoverCoverageStatus.EXCLUDED
    ]

    capture_recall_rate = _safe_div(len(captured), len(eligible))
    partial_capture_rate = _safe_div(len(partial), len(eligible))
    miss_rate = _safe_div(len(missed), len(eligible))

    anomaly_count = sum(
        1 for r in records if r.capture_path.reached_anomaly
    )
    label_count = sum(
        1 for r in records if r.capture_path.reached_label_queue
    )
    tail_count = sum(
        1 for r in records if r.capture_path.reached_tail_label
    )
    sample_count = sum(
        1
        for r in records
        if r.capture_path.reached_strategy_validation_sample
    )

    risk_rejected_count = sum(
        1 for r in records if r.capture_path.risk_rejected
    )
    not_in_universe_count = sum(
        1
        for r in records
        if r.miss_reasons
        and r.miss_reasons[0]
        in HistoricalMoverMissReason.EXCLUSION_REASONS
    )
    missing_event_history_count = sum(
        1
        for r in records
        if HistoricalMoverMissReason.MISSING_EVENT_HISTORY in r.miss_reasons
    )
    data_unreliable_count = sum(
        1 for r in records if r.capture_path.data_unreliable
    )

    latencies: list[float] = []
    for record in records:
        if record.coverage_status in (
            HistoricalMoverCoverageStatus.CAPTURED,
            HistoricalMoverCoverageStatus.PARTIALLY_CAPTURED,
        ):
            latency = record.first_seen_latency_seconds
            if latency is not None:
                latencies.append(float(latency))
    latencies.sort()
    median_latency = _median(latencies)
    p90_latency = _percentile(latencies, 90.0)

    miss_reason_summary: dict[str, int] = {}
    for record in records:
        for reason in record.miss_reasons:
            miss_reason_summary[reason] = miss_reason_summary.get(
                reason, 0
            ) + 1

    # ------------------------------------------------------------------
    # Top-level backfill status. INSUFFICIENT_HISTORY trumps
    # everything (it is the most actionable warning); FAILED_REFERENCE_DATA
    # is reserved for a fully empty / unreadable input. PARTIAL fires
    # when at least one record carries a missing-data warning,
    # DEGRADED when an explicit guard warning fired, and READY
    # otherwise.
    # ------------------------------------------------------------------
    if audit_input.history_days_observed < audit_input.min_history_days:
        backfill_status = HistoricalMoverCoverageBackfillStatus.INSUFFICIENT_HISTORY
    elif total == 0:
        backfill_status = HistoricalMoverCoverageBackfillStatus.FAILED_REFERENCE_DATA
    elif lookahead_guard_warnings:
        backfill_status = HistoricalMoverCoverageBackfillStatus.DEGRADED
    elif coverage_warnings:
        backfill_status = HistoricalMoverCoverageBackfillStatus.PARTIAL
    elif missing_event_history_count > 0 or data_unreliable_count > 0:
        backfill_status = HistoricalMoverCoverageBackfillStatus.PARTIAL
    else:
        backfill_status = HistoricalMoverCoverageBackfillStatus.READY

    return HistoricalMoverCoverageBackfillReport(
        backfill_status=backfill_status,
        reference_window_days=int(audit_input.reference_window_days),
        window_start_utc_ms=int(
            audit_input.reference_set.window_start_utc_ms
        ),
        window_end_utc_ms=int(audit_input.reference_set.window_end_utc_ms),
        history_days_observed=int(audit_input.history_days_observed),
        top_mover_count=int(total),
        eligible_top_mover_count=int(len(eligible)),
        captured_top_mover_count=int(len(captured)),
        partially_captured_top_mover_count=int(len(partial)),
        missed_top_mover_count=int(len(missed)),
        excluded_top_mover_count=int(len(excluded)),
        capture_recall_rate=float(capture_recall_rate),
        partial_capture_rate=float(partial_capture_rate),
        miss_rate=float(miss_rate),
        anomaly_detected_rate=_safe_div(anomaly_count, len(eligible)),
        label_tracking_rate=_safe_div(label_count, len(eligible)),
        tail_label_assigned_rate=_safe_div(tail_count, len(eligible)),
        strategy_validation_sample_rate=_safe_div(
            sample_count, len(eligible)
        ),
        risk_rejected_mover_count=int(risk_rejected_count),
        not_in_universe_count=int(not_in_universe_count),
        missing_event_history_count=int(missing_event_history_count),
        data_unreliable_count=int(data_unreliable_count),
        median_first_seen_latency_seconds=median_latency,
        p90_first_seen_latency_seconds=p90_latency,
        records=tuple(records),
        miss_reason_summary=dict(sorted(miss_reason_summary.items())),
        coverage_warnings=tuple(coverage_warnings),
        lookahead_guard_warnings=tuple(lookahead_guard_warnings),
        generated_at_ms=int(generated_at_ms or 0),
    )


# ---------------------------------------------------------------------------
# Export / replay payload helpers
# ---------------------------------------------------------------------------


def export_historical_mover_coverage_payload(
    report: HistoricalMoverCoverageBackfillReport,
) -> dict[str, Any]:
    """Return a JSON-safe dict ready for export / events.jsonl."""

    return report.to_dict()


def load_historical_mover_coverage_payload(
    payload: Mapping[str, Any],
) -> HistoricalMoverCoverageBackfillReport:
    """Inverse of :func:`export_historical_mover_coverage_payload`."""

    schema_version = str(
        payload.get(
            "schema_version",
            HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION,
        )
    )
    if schema_version not in KNOWN_HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSIONS:
        raise ValueError(
            f"unknown historical mover coverage backfill schema_version: "
            f"{schema_version!r}"
        )
    records: list[HistoricalMoverCoverageRecord] = []
    for raw_record in payload.get("records", []):
        if not isinstance(raw_record, Mapping):
            continue
        ref_dict = raw_record.get("reference", {})
        cap_dict = raw_record.get("capture_path", {})
        reference = HistoricalMoverReference(
            symbol=str(ref_dict.get("symbol", raw_record.get("symbol", ""))),
            reference_timestamp_utc_ms=int(
                ref_dict.get("reference_timestamp_utc_ms", 0)
            ),
            mover_window_start_utc_ms=int(
                ref_dict.get("mover_window_start_utc_ms", 0)
            ),
            mover_window_end_utc_ms=int(
                ref_dict.get("mover_window_end_utc_ms", 0)
            ),
            eligible_usdt_perpetual=bool(
                ref_dict.get("eligible_usdt_perpetual", True)
            ),
            not_eligible_reason=ref_dict.get("not_eligible_reason"),
            top_mover_rank=ref_dict.get("top_mover_rank"),
            max_window_gain=ref_dict.get("max_window_gain"),
            max_24h_gain=ref_dict.get("max_24h_gain"),
            quote_volume_usdt=ref_dict.get("quote_volume_usdt"),
            notes=ref_dict.get("notes"),
        )
        capture_path = HistoricalMoverCapturePath(
            symbol=str(cap_dict.get("symbol", reference.symbol)),
            first_seen_time_utc_ms=cap_dict.get("first_seen_time_utc_ms"),
            first_seen_event_type=cap_dict.get("first_seen_event_type"),
            first_seen_latency_seconds=cap_dict.get(
                "first_seen_latency_seconds"
            ),
            capture_path_depth=int(cap_dict.get("capture_path_depth", 0)),
            reached_anomaly=bool(cap_dict.get("reached_anomaly", False)),
            reached_label_queue=bool(
                cap_dict.get("reached_label_queue", False)
            ),
            reached_tail_label=bool(
                cap_dict.get("reached_tail_label", False)
            ),
            reached_strategy_validation_sample=bool(
                cap_dict.get("reached_strategy_validation_sample", False)
            ),
            risk_rejected=bool(cap_dict.get("risk_rejected", False)),
            data_unreliable=bool(cap_dict.get("data_unreliable", False)),
            observed_event_types=tuple(
                cap_dict.get("observed_event_types", ()) or ()
            ),
            observed_event_count=int(
                cap_dict.get("observed_event_count", 0)
            ),
        )
        miss_reasons = tuple(raw_record.get("miss_reasons", ()) or ())
        records.append(
            HistoricalMoverCoverageRecord(
                symbol=str(raw_record.get("symbol", reference.symbol)),
                coverage_status=str(
                    raw_record.get(
                        "coverage_status",
                        HistoricalMoverCoverageStatus.MISSED,
                    )
                ),
                reference=reference,
                capture_path=capture_path,
                miss_reason=raw_record.get("miss_reason"),
                miss_reasons=miss_reasons,
                notes=raw_record.get("notes"),
            )
        )

    return HistoricalMoverCoverageBackfillReport(
        backfill_status=str(
            payload.get(
                "backfill_status",
                HistoricalMoverCoverageBackfillStatus.READY,
            )
        ),
        reference_window_days=int(
            payload.get("reference_window_days", DEFAULT_REFERENCE_WINDOW_DAYS)
        ),
        window_start_utc_ms=int(payload.get("window_start_utc_ms", 0)),
        window_end_utc_ms=int(payload.get("window_end_utc_ms", 0)),
        history_days_observed=int(payload.get("history_days_observed", 0)),
        top_mover_count=int(payload.get("top_mover_count", len(records))),
        eligible_top_mover_count=int(
            payload.get("eligible_top_mover_count", 0)
        ),
        captured_top_mover_count=int(
            payload.get("captured_top_mover_count", 0)
        ),
        partially_captured_top_mover_count=int(
            payload.get("partially_captured_top_mover_count", 0)
        ),
        missed_top_mover_count=int(payload.get("missed_top_mover_count", 0)),
        excluded_top_mover_count=int(
            payload.get("excluded_top_mover_count", 0)
        ),
        capture_recall_rate=float(payload.get("capture_recall_rate", 0.0)),
        partial_capture_rate=float(payload.get("partial_capture_rate", 0.0)),
        miss_rate=float(payload.get("miss_rate", 0.0)),
        anomaly_detected_rate=float(
            payload.get("anomaly_detected_rate", 0.0)
        ),
        label_tracking_rate=float(payload.get("label_tracking_rate", 0.0)),
        tail_label_assigned_rate=float(
            payload.get("tail_label_assigned_rate", 0.0)
        ),
        strategy_validation_sample_rate=float(
            payload.get("strategy_validation_sample_rate", 0.0)
        ),
        risk_rejected_mover_count=int(
            payload.get("risk_rejected_mover_count", 0)
        ),
        not_in_universe_count=int(payload.get("not_in_universe_count", 0)),
        missing_event_history_count=int(
            payload.get("missing_event_history_count", 0)
        ),
        data_unreliable_count=int(payload.get("data_unreliable_count", 0)),
        median_first_seen_latency_seconds=payload.get(
            "median_first_seen_latency_seconds"
        ),
        p90_first_seen_latency_seconds=payload.get(
            "p90_first_seen_latency_seconds"
        ),
        records=tuple(records),
        miss_reason_summary=dict(payload.get("miss_reason_summary", {}) or {}),
        coverage_warnings=tuple(payload.get("coverage_warnings", ()) or ()),
        lookahead_guard_warnings=tuple(
            payload.get("lookahead_guard_warnings", ()) or ()
        ),
        generated_at_ms=int(payload.get("generated_at_ms", 0)),
        schema_version=schema_version,
        source_phase=str(
            payload.get(
                "source_phase",
                HISTORICAL_MOVER_COVERAGE_BACKFILL_SOURCE_PHASE,
            )
        ),
    )


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


SOURCE_MODULE = "app.adaptive.historical_mover_coverage_backfill"


class HistoricalMoverCoverageBackfillRuntime:
    """Paper / report / evidence-only runtime for the Historical 60D
    Mover Coverage Backfill audit.

    The runtime is a thin orchestrator: it walks each
    :class:`HistoricalMoverReference` row, calls
    :func:`audit_historical_mover_capture_path` against the per-symbol
    event stream, classifies the miss reason, and emits two new
    event types (:data:`EventType.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED`
    + :data:`EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`).

    Boundary:
      * Paper / report only. The runtime never opens / closes a
        position, never modifies a Risk Engine threshold, never
        flips a Phase 1 safety flag, never reads a private API,
        never signs a request, and never authorises a trade.
      * The descriptive ``backfill_status`` is **NEVER** consumed
        as a trade-decision input.
    """

    def __init__(self, *, event_repo: EventRepository) -> None:
        self._event_repo = event_repo
        self._latest_report: HistoricalMoverCoverageBackfillReport | None = None
        self._generated_count = 0
        self._record_audited_count = 0

    @property
    def latest_report(self) -> HistoricalMoverCoverageBackfillReport | None:
        return self._latest_report

    def flush(
        self,
        audit_input: HistoricalMoverCoverageBackfillInput,
        *,
        generated_at_ms: int | None = None,
        emit_events: bool = True,
        coverage_warnings: Sequence[str] = (),
    ) -> HistoricalMoverCoverageBackfillReport:
        """Run one Historical 60D Mover Coverage Backfill audit and
        return its report.

        ``coverage_warnings`` is the set of operator-supplied
        warnings (e.g. "exchange_info bootstrap snapshot missing");
        they are concatenated with the ones the audit derives from
        the input.
        """

        ts_ms = int(generated_at_ms if generated_at_ms is not None else now_ms())
        warnings: list[str] = list(coverage_warnings)
        warnings.extend(audit_input.coverage_warnings_in)
        lookahead_warnings: list[str] = []

        # Lookahead guard pre-flight on the reference rows.
        for ref in audit_input.reference_set.references:
            try:
                validate_no_lookahead_fields(
                    ref.to_dict(),
                    context=f"reference[{ref.symbol}]",
                )
            except HistoricalMoverLookaheadGuardError as exc:
                lookahead_warnings.append(str(exc))

        # Collect per-symbol event streams in one DB pass.
        symbols = [
            r.symbol
            for r in audit_input.reference_set.references
        ]
        symbol_streams: dict[str, tuple[Event, ...]]
        try:
            symbol_streams = _collect_symbol_event_streams(
                event_repo=self._event_repo,
                symbols=symbols,
                window_start_ms=audit_input.reference_set.window_start_utc_ms,
                window_end_ms=audit_input.reference_set.window_end_utc_ms,
                grace_seconds_before=audit_input.grace_seconds_before,
                grace_seconds_after=audit_input.grace_seconds_after,
            )
        except Exception as exc:  # pragma: no cover - defensive
            warnings.append(f"event repository unavailable: {exc!s}")
            symbol_streams = {sym: () for sym in symbols}

        records: list[HistoricalMoverCoverageRecord] = []
        for ref in audit_input.reference_set.references:
            events = symbol_streams.get(ref.symbol, ())
            try:
                capture_path = audit_historical_mover_capture_path(
                    reference=ref,
                    events=events,
                    window_start_utc_ms=audit_input.reference_set.window_start_utc_ms,
                    window_end_utc_ms=audit_input.reference_set.window_end_utc_ms,
                    grace_seconds_before=audit_input.grace_seconds_before,
                    grace_seconds_after=audit_input.grace_seconds_after,
                )
            except HistoricalMoverLookaheadGuardError as exc:
                lookahead_warnings.append(str(exc))
                capture_path = HistoricalMoverCapturePath(
                    symbol=ref.symbol,
                    first_seen_time_utc_ms=None,
                    first_seen_event_type=None,
                    first_seen_latency_seconds=None,
                    capture_path_depth=0,
                    reached_anomaly=False,
                    reached_label_queue=False,
                    reached_tail_label=False,
                    reached_strategy_validation_sample=False,
                    risk_rejected=False,
                    data_unreliable=False,
                    observed_event_types=(),
                    observed_event_count=0,
                )
            primary, reasons = classify_historical_miss_reason(
                reference=ref, capture_path=capture_path
            )
            status = _coverage_status(reference=ref, capture_path=capture_path)
            record = HistoricalMoverCoverageRecord(
                symbol=ref.symbol,
                coverage_status=status,
                reference=ref,
                capture_path=capture_path,
                miss_reason=primary,
                miss_reasons=reasons,
            )
            records.append(record)

        report = build_historical_mover_coverage_backfill_report(
            audit_input=audit_input,
            records=records,
            coverage_warnings=tuple(warnings),
            lookahead_guard_warnings=tuple(lookahead_warnings),
            generated_at_ms=ts_ms,
        )
        self._latest_report = report

        if emit_events:
            self._emit_events(report=report, audit_input=audit_input)

        return report

    def metrics_payload(self) -> dict[str, Any]:
        """Return the runner-side metrics dict consumed by the
        daily report builder + the safety / event-type cross-check
        in the Phase 11B no-network test."""

        report = self._latest_report
        if report is None:
            return {
                "schema_version": HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION,
                "historical_mover_coverage_backfill_generated_count": int(
                    self._generated_count
                ),
                "historical_mover_coverage_record_audited_count": int(
                    self._record_audited_count
                ),
                "backfill_status": "",
                "reference_window_days": 0,
                "history_days_observed": 0,
                "top_mover_count": 0,
                "eligible_top_mover_count": 0,
                "captured_top_mover_count": 0,
                "partially_captured_top_mover_count": 0,
                "missed_top_mover_count": 0,
                "excluded_top_mover_count": 0,
                "capture_recall_rate": 0.0,
                "partial_capture_rate": 0.0,
                "miss_rate": 0.0,
                "anomaly_detected_rate": 0.0,
                "label_tracking_rate": 0.0,
                "tail_label_assigned_rate": 0.0,
                "strategy_validation_sample_rate": 0.0,
                "risk_rejected_mover_count": 0,
                "not_in_universe_count": 0,
                "missing_event_history_count": 0,
                "data_unreliable_count": 0,
                "median_first_seen_latency_seconds": None,
                "p90_first_seen_latency_seconds": None,
                "records": [],
                "miss_reason_summary": {},
                "coverage_warnings": [],
                "lookahead_guard_warnings": [],
                "report": {},
            }
        return {
            "schema_version": report.schema_version,
            "historical_mover_coverage_backfill_generated_count": int(
                self._generated_count
            ),
            "historical_mover_coverage_record_audited_count": int(
                self._record_audited_count
            ),
            "backfill_status": report.backfill_status,
            "reference_window_days": int(report.reference_window_days),
            "history_days_observed": int(report.history_days_observed),
            "top_mover_count": int(report.top_mover_count),
            "eligible_top_mover_count": int(report.eligible_top_mover_count),
            "captured_top_mover_count": int(report.captured_top_mover_count),
            "partially_captured_top_mover_count": int(
                report.partially_captured_top_mover_count
            ),
            "missed_top_mover_count": int(report.missed_top_mover_count),
            "excluded_top_mover_count": int(report.excluded_top_mover_count),
            "capture_recall_rate": float(report.capture_recall_rate),
            "partial_capture_rate": float(report.partial_capture_rate),
            "miss_rate": float(report.miss_rate),
            "anomaly_detected_rate": float(report.anomaly_detected_rate),
            "label_tracking_rate": float(report.label_tracking_rate),
            "tail_label_assigned_rate": float(
                report.tail_label_assigned_rate
            ),
            "strategy_validation_sample_rate": float(
                report.strategy_validation_sample_rate
            ),
            "risk_rejected_mover_count": int(report.risk_rejected_mover_count),
            "not_in_universe_count": int(report.not_in_universe_count),
            "missing_event_history_count": int(
                report.missing_event_history_count
            ),
            "data_unreliable_count": int(report.data_unreliable_count),
            "median_first_seen_latency_seconds": (
                report.median_first_seen_latency_seconds
            ),
            "p90_first_seen_latency_seconds": (
                report.p90_first_seen_latency_seconds
            ),
            "records": [
                {
                    "symbol": r.symbol,
                    "coverage_status": r.coverage_status,
                    "miss_reason": r.miss_reason,
                    "first_seen_time_utc_ms": r.first_seen_time_utc_ms,
                    "first_seen_event_type": r.first_seen_event_type,
                    "first_seen_latency_seconds": r.first_seen_latency_seconds,
                    "capture_path_depth": r.capture_path.capture_path_depth,
                    "top_mover_rank": r.reference.top_mover_rank,
                    "max_window_gain": r.reference.max_window_gain,
                    "reached_anomaly": r.capture_path.reached_anomaly,
                    "reached_label_queue": r.capture_path.reached_label_queue,
                    "reached_tail_label": r.capture_path.reached_tail_label,
                    "reached_strategy_validation_sample": (
                        r.capture_path.reached_strategy_validation_sample
                    ),
                    "risk_rejected": r.capture_path.risk_rejected,
                    "data_unreliable": r.capture_path.data_unreliable,
                }
                for r in report.records
            ],
            "miss_reason_summary": dict(report.miss_reason_summary),
            "coverage_warnings": list(report.coverage_warnings),
            "lookahead_guard_warnings": list(
                report.lookahead_guard_warnings
            ),
            "report": report.to_dict(),
        }

    # ------------------------------------------------------------------
    # Internal: event emission
    # ------------------------------------------------------------------
    def _emit_events(
        self,
        *,
        report: HistoricalMoverCoverageBackfillReport,
        audit_input: HistoricalMoverCoverageBackfillInput,
    ) -> None:
        report_payload: dict[str, Any] = report.to_dict()
        report_event = Event(
            event_type=EventType.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED,
            source_module=SOURCE_MODULE,
            payload={
                "schema_version": report.schema_version,
                "source_phase": report.source_phase,
                "backfill_status": report.backfill_status,
                "reference_window_days": int(report.reference_window_days),
                "history_days_observed": int(report.history_days_observed),
                "top_mover_count": int(report.top_mover_count),
                "eligible_top_mover_count": int(
                    report.eligible_top_mover_count
                ),
                "captured_top_mover_count": int(
                    report.captured_top_mover_count
                ),
                "partially_captured_top_mover_count": int(
                    report.partially_captured_top_mover_count
                ),
                "missed_top_mover_count": int(report.missed_top_mover_count),
                "excluded_top_mover_count": int(
                    report.excluded_top_mover_count
                ),
                "capture_recall_rate": float(report.capture_recall_rate),
                "partial_capture_rate": float(report.partial_capture_rate),
                "miss_rate": float(report.miss_rate),
                "anomaly_detected_rate": float(report.anomaly_detected_rate),
                "label_tracking_rate": float(report.label_tracking_rate),
                "tail_label_assigned_rate": float(
                    report.tail_label_assigned_rate
                ),
                "strategy_validation_sample_rate": float(
                    report.strategy_validation_sample_rate
                ),
                "risk_rejected_mover_count": int(
                    report.risk_rejected_mover_count
                ),
                "not_in_universe_count": int(report.not_in_universe_count),
                "missing_event_history_count": int(
                    report.missing_event_history_count
                ),
                "data_unreliable_count": int(report.data_unreliable_count),
                "median_first_seen_latency_seconds": (
                    report.median_first_seen_latency_seconds
                ),
                "p90_first_seen_latency_seconds": (
                    report.p90_first_seen_latency_seconds
                ),
                "miss_reason_summary": dict(report.miss_reason_summary),
                "coverage_warnings": list(report.coverage_warnings),
                "lookahead_guard_warnings": list(
                    report.lookahead_guard_warnings
                ),
                "audit_input": audit_input.to_dict(),
                "report": report_payload,
            },
            timestamp=int(report.generated_at_ms or now_ms()),
        )
        self._event_repo.append(report_event)
        self._generated_count += 1

        for record in report.records:
            record_event = Event(
                event_type=EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
                source_module=SOURCE_MODULE,
                payload={
                    "schema_version": record.schema_version,
                    "coverage_status": record.coverage_status,
                    "miss_reason": record.miss_reason,
                    "miss_reasons": list(record.miss_reasons),
                    "first_seen_time_utc_ms": record.first_seen_time_utc_ms,
                    "first_seen_event_type": record.first_seen_event_type,
                    "first_seen_latency_seconds": (
                        record.first_seen_latency_seconds
                    ),
                    "capture_path_depth": int(
                        record.capture_path.capture_path_depth
                    ),
                    "reached_anomaly": bool(record.capture_path.reached_anomaly),
                    "reached_label_queue": bool(
                        record.capture_path.reached_label_queue
                    ),
                    "reached_tail_label": bool(
                        record.capture_path.reached_tail_label
                    ),
                    "reached_strategy_validation_sample": bool(
                        record.capture_path.reached_strategy_validation_sample
                    ),
                    "risk_rejected": bool(record.capture_path.risk_rejected),
                    "data_unreliable": bool(
                        record.capture_path.data_unreliable
                    ),
                    "reference": record.reference.to_dict(),
                    "capture_path": record.capture_path.to_dict(),
                    "notes": record.notes,
                },
                symbol=record.symbol,
                timestamp=int(report.generated_at_ms or now_ms()),
            )
            self._event_repo.append(record_event)
            self._record_audited_count += 1


__all__ = (
    "HISTORICAL_MOVER_COVERAGE_BACKFILL_VERSION",
    "HISTORICAL_MOVER_COVERAGE_BACKFILL_SOURCE_PHASE",
    "HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION",
    "KNOWN_HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSIONS",
    "DEFAULT_REFERENCE_WINDOW_DAYS",
    "DEFAULT_TOP_MOVERS_PER_DAY",
    "DEFAULT_MIN_HISTORY_DAYS",
    "DEFAULT_DAILY_REPORT_RECORD_LIMIT",
    "HistoricalMoverCoverageBackfillStatus",
    "HistoricalMoverCoverageStatus",
    "HistoricalMoverMissReason",
    "HISTORICAL_CAPTURE_EVENT_ORDER",
    "HISTORICAL_NEGATIVE_SIGNAL_EVENTS",
    "LOOKAHEAD_FORBIDDEN_FIELDS",
    "HistoricalMoverLookaheadGuardError",
    "validate_no_lookahead_fields",
    "assert_capture_event_is_past_or_equal_reference_window",
    "HistoricalMoverReference",
    "HistoricalMoverReferenceSet",
    "HistoricalMoverCapturePath",
    "HistoricalMoverCoverageRecord",
    "HistoricalMoverCoverageBackfillInput",
    "HistoricalMoverCoverageBackfillReport",
    "HistoricalMarketStoreSnapshot",
    "load_historical_market_store",
    "build_historical_60d_mover_reference_set",
    "audit_historical_mover_capture_path",
    "classify_historical_miss_reason",
    "build_historical_mover_coverage_backfill_report",
    "export_historical_mover_coverage_payload",
    "load_historical_mover_coverage_payload",
    "HistoricalMoverCoverageBackfillRuntime",
)
