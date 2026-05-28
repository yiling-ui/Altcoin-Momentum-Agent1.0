"""Unit tests for Phase 11C.1C-C-B-B-B-D-D Discovery Quality
Scorecard v0.

Every test in this module enforces the brief's hard invariants:

  - The scorecard layer is paper / report / evidence only.
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
    serialised scorecard.
  - ``GOOD`` / ``PARTIAL`` / ``WEAK`` / ``DEGRADED`` /
    ``INSUFFICIENT_EVIDENCE`` are *discovery-quality* labels, NOT
    trade-approval labels.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adaptive.discovery_quality_scorecard import (
    DEFAULT_DATA_GAP_RATE_DEGRADED,
    DEFAULT_DATA_GAP_RATE_WARN,
    DEFAULT_FALSE_NEGATIVE_REJECT_RATE_WARN,
    DEFAULT_GOOD_COVERAGE_RATE,
    DEFAULT_GOOD_USABLE_DISCOVERY_RATE,
    DEFAULT_INSUFFICIENT_PRICE_PATH_RATE_DEGRADED,
    DEFAULT_INSUFFICIENT_PRICE_PATH_RATE_WARN,
    DEFAULT_PARTIAL_COVERAGE_RATE,
    DEFAULT_SEVERE_MISS_RATE_DEGRADED,
    DEFAULT_SEVERE_MISS_RATE_WARN,
    DISCOVERY_QUALITY_SCORECARD_FORBIDDEN_PAYLOAD_KEYS,
    DISCOVERY_QUALITY_SCORECARD_SCHEMA_VERSION,
    DiscoveryQualityBucket,
    DiscoveryQualityScorecard,
    DiscoveryQualityScorecardEngine,
    DiscoveryQualityScorecardEngineConfig,
    DiscoveryQualityScorecardForbiddenFieldError,
    DiscoveryQualityScorecardInput,
    assert_payload_has_no_forbidden_keys,
    build_discovery_quality_scorecard,
)
from app.core.events import EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engine() -> DiscoveryQualityScorecardEngine:
    return DiscoveryQualityScorecardEngine(
        DiscoveryQualityScorecardEngineConfig()
    )


def _base_evidence() -> tuple[str, ...]:
    return (
        "evt://historical_mover_coverage_backfill_generated/1",
        "evt://post_discovery_outcome_report_generated/1",
        "evt://reject_to_outcome_attribution_generated/1",
        "evt://severe_missed_tail_triage_generated/1",
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
    return keys & DISCOVERY_QUALITY_SCORECARD_FORBIDDEN_PAYLOAD_KEYS


# ---------------------------------------------------------------------------
# Test 1: insufficient evidence
# ---------------------------------------------------------------------------


def test_insufficient_evidence_when_coverage_total_count_is_zero() -> None:
    """``coverage_total_count == 0`` -> bucket
    ``INSUFFICIENT_EVIDENCE``.
    """

    engine = _engine()
    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=0,
        evidence_refs=_base_evidence(),
    )
    sc = engine.evaluate(inp)
    assert sc.quality_bucket == DiscoveryQualityBucket.INSUFFICIENT_EVIDENCE
    assert sc.coverage_rate == 0.0
    assert sc.usable_discovery_rate == 0.0
    assert sc.needs_operator_review is True
    assert sc.needs_data_recovery is False
    assert sc.needs_rule_review is False
    assert sc.auto_tuning_allowed is False
    assert sc.to_dict()["auto_tuning_allowed"] is False
    assert "insufficient_evidence" in sc.notable_warnings


def test_insufficient_evidence_when_evidence_refs_empty() -> None:
    """Empty ``evidence_refs`` -> bucket ``INSUFFICIENT_EVIDENCE``,
    even if coverage_total_count is non-zero.
    """

    engine = _engine()
    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=100,
        captured_count=80,
        usable_discovery_count=60,
        evidence_refs=(),
    )
    sc = engine.evaluate(inp)
    assert sc.quality_bucket == DiscoveryQualityBucket.INSUFFICIENT_EVIDENCE
    assert sc.needs_operator_review is True
    assert sc.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# Test 2: good / partial quality
# ---------------------------------------------------------------------------


def test_good_quality_when_coverage_and_usable_high_and_misses_low() -> None:
    """High coverage_rate AND high usable_discovery_rate AND low
    severe_miss_rate / data_gap_rate / late_chase_rate -> bucket
    ``GOOD`` or ``PARTIAL``.
    """

    engine = _engine()
    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=100,
        captured_count=85,
        missed_count=15,
        usable_discovery_count=55,
        early_discovery_count=30,
        late_chase_count=10,
        severe_miss_count=2,
        insufficient_price_path_count=10,
        false_negative_reject_count=2,
        correct_protective_reject_count=8,
        data_gap_count=5,
        evidence_refs=_base_evidence(),
    )
    sc = engine.evaluate(inp)

    assert sc.quality_bucket in (
        DiscoveryQualityBucket.GOOD,
        DiscoveryQualityBucket.PARTIAL,
    )
    assert sc.coverage_rate == pytest.approx(0.85)
    assert sc.usable_discovery_rate == pytest.approx(0.55)
    assert sc.early_discovery_rate == pytest.approx(0.30)
    assert sc.severe_miss_rate == pytest.approx(0.02)
    assert sc.data_gap_rate == pytest.approx(0.05)
    assert sc.to_dict()["auto_tuning_allowed"] is False


def test_clean_high_signal_returns_good_bucket() -> None:
    """When every axis is clean and well above the GOOD threshold,
    the engine returns ``GOOD``.
    """

    engine = _engine()
    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=200,
        captured_count=180,
        usable_discovery_count=120,
        early_discovery_count=80,
        late_chase_count=10,
        severe_miss_count=0,
        insufficient_price_path_count=4,
        false_negative_reject_count=2,
        correct_protective_reject_count=20,
        data_gap_count=4,
        evidence_refs=_base_evidence(),
    )
    sc = engine.evaluate(inp)
    assert sc.quality_bucket == DiscoveryQualityBucket.GOOD
    assert sc.needs_operator_review is False
    assert sc.needs_data_recovery is False
    assert sc.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# Test 3: partial / weak / degraded due to data gap or insufficient price path
# ---------------------------------------------------------------------------


def test_high_data_gap_rate_routes_to_data_recovery() -> None:
    """High ``data_gap_rate`` -> bucket at most ``PARTIAL`` /
    ``WEAK`` / ``DEGRADED`` and ``needs_data_recovery=True``.
    """

    engine = _engine()
    # data_gap_count = 25 / 100 = 0.25 -> WARN tier
    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=100,
        captured_count=80,
        usable_discovery_count=40,
        early_discovery_count=20,
        late_chase_count=8,
        severe_miss_count=2,
        insufficient_price_path_count=10,
        false_negative_reject_count=1,
        correct_protective_reject_count=5,
        data_gap_count=25,
        evidence_refs=_base_evidence(),
    )
    sc = engine.evaluate(inp)
    assert sc.quality_bucket in (
        DiscoveryQualityBucket.PARTIAL,
        DiscoveryQualityBucket.WEAK,
        DiscoveryQualityBucket.DEGRADED,
    )
    assert sc.quality_bucket != DiscoveryQualityBucket.GOOD
    assert sc.needs_data_recovery is True
    assert sc.data_gap_rate >= DEFAULT_DATA_GAP_RATE_WARN
    assert sc.to_dict()["auto_tuning_allowed"] is False


def test_severe_data_gap_rate_routes_to_degraded() -> None:
    """When ``data_gap_rate`` crosses the DEGRADED threshold, the
    bucket is ``DEGRADED``.
    """

    engine = _engine()
    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=100,
        captured_count=70,
        usable_discovery_count=30,
        early_discovery_count=15,
        late_chase_count=5,
        severe_miss_count=2,
        insufficient_price_path_count=20,
        false_negative_reject_count=0,
        correct_protective_reject_count=4,
        data_gap_count=60,
        evidence_refs=_base_evidence(),
    )
    sc = engine.evaluate(inp)
    assert sc.quality_bucket == DiscoveryQualityBucket.DEGRADED
    assert sc.needs_data_recovery is True
    assert sc.data_gap_rate >= DEFAULT_DATA_GAP_RATE_DEGRADED
    assert sc.to_dict()["auto_tuning_allowed"] is False


def test_high_insufficient_price_path_rate_routes_to_data_recovery() -> None:
    """High ``insufficient_price_path_rate`` -> bucket at most
    ``PARTIAL`` / ``WEAK`` / ``DEGRADED`` and
    ``needs_data_recovery=True``.
    """

    engine = _engine()
    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=100,
        captured_count=80,
        usable_discovery_count=40,
        early_discovery_count=20,
        late_chase_count=8,
        severe_miss_count=2,
        # 65% of records have insufficient price path -> >= DEGRADED
        insufficient_price_path_count=65,
        false_negative_reject_count=2,
        correct_protective_reject_count=5,
        data_gap_count=5,
        evidence_refs=_base_evidence(),
    )
    sc = engine.evaluate(inp)
    assert sc.quality_bucket == DiscoveryQualityBucket.DEGRADED
    assert sc.needs_data_recovery is True
    assert (
        sc.insufficient_price_path_rate
        >= DEFAULT_INSUFFICIENT_PRICE_PATH_RATE_DEGRADED
    )
    assert sc.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# Test 4: degraded due to severe misses
# ---------------------------------------------------------------------------


def test_high_severe_miss_rate_routes_to_weak_or_degraded() -> None:
    """High ``severe_miss_rate`` -> bucket ``WEAK`` or ``DEGRADED``
    and ``needs_operator_review=True``.
    """

    engine = _engine()
    # severe_miss_rate = 0.30 -> >= DEGRADED threshold (0.25)
    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=100,
        captured_count=85,
        usable_discovery_count=45,
        early_discovery_count=20,
        late_chase_count=10,
        severe_miss_count=30,
        insufficient_price_path_count=10,
        false_negative_reject_count=2,
        correct_protective_reject_count=10,
        data_gap_count=5,
        evidence_refs=_base_evidence(),
    )
    sc = engine.evaluate(inp)
    assert sc.quality_bucket in (
        DiscoveryQualityBucket.WEAK,
        DiscoveryQualityBucket.DEGRADED,
    )
    assert sc.needs_operator_review is True
    assert sc.severe_miss_rate >= DEFAULT_SEVERE_MISS_RATE_WARN
    assert sc.to_dict()["auto_tuning_allowed"] is False


def test_severe_miss_warn_tier_lifts_bucket_to_weak() -> None:
    """A WARN-tier severe_miss_rate (>= warn, < degraded) lifts the
    bucket to at least ``WEAK`` and flips ``needs_operator_review``.
    """

    engine = _engine()
    # severe_miss_rate = 0.15 -> WARN tier (>= 0.10, < 0.25)
    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=100,
        captured_count=85,
        usable_discovery_count=50,
        early_discovery_count=25,
        late_chase_count=8,
        severe_miss_count=15,
        insufficient_price_path_count=8,
        false_negative_reject_count=2,
        correct_protective_reject_count=8,
        data_gap_count=4,
        evidence_refs=_base_evidence(),
    )
    sc = engine.evaluate(inp)
    assert sc.quality_bucket in (
        DiscoveryQualityBucket.WEAK,
        DiscoveryQualityBucket.DEGRADED,
    )
    assert sc.needs_operator_review is True
    assert sc.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# Test 5: false negative reject warning -> rule review (no auto-tuning)
# ---------------------------------------------------------------------------


def test_high_false_negative_reject_rate_routes_to_rule_review() -> None:
    """High ``false_negative_reject_rate`` -> ``needs_rule_review=
    True`` but ``auto_tuning_allowed`` MUST stay ``False``.
    """

    engine = _engine()
    # false_negative_reject_count = 15 / 100 = 0.15 -> >= warn (0.10)
    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=100,
        captured_count=85,
        usable_discovery_count=55,
        early_discovery_count=30,
        late_chase_count=8,
        severe_miss_count=2,
        insufficient_price_path_count=8,
        false_negative_reject_count=15,
        correct_protective_reject_count=10,
        data_gap_count=4,
        evidence_refs=_base_evidence(),
    )
    sc = engine.evaluate(inp)
    assert sc.needs_rule_review is True
    # auto_tuning_allowed MUST stay False even when the rule-review
    # queue is engaged - the brief says auto-tuning is forbidden.
    assert sc.auto_tuning_allowed is False
    assert sc.to_dict()["auto_tuning_allowed"] is False
    assert (
        sc.false_negative_reject_rate >= DEFAULT_FALSE_NEGATIVE_REJECT_RATE_WARN
    )


# ---------------------------------------------------------------------------
# Test 6: root cause summary preserved on output
# ---------------------------------------------------------------------------


def test_root_cause_summary_preserved_on_output() -> None:
    """The ``root_cause_summary`` from the input MUST be carried
    verbatim onto the scorecard output (modulo sorting / int
    coercion).
    """

    engine = _engine()
    summary = {
        "WS_DATA_GAP": 4,
        "PRICE_PATH_MISSING": 7,
        "RISK_REJECTED_FALSE_NEGATIVE": 1,
        "TRUE_DISCOVERY_FAILURE": 2,
    }
    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=80,
        captured_count=60,
        usable_discovery_count=30,
        early_discovery_count=15,
        late_chase_count=5,
        severe_miss_count=4,
        insufficient_price_path_count=12,
        false_negative_reject_count=1,
        correct_protective_reject_count=6,
        data_gap_count=4,
        root_cause_summary=summary,
        evidence_refs=_base_evidence(),
    )
    sc = engine.evaluate(inp)

    assert dict(sc.root_cause_summary) == summary
    payload = sc.to_dict()
    assert payload["root_cause_summary"] == dict(sorted(summary.items()))


# ---------------------------------------------------------------------------
# Test 7: forbidden fields absent on every output payload
# ---------------------------------------------------------------------------


def test_forbidden_fields_absent_on_every_scorecard_payload() -> None:
    """No emitted payload shape (input.to_dict, scorecard.to_dict)
    may contain any of the forbidden trade-authority /
    runtime-tuning keys.
    """

    engine = _engine()
    cases = [
        # 7a. INSUFFICIENT_EVIDENCE
        DiscoveryQualityScorecardInput(
            reference_window="60d",
            coverage_total_count=0,
            evidence_refs=_base_evidence(),
        ),
        # 7b. GOOD
        DiscoveryQualityScorecardInput(
            reference_window="60d",
            coverage_total_count=100,
            captured_count=85,
            usable_discovery_count=60,
            early_discovery_count=40,
            late_chase_count=5,
            severe_miss_count=1,
            insufficient_price_path_count=4,
            false_negative_reject_count=1,
            correct_protective_reject_count=10,
            data_gap_count=2,
            root_cause_summary={"PRICE_PATH_MISSING": 4},
            evidence_refs=_base_evidence(),
        ),
        # 7c. DEGRADED (data gap)
        DiscoveryQualityScorecardInput(
            reference_window="60d",
            coverage_total_count=100,
            captured_count=70,
            usable_discovery_count=30,
            severe_miss_count=2,
            insufficient_price_path_count=20,
            data_gap_count=60,
            evidence_refs=_base_evidence(),
        ),
        # 7d. WEAK (severe miss)
        DiscoveryQualityScorecardInput(
            reference_window="60d",
            coverage_total_count=100,
            captured_count=80,
            usable_discovery_count=40,
            severe_miss_count=18,
            insufficient_price_path_count=8,
            data_gap_count=5,
            evidence_refs=_base_evidence(),
        ),
        # 7e. False negative rule review
        DiscoveryQualityScorecardInput(
            reference_window="60d",
            coverage_total_count=100,
            captured_count=85,
            usable_discovery_count=55,
            severe_miss_count=2,
            false_negative_reject_count=15,
            data_gap_count=2,
            evidence_refs=_base_evidence(),
        ),
    ]
    for inp in cases:
        sc = engine.evaluate(inp)
        # Input payload
        leaked = _payload_contains_forbidden(inp.to_dict())
        assert not leaked, f"input.to_dict leaked forbidden keys: {leaked}"
        # Scorecard payload
        leaked = _payload_contains_forbidden(sc.to_dict())
        assert not leaked, (
            f"scorecard.to_dict leaked forbidden keys: {leaked}"
        )
        # auto_tuning_allowed MUST stay False on every emitted scorecard
        assert sc.to_dict()["auto_tuning_allowed"] is False


def test_forbidden_keys_in_root_cause_summary_raise() -> None:
    """The recursive guard MUST raise if a payload contains a
    forbidden trade-authority key anywhere - including a nested
    root_cause_summary key.
    """

    payload = {
        "schema_version": DISCOVERY_QUALITY_SCORECARD_SCHEMA_VERSION,
        "reference_window": "60d",
        "quality_bucket": DiscoveryQualityBucket.GOOD,
        "auto_tuning_allowed": False,
        # Forbidden trade-authority key smuggled into the payload.
        "position_size": 1.0,
    }
    with pytest.raises(DiscoveryQualityScorecardForbiddenFieldError):
        assert_payload_has_no_forbidden_keys(payload, context="test")


def test_assert_payload_has_no_forbidden_keys_walks_nested_dicts() -> None:
    """Nested dicts must be walked too."""

    payload = {
        "schema_version": DISCOVERY_QUALITY_SCORECARD_SCHEMA_VERSION,
        "reference_window": "60d",
        "nested": {
            "deeper": {
                # Forbidden trade-authority key buried deep.
                "leverage": 5,
            },
        },
    }
    with pytest.raises(DiscoveryQualityScorecardForbiddenFieldError):
        assert_payload_has_no_forbidden_keys(payload, context="test_nested")


# ---------------------------------------------------------------------------
# Test 8: forbidden imports
# ---------------------------------------------------------------------------


def test_module_does_not_import_forbidden_packages() -> None:
    """``app/adaptive/discovery_quality_scorecard.py`` MUST NOT
    import ``app.risk`` / ``app.execution`` / ``app.exchanges`` /
    ``app.llm`` / ``app.telegram``.
    """

    repo_root = Path(__file__).resolve().parents[2]
    module_path = (
        repo_root / "app" / "adaptive" / "discovery_quality_scorecard.py"
    )
    assert module_path.exists(), f"missing source file: {module_path}"
    src = module_path.read_text(encoding="utf-8")

    forbidden_imports = (
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.llm",
        "app.telegram",
    )
    for forbidden in forbidden_imports:
        assert (
            f"import {forbidden}" not in src
            and f"from {forbidden}" not in src
        ), f"discovery_quality_scorecard.py forbidden import: {forbidden}"


# ---------------------------------------------------------------------------
# Auxiliary tests
# ---------------------------------------------------------------------------


def test_event_types_registered_on_event_type_enum() -> None:
    """Both new event types must be members of
    :class:`EventType`.
    """

    assert (
        EventType.DISCOVERY_QUALITY_SCORECARD_GENERATED.value
        == "DISCOVERY_QUALITY_SCORECARD_GENERATED"
    )
    assert (
        EventType.DISCOVERY_QUALITY_BUCKET_EVALUATED.value
        == "DISCOVERY_QUALITY_BUCKET_EVALUATED"
    )


def test_build_discovery_quality_scorecard_convenience_helper() -> None:
    """The module-level ``build_discovery_quality_scorecard`` helper
    is a thin wrapper around the engine.
    """

    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=100,
        captured_count=85,
        usable_discovery_count=55,
        early_discovery_count=30,
        late_chase_count=10,
        severe_miss_count=2,
        insufficient_price_path_count=8,
        false_negative_reject_count=2,
        correct_protective_reject_count=10,
        data_gap_count=4,
        evidence_refs=_base_evidence(),
    )
    sc_helper = build_discovery_quality_scorecard(inp)
    sc_engine = _engine().evaluate(inp)

    assert isinstance(sc_helper, DiscoveryQualityScorecard)
    assert sc_helper.to_dict() == sc_engine.to_dict()


def test_quality_bucket_taxonomy_is_closed_5_label_set() -> None:
    """``DiscoveryQualityBucket.ALL`` must be the closed 5-label set
    the brief mandates.
    """

    assert set(DiscoveryQualityBucket.ALL) == {
        "GOOD",
        "PARTIAL",
        "WEAK",
        "DEGRADED",
        "INSUFFICIENT_EVIDENCE",
    }


def test_unknown_bucket_strings_do_not_appear_in_normal_evaluation() -> None:
    """The engine should never emit a label outside the closed
    taxonomy for any reasonable input.
    """

    engine = _engine()
    cases = [
        # INSUFFICIENT_EVIDENCE
        DiscoveryQualityScorecardInput(
            reference_window="60d",
            coverage_total_count=0,
            evidence_refs=_base_evidence(),
        ),
        # GOOD
        DiscoveryQualityScorecardInput(
            reference_window="60d",
            coverage_total_count=200,
            captured_count=180,
            usable_discovery_count=120,
            early_discovery_count=80,
            late_chase_count=10,
            severe_miss_count=1,
            insufficient_price_path_count=4,
            false_negative_reject_count=2,
            correct_protective_reject_count=20,
            data_gap_count=2,
            evidence_refs=_base_evidence(),
        ),
        # DEGRADED
        DiscoveryQualityScorecardInput(
            reference_window="60d",
            coverage_total_count=100,
            captured_count=40,
            usable_discovery_count=10,
            severe_miss_count=30,
            insufficient_price_path_count=70,
            data_gap_count=70,
            evidence_refs=_base_evidence(),
        ),
    ]
    for inp in cases:
        sc = engine.evaluate(inp)
        assert sc.quality_bucket in DiscoveryQualityBucket.ALL


def test_partial_floor_when_late_chase_high_but_other_axes_clean() -> None:
    """A high ``late_chase_rate`` alone should bump the bucket from
    GOOD to at most PARTIAL even when the other axes are clean.
    """

    engine = _engine()
    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=100,
        captured_count=85,
        usable_discovery_count=55,
        early_discovery_count=20,
        # 45% late chase -> >= warn (0.40)
        late_chase_count=45,
        severe_miss_count=1,
        insufficient_price_path_count=4,
        false_negative_reject_count=1,
        correct_protective_reject_count=8,
        data_gap_count=2,
        evidence_refs=_base_evidence(),
    )
    sc = engine.evaluate(inp)
    assert sc.quality_bucket != DiscoveryQualityBucket.GOOD
    # PARTIAL or worse
    assert sc.quality_bucket in (
        DiscoveryQualityBucket.PARTIAL,
        DiscoveryQualityBucket.WEAK,
        DiscoveryQualityBucket.DEGRADED,
    )
    assert sc.to_dict()["auto_tuning_allowed"] is False


def test_evidence_refs_preserved_in_output() -> None:
    engine = _engine()
    refs = _base_evidence()
    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=100,
        captured_count=80,
        usable_discovery_count=50,
        early_discovery_count=20,
        late_chase_count=8,
        severe_miss_count=2,
        insufficient_price_path_count=8,
        false_negative_reject_count=2,
        correct_protective_reject_count=10,
        data_gap_count=4,
        evidence_refs=refs,
    )
    sc = engine.evaluate(inp)
    assert tuple(sc.evidence_refs) == refs


def test_scorecard_does_not_authorise_trades() -> None:
    """Sanity: every scorecard payload MUST NOT contain any field
    that could be interpreted as a trade authority.
    """

    engine = _engine()
    inp = DiscoveryQualityScorecardInput(
        reference_window="60d",
        coverage_total_count=100,
        captured_count=85,
        usable_discovery_count=55,
        early_discovery_count=30,
        late_chase_count=10,
        severe_miss_count=2,
        insufficient_price_path_count=8,
        false_negative_reject_count=2,
        correct_protective_reject_count=10,
        data_gap_count=4,
        evidence_refs=_base_evidence(),
    )
    sc = engine.evaluate(inp)
    payload = sc.to_dict()

    # No direction / sizing / runtime-knob field.
    forbidden_words = {
        "buy",
        "sell",
        "long",
        "short",
        "direction",
        "side",
        "entry",
        "exit",
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
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
    }
    keys_in_payload = set(_walk_payload(payload))
    assert not (keys_in_payload & forbidden_words)
