"""PR112 - Live Capital / Risk / Funding-Aware PnL / 10U Profile Enforcement.

All tests use fake/mock Binance snapshots + income rows only. No network,
no real orders, no mode switching, no profile escalation.

The numbered tests map to the brief's "Tests Required" list (1..28); the
PR110/PR111-pass requirement (29) is satisfied by the full suite run.
"""

from __future__ import annotations

import pytest

from app.core.enums import LiveRuntimeMode, OrderSource
from app.live.binance_income import classify_income_rows
from app.live.binance_models import parse_account
from app.live.capital_profile import CapitalProfileId, get_profile
from app.live.capital_state import LiveCapitalState
from app.live.leverage_gate import LeverageDecision
from app.live.live_capital_service import (
    LiveCapitalService,
    build_capital_profile_mismatch_payload,
    build_live_account_status_payload,
    build_live_pnl_summary_payload,
    build_live_risk_reject_payload,
)
from app.live.live_risk_engine import (
    CapitalProfileStatus,
    LiveOrderIntent,
    LiveRiskRejectReason,
    evaluate_capital_profile_state,
    evaluate_live_order_risk,
)
from app.live.pnl_accounting import (
    FundingAttributionStatus,
    build_live_pnl_summary,
)

L1 = CapitalProfileId.L1_10U_PROBE


# ---------------------------------------------------------------------------
# Account snapshot fixtures
# ---------------------------------------------------------------------------
def _account(
    *,
    wallet="1000.5",
    margin="1012.75",
    available="950.0",
    unrealized="12.25",
    positions=None,
):
    if positions is None:
        positions = [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.010",
                "entryPrice": "60000",
                "unrealizedProfit": "12.25",
                "leverage": "5",
                "marginType": "isolated",
                "positionSide": "BOTH",
            },
            {
                "symbol": "ETHUSDT",
                "positionAmt": "0",
                "entryPrice": "0",
                "unrealizedProfit": "0",
                "leverage": "10",
                "marginType": "cross",
                "positionSide": "BOTH",
            },
        ]
    return parse_account(
        {
            "totalWalletBalance": wallet,
            "totalUnrealizedProfit": unrealized,
            "totalMarginBalance": margin,
            "availableBalance": available,
            "feeTier": 0,
            "canTrade": True,
            "canDeposit": False,
            "canWithdraw": False,
            "assets": [
                {
                    "asset": "USDT",
                    "walletBalance": wallet,
                    "availableBalance": available,
                    "crossUnPnl": unrealized,
                }
            ],
            "positions": positions,
        },
        timestamp_ms=1700000000000,
    )


def _tiny_l1_state(equity="8.0", available="8.0", positions=None):
    """A funded L1_10U account well within band (equity in [5,25])."""
    return LiveCapitalState.from_account_snapshot(
        _account(wallet=equity, margin=equity, available=available, unrealized="0", positions=positions or []),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
        capital_profile_id=L1,
    )


SAMPLE_INCOME = [
    {"symbol": "BTCUSDT", "incomeType": "REALIZED_PNL", "income": "25.5", "asset": "USDT", "time": 1, "tradeId": "t1", "tranId": "1"},
    {"symbol": "BTCUSDT", "incomeType": "REALIZED_PNL", "income": "-10.0", "asset": "USDT", "time": 2, "tradeId": "t2", "tranId": "2"},
    {"symbol": "BTCUSDT", "incomeType": "COMMISSION", "income": "-0.5", "asset": "USDT", "time": 3, "tradeId": "t1", "tranId": "3"},
    {"symbol": "BTCUSDT", "incomeType": "FUNDING_FEE", "income": "-1.2", "asset": "USDT", "time": 4, "tranId": "4"},
    {"symbol": "BTCUSDT", "incomeType": "FUNDING_FEE", "income": "0.8", "asset": "USDT", "time": 5, "tranId": "5"},
    {"symbol": "", "incomeType": "TRANSFER", "income": "500", "asset": "USDT", "time": 6, "tranId": "6"},
    {"symbol": "", "incomeType": "TRANSFER", "income": "-200", "asset": "USDT", "time": 7, "tranId": "7"},
    {"symbol": "", "incomeType": "WELCOME_BONUS", "income": "100", "asset": "USDT", "time": 8, "tranId": "8"},
    {"symbol": "", "incomeType": "SOME_FUTURE_TYPE", "income": "3.3", "asset": "USDT", "time": 9, "tranId": "9"},
]


