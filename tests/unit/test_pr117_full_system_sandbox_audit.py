"""PR117 - Full-System Single-Altcoin Live Sandbox Audit v0 tests.

These tests exercise the FINAL full-system sandbox audit: the real
PR110-PR116 live chain wired against a single fake altcoin
(``RAVEUSDT_SANDBOX``) using fake transports only. They prove the whole
chain behaves like a real live system WITHOUT ever placing a real order,
and that blind / replay / sim stay isolated from the live path.

The numbered tests map 1:1 onto the PR117 brief's "Tests required" list.
"""

from __future__ import annotations

import math

import pytest

from app.core.enums import LiveRuntimeMode, OrderSource
from app.live.ai_output_guard import BriefingStatus, sanitize_ai_output
from app.live.capital_profile import (
    AUTO_ESCALATION_ALLOWED,
    CapitalProfileId,
    detect_profile_mismatch,
    get_profile,
)
from app.live.execution_errors import AiTradeAuthorityForbidden
from app.live.execution_gateway import (
    ExecutionPermissionContext,
    LiveExecutionGateway,
)
from app.live.execution_models import (
    LiveExecutionStatus,
    LiveOrderIntent as ExecOrderIntent,
    OrderSide,
    OrderType,
    generate_client_order_id,
)
from app.live.fake_live_exchange import (
    BEHAVIOR_FILL,
    BEHAVIOR_PARTIAL,
    BEHAVIOR_REJECT,
    BEHAVIOR_TIMEOUT,
    FakeBinanceLiveAdapter,
    FakeBinanceTransport,
    FakeFeeEngine,
    FakeFundingEngine,
    FakeLiveAccount,
)
from app.live.fake_live_market import (
    ALL_MARKET_SCENARIOS,
    FakeLiveMarketAdapter,
    MarketScenario,
)
from app.live.fake_live_strategy import LiveStrategySandboxAdapter, StrategyDecision
from app.live.full_system_audit_models import AUDIT_FAIL, AUDIT_PASS, AUDIT_WARN
from app.live.full_system_sandbox import FullSystemSandboxAudit, run_full_system_sandbox_audit
from app.live.leverage_gate import (
    RightTailLeverageReason,
    evaluate_right_tail_leverage_permission,
)
from app.live.live_runtime import FORBIDDEN_LIVE_SOURCE_CLASSES, LiveRuntime
from app.core.errors import LiveSourceRejected
from app.live.order_ledger import LiveOrderLedger, compute_net_pnl
from app.live.pnl_accounting import build_live_pnl_summary_from_rows


SYMBOL = "RAVEUSDT_SANDBOX"


@pytest.fixture(scope="module")
def full_report():
    return run_full_system_sandbox_audit(symbol=SYMBOL, scenario="all")


@pytest.fixture()
def audit():
    return FullSystemSandboxAudit(symbol=SYMBOL)


# ---------------------------------------------------------------------------
# 1-2: full audit default uses fake transports only + sends no real order
# ---------------------------------------------------------------------------
def test_01_full_audit_uses_fake_transports_only(full_report):
    d = full_report.to_dict()
    assert d["fake_transports_used"] is True
    assert d["live_trading"] is False
    assert d["exchange_live_orders"] is False
    assert d["trade_authority"] is False
    assert d["ai_trade_authority"] is False


def test_02_full_audit_sends_no_real_order(full_report):
    assert full_report.no_real_order_sent is True
    assert full_report.overall_status in (AUDIT_PASS, AUDIT_WARN)
    assert full_report.overall_status != AUDIT_FAIL


# ---------------------------------------------------------------------------
# 3-9: single-altcoin strategy lifecycle
# ---------------------------------------------------------------------------
def test_03_quiet_market_produces_no_entry():
    strat = LiveStrategySandboxAdapter()
    market = FakeLiveMarketAdapter(symbol=SYMBOL)
    plan = strat.evaluate(market.series(MarketScenario.QUIET_MARKET))
    assert plan.decision == StrategyDecision.NO_ENTRY
    assert plan.produces_entry is False


