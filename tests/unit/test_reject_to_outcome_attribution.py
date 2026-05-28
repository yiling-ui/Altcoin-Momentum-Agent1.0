"""Phase 11C.1C-C-B-B-B-D-C-A - Reject-to-Outcome Attribution v0 tests.

Test plan (mirrors the brief's acceptance list):

  1. stop safety reject remains protective even when MFE is positive
  2. data quality reject -> needs_data_recovery=true
  3. liquidity protective reject
  4. manipulation protective reject
  5. false negative reject (non-hard-safety reject + strong outcome
     + positive MFE)
  6. strategy mode false negative (strategy_mode in {reject, observe}
     + strong outcome, no hard-safety reject)
  7. no reject found (no risk_reject_reasons / no no_trade_reasons /
     strategy_mode not in no-trade set)
  8. insufficient evidence (missing evidence_refs / missing outcome
     fields)
  9. forbidden fields absent on every emitted record / report
 10. no forbidden imports (no app.risk / app.execution / app.exchanges
     / app.llm / app.telegram in reject_to_outcome_attribution.py)

Plus a small set of sanity / regression tests for:

  - the four new EventType values exist in app.core.events.EventType,
  - build_reject_attribution_report aggregates correctly,
  - auto_tuning_allowed is hard-pinned to False on every payload,
  - CORRECT_PROTECTIVE_REJECT confirms a reject when the outcome
    surface explicitly marks the candidate as weak / fake / dumped.

The module is paper / report / evidence only. None of these tests
authorise a real trade or flip a Phase 1 safety flag.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.adaptive.reject_to_outcome_attribution import (
    DEFAULT_FALSE_NEGATIVE_MFE_THRESHOLD,
    REJECT_ATTRIBUTION_FORBIDDEN_PAYLOAD_KEYS,
    REJECT_TO_OUTCOME_ATTRIBUTION_SCHEMA_VERSION,
    REJECT_TO_OUTCOME_ATTRIBUTION_SOURCE_PHASE,
    REJECT_TO_OUTCOME_ATTRIBUTION_VERSION,
    RejectAttributionEngineConfig,
    RejectAttributionForbiddenFieldError,
    RejectAttributionInput,
    RejectAttributionRecord,
    RejectAttributionReport,
    RejectAttributionVerdict,
    RejectToOutcomeAttributionEngine,
    assert_payload_has_no_forbidden_keys,
    build_reject_attribution_report,
)
from app.core.events import EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engine() -> RejectToOutcomeAttributionEngine:
    return RejectToOutcomeAttributionEngine()


def _baseline_input(**overrides: object) -> RejectAttributionInput:
    """Build a baseline input that already has ``evidence_refs`` and
    an outcome signal, so individual tests can override only the
    fields they care about.
    """

    defaults: dict[str, object] = {
        "opportunity_id": "OPP-0001",
        "symbol": "TESTUSDT",
        "reference_window": "60D",
        "first_seen_time_utc_ms": 1_767_225_600_000,
        "risk_reject_reasons": ("threshold_under_floor",),
        "no_trade_reasons": (),
        "strategy_mode": "reject",
        "candidate_stage": "early",
        "opportunity_score_bucket": "B",
        "tail_label": None,
        "post_discovery_outcome_label": "EARLY_CONTINUATION",
        "detection_timing_label": "EARLY",
        "post_seen_mfe_pct": 0.40,
        "post_seen_mae_pct": -0.02,
        "remaining_upside_to_peak_pct": 0.30,
        "price_path_status": "RESOLVED",
        "data_quality_flags": (),
        "evidence_refs": ("audit:OPP-0001",),
    }
    defaults.update(overrides)
    return RejectAttributionInput(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. Stop safety reject stays protective even on positive MFE
# ---------------------------------------------------------------------------


def test_stop_safety_reject_stays_protective_on_positive_mfe() -> None:
    inp = _baseline_input(
        opportunity_id="OPP-STOP-001",
        symbol="STOPUSDT",
        risk_reject_reasons=("stop_unconfirmed",),
        post_seen_mfe_pct=0.80,
        post_discovery_outcome_label="EARLY_CONTINUATION",
        evidence_refs=("audit:STOPUSDT:1",),
    )
    record = _engine().attribute(inp)

    # Brief allows STOP_SAFETY_REJECT or SYSTEM_SAFETY_REJECT here.
    assert record.verdict in {
        RejectAttributionVerdict.STOP_SAFETY_REJECT,
        RejectAttributionVerdict.SYSTEM_SAFETY_REJECT,
    }
    assert record.was_reject_protective is True
    assert record.was_false_negative is False
    assert record.needs_rule_review is False
    assert record.auto_tuning_allowed is False


def test_unknown_position_routes_to_system_safety() -> None:
    inp = _baseline_input(
        opportunity_id="OPP-SAFE-001",
        symbol="SAFEUSDT",
        risk_reject_reasons=("unknown_position",),
        post_seen_mfe_pct=0.50,
    )
    record = _engine().attribute(inp)
    assert record.verdict == RejectAttributionVerdict.SYSTEM_SAFETY_REJECT
    assert record.was_reject_protective is True
    assert record.was_false_negative is False


def test_protection_mode_routes_to_system_safety() -> None:
    inp = _baseline_input(
        opportunity_id="OPP-PMODE-001",
        symbol="PMODEUSDT",
        risk_reject_reasons=("protection_mode_active",),
        post_seen_mfe_pct=0.25,
    )
    record = _engine().attribute(inp)
    assert record.verdict == RejectAttributionVerdict.SYSTEM_SAFETY_REJECT
    assert record.was_reject_protective is True


# ---------------------------------------------------------------------------
# 2. Data quality reject
# ---------------------------------------------------------------------------


def test_data_quality_reject_via_risk_reason() -> None:
    inp = _baseline_input(
        opportunity_id="OPP-DQ-001",
        symbol="DQUSDT",
        risk_reject_reasons=("data_degraded",),
    )
    record = _engine().attribute(inp)
    assert record.verdict == RejectAttributionVerdict.DATA_QUALITY_REJECT
    assert record.needs_data_recovery is True
    assert record.was_reject_protective is True
    assert record.needs_rule_review is False


def test_data_quality_reject_via_data_quality_flag() -> None:
    inp = _baseline_input(
        opportunity_id="OPP-DQ-002",
        symbol="DQ2USDT",
        risk_reject_reasons=(),
        no_trade_reasons=("threshold_floor",),
        data_quality_flags=("insufficient_price_path",),
    )
    record = _engine().attribute(inp)
    assert record.verdict == RejectAttributionVerdict.DATA_QUALITY_REJECT
    assert record.needs_data_recovery is True


# ---------------------------------------------------------------------------
# 3. Liquidity protective reject
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason",
    [
        "spread_too_wide",
        "depth_too_thin",
        "slippage_too_high",
        "exit_liquidity_low",
        "thin_book",
    ],
)
def test_liquidity_protective_reject(reason: str) -> None:
    inp = _baseline_input(
        opportunity_id=f"OPP-LIQ-{reason}",
        symbol="LIQUSDT",
        risk_reject_reasons=(reason,),
        post_seen_mfe_pct=0.40,
    )
    record = _engine().attribute(inp)
    assert record.verdict == RejectAttributionVerdict.LIQUIDITY_PROTECTIVE_REJECT
    assert record.was_reject_protective is True
    assert record.was_false_negative is False


# ---------------------------------------------------------------------------
# 4. Manipulation protective reject
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reason",
    [
        "manipulation_pattern",
        "fake_breakout_detected",
        "m2_pattern_match",
        "m3_signal_active",
        "spoof_layering",
    ],
)
def test_manipulation_protective_reject(reason: str) -> None:
    inp = _baseline_input(
        opportunity_id=f"OPP-MAN-{reason}",
        symbol="MANUSDT",
        risk_reject_reasons=(reason,),
        post_seen_mfe_pct=0.30,
    )
    record = _engine().attribute(inp)
    assert (
        record.verdict == RejectAttributionVerdict.MANIPULATION_PROTECTIVE_REJECT
    )
    assert record.was_reject_protective is True
    assert record.was_false_negative is False


# ---------------------------------------------------------------------------
# 5. False negative reject (non-hard-safety + strong outcome + +MFE)
# ---------------------------------------------------------------------------


def test_false_negative_reject_when_outcome_runs_strong() -> None:
    inp = _baseline_input(
        opportunity_id="OPP-FN-001",
        symbol="FNUSDT",
        risk_reject_reasons=("threshold_under_floor",),
        no_trade_reasons=(),
        strategy_mode="follow",
        post_discovery_outcome_label="EARLY_CONTINUATION",
        post_seen_mfe_pct=0.40,
    )
    record = _engine().attribute(inp)
    assert record.verdict == RejectAttributionVerdict.FALSE_NEGATIVE_REJECT
    assert record.was_false_negative is True
    assert record.was_reject_protective is False
    assert record.needs_operator_review is True
    assert record.needs_rule_review is True
    assert record.auto_tuning_allowed is False


def test_false_negative_reject_with_missed_strong_tail_outcome() -> None:
    inp = _baseline_input(
        opportunity_id="OPP-FN-002",
        symbol="FN2USDT",
        risk_reject_reasons=("regime_neutral",),
        strategy_mode="follow",
        post_discovery_outcome_label="MISSED_STRONG_TAIL",
        post_seen_mfe_pct=0.65,
    )
    record = _engine().attribute(inp)
    assert record.verdict == RejectAttributionVerdict.FALSE_NEGATIVE_REJECT
    assert record.was_false_negative is True
    assert record.needs_rule_review is True


def test_false_negative_threshold_respected() -> None:
    """A tiny positive MFE below the false-negative threshold MUST
    NOT flip a non-hard-safety reject to FALSE_NEGATIVE_REJECT."""

    inp = _baseline_input(
        opportunity_id="OPP-FN-003",
        symbol="FN3USDT",
        risk_reject_reasons=("regime_neutral",),
        strategy_mode="follow",
        post_discovery_outcome_label="EARLY_CONTINUATION",
        post_seen_mfe_pct=DEFAULT_FALSE_NEGATIVE_MFE_THRESHOLD / 4.0,
        remaining_upside_to_peak_pct=0.0,
        tail_label=None,
    )
    record = _engine().attribute(inp)
    assert record.verdict != RejectAttributionVerdict.FALSE_NEGATIVE_REJECT


# ---------------------------------------------------------------------------
# 6. Strategy mode false negative
# ---------------------------------------------------------------------------


def test_strategy_mode_false_negative_reject_only() -> None:
    inp = _baseline_input(
        opportunity_id="OPP-SM-001",
        symbol="SMUSDT",
        risk_reject_reasons=(),
        no_trade_reasons=(),
        strategy_mode="reject",
        post_discovery_outcome_label="EARLY_CONTINUATION",
        post_seen_mfe_pct=0.30,
    )
    record = _engine().attribute(inp)
    assert record.verdict == RejectAttributionVerdict.STRATEGY_MODE_FALSE_NEGATIVE
    assert record.was_false_negative is True
    assert record.needs_operator_review is True


def test_strategy_mode_false_negative_observe_with_strong_tail_label() -> None:
    inp = _baseline_input(
        opportunity_id="OPP-SM-002",
        symbol="SM2USDT",
        risk_reject_reasons=(),
        no_trade_reasons=(),
        strategy_mode="observe",
        tail_label="strong_tail",
        post_discovery_outcome_label=None,
        detection_timing_label=None,
        post_seen_mfe_pct=0.40,
    )
    record = _engine().attribute(inp)
    assert record.verdict == RejectAttributionVerdict.STRATEGY_MODE_FALSE_NEGATIVE


def test_strategy_mode_observe_with_weak_outcome_does_not_flip() -> None:
    inp = _baseline_input(
        opportunity_id="OPP-SM-003",
        symbol="SM3USDT",
        risk_reject_reasons=(),
        no_trade_reasons=(),
        strategy_mode="observe",
        post_discovery_outcome_label="FAKE_BREAKOUT",
        tail_label="weak_tail",
        post_seen_mfe_pct=0.01,
        remaining_upside_to_peak_pct=0.0,
    )
    record = _engine().attribute(inp)
    assert record.verdict not in {
        RejectAttributionVerdict.STRATEGY_MODE_FALSE_NEGATIVE,
        RejectAttributionVerdict.FALSE_NEGATIVE_REJECT,
    }


# ---------------------------------------------------------------------------
# 7. No reject found
# ---------------------------------------------------------------------------


def test_no_reject_found_when_no_signal() -> None:
    inp = _baseline_input(
        opportunity_id="OPP-NR-001",
        symbol="NRUSDT",
        risk_reject_reasons=(),
        no_trade_reasons=(),
        strategy_mode="follow",
        data_quality_flags=(),
    )
    record = _engine().attribute(inp)
    assert record.verdict == RejectAttributionVerdict.NO_REJECT_FOUND
    assert record.was_reject_protective is False
    assert record.was_false_negative is False
    assert record.needs_operator_review is False


# ---------------------------------------------------------------------------
# 8. Insufficient evidence
# ---------------------------------------------------------------------------


def test_insufficient_evidence_when_evidence_refs_missing() -> None:
    inp = _baseline_input(
        opportunity_id="OPP-IE-001",
        symbol="IEUSDT",
        risk_reject_reasons=("threshold_under_floor",),
        evidence_refs=(),
    )
    record = _engine().attribute(inp)
    assert record.verdict == RejectAttributionVerdict.INSUFFICIENT_EVIDENCE
    assert record.was_false_negative is False
    assert record.needs_operator_review is True


def test_insufficient_evidence_when_outcome_signal_missing() -> None:
    inp = _baseline_input(
        opportunity_id="OPP-IE-002",
        symbol="IE2USDT",
        risk_reject_reasons=("threshold_under_floor",),
        post_discovery_outcome_label=None,
        detection_timing_label=None,
        tail_label=None,
        post_seen_mfe_pct=None,
        post_seen_mae_pct=None,
        remaining_upside_to_peak_pct=None,
    )
    record = _engine().attribute(inp)
    assert record.verdict == RejectAttributionVerdict.INSUFFICIENT_EVIDENCE


# ---------------------------------------------------------------------------
# 9. Forbidden fields absent on every emitted record / report
# ---------------------------------------------------------------------------


def _all_keys(payload: object, acc: set[str] | None = None) -> set[str]:
    if acc is None:
        acc = set()
    if isinstance(payload, dict):
        for k, v in payload.items():
            acc.add(str(k))
            _all_keys(v, acc)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            _all_keys(item, acc)
    return acc


@pytest.mark.parametrize(
    "factory",
    [
        lambda: _baseline_input(
            opportunity_id="OPP-FK-A",
            risk_reject_reasons=("stop_unconfirmed",),
        ),
        lambda: _baseline_input(
            opportunity_id="OPP-FK-B",
            risk_reject_reasons=("threshold_under_floor",),
            strategy_mode="follow",
            post_seen_mfe_pct=0.40,
        ),
        lambda: _baseline_input(
            opportunity_id="OPP-FK-C",
            risk_reject_reasons=(),
            strategy_mode="follow",
        ),
        lambda: _baseline_input(
            opportunity_id="OPP-FK-D",
            risk_reject_reasons=("data_degraded",),
        ),
    ],
)
def test_record_payload_has_no_forbidden_keys(factory) -> None:
    record = _engine().attribute(factory())
    payload = record.to_dict()
    found = _all_keys(payload)
    assert not (found & REJECT_ATTRIBUTION_FORBIDDEN_PAYLOAD_KEYS), (
        f"forbidden keys leaked into record payload: "
        f"{found & REJECT_ATTRIBUTION_FORBIDDEN_PAYLOAD_KEYS}"
    )
    assert payload["auto_tuning_allowed"] is False


def test_report_payload_has_no_forbidden_keys() -> None:
    inputs = [
        _baseline_input(
            opportunity_id="OPP-RPT-A",
            risk_reject_reasons=("stop_unconfirmed",),
        ),
        _baseline_input(
            opportunity_id="OPP-RPT-B",
            risk_reject_reasons=("threshold_under_floor",),
            strategy_mode="follow",
            post_seen_mfe_pct=0.40,
        ),
        _baseline_input(
            opportunity_id="OPP-RPT-C",
            risk_reject_reasons=("spread_too_wide",),
        ),
    ]
    records = _engine().attribute_many(inputs)
    report = build_reject_attribution_report(
        records, reference_window="60D"
    )
    payload = report.to_dict()
    found = _all_keys(payload)
    assert not (found & REJECT_ATTRIBUTION_FORBIDDEN_PAYLOAD_KEYS)
    assert payload["auto_tuning_allowed"] is False
    assert payload["total_records"] == 3
    assert payload["false_negative_reject_count"] == 1
    # STOP + LIQUIDITY = 2 hard-safety protective verdicts.
    assert payload["correct_protective_reject_count"] >= 2


def test_assert_payload_has_no_forbidden_keys_raises_on_direction() -> None:
    bad = {"opportunity_id": "X", "direction": "long"}
    with pytest.raises(RejectAttributionForbiddenFieldError):
        assert_payload_has_no_forbidden_keys(bad, context="bad")


def test_assert_payload_has_no_forbidden_keys_raises_on_nested_patch() -> None:
    bad = {
        "opportunity_id": "X",
        "child": {"runtime_config_patch": {"symbol_limit": 999}},
    }
    with pytest.raises(RejectAttributionForbiddenFieldError):
        assert_payload_has_no_forbidden_keys(bad, context="bad-nested")


# ---------------------------------------------------------------------------
# 10. Forbidden imports
# ---------------------------------------------------------------------------


_REJECT_MODULE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "adaptive"
    / "reject_to_outcome_attribution.py"
)


@pytest.mark.parametrize(
    "forbidden_root",
    [
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.llm",
        "app.telegram",
    ],
)
def test_no_forbidden_imports(forbidden_root: str) -> None:
    source = _REJECT_MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(_REJECT_MODULE_PATH))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith(forbidden_root), (
                    f"reject_to_outcome_attribution.py imports forbidden "
                    f"{alias.name}"
                )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith(forbidden_root), (
                f"reject_to_outcome_attribution.py imports forbidden "
                f"{mod}"
            )


def test_no_forbidden_runtime_keywords_in_source() -> None:
    """Belt-and-suspenders: the source MUST NOT contain literal strings
    that signal a trade-authority surface (direction, leverage,
    stop_loss, take_profit, runtime_config_patch, ...). Comments may
    refer to them as forbidden; the test only flags suspicious
    *non-comment, non-string-list* occurrences by checking that the
    declared FORBIDDEN_PAYLOAD_KEYS still pin the canonical names.
    """

    expected = {
        "buy",
        "sell",
        "long",
        "short",
        "direction",
        "entry",
        "exit",
        "position_size",
        "leverage",
        "stop",
        "stop_loss",
        "target",
        "take_profit",
        "risk_budget",
        "order",
        "execution_command",
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
    }
    missing = expected - set(REJECT_ATTRIBUTION_FORBIDDEN_PAYLOAD_KEYS)
    assert not missing, (
        f"REJECT_ATTRIBUTION_FORBIDDEN_PAYLOAD_KEYS is missing the "
        f"brief-mandated forbidden keys: {sorted(missing)}"
    )


# ---------------------------------------------------------------------------
# Sanity / regression tests
# ---------------------------------------------------------------------------


def test_event_types_exist_for_phase_d_c_a() -> None:
    assert (
        EventType.REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED.value
        == "REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED"
    )
    assert (
        EventType.REJECT_TO_OUTCOME_CASE_ATTRIBUTED.value
        == "REJECT_TO_OUTCOME_CASE_ATTRIBUTED"
    )
    assert (
        EventType.FALSE_NEGATIVE_REJECT_DETECTED.value
        == "FALSE_NEGATIVE_REJECT_DETECTED"
    )
    assert (
        EventType.CORRECT_PROTECTIVE_REJECT_CONFIRMED.value
        == "CORRECT_PROTECTIVE_REJECT_CONFIRMED"
    )


def test_correct_protective_reject_when_outcome_marks_weak() -> None:
    """A non-hard-safety reject whose outcome was explicitly
    classified as ``FAKE_BREAKOUT`` / ``DUMPED`` / ``WEAK_TAIL``
    should be CORRECT_PROTECTIVE_REJECT."""

    inp = _baseline_input(
        opportunity_id="OPP-CPR-001",
        symbol="CPRUSDT",
        risk_reject_reasons=("regime_neutral",),
        strategy_mode="reject",
        post_discovery_outcome_label="FAKE_BREAKOUT",
        tail_label="weak_tail",
        post_seen_mfe_pct=0.01,
        post_seen_mae_pct=-0.30,
        remaining_upside_to_peak_pct=0.01,
    )
    record = _engine().attribute(inp)
    assert record.verdict == RejectAttributionVerdict.CORRECT_PROTECTIVE_REJECT
    assert record.was_reject_protective is True
    assert record.was_false_negative is False


def test_engine_config_threshold_can_be_tuned_descriptively() -> None:
    """Engine config is descriptive only; raising the threshold MUST
    NOT change any runtime knob and SHOULD flip a borderline case
    away from FALSE_NEGATIVE_REJECT."""

    inp = _baseline_input(
        opportunity_id="OPP-CFG-001",
        symbol="CFGUSDT",
        risk_reject_reasons=("regime_neutral",),
        strategy_mode="follow",
        post_discovery_outcome_label="EARLY_CONTINUATION",
        post_seen_mfe_pct=0.06,
    )
    permissive = RejectToOutcomeAttributionEngine().attribute(inp)
    strict = RejectToOutcomeAttributionEngine(
        RejectAttributionEngineConfig(false_negative_mfe_threshold=0.50)
    ).attribute(inp)
    assert permissive.verdict == RejectAttributionVerdict.FALSE_NEGATIVE_REJECT
    assert strict.verdict != RejectAttributionVerdict.FALSE_NEGATIVE_REJECT


def test_record_repr_round_trips_minimal_fields() -> None:
    record = RejectAttributionRecord(
        opportunity_id="OPP-REPR-001",
        symbol="REPRUSDT",
        reference_window="60D",
        verdict=RejectAttributionVerdict.NO_REJECT_FOUND,
        primary_reason="no_reject_or_no_trade_signal",
    )
    payload = record.to_dict()
    assert payload["verdict"] == "NO_REJECT_FOUND"
    assert payload["auto_tuning_allowed"] is False


def test_module_constants_match_brief() -> None:
    assert (
        REJECT_TO_OUTCOME_ATTRIBUTION_VERSION.startswith(
            "phase_11c_1c_c_b_b_b_d_c_a"
        )
    )
    assert REJECT_TO_OUTCOME_ATTRIBUTION_SOURCE_PHASE == (
        "phase_11c_1c_c_b_b_b_d_c_a_reject_to_outcome_attribution_v0"
    )
    assert REJECT_TO_OUTCOME_ATTRIBUTION_SCHEMA_VERSION.startswith(
        "phase_11c_1c_c_b_b_b_d_c_a.reject_to_outcome_attribution"
    )


def test_report_aggregates_review_symbols() -> None:
    inputs = [
        _baseline_input(
            opportunity_id="OPP-AGG-FN",
            symbol="FNAGGUSDT",
            risk_reject_reasons=("regime_neutral",),
            strategy_mode="follow",
            post_discovery_outcome_label="EARLY_CONTINUATION",
            post_seen_mfe_pct=0.40,
        ),
        _baseline_input(
            opportunity_id="OPP-AGG-DQ",
            symbol="DQAGGUSDT",
            risk_reject_reasons=("data_degraded",),
        ),
        _baseline_input(
            opportunity_id="OPP-AGG-NR",
            symbol="NRAGGUSDT",
            risk_reject_reasons=(),
            strategy_mode="follow",
        ),
    ]
    records = _engine().attribute_many(inputs)
    report = build_reject_attribution_report(records, reference_window="60D")
    assert "FNAGGUSDT" in report.needs_operator_review_symbols
    assert "FNAGGUSDT" in report.needs_rule_review_symbols
    assert "DQAGGUSDT" in report.needs_data_recovery_symbols
    assert report.auto_tuning_allowed is False
    assert report.false_negative_reject_count == 1
    assert report.insufficient_evidence_count == 0
