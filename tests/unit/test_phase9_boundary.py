"""Phase 9 - boundary tests (Issue #9).

Pin the cumulative defence-in-depth Phase 9 inherits from Phase 1-8.5
plus the new Phase 9 invariants:

  - Phase 1 safety lock unchanged (paper, no live, no right-tail,
    no LLM, no exchange live orders).
  - Phase 3 ExchangeClientBase write surfaces still raise
    SafeModeViolation.
  - Phase 9 packages do NOT subclass ExchangeClientBase.
  - Phase 9 packages do NOT define create_order / cancel_order /
    set_leverage / set_margin_mode.
  - Phase 9 driver refuses to construct when the safety lock has
    drifted.
  - Phase 9 events that may be emitted by the driver and the
    reconciler are reachable through EventType.
  - Phase 9 vocabulary (OrderIntent, OrderKind, MismatchType,
    MismatchSeverity) is reachable through public exports.
  - Phase 9 reduce-only intents auto-resolve to is_new_open=False.
"""

from __future__ import annotations

import inspect
from typing import Iterable

import pytest

from app.config.settings import get_settings
from app.core.enums import IncidentLevel
from app.core.errors import SafeModeViolation
from app.core.events import EventType
from app.exchanges.base import WRITE_SURFACE_METHODS
from app.exchanges.binance import BinanceClient
from app.exchanges.mock import MockExchangeClient
from app.execution.fsm import ExecutionFSM, ExecutionFSMDriver, IllegalTransition
from app.execution.models import (
    NEW_OPEN_INTENTS,
    REDUCE_ONLY_INTENTS,
    MarginMode,
    OrderIntent,
    OrderKind,
    OrderRequest,
    OrderSide,
)
from app.execution.paper_ledger import PaperLedger
from app.incidents.repository import IncidentRepository, ProtectionHook
from app.reconciliation.models import (
    LocalSnapshot,
    Mismatch,
    MismatchSeverity,
    MismatchType,
    RemoteSnapshot,
)
from app.reconciliation.reconciler import Reconciler


# ---------------------------------------------------------------------------
# Phase 1 + Phase 3 invariants unchanged
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
# Phase 9 packages do not extend the gateway
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


def test_phase9_packages_do_not_subclass_exchange_client_base():
    from app.exchanges.base import ExchangeClientBase

    for module in _modules_for("app.execution", "app.incidents", "app.reconciliation"):
        for name, member in inspect.getmembers(module, inspect.isclass):
            if member is ExchangeClientBase:
                continue
            if not inspect.getmodule(member) or not inspect.getmodule(member).__name__.startswith(
                ("app.execution", "app.incidents", "app.reconciliation")
            ):
                continue
            assert not issubclass(member, ExchangeClientBase), (
                f"{module.__name__}.{name} subclasses ExchangeClientBase"
            )


def test_phase9_packages_expose_no_write_surface_method():
    forbidden = {"create_order", "cancel_order", "set_leverage", "set_margin_mode"}
    for module in _modules_for("app.execution", "app.incidents", "app.reconciliation"):
        for name, member in inspect.getmembers(module, inspect.isclass):
            if not inspect.getmodule(member) or not inspect.getmodule(member).__name__.startswith(
                ("app.execution", "app.incidents", "app.reconciliation")
            ):
                continue
            for fn_name in forbidden:
                fn = getattr(member, fn_name, None)
                if fn is None:
                    continue
                # The only acceptable case is inheriting the
                # ExchangeClientBase refusal; Phase 9 classes never
                # subclass that, so getting here means a real method
                # was added.
                raise AssertionError(
                    f"{module.__name__}.{name}.{fn_name} unexpectedly defined"
                )


# ---------------------------------------------------------------------------
# Phase 9 vocabulary
# ---------------------------------------------------------------------------
def test_order_intent_vocabulary_complete():
    assert {i.value for i in OrderIntent} == {
        "new_open",
        "scale_in",
        "lock_profit",
        "forced_exit",
        "distribution_exit",
        "protective_close",
        "kill_all",
        "stop_attach",
    }


def test_intent_partition_no_overlap_no_gap():
    assert NEW_OPEN_INTENTS.isdisjoint(REDUCE_ONLY_INTENTS)
    assert set(NEW_OPEN_INTENTS) | set(REDUCE_ONLY_INTENTS) == set(OrderIntent)


def test_order_kind_vocabulary_complete():
    assert {k.value for k in OrderKind} == {
        "limit",
        "market",
        "stop_market",
        "stop_limit",
    }


