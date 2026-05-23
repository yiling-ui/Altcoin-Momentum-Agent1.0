"""Phase 11C.1C-C-B-B-A - Strategy Validation Dataset Builder &
Quality Gate v0.

Phase 11C.1C-C-B-A produced the value-object contracts for one
:class:`StrategyValidationSample` per opportunity outcome plus the
top-level :class:`StrategyValidationReport`. This module turns those
artefacts into a **dataset** that is:

  - exportable (JSON-safe payload via ``export_validation_dataset_payload``);
  - replayable (round-trippable via ``load_validation_dataset_payload``);
  - auditable (a quality gate flags whether the dataset is trustworthy
    enough for downstream review).

The first version of the quality gate is intentionally a *sample
trust* gate, not a *strategy quality* gate. It only tests:

  - did we collect enough samples?
  - did the samples carry every brief-mandated field?
  - is the dataset coverage diverse enough to be useful (no missing
    canonical strategy_mode / candidate_stage / opportunity_score
    bucket)?
  - does the dataset round-trip through the export / replay layer
    cleanly?

It does **not** judge whether the strategy is profitable.

Phase 11C.1C-C-B-B-A boundary
-----------------------------

This module:

  - is paper / virtual ONLY;
  - is contract + pure functions; nothing here triggers a real trade,
    opens a position, modifies a stop-loss, or reads a private API;
  - the quality gate result is **descriptive**: ``pass`` /
    ``warn`` / ``fail`` is a label for human review, NEVER an input
    to a trade-decision pipeline;
  - is **NOT** the complete Strategy Validation Lab follow-up
    (Phase 11C.1C-C-B-B-B);
  - is **NOT** AI Learning, **NOT** automatic parameter optimisation,
    **NOT** reinforcement learning, **NOT** Phase 12;
  - tags every payload with a ``schema_version`` field so old payloads
    without the v0 sub-block remain replayable verbatim.

The runtime that consumes this module
(:class:`app.adaptive.strategy_validation_runtime.StrategyValidationRuntime`)
emits the three new typed events:

  - ``STRATEGY_VALIDATION_DATASET_BUILT``
  - ``STRATEGY_VALIDATION_DATASET_EXPORTED``
  - ``STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED``

Every event payload includes ``report_id``, ``timestamp``,
``strategy_version``, ``scoring_version``, ``risk_config_version``,
``state_machine_version`` and ``schema_version`` so Reflection /
Replay can group on them without parsing free-form audit dicts.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.adaptive.strategy_validation import (
    EARLY_TAIL_SCORE_BUCKET_LABELS,
    OPPORTUNITY_SCORE_BUCKET_LABELS,
    StrategyValidationSample,
    early_tail_score_bucket_for,
    opportunity_score_bucket_for,
)


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Schema version stamp written on every Phase 11C.1C-C-B-B-A payload.
#: A future PR that changes the payload shape MUST bump this label.
STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION: str = (
    "phase_11c_1c_c_b_b_a.strategy_validation_dataset.v1"
)
KNOWN_STRATEGY_VALIDATION_DATASET_SCHEMA_VERSIONS: tuple[str, ...] = (
    STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION,
)

#: Phase 11C.1C-C-B-B-A canonical version labels. Carried on every
#: event payload so Reflection / Replay can group on them.
STRATEGY_VALIDATION_DATASET_VERSION: str = (
    "phase_11c_1c_c_b_b_a.strategy_validation_dataset.v1"
)
STRATEGY_VALIDATION_DATASET_SOURCE_PHASE: str = (
    "phase_11c_1c_c_b_b_a_strategy_validation_dataset_quality_gate_v0"
)

#: Allowed quality-gate statuses. ``pass`` / ``warn`` / ``fail`` are
#: descriptive labels - they are NEVER an input to a trade-decision
#: pipeline.
QUALITY_GATE_STATUSES: tuple[str, ...] = ("pass", "warn", "fail")

#: The four canonical strategy modes the validation dataset MUST
#: cover at minimum (Phase 11C.1C-C-B-A brief).
CANONICAL_STRATEGY_MODES: tuple[str, ...] = (
    "follow",
    "pullback",
    "observe",
    "reject",
)

#: The five canonical candidate stages the validation dataset MUST
#: cover at minimum (Phase 11C.1C-C-B-A brief).
CANONICAL_CANDIDATE_STAGES: tuple[str, ...] = (
    "early",
    "mid",
    "late",
    "blowoff",
    "dumped",
)

#: The set of ``tail_label`` values considered *completed* (the
#: opportunity reached at least its primary tracking window). The
#: ``unresolved`` label is intentionally excluded - that is the
#: in-flight state.
COMPLETED_TAIL_LABELS: frozenset[str] = frozenset(
    {
        "strong_tail",
        "moderate_tail",
        "weak_tail",
        "fake_breakout",
        "late_chase_failure",
        "missed_tail",
        "dumped",
    }
)

#: The set of fields the dataset record MUST carry on every row.
#: Used by ``evaluate_validation_dataset_quality`` to detect missing
#: fields without re-encoding the contract.
REQUIRED_DATASET_RECORD_FIELDS: tuple[str, ...] = (
    "report_id",
    "opportunity_id",
    "scan_batch_id",
    "symbol",
    "candidate_stage",
    "strategy_mode",
    "opportunity_score",
    "early_tail_score",
    "late_chase_risk",
    "cluster_id",
    "tail_label",
    "mfe_5m",
    "mae_5m",
    "mfe_15m",
    "mae_15m",
    "mfe_30m",
    "mae_30m",
    "mfe_1h",
    "mae_1h",
    "mfe_4h",
    "mae_4h",
    "reached_2r",
    "reached_3r",
    "reached_5r",
    "reached_10r",
    "fake_breakout",
    "missed_tail",
    "late_chase_failure",
    "source_event_id",
    "schema_version",
)


# ---------------------------------------------------------------------------
# Dataset record
# ---------------------------------------------------------------------------
class StrategyValidationDatasetRecord(BaseModel):
    """One Phase 11C.1C-C-B-B-A dataset row.

    Maps 1:1 to a Phase 11C.1C-C-B-A
    :class:`StrategyValidationSample` plus the report identity that
    aggregated it. Contract-only: building one does NOT authorise
    opening a real position; the Risk Engine remains the single
    trade-decision gate.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Identity (Phase 8.5 contract).
    report_id: str
    opportunity_id: str
    scan_batch_id: str
    symbol: str

    # Adaptive context snapshot.
    candidate_stage: str
    strategy_mode: str
    opportunity_score: float = 0.0
    early_tail_score: float = 0.0
    late_chase_risk: float = 0.0

    # Cluster context.
    cluster_id: str = "unknown"
    cluster_leader: str | None = None

    # Final tail label assigned by the Phase 11C.1C-C-A runtime.
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

    # R-multiple milestones.
    reached_2r: bool = False
    reached_3r: bool = False
    reached_5r: bool = False
    reached_10r: bool = False

    # Outcome flags.
    fake_breakout: bool = False
    missed_tail: bool = False
    late_chase_failure: bool = False

    # Provenance. ``source_event_id`` cross-references the originating
    # ``STRATEGY_VALIDATION_SAMPLE_CREATED`` event row in events.db so
    # a downstream auditor can replay the exact event that produced
    # the row.
    source_event_id: str = ""
    schema_version: str = STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION

    @field_validator("strategy_mode")
    @classmethod
    def _check_mode(cls, value: str) -> str:
        text = str(value).strip()
        return text or "observe"

    @field_validator("candidate_stage")
    @classmethod
    def _check_stage(cls, value: str) -> str:
        text = str(value).strip()
        return text or "early"

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
            "report_id": str(self.report_id),
            "opportunity_id": str(self.opportunity_id),
            "scan_batch_id": str(self.scan_batch_id),
            "symbol": str(self.symbol),
            "candidate_stage": str(self.candidate_stage),
            "strategy_mode": str(self.strategy_mode),
            "opportunity_score": float(self.opportunity_score),
            "early_tail_score": float(self.early_tail_score),
            "late_chase_risk": float(self.late_chase_risk),
            "cluster_id": str(self.cluster_id),
            "cluster_leader": (
                str(self.cluster_leader)
                if self.cluster_leader is not None
                else None
            ),
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
            "source_event_id": str(self.source_event_id),
            "schema_version": str(self.schema_version),
        }


