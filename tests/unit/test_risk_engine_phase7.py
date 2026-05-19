"""Phase 7 - Risk Engine integration tests (Issue #7).

Drives the full Phase 7 ``RiskEngine`` against the composed
:class:`NoTradeGateInput` + Account Tier policy + Circuit Breakers.
Pins every Issue #7 acceptance criterion that involves the engine.
"""

from __future__ import annotations

from app.core.enums import (
    AccountLifeTier,
    AltLiquidity,
    BtcTrend,
    BtcVolatility,
    CircuitBreakerState,
    ExchangeConnectionState,
    LiquidityRejectReason,
    ManipulationLevel,
    MarketRegime,
    RiskPermission,
    TradeConfirmationLevel,
    UniverseRejectReason,
)
from app.core.events import EventType
from app.liquidity.models import ExitPlan, LiquidityDecision, Side
from app.regime.models import RegimeSnapshot
from app.risk.engine import RiskEngine, RiskRequest
from app.universe.models import UniverseDecision


def _regime(perm, regime=MarketRegime.MEME_RISK_ON):
    return RegimeSnapshot(
        market_regime=regime,
        btc_trend=BtcTrend.UP,
        btc_volatility=BtcVolatility.NORMAL,
        alt_liquidity=AltLiquidity.STABLE,
        risk_permission=perm,
    )


# ---------------------------------------------------------------------------
# Issue #7 acceptance criterion 8: Liquidity not exitable -> reject
# ---------------------------------------------------------------------------
def test_liquidity_rejected_blocks_attack():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            liquidity_decision=LiquidityDecision(
                symbol="PEPEUSDT",
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
    assert decision.rejected
    assert "liquidity_rejected" in decision.reasons


def test_no_exit_channel_blocks_attack():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            exit_plan=ExitPlan(
                symbol="PEPEUSDT",
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
    assert decision.rejected
    assert "no_exit_channel" in decision.reasons


# ---------------------------------------------------------------------------
# Issue #7 acceptance criterion 7: ALLOW_ATTACK alone does not authorise
# ---------------------------------------------------------------------------
def test_allow_attack_alone_does_not_authorise_live_trade():
    """ALLOW_ATTACK is a regime gate, not a trade approval. The Risk
    Engine still rejects live_trading_required because the Phase 1
    safety lock keeps live_trading_enabled=False."""
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            live_trading_required=True,
            regime_snapshot=_regime(RiskPermission.ALLOW_ATTACK),
            trade_confirmation_level=TradeConfirmationLevel.T4,
            manipulation_level=ManipulationLevel.M0,
        )
    )
    assert decision.rejected
    assert "live_trading_disabled" in decision.reasons


def test_t3_alone_does_not_authorise_live_trade():
    """Acceptance criterion 6: T3/T4 alone does not approve a trade."""
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            live_trading_required=True,
            trade_confirmation_level=TradeConfirmationLevel.T3,
        )
    )
    assert decision.rejected
    assert "live_trading_disabled" in decision.reasons


# ---------------------------------------------------------------------------
# Issue #7 semantic lock #5: ALT_RISK_OFF -> ALLOW_SCOUT no attack
# ---------------------------------------------------------------------------
def test_alt_risk_off_allow_scout_blocks_attack():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            regime_snapshot=_regime(
                RiskPermission.ALLOW_SCOUT, MarketRegime.ALT_RISK_OFF
            ),
            trade_confirmation_level=TradeConfirmationLevel.T4,
            manipulation_level=ManipulationLevel.M0,
        )
    )
    assert decision.rejected
    assert "regime_scout_only_for_attack" in decision.reasons


def test_alt_risk_off_allow_scout_permits_observe():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="observe",
            symbol="PEPEUSDT",
            attack_intent=False,
            regime_snapshot=_regime(
                RiskPermission.ALLOW_SCOUT, MarketRegime.ALT_RISK_OFF
            ),
            trade_confirmation_level=TradeConfirmationLevel.T2,
            manipulation_level=ManipulationLevel.M0,
        )
    )
    assert decision.approved


# ---------------------------------------------------------------------------
# Issue #7 semantic lock #6: SYSTEMIC_RISK overrides single-symbol strength
# ---------------------------------------------------------------------------
def test_systemic_risk_overrides_strong_individual_signal():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            regime_snapshot=_regime(
                RiskPermission.BLOCK_ALL, MarketRegime.SYSTEMIC_RISK
            ),
            trade_confirmation_level=TradeConfirmationLevel.T4,
            manipulation_level=ManipulationLevel.M0,
        )
    )
    assert decision.rejected
    assert "regime_block_all" in decision.reasons


