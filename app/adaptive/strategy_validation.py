"""Phase 11C.1C-C-B-A - Strategy Validation Lab v0 & Cluster
Exposure Control Contracts.

Phase 11C.1C-C-A produces forward MFE / MAE / ``tail_label`` outcomes
for every ACTIVE candidate the WS-radar chain admits. This module
turns those outcomes into the **first version** of:

  - the Strategy Validation Lab data contract; and
  - the Cluster Exposure Control data contract.

Concretely, the Lab v0 lets a human reviewer answer:

  - is ``early_tail_score`` actually finding "demon coins" earlier?
  - does ``opportunity_score`` correlate with later MFE / MAE?
  - is ``strategy_mode`` (follow / pullback / observe / reject)
    making the right call?
  - is ``candidate_stage`` (early / mid / late / blowoff / dumped)
    informative?
  - is the cluster *leader* actually outperforming its followers?
  - do simultaneous candidates inside one cluster need exposure
    capping in a future PR?

Phase 11C.1C-C-B-A boundary
---------------------------

This module:

  - is paper / virtual ONLY;
  - is contracts + pure aggregation; the Lab is **NOT** a complete
    Strategy Validation Lab and not the Phase 11C.1C-C-B-B follow-up
    that ships richer auto-validation;
  - NEVER opens, closes, or reasons about a real position;
  - NEVER reads a private API / signed endpoint / private WS /
    listenKey / account / order / position / leverage / margin
    endpoint;
  - NEVER infers live position PnL;
  - NEVER calls an LLM / Telegram outbound / DeepSeek trade-decision
    endpoint;
  - NEVER opens a path into Phase 12 / AI Learning / automatic
    parameter optimisation;
  - emits every event through :class:`EventRepository` only;
  - tags every event payload with a ``schema_version`` field so old
    events without the v0 sub-block remain replayable verbatim;
  - the ``suggested_cluster_action`` on every
    :class:`ClusterExposureAssessment` is **paper / report only** and
    MUST NEVER trigger a real trade. The Risk Engine remains the
    single trade-decision gate.

The runtime that drives this module
(:class:`app.adaptive.strategy_validation_runtime.StrategyValidationRuntime`)
consumes the Phase 11C.1C-C-A label-tracking events and emits the
seven new typed events:

  - ``STRATEGY_VALIDATION_SAMPLE_CREATED``
  - ``STRATEGY_VALIDATION_REPORT_GENERATED``
  - ``STRATEGY_MODE_VALIDATED``
  - ``CANDIDATE_STAGE_VALIDATED``
  - ``SCORE_BUCKET_VALIDATED``
  - ``CLUSTER_EXPOSURE_ASSESSED``
  - ``CLUSTER_LEADER_VALIDATED``

This module ships the value-object contracts + pure aggregation
helpers; the runtime + EventRepository wiring lives in
:mod:`app.adaptive.strategy_validation_runtime`.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Schema version stamp written on every Phase 11C.1C-C-B-A payload.
#: A future PR that changes the payload shape MUST bump this label
#: and update :data:`KNOWN_STRATEGY_VALIDATION_SCHEMA_VERSIONS` so
#: Replay can detect the change explicitly.
STRATEGY_VALIDATION_SCHEMA_VERSION: str = (
    "phase_11c_1c_c_b_a.strategy_validation.v1"
)
KNOWN_STRATEGY_VALIDATION_SCHEMA_VERSIONS: tuple[str, ...] = (
    STRATEGY_VALIDATION_SCHEMA_VERSION,
)

#: Phase 11C.1C-C-B-A canonical version labels. Carried on every
#: event payload so Reflection / Replay can group on them without
#: parsing free-form audit dicts.
STRATEGY_VALIDATION_VERSION: str = (
    "phase_11c_1c_c_b_a.strategy_validation.v1"
)
STRATEGY_VALIDATION_SOURCE_PHASE: str = (
    "phase_11c_1c_c_b_a_strategy_validation_lab_v0"
)

#: Window selected as the *primary* MFE / MAE driver for cohort
#: aggregates. Mirrors the Phase 11C.1C-C-A primary window so the
#: validation lab and the label-runtime daily-report aggregates use
#: the same anchor.
STRATEGY_VALIDATION_PRIMARY_WINDOW: str = "5m"

#: Default tracking windows the Phase 11C.1C-C-A runtime exposes.
#: The Lab carries one ``mfe_*`` / ``mae_*`` pair per window onto
#: every sample so a future Lab can compute per-window correlations
#: without re-querying events.db.
STRATEGY_VALIDATION_TRACKING_WINDOWS: tuple[str, ...] = (
    "5m",
    "15m",
    "30m",
    "1h",
    "4h",
)

#: Phase 11C.1C-C-B-A opportunity-score buckets. The brief mandates
#: these as the v0 buckets so high-grade candidates can be compared
#: against low-grade ones by realised MFE / MAE.
OPPORTUNITY_SCORE_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0-49", 0.0, 49.0),
    ("50-64", 50.0, 64.0),
    ("65-79", 65.0, 79.0),
    ("80-100", 80.0, 100.0),
)
OPPORTUNITY_SCORE_BUCKET_LABELS: tuple[str, ...] = tuple(
    label for label, _, _ in OPPORTUNITY_SCORE_BUCKETS
)

#: Phase 11C.1C-C-B-A early-tail-score buckets.
EARLY_TAIL_SCORE_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0-24", 0.0, 24.0),
    ("25-49", 25.0, 49.0),
    ("50-74", 50.0, 74.0),
    ("75-100", 75.0, 100.0),
)
EARLY_TAIL_SCORE_BUCKET_LABELS: tuple[str, ...] = tuple(
    label for label, _, _ in EARLY_TAIL_SCORE_BUCKETS
)

#: Allowed paper / report-only suggestions on every
#: :class:`ClusterExposureAssessment`. The values are descriptive;
#: NONE of them authorises a real trade.
CLUSTER_ACTIONS: tuple[str, ...] = (
    "leader_only",
    "observe_followers",
    "reject_cluster",
    "no_action",
)

#: Threshold (count of correlated candidates) above which the Lab
#: surfaces an ``overexposure_warning`` on the cluster assessment.
DEFAULT_OVEREXPOSURE_WARNING_THRESHOLD: int = 3


# ---------------------------------------------------------------------------
# Bucket helpers
# ---------------------------------------------------------------------------
def opportunity_score_bucket_for(value: float) -> str:
    """Return the canonical opportunity-score bucket label for a score
    in ``[0.0, 100.0]``. Out-of-range inputs are clamped."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0
    if v < 0.0:
        v = 0.0
    if v > 100.0:
        v = 100.0
    for label, lo, hi in OPPORTUNITY_SCORE_BUCKETS:
        if lo <= v <= hi:
            return label
    # Defensive: should be unreachable.
    return OPPORTUNITY_SCORE_BUCKETS[0][0]