def test_04_weak_pump_rejected_or_observe_only():
    strat = LiveStrategySandboxAdapter()
    market = FakeLiveMarketAdapter(symbol=SYMBOL)
    plan = strat.evaluate(market.series(MarketScenario.WEAK_PUMP))
    assert plan.decision == StrategyDecision.OBSERVE
    assert plan.produces_entry is False


def test_05_right_tail_breakout_produces_shadow_entry_plan():
    strat = LiveStrategySandboxAdapter()
    market = FakeLiveMarketAdapter(symbol=SYMBOL)
    plan = strat.evaluate(market.series(MarketScenario.RIGHT_TAIL_BREAKOUT))
    assert plan.decision == StrategyDecision.SHADOW_ENTRY_PLAN
    assert plan.source == OrderSource.LIVE.value
    assert plan.no_future_labels is True
    assert plan.completed_tail_label is None and plan.mfe_pct is None and plan.mae_pct is None


def test_06_spread_liquidity_bad_rejected():
    strat = LiveStrategySandboxAdapter()
    market = FakeLiveMarketAdapter(symbol=SYMBOL)
    plan = strat.evaluate(market.series(MarketScenario.SPREAD_LIQUIDITY_BAD))
    gate = evaluate_right_tail_leverage_permission(plan.to_leverage_evidence())
    assert gate.leverage_allowed is False
    assert RightTailLeverageReason.NO_LIQUIDITY_EVIDENCE in gate.reject_reasons


def test_07_fake_reversal_triggers_stop_exit_logic():
    strat = LiveStrategySandboxAdapter()
    market = FakeLiveMarketAdapter(symbol=SYMBOL)
    series = market.series(MarketScenario.FAKE_BREAKOUT_REVERSAL)
    plan = strat.evaluate(series)
    exit_decision = strat.evaluate_exit(plan, series)
    assert plan.stop_plan_present and plan.exit_plan_present
    assert exit_decision["stop_triggered"] is True
    assert exit_decision["exit_decision"] == StrategyDecision.STOP_EXIT


def test_08_no_stop_plan_rejected(audit):
    r = audit.scenario_strategy_lifecycle()
    check = next(c for c in r.checks if c.check_id == "no_stop_plan_rejected")
    assert check.passed is True


def test_09_no_exit_plan_rejected(audit):
    r = audit.scenario_strategy_lifecycle()
    check = next(c for c in r.checks if c.check_id == "no_exit_plan_rejected")
    assert check.passed is True


# ---------------------------------------------------------------------------
# 10-14: execution lifecycle
# ---------------------------------------------------------------------------
def _exec_intent(price=1.05, profile=CapitalProfileId.L1_10U_PROBE):
    qty = float(math.floor(10.0 / price))
    return ExecOrderIntent(
        symbol=SYMBOL, side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=qty, notional_usdt=round(qty * price, 8),
        planned_entry_price=price, planned_stop_price=round(price * 0.9, 8),
        planned_take_profit_price=round(price * 1.3, 8), planned_leverage=2.0,
        exit_plan_present=True, stop_plan_present=True,
        client_order_id=generate_client_order_id(), source=OrderSource.LIVE,
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED, capital_profile_id=profile,
    )


def _armed_ctx(profile=CapitalProfileId.L1_10U_PROBE, equity=10.0):
    return ExecutionPermissionContext(
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED, live_limited_confirmed=True,
        exchange_live_orders=True, trade_authority=True, private_trade_enabled=True,
        kill_switch_active=False, account_equity_usdt=equity, allowed_profile_ids=(profile,),
    )


class _Approved:
    approved = True
    real_order_allowed = True


def test_10_all_gates_fake_live_limited_can_fake_submit_order():
    adapter = FakeBinanceLiveAdapter(symbol=SYMBOL, behavior=BEHAVIOR_FILL, fill_price=1.05)
    gw = LiveExecutionGateway(adapter=adapter.adapter, ledger=LiveOrderLedger())
    res = gw.submit_order(_exec_intent(), _Approved(), _armed_ctx())
    assert res.status is LiveExecutionStatus.FILLED
    assert res.is_real_order is True
    assert adapter.order_post_count == 1
    # Only the fake Binance transport was used.
    assert isinstance(adapter.transport, FakeBinanceTransport)