# ---------------------------------------------------------------------------
# Acceptance criterion 9: DATA_DEGRADED rejects new openings
# ---------------------------------------------------------------------------
def test_data_degraded_rejects_new_open():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            is_data_degraded=True,
        )
    )
    assert decision.rejected
    assert "data_degraded" in decision.reasons


def test_data_degraded_does_not_block_protective_exit():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="execution_fsm",
            action="lock_profit",
            symbol="PEPEUSDT",
            attack_intent=False,
            is_new_open=False,
            is_data_degraded=True,
        )
    )
    assert decision.approved


# ---------------------------------------------------------------------------
# Phase 7 protective-exit caveat: M3 must NOT block reduce-only flows
# ---------------------------------------------------------------------------
def test_m3_does_not_block_protective_exit_when_is_new_open_false():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="execution_fsm",
            action="forced_exit",
            symbol="PEPEUSDT",
            is_new_open=False,
            attack_intent=False,
            manipulation_level=ManipulationLevel.M3,
        )
    )
    assert decision.approved
    assert "manipulation_m3" not in decision.reasons


# ---------------------------------------------------------------------------
# Acceptance criterion 12: 5 consecutive losses pause new opens
# ---------------------------------------------------------------------------
def test_consecutive_loss_breaker_blocks_new_open(events_repo):
    engine = RiskEngine(event_repo=events_repo)
    for _ in range(5):
        engine.record_loss(loss_amount=0.0)
    assert engine.consecutive_loss_breaker.state.is_open
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="observe",
            symbol="PEPEUSDT",
        )
    )
    assert decision.rejected
    assert "consecutive_loss_breaker_open" in decision.reasons


# ---------------------------------------------------------------------------
# Acceptance criterion 13: daily loss threshold pauses new opens
# ---------------------------------------------------------------------------
def test_daily_loss_breaker_blocks_new_open():
    engine = RiskEngine()
    engine.configure_initial_capital(initial_capital=1_000.0)
    # 6% drop -> open.
    engine.record_loss(loss_amount=60.0)
    assert engine.daily_loss_breaker.state is CircuitBreakerState.OPEN_DAILY_LOSS
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
        )
    )
    assert decision.rejected
    assert "daily_loss_breaker_open" in decision.reasons


# ---------------------------------------------------------------------------
# Account Tier policy
# ---------------------------------------------------------------------------
def test_account_tier_f_halts_new_open():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="observe",
            symbol="PEPEUSDT",
            account_tier_override=AccountLifeTier.F,
        )
    )
    assert decision.rejected
    assert "account_tier_halt" in decision.reasons
    assert "account_tier_no_new_open" in decision.reasons


def test_account_tier_e_blocks_new_open_but_allows_protective_exit():
    engine = RiskEngine()
    open_decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="observe",
            symbol="PEPEUSDT",
            account_tier_override=AccountLifeTier.E,
        )
    )
    assert open_decision.rejected
    assert "account_tier_no_new_open" in open_decision.reasons
    exit_decision = engine.evaluate(
        RiskRequest(
            source_module="execution_fsm",
            action="lock_profit",
            symbol="PEPEUSDT",
            is_new_open=False,
            account_tier_override=AccountLifeTier.E,
        )
    )
    assert exit_decision.approved


def test_account_tier_d_blocks_right_tail_amplify():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="amplify",
            symbol="PEPEUSDT",
            attack_intent=True,
            right_tail_amplify=True,
            account_tier_override=AccountLifeTier.D,
        )
    )
    assert decision.rejected
    # Phase 1 right_tail_disabled fires too.
    assert "right_tail_disabled" in decision.reasons
    assert "account_tier_no_right_tail" in decision.reasons


def test_account_tier_a_does_not_add_extra_rejections():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="observe",
            symbol="PEPEUSDT",
            account_tier_override=AccountLifeTier.A,
        )
    )
    assert decision.approved
    assert decision.account_tier is AccountLifeTier.A


