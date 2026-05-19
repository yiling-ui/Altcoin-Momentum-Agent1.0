"""Phase 10C - LLM JSON schema validator tests (Spec §22.2)."""

from __future__ import annotations

from app.llm.schema import (
    LLM_OUTPUT_SCHEMA,
    SCHEMA_VERSION,
    SchemaValidationError,
    validate_llm_output,
)


def _valid_payload() -> dict:
    return {
        "narrative": "tight breakout, mild OI pop",
        "catalyst": "real",
        "evidence_quality": "B",
        "source_diversity": 4,
        "kol_concentration": 0.3,
        "bot_risk": 0.1,
        "hype_stage": "spreading",
        "contradictions": [],
        "risk_tags": ["narrative_after_pump"],
        "confidence": 0.7,
    }


def test_schema_version_is_versioned_string():
    assert isinstance(SCHEMA_VERSION, str)
    assert SCHEMA_VERSION.startswith("v")


def test_schema_required_field_set_pinned():
    assert set(LLM_OUTPUT_SCHEMA["required"]) == {
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
    }


def test_validate_clean_payload_passes():
    coerced, errors = validate_llm_output(_valid_payload())
    assert errors == []
    assert coerced["narrative"] == "tight breakout, mild OI pop"
    assert coerced["catalyst"] == "real"


def test_validate_missing_required_field_reports_error():
    payload = _valid_payload()
    del payload["narrative"]
    coerced, errors = validate_llm_output(payload)
    codes = {e.code for e in errors}
    assert "missing_required_field" in codes
    fields = {e.field for e in errors}
    assert "narrative" in fields


def test_validate_unknown_field_reports_error():
    payload = _valid_payload()
    payload["direction"] = "long"
    _, errors = validate_llm_output(payload)
    fields = {e.field: e.code for e in errors}
    assert fields.get("direction") == "unknown_field"


def test_validate_bad_enum_reports_error():
    payload = _valid_payload()
    payload["catalyst"] = "definitely_real"
    _, errors = validate_llm_output(payload)
    assert any(e.field == "catalyst" and e.code == "enum_mismatch" for e in errors)


def test_validate_above_maximum_reports_error():
    payload = _valid_payload()
    payload["confidence"] = 1.7
    _, errors = validate_llm_output(payload)
    assert any(e.field == "confidence" and e.code == "above_maximum" for e in errors)


def test_validate_below_minimum_reports_error():
    payload = _valid_payload()
    payload["bot_risk"] = -0.1
    _, errors = validate_llm_output(payload)
    assert any(e.field == "bot_risk" and e.code == "below_minimum" for e in errors)


def test_validate_bad_type_reports_error():
    payload = _valid_payload()
    payload["source_diversity"] = "many"
    _, errors = validate_llm_output(payload)
    assert any(
        e.field == "source_diversity" and e.code == "bad_type" for e in errors
    )


def test_validate_array_items_get_checked():
    payload = _valid_payload()
    payload["contradictions"] = ["valid", 123]
    _, errors = validate_llm_output(payload)
    # The 123 fails type-check; the array as a whole is rejected.
    assert any(
        e.field == "contradictions[1]" and e.code == "bad_type" for e in errors
    )


def test_validate_top_level_not_object():
    coerced, errors = validate_llm_output("not a dict")
    assert coerced == {}
    assert any(e.code == "not_an_object" for e in errors)


def test_schema_validation_error_to_payload_is_json_safe():
    err = SchemaValidationError(field="x", code="y", message="z")
    payload = err.to_payload()
    assert payload == {"field": "x", "code": "y", "message": "z"}


def test_validator_never_raises_on_garbage():
    # None / bool / int top-level inputs all should be safely rejected.
    for bad in (None, True, 42, 3.14):
        coerced, errors = validate_llm_output(bad)
        assert coerced == {}
        assert errors


def test_string_max_length_enforced():
    payload = _valid_payload()
    payload["narrative"] = "x" * (1024 + 1)
    _, errors = validate_llm_output(payload)
    assert any(e.field == "narrative" and e.code == "too_long" for e in errors)


def test_max_items_enforced():
    payload = _valid_payload()
    payload["risk_tags"] = ["x"] * (64 + 1)
    _, errors = validate_llm_output(payload)
    assert any(
        e.field == "risk_tags" and e.code == "too_many_items" for e in errors
    )