def test_11_fake_fill_updates_ledger():
    adapter = FakeBinanceLiveAdapter(symbol=SYMBOL, behavior=BEHAVIOR_FILL, fill_price=1.05)
    ledger = LiveOrderLedger()
    gw = LiveExecutionGateway(adapter=adapter.adapter, ledger=ledger)
    gw.submit_order(_exec_intent(), _Approved(), _armed_ctx())
    assert len(ledger) >= 1
    assert any(row.status == LiveExecutionStatus.FILLED.value for row in ledger.rows)


def test_12_fake_partial_fill_preserved():
    adapter = FakeBinanceLiveAdapter(symbol=SYMBOL, behavior=BEHAVIOR_PARTIAL, fill_price=1.05, partial_ratio=0.4)
    gw = LiveExecutionGateway(adapter=adapter.adapter, ledger=LiveOrderLedger())
    intent = _exec_intent()
    res = gw.submit_order(intent, _Approved(), _armed_ctx())
    assert res.status is LiveExecutionStatus.PARTIALLY_FILLED
    assert 0 < res.executed_qty < intent.quantity
    assert adapter.order_post_count == 1


def test_13_fake_timeout_does_not_duplicate_order():
    adapter = FakeBinanceLiveAdapter(symbol=SYMBOL, behavior=BEHAVIOR_TIMEOUT, fill_price=1.05)
    gw = LiveExecutionGateway(adapter=adapter.adapter, ledger=LiveOrderLedger())
    res = gw.submit_order(_exec_intent(), _Approved(), _armed_ctx())
    assert res.status is LiveExecutionStatus.FAILED
    assert res.is_real_order is False
    assert adapter.order_post_count == 1  # never blind-retried


def test_13b_fake_reject_no_ledger_corruption():
    adapter = FakeBinanceLiveAdapter(symbol=SYMBOL, behavior=BEHAVIOR_REJECT, fill_price=1.05)
    ledger = LiveOrderLedger()
    gw = LiveExecutionGateway(adapter=adapter.adapter, ledger=ledger)
    res = gw.submit_order(_exec_intent(), _Approved(), _armed_ctx())
    assert res.status is LiveExecutionStatus.REJECTED
    assert len(ledger) >= 1
    assert adapter.order_post_count == 1


def test_14_fake_exit_computes_gross_fee_funding_net():
    fee_engine = FakeFeeEngine()
    funding_engine = FakeFundingEngine()
    entry, exit_price, qty = 1.05, 1.365, 9.0
    gross = (exit_price - entry) * qty
    fee = fee_engine.commission(entry * qty) + fee_engine.commission(exit_price * qty)
    funding = -funding_engine.funding_fee(entry * qty, 0.0006)
    net = compute_net_pnl(gross, fee, funding)
    assert abs(net - (gross - fee + funding)) < 1e-9
    assert fee > 0 and funding < 0


# ---------------------------------------------------------------------------
# 15-19: funding / fee / PnL
# ---------------------------------------------------------------------------
def test_15_deposit_not_counted_as_profit():
    acct = FakeLiveAccount(initial_balance_usdt=10.0)
    acct.deposit(100.0)
    assert acct.ledger.total_external_deposits == 100.0
    assert acct.net_strategy_pnl == 0.0


def test_16_withdrawal_not_counted_as_loss():
    acct = FakeLiveAccount(initial_balance_usdt=110.0)
    acct.withdraw(50.0)
    assert acct.ledger.total_external_withdrawals == 50.0
    assert acct.net_strategy_pnl == 0.0


def test_17_funding_fee_included():
    acct = FakeLiveAccount(initial_balance_usdt=10.0)
    acct.funding_fee(0.4)
    assert abs(acct.ledger.total_funding - (-0.4)) < 1e-9
    assert acct.net_strategy_pnl < 0


