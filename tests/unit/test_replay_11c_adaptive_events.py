"""Phase 11C.1C-C-B-B-B-E-A - Replay Extension for 11C Adaptive Events v0.

Test surface required by the brief:

  1. HISTORICAL_MOVER_COVERAGE_* replay
  2. POST_DISCOVERY_OUTCOME_* replay
  3. REJECT_TO_OUTCOME_* replay
  4. SEVERE_MISSED_TAIL_* replay
  5. DISCOVERY_QUALITY_* replay
  6. LABEL_* / TAIL_LABEL_* replay
  7. missing fields do not crash, output partial / degraded
  8. replay count == input event count for the supported groups
  9. forbidden imports: replay module never imports app.risk /
     app.execution / app.exchanges / app.llm / app.telegram
 10. forbidden fields absent: replay payload never contains
     buy / sell / long / short / position_size / leverage / stop /
     target / risk_budget / runtime_config_patch
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.core.events import Event, EventType
from app.replay.adaptive_replay_11c import (
    ADAPTIVE_REPLAY_EVENT_TYPES,
    AdaptiveEventReplayExtension,
    AdaptiveReplayBundle,
    CANDIDATE_LIFECYCLE_EVENT_TYPES,
    DISCOVERY_QUALITY_EVENT_TYPES,
    DISCOVERY_TIMELINE_EVENT_TYPES,
    FORBIDDEN_REPLAY_PAYLOAD_KEYS,
    MOVER_COVERAGE_EVENT_TYPES,
    POST_DISCOVERY_OUTCOME_EVENT_TYPES,
    REJECT_ATTRIBUTION_EVENT_TYPES,
    SEVERE_MISS_EVENT_TYPES,
    SOURCE_MODULE,
    SOURCE_PHASE,
    TAIL_OUTCOME_EVENT_TYPES,
    ReplayCandidateLifecycle,
    ReplayDiscoveryQualityCase,
    ReplayDiscoveryTimeline,
    ReplayMoverCoverageCase,
    ReplayPostDiscoveryOutcomeCase,
    ReplayRejectAttributionCase,
    ReplaySevereMissCase,
    ReplayStatus,
    ReplayTailOutcome,
    build_candidate_lifecycles,
    build_discovery_quality_cases,
    build_discovery_timelines,
    build_mover_coverage_cases,
    build_post_discovery_outcome_cases,
    build_reject_attribution_cases,
    build_severe_miss_cases,
    build_tail_outcomes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
SRC_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "replay"
    / "adaptive_replay_11c.py"
)


def _ev(
    event_type: EventType,
    *,
    timestamp: int,
    payload: dict | None = None,
    symbol: str | None = None,
    source_module: str = "test_phase_11c_e_a",
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


def _build_extension() -> AdaptiveEventReplayExtension:
    """A bare extension that only uses ``replay_from_events`` so we
    don't need a sqlite repo fixture."""

    class _NullRepo:
        def list_events(self, **_kwargs):  # pragma: no cover - never used
            return []

    return AdaptiveEventReplayExtension(event_repo=_NullRepo())


# ---------------------------------------------------------------------------
# Forbidden-import / forbidden-field static checks
# ---------------------------------------------------------------------------
FORBIDDEN_MODULE_PREFIXES = (
    "app.risk",
    "app.execution",
    "app.exchanges",
    "app.llm",
    "app.telegram",
)


def test_replay_module_does_not_import_forbidden_modules() -> None:
    """Phase 11C.1C-C-B-B-B-E-A boundary: replay extension must NEVER
    import Risk / Execution / Exchange / LLM / Telegram modules."""
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
        "replay extension imports forbidden modules: "
        f"{bad!r}; this violates the Phase 11C.1C-C-B-B-B-E-A boundary."
    )


def test_replay_module_has_no_forbidden_strings() -> None:
    """Static check: the replay source MUST NOT contain trade-decision
    or runtime-patch strings as identifiers / dictionary keys.

    The check is conservative - it scans the source for word-boundary
    matches of forbidden tokens in code (not in comments / docstrings)
    and ignores the constant ``FORBIDDEN_REPLAY_PAYLOAD_KEYS`` literal
    set itself plus the assertion message in
    ``_assert_no_forbidden_keys``.
    """
    src = SRC_PATH.read_text(encoding="utf-8")
    # Strip the forbidden-set definition + the violation message so we
    # only check the *replay output surface*.
    cleaned = re.sub(
        r"FORBIDDEN_REPLAY_PAYLOAD_KEYS:\s*frozenset\[str\][\s\S]+?\)\n",
        "FORBIDDEN_REPLAY_PAYLOAD_KEYS = frozenset()\n",
        src,
        count=1,
    )
    cleaned = cleaned.replace(
        'replay extension produced a forbidden payload key',
        '<message>',
    )
    forbidden_substrings = (
        "create_order",
        "cancel_order",
        "place_order",
        "set_leverage",
        "submit_order",
        "runtime_config_patch=",
        "leverage=",
        "position_size=",
    )
    found = [s for s in forbidden_substrings if s in cleaned]
    assert not found, (
        f"replay source contains forbidden trade-decision strings: {found!r}"
    )


