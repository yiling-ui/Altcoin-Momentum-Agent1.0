"""Phase 11C.1C-C-B-B-B-D - Mover Capture Recall & Missed-Tail Coverage Audit v0.

The Mover Capture Recall & Missed-Tail Coverage Audit v0 is a
**paper-only / report-only / evidence-only** coverage audit layer
that institutionalises the operator's "did the system actually see
this mover?" cross-check.

It consumes existing surfaces:

  - the public Binance 24h ticker / market data already pulled by
    the Phase 11C.1B WS-radar / public market data adapter;
  - the :class:`EventRepository` event log;
  - the Phase 11B daily-report aggregates;
  - the Phase 8.5 export / Phase 10A replay bundles;
  - the Phase 11C.1C-C-B-B-A
    :class:`StrategyValidationDataset`;
  - the Phase 11C.1C-C-B-B-B-A :class:`PaperAlphaGateReport`
    verdict (when present);
  - the Phase 11C.1C-C-B-B-B-B :class:`RegimeClusterEvidencePack`
    cohort summaries (when present);
  - the Phase 11C.1B :class:`SymbolUniverse`
    (exchangeInfo-as-truth) catalogue.

It produces:

  - one :class:`MoverCaptureRecallAuditReport` per audit window;
  - one :class:`MoverCaptureAuditRecord` per top mover (CAPTURED,
    PARTIALLY_CAPTURED, MISSED, EXCLUDED, INSUFFICIENT_DATA);
  - per-mover :class:`CapturePathEvidence` for every step of the
    Phase 11C.1C-A / 11C.1C-C-A / 11C.1C-C-B-A / 11C.1C-C-B-B-A
    chain;
  - structured ``miss_reasons`` per the brief's miss-reason
    taxonomy.

Phase 11C.1C-C-B-B-B-D boundary
-------------------------------

This module:

  - is paper / virtual ONLY;
  - is contract + pure functions; nothing here triggers a real
    trade, opens a position, modifies a stop-loss / target price /
    leverage, the Risk Engine, the Execution FSM, ``symbol_limit``,
    candidate-pool capacity, anomaly thresholds, Regime weights,
    or any other runtime knob;
  - the per-mover ``audit_status`` is **descriptive only** - one
    of ``CAPTURED`` / ``PARTIALLY_CAPTURED`` / ``MISSED`` /
    ``EXCLUDED`` / ``INSUFFICIENT_DATA`` - and is NEVER an input
    to a trade-decision pipeline; the Risk Engine remains the
    single trade-decision gate;
  - is **NOT** a new strategy, **NOT** a trading module, **NOT**
    AI Learning, **NOT** automatic parameter optimisation, **NOT**
    reinforcement learning, **NOT** a Historical 30D+ Blind Replay
    / Walk-forward Validation gate (that gate is a Phase 12
    candidate pre-gate and is explicitly out of scope here),
    **NOT** the complete Strategy Validation Lab follow-up,
    **NOT** Phase 12;
  - tags every payload with a ``schema_version`` field so old
    payloads without the v0 sub-block remain replayable verbatim;
  - degrades safely when an upstream surface is missing - e.g.
    when no public ticker rows are available, the module emits an
    ``INSUFFICIENT_DATA`` report rather than raising;
  - never auto-relaxes thresholds when a single mover is missed -
    the brief explicitly forbids reacting to single-coin cases
    such as a single SAGAUSDT print.

Interpretation contract (carried in the report, the docs, and every
event payload)
-------------------------------------------------------------------

    * Captured-but-rejected ≠ failure: a mover that the chain saw
      and the Risk Engine declined is still *covered* by the
      discovery layer.
    * Missed-but-not-in-eligible-universe ≠ failure: a mover that is
      not a USDT-perpetual or has been delisted is correctly
      excluded from the audit.
    * A coverage warning fires only when the mover is in the
      eligible USDT-perpetual universe AND shows a clear right-tail
      signal AND was missed for a system-correctable reason.
    * A single coin proves nothing. Low coverage cannot
      auto-relax rules; high coverage cannot authorise live
      trading. Both flow into human review only.
    * The audit can only describe the *discovery* layer. It cannot
      attest to trading PnL, alpha, or the outcome of a real
      position - the Risk Engine + Execution FSM remain the
      single trade-decision gates.

The runtime that wires this module (the Phase 11B paper-run
:class:`StrategyValidationRuntime` host) emits at most TWO new
typed events:

  - ``MOVER_CAPTURE_RECALL_AUDIT_GENERATED`` - one per audit
    window (top-level :class:`MoverCaptureRecallAuditReport` payload).
  - ``MOVER_CAPTURE_PATH_AUDITED`` - one per audited top mover.

Every event payload includes ``report_id``, ``audit_id``,
``timestamp``, ``audit_status`` (or report_status),
``strategy_version``, ``scoring_version``, ``risk_config_version``,
``state_machine_version``, and ``schema_version`` so Reflection /
Replay can group on them without parsing free-form audit dicts.
"""

from __future__ import annotations

import statistics
from typing import Any, Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Schema version stamp written on every Phase 11C.1C-C-B-B-B-D
#: payload. A future PR that changes the payload shape MUST bump
#: this label.
MOVER_CAPTURE_RECALL_AUDIT_SCHEMA_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d.mover_capture_recall_audit.v1"
)
KNOWN_MOVER_CAPTURE_RECALL_AUDIT_SCHEMA_VERSIONS: tuple[str, ...] = (
    MOVER_CAPTURE_RECALL_AUDIT_SCHEMA_VERSION,
)

#: Phase 11C.1C-C-B-B-B-D canonical version labels. Carried on
#: every event payload so Reflection / Replay can group on them.
MOVER_CAPTURE_RECALL_AUDIT_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d.mover_capture_recall_audit.v1"
)
MOVER_CAPTURE_RECALL_AUDIT_SOURCE_PHASE: str = (
    "phase_11c_1c_c_b_b_b_d_mover_capture_recall_audit_v0"
)


# ---------------------------------------------------------------------------
# Status taxonomy
# ---------------------------------------------------------------------------
class MoverCaptureRecallAuditStatus:
    """Allowed top-level audit-report status labels.

    The status is **descriptive only** - none of these labels
    authorises a real trade or modifies any runtime state.
    """

    OK: str = "OK"  # the audit report is well-formed and useful
    INSUFFICIENT_DATA: str = "INSUFFICIENT_DATA"  # no usable input
    DEGRADED: str = "DEGRADED"  # generated but with warnings

    ALL: tuple[str, ...] = ("OK", "INSUFFICIENT_DATA", "DEGRADED")


MOVER_CAPTURE_RECALL_AUDIT_STATUSES: tuple[str, ...] = (
    MoverCaptureRecallAuditStatus.ALL
)


class CapturePathStatus:
    """Allowed per-mover capture status labels.

    The status is **descriptive only** - none of these labels
    authorises a real trade or modifies any runtime state.
    """

    CAPTURED: str = "CAPTURED"
    PARTIALLY_CAPTURED: str = "PARTIALLY_CAPTURED"
    MISSED: str = "MISSED"
    EXCLUDED: str = "EXCLUDED"
    INSUFFICIENT_DATA: str = "INSUFFICIENT_DATA"

    ALL: tuple[str, ...] = (
        "CAPTURED",
        "PARTIALLY_CAPTURED",
        "MISSED",
        "EXCLUDED",
        "INSUFFICIENT_DATA",
    )


CAPTURE_PATH_STATUSES: tuple[str, ...] = CapturePathStatus.ALL


# ---------------------------------------------------------------------------
# Miss-reason taxonomy
# ---------------------------------------------------------------------------
class MissReason:
    """Structured reasons describing why a top mover was not fully
    captured. All values are **descriptive only**.

    Members mirror the Phase 11C.1C-C-B-B-B-D brief verbatim. Future
    PRs may add new reasons; old reasons MUST stay so replay does
    not break.
    """

    NOT_IN_FUTURES_UNIVERSE: str = "not_in_futures_universe"
    SYMBOL_NOT_IN_EXCHANGE_INFO: str = "symbol_not_in_exchange_info"
    NOT_USDT_PERPETUAL: str = "not_usdt_perpetual"
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

    ALL: tuple[str, ...] = (
        "not_in_futures_universe",
        "symbol_not_in_exchange_info",
        "not_usdt_perpetual",
        "below_liquidity_threshold",
        "symbol_limit_excluded",
        "candidate_pool_evicted",
        "insufficient_ws_data",
        "stale_data",
        "data_unreliable",
        "no_anomaly_threshold_cross",
        "risk_rejected",
        "no_completed_tail_label_yet",
        "unknown",
    )


MISS_REASONS: tuple[str, ...] = MissReason.ALL