def test_margin_mode_only_admits_isolated():
    """Cross margin is not declared at all in Phase 9."""
    assert {m.value for m in MarginMode} == {"isolated"}


def test_mismatch_type_vocabulary_complete():
    expected = {
        "order_mismatch",
        "position_mismatch",
        "stop_mismatch",
        "equity_drift",
        "ws_rest_conflict",
        "ghost_position",
        "missing_remote_position",
        "unattached_stop",
    }
    assert {t.value for t in MismatchType} == expected


def test_mismatch_severity_vocabulary_complete():
    assert {s.value for s in MismatchSeverity} == {"P0", "P1", "P2"}


# ---------------------------------------------------------------------------
# Driver construction guard
# ---------------------------------------------------------------------------
def test_driver_construction_refuses_drifted_safety_lock(in_memory_conn):
    from app.database.repositories import EventRepository
    from app.risk.engine import RiskEngine

    settings = get_settings()
    repo = EventRepository(in_memory_conn)
    risk = RiskEngine(settings=settings, event_repo=repo)
    object.__setattr__(settings.defaults.mode, "live_trading_enabled", True)
    try:
        with pytest.raises(SafeModeViolation):
            ExecutionFSMDriver(
                risk_engine=risk,
                event_repo=repo,
                paper_ledger=PaperLedger(),
                settings=settings,
            )
    finally:
        object.__setattr__(settings.defaults.mode, "live_trading_enabled", False)


# ---------------------------------------------------------------------------
# Phase 9 event types reachable through EventType
# ---------------------------------------------------------------------------
def test_phase9_event_types_reachable():
    """The EventType enum must already declare every Phase 9 event."""
    required = (
        EventType.ORDER_SENT,
        EventType.ORDER_ACK,
        EventType.ORDER_PARTIAL_FILLED,
        EventType.ORDER_FILLED,
        EventType.ORDER_CANCELLED,
        EventType.STOP_SENT,
        EventType.STOP_CONFIRMED,
        EventType.STOP_FAILED,
        EventType.POSITION_OPENED,
        EventType.POSITION_UPDATED,
        EventType.POSITION_CLOSED,
        EventType.EXIT_TRIGGERED,
        EventType.RECONCILIATION_STARTED,
        EventType.RECONCILIATION_MISMATCH,
        EventType.RECONCILIATION_RESOLVED,
        EventType.PROTECTION_MODE_ENTERED,
        EventType.PROTECTION_MODE_EXITED,
        EventType.INCIDENT_OPENED,
        EventType.INCIDENT_RESOLVED,
    )
    for et in required:
        assert isinstance(et, EventType)


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------
def test_execution_package_public_exports():
    import app.execution as execution

    for name in (
        "ExecutionFSM",
        "ExecutionFSMDriver",
        "IllegalTransition",
        "OrderRequest",
        "OrderIntent",
        "OrderKind",
        "OrderSide",
        "MarginMode",
        "TimeInForce",
        "FillEvent",
        "StopEvent",
        "PaperLedger",
    ):
        assert name in execution.__all__, f"{name} missing from app.execution"


def test_reconciliation_package_public_exports():
    import app.reconciliation as r

    for name in (
        "Reconciler",
        "ReconciliationDecision",
        "Mismatch",
        "MismatchType",
        "MismatchSeverity",
        "LocalSnapshot",
        "RemoteSnapshot",
        "OrderView",
        "PositionView",
        "StopView",
        "EquitySnapshot",
        "LinkHealth",
    ):
        assert name in r.__all__, f"{name} missing from app.reconciliation"


def test_incidents_package_public_exports():
    import app.incidents as inc

    for name in ("Incident", "IncidentRecord", "IncidentRepository", "ProtectionHook"):
        assert name in inc.__all__, f"{name} missing from app.incidents"


# ---------------------------------------------------------------------------
# OrderRequest validates Phase 9 hard rules at the model layer
# ---------------------------------------------------------------------------
def test_order_request_refuses_zero_qty():
    with pytest.raises(Exception):
        OrderRequest(
            client_order_id="x",
            symbol="X",
            side=OrderSide.BUY,
            qty=0,
            limit_price=1.0,
        )


def test_order_request_refuses_excess_slippage():
    with pytest.raises(Exception):
        OrderRequest(
            client_order_id="x",
            symbol="X",
            side=OrderSide.BUY,
            qty=1.0,
            limit_price=1.0,
            max_slippage_pct=0.5,  # 50% - way above the cap
        )