def test_18_funding_income_included():
    acct = FakeLiveAccount(initial_balance_usdt=10.0)
    acct.funding_income(0.6)
    assert abs(acct.ledger.total_funding - 0.6) < 1e-9
    assert acct.net_strategy_pnl > 0


def test_19_commission_included():
    acct = FakeLiveAccount(initial_balance_usdt=10.0)
    acct.realized_profit(5.0)
    acct.commission(0.2)
    assert acct.ledger.total_fees == 0.2
    assert abs(acct.net_strategy_pnl - (5.0 - 0.2)) < 1e-9


def test_19b_net_strategy_pnl_formula_and_performance_equity_excludes_flows():
    rows = [
        {"incomeType": "REALIZED_PNL", "income": "5.0", "asset": "USDT", "symbol": SYMBOL, "time": 1, "tradeId": "t1"},
        {"incomeType": "COMMISSION", "income": "-0.2", "asset": "USDT", "symbol": SYMBOL, "time": 2, "tradeId": "t1"},
        {"incomeType": "FUNDING_FEE", "income": "0.6", "asset": "USDT", "symbol": SYMBOL, "time": 3},
        {"incomeType": "FUNDING_FEE", "income": "-0.4", "asset": "USDT", "symbol": SYMBOL, "time": 4},
        {"incomeType": "WELCOME_BONUS", "income": "100.0", "asset": "USDT", "time": 5},
    ]
    s = build_live_pnl_summary_from_rows(rows, account_equity_usdt=110.0)
    assert abs(s.net_strategy_pnl_usdt - 5.0) < 1e-9
    assert abs(s.performance_equity_excluding_external_flows - 10.0) < 1e-9


# ---------------------------------------------------------------------------
# 20-27: capital ladder 1U -> 10M
# ---------------------------------------------------------------------------
def test_20_1u_profile_distinct_from_10u():
    p1 = get_profile(CapitalProfileId.L1_1U_MICRO_PROBE)
    p10 = get_profile(CapitalProfileId.L1_10U_PROBE)
    assert p1.max_account_capital_usdt != p10.max_account_capital_usdt
    assert p1.max_position_notional_usdt != p10.max_position_notional_usdt


def test_21_10u_cap_enforced():
    from app.live.live_risk_engine import evaluate_capital_profile_state
    audit = FullSystemSandboxAudit(symbol=SYMBOL)
    cap = audit._capital_state(balance_usdt=50.0, profile_id=CapitalProfileId.L1_10U_PROBE)
    state = evaluate_capital_profile_state(cap, get_profile(CapitalProfileId.L1_10U_PROBE))
    assert abs(state.usable_capital_usdt - 10.0) < 1e-9


def test_22_50u_profile_changes_caps():
    p10 = get_profile(CapitalProfileId.L1_10U_PROBE)
    p50 = get_profile(CapitalProfileId.L2_25U_50U_SCOUT)
    assert p50.max_account_capital_usdt == 50.0
    assert p50.max_position_notional_usdt != p10.max_position_notional_usdt


def test_23_1000u_profile_changes_caps():
    p50 = get_profile(CapitalProfileId.L2_25U_50U_SCOUT)
    p1k = get_profile(CapitalProfileId.L4_1K_GROWTH)
    assert p1k.max_account_capital_usdt == 1000.0
    assert p1k.max_position_notional_usdt > p50.max_position_notional_usdt


def test_24_10000u_profile_does_not_reuse_10u_limits():
    p10u = get_profile(CapitalProfileId.L1_10U_PROBE)
    p10k = get_profile(CapitalProfileId.L5_10K_PROFIT_PROTECTION)
    assert p10k.max_account_capital_usdt == 10000.0
    assert p10k.max_position_notional_usdt != p10u.max_position_notional_usdt
    assert p10k.max_slippage_bps < p10u.max_slippage_bps


