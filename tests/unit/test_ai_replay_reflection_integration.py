"""Unit tests for Phase AI-6 - AI Replay / Reflection Integration v0.

These tests cover every brief-mandated scenario:

  1.  builds replay case from operator briefing / evidence
      compression input
  2.  preserves evidence_refs
  3.  unsupported claims create AI_UNSUPPORTED_CLAIM tag
  4.  contradicted claims create
      AI_CONTRADICTED_BY_TRUTH_LAYER tag
  5.  failed Reality Check creates AI_REALITY_CHECK_FAILED tag
  6.  missing evidence creates AI_EVIDENCE_MISSING tag
  7.  forbidden fields stripped creates
      AI_FORBIDDEN_FIELD_STRIPPED tag
  8.  AI output cannot become truth
  9.  AI output cannot become training label
 10.  AI output cannot become tail_label
 11.  AI output cannot become strategy validation sample
 12.  trade_authority=False
 13.  auto_tuning_allowed=False
 14.  phase_12_forbidden=True
 15.  forbidden fields absent at every nesting depth
 16.  no Risk / Execution / Strategy / Config consumer
 17.  JSON output serializable
 18.  deterministic output
 19.  forbidden imports - the new modules do NOT import
      app.risk / app.execution / app.exchanges / app.telegram
 20.  no live LLM / DeepSeek network call required for unit
      tests

The whole test module is paper / read-only / deterministic.
It NEVER calls a live LLM, NEVER opens a network socket,
and NEVER touches Risk / Execution / Exchange / Telegram /
Config surfaces.
"""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.replay.ai_replay import (
    AI_REPLAY_CASE_RECONSTRUCTED,
    AI_REPLAY_SUMMARY_GENERATED,
    AIReplayBuilder,
    AIReplayCase,
    AIReplaySourceKind,
    AIReplaySummary,
    build_ai_replay_case,
    build_ai_replay_summary,
)
from app.reflection.ai_reflection import (
    AI_REFLECTION_CASE_GENERATED,
    AI_REFLECTION_SUMMARY_GENERATED,
    AIReflectionCase,
    AIReflectionSeverity,
    AIReflectionSummary,
    AIReflectionTag,
    AIReplayReflectionEngine,
    FORBIDDEN_REFLECTION_TAGS,
    reflect_replay_case,
    reflect_replay_cases,
    replay_and_reflect_artefacts,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------
def _operator_briefing_artefact() -> dict[str, Any]:
    """A minimal Phase AI-5 OperatorBriefing-shaped JSON."""
    return {
        "schema_version": "v0",
        "source_phase": "phase_ai_5",
        "source_module": "ai_operator_briefing",
        "briefing_id": "briefing_001",
        "created_at_utc": "2026-05-28T00:00:00Z",
        "reference_window": "60d",
        "source_bundle_id": "bundle_abc",
        "source_ai_output_id": "intel_xyz",
        "source_block_c_status": "EVIDENCE_GENERATED",
        "source_report_paths": [
            "data/reports/post_discovery_outcome/foo.json",
            "data/reports/coverage/bar.json",
        ],
        "task_type": "OPERATOR_BRIEFING_DRAFT",
        "sections": [],
        "key_findings": [],
        "unsupported_claims": ["claim_unsup_1"],
        "contradictions": ["claim_contradict_1"],
        "data_gaps": ["data_gap_a"],
        "operator_review_items": ["review item 1"],
        "evidence_refs": [
            "event:TAIL_LABEL_ASSIGNED:evt-001",
            "symbol:BTCUSDT",
            "metric:capture_recall_rate:60d",
        ],
        "notable_symbols": ["BTCUSDT", "ETHUSDT"],
        "risk_tags": ["data_gap"],
        "authority_level": "COMMENTARY_SUBSTRATE",
        "forbidden_fields_stripped": ["claims[0].buy"],
        "redacted_secret_count": 1,
        "warnings": ["narrative pollution risk detected"],
        "consumer_contract": {"allowed": ["human_operator"]},
    }


def _evidence_compression_artefact() -> dict[str, Any]:
    """A minimal Phase AI-5 EvidenceCompressionReport-shaped JSON."""
    return {
        "schema_version": "v0",
        "source_phase": "phase_ai_5",
        "source_module": "ai_evidence_compression_report",
        "report_id": "compress_001",
        "created_at_utc": "2026-05-28T00:00:00Z",
        "reference_window": "60d",
        "source_bundle_id": "bundle_abc",
        "source_ai_output_id": "intel_xyz",
        "task_type": "EVIDENCE_COMPRESSION",
        "summary": "summary text",
        "compressed_claims": [
            {
                "claim_id": "c1",
                "claim_type": "OUTCOME",
                "claim_text": "supported claim",
                "evidence_refs": ["event:TAIL_LABEL_ASSIGNED:evt-001"],
                "truth_layer_fields_used": ["outcome_label"],
                "citation_authority_level": "SUPPORTED_INTELLIGENCE",
                "reality_check_status": "SUPPORTED",
                "reality_check_authority_level": "SUPPORTED_INTELLIGENCE",
                "classification": "SUPPORTED",
                "confidence_raw": 0.6,
                "confidence_reality_checked": 0.6,
                "warnings": [],
            },
            {
                "claim_id": "c2",
                "claim_type": "NARRATIVE",
                "claim_text": "unsupported claim",
                "evidence_refs": [],
                "truth_layer_fields_used": [],
                "citation_authority_level": "DEGRADED_NO_EVIDENCE",
                "reality_check_status": "INSUFFICIENT_EVIDENCE",
                "reality_check_authority_level": "DEGRADED_NO_EVIDENCE",
                "classification": "DEGRADED_NO_EVIDENCE",
                "confidence_raw": None,
                "confidence_reality_checked": None,
                "warnings": [],
            },
            {
                "claim_id": "c3",
                "claim_type": "REGIME",
                "claim_text": "contradicted claim",
                "evidence_refs": ["event:MARKET_REGIME_ASSESSED:evt-002"],
                "truth_layer_fields_used": ["regime"],
                "citation_authority_level": "SUPPORTED_INTELLIGENCE",
                "reality_check_status": "CONTRADICTED",
                "reality_check_authority_level": "UNSUPPORTED_INTELLIGENCE",
                "classification": "CONTRADICTED",
                "confidence_raw": 0.9,
                "confidence_reality_checked": 0.0,
                "warnings": ["contradicts breadth_weak=True"],
            },
        ],
        "supported_claims": ["c1"],
        "degraded_claims": ["c2"],
        "rejected_claims": [],
        "contradictions": ["c3"],
        "unsupported_claims": ["c2"],
        "reality_check_summary": {
            "SUPPORTED": 1,
            "INSUFFICIENT_EVIDENCE": 1,
            "CONTRADICTED": 1,
        },
        "evidence_quality_summary": {},
        "data_gap_summary": {},
        "notable_symbols": ["BTCUSDT"],
        "risk_tags": [],
        "evidence_refs": [
            "event:TAIL_LABEL_ASSIGNED:evt-001",
            "event:MARKET_REGIME_ASSESSED:evt-002",
        ],
        "forbidden_fields_stripped": [
            "claims[0].buy",
            "summary.runtime_config_patch",
        ],
        "redacted_secret_count": 2,
        "warnings": [
            "claim c2 has no evidence_refs",
            "smart money narrative detected",
        ],
        "degraded_reasons": [],
    }


def _ai_intelligence_output_artefact() -> dict[str, Any]:
    """A minimal Phase AI-4 AIIntelligenceOutput-shaped JSON."""
    return {
        "schema_version": "v0",
        "source_phase": "phase_ai_4",
        "source_module": "ai_intelligence_output",
        "bundle_id": "bundle_abc",
        "task_type": "MARKET_INTELLIGENCE_SUMMARY",
        "summary": "intelligence summary",
        "claims": [
            {
                "claim_id": "ic1",
                "claim_type": "REGIME",
                "claim_text": "regime is mixed",
                "evidence_refs": ["event:MARKET_REGIME_ASSESSED:evt-002"],
                "truth_layer_fields_used": ["regime"],
                "citation_authority_level": "SUPPORTED_INTELLIGENCE",
                "reality_check_status": "SUPPORTED",
                "reality_check_authority_level": "SUPPORTED_INTELLIGENCE",
                "confidence_raw": 0.5,
                "confidence_reality_checked": 0.5,
                "warnings": [],
            }
        ],
        "contradictions": [],
        "unsupported_claims": [],
        "risk_tags": [],
        "evidence_refs": ["event:MARKET_REGIME_ASSESSED:evt-002"],
        "reality_check_status": "SUPPORTED",
        "authority_level": "SUPPORTED_INTELLIGENCE",
        "status": "OK",
        "forbidden_fields_stripped": [],
        "redacted_secret_count": 0,
        "warnings": [],
        "degraded_reasons": [],
    }


def _evidence_bundle_artefact() -> dict[str, Any]:
    """A minimal Phase AI-1 AIEvidenceBundle-shaped JSON."""
    return {
        "schema_version": "v0",
        "source_phase": "phase_ai_1",
        "source_module": "ai_evidence_bundle_builder",
        "bundle_id": "bundle_abc",
        "created_at_utc": "2026-05-28T00:00:00Z",
        "task_type": "OPERATOR_BRIEFING",
        "build_status": "EVIDENCE_BUNDLE_BUILT",
        "phase_context": {},
        "reference_window": "60d",
        "market_facts": [],
        "system_behavior_facts": [],
        "outcome_facts": [],
        "replay_facts": [],
        "reflection_facts": [],
        "evidence_contract_facts": [],
        "degraded_facts": [],
        "evidence_refs": ["event:TAIL_LABEL_ASSIGNED:evt-001"],
        "source_reports": [
            "data/reports/post_discovery_outcome/foo.json",
        ],
        "forbidden_fields": [],
        "lookahead_policy": {"frozen_evidence_only": True},
        "consumer_contract": {},
        "warnings": [],
        "accepted_fact_count": 0,
        "degraded_fact_count": 0,
    }


# ---------------------------------------------------------------------------
# 1. builds replay case from operator briefing / evidence compression input
# ---------------------------------------------------------------------------
def test_replay_case_built_from_operator_briefing() -> None:
    case = build_ai_replay_case(_operator_briefing_artefact())
    assert isinstance(case, AIReplayCase)
    assert case.source_kind == AIReplaySourceKind.OPERATOR_BRIEFING
    assert case.bundle_id == "bundle_abc"
    assert case.ai_output_id == "intel_xyz"
    assert case.case_id


def test_replay_case_built_from_evidence_compression() -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    assert case.source_kind == AIReplaySourceKind.EVIDENCE_COMPRESSION_REPORT
    assert case.claim_count == 3
    assert case.supported_claim_count == 1
    assert case.degraded_claim_count == 1
    assert case.contradicted_claim_count == 1
    assert case.unsupported_claim_count == 1


def test_replay_case_built_from_ai_intelligence_output() -> None:
    case = build_ai_replay_case(_ai_intelligence_output_artefact())
    assert case.source_kind == AIReplaySourceKind.AI_INTELLIGENCE_OUTPUT
    assert case.bundle_id == "bundle_abc"
    assert case.task_type == "MARKET_INTELLIGENCE_SUMMARY"


def test_replay_case_built_from_evidence_bundle() -> None:
    case = build_ai_replay_case(_evidence_bundle_artefact())
    assert case.source_kind == AIReplaySourceKind.EVIDENCE_BUNDLE
    assert case.bundle_id == "bundle_abc"
    # Bundle has no claims; claim_count should be 0.
    assert case.claim_count == 0


# ---------------------------------------------------------------------------
# 2. preserves evidence_refs
# ---------------------------------------------------------------------------
def test_evidence_refs_preserved_on_operator_briefing() -> None:
    case = build_ai_replay_case(_operator_briefing_artefact())
    assert "event:TAIL_LABEL_ASSIGNED:evt-001" in case.evidence_refs
    assert "symbol:BTCUSDT" in case.evidence_refs
    assert "metric:capture_recall_rate:60d" in case.evidence_refs


def test_evidence_refs_preserved_on_compression_report() -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    refs = set(case.evidence_refs)
    # Top-level + per-claim refs are both preserved.
    assert "event:TAIL_LABEL_ASSIGNED:evt-001" in refs
    assert "event:MARKET_REGIME_ASSESSED:evt-002" in refs


def test_evidence_refs_preserved_on_reflection_case() -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    reflection = reflect_replay_case(case)
    # Same ordering and content.
    assert reflection.evidence_refs == case.evidence_refs


# ---------------------------------------------------------------------------
# 3. unsupported claims create AI_UNSUPPORTED_CLAIM tag
# ---------------------------------------------------------------------------
def test_unsupported_claims_tag() -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    reflection = reflect_replay_case(case)
    assert AIReflectionTag.AI_UNSUPPORTED_CLAIM.value in reflection.tags


# ---------------------------------------------------------------------------
# 4. contradicted claims create AI_CONTRADICTED_BY_TRUTH_LAYER tag
# ---------------------------------------------------------------------------
def test_contradicted_claims_tag() -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    reflection = reflect_replay_case(case)
    assert (
        AIReflectionTag.AI_CONTRADICTED_BY_TRUTH_LAYER.value
        in reflection.tags
    )


# ---------------------------------------------------------------------------
# 5. failed Reality Check creates AI_REALITY_CHECK_FAILED tag
# ---------------------------------------------------------------------------
def test_reality_check_failed_tag_from_contradicted() -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    reflection = reflect_replay_case(case)
    assert AIReflectionTag.AI_REALITY_CHECK_FAILED.value in reflection.tags


def test_reality_check_failed_tag_from_lookahead() -> None:
    artefact = _evidence_compression_artefact()
    artefact["reality_check_summary"] = {"REJECTED_LOOKAHEAD": 1}
    artefact["compressed_claims"] = []
    artefact["supported_claims"] = []
    artefact["degraded_claims"] = []
    artefact["rejected_claims"] = []
    artefact["contradictions"] = []
    artefact["unsupported_claims"] = []
    case = build_ai_replay_case(artefact)
    reflection = reflect_replay_case(case)
    assert AIReflectionTag.AI_REALITY_CHECK_FAILED.value in reflection.tags


# ---------------------------------------------------------------------------
# 6. missing evidence creates AI_EVIDENCE_MISSING tag
# ---------------------------------------------------------------------------
def test_evidence_missing_tag_from_degraded_claims() -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    reflection = reflect_replay_case(case)
    assert AIReflectionTag.AI_EVIDENCE_MISSING.value in reflection.tags


def test_evidence_missing_tag_from_no_refs_with_claims() -> None:
    artefact = _ai_intelligence_output_artefact()
    artefact["evidence_refs"] = []
    artefact["claims"][0]["evidence_refs"] = []
    case = build_ai_replay_case(artefact)
    reflection = reflect_replay_case(case)
    assert AIReflectionTag.AI_EVIDENCE_MISSING.value in reflection.tags


# ---------------------------------------------------------------------------
# 7. forbidden fields stripped creates AI_FORBIDDEN_FIELD_STRIPPED tag
# ---------------------------------------------------------------------------
def test_forbidden_field_stripped_tag() -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    assert case.forbidden_fields_stripped  # sanity
    reflection = reflect_replay_case(case)
    assert (
        AIReflectionTag.AI_FORBIDDEN_FIELD_STRIPPED.value in reflection.tags
    )
    assert reflection.severity in (
        AIReflectionSeverity.HIGH.value,
        AIReflectionSeverity.MEDIUM.value,
    )


# ---------------------------------------------------------------------------
# 8/9/10/11. AI output cannot become truth / training label / tail_label /
# strategy validation sample
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "flag",
    [
        "ai_output_can_be_truth",
        "ai_output_can_be_training_label",
        "ai_output_can_be_tail_label",
        "ai_output_can_be_strategy_sample",
    ],
)
def test_replay_case_ai_output_isolation_flags(flag: str) -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    payload = case.to_dict()
    assert payload[flag] is False


