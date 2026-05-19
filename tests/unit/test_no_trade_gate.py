"""Phase 7 - No-Trade Gate tests (Issue #7, Spec §27.2)."""

from __future__ import annotations

from app.core.enums import (
    CircuitBreakerState,
    ExchangeConnectionState,
    LiquidityRejectReason,
    ManipulationLevel,
    MarketRegime,
    AltLiquidity,
    BtcTrend,
    BtcVolatility,
    RiskPermission,
    RiskRejectReason,
    TradeConfirmationLevel,
    UniverseRejectReason,
)
from app.liquidity.models import ExitPlan, LiquidityDecision, Side
from app.regime.models import RegimeSnapshot
from app.risk.no_trade_gate import (
    NoTradeGateInput,
    evaluate_no_trade_gate,
)
from app.universe.models import UniverseDecision


def _regime(perm: RiskPermission, regime: MarketRegime = MarketRegime.MEME_RISK_ON):
    return RegimeSnapshot(
        market_regime=regime,
        btc_trend=BtcTrend.UP,
        btc_volatility=BtcVolatility.NORMAL,
        alt_liquidity=AltLiquidity.STABLE,
        risk_permission=perm,
    )


def test_clean_input_is_allowed():
    decision = evaluate_no_trade_gate(NoTradeGateInput(symbol="X"))
    assert decision.allowed
    assert decision.reasons == ()


# ---------------------------------------------------------------------------
# Acceptance criterion 9: DATA_DEGRADED must reject or downgrade
# ---------------------------------------------------------------------------
def test_data_degraded_rejects_new_open():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(symbol="X", is_data_degraded=True)
    )
    assert not decision.allowed
    assert RiskRejectReason.DATA_DEGRADED in decision.reasons


def test_data_degraded_does_not_block_non_open_actions():
    """A protective exit / kill_all path must NOT be blocked by
    data-degraded; Phase 9 will set is_new_open=False on those."""
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(symbol="X", is_data_degraded=True, is_new_open=False)
    )
    assert decision.allowed


# ---------------------------------------------------------------------------
# SYSTEMIC_RISK / regime
# ---------------------------------------------------------------------------
def test_systemic_risk_block_all_rejects():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            regime_snapshot=_regime(
                RiskPermission.BLOCK_ALL, MarketRegime.SYSTEMIC_RISK
            ),
        )
    )
    assert not decision.allowed
    assert RiskRejectReason.REGIME_BLOCK_ALL in decision.reasons


def test_observe_only_rejects_new_open():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            regime_snapshot=_regime(RiskPermission.OBSERVE_ONLY),
        )
    )
    assert not decision.allowed
    assert RiskRejectReason.REGIME_OBSERVE_ONLY_FOR_NEW_OPEN in decision.reasons


def test_allow_scout_rejects_attack_intent():
    """Issue #7 semantic lock #5: ALLOW_SCOUT only permits observe /
    scout, NOT attack / right_tail_amplify."""
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            attack_intent=True,
            regime_snapshot=_regime(
                RiskPermission.ALLOW_SCOUT, MarketRegime.ALT_RISK_OFF
            ),
        )
    )
    assert not decision.allowed
    assert RiskRejectReason.REGIME_SCOUT_ONLY_FOR_ATTACK in decision.reasons


def test_allow_scout_does_not_reject_observe_intent():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            attack_intent=False,
            regime_snapshot=_regime(RiskPermission.ALLOW_SCOUT),
        )
    )
    assert decision.allowed


def test_allow_attack_lets_attack_through():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            attack_intent=True,
            regime_snapshot=_regime(RiskPermission.ALLOW_ATTACK),
        )
    )
    assert decision.allowed


# ---------------------------------------------------------------------------
# Universe / Liquidity / can_exit_position
# ---------------------------------------------------------------------------
def test_universe_ineligible_rejects():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            universe_decision=UniverseDecision(
                symbol="X",
                eligible=False,
                reject_reasons=(UniverseRejectReason.SPREAD_TOO_WIDE,),
            ),
        )
    )
    assert not decision.allowed
    assert RiskRejectReason.UNIVERSE_INELIGIBLE in decision.reasons


def test_liquidity_rejected_blocks():
    """Issue #7 acceptance criterion 8: Liquidity not exitable -> reject."""
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            liquidity_decision=LiquidityDecision(
                symbol="X",
                side=Side.LONG,
                passed=False,
                spread_score=0.0,
                depth_score=0.0,
                estimated_slippage_pct=0.05,
                estimated_exit_seconds=300.0,
                reject_reasons=(LiquidityRejectReason.SLIPPAGE_TOO_HIGH,),
            ),
        )
    )
    assert not decision.allowed
    assert RiskRejectReason.LIQUIDITY_REJECTED in decision.reasons


def test_no_exit_channel_blocks():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            exit_plan=ExitPlan(
                symbol="X",
                side=Side.LONG,
                qty=1.0,
                feasible=False,
                estimated_slippage_pct=None,
                estimated_exit_seconds=None,
                cleared_qty=0.0,
                weighted_avg_fill_price=None,
                reject_reasons=(LiquidityRejectReason.NO_EXIT_CHANNEL,),
            ),
        )
    )
    assert not decision.allowed
    assert RiskRejectReason.NO_EXIT_CHANNEL in decision.reasons