def test_25_1m_10m_profiles_stricter_liquidity_slippage():
    p10u = get_profile(CapitalProfileId.L1_10U_PROBE)
    p1m = get_profile(CapitalProfileId.L7_1M_INSTITUTIONAL_STYLE)
    p10m = get_profile(CapitalProfileId.L8_10M_CAPITAL_PRESERVATION)
    assert p1m.max_slippage_bps < p10u.max_slippage_bps
    assert p10m.max_slippage_bps < p1m.max_slippage_bps
    assert p1m.min_exit_liquidity_score > p10u.min_exit_liquidity_score
    assert p10m.right_tail_boost_allowed is False


def test_26_profile_mismatch_does_not_auto_upgrade():
    mm = detect_profile_mismatch(CapitalProfileId.L1_10U_PROBE, 10000.0)
    assert mm.mismatch is True
    assert mm.direction == "escalate"
    assert mm.requires_operator_action is True
    assert AUTO_ESCALATION_ALLOWED is False


def test_27_operator_profile_switch_changes_caps_without_code_change(tmp_path):
    from app.live.telegram_state import LiveOperatorStateStore
    rt = LiveRuntime(state_store=LiveOperatorStateStore(state_dir=tmp_path / "rt"))
    rt.set_capital_profile(CapitalProfileId.L1_10U_PROBE)
    caps_10 = rt.profile_caps().max_account_capital_usdt
    rt.set_capital_profile(CapitalProfileId.L4_1K_GROWTH)
    caps_1k = rt.profile_caps().max_account_capital_usdt
    assert caps_10 == 10.0 and caps_1k == 1000.0
    ctx = rt.build_execution_context(account_equity_usdt=1000.0)
    assert ctx.allowed_profile_ids == (CapitalProfileId.L4_1K_GROWTH,)


# ---------------------------------------------------------------------------
# 28-33: Telegram operator
# ---------------------------------------------------------------------------
@pytest.fixture()
def telegram_result(audit):
    return audit.scenario_telegram_operator()


def test_28_telegram_unauthorized_rejected(telegram_result):
    check = next(c for c in telegram_result.checks if c.check_id == "unauthorized_chat_rejected")
    assert check.passed is True
    empty = next(c for c in telegram_result.checks if c.check_id == "empty_allowlist_fails_closed")
    assert empty.passed is True


def test_29_telegram_mode_live_limited_only_returns_confirmation(telegram_result):
    check = next(c for c in telegram_result.checks if c.check_id == "mode_live_limited_only_confirmation")
    assert check.passed is True


def test_30_telegram_confirm_arms_but_does_not_bypass_execution_gates(telegram_result):
    check = next(c for c in telegram_result.checks if c.check_id == "confirm_arms_but_does_not_enable_real_orders")
    assert check.passed is True
    no_adapter = next(c for c in telegram_result.checks if c.check_id == "console_has_no_execution_adapter")
    assert no_adapter.passed is True


def test_31_telegram_entry_card_readable(telegram_result):
    check = next(c for c in telegram_result.checks if c.check_id == "shadow_entry_card_readable")
    assert check.passed is True


def test_32_telegram_exit_card_shows_gross_fee_funding_net(telegram_result):
    check = next(c for c in telegram_result.checks if c.check_id == "exit_card_shows_gross_fee_funding_net")
    assert check.passed is True


def test_33_telegram_pnl_separates_deposit_withdrawal(telegram_result):
    check = next(c for c in telegram_result.checks if c.check_id == "pnl_card_separates_external_flows")
    assert check.passed is True


# ---------------------------------------------------------------------------
# 34-36: AI guard
# ---------------------------------------------------------------------------
def test_34_ai_forbidden_fields_rejected():
    guard = sanitize_ai_output(
        {
            "market_summary": "ok",
            "should_buy": True,
            "direction": "LONG",
            "leverage": 20,
            "stop_price": 0.9,
            "take_profit": 1.5,
            "position_size": 100,
            "order_type": "MARKET",
            "entry_price": 1.0,
            "exit_price": 1.4,
            "runtime_config_patch": {"x": 1},
        }
    )
    assert guard.status == BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY
    for forbidden in ("should_buy", "direction", "leverage", "stop_price", "take_profit",
                      "position_size", "order_type", "entry_price", "exit_price", "runtime_config_patch"):
        assert forbidden not in guard.clean_payload