# ===========================================================================
# 1-3: LiveCapitalState construction
# ===========================================================================
def test_01_build_live_capital_state_from_snapshot():
    state = LiveCapitalState.from_account_snapshot(
        _account(), runtime_mode=LiveRuntimeMode.LIVE_SHADOW, capital_profile_id=L1
    )
    assert state.source == "BINANCE_PRIVATE_READ"
    assert state.is_real_account_snapshot is True
    assert state.runtime_mode is LiveRuntimeMode.LIVE_SHADOW
    assert state.capital_profile_id is L1
    # PR112 hard markers.
    assert state.real_orders_allowed is False
    assert state.exchange_live_orders is False


def test_02_open_positions_counted_correctly():
    state = LiveCapitalState.from_account_snapshot(_account())
    assert state.open_position_count == 1  # only BTCUSDT is open
    assert len(state.open_positions) == 1
    pos = state.open_positions[0]
    assert pos.symbol == "BTCUSDT"
    assert pos.side == "LONG"
    assert pos.isolated_or_cross == "isolated"
    assert pos.notional_usdt == pytest.approx(0.010 * 60000)


def test_03_available_balance_and_equity_parsed():
    state = LiveCapitalState.from_account_snapshot(_account())
    assert state.account_equity_usdt == pytest.approx(1012.75)
    assert state.available_balance_usdt == pytest.approx(950.0)
    assert state.free_margin_usdt == pytest.approx(950.0)
    assert state.used_margin_usdt == pytest.approx(62.75)
    assert state.unrealized_pnl_usdt == pytest.approx(12.25)


# ===========================================================================
# 4-11: Funding-aware PnL + external-flow separation
# ===========================================================================
def _summary():
    return build_live_pnl_summary(classify_income_rows(SAMPLE_INCOME), account_equity_usdt=1000.0)


def test_04_realized_pnl_maps_to_gross_realized():
    s = _summary()
    assert s.gross_realized_pnl_usdt == pytest.approx(15.5)  # 25.5 - 10.0


def test_05_commission_reduces_net_pnl():
    s = _summary()
    assert s.commission_total_usdt == pytest.approx(0.5)
    # net is reduced by the commission.
    assert s.net_strategy_pnl_usdt < s.gross_realized_pnl_usdt + s.funding_total_usdt


def test_06_funding_affects_funding_total():
    s = _summary()
    assert s.funding_total_usdt == pytest.approx(-0.4)  # -1.2 + 0.8


def test_07_deposit_and_transfer_in_not_strategy_pnl():
    s = _summary()
    assert s.external_deposit_total_usdt == pytest.approx(100.0)  # WELCOME_BONUS
    assert s.transfer_in_total_usdt == pytest.approx(500.0)
    # Neither deposit nor transfer-in enters net strategy pnl.
    assert s.net_strategy_pnl_usdt == pytest.approx(14.6)


def test_08_withdrawal_and_transfer_out_not_strategy_loss():
    s = _summary()
    assert s.transfer_out_total_usdt == pytest.approx(200.0)
    # The 200 transfer-out does NOT reduce strategy pnl.
    assert s.net_strategy_pnl_usdt == pytest.approx(14.6)
    # A direct external withdrawal event is also kept out of strategy pnl.
    wd_rows = [{"incomeType": "TRANSFER", "income": "-50", "asset": "USDT", "time": 1, "tranId": "x"}]
    wd = build_live_pnl_summary(classify_income_rows(wd_rows))
    assert wd.net_strategy_pnl_usdt == pytest.approx(0.0)
    assert wd.transfer_out_total_usdt == pytest.approx(50.0)


def test_09_unknown_income_preserved_separately():
    s = _summary()
    assert s.unknown_income_total_usdt == pytest.approx(3.3)
    assert s.unknown_income_count == 1
    # Unknown income never enters strategy pnl.
    assert s.net_strategy_pnl_usdt == pytest.approx(14.6)


def test_10_net_strategy_pnl_formula():
    s = _summary()
    # net = realized - commission + funding
    expected = s.gross_realized_pnl_usdt - s.commission_total_usdt + s.funding_total_usdt
    assert s.net_strategy_pnl_usdt == pytest.approx(expected)
    assert s.net_strategy_pnl_usdt == pytest.approx(14.6)


def test_11_funding_without_trade_id_unattributed():
    s = _summary()
    assert s.unattributed_funding_count == 2
    assert (
        s.funding_attribution_status
        == FundingAttributionStatus.UNATTRIBUTED_PENDING_POSITION_LINK
    )
    # Handoff marker present for PR113/PR114.
    assert "PR113" in s.funding_attribution_handoff


