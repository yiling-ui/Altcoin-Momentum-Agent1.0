"""Phase 11C.1C-C-B-B-B-E-C - Evidence Contract Baseline v0 tests.

Test surface mandated by the brief:

  1. valid event evidence ref
     ``event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_123`` parses
     into ``EvidenceRefType.EVENT`` with ``valid=True``.
  2. valid symbol / opportunity / report ref
     ``symbol:RAVEUSDT``, ``opportunity:opp_123``,
     ``report:block_b_integrated_evidence_report`` all parse.
  3. claim without evidence refs is degraded
     (``DEGRADED_NO_EVIDENCE``); never accepted as fact.
  4. invalid evidence ref is rejected (or degraded); never silently
     passed.
  5. multiple refs preserved
     a claim with multiple valid refs keeps all of them in input order.
  6. no hallucinated refs
     the validator does not auto-generate evidence refs that were not
     supplied.
  7. result summary counts correct
     accepted / degraded / rejected / partial / missing / invalid
     counters add up.
  8. forbidden fields absent
     no payload contains any of the brief's forbidden keys.
  9. forbidden imports
     ``app.evidence.evidence_contract`` does NOT import
     ``app.risk`` / ``app.execution`` / ``app.exchanges`` /
     ``app.llm`` / ``app.telegram``.
 10. deterministic output
     same input -> same output (counts + statuses + payload).
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.core.events import EventType
from app.evidence import (
    EVIDENCE_CONTRACT_BASELINE_SCHEMA_VERSION,
    EVIDENCE_CONTRACT_SOURCE_MODULE,
    EVIDENCE_CONTRACT_SOURCE_PHASE,
    FORBIDDEN_EVIDENCE_PAYLOAD_KEYS,
    ClaimStatus,
    EvidenceClaim,
    EvidenceClaimInput,
    EvidenceContractResult,
    EvidenceContractValidator,
    EvidenceRef,
    EvidenceRefType,
    parse_evidence_ref,
    validate_claims,
)


SRC_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "evidence"
    / "evidence_contract.py"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _walk_keys(payload):
    if isinstance(payload, dict):
        for k, v in payload.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            yield from _walk_keys(item)


# ---------------------------------------------------------------------------
# 1. valid event evidence ref
# ---------------------------------------------------------------------------
def test_event_evidence_ref_parses_into_event_ref_type() -> None:
    """``event:<EVENT_TYPE>:<event_id>`` parses into the EVENT namespace."""
    raw = "event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_123"
    ref = parse_evidence_ref(raw)
    assert isinstance(ref, EvidenceRef)
    assert ref.ref_type is EvidenceRefType.EVENT
    assert ref.namespace == "event"
    assert (
        ref.identifier
        == "HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_123"
    )
    assert ref.valid is True
    assert ref.warnings == ()
    assert ref.raw == raw


def test_event_evidence_ref_missing_event_id_is_invalid() -> None:
    """``event:<EVENT_TYPE>`` with no event_id is invalid (no inference)."""
    ref = parse_evidence_ref("event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED")
    assert ref.ref_type is EvidenceRefType.EVENT
    assert ref.valid is False
    assert any("event_id" in w for w in ref.warnings)


# ---------------------------------------------------------------------------
# 2. valid symbol / opportunity / report ref
# ---------------------------------------------------------------------------
def test_symbol_evidence_ref_parses() -> None:
    ref = parse_evidence_ref("symbol:RAVEUSDT")
    assert ref.ref_type is EvidenceRefType.SYMBOL
    assert ref.identifier == "RAVEUSDT"
    assert ref.valid is True


def test_opportunity_evidence_ref_parses() -> None:
    ref = parse_evidence_ref("opportunity:opp_123")
    assert ref.ref_type is EvidenceRefType.OPPORTUNITY
    assert ref.identifier == "opp_123"
    assert ref.valid is True


def test_report_evidence_ref_parses() -> None:
    raw = "report:block_b_integrated_evidence_report"
    ref = parse_evidence_ref(raw)
    assert ref.ref_type is EvidenceRefType.REPORT
    assert ref.identifier == "block_b_integrated_evidence_report"
    assert ref.valid is True


def test_scan_batch_evidence_ref_parses() -> None:
    ref = parse_evidence_ref("scan_batch:batch_42")
    assert ref.ref_type is EvidenceRefType.SCAN_BATCH
    assert ref.identifier == "batch_42"
    assert ref.valid is True


def test_metric_evidence_ref_parses() -> None:
    ref = parse_evidence_ref("metric:capture_rate:24h")
    assert ref.ref_type is EvidenceRefType.METRIC
    assert ref.identifier == "capture_rate:24h"
    assert ref.valid is True


def test_metric_evidence_ref_missing_window_is_invalid() -> None:
    """``metric:<metric_name>`` with no window is invalid."""
    ref = parse_evidence_ref("metric:capture_rate")
    assert ref.ref_type is EvidenceRefType.METRIC
    assert ref.valid is False
    assert any("window" in w for w in ref.warnings)


# ---------------------------------------------------------------------------
# 3. claim without evidence refs -> degraded
# ---------------------------------------------------------------------------
def test_claim_without_evidence_refs_is_degraded_not_accepted() -> None:
    """A claim that supplies no evidence_refs MUST be degraded; never
    accepted as fact."""
    validator = EvidenceContractValidator()
    claim = validator.validate_claim(
        EvidenceClaimInput(
            claim_id="c-no-refs",
            claim_type="discovery_quality",
            text_or_label="discovery_quality_bucket=DEGRADED",
        )
    )
    assert claim.status is ClaimStatus.DEGRADED_NO_EVIDENCE
    assert claim.degraded is True
    assert claim.degradation_reason == "no_evidence_refs_supplied"
    assert claim.confidence_label == "insufficient_evidence"
    assert claim.evidence_refs == ()
    assert claim.parsed_refs == ()
    # The claim text / label is preserved verbatim - the validator
    # never silently drops the claim.
    assert claim.text_or_label == "discovery_quality_bucket=DEGRADED"


def test_aggregate_overall_status_is_degraded_when_only_no_evidence_claims() -> None:
    validator = EvidenceContractValidator()
    result = validator.validate(
        [
            EvidenceClaimInput(
                claim_id=f"c-{i}",
                claim_type="generic",
                text_or_label=f"label-{i}",
            )
            for i in range(3)
        ]
    )
    assert result.overall_status is ClaimStatus.DEGRADED_NO_EVIDENCE
    assert result.degraded_claim_count == 3
    assert result.accepted_claim_count == 0


# ---------------------------------------------------------------------------
# 4. invalid evidence ref -> rejected or degraded
# ---------------------------------------------------------------------------
def test_invalid_evidence_ref_rejects_claim_when_only_invalid_refs() -> None:
    """A claim whose every supplied evidence ref is invalid is rejected
    (``REJECTED_INVALID_EVIDENCE``); the invalid refs are NOT silently
    accepted."""
    validator = EvidenceContractValidator()
    claim = validator.validate_claim(
        EvidenceClaimInput(
            claim_id="c-bad",
            claim_type="discovery",
            text_or_label="some claim",
            evidence_refs=("garbage", "event:NO_ID", "unknown:xyz"),
        )
    )
    assert claim.status is ClaimStatus.REJECTED_INVALID_EVIDENCE
    assert claim.degraded is True
    assert claim.evidence_refs == ()
    assert len(claim.parsed_refs) == 3
    assert all(r.valid is False for r in claim.parsed_refs)
    # warnings are not silent: they are surfaced on the claim.
    assert claim.warnings != ()


def test_partial_invalid_evidence_ref_marks_claim_partial() -> None:
    """A claim with a mix of valid + invalid refs is recorded as
    PARTIAL: valid refs preserved, invalid refs surfaced as warnings."""
    validator = EvidenceContractValidator()
    claim = validator.validate_claim(
        EvidenceClaimInput(
            claim_id="c-mix",
            claim_type="discovery",
            text_or_label="some claim",
            evidence_refs=(
                "event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_1",
                "garbage",
            ),
        )
    )
    assert claim.status is ClaimStatus.PARTIAL
    assert claim.degraded is True
    assert claim.evidence_refs == (
        "event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_1",
    )
    # The invalid ref is preserved on parsed_refs but not on
    # evidence_refs.
    assert any(not r.valid for r in claim.parsed_refs)


def test_invalid_unknown_namespace_does_not_pass_silently() -> None:
    """An unknown namespace (e.g. ``foo:bar``) is parsed as UNKNOWN
    with a warning and is treated as invalid."""
    ref = parse_evidence_ref("foo:bar")
    assert ref.ref_type is EvidenceRefType.UNKNOWN
    assert ref.valid is False
    assert any("unknown_namespace" in w for w in ref.warnings)


# ---------------------------------------------------------------------------
# 5. multiple refs preserved
# ---------------------------------------------------------------------------
def test_multiple_valid_refs_are_preserved_in_order() -> None:
    refs = (
        "event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_1",
        "symbol:RAVEUSDT",
        "opportunity:opp_42",
        "scan_batch:batch_7",
        "metric:capture_rate:24h",
        "report:block_b_integrated_evidence_report",
    )
    validator = EvidenceContractValidator()
    claim = validator.validate_claim(
        EvidenceClaimInput(
            claim_id="c-many",
            claim_type="multi_evidence",
            text_or_label="lots of refs",
            evidence_refs=refs,
        )
    )
    assert claim.status is ClaimStatus.ACCEPTED
    assert claim.evidence_refs == refs
    assert len(claim.parsed_refs) == len(refs)
    assert all(r.valid for r in claim.parsed_refs)


# ---------------------------------------------------------------------------
# 6. no hallucinated refs
# ---------------------------------------------------------------------------
def test_validator_does_not_invent_evidence_refs() -> None:
    """When a claim supplies no refs, the validator MUST NOT invent
    new ones. The parsed_refs and evidence_refs must remain empty."""
    validator = EvidenceContractValidator()
    claim = validator.validate_claim(
        EvidenceClaimInput(
            claim_id="c-empty",
            claim_type="reflection",
            text_or_label="claim with no provenance",
        )
    )
    assert claim.parsed_refs == ()
    assert claim.evidence_refs == ()


def test_validator_does_not_inject_extra_refs_on_partial() -> None:
    """The validator must not enrich the claim's evidence_refs with
    refs that the caller did not supply."""
    validator = EvidenceContractValidator()
    claim = validator.validate_claim(
        EvidenceClaimInput(
            claim_id="c-mix-2",
            claim_type="discovery",
            text_or_label="x",
            evidence_refs=("symbol:RAVEUSDT", "garbage"),
        )
    )
    # parsed_refs MUST be exactly the two raw inputs - no extras.
    assert tuple(r.raw for r in claim.parsed_refs) == (
        "symbol:RAVEUSDT",
        "garbage",
    )


# ---------------------------------------------------------------------------
# 7. result summary counts correct
# ---------------------------------------------------------------------------
def test_result_summary_counts_are_correct() -> None:
    validator = EvidenceContractValidator()
    inputs = [
        # accepted (1 valid ref).
        EvidenceClaimInput(
            claim_id="c1",
            claim_type="discovery",
            text_or_label="ok",
            evidence_refs=("symbol:RAVEUSDT",),
        ),
        # accepted (multi valid refs).
        EvidenceClaimInput(
            claim_id="c2",
            claim_type="discovery",
            text_or_label="ok2",
            evidence_refs=("opportunity:opp_1", "report:r_1"),
        ),
        # degraded (no refs).
        EvidenceClaimInput(
            claim_id="c3",
            claim_type="reflection",
            text_or_label="no refs",
        ),
        # rejected (only invalid refs).
        EvidenceClaimInput(
            claim_id="c4",
            claim_type="reflection",
            text_or_label="bad",
            evidence_refs=("garbage", "event:NO_ID"),
        ),
        # partial (mix).
        EvidenceClaimInput(
            claim_id="c5",
            claim_type="reflection",
            text_or_label="mix",
            evidence_refs=("symbol:DOGEUSDT", "garbage"),
        ),
    ]
    result = validator.validate(inputs)
    assert result.total_claim_count == 5
    assert result.accepted_claim_count == 2
    assert result.degraded_claim_count == 1
    assert result.rejected_claim_count == 1
    assert result.partial_claim_count == 1
    # missing_evidence_count is the count of claims with zero
    # parsed_refs (only c3 here).
    assert result.missing_evidence_count == 1
    # invalid_evidence_count is the total number of invalid refs
    # across all claims (c4 has 2 invalid + c5 has 1 invalid).
    assert result.invalid_evidence_count == 3
    # overall_status is PARTIAL because the result is mixed.
    assert result.overall_status is ClaimStatus.PARTIAL
    # auto-tuning is hard-pinned False.
    assert result.auto_tuning_allowed is False
    # the schema_version + source_phase + source_module are populated.
    assert result.schema_version == EVIDENCE_CONTRACT_BASELINE_SCHEMA_VERSION
    assert result.source_phase == EVIDENCE_CONTRACT_SOURCE_PHASE
    assert result.source_module == EVIDENCE_CONTRACT_SOURCE_MODULE


def test_empty_input_is_insufficient_evidence() -> None:
    result = validate_claims([])
    assert result.total_claim_count == 0
    assert result.overall_status is ClaimStatus.INSUFFICIENT_EVIDENCE
    assert result.auto_tuning_allowed is False
    assert "no_claims_supplied" in result.warnings


def test_none_input_is_insufficient_evidence() -> None:
    result = validate_claims(None)
    assert result.total_claim_count == 0
    assert result.overall_status is ClaimStatus.INSUFFICIENT_EVIDENCE


# ---------------------------------------------------------------------------
# 8. forbidden fields absent
# ---------------------------------------------------------------------------
def _required_forbidden_keys() -> set[str]:
    return {
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


def test_forbidden_payload_keys_complete() -> None:
    """The brief requires that the forbidden-key set covers every
    direction / sizing / risk / runtime-config-patch key."""
    required = _required_forbidden_keys()
    missing = required - FORBIDDEN_EVIDENCE_PAYLOAD_KEYS
    assert not missing, (
        f"FORBIDDEN_EVIDENCE_PAYLOAD_KEYS is missing required tokens: "
        f"{missing!r}"
    )


def test_emitted_payloads_contain_no_forbidden_keys() -> None:
    """Every emitted payload (claim + result) must be free of the
    brief's forbidden keys, at any nesting depth."""
    validator = EvidenceContractValidator()
    inputs = [
        EvidenceClaimInput(
            claim_id="c1",
            claim_type="discovery",
            text_or_label="x",
            evidence_refs=("symbol:RAVEUSDT",),
        ),
        EvidenceClaimInput(
            claim_id="c2",
            claim_type="discovery",
            text_or_label="y",
        ),
        EvidenceClaimInput(
            claim_id="c3",
            claim_type="discovery",
            text_or_label="z",
            evidence_refs=("garbage",),
        ),
    ]
    result = validator.validate(inputs)
    payload = result.to_dict()
    forbidden = set(_required_forbidden_keys())
    for key in _walk_keys(payload):
        assert key not in forbidden, (
            f"forbidden key {key!r} appeared in EvidenceContractResult "
            "payload; this is a hard violation of the Phase "
            "11C.1C-C-B-B-B-E-C boundary."
        )