@pytest.mark.parametrize(
    "flag",
    [
        "ai_output_can_be_truth",
        "ai_output_can_be_training_label",
        "ai_output_can_be_tail_label",
        "ai_output_can_be_strategy_sample",
    ],
)
def test_reflection_case_ai_output_isolation_flags(flag: str) -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    reflection = reflect_replay_case(case)
    payload = reflection.to_dict()
    assert payload[flag] is False


def test_isolation_flags_pinned_even_if_dataclass_field_flipped() -> None:
    """Even if a downstream caller flips the dataclass field via
    ``object.__setattr__``, ``to_dict`` re-pins the safe values."""
    case = build_ai_replay_case(_evidence_compression_artefact())
    object.__setattr__(case, "ai_output_can_be_truth", True)
    object.__setattr__(case, "ai_output_can_be_training_label", True)
    object.__setattr__(case, "ai_output_can_be_tail_label", True)
    object.__setattr__(case, "ai_output_can_be_strategy_sample", True)
    payload = case.to_dict()
    assert payload["ai_output_can_be_truth"] is False
    assert payload["ai_output_can_be_training_label"] is False
    assert payload["ai_output_can_be_tail_label"] is False
    assert payload["ai_output_can_be_strategy_sample"] is False


# ---------------------------------------------------------------------------
# 12/13/14. trade_authority / auto_tuning_allowed / phase_12_forbidden
# ---------------------------------------------------------------------------
def test_replay_case_trade_authority_false() -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    assert case.to_dict()["trade_authority"] is False