# ---------------------------------------------------------------------------
# Manipulation + confirmation hard rules
# ---------------------------------------------------------------------------
def test_m3_blocks_new_open():
    """Issue #7 acceptance criterion 3: M3 必须禁止新开仓."""
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(symbol="X", manipulation_level=ManipulationLevel.M3)
    )
    assert not decision.allowed
    assert RiskRejectReason.MANIPULATION_M3 in decision.reasons


def test_m3_does_not_block_protective_exit():
    """Phase 7 protective-exit caveat: M3 only blocks NEW openings.
    A reduce-only / kill_all path (is_new_open=False) must pass."""
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            is_new_open=False,
            manipulation_level=ManipulationLevel.M3,
        )
    )
    assert decision.allowed


def test_m2_with_attack_intent_blocks():
    """Issue #7 acceptance criterion 4: M2 + attack_intent."""
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            attack_intent=True,
            manipulation_level=ManipulationLevel.M2,
        )
    )
    assert not decision.allowed
    assert RiskRejectReason.MANIPULATION_M2_ATTACK in decision.reasons


def test_m2_without_attack_intent_passes():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            attack_intent=False,
            manipulation_level=ManipulationLevel.M2,
        )
    )
    assert decision.allowed


def test_t0_with_attack_intent_blocks():
    """Issue #7 acceptance criterion 5: T0/T1 + attack_intent."""
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            attack_intent=True,
            trade_confirmation_level=TradeConfirmationLevel.T0,
        )
    )
    assert not decision.allowed
    assert (
        RiskRejectReason.TRADE_CONFIRMATION_TOO_LOW_FOR_ATTACK
        in decision.reasons
    )


def test_t1_with_attack_intent_blocks():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            attack_intent=True,
            trade_confirmation_level=TradeConfirmationLevel.T1,
        )
    )
    assert not decision.allowed


def test_t3_alone_does_not_authorise_attack():
    """Issue #7 acceptance criterion 6: T3/T4 alone is not approval.

    The gate must still see a regime (or default to no-opinion) and
    every other gate must pass. A T3 reading without any other input
    is allowed *by the No-Trade Gate*, but the wider Risk Engine
    will keep refusing live_trading_required and right_tail_amplify
    via the Phase 1 hard flags."""
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            attack_intent=True,
            trade_confirmation_level=TradeConfirmationLevel.T3,
        )
    )
    # The gate has no other reason to fire -> it permits.
    # The full RiskEngine adds the live_trading / right_tail / Phase 1
    # gates on top of the gate output; this is asserted in
    # tests/unit/test_risk_engine_phase7.py.
    assert decision.allowed


# ---------------------------------------------------------------------------
# Stop / position / breaker
# ---------------------------------------------------------------------------
def test_stop_unconfirmed_blocks():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(symbol="X", stop_unconfirmed=True)
    )
    assert not decision.allowed
    assert RiskRejectReason.STOP_UNCONFIRMED in decision.reasons


def test_unknown_position_blocks():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(symbol="X", unknown_position=True)
    )
    assert not decision.allowed
    assert RiskRejectReason.UNKNOWN_POSITION in decision.reasons


def test_daily_loss_breaker_open_blocks():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            daily_loss_breaker_state=CircuitBreakerState.OPEN_DAILY_LOSS,
        )
    )
    assert not decision.allowed
    assert RiskRejectReason.DAILY_LOSS_BREAKER_OPEN in decision.reasons


def test_consecutive_loss_breaker_open_blocks():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            consecutive_loss_breaker_state=CircuitBreakerState.OPEN_CONSECUTIVE_LOSS,
        )
    )
    assert not decision.allowed
    assert RiskRejectReason.CONSECUTIVE_LOSS_BREAKER_OPEN in decision.reasons


def test_exchange_disconnected_blocks():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            exchange_connection_state=ExchangeConnectionState.DISCONNECTED,
        )
    )
    assert not decision.allowed
    assert RiskRejectReason.EXCHANGE_DISCONNECTED in decision.reasons


def test_exchange_connected_passes():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            exchange_connection_state=ExchangeConnectionState.CONNECTED,
        )
    )
    assert decision.allowed


def test_multiple_reasons_accumulate():
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="X",
            attack_intent=True,
            stop_unconfirmed=True,
            unknown_position=True,
            is_data_degraded=True,
            manipulation_level=ManipulationLevel.M3,
            trade_confirmation_level=TradeConfirmationLevel.T0,
        )
    )
    assert not decision.allowed
    expected = {
        RiskRejectReason.STOP_UNCONFIRMED,
        RiskRejectReason.UNKNOWN_POSITION,
        RiskRejectReason.DATA_DEGRADED,
        RiskRejectReason.MANIPULATION_M3,
        RiskRejectReason.TRADE_CONFIRMATION_TOO_LOW_FOR_ATTACK,
    }
    assert expected.issubset(set(decision.reasons))
