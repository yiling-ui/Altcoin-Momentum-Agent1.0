"""Phase 10A - boundary tests (Issue #10 Part 1).

Pin the cumulative defence-in-depth Phase 10A inherits from
Phase 1-9 plus the new Phase 10A invariants:

  - Phase 1 safety lock unchanged.
  - Phase 3 ExchangeClientBase write surfaces still raise
    SafeModeViolation.
  - Phase 9 ExecutionFSMDriver construction-time refusals
    unchanged.
  - Phase 10A package does NOT subclass ExchangeClientBase.
  - Phase 10A package does NOT define ``create_order`` / ``cancel_order``
    / ``set_leverage`` / ``set_margin_mode``.
  - Phase 10A package does NOT instantiate any of the state-mutating
    components (CapitalFlowEngine / RiskEngine /
    ExecutionFSMDriver / Reconciler / IncidentRepository /
    MarketDataBuffer / MockExchangeClient / BinanceClient /
    TelegramCommandCenter).
  - Phase 10A package's ReplayEngine constructor takes only
    ``event_repo``.
  - Phase 10A public exports complete.
  - Phase 10A is NOT a writer of events.db: ``replay`` never
    appends an event during a replay run.
"""

from __future__ import annotations

import inspect

import pytest

from app.config.settings import get_settings
from app.core.errors import SafeModeViolation
from app.core.events import EventType
from app.exchanges.base import WRITE_SURFACE_METHODS
from app.exchanges.binance import BinanceClient
from app.exchanges.mock import MockExchangeClient
from app.replay import (
    CANONICAL_CLOSED_PAPER_TRADE_CHAIN,
    CANONICAL_OPEN_PAPER_TRADE_CHAIN,
    CapitalRebaseReplay,
    DiffEntry,
    DiffKind,
    IncidentReplay,
    LearningReadyReplay,
    P0LatchedPauseInvariantReport,
    PaperTradeReplay,
    ReplayDiffReport,
    ReplayEngine,
    RiskDecisionReplay,
    StateTransitionReplay,
    TelegramCommandReplay,
    compare_event_chains,
)


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
# Phase 10A package does not extend the gateway
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


def test_phase10a_package_does_not_subclass_exchange_client_base():
    from app.exchanges.base import ExchangeClientBase

    for module in _modules_for("app.replay"):
        for name, member in inspect.getmembers(module, inspect.isclass):
            if member is ExchangeClientBase:
                continue
            mod = inspect.getmodule(member)
            if mod is None or not mod.__name__.startswith("app.replay"):
                continue
            assert not issubclass(member, ExchangeClientBase), (
                f"{module.__name__}.{name} subclasses ExchangeClientBase"
            )


def test_phase10a_package_defines_no_write_surface_method():
    forbidden = {"create_order", "cancel_order", "set_leverage", "set_margin_mode"}
    for module in _modules_for("app.replay"):
        for name, member in inspect.getmembers(module, inspect.isclass):
            mod = inspect.getmodule(member)
            if mod is None or not mod.__name__.startswith("app.replay"):
                continue
            for fn_name in forbidden:
                if hasattr(member, fn_name):
                    raise AssertionError(
                        f"{module.__name__}.{name} unexpectedly defines {fn_name}"
                    )


# ---------------------------------------------------------------------------
# Phase 10A package does not instantiate state-mutating components
# ---------------------------------------------------------------------------
def test_phase10a_does_not_import_state_mutating_components():
    """Replay must not import any state-mutating component into its namespace.

    AST scan: walk every ``import`` statement under ``app/replay/`` and
    confirm none of them pull in :class:`CapitalFlowEngine`,
    :class:`ExecutionFSMDriver`, :class:`Reconciler`,
    :class:`MockExchangeClient`, :class:`BinanceClient`,
    :class:`MarketDataBuffer`, :class:`TelegramCommandCenter`,
    or :class:`IncidentRepository` (the writer; the read-only
    ``Incident`` value object is allowed via app.incidents.models).
    """
    import ast
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent.parent
    replay_files = list((ROOT / "app" / "replay").rglob("*.py"))

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
    # Replay MAY reuse the existing :class:`PaperLifecycleSummary` /
    # :func:`reconstruct_paper_lifecycle` helper which lives in
    # ``app.execution.lifecycle``. Importing those by name does NOT
    # bring any state-mutating component into the namespace.
    for path in replay_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.name not in forbidden_classes, (
                        f"{path.relative_to(ROOT)} imports forbidden state-mutating "
                        f"class {alias.name} from {node.module}"
                    )


def test_phase10a_replay_engine_constructor_only_takes_event_repo():
    sig = inspect.signature(ReplayEngine.__init__)
    params = list(sig.parameters)
    # Constructor: (self, *, event_repo).
    assert params[0] == "self"
    assert "event_repo" in params
    assert len(params) == 2


