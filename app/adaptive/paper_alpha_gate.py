"""Phase 11C.1C-C-B-B-B-A - Paper Alpha Gate v0.

The Paper Alpha Gate v0 is a **paper / report / evidence-only**
alpha-judgement layer that aggregates the Phase 11C.1C-C-B-B-A
:class:`StrategyValidationDataset` /
:class:`StrategyValidationQualityGateResult` artefacts (and,
transitively, the Phase 11C.1C-C-B-A
:class:`StrategyValidationReport` cohort stats) into a single
descriptive verdict for human review.

The verdict is one of:

  - ``PASS`` - the gate's alpha-evidence checks were all met on a
    trustworthy dataset.
  - ``WARN`` - the gate's alpha-evidence checks were partially met
    or the dataset is borderline; human review required.
  - ``FAIL`` - the gate's alpha-evidence checks were not met on a
    trustworthy dataset.
  - ``INCONCLUSIVE`` - the dataset was too thin / too in-flight /
    failed the Phase 11C.1C-C-B-B-A
    ``validation_quality_gate_status`` to support an alpha-evidence
    verdict.

Phase 11C.1C-C-B-B-B-A boundary
-------------------------------

This module:

  - is paper / virtual ONLY;
  - is contract + pure functions; nothing here triggers a real
    trade, opens a position, modifies a stop-loss, target price,
    leverage, the Risk Engine, or the Execution FSM;
  - the verdict is **descriptive only** - one of
    ``PASS`` / ``WARN`` / ``FAIL`` / ``INCONCLUSIVE`` - and is
    NEVER an input to a trade-decision pipeline;
  - is **NOT** AI Learning, **NOT** automatic parameter
    optimisation, **NOT** reinforcement learning, **NOT** the
    complete Strategy Validation Lab follow-up, **NOT** Phase 12;
  - tags every payload with a ``schema_version`` field so old
    payloads without the v0 sub-block remain replayable verbatim.

The runtime that consumes this module
(:class:`app.adaptive.strategy_validation_runtime.StrategyValidationRuntime`)
emits the four new typed events:

  - ``PAPER_ALPHA_GATE_EVALUATED``
  - ``PAPER_ALPHA_RULE_EVALUATED``
  - ``PAPER_ALPHA_COHORT_EVALUATED``
  - ``PAPER_ALPHA_REPORT_GENERATED``

Every event payload includes ``report_id``, ``dataset_id`` (where
applicable), ``timestamp``, ``gate_status``, ``strategy_version``,
``scoring_version``, ``risk_config_version``,
``state_machine_version``, and ``schema_version`` so Reflection /
Replay can group on them without parsing free-form audit dicts.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.adaptive.strategy_validation import (
    EARLY_TAIL_SCORE_BUCKET_LABELS,
    OPPORTUNITY_SCORE_BUCKET_LABELS,
    StrategyValidationReport,
)
from app.adaptive.strategy_validation_dataset import (
    StrategyValidationDataset,
    StrategyValidationDatasetRecord,
    StrategyValidationQualityGateResult,
)


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Schema version stamp written on every Phase 11C.1C-C-B-B-B-A payload.
#: A future PR that changes the payload shape MUST bump this label.
PAPER_ALPHA_GATE_SCHEMA_VERSION: str = (
    "phase_11c_1c_c_b_b_b_a.paper_alpha_gate.v1"
)
KNOWN_PAPER_ALPHA_GATE_SCHEMA_VERSIONS: tuple[str, ...] = (
    PAPER_ALPHA_GATE_SCHEMA_VERSION,
)

#: Phase 11C.1C-C-B-B-B-A canonical version labels. Carried on every
#: event payload so Reflection / Replay can group on them.
PAPER_ALPHA_GATE_VERSION: str = (
    "phase_11c_1c_c_b_b_b_a.paper_alpha_gate.v1"
)
PAPER_ALPHA_GATE_SOURCE_PHASE: str = (
    "phase_11c_1c_c_b_b_b_a_paper_alpha_gate_v0"
)


# ---------------------------------------------------------------------------
# Status / Cohort vocabulary
# ---------------------------------------------------------------------------
class PaperAlphaGateStatus:
    """Allowed Paper Alpha Gate v0 verdict labels.

    Implemented as plain string constants on a holder class (not an
    Enum) so payload dictionaries from
    :func:`export_paper_alpha_gate_payload` round-trip through JSON
    without losing the ``PASS`` / ``WARN`` / ``FAIL`` /
    ``INCONCLUSIVE`` literal.

    The verdict is **descriptive only** - none of these labels
    authorises a real trade. The Risk Engine remains the single
    trade-decision gate.
    """

    PASS: str = "PASS"
    WARN: str = "WARN"
    FAIL: str = "FAIL"
    INCONCLUSIVE: str = "INCONCLUSIVE"

    ALL: tuple[str, ...] = ("PASS", "WARN", "FAIL", "INCONCLUSIVE")


PAPER_ALPHA_GATE_STATUSES: tuple[str, ...] = PaperAlphaGateStatus.ALL


#: Cohort dimensions the Paper Alpha Gate v0 surfaces. Every value
#: is descriptive; the labels mirror the Phase 11C.1C-C-B-A cohort
#: vocabulary so a human reviewer can cross-reference the gate
#: result with the underlying Strategy Validation Lab v0 report.
PAPER_ALPHA_COHORT_DIMENSIONS: tuple[str, ...] = (
    "strategy_mode",
    "candidate_stage",
    "opportunity_score_bucket",
    "early_tail_score_bucket",
    "cluster_leader_vs_follower",
    "tail_label_distribution",
)


# ---------------------------------------------------------------------------
# Default rule / threshold knobs
# ---------------------------------------------------------------------------
#: Minimum total dataset rows required to attempt a non-INCONCLUSIVE
#: verdict. Below this the gate emits ``INCONCLUSIVE`` because the
#: sample is too thin to support an alpha-evidence claim.
DEFAULT_MIN_TOTAL_SAMPLES: int = 20

#: Minimum number of rows whose ``tail_label`` is one of the
#: completed labels (i.e. not ``unresolved``). Below this the gate
#: emits ``INCONCLUSIVE`` because too many rows are still in-flight.
DEFAULT_MIN_COMPLETED_TAIL_LABELS: int = 10

#: Minimum number of rows in *each* of the high-vs-low score
#: buckets we compare. Below this the per-bucket comparison is
#: skipped (inconclusive on that signal).
DEFAULT_MIN_BUCKET_SAMPLES: int = 5

#: A high-bucket is considered to outperform a low-bucket only when
#: its strong-tail rate (or reached_3r / reached_5r rate) exceeds
#: the low-bucket's by at least this absolute margin.
DEFAULT_HIGH_BUCKET_ADVANTAGE: float = 0.10

#: Threshold (absolute rate) above which the late / blowoff
#: ``fake_breakout`` rate is considered "high enough to flag"; the
#: gate raises a ``late_chase_warning``.
DEFAULT_LATE_CHASE_FAKE_BREAKOUT_RATE: float = 0.30

#: Threshold (absolute rate) above which observe / reject cohorts
#: are considered to have produced "too many strong-tail outcomes
#: that we missed"; the gate raises a ``missed_alpha_warning``.
DEFAULT_MISSED_ALPHA_STRONG_TAIL_RATE: float = 0.20

#: Threshold (absolute rate) above which the follow cohort's
#: ``fake_breakout`` rate is considered to have produced "follow
#: chasing risk"; the gate raises a ``follow_risk_warning``.
DEFAULT_FOLLOW_FAKE_BREAKOUT_RATE: float = 0.30

#: Minimum absolute advantage of leader.strong_tail_rate over
#: follower.strong_tail_rate (or leader_avg_mfe over
#: follower_avg_mfe) for a cluster to count as a
#: ``leader_preference_signal``.
DEFAULT_LEADER_PREFERENCE_ADVANTAGE: float = 0.10


#: Buckets considered "high" / "low" when comparing high-grade vs.
#: low-grade opportunity_score / early_tail_score cohorts.
HIGH_OPPORTUNITY_SCORE_BUCKETS: tuple[str, ...] = ("65-79", "80-100")
LOW_OPPORTUNITY_SCORE_BUCKETS: tuple[str, ...] = ("0-49", "50-64")

HIGH_EARLY_TAIL_SCORE_BUCKETS: tuple[str, ...] = ("50-74", "75-100")
LOW_EARLY_TAIL_SCORE_BUCKETS: tuple[str, ...] = ("0-24", "25-49")


# ---------------------------------------------------------------------------
# PaperAlphaGateRule (definition)
# ---------------------------------------------------------------------------
class PaperAlphaGateRule(BaseModel):
    """One Paper Alpha Gate v0 rule definition.

    A rule is a *named* threshold check the gate evaluates against
    the input. The rules are deterministic: identical inputs ->
    identical results.

    The gate is descriptive; rules NEVER fire side effects, NEVER
    open a position, NEVER modify the Risk Engine, NEVER modify the
    Execution FSM.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    description: str = ""
    threshold: float = 0.0
    severity: str = "info"  # info | warning | block
    schema_version: str = PAPER_ALPHA_GATE_SCHEMA_VERSION

    @field_validator("severity")
    @classmethod
    def _check_severity(cls, value: str) -> str:
        text = str(value).strip().lower()
        if text not in ("info", "warning", "block"):
            return "info"
        return text

    def to_payload(self) -> dict[str, Any]:
        return {
            "rule_id": str(self.rule_id),
            "description": str(self.description),
            "threshold": float(self.threshold),
            "severity": str(self.severity),
            "schema_version": str(self.schema_version),
        }