def test_replay_case_auto_tuning_disallowed() -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    assert case.to_dict()["auto_tuning_allowed"] is False


def test_replay_case_phase_12_forbidden() -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    assert case.to_dict()["phase_12_forbidden"] is True


def test_reflection_case_trade_authority_false() -> None:
    reflection = reflect_replay_case(
        build_ai_replay_case(_evidence_compression_artefact())
    )
    assert reflection.to_dict()["trade_authority"] is False


def test_reflection_case_auto_tuning_disallowed() -> None:
    reflection = reflect_replay_case(
        build_ai_replay_case(_evidence_compression_artefact())
    )
    assert reflection.to_dict()["auto_tuning_allowed"] is False


def test_reflection_case_phase_12_forbidden() -> None:
    reflection = reflect_replay_case(
        build_ai_replay_case(_evidence_compression_artefact())
    )
    assert reflection.to_dict()["phase_12_forbidden"] is True


def test_summary_safety_flags() -> None:
    summary = build_ai_replay_summary(
        [
            _operator_briefing_artefact(),
            _evidence_compression_artefact(),
        ]
    )
    payload = summary.to_dict()
    assert payload["trade_authority"] is False
    assert payload["auto_tuning_allowed"] is False
    assert payload["phase_12_forbidden"] is True
    assert payload["safety_flags"]["mode"] == "paper"
    assert payload["safety_flags"]["live_trading"] is False
    assert payload["safety_flags"]["llm"] is False
    assert payload["safety_flags"]["telegram_outbound_enabled"] is False
    assert payload["safety_flags"]["binance_private_api_enabled"] is False


