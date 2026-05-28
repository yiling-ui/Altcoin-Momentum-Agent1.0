"""Phase 11C.1C-C-B-B-B-E-A - Replay Extension for 11C Adaptive Events v0.

Read-only replay over the Phase 11C adaptive / discovery / evidence
event chain. The extension reconstructs the descriptive event groups
emitted by Block A and Block B (LABEL_*, TAIL_LABEL_*, MISSED_TAIL_*,
FAKE_BREAKOUT_*, STRATEGY_VALIDATION_*, PAPER_ALPHA_*,
REGIME_CLUSTER_*, MOVER_CAPTURE_*, HISTORICAL_MOVER_COVERAGE_*,
POST_DISCOVERY_OUTCOME_*, REJECT_TO_OUTCOME_*, SEVERE_MISSED_TAIL_*,
DISCOVERY_QUALITY_*) into deterministic value objects suitable for:

  * Reflection input (Phase 11C.1C-C-B-B-B-E-B; out of scope here)
  * Export bundles
  * Operator audit
  * Block C unit / property tests

Phase 11C.1C-C-B-B-B-E-A boundary
---------------------------------

The extension is **fundamentally** read-only:

  - opens NO socket
  - imports NO exchange SDK / HTTP / WebSocket / LLM client / Telegram
    bot library / Risk Engine / Execution FSM / DeepSeek
  - reads NO ``os.environ``
  - defines NO order-creation / order-cancellation / leverage-mutation
    / margin-mode-mutation / position-mutation / runtime-config-patch
    function
  - mutates NO event row, NO trading state, NO capital state, NO risk
    state, NO runtime parameter
  - is therefore SAFE to run against any production-grade events.db

This extension is paper-only / report-only / replay-only. It MUST
NEVER:

  - produce ``buy`` / ``sell`` / ``long`` / ``short`` / ``direction``
  - produce ``position_size`` / ``leverage`` / ``stop`` / ``stop_loss``
    / ``target`` / ``take_profit`` / ``risk_budget``
  - produce ``runtime_config_patch`` / ``symbol_limit_patch`` /
    ``threshold_patch`` / ``candidate_pool_patch`` /
    ``regime_weight_patch``
  - authorise live trading or auto-tuning
  - trigger Phase 12

Successful Phase 11C.1C-C-B-B-B-E-A acceptance only allows the next
phase (Phase 11C.1C-C-B-B-B-E-B Reflection Extension for 11C Adaptive
Events v0) to start; it does NOT close out cloud evidence and does NOT
authorise live trading.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.core.events import Event, EventType
from app.database.repositories import EventRepository


SOURCE_PHASE: str = "phase_11c_1c_c_b_b_b_e_a"
SOURCE_MODULE: str = "replay_11c_adaptive_extension"
SCHEMA_VERSION: str = "v0"


# ---------------------------------------------------------------------------
# Forbidden payload-key vocabulary (defensive)
# ---------------------------------------------------------------------------
# Every replay value object's ``to_payload()`` is checked at construction
# time against this set. The set codifies the brief's "no trade
# decisions, no runtime patches" boundary; it is paranoid-by-design so
# a future regression cannot silently smuggle a forbidden key into a
# replay output.
FORBIDDEN_REPLAY_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        # Direction / trade-decision keys
        "buy",
        "sell",
        "long",
        "short",
        "direction",
        "side",
        "entry",
        "exit",
        # Sizing / leverage / risk-budget keys
        "position_size",
        "leverage",
        "stop",
        "stop_loss",
        "target",
        "take_profit",
        "risk_budget",
        "order",
        "execution_command",
        # Runtime-config patch keys
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
    }
)


# ---------------------------------------------------------------------------
# Event-group vocabulary
# ---------------------------------------------------------------------------
# Each tuple lists the event types Phase 11C.1C-C-B-B-B-E-A consumes
# for that replay object. They are deliberately read-only references
# to :class:`EventType` members; nothing here registers a new type.

DISCOVERY_TIMELINE_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.MARKET_REGIME_ASSESSED,
    EventType.CANDIDATE_STAGE_CLASSIFIED,
    EventType.OPPORTUNITY_SCORED,
    EventType.STRATEGY_MODE_SELECTED,
    EventType.CLUSTER_CONTEXT_ATTACHED,
    EventType.LABEL_QUEUE_ENQUEUED,
)

CANDIDATE_LIFECYCLE_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.LABEL_TRACKING_STARTED,
    EventType.LABEL_WINDOW_UPDATED,
    EventType.LABEL_WINDOW_COMPLETED,
)

TAIL_OUTCOME_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.TAIL_LABEL_ASSIGNED,
    EventType.MISSED_TAIL_DETECTED,
    EventType.FAKE_BREAKOUT_DETECTED,
)

MOVER_COVERAGE_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.MOVER_CAPTURE_PATH_AUDITED,
    EventType.MOVER_CAPTURE_RECALL_AUDIT_GENERATED,
    EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
    EventType.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED,
)

POST_DISCOVERY_OUTCOME_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
    EventType.POST_DISCOVERY_OUTCOME_REPORT_GENERATED,
)

REJECT_ATTRIBUTION_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
    EventType.REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED,
    EventType.FALSE_NEGATIVE_REJECT_DETECTED,
    EventType.CORRECT_PROTECTIVE_REJECT_CONFIRMED,
)

SEVERE_MISS_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED,
    EventType.SEVERE_MISSED_TAIL_TRIAGE_GENERATED,
    EventType.SEVERE_MISS_ESCALATION_REQUIRED,
)

DISCOVERY_QUALITY_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.DISCOVERY_QUALITY_BUCKET_EVALUATED,
    EventType.DISCOVERY_QUALITY_SCORECARD_GENERATED,
)

STRATEGY_VALIDATION_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.STRATEGY_VALIDATION_SAMPLE_CREATED,
    EventType.STRATEGY_VALIDATION_REPORT_GENERATED,
    EventType.STRATEGY_MODE_VALIDATED,
    EventType.CANDIDATE_STAGE_VALIDATED,
    EventType.SCORE_BUCKET_VALIDATED,
    EventType.CLUSTER_EXPOSURE_ASSESSED,
    EventType.CLUSTER_LEADER_VALIDATED,
    EventType.STRATEGY_VALIDATION_DATASET_BUILT,
    EventType.STRATEGY_VALIDATION_DATASET_EXPORTED,
    EventType.STRATEGY_VALIDATION_QUALITY_GATE_EVALUATED,
)

PAPER_ALPHA_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.PAPER_ALPHA_GATE_EVALUATED,
    EventType.PAPER_ALPHA_RULE_EVALUATED,
    EventType.PAPER_ALPHA_COHORT_EVALUATED,
    EventType.PAPER_ALPHA_REPORT_GENERATED,
)

REGIME_CLUSTER_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.REGIME_CLUSTER_EVIDENCE_PACK_GENERATED,
    EventType.REGIME_CLUSTER_COHORT_SUMMARY_GENERATED,
)


# Union of every adaptive event type the extension knows how to read.
ADAPTIVE_REPLAY_EVENT_TYPES: tuple[EventType, ...] = tuple(
    dict.fromkeys(  # de-duplicate while preserving order
        DISCOVERY_TIMELINE_EVENT_TYPES
        + CANDIDATE_LIFECYCLE_EVENT_TYPES
        + TAIL_OUTCOME_EVENT_TYPES
        + MOVER_COVERAGE_EVENT_TYPES
        + POST_DISCOVERY_OUTCOME_EVENT_TYPES
        + REJECT_ATTRIBUTION_EVENT_TYPES
        + SEVERE_MISS_EVENT_TYPES
        + DISCOVERY_QUALITY_EVENT_TYPES
        + STRATEGY_VALIDATION_EVENT_TYPES
        + PAPER_ALPHA_EVENT_TYPES
        + REGIME_CLUSTER_EVENT_TYPES
    )
)


# ---------------------------------------------------------------------------
# Replay status vocabulary
# ---------------------------------------------------------------------------
class ReplayStatus:
    """Closed string set for replay-object status flags.

    The replay extension never raises on missing fields; instead it
    flags the result as ``partial`` (some required fields missing
    from payload but core identity is intact) or ``degraded`` (the
    parent / canonical event was not found in the stream).
    """

    OK: str = "ok"
    PARTIAL: str = "partial"
    DEGRADED: str = "degraded"


_VALID_REPLAY_STATUSES: frozenset[str] = frozenset(
    {ReplayStatus.OK, ReplayStatus.PARTIAL, ReplayStatus.DEGRADED}
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _payload(ev: Event) -> dict[str, Any]:
    p = ev.payload
    return p if isinstance(p, dict) else {}


def _maybe_str(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _maybe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _maybe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _maybe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _opportunity_identity(ev: Event) -> tuple[str | None, str | None, str | None]:
    """Best-effort (opportunity_id, scan_batch_id, symbol) extraction.

    Phase 11C.1C-* emits identity at the payload top level; we also
    fall back to the ``Event.symbol`` column.
    """
    payload = _payload(ev)
    opp = _maybe_str(payload.get("opportunity_id"))
    scan = _maybe_str(payload.get("scan_batch_id"))
    sym = _maybe_str(payload.get("symbol")) or ev.symbol
    return opp, scan, sym


def _evidence_refs(ev: Event) -> list[str]:
    payload = _payload(ev)
    refs = payload.get("evidence_refs")
    out: list[str] = []
    if isinstance(refs, list):
        for ref in refs:
            if isinstance(ref, str) and ref:
                out.append(ref)
    return out


def _assert_no_forbidden_keys(payload: dict[str, Any], *, context: str) -> None:
    """Defensive guard: a replay payload must NEVER contain forbidden keys.

    This is invoked from every value object's ``to_payload()`` so a
    regression cannot smuggle a ``buy`` / ``leverage`` /
    ``runtime_config_patch`` / ... key into a replay output. The check
    is shallow (one level of dict keys) - replay objects do not nest
    raw event payloads under known-forbidden keys. The function is
    pure and deterministic.
    """
    for key in payload.keys():
        if key in FORBIDDEN_REPLAY_PAYLOAD_KEYS:
            raise ValueError(
                f"replay extension produced a forbidden payload key "
                f"{key!r} in {context!r}; this is a hard violation of "
                "Phase 11C.1C-C-B-B-B-E-A boundary."
            )


def _sort_events(events: Iterable[Event]) -> list[Event]:
    """Deterministic ordering: (timestamp ASC, event_type, event_id)."""
    return sorted(
        events,
        key=lambda ev: (int(ev.timestamp), ev.event_type.value, ev.event_id),
    )


# ---------------------------------------------------------------------------
# Replay value objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ReplayDiscoveryTimeline:
    """One opportunity's discovery-event chain in the WS-radar driver.

    Reconstructs (in stream order):
        MARKET_REGIME_ASSESSED -> CANDIDATE_STAGE_CLASSIFIED ->
        OPPORTUNITY_SCORED -> STRATEGY_MODE_SELECTED ->
        CLUSTER_CONTEXT_ATTACHED -> LABEL_QUEUE_ENQUEUED

    Missing events do NOT raise; the timeline is flagged ``partial``
    when one or more canonical steps are absent, and ``degraded`` when
    the timeline was synthesised from only one event (no chain).
    """

    opportunity_id: str | None
    scan_batch_id: str | None
    symbol: str | None
    market_regime: str | None
    candidate_stage: str | None
    opportunity_score: float | None
    strategy_mode: str | None
    cluster_id: str | None
    label_queue_window_count: int | None
    chain: tuple[str, ...]
    event_ids: tuple[str, ...]
    first_seen_ts: int | None
    last_seen_ts: int | None
    status: str
    missing_steps: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "source_phase": SOURCE_PHASE,
            "replay_object": "ReplayDiscoveryTimeline",
            "status": self.status,
            "opportunity_id": self.opportunity_id,
            "scan_batch_id": self.scan_batch_id,
            "symbol": self.symbol,
            "market_regime": self.market_regime,
            "candidate_stage": self.candidate_stage,
            "opportunity_score": self.opportunity_score,
            "strategy_mode": self.strategy_mode,
            "cluster_id": self.cluster_id,
            "label_queue_window_count": self.label_queue_window_count,
            "chain": list(self.chain),
            "event_ids": list(self.event_ids),
            "first_seen_ts": self.first_seen_ts,
            "last_seen_ts": self.last_seen_ts,
            "missing_steps": list(self.missing_steps),
        }
        _assert_no_forbidden_keys(
            payload, context="ReplayDiscoveryTimeline.to_payload"
        )
        return payload


@dataclass(frozen=True)
class ReplayCandidateLifecycle:
    """One LabelTrackingRecord lifecycle reconstructed from events.

    Tracks LABEL_TRACKING_STARTED -> LABEL_WINDOW_UPDATED* ->
    LABEL_WINDOW_COMPLETED for one opportunity_id (or symbol /
    tracking_id fall-back).
    """

    opportunity_id: str | None
    scan_batch_id: str | None
    tracking_id: str | None
    symbol: str | None
    started_ts: int | None
    last_update_ts: int | None
    completed_window_names: tuple[str, ...]
    update_count: int
    final_status: str | None  # "pending" / "completed" / None
    final_tail_label: str | None
    event_ids: tuple[str, ...]
    status: str
    missing_steps: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "source_phase": SOURCE_PHASE,
            "replay_object": "ReplayCandidateLifecycle",
            "status": self.status,
            "opportunity_id": self.opportunity_id,
            "scan_batch_id": self.scan_batch_id,
            "tracking_id": self.tracking_id,
            "symbol": self.symbol,
            "started_ts": self.started_ts,
            "last_update_ts": self.last_update_ts,
            "completed_window_names": list(self.completed_window_names),
            "update_count": int(self.update_count),
            "final_status": self.final_status,
            "final_tail_label": self.final_tail_label,
            "event_ids": list(self.event_ids),
            "missing_steps": list(self.missing_steps),
        }
        _assert_no_forbidden_keys(
            payload, context="ReplayCandidateLifecycle.to_payload"
        )
        return payload


@dataclass(frozen=True)
class ReplayTailOutcome:
    """One TAIL_LABEL_ASSIGNED outcome plus optional MISSED / FAKE flags."""

    opportunity_id: str | None
    scan_batch_id: str | None
    symbol: str | None
    window_name: str | None
    tail_label: str | None
    mfe_pct: float | None
    mae_pct: float | None
    missed_tail: bool
    fake_breakout: bool
    candidate_stage: str | None
    strategy_mode: str | None
    tail_event_id: str | None
    missed_event_id: str | None
    fake_breakout_event_id: str | None
    timestamp: int | None
    status: str

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "source_phase": SOURCE_PHASE,
            "replay_object": "ReplayTailOutcome",
            "status": self.status,
            "opportunity_id": self.opportunity_id,
            "scan_batch_id": self.scan_batch_id,
            "symbol": self.symbol,
            "window_name": self.window_name,
            "tail_label": self.tail_label,
            "mfe_pct": self.mfe_pct,
            "mae_pct": self.mae_pct,
            "missed_tail": bool(self.missed_tail),
            "fake_breakout": bool(self.fake_breakout),
            "candidate_stage": self.candidate_stage,
            "strategy_mode": self.strategy_mode,
            "tail_event_id": self.tail_event_id,
            "missed_event_id": self.missed_event_id,
            "fake_breakout_event_id": self.fake_breakout_event_id,
            "timestamp": self.timestamp,
        }
        _assert_no_forbidden_keys(
            payload, context="ReplayTailOutcome.to_payload"
        )
        return payload


@dataclass(frozen=True)
class ReplayMoverCoverageCase:
    """One Mover Capture Path / Historical 60D Coverage case.

    Built from MOVER_CAPTURE_PATH_AUDITED or
    HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED, optionally pinned to its
    parent ``*_GENERATED`` rollup event.
    """

    symbol: str | None
    audit_status: str | None
    miss_reasons: tuple[str, ...]
    rank: int | None
    capture_recall_score: float | None
    in_eligible_universe: bool | None
    risk_rejected: bool | None
    has_completed_tail_label: bool | None
    has_strategy_validation_sample: bool | None
    first_seen_latency_seconds: float | None
    record_event_id: str
    record_event_type: str
    parent_event_id: str | None
    parent_event_type: str | None
    timestamp: int | None
    evidence_refs: tuple[str, ...]
    status: str

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "source_phase": SOURCE_PHASE,
            "replay_object": "ReplayMoverCoverageCase",
            "status": self.status,
            "symbol": self.symbol,
            "audit_status": self.audit_status,
            "miss_reasons": list(self.miss_reasons),
            "rank": self.rank,
            "capture_recall_score": self.capture_recall_score,
            "in_eligible_universe": self.in_eligible_universe,
            "risk_rejected": self.risk_rejected,
            "has_completed_tail_label": self.has_completed_tail_label,
            "has_strategy_validation_sample": self.has_strategy_validation_sample,
            "first_seen_latency_seconds": self.first_seen_latency_seconds,
            "record_event_id": self.record_event_id,
            "record_event_type": self.record_event_type,
            "parent_event_id": self.parent_event_id,
            "parent_event_type": self.parent_event_type,
            "timestamp": self.timestamp,
            "evidence_refs": list(self.evidence_refs),
        }
        _assert_no_forbidden_keys(
            payload, context="ReplayMoverCoverageCase.to_payload"
        )
        return payload


@dataclass(frozen=True)
class ReplayPostDiscoveryOutcomeCase:
    """One POST_DISCOVERY_OUTCOME_EVALUATED record reconstructed."""

    symbol: str | None
    detection_timing_label: str | None
    outcome_label: str | None
    remaining_upside_to_peak_pct: float | None
    post_seen_drawdown_pct: float | None
    mfe_pct: float | None
    mae_pct: float | None
    time_to_peak_seconds: float | None
    distance_to_prior_high_pct: float | None
    reference_window: str | None
    record_event_id: str
    parent_event_id: str | None
    timestamp: int | None
    evidence_refs: tuple[str, ...]
    status: str

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "source_phase": SOURCE_PHASE,
            "replay_object": "ReplayPostDiscoveryOutcomeCase",
            "status": self.status,
            "symbol": self.symbol,
            "detection_timing_label": self.detection_timing_label,
            "outcome_label": self.outcome_label,
            "remaining_upside_to_peak_pct": self.remaining_upside_to_peak_pct,
            "post_seen_drawdown_pct": self.post_seen_drawdown_pct,
            "mfe_pct": self.mfe_pct,
            "mae_pct": self.mae_pct,
            "time_to_peak_seconds": self.time_to_peak_seconds,
            "distance_to_prior_high_pct": self.distance_to_prior_high_pct,
            "reference_window": self.reference_window,
            "record_event_id": self.record_event_id,
            "parent_event_id": self.parent_event_id,
            "timestamp": self.timestamp,
            "evidence_refs": list(self.evidence_refs),
        }
        _assert_no_forbidden_keys(
            payload,
            context="ReplayPostDiscoveryOutcomeCase.to_payload",
        )
        return payload


@dataclass(frozen=True)
class ReplayRejectAttributionCase:
    """One REJECT_TO_OUTCOME_CASE_ATTRIBUTED record reconstructed.

    The verdict / reasons are descriptive labels - they MUST NEVER be
    used as a trade-decision input.
    """

    symbol: str | None
    opportunity_id: str | None
    verdict: str | None
    primary_reason: str | None
    secondary_reasons: tuple[str, ...]
    is_false_negative: bool
    is_correct_protective: bool
    record_event_id: str
    parent_event_id: str | None
    false_negative_event_id: str | None
    correct_protective_event_id: str | None
    timestamp: int | None
    evidence_refs: tuple[str, ...]
    auto_tuning_allowed: bool
    status: str

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "source_phase": SOURCE_PHASE,
            "replay_object": "ReplayRejectAttributionCase",
            "status": self.status,
            "symbol": self.symbol,
            "opportunity_id": self.opportunity_id,
            "verdict": self.verdict,
            "primary_reason": self.primary_reason,
            "secondary_reasons": list(self.secondary_reasons),
            "is_false_negative": bool(self.is_false_negative),
            "is_correct_protective": bool(self.is_correct_protective),
            "record_event_id": self.record_event_id,
            "parent_event_id": self.parent_event_id,
            "false_negative_event_id": self.false_negative_event_id,
            "correct_protective_event_id": self.correct_protective_event_id,
            "timestamp": self.timestamp,
            "evidence_refs": list(self.evidence_refs),
            "auto_tuning_allowed": bool(self.auto_tuning_allowed),
        }
        _assert_no_forbidden_keys(
            payload, context="ReplayRejectAttributionCase.to_payload"
        )
        return payload


@dataclass(frozen=True)
class ReplaySevereMissCase:
    """One SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED record."""

    symbol: str | None
    opportunity_id: str | None
    root_cause: str | None
    severity: str | None
    requires_escalation: bool
    record_event_id: str
    parent_event_id: str | None
    escalation_event_id: str | None
    timestamp: int | None
    evidence_refs: tuple[str, ...]
    auto_tuning_allowed: bool
    status: str

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "source_phase": SOURCE_PHASE,
            "replay_object": "ReplaySevereMissCase",
            "status": self.status,
            "symbol": self.symbol,
            "opportunity_id": self.opportunity_id,
            "root_cause": self.root_cause,
            "severity": self.severity,
            "requires_escalation": bool(self.requires_escalation),
            "record_event_id": self.record_event_id,
            "parent_event_id": self.parent_event_id,
            "escalation_event_id": self.escalation_event_id,
            "timestamp": self.timestamp,
            "evidence_refs": list(self.evidence_refs),
            "auto_tuning_allowed": bool(self.auto_tuning_allowed),
        }
        _assert_no_forbidden_keys(
            payload, context="ReplaySevereMissCase.to_payload"
        )
        return payload


@dataclass(frozen=True)
class ReplayDiscoveryQualityCase:
    """One DISCOVERY_QUALITY_BUCKET_EVALUATED / SCORECARD_GENERATED case."""

    quality_bucket: str | None
    capture_recall_rate: float | None
    early_continuation_rate: float | None
    severe_miss_rate: float | None
    false_negative_reject_rate: float | None
    bucket_event_id: str | None
    scorecard_event_id: str | None
    parent_event_id: str | None
    timestamp: int | None
    evidence_refs: tuple[str, ...]
    auto_tuning_allowed: bool
    status: str

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "source_phase": SOURCE_PHASE,
            "replay_object": "ReplayDiscoveryQualityCase",
            "status": self.status,
            "quality_bucket": self.quality_bucket,
            "capture_recall_rate": self.capture_recall_rate,
            "early_continuation_rate": self.early_continuation_rate,
            "severe_miss_rate": self.severe_miss_rate,
            "false_negative_reject_rate": self.false_negative_reject_rate,
            "bucket_event_id": self.bucket_event_id,
            "scorecard_event_id": self.scorecard_event_id,
            "parent_event_id": self.parent_event_id,
            "timestamp": self.timestamp,
            "evidence_refs": list(self.evidence_refs),
            "auto_tuning_allowed": bool(self.auto_tuning_allowed),
        }
        _assert_no_forbidden_keys(
            payload, context="ReplayDiscoveryQualityCase.to_payload"
        )
        return payload


@dataclass(frozen=True)
class AdaptiveReplayBundle:
    """Aggregate result of :meth:`AdaptiveEventReplayExtension.replay_all`.

    Carries one list per replay object plus a bookkeeping
    ``input_event_count`` / ``replay_count`` pair so callers can
    enforce the "replay count == input event count for the supported
    groups" invariant required by the Phase 11C.1C-C-B-B-B-E-A
    acceptance criteria.
    """

    discovery_timelines: tuple[ReplayDiscoveryTimeline, ...]
    candidate_lifecycles: tuple[ReplayCandidateLifecycle, ...]
    tail_outcomes: tuple[ReplayTailOutcome, ...]
    mover_coverage_cases: tuple[ReplayMoverCoverageCase, ...]
    post_discovery_outcome_cases: tuple[ReplayPostDiscoveryOutcomeCase, ...]
    reject_attribution_cases: tuple[ReplayRejectAttributionCase, ...]
    severe_miss_cases: tuple[ReplaySevereMissCase, ...]
    discovery_quality_cases: tuple[ReplayDiscoveryQualityCase, ...]
    input_event_count: int
    replay_record_event_count: int
    skipped_event_count: int

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "source_phase": SOURCE_PHASE,
            "replay_object": "AdaptiveReplayBundle",
            "input_event_count": int(self.input_event_count),
            "replay_record_event_count": int(self.replay_record_event_count),
            "skipped_event_count": int(self.skipped_event_count),
            "discovery_timeline_count": len(self.discovery_timelines),
            "candidate_lifecycle_count": len(self.candidate_lifecycles),
            "tail_outcome_count": len(self.tail_outcomes),
            "mover_coverage_case_count": len(self.mover_coverage_cases),
            "post_discovery_outcome_case_count": len(
                self.post_discovery_outcome_cases
            ),
            "reject_attribution_case_count": len(
                self.reject_attribution_cases
            ),
            "severe_miss_case_count": len(self.severe_miss_cases),
            "discovery_quality_case_count": len(
                self.discovery_quality_cases
            ),
            "discovery_timelines": [
                t.to_payload() for t in self.discovery_timelines
            ],
            "candidate_lifecycles": [
                c.to_payload() for c in self.candidate_lifecycles
            ],
            "tail_outcomes": [t.to_payload() for t in self.tail_outcomes],
            "mover_coverage_cases": [
                m.to_payload() for m in self.mover_coverage_cases
            ],
            "post_discovery_outcome_cases": [
                p.to_payload() for p in self.post_discovery_outcome_cases
            ],
            "reject_attribution_cases": [
                r.to_payload() for r in self.reject_attribution_cases
            ],
            "severe_miss_cases": [
                s.to_payload() for s in self.severe_miss_cases
            ],
            "discovery_quality_cases": [
                d.to_payload() for d in self.discovery_quality_cases
            ],
        }
        _assert_no_forbidden_keys(
            payload, context="AdaptiveReplayBundle.to_payload"
        )
        return payload


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------
def load_adaptive_events(
    event_repo: EventRepository,
    *,
    since_ts: int | None = None,
    until_ts: int | None = None,
    symbol: str | None = None,
) -> list[Event]:
    """Read every Phase 11C adaptive event in the window.

    The loader is read-only - it never appends, mutates, or reorders
    rows in events.db.
    """
    events = event_repo.list_events(
        event_types=ADAPTIVE_REPLAY_EVENT_TYPES,
        since_ts=since_ts,
        until_ts=until_ts,
        symbol=symbol,
    )
    return _sort_events(events)


# ---------------------------------------------------------------------------
# Builders (pure functions over an event sequence)
# ---------------------------------------------------------------------------
def _identity_key(ev: Event) -> tuple[str, str, str]:
    """Group key for opportunity-scoped replay objects.

    The key is ``(opportunity_id_or_blank, symbol_or_blank,
    scan_batch_or_blank)`` so events that share an opportunity_id are
    grouped together; events with no opportunity_id fall back to the
    (symbol, scan_batch) tuple. Three-tuple of strings keeps the
    dictionary keys hashable and JSON-safe.
    """
    opp, scan, sym = _opportunity_identity(ev)
    return (opp or "", sym or "", scan or "")


def build_discovery_timelines(
    events: Sequence[Event],
) -> list[ReplayDiscoveryTimeline]:
    """Group adaptive discovery events into per-opportunity timelines."""
    expected_steps = tuple(
        et.value for et in DISCOVERY_TIMELINE_EVENT_TYPES
    )
    groups: dict[tuple[str, str, str], list[Event]] = {}
    for ev in events:
        if ev.event_type not in DISCOVERY_TIMELINE_EVENT_TYPES:
            continue
        key = _identity_key(ev)
        groups.setdefault(key, []).append(ev)
    out: list[ReplayDiscoveryTimeline] = []
    for key in sorted(groups.keys()):
        chain_events = _sort_events(groups[key])
        regime = stage = strategy_mode = cluster_id = None
        score: float | None = None
        label_window_count: int | None = None
        for ev in chain_events:
            payload = _payload(ev)
            if ev.event_type is EventType.MARKET_REGIME_ASSESSED:
                regime = _maybe_str(payload.get("market_regime")) or _maybe_str(
                    payload.get("regime")
                )
            elif ev.event_type is EventType.CANDIDATE_STAGE_CLASSIFIED:
                stage = _maybe_str(payload.get("candidate_stage")) or _maybe_str(
                    payload.get("stage")
                )
            elif ev.event_type is EventType.OPPORTUNITY_SCORED:
                score = _maybe_float(
                    payload.get("opportunity_score")
                ) or _maybe_float(payload.get("score"))
            elif ev.event_type is EventType.STRATEGY_MODE_SELECTED:
                strategy_mode = _maybe_str(payload.get("strategy_mode"))
            elif ev.event_type is EventType.CLUSTER_CONTEXT_ATTACHED:
                cluster_id = _maybe_str(payload.get("cluster_id"))
            elif ev.event_type is EventType.LABEL_QUEUE_ENQUEUED:
                windows = _maybe_list(payload.get("tracking_windows"))
                if windows:
                    label_window_count = len(windows)
                else:
                    label_window_count = _maybe_int(
                        payload.get("tracking_window_count")
                    )
        chain = tuple(ev.event_type.value for ev in chain_events)
        observed_set = set(chain)
        missing = tuple(
            step for step in expected_steps if step not in observed_set
        )
        if not missing:
            status = ReplayStatus.OK
        elif len(chain) <= 1:
            status = ReplayStatus.DEGRADED
        else:
            status = ReplayStatus.PARTIAL
        first_ev = chain_events[0]
        last_ev = chain_events[-1]
        opp = key[0] or None
        sym = key[1] or None
        scan = key[2] or None
        out.append(
            ReplayDiscoveryTimeline(
                opportunity_id=opp,
                scan_batch_id=scan,
                symbol=sym,
                market_regime=regime,
                candidate_stage=stage,
                opportunity_score=score,
                strategy_mode=strategy_mode,
                cluster_id=cluster_id,
                label_queue_window_count=label_window_count,
                chain=chain,
                event_ids=tuple(ev.event_id for ev in chain_events),
                first_seen_ts=int(first_ev.timestamp),
                last_seen_ts=int(last_ev.timestamp),
                status=status,
                missing_steps=missing,
            )
        )
    return out


def build_candidate_lifecycles(
    events: Sequence[Event],
) -> list[ReplayCandidateLifecycle]:
    groups: dict[tuple[str, str, str], list[Event]] = {}
    for ev in events:
        if ev.event_type not in CANDIDATE_LIFECYCLE_EVENT_TYPES:
            continue
        key = _identity_key(ev)
        groups.setdefault(key, []).append(ev)
    out: list[ReplayCandidateLifecycle] = []
    for key in sorted(groups.keys()):
        chain_events = _sort_events(groups[key])
        started_ev = next(
            (
                ev
                for ev in chain_events
                if ev.event_type is EventType.LABEL_TRACKING_STARTED
            ),
            None,
        )
        update_events = [
            ev
            for ev in chain_events
            if ev.event_type is EventType.LABEL_WINDOW_UPDATED
        ]
        completed_events = [
            ev
            for ev in chain_events
            if ev.event_type is EventType.LABEL_WINDOW_COMPLETED
        ]
        tracking_id: str | None = None
        final_status: str | None = None
        final_tail_label: str | None = None
        if started_ev is not None:
            payload = _payload(started_ev)
            tracking_id = _maybe_str(payload.get("tracking_id"))
            record = payload.get("label_tracking_record")
            if isinstance(record, dict):
                final_status = _maybe_str(record.get("status"))
                final_tail_label = _maybe_str(record.get("final_tail_label"))
                if tracking_id is None:
                    tracking_id = _maybe_str(record.get("tracking_id"))
        completed_window_names: list[str] = []
        for ev in completed_events:
            window = _payload(ev).get("window")
            if isinstance(window, dict):
                name = _maybe_str(window.get("window_name"))
                if name:
                    completed_window_names.append(name)
        opp = key[0] or None
        sym = key[1] or None
        scan = key[2] or None
        missing: list[str] = []
        if started_ev is None:
            missing.append(EventType.LABEL_TRACKING_STARTED.value)
        if not completed_events:
            missing.append(EventType.LABEL_WINDOW_COMPLETED.value)
        # Status:
        #   ok       - START + at least one COMPLETED (lifecycle reached
        #              completion at least once)
        #   partial  - START present but no COMPLETED (still pending)
        #   degraded - START missing entirely (only updates / completes
        #              were seen)
        if started_ev is not None and completed_events:
            status = ReplayStatus.OK
        elif started_ev is not None:
            status = ReplayStatus.PARTIAL
        else:
            status = ReplayStatus.DEGRADED
        first_ts = int(chain_events[0].timestamp) if chain_events else None
        last_ts = int(chain_events[-1].timestamp) if chain_events else None
        out.append(
            ReplayCandidateLifecycle(
                opportunity_id=opp,
                scan_batch_id=scan,
                tracking_id=tracking_id,
                symbol=sym,
                started_ts=first_ts,
                last_update_ts=last_ts,
                completed_window_names=tuple(completed_window_names),
                update_count=len(update_events),
                final_status=final_status,
                final_tail_label=final_tail_label,
                event_ids=tuple(ev.event_id for ev in chain_events),
                status=status,
                missing_steps=tuple(missing),
            )
        )
    return out


def _per_window_key(ev: Event) -> tuple[str, str, str, str]:
    """Group by (opportunity_id, symbol, scan_batch, window_name).

    A single opportunity may produce multiple TAIL_LABEL_ASSIGNED
    events - one per window - so we group on window_name rather than
    just opportunity_id.
    """
    opp, scan, sym = _opportunity_identity(ev)
    payload = _payload(ev)
    window_name = _maybe_str(payload.get("window_name")) or ""
    return (opp or "", sym or "", scan or "", window_name)


def build_tail_outcomes(
    events: Sequence[Event],
) -> list[ReplayTailOutcome]:
    groups: dict[tuple[str, str, str, str], list[Event]] = {}
    for ev in events:
        if ev.event_type not in TAIL_OUTCOME_EVENT_TYPES:
            continue
        key = _per_window_key(ev)
        groups.setdefault(key, []).append(ev)
    out: list[ReplayTailOutcome] = []
    for key in sorted(groups.keys()):
        chain_events = _sort_events(groups[key])
        tail_ev = next(
            (
                ev
                for ev in chain_events
                if ev.event_type is EventType.TAIL_LABEL_ASSIGNED
            ),
            None,
        )
        missed_ev = next(
            (
                ev
                for ev in chain_events
                if ev.event_type is EventType.MISSED_TAIL_DETECTED
            ),
            None,
        )
        fake_ev = next(
            (
                ev
                for ev in chain_events
                if ev.event_type is EventType.FAKE_BREAKOUT_DETECTED
            ),
            None,
        )
        # Pick a reference event for top-level metadata. Prefer
        # TAIL_LABEL_ASSIGNED (the canonical outcome); fall back to
        # whichever flag event we have.
        reference = tail_ev or missed_ev or fake_ev
        if reference is None:  # pragma: no cover - defensive
            continue
        payload = _payload(reference)
        opp, scan, sym = _opportunity_identity(reference)
        window_name = _maybe_str(payload.get("window_name")) or (
            key[3] or None
        )
        tail_label = _maybe_str(payload.get("tail_label"))
        mfe = _maybe_float(payload.get("mfe_pct"))
        mae = _maybe_float(payload.get("mae_pct"))
        candidate_stage = _maybe_str(payload.get("candidate_stage"))
        strategy_mode = _maybe_str(payload.get("strategy_mode"))
        missed_tail_flag = bool(payload.get("missed_tail")) or (
            missed_ev is not None
        )
        fake_breakout_flag = bool(payload.get("fake_breakout")) or (
            fake_ev is not None
        )
        if tail_ev is not None and tail_label and window_name:
            status = ReplayStatus.OK
        elif tail_ev is not None:
            status = ReplayStatus.PARTIAL
        else:
            status = ReplayStatus.DEGRADED
        out.append(
            ReplayTailOutcome(
                opportunity_id=opp,
                scan_batch_id=scan,
                symbol=sym,
                window_name=window_name,
                tail_label=tail_label,
                mfe_pct=mfe,
                mae_pct=mae,
                missed_tail=missed_tail_flag,
                fake_breakout=fake_breakout_flag,
                candidate_stage=candidate_stage,
                strategy_mode=strategy_mode,
                tail_event_id=(tail_ev.event_id if tail_ev else None),
                missed_event_id=(missed_ev.event_id if missed_ev else None),
                fake_breakout_event_id=(
                    fake_ev.event_id if fake_ev else None
                ),
                timestamp=int(reference.timestamp),
                status=status,
            )
        )
    return out


def _find_parent(
    events: Sequence[Event],
    *,
    parent_types: Iterable[EventType],
    after_ts: int,
) -> Event | None:
    """Pick the first parent event whose timestamp >= ``after_ts``."""
    parents = [ev for ev in events if ev.event_type in tuple(parent_types)]
    parents.sort(key=lambda ev: (int(ev.timestamp), ev.event_id))
    for ev in parents:
        if int(ev.timestamp) >= after_ts:
            return ev
    # Fall back to the most-recent parent before the record so a
    # late-emitted record still gets pinned to its rollup.
    if parents:
        return parents[-1]
    return None


def build_mover_coverage_cases(
    events: Sequence[Event],
) -> list[ReplayMoverCoverageCase]:
    out: list[ReplayMoverCoverageCase] = []
    record_types = {
        EventType.MOVER_CAPTURE_PATH_AUDITED,
        EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
    }
    parent_types_for: dict[EventType, tuple[EventType, ...]] = {
        EventType.MOVER_CAPTURE_PATH_AUDITED: (
            EventType.MOVER_CAPTURE_RECALL_AUDIT_GENERATED,
        ),
        EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED: (
            EventType.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED,
        ),
    }
    for ev in _sort_events(events):
        if ev.event_type not in record_types:
            continue
        payload = _payload(ev)
        symbol = _maybe_str(payload.get("symbol")) or ev.symbol
        # The two record event types share the audit_status / miss
        # reason vocabulary - we read both into a unified shape.
        audit_status = _maybe_str(payload.get("audit_status")) or _maybe_str(
            payload.get("coverage_status")
        )
        miss_reasons_raw = payload.get("miss_reasons")
        miss_reasons: list[str] = []
        if isinstance(miss_reasons_raw, list):
            for r in miss_reasons_raw:
                if isinstance(r, str) and r:
                    miss_reasons.append(r)
        else:
            single = _maybe_str(payload.get("miss_reason"))
            if single:
                miss_reasons.append(single)
        rank = _maybe_int(payload.get("rank"))
        capture_recall_score = _maybe_float(
            payload.get("capture_recall_score")
        )
        in_eligible_universe = payload.get("in_eligible_universe")
        in_eligible_universe = (
            bool(in_eligible_universe)
            if isinstance(in_eligible_universe, bool)
            else None
        )
        risk_rejected = payload.get("risk_rejected")
        risk_rejected = (
            bool(risk_rejected)
            if isinstance(risk_rejected, bool)
            else None
        )
        has_completed_tail_label = payload.get("has_completed_tail_label")
        has_completed_tail_label = (
            bool(has_completed_tail_label)
            if isinstance(has_completed_tail_label, bool)
            else None
        )
        has_strategy_validation_sample = payload.get(
            "has_strategy_validation_sample"
        )
        has_strategy_validation_sample = (
            bool(has_strategy_validation_sample)
            if isinstance(has_strategy_validation_sample, bool)
            else None
        )
        first_seen_latency = _maybe_float(
            payload.get("first_seen_latency_seconds")
        )
        # Parent rollup
        parent_event = _find_parent(
            events,
            parent_types=parent_types_for[ev.event_type],
            after_ts=int(ev.timestamp),
        )
        evidence_refs = _evidence_refs(ev)
        # Status:
        #   ok       - audit_status and symbol present, and parent rollup
        #              is also in the stream
        #   partial  - audit_status missing or no symbol but record is
        #              still useful
        #   degraded - parent rollup is absent
        if audit_status is None or symbol is None:
            status = ReplayStatus.PARTIAL
        elif parent_event is None:
            status = ReplayStatus.DEGRADED
        else:
            status = ReplayStatus.OK
        out.append(
            ReplayMoverCoverageCase(
                symbol=symbol,
                audit_status=audit_status,
                miss_reasons=tuple(miss_reasons),
                rank=rank,
                capture_recall_score=capture_recall_score,
                in_eligible_universe=in_eligible_universe,
                risk_rejected=risk_rejected,
                has_completed_tail_label=has_completed_tail_label,
                has_strategy_validation_sample=has_strategy_validation_sample,
                first_seen_latency_seconds=first_seen_latency,
                record_event_id=ev.event_id,
                record_event_type=ev.event_type.value,
                parent_event_id=(
                    parent_event.event_id if parent_event else None
                ),
                parent_event_type=(
                    parent_event.event_type.value if parent_event else None
                ),
                timestamp=int(ev.timestamp),
                evidence_refs=tuple(evidence_refs),
                status=status,
            )
        )
    return out


def build_post_discovery_outcome_cases(
    events: Sequence[Event],
) -> list[ReplayPostDiscoveryOutcomeCase]:
    out: list[ReplayPostDiscoveryOutcomeCase] = []
    for ev in _sort_events(events):
        if ev.event_type is not EventType.POST_DISCOVERY_OUTCOME_EVALUATED:
            continue
        payload = _payload(ev)
        record = payload.get("record")
        if not isinstance(record, dict):
            record = {}
        symbol = (
            _maybe_str(record.get("symbol"))
            or _maybe_str(payload.get("symbol"))
            or ev.symbol
        )
        detection_timing = _maybe_str(record.get("detection_timing_label"))
        outcome = _maybe_str(record.get("outcome_label"))
        remaining_upside = _maybe_float(
            record.get("remaining_upside_to_peak_pct")
        )
        post_seen_drawdown = _maybe_float(
            record.get("post_seen_drawdown_pct")
        )
        mfe = _maybe_float(record.get("mfe_pct"))
        mae = _maybe_float(record.get("mae_pct"))
        time_to_peak = _maybe_float(record.get("time_to_peak_seconds"))
        distance_to_prior_high = _maybe_float(
            record.get("distance_to_prior_high_pct")
        )
        reference_window = _maybe_str(payload.get("reference_window"))
        parent_event = _find_parent(
            events,
            parent_types=(
                EventType.POST_DISCOVERY_OUTCOME_REPORT_GENERATED,
            ),
            after_ts=int(ev.timestamp),
        )
        evidence_refs = _evidence_refs(ev) or _evidence_refs(
            Event(
                event_type=ev.event_type,
                source_module=ev.source_module,
                payload=record,  # try the nested record too
                timestamp=ev.timestamp,
            )
        )
        if outcome and detection_timing and symbol:
            status = (
                ReplayStatus.OK
                if parent_event is not None
                else ReplayStatus.DEGRADED
            )
        else:
            status = ReplayStatus.PARTIAL
        out.append(
            ReplayPostDiscoveryOutcomeCase(
                symbol=symbol,
                detection_timing_label=detection_timing,
                outcome_label=outcome,
                remaining_upside_to_peak_pct=remaining_upside,
                post_seen_drawdown_pct=post_seen_drawdown,
                mfe_pct=mfe,
                mae_pct=mae,
                time_to_peak_seconds=time_to_peak,
                distance_to_prior_high_pct=distance_to_prior_high,
                reference_window=reference_window,
                record_event_id=ev.event_id,
                parent_event_id=(
                    parent_event.event_id if parent_event else None
                ),
                timestamp=int(ev.timestamp),
                evidence_refs=tuple(evidence_refs),
                status=status,
            )
        )
    return out


def _correlated_event_id(
    events: Sequence[Event],
    *,
    event_type: EventType,
    record_ev: Event,
) -> str | None:
    """Find a sibling event that shares (symbol, opportunity_id, ts)."""
    target_ts = int(record_ev.timestamp)
    target_symbol = record_ev.symbol or _maybe_str(
        _payload(record_ev).get("symbol")
    )
    target_opp = _maybe_str(_payload(record_ev).get("opportunity_id"))
    matches: list[Event] = []
    for ev in events:
        if ev.event_type is not event_type:
            continue
        ev_symbol = ev.symbol or _maybe_str(_payload(ev).get("symbol"))
        ev_opp = _maybe_str(_payload(ev).get("opportunity_id"))
        if target_symbol and ev_symbol and target_symbol != ev_symbol:
            continue
        if target_opp and ev_opp and target_opp != ev_opp:
            continue
        # Loose timestamp window: same scan batch usually fits within
        # a few seconds. Anything within +/- 60s counts.
        if abs(int(ev.timestamp) - target_ts) <= 60_000:
            matches.append(ev)
    if not matches:
        return None
    matches.sort(
        key=lambda ev: (abs(int(ev.timestamp) - target_ts), ev.event_id)
    )
    return matches[0].event_id


def build_reject_attribution_cases(
    events: Sequence[Event],
) -> list[ReplayRejectAttributionCase]:
    out: list[ReplayRejectAttributionCase] = []
    for ev in _sort_events(events):
        if ev.event_type is not EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED:
            continue
        payload = _payload(ev)
        symbol = _maybe_str(payload.get("symbol")) or ev.symbol
        opportunity_id = _maybe_str(payload.get("opportunity_id"))
        verdict = _maybe_str(payload.get("verdict"))
        primary_reason = _maybe_str(
            payload.get("primary_reason")
        ) or _maybe_str(payload.get("primary_reject_reason"))
        secondary_raw = payload.get("secondary_reasons") or payload.get(
            "secondary_reject_reasons"
        )
        secondary: list[str] = []
        if isinstance(secondary_raw, list):
            for r in secondary_raw:
                if isinstance(r, str) and r:
                    secondary.append(r)
        false_negative_id = _correlated_event_id(
            events,
            event_type=EventType.FALSE_NEGATIVE_REJECT_DETECTED,
            record_ev=ev,
        )
        correct_protective_id = _correlated_event_id(
            events,
            event_type=EventType.CORRECT_PROTECTIVE_REJECT_CONFIRMED,
            record_ev=ev,
        )
        parent_event = _find_parent(
            events,
            parent_types=(
                EventType.REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED,
            ),
            after_ts=int(ev.timestamp),
        )
        # Phase 11C.1C-C-B-B-B-D-C-A requires every payload to carry
        # ``auto_tuning_allowed=False``; default to True only if the
        # field is missing from the source event (replay extension does
        # NOT change the source event).
        auto_tuning_allowed = bool(payload.get("auto_tuning_allowed", False))
        evidence_refs = _evidence_refs(ev)
        if verdict and (symbol or opportunity_id):
            status = (
                ReplayStatus.OK
                if parent_event is not None
                else ReplayStatus.DEGRADED
            )
        else:
            status = ReplayStatus.PARTIAL
        out.append(
            ReplayRejectAttributionCase(
                symbol=symbol,
                opportunity_id=opportunity_id,
                verdict=verdict,
                primary_reason=primary_reason,
                secondary_reasons=tuple(secondary),
                is_false_negative=(false_negative_id is not None)
                or (
                    verdict
                    in {
                        "FALSE_NEGATIVE_REJECT",
                        "STRATEGY_MODE_FALSE_NEGATIVE",
                    }
                ),
                is_correct_protective=(correct_protective_id is not None)
                or (verdict == "CORRECT_PROTECTIVE_REJECT"),
                record_event_id=ev.event_id,
                parent_event_id=(
                    parent_event.event_id if parent_event else None
                ),
                false_negative_event_id=false_negative_id,
                correct_protective_event_id=correct_protective_id,
                timestamp=int(ev.timestamp),
                evidence_refs=tuple(evidence_refs),
                auto_tuning_allowed=auto_tuning_allowed,
                status=status,
            )
        )
    return out


def build_severe_miss_cases(
    events: Sequence[Event],
) -> list[ReplaySevereMissCase]:
    out: list[ReplaySevereMissCase] = []
    for ev in _sort_events(events):
        if (
            ev.event_type
            is not EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED
        ):
            continue
        payload = _payload(ev)
        symbol = _maybe_str(payload.get("symbol")) or ev.symbol
        opportunity_id = _maybe_str(payload.get("opportunity_id"))
        root_cause = _maybe_str(payload.get("root_cause"))
        severity = _maybe_str(payload.get("severity"))
        escalation_id = _correlated_event_id(
            events,
            event_type=EventType.SEVERE_MISS_ESCALATION_REQUIRED,
            record_ev=ev,
        )
        parent_event = _find_parent(
            events,
            parent_types=(EventType.SEVERE_MISSED_TAIL_TRIAGE_GENERATED,),
            after_ts=int(ev.timestamp),
        )
        auto_tuning_allowed = bool(payload.get("auto_tuning_allowed", False))
        evidence_refs = _evidence_refs(ev)
        if root_cause and severity:
            status = (
                ReplayStatus.OK
                if parent_event is not None
                else ReplayStatus.DEGRADED
            )
        else:
            status = ReplayStatus.PARTIAL
        out.append(
            ReplaySevereMissCase(
                symbol=symbol,
                opportunity_id=opportunity_id,
                root_cause=root_cause,
                severity=severity,
                requires_escalation=escalation_id is not None
                or (
                    severity in {"SEVERE", "CRITICAL"}
                    if severity
                    else False
                ),
                record_event_id=ev.event_id,
                parent_event_id=(
                    parent_event.event_id if parent_event else None
                ),
                escalation_event_id=escalation_id,
                timestamp=int(ev.timestamp),
                evidence_refs=tuple(evidence_refs),
                auto_tuning_allowed=auto_tuning_allowed,
                status=status,
            )
        )
    return out


def build_discovery_quality_cases(
    events: Sequence[Event],
) -> list[ReplayDiscoveryQualityCase]:
    bucket_events = [
        ev
        for ev in events
        if ev.event_type is EventType.DISCOVERY_QUALITY_BUCKET_EVALUATED
    ]
    scorecard_events = [
        ev
        for ev in events
        if ev.event_type is EventType.DISCOVERY_QUALITY_SCORECARD_GENERATED
    ]
    bucket_events = _sort_events(bucket_events)
    scorecard_events = _sort_events(scorecard_events)
    out: list[ReplayDiscoveryQualityCase] = []
    used_scorecards: set[str] = set()

    def _pick_scorecard(after_ts: int) -> Event | None:
        for s in scorecard_events:
            if s.event_id in used_scorecards:
                continue
            if abs(int(s.timestamp) - after_ts) <= 60_000:
                return s
        # Fallback: nearest in time
        if scorecard_events:
            return min(
                (
                    s
                    for s in scorecard_events
                    if s.event_id not in used_scorecards
                ),
                key=lambda s: abs(int(s.timestamp) - after_ts),
                default=None,
            )
        return None

    if bucket_events:
        for ev in bucket_events:
            payload = _payload(ev)
            quality_bucket = _maybe_str(payload.get("quality_bucket"))
            scorecard = _pick_scorecard(int(ev.timestamp))
            sc_payload = _payload(scorecard) if scorecard else {}
            if scorecard is not None:
                used_scorecards.add(scorecard.event_id)
            evidence_refs = _evidence_refs(ev) or (
                _evidence_refs(scorecard) if scorecard else []
            )
            auto_tuning_allowed = bool(
                payload.get("auto_tuning_allowed", False)
            )
            capture_rate = _maybe_float(sc_payload.get("capture_recall_rate"))
            early_continuation = _maybe_float(
                sc_payload.get("early_continuation_rate")
            )
            severe_miss_rate = _maybe_float(
                sc_payload.get("severe_miss_rate")
            )
            false_neg_rate = _maybe_float(
                sc_payload.get("false_negative_reject_rate")
            )
            if quality_bucket and scorecard is not None:
                status = ReplayStatus.OK
            elif quality_bucket:
                status = ReplayStatus.DEGRADED
            else:
                status = ReplayStatus.PARTIAL
            out.append(
                ReplayDiscoveryQualityCase(
                    quality_bucket=quality_bucket,
                    capture_recall_rate=capture_rate,
                    early_continuation_rate=early_continuation,
                    severe_miss_rate=severe_miss_rate,
                    false_negative_reject_rate=false_neg_rate,
                    bucket_event_id=ev.event_id,
                    scorecard_event_id=(
                        scorecard.event_id if scorecard else None
                    ),
                    parent_event_id=(
                        scorecard.event_id if scorecard else None
                    ),
                    timestamp=int(ev.timestamp),
                    evidence_refs=tuple(evidence_refs),
                    auto_tuning_allowed=auto_tuning_allowed,
                    status=status,
                )
            )
    # Any scorecard rows that did NOT pair with a bucket event are
    # still surfaced as a degraded case so the replay count >= input
    # count for these two event types.
    for sc in scorecard_events:
        if sc.event_id in used_scorecards:
            continue
        sc_payload = _payload(sc)
        quality_bucket = _maybe_str(sc_payload.get("quality_bucket"))
        evidence_refs = _evidence_refs(sc)
        auto_tuning_allowed = bool(sc_payload.get("auto_tuning_allowed", False))
        out.append(
            ReplayDiscoveryQualityCase(
                quality_bucket=quality_bucket,
                capture_recall_rate=_maybe_float(
                    sc_payload.get("capture_recall_rate")
                ),
                early_continuation_rate=_maybe_float(
                    sc_payload.get("early_continuation_rate")
                ),
                severe_miss_rate=_maybe_float(
                    sc_payload.get("severe_miss_rate")
                ),
                false_negative_reject_rate=_maybe_float(
                    sc_payload.get("false_negative_reject_rate")
                ),
                bucket_event_id=None,
                scorecard_event_id=sc.event_id,
                parent_event_id=sc.event_id,
                timestamp=int(sc.timestamp),
                evidence_refs=tuple(evidence_refs),
                auto_tuning_allowed=auto_tuning_allowed,
                status=ReplayStatus.DEGRADED,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Public extension class
# ---------------------------------------------------------------------------
class AdaptiveEventReplayExtension:
    """Read-only Phase 11C.1C-C-B-B-B-E-A replay extension.

    Construct ONCE per process / test. The extension holds a
    reference to an :class:`EventRepository` and never writes through
    it; the underlying ``conn`` is consumed via the public read API
    only.
    """

    SOURCE_PHASE: str = SOURCE_PHASE
    SOURCE_MODULE: str = SOURCE_MODULE
    SCHEMA_VERSION: str = SCHEMA_VERSION

    def __init__(self, *, event_repo: EventRepository) -> None:
        self._repo = event_repo

    # ------------------------------------------------------------------
    @property
    def event_repo(self) -> EventRepository:
        return self._repo

    # ------------------------------------------------------------------
    def replay_all(
        self,
        *,
        since_ts: int | None = None,
        until_ts: int | None = None,
        symbol: str | None = None,
    ) -> AdaptiveReplayBundle:
        """Replay every adaptive event in the (since_ts, until_ts) window."""
        events = load_adaptive_events(
            self._repo,
            since_ts=since_ts,
            until_ts=until_ts,
            symbol=symbol,
        )
        return self._replay_from(events)

    def replay_from_events(
        self,
        events: Sequence[Event],
    ) -> AdaptiveReplayBundle:
        """Replay against an explicit, in-memory event list.

        Used by tests that don't want to go through the repository.
        """
        return self._replay_from(_sort_events(events))

    def _replay_from(self, events: Sequence[Event]) -> AdaptiveReplayBundle:
        events = _sort_events(events)
        discovery_timelines = build_discovery_timelines(events)
        candidate_lifecycles = build_candidate_lifecycles(events)
        tail_outcomes = build_tail_outcomes(events)
        mover_coverage = build_mover_coverage_cases(events)
        post_discovery = build_post_discovery_outcome_cases(events)
        reject_attribution = build_reject_attribution_cases(events)
        severe_miss = build_severe_miss_cases(events)
        discovery_quality = build_discovery_quality_cases(events)

        # Replay-record event counts: we count events that *can*
        # produce a replay record in the absence of duplicates. This
        # is the brief's "replay count == input event count" check
        # surface; we report skipped events separately (e.g. cohort /
        # validation rollups that aren't yet expanded into per-record
        # objects).
        record_event_types = {
            # Discovery timeline group counts every event - one per
            # canonical step.
            *DISCOVERY_TIMELINE_EVENT_TYPES,
            *CANDIDATE_LIFECYCLE_EVENT_TYPES,
            *TAIL_OUTCOME_EVENT_TYPES,
            EventType.MOVER_CAPTURE_PATH_AUDITED,
            EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
            EventType.MOVER_CAPTURE_RECALL_AUDIT_GENERATED,
            EventType.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED,
            EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
            EventType.POST_DISCOVERY_OUTCOME_REPORT_GENERATED,
            EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
            EventType.REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED,
            EventType.FALSE_NEGATIVE_REJECT_DETECTED,
            EventType.CORRECT_PROTECTIVE_REJECT_CONFIRMED,
            EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED,
            EventType.SEVERE_MISSED_TAIL_TRIAGE_GENERATED,
            EventType.SEVERE_MISS_ESCALATION_REQUIRED,
            EventType.DISCOVERY_QUALITY_BUCKET_EVALUATED,
            EventType.DISCOVERY_QUALITY_SCORECARD_GENERATED,
        }
        adaptive_count = sum(
            1
            for ev in events
            if ev.event_type in ADAPTIVE_REPLAY_EVENT_TYPES
        )
        record_count = sum(
            1 for ev in events if ev.event_type in record_event_types
        )
        skipped = adaptive_count - record_count
        return AdaptiveReplayBundle(
            discovery_timelines=tuple(discovery_timelines),
            candidate_lifecycles=tuple(candidate_lifecycles),
            tail_outcomes=tuple(tail_outcomes),
            mover_coverage_cases=tuple(mover_coverage),
            post_discovery_outcome_cases=tuple(post_discovery),
            reject_attribution_cases=tuple(reject_attribution),
            severe_miss_cases=tuple(severe_miss),
            discovery_quality_cases=tuple(discovery_quality),
            input_event_count=adaptive_count,
            replay_record_event_count=record_count,
            skipped_event_count=skipped,
        )


__all__ = [
    "SOURCE_PHASE",
    "SOURCE_MODULE",
    "SCHEMA_VERSION",
    "FORBIDDEN_REPLAY_PAYLOAD_KEYS",
    "DISCOVERY_TIMELINE_EVENT_TYPES",
    "CANDIDATE_LIFECYCLE_EVENT_TYPES",
    "TAIL_OUTCOME_EVENT_TYPES",
    "MOVER_COVERAGE_EVENT_TYPES",
    "POST_DISCOVERY_OUTCOME_EVENT_TYPES",
    "REJECT_ATTRIBUTION_EVENT_TYPES",
    "SEVERE_MISS_EVENT_TYPES",
    "DISCOVERY_QUALITY_EVENT_TYPES",
    "STRATEGY_VALIDATION_EVENT_TYPES",
    "PAPER_ALPHA_EVENT_TYPES",
    "REGIME_CLUSTER_EVENT_TYPES",
    "ADAPTIVE_REPLAY_EVENT_TYPES",
    "ReplayStatus",
    "ReplayDiscoveryTimeline",
    "ReplayCandidateLifecycle",
    "ReplayTailOutcome",
    "ReplayMoverCoverageCase",
    "ReplayPostDiscoveryOutcomeCase",
    "ReplayRejectAttributionCase",
    "ReplaySevereMissCase",
    "ReplayDiscoveryQualityCase",
    "AdaptiveReplayBundle",
    "AdaptiveEventReplayExtension",
    "load_adaptive_events",
    "build_discovery_timelines",
    "build_candidate_lifecycles",
    "build_tail_outcomes",
    "build_mover_coverage_cases",
    "build_post_discovery_outcome_cases",
    "build_reject_attribution_cases",
    "build_severe_miss_cases",
    "build_discovery_quality_cases",
]
