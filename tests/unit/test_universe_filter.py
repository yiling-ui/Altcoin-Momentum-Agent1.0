"""Phase 5 - Universe Filter tests (Issue #5).

Acceptance criterion 4: "Universe Filter 能过滤不合格 symbol".
Phase 5 hard rule 5: "任何 reject 必须有 reject_reason".
Phase 5 hard rule 6: "reject 必须写入 Event Sourcing".
"""

from __future__ import annotations

import pytest

from app.core.enums import (
    DataReliability,
    MarketRegime,
    RiskPermission,
    UniverseRejectReason,
)
from app.core.events import EventType
from app.exchanges.models import ExchangeSymbol
from app.regime import REGIME_TO_RISK_PERMISSION, RegimeSnapshot
from app.universe import UniverseConfig, UniverseDecision, UniverseFilter, UniverseInput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _good_input(**overrides) -> UniverseInput:
    base = dict(
        symbol="BTCUSDT",
        contract_status="TRADING",
        spread_pct=0.001,
        orderbook_depth_usdt=200_000.0,
        trade_count_5m=50,
        volume_5m=1_000.0,
        reliability=DataReliability.A,
        is_data_degraded=False,
        abnormal_data_flag=False,
        market_regime=MarketRegime.MEME_RISK_ON,
        risk_permission=RiskPermission.ALLOW_ATTACK,
    )
    base.update(overrides)
    return UniverseInput(**base)


# ---------------------------------------------------------------------------
# Frozen value objects
# ---------------------------------------------------------------------------
def test_universe_input_is_frozen():
    request = _good_input()
    with pytest.raises(Exception):
        request.symbol = "ETHUSDT"  # type: ignore[misc]


def test_universe_decision_is_frozen():
    decision = UniverseDecision(symbol="BTCUSDT", eligible=True)
    with pytest.raises(Exception):
        decision.eligible = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Accept path
