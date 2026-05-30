"""PR110 - Live Foundation v0 unit tests.

Covers the 24 brief-mandated cases for:
  - Live Path Isolation
  - Runtime Mode Guard (LIVE_SHADOW / LIVE_LIMITED)
  - Capital Profile Ladder
  - Capital Event Contract
  - Right-tail Leverage Gate
  - Telegram Operator Contract
  - Safety-flag invariants

PR110 is a live-preparation safety foundation: no live trading, no
private Binance API, no real orders, no Telegram outbound.
"""

from __future__ import annotations

import pytest

from app.config.schema import LiveConfig
from app.config.settings import get_settings, load_settings
from app.core.enums import Direction, LiveRuntimeMode, MarketRegime, OrderSource
from app.core.errors import (
    LiveModeViolation,
    LivePathIsolationViolation,
    SafeModeViolation,
)
from app.core.events import EventType
from app.live.capital_event import (
    CapitalEventCategory,
    CapitalEventLedger,
    CapitalEventType,
    LiveCapitalEvent,
    classify_capital_event,
)
from app.live.capital_profile import (
    AUTO_ESCALATION_ALLOWED,
    CapitalProfileId,
    build_profile_change_request,
    detect_profile_mismatch,
    get_profile,
)
from app.live.gateway import LiveExecutionGateway
from app.live.leverage_gate import (
    LeverageDecision,
    RightTailLeverageEvidence,
    RightTailLeverageReason,
    evaluate_right_tail_leverage_permission,
)
from app.live.path_isolation import (
    LiveOrderIntent,
    LivePathIsolationGuard,
    classify_source_module,
)
from app.live.runtime_mode import LiveModeGuard, LiveModeState
from app.live.telegram_operator_contract import (
    LIVE_EXECUTION_ADAPTER_AVAILABLE,
    OperatorCardType,
    build_operator_card,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------
class _FakeRepo:
    """Minimal EventRepository stand-in capturing appended events."""

    def __init__(self) -> None:
        self.events: list = []

    def append(self, event) -> None:
        self.events.append(event)

    def types(self) -> list:
        return [e.event_type for e in self.events]


def _settings():
    get_settings.cache_clear()
    return load_settings()


def _good_leverage_evidence(**overrides) -> RightTailLeverageEvidence:
    """A leverage-evidence bundle that grants a boost unless overridden."""
    base = dict(
        capital_profile_id=CapitalProfileId.L1_10U_PROBE,
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
        market_regime=MarketRegime.MEME_RISK_ON,
        systemic_risk_state=False,
        risk_halt_state=False,
        candidate_stage="early",
        opportunity_score=0.9,
        liquidity_score=0.8,
        spread_bps=10.0,
        estimated_slippage_bps=10.0,
        volume_expansion_score=0.9,
        volatility_state="expanding",
        current_drawdown=0.0,
        floating_profit_state=5.0,
        exit_plan_present=True,
        stop_plan_present=True,
        take_profit_plan_present=True,
        symbol_exposure=0.5,
        account_exposure=0.5,
        oi_expansion_score=0.9,
        breakout_structure_score=0.9,
        requested_boost=True,
        requested_leverage=None,
    )
    base.update(overrides)
    return RightTailLeverageEvidence(**base)


# ---------------------------------------------------------------------------
# Runtime Mode Guard
# ---------------------------------------------------------------------------
def test_01_default_runtime_mode_is_live_shadow():
    guard = LiveModeGuard()
    assert guard.runtime_mode is LiveRuntimeMode.LIVE_SHADOW
    # Config default also LIVE_SHADOW.
    assert _settings().live_runtime_mode == "LIVE_SHADOW"


def test_02_live_shadow_rejects_all_real_order_attempts():
    guard = LiveModeGuard()
    with pytest.raises(LiveModeViolation):
        guard.assert_live_orders_allowed()
    # And through the gateway with a LIVE-sourced intent.
    isolation = LivePathIsolationGuard()
    gateway = LiveExecutionGateway(isolation_guard=isolation, mode_guard=guard)
    intent = LiveOrderIntent(
        source=OrderSource.LIVE,
        source_module="FutureLiveAdapter",
        symbol="BTCUSDT",
        side=Direction.LONG,
        notional_usdt=5.0,
    )
    with pytest.raises(LiveModeViolation):
        gateway.submit_order(intent)


def test_03_live_limited_cannot_be_enabled_without_confirmation_state():
    # Profile that allows real orders + kill switch armed, but NO handshake.
    state = LiveModeState(capital_profile_id=CapitalProfileId.L1_10U_PROBE)
    guard = LiveModeGuard(state=state)
    guard.arm_kill_switch()
    # Without request/confirm, the guard is not armed.
    assert guard.is_live_limited_armed is False
    with pytest.raises(LiveModeViolation):
        guard.assert_live_orders_allowed()
    # A confirm with a bogus code (no pending request) is rejected.
    result = guard.confirm_live("LIVE-BOGUS")
    assert result.success is False
    assert guard.runtime_mode is LiveRuntimeMode.LIVE_SHADOW
    assert guard.is_live_limited_armed is False


def test_03b_full_handshake_arms_live_limited():
    state = LiveModeState(capital_profile_id=CapitalProfileId.L1_10U_PROBE)
    repo = _FakeRepo()
    guard = LiveModeGuard(state=state, event_repo=repo)
    guard.arm_kill_switch()
    summary = guard.request_live_limited(account_equity_usdt=10.0)
    assert summary.confirmation_code.startswith("LIVE-")
    result = guard.confirm_live(summary.confirmation_code)
    assert result.success is True
    assert guard.runtime_mode is LiveRuntimeMode.LIVE_LIMITED
    assert guard.is_live_limited_armed is True
    guard.assert_live_orders_allowed()  # does not raise
    assert EventType.LIVE_LIMITED_ARMED in repo.types()
    assert EventType.LIVE_MODE_SWITCH_CONFIRMED in repo.types()


def test_03c_confirm_rejected_without_armed_kill_switch():
    state = LiveModeState(capital_profile_id=CapitalProfileId.L1_10U_PROBE)
    guard = LiveModeGuard(state=state)
    summary = guard.request_live_limited(account_equity_usdt=10.0)
    result = guard.confirm_live(summary.confirmation_code)
    assert result.success is False
    assert "kill_switch_not_armed" in result.reject_reasons
    assert guard.runtime_mode is LiveRuntimeMode.LIVE_SHADOW


def test_04_restart_or_default_config_cannot_silently_enter_live_limited():
    # Even a config that *says* LIVE_LIMITED + confirmation_state True +
    # kill switch armed must boot in LIVE_SHADOW.
    cfg = LiveConfig(
        runtime_mode="LIVE_LIMITED",
        capital_profile_id="L1_10U_PROBE",
        live_limited_confirmation_state=True,
        kill_switch_armed=True,
    )
    guard = LiveModeGuard.from_config(cfg)
    assert guard.runtime_mode is LiveRuntimeMode.LIVE_SHADOW
    assert guard.is_live_limited_armed is False
    with pytest.raises(LiveModeViolation):
        guard.assert_live_orders_allowed()


# ---------------------------------------------------------------------------
# Capital Profile Ladder
# ---------------------------------------------------------------------------
def test_05_l0_shadow_real_orders_not_allowed():
    profile = get_profile(CapitalProfileId.L0_SHADOW)
    assert profile.real_orders_allowed is False
    assert profile.check_order_notional(5.0) is False


def test_06_l1_10u_probe_max_account_capital_le_10():
    profile = get_profile(CapitalProfileId.L1_10U_PROBE)
    assert profile.max_account_capital_usdt <= 10.0


def test_07_l1_10u_probe_rejects_order_notional_above_max():
    profile = get_profile(CapitalProfileId.L1_10U_PROBE)
    too_big = profile.max_position_notional_usdt + 1000.0
    assert profile.check_order_notional(too_big) is False
    assert (
        profile.reject_reason_for_notional(too_big)
        == "order_notional_exceeds_profile_max"
    )
    # A within-limit notional is accepted.
    assert profile.check_order_notional(profile.max_position_notional_usdt) is True


def test_08_capital_profile_escalation_is_not_automatic():
    assert AUTO_ESCALATION_ALLOWED is False
    req = build_profile_change_request(
        CapitalProfileId.L1_10U_PROBE,
        CapitalProfileId.L2_25U_50U_SCOUT,
        requested_by="operator",
    )
    assert req.is_escalation is True
    assert req.requires_operator_ack is True


def test_09_profile_mismatch_detected_when_equity_exceeds_range():
    mismatch = detect_profile_mismatch(CapitalProfileId.L1_10U_PROBE, 10_000.0)
    assert mismatch.mismatch is True
    assert mismatch.direction == "escalate"
    assert mismatch.requires_operator_action is True
    assert mismatch.suggested_profile_id is not CapitalProfileId.L1_10U_PROBE
    # In-band equity is not a mismatch.
    ok = detect_profile_mismatch(CapitalProfileId.L1_10U_PROBE, 10.0)
    assert ok.mismatch is False


# ---------------------------------------------------------------------------
# Capital Event Contract
# ---------------------------------------------------------------------------
def test_10_deposit_does_not_count_as_trading_pnl():
    ledger = CapitalEventLedger(initial_capital_usdt=10.0, current_balance_usdt=10.0)
    deposit = LiveCapitalEvent.create(
        event_type=CapitalEventType.EXTERNAL_DEPOSIT,
        amount_usdt=9_990.0,
        balance_before=10.0,
    )
    assert deposit.is_trading_pnl is False
    assert deposit.is_external_capital_flow is True
    assert deposit.trading_pnl_contribution == 0.0
    ledger.apply(deposit)
    assert ledger.total_realized_pnl == 0.0
    assert ledger.total_external_deposits == 9_990.0
    assert ledger.net_strategy_pnl == 0.0


def test_11_withdrawal_does_not_count_as_trading_loss():
    ledger = CapitalEventLedger(initial_capital_usdt=100.0, current_balance_usdt=100.0)
    withdrawal = LiveCapitalEvent.create(
        event_type=CapitalEventType.EXTERNAL_WITHDRAWAL,
        amount_usdt=40.0,
        balance_before=100.0,
    )
    assert withdrawal.is_trading_pnl is False
    assert withdrawal.trading_pnl_contribution == 0.0
    ledger.apply(withdrawal)
    assert ledger.total_realized_pnl == 0.0
    assert ledger.total_external_withdrawals == 40.0
    # A withdrawal must not show up as a negative strategy PnL.
    assert ledger.net_strategy_pnl == 0.0


def test_12_fee_and_funding_events_classified_separately():
    fee_cls = classify_capital_event(CapitalEventType.FEE)
    assert fee_cls.category is CapitalEventCategory.FEE_FUNDING
    assert fee_cls.is_trading_pnl is False
    assert fee_cls.is_fee_or_funding is True

    funding_fee_cls = classify_capital_event(CapitalEventType.FUNDING_FEE)
    funding_income_cls = classify_capital_event(CapitalEventType.FUNDING_INCOME)
    assert funding_fee_cls.category is CapitalEventCategory.FEE_FUNDING
    assert funding_income_cls.category is CapitalEventCategory.FEE_FUNDING

    # And they accumulate in their own buckets, not in realized PnL.
    ledger = CapitalEventLedger(current_balance_usdt=100.0)
    ledger.apply(
        LiveCapitalEvent.create(
            event_type=CapitalEventType.REALIZED_PNL, amount_usdt=20.0, balance_before=100.0
        )
    )
    ledger.apply(
        LiveCapitalEvent.create(
            event_type=CapitalEventType.FEE, amount_usdt=1.0, balance_before=120.0
        )
    )
    ledger.apply(
        LiveCapitalEvent.create(
            event_type=CapitalEventType.FUNDING_INCOME, amount_usdt=2.0, balance_before=119.0
        )
    )
    assert ledger.total_realized_pnl == 20.0
    assert ledger.total_fees == 1.0
    assert ledger.total_funding == 2.0


# ---------------------------------------------------------------------------
# Right-tail Leverage Gate
# ---------------------------------------------------------------------------
def test_13_leverage_gate_rejects_ai_input():
    # A mapping carrying an AI-shaped field is refused outright.
    decision = evaluate_right_tail_leverage_permission(
        {
            "capital_profile_id": "L1_10U_PROBE",
            "runtime_mode": "LIVE_LIMITED",
            "market_regime": "MEME_RISK_ON",
            "exit_plan_present": True,
            "stop_plan_present": True,
            "take_profit_plan_present": True,
            "liquidity_score": 0.8,
            "floating_profit_state": 5.0,
            "ai_recommendation": "max leverage now",
        }
    )
    assert decision.leverage_allowed is False
    assert decision.ai_input_detected is True
    assert decision.reject_reason == RightTailLeverageReason.AI_INPUT_FORBIDDEN


def test_14_leverage_gate_rejects_no_exit_plan():
    decision = evaluate_right_tail_leverage_permission(
        _good_leverage_evidence(exit_plan_present=False)
    )
    assert decision.leverage_allowed is False
    assert RightTailLeverageReason.NO_EXIT_PLAN in decision.reject_reasons


def test_15_leverage_gate_rejects_no_stop_plan():
    decision = evaluate_right_tail_leverage_permission(
        _good_leverage_evidence(stop_plan_present=False)
    )
    assert decision.leverage_allowed is False
    assert RightTailLeverageReason.NO_STOP_PLAN in decision.reject_reasons


def test_16_leverage_gate_rejects_risk_off_regime():
    decision = evaluate_right_tail_leverage_permission(
        _good_leverage_evidence(market_regime=MarketRegime.ALT_RISK_OFF)
    )
    assert decision.leverage_allowed is False
    assert RightTailLeverageReason.REGIME_RISK_OFF in decision.reject_reasons


def test_17_leverage_gate_rejects_drawdown_or_risk_halt():
    # Risk halt active.
    halt = evaluate_right_tail_leverage_permission(
        _good_leverage_evidence(risk_halt_state=True)
    )
    assert halt.leverage_allowed is False
    assert RightTailLeverageReason.RISK_HALT_ACTIVE in halt.reject_reasons
    # Drawdown warning (>= 0.6 * kill_switch_drawdown_pct of 0.5 => >= 0.3).
    drawdown = evaluate_right_tail_leverage_permission(
        _good_leverage_evidence(current_drawdown=0.4)
    )
    assert drawdown.leverage_allowed is False
    assert RightTailLeverageReason.ACCOUNT_DRAWDOWN_WARNING in drawdown.reject_reasons


def test_18_leverage_gate_rejects_if_profile_disallows_boost():
    # L6 forbids right-tail boost; supply otherwise-strong evidence.
    decision = evaluate_right_tail_leverage_permission(
        _good_leverage_evidence(
            capital_profile_id=CapitalProfileId.L6_100K_LIQUIDITY_CONSTRAINED,
            liquidity_score=0.95,
            spread_bps=2.0,
            estimated_slippage_bps=2.0,
            symbol_exposure=0.05,
        )
    )
    assert decision.leverage_allowed is False
    assert RightTailLeverageReason.PROFILE_DISALLOWS_BOOST in decision.reject_reasons


def test_18b_leverage_gate_rejects_no_floating_profit_for_boost():
    decision = evaluate_right_tail_leverage_permission(
        _good_leverage_evidence(floating_profit_state=0.0)
    )
    assert decision.leverage_allowed is False
    assert (
        RightTailLeverageReason.NO_FLOATING_PROFIT_FOR_BOOST in decision.reject_reasons
    )


def test_19_leverage_gate_grants_limited_leverage_with_deterministic_evidence():
    decision = evaluate_right_tail_leverage_permission(_good_leverage_evidence())
    assert isinstance(decision, LeverageDecision)
    assert decision.leverage_allowed is True
    profile = get_profile(CapitalProfileId.L1_10U_PROBE)
    # Granted leverage is a real boost above base, capped at the profile's
    # right-tail max.
    assert decision.leverage_ratio > profile.base_leverage
    assert decision.leverage_ratio <= profile.right_tail_max_leverage
    assert decision.max_allowed_leverage == profile.right_tail_max_leverage
    assert decision.requires_operator_ack is True
    assert decision.reject_reason is None


# ---------------------------------------------------------------------------
# Live Path Isolation
# ---------------------------------------------------------------------------
def test_20_isolation_blocks_mock_exchange_from_live_order_submission():
    repo = _FakeRepo()
    guard = LivePathIsolationGuard(event_repo=repo)
    intent = LiveOrderIntent.from_module(
        source_module="MockExchangeClient",
        symbol="BTCUSDT",
        side=Direction.LONG,
        notional_usdt=5.0,
    )
    assert intent.source is OrderSource.SIM
    decision = guard.authorize(intent)
    assert decision.authorised is False
    with pytest.raises(LivePathIsolationViolation):
        guard.assert_live_path(intent)
    assert EventType.LIVE_PATH_BLOCKED in repo.types()


def test_21_isolation_blocks_blind_and_paper_shadow_sources():
    guard = LivePathIsolationGuard()
    for module, expected in (
        ("BlindWalkForwardRunner", OrderSource.BLIND),
        ("ReplayFeedProvider", OrderSource.REPLAY),
        ("PaperShadowStrategyBridge", OrderSource.PAPER_SHADOW),
        ("SimulatedCapitalFlowEngine", OrderSource.SIM),
    ):
        assert classify_source_module(module) is expected
        intent = LiveOrderIntent.from_module(
            source_module=module, symbol="ETHUSDT", side=Direction.LONG
        )
        assert guard.authorize(intent).authorised is False
        with pytest.raises(LivePathIsolationViolation):
            guard.assert_live_path(intent)
    # An unknown module fails safe to a blocked source (never LIVE).
    assert classify_source_module("SomethingNew") is OrderSource.SIM


def test_21b_gateway_refuses_even_a_live_sourced_armed_submission():
    """A LIVE source + armed LIVE_LIMITED still cannot place a real order
    in PR110 (no execution adapter)."""
    state = LiveModeState(capital_profile_id=CapitalProfileId.L1_10U_PROBE)
    mode_guard = LiveModeGuard(state=state)
    mode_guard.arm_kill_switch()
    summary = mode_guard.request_live_limited(account_equity_usdt=10.0)
    mode_guard.confirm_live(summary.confirmation_code)
    isolation = LivePathIsolationGuard()
    gateway = LiveExecutionGateway(isolation_guard=isolation, mode_guard=mode_guard)
    intent = LiveOrderIntent(
        source=OrderSource.LIVE,
        source_module="FutureLiveAdapter",
        symbol="BTCUSDT",
        side=Direction.LONG,
        notional_usdt=5.0,
    )
    with pytest.raises(SafeModeViolation):
        gateway.submit_order(intent)


# ---------------------------------------------------------------------------
# Telegram Operator Contract
# ---------------------------------------------------------------------------
def test_22_shadow_card_shows_planned_but_real_order_false_and_order_id_dash():
    card = build_operator_card(
        OperatorCardType.SHADOW_ENTRY_PLAN,
        {
            "symbol": "PEPEUSDT",
            "side": "long",
            "planned_entry_zone": "0.0000100-0.0000105",
            "planned_entry_price": 0.0000102,
            "planned_stop_price": 0.0000095,
            "planned_take_profit_1": 0.0000130,
            "planned_leverage": 5,
            "real_order": True,  # must be ignored on a shadow card
            "fill_price": 0.0000102,
        },
    )
    assert card["real_order"] is False
    assert card["real_capital_changed"] is False
    assert card["order_id"] == "--"
    assert card["fill_price"] == "--"
    # Planned fields ARE shown.
    assert card["planned_entry_price"] == 0.0000102
    assert card["planned_stop_price"] == 0.0000095
    assert card["planned_take_profit_1"] == 0.0000130
    assert card["mode_display"] == "空盘跑"


def test_23_live_card_schema_includes_entry_exit_pnl_balance_fields():
    card = build_operator_card(
        OperatorCardType.LIVE_EXIT_FILLED,
        {
            "symbol": "BTCUSDT",
            "side": "long",
            "entry_price": 60000.0,
            "exit_price": 63000.0,
            "realized_pnl_usdt": 30.0,
            "pnl_pct": 0.05,
            "balance_before": 100.0,
            "balance_after": 130.0,
            "equity_after": 130.0,
            "order_id": "abc123",
            "real_order": True,
        },
    )
    for fld in (
        "entry_price",
        "exit_price",
        "realized_pnl_usdt",
        "pnl_pct",
        "balance_before",
        "balance_after",
        "equity_after",
    ):
        assert fld in card, f"live card schema missing {fld}"
    assert card["entry_price"] == 60000.0
    assert card["exit_price"] == 63000.0
    # PR110: no execution adapter, so real_order is still forced False.
    assert LIVE_EXECUTION_ADAPTER_AVAILABLE is False
    assert card["real_order"] is False
    assert card["mode_display"] == "有资金跑"


# ---------------------------------------------------------------------------
# Safety-flag invariants
# ---------------------------------------------------------------------------
def test_24_safety_flags_remain_false_or_forbidden():
    s = _settings()
    # Phase 1 flags.
    assert s.trading_mode == "paper"
    assert s.live_trading_enabled is False
    assert s.right_tail_enabled is False
    assert s.llm_enabled is False
    assert s.exchange_live_order_enabled is False
    assert s.telegram_outbound_enabled is False
    # PR110 live section.
    live = s.live
    assert live.live_trading is False
    assert live.exchange_live_orders is False
    assert live.binance_private_api_enabled is False
    assert live.ai_trade_authority is False
    assert live.trade_authority is False
    assert live.right_tail_live_boost_enabled is False
    assert live.phase_12_forbidden is True
    # No live execution adapter in PR110.
    assert LIVE_EXECUTION_ADAPTER_AVAILABLE is False


def test_24b_live_config_refuses_to_loosen_capability_flags():
    import pydantic

    for fld in (
        "live_trading",
        "exchange_live_orders",
        "binance_private_api_enabled",
        "ai_trade_authority",
        "trade_authority",
        "right_tail_live_boost_enabled",
    ):
        with pytest.raises(pydantic.ValidationError):
            LiveConfig(**{fld: True})
    with pytest.raises(pydantic.ValidationError):
        LiveConfig(phase_12_forbidden=False)
