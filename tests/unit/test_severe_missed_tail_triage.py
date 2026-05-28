"""Unit tests for Phase 11C.1C-C-B-B-B-D-C-B Severe Missed Tail
Triage v0.

Every test in this module enforces the brief's hard invariants:

  - The triage layer is paper / report / evidence only.
  - It NEVER emits a payload containing a trade-authority field
    (``buy`` / ``sell`` / ``long`` / ``short`` / ``direction`` /
    ``side`` / ``entry`` / ``exit`` / ``position_size`` /
    ``leverage`` / ``stop`` / ``stop_loss`` / ``target`` /
    ``take_profit`` / ``risk_budget`` / ``order`` /
    ``execution_command`` / ``runtime_config_patch`` /
    ``symbol_limit_patch`` / ``threshold_patch`` /
    ``candidate_pool_patch`` / ``regime_weight_patch``).
  - It NEVER imports ``app.risk`` / ``app.execution`` /
    ``app.exchanges`` / ``app.llm`` / ``app.telegram``.
  - ``auto_tuning_allowed`` is hard-pinned to ``False`` on every
    serialised record / report.
  - ``RAVEUSDT`` / ``STOUSDT``-style cases must be classified as
    data-gap / severe-miss triage candidates only; this layer
    must NEVER assert a parameter error from a single coin.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adaptive.severe_missed_tail_triage import (
    DEFAULT_TRUE_DISCOVERY_FAILURE_MFE_THRESHOLD,
    SEVERE_MISSED_TAIL_TRIAGE_FORBIDDEN_PAYLOAD_KEYS,
    SevereMissedTailTriageEngine,
    SevereMissedTailTriageEngineConfig,
    SevereMissedTailTriageForbiddenFieldError,
    SevereMissRootCause,
    SevereMissSeverity,
    SevereMissTriageInput,
    SevereMissTriageRecord,
    SevereMissTriageReport,
    assert_payload_has_no_forbidden_keys,
    build_severe_missed_tail_triage_report,
)
from app.core.events import EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engine() -> SevereMissedTailTriageEngine:
    return SevereMissedTailTriageEngine(SevereMissedTailTriageEngineConfig())


def _base_evidence() -> tuple[str, ...]:
    return (
        "evt://historical_mover_coverage_record_audited/1",
        "evt://post_discovery_outcome_evaluated/1",
    )


def _walk_payload(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _walk_payload(v)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk_payload(item)


def _payload_contains_forbidden(payload) -> set[str]:
    keys = set(_walk_payload(payload))
    return keys & SEVERE_MISSED_TAIL_TRIAGE_FORBIDDEN_PAYLOAD_KEYS


# ---------------------------------------------------------------------------
# Test 1: price path missing  (RAVEUSDT / STOUSDT style)
# ---------------------------------------------------------------------------


def test_price_path_missing_no_top_mover_row_routes_to_data_recovery() -> None:
    """RAVE / STO style: price_path_missing_reason =
    no_top_mover_row_covering_first_seen_time.

    Triage MUST route to ``needs_data_recovery=True`` and MUST NOT
    assert any threshold problem.
    """

    engine = _engine()

    rave = SevereMissTriageInput(
        symbol="RAVEUSDT",
        reference_window="60d",
        capture_status="missed",
        price_path_status="absent",
        price_path_missing_reason="no_top_mover_row_covering_first_seen_time",
        d_b_outcome_label="INSUFFICIENT_PRICE_PATH",
        d_b_detection_timing_label="INSUFFICIENT_DATA",
        evidence_refs=_base_evidence(),
    )
    sto = SevereMissTriageInput(
        symbol="STOUSDT",
        reference_window="60d",
        capture_status="missed",
        price_path_status="absent",
        price_path_missing_reason="no_top_mover_row_covering_first_seen_time",
        d_b_outcome_label="INSUFFICIENT_PRICE_PATH",
        d_b_detection_timing_label="INSUFFICIENT_DATA",
        evidence_refs=_base_evidence(),
    )

    rec_rave = engine.triage(rave)
    rec_sto = engine.triage(sto)

    assert (
        rec_rave.root_cause
        == SevereMissRootCause.NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME
    )
    assert (
        rec_sto.root_cause
        == SevereMissRootCause.NO_TOP_MOVER_ROW_COVERING_FIRST_SEEN_TIME
    )

    assert rec_rave.needs_data_recovery is True
    assert rec_sto.needs_data_recovery is True

    # Brief: 不要直接断言 threshold 问题 — must NOT assign
    # THRESHOLD_TOO_STRICT or any rule-gap label as primary
    # cause when only the price path is missing.
    assert rec_rave.root_cause != SevereMissRootCause.THRESHOLD_TOO_STRICT
    assert rec_sto.root_cause != SevereMissRootCause.THRESHOLD_TOO_STRICT

    # The triage MUST NOT route a price-path-only data-gap case
    # into the rule-review queue.
    assert rec_rave.needs_rule_review is False
    assert rec_sto.needs_rule_review is False

    # auto_tuning_allowed is hard-pinned False on every record.
    assert rec_rave.to_dict()["auto_tuning_allowed"] is False
    assert rec_sto.to_dict()["auto_tuning_allowed"] is False


def test_price_path_missing_status_only_routes_to_price_path_missing() -> None:
    """If only ``price_path_status`` is set to ``missing`` (no
    explicit ``price_path_missing_reason``), root cause is
    ``PRICE_PATH_MISSING``.
    """

    engine = _engine()
    case = SevereMissTriageInput(
        symbol="FOOUSDT",
        reference_window="60d",
        capture_status="missed",
        price_path_status="missing",
        evidence_refs=_base_evidence(),
    )
    rec = engine.triage(case)
    assert rec.root_cause == SevereMissRootCause.PRICE_PATH_MISSING
    assert rec.needs_data_recovery is True
    assert rec.severity == SevereMissSeverity.MEDIUM


# ---------------------------------------------------------------------------
# Test 2: candidate pool evicted
# ---------------------------------------------------------------------------


def test_candidate_pool_evicted_routes_to_candidate_pool_evicted() -> None:
    engine = _engine()
    case = SevereMissTriageInput(
        symbol="EVICTUSDT",
        reference_window="60d",
        capture_status="missed",
        candidate_pool_seen=True,
        candidate_pool_evicted=True,
        universe_eligible=True,
        symbol_limit_included=True,
        evidence_refs=_base_evidence(),
    )
    rec = engine.triage(case)

    assert rec.root_cause == SevereMissRootCause.CANDIDATE_POOL_EVICTED
    assert rec.severity == SevereMissSeverity.HIGH
    assert rec.needs_operator_review is True
    assert rec.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# Test 3: symbol limit gap
# ---------------------------------------------------------------------------


def test_symbol_limit_gap_routes_to_rule_review_no_auto_tuning() -> None:
    engine = _engine()
    case = SevereMissTriageInput(
        symbol="OUTUSDT",
        reference_window="60d",
        capture_status="missed",
        universe_eligible=True,
        symbol_limit_included=False,
        evidence_refs=_base_evidence(),
    )
    rec = engine.triage(case)

    assert rec.root_cause == SevereMissRootCause.SYMBOL_LIMIT_GAP
    assert rec.needs_rule_review is True
    # auto_tuning_allowed must be False even when the rule review
    # queue is engaged — the brief says auto-tuning is forbidden.
    assert rec.auto_tuning_allowed is False
    assert rec.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# Test 4: universe gap
# ---------------------------------------------------------------------------


def test_universe_gap_routes_to_universe_gap() -> None:
    engine = _engine()
    case = SevereMissTriageInput(
        symbol="DELISTEDUSDT",
        reference_window="60d",
        capture_status="excluded",
        universe_eligible=False,
        evidence_refs=_base_evidence(),
    )
    rec = engine.triage(case)
    assert rec.root_cause == SevereMissRootCause.UNIVERSE_GAP
    assert rec.severity == SevereMissSeverity.MEDIUM
    assert rec.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# Test 5: risk rejected protective
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "verdict",
    [
        "CORRECT_PROTECTIVE_REJECT",
        "STOP_SAFETY_REJECT",
        "DATA_QUALITY_REJECT",
        "LIQUIDITY_PROTECTIVE_REJECT",
        "MANIPULATION_PROTECTIVE_REJECT",
    ],
)
def test_risk_rejected_protective_routes_to_protective(verdict: str) -> None:
    engine = _engine()
    case = SevereMissTriageInput(
        symbol="PROTECTUSDT",
        reference_window="60d",
        capture_status="missed",
        universe_eligible=True,
        symbol_limit_included=True,
        candidate_pool_seen=True,
        candidate_pool_evicted=False,
        reject_attribution_verdict=verdict,
        reject_attribution_primary_reason="protective_signal",
        evidence_refs=_base_evidence(),
    )
    rec = engine.triage(case)
    assert rec.root_cause == SevereMissRootCause.RISK_REJECTED_PROTECTIVE
    assert rec.severity == SevereMissSeverity.LOW
    assert rec.needs_rule_review is False
    assert rec.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# Test 6: risk rejected false negative
# ---------------------------------------------------------------------------


def test_risk_rejected_false_negative_routes_to_critical_no_auto_tuning() -> None:
    engine = _engine()
    case = SevereMissTriageInput(
        symbol="FALSEUSDT",
        reference_window="60d",
        capture_status="missed",
        universe_eligible=True,
        symbol_limit_included=True,
        candidate_pool_seen=True,
        candidate_pool_evicted=False,
        reject_attribution_verdict="FALSE_NEGATIVE_REJECT",
        reject_attribution_primary_reason="overshoot_filter",
        post_seen_mfe_pct=0.18,
        d_b_outcome_label="MISSED_STRONG_TAIL",
        evidence_refs=_base_evidence(),
    )
    rec = engine.triage(case)

    assert rec.root_cause == SevereMissRootCause.RISK_REJECTED_FALSE_NEGATIVE
    assert rec.severity == SevereMissSeverity.CRITICAL
    assert rec.needs_operator_review is True
    assert rec.needs_rule_review is True
    # MUST be False — a CRITICAL severity is NOT permission to
    # relax the Risk Engine.
    assert rec.auto_tuning_allowed is False
    assert rec.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# Test 7: strategy mode false negative
# ---------------------------------------------------------------------------


def test_strategy_mode_false_negative_routes_to_strategy_mode_false_negative() -> None:
    engine = _engine()
    case = SevereMissTriageInput(
        symbol="OBSERVEUSDT",
        reference_window="60d",
        capture_status="missed",
        universe_eligible=True,
        symbol_limit_included=True,
        candidate_pool_seen=True,
        candidate_pool_evicted=False,
        reject_attribution_verdict="STRATEGY_MODE_FALSE_NEGATIVE",
        reject_attribution_primary_reason="strategy_mode=observe",
        post_seen_mfe_pct=0.22,
        d_b_outcome_label="MISSED_STRONG_TAIL",
        evidence_refs=_base_evidence(),
    )
    rec = engine.triage(case)

    assert rec.root_cause == SevereMissRootCause.STRATEGY_MODE_FALSE_NEGATIVE
    assert rec.severity == SevereMissSeverity.HIGH
    assert rec.needs_operator_review is True
    assert rec.needs_rule_review is True
    assert rec.auto_tuning_allowed is False


# ---------------------------------------------------------------------------
# Test 8: true discovery failure
# ---------------------------------------------------------------------------


def test_true_discovery_failure_when_no_other_gap_and_mfe_positive() -> None:
    engine = _engine()
    case = SevereMissTriageInput(
        symbol="GENUINEMISSUSDT",
        reference_window="60d",
        capture_status="missed",
        universe_eligible=True,
        symbol_limit_included=True,
        candidate_pool_seen=False,
        candidate_pool_evicted=False,
        reject_attribution_verdict=None,
        # Notably: no price_path gap, no risk reject, no strategy
        # mode false negative, capture_status=missed, and the MFE
        # is meaningfully positive.
        post_seen_mfe_pct=0.35,
        d_b_outcome_label="MISSED_STRONG_TAIL",
        evidence_refs=_base_evidence(),
    )
    rec = engine.triage(case)

    assert rec.root_cause == SevereMissRootCause.TRUE_DISCOVERY_FAILURE
    assert rec.severity == SevereMissSeverity.SEVERE
    assert rec.needs_operator_review is True
    assert rec.needs_rule_review is False
    assert rec.auto_tuning_allowed is False


def test_true_discovery_failure_threshold_below_default_does_not_fire() -> None:
    """If MFE is below the threshold, do NOT classify as
    TRUE_DISCOVERY_FAILURE — fall through to UNKNOWN.
    """

    engine = _engine()
    case = SevereMissTriageInput(
        symbol="WEAKMOVERUSDT",
        reference_window="60d",
        capture_status="missed",
        universe_eligible=True,
        symbol_limit_included=True,
        candidate_pool_seen=False,
        candidate_pool_evicted=False,
        post_seen_mfe_pct=DEFAULT_TRUE_DISCOVERY_FAILURE_MFE_THRESHOLD - 0.01,
        evidence_refs=_base_evidence(),
    )
    rec = engine.triage(case)
    assert rec.root_cause == SevereMissRootCause.UNKNOWN
    assert rec.severity == SevereMissSeverity.INSUFFICIENT_EVIDENCE


# ---------------------------------------------------------------------------
# Test 9: insufficient evidence
# ---------------------------------------------------------------------------


def test_insufficient_evidence_when_evidence_refs_missing() -> None:
    engine = _engine()
    case = SevereMissTriageInput(
        symbol="MAYBEUSDT",
        reference_window="60d",
        capture_status="missed",
        evidence_refs=(),
    )
    rec = engine.triage(case)

    assert rec.root_cause == SevereMissRootCause.INSUFFICIENT_EVIDENCE
    assert rec.severity == SevereMissSeverity.INSUFFICIENT_EVIDENCE
    assert rec.needs_operator_review is True
    # MUST not fabricate a more-specific root cause when
    # evidence_refs are missing.
    assert rec.root_cause != SevereMissRootCause.TRUE_DISCOVERY_FAILURE
    assert rec.root_cause != SevereMissRootCause.SYMBOL_LIMIT_GAP


def test_insufficient_evidence_when_no_signals_present() -> None:
    """If evidence_refs exist but every triage signal is None,
    refuse to fabricate a verdict.
    """

    engine = _engine()
    case = SevereMissTriageInput(
        symbol="EMPTYUSDT",
        reference_window="60d",
        evidence_refs=_base_evidence(),
    )
    rec = engine.triage(case)
    assert rec.root_cause == SevereMissRootCause.INSUFFICIENT_EVIDENCE


# ---------------------------------------------------------------------------
# Test 10: forbidden fields absent on every output payload
# ---------------------------------------------------------------------------


def test_forbidden_fields_absent_on_every_record_and_report_payload() -> None:
    engine = _engine()
    inputs = [
        # universe gap
        SevereMissTriageInput(
            symbol="UGUSDT",
            reference_window="60d",
            universe_eligible=False,
            evidence_refs=_base_evidence(),
        ),
        # symbol limit gap
        SevereMissTriageInput(
            symbol="SLUSDT",
            reference_window="60d",
            universe_eligible=True,
            symbol_limit_included=False,
            evidence_refs=_base_evidence(),
        ),
        # candidate pool evicted
        SevereMissTriageInput(
            symbol="CPUSDT",
            reference_window="60d",
            universe_eligible=True,
            symbol_limit_included=True,
            candidate_pool_seen=True,
            candidate_pool_evicted=True,
            evidence_refs=_base_evidence(),
        ),
        # price path missing
        SevereMissTriageInput(
            symbol="RAVEUSDT",
            reference_window="60d",
            universe_eligible=True,
            symbol_limit_included=True,
            price_path_status="absent",
            price_path_missing_reason="no_top_mover_row_covering_first_seen_time",
            evidence_refs=_base_evidence(),
        ),
        # risk rejected protective
        SevereMissTriageInput(
            symbol="PRUSDT",
            reference_window="60d",
            universe_eligible=True,
            symbol_limit_included=True,
            reject_attribution_verdict="STOP_SAFETY_REJECT",
            evidence_refs=_base_evidence(),
        ),
        # risk rejected false negative
        SevereMissTriageInput(
            symbol="FNUSDT",
            reference_window="60d",
            universe_eligible=True,
            symbol_limit_included=True,
            reject_attribution_verdict="FALSE_NEGATIVE_REJECT",
            post_seen_mfe_pct=0.20,
            evidence_refs=_base_evidence(),
        ),
        # strategy mode false negative
        SevereMissTriageInput(
            symbol="SMUSDT",
            reference_window="60d",
            universe_eligible=True,
            symbol_limit_included=True,
            reject_attribution_verdict="STRATEGY_MODE_FALSE_NEGATIVE",
            post_seen_mfe_pct=0.20,
            evidence_refs=_base_evidence(),
        ),
        # true discovery failure
        SevereMissTriageInput(
            symbol="TDFUSDT",
            reference_window="60d",
            capture_status="missed",
            universe_eligible=True,
            symbol_limit_included=True,
            candidate_pool_seen=False,
            post_seen_mfe_pct=0.40,
            evidence_refs=_base_evidence(),
        ),
        # insufficient evidence
        SevereMissTriageInput(
            symbol="IEUSDT",
            reference_window="60d",
            evidence_refs=(),
        ),
    ]

    records = engine.triage_many(inputs)
    report = build_severe_missed_tail_triage_report(
        records, reference_window="60d"
    )

    for rec in records:
        payload = rec.to_dict()
        assert _payload_contains_forbidden(payload) == set()
        assert payload["auto_tuning_allowed"] is False

    report_payload = report.to_dict()
    assert _payload_contains_forbidden(report_payload) == set()
    assert report_payload["auto_tuning_allowed"] is False


def test_assert_payload_has_no_forbidden_keys_raises_on_planted_key() -> None:
    """Defensive: the recursive guard must catch a forbidden key
    if anyone tries to slip one in.
    """

    bad_payload = {
        "symbol": "X",
        "nested": {"position_size": 1.0},
    }
    with pytest.raises(SevereMissedTailTriageForbiddenFieldError):
        assert_payload_has_no_forbidden_keys(bad_payload, context="bad")

    # Forbidden keys inside lists must also raise.
    bad_list_payload = {"items": [{"leverage": 5}]}
    with pytest.raises(SevereMissedTailTriageForbiddenFieldError):
        assert_payload_has_no_forbidden_keys(bad_list_payload, context="bad_list")


# ---------------------------------------------------------------------------
# Test 11: forbidden imports
# ---------------------------------------------------------------------------


def test_severe_missed_tail_triage_module_does_not_import_forbidden_layers() -> None:
    """The module MUST NOT import ``app.risk`` / ``app.execution`` /
    ``app.exchanges`` / ``app.llm`` / ``app.telegram`` directly or
    transitively at module level.
    """

    module_path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "adaptive"
        / "severe_missed_tail_triage.py"
    )
    source = module_path.read_text(encoding="utf-8")

    # Strip docstrings and comments so prose like
    # "MUST NOT import app.risk" doesn't trip the check.
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.lstrip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)

    forbidden_modules = (
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.llm",
        "app.telegram",
    )
    for forbidden in forbidden_modules:
        assert forbidden not in joined, (
            f"severe_missed_tail_triage.py imports forbidden module "
            f"{forbidden!r}: {joined!r}"
        )


# ---------------------------------------------------------------------------
# Aggregate report behaviour
# ---------------------------------------------------------------------------


def test_report_aggregates_severity_counts_and_notable_symbols() -> None:
    engine = _engine()
    inputs = [
        SevereMissTriageInput(
            symbol="A",
            reference_window="60d",
            universe_eligible=True,
            symbol_limit_included=True,
            reject_attribution_verdict="FALSE_NEGATIVE_REJECT",
            post_seen_mfe_pct=0.20,
            evidence_refs=_base_evidence(),
        ),  # CRITICAL
        SevereMissTriageInput(
            symbol="B",
            reference_window="60d",
            capture_status="missed",
            universe_eligible=True,
            symbol_limit_included=True,
            candidate_pool_seen=False,
            post_seen_mfe_pct=0.40,
            evidence_refs=_base_evidence(),
        ),  # SEVERE
        SevereMissTriageInput(
            symbol="C",
            reference_window="60d",
            evidence_refs=(),
        ),  # INSUFFICIENT_EVIDENCE
    ]
    records = engine.triage_many(inputs)
    report = build_severe_missed_tail_triage_report(
        records, reference_window="60d"
    )

    assert report.total_records == 3
    assert report.critical_count == 1
    assert report.severe_count == 1
    assert report.insufficient_evidence_count == 1
    assert "A" in report.notable_symbols
    assert "B" in report.notable_symbols
    assert "A" in report.needs_operator_review_symbols
    assert "A" in report.needs_rule_review_symbols
    assert report.auto_tuning_allowed is False
    assert report.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# Event-type hookup
# ---------------------------------------------------------------------------


def test_severe_missed_tail_triage_event_types_registered() -> None:
    """The three new typed events must exist on
    :class:`EventType` and round-trip through ``.value``.
    """

    assert (
        EventType.SEVERE_MISSED_TAIL_TRIAGE_GENERATED.value
        == "SEVERE_MISSED_TAIL_TRIAGE_GENERATED"
    )
    assert (
        EventType.SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED.value
        == "SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED"
    )
    assert (
        EventType.SEVERE_MISS_ESCALATION_REQUIRED.value
        == "SEVERE_MISS_ESCALATION_REQUIRED"
    )


# ---------------------------------------------------------------------------
# Dataclass identity sanity
# ---------------------------------------------------------------------------


def test_record_and_report_dataclasses_are_frozen() -> None:
    """Records / reports are immutable so payloads cannot be
    mutated after emission.
    """

    rec = SevereMissTriageRecord(
        symbol="X",
        reference_window="60d",
        severity=SevereMissSeverity.LOW,
        root_cause=SevereMissRootCause.RISK_REJECTED_PROTECTIVE,
    )
    with pytest.raises(Exception):
        rec.severity = SevereMissSeverity.CRITICAL  # type: ignore[misc]

    report = SevereMissTriageReport(
        reference_window="60d",
        total_records=0,
        severe_count=0,
        critical_count=0,
        insufficient_evidence_count=0,
        root_cause_summary={},
    )
    with pytest.raises(Exception):
        report.total_records = 1  # type: ignore[misc]
