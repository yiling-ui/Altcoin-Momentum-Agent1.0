"""Phase 6 - boundary tests (Issue #6).

Pin the cumulative defence-in-depth that Phase 6 inherits from Phase
1-5 plus the new Phase 6 invariants:

  - Phase 1 safety lock unchanged.
  - Phase 3 read-only invariant unchanged: every write surface still
    refuses with SafeModeViolation.
  - The four Phase 6 event types are reachable through EventType.
  - The reason-tag enums are exhaustive enough to round-trip every
    code path the classifiers can fire.
  - The four classifier classes are public + don't expose a write
    surface.
  - The Risk Engine adds the three Phase 6 fields and accepts the
    legacy call signature unchanged.
"""

from __future__ import annotations

import inspect

from app.confirmation import RealTradeConfirmation
from app.core.enums import (
    AnomalyReasonTag,
    ConfirmationReasonTag,
    ManipulationLevel,
    ManipulationReasonTag,
    PreAnomalyReasonTag,
    TradeConfirmationLevel,
)
from app.core.events import EventType
from app.exchanges.base import ExchangeClientBase, WRITE_SURFACE_METHODS
from app.exchanges.mock import MockExchangeClient
from app.exchanges.binance import BinanceClient
from app.core.errors import SafeModeViolation
from app.manipulation import ManipulationDetector
from app.risk.engine import RiskEngine, RiskRequest
from app.scanner import AnomalyScanner, PreAnomalyScanner


# ---------------------------------------------------------------------------
# Phase 1 safety lock + Phase 3 read-only invariant unchanged
# ---------------------------------------------------------------------------
def test_phase3_write_surfaces_still_refuse_on_mock():
    client = MockExchangeClient(autostart=False)
    for fn_name in WRITE_SURFACE_METHODS:
        try:
            getattr(client, fn_name)()
        except SafeModeViolation:
            continue
        else:  # pragma: no cover - regression
            raise AssertionError(
                f"{fn_name} stopped refusing in Phase 6"
            )


def test_phase3_write_surfaces_still_refuse_on_binance_skeleton():
    client = BinanceClient()
    for fn_name in WRITE_SURFACE_METHODS:
        try:
            getattr(client, fn_name)()
        except SafeModeViolation:
            continue
        else:  # pragma: no cover - regression
            raise AssertionError(
                f"{fn_name} stopped refusing in Phase 6"
            )


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------
def test_phase6_event_types_are_reachable():
    for name in (
        "PRE_ANOMALY_DETECTED",
        "ANOMALY_DETECTED",
        "TRADE_CONFIRMED",
        "MANIPULATION_DETECTED",
    ):
        assert getattr(EventType, name).value == name


# ---------------------------------------------------------------------------
# Reason-tag enums exist and contain the Phase 6 base vocabulary
# ---------------------------------------------------------------------------
def test_pre_anomaly_reason_tags_cover_spec_17_2():
    expected = {
        "VOLUME_BASE_EXPANSION",
        "SPREAD_COMPRESSION",
        "BUY_PRESSURE_RISING",
        "OI_SOFT_RISE",
        "FUNDING_NOT_OVERHEATED",
        "MINOR_UPTREND",
    }
    actual = {t.name for t in PreAnomalyReasonTag}
    assert expected.issubset(actual)


def test_anomaly_reason_tags_cover_spec_18_1():
    expected = {
        "OI_SPIKE",
        "CVD_SPIKE",
        "VOLUME_SPIKE",
        "ATR_EXPANSION",
        "FUNDING_EXTREME",
        "LIQUIDATION_SPIKE",
        "SWEEP",
        "MULTI_TIMEFRAME_BREAKOUT",
    }
    actual = {t.name for t in AnomalyReasonTag}
    assert expected.issubset(actual)