def test_35_ai_blind_evidence_rejected():
    from app.live.ai_live_evidence import build_live_ai_evidence_bundle
    res = build_live_ai_evidence_bundle(sources=[OrderSource.OFFLINE_AI])
    assert res.accepted is False
    assert res.bundle is None
    assert len(res.forbidden_sources_detected) >= 1


def test_36_ai_cannot_call_execution():
    adapter = FakeBinanceLiveAdapter(symbol=SYMBOL)
    gw = LiveExecutionGateway(adapter=adapter.adapter, ledger=LiveOrderLedger())
    ctx = ExecutionPermissionContext(
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED, live_limited_confirmed=True,
        exchange_live_orders=True, trade_authority=True, private_trade_enabled=True,
        ai_trade_authority=True, account_equity_usdt=10.0,
    )
    with pytest.raises(AiTradeAuthorityForbidden):
        gw.submit_order(_exec_intent(), _Approved(), ctx)
    assert adapter.order_post_count == 0


# ---------------------------------------------------------------------------
# 37-43: blind / replay / sim isolation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("source", [OrderSource.BLIND, OrderSource.SIM, OrderSource.REPLAY, OrderSource.PAPER_SHADOW])
def test_37_to_40_nonlive_source_blocked(source):
    from app.core.enums import Direction
    from app.live.path_isolation import LiveOrderIntent as IsolationIntent, LivePathIsolationGuard
    guard = LivePathIsolationGuard()
    intent = IsolationIntent(source=source, source_module="t", symbol=SYMBOL, side=Direction.LONG)
    decision = guard.authorize(intent)
    assert decision.authorised is False
    assert "non_live_source_blocked" in decision.reason


def test_41_historical_market_store_not_used_as_live_source():
    class HistoricalMarketStore:
        pass

    assert "HistoricalMarketStore" in FORBIDDEN_LIVE_SOURCE_CLASSES
    with pytest.raises(LiveSourceRejected):
        LiveRuntime.assert_live_market_source(HistoricalMarketStore())


def test_42_mock_exchange_not_used_in_live_execution():
    class MockExchange:
        pass

    assert "MockExchange" in FORBIDDEN_LIVE_SOURCE_CLASSES
    with pytest.raises(LiveSourceRejected):
        LiveRuntime.assert_live_market_source(MockExchange())


def test_43_simulated_capital_flow_not_used_as_live_capital():
    class SimulatedCapitalFlow:
        pass

    assert "SimulatedCapitalFlow" in FORBIDDEN_LIVE_SOURCE_CLASSES
    with pytest.raises(LiveSourceRejected):
        LiveRuntime.assert_live_market_source(SimulatedCapitalFlow())


# ---------------------------------------------------------------------------
# 44-47: kill switch / rollback / fail-safe
# ---------------------------------------------------------------------------
def test_44_kill_switch_ready_active_semantics(tmp_path):
    from app.live.live_kill_switch import LiveKillSwitch
    from app.live.telegram_state import LiveOperatorStateStore
    kill = LiveKillSwitch(state_store=LiveOperatorStateStore(state_dir=tmp_path / "k"))
    assert kill.is_ready is True
    assert kill.is_active is False
    code = kill.request_arm()
    assert kill.is_active is False  # requires confirmation
    kill.confirm_arm(code)
    assert kill.is_active is True


def test_45_kill_switch_active_blocks_entries():
    adapter = FakeBinanceLiveAdapter(symbol=SYMBOL)
    gw = LiveExecutionGateway(adapter=adapter.adapter, ledger=LiveOrderLedger())
    ctx = ExecutionPermissionContext(
        runtime_mode=LiveRuntimeMode.LIVE_LIMITED, live_limited_confirmed=True,
        exchange_live_orders=True, trade_authority=True, private_trade_enabled=True,
        kill_switch_active=True, account_equity_usdt=10.0,
    )
    res = gw.submit_order(_exec_intent(), _Approved(), ctx)
    assert res.status is LiveExecutionStatus.BLOCKED
    assert adapter.order_post_count == 0