# ---------------------------------------------------------------------------
# Public exports complete
# ---------------------------------------------------------------------------
def test_replay_package_public_exports():
    import app.replay as r

    expected = {
        "ReplayEngine",
        "PaperTradeReplay",
        "CapitalRebaseReplay",
        "RiskDecisionReplay",
        "IncidentReplay",
        "StateTransitionReplay",
        "TelegramCommandReplay",
        "LearningReadyReplay",
        "P0LatchedPauseInvariantReport",
        "DiffEntry",
        "DiffKind",
        "ReplayDiffReport",
        "compare_event_chains",
        "load_all_events",
        "stream_events",
        "load_events_for_order",
        "load_events_for_symbol",
        "load_events_for_position",
        "load_events_for_opportunity",
        "load_capital_flow_events",
        "load_risk_decision_events",
        "load_incident_lifecycle_events",
        "load_state_transition_events",
        "load_telegram_command_events",
        "load_reconciliation_events",
        "has_learning_ready",
        "extract_learning_ready",
        "opportunity_id_for",
        "pair_reconciliation_passes",
        "CANONICAL_CLOSED_PAPER_TRADE_CHAIN",
        "CANONICAL_OPEN_PAPER_TRADE_CHAIN",
        "PAPER_LIFECYCLE_EVENT_TYPES",
        "CAPITAL_FLOW_EVENT_TYPES",
        "INCIDENT_LIFECYCLE_EVENT_TYPES",
        "RECONCILIATION_EVENT_TYPES",
        "RISK_DECISION_EVENT_TYPES",
    }
    missing = expected - set(r.__all__)
    assert not missing, f"missing public exports: {missing}"


def test_canonical_closed_paper_trade_chain_pinned():
    """Pin the canonical chain so future PRs cannot drift it silently."""
    assert CANONICAL_CLOSED_PAPER_TRADE_CHAIN == (
        EventType.ORDER_SENT.value,
        EventType.ORDER_ACK.value,
        EventType.ORDER_FILLED.value,
        EventType.STOP_SENT.value,
        EventType.STOP_CONFIRMED.value,
        EventType.POSITION_OPENED.value,
        EventType.EXIT_TRIGGERED.value,
        EventType.POSITION_CLOSED.value,
    )


def test_canonical_open_paper_trade_chain_pinned():
    assert CANONICAL_OPEN_PAPER_TRADE_CHAIN == (
        EventType.ORDER_SENT.value,
        EventType.ORDER_ACK.value,
        EventType.ORDER_FILLED.value,
        EventType.STOP_SENT.value,
        EventType.STOP_CONFIRMED.value,
        EventType.POSITION_OPENED.value,
    )


# ---------------------------------------------------------------------------
# Replay value objects are JSON-safe
# ---------------------------------------------------------------------------
def test_diff_kind_vocabulary_pinned():
    assert {k.value for k in DiffKind} == {
        "match",
        "missing",
        "extra",
        "reordered",
    }


def test_replay_value_objects_have_to_payload():
    """Every Replay value object exposes a JSON-safe ``to_payload``."""
    for cls in (
        PaperTradeReplay,
        CapitalRebaseReplay,
        RiskDecisionReplay,
        IncidentReplay,
        StateTransitionReplay,
        TelegramCommandReplay,
        LearningReadyReplay,
        P0LatchedPauseInvariantReport,
        ReplayDiffReport,
        DiffEntry,
    ):
        assert hasattr(cls, "to_payload"), (
            f"{cls.__name__} missing to_payload helper"
        )


# ---------------------------------------------------------------------------
# Replay is read-only against events.db
# ---------------------------------------------------------------------------
def test_replay_engine_does_not_call_append_event(events_repo):
    """Drive several replays against an empty/empty repo and confirm
    the count of events is unchanged."""
    pre = events_repo.count_events()
    engine = ReplayEngine(event_repo=events_repo)
    # No events to replay -> these still must not write.
    engine.verify_p0_latched_pause_invariant()
    engine.replay_state_transitions()
    engine.replay_telegram_commands()
    engine.replay_p0_incidents()
    engine.replay_risk_rejections()
    assert events_repo.count_events() == pre


def test_compare_event_chains_returns_replay_diff_report():
    """The free function returns the same value-object the engine helper does."""
    diff = compare_event_chains(["A"], ["A"])
    assert isinstance(diff, ReplayDiffReport)
    assert diff.matched is True


def test_replay_engine_static_diff_helper_matches_free_function():
    a = compare_event_chains(["A", "B"], ["A", "C"])
    b = ReplayEngine.diff_event_chains(["A", "B"], ["A", "C"])
    assert a.to_payload() == b.to_payload()