# ---------------------------------------------------------------------------
# Dataset summary
# ---------------------------------------------------------------------------
class StrategyValidationDatasetSummary(BaseModel):
    """Summary statistics over a :class:`StrategyValidationDataset`.

    The summary is the input the daily-report builder consumes; it
    answers "how many samples / which symbols / which tail labels"
    without re-walking every record.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_count: int = 0
    completed_tail_label_count: int = 0
    symbols: tuple[str, ...] = Field(default_factory=tuple)
    strategy_mode_counts: dict[str, int] = Field(default_factory=dict)
    candidate_stage_counts: dict[str, int] = Field(default_factory=dict)
    opportunity_score_bucket_counts: dict[str, int] = Field(default_factory=dict)
    early_tail_score_bucket_counts: dict[str, int] = Field(default_factory=dict)
    tail_label_counts: dict[str, int] = Field(default_factory=dict)
    cluster_ids: tuple[str, ...] = Field(default_factory=tuple)
    fake_breakout_count: int = 0
    missed_tail_count: int = 0
    late_chase_failure_count: int = 0
    schema_version: str = STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "record_count": int(self.record_count),
            "completed_tail_label_count": int(
                self.completed_tail_label_count
            ),
            "symbols": list(self.symbols),
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
            "cluster_ids": list(self.cluster_ids),
            "fake_breakout_count": int(self.fake_breakout_count),
            "missed_tail_count": int(self.missed_tail_count),
            "late_chase_failure_count": int(self.late_chase_failure_count),
            "schema_version": str(self.schema_version),
        }


# ---------------------------------------------------------------------------
# Dataset top-level container
# ---------------------------------------------------------------------------
class StrategyValidationDataset(BaseModel):
    """Container for the dataset rows + summary + report identity.

    Frozen + JSON-safe; the canonical payload form for export / replay.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str
    generated_at_ms: int = 0
    records: tuple[StrategyValidationDatasetRecord, ...] = Field(
        default_factory=tuple
    )
    summary: StrategyValidationDatasetSummary = Field(
        default_factory=StrategyValidationDatasetSummary
    )
    strategy_version: str = "phase_11c_1c_a.strategy.v1"
    scoring_version: str = "phase_11c_1c_a.scoring.v1"
    risk_config_version: str = "phase_11c_1c_a.risk_config.v1"
    state_machine_version: str = "phase_11c_1c_a.state_machine.v1"
    schema_version: str = STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION

    def to_payload(self) -> dict[str, Any]:
        return {
            "report_id": str(self.report_id),
            "generated_at_ms": int(self.generated_at_ms),
            "records": [r.to_payload() for r in self.records],
            "summary": self.summary.to_payload(),
            "strategy_version": str(self.strategy_version),
            "scoring_version": str(self.scoring_version),
            "risk_config_version": str(self.risk_config_version),
            "state_machine_version": str(self.state_machine_version),
            "schema_version": str(self.schema_version),
        }


