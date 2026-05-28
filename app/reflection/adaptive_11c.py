"""Phase 11C.1C-C-B-B-B-E-B - Reflection Extension for 11C Adaptive Events v0.

Read-only, deterministic, structured reflection over the Phase 11C
adaptive / discovery / evidence event chain produced by Block A and
Block B (LABEL_*, TAIL_LABEL_*, MISSED_TAIL_*, FAKE_BREAKOUT_*,
STRATEGY_VALIDATION_*, PAPER_ALPHA_*, REGIME_CLUSTER_*,
MOVER_CAPTURE_*, HISTORICAL_MOVER_COVERAGE_*, POST_DISCOVERY_OUTCOME_*,
REJECT_TO_OUTCOME_*, SEVERE_MISSED_TAIL_*, DISCOVERY_QUALITY_*).

The engine consumes the event payloads (or, equivalently, the Phase
11C.1C-C-B-B-B-E-A replay value objects which carry the same fields)
and emits one :class:`AdaptiveReflectionCase` per input event, plus a
top-level :class:`AdaptiveReflectionSummary` with deterministic counts.

Output is **only** structured tags / summaries / counts / warnings.
The engine NEVER:

  - emits trade advice (no buy / sell / long / short / direction /
    side / entry / exit),
  - emits sizing or risk numbers (no position_size / leverage / stop /
    stop_loss / target / take_profit / risk_budget),
  - emits a runtime config patch (no runtime_config_patch /
    symbol_limit_patch / threshold_patch / candidate_pool_patch /
    regime_weight_patch),
  - calls an LLM, DeepSeek, or any natural-language model,
  - depends on chat history,
  - mutates events.db, runtime parameters, or any shared state,
  - imports `app.risk`, `app.execution`, `app.exchanges`,
    `app.llm`, or `app.telegram`.

Phase 11C.1C-C-B-B-B-E-B safety boundary
----------------------------------------

  - mode = paper
  - live_trading = False
  - exchange_live_orders = False
  - right_tail = False
  - llm = False
  - telegram_outbound_enabled = False
  - binance_private_api_enabled = False
  - no Binance API key / secret / signed endpoint / private websocket
    / listenKey
  - no real Telegram outbound
  - no DeepSeek trade decision
  - **Phase 12 = FORBIDDEN**
  - **auto_tuning_allowed = False** on every emitted case / summary

A successful Phase 11C.1C-C-B-B-B-E-B only allows the next phase
(C3 Evidence Contract Baseline) to start; it does NOT close out cloud
evidence and does NOT authorise live trading.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.events import Event, EventType


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------
SOURCE_PHASE: str = "phase_11c_1c_c_b_b_b_e_b"
SOURCE_MODULE: str = "reflection_11c_adaptive_engine"
SCHEMA_VERSION: str = "v0"


# ---------------------------------------------------------------------------
# Forbidden-payload vocabulary (defensive)
# ---------------------------------------------------------------------------
#: Keys that MUST NEVER appear, at any nesting depth, in any payload
#: this module emits. The set codifies the brief's
#: "no trade decisions, no runtime patches" boundary.
FORBIDDEN_REFLECTION_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        # Direction / trade-decision keys.
        "buy",
        "sell",
        "long",
        "short",
        "direction",
        "side",
        "entry",
        "exit",
        # Sizing / leverage / risk-budget keys.
        "position_size",
        "leverage",
        "stop",
        "stop_loss",
        "stop_price",
        "target",
        "target_price",
        "take_profit",
        "risk_budget",
        "order",
        "order_type",
        "execution_command",
        # Runtime-config patch keys.
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
    }
)


class AdaptiveReflectionForbiddenFieldError(ValueError):
    """Raised when a payload contains a forbidden key."""


def _assert_no_forbidden_keys(
    payload: Mapping[str, Any] | None,
    *,
    context: str,
) -> None:
    """Walk ``payload`` recursively and refuse any forbidden key."""
    if payload is None:
        return

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            for key, value in node.items():
                key_str = str(key)
                if key_str in FORBIDDEN_REFLECTION_PAYLOAD_KEYS:
                    raise AdaptiveReflectionForbiddenFieldError(
                        "reflection 11C extension produced a forbidden "
                        f"payload key {key_str!r} at {path}.{key_str} in "
                        f"context {context!r}; this is a hard violation "
                        "of the Phase 11C.1C-C-B-B-B-E-B boundary."
                    )
                _walk(value, f"{path}.{key_str}")
        elif isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                _walk(item, f"{path}[{index}]")

    _walk(payload, context or "<root>")


# ---------------------------------------------------------------------------
# Severity vocabulary
# ---------------------------------------------------------------------------
class AdaptiveReflectionSeverity(str, Enum):
    """Closed severity vocabulary used on every reflection case.

    Severity is a descriptive label only; it never authorises a trade
    or a runtime change. The vocabulary is intentionally narrow so the
    output is structurally comparable across runs.
    """

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SEVERE = "severe"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Reflection tag vocabulary
# ---------------------------------------------------------------------------
class AdaptiveReflectionTag(str, Enum):
    """Closed tag vocabulary attached to a reflection case.

    Tags are additive (a single case can carry several) and are drawn
    from this enum only. The engine NEVER produces a free-form natural
    language tag.
    """

    # Discovery-timing tags.
    EARLY_DISCOVERY = "early_discovery"
    LATE_DISCOVERY = "late_discovery"
    LATE_TOP_CHASE = "late_top_chase"
    POST_DISCOVERY_NO_EDGE = "post_discovery_no_edge"

    # Tail-coverage tags.
    MISSED_TAIL = "missed_tail"
    SEVERE_MISS = "severe_miss"
    CANDIDATE_EVICTED_BEFORE_TAIL = "candidate_evicted_before_tail"
    FAKE_BREAKOUT_DETECTED = "fake_breakout_detected"

    # Reject-attribution tags.
    RISK_REJECTED_THEN_MOVED = "risk_rejected_then_moved"
    FALSE_NEGATIVE_REJECT = "false_negative_reject"
    CORRECT_PROTECTIVE_REJECT = "correct_protective_reject"

    # Pre-anomaly tags.
    WEAK_PRE_ANOMALY = "weak_pre_anomaly"

    # Data quality tags.
    DATA_GAP = "data_gap"
    INSUFFICIENT_HISTORY = "insufficient_history"
    DEGRADED_DISCOVERY_QUALITY = "degraded_discovery_quality"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"

    # Operator-action tags.
    NEEDS_OPERATOR_REVIEW = "needs_operator_review"
    NEEDS_DATA_RECOVERY = "needs_data_recovery"
    NEEDS_RULE_REVIEW = "needs_rule_review"


# ---------------------------------------------------------------------------
# Closed event-group vocabulary the engine knows how to read
# ---------------------------------------------------------------------------
ADAPTIVE_REFLECTION_EVENT_TYPES: tuple[EventType, ...] = (
    # Label / candidate lifecycle.
    EventType.LABEL_TRACKING_STARTED,
    EventType.LABEL_WINDOW_UPDATED,
    EventType.LABEL_WINDOW_COMPLETED,
    # Tail outcome.
    EventType.TAIL_LABEL_ASSIGNED,
    EventType.MISSED_TAIL_DETECTED,
    EventType.FAKE_BREAKOUT_DETECTED,
    # Mover coverage.
    EventType.MOVER_CAPTURE_PATH_AUDITED,
    EventType.MOVER_CAPTURE_RECALL_AUDIT_GENERATED,
    EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
    EventType.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED,
    # Post-discovery outcome.
    EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
    EventType.POST_DISCOVERY_OUTCOME_REPORT_GENERATED,
    # Reject attribution.
    EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
    EventType.REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED,
    EventType.FALSE_NEGATIVE_REJECT_DETECTED,
    EventType.CORRECT_PROTECTIVE_REJECT_CONFIRMED,
    # Severe miss triage.
    EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED,
    EventType.SEVERE_MISSED_TAIL_TRIAGE_GENERATED,
    EventType.SEVERE_MISS_ESCALATION_REQUIRED,
    # Discovery quality.
    EventType.DISCOVERY_QUALITY_BUCKET_EVALUATED,
    EventType.DISCOVERY_QUALITY_SCORECARD_GENERATED,
    # Strategy validation.
    EventType.STRATEGY_VALIDATION_SAMPLE_CREATED,
    EventType.STRATEGY_MODE_VALIDATED,
    EventType.CANDIDATE_STAGE_VALIDATED,
    EventType.SCORE_BUCKET_VALIDATED,
    EventType.CLUSTER_EXPOSURE_ASSESSED,
    EventType.CLUSTER_LEADER_VALIDATED,
    EventType.STRATEGY_VALIDATION_DATASET_BUILT,
    # Paper alpha gate.
    EventType.PAPER_ALPHA_GATE_EVALUATED,
    EventType.PAPER_ALPHA_RULE_EVALUATED,
    EventType.PAPER_ALPHA_COHORT_EVALUATED,
    EventType.PAPER_ALPHA_REPORT_GENERATED,
    # Regime cluster cohort.
    EventType.REGIME_CLUSTER_EVIDENCE_PACK_GENERATED,
    EventType.REGIME_CLUSTER_COHORT_SUMMARY_GENERATED,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _payload(ev: Event) -> dict[str, Any]:
    p = ev.payload
    return p if isinstance(p, dict) else {}


def _maybe_str(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _maybe_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _maybe_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _evidence_refs_for(ev: Event) -> tuple[str, ...]:
    """Best-effort evidence_refs extraction.

    The engine always preserves an event_id-based fallback so a case
    can never lose its provenance.
    """
    payload = _payload(ev)
    refs: list[str] = []
    payload_refs = payload.get("evidence_refs")
    if isinstance(payload_refs, (list, tuple)):
        for ref in payload_refs:
            if isinstance(ref, str) and ref:
                refs.append(ref)
    # Look one level deep into common nested record blocks.
    for nested_key in ("record", "case", "summary"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            nested_refs = nested.get("evidence_refs")
            if isinstance(nested_refs, (list, tuple)):
                for ref in nested_refs:
                    if isinstance(ref, str) and ref and ref not in refs:
                        refs.append(ref)
    # Always add the event_id last so it is always present.
    if ev.event_id and ev.event_id not in refs:
        refs.append(ev.event_id)
    return tuple(refs)


def _record_block(ev: Event) -> dict[str, Any]:
    """Return the inner ``record`` block if present, else an empty dict."""
    payload = _payload(ev)
    rec = payload.get("record")
    if isinstance(rec, dict):
        return rec
    return {}


# ---------------------------------------------------------------------------
# Reflection input
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AdaptiveReflectionInput:
    """Bundle of inputs the adaptive reflection engine consumes.

    The engine accepts an iterable of :class:`Event` instances. Tests
    construct events directly; production callers feed the events
    surfaced by the Phase 11C.1C-C-B-B-B-E-A
    :class:`AdaptiveEventReplayExtension` (which also reads from
    ``EventRepository`` read-only).

    The bundle is read-only - it is consumed but never mutated.
    """

    events: tuple[Event, ...] = field(default_factory=tuple)
    notes: str | None = None
    schema_version: str = SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Reflection case
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AdaptiveReflectionCase:
    """One reflection case for one input event.

    The case carries:

      - ``case_id``: the reflecting event's ``event_id`` (so the case
        is byte-stable and unambiguous);
      - ``symbol``, ``opportunity_id``: best-effort identity;
      - ``event_type``: the event-type value the case was built from;
      - ``tags``: a sorted tuple of :class:`AdaptiveReflectionTag`;
      - ``severity``: the closed :class:`AdaptiveReflectionSeverity`
        label;
      - ``evidence_refs``: payload refs + ``event_id`` so a downstream
        auditor can pin the case to its source row;
      - ``needs_operator_review``, ``needs_data_recovery``,
        ``needs_rule_review``: actionable booleans;
      - ``auto_tuning_allowed``: hard-pinned to ``False``;
      - ``warnings``: a sorted tuple of descriptive strings (no
        natural-language hallucinations - every entry comes from a
        fixed vocabulary inside the engine).
    """

    case_id: str
    symbol: str | None
    opportunity_id: str | None
    event_type: str
    tags: tuple[str, ...]
    severity: str
    evidence_refs: tuple[str, ...]
    needs_operator_review: bool
    needs_data_recovery: bool
    needs_rule_review: bool
    auto_tuning_allowed: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)
    timestamp: int | None = None
    schema_version: str = SCHEMA_VERSION
    source_phase: str = SOURCE_PHASE
    source_module: str = SOURCE_MODULE

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "source_module": self.source_module,
            "reflection_object": "AdaptiveReflectionCase",
            "case_id": self.case_id,
            "symbol": self.symbol,
            "opportunity_id": self.opportunity_id,
            "event_type": self.event_type,
            "tags": list(self.tags),
            "severity": self.severity,
            "evidence_refs": list(self.evidence_refs),
            "needs_operator_review": bool(self.needs_operator_review),
            "needs_data_recovery": bool(self.needs_data_recovery),
            "needs_rule_review": bool(self.needs_rule_review),
            "auto_tuning_allowed": False,
            "warnings": list(self.warnings),
            "timestamp": self.timestamp,
        }
        _assert_no_forbidden_keys(
            payload, context="AdaptiveReflectionCase.to_payload"
        )
        return payload


# ---------------------------------------------------------------------------
# Reflection summary
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AdaptiveReflectionSummary:
    """Aggregate reflection summary across many cases.

    Carries deterministic counts (no fabrication) plus the per-case
    list. ``auto_tuning_allowed`` is hard-pinned to ``False``.
    """

    total_input_event_count: int
    total_case_count: int
    skipped_event_count: int
    cases: tuple[AdaptiveReflectionCase, ...]
    tag_counts: dict[str, int]
    severity_counts: dict[str, int]
    needs_operator_review_count: int
    needs_data_recovery_count: int
    needs_rule_review_count: int
    auto_tuning_allowed: bool = False
    warnings: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = SCHEMA_VERSION
    source_phase: str = SOURCE_PHASE
    source_module: str = SOURCE_MODULE

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "source_module": self.source_module,
            "reflection_object": "AdaptiveReflectionSummary",
            "total_input_event_count": int(self.total_input_event_count),
            "total_case_count": int(self.total_case_count),
            "skipped_event_count": int(self.skipped_event_count),
            "tag_counts": dict(sorted(self.tag_counts.items())),
            "severity_counts": dict(sorted(self.severity_counts.items())),
            "needs_operator_review_count": int(
                self.needs_operator_review_count
            ),
            "needs_data_recovery_count": int(self.needs_data_recovery_count),
            "needs_rule_review_count": int(self.needs_rule_review_count),
            "auto_tuning_allowed": False,
            "warnings": list(self.warnings),
            "cases": [c.to_payload() for c in self.cases],
        }
        _assert_no_forbidden_keys(
            payload, context="AdaptiveReflectionSummary.to_payload"
        )
        return payload


# ---------------------------------------------------------------------------
# Reflection engine
# ---------------------------------------------------------------------------
class Reflection11CAdaptiveEngine:
    """Read-only reflection engine for the 11C adaptive event chain.

    Public surface:

      - :meth:`reflect_event`  - reflect on one event, return one case.
      - :meth:`reflect_events` - reflect on many events, return a
        summary.

    The engine is stateless and side-effect-free. It never opens a
    socket, never imports a Risk / Execution / Exchange / LLM /
    Telegram module, and never produces a runtime-config patch.
    """

    def __init__(self) -> None:
        # No mutable state; the engine is intentionally inert.
        self._supported_types: frozenset[EventType] = frozenset(
            ADAPTIVE_REFLECTION_EVENT_TYPES
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def reflect_events(
        self,
        events: Iterable[Event] | AdaptiveReflectionInput,
    ) -> AdaptiveReflectionSummary:
        """Reflect on many events and return a deterministic summary."""
        if isinstance(events, AdaptiveReflectionInput):
            event_seq: Sequence[Event] = events.events
        else:
            event_seq = tuple(events)

        cases: list[AdaptiveReflectionCase] = []
        skipped = 0
        # Deterministic ordering: (timestamp, event_type, event_id)
        ordered = sorted(
            event_seq,
            key=lambda ev: (
                int(ev.timestamp),
                ev.event_type.value,
                ev.event_id,
            ),
        )
        for ev in ordered:
            if ev.event_type not in self._supported_types:
                skipped += 1
                continue
            cases.append(self.reflect_event(ev))

        # Counts (deterministic).
        tag_counts: dict[str, int] = {}
        severity_counts: dict[str, int] = {}
        op_count = 0
        dr_count = 0
        rr_count = 0
        for case in cases:
            severity_counts[case.severity] = (
                severity_counts.get(case.severity, 0) + 1
            )
            for tag in case.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            if case.needs_operator_review:
                op_count += 1
            if case.needs_data_recovery:
                dr_count += 1
            if case.needs_rule_review:
                rr_count += 1

        return AdaptiveReflectionSummary(
            total_input_event_count=len(event_seq),
            total_case_count=len(cases),
            skipped_event_count=skipped,
            cases=tuple(cases),
            tag_counts=tag_counts,
            severity_counts=severity_counts,
            needs_operator_review_count=op_count,
            needs_data_recovery_count=dr_count,
            needs_rule_review_count=rr_count,
        )

    def reflect_event(self, ev: Event) -> AdaptiveReflectionCase:
        """Reflect on one event and return one deterministic case."""
        et = ev.event_type
        if et not in self._supported_types:
            return self._build_unsupported_case(ev)

        # Dispatch by event type. Each builder is pure and
        # deterministic; missing fields produce ``insufficient_evidence``
        # / ``insufficient_history`` tags rather than raising.
        if et is EventType.POST_DISCOVERY_OUTCOME_EVALUATED:
            return self._reflect_post_discovery_outcome(ev)
        if et is EventType.POST_DISCOVERY_OUTCOME_REPORT_GENERATED:
            return self._reflect_post_discovery_report(ev)
        if et is EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED:
            return self._reflect_reject_attribution_case(ev)
        if et is EventType.FALSE_NEGATIVE_REJECT_DETECTED:
            return self._reflect_false_negative_reject(ev)
        if et is EventType.CORRECT_PROTECTIVE_REJECT_CONFIRMED:
            return self._reflect_correct_protective_reject(ev)
        if et is EventType.REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED:
            return self._reflect_reject_attribution_report(ev)
        if et is EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED:
            return self._reflect_severe_miss_root_cause(ev)
        if et is EventType.SEVERE_MISS_ESCALATION_REQUIRED:
            return self._reflect_severe_miss_escalation(ev)
        if et is EventType.SEVERE_MISSED_TAIL_TRIAGE_GENERATED:
            return self._reflect_severe_miss_triage(ev)
        if et is EventType.DISCOVERY_QUALITY_BUCKET_EVALUATED:
            return self._reflect_discovery_quality_bucket(ev)
        if et is EventType.DISCOVERY_QUALITY_SCORECARD_GENERATED:
            return self._reflect_discovery_quality_scorecard(ev)
        if et is EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:
            return self._reflect_historical_mover_record(ev)
        if et is EventType.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED:
            return self._reflect_historical_mover_backfill(ev)
        if et is EventType.MOVER_CAPTURE_PATH_AUDITED:
            return self._reflect_mover_capture_path(ev)
        if et is EventType.MOVER_CAPTURE_RECALL_AUDIT_GENERATED:
            return self._reflect_mover_capture_recall(ev)
        if et is EventType.TAIL_LABEL_ASSIGNED:
            return self._reflect_tail_label_assigned(ev)
        if et is EventType.MISSED_TAIL_DETECTED:
            return self._reflect_missed_tail(ev)
        if et is EventType.FAKE_BREAKOUT_DETECTED:
            return self._reflect_fake_breakout(ev)
        if et in (
            EventType.LABEL_TRACKING_STARTED,
            EventType.LABEL_WINDOW_UPDATED,
            EventType.LABEL_WINDOW_COMPLETED,
        ):
            return self._reflect_label_lifecycle(ev)
        if et in (
            EventType.STRATEGY_VALIDATION_SAMPLE_CREATED,
            EventType.STRATEGY_MODE_VALIDATED,
            EventType.CANDIDATE_STAGE_VALIDATED,
            EventType.SCORE_BUCKET_VALIDATED,
            EventType.CLUSTER_EXPOSURE_ASSESSED,
            EventType.CLUSTER_LEADER_VALIDATED,
            EventType.STRATEGY_VALIDATION_DATASET_BUILT,
        ):
            return self._reflect_strategy_validation(ev)
        if et in (
            EventType.PAPER_ALPHA_GATE_EVALUATED,
            EventType.PAPER_ALPHA_RULE_EVALUATED,
            EventType.PAPER_ALPHA_COHORT_EVALUATED,
            EventType.PAPER_ALPHA_REPORT_GENERATED,
        ):
            return self._reflect_paper_alpha(ev)
        if et in (
            EventType.REGIME_CLUSTER_EVIDENCE_PACK_GENERATED,
            EventType.REGIME_CLUSTER_COHORT_SUMMARY_GENERATED,
        ):
            return self._reflect_regime_cluster(ev)
        # Defensive: should be unreachable thanks to _supported_types.
        return self._build_unsupported_case(ev)

    # ==================================================================
    # Per-event reflection builders
    # ==================================================================
    def _reflect_post_discovery_outcome(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        record = _record_block(ev)
        if not record:
            return self._build_insufficient_case(
                ev,
                warnings=("post_discovery_outcome_record_missing",),
                opportunity_id=_maybe_str(payload.get("opportunity_id")),
            )

        tags: list[AdaptiveReflectionTag] = []
        warnings: list[str] = []
        timing = _maybe_str(record.get("detection_timing_label"))
        outcome = _maybe_str(record.get("outcome_label"))
        symbol = (
            _maybe_str(record.get("symbol"))
            or _maybe_str(payload.get("symbol"))
            or ev.symbol
        )

        # Late top-chase: the bundled timing / outcome label says we
        # entered after the move was already mostly over.
        late_timing = timing in {"LATE", "TOO_LATE", "LATE_DISCOVERY"}
        late_outcome = outcome in {
            "LATE_TOP_CHASE",
            "LATE_REVERSAL",
            "DUMPED",
            "EXHAUSTION_CANDIDATE",
        }
        if late_timing or late_outcome:
            tags.append(AdaptiveReflectionTag.LATE_TOP_CHASE)
            tags.append(AdaptiveReflectionTag.LATE_DISCOVERY)

        # Early discovery.
        early_timing = timing in {"EARLY", "EARLY_BUT_CHOPPY", "EARLY_DISCOVERY"}
        early_outcome = outcome in {"EARLY_CONTINUATION", "EARLY_BUT_CHOPPY"}
        if early_timing or early_outcome:
            tags.append(AdaptiveReflectionTag.EARLY_DISCOVERY)

        # No-edge bucket.
        if outcome == "NO_CLEAR_EDGE":
            tags.append(AdaptiveReflectionTag.POST_DISCOVERY_NO_EDGE)

        # Missed strong tail.
        if outcome == "MISSED_STRONG_TAIL":
            tags.append(AdaptiveReflectionTag.MISSED_TAIL)
            tags.append(AdaptiveReflectionTag.LATE_DISCOVERY)

        # Fake breakout shape on post-discovery side.
        if outcome == "FAKE_BREAKOUT":
            tags.append(AdaptiveReflectionTag.FAKE_BREAKOUT_DETECTED)

        # Insufficient price-path.
        if outcome == "INSUFFICIENT_PRICE_PATH" or timing == "INSUFFICIENT_DATA":
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_HISTORY)
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE)
            warnings.append("post_discovery_insufficient_price_path")

        if not tags:
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE)
            warnings.append("post_discovery_outcome_label_unrecognised")

        severity = self._severity_for(tags)
        needs_review = self._needs_operator_review(tags)
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=symbol,
            opportunity_id=_maybe_str(payload.get("opportunity_id")),
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=severity.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=needs_review,
            needs_data_recovery=AdaptiveReflectionTag.INSUFFICIENT_HISTORY
            in tags
            or AdaptiveReflectionTag.DATA_GAP in tags,
            needs_rule_review=AdaptiveReflectionTag.LATE_TOP_CHASE in tags
            or AdaptiveReflectionTag.POST_DISCOVERY_NO_EDGE in tags,
            warnings=tuple(sorted(warnings)),
            timestamp=int(ev.timestamp),
        )

    def _reflect_post_discovery_report(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        warnings: list[str] = []
        tags: list[AdaptiveReflectionTag] = []
        # Roll-up record - we mostly just acknowledge it.
        ref_window = _maybe_str(payload.get("reference_window"))
        if not ref_window:
            warnings.append("post_discovery_report_reference_window_missing")
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE)

        if not tags:
            # No anomaly detected; emit info only.
            severity = AdaptiveReflectionSeverity.INFO
        else:
            severity = self._severity_for(tags)

        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=ev.symbol,
            opportunity_id=None,
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=severity.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=False,
            needs_data_recovery=False,
            needs_rule_review=False,
            warnings=tuple(sorted(warnings)),
            timestamp=int(ev.timestamp),
        )

    def _reflect_reject_attribution_case(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        verdict = _maybe_str(payload.get("verdict"))
        if verdict is None:
            return self._build_insufficient_case(
                ev,
                warnings=("reject_attribution_verdict_missing",),
                opportunity_id=_maybe_str(payload.get("opportunity_id")),
            )

        tags: list[AdaptiveReflectionTag] = []
        warnings: list[str] = []
        if verdict == "FALSE_NEGATIVE_REJECT":
            tags.append(AdaptiveReflectionTag.FALSE_NEGATIVE_REJECT)
            tags.append(AdaptiveReflectionTag.RISK_REJECTED_THEN_MOVED)
        elif verdict == "STRATEGY_MODE_FALSE_NEGATIVE":
            tags.append(AdaptiveReflectionTag.FALSE_NEGATIVE_REJECT)
        elif verdict == "CORRECT_PROTECTIVE_REJECT":
            tags.append(AdaptiveReflectionTag.CORRECT_PROTECTIVE_REJECT)
        elif verdict in {
            "DATA_QUALITY_REJECT",
            "LIQUIDITY_PROTECTIVE_REJECT",
            "MANIPULATION_PROTECTIVE_REJECT",
            "STOP_SAFETY_REJECT",
            "REBASE_PROTECTIVE_REJECT",
            "SYSTEM_SAFETY_REJECT",
        }:
            tags.append(AdaptiveReflectionTag.CORRECT_PROTECTIVE_REJECT)
            if verdict == "DATA_QUALITY_REJECT":
                tags.append(AdaptiveReflectionTag.DATA_GAP)
        elif verdict == "INSUFFICIENT_EVIDENCE":
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE)
        else:
            # Includes "NO_REJECT_FOUND", "UNKNOWN", new labels.
            warnings.append(f"reject_attribution_verdict_unrecognised:{verdict}")
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE)

        severity = self._severity_for(tags)
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=_maybe_str(payload.get("symbol")) or ev.symbol,
            opportunity_id=_maybe_str(payload.get("opportunity_id")),
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=severity.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=AdaptiveReflectionTag.FALSE_NEGATIVE_REJECT
            in tags,
            needs_data_recovery=AdaptiveReflectionTag.DATA_GAP in tags,
            needs_rule_review=AdaptiveReflectionTag.FALSE_NEGATIVE_REJECT
            in tags,
            warnings=tuple(sorted(warnings)),
            timestamp=int(ev.timestamp),
        )

    def _reflect_false_negative_reject(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        tags = [
            AdaptiveReflectionTag.FALSE_NEGATIVE_REJECT,
            AdaptiveReflectionTag.RISK_REJECTED_THEN_MOVED,
        ]
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=_maybe_str(payload.get("symbol")) or ev.symbol,
            opportunity_id=_maybe_str(payload.get("opportunity_id")),
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=AdaptiveReflectionSeverity.HIGH.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=True,
            needs_data_recovery=False,
            needs_rule_review=True,
            warnings=(),
            timestamp=int(ev.timestamp),
        )

    def _reflect_correct_protective_reject(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        tags = [AdaptiveReflectionTag.CORRECT_PROTECTIVE_REJECT]
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=_maybe_str(payload.get("symbol")) or ev.symbol,
            opportunity_id=_maybe_str(payload.get("opportunity_id")),
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=AdaptiveReflectionSeverity.INFO.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=False,
            needs_data_recovery=False,
            needs_rule_review=False,
            warnings=(),
            timestamp=int(ev.timestamp),
        )

    def _reflect_reject_attribution_report(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        # Roll-up record - acknowledge only.
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=ev.symbol,
            opportunity_id=None,
            event_type=ev.event_type.value,
            tags=(),
            severity=AdaptiveReflectionSeverity.INFO.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=False,
            needs_data_recovery=False,
            needs_rule_review=False,
            warnings=(),
            timestamp=int(ev.timestamp),
        )

    def _reflect_severe_miss_root_cause(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        severity_label = _maybe_str(payload.get("severity")) or "UNKNOWN"
        root_cause = _maybe_str(payload.get("root_cause"))
        warnings: list[str] = []
        tags = [AdaptiveReflectionTag.SEVERE_MISS, AdaptiveReflectionTag.MISSED_TAIL]
        # Data-related root causes -> needs_data_recovery.
        data_causes = {
            "DATA_GAP",
            "DATA_UNRELIABLE",
            "INSUFFICIENT_HISTORY",
            "PRICE_PATH_INSUFFICIENT",
            "EVENT_SCHEMA_VERSION_MISMATCH",
        }
        rule_causes = {
            "ANOMALY_FILTER_TOO_STRICT",
            "STRATEGY_MODE_TOO_STRICT",
            "CANDIDATE_POOL_FULL",
            "REGIME_WEIGHT_DEPRIORITISED",
            "RISK_REJECT_TOO_AGGRESSIVE",
        }
        needs_data = False
        needs_rule = False
        if root_cause in data_causes:
            tags.append(AdaptiveReflectionTag.DATA_GAP)
            tags.append(AdaptiveReflectionTag.NEEDS_DATA_RECOVERY)
            needs_data = True
        elif root_cause in rule_causes:
            tags.append(AdaptiveReflectionTag.NEEDS_RULE_REVIEW)
            needs_rule = True
        elif root_cause is None:
            warnings.append("severe_miss_root_cause_missing")
        else:
            warnings.append(f"severe_miss_root_cause_unrecognised:{root_cause}")

        # SEVERE / CRITICAL severity -> always escalate.
        if severity_label in {"SEVERE", "CRITICAL"}:
            tags.append(AdaptiveReflectionTag.NEEDS_OPERATOR_REVIEW)

        # Always recommend operator review for severe misses.
        case_severity = (
            AdaptiveReflectionSeverity.SEVERE
            if severity_label in {"SEVERE", "CRITICAL"}
            else AdaptiveReflectionSeverity.HIGH
        )
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=_maybe_str(payload.get("symbol")) or ev.symbol,
            opportunity_id=_maybe_str(payload.get("opportunity_id")),
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=case_severity.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=True,
            needs_data_recovery=needs_data,
            needs_rule_review=needs_rule,
            warnings=tuple(sorted(warnings)),
            timestamp=int(ev.timestamp),
        )

    def _reflect_severe_miss_escalation(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        tags = [
            AdaptiveReflectionTag.SEVERE_MISS,
            AdaptiveReflectionTag.NEEDS_OPERATOR_REVIEW,
        ]
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=_maybe_str(payload.get("symbol")) or ev.symbol,
            opportunity_id=_maybe_str(payload.get("opportunity_id")),
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=AdaptiveReflectionSeverity.SEVERE.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=True,
            needs_data_recovery=False,
            needs_rule_review=False,
            warnings=(),
            timestamp=int(ev.timestamp),
        )

    def _reflect_severe_miss_triage(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        # Roll-up triage report - acknowledge only.
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=ev.symbol,
            opportunity_id=None,
            event_type=ev.event_type.value,
            tags=(),
            severity=AdaptiveReflectionSeverity.INFO.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=False,
            needs_data_recovery=False,
            needs_rule_review=False,
            warnings=(),
            timestamp=int(ev.timestamp),
        )

    def _reflect_discovery_quality_bucket(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        bucket = _maybe_str(payload.get("quality_bucket"))
        tags: list[AdaptiveReflectionTag] = []
        warnings: list[str] = []
        if bucket is None:
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE)
            warnings.append("discovery_quality_bucket_missing")
        elif bucket in {"DEGRADED", "WEAK", "POOR", "INSUFFICIENT"}:
            tags.append(AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY)
            tags.append(AdaptiveReflectionTag.NEEDS_RULE_REVIEW)
        elif bucket in {"INSUFFICIENT_EVIDENCE", "INSUFFICIENT_DATA"}:
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE)
        # GOLDEN_TAIL / STRONG / OK -> no anomaly tag.

        severity = self._severity_for(tags) if tags else AdaptiveReflectionSeverity.INFO
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=ev.symbol,
            opportunity_id=None,
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=severity.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY
            in tags,
            needs_data_recovery=False,
            needs_rule_review=AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY
            in tags,
            warnings=tuple(sorted(warnings)),
            timestamp=int(ev.timestamp),
        )

    def _reflect_discovery_quality_scorecard(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        recall = _maybe_float(payload.get("capture_recall_rate"))
        severe_rate = _maybe_float(payload.get("severe_miss_rate"))
        false_neg_rate = _maybe_float(payload.get("false_negative_reject_rate"))
        tags: list[AdaptiveReflectionTag] = []
        warnings: list[str] = []
        if recall is None and severe_rate is None and false_neg_rate is None:
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE)
            warnings.append("discovery_quality_scorecard_metrics_missing")
        # Heuristic descriptive thresholds (NEVER runtime knobs).
        if recall is not None and recall < 0.40:
            tags.append(AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY)
        if severe_rate is not None and severe_rate >= 0.10:
            tags.append(AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY)
        if false_neg_rate is not None and false_neg_rate >= 0.10:
            tags.append(AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY)

        severity = self._severity_for(tags) if tags else AdaptiveReflectionSeverity.INFO
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=ev.symbol,
            opportunity_id=None,
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=severity.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY
            in tags,
            needs_data_recovery=False,
            needs_rule_review=AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY
            in tags,
            warnings=tuple(sorted(warnings)),
            timestamp=int(ev.timestamp),
        )

    def _reflect_historical_mover_record(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        coverage_status = _maybe_str(payload.get("coverage_status"))
        miss_reasons_raw = payload.get("miss_reasons") or []
        miss_reasons: list[str] = []
        if isinstance(miss_reasons_raw, (list, tuple)):
            for reason in miss_reasons_raw:
                if isinstance(reason, str) and reason:
                    miss_reasons.append(reason)
        tags: list[AdaptiveReflectionTag] = []
        warnings: list[str] = []
        if coverage_status is None:
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE)
            warnings.append("historical_mover_coverage_status_missing")
        elif coverage_status == "MISSED":
            tags.append(AdaptiveReflectionTag.MISSED_TAIL)
            if "ANOMALY_NOT_TRIGGERED" in miss_reasons:
                tags.append(AdaptiveReflectionTag.WEAK_PRE_ANOMALY)
            if "EVICTED_BEFORE_TAIL" in miss_reasons:
                tags.append(AdaptiveReflectionTag.CANDIDATE_EVICTED_BEFORE_TAIL)
            if "DATA_GAP" in miss_reasons or "DATA_UNRELIABLE" in miss_reasons:
                tags.append(AdaptiveReflectionTag.DATA_GAP)
        elif coverage_status == "PARTIALLY_CAPTURED":
            tags.append(AdaptiveReflectionTag.MISSED_TAIL)
        elif coverage_status == "CAPTURED":
            # Captured -> no anomaly tag.
            pass
        elif coverage_status == "EXCLUDED":
            tags.append(AdaptiveReflectionTag.NEEDS_OPERATOR_REVIEW)

        severity = self._severity_for(tags) if tags else AdaptiveReflectionSeverity.INFO
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=_maybe_str(payload.get("symbol")) or ev.symbol,
            opportunity_id=None,
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=severity.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=AdaptiveReflectionTag.MISSED_TAIL in tags,
            needs_data_recovery=AdaptiveReflectionTag.DATA_GAP in tags,
            needs_rule_review=AdaptiveReflectionTag.WEAK_PRE_ANOMALY in tags
            or AdaptiveReflectionTag.CANDIDATE_EVICTED_BEFORE_TAIL in tags,
            warnings=tuple(sorted(warnings)),
            timestamp=int(ev.timestamp),
        )

    def _reflect_historical_mover_backfill(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        # Roll-up backfill report - acknowledge only.
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=ev.symbol,
            opportunity_id=None,
            event_type=ev.event_type.value,
            tags=(),
            severity=AdaptiveReflectionSeverity.INFO.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=False,
            needs_data_recovery=False,
            needs_rule_review=False,
            warnings=(),
            timestamp=int(ev.timestamp),
        )

    def _reflect_mover_capture_path(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        audit_status = _maybe_str(payload.get("audit_status"))
        miss_reasons_raw = payload.get("miss_reasons") or []
        miss_reasons: list[str] = []
        if isinstance(miss_reasons_raw, (list, tuple)):
            for reason in miss_reasons_raw:
                if isinstance(reason, str) and reason:
                    miss_reasons.append(reason)
        tags: list[AdaptiveReflectionTag] = []
        warnings: list[str] = []
        if audit_status is None:
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE)
            warnings.append("mover_capture_audit_status_missing")
        elif audit_status == "MISSED":
            tags.append(AdaptiveReflectionTag.MISSED_TAIL)
            if "EVICTED_BEFORE_TAIL" in miss_reasons:
                tags.append(AdaptiveReflectionTag.CANDIDATE_EVICTED_BEFORE_TAIL)
            if "RISK_REJECTED_BUT_TAIL_HIT" in miss_reasons:
                tags.append(AdaptiveReflectionTag.RISK_REJECTED_THEN_MOVED)
            if "DATA_GAP" in miss_reasons or "DATA_UNRELIABLE" in miss_reasons:
                tags.append(AdaptiveReflectionTag.DATA_GAP)
        elif audit_status == "DEGRADED":
            tags.append(AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY)
        elif audit_status == "PARTIALLY_CAPTURED":
            tags.append(AdaptiveReflectionTag.MISSED_TAIL)

        severity = self._severity_for(tags) if tags else AdaptiveReflectionSeverity.INFO
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=_maybe_str(payload.get("symbol")) or ev.symbol,
            opportunity_id=None,
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=severity.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=AdaptiveReflectionTag.MISSED_TAIL in tags
            or AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY in tags,
            needs_data_recovery=AdaptiveReflectionTag.DATA_GAP in tags,
            needs_rule_review=AdaptiveReflectionTag.CANDIDATE_EVICTED_BEFORE_TAIL
            in tags,
            warnings=tuple(sorted(warnings)),
            timestamp=int(ev.timestamp),
        )

    def _reflect_mover_capture_recall(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        report_status = _maybe_str(payload.get("report_status")) or _maybe_str(
            payload.get("mover_capture_audit_status")
        )
        tags: list[AdaptiveReflectionTag] = []
        warnings: list[str] = []
        if report_status == "DEGRADED":
            tags.append(AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY)
        elif report_status is None:
            warnings.append("mover_capture_recall_report_status_missing")

        severity = self._severity_for(tags) if tags else AdaptiveReflectionSeverity.INFO
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=ev.symbol,
            opportunity_id=None,
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=severity.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY
            in tags,
            needs_data_recovery=False,
            needs_rule_review=AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY
            in tags,
            warnings=tuple(sorted(warnings)),
            timestamp=int(ev.timestamp),
        )

    def _reflect_tail_label_assigned(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        tail_label = _maybe_str(payload.get("tail_label"))
        candidate_stage = _maybe_str(payload.get("candidate_stage"))
        missed = _maybe_bool(payload.get("missed_tail")) or False
        fake = _maybe_bool(payload.get("fake_breakout")) or False
        tags: list[AdaptiveReflectionTag] = []
        warnings: list[str] = []
        if tail_label is None:
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE)
            warnings.append("tail_label_assigned_label_missing")
        else:
            if tail_label == "MISSED_TAIL" or missed:
                tags.append(AdaptiveReflectionTag.MISSED_TAIL)
            if tail_label == "FAKE_BREAKOUT" or fake:
                tags.append(AdaptiveReflectionTag.FAKE_BREAKOUT_DETECTED)
            if candidate_stage in {"LATE", "TOO_LATE"}:
                tags.append(AdaptiveReflectionTag.LATE_DISCOVERY)
            if candidate_stage in {"EARLY", "PROBE"} and tail_label in {
                "RIGHT_TAIL",
                "STRONG_TAIL",
            }:
                tags.append(AdaptiveReflectionTag.EARLY_DISCOVERY)

        severity = self._severity_for(tags) if tags else AdaptiveReflectionSeverity.INFO
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=_maybe_str(payload.get("symbol")) or ev.symbol,
            opportunity_id=_maybe_str(payload.get("opportunity_id")),
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=severity.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=AdaptiveReflectionTag.MISSED_TAIL in tags,
            needs_data_recovery=False,
            needs_rule_review=AdaptiveReflectionTag.FAKE_BREAKOUT_DETECTED
            in tags,
            warnings=tuple(sorted(warnings)),
            timestamp=int(ev.timestamp),
        )

    def _reflect_missed_tail(self, ev: Event) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        tags = [AdaptiveReflectionTag.MISSED_TAIL]
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=_maybe_str(payload.get("symbol")) or ev.symbol,
            opportunity_id=_maybe_str(payload.get("opportunity_id")),
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=AdaptiveReflectionSeverity.MEDIUM.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=True,
            needs_data_recovery=False,
            needs_rule_review=True,
            warnings=(),
            timestamp=int(ev.timestamp),
        )

    def _reflect_fake_breakout(self, ev: Event) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        tags = [AdaptiveReflectionTag.FAKE_BREAKOUT_DETECTED]
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=_maybe_str(payload.get("symbol")) or ev.symbol,
            opportunity_id=_maybe_str(payload.get("opportunity_id")),
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=AdaptiveReflectionSeverity.MEDIUM.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=False,
            needs_data_recovery=False,
            needs_rule_review=True,
            warnings=(),
            timestamp=int(ev.timestamp),
        )

    def _reflect_label_lifecycle(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=_maybe_str(payload.get("symbol")) or ev.symbol,
            opportunity_id=_maybe_str(payload.get("opportunity_id")),
            event_type=ev.event_type.value,
            tags=(),
            severity=AdaptiveReflectionSeverity.INFO.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=False,
            needs_data_recovery=False,
            needs_rule_review=False,
            warnings=(),
            timestamp=int(ev.timestamp),
        )

    def _reflect_strategy_validation(
        self, ev: Event
    ) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        status = _maybe_str(payload.get("status")) or _maybe_str(
            payload.get("validation_status")
        )
        tags: list[AdaptiveReflectionTag] = []
        warnings: list[str] = []
        if status in {"INSUFFICIENT_SAMPLE", "INCONCLUSIVE", "INSUFFICIENT_EVIDENCE"}:
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE)
        severity = self._severity_for(tags) if tags else AdaptiveReflectionSeverity.INFO
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=_maybe_str(payload.get("symbol")) or ev.symbol,
            opportunity_id=_maybe_str(payload.get("opportunity_id")),
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=severity.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=False,
            needs_data_recovery=False,
            needs_rule_review=False,
            warnings=tuple(sorted(warnings)),
            timestamp=int(ev.timestamp),
        )

    def _reflect_paper_alpha(self, ev: Event) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        gate_status = _maybe_str(payload.get("paper_alpha_gate_status")) or _maybe_str(
            payload.get("status")
        )
        tags: list[AdaptiveReflectionTag] = []
        if gate_status in {"INCONCLUSIVE", "INSUFFICIENT_SAMPLE", "INSUFFICIENT_EVIDENCE"}:
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE)
        severity = self._severity_for(tags) if tags else AdaptiveReflectionSeverity.INFO
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=ev.symbol,
            opportunity_id=None,
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=severity.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=False,
            needs_data_recovery=False,
            needs_rule_review=False,
            warnings=(),
            timestamp=int(ev.timestamp),
        )

    def _reflect_regime_cluster(self, ev: Event) -> AdaptiveReflectionCase:
        payload = _payload(ev)
        status = _maybe_str(payload.get("regime_cluster_evidence_status"))
        tags: list[AdaptiveReflectionTag] = []
        if status in {"INSUFFICIENT_SAMPLE", "INSUFFICIENT_EVIDENCE", "INCONCLUSIVE"}:
            tags.append(AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE)
        severity = self._severity_for(tags) if tags else AdaptiveReflectionSeverity.INFO
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=ev.symbol,
            opportunity_id=None,
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=severity.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=False,
            needs_data_recovery=False,
            needs_rule_review=False,
            warnings=(),
            timestamp=int(ev.timestamp),
        )

    # ==================================================================
    # Common helpers
    # ==================================================================
    def _build_unsupported_case(self, ev: Event) -> AdaptiveReflectionCase:
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=ev.symbol,
            opportunity_id=None,
            event_type=ev.event_type.value,
            tags=self._sorted_tags(
                [AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE]
            ),
            severity=AdaptiveReflectionSeverity.UNKNOWN.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=False,
            needs_data_recovery=False,
            needs_rule_review=False,
            warnings=("event_type_not_supported_by_reflection_11c",),
            timestamp=int(ev.timestamp),
        )

    def _build_insufficient_case(
        self,
        ev: Event,
        *,
        warnings: tuple[str, ...] = (),
        opportunity_id: str | None = None,
    ) -> AdaptiveReflectionCase:
        tags = [AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE]
        return AdaptiveReflectionCase(
            case_id=ev.event_id,
            symbol=ev.symbol,
            opportunity_id=opportunity_id,
            event_type=ev.event_type.value,
            tags=self._sorted_tags(tags),
            severity=AdaptiveReflectionSeverity.LOW.value,
            evidence_refs=_evidence_refs_for(ev),
            needs_operator_review=False,
            needs_data_recovery=False,
            needs_rule_review=False,
            warnings=tuple(sorted(warnings)),
            timestamp=int(ev.timestamp),
        )

    @staticmethod
    def _sorted_tags(
        tags: Iterable[AdaptiveReflectionTag],
    ) -> tuple[str, ...]:
        seen: set[str] = set()
        out: list[str] = []
        for tag in tags:
            value = tag.value if isinstance(tag, AdaptiveReflectionTag) else str(tag)
            if value in seen:
                continue
            seen.add(value)
            out.append(value)
        return tuple(sorted(out))

    @staticmethod
    def _severity_for(
        tags: Sequence[AdaptiveReflectionTag],
    ) -> AdaptiveReflectionSeverity:
        if not tags:
            return AdaptiveReflectionSeverity.INFO
        if AdaptiveReflectionTag.SEVERE_MISS in tags:
            return AdaptiveReflectionSeverity.SEVERE
        if (
            AdaptiveReflectionTag.FALSE_NEGATIVE_REJECT in tags
            or AdaptiveReflectionTag.MISSED_TAIL in tags
            or AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY in tags
        ):
            return AdaptiveReflectionSeverity.HIGH
        if (
            AdaptiveReflectionTag.LATE_TOP_CHASE in tags
            or AdaptiveReflectionTag.FAKE_BREAKOUT_DETECTED in tags
            or AdaptiveReflectionTag.CANDIDATE_EVICTED_BEFORE_TAIL in tags
            or AdaptiveReflectionTag.RISK_REJECTED_THEN_MOVED in tags
        ):
            return AdaptiveReflectionSeverity.MEDIUM
        if (
            AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE in tags
            or AdaptiveReflectionTag.INSUFFICIENT_HISTORY in tags
            or AdaptiveReflectionTag.DATA_GAP in tags
            or AdaptiveReflectionTag.WEAK_PRE_ANOMALY in tags
        ):
            return AdaptiveReflectionSeverity.LOW
        return AdaptiveReflectionSeverity.INFO

    @staticmethod
    def _needs_operator_review(
        tags: Sequence[AdaptiveReflectionTag],
    ) -> bool:
        return any(
            tag
            in {
                AdaptiveReflectionTag.SEVERE_MISS,
                AdaptiveReflectionTag.FALSE_NEGATIVE_REJECT,
                AdaptiveReflectionTag.MISSED_TAIL,
                AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY,
                AdaptiveReflectionTag.LATE_TOP_CHASE,
                AdaptiveReflectionTag.NEEDS_OPERATOR_REVIEW,
            }
            for tag in tags
        )


__all__ = [
    "SOURCE_PHASE",
    "SOURCE_MODULE",
    "SCHEMA_VERSION",
    "FORBIDDEN_REFLECTION_PAYLOAD_KEYS",
    "AdaptiveReflectionForbiddenFieldError",
    "AdaptiveReflectionSeverity",
    "AdaptiveReflectionTag",
    "ADAPTIVE_REFLECTION_EVENT_TYPES",
    "AdaptiveReflectionInput",
    "AdaptiveReflectionCase",
    "AdaptiveReflectionSummary",
    "Reflection11CAdaptiveEngine",
]
