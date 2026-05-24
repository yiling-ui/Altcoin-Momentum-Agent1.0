"""Phase 11B - Daily Paper Report builder.

Reads the same :class:`EventRepository` the rest of the system writes
to and emits a Markdown report under
``data/reports/daily/{date}-paper-report.md``. The report is **read-only**
in the sense that the builder NEVER calls ``EventRepository.append_event``
and NEVER mutates any other database.

Phase 11B brief - the report MUST contain:

  - System uptime
  - Event count
  - Candidate-opportunity count
  - Risk-rejection count
  - State-transition count
  - Paper-trade count
  - Paper PnL
  - Capital-rebase count
  - P0 / P1 incident counts
  - Protection-mode entry count
  - Telegram message-sent count
  - Export count
  - Top reject reasons
  - Top symbols
  - Errors / degraded-status notes

Defence in depth: the rendered Markdown body is run through
:func:`app.exports.redaction.assert_no_forbidden_substrings` so a
malformed payload cannot leak a credential literal.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from app.core.clock import now_ms
from app.core.events import CAPITAL_EVENT_TYPES, Event, EventType
from app.database.repositories import EventRepository
from app.exports.redaction import assert_no_forbidden_substrings


# Top-N caps for "top symbols" / "top reject reasons" sections.
_TOP_REJECT_REASONS_LIMIT = 5
_TOP_SYMBOLS_LIMIT = 5


@dataclass(frozen=True)
class DailyReportSnapshot:
    """JSON-safe view of one daily report. The supervisor + acceptance
    report consume this dataclass directly; the Markdown body is
    available as :attr:`markdown`."""

    date: str
    started_at_ms: int
    finished_at_ms: int
    uptime_seconds: int
    event_count: int
    candidate_opportunity_count: int
    risk_approved_count: int
    risk_rejected_count: int
    state_transition_count: int
    paper_trade_count: int
    paper_realized_pnl: float
    paper_unrealized_pnl: float
    capital_rebase_count: int
    capital_deposit_count: int
    capital_withdrawal_count: int
    incidents_p0_count: int
    incidents_p1_count: int
    incidents_p2_count: int
    incidents_p3_count: int
    protection_mode_entered_count: int
    protection_mode_exited_count: int
    telegram_messages_sent_count: int
    telegram_send_failed_count: int
    telegram_command_rejected_count: int
    data_export_generated_count: int
    data_export_failed_count: int
    llm_interpreted_count: int
    llm_degraded_count: int
    llm_schema_rejected_count: int
    reconciliation_started_count: int
    reconciliation_resolved_count: int
    reconciliation_mismatch_count: int
    new_opens_paused: bool
    top_reject_reasons: tuple[tuple[str, int], ...]
    top_symbols: tuple[tuple[str, int], ...]
    error_notes: tuple[str, ...] = field(default_factory=tuple)
    degraded_notes: tuple[str, ...] = field(default_factory=tuple)
    safety_summary: dict[str, bool] = field(default_factory=dict)
    paper_cloud_summary: dict[str, Any] = field(default_factory=dict)
    # Phase 11C.1A - Binance public REST rate-limit governor metrics.
    rate_limit_429_count: int = 0
    rate_limit_418_count: int = 0
    retry_after_seconds_last: int = 0
    retry_after_seconds_total: int = 0
    used_weight_1m_last: int = 0
    used_weight_1m_max: int = 0
    rest_requests_total: int = 0
    rest_requests_skipped_by_budget: int = 0
    rate_limit_protection_triggered: bool = False
    rate_limit_ban: bool = False
    rate_limit_backoff_started_count: int = 0
    rate_limit_backoff_ended_count: int = 0
    ingestion_errors: int = 0
    rate_limit_metrics: dict[str, Any] = field(default_factory=dict)
    # Phase 11C.1B - WebSocket-first all-market radar metrics.
    ws_messages_received: int = 0
    ws_messages_received_by_stream: dict[str, int] = field(default_factory=dict)
    ws_reconnect_count: int = 0
    ws_staleness_ms_max: int = 0
    ws_stale_count: int = 0
    ws_connect_count: int = 0
    ws_disconnect_count: int = 0
    ws_is_stale: bool = False
    radar_candidates_seen: int = 0
    candidate_pool_size_max: int = 0
    pre_anomaly_candidates: int = 0
    liquidation_events_seen: int = 0
    radar_score_top_symbols: list[dict[str, Any]] = field(default_factory=list)
    ws_metrics: dict[str, Any] = field(default_factory=dict)
    candidate_pool_metrics: dict[str, Any] = field(default_factory=dict)
    # Phase 11C.1C-A - Adaptive Candidate Regime & Strategy Selector
    # metrics. The runner passes the WSRadarChainDriver's
    # ``adaptive_metrics_payload()`` through ``adaptive_metrics``;
    # the builder cross-checks the event-log counts of the six new
    # event types against those counters before rendering.
    market_regime_counts: dict[str, int] = field(default_factory=dict)
    candidate_stage_counts: dict[str, int] = field(default_factory=dict)
    strategy_mode_counts: dict[str, int] = field(default_factory=dict)
    opportunity_grade_counts: dict[str, int] = field(default_factory=dict)
    top_opportunity_scores: list[dict[str, Any]] = field(default_factory=list)
    label_queue_enqueued: int = 0
    observe_count: int = 0
    reject_count: int = 0
    follow_count: int = 0
    pullback_count: int = 0
    late_chase_rejected_count: int = 0
    blowoff_observed_count: int = 0
    market_regime_assessed_count: int = 0
    candidate_stage_classified_count: int = 0
    opportunity_scored_count: int = 0
    strategy_mode_selected_count: int = 0
    cluster_context_attached_count: int = 0
    adaptive_metrics: dict[str, Any] = field(default_factory=dict)
    # Phase 11C.1C-B - Adaptive Candidate Runtime Calibration & Early
    # Tail Discovery v0 metrics. The runner passes the
    # ``adaptive_metrics`` (chain) + ``candidate_pool_metrics``
    # (pool) blocks; the builder unifies the two so the daily
    # report surfaces both the chain-side aggregates (top early
    # tail scored on driven candidates) and the pool-side
    # protection state (early-tail-protect threshold, count of
    # candidates promoted before the 24h top print).
    top_early_tail_candidates: list[dict[str, Any]] = field(
        default_factory=list
    )
    top_late_chase_risk_candidates: list[dict[str, Any]] = field(
        default_factory=list
    )
    early_tail_score_top_symbols: list[dict[str, Any]] = field(
        default_factory=list
    )
    opportunity_score_distribution: dict[str, int] = field(
        default_factory=dict
    )
    symbols_promoted_before_24h_top_move: list[dict[str, Any]] = field(
        default_factory=list
    )
    eden_alt_near_examples: list[dict[str, Any]] = field(default_factory=list)
    early_tail_protect_threshold: float = 0.0
    candidate_pool_promoted_before_24h_top_move: int = 0
    # Phase 11C.1C-C-A - MFE / MAE Label Queue Runtime metrics. The
    # runner passes the :meth:`LabelQueueRuntime.metrics_payload`
    # dict through ``label_runtime_metrics``; the builder cross-checks
    # the event-log counts of the six new event types against those
    # counters before rendering.
    label_tracking_started_count: int = 0
    label_window_updated_count: int = 0
    label_window_completed_count: int = 0
    tail_label_assigned_count: int = 0
    missed_tail_detected_count: int = 0
    fake_breakout_detected_count: int = 0
    pending_label_records: int = 0
    completed_label_records: int = 0
    expired_label_records: int = 0
    unresolved_label_records: int = 0
    tail_label_distribution: dict[str, int] = field(default_factory=dict)
    reached_2r_count: int = 0
    reached_3r_count: int = 0
    reached_5r_count: int = 0
    reached_10r_count: int = 0
    early_tail_score_bucket_outcomes: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
    opportunity_score_bucket_outcomes: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
    strategy_mode_outcomes: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
    late_chase_risk_bucket_outcomes: dict[str, dict[str, int]] = field(
        default_factory=dict
    )
    top_mfe_symbols: list[dict[str, Any]] = field(default_factory=list)
    worst_mae_symbols: list[dict[str, Any]] = field(default_factory=list)
    missed_tail_symbols: list[dict[str, Any]] = field(default_factory=list)
    fake_breakout_symbols: list[dict[str, Any]] = field(default_factory=list)
    label_runtime_metrics: dict[str, Any] = field(default_factory=dict)
    # Phase 11C.1C-C-B-A - Strategy Validation Lab v0 & Cluster
    # Exposure Control Contracts metrics. The runner passes the
    # :meth:`StrategyValidationRuntime.metrics_payload` dict
    # through ``strategy_validation_metrics``; the builder
    # cross-checks the event-log counts of the seven new event
    # types against those counters before rendering. Every value is
    # paper / report only - the ``suggested_cluster_action`` on
    # each cluster assessment is descriptive; the Risk Engine
    # remains the single trade-decision gate.
    strategy_validation_sample_count: int = 0
    strategy_validation_sample_created_count: int = 0
    strategy_validation_report_generated_count: int = 0
    strategy_mode_validated_count: int = 0
    candidate_stage_validated_count: int = 0
    score_bucket_validated_count: int = 0
    cluster_exposure_assessed_count: int = 0
    cluster_leader_validated_count: int = 0
    strategy_mode_validation: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    candidate_stage_validation: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    opportunity_score_bucket_validation: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    early_tail_score_bucket_validation: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    strategy_validation_tail_label_distribution: dict[str, Any] = field(
        default_factory=dict
    )
    top_strategy_validation_symbols: list[dict[str, Any]] = field(
        default_factory=list
    )
    cluster_exposure_assessments: list[dict[str, Any]] = field(
        default_factory=list
    )
    cluster_leader_validation: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    cluster_leader_outperformance_count: int = 0
    overexposure_warning_count: int = 0
    strategy_validation_flagged_findings: list[str] = field(
        default_factory=list
    )
    strategy_validation_metrics: dict[str, Any] = field(default_factory=dict)
    # Phase 11C.1C-C-B-B-A - Strategy Validation Dataset Builder &
    # Quality Gate v0. The runner passes the
    # :meth:`StrategyValidationRuntime.metrics_payload` dict through
    # ``strategy_validation_metrics``; the dataset / gate sub-block
    # below is read from that dict. Every value is paper / report
    # only - the ``validation_quality_gate_status`` is a descriptive
    # label and **MUST NEVER trigger a real trade**; the Risk Engine
    # remains the single trade-decision gate.
    validation_dataset_built_count: int = 0
    validation_dataset_exported_count: int = 0
    validation_quality_gate_evaluated_count: int = 0
    validation_dataset_records: int = 0
    validation_dataset_symbols: list[str] = field(default_factory=list)
    validation_dataset_tail_label_counts: dict[str, int] = field(
        default_factory=dict
    )
    validation_quality_gate_status: str = ""
    validation_quality_gate_reasons: list[str] = field(default_factory=list)
    validation_dataset_export_ready: bool = False
    validation_dataset_replay_ready: bool = False
    validation_quality_gate_result: dict[str, Any] = field(
        default_factory=dict
    )
    # Phase 11C.1C-C-B-B-B-A - Paper Alpha Gate v0. The runner
    # passes the :meth:`StrategyValidationRuntime.metrics_payload`
    # dict through ``strategy_validation_metrics``; the paper alpha
    # gate sub-block below is read from that dict. Every value is
    # paper / report only - the ``paper_alpha_gate_status`` is a
    # *descriptive* label (``PASS`` / ``WARN`` / ``FAIL`` /
    # ``INCONCLUSIVE``) and **MUST NEVER trigger a real trade**, and
    # **MUST NEVER** modify position size, leverage, stop-loss,
    # target price, the Risk Engine, or the Execution FSM. The Risk
    # Engine remains the single trade-decision gate.
    paper_alpha_gate_evaluated_count: int = 0
    paper_alpha_rule_evaluated_count: int = 0
    paper_alpha_cohort_evaluated_count: int = 0
    paper_alpha_report_generated_count: int = 0
    paper_alpha_gate_status: str = ""
    paper_alpha_gate_reasons: list[str] = field(default_factory=list)
    paper_alpha_gate_warnings: list[str] = field(default_factory=list)
    paper_alpha_gate_sample_count: int = 0
    paper_alpha_strategy_mode_results: dict[str, Any] = field(
        default_factory=dict
    )
    paper_alpha_candidate_stage_results: dict[str, Any] = field(
        default_factory=dict
    )
    paper_alpha_score_bucket_results: dict[str, Any] = field(
        default_factory=dict
    )
    paper_alpha_cluster_results: dict[str, Any] = field(
        default_factory=dict
    )
    paper_alpha_missed_alpha_warnings: int = 0
    paper_alpha_late_chase_warnings: int = 0
    paper_alpha_follow_risk_warnings: int = 0
    paper_alpha_leader_preference_signals: int = 0
    paper_alpha_gate_report: dict[str, Any] = field(default_factory=dict)
    # Phase 11C.1C-C-B-B-B-B - Regime & Cluster Cohort Evidence Pack
    # v0. The runner passes the
    # :meth:`StrategyValidationRuntime.metrics_payload` dict through
    # ``strategy_validation_metrics``; the regime / cluster
    # evidence-pack sub-block below is read from that dict. Every
    # value is paper / report / evidence only - the per-cohort
    # status and the ``regime_cluster_evidence_status`` are
    # *descriptive* labels (``INSUFFICIENT_SAMPLE`` /
    # ``OBSERVE_ONLY`` / ``WARNING`` / ``EVIDENCE_SIGNAL``) and
    # **MUST NEVER trigger a real trade**, and **MUST NEVER**
    # modify position size, leverage, stop-loss, target price, the
    # Risk Engine, or the Execution FSM. The Risk Engine remains
    # the single trade-decision gate.
    regime_cluster_evidence_pack_generated_count: int = 0
    regime_cluster_cohort_summary_generated_count: int = 0
    regime_cluster_evidence_status: str = ""
    regime_cluster_sample_count: int = 0
    regime_cluster_completed_tail_label_count: int = 0
    regime_cluster_insufficient_sample_reasons: list[str] = field(
        default_factory=list
    )
    regime_cluster_warnings: list[str] = field(default_factory=list)
    regime_cluster_signals: list[str] = field(default_factory=list)
    regime_cohort_summary: dict[str, Any] = field(default_factory=dict)
    cluster_cohort_summary: dict[str, Any] = field(default_factory=dict)
    score_bucket_summary: dict[str, Any] = field(default_factory=dict)
    stage_outcome_summary: dict[str, Any] = field(default_factory=dict)
    strategy_mode_outcome_summary: dict[str, Any] = field(
        default_factory=dict
    )
    regime_cluster_evidence_pack: dict[str, Any] = field(default_factory=dict)
    markdown: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "started_at_ms": int(self.started_at_ms),
            "finished_at_ms": int(self.finished_at_ms),
            "uptime_seconds": int(self.uptime_seconds),
            "event_count": int(self.event_count),
            "candidate_opportunity_count": int(self.candidate_opportunity_count),
            "risk_approved_count": int(self.risk_approved_count),
            "risk_rejected_count": int(self.risk_rejected_count),
            "state_transition_count": int(self.state_transition_count),
            "paper_trade_count": int(self.paper_trade_count),
            "paper_realized_pnl": float(self.paper_realized_pnl),
            "paper_unrealized_pnl": float(self.paper_unrealized_pnl),
            "capital_rebase_count": int(self.capital_rebase_count),
            "capital_deposit_count": int(self.capital_deposit_count),
            "capital_withdrawal_count": int(self.capital_withdrawal_count),
            "incidents_p0_count": int(self.incidents_p0_count),
            "incidents_p1_count": int(self.incidents_p1_count),
            "incidents_p2_count": int(self.incidents_p2_count),
            "incidents_p3_count": int(self.incidents_p3_count),
            "protection_mode_entered_count": int(
                self.protection_mode_entered_count
            ),
            "protection_mode_exited_count": int(
                self.protection_mode_exited_count
            ),
            "telegram_messages_sent_count": int(
                self.telegram_messages_sent_count
            ),
            "telegram_send_failed_count": int(self.telegram_send_failed_count),
            "telegram_command_rejected_count": int(
                self.telegram_command_rejected_count
            ),
            "data_export_generated_count": int(
                self.data_export_generated_count
            ),
            "data_export_failed_count": int(self.data_export_failed_count),
            "llm_interpreted_count": int(self.llm_interpreted_count),
            "llm_degraded_count": int(self.llm_degraded_count),
            "llm_schema_rejected_count": int(self.llm_schema_rejected_count),
            "reconciliation_started_count": int(
                self.reconciliation_started_count
            ),
            "reconciliation_resolved_count": int(
                self.reconciliation_resolved_count
            ),
            "reconciliation_mismatch_count": int(
                self.reconciliation_mismatch_count
            ),
            "new_opens_paused": bool(self.new_opens_paused),
            "top_reject_reasons": [
                {"reason": r, "count": int(c)}
                for r, c in self.top_reject_reasons
            ],
            "top_symbols": [
                {"symbol": s, "count": int(c)} for s, c in self.top_symbols
            ],
            "error_notes": list(self.error_notes),
            "degraded_notes": list(self.degraded_notes),
            "safety_summary": dict(self.safety_summary),
            "paper_cloud_summary": dict(self.paper_cloud_summary),
            # Phase 11C.1A rate-limit metrics.
            "rate_limit_429_count": int(self.rate_limit_429_count),
            "rate_limit_418_count": int(self.rate_limit_418_count),
            "retry_after_seconds_last": int(self.retry_after_seconds_last),
            "retry_after_seconds_total": int(self.retry_after_seconds_total),
            "used_weight_1m_last": int(self.used_weight_1m_last),
            "used_weight_1m_max": int(self.used_weight_1m_max),
            "rest_requests_total": int(self.rest_requests_total),
            "rest_requests_skipped_by_budget": int(
                self.rest_requests_skipped_by_budget
            ),
            "rate_limit_protection_triggered": bool(
                self.rate_limit_protection_triggered
            ),
            "rate_limit_ban": bool(self.rate_limit_ban),
            "rate_limit_backoff_started_count": int(
                self.rate_limit_backoff_started_count
            ),
            "rate_limit_backoff_ended_count": int(
                self.rate_limit_backoff_ended_count
            ),
            "ingestion_errors": int(self.ingestion_errors),
            "rate_limit_metrics": dict(self.rate_limit_metrics),
            # Phase 11C.1B WS-first radar.
            "ws_messages_received": int(self.ws_messages_received),
            "ws_messages_received_by_stream": dict(
                self.ws_messages_received_by_stream
            ),
            "ws_reconnect_count": int(self.ws_reconnect_count),
            "ws_staleness_ms_max": int(self.ws_staleness_ms_max),
            "ws_stale_count": int(self.ws_stale_count),
            "ws_connect_count": int(self.ws_connect_count),
            "ws_disconnect_count": int(self.ws_disconnect_count),
            "ws_is_stale": bool(self.ws_is_stale),
            "radar_candidates_seen": int(self.radar_candidates_seen),
            "candidate_pool_size_max": int(self.candidate_pool_size_max),
            "pre_anomaly_candidates": int(self.pre_anomaly_candidates),
            "liquidation_events_seen": int(self.liquidation_events_seen),
            "radar_score_top_symbols": list(self.radar_score_top_symbols),
            "ws_metrics": dict(self.ws_metrics),
            "candidate_pool_metrics": dict(self.candidate_pool_metrics),
            # Phase 11C.1C-A adaptive metrics.
            "market_regime_counts": dict(self.market_regime_counts),
            "candidate_stage_counts": dict(self.candidate_stage_counts),
            "strategy_mode_counts": dict(self.strategy_mode_counts),
            "opportunity_grade_counts": dict(self.opportunity_grade_counts),
            "top_opportunity_scores": list(self.top_opportunity_scores),
            "label_queue_enqueued": int(self.label_queue_enqueued),
            "observe_count": int(self.observe_count),
            "reject_count": int(self.reject_count),
            "follow_count": int(self.follow_count),
            "pullback_count": int(self.pullback_count),
            "late_chase_rejected_count": int(self.late_chase_rejected_count),
            "blowoff_observed_count": int(self.blowoff_observed_count),
            "market_regime_assessed_count": int(
                self.market_regime_assessed_count
            ),
            "candidate_stage_classified_count": int(
                self.candidate_stage_classified_count
            ),
            "opportunity_scored_count": int(self.opportunity_scored_count),
            "strategy_mode_selected_count": int(
                self.strategy_mode_selected_count
            ),
            "cluster_context_attached_count": int(
                self.cluster_context_attached_count
            ),
            "adaptive_metrics": dict(self.adaptive_metrics),
            # Phase 11C.1C-B runtime calibration aggregates.
            "top_early_tail_candidates": list(
                self.top_early_tail_candidates
            ),
            "top_late_chase_risk_candidates": list(
                self.top_late_chase_risk_candidates
            ),
            "early_tail_score_top_symbols": list(
                self.early_tail_score_top_symbols
            ),
            "opportunity_score_distribution": dict(
                self.opportunity_score_distribution
            ),
            "symbols_promoted_before_24h_top_move": list(
                self.symbols_promoted_before_24h_top_move
            ),
            "eden_alt_near_examples": list(self.eden_alt_near_examples),
            "early_tail_protect_threshold": float(
                self.early_tail_protect_threshold
            ),
            "candidate_pool_promoted_before_24h_top_move": int(
                self.candidate_pool_promoted_before_24h_top_move
            ),
            # Phase 11C.1C-C-A label-tracking runtime aggregates.
            "label_tracking_started_count": int(
                self.label_tracking_started_count
            ),
            "label_window_updated_count": int(
                self.label_window_updated_count
            ),
            "label_window_completed_count": int(
                self.label_window_completed_count
            ),
            "tail_label_assigned_count": int(
                self.tail_label_assigned_count
            ),
            "missed_tail_detected_count": int(
                self.missed_tail_detected_count
            ),
            "fake_breakout_detected_count": int(
                self.fake_breakout_detected_count
            ),
            "pending_label_records": int(self.pending_label_records),
            "completed_label_records": int(self.completed_label_records),
            "expired_label_records": int(self.expired_label_records),
            "unresolved_label_records": int(self.unresolved_label_records),
            "tail_label_distribution": dict(self.tail_label_distribution),
            "reached_2r_count": int(self.reached_2r_count),
            "reached_3r_count": int(self.reached_3r_count),
            "reached_5r_count": int(self.reached_5r_count),
            "reached_10r_count": int(self.reached_10r_count),
            "early_tail_score_bucket_outcomes": dict(
                self.early_tail_score_bucket_outcomes
            ),
            "opportunity_score_bucket_outcomes": dict(
                self.opportunity_score_bucket_outcomes
            ),
            "strategy_mode_outcomes": dict(self.strategy_mode_outcomes),
            "late_chase_risk_bucket_outcomes": dict(
                self.late_chase_risk_bucket_outcomes
            ),
            "top_mfe_symbols": list(self.top_mfe_symbols),
            "worst_mae_symbols": list(self.worst_mae_symbols),
            "missed_tail_symbols": list(self.missed_tail_symbols),
            "fake_breakout_symbols": list(self.fake_breakout_symbols),
            "label_runtime_metrics": dict(self.label_runtime_metrics),
            # Phase 11C.1C-C-B-A Strategy Validation Lab v0 + Cluster
            # Exposure Control Contracts.
            "strategy_validation_sample_count": int(
                self.strategy_validation_sample_count
            ),
            "strategy_validation_sample_created_count": int(
                self.strategy_validation_sample_created_count
            ),
            "strategy_validation_report_generated_count": int(
                self.strategy_validation_report_generated_count
            ),
            "strategy_mode_validated_count": int(
                self.strategy_mode_validated_count
            ),
            "candidate_stage_validated_count": int(
                self.candidate_stage_validated_count
            ),
            "score_bucket_validated_count": int(
                self.score_bucket_validated_count
            ),
            "cluster_exposure_assessed_count": int(
                self.cluster_exposure_assessed_count
            ),
            "cluster_leader_validated_count": int(
                self.cluster_leader_validated_count
            ),
            "strategy_mode_validation": dict(self.strategy_mode_validation),
            "candidate_stage_validation": dict(
                self.candidate_stage_validation
            ),
            "opportunity_score_bucket_validation": dict(
                self.opportunity_score_bucket_validation
            ),
            "early_tail_score_bucket_validation": dict(
                self.early_tail_score_bucket_validation
            ),
            "strategy_validation_tail_label_distribution": dict(
                self.strategy_validation_tail_label_distribution
            ),
            "top_strategy_validation_symbols": list(
                self.top_strategy_validation_symbols
            ),
            "cluster_exposure_assessments": list(
                self.cluster_exposure_assessments
            ),
            "cluster_leader_validation": dict(self.cluster_leader_validation),
            "cluster_leader_outperformance_count": int(
                self.cluster_leader_outperformance_count
            ),
            "overexposure_warning_count": int(self.overexposure_warning_count),
            "strategy_validation_flagged_findings": list(
                self.strategy_validation_flagged_findings
            ),
            "strategy_validation_metrics": dict(
                self.strategy_validation_metrics
            ),
            # Phase 11C.1C-C-B-B-A dataset / quality-gate fields.
            "validation_dataset_built_count": int(
                self.validation_dataset_built_count
            ),
            "validation_dataset_exported_count": int(
                self.validation_dataset_exported_count
            ),
            "validation_quality_gate_evaluated_count": int(
                self.validation_quality_gate_evaluated_count
            ),
            "validation_dataset_records": int(
                self.validation_dataset_records
            ),
            "validation_dataset_symbols": list(
                self.validation_dataset_symbols
            ),
            "validation_dataset_tail_label_counts": dict(
                self.validation_dataset_tail_label_counts
            ),
            "validation_quality_gate_status": str(
                self.validation_quality_gate_status
            ),
            "validation_quality_gate_reasons": list(
                self.validation_quality_gate_reasons
            ),
            "validation_dataset_export_ready": bool(
                self.validation_dataset_export_ready
            ),
            "validation_dataset_replay_ready": bool(
                self.validation_dataset_replay_ready
            ),
            "validation_quality_gate_result": dict(
                self.validation_quality_gate_result
            ),
            # Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0 fields.
            "paper_alpha_gate_evaluated_count": int(
                self.paper_alpha_gate_evaluated_count
            ),
            "paper_alpha_rule_evaluated_count": int(
                self.paper_alpha_rule_evaluated_count
            ),
            "paper_alpha_cohort_evaluated_count": int(
                self.paper_alpha_cohort_evaluated_count
            ),
            "paper_alpha_report_generated_count": int(
                self.paper_alpha_report_generated_count
            ),
            "paper_alpha_gate_status": str(self.paper_alpha_gate_status),
            "paper_alpha_gate_reasons": list(self.paper_alpha_gate_reasons),
            "paper_alpha_gate_warnings": list(
                self.paper_alpha_gate_warnings
            ),
            "paper_alpha_gate_sample_count": int(
                self.paper_alpha_gate_sample_count
            ),
            "paper_alpha_strategy_mode_results": dict(
                self.paper_alpha_strategy_mode_results
            ),
            "paper_alpha_candidate_stage_results": dict(
                self.paper_alpha_candidate_stage_results
            ),
            "paper_alpha_score_bucket_results": dict(
                self.paper_alpha_score_bucket_results
            ),
            "paper_alpha_cluster_results": dict(
                self.paper_alpha_cluster_results
            ),
            "paper_alpha_missed_alpha_warnings": int(
                self.paper_alpha_missed_alpha_warnings
            ),
            "paper_alpha_late_chase_warnings": int(
                self.paper_alpha_late_chase_warnings
            ),
            "paper_alpha_follow_risk_warnings": int(
                self.paper_alpha_follow_risk_warnings
            ),
            "paper_alpha_leader_preference_signals": int(
                self.paper_alpha_leader_preference_signals
            ),
            "paper_alpha_gate_report": dict(self.paper_alpha_gate_report),
            # Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort Evidence
            # Pack v0 fields.
            "regime_cluster_evidence_pack_generated_count": int(
                self.regime_cluster_evidence_pack_generated_count
            ),
            "regime_cluster_cohort_summary_generated_count": int(
                self.regime_cluster_cohort_summary_generated_count
            ),
            "regime_cluster_evidence_status": str(
                self.regime_cluster_evidence_status
            ),
            "regime_cluster_sample_count": int(
                self.regime_cluster_sample_count
            ),
            "regime_cluster_completed_tail_label_count": int(
                self.regime_cluster_completed_tail_label_count
            ),
            "regime_cluster_insufficient_sample_reasons": list(
                self.regime_cluster_insufficient_sample_reasons
            ),
            "regime_cluster_warnings": list(self.regime_cluster_warnings),
            "regime_cluster_signals": list(self.regime_cluster_signals),
            "regime_cohort_summary": dict(self.regime_cohort_summary),
            "cluster_cohort_summary": dict(self.cluster_cohort_summary),
            "score_bucket_summary": dict(self.score_bucket_summary),
            "stage_outcome_summary": dict(self.stage_outcome_summary),
            "strategy_mode_outcome_summary": dict(
                self.strategy_mode_outcome_summary
            ),
            "regime_cluster_evidence_pack": dict(
                self.regime_cluster_evidence_pack
            ),
        }


class DailyReportBuilder:
    """Builds :class:`DailyReportSnapshot` from a :class:`EventRepository`.

    The builder is stateless aside from the wired repository and
    output directory. Each :meth:`build` call queries events.db,
    aggregates the numbers, and writes one Markdown file under
    ``output_dir / filename``.
    """

    def __init__(
        self,
        *,
        event_repo: EventRepository,
        output_dir: Path,
        filename_template: str = "{date}-paper-report.md",
    ) -> None:
        self._event_repo = event_repo
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._filename_template = filename_template

    @property
    def output_dir(self) -> Path:
        return self._output_dir

    # ------------------------------------------------------------------
    def build(
        self,
        *,
        started_at_ms: int,
        finished_at_ms: int | None = None,
        clock_ms: int | None = None,
        safety_summary: Mapping[str, bool] | None = None,
        paper_cloud_summary: Mapping[str, Any] | None = None,
        write_to_disk: bool = True,
        error_notes: Iterable[str] = (),
        degraded_notes: Iterable[str] = (),
        rate_limit_metrics: Mapping[str, Any] | None = None,
        ingestion_errors: int | None = None,
        ws_metrics: Mapping[str, Any] | None = None,
        candidate_pool_metrics: Mapping[str, Any] | None = None,
        adaptive_metrics: Mapping[str, Any] | None = None,
        label_runtime_metrics: Mapping[str, Any] | None = None,
        strategy_validation_metrics: Mapping[str, Any] | None = None,
    ) -> DailyReportSnapshot:
        """Build the daily report.

        ``started_at_ms`` is the Phase 11B run's first observation; the
        builder pulls every event in ``[started_at_ms, finished_at_ms]``
        from events.db so the cadence-driven cloud loop reports the
        previous 24-hour window without leakage.

        Phase 11C.1A additions:

        ``rate_limit_metrics`` carries the
        :meth:`BinancePublicRestGovernor.metrics_payload` dict so the
        builder can report exact governor counters that may not be
        fully reconstructable from events.db alone (the governor still
        emits ``RATE_LIMIT_429`` / ``RATE_LIMIT_BACKOFF_STARTED`` /
        ``RATE_LIMIT_BACKOFF_ENDED`` / ``RATE_LIMIT_418`` /
        ``RATE_LIMIT_PROTECTION_ENTERED`` events on every transition,
        and the builder cross-checks the event counts against the
        governor counters before rendering).

        ``ingestion_errors`` is the runner-side count of failed REST
        ingest attempts (e.g. transport failures that did NOT trigger
        a 429 or 418).

        Phase 11C.1C-A addition:

        ``adaptive_metrics`` carries the
        :meth:`WSRadarChainDriver.adaptive_metrics_payload` dict so the
        builder can render the new
        ``Phase 11C.1C-A Adaptive Candidate Regime & Strategy Selector``
        Markdown section. The builder cross-checks the event-log
        counts of the six new event types
        (``MARKET_REGIME_ASSESSED`` / ``CANDIDATE_STAGE_CLASSIFIED`` /
        ``OPPORTUNITY_SCORED`` / ``STRATEGY_MODE_SELECTED`` /
        ``CLUSTER_CONTEXT_ATTACHED`` / ``LABEL_QUEUE_ENQUEUED``)
        against those counters before rendering.

        Phase 11C.1C-C-B-A addition:

        ``strategy_validation_metrics`` carries the
        :meth:`StrategyValidationRuntime.metrics_payload` dict so the
        builder can render the new
        ``Phase 11C.1C-C-B-A Strategy Validation Lab v0 & Cluster
        Exposure Control Contracts`` Markdown section. The builder
        cross-checks the event-log counts of the seven new event
        types
        (``STRATEGY_VALIDATION_SAMPLE_CREATED`` /
        ``STRATEGY_VALIDATION_REPORT_GENERATED`` /
        ``STRATEGY_MODE_VALIDATED`` /
        ``CANDIDATE_STAGE_VALIDATED`` / ``SCORE_BUCKET_VALIDATED`` /
        ``CLUSTER_EXPOSURE_ASSESSED`` /
        ``CLUSTER_LEADER_VALIDATED``) against those counters before
        rendering. The section is paper / report only; nothing it
        produces authorises a real trade.
        """
        finished_ms = (
            finished_at_ms
            if finished_at_ms is not None
            else (clock_ms if clock_ms is not None else now_ms())
        )
        events = self._event_repo.list_events(
            since_ts=int(started_at_ms),
            until_ts=int(finished_ms),
        )
        snapshot = self._aggregate(
            events=events,
            started_at_ms=int(started_at_ms),
            finished_at_ms=int(finished_ms),
            safety_summary=safety_summary or {},
            paper_cloud_summary=paper_cloud_summary or {},
            error_notes=tuple(error_notes),
            degraded_notes=tuple(degraded_notes),
            rate_limit_metrics=dict(rate_limit_metrics or {}),
            ingestion_errors=ingestion_errors,
            ws_metrics=dict(ws_metrics or {}),
            candidate_pool_metrics=dict(candidate_pool_metrics or {}),
            adaptive_metrics=dict(adaptive_metrics or {}),
            label_runtime_metrics=dict(label_runtime_metrics or {}),
            strategy_validation_metrics=dict(
                strategy_validation_metrics or {}
            ),
        )

        if write_to_disk:
            date_label = snapshot.date
            filename = self._filename_template.format(date=date_label)
            target = self._output_dir / filename
            self._output_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(snapshot.markdown, encoding="utf-8")
        return snapshot

    # ------------------------------------------------------------------
    def _aggregate(
        self,
        *,
        events: list[Event],
        started_at_ms: int,
        finished_at_ms: int,
        safety_summary: Mapping[str, bool],
        paper_cloud_summary: Mapping[str, Any],
        error_notes: tuple[str, ...],
        degraded_notes: tuple[str, ...],
        rate_limit_metrics: Mapping[str, Any] | None = None,
        ingestion_errors: int | None = None,
        ws_metrics: Mapping[str, Any] | None = None,
        candidate_pool_metrics: Mapping[str, Any] | None = None,
        adaptive_metrics: Mapping[str, Any] | None = None,
        label_runtime_metrics: Mapping[str, Any] | None = None,
        strategy_validation_metrics: Mapping[str, Any] | None = None,
    ) -> DailyReportSnapshot:
        date_label = datetime.fromtimestamp(
            finished_at_ms / 1000.0, tz=timezone.utc
        ).strftime("%Y-%m-%d")

        type_counts: Counter[str] = Counter()
        reject_reasons: Counter[str] = Counter()
        symbol_counts: Counter[str] = Counter()
        incidents_by_level: Counter[str] = Counter()
        paper_realized_pnl = 0.0
        paper_unrealized_pnl = 0.0
        paper_trade_count = 0
        candidate_opportunity_ids: set[str] = set()
        new_opens_paused = False
        local_error_notes: list[str] = []
        local_degraded_notes: list[str] = []

        for ev in events:
            type_counts[ev.event_type.value] += 1
            if ev.symbol:
                symbol_counts[str(ev.symbol)] += 1
            payload = ev.payload or {}
            if ev.event_type is EventType.RISK_REJECTED:
                for r in payload.get("reasons") or []:
                    reject_reasons[str(r)] += 1
            if ev.event_type is EventType.OPPORTUNITY_GRADED:
                opp_id = payload.get("opportunity_id")
                if opp_id:
                    candidate_opportunity_ids.add(str(opp_id))
            if ev.event_type is EventType.POSITION_CLOSED:
                paper_trade_count += 1
                try:
                    paper_realized_pnl += float(
                        payload.get("realized_pnl", 0.0) or 0.0
                    )
                except (TypeError, ValueError):
                    pass
            if ev.event_type is EventType.POSITION_UPDATED:
                try:
                    paper_unrealized_pnl = float(
                        payload.get("unrealized_pnl", paper_unrealized_pnl)
                    )
                except (TypeError, ValueError):
                    pass
            if ev.event_type is EventType.INCIDENT_OPENED:
                incidents_by_level[str(payload.get("level", "P3"))] += 1
            if ev.event_type is EventType.RECONCILIATION_RESOLVED:
                if bool(payload.get("new_opens_paused")):
                    new_opens_paused = True
                if int(payload.get("p0_count", 0) or 0) > 0:
                    local_error_notes.append(
                        f"reconciliation_p0={int(payload.get('p0_count', 0))}"
                    )
                if int(payload.get("p1_count", 0) or 0) > 0:
                    local_degraded_notes.append(
                        f"reconciliation_p1={int(payload.get('p1_count', 0))}"
                    )
            if ev.event_type is EventType.LLM_DEGRADED:
                reasons = payload.get("degraded_reasons") or payload.get(
                    "reasons"
                ) or []
                if reasons:
                    local_degraded_notes.append(
                        "llm_degraded:" + ",".join(str(r) for r in reasons)
                    )
            if ev.event_type is EventType.PROTECTION_MODE_ENTERED:
                local_error_notes.append(
                    f"protection_entered:{payload.get('reason', 'unknown')}"
                )

        capital_count = sum(
            type_counts.get(t.value, 0) for t in CAPITAL_EVENT_TYPES
        )

        # Phase 11C.1A - rate-limit metrics. The runner passes the
        # governor's metrics_payload() through ``rate_limit_metrics``.
        # Counts are double-checked against the events.db audit trail
        # so a stale governor counter cannot hide a real protection
        # event.
        gov_metrics = dict(rate_limit_metrics or {})
        rate_limit_429_count = max(
            int(gov_metrics.get("rate_limit_429_count", 0) or 0),
            int(type_counts.get(EventType.RATE_LIMIT_429.value, 0)),
        )
        rate_limit_418_count = max(
            int(gov_metrics.get("rate_limit_418_count", 0) or 0),
            int(type_counts.get(EventType.RATE_LIMIT_418.value, 0)),
        )
        backoff_started_from_events = int(
            type_counts.get(EventType.RATE_LIMIT_BACKOFF_STARTED.value, 0)
        )
        backoff_ended_from_events = int(
            type_counts.get(EventType.RATE_LIMIT_BACKOFF_ENDED.value, 0)
        )
        protection_entered_from_events = int(
            type_counts.get(
                EventType.RATE_LIMIT_PROTECTION_ENTERED.value, 0
            )
        )
        rate_limit_protection_triggered = bool(
            gov_metrics.get("rate_limit_protection_triggered", False)
        ) or protection_entered_from_events > 0
        rate_limit_ban = bool(
            gov_metrics.get("rate_limit_ban", False)
        ) or rate_limit_418_count > 0
        # If the governor never saw a 429/418 the daily report still
        # shows zero - that is the steady-state Phase 11C.1A
        # invariant: a healthy run shows zero counts and the
        # protection flag stays False.
        ingestion_errors_value = int(
            ingestion_errors
            if ingestion_errors is not None
            else int(gov_metrics.get("ingestion_errors", 0) or 0)
        )

        snapshot = DailyReportSnapshot(
            date=date_label,
            started_at_ms=int(started_at_ms),
            finished_at_ms=int(finished_at_ms),
            uptime_seconds=max(
                0, int((finished_at_ms - started_at_ms) // 1000)
            ),
            event_count=len(events),
            candidate_opportunity_count=len(candidate_opportunity_ids),
            risk_approved_count=int(
                type_counts.get(EventType.RISK_APPROVED.value, 0)
            ),
            risk_rejected_count=int(
                type_counts.get(EventType.RISK_REJECTED.value, 0)
            ),
            state_transition_count=int(
                type_counts.get(EventType.STATE_TRANSITION.value, 0)
            ),
            paper_trade_count=paper_trade_count,
            paper_realized_pnl=float(paper_realized_pnl),
            paper_unrealized_pnl=float(paper_unrealized_pnl),
            capital_rebase_count=int(
                type_counts.get(EventType.CAPITAL_REBASE.value, 0)
            ),
            capital_deposit_count=int(
                type_counts.get(EventType.CAPITAL_DEPOSIT.value, 0)
            ),
            capital_withdrawal_count=int(
                type_counts.get(EventType.CAPITAL_WITHDRAWAL.value, 0)
            ),
            incidents_p0_count=int(incidents_by_level.get("P0", 0)),
            incidents_p1_count=int(incidents_by_level.get("P1", 0)),
            incidents_p2_count=int(incidents_by_level.get("P2", 0)),
            incidents_p3_count=int(incidents_by_level.get("P3", 0)),
            protection_mode_entered_count=int(
                type_counts.get(EventType.PROTECTION_MODE_ENTERED.value, 0)
            ),
            protection_mode_exited_count=int(
                type_counts.get(EventType.PROTECTION_MODE_EXITED.value, 0)
            ),
            telegram_messages_sent_count=int(
                type_counts.get(EventType.TELEGRAM_MESSAGE_SENT.value, 0)
            ),
            telegram_send_failed_count=int(
                type_counts.get(EventType.TELEGRAM_SEND_FAILED.value, 0)
            ),
            telegram_command_rejected_count=int(
                type_counts.get(EventType.TELEGRAM_COMMAND_REJECTED.value, 0)
            ),
            data_export_generated_count=int(
                type_counts.get(EventType.DATA_EXPORT_GENERATED.value, 0)
            ),
            data_export_failed_count=int(
                type_counts.get(EventType.DATA_EXPORT_FAILED.value, 0)
            ),
            llm_interpreted_count=int(
                type_counts.get(EventType.LLM_INTERPRETED.value, 0)
            ),
            llm_degraded_count=int(
                type_counts.get(EventType.LLM_DEGRADED.value, 0)
            ),
            llm_schema_rejected_count=int(
                type_counts.get(EventType.LLM_SCHEMA_REJECTED.value, 0)
            ),
            reconciliation_started_count=int(
                type_counts.get(EventType.RECONCILIATION_STARTED.value, 0)
            ),
            reconciliation_resolved_count=int(
                type_counts.get(EventType.RECONCILIATION_RESOLVED.value, 0)
            ),
            reconciliation_mismatch_count=int(
                type_counts.get(EventType.RECONCILIATION_MISMATCH.value, 0)
            ),
            new_opens_paused=bool(new_opens_paused),
            top_reject_reasons=tuple(
                reject_reasons.most_common(_TOP_REJECT_REASONS_LIMIT)
            ),
            top_symbols=tuple(symbol_counts.most_common(_TOP_SYMBOLS_LIMIT)),
            error_notes=tuple(list(error_notes) + local_error_notes),
            degraded_notes=tuple(list(degraded_notes) + local_degraded_notes),
            safety_summary=dict(safety_summary),
            paper_cloud_summary=dict(paper_cloud_summary),
            # Phase 11C.1A rate-limit metrics.
            rate_limit_429_count=int(rate_limit_429_count),
            rate_limit_418_count=int(rate_limit_418_count),
            retry_after_seconds_last=int(
                gov_metrics.get("retry_after_seconds_last", 0) or 0
            ),
            retry_after_seconds_total=int(
                gov_metrics.get("retry_after_seconds_total", 0) or 0
            ),
            used_weight_1m_last=int(
                gov_metrics.get("used_weight_1m_last", 0) or 0
            ),
            used_weight_1m_max=int(
                gov_metrics.get("used_weight_1m_max", 0) or 0
            ),
            rest_requests_total=int(
                gov_metrics.get("rest_requests_total", 0) or 0
            ),
            rest_requests_skipped_by_budget=int(
                gov_metrics.get("rest_requests_skipped_by_budget", 0) or 0
            ),
            rate_limit_protection_triggered=bool(
                rate_limit_protection_triggered
            ),
            rate_limit_ban=bool(rate_limit_ban),
            rate_limit_backoff_started_count=int(
                max(
                    int(gov_metrics.get("backoff_started_count", 0) or 0),
                    backoff_started_from_events,
                )
            ),
            rate_limit_backoff_ended_count=int(
                max(
                    int(gov_metrics.get("backoff_ended_count", 0) or 0),
                    backoff_ended_from_events,
                )
            ),
            ingestion_errors=int(ingestion_errors_value),
            rate_limit_metrics=dict(gov_metrics),
            # Phase 11C.1B WS-first radar metrics.
            ws_messages_received=int(
                (ws_metrics or {}).get("ws_messages_received", 0) or 0
            ),
            ws_messages_received_by_stream=dict(
                (ws_metrics or {}).get(
                    "ws_messages_received_by_stream", {}
                )
                or {}
            ),
            ws_reconnect_count=int(
                max(
                    int((ws_metrics or {}).get("ws_reconnect_count", 0) or 0),
                    int(type_counts.get(EventType.PUBLIC_WS_DISCONNECTED.value, 0)),
                )
            ),
            ws_staleness_ms_max=int(
                (ws_metrics or {}).get("ws_staleness_ms_max", 0) or 0
            ),
            ws_stale_count=int(
                max(
                    int((ws_metrics or {}).get("ws_stale_count", 0) or 0),
                    int(type_counts.get(EventType.PUBLIC_WS_STALE.value, 0)),
                )
            ),
            ws_connect_count=int(
                max(
                    int((ws_metrics or {}).get("ws_connect_count", 0) or 0),
                    int(type_counts.get(EventType.PUBLIC_WS_CONNECTED.value, 0)),
                )
            ),
            ws_disconnect_count=int(
                (ws_metrics or {}).get("ws_disconnect_count", 0) or 0
            ),
            ws_is_stale=bool(
                (ws_metrics or {}).get("ws_is_stale", False)
            ),
            radar_candidates_seen=int(
                (candidate_pool_metrics or {}).get(
                    "radar_candidates_seen", 0
                )
                or 0
            ),
            candidate_pool_size_max=int(
                (candidate_pool_metrics or {}).get(
                    "candidate_pool_size_max", 0
                )
                or 0
            ),
            pre_anomaly_candidates=int(
                (candidate_pool_metrics or {}).get(
                    "candidate_pool_promoted", 0
                )
                or 0
            ),
            liquidation_events_seen=int(
                (candidate_pool_metrics or {}).get(
                    "liquidation_events_seen", 0
                )
                or 0
            ),
            radar_score_top_symbols=list(
                (candidate_pool_metrics or {}).get(
                    "candidate_pool_top_symbols", []
                )
                or []
            ),
            ws_metrics=dict(ws_metrics or {}),
            candidate_pool_metrics=dict(candidate_pool_metrics or {}),
            # Phase 11C.1C-A adaptive metrics. The values come from
            # the ``adaptive_metrics`` kwarg first; the event-log
            # counts of the six new event types are used as a
            # cross-check / fall-back so a stale runner counter
            # cannot under-report a real adaptive event.
            market_regime_counts=dict(
                (adaptive_metrics or {}).get("market_regime_counts", {})
                or {}
            ),
            candidate_stage_counts=dict(
                (adaptive_metrics or {}).get("candidate_stage_counts", {})
                or {}
            ),
            strategy_mode_counts=dict(
                (adaptive_metrics or {}).get("strategy_mode_counts", {})
                or {}
            ),
            opportunity_grade_counts=dict(
                (adaptive_metrics or {}).get("opportunity_grade_counts", {})
                or {}
            ),
            top_opportunity_scores=list(
                (adaptive_metrics or {}).get("top_opportunity_scores", [])
                or []
            ),
            label_queue_enqueued=int(
                max(
                    int(
                        (adaptive_metrics or {}).get(
                            "label_queue_enqueued", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.LABEL_QUEUE_ENQUEUED.value, 0
                        )
                    ),
                )
            ),
            observe_count=int(
                (adaptive_metrics or {}).get("observe_count", 0) or 0
            ),
            reject_count=int(
                (adaptive_metrics or {}).get("reject_count", 0) or 0
            ),
            follow_count=int(
                (adaptive_metrics or {}).get("follow_count", 0) or 0
            ),
            pullback_count=int(
                (adaptive_metrics or {}).get("pullback_count", 0) or 0
            ),
            late_chase_rejected_count=int(
                (adaptive_metrics or {}).get(
                    "late_chase_rejected_count", 0
                )
                or 0
            ),
            blowoff_observed_count=int(
                (adaptive_metrics or {}).get("blowoff_observed_count", 0)
                or 0
            ),
            market_regime_assessed_count=int(
                max(
                    int(
                        (adaptive_metrics or {}).get(
                            "market_regime_assessed_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.MARKET_REGIME_ASSESSED.value, 0
                        )
                    ),
                )
            ),
            candidate_stage_classified_count=int(
                max(
                    int(
                        (adaptive_metrics or {}).get(
                            "candidate_stage_classified_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.CANDIDATE_STAGE_CLASSIFIED.value, 0
                        )
                    ),
                )
            ),
            opportunity_scored_count=int(
                max(
                    int(
                        (adaptive_metrics or {}).get(
                            "opportunity_scored_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.OPPORTUNITY_SCORED.value, 0
                        )
                    ),
                )
            ),
            strategy_mode_selected_count=int(
                max(
                    int(
                        (adaptive_metrics or {}).get(
                            "strategy_mode_selected_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.STRATEGY_MODE_SELECTED.value, 0
                        )
                    ),
                )
            ),
            cluster_context_attached_count=int(
                max(
                    int(
                        (adaptive_metrics or {}).get(
                            "cluster_context_attached_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.CLUSTER_CONTEXT_ATTACHED.value, 0
                        )
                    ),
                )
            ),
            adaptive_metrics=dict(adaptive_metrics or {}),
            # Phase 11C.1C-B runtime calibration aggregates. Values
            # come from the chain's ``adaptive_metrics_payload`` first
            # (per-driven-candidate accuracy); the candidate-pool
            # metrics fill in pool-wide aggregates (protected count,
            # threshold).
            top_early_tail_candidates=list(
                (adaptive_metrics or {}).get(
                    "top_early_tail_candidates", []
                )
                or []
            ),
            top_late_chase_risk_candidates=list(
                (adaptive_metrics or {}).get(
                    "top_late_chase_risk_candidates", []
                )
                or []
            ),
            early_tail_score_top_symbols=list(
                (adaptive_metrics or {}).get(
                    "early_tail_score_top_symbols", []
                )
                or []
            ),
            opportunity_score_distribution=dict(
                (adaptive_metrics or {}).get(
                    "opportunity_score_distribution", {}
                )
                or {}
            ),
            symbols_promoted_before_24h_top_move=list(
                (adaptive_metrics or {}).get(
                    "symbols_promoted_before_24h_top_move", []
                )
                or []
            ),
            eden_alt_near_examples=list(
                (adaptive_metrics or {}).get(
                    "eden_alt_near_examples", []
                )
                or []
            ),
            early_tail_protect_threshold=float(
                (candidate_pool_metrics or {}).get(
                    "early_tail_protect_threshold", 0.0
                )
                or 0.0
            ),
            candidate_pool_promoted_before_24h_top_move=int(
                (candidate_pool_metrics or {}).get(
                    "candidate_pool_promoted_before_24h_top_move", 0
                )
                or 0
            ),
            # Phase 11C.1C-C-A label-tracking runtime aggregates.
            label_tracking_started_count=int(
                max(
                    int(
                        (label_runtime_metrics or {}).get(
                            "label_tracking_started_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.LABEL_TRACKING_STARTED.value, 0
                        )
                    ),
                )
            ),
            label_window_updated_count=int(
                max(
                    int(
                        (label_runtime_metrics or {}).get(
                            "label_window_updated_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.LABEL_WINDOW_UPDATED.value, 0
                        )
                    ),
                )
            ),
            label_window_completed_count=int(
                max(
                    int(
                        (label_runtime_metrics or {}).get(
                            "label_window_completed_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.LABEL_WINDOW_COMPLETED.value, 0
                        )
                    ),
                )
            ),
            tail_label_assigned_count=int(
                max(
                    int(
                        (label_runtime_metrics or {}).get(
                            "tail_label_assigned_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.TAIL_LABEL_ASSIGNED.value, 0
                        )
                    ),
                )
            ),
            missed_tail_detected_count=int(
                max(
                    int(
                        (label_runtime_metrics or {}).get(
                            "missed_tail_detected_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.MISSED_TAIL_DETECTED.value, 0
                        )
                    ),
                )
            ),
            fake_breakout_detected_count=int(
                max(
                    int(
                        (label_runtime_metrics or {}).get(
                            "fake_breakout_detected_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.FAKE_BREAKOUT_DETECTED.value, 0
                        )
                    ),
                )
            ),
            pending_label_records=int(
                (label_runtime_metrics or {}).get(
                    "pending_label_records", 0
                )
                or 0
            ),
            completed_label_records=int(
                (label_runtime_metrics or {}).get(
                    "completed_label_records", 0
                )
                or 0
            ),
            expired_label_records=int(
                (label_runtime_metrics or {}).get(
                    "expired_label_records", 0
                )
                or 0
            ),
            unresolved_label_records=int(
                (label_runtime_metrics or {}).get(
                    "unresolved_label_records", 0
                )
                or 0
            ),
            tail_label_distribution=dict(
                (label_runtime_metrics or {}).get(
                    "tail_label_distribution", {}
                )
                or {}
            ),
            reached_2r_count=int(
                (label_runtime_metrics or {}).get("reached_2r_count", 0)
                or 0
            ),
            reached_3r_count=int(
                (label_runtime_metrics or {}).get("reached_3r_count", 0)
                or 0
            ),
            reached_5r_count=int(
                (label_runtime_metrics or {}).get("reached_5r_count", 0)
                or 0
            ),
            reached_10r_count=int(
                (label_runtime_metrics or {}).get("reached_10r_count", 0)
                or 0
            ),
            early_tail_score_bucket_outcomes=dict(
                (label_runtime_metrics or {}).get(
                    "early_tail_score_bucket_outcomes", {}
                )
                or {}
            ),
            opportunity_score_bucket_outcomes=dict(
                (label_runtime_metrics or {}).get(
                    "opportunity_score_bucket_outcomes", {}
                )
                or {}
            ),
            strategy_mode_outcomes=dict(
                (label_runtime_metrics or {}).get(
                    "strategy_mode_outcomes", {}
                )
                or {}
            ),
            late_chase_risk_bucket_outcomes=dict(
                (label_runtime_metrics or {}).get(
                    "late_chase_risk_bucket_outcomes", {}
                )
                or {}
            ),
            top_mfe_symbols=list(
                (label_runtime_metrics or {}).get("top_mfe_symbols", [])
                or []
            ),
            worst_mae_symbols=list(
                (label_runtime_metrics or {}).get("worst_mae_symbols", [])
                or []
            ),
            missed_tail_symbols=list(
                (label_runtime_metrics or {}).get("missed_tail_symbols", [])
                or []
            ),
            fake_breakout_symbols=list(
                (label_runtime_metrics or {}).get(
                    "fake_breakout_symbols", []
                )
                or []
            ),
            label_runtime_metrics=dict(label_runtime_metrics or {}),
            # Phase 11C.1C-C-B-A Strategy Validation Lab v0 + Cluster
            # Exposure Control Contracts. Values come from the
            # ``strategy_validation_metrics`` kwarg first; the
            # event-log counts of the seven new event types are used
            # as a cross-check / fall-back so a stale runner counter
            # cannot under-report a real validation event.
            strategy_validation_sample_count=int(
                (strategy_validation_metrics or {}).get(
                    "strategy_validation_sample_count", 0
                )
                or 0
            ),
            strategy_validation_sample_created_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "strategy_validation_sample_created_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.STRATEGY_VALIDATION_SAMPLE_CREATED.value,
                            0,
                        )
                    ),
                )
            ),
            strategy_validation_report_generated_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "strategy_validation_report_generated_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.STRATEGY_VALIDATION_REPORT_GENERATED.value,
                            0,
                        )
                    ),
                )
            ),
            strategy_mode_validated_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "strategy_mode_validated_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.STRATEGY_MODE_VALIDATED.value, 0
                        )
                    ),
                )
            ),
            candidate_stage_validated_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "candidate_stage_validated_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.CANDIDATE_STAGE_VALIDATED.value, 0
                        )
                    ),
                )
            ),
            score_bucket_validated_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "score_bucket_validated_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.SCORE_BUCKET_VALIDATED.value, 0
                        )
                    ),
                )
            ),
            cluster_exposure_assessed_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "cluster_exposure_assessed_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.CLUSTER_EXPOSURE_ASSESSED.value, 0
                        )
                    ),
                )
            ),
            cluster_leader_validated_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "cluster_leader_validated_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.CLUSTER_LEADER_VALIDATED.value, 0
                        )
                    ),
                )
            ),
            strategy_mode_validation=dict(
                (strategy_validation_metrics or {}).get(
                    "strategy_mode_validation", {}
                )
                or {}
            ),
            candidate_stage_validation=dict(
                (strategy_validation_metrics or {}).get(
                    "candidate_stage_validation", {}
                )
                or {}
            ),
            opportunity_score_bucket_validation=dict(
                (strategy_validation_metrics or {}).get(
                    "opportunity_score_bucket_validation", {}
                )
                or {}
            ),
            early_tail_score_bucket_validation=dict(
                (strategy_validation_metrics or {}).get(
                    "early_tail_score_bucket_validation", {}
                )
                or {}
            ),
            strategy_validation_tail_label_distribution=dict(
                (strategy_validation_metrics or {}).get(
                    "tail_label_distribution", {}
                )
                or {}
            ),
            top_strategy_validation_symbols=list(
                (strategy_validation_metrics or {}).get(
                    "top_strategy_validation_symbols", []
                )
                or []
            ),
            cluster_exposure_assessments=list(
                (strategy_validation_metrics or {}).get(
                    "cluster_exposure_assessments", []
                )
                or []
            ),
            cluster_leader_validation=dict(
                (strategy_validation_metrics or {}).get(
                    "cluster_leader_validation", {}
                )
                or {}
            ),
            cluster_leader_outperformance_count=int(
                (strategy_validation_metrics or {}).get(
                    "cluster_leader_outperformance_count", 0
                )
                or 0
            ),
            overexposure_warning_count=int(
                (strategy_validation_metrics or {}).get(
                    "overexposure_warning_count", 0
                )
                or 0
            ),
            strategy_validation_flagged_findings=list(
                (strategy_validation_metrics or {}).get(
                    "flagged_findings", []
                )
                or []
            ),
            strategy_validation_metrics=dict(
                strategy_validation_metrics or {}
            ),
            # Phase 11C.1C-C-B-B-A - dataset / quality-gate sub-block
            # read off the runtime metrics payload. Event-log counts
            # of the three new event types are used as the
            # cross-check / fall-back so a stale runner counter
            # cannot under-report a real dataset / gate event.
            validation_dataset_built_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "validation_dataset_built_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.STRATEGY_VALIDATION_DATASET_BUILT.value,
                            0,
                        )
                    ),
                )
            ),
            validation_dataset_exported_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "validation_dataset_exported_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.STRATEGY_VALIDATION_DATASET_EXPORTED.value,
                            0,
                        )
                    ),
                )
            ),
            validation_quality_gate_evaluated_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "validation_quality_gate_evaluated_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED.value,
                            0,
                        )
                    ),
                )
            ),
            validation_dataset_records=int(
                (strategy_validation_metrics or {}).get(
                    "validation_dataset_records", 0
                )
                or 0
            ),
            validation_dataset_symbols=list(
                (strategy_validation_metrics or {}).get(
                    "validation_dataset_symbols", []
                )
                or []
            ),
            validation_dataset_tail_label_counts=dict(
                (strategy_validation_metrics or {}).get(
                    "validation_dataset_tail_label_counts", {}
                )
                or {}
            ),
            validation_quality_gate_status=str(
                (strategy_validation_metrics or {}).get(
                    "validation_quality_gate_status", ""
                )
                or ""
            ),
            validation_quality_gate_reasons=list(
                (strategy_validation_metrics or {}).get(
                    "validation_quality_gate_reasons", []
                )
                or []
            ),
            validation_dataset_export_ready=bool(
                (strategy_validation_metrics or {}).get(
                    "validation_dataset_export_ready", False
                )
            ),
            validation_dataset_replay_ready=bool(
                (strategy_validation_metrics or {}).get(
                    "validation_dataset_replay_ready", False
                )
            ),
            validation_quality_gate_result=dict(
                (strategy_validation_metrics or {}).get(
                    "validation_quality_gate_result", {}
                )
                or {}
            ),
            # Phase 11C.1C-C-B-B-B-A - Paper Alpha Gate v0 sub-block
            # read off the runtime metrics payload. Event-log counts
            # of the four new event types are used as the
            # cross-check / fall-back so a stale runner counter
            # cannot under-report a real Paper Alpha Gate event.
            paper_alpha_gate_evaluated_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "paper_alpha_gate_evaluated_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.PAPER_ALPHA_GATE_EVALUATED.value,
                            0,
                        )
                    ),
                )
            ),
            paper_alpha_rule_evaluated_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "paper_alpha_rule_evaluated_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.PAPER_ALPHA_RULE_EVALUATED.value,
                            0,
                        )
                    ),
                )
            ),
            paper_alpha_cohort_evaluated_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "paper_alpha_cohort_evaluated_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.PAPER_ALPHA_COHORT_EVALUATED.value,
                            0,
                        )
                    ),
                )
            ),
            paper_alpha_report_generated_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "paper_alpha_report_generated_count", 0
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.PAPER_ALPHA_REPORT_GENERATED.value,
                            0,
                        )
                    ),
                )
            ),
            paper_alpha_gate_status=str(
                (strategy_validation_metrics or {}).get(
                    "paper_alpha_gate_status", ""
                )
                or ""
            ),
            paper_alpha_gate_reasons=list(
                (strategy_validation_metrics or {}).get(
                    "paper_alpha_gate_reasons", []
                )
                or []
            ),
            paper_alpha_gate_warnings=list(
                (strategy_validation_metrics or {}).get(
                    "paper_alpha_gate_warnings", []
                )
                or []
            ),
            paper_alpha_gate_sample_count=int(
                (strategy_validation_metrics or {}).get(
                    "paper_alpha_gate_sample_count", 0
                )
                or 0
            ),
            paper_alpha_strategy_mode_results=dict(
                (strategy_validation_metrics or {}).get(
                    "paper_alpha_strategy_mode_results", {}
                )
                or {}
            ),
            paper_alpha_candidate_stage_results=dict(
                (strategy_validation_metrics or {}).get(
                    "paper_alpha_candidate_stage_results", {}
                )
                or {}
            ),
            paper_alpha_score_bucket_results=dict(
                (strategy_validation_metrics or {}).get(
                    "paper_alpha_score_bucket_results", {}
                )
                or {}
            ),
            paper_alpha_cluster_results=dict(
                (strategy_validation_metrics or {}).get(
                    "paper_alpha_cluster_results", {}
                )
                or {}
            ),
            paper_alpha_missed_alpha_warnings=int(
                (strategy_validation_metrics or {}).get(
                    "paper_alpha_missed_alpha_warnings", 0
                )
                or 0
            ),
            paper_alpha_late_chase_warnings=int(
                (strategy_validation_metrics or {}).get(
                    "paper_alpha_late_chase_warnings", 0
                )
                or 0
            ),
            paper_alpha_follow_risk_warnings=int(
                (strategy_validation_metrics or {}).get(
                    "paper_alpha_follow_risk_warnings", 0
                )
                or 0
            ),
            paper_alpha_leader_preference_signals=int(
                (strategy_validation_metrics or {}).get(
                    "paper_alpha_leader_preference_signals", 0
                )
                or 0
            ),
            paper_alpha_gate_report=dict(
                (strategy_validation_metrics or {}).get(
                    "paper_alpha_gate_report", {}
                )
                or {}
            ),
            # Phase 11C.1C-C-B-B-B-B - Regime & Cluster Cohort
            # Evidence Pack v0 sub-block read off the runtime metrics
            # payload. Event-log counts of the two new event types
            # are used as the cross-check / fall-back so a stale
            # runner counter cannot under-report a real evidence-pack
            # event.
            regime_cluster_evidence_pack_generated_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "regime_cluster_evidence_pack_generated_count",
                            0,
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.REGIME_CLUSTER_EVIDENCE_PACK_GENERATED.value,
                            0,
                        )
                    ),
                )
            ),
            regime_cluster_cohort_summary_generated_count=int(
                max(
                    int(
                        (strategy_validation_metrics or {}).get(
                            "regime_cluster_cohort_summary_generated_count",
                            0,
                        )
                        or 0
                    ),
                    int(
                        type_counts.get(
                            EventType.REGIME_CLUSTER_COHORT_SUMMARY_GENERATED.value,
                            0,
                        )
                    ),
                )
            ),
            regime_cluster_evidence_status=str(
                (strategy_validation_metrics or {}).get(
                    "regime_cluster_evidence_status", ""
                )
                or ""
            ),
            regime_cluster_sample_count=int(
                (strategy_validation_metrics or {}).get(
                    "regime_cluster_sample_count", 0
                )
                or 0
            ),
            regime_cluster_completed_tail_label_count=int(
                (strategy_validation_metrics or {}).get(
                    "regime_cluster_completed_tail_label_count", 0
                )
                or 0
            ),
            regime_cluster_insufficient_sample_reasons=list(
                (strategy_validation_metrics or {}).get(
                    "regime_cluster_insufficient_sample_reasons", []
                )
                or []
            ),
            regime_cluster_warnings=list(
                (strategy_validation_metrics or {}).get(
                    "regime_cluster_warnings", []
                )
                or []
            ),
            regime_cluster_signals=list(
                (strategy_validation_metrics or {}).get(
                    "regime_cluster_signals", []
                )
                or []
            ),
            regime_cohort_summary=dict(
                (strategy_validation_metrics or {}).get(
                    "regime_cohort_summary", {}
                )
                or {}
            ),
            cluster_cohort_summary=dict(
                (strategy_validation_metrics or {}).get(
                    "cluster_cohort_summary", {}
                )
                or {}
            ),
            score_bucket_summary=dict(
                (strategy_validation_metrics or {}).get(
                    "score_bucket_summary", {}
                )
                or {}
            ),
            stage_outcome_summary=dict(
                (strategy_validation_metrics or {}).get(
                    "stage_outcome_summary", {}
                )
                or {}
            ),
            strategy_mode_outcome_summary=dict(
                (strategy_validation_metrics or {}).get(
                    "strategy_mode_outcome_summary", {}
                )
                or {}
            ),
            regime_cluster_evidence_pack=dict(
                (strategy_validation_metrics or {}).get(
                    "regime_cluster_evidence_pack", {}
                )
                or {}
            ),
        )
        # Build Markdown last so we can embed the snapshot itself.
        markdown = self._render_markdown(
            snapshot=snapshot, capital_count=capital_count
        )
        # Defence-in-depth: refuse to emit a report that contains a
        # forbidden literal.
        assert_no_forbidden_substrings(markdown)
        return _replace_markdown(snapshot, markdown)

    # ------------------------------------------------------------------
    def _render_markdown(
        self,
        *,
        snapshot: DailyReportSnapshot,
        capital_count: int,
    ) -> str:
        """Render the daily report Markdown body."""
        safety_lines = "\n".join(
            f"- `{k}` = `{v}`"
            for k, v in sorted(snapshot.safety_summary.items())
        ) or "- (no safety summary supplied)"

        cloud_lines = "\n".join(
            f"- `{k}` = `{json.dumps(v, separators=(',', ':'), default=str)}`"
            for k, v in sorted(snapshot.paper_cloud_summary.items())
        ) or "- (no paper-cloud summary supplied)"

        top_reject = "\n".join(
            f"- `{r}` x {c}" for r, c in snapshot.top_reject_reasons
        ) or "- (no risk rejections in this window)"

        top_symbols = "\n".join(
            f"- `{s}` x {c}" for s, c in snapshot.top_symbols
        ) or "- (no symbol activity in this window)"

        error_notes = "\n".join(
            f"- `{n}`" for n in snapshot.error_notes
        ) or "- (no error notes in this window)"

        degraded_notes = "\n".join(
            f"- `{n}`" for n in snapshot.degraded_notes
        ) or "- (no degraded notes in this window)"

        rate_limit_block = (
            f"- HTTP 429 count: **{snapshot.rate_limit_429_count}**\n"
            f"- HTTP 418 count: **{snapshot.rate_limit_418_count}**\n"
            f"- Retry-After last (seconds): "
            f"**{snapshot.retry_after_seconds_last}**\n"
            f"- Retry-After total (seconds): "
            f"**{snapshot.retry_after_seconds_total}**\n"
            f"- X-MBX-USED-WEIGHT-1M last: "
            f"**{snapshot.used_weight_1m_last}**\n"
            f"- X-MBX-USED-WEIGHT-1M max: "
            f"**{snapshot.used_weight_1m_max}**\n"
            f"- REST requests total: **{snapshot.rest_requests_total}**\n"
            f"- REST requests skipped by budget: "
            f"**{snapshot.rest_requests_skipped_by_budget}**\n"
            f"- Backoff windows started: "
            f"**{snapshot.rate_limit_backoff_started_count}**\n"
            f"- Backoff windows ended: "
            f"**{snapshot.rate_limit_backoff_ended_count}**\n"
            f"- Rate-limit protection triggered: "
            f"**{snapshot.rate_limit_protection_triggered}**\n"
            f"- Rate-limit IP ban observed: "
            f"**{snapshot.rate_limit_ban}**\n"
            f"- Ingestion errors (transport): "
            f"**{snapshot.ingestion_errors}**\n"
        )

        ws_top_lines = "\n".join(
            f"- `{row.get('symbol', '?')}` score="
            f"{float(row.get('radar_score', 0.0)):.2f} "
            f"state={row.get('state', '?')}"
            for row in (snapshot.radar_score_top_symbols or [])[:10]
        ) or "- (no radar candidates in this window)"

        ws_messages_by_stream_lines = "\n".join(
            f"- `{stream}` x {count}"
            for stream, count in sorted(
                snapshot.ws_messages_received_by_stream.items()
            )
        ) or "- (no WS messages observed)"

        ws_block = (
            f"- WS messages received: "
            f"**{snapshot.ws_messages_received}**\n"
            f"- WS reconnect count: "
            f"**{snapshot.ws_reconnect_count}**\n"
            f"- WS staleness (ms) max: "
            f"**{snapshot.ws_staleness_ms_max}**\n"
            f"- WS stale event count: "
            f"**{snapshot.ws_stale_count}**\n"
            f"- WS connect count: "
            f"**{snapshot.ws_connect_count}**\n"
            f"- WS disconnect count: "
            f"**{snapshot.ws_disconnect_count}**\n"
            f"- WS currently stale: **{snapshot.ws_is_stale}**\n"
            f"- Radar candidates seen: "
            f"**{snapshot.radar_candidates_seen}**\n"
            f"- Candidate pool size max: "
            f"**{snapshot.candidate_pool_size_max}**\n"
            f"- Pre-anomaly candidates promoted: "
            f"**{snapshot.pre_anomaly_candidates}**\n"
            f"- Liquidation events seen: "
            f"**{snapshot.liquidation_events_seen}**\n"
        )

        # Phase 11C.1C-A - Adaptive Candidate Regime & Strategy Selector
        # Markdown block. Every value is read straight off the
        # snapshot so a stale runner counter cannot under-report a
        # real adaptive event (the snapshot's
        # ``..._count`` fields take ``max`` of the runner counter and
        # the events.db count).
        def _kv_lines(d: dict) -> str:
            if not d:
                return "- (no entries in this window)"
            return "\n".join(
                f"- `{k}` x {int(v)}" for k, v in sorted(
                    d.items(), key=lambda r: (-int(r[1]), str(r[0]))
                )
            )

        market_regime_lines = _kv_lines(snapshot.market_regime_counts)
        candidate_stage_lines = _kv_lines(snapshot.candidate_stage_counts)
        strategy_mode_lines = _kv_lines(snapshot.strategy_mode_counts)
        opportunity_grade_lines = _kv_lines(snapshot.opportunity_grade_counts)
        if snapshot.top_opportunity_scores:
            top_score_lines = "\n".join(
                f"- `{row.get('symbol', '?')}` "
                f"score={float(row.get('score', 0.0)):.2f} "
                f"grade={row.get('grade', '?')} "
                f"opp={row.get('opportunity_id', '?')}"
                for row in snapshot.top_opportunity_scores[:10]
            )
        else:
            top_score_lines = "- (no opportunity scores in this window)"

        adaptive_block = (
            f"- MARKET_REGIME_ASSESSED count: "
            f"**{snapshot.market_regime_assessed_count}**\n"
            f"- CANDIDATE_STAGE_CLASSIFIED count: "
            f"**{snapshot.candidate_stage_classified_count}**\n"
            f"- OPPORTUNITY_SCORED count: "
            f"**{snapshot.opportunity_scored_count}**\n"
            f"- STRATEGY_MODE_SELECTED count: "
            f"**{snapshot.strategy_mode_selected_count}**\n"
            f"- CLUSTER_CONTEXT_ATTACHED count: "
            f"**{snapshot.cluster_context_attached_count}**\n"
            f"- LABEL_QUEUE_ENQUEUED count: "
            f"**{snapshot.label_queue_enqueued}**\n"
            f"- Strategy modes: follow="
            f"{snapshot.follow_count} pullback="
            f"{snapshot.pullback_count} observe="
            f"{snapshot.observe_count} reject="
            f"{snapshot.reject_count}\n"
            f"- Late-chase rejected: "
            f"**{snapshot.late_chase_rejected_count}**\n"
            f"- Blowoff observed: "
            f"**{snapshot.blowoff_observed_count}**\n"
        )

        # Phase 11C.1C-B - Adaptive Candidate Runtime Calibration &
        # Early Tail Discovery v0 Markdown block. Every value is read
        # straight off the snapshot. The block is paper / virtual
        # only; nothing here authorises a real trade.
        if snapshot.top_early_tail_candidates:
            top_early_tail_lines = "\n".join(
                f"- `{row.get('symbol', '?')}` "
                f"early_tail_score="
                f"{float(row.get('early_tail_score', 0.0)):.2f} "
                f"freshness="
                f"{float(row.get('freshness_score', 0.0)):.2f} "
                f"opp={row.get('opportunity_id', '?')}"
                for row in snapshot.top_early_tail_candidates[:10]
            )
        else:
            top_early_tail_lines = (
                "- (no early-tail candidates in this window)"
            )
        if snapshot.top_late_chase_risk_candidates:
            top_late_chase_lines = "\n".join(
                f"- `{row.get('symbol', '?')}` "
                f"late_chase_risk="
                f"{float(row.get('late_chase_risk', 0.0)):.2f} "
                f"stage={row.get('candidate_stage', '?')} "
                f"opp={row.get('opportunity_id', '?')}"
                for row in snapshot.top_late_chase_risk_candidates[:10]
            )
        else:
            top_late_chase_lines = (
                "- (no late-chase candidates in this window)"
            )
        if snapshot.opportunity_score_distribution:
            distribution_lines = "\n".join(
                f"- `{bucket}` x {count}"
                for bucket, count in sorted(
                    snapshot.opportunity_score_distribution.items()
                )
            )
        else:
            distribution_lines = (
                "- (no opportunity scores in this window)"
            )
        if snapshot.eden_alt_near_examples:
            eden_lines = "\n".join(
                f"- `{row.get('symbol', '?')}` "
                f"early_tail_score="
                f"{float(row.get('early_tail_score', 0.0)):.2f} "
                f"opp={row.get('opportunity_id', '?')}"
                for row in snapshot.eden_alt_near_examples[:5]
            )
        else:
            eden_lines = (
                "- (no EDEN / ALT / NEAR-style demon-coin candidates "
                "observed)"
            )

        runtime_calibration_block = (
            f"- Top early-tail candidates: "
            f"**{len(snapshot.top_early_tail_candidates)}**\n"
            f"- Top late-chase-risk candidates: "
            f"**{len(snapshot.top_late_chase_risk_candidates)}**\n"
            f"- Symbols promoted before 24h top move (chain): "
            f"**{len(snapshot.symbols_promoted_before_24h_top_move)}**\n"
            f"- Symbols promoted before 24h top move (pool): "
            f"**{snapshot.candidate_pool_promoted_before_24h_top_move}**\n"
            f"- Early-tail protect threshold: "
            f"**{snapshot.early_tail_protect_threshold:.2f}**\n"
        )

        # ---- Phase 11C.1C-C-A label-tracking runtime block ----
        label_runtime_block = (
            f"- LABEL_TRACKING_STARTED count: "
            f"**{snapshot.label_tracking_started_count}**\n"
            f"- LABEL_WINDOW_UPDATED count: "
            f"**{snapshot.label_window_updated_count}**\n"
            f"- LABEL_WINDOW_COMPLETED count: "
            f"**{snapshot.label_window_completed_count}**\n"
            f"- TAIL_LABEL_ASSIGNED count: "
            f"**{snapshot.tail_label_assigned_count}**\n"
            f"- MISSED_TAIL_DETECTED count: "
            f"**{snapshot.missed_tail_detected_count}**\n"
            f"- FAKE_BREAKOUT_DETECTED count: "
            f"**{snapshot.fake_breakout_detected_count}**\n"
            f"- Pending records: **{snapshot.pending_label_records}** "
            f"completed: **{snapshot.completed_label_records}** "
            f"expired: **{snapshot.expired_label_records}** "
            f"unresolved: **{snapshot.unresolved_label_records}**\n"
            f"- Reached 2R: **{snapshot.reached_2r_count}** "
            f"3R: **{snapshot.reached_3r_count}** "
            f"5R: **{snapshot.reached_5r_count}** "
            f"10R: **{snapshot.reached_10r_count}**\n"
        )
        if snapshot.tail_label_distribution:
            tail_dist_lines = "\n".join(
                f"- `{label}` x {int(count)}"
                for label, count in sorted(
                    snapshot.tail_label_distribution.items(),
                    key=lambda r: (-int(r[1]), str(r[0])),
                )
            )
        else:
            tail_dist_lines = "- (no tail labels assigned in this window)"
        if snapshot.top_mfe_symbols:
            top_mfe_lines = "\n".join(
                f"- `{row.get('symbol', '?')}` "
                f"mfe={float(row.get('mfe_pct', 0.0)) * 100.0:.2f}% "
                f"opp={row.get('opportunity_id', '?')}"
                for row in snapshot.top_mfe_symbols[:10]
            )
        else:
            top_mfe_lines = "- (no completed label records in this window)"
        if snapshot.worst_mae_symbols:
            worst_mae_lines = "\n".join(
                f"- `{row.get('symbol', '?')}` "
                f"mae={float(row.get('mae_pct', 0.0)) * 100.0:.2f}% "
                f"opp={row.get('opportunity_id', '?')}"
                for row in snapshot.worst_mae_symbols[:10]
            )
        else:
            worst_mae_lines = "- (no completed label records in this window)"
        if snapshot.missed_tail_symbols:
            missed_lines = "\n".join(
                f"- `{row.get('symbol', '?')}` "
                f"label={row.get('tail_label', '?')} "
                f"opp={row.get('opportunity_id', '?')}"
                for row in snapshot.missed_tail_symbols[:10]
            )
        else:
            missed_lines = "- (no missed-tail outcomes in this window)"
        if snapshot.fake_breakout_symbols:
            fake_lines = "\n".join(
                f"- `{row.get('symbol', '?')}` "
                f"label={row.get('tail_label', '?')} "
                f"opp={row.get('opportunity_id', '?')}"
                for row in snapshot.fake_breakout_symbols[:10]
            )
        else:
            fake_lines = "- (no fake-breakout outcomes in this window)"

        def _bucket_outcome_lines(
            buckets: dict[str, dict[str, int]],
        ) -> str:
            if not buckets:
                return "- (no entries in this window)"
            lines: list[str] = []
            for bucket in sorted(buckets):
                inner = buckets[bucket]
                pairs = ", ".join(
                    f"{label}={int(c)}"
                    for label, c in sorted(inner.items())
                    if int(c) > 0
                )
                lines.append(f"- `{bucket}`: {pairs or '(no labels)'}")
            return "\n".join(lines)

        early_tail_outcome_lines = _bucket_outcome_lines(
            snapshot.early_tail_score_bucket_outcomes
        )
        opp_score_outcome_lines = _bucket_outcome_lines(
            snapshot.opportunity_score_bucket_outcomes
        )
        strategy_mode_outcome_lines = _bucket_outcome_lines(
            snapshot.strategy_mode_outcomes
        )
        late_chase_outcome_lines = _bucket_outcome_lines(
            snapshot.late_chase_risk_bucket_outcomes
        )

        # ---- Phase 11C.1C-C-B-A Strategy Validation Lab v0 + Cluster
        # Exposure Control Contracts. Paper / report only. The
        # ``suggested_cluster_action`` field on every cluster
        # assessment is descriptive; the Risk Engine remains the
        # single trade-decision gate.
        sv_block = (
            f"- STRATEGY_VALIDATION_SAMPLE_CREATED count: "
            f"**{snapshot.strategy_validation_sample_created_count}**\n"
            f"- STRATEGY_VALIDATION_REPORT_GENERATED count: "
            f"**{snapshot.strategy_validation_report_generated_count}**\n"
            f"- STRATEGY_MODE_VALIDATED count: "
            f"**{snapshot.strategy_mode_validated_count}**\n"
            f"- CANDIDATE_STAGE_VALIDATED count: "
            f"**{snapshot.candidate_stage_validated_count}**\n"
            f"- SCORE_BUCKET_VALIDATED count: "
            f"**{snapshot.score_bucket_validated_count}**\n"
            f"- CLUSTER_EXPOSURE_ASSESSED count: "
            f"**{snapshot.cluster_exposure_assessed_count}**\n"
            f"- CLUSTER_LEADER_VALIDATED count: "
            f"**{snapshot.cluster_leader_validated_count}**\n"
            f"- Validation samples in latest report: "
            f"**{snapshot.strategy_validation_sample_count}**\n"
            f"- Cluster leader outperformance count: "
            f"**{snapshot.cluster_leader_outperformance_count}**\n"
            f"- Overexposure warning count: "
            f"**{snapshot.overexposure_warning_count}**\n"
        )

        if snapshot.strategy_validation_sample_count == 0:
            sv_empty_line = (
                "- (no samples in this window; empty Strategy "
                "Validation Lab v0 report - this is expected when "
                "no Phase 11C.1C-C-A primary window completed during "
                "the run)\n"
            )
        else:
            sv_empty_line = ""

        def _sv_cohort_lines(
            buckets: dict[str, dict[str, Any]],
            *,
            label_field: str,
        ) -> str:
            if not buckets:
                return "- (no cohort entries in this window)"
            lines: list[str] = []
            for key in sorted(buckets):
                stats = buckets.get(key) or {}
                if not isinstance(stats, dict):
                    continue
                count = int(stats.get("sample_count", 0) or 0)
                avg_mfe = float(stats.get("avg_mfe", 0.0) or 0.0)
                avg_mae = float(stats.get("avg_mae", 0.0) or 0.0)
                fake_rate = float(stats.get("fake_breakout_rate", 0.0) or 0.0)
                missed_rate = float(stats.get("missed_tail_rate", 0.0) or 0.0)
                strong_rate = float(stats.get("strong_tail_rate", 0.0) or 0.0)
                p2r = float(stats.get("p_reached_2r", 0.0) or 0.0)
                p3r = float(stats.get("p_reached_3r", 0.0) or 0.0)
                p5r = float(stats.get("p_reached_5r", 0.0) or 0.0)
                lines.append(
                    f"- `{label_field}={key}` n={count} "
                    f"avg_mfe={avg_mfe:.4f} avg_mae={avg_mae:.4f} "
                    f"strong={strong_rate:.3f} fake={fake_rate:.3f} "
                    f"missed={missed_rate:.3f} "
                    f"p2r={p2r:.3f} p3r={p3r:.3f} p5r={p5r:.3f}"
                )
            return "\n".join(lines)

        sv_strategy_mode_lines = _sv_cohort_lines(
            snapshot.strategy_mode_validation, label_field="strategy_mode"
        )
        sv_candidate_stage_lines = _sv_cohort_lines(
            snapshot.candidate_stage_validation,
            label_field="candidate_stage",
        )
        sv_opp_bucket_lines = _sv_cohort_lines(
            snapshot.opportunity_score_bucket_validation,
            label_field="opportunity_score_bucket",
        )
        sv_ets_bucket_lines = _sv_cohort_lines(
            snapshot.early_tail_score_bucket_validation,
            label_field="early_tail_score_bucket",
        )
        sv_tail_dist = snapshot.strategy_validation_tail_label_distribution
        sv_tail_dist_counts = (
            sv_tail_dist.get("counts", {})
            if isinstance(sv_tail_dist, dict)
            else {}
        )
        if sv_tail_dist_counts:
            sv_tail_dist_lines = "\n".join(
                f"- `{label}` x {int(count)}"
                for label, count in sorted(
                    sv_tail_dist_counts.items(),
                    key=lambda r: (-int(r[1]), str(r[0])),
                )
            )
        else:
            sv_tail_dist_lines = (
                "- (no tail labels in this Strategy Validation Lab "
                "report)"
            )
        if snapshot.top_strategy_validation_symbols:
            sv_top_symbol_lines = "\n".join(
                f"- `{row.get('symbol', '?')}` "
                f"mfe={float(row.get('mfe', 0.0)) * 100.0:.2f}% "
                f"mae={float(row.get('mae', 0.0)) * 100.0:.2f}% "
                f"mode={row.get('strategy_mode', '?')} "
                f"stage={row.get('candidate_stage', '?')} "
                f"label={row.get('tail_label', '?')} "
                f"opp={row.get('opportunity_id', '?')}"
                for row in snapshot.top_strategy_validation_symbols[:10]
            )
        else:
            sv_top_symbol_lines = (
                "- (no validation samples in this window)"
            )
        if snapshot.cluster_exposure_assessments:
            sv_cluster_lines = "\n".join(
                f"- cluster=`{row.get('cluster_id', '?')}` "
                f"size={int(row.get('cluster_size', 0) or 0)} "
                f"correlated={int(row.get('correlated_candidate_count', 0) or 0)} "
                f"leader=`{row.get('leader_symbol') or '-'}` "
                f"mfe_mean={float(row.get('cluster_mfe_mean', 0.0)) * 100.0:.2f}% "
                f"leader_outperformed={row.get('leader_outperformed_followers', False)} "
                f"overexposure={row.get('overexposure_warning', False)} "
                f"action=`{row.get('suggested_cluster_action', 'no_action')}`"
                for row in snapshot.cluster_exposure_assessments[:10]
            )
        else:
            sv_cluster_lines = (
                "- (no cluster exposure assessments in this window)"
            )
        if snapshot.cluster_leader_validation:
            sv_leader_lines = "\n".join(
                (
                    f"- cluster=`{cluster}` "
                    f"leader=`{(stats or {}).get('leader_symbol') or '-'}` "
                    f"leader_n={int((stats or {}).get('leader_sample_count', 0) or 0)} "
                    f"follower_n={int((stats or {}).get('follower_sample_count', 0) or 0)} "
                    f"leader_mfe={float((stats or {}).get('leader_avg_mfe', 0.0)) * 100.0:.2f}% "
                    f"follower_mfe={float((stats or {}).get('follower_avg_mfe', 0.0)) * 100.0:.2f}% "
                    f"outperformed={(stats or {}).get('leader_outperformed_followers', False)}"
                )
                for cluster, stats in sorted(
                    snapshot.cluster_leader_validation.items()
                )
            )
        else:
            sv_leader_lines = (
                "- (no cluster leader validation in this window)"
            )
        if snapshot.strategy_validation_flagged_findings:
            sv_findings_lines = "\n".join(
                f"- `{f}`"
                for f in snapshot.strategy_validation_flagged_findings
            )
        else:
            sv_findings_lines = (
                "- (no flagged findings in this Strategy Validation "
                "Lab v0 report)"
            )

        # ---- Phase 11C.1C-C-B-B-A Strategy Validation Dataset
        # Builder & Quality Gate v0. Paper / report only. The
        # ``validation_quality_gate_status`` is a *descriptive*
        # label (one of ``pass`` / ``warn`` / ``fail``) and **MUST
        # NEVER trigger a real trade**; the Risk Engine remains the
        # single trade-decision gate.
        sv_dataset_block = (
            f"- STRATEGY_VALIDATION_DATASET_BUILT count: "
            f"**{snapshot.validation_dataset_built_count}**\n"
            f"- STRATEGY_VALIDATION_DATASET_EXPORTED count: "
            f"**{snapshot.validation_dataset_exported_count}**\n"
            f"- STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED count: "
            f"**{snapshot.validation_quality_gate_evaluated_count}**\n"
            f"- Validation dataset records: "
            f"**{snapshot.validation_dataset_records}**\n"
            f"- Validation dataset symbols: "
            f"**{len(snapshot.validation_dataset_symbols)}**\n"
            f"- Quality gate status: "
            f"**{snapshot.validation_quality_gate_status or '(not evaluated)'}**\n"
            f"- Validation dataset export ready: "
            f"**{snapshot.validation_dataset_export_ready}**\n"
            f"- Validation dataset replay ready: "
            f"**{snapshot.validation_dataset_replay_ready}**\n"
        )
        if snapshot.validation_dataset_tail_label_counts:
            sv_dataset_tail_lines = "\n".join(
                f"- `{label}` x {int(count)}"
                for label, count in sorted(
                    snapshot.validation_dataset_tail_label_counts.items(),
                    key=lambda r: (-int(r[1]), str(r[0])),
                )
            )
        else:
            sv_dataset_tail_lines = (
                "- (no validation dataset tail labels in this window)"
            )
        if snapshot.validation_dataset_symbols:
            sv_dataset_symbol_lines = "\n".join(
                f"- `{s}`"
                for s in snapshot.validation_dataset_symbols[:20]
            )
        else:
            sv_dataset_symbol_lines = (
                "- (no validation dataset symbols in this window)"
            )
        if snapshot.validation_quality_gate_reasons:
            sv_dataset_reason_lines = "\n".join(
                f"- `{r}`"
                for r in snapshot.validation_quality_gate_reasons
            )
        else:
            sv_dataset_reason_lines = (
                "- (no quality gate reasons in this window)"
            )

        # ---- Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0. Paper /
        # report only. The ``paper_alpha_gate_status`` is a
        # *descriptive* label (one of ``PASS`` / ``WARN`` / ``FAIL``
        # / ``INCONCLUSIVE``) and **MUST NEVER trigger a real
        # trade** and **MUST NEVER** modify position size,
        # leverage, stop-loss, target price, the Risk Engine, or
        # the Execution FSM. The Risk Engine remains the single
        # trade-decision gate.
        paper_alpha_block = (
            f"- PAPER_ALPHA_GATE_EVALUATED count: "
            f"**{snapshot.paper_alpha_gate_evaluated_count}**\n"
            f"- PAPER_ALPHA_RULE_EVALUATED count: "
            f"**{snapshot.paper_alpha_rule_evaluated_count}**\n"
            f"- PAPER_ALPHA_COHORT_EVALUATED count: "
            f"**{snapshot.paper_alpha_cohort_evaluated_count}**\n"
            f"- PAPER_ALPHA_REPORT_GENERATED count: "
            f"**{snapshot.paper_alpha_report_generated_count}**\n"
            f"- Paper alpha gate status: "
            f"**{snapshot.paper_alpha_gate_status or '(not evaluated)'}**\n"
            f"- Paper alpha gate sample count: "
            f"**{snapshot.paper_alpha_gate_sample_count}**\n"
            f"- Paper alpha missed-alpha warnings: "
            f"**{snapshot.paper_alpha_missed_alpha_warnings}**\n"
            f"- Paper alpha late-chase warnings: "
            f"**{snapshot.paper_alpha_late_chase_warnings}**\n"
            f"- Paper alpha follow-risk warnings: "
            f"**{snapshot.paper_alpha_follow_risk_warnings}**\n"
            f"- Paper alpha leader-preference signals: "
            f"**{snapshot.paper_alpha_leader_preference_signals}**\n"
        )

        if snapshot.paper_alpha_gate_reasons:
            paper_alpha_reason_lines = "\n".join(
                f"- `{r}`" for r in snapshot.paper_alpha_gate_reasons
            )
        else:
            paper_alpha_reason_lines = (
                "- (no paper alpha gate reasons in this window)"
            )

        if snapshot.paper_alpha_gate_warnings:
            paper_alpha_warning_lines = "\n".join(
                f"- `{w}`" for w in snapshot.paper_alpha_gate_warnings
            )
        else:
            paper_alpha_warning_lines = (
                "- (no paper alpha gate warnings in this window)"
            )

        def _cohort_metric_lines(payload: Mapping[str, Any]) -> str:
            if not isinstance(payload, Mapping) or not payload:
                return "- (no entries in this window)"
            status = str(payload.get("status") or "")
            n = int(payload.get("sample_count", 0) or 0)
            signals = list(payload.get("signals") or [])
            warnings = list(payload.get("warnings") or [])
            metrics = payload.get("metrics") or {}
            metric_pairs = ", ".join(
                f"{k}={float(v):.3f}"
                for k, v in sorted(metrics.items())
                if isinstance(v, (int, float))
            )
            lines = [
                f"- status=**{status or '(unset)'}** n={n} "
                f"signals={signals or '-'} warnings={warnings or '-'}"
            ]
            if metric_pairs:
                lines.append(f"  - metrics: {metric_pairs}")
            return "\n".join(lines)

        paper_alpha_strategy_mode_lines = _cohort_metric_lines(
            snapshot.paper_alpha_strategy_mode_results
        )
        paper_alpha_candidate_stage_lines = _cohort_metric_lines(
            snapshot.paper_alpha_candidate_stage_results
        )
        paper_alpha_opp_bucket_lines = _cohort_metric_lines(
            (snapshot.paper_alpha_score_bucket_results or {}).get(
                "opportunity_score_bucket"
            )
            or {}
        )
        paper_alpha_ets_bucket_lines = _cohort_metric_lines(
            (snapshot.paper_alpha_score_bucket_results or {}).get(
                "early_tail_score_bucket"
            )
            or {}
        )
        paper_alpha_cluster_lines = _cohort_metric_lines(
            snapshot.paper_alpha_cluster_results
        )

        # ---- Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort
        # Evidence Pack v0. Paper / report / evidence only. The
        # ``regime_cluster_evidence_status`` is a *descriptive*
        # roll-up (one of ``INSUFFICIENT_SAMPLE`` / ``OBSERVE_ONLY``
        # / ``WARNING`` / ``EVIDENCE_SIGNAL``) and **MUST NEVER
        # trigger a real trade** and **MUST NEVER** modify position
        # size, leverage, stop-loss, target price, the Risk Engine,
        # or the Execution FSM. The Risk Engine remains the single
        # trade-decision gate.
        regime_cluster_block = (
            f"- REGIME_CLUSTER_EVIDENCE_PACK_GENERATED count: "
            f"**{snapshot.regime_cluster_evidence_pack_generated_count}**\n"
            f"- REGIME_CLUSTER_COHORT_SUMMARY_GENERATED count: "
            f"**{snapshot.regime_cluster_cohort_summary_generated_count}**\n"
            f"- Regime / cluster evidence status: "
            f"**{snapshot.regime_cluster_evidence_status or '(not evaluated)'}**\n"
            f"- Regime / cluster sample count: "
            f"**{snapshot.regime_cluster_sample_count}**\n"
            f"- Regime / cluster completed tail-label count: "
            f"**{snapshot.regime_cluster_completed_tail_label_count}**\n"
        )

        if snapshot.regime_cluster_insufficient_sample_reasons:
            regime_cluster_insufficient_lines = "\n".join(
                f"- `{r}`"
                for r in snapshot.regime_cluster_insufficient_sample_reasons
            )
        else:
            regime_cluster_insufficient_lines = (
                "- (no insufficient_sample reasons in this window)"
            )

        if snapshot.regime_cluster_warnings:
            regime_cluster_warning_lines = "\n".join(
                f"- `{w}`" for w in snapshot.regime_cluster_warnings
            )
        else:
            regime_cluster_warning_lines = (
                "- (no regime/cluster warnings in this window)"
            )

        if snapshot.regime_cluster_signals:
            regime_cluster_signal_lines = "\n".join(
                f"- `{s}`" for s in snapshot.regime_cluster_signals
            )
        else:
            regime_cluster_signal_lines = (
                "- (no regime/cluster signals in this window)"
            )

        def _evidence_row_lines(rows: Sequence[Mapping[str, Any]]) -> str:
            if not rows:
                return "- (no entries in this window)"
            lines: list[str] = []
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                key = row.get("key") or {}
                dim = (
                    str(key.get("dimension"))
                    if isinstance(key, Mapping)
                    else ""
                )
                val = (
                    str(key.get("value"))
                    if isinstance(key, Mapping)
                    else ""
                )
                n = int(row.get("sample_count", 0) or 0)
                completed = int(
                    row.get("completed_tail_label_count", 0) or 0
                )
                strong_rate = float(row.get("strong_tail_rate", 0.0) or 0.0)
                p3r = float(row.get("reached_3r_rate", 0.0) or 0.0)
                p5r = float(row.get("reached_5r_rate", 0.0) or 0.0)
                fake = float(row.get("fake_breakout_rate", 0.0) or 0.0)
                missed = float(row.get("missed_tail_rate", 0.0) or 0.0)
                late = float(
                    row.get("late_chase_failure_rate", 0.0) or 0.0
                )
                med_mfe = float(row.get("median_mfe", 0.0) or 0.0)
                med_mae = float(row.get("median_mae", 0.0) or 0.0)
                status = str(row.get("status") or "")
                signals = list(row.get("signals") or [])
                warnings = list(row.get("warnings") or [])
                lines.append(
                    f"- `{dim}={val}` n={n} completed={completed} "
                    f"status=**{status or '(unset)'}** "
                    f"strong={strong_rate:.3f} 3r={p3r:.3f} "
                    f"5r={p5r:.3f} fake={fake:.3f} "
                    f"missed={missed:.3f} late={late:.3f} "
                    f"mfe~={med_mfe:.4f} mae~={med_mae:.4f} "
                    f"signals={signals or '-'} warnings={warnings or '-'}"
                )
            return "\n".join(lines) if lines else "- (no entries)"

        regime_rows = (snapshot.regime_cohort_summary or {}).get("rows") or []
        cluster_rows = (snapshot.cluster_cohort_summary or {}).get(
            "rows"
        ) or []
        leader_follower_rows = (
            (snapshot.cluster_cohort_summary or {}).get(
                "leader_vs_follower_rows"
            )
            or []
        )
        opp_score_rows = (snapshot.score_bucket_summary or {}).get(
            "opportunity_score_rows"
        ) or []
        ets_score_rows = (snapshot.score_bucket_summary or {}).get(
            "early_tail_score_rows"
        ) or []
        stage_rows = (snapshot.stage_outcome_summary or {}).get(
            "rows"
        ) or []
        mode_rows = (snapshot.strategy_mode_outcome_summary or {}).get(
            "rows"
        ) or []

        regime_cluster_regime_lines = _evidence_row_lines(regime_rows)
        regime_cluster_cluster_lines = _evidence_row_lines(cluster_rows)
        regime_cluster_leader_follower_lines = _evidence_row_lines(
            leader_follower_rows
        )
        regime_cluster_opp_bucket_lines = _evidence_row_lines(
            opp_score_rows
        )
        regime_cluster_ets_bucket_lines = _evidence_row_lines(
            ets_score_rows
        )
        regime_cluster_stage_lines = _evidence_row_lines(stage_rows)
        regime_cluster_mode_lines = _evidence_row_lines(mode_rows)

        body = (
            f"# AMA-RT Phase 11B - Daily Paper Report\n\n"
            f"- **Date (UTC):** {snapshot.date}\n"
            f"- **Window:** {snapshot.started_at_ms} ms -> "
            f"{snapshot.finished_at_ms} ms (uptime "
            f"{snapshot.uptime_seconds}s)\n"
            f"- **Trading mode:** paper (Phase 1 safety lock in force)\n"
            f"- **New opens paused (latest reconciliation):** "
            f"{snapshot.new_opens_paused}\n\n"
            f"## Phase 1 safety summary\n{safety_lines}\n\n"
            f"## Paper-cloud configuration\n{cloud_lines}\n\n"
            f"## Counters\n"
            f"- Total events: **{snapshot.event_count}**\n"
            f"- Candidate opportunities: **"
            f"{snapshot.candidate_opportunity_count}**\n"
            f"- Risk approved: **{snapshot.risk_approved_count}**\n"
            f"- Risk rejected: **{snapshot.risk_rejected_count}**\n"
            f"- State transitions: **{snapshot.state_transition_count}**\n"
            f"- Paper trades closed: **{snapshot.paper_trade_count}**\n"
            f"- Paper realized PnL: **{snapshot.paper_realized_pnl:.4f}**\n"
            f"- Paper unrealized PnL: "
            f"**{snapshot.paper_unrealized_pnl:.4f}**\n"
            f"- Capital events (deposit/withdrawal/harvest/rebase/budget): "
            f"**{capital_count}**\n"
            f"- Capital rebases: **{snapshot.capital_rebase_count}**\n"
            f"- Capital deposits: **{snapshot.capital_deposit_count}**\n"
            f"- Capital withdrawals: **{snapshot.capital_withdrawal_count}**\n"
            f"- Reconciliations: started="
            f"{snapshot.reconciliation_started_count} resolved="
            f"{snapshot.reconciliation_resolved_count} mismatches="
            f"{snapshot.reconciliation_mismatch_count}\n"
            f"- Incidents: P0={snapshot.incidents_p0_count} "
            f"P1={snapshot.incidents_p1_count} "
            f"P2={snapshot.incidents_p2_count} "
            f"P3={snapshot.incidents_p3_count}\n"
            f"- Protection mode entered: "
            f"**{snapshot.protection_mode_entered_count}** "
            f"(exited: {snapshot.protection_mode_exited_count})\n"
            f"- Telegram messages sent: "
            f"**{snapshot.telegram_messages_sent_count}** "
            f"(failed: {snapshot.telegram_send_failed_count}, "
            f"commands rejected: {snapshot.telegram_command_rejected_count})\n"
            f"- Data exports generated: "
            f"**{snapshot.data_export_generated_count}** "
            f"(failed: {snapshot.data_export_failed_count})\n"
            f"- LLM events: interpreted={snapshot.llm_interpreted_count} "
            f"degraded={snapshot.llm_degraded_count} "
            f"schema_rejected={snapshot.llm_schema_rejected_count}\n\n"
            f"## Phase 11C.1A rate-limit governor\n{rate_limit_block}\n"
            f"## Phase 11C.1B WebSocket all-market radar\n{ws_block}\n"
            f"### WS messages by stream\n{ws_messages_by_stream_lines}\n\n"
            f"### Radar score top symbols\n{ws_top_lines}\n\n"
            f"## Phase 11C.1C-A Adaptive Candidate Regime "
            f"& Strategy Selector\n"
            f"_Adaptive sub-blocks are paper / virtual only. "
            f"Strategy modes do NOT authorise real orders; the Risk "
            f"Engine remains the single trade-decision gate._\n\n"
            f"{adaptive_block}\n"
            f"### Market regime counts\n{market_regime_lines}\n\n"
            f"### Candidate stage counts\n{candidate_stage_lines}\n\n"
            f"### Strategy mode counts\n{strategy_mode_lines}\n\n"
            f"### Opportunity grade counts\n{opportunity_grade_lines}\n\n"
            f"### Top opportunity scores\n{top_score_lines}\n\n"
            f"## Phase 11C.1C-B Adaptive Candidate Runtime "
            f"Calibration & Early Tail Discovery v0\n"
            f"_Runtime calibration sub-blocks are paper / virtual "
            f"only. ``early_tail_score`` is a discovery signal that "
            f"protects high-tail candidates from candidate-pool "
            f"capacity eviction; it does NOT authorise opening a "
            f"real position. Late / blowoff candidates remain "
            f"observe-only regardless of any early-tail score._\n\n"
            f"{runtime_calibration_block}\n"
            f"### Top early-tail candidates\n{top_early_tail_lines}\n\n"
            f"### Top late-chase-risk candidates\n"
            f"{top_late_chase_lines}\n\n"
            f"### Opportunity score distribution\n"
            f"{distribution_lines}\n\n"
            f"### EDEN / ALT / NEAR-style examples\n"
            f"{eden_lines}\n\n"
            f"## Phase 11C.1C-C-A MFE / MAE Label Queue Runtime "
            f"& Tail Outcome Tracking\n"
            f"_Label-tracking sub-blocks are paper / virtual only. "
            f"The runtime records candidate outcome labels; it does "
            f"NOT open / close any real position, and it does NOT "
            f"infer live position PnL. Tail labels are rule-based; "
            f"no LLM. Strategy validation conclusions are reserved "
            f"for the future Strategy Validation Lab._\n\n"
            f"{label_runtime_block}\n"
            f"### Tail label distribution\n{tail_dist_lines}\n\n"
            f"### Top MFE symbols (primary window)\n{top_mfe_lines}\n\n"
            f"### Worst MAE symbols (primary window)\n"
            f"{worst_mae_lines}\n\n"
            f"### Missed-tail symbols\n{missed_lines}\n\n"
            f"### Fake-breakout symbols\n{fake_lines}\n\n"
            f"### Outcome by early_tail_score bucket\n"
            f"{early_tail_outcome_lines}\n\n"
            f"### Outcome by opportunity_score bucket\n"
            f"{opp_score_outcome_lines}\n\n"
            f"### Outcome by strategy_mode\n"
            f"{strategy_mode_outcome_lines}\n\n"
            f"### Outcome by late_chase_risk bucket\n"
            f"{late_chase_outcome_lines}\n\n"
            f"## Phase 11C.1C-C-B-A Strategy Validation Lab v0 "
            f"& Cluster Exposure Control Contracts\n"
            f"_Strategy Validation Lab v0 sub-blocks are paper / "
            f"report only. Validation samples / cohort stats / "
            f"cluster assessments are descriptive; the "
            f"`suggested_cluster_action` on every cluster "
            f"assessment is one of `leader_only` / "
            f"`observe_followers` / `reject_cluster` / `no_action` "
            f"and **MUST NEVER trigger a real trade**. The Risk "
            f"Engine remains the single trade-decision gate. This "
            f"is **NOT** the complete Strategy Validation Lab, "
            f"**NOT** AI Learning, and **NOT** automatic parameter "
            f"optimisation; Phase 12 remains FORBIDDEN._\n\n"
            f"{sv_block}{sv_empty_line}\n"
            f"### Strategy mode validation (follow / pullback / "
            f"observe / reject)\n{sv_strategy_mode_lines}\n\n"
            f"### Candidate stage validation (early / mid / late / "
            f"blowoff / dumped)\n{sv_candidate_stage_lines}\n\n"
            f"### Opportunity score bucket validation\n"
            f"{sv_opp_bucket_lines}\n\n"
            f"### Early tail score bucket validation\n"
            f"{sv_ets_bucket_lines}\n\n"
            f"### Strategy Validation Lab v0 tail label distribution\n"
            f"{sv_tail_dist_lines}\n\n"
            f"### Top strategy validation symbols\n"
            f"{sv_top_symbol_lines}\n\n"
            f"### Cluster exposure assessments\n{sv_cluster_lines}\n\n"
            f"### Cluster leader validation\n{sv_leader_lines}\n\n"
            f"### Flagged findings\n{sv_findings_lines}\n\n"
            f"## Phase 11C.1C-C-B-B-A Strategy Validation Dataset "
            f"Builder & Quality Gate v0\n"
            f"_Strategy Validation Dataset / Quality Gate v0 sub-blocks "
            f"are paper / report only. The "
            f"`validation_quality_gate_status` is a **descriptive** "
            f"label (one of `pass` / `warn` / `fail`) and **MUST NEVER "
            f"trigger a real trade**. The Risk Engine remains the "
            f"single trade-decision gate. This is **NOT** the complete "
            f"Strategy Validation Lab follow-up (Phase 11C.1C-C-B-B-B), "
            f"**NOT** AI Learning, and **NOT** automatic parameter "
            f"optimisation; Phase 12 remains FORBIDDEN._\n\n"
            f"{sv_dataset_block}\n"
            f"### Validation dataset symbols\n"
            f"{sv_dataset_symbol_lines}\n\n"
            f"### Validation dataset tail label counts\n"
            f"{sv_dataset_tail_lines}\n\n"
            f"### Validation quality gate reasons\n"
            f"{sv_dataset_reason_lines}\n\n"
            f"## Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0\n"
            f"_Paper Alpha Gate v0 sub-blocks are paper / report / "
            f"evidence-only. The `paper_alpha_gate_status` is a "
            f"**descriptive** label (one of `PASS` / `WARN` / "
            f"`FAIL` / `INCONCLUSIVE`) and **MUST NEVER trigger a "
            f"real trade**, and **MUST NEVER** modify position size, "
            f"leverage, stop-loss, target price, the Risk Engine, "
            f"or the Execution FSM. The Risk Engine remains the "
            f"single trade-decision gate. This is **NOT** AI "
            f"Learning, **NOT** automatic parameter optimisation, "
            f"**NOT** reinforcement learning, **NOT** the complete "
            f"Strategy Validation Lab follow-up; Phase 12 remains "
            f"FORBIDDEN._\n\n"
            f"{paper_alpha_block}\n"
            f"### Paper alpha gate reasons\n{paper_alpha_reason_lines}\n\n"
            f"### Paper alpha gate warnings\n{paper_alpha_warning_lines}\n\n"
            f"### Paper alpha strategy_mode results\n"
            f"{paper_alpha_strategy_mode_lines}\n\n"
            f"### Paper alpha candidate_stage results\n"
            f"{paper_alpha_candidate_stage_lines}\n\n"
            f"### Paper alpha opportunity_score_bucket results\n"
            f"{paper_alpha_opp_bucket_lines}\n\n"
            f"### Paper alpha early_tail_score_bucket results\n"
            f"{paper_alpha_ets_bucket_lines}\n\n"
            f"### Paper alpha cluster_leader_vs_follower results\n"
            f"{paper_alpha_cluster_lines}\n\n"
            f"## Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort "
            f"Evidence Pack v0\n"
            f"_Regime & Cluster Cohort Evidence Pack v0 sub-blocks "
            f"are paper / report / evidence-only. The "
            f"`regime_cluster_evidence_status` is a **descriptive** "
            f"label (one of `INSUFFICIENT_SAMPLE` / `OBSERVE_ONLY` "
            f"/ `WARNING` / `EVIDENCE_SIGNAL`) and **MUST NEVER "
            f"trigger a real trade**, and **MUST NEVER** modify "
            f"position size, leverage, stop-loss, target price, the "
            f"Risk Engine, or the Execution FSM. The Risk Engine "
            f"remains the single trade-decision gate. This is "
            f"**NOT** a new strategy, **NOT** a trading module, "
            f"**NOT** AI Learning, **NOT** automatic parameter "
            f"optimisation, **NOT** reinforcement learning, "
            f"**NOT** the complete Strategy Validation Lab "
            f"follow-up; Phase 12 remains FORBIDDEN._\n\n"
            f"{regime_cluster_block}\n"
            f"### Regime / cluster insufficient sample reasons\n"
            f"{regime_cluster_insufficient_lines}\n\n"
            f"### Regime / cluster warnings\n"
            f"{regime_cluster_warning_lines}\n\n"
            f"### Regime / cluster signals\n"
            f"{regime_cluster_signal_lines}\n\n"
            f"### Regime cohort summary (per market_regime)\n"
            f"{regime_cluster_regime_lines}\n\n"
            f"### Cluster cohort summary (per cluster_id)\n"
            f"{regime_cluster_cluster_lines}\n\n"
            f"### Cluster leader-vs-follower cohort summary\n"
            f"{regime_cluster_leader_follower_lines}\n\n"
            f"### Score bucket summary (opportunity_score buckets)\n"
            f"{regime_cluster_opp_bucket_lines}\n\n"
            f"### Score bucket summary (early_tail_score buckets)\n"
            f"{regime_cluster_ets_bucket_lines}\n\n"
            f"### Stage outcome summary (per candidate_stage)\n"
            f"{regime_cluster_stage_lines}\n\n"
            f"### Strategy mode outcome summary (per strategy_mode)\n"
            f"{regime_cluster_mode_lines}\n\n"
            f"## Top risk-rejection reasons\n{top_reject}\n\n"
            f"## Top symbols by event volume\n{top_symbols}\n\n"
            f"## Error notes\n{error_notes}\n\n"
            f"## Degraded notes\n{degraded_notes}\n\n"
            f"---\n"
            f"_Phase 11B paper-mode cloud run. No live trading. "
            f"No real exchange order. No credential is read by this "
            f"report._\n"
        )
        return body


def _replace_markdown(
    snapshot: DailyReportSnapshot, markdown: str
) -> DailyReportSnapshot:
    """Return a copy of ``snapshot`` with ``markdown`` swapped in.

    :class:`DailyReportSnapshot` is frozen so we use ``dataclasses.replace``.
    """
    from dataclasses import replace

    return replace(snapshot, markdown=markdown)


__all__ = [
    "DailyReportBuilder",
    "DailyReportSnapshot",
]