# ---------------------------------------------------------------------------
# Quality gate (input)
# ---------------------------------------------------------------------------
class StrategyValidationQualityGate(BaseModel):
    """Phase 11C.1C-C-B-B-A quality gate v0 thresholds.

    The gate is intentionally a *sample trust* gate, not a *strategy
    quality* gate. It only judges whether the dataset is trustworthy
    enough for downstream review. It does NOT judge whether the
    strategy is profitable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: Minimum total dataset rows required for ``pass``. Below this
    #: the gate emits ``warn``; below half this the gate emits
    #: ``fail``.
    min_total_samples: int = 20

    #: Minimum number of rows whose ``tail_label`` is one of the
    #: completed labels (i.e. not ``unresolved``).
    min_completed_tail_labels: int = 10

    #: Minimum number of canonical ``strategy_mode`` values that must
    #: be present in the dataset for ``pass`` (default: at least 2 of
    #: the 4 canonical modes - the brief expects observe+reject to be
    #: present alongside follow / pullback when the runtime has been
    #: live for any meaningful window).
    min_strategy_mode_coverage: int = 2

    #: Minimum number of canonical ``candidate_stage`` values that
    #: must be present.
    min_candidate_stage_coverage: int = 2

    #: Minimum number of ``opportunity_score`` buckets that must be
    #: covered.
    min_score_bucket_coverage: int = 2

    #: When True, the gate refuses to ``pass`` unless the dataset
    #: round-trips through ``export_validation_dataset_payload`` /
    #: ``load_validation_dataset_payload``.
    require_export_roundtrip: bool = True

    #: When True, the gate refuses to ``pass`` unless the dataset
    #: payload is replay-readable (every record has a non-empty
    #: ``opportunity_id`` + ``scan_batch_id``).
    require_replay_readable: bool = True

    @field_validator(
        "min_total_samples",
        "min_completed_tail_labels",
        "min_strategy_mode_coverage",
        "min_candidate_stage_coverage",
        "min_score_bucket_coverage",
    )
    @classmethod
    def _check_non_negative(cls, value: int) -> int:
        if int(value) < 0:
            raise ValueError(
                "StrategyValidationQualityGate thresholds must be >= 0"
            )
        return int(value)

    def to_payload(self) -> dict[str, Any]:
        return {
            "min_total_samples": int(self.min_total_samples),
            "min_completed_tail_labels": int(self.min_completed_tail_labels),
            "min_strategy_mode_coverage": int(
                self.min_strategy_mode_coverage
            ),
            "min_candidate_stage_coverage": int(
                self.min_candidate_stage_coverage
            ),
            "min_score_bucket_coverage": int(
                self.min_score_bucket_coverage
            ),
            "require_export_roundtrip": bool(self.require_export_roundtrip),
            "require_replay_readable": bool(self.require_replay_readable),
        }


# ---------------------------------------------------------------------------
# Quality gate (output)
# ---------------------------------------------------------------------------
class StrategyValidationQualityGateResult(BaseModel):
    """Result of a quality-gate evaluation.

    The ``gate_status`` is a *descriptive* label - one of
    ``pass`` / ``warn`` / ``fail``. It is NEVER an input to a
    trade-decision pipeline. The Risk Engine remains the single
    trade-decision gate.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    gate_status: str = "fail"
    reasons: tuple[str, ...] = Field(default_factory=tuple)
    sample_count: int = 0
    completed_tail_label_count: int = 0
    missing_modes: tuple[str, ...] = Field(default_factory=tuple)
    missing_stages: tuple[str, ...] = Field(default_factory=tuple)
    missing_buckets: tuple[str, ...] = Field(default_factory=tuple)
    missing_required_fields: tuple[str, ...] = Field(default_factory=tuple)
    export_roundtrip_ok: bool = False
    replay_readable: bool = False
    gate: StrategyValidationQualityGate = Field(
        default_factory=StrategyValidationQualityGate
    )
    schema_version: str = STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION

    @field_validator("gate_status")
    @classmethod
    def _check_status(cls, value: str) -> str:
        text = str(value).strip()
        if text not in QUALITY_GATE_STATUSES:
            raise ValueError(
                "gate_status must be one of "
                f"{QUALITY_GATE_STATUSES}; got {value!r}"
            )
        return text

    def to_payload(self) -> dict[str, Any]:
        return {
            "gate_status": str(self.gate_status),
            "reasons": list(self.reasons),
            "sample_count": int(self.sample_count),
            "completed_tail_label_count": int(
                self.completed_tail_label_count
            ),
            "missing_modes": list(self.missing_modes),
            "missing_stages": list(self.missing_stages),
            "missing_buckets": list(self.missing_buckets),
            "missing_required_fields": list(self.missing_required_fields),
            "export_roundtrip_ok": bool(self.export_roundtrip_ok),
            "replay_readable": bool(self.replay_readable),
            "gate": self.gate.to_payload(),
            "schema_version": str(self.schema_version),
        }