# ---------------------------------------------------------------------------
# Vocabulary tests
# ---------------------------------------------------------------------------
def test_event_type_groups_are_complete() -> None:
    assert {et.value for et in DISCOVERY_TIMELINE_EVENT_TYPES} == {
        "MARKET_REGIME_ASSESSED",
        "CANDIDATE_STAGE_CLASSIFIED",
        "OPPORTUNITY_SCORED",
        "STRATEGY_MODE_SELECTED",
        "CLUSTER_CONTEXT_ATTACHED",
        "LABEL_QUEUE_ENQUEUED",
    }
    assert {et.value for et in CANDIDATE_LIFECYCLE_EVENT_TYPES} == {
        "LABEL_TRACKING_STARTED",
        "LABEL_WINDOW_UPDATED",
        "LABEL_WINDOW_COMPLETED",
    }
    assert {et.value for et in TAIL_OUTCOME_EVENT_TYPES} == {
        "TAIL_LABEL_ASSIGNED",
        "MISSED_TAIL_DETECTED",
        "FAKE_BREAKOUT_DETECTED",
    }
    assert {et.value for et in MOVER_COVERAGE_EVENT_TYPES} >= {
        "MOVER_CAPTURE_PATH_AUDITED",
        "MOVER_CAPTURE_RECALL_AUDIT_GENERATED",
        "HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED",
        "HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED",
    }
    assert {et.value for et in POST_DISCOVERY_OUTCOME_EVENT_TYPES} == {
        "POST_DISCOVERY_OUTCOME_EVALUATED",
        "POST_DISCOVERY_OUTCOME_REPORT_GENERATED",
    }
    assert {et.value for et in REJECT_ATTRIBUTION_EVENT_TYPES} == {
        "REJECT_TO_OUTCOME_CASE_ATTRIBUTED",
        "REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED",
        "FALSE_NEGATIVE_REJECT_DETECTED",
        "CORRECT_PROTECTIVE_REJECT_CONFIRMED",
    }
    assert {et.value for et in SEVERE_MISS_EVENT_TYPES} == {
        "SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED",
        "SEVERE_MISSED_TAIL_TRIAGE_GENERATED",
        "SEVERE_MISS_ESCALATION_REQUIRED",
    }
    assert {et.value for et in DISCOVERY_QUALITY_EVENT_TYPES} == {
        "DISCOVERY_QUALITY_BUCKET_EVALUATED",
        "DISCOVERY_QUALITY_SCORECARD_GENERATED",
    }


def test_forbidden_payload_keys_complete() -> None:
    """Mandatory minimum set required by the Phase 11C.1C-C-B-B-B-E-A
    brief. Any superset is fine; missing keys is a hard fail."""
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
    assert required.issubset(FORBIDDEN_REPLAY_PAYLOAD_KEYS), (
        FORBIDDEN_REPLAY_PAYLOAD_KEYS - required
    )


# ---------------------------------------------------------------------------
# 6. LABEL / TAIL_LABEL replay
# ---------------------------------------------------------------------------
def test_label_lifecycle_full_chain_is_ok() -> None:
    """A full LABEL_TRACKING_STARTED -> WINDOW_UPDATED ->
    WINDOW_COMPLETED chain replays to status=ok with a tail outcome."""
    opp_id = "opp-FOO-1"
    scan = "scan-1"
    base = 1_700_000_000_000
    started = _ev(
        EventType.LABEL_TRACKING_STARTED,
        symbol="FOOUSDT",
        timestamp=base,
        payload={
            "opportunity_id": opp_id,
            "scan_batch_id": scan,
            "label_tracking_record": {
                "tracking_id": "trk-1",
                "status": "pending",
                "final_tail_label": None,
            },
        },
    )
    updated = _ev(
        EventType.LABEL_WINDOW_UPDATED,
        symbol="FOOUSDT",
        timestamp=base + 100,
        payload={
            "opportunity_id": opp_id,
            "scan_batch_id": scan,
            "window": {"window_name": "4h"},
        },
    )
    completed = _ev(
        EventType.LABEL_WINDOW_COMPLETED,
        symbol="FOOUSDT",
        timestamp=base + 200,
        payload={
            "opportunity_id": opp_id,
            "scan_batch_id": scan,
            "window": {"window_name": "4h"},
        },
    )
    tail = _ev(
        EventType.TAIL_LABEL_ASSIGNED,
        symbol="FOOUSDT",
        timestamp=base + 200,
        payload={
            "opportunity_id": opp_id,
            "scan_batch_id": scan,
            "window_name": "4h",
            "tail_label": "RIGHT_TAIL",
            "mfe_pct": 5.0,
            "mae_pct": -1.0,
            "candidate_stage": "EARLY",
            "strategy_mode": "MOMENTUM",
        },
    )
    bundle = _build_extension().replay_from_events(
        [started, updated, completed, tail]
    )
    assert len(bundle.candidate_lifecycles) == 1
    lc = bundle.candidate_lifecycles[0]
    assert lc.status == ReplayStatus.OK
    assert lc.tracking_id == "trk-1"
    assert "4h" in lc.completed_window_names
    assert lc.update_count == 1
    assert started.event_id in lc.event_ids

    assert len(bundle.tail_outcomes) == 1
    out = bundle.tail_outcomes[0]
    assert out.status == ReplayStatus.OK
    assert out.tail_label == "RIGHT_TAIL"
    assert out.window_name == "4h"
    assert out.candidate_stage == "EARLY"
    assert out.opportunity_id == opp_id
    assert out.tail_event_id == tail.event_id
    assert not out.missed_tail
    assert not out.fake_breakout


