"""Phase AI-2 - Truth Layer / AI Evidence Citation Contract v0 tests.

The brief mandates that this test module covers, at minimum:

  1. supported claim with valid evidence_refs becomes
     ``SUPPORTED_INTELLIGENCE``
  2. claim without evidence_refs becomes ``DEGRADED_NO_EVIDENCE``
  3. invalid evidence_ref becomes ``REJECTED_INVALID_EVIDENCE``
     (strict) or degraded (non-strict)
  4. commentary-only claim cannot become trade authority
  5. multiple evidence_refs are preserved
  6. ``truth_layer_fields_used`` are preserved
  7. validator never invents missing ``evidence_refs``
  8. forbidden trade fields are rejected / stripped / absent
  9. result summary counts are correct
 10. deterministic output
 11. JSON-serializable output
 12. forbidden imports: must not import ``app.risk`` /
     ``app.execution`` / ``app.exchanges`` / ``app.llm`` /
     ``app.telegram``
 13. no LLM / DeepSeek call path

The tests below address every brief-mandated scenario plus a
handful of defensive companions.

This test module is paper / report / read-only. It does not
authorise live trading, does not authorise auto-tuning, does
not call DeepSeek / any LLM, and does not open Phase 12.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from app.ai import (
    AI_CLAIM_CONTRACT_SCHEMA_VERSION,
    AI_CLAIM_CONTRACT_SOURCE_MODULE,
    AI_CLAIM_CONTRACT_SOURCE_PHASE,
    FORBIDDEN_CLAIM_FIELDS,
    SUPPORTED_EVIDENCE_REF_FORMATS,
    SUPPORTED_EVIDENCE_REF_PREFIXES,
    AIClaim,
    AIClaimAuthorityLevel,
    AIClaimCitationResult,
    AIClaimCitationValidator,
    AIClaimInput,
    AIClaimType,
    validate_ai_claims,
)


SRC_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "ai"
    / "claim_contract.py"
)
INIT_SRC_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "ai"
    / "__init__.py"
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
def _walk_keys(payload):
    if isinstance(payload, dict):
        for k, v in payload.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            yield from _walk_keys(item)


def _make_supported_claim(
    claim_id: str = "claim-supported-1",
    *,
    evidence_refs: tuple[str, ...] = (
        "event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_123",
        "symbol:RAVEUSDT",
    ),
    truth_layer_fields_used: tuple[str, ...] = (
        "market_facts.regime",
        "market_facts.narrative",
    ),
    claim_type: AIClaimType = AIClaimType.REGIME,
    claim_text: str = (
        "60d altcoin momentum regime is dominated by RAVEUSDT-style "
        "right-tail movers"
    ),
) -> AIClaimInput:
    return AIClaimInput(
        claim_id=claim_id,
        claim_type=claim_type,
        claim_text=claim_text,
        evidence_refs=evidence_refs,
        truth_layer_fields_used=truth_layer_fields_used,
        confidence_raw=0.42,
    )


def _make_unsupported_claim(
    claim_id: str = "claim-unsupported-1",
) -> AIClaimInput:
    return AIClaimInput(
        claim_id=claim_id,
        claim_type=AIClaimType.NARRATIVE,
        claim_text="market is bullish (no evidence supplied)",
        evidence_refs=(),
        truth_layer_fields_used=(),
    )


# ---------------------------------------------------------------------------
# 1. supported claim with valid evidence_refs -> SUPPORTED_INTELLIGENCE
# ---------------------------------------------------------------------------
def test_supported_claim_with_valid_evidence_becomes_supported_intelligence() -> None:
    validator = AIClaimCitationValidator()
    result = validator.validate([_make_supported_claim()])

    assert isinstance(result, AIClaimCitationResult)
    assert result.accepted_claim_count == 1
    assert result.degraded_claim_count == 0
    assert result.rejected_claim_count == 0
    assert result.missing_evidence_count == 0
    assert result.invalid_evidence_count == 0

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert isinstance(claim, AIClaim)
    assert (
        claim.authority_level
        is AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE
    )
    assert claim.claim_id == "claim-supported-1"
    assert claim.claim_type == AIClaimType.REGIME.value


@pytest.mark.parametrize(
    "ref",
    [
        "event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_123",
        "symbol:RAVEUSDT",
        "opportunity:opp_abc-1",
        "scan_batch:batch_2026_05_28_001",
        "metric:capture_recall_rate:60d",
        "report:post_discovery_outcome_report",
    ],
)
def test_each_supported_evidence_ref_format_is_accepted(ref: str) -> None:
    """Every brief-mandated citation prefix is accepted."""
    claim = AIClaimInput(
        claim_id="claim-grammar-1",
        claim_type=AIClaimType.OUTCOME,
        claim_text="evidence-cited claim",
        evidence_refs=(ref,),
        truth_layer_fields_used=("outcome_facts.label",),
    )
    result = AIClaimCitationValidator().validate([claim])
    assert result.accepted_claim_count == 1
    assert (
        result.claims[0].authority_level
        is AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE
    )


# ---------------------------------------------------------------------------
# 2. claim without evidence_refs -> DEGRADED_NO_EVIDENCE
# ---------------------------------------------------------------------------
def test_claim_without_evidence_refs_becomes_degraded_no_evidence() -> None:
    validator = AIClaimCitationValidator()
    result = validator.validate([_make_unsupported_claim()])

    assert result.accepted_claim_count == 0
    assert result.degraded_claim_count == 1
    assert result.rejected_claim_count == 0
    assert result.missing_evidence_count == 1
    assert result.invalid_evidence_count == 0

    claim = result.claims[0]
    assert (
        claim.authority_level
        is AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE
    )
    assert "missing_evidence_refs" in claim.warnings
    # The validator MUST NOT invent a substitute evidence_refs.
    assert claim.evidence_refs == ()


def test_claim_with_only_blank_evidence_refs_is_degraded() -> None:
    """Whitespace-only / empty-string ``evidence_refs`` are
    filtered to an empty tuple at intake; the claim is then
    treated as missing-evidence and demoted, not silently
    accepted with a blank citation."""
    claim = AIClaimInput(
        claim_id="claim-blank-refs",
        claim_type=AIClaimType.NARRATIVE,
        claim_text="claim with whitespace-only evidence_refs",
        evidence_refs=("", "   "),
    )
    result = AIClaimCitationValidator().validate([claim])
    assert result.degraded_claim_count == 1
    assert result.missing_evidence_count == 1
    assert (
        result.claims[0].authority_level
        is AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE
    )


# ---------------------------------------------------------------------------
# 3. invalid evidence_ref -> REJECTED_INVALID_EVIDENCE / degraded
# ---------------------------------------------------------------------------
def test_invalid_evidence_ref_in_strict_mode_is_rejected() -> None:
    """Strict mode is the default. An invalid citation prefix
    causes a hard rejection."""
    claim = AIClaimInput(
        claim_id="claim-bad-ref",
        claim_type=AIClaimType.OUTCOME,
        claim_text="claim with malformed evidence ref",
        evidence_refs=("not_a_supported_prefix:foo",),
    )
    result = AIClaimCitationValidator(strict=True).validate([claim])
    assert result.rejected_claim_count == 1
    assert result.invalid_evidence_count == 1
    assert (
        result.claims[0].authority_level
        is AIClaimAuthorityLevel.REJECTED_INVALID_EVIDENCE
    )
    # Original evidence_refs preserved verbatim - never
    # invented or rewritten.
    assert result.claims[0].evidence_refs == (
        "not_a_supported_prefix:foo",
    )


def test_invalid_evidence_ref_in_non_strict_mode_is_degraded() -> None:
    """In non-strict mode an all-invalid citation set demotes
    the claim to DEGRADED_NO_EVIDENCE, never silently accepted."""
    claim = AIClaimInput(
        claim_id="claim-bad-ref-non-strict",
        claim_type=AIClaimType.OUTCOME,
        claim_text="claim with malformed evidence ref",
        evidence_refs=("not_a_supported_prefix:foo",),
    )
    result = AIClaimCitationValidator(strict=False).validate([claim])
    assert result.rejected_claim_count == 0
    assert result.degraded_claim_count == 1
    assert result.invalid_evidence_count == 1
    assert (
        result.claims[0].authority_level
        is AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE
    )
    # Even when degraded, the validator preserves the
    # original evidence_refs verbatim.
    assert result.claims[0].evidence_refs == (
        "not_a_supported_prefix:foo",
    )


def test_partial_invalid_evidence_ref_in_non_strict_mode_keeps_claim() -> None:
    """Non-strict mode + some valid + some invalid refs:
    the claim stays SUPPORTED_INTELLIGENCE but a warning is
    surfaced."""
    claim = AIClaimInput(
        claim_id="claim-partial-bad",
        claim_type=AIClaimType.REGIME,
        claim_text="partially cited claim",
        evidence_refs=(
            "symbol:RAVEUSDT",
            "freeform-not-a-citation",
        ),
    )
    result = AIClaimCitationValidator(strict=False).validate([claim])
    assert result.accepted_claim_count == 1
    assert result.invalid_evidence_count == 1
    out = result.claims[0]
    assert (
        out.authority_level
        is AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE
    )
    # Original evidence_refs preserved verbatim, including
    # the invalid one - no silent rewrite.
    assert out.evidence_refs == (
        "symbol:RAVEUSDT",
        "freeform-not-a-citation",
    )
    assert any(
        w.startswith("invalid_evidence_ref:")
        for w in out.warnings
    )


def test_unknown_claim_type_is_rejected_by_schema() -> None:
    claim = AIClaimInput(
        claim_id="claim-unknown-type",
        claim_type="NOT_A_REAL_CLAIM_TYPE",
        claim_text="claim with unknown type",
        evidence_refs=("symbol:RAVEUSDT",),
    )
    result = AIClaimCitationValidator().validate([claim])
    assert result.rejected_claim_count == 1
    assert (
        result.claims[0].authority_level
        is AIClaimAuthorityLevel.REJECTED_BY_SCHEMA
    )


# ---------------------------------------------------------------------------
# 4. commentary-only claim cannot become trade authority
# ---------------------------------------------------------------------------
def test_commentary_only_claim_stays_commentary_only_even_with_valid_refs() -> None:
    """A producer can opt the claim into commentary-only
    authority. Even when citations are well-formed, the
    validator MUST NOT escalate the claim past
    COMMENTARY_ONLY."""
    claim = AIClaimInput(
        claim_id="claim-commentary",
        claim_type=AIClaimType.NARRATIVE,
        claim_text="opinion-only narrative",
        evidence_refs=("symbol:RAVEUSDT",),
        intended_authority_level=AIClaimAuthorityLevel.COMMENTARY_ONLY,
    )
    result = AIClaimCitationValidator().validate([claim])
    assert (
        result.claims[0].authority_level
        is AIClaimAuthorityLevel.COMMENTARY_ONLY
    )


def test_authority_level_enum_has_no_trade_authority_member() -> None:
    """The enum MUST NOT contain a member that grants trade
    authority. The maximum any claim can reach is
    SUPPORTED_INTELLIGENCE, which is commentary substrate
    only."""
    members = {member.value for member in AIClaimAuthorityLevel}
    forbidden_authority_names = {
        "TRADE_AUTHORITY",
        "EXECUTION_AUTHORITY",
        "ORDER_AUTHORITY",
        "RISK_OVERRIDE",
        "RUNTIME_TUNING_AUTHORITY",
        "AUTO_TUNING_AUTHORITY",
        "LIVE_TRADING_AUTHORITY",
    }
    assert members.isdisjoint(forbidden_authority_names)


def test_no_claim_can_be_promoted_to_trade_authority_through_input() -> None:
    """Even if a producer tries to declare a fake "trade
    authority" intent, the validator MUST NOT honour it -
    intended levels outside the closed enum get coerced back
    to SUPPORTED_INTELLIGENCE before being used."""
    raw = {
        "claim_id": "claim-fake-authority",
        "claim_type": AIClaimType.REGIME.value,
        "claim_text": "regime claim",
        "evidence_refs": ("symbol:RAVEUSDT",),
        "intended_authority_level": "TRADE_AUTHORITY",
    }
    result = AIClaimCitationValidator().validate([raw])
    assert (
        result.claims[0].authority_level
        is AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE
    )


# ---------------------------------------------------------------------------
# 5. multiple evidence_refs are preserved
# ---------------------------------------------------------------------------
def test_multiple_evidence_refs_preserved_in_input_order() -> None:
    refs = (
        "event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_a",
        "symbol:RAVEUSDT",
        "opportunity:opp_42",
        "scan_batch:batch_001",
        "metric:capture_recall_rate:60d",
        "report:post_discovery_outcome_report",
    )
    claim = AIClaimInput(
        claim_id="claim-multi-refs",
        claim_type=AIClaimType.COVERAGE,
        claim_text="multi-evidence coverage claim",
        evidence_refs=refs,
    )
    result = AIClaimCitationValidator().validate([claim])
    assert result.accepted_claim_count == 1
    assert result.claims[0].evidence_refs == refs


# ---------------------------------------------------------------------------
# 6. truth_layer_fields_used are preserved
# ---------------------------------------------------------------------------
def test_truth_layer_fields_used_preserved_verbatim() -> None:
    truth_fields = (
        "market_facts.regime",
        "outcome_facts.outcome_label",
        "evidence_contract_facts.accepted_claim_count",
    )
    claim = AIClaimInput(
        claim_id="claim-truth-fields",
        claim_type=AIClaimType.OUTCOME,
        claim_text="claim referencing specific truth-layer fields",
        evidence_refs=("report:post_discovery_outcome_report",),
        truth_layer_fields_used=truth_fields,
    )
    result = AIClaimCitationValidator().validate([claim])
    assert (
        result.claims[0].truth_layer_fields_used == truth_fields
    )


def test_truth_layer_fields_used_preserved_even_when_degraded() -> None:
    truth_fields = ("market_facts.regime",)
    claim = AIClaimInput(
        claim_id="claim-degraded-with-fields",
        claim_type=AIClaimType.REGIME,
        claim_text="claim with no evidence_refs",
        evidence_refs=(),
        truth_layer_fields_used=truth_fields,
    )
    result = AIClaimCitationValidator().validate([claim])
    assert (
        result.claims[0].authority_level
        is AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE
    )
    assert (
        result.claims[0].truth_layer_fields_used == truth_fields
    )


# ---------------------------------------------------------------------------
# 7. validator never invents missing evidence_refs
# ---------------------------------------------------------------------------
def test_validator_never_invents_missing_evidence_refs() -> None:
    """The validator MUST NOT fabricate a substitute citation
    for a claim that supplied none. The output's
    ``evidence_refs`` MUST be exactly what the producer gave."""
    inputs = [
        _make_unsupported_claim("claim-no-refs-1"),
        _make_unsupported_claim("claim-no-refs-2"),
    ]
    result = AIClaimCitationValidator().validate(inputs)
    for out in result.claims:
        assert out.evidence_refs == ()
        assert (
            out.authority_level
            is AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE
        )


def test_validator_never_invents_evidence_refs_for_invalid_strict() -> None:
    """A claim rejected in strict mode keeps its original
    (malformed) evidence_refs verbatim."""
    bad_refs = (
        "freeform-non-citation",
        "another-non-citation",
    )
    claim = AIClaimInput(
        claim_id="claim-bad-refs-keep-original",
        claim_type=AIClaimType.OUTCOME,
        claim_text="claim with malformed citations",
        evidence_refs=bad_refs,
    )
    result = AIClaimCitationValidator(strict=True).validate([claim])
    assert (
        result.claims[0].authority_level
        is AIClaimAuthorityLevel.REJECTED_INVALID_EVIDENCE
    )
    # Original refs preserved verbatim, no replacement.
    assert result.claims[0].evidence_refs == bad_refs


# ---------------------------------------------------------------------------
# 8. forbidden trade fields are rejected / stripped / absent
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "forbidden_field",
    [
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
    ],
)
def test_forbidden_field_in_claim_payload_is_rejected_by_schema(
    forbidden_field: str,
) -> None:
    """A producer trying to smuggle a forbidden trade-action
    field name into a claim's claim_id / claim_type /
    claim_text / evidence_refs / truth_layer_fields_used
    MUST be rejected by schema."""
    claim = AIClaimInput(
        claim_id="claim-forbidden",
        claim_type=AIClaimType.REGIME,
        claim_text="claim text",
        evidence_refs=("symbol:RAVEUSDT",),
        truth_layer_fields_used=(forbidden_field,),
    )
    result = AIClaimCitationValidator().validate([claim])
    assert result.rejected_claim_count == 1
    assert (
        result.claims[0].authority_level
        is AIClaimAuthorityLevel.REJECTED_BY_SCHEMA
    )
    assert any(
        f"forbidden_field_in_claim:{forbidden_field}" in w
        for w in result.claims[0].warnings
    )


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "buy",
        "leverage",
        "runtime_config_patch",
        "symbol_limit_patch",
        "should_buy",
    ],
)
def test_forbidden_field_never_appears_in_serialized_result(
    forbidden_field: str,
) -> None:
    """A successfully built result's serialised payload MUST
    NOT contain any forbidden trade-action / runtime-config-
    patch field at any nesting depth, even when an upstream
    producer tries to smuggle one in."""
    bad = AIClaimInput(
        claim_id="claim-bad",
        claim_type=AIClaimType.REGIME,
        claim_text="claim text",
        evidence_refs=("symbol:RAVEUSDT",),
        truth_layer_fields_used=(forbidden_field,),
    )
    good = _make_supported_claim()
    result = AIClaimCitationValidator().validate([good, bad])
    payload = result.to_dict()
    keys = list(_walk_keys(payload))
    assert forbidden_field not in keys


def test_forbidden_claim_fields_constant_covers_brief_minimum_set() -> None:
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
        "strategy_parameter_patch",
        "signal_to_trade",
        "should_buy",
        "should_short",
    }
    assert expected.issubset(FORBIDDEN_CLAIM_FIELDS)


# ---------------------------------------------------------------------------
# 9. result summary counts are correct
# ---------------------------------------------------------------------------
def test_result_summary_counts_are_correct() -> None:
    inputs = [
        # Accepted (SUPPORTED_INTELLIGENCE).
        _make_supported_claim("claim-1"),
        _make_supported_claim("claim-2"),
        # Accepted (COMMENTARY_ONLY).
        AIClaimInput(
            claim_id="claim-commentary",
            claim_type=AIClaimType.NARRATIVE,
            claim_text="commentary",
            evidence_refs=("symbol:RAVEUSDT",),
            intended_authority_level=(
                AIClaimAuthorityLevel.COMMENTARY_ONLY
            ),
        ),
        # Degraded (no evidence).
        _make_unsupported_claim("claim-no-refs"),
        # Rejected (invalid evidence in strict mode).
        AIClaimInput(
            claim_id="claim-bad-ref",
            claim_type=AIClaimType.OUTCOME,
            claim_text="bad ref",
            evidence_refs=("not_a_prefix:foo",),
        ),
        # Rejected (unknown claim_type).
        AIClaimInput(
            claim_id="claim-unknown-type",
            claim_type="NOT_A_REAL_TYPE",
            claim_text="unknown type",
            evidence_refs=("symbol:RAVEUSDT",),
        ),
    ]
    result = AIClaimCitationValidator(strict=True).validate(inputs)

    assert result.accepted_claim_count == 3
    assert result.degraded_claim_count == 1
    assert result.rejected_claim_count == 2
    assert result.missing_evidence_count == 1
    assert result.invalid_evidence_count == 1


def test_result_summary_for_empty_input_is_all_zero() -> None:
    result = AIClaimCitationValidator().validate([])
    assert result.accepted_claim_count == 0
    assert result.degraded_claim_count == 0
    assert result.rejected_claim_count == 0
    assert result.missing_evidence_count == 0
    assert result.invalid_evidence_count == 0
    assert result.claims == ()


def test_result_summary_handles_none_input() -> None:
    result = AIClaimCitationValidator().validate(None)
    assert result.accepted_claim_count == 0
    assert result.claims == ()


# ---------------------------------------------------------------------------
# 10. deterministic output
# ---------------------------------------------------------------------------
def test_validator_output_is_deterministic_for_identical_inputs() -> None:
    inputs = [
        _make_supported_claim("claim-1"),
        _make_unsupported_claim("claim-2"),
    ]
    a = AIClaimCitationValidator(strict=True).validate(inputs)
    b = AIClaimCitationValidator(strict=True).validate(inputs)
    assert a.to_dict() == b.to_dict()
    assert json.dumps(a.to_dict(), sort_keys=False) == json.dumps(
        b.to_dict(), sort_keys=False
    )


def test_convenience_wrapper_matches_validator_output() -> None:
    """``validate_ai_claims`` and
    ``AIClaimCitationValidator().validate`` produce equivalent
    output for identical inputs."""
    inputs = [_make_supported_claim()]
    a = AIClaimCitationValidator(strict=True).validate(inputs)
    b = validate_ai_claims(inputs, strict=True)
    assert a.to_dict() == b.to_dict()


# ---------------------------------------------------------------------------
# 11. JSON-serializable output
# ---------------------------------------------------------------------------
def test_result_payload_is_json_serializable_and_re_pins_invariants() -> None:
    inputs = [_make_supported_claim(), _make_unsupported_claim()]
    result = AIClaimCitationValidator().validate(inputs)
    payload = result.to_dict()

    # Round-trip via json without a custom encoder.
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)

    assert decoded["schema_version"] == AI_CLAIM_CONTRACT_SCHEMA_VERSION
    assert decoded["source_phase"] == AI_CLAIM_CONTRACT_SOURCE_PHASE
    assert decoded["source_module"] == AI_CLAIM_CONTRACT_SOURCE_MODULE
    assert decoded["accepted_claim_count"] == 1
    assert decoded["degraded_claim_count"] == 1
    assert decoded["rejected_claim_count"] == 0
    assert decoded["missing_evidence_count"] == 1
    assert decoded["invalid_evidence_count"] == 0

    # Hard-pinned root-constraint flags re-emitted at the
    # serialisation boundary.
    assert decoded["ai_output_is_commentary_only"] is True
    assert decoded["ai_output_can_be_training_label"] is False
    assert decoded["phase_12_forbidden"] is True
    assert decoded["auto_tuning_allowed"] is False

    # Project-wide safety-flag invariants.
    assert decoded["safety_flags"]["mode"] == "paper"
    assert decoded["safety_flags"]["live_trading"] is False
    assert decoded["safety_flags"]["exchange_live_orders"] is False
    assert decoded["safety_flags"]["right_tail"] is False
    assert decoded["safety_flags"]["llm"] is False
    assert decoded["safety_flags"]["telegram_outbound_enabled"] is False
    assert (
        decoded["safety_flags"]["binance_private_api_enabled"] is False
    )

    # Supported citation grammar surfaced for documentation.
    assert set(decoded["supported_evidence_ref_formats"]) == set(
        SUPPORTED_EVIDENCE_REF_FORMATS
    )
    assert set(decoded["supported_evidence_ref_prefixes"]) == set(
        SUPPORTED_EVIDENCE_REF_PREFIXES
    )


def test_invariants_repinned_even_if_dataclass_field_flipped() -> None:
    """Even if a downstream consumer mutates the (frozen)
    dataclass fields via ``object.__setattr__``, ``to_dict``
    re-pins the safe values."""
    result = AIClaimCitationValidator().validate(
        [_make_supported_claim()]
    )
    object.__setattr__(result, "ai_output_is_commentary_only", False)
    object.__setattr__(
        result, "ai_output_can_be_training_label", True
    )
    object.__setattr__(result, "auto_tuning_allowed", True)
    object.__setattr__(result, "phase_12_forbidden", False)

    repinned = result.to_dict()
    assert repinned["ai_output_is_commentary_only"] is True
    assert repinned["ai_output_can_be_training_label"] is False
    assert repinned["auto_tuning_allowed"] is False
    assert repinned["phase_12_forbidden"] is True


# ---------------------------------------------------------------------------
# 12. forbidden imports
# ---------------------------------------------------------------------------
FORBIDDEN_MODULE_PREFIXES = (
    "app.risk",
    "app.execution",
    "app.exchanges",
    "app.llm",
    "app.telegram",
    "app.config",
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


def test_claim_contract_module_does_not_import_forbidden_modules() -> None:
    """Phase AI-2 boundary: the AI claim citation contract
    module MUST NOT import Risk / Execution / Exchange / LLM
    / Telegram / Config modules. Importing any of them would
    compromise either the Responsibility Isolation constraint
    (AI is read-only) or the Stateless Inference constraint
    (AI never reads runtime config)."""
    for path in (SRC_PATH, INIT_SRC_PATH):
        modules = _collect_imports(path.read_text(encoding="utf-8"))
        bad = [
            m
            for m in modules
            if any(
                m == pre or m.startswith(pre + ".")
                for pre in FORBIDDEN_MODULE_PREFIXES
            )
        ]
        assert not bad, (
            f"{path.name} imports forbidden modules: {bad!r}; "
            "this violates the Phase AI-2 boundary."
        )


# ---------------------------------------------------------------------------
# 13. no LLM / DeepSeek call path
# ---------------------------------------------------------------------------
def test_no_deepseek_or_llm_or_http_call_path_in_imports() -> None:
    """The module MUST NOT import any LLM / DeepSeek / HTTP
    client. The AI claim citation contract layer is offline,
    deterministic, and has no transport."""
    forbidden_modules = (
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
    )
    for path in (SRC_PATH, INIT_SRC_PATH):
        modules = _collect_imports(path.read_text(encoding="utf-8"))
        bad = [
            m
            for m in modules
            if any(
                m == pre or m.startswith(pre + ".")
                for pre in forbidden_modules
            )
        ]
        assert not bad, (
            f"{path.name} imports an LLM / DeepSeek / HTTP / "
            f"network module: {bad!r}; this violates the Phase "
            "AI-2 boundary."
        )


def test_module_exposes_no_llm_client_callable() -> None:
    """A defensive check: the module MUST NOT expose any
    callable whose name suggests an LLM client (e.g.
    ``call_deepseek``, ``invoke_llm``)."""
    import app.ai.claim_contract as mod

    public = [
        name for name in dir(mod) if not name.startswith("_")
    ]
    bad = [
        name
        for name in public
        if any(
            tok in name.lower()
            for tok in ("deepseek", "openai", "anthropic", "llm_call")
        )
    ]
    assert not bad, (
        "AI claim contract module exposes LLM-client-shaped "
        f"callables: {bad!r}; this violates the Phase AI-2 boundary."
    )


# ---------------------------------------------------------------------------
# Defensive companions
# ---------------------------------------------------------------------------
def test_unsupported_intelligence_member_exists_for_future_reality_check() -> None:
    """The closed authority-level enum reserves
    ``UNSUPPORTED_INTELLIGENCE`` for the later Reality Check
    Layer. The v0 validator does not produce it; the constant
    is preserved so consumers can ship without an enum
    migration when the Reality Check Layer lands."""
    assert hasattr(AIClaimAuthorityLevel, "UNSUPPORTED_INTELLIGENCE")


def test_each_claim_type_member_present() -> None:
    """Every brief-mandated claim type is represented in the
    closed enum."""
    expected = {
        "REGIME",
        "NARRATIVE",
        "LIQUIDITY",
        "RISK",
        "COVERAGE",
        "OUTCOME",
        "CONTRADICTION",
        "REPLAY_SUMMARY",
        "REFLECTION_SUMMARY",
        "EVIDENCE_QUALITY",
    }
    actual = {member.value for member in AIClaimType}
    assert expected.issubset(actual)


def test_each_authority_level_member_present() -> None:
    """Every brief-mandated authority level is represented in
    the closed enum."""
    expected = {
        "COMMENTARY_ONLY",
        "SUPPORTED_INTELLIGENCE",
        "UNSUPPORTED_INTELLIGENCE",
        "DEGRADED_NO_EVIDENCE",
        "REJECTED_BY_SCHEMA",
        "REJECTED_INVALID_EVIDENCE",
    }
    actual = {member.value for member in AIClaimAuthorityLevel}
    assert expected.issubset(actual)


def test_strict_mode_default_is_strict() -> None:
    validator = AIClaimCitationValidator()
    assert validator.strict is True


def test_non_strict_mode_is_recorded_in_result() -> None:
    result = AIClaimCitationValidator(strict=False).validate(
        [_make_supported_claim()]
    )
    assert result.strict is False
    payload = result.to_dict()
    assert payload["strict"] is False


def test_mapping_input_is_accepted_alongside_dataclass_input() -> None:
    """Producers may hand in plain ``Mapping`` records; the
    validator coerces them transparently."""
    result = AIClaimCitationValidator().validate(
        [
            {
                "claim_id": "claim-mapping-1",
                "claim_type": "REGIME",
                "claim_text": "regime claim from mapping",
                "evidence_refs": ["symbol:RAVEUSDT"],
                "truth_layer_fields_used": ["market_facts.regime"],
            },
        ]
    )
    assert result.accepted_claim_count == 1
    assert (
        result.claims[0].authority_level
        is AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE
    )
    assert result.claims[0].evidence_refs == ("symbol:RAVEUSDT",)
    assert result.claims[0].truth_layer_fields_used == (
        "market_facts.regime",
    )


def test_supported_evidence_ref_prefixes_match_brief_minimum_set() -> None:
    expected = {
        "event",
        "symbol",
        "opportunity",
        "scan_batch",
        "metric",
        "report",
    }
    assert set(SUPPORTED_EVIDENCE_REF_PREFIXES) == expected


def test_phase_ai_2_does_not_call_phase_12_or_authorise_live_trading() -> None:
    """A bundle-style invariant smoke check: the result's
    safety_flags block surfaces every Phase 12 / live-trading
    invariant as ``False`` so a downstream consumer can
    programmatically assert the boundary."""
    result = AIClaimCitationValidator().validate(
        [_make_supported_claim()]
    )
    payload = result.to_dict()
    flags = payload["safety_flags"]
    assert flags["mode"] == "paper"
    assert flags["live_trading"] is False
    assert flags["exchange_live_orders"] is False
    assert flags["right_tail"] is False
    assert flags["llm"] is False
    assert flags["telegram_outbound_enabled"] is False
    assert flags["binance_private_api_enabled"] is False
    assert payload["phase_12_forbidden"] is True
    assert payload["auto_tuning_allowed"] is False
