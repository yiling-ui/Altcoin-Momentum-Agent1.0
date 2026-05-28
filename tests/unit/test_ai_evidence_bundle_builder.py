"""Phase AI-1 - AI Evidence Bundle Builder v0 tests.

The brief mandates that this test module covers, at minimum:

  1. builds bundle from valid evidence-cited facts
  2. drops or degrades facts without ``evidence_refs``
  3. preserves ``evidence_refs``
  4. injects ``forbidden_fields``
  5. injects ``lookahead_policy``
  6. injects ``consumer_contract``
  7. rejects / warns on ``previous_ai_answer`` input
  8. rejects / warns on ``chat_history`` input
  9. rejects / warns on ``private_account_state`` input
 10. rejects / warns on ``api_secret`` / credential-like fields
 11. no forbidden output fields as actionable decisions
 12. deterministic output
 13. JSON-serializable output
 14. forbidden imports: must not import ``app.risk`` /
     ``app.execution`` / ``app.exchanges`` / ``app.llm`` /
     ``app.telegram``
 15. no LLM / DeepSeek call path
 16. AI output cannot become truth / training label field

The tests below address every brief-mandated scenario plus a
handful of defensive companion checks (safety-flag block,
phase-12-forbidden pin, no-trade-authority pin, build-status
taxonomy).

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
    AI_EVIDENCE_BUNDLE_SCHEMA_VERSION,
    AI_EVIDENCE_BUNDLE_SOURCE_MODULE,
    AI_EVIDENCE_BUNDLE_SOURCE_PHASE,
    ALLOWED_CONSUMERS,
    CREDENTIAL_LIKE_KEY_TOKENS,
    FORBIDDEN_AI_OUTPUT_FIELDS,
    FORBIDDEN_CONSUMERS,
    FORBIDDEN_INPUT_KEYS,
    LOOKAHEAD_POLICY_FLAGS,
    AIEvidenceBundle,
    AIEvidenceBundleBuilder,
    AIEvidenceBundleBuildStatus,
    AIEvidenceBundleFact,
    AIEvidenceBundleFactInput,
    AIEvidenceBundleTaskType,
    ForbiddenAIInputError,
    build_ai_evidence_bundle,
)


SRC_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "ai"
    / "evidence_bundle.py"
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


def _walk_strings(payload):
    if isinstance(payload, dict):
        for k, v in payload.items():
            yield from _walk_strings(k)
            yield from _walk_strings(v)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            yield from _walk_strings(item)
    elif isinstance(payload, str):
        yield payload


def _make_market_fact(
    fact_id: str = "mkt-1",
    *,
    evidence_refs: tuple[str, ...] = (
        "event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_123",
    ),
) -> AIEvidenceBundleFactInput:
    return AIEvidenceBundleFactInput(
        fact_id=fact_id,
        fact_type="market_fact",
        content={
            "symbol": "RAVEUSDT",
            "regime": "altcoin_momentum",
            "narrative": "demo right-tail mover",
        },
        evidence_refs=evidence_refs,
        source_report="block_b_integrated_evidence_report",
    )


def _make_outcome_fact(
    fact_id: str = "out-1",
    *,
    evidence_refs: tuple[str, ...] = (
        "report:post_discovery_outcome_report",
    ),
) -> AIEvidenceBundleFactInput:
    return AIEvidenceBundleFactInput(
        fact_id=fact_id,
        fact_type="post_discovery_outcome",
        content={
            "outcome_label": "INSUFFICIENT_PRICE_PATH",
            "evaluated_count": 300,
        },
        evidence_refs=evidence_refs,
        source_report="post_discovery_outcome_report",
    )


def _build_minimal(
    *,
    market_facts=None,
    outcome_facts=None,
    phase_context=None,
    task_type=AIEvidenceBundleTaskType.OPERATOR_BRIEFING,
) -> AIEvidenceBundle:
    builder = AIEvidenceBundleBuilder()
    return builder.build(
        bundle_id="bundle_test_001",
        created_at_utc="2026-05-28T12:00:00Z",
        task_type=task_type,
        phase_context=phase_context or {"phase": "phase_ai_1"},
        reference_window="60d",
        market_facts=market_facts,
        outcome_facts=outcome_facts,
    )


# ---------------------------------------------------------------------------
# 1. builds bundle from valid evidence-cited facts
# ---------------------------------------------------------------------------
def test_builds_bundle_from_valid_evidence_cited_facts() -> None:
    bundle = _build_minimal(
        market_facts=[_make_market_fact()],
        outcome_facts=[_make_outcome_fact()],
    )

    assert isinstance(bundle, AIEvidenceBundle)
    assert bundle.bundle_id == "bundle_test_001"
    assert bundle.task_type is AIEvidenceBundleTaskType.OPERATOR_BRIEFING
    assert bundle.reference_window == "60d"
    assert bundle.accepted_fact_count == 2
    assert bundle.degraded_fact_count == 0
    assert (
        bundle.build_status
        is AIEvidenceBundleBuildStatus.EVIDENCE_BUNDLE_BUILT
    )
    assert bundle.schema_version == AI_EVIDENCE_BUNDLE_SCHEMA_VERSION
    assert bundle.source_phase == AI_EVIDENCE_BUNDLE_SOURCE_PHASE
    assert bundle.source_module == AI_EVIDENCE_BUNDLE_SOURCE_MODULE
    assert len(bundle.market_facts) == 1
    assert len(bundle.outcome_facts) == 1
    # Accepted facts carry their per-fact status.
    assert bundle.market_facts[0].status == "ACCEPTED"
    assert bundle.outcome_facts[0].status == "ACCEPTED"


def test_build_status_insufficient_when_no_facts_supplied() -> None:
    bundle = _build_minimal()
    assert (
        bundle.build_status
        is AIEvidenceBundleBuildStatus.EVIDENCE_BUNDLE_INSUFFICIENT_EVIDENCE
    )
    assert "no_facts_supplied" in bundle.warnings


def test_each_task_type_member_present() -> None:
    """Every brief-mandated task type is represented in the closed enum."""
    expected = {
        "OPERATOR_BRIEFING",
        "MARKET_INTELLIGENCE_SUMMARY",
        "COVERAGE_AUDIT_INTERPRETATION",
        "POST_DISCOVERY_OUTCOME_SUMMARY",
        "REJECT_TO_OUTCOME_SUMMARY",
        "SEVERE_MISS_SUMMARY",
        "REPLAY_REFLECTION_SUMMARY",
        "EVIDENCE_COMPRESSION",
        "CONTRADICTION_SUMMARY",
        "EVIDENCE_QUALITY_ASSESSMENT",
    }
    actual = {member.value for member in AIEvidenceBundleTaskType}
    assert expected.issubset(actual)


# ---------------------------------------------------------------------------
# 2. drops or degrades facts without evidence_refs
# ---------------------------------------------------------------------------
def test_drops_or_degrades_facts_without_evidence_refs() -> None:
    """A fact with no ``evidence_refs`` MUST be degraded (NEVER
    accepted as fact). The accepted ``*_facts`` collections must
    not contain it; the degraded record AND a warning are
    produced instead.
    """

    bundle = _build_minimal(
        market_facts=[
            _make_market_fact(),
            AIEvidenceBundleFactInput(
                fact_id="mkt-no-refs",
                fact_type="market_fact",
                content={"symbol": "BTCUSDT", "narrative": "demo"},
                evidence_refs=(),
            ),
        ],
    )

    # Only the cited fact is accepted.
    assert bundle.accepted_fact_count == 1
    assert bundle.degraded_fact_count == 1
    assert len(bundle.market_facts) == 1
    assert bundle.market_facts[0].fact_id == "mkt-1"

    # The uncited fact is preserved as degraded with the
    # documented reason.
    assert len(bundle.degraded_facts) == 1
    degraded = bundle.degraded_facts[0]
    assert degraded.fact_id == "mkt-no-refs"
    assert degraded.status == "DEGRADED_NO_EVIDENCE"
    assert degraded.degradation_reason == "no_evidence_refs_supplied"

    # And a matching warning is emitted.
    assert any(
        "degraded:market_facts:mkt-no-refs" in w
        for w in bundle.warnings
    )

    # Build status reflects the degradation.
    assert (
        bundle.build_status
        is AIEvidenceBundleBuildStatus.EVIDENCE_BUNDLE_DEGRADED
    )


# ---------------------------------------------------------------------------
# 3. preserves evidence_refs
# ---------------------------------------------------------------------------
def test_preserves_evidence_refs_per_fact_and_aggregated() -> None:
    """Per-fact evidence_refs are preserved verbatim, in input order;
    the bundle-level ``evidence_refs`` is the deduplicated union
    in first-seen order."""

    refs_a = (
        "event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_a",
        "symbol:RAVEUSDT",
    )
    refs_b = (
        "report:post_discovery_outcome_report",
        "event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_a",
    )

    bundle = _build_minimal(
        market_facts=[_make_market_fact(evidence_refs=refs_a)],
        outcome_facts=[_make_outcome_fact(evidence_refs=refs_b)],
    )

    # Per-fact refs preserved verbatim, in input order.
    assert bundle.market_facts[0].evidence_refs == refs_a
    assert bundle.outcome_facts[0].evidence_refs == refs_b

    # Bundle-level refs deduplicated, first-seen order preserved.
    assert bundle.evidence_refs == (
        "event:HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED:evt_a",
        "symbol:RAVEUSDT",
        "report:post_discovery_outcome_report",
    )


# ---------------------------------------------------------------------------
# 4. injects forbidden_fields
# ---------------------------------------------------------------------------
def test_injects_forbidden_fields_and_covers_brief_minimum_set() -> None:
    bundle = _build_minimal(market_facts=[_make_market_fact()])

    # forbidden_fields is a sorted tuple of strings.
    assert isinstance(bundle.forbidden_fields, tuple)
    assert all(isinstance(f, str) for f in bundle.forbidden_fields)
    assert list(bundle.forbidden_fields) == sorted(bundle.forbidden_fields)

    expected_minimum = {
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
    assert expected_minimum.issubset(set(bundle.forbidden_fields))

    # And the same keys are present in the FORBIDDEN_AI_OUTPUT_FIELDS
    # constant.
    assert expected_minimum.issubset(FORBIDDEN_AI_OUTPUT_FIELDS)


# ---------------------------------------------------------------------------
# 5. injects lookahead_policy
# ---------------------------------------------------------------------------
def test_injects_lookahead_policy_with_brief_minimum_flags() -> None:
    bundle = _build_minimal(market_facts=[_make_market_fact()])

    expected = {
        "frozen_evidence_only",
        "no_future_market_data",
        "no_training_from_ai_output",
        "no_runtime_feedback",
        "post_hoc_analysis_only_when_window_closed",
    }
    assert expected.issubset(set(bundle.lookahead_policy.keys()))
    for flag in expected:
        assert bundle.lookahead_policy[flag] is True

    # And the LOOKAHEAD_POLICY_FLAGS constant is consistent.
    assert expected.issubset(set(LOOKAHEAD_POLICY_FLAGS))


# ---------------------------------------------------------------------------
# 6. injects consumer_contract
# ---------------------------------------------------------------------------
def test_injects_consumer_contract_with_allowed_and_forbidden_consumers() -> None:
    bundle = _build_minimal(market_facts=[_make_market_fact()])

    contract = bundle.consumer_contract
    allowed = list(contract["allowed_consumers"])
    forbidden = list(contract["forbidden_consumers"])

    expected_allowed = {
        "human_operator",
        "export_bundle",
        "replay_annotation",
        "reflection_annotation",
        "operator_briefing_report",
    }
    expected_forbidden = {
        "RiskEngine",
        "ExecutionFSM",
        "StrategyEngine",
        "ExchangeGateway",
        "RuntimeConfig",
        "TelegramLiveCommand",
        "CapitalFlow",
        "PositionManager",
    }
    assert expected_allowed.issubset(set(allowed))
    assert expected_forbidden.issubset(set(forbidden))

    # The allowed and forbidden lists must be disjoint.
    assert set(allowed).isdisjoint(set(forbidden))

    # And the constants are consistent.
    assert expected_allowed.issubset(set(ALLOWED_CONSUMERS))
    assert expected_forbidden.issubset(set(FORBIDDEN_CONSUMERS))

    # The contract block is also commentary-only / no trade
    # authority.
    assert contract["ai_output_is_commentary_only"] is True
    assert contract["ai_output_can_be_training_label"] is False
    assert contract["no_trade_authority"] is True
    assert contract["no_runtime_config_patch_authority"] is True


# ---------------------------------------------------------------------------
# 7. rejects / warns on previous_ai_answer input
# ---------------------------------------------------------------------------
def test_rejects_previous_ai_answer_in_phase_context() -> None:
    builder = AIEvidenceBundleBuilder()
    with pytest.raises(ForbiddenAIInputError) as exc:
        builder.build(
            bundle_id="bundle_test_002",
            created_at_utc="2026-05-28T12:00:00Z",
            task_type=AIEvidenceBundleTaskType.OPERATOR_BRIEFING,
            phase_context={
                "phase": "phase_ai_1",
                "previous_ai_answer": "the AI said X yesterday",
            },
        )
    assert "previous_ai_answer" in str(exc.value)


def test_rejects_previous_ai_answer_nested_in_fact_content() -> None:
    builder = AIEvidenceBundleBuilder()
    bad_fact = AIEvidenceBundleFactInput(
        fact_id="bad-1",
        fact_type="market_fact",
        content={
            "symbol": "RAVEUSDT",
            # Smuggle previous AI answer in via nested mapping.
            "context": {"previous_ai_answer": "AI said long yesterday"},
        },
        evidence_refs=("symbol:RAVEUSDT",),
    )
    with pytest.raises(ForbiddenAIInputError):
        builder.build(
            bundle_id="bundle_test_003",
            created_at_utc="2026-05-28T12:00:00Z",
            task_type=AIEvidenceBundleTaskType.OPERATOR_BRIEFING,
            market_facts=[bad_fact],
        )


# ---------------------------------------------------------------------------
# 8. rejects / warns on chat_history input
# ---------------------------------------------------------------------------
def test_rejects_chat_history_in_phase_context() -> None:
    builder = AIEvidenceBundleBuilder()
    with pytest.raises(ForbiddenAIInputError) as exc:
        builder.build(
            bundle_id="bundle_test_004",
            created_at_utc="2026-05-28T12:00:00Z",
            task_type=AIEvidenceBundleTaskType.OPERATOR_BRIEFING,
            phase_context={
                "phase": "phase_ai_1",
                "chat_history": [{"role": "user", "content": "hello"}],
            },
        )
    assert "chat_history" in str(exc.value)


def test_rejects_conversation_history_alias_input() -> None:
    """Aliases like ``conversation_history`` / ``ai_session_history``
    are also rejected."""
    builder = AIEvidenceBundleBuilder()
    for forbidden_alias in (
        "conversation_history",
        "ai_session_history",
        "previous_briefing",
    ):
        with pytest.raises(ForbiddenAIInputError):
            builder.build(
                bundle_id="bundle_test_005",
                created_at_utc="2026-05-28T12:00:00Z",
                task_type=AIEvidenceBundleTaskType.OPERATOR_BRIEFING,
                phase_context={forbidden_alias: ["something"]},
            )


# ---------------------------------------------------------------------------
# 9. rejects / warns on private_account_state input
# ---------------------------------------------------------------------------
def test_rejects_private_account_state_in_phase_context() -> None:
    builder = AIEvidenceBundleBuilder()
    with pytest.raises(ForbiddenAIInputError) as exc:
        builder.build(
            bundle_id="bundle_test_006",
            created_at_utc="2026-05-28T12:00:00Z",
            task_type=AIEvidenceBundleTaskType.OPERATOR_BRIEFING,
            phase_context={
                "private_account_state": {
                    "balance_usdt": 10000.0,
                    "open_positions": [],
                },
            },
        )
    assert "private_account_state" in str(exc.value)


def test_rejects_private_account_state_aliases() -> None:
    """Aliases for private account state (``account_balance`` /
    ``account_positions`` / ``listen_key`` / ``wallet_balance``)
    are also rejected."""
    builder = AIEvidenceBundleBuilder()
    for forbidden_alias in (
        "account_balance",
        "account_positions",
        "account_orders",
        "wallet_balance",
        "listen_key",
        "binance_private_account_state",
    ):
        with pytest.raises(ForbiddenAIInputError):
            builder.build(
                bundle_id="bundle_test_007",
                created_at_utc="2026-05-28T12:00:00Z",
                task_type=(
                    AIEvidenceBundleTaskType.OPERATOR_BRIEFING
                ),
                phase_context={forbidden_alias: "something"},
            )


# ---------------------------------------------------------------------------
# 10. rejects / warns on api_secret / credential-like fields
# ---------------------------------------------------------------------------
def test_rejects_api_secret_credential_like_inputs() -> None:
    builder = AIEvidenceBundleBuilder()
    for forbidden_alias in (
        "api_key",
        "api_secret",
        "binance_api_key",
        "binance_api_secret",
        "deepseek_api_key",
        "telegram_bot_token",
        "auth_token",
        "bearer_token",
        "private_key",
        "password",
    ):
        with pytest.raises(ForbiddenAIInputError):
            builder.build(
                bundle_id="bundle_test_008",
                created_at_utc="2026-05-28T12:00:00Z",
                task_type=AIEvidenceBundleTaskType.OPERATOR_BRIEFING,
                phase_context={forbidden_alias: "REDACTED-VALUE"},
            )


def test_rejects_credential_like_substrings_at_any_nesting_depth() -> None:
    builder = AIEvidenceBundleBuilder()
    fact = AIEvidenceBundleFactInput(
        fact_id="bad-secret-fact",
        fact_type="market_fact",
        content={
            "symbol": "RAVEUSDT",
            # Smuggle credential via nested mapping.
            "auth": {"api_secret": "REDACTED"},
        },
        evidence_refs=("symbol:RAVEUSDT",),
    )
    with pytest.raises(ForbiddenAIInputError):
        builder.build(
            bundle_id="bundle_test_009",
            created_at_utc="2026-05-28T12:00:00Z",
            task_type=AIEvidenceBundleTaskType.OPERATOR_BRIEFING,
            market_facts=[fact],
        )


def test_credential_like_string_value_is_allowed_only_keys_blocked() -> None:
    """Only credential-shaped KEY names are rejected; a string
    value that happens to contain the word ``secret`` (e.g. a
    narrative description) MUST NOT trigger the guard, otherwise
    free-form market commentary becomes impossible."""
    builder = AIEvidenceBundleBuilder()
    fact = AIEvidenceBundleFactInput(
        fact_id="narrative-1",
        fact_type="market_fact",
        content={
            "symbol": "RAVEUSDT",
            "narrative": "the team kept their roadmap secret",
        },
        evidence_refs=("symbol:RAVEUSDT",),
    )
    # Should NOT raise.
    bundle = builder.build(
        bundle_id="bundle_test_010",
        created_at_utc="2026-05-28T12:00:00Z",
        task_type=AIEvidenceBundleTaskType.OPERATOR_BRIEFING,
        market_facts=[fact],
    )
    assert bundle.accepted_fact_count == 1


# ---------------------------------------------------------------------------
# 11. no forbidden output fields as actionable decisions
# ---------------------------------------------------------------------------
def test_forbidden_output_field_smuggled_into_fact_content_is_rejected() -> None:
    """A caller MUST NOT be able to smuggle a ``buy`` /
    ``leverage`` / ``runtime_config_patch`` key into the bundle
    via the fact's ``content`` payload.
    """
    builder = AIEvidenceBundleBuilder()
    fact = AIEvidenceBundleFactInput(
        fact_id="bad-output-fact",
        fact_type="market_fact",
        content={
            "symbol": "RAVEUSDT",
            "buy": True,  # forbidden.
        },
        evidence_refs=("symbol:RAVEUSDT",),
    )
    with pytest.raises(ValueError):
        builder.build(
            bundle_id="bundle_test_011",
            created_at_utc="2026-05-28T12:00:00Z",
            task_type=AIEvidenceBundleTaskType.OPERATOR_BRIEFING,
            market_facts=[fact],
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "buy",
        "sell",
        "direction",
        "leverage",
        "stop_loss",
        "take_profit",
        "position_size",
        "risk_budget",
        "order",
        "execution_command",
        "runtime_config_patch",
        "symbol_limit_patch",
        "regime_weight_patch",
        "should_buy",
        "should_short",
        "trading_approved",
        "live_ready",
        "live_trading_allowed",
    ],
)
def test_no_forbidden_field_appears_in_serialized_bundle(field_name) -> None:
    """A successfully built bundle's serialised payload MUST NOT
    contain any forbidden output field at any nesting depth."""
    bundle = _build_minimal(
        market_facts=[_make_market_fact()],
        outcome_facts=[_make_outcome_fact()],
    )
    payload = bundle.to_dict()
    keys = list(_walk_keys(payload))
    assert field_name not in keys, (
        f"Forbidden output field {field_name!r} appeared in the "
        "serialised bundle payload."
    )


# ---------------------------------------------------------------------------
# 12. deterministic output
# ---------------------------------------------------------------------------
def test_bundle_output_is_deterministic_for_identical_inputs() -> None:
    a = _build_minimal(
        market_facts=[_make_market_fact()],
        outcome_facts=[_make_outcome_fact()],
    )
    b = _build_minimal(
        market_facts=[_make_market_fact()],
        outcome_facts=[_make_outcome_fact()],
    )
    assert a.to_dict() == b.to_dict()
    assert json.dumps(a.to_dict(), sort_keys=False) == json.dumps(
        b.to_dict(), sort_keys=False
    )


def test_convenience_wrapper_matches_builder_output() -> None:
    """``build_ai_evidence_bundle`` and
    ``AIEvidenceBundleBuilder().build`` produce equivalent output
    for identical inputs."""
    inputs = dict(
        bundle_id="bundle_test_012",
        created_at_utc="2026-05-28T12:00:00Z",
        task_type=AIEvidenceBundleTaskType.MARKET_INTELLIGENCE_SUMMARY,
        phase_context={"phase": "phase_ai_1"},
        reference_window="60d",
        market_facts=[_make_market_fact()],
    )
    builder_out = AIEvidenceBundleBuilder().build(**inputs)
    wrapper_out = build_ai_evidence_bundle(**inputs)
    assert builder_out.to_dict() == wrapper_out.to_dict()


# ---------------------------------------------------------------------------
# 13. JSON-serializable output
# ---------------------------------------------------------------------------
def test_bundle_payload_is_json_serializable() -> None:
    bundle = _build_minimal(
        market_facts=[_make_market_fact()],
        outcome_facts=[_make_outcome_fact()],
    )
    payload = bundle.to_dict()
    # Must round-trip via json without a custom encoder.
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["schema_version"] == AI_EVIDENCE_BUNDLE_SCHEMA_VERSION
    assert decoded["task_type"] == bundle.task_type.value
    assert decoded["build_status"] == bundle.build_status.value
    assert decoded["accepted_fact_count"] == 2
    assert decoded["degraded_fact_count"] == 0
    assert decoded["phase_12_forbidden"] is True
    assert decoded["auto_tuning_allowed"] is False
    assert decoded["ai_output_is_commentary_only"] is True
    assert decoded["ai_output_can_be_training_label"] is False
    assert decoded["safety_flags"]["mode"] == "paper"
    assert decoded["safety_flags"]["live_trading"] is False
    assert decoded["safety_flags"]["llm"] is False
    assert decoded["safety_flags"]["binance_private_api_enabled"] is False


# ---------------------------------------------------------------------------
# 14. forbidden imports
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


def test_evidence_bundle_module_does_not_import_forbidden_modules() -> None:
    """Phase AI-1 boundary: the AI evidence bundle module MUST NOT
    import Risk / Execution / Exchange / LLM / Telegram / Config
    modules. Importing any of them would compromise either the
    Responsibility Isolation constraint (AI is read-only) or the
    Stateless Inference constraint (AI never reads runtime config).
    """
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
            "this violates the Phase AI-1 boundary."
        )


# ---------------------------------------------------------------------------
# 15. no LLM / DeepSeek call path
# ---------------------------------------------------------------------------
def test_no_deepseek_or_llm_or_http_call_path_in_imports() -> None:
    """The module MUST NOT import any LLM / DeepSeek / HTTP client.
    The AI Evidence Bundle layer is offline, deterministic, and
    has no transport.
    """
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
            "AI-1 boundary."
        )


def test_module_exposes_no_llm_client_callable() -> None:
    """A defensive check: the module MUST NOT expose any callable
    whose name suggests an LLM client (e.g. ``call_deepseek``,
    ``invoke_llm``)."""
    import app.ai.evidence_bundle as mod

    public = [
        name
        for name in dir(mod)
        if not name.startswith("_")
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
        "AI evidence bundle module exposes LLM-client-shaped "
        f"callables: {bad!r}; this violates the Phase AI-1 boundary."
    )


# ---------------------------------------------------------------------------
# 16. AI output cannot become truth / training label field
# ---------------------------------------------------------------------------
def test_bundle_pins_ai_output_is_commentary_only_and_not_training_label() -> None:
    """The bundle MUST hard-pin
    ``ai_output_is_commentary_only=True`` and
    ``ai_output_can_be_training_label=False`` so AI output can
    never become a training label or a runtime fact, even if a
    downstream consumer flips the dataclass field.
    """

    bundle = _build_minimal(market_facts=[_make_market_fact()])

    # Top-level fields hard-pinned by ``to_dict``.
    payload = bundle.to_dict()
    assert payload["ai_output_is_commentary_only"] is True
    assert payload["ai_output_can_be_training_label"] is False

    # Even if the dataclass field is flipped (frozen=True
    # prevents direct mutation, so emulate via object.__setattr__),
    # ``to_dict`` re-pins the safe values.
    object.__setattr__(bundle, "ai_output_is_commentary_only", False)
    object.__setattr__(bundle, "ai_output_can_be_training_label", True)
    object.__setattr__(bundle, "auto_tuning_allowed", True)
    object.__setattr__(bundle, "phase_12_forbidden", False)
    repinned = bundle.to_dict()
    assert repinned["ai_output_is_commentary_only"] is True
    assert repinned["ai_output_can_be_training_label"] is False
    assert repinned["auto_tuning_allowed"] is False
    assert repinned["phase_12_forbidden"] is True


def test_consumer_contract_rejects_any_truth_layer_or_runtime_consumer() -> None:
    """Even structurally, the consumer contract names every
    Truth-Layer / runtime-config surface as forbidden."""
    bundle = _build_minimal(market_facts=[_make_market_fact()])
    forbidden = set(bundle.consumer_contract["forbidden_consumers"])
    # Structural surfaces that, if they consumed the bundle, would
    # turn AI commentary into runtime fact.
    must_be_forbidden = {
        "RiskEngine",
        "ExecutionFSM",
        "StrategyEngine",
        "ExchangeGateway",
        "RuntimeConfig",
        "TelegramLiveCommand",
        "CapitalFlow",
        "PositionManager",
    }
    assert must_be_forbidden.issubset(forbidden)


# ---------------------------------------------------------------------------
# Defensive companions (not on the brief's numbered list, but
# protect the same root-constraint surface).
# ---------------------------------------------------------------------------
def test_safety_flag_block_pinned_in_serialised_payload() -> None:
    bundle = _build_minimal(market_facts=[_make_market_fact()])
    payload = bundle.to_dict()
    flags = payload["safety_flags"]
    assert flags == {
        "mode": "paper",
        "live_trading": False,
        "exchange_live_orders": False,
        "right_tail": False,
        "llm": False,
        "telegram_outbound_enabled": False,
        "binance_private_api_enabled": False,
    }


def test_string_task_type_is_coerced_to_enum() -> None:
    bundle = _build_minimal(
        market_facts=[_make_market_fact()],
        task_type="EVIDENCE_QUALITY_ASSESSMENT",
    )
    assert (
        bundle.task_type
        is AIEvidenceBundleTaskType.EVIDENCE_QUALITY_ASSESSMENT
    )


def test_unknown_task_type_string_is_rejected() -> None:
    builder = AIEvidenceBundleBuilder()
    with pytest.raises(ValueError):
        builder.build(
            bundle_id="bundle_test_unknown_task",
            created_at_utc="2026-05-28T12:00:00Z",
            task_type="NOT_A_REAL_TASK",
        )


def test_empty_bundle_id_is_rejected() -> None:
    builder = AIEvidenceBundleBuilder()
    with pytest.raises(ValueError):
        builder.build(
            bundle_id="   ",
            created_at_utc="2026-05-28T12:00:00Z",
            task_type=AIEvidenceBundleTaskType.OPERATOR_BRIEFING,
        )


def test_empty_created_at_utc_is_rejected() -> None:
    builder = AIEvidenceBundleBuilder()
    with pytest.raises(ValueError):
        builder.build(
            bundle_id="bundle_test_empty_ts",
            created_at_utc="",
            task_type=AIEvidenceBundleTaskType.OPERATOR_BRIEFING,
        )


def test_fact_to_dict_is_json_serializable_and_no_forbidden_fields() -> None:
    bundle = _build_minimal(market_facts=[_make_market_fact()])
    fact_payload = bundle.market_facts[0].to_dict()
    encoded = json.dumps(fact_payload)
    decoded = json.loads(encoded)
    assert decoded["fact_id"] == "mkt-1"
    assert decoded["status"] == "ACCEPTED"
    keys = list(_walk_keys(decoded))
    for forbidden in FORBIDDEN_AI_OUTPUT_FIELDS:
        assert forbidden not in keys


def test_credential_token_constants_are_consistent() -> None:
    """Every credential-like token is a non-empty lowercase string."""
    for token in CREDENTIAL_LIKE_KEY_TOKENS:
        assert token == token.lower() and token.strip() != ""


def test_forbidden_input_keys_constants_are_consistent() -> None:
    """Every forbidden input key is a non-empty lowercase string."""
    for key in FORBIDDEN_INPUT_KEYS:
        assert key == key.lower() and key.strip() != ""


def test_source_reports_are_deduplicated_and_first_seen_order() -> None:
    bundle = _build_minimal(
        market_facts=[
            _make_market_fact(),
            AIEvidenceBundleFactInput(
                fact_id="mkt-2",
                fact_type="market_fact",
                content={"symbol": "ETHUSDT"},
                evidence_refs=("symbol:ETHUSDT",),
                source_report="block_b_integrated_evidence_report",
            ),
            AIEvidenceBundleFactInput(
                fact_id="mkt-3",
                fact_type="market_fact",
                content={"symbol": "BTCUSDT"},
                evidence_refs=("symbol:BTCUSDT",),
                source_report="discovery_quality_scorecard_report",
            ),
        ],
    )
    assert bundle.source_reports == (
        "block_b_integrated_evidence_report",
        "discovery_quality_scorecard_report",
    )


def test_warnings_preserve_caller_supplied_entries() -> None:
    builder = AIEvidenceBundleBuilder()
    bundle = builder.build(
        bundle_id="bundle_test_warn",
        created_at_utc="2026-05-28T12:00:00Z",
        task_type=AIEvidenceBundleTaskType.OPERATOR_BRIEFING,
        market_facts=[_make_market_fact()],
        warnings=(
            "operator_supplied:reference_window_partial",
            "operator_supplied:notable_symbol_unresolved:RAVEUSDT",
        ),
    )
    assert (
        "operator_supplied:reference_window_partial" in bundle.warnings
    )
    assert any(
        "RAVEUSDT" in w for w in bundle.warnings
    )


def test_phase_12_remains_forbidden_in_payload() -> None:
    bundle = _build_minimal(market_facts=[_make_market_fact()])
    payload = bundle.to_dict()
    assert payload["phase_12_forbidden"] is True
    assert payload["auto_tuning_allowed"] is False
