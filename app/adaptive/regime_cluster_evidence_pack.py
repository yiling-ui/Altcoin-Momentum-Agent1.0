"""Phase 11C.1C-C-B-B-B-B - Regime & Cluster Cohort Evidence Pack v0.

The Regime & Cluster Cohort Evidence Pack v0 is a **paper / report /
evidence-only** compression layer that aggregates the Phase
11C.1C-C-B-B-A :class:`StrategyValidationDataset` (and, transitively,
the Phase 11C.1C-C-B-A :class:`StrategyValidationReport` cohort
stats and the Phase 11C.1C-C-B-B-B-A :class:`PaperAlphaGateReport`
verdict) into a structured cohort summary across the dimensions:

  - ``market_regime``
  - ``cluster_id``
  - ``cluster_leader_vs_follower``
  - ``candidate_stage``
  - ``strategy_mode``
  - ``opportunity_score_bucket``
  - ``early_tail_score_bucket``

The pack answers the eight cohort questions called out by the
Phase 11C.1C-C-B-B-B-B brief:

  1. Which Regimes are more likely to produce
     ``strong_tail`` / ``reached_3r`` / ``reached_5r``?
  2. Which Regimes are more likely to produce
     ``fake_breakout`` / ``late_chase_failure``?
  3. Is the ``cluster_leader`` materially better than its
     followers on the same cohort?
  4. Does the high ``opportunity_score_bucket`` actually
     out-perform the low bucket?
  5. Does the high ``early_tail_score_bucket`` actually
     out-perform the low bucket?
  6. Do ``follow`` / ``pullback`` / ``observe`` / ``reject``
     downstream outcomes match expectations?
  7. Which state combinations deserve continued paper
     observation?
  8. Which state combinations must be down-weighted or rejected?

Phase 11C.1C-C-B-B-B-B boundary
-------------------------------

This module:

  - is paper / virtual ONLY;
  - is contracts + pure functions; nothing here triggers a real
    trade, opens a position, modifies a stop-loss / target price /
    leverage, the Risk Engine, or the Execution FSM;
  - the per-cohort status is **descriptive only** - one of
    ``INSUFFICIENT_SAMPLE`` / ``OBSERVE_ONLY`` / ``WARNING`` /
    ``EVIDENCE_SIGNAL`` - and is NEVER an input to a trade-decision
    pipeline;
  - is **NOT** a new strategy, **NOT** a trading module, **NOT** AI
    Learning, **NOT** automatic parameter optimisation, **NOT**
    reinforcement learning, **NOT** the complete Strategy
    Validation Lab follow-up, **NOT** Phase 12;
  - tags every payload with a ``schema_version`` field so old
    payloads without the v0 sub-block remain replayable verbatim;
  - degrades safely when an upstream field is missing; e.g. a
    dataset record without an attached ``market_regime`` is
    classified as ``"unknown"`` instead of raising;
  - never auto-relaxes thresholds when sample counts are low; thin
    cohorts are emitted as ``INSUFFICIENT_SAMPLE`` together with
    explicit ``insufficient_sample_reasons`` entries.

The runtime that consumes this module
(:class:`app.adaptive.strategy_validation_runtime.StrategyValidationRuntime`)
emits two new typed events:

  - ``REGIME_CLUSTER_EVIDENCE_PACK_GENERATED``
  - ``REGIME_CLUSTER_COHORT_SUMMARY_GENERATED``

Every event payload includes ``report_id``, ``dataset_id``,
``timestamp``, ``evidence_pack_status`` (a top-level descriptive
roll-up), ``strategy_version``, ``scoring_version``,
``risk_config_version``, ``state_machine_version``, and
``schema_version`` so Reflection / Replay can group on them
without parsing free-form audit dicts.
"""

from __future__ import annotations

import statistics
from typing import Any, Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.adaptive.strategy_validation import (
    EARLY_TAIL_SCORE_BUCKET_LABELS,
    OPPORTUNITY_SCORE_BUCKET_LABELS,
    early_tail_score_bucket_for,
    opportunity_score_bucket_for,
)
from app.adaptive.strategy_validation_dataset import (
    StrategyValidationDataset,
    StrategyValidationDatasetRecord,
)


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Schema version stamp written on every Phase 11C.1C-C-B-B-B-B
#: payload. A future PR that changes the payload shape MUST bump
#: this label.
REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION: str = (
    "phase_11c_1c_c_b_b_b_b.regime_cluster_evidence_pack.v1"
)
KNOWN_REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSIONS: tuple[str, ...] = (
    REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION,
)

#: Phase 11C.1C-C-B-B-B-B canonical version labels. Carried on every
#: event payload so Reflection / Replay can group on them.
REGIME_CLUSTER_EVIDENCE_VERSION: str = (
    "phase_11c_1c_c_b_b_b_b.regime_cluster_evidence_pack.v1"
)
REGIME_CLUSTER_EVIDENCE_SOURCE_PHASE: str = (
    "phase_11c_1c_c_b_b_b_b_regime_cluster_evidence_pack_v0"
)

#: Sentinel used for records whose ``market_regime`` is not
#: attached by the upstream runtime. The brief's "safely degrade"
#: rule treats unknown regime as a labelled cohort - the cohort
#: still appears in the report but is annotated so a human reviewer
#: can tell the input was incomplete.
UNKNOWN_REGIME: str = "unknown"

#: Sentinel used for records whose ``cluster_id`` field is missing.
UNKNOWN_CLUSTER: str = "unknown"

#: Cohort dimensions the evidence pack v0 surfaces.
REGIME_CLUSTER_COHORT_DIMENSIONS: tuple[str, ...] = (
    "market_regime",
    "cluster_id",
    "cluster_leader_vs_follower",
    "candidate_stage",
    "strategy_mode",
    "opportunity_score_bucket",
    "early_tail_score_bucket",
)

#: Tail labels whose presence implies a "completed" sample
#: (i.e. the Phase 11C.1C-C-A primary window has resolved). Mirrors
#: :data:`app.adaptive.strategy_validation_dataset.COMPLETED_TAIL_LABELS`
#: but redeclared locally to avoid an import cycle.
COMPLETED_TAIL_LABELS: tuple[str, ...] = (
    "strong_tail",
    "moderate_tail",
    "weak_tail",
    "fake_breakout",
    "missed_tail",
    "late_chase_failure",
    "dumped",
)


# ---------------------------------------------------------------------------
# Default thresholds
# ---------------------------------------------------------------------------
#: Minimum total samples required for the pack as a whole to leave
#: ``INSUFFICIENT_SAMPLE`` and consider per-cohort signals.
DEFAULT_MIN_TOTAL_SAMPLES: int = 20

#: Minimum number of completed tail labels required for the pack as
#: a whole to leave ``INSUFFICIENT_SAMPLE``.
DEFAULT_MIN_COMPLETED_TAIL_LABELS: int = 10

#: Minimum number of samples per cohort row required to consider
#: that cohort row's signals / warnings. Below this threshold the
#: cohort is annotated ``INSUFFICIENT_SAMPLE``.
DEFAULT_MIN_COHORT_SAMPLES: int = 5

#: Minimum strong-tail rate that promotes a regime / score-bucket
#: cohort to ``EVIDENCE_SIGNAL`` (descriptive only; does not
#: authorise a real trade).
DEFAULT_STRONG_TAIL_SIGNAL_RATE: float = 0.30

#: Minimum reached_3r rate that promotes a cohort to
#: ``EVIDENCE_SIGNAL``.
DEFAULT_REACHED_3R_SIGNAL_RATE: float = 0.20

#: Minimum reached_5r rate that promotes a cohort to
#: ``EVIDENCE_SIGNAL``.
DEFAULT_REACHED_5R_SIGNAL_RATE: float = 0.10

#: Threshold above which a cohort's ``fake_breakout_rate`` raises a
#: ``regime_fake_breakout_warning`` / ``strategy_mode_risk_warning``.
DEFAULT_FAKE_BREAKOUT_WARNING_RATE: float = 0.30

#: Threshold above which a cohort's ``missed_tail_rate`` raises a
#: ``stage_missed_tail_warning``.
DEFAULT_MISSED_TAIL_WARNING_RATE: float = 0.20

#: Threshold above which a cohort's ``late_chase_failure_rate``
#: raises a ``stage_late_chase_failure_warning``.
DEFAULT_LATE_CHASE_FAILURE_WARNING_RATE: float = 0.20

#: Minimum absolute advantage (leader's strong_tail_rate or
#: median_mfe over follower's) for a ``cluster_leader_signal``.
DEFAULT_LEADER_PREFERENCE_ADVANTAGE: float = 0.10

#: Minimum absolute advantage of high-bucket vs low-bucket
#: strong_tail_rate / reached_3r_rate for a ``score_bucket_signal``.
DEFAULT_HIGH_BUCKET_ADVANTAGE: float = 0.10


#: Buckets considered "high" / "low" when comparing high-grade vs.
#: low-grade opportunity_score / early_tail_score cohorts. Mirrors
#: the Phase 11C.1C-C-B-B-B-A vocabulary.
HIGH_OPPORTUNITY_SCORE_BUCKETS: tuple[str, ...] = ("65-79", "80-100")
LOW_OPPORTUNITY_SCORE_BUCKETS: tuple[str, ...] = ("0-49", "50-64")

