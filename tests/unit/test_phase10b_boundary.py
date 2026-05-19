"""Phase 10B - boundary tests (Issue #10 Part 2).

Pin the cumulative defence-in-depth Phase 10B inherits from
Phase 1-10A plus the new Phase 10B invariants:

  - Phase 1 safety lock unchanged.
  - Phase 3 ExchangeClientBase write surfaces still raise
    SafeModeViolation.
  - Phase 9 ExecutionFSMDriver construction-time refusals
    unchanged.
  - Phase 10A ReplayEngine constructor unchanged.
  - Phase 10B package does NOT subclass ExchangeClientBase.
  - Phase 10B package does NOT define ``create_order`` /
    ``cancel_order`` / ``set_leverage`` / ``set_margin_mode``.
  - Phase 10B package does NOT instantiate any state-mutating
    component (CapitalFlowEngine / RiskEngine /
    ExecutionFSMDriver / Reconciler / IncidentRepository /
    MarketDataBuffer / MockExchangeClient / BinanceClient /
    TelegramCommandCenter / RegimeEngine).
  - Phase 10B public exports complete.
  - The MistakeTag vocabulary contains every Issue-required tag.
  - ReflectionResult schema pinned (field set + JSON-safe).
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from app.config.settings import get_settings
from app.core.errors import SafeModeViolation
from app.exchanges.base import WRITE_SURFACE_METHODS
from app.exchanges.binance import BinanceClient
from app.exchanges.mock import MockExchangeClient
from app.reflection import (
    DIAGNOSTIC_MISTAKE_TAGS,
    ISSUE_REQUIRED_MISTAKE_TAGS,
    MetricResult,
    MistakeTag,
    QualityScore,
    ReflectionConfig,
    ReflectionEngine,
    ReflectionInput,
    ReflectionResult,
    TradeOutcome,
    UnknownReason,
    compute_mae,
    compute_mfe,
    compute_tail_contribution,
    realized_pnl_for,
)
from app.replay import ReplayEngine


# ---------------------------------------------------------------------------
# Phase 1 + Phase 3 + Phase 9 invariants
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
# Phase 10A invariant: ReplayEngine constructor unchanged
# ---------------------------------------------------------------------------
def test_phase10a_replay_engine_constructor_unchanged():
    sig = inspect.signature(ReplayEngine.__init__)
    params = list(sig.parameters)
    assert params[0] == "self"
    assert "event_repo" in params
    assert len(params) == 2


# ---------------------------------------------------------------------------
# Phase 10B package does not extend the gateway
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


def test_phase10b_package_does_not_subclass_exchange_client_base():
    from app.exchanges.base import ExchangeClientBase

    for module in _modules_for("app.reflection"):
        for name, member in inspect.getmembers(module, inspect.isclass):
            if member is ExchangeClientBase:
                continue
            mod = inspect.getmodule(member)
            if mod is None or not mod.__name__.startswith("app.reflection"):
                continue
            assert not issubclass(member, ExchangeClientBase), (
                f"{module.__name__}.{name} subclasses ExchangeClientBase"
            )


def test_phase10b_package_defines_no_write_surface_method():
    forbidden = {"create_order", "cancel_order", "set_leverage", "set_margin_mode"}
    for module in _modules_for("app.reflection"):
        for name, member in inspect.getmembers(module, inspect.isclass):
            mod = inspect.getmodule(member)
            if mod is None or not mod.__name__.startswith("app.reflection"):
                continue
            for fn_name in forbidden:
                if hasattr(member, fn_name):
                    raise AssertionError(
                        f"{module.__name__}.{name} unexpectedly defines {fn_name}"
                    )


# ---------------------------------------------------------------------------
# Phase 10B package does not import state-mutating components
# ---------------------------------------------------------------------------
def test_phase10b_does_not_import_state_mutating_components():
    """Reflection must not import any state-mutating component.

    Walk every ``import`` statement under ``app/reflection/`` and
    confirm none of them pull in the state-mutating components.
    Reflection MAY import :class:`ReplayEngine` from ``app.replay``
    (Replay is itself read-only) and the read-only Phase 9
    :class:`PaperLifecycleSummary` value object, but NOT the writer
    surfaces.
    """
    import ast
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent.parent
    reflection_files = list((ROOT / "app" / "reflection").rglob("*.py"))

    forbidden_classes = {
        "CapitalFlowEngine",
        "ExecutionFSMDriver",
        "Reconciler",
        "MockExchangeClient",
        "BinanceClient",
        "MarketDataBuffer",
        "TelegramCommandCenter",
        "RiskEngine",
        "RegimeEngine",
        "IncidentRepository",
    }
    for path in reflection_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.name not in forbidden_classes, (
                        f"{path.relative_to(ROOT)} imports forbidden state-mutating "
                        f"class {alias.name} from {node.module}"
                    )


def test_phase10b_reflection_engine_constructor_takes_only_read_only_args():
    """Constructor: ``(self, *, replay=None, event_repo=None, config=None)``.

    No exchange client, no risk engine, no FSM driver, no buffer.
    """
    sig = inspect.signature(ReflectionEngine.__init__)
    params = list(sig.parameters)
    assert params[0] == "self"
    # Allowed read-only knobs only.
    assert set(params[1:]) <= {"replay", "event_repo", "config"}


# ---------------------------------------------------------------------------
# Public exports complete
# ---------------------------------------------------------------------------
def test_reflection_package_public_exports():
    import app.reflection as r

    expected = {
        "ReflectionEngine",
        "ReflectionConfig",
        "ReflectionInput",
        "ReflectionResult",
        "QualityScore",
        "TradeOutcome",
        "UnknownReason",
        "MistakeTag",
        "ISSUE_REQUIRED_MISTAKE_TAGS",
        "DIAGNOSTIC_MISTAKE_TAGS",
        "MetricResult",
        "compute_mfe",
        "compute_mae",
        "compute_tail_contribution",
        "realized_pnl_for",
    }
    missing = expected - set(r.__all__)
    assert not missing, f"missing public exports: {missing}"


# ---------------------------------------------------------------------------
# MistakeTag vocabulary pinned
# ---------------------------------------------------------------------------
def test_mistake_tag_required_set_pinned():
    assert {t.value for t in ISSUE_REQUIRED_MISTAKE_TAGS} == {
        "late_entry",
        "early_exit",
        "weak_volume",
        "fake_breakout",
        "high_trap_score",
        "ignored_no_trade_gate",
        "slippage_error",
        "execution_delay",
        "stop_not_confirmed",
        "tail_saved_trade",
        "tail_failed",
        "right_tail_success",
    }


def test_mistake_tag_diagnostic_set_pinned():
    assert {t.value for t in DIAGNOSTIC_MISTAKE_TAGS} == {
        "insufficient_data",
        "no_lifecycle_observed",
        "incident_during_lifecycle",
    }


def test_mistake_tag_required_and_diagnostic_disjoint():
    assert ISSUE_REQUIRED_MISTAKE_TAGS.isdisjoint(DIAGNOSTIC_MISTAKE_TAGS)


def test_mistake_tag_total_size_at_least_15():
    assert len(set(MistakeTag)) >= 15


# ---------------------------------------------------------------------------
# ReflectionResult schema pinned
# ---------------------------------------------------------------------------
def test_reflection_result_field_set_pinned():
    expected = {
        "opportunity_id",
        "client_order_id",
        "symbol",
        "setup",
        "result",
        "mistake_tags",
        "mfe",
        "mae",
        "tail_contribution",
        "entry_quality",
        "exit_quality",
        "risk_process_quality",
        "execution_quality",
        "data_quality_notes",
        "source_event_ids",
        "learning_ready",
        "generated_at",
    }
    assert {f.name for f in dataclasses.fields(ReflectionResult)} == expected


def test_reflection_value_objects_have_to_payload():
    """The value objects produced by the engine are JSON-safe."""
    assert hasattr(ReflectionResult, "to_payload")
    # Metric helper output is also JSON-friendly via its own field set.
    metric_field_names = {f.name for f in dataclasses.fields(MetricResult)}
    assert metric_field_names == {"value", "unknown_reasons"}


# ---------------------------------------------------------------------------
# Quality / outcome / unknown-reason vocabularies pinned
# ---------------------------------------------------------------------------
def test_quality_score_vocabulary_pinned():
    assert {s.value for s in QualityScore} == {
        "high",
        "medium",
        "low",
        "unknown",
    }


def test_trade_outcome_vocabulary_pinned():
    assert {t.value for t in TradeOutcome} == {
        "win",
        "loss",
        "breakeven",
        "protected",
        "open",
        "unknown",
    }


def test_unknown_reason_vocabulary_pinned():
    assert {r.value for r in UnknownReason} == {
        "insufficient_price_path",
        "no_fill_recorded",
        "no_virtual_trade_plan",
        "no_signal_snapshot",
        "no_right_tail_amplify_lifecycle",
        "no_opportunity_id",
        "no_lifecycle_events",
        "no_realised_pnl",
        "no_risk_decision_trail",
        "no_state_transition_trail",
        "no_config_versions",
    }


# ---------------------------------------------------------------------------
# ReflectionConfig defaults pinned
# ---------------------------------------------------------------------------
def test_reflection_config_default_values_pinned():
    config = ReflectionConfig()
    assert config.late_entry_pct == 0.005
    assert config.slippage_overrun_pct == 0.001
    assert config.execution_delay_ms == 1500
    assert config.weak_volume_anomaly_threshold == 50.0
    assert config.trap_score_threshold == 0.6


# ---------------------------------------------------------------------------
# Reflection engine reads-only against the events.db (smoke)
# ---------------------------------------------------------------------------
def test_reflection_engine_does_not_call_append_event(events_repo):
    """Drive a no-op replay+reflect against an empty repo and confirm
    the count of events is unchanged."""
    pre = events_repo.count_events()
    engine = ReflectionEngine(event_repo=events_repo)
    # No events -> reflect_paper_trade raises ValueError. We exercise
    # the metric helpers + the dataclass instead.
    helpers = (compute_mfe, compute_mae, realized_pnl_for)
    for fn in helpers:
        fn([])
    compute_tail_contribution(
        events=[],
        state_transitions=(),
        realized_pnl=None,
        virtual_trade_plan=None,
    )
    # Construct an explicit ReflectionInput and confirm reflect returns
    # without adding events.
    from app.execution.lifecycle import PaperLifecycleSummary
    from app.replay import PaperTradeReplay, ReplayDiffReport

    summary = PaperLifecycleSummary(
        client_order_id=None,
        opportunity_id=None,
        symbol=None,
        side=None,
        qty=None,
        entry_state=None,
        exit_state=None,
        stop_confirmed=False,
        partial_fills=0,
        final_status="rejected",
        learning_ready_present=False,
        event_chain=(),
    )
    paper_trade = PaperTradeReplay(
        client_order_id=None,
        opportunity_id=None,
        summary=summary,
        events=(),
        diff_against_canonical=ReplayDiffReport(
            expected_chain=(),
            observed_chain=(),
            entries=(),
        ),
        learning_ready_event_count=0,
    )
    engine.reflect(ReflectionInput(paper_trade=paper_trade))
    assert events_repo.count_events() == pre


# ---------------------------------------------------------------------------
# ReflectionInput is the public input vehicle
# ---------------------------------------------------------------------------
def test_reflection_input_field_set():
    fields = {f.name for f in dataclasses.fields(ReflectionInput)}
    assert fields == {
        "paper_trade",
        "risk_decisions",
        "state_transitions",
        "incidents",
        "learning_ready",
    }
