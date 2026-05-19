"""Phase 10D - boundary tests (Issue #10 Part 4).

Pin the cumulative defence-in-depth Phase 10D inherits from
Phase 1-10C plus the Phase 10D-specific invariants:

  - Phase 1 safety lock unchanged.
  - Phase 3 ExchangeClientBase write surfaces still raise
    SafeModeViolation.
  - Phase 9 ExecutionFSMDriver construction-time refusals unchanged.
  - Phase 10A ReplayEngine + 10B ReflectionEngine + 10C
    LLMGuardedInterpreter constructors unchanged.
  - app/telegram/ does NOT subclass ExchangeClientBase.
  - app/telegram/ does NOT define create_order / cancel_order /
    set_leverage / set_margin_mode.
  - app/telegram/ does NOT instantiate any state-mutating component
    (RiskEngine / ExecutionFSMDriver / CapitalFlowEngine / etc.).
  - Public exports complete.
  - 5 new EventType values exist.
"""

from __future__ import annotations

import inspect

import pytest

from app.config.settings import get_settings
from app.core.errors import (
    DataExportError,
    SafeModeViolation,
    TelegramAuthError,
    TelegramTransportError,
)
from app.core.events import EventType
from app.exchanges.base import WRITE_SURFACE_METHODS
from app.exchanges.binance import BinanceClient
from app.exchanges.mock import MockExchangeClient
from app.execution.fsm import ExecutionFSMDriver
from app.llm import LLMGuardedInterpreter
from app.reflection import ReflectionEngine
from app.replay import ReplayEngine
from app.telegram import (
    AVAILABLE_COMMANDS,
    AlertDispatcher,
    AlertSeverity,
    CONFIRM_REQUIRED,
    EXPORT_COMMAND_SET,
    FORMATTERS,
    FakeTelegramClient,
    HIGH_PRIORITY_REJECT_REASONS,
    OutboundSurface,
    TelegramCommandCenter,
    TelegramExportBridge,
    TelegramHttpClient,
    TelegramOutboundClient,
)


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


def test_phase10c_interpreter_constructor_unchanged():
    sig = inspect.signature(LLMGuardedInterpreter.__init__)
    params = list(sig.parameters)
    assert params[0] == "self"
    allowed = {"client", "event_repo", "config", "cache", "llm_enabled"}
    assert set(params[1:]) <= allowed


# ---------------------------------------------------------------------------
# Phase 10D package does not extend the gateway
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


def test_phase10d_package_does_not_subclass_exchange_client_base():
    from app.exchanges.base import ExchangeClientBase

    for module in _modules_for("app.telegram"):
        for name, member in inspect.getmembers(module, inspect.isclass):
            if member is ExchangeClientBase:
                continue
            mod = inspect.getmodule(member)
            if mod is None or not mod.__name__.startswith("app.telegram"):
                continue
            assert not issubclass(member, ExchangeClientBase), (
                f"{module.__name__}.{name} subclasses ExchangeClientBase"
            )


def test_phase10d_package_defines_no_write_surface_method():
    forbidden = {"create_order", "cancel_order", "set_leverage", "set_margin_mode"}
    for module in _modules_for("app.telegram"):
        for name, member in inspect.getmembers(module, inspect.isclass):
            mod = inspect.getmodule(member)
            if mod is None or not mod.__name__.startswith("app.telegram"):
                continue
            for fn_name in forbidden:
                if hasattr(member, fn_name):
                    raise AssertionError(
                        f"{module.__name__}.{name} unexpectedly defines {fn_name}"
                    )


def test_phase10d_does_not_import_state_mutating_components():
    """Telegram package must not import any state-mutating component
    (RiskEngine / ExecutionFSMDriver / Reconciler / CapitalFlowEngine /
    MockExchangeClient / BinanceClient / MarketDataBuffer /
    RegimeEngine / IncidentRepository / PaperLedger /
    LLMGuardedInterpreter)."""
    import ast
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent.parent
    telegram_files = list((ROOT / "app" / "telegram").rglob("*.py"))

    forbidden_classes = {
        "CapitalFlowEngine",
        "ExecutionFSMDriver",
        "Reconciler",
        "MockExchangeClient",
        "BinanceClient",
        "MarketDataBuffer",
        "RiskEngine",
        "RiskRequest",
        "RegimeEngine",
        "IncidentRepository",
        "PaperLedger",
        "LLMGuardedInterpreter",
    }
    for path in telegram_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    assert alias.name not in forbidden_classes, (
                        f"{path.relative_to(ROOT)} imports forbidden state-mutating "
                        f"class {alias.name} from {node.module}"
                    )


def test_phase10d_outbound_client_abc_takes_two_methods_only():
    abstract = TelegramOutboundClient.__abstractmethods__
    assert abstract == {"send_message", "send_document"}


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------
def test_telegram_package_public_exports_complete():
    import app.telegram as t

    expected = {
        # formatters
        "format_system_status",
        "format_market_regime",
        "format_candidate_symbol",
        "format_state_transition",
        "format_order_event",
        "format_risk_rejection",
        "format_profit_lock",
        "format_capital_rebase",
        "format_incident_alert",
        "format_daily_report",
        "FORMATTERS",
        "ALL_TAGS",
        "HIGH_PRIORITY_REJECT_REASONS",
        # outbound
        "TelegramOutboundClient",
        "FakeTelegramClient",
        "TelegramHttpClient",
        "OutboundCall",
        "OutboundSurface",
        # alerts
        "AlertDispatcher",
        "AlertDispatchResult",
        "AlertSeverity",
        # commands
        "TelegramCommandCenter",
        "Command",
        "CommandResult",
        "CommandStatus",
        "AVAILABLE_COMMANDS",
        "EXPORT_COMMAND_SET",
        "CONFIRM_REQUIRED",
        # bridge
        "TelegramExportBridge",
    }
    missing = expected - set(t.__all__)
    assert not missing, f"missing public exports: {missing}"