def test_pnl_performance_equity_excludes_external_flows():
    s = build_live_pnl_summary(classify_income_rows(SAMPLE_INCOME), account_equity_usdt=1000.0)
    # net external = deposit(100) - withdrawal(0) + transfer_in(500) - transfer_out(200) = 400
    assert s.net_external_capital_usdt == pytest.approx(400.0)
    assert s.adjusted_strategy_equity_usdt == pytest.approx(1000.0)
    assert s.performance_equity_excluding_external_flows == pytest.approx(600.0)


# ===========================================================================
# 12-14: L1_10U_PROBE capital profile enforcement
# ===========================================================================
def test_12_l1_caps_usable_capital_at_10u():
    state = LiveCapitalState.from_account_snapshot(
        _account(wallet="100", margin="100", available="100", unrealized="0", positions=[]),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
        capital_profile_id=L1,
    )
    ps = evaluate_capital_profile_state(state, L1)
    assert ps.usable_capital_usdt == pytest.approx(10.0)
    assert CapitalProfileStatus.ACCOUNT_CAPITAL_EXCEEDS_PROFILE_CAP in ps.flags


def test_13_equity_above_range_no_auto_upgrade():
    state = LiveCapitalState.from_account_snapshot(
        _account(wallet="100", margin="100", available="100", unrealized="0", positions=[]),
        capital_profile_id=L1,
    )
    ps = evaluate_capital_profile_state(state, L1)
    assert ps.profile_status == CapitalProfileStatus.PROFILE_MISMATCH_EQUITY_ABOVE_RANGE
    # The active profile did NOT change.
    assert ps.capital_profile_id is L1
    assert ps.auto_escalation_allowed is False
    assert ps.requires_operator_action is True
    # A recommendation is offered but never auto-applied.
    assert ps.suggested_profile_id is not L1


def test_14_equity_below_range_warns_no_auto_downgrade():
    state = LiveCapitalState.from_account_snapshot(
        _account(wallet="2", margin="2", available="2", unrealized="0", positions=[]),
        capital_profile_id=L1,
    )
    ps = evaluate_capital_profile_state(state, L1)
    assert ps.profile_status == CapitalProfileStatus.PROFILE_MISMATCH_EQUITY_BELOW_RANGE
    assert ps.capital_profile_id is L1  # unchanged
    assert ps.requires_operator_action is True


# ===========================================================================
# 15-25: Live order risk pre-check
# ===========================================================================
def _intent(**kw):
    base = dict(
        symbol="RAVEUSDT",
        side="LONG",
        planned_entry_price=1.0,
        planned_notional_usdt=1.0,
        planned_leverage=1.0,
        planned_stop_price=0.9,
        planned_take_profit_price=1.5,
        exit_plan_present=True,
        stop_plan_present=True,
        candidate_stage="early",
        opportunity_score=70.0,
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
        source=OrderSource.LIVE,
    )
    base.update(kw)
    return LiveOrderIntent(**base)


def test_15_notional_above_profile_max_rejected():
    state = _tiny_l1_state()
    decision = evaluate_live_order_risk(
        _intent(planned_notional_usdt=50.0),
        state,
        get_profile(L1),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
    )
    assert decision.approved is False
    assert LiveRiskRejectReason.NOTIONAL_EXCEEDS_PROFILE_MAX in decision.reject_reasons


def test_16_leverage_above_profile_max_rejected():
    state = _tiny_l1_state()
    decision = evaluate_live_order_risk(
        _intent(planned_leverage=10.0),
        state,
        get_profile(L1),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
    )
    assert decision.approved is False
    assert LiveRiskRejectReason.LEVERAGE_EXCEEDS_PROFILE_MAX in decision.reject_reasons
    assert decision.max_allowed_leverage == pytest.approx(get_profile(L1).max_leverage)


def test_17_no_stop_plan_rejected():
    state = _tiny_l1_state()
    decision = evaluate_live_order_risk(
        _intent(stop_plan_present=False, planned_stop_price=None),
        state,
        get_profile(L1),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
    )
    assert decision.approved is False
    assert LiveRiskRejectReason.NO_STOP_PLAN in decision.reject_reasons


def test_18_no_exit_plan_rejected():
    state = _tiny_l1_state()
    decision = evaluate_live_order_risk(
        _intent(exit_plan_present=False),
        state,
        get_profile(L1),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
    )
    assert decision.approved is False
    assert LiveRiskRejectReason.NO_EXIT_PLAN in decision.reject_reasons