def early_tail_score_bucket_for(value: float) -> str:
    """Return the canonical early-tail-score bucket label."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0
    if v < 0.0:
        v = 0.0
    if v > 100.0:
        v = 100.0
    for label, lo, hi in EARLY_TAIL_SCORE_BUCKETS:
        if lo <= v <= hi:
            return label
    return EARLY_TAIL_SCORE_BUCKETS[0][0]


# ---------------------------------------------------------------------------
# Sample
# ---------------------------------------------------------------------------
class StrategyValidationSample(BaseModel):
    """One Strategy Validation Lab v0 sample for one opportunity.

    Brief contract: every per-candidate outcome the Phase 11C.1C-C-A
    runtime produces becomes one immutable sample. The Lab v0
    aggregators read a list of these and produce per-mode /
    per-stage / per-bucket cohort statistics.

    Phase 11C.1C-C-B-A boundary - the sample is descriptive only.
    Building one does NOT authorise opening a real position; the
    Risk Engine remains the single trade-decision gate.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Identity (Phase 8.5 contract).
    opportunity_id: str
    scan_batch_id: str
    symbol: str

    # Adaptive context snapshot (the values when the sample was taken).
    candidate_stage: str
    strategy_mode: str
    opportunity_score: float = 0.0
    opportunity_grade: str = "C"
    early_tail_score: float = 0.0
    late_chase_risk: float = 0.0

    # Cluster context.
    cluster_id: str = "unknown"
    cluster_leader: str | None = None
    is_cluster_leader: bool = False

    # Final tail label assigned by the Phase 11C.1C-C-A runtime
    # (rule-based; no LLM). One of :data:`TAIL_LABELS` from
    # :mod:`app.adaptive.label_runtime`.
    tail_label: str = "unresolved"

    # Per-window MFE / MAE (decimal returns; +0.05 = +5%).
    mfe_5m: float = 0.0
    mae_5m: float = 0.0
    mfe_15m: float = 0.0
    mae_15m: float = 0.0
    mfe_30m: float = 0.0
    mae_30m: float = 0.0
    mfe_1h: float = 0.0
    mae_1h: float = 0.0
    mfe_4h: float = 0.0
    mae_4h: float = 0.0

    # R-multiple milestones (driven by the primary window flags).
    reached_2r: bool = False
    reached_3r: bool = False
    reached_5r: bool = False
    reached_10r: bool = False

    # Outcome flags (driven by the primary window).
    fake_breakout: bool = False
    missed_tail: bool = False
    late_chase_failure: bool = False

    # Provenance / versioning so Reflection can group on these
    # without parsing free-form audit dicts.
    strategy_version: str = "phase_11c_1c_a.strategy.v1"
    scoring_version: str = "phase_11c_1c_a.scoring.v1"
    risk_config_version: str = "phase_11c_1c_a.risk_config.v1"
    state_machine_version: str = "phase_11c_1c_a.state_machine.v1"
    sample_created_ts: int = 0
    schema_version: str = STRATEGY_VALIDATION_SCHEMA_VERSION
    notes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("strategy_mode")
    @classmethod
    def _check_mode(cls, value: str) -> str:
        text = str(value).strip()
        if not text:
            return "observe"
        # Every Phase 11C.1C-A canonical mode is allowed; we intentionally
        # do NOT raise on unknown modes so the Lab can still record an
        # outcome for a future strategy_mode without bumping the schema.
        return text

    @field_validator("candidate_stage")
    @classmethod
    def _check_stage(cls, value: str) -> str:
        text = str(value).strip()
        if not text:
            return "early"
        return text

    @field_validator("opportunity_score", "early_tail_score", "late_chase_risk")
    @classmethod
    def _check_pct(cls, value: float) -> float:
        v = float(value)
        if v < 0.0:
            return 0.0
        if v > 100.0:
            return 100.0
        return v

    def to_payload(self) -> dict[str, Any]:
        return {
            "opportunity_id": str(self.opportunity_id),
            "scan_batch_id": str(self.scan_batch_id),
            "symbol": str(self.symbol),
            "candidate_stage": str(self.candidate_stage),
            "strategy_mode": str(self.strategy_mode),
            "opportunity_score": float(self.opportunity_score),
            "opportunity_grade": str(self.opportunity_grade),
            "early_tail_score": float(self.early_tail_score),
            "late_chase_risk": float(self.late_chase_risk),
            "cluster_id": str(self.cluster_id),
            "cluster_leader": (
                str(self.cluster_leader)
                if self.cluster_leader is not None
                else None
            ),
            "is_cluster_leader": bool(self.is_cluster_leader),
            "tail_label": str(self.tail_label),
            "mfe_5m": float(self.mfe_5m),
            "mae_5m": float(self.mae_5m),
            "mfe_15m": float(self.mfe_15m),
            "mae_15m": float(self.mae_15m),
            "mfe_30m": float(self.mfe_30m),
            "mae_30m": float(self.mae_30m),
            "mfe_1h": float(self.mfe_1h),
            "mae_1h": float(self.mae_1h),
            "mfe_4h": float(self.mfe_4h),
            "mae_4h": float(self.mae_4h),
            "reached_2r": bool(self.reached_2r),
            "reached_3r": bool(self.reached_3r),
            "reached_5r": bool(self.reached_5r),
            "reached_10r": bool(self.reached_10r),
            "fake_breakout": bool(self.fake_breakout),
            "missed_tail": bool(self.missed_tail),
            "late_chase_failure": bool(self.late_chase_failure),
            "strategy_version": str(self.strategy_version),
            "scoring_version": str(self.scoring_version),
            "risk_config_version": str(self.risk_config_version),
            "state_machine_version": str(self.state_machine_version),
            "sample_created_ts": int(self.sample_created_ts),
            "schema_version": str(self.schema_version),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Per-window aggregate
# ---------------------------------------------------------------------------
class StrategyValidationWindowStats(BaseModel):
    """Per-window MFE / MAE aggregate for a cohort.

    Used by every per-mode / per-stage / per-bucket aggregate to
    surface window-level granularity without expanding the cohort
    contract by a factor of five.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    window_name: str
    sample_count: int = 0
    avg_mfe: float = 0.0
    avg_mae: float = 0.0
    median_mfe: float = 0.0
    median_mae: float = 0.0

    def to_payload(self) -> dict[str, Any]:
        return {
            "window_name": str(self.window_name),
            "sample_count": int(self.sample_count),
            "avg_mfe": float(self.avg_mfe),
            "avg_mae": float(self.avg_mae),
            "median_mfe": float(self.median_mfe),
            "median_mae": float(self.median_mae),
        }


# ---------------------------------------------------------------------------
# Cohort aggregates
# ---------------------------------------------------------------------------
class _BaseCohortStats(BaseModel):
    """Shared cohort-level numerics for every per-mode / per-stage /
    per-bucket aggregate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_count: int = 0
    avg_mfe: float = 0.0
    avg_mae: float = 0.0
    median_mfe: float = 0.0
    median_mae: float = 0.0
    p_reached_2r: float = 0.0
    p_reached_3r: float = 0.0
    p_reached_5r: float = 0.0
    p_reached_10r: float = 0.0
    fake_breakout_rate: float = 0.0
    missed_tail_rate: float = 0.0
    late_chase_failure_rate: float = 0.0
    strong_tail_rate: float = 0.0
    weak_tail_rate: float = 0.0
    moderate_tail_rate: float = 0.0
    dumped_rate: float = 0.0
    unresolved_rate: float = 0.0
    window_stats: dict[str, StrategyValidationWindowStats] = Field(
        default_factory=dict
    )
    notes: tuple[str, ...] = Field(default_factory=tuple)

    def _shared_payload(self) -> dict[str, Any]:
        return {
            "sample_count": int(self.sample_count),
            "avg_mfe": float(self.avg_mfe),
            "avg_mae": float(self.avg_mae),
            "median_mfe": float(self.median_mfe),
            "median_mae": float(self.median_mae),
            "p_reached_2r": float(self.p_reached_2r),
            "p_reached_3r": float(self.p_reached_3r),
            "p_reached_5r": float(self.p_reached_5r),
            "p_reached_10r": float(self.p_reached_10r),
            "fake_breakout_rate": float(self.fake_breakout_rate),
            "missed_tail_rate": float(self.missed_tail_rate),
            "late_chase_failure_rate": float(self.late_chase_failure_rate),
            "strong_tail_rate": float(self.strong_tail_rate),
            "weak_tail_rate": float(self.weak_tail_rate),
            "moderate_tail_rate": float(self.moderate_tail_rate),
            "dumped_rate": float(self.dumped_rate),
            "unresolved_rate": float(self.unresolved_rate),
            "window_stats": {
                k: v.to_payload() for k, v in sorted(self.window_stats.items())
            },
            "notes": list(self.notes),
        }


class StrategyModeValidationStats(_BaseCohortStats):
    """Per-strategy_mode validation aggregate.

    Phase 11C.1C-C-B-A explicitly statisticks ``observe`` and
    ``reject`` cohorts because they validate "did the runtime correctly
    refuse"; that is just as important as validating the
    follow / pullback cohort.
    """

    strategy_mode: str = "observe"

    def to_payload(self) -> dict[str, Any]:
        return {"strategy_mode": str(self.strategy_mode), **self._shared_payload()}


class CandidateStageValidationStats(_BaseCohortStats):
    """Per-candidate_stage validation aggregate."""

    candidate_stage: str = "early"

    def to_payload(self) -> dict[str, Any]:
        return {
            "candidate_stage": str(self.candidate_stage),
            **self._shared_payload(),
        }


class OpportunityScoreBucketStats(_BaseCohortStats):
    """Per-opportunity_score-bucket aggregate."""

    bucket: str = ""
    bucket_lower: float = 0.0
    bucket_upper: float = 0.0

    def to_payload(self) -> dict[str, Any]:
        return {
            "bucket": str(self.bucket),
            "bucket_lower": float(self.bucket_lower),
            "bucket_upper": float(self.bucket_upper),
            **self._shared_payload(),
        }


class EarlyTailScoreBucketStats(_BaseCohortStats):
    """Per-early_tail_score-bucket aggregate."""

    bucket: str = ""
    bucket_lower: float = 0.0
    bucket_upper: float = 0.0

    def to_payload(self) -> dict[str, Any]:
        return {
            "bucket": str(self.bucket),
            "bucket_lower": float(self.bucket_lower),
            "bucket_upper": float(self.bucket_upper),
            **self._shared_payload(),
        }


# ---------------------------------------------------------------------------
# Tail label distribution
# ---------------------------------------------------------------------------
class TailLabelDistribution(BaseModel):
    """Tail-label distribution + headline rates across a sample set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_count: int = 0
    counts: dict[str, int] = Field(default_factory=dict)
    rates: dict[str, float] = Field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "sample_count": int(self.sample_count),
            "counts": {k: int(v) for k, v in sorted(self.counts.items())},
            "rates": {k: float(v) for k, v in sorted(self.rates.items())},
        }


# ---------------------------------------------------------------------------
# Cluster contracts
# ---------------------------------------------------------------------------
class ClusterLeaderValidationStats(BaseModel):
    """Per-cluster leader-vs-follower validation aggregate.

    The brief asks: is the cluster *leader* outperforming its
    followers? The fields below record the comparison so a human
    reviewer can audit the answer without re-deriving it from
    events.db.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: str
    leader_symbol: str | None = None
    leader_sample_count: int = 0
    follower_sample_count: int = 0
    leader_avg_mfe: float = 0.0
    follower_avg_mfe: float = 0.0
    leader_avg_mae: float = 0.0
    follower_avg_mae: float = 0.0
    leader_strong_tail_rate: float = 0.0
    follower_strong_tail_rate: float = 0.0
    leader_outperformed_followers: bool = False
    notes: tuple[str, ...] = Field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return {
            "cluster_id": str(self.cluster_id),
            "leader_symbol": (
                str(self.leader_symbol)
                if self.leader_symbol is not None
                else None
            ),
            "leader_sample_count": int(self.leader_sample_count),
            "follower_sample_count": int(self.follower_sample_count),
            "leader_avg_mfe": float(self.leader_avg_mfe),
            "follower_avg_mfe": float(self.follower_avg_mfe),
            "leader_avg_mae": float(self.leader_avg_mae),
            "follower_avg_mae": float(self.follower_avg_mae),
            "leader_strong_tail_rate": float(self.leader_strong_tail_rate),
            "follower_strong_tail_rate": float(
                self.follower_strong_tail_rate
            ),
            "leader_outperformed_followers": bool(
                self.leader_outperformed_followers
            ),
            "notes": list(self.notes),
        }


class ClusterExposureAssessment(BaseModel):
    """Cluster exposure data contract.

    Phase 11C.1C-C-B-A boundary - this contract is **paper / report
    only**. ``suggested_cluster_action`` is descriptive; nothing on
    this assessment authorises a real trade or modifies any real
    position. The Risk Engine remains the single trade-decision gate.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: str
    symbols: tuple[str, ...] = Field(default_factory=tuple)
    leader_symbol: str | None = None
    follower_symbols: tuple[str, ...] = Field(default_factory=tuple)
    leader_score: float = 0.0
    cluster_size: int = 0
    correlated_candidate_count: int = 0
    cluster_mfe_mean: float = 0.0
    cluster_mae_mean: float = 0.0
    leader_outperformed_followers: bool = False
    overexposure_warning: bool = False
    suggested_cluster_action: str = "no_action"
    reason_tags: tuple[str, ...] = Field(default_factory=tuple)
    notes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("suggested_cluster_action")
    @classmethod
    def _check_action(cls, value: str) -> str:
        text = str(value).strip()
        if text not in CLUSTER_ACTIONS:
            raise ValueError(
                f"suggested_cluster_action must be one of {CLUSTER_ACTIONS}; "
                f"got {value!r}"
            )
        return text

    def to_payload(self) -> dict[str, Any]:
        return {
            "cluster_id": str(self.cluster_id),
            "symbols": list(self.symbols),
            "leader_symbol": (
                str(self.leader_symbol)
                if self.leader_symbol is not None
                else None
            ),
            "follower_symbols": list(self.follower_symbols),
            "leader_score": float(self.leader_score),
            "cluster_size": int(self.cluster_size),
            "correlated_candidate_count": int(self.correlated_candidate_count),
            "cluster_mfe_mean": float(self.cluster_mfe_mean),
            "cluster_mae_mean": float(self.cluster_mae_mean),
            "leader_outperformed_followers": bool(
                self.leader_outperformed_followers
            ),
            "overexposure_warning": bool(self.overexposure_warning),
            "suggested_cluster_action": str(self.suggested_cluster_action),
            "reason_tags": list(self.reason_tags),
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Top-level report
# ---------------------------------------------------------------------------
class StrategyValidationReport(BaseModel):
    """Top-level Strategy Validation Lab v0 report.

    Aggregates every per-mode / per-stage / per-bucket / per-cluster
    statistic so a human reviewer can audit the runtime's discovery
    quality + cluster behaviour in a single payload.

    Phase 11C.1C-C-B-A boundary - this report is paper / report only.
    Generating one does NOT authorise any real trade and NEVER bumps
    a Phase 1 safety flag.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str
    generated_at_ms: int = 0
    sample_count: int = 0
    by_strategy_mode: dict[str, StrategyModeValidationStats] = Field(
        default_factory=dict
    )
    by_candidate_stage: dict[str, CandidateStageValidationStats] = Field(
        default_factory=dict
    )
    by_opportunity_score_bucket: dict[
        str, OpportunityScoreBucketStats
    ] = Field(default_factory=dict)
    by_early_tail_score_bucket: dict[
        str, EarlyTailScoreBucketStats
    ] = Field(default_factory=dict)
    tail_label_distribution: TailLabelDistribution = Field(
        default_factory=TailLabelDistribution
    )
    cluster_leader_validation: dict[str, ClusterLeaderValidationStats] = Field(
        default_factory=dict
    )
    cluster_exposure_assessments: tuple[ClusterExposureAssessment, ...] = (
        Field(default_factory=tuple)
    )
    top_strategy_validation_symbols: tuple[dict[str, Any], ...] = Field(
        default_factory=tuple
    )
    flagged_findings: tuple[str, ...] = Field(default_factory=tuple)
    strategy_version: str = "phase_11c_1c_a.strategy.v1"
    scoring_version: str = "phase_11c_1c_a.scoring.v1"
    risk_config_version: str = "phase_11c_1c_a.risk_config.v1"
    state_machine_version: str = "phase_11c_1c_a.state_machine.v1"
    schema_version: str = STRATEGY_VALIDATION_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "report_id": str(self.report_id),
            "generated_at_ms": int(self.generated_at_ms),
            "sample_count": int(self.sample_count),
            "by_strategy_mode": {
                k: v.to_payload()
                for k, v in sorted(self.by_strategy_mode.items())
            },
            "by_candidate_stage": {
                k: v.to_payload()
                for k, v in sorted(self.by_candidate_stage.items())
            },
            "by_opportunity_score_bucket": {
                k: v.to_payload()
                for k, v in sorted(
                    self.by_opportunity_score_bucket.items()
                )
            },
            "by_early_tail_score_bucket": {
                k: v.to_payload()
                for k, v in sorted(
                    self.by_early_tail_score_bucket.items()
                )
            },
            "tail_label_distribution": self.tail_label_distribution.to_payload(),
            "cluster_leader_validation": {
                k: v.to_payload()
                for k, v in sorted(self.cluster_leader_validation.items())
            },
            "cluster_exposure_assessments": [
                a.to_payload() for a in self.cluster_exposure_assessments
            ],
            "top_strategy_validation_symbols": list(
                self.top_strategy_validation_symbols
            ),
            "flagged_findings": list(self.flagged_findings),
            "strategy_version": str(self.strategy_version),
            "scoring_version": str(self.scoring_version),
            "risk_config_version": str(self.risk_config_version),
            "state_machine_version": str(self.state_machine_version),
            "schema_version": str(self.schema_version),
        }


