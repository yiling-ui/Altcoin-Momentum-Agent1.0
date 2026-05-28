"""Phase AI-4 - DeepSeek Offline Sandbox v0 tests.

The brief mandates that this test module covers, at minimum:

  1. disabled by default
  2. fake provider works offline
  3. outbound disabled degrades safely
  4. forbidden trade fields stripped or rejected
  5. evidence refs required
  6. reality check required
  7. stateless inference
  8. feedback isolation
  9. secret redaction
 10. timeout / 429 / 5xx degrade safely
 11. no hot path imports
 12. no Risk / Execution consumer
 13. deterministic fake test
 14. JSON serializable output
 15. no Phase 12 / no live authority

The tests below address every brief-mandated scenario plus a
handful of defensive companions.

This test module is paper / report / read-only. It does not
authorise live trading, does not authorise auto-tuning, does
not call DeepSeek live, and does not open Phase 12.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from app.ai import (
    AI_INTELLIGENCE_OUTPUT_SCHEMA_VERSION,
    AI_INTELLIGENCE_OUTPUT_SOURCE_MODULE,
    AI_INTELLIGENCE_OUTPUT_SOURCE_PHASE,
    AI_SECRET_REDACTED_PLACEHOLDER,
    DEEPSEEK_SANDBOX_SCHEMA_VERSION,
    DEEPSEEK_SANDBOX_SOURCE_MODULE,
    DEEPSEEK_SANDBOX_SOURCE_PHASE,
    FORBIDDEN_AI_OUTPUT_FIELDS,
    FORBIDDEN_INTELLIGENCE_OUTPUT_FIELDS,
    AIIntelligenceAuthorityLevel,
    AIIntelligenceClaim,
    AIIntelligenceOutput,
    AIIntelligenceStatus,
    AIIntelligenceTaskType,
    DeepSeekOfflineSandboxRunner,
    DeepSeekOutboundDisabledError,
    DeepSeekProviderRateLimitedError,
    DeepSeekProviderServerError,
    DeepSeekProviderTimeoutError,
    DeepSeekSandboxConfig,
    DeepSeekSandboxError,
    DeepSeekSandboxInput,
    FakeDeepSeekProvider,
    OptionalDeepSeekHTTPProvider,
    redact_secrets,
    run_deepseek_offline_sandbox,
    strip_forbidden_fields,
)


# ---------------------------------------------------------------------------
# Source paths (used by the static-analysis tests)
# ---------------------------------------------------------------------------
SANDBOX_SRC_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "ai"
    / "deepseek_sandbox.py"
)
SCHEMA_SRC_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "ai"
    / "intelligence_schema.py"
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
    / "run_deepseek_offline_sandbox.py"
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
        "task_type": "MARKET_INTELLIGENCE_SUMMARY",
        "build_status": "EVIDENCE_BUNDLE_BUILT",
        "phase_context": {"phase": "phase_ai_4", "block": "AI"},
        "reference_window": "60d",
        "market_facts": [
            {
                "schema_version": "v0",
                "fact_id": "market.breadth.60d",
                "fact_type": "market_breadth",
                "evidence_refs": ["report:post_discovery_outcome_report"],
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
                "evidence_refs": ["report:post_discovery_outcome_report"],
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
                "evidence_refs": ["report:post_discovery_outcome_report"],
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
        "evidence_refs": ["report:post_discovery_outcome_report"],
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


def _make_supported_payload() -> dict[str, Any]:
    """A model-shaped response with one well-cited claim."""

    return {
        "summary": (
            "Recent 60d altcoin discovery quality remains "
            "broadly stable on the audit window."
        ),
        "claims": [
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
                "confidence_raw": 0.6,
            }
        ],
        "contradictions": [],
        "unsupported_claims": [],
        "risk_tags": [],
    }


def _make_input(
    *,
    bundle_id: str = "bundle-1",
    task_type: AIIntelligenceTaskType = (
        AIIntelligenceTaskType.MARKET_INTELLIGENCE_SUMMARY
    ),
    operator_instruction: str = "Summarise the bundle as commentary substrate.",
) -> DeepSeekSandboxInput:
    return DeepSeekSandboxInput(
        evidence_bundle=_make_bundle(bundle_id=bundle_id),
        task_type=task_type,
        operator_instruction=operator_instruction,
        allowed_output_schema={
            "summary": "str",
            "claims": "list",
            "contradictions": "list",
            "unsupported_claims": "list",
            "risk_tags": "list",
        },
        forbidden_fields=tuple(),
    )


def _enabled_config(
    *,
    outbound_enabled: bool = False,
) -> DeepSeekSandboxConfig:
    return DeepSeekSandboxConfig(
        enabled=True,
        outbound_enabled=outbound_enabled,
        sandbox_only=True,
        require_evidence_refs=True,
        require_reality_check=True,
    )


# ---------------------------------------------------------------------------
# 1. disabled by default
# ---------------------------------------------------------------------------
def test_default_config_is_disabled_and_safe() -> None:
    cfg = DeepSeekSandboxConfig()
    assert cfg.enabled is False
    assert cfg.outbound_enabled is False
    assert cfg.sandbox_only is True
    assert cfg.allow_trade_decision is False
    assert cfg.allow_runtime_config_change is False
    assert cfg.require_evidence_refs is True
    assert cfg.require_reality_check is True
    assert cfg.stateless_inference is True
    assert cfg.feedback_isolation is True
    assert cfg.redaction_enabled is True


def test_default_runner_short_circuits_to_degraded_outbound_disabled() -> None:
    runner = DeepSeekOfflineSandboxRunner()
    output = runner.run(_make_input())
    assert isinstance(output, AIIntelligenceOutput)
    assert (
        output.status
        is AIIntelligenceStatus.DEGRADED_OUTBOUND_DISABLED
    )
    assert (
        output.authority_level
        is AIIntelligenceAuthorityLevel.DEGRADED_NO_EVIDENCE
    )
    assert "sandbox_disabled" in output.warnings


def test_config_refuses_to_relax_trade_or_runtime_or_sandbox_only() -> None:
    with pytest.raises(ValueError):
        DeepSeekSandboxConfig(allow_trade_decision=True)
    with pytest.raises(ValueError):
        DeepSeekSandboxConfig(allow_runtime_config_change=True)
    with pytest.raises(ValueError):
        DeepSeekSandboxConfig(sandbox_only=False)


# ---------------------------------------------------------------------------
# 2. fake provider works offline
# ---------------------------------------------------------------------------
def test_fake_provider_produces_schema_valid_output_offline() -> None:
    provider = FakeDeepSeekProvider(payload=_make_supported_payload())
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=provider,
    )
    output = runner.run(_make_input())
    assert isinstance(output, AIIntelligenceOutput)
    assert output.bundle_id == "bundle-1"
    assert output.task_type == "MARKET_INTELLIGENCE_SUMMARY"
    # The claim was well-cited and well-supported by the
    # bundle's facts.
    assert output.status is AIIntelligenceStatus.OK
    assert (
        output.authority_level
        is AIIntelligenceAuthorityLevel.SUPPORTED_INTELLIGENCE
    )
    assert len(output.claims) == 1
    claim = output.claims[0]
    assert claim.claim_id == "claim-1"
    assert (
        "report:post_discovery_outcome_report"
        in claim.evidence_refs
    )
    # Provider was invoked exactly once, offline.
    assert provider.calls == 1


# ---------------------------------------------------------------------------
# 3. outbound disabled degrades safely (HTTP provider not invoked)
# ---------------------------------------------------------------------------
class _RecordingHTTPProvider:
    """A test double that simulates an HTTP provider. The
    runner MUST NOT invoke this when outbound is disabled."""

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, **_: Any) -> Mapping[str, Any]:
        self.calls += 1
        return {"summary": "should_not_be_called"}


def test_outbound_disabled_does_not_call_http_provider() -> None:
    """When ``outbound_enabled=False`` the runner uses the
    in-memory FakeDeepSeekProvider regardless of what was
    passed in. The HTTP-shaped provider's ``generate`` is
    NEVER called."""
    http_provider = _RecordingHTTPProvider()
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=False),
        provider=http_provider,
    )
    output = runner.run(_make_input())
    assert http_provider.calls == 0
    # The output is still well-formed; the runner short-
    # circuited to the in-memory provider.
    assert isinstance(output, AIIntelligenceOutput)
    assert "outbound_disabled_using_fake_provider" in output.warnings


def test_optional_http_provider_refuses_when_outbound_disabled() -> None:
    provider = OptionalDeepSeekHTTPProvider(outbound_enabled=False)
    with pytest.raises(DeepSeekOutboundDisabledError):
        provider.generate(
            prompt={"hello": "world"},
            max_tokens=10,
            timeout_seconds=1.0,
            model="deepseek-chat",
        )


def test_optional_http_provider_v0_refuses_even_when_outbound_enabled() -> None:
    """The v0 skeleton refuses to actually contact the network
    even when ``outbound_enabled=True``; the real transport
    lands behind a later, separately gated PR."""
    provider = OptionalDeepSeekHTTPProvider(
        outbound_enabled=True,
        credentials_provided=True,
    )
    with pytest.raises(DeepSeekOutboundDisabledError):
        provider.generate(
            prompt={"hello": "world"},
            max_tokens=10,
            timeout_seconds=1.0,
            model="deepseek-chat",
        )


# ---------------------------------------------------------------------------
# 4. forbidden trade fields stripped or rejected
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
def test_forbidden_top_level_field_stripped_and_recorded(field: str) -> None:
    """When DeepSeek emits a forbidden field at the top level
    of the response, the field MUST be stripped, the run MUST
    be rejected as REJECTED_FORBIDDEN_FIELDS, and the stripped
    path MUST appear in ``forbidden_fields_stripped``."""
    payload = _make_supported_payload()
    payload[field] = "anything"  # forbidden field smuggled in
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(payload=payload),
    )
    output = runner.run(_make_input())
    assert (
        output.status is AIIntelligenceStatus.REJECTED_FORBIDDEN_FIELDS
    )
    assert (
        output.authority_level is AIIntelligenceAuthorityLevel.REJECTED
    )
    assert field in output.forbidden_fields_stripped
    # Recursive guard never serialises a forbidden field as a
    # KEY anywhere in the output. Note the field name MAY
    # appear as a string VALUE in the audit-trail blocks
    # (``forbidden_fields_stripped`` / ``forbidden_fields``)
    # which is allowed and expected.
    decoded = output.to_dict()

    def _walk_keys(node: Any) -> None:
        if isinstance(node, dict):
            assert (
                field not in node
            ), f"forbidden field {field!r} survived as a key"
            for value in node.values():
                _walk_keys(value)
        elif isinstance(node, list):
            for item in node:
                _walk_keys(item)

    _walk_keys(decoded)


@pytest.mark.parametrize("field", FORBIDDEN_FIELD_SAMPLES)
def test_forbidden_nested_field_stripped_recursively(field: str) -> None:
    """The strip must walk into nested mappings / lists."""
    payload = _make_supported_payload()
    payload["claims"][0][field] = "anything"
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(payload=payload),
    )
    output = runner.run(_make_input())
    # The nested forbidden key was stripped.
    nested_path = f"claims[0].{field}"
    assert nested_path in output.forbidden_fields_stripped
    assert (
        output.status is AIIntelligenceStatus.REJECTED_FORBIDDEN_FIELDS
    )
    decoded = json.dumps(output.to_dict())
    # The forbidden key name MUST NOT appear as a key in the
    # serialised payload (the recursive guard would have
    # raised). It MAY appear inside a string value (e.g. the
    # ``forbidden_fields`` reference list), so we check for
    # the stripped path instead.
    assert nested_path in decoded


def test_strip_forbidden_fields_helper_is_pure() -> None:
    payload = {
        "summary": "ok",
        "claims": [
            {
                "claim_id": "c-1",
                "buy": "yes",
                "evidence_refs": ["symbol:BTCUSDT"],
            }
        ],
        "runtime_config_patch": {"symbol_limit": 10},
    }
    cleaned, stripped = strip_forbidden_fields(payload)
    assert "runtime_config_patch" not in cleaned
    assert "buy" not in cleaned["claims"][0]
    assert "claims[0].buy" in stripped
    assert "runtime_config_patch" in stripped
    # Original input is untouched.
    assert "runtime_config_patch" in payload
    assert "buy" in payload["claims"][0]


# ---------------------------------------------------------------------------
# 5. evidence refs required
# ---------------------------------------------------------------------------
def test_claim_without_evidence_refs_is_unsupported() -> None:
    payload = _make_supported_payload()
    payload["claims"][0]["evidence_refs"] = []
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(payload=payload),
    )
    output = runner.run(_make_input())
    # The claim is demoted - no SUPPORTED_INTELLIGENCE
    # authority on the output.
    assert (
        output.authority_level
        is not AIIntelligenceAuthorityLevel.SUPPORTED_INTELLIGENCE
    )
    # The runner records the missing-evidence degraded reason
    # and surfaces the claim id in unsupported_claims.
    assert (
        output.status
        is AIIntelligenceStatus.DEGRADED_MISSING_EVIDENCE
    )
    assert "claim-1" in output.unsupported_claims


# ---------------------------------------------------------------------------
# 6. reality check required
# ---------------------------------------------------------------------------
def test_reality_check_failure_demotes_authority() -> None:
    """A claim whose claim_text contradicts the bundle's facts
    must NOT reach SUPPORTED_INTELLIGENCE."""
    bundle = _make_bundle()
    # Mutate the bundle so a "risk appetite expanding" claim
    # is contradicted by ``breadth_weak=True`` /
    # ``data_gap_severe=True``.
    bundle["market_facts"][0]["content"]["breadth_weak"] = True
    bundle["market_facts"][0]["content"]["data_gap_severe"] = True
    bundle["system_behavior_facts"][0]["content"][
        "late_chase_high"
    ] = True
    bundle["outcome_facts"][0]["content"][
        "failed_continuation"
    ] = True
    payload = _make_supported_payload()
    payload["claims"][0]["claim_text"] = (
        "Risk appetite expanding rapidly across the breadth "
        "with broad rally and bullish continuation."
    )

    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(payload=payload),
    )
    output = runner.run(
        DeepSeekSandboxInput(
            evidence_bundle=bundle,
            task_type=(
                AIIntelligenceTaskType.MARKET_INTELLIGENCE_SUMMARY
            ),
            operator_instruction="Summarise the bundle.",
        )
    )
    assert (
        output.authority_level
        is not AIIntelligenceAuthorityLevel.SUPPORTED_INTELLIGENCE
    )
    assert (
        output.status is AIIntelligenceStatus.DEGRADED_REALITY_CHECK
    )
    assert "claim-1" in output.contradictions


# ---------------------------------------------------------------------------
# 7. stateless inference
# ---------------------------------------------------------------------------
def test_input_with_chat_history_is_rejected() -> None:
    """The runner MUST NOT accept inputs that smuggle
    ``previous_ai_answer`` / ``chat_history`` etc."""
    bundle = _make_bundle()
    bundle["chat_history"] = [
        {"role": "assistant", "content": "previous answer"}
    ]
    si = DeepSeekSandboxInput(
        evidence_bundle=bundle,
        task_type=AIIntelligenceTaskType.MARKET_INTELLIGENCE_SUMMARY,
        operator_instruction="ignored",
    )
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(payload=_make_supported_payload()),
    )
    output = runner.run(si)
    assert (
        output.status is AIIntelligenceStatus.REJECTED_INVALID_INPUT
    )
    assert (
        output.authority_level is AIIntelligenceAuthorityLevel.REJECTED
    )


def test_input_with_previous_ai_answer_is_rejected() -> None:
    bundle = _make_bundle()
    bundle["previous_ai_answer"] = "old answer"
    si = DeepSeekSandboxInput(
        evidence_bundle=bundle,
        task_type=AIIntelligenceTaskType.MARKET_INTELLIGENCE_SUMMARY,
        operator_instruction="ignored",
    )
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(
            payload=_make_supported_payload()
        ),
    )
    output = runner.run(si)
    assert (
        output.status is AIIntelligenceStatus.REJECTED_INVALID_INPUT
    )


# ---------------------------------------------------------------------------
# 8. feedback isolation
# ---------------------------------------------------------------------------
def test_output_pins_feedback_isolation_invariants() -> None:
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(
            payload=_make_supported_payload()
        ),
    )
    output = runner.run(_make_input())
    decoded = output.to_dict()
    assert decoded["stateless_inference"] is True
    assert decoded["feedback_isolation"] is True
    assert decoded["trade_authority"] is False
    assert decoded["auto_tuning_allowed"] is False
    assert decoded["phase_12_forbidden"] is True
    assert decoded["ai_output_is_commentary_only"] is True
    assert decoded["ai_output_can_be_training_label"] is False


def test_invariants_repinned_even_if_dataclass_field_flipped() -> None:
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(
            payload=_make_supported_payload()
        ),
    )
    output = runner.run(_make_input())
    object.__setattr__(output, "trade_authority", True)
    object.__setattr__(output, "auto_tuning_allowed", True)
    object.__setattr__(output, "phase_12_forbidden", False)
    object.__setattr__(output, "stateless_inference", False)
    object.__setattr__(output, "feedback_isolation", False)
    object.__setattr__(
        output, "ai_output_is_commentary_only", False
    )
    object.__setattr__(
        output, "ai_output_can_be_training_label", True
    )
    repinned = output.to_dict()
    assert repinned["trade_authority"] is False
    assert repinned["auto_tuning_allowed"] is False
    assert repinned["phase_12_forbidden"] is True
    assert repinned["stateless_inference"] is True
    assert repinned["feedback_isolation"] is True
    assert repinned["ai_output_is_commentary_only"] is True
    assert repinned["ai_output_can_be_training_label"] is False


# ---------------------------------------------------------------------------
# 9. secret redaction
# ---------------------------------------------------------------------------
def test_redact_secrets_replaces_credential_keys() -> None:
    payload = {
        "model": "deepseek-chat",
        "api_key": "sk-supersecret-1234567890",
        "claims": [
            {
                "claim_id": "c-1",
                "deepseek_api_key": "raw_key_value",
                "metadata": {
                    "binance_api_secret": "real-secret",
                    "evidence_refs": ["symbol:BTCUSDT"],
                },
            }
        ],
        "telegram_bot_token": "token_value",
    }
    cleaned, count = redact_secrets(payload)
    assert count == 4
    assert cleaned["api_key"] == AI_SECRET_REDACTED_PLACEHOLDER
    assert (
        cleaned["claims"][0]["deepseek_api_key"]
        == AI_SECRET_REDACTED_PLACEHOLDER
    )
    assert (
        cleaned["claims"][0]["metadata"]["binance_api_secret"]
        == AI_SECRET_REDACTED_PLACEHOLDER
    )
    assert (
        cleaned["telegram_bot_token"]
        == AI_SECRET_REDACTED_PLACEHOLDER
    )
    # Non-credential values are untouched.
    assert cleaned["model"] == "deepseek-chat"
    assert (
        cleaned["claims"][0]["metadata"]["evidence_refs"]
        == ["symbol:BTCUSDT"]
    )


def test_provider_response_with_credentials_is_redacted_in_output() -> None:
    payload = _make_supported_payload()
    # Smuggle a credential-shaped key into the provider
    # response.
    payload["claims"][0]["deepseek_api_key"] = "sk-secret-xyz"
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(payload=payload),
    )
    output = runner.run(_make_input())
    decoded = json.dumps(output.to_dict())
    # The raw secret value MUST NOT appear anywhere in the
    # serialised output.
    assert "sk-secret-xyz" not in decoded
    assert output.redacted_secret_count >= 1


def test_prompt_does_not_leak_secrets_via_provider_capture() -> None:
    """Even if a forbidden secret slips into the bundle (it
    would normally be rejected by the intake guard), the
    prompt builder must redact credential-shaped keys before
    handing them to the provider."""
    # We can't put a credential key in the bundle directly -
    # the intake guard rejects that. Instead we put a
    # credential-shaped key inside a fact's content (the
    # guard doesn't enter content keys; redaction handles
    # the prompt-builder side as a defence in depth).
    bundle = _make_bundle()
    # NB: ``api_key`` as a content key would be caught by
    # the recursive guard inside ``_scan_for_forbidden_input``.
    # We assert here that the runner refuses such input
    # outright (defensive: secrets MUST NEVER make it into
    # a prompt artifact, even via content).
    bundle["market_facts"][0]["content"]["api_key"] = "sk-x"
    si = DeepSeekSandboxInput(
        evidence_bundle=bundle,
        task_type=AIIntelligenceTaskType.MARKET_INTELLIGENCE_SUMMARY,
        operator_instruction="ignored",
    )
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(
            payload=_make_supported_payload()
        ),
    )
    output = runner.run(si)
    # Defensive: the runner refuses credential-shaped input.
    assert (
        output.status is AIIntelligenceStatus.REJECTED_INVALID_INPUT
    )


# ---------------------------------------------------------------------------
# 10. timeout / 429 / 5xx degrade safely
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "exc, expected_warning_substring",
    [
        (
            DeepSeekProviderTimeoutError("budget exceeded"),
            "provider_timeout",
        ),
        (
            DeepSeekProviderRateLimitedError("HTTP 429"),
            "provider_rate_limited_429",
        ),
        (
            DeepSeekProviderServerError("HTTP 503"),
            "provider_server_error_5xx",
        ),
        (
            DeepSeekOutboundDisabledError("network refused"),
            "provider_outbound_disabled",
        ),
        (
            RuntimeError("totally unexpected"),
            "provider_unexpected_error",
        ),
    ],
)
def test_provider_errors_degrade_safely(
    exc: Exception, expected_warning_substring: str
) -> None:
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(raise_exc=exc),
    )
    output = runner.run(_make_input())
    # The runner NEVER crashes a hot path; it always emits a
    # degraded result.
    assert isinstance(output, AIIntelligenceOutput)
    assert output.status in (
        AIIntelligenceStatus.DEGRADED_PROVIDER_ERROR,
        AIIntelligenceStatus.DEGRADED_OUTBOUND_DISABLED,
    )
    assert any(
        expected_warning_substring in w for w in output.warnings
    )


# ---------------------------------------------------------------------------
# 11. no hot path imports
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


@pytest.mark.parametrize(
    "src_path",
    [SANDBOX_SRC_PATH, SCHEMA_SRC_PATH, RUNNER_SCRIPT_PATH],
)
def test_phase_ai_4_module_does_not_import_hot_path(src_path: Path) -> None:
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
        f"{bad!r}; this violates the Phase AI-4 boundary."
    )


@pytest.mark.parametrize(
    "src_path",
    [SANDBOX_SRC_PATH, SCHEMA_SRC_PATH, RUNNER_SCRIPT_PATH],
)
def test_phase_ai_4_module_does_not_import_network(src_path: Path) -> None:
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
        f"{bad!r}; the Phase AI-4 sandbox is offline-only."
    )


def test_sandbox_source_contains_no_live_call_shape() -> None:
    """Defensive string scan: the source MUST NOT contain a
    ``deepseek.`` / ``DeepSeekClient(`` / ``call_deepseek(`` /
    ``requests.get(`` / ``httpx.post(`` /
    ``aiohttp.ClientSession(`` /
    ``websocket.create_connection(`` shape."""
    forbidden_shapes = (
        "deepseek.api",
        "DeepSeekClient(",
        "call_deepseek(",
        "requests.get(",
        "requests.post(",
        "httpx.post(",
        "httpx.get(",
        "aiohttp.ClientSession(",
        "websocket.create_connection(",
        "websockets.connect(",
        "socket.socket(",
    )
    src = SANDBOX_SRC_PATH.read_text(encoding="utf-8")
    for shape in forbidden_shapes:
        assert shape not in src, (
            f"deepseek_sandbox.py source contains live call "
            f"shape {shape!r}; the v0 sandbox is offline-only."
        )


# ---------------------------------------------------------------------------
# 12. no Risk / Execution consumer
# ---------------------------------------------------------------------------
def _walk_python_files(root: Path):
    for path in root.rglob("*.py"):
        yield path


@pytest.mark.parametrize(
    "pkg_root", [RISK_PKG_PATH, EXECUTION_PKG_PATH, EXCHANGES_PKG_PATH]
)
def test_risk_execution_exchange_do_not_import_app_ai(pkg_root: Path) -> None:
    """The Risk / Execution / Exchange packages MUST NOT import
    ``app.ai`` (any submodule). AI output is commentary
    substrate; it never feeds the trade-decision gate."""
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
        f"Risk / Execution / Exchange package imports app.ai: "
        f"{bad!r}; AI output is commentary-only and must not "
        "reach the trade-decision gate."
    )


# ---------------------------------------------------------------------------
# 13. deterministic fake test
# ---------------------------------------------------------------------------
def test_same_input_same_output_is_deterministic() -> None:
    payload = _make_supported_payload()

    def _run_once() -> dict[str, Any]:
        runner = DeepSeekOfflineSandboxRunner(
            config=_enabled_config(outbound_enabled=True),
            provider=FakeDeepSeekProvider(payload=payload),
        )
        return runner.run(_make_input()).to_dict()

    out_a = _run_once()
    out_b = _run_once()
    assert out_a == out_b
    # JSON serialisation is stable too.
    assert json.dumps(out_a, sort_keys=False) == json.dumps(
        out_b, sort_keys=False
    )


def test_run_deepseek_offline_sandbox_helper_is_deterministic() -> None:
    payload = _make_supported_payload()
    out_a = run_deepseek_offline_sandbox(
        sandbox_input=_make_input(),
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(payload=payload),
    ).to_dict()
    out_b = run_deepseek_offline_sandbox(
        sandbox_input=_make_input(),
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(payload=payload),
    ).to_dict()
    assert out_a == out_b


# ---------------------------------------------------------------------------
# 14. JSON serializable output
# ---------------------------------------------------------------------------
def test_output_round_trips_as_json() -> None:
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(
            payload=_make_supported_payload()
        ),
    )
    output = runner.run(_make_input())
    encoded = json.dumps(output.to_dict())
    decoded = json.loads(encoded)
    # Round-trip is identity at the dict level.
    assert decoded == output.to_dict()


def test_output_contains_no_forbidden_keys_at_any_depth() -> None:
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(
            payload=_make_supported_payload()
        ),
    )
    output = runner.run(_make_input())
    decoded = output.to_dict()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                # The serialised payload contains a
                # ``forbidden_fields`` reference list - a list
                # of strings naming the forbidden keys. That
                # list is allowed (it documents what is
                # forbidden); the recursive guard only forbids
                # such names from appearing as KEYS.
                assert key not in FORBIDDEN_INTELLIGENCE_OUTPUT_FIELDS
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(decoded)


# ---------------------------------------------------------------------------
# 15. no Phase 12 / no live authority
# ---------------------------------------------------------------------------
def test_output_pins_no_live_authority_and_no_phase_12() -> None:
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(
            payload=_make_supported_payload()
        ),
    )
    output = runner.run(_make_input())
    decoded = output.to_dict()
    assert decoded["trade_authority"] is False
    assert decoded["auto_tuning_allowed"] is False
    assert decoded["phase_12_forbidden"] is True
    safety = decoded["safety_flags"]
    assert safety["mode"] == "paper"
    assert safety["live_trading"] is False
    assert safety["exchange_live_orders"] is False
    assert safety["right_tail"] is False
    assert safety["llm"] is False
    assert safety["llm_outbound_enabled"] is False
    assert safety["sandbox_only"] is True
    assert safety["telegram_outbound_enabled"] is False
    assert safety["binance_private_api_enabled"] is False


def test_intelligence_authority_level_has_no_trade_member() -> None:
    """No member of :class:`AIIntelligenceAuthorityLevel` may
    grant trade authority."""
    members = {m.value for m in AIIntelligenceAuthorityLevel}
    assert members == {
        "COMMENTARY_ONLY",
        "SUPPORTED_INTELLIGENCE",
        "DEGRADED_NO_EVIDENCE",
        "DEGRADED_REALITY_CHECK",
        "REJECTED",
    }


# ---------------------------------------------------------------------------
# Defensive companions
# ---------------------------------------------------------------------------
def test_unknown_task_type_is_rejected() -> None:
    si = DeepSeekSandboxInput(
        evidence_bundle=_make_bundle(),
        task_type="UNKNOWN_TASK_TYPE",
        operator_instruction="ignored",
    )
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(
            payload=_make_supported_payload()
        ),
    )
    output = runner.run(si)
    assert (
        output.status is AIIntelligenceStatus.REJECTED_INVALID_INPUT
    )


def test_non_mapping_evidence_bundle_is_rejected() -> None:
    si = DeepSeekSandboxInput(
        evidence_bundle=[1, 2, 3],  # type: ignore[arg-type]
        task_type=AIIntelligenceTaskType.MARKET_INTELLIGENCE_SUMMARY,
        operator_instruction="ignored",
    )
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(
            payload=_make_supported_payload()
        ),
    )
    output = runner.run(si)
    assert (
        output.status is AIIntelligenceStatus.REJECTED_INVALID_INPUT
    )


def test_non_mapping_provider_response_degrades() -> None:
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=FakeDeepSeekProvider(
            payload_fn=lambda **_: ["not", "a", "mapping"]
        ),
    )
    output = runner.run(_make_input())
    assert (
        output.status is AIIntelligenceStatus.DEGRADED_PROVIDER_ERROR
    )


def test_outbound_enabled_without_provider_degrades_safely() -> None:
    runner = DeepSeekOfflineSandboxRunner(
        config=_enabled_config(outbound_enabled=True),
        provider=None,
    )
    output = runner.run(_make_input())
    assert (
        output.status is AIIntelligenceStatus.DEGRADED_OUTBOUND_DISABLED
    )
    assert "outbound_enabled_but_no_provider" in output.warnings


def test_phase_identity_constants_are_stable() -> None:
    assert AI_INTELLIGENCE_OUTPUT_SCHEMA_VERSION == "v0"
    assert AI_INTELLIGENCE_OUTPUT_SOURCE_PHASE == "phase_ai_4"
    assert (
        AI_INTELLIGENCE_OUTPUT_SOURCE_MODULE
        == "ai_intelligence_output"
    )
    assert DEEPSEEK_SANDBOX_SCHEMA_VERSION == "v0"
    assert DEEPSEEK_SANDBOX_SOURCE_PHASE == "phase_ai_4"
    assert (
        DEEPSEEK_SANDBOX_SOURCE_MODULE
        == "ai_deepseek_offline_sandbox"
    )


def test_init_module_re_exports_phase_ai_4_surface() -> None:
    src = INIT_SRC_PATH.read_text(encoding="utf-8")
    for name in (
        "DeepSeekSandboxConfig",
        "DeepSeekSandboxInput",
        "DeepSeekProviderProtocol",
        "FakeDeepSeekProvider",
        "OptionalDeepSeekHTTPProvider",
        "DeepSeekOfflineSandboxRunner",
        "AIIntelligenceOutput",
        "AIIntelligenceTaskType",
        "AIIntelligenceAuthorityLevel",
        "AIIntelligenceStatus",
        "AIIntelligenceClaim",
        "FORBIDDEN_INTELLIGENCE_OUTPUT_FIELDS",
        "redact_secrets",
        "strip_forbidden_fields",
        "run_deepseek_offline_sandbox",
    ):
        assert name in src, (
            f"app/ai/__init__.py is missing the Phase AI-4 "
            f"re-export {name!r}."
        )
