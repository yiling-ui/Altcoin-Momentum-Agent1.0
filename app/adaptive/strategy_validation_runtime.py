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
from app.core.clock import now_ms
from app.core.events import Event, EventType
from app.database.repositories import EventRepository


@dataclass(frozen=True)
class StrategyValidationRuntimeConfig:
    """Tunable knobs for the Phase 11C.1C-C-B-A Lab v0 runtime.

    Every threshold the runtime consumes lives here so the brief's
    "thresholds must be configurable, not hard-coded" rule holds at
    the YAML / boot layer too.
    """

    enabled: bool = True
    max_samples: int = 2_000
    primary_window: str = STRATEGY_VALIDATION_PRIMARY_WINDOW
    overexposure_warning_threshold: int = (
        DEFAULT_OVEREXPOSURE_WARNING_THRESHOLD
    )
    top_symbol_limit: int = 10

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
        ):
            if hasattr(section, f):
                attrs[f] = getattr(section, f)
        return StrategyValidationRuntimeConfig.from_mapping(attrs)


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
    ) -> StrategyValidationReport:
        """Build the latest :class:`StrategyValidationReport` and emit
        the per-cohort + per-cluster events.

        Phase 11C.1C-C-B-A boundary - the report is paper / report
        only. ``emit_events=True`` does NOT authorise any real trade;
        the seven new event types are descriptive.
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
        self._emit(
            EventType.STRATEGY_VALIDATION_SAMPLE_CREATED,
            symbol=sample.symbol or None,
            timestamp=sample.sample_created_ts,
            payload=payload,
        )
        self._sample_created_count += 1

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

    def _emit(
        self,
        event_type: EventType,
        *,
        symbol: str | None,
        timestamp: int,
        payload: dict[str, Any],
    ) -> None:
        try:
            event = Event(
                event_type=event_type,
                source_module=self.SOURCE_MODULE,
                symbol=str(symbol) if symbol else None,
                timestamp=int(timestamp),
                payload=payload,
            )
            self._event_repo.append(event)
        except Exception as exc:  # pragma: no cover - protective
            logger.error(
                "[phase11c.1c-c-b-a] failed to emit {} symbol={}: {}",
                event_type.value,
                symbol,
                exc,
            )


__all__ = [
    "StrategyValidationRuntime",
    "StrategyValidationRuntimeConfig",
]