# ---------------------------------------------------------------------------
# Pure builders
# ---------------------------------------------------------------------------
def _record_from_sample(
    sample: StrategyValidationSample,
    *,
    report_id: str,
    source_event_id: str = "",
    schema_version: str = STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION,
) -> StrategyValidationDatasetRecord:
    return StrategyValidationDatasetRecord(
        report_id=str(report_id),
        opportunity_id=str(sample.opportunity_id),
        scan_batch_id=str(sample.scan_batch_id),
        symbol=str(sample.symbol),
        candidate_stage=str(sample.candidate_stage),
        strategy_mode=str(sample.strategy_mode),
        opportunity_score=float(sample.opportunity_score),
        early_tail_score=float(sample.early_tail_score),
        late_chase_risk=float(sample.late_chase_risk),
        cluster_id=str(sample.cluster_id),
        cluster_leader=(
            str(sample.cluster_leader)
            if sample.cluster_leader is not None
            else None
        ),
        tail_label=str(sample.tail_label),
        mfe_5m=float(sample.mfe_5m),
        mae_5m=float(sample.mae_5m),
        mfe_15m=float(sample.mfe_15m),
        mae_15m=float(sample.mae_15m),
        mfe_30m=float(sample.mfe_30m),
        mae_30m=float(sample.mae_30m),
        mfe_1h=float(sample.mfe_1h),
        mae_1h=float(sample.mae_1h),
        mfe_4h=float(sample.mfe_4h),
        mae_4h=float(sample.mae_4h),
        reached_2r=bool(sample.reached_2r),
        reached_3r=bool(sample.reached_3r),
        reached_5r=bool(sample.reached_5r),
        reached_10r=bool(sample.reached_10r),
        fake_breakout=bool(sample.fake_breakout),
        missed_tail=bool(sample.missed_tail),
        late_chase_failure=bool(sample.late_chase_failure),
        source_event_id=str(source_event_id or ""),
        schema_version=str(schema_version),
    )