# ---------------------------------------------------------------------------
# 15. forbidden fields absent at every nesting depth
# ---------------------------------------------------------------------------
FORBIDDEN_FIELDS = (
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
    "strategy_parameter_patch",
    "signal_to_trade",
    "should_buy",
    "should_short",
)


def _walk_and_collect_keys(payload: Any, out: set[str]) -> None:
    if isinstance(payload, dict):
        for k, v in payload.items():
            out.add(str(k))
            _walk_and_collect_keys(v, out)
    elif isinstance(payload, list):
        for v in payload:
            _walk_and_collect_keys(v, out)


@pytest.mark.parametrize("forbidden", FORBIDDEN_FIELDS)
def test_replay_case_no_forbidden_field_at_any_depth(
    forbidden: str,
) -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    payload = case.to_dict()
    keys: set[str] = set()
    _walk_and_collect_keys(payload, keys)
    # The dump intentionally CONTAINS a "forbidden_fields"
    # reference list documenting *what is forbidden*; this is
    # the closed allow-list we expose to downstream auditors.
    # The actual forbidden KEY must never appear at any depth.
    forbidden_block = payload.get("forbidden_fields", [])
    assert forbidden in forbidden_block  # documented as forbidden
    # The forbidden key itself must not appear as a structural
    # key elsewhere.
    structural_keys = keys - {"forbidden_fields"}
    assert forbidden not in structural_keys