def test_19_live_shadow_rejects_real_order_intent():
    state = _tiny_l1_state()
    decision = evaluate_live_order_risk(
        _intent(),
        state,
        get_profile(L1),
        runtime_mode=LiveRuntimeMode.LIVE_SHADOW,
    )
    assert decision.approved is False
    assert (
        LiveRiskRejectReason.RUNTIME_MODE_SHADOW_NO_REAL_ORDER
        in decision.reject_reasons
    )


def test_20_source_not_live_rejected():
    state = _tiny_l1_state()
    decision = evaluate_live_order_risk(
        _intent(source=OrderSource.SIM),
        state,
        get_profile(L1),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
    )
    assert decision.approved is False
    assert LiveRiskRejectReason.SOURCE_NOT_LIVE in decision.reject_reasons


def test_21_max_active_positions_reached_rejected():
    open_pos = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "0.001",
            "entryPrice": "1000",
            "unrealizedProfit": "0",
            "leverage": "2",
            "marginType": "isolated",
            "positionSide": "BOTH",
        }
    ]
    state = _tiny_l1_state(positions=open_pos)
    assert state.open_position_count == 1
    decision = evaluate_live_order_risk(
        _intent(),
        state,
        get_profile(L1),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
    )
    assert decision.approved is False
    assert (
        LiveRiskRejectReason.MAX_ACTIVE_POSITIONS_REACHED in decision.reject_reasons
    )


def test_22_daily_loss_limit_reached_rejected():
    state = _tiny_l1_state()
    decision = evaluate_live_order_risk(
        _intent(),
        state,
        get_profile(L1),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
        daily_loss_usdt=10.0,  # == profile max_daily_loss_usdt
    )
    assert decision.approved is False
    assert LiveRiskRejectReason.DAILY_LOSS_LIMIT_REACHED in decision.reject_reasons


def test_23_total_loss_limit_reached_rejected():
    state = _tiny_l1_state()
    decision = evaluate_live_order_risk(
        _intent(),
        state,
        get_profile(L1),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
        total_loss_usdt=10.0,  # == profile max_total_loss_usdt
    )
    assert decision.approved is False
    assert LiveRiskRejectReason.TOTAL_LOSS_LIMIT_REACHED in decision.reject_reasons


def test_24_risk_halt_active_rejected():
    state = _tiny_l1_state()
    # Force a risk halt via a safety equity floor above the equity.
    ps = evaluate_capital_profile_state(
        state, L1, safety_equity_floor_usdt=100.0
    )
    assert ps.risk_halt_active is True
    decision = evaluate_live_order_risk(
        _intent(),
        state,
        get_profile(L1),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
        profile_state=ps,
    )
    assert decision.approved is False
    assert LiveRiskRejectReason.RISK_HALT_ACTIVE in decision.reject_reasons
    assert decision.risk_halt_active is True


def test_25_valid_tiny_l1_sample_dry_approved_but_no_real_order():
    state = _tiny_l1_state(equity="8.0", available="8.0")
    decision = evaluate_live_order_risk(
        _intent(planned_notional_usdt=1.0, planned_leverage=1.0),
        state,
        get_profile(L1),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
        symbol_tradable=True,
    )
    assert decision.approved is True, decision.reject_reasons
    # PR112: a dry-approved decision STILL never authorises a real order.
    assert decision.real_order_allowed is False
    assert decision.to_dict()["exchange_live_orders"] is False


def test_right_tail_leverage_gate_rejection_propagates():
    state = _tiny_l1_state()
    gate = LeverageDecision(
        leverage_allowed=False,
        leverage_ratio=2.0,
        max_allowed_leverage=2.0,
        reject_reason="no_floating_profit_for_boost",
        reject_reasons=("no_floating_profit_for_boost",),
        evidence_refs=(),
        requires_operator_ack=False,
    )
    decision = evaluate_live_order_risk(
        _intent(),
        state,
        get_profile(L1),
        leverage_gate=gate,
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
    )
    assert decision.approved is False
    assert (
        LiveRiskRejectReason.RIGHT_TAIL_LEVERAGE_GATE_REJECTED
        in decision.reject_reasons
    )


def test_symbol_not_tradable_rejected():
    state = _tiny_l1_state()
    decision = evaluate_live_order_risk(
        _intent(),
        state,
        get_profile(L1),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
        symbol_tradable=False,
    )
    assert decision.approved is False
    assert LiveRiskRejectReason.SYMBOL_NOT_TRADABLE in decision.reject_reasons