def build_validation_dataset_from_samples(
    samples: Iterable[StrategyValidationSample],
    *,
    report_id: str,
    generated_at_ms: int = 0,
    source_event_ids: Mapping[str, str] | None = None,
    strategy_version: str = "phase_11c_1c_a.strategy.v1",
    scoring_version: str = "phase_11c_1c_a.scoring.v1",
    risk_config_version: str = "phase_11c_1c_a.risk_config.v1",
    state_machine_version: str = "phase_11c_1c_a.state_machine.v1",
    schema_version: str = STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION,
) -> StrategyValidationDataset:
    """Build a :class:`StrategyValidationDataset` from Phase
    11C.1C-C-B-A samples.

    The function is **pure**: no I/O, no clock read, no
    ``EventRepository.append_event`` call.

    ``source_event_ids`` is an optional ``opportunity_id`` ->
    ``event_id`` map; when supplied, every record carries the
    originating ``STRATEGY_VALIDATION_SAMPLE_CREATED`` event id so a
    downstream auditor can cross-reference the row back to events.db.
    Missing entries default to the empty string (the row is still
    valid; cross-referencing is best-effort).
    """
    samples_list = list(samples)
    sources = dict(source_event_ids or {})
    records = tuple(
        _record_from_sample(
            sample,
            report_id=report_id,
            source_event_id=sources.get(str(sample.opportunity_id), ""),
            schema_version=schema_version,
        )
        for sample in samples_list
    )
    summary = summarize_validation_dataset(
        records, schema_version=schema_version
    )
    return StrategyValidationDataset(
        report_id=str(report_id),
        generated_at_ms=int(generated_at_ms),
        records=records,
        summary=summary,
        strategy_version=str(strategy_version),
        scoring_version=str(scoring_version),
        risk_config_version=str(risk_config_version),
        state_machine_version=str(state_machine_version),
        schema_version=str(schema_version),
    )


def summarize_validation_dataset(
    records: Iterable[StrategyValidationDatasetRecord],
    *,
    schema_version: str = STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION,
) -> StrategyValidationDatasetSummary:
    """Aggregate dataset records into a
    :class:`StrategyValidationDatasetSummary`.

    The function is **pure**.
    """
    rows = list(records)
    n = len(rows)
    completed_count = sum(
        1 for r in rows if str(r.tail_label) in COMPLETED_TAIL_LABELS
    )
    symbols: list[str] = []
    seen_syms: set[str] = set()
    for r in rows:
        sym = str(r.symbol)
        if sym and sym not in seen_syms:
            seen_syms.add(sym)
            symbols.append(sym)
    cluster_ids: list[str] = []
    seen_clusters: set[str] = set()
    for r in rows:
        cid = str(r.cluster_id)
        if cid and cid not in seen_clusters:
            seen_clusters.add(cid)
            cluster_ids.append(cid)
    strategy_mode_counts: dict[str, int] = {}
    candidate_stage_counts: dict[str, int] = {}
    opp_bucket_counts: dict[str, int] = {}
    ets_bucket_counts: dict[str, int] = {}
    tail_label_counts: dict[str, int] = {}
    fake_breakout = 0
    missed_tail = 0
    late_chase_failure = 0
    for r in rows:
        strategy_mode_counts[str(r.strategy_mode)] = (
            strategy_mode_counts.get(str(r.strategy_mode), 0) + 1
        )
        candidate_stage_counts[str(r.candidate_stage)] = (
            candidate_stage_counts.get(str(r.candidate_stage), 0) + 1
        )
        opp_bucket = opportunity_score_bucket_for(r.opportunity_score)
        opp_bucket_counts[opp_bucket] = (
            opp_bucket_counts.get(opp_bucket, 0) + 1
        )
        ets_bucket = early_tail_score_bucket_for(r.early_tail_score)
        ets_bucket_counts[ets_bucket] = (
            ets_bucket_counts.get(ets_bucket, 0) + 1
        )
        tail_label_counts[str(r.tail_label)] = (
            tail_label_counts.get(str(r.tail_label), 0) + 1
        )
        if r.fake_breakout:
            fake_breakout += 1
        if r.missed_tail:
            missed_tail += 1
        if r.late_chase_failure:
            late_chase_failure += 1
    return StrategyValidationDatasetSummary(
        record_count=n,
        completed_tail_label_count=completed_count,
        symbols=tuple(symbols),
        strategy_mode_counts=strategy_mode_counts,
        candidate_stage_counts=candidate_stage_counts,
        opportunity_score_bucket_counts=opp_bucket_counts,
        early_tail_score_bucket_counts=ets_bucket_counts,
        tail_label_counts=tail_label_counts,
        cluster_ids=tuple(cluster_ids),
        fake_breakout_count=fake_breakout,
        missed_tail_count=missed_tail,
        late_chase_failure_count=late_chase_failure,
        schema_version=str(schema_version),
    )