# ---------------------------------------------------------------------------
# Capture-path stage names
# ---------------------------------------------------------------------------
#: The full ordered list of capture-path stages the audit walks.
#: Each name is also the name of a typed event the runtime emits
#: (see app/core/events.py for the canonical vocabulary). The
#: names are reused verbatim in :class:`CapturePathEvidence` so a
#: human reviewer can read the per-stage map straight from the
#: event vocabulary.
CAPTURE_PATH_STAGES: tuple[str, ...] = (
    "MARKET_SNAPSHOT",
    "CANDIDATE_POOL",
    "PRE_ANOMALY_DETECTED",
    "ANOMALY_DETECTED",
    "MARKET_REGIME_ASSESSED",
    "CANDIDATE_STAGE_CLASSIFIED",
    "OPPORTUNITY_SCORED",
    "STRATEGY_MODE_SELECTED",
    "CLUSTER_CONTEXT_ATTACHED",
    "LABEL_QUEUE_ENQUEUED",
    "LABEL_TRACKING_STARTED",
    "LABEL_WINDOW_COMPLETED",
    "TAIL_LABEL_ASSIGNED",
    "STRATEGY_VALIDATION_SAMPLE_CREATED",
    "RISK_REJECTED",
    "DATA_UNRELIABLE",
    "DAILY_REPORT_OR_EXPORT_EVIDENCE",
)

#: The minimum subset of stages required to count a mover as
#: ``CAPTURED``. Phase 11C.1C-C-B-B-B-D defines "fully captured"
#: as: the discovery chain saw the mover (MARKET_SNAPSHOT or
#: CANDIDATE_POOL), classified the candidate
#: (CANDIDATE_STAGE_CLASSIFIED), scored it (OPPORTUNITY_SCORED),
#: and either reached LABEL_QUEUE_ENQUEUED OR was explicitly
#: RISK_REJECTED (rejection-after-discovery counts as capture).
CAPTURED_REQUIRED_STAGES: tuple[str, ...] = (
    "MARKET_SNAPSHOT",
    "CANDIDATE_STAGE_CLASSIFIED",
    "OPPORTUNITY_SCORED",
)
CAPTURED_TERMINAL_STAGES: tuple[str, ...] = (
    "LABEL_QUEUE_ENQUEUED",
    "RISK_REJECTED",
)

#: Stages whose presence promotes a mover from
#: ``PARTIALLY_CAPTURED`` to ``CAPTURED`` (any one suffices). A
#: completed tail label or strategy-validation sample is
#: considered the strongest evidence of full capture.
FULL_CAPTURE_STRONG_STAGES: tuple[str, ...] = (
    "TAIL_LABEL_ASSIGNED",
    "STRATEGY_VALIDATION_SAMPLE_CREATED",
)


# ---------------------------------------------------------------------------
# Default thresholds
# ---------------------------------------------------------------------------
#: Maximum number of top movers to include in the reference set.
#: Defaults to 20 - small enough that a human reviewer can scan
#: every row in the daily report.
DEFAULT_TOP_MOVER_LIMIT: int = 20

#: Minimum 24h price change (decimal; +0.10 = +10%) for a symbol
#: to enter the top mover reference set. Tunable; the runtime
#: passes the configured value in via the input.
DEFAULT_MIN_PRICE_CHANGE_PCT: float = 0.10

#: Minimum 24h quote-volume (USDT) for a symbol to count as
#: liquid enough to be considered a top mover.
DEFAULT_MIN_QUOTE_VOLUME_USDT: float = 1_000_000.0

#: Minimum number of top mover rows required to leave
#: ``INSUFFICIENT_DATA``.
DEFAULT_MIN_TOP_MOVER_COUNT: int = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalise_symbol(symbol: Any) -> str:
    """Return a stripped string symbol; never raises.

    The audit accepts non-ASCII symbols (e.g. ``币安人生USDT``) -
    Phase 11C.1B forbids character-class regex validation.
    """
    if symbol is None:
        return ""
    return str(symbol).strip()


def _safe_ratio(numerator: int, denominator: int) -> float:
    """Return ``numerator / denominator``; 0.0 when denominator is 0."""
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


# ---------------------------------------------------------------------------
# Models - Top Mover Reference
# ---------------------------------------------------------------------------
class TopMoverReference(BaseModel):
    """One row of the top-mover reference set.

    All fields are descriptive. The reference set is built from
    public Binance 24h ticker / market-snapshot data ONLY. No
    private API. Entries flagged ``in_eligible_universe=False``
    are kept (so a human reviewer can audit the exclusion) but
    are reported with status ``EXCLUDED``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    rank: int = 0  # 1-based; 0 means "unranked"
    price_change_pct: float = 0.0  # 24h % change (decimal: +0.10 = +10%)
    quote_volume_usdt: float = 0.0  # 24h quote-volume in USDT
    last_price: float = 0.0
    first_seen_ts: int = 0  # public-data first-seen timestamp (ms)
    in_eligible_universe: bool = True
    not_in_futures_universe_reason: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _check_symbol(cls, value: str) -> str:
        return _normalise_symbol(value)

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": str(self.symbol),
            "rank": int(self.rank),
            "price_change_pct": float(self.price_change_pct),
            "quote_volume_usdt": float(self.quote_volume_usdt),
            "last_price": float(self.last_price),
            "first_seen_ts": int(self.first_seen_ts),
            "in_eligible_universe": bool(self.in_eligible_universe),
            "not_in_futures_universe_reason": str(
                self.not_in_futures_universe_reason
            ),
            "extra": dict(self.extra),
        }


# ---------------------------------------------------------------------------
# Models - Capture path evidence
# ---------------------------------------------------------------------------
class CapturePathEvidence(BaseModel):
    """Per-stage capture evidence for one top mover.

    ``observed`` reflects whether the runtime saw the stage at
    least once for the symbol; ``count`` is the absolute number
    of observations. ``first_seen_ts`` / ``last_seen_ts`` are
    timestamps in milliseconds (epoch ms). ``event_ids`` is a
    bounded list (max 8) so the audit payload stays JSON-friendly
    and replay-stable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: str
    observed: bool = False
    count: int = 0
    first_seen_ts: int = 0
    last_seen_ts: int = 0
    event_ids: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("stage")
    @classmethod
    def _check_stage(cls, value: str) -> str:
        text = str(value).strip()
        if text not in CAPTURE_PATH_STAGES:
            # Tolerate but normalise; a future PR may add a stage.
            return text or "unknown"
        return text

    def to_payload(self) -> dict[str, Any]:
        return {
            "stage": str(self.stage),
            "observed": bool(self.observed),
            "count": int(self.count),
            "first_seen_ts": int(self.first_seen_ts),
            "last_seen_ts": int(self.last_seen_ts),
            "event_ids": list(self.event_ids),
        }


