"""Phase 10C - boundary tests (Issue #10 Part 3).

Pin the cumulative defence-in-depth Phase 10C inherits from
Phase 1-10B plus the Phase 10C invariants:

  - Phase 1 safety lock unchanged.
  - Phase 3 ExchangeClientBase write surfaces still raise
    SafeModeViolation.
  - Phase 9 ExecutionFSMDriver construction-time refusals
    unchanged.
  - Phase 10A ReplayEngine constructor unchanged.
  - Phase 10B ReflectionEngine constructor unchanged.
  - Phase 10C package does NOT subclass ExchangeClientBase.
  - Phase 10C package does NOT define create_order / cancel_order /
    set_leverage / set_margin_mode.
  - Phase 10C package does NOT instantiate any state-mutating
    component.
  - Phase 10C public exports complete.
  - LLM_OUTPUT_WHITELIST + LLM_FORBIDDEN_FIELDS pinned.
  - LLMInterpretationResult schema pinned.
  - Three new EventType values exist.
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from app.config.settings import get_settings
from app.core.errors import SafeModeViolation
from app.core.events import EventType
from app.exchanges.base import WRITE_SURFACE_METHODS
from app.exchanges.binance import BinanceClient
from app.exchanges.mock import MockExchangeClient
from app.execution.fsm import ExecutionFSMDriver
from app.llm import (
    DeepSeekClient,
    FakeLLMClient,
    HypeStage,
    LLMCache,
    LLMClientBase,
    LLMDegradedReason,
    LLMGuardedInterpreter,
    LLMInterpretationInput,
    LLMInterpretationResult,
    LLMInterpreterConfig,
    LLMRiskTag,
    LLMTokenBucket,
    LLM_FORBIDDEN_FIELDS,
    LLM_OUTPUT_SCHEMA,
    LLM_OUTPUT_WHITELIST,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    SYSTEM_PROMPT_TEMPLATE,
    SchemaValidationError,
    TokenThrottleTier,
    TransportError,
    LLMTimeoutError,
    SchemaRejection,
    build_user_prompt,
    detect_prompt_injection,
    enforce_field_whitelist,
    sanitize_input_text,
    strip_forbidden_fields,
    validate_llm_output,
)
from app.reflection import ReflectionEngine
from app.replay import ReplayEngine


# ---------------------------------------------------------------------------
# Phase 1 + Phase 3 invariants
# ---------------------------------------------------------------------------
def test_phase1_safety_lock_remains_in_force():
    settings = get_settings()
    assert settings.trading_mode == "paper"
    assert settings.live_trading_enabled is False
    assert settings.right_tail_enabled is False
    assert settings.llm_enabled is False
    assert settings.exchange_live_order_enabled is False


@pytest.mark.parametrize(
    "client_factory",
    [
        lambda: MockExchangeClient(autostart=False),
        lambda: BinanceClient(),
    ],
    ids=["mock", "binance_skeleton"],
)
def test_phase3_write_surfaces_still_refuse(client_factory):
    client = client_factory()
    for fn_name in WRITE_SURFACE_METHODS:
        with pytest.raises(SafeModeViolation):
            getattr(client, fn_name)()


# ---------------------------------------------------------------------------
# Earlier-phase engine constructors unchanged
# ---------------------------------------------------------------------------
def test_phase10a_replay_engine_constructor_unchanged():
    sig = inspect.signature(ReplayEngine.__init__)
    params = list(sig.parameters)
    assert params[0] == "self"
    assert "event_repo" in params
    assert len(params) == 2


def test_phase10b_reflection_engine_constructor_unchanged():
    sig = inspect.signature(ReflectionEngine.__init__)
    params = list(sig.parameters)
    assert params[0] == "self"
    assert set(params[1:]) <= {"replay", "event_repo", "config"}


# ---------------------------------------------------------------------------
# Phase 10C package does not extend the gateway
# ---------------------------------------------------------------------------
def _modules_for(*pkgs: str):
    import importlib
    import pkgutil

    out = []
    for pkg in pkgs:
        mod = importlib.import_module(pkg)
        out.append(mod)
        if hasattr(mod, "__path__"):
            for info in pkgutil.iter_modules(mod.__path__):
                out.append(importlib.import_module(f"{pkg}.{info.name}"))
    return out


def test_phase10c_package_does_not_subclass_exchange_client_base():
    from app.exchanges.base import ExchangeClientBase

    for module in _modules_for("app.llm"):
        for name, member in inspect.getmembers(module, inspect.isclass):
            if member is ExchangeClientBase:
                continue
            mod = inspect.getmodule(member)
            if mod is None or not mod.__name__.startswith("app.llm"):
                continue
            assert not issubclass(member, ExchangeClientBase), (
                f"{module.__name__}.{name} subclasses ExchangeClientBase"
            )


def test_phase10c_package_defines_no_write_surface_method():
    forbidden = {"create_order", "cancel_order", "set_leverage", "set_margin_mode"}
    for module in _modules_for("app.llm"):
        for name, member in inspect.getmembers(module, inspect.isclass):
            mod = inspect.getmodule(member)
            if mod is None or not mod.__name__.startswith("app.llm"):
                continue
            for fn_name in forbidden:
                if hasattr(member, fn_name):
                    raise AssertionError(
                        f"{module.__name__}.{name} unexpectedly defines {fn_name}"
                    )


def test_phase10c_does_not_import_state_mutating_components():
    """LLM package must not import any state-mutating component.

    Walk every ``import`` statement under ``app/llm/`` and confirm
    none of them pull in the state-mutating components.
    """
    import ast
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent.parent
    llm_files = list((ROOT / "app" / "llm").rglob("*.py"))

    forbidden_classes = {
        "CapitalFlowEngine",
        "ExecutionFSMDriver",
        "Reconciler",
        "MockExchangeClient",
        "BinanceClient",
        "MarketDataBuffer",
        "TelegramCommandCenter",
        "RiskEngine",
        "RiskRequest",
        "RegimeEngine",
        "IncidentRepository",
        "PaperLedger",
    }
    for path in llm_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.name not in forbidden_classes, (
                        f"{path.relative_to(ROOT)} imports forbidden state-mutating "
                        f"class {alias.name} from {node.module}"
                    )


def test_phase10c_interpreter_constructor_takes_only_kwargs():
    sig = inspect.signature(LLMGuardedInterpreter.__init__)
    params = list(sig.parameters)
    assert params[0] == "self"
    allowed = {"client", "event_repo", "config", "cache", "llm_enabled"}
    assert set(params[1:]) <= allowed


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------
def test_llm_package_public_exports():
    import app.llm as l

    expected = {
        "LLMGuardedInterpreter",
        "LLMInterpreterConfig",
        "LLMTokenBucket",
        "LLMInterpretationInput",
        "LLMInterpretationResult",
        "HypeStage",
        "EvidenceQuality",
        "CatalystStrength",
        "LLMRiskTag",
        "LLMDegradedReason",
        "TokenThrottleTier",
        "LLMClientBase",
        "FakeLLMClient",
        "DeepSeekClient",
        "TransportError",
        "LLMTimeoutError",
        "SchemaRejection",
        "LLMCache",
        "LLMCacheEntry",
        "LLM_OUTPUT_WHITELIST",
        "LLM_FORBIDDEN_FIELDS",
        "LLM_OUTPUT_SCHEMA",
        "PROMPT_VERSION",
        "SCHEMA_VERSION",
        "SYSTEM_PROMPT_TEMPLATE",
        "build_user_prompt",
        "sanitize_input_text",
        "detect_prompt_injection",
        "enforce_field_whitelist",
        "strip_forbidden_fields",
        "validate_llm_output",
        "SchemaValidationError",
    }
    missing = expected - set(l.__all__)
    assert not missing, f"missing public exports: {missing}"


# ---------------------------------------------------------------------------
# Whitelist / forbidden vocabularies pinned
# ---------------------------------------------------------------------------
def test_llm_output_whitelist_pinned():
    assert LLM_OUTPUT_WHITELIST == frozenset(
        {
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
    )


def test_llm_forbidden_fields_pinned():
    assert LLM_FORBIDDEN_FIELDS == frozenset(
        {
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
    )


def test_whitelist_and_forbidden_are_disjoint():
    assert LLM_OUTPUT_WHITELIST.isdisjoint(LLM_FORBIDDEN_FIELDS)


# ---------------------------------------------------------------------------
# Schema / prompt versions pinned
# ---------------------------------------------------------------------------
def test_prompt_and_schema_versions_pinned():
    assert PROMPT_VERSION == "v1.4.0a10c"
    assert SCHEMA_VERSION == "v1.4.0a10c"
    assert LLM_OUTPUT_SCHEMA["version"] == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Three new event types exist
# ---------------------------------------------------------------------------
def test_phase10c_event_types_exist():
    assert EventType.LLM_INTERPRETED.value == "LLM_INTERPRETED"
    assert EventType.LLM_DEGRADED.value == "LLM_DEGRADED"
    assert EventType.LLM_SCHEMA_REJECTED.value == "LLM_SCHEMA_REJECTED"


# ---------------------------------------------------------------------------
# Result schema pinned
# ---------------------------------------------------------------------------
def test_result_schema_pinned():
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


# ---------------------------------------------------------------------------
# Result NEVER carries a forbidden trade-action field
# ---------------------------------------------------------------------------
def test_result_payload_never_contains_forbidden_fields():
    result = LLMInterpretationResult(
        narrative="hi",
        catalyst=__import__("app.llm.models", fromlist=["CatalystStrength"]).CatalystStrength.UNKNOWN,
        evidence_quality=__import__("app.llm.models", fromlist=["EvidenceQuality"]).EvidenceQuality.UNKNOWN,
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
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        cache_hit=False,
    )
    payload = result.to_payload()
    assert LLM_FORBIDDEN_FIELDS.isdisjoint(set(payload))


# ---------------------------------------------------------------------------
# DeepSeek skeleton remains a refusal-only adapter in Phase 10C
# ---------------------------------------------------------------------------
def test_deepseek_skeleton_refuses_in_phase10c():
    client = DeepSeekClient(llm_enabled=True, credentials_provided=True)
    with pytest.raises(TransportError):
        client.generate(messages=[], timeout_ms=10)


# ---------------------------------------------------------------------------
# Phase 9 ExecutionFSMDriver construction guard still in force
# ---------------------------------------------------------------------------
def test_phase9_fsm_driver_constructor_still_refuses_unsafe_settings():
    """Smoke: the Phase 9 construction-time refusal is unchanged.

    We cannot easily construct the driver with bad flags here (the
    settings come from get_settings() which applies the Phase 1
    lock), but we assert that the refusal helper exists and reads
    the flags.
    """
    src = inspect.getsource(ExecutionFSMDriver.__init__)
    for needle in (
        "trading_mode",
        "live_trading_enabled",
        "exchange_live_order_enabled",
    ):
        assert needle in src