# ---------------------------------------------------------------------------
# Quality gate
# ---------------------------------------------------------------------------
def _check_required_fields(
    payload_records: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Return the sorted tuple of missing required fields across the
    given dataset payload records. A field is *missing* if at least
    one record lacks it (``None`` is considered missing for non-Optional
    fields).
    """
    missing: set[str] = set()
    for row in payload_records:
        for field in REQUIRED_DATASET_RECORD_FIELDS:
            if field not in row:
                missing.add(field)
                continue
            # cluster_leader is allowed to be None per the contract,
            # but the brief lists it under fields we expect to see;
            # we surface it via REQUIRED_DATASET_RECORD_FIELDS only
            # when present, so do not penalise None.
            value = row.get(field)
            if field == "schema_version" and not value:
                missing.add(field)
    return tuple(sorted(missing))


def _check_replay_readable(
    payload_records: Sequence[Mapping[str, Any]],
) -> bool:
    """Replay-readable means every record has a non-empty
    ``opportunity_id`` and ``scan_batch_id`` so the replay engine
    can join the row back to the event log."""
    if not payload_records:
        return True  # vacuously true for an empty dataset
    for row in payload_records:
        if not str(row.get("opportunity_id") or "").strip():
            return False
        if not str(row.get("scan_batch_id") or "").strip():
            return False
    return True


def _try_export_roundtrip(
    dataset: StrategyValidationDataset,
) -> bool:
    """Attempt a JSON-safe export -> load round-trip; returns True
    when the round-trip yields an equivalent dataset."""
    try:
        payload = export_validation_dataset_payload(dataset)
        loaded = load_validation_dataset_payload(payload)
    except Exception:
        return False
    if loaded.report_id != dataset.report_id:
        return False
    if len(loaded.records) != len(dataset.records):
        return False
    for original, restored in zip(dataset.records, loaded.records):
        if original.opportunity_id != restored.opportunity_id:
            return False
        if original.symbol != restored.symbol:
            return False
        if original.tail_label != restored.tail_label:
            return False
    return True


def evaluate_validation_dataset_quality(
    dataset: StrategyValidationDataset,
    *,
    gate: StrategyValidationQualityGate | None = None,
) -> StrategyValidationQualityGateResult:
    """Evaluate the Phase 11C.1C-C-B-B-A quality gate v0 against a
    :class:`StrategyValidationDataset`.

    The function is **pure** - no I/O, no clock read, no event emit.
    The result is descriptive: ``pass`` / ``warn`` / ``fail`` is a
    label for human review, NEVER an input to a trade-decision
    pipeline.
    """
    cfg = gate or StrategyValidationQualityGate()
    summary = dataset.summary
    payload = dataset.to_payload()
    payload_records = list(payload.get("records") or [])

    reasons: list[str] = []
    sample_count = int(summary.record_count)
    completed_count = int(summary.completed_tail_label_count)

    # Coverage diagnostics.
    present_modes = set(str(k) for k in summary.strategy_mode_counts.keys())
    present_stages = set(
        str(k) for k in summary.candidate_stage_counts.keys()
    )
    present_buckets = set(
        str(k) for k in summary.opportunity_score_bucket_counts.keys()
    )
    missing_modes = tuple(
        m for m in CANONICAL_STRATEGY_MODES if m not in present_modes
    )
    missing_stages = tuple(
        s for s in CANONICAL_CANDIDATE_STAGES if s not in present_stages
    )
    missing_buckets = tuple(
        b for b in OPPORTUNITY_SCORE_BUCKET_LABELS if b not in present_buckets
    )

    # Required field check.
    missing_required = _check_required_fields(payload_records)

    # Replay-readable + export round-trip.
    replay_readable = _check_replay_readable(payload_records)
    export_ok = _try_export_roundtrip(dataset)

    # Decide gate status. Hierarchy:
    #   1. fail  - structural integrity broken (required field
    #              missing, export round-trip broken when required,
    #              not replay-readable when required, sample count
    #              below half min)
    #   2. warn  - acceptable structurally but coverage / sample
    #              count below thresholds
    #   3. pass  - every threshold met
    fail = False
    warn = False

    if missing_required:
        fail = True
        reasons.append(
            "missing_required_fields=" + ",".join(missing_required)
        )

    if cfg.require_export_roundtrip and not export_ok:
        fail = True
        reasons.append("export_roundtrip_failed")

    if cfg.require_replay_readable and not replay_readable:
        fail = True
        reasons.append("not_replay_readable")

    # Sample-count gating.
    if sample_count < max(1, cfg.min_total_samples // 2):
        # Below half the minimum -> structural fail (the dataset is
        # too thin to be useful).
        if cfg.min_total_samples > 0:
            fail = True
            reasons.append(
                f"sample_count_below_half_min={sample_count}<"
                f"{max(1, cfg.min_total_samples // 2)}"
            )
    elif sample_count < cfg.min_total_samples:
        warn = True
        reasons.append(
            f"sample_count_below_min={sample_count}<{cfg.min_total_samples}"
        )

    if completed_count < cfg.min_completed_tail_labels:
        warn = True
        reasons.append(
            f"completed_tail_labels_below_min={completed_count}<"
            f"{cfg.min_completed_tail_labels}"
        )

    # Coverage gating.
    canonical_mode_present = sum(
        1 for m in CANONICAL_STRATEGY_MODES if m in present_modes
    )
    if canonical_mode_present < cfg.min_strategy_mode_coverage:
        warn = True
        reasons.append(
            f"strategy_mode_coverage_below_min={canonical_mode_present}<"
            f"{cfg.min_strategy_mode_coverage}"
        )

    canonical_stage_present = sum(
        1 for s in CANONICAL_CANDIDATE_STAGES if s in present_stages
    )
    if canonical_stage_present < cfg.min_candidate_stage_coverage:
        warn = True
        reasons.append(
            f"candidate_stage_coverage_below_min={canonical_stage_present}<"
            f"{cfg.min_candidate_stage_coverage}"
        )

    canonical_bucket_present = sum(
        1
        for b in OPPORTUNITY_SCORE_BUCKET_LABELS
        if b in present_buckets
    )
    if canonical_bucket_present < cfg.min_score_bucket_coverage:
        warn = True
        reasons.append(
            f"score_bucket_coverage_below_min={canonical_bucket_present}<"
            f"{cfg.min_score_bucket_coverage}"
        )

    if fail:
        gate_status = "fail"
    elif warn:
        gate_status = "warn"
    else:
        gate_status = "pass"
        reasons.append("all_quality_gate_thresholds_met")

    return StrategyValidationQualityGateResult(
        gate_status=gate_status,
        reasons=tuple(reasons),
        sample_count=sample_count,
        completed_tail_label_count=completed_count,
        missing_modes=tuple(missing_modes),
        missing_stages=tuple(missing_stages),
        missing_buckets=tuple(missing_buckets),
        missing_required_fields=tuple(missing_required),
        export_roundtrip_ok=bool(export_ok),
        replay_readable=bool(replay_readable),
        gate=cfg,
        schema_version=STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION,
    )


# ---------------------------------------------------------------------------
# Export / Replay (round-trip)
# ---------------------------------------------------------------------------
def export_validation_dataset_payload(
    dataset: StrategyValidationDataset,
) -> dict[str, Any]:
    """Return a JSON-safe dict for the dataset.

    The function is **pure** - it does not write to disk. The runner /
    daily-report builder is responsible for serialising the dict to
    bytes.
    """
    return dataset.to_payload()


def load_validation_dataset_payload(
    payload: Mapping[str, Any],
) -> StrategyValidationDataset:
    """Reconstruct a :class:`StrategyValidationDataset` from a payload
    produced by :func:`export_validation_dataset_payload`.

    Tolerates payloads from old schema_versions: missing optional
    fields default to the v0 defaults so a future PR can extend the
    contract without breaking replay.
    """
    if not isinstance(payload, Mapping):
        raise TypeError(
            "load_validation_dataset_payload requires a Mapping; got "
            f"{type(payload).__name__}"
        )

    raw_records = payload.get("records") or []
    records: list[StrategyValidationDatasetRecord] = []
    for row in raw_records:
        if not isinstance(row, Mapping):
            continue
        record_kwargs = {
            "report_id": str(row.get("report_id", payload.get("report_id", "") or "")),
            "opportunity_id": str(row.get("opportunity_id") or ""),
            "scan_batch_id": str(row.get("scan_batch_id") or ""),
            "symbol": str(row.get("symbol") or ""),
            "candidate_stage": str(row.get("candidate_stage") or "early"),
            "strategy_mode": str(row.get("strategy_mode") or "observe"),
            "opportunity_score": float(row.get("opportunity_score") or 0.0),
            "early_tail_score": float(row.get("early_tail_score") or 0.0),
            "late_chase_risk": float(row.get("late_chase_risk") or 0.0),
            "cluster_id": str(row.get("cluster_id") or "unknown"),
            "cluster_leader": (
                str(row.get("cluster_leader"))
                if row.get("cluster_leader") is not None
                else None
            ),
            "tail_label": str(row.get("tail_label") or "unresolved"),
            "mfe_5m": float(row.get("mfe_5m") or 0.0),
            "mae_5m": float(row.get("mae_5m") or 0.0),
            "mfe_15m": float(row.get("mfe_15m") or 0.0),
            "mae_15m": float(row.get("mae_15m") or 0.0),
            "mfe_30m": float(row.get("mfe_30m") or 0.0),
            "mae_30m": float(row.get("mae_30m") or 0.0),
            "mfe_1h": float(row.get("mfe_1h") or 0.0),
            "mae_1h": float(row.get("mae_1h") or 0.0),
            "mfe_4h": float(row.get("mfe_4h") or 0.0),
            "mae_4h": float(row.get("mae_4h") or 0.0),
            "reached_2r": bool(row.get("reached_2r") or False),
            "reached_3r": bool(row.get("reached_3r") or False),
            "reached_5r": bool(row.get("reached_5r") or False),
            "reached_10r": bool(row.get("reached_10r") or False),
            "fake_breakout": bool(row.get("fake_breakout") or False),
            "missed_tail": bool(row.get("missed_tail") or False),
            "late_chase_failure": bool(
                row.get("late_chase_failure") or False
            ),
            "source_event_id": str(row.get("source_event_id") or ""),
            "schema_version": str(
                row.get("schema_version")
                or STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION
            ),
        }
        records.append(StrategyValidationDatasetRecord(**record_kwargs))

    summary_payload = payload.get("summary") or {}
    if isinstance(summary_payload, Mapping):
        summary = StrategyValidationDatasetSummary(
            record_count=int(summary_payload.get("record_count") or 0),
            completed_tail_label_count=int(
                summary_payload.get("completed_tail_label_count") or 0
            ),
            symbols=tuple(summary_payload.get("symbols") or ()),
            strategy_mode_counts=dict(
                summary_payload.get("strategy_mode_counts") or {}
            ),
            candidate_stage_counts=dict(
                summary_payload.get("candidate_stage_counts") or {}
            ),
            opportunity_score_bucket_counts=dict(
                summary_payload.get("opportunity_score_bucket_counts") or {}
            ),
            early_tail_score_bucket_counts=dict(
                summary_payload.get("early_tail_score_bucket_counts") or {}
            ),
            tail_label_counts=dict(
                summary_payload.get("tail_label_counts") or {}
            ),
            cluster_ids=tuple(summary_payload.get("cluster_ids") or ()),
            fake_breakout_count=int(
                summary_payload.get("fake_breakout_count") or 0
            ),
            missed_tail_count=int(
                summary_payload.get("missed_tail_count") or 0
            ),
            late_chase_failure_count=int(
                summary_payload.get("late_chase_failure_count") or 0
            ),
            schema_version=str(
                summary_payload.get("schema_version")
                or STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION
            ),
        )
    else:
        summary = summarize_validation_dataset(records)

    return StrategyValidationDataset(
        report_id=str(payload.get("report_id") or ""),
        generated_at_ms=int(payload.get("generated_at_ms") or 0),
        records=tuple(records),
        summary=summary,
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
            or STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION
        ),
    )


__all__ = [
    # Constants
    "STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION",
    "KNOWN_STRATEGY_VALIDATION_DATASET_SCHEMA_VERSIONS",
    "STRATEGY_VALIDATION_DATASET_VERSION",
    "STRATEGY_VALIDATION_DATASET_SOURCE_PHASE",
    "QUALITY_GATE_STATUSES",
    "CANONICAL_STRATEGY_MODES",
    "CANONICAL_CANDIDATE_STAGES",
    "COMPLETED_TAIL_LABELS",
    "REQUIRED_DATASET_RECORD_FIELDS",
    # Models
    "StrategyValidationDatasetRecord",
    "StrategyValidationDatasetSummary",
    "StrategyValidationDataset",
    "StrategyValidationQualityGate",
    "StrategyValidationQualityGateResult",
    # Pure functions
    "build_validation_dataset_from_samples",
    "summarize_validation_dataset",
    "evaluate_validation_dataset_quality",
    "export_validation_dataset_payload",
    "load_validation_dataset_payload",
]
