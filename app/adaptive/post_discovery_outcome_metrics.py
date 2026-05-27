"""Phase 11C.1C-C-B-B-B-D-B - Post-Discovery Outcome Metrics v0.

This module implements a paper-only / report-only / evidence-only
**Post-Discovery Outcome Metrics** layer that turns the Phase
11C.1C-C-B-B-B-D-A *Historical 60D Mover Coverage Backfill Audit
v0* records from a "where did we see this mover?" coverage signal
into a "what room was left to capture after we saw it?" outcome
signal.

The Phase 11C.1C-C-B-B-B-D-A audit only describes the discovery
layer:

    * did the system see the mover?
    * when was the first sighting?
    * how deep did the capture path go?
    * if missed, why?

Phase 11C.1C-C-B-B-B-D-B answers a different, follow-up question:

    * once the system first saw a mover, **how much room remained
      to be captured?**
    * was the first sighting *early*, *late*, *choppy*,
      *fake-breakout*, *late-reversal*, or *missed-strong-tail*?

The whole module is **paper / report / evidence only**. It does
NOT and CANNOT:

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

Public surface
--------------

    PostDiscoveryOutcomeInput      one mover's first-seen + price
                                   path bundle.
    PostDiscoveryOutcomeRecord     one mover's evaluated outcome.
    PostDiscoveryOutcomeReport     aggregate roll-up across many
                                   movers.
    PostDiscoveryOutcomeEvaluator  pure evaluator that turns one
                                   input into one record.

    DetectionTimingLabel           closed enum of timing labels.
    OutcomeLabel                   closed enum of outcome labels.

    POST_DISCOVERY_OUTCOME_FORBIDDEN_PAYLOAD_KEYS
                                   keys that MUST NEVER appear in
                                   any payload this module emits.
    assert_payload_has_no_forbidden_keys
                                   guard helper used by the
                                   evaluator and the report
                                   builder.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

POST_DISCOVERY_OUTCOME_METRICS_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_b.post_discovery_outcome_metrics.v0"
)
POST_DISCOVERY_OUTCOME_METRICS_SOURCE_PHASE: str = (
    "phase_11c_1c_c_b_b_b_d_b_post_discovery_outcome_metrics_v0"
)
POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_b.post_discovery_outcome_metrics.v1"
)
KNOWN_POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSIONS: tuple[str, ...] = (
    POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------


class DetectionTimingLabel:
    """Closed taxonomy describing the timing of the first sighting
    relative to the reference mover's full move.

    All labels are descriptive only - **never** an input to a
    trade-decision pipeline, the Risk Engine, the Execution FSM,
    ``symbol_limit``, candidate-pool capacity, anomaly thresholds,
    or Regime weights.
    """

    EARLY: str = "EARLY"
    EARLY_BUT_CHOPPY: str = "EARLY_BUT_CHOPPY"
    MID_MOVE: str = "MID_MOVE"
    LATE: str = "LATE"
    TOO_LATE: str = "TOO_LATE"
    MISSED: str = "MISSED"
    INSUFFICIENT_DATA: str = "INSUFFICIENT_DATA"

    ALL: tuple[str, ...] = (
        EARLY,
        EARLY_BUT_CHOPPY,
        MID_MOVE,
        LATE,
        TOO_LATE,
        MISSED,
        INSUFFICIENT_DATA,
    )


class OutcomeLabel:
    """Closed taxonomy describing the post-first-seen outcome shape.

    All labels are descriptive only - **never** an input to a
    trade-decision pipeline, the Risk Engine, the Execution FSM,
    ``symbol_limit``, candidate-pool capacity, anomaly thresholds,
    or Regime weights.
    """

    EARLY_CONTINUATION: str = "EARLY_CONTINUATION"
    EARLY_BUT_CHOPPY: str = "EARLY_BUT_CHOPPY"
    LATE_TOP_CHASE: str = "LATE_TOP_CHASE"
    LATE_REVERSAL: str = "LATE_REVERSAL"
    MISSED_STRONG_TAIL: str = "MISSED_STRONG_TAIL"
    FAKE_BREAKOUT: str = "FAKE_BREAKOUT"
    DUMPED: str = "DUMPED"
    EXHAUSTION_CANDIDATE: str = "EXHAUSTION_CANDIDATE"
    NO_CLEAR_EDGE: str = "NO_CLEAR_EDGE"
    INSUFFICIENT_PRICE_PATH: str = "INSUFFICIENT_PRICE_PATH"

    ALL: tuple[str, ...] = (
        EARLY_CONTINUATION,
        EARLY_BUT_CHOPPY,
        LATE_TOP_CHASE,
        LATE_REVERSAL,
        MISSED_STRONG_TAIL,
        FAKE_BREAKOUT,
        DUMPED,
        EXHAUSTION_CANDIDATE,
        NO_CLEAR_EDGE,
        INSUFFICIENT_PRICE_PATH,
    )


class CaptureStatus:
    """Mirrors the Phase 11C.1C-C-B-B-B-D-A coverage status taxonomy.

    Only the subset relevant to the post-discovery evaluation is
    enumerated here. The evaluator accepts any string but only
    these values are treated as semantically meaningful.
    """

    CAPTURED: str = "captured"
    PARTIALLY_CAPTURED: str = "partially_captured"
    MISSED: str = "missed"
    EXCLUDED: str = "excluded"

    ALL: tuple[str, ...] = (CAPTURED, PARTIALLY_CAPTURED, MISSED, EXCLUDED)


# ---------------------------------------------------------------------------
# Forbidden-payload guard
# ---------------------------------------------------------------------------


#: Keys that MUST NEVER appear in any payload this module emits. The
#: list is intentionally defensive: it is easier to extend the
#: forbidden set in a follow-up brief than to silently let a
#: trade-authority key slip into a paper / report payload.
POST_DISCOVERY_OUTCOME_FORBIDDEN_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        # Direction / side.
        "buy",
        "sell",
        "long",
        "short",
        "direction",
        "side",
        # Order plumbing.
        "entry",
        "entry_price",
        "exit",
        "exit_price",
        "order",
        "order_type",
        "execution_command",
        # Sizing / risk.
        "position_size",
        "leverage",
        "stop",
        "stop_loss",
        "stop_price",
        "target",
        "target_price",
        "take_profit",
        "risk_budget",
        # Runtime tuning.
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
    }
)


class PostDiscoveryOutcomeForbiddenFieldError(ValueError):
    """Raised when a payload contains one of the
    :data:`POST_DISCOVERY_OUTCOME_FORBIDDEN_PAYLOAD_KEYS`.
    """


def assert_payload_has_no_forbidden_keys(
    payload: Mapping[str, Any] | None,
    *,
    context: str = "",
    forbidden_keys: Iterable[str] = POST_DISCOVERY_OUTCOME_FORBIDDEN_PAYLOAD_KEYS,
) -> None:
    """Raise if ``payload`` (or any nested mapping) contains a
    forbidden key.

    The check is recursive but bounded - it walks ``Mapping``
    instances and ``list`` / ``tuple`` collections inside the
    payload but never recurses into freeform string blobs.
    """

    if payload is None:
        return
    forbidden_set = frozenset(forbidden_keys)

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                key_str = str(key)
                if key_str in forbidden_set:
                    raise PostDiscoveryOutcomeForbiddenFieldError(
                        "post-discovery outcome metrics: payload "
                        f"{context or '<unnamed>'} at {path}.{key_str} "
                        "contains forbidden key; the module is paper / "
                        "report / evidence only and MUST NOT carry "
                        "trade-authority or runtime-tuning fields"
                    )
                _walk(value, f"{path}.{key_str}")
        elif isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                _walk(item, f"{path}[{index}]")

    _walk(payload, context or "<root>")


# ---------------------------------------------------------------------------
# Default thresholds (descriptive only)
# ---------------------------------------------------------------------------

#: Minimum number of price points required after first_seen for the
#: evaluator to attempt anything other than ``INSUFFICIENT_DATA`` /
#: ``INSUFFICIENT_PRICE_PATH``.
DEFAULT_MIN_PRICE_PATH_POINTS: int = 2

#: A first-seen sighting whose ``remaining_upside_to_peak_pct`` is
#: at least this large is treated as ``EARLY``.
DEFAULT_EARLY_REMAINING_UPSIDE_PCT: float = 0.10

#: A first-seen sighting whose ``remaining_upside_to_peak_pct`` is
#: at most this small is treated as ``LATE`` (or ``TOO_LATE``).
DEFAULT_LATE_REMAINING_UPSIDE_PCT: float = 0.05

#: ``TOO_LATE`` threshold: essentially no upside left.
DEFAULT_TOO_LATE_REMAINING_UPSIDE_PCT: float = 0.005

#: A move with absolute MAE/MFE ratio above this is "choppy" / fake.
DEFAULT_CHOPPY_MAE_MFE_RATIO: float = 0.5

#: For a captured early sighting that still ends up with a large
#: drawdown, classify the outcome as EARLY_BUT_CHOPPY.
DEFAULT_CHOPPY_DRAWDOWN_PCT: float = 0.05

#: For a missed mover whose reference recorded a large remaining
#: upside, classify the outcome as MISSED_STRONG_TAIL.
DEFAULT_MISSED_STRONG_TAIL_PCT: float = 0.20

#: For an early sighting whose post-peak drawdown wipes out the
#: gain, classify the outcome as FAKE_BREAKOUT.
DEFAULT_FAKE_BREAKOUT_GIVEBACK_RATIO: float = 0.7


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PricePoint:
    """One price observation along the post-first-seen path.

    Both fields are required. ``timestamp_utc_ms`` is wall-clock
    epoch ms; ``price`` is a positive float. The evaluator never
    fabricates a price - missing observations cause the record to
    be flagged ``INSUFFICIENT_PRICE_PATH``.
    """

    timestamp_utc_ms: int
    price: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc_ms": int(self.timestamp_utc_ms),
            "price": float(self.price),
        }


@dataclass(frozen=True)
class HistoricalMoverReferenceSummary:
    """Lightweight view of the Phase 11C.1C-C-B-B-B-D-A reference row
    that is relevant to the post-discovery outcome evaluation.

    The full :class:`HistoricalMoverReference` carries more columns
    (rank, 24h gain, quote volume, ...) but this module only needs
    the prior-high anchor + the reference window's max gain to
    decide whether a missed mover ran a strong tail after the
    first sighting.
    """

    symbol: str
    reference_window: str = ""
    mover_window_start_utc_ms: int = 0
    mover_window_end_utc_ms: int = 0
    prior_high_time_utc_ms: int | None = None
    prior_high_price: float | None = None
    reference_peak_price: float | None = None
    reference_peak_time_utc_ms: int | None = None
    reference_max_window_gain_pct: float | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": str(self.symbol),
            "reference_window": str(self.reference_window),
            "mover_window_start_utc_ms": int(self.mover_window_start_utc_ms),
            "mover_window_end_utc_ms": int(self.mover_window_end_utc_ms),
            "prior_high_time_utc_ms": (
                int(self.prior_high_time_utc_ms)
                if self.prior_high_time_utc_ms is not None
                else None
            ),
            "prior_high_price": (
                float(self.prior_high_price)
                if self.prior_high_price is not None
                else None
            ),
            "reference_peak_price": (
                float(self.reference_peak_price)
                if self.reference_peak_price is not None
                else None
            ),
            "reference_peak_time_utc_ms": (
                int(self.reference_peak_time_utc_ms)
                if self.reference_peak_time_utc_ms is not None
                else None
            ),
            "reference_max_window_gain_pct": (
                float(self.reference_max_window_gain_pct)
                if self.reference_max_window_gain_pct is not None
                else None
            ),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class PostDiscoveryOutcomeInput:
    """One mover's evaluation input.

    Carries the identity columns (``symbol``, ``reference_window``),
    the first-seen anchor (timestamp + event type + price), the
    price path observed *after* the first sighting (a sequence of
    :class:`PricePoint`), the historical reference summary, the
    Phase 11C.1C-C-B-B-B-D-A capture status, the capture-path
    depth, and ``evidence_refs`` (links to the originating Phase
    11C.1C-C-B-B-B-D-A audit records).
    """

    symbol: str
    reference_window: str = ""
    first_seen_time_utc_ms: int | None = None
    first_seen_event_type: str | None = None
    first_seen_price: float | None = None
    price_path_after_first_seen: tuple[PricePoint, ...] = field(default_factory=tuple)
    historical_mover_reference: HistoricalMoverReferenceSummary | None = None
    capture_status: str = CaptureStatus.MISSED
    capture_path_depth: int = 0
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    notes: str | None = None
    schema_version: str = POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": str(self.symbol),
            "reference_window": str(self.reference_window),
            "first_seen_time_utc_ms": (
                int(self.first_seen_time_utc_ms)
                if self.first_seen_time_utc_ms is not None
                else None
            ),
            "first_seen_event_type": self.first_seen_event_type,
            "first_seen_price": (
                float(self.first_seen_price)
                if self.first_seen_price is not None
                else None
            ),
            "price_path_after_first_seen": [
                p.to_dict() for p in self.price_path_after_first_seen
            ],
            "historical_mover_reference": (
                self.historical_mover_reference.to_dict()
                if self.historical_mover_reference is not None
                else None
            ),
            "capture_status": str(self.capture_status),
            "capture_path_depth": int(self.capture_path_depth),
            "evidence_refs": list(self.evidence_refs),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class PostDiscoveryOutcomeRecord:
    """One evaluated mover record.

    Carries the identity columns, the first-seen anchor, the
    derived prior-high / post-seen-high / post-seen-low anchors,
    the descriptive metrics (MFE / MAE / remaining upside /
    drawdown / time-to-peak), and the closed
    :class:`DetectionTimingLabel` / :class:`OutcomeLabel`.

    The record carries ``evidence_refs`` (links to the source
    Phase 11C.1C-C-B-B-B-D-A audit records) so a downstream auditor
    can trace any number back to its origin without re-running
    the evaluator.

    ``warnings`` collects any descriptive notes the evaluator
    emitted (missing prior_high, ambiguous timing, etc.). The
    record is paper / evidence only - **no field below authorises
    a real trade or modifies any runtime knob**.
    """

    symbol: str
    reference_window: str
    first_seen_time_utc_ms: int | None
    first_seen_event_type: str | None
    first_seen_price: float | None

    prior_high_time_utc_ms: int | None
    prior_high_price: float | None
    distance_to_prior_high_pct: float | None

    post_seen_high_time_utc_ms: int | None
    post_seen_high_price: float | None
    post_seen_low_time_utc_ms: int | None
    post_seen_low_price: float | None

    remaining_upside_to_peak_pct: float | None
    post_seen_drawdown_pct: float | None
    mfe_pct: float | None
    mae_pct: float | None
    time_to_peak_seconds: float | None

    detection_timing_label: str
    outcome_label: str
    capture_status: str
    capture_path_depth: int

    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION
    source_phase: str = POST_DISCOVERY_OUTCOME_METRICS_SOURCE_PHASE

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "symbol": str(self.symbol),
            "reference_window": str(self.reference_window),
            "first_seen_time_utc_ms": self.first_seen_time_utc_ms,
            "first_seen_event_type": self.first_seen_event_type,
            "first_seen_price": self.first_seen_price,
            "prior_high_time_utc_ms": self.prior_high_time_utc_ms,
            "prior_high_price": self.prior_high_price,
            "distance_to_prior_high_pct": self.distance_to_prior_high_pct,
            "post_seen_high_time_utc_ms": self.post_seen_high_time_utc_ms,
            "post_seen_high_price": self.post_seen_high_price,
            "post_seen_low_time_utc_ms": self.post_seen_low_time_utc_ms,
            "post_seen_low_price": self.post_seen_low_price,
            "remaining_upside_to_peak_pct": self.remaining_upside_to_peak_pct,
            "post_seen_drawdown_pct": self.post_seen_drawdown_pct,
            "mfe_pct": self.mfe_pct,
            "mae_pct": self.mae_pct,
            "time_to_peak_seconds": self.time_to_peak_seconds,
            "detection_timing_label": str(self.detection_timing_label),
            "outcome_label": str(self.outcome_label),
            "capture_status": str(self.capture_status),
            "capture_path_depth": int(self.capture_path_depth),
            "evidence_refs": list(self.evidence_refs),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class PostDiscoveryOutcomeReport:
    """Aggregate roll-up across many :class:`PostDiscoveryOutcomeRecord`.

    Every field is descriptive only. The report MUST NEVER trigger
    a real trade or modify any runtime knob.
    """

    reference_window: str
    total_records: int
    early_count: int
    late_count: int
    missed_strong_tail_count: int
    fake_breakout_count: int
    insufficient_data_count: int
    median_remaining_upside_pct: float | None
    median_mfe_pct: float | None
    median_mae_pct: float | None
    detection_timing_label_summary: dict[str, int]
    outcome_label_summary: dict[str, int]
    records: tuple[PostDiscoveryOutcomeRecord, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION
    source_phase: str = POST_DISCOVERY_OUTCOME_METRICS_SOURCE_PHASE

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "reference_window": str(self.reference_window),
            "total_records": int(self.total_records),
            "early_count": int(self.early_count),
            "late_count": int(self.late_count),
            "missed_strong_tail_count": int(self.missed_strong_tail_count),
            "fake_breakout_count": int(self.fake_breakout_count),
            "insufficient_data_count": int(self.insufficient_data_count),
            "median_remaining_upside_pct": self.median_remaining_upside_pct,
            "median_mfe_pct": self.median_mfe_pct,
            "median_mae_pct": self.median_mae_pct,
            "detection_timing_label_summary": dict(
                sorted(self.detection_timing_label_summary.items())
            ),
            "outcome_label_summary": dict(
                sorted(self.outcome_label_summary.items())
            ),
            "records": [r.to_dict() for r in self.records],
            "warnings": list(self.warnings),
            "evidence_refs": list(self.evidence_refs),
        }


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _safe_pct(numerator: float | None, denominator: float | None) -> float | None:
    """Return ``numerator / denominator``; ``None`` if either side
    is missing or ``denominator`` is non-positive.
    """

    if numerator is None or denominator is None:
        return None
    try:
        denom = float(denominator)
    except (TypeError, ValueError):
        return None
    if denom <= 0.0:
        return None
    try:
        return float(numerator) / denom
    except (TypeError, ValueError):
        return None


def _median_or_none(values: Sequence[float]) -> float | None:
    """Median of ``values`` ignoring ``None``; ``None`` when empty."""

    cleaned = [float(v) for v in values if v is not None]
    if not cleaned:
        return None
    return statistics.median(cleaned)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PostDiscoveryOutcomeEvaluatorConfig:
    """Tunable thresholds for :class:`PostDiscoveryOutcomeEvaluator`.

    The defaults mirror the module-level ``DEFAULT_*`` constants.
    They are descriptive only - changing them does NOT and CANNOT
    change any runtime knob, the Risk Engine, the Execution FSM,
    ``symbol_limit``, candidate-pool capacity, anomaly thresholds,
    or Regime weights.
    """

    min_price_path_points: int = DEFAULT_MIN_PRICE_PATH_POINTS
    early_remaining_upside_pct: float = DEFAULT_EARLY_REMAINING_UPSIDE_PCT
    late_remaining_upside_pct: float = DEFAULT_LATE_REMAINING_UPSIDE_PCT
    too_late_remaining_upside_pct: float = DEFAULT_TOO_LATE_REMAINING_UPSIDE_PCT
    choppy_mae_mfe_ratio: float = DEFAULT_CHOPPY_MAE_MFE_RATIO
    choppy_drawdown_pct: float = DEFAULT_CHOPPY_DRAWDOWN_PCT
    missed_strong_tail_pct: float = DEFAULT_MISSED_STRONG_TAIL_PCT
    fake_breakout_giveback_ratio: float = DEFAULT_FAKE_BREAKOUT_GIVEBACK_RATIO


class PostDiscoveryOutcomeEvaluator:
    """Pure evaluator that turns one :class:`PostDiscoveryOutcomeInput`
    into one :class:`PostDiscoveryOutcomeRecord`.

    The evaluator does NOT make a network call, NEVER consults a
    private API, NEVER calls an LLM, and NEVER opens a Telegram
    socket. Every output field is derived deterministically from
    the input.

    Every emitted record is paper / report / evidence only.
    """

    def __init__(
        self,
        config: PostDiscoveryOutcomeEvaluatorConfig | None = None,
    ) -> None:
        self._config: PostDiscoveryOutcomeEvaluatorConfig = (
            config or PostDiscoveryOutcomeEvaluatorConfig()
        )

    # -----
    # Public
    # -----

    def evaluate(
        self,
        outcome_input: PostDiscoveryOutcomeInput,
    ) -> PostDiscoveryOutcomeRecord:
        """Evaluate ``outcome_input`` and return one record.

        The method is total: it ALWAYS returns a record, even when
        the price path is missing (in which case
        ``outcome_label = INSUFFICIENT_PRICE_PATH`` and
        ``detection_timing_label = INSUFFICIENT_DATA``).
        """

        warnings: list[str] = []
        cfg = self._config
        ref = outcome_input.historical_mover_reference

        # Identity columns.
        symbol = str(outcome_input.symbol)
        reference_window = str(outcome_input.reference_window)
        first_seen_time = outcome_input.first_seen_time_utc_ms
        first_seen_event = outcome_input.first_seen_event_type
        first_seen_price = outcome_input.first_seen_price

        # Reference-derived anchors.
        prior_high_time = ref.prior_high_time_utc_ms if ref is not None else None
        prior_high_price = ref.prior_high_price if ref is not None else None
        reference_peak_price = (
            ref.reference_peak_price if ref is not None else None
        )
        reference_peak_time = (
            ref.reference_peak_time_utc_ms if ref is not None else None
        )

        distance_to_prior_high_pct = _safe_pct(
            (first_seen_price - prior_high_price)
            if (first_seen_price is not None and prior_high_price is not None)
            else None,
            prior_high_price,
        )

        # ----- Insufficient-data short circuit -----
        path = tuple(outcome_input.price_path_after_first_seen or ())
        capture_status = outcome_input.capture_status

        # Highest priority: a missed mover whose reference recorded a
        # strong tail is MISSED_STRONG_TAIL even when no first_seen
        # price / no price path was supplied. The audit can still
        # describe "system never saw it but the move was real".
        if capture_status == CaptureStatus.MISSED and self._is_strong_tail(ref):
            warnings.append("missed_with_strong_reference_tail")
            return self._build_missed_strong_tail_record(
                outcome_input=outcome_input,
                prior_high_time=prior_high_time,
                prior_high_price=prior_high_price,
                distance_to_prior_high_pct=distance_to_prior_high_pct,
                warnings=warnings,
            )

        if first_seen_price is None or first_seen_price <= 0.0:
            warnings.append("missing_first_seen_price")
            return self._build_insufficient_record(
                outcome_input=outcome_input,
                prior_high_time=prior_high_time,
                prior_high_price=prior_high_price,
                distance_to_prior_high_pct=distance_to_prior_high_pct,
                warnings=warnings,
            )

        if len(path) < max(1, cfg.min_price_path_points):
            warnings.append("insufficient_price_path")
            return self._build_insufficient_record(
                outcome_input=outcome_input,
                prior_high_time=prior_high_time,
                prior_high_price=prior_high_price,
                distance_to_prior_high_pct=distance_to_prior_high_pct,
                warnings=warnings,
            )

        # Walk the price path to derive post-seen extrema.
        post_high_point = max(path, key=lambda p: p.price)
        post_low_point = min(path, key=lambda p: p.price)

        post_seen_high_time = post_high_point.timestamp_utc_ms
        post_seen_high_price = post_high_point.price
        post_seen_low_time = post_low_point.timestamp_utc_ms
        post_seen_low_price = post_low_point.price

        mfe_pct = _safe_pct(
            post_seen_high_price - first_seen_price, first_seen_price
        )
        mae_pct = _safe_pct(
            post_seen_low_price - first_seen_price, first_seen_price
        )

        # Remaining upside is computed against the reference peak when
        # available, otherwise against the post-seen high.
        peak_price_for_remaining = (
            reference_peak_price
            if reference_peak_price is not None
            and reference_peak_price >= post_seen_high_price
            else post_seen_high_price
        )
        remaining_upside_to_peak_pct = _safe_pct(
            peak_price_for_remaining - first_seen_price, first_seen_price
        )

        # Drawdown after the first sighting (positive = magnitude of loss).
        post_seen_drawdown_pct = (
            -mae_pct if mae_pct is not None and mae_pct < 0.0 else 0.0
        )

        # Time-to-peak: prefer reference peak time, fall back to
        # post-seen high time. Never negative.
        time_to_peak_seconds = self._compute_time_to_peak_seconds(
            first_seen_time=first_seen_time,
            reference_peak_time=reference_peak_time,
            post_seen_high_time=post_seen_high_time,
        )

        # Capture-status / evidence may flip the labels: a missed
        # mover with a strong-tail reference is MISSED_STRONG_TAIL
        # regardless of any path observed afterwards.
        if capture_status == CaptureStatus.MISSED and self._is_strong_tail(ref):
            detection_timing_label = DetectionTimingLabel.MISSED
            outcome_label = OutcomeLabel.MISSED_STRONG_TAIL
        else:
            detection_timing_label = self._classify_timing(
                remaining_upside_to_peak_pct=remaining_upside_to_peak_pct,
                mfe_pct=mfe_pct,
                mae_pct=mae_pct,
            )
            outcome_label = self._classify_outcome(
                detection_timing_label=detection_timing_label,
                remaining_upside_to_peak_pct=remaining_upside_to_peak_pct,
                mfe_pct=mfe_pct,
                mae_pct=mae_pct,
                post_seen_high_price=post_seen_high_price,
                final_price=path[-1].price,
                first_seen_price=first_seen_price,
            )

        evidence_refs = tuple(outcome_input.evidence_refs)

        record = PostDiscoveryOutcomeRecord(
            symbol=symbol,
            reference_window=reference_window,
            first_seen_time_utc_ms=first_seen_time,
            first_seen_event_type=first_seen_event,
            first_seen_price=first_seen_price,
            prior_high_time_utc_ms=prior_high_time,
            prior_high_price=prior_high_price,
            distance_to_prior_high_pct=distance_to_prior_high_pct,
            post_seen_high_time_utc_ms=post_seen_high_time,
            post_seen_high_price=post_seen_high_price,
            post_seen_low_time_utc_ms=post_seen_low_time,
            post_seen_low_price=post_seen_low_price,
            remaining_upside_to_peak_pct=remaining_upside_to_peak_pct,
            post_seen_drawdown_pct=post_seen_drawdown_pct,
            mfe_pct=mfe_pct,
            mae_pct=mae_pct,
            time_to_peak_seconds=time_to_peak_seconds,
            detection_timing_label=detection_timing_label,
            outcome_label=outcome_label,
            capture_status=str(capture_status),
            capture_path_depth=int(outcome_input.capture_path_depth),
            evidence_refs=evidence_refs,
            warnings=tuple(warnings),
        )

        # Defence-in-depth: refuse to emit a record whose payload
        # accidentally contains a forbidden trade-authority field.
        assert_payload_has_no_forbidden_keys(
            record.to_dict(), context=f"record:{symbol}"
        )
        return record

    # -----
    # Internal helpers
    # -----

    def _is_strong_tail(
        self, ref: HistoricalMoverReferenceSummary | None
    ) -> bool:
        if ref is None:
            return False
        gain = ref.reference_max_window_gain_pct
        if gain is None:
            return False
        return gain >= self._config.missed_strong_tail_pct

    def _build_insufficient_record(
        self,
        *,
        outcome_input: PostDiscoveryOutcomeInput,
        prior_high_time: int | None,
        prior_high_price: float | None,
        distance_to_prior_high_pct: float | None,
        warnings: list[str],
    ) -> PostDiscoveryOutcomeRecord:
        record = PostDiscoveryOutcomeRecord(
            symbol=str(outcome_input.symbol),
            reference_window=str(outcome_input.reference_window),
            first_seen_time_utc_ms=outcome_input.first_seen_time_utc_ms,
            first_seen_event_type=outcome_input.first_seen_event_type,
            first_seen_price=outcome_input.first_seen_price,
            prior_high_time_utc_ms=prior_high_time,
            prior_high_price=prior_high_price,
            distance_to_prior_high_pct=distance_to_prior_high_pct,
            post_seen_high_time_utc_ms=None,
            post_seen_high_price=None,
            post_seen_low_time_utc_ms=None,
            post_seen_low_price=None,
            remaining_upside_to_peak_pct=None,
            post_seen_drawdown_pct=None,
            mfe_pct=None,
            mae_pct=None,
            time_to_peak_seconds=None,
            detection_timing_label=DetectionTimingLabel.INSUFFICIENT_DATA,
            outcome_label=OutcomeLabel.INSUFFICIENT_PRICE_PATH,
            capture_status=str(outcome_input.capture_status),
            capture_path_depth=int(outcome_input.capture_path_depth),
            evidence_refs=tuple(outcome_input.evidence_refs),
            warnings=tuple(warnings),
        )
        assert_payload_has_no_forbidden_keys(
            record.to_dict(), context=f"insufficient_record:{outcome_input.symbol}"
        )
        return record

    def _build_missed_strong_tail_record(
        self,
        *,
        outcome_input: PostDiscoveryOutcomeInput,
        prior_high_time: int | None,
        prior_high_price: float | None,
        distance_to_prior_high_pct: float | None,
        warnings: list[str],
    ) -> PostDiscoveryOutcomeRecord:
        ref = outcome_input.historical_mover_reference
        ref_peak_price = ref.reference_peak_price if ref is not None else None
        ref_peak_time = (
            ref.reference_peak_time_utc_ms if ref is not None else None
        )
        ref_gain = (
            ref.reference_max_window_gain_pct if ref is not None else None
        )
        record = PostDiscoveryOutcomeRecord(
            symbol=str(outcome_input.symbol),
            reference_window=str(outcome_input.reference_window),
            first_seen_time_utc_ms=outcome_input.first_seen_time_utc_ms,
            first_seen_event_type=outcome_input.first_seen_event_type,
            first_seen_price=outcome_input.first_seen_price,
            prior_high_time_utc_ms=prior_high_time,
            prior_high_price=prior_high_price,
            distance_to_prior_high_pct=distance_to_prior_high_pct,
            post_seen_high_time_utc_ms=ref_peak_time,
            post_seen_high_price=ref_peak_price,
            post_seen_low_time_utc_ms=None,
            post_seen_low_price=None,
            remaining_upside_to_peak_pct=ref_gain,
            post_seen_drawdown_pct=None,
            mfe_pct=ref_gain,
            mae_pct=None,
            time_to_peak_seconds=None,
            detection_timing_label=DetectionTimingLabel.MISSED,
            outcome_label=OutcomeLabel.MISSED_STRONG_TAIL,
            capture_status=str(outcome_input.capture_status),
            capture_path_depth=int(outcome_input.capture_path_depth),
            evidence_refs=tuple(outcome_input.evidence_refs),
            warnings=tuple(warnings),
        )
        assert_payload_has_no_forbidden_keys(
            record.to_dict(),
            context=f"missed_strong_tail_record:{outcome_input.symbol}",
        )
        return record

    def _compute_time_to_peak_seconds(
        self,
        *,
        first_seen_time: int | None,
        reference_peak_time: int | None,
        post_seen_high_time: int | None,
    ) -> float | None:
        if first_seen_time is None:
            return None
        peak_time = (
            reference_peak_time
            if reference_peak_time is not None
            else post_seen_high_time
        )
        if peak_time is None:
            return None
        delta_ms = float(peak_time) - float(first_seen_time)
        if delta_ms < 0.0:
            return 0.0
        return delta_ms / 1000.0

    def _classify_timing(
        self,
        *,
        remaining_upside_to_peak_pct: float | None,
        mfe_pct: float | None,
        mae_pct: float | None,
    ) -> str:
        cfg = self._config
        if remaining_upside_to_peak_pct is None:
            return DetectionTimingLabel.INSUFFICIENT_DATA
        ru = remaining_upside_to_peak_pct
        choppy = self._is_choppy(mfe_pct=mfe_pct, mae_pct=mae_pct)
        if ru >= cfg.early_remaining_upside_pct:
            if choppy:
                return DetectionTimingLabel.EARLY_BUT_CHOPPY
            return DetectionTimingLabel.EARLY
        if ru <= cfg.too_late_remaining_upside_pct:
            return DetectionTimingLabel.TOO_LATE
        if ru <= cfg.late_remaining_upside_pct:
            return DetectionTimingLabel.LATE
        return DetectionTimingLabel.MID_MOVE

    def _is_choppy(
        self,
        *,
        mfe_pct: float | None,
        mae_pct: float | None,
    ) -> bool:
        cfg = self._config
        if mfe_pct is None or mae_pct is None:
            return False
        mae_mag = abs(mae_pct)
        if mae_mag < cfg.choppy_drawdown_pct:
            return False
        # If the MFE is non-positive there is no upside leg to chop
        # against; treat MAE alone as drawdown not chop.
        if mfe_pct <= 0.0:
            return False
        ratio = mae_mag / mfe_pct
        return ratio >= cfg.choppy_mae_mfe_ratio

    def _classify_outcome(
        self,
        *,
        detection_timing_label: str,
        remaining_upside_to_peak_pct: float | None,
        mfe_pct: float | None,
        mae_pct: float | None,
        post_seen_high_price: float,
        final_price: float,
        first_seen_price: float,
    ) -> str:
        cfg = self._config

        # Pure drawdown without upside.
        if (mfe_pct is None or mfe_pct <= 0.0) and (
            mae_pct is not None and mae_pct < 0.0
        ):
            # Big drawdown -> DUMPED; small drawdown still no edge.
            if mae_pct <= -cfg.choppy_drawdown_pct:
                return OutcomeLabel.DUMPED
            return OutcomeLabel.NO_CLEAR_EDGE

        # Determine whether the post-seen high gave back most of the gain.
        gave_back = self._gave_back_most_of_gain(
            post_seen_high_price=post_seen_high_price,
            final_price=final_price,
            first_seen_price=first_seen_price,
        )

        if detection_timing_label == DetectionTimingLabel.EARLY:
            if gave_back:
                return OutcomeLabel.FAKE_BREAKOUT
            return OutcomeLabel.EARLY_CONTINUATION

        if detection_timing_label == DetectionTimingLabel.EARLY_BUT_CHOPPY:
            return OutcomeLabel.EARLY_BUT_CHOPPY

        if detection_timing_label == DetectionTimingLabel.MID_MOVE:
            if gave_back:
                return OutcomeLabel.FAKE_BREAKOUT
            return OutcomeLabel.NO_CLEAR_EDGE

        if detection_timing_label == DetectionTimingLabel.LATE:
            # Late sighting that still ran is LATE_TOP_CHASE.
            if mfe_pct is not None and mfe_pct > 0.0 and not gave_back:
                return OutcomeLabel.LATE_TOP_CHASE
            # Late sighting that reverses adversely.
            if mae_pct is not None and mae_pct < 0.0 and (
                mfe_pct is None or abs(mae_pct) >= mfe_pct
            ):
                return OutcomeLabel.LATE_REVERSAL
            return OutcomeLabel.LATE_TOP_CHASE

        if detection_timing_label == DetectionTimingLabel.TOO_LATE:
            if mae_pct is not None and mae_pct < 0.0:
                return OutcomeLabel.LATE_REVERSAL
            return OutcomeLabel.EXHAUSTION_CANDIDATE

        # Fallback - never normally reached because INSUFFICIENT_DATA
        # is short-circuited above.
        return OutcomeLabel.NO_CLEAR_EDGE

    def _gave_back_most_of_gain(
        self,
        *,
        post_seen_high_price: float,
        final_price: float,
        first_seen_price: float,
    ) -> bool:
        gain = post_seen_high_price - first_seen_price
        if gain <= 0.0:
            return False
        giveback = post_seen_high_price - final_price
        if giveback <= 0.0:
            return False
        ratio = giveback / gain
        return ratio >= self._config.fake_breakout_giveback_ratio


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_post_discovery_outcome_report(
    records: Sequence[PostDiscoveryOutcomeRecord],
    *,
    reference_window: str = "",
    extra_warnings: Sequence[str] = (),
) -> PostDiscoveryOutcomeReport:
    """Aggregate ``records`` into a :class:`PostDiscoveryOutcomeReport`.

    The function is pure; it does not call any network service,
    LLM, or Telegram transport. Every emitted field is descriptive
    paper / report / evidence only.
    """

    record_tuple = tuple(records)

    detection_summary: dict[str, int] = {}
    outcome_summary: dict[str, int] = {}
    early_count = 0
    late_count = 0
    missed_strong_tail_count = 0
    fake_breakout_count = 0
    insufficient_data_count = 0
    remaining_upside_values: list[float] = []
    mfe_values: list[float] = []
    mae_values: list[float] = []
    evidence_refs: list[str] = []

    for record in record_tuple:
        timing = str(record.detection_timing_label)
        outcome = str(record.outcome_label)
        detection_summary[timing] = detection_summary.get(timing, 0) + 1
        outcome_summary[outcome] = outcome_summary.get(outcome, 0) + 1
        if timing in (
            DetectionTimingLabel.EARLY,
            DetectionTimingLabel.EARLY_BUT_CHOPPY,
        ):
            early_count += 1
        if timing in (
            DetectionTimingLabel.LATE,
            DetectionTimingLabel.TOO_LATE,
        ):
            late_count += 1
        if outcome == OutcomeLabel.MISSED_STRONG_TAIL:
            missed_strong_tail_count += 1
        if outcome == OutcomeLabel.FAKE_BREAKOUT:
            fake_breakout_count += 1
        if (
            outcome == OutcomeLabel.INSUFFICIENT_PRICE_PATH
            or timing == DetectionTimingLabel.INSUFFICIENT_DATA
        ):
            insufficient_data_count += 1
        if record.remaining_upside_to_peak_pct is not None:
            remaining_upside_values.append(
                float(record.remaining_upside_to_peak_pct)
            )
        if record.mfe_pct is not None:
            mfe_values.append(float(record.mfe_pct))
        if record.mae_pct is not None:
            mae_values.append(float(record.mae_pct))
        evidence_refs.extend(record.evidence_refs)

    report = PostDiscoveryOutcomeReport(
        reference_window=str(reference_window),
        total_records=len(record_tuple),
        early_count=early_count,
        late_count=late_count,
        missed_strong_tail_count=missed_strong_tail_count,
        fake_breakout_count=fake_breakout_count,
        insufficient_data_count=insufficient_data_count,
        median_remaining_upside_pct=_median_or_none(remaining_upside_values),
        median_mfe_pct=_median_or_none(mfe_values),
        median_mae_pct=_median_or_none(mae_values),
        detection_timing_label_summary=detection_summary,
        outcome_label_summary=outcome_summary,
        records=record_tuple,
        warnings=tuple(extra_warnings),
        evidence_refs=tuple(dict.fromkeys(evidence_refs)),
    )

    assert_payload_has_no_forbidden_keys(
        report.to_dict(), context=f"report:{reference_window}"
    )
    return report


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


__all__ = [
    "POST_DISCOVERY_OUTCOME_METRICS_VERSION",
    "POST_DISCOVERY_OUTCOME_METRICS_SOURCE_PHASE",
    "POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION",
    "KNOWN_POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSIONS",
    "POST_DISCOVERY_OUTCOME_FORBIDDEN_PAYLOAD_KEYS",
    "DEFAULT_MIN_PRICE_PATH_POINTS",
    "DEFAULT_EARLY_REMAINING_UPSIDE_PCT",
    "DEFAULT_LATE_REMAINING_UPSIDE_PCT",
    "DEFAULT_TOO_LATE_REMAINING_UPSIDE_PCT",
    "DEFAULT_CHOPPY_MAE_MFE_RATIO",
    "DEFAULT_CHOPPY_DRAWDOWN_PCT",
    "DEFAULT_MISSED_STRONG_TAIL_PCT",
    "DEFAULT_FAKE_BREAKOUT_GIVEBACK_RATIO",
    "DetectionTimingLabel",
    "OutcomeLabel",
    "CaptureStatus",
    "PostDiscoveryOutcomeForbiddenFieldError",
    "PricePoint",
    "HistoricalMoverReferenceSummary",
    "PostDiscoveryOutcomeInput",
    "PostDiscoveryOutcomeRecord",
    "PostDiscoveryOutcomeReport",
    "PostDiscoveryOutcomeEvaluatorConfig",
    "PostDiscoveryOutcomeEvaluator",
    "build_post_discovery_outcome_report",
    "assert_payload_has_no_forbidden_keys",
]