def test_to_dict_hard_pins_auto_tuning_allowed_false() -> None:
    """``EvidenceContractResult.to_dict`` must always emit
    ``auto_tuning_allowed=False``, even if the dataclass field was
    overridden."""
    result = EvidenceContractResult(
        accepted_claim_count=0,
        degraded_claim_count=0,
        rejected_claim_count=0,
        partial_claim_count=0,
        missing_evidence_count=0,
        invalid_evidence_count=0,
        total_claim_count=0,
        overall_status=ClaimStatus.INSUFFICIENT_EVIDENCE,
        # Caller tries to flip the flag - must be re-pinned to False.
        auto_tuning_allowed=True,  # type: ignore[arg-type]
    )
    assert result.to_dict()["auto_tuning_allowed"] is False


# ---------------------------------------------------------------------------
# 9. forbidden imports
# ---------------------------------------------------------------------------
FORBIDDEN_MODULE_PREFIXES = (
    "app.risk",
    "app.execution",
    "app.exchanges",
    "app.llm",
    "app.telegram",
)


def test_evidence_contract_module_does_not_import_forbidden_modules() -> None:
    """Phase 11C.1C-C-B-B-B-E-C boundary: the evidence_contract module
    MUST NOT import Risk / Execution / Exchange / LLM / Telegram
    modules."""
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
        "evidence_contract module imports forbidden modules: "
        f"{bad!r}; this violates the Phase 11C.1C-C-B-B-B-E-C boundary."
    )


