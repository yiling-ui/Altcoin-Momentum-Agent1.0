"""Phase AI-3 - Reality Check Layer v0 tests.

The brief mandates that this test module covers, at minimum:

  1. supported claim
  2. partially supported claim with confidence downgrade
  3. contradicted claim
  4. insufficient evidence
  5. lookahead violation
  6. unverifiable narrative
  7. confidence calibration (always <= raw)
  8. no trade authority on result
  9. forbidden fields absent on serialised result
 10. forbidden imports
 11. no DeepSeek / LLM / network call path
 12. deterministic output

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
    AI_REALITY_CHECK_SCHEMA_VERSION,
    AI_REALITY_CHECK_SOURCE_MODULE,
    AI_REALITY_CHECK_SOURCE_PHASE,
    FORBIDDEN_REALITY_CHECK_FIELDS,
    AIRealityCheckAuthorityLevel,
    AIRealityCheckCategory,
    AIRealityCheckEngine,
    AIRealityCheckInput,
    AIRealityCheckResult,
    AIRealityCheckStatus,
    reality_check_claim,
)


SRC_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "ai"
    / "reality_check.py"
)
INIT_SRC_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "ai"
    / "__init__.py"
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


def _safe_lookahead_policy() -> dict[str, bool]:
    """Return a policy where every required flag is True and
    no forbidden flag is set. Mirrors the Phase AI-1 bundle's
    pinned policy."""
    return {
        "frozen_evidence_only": True,
        "no_future_market_data": True,
        "no_training_from_ai_output": True,
        "no_runtime_feedback": True,
        "post_hoc_analysis_only_when_window_closed": True,
    }


def _make_supported_input(
    *,
    claim_id: str = "claim-supported-1",
    confidence_raw: float | None = 0.6,
) -> AIRealityCheckInput:
    return AIRealityCheckInput(
        claim_id=claim_id,
        claim_type="REGIME",
        claim_text=(
            "Recent 60d altcoin discovery quality remains "
            "broadly stable on the audit window."
        ),
        evidence_refs=(
            "symbol:RAVEUSDT",
            "report:post_discovery_outcome_report",
        ),
        truth_layer_fields_used=(
            "market_facts.breadth_score",
            "outcome_facts.outcome_label",
        ),
        authority_level="SUPPORTED_INTELLIGENCE",
        confidence_raw=confidence_raw,
        evidence_bundle_facts={"bundle_id": "bundle-1"},
        market_facts={
            "breadth_score": 0.78,
            "breadth_weak": False,
            "data_gap_rate": 0.05,
            "data_gap_severe": False,
        },
        system_behavior_facts={
            "late_chase_high": False,
            "late_chase_rate": 0.1,
            "fake_breakout_rising": False,
            "funding_overheated": False,
        },
        outcome_facts={
            "failed_continuation": False,
            "missed_strong_tail_rate": 0.2,
        },
        lookahead_policy=_safe_lookahead_policy(),
    )


# ---------------------------------------------------------------------------
# 1. supported claim
# ---------------------------------------------------------------------------
def test_supported_claim_yields_supported_status() -> None:
    engine = AIRealityCheckEngine()
    result = engine.check(_make_supported_input())

    assert isinstance(result, AIRealityCheckResult)
    assert result.status is AIRealityCheckStatus.SUPPORTED
    assert (
        result.authority_level_after_check
        is AIRealityCheckAuthorityLevel.SUPPORTED_INTELLIGENCE
    )
    assert result.degradation_reason is None
    # The cited evidence_refs are surfaced as supporting axis.
    assert "symbol:RAVEUSDT" in result.supporting_evidence_refs
    assert (
        "report:post_discovery_outcome_report"
        in result.supporting_evidence_refs
    )
    assert result.contradicting_evidence_refs == ()


def test_supported_claim_runs_every_required_category() -> None:
    """A SUPPORTED outcome must touch the LOOKAHEAD_GUARD,
    NARRATIVE_POLLUTION_GUARD, STATISTICAL_VERIFICATION,
    CONTRADICTION_DETECTION, MICROSTRUCTURE_VALIDATION,
    ADVERSARIAL_EVIDENCE_CHECK, CONFIDENCE_CALIBRATION
    categories."""
    result = AIRealityCheckEngine().check(_make_supported_input())
    cats = set(result.categories_checked)
    for required in (
        AIRealityCheckCategory.LOOKAHEAD_GUARD,
        AIRealityCheckCategory.NARRATIVE_POLLUTION_GUARD,
        AIRealityCheckCategory.STATISTICAL_VERIFICATION,
        AIRealityCheckCategory.CONTRADICTION_DETECTION,
        AIRealityCheckCategory.MICROSTRUCTURE_VALIDATION,
        AIRealityCheckCategory.ADVERSARIAL_EVIDENCE_CHECK,
        AIRealityCheckCategory.CONFIDENCE_CALIBRATION,
    ):
        assert required in cats


# ---------------------------------------------------------------------------
# 2. partially supported claim (confidence downgrade)
# ---------------------------------------------------------------------------
def test_partial_support_when_truth_field_group_is_empty() -> None:
    """Claim cites ``outcome_facts.outcome_label`` but the
    caller did not pass any ``outcome_facts``. The engine
    must demote to PARTIALLY_SUPPORTED and downgrade
    confidence."""
    ri = AIRealityCheckInput(
        claim_id="claim-partial-1",
        claim_type="REGIME",
        claim_text="60d momentum mostly stable.",
        evidence_refs=("symbol:RAVEUSDT",),
        truth_layer_fields_used=(
            "market_facts.breadth_score",
            "outcome_facts.outcome_label",
        ),
        confidence_raw=0.6,
        market_facts={"breadth_weak": False, "breadth_score": 0.7},
        # outcome_facts intentionally omitted.
        lookahead_policy=_safe_lookahead_policy(),
    )
    result = AIRealityCheckEngine().check(ri)
    assert (
        result.status is AIRealityCheckStatus.PARTIALLY_SUPPORTED
    )
    assert (
        result.confidence_reality_checked is not None
        and result.confidence_reality_checked < 0.6
    )
    assert any(
        w.startswith("truth_field_group_empty:")
        for w in result.warnings
    )


def test_partial_support_when_no_market_or_outcome_facts() -> None:
    """Claim cites evidence and supplies only the abstract
    ``evidence_bundle_facts`` but no concrete market /
    system-behavior / outcome facts. The engine must demote
    to PARTIALLY_SUPPORTED with a downgraded confidence."""
    ri = AIRealityCheckInput(
        claim_id="claim-partial-2",
        claim_type="REGIME",
        claim_text="60d momentum stable, evidence bundled.",
        evidence_refs=("symbol:RAVEUSDT",),
        confidence_raw=0.4,
        evidence_bundle_facts={"bundle_id": "bundle-2"},
        lookahead_policy=_safe_lookahead_policy(),
    )
    result = AIRealityCheckEngine().check(ri)
    assert (
        result.status is AIRealityCheckStatus.PARTIALLY_SUPPORTED
    )
    assert (
        result.confidence_reality_checked is not None
        and result.confidence_reality_checked <= 0.4
    )
    assert (
        "no_market_or_system_behavior_or_outcome_facts"
        in result.warnings
    )


# ---------------------------------------------------------------------------
# 3. contradicted claim
# ---------------------------------------------------------------------------
def test_expansion_claim_with_weak_breadth_is_contradicted() -> None:
    ri = AIRealityCheckInput(
        claim_id="claim-contradicted-1",
        claim_type="REGIME",
        claim_text=(
            "Risk appetite expanding rapidly across altcoins."
        ),
        evidence_refs=("symbol:RAVEUSDT",),
        truth_layer_fields_used=("market_facts.breadth_weak",),
        confidence_raw=0.7,
        market_facts={"breadth_weak": True, "data_gap_rate": 0.6},
        system_behavior_facts={
            "late_chase_high": True,
            "fake_breakout_rising": True,
        },
        outcome_facts={"failed_continuation": True},
        lookahead_policy=_safe_lookahead_policy(),
    )
    result = AIRealityCheckEngine().check(ri)
    assert result.status is AIRealityCheckStatus.CONTRADICTED
    assert (
        result.authority_level_after_check
        is AIRealityCheckAuthorityLevel.REJECTED_BY_REALITY_CHECK
    )
    assert (
        result.confidence_reality_checked == 0.0
        if result.confidence_raw is not None
        else result.confidence_reality_checked is None
    )
    assert result.degradation_reason is not None
    assert any(
        w.startswith("contradiction_signal:") for w in result.warnings
    )
    assert "symbol:RAVEUSDT" in result.contradicting_evidence_refs


def test_non_expansion_claim_with_one_microstructure_signal_demotes_to_partial() -> None:
    """A non-expansion claim that cites real evidence but
    rides on top of a single contradicting microstructure
    signal is demoted to PARTIALLY_SUPPORTED with the
    UNSUPPORTED_INTELLIGENCE warning level - the engine MUST
    NOT silently accept it as fully SUPPORTED."""
    ri = AIRealityCheckInput(
        claim_id="claim-partial-contradiction",
        claim_type="OUTCOME",
        claim_text=(
            "Discovery cohort shows mover capture coverage."
        ),
        evidence_refs=("report:mover_capture_recall_audit",),
        truth_layer_fields_used=(
            "outcome_facts.missed_strong_tail_rate",
        ),
        confidence_raw=0.6,
        market_facts={"breadth_weak": False},
        system_behavior_facts={"late_chase_high": False},
        outcome_facts={"missed_strong_tail_rate": 0.7},
        lookahead_policy=_safe_lookahead_policy(),
    )
    result = AIRealityCheckEngine().check(ri)
    assert (
        result.status is AIRealityCheckStatus.PARTIALLY_SUPPORTED
    )
    assert (
        result.authority_level_after_check
        is AIRealityCheckAuthorityLevel.UNSUPPORTED_INTELLIGENCE
    )
    assert (
        result.confidence_reality_checked is not None
        and result.confidence_reality_checked < 0.6
    )
    assert any(
        w.startswith("contradiction_signal:")
        for w in result.warnings
    )


# ---------------------------------------------------------------------------
# 4. insufficient evidence
# ---------------------------------------------------------------------------
def test_no_evidence_refs_is_insufficient_evidence() -> None:
    ri = AIRealityCheckInput(
        claim_id="claim-no-refs",
        claim_type="REGIME",
        claim_text="A bland claim with no citations.",
        evidence_refs=(),
        market_facts={"breadth_weak": False},
        lookahead_policy=_safe_lookahead_policy(),
    )
    result = AIRealityCheckEngine().check(ri)
    assert (
        result.status is AIRealityCheckStatus.INSUFFICIENT_EVIDENCE
    )
    assert (
        result.authority_level_after_check
        is AIRealityCheckAuthorityLevel.DEGRADED_NO_EVIDENCE
    )
    assert "missing_evidence_refs" in result.warnings


def test_no_facts_at_all_is_insufficient_evidence() -> None:
    ri = AIRealityCheckInput(
        claim_id="claim-no-facts",
        claim_type="REGIME",
        claim_text="A bland claim with citations but no facts.",
        evidence_refs=("symbol:RAVEUSDT",),
        lookahead_policy=_safe_lookahead_policy(),
    )
    result = AIRealityCheckEngine().check(ri)
    assert (
        result.status is AIRealityCheckStatus.INSUFFICIENT_EVIDENCE
    )
    assert (
        result.authority_level_after_check
        is AIRealityCheckAuthorityLevel.DEGRADED_NO_EVIDENCE
    )
    assert "missing_evidence_bundle_facts" in result.warnings


# ---------------------------------------------------------------------------
# 5. lookahead violation
# ---------------------------------------------------------------------------
def test_explicit_future_outcome_flag_rejects_lookahead() -> None:
    ri = AIRealityCheckInput(
        claim_id="claim-lookahead-1",
        claim_type="OUTCOME",
        claim_text="The next 5min window will close green.",
        evidence_refs=("symbol:BTCUSDT",),
        market_facts={"breadth_weak": False},
        lookahead_policy={"live_inference_uses_future_outcome": True},
    )
    result = AIRealityCheckEngine().check(ri)
    assert result.status is AIRealityCheckStatus.REJECTED_LOOKAHEAD
    assert (
        result.authority_level_after_check
        is AIRealityCheckAuthorityLevel.REJECTED_BY_REALITY_CHECK
    )
    assert any(
        w.startswith("lookahead_violation:")
        for w in result.warnings
    )


def test_disabled_required_flag_rejects_lookahead() -> None:
    ri = AIRealityCheckInput(
        claim_id="claim-lookahead-2",
        claim_type="OUTCOME",
        claim_text="Some claim.",
        evidence_refs=("symbol:BTCUSDT",),
        market_facts={"breadth_weak": False},
        lookahead_policy={"frozen_evidence_only": False},
    )
    result = AIRealityCheckEngine().check(ri)
    assert result.status is AIRealityCheckStatus.REJECTED_LOOKAHEAD
    assert (
        result.authority_level_after_check
        is AIRealityCheckAuthorityLevel.REJECTED_BY_REALITY_CHECK
    )


def test_lookahead_violation_runs_first_even_with_no_evidence() -> None:
    """The Lookahead Guard runs before every other axis. A
    claim with no evidence_refs AND a lookahead violation
    must be rejected with REJECTED_LOOKAHEAD, not demoted
    with INSUFFICIENT_EVIDENCE."""
    ri = AIRealityCheckInput(
        claim_id="claim-lookahead-3",
        claim_type="OUTCOME",
        claim_text="x",
        evidence_refs=(),
        lookahead_policy={"uses_future_market_data": True},
    )
    result = AIRealityCheckEngine().check(ri)
    assert result.status is AIRealityCheckStatus.REJECTED_LOOKAHEAD


# ---------------------------------------------------------------------------
# 6. unverifiable narrative
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "narrative_text",
    [
        "smart money is definitely entering this market.",
        "Whales are accumulating without a doubt.",
        "Faith is returning across the alt names.",
        "Main force intention is clear here.",
    ],
)
def test_narrative_without_facts_is_rejected(
    narrative_text: str,
) -> None:
    ri = AIRealityCheckInput(
        claim_id="claim-narrative",
        claim_type="NARRATIVE",
        claim_text=narrative_text,
        evidence_refs=("symbol:BTCUSDT",),
        lookahead_policy=_safe_lookahead_policy(),
    )
    result = AIRealityCheckEngine().check(ri)
    assert (
        result.status
        is AIRealityCheckStatus.REJECTED_UNVERIFIABLE_NARRATIVE
    )
    assert (
        result.authority_level_after_check
        is AIRealityCheckAuthorityLevel.REJECTED_BY_REALITY_CHECK
    )
    assert any(
        w.startswith("unverifiable_narrative_fragment:")
        for w in result.warnings
    )


def test_narrative_with_facts_is_warned_not_rejected() -> None:
    """When a narrative phrase is paired with computable
    backing (truth_layer_fields_used, concrete facts), the
    engine surfaces a warning but does NOT reject the claim."""
    ri = AIRealityCheckInput(
        claim_id="claim-narrative-with-facts",
        claim_type="NARRATIVE",
        claim_text=(
            "Smart money entering BTCUSDT regime according "
            "to breadth_score."
        ),
        evidence_refs=("symbol:BTCUSDT",),
        truth_layer_fields_used=("market_facts.breadth_score",),
        market_facts={"breadth_score": 0.85, "breadth_weak": False},
        confidence_raw=0.5,
        lookahead_policy=_safe_lookahead_policy(),
    )
    result = AIRealityCheckEngine().check(ri)
    assert result.status in (
        AIRealityCheckStatus.SUPPORTED,
        AIRealityCheckStatus.PARTIALLY_SUPPORTED,
    )
    assert (
        "narrative_phrase_present_but_facts_supplied"
        in result.warnings
    )


# ---------------------------------------------------------------------------
# 7. confidence calibration (always <= raw)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,build",
    [
        (0.9, _make_supported_input),
        # partial-without-facts
        (
            0.7,
            lambda: AIRealityCheckInput(
                claim_id="c-calib-partial",
                claim_type="REGIME",
                claim_text="claim",
                evidence_refs=("symbol:BTCUSDT",),
                evidence_bundle_facts={"bundle_id": "b"},
                confidence_raw=0.7,
                lookahead_policy=_safe_lookahead_policy(),
            ),
        ),
        # contradicted
        (
            0.95,
            lambda: AIRealityCheckInput(
                claim_id="c-calib-contradicted",
                claim_type="REGIME",
                claim_text="risk appetite expanding rapidly",
                evidence_refs=("symbol:BTCUSDT",),
                market_facts={"breadth_weak": True},
                confidence_raw=0.95,
                lookahead_policy=_safe_lookahead_policy(),
            ),
        ),
    ],
)
def test_confidence_reality_checked_le_confidence_raw(
    raw: float, build
) -> None:
    if build is _make_supported_input:
        ri = _make_supported_input(confidence_raw=raw)
    else:
        ri = build()
    result = AIRealityCheckEngine().check(ri)
    assert result.confidence_raw == raw
    assert result.confidence_reality_checked is not None
    assert result.confidence_reality_checked <= raw


def test_confidence_input_above_one_is_clamped_then_calibrated() -> None:
    """A producer that smuggles confidence > 1.0 must not be
    able to use it as a back-door. The engine clamps the raw
    value to 1.0 before applying the calibration factor."""
    ri = _make_supported_input(confidence_raw=1.5)
    result = AIRealityCheckEngine().check(ri)
    assert result.confidence_reality_checked is not None
    assert result.confidence_reality_checked <= 1.0


def test_confidence_none_stays_none() -> None:
    ri = _make_supported_input(confidence_raw=None)
    result = AIRealityCheckEngine().check(ri)
    assert result.confidence_raw is None
    assert result.confidence_reality_checked is None


# ---------------------------------------------------------------------------
# 8. no trade authority on the result
# ---------------------------------------------------------------------------
def test_authority_level_enum_has_no_trade_authority_member() -> None:
    members = {m.value for m in AIRealityCheckAuthorityLevel}
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


def test_status_enum_has_no_trade_authority_member() -> None:
    members = {m.value for m in AIRealityCheckStatus}
    forbidden_status_names = {
        "BUY",
        "SELL",
        "LONG",
        "SHORT",
        "ENTRY",
        "EXIT",
        "TRADE",
        "EXECUTE",
    }
    assert members.isdisjoint(forbidden_status_names)


def test_supported_result_does_not_grant_trade_authority() -> None:
    """Even a fully SUPPORTED result must NOT carry a
    direction / sizing / order field on its serialised
    payload."""
    result = AIRealityCheckEngine().check(_make_supported_input())
    payload = result.to_dict()
    keys = list(_walk_keys(payload))
    forbidden = {
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
        "target",
        "take_profit",
        "risk_budget",
        "order",
        "order_type",
        "execution_command",
        "trading_approved",
        "live_ready",
        "live_trading_allowed",
    }
    assert forbidden.isdisjoint(keys)


# ---------------------------------------------------------------------------
# 9. forbidden fields absent on serialised result
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
def test_forbidden_field_never_appears_in_serialized_result(
    forbidden_field: str,
) -> None:
    """No forbidden trade-action / runtime-config-patch field
    appears anywhere in the serialised payload."""
    result = AIRealityCheckEngine().check(_make_supported_input())
    payload = result.to_dict()
    keys = list(_walk_keys(payload))
    assert forbidden_field not in keys


def test_forbidden_reality_check_fields_constant_covers_brief_minimum_set() -> None:
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
    assert expected.issubset(FORBIDDEN_REALITY_CHECK_FIELDS)


def test_result_payload_pins_safety_invariants() -> None:
    result = AIRealityCheckEngine().check(_make_supported_input())
    payload = result.to_dict()
    # JSON round-trip without a custom encoder.
    decoded = json.loads(json.dumps(payload))
    assert decoded["schema_version"] == AI_REALITY_CHECK_SCHEMA_VERSION
    assert decoded["source_phase"] == AI_REALITY_CHECK_SOURCE_PHASE
    assert decoded["source_module"] == AI_REALITY_CHECK_SOURCE_MODULE
    assert decoded["auto_tuning_allowed"] is False
    assert decoded["phase_12_forbidden"] is True
    assert decoded["ai_output_is_commentary_only"] is True
    assert decoded["ai_output_can_be_training_label"] is False
    assert decoded["safety_flags"]["mode"] == "paper"
    assert decoded["safety_flags"]["live_trading"] is False
    assert decoded["safety_flags"]["exchange_live_orders"] is False
    assert decoded["safety_flags"]["right_tail"] is False
    assert decoded["safety_flags"]["llm"] is False
    assert decoded["safety_flags"]["telegram_outbound_enabled"] is False
    assert (
        decoded["safety_flags"]["binance_private_api_enabled"] is False
    )


def test_invariants_repinned_even_if_dataclass_field_flipped() -> None:
    """Even if a downstream consumer mutates the (frozen)
    dataclass fields via ``object.__setattr__``, ``to_dict``
    re-pins the safe values."""
    result = AIRealityCheckEngine().check(_make_supported_input())
    object.__setattr__(result, "auto_tuning_allowed", True)
    object.__setattr__(result, "phase_12_forbidden", False)
    object.__setattr__(result, "ai_output_is_commentary_only", False)
    object.__setattr__(result, "ai_output_can_be_training_label", True)
    repinned = result.to_dict()
    assert repinned["auto_tuning_allowed"] is False
    assert repinned["phase_12_forbidden"] is True
    assert repinned["ai_output_is_commentary_only"] is True
    assert repinned["ai_output_can_be_training_label"] is False


# ---------------------------------------------------------------------------
# 10. forbidden imports
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


def test_reality_check_module_does_not_import_forbidden_modules() -> None:
    """Phase AI-3 boundary: the Reality Check module MUST NOT
    import Risk / Execution / Exchange / LLM / Telegram /
    Config modules. Importing any of them would compromise
    either the Responsibility Isolation constraint (AI is
    read-only) or the Stateless Inference constraint (AI
    never reads runtime config)."""
    modules = _collect_imports(SRC_PATH.read_text(encoding="utf-8"))
    bad = [
        m
        for m in modules
        if any(
            m == pre or m.startswith(pre + ".")
            for pre in FORBIDDEN_MODULE_PREFIXES
        )
    ]
    assert not bad, (
        f"reality_check.py imports forbidden modules: {bad!r}; "
        "this violates the Phase AI-3 boundary."
    )


# ---------------------------------------------------------------------------
# 11. no DeepSeek / LLM / network call path
# ---------------------------------------------------------------------------
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


def test_no_deepseek_or_llm_or_http_call_path_in_imports() -> None:
    """The module MUST NOT import any LLM / DeepSeek / HTTP /
    network client. The Reality Check Layer is offline,
    deterministic, and has no transport."""
    modules = _collect_imports(SRC_PATH.read_text(encoding="utf-8"))
    bad = [
        m
        for m in modules
        if any(
            m == pre or m.startswith(pre + ".")
            for pre in FORBIDDEN_NETWORK_MODULES
        )
    ]
    assert not bad, (
        "reality_check.py imports an LLM / DeepSeek / HTTP / "
        f"network module: {bad!r}; this violates the Phase "
        "AI-3 boundary."
    )


def test_module_exposes_no_llm_client_callable() -> None:
    """The Reality Check module MUST NOT expose any callable
    whose name suggests an LLM client (e.g. ``call_deepseek``,
    ``invoke_llm``)."""
    import app.ai.reality_check as mod

    public = [n for n in dir(mod) if not n.startswith("_")]
    bad = [
        name
        for name in public
        if any(
            tok in name.lower()
            for tok in (
                "deepseek",
                "openai",
                "anthropic",
                "llm_call",
                "invoke_llm",
                "http_",
                "_http",
                "outbound",
                "websocket",
            )
        )
    ]
    assert not bad, (
        "reality_check exposes LLM-client-shaped / network-"
        f"shaped callables: {bad!r}; this violates the Phase "
        "AI-3 boundary."
    )


def test_module_source_does_not_reference_deepseek_or_prompts() -> None:
    """A defensive check: the source file MUST NOT contain a
    DeepSeek client / prompt template reference. Reality
    Check is deterministic / statistical, not an LLM."""
    src = SRC_PATH.read_text(encoding="utf-8")
    # Allow brief mentions of "deepseek" only inside docstrings
    # / comments; forbid any function call shape such as
    # ``deepseek.`` / ``DeepSeekClient(`` / ``call_deepseek(``.
    forbidden_substrings = (
        "deepseek.",
        "DeepSeekClient(",
        "call_deepseek(",
        "DeepSeekTransport(",
        "import deepseek",
        "from deepseek",
        "openai.ChatCompletion",
        "openai.Completion",
        "anthropic.Client",
        "import openai",
        "from openai",
        "import anthropic",
        "from anthropic",
        "requests.get(",
        "requests.post(",
        "httpx.get(",
        "httpx.post(",
        "aiohttp.ClientSession(",
        "websocket.create_connection(",
    )
    hits = [s for s in forbidden_substrings if s in src]
    assert not hits, (
        f"reality_check.py contains LLM / network call "
        f"shapes: {hits!r}."
    )


# ---------------------------------------------------------------------------
# 12. deterministic output
# ---------------------------------------------------------------------------
def test_engine_output_is_deterministic_for_identical_inputs() -> None:
    a = AIRealityCheckEngine().check(_make_supported_input())
    b = AIRealityCheckEngine().check(_make_supported_input())
    assert a.to_dict() == b.to_dict()
    assert json.dumps(a.to_dict(), sort_keys=False) == json.dumps(
        b.to_dict(), sort_keys=False
    )


def test_engine_output_is_deterministic_across_status_classes() -> None:
    """Running the same input through the engine twice
    produces identical output for every status class
    (SUPPORTED, PARTIALLY_SUPPORTED, CONTRADICTED,
    INSUFFICIENT_EVIDENCE, REJECTED_LOOKAHEAD,
    REJECTED_UNVERIFIABLE_NARRATIVE)."""
    cases: list[AIRealityCheckInput] = [
        _make_supported_input(),
        AIRealityCheckInput(
            claim_id="c-deterministic-partial",
            claim_type="REGIME",
            claim_text="claim",
            evidence_refs=("symbol:BTCUSDT",),
            evidence_bundle_facts={"bundle_id": "b"},
            confidence_raw=0.4,
            lookahead_policy=_safe_lookahead_policy(),
        ),
        AIRealityCheckInput(
            claim_id="c-deterministic-contradicted",
            claim_type="REGIME",
            claim_text="risk appetite expanding rapidly",
            evidence_refs=("symbol:BTCUSDT",),
            market_facts={"breadth_weak": True},
            confidence_raw=0.5,
            lookahead_policy=_safe_lookahead_policy(),
        ),
        AIRealityCheckInput(
            claim_id="c-deterministic-insufficient",
            claim_type="REGIME",
            claim_text="x",
            evidence_refs=(),
            lookahead_policy=_safe_lookahead_policy(),
        ),
        AIRealityCheckInput(
            claim_id="c-deterministic-lookahead",
            claim_type="OUTCOME",
            claim_text="x",
            evidence_refs=("symbol:BTCUSDT",),
            lookahead_policy={"uses_future_market_data": True},
        ),
        AIRealityCheckInput(
            claim_id="c-deterministic-narrative",
            claim_type="NARRATIVE",
            claim_text="smart money is definitely entering.",
            evidence_refs=("symbol:BTCUSDT",),
            lookahead_policy=_safe_lookahead_policy(),
        ),
    ]
    engine = AIRealityCheckEngine()
    for ri in cases:
        a = engine.check(ri).to_dict()
        b = engine.check(ri).to_dict()
        assert a == b, (
            f"Reality Check output not deterministic for "
            f"claim {ri.claim_id!r}."
        )


def test_convenience_wrapper_matches_engine_output() -> None:
    a = AIRealityCheckEngine().check(_make_supported_input())
    b = reality_check_claim(_make_supported_input())
    assert a.to_dict() == b.to_dict()


# ---------------------------------------------------------------------------
# Defensive companions
# ---------------------------------------------------------------------------
def test_check_many_handles_none_and_empty() -> None:
    engine = AIRealityCheckEngine()
    assert engine.check_many(None) == ()
    assert engine.check_many([]) == ()


def test_check_many_returns_one_result_per_claim() -> None:
    engine = AIRealityCheckEngine()
    inputs = [
        _make_supported_input(claim_id="c-1"),
        _make_supported_input(claim_id="c-2"),
        _make_supported_input(claim_id="c-3"),
    ]
    results = engine.check_many(inputs)
    assert len(results) == 3
    assert [r.claim_id for r in results] == ["c-1", "c-2", "c-3"]


def test_mapping_input_is_coerced() -> None:
    raw = {
        "claim_id": "c-mapping",
        "claim_type": "REGIME",
        "claim_text": "claim",
        "evidence_refs": ["symbol:BTCUSDT"],
        "truth_layer_fields_used": ["market_facts.breadth_score"],
        "confidence_raw": 0.5,
        "market_facts": {"breadth_weak": False, "breadth_score": 0.9},
        "outcome_facts": {"failed_continuation": False},
        "lookahead_policy": _safe_lookahead_policy(),
    }
    result = AIRealityCheckEngine().check(raw)
    assert result.claim_id == "c-mapping"
    assert result.status in (
        AIRealityCheckStatus.SUPPORTED,
        AIRealityCheckStatus.PARTIALLY_SUPPORTED,
    )


def test_non_mapping_non_input_raises_typeerror() -> None:
    with pytest.raises(TypeError):
        AIRealityCheckEngine().check("not a mapping or input")  # type: ignore[arg-type]


def test_lookahead_safe_string_flags_are_honoured() -> None:
    """The engine accepts string ``"true"`` / ``"false"``
    flag values and honours them. A producer cannot use
    string flags as a back-door past the Lookahead Guard."""
    ri = AIRealityCheckInput(
        claim_id="c-lookahead-string",
        claim_type="OUTCOME",
        claim_text="x",
        evidence_refs=("symbol:BTCUSDT",),
        market_facts={"breadth_weak": False},
        lookahead_policy={"frozen_evidence_only": "false"},
    )
    result = AIRealityCheckEngine().check(ri)
    assert result.status is AIRealityCheckStatus.REJECTED_LOOKAHEAD


def test_supporting_evidence_refs_are_subset_of_input_refs() -> None:
    """The engine MUST NOT invent supporting evidence_refs
    that the producer did not cite."""
    ri = _make_supported_input()
    result = AIRealityCheckEngine().check(ri)
    for ref in result.supporting_evidence_refs:
        assert ref in ri.evidence_refs


def test_contradicting_evidence_refs_are_subset_of_input_refs() -> None:
    """Same defensive invariant for contradicting refs."""
    ri = AIRealityCheckInput(
        claim_id="c-contradiction-refs",
        claim_type="REGIME",
        claim_text="risk appetite expanding rapidly",
        evidence_refs=("symbol:BTCUSDT", "report:r1"),
        confidence_raw=0.6,
        market_facts={"breadth_weak": True},
        lookahead_policy=_safe_lookahead_policy(),
    )
    result = AIRealityCheckEngine().check(ri)
    for ref in result.contradicting_evidence_refs:
        assert ref in ri.evidence_refs


def test_authority_after_check_is_closed_enum() -> None:
    """Authority level after Reality Check must be one of the
    closed AIRealityCheckAuthorityLevel members."""
    members = set(AIRealityCheckAuthorityLevel)
    for ri in [
        _make_supported_input(),
        AIRealityCheckInput(
            claim_id="c-empty",
            claim_type="REGIME",
            claim_text="x",
            evidence_refs=(),
            lookahead_policy=_safe_lookahead_policy(),
        ),
    ]:
        result = AIRealityCheckEngine().check(ri)
        assert result.authority_level_after_check in members


def test_status_enum_has_exactly_the_brief_mandated_values() -> None:
    expected = {
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "CONTRADICTED",
        "INSUFFICIENT_EVIDENCE",
        "REJECTED_LOOKAHEAD",
        "REJECTED_UNVERIFIABLE_NARRATIVE",
    }
    actual = {m.value for m in AIRealityCheckStatus}
    assert actual == expected


def test_category_enum_has_exactly_the_brief_mandated_values() -> None:
    expected = {
        "STATISTICAL_VERIFICATION",
        "MICROSTRUCTURE_VALIDATION",
        "CONFIDENCE_CALIBRATION",
        "CONTRADICTION_DETECTION",
        "ADVERSARIAL_EVIDENCE_CHECK",
        "LOOKAHEAD_GUARD",
        "NARRATIVE_POLLUTION_GUARD",
    }
    actual = {m.value for m in AIRealityCheckCategory}
    assert actual == expected


def test_phase_identity_constants_are_phase_ai_3() -> None:
    assert AI_REALITY_CHECK_SOURCE_PHASE == "phase_ai_3"
    assert AI_REALITY_CHECK_SOURCE_MODULE == "ai_reality_check_layer"
    assert AI_REALITY_CHECK_SCHEMA_VERSION == "v0"