@pytest.mark.parametrize("forbidden", FORBIDDEN_FIELDS)
def test_reflection_case_no_forbidden_field_at_any_depth(
    forbidden: str,
) -> None:
    reflection = reflect_replay_case(
        build_ai_replay_case(_evidence_compression_artefact())
    )
    payload = reflection.to_dict()
    keys: set[str] = set()
    _walk_and_collect_keys(payload, keys)
    forbidden_block = payload.get("forbidden_fields", [])
    assert forbidden in forbidden_block
    structural_keys = keys - {"forbidden_fields"}
    assert forbidden not in structural_keys


def test_to_dict_refuses_forbidden_field_smuggled_via_warning_dict() -> None:
    """If a downstream caller somehow constructed a case
    carrying a forbidden key in a payload-shaped warning, the
    recursive guard catches it. Here we simulate by handing a
    Mapping with a forbidden top-level key to the builder.
    """
    artefact = _evidence_compression_artefact()
    artefact["leverage"] = 10  # forbidden
    with pytest.raises(ValueError):
        build_ai_replay_case(artefact)


# ---------------------------------------------------------------------------
# 16. no Risk / Execution / Strategy / Config / Telegram consumer
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "consumer_pkg",
    [
        "app.risk",
        "app.execution",
        "app.exchanges",
        "app.telegram",
        "app.config",
    ],
)
def test_consumer_package_does_not_import_phase_ai_6(
    consumer_pkg: str,
) -> None:
    """Risk / Execution / Exchanges / Telegram / Config
    packages MUST NOT import any Phase AI-6 module."""
    pkg = importlib.import_module(consumer_pkg)
    pkg_path = Path(pkg.__file__).parent  # type: ignore[arg-type]
    forbidden_targets = (
        "app.replay.ai_replay",
        "app.reflection.ai_reflection",
    )
    for path in pkg_path.rglob("*.py"):
        text = path.read_text()
        for target in forbidden_targets:
            assert target not in text, (
                f"{path} imports {target}; Phase AI-6 must not "
                "be wired into Risk / Execution / Exchanges / "
                "Telegram / Config."
            )