# ---------------------------------------------------------------------------
# PaperAlphaGateRuleResult (one evaluation outcome)
# ---------------------------------------------------------------------------
class PaperAlphaGateRuleResult(BaseModel):
    """Result of evaluating a single :class:`PaperAlphaGateRule`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    triggered: bool = False
    observed_value: float = 0.0
    threshold: float = 0.0
    severity: str = "info"
    message: str = ""
    schema_version: str = PAPER_ALPHA_GATE_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "rule_id": str(self.rule_id),
            "triggered": bool(self.triggered),
            "observed_value": float(self.observed_value),
            "threshold": float(self.threshold),
            "severity": str(self.severity),
            "message": str(self.message),
            "schema_version": str(self.schema_version),
        }


# ---------------------------------------------------------------------------
# PaperAlphaGateCohortResult (one cohort dimension's outcome)
# ---------------------------------------------------------------------------
class PaperAlphaGateCohortResult(BaseModel):
    """Result of one cohort-dimension evaluation.

    Aggregates the per-bucket / per-mode / per-cluster signal the
    gate observed on a single dimension, plus the descriptive
    verdict label and any raised warnings.

    Paper / report only; nothing on this object authorises a real
    trade.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: str
    sample_count: int = 0
    status: str = PaperAlphaGateStatus.INCONCLUSIVE
    signals: tuple[str, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    notes: tuple[str, ...] = Field(default_factory=tuple)
    metrics: dict[str, Any] = Field(default_factory=dict)
    schema_version: str = PAPER_ALPHA_GATE_SCHEMA_VERSION

    @field_validator("status")
    @classmethod
    def _check_status(cls, value: str) -> str:
        text = str(value).strip()
        if text not in PAPER_ALPHA_GATE_STATUSES:
            return PaperAlphaGateStatus.INCONCLUSIVE
        return text

    def to_payload(self) -> dict[str, Any]:
        return {
            "dimension": str(self.dimension),
            "sample_count": int(self.sample_count),
            "status": str(self.status),
            "signals": list(self.signals),
            "warnings": list(self.warnings),
            "notes": list(self.notes),
            "metrics": dict(self.metrics),
            "schema_version": str(self.schema_version),
        }


# ---------------------------------------------------------------------------
# PaperAlphaGateInput (everything the gate consumes)
# ---------------------------------------------------------------------------
class PaperAlphaGateInput(BaseModel):
    """Everything :func:`evaluate_paper_alpha_gate` consumes.

    Built by :func:`build_paper_alpha_gate_input` from the
    Phase 11C.1C-C-B-B-A
    :class:`StrategyValidationDataset` /
    :class:`StrategyValidationQualityGateResult` artefacts plus the
    transitive Phase 11C.1C-C-B-A
    :class:`StrategyValidationReport` cohort stats.

    Nothing on this object reads a private API or authorises a real
    trade; it is a pure descriptive snapshot.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str
    dataset_id: str = ""
    sample_count: int = 0
    completed_tail_label_count: int = 0
    quality_gate_status: str = ""
    quality_gate_reasons: tuple[str, ...] = Field(default_factory=tuple)
    strategy_mode_counts: dict[str, int] = Field(default_factory=dict)
    candidate_stage_counts: dict[str, int] = Field(default_factory=dict)
    opportunity_score_bucket_counts: dict[str, int] = Field(
        default_factory=dict
    )
    early_tail_score_bucket_counts: dict[str, int] = Field(
        default_factory=dict
    )
    tail_label_counts: dict[str, int] = Field(default_factory=dict)
    # Per-bucket / per-mode / per-cluster cohort stats (read off the
    # Phase 11C.1C-C-B-A report). Each value is a JSON-safe mapping
    # mirroring the cohort stat ``to_payload()`` output so a
    # downstream auditor can replay the gate result without
    # re-reading events.db.
    strategy_mode_stats: dict[str, dict[str, Any]] = Field(
        default_factory=dict
    )
    candidate_stage_stats: dict[str, dict[str, Any]] = Field(
        default_factory=dict
    )
    opportunity_score_bucket_stats: dict[str, dict[str, Any]] = Field(
        default_factory=dict
    )
    early_tail_score_bucket_stats: dict[str, dict[str, Any]] = Field(
        default_factory=dict
    )
    cluster_leader_stats: dict[str, dict[str, Any]] = Field(
        default_factory=dict
    )
    strategy_version: str = "phase_11c_1c_a.strategy.v1"
    scoring_version: str = "phase_11c_1c_a.scoring.v1"
    risk_config_version: str = "phase_11c_1c_a.risk_config.v1"
    state_machine_version: str = "phase_11c_1c_a.state_machine.v1"
    schema_version: str = PAPER_ALPHA_GATE_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "report_id": str(self.report_id),
            "dataset_id": str(self.dataset_id),
            "sample_count": int(self.sample_count),
            "completed_tail_label_count": int(
                self.completed_tail_label_count
            ),
            "quality_gate_status": str(self.quality_gate_status),
            "quality_gate_reasons": list(self.quality_gate_reasons),
            "strategy_mode_counts": {
                k: int(v)
                for k, v in sorted(self.strategy_mode_counts.items())
            },
            "candidate_stage_counts": {
                k: int(v)
                for k, v in sorted(self.candidate_stage_counts.items())
            },
            "opportunity_score_bucket_counts": {
                k: int(v)
                for k, v in sorted(
                    self.opportunity_score_bucket_counts.items()
                )
            },
            "early_tail_score_bucket_counts": {
                k: int(v)
                for k, v in sorted(
                    self.early_tail_score_bucket_counts.items()
                )
            },
            "tail_label_counts": {
                k: int(v) for k, v in sorted(self.tail_label_counts.items())
            },
            "strategy_mode_stats": {
                k: dict(v)
                for k, v in sorted(self.strategy_mode_stats.items())
            },
            "candidate_stage_stats": {
                k: dict(v)
                for k, v in sorted(self.candidate_stage_stats.items())
            },
            "opportunity_score_bucket_stats": {
                k: dict(v)
                for k, v in sorted(
                    self.opportunity_score_bucket_stats.items()
                )
            },
            "early_tail_score_bucket_stats": {
                k: dict(v)
                for k, v in sorted(
                    self.early_tail_score_bucket_stats.items()
                )
            },
            "cluster_leader_stats": {
                k: dict(v)
                for k, v in sorted(self.cluster_leader_stats.items())
            },
            "strategy_version": str(self.strategy_version),
            "scoring_version": str(self.scoring_version),
            "risk_config_version": str(self.risk_config_version),
            "state_machine_version": str(self.state_machine_version),
            "schema_version": str(self.schema_version),
        }


# ---------------------------------------------------------------------------
# PaperAlphaGateReport (top-level container)
# ---------------------------------------------------------------------------
class PaperAlphaGateReport(BaseModel):
    """Top-level Paper Alpha Gate v0 report.

    Carries the descriptive verdict + the per-rule results + the
    per-cohort results + the warnings + the version block. The
    payload form (``to_payload()``) is JSON-safe and round-trippable
    through :func:`export_paper_alpha_gate_payload` /
    :func:`load_paper_alpha_gate_payload`.

    Phase 11C.1C-C-B-B-B-A boundary - the report is paper / report
    only. Generating one does NOT authorise any real trade and
    NEVER bumps a Phase 1 safety flag.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str
    dataset_id: str = ""
    sample_count: int = 0
    quality_gate_status: str = ""
    evaluated_at: int = 0
    gate_status: str = PaperAlphaGateStatus.INCONCLUSIVE
    reasons: tuple[str, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    rule_results: tuple[PaperAlphaGateRuleResult, ...] = Field(
        default_factory=tuple
    )
    cohort_results: tuple[PaperAlphaGateCohortResult, ...] = Field(
        default_factory=tuple
    )
    strategy_version: str = "phase_11c_1c_a.strategy.v1"
    scoring_version: str = "phase_11c_1c_a.scoring.v1"
    risk_config_version: str = "phase_11c_1c_a.risk_config.v1"
    state_machine_version: str = "phase_11c_1c_a.state_machine.v1"
    schema_version: str = PAPER_ALPHA_GATE_SCHEMA_VERSION

    @field_validator("gate_status")
    @classmethod
    def _check_status(cls, value: str) -> str:
        text = str(value).strip()
        if text not in PAPER_ALPHA_GATE_STATUSES:
            raise ValueError(
                "gate_status must be one of "
                f"{PAPER_ALPHA_GATE_STATUSES}; got {value!r}"
            )
        return text

    def to_payload(self) -> dict[str, Any]:
        return {
            "report_id": str(self.report_id),
            "dataset_id": str(self.dataset_id),
            "sample_count": int(self.sample_count),
            "quality_gate_status": str(self.quality_gate_status),
            "evaluated_at": int(self.evaluated_at),
            "gate_status": str(self.gate_status),
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "rule_results": [r.to_payload() for r in self.rule_results],
            "cohort_results": [c.to_payload() for c in self.cohort_results],
            "strategy_version": str(self.strategy_version),
            "scoring_version": str(self.scoring_version),
            "risk_config_version": str(self.risk_config_version),
            "state_machine_version": str(self.state_machine_version),
            "schema_version": str(self.schema_version),
        }


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


def _stat_to_payload(value: Any) -> dict[str, Any]:
    """Coerce a Phase 11C.1C-C-B-A cohort-stat object (or its
    ``to_payload()`` mapping) into a JSON-safe dict."""
    if isinstance(value, Mapping):
        return dict(value)
    payload_fn = getattr(value, "to_payload", None)
    if callable(payload_fn):
        try:
            return dict(payload_fn())
        except Exception:  # pragma: no cover - defensive
            return {}
    return {}


def _aggregate_strategy_mode_counts(
    records: Sequence[StrategyValidationDatasetRecord],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        counts[str(r.strategy_mode)] = counts.get(str(r.strategy_mode), 0) + 1
    return counts


def _aggregate_candidate_stage_counts(
    records: Sequence[StrategyValidationDatasetRecord],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        counts[str(r.candidate_stage)] = (
            counts.get(str(r.candidate_stage), 0) + 1
        )
    return counts


# ---------------------------------------------------------------------------
# Builder: PaperAlphaGateInput
# ---------------------------------------------------------------------------
def build_paper_alpha_gate_input(
    *,
    dataset: StrategyValidationDataset | None = None,
    quality_gate_result: StrategyValidationQualityGateResult | None = None,
    validation_report: StrategyValidationReport | None = None,
    report_id: str | None = None,
) -> PaperAlphaGateInput:
    """Build a :class:`PaperAlphaGateInput` from the upstream
    Phase 11C.1C-C-B-B-A / Phase 11C.1C-C-B-A artefacts.

    The function is **pure**: no I/O, no clock read, no
    ``EventRepository.append_event`` call. Missing inputs default
    to safe zeros so the gate can still emit an ``INCONCLUSIVE``
    verdict on a thin dataset.
    """
    rid = str(
        report_id
        or (dataset.report_id if dataset is not None else "")
        or (
            validation_report.report_id if validation_report is not None
            else ""
        )
    )
    sample_count = 0
    completed = 0
    strategy_mode_counts: dict[str, int] = {}
    candidate_stage_counts: dict[str, int] = {}
    opp_bucket_counts: dict[str, int] = {}
    ets_bucket_counts: dict[str, int] = {}
    tail_label_counts: dict[str, int] = {}
    dataset_id = ""
    strategy_version = "phase_11c_1c_a.strategy.v1"
    scoring_version = "phase_11c_1c_a.scoring.v1"
    risk_config_version = "phase_11c_1c_a.risk_config.v1"
    state_machine_version = "phase_11c_1c_a.state_machine.v1"

    if dataset is not None:
        summary = dataset.summary
        sample_count = int(summary.record_count)
        completed = int(summary.completed_tail_label_count)
        strategy_mode_counts = {
            str(k): int(v) for k, v in summary.strategy_mode_counts.items()
        }
        candidate_stage_counts = {
            str(k): int(v) for k, v in summary.candidate_stage_counts.items()
        }
        opp_bucket_counts = {
            str(k): int(v)
            for k, v in summary.opportunity_score_bucket_counts.items()
        }
        ets_bucket_counts = {
            str(k): int(v)
            for k, v in summary.early_tail_score_bucket_counts.items()
        }
        tail_label_counts = {
            str(k): int(v) for k, v in summary.tail_label_counts.items()
        }
        dataset_id = str(dataset.report_id)
        strategy_version = str(dataset.strategy_version)
        scoring_version = str(dataset.scoring_version)
        risk_config_version = str(dataset.risk_config_version)
        state_machine_version = str(dataset.state_machine_version)

    quality_gate_status = ""
    quality_gate_reasons: tuple[str, ...] = ()
    if quality_gate_result is not None:
        quality_gate_status = str(quality_gate_result.gate_status)
        quality_gate_reasons = tuple(
            str(r) for r in quality_gate_result.reasons
        )

    strategy_mode_stats: dict[str, dict[str, Any]] = {}
    candidate_stage_stats: dict[str, dict[str, Any]] = {}
    opportunity_score_bucket_stats: dict[str, dict[str, Any]] = {}
    early_tail_score_bucket_stats: dict[str, dict[str, Any]] = {}
    cluster_leader_stats: dict[str, dict[str, Any]] = {}
    if validation_report is not None:
        for k, v in validation_report.by_strategy_mode.items():
            strategy_mode_stats[str(k)] = _stat_to_payload(v)
        for k, v in validation_report.by_candidate_stage.items():
            candidate_stage_stats[str(k)] = _stat_to_payload(v)
        for k, v in validation_report.by_opportunity_score_bucket.items():
            opportunity_score_bucket_stats[str(k)] = _stat_to_payload(v)
        for k, v in validation_report.by_early_tail_score_bucket.items():
            early_tail_score_bucket_stats[str(k)] = _stat_to_payload(v)
        for k, v in validation_report.cluster_leader_validation.items():
            cluster_leader_stats[str(k)] = _stat_to_payload(v)
        # Use the report's version block if no dataset was supplied.
        if dataset is None:
            strategy_version = str(validation_report.strategy_version)
            scoring_version = str(validation_report.scoring_version)
            risk_config_version = str(validation_report.risk_config_version)
            state_machine_version = str(
                validation_report.state_machine_version
            )

    return PaperAlphaGateInput(
        report_id=rid,
        dataset_id=str(dataset_id),
        sample_count=int(sample_count),
        completed_tail_label_count=int(completed),
        quality_gate_status=str(quality_gate_status),
        quality_gate_reasons=quality_gate_reasons,
        strategy_mode_counts=strategy_mode_counts,
        candidate_stage_counts=candidate_stage_counts,
        opportunity_score_bucket_counts=opp_bucket_counts,
        early_tail_score_bucket_counts=ets_bucket_counts,
        tail_label_counts=tail_label_counts,
        strategy_mode_stats=strategy_mode_stats,
        candidate_stage_stats=candidate_stage_stats,
        opportunity_score_bucket_stats=opportunity_score_bucket_stats,
        early_tail_score_bucket_stats=early_tail_score_bucket_stats,
        cluster_leader_stats=cluster_leader_stats,
        strategy_version=str(strategy_version),
        scoring_version=str(scoring_version),
        risk_config_version=str(risk_config_version),
        state_machine_version=str(state_machine_version),
    )


# ---------------------------------------------------------------------------
# Per-cohort evaluators (pure)
# ---------------------------------------------------------------------------
def evaluate_strategy_mode_alpha(
    gate_input: PaperAlphaGateInput,
    *,
    follow_fake_breakout_rate: float = DEFAULT_FOLLOW_FAKE_BREAKOUT_RATE,
    missed_alpha_strong_tail_rate: float = (
        DEFAULT_MISSED_ALPHA_STRONG_TAIL_RATE
    ),
    min_bucket_samples: int = DEFAULT_MIN_BUCKET_SAMPLES,
) -> PaperAlphaGateCohortResult:
    """Evaluate the per-strategy_mode signals.

    Pure function. Surfaces:

      - ``follow_risk_warning`` when ``follow.fake_breakout_rate`` is
        above ``follow_fake_breakout_rate`` on a non-thin cohort;
      - ``missed_alpha_warning`` when the observe / reject cohorts
        have a strong-tail rate above
        ``missed_alpha_strong_tail_rate`` on a non-thin cohort.

    The status hierarchy:

      - ``INCONCLUSIVE`` if every relevant cohort is too thin to
        decide;
      - ``WARN`` if any warning fires;
      - ``PASS`` only when the follow cohort has produced a
        strong-tail rate above 0.0 and no warning fires.

    Paper / report only; nothing here authorises a real trade.
    """
    signals: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    metrics: dict[str, Any] = {}

    follow_stats = gate_input.strategy_mode_stats.get("follow") or {}
    pullback_stats = gate_input.strategy_mode_stats.get("pullback") or {}
    observe_stats = gate_input.strategy_mode_stats.get("observe") or {}
    reject_stats = gate_input.strategy_mode_stats.get("reject") or {}

    follow_n = _safe_int(follow_stats.get("sample_count", 0))
    pullback_n = _safe_int(pullback_stats.get("sample_count", 0))
    observe_n = _safe_int(observe_stats.get("sample_count", 0))
    reject_n = _safe_int(reject_stats.get("sample_count", 0))
    total_n = follow_n + pullback_n + observe_n + reject_n

    follow_fake = _safe_float(follow_stats.get("fake_breakout_rate", 0.0))
    follow_strong = _safe_float(follow_stats.get("strong_tail_rate", 0.0))
    observe_strong = _safe_float(observe_stats.get("strong_tail_rate", 0.0))
    reject_strong = _safe_float(reject_stats.get("strong_tail_rate", 0.0))
    pullback_strong = _safe_float(pullback_stats.get("strong_tail_rate", 0.0))

    metrics.update(
        {
            "follow_sample_count": follow_n,
            "follow_fake_breakout_rate": follow_fake,
            "follow_strong_tail_rate": follow_strong,
            "pullback_sample_count": pullback_n,
            "pullback_strong_tail_rate": pullback_strong,
            "observe_sample_count": observe_n,
            "observe_strong_tail_rate": observe_strong,
            "reject_sample_count": reject_n,
            "reject_strong_tail_rate": reject_strong,
            "follow_fake_breakout_rate_threshold": float(
                follow_fake_breakout_rate
            ),
            "missed_alpha_strong_tail_rate_threshold": float(
                missed_alpha_strong_tail_rate
            ),
        }
    )

    # Follow risk: high fake_breakout_rate inside a non-thin follow
    # cohort.
    if follow_n >= int(min_bucket_samples):
        if follow_fake >= float(follow_fake_breakout_rate):
            warnings.append("follow_risk_warning")
            notes.append(
                f"follow.fake_breakout_rate={follow_fake:.3f} "
                f">= threshold={float(follow_fake_breakout_rate):.3f}"
            )
        else:
            signals.append("follow_safe_signal")
    else:
        notes.append(
            f"follow_cohort_too_thin n={follow_n}<{int(min_bucket_samples)}"
        )

    # Missed alpha: observe / reject cohorts with high strong-tail
    # rate. A non-thin cohort is required to fire.
    for mode_name, stats_n, stats_strong in (
        ("observe", observe_n, observe_strong),
        ("reject", reject_n, reject_strong),
    ):
        if stats_n >= int(min_bucket_samples):
            if stats_strong >= float(missed_alpha_strong_tail_rate):
                warnings.append("missed_alpha_warning")
                notes.append(
                    f"{mode_name}.strong_tail_rate={stats_strong:.3f} "
                    f">= threshold="
                    f"{float(missed_alpha_strong_tail_rate):.3f}"
                )
        else:
            notes.append(
                f"{mode_name}_cohort_too_thin n={stats_n}"
                f"<{int(min_bucket_samples)}"
            )

    # Status decision.
    if total_n < int(min_bucket_samples):
        status = PaperAlphaGateStatus.INCONCLUSIVE
    elif warnings:
        status = PaperAlphaGateStatus.WARN
    elif follow_n >= int(min_bucket_samples) and follow_strong > 0.0:
        status = PaperAlphaGateStatus.PASS
        signals.append("follow_strong_tail_present_signal")
    else:
        status = PaperAlphaGateStatus.INCONCLUSIVE

    # Deduplicate while preserving order so identical warnings raised
    # from observe and reject cohorts collapse into one.
    seen: set[str] = set()
    deduped_warnings: list[str] = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            deduped_warnings.append(w)

    return PaperAlphaGateCohortResult(
        dimension="strategy_mode",
        sample_count=int(total_n),
        status=status,
        signals=tuple(signals),
        warnings=tuple(deduped_warnings),
        notes=tuple(notes),
        metrics=metrics,
    )


def evaluate_candidate_stage_alpha(
    gate_input: PaperAlphaGateInput,
    *,
    late_chase_fake_breakout_rate: float = (
        DEFAULT_LATE_CHASE_FAKE_BREAKOUT_RATE
    ),
    min_bucket_samples: int = DEFAULT_MIN_BUCKET_SAMPLES,
) -> PaperAlphaGateCohortResult:
    """Evaluate the per-candidate_stage signals.

    Surfaces:

      - ``late_chase_warning`` when the ``late`` / ``blowoff``
        cohorts produce a ``fake_breakout_rate`` above
        ``late_chase_fake_breakout_rate`` on a non-thin cohort.

    Paper / report only.
    """
    signals: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    metrics: dict[str, Any] = {}

    total_n = 0
    for stage in ("early", "mid", "late", "blowoff", "dumped"):
        stats = gate_input.candidate_stage_stats.get(stage) or {}
        n = _safe_int(stats.get("sample_count", 0))
        fake = _safe_float(stats.get("fake_breakout_rate", 0.0))
        total_n += n
        metrics[f"{stage}_sample_count"] = n
        metrics[f"{stage}_fake_breakout_rate"] = fake
    metrics["late_chase_fake_breakout_rate_threshold"] = float(
        late_chase_fake_breakout_rate
    )

    for stage in ("late", "blowoff"):
        stats = gate_input.candidate_stage_stats.get(stage) or {}
        n = _safe_int(stats.get("sample_count", 0))
        fake = _safe_float(stats.get("fake_breakout_rate", 0.0))
        if n >= int(min_bucket_samples):
            if fake >= float(late_chase_fake_breakout_rate):
                warnings.append("late_chase_warning")
                notes.append(
                    f"{stage}.fake_breakout_rate={fake:.3f} "
                    f">= threshold="
                    f"{float(late_chase_fake_breakout_rate):.3f}"
                )
        else:
            notes.append(
                f"{stage}_cohort_too_thin n={n}<{int(min_bucket_samples)}"
            )

    if total_n < int(min_bucket_samples):
        status = PaperAlphaGateStatus.INCONCLUSIVE
    elif warnings:
        status = PaperAlphaGateStatus.WARN
    else:
        status = PaperAlphaGateStatus.PASS
        signals.append("no_late_chase_warning")

    # Deduplicate.
    seen: set[str] = set()
    deduped_warnings: list[str] = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            deduped_warnings.append(w)

    return PaperAlphaGateCohortResult(
        dimension="candidate_stage",
        sample_count=int(total_n),
        status=status,
        signals=tuple(signals),
        warnings=tuple(deduped_warnings),
        notes=tuple(notes),
        metrics=metrics,
    )


def _bucket_metric_avg(
    bucket_stats: Mapping[str, Mapping[str, Any]],
    *,
    bucket_keys: Sequence[str],
    metric_key: str,
    min_bucket_samples: int,
) -> tuple[float, int]:
    """Compute the sample-weighted average of ``metric_key`` across
    the union of ``bucket_keys`` (filtering out thin buckets).

    Returns ``(weighted_avg, total_n)``. ``total_n=0`` when every
    bucket is thin / missing - the caller treats that as
    inconclusive.
    """
    total_n = 0
    weighted_sum = 0.0
    for key in bucket_keys:
        stats = bucket_stats.get(key) or {}
        n = _safe_int(stats.get("sample_count", 0))
        if n < int(min_bucket_samples):
            continue
        rate = _safe_float(stats.get(metric_key, 0.0))
        total_n += n
        weighted_sum += rate * n
    if total_n <= 0:
        return 0.0, 0
    return weighted_sum / total_n, total_n


def evaluate_score_bucket_alpha(
    gate_input: PaperAlphaGateInput,
    *,
    high_bucket_advantage: float = DEFAULT_HIGH_BUCKET_ADVANTAGE,
    min_bucket_samples: int = DEFAULT_MIN_BUCKET_SAMPLES,
) -> tuple[PaperAlphaGateCohortResult, PaperAlphaGateCohortResult]:
    """Evaluate the per-opportunity_score_bucket and the
    per-early_tail_score_bucket cohort signals.

    Returns a 2-tuple ``(opportunity_result, early_tail_result)``.

    For each family, the gate compares the high-grade bucket's
    aggregated strong-tail / reached_3r / reached_5r rate against
    the low-grade bucket's. A clear advantage above
    ``high_bucket_advantage`` raises a positive ``*_signal``;
    otherwise the family stays ``INCONCLUSIVE`` (or, for early
    tail, ``WARN`` because the brief explicitly says "if early
    tail high bucket has no advantage, the gate cannot PASS").

    Paper / report only.
    """
    # --- opportunity_score family -------------------------------------
    opp_signals: list[str] = []
    opp_warnings: list[str] = []
    opp_notes: list[str] = []
    opp_metrics: dict[str, Any] = {}

    high_strong_tail, high_n = _bucket_metric_avg(
        gate_input.opportunity_score_bucket_stats,
        bucket_keys=HIGH_OPPORTUNITY_SCORE_BUCKETS,
        metric_key="strong_tail_rate",
        min_bucket_samples=int(min_bucket_samples),
    )
    low_strong_tail, low_n = _bucket_metric_avg(
        gate_input.opportunity_score_bucket_stats,
        bucket_keys=LOW_OPPORTUNITY_SCORE_BUCKETS,
        metric_key="strong_tail_rate",
        min_bucket_samples=int(min_bucket_samples),
    )
    high_p3r, _ = _bucket_metric_avg(
        gate_input.opportunity_score_bucket_stats,
        bucket_keys=HIGH_OPPORTUNITY_SCORE_BUCKETS,
        metric_key="p_reached_3r",
        min_bucket_samples=int(min_bucket_samples),
    )
    low_p3r, _ = _bucket_metric_avg(
        gate_input.opportunity_score_bucket_stats,
        bucket_keys=LOW_OPPORTUNITY_SCORE_BUCKETS,
        metric_key="p_reached_3r",
        min_bucket_samples=int(min_bucket_samples),
    )
    high_p5r, _ = _bucket_metric_avg(
        gate_input.opportunity_score_bucket_stats,
        bucket_keys=HIGH_OPPORTUNITY_SCORE_BUCKETS,
        metric_key="p_reached_5r",
        min_bucket_samples=int(min_bucket_samples),
    )
    low_p5r, _ = _bucket_metric_avg(
        gate_input.opportunity_score_bucket_stats,
        bucket_keys=LOW_OPPORTUNITY_SCORE_BUCKETS,
        metric_key="p_reached_5r",
        min_bucket_samples=int(min_bucket_samples),
    )
    opp_total_n = high_n + low_n
    opp_metrics.update(
        {
            "high_bucket_sample_count": high_n,
            "low_bucket_sample_count": low_n,
            "high_bucket_strong_tail_rate": high_strong_tail,
            "low_bucket_strong_tail_rate": low_strong_tail,
            "high_bucket_p_reached_3r": high_p3r,
            "low_bucket_p_reached_3r": low_p3r,
            "high_bucket_p_reached_5r": high_p5r,
            "low_bucket_p_reached_5r": low_p5r,
            "high_bucket_advantage_threshold": float(high_bucket_advantage),
            "high_buckets": list(HIGH_OPPORTUNITY_SCORE_BUCKETS),
            "low_buckets": list(LOW_OPPORTUNITY_SCORE_BUCKETS),
        }
    )

    if high_n >= int(min_bucket_samples) and low_n >= int(min_bucket_samples):
        # Compute the advantage on each metric independently; any
        # one being above threshold raises the signal.
        advantage_strong = high_strong_tail - low_strong_tail
        advantage_3r = high_p3r - low_p3r
        advantage_5r = high_p5r - low_p5r
        opp_metrics["advantage_strong_tail_rate"] = advantage_strong
        opp_metrics["advantage_p_reached_3r"] = advantage_3r
        opp_metrics["advantage_p_reached_5r"] = advantage_5r
        if (
            advantage_strong >= float(high_bucket_advantage)
            or advantage_3r >= float(high_bucket_advantage)
            or advantage_5r >= float(high_bucket_advantage)
        ):
            opp_signals.append("high_score_bucket_outperforms_low_signal")
            opp_status = PaperAlphaGateStatus.PASS
        else:
            opp_notes.append(
                "high_score_bucket_advantage_below_threshold "
                f"strong={advantage_strong:.3f} "
                f"p3r={advantage_3r:.3f} p5r={advantage_5r:.3f}"
            )
            opp_status = PaperAlphaGateStatus.INCONCLUSIVE
    else:
        opp_notes.append(
            "score_bucket_cohort_too_thin "
            f"high_n={high_n} low_n={low_n} "
            f"min={int(min_bucket_samples)}"
        )
        opp_status = PaperAlphaGateStatus.INCONCLUSIVE

    opp_result = PaperAlphaGateCohortResult(
        dimension="opportunity_score_bucket",
        sample_count=int(opp_total_n),
        status=opp_status,
        signals=tuple(opp_signals),
        warnings=tuple(opp_warnings),
        notes=tuple(opp_notes),
        metrics=opp_metrics,
    )

    # --- early_tail_score family --------------------------------------
    ets_signals: list[str] = []
    ets_warnings: list[str] = []
    ets_notes: list[str] = []
    ets_metrics: dict[str, Any] = {}

    high_strong_ets, high_n_ets = _bucket_metric_avg(
        gate_input.early_tail_score_bucket_stats,
        bucket_keys=HIGH_EARLY_TAIL_SCORE_BUCKETS,
        metric_key="strong_tail_rate",
        min_bucket_samples=int(min_bucket_samples),
    )
    low_strong_ets, low_n_ets = _bucket_metric_avg(
        gate_input.early_tail_score_bucket_stats,
        bucket_keys=LOW_EARLY_TAIL_SCORE_BUCKETS,
        metric_key="strong_tail_rate",
        min_bucket_samples=int(min_bucket_samples),
    )
    high_p3r_ets, _ = _bucket_metric_avg(
        gate_input.early_tail_score_bucket_stats,
        bucket_keys=HIGH_EARLY_TAIL_SCORE_BUCKETS,
        metric_key="p_reached_3r",
        min_bucket_samples=int(min_bucket_samples),
    )
    low_p3r_ets, _ = _bucket_metric_avg(
        gate_input.early_tail_score_bucket_stats,
        bucket_keys=LOW_EARLY_TAIL_SCORE_BUCKETS,
        metric_key="p_reached_3r",
        min_bucket_samples=int(min_bucket_samples),
    )
    ets_total_n = high_n_ets + low_n_ets
    ets_metrics.update(
        {
            "high_bucket_sample_count": high_n_ets,
            "low_bucket_sample_count": low_n_ets,
            "high_bucket_strong_tail_rate": high_strong_ets,
            "low_bucket_strong_tail_rate": low_strong_ets,
            "high_bucket_p_reached_3r": high_p3r_ets,
            "low_bucket_p_reached_3r": low_p3r_ets,
            "high_bucket_advantage_threshold": float(high_bucket_advantage),
            "high_buckets": list(HIGH_EARLY_TAIL_SCORE_BUCKETS),
            "low_buckets": list(LOW_EARLY_TAIL_SCORE_BUCKETS),
        }
    )

    if (
        high_n_ets >= int(min_bucket_samples)
        and low_n_ets >= int(min_bucket_samples)
    ):
        advantage_strong_ets = high_strong_ets - low_strong_ets
        advantage_3r_ets = high_p3r_ets - low_p3r_ets
        ets_metrics["advantage_strong_tail_rate"] = advantage_strong_ets
        ets_metrics["advantage_p_reached_3r"] = advantage_3r_ets
        if (
            advantage_strong_ets >= float(high_bucket_advantage)
            or advantage_3r_ets >= float(high_bucket_advantage)
        ):
            ets_signals.append(
                "high_early_tail_bucket_outperforms_low_signal"
            )
            ets_status = PaperAlphaGateStatus.PASS
        else:
            ets_warnings.append("early_tail_no_alpha_advantage")
            ets_notes.append(
                "early_tail_high_bucket_advantage_below_threshold "
                f"strong={advantage_strong_ets:.3f} "
                f"p3r={advantage_3r_ets:.3f}"
            )
            ets_status = PaperAlphaGateStatus.WARN
    else:
        ets_notes.append(
            "early_tail_score_bucket_cohort_too_thin "
            f"high_n={high_n_ets} low_n={low_n_ets} "
            f"min={int(min_bucket_samples)}"
        )
        ets_status = PaperAlphaGateStatus.INCONCLUSIVE

    ets_result = PaperAlphaGateCohortResult(
        dimension="early_tail_score_bucket",
        sample_count=int(ets_total_n),
        status=ets_status,
        signals=tuple(ets_signals),
        warnings=tuple(ets_warnings),
        notes=tuple(ets_notes),
        metrics=ets_metrics,
    )

    return opp_result, ets_result


def evaluate_cluster_alpha(
    gate_input: PaperAlphaGateInput,
    *,
    leader_preference_advantage: float = DEFAULT_LEADER_PREFERENCE_ADVANTAGE,
    min_bucket_samples: int = DEFAULT_MIN_BUCKET_SAMPLES,
) -> PaperAlphaGateCohortResult:
    """Evaluate the cluster-leader-vs-follower signal.

    Surfaces ``leader_preference_signal`` when the average leader
    advantage (over its followers' strong-tail rate or avg MFE)
    exceeds ``leader_preference_advantage`` on a non-thin set of
    clusters.

    Paper / report only.
    """
    signals: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []
    metrics: dict[str, Any] = {}

    cluster_count = 0
    cluster_with_outperformance = 0
    leader_total_n = 0
    follower_total_n = 0
    advantage_sum_strong = 0.0
    advantage_sum_mfe = 0.0
    contributing_clusters = 0

    for cluster_id, stats in gate_input.cluster_leader_stats.items():
        leader_n = _safe_int(stats.get("leader_sample_count", 0))
        follower_n = _safe_int(stats.get("follower_sample_count", 0))
        if leader_n <= 0 and follower_n <= 0:
            continue
        cluster_count += 1
        leader_total_n += leader_n
        follower_total_n += follower_n
        leader_strong = _safe_float(stats.get("leader_strong_tail_rate", 0.0))
        follower_strong = _safe_float(
            stats.get("follower_strong_tail_rate", 0.0)
        )
        leader_mfe = _safe_float(stats.get("leader_avg_mfe", 0.0))
        follower_mfe = _safe_float(stats.get("follower_avg_mfe", 0.0))
        if bool(stats.get("leader_outperformed_followers", False)):
            cluster_with_outperformance += 1
        # Contribute to the average only when the cluster has
        # enough leader + follower samples.
        if leader_n >= int(min_bucket_samples) and follower_n >= int(
            min_bucket_samples
        ):
            advantage_sum_strong += leader_strong - follower_strong
            advantage_sum_mfe += leader_mfe - follower_mfe
            contributing_clusters += 1

    metrics.update(
        {
            "cluster_count": cluster_count,
            "leader_total_sample_count": leader_total_n,
            "follower_total_sample_count": follower_total_n,
            "leader_outperformance_count": cluster_with_outperformance,
            "leader_preference_advantage_threshold": float(
                leader_preference_advantage
            ),
            "contributing_clusters": contributing_clusters,
        }
    )

    if contributing_clusters > 0:
        avg_strong_advantage = advantage_sum_strong / contributing_clusters
        avg_mfe_advantage = advantage_sum_mfe / contributing_clusters
        metrics["avg_leader_strong_tail_advantage"] = avg_strong_advantage
        metrics["avg_leader_mfe_advantage"] = avg_mfe_advantage
        if (
            avg_strong_advantage >= float(leader_preference_advantage)
            or avg_mfe_advantage >= float(leader_preference_advantage)
        ):
            signals.append("leader_preference_signal")
            status = PaperAlphaGateStatus.PASS
        else:
            notes.append(
                "leader_preference_advantage_below_threshold "
                f"strong={avg_strong_advantage:.3f} "
                f"mfe={avg_mfe_advantage:.3f}"
            )
            status = PaperAlphaGateStatus.INCONCLUSIVE
    else:
        notes.append(
            "cluster_leader_cohort_too_thin "
            f"contributing_clusters={contributing_clusters} "
            f"min={int(min_bucket_samples)}"
        )
        status = PaperAlphaGateStatus.INCONCLUSIVE

    return PaperAlphaGateCohortResult(
        dimension="cluster_leader_vs_follower",
        sample_count=int(leader_total_n + follower_total_n),
        status=status,
        signals=tuple(signals),
        warnings=tuple(warnings),
        notes=tuple(notes),
        metrics=metrics,
    )


def _evaluate_tail_label_distribution(
    gate_input: PaperAlphaGateInput,
) -> PaperAlphaGateCohortResult:
    """Surface a descriptive snapshot of the tail-label distribution.

    Always ``INCONCLUSIVE`` standalone (the gate does not reach a
    PASS verdict on label distribution alone); the dimension is
    surfaced so a human reviewer can audit the underlying mix.
    """
    counts = dict(gate_input.tail_label_counts)
    total = sum(int(v) for v in counts.values())
    return PaperAlphaGateCohortResult(
        dimension="tail_label_distribution",
        sample_count=int(total),
        status=PaperAlphaGateStatus.INCONCLUSIVE,
        signals=tuple(),
        warnings=tuple(),
        notes=(
            "tail_label_distribution_is_descriptive_only",
        ),
        metrics={"counts": {k: int(v) for k, v in sorted(counts.items())}},
    )


# ---------------------------------------------------------------------------
# Top-level evaluator
# ---------------------------------------------------------------------------
def _build_rule_results(
    gate_input: PaperAlphaGateInput,
    cohort_results: Sequence[PaperAlphaGateCohortResult],
    *,
    min_total_samples: int,
    min_completed_tail_labels: int,
    follow_fake_breakout_rate: float,
    missed_alpha_strong_tail_rate: float,
    late_chase_fake_breakout_rate: float,
    high_bucket_advantage: float,
    leader_preference_advantage: float,
) -> list[PaperAlphaGateRuleResult]:
    """Project the cohort signals + the input thresholds onto a list
    of named rule results so a downstream auditor can render a
    flat per-rule table without re-walking the cohort objects.
    """
    results: list[PaperAlphaGateRuleResult] = []

    # 1. quality_gate_status feeds-in.
    qg_status = str(gate_input.quality_gate_status or "")
    qg_failed = qg_status == "fail"
    results.append(
        PaperAlphaGateRuleResult(
            rule_id="quality_gate_status_must_not_fail",
            triggered=bool(qg_failed),
            observed_value=1.0 if qg_failed else 0.0,
            threshold=1.0,
            severity="block",
            message=f"validation_quality_gate_status={qg_status or 'unset'}",
        )
    )

    # 2. min_total_samples.
    triggered_thin = int(gate_input.sample_count) < int(min_total_samples)
    results.append(
        PaperAlphaGateRuleResult(
            rule_id="dataset_must_have_min_total_samples",
            triggered=bool(triggered_thin),
            observed_value=float(gate_input.sample_count),
            threshold=float(min_total_samples),
            severity="block",
            message=(
                f"sample_count={gate_input.sample_count} "
                f"min={int(min_total_samples)}"
            ),
        )
    )

    # 3. min_completed_tail_labels.
    triggered_completed = int(gate_input.completed_tail_label_count) < int(
        min_completed_tail_labels
    )
    results.append(
        PaperAlphaGateRuleResult(
            rule_id="dataset_must_have_min_completed_tail_labels",
            triggered=bool(triggered_completed),
            observed_value=float(gate_input.completed_tail_label_count),
            threshold=float(min_completed_tail_labels),
            severity="block",
            message=(
                "completed_tail_label_count="
                f"{gate_input.completed_tail_label_count} "
                f"min={int(min_completed_tail_labels)}"
            ),
        )
    )

    # 4. follow_risk_warning.
    follow_n = 0
    follow_fake = 0.0
    for c in cohort_results:
        if c.dimension == "strategy_mode":
            follow_n = _safe_int(c.metrics.get("follow_sample_count", 0))
            follow_fake = _safe_float(
                c.metrics.get("follow_fake_breakout_rate", 0.0)
            )
            break
    results.append(
        PaperAlphaGateRuleResult(
            rule_id="follow_fake_breakout_rate_below_threshold",
            triggered=bool(
                follow_n > 0 and follow_fake >= float(follow_fake_breakout_rate)
            ),
            observed_value=float(follow_fake),
            threshold=float(follow_fake_breakout_rate),
            severity="warning",
            message=(
                f"follow.fake_breakout_rate={follow_fake:.3f} "
                f"threshold={float(follow_fake_breakout_rate):.3f}"
            ),
        )
    )

    # 5. missed_alpha_warning.
    missed_alpha = False
    for c in cohort_results:
        if c.dimension == "strategy_mode":
            missed_alpha = "missed_alpha_warning" in c.warnings
            break
    results.append(
        PaperAlphaGateRuleResult(
            rule_id="observe_reject_strong_tail_rate_below_threshold",
            triggered=bool(missed_alpha),
            observed_value=1.0 if missed_alpha else 0.0,
            threshold=float(missed_alpha_strong_tail_rate),
            severity="warning",
            message=(
                "observe/reject strong_tail_rate flagged"
                if missed_alpha
                else "observe/reject strong_tail_rate within threshold"
            ),
        )
    )

    # 6. late_chase_warning.
    late_chase = False
    for c in cohort_results:
        if c.dimension == "candidate_stage":
            late_chase = "late_chase_warning" in c.warnings
            break
    results.append(
        PaperAlphaGateRuleResult(
            rule_id="late_blowoff_fake_breakout_rate_below_threshold",
            triggered=bool(late_chase),
            observed_value=1.0 if late_chase else 0.0,
            threshold=float(late_chase_fake_breakout_rate),
            severity="warning",
            message=(
                "late/blowoff fake_breakout_rate flagged"
                if late_chase
                else "late/blowoff fake_breakout_rate within threshold"
            ),
        )
    )

    # 7. high score bucket signal.
    opp_signal = False
    ets_signal = False
    ets_warn = False
    for c in cohort_results:
        if c.dimension == "opportunity_score_bucket":
            opp_signal = (
                "high_score_bucket_outperforms_low_signal" in c.signals
            )
        elif c.dimension == "early_tail_score_bucket":
            ets_signal = (
                "high_early_tail_bucket_outperforms_low_signal" in c.signals
            )
            ets_warn = "early_tail_no_alpha_advantage" in c.warnings
    results.append(
        PaperAlphaGateRuleResult(
            rule_id="high_opportunity_score_bucket_outperforms_low",
            triggered=bool(opp_signal),
            observed_value=1.0 if opp_signal else 0.0,
            threshold=float(high_bucket_advantage),
            severity="info",
            message=(
                "high opportunity_score bucket out-performs low"
                if opp_signal
                else "no high-vs-low opportunity_score bucket advantage"
            ),
        )
    )
    results.append(
        PaperAlphaGateRuleResult(
            rule_id="high_early_tail_score_bucket_outperforms_low",
            triggered=bool(ets_signal),
            observed_value=1.0 if ets_signal else 0.0,
            threshold=float(high_bucket_advantage),
            severity="info",
            message=(
                "high early_tail_score bucket out-performs low"
                if ets_signal
                else (
                    "no high-vs-low early_tail_score bucket advantage"
                    if not ets_warn
                    else "early_tail high bucket has no alpha advantage"
                )
            ),
        )
    )

    # 8. leader_preference_signal.
    leader_pref = False
    for c in cohort_results:
        if c.dimension == "cluster_leader_vs_follower":
            leader_pref = "leader_preference_signal" in c.signals
            break
    results.append(
        PaperAlphaGateRuleResult(
            rule_id="cluster_leader_outperforms_followers",
            triggered=bool(leader_pref),
            observed_value=1.0 if leader_pref else 0.0,
            threshold=float(leader_preference_advantage),
            severity="info",
            message=(
                "cluster leader out-performs followers"
                if leader_pref
                else "no cluster leader-vs-follower advantage"
            ),
        )
    )

    return results


def evaluate_paper_alpha_gate(
    gate_input: PaperAlphaGateInput,
    *,
    min_total_samples: int = DEFAULT_MIN_TOTAL_SAMPLES,
    min_completed_tail_labels: int = DEFAULT_MIN_COMPLETED_TAIL_LABELS,
    min_bucket_samples: int = DEFAULT_MIN_BUCKET_SAMPLES,
    follow_fake_breakout_rate: float = DEFAULT_FOLLOW_FAKE_BREAKOUT_RATE,
    missed_alpha_strong_tail_rate: float = (
        DEFAULT_MISSED_ALPHA_STRONG_TAIL_RATE
    ),
    late_chase_fake_breakout_rate: float = (
        DEFAULT_LATE_CHASE_FAKE_BREAKOUT_RATE
    ),
    high_bucket_advantage: float = DEFAULT_HIGH_BUCKET_ADVANTAGE,
    leader_preference_advantage: float = DEFAULT_LEADER_PREFERENCE_ADVANTAGE,
) -> tuple[
    str,
    tuple[str, ...],
    tuple[str, ...],
    tuple[PaperAlphaGateCohortResult, ...],
    tuple[PaperAlphaGateRuleResult, ...],
]:
    """Evaluate every Paper Alpha Gate v0 rule against ``gate_input``.

    Returns a 5-tuple
    ``(gate_status, reasons, warnings, cohort_results, rule_results)``.

    The function is **pure** - no I/O, no clock read, no event
    emission. The verdict is descriptive: ``PASS`` / ``WARN`` /
    ``FAIL`` / ``INCONCLUSIVE`` is a label for human review,
    NEVER an input to a trade-decision pipeline. The Risk Engine
    remains the single trade-decision gate.
    """
    reasons: list[str] = []
    warnings: list[str] = []

    # Phase 1: per-cohort evaluators.
    strategy_mode_result = evaluate_strategy_mode_alpha(
        gate_input,
        follow_fake_breakout_rate=float(follow_fake_breakout_rate),
        missed_alpha_strong_tail_rate=float(missed_alpha_strong_tail_rate),
        min_bucket_samples=int(min_bucket_samples),
    )
    candidate_stage_result = evaluate_candidate_stage_alpha(
        gate_input,
        late_chase_fake_breakout_rate=float(late_chase_fake_breakout_rate),
        min_bucket_samples=int(min_bucket_samples),
    )
    opp_bucket_result, ets_bucket_result = evaluate_score_bucket_alpha(
        gate_input,
        high_bucket_advantage=float(high_bucket_advantage),
        min_bucket_samples=int(min_bucket_samples),
    )
    cluster_result = evaluate_cluster_alpha(
        gate_input,
        leader_preference_advantage=float(leader_preference_advantage),
        min_bucket_samples=int(min_bucket_samples),
    )
    tail_label_result = _evaluate_tail_label_distribution(gate_input)

    cohort_results: tuple[PaperAlphaGateCohortResult, ...] = (
        strategy_mode_result,
        candidate_stage_result,
        opp_bucket_result,
        ets_bucket_result,
        cluster_result,
        tail_label_result,
    )

    # Phase 2: top-level decision.
    qg_status = str(gate_input.quality_gate_status or "")
    sample_count = int(gate_input.sample_count)
    completed = int(gate_input.completed_tail_label_count)

    inconclusive = False
    fail = False
    warn = False

    if qg_status == "fail":
        # Rule: validation_quality_gate_status=fail -> the dataset
        # is structurally untrustworthy. The brief lets us pick
        # ``INCONCLUSIVE`` or ``FAIL``; we emit ``INCONCLUSIVE`` so a
        # downstream auditor knows the gate refused to evaluate
        # alpha evidence (rather than asserting "no alpha"). The
        # ``quality_gate_status_must_not_fail`` block-rule still
        # surfaces in the rule_results.
        inconclusive = True
        reasons.append(f"validation_quality_gate_status={qg_status}")

    if sample_count < int(min_total_samples):
        inconclusive = True
        reasons.append(
            f"sample_count_below_min={sample_count}<{int(min_total_samples)}"
        )

    if completed < int(min_completed_tail_labels):
        inconclusive = True
        reasons.append(
            f"completed_tail_label_count_below_min={completed}<"
            f"{int(min_completed_tail_labels)}"
        )

    # Aggregate warnings from cohort results.
    for cohort in cohort_results:
        for w in cohort.warnings:
            if w not in warnings:
                warnings.append(w)

    # Map warnings to per-rule reasons so a Markdown / JSON consumer
    # has a flat list of "why".
    if "follow_risk_warning" in warnings:
        reasons.append("follow_risk_warning")
    if "missed_alpha_warning" in warnings:
        reasons.append("missed_alpha_warning")
    if "late_chase_warning" in warnings:
        reasons.append("late_chase_warning")
    if "early_tail_no_alpha_advantage" in warnings:
        reasons.append("early_tail_no_alpha_advantage")

    # Positive-signal projection.
    has_high_score_signal = any(
        "high_score_bucket_outperforms_low_signal" in c.signals
        for c in cohort_results
    )
    has_high_early_tail_signal = any(
        "high_early_tail_bucket_outperforms_low_signal" in c.signals
        for c in cohort_results
    )
    has_leader_signal = any(
        "leader_preference_signal" in c.signals for c in cohort_results
    )

    if has_high_score_signal:
        reasons.append("high_score_bucket_outperforms_low_signal")
    if has_high_early_tail_signal:
        reasons.append("high_early_tail_bucket_outperforms_low_signal")
    if has_leader_signal:
        reasons.append("leader_preference_signal")

    # Top-level decision tree.
    if inconclusive:
        gate_status = PaperAlphaGateStatus.INCONCLUSIVE
    elif warnings:
        # The brief lets WARN co-exist with positive signals - the
        # gate raises WARN and the human reviewer audits the rule
        # results.
        gate_status = PaperAlphaGateStatus.WARN
        warn = True
    elif (
        has_high_score_signal
        and has_high_early_tail_signal
    ):
        # Strict PASS: requires *both* alpha-evidence signals on a
        # trustworthy dataset with no warning.
        gate_status = PaperAlphaGateStatus.PASS
        reasons.append("paper_alpha_gate_v0_pass_signals_aligned")
    elif has_high_score_signal or has_leader_signal:
        # Soft PASS becomes WARN when we cannot find both score-
        # bucket signals; the brief explicitly says "if early tail
        # high bucket has no advantage, the gate cannot PASS".
        gate_status = PaperAlphaGateStatus.WARN
        warn = True
        reasons.append("paper_alpha_gate_v0_partial_signals")
    else:
        # No fail trigger, no warning, but no positive signal either.
        # Insufficient evidence to PASS.
        gate_status = PaperAlphaGateStatus.INCONCLUSIVE
        reasons.append("paper_alpha_gate_v0_no_positive_signal")

    # Build per-rule results last so we have all the cohort signals.
    rule_results = _build_rule_results(
        gate_input,
        cohort_results,
        min_total_samples=int(min_total_samples),
        min_completed_tail_labels=int(min_completed_tail_labels),
        follow_fake_breakout_rate=float(follow_fake_breakout_rate),
        missed_alpha_strong_tail_rate=float(missed_alpha_strong_tail_rate),
        late_chase_fake_breakout_rate=float(late_chase_fake_breakout_rate),
        high_bucket_advantage=float(high_bucket_advantage),
        leader_preference_advantage=float(leader_preference_advantage),
    )

    # Suppress unused locals (kept for readability / future
    # extensions; ruff treats _ assignments as intentional).
    _ = warn
    _ = fail

    return (
        str(gate_status),
        tuple(reasons),
        tuple(warnings),
        tuple(cohort_results),
        tuple(rule_results),
    )


# ---------------------------------------------------------------------------
# Top-level report builder
# ---------------------------------------------------------------------------
def build_paper_alpha_gate_report(
    gate_input: PaperAlphaGateInput,
    *,
    evaluated_at: int = 0,
    min_total_samples: int = DEFAULT_MIN_TOTAL_SAMPLES,
    min_completed_tail_labels: int = DEFAULT_MIN_COMPLETED_TAIL_LABELS,
    min_bucket_samples: int = DEFAULT_MIN_BUCKET_SAMPLES,
    follow_fake_breakout_rate: float = DEFAULT_FOLLOW_FAKE_BREAKOUT_RATE,
    missed_alpha_strong_tail_rate: float = (
        DEFAULT_MISSED_ALPHA_STRONG_TAIL_RATE
    ),
    late_chase_fake_breakout_rate: float = (
        DEFAULT_LATE_CHASE_FAKE_BREAKOUT_RATE
    ),
    high_bucket_advantage: float = DEFAULT_HIGH_BUCKET_ADVANTAGE,
    leader_preference_advantage: float = DEFAULT_LEADER_PREFERENCE_ADVANTAGE,
) -> PaperAlphaGateReport:
    """Build a :class:`PaperAlphaGateReport` from a
    :class:`PaperAlphaGateInput`.

    The function is **pure** - no I/O, no clock read, no event
    emission. The result is descriptive only and grants no trade
    authority.
    """
    (
        gate_status,
        reasons,
        warnings,
        cohort_results,
        rule_results,
    ) = evaluate_paper_alpha_gate(
        gate_input,
        min_total_samples=int(min_total_samples),
        min_completed_tail_labels=int(min_completed_tail_labels),
        min_bucket_samples=int(min_bucket_samples),
        follow_fake_breakout_rate=float(follow_fake_breakout_rate),
        missed_alpha_strong_tail_rate=float(missed_alpha_strong_tail_rate),
        late_chase_fake_breakout_rate=float(late_chase_fake_breakout_rate),
        high_bucket_advantage=float(high_bucket_advantage),
        leader_preference_advantage=float(leader_preference_advantage),
    )
    return PaperAlphaGateReport(
        report_id=str(gate_input.report_id),
        dataset_id=str(gate_input.dataset_id),
        sample_count=int(gate_input.sample_count),
        quality_gate_status=str(gate_input.quality_gate_status),
        evaluated_at=int(evaluated_at),
        gate_status=str(gate_status),
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        rule_results=tuple(rule_results),
        cohort_results=tuple(cohort_results),
        strategy_version=str(gate_input.strategy_version),
        scoring_version=str(gate_input.scoring_version),
        risk_config_version=str(gate_input.risk_config_version),
        state_machine_version=str(gate_input.state_machine_version),
    )


# ---------------------------------------------------------------------------
# Export / Replay (round-trip)
# ---------------------------------------------------------------------------
def export_paper_alpha_gate_payload(
    report: PaperAlphaGateReport,
) -> dict[str, Any]:
    """Return a JSON-safe dict for the Paper Alpha Gate report.

    The function is **pure** - it does not write to disk. The
    runner / daily-report builder is responsible for serialising
    the dict to bytes.
    """
    return report.to_payload()


def load_paper_alpha_gate_payload(
    payload: Mapping[str, Any],
) -> PaperAlphaGateReport:
    """Reconstruct a :class:`PaperAlphaGateReport` from a payload
    produced by :func:`export_paper_alpha_gate_payload`.

    Tolerates payloads from old schema_versions: missing optional
    fields default to the v0 defaults so a future PR can extend
    the contract without breaking replay.
    """
    if not isinstance(payload, Mapping):
        raise TypeError(
            "load_paper_alpha_gate_payload requires a Mapping; got "
            f"{type(payload).__name__}"
        )
    raw_rules = payload.get("rule_results") or []
    rule_results: list[PaperAlphaGateRuleResult] = []
    for row in raw_rules:
        if not isinstance(row, Mapping):
            continue
        rule_results.append(
            PaperAlphaGateRuleResult(
                rule_id=str(row.get("rule_id") or ""),
                triggered=bool(row.get("triggered") or False),
                observed_value=float(row.get("observed_value") or 0.0),
                threshold=float(row.get("threshold") or 0.0),
                severity=str(row.get("severity") or "info"),
                message=str(row.get("message") or ""),
                schema_version=str(
                    row.get("schema_version")
                    or PAPER_ALPHA_GATE_SCHEMA_VERSION
                ),
            )
        )

    raw_cohorts = payload.get("cohort_results") or []
    cohort_results: list[PaperAlphaGateCohortResult] = []
    for row in raw_cohorts:
        if not isinstance(row, Mapping):
            continue
        cohort_results.append(
            PaperAlphaGateCohortResult(
                dimension=str(row.get("dimension") or ""),
                sample_count=int(row.get("sample_count") or 0),
                status=str(
                    row.get("status") or PaperAlphaGateStatus.INCONCLUSIVE
                ),
                signals=tuple(str(s) for s in (row.get("signals") or ())),
                warnings=tuple(str(s) for s in (row.get("warnings") or ())),
                notes=tuple(str(s) for s in (row.get("notes") or ())),
                metrics=dict(row.get("metrics") or {}),
                schema_version=str(
                    row.get("schema_version")
                    or PAPER_ALPHA_GATE_SCHEMA_VERSION
                ),
            )
        )

    return PaperAlphaGateReport(
        report_id=str(payload.get("report_id") or ""),
        dataset_id=str(payload.get("dataset_id") or ""),
        sample_count=int(payload.get("sample_count") or 0),
        quality_gate_status=str(payload.get("quality_gate_status") or ""),
        evaluated_at=int(payload.get("evaluated_at") or 0),
        gate_status=str(
            payload.get("gate_status") or PaperAlphaGateStatus.INCONCLUSIVE
        ),
        reasons=tuple(str(r) for r in (payload.get("reasons") or ())),
        warnings=tuple(str(w) for w in (payload.get("warnings") or ())),
        rule_results=tuple(rule_results),
        cohort_results=tuple(cohort_results),
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
            or PAPER_ALPHA_GATE_SCHEMA_VERSION
        ),
    )


__all__ = [
    # Constants
    "PAPER_ALPHA_GATE_SCHEMA_VERSION",
    "KNOWN_PAPER_ALPHA_GATE_SCHEMA_VERSIONS",
    "PAPER_ALPHA_GATE_VERSION",
    "PAPER_ALPHA_GATE_SOURCE_PHASE",
    "PAPER_ALPHA_GATE_STATUSES",
    "PAPER_ALPHA_COHORT_DIMENSIONS",
    "DEFAULT_MIN_TOTAL_SAMPLES",
    "DEFAULT_MIN_COMPLETED_TAIL_LABELS",
    "DEFAULT_MIN_BUCKET_SAMPLES",
    "DEFAULT_HIGH_BUCKET_ADVANTAGE",
    "DEFAULT_LATE_CHASE_FAKE_BREAKOUT_RATE",
    "DEFAULT_MISSED_ALPHA_STRONG_TAIL_RATE",
    "DEFAULT_FOLLOW_FAKE_BREAKOUT_RATE",
    "DEFAULT_LEADER_PREFERENCE_ADVANTAGE",
    "HIGH_OPPORTUNITY_SCORE_BUCKETS",
    "LOW_OPPORTUNITY_SCORE_BUCKETS",
    "HIGH_EARLY_TAIL_SCORE_BUCKETS",
    "LOW_EARLY_TAIL_SCORE_BUCKETS",
    # Models
    "PaperAlphaGateStatus",
    "PaperAlphaGateRule",
    "PaperAlphaGateRuleResult",
    "PaperAlphaGateCohortResult",
    "PaperAlphaGateInput",
    "PaperAlphaGateReport",
    # Pure functions
    "build_paper_alpha_gate_input",
    "evaluate_paper_alpha_gate",
    "evaluate_strategy_mode_alpha",
    "evaluate_candidate_stage_alpha",
    "evaluate_score_bucket_alpha",
    "evaluate_cluster_alpha",
    "build_paper_alpha_gate_report",
    "export_paper_alpha_gate_payload",
    "load_paper_alpha_gate_payload",
]