def test_tail_outcome_with_missed_and_fake_flags() -> None:
    base = 1_700_000_000_000
    tail = _ev(
        EventType.TAIL_LABEL_ASSIGNED,
        symbol="BARUSDT",
        timestamp=base,
        payload={
            "opportunity_id": "opp-BAR-1",
            "window_name": "1h",
            "tail_label": "MISSED_TAIL",
            "mfe_pct": 1.5,
            "mae_pct": -0.5,
            "missed_tail": True,
            "fake_breakout": False,
        },
    )
    missed = _ev(
        EventType.MISSED_TAIL_DETECTED,
        symbol="BARUSDT",
        timestamp=base,
        payload={
            "opportunity_id": "opp-BAR-1",
            "window_name": "1h",
            "tail_label": "MISSED_TAIL",
            "mfe_pct": 1.5,
            "candidate_stage": "PROBE",
            "strategy_mode": "RECLAIM",
        },
    )
    fake = _ev(
        EventType.FAKE_BREAKOUT_DETECTED,
        symbol="BARUSDT",
        timestamp=base,
        payload={
            "opportunity_id": "opp-BAR-1",
            "window_name": "1h",
            "tail_label": "FAKE_BREAKOUT",
        },
    )
    bundle = _build_extension().replay_from_events([tail, missed, fake])
    assert len(bundle.tail_outcomes) == 1
    out = bundle.tail_outcomes[0]
    assert out.status == ReplayStatus.OK
    assert out.missed_tail is True
    assert out.fake_breakout is True
    assert out.missed_event_id == missed.event_id
    assert out.fake_breakout_event_id == fake.event_id


# ---------------------------------------------------------------------------
# 1. HISTORICAL_MOVER_COVERAGE_* replay
# ---------------------------------------------------------------------------
def test_historical_mover_coverage_replay_full() -> None:
    base = 1_700_000_000_000
    record = _ev(
        EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
        symbol="MEMEUSDT",
        timestamp=base,
        payload={
            "coverage_status": "MISSED",
            "miss_reasons": ["NOT_IN_UNIVERSE", "ANOMALY_NOT_TRIGGERED"],
            "evidence_refs": ["evt://hm-rec-1"],
        },
    )
    parent = _ev(
        EventType.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED,
        timestamp=base + 50,
        payload={
            "backfill_status": "GENERATED",
            "captured_top_mover_count": 1,
        },
    )
    bundle = _build_extension().replay_from_events([record, parent])
    assert len(bundle.mover_coverage_cases) == 1
    case = bundle.mover_coverage_cases[0]
    assert case.status == ReplayStatus.OK
    assert case.symbol == "MEMEUSDT"
    assert case.audit_status == "MISSED"
    assert "NOT_IN_UNIVERSE" in case.miss_reasons
    assert case.parent_event_id == parent.event_id
    assert case.parent_event_type == (
        EventType.HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED.value
    )
    assert "evt://hm-rec-1" in case.evidence_refs