# ---------------------------------------------------------------------------
# Audit event payload
# ---------------------------------------------------------------------------
def test_audit_payload_includes_phase7_fields(events_repo):
    """Issue #7 acceptance criterion 15: rejected events must carry
    typed reason_tags and surface every Phase 7 input."""
    engine = RiskEngine(event_repo=events_repo)
    engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            regime_snapshot=_regime(RiskPermission.ALLOW_ATTACK),
            trade_confirmation_level=TradeConfirmationLevel.T3,
            manipulation_level=ManipulationLevel.M0,
            is_data_degraded=False,
            exchange_connection_state=ExchangeConnectionState.CONNECTED,
            current_equity=140.0,
            initial_capital=100.0,
        )
    )
    [event] = events_repo.list(event_type=EventType.RISK_APPROVED)
    payload = event.payload
    assert payload["account_tier"] == "B"
    assert payload["regime"] == MarketRegime.MEME_RISK_ON.value
    assert payload["risk_permission"] == RiskPermission.ALLOW_ATTACK.value
    assert payload["is_new_open"] is True
    assert payload["exchange_connection_state"] == "connected"
    assert payload["daily_loss_breaker_state"] == "closed"
    assert payload["consecutive_loss_breaker_state"] == "closed"
    assert isinstance(payload["no_trade_gate_reasons"], list)


# ---------------------------------------------------------------------------
# Phase 1 + Phase 6 + Phase 7 reasons compose deterministically
# ---------------------------------------------------------------------------
def test_phase_one_six_seven_reasons_accumulate():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            live_trading_required=True,
            stop_unconfirmed=True,
            unknown_position=True,
            is_data_degraded=True,
            regime_snapshot=_regime(
                RiskPermission.BLOCK_ALL, MarketRegime.SYSTEMIC_RISK
            ),
            manipulation_level=ManipulationLevel.M3,
            trade_confirmation_level=TradeConfirmationLevel.T0,
            account_tier_override=AccountLifeTier.F,
            exchange_connection_state=ExchangeConnectionState.DISCONNECTED,
        )
    )
    assert decision.rejected
    expected = {
        "live_trading_disabled",
        "stop_unconfirmed",
        "unknown_position",
        "manipulation_m3",
        "trade_confirmation_too_low_for_attack",
        "regime_block_all",
        "data_degraded",
        "exchange_disconnected",
        "account_tier_halt",
        "account_tier_no_new_open",
    }
    assert expected.issubset(set(decision.reasons))


# ---------------------------------------------------------------------------
# Issue #7 acceptance criterion 11: unknown_position rejected
# ---------------------------------------------------------------------------
def test_unknown_position_rejected_for_new_open():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="reconciliation",
            action="open",
            symbol="PEPEUSDT",
            unknown_position=True,
        )
    )
    assert decision.rejected
    assert "unknown_position" in decision.reasons


def test_universe_ineligible_rejects_new_open():
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            universe_decision=UniverseDecision(
                symbol="PEPEUSDT",
                eligible=False,
                reject_reasons=(UniverseRejectReason.SPREAD_TOO_WIDE,),
            ),
        )
    )
    assert decision.rejected
    assert "universe_ineligible" in decision.reasons


def test_legacy_phase1_request_still_approved():
    """Phase 1 / Phase 6 callers that don't pass the new fields keep
    working unchanged (Phase 7 is additive)."""
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(source_module="legacy", action="self_check")
    )
    assert decision.approved
    assert decision.reasons == ["paper_only_skeleton_approval"]




# ===========================================================================
# Issue #7 review fix: conservative throughput discount
# ===========================================================================
from app.liquidity.models import Side  # noqa: E402  (local import for clarity)
from app.risk.no_trade_gate import NoTradeGateInput, evaluate_no_trade_gate  # noqa: E402


def _feasible_exit_plan(*, exit_seconds: float = 30.0) -> ExitPlan:
    """Build a Phase 5 :class:`ExitPlan` whose raw view is feasible.

    Used by the Issue #7 review-fix tests: the raw plan is feasible
    (Phase 5 thinks the position can be flattened in
    ``exit_seconds`` seconds at <= max_slippage_pct), but the Phase 7
    Risk Engine must STILL refuse when the discounted re-check
    fails.
    """
    return ExitPlan(
        symbol="PEPEUSDT",
        side=Side.LONG,
        qty=1.0,
        feasible=True,
        estimated_slippage_pct=0.001,
        estimated_exit_seconds=exit_seconds,
        cleared_qty=1.0,
        weighted_avg_fill_price=100.0,
        reject_reasons=(),
    )


def test_throughput_safety_factor_default_is_one_half():
    """Issue #7 review fix: the engine must default to a conservative
    throughput discount of 0.5."""
    engine = RiskEngine()
    assert engine.throughput_safety_factor == 0.5


def test_throughput_safety_factor_invalid_rejected():
    import pytest

    with pytest.raises(ValueError):
        RiskEngine(throughput_safety_factor=0.0)
    with pytest.raises(ValueError):
        RiskEngine(throughput_safety_factor=-0.1)
    with pytest.raises(ValueError):
        RiskEngine(throughput_safety_factor=1.5)


