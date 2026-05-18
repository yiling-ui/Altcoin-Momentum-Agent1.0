"""Phase 5 - structural boundary tests (Issue #5).

These tests are *contract* tests, not functional tests. They pin the
shape of the Phase 5 packages so the Issue #6 / #7 PRs cannot drift:

  - The Spec §15.3 regime -> risk_permission map is exhaustive and
    matches the in-code declaration.
  - All three packages re-export their public symbols cleanly.
  - The five regimes from Spec §15.2 each have a deterministic
    risk_permission.
  - The four write-surface refusals on ExchangeClientBase are still
    in force (re-asserted from a Phase 5 vantage point because a Phase 5
    PR could in theory weaken them).
  - The Phase 1 safety lock is still on.
"""

from __future__ import annotations

from app.config.settings import load_settings
from app.core.enums import (
    AltLiquidity,
    BtcTrend,
    BtcVolatility,
    DataReliability,
    LiquidityRejectReason,
    MarketRegime,
    RiskPermission,
    UniverseRejectReason,
)
from app.core.errors import SafeModeViolation
from app.exchanges.base import ExchangeClientBase
from app.liquidity import LiquidityFilter
from app.regime import REGIME_TO_RISK_PERMISSION, RegimeEngine
from app.universe import UniverseFilter


# ---------------------------------------------------------------------------
# Phase 1 safety lock is still in force at Phase 5
# ---------------------------------------------------------------------------
def test_phase1_safety_lock_unchanged():
    settings = load_settings()
    assert settings.trading_mode == "paper"
    assert settings.live_trading_enabled is False
    assert settings.right_tail_enabled is False
    assert settings.llm_enabled is False
    assert settings.exchange_live_order_enabled is False


# ---------------------------------------------------------------------------
# Phase 3 read-only contract still in force
# ---------------------------------------------------------------------------
def test_exchange_client_base_write_surfaces_still_refuse():
    """Phase 5 must NOT touch the base-class write refusals."""

    class _Probe(ExchangeClientBase):
        name = "probe"

        def get_symbols(self):
            return []

        def get_orderbook(self, symbol, *, depth=20):
            raise RuntimeError("not in this test")

        def get_recent_trades(self, symbol, *, limit=100):
            raise RuntimeError("not in this test")

        def get_funding_rate(self, symbol):
            raise RuntimeError("not in this test")

        def get_open_interest(self, symbol):
            raise RuntimeError("not in this test")

        def get_account_snapshot(self):
            raise RuntimeError("not in this test")

    p = _Probe()
    for fn in ("create_order", "cancel_order", "set_leverage", "set_margin_mode"):
        try:
            getattr(p, fn)()
        except SafeModeViolation:
            continue
        else:
            raise AssertionError(
                f"{fn} did NOT refuse - Phase 5 must not loosen the "
                f"Phase 3 read-only contract"
            )


# ---------------------------------------------------------------------------
# Spec §15.3 mapping
# ---------------------------------------------------------------------------
def test_regime_map_is_exhaustive():
    assert set(REGIME_TO_RISK_PERMISSION.keys()) == set(MarketRegime)


def test_regime_map_value_set():
    assert set(REGIME_TO_RISK_PERMISSION.values()).issubset(set(RiskPermission))


def test_systemic_risk_blocks_all():
    assert (
        REGIME_TO_RISK_PERMISSION[MarketRegime.SYSTEMIC_RISK]
        is RiskPermission.BLOCK_ALL
    )


def test_meme_and_sector_allow_attack():
    assert (
        REGIME_TO_RISK_PERMISSION[MarketRegime.MEME_RISK_ON]
        is RiskPermission.ALLOW_ATTACK
    )
    assert (
        REGIME_TO_RISK_PERMISSION[MarketRegime.SECTOR_ROTATION]
        is RiskPermission.ALLOW_ATTACK
    )


# ---------------------------------------------------------------------------
# Each Phase 5 enum has the values the spec mandates
# ---------------------------------------------------------------------------
def test_market_regime_enum_has_five_named_states():
    expected = {"MEME_RISK_ON", "SECTOR_ROTATION", "BTC_ABSORPTION", "ALT_RISK_OFF", "SYSTEMIC_RISK"}
    assert {m.name for m in MarketRegime} == expected