def test_mover_capture_path_replay_with_audit_metrics() -> None:
    base = 1_700_000_000_000
    record = _ev(
        EventType.MOVER_CAPTURE_PATH_AUDITED,
        symbol="ABCUSDT",
        timestamp=base,
        payload={
            "audit_status": "CAPTURED",
            "miss_reasons": [],
            "rank": 3,
            "capture_recall_score": 0.85,
            "in_eligible_universe": True,
            "risk_rejected": False,
            "has_completed_tail_label": True,
            "has_strategy_validation_sample": True,
            "first_seen_latency_seconds": 12.5,
        },
    )
    parent = _ev(
        EventType.MOVER_CAPTURE_RECALL_AUDIT_GENERATED,
        timestamp=base + 100,
        payload={"report_status": "OK", "evidence_refs": ["evt://mc-rep-1"]},
    )
    bundle = _build_extension().replay_from_events([record, parent])
    case = bundle.mover_coverage_cases[0]
    assert case.status == ReplayStatus.OK
    assert case.audit_status == "CAPTURED"
    assert case.rank == 3
    assert case.capture_recall_score == pytest.approx(0.85)
    assert case.in_eligible_universe is True
    assert case.has_completed_tail_label is True


def test_historical_mover_record_without_parent_is_degraded() -> None:
    base = 1_700_000_000_000
    record = _ev(
        EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
        symbol="LONELYUSDT",
        timestamp=base,
        payload={
            "coverage_status": "CAPTURED",
            "miss_reason": None,
        },
    )
    bundle = _build_extension().replay_from_events([record])
    case = bundle.mover_coverage_cases[0]
    assert case.status == ReplayStatus.DEGRADED
    assert case.parent_event_id is None


# ---------------------------------------------------------------------------
# 2. POST_DISCOVERY_OUTCOME_* replay
# ---------------------------------------------------------------------------
def test_post_discovery_outcome_replay_full() -> None:
    base = 1_700_000_000_000
    eval_ev = _ev(
        EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
        symbol="RAVEUSDT",
        timestamp=base,
        payload={
            "reference_window": "60d",
            "record": {
                "symbol": "RAVEUSDT",
                "detection_timing_label": "LATE_DISCOVERY",
                "outcome_label": "MISSED_STRONG_TAIL",
                "remaining_upside_to_peak_pct": 12.4,
                "post_seen_drawdown_pct": -3.1,
                "mfe_pct": 9.5,
                "mae_pct": -1.2,
                "time_to_peak_seconds": 3600.0,
                "distance_to_prior_high_pct": 1.5,
            },
            "evidence_refs": ["evt://pdo-1"],
        },
    )
    rep_ev = _ev(
        EventType.POST_DISCOVERY_OUTCOME_REPORT_GENERATED,
        timestamp=base + 50,
        payload={"reference_window": "60d"},
    )
    bundle = _build_extension().replay_from_events([eval_ev, rep_ev])
    assert len(bundle.post_discovery_outcome_cases) == 1
    case = bundle.post_discovery_outcome_cases[0]
    assert case.status == ReplayStatus.OK
    assert case.detection_timing_label == "LATE_DISCOVERY"
    assert case.outcome_label == "MISSED_STRONG_TAIL"
    assert case.symbol == "RAVEUSDT"
    assert case.parent_event_id == rep_ev.event_id
    assert "evt://pdo-1" in case.evidence_refs


def test_post_discovery_outcome_missing_record_is_partial() -> None:
    """A POST_DISCOVERY_OUTCOME_EVALUATED with no ``record`` block must
    NOT crash; the case is flagged ``partial``."""
    base = 1_700_000_000_000
    eval_ev = _ev(
        EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
        symbol="GHOSTUSDT",
        timestamp=base,
        payload={"reference_window": "60d"},  # no record
    )
    bundle = _build_extension().replay_from_events([eval_ev])
    case = bundle.post_discovery_outcome_cases[0]
    assert case.status == ReplayStatus.PARTIAL
    assert case.outcome_label is None
    assert case.symbol == "GHOSTUSDT"


# ---------------------------------------------------------------------------
# 3. REJECT_TO_OUTCOME_* replay
# ---------------------------------------------------------------------------
def test_reject_to_outcome_replay_false_negative() -> None:
    base = 1_700_000_000_000
    case_ev = _ev(
        EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
        symbol="ZAPUSDT",
        timestamp=base,
        payload={
            "opportunity_id": "opp-ZAP-1",
            "verdict": "FALSE_NEGATIVE_REJECT",
            "primary_reason": "RISK_REJECTED_BUT_TAIL_HIT",
            "secondary_reasons": ["LATE_DISCOVERY"],
            "auto_tuning_allowed": False,
            "evidence_refs": ["evt://r2o-1"],
        },
    )
    fn_ev = _ev(
        EventType.FALSE_NEGATIVE_REJECT_DETECTED,
        symbol="ZAPUSDT",
        timestamp=base,
        payload={"opportunity_id": "opp-ZAP-1"},
    )
    parent_ev = _ev(
        EventType.REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED,
        timestamp=base + 10,
        payload={"verdict_summary": {"FALSE_NEGATIVE_REJECT": 1}},
    )
    bundle = _build_extension().replay_from_events(
        [case_ev, fn_ev, parent_ev]
    )
    case = bundle.reject_attribution_cases[0]
    assert case.status == ReplayStatus.OK
    assert case.verdict == "FALSE_NEGATIVE_REJECT"
    assert case.is_false_negative is True
    assert case.is_correct_protective is False
    assert case.false_negative_event_id == fn_ev.event_id
    assert case.parent_event_id == parent_ev.event_id
    assert case.auto_tuning_allowed is False