def test_raw_feasible_plan_rejected_when_discounted_exceeds_ceiling():
    """Issue #7 review fix: raw can_exit_position is feasible, but
    after the conservative throughput discount it would exceed the
    configured exit-time ceiling. The Risk Engine MUST reject the
    attack candidate."""
    engine = RiskEngine()
    # Raw plan is 40s; max_exit_seconds is 60s -> raw passes.
    # With safety_factor=0.5 the discounted estimate is 80s -> reject.
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            exit_plan=_feasible_exit_plan(exit_seconds=40.0),
            max_exit_seconds=60.0,
        )
    )
    assert decision.rejected
    assert "liquidity_throughput_insufficient" in decision.reasons


def test_raw_feasible_plan_passes_when_discounted_under_ceiling():
    """Sanity: when the discounted estimate is comfortably under the
    ceiling, no rejection fires from the new gate."""
    engine = RiskEngine()
    # 10s raw, doubled = 20s. Ceiling 60s -> approved.
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            exit_plan=_feasible_exit_plan(exit_seconds=10.0),
            max_exit_seconds=60.0,
            regime_snapshot=_regime(RiskPermission.ALLOW_ATTACK),
            trade_confirmation_level=TradeConfirmationLevel.T3,
            manipulation_level=ManipulationLevel.M0,
        )
    )
    assert decision.approved
    assert "liquidity_throughput_insufficient" not in decision.reasons


def test_data_degraded_blocks_even_when_raw_plan_is_feasible():
    """Issue #7 review fix: degraded=True must keep the engine from
    approving a new opening even if the raw can_exit_position plan
    looks feasible. DATA_DEGRADED fires regardless of the discount."""
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            is_data_degraded=True,
            exit_plan=_feasible_exit_plan(exit_seconds=10.0),
            max_exit_seconds=60.0,
        )
    )
    assert decision.rejected
    assert "data_degraded" in decision.reasons


def test_no_trade_gate_throughput_discount_directly():
    """Driving evaluate_no_trade_gate directly so the discount logic
    is also pinned at the gate level (the engine adds Phase 1 / Phase
    6 reasons on top, which can mask the gate result in the
    higher-level test)."""
    decision = evaluate_no_trade_gate(
        NoTradeGateInput(
            symbol="PEPEUSDT",
            attack_intent=True,
            exit_plan=_feasible_exit_plan(exit_seconds=40.0),
            max_exit_seconds=60.0,
            throughput_safety_factor=0.5,
        )
    )
    assert not decision.allowed
    from app.core.enums import RiskRejectReason as _RR  # local import

    assert _RR.LIQUIDITY_THROUGHPUT_INSUFFICIENT in decision.reasons


def test_per_request_safety_factor_override_honoured():
    """The default factor is 0.5 but a per-request override is
    honoured. With factor=1.0 (no discount), a 40s raw plan against
    a 60s ceiling MUST pass."""
    engine = RiskEngine()
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            exit_plan=_feasible_exit_plan(exit_seconds=40.0),
            max_exit_seconds=60.0,
            throughput_safety_factor=1.0,  # no discount
            regime_snapshot=_regime(RiskPermission.ALLOW_ATTACK),
            trade_confirmation_level=TradeConfirmationLevel.T3,
            manipulation_level=ManipulationLevel.M0,
        )
    )
    assert decision.approved


def test_engine_level_safety_factor_override_honoured():
    """A loose engine-level factor (e.g. 0.9) is also honoured."""
    engine = RiskEngine(throughput_safety_factor=0.9)
    assert engine.throughput_safety_factor == 0.9
    # 40s / 0.9 ~ 44.4s, still under 60s -> approved.
    decision = engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="open_attack",
            symbol="PEPEUSDT",
            attack_intent=True,
            exit_plan=_feasible_exit_plan(exit_seconds=40.0),
            max_exit_seconds=60.0,
            regime_snapshot=_regime(RiskPermission.ALLOW_ATTACK),
            trade_confirmation_level=TradeConfirmationLevel.T3,
            manipulation_level=ManipulationLevel.M0,
        )
    )
    assert decision.approved


def test_audit_payload_includes_throughput_safety_factor(events_repo):
    """Reflection (Issue #10) must be able to read the safety factor
    that was applied for any historic decision."""
    engine = RiskEngine(event_repo=events_repo)
    engine.evaluate(
        RiskRequest(
            source_module="strategy",
            action="probe",
            symbol="PEPEUSDT",
            attack_intent=False,
        )
    )
    [event] = events_repo.list(event_type=EventType.RISK_APPROVED)
    assert event.payload["throughput_safety_factor"] == 0.5