# ---------------------------------------------------------------------------
# 5 new EventType values
# ---------------------------------------------------------------------------
def test_phase10d_event_types_exist():
    assert EventType.TELEGRAM_COMMAND_REJECTED.value == "TELEGRAM_COMMAND_REJECTED"
    assert EventType.TELEGRAM_MESSAGE_SENT.value == "TELEGRAM_MESSAGE_SENT"
    assert EventType.TELEGRAM_SEND_FAILED.value == "TELEGRAM_SEND_FAILED"
    assert EventType.DATA_EXPORT_GENERATED.value == "DATA_EXPORT_GENERATED"
    assert EventType.DATA_EXPORT_FAILED.value == "DATA_EXPORT_FAILED"


# ---------------------------------------------------------------------------
# Vocabularies pinned
# ---------------------------------------------------------------------------
def test_available_commands_pinned():
    expected = {
        "/status",
        "/positions",
        "/pnl",
        "/risk",
        "/capital",
        "/incidents",
        "/pause",
        "/resume",
        "/kill_all",
        "/rebase",
        "/export_test_data",
        "/export_events",
        "/export_rejections",
        "/export_capital",
        "/export_report",
        "/export_learning_dataset",
    }
    assert set(AVAILABLE_COMMANDS) == expected


def test_export_command_set_pinned():
    assert EXPORT_COMMAND_SET == frozenset(
        {
            "/export_test_data",
            "/export_events",
            "/export_rejections",
            "/export_capital",
            "/export_report",
            "/export_learning_dataset",
        }
    )


def test_confirm_required_includes_resume_and_rebase():
    assert "/resume" in CONFIRM_REQUIRED
    assert "/rebase" in CONFIRM_REQUIRED


def test_high_priority_reject_reasons_pinned():
    assert set(HIGH_PRIORITY_REJECT_REASONS) == {
        "stop_unconfirmed",
        "unknown_position",
        "rebase_in_progress",
        "manipulation_m3",
        "data_degraded",
        "no_exit_channel",
    }


def test_alert_severity_vocabulary_pinned():
    assert {s.value for s in AlertSeverity} == {"info", "warning", "critical"}


def test_outbound_surface_vocabulary_pinned():
    assert {s.value for s in OutboundSurface} == {
        "send_message",
        "send_document",
    }


# ---------------------------------------------------------------------------
# Errors hierarchy
# ---------------------------------------------------------------------------
def test_telegram_transport_error_is_not_a_safety_violation():
    """Phase 10D: a transport drop is recoverable; it must NOT be
    caught as a SafetyViolation (so Phase 1 SafetyViolation handlers
    don't accidentally swallow it)."""
    from app.core.errors import SafetyViolation

    assert not issubclass(TelegramTransportError, SafetyViolation)


def test_telegram_auth_error_IS_a_safety_violation():
    """Operator-allow-list breaches ARE safety violations."""
    from app.core.errors import SafetyViolation

    assert issubclass(TelegramAuthError, SafetyViolation)


def test_data_export_error_is_not_a_safety_violation():
    from app.core.errors import SafetyViolation

    assert not issubclass(DataExportError, SafetyViolation)


# ---------------------------------------------------------------------------
# Phase 9 ExecutionFSMDriver construction guard still in force
# ---------------------------------------------------------------------------
def test_phase9_fsm_driver_constructor_still_refuses_unsafe_settings():
    """Smoke: the Phase 9 construction-time refusal is unchanged."""
    src = inspect.getsource(ExecutionFSMDriver.__init__)
    for needle in (
        "trading_mode",
        "live_trading_enabled",
        "exchange_live_order_enabled",
    ):
        assert needle in src


# ---------------------------------------------------------------------------
# Bridge constructor signature pinned
# ---------------------------------------------------------------------------
def test_export_bridge_constructor_pinned():
    """The TelegramExportBridge is a dataclass with exactly the
    Phase 10D-mandated fields."""
    import dataclasses

    fields = {f.name for f in dataclasses.fields(TelegramExportBridge)}
    expected = {"service", "dispatcher", "event_repo", "refuse_when_not_paper"}
    # Allow extra fields like SOURCE_MODULE which is class-level only.
    assert expected <= fields


# ---------------------------------------------------------------------------
# Formatter registry contract
# ---------------------------------------------------------------------------
def test_formatter_registry_count_is_ten():
    assert len(FORMATTERS) == 10


def test_dispatcher_construct_with_default_paper_flags():
    """The dispatcher's defaults must ship in safe paper-mode form
    (outbound_enabled=False)."""
    sig = inspect.signature(AlertDispatcher.__init__)
    p = sig.parameters
    assert p["outbound_enabled"].default is False