# ---------------------------------------------------------------------------
# Sample builder
# ---------------------------------------------------------------------------
def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return float(default)
    if math.isnan(f) or math.isinf(f):
        return float(default)
    return f


def _safe_bool(value: Any) -> bool:
    return bool(value)


def _window_pct_from_record(
    record_or_payload: Any,
    window_name: str,
    *,
    field_name: str,
) -> float:
    """Extract ``window.<field_name>`` from a :class:`LabelTrackingRecord`
    or its ``to_payload()`` mapping. Returns 0.0 when the window is
    missing."""
    # Mapping form (e.g. an event payload dict).
    if isinstance(record_or_payload, Mapping):
        windows = record_or_payload.get("tracking_windows") or []
        for w in windows:
            if not isinstance(w, Mapping):
                continue
            if str(w.get("window_name")) == window_name:
                return _safe_float(w.get(field_name), 0.0)
        return 0.0
    # Object form (LabelTrackingRecord).
    windows = getattr(record_or_payload, "tracking_windows", []) or []
    for w in windows:
        if str(getattr(w, "window_name", "")) == window_name:
            return _safe_float(getattr(w, field_name, 0.0), 0.0)
    return 0.0


def _window_bool_from_record(
    record_or_payload: Any,
    window_name: str,
    *,
    field_name: str,
) -> bool:
    if isinstance(record_or_payload, Mapping):
        windows = record_or_payload.get("tracking_windows") or []
        for w in windows:
            if isinstance(w, Mapping) and str(w.get("window_name")) == window_name:
                return _safe_bool(w.get(field_name, False))
        return False
    windows = getattr(record_or_payload, "tracking_windows", []) or []
    for w in windows:
        if str(getattr(w, "window_name", "")) == window_name:
            return _safe_bool(getattr(w, field_name, False))
    return False