# ---------------------------------------------------------------------------
# Models - Per-mover audit record
# ---------------------------------------------------------------------------
class MoverCaptureAuditRecord(BaseModel):
    """One audited top mover.

    Carries the per-mover :class:`CapturePathEvidence` map +
    descriptive ``audit_status`` + structured ``miss_reasons``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    rank: int = 0
    audit_status: str = CapturePathStatus.MISSED
    price_change_pct: float = 0.0
    quote_volume_usdt: float = 0.0
    last_price: float = 0.0
    in_eligible_universe: bool = True
    captured_stage_count: int = 0
    total_stage_count: int = 0
    capture_recall_score: float = 0.0  # 0.0 - 1.0 (descriptive)
    risk_rejected: bool = False
    has_completed_tail_label: bool = False
    has_strategy_validation_sample: bool = False
    first_seen_latency_seconds: float = 0.0
    miss_reasons: tuple[str, ...] = Field(default_factory=tuple)
    capture_path: tuple[CapturePathEvidence, ...] = Field(default_factory=tuple)
    notes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("symbol")
    @classmethod
    def _check_symbol(cls, value: str) -> str:
        return _normalise_symbol(value)

    @field_validator("audit_status")
    @classmethod
    def _check_status(cls, value: str) -> str:
        text = str(value).strip()
        if text not in CAPTURE_PATH_STATUSES:
            return CapturePathStatus.INSUFFICIENT_DATA
        return text

    @field_validator("miss_reasons")
    @classmethod
    def _check_miss_reasons(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        out: list[str] = []
        seen: set[str] = set()
        for reason in value or ():
            text = str(reason).strip()
            if not text:
                continue
            if text not in seen:
                seen.add(text)
                out.append(text)
        return tuple(out)

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": str(self.symbol),
            "rank": int(self.rank),
            "audit_status": str(self.audit_status),
            "price_change_pct": float(self.price_change_pct),
            "quote_volume_usdt": float(self.quote_volume_usdt),
            "last_price": float(self.last_price),
            "in_eligible_universe": bool(self.in_eligible_universe),
            "captured_stage_count": int(self.captured_stage_count),
            "total_stage_count": int(self.total_stage_count),
            "capture_recall_score": float(self.capture_recall_score),
            "risk_rejected": bool(self.risk_rejected),
            "has_completed_tail_label": bool(self.has_completed_tail_label),
            "has_strategy_validation_sample": bool(
                self.has_strategy_validation_sample
            ),
            "first_seen_latency_seconds": float(
                self.first_seen_latency_seconds
            ),
            "miss_reasons": list(self.miss_reasons),
            "capture_path": [s.to_payload() for s in self.capture_path],
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Models - Audit input
# ---------------------------------------------------------------------------
class MoverCaptureRecallAuditInput(BaseModel):
    """Input for :func:`build_mover_capture_recall_audit_report`.

    All fields are *snapshots* taken from existing surfaces. The
    audit module never makes a network call - upstream wiring
    (the runner / daily-report builder) is responsible for pulling
    the public data and providing it here.

    The audit module does not require every field to be populated.
    When a field is missing the corresponding capture-path stage
    is recorded as ``observed=False`` and the relevant miss reason
    is appended.

    Concretely:

      - ``top_movers`` - rows of :class:`TopMoverReference`. May be
        empty; the audit then yields an ``INSUFFICIENT_DATA``
        report.
      - ``known_universe`` - the set of symbols Phase 11C.1B
        bootstrapped from exchangeInfo. When the set is empty, the
        audit assumes every symbol is in the universe (degraded
        mode) and emits a warning.
      - ``not_usdt_perpetual_symbols`` - explicit deny list (e.g.
        delivery contracts) the runner has identified as
        non-USDT-perpetual. Optional.
      - ``symbol_limit_excluded_symbols`` - symbols the runner
        excluded because of the ``--symbol-limit`` runtime flag.
        Optional.
      - ``below_liquidity_threshold_symbols`` - symbols the runner
        excluded because their 24h quote volume was below the
        configured liquidity threshold. Optional.
      - ``insufficient_ws_data_symbols`` - symbols the runner
        flagged as having too few WS pushes during the window.
        Optional.
      - ``stale_data_symbols`` - symbols flagged ``stale``.
      - ``data_unreliable_symbols`` - symbols that tripped the
        Phase 4 ``DATA_UNRELIABLE`` event during the window.
      - ``candidate_pool_evicted_symbols`` - symbols whose
        candidate-pool entry was evicted before the chain finished.
      - ``risk_rejected_symbols`` - symbols that reached the Risk
        Engine and were rejected.
      - ``stage_observations`` - mapping from
        ``(symbol, stage)`` → :class:`CapturePathEvidence`. The
        audit builder reads this directly to populate per-mover
        ``capture_path`` evidence. May be empty.
      - ``window_start_ts`` / ``window_end_ts`` - inclusive
        window in epoch ms.
      - ``min_top_mover_count`` - minimum top mover rows to leave
        ``INSUFFICIENT_DATA`` (defaults to
        :data:`DEFAULT_MIN_TOP_MOVER_COUNT`).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    top_movers: tuple[TopMoverReference, ...] = Field(default_factory=tuple)
    known_universe: tuple[str, ...] = Field(default_factory=tuple)
    not_usdt_perpetual_symbols: tuple[str, ...] = Field(default_factory=tuple)
    symbol_limit_excluded_symbols: tuple[str, ...] = Field(
        default_factory=tuple
    )
    below_liquidity_threshold_symbols: tuple[str, ...] = Field(
        default_factory=tuple
    )
    insufficient_ws_data_symbols: tuple[str, ...] = Field(
        default_factory=tuple
    )
    stale_data_symbols: tuple[str, ...] = Field(default_factory=tuple)
    data_unreliable_symbols: tuple[str, ...] = Field(default_factory=tuple)
    candidate_pool_evicted_symbols: tuple[str, ...] = Field(
        default_factory=tuple
    )
    risk_rejected_symbols: tuple[str, ...] = Field(default_factory=tuple)
    stage_observations: dict[str, dict[str, CapturePathEvidence]] = Field(
        default_factory=dict
    )
    window_start_ts: int = 0
    window_end_ts: int = 0
    min_top_mover_count: int = DEFAULT_MIN_TOP_MOVER_COUNT
    report_id: str = ""
    audit_id: str = ""
    strategy_version: str = "phase_11c_1c_a.strategy.v1"
    scoring_version: str = "phase_11c_1c_a.scoring.v1"
    risk_config_version: str = "phase_11c_1c_a.risk_config.v1"
    state_machine_version: str = "phase_11c_1c_a.state_machine.v1"