# ---------------------------------------------------------------------------
def test_accepts_a_clean_symbol(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    decision = f.evaluate(_good_input())
    assert decision.eligible is True
    assert decision.reject_reasons == ()
    assert f.accepted == 1
    assert f.rejected == 0


# ---------------------------------------------------------------------------
# Each of the 7 reject conditions Issue #5 lists, plus the 2 phase-5 ones.
# ---------------------------------------------------------------------------
def test_rejects_when_spread_too_wide(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    decision = f.evaluate(_good_input(spread_pct=0.05))
    assert decision.eligible is False
    assert UniverseRejectReason.SPREAD_TOO_WIDE in decision.reject_reasons


def test_rejects_when_depth_insufficient(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    decision = f.evaluate(_good_input(orderbook_depth_usdt=10.0))
    assert decision.eligible is False
    assert UniverseRejectReason.DEPTH_INSUFFICIENT in decision.reject_reasons


def test_rejects_when_trade_discontinuous(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    decision = f.evaluate(_good_input(trade_count_5m=1))
    assert decision.eligible is False
    assert UniverseRejectReason.TRADE_DISCONTINUOUS in decision.reject_reasons


def test_rejects_when_contract_not_trading(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    decision = f.evaluate(_good_input(contract_status="HALTED"))
    assert decision.eligible is False
    assert (
        UniverseRejectReason.CONTRACT_NOT_TRADING in decision.reject_reasons
    )


def test_rejects_when_data_reliability_too_low(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    decision = f.evaluate(_good_input(reliability=DataReliability.D))
    assert decision.eligible is False
    assert (
        UniverseRejectReason.DATA_RELIABILITY_TOO_LOW
        in decision.reject_reasons
    )


def test_rejects_when_volume_below_minimum(events_repo):
    cfg = UniverseConfig(min_volume_5m=1_000.0)
    f = UniverseFilter(config=cfg, event_repo=events_repo)
    decision = f.evaluate(_good_input(volume_5m=10.0))
    assert decision.eligible is False
    assert (
        UniverseRejectReason.VOLUME_BELOW_MINIMUM in decision.reject_reasons
    )


def test_rejects_when_abnormal_data_flag_set(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    decision = f.evaluate(_good_input(abnormal_data_flag=True))
    assert decision.eligible is False
    assert (
        UniverseRejectReason.ABNORMAL_DATA_FLAG in decision.reject_reasons
    )


def test_rejects_when_data_degraded(events_repo):
    """Phase 5 hard rule 4."""
    f = UniverseFilter(event_repo=events_repo)
    decision = f.evaluate(_good_input(is_data_degraded=True))
    assert decision.eligible is False
    assert UniverseRejectReason.DATA_DEGRADED in decision.reject_reasons


# ---------------------------------------------------------------------------
# Phase 5 hard rule 1: SYSTEMIC_RISK -> regime block
# ---------------------------------------------------------------------------
def test_rejects_when_regime_is_systemic_risk(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    decision = f.evaluate(
        _good_input(
            market_regime=MarketRegime.SYSTEMIC_RISK,
            risk_permission=REGIME_TO_RISK_PERMISSION[
                MarketRegime.SYSTEMIC_RISK
            ],
        )
    )
    assert decision.eligible is False
    assert UniverseRejectReason.REGIME_BLOCKED in decision.reject_reasons


def test_accepts_when_regime_is_meme_risk_on(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    decision = f.evaluate(
        _good_input(
            market_regime=MarketRegime.MEME_RISK_ON,
            risk_permission=RiskPermission.ALLOW_ATTACK,
        )
    )
    assert decision.eligible is True


# ---------------------------------------------------------------------------
# Multiple reasons accumulate (Phase 5 hard rule 5)
# ---------------------------------------------------------------------------
def test_multiple_reject_reasons_accumulate(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    decision = f.evaluate(
        _good_input(
            spread_pct=0.05,
            orderbook_depth_usdt=10.0,
            is_data_degraded=True,
        )
    )
    assert not decision.eligible
    # All three reasons appear in the same decision.
    assert UniverseRejectReason.SPREAD_TOO_WIDE in decision.reject_reasons
    assert UniverseRejectReason.DEPTH_INSUFFICIENT in decision.reject_reasons
    assert UniverseRejectReason.DATA_DEGRADED in decision.reject_reasons


# ---------------------------------------------------------------------------
# Phase 5 hard rule 6: persisted as event
# ---------------------------------------------------------------------------
def test_accept_decision_persisted_as_event(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    f.evaluate(_good_input())
    events = events_repo.list_events(event_type=EventType.UNIVERSE_FILTERED)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["eligible"] is True
    assert payload["reject_reasons"] == []
    assert payload["symbol"] == "BTCUSDT"


def test_reject_decision_persisted_as_event(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    f.evaluate(_good_input(spread_pct=0.05))
    events = events_repo.list_events(event_type=EventType.UNIVERSE_FILTERED)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["eligible"] is False
    assert UniverseRejectReason.SPREAD_TOO_WIDE.value in payload["reject_reasons"]


def test_emit_event_false_skips_persistence(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    f.evaluate(_good_input(), emit_event=False)
    events = events_repo.list_events(event_type=EventType.UNIVERSE_FILTERED)
    assert len(events) == 0


# ---------------------------------------------------------------------------
# evaluate_snapshot helper
# ---------------------------------------------------------------------------
def test_evaluate_snapshot_helper_accepts_clean_symbol(events_repo):
    from app.core.models import MarketSnapshot

    f = UniverseFilter(event_repo=events_repo)
    sym_meta = ExchangeSymbol(
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
    )
    snapshot = MarketSnapshot(
        symbol="BTCUSDT",
        timestamp=1,
        last_price=100.0,
        bid=99.99,
        ask=100.01,
        spread_pct=0.0001,
        volume_5m=2_000.0,
        orderbook_depth_usdt=100_000.0,
    )
    regime = RegimeSnapshot(
        market_regime=MarketRegime.MEME_RISK_ON,
        btc_trend=__import__("app.core.enums", fromlist=["BtcTrend"]).BtcTrend.UP,
        btc_volatility=__import__(
            "app.core.enums", fromlist=["BtcVolatility"]
        ).BtcVolatility.NORMAL,
        alt_liquidity=__import__(
            "app.core.enums", fromlist=["AltLiquidity"]
        ).AltLiquidity.EXPANDING,
        risk_permission=RiskPermission.ALLOW_ATTACK,
    )
    decision = f.evaluate_snapshot(
        snapshot,
        symbol_meta=sym_meta,
        regime=regime,
        is_data_degraded=False,
        abnormal_data_flag=False,
        reliability=DataReliability.A,
        trade_count_5m=50,
    )
    assert decision.eligible is True


def test_evaluate_snapshot_helper_inherits_regime_block():
    from app.core.models import MarketSnapshot

    f = UniverseFilter()
    sym_meta = ExchangeSymbol(
        symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT"
    )
    snapshot = MarketSnapshot(
        symbol="BTCUSDT",
        timestamp=1,
        last_price=100.0,
        bid=99.99,
        ask=100.01,
        spread_pct=0.0001,
        volume_5m=2_000.0,
        orderbook_depth_usdt=100_000.0,
    )
    regime = RegimeSnapshot(
        market_regime=MarketRegime.SYSTEMIC_RISK,
        btc_trend=__import__("app.core.enums", fromlist=["BtcTrend"]).BtcTrend.DOWN,
        btc_volatility=__import__(
            "app.core.enums", fromlist=["BtcVolatility"]
        ).BtcVolatility.EXTREME,
        alt_liquidity=__import__(
            "app.core.enums", fromlist=["AltLiquidity"]
        ).AltLiquidity.UNKNOWN,
        risk_permission=RiskPermission.BLOCK_ALL,
    )
    decision = f.evaluate_snapshot(
        snapshot,
        symbol_meta=sym_meta,
        regime=regime,
        emit_event=False,
        trade_count_5m=50,
    )
    assert decision.eligible is False
    assert UniverseRejectReason.REGIME_BLOCKED in decision.reject_reasons


# ---------------------------------------------------------------------------
# Filter is stateless: counters add up per evaluation
# ---------------------------------------------------------------------------
def test_counters_accumulate_across_calls(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    f.evaluate(_good_input())
    f.evaluate(_good_input(spread_pct=0.05))
    f.evaluate(_good_input(symbol="ETHUSDT"))
    assert f.evaluations == 3
    assert f.accepted == 2
    assert f.rejected == 1
    assert f.universe_filtered_events_emitted == 3


def test_evaluate_many_runs_each_request(events_repo):
    f = UniverseFilter(event_repo=events_repo)
    decisions = f.evaluate_many(
        [
            _good_input(symbol="BTCUSDT"),
            _good_input(symbol="ETHUSDT", spread_pct=0.05),
            _good_input(symbol="PEPEUSDT", contract_status="HALTED"),
        ]
    )
    assert [d.eligible for d in decisions] == [True, False, False]
    assert events_repo.count_events(event_type=EventType.UNIVERSE_FILTERED) == 3