# ---------------------------------------------------------------------------
# 17. JSON output serializable
# ---------------------------------------------------------------------------
def test_replay_case_json_serializable() -> None:
    case = build_ai_replay_case(_evidence_compression_artefact())
    text = json.dumps(case.to_dict())
    parsed = json.loads(text)
    assert parsed["case_id"] == case.case_id


def test_replay_summary_json_serializable() -> None:
    summary = build_ai_replay_summary(
        [
            _operator_briefing_artefact(),
            _evidence_compression_artefact(),
        ]
    )
    text = json.dumps(summary.to_dict())
    parsed = json.loads(text)
    assert parsed["total_cases"] == 2


def test_reflection_case_json_serializable() -> None:
    reflection = reflect_replay_case(
        build_ai_replay_case(_evidence_compression_artefact())
    )
    text = json.dumps(reflection.to_dict())
    parsed = json.loads(text)
    assert parsed["case_id"] == reflection.case_id


def test_reflection_summary_json_serializable() -> None:
    summary = reflect_replay_cases(
        [
            build_ai_replay_case(_evidence_compression_artefact()),
            build_ai_replay_case(_operator_briefing_artefact()),
        ]
    )
    text = json.dumps(summary.to_dict())
    parsed = json.loads(text)
    assert parsed["total_cases"] == 2


# ---------------------------------------------------------------------------
# 18. deterministic output
# ---------------------------------------------------------------------------
def test_deterministic_replay_case() -> None:
    a = build_ai_replay_case(_evidence_compression_artefact()).to_dict()
    b = build_ai_replay_case(_evidence_compression_artefact()).to_dict()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_deterministic_reflection_case() -> None:
    a = reflect_replay_case(
        build_ai_replay_case(_evidence_compression_artefact())
    ).to_dict()
    b = reflect_replay_case(
        build_ai_replay_case(_evidence_compression_artefact())
    ).to_dict()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_deterministic_summaries() -> None:
    artefacts = [
        _operator_briefing_artefact(),
        _evidence_compression_artefact(),
        _ai_intelligence_output_artefact(),
        _evidence_bundle_artefact(),
    ]
    replay_a, reflect_a = AIReplayReflectionEngine().replay_and_reflect(
        artefacts
    )
    replay_b, reflect_b = AIReplayReflectionEngine().replay_and_reflect(
        artefacts
    )
    assert json.dumps(replay_a.to_dict(), sort_keys=True) == json.dumps(
        replay_b.to_dict(), sort_keys=True
    )
    assert json.dumps(reflect_a.to_dict(), sort_keys=True) == json.dumps(
        reflect_b.to_dict(), sort_keys=True
    )


# ---------------------------------------------------------------------------
# 19. forbidden imports - the new modules must NOT import app.risk /
# app.execution / app.exchanges / app.telegram / app.config / network libs
# ---------------------------------------------------------------------------
PHASE_AI_6_MODULE_PATHS = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "replay"
    / "ai_replay.py",
    Path(__file__).resolve().parents[2]
    / "app"
    / "reflection"
    / "ai_reflection.py",
)