HIGH_EARLY_TAIL_SCORE_BUCKETS: tuple[str, ...] = ("50-74", "75-100")
LOW_EARLY_TAIL_SCORE_BUCKETS: tuple[str, ...] = ("0-24", "25-49")


# ---------------------------------------------------------------------------
# Status vocabulary
# ---------------------------------------------------------------------------
class RegimeClusterEvidencePackStatus:
    """Allowed Phase 11C.1C-C-B-B-B-B status labels.

    Implemented as plain string constants on a holder class (not an
    Enum) so payload dictionaries from
    :func:`export_regime_cluster_evidence_payload` round-trip
    through JSON without losing the literal.

    Every label is **descriptive only** - none authorises a real
    trade. The Risk Engine remains the single trade-decision gate.
    """

    INSUFFICIENT_SAMPLE: str = "INSUFFICIENT_SAMPLE"
    OBSERVE_ONLY: str = "OBSERVE_ONLY"
    WARNING: str = "WARNING"
    EVIDENCE_SIGNAL: str = "EVIDENCE_SIGNAL"

    ALL: tuple[str, ...] = (
        "INSUFFICIENT_SAMPLE",
        "OBSERVE_ONLY",
        "WARNING",
        "EVIDENCE_SIGNAL",
    )


REGIME_CLUSTER_EVIDENCE_PACK_STATUSES: tuple[str, ...] = (
    RegimeClusterEvidencePackStatus.ALL
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return float(default)
    return f


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _median_or_zero(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    try:
        return float(statistics.median(values))
    except statistics.StatisticsError:
        return 0.0


# ---------------------------------------------------------------------------
# RegimeClusterCohortKey - identity for one cohort row
# ---------------------------------------------------------------------------
class RegimeClusterCohortKey(BaseModel):
    """Identity for a single cohort row.

    A key is the (dimension, value) pair the row aggregates over,
    e.g. ``("market_regime", "MEME_RISK_ON")`` or
    ``("cluster_id", "USDT")``. Frozen + JSON-safe.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: str
    value: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "dimension": str(self.dimension),
            "value": str(self.value),
        }


# ---------------------------------------------------------------------------
# RegimeClusterCohortStats - shared per-cohort numerics
# ---------------------------------------------------------------------------
class RegimeClusterCohortStats(BaseModel):
    """Shared per-cohort statistics produced by every summary.

    Brief contract: every cohort row exposes:

      - ``sample_count`` / ``completed_tail_label_count``
      - ``strong_tail_count`` / ``moderate_tail_count`` /
        ``weak_tail_count``
      - ``fake_breakout_count`` / ``missed_tail_count`` /
        ``late_chase_failure_count``
      - ``reached_3r_count`` / ``reached_5r_count``
      - ``strong_tail_rate`` / ``fake_breakout_rate`` /
        ``reached_3r_rate`` / ``reached_5r_rate``
      - ``median_mfe`` / ``median_mae``
      - ``status`` (descriptive: ``INSUFFICIENT_SAMPLE`` /
        ``OBSERVE_ONLY`` / ``WARNING`` / ``EVIDENCE_SIGNAL``)
      - ``signals`` / ``warnings`` (descriptive label tuples)
      - ``notes`` (free-form annotations, e.g. "thin cohort
        n=3<5")

    Every field is paper / report only; nothing on this object
    authorises a real trade.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: RegimeClusterCohortKey

    sample_count: int = 0
    completed_tail_label_count: int = 0

    strong_tail_count: int = 0
    moderate_tail_count: int = 0
    weak_tail_count: int = 0
    fake_breakout_count: int = 0
    missed_tail_count: int = 0
    late_chase_failure_count: int = 0
    reached_3r_count: int = 0
    reached_5r_count: int = 0

    strong_tail_rate: float = 0.0
    fake_breakout_rate: float = 0.0
    missed_tail_rate: float = 0.0
    late_chase_failure_rate: float = 0.0
    reached_3r_rate: float = 0.0
    reached_5r_rate: float = 0.0

    median_mfe: float = 0.0
    median_mae: float = 0.0

    status: str = RegimeClusterEvidencePackStatus.INSUFFICIENT_SAMPLE
    signals: tuple[str, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    notes: tuple[str, ...] = Field(default_factory=tuple)
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def _check_status(cls, value: str) -> str:
        text = str(value).strip()
        if text not in REGIME_CLUSTER_EVIDENCE_PACK_STATUSES:
            return RegimeClusterEvidencePackStatus.INSUFFICIENT_SAMPLE
        return text

    def to_payload(self) -> dict[str, Any]:
        return {
            "key": self.key.to_payload(),
            "sample_count": int(self.sample_count),
            "completed_tail_label_count": int(self.completed_tail_label_count),
            "strong_tail_count": int(self.strong_tail_count),
            "moderate_tail_count": int(self.moderate_tail_count),
            "weak_tail_count": int(self.weak_tail_count),
            "fake_breakout_count": int(self.fake_breakout_count),
            "missed_tail_count": int(self.missed_tail_count),
            "late_chase_failure_count": int(self.late_chase_failure_count),
            "reached_3r_count": int(self.reached_3r_count),
            "reached_5r_count": int(self.reached_5r_count),
            "strong_tail_rate": float(self.strong_tail_rate),
            "fake_breakout_rate": float(self.fake_breakout_rate),
            "missed_tail_rate": float(self.missed_tail_rate),
            "late_chase_failure_rate": float(self.late_chase_failure_rate),
            "reached_3r_rate": float(self.reached_3r_rate),
            "reached_5r_rate": float(self.reached_5r_rate),
            "median_mfe": float(self.median_mfe),
            "median_mae": float(self.median_mae),
            "status": str(self.status),
            "signals": list(self.signals),
            "warnings": list(self.warnings),
            "notes": list(self.notes),
            "extra": dict(self.extra),
        }


# ---------------------------------------------------------------------------
# RegimeClusterEvidenceRecord - normalised row consumed by the cohort
# builders. Mirrors a :class:`StrategyValidationDatasetRecord` plus an
# optional augmented ``market_regime`` field (see "safely degrade"
# requirement in the brief).
# ---------------------------------------------------------------------------
class RegimeClusterEvidenceRecord(BaseModel):
    """Normalised per-sample row consumed by the cohort builders."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_id: str
    symbol: str = ""
    market_regime: str = UNKNOWN_REGIME
    cluster_id: str = UNKNOWN_CLUSTER
    cluster_leader: str | None = None
    is_cluster_leader: bool = False
    candidate_stage: str = "early"
    strategy_mode: str = "observe"
    opportunity_score: float = 0.0
    early_tail_score: float = 0.0
    opportunity_score_bucket: str = ""
    early_tail_score_bucket: str = ""
    tail_label: str = "unresolved"
    mfe_5m: float = 0.0
    mae_5m: float = 0.0
    reached_3r: bool = False
    reached_5r: bool = False
    fake_breakout: bool = False
    missed_tail: bool = False
    late_chase_failure: bool = False

    @field_validator("market_regime")
    @classmethod
    def _check_regime(cls, value: str) -> str:
        text = str(value or "").strip()
        return text or UNKNOWN_REGIME

    @field_validator("cluster_id")
    @classmethod
    def _check_cluster(cls, value: str) -> str:
        text = str(value or "").strip()
        return text or UNKNOWN_CLUSTER

    def to_payload(self) -> dict[str, Any]:
        return {
            "opportunity_id": str(self.opportunity_id),
            "symbol": str(self.symbol),
            "market_regime": str(self.market_regime),
            "cluster_id": str(self.cluster_id),
            "cluster_leader": (
                str(self.cluster_leader)
                if self.cluster_leader is not None
                else None
            ),
            "is_cluster_leader": bool(self.is_cluster_leader),
            "candidate_stage": str(self.candidate_stage),
            "strategy_mode": str(self.strategy_mode),
            "opportunity_score": float(self.opportunity_score),
            "early_tail_score": float(self.early_tail_score),
            "opportunity_score_bucket": str(self.opportunity_score_bucket),
            "early_tail_score_bucket": str(self.early_tail_score_bucket),
            "tail_label": str(self.tail_label),
            "mfe_5m": float(self.mfe_5m),
            "mae_5m": float(self.mae_5m),
            "reached_3r": bool(self.reached_3r),
            "reached_5r": bool(self.reached_5r),
            "fake_breakout": bool(self.fake_breakout),
            "missed_tail": bool(self.missed_tail),
            "late_chase_failure": bool(self.late_chase_failure),
        }


# ---------------------------------------------------------------------------
# RegimeClusterEvidenceInput
# ---------------------------------------------------------------------------
class RegimeClusterEvidenceInput(BaseModel):
    """Everything the evidence-pack builder consumes.

    Built by :func:`build_regime_cluster_evidence_input` from a
    Phase 11C.1C-C-B-B-A :class:`StrategyValidationDataset` (and an
    optional ``regime_by_opportunity`` mapping that the runtime
    attaches when it has the regime information). A future PR may
    extend the input with additional auxiliary fields - the v0
    schema deliberately keeps the surface narrow.

    The input is **pure**: building one does NOT read a private API
    or authorise a real trade.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str
    dataset_id: str = ""
    sample_count: int = 0
    completed_tail_label_count: int = 0
    records: tuple[RegimeClusterEvidenceRecord, ...] = Field(
        default_factory=tuple
    )
    paper_alpha_gate_status: str = ""
    quality_gate_status: str = ""
    strategy_version: str = "phase_11c_1c_a.strategy.v1"
    scoring_version: str = "phase_11c_1c_a.scoring.v1"
    risk_config_version: str = "phase_11c_1c_a.risk_config.v1"
    state_machine_version: str = "phase_11c_1c_a.state_machine.v1"
    schema_version: str = REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "report_id": str(self.report_id),
            "dataset_id": str(self.dataset_id),
            "sample_count": int(self.sample_count),
            "completed_tail_label_count": int(
                self.completed_tail_label_count
            ),
            "records": [r.to_payload() for r in self.records],
            "paper_alpha_gate_status": str(self.paper_alpha_gate_status),
            "quality_gate_status": str(self.quality_gate_status),
            "strategy_version": str(self.strategy_version),
            "scoring_version": str(self.scoring_version),
            "risk_config_version": str(self.risk_config_version),
            "state_machine_version": str(self.state_machine_version),
            "schema_version": str(self.schema_version),
        }


# ---------------------------------------------------------------------------
# Per-summary value objects
# ---------------------------------------------------------------------------
class RegimeCohortSummary(BaseModel):
    """Per-``market_regime`` cohort summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rows: tuple[RegimeClusterCohortStats, ...] = Field(default_factory=tuple)
    schema_version: str = REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "rows": [r.to_payload() for r in self.rows],
            "schema_version": str(self.schema_version),
        }


class ClusterCohortSummary(BaseModel):
    """Per-``cluster_id`` cohort summary + leader-vs-follower
    breakdowns.

    The leader-vs-follower breakdown is carried as a parallel tuple
    of cohort rows (``leader_vs_follower_rows``) so a downstream
    auditor can compare leader / follower outcomes against the
    cluster-level row without joining tables.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    rows: tuple[RegimeClusterCohortStats, ...] = Field(default_factory=tuple)
    leader_vs_follower_rows: tuple[
        RegimeClusterCohortStats, ...
    ] = Field(default_factory=tuple)
    schema_version: str = REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "rows": [r.to_payload() for r in self.rows],
            "leader_vs_follower_rows": [
                r.to_payload() for r in self.leader_vs_follower_rows
            ],
            "schema_version": str(self.schema_version),
        }


class ScoreBucketSummary(BaseModel):
    """Per-bucket cohort summary for both score families.

    ``opportunity_score_rows`` aggregates over
    :data:`OPPORTUNITY_SCORE_BUCKET_LABELS`;
    ``early_tail_score_rows`` aggregates over
    :data:`EARLY_TAIL_SCORE_BUCKET_LABELS`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_score_rows: tuple[
        RegimeClusterCohortStats, ...
    ] = Field(default_factory=tuple)
    early_tail_score_rows: tuple[
        RegimeClusterCohortStats, ...
    ] = Field(default_factory=tuple)
    schema_version: str = REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "opportunity_score_rows": [
                r.to_payload() for r in self.opportunity_score_rows
            ],
            "early_tail_score_rows": [
                r.to_payload() for r in self.early_tail_score_rows
            ],
            "schema_version": str(self.schema_version),
        }


class StageOutcomeSummary(BaseModel):
    """Per-``candidate_stage`` cohort summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rows: tuple[RegimeClusterCohortStats, ...] = Field(default_factory=tuple)
    schema_version: str = REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "rows": [r.to_payload() for r in self.rows],
            "schema_version": str(self.schema_version),
        }


class StrategyModeOutcomeSummary(BaseModel):
    """Per-``strategy_mode`` cohort summary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rows: tuple[RegimeClusterCohortStats, ...] = Field(default_factory=tuple)
    schema_version: str = REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "rows": [r.to_payload() for r in self.rows],
            "schema_version": str(self.schema_version),
        }


# ---------------------------------------------------------------------------
# RegimeClusterEvidencePack - top-level container
# ---------------------------------------------------------------------------
class RegimeClusterEvidencePack(BaseModel):
    """Top-level Regime & Cluster Cohort Evidence Pack v0 report.

    Bundles the five summaries above + the upstream Paper Alpha
    Gate verdict + a small ``warnings`` /
    ``insufficient_sample_reasons`` block. Carries ``report_id``,
    ``dataset_id``, ``evaluated_at``, ``schema_version``, and the
    full version block so the artefact is fully replayable.

    Phase 11C.1C-C-B-B-B-B boundary - the pack is paper / report
    only. Generating one does NOT authorise any real trade and
    NEVER bumps a Phase 1 safety flag.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str
    dataset_id: str = ""
    evaluated_at: int = 0

    sample_count: int = 0
    completed_tail_label_count: int = 0

    status: str = RegimeClusterEvidencePackStatus.INSUFFICIENT_SAMPLE
    insufficient_sample_reasons: tuple[str, ...] = Field(
        default_factory=tuple
    )
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    signals: tuple[str, ...] = Field(default_factory=tuple)

    regime_cohort_summary: RegimeCohortSummary = Field(
        default_factory=RegimeCohortSummary
    )
    cluster_cohort_summary: ClusterCohortSummary = Field(
        default_factory=ClusterCohortSummary
    )
    score_bucket_summary: ScoreBucketSummary = Field(
        default_factory=ScoreBucketSummary
    )
    stage_outcome_summary: StageOutcomeSummary = Field(
        default_factory=StageOutcomeSummary
    )
    strategy_mode_outcome_summary: StrategyModeOutcomeSummary = Field(
        default_factory=StrategyModeOutcomeSummary
    )

    paper_alpha_gate_status: str = ""
    quality_gate_status: str = ""

    strategy_version: str = "phase_11c_1c_a.strategy.v1"
    scoring_version: str = "phase_11c_1c_a.scoring.v1"
    risk_config_version: str = "phase_11c_1c_a.risk_config.v1"
    state_machine_version: str = "phase_11c_1c_a.state_machine.v1"
    schema_version: str = REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION

    @field_validator("status")
    @classmethod
    def _check_status(cls, value: str) -> str:
        text = str(value).strip()
        if text not in REGIME_CLUSTER_EVIDENCE_PACK_STATUSES:
            raise ValueError(
                "status must be one of "
                f"{REGIME_CLUSTER_EVIDENCE_PACK_STATUSES}; got {value!r}"
            )
        return text

    def to_payload(self) -> dict[str, Any]:
        return {
            "report_id": str(self.report_id),
            "dataset_id": str(self.dataset_id),
            "evaluated_at": int(self.evaluated_at),
            "sample_count": int(self.sample_count),
            "completed_tail_label_count": int(
                self.completed_tail_label_count
            ),
            "status": str(self.status),
            "insufficient_sample_reasons": list(
                self.insufficient_sample_reasons
            ),
            "warnings": list(self.warnings),
            "signals": list(self.signals),
            "regime_cohort_summary": (
                self.regime_cohort_summary.to_payload()
            ),
            "cluster_cohort_summary": (
                self.cluster_cohort_summary.to_payload()
            ),
            "score_bucket_summary": (
                self.score_bucket_summary.to_payload()
            ),
            "stage_outcome_summary": (
                self.stage_outcome_summary.to_payload()
            ),
            "strategy_mode_outcome_summary": (
                self.strategy_mode_outcome_summary.to_payload()
            ),
            "paper_alpha_gate_status": str(self.paper_alpha_gate_status),
            "quality_gate_status": str(self.quality_gate_status),
            "strategy_version": str(self.strategy_version),
            "scoring_version": str(self.scoring_version),
            "risk_config_version": str(self.risk_config_version),
            "state_machine_version": str(self.state_machine_version),
            "schema_version": str(self.schema_version),
        }


# ---------------------------------------------------------------------------
# Builder: RegimeClusterEvidenceInput
# ---------------------------------------------------------------------------
def _record_from_dataset_row(
    row: StrategyValidationDatasetRecord,
    *,
    market_regime: str,
) -> RegimeClusterEvidenceRecord:
    opp_score = _safe_float(row.opportunity_score, 0.0)
    ets_score = _safe_float(row.early_tail_score, 0.0)
    is_leader = bool(
        row.cluster_leader is not None
        and row.symbol
        and str(row.symbol) == str(row.cluster_leader)
    )
    return RegimeClusterEvidenceRecord(
        opportunity_id=str(row.opportunity_id),
        symbol=str(row.symbol or ""),
        market_regime=str(market_regime or UNKNOWN_REGIME),
        cluster_id=str(row.cluster_id or UNKNOWN_CLUSTER),
        cluster_leader=(
            str(row.cluster_leader)
            if row.cluster_leader is not None
            else None
        ),
        is_cluster_leader=is_leader,
        candidate_stage=str(row.candidate_stage or "early"),
        strategy_mode=str(row.strategy_mode or "observe"),
        opportunity_score=opp_score,
        early_tail_score=ets_score,
        opportunity_score_bucket=opportunity_score_bucket_for(opp_score),
        early_tail_score_bucket=early_tail_score_bucket_for(ets_score),
        tail_label=str(row.tail_label or "unresolved"),
        mfe_5m=_safe_float(row.mfe_5m, 0.0),
        mae_5m=_safe_float(row.mae_5m, 0.0),
        reached_3r=bool(row.reached_3r),
        reached_5r=bool(row.reached_5r),
        fake_breakout=bool(row.fake_breakout),
        missed_tail=bool(row.missed_tail),
        late_chase_failure=bool(row.late_chase_failure),
    )


def build_regime_cluster_evidence_input(
    *,
    dataset: StrategyValidationDataset | None = None,
    regime_by_opportunity: Mapping[str, str] | None = None,
    paper_alpha_gate_status: str = "",
    quality_gate_status: str = "",
    report_id: str | None = None,
) -> RegimeClusterEvidenceInput:
    """Build a :class:`RegimeClusterEvidenceInput` from the upstream
    Phase 11C.1C-C-B-B-A artefacts.

    The function is **pure**: no I/O, no clock read, no
    ``EventRepository.append_event`` call. Missing inputs default to
    safe zeros so the pack can still emit an
    ``INSUFFICIENT_SAMPLE`` verdict on a thin / empty dataset.

    ``regime_by_opportunity`` is an optional mapping that the
    runtime supplies when it has the ``market_regime`` per
    opportunity. Records whose opportunity_id is missing from the
    map default to :data:`UNKNOWN_REGIME` - the brief's "safely
    degrade" rule.
    """
    rid = str(
        report_id or (dataset.report_id if dataset is not None else "")
    )
    sample_count = 0
    completed = 0
    records: list[RegimeClusterEvidenceRecord] = []
    dataset_id = ""
    strategy_version = "phase_11c_1c_a.strategy.v1"
    scoring_version = "phase_11c_1c_a.scoring.v1"
    risk_config_version = "phase_11c_1c_a.risk_config.v1"
    state_machine_version = "phase_11c_1c_a.state_machine.v1"

    regime_map = dict(regime_by_opportunity or {})

    if dataset is not None:
        dataset_id = str(dataset.report_id)
        strategy_version = str(dataset.strategy_version)
        scoring_version = str(dataset.scoring_version)
        risk_config_version = str(dataset.risk_config_version)
        state_machine_version = str(dataset.state_machine_version)
        for row in dataset.records:
            opp_id = str(row.opportunity_id or "")
            regime = regime_map.get(opp_id) or UNKNOWN_REGIME
            try:
                rec = _record_from_dataset_row(row, market_regime=regime)
            except Exception:  # pragma: no cover - defensive
                continue
            records.append(rec)
        sample_count = int(dataset.summary.record_count)
        completed = int(dataset.summary.completed_tail_label_count)

    return RegimeClusterEvidenceInput(
        report_id=rid,
        dataset_id=dataset_id,
        sample_count=int(sample_count),
        completed_tail_label_count=int(completed),
        records=tuple(records),
        paper_alpha_gate_status=str(paper_alpha_gate_status or ""),
        quality_gate_status=str(quality_gate_status or ""),
        strategy_version=str(strategy_version),
        scoring_version=str(scoring_version),
        risk_config_version=str(risk_config_version),
        state_machine_version=str(state_machine_version),
    )


# ---------------------------------------------------------------------------
# Pure cohort builders
# ---------------------------------------------------------------------------
def _stats_for_records(
    *,
    key: RegimeClusterCohortKey,
    records: Sequence[RegimeClusterEvidenceRecord],
    min_cohort_samples: int,
    strong_tail_signal_rate: float,
    reached_3r_signal_rate: float,
    reached_5r_signal_rate: float,
    fake_breakout_warning_rate: float,
    missed_tail_warning_rate: float,
    late_chase_failure_warning_rate: float,
    extra: dict[str, Any] | None = None,
) -> RegimeClusterCohortStats:
    """Compute :class:`RegimeClusterCohortStats` for one cohort.

    Pure function. Records with ``tail_label='unresolved'`` are
    counted in ``sample_count`` but not in
    ``completed_tail_label_count``.
    """
    n = len(records)
    completed = sum(
        1 for r in records if r.tail_label in COMPLETED_TAIL_LABELS
    )
    strong = sum(1 for r in records if r.tail_label == "strong_tail")
    moderate = sum(1 for r in records if r.tail_label == "moderate_tail")
    weak = sum(1 for r in records if r.tail_label == "weak_tail")
    fake = sum(1 for r in records if r.fake_breakout)
    missed = sum(1 for r in records if r.missed_tail)
    late_fail = sum(1 for r in records if r.late_chase_failure)
    p3r = sum(1 for r in records if r.reached_3r)
    p5r = sum(1 for r in records if r.reached_5r)

    mfes = [_safe_float(r.mfe_5m, 0.0) for r in records]
    maes = [_safe_float(r.mae_5m, 0.0) for r in records]

    strong_rate = _rate(strong, n)
    fake_rate = _rate(fake, n)
    missed_rate = _rate(missed, n)
    late_rate = _rate(late_fail, n)
    p3r_rate = _rate(p3r, n)
    p5r_rate = _rate(p5r, n)

    notes: list[str] = []
    signals: list[str] = []
    warnings: list[str] = []

    if n < int(min_cohort_samples):
        notes.append(
            f"thin_cohort n={n}<{int(min_cohort_samples)}"
        )
        status = RegimeClusterEvidencePackStatus.INSUFFICIENT_SAMPLE
    else:
        # Positive signals.
        if strong_rate >= float(strong_tail_signal_rate):
            signals.append("strong_tail_rate_signal")
        if p3r_rate >= float(reached_3r_signal_rate):
            signals.append("reached_3r_rate_signal")
        if p5r_rate >= float(reached_5r_signal_rate):
            signals.append("reached_5r_rate_signal")
        # Warnings.
        if fake_rate >= float(fake_breakout_warning_rate):
            warnings.append("fake_breakout_warning")
        if missed_rate >= float(missed_tail_warning_rate):
            warnings.append("missed_tail_warning")
        if late_rate >= float(late_chase_failure_warning_rate):
            warnings.append("late_chase_failure_warning")
        # Status decision: warnings dominate signals.
        if warnings:
            status = RegimeClusterEvidencePackStatus.WARNING
        elif signals:
            status = RegimeClusterEvidencePackStatus.EVIDENCE_SIGNAL
        else:
            status = RegimeClusterEvidencePackStatus.OBSERVE_ONLY

    return RegimeClusterCohortStats(
        key=key,
        sample_count=n,
        completed_tail_label_count=completed,
        strong_tail_count=strong,
        moderate_tail_count=moderate,
        weak_tail_count=weak,
        fake_breakout_count=fake,
        missed_tail_count=missed,
        late_chase_failure_count=late_fail,
        reached_3r_count=p3r,
        reached_5r_count=p5r,
        strong_tail_rate=strong_rate,
        fake_breakout_rate=fake_rate,
        missed_tail_rate=missed_rate,
        late_chase_failure_rate=late_rate,
        reached_3r_rate=p3r_rate,
        reached_5r_rate=p5r_rate,
        median_mfe=_median_or_zero(mfes),
        median_mae=_median_or_zero(maes),
        status=status,
        signals=tuple(signals),
        warnings=tuple(warnings),
        notes=tuple(notes),
        extra=dict(extra or {}),
    )


def build_regime_cohort_summary(
    gate_input: RegimeClusterEvidenceInput,
    *,
    min_cohort_samples: int = DEFAULT_MIN_COHORT_SAMPLES,
    strong_tail_signal_rate: float = DEFAULT_STRONG_TAIL_SIGNAL_RATE,
    reached_3r_signal_rate: float = DEFAULT_REACHED_3R_SIGNAL_RATE,
    reached_5r_signal_rate: float = DEFAULT_REACHED_5R_SIGNAL_RATE,
    fake_breakout_warning_rate: float = (
        DEFAULT_FAKE_BREAKOUT_WARNING_RATE
    ),
    missed_tail_warning_rate: float = DEFAULT_MISSED_TAIL_WARNING_RATE,
    late_chase_failure_warning_rate: float = (
        DEFAULT_LATE_CHASE_FAILURE_WARNING_RATE
    ),
) -> RegimeCohortSummary:
    """Build the per-``market_regime`` cohort summary.

    Pure function. Records with an unknown / missing
    ``market_regime`` are aggregated under :data:`UNKNOWN_REGIME`
    with an explanatory note - the brief's "safely degrade" rule.
    """
    by_regime: dict[str, list[RegimeClusterEvidenceRecord]] = {}
    for r in gate_input.records:
        by_regime.setdefault(str(r.market_regime), []).append(r)
    rows: list[RegimeClusterCohortStats] = []
    for regime, recs in sorted(by_regime.items()):
        key = RegimeClusterCohortKey(
            dimension="market_regime", value=str(regime)
        )
        extra: dict[str, Any] = {}
        if regime == UNKNOWN_REGIME:
            extra["regime_field_missing"] = True
        stats = _stats_for_records(
            key=key,
            records=recs,
            min_cohort_samples=int(min_cohort_samples),
            strong_tail_signal_rate=float(strong_tail_signal_rate),
            reached_3r_signal_rate=float(reached_3r_signal_rate),
            reached_5r_signal_rate=float(reached_5r_signal_rate),
            fake_breakout_warning_rate=float(fake_breakout_warning_rate),
            missed_tail_warning_rate=float(missed_tail_warning_rate),
            late_chase_failure_warning_rate=float(
                late_chase_failure_warning_rate
            ),
            extra=extra,
        )
        rows.append(stats)
    return RegimeCohortSummary(rows=tuple(rows))


def build_cluster_cohort_summary(
    gate_input: RegimeClusterEvidenceInput,
    *,
    min_cohort_samples: int = DEFAULT_MIN_COHORT_SAMPLES,
    strong_tail_signal_rate: float = DEFAULT_STRONG_TAIL_SIGNAL_RATE,
    reached_3r_signal_rate: float = DEFAULT_REACHED_3R_SIGNAL_RATE,
    reached_5r_signal_rate: float = DEFAULT_REACHED_5R_SIGNAL_RATE,
    fake_breakout_warning_rate: float = (
        DEFAULT_FAKE_BREAKOUT_WARNING_RATE
    ),
    missed_tail_warning_rate: float = DEFAULT_MISSED_TAIL_WARNING_RATE,
    late_chase_failure_warning_rate: float = (
        DEFAULT_LATE_CHASE_FAILURE_WARNING_RATE
    ),
    leader_preference_advantage: float = (
        DEFAULT_LEADER_PREFERENCE_ADVANTAGE
    ),
) -> ClusterCohortSummary:
    """Build the per-``cluster_id`` cohort summary + the
    leader-vs-follower breakdown.

    Pure function. The leader-vs-follower rows are emitted as a
    parallel tuple so a downstream auditor can compare leader /
    follower outcomes without joining tables.
    """
    by_cluster: dict[str, list[RegimeClusterEvidenceRecord]] = {}
    for r in gate_input.records:
        by_cluster.setdefault(str(r.cluster_id), []).append(r)

    cluster_rows: list[RegimeClusterCohortStats] = []
    leader_follower_rows: list[RegimeClusterCohortStats] = []
    for cluster_id, recs in sorted(by_cluster.items()):
        key = RegimeClusterCohortKey(
            dimension="cluster_id", value=str(cluster_id)
        )
        extra: dict[str, Any] = {}
        if cluster_id == UNKNOWN_CLUSTER:
            extra["cluster_field_missing"] = True
        cluster_stats = _stats_for_records(
            key=key,
            records=recs,
            min_cohort_samples=int(min_cohort_samples),
            strong_tail_signal_rate=float(strong_tail_signal_rate),
            reached_3r_signal_rate=float(reached_3r_signal_rate),
            reached_5r_signal_rate=float(reached_5r_signal_rate),
            fake_breakout_warning_rate=float(fake_breakout_warning_rate),
            missed_tail_warning_rate=float(missed_tail_warning_rate),
            late_chase_failure_warning_rate=float(
                late_chase_failure_warning_rate
            ),
            extra=extra,
        )
        cluster_rows.append(cluster_stats)

        leaders = [r for r in recs if r.is_cluster_leader]
        followers = [r for r in recs if not r.is_cluster_leader]
        leader_key = RegimeClusterCohortKey(
            dimension="cluster_leader_vs_follower",
            value=f"{cluster_id}::leader",
        )
        follower_key = RegimeClusterCohortKey(
            dimension="cluster_leader_vs_follower",
            value=f"{cluster_id}::follower",
        )
        leader_stats = _stats_for_records(
            key=leader_key,
            records=leaders,
            min_cohort_samples=int(min_cohort_samples),
            strong_tail_signal_rate=float(strong_tail_signal_rate),
            reached_3r_signal_rate=float(reached_3r_signal_rate),
            reached_5r_signal_rate=float(reached_5r_signal_rate),
            fake_breakout_warning_rate=float(fake_breakout_warning_rate),
            missed_tail_warning_rate=float(missed_tail_warning_rate),
            late_chase_failure_warning_rate=float(
                late_chase_failure_warning_rate
            ),
            extra={"role": "leader", "cluster_id": str(cluster_id)},
        )
        follower_stats = _stats_for_records(
            key=follower_key,
            records=followers,
            min_cohort_samples=int(min_cohort_samples),
            strong_tail_signal_rate=float(strong_tail_signal_rate),
            reached_3r_signal_rate=float(reached_3r_signal_rate),
            reached_5r_signal_rate=float(reached_5r_signal_rate),
            fake_breakout_warning_rate=float(fake_breakout_warning_rate),
            missed_tail_warning_rate=float(missed_tail_warning_rate),
            late_chase_failure_warning_rate=float(
                late_chase_failure_warning_rate
            ),
            extra={"role": "follower", "cluster_id": str(cluster_id)},
        )
        # Surface an explicit ``cluster_leader_signal`` when the
        # leader is materially better than the followers on a
        # non-thin cohort.
        if (
            leader_stats.status
            != RegimeClusterEvidencePackStatus.INSUFFICIENT_SAMPLE
            and follower_stats.status
            != RegimeClusterEvidencePackStatus.INSUFFICIENT_SAMPLE
        ):
            advantage_strong = (
                leader_stats.strong_tail_rate
                - follower_stats.strong_tail_rate
            )
            advantage_mfe = (
                leader_stats.median_mfe - follower_stats.median_mfe
            )
            if advantage_strong >= float(
                leader_preference_advantage
            ) or advantage_mfe >= float(leader_preference_advantage):
                # Reconstruct leader_stats with an additional signal
                # by building a new instance (frozen Pydantic
                # objects).
                leader_stats = leader_stats.model_copy(
                    update={
                        "signals": tuple(leader_stats.signals)
                        + ("cluster_leader_signal",),
                        "status": (
                            RegimeClusterEvidencePackStatus.EVIDENCE_SIGNAL
                            if not leader_stats.warnings
                            else leader_stats.status
                        ),
                        "extra": {
                            **dict(leader_stats.extra),
                            "advantage_strong_tail_rate": float(
                                advantage_strong
                            ),
                            "advantage_median_mfe": float(advantage_mfe),
                        },
                    }
                )
        leader_follower_rows.append(leader_stats)
        leader_follower_rows.append(follower_stats)

    return ClusterCohortSummary(
        rows=tuple(cluster_rows),
        leader_vs_follower_rows=tuple(leader_follower_rows),
    )


def build_score_bucket_summary(
    gate_input: RegimeClusterEvidenceInput,
    *,
    min_cohort_samples: int = DEFAULT_MIN_COHORT_SAMPLES,
    strong_tail_signal_rate: float = DEFAULT_STRONG_TAIL_SIGNAL_RATE,
    reached_3r_signal_rate: float = DEFAULT_REACHED_3R_SIGNAL_RATE,
    reached_5r_signal_rate: float = DEFAULT_REACHED_5R_SIGNAL_RATE,
    fake_breakout_warning_rate: float = (
        DEFAULT_FAKE_BREAKOUT_WARNING_RATE
    ),
    missed_tail_warning_rate: float = DEFAULT_MISSED_TAIL_WARNING_RATE,
    late_chase_failure_warning_rate: float = (
        DEFAULT_LATE_CHASE_FAILURE_WARNING_RATE
    ),
    high_bucket_advantage: float = DEFAULT_HIGH_BUCKET_ADVANTAGE,
) -> ScoreBucketSummary:
    """Build the per-``opportunity_score_bucket`` and
    per-``early_tail_score_bucket`` cohort summary.

    Pure function. When the high-grade buckets materially
    out-perform the low-grade buckets on a non-thin cohort, the
    affected high-bucket rows raise a ``score_bucket_signal``
    (descriptive only).
    """
    by_opp: dict[str, list[RegimeClusterEvidenceRecord]] = {}
    by_ets: dict[str, list[RegimeClusterEvidenceRecord]] = {}
    for r in gate_input.records:
        by_opp.setdefault(str(r.opportunity_score_bucket), []).append(r)
        by_ets.setdefault(str(r.early_tail_score_bucket), []).append(r)

    def _build_family_rows(
        by_bucket: Mapping[str, Sequence[RegimeClusterEvidenceRecord]],
        *,
        labels: Sequence[str],
        high_buckets: Sequence[str],
        low_buckets: Sequence[str],
        family_dimension: str,
    ) -> list[RegimeClusterCohortStats]:
        rows: list[RegimeClusterCohortStats] = []
        # Always emit canonical labels (possibly empty) so a stable
        # report layout holds even on thin runs.
        seen: set[str] = set()
        for label in labels:
            recs = list(by_bucket.get(label, ()))
            seen.add(label)
            key = RegimeClusterCohortKey(
                dimension=family_dimension, value=str(label)
            )
            stats = _stats_for_records(
                key=key,
                records=recs,
                min_cohort_samples=int(min_cohort_samples),
                strong_tail_signal_rate=float(strong_tail_signal_rate),
                reached_3r_signal_rate=float(reached_3r_signal_rate),
                reached_5r_signal_rate=float(reached_5r_signal_rate),
                fake_breakout_warning_rate=float(
                    fake_breakout_warning_rate
                ),
                missed_tail_warning_rate=float(missed_tail_warning_rate),
                late_chase_failure_warning_rate=float(
                    late_chase_failure_warning_rate
                ),
                extra={
                    "is_high_bucket": label in high_buckets,
                    "is_low_bucket": label in low_buckets,
                },
            )
            rows.append(stats)
        # Carry through any non-canonical bucket the caller still
        # wants surfaced (defensive, for forward-compat).
        for label, recs in by_bucket.items():
            if label in seen:
                continue
            key = RegimeClusterCohortKey(
                dimension=family_dimension, value=str(label)
            )
            stats = _stats_for_records(
                key=key,
                records=list(recs),
                min_cohort_samples=int(min_cohort_samples),
                strong_tail_signal_rate=float(strong_tail_signal_rate),
                reached_3r_signal_rate=float(reached_3r_signal_rate),
                reached_5r_signal_rate=float(reached_5r_signal_rate),
                fake_breakout_warning_rate=float(
                    fake_breakout_warning_rate
                ),
                missed_tail_warning_rate=float(missed_tail_warning_rate),
                late_chase_failure_warning_rate=float(
                    late_chase_failure_warning_rate
                ),
                extra={
                    "is_high_bucket": False,
                    "is_low_bucket": False,
                },
            )
            rows.append(stats)
        return rows

    opp_rows = _build_family_rows(
        by_opp,
        labels=OPPORTUNITY_SCORE_BUCKET_LABELS,
        high_buckets=HIGH_OPPORTUNITY_SCORE_BUCKETS,
        low_buckets=LOW_OPPORTUNITY_SCORE_BUCKETS,
        family_dimension="opportunity_score_bucket",
    )
    ets_rows = _build_family_rows(
        by_ets,
        labels=EARLY_TAIL_SCORE_BUCKET_LABELS,
        high_buckets=HIGH_EARLY_TAIL_SCORE_BUCKETS,
        low_buckets=LOW_EARLY_TAIL_SCORE_BUCKETS,
        family_dimension="early_tail_score_bucket",
    )

    def _annotate_high_vs_low(
        rows: list[RegimeClusterCohortStats],
        *,
        high_buckets: Sequence[str],
        low_buckets: Sequence[str],
    ) -> list[RegimeClusterCohortStats]:
        # Compute aggregate high vs low strong_tail_rate.
        high_n = 0
        low_n = 0
        high_strong_w = 0.0
        low_strong_w = 0.0
        high_p3r_w = 0.0
        low_p3r_w = 0.0
        for r in rows:
            label = str(r.key.value)
            n = int(r.sample_count)
            if n < int(min_cohort_samples):
                continue
            if label in high_buckets:
                high_n += n
                high_strong_w += float(r.strong_tail_rate) * n
                high_p3r_w += float(r.reached_3r_rate) * n
            elif label in low_buckets:
                low_n += n
                low_strong_w += float(r.strong_tail_rate) * n
                low_p3r_w += float(r.reached_3r_rate) * n
        if high_n <= 0 or low_n <= 0:
            return rows
        avg_high_strong = high_strong_w / high_n
        avg_low_strong = low_strong_w / low_n
        avg_high_p3r = high_p3r_w / high_n
        avg_low_p3r = low_p3r_w / low_n
        adv_strong = avg_high_strong - avg_low_strong
        adv_p3r = avg_high_p3r - avg_low_p3r
        if adv_strong < float(high_bucket_advantage) and adv_p3r < float(
            high_bucket_advantage
        ):
            return rows
        # Annotate the high-bucket rows.
        out: list[RegimeClusterCohortStats] = []
        for r in rows:
            label = str(r.key.value)
            if (
                label in high_buckets
                and int(r.sample_count) >= int(min_cohort_samples)
            ):
                out.append(
                    r.model_copy(
                        update={
                            "signals": tuple(r.signals)
                            + ("score_bucket_signal",),
                            "status": (
                                RegimeClusterEvidencePackStatus.EVIDENCE_SIGNAL
                                if not r.warnings
                                else r.status
                            ),
                            "extra": {
                                **dict(r.extra),
                                "advantage_strong_tail_rate": float(
                                    adv_strong
                                ),
                                "advantage_reached_3r_rate": float(adv_p3r),
                            },
                        }
                    )
                )
            else:
                out.append(r)
        return out

    opp_rows = _annotate_high_vs_low(
        opp_rows,
        high_buckets=HIGH_OPPORTUNITY_SCORE_BUCKETS,
        low_buckets=LOW_OPPORTUNITY_SCORE_BUCKETS,
    )
    ets_rows = _annotate_high_vs_low(
        ets_rows,
        high_buckets=HIGH_EARLY_TAIL_SCORE_BUCKETS,
        low_buckets=LOW_EARLY_TAIL_SCORE_BUCKETS,
    )

    return ScoreBucketSummary(
        opportunity_score_rows=tuple(opp_rows),
        early_tail_score_rows=tuple(ets_rows),
    )


def build_stage_outcome_summary(
    gate_input: RegimeClusterEvidenceInput,
    *,
    min_cohort_samples: int = DEFAULT_MIN_COHORT_SAMPLES,
    strong_tail_signal_rate: float = DEFAULT_STRONG_TAIL_SIGNAL_RATE,
    reached_3r_signal_rate: float = DEFAULT_REACHED_3R_SIGNAL_RATE,
    reached_5r_signal_rate: float = DEFAULT_REACHED_5R_SIGNAL_RATE,
    fake_breakout_warning_rate: float = (
        DEFAULT_FAKE_BREAKOUT_WARNING_RATE
    ),
    missed_tail_warning_rate: float = DEFAULT_MISSED_TAIL_WARNING_RATE,
    late_chase_failure_warning_rate: float = (
        DEFAULT_LATE_CHASE_FAILURE_WARNING_RATE
    ),
) -> StageOutcomeSummary:
    """Build the per-``candidate_stage`` cohort summary."""
    by_stage: dict[str, list[RegimeClusterEvidenceRecord]] = {}
    for r in gate_input.records:
        by_stage.setdefault(str(r.candidate_stage), []).append(r)
    canonical = ("early", "mid", "late", "blowoff", "dumped")
    rows: list[RegimeClusterCohortStats] = []
    seen: set[str] = set()
    for stage in canonical:
        seen.add(stage)
        recs = by_stage.get(stage, [])
        key = RegimeClusterCohortKey(
            dimension="candidate_stage", value=str(stage)
        )
        stats = _stats_for_records(
            key=key,
            records=recs,
            min_cohort_samples=int(min_cohort_samples),
            strong_tail_signal_rate=float(strong_tail_signal_rate),
            reached_3r_signal_rate=float(reached_3r_signal_rate),
            reached_5r_signal_rate=float(reached_5r_signal_rate),
            fake_breakout_warning_rate=float(fake_breakout_warning_rate),
            missed_tail_warning_rate=float(missed_tail_warning_rate),
            late_chase_failure_warning_rate=float(
                late_chase_failure_warning_rate
            ),
        )
        rows.append(stats)
    for stage, recs in by_stage.items():
        if stage in seen:
            continue
        key = RegimeClusterCohortKey(
            dimension="candidate_stage", value=str(stage)
        )
        rows.append(
            _stats_for_records(
                key=key,
                records=recs,
                min_cohort_samples=int(min_cohort_samples),
                strong_tail_signal_rate=float(strong_tail_signal_rate),
                reached_3r_signal_rate=float(reached_3r_signal_rate),
                reached_5r_signal_rate=float(reached_5r_signal_rate),
                fake_breakout_warning_rate=float(
                    fake_breakout_warning_rate
                ),
                missed_tail_warning_rate=float(missed_tail_warning_rate),
                late_chase_failure_warning_rate=float(
                    late_chase_failure_warning_rate
                ),
            )
        )
    return StageOutcomeSummary(rows=tuple(rows))


def build_strategy_mode_outcome_summary(
    gate_input: RegimeClusterEvidenceInput,
    *,
    min_cohort_samples: int = DEFAULT_MIN_COHORT_SAMPLES,
    strong_tail_signal_rate: float = DEFAULT_STRONG_TAIL_SIGNAL_RATE,
    reached_3r_signal_rate: float = DEFAULT_REACHED_3R_SIGNAL_RATE,
    reached_5r_signal_rate: float = DEFAULT_REACHED_5R_SIGNAL_RATE,
    fake_breakout_warning_rate: float = (
        DEFAULT_FAKE_BREAKOUT_WARNING_RATE
    ),
    missed_tail_warning_rate: float = DEFAULT_MISSED_TAIL_WARNING_RATE,
    late_chase_failure_warning_rate: float = (
        DEFAULT_LATE_CHASE_FAILURE_WARNING_RATE
    ),
) -> StrategyModeOutcomeSummary:
    """Build the per-``strategy_mode`` cohort summary."""
    by_mode: dict[str, list[RegimeClusterEvidenceRecord]] = {}
    for r in gate_input.records:
        by_mode.setdefault(str(r.strategy_mode), []).append(r)
    canonical = ("follow", "pullback", "observe", "reject")
    rows: list[RegimeClusterCohortStats] = []
    seen: set[str] = set()
    for mode in canonical:
        seen.add(mode)
        recs = by_mode.get(mode, [])
        key = RegimeClusterCohortKey(
            dimension="strategy_mode", value=str(mode)
        )
        stats = _stats_for_records(
            key=key,
            records=recs,
            min_cohort_samples=int(min_cohort_samples),
            strong_tail_signal_rate=float(strong_tail_signal_rate),
            reached_3r_signal_rate=float(reached_3r_signal_rate),
            reached_5r_signal_rate=float(reached_5r_signal_rate),
            fake_breakout_warning_rate=float(fake_breakout_warning_rate),
            missed_tail_warning_rate=float(missed_tail_warning_rate),
            late_chase_failure_warning_rate=float(
                late_chase_failure_warning_rate
            ),
        )
        # ``strategy_mode_risk_warning`` for follow / pullback with
        # high fake_breakout_rate.
        if (
            mode in ("follow", "pullback")
            and stats.status
            != RegimeClusterEvidencePackStatus.INSUFFICIENT_SAMPLE
            and stats.fake_breakout_rate
            >= float(fake_breakout_warning_rate)
        ):
            stats = stats.model_copy(
                update={
                    "warnings": tuple(stats.warnings)
                    + ("strategy_mode_risk_warning",)
                    if "strategy_mode_risk_warning" not in stats.warnings
                    else stats.warnings,
                    "status": RegimeClusterEvidencePackStatus.WARNING,
                }
            )
        rows.append(stats)
    for mode, recs in by_mode.items():
        if mode in seen:
            continue
        key = RegimeClusterCohortKey(
            dimension="strategy_mode", value=str(mode)
        )
        rows.append(
            _stats_for_records(
                key=key,
                records=recs,
                min_cohort_samples=int(min_cohort_samples),
                strong_tail_signal_rate=float(strong_tail_signal_rate),
                reached_3r_signal_rate=float(reached_3r_signal_rate),
                reached_5r_signal_rate=float(reached_5r_signal_rate),
                fake_breakout_warning_rate=float(
                    fake_breakout_warning_rate
                ),
                missed_tail_warning_rate=float(missed_tail_warning_rate),
                late_chase_failure_warning_rate=float(
                    late_chase_failure_warning_rate
                ),
            )
        )
    return StrategyModeOutcomeSummary(rows=tuple(rows))


# ---------------------------------------------------------------------------
# Top-level pack builder
# ---------------------------------------------------------------------------
def _aggregate_signals_and_warnings(
    pack_summaries: Iterable[Iterable[RegimeClusterCohortStats]],
) -> tuple[list[str], list[str]]:
    """Walk every cohort row across every summary; collect the
    union of signals + warnings (deduplicated, order-preserving)."""
    signals: list[str] = []
    warnings: list[str] = []
    seen_signals: set[str] = set()
    seen_warnings: set[str] = set()
    for summary in pack_summaries:
        for row in summary:
            for s in row.signals:
                if s not in seen_signals:
                    seen_signals.add(s)
                    signals.append(s)
            for w in row.warnings:
                if w not in seen_warnings:
                    seen_warnings.add(w)
                    warnings.append(w)
    return signals, warnings


def build_regime_cluster_evidence_pack(
    gate_input: RegimeClusterEvidenceInput,
    *,
    evaluated_at: int = 0,
    min_total_samples: int = DEFAULT_MIN_TOTAL_SAMPLES,
    min_completed_tail_labels: int = DEFAULT_MIN_COMPLETED_TAIL_LABELS,
    min_cohort_samples: int = DEFAULT_MIN_COHORT_SAMPLES,
    strong_tail_signal_rate: float = DEFAULT_STRONG_TAIL_SIGNAL_RATE,
    reached_3r_signal_rate: float = DEFAULT_REACHED_3R_SIGNAL_RATE,
    reached_5r_signal_rate: float = DEFAULT_REACHED_5R_SIGNAL_RATE,
    fake_breakout_warning_rate: float = (
        DEFAULT_FAKE_BREAKOUT_WARNING_RATE
    ),
    missed_tail_warning_rate: float = DEFAULT_MISSED_TAIL_WARNING_RATE,
    late_chase_failure_warning_rate: float = (
        DEFAULT_LATE_CHASE_FAILURE_WARNING_RATE
    ),
    leader_preference_advantage: float = (
        DEFAULT_LEADER_PREFERENCE_ADVANTAGE
    ),
    high_bucket_advantage: float = DEFAULT_HIGH_BUCKET_ADVANTAGE,
) -> RegimeClusterEvidencePack:
    """Build the top-level :class:`RegimeClusterEvidencePack` from a
    :class:`RegimeClusterEvidenceInput`.

    Pure function. The pack is descriptive only; nothing it
    produces authorises a real trade. The Risk Engine remains the
    single trade-decision gate.

    Threshold knobs match the brief's "do not loosen rules on low
    samples" rule: a thin total / completed-tail-label pool yields
    ``INSUFFICIENT_SAMPLE`` and a non-empty
    ``insufficient_sample_reasons`` list.
    """
    sample_count = int(gate_input.sample_count)
    completed = int(gate_input.completed_tail_label_count)

    insufficient_reasons: list[str] = []
    if sample_count < int(min_total_samples):
        insufficient_reasons.append(
            f"sample_count_below_min={sample_count}<{int(min_total_samples)}"
        )
    if completed < int(min_completed_tail_labels):
        insufficient_reasons.append(
            "completed_tail_label_count_below_min="
            f"{completed}<{int(min_completed_tail_labels)}"
        )

    # Build every summary - even when the pack is INSUFFICIENT we
    # still emit the empty-but-well-formed rows so the daily report
    # can render the section.
    regime_summary = build_regime_cohort_summary(
        gate_input,
        min_cohort_samples=int(min_cohort_samples),
        strong_tail_signal_rate=float(strong_tail_signal_rate),
        reached_3r_signal_rate=float(reached_3r_signal_rate),
        reached_5r_signal_rate=float(reached_5r_signal_rate),
        fake_breakout_warning_rate=float(fake_breakout_warning_rate),
        missed_tail_warning_rate=float(missed_tail_warning_rate),
        late_chase_failure_warning_rate=float(
            late_chase_failure_warning_rate
        ),
    )
    cluster_summary = build_cluster_cohort_summary(
        gate_input,
        min_cohort_samples=int(min_cohort_samples),
        strong_tail_signal_rate=float(strong_tail_signal_rate),
        reached_3r_signal_rate=float(reached_3r_signal_rate),
        reached_5r_signal_rate=float(reached_5r_signal_rate),
        fake_breakout_warning_rate=float(fake_breakout_warning_rate),
        missed_tail_warning_rate=float(missed_tail_warning_rate),
        late_chase_failure_warning_rate=float(
            late_chase_failure_warning_rate
        ),
        leader_preference_advantage=float(leader_preference_advantage),
    )
    score_summary = build_score_bucket_summary(
        gate_input,
        min_cohort_samples=int(min_cohort_samples),
        strong_tail_signal_rate=float(strong_tail_signal_rate),
        reached_3r_signal_rate=float(reached_3r_signal_rate),
        reached_5r_signal_rate=float(reached_5r_signal_rate),
        fake_breakout_warning_rate=float(fake_breakout_warning_rate),
        missed_tail_warning_rate=float(missed_tail_warning_rate),
        late_chase_failure_warning_rate=float(
            late_chase_failure_warning_rate
        ),
        high_bucket_advantage=float(high_bucket_advantage),
    )
    stage_summary = build_stage_outcome_summary(
        gate_input,
        min_cohort_samples=int(min_cohort_samples),
        strong_tail_signal_rate=float(strong_tail_signal_rate),
        reached_3r_signal_rate=float(reached_3r_signal_rate),
        reached_5r_signal_rate=float(reached_5r_signal_rate),
        fake_breakout_warning_rate=float(fake_breakout_warning_rate),
        missed_tail_warning_rate=float(missed_tail_warning_rate),
        late_chase_failure_warning_rate=float(
            late_chase_failure_warning_rate
        ),
    )
    mode_summary = build_strategy_mode_outcome_summary(
        gate_input,
        min_cohort_samples=int(min_cohort_samples),
        strong_tail_signal_rate=float(strong_tail_signal_rate),
        reached_3r_signal_rate=float(reached_3r_signal_rate),
        reached_5r_signal_rate=float(reached_5r_signal_rate),
        fake_breakout_warning_rate=float(fake_breakout_warning_rate),
        missed_tail_warning_rate=float(missed_tail_warning_rate),
        late_chase_failure_warning_rate=float(
            late_chase_failure_warning_rate
        ),
    )

    signals, warnings = _aggregate_signals_and_warnings(
        (
            regime_summary.rows,
            cluster_summary.rows,
            cluster_summary.leader_vs_follower_rows,
            score_summary.opportunity_score_rows,
            score_summary.early_tail_score_rows,
            stage_summary.rows,
            mode_summary.rows,
        )
    )

    # Top-level status decision tree:
    #   - INSUFFICIENT_SAMPLE if total / completed below thresholds
    #     (the brief says "low sample cannot produce strong
    #     conclusions");
    #   - WARNING if any cohort raised a warning;
    #   - EVIDENCE_SIGNAL if any cohort raised a positive signal
    #     and no warning fired;
    #   - OBSERVE_ONLY otherwise.
    if insufficient_reasons:
        status = RegimeClusterEvidencePackStatus.INSUFFICIENT_SAMPLE
    elif warnings:
        status = RegimeClusterEvidencePackStatus.WARNING
    elif signals:
        status = RegimeClusterEvidencePackStatus.EVIDENCE_SIGNAL
    else:
        status = RegimeClusterEvidencePackStatus.OBSERVE_ONLY

    return RegimeClusterEvidencePack(
        report_id=str(gate_input.report_id),
        dataset_id=str(gate_input.dataset_id),
        evaluated_at=int(evaluated_at),
        sample_count=sample_count,
        completed_tail_label_count=completed,
        status=status,
        insufficient_sample_reasons=tuple(insufficient_reasons),
        warnings=tuple(warnings),
        signals=tuple(signals),
        regime_cohort_summary=regime_summary,
        cluster_cohort_summary=cluster_summary,
        score_bucket_summary=score_summary,
        stage_outcome_summary=stage_summary,
        strategy_mode_outcome_summary=mode_summary,
        paper_alpha_gate_status=str(gate_input.paper_alpha_gate_status or ""),
        quality_gate_status=str(gate_input.quality_gate_status or ""),
        strategy_version=str(gate_input.strategy_version),
        scoring_version=str(gate_input.scoring_version),
        risk_config_version=str(gate_input.risk_config_version),
        state_machine_version=str(gate_input.state_machine_version),
    )


# ---------------------------------------------------------------------------
# Export / Replay (round-trip)
# ---------------------------------------------------------------------------
def export_regime_cluster_evidence_payload(
    pack: RegimeClusterEvidencePack,
) -> dict[str, Any]:
    """Return a JSON-safe dict for the evidence pack.

    The function is **pure** - it does not write to disk. The
    runner / daily-report builder is responsible for serialising
    the dict to bytes.
    """
    return pack.to_payload()


def _load_cohort_stats(
    payload: Mapping[str, Any] | None,
) -> RegimeClusterCohortStats | None:
    if not isinstance(payload, Mapping):
        return None
    key_payload = payload.get("key") or {}
    if not isinstance(key_payload, Mapping):
        return None
    key = RegimeClusterCohortKey(
        dimension=str(key_payload.get("dimension") or ""),
        value=str(key_payload.get("value") or ""),
    )
    return RegimeClusterCohortStats(
        key=key,
        sample_count=_safe_int(payload.get("sample_count") or 0),
        completed_tail_label_count=_safe_int(
            payload.get("completed_tail_label_count") or 0
        ),
        strong_tail_count=_safe_int(payload.get("strong_tail_count") or 0),
        moderate_tail_count=_safe_int(
            payload.get("moderate_tail_count") or 0
        ),
        weak_tail_count=_safe_int(payload.get("weak_tail_count") or 0),
        fake_breakout_count=_safe_int(
            payload.get("fake_breakout_count") or 0
        ),
        missed_tail_count=_safe_int(payload.get("missed_tail_count") or 0),
        late_chase_failure_count=_safe_int(
            payload.get("late_chase_failure_count") or 0
        ),
        reached_3r_count=_safe_int(payload.get("reached_3r_count") or 0),
        reached_5r_count=_safe_int(payload.get("reached_5r_count") or 0),
        strong_tail_rate=_safe_float(payload.get("strong_tail_rate") or 0.0),
        fake_breakout_rate=_safe_float(
            payload.get("fake_breakout_rate") or 0.0
        ),
        missed_tail_rate=_safe_float(payload.get("missed_tail_rate") or 0.0),
        late_chase_failure_rate=_safe_float(
            payload.get("late_chase_failure_rate") or 0.0
        ),
        reached_3r_rate=_safe_float(payload.get("reached_3r_rate") or 0.0),
        reached_5r_rate=_safe_float(payload.get("reached_5r_rate") or 0.0),
        median_mfe=_safe_float(payload.get("median_mfe") or 0.0),
        median_mae=_safe_float(payload.get("median_mae") or 0.0),
        status=str(
            payload.get("status")
            or RegimeClusterEvidencePackStatus.INSUFFICIENT_SAMPLE
        ),
        signals=tuple(str(s) for s in (payload.get("signals") or ())),
        warnings=tuple(str(s) for s in (payload.get("warnings") or ())),
        notes=tuple(str(s) for s in (payload.get("notes") or ())),
        extra=dict(payload.get("extra") or {}),
    )


def _load_rows(
    payload_rows: Iterable[Mapping[str, Any]] | None,
) -> tuple[RegimeClusterCohortStats, ...]:
    out: list[RegimeClusterCohortStats] = []
    for row in payload_rows or ():
        loaded = _load_cohort_stats(row)
        if loaded is not None:
            out.append(loaded)
    return tuple(out)


def load_regime_cluster_evidence_payload(
    payload: Mapping[str, Any],
) -> RegimeClusterEvidencePack:
    """Reconstruct a :class:`RegimeClusterEvidencePack` from a
    payload produced by
    :func:`export_regime_cluster_evidence_payload`.

    Tolerates payloads from old schema_versions: missing optional
    fields default to v0 defaults so a future PR can extend the
    contract without breaking replay.
    """
    if not isinstance(payload, Mapping):
        raise TypeError(
            "load_regime_cluster_evidence_payload requires a Mapping; "
            f"got {type(payload).__name__}"
        )

    regime_payload = payload.get("regime_cohort_summary") or {}
    cluster_payload = payload.get("cluster_cohort_summary") or {}
    score_payload = payload.get("score_bucket_summary") or {}
    stage_payload = payload.get("stage_outcome_summary") or {}
    mode_payload = payload.get("strategy_mode_outcome_summary") or {}

    return RegimeClusterEvidencePack(
        report_id=str(payload.get("report_id") or ""),
        dataset_id=str(payload.get("dataset_id") or ""),
        evaluated_at=_safe_int(payload.get("evaluated_at") or 0),
        sample_count=_safe_int(payload.get("sample_count") or 0),
        completed_tail_label_count=_safe_int(
            payload.get("completed_tail_label_count") or 0
        ),
        status=str(
            payload.get("status")
            or RegimeClusterEvidencePackStatus.INSUFFICIENT_SAMPLE
        ),
        insufficient_sample_reasons=tuple(
            str(r) for r in (payload.get("insufficient_sample_reasons") or ())
        ),
        warnings=tuple(str(w) for w in (payload.get("warnings") or ())),
        signals=tuple(str(s) for s in (payload.get("signals") or ())),
        regime_cohort_summary=RegimeCohortSummary(
            rows=_load_rows(
                regime_payload.get("rows")
                if isinstance(regime_payload, Mapping)
                else None
            ),
        ),
        cluster_cohort_summary=ClusterCohortSummary(
            rows=_load_rows(
                cluster_payload.get("rows")
                if isinstance(cluster_payload, Mapping)
                else None
            ),
            leader_vs_follower_rows=_load_rows(
                cluster_payload.get("leader_vs_follower_rows")
                if isinstance(cluster_payload, Mapping)
                else None
            ),
        ),
        score_bucket_summary=ScoreBucketSummary(
            opportunity_score_rows=_load_rows(
                score_payload.get("opportunity_score_rows")
                if isinstance(score_payload, Mapping)
                else None
            ),
            early_tail_score_rows=_load_rows(
                score_payload.get("early_tail_score_rows")
                if isinstance(score_payload, Mapping)
                else None
            ),
        ),
        stage_outcome_summary=StageOutcomeSummary(
            rows=_load_rows(
                stage_payload.get("rows")
                if isinstance(stage_payload, Mapping)
                else None
            ),
        ),
        strategy_mode_outcome_summary=StrategyModeOutcomeSummary(
            rows=_load_rows(
                mode_payload.get("rows")
                if isinstance(mode_payload, Mapping)
                else None
            ),
        ),
        paper_alpha_gate_status=str(
            payload.get("paper_alpha_gate_status") or ""
        ),
        quality_gate_status=str(payload.get("quality_gate_status") or ""),
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
        schema_version=str(
            payload.get("schema_version")
            or REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
        ),
    )


__all__ = [
    # Constants
    "REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION",
    "KNOWN_REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSIONS",
    "REGIME_CLUSTER_EVIDENCE_VERSION",
    "REGIME_CLUSTER_EVIDENCE_SOURCE_PHASE",
    "UNKNOWN_REGIME",
    "UNKNOWN_CLUSTER",
    "REGIME_CLUSTER_COHORT_DIMENSIONS",
    "REGIME_CLUSTER_EVIDENCE_PACK_STATUSES",
    "COMPLETED_TAIL_LABELS",
    "DEFAULT_MIN_TOTAL_SAMPLES",
    "DEFAULT_MIN_COMPLETED_TAIL_LABELS",
    "DEFAULT_MIN_COHORT_SAMPLES",
    "DEFAULT_STRONG_TAIL_SIGNAL_RATE",
    "DEFAULT_REACHED_3R_SIGNAL_RATE",
    "DEFAULT_REACHED_5R_SIGNAL_RATE",
    "DEFAULT_FAKE_BREAKOUT_WARNING_RATE",
    "DEFAULT_MISSED_TAIL_WARNING_RATE",
    "DEFAULT_LATE_CHASE_FAILURE_WARNING_RATE",
    "DEFAULT_LEADER_PREFERENCE_ADVANTAGE",
    "DEFAULT_HIGH_BUCKET_ADVANTAGE",
    "HIGH_OPPORTUNITY_SCORE_BUCKETS",
    "LOW_OPPORTUNITY_SCORE_BUCKETS",
    "HIGH_EARLY_TAIL_SCORE_BUCKETS",
    "LOW_EARLY_TAIL_SCORE_BUCKETS",
    # Models
    "RegimeClusterEvidencePackStatus",
    "RegimeClusterCohortKey",
    "RegimeClusterCohortStats",
    "RegimeClusterEvidenceRecord",
    "RegimeClusterEvidenceInput",
    "RegimeCohortSummary",
    "ClusterCohortSummary",
    "ScoreBucketSummary",
    "StageOutcomeSummary",
    "StrategyModeOutcomeSummary",
    "RegimeClusterEvidencePack",
    # Pure functions
    "build_regime_cluster_evidence_input",
    "build_regime_cohort_summary",
    "build_cluster_cohort_summary",
    "build_score_bucket_summary",
    "build_stage_outcome_summary",
    "build_strategy_mode_outcome_summary",
    "build_regime_cluster_evidence_pack",
    "export_regime_cluster_evidence_payload",
    "load_regime_cluster_evidence_payload",
]