# ---------------------------------------------------------------------------
# Models - Audit report
# ---------------------------------------------------------------------------
class MoverCaptureRecallAuditReport(BaseModel):
    """Top-level Phase 11C.1C-C-B-B-B-D audit report.

    Frozen + JSON-safe. Mirrors the cohort-pack pattern used by
    Phase 11C.1C-C-B-B-B-A / 11C.1C-C-B-B-B-B so the runtime can
    emit the report through ``MOVER_CAPTURE_RECALL_AUDIT_GENERATED``
    and the daily-report builder can render the section verbatim.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str = ""
    audit_id: str = ""
    evaluated_at: int = 0
    window_start: int = 0
    window_end: int = 0
    source_phase: str = MOVER_CAPTURE_RECALL_AUDIT_SOURCE_PHASE
    schema_version: str = MOVER_CAPTURE_RECALL_AUDIT_SCHEMA_VERSION
    status: str = MoverCaptureRecallAuditStatus.OK

    # Counts
    top_mover_count: int = 0
    captured_top_mover_count: int = 0
    partially_captured_top_mover_count: int = 0
    missed_top_mover_count: int = 0
    excluded_top_mover_count: int = 0
    insufficient_data_top_mover_count: int = 0

    # Rates (descriptive only)
    capture_recall_rate: float = 0.0
    anomaly_detected_rate: float = 0.0
    label_tracking_rate: float = 0.0
    tail_label_assigned_rate: float = 0.0
    strategy_validation_sample_rate: float = 0.0

    # Mover counters
    risk_rejected_mover_count: int = 0
    not_in_universe_count: int = 0
    capacity_evicted_count: int = 0
    data_unreliable_count: int = 0
    insufficient_ws_data_count: int = 0
    stale_data_count: int = 0
    below_liquidity_threshold_count: int = 0
    symbol_limit_excluded_count: int = 0
    not_usdt_perpetual_count: int = 0

    # Latency (descriptive)
    median_first_seen_latency_seconds: float = 0.0

    # Records
    records: tuple[MoverCaptureAuditRecord, ...] = Field(default_factory=tuple)
    miss_reason_summary: dict[str, int] = Field(default_factory=dict)
    coverage_warnings: tuple[str, ...] = Field(default_factory=tuple)
    insufficient_coverage_reasons: tuple[str, ...] = Field(
        default_factory=tuple
    )
    warnings: tuple[str, ...] = Field(default_factory=tuple)

    # Identity / provenance
    strategy_version: str = "phase_11c_1c_a.strategy.v1"
    scoring_version: str = "phase_11c_1c_a.scoring.v1"
    risk_config_version: str = "phase_11c_1c_a.risk_config.v1"
    state_machine_version: str = "phase_11c_1c_a.state_machine.v1"

    @field_validator("status")
    @classmethod
    def _check_status(cls, value: str) -> str:
        text = str(value).strip()
        if text not in MOVER_CAPTURE_RECALL_AUDIT_STATUSES:
            return MoverCaptureRecallAuditStatus.OK
        return text

    def to_payload(self) -> dict[str, Any]:
        return {
            "report_id": str(self.report_id),
            "audit_id": str(self.audit_id),
            "evaluated_at": int(self.evaluated_at),
            "window_start": int(self.window_start),
            "window_end": int(self.window_end),
            "source_phase": str(self.source_phase),
            "schema_version": str(self.schema_version),
            "status": str(self.status),
            "top_mover_count": int(self.top_mover_count),
            "captured_top_mover_count": int(self.captured_top_mover_count),
            "partially_captured_top_mover_count": int(
                self.partially_captured_top_mover_count
            ),
            "missed_top_mover_count": int(self.missed_top_mover_count),
            "excluded_top_mover_count": int(self.excluded_top_mover_count),
            "insufficient_data_top_mover_count": int(
                self.insufficient_data_top_mover_count
            ),
            "capture_recall_rate": float(self.capture_recall_rate),
            "anomaly_detected_rate": float(self.anomaly_detected_rate),
            "label_tracking_rate": float(self.label_tracking_rate),
            "tail_label_assigned_rate": float(
                self.tail_label_assigned_rate
            ),
            "strategy_validation_sample_rate": float(
                self.strategy_validation_sample_rate
            ),
            "risk_rejected_mover_count": int(self.risk_rejected_mover_count),
            "not_in_universe_count": int(self.not_in_universe_count),
            "capacity_evicted_count": int(self.capacity_evicted_count),
            "data_unreliable_count": int(self.data_unreliable_count),
            "insufficient_ws_data_count": int(
                self.insufficient_ws_data_count
            ),
            "stale_data_count": int(self.stale_data_count),
            "below_liquidity_threshold_count": int(
                self.below_liquidity_threshold_count
            ),
            "symbol_limit_excluded_count": int(
                self.symbol_limit_excluded_count
            ),
            "not_usdt_perpetual_count": int(self.not_usdt_perpetual_count),
            "median_first_seen_latency_seconds": float(
                self.median_first_seen_latency_seconds
            ),
            "records": [r.to_payload() for r in self.records],
            "miss_reason_summary": {
                k: int(v) for k, v in sorted(self.miss_reason_summary.items())
            },
            "coverage_warnings": list(self.coverage_warnings),
            "insufficient_coverage_reasons": list(
                self.insufficient_coverage_reasons
            ),
            "warnings": list(self.warnings),
            "strategy_version": str(self.strategy_version),
            "scoring_version": str(self.scoring_version),
            "risk_config_version": str(self.risk_config_version),
            "state_machine_version": str(self.state_machine_version),
        }


# ---------------------------------------------------------------------------
# Pure builders
# ---------------------------------------------------------------------------
def build_top_mover_reference_set(
    *,
    ticker_rows: Sequence[Mapping[str, Any]] | None = None,
    known_universe: Sequence[str] | None = None,
    not_usdt_perpetual_symbols: Sequence[str] | None = None,
    min_price_change_pct: float = DEFAULT_MIN_PRICE_CHANGE_PCT,
    min_quote_volume_usdt: float = DEFAULT_MIN_QUOTE_VOLUME_USDT,
    top_mover_limit: int = DEFAULT_TOP_MOVER_LIMIT,
    now_ms_value: int = 0,
) -> tuple[TopMoverReference, ...]:
    """Build the top-mover reference set from a list of public 24h
    ticker rows.

    The function is deterministic and pure - it does not call any
    network service. ``ticker_rows`` is expected to be the public
    Binance 24h ticker payload (or any equivalent shape). Each row
    must expose at least:

      - ``symbol`` - the trading symbol;
      - ``priceChangePercent`` - 24h percent change as a number
        (Binance returns a string; the helper coerces);
      - ``quoteVolume`` - 24h quote volume in USDT;
      - ``lastPrice`` (optional).

    Behaviour:

      - rows whose ``priceChangePercent`` is below the configured
        threshold are dropped;
      - rows whose ``quoteVolume`` is below the configured
        liquidity threshold are kept but flagged
        ``in_eligible_universe=False`` (so a human reviewer can
        audit the exclusion);
      - rows whose ``symbol`` is not in ``known_universe`` are
        kept and flagged ``in_eligible_universe=False`` with
        ``not_in_futures_universe_reason`` populated;
      - rows whose ``symbol`` is in ``not_usdt_perpetual_symbols``
        are also flagged ``in_eligible_universe=False``;
      - rows are sorted by absolute ``priceChangePercent`` descending
        (largest mover first);
      - the top ``top_mover_limit`` rows are returned.
    """
    if not ticker_rows:
        return ()

    universe_set = {
        _normalise_symbol(s) for s in (known_universe or ()) if s
    }
    deny_perp_set = {
        _normalise_symbol(s) for s in (not_usdt_perpetual_symbols or ()) if s
    }

    refs: list[TopMoverReference] = []
    for row in ticker_rows:
        if not isinstance(row, Mapping):
            continue
        symbol = _normalise_symbol(row.get("symbol"))
        if not symbol:
            continue

        # Binance returns the ``priceChangePercent`` as a string
        # like ``"15.2"`` (=== +15.2%). We accept both forms and
        # convert to decimal (e.g. 0.152).
        raw_pct = _safe_float(
            row.get("priceChangePercent", row.get("price_change_pct", 0.0)),
            0.0,
        )
        # If the caller already supplied a decimal (|value| <= 1.0
        # AND non-zero), keep it. Otherwise treat the value as a
        # percent and divide by 100.
        if abs(raw_pct) > 1.0 or row.get("priceChangePercent") is not None:
            price_change_pct = raw_pct / 100.0
        else:
            price_change_pct = raw_pct
        quote_volume = _safe_float(
            row.get("quoteVolume", row.get("quote_volume_usdt", 0.0)), 0.0
        )
        last_price = _safe_float(
            row.get("lastPrice", row.get("last_price", 0.0)), 0.0
        )

        if abs(price_change_pct) < float(min_price_change_pct):
            continue

        in_universe = True
        not_in_reason = ""
        if universe_set and symbol not in universe_set:
            in_universe = False
            not_in_reason = MissReason.SYMBOL_NOT_IN_EXCHANGE_INFO
        elif symbol in deny_perp_set:
            in_universe = False
            not_in_reason = MissReason.NOT_USDT_PERPETUAL
        elif quote_volume < float(min_quote_volume_usdt):
            in_universe = False
            not_in_reason = MissReason.BELOW_LIQUIDITY_THRESHOLD

        refs.append(
            TopMoverReference(
                symbol=symbol,
                rank=0,  # filled in once the list is sorted
                price_change_pct=price_change_pct,
                quote_volume_usdt=quote_volume,
                last_price=last_price,
                first_seen_ts=int(now_ms_value),
                in_eligible_universe=in_universe,
                not_in_futures_universe_reason=not_in_reason,
            )
        )

    # Sort by absolute price change descending; tie-break by quote
    # volume descending so the result is deterministic.
    refs.sort(
        key=lambda r: (-abs(r.price_change_pct), -r.quote_volume_usdt, r.symbol)
    )

    limit = max(0, int(top_mover_limit))
    if limit > 0:
        refs = refs[:limit]

    # Re-rank.
    ranked: list[TopMoverReference] = []
    for idx, ref in enumerate(refs, start=1):
        ranked.append(
            TopMoverReference(
                symbol=ref.symbol,
                rank=idx,
                price_change_pct=ref.price_change_pct,
                quote_volume_usdt=ref.quote_volume_usdt,
                last_price=ref.last_price,
                first_seen_ts=ref.first_seen_ts,
                in_eligible_universe=ref.in_eligible_universe,
                not_in_futures_universe_reason=ref.not_in_futures_universe_reason,
                extra=dict(ref.extra),
            )
        )
    return tuple(ranked)


def _stage_observed(
    stage_evidence: Mapping[str, CapturePathEvidence] | None, stage: str
) -> bool:
    if not stage_evidence:
        return False
    ev = stage_evidence.get(stage)
    if ev is None:
        return False
    return bool(ev.observed) and int(ev.count) > 0


def audit_mover_capture_path(
    mover: TopMoverReference,
    *,
    audit_input: MoverCaptureRecallAuditInput,
) -> MoverCaptureAuditRecord:
    """Audit one top mover against the chain.

    Pure function. Reads ``audit_input`` only; never raises on
    missing data.
    """
    symbol = _normalise_symbol(mover.symbol)
    stage_evidence_by_symbol = audit_input.stage_observations or {}
    per_symbol_stage_map: Mapping[str, CapturePathEvidence] = (
        stage_evidence_by_symbol.get(symbol) or {}
    )

    # Build the per-stage evidence list in the canonical order.
    capture_path: list[CapturePathEvidence] = []
    captured_stage_count = 0
    first_seen_in_chain_ts: int | None = None

    for stage in CAPTURE_PATH_STAGES:
        ev = per_symbol_stage_map.get(stage)
        if ev is None:
            ev = CapturePathEvidence(stage=stage)
        else:
            # Defensive: re-build to enforce the validator.
            ev = CapturePathEvidence(
                stage=str(ev.stage),
                observed=bool(ev.observed),
                count=int(ev.count),
                first_seen_ts=int(ev.first_seen_ts),
                last_seen_ts=int(ev.last_seen_ts),
                event_ids=tuple(ev.event_ids),
            )
        capture_path.append(ev)
        if ev.observed and ev.count > 0:
            captured_stage_count += 1
            if (
                ev.first_seen_ts > 0
                and (
                    first_seen_in_chain_ts is None
                    or ev.first_seen_ts < first_seen_in_chain_ts
                )
            ):
                first_seen_in_chain_ts = int(ev.first_seen_ts)

    total_stage_count = len(CAPTURE_PATH_STAGES)
    capture_recall_score = _safe_ratio(
        captured_stage_count, total_stage_count
    )

    risk_rejected = (
        symbol in {_normalise_symbol(s) for s in audit_input.risk_rejected_symbols}
        or _stage_observed(per_symbol_stage_map, "RISK_REJECTED")
    )
    has_completed_tail_label = _stage_observed(
        per_symbol_stage_map, "TAIL_LABEL_ASSIGNED"
    ) or _stage_observed(per_symbol_stage_map, "LABEL_WINDOW_COMPLETED")
    has_strategy_validation_sample = _stage_observed(
        per_symbol_stage_map, "STRATEGY_VALIDATION_SAMPLE_CREATED"
    )

    first_seen_latency_seconds = 0.0
    if (
        first_seen_in_chain_ts is not None
        and mover.first_seen_ts > 0
        and first_seen_in_chain_ts >= mover.first_seen_ts
    ):
        first_seen_latency_seconds = max(
            0.0,
            (first_seen_in_chain_ts - mover.first_seen_ts) / 1000.0,
        )

    # Decide audit_status + miss_reasons.
    miss_reasons = classify_miss_reason(
        mover=mover,
        stage_evidence=per_symbol_stage_map,
        audit_input=audit_input,
        risk_rejected=risk_rejected,
        has_completed_tail_label=has_completed_tail_label,
    )

    if not mover.in_eligible_universe:
        audit_status = CapturePathStatus.EXCLUDED
    elif _stage_evidence_empty(per_symbol_stage_map):
        # No chain observations whatsoever. If the symbol is
        # eligible but the chain saw nothing, that is a coverage
        # MISS (the discovery layer did not detect this mover).
        audit_status = CapturePathStatus.MISSED
    else:
        # The chain saw at least one stage. Decide between
        # CAPTURED / PARTIALLY_CAPTURED / MISSED based on which
        # stages fired.
        required_seen = all(
            _stage_observed(per_symbol_stage_map, s)
            for s in CAPTURED_REQUIRED_STAGES
        )
        terminal_or_strong_seen = any(
            _stage_observed(per_symbol_stage_map, s)
            for s in (
                *CAPTURED_TERMINAL_STAGES,
                *FULL_CAPTURE_STRONG_STAGES,
            )
        )
        market_snapshot_seen = _stage_observed(
            per_symbol_stage_map, "MARKET_SNAPSHOT"
        ) or _stage_observed(per_symbol_stage_map, "CANDIDATE_POOL")

        if required_seen and terminal_or_strong_seen:
            audit_status = CapturePathStatus.CAPTURED
        elif market_snapshot_seen:
            audit_status = CapturePathStatus.PARTIALLY_CAPTURED
        else:
            audit_status = CapturePathStatus.MISSED

    notes: tuple[str, ...] = ()
    if (
        audit_status == CapturePathStatus.CAPTURED
        and risk_rejected
    ):
        notes = ("captured_then_risk_rejected",)
    elif (
        audit_status == CapturePathStatus.PARTIALLY_CAPTURED
        and not has_completed_tail_label
        and MissReason.NO_COMPLETED_TAIL_LABEL_YET in miss_reasons
    ):
        notes = ("label_tracking_in_flight",)

    return MoverCaptureAuditRecord(
        symbol=symbol,
        rank=int(mover.rank),
        audit_status=audit_status,
        price_change_pct=float(mover.price_change_pct),
        quote_volume_usdt=float(mover.quote_volume_usdt),
        last_price=float(mover.last_price),
        in_eligible_universe=bool(mover.in_eligible_universe),
        captured_stage_count=int(captured_stage_count),
        total_stage_count=int(total_stage_count),
        capture_recall_score=float(capture_recall_score),
        risk_rejected=bool(risk_rejected),
        has_completed_tail_label=bool(has_completed_tail_label),
        has_strategy_validation_sample=bool(has_strategy_validation_sample),
        first_seen_latency_seconds=float(first_seen_latency_seconds),
        miss_reasons=tuple(miss_reasons),
        capture_path=tuple(capture_path),
        notes=notes,
    )


def _stage_evidence_empty(
    stage_evidence: Mapping[str, CapturePathEvidence] | None,
) -> bool:
    if not stage_evidence:
        return True
    return not any(
        ev is not None and bool(ev.observed) and int(ev.count) > 0
        for ev in stage_evidence.values()
    )


def classify_miss_reason(
    *,
    mover: TopMoverReference,
    stage_evidence: Mapping[str, CapturePathEvidence] | None,
    audit_input: MoverCaptureRecallAuditInput,
    risk_rejected: bool,
    has_completed_tail_label: bool,
) -> tuple[str, ...]:
    """Classify the structured miss reasons for one mover.

    Pure function. Returns an ordered tuple of miss-reason strings
    drawn from :class:`MissReason`. Empty tuple for a fully
    captured mover.

    The same mover can carry multiple reasons - e.g. a symbol that
    is below the liquidity threshold AND not in exchangeInfo.
    """
    reasons: list[str] = []
    seen: set[str] = set()

    def _add(reason: str) -> None:
        if reason and reason not in seen:
            seen.add(reason)
            reasons.append(reason)

    symbol = _normalise_symbol(mover.symbol)

    # Eligibility-driven reasons take precedence.
    if not mover.in_eligible_universe:
        if (
            mover.not_in_futures_universe_reason
            == MissReason.SYMBOL_NOT_IN_EXCHANGE_INFO
        ):
            _add(MissReason.SYMBOL_NOT_IN_EXCHANGE_INFO)
            _add(MissReason.NOT_IN_FUTURES_UNIVERSE)
        elif (
            mover.not_in_futures_universe_reason
            == MissReason.NOT_USDT_PERPETUAL
        ):
            _add(MissReason.NOT_USDT_PERPETUAL)
            _add(MissReason.NOT_IN_FUTURES_UNIVERSE)
        elif (
            mover.not_in_futures_universe_reason
            == MissReason.BELOW_LIQUIDITY_THRESHOLD
        ):
            _add(MissReason.BELOW_LIQUIDITY_THRESHOLD)
        else:
            _add(MissReason.NOT_IN_FUTURES_UNIVERSE)
        # Eligibility reasons are usually enough by themselves; we
        # still cross-check the runner-supplied deny lists below.

    # Cross-check the runner-supplied deny lists.
    if symbol in {_normalise_symbol(s) for s in audit_input.not_usdt_perpetual_symbols}:
        _add(MissReason.NOT_USDT_PERPETUAL)
    if symbol in {_normalise_symbol(s) for s in audit_input.below_liquidity_threshold_symbols}:
        _add(MissReason.BELOW_LIQUIDITY_THRESHOLD)
    if symbol in {_normalise_symbol(s) for s in audit_input.symbol_limit_excluded_symbols}:
        _add(MissReason.SYMBOL_LIMIT_EXCLUDED)
    if symbol in {_normalise_symbol(s) for s in audit_input.candidate_pool_evicted_symbols}:
        _add(MissReason.CANDIDATE_POOL_EVICTED)
    if symbol in {_normalise_symbol(s) for s in audit_input.insufficient_ws_data_symbols}:
        _add(MissReason.INSUFFICIENT_WS_DATA)
    if symbol in {_normalise_symbol(s) for s in audit_input.stale_data_symbols}:
        _add(MissReason.STALE_DATA)
    if symbol in {_normalise_symbol(s) for s in audit_input.data_unreliable_symbols}:
        _add(MissReason.DATA_UNRELIABLE)
    if (
        stage_evidence is not None
        and _stage_observed(stage_evidence, "DATA_UNRELIABLE")
    ):
        _add(MissReason.DATA_UNRELIABLE)
    if risk_rejected:
        _add(MissReason.RISK_REJECTED)

    # Stage-based reasons - only meaningful when the mover is in
    # the eligible universe (otherwise the universe reasons above
    # already explain the gap).
    if mover.in_eligible_universe:
        market_snapshot_seen = _stage_observed(
            stage_evidence, "MARKET_SNAPSHOT"
        ) or _stage_observed(stage_evidence, "CANDIDATE_POOL")
        anomaly_seen = _stage_observed(
            stage_evidence, "ANOMALY_DETECTED"
        ) or _stage_observed(stage_evidence, "PRE_ANOMALY_DETECTED")

        if not market_snapshot_seen and stage_evidence:
            # The chain reported on this symbol via some other
            # stage but never via MARKET_SNAPSHOT - usually a
            # WS-data gap.
            _add(MissReason.INSUFFICIENT_WS_DATA)
        if (
            market_snapshot_seen
            and not anomaly_seen
            and not risk_rejected
            and not has_completed_tail_label
        ):
            _add(MissReason.NO_ANOMALY_THRESHOLD_CROSS)
        if (
            anomaly_seen
            and not has_completed_tail_label
            and not risk_rejected
        ):
            _add(MissReason.NO_COMPLETED_TAIL_LABEL_YET)

    if not reasons and not has_completed_tail_label and mover.in_eligible_universe:
        # Fallback: we have no signal either way.
        _add(MissReason.UNKNOWN)

    return tuple(reasons)


def _median_or_zero(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    try:
        return float(statistics.median(values))
    except statistics.StatisticsError:
        return 0.0


def build_mover_capture_recall_audit_report(
    audit_input: MoverCaptureRecallAuditInput,
    *,
    evaluated_at_ms: int = 0,
) -> MoverCaptureRecallAuditReport:
    """Assemble a :class:`MoverCaptureRecallAuditReport` from the
    given input.

    Pure function. Never raises on missing data; an empty
    ``top_movers`` produces an ``INSUFFICIENT_DATA`` report with
    explicit ``insufficient_coverage_reasons``.
    """
    top_movers = tuple(audit_input.top_movers or ())
    min_required = max(
        0, int(audit_input.min_top_mover_count or DEFAULT_MIN_TOP_MOVER_COUNT)
    )

    insufficient_reasons: list[str] = []
    warnings: list[str] = []

    # Insufficient-data short-circuit.
    if len(top_movers) < min_required or not top_movers:
        insufficient_reasons.append(
            f"top_mover_count={len(top_movers)} below min={min_required}"
        )
        if not audit_input.known_universe:
            warnings.append(
                "known_universe is empty; eligibility classification is "
                "DEGRADED - all symbols treated as in-universe"
            )
        return MoverCaptureRecallAuditReport(
            report_id=str(audit_input.report_id),
            audit_id=str(audit_input.audit_id),
            evaluated_at=int(evaluated_at_ms),
            window_start=int(audit_input.window_start_ts),
            window_end=int(audit_input.window_end_ts),
            status=MoverCaptureRecallAuditStatus.INSUFFICIENT_DATA,
            top_mover_count=int(len(top_movers)),
            insufficient_coverage_reasons=tuple(insufficient_reasons),
            warnings=tuple(warnings),
            strategy_version=str(audit_input.strategy_version),
            scoring_version=str(audit_input.scoring_version),
            risk_config_version=str(audit_input.risk_config_version),
            state_machine_version=str(audit_input.state_machine_version),
        )

    if not audit_input.known_universe:
        warnings.append(
            "known_universe is empty; eligibility classification is "
            "DEGRADED - all symbols treated as in-universe"
        )

    records: list[MoverCaptureAuditRecord] = []
    miss_summary: dict[str, int] = {}
    coverage_warnings: list[str] = []
    latencies: list[float] = []

    captured = 0
    partially = 0
    missed = 0
    excluded = 0
    insufficient = 0

    risk_rejected_count = 0
    not_in_universe_count = 0
    capacity_evicted_count = 0
    data_unreliable_count = 0
    insufficient_ws_data_count = 0
    stale_data_count = 0
    below_liq_count = 0
    symbol_limit_count = 0
    not_usdt_count = 0

    anomaly_seen_count = 0
    label_tracking_seen_count = 0
    tail_label_seen_count = 0
    strategy_sample_seen_count = 0

    for mover in top_movers:
        record = audit_mover_capture_path(mover, audit_input=audit_input)
        records.append(record)

        if record.audit_status == CapturePathStatus.CAPTURED:
            captured += 1
        elif record.audit_status == CapturePathStatus.PARTIALLY_CAPTURED:
            partially += 1
        elif record.audit_status == CapturePathStatus.MISSED:
            missed += 1
        elif record.audit_status == CapturePathStatus.EXCLUDED:
            excluded += 1
        elif record.audit_status == CapturePathStatus.INSUFFICIENT_DATA:
            insufficient += 1

        for reason in record.miss_reasons:
            miss_summary[reason] = miss_summary.get(reason, 0) + 1
            if reason == MissReason.RISK_REJECTED:
                risk_rejected_count += 1
            elif reason in (
                MissReason.NOT_IN_FUTURES_UNIVERSE,
                MissReason.SYMBOL_NOT_IN_EXCHANGE_INFO,
            ):
                not_in_universe_count += 1
            elif reason == MissReason.CANDIDATE_POOL_EVICTED:
                capacity_evicted_count += 1
            elif reason == MissReason.DATA_UNRELIABLE:
                data_unreliable_count += 1
            elif reason == MissReason.INSUFFICIENT_WS_DATA:
                insufficient_ws_data_count += 1
            elif reason == MissReason.STALE_DATA:
                stale_data_count += 1
            elif reason == MissReason.BELOW_LIQUIDITY_THRESHOLD:
                below_liq_count += 1
            elif reason == MissReason.SYMBOL_LIMIT_EXCLUDED:
                symbol_limit_count += 1
            elif reason == MissReason.NOT_USDT_PERPETUAL:
                not_usdt_count += 1

        if record.first_seen_latency_seconds > 0:
            latencies.append(float(record.first_seen_latency_seconds))

        # Per-stage roll-ups (only count over eligible movers so the
        # rates describe the chain's behaviour on the in-scope set).
        per_symbol_stage_map = (
            audit_input.stage_observations or {}
        ).get(record.symbol) or {}
        if record.in_eligible_universe:
            if (
                _stage_observed(per_symbol_stage_map, "ANOMALY_DETECTED")
                or _stage_observed(
                    per_symbol_stage_map, "PRE_ANOMALY_DETECTED"
                )
            ):
                anomaly_seen_count += 1
            if _stage_observed(
                per_symbol_stage_map, "LABEL_TRACKING_STARTED"
            ):
                label_tracking_seen_count += 1
            if _stage_observed(
                per_symbol_stage_map, "TAIL_LABEL_ASSIGNED"
            ):
                tail_label_seen_count += 1
            if _stage_observed(
                per_symbol_stage_map, "STRATEGY_VALIDATION_SAMPLE_CREATED"
            ):
                strategy_sample_seen_count += 1

        # Coverage warning: the mover is eligible AND clearly a
        # right-tail signal AND was missed (or only partially
        # captured) for a system-correctable reason. Captured-then-
        # rejected is NOT a coverage warning per the brief.
        if (
            record.in_eligible_universe
            and record.audit_status
            in (
                CapturePathStatus.MISSED,
                CapturePathStatus.PARTIALLY_CAPTURED,
            )
            and record.price_change_pct >= float(DEFAULT_MIN_PRICE_CHANGE_PCT)
            and not record.risk_rejected
        ):
            coverage_warnings.append(
                f"coverage_warning symbol={record.symbol} "
                f"status={record.audit_status} "
                f"price_change_pct={record.price_change_pct:.4f} "
                f"miss_reasons={','.join(record.miss_reasons) or 'unknown'}"
            )

    eligible_count = sum(1 for r in records if r.in_eligible_universe)
    capture_recall_rate = _safe_ratio(captured, eligible_count) if eligible_count else 0.0
    anomaly_detected_rate = _safe_ratio(
        anomaly_seen_count, eligible_count
    ) if eligible_count else 0.0
    label_tracking_rate = _safe_ratio(
        label_tracking_seen_count, eligible_count
    ) if eligible_count else 0.0
    tail_label_assigned_rate = _safe_ratio(
        tail_label_seen_count, eligible_count
    ) if eligible_count else 0.0
    strategy_validation_sample_rate = _safe_ratio(
        strategy_sample_seen_count, eligible_count
    ) if eligible_count else 0.0

    median_latency_seconds = _median_or_zero(latencies)

    status = MoverCaptureRecallAuditStatus.OK
    if warnings or coverage_warnings:
        status = MoverCaptureRecallAuditStatus.DEGRADED

    return MoverCaptureRecallAuditReport(
        report_id=str(audit_input.report_id),
        audit_id=str(audit_input.audit_id),
        evaluated_at=int(evaluated_at_ms),
        window_start=int(audit_input.window_start_ts),
        window_end=int(audit_input.window_end_ts),
        status=status,
        top_mover_count=int(len(top_movers)),
        captured_top_mover_count=int(captured),
        partially_captured_top_mover_count=int(partially),
        missed_top_mover_count=int(missed),
        excluded_top_mover_count=int(excluded),
        insufficient_data_top_mover_count=int(insufficient),
        capture_recall_rate=float(capture_recall_rate),
        anomaly_detected_rate=float(anomaly_detected_rate),
        label_tracking_rate=float(label_tracking_rate),
        tail_label_assigned_rate=float(tail_label_assigned_rate),
        strategy_validation_sample_rate=float(strategy_validation_sample_rate),
        risk_rejected_mover_count=int(risk_rejected_count),
        not_in_universe_count=int(not_in_universe_count),
        capacity_evicted_count=int(capacity_evicted_count),
        data_unreliable_count=int(data_unreliable_count),
        insufficient_ws_data_count=int(insufficient_ws_data_count),
        stale_data_count=int(stale_data_count),
        below_liquidity_threshold_count=int(below_liq_count),
        symbol_limit_excluded_count=int(symbol_limit_count),
        not_usdt_perpetual_count=int(not_usdt_count),
        median_first_seen_latency_seconds=float(median_latency_seconds),
        records=tuple(records),
        miss_reason_summary=dict(miss_summary),
        coverage_warnings=tuple(coverage_warnings),
        insufficient_coverage_reasons=tuple(insufficient_reasons),
        warnings=tuple(warnings),
        strategy_version=str(audit_input.strategy_version),
        scoring_version=str(audit_input.scoring_version),
        risk_config_version=str(audit_input.risk_config_version),
        state_machine_version=str(audit_input.state_machine_version),
    )


# ---------------------------------------------------------------------------
# Export / Replay (round-trip)
# ---------------------------------------------------------------------------
def export_mover_capture_recall_audit_payload(
    report: MoverCaptureRecallAuditReport,
) -> dict[str, Any]:
    """Return a JSON-safe dict for the audit report.

    Pure function; does not write to disk. The runner / daily-
    report builder is responsible for serialising the dict to
    bytes.
    """
    return report.to_payload()


def _load_capture_path(
    payload_rows: Iterable[Mapping[str, Any]] | None,
) -> tuple[CapturePathEvidence, ...]:
    out: list[CapturePathEvidence] = []
    for row in payload_rows or ():
        if not isinstance(row, Mapping):
            continue
        out.append(
            CapturePathEvidence(
                stage=str(row.get("stage") or "unknown"),
                observed=bool(row.get("observed") or False),
                count=_safe_int(row.get("count") or 0),
                first_seen_ts=_safe_int(row.get("first_seen_ts") or 0),
                last_seen_ts=_safe_int(row.get("last_seen_ts") or 0),
                event_ids=tuple(
                    str(e) for e in (row.get("event_ids") or ())
                ),
            )
        )
    return tuple(out)


def _load_record(payload: Mapping[str, Any]) -> MoverCaptureAuditRecord:
    return MoverCaptureAuditRecord(
        symbol=str(payload.get("symbol") or ""),
        rank=_safe_int(payload.get("rank") or 0),
        audit_status=str(
            payload.get("audit_status") or CapturePathStatus.INSUFFICIENT_DATA
        ),
        price_change_pct=_safe_float(payload.get("price_change_pct") or 0.0),
        quote_volume_usdt=_safe_float(payload.get("quote_volume_usdt") or 0.0),
        last_price=_safe_float(payload.get("last_price") or 0.0),
        in_eligible_universe=bool(
            payload.get("in_eligible_universe", True)
        ),
        captured_stage_count=_safe_int(
            payload.get("captured_stage_count") or 0
        ),
        total_stage_count=_safe_int(payload.get("total_stage_count") or 0),
        capture_recall_score=_safe_float(
            payload.get("capture_recall_score") or 0.0
        ),
        risk_rejected=bool(payload.get("risk_rejected") or False),
        has_completed_tail_label=bool(
            payload.get("has_completed_tail_label") or False
        ),
        has_strategy_validation_sample=bool(
            payload.get("has_strategy_validation_sample") or False
        ),
        first_seen_latency_seconds=_safe_float(
            payload.get("first_seen_latency_seconds") or 0.0
        ),
        miss_reasons=tuple(
            str(r) for r in (payload.get("miss_reasons") or ())
        ),
        capture_path=_load_capture_path(payload.get("capture_path")),
        notes=tuple(str(n) for n in (payload.get("notes") or ())),
    )


def load_mover_capture_recall_audit_payload(
    payload: Mapping[str, Any],
) -> MoverCaptureRecallAuditReport:
    """Reconstruct a :class:`MoverCaptureRecallAuditReport` from a
    payload produced by
    :func:`export_mover_capture_recall_audit_payload`.

    Tolerates payloads from old schema_versions: missing optional
    fields default to v0 defaults so a future PR can extend the
    contract without breaking replay.
    """
    if not isinstance(payload, Mapping):
        raise TypeError(
            "load_mover_capture_recall_audit_payload requires a Mapping; "
            f"got {type(payload).__name__}"
        )

    records: list[MoverCaptureAuditRecord] = []
    for row in payload.get("records") or ():
        if isinstance(row, Mapping):
            records.append(_load_record(row))

    miss_summary_payload = payload.get("miss_reason_summary") or {}
    miss_summary: dict[str, int] = {}
    if isinstance(miss_summary_payload, Mapping):
        for k, v in miss_summary_payload.items():
            miss_summary[str(k)] = _safe_int(v, 0)

    return MoverCaptureRecallAuditReport(
        report_id=str(payload.get("report_id") or ""),
        audit_id=str(payload.get("audit_id") or ""),
        evaluated_at=_safe_int(payload.get("evaluated_at") or 0),
        window_start=_safe_int(payload.get("window_start") or 0),
        window_end=_safe_int(payload.get("window_end") or 0),
        source_phase=str(
            payload.get("source_phase")
            or MOVER_CAPTURE_RECALL_AUDIT_SOURCE_PHASE
        ),
        schema_version=str(
            payload.get("schema_version")
            or MOVER_CAPTURE_RECALL_AUDIT_SCHEMA_VERSION
        ),
        status=str(
            payload.get("status") or MoverCaptureRecallAuditStatus.OK
        ),
        top_mover_count=_safe_int(payload.get("top_mover_count") or 0),
        captured_top_mover_count=_safe_int(
            payload.get("captured_top_mover_count") or 0
        ),
        partially_captured_top_mover_count=_safe_int(
            payload.get("partially_captured_top_mover_count") or 0
        ),
        missed_top_mover_count=_safe_int(
            payload.get("missed_top_mover_count") or 0
        ),
        excluded_top_mover_count=_safe_int(
            payload.get("excluded_top_mover_count") or 0
        ),
        insufficient_data_top_mover_count=_safe_int(
            payload.get("insufficient_data_top_mover_count") or 0
        ),
        capture_recall_rate=_safe_float(
            payload.get("capture_recall_rate") or 0.0
        ),
        anomaly_detected_rate=_safe_float(
            payload.get("anomaly_detected_rate") or 0.0
        ),
        label_tracking_rate=_safe_float(
            payload.get("label_tracking_rate") or 0.0
        ),
        tail_label_assigned_rate=_safe_float(
            payload.get("tail_label_assigned_rate") or 0.0
        ),
        strategy_validation_sample_rate=_safe_float(
            payload.get("strategy_validation_sample_rate") or 0.0
        ),
        risk_rejected_mover_count=_safe_int(
            payload.get("risk_rejected_mover_count") or 0
        ),
        not_in_universe_count=_safe_int(
            payload.get("not_in_universe_count") or 0
        ),
        capacity_evicted_count=_safe_int(
            payload.get("capacity_evicted_count") or 0
        ),
        data_unreliable_count=_safe_int(
            payload.get("data_unreliable_count") or 0
        ),
        insufficient_ws_data_count=_safe_int(
            payload.get("insufficient_ws_data_count") or 0
        ),
        stale_data_count=_safe_int(payload.get("stale_data_count") or 0),
        below_liquidity_threshold_count=_safe_int(
            payload.get("below_liquidity_threshold_count") or 0
        ),
        symbol_limit_excluded_count=_safe_int(
            payload.get("symbol_limit_excluded_count") or 0
        ),
        not_usdt_perpetual_count=_safe_int(
            payload.get("not_usdt_perpetual_count") or 0
        ),
        median_first_seen_latency_seconds=_safe_float(
            payload.get("median_first_seen_latency_seconds") or 0.0
        ),
        records=tuple(records),
        miss_reason_summary=miss_summary,
        coverage_warnings=tuple(
            str(w) for w in (payload.get("coverage_warnings") or ())
        ),
        insufficient_coverage_reasons=tuple(
            str(r)
            for r in (payload.get("insufficient_coverage_reasons") or ())
        ),
        warnings=tuple(str(w) for w in (payload.get("warnings") or ())),
        strategy_version=str(
            payload.get("strategy_version") or "phase_11c_1c_a.strategy.v1"
        ),
        scoring_version=str(
            payload.get("scoring_version") or "phase_11c_1c_a.scoring.v1"
        ),
        risk_config_version=str(
            payload.get("risk_config_version")
            or "phase_11c_1c_a.risk_config.v1"
        ),
        state_machine_version=str(
            payload.get("state_machine_version")
            or "phase_11c_1c_a.state_machine.v1"
        ),
    )


# ---------------------------------------------------------------------------
# Runtime orchestrator
# ---------------------------------------------------------------------------
class MoverCaptureRecallAuditRuntime:
    """Thin runtime helper that wires the audit into the
    :class:`EventRepository` and produces the daily-report
    metrics payload.

    The runtime is **paper / report / evidence only**:

      - it does not subscribe to any private API;
      - it does not modify the Risk Engine, the Execution FSM,
        ``symbol_limit``, candidate-pool capacity, anomaly
        thresholds, Regime weights, or any other runtime knob;
      - the events it emits
        (``MOVER_CAPTURE_PATH_AUDITED`` /
        ``MOVER_CAPTURE_RECALL_AUDIT_GENERATED``) are descriptive
        only and **MUST NEVER** authorise a real trade.

    The orchestrator's responsibilities:

      - build the :class:`MoverCaptureRecallAuditReport` from a
        caller-provided :class:`MoverCaptureRecallAuditInput`;
      - emit ``MOVER_CAPTURE_PATH_AUDITED`` per record and
        ``MOVER_CAPTURE_RECALL_AUDIT_GENERATED`` per report
        through the :class:`EventRepository`;
      - cache the latest report so :meth:`metrics_payload` can
        return a stable dict for the daily-report builder.
    """

    SOURCE_MODULE: str = "mover_capture_recall_audit"
    SOURCE_PHASE: str = MOVER_CAPTURE_RECALL_AUDIT_SOURCE_PHASE

    def __init__(self, *, event_repo: Any = None) -> None:
        # ``event_repo`` is typed Any so the audit module does not
        # import the persistence layer directly. The runtime
        # accesses only ``event_repo.append(event)``; ``None`` is
        # tolerated so unit tests can exercise the orchestrator
        # without standing up SQLite.
        self._event_repo = event_repo
        self._latest_report: MoverCaptureRecallAuditReport | None = None
        self._mover_capture_recall_audit_generated_count: int = 0
        self._mover_capture_path_audited_count: int = 0

    # -- Properties --------------------------------------------------------
    @property
    def latest_report(self) -> MoverCaptureRecallAuditReport | None:
        return self._latest_report

    @property
    def mover_capture_recall_audit_generated_count(self) -> int:
        return self._mover_capture_recall_audit_generated_count

    @property
    def mover_capture_path_audited_count(self) -> int:
        return self._mover_capture_path_audited_count

    # -- Core action -------------------------------------------------------
    def flush(
        self,
        audit_input: MoverCaptureRecallAuditInput,
        *,
        generated_at_ms: int = 0,
        emit_events: bool = True,
    ) -> MoverCaptureRecallAuditReport:
        """Build the audit report from the input, emit the
        Phase 11C.1C-C-B-B-B-D events through the
        :class:`EventRepository`, and cache the result for
        :meth:`metrics_payload`.

        Pure aside from the cached state and the (optional)
        :class:`EventRepository` writes. Never raises on missing
        inputs - an empty ``top_movers`` produces an
        ``INSUFFICIENT_DATA`` report.
        """
        report = build_mover_capture_recall_audit_report(
            audit_input, evaluated_at_ms=int(generated_at_ms)
        )
        self._latest_report = report

        if emit_events and self._event_repo is not None:
            self._emit_audit_events(report=report, ts_ms=int(generated_at_ms))

        return report

    # -- Metrics -----------------------------------------------------------
    def metrics_payload(self) -> dict[str, Any]:
        """Return a JSON-safe dict of Phase 11C.1C-C-B-B-B-D
        aggregates the daily-report builder consumes.

        If no flush has been performed yet the payload still
        carries every key (zeros / empty values) so the
        downstream daily-report builder can render the section
        without ambiguity.
        """
        report = self._latest_report
        if report is None:
            return {
                "mover_capture_recall_audit_schema_version": (
                    MOVER_CAPTURE_RECALL_AUDIT_SCHEMA_VERSION
                ),
                "mover_capture_recall_audit_generated_count": int(
                    self._mover_capture_recall_audit_generated_count
                ),
                "mover_capture_path_audited_count": int(
                    self._mover_capture_path_audited_count
                ),
                "mover_capture_audit_status": "",
                "top_mover_count": 0,
                "captured_top_mover_count": 0,
                "partially_captured_top_mover_count": 0,
                "missed_top_mover_count": 0,
                "excluded_top_mover_count": 0,
                "insufficient_data_top_mover_count": 0,
                "capture_recall_rate": 0.0,
                "anomaly_detected_rate": 0.0,
                "label_tracking_rate": 0.0,
                "tail_label_assigned_rate": 0.0,
                "strategy_validation_sample_rate": 0.0,
                "risk_rejected_mover_count": 0,
                "not_in_universe_count": 0,
                "capacity_evicted_count": 0,
                "data_unreliable_count": 0,
                "median_first_seen_latency_seconds": 0.0,
                "mover_capture_records": [],
                "miss_reason_summary": {},
                "coverage_warnings": [],
                "mover_capture_audit_insufficient_reasons": [],
                "mover_capture_audit_warnings": [],
                "mover_capture_audit_report": {},
            }
        return {
            "mover_capture_recall_audit_schema_version": str(
                report.schema_version
            ),
            "mover_capture_recall_audit_generated_count": int(
                self._mover_capture_recall_audit_generated_count
            ),
            "mover_capture_path_audited_count": int(
                self._mover_capture_path_audited_count
            ),
            "mover_capture_audit_status": str(report.status),
            "top_mover_count": int(report.top_mover_count),
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
            "insufficient_data_top_mover_count": int(
                report.insufficient_data_top_mover_count
            ),
            "capture_recall_rate": float(report.capture_recall_rate),
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
            "capacity_evicted_count": int(report.capacity_evicted_count),
            "data_unreliable_count": int(report.data_unreliable_count),
            "median_first_seen_latency_seconds": float(
                report.median_first_seen_latency_seconds
            ),
            "mover_capture_records": [r.to_payload() for r in report.records],
            "miss_reason_summary": dict(report.miss_reason_summary),
            "coverage_warnings": list(report.coverage_warnings),
            "mover_capture_audit_insufficient_reasons": list(
                report.insufficient_coverage_reasons
            ),
            "mover_capture_audit_warnings": list(report.warnings),
            "mover_capture_audit_report": report.to_payload(),
        }

    # -- Internals ---------------------------------------------------------
    def _emit_audit_events(
        self,
        *,
        report: MoverCaptureRecallAuditReport,
        ts_ms: int,
    ) -> None:
        """Emit the two Phase 11C.1C-C-B-B-B-D events.

        Failures during a single emit are logged through the
        :class:`EventRepository` failure path but do not raise -
        the audit is paper / evidence only and a missing event
        log row must never crash the run.
        """
        identity = self._identity_block(report=report, ts_ms=ts_ms)

        # 1. Per-mover MOVER_CAPTURE_PATH_AUDITED so a downstream
        #    auditor can replay the per-mover capture map without
        #    parsing the full report.
        for record in report.records:
            payload = {
                **identity,
                "symbol": str(record.symbol),
                "audit_status": str(record.audit_status),
                "rank": int(record.rank),
                "miss_reasons": list(record.miss_reasons),
                "capture_recall_score": float(record.capture_recall_score),
                "in_eligible_universe": bool(record.in_eligible_universe),
                "risk_rejected": bool(record.risk_rejected),
                "has_completed_tail_label": bool(
                    record.has_completed_tail_label
                ),
                "has_strategy_validation_sample": bool(
                    record.has_strategy_validation_sample
                ),
                "first_seen_latency_seconds": float(
                    record.first_seen_latency_seconds
                ),
                "record": record.to_payload(),
            }
            self._emit_event(
                event_type_value="MOVER_CAPTURE_PATH_AUDITED",
                symbol=record.symbol or None,
                timestamp=ts_ms,
                payload=payload,
            )
            self._mover_capture_path_audited_count += 1

        # 2. Top-level MOVER_CAPTURE_RECALL_AUDIT_GENERATED.
        full_payload = {
            **identity,
            "report_status": str(report.status),
            "top_mover_count": int(report.top_mover_count),
            "captured_top_mover_count": int(report.captured_top_mover_count),
            "missed_top_mover_count": int(report.missed_top_mover_count),
            "excluded_top_mover_count": int(report.excluded_top_mover_count),
            "capture_recall_rate": float(report.capture_recall_rate),
            "miss_reason_summary": dict(report.miss_reason_summary),
            "coverage_warnings": list(report.coverage_warnings),
            "warnings": list(report.warnings),
            "insufficient_coverage_reasons": list(
                report.insufficient_coverage_reasons
            ),
            "report": report.to_payload(),
        }
        self._emit_event(
            event_type_value="MOVER_CAPTURE_RECALL_AUDIT_GENERATED",
            symbol=None,
            timestamp=ts_ms,
            payload=full_payload,
        )
        self._mover_capture_recall_audit_generated_count += 1

    def _identity_block(
        self,
        *,
        report: MoverCaptureRecallAuditReport,
        ts_ms: int,
    ) -> dict[str, Any]:
        return {
            "schema_version": MOVER_CAPTURE_RECALL_AUDIT_SCHEMA_VERSION,
            "audit_version": MOVER_CAPTURE_RECALL_AUDIT_VERSION,
            "source_phase": self.SOURCE_PHASE,
            "report_id": str(report.report_id),
            "audit_id": str(report.audit_id),
            "timestamp": int(ts_ms),
            "evaluated_at": int(report.evaluated_at),
            "audit_status": str(report.status),
            "strategy_version": str(report.strategy_version),
            "scoring_version": str(report.scoring_version),
            "risk_config_version": str(report.risk_config_version),
            "state_machine_version": str(report.state_machine_version),
        }

    def _emit_event(
        self,
        *,
        event_type_value: str,
        symbol: str | None,
        timestamp: int,
        payload: dict[str, Any],
    ) -> None:
        """Append one event through the wired EventRepository.

        The audit module imports the events module lazily so the
        pure-function path does not pull the persistence layer.
        """
        if self._event_repo is None:
            return
        try:
            from app.core.events import Event, EventType  # local import

            event = Event(
                event_type=EventType(event_type_value),
                source_module=self.SOURCE_MODULE,
                symbol=str(symbol) if symbol else None,
                timestamp=int(timestamp),
                payload=payload,
            )
            self._event_repo.append(event)
        except Exception:  # pragma: no cover - protective
            # Never raise from the audit emitter; the audit is
            # evidence-only and a missing event row must not crash
            # the run.
            return


__all__ = [
    # Constants
    "MOVER_CAPTURE_RECALL_AUDIT_SCHEMA_VERSION",
    "KNOWN_MOVER_CAPTURE_RECALL_AUDIT_SCHEMA_VERSIONS",
    "MOVER_CAPTURE_RECALL_AUDIT_VERSION",
    "MOVER_CAPTURE_RECALL_AUDIT_SOURCE_PHASE",
    "MOVER_CAPTURE_RECALL_AUDIT_STATUSES",
    "CAPTURE_PATH_STATUSES",
    "MISS_REASONS",
    "CAPTURE_PATH_STAGES",
    "CAPTURED_REQUIRED_STAGES",
    "CAPTURED_TERMINAL_STAGES",
    "FULL_CAPTURE_STRONG_STAGES",
    "DEFAULT_TOP_MOVER_LIMIT",
    "DEFAULT_MIN_PRICE_CHANGE_PCT",
    "DEFAULT_MIN_QUOTE_VOLUME_USDT",
    "DEFAULT_MIN_TOP_MOVER_COUNT",
    # Status / Reason holders
    "MoverCaptureRecallAuditStatus",
    "CapturePathStatus",
    "MissReason",
    # Models
    "TopMoverReference",
    "CapturePathEvidence",
    "MoverCaptureAuditRecord",
    "MoverCaptureRecallAuditInput",
    "MoverCaptureRecallAuditReport",
    # Pure functions
    "build_top_mover_reference_set",
    "audit_mover_capture_path",
    "classify_miss_reason",
    "build_mover_capture_recall_audit_report",
    "export_mover_capture_recall_audit_payload",
    "load_mover_capture_recall_audit_payload",
    # Runtime
    "MoverCaptureRecallAuditRuntime",
]