_FORBIDDEN_TOP_LEVEL_IMPORTS: tuple[str, ...] = (
    "app.risk",
    "app.execution",
    "app.exchanges",
    "app.telegram",
    "app.config",
    # Network / LLM transports
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


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


@pytest.mark.parametrize("module_path", PHASE_AI_6_MODULE_PATHS)
@pytest.mark.parametrize("forbidden", _FORBIDDEN_TOP_LEVEL_IMPORTS)
def test_phase_ai_6_module_does_not_import_forbidden(
    module_path: Path, forbidden: str
) -> None:
    imports = _module_imports(module_path)
    for imp in imports:
        # An import is "forbidden" only if it is the forbidden
        # name itself or a sub-module of the forbidden package.
        assert not (
            imp == forbidden or imp.startswith(forbidden + ".")
        ), (
            f"{module_path.name} imports forbidden module {imp!r} "
            f"(matched against {forbidden!r})."
        )


@pytest.mark.parametrize("module_path", PHASE_AI_6_MODULE_PATHS)
def test_phase_ai_6_module_source_has_no_live_call_shape(
    module_path: Path,
) -> None:
    text = module_path.read_text()
    forbidden_shapes = (
        "DeepSeekClient(",
        "openai.ChatCompletion",
        "openai.Completion",
        "deepseek.api",
        "call_deepseek(",
        "requests.get(",
        "requests.post(",
        "httpx.get(",
        "httpx.post(",
        "aiohttp.ClientSession(",
        "websocket.create_connection(",
        "asyncio.open_connection(",
        "telegram.Bot(",
        "TelegramClient(",
    )
    for shape in forbidden_shapes:
        assert shape not in text, (
            f"{module_path.name} source contains forbidden "
            f"call shape {shape!r}."
        )


# ---------------------------------------------------------------------------
# 20. no live LLM / DeepSeek network call required for unit tests
# ---------------------------------------------------------------------------
def test_full_pipeline_runs_without_network_or_llm() -> None:
    """End-to-end: build replay summary + reflection summary
    from offline JSON dicts. No network. No LLM. No DeepSeek.
    """
    engine = AIReplayReflectionEngine()
    artefacts = [
        _evidence_bundle_artefact(),
        _ai_intelligence_output_artefact(),
        _operator_briefing_artefact(),
        _evidence_compression_artefact(),
    ]
    replay_summary, reflection_summary = engine.replay_and_reflect(
        artefacts
    )
    assert replay_summary.total_cases == 4
    assert reflection_summary.total_cases == 4
    # Every reflection case must carry at least one tag.
    for c in reflection_summary.cases:
        assert c.tags
    # Replay summary must count operator briefing + compression.
    assert replay_summary.operator_briefing_count == 1
    assert replay_summary.evidence_compression_count == 1


# ---------------------------------------------------------------------------
# Forbidden-tag enforcement (Phase AI-6 brief: 禁止 reflection 标签)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "forbidden_tag",
    [
        "ai_said_buy",
        "ai_said_long",
        "ai_target_hit",
        "ai_direction_correct",
        "ai_trade_signal_correct",
    ],
)
def test_forbidden_reflection_tags_never_emitted(
    forbidden_tag: str,
) -> None:
    """The Phase AI-6 brief explicitly forbids these reflection
    tags. The engine must never emit them; the closed
    :class:`AIReflectionTag` enum must not contain them."""
    assert forbidden_tag in FORBIDDEN_REFLECTION_TAGS
    # Enum membership: forbidden tags must NOT be enum values.
    enum_values = {tag.value for tag in AIReflectionTag}
    assert forbidden_tag not in enum_values
    # End-to-end: run on the rich fixture and assert.
    engine = AIReplayReflectionEngine()
    _, reflection_summary = engine.replay_and_reflect(
        [
            _operator_briefing_artefact(),
            _evidence_compression_artefact(),
            _ai_intelligence_output_artefact(),
            _evidence_bundle_artefact(),
        ]
    )
    for c in reflection_summary.cases:
        for tag in c.tags:
            assert tag != forbidden_tag


# ---------------------------------------------------------------------------
# Allowed-tag enum membership
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "allowed_tag",
    [
        "ai_helpful_explanation",
        "ai_unsupported_claim",
        "ai_contradicted_by_truth_layer",
        "ai_reality_check_failed",
        "ai_evidence_missing",
        "ai_narrative_pollution_risk",
        "ai_forbidden_field_stripped",
        "ai_degraded_output",
        "ai_operator_briefing_generated",
        "ai_evidence_compression_generated",
    ],
)
def test_allowed_reflection_tag_enum_member(allowed_tag: str) -> None:
    enum_values = {tag.value for tag in AIReflectionTag}
    assert allowed_tag in enum_values


# ---------------------------------------------------------------------------
# Defensive companions
# ---------------------------------------------------------------------------
def test_event_type_constants_are_strings() -> None:
    assert AI_REPLAY_CASE_RECONSTRUCTED == "AI_REPLAY_CASE_RECONSTRUCTED"
    assert AI_REPLAY_SUMMARY_GENERATED == "AI_REPLAY_SUMMARY_GENERATED"
    assert AI_REFLECTION_CASE_GENERATED == "AI_REFLECTION_CASE_GENERATED"
    assert (
        AI_REFLECTION_SUMMARY_GENERATED
        == "AI_REFLECTION_SUMMARY_GENERATED"
    )