def test_reject_to_outcome_replay_correct_protective() -> None:
    base = 1_700_000_000_000
    case_ev = _ev(
        EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
        symbol="OKUSDT",
        timestamp=base,
        payload={
            "opportunity_id": "opp-OK-1",
            "verdict": "CORRECT_PROTECTIVE_REJECT",
            "primary_reason": "TAIL_NEVER_HIT",
            "auto_tuning_allowed": False,
        },
    )
    cp_ev = _ev(
        EventType.CORRECT_PROTECTIVE_REJECT_CONFIRMED,
        symbol="OKUSDT",
        timestamp=base,
        payload={"opportunity_id": "opp-OK-1"},
    )
    bundle = _build_extension().replay_from_events([case_ev, cp_ev])
    case = bundle.reject_attribution_cases[0]
    # No parent -> degraded; still useful, no crash.
    assert case.status == ReplayStatus.DEGRADED
    assert case.is_correct_protective is True
    assert case.correct_protective_event_id == cp_ev.event_id


# ---------------------------------------------------------------------------
# 4. SEVERE_MISSED_TAIL_* replay
# ---------------------------------------------------------------------------
def test_severe_miss_replay_full() -> None:
    base = 1_700_000_000_000
    record = _ev(
        EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED,
        symbol="MOONUSDT",
        timestamp=base,
        payload={
            "opportunity_id": "opp-MOON-1",
            "root_cause": "ANOMALY_FILTER_TOO_STRICT",
            "severity": "SEVERE",
            "auto_tuning_allowed": False,
            "evidence_refs": ["evt://smt-1"],
        },
    )
    esc_ev = _ev(
        EventType.SEVERE_MISS_ESCALATION_REQUIRED,
        symbol="MOONUSDT",
        timestamp=base,
        payload={"opportunity_id": "opp-MOON-1"},
    )
    parent_ev = _ev(
        EventType.SEVERE_MISSED_TAIL_TRIAGE_GENERATED,
        timestamp=base + 5,
        payload={"summary": {"severity_distribution": {"SEVERE": 1}}},
    )
    bundle = _build_extension().replay_from_events(
        [record, esc_ev, parent_ev]
    )
    case = bundle.severe_miss_cases[0]
    assert case.status == ReplayStatus.OK
    assert case.root_cause == "ANOMALY_FILTER_TOO_STRICT"
    assert case.severity == "SEVERE"
    assert case.requires_escalation is True
    assert case.escalation_event_id == esc_ev.event_id
    assert case.parent_event_id == parent_ev.event_id
    assert case.auto_tuning_allowed is False


# ---------------------------------------------------------------------------
# 5. DISCOVERY_QUALITY_* replay
# ---------------------------------------------------------------------------
def test_discovery_quality_replay_pairs_bucket_with_scorecard() -> None:
    base = 1_700_000_000_000
    bucket = _ev(
        EventType.DISCOVERY_QUALITY_BUCKET_EVALUATED,
        timestamp=base,
        payload={
            "quality_bucket": "GOLDEN_TAIL",
            "auto_tuning_allowed": False,
            "evidence_refs": ["evt://dq-1"],
        },
    )
    scorecard = _ev(
        EventType.DISCOVERY_QUALITY_SCORECARD_GENERATED,
        timestamp=base + 10,
        payload={
            "capture_recall_rate": 0.62,
            "early_continuation_rate": 0.34,
            "severe_miss_rate": 0.08,
            "false_negative_reject_rate": 0.04,
        },
    )
    bundle = _build_extension().replay_from_events([bucket, scorecard])
    cases = bundle.discovery_quality_cases
    assert len(cases) == 1
    case = cases[0]
    assert case.status == ReplayStatus.OK
    assert case.quality_bucket == "GOLDEN_TAIL"
    assert case.capture_recall_rate == pytest.approx(0.62)
    assert case.scorecard_event_id == scorecard.event_id
    assert case.bucket_event_id == bucket.event_id
    assert case.auto_tuning_allowed is False
    assert "evt://dq-1" in case.evidence_refs