def test_btc_trend_enum_values():
    assert {t.name for t in BtcTrend} == {"UP", "SIDEWAYS", "DOWN", "UNKNOWN"}


def test_btc_volatility_enum_values():
    assert {v.name for v in BtcVolatility} == {
        "LOW",
        "NORMAL",
        "HIGH",
        "EXTREME",
        "UNKNOWN",
    }


def test_alt_liquidity_enum_values():
    assert {a.name for a in AltLiquidity} == {
        "EXPANDING",
        "STABLE",
        "CONTRACTING",
        "DRY",
        "UNKNOWN",
    }


def test_risk_permission_enum_values():
    assert {p.name for p in RiskPermission} == {
        "ALLOW_ATTACK",
        "ALLOW_SCOUT",
        "OBSERVE_ONLY",
        "BLOCK_ALL",
    }


def test_universe_reject_reason_covers_issue_5_acceptance_set():
    # Issue #5 explicitly enumerates these conditions.
    expected_subset = {
        "SPREAD_TOO_WIDE",
        "DEPTH_INSUFFICIENT",
        "TRADE_DISCONTINUOUS",
        "CONTRACT_NOT_TRADING",
        "DATA_RELIABILITY_TOO_LOW",
        "DATA_DEGRADED",
        "VOLUME_BELOW_MINIMUM",
        "ABNORMAL_DATA_FLAG",
        "REGIME_BLOCKED",
    }
    assert expected_subset <= {r.name for r in UniverseRejectReason}


def test_liquidity_reject_reason_covers_phase5_set():
    expected_subset = {
        "SPREAD_TOO_WIDE",
        "DEPTH_INSUFFICIENT",
        "SLIPPAGE_TOO_HIGH",
        "NO_EXIT_CHANNEL",
        "EXIT_TOO_SLOW",
        "BOOK_MISSING",
        "DATA_DEGRADED",
        "REGIME_BLOCKED",
    }
    assert expected_subset <= {r.name for r in LiquidityRejectReason}


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------
def test_regime_package_exports_engine_and_models():
    import app.regime as regime_pkg

    for name in ("RegimeEngine", "RegimeConfig", "RegimeInput", "RegimeSnapshot"):
        assert hasattr(regime_pkg, name)


def test_universe_package_exports_filter_and_models():
    import app.universe as universe_pkg

    for name in ("UniverseFilter", "UniverseConfig", "UniverseInput"):
        assert hasattr(universe_pkg, name)


def test_liquidity_package_exports_filter_and_helpers():
    import app.liquidity as liquidity_pkg

    for name in (
        "LiquidityFilter",
        "LiquidityConfig",
        "LiquidityInput",
        "LiquidityDecision",
        "ExitPlan",
        "Side",
        "estimate_book_walk",
        "estimated_slippage_pct",
        "walk_book_for_quote_notional",
    ):
        assert hasattr(liquidity_pkg, name)


# ---------------------------------------------------------------------------
# DataReliability tier ordering still matches Phase 3
# ---------------------------------------------------------------------------
def test_data_reliability_a_is_strongest():
    assert DataReliability.A.is_at_least(DataReliability.A)
    assert DataReliability.A.is_at_least(DataReliability.B)
    assert DataReliability.A.is_at_least(DataReliability.D)
    assert not DataReliability.D.is_at_least(DataReliability.A)


# ---------------------------------------------------------------------------
# Phase 5 engines do not own a buffer / client.
# ---------------------------------------------------------------------------
def test_phase5_engines_do_not_instantiate_a_market_data_buffer():
    """Sanity check: instantiating each engine without an exchange or
    buffer must not crash and must not own one. Phase 5 hard rule:
    the engine does not auto-connect to anything."""
    regime = RegimeEngine()
    universe = UniverseFilter()
    liquidity = LiquidityFilter()
    # No private _exchange / _buffer reference should exist on these
    # engines. They take state in via their evaluate() methods.
    for engine in (regime, universe, liquidity):
        assert not hasattr(engine, "_exchange"), (
            f"{type(engine).__name__} owns an _exchange attribute; "
            f"Phase 5 engines must not auto-connect."
        )
        assert not hasattr(engine, "_buffer"), (
            f"{type(engine).__name__} owns a _buffer attribute; "
            f"Phase 5 engines must not own a MarketDataBuffer."
        )