def _window_label_from_record(
    record_or_payload: Any,
    window_name: str,
    *,
    field_name: str = "tail_label",
) -> str:
    if isinstance(record_or_payload, Mapping):
        windows = record_or_payload.get("tracking_windows") or []
        for w in windows:
            if isinstance(w, Mapping) and str(w.get("window_name")) == window_name:
                return str(w.get(field_name) or "")
        return ""
    windows = getattr(record_or_payload, "tracking_windows", []) or []
    for w in windows:
        if str(getattr(w, "window_name", "")) == window_name:
            return str(getattr(w, field_name, "") or "")
    return ""


def build_strategy_validation_sample(
    *,
    label_record: Any = None,
    adaptive: Any = None,
    sample_created_ts: int = 0,
    primary_window: str = STRATEGY_VALIDATION_PRIMARY_WINDOW,
    notes: Sequence[str] = (),
    schema_version: str = STRATEGY_VALIDATION_SCHEMA_VERSION,
) -> StrategyValidationSample:
    """Build a :class:`StrategyValidationSample` from a Phase 11C.1C-C-A
    :class:`LabelTrackingRecord` (or its ``to_payload()`` mapping)
    and the originating Phase 11C.1C-A
    :class:`AdaptiveCandidateContext` (or its ``to_payload()`` mapping).

    Either ``label_record`` or ``adaptive`` is required; when only
    one is supplied, the missing fields default to safe zeros so the
    Lab can still record an outcome (e.g. when a label record is
    expired before an adaptive snapshot is available).

    The function is **pure**: no I/O, no clock read, no
    ``EventRepository.append_event`` call. ``sample_created_ts`` MUST
    be supplied by the caller.
    """
    if label_record is None and adaptive is None:
        raise ValueError(
            "build_strategy_validation_sample requires at least one of "
            "label_record or adaptive"
        )

    # Identity.
    opp_id = ""
    scan_batch_id = ""
    symbol = ""
    if adaptive is not None:
        if isinstance(adaptive, Mapping):
            opp_id = str(adaptive.get("opportunity_id") or "")
            scan_batch_id = str(adaptive.get("scan_batch_id") or "")
            symbol = str(adaptive.get("symbol") or "")
        else:
            opp_id = str(getattr(adaptive, "opportunity_id", "") or "")
            scan_batch_id = str(getattr(adaptive, "scan_batch_id", "") or "")
            symbol = str(getattr(adaptive, "symbol", "") or "")
    if label_record is not None and (not opp_id or not scan_batch_id or not symbol):
        if isinstance(label_record, Mapping):
            opp_id = opp_id or str(label_record.get("opportunity_id") or "")
            scan_batch_id = scan_batch_id or str(
                label_record.get("scan_batch_id") or ""
            )
            symbol = symbol or str(label_record.get("symbol") or "")
        else:
            opp_id = opp_id or str(
                getattr(label_record, "opportunity_id", "") or ""
            )
            scan_batch_id = scan_batch_id or str(
                getattr(label_record, "scan_batch_id", "") or ""
            )
            symbol = symbol or str(getattr(label_record, "symbol", "") or "")

    # Adaptive sub-block.
    candidate_stage = "early"
    strategy_mode = "observe"
    opportunity_score_value = 0.0
    opportunity_grade = "C"
    early_tail_score = 0.0
    late_chase_risk = 0.0
    cluster_id = "unknown"
    cluster_leader: str | None = None
    is_cluster_leader = False
    strategy_version = "phase_11c_1c_a.strategy.v1"
    scoring_version = "phase_11c_1c_a.scoring.v1"
    risk_config_version = "phase_11c_1c_a.risk_config.v1"
    state_machine_version = "phase_11c_1c_a.state_machine.v1"
    if adaptive is not None:
        if isinstance(adaptive, Mapping):
            stage_block = adaptive.get("candidate_stage") or {}
            score_block = adaptive.get("opportunity_score") or {}
            mode_block = adaptive.get("strategy_mode") or {}
            cluster_block = adaptive.get("cluster") or {}
            runtime_block = adaptive.get("runtime_calibration") or {}
            candidate_stage = str(
                stage_block.get("stage") if isinstance(stage_block, Mapping)
                else "early"
            ) or "early"
            opportunity_score_value = _safe_float(
                score_block.get("score") if isinstance(score_block, Mapping)
                else 0.0
            )
            opportunity_grade = str(
                score_block.get("grade")
                if isinstance(score_block, Mapping)
                else "C"
            ) or "C"
            strategy_mode = str(
                mode_block.get("mode") if isinstance(mode_block, Mapping)
                else "observe"
            ) or "observe"
            cluster_id = str(
                cluster_block.get("cluster_id")
                if isinstance(cluster_block, Mapping)
                else "unknown"
            ) or "unknown"
            leader_value = (
                cluster_block.get("cluster_leader")
                if isinstance(cluster_block, Mapping)
                else None
            )
            cluster_leader = (
                str(leader_value) if leader_value is not None else None
            )
            if isinstance(runtime_block, Mapping):
                early_tail_score = _safe_float(
                    runtime_block.get("early_tail_score"), 0.0
                )
                late_chase_risk = _safe_float(
                    runtime_block.get("late_chase_risk"), 0.0
                )
            if isinstance(score_block, Mapping):
                # Fall-back: late_chase_risk on the score block if no
                # runtime calibration is present.
                if late_chase_risk == 0.0:
                    late_chase_risk = _safe_float(
                        score_block.get("late_chase_risk"), 0.0
                    )
            strategy_version = str(
                adaptive.get("strategy_version") or strategy_version
            )
            scoring_version = str(
                adaptive.get("scoring_version") or scoring_version
            )
            risk_config_version = str(
                adaptive.get("risk_config_version") or risk_config_version
            )
            state_machine_version = str(
                adaptive.get("state_machine_version") or state_machine_version
            )
        else:
            stage_obj = getattr(adaptive, "candidate_stage", None)
            score_obj = getattr(adaptive, "opportunity_score", None)
            mode_obj = getattr(adaptive, "strategy_mode", None)
            cluster_obj = getattr(adaptive, "cluster", None)
            runtime_obj = getattr(adaptive, "runtime_calibration", None)
            if stage_obj is not None:
                candidate_stage = str(getattr(stage_obj, "stage", "early"))
            if score_obj is not None:
                opportunity_score_value = _safe_float(
                    getattr(score_obj, "score", 0.0)
                )
                opportunity_grade = str(getattr(score_obj, "grade", "C"))
                if late_chase_risk == 0.0:
                    late_chase_risk = _safe_float(
                        getattr(score_obj, "late_chase_risk", 0.0), 0.0
                    )
            if mode_obj is not None:
                strategy_mode = str(getattr(mode_obj, "mode", "observe"))
            if cluster_obj is not None:
                cluster_id = str(
                    getattr(cluster_obj, "cluster_id", "unknown")
                )
                leader_attr = getattr(cluster_obj, "cluster_leader", None)
                cluster_leader = (
                    str(leader_attr) if leader_attr is not None else None
                )
            if runtime_obj is not None:
                early_tail_score = _safe_float(
                    getattr(runtime_obj, "early_tail_score", 0.0)
                )
                late_chase_risk = _safe_float(
                    getattr(runtime_obj, "late_chase_risk", 0.0),
                    late_chase_risk,
                )
            strategy_version = str(
                getattr(adaptive, "strategy_version", strategy_version)
            )
            scoring_version = str(
                getattr(adaptive, "scoring_version", scoring_version)
            )
            risk_config_version = str(
                getattr(adaptive, "risk_config_version", risk_config_version)
            )
            state_machine_version = str(
                getattr(adaptive, "state_machine_version", state_machine_version)
            )

    # Label-record sub-block (Phase 11C.1C-C-A).
    tail_label = "unresolved"
    mfe = {w: 0.0 for w in STRATEGY_VALIDATION_TRACKING_WINDOWS}
    mae = {w: 0.0 for w in STRATEGY_VALIDATION_TRACKING_WINDOWS}
    reached_2r = False
    reached_3r = False
    reached_5r = False
    reached_10r = False
    fake_breakout = False
    missed_tail = False
    if label_record is not None:
        for w in STRATEGY_VALIDATION_TRACKING_WINDOWS:
            mfe[w] = _window_pct_from_record(
                label_record, w, field_name="mfe_pct"
            )
            mae[w] = _window_pct_from_record(
                label_record, w, field_name="mae_pct"
            )
        # Pull primary-window flags + the record-level tail label.
        reached_2r = _window_bool_from_record(
            label_record, primary_window, field_name="reached_2r"
        )
        reached_3r = _window_bool_from_record(
            label_record, primary_window, field_name="reached_3r"
        )
        reached_5r = _window_bool_from_record(
            label_record, primary_window, field_name="reached_5r"
        )
        reached_10r = _window_bool_from_record(
            label_record, primary_window, field_name="reached_10r"
        )
        fake_breakout = _window_bool_from_record(
            label_record, primary_window, field_name="fake_breakout"
        )
        missed_tail = _window_bool_from_record(
            label_record, primary_window, field_name="missed_tail"
        )
        # Record-level tail label preferred, then per-window.
        if isinstance(label_record, Mapping):
            tail_label = str(label_record.get("final_tail_label") or "")
            if not tail_label:
                tail_label = _window_label_from_record(
                    label_record, primary_window
                )
            # Allow falling back to the record's own
            # ``strategy_mode`` / ``candidate_stage`` if the adaptive
            # context did not provide them.
            if strategy_mode == "observe":
                strategy_mode = (
                    str(label_record.get("strategy_mode") or strategy_mode)
                )
            if candidate_stage == "early":
                candidate_stage = (
                    str(label_record.get("candidate_stage") or candidate_stage)
                )
            if early_tail_score == 0.0:
                early_tail_score = _safe_float(
                    label_record.get("early_tail_score"), 0.0
                )
            if late_chase_risk == 0.0:
                late_chase_risk = _safe_float(
                    label_record.get("late_chase_risk"), 0.0
                )
            if opportunity_score_value == 0.0:
                opportunity_score_value = _safe_float(
                    label_record.get("opportunity_score"), 0.0
                )
        else:
            tail_label = str(getattr(label_record, "final_tail_label", "") or "")
            if not tail_label:
                tail_label = _window_label_from_record(
                    label_record, primary_window
                )
            if strategy_mode == "observe":
                strategy_mode = str(
                    getattr(label_record, "strategy_mode", strategy_mode)
                )
            if candidate_stage == "early":
                candidate_stage = str(
                    getattr(label_record, "candidate_stage", candidate_stage)
                )
            if early_tail_score == 0.0:
                early_tail_score = _safe_float(
                    getattr(label_record, "early_tail_score", 0.0)
                )
            if late_chase_risk == 0.0:
                late_chase_risk = _safe_float(
                    getattr(label_record, "late_chase_risk", 0.0)
                )
            if opportunity_score_value == 0.0:
                opportunity_score_value = _safe_float(
                    getattr(label_record, "opportunity_score", 0.0)
                )

    if not tail_label:
        tail_label = "unresolved"

    # Derived flags.
    is_cluster_leader = bool(
        cluster_leader is not None
        and symbol
        and symbol == cluster_leader
    )
    late_chase_failure = bool(tail_label == "late_chase_failure")

    return StrategyValidationSample(
        opportunity_id=str(opp_id),
        scan_batch_id=str(scan_batch_id),
        symbol=str(symbol),
        candidate_stage=str(candidate_stage),
        strategy_mode=str(strategy_mode),
        opportunity_score=float(opportunity_score_value),
        opportunity_grade=str(opportunity_grade),
        early_tail_score=float(early_tail_score),
        late_chase_risk=float(late_chase_risk),
        cluster_id=str(cluster_id),
        cluster_leader=cluster_leader,
        is_cluster_leader=bool(is_cluster_leader),
        tail_label=str(tail_label),
        mfe_5m=float(mfe["5m"]),
        mae_5m=float(mae["5m"]),
        mfe_15m=float(mfe["15m"]),
        mae_15m=float(mae["15m"]),
        mfe_30m=float(mfe["30m"]),
        mae_30m=float(mae["30m"]),
        mfe_1h=float(mfe["1h"]),
        mae_1h=float(mae["1h"]),
        mfe_4h=float(mfe["4h"]),
        mae_4h=float(mae["4h"]),
        reached_2r=bool(reached_2r),
        reached_3r=bool(reached_3r),
        reached_5r=bool(reached_5r),
        reached_10r=bool(reached_10r),
        fake_breakout=bool(fake_breakout),
        missed_tail=bool(missed_tail),
        late_chase_failure=bool(late_chase_failure),
        strategy_version=str(strategy_version),
        scoring_version=str(scoring_version),
        risk_config_version=str(risk_config_version),
        state_machine_version=str(state_machine_version),
        sample_created_ts=int(sample_created_ts),
        schema_version=str(schema_version),
        notes=tuple(str(n) for n in notes),
    )