def test_46_rollback_to_live_shadow_works(tmp_path):
    from app.live.telegram_commands import TelegramCommandHandler
    from app.live.telegram_state import LiveOperatorStateStore
    handler = TelegramCommandHandler(state_store=LiveOperatorStateStore(state_dir=tmp_path / "r"))
    handler.handle("/profile set L1_10U_PROBE confirm")
    card = handler.handle("/mode live_limited").card
    code = next((v for v in card.values() if isinstance(v, str) and v.startswith("LIVE-")), "")
    handler.handle(f"/confirm_live {code}")
    assert handler.runtime_mode is LiveRuntimeMode.LIVE_LIMITED
    handler.handle("/mode shadow")
    assert handler.runtime_mode is LiveRuntimeMode.LIVE_SHADOW
    assert handler.live_limited_armed is False


def test_47_corrupt_state_fails_safe(tmp_path):
    from app.live.live_kill_switch import LiveKillSwitch
    from app.live.telegram_state import (
        KILL_SWITCH_FILE,
        RUNTIME_MODE_FILE,
        LiveOperatorStateStore,
    )
    d = tmp_path / "corrupt"
    d.mkdir()
    (d / RUNTIME_MODE_FILE).write_text("{ not json", encoding="utf-8")
    (d / KILL_SWITCH_FILE).write_text("}{ broken", encoding="utf-8")
    store = LiveOperatorStateStore(state_dir=d)
    loaded = store.load()
    assert loaded.runtime.runtime_mode is LiveRuntimeMode.LIVE_SHADOW
    assert any("CORRUPT" in w.upper() for w in loaded.warnings)
    assert LiveKillSwitch(state_store=store).is_ready is False


# ---------------------------------------------------------------------------
# 48-49: final audit JSON content
# ---------------------------------------------------------------------------
def test_48_final_audit_json_includes_scenario_results(full_report):
    d = full_report.to_dict()
    assert "scenario_results" in d and len(d["scenario_results"]) == 9
    names = {s["scenario"] for s in d["scenario_results"]}
    assert {"strategy_lifecycle", "execution_lifecycle", "capital_ladder",
            "funding_fee_pnl", "telegram_operator", "ai_guard", "blind_isolation",
            "kill_switch", "live_risk"}.issubset(names)


def test_49_final_audit_json_includes_capital_scaling_result(full_report):
    ladder = next(s for s in full_report.scenario_results if s.scenario == "capital_ladder")
    assert "ladder_caps" in ladder.details
    caps = ladder.details["ladder_caps"]
    assert list(caps.values()) == sorted(caps.values())  # scales without code change
    assert full_report.to_dict()["ready_for_real_key_validation"] is True


# ---------------------------------------------------------------------------
# Extra: market generator + report shape sanity
# ---------------------------------------------------------------------------
def test_market_generator_has_eight_scenarios():
    assert len(ALL_MARKET_SCENARIOS) == 8
    market = FakeLiveMarketAdapter(symbol=SYMBOL)
    for scenario in ALL_MARKET_SCENARIOS:
        series = market.series(scenario)
        assert series.symbol == SYMBOL
        assert len(series.frames) >= 5
        for f in series.frames:
            assert f.is_future_label is False


def test_report_overall_pass_and_all_chain_flags(full_report):
    d = full_report.to_dict()
    assert d["overall_status"] == AUDIT_PASS
    for flag in ("full_system_chain_ok", "strategy_chain_ok", "live_risk_chain_ok",
                 "execution_chain_ok", "telegram_chain_ok", "ai_chain_ok",
                 "funding_pnl_chain_ok", "capital_ladder_chain_ok",
                 "blind_isolation_ok", "kill_switch_chain_ok"):
        assert d[flag] is True