def test_discovery_quality_scorecard_without_bucket_is_degraded() -> None:
    """A standalone scorecard still produces one replay case so that
    replay_count == input_count for the discovery-quality group."""
    base = 1_700_000_000_000
    scorecard = _ev(
        EventType.DISCOVERY_QUALITY_SCORECARD_GENERATED,
        timestamp=base,
        payload={"capture_recall_rate": 0.5},
    )
    bundle = _build_extension().replay_from_events([scorecard])
    cases = bundle.discovery_quality_cases
    assert len(cases) == 1
    assert cases[0].status == ReplayStatus.DEGRADED
    assert cases[0].bucket_event_id is None
    assert cases[0].scorecard_event_id == scorecard.event_id


# ---------------------------------------------------------------------------
# 7. Missing fields do not crash, output partial / degraded
# ---------------------------------------------------------------------------
def test_label_lifecycle_without_started_is_degraded() -> None:
    base = 1_700_000_000_000
    completed = _ev(
        EventType.LABEL_WINDOW_COMPLETED,
        symbol="ORPHANUSDT",
        timestamp=base,
        payload={
            "opportunity_id": "opp-ORPH-1",
            "scan_batch_id": "scan-zz",
            "window": {"window_name": "5m"},
        },
    )
    bundle = _build_extension().replay_from_events([completed])
    lc = bundle.candidate_lifecycles[0]
    assert lc.status == ReplayStatus.DEGRADED
    assert lc.tracking_id is None
    assert lc.completed_window_names == ("5m",)


def test_replay_does_not_crash_on_empty_payloads() -> None:
    """Every record event with no payload must still produce a value
    object (status=partial)."""
    base = 1_700_000_000_000
    events = [
        _ev(et, timestamp=base + i, payload={})
        for i, et in enumerate(
            [
                EventType.HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
                EventType.MOVER_CAPTURE_PATH_AUDITED,
                EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
                EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
                EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED,
                EventType.DISCOVERY_QUALITY_BUCKET_EVALUATED,
                EventType.TAIL_LABEL_ASSIGNED,
                EventType.LABEL_WINDOW_UPDATED,
            ]
        )
    ]
    bundle = _build_extension().replay_from_events(events)
    for case in bundle.mover_coverage_cases:
        assert case.status in (ReplayStatus.PARTIAL, ReplayStatus.DEGRADED)
    for case in bundle.post_discovery_outcome_cases:
        assert case.status == ReplayStatus.PARTIAL
    for case in bundle.reject_attribution_cases:
        assert case.status == ReplayStatus.PARTIAL
    for case in bundle.severe_miss_cases:
        assert case.status == ReplayStatus.PARTIAL
    for case in bundle.discovery_quality_cases:
        assert case.status in (ReplayStatus.PARTIAL, ReplayStatus.DEGRADED)
    # No exception was raised - the brief's "missing fields ->
    # degraded/partial, never crash" rule is satisfied.


# ---------------------------------------------------------------------------
# 8. Replay count == input event count for the supported groups
# ---------------------------------------------------------------------------
def test_replay_record_count_matches_input_event_count() -> None:
    base = 1_700_000_000_000
    events = [
        _ev(
            EventType.LABEL_TRACKING_STARTED,
            symbol="A",
            timestamp=base,
            payload={
                "opportunity_id": "a",
                "label_tracking_record": {"tracking_id": "t-a"},
            },
        ),
        _ev(
            EventType.LABEL_WINDOW_COMPLETED,
            symbol="A",
            timestamp=base + 1,
            payload={"opportunity_id": "a", "window": {"window_name": "5m"}},
        ),
        _ev(
            EventType.TAIL_LABEL_ASSIGNED,
            symbol="A",
            timestamp=base + 2,
            payload={
                "opportunity_id": "a",
                "window_name": "5m",
                "tail_label": "RIGHT_TAIL",
            },
        ),
        _ev(
            EventType.MOVER_CAPTURE_PATH_AUDITED,
            symbol="B",
            timestamp=base + 3,
            payload={"audit_status": "CAPTURED"},
        ),
        _ev(
            EventType.MOVER_CAPTURE_RECALL_AUDIT_GENERATED,
            timestamp=base + 4,
            payload={"report_status": "OK"},
        ),
        _ev(
            EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
            symbol="C",
            timestamp=base + 5,
            payload={"record": {"outcome_label": "EARLY_DISCOVERY"}},
        ),
        _ev(
            EventType.POST_DISCOVERY_OUTCOME_REPORT_GENERATED,
            timestamp=base + 6,
            payload={"reference_window": "60d"},
        ),
        _ev(
            EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
            symbol="D",
            timestamp=base + 7,
            payload={"verdict": "CORRECT_PROTECTIVE_REJECT"},
        ),
        _ev(
            EventType.REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED,
            timestamp=base + 8,
            payload={},
        ),
        _ev(
            EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED,
            symbol="E",
            timestamp=base + 9,
            payload={"root_cause": "DATA_GAP", "severity": "SEVERE"},
        ),
        _ev(
            EventType.SEVERE_MISSED_TAIL_TRIAGE_GENERATED,
            timestamp=base + 10,
            payload={},
        ),
        _ev(
            EventType.DISCOVERY_QUALITY_BUCKET_EVALUATED,
            timestamp=base + 11,
            payload={"quality_bucket": "STRONG"},
        ),
        _ev(
            EventType.DISCOVERY_QUALITY_SCORECARD_GENERATED,
            timestamp=base + 12,
            payload={"capture_recall_rate": 0.7},
        ),
    ]
    bundle = _build_extension().replay_from_events(events)
    # Every input event is counted as a replay-record event.
    assert bundle.input_event_count == len(events)
    assert bundle.replay_record_event_count == len(events)
    assert bundle.skipped_event_count == 0
    # Per-group counts:
    assert len(bundle.tail_outcomes) == 1
    assert len(bundle.candidate_lifecycles) == 1
    assert len(bundle.mover_coverage_cases) == 1
    assert len(bundle.post_discovery_outcome_cases) == 1
    assert len(bundle.reject_attribution_cases) == 1
    assert len(bundle.severe_miss_cases) == 1
    assert len(bundle.discovery_quality_cases) == 1