# ---------------------------------------------------------------------------
# Cohort-level numeric helpers
# ---------------------------------------------------------------------------
def _mean_or_zero(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    try:
        return float(statistics.fmean(values))
    except statistics.StatisticsError:
        return 0.0


def _median_or_zero(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    try:
        return float(statistics.median(values))
    except statistics.StatisticsError:
        return 0.0


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _mfe_for_window(sample: StrategyValidationSample, window: str) -> float:
    return _safe_float(getattr(sample, f"mfe_{window}", 0.0), 0.0)


def _mae_for_window(sample: StrategyValidationSample, window: str) -> float:
    return _safe_float(getattr(sample, f"mae_{window}", 0.0), 0.0)


def _build_window_stats(
    samples: Sequence[StrategyValidationSample],
) -> dict[str, StrategyValidationWindowStats]:
    stats: dict[str, StrategyValidationWindowStats] = {}
    for window in STRATEGY_VALIDATION_TRACKING_WINDOWS:
        mfes = [_mfe_for_window(s, window) for s in samples]
        maes = [_mae_for_window(s, window) for s in samples]
        stats[window] = StrategyValidationWindowStats(
            window_name=window,
            sample_count=len(samples),
            avg_mfe=_mean_or_zero(mfes),
            avg_mae=_mean_or_zero(maes),
            median_mfe=_median_or_zero(mfes),
            median_mae=_median_or_zero(maes),
        )
    return stats


def _cohort_numerics(
    samples: Sequence[StrategyValidationSample],
    *,
    primary_window: str = STRATEGY_VALIDATION_PRIMARY_WINDOW,
) -> dict[str, Any]:
    n = len(samples)
    if n == 0:
        return {
            "sample_count": 0,
            "avg_mfe": 0.0,
            "avg_mae": 0.0,
            "median_mfe": 0.0,
            "median_mae": 0.0,
            "p_reached_2r": 0.0,
            "p_reached_3r": 0.0,
            "p_reached_5r": 0.0,
            "p_reached_10r": 0.0,
            "fake_breakout_rate": 0.0,
            "missed_tail_rate": 0.0,
            "late_chase_failure_rate": 0.0,
            "strong_tail_rate": 0.0,
            "weak_tail_rate": 0.0,
            "moderate_tail_rate": 0.0,
            "dumped_rate": 0.0,
            "unresolved_rate": 0.0,
            "window_stats": _build_window_stats(()),
        }
    primary_mfes = [_mfe_for_window(s, primary_window) for s in samples]
    primary_maes = [_mae_for_window(s, primary_window) for s in samples]
    reached_2r = sum(1 for s in samples if s.reached_2r)
    reached_3r = sum(1 for s in samples if s.reached_3r)
    reached_5r = sum(1 for s in samples if s.reached_5r)
    reached_10r = sum(1 for s in samples if s.reached_10r)
    fake_breakout = sum(1 for s in samples if s.fake_breakout)
    missed_tail = sum(1 for s in samples if s.missed_tail)
    late_chase_failure = sum(1 for s in samples if s.late_chase_failure)
    strong_tail = sum(1 for s in samples if s.tail_label == "strong_tail")
    weak_tail = sum(1 for s in samples if s.tail_label == "weak_tail")
    moderate_tail = sum(1 for s in samples if s.tail_label == "moderate_tail")
    dumped = sum(1 for s in samples if s.tail_label == "dumped")
    unresolved = sum(1 for s in samples if s.tail_label == "unresolved")
    return {
        "sample_count": n,
        "avg_mfe": _mean_or_zero(primary_mfes),
        "avg_mae": _mean_or_zero(primary_maes),
        "median_mfe": _median_or_zero(primary_mfes),
        "median_mae": _median_or_zero(primary_maes),
        "p_reached_2r": _rate(reached_2r, n),
        "p_reached_3r": _rate(reached_3r, n),
        "p_reached_5r": _rate(reached_5r, n),
        "p_reached_10r": _rate(reached_10r, n),
        "fake_breakout_rate": _rate(fake_breakout, n),
        "missed_tail_rate": _rate(missed_tail, n),
        "late_chase_failure_rate": _rate(late_chase_failure, n),
        "strong_tail_rate": _rate(strong_tail, n),
        "weak_tail_rate": _rate(weak_tail, n),
        "moderate_tail_rate": _rate(moderate_tail, n),
        "dumped_rate": _rate(dumped, n),
        "unresolved_rate": _rate(unresolved, n),
        "window_stats": _build_window_stats(samples),
    }


# ---------------------------------------------------------------------------
# Aggregators
# ---------------------------------------------------------------------------
def aggregate_by_strategy_mode(
    samples: Iterable[StrategyValidationSample],
    *,
    include_modes: Sequence[str] = ("follow", "pullback", "observe", "reject"),
    primary_window: str = STRATEGY_VALIDATION_PRIMARY_WINDOW,
) -> dict[str, StrategyModeValidationStats]:
    """Aggregate samples by ``strategy_mode``.

    Brief contract: ``observe`` and ``reject`` MUST be aggregated
    alongside ``follow`` and ``pullback`` because validating a
    refusal is just as informative as validating an admission. The
    function returns a dict keyed by mode (a mode with zero samples
    in the cohort is omitted; ``include_modes`` ensures the four
    canonical modes are always present, possibly empty).
    """
    samples_list = list(samples)
    by_mode: dict[str, list[StrategyValidationSample]] = {}
    for s in samples_list:
        by_mode.setdefault(str(s.strategy_mode), []).append(s)
    out: dict[str, StrategyModeValidationStats] = {}
    seen_modes: set[str] = set()
    for mode in include_modes:
        seen_modes.add(mode)
        bucket = by_mode.get(mode, [])
        out[mode] = StrategyModeValidationStats(
            strategy_mode=mode,
            **_cohort_numerics(bucket, primary_window=primary_window),
        )
    # Carry through any non-canonical modes the caller still wants
    # to see (defensive: a future PR could add a new strategy_mode
    # without bumping the schema).
    for mode, bucket in by_mode.items():
        if mode in seen_modes:
            continue
        out[mode] = StrategyModeValidationStats(
            strategy_mode=mode,
            **_cohort_numerics(bucket, primary_window=primary_window),
        )
    return out


def aggregate_by_candidate_stage(
    samples: Iterable[StrategyValidationSample],
    *,
    include_stages: Sequence[str] = (
        "early",
        "mid",
        "late",
        "blowoff",
        "dumped",
    ),
    primary_window: str = STRATEGY_VALIDATION_PRIMARY_WINDOW,
) -> dict[str, CandidateStageValidationStats]:
    """Aggregate samples by ``candidate_stage``.

    Brief contract: the ``dumped`` stage MUST be aggregated, and the
    aggregator MUST NOT interpret it as a long opportunity. The
    aggregator only counts; downstream code is responsible for
    refusing to authorise a long.
    """
    samples_list = list(samples)
    by_stage: dict[str, list[StrategyValidationSample]] = {}
    for s in samples_list:
        by_stage.setdefault(str(s.candidate_stage), []).append(s)
    out: dict[str, CandidateStageValidationStats] = {}
    seen_stages: set[str] = set()
    for stage in include_stages:
        seen_stages.add(stage)
        bucket = by_stage.get(stage, [])
        out[stage] = CandidateStageValidationStats(
            candidate_stage=stage,
            **_cohort_numerics(bucket, primary_window=primary_window),
        )
    for stage, bucket in by_stage.items():
        if stage in seen_stages:
            continue
        out[stage] = CandidateStageValidationStats(
            candidate_stage=stage,
            **_cohort_numerics(bucket, primary_window=primary_window),
        )
    return out


def aggregate_by_opportunity_score_bucket(
    samples: Iterable[StrategyValidationSample],
    *,
    primary_window: str = STRATEGY_VALIDATION_PRIMARY_WINDOW,
) -> dict[str, OpportunityScoreBucketStats]:
    """Aggregate samples by opportunity-score bucket.

    Buckets: ``0-49`` / ``50-64`` / ``65-79`` / ``80-100``.
    """
    samples_list = list(samples)
    by_bucket: dict[str, list[StrategyValidationSample]] = {}
    for s in samples_list:
        bucket = opportunity_score_bucket_for(s.opportunity_score)
        by_bucket.setdefault(bucket, []).append(s)
    out: dict[str, OpportunityScoreBucketStats] = {}
    for label, lo, hi in OPPORTUNITY_SCORE_BUCKETS:
        bucket = by_bucket.get(label, [])
        out[label] = OpportunityScoreBucketStats(
            bucket=label,
            bucket_lower=float(lo),
            bucket_upper=float(hi),
            **_cohort_numerics(bucket, primary_window=primary_window),
        )
    return out


def aggregate_by_early_tail_score_bucket(
    samples: Iterable[StrategyValidationSample],
    *,
    primary_window: str = STRATEGY_VALIDATION_PRIMARY_WINDOW,
) -> dict[str, EarlyTailScoreBucketStats]:
    """Aggregate samples by early-tail-score bucket.

    Buckets: ``0-24`` / ``25-49`` / ``50-74`` / ``75-100``.
    """
    samples_list = list(samples)
    by_bucket: dict[str, list[StrategyValidationSample]] = {}
    for s in samples_list:
        bucket = early_tail_score_bucket_for(s.early_tail_score)
        by_bucket.setdefault(bucket, []).append(s)
    out: dict[str, EarlyTailScoreBucketStats] = {}
    for label, lo, hi in EARLY_TAIL_SCORE_BUCKETS:
        bucket = by_bucket.get(label, [])
        out[label] = EarlyTailScoreBucketStats(
            bucket=label,
            bucket_lower=float(lo),
            bucket_upper=float(hi),
            **_cohort_numerics(bucket, primary_window=primary_window),
        )
    return out


def aggregate_tail_label_distribution(
    samples: Iterable[StrategyValidationSample],
) -> TailLabelDistribution:
    """Aggregate samples into a :class:`TailLabelDistribution`."""
    samples_list = list(samples)
    n = len(samples_list)
    counts: dict[str, int] = {}
    for s in samples_list:
        counts[str(s.tail_label)] = counts.get(str(s.tail_label), 0) + 1
    rates: dict[str, float] = {
        k: _rate(v, n) for k, v in counts.items()
    } if n else {}
    return TailLabelDistribution(
        sample_count=n, counts=counts, rates=rates
    )


# ---------------------------------------------------------------------------
# Cluster validation
# ---------------------------------------------------------------------------
def evaluate_cluster_leader_performance(
    samples: Iterable[StrategyValidationSample],
    *,
    primary_window: str = STRATEGY_VALIDATION_PRIMARY_WINDOW,
) -> dict[str, ClusterLeaderValidationStats]:
    """Compare the leader's outcomes against the followers' inside
    each cluster.

    The brief asks: did the cluster leader actually outperform its
    followers? The function partitions samples by ``cluster_id`` and
    splits each partition by ``is_cluster_leader``.

    A cluster with no leader sample (no ``is_cluster_leader=True``
    sample) still produces a stats entry with ``leader_symbol=None``
    so the daily report can surface "no leader observed".
    """
    samples_list = list(samples)
    by_cluster: dict[str, list[StrategyValidationSample]] = {}
    for s in samples_list:
        by_cluster.setdefault(str(s.cluster_id), []).append(s)
    out: dict[str, ClusterLeaderValidationStats] = {}
    for cluster_id, cluster_samples in by_cluster.items():
        leader_samples = [s for s in cluster_samples if s.is_cluster_leader]
        follower_samples = [s for s in cluster_samples if not s.is_cluster_leader]
        leader_symbol: str | None = None
        if leader_samples:
            # Pick the first observed leader symbol; in v0 we expect
            # at most one leader per cluster, but we do not raise on
            # duplicates.
            leader_symbol = str(leader_samples[0].symbol or "") or None
        leader_mfes = [
            _mfe_for_window(s, primary_window) for s in leader_samples
        ]
        leader_maes = [
            _mae_for_window(s, primary_window) for s in leader_samples
        ]
        follower_mfes = [
            _mfe_for_window(s, primary_window) for s in follower_samples
        ]
        follower_maes = [
            _mae_for_window(s, primary_window) for s in follower_samples
        ]
        leader_avg_mfe = _mean_or_zero(leader_mfes)
        follower_avg_mfe = _mean_or_zero(follower_mfes)
        leader_avg_mae = _mean_or_zero(leader_maes)
        follower_avg_mae = _mean_or_zero(follower_maes)
        leader_strong = sum(
            1 for s in leader_samples if s.tail_label == "strong_tail"
        )
        follower_strong = sum(
            1 for s in follower_samples if s.tail_label == "strong_tail"
        )
        leader_strong_rate = _rate(leader_strong, len(leader_samples))
        follower_strong_rate = _rate(follower_strong, len(follower_samples))
        leader_outperformed = bool(
            leader_samples
            and follower_samples
            and leader_avg_mfe > follower_avg_mfe
        )
        notes: list[str] = []
        if not leader_samples:
            notes.append("no_leader_sample")
        if not follower_samples:
            notes.append("no_follower_sample")
        out[cluster_id] = ClusterLeaderValidationStats(
            cluster_id=cluster_id,
            leader_symbol=leader_symbol,
            leader_sample_count=len(leader_samples),
            follower_sample_count=len(follower_samples),
            leader_avg_mfe=leader_avg_mfe,
            follower_avg_mfe=follower_avg_mfe,
            leader_avg_mae=leader_avg_mae,
            follower_avg_mae=follower_avg_mae,
            leader_strong_tail_rate=leader_strong_rate,
            follower_strong_tail_rate=follower_strong_rate,
            leader_outperformed_followers=leader_outperformed,
            notes=tuple(notes),
        )
    return out


def assess_cluster_exposure(
    samples: Iterable[StrategyValidationSample],
    *,
    primary_window: str = STRATEGY_VALIDATION_PRIMARY_WINDOW,
    overexposure_warning_threshold: int = (
        DEFAULT_OVEREXPOSURE_WARNING_THRESHOLD
    ),
) -> tuple[ClusterExposureAssessment, ...]:
    """Build per-cluster :class:`ClusterExposureAssessment` records.

    Phase 11C.1C-C-B-A boundary - the assessments are paper / report
    only. Nothing on the resulting tuple authorises a real trade.
    """
    samples_list = list(samples)
    by_cluster: dict[str, list[StrategyValidationSample]] = {}
    for s in samples_list:
        by_cluster.setdefault(str(s.cluster_id), []).append(s)
    out: list[ClusterExposureAssessment] = []
    for cluster_id in sorted(by_cluster):
        cluster_samples = by_cluster[cluster_id]
        # Deduplicate symbols while preserving first-seen order.
        seen_syms: list[str] = []
        for s in cluster_samples:
            sym = str(s.symbol or "")
            if sym and sym not in seen_syms:
                seen_syms.append(sym)
        leader_samples = [s for s in cluster_samples if s.is_cluster_leader]
        leader_symbol: str | None = (
            str(leader_samples[0].symbol)
            if leader_samples
            else None
        )
        follower_symbols = tuple(
            s for s in seen_syms if s != (leader_symbol or "")
        )
        leader_score = (
            float(leader_samples[0].opportunity_score)
            if leader_samples
            else 0.0
        )
        cluster_size = len(seen_syms)
        correlated = len(cluster_samples)
        cluster_mfes = [
            _mfe_for_window(s, primary_window) for s in cluster_samples
        ]
        cluster_maes = [
            _mae_for_window(s, primary_window) for s in cluster_samples
        ]
        cluster_mfe_mean = _mean_or_zero(cluster_mfes)
        cluster_mae_mean = _mean_or_zero(cluster_maes)
        leader_mfes = [
            _mfe_for_window(s, primary_window) for s in leader_samples
        ]
        leader_avg_mfe = _mean_or_zero(leader_mfes)
        follower_mfes = [
            _mfe_for_window(s, primary_window)
            for s in cluster_samples
            if not s.is_cluster_leader
        ]
        follower_avg_mfe = _mean_or_zero(follower_mfes)
        leader_outperformed = bool(
            leader_samples
            and follower_mfes
            and leader_avg_mfe > follower_avg_mfe
        )
        overexposure = bool(
            correlated >= int(overexposure_warning_threshold)
        )

        # Decide the suggested cluster action. PAPER / REPORT ONLY.
        # Hierarchy:
        # 1. all dumped + no strong tail -> reject_cluster
        # 2. leader_outperformed_followers AND >= 2 follower samples
        #    -> leader_only
        # 3. follower_avg_mfe > leader_avg_mfe AND leader_samples
        #    -> observe_followers
        # 4. otherwise -> no_action
        action = "no_action"
        reason_tags: list[str] = []
        dumped_count = sum(
            1 for s in cluster_samples if s.tail_label == "dumped"
        )
        strong_count = sum(
            1 for s in cluster_samples if s.tail_label == "strong_tail"
        )
        if (
            cluster_samples
            and dumped_count == len(cluster_samples)
            and strong_count == 0
        ):
            action = "reject_cluster"
            reason_tags.append("all_dumped")
        elif leader_outperformed and len(follower_mfes) >= 2:
            action = "leader_only"
            reason_tags.append("leader_outperformed")
        elif (
            leader_samples
            and follower_mfes
            and follower_avg_mfe > leader_avg_mfe
        ):
            action = "observe_followers"
            reason_tags.append("followers_outperformed_leader")
        else:
            reason_tags.append("insufficient_signal")

        if overexposure:
            reason_tags.append("overexposure_warning")

        out.append(
            ClusterExposureAssessment(
                cluster_id=cluster_id,
                symbols=tuple(seen_syms),
                leader_symbol=leader_symbol,
                follower_symbols=tuple(follower_symbols),
                leader_score=float(leader_score),
                cluster_size=int(cluster_size),
                correlated_candidate_count=int(correlated),
                cluster_mfe_mean=float(cluster_mfe_mean),
                cluster_mae_mean=float(cluster_mae_mean),
                leader_outperformed_followers=bool(leader_outperformed),
                overexposure_warning=bool(overexposure),
                suggested_cluster_action=str(action),
                reason_tags=tuple(reason_tags),
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------------
# Top-level report builder
# ---------------------------------------------------------------------------
def _build_top_strategy_validation_symbols(
    samples: Sequence[StrategyValidationSample],
    *,
    primary_window: str = STRATEGY_VALIDATION_PRIMARY_WINDOW,
    limit: int = 10,
) -> tuple[dict[str, Any], ...]:
    """Top-N symbols ordered by primary-window MFE.

    The brief asks for ``top_strategy_validation_symbols`` on the
    daily report. We surface the top MFE candidates because that is
    the most informative summary of what the runtime thought looked
    like a "demon coin" lead.
    """
    enriched: list[tuple[float, dict[str, Any]]] = []
    for s in samples:
        mfe = _mfe_for_window(s, primary_window)
        enriched.append(
            (
                mfe,
                {
                    "symbol": str(s.symbol),
                    "opportunity_id": str(s.opportunity_id),
                    "strategy_mode": str(s.strategy_mode),
                    "candidate_stage": str(s.candidate_stage),
                    "tail_label": str(s.tail_label),
                    "opportunity_score": float(s.opportunity_score),
                    "early_tail_score": float(s.early_tail_score),
                    "mfe": float(mfe),
                    "mae": float(_mae_for_window(s, primary_window)),
                },
            )
        )
    enriched.sort(key=lambda r: -r[0])
    return tuple(row for _, row in enriched[: int(limit)])


def _flag_findings(
    samples: Sequence[StrategyValidationSample],
    *,
    by_stage: Mapping[str, CandidateStageValidationStats],
    by_mode: Mapping[str, StrategyModeValidationStats],
) -> tuple[str, ...]:
    """Heuristic findings the daily report surfaces verbatim.

    The brief mandates two specific findings:

      - late / blowoff with a high ``fake_breakout_rate`` should be
        reported;
      - early with a high ``strong_tail_rate`` should be reported.

    Plus a third, derived from the safety boundary:

      - ``dumped`` stage MUST NOT be interpreted as a long; if any
        ``dumped`` sample is present, surface that count so a human
        reviewer can audit.
    """
    flags: list[str] = []
    high_fake_breakout = 0.20
    high_strong_tail = 0.20
    for stage in ("late", "blowoff"):
        s = by_stage.get(stage)
        if s is None:
            continue
        if s.sample_count >= 1 and s.fake_breakout_rate >= high_fake_breakout:
            flags.append(
                f"{stage}_high_fake_breakout_rate="
                f"{s.fake_breakout_rate:.3f}"
            )
    early = by_stage.get("early")
    if (
        early is not None
        and early.sample_count >= 1
        and early.strong_tail_rate >= high_strong_tail
    ):
        flags.append(
            f"early_high_strong_tail_rate={early.strong_tail_rate:.3f}"
        )
    dumped = by_stage.get("dumped")
    if dumped is not None and dumped.sample_count >= 1:
        flags.append(
            "dumped_stage_observed="
            f"{dumped.sample_count}; not_a_long_opportunity"
        )
    # Sanity flag - a high reject_count but high observe missed_tail
    # rate signals the runtime may be too conservative on rejections.
    reject_stats = by_mode.get("reject")
    observe_stats = by_mode.get("observe")
    if (
        observe_stats is not None
        and observe_stats.sample_count >= 1
        and observe_stats.missed_tail_rate >= 0.20
    ):
        flags.append(
            f"observe_high_missed_tail_rate="
            f"{observe_stats.missed_tail_rate:.3f}"
        )
    if reject_stats is not None and reject_stats.sample_count >= 1:
        flags.append(
            f"reject_cohort_observed_count={reject_stats.sample_count}"
        )
    return tuple(flags)


def build_strategy_validation_report(
    samples: Iterable[StrategyValidationSample],
    *,
    report_id: str,
    generated_at_ms: int = 0,
    primary_window: str = STRATEGY_VALIDATION_PRIMARY_WINDOW,
    overexposure_warning_threshold: int = (
        DEFAULT_OVEREXPOSURE_WARNING_THRESHOLD
    ),
    top_symbol_limit: int = 10,
    strategy_version: str = "phase_11c_1c_a.strategy.v1",
    scoring_version: str = "phase_11c_1c_a.scoring.v1",
    risk_config_version: str = "phase_11c_1c_a.risk_config.v1",
    state_machine_version: str = "phase_11c_1c_a.state_machine.v1",
    schema_version: str = STRATEGY_VALIDATION_SCHEMA_VERSION,
) -> StrategyValidationReport:
    """Build the top-level :class:`StrategyValidationReport`.

    When ``samples`` is empty, the function returns a well-formed
    report with ``sample_count=0`` and every aggregate filled in
    with the canonical empty-cohort defaults so the daily-report
    section can render "Strategy Validation Lab v0 - empty report
    (no samples in this window)" without ambiguity.
    """
    samples_list = list(samples)
    by_strategy_mode = aggregate_by_strategy_mode(
        samples_list, primary_window=primary_window
    )
    by_candidate_stage = aggregate_by_candidate_stage(
        samples_list, primary_window=primary_window
    )
    by_opp_bucket = aggregate_by_opportunity_score_bucket(
        samples_list, primary_window=primary_window
    )
    by_ets_bucket = aggregate_by_early_tail_score_bucket(
        samples_list, primary_window=primary_window
    )
    distribution = aggregate_tail_label_distribution(samples_list)
    cluster_leader = evaluate_cluster_leader_performance(
        samples_list, primary_window=primary_window
    )
    cluster_exposure = assess_cluster_exposure(
        samples_list,
        primary_window=primary_window,
        overexposure_warning_threshold=overexposure_warning_threshold,
    )
    top_symbols = _build_top_strategy_validation_symbols(
        samples_list, primary_window=primary_window, limit=top_symbol_limit
    )
    flagged = _flag_findings(
        samples_list, by_stage=by_candidate_stage, by_mode=by_strategy_mode
    )
    return StrategyValidationReport(
        report_id=str(report_id),
        generated_at_ms=int(generated_at_ms),
        sample_count=len(samples_list),
        by_strategy_mode=by_strategy_mode,
        by_candidate_stage=by_candidate_stage,
        by_opportunity_score_bucket=by_opp_bucket,
        by_early_tail_score_bucket=by_ets_bucket,
        tail_label_distribution=distribution,
        cluster_leader_validation=cluster_leader,
        cluster_exposure_assessments=cluster_exposure,
        top_strategy_validation_symbols=top_symbols,
        flagged_findings=flagged,
        strategy_version=str(strategy_version),
        scoring_version=str(scoring_version),
        risk_config_version=str(risk_config_version),
        state_machine_version=str(state_machine_version),
        schema_version=str(schema_version),
    )


__all__ = [
    # Constants
    "STRATEGY_VALIDATION_SCHEMA_VERSION",
    "KNOWN_STRATEGY_VALIDATION_SCHEMA_VERSIONS",
    "STRATEGY_VALIDATION_VERSION",
    "STRATEGY_VALIDATION_SOURCE_PHASE",
    "STRATEGY_VALIDATION_PRIMARY_WINDOW",
    "STRATEGY_VALIDATION_TRACKING_WINDOWS",
    "OPPORTUNITY_SCORE_BUCKETS",
    "OPPORTUNITY_SCORE_BUCKET_LABELS",
    "EARLY_TAIL_SCORE_BUCKETS",
    "EARLY_TAIL_SCORE_BUCKET_LABELS",
    "CLUSTER_ACTIONS",
    "DEFAULT_OVEREXPOSURE_WARNING_THRESHOLD",
    # Bucket helpers
    "opportunity_score_bucket_for",
    "early_tail_score_bucket_for",
    # Models
    "StrategyValidationSample",
    "StrategyValidationWindowStats",
    "StrategyModeValidationStats",
    "CandidateStageValidationStats",
    "OpportunityScoreBucketStats",
    "EarlyTailScoreBucketStats",
    "TailLabelDistribution",
    "ClusterLeaderValidationStats",
    "ClusterExposureAssessment",
    "StrategyValidationReport",
    # Pure functions
    "build_strategy_validation_sample",
    "aggregate_by_strategy_mode",
    "aggregate_by_candidate_stage",
    "aggregate_by_opportunity_score_bucket",
    "aggregate_by_early_tail_score_bucket",
    "aggregate_tail_label_distribution",
    "evaluate_cluster_leader_performance",
    "assess_cluster_exposure",
    "build_strategy_validation_report",
]
