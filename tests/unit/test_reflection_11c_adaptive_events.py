"""Phase 11C.1C-C-B-B-B-E-B - Reflection Extension for 11C Adaptive Events v0.

Test surface mandated by the brief:

  1. POST_DISCOVERY_OUTCOME_* -> late_top_chase / early_discovery /
     post_discovery_no_edge tags
  2. REJECT_TO_OUTCOME_* -> false_negative_reject /
     correct_protective_reject tags
  3. SEVERE_MISSED_TAIL_* -> severe_miss / needs_data_recovery tags
  4. DISCOVERY_QUALITY_* DEGRADED -> degraded_discovery_quality tag
  5. HISTORICAL_MOVER_COVERAGE_* missed -> missed_tail tag
  6. missing fields do not crash, output insufficient_evidence
  7. evidence_refs preserved
  8. auto_tuning_allowed=false on every emitted case + summary
  9. forbidden imports: reflection module never imports app.risk /
     app.execution / app.exchanges / app.llm / app.telegram
 10. forbidden fields absent on every emitted payload: never
     buy / sell / long / short / position_size / leverage / stop /
     target / risk_budget / runtime_config_patch
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.core.events import Event, EventType
from app.reflection.adaptive_11c import (
    ADAPTIVE_REFLECTION_EVENT_TYPES,
    FORBIDDEN_REFLECTION_PAYLOAD_KEYS,
    SOURCE_PHASE,
    AdaptiveReflectionCase,
    AdaptiveReflectionForbiddenFieldError,
    AdaptiveReflectionInput,
    AdaptiveReflectionSeverity,
    AdaptiveReflectionSummary,
    AdaptiveReflectionTag,
    Reflection11CAdaptiveEngine,
)


SRC_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "reflection"
    / "adaptive_11c.py"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ev(
    event_type: EventType,
    *,
    timestamp: int = 1_700_000_000_000,
    payload: dict | None = None,
    symbol: str | None = None,
    source_module: str = "test_reflection_11c",
    event_id: str | None = None,
) -> Event:
    kwargs: dict = dict(
        event_type=event_type,
        source_module=source_module,
        symbol=symbol,
        payload=payload or {},
        timestamp=timestamp,
    )
    if event_id is not None:
        kwargs["event_id"] = event_id
    return Event(**kwargs)


def _engine() -> Reflection11CAdaptiveEngine:
    return Reflection11CAdaptiveEngine()


def _walk_keys(payload):
    if isinstance(payload, dict):
        for k, v in payload.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            yield from _walk_keys(item)


# ---------------------------------------------------------------------------
# Forbidden import / field static checks
# ---------------------------------------------------------------------------
FORBIDDEN_MODULE_PREFIXES = (
    "app.risk",
    "app.execution",
    "app.exchanges",
    "app.llm",
    "app.telegram",
)


def test_reflection_module_does_not_import_forbidden_modules() -> None:
    """Phase 11C.1C-C-B-B-B-E-B boundary: reflection extension MUST
    NOT import Risk / Execution / Exchange / LLM / Telegram modules."""
    src = SRC_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if any(
                module == pre or module.startswith(pre + ".")
                for pre in FORBIDDEN_MODULE_PREFIXES
            ):
                bad.append(module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                if any(
                    module == pre or module.startswith(pre + ".")
                    for pre in FORBIDDEN_MODULE_PREFIXES
                ):
                    bad.append(module)
    assert not bad, (
        "reflection extension imports forbidden modules: "
        f"{bad!r}; this violates the Phase 11C.1C-C-B-B-B-E-B boundary."
    )


def test_forbidden_payload_keys_complete() -> None:
    """The brief requires that the forbidden-key set contains at least
    these tokens. Any superset is fine; missing keys are a hard fail."""
    required = {
        "buy",
        "sell",
        "long",
        "short",
        "position_size",
        "leverage",
        "stop",
        "target",
        "risk_budget",
        "runtime_config_patch",
    }
    assert required.issubset(FORBIDDEN_REFLECTION_PAYLOAD_KEYS), (
        FORBIDDEN_REFLECTION_PAYLOAD_KEYS - required
    )


# ---------------------------------------------------------------------------
# Vocabulary tests
# ---------------------------------------------------------------------------
def test_adaptive_reflection_tag_vocabulary_complete() -> None:
    """The 18 brief-listed reflection tags are present on the enum."""
    expected = {
        "early_discovery",
        "late_discovery",
        "missed_tail",
        "severe_miss",
        "candidate_evicted_before_tail",
        "risk_rejected_then_moved",
        "false_negative_reject",
        "correct_protective_reject",
        "weak_pre_anomaly",
        "fake_breakout_detected",
        "late_top_chase",
        "post_discovery_no_edge",
        "data_gap",
        "insufficient_history",
        "degraded_discovery_quality",
        "insufficient_evidence",
        "needs_operator_review",
        "needs_data_recovery",
        "needs_rule_review",
    }
    actual = {t.value for t in AdaptiveReflectionTag}
    assert expected.issubset(actual), expected - actual


def test_adaptive_reflection_event_groups_present() -> None:
    """Every event group the brief calls out is consumable."""
    consumed = {et.value for et in ADAPTIVE_REFLECTION_EVENT_TYPES}
    required = {
        "LABEL_TRACKING_STARTED",
        "LABEL_WINDOW_UPDATED",
        "LABEL_WINDOW_COMPLETED",
        "TAIL_LABEL_ASSIGNED",
        "MISSED_TAIL_DETECTED",
        "FAKE_BREAKOUT_DETECTED",
        "STRATEGY_VALIDATION_SAMPLE_CREATED",
        "PAPER_ALPHA_GATE_EVALUATED",
        "PAPER_ALPHA_REPORT_GENERATED",
        "REGIME_CLUSTER_EVIDENCE_PACK_GENERATED",
        "MOVER_CAPTURE_PATH_AUDITED",
        "HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED",
        "POST_DISCOVERY_OUTCOME_EVALUATED",
        "POST_DISCOVERY_OUTCOME_REPORT_GENERATED",
        "REJECT_TO_OUTCOME_CASE_ATTRIBUTED",
        "FALSE_NEGATIVE_REJECT_DETECTED",
        "CORRECT_PROTECTIVE_REJECT_CONFIRMED",
        "SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED",
        "SEVERE_MISS_ESCALATION_REQUIRED",
        "DISCOVERY_QUALITY_BUCKET_EVALUATED",
        "DISCOVERY_QUALITY_SCORECARD_GENERATED",
    }
    assert required.issubset(consumed), required - consumed


# ---------------------------------------------------------------------------
# 1. POST_DISCOVERY_OUTCOME_* tag rules
# ---------------------------------------------------------------------------
def test_post_discovery_outcome_late_top_chase_tag() -> None:
    ev = _ev(
        EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
        symbol="LATEUSDT",
        payload={
            "opportunity_id": "opp-late",
            "record": {
                "symbol": "LATEUSDT",
                "detection_timing_label": "LATE",
                "outcome_label": "LATE_TOP_CHASE",
            },
            "evidence_refs": ["evt://pdo-late"],
        },
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.LATE_TOP_CHASE.value in case.tags
    assert AdaptiveReflectionTag.LATE_DISCOVERY.value in case.tags
    assert case.symbol == "LATEUSDT"
    assert case.opportunity_id == "opp-late"
    assert "evt://pdo-late" in case.evidence_refs
    assert case.case_id == ev.event_id
    assert case.auto_tuning_allowed is False


def test_post_discovery_outcome_early_discovery_tag() -> None:
    ev = _ev(
        EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
        symbol="EARLYUSDT",
        payload={
            "opportunity_id": "opp-early",
            "record": {
                "symbol": "EARLYUSDT",
                "detection_timing_label": "EARLY",
                "outcome_label": "EARLY_CONTINUATION",
            },
        },
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.EARLY_DISCOVERY.value in case.tags
    # No late_top_chase fired.
    assert AdaptiveReflectionTag.LATE_TOP_CHASE.value not in case.tags
    assert case.auto_tuning_allowed is False


def test_post_discovery_outcome_no_edge_tag() -> None:
    ev = _ev(
        EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
        symbol="NULLUSDT",
        payload={
            "opportunity_id": "opp-null",
            "record": {
                "symbol": "NULLUSDT",
                "detection_timing_label": "MID_MOVE",
                "outcome_label": "NO_CLEAR_EDGE",
            },
        },
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.POST_DISCOVERY_NO_EDGE.value in case.tags


def test_post_discovery_outcome_missed_strong_tail_tag() -> None:
    ev = _ev(
        EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
        symbol="MOONUSDT",
        payload={
            "record": {
                "detection_timing_label": "TOO_LATE",
                "outcome_label": "MISSED_STRONG_TAIL",
            },
        },
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.MISSED_TAIL.value in case.tags


def test_post_discovery_outcome_missing_record_returns_insufficient() -> None:
    ev = _ev(
        EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
        symbol="GHOSTUSDT",
        payload={"opportunity_id": "opp-ghost"},  # no record block
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE.value in case.tags
    assert case.severity == AdaptiveReflectionSeverity.LOW.value
    assert ev.event_id in case.evidence_refs


# ---------------------------------------------------------------------------
# 2. REJECT_TO_OUTCOME_* tag rules
# ---------------------------------------------------------------------------
def test_reject_to_outcome_false_negative_tag() -> None:
    ev = _ev(
        EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
        symbol="FNUSDT",
        payload={
            "opportunity_id": "opp-fn",
            "verdict": "FALSE_NEGATIVE_REJECT",
            "evidence_refs": ["evt://r2o-fn"],
        },
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.FALSE_NEGATIVE_REJECT.value in case.tags
    assert AdaptiveReflectionTag.RISK_REJECTED_THEN_MOVED.value in case.tags
    assert case.needs_operator_review is True
    assert case.needs_rule_review is True
    assert "evt://r2o-fn" in case.evidence_refs


def test_reject_to_outcome_correct_protective_tag() -> None:
    ev = _ev(
        EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
        symbol="OKUSDT",
        payload={
            "opportunity_id": "opp-ok",
            "verdict": "CORRECT_PROTECTIVE_REJECT",
        },
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.CORRECT_PROTECTIVE_REJECT.value in case.tags
    assert case.needs_operator_review is False
    assert case.severity == AdaptiveReflectionSeverity.INFO.value


def test_reject_to_outcome_data_quality_tags_data_gap() -> None:
    ev = _ev(
        EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
        symbol="DQUSDT",
        payload={"verdict": "DATA_QUALITY_REJECT"},
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.DATA_GAP.value in case.tags
    assert AdaptiveReflectionTag.CORRECT_PROTECTIVE_REJECT.value in case.tags
    assert case.needs_data_recovery is True


def test_false_negative_reject_event_carries_correct_tag() -> None:
    """A FALSE_NEGATIVE_REJECT_DETECTED event by itself is a strong
    operator-review signal."""
    ev = _ev(
        EventType.FALSE_NEGATIVE_REJECT_DETECTED,
        symbol="ZAPUSDT",
        payload={"opportunity_id": "opp-zap"},
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.FALSE_NEGATIVE_REJECT.value in case.tags
    assert case.severity == AdaptiveReflectionSeverity.HIGH.value


def test_correct_protective_reject_event_emits_tag() -> None:
    ev = _ev(
        EventType.CORRECT_PROTECTIVE_REJECT_CONFIRMED,
        symbol="OKUSDT",
        payload={"opportunity_id": "opp-ok"},
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.CORRECT_PROTECTIVE_REJECT.value in case.tags
    assert case.needs_operator_review is False


# ---------------------------------------------------------------------------
# 3. SEVERE_MISSED_TAIL_* tag rules
# ---------------------------------------------------------------------------
def test_severe_miss_root_cause_data_gap_needs_data_recovery() -> None:
    ev = _ev(
        EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED,
        symbol="MEMEUSDT",
        payload={
            "opportunity_id": "opp-meme",
            "root_cause": "DATA_GAP",
            "severity": "SEVERE",
            "evidence_refs": ["evt://smt-1"],
        },
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.SEVERE_MISS.value in case.tags
    assert AdaptiveReflectionTag.MISSED_TAIL.value in case.tags
    assert AdaptiveReflectionTag.DATA_GAP.value in case.tags
    assert AdaptiveReflectionTag.NEEDS_DATA_RECOVERY.value in case.tags
    assert case.needs_data_recovery is True
    assert case.needs_operator_review is True
    assert case.severity == AdaptiveReflectionSeverity.SEVERE.value
    assert "evt://smt-1" in case.evidence_refs


def test_severe_miss_root_cause_rule_needs_rule_review() -> None:
    ev = _ev(
        EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED,
        symbol="MEMEUSDT",
        payload={
            "opportunity_id": "opp-meme",
            "root_cause": "ANOMALY_FILTER_TOO_STRICT",
            "severity": "SEVERE",
        },
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.SEVERE_MISS.value in case.tags
    assert AdaptiveReflectionTag.NEEDS_RULE_REVIEW.value in case.tags
    assert case.needs_rule_review is True
    assert case.needs_data_recovery is False


def test_severe_miss_escalation_required_emits_severe_miss_tag() -> None:
    ev = _ev(
        EventType.SEVERE_MISS_ESCALATION_REQUIRED,
        symbol="MOONUSDT",
        payload={"opportunity_id": "opp-moon"},
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.SEVERE_MISS.value in case.tags
    assert AdaptiveReflectionTag.NEEDS_OPERATOR_REVIEW.value in case.tags
    assert case.needs_operator_review is True
    assert case.severity == AdaptiveReflectionSeverity.SEVERE.value


# ---------------------------------------------------------------------------
# 4. DISCOVERY_QUALITY_* DEGRADED tag rule
# ---------------------------------------------------------------------------
def test_discovery_quality_bucket_degraded_tag() -> None:
    ev = _ev(
        EventType.DISCOVERY_QUALITY_BUCKET_EVALUATED,
        payload={
            "quality_bucket": "DEGRADED",
            "evidence_refs": ["evt://dq-deg"],
        },
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY.value in case.tags
    assert AdaptiveReflectionTag.NEEDS_RULE_REVIEW.value in case.tags
    assert case.needs_rule_review is True
    assert case.needs_operator_review is True
    assert "evt://dq-deg" in case.evidence_refs


def test_discovery_quality_scorecard_low_recall_degraded() -> None:
    ev = _ev(
        EventType.DISCOVERY_QUALITY_SCORECARD_GENERATED,
        payload={
            "capture_recall_rate": 0.20,
            "severe_miss_rate": 0.02,
            "false_negative_reject_rate": 0.01,
        },
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.DEGRADED_DISCOVERY_QUALITY.value in case.tags


def test_discovery_quality_scorecard_healthy_no_anomaly() -> None:
    ev = _ev(
        EventType.DISCOVERY_QUALITY_SCORECARD_GENERATED,
        payload={
            "capture_recall_rate": 0.85,
            "severe_miss_rate": 0.01,
            "false_negative_reject_rate": 0.01,
        },
    )
    case = _engine().reflect_event(ev)
    assert case.tags == ()
    assert case.severity == AdaptiveReflectionSeverity.INFO.value


# ---------------------------------------------------------------------------
# 5. HISTORICAL_MOVER_COVERAGE_* missed -> missed_tail
# ---------------------------------------------------------------------------
def test_historical_mover_coverage_missed_emits_missed_tail() -> None:
    ev = _ev(
        EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
        symbol="MEMEUSDT",
        payload={
            "coverage_status": "MISSED",
            "miss_reasons": ["NOT_IN_UNIVERSE", "ANOMALY_NOT_TRIGGERED"],
            "evidence_refs": ["evt://hm-rec-1"],
        },
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.MISSED_TAIL.value in case.tags
    assert AdaptiveReflectionTag.WEAK_PRE_ANOMALY.value in case.tags
    assert case.symbol == "MEMEUSDT"
    assert "evt://hm-rec-1" in case.evidence_refs
    assert case.needs_operator_review is True


def test_historical_mover_coverage_captured_no_missed_tail() -> None:
    ev = _ev(
        EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
        symbol="OKUSDT",
        payload={"coverage_status": "CAPTURED", "miss_reasons": []},
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.MISSED_TAIL.value not in case.tags


def test_mover_capture_path_missed_with_eviction() -> None:
    ev = _ev(
        EventType.MOVER_CAPTURE_PATH_AUDITED,
        symbol="EVICTUSDT",
        payload={
            "audit_status": "MISSED",
            "miss_reasons": ["EVICTED_BEFORE_TAIL", "RISK_REJECTED_BUT_TAIL_HIT"],
        },
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.MISSED_TAIL.value in case.tags
    assert AdaptiveReflectionTag.CANDIDATE_EVICTED_BEFORE_TAIL.value in case.tags
    assert AdaptiveReflectionTag.RISK_REJECTED_THEN_MOVED.value in case.tags


# ---------------------------------------------------------------------------
# 6. Missing fields do not crash, output insufficient_evidence
# ---------------------------------------------------------------------------
def test_missing_fields_do_not_crash_for_every_supported_event() -> None:
    """Every supported event with no payload must still produce a case
    (status / tags reflect insufficient evidence) and never raise."""
    base = 1_700_000_000_000
    events = [
        _ev(et, timestamp=base + i, payload={})
        for i, et in enumerate(ADAPTIVE_REFLECTION_EVENT_TYPES)
    ]
    summary = _engine().reflect_events(events)
    assert summary.total_input_event_count == len(events)
    assert summary.total_case_count == len(events)
    # Every case must be a valid AdaptiveReflectionCase (no exception).
    assert all(isinstance(c, AdaptiveReflectionCase) for c in summary.cases)


def test_post_discovery_missing_record_yields_insufficient_evidence_tag() -> None:
    ev = _ev(
        EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
        symbol="GHOSTUSDT",
        payload={"opportunity_id": "g"},
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE.value in case.tags


def test_reject_attribution_missing_verdict_yields_insufficient_evidence() -> None:
    ev = _ev(
        EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
        symbol="X",
        payload={"opportunity_id": "x"},
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE.value in case.tags


def test_unknown_verdict_yields_insufficient_evidence_with_warning() -> None:
    ev = _ev(
        EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
        symbol="X",
        payload={"verdict": "MADE_UP_LABEL"},
    )
    case = _engine().reflect_event(ev)
    assert AdaptiveReflectionTag.INSUFFICIENT_EVIDENCE.value in case.tags
    assert any("verdict_unrecognised" in w for w in case.warnings)


# ---------------------------------------------------------------------------
# 7. evidence_refs preserved (event_id always present)
# ---------------------------------------------------------------------------
def test_evidence_refs_preserved_with_event_id_fallback() -> None:
    """Even when the source payload omits evidence_refs, the case must
    still carry the source event_id so provenance is never lost."""
    ev = _ev(
        EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED,
        payload={"root_cause": "DATA_GAP", "severity": "SEVERE"},
    )
    case = _engine().reflect_event(ev)
    assert ev.event_id in case.evidence_refs


def test_evidence_refs_preserved_from_payload_top_level() -> None:
    refs = ["evt://a", "evt://b", "evt://c"]
    ev = _ev(
        EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
        payload={
            "record": {"detection_timing_label": "EARLY"},
            "evidence_refs": refs,
        },
    )
    case = _engine().reflect_event(ev)
    for ref in refs:
        assert ref in case.evidence_refs
    # event_id always appended for provenance.
    assert ev.event_id in case.evidence_refs


def test_evidence_refs_preserved_from_record_block() -> None:
    ev = _ev(
        EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
        payload={
            "record": {
                "detection_timing_label": "LATE",
                "outcome_label": "LATE_TOP_CHASE",
                "evidence_refs": ["evt://nested"],
            },
        },
    )
    case = _engine().reflect_event(ev)
    assert "evt://nested" in case.evidence_refs


# ---------------------------------------------------------------------------
# 8. auto_tuning_allowed=false on every emitted case + summary
# ---------------------------------------------------------------------------
def test_auto_tuning_allowed_false_on_every_case() -> None:
    """auto_tuning_allowed MUST be False on every emitted case payload,
    regardless of how the case was constructed."""
    base = 1_700_000_000_000
    events = [
        _ev(et, timestamp=base + i, payload={"verdict": "FALSE_NEGATIVE_REJECT"})
        if et is EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED
        else _ev(et, timestamp=base + i, payload={})
        for i, et in enumerate(ADAPTIVE_REFLECTION_EVENT_TYPES)
    ]
    summary = _engine().reflect_events(events)
    payload = summary.to_payload()
    assert payload["auto_tuning_allowed"] is False
    for case_payload in payload["cases"]:
        assert case_payload["auto_tuning_allowed"] is False


def test_auto_tuning_allowed_false_unconstructable() -> None:
    """The dataclass field default for auto_tuning_allowed is False."""
    case = AdaptiveReflectionCase(
        case_id="c-1",
        symbol="X",
        opportunity_id="o-1",
        event_type="POST_DISCOVERY_OUTCOME_EVALUATED",
        tags=(),
        severity=AdaptiveReflectionSeverity.INFO.value,
        evidence_refs=("evt://x",),
        needs_operator_review=False,
        needs_data_recovery=False,
        needs_rule_review=False,
    )
    # Default must be False - hard-pinned.
    assert case.auto_tuning_allowed is False
    # to_payload() always emits False even if the field was overridden.
    overridden = AdaptiveReflectionCase(
        case_id="c-2",
        symbol="X",
        opportunity_id="o-2",
        event_type="POST_DISCOVERY_OUTCOME_EVALUATED",
        tags=(),
        severity=AdaptiveReflectionSeverity.INFO.value,
        evidence_refs=("evt://x",),
        needs_operator_review=False,
        needs_data_recovery=False,
        needs_rule_review=False,
        auto_tuning_allowed=True,  # malicious caller
    )
    assert overridden.to_payload()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# 10. Forbidden fields absent on every emitted payload
# ---------------------------------------------------------------------------
def test_no_forbidden_keys_in_any_emitted_payload() -> None:
    """No emitted case / summary payload may carry a forbidden key."""
    base = 1_700_000_000_000
    events = [
        _ev(
            EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
            symbol="X",
            timestamp=base,
            payload={
                "record": {
                    "detection_timing_label": "LATE",
                    "outcome_label": "LATE_TOP_CHASE",
                    "evidence_refs": ["evt://x"],
                },
            },
        ),
        _ev(
            EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
            timestamp=base + 1,
            payload={"verdict": "FALSE_NEGATIVE_REJECT"},
        ),
        _ev(
            EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED,
            timestamp=base + 2,
            payload={"root_cause": "DATA_GAP", "severity": "SEVERE"},
        ),
        _ev(
            EventType.DISCOVERY_QUALITY_BUCKET_EVALUATED,
            timestamp=base + 3,
            payload={"quality_bucket": "DEGRADED"},
        ),
    ]
    summary = _engine().reflect_events(events)
    payload = summary.to_payload()
    bad = [
        k for k in _walk_keys(payload) if k in FORBIDDEN_REFLECTION_PAYLOAD_KEYS
    ]
    assert not bad, bad


def test_constructing_case_with_forbidden_key_in_warnings_does_not_smuggle() -> None:
    """The dataclass payload schema is fixed; warnings is a list of
    plain strings - it can never become a forbidden-key dict."""
    case = AdaptiveReflectionCase(
        case_id="c",
        symbol=None,
        opportunity_id=None,
        event_type="POST_DISCOVERY_OUTCOME_EVALUATED",
        tags=(),
        severity=AdaptiveReflectionSeverity.INFO.value,
        evidence_refs=(),
        needs_operator_review=False,
        needs_data_recovery=False,
        needs_rule_review=False,
        warnings=("buy", "sell", "leverage"),  # strings, NOT keys
    )
    payload = case.to_payload()
    # Warnings are values, not keys - the forbidden-key guard checks keys.
    assert payload["warnings"] == ["buy", "sell", "leverage"]


def test_forbidden_key_guard_rejects_smuggled_payload() -> None:
    """Direct guard test: if a future regression smuggles a forbidden
    key into a manually-built payload, the recursive guard fires."""
    from app.reflection.adaptive_11c import _assert_no_forbidden_keys  # noqa

    smuggled = {"foo": {"bar": [{"leverage": 10}]}}
    with pytest.raises(AdaptiveReflectionForbiddenFieldError):
        _assert_no_forbidden_keys(smuggled, context="unit_test")


# ---------------------------------------------------------------------------
# Summary-level tests
# ---------------------------------------------------------------------------
def test_summary_counts_are_deterministic() -> None:
    base = 1_700_000_000_000
    events = [
        _ev(
            EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
            symbol="A",
            timestamp=base,
            payload={"coverage_status": "MISSED", "miss_reasons": []},
        ),
        _ev(
            EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
            symbol="B",
            timestamp=base + 1,
            payload={"coverage_status": "MISSED", "miss_reasons": []},
        ),
        _ev(
            EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED,
            symbol="A",
            timestamp=base + 2,
            payload={"root_cause": "DATA_GAP", "severity": "SEVERE"},
        ),
    ]
    summary = _engine().reflect_events(events)
    assert summary.total_input_event_count == 3
    assert summary.total_case_count == 3
    assert summary.skipped_event_count == 0
    assert summary.tag_counts.get("missed_tail", 0) >= 3
    assert summary.tag_counts.get("severe_miss", 0) == 1
    assert summary.severity_counts.get("severe", 0) == 1
    assert summary.needs_operator_review_count >= 1
    assert summary.needs_data_recovery_count >= 1
    assert summary.auto_tuning_allowed is False


def test_summary_skips_unsupported_events() -> None:
    base = 1_700_000_000_000
    events = [
        _ev(EventType.MARKET_SNAPSHOT, timestamp=base, payload={}),
        _ev(
            EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
            timestamp=base + 1,
            payload={"record": {"detection_timing_label": "EARLY"}},
        ),
    ]
    summary = _engine().reflect_events(events)
    assert summary.total_input_event_count == 2
    assert summary.total_case_count == 1
    assert summary.skipped_event_count == 1


def test_reflection_is_deterministic_under_input_reordering() -> None:
    base = 1_700_000_000_000
    e1 = _ev(
        EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
        symbol="A",
        timestamp=base,
        payload={"coverage_status": "MISSED", "miss_reasons": []},
        event_id="11111111-1111-1111-1111-111111111111",
    )
    e2 = _ev(
        EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
        symbol="B",
        timestamp=base,
        payload={"coverage_status": "CAPTURED", "miss_reasons": []},
        event_id="22222222-2222-2222-2222-222222222222",
    )
    e3 = _ev(
        EventType.SEVERE_MISS_ESCALATION_REQUIRED,
        timestamp=base + 5,
        payload={"opportunity_id": "z"},
        event_id="33333333-3333-3333-3333-333333333333",
    )
    forward = _engine().reflect_events([e1, e2, e3]).to_payload()
    reverse = _engine().reflect_events([e3, e2, e1]).to_payload()
    assert forward == reverse


# ---------------------------------------------------------------------------
# AdaptiveReflectionInput acceptance
# ---------------------------------------------------------------------------
def test_engine_accepts_adaptive_reflection_input() -> None:
    inp = AdaptiveReflectionInput(
        events=(
            _ev(
                EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
                payload={
                    "record": {
                        "detection_timing_label": "EARLY",
                        "outcome_label": "EARLY_CONTINUATION",
                    }
                },
            ),
        )
    )
    summary = _engine().reflect_events(inp)
    assert summary.total_case_count == 1
    assert (
        AdaptiveReflectionTag.EARLY_DISCOVERY.value
        in summary.cases[0].tags
    )


# ---------------------------------------------------------------------------
# Source / module identity
# ---------------------------------------------------------------------------
def test_source_phase_pinned() -> None:
    assert SOURCE_PHASE == "phase_11c_1c_c_b_b_b_e_b"


def test_case_payload_carries_source_phase() -> None:
    ev = _ev(
        EventType.MISSED_TAIL_DETECTED,
        symbol="X",
        payload={"opportunity_id": "x"},
    )
    case = _engine().reflect_event(ev)
    payload = case.to_payload()
    assert payload["source_phase"] == "phase_11c_1c_c_b_b_b_e_b"
    assert payload["source_module"] == "reflection_11c_adaptive_engine"
    assert payload["reflection_object"] == "AdaptiveReflectionCase"


def test_summary_payload_carries_source_phase_and_object_marker() -> None:
    summary = _engine().reflect_events([])
    payload = summary.to_payload()
    assert payload["source_phase"] == "phase_11c_1c_c_b_b_b_e_b"
    assert payload["reflection_object"] == "AdaptiveReflectionSummary"
    assert payload["total_input_event_count"] == 0
    assert payload["total_case_count"] == 0
    assert payload["auto_tuning_allowed"] is False