# ---------------------------------------------------------------------------
# 10. Forbidden fields absent from every replay payload
# ---------------------------------------------------------------------------
def _walk_keys(payload):
    if isinstance(payload, dict):
        for k, v in payload.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk_keys(item)


def test_replay_payloads_never_contain_forbidden_fields() -> None:
    base = 1_700_000_000_000
    # Simulate a malicious upstream payload that smuggles
    # forbidden keys inside a record block. The replay extension must
    # NOT propagate any of them.
    malicious_payload = {
        "opportunity_id": "opp-evil",
        "record": {
            "buy": True,
            "sell": True,
            "long": True,
            "short": True,
            "leverage": 10,
            "position_size": 1234,
            "stop": 0.95,
            "target": 1.05,
            "risk_budget": 999,
            "runtime_config_patch": {"foo": "bar"},
            # Plus legitimate fields:
            "outcome_label": "EARLY_DISCOVERY",
            "detection_timing_label": "EARLY",
            "symbol": "EVILUSDT",
        },
    }
    eval_ev = _ev(
        EventType.POST_DISCOVERY_OUTCOME_EVALUATED,
        symbol="EVILUSDT",
        timestamp=base,
        payload=malicious_payload,
    )
    rej_ev = _ev(
        EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
        symbol="EVILUSDT",
        timestamp=base + 1,
        payload={
            "verdict": "FALSE_NEGATIVE_REJECT",
            "leverage": 25,  # forbidden, but at top-level of source payload
        },
    )
    bundle = _build_extension().replay_from_events([eval_ev, rej_ev])
    bundle_payload = bundle.to_payload()
    bad_keys = [
        k
        for k in _walk_keys(bundle_payload)
        if k in FORBIDDEN_REPLAY_PAYLOAD_KEYS
    ]
    assert not bad_keys, bad_keys


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
def test_replay_is_deterministic_under_input_reordering() -> None:
    base = 1_700_000_000_000
    e1 = _ev(
        EventType.MOVER_CAPTURE_PATH_AUDITED,
        symbol="A",
        timestamp=base,
        payload={"audit_status": "CAPTURED"},
    )
    e2 = _ev(
        EventType.MOVER_CAPTURE_PATH_AUDITED,
        symbol="B",
        timestamp=base,
        payload={"audit_status": "MISSED"},
    )
    e3 = _ev(
        EventType.MOVER_CAPTURE_RECALL_AUDIT_GENERATED,
        timestamp=base + 5,
        payload={"report_status": "OK"},
    )
    forward = _build_extension().replay_from_events([e1, e2, e3]).to_payload()
    reverse = _build_extension().replay_from_events([e3, e2, e1]).to_payload()
    assert forward == reverse