def test_confirmation_reason_tags_cover_spec_20_4():
    expected = {
        "CVD_PRICE_AGREEMENT",
        "BREAKOUT_HELD",
        "LARGE_TRADE_FOLLOW_THROUGH",
        "TRADE_EFFICIENCY_HIGH",
        "VOLUME_UP_PRICE_MOVE",
    }
    actual = {t.name for t in ConfirmationReasonTag}
    assert expected.issubset(actual)


def test_manipulation_reason_tags_cover_spec_21_2():
    expected = {
        "CVD_UP_PRICE_FLAT",
        "VOLUME_UP_PRICE_NO_MOVE",
        "OI_UP_PRICE_FLAT",
        "FUNDING_HOT_PRICE_WEAK",
        "UPPER_WICK_GROWTH",
        "BUY_PRESSURE_NO_PUSH",
        "BOOK_WALL_FLICKER",
        "NARRATIVE_AFTER_PUMP",
    }
    actual = {t.name for t in ManipulationReasonTag}
    assert expected.issubset(actual)


# ---------------------------------------------------------------------------
# Classifier surface
# ---------------------------------------------------------------------------
def test_classifiers_are_public():
    """Every Phase 6 classifier is exported from its package __init__."""
    import app.confirmation as conf
    import app.manipulation as manip
    import app.scanner as scan

    assert "PreAnomalyScanner" in scan.__all__
    assert "AnomalyScanner" in scan.__all__
    assert "RealTradeConfirmation" in conf.__all__
    assert "ManipulationDetector" in manip.__all__


def test_classifiers_have_no_write_surface_methods():
    forbidden = {"create_order", "cancel_order", "set_leverage", "set_margin_mode"}
    for cls in (
        PreAnomalyScanner,
        AnomalyScanner,
        RealTradeConfirmation,
        ManipulationDetector,
    ):
        members = {name for name, _ in inspect.getmembers(cls)}
        assert not (members & forbidden), (
            f"{cls.__name__} exposes a write surface: {members & forbidden}"
        )


def test_classifiers_do_not_subclass_exchange_client_base():
    for cls in (
        PreAnomalyScanner,
        AnomalyScanner,
        RealTradeConfirmation,
        ManipulationDetector,
    ):
        assert not issubclass(cls, ExchangeClientBase), (
            f"{cls.__name__} is an ExchangeClientBase subclass; forbidden in Phase 6."
        )


def test_classifiers_construct_without_exchange_or_buffer():
    """Phase 6 classifiers do not own a buffer or an exchange client.

    Any future PR that wires one in via ``__init__`` would change this
    test - the boundary needs an explicit review checkpoint.
    """
    PreAnomalyScanner()
    AnomalyScanner()
    RealTradeConfirmation()
    ManipulationDetector()


# ---------------------------------------------------------------------------
# Risk Engine surface
# ---------------------------------------------------------------------------
def test_risk_request_exposes_phase6_fields():
    fields = {f.name for f in RiskRequest.__dataclass_fields__.values()}
    assert {
        "manipulation_level",
        "trade_confirmation_level",
        "attack_intent",
    } <= fields


def test_risk_request_effective_attack_intent_implied_by_right_tail():
    req = RiskRequest(
        source_module="t",
        action="amplify",
        attack_intent=False,
        right_tail_amplify=True,
    )
    assert req.effective_attack_intent is True


def test_risk_engine_legacy_request_is_backwards_compatible():
    decision = RiskEngine().evaluate(
        RiskRequest(source_module="legacy", action="self_check")
    )
    assert decision.approved


# ---------------------------------------------------------------------------
# ManipulationLevel <-> TradeConfirmationLevel ladders are intact
# ---------------------------------------------------------------------------
def test_manipulation_levels_are_m0_to_m3():
    assert {l.value for l in ManipulationLevel} == {"M0", "M1", "M2", "M3"}


def test_confirmation_levels_are_t0_to_t4():
    assert {l.value for l in TradeConfirmationLevel} == {
        "T0",
        "T1",
        "T2",
        "T3",
        "T4",
    }