# ---------------------------------------------------------------------------
# 10. deterministic output
# ---------------------------------------------------------------------------
def test_validator_output_is_deterministic() -> None:
    """Same input -> same output (counts, statuses, payload)."""
    inputs = [
        EvidenceClaimInput(
            claim_id="c1",
            claim_type="discovery",
            text_or_label="x",
            evidence_refs=(
                "event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_1",
                "symbol:RAVEUSDT",
            ),
        ),
        EvidenceClaimInput(
            claim_id="c2",
            claim_type="reflection",
            text_or_label="y",
        ),
        EvidenceClaimInput(
            claim_id="c3",
            claim_type="reflection",
            text_or_label="z",
            evidence_refs=("garbage",),
        ),
    ]
    r1 = EvidenceContractValidator().validate(inputs)
    r2 = EvidenceContractValidator().validate(inputs)
    assert r1.to_dict() == r2.to_dict()


def test_parse_evidence_ref_is_deterministic() -> None:
    raws = [
        "event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_1",
        "symbol:RAVEUSDT",
        "metric:capture_rate:24h",
        "garbage",
        "",
        "unknown:xyz",
    ]
    a = [parse_evidence_ref(r).to_dict() for r in raws]
    b = [parse_evidence_ref(r).to_dict() for r in raws]
    assert a == b


