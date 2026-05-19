"""Phase 10C - LLM value object tests (Issue #10 Part 3)."""

from __future__ import annotations

import dataclasses
import json

import pytest

from app.llm import (
    CatalystStrength,
    EvidenceQuality,
    HypeStage,
    LLMDegradedReason,
    LLMInterpretationInput,
    LLMInterpretationResult,
    LLMRiskTag,
    TokenThrottleTier,
)


# ---------------------------------------------------------------------------
# Vocabularies pinned
# ---------------------------------------------------------------------------
def test_hype_stage_vocabulary_pinned():
    assert {v.value for v in HypeStage} == {
        "early",
        "spreading",
        "climax",
        "decay",
        "unknown",
    }


def test_evidence_quality_vocabulary_pinned():
    assert {v.value for v in EvidenceQuality} == {"A", "B", "C", "D", "unknown"}


def test_catalyst_vocabulary_pinned():
    assert {v.value for v in CatalystStrength} == {
        "real",
        "weak",
        "none",
        "unknown",
    }


def test_token_throttle_tier_vocabulary_pinned():
    assert {v.value for v in TokenThrottleTier} == {
        "skip",
        "light",
        "standard",
        "full",
    }


def test_llm_degraded_reason_vocabulary_includes_required_codes():
    values = {r.value for r in LLMDegradedReason}
    required = {
        "llm_disabled",
        "no_api_key",
        "below_token_throttle",
        "empty_input",
        "prompt_injection_detected",
        "schema_validation_failed",
        "forbidden_field_present",
        "timeout",
        "transport_error",
        "exception",
        "low_confidence",
        "safety_lock",
    }
    missing = required - values
    assert not missing, f"missing degraded reasons: {missing}"


def test_llm_risk_tag_includes_required_codes():
    values = {t.value for t in LLMRiskTag}
    required = {
        "prompt_injection_detected",
        "forbidden_field_stripped",
        "low_confidence",
        "schema_violation",
        "data_insufficient",
    }
    missing = required - values
    assert not missing, f"missing risk tags: {missing}"


# ---------------------------------------------------------------------------
# LLMInterpretationInput
# ---------------------------------------------------------------------------
def test_input_is_frozen():
    inp = LLMInterpretationInput(source_text="hello")
    with pytest.raises(dataclasses.FrozenInstanceError):
        inp.source_text = "tampered"  # type: ignore[misc]


def test_input_field_set():
    fields = {f.name for f in dataclasses.fields(LLMInterpretationInput)}
    assert fields == {
        "source_text",
        "symbol",
        "opportunity_id",
        "anomaly_score",
        "price_change_pct",
        "oi_change_pct",
        "funding_change_pct",
        "sources",
        "timestamp",
        "learning_ready",
        "correlation_id",
    }


def test_input_defaults():
    inp = LLMInterpretationInput(source_text="hi")
    assert inp.symbol is None
    assert inp.anomaly_score is None
    assert inp.sources == ()
    assert inp.learning_ready is None


# ---------------------------------------------------------------------------
# LLMInterpretationResult
# ---------------------------------------------------------------------------
def test_result_field_set_pinned():
    expected = {
        "narrative",
        "catalyst",
        "evidence_quality",
        "source_diversity",
        "kol_concentration",
        "bot_risk",
        "hype_stage",
        "contradictions",
        "risk_tags",
        "confidence",
        "degraded",
        "degraded_reasons",
        "stripped_fields",
        "prompt_injection_detected",
        "source_count",
        "model_name",
        "prompt_version",
        "schema_version",
        "cache_hit",
        "generated_at",
        "opportunity_id",
        "symbol",
        "correlation_id",
    }
    assert {f.name for f in dataclasses.fields(LLMInterpretationResult)} == expected


def test_result_to_payload_is_json_safe():
    result = LLMInterpretationResult(
        narrative="hello",
        catalyst=CatalystStrength.REAL,
        evidence_quality=EvidenceQuality.A,
        source_diversity=3,
        kol_concentration=0.2,
        bot_risk=0.1,
        hype_stage=HypeStage.SPREADING,
        contradictions=("a", "b"),
        risk_tags=(LLMRiskTag.LOW_CONFIDENCE,),
        confidence=0.8,
        degraded=False,
        degraded_reasons=(),
        stripped_fields=(),
        prompt_injection_detected=False,
        source_count=2,
        model_name="fake",
        prompt_version="v1.4.0a10c",
        schema_version="v1.4.0a10c",
        cache_hit=False,
    )
    payload = result.to_payload()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["narrative"] == "hello"
    assert decoded["catalyst"] == "real"
    assert decoded["risk_tags"] == ["low_confidence"]


def test_result_payload_never_carries_forbidden_keys():
    result = LLMInterpretationResult(
        narrative="hi",
        catalyst=CatalystStrength.UNKNOWN,
        evidence_quality=EvidenceQuality.UNKNOWN,
        source_diversity=0,
        kol_concentration=0.0,
        bot_risk=0.0,
        hype_stage=HypeStage.UNKNOWN,
        contradictions=(),
        risk_tags=(),
        confidence=0.0,
        degraded=True,
        degraded_reasons=(LLMDegradedReason.LLM_DISABLED,),
        stripped_fields=(),
        prompt_injection_detected=False,
        source_count=0,
        model_name="fake",
        prompt_version="v1.4.0a10c",
        schema_version="v1.4.0a10c",
        cache_hit=False,
    )
    payload = result.to_payload()
    forbidden = {
        "direction",
        "leverage",
        "position_size",
        "target_price",
        "order_type",
        "stop_price",
        "take_profit",
        "should_buy",
        "should_short",
        "trade_decision",
        "entry",
        "exit",
        "liquidation_price",
        "margin_mode",
        "risk_budget",
        "order",
        "signal_to_trade",
    }
    overlap = forbidden & set(payload)
    assert not overlap, f"payload leaked forbidden keys: {overlap}"


def test_result_helper_properties():
    result = LLMInterpretationResult(
        narrative="hi",
        catalyst=CatalystStrength.UNKNOWN,
        evidence_quality=EvidenceQuality.UNKNOWN,
        source_diversity=0,
        kol_concentration=0.0,
        bot_risk=0.0,
        hype_stage=HypeStage.UNKNOWN,
        contradictions=(),
        risk_tags=(LLMRiskTag.SCHEMA_VIOLATION, LLMRiskTag.LOW_CONFIDENCE),
        confidence=0.0,
        degraded=True,
        degraded_reasons=(LLMDegradedReason.LLM_DISABLED,),
        stripped_fields=("direction",),
        prompt_injection_detected=False,
        source_count=0,
        model_name="fake",
        prompt_version="v1.4.0a10c",
        schema_version="v1.4.0a10c",
        cache_hit=False,
    )
    assert result.is_degraded is True
    assert result.risk_tag_values == ("schema_violation", "low_confidence")
    assert result.degraded_reason_values == ("llm_disabled",)