# ---------------------------------------------------------------------------
# Discovery timeline
# ---------------------------------------------------------------------------
def test_discovery_timeline_full_chain() -> None:
    base = 1_700_000_000_000
    payload_id = {"opportunity_id": "opp-DT-1", "scan_batch_id": "scan-z"}
    chain_events = [
        _ev(
            EventType.MARKET_REGIME_ASSESSED,
            symbol="DTUSDT",
            timestamp=base,
            payload={**payload_id, "market_regime": "RISK_ON"},
        ),
        _ev(
            EventType.CANDIDATE_STAGE_CLASSIFIED,
            symbol="DTUSDT",
            timestamp=base + 1,
            payload={**payload_id, "candidate_stage": "EARLY"},
        ),
        _ev(
            EventType.OPPORTUNITY_SCORED,
            symbol="DTUSDT",
            timestamp=base + 2,
            payload={**payload_id, "opportunity_score": 0.72},
        ),
        _ev(
            EventType.STRATEGY_MODE_SELECTED,
            symbol="DTUSDT",
            timestamp=base + 3,
            payload={**payload_id, "strategy_mode": "MOMENTUM"},
        ),
        _ev(
            EventType.CLUSTER_CONTEXT_ATTACHED,
            symbol="DTUSDT",
            timestamp=base + 4,
            payload={**payload_id, "cluster_id": "AI_AGENT"},
        ),
        _ev(
            EventType.LABEL_QUEUE_ENQUEUED,
            symbol="DTUSDT",
            timestamp=base + 5,
            payload={**payload_id, "tracking_windows": ["5m", "1h", "4h"]},
        ),
    ]
    bundle = _build_extension().replay_from_events(chain_events)
    assert len(bundle.discovery_timelines) == 1
    tl = bundle.discovery_timelines[0]
    assert tl.status == ReplayStatus.OK
    assert tl.market_regime == "RISK_ON"
    assert tl.candidate_stage == "EARLY"
    assert tl.opportunity_score == pytest.approx(0.72)
    assert tl.strategy_mode == "MOMENTUM"
    assert tl.cluster_id == "AI_AGENT"
    assert tl.label_queue_window_count == 3
    assert tl.missing_steps == ()


def test_discovery_timeline_partial_chain_flags_missing_steps() -> None:
    base = 1_700_000_000_000
    chain = [
        _ev(
            EventType.MARKET_REGIME_ASSESSED,
            symbol="X",
            timestamp=base,
            payload={"opportunity_id": "x", "market_regime": "RISK_OFF"},
        ),
        _ev(
            EventType.OPPORTUNITY_SCORED,
            symbol="X",
            timestamp=base + 1,
            payload={"opportunity_id": "x", "opportunity_score": 0.4},
        ),
    ]
    bundle = _build_extension().replay_from_events(chain)
    tl = bundle.discovery_timelines[0]
    assert tl.status == ReplayStatus.PARTIAL
    assert "CANDIDATE_STAGE_CLASSIFIED" in tl.missing_steps
    assert "LABEL_QUEUE_ENQUEUED" in tl.missing_steps


# ---------------------------------------------------------------------------
# Public extension class
# ---------------------------------------------------------------------------
def test_extension_replay_all_uses_repository(events_repo) -> None:
    """End-to-end: persist a small adaptive event chain to events.db
    and confirm ``replay_all`` returns the expected bundle without
    mutating the row count."""
    base = 1_700_000_000_000
    events_repo.append_event(
        _ev(
            EventType.LABEL_TRACKING_STARTED,
            symbol="EEUSDT",
            timestamp=base,
            payload={
                "opportunity_id": "opp-EE",
                "label_tracking_record": {
                    "tracking_id": "trk-EE",
                    "status": "pending",
                },
            },
        )
    )
    events_repo.append_event(
        _ev(
            EventType.LABEL_WINDOW_COMPLETED,
            symbol="EEUSDT",
            timestamp=base + 10,
            payload={"opportunity_id": "opp-EE", "window": {"window_name": "5m"}},
        )
    )
    events_repo.append_event(
        _ev(
            EventType.TAIL_LABEL_ASSIGNED,
            symbol="EEUSDT",
            timestamp=base + 10,
            payload={
                "opportunity_id": "opp-EE",
                "window_name": "5m",
                "tail_label": "RIGHT_TAIL",
            },
        )
    )
    pre_count = events_repo.count_events()
    extension = AdaptiveEventReplayExtension(event_repo=events_repo)
    bundle = extension.replay_all()
    post_count = events_repo.count_events()
    # Read-only invariant
    assert pre_count == post_count
    assert isinstance(bundle, AdaptiveReplayBundle)
    assert len(bundle.candidate_lifecycles) == 1
    assert len(bundle.tail_outcomes) == 1
    assert bundle.input_event_count == 3
    assert bundle.replay_record_event_count == 3


def test_extension_constants_pin_phase_id() -> None:
    """Every replay payload must declare its source phase so a
    downstream auditor can pin Phase 11C.1C-C-B-B-B-E-A as the
    producer."""
    assert SOURCE_PHASE == "phase_11c_1c_c_b_b_b_e_a"
    assert SOURCE_MODULE == "replay_11c_adaptive_extension"
    bundle = _build_extension().replay_from_events([])
    payload = bundle.to_payload()
    assert payload["source_phase"] == SOURCE_PHASE