# ---------------------------------------------------------------------------
# Vocabulary integrity
# ---------------------------------------------------------------------------
def test_evidence_ref_type_vocabulary_complete() -> None:
    expected = {
        "EVENT",
        "SYMBOL",
        "OPPORTUNITY",
        "SCAN_BATCH",
        "METRIC",
        "REPORT",
        "UNKNOWN",
    }
    assert {m.name for m in EvidenceRefType} == expected


def test_claim_status_vocabulary_complete() -> None:
    expected = {
        "ACCEPTED",
        "DEGRADED_NO_EVIDENCE",
        "REJECTED_INVALID_EVIDENCE",
        "PARTIAL",
        "INSUFFICIENT_EVIDENCE",
    }
    assert {m.name for m in ClaimStatus} == expected


def test_evidence_event_types_registered() -> None:
    """The three Phase 11C.1C-C-B-B-B-E-C event types are registered
    on :class:`EventType`."""
    assert EventType.EVIDENCE_CONTRACT_VALIDATED.value == "EVIDENCE_CONTRACT_VALIDATED"
    assert EventType.EVIDENCE_CLAIM_DEGRADED.value == "EVIDENCE_CLAIM_DEGRADED"
    assert EventType.EVIDENCE_CLAIM_REJECTED.value == "EVIDENCE_CLAIM_REJECTED"


