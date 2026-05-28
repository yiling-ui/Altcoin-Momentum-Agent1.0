"""Phase AI-5 - Operator Briefing / Evidence Compression v0 tests.

The brief mandates that this test module covers, at minimum:

  1. builds operator briefing from evidence bundle + sandbox output
  2. preserves evidence_refs
  3. unsupported claims appear in unsupported_claims section,
     not key findings
  4. rejected / contradicted claims do not become supported
     findings
  5. data gaps are surfaced
  6. operator action items are review-only, not trade actions
  7. forbidden fields stripped / absent
  8. trade_authority=false
  9. auto_tuning_allowed=false
 10. phase_12_forbidden=true
 11. no Telegram outbound
 12. no Risk / Execution / Strategy / Config consumer
 13. no private account state / API secret leaks
 14. Markdown output generated
 15. JSON output serializable
 16. deterministic output with fake input
 17. forbidden imports
 18. no live LLM / DeepSeek network call required for unit tests

This test module is paper / report / read-only. It does not
authorise live trading, does not authorise auto-tuning, does
not call DeepSeek live, and does not open Phase 12.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from app.ai import (
    AI_EVIDENCE_COMPRESSION_GENERATED,
    AI_EVIDENCE_COMPRESSION_SCHEMA_VERSION,
    AI_EVIDENCE_COMPRESSION_SOURCE_MODULE,
    AI_EVIDENCE_COMPRESSION_SOURCE_PHASE,
    AI_OPERATOR_BRIEFING_GENERATED,
    AI_OPERATOR_BRIEFING_SCHEMA_VERSION,
    AI_OPERATOR_BRIEFING_SOURCE_MODULE,
    AI_OPERATOR_BRIEFING_SOURCE_PHASE,
    AI_UNSUPPORTED_CLAIMS_SUMMARIZED,
    CLAIM_CLASS_CONTRADICTED,
    CLAIM_CLASS_DEGRADED_NO_EVIDENCE,
    CLAIM_CLASS_REJECTED,
    CLAIM_CLASS_SUPPORTED,
    CLAIM_CLASS_UNSUPPORTED,
    FORBIDDEN_AI_OUTPUT_FIELDS,
    EvidenceCompressionReport,
    EvidenceCompressionReportBuilder,
    OperatorBriefing,
    OperatorBriefingAuthorityLevel,
    OperatorBriefingBuilder,
    OperatorBriefingFinding,
    OperatorBriefingSection,
    OperatorBriefingSectionRecord,
    build_evidence_compression_report,
    build_operator_briefing,
    classify_claim,
    render_evidence_compression_report_markdown,
    render_operator_briefing_markdown,
)


# ---------------------------------------------------------------------------
# Source paths (used by the static-analysis tests)
# ---------------------------------------------------------------------------
BRIEFING_SRC_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "ai"
    / "operator_briefing.py"
)
COMPRESSION_SRC_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "ai"
    / "evidence_compression.py"
)
INIT_SRC_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "ai"
    / "__init__.py"
)
RUNNER_SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "run_ai_operator_briefing.py"
)
RISK_PKG_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "risk"
)
EXECUTION_PKG_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "execution"
)
EXCHANGES_PKG_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "exchanges"
)
TELEGRAM_PKG_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "telegram"
)
CONFIG_PKG_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "config"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _safe_lookahead_policy() -> dict[str, bool]:
    return {
        "frozen_evidence_only": True,
        "no_future_market_data": True,
        "no_training_from_ai_output": True,
        "no_runtime_feedback": True,
        "post_hoc_analysis_only_when_window_closed": True,
    }


def _make_bundle(*, bundle_id: str = "bundle-1") -> dict[str, Any]:
    """Return a minimal but representative serialised
    Phase AI-1 evidence bundle."""

    return {
        "schema_version": "v0",
        "source_phase": "phase_ai_1",
        "source_module": "ai_evidence_bundle_builder",
        "bundle_id": bundle_id,
        "created_at_utc": "2026-05-28T00:00:00Z",
        "task_type": "OPERATOR_BRIEFING",
        "build_status": "EVIDENCE_BUNDLE_BUILT",
        "phase_context": {"phase": "phase_ai_5", "block": "AI"},
        "reference_window": "60d",
        "market_facts": [
            {
                "schema_version": "v0",
                "fact_id": "market.breadth.60d",
                "fact_type": "market_breadth",
                "evidence_refs": [
                    "report:post_discovery_outcome_report"
                ],
                "source_report": "post_discovery_outcome_report",
                "status": "ACCEPTED",
                "degradation_reason": None,
                "content": {
                    "breadth_score": 0.78,
                    "breadth_weak": False,
                    "data_gap_rate": 0.05,
                    "data_gap_severe": False,
                },
            }
        ],
        "system_behavior_facts": [
            {
                "schema_version": "v0",
                "fact_id": "system.late_chase.60d",
                "fact_type": "system_behavior",
                "evidence_refs": [
                    "report:post_discovery_outcome_report"
                ],
                "source_report": "post_discovery_outcome_report",
                "status": "ACCEPTED",
                "degradation_reason": None,
                "content": {
                    "late_chase_high": False,
                    "late_chase_rate": 0.1,
                    "fake_breakout_rising": False,
                    "funding_overheated": False,
                },
            }
        ],
        "outcome_facts": [
            {
                "schema_version": "v0",
                "fact_id": "outcome.failed_continuation.60d",
                "fact_type": "outcome",
                "evidence_refs": [
                    "report:post_discovery_outcome_report"
                ],
                "source_report": "post_discovery_outcome_report",
                "status": "ACCEPTED",
                "degradation_reason": None,
                "content": {
                    "failed_continuation": False,
                    "missed_strong_tail_rate": 0.2,
                },
            }
        ],
        "replay_facts": [],
        "reflection_facts": [],
        "evidence_contract_facts": [],
        "degraded_facts": [],
        "evidence_refs": [
            "report:post_discovery_outcome_report",
        ],
        "source_reports": ["post_discovery_outcome_report"],
        "forbidden_fields": sorted(FORBIDDEN_AI_OUTPUT_FIELDS),
        "lookahead_policy": _safe_lookahead_policy(),
        "consumer_contract": {
            "allowed_consumers": [
                "human_operator",
                "export_bundle",
                "replay_annotation",
                "reflection_annotation",
                "operator_briefing_report",
            ],
            "forbidden_consumers": [
                "RiskEngine",
                "ExecutionFSM",
                "StrategyEngine",
                "ExchangeGateway",
                "RuntimeConfig",
                "TelegramLiveCommand",
                "CapitalFlow",
                "PositionManager",
            ],
        },
        "warnings": [],
        "accepted_fact_count": 3,
        "degraded_fact_count": 0,
        "ai_output_is_commentary_only": True,
        "ai_output_can_be_training_label": False,
        "phase_12_forbidden": True,
        "auto_tuning_allowed": False,
        "safety_flags": {
            "mode": "paper",
            "live_trading": False,
            "exchange_live_orders": False,
            "right_tail": False,
            "llm": False,
            "telegram_outbound_enabled": False,
            "binance_private_api_enabled": False,
        },
    }


def _make_ai_output(
    *,
    bundle_id: str = "bundle-1",
    claims: list[dict[str, Any]] | None = None,
    contradictions: list[str] | None = None,
    unsupported_claims: list[str] | None = None,
    risk_tags: list[str] | None = None,
    summary: str | None = None,
    status: str = "OK",
    authority_level: str = "SUPPORTED_INTELLIGENCE",
    reality_check_status: str = "SUPPORTED",
) -> dict[str, Any]:
    """Return a minimal but representative serialised Phase
    AI-4 AIIntelligenceOutput."""

    if claims is None:
        claims = [
            {
                "claim_id": "claim-1",
                "claim_type": "REGIME",
                "claim_text": (
                    "60d breadth score 0.78 indicates broad "
                    "discovery is currently stable."
                ),
                "evidence_refs": [
                    "symbol:RAVEUSDT",
                    "report:post_discovery_outcome_report",
                ],
                "truth_layer_fields_used": [
                    "market_facts.breadth_score",
                    "outcome_facts.missed_strong_tail_rate",
                ],
                "citation_authority_level": "SUPPORTED_INTELLIGENCE",
                "reality_check_status": "SUPPORTED",
                "reality_check_authority_level": (
                    "SUPPORTED_INTELLIGENCE"
                ),
                "confidence_raw": 0.6,
                "confidence_reality_checked": 0.6,
                "warnings": [],
            }
        ]
    return {
        "schema_version": "v0",
        "source_phase": "phase_ai_4",
        "source_module": "ai_intelligence_output",
        "bundle_id": bundle_id,
        "task_type": "OPERATOR_BRIEFING_DRAFT",
        "summary": (
            summary
            if summary is not None
            else (
                "60d altcoin discovery quality is currently "
                "stable on the audit window."
            )
        ),
        "claims": claims,
        "contradictions": contradictions or [],
        "unsupported_claims": unsupported_claims or [],
        "risk_tags": risk_tags or [],
        "evidence_refs": [
            "symbol:RAVEUSDT",
            "report:post_discovery_outcome_report",
        ],
        "reality_check_status": reality_check_status,
        "authority_level": authority_level,
        "status": status,
        "forbidden_fields_stripped": [],
        "redacted_secret_count": 0,
        "warnings": [],
        "degraded_reasons": [],
        "stateless_inference": True,
        "feedback_isolation": True,
        "trade_authority": False,
        "auto_tuning_allowed": False,
        "phase_12_forbidden": True,
        "ai_output_is_commentary_only": True,
        "ai_output_can_be_training_label": False,
        "safety_flags": {
            "mode": "paper",
            "live_trading": False,
            "exchange_live_orders": False,
            "right_tail": False,
            "llm": False,
            "llm_outbound_enabled": False,
            "sandbox_only": True,
            "telegram_outbound_enabled": False,
            "binance_private_api_enabled": False,
        },
        "forbidden_fields": sorted(FORBIDDEN_AI_OUTPUT_FIELDS),
    }


def _make_block_c_report(
    *,
    status: str = "EVIDENCE_GENERATED",
    replay_status: str = "EVIDENCE_GENERATED",
    reflection_status: str = "EVIDENCE_GENERATED",
    evidence_contract_status: str = "EVIDENCE_GENERATED",
    accepted_claim_count: int = 2704,
    known_blockers: list[str] | None = None,
    phase_12_forbidden: bool = True,
    auto_tuning_allowed: bool = False,
) -> dict[str, Any]:
    return {
        "status": status,
        "replay_status": replay_status,
        "reflection_status": reflection_status,
        "evidence_contract_status": evidence_contract_status,
        "accepted_claim_count": int(accepted_claim_count),
        "known_blockers": known_blockers or [],
        "phase_12_forbidden": bool(phase_12_forbidden),
        "auto_tuning_allowed": bool(auto_tuning_allowed),
    }


def _build_briefing(
    *,
    bundle: dict[str, Any] | None = None,
    ai_output: dict[str, Any] | None = None,
    block_c: dict[str, Any] | None = None,
    briefing_id: str = "briefing-1",
    created_at_utc: str = "2026-05-28T01:00:00Z",
    reference_window: str = "60d",
) -> tuple[OperatorBriefing, EvidenceCompressionReport]:
    if bundle is None:
        bundle = _make_bundle()
    if ai_output is None:
        ai_output = _make_ai_output(
            bundle_id=str(bundle.get("bundle_id", "bundle-1"))
        )
    if block_c is None:
        block_c = _make_block_c_report()
    return build_operator_briefing(
        briefing_id=briefing_id,
        created_at_utc=created_at_utc,
        evidence_bundle=bundle,
        ai_intelligence_output=ai_output,
        block_c_report=block_c,
        reference_window=reference_window,
    )


# ---------------------------------------------------------------------------
# 1. builds operator briefing from evidence bundle + sandbox output
# ---------------------------------------------------------------------------
def test_builder_returns_operator_briefing_and_compression() -> None:
    briefing, compression = _build_briefing()
    assert isinstance(briefing, OperatorBriefing)
    assert isinstance(compression, EvidenceCompressionReport)
    assert briefing.briefing_id == "briefing-1"
    assert briefing.source_bundle_id == "bundle-1"
    assert briefing.reference_window == "60d"
    assert (
        briefing.source_block_c_status == "EVIDENCE_GENERATED"
    )


def test_builder_produces_one_section_per_enum_value() -> None:
    briefing, _ = _build_briefing()
    sections_seen = [s.section for s in briefing.sections]
    assert sections_seen == list(OperatorBriefingSection)
    # Section titles are non-empty.
    for section in briefing.sections:
        assert isinstance(section, OperatorBriefingSectionRecord)
        assert section.title
        assert section.body


def test_builder_rejects_non_mapping_bundle() -> None:
    with pytest.raises(TypeError):
        OperatorBriefingBuilder().build(
            briefing_id="b1",
            created_at_utc="2026-05-28T01:00:00Z",
            evidence_bundle=[1, 2, 3],  # type: ignore[arg-type]
            ai_intelligence_output=_make_ai_output(),
        )


def test_builder_rejects_non_mapping_ai_output() -> None:
    with pytest.raises(TypeError):
        OperatorBriefingBuilder().build(
            briefing_id="b1",
            created_at_utc="2026-05-28T01:00:00Z",
            evidence_bundle=_make_bundle(),
            ai_intelligence_output=[1, 2, 3],  # type: ignore[arg-type]
        )


def test_builder_rejects_non_mapping_block_c() -> None:
    with pytest.raises(TypeError):
        OperatorBriefingBuilder().build(
            briefing_id="b1",
            created_at_utc="2026-05-28T01:00:00Z",
            evidence_bundle=_make_bundle(),
            ai_intelligence_output=_make_ai_output(),
            block_c_report="not a mapping",  # type: ignore[arg-type]
        )


def test_builder_rejects_empty_briefing_id() -> None:
    with pytest.raises(ValueError):
        OperatorBriefingBuilder().build(
            briefing_id="   ",
            created_at_utc="2026-05-28T01:00:00Z",
            evidence_bundle=_make_bundle(),
            ai_intelligence_output=_make_ai_output(),
        )


def test_builder_rejects_empty_created_at() -> None:
    with pytest.raises(ValueError):
        OperatorBriefingBuilder().build(
            briefing_id="b1",
            created_at_utc="",
            evidence_bundle=_make_bundle(),
            ai_intelligence_output=_make_ai_output(),
        )


# ---------------------------------------------------------------------------
# 2. preserves evidence_refs
# ---------------------------------------------------------------------------
def test_evidence_refs_preserved_on_briefing() -> None:
    briefing, _ = _build_briefing()
    assert "symbol:RAVEUSDT" in briefing.evidence_refs
    assert (
        "report:post_discovery_outcome_report"
        in briefing.evidence_refs
    )
    # Findings preserve evidence_refs too.
    findings_with_refs = [
        f
        for section in briefing.sections
        for f in section.findings
        if f.evidence_refs
    ]
    assert findings_with_refs
    assert any(
        "symbol:RAVEUSDT" in f.evidence_refs
        for f in findings_with_refs
    )


def test_evidence_refs_preserved_on_compression_report() -> None:
    _, compression = _build_briefing()
    assert (
        "symbol:RAVEUSDT" in compression.evidence_refs
    )
    assert (
        "report:post_discovery_outcome_report"
        in compression.evidence_refs
    )


def test_compression_report_preserves_per_claim_evidence_refs() -> None:
    _, compression = _build_briefing()
    assert compression.compressed_claims
    claim = compression.compressed_claims[0]
    assert "symbol:RAVEUSDT" in claim.evidence_refs
    assert (
        "report:post_discovery_outcome_report"
        in claim.evidence_refs
    )


# ---------------------------------------------------------------------------
# 3. unsupported claims appear in unsupported_claims section,
#    not key findings
# ---------------------------------------------------------------------------
def test_unsupported_claim_does_not_become_key_finding() -> None:
    ai_output = _make_ai_output(
        claims=[
            {
                "claim_id": "claim-unsupported",
                "claim_type": "NARRATIVE",
                "claim_text": (
                    "Unsupported intuition about future flows."
                ),
                "evidence_refs": [],
                "truth_layer_fields_used": [],
                "citation_authority_level": "DEGRADED_NO_EVIDENCE",
                "reality_check_status": "INSUFFICIENT_EVIDENCE",
                "reality_check_authority_level": (
                    "DEGRADED_NO_EVIDENCE"
                ),
                "confidence_raw": 0.5,
                "confidence_reality_checked": 0.0,
                "warnings": ["missing_evidence_refs"],
            }
        ],
        unsupported_claims=["claim-unsupported"],
        status="DEGRADED_MISSING_EVIDENCE",
        authority_level="DEGRADED_NO_EVIDENCE",
        reality_check_status="INSUFFICIENT_EVIDENCE",
    )
    briefing, _ = _build_briefing(ai_output=ai_output)
    assert "claim-unsupported" not in briefing.key_findings
    assert "claim-unsupported" in briefing.unsupported_claims
    # The claim is surfaced in the UNSUPPORTED_CLAIMS section.
    unsupported_section = next(
        s
        for s in briefing.sections
        if s.section is OperatorBriefingSection.UNSUPPORTED_CLAIMS
    )
    related_ids = [
        cid
        for f in unsupported_section.findings
        for cid in f.related_claim_ids
    ]
    assert "claim-unsupported" in related_ids


def test_degraded_no_evidence_claim_classified_correctly() -> None:
    classification = classify_claim(
        citation_authority_level="DEGRADED_NO_EVIDENCE",
        reality_check_status="INSUFFICIENT_EVIDENCE",
        reality_check_authority_level="DEGRADED_NO_EVIDENCE",
        has_evidence_refs=False,
    )
    assert classification == CLAIM_CLASS_DEGRADED_NO_EVIDENCE


# ---------------------------------------------------------------------------
# 4. rejected / contradicted claims do not become supported findings
# ---------------------------------------------------------------------------
def test_contradicted_claim_does_not_become_key_finding() -> None:
    ai_output = _make_ai_output(
        claims=[
            {
                "claim_id": "claim-contradicted",
                "claim_type": "REGIME",
                "claim_text": (
                    "Risk appetite expanding rapidly across "
                    "the breadth."
                ),
                "evidence_refs": ["symbol:BTCUSDT"],
                "truth_layer_fields_used": [
                    "market_facts.breadth_score"
                ],
                "citation_authority_level": "SUPPORTED_INTELLIGENCE",
                "reality_check_status": "CONTRADICTED",
                "reality_check_authority_level": (
                    "REJECTED_BY_REALITY_CHECK"
                ),
                "confidence_raw": 0.7,
                "confidence_reality_checked": 0.0,
                "warnings": ["contradicted_by_market_facts"],
            }
        ],
        contradictions=["claim-contradicted"],
        status="DEGRADED_REALITY_CHECK",
        authority_level="DEGRADED_REALITY_CHECK",
        reality_check_status="CONTRADICTED",
    )
    briefing, _ = _build_briefing(ai_output=ai_output)
    assert "claim-contradicted" not in briefing.key_findings
    assert "claim-contradicted" in briefing.contradictions
    contradictions_section = next(
        s
        for s in briefing.sections
        if s.section is OperatorBriefingSection.CONTRADICTIONS
    )
    related_ids = [
        cid
        for f in contradictions_section.findings
        for cid in f.related_claim_ids
    ]
    assert "claim-contradicted" in related_ids


def test_rejected_claim_does_not_become_key_finding() -> None:
    ai_output = _make_ai_output(
        claims=[
            {
                "claim_id": "claim-rejected",
                "claim_type": "NARRATIVE",
                "claim_text": (
                    "Smart money is definitely entering."
                ),
                "evidence_refs": ["symbol:BTCUSDT"],
                "truth_layer_fields_used": [],
                "citation_authority_level": "SUPPORTED_INTELLIGENCE",
                "reality_check_status": (
                    "REJECTED_UNVERIFIABLE_NARRATIVE"
                ),
                "reality_check_authority_level": (
                    "REJECTED_BY_REALITY_CHECK"
                ),
                "confidence_raw": 0.9,
                "confidence_reality_checked": 0.0,
                "warnings": ["unverifiable_narrative"],
            }
        ],
        unsupported_claims=["claim-rejected"],
        status="DEGRADED_REALITY_CHECK",
        authority_level="DEGRADED_REALITY_CHECK",
        reality_check_status="REJECTED_UNVERIFIABLE_NARRATIVE",
    )
    briefing, compression = _build_briefing(ai_output=ai_output)
    assert "claim-rejected" not in briefing.key_findings
    assert "claim-rejected" in briefing.unsupported_claims
    assert "claim-rejected" in compression.rejected_claims


# ---------------------------------------------------------------------------
# 5. data gaps are surfaced
# ---------------------------------------------------------------------------
def test_data_gaps_are_surfaced_when_bundle_flags_them() -> None:
    bundle = _make_bundle()
    bundle["market_facts"][0]["content"]["data_gap_severe"] = True
    bundle["market_facts"][0]["content"]["data_gap_rate"] = 0.6
    bundle["system_behavior_facts"][0]["content"][
        "late_chase_high"
    ] = True
    bundle["outcome_facts"][0]["content"][
        "missed_strong_tail_rate"
    ] = 0.8
    briefing, _ = _build_briefing(bundle=bundle)
    assert briefing.data_gaps
    flagged_keys = " ".join(briefing.data_gaps)
    assert "market_facts.data_gap_severe" in flagged_keys
    assert "market_facts.data_gap_rate" in flagged_keys
    assert "system_behavior_facts.late_chase_high" in flagged_keys
    assert (
        "outcome_facts.missed_strong_tail_rate" in flagged_keys
    )
    # Findings under the DATA_GAPS section also exist.
    data_gaps_section = next(
        s
        for s in briefing.sections
        if s.section is OperatorBriefingSection.DATA_GAPS
    )
    assert data_gaps_section.findings


def test_no_data_gaps_when_bundle_clean() -> None:
    briefing, _ = _build_briefing()
    assert briefing.data_gaps == ()


# ---------------------------------------------------------------------------
# 6. operator action items are review-only, not trade actions
# ---------------------------------------------------------------------------
def test_operator_action_items_review_only() -> None:
    bundle = _make_bundle()
    bundle["market_facts"][0]["content"]["data_gap_severe"] = True
    ai_output = _make_ai_output(
        claims=[
            {
                "claim_id": "claim-c1",
                "claim_type": "NARRATIVE",
                "claim_text": "Unsupported intuition.",
                "evidence_refs": [],
                "truth_layer_fields_used": [],
                "citation_authority_level": "DEGRADED_NO_EVIDENCE",
                "reality_check_status": "INSUFFICIENT_EVIDENCE",
                "reality_check_authority_level": (
                    "DEGRADED_NO_EVIDENCE"
                ),
                "confidence_raw": 0.4,
                "confidence_reality_checked": 0.0,
                "warnings": ["missing_evidence_refs"],
            }
        ],
        unsupported_claims=["claim-c1"],
    )
    block_c = _make_block_c_report(
        known_blockers=["replay_blocker_a"]
    )
    briefing, _ = _build_briefing(
        bundle=bundle, ai_output=ai_output, block_c=block_c
    )
    items = briefing.operator_review_items
    assert items
    # All items are review-shaped strings; none start with a
    # trade-action verb.
    forbidden_prefixes = (
        "buy",
        "sell",
        "long",
        "short",
        "enter",
        "exit",
        "place_order",
        "open_position",
        "close_position",
        "execute",
    )
    for item in items:
        assert isinstance(item, str)
        text = item.lower()
        assert not any(
            text.startswith(p) for p in forbidden_prefixes
        )
        # A review-only item must start with one of the
        # "review_" / "block_c_blocker" markers.
        assert (
            text.startswith("review_")
            or text.startswith("block_c_blocker")
        ), f"unexpected operator item: {item!r}"


def test_findings_carry_review_only_true() -> None:
    briefing, _ = _build_briefing()
    for section in briefing.sections:
        for finding in section.findings:
            payload = finding.to_dict()
            assert payload["review_only"] is True


# ---------------------------------------------------------------------------
# 7. forbidden fields stripped / absent
# ---------------------------------------------------------------------------
FORBIDDEN_FIELD_SAMPLES = [
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
    "strategy_parameter_patch",
    "signal_to_trade",
    "should_buy",
    "should_short",
]


@pytest.mark.parametrize("field", FORBIDDEN_FIELD_SAMPLES)
def test_forbidden_field_smuggled_in_ai_output_is_stripped(
    field: str,
) -> None:
    ai_output = _make_ai_output()
    ai_output[field] = "anything"
    briefing, compression = _build_briefing(ai_output=ai_output)
    # Both artefacts strip the field.
    assert field in compression.forbidden_fields_stripped
    # The briefing's audit trail records the strip too (the
    # briefing builder runs strip_forbidden_fields a second
    # time as defence in depth).
    assert field in briefing.forbidden_fields_stripped
    # And the field NEVER appears as a KEY in the serialised
    # briefing.
    decoded = briefing.to_dict()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                assert (
                    key not in FORBIDDEN_AI_OUTPUT_FIELDS
                ), f"forbidden key {key!r} survived"
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(decoded)


@pytest.mark.parametrize("field", FORBIDDEN_FIELD_SAMPLES)
def test_forbidden_field_absent_in_clean_briefing_payload(
    field: str,
) -> None:
    briefing, _ = _build_briefing()
    decoded = briefing.to_dict()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            assert field not in node
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(decoded)


# ---------------------------------------------------------------------------
# 8. trade_authority=false
# ---------------------------------------------------------------------------
def test_briefing_pins_trade_authority_false() -> None:
    briefing, compression = _build_briefing()
    assert briefing.to_dict()["trade_authority"] is False
    assert compression.to_dict()["trade_authority"] is False


def test_briefing_repins_trade_authority_even_if_field_flipped() -> None:
    briefing, _ = _build_briefing()
    object.__setattr__(briefing, "trade_authority", True)
    object.__setattr__(briefing, "auto_tuning_allowed", True)
    object.__setattr__(briefing, "phase_12_forbidden", False)
    object.__setattr__(briefing, "stateless_inference", False)
    object.__setattr__(briefing, "feedback_isolation", False)
    object.__setattr__(
        briefing, "ai_output_is_commentary_only", False
    )
    object.__setattr__(
        briefing, "ai_output_can_be_training_label", True
    )
    payload = briefing.to_dict()
    assert payload["trade_authority"] is False
    assert payload["auto_tuning_allowed"] is False
    assert payload["phase_12_forbidden"] is True
    assert payload["stateless_inference"] is True
    assert payload["feedback_isolation"] is True
    assert payload["ai_output_is_commentary_only"] is True
    assert payload["ai_output_can_be_training_label"] is False


def test_authority_level_has_no_trade_member() -> None:
    members = {m.value for m in OperatorBriefingAuthorityLevel}
    assert members == {
        "COMMENTARY_SUBSTRATE",
        "DEGRADED_PARTIAL_EVIDENCE",
        "DEGRADED_NO_EVIDENCE",
        "REJECTED",
    }


# ---------------------------------------------------------------------------
# 9. auto_tuning_allowed=false
# ---------------------------------------------------------------------------
def test_briefing_pins_auto_tuning_allowed_false() -> None:
    briefing, compression = _build_briefing()
    assert briefing.to_dict()["auto_tuning_allowed"] is False
    assert compression.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# 10. phase_12_forbidden=true
# ---------------------------------------------------------------------------
def test_briefing_pins_phase_12_forbidden_true() -> None:
    briefing, compression = _build_briefing()
    assert briefing.to_dict()["phase_12_forbidden"] is True
    assert compression.to_dict()["phase_12_forbidden"] is True


def test_briefing_pins_safety_flags() -> None:
    briefing, _ = _build_briefing()
    safety = briefing.to_dict()["safety_flags"]
    assert safety["mode"] == "paper"
    assert safety["live_trading"] is False
    assert safety["exchange_live_orders"] is False
    assert safety["right_tail"] is False
    assert safety["llm"] is False
    assert safety["llm_outbound_enabled"] is False
    assert safety["sandbox_only"] is True
    assert safety["telegram_outbound_enabled"] is False
    assert safety["binance_private_api_enabled"] is False


# ---------------------------------------------------------------------------
# 11. no Telegram outbound
# ---------------------------------------------------------------------------
FORBIDDEN_HOT_PATH_PREFIXES = (
    "app.risk",
    "app.execution",
    "app.exchanges",
    "app.telegram",
    "app.config",
)

FORBIDDEN_NETWORK_MODULES = (
    "openai",
    "anthropic",
    "deepseek",
    "httpx",
    "requests",
    "aiohttp",
    "urllib3",
    "websocket",
    "websockets",
    "grpc",
    "boto3",
    "socket",
)


def _collect_imports(src_text: str) -> list[str]:
    tree = ast.parse(src_text)
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            out.append(module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name)
    return out


def test_briefing_module_has_no_telegram_outbound_path() -> None:
    """The Phase AI-5 modules MUST NOT import the Telegram /
    Telegram-outbound surface."""
    for src_path in (
        BRIEFING_SRC_PATH,
        COMPRESSION_SRC_PATH,
        RUNNER_SCRIPT_PATH,
    ):
        modules = _collect_imports(
            src_path.read_text(encoding="utf-8")
        )
        for m in modules:
            assert not m.startswith("app.telegram"), (
                f"{src_path.name} imports {m!r}; the Phase AI-5 "
                "modules must not call the Telegram surface."
            )


def test_briefing_source_contains_no_telegram_send_shape() -> None:
    """Defensive string scan: the source MUST NOT contain a
    ``telegram.send(`` / ``send_message(`` / ``post_to_chat_id(`` /
    ``call_telegram(`` shape."""
    forbidden_shapes = (
        "telegram.send",
        "TelegramOutbound(",
        "send_telegram_message(",
        "post_to_chat_id(",
        "call_telegram(",
        "requests.post(",
        "httpx.post(",
        "aiohttp.ClientSession(",
        "websocket.create_connection(",
        "websockets.connect(",
        "socket.socket(",
    )
    for src_path in (BRIEFING_SRC_PATH, COMPRESSION_SRC_PATH):
        src = src_path.read_text(encoding="utf-8")
        for shape in forbidden_shapes:
            assert shape not in src, (
                f"{src_path.name} contains forbidden call "
                f"shape {shape!r}; Phase AI-5 is read-only / "
                "no-network."
            )


# ---------------------------------------------------------------------------
# 12. no Risk / Execution / Strategy / Config consumer
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "src_path",
    [BRIEFING_SRC_PATH, COMPRESSION_SRC_PATH, RUNNER_SCRIPT_PATH],
)
def test_phase_ai_5_module_does_not_import_hot_path(
    src_path: Path,
) -> None:
    modules = _collect_imports(src_path.read_text(encoding="utf-8"))
    bad = [
        m
        for m in modules
        if any(
            m == pre or m.startswith(pre + ".")
            for pre in FORBIDDEN_HOT_PATH_PREFIXES
        )
    ]
    assert not bad, (
        f"{src_path.name} imports forbidden hot-path modules: "
        f"{bad!r}; this violates the Phase AI-5 boundary."
    )


@pytest.mark.parametrize(
    "src_path",
    [BRIEFING_SRC_PATH, COMPRESSION_SRC_PATH, RUNNER_SCRIPT_PATH],
)
def test_phase_ai_5_module_does_not_import_network(
    src_path: Path,
) -> None:
    modules = _collect_imports(src_path.read_text(encoding="utf-8"))
    bad = [
        m
        for m in modules
        if any(
            m == pre or m.startswith(pre + ".")
            for pre in FORBIDDEN_NETWORK_MODULES
        )
    ]
    assert not bad, (
        f"{src_path.name} imports forbidden network modules: "
        f"{bad!r}; the Phase AI-5 builder is offline-only."
    )


def _walk_python_files(root: Path):
    for path in root.rglob("*.py"):
        yield path


@pytest.mark.parametrize(
    "pkg_root",
    [
        RISK_PKG_PATH,
        EXECUTION_PKG_PATH,
        EXCHANGES_PKG_PATH,
        TELEGRAM_PKG_PATH,
        CONFIG_PKG_PATH,
    ],
)
def test_risk_execution_exchange_telegram_config_do_not_import_app_ai(
    pkg_root: Path,
) -> None:
    """The Risk / Execution / Exchange / Telegram / Config
    packages MUST NOT import ``app.ai`` (any submodule)."""
    if not pkg_root.exists():
        pytest.skip(f"{pkg_root} not present in this checkout")
    bad: list[tuple[str, str]] = []
    for path in _walk_python_files(pkg_root):
        try:
            modules = _collect_imports(
                path.read_text(encoding="utf-8")
            )
        except SyntaxError:
            continue
        for m in modules:
            if m == "app.ai" or m.startswith("app.ai."):
                bad.append((str(path), m))
    assert not bad, (
        f"{pkg_root.name} package imports app.ai: {bad!r}; "
        "AI output is commentary-only and must not reach the "
        "trade-decision gate."
    )


# ---------------------------------------------------------------------------
# 13. no private account state / API secret leaks
# ---------------------------------------------------------------------------
def test_credential_shaped_value_redacted_in_briefing() -> None:
    ai_output = _make_ai_output()
    # Smuggle a credential-shaped key value.
    ai_output["claims"][0]["deepseek_api_key"] = "sk-secret-xyz"
    ai_output["telegram_bot_token"] = "raw-token-1234567890"
    briefing, compression = _build_briefing(ai_output=ai_output)
    decoded = json.dumps(briefing.to_dict())
    decoded_compression = json.dumps(compression.to_dict())
    assert "sk-secret-xyz" not in decoded
    assert "sk-secret-xyz" not in decoded_compression
    assert "raw-token-1234567890" not in decoded
    assert "raw-token-1234567890" not in decoded_compression
    assert briefing.redacted_secret_count >= 1
    assert compression.redacted_secret_count >= 1


def test_briefing_does_not_carry_private_account_state() -> None:
    """Defensive: the briefing must not propagate keys that
    look like private exchange / account state."""
    briefing, _ = _build_briefing()
    decoded = json.dumps(briefing.to_dict())
    forbidden_substrings = (
        "account_balance",
        "account_orders",
        "account_positions",
        "account_leverage",
        "account_margin",
        "wallet_balance",
        "binance_account_state",
        "listenKey",
        "signed_endpoint_payload",
    )
    for token in forbidden_substrings:
        assert token not in decoded, (
            f"briefing leaked private-account-state token: "
            f"{token!r}"
        )


# ---------------------------------------------------------------------------
# 14. Markdown output generated
# ---------------------------------------------------------------------------
def test_render_markdown_emits_non_empty_briefing() -> None:
    briefing, _ = _build_briefing()
    md = render_operator_briefing_markdown(briefing)
    assert "# AI Operator Briefing v0" in md
    assert "## Executive summary" in md
    assert "## Operator review items (review-only)" in md
    assert "## Safety boundary (held end-to-end)" in md
    # The Markdown surfaces the briefing identifier.
    assert briefing.briefing_id in md


def test_render_markdown_emits_non_empty_compression() -> None:
    _, compression = _build_briefing()
    md = render_evidence_compression_report_markdown(compression)
    assert "# AI Evidence Compression Report v0" in md
    assert compression.report_id in md
    assert "## Safety boundary (held end-to-end)" in md


# ---------------------------------------------------------------------------
# 15. JSON output serializable
# ---------------------------------------------------------------------------
def test_briefing_round_trips_as_json() -> None:
    briefing, compression = _build_briefing()
    encoded = json.dumps(briefing.to_dict())
    decoded = json.loads(encoded)
    assert decoded == briefing.to_dict()
    encoded_compression = json.dumps(compression.to_dict())
    decoded_compression = json.loads(encoded_compression)
    assert decoded_compression == compression.to_dict()


# ---------------------------------------------------------------------------
# 16. deterministic output with fake input
# ---------------------------------------------------------------------------
def test_same_input_same_output_is_deterministic() -> None:
    bundle = _make_bundle()
    ai_output = _make_ai_output()
    block_c = _make_block_c_report()
    a, ca = build_operator_briefing(
        briefing_id="brief-x",
        created_at_utc="2026-05-28T01:00:00Z",
        evidence_bundle=bundle,
        ai_intelligence_output=ai_output,
        block_c_report=block_c,
        reference_window="60d",
    )
    b, cb = build_operator_briefing(
        briefing_id="brief-x",
        created_at_utc="2026-05-28T01:00:00Z",
        evidence_bundle=bundle,
        ai_intelligence_output=ai_output,
        block_c_report=block_c,
        reference_window="60d",
    )
    assert a.to_dict() == b.to_dict()
    assert ca.to_dict() == cb.to_dict()
    # JSON serialisation is stable too.
    assert json.dumps(a.to_dict(), sort_keys=False) == json.dumps(
        b.to_dict(), sort_keys=False
    )


def test_compression_helper_is_deterministic() -> None:
    bundle = _make_bundle()
    ai_output = _make_ai_output()
    a = build_evidence_compression_report(
        report_id="cmp-1",
        created_at_utc="2026-05-28T01:00:00Z",
        evidence_bundle=bundle,
        ai_intelligence_output=ai_output,
        reference_window="60d",
    )
    b = build_evidence_compression_report(
        report_id="cmp-1",
        created_at_utc="2026-05-28T01:00:00Z",
        evidence_bundle=bundle,
        ai_intelligence_output=ai_output,
        reference_window="60d",
    )
    assert a.to_dict() == b.to_dict()


# ---------------------------------------------------------------------------
# 17. forbidden imports
# ---------------------------------------------------------------------------
def test_init_module_re_exports_phase_ai_5_surface() -> None:
    src = INIT_SRC_PATH.read_text(encoding="utf-8")
    for name in (
        "OperatorBriefing",
        "OperatorBriefingAuthorityLevel",
        "OperatorBriefingBuilder",
        "OperatorBriefingFinding",
        "OperatorBriefingSection",
        "OperatorBriefingSectionRecord",
        "EvidenceCompressionReport",
        "EvidenceCompressionReportBuilder",
        "CompressedClaim",
        "CLAIM_CLASS_SUPPORTED",
        "CLAIM_CLASS_UNSUPPORTED",
        "CLAIM_CLASS_REJECTED",
        "CLAIM_CLASS_CONTRADICTED",
        "CLAIM_CLASS_DEGRADED_NO_EVIDENCE",
        "CLAIM_CLASS_COMMENTARY_ONLY",
        "build_operator_briefing",
        "build_evidence_compression_report",
        "render_operator_briefing_markdown",
        "render_evidence_compression_report_markdown",
        "AI_OPERATOR_BRIEFING_GENERATED",
        "AI_EVIDENCE_COMPRESSION_GENERATED",
        "AI_UNSUPPORTED_CLAIMS_SUMMARIZED",
    ):
        assert name in src, (
            f"app/ai/__init__.py is missing the Phase AI-5 "
            f"re-export {name!r}."
        )


def test_phase_identity_constants_are_stable() -> None:
    assert (
        AI_OPERATOR_BRIEFING_SCHEMA_VERSION == "v0"
    )
    assert (
        AI_OPERATOR_BRIEFING_SOURCE_PHASE == "phase_ai_5"
    )
    assert (
        AI_OPERATOR_BRIEFING_SOURCE_MODULE
        == "ai_operator_briefing"
    )
    assert (
        AI_EVIDENCE_COMPRESSION_SCHEMA_VERSION == "v0"
    )
    assert (
        AI_EVIDENCE_COMPRESSION_SOURCE_PHASE == "phase_ai_5"
    )
    assert (
        AI_EVIDENCE_COMPRESSION_SOURCE_MODULE
        == "ai_evidence_compression_report"
    )


def test_event_type_constants_have_expected_values() -> None:
    assert (
        AI_OPERATOR_BRIEFING_GENERATED
        == "AI_OPERATOR_BRIEFING_GENERATED"
    )
    assert (
        AI_EVIDENCE_COMPRESSION_GENERATED
        == "AI_EVIDENCE_COMPRESSION_GENERATED"
    )
    assert (
        AI_UNSUPPORTED_CLAIMS_SUMMARIZED
        == "AI_UNSUPPORTED_CLAIMS_SUMMARIZED"
    )


# ---------------------------------------------------------------------------
# 18. no live LLM / DeepSeek network call required for unit tests
# ---------------------------------------------------------------------------
def test_briefing_module_has_no_llm_call_path() -> None:
    """The Phase AI-5 modules MUST NOT contain any code path
    that calls an LLM / DeepSeek transport."""
    for src_path in (
        BRIEFING_SRC_PATH,
        COMPRESSION_SRC_PATH,
        RUNNER_SCRIPT_PATH,
    ):
        src = src_path.read_text(encoding="utf-8")
        for shape in (
            "deepseek.api",
            "DeepSeekClient(",
            "call_deepseek(",
            "openai.ChatCompletion(",
            "OpenAI(",
            "anthropic.Client(",
        ):
            assert shape not in src, (
                f"{src_path.name} contains LLM call shape "
                f"{shape!r}; Phase AI-5 is offline-only."
            )


def test_briefing_runs_without_network() -> None:
    """Fast smoke: the entire build path runs synchronously
    in-memory; no socket is opened. We assert this implicitly
    by running the build path here."""
    briefing, compression = _build_briefing()
    assert briefing is not None
    assert compression is not None


# ---------------------------------------------------------------------------
# Defensive companions
# ---------------------------------------------------------------------------
def test_block_c_known_blockers_surfaced_as_review_items() -> None:
    block_c = _make_block_c_report(
        known_blockers=["blocker_alpha", "blocker_beta"]
    )
    briefing, _ = _build_briefing(block_c=block_c)
    assert (
        "block_c_blocker:blocker_alpha"
        in briefing.operator_review_items
    )
    assert (
        "block_c_blocker:blocker_beta"
        in briefing.operator_review_items
    )
    action_section = next(
        s
        for s in briefing.sections
        if s.section
        is OperatorBriefingSection.OPERATOR_ACTION_ITEMS
    )
    headlines = [f.headline for f in action_section.findings]
    assert any("blocker_alpha" in h for h in headlines)


def test_authority_level_degrades_when_known_blockers_present() -> None:
    block_c = _make_block_c_report(
        known_blockers=["blocker_alpha"]
    )
    briefing, _ = _build_briefing(block_c=block_c)
    assert (
        briefing.authority_level
        is OperatorBriefingAuthorityLevel.DEGRADED_PARTIAL_EVIDENCE
    )


def test_authority_level_commentary_when_clean() -> None:
    briefing, _ = _build_briefing()
    assert (
        briefing.authority_level
        is OperatorBriefingAuthorityLevel.COMMENTARY_SUBSTRATE
    )


def test_authority_level_rejected_when_phase_12_leak() -> None:
    block_c = _make_block_c_report(phase_12_forbidden=False)
    briefing, _ = _build_briefing(block_c=block_c)
    assert (
        briefing.authority_level
        is OperatorBriefingAuthorityLevel.REJECTED
    )


def test_classify_claim_supported_path() -> None:
    classification = classify_claim(
        citation_authority_level="SUPPORTED_INTELLIGENCE",
        reality_check_status="SUPPORTED",
        reality_check_authority_level="SUPPORTED_INTELLIGENCE",
        has_evidence_refs=True,
    )
    assert classification == CLAIM_CLASS_SUPPORTED


def test_classify_claim_contradicted_path() -> None:
    classification = classify_claim(
        citation_authority_level="SUPPORTED_INTELLIGENCE",
        reality_check_status="CONTRADICTED",
        reality_check_authority_level="REJECTED_BY_REALITY_CHECK",
        has_evidence_refs=True,
    )
    assert classification == CLAIM_CLASS_CONTRADICTED


def test_classify_claim_rejected_path() -> None:
    classification = classify_claim(
        citation_authority_level="SUPPORTED_INTELLIGENCE",
        reality_check_status="REJECTED_LOOKAHEAD",
        reality_check_authority_level="REJECTED_BY_REALITY_CHECK",
        has_evidence_refs=True,
    )
    assert classification == CLAIM_CLASS_REJECTED


def test_classify_claim_unsupported_path() -> None:
    classification = classify_claim(
        citation_authority_level="SUPPORTED_INTELLIGENCE",
        reality_check_status="INSUFFICIENT_EVIDENCE",
        reality_check_authority_level="DEGRADED_NO_EVIDENCE",
        has_evidence_refs=True,
    )
    assert classification == CLAIM_CLASS_UNSUPPORTED


def test_briefing_works_without_block_c_report() -> None:
    briefing, _ = build_operator_briefing(
        briefing_id="briefing-no-block-c",
        created_at_utc="2026-05-28T01:00:00Z",
        evidence_bundle=_make_bundle(),
        ai_intelligence_output=_make_ai_output(),
        block_c_report=None,
        reference_window="60d",
    )
    assert briefing.source_block_c_status == "<missing>"
    assert briefing.source_report_paths == ()


def test_compression_classification_counts_match_buckets() -> None:
    ai_output = _make_ai_output(
        claims=[
            {
                "claim_id": "claim-supported",
                "claim_type": "REGIME",
                "claim_text": "Supported.",
                "evidence_refs": [
                    "report:post_discovery_outcome_report"
                ],
                "truth_layer_fields_used": [
                    "market_facts.breadth_score"
                ],
                "citation_authority_level": "SUPPORTED_INTELLIGENCE",
                "reality_check_status": "SUPPORTED",
                "reality_check_authority_level": (
                    "SUPPORTED_INTELLIGENCE"
                ),
                "confidence_raw": 0.6,
                "confidence_reality_checked": 0.6,
                "warnings": [],
            },
            {
                "claim_id": "claim-degraded",
                "claim_type": "NARRATIVE",
                "claim_text": "Degraded.",
                "evidence_refs": [],
                "truth_layer_fields_used": [],
                "citation_authority_level": "DEGRADED_NO_EVIDENCE",
                "reality_check_status": "INSUFFICIENT_EVIDENCE",
                "reality_check_authority_level": (
                    "DEGRADED_NO_EVIDENCE"
                ),
                "confidence_raw": 0.4,
                "confidence_reality_checked": 0.0,
                "warnings": ["missing_evidence_refs"],
            },
            {
                "claim_id": "claim-contradicted",
                "claim_type": "REGIME",
                "claim_text": "Contradicted.",
                "evidence_refs": ["symbol:BTCUSDT"],
                "truth_layer_fields_used": [
                    "market_facts.breadth_score"
                ],
                "citation_authority_level": "SUPPORTED_INTELLIGENCE",
                "reality_check_status": "CONTRADICTED",
                "reality_check_authority_level": (
                    "REJECTED_BY_REALITY_CHECK"
                ),
                "confidence_raw": 0.7,
                "confidence_reality_checked": 0.0,
                "warnings": ["contradicted"],
            },
        ],
        unsupported_claims=["claim-degraded"],
        contradictions=["claim-contradicted"],
    )
    briefing, compression = _build_briefing(ai_output=ai_output)
    assert "claim-supported" in compression.supported_claims
    assert "claim-degraded" in compression.degraded_claims
    assert "claim-contradicted" in compression.contradictions
    # The briefing's key findings only contain the supported
    # claim id.
    assert briefing.key_findings == ("claim-supported",)


def test_section_grouping_for_each_claim_type() -> None:
    """Different claim_types should land in their dedicated
    sections so the briefing is operator-readable."""
    type_section_pairs = [
        ("REGIME", OperatorBriefingSection.MARKET_INTELLIGENCE),
        ("NARRATIVE", OperatorBriefingSection.MARKET_INTELLIGENCE),
        ("LIQUIDITY", OperatorBriefingSection.MARKET_INTELLIGENCE),
        ("RISK", OperatorBriefingSection.DATA_GAPS),
        ("COVERAGE", OperatorBriefingSection.COVERAGE_AUDIT),
        ("OUTCOME", OperatorBriefingSection.POST_DISCOVERY_OUTCOME),
        (
            "REPLAY_SUMMARY",
            OperatorBriefingSection.REPLAY_REFLECTION,
        ),
        (
            "REFLECTION_SUMMARY",
            OperatorBriefingSection.REPLAY_REFLECTION,
        ),
        (
            "EVIDENCE_QUALITY",
            OperatorBriefingSection.DISCOVERY_QUALITY,
        ),
    ]
    for claim_type, expected_section in type_section_pairs:
        claim = {
            "claim_id": f"claim-{claim_type.lower()}",
            "claim_type": claim_type,
            "claim_text": f"Test claim for {claim_type}.",
            "evidence_refs": [
                "report:post_discovery_outcome_report"
            ],
            "truth_layer_fields_used": [
                "market_facts.breadth_score"
            ],
            "citation_authority_level": "SUPPORTED_INTELLIGENCE",
            "reality_check_status": "SUPPORTED",
            "reality_check_authority_level": (
                "SUPPORTED_INTELLIGENCE"
            ),
            "confidence_raw": 0.5,
            "confidence_reality_checked": 0.5,
            "warnings": [],
        }
        ai_output = _make_ai_output(claims=[claim])
        briefing, _ = _build_briefing(ai_output=ai_output)
        section = next(
            s for s in briefing.sections
            if s.section is expected_section
        )
        related_ids = [
            cid
            for f in section.findings
            for cid in f.related_claim_ids
        ]
        assert claim["claim_id"] in related_ids, (
            f"claim_type={claim_type!r} did not land in "
            f"section {expected_section.value}"
        )


def test_consumer_contract_is_pinned() -> None:
    briefing, _ = _build_briefing()
    payload = briefing.to_dict()
    contract = payload["consumer_contract"]
    assert "human_operator" in contract["allowed_consumers"]
    assert (
        "operator_briefing_report"
        in contract["allowed_consumers"]
    )
    assert "RiskEngine" in contract["forbidden_consumers"]
    assert "ExecutionFSM" in contract["forbidden_consumers"]
    assert "TelegramLiveCommand" in contract["forbidden_consumers"]


def test_compression_summary_mentions_bundle() -> None:
    _, compression = _build_briefing()
    assert compression.source_bundle_id in compression.summary
    assert compression.reference_window in compression.summary


def test_notable_symbols_extracted_from_evidence_refs() -> None:
    ai_output = _make_ai_output(
        claims=[
            {
                "claim_id": "claim-1",
                "claim_type": "REGIME",
                "claim_text": "Sample.",
                "evidence_refs": [
                    "symbol:BTCUSDT",
                    "symbol:ETHUSDT",
                    "symbol:RAVEUSDT",
                ],
                "truth_layer_fields_used": [
                    "market_facts.breadth_score"
                ],
                "citation_authority_level": "SUPPORTED_INTELLIGENCE",
                "reality_check_status": "SUPPORTED",
                "reality_check_authority_level": (
                    "SUPPORTED_INTELLIGENCE"
                ),
                "confidence_raw": 0.6,
                "confidence_reality_checked": 0.6,
                "warnings": [],
            }
        ]
    )
    briefing, _ = _build_briefing(ai_output=ai_output)
    assert "BTCUSDT" in briefing.notable_symbols
    assert "ETHUSDT" in briefing.notable_symbols
    assert "RAVEUSDT" in briefing.notable_symbols