def test_account_snapshot_missing_rejected():
    decision = evaluate_live_order_risk(
        _intent(),
        None,
        get_profile(L1),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
    )
    assert decision.approved is False
    assert LiveRiskRejectReason.ACCOUNT_SNAPSHOT_MISSING in decision.reject_reasons


# ===========================================================================
# 26-27: Telegram operator payloads
# ===========================================================================
def test_26_account_status_payload_includes_mode_profile_equity_positions():
    state = LiveCapitalState.from_account_snapshot(_account(), capital_profile_id=L1)
    payload = build_live_account_status_payload(state, kill_switch_armed=False)
    assert payload["payload_type"] == "LIVE_ACCOUNT_STATUS"
    assert payload["runtime_mode"] == "LIVE_SHADOW"
    assert payload["mode_display"] == "空盘跑"
    assert payload["capital_profile_id"] == L1.value
    assert payload["account_equity_usdt"] == pytest.approx(1012.75)
    assert payload["open_position_count"] == 1
    assert len(payload["positions"]) == 1
    # Safety markers.
    assert payload["real_order"] is False
    assert payload["trade_authority"] is False
    assert payload["ai_trade_authority"] is False


def test_27_pnl_payload_includes_commission_funding_net():
    s = _summary()
    payload = build_live_pnl_summary_payload(s)
    assert payload["payload_type"] == "LIVE_PNL_SUMMARY"
    assert payload["commission_total_usdt"] == pytest.approx(0.5)
    assert payload["funding_total_usdt"] == pytest.approx(-0.4)
    assert payload["net_strategy_pnl_usdt"] == pytest.approx(14.6)
    assert payload["real_order"] is False
    assert payload["ai_trade_authority"] is False


def test_capital_profile_mismatch_payload_no_auto_upgrade():
    state = LiveCapitalState.from_account_snapshot(
        _account(wallet="100", margin="100", available="100", unrealized="0", positions=[]),
        capital_profile_id=L1,
    )
    ps = evaluate_capital_profile_state(state, L1)
    payload = build_capital_profile_mismatch_payload(ps)
    assert payload["payload_type"] == "CAPITAL_PROFILE_MISMATCH"
    assert payload["current_profile_id"] == L1.value
    assert payload["recommended_next_profile_id"] != L1.value
    assert payload["auto_escalation_allowed"] is False
    assert payload["requires_operator_action"] is True


def test_risk_reject_payload_fields():
    state = _tiny_l1_state()
    decision = evaluate_live_order_risk(
        _intent(planned_notional_usdt=50.0),
        state,
        get_profile(L1),
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
    )
    payload = build_live_risk_reject_payload(decision)
    assert payload["payload_type"] == "LIVE_RISK_REJECT"
    assert payload["symbol"] == "RAVEUSDT"
    assert payload["reject_reason"] is not None
    assert payload["max_allowed_notional_usdt"] == pytest.approx(20.0)
    assert payload["real_order"] is False


# ===========================================================================
# 28: Safety flags remain false / forbidden
# ===========================================================================
def test_28_safety_flags_false_forbidden_across_layer():
    state = _tiny_l1_state()
    # Capital state.
    assert state.real_orders_allowed is False
    assert state.exchange_live_orders is False
    # Risk decision.
    decision = evaluate_live_order_risk(
        _intent(), state, get_profile(L1), runtime_mode=LiveRuntimeMode.LIVE_LIMITED
    )
    d = decision.to_dict()
    assert d["real_order_allowed"] is False
    assert d["exchange_live_orders"] is False
    assert d["trade_authority"] is False
    assert d["ai_trade_authority"] is False
    # Service status report safety flags.
    service = LiveCapitalService(
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED, capital_profile_id=L1
    )
    report = service.build_status_report(_account(), classify_income_rows(SAMPLE_INCOME))
    flags = report["safety_flags"]
    assert flags["real_order"] is False
    assert flags["trade_authority"] is False
    assert flags["ai_trade_authority"] is False
    assert flags["exchange_live_orders"] is False
    assert flags["phase_12_forbidden"] is True


def test_service_status_report_includes_all_payloads():
    service = LiveCapitalService(capital_profile_id=L1)
    report = service.build_status_report(_account(), classify_income_rows(SAMPLE_INCOME))
    payloads = report["telegram_payloads"]
    assert "LIVE_ACCOUNT_STATUS" in payloads
    assert "LIVE_CAPITAL_PROFILE_STATUS" in payloads
    assert "LIVE_PNL_SUMMARY" in payloads
    assert "FUNDING_EVENT_SUMMARY" in payloads
