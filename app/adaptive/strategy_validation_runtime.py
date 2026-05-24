"""Phase 11C.1C-C-B-A - Strategy Validation Lab v0 runtime.

The Phase 11C.1C-C-A :class:`LabelQueueRuntime` produces forward
MFE / MAE / ``tail_label`` outcomes per ACTIVE candidate. This
runtime turns those outcomes into:

  - one :class:`StrategyValidationSample` per completed opportunity;
  - aggregated cohort stats (per mode / stage / bucket);
  - cluster-leader validation + cluster exposure assessments;
  - one :class:`StrategyValidationReport` per scheduled flush.

It emits the seven Phase 11C.1C-C-B-A typed events through
:class:`EventRepository` so Reflection / Replay / Export can carry
the new sub-blocks forward without re-deriving them.

Phase 11C.1C-C-B-A boundary
---------------------------

This runtime:

  - records strategy validation outcomes ONLY;
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
  - the ``suggested_cluster_action`` it emits is **paper / report
    only**. The Risk Engine remains the single trade-decision gate.

The runtime is the single owner of the in-process sample buffer.
The :class:`WSRadarChainDriver` calls
:meth:`StrategyValidationRuntime.observe_label_record` once per
candidate per chain pass; the runner calls
:meth:`StrategyValidationRuntime.flush_report` periodically to
generate fresh reports.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping

from loguru import logger

from app.adaptive.label_runtime import LabelTrackingRecord
from app.adaptive.models import AdaptiveCandidateContext
from app.adaptive.strategy_validation import (
    DEFAULT_OVEREXPOSURE_WARNING_THRESHOLD,
    EARLY_TAIL_SCORE_BUCKET_LABELS,
    OPPORTUNITY_SCORE_BUCKET_LABELS,
    STRATEGY_VALIDATION_PRIMARY_WINDOW,
    STRATEGY_VALIDATION_SCHEMA_VERSION,
    STRATEGY_VALIDATION_SOURCE_PHASE,
    STRATEGY_VALIDATION_VERSION,
    StrategyValidationReport,
    StrategyValidationSample,
    aggregate_by_candidate_stage,
    aggregate_by_early_tail_score_bucket,
    aggregate_by_opportunity_score_bucket,
    aggregate_by_strategy_mode,
    aggregate_tail_label_distribution,
    assess_cluster_exposure,
    build_strategy_validation_report,
    build_strategy_validation_sample,
    evaluate_cluster_leader_performance,
)
from app.adaptive.strategy_validation_dataset import (
    STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION,
    STRATEGY_VALIDATION_DATASET_SOURCE_PHASE,
    STRATEGY_VALIDATION_DATASET_VERSION,
    StrategyValidationDataset,
    StrategyValidationQualityGate,
    StrategyValidationQualityGateResult,
    build_validation_dataset_from_samples,
    evaluate_validation_dataset_quality,
    export_validation_dataset_payload,
)
from app.adaptive.paper_alpha_gate import (
    PAPER_ALPHA_GATE_SCHEMA_VERSION,
    PAPER_ALPHA_GATE_SOURCE_PHASE,
    PAPER_ALPHA_GATE_VERSION,
    PaperAlphaGateInput,
    PaperAlphaGateReport,
    build_paper_alpha_gate_input,
    build_paper_alpha_gate_report,
    export_paper_alpha_gate_payload,
)
from app.adaptive.regime_cluster_evidence_pack import (
    REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION,
    REGIME_CLUSTER_EVIDENCE_SOURCE_PHASE,
    REGIME_CLUSTER_EVIDENCE_VERSION,
    RegimeClusterEvidencePack,
    RegimeClusterEvidencePackStatus,
    build_regime_cluster_evidence_input,
    build_regime_cluster_evidence_pack,
    export_regime_cluster_evidence_payload,
)
from app.core.clock import now_ms
from app.core.events import Event, EventType
from app.database.repositories import EventRepository


@dataclass(frozen=True)
class StrategyValidationRuntimeConfig:
    """Tunable knobs for the Phase 11C.1C-C-B-A Lab v0 runtime.

    Every threshold the runtime consumes lives here so the brief's
    "thresholds must be configurable, not hard-coded" rule holds at
    the YAML / boot layer too.

    Phase 11C.1C-C-B-B-A extends the config with five quality-gate
    thresholds. The defaults match
    :class:`StrategyValidationQualityGate`. Setting
    ``dataset_enabled=False`` disables the Phase 11C.1C-C-B-B-A
    dataset / quality-gate slice without affecting the
    Phase 11C.1C-C-B-A Lab v0 contract.
    """

    enabled: bool = True
    max_samples: int = 2_000
    primary_window: str = STRATEGY_VALIDATION_PRIMARY_WINDOW
    overexposure_warning_threshold: int = (
        DEFAULT_OVEREXPOSURE_WARNING_THRESHOLD
    )
    top_symbol_limit: int = 10
    # Phase 11C.1C-C-B-B-A - Strategy Validation Dataset Builder &
    # Quality Gate v0 thresholds. Paper / report only; do NOT
    # authorise real trades.
    dataset_enabled: bool = True
    quality_gate_min_total_samples: int = 20
    quality_gate_min_completed_tail_labels: int = 10
    quality_gate_min_strategy_mode_coverage: int = 2
    quality_gate_min_candidate_stage_coverage: int = 2
    quality_gate_min_score_bucket_coverage: int = 2
    quality_gate_require_export_roundtrip: bool = True
    quality_gate_require_replay_readable: bool = True
    # Phase 11C.1C-C-B-B-B-A - Paper Alpha Gate v0 thresholds. Paper
    # / report only; the verdict is descriptive (``PASS`` /
    # ``WARN`` / ``FAIL`` / ``INCONCLUSIVE``) and **MUST NEVER**
    # trigger a real trade or modify the Risk Engine / Execution
    # FSM.
    paper_alpha_gate_enabled: bool = True
    paper_alpha_min_total_samples: int = 20
    paper_alpha_min_completed_tail_labels: int = 10
    paper_alpha_min_bucket_samples: int = 5
    paper_alpha_high_bucket_advantage: float = 0.10
    paper_alpha_late_chase_fake_breakout_rate: float = 0.30
    paper_alpha_missed_alpha_strong_tail_rate: float = 0.20
    paper_alpha_follow_fake_breakout_rate: float = 0.30
    paper_alpha_leader_preference_advantage: float = 0.10
    # Phase 11C.1C-C-B-B-B-B - Regime & Cluster Cohort Evidence Pack
    # v0 thresholds. Paper / report / evidence only; the per-cohort
    # ``status`` (``INSUFFICIENT_SAMPLE`` / ``OBSERVE_ONLY`` /
    # ``WARNING`` / ``EVIDENCE_SIGNAL``) is descriptive and **MUST
    # NEVER** trigger a real trade or modify the Risk Engine /
    # Execution FSM.
    regime_cluster_evidence_pack_enabled: bool = True
    regime_cluster_min_total_samples: int = 20
    regime_cluster_min_completed_tail_labels: int = 10
    regime_cluster_min_cohort_samples: int = 5
    regime_cluster_strong_tail_signal_rate: float = 0.30
    regime_cluster_reached_3r_signal_rate: float = 0.20
    regime_cluster_reached_5r_signal_rate: float = 0.10
    regime_cluster_fake_breakout_warning_rate: float = 0.30
    regime_cluster_missed_tail_warning_rate: float = 0.20
    regime_cluster_late_chase_failure_warning_rate: float = 0.20
    regime_cluster_leader_preference_advantage: float = 0.10
    regime_cluster_high_bucket_advantage: float = 0.10

    @staticmethod
    def from_mapping(
        mapping: Mapping[str, Any] | None,
    ) -> "StrategyValidationRuntimeConfig":
        if not mapping:
            return StrategyValidationRuntimeConfig()
        kwargs: dict[str, Any] = {}
        for f in (
            "enabled",
            "max_samples",
            "primary_window",
            "overexposure_warning_threshold",
            "top_symbol_limit",
            "dataset_enabled",
            "quality_gate_min_total_samples",
            "quality_gate_min_completed_tail_labels",
            "quality_gate_min_strategy_mode_coverage",
            "quality_gate_min_candidate_stage_coverage",
            "quality_gate_min_score_bucket_coverage",
            "quality_gate_require_export_roundtrip",
            "quality_gate_require_replay_readable",
            "paper_alpha_gate_enabled",
            "paper_alpha_min_total_samples",
            "paper_alpha_min_completed_tail_labels",
            "paper_alpha_min_bucket_samples",
            "paper_alpha_high_bucket_advantage",
            "paper_alpha_late_chase_fake_breakout_rate",
            "paper_alpha_missed_alpha_strong_tail_rate",
            "paper_alpha_follow_fake_breakout_rate",
            "paper_alpha_leader_preference_advantage",
            "regime_cluster_evidence_pack_enabled",
            "regime_cluster_min_total_samples",
            "regime_cluster_min_completed_tail_labels",
            "regime_cluster_min_cohort_samples",
            "regime_cluster_strong_tail_signal_rate",
            "regime_cluster_reached_3r_signal_rate",
            "regime_cluster_reached_5r_signal_rate",
            "regime_cluster_fake_breakout_warning_rate",
            "regime_cluster_missed_tail_warning_rate",
            "regime_cluster_late_chase_failure_warning_rate",
            "regime_cluster_leader_preference_advantage",
            "regime_cluster_high_bucket_advantage",
        ):
            if f in mapping and mapping[f] is not None:
                kwargs[f] = mapping[f]
        return StrategyValidationRuntimeConfig(**kwargs)

    @staticmethod
    def from_settings_section(
        section: Any,
    ) -> "StrategyValidationRuntimeConfig":
        if section is None:
            return StrategyValidationRuntimeConfig()
        if hasattr(section, "model_dump"):
            return StrategyValidationRuntimeConfig.from_mapping(
                section.model_dump()
            )
        if isinstance(section, Mapping):
            return StrategyValidationRuntimeConfig.from_mapping(section)
        attrs: dict[str, Any] = {}
        for f in (
            "enabled",
            "max_samples",
            "primary_window",
            "overexposure_warning_threshold",
            "top_symbol_limit",
            "dataset_enabled",
            "quality_gate_min_total_samples",
            "quality_gate_min_completed_tail_labels",
            "quality_gate_min_strategy_mode_coverage",
            "quality_gate_min_candidate_stage_coverage",
            "quality_gate_min_score_bucket_coverage",
            "quality_gate_require_export_roundtrip",
            "quality_gate_require_replay_readable",
            "paper_alpha_gate_enabled",
            "paper_alpha_min_total_samples",
            "paper_alpha_min_completed_tail_labels",
            "paper_alpha_min_bucket_samples",
            "paper_alpha_high_bucket_advantage",
            "paper_alpha_late_chase_fake_breakout_rate",
            "paper_alpha_missed_alpha_strong_tail_rate",
            "paper_alpha_follow_fake_breakout_rate",
            "paper_alpha_leader_preference_advantage",
            "regime_cluster_evidence_pack_enabled",
            "regime_cluster_min_total_samples",
            "regime_cluster_min_completed_tail_labels",
            "regime_cluster_min_cohort_samples",
            "regime_cluster_strong_tail_signal_rate",
            "regime_cluster_reached_3r_signal_rate",
            "regime_cluster_reached_5r_signal_rate",
            "regime_cluster_fake_breakout_warning_rate",
            "regime_cluster_missed_tail_warning_rate",
            "regime_cluster_late_chase_failure_warning_rate",
            "regime_cluster_leader_preference_advantage",
            "regime_cluster_high_bucket_advantage",
        ):
            if hasattr(section, f):
                attrs[f] = getattr(section, f)
        return StrategyValidationRuntimeConfig.from_mapping(attrs)

    def quality_gate(self) -> StrategyValidationQualityGate:
        """Build the :class:`StrategyValidationQualityGate` carried
        by this config so the runtime / pure functions consume the
        same thresholds."""
        return StrategyValidationQualityGate(
            min_total_samples=int(self.quality_gate_min_total_samples),
            min_completed_tail_labels=int(
                self.quality_gate_min_completed_tail_labels
            ),
            min_strategy_mode_coverage=int(
                self.quality_gate_min_strategy_mode_coverage
            ),
            min_candidate_stage_coverage=int(
                self.quality_gate_min_candidate_stage_coverage
            ),
            min_score_bucket_coverage=int(
                self.quality_gate_min_score_bucket_coverage
            ),
            require_export_roundtrip=bool(
                self.quality_gate_require_export_roundtrip
            ),
            require_replay_readable=bool(
                self.quality_gate_require_replay_readable
            ),
        )


@dataclass
class _SampleEntry:
    """Mutable sample wrapper - keeps the source event id so a
    later report can be cross-referenced back to the originating
    label-tracking event."""

    sample: StrategyValidationSample
    source_event_id: str
    created_at_ms: int


class StrategyValidationRuntime:
    """Phase 11C.1C-C-B-A Strategy Validation Lab v0 runtime.

    Wires into the WS-radar event chain:

      - :meth:`observe_label_record` is called by the chain after
        every Phase 11C.1C-C-A ``LABEL_QUEUE_ENQUEUED`` /
        ``LABEL_TRACKING_STARTED`` / ``TAIL_LABEL_ASSIGNED`` event
        with the matching :class:`LabelTrackingRecord` and adaptive
        context;
      - :meth:`flush_report` is called periodically by the runner to
        emit the seven Phase 11C.1C-C-B-A typed events;
      - :meth:`metrics_payload` returns the daily-report aggregates;
      - every event flows through :class:`EventRepository` only.

    The runtime never opens a socket, never reads ``os.environ``,
    never imports an exchange / Telegram / LLM library, never
    mutates settings, and never authorises a real trade. The entire
    surface is paper / virtual.
    """

    SOURCE_MODULE = "adaptive.strategy_validation_runtime"
    SOURCE_PHASE = STRATEGY_VALIDATION_SOURCE_PHASE

    def __init__(
        self,
        *,
        event_repo: EventRepository,
        config: StrategyValidationRuntimeConfig | None = None,
        clock_ms_fn=None,
    ) -> None:
        self._event_repo = event_repo
        self._config = config or StrategyValidationRuntimeConfig()
        self._clock_ms_fn = clock_ms_fn or now_ms
        # Identity-based sample index so a candidate that completes
        # the primary window once + later expires a longer window
        # cannot land twice in the report.
        self._samples_by_opportunity: dict[str, _SampleEntry] = {}
        # Counters surfaced to the daily report.
        self._sample_created_count = 0
        self._report_generated_count = 0
        self._strategy_mode_validated_count = 0
        self._candidate_stage_validated_count = 0
        self._score_bucket_validated_count = 0
        self._cluster_exposure_assessed_count = 0
        self._cluster_leader_validated_count = 0
        self._samples_dropped_capacity = 0
        # Latest report - so the runner can surface it on shutdown
        # without re-flushing.
        self._latest_report: StrategyValidationReport | None = None
        self._latest_report_metrics: dict[str, Any] | None = None
        # Phase 11C.1C-C-B-B-A - dataset / quality-gate counters +
        # the most-recent dataset payload + gate result so the
        # daily-report builder can render the new section.
        self._dataset_built_count = 0
        self._dataset_exported_count = 0
        self._quality_gate_evaluated_count = 0
        self._latest_dataset: StrategyValidationDataset | None = None
        self._latest_quality_gate_result: (
            StrategyValidationQualityGateResult | None
        ) = None
        # ``opportunity_id`` -> originating
        # ``STRATEGY_VALIDATION_SAMPLE_CREATED`` event id. Built as
        # samples are emitted so dataset records carry
        # ``source_event_id`` without re-querying events.db.
        self._sample_event_ids: dict[str, str] = {}
        # Phase 11C.1C-C-B-B-B-A - Paper Alpha Gate v0 counters +
        # latest report cache. Paper / report only; the verdict is
        # descriptive and **MUST NEVER trigger a real trade**.
        self._paper_alpha_gate_evaluated_count = 0
        self._paper_alpha_rule_evaluated_count = 0
        self._paper_alpha_cohort_evaluated_count = 0
        self._paper_alpha_report_generated_count = 0
        self._latest_paper_alpha_report: PaperAlphaGateReport | None = None
        # Phase 11C.1C-C-B-B-B-B - Regime & Cluster Cohort Evidence
        # Pack v0 counters + latest pack cache. Paper / report /
        # evidence only; the per-cohort status is descriptive and
        # **MUST NEVER trigger a real trade** or modify the Risk
        # Engine / Execution FSM.
        self._regime_cluster_evidence_pack_generated_count = 0
        self._regime_cluster_cohort_summary_generated_count = 0
        self._latest_regime_cluster_evidence_pack: (
            RegimeClusterEvidencePack | None
        ) = None
        # ``opportunity_id`` -> ``market_regime`` cache. Populated
        # by :meth:`observe_market_regime` so the evidence pack
        # builder can attach the regime to dataset records without
        # re-querying events.db. Records whose opportunity_id is
        # missing from this cache safely degrade to "unknown".
        self._regime_by_opportunity: dict[str, str] = {}

    # ------------------------------------------------------------------
    @property
    def config(self) -> StrategyValidationRuntimeConfig:
        return self._config

    @property
    def samples(self) -> tuple[StrategyValidationSample, ...]:
        return tuple(e.sample for e in self._samples_by_opportunity.values())

    @property
    def sample_count(self) -> int:
        return len(self._samples_by_opportunity)

    @property
    def latest_report(self) -> StrategyValidationReport | None:
        return self._latest_report

    @property
    def sample_created_count(self) -> int:
        return self._sample_created_count

    @property
    def report_generated_count(self) -> int:
        return self._report_generated_count

    # ------------------------------------------------------------------
    # Phase 11C.1C-C-B-B-A - dataset / quality-gate accessors. Read-
    # only views; mutations happen exclusively in flush_report().
    # ------------------------------------------------------------------
    @property
    def latest_dataset(self) -> StrategyValidationDataset | None:
        return self._latest_dataset

    @property
    def latest_quality_gate_result(
        self,
    ) -> StrategyValidationQualityGateResult | None:
        return self._latest_quality_gate_result

    @property
    def dataset_built_count(self) -> int:
        return self._dataset_built_count

    @property
    def dataset_exported_count(self) -> int:
        return self._dataset_exported_count

    @property
    def quality_gate_evaluated_count(self) -> int:
        return self._quality_gate_evaluated_count

    # ------------------------------------------------------------------
    # Phase 11C.1C-C-B-B-B-A - Paper Alpha Gate v0 accessors. Read-
    # only views; mutations happen exclusively in flush_report().
    # ------------------------------------------------------------------
    @property
    def latest_paper_alpha_report(self) -> PaperAlphaGateReport | None:
        return self._latest_paper_alpha_report

    @property
    def paper_alpha_gate_evaluated_count(self) -> int:
        return self._paper_alpha_gate_evaluated_count

    @property
    def paper_alpha_rule_evaluated_count(self) -> int:
        return self._paper_alpha_rule_evaluated_count

    @property
    def paper_alpha_cohort_evaluated_count(self) -> int:
        return self._paper_alpha_cohort_evaluated_count

    @property
    def paper_alpha_report_generated_count(self) -> int:
        return self._paper_alpha_report_generated_count

    # ------------------------------------------------------------------
    # Phase 11C.1C-C-B-B-B-B - Regime & Cluster Cohort Evidence Pack
    # v0 accessors. Read-only views; mutations happen exclusively in
    # flush_report() (or via observe_market_regime() which only
    # populates the per-opportunity regime cache).
    # ------------------------------------------------------------------
    @property
    def latest_regime_cluster_evidence_pack(
        self,
    ) -> RegimeClusterEvidencePack | None:
        return self._latest_regime_cluster_evidence_pack

    @property
    def regime_cluster_evidence_pack_generated_count(self) -> int:
        return self._regime_cluster_evidence_pack_generated_count

    @property
    def regime_cluster_cohort_summary_generated_count(self) -> int:
        return self._regime_cluster_cohort_summary_generated_count

    def observe_market_regime(
        self,
        *,
        opportunity_id: str,
        market_regime: str,
    ) -> None:
        """Record the ``market_regime`` snapshot taken when an
        adaptive context was assembled for ``opportunity_id``.

        Paper / virtual only; storing the regime does NOT authorise
        opening a position. The cache is consumed by
        :meth:`flush_report` to attach the regime to dataset rows
        before the evidence pack is built.

        ``observe_market_regime`` is intentionally a tiny helper -
        the WS-radar driver calls it after every
        ``MARKET_REGIME_ASSESSED`` it would have already emitted.
        Records whose opportunity_id is missing from the cache
        safely degrade to ``"unknown"`` per the brief.
        """
        opp_id = str(opportunity_id or "").strip()
        if not opp_id:
            return
        regime = str(market_regime or "").strip()
        if not regime:
            return
        self._regime_by_opportunity[opp_id] = regime

    # ------------------------------------------------------------------
    def observe_label_record(
        self,
        *,
        label_record: LabelTrackingRecord | Mapping[str, Any] | None,
        adaptive: AdaptiveCandidateContext | Mapping[str, Any] | None,
        source_event_id: str = "",
        sample_created_ts: int | None = None,
    ) -> StrategyValidationSample | None:
        """Build a :class:`StrategyValidationSample` and emit a
        ``STRATEGY_VALIDATION_SAMPLE_CREATED`` event.

        Idempotent on ``opportunity_id``: a duplicate observation for
        the same opportunity overwrites the existing sample (so a
        later, more-complete window can replace an earlier partial
        one) but does NOT re-emit the event.

        Returns the resulting :class:`StrategyValidationSample`, or
        ``None`` when the runtime is disabled / capacity-bound.
        """
        if not self._config.enabled:
            return None
        ts_value = (
            int(sample_created_ts)
            if sample_created_ts is not None
            else int(self._clock_ms_fn())
        )
        try:
            sample = build_strategy_validation_sample(
                label_record=label_record,
                adaptive=adaptive,
                sample_created_ts=ts_value,
                primary_window=self._config.primary_window,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "[phase11c.1c-c-b-a] build_strategy_validation_sample "
                "failed: {}",
                exc,
            )
            return None
        opp_id = str(sample.opportunity_id or "")
        if not opp_id:
            # Fallback identity: (symbol, sample_created_ts) so a
            # legacy event without an opportunity_id still records
            # an outcome, but cannot collide with a real opp.
            opp_id = f"__fallback__:{sample.symbol}:{ts_value}"
        is_new = opp_id not in self._samples_by_opportunity
        if is_new and len(self._samples_by_opportunity) >= int(
            self._config.max_samples
        ):
            self._samples_dropped_capacity += 1
            logger.debug(
                "[phase11c.1c-c-b-a] strategy validation buffer at "
                "capacity={}, dropping symbol={} opp={}",
                self._config.max_samples,
                sample.symbol,
                opp_id,
            )
            return None
        entry = _SampleEntry(
            sample=sample,
            source_event_id=str(source_event_id or ""),
            created_at_ms=ts_value,
        )
        self._samples_by_opportunity[opp_id] = entry
        if is_new:
            self._emit_sample_created(
                sample=sample, source_event_id=str(source_event_id or "")
            )
        return sample

    # ------------------------------------------------------------------
    def flush_report(
        self,
        *,
        report_id: str | None = None,
        generated_at_ms: int | None = None,
        emit_events: bool = True,
        build_dataset: bool | None = None,
        evaluate_quality_gate: bool | None = None,
    ) -> StrategyValidationReport:
        """Build the latest :class:`StrategyValidationReport` and emit
        the per-cohort + per-cluster events.

        Phase 11C.1C-C-B-A boundary - the report is paper / report
        only. ``emit_events=True`` does NOT authorise any real trade;
        the seven new event types are descriptive.

        Phase 11C.1C-C-B-B-A extension - when ``build_dataset`` (or
        ``evaluate_quality_gate``) is True, this method also builds
        the :class:`StrategyValidationDataset`, emits
        ``STRATEGY_VALIDATION_DATASET_BUILT`` /
        ``STRATEGY_VALIDATION_DATASET_EXPORTED``, evaluates the
        quality gate, and emits
        ``STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED``. When the
        kwargs are left at ``None``, the runtime falls back to the
        config-level ``dataset_enabled`` flag so the runner does not
        need to opt in explicitly. None of the new events authorises
        a real trade; ``gate_status`` is a descriptive label only.
        """
        ts_value = (
            int(generated_at_ms)
            if generated_at_ms is not None
            else int(self._clock_ms_fn())
        )
        rid = str(report_id or f"strategy-validation-{uuid.uuid4()}")
        samples = self.samples
        report = build_strategy_validation_report(
            samples,
            report_id=rid,
            generated_at_ms=ts_value,
            primary_window=self._config.primary_window,
            overexposure_warning_threshold=int(
                self._config.overexposure_warning_threshold
            ),
            top_symbol_limit=int(self._config.top_symbol_limit),
            schema_version=STRATEGY_VALIDATION_SCHEMA_VERSION,
        )
        self._latest_report = report
        self._latest_report_metrics = self._build_metrics_payload(report)
        if emit_events:
            self._emit_report_events(report=report, ts_ms=ts_value)

        # Phase 11C.1C-C-B-B-A - dataset / quality-gate slice. When
        # the runtime config opts in (default True), build the
        # dataset and evaluate the gate so the daily-report builder
        # can render the new section without an extra runner hook.
        do_dataset = (
            self._config.dataset_enabled
            if build_dataset is None
            else bool(build_dataset)
        )
        do_gate = (
            self._config.dataset_enabled
            if evaluate_quality_gate is None
            else bool(evaluate_quality_gate)
        )
        if emit_events and (do_dataset or do_gate):
            self._build_and_emit_dataset_events(
                report=report,
                ts_ms=ts_value,
                build_dataset=do_dataset,
                evaluate_quality_gate=do_gate,
            )
            # Phase 11C.1C-C-B-B-B-A - Paper Alpha Gate v0. Emit only
            # when the parent dataset / quality-gate run produced a
            # dataset (so the gate has structured input). The
            # verdict is paper / report only; nothing on the path
            # below authorises a real trade.
            if (
                self._config.paper_alpha_gate_enabled
                and self._latest_dataset is not None
            ):
                self._build_and_emit_paper_alpha_gate_events(
                    report=report,
                    ts_ms=ts_value,
                )
            # Phase 11C.1C-C-B-B-B-B - Regime & Cluster Cohort
            # Evidence Pack v0. Emit only when the parent dataset
            # exists (the brief's "if sample_count is insufficient,
            # emit INSUFFICIENT_SAMPLE - do NOT skip" requirement
            # holds so long as the dataset object exists, even when
            # it contains zero records). The pack is paper / report
            # / evidence only; nothing on the path below authorises
            # a real trade or modifies the Risk Engine / Execution
            # FSM.
            if (
                self._config.regime_cluster_evidence_pack_enabled
                and self._latest_dataset is not None
            ):
                self._build_and_emit_regime_cluster_evidence_events(
                    ts_ms=ts_value,
                )
            # Rebuild metrics so the daily-report builder sees the
            # latest dataset / quality-gate fields. Without this
            # refresh, a metrics_payload() call after the flush
            # would return the pre-dataset snapshot.
            self._latest_report_metrics = self._build_metrics_payload(
                report
            )

        return report

    # ------------------------------------------------------------------
    def metrics_payload(self) -> dict[str, Any]:
        """Return a JSON-safe dict of Phase 11C.1C-C-B-A aggregates
        the daily-report builder consumes.

        If no report has been flushed yet, an empty-but-well-formed
        payload is returned so the daily report can render the
        section without ambiguity.
        """
        if self._latest_report_metrics is not None:
            return dict(self._latest_report_metrics)
        # No flush yet - build an empty payload from current samples.
        samples = self.samples
        if not samples:
            return {
                "schema_version": STRATEGY_VALIDATION_SCHEMA_VERSION,
                "strategy_validation_sample_count": 0,
                "strategy_validation_report_generated_count": 0,
                "strategy_validation_sample_created_count": int(
                    self._sample_created_count
                ),
                "strategy_validation_dropped_capacity": int(
                    self._samples_dropped_capacity
                ),
                "strategy_mode_validation": {},
                "candidate_stage_validation": {},
                "opportunity_score_bucket_validation": {},
                "early_tail_score_bucket_validation": {},
                "tail_label_distribution": {
                    "sample_count": 0,
                    "counts": {},
                    "rates": {},
                },
                "top_strategy_validation_symbols": [],
                "cluster_exposure_assessments": [],
                "cluster_leader_validation": {},
                "cluster_leader_outperformance_count": 0,
                "overexposure_warning_count": 0,
                "flagged_findings": [],
                "report_id": "",
                "is_empty_report": True,
                # Phase 11C.1C-C-B-B-A - empty dataset / quality-gate
                # block so the daily-report builder can still render
                # the new section.
                "validation_dataset_schema_version": (
                    STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION
                ),
                "validation_dataset_built_count": int(
                    self._dataset_built_count
                ),
                "validation_dataset_exported_count": int(
                    self._dataset_exported_count
                ),
                "validation_quality_gate_evaluated_count": int(
                    self._quality_gate_evaluated_count
                ),
                "validation_dataset_records": 0,
                "validation_dataset_symbols": [],
                "validation_dataset_tail_label_counts": {},
                "validation_quality_gate_status": "",
                "validation_quality_gate_reasons": [],
                "validation_dataset_export_ready": False,
                "validation_dataset_replay_ready": False,
                "validation_quality_gate_result": {},
                # Phase 11C.1C-C-B-B-B-A - empty Paper Alpha Gate v0
                # block so the daily-report builder can still render
                # the new section. Paper / report only; **MUST
                # NEVER trigger a real trade**.
                "paper_alpha_gate_schema_version": (
                    PAPER_ALPHA_GATE_SCHEMA_VERSION
                ),
                "paper_alpha_gate_evaluated_count": int(
                    self._paper_alpha_gate_evaluated_count
                ),
                "paper_alpha_rule_evaluated_count": int(
                    self._paper_alpha_rule_evaluated_count
                ),
                "paper_alpha_cohort_evaluated_count": int(
                    self._paper_alpha_cohort_evaluated_count
                ),
                "paper_alpha_report_generated_count": int(
                    self._paper_alpha_report_generated_count
                ),
                "paper_alpha_gate_status": "",
                "paper_alpha_gate_reasons": [],
                "paper_alpha_gate_warnings": [],
                "paper_alpha_gate_sample_count": 0,
                "paper_alpha_strategy_mode_results": {},
                "paper_alpha_candidate_stage_results": {},
                "paper_alpha_score_bucket_results": {
                    "opportunity_score_bucket": {},
                    "early_tail_score_bucket": {},
                },
                "paper_alpha_cluster_results": {},
                "paper_alpha_missed_alpha_warnings": 0,
                "paper_alpha_late_chase_warnings": 0,
                "paper_alpha_follow_risk_warnings": 0,
                "paper_alpha_leader_preference_signals": 0,
                "paper_alpha_gate_report": {},
                # Phase 11C.1C-C-B-B-B-B - empty Regime & Cluster
                # Cohort Evidence Pack v0 block so the daily-report
                # builder can still render the new section. Paper /
                # report / evidence only; the per-cohort status is
                # descriptive and **MUST NEVER trigger a real
                # trade**.
                "regime_cluster_evidence_schema_version": (
                    REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
                ),
                "regime_cluster_evidence_pack_generated_count": int(
                    self._regime_cluster_evidence_pack_generated_count
                ),
                "regime_cluster_cohort_summary_generated_count": int(
                    self._regime_cluster_cohort_summary_generated_count
                ),
                "regime_cluster_evidence_status": "",
                "regime_cluster_sample_count": 0,
                "regime_cluster_completed_tail_label_count": 0,
                "regime_cluster_insufficient_sample_reasons": [],
                "regime_cluster_warnings": [],
                "regime_cluster_signals": [],
                "regime_cohort_summary": {
                    "rows": [],
                    "schema_version": (
                        REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
                    ),
                },
                "cluster_cohort_summary": {
                    "rows": [],
                    "leader_vs_follower_rows": [],
                    "schema_version": (
                        REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
                    ),
                },
                "score_bucket_summary": {
                    "opportunity_score_rows": [],
                    "early_tail_score_rows": [],
                    "schema_version": (
                        REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
                    ),
                },
                "stage_outcome_summary": {
                    "rows": [],
                    "schema_version": (
                        REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
                    ),
                },
                "strategy_mode_outcome_summary": {
                    "rows": [],
                    "schema_version": (
                        REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
                    ),
                },
                "regime_cluster_evidence_pack": {},
            }
        report = build_strategy_validation_report(
            samples,
            report_id="strategy-validation-metrics-only",
            generated_at_ms=int(self._clock_ms_fn()),
            primary_window=self._config.primary_window,
            overexposure_warning_threshold=int(
                self._config.overexposure_warning_threshold
            ),
            top_symbol_limit=int(self._config.top_symbol_limit),
        )
        return self._build_metrics_payload(report)

    # ------------------------------------------------------------------
    def _build_metrics_payload(
        self, report: StrategyValidationReport
    ) -> dict[str, Any]:
        leader_outperformance = sum(
            1
            for v in report.cluster_leader_validation.values()
            if v.leader_outperformed_followers
        )
        overexposure = sum(
            1 for a in report.cluster_exposure_assessments if a.overexposure_warning
        )
        return {
            "schema_version": STRATEGY_VALIDATION_SCHEMA_VERSION,
            "strategy_validation_sample_count": int(report.sample_count),
            "strategy_validation_report_generated_count": int(
                self._report_generated_count
            ),
            "strategy_validation_sample_created_count": int(
                self._sample_created_count
            ),
            "strategy_validation_dropped_capacity": int(
                self._samples_dropped_capacity
            ),
            "strategy_mode_validation": {
                k: v.to_payload()
                for k, v in sorted(report.by_strategy_mode.items())
            },
            "candidate_stage_validation": {
                k: v.to_payload()
                for k, v in sorted(report.by_candidate_stage.items())
            },
            "opportunity_score_bucket_validation": {
                k: v.to_payload()
                for k, v in sorted(report.by_opportunity_score_bucket.items())
            },
            "early_tail_score_bucket_validation": {
                k: v.to_payload()
                for k, v in sorted(report.by_early_tail_score_bucket.items())
            },
            "tail_label_distribution": report.tail_label_distribution.to_payload(),
            "top_strategy_validation_symbols": list(
                report.top_strategy_validation_symbols
            ),
            "cluster_exposure_assessments": [
                a.to_payload() for a in report.cluster_exposure_assessments
            ],
            "cluster_leader_validation": {
                k: v.to_payload()
                for k, v in sorted(report.cluster_leader_validation.items())
            },
            "cluster_leader_outperformance_count": int(leader_outperformance),
            "overexposure_warning_count": int(overexposure),
            "flagged_findings": list(report.flagged_findings),
            "report_id": str(report.report_id),
            "is_empty_report": bool(report.sample_count == 0),
            "strategy_mode_validated_count": int(
                self._strategy_mode_validated_count
            ),
            "candidate_stage_validated_count": int(
                self._candidate_stage_validated_count
            ),
            "score_bucket_validated_count": int(
                self._score_bucket_validated_count
            ),
            "cluster_exposure_assessed_count": int(
                self._cluster_exposure_assessed_count
            ),
            "cluster_leader_validated_count": int(
                self._cluster_leader_validated_count
            ),
            # Phase 11C.1C-C-B-B-A - dataset / quality-gate aggregates
            # the daily-report builder consumes. The fields are
            # paper / report only; ``validation_quality_gate_status``
            # is descriptive and MUST NEVER trigger a real trade.
            "validation_dataset_schema_version": (
                STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION
            ),
            "validation_dataset_built_count": int(
                self._dataset_built_count
            ),
            "validation_dataset_exported_count": int(
                self._dataset_exported_count
            ),
            "validation_quality_gate_evaluated_count": int(
                self._quality_gate_evaluated_count
            ),
            "validation_dataset_records": int(
                len(self._latest_dataset.records)
                if self._latest_dataset is not None
                else 0
            ),
            "validation_dataset_symbols": list(
                self._latest_dataset.summary.symbols
                if self._latest_dataset is not None
                else ()
            ),
            "validation_dataset_tail_label_counts": (
                {
                    k: int(v)
                    for k, v in sorted(
                        self._latest_dataset.summary.tail_label_counts.items()
                    )
                }
                if self._latest_dataset is not None
                else {}
            ),
            "validation_quality_gate_status": (
                str(self._latest_quality_gate_result.gate_status)
                if self._latest_quality_gate_result is not None
                else ""
            ),
            "validation_quality_gate_reasons": list(
                self._latest_quality_gate_result.reasons
                if self._latest_quality_gate_result is not None
                else ()
            ),
            "validation_dataset_export_ready": bool(
                self._latest_quality_gate_result.export_roundtrip_ok
                if self._latest_quality_gate_result is not None
                else False
            ),
            "validation_dataset_replay_ready": bool(
                self._latest_quality_gate_result.replay_readable
                if self._latest_quality_gate_result is not None
                else False
            ),
            "validation_quality_gate_result": (
                self._latest_quality_gate_result.to_payload()
                if self._latest_quality_gate_result is not None
                else {}
            ),
            # Phase 11C.1C-C-B-B-B-A - Paper Alpha Gate v0 aggregates
            # the daily-report builder consumes. The fields are
            # paper / report only; the ``paper_alpha_gate_status``
            # is descriptive and **MUST NEVER trigger a real
            # trade**. The Risk Engine remains the single
            # trade-decision gate.
            "paper_alpha_gate_schema_version": (
                PAPER_ALPHA_GATE_SCHEMA_VERSION
            ),
            "paper_alpha_gate_evaluated_count": int(
                self._paper_alpha_gate_evaluated_count
            ),
            "paper_alpha_rule_evaluated_count": int(
                self._paper_alpha_rule_evaluated_count
            ),
            "paper_alpha_cohort_evaluated_count": int(
                self._paper_alpha_cohort_evaluated_count
            ),
            "paper_alpha_report_generated_count": int(
                self._paper_alpha_report_generated_count
            ),
            "paper_alpha_gate_status": (
                str(self._latest_paper_alpha_report.gate_status)
                if self._latest_paper_alpha_report is not None
                else ""
            ),
            "paper_alpha_gate_reasons": list(
                self._latest_paper_alpha_report.reasons
                if self._latest_paper_alpha_report is not None
                else ()
            ),
            "paper_alpha_gate_warnings": list(
                self._latest_paper_alpha_report.warnings
                if self._latest_paper_alpha_report is not None
                else ()
            ),
            "paper_alpha_gate_sample_count": int(
                self._latest_paper_alpha_report.sample_count
                if self._latest_paper_alpha_report is not None
                else 0
            ),
            "paper_alpha_strategy_mode_results": (
                self._cohort_payload_for("strategy_mode")
            ),
            "paper_alpha_candidate_stage_results": (
                self._cohort_payload_for("candidate_stage")
            ),
            "paper_alpha_score_bucket_results": {
                "opportunity_score_bucket": (
                    self._cohort_payload_for("opportunity_score_bucket")
                ),
                "early_tail_score_bucket": (
                    self._cohort_payload_for("early_tail_score_bucket")
                ),
            },
            "paper_alpha_cluster_results": (
                self._cohort_payload_for("cluster_leader_vs_follower")
            ),
            "paper_alpha_missed_alpha_warnings": int(
                self._cohort_warning_count("missed_alpha_warning")
            ),
            "paper_alpha_late_chase_warnings": int(
                self._cohort_warning_count("late_chase_warning")
            ),
            "paper_alpha_follow_risk_warnings": int(
                self._cohort_warning_count("follow_risk_warning")
            ),
            "paper_alpha_leader_preference_signals": int(
                self._cohort_signal_count("leader_preference_signal")
            ),
            "paper_alpha_gate_report": (
                self._latest_paper_alpha_report.to_payload()
                if self._latest_paper_alpha_report is not None
                else {}
            ),
            # Phase 11C.1C-C-B-B-B-B - Regime & Cluster Cohort
            # Evidence Pack v0 aggregates the daily-report builder
            # consumes. Paper / report / evidence only; the per-
            # cohort status is descriptive and **MUST NEVER trigger
            # a real trade** or modify the Risk Engine / Execution
            # FSM. The Risk Engine remains the single trade-decision
            # gate.
            "regime_cluster_evidence_schema_version": (
                REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
            ),
            "regime_cluster_evidence_pack_generated_count": int(
                self._regime_cluster_evidence_pack_generated_count
            ),
            "regime_cluster_cohort_summary_generated_count": int(
                self._regime_cluster_cohort_summary_generated_count
            ),
            "regime_cluster_evidence_status": (
                str(self._latest_regime_cluster_evidence_pack.status)
                if self._latest_regime_cluster_evidence_pack is not None
                else ""
            ),
            "regime_cluster_sample_count": int(
                self._latest_regime_cluster_evidence_pack.sample_count
                if self._latest_regime_cluster_evidence_pack is not None
                else 0
            ),
            "regime_cluster_completed_tail_label_count": int(
                self._latest_regime_cluster_evidence_pack
                .completed_tail_label_count
                if self._latest_regime_cluster_evidence_pack is not None
                else 0
            ),
            "regime_cluster_insufficient_sample_reasons": list(
                self._latest_regime_cluster_evidence_pack
                .insufficient_sample_reasons
                if self._latest_regime_cluster_evidence_pack is not None
                else ()
            ),
            "regime_cluster_warnings": list(
                self._latest_regime_cluster_evidence_pack.warnings
                if self._latest_regime_cluster_evidence_pack is not None
                else ()
            ),
            "regime_cluster_signals": list(
                self._latest_regime_cluster_evidence_pack.signals
                if self._latest_regime_cluster_evidence_pack is not None
                else ()
            ),
            "regime_cohort_summary": (
                self._latest_regime_cluster_evidence_pack
                .regime_cohort_summary.to_payload()
                if self._latest_regime_cluster_evidence_pack is not None
                else {
                    "rows": [],
                    "schema_version": (
                        REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
                    ),
                }
            ),
            "cluster_cohort_summary": (
                self._latest_regime_cluster_evidence_pack
                .cluster_cohort_summary.to_payload()
                if self._latest_regime_cluster_evidence_pack is not None
                else {
                    "rows": [],
                    "leader_vs_follower_rows": [],
                    "schema_version": (
                        REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
                    ),
                }
            ),
            "score_bucket_summary": (
                self._latest_regime_cluster_evidence_pack
                .score_bucket_summary.to_payload()
                if self._latest_regime_cluster_evidence_pack is not None
                else {
                    "opportunity_score_rows": [],
                    "early_tail_score_rows": [],
                    "schema_version": (
                        REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
                    ),
                }
            ),
            "stage_outcome_summary": (
                self._latest_regime_cluster_evidence_pack
                .stage_outcome_summary.to_payload()
                if self._latest_regime_cluster_evidence_pack is not None
                else {
                    "rows": [],
                    "schema_version": (
                        REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
                    ),
                }
            ),
            "strategy_mode_outcome_summary": (
                self._latest_regime_cluster_evidence_pack
                .strategy_mode_outcome_summary.to_payload()
                if self._latest_regime_cluster_evidence_pack is not None
                else {
                    "rows": [],
                    "schema_version": (
                        REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
                    ),
                }
            ),
            "regime_cluster_evidence_pack": (
                self._latest_regime_cluster_evidence_pack.to_payload()
                if self._latest_regime_cluster_evidence_pack is not None
                else {}
            ),
        }

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------
    def _identity_block(
        self,
        *,
        report_id: str = "",
        opportunity_id: str = "",
        scan_batch_id: str = "",
        symbol: str | None = None,
        timestamp: int | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        ts_value = int(timestamp) if timestamp is not None else int(
            self._clock_ms_fn()
        )
        block: dict[str, Any] = {
            "schema_version": STRATEGY_VALIDATION_SCHEMA_VERSION,
            "report_id": str(report_id),
            "opportunity_id": str(opportunity_id),
            "scan_batch_id": str(scan_batch_id),
            "symbol": str(symbol) if symbol is not None else None,
            "timestamp": ts_value,
            "strategy_version": "phase_11c_1c_a.strategy.v1",
            "scoring_version": "phase_11c_1c_a.scoring.v1",
            "risk_config_version": "phase_11c_1c_a.risk_config.v1",
            "state_machine_version": "phase_11c_1c_a.state_machine.v1",
            "validation_version": STRATEGY_VALIDATION_VERSION,
            "source_phase": self.SOURCE_PHASE,
        }
        if extra:
            for k, v in extra.items():
                block[k] = v
        return block

    def _emit_sample_created(
        self,
        *,
        sample: StrategyValidationSample,
        source_event_id: str,
    ) -> None:
        identity = self._identity_block(
            opportunity_id=sample.opportunity_id,
            scan_batch_id=sample.scan_batch_id,
            symbol=sample.symbol,
            timestamp=sample.sample_created_ts,
            extra={"source_event_id": str(source_event_id)},
        )
        # Override version fields from the sample where available so
        # Reflection groups by the *originating* adaptive versions.
        identity["strategy_version"] = str(sample.strategy_version)
        identity["scoring_version"] = str(sample.scoring_version)
        identity["risk_config_version"] = str(sample.risk_config_version)
        identity["state_machine_version"] = str(sample.state_machine_version)
        payload = {
            **identity,
            "sample": sample.to_payload(),
        }
        emitted_event_id = self._emit(
            EventType.STRATEGY_VALIDATION_SAMPLE_CREATED,
            symbol=sample.symbol or None,
            timestamp=sample.sample_created_ts,
            payload=payload,
        )
        self._sample_created_count += 1
        # Phase 11C.1C-C-B-B-A - record the originating event_id so
        # the dataset builder can stamp ``source_event_id`` on every
        # row without re-querying events.db.
        opp_id = str(sample.opportunity_id or "")
        if opp_id and emitted_event_id:
            self._sample_event_ids[opp_id] = str(emitted_event_id)

    def _emit_report_events(
        self,
        *,
        report: StrategyValidationReport,
        ts_ms: int,
    ) -> None:
        # 1. STRATEGY_VALIDATION_REPORT_GENERATED carries the entire
        #    report payload so a single event-log row is sufficient
        #    for a human reviewer to audit the run.
        report_identity = self._identity_block(
            report_id=report.report_id,
            timestamp=ts_ms,
        )
        report_identity["strategy_version"] = str(report.strategy_version)
        report_identity["scoring_version"] = str(report.scoring_version)
        report_identity["risk_config_version"] = str(
            report.risk_config_version
        )
        report_identity["state_machine_version"] = str(
            report.state_machine_version
        )
        self._emit(
            EventType.STRATEGY_VALIDATION_REPORT_GENERATED,
            symbol=None,
            timestamp=ts_ms,
            payload={**report_identity, "report": report.to_payload()},
        )
        self._report_generated_count += 1

        # 2. STRATEGY_MODE_VALIDATED - one event per mode (always
        #    emit follow / pullback / observe / reject so the brief's
        #    "observe / reject 也必须被统计" requirement holds even
        #    when the cohort is empty).
        for mode, stats in report.by_strategy_mode.items():
            self._emit(
                EventType.STRATEGY_MODE_VALIDATED,
                symbol=None,
                timestamp=ts_ms,
                payload={
                    **self._identity_block(
                        report_id=report.report_id,
                        timestamp=ts_ms,
                    ),
                    "strategy_mode": str(mode),
                    "stats": stats.to_payload(),
                },
            )
            self._strategy_mode_validated_count += 1

        # 3. CANDIDATE_STAGE_VALIDATED.
        for stage, stats in report.by_candidate_stage.items():
            self._emit(
                EventType.CANDIDATE_STAGE_VALIDATED,
                symbol=None,
                timestamp=ts_ms,
                payload={
                    **self._identity_block(
                        report_id=report.report_id,
                        timestamp=ts_ms,
                    ),
                    "candidate_stage": str(stage),
                    "stats": stats.to_payload(),
                },
            )
            self._candidate_stage_validated_count += 1

        # 4. SCORE_BUCKET_VALIDATED - emit one event per bucket per
        #    family (opportunity_score / early_tail_score). The
        #    payload's ``family`` field disambiguates.
        for bucket in OPPORTUNITY_SCORE_BUCKET_LABELS:
            stats = report.by_opportunity_score_bucket.get(bucket)
            if stats is None:
                continue
            self._emit(
                EventType.SCORE_BUCKET_VALIDATED,
                symbol=None,
                timestamp=ts_ms,
                payload={
                    **self._identity_block(
                        report_id=report.report_id,
                        timestamp=ts_ms,
                    ),
                    "family": "opportunity_score",
                    "bucket": str(bucket),
                    "stats": stats.to_payload(),
                },
            )
            self._score_bucket_validated_count += 1
        for bucket in EARLY_TAIL_SCORE_BUCKET_LABELS:
            stats = report.by_early_tail_score_bucket.get(bucket)
            if stats is None:
                continue
            self._emit(
                EventType.SCORE_BUCKET_VALIDATED,
                symbol=None,
                timestamp=ts_ms,
                payload={
                    **self._identity_block(
                        report_id=report.report_id,
                        timestamp=ts_ms,
                    ),
                    "family": "early_tail_score",
                    "bucket": str(bucket),
                    "stats": stats.to_payload(),
                },
            )
            self._score_bucket_validated_count += 1

        # 5. CLUSTER_EXPOSURE_ASSESSED.
        for assessment in report.cluster_exposure_assessments:
            self._emit(
                EventType.CLUSTER_EXPOSURE_ASSESSED,
                symbol=assessment.leader_symbol,
                timestamp=ts_ms,
                payload={
                    **self._identity_block(
                        report_id=report.report_id,
                        timestamp=ts_ms,
                        symbol=assessment.leader_symbol,
                    ),
                    "cluster": assessment.to_payload(),
                },
            )
            self._cluster_exposure_assessed_count += 1

        # 6. CLUSTER_LEADER_VALIDATED.
        for cluster_id, stats in report.cluster_leader_validation.items():
            self._emit(
                EventType.CLUSTER_LEADER_VALIDATED,
                symbol=stats.leader_symbol,
                timestamp=ts_ms,
                payload={
                    **self._identity_block(
                        report_id=report.report_id,
                        timestamp=ts_ms,
                        symbol=stats.leader_symbol,
                    ),
                    "cluster_id": str(cluster_id),
                    "stats": stats.to_payload(),
                },
            )
            self._cluster_leader_validated_count += 1

    # ------------------------------------------------------------------
    # Phase 11C.1C-C-B-B-A - dataset / quality-gate emission
    # ------------------------------------------------------------------
    def _build_and_emit_dataset_events(
        self,
        *,
        report: StrategyValidationReport,
        ts_ms: int,
        build_dataset: bool,
        evaluate_quality_gate: bool,
    ) -> None:
        """Build the Phase 11C.1C-C-B-B-A dataset, emit the BUILT /
        EXPORTED / QUALITY_GATE_EVALUATED events, and cache the
        artefacts on the runtime for the daily-report builder.

        Phase 11C.1C-C-B-B-A boundary - this method is paper /
        report only. None of the events it emits authorises a real
        trade; ``gate_status`` is a descriptive label only.
        """
        if not build_dataset and not evaluate_quality_gate:
            return
        try:
            dataset = build_validation_dataset_from_samples(
                self.samples,
                report_id=report.report_id,
                generated_at_ms=int(ts_ms),
                source_event_ids=self._sample_event_ids,
                strategy_version=str(report.strategy_version),
                scoring_version=str(report.scoring_version),
                risk_config_version=str(report.risk_config_version),
                state_machine_version=str(report.state_machine_version),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "[phase11c.1c-c-b-b-a] build_validation_dataset_from_samples"
                " failed: {}",
                exc,
            )
            return
        self._latest_dataset = dataset

        # 1. STRATEGY_VALIDATION_DATASET_BUILT.
        if build_dataset:
            payload = {
                **self._dataset_identity_block(
                    report_id=report.report_id, ts_ms=ts_ms
                ),
                "dataset_summary": dataset.summary.to_payload(),
                "record_count": int(len(dataset.records)),
                "symbols": list(dataset.summary.symbols),
                "tail_label_counts": {
                    k: int(v)
                    for k, v in sorted(
                        dataset.summary.tail_label_counts.items()
                    )
                },
            }
            self._emit(
                EventType.STRATEGY_VALIDATION_DATASET_BUILT,
                symbol=None,
                timestamp=ts_ms,
                payload=payload,
            )
            self._dataset_built_count += 1

        # 2. STRATEGY_VALIDATION_DATASET_EXPORTED. Paper / report
        #    only; the runner / daily-report builder writes the
        #    actual bytes. We emit the event with a hash-free
        #    descriptor so a downstream auditor can cross-reference
        #    the dataset against the bundle on disk.
        export_ok = False
        export_record_count = 0
        try:
            exported_payload = export_validation_dataset_payload(dataset)
            export_record_count = int(
                len(exported_payload.get("records") or [])
            )
            export_ok = True
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "[phase11c.1c-c-b-b-a] export_validation_dataset_payload"
                " failed: {}",
                exc,
            )
        if build_dataset:
            payload = {
                **self._dataset_identity_block(
                    report_id=report.report_id, ts_ms=ts_ms
                ),
                "export_ok": bool(export_ok),
                "record_count": int(export_record_count),
            }
            self._emit(
                EventType.STRATEGY_VALIDATION_DATASET_EXPORTED,
                symbol=None,
                timestamp=ts_ms,
                payload=payload,
            )
            self._dataset_exported_count += 1

        # 3. STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED. The gate
        #    result is descriptive; ``gate_status`` MUST NEVER
        #    trigger a real trade.
        if evaluate_quality_gate:
            try:
                gate_result = evaluate_validation_dataset_quality(
                    dataset, gate=self._config.quality_gate()
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "[phase11c.1c-c-b-b-a] evaluate_validation_dataset_"
                    "quality failed: {}",
                    exc,
                )
                gate_result = None
            if gate_result is not None:
                self._latest_quality_gate_result = gate_result
                payload = {
                    **self._dataset_identity_block(
                        report_id=report.report_id, ts_ms=ts_ms
                    ),
                    "gate_status": str(gate_result.gate_status),
                    "reasons": list(gate_result.reasons),
                    "sample_count": int(gate_result.sample_count),
                    "completed_tail_label_count": int(
                        gate_result.completed_tail_label_count
                    ),
                    "missing_modes": list(gate_result.missing_modes),
                    "missing_stages": list(gate_result.missing_stages),
                    "missing_buckets": list(gate_result.missing_buckets),
                    "missing_required_fields": list(
                        gate_result.missing_required_fields
                    ),
                    "export_roundtrip_ok": bool(
                        gate_result.export_roundtrip_ok
                    ),
                    "replay_readable": bool(gate_result.replay_readable),
                    "gate": gate_result.gate.to_payload(),
                }
                self._emit(
                    EventType.STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED,
                    symbol=None,
                    timestamp=ts_ms,
                    payload=payload,
                )
                self._quality_gate_evaluated_count += 1

    def _dataset_identity_block(
        self,
        *,
        report_id: str,
        ts_ms: int,
    ) -> dict[str, Any]:
        """Build the Phase 11C.1C-C-B-B-A identity block carried by
        every dataset / quality-gate event. Mirrors
        :meth:`_identity_block` but stamps the dataset schema_version
        + dataset version label so a downstream auditor can group
        on them."""
        return {
            "schema_version": STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION,
            "dataset_version": STRATEGY_VALIDATION_DATASET_VERSION,
            "source_phase": STRATEGY_VALIDATION_DATASET_SOURCE_PHASE,
            "report_id": str(report_id),
            "timestamp": int(ts_ms),
            "strategy_version": "phase_11c_1c_a.strategy.v1",
            "scoring_version": "phase_11c_1c_a.scoring.v1",
            "risk_config_version": "phase_11c_1c_a.risk_config.v1",
            "state_machine_version": "phase_11c_1c_a.state_machine.v1",
        }

    # ------------------------------------------------------------------
    # Phase 11C.1C-C-B-B-B-A - Paper Alpha Gate v0 helpers
    # ------------------------------------------------------------------
    def _cohort_payload_for(self, dimension: str) -> dict[str, Any]:
        """Return the to_payload() of the cohort-result for the given
        dimension on the latest Paper Alpha Gate report, or ``{}``
        when no report has been built yet / the dimension is missing.
        """
        report = self._latest_paper_alpha_report
        if report is None:
            return {}
        for c in report.cohort_results:
            if str(c.dimension) == str(dimension):
                return c.to_payload()
        return {}

    def _cohort_warning_count(self, warning: str) -> int:
        """Return the number of cohort-results on the latest Paper
        Alpha Gate report that raised the named warning."""
        report = self._latest_paper_alpha_report
        if report is None:
            return 0
        return sum(
            1 for c in report.cohort_results if str(warning) in c.warnings
        )

    def _cohort_signal_count(self, signal: str) -> int:
        """Return the number of cohort-results on the latest Paper
        Alpha Gate report that raised the named signal."""
        report = self._latest_paper_alpha_report
        if report is None:
            return 0
        return sum(
            1 for c in report.cohort_results if str(signal) in c.signals
        )

    def _paper_alpha_identity_block(
        self,
        *,
        report_id: str,
        dataset_id: str,
        gate_status: str,
        ts_ms: int,
    ) -> dict[str, Any]:
        """Build the Phase 11C.1C-C-B-B-B-A identity block carried by
        every Paper Alpha Gate v0 event. Mirrors
        :meth:`_dataset_identity_block` but stamps the alpha-gate
        schema_version + version label + the descriptive
        ``gate_status``."""
        return {
            "schema_version": PAPER_ALPHA_GATE_SCHEMA_VERSION,
            "paper_alpha_gate_version": PAPER_ALPHA_GATE_VERSION,
            "source_phase": PAPER_ALPHA_GATE_SOURCE_PHASE,
            "report_id": str(report_id),
            "dataset_id": str(dataset_id),
            "timestamp": int(ts_ms),
            "gate_status": str(gate_status),
            "strategy_version": "phase_11c_1c_a.strategy.v1",
            "scoring_version": "phase_11c_1c_a.scoring.v1",
            "risk_config_version": "phase_11c_1c_a.risk_config.v1",
            "state_machine_version": "phase_11c_1c_a.state_machine.v1",
        }

    def _build_and_emit_paper_alpha_gate_events(
        self,
        *,
        report: StrategyValidationReport,
        ts_ms: int,
    ) -> None:
        """Build the Phase 11C.1C-C-B-B-B-A
        :class:`PaperAlphaGateReport` from the cached
        :class:`StrategyValidationDataset` /
        :class:`StrategyValidationQualityGateResult` /
        :class:`StrategyValidationReport` artefacts, emit the four
        new typed events, and cache the result on the runtime for
        the daily-report builder.

        Phase 11C.1C-C-B-B-B-A boundary - this method is paper /
        report only. None of the events it emits authorises a real
        trade; ``gate_status`` is a *descriptive* label (one of
        ``PASS`` / ``WARN`` / ``FAIL`` / ``INCONCLUSIVE``) and
        **MUST NEVER** modify position size, leverage, stop-loss,
        target price, the Risk Engine, or the Execution FSM.
        """
        if self._latest_dataset is None:
            return
        try:
            gate_input = build_paper_alpha_gate_input(
                dataset=self._latest_dataset,
                quality_gate_result=self._latest_quality_gate_result,
                validation_report=report,
                report_id=str(report.report_id),
            )
            paper_report = build_paper_alpha_gate_report(
                gate_input,
                evaluated_at=int(ts_ms),
                min_total_samples=int(
                    self._config.paper_alpha_min_total_samples
                ),
                min_completed_tail_labels=int(
                    self._config.paper_alpha_min_completed_tail_labels
                ),
                min_bucket_samples=int(
                    self._config.paper_alpha_min_bucket_samples
                ),
                follow_fake_breakout_rate=float(
                    self._config.paper_alpha_follow_fake_breakout_rate
                ),
                missed_alpha_strong_tail_rate=float(
                    self._config.paper_alpha_missed_alpha_strong_tail_rate
                ),
                late_chase_fake_breakout_rate=float(
                    self._config.paper_alpha_late_chase_fake_breakout_rate
                ),
                high_bucket_advantage=float(
                    self._config.paper_alpha_high_bucket_advantage
                ),
                leader_preference_advantage=float(
                    self._config.paper_alpha_leader_preference_advantage
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "[phase11c.1c-c-b-b-b-a] build_paper_alpha_gate_report "
                "failed: {}",
                exc,
            )
            return
        self._latest_paper_alpha_report = paper_report

        gate_status = str(paper_report.gate_status)
        dataset_id = str(self._latest_dataset.report_id)

        # 1. PAPER_ALPHA_GATE_EVALUATED - top-level decision.
        gate_payload = {
            **self._paper_alpha_identity_block(
                report_id=paper_report.report_id,
                dataset_id=dataset_id,
                gate_status=gate_status,
                ts_ms=ts_ms,
            ),
            "sample_count": int(paper_report.sample_count),
            "quality_gate_status": str(paper_report.quality_gate_status),
            "reasons": list(paper_report.reasons),
            "warnings": list(paper_report.warnings),
        }
        self._emit(
            EventType.PAPER_ALPHA_GATE_EVALUATED,
            symbol=None,
            timestamp=ts_ms,
            payload=gate_payload,
        )
        self._paper_alpha_gate_evaluated_count += 1

        # 2. PAPER_ALPHA_RULE_EVALUATED - one event per rule.
        for rule_result in paper_report.rule_results:
            rule_payload = {
                **self._paper_alpha_identity_block(
                    report_id=paper_report.report_id,
                    dataset_id=dataset_id,
                    gate_status=gate_status,
                    ts_ms=ts_ms,
                ),
                "rule": rule_result.to_payload(),
            }
            self._emit(
                EventType.PAPER_ALPHA_RULE_EVALUATED,
                symbol=None,
                timestamp=ts_ms,
                payload=rule_payload,
            )
            self._paper_alpha_rule_evaluated_count += 1

        # 3. PAPER_ALPHA_COHORT_EVALUATED - one event per cohort
        #    dimension.
        for cohort_result in paper_report.cohort_results:
            cohort_payload = {
                **self._paper_alpha_identity_block(
                    report_id=paper_report.report_id,
                    dataset_id=dataset_id,
                    gate_status=gate_status,
                    ts_ms=ts_ms,
                ),
                "cohort": cohort_result.to_payload(),
            }
            self._emit(
                EventType.PAPER_ALPHA_COHORT_EVALUATED,
                symbol=None,
                timestamp=ts_ms,
                payload=cohort_payload,
            )
            self._paper_alpha_cohort_evaluated_count += 1

        # 4. PAPER_ALPHA_REPORT_GENERATED - the full report payload
        #    so a downstream auditor can replay the verdict from one
        #    event-log row.
        report_payload = {
            **self._paper_alpha_identity_block(
                report_id=paper_report.report_id,
                dataset_id=dataset_id,
                gate_status=gate_status,
                ts_ms=ts_ms,
            ),
            "report": export_paper_alpha_gate_payload(paper_report),
        }
        self._emit(
            EventType.PAPER_ALPHA_REPORT_GENERATED,
            symbol=None,
            timestamp=ts_ms,
            payload=report_payload,
        )
        self._paper_alpha_report_generated_count += 1

    # ------------------------------------------------------------------
    # Phase 11C.1C-C-B-B-B-B - Regime & Cluster Cohort Evidence Pack
    # v0 helpers
    # ------------------------------------------------------------------
    def _regime_cluster_identity_block(
        self,
        *,
        report_id: str,
        dataset_id: str,
        evidence_pack_status: str,
        ts_ms: int,
    ) -> dict[str, Any]:
        """Build the Phase 11C.1C-C-B-B-B-B identity block carried by
        every Regime & Cluster Evidence Pack v0 event. Mirrors
        :meth:`_paper_alpha_identity_block` but stamps the
        evidence-pack schema_version + version label + the
        descriptive ``evidence_pack_status``."""
        return {
            "schema_version": REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION,
            "regime_cluster_evidence_version": (
                REGIME_CLUSTER_EVIDENCE_VERSION
            ),
            "source_phase": REGIME_CLUSTER_EVIDENCE_SOURCE_PHASE,
            "report_id": str(report_id),
            "dataset_id": str(dataset_id),
            "timestamp": int(ts_ms),
            "evidence_pack_status": str(evidence_pack_status),
            "strategy_version": "phase_11c_1c_a.strategy.v1",
            "scoring_version": "phase_11c_1c_a.scoring.v1",
            "risk_config_version": "phase_11c_1c_a.risk_config.v1",
            "state_machine_version": "phase_11c_1c_a.state_machine.v1",
        }

    def _build_and_emit_regime_cluster_evidence_events(
        self,
        *,
        ts_ms: int,
    ) -> None:
        """Build the Phase 11C.1C-C-B-B-B-B
        :class:`RegimeClusterEvidencePack` from the cached
        :class:`StrategyValidationDataset` /
        :class:`StrategyValidationQualityGateResult` /
        :class:`PaperAlphaGateReport` artefacts, emit the two new
        typed events
        (``REGIME_CLUSTER_EVIDENCE_PACK_GENERATED`` and
        ``REGIME_CLUSTER_COHORT_SUMMARY_GENERATED``), and cache the
        result on the runtime for the daily-report builder.

        Phase 11C.1C-C-B-B-B-B boundary - this method is paper /
        report / evidence only. None of the events it emits
        authorises a real trade; the per-cohort ``status`` is a
        descriptive label and **MUST NEVER** modify position size,
        leverage, stop-loss, target price, the Risk Engine, or the
        Execution FSM.
        """
        if self._latest_dataset is None:
            return
        try:
            paper_alpha_status = ""
            if self._latest_paper_alpha_report is not None:
                paper_alpha_status = str(
                    self._latest_paper_alpha_report.gate_status
                )
            quality_gate_status = ""
            if self._latest_quality_gate_result is not None:
                quality_gate_status = str(
                    self._latest_quality_gate_result.gate_status
                )
            evidence_input = build_regime_cluster_evidence_input(
                dataset=self._latest_dataset,
                regime_by_opportunity=self._regime_by_opportunity,
                paper_alpha_gate_status=paper_alpha_status,
                quality_gate_status=quality_gate_status,
                report_id=str(self._latest_dataset.report_id),
            )
            evidence_pack = build_regime_cluster_evidence_pack(
                evidence_input,
                evaluated_at=int(ts_ms),
                min_total_samples=int(
                    self._config.regime_cluster_min_total_samples
                ),
                min_completed_tail_labels=int(
                    self._config.regime_cluster_min_completed_tail_labels
                ),
                min_cohort_samples=int(
                    self._config.regime_cluster_min_cohort_samples
                ),
                strong_tail_signal_rate=float(
                    self._config.regime_cluster_strong_tail_signal_rate
                ),
                reached_3r_signal_rate=float(
                    self._config.regime_cluster_reached_3r_signal_rate
                ),
                reached_5r_signal_rate=float(
                    self._config.regime_cluster_reached_5r_signal_rate
                ),
                fake_breakout_warning_rate=float(
                    self._config.regime_cluster_fake_breakout_warning_rate
                ),
                missed_tail_warning_rate=float(
                    self._config.regime_cluster_missed_tail_warning_rate
                ),
                late_chase_failure_warning_rate=float(
                    self._config
                    .regime_cluster_late_chase_failure_warning_rate
                ),
                leader_preference_advantage=float(
                    self._config.regime_cluster_leader_preference_advantage
                ),
                high_bucket_advantage=float(
                    self._config.regime_cluster_high_bucket_advantage
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "[phase11c.1c-c-b-b-b-b] build_regime_cluster_evidence_pack"
                " failed: {}",
                exc,
            )
            return
        self._latest_regime_cluster_evidence_pack = evidence_pack

        evidence_pack_status = str(evidence_pack.status)
        dataset_id = str(self._latest_dataset.report_id)
        report_id = str(evidence_pack.report_id)

        # 1. REGIME_CLUSTER_COHORT_SUMMARY_GENERATED - one event per
        #    named cohort summary so a downstream auditor can flatly
        #    iterate the per-cohort summaries without parsing the
        #    nested top-level pack.
        cohort_summaries: tuple[tuple[str, dict[str, Any]], ...] = (
            (
                "regime_cohort_summary",
                evidence_pack.regime_cohort_summary.to_payload(),
            ),
            (
                "cluster_cohort_summary",
                evidence_pack.cluster_cohort_summary.to_payload(),
            ),
            (
                "score_bucket_summary",
                evidence_pack.score_bucket_summary.to_payload(),
            ),
            (
                "stage_outcome_summary",
                evidence_pack.stage_outcome_summary.to_payload(),
            ),
            (
                "strategy_mode_outcome_summary",
                evidence_pack.strategy_mode_outcome_summary.to_payload(),
            ),
        )
        for summary_name, summary_payload in cohort_summaries:
            payload = {
                **self._regime_cluster_identity_block(
                    report_id=report_id,
                    dataset_id=dataset_id,
                    evidence_pack_status=evidence_pack_status,
                    ts_ms=ts_ms,
                ),
                "summary_name": str(summary_name),
                "summary": summary_payload,
            }
            self._emit(
                EventType.REGIME_CLUSTER_COHORT_SUMMARY_GENERATED,
                symbol=None,
                timestamp=ts_ms,
                payload=payload,
            )
            self._regime_cluster_cohort_summary_generated_count += 1

        # 2. REGIME_CLUSTER_EVIDENCE_PACK_GENERATED - the full pack
        #    payload so a downstream auditor can replay the report
        #    from one event-log row.
        pack_payload = {
            **self._regime_cluster_identity_block(
                report_id=report_id,
                dataset_id=dataset_id,
                evidence_pack_status=evidence_pack_status,
                ts_ms=ts_ms,
            ),
            "sample_count": int(evidence_pack.sample_count),
            "completed_tail_label_count": int(
                evidence_pack.completed_tail_label_count
            ),
            "insufficient_sample_reasons": list(
                evidence_pack.insufficient_sample_reasons
            ),
            "warnings": list(evidence_pack.warnings),
            "signals": list(evidence_pack.signals),
            "paper_alpha_gate_status": str(
                evidence_pack.paper_alpha_gate_status
            ),
            "quality_gate_status": str(evidence_pack.quality_gate_status),
            "pack": export_regime_cluster_evidence_payload(evidence_pack),
        }
        self._emit(
            EventType.REGIME_CLUSTER_EVIDENCE_PACK_GENERATED,
            symbol=None,
            timestamp=ts_ms,
            payload=pack_payload,
        )
        self._regime_cluster_evidence_pack_generated_count += 1

    def _emit(
        self,
        event_type: EventType,
        *,
        symbol: str | None,
        timestamp: int,
        payload: dict[str, Any],
    ) -> str:
        """Emit one event through the EventRepository. Returns the
        ``event_id`` of the appended event so callers can cross-
        reference it later (used by Phase 11C.1C-C-B-B-A dataset
        records). Returns the empty string on failure."""
        try:
            event = Event(
                event_type=event_type,
                source_module=self.SOURCE_MODULE,
                symbol=str(symbol) if symbol else None,
                timestamp=int(timestamp),
                payload=payload,
            )
            self._event_repo.append(event)
            return str(event.event_id)
        except Exception as exc:  # pragma: no cover - protective
            logger.error(
                "[phase11c.1c-c-b-a] failed to emit {} symbol={}: {}",
                event_type.value,
                symbol,
                exc,
            )
            return ""


__all__ = [
    "StrategyValidationRuntime",
    "StrategyValidationRuntimeConfig",
]