# ---------------------------------------------------------------------------
# Mapping-input compatibility (the validator can also consume plain dicts
# emitted by upstream Block A / Block B surfaces).
# ---------------------------------------------------------------------------
def test_validator_accepts_mapping_input() -> None:
    validator = EvidenceContractValidator()
    claim = validator.validate_claim(
        {
            "claim_id": "c-map",
            "claim_type": "discovery",
            "text_or_label": "from a dict",
            "evidence_refs": ["symbol:RAVEUSDT"],
        }
    )
    assert claim.status is ClaimStatus.ACCEPTED
    assert claim.evidence_refs == ("symbol:RAVEUSDT",)


def test_validator_handles_non_string_refs_in_mapping_without_inferring() -> None:
    """When a mapping supplies a non-string ref, it is coerced to a
    string but NOT silently accepted unless it parses validly. The
    validator does not infer or rewrite ref content."""
    validator = EvidenceContractValidator()
    claim = validator.validate_claim(
        {
            "claim_id": "c-coerce",
            "claim_type": "discovery",
            "text_or_label": "x",
            "evidence_refs": [12345, "symbol:RAVEUSDT"],
        }
    )
    # The integer ``12345`` does not parse; ``symbol:RAVEUSDT`` does.
    assert claim.status is ClaimStatus.PARTIAL
    assert claim.evidence_refs == ("symbol:RAVEUSDT",)


def test_validator_rejects_non_mapping_non_dataclass_input() -> None:
    validator = EvidenceContractValidator()
    import pytest

    with pytest.raises(TypeError):
        validator.validate_claim(123)  # type: ignore[arg-type]