def test_replay_summary_evidence_refs_de_duplicated() -> None:
    summary = build_ai_replay_summary(
        [
            _evidence_compression_artefact(),
            _evidence_compression_artefact(),  # duplicate input
        ]
    )
    # Each ref appears once.
    assert len(summary.evidence_refs) == len(set(summary.evidence_refs))


def test_replay_builder_rejects_non_mapping() -> None:
    with pytest.raises(TypeError):
        AIReplayBuilder.replay_artefact("not a mapping")  # type: ignore[arg-type]


def test_reflection_engine_rejects_non_replay_case() -> None:
    engine = AIReplayReflectionEngine()
    with pytest.raises(TypeError):
        engine.reflect_replay_case({"not": "a case"})  # type: ignore[arg-type]


def test_replay_artefact_accepts_object_with_to_dict() -> None:
    class _Wrapper:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._payload = payload

        def to_dict(self) -> dict[str, Any]:
            return self._payload

    artefact = _Wrapper(_operator_briefing_artefact())
    case = AIReplayBuilder.replay_artefact(artefact)
    assert case.source_kind == AIReplaySourceKind.OPERATOR_BRIEFING


def test_replay_summary_counts_match_inputs() -> None:
    summary = build_ai_replay_summary(
        [
            _operator_briefing_artefact(),
            _evidence_compression_artefact(),
            _ai_intelligence_output_artefact(),
            _evidence_bundle_artefact(),
        ]
    )
    assert summary.total_cases == 4
    assert summary.operator_briefing_count == 1
    assert summary.evidence_compression_count == 1
    assert summary.ai_intelligence_output_count == 1
    assert summary.evidence_bundle_count == 1


def test_reflection_summary_helpful_explanation_for_clean_intel_output() -> None:
    case = build_ai_replay_case(_ai_intelligence_output_artefact())
    reflection = reflect_replay_case(case)
    assert (
        AIReflectionTag.AI_HELPFUL_EXPLANATION.value in reflection.tags
    )


def test_reflection_summary_includes_both_operator_briefing_and_compression_tags() -> None:
    summary = reflect_replay_cases(
        [
            build_ai_replay_case(_operator_briefing_artefact()),
            build_ai_replay_case(_evidence_compression_artefact()),
        ]
    )
    tag_counts = summary.tag_counts
    assert (
        tag_counts.get(
            AIReflectionTag.AI_OPERATOR_BRIEFING_GENERATED.value, 0
        )
        >= 1
    )
    assert (
        tag_counts.get(
            AIReflectionTag.AI_EVIDENCE_COMPRESSION_GENERATED.value, 0
        )
        >= 1
    )


def test_replay_artefact_rejects_credential_smuggle_via_intake_guard() -> None:
    """The Phase AI-1 forbidden-field guard is paranoid; it
    refuses any payload that carries a forbidden trade-action /
    runtime-config-patch key. This guard runs at the AI-6
    intake boundary too."""
    artefact = _evidence_compression_artefact()
    artefact["runtime_config_patch"] = {"symbol_limit": 999}
    with pytest.raises(ValueError):
        build_ai_replay_case(artefact)


def test_replay_and_reflect_via_module_function() -> None:
    artefacts = [
        _operator_briefing_artefact(),
        _evidence_compression_artefact(),
    ]
    replay_summary, reflection_summary = replay_and_reflect_artefacts(
        artefacts
    )
    assert isinstance(replay_summary, AIReplaySummary)
    assert isinstance(reflection_summary, AIReflectionSummary)


def test_replay_case_round_trip_json() -> None:
    """JSON round-trip preserves every documented field."""
    case = build_ai_replay_case(_evidence_compression_artefact())
    payload = case.to_dict()
    text = json.dumps(payload)
    parsed = json.loads(text)
    assert parsed["case_id"] == case.case_id
    assert parsed["bundle_id"] == case.bundle_id
    assert parsed["ai_output_id"] == case.ai_output_id
    assert parsed["task_type"] == case.task_type
    assert parsed["source_kind"] == case.source_kind
    assert parsed["claim_count"] == case.claim_count
    assert parsed["supported_claim_count"] == case.supported_claim_count
    assert parsed["unsupported_claim_count"] == case.unsupported_claim_count
    assert parsed["contradicted_claim_count"] == case.contradicted_claim_count
    assert parsed["degraded_claim_count"] == case.degraded_claim_count
    assert parsed["rejected_claim_count"] == case.rejected_claim_count
    assert parsed["evidence_refs"] == list(case.evidence_refs)
    assert parsed["forbidden_fields_stripped"] == list(
        case.forbidden_fields_stripped
    )
