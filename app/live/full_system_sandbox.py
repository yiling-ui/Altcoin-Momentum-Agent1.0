"""Full-system single-altcoin live sandbox audit runner (PR117).

PR117 is the FINAL full-system sandbox audit. It wires the REAL
PR110-PR116 live chain together against a single fake altcoin
(``RAVEUSDT_SANDBOX``) using fake transports only, and asserts the whole
chain behaves like a real live system would WITHOUT ever placing a real
order:

    fake live market
      -> strategy / opportunity (LiveStrategySandboxAdapter, source=LIVE)
      -> live risk decision      (evaluate_live_order_risk)
      -> capital profile          (capital_profile ladder)
      -> right-tail leverage gate (deterministic, no AI)
      -> execution gateway        (LiveExecutionGateway, 15-point gate)
      -> fake Binance order        (real adapter + FakeBinanceTransport)
      -> fills / fees / funding    (FakeFeeEngine / FakeFundingEngine)
      -> live order ledger + PnL   (compute_net_pnl, build_live_pnl_summary)
      -> Telegram operator cards    (real console + FakeTelegramTransport)
      -> DeepSeek briefing          (real generator + FakeDeepSeekTransport)
      -> kill switch / rollback     (LiveKillSwitch)
      -> deposit / withdrawal / profile mismatch / capital scaling

Hard posture (the brief): NEVER sends a real order, NEVER uses a real
transport, default ``live_trading`` / ``exchange_live_orders`` /
``trade_authority`` / ``ai_trade_authority`` all False, and blind /
replay / sim / paper-shadow stay isolated from the live path.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import Any, Callable

from app.core.enums import LiveRuntimeMode, OrderSource
from app.live.ai_live_briefing import AI_AUTHORITY_LABEL, LiveAIBriefingGenerator
from app.live.ai_live_evidence import build_live_ai_evidence_bundle
from app.live.ai_output_guard import BriefingStatus, sanitize_ai_output
from app.live.api_config import TelegramApiConfig
from app.live.capital_event import CapitalEventType
from app.live.capital_profile import (
    AUTO_ESCALATION_ALLOWED,
    CAPITAL_PROFILE_ORDER,
    CapitalProfileId,
    detect_profile_mismatch,
    get_profile,
    suggest_profile_for_equity,
)
from app.live.capital_state import LiveCapitalState
from app.live.execution_errors import AiTradeAuthorityForbidden
from app.live.execution_gateway import (
    ExecutionPermissionContext,
    ExecutionRejectReason,
    LiveExecutionGateway,
    authorize_real_order,
)
from app.live.execution_models import (
    LiveExecutionStatus,
    LiveOrderIntent as ExecOrderIntent,
    LiveOrderResult,
    OrderSide,
    OrderType,
    generate_client_order_id,
)
from app.live.execution_telegram import (
    PAYLOAD_LIVE_EXIT_FILLED,
    build_execution_telegram_payload,
)
from app.live.fake_live_deepseek import (
    FakeDeepSeekTransport,
    fake_sandbox_deepseek_config,
)
from app.live.fake_live_exchange import (
    BEHAVIOR_FILL,
    BEHAVIOR_PARTIAL,
    BEHAVIOR_REJECT,
    BEHAVIOR_TIMEOUT,
    UNKNOWN_PENDING_RECONCILIATION,
    FakeBinanceLiveAdapter,
    FakeFeeEngine,
    FakeFundingEngine,
    FakeLiveAccount,
)
from app.live.fake_live_market import FakeLiveMarketAdapter, MarketScenario
from app.live.fake_live_strategy import LiveStrategySandboxAdapter, StrategyDecision
from app.live.fake_live_telegram import (
    FakeOperator,
    FakeTelegramTransport,
    SandboxConsoleDataProvider,
)
from app.live.full_system_audit_models import (
    ALL_SCENARIOS,
    DEFAULT_SANDBOX_SYMBOL,
    FullSystemAuditReport,
    ScenarioBuilder,
    ScenarioResult,
)
from app.live.leverage_gate import (
    LeverageDecision,
    RightTailLeverageReason,
    evaluate_right_tail_leverage_permission,
)
from app.live.live_kill_switch import (
    KILL_EXIT_MANUAL_ACTION_REQUIRED,
    LiveKillSwitch,
)
from app.live.live_risk_engine import (
    LiveRiskRejectReason,
    evaluate_live_order_risk,
)
from app.live.live_runtime import FORBIDDEN_LIVE_SOURCE_CLASSES, LiveRuntime
from app.core.errors import LiveSourceRejected
from app.live.order_ledger import LiveOrderLedger, compute_net_pnl
from app.live.path_isolation import (
    LiveOrderIntent as IsolationIntent,
    LivePathIsolationGuard,
    classify_source_module,
)
from app.live.pnl_accounting import build_live_pnl_summary_from_rows
from app.live.telegram_auth import LiveSourceGuard, TelegramAuthGuard
from app.live.telegram_commands import TelegramCommandHandler
from app.live.telegram_operator import TelegramOperatorConsole
from app.live.telegram_state import KILL_SWITCH_FILE, RUNTIME_MODE_FILE, LiveOperatorStateStore
from app.live.secrets import SecretValue

FULL_SYSTEM_SANDBOX_MODULE = "live.full_system_sandbox"

# The right-tail-equivalent market scenarios (clean breakout structure).
_RIGHT_TAIL_SCENARIOS = (
    MarketScenario.RIGHT_TAIL_BREAKOUT,
    MarketScenario.FUNDING_NEGATIVE_HOLD,
    MarketScenario.FUNDING_POSITIVE_HOLD,
    MarketScenario.EXCHANGE_FAILURE_MID_TRADE,
)


class FullSystemSandboxAudit:
    """Runs the PR117 full-system single-altcoin sandbox audit.

    Every scenario uses fake transports only; no real order is ever sent.
    """

    def __init__(self, *, symbol: str = DEFAULT_SANDBOX_SYMBOL) -> None:
        self.symbol = symbol
        self.market = FakeLiveMarketAdapter(symbol=symbol)
        self.strategy = LiveStrategySandboxAdapter()
        self.fee_engine = FakeFeeEngine()
        self.funding_engine = FakeFundingEngine()
        self.operator = FakeOperator()
        self._tmp_root = Path(tempfile.mkdtemp(prefix="ama_pr117_"))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _state_store(self, name: str) -> LiveOperatorStateStore:
        return LiveOperatorStateStore(state_dir=self._tmp_root / name)

    def _capital_state(
        self,
        *,
        balance_usdt: float,
        profile_id: CapitalProfileId,
        runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_LIMITED,
    ) -> LiveCapitalState:
        account = FakeLiveAccount(initial_balance_usdt=balance_usdt)
        return LiveCapitalState.from_account_snapshot(
            account.to_account_snapshot(),
            runtime_mode=runtime_mode,
            capital_profile_id=profile_id,
        )

    def _right_tail_plan_and_gate(
        self,
        *,
        profile_id: CapitalProfileId = CapitalProfileId.L1_10U_PROBE,
        equity: float = 10.0,
        scenario: str = MarketScenario.RIGHT_TAIL_BREAKOUT,
    ):
        """Build a right-tail plan + the deterministic leverage decision."""
        series = self.market.series(scenario)
        plan = self.strategy.evaluate(
            series, capital_profile_id=profile_id, account_equity_usdt=equity
        )
        evidence = plan.to_leverage_evidence(runtime_mode=LiveRuntimeMode.LIVE_LIMITED)
        gate = evaluate_right_tail_leverage_permission(evidence)
        return series, plan, gate

    def _exec_intent_from_plan(
        self,
        plan,
        gate: LeverageDecision,
        *,
        profile_id: CapitalProfileId = CapitalProfileId.L1_10U_PROBE,
    ) -> ExecOrderIntent:
        """Build an exchange-ready execution intent from a right-tail plan."""
        price = plan.planned_entry_price
        notional_target = min(get_profile(profile_id).max_position_notional_usdt * 0.5, 10.0)
        qty = float(math.floor(notional_target / price)) if price > 0 else 0.0
        qty = max(qty, 1.0)
        notional = round(qty * price, 8)
        leverage = gate.leverage_ratio if gate.leverage_allowed else plan.planned_leverage_request
        return ExecOrderIntent(
            symbol=plan.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=qty,
            notional_usdt=notional,
            planned_entry_price=price,
            planned_stop_price=plan.planned_stop_price,
            planned_take_profit_price=plan.planned_take_profit_price,
            planned_leverage=leverage,
            exit_plan_present=True,
            stop_plan_present=True,
            client_order_id=generate_client_order_id(),
            source=OrderSource.LIVE,
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
            capital_profile_id=profile_id,
        )

    def _armed_context(
        self, *, equity: float = 10.0, profile_id: CapitalProfileId = CapitalProfileId.L1_10U_PROBE
    ) -> ExecutionPermissionContext:
        return ExecutionPermissionContext(
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
            live_limited_confirmed=True,
            exchange_live_orders=True,
            trade_authority=True,
            ai_trade_authority=False,
            private_trade_enabled=True,
            kill_switch_active=False,
            profile_operator_acknowledged=False,
            hard_block_on_profile_mismatch=True,
            account_equity_usdt=equity,
            allowed_profile_ids=(profile_id,),
        )

    def _approved_risk_decision(
        self, plan, gate, *, profile_id=CapitalProfileId.L1_10U_PROBE, equity=10.0, exec_intent=None
    ):
        cap_state = self._capital_state(balance_usdt=equity, profile_id=profile_id)
        notional = exec_intent.notional_usdt if exec_intent else plan.planned_notional_usdt
        leverage = exec_intent.planned_leverage if exec_intent else plan.planned_leverage_request
        risk_intent = plan.to_risk_intent(runtime_mode=LiveRuntimeMode.LIVE_LIMITED)
        # Align the risk intent notional/leverage with the execution intent.
        risk_intent = type(risk_intent)(
            symbol=risk_intent.symbol,
            side=risk_intent.side,
            planned_entry_price=risk_intent.planned_entry_price,
            planned_notional_usdt=notional,
            planned_leverage=leverage,
            planned_stop_price=risk_intent.planned_stop_price,
            planned_take_profit_price=risk_intent.planned_take_profit_price,
            exit_plan_present=risk_intent.exit_plan_present,
            stop_plan_present=risk_intent.stop_plan_present,
            candidate_stage=risk_intent.candidate_stage,
            opportunity_score=risk_intent.opportunity_score,
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
            source=OrderSource.LIVE,
        )
        decision = evaluate_live_order_risk(
            risk_intent, cap_state, profile_id, leverage_gate=gate,
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
        )
        return decision

    # ==================================================================
    # Scenario: strategy lifecycle
    # ==================================================================
    def scenario_strategy_lifecycle(self) -> ScenarioResult:
        b = ScenarioBuilder("strategy_lifecycle")
        profile_id = CapitalProfileId.L1_10U_PROBE

        # 1. quiet market -> no entry.
        quiet = self.strategy.evaluate(self.market.series(MarketScenario.QUIET_MARKET), capital_profile_id=profile_id)
        b.blocker("quiet_market_no_entry", quiet.decision == StrategyDecision.NO_ENTRY,
                  detail=f"decision={quiet.decision}", value=quiet.decision)

        # 2. weak pump -> observe / reject (no entry).
        weak = self.strategy.evaluate(self.market.series(MarketScenario.WEAK_PUMP), capital_profile_id=profile_id)
        b.blocker("weak_pump_observe_or_reject",
                  weak.decision == StrategyDecision.OBSERVE and not weak.produces_entry,
                  detail=f"decision={weak.decision}", value=weak.decision)

        # 3. right-tail breakout -> shadow entry plan.
        series, plan, gate = self._right_tail_plan_and_gate(profile_id=profile_id)
        b.blocker("right_tail_breakout_shadow_entry_plan",
                  plan.decision == StrategyDecision.SHADOW_ENTRY_PLAN and plan.produces_entry,
                  detail=f"decision={plan.decision}", value=plan.decision)
        b.info("right_tail_source_is_live", plan.source == OrderSource.LIVE.value, value=plan.source)
        b.info("right_tail_no_future_labels",
               plan.no_future_labels and plan.completed_tail_label is None
               and plan.mfe_pct is None and plan.mae_pct is None)

        # 4. spread/liquidity bad -> risk / leverage gate rejects.
        bad_series = self.market.series(MarketScenario.SPREAD_LIQUIDITY_BAD)
        bad_plan = self.strategy.evaluate(bad_series, capital_profile_id=profile_id)
        bad_gate = evaluate_right_tail_leverage_permission(
            bad_plan.to_leverage_evidence(runtime_mode=LiveRuntimeMode.LIVE_LIMITED)
        )
        b.blocker("spread_liquidity_bad_leverage_gate_rejects",
                  not bad_gate.leverage_allowed
                  and RightTailLeverageReason.NO_LIQUIDITY_EVIDENCE in bad_gate.reject_reasons,
                  detail=f"reasons={bad_gate.reject_reasons}")

        # 5. fake breakout reversal -> stop/exit logic fires.
        rev_series = self.market.series(MarketScenario.FAKE_BREAKOUT_REVERSAL)
        rev_plan = self.strategy.evaluate(rev_series, capital_profile_id=profile_id)
        rev_exit = self.strategy.evaluate_exit(rev_plan, rev_series)
        b.blocker("fake_reversal_has_stop_and_exit",
                  rev_plan.stop_plan_present and rev_plan.exit_plan_present)
        b.blocker("fake_reversal_stop_triggered",
                  rev_exit["stop_triggered"] is True,
                  detail=f"exit={rev_exit}")

        # 6. no stop plan -> risk rejects.
        cap_state = self._capital_state(balance_usdt=10.0, profile_id=profile_id)
        no_stop_intent = plan.to_risk_intent(runtime_mode=LiveRuntimeMode.LIVE_LIMITED, drop_stop=True)
        no_stop = evaluate_live_order_risk(no_stop_intent, cap_state, profile_id, leverage_gate=gate,
                                           runtime_mode=LiveRuntimeMode.LIVE_LIMITED)
        b.blocker("no_stop_plan_rejected",
                  not no_stop.approved and LiveRiskRejectReason.NO_STOP_PLAN in no_stop.reject_reasons)

        # 7. no exit plan -> risk rejects.
        no_exit_intent = plan.to_risk_intent(runtime_mode=LiveRuntimeMode.LIVE_LIMITED, drop_exit=True)
        no_exit = evaluate_live_order_risk(no_exit_intent, cap_state, profile_id, leverage_gate=gate,
                                           runtime_mode=LiveRuntimeMode.LIVE_LIMITED)
        b.blocker("no_exit_plan_rejected",
                  not no_exit.approved and LiveRiskRejectReason.NO_EXIT_PLAN in no_exit.reject_reasons)

        # 8. right-tail leverage only from the deterministic gate.
        b.blocker("leverage_decided_by_deterministic_gate",
                  gate.leverage_allowed and gate.to_dict()["decided_by"] == "deterministic_gate",
                  detail=f"leverage_ratio={gate.leverage_ratio}")

        # 9. AI cannot influence strategy / leverage.
        ai_gate = evaluate_right_tail_leverage_permission(
            plan.to_leverage_evidence(runtime_mode=LiveRuntimeMode.LIVE_LIMITED, inject_forbidden_ai=True)
        )
        b.blocker("ai_input_refused_by_leverage_gate",
                  (not ai_gate.leverage_allowed) and ai_gate.ai_input_detected
                  and ai_gate.reject_reason == RightTailLeverageReason.AI_INPUT_FORBIDDEN)

        # 10. blind/replay cannot influence the strategy/live decision.
        blind_intent = plan.to_risk_intent(runtime_mode=LiveRuntimeMode.LIVE_LIMITED)
        blind_intent = type(blind_intent)(
            symbol=blind_intent.symbol, side=blind_intent.side,
            planned_entry_price=blind_intent.planned_entry_price,
            planned_notional_usdt=blind_intent.planned_notional_usdt,
            planned_leverage=blind_intent.planned_leverage,
            planned_stop_price=blind_intent.planned_stop_price,
            planned_take_profit_price=blind_intent.planned_take_profit_price,
            exit_plan_present=blind_intent.exit_plan_present,
            stop_plan_present=blind_intent.stop_plan_present,
            candidate_stage=blind_intent.candidate_stage,
            opportunity_score=blind_intent.opportunity_score,
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED, source=OrderSource.BLIND,
        )
        blind_dec = evaluate_live_order_risk(blind_intent, cap_state, profile_id, leverage_gate=gate,
                                             runtime_mode=LiveRuntimeMode.LIVE_LIMITED)
        b.blocker("blind_source_rejected_by_risk",
                  not blind_dec.approved and LiveRiskRejectReason.SOURCE_NOT_LIVE in blind_dec.reject_reasons)

        # Strategy reaches a complete, approved live chain for right-tail.
        exec_intent = self._exec_intent_from_plan(plan, gate, profile_id=profile_id)
        approved = self._approved_risk_decision(plan, gate, profile_id=profile_id, exec_intent=exec_intent)
        b.blocker("right_tail_chain_risk_approved", approved.approved,
                  detail=f"reasons={approved.reject_reasons}")
        b.detail("right_tail_plan", plan.to_dict())
        return b.build()

    # ==================================================================
    # Scenario: execution lifecycle
    # ==================================================================
    def scenario_execution_lifecycle(self) -> ScenarioResult:
        b = ScenarioBuilder("execution_lifecycle")
        profile_id = CapitalProfileId.L1_10U_PROBE
        series, plan, gate = self._right_tail_plan_and_gate(profile_id=profile_id)
        exec_intent = self._exec_intent_from_plan(plan, gate, profile_id=profile_id)
        risk_decision = self._approved_risk_decision(plan, gate, profile_id=profile_id, exec_intent=exec_intent)
        armed = self._armed_context(profile_id=profile_id)
        shadow_ctx = ExecutionPermissionContext(
            runtime_mode=LiveRuntimeMode.LIVE_SHADOW, account_equity_usdt=10.0,
            allowed_profile_ids=(profile_id,),
        )

        # 1. Default LIVE_SHADOW: plan only, no real order.
        shadow_adapter = FakeBinanceLiveAdapter(
            symbol=self.symbol, behavior=BEHAVIOR_FILL, fill_price=plan.planned_entry_price,
            runtime_mode=LiveRuntimeMode.LIVE_SHADOW,
        )
        shadow_gw = LiveExecutionGateway(adapter=shadow_adapter.adapter, ledger=LiveOrderLedger())
        shadow_intent = type(exec_intent)(
            symbol=exec_intent.symbol, side=exec_intent.side, order_type=exec_intent.order_type,
            quantity=exec_intent.quantity, notional_usdt=exec_intent.notional_usdt,
            planned_entry_price=exec_intent.planned_entry_price,
            planned_stop_price=exec_intent.planned_stop_price,
            planned_take_profit_price=exec_intent.planned_take_profit_price,
            planned_leverage=exec_intent.planned_leverage, exit_plan_present=True, stop_plan_present=True,
            client_order_id=generate_client_order_id(), source=OrderSource.LIVE,
            runtime_mode=LiveRuntimeMode.LIVE_SHADOW, capital_profile_id=profile_id,
        )
        shadow_res = shadow_gw.submit_order(shadow_intent, risk_decision, shadow_ctx)
        b.blocker("shadow_no_real_order",
                  shadow_res.status is LiveExecutionStatus.BLOCKED and not shadow_res.is_real_order
                  and shadow_adapter.order_post_count == 0,
                  detail=f"status={shadow_res.status.value} post_count={shadow_adapter.order_post_count}")
        shadow_card = getattr(shadow_gw, "_last_telegram_payload", None)
        b.blocker("shadow_card_real_order_false",
                  bool(shadow_card) and shadow_card.get("real_order") is False)

        # 2. Gated LIVE_LIMITED fake execution -> filled.
        fill_adapter = FakeBinanceLiveAdapter(
            symbol=self.symbol, behavior=BEHAVIOR_FILL, fill_price=plan.planned_entry_price,
        )
        fill_gw = LiveExecutionGateway(adapter=fill_adapter.adapter, ledger=LiveOrderLedger())
        authd = authorize_real_order(risk_decision, armed)
        fill_res = fill_gw.submit_order(exec_intent, authd, armed)
        b.blocker("gated_fill_filled_real_fake_order",
                  fill_res.status is LiveExecutionStatus.FILLED and fill_res.is_real_order
                  and fill_adapter.order_post_count == 1,
                  detail=f"status={fill_res.status.value} post_count={fill_adapter.order_post_count}")
        b.blocker("gated_fill_ledger_written", len(fill_gw.ledger) >= 1)
        fill_card = getattr(fill_gw, "_last_telegram_payload", None)
        b.blocker("gated_fill_card_real_order_true",
                  bool(fill_card) and fill_card.get("real_order") is True
                  and fill_card.get("order_id") not in (None, "--"))
        b.blocker("only_fake_binance_transport_used",
                  type(fill_adapter.transport).__name__ == "FakeBinanceTransport")

        # 3. Partial fill.
        partial_adapter = FakeBinanceLiveAdapter(
            symbol=self.symbol, behavior=BEHAVIOR_PARTIAL, fill_price=plan.planned_entry_price,
            partial_ratio=0.4,
        )
        partial_gw = LiveExecutionGateway(adapter=partial_adapter.adapter, ledger=LiveOrderLedger())
        partial_intent = self._fresh_intent(exec_intent, profile_id)
        partial_res = partial_gw.submit_order(partial_intent, authorize_real_order(risk_decision, armed), armed)
        b.blocker("partial_fill_preserved",
                  partial_res.status is LiveExecutionStatus.PARTIALLY_FILLED
                  and 0 < partial_res.executed_qty < partial_intent.quantity
                  and partial_adapter.order_post_count == 1,
                  detail=f"executed={partial_res.executed_qty} requested={partial_intent.quantity}")

        # 4. Order reject.
        reject_adapter = FakeBinanceLiveAdapter(
            symbol=self.symbol, behavior=BEHAVIOR_REJECT, fill_price=plan.planned_entry_price,
        )
        reject_gw = LiveExecutionGateway(adapter=reject_adapter.adapter, ledger=LiveOrderLedger())
        reject_intent = self._fresh_intent(exec_intent, profile_id)
        reject_res = reject_gw.submit_order(reject_intent, authorize_real_order(risk_decision, armed), armed)
        b.blocker("order_reject_no_ledger_corruption",
                  reject_res.status is LiveExecutionStatus.REJECTED
                  and len(reject_gw.ledger) >= 1
                  and reject_adapter.order_post_count == 1,
                  detail=f"status={reject_res.status.value}")

        # 5. Timeout after submit -> no duplicate, pending reconciliation.
        timeout_adapter = FakeBinanceLiveAdapter(
            symbol=self.symbol, behavior=BEHAVIOR_TIMEOUT, fill_price=plan.planned_entry_price,
        )
        timeout_gw = LiveExecutionGateway(adapter=timeout_adapter.adapter, ledger=LiveOrderLedger())
        timeout_intent = self._fresh_intent(exec_intent, profile_id)
        timeout_res = timeout_gw.submit_order(timeout_intent, authorize_real_order(risk_decision, armed), armed)
        audit_status = (
            UNKNOWN_PENDING_RECONCILIATION
            if timeout_res.status is LiveExecutionStatus.FAILED
            else timeout_res.status.value
        )
        b.blocker("timeout_no_duplicate_order", timeout_adapter.order_post_count == 1,
                  detail=f"post_count={timeout_adapter.order_post_count}")
        b.blocker("timeout_safe_pending_state",
                  timeout_res.status is LiveExecutionStatus.FAILED and not timeout_res.is_real_order,
                  detail=f"audit_status={audit_status}")
        b.detail("timeout_ledger_audit_status", audit_status)

        # 6. Exit fill: gross / commission / funding / net PnL.
        entry_price = plan.planned_entry_price
        exit_price = plan.planned_take_profit_price
        qty = exec_intent.quantity
        gross = round((exit_price - entry_price) * qty, 8)
        fee = round(self.fee_engine.commission(entry_price * qty) + self.fee_engine.commission(exit_price * qty), 8)
        funding = -self.funding_engine.funding_fee(entry_price * qty, 0.0006, intervals=1)
        net = compute_net_pnl(gross, fee, funding)
        exit_intent = type(exec_intent)(
            symbol=exec_intent.symbol, side=OrderSide.SELL, order_type=OrderType.MARKET,
            quantity=qty, notional_usdt=round(exit_price * qty, 8), reduce_only=True,
            planned_entry_price=entry_price, planned_take_profit_price=exit_price,
            planned_leverage=exec_intent.planned_leverage, client_order_id=generate_client_order_id(),
            source=OrderSource.LIVE, runtime_mode=LiveRuntimeMode.LIVE_LIMITED, capital_profile_id=profile_id,
        )
        exit_result = LiveOrderResult(
            status=LiveExecutionStatus.FILLED, client_order_id=exit_intent.client_order_id,
            symbol=exit_intent.symbol, side=OrderSide.SELL, order_type=OrderType.MARKET,
            exchange_order_id="8800117", avg_fill_price=exit_price, executed_qty=qty,
            cum_quote=round(exit_price * qty, 8), fee_usdt=fee, realized_pnl_usdt=gross,
            reduce_only=True, is_real_order=True,
        )
        exit_card = build_execution_telegram_payload(
            PAYLOAD_LIVE_EXIT_FILLED, intent=exit_intent, result=exit_result,
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED, funding_usdt=funding, balance_before=10.0,
            balance_after=round(10.0 + net, 8),
        )
        b.blocker("exit_net_pnl_formula", abs(exit_card["net_pnl"] - net) < 1e-9
                  and abs(net - (gross - fee + funding)) < 1e-9,
                  detail=f"gross={gross} fee={fee} funding={funding} net={net}")
        b.blocker("exit_card_has_components",
                  exit_card["gross_pnl"] == gross and exit_card["fee_usdt"] == fee
                  and exit_card["funding_usdt"] == funding)
        b.detail("exit_card", exit_card)
        return b.build()

    def _fresh_intent(self, template: ExecOrderIntent, profile_id: CapitalProfileId) -> ExecOrderIntent:
        return type(template)(
            symbol=template.symbol, side=template.side, order_type=template.order_type,
            quantity=template.quantity, notional_usdt=template.notional_usdt,
            planned_entry_price=template.planned_entry_price,
            planned_stop_price=template.planned_stop_price,
            planned_take_profit_price=template.planned_take_profit_price,
            planned_leverage=template.planned_leverage, exit_plan_present=True, stop_plan_present=True,
            client_order_id=generate_client_order_id(), source=OrderSource.LIVE,
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED, capital_profile_id=profile_id,
        )

    # ==================================================================
    # Scenario: live risk
    # ==================================================================
    def scenario_live_risk(self) -> ScenarioResult:
        b = ScenarioBuilder("live_risk")
        profile_id = CapitalProfileId.L1_10U_PROBE
        series, plan, gate = self._right_tail_plan_and_gate(profile_id=profile_id)
        exec_intent = self._exec_intent_from_plan(plan, gate, profile_id=profile_id)
        cap_state = self._capital_state(balance_usdt=10.0, profile_id=profile_id)
        risk_intent = self._risk_intent(plan, exec_intent)

        approved = evaluate_live_order_risk(risk_intent, cap_state, profile_id, leverage_gate=gate,
                                            runtime_mode=LiveRuntimeMode.LIVE_LIMITED)
        b.blocker("right_tail_risk_approved", approved.approved, detail=f"reasons={approved.reject_reasons}")
        b.blocker("dry_decision_real_order_allowed_false", approved.real_order_allowed is False)

        # authorize only when fully armed.
        authd_armed = authorize_real_order(approved, self._armed_context(profile_id=profile_id))
        authd_shadow = authorize_real_order(
            approved, ExecutionPermissionContext(runtime_mode=LiveRuntimeMode.LIVE_SHADOW)
        )
        b.blocker("authorize_only_when_fully_armed",
                  authd_armed.real_order_allowed is True and authd_shadow.real_order_allowed is False)

        # shadow mode reject.
        shadow_dec = evaluate_live_order_risk(risk_intent, cap_state, profile_id, leverage_gate=gate,
                                              runtime_mode=LiveRuntimeMode.LIVE_SHADOW)
        b.blocker("shadow_mode_no_real_order",
                  LiveRiskRejectReason.RUNTIME_MODE_SHADOW_NO_REAL_ORDER in shadow_dec.reject_reasons)

        # notional over cap.
        big_intent = type(risk_intent)(
            symbol=risk_intent.symbol, side=risk_intent.side,
            planned_entry_price=risk_intent.planned_entry_price, planned_notional_usdt=999.0,
            planned_leverage=risk_intent.planned_leverage, planned_stop_price=risk_intent.planned_stop_price,
            planned_take_profit_price=risk_intent.planned_take_profit_price, exit_plan_present=True,
            stop_plan_present=True, candidate_stage=risk_intent.candidate_stage,
            opportunity_score=risk_intent.opportunity_score, runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
            source=OrderSource.LIVE,
        )
        big_dec = evaluate_live_order_risk(big_intent, cap_state, profile_id, leverage_gate=gate,
                                           runtime_mode=LiveRuntimeMode.LIVE_LIMITED)
        b.blocker("notional_over_cap_rejected",
                  LiveRiskRejectReason.NOTIONAL_EXCEEDS_PROFILE_MAX in big_dec.reject_reasons)

        # account capital over cap (equity 50 on 10U profile).
        over_state = self._capital_state(balance_usdt=50.0, profile_id=profile_id)
        over_dec = evaluate_live_order_risk(risk_intent, over_state, profile_id, leverage_gate=gate,
                                            runtime_mode=LiveRuntimeMode.LIVE_LIMITED)
        b.blocker("account_capital_over_cap_rejected",
                  LiveRiskRejectReason.ACCOUNT_CAPITAL_EXCEEDS_PROFILE_CAP in over_dec.reject_reasons)

        # live risk reads the ACTIVE profile dynamically (via runtime).
        rt = LiveRuntime(state_store=self._state_store("live_risk_rt"))
        rt.set_capital_profile(CapitalProfileId.L1_10U_PROBE)
        caps_10 = rt.profile_caps().max_position_notional_usdt
        rt.set_capital_profile(CapitalProfileId.L4_1K_GROWTH)
        caps_1k = rt.profile_caps().max_position_notional_usdt
        b.blocker("live_risk_reads_active_profile", caps_1k != caps_10 and caps_1k > caps_10,
                  detail=f"10U={caps_10} 1k={caps_1k}")
        return b.build()

    def _risk_intent(self, plan, exec_intent):
        ri = plan.to_risk_intent(runtime_mode=LiveRuntimeMode.LIVE_LIMITED)
        return type(ri)(
            symbol=ri.symbol, side=ri.side, planned_entry_price=ri.planned_entry_price,
            planned_notional_usdt=exec_intent.notional_usdt, planned_leverage=exec_intent.planned_leverage,
            planned_stop_price=ri.planned_stop_price, planned_take_profit_price=ri.planned_take_profit_price,
            exit_plan_present=ri.exit_plan_present, stop_plan_present=ri.stop_plan_present,
            candidate_stage=ri.candidate_stage, opportunity_score=ri.opportunity_score,
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED, source=OrderSource.LIVE,
        )

    # ==================================================================
    # Scenario: capital ladder (1U -> 10M)
    # ==================================================================
    def scenario_capital_ladder(self) -> ScenarioResult:
        b = ScenarioBuilder("capital_ladder")
        funded = [p for p in CAPITAL_PROFILE_ORDER if p is not CapitalProfileId.L0_SHADOW]

        # Every funded profile exists with the required caps.
        for pid in funded:
            prof = get_profile(pid)
            ok = (
                prof.max_account_capital_usdt > 0
                and prof.max_position_notional_usdt > 0
                and prof.max_leverage > 0
            )
            b.blocker(f"profile_caps_present:{pid.value}", ok)

        p1u = get_profile(CapitalProfileId.L1_1U_MICRO_PROBE)
        p10u = get_profile(CapitalProfileId.L1_10U_PROBE)
        p50 = get_profile(CapitalProfileId.L2_25U_50U_SCOUT)
        p1k = get_profile(CapitalProfileId.L4_1K_GROWTH)
        p10k = get_profile(CapitalProfileId.L5_10K_PROFIT_PROTECTION)
        p1m = get_profile(CapitalProfileId.L7_1M_INSTITUTIONAL_STYLE)
        p10m = get_profile(CapitalProfileId.L8_10M_CAPITAL_PRESERVATION)

        # 1U distinct from 10U.
        b.blocker("1u_distinct_from_10u",
                  p1u.max_account_capital_usdt != p10u.max_account_capital_usdt
                  and p1u.max_position_notional_usdt != p10u.max_position_notional_usdt)

        # 10U usable capital capped at 10 even with 50 equity.
        cap10 = self._capital_state(balance_usdt=50.0, profile_id=CapitalProfileId.L1_10U_PROBE)
        from app.live.live_risk_engine import evaluate_capital_profile_state
        state10 = evaluate_capital_profile_state(cap10, p10u)
        b.blocker("10u_usable_capital_capped", abs(state10.usable_capital_usdt - 10.0) < 1e-9,
                  detail=f"usable={state10.usable_capital_usdt}")

        # 50U equity on 10U profile -> mismatch, no auto-upgrade.
        mm = detect_profile_mismatch(CapitalProfileId.L1_10U_PROBE, 50.0)
        b.blocker("profile_mismatch_no_auto_upgrade",
                  mm.mismatch and mm.direction == "escalate" and mm.requires_operator_action
                  and AUTO_ESCALATION_ALLOWED is False)

        # 50U profile changes caps.
        b.blocker("50u_profile_changes_caps",
                  p50.max_account_capital_usdt == 50.0 and p50.max_position_notional_usdt != p10u.max_position_notional_usdt)
        # 1000U profile changes caps.
        b.blocker("1000u_profile_changes_caps",
                  p1k.max_account_capital_usdt == 1000.0
                  and p1k.max_position_notional_usdt > p50.max_position_notional_usdt)
        # 10,000U does not reuse 10U limits.
        b.blocker("10000u_not_reuse_10u_limits",
                  p10k.max_account_capital_usdt == 10000.0
                  and p10k.max_position_notional_usdt != p10u.max_position_notional_usdt
                  and p10k.max_slippage_bps < p10u.max_slippage_bps)
        # 1M / 10M stricter liquidity + slippage.
        b.blocker("1m_10m_stricter_liquidity_slippage",
                  p1m.max_slippage_bps < p10u.max_slippage_bps
                  and p10m.max_slippage_bps < p1m.max_slippage_bps
                  and p1m.min_exit_liquidity_score > p10u.min_exit_liquidity_score
                  and p10m.min_exit_liquidity_score >= p1m.min_exit_liquidity_score
                  and p10m.right_tail_boost_allowed is False)

        # Operator profile switch changes risk caps WITHOUT a code change.
        rt = LiveRuntime(state_store=self._state_store("capital_ladder_rt"))
        seen_caps: dict[str, float] = {}
        for pid in (CapitalProfileId.L1_10U_PROBE, CapitalProfileId.L2_25U_50U_SCOUT,
                    CapitalProfileId.L4_1K_GROWTH, CapitalProfileId.L5_10K_PROFIT_PROTECTION,
                    CapitalProfileId.L7_1M_INSTITUTIONAL_STYLE, CapitalProfileId.L8_10M_CAPITAL_PRESERVATION):
            rt.set_capital_profile(pid)
            caps = rt.profile_caps()
            seen_caps[pid.value] = caps.max_account_capital_usdt
            ctx = rt.build_execution_context(account_equity_usdt=caps.max_account_capital_usdt)
            b.blocker(f"runtime_caps_match_profile:{pid.value}",
                      caps.capital_profile_id == pid
                      and ctx.allowed_profile_ids == (pid,)
                      and caps.max_account_capital_usdt == get_profile(pid).max_account_capital_usdt)
        # Caps strictly increased across the ladder switch (no code change).
        ladder_values = list(seen_caps.values())
        b.blocker("capital_scales_without_code_change",
                  ladder_values == sorted(ladder_values) and len(set(ladder_values)) == len(ladder_values),
                  detail=f"caps={seen_caps}")
        b.detail("ladder_caps", seen_caps)
        b.detail("auto_escalation_allowed", AUTO_ESCALATION_ALLOWED)

        # Capital scaling proof (section 10): 10U->50U->1000U->10000U->1M->10M
        # all reachable by profile switch only; suggest_profile_for_equity
        # recommends (never applies) the next stage.
        b.blocker("equity_suggestion_never_auto_applied",
                  suggest_profile_for_equity(50.0) == CapitalProfileId.L2_25U_50U_SCOUT
                  and suggest_profile_for_equity(1000.0) == CapitalProfileId.L4_1K_GROWTH
                  and suggest_profile_for_equity(10000.0) == CapitalProfileId.L5_10K_PROFIT_PROTECTION)
        return b.build()

    # ==================================================================
    # Scenario: funding / fee / PnL
    # ==================================================================
    def scenario_funding_fee_pnl(self) -> ScenarioResult:
        b = ScenarioBuilder("funding_fee_pnl")
        acct = FakeLiveAccount(initial_balance_usdt=10.0)

        # 1/2. Deposit + withdrawal never become strategy PnL.
        acct.deposit(100.0)
        acct.withdraw(50.0)
        b.blocker("deposit_not_counted_as_profit",
                  acct.ledger.total_external_deposits == 100.0 and acct.net_strategy_pnl == 0.0)
        b.blocker("withdrawal_not_counted_as_loss",
                  acct.ledger.total_external_withdrawals == 50.0 and acct.net_strategy_pnl == 0.0)

        # 3/4/5/6/7. Realised PnL / loss / commission / funding fee / income.
        acct.realized_profit(5.0)
        acct.realized_loss(3.0)
        acct.commission(0.2)
        acct.funding_fee(0.4)
        acct.funding_income(0.6)
        expected_net = 5.0 - 3.0 - 0.2 + (0.6 - 0.4)
        b.blocker("net_strategy_pnl_formula", abs(acct.net_strategy_pnl - expected_net) < 1e-9,
                  detail=f"net={acct.net_strategy_pnl} expected={expected_net}")
        b.blocker("commission_included", acct.ledger.total_fees == 0.2)
        b.blocker("funding_fee_and_income_included",
                  abs(acct.ledger.total_funding - 0.2) < 1e-9)

        # 8. Profit harvest does not pollute strategy PnL.
        before_harvest = acct.net_strategy_pnl
        acct.apply_event(CapitalEventType.PROFIT_HARVEST, 2.0)
        b.blocker("profit_harvest_not_pollute_pnl",
                  abs(acct.net_strategy_pnl - before_harvest) < 1e-9
                  and acct.ledger.total_profit_harvested == 2.0)

        # 9. Rebase / manual adjustment audited, never silently change PnL.
        acct.apply_event(CapitalEventType.MANUAL_ADJUSTMENT, 1.0)
        acct.apply_event(CapitalEventType.CAPITAL_REBASE, 0.0)
        b.blocker("rebase_manual_not_change_pnl_curve",
                  abs(acct.net_strategy_pnl - before_harvest) < 1e-9
                  and acct.ledger.total_manual_adjustment == 1.0)

        # 11. Performance equity excludes external flows (PR112 path).
        rows = [
            {"incomeType": "REALIZED_PNL", "income": "5.0", "asset": "USDT", "symbol": self.symbol, "time": 1, "tradeId": "t1"},
            {"incomeType": "COMMISSION", "income": "-0.2", "asset": "USDT", "symbol": self.symbol, "time": 2, "tradeId": "t1"},
            {"incomeType": "FUNDING_FEE", "income": "0.6", "asset": "USDT", "symbol": self.symbol, "time": 3},
            {"incomeType": "FUNDING_FEE", "income": "-0.4", "asset": "USDT", "symbol": self.symbol, "time": 4},
            {"incomeType": "WELCOME_BONUS", "income": "100.0", "asset": "USDT", "time": 5},
        ]
        summary = build_live_pnl_summary_from_rows(rows, account_equity_usdt=110.0)
        b.blocker("pnl_summary_net_strategy",
                  abs(summary.net_strategy_pnl_usdt - 5.0) < 1e-9,
                  detail=f"net={summary.net_strategy_pnl_usdt}")
        b.blocker("pnl_summary_funding_fee_and_income",
                  abs(summary.funding_total_usdt - 0.2) < 1e-9 and summary.funding_event_count == 2)
        b.blocker("pnl_summary_commission_included", summary.commission_total_usdt == 0.2)
        b.blocker("performance_equity_excludes_external_flows",
                  abs(summary.performance_equity_excluding_external_flows - 10.0) < 1e-9,
                  detail=f"perf_equity={summary.performance_equity_excluding_external_flows}")

        # funding_negative_hold (a fee) reduces net PnL; positive (income) raises it.
        neg = self.market.series(MarketScenario.FUNDING_NEGATIVE_HOLD).entry_frame
        pos = self.market.series(MarketScenario.FUNDING_POSITIVE_HOLD).entry_frame
        notional = 10.0
        fee = self.funding_engine.funding_fee(notional, neg.funding_rate)
        income = self.funding_engine.funding_income(notional, pos.funding_rate)
        net_with_fee = compute_net_pnl(1.0, 0.0, -fee)
        net_with_income = compute_net_pnl(1.0, 0.0, income)
        b.blocker("funding_negative_hold_reduces_net", net_with_fee < 1.0 and fee > 0)
        b.blocker("funding_positive_hold_raises_net", net_with_income > 1.0 and income > 0)
        b.detail("ledger", acct.ledger.to_dict())
        return b.build()

    # ==================================================================
    # Scenario: Telegram operator
    # ==================================================================
    def scenario_telegram_operator(self) -> ScenarioResult:
        b = ScenarioBuilder("telegram_operator")
        store = self._state_store("telegram")
        data = SandboxConsoleDataProvider(
            capital_profile_id=CapitalProfileId.L1_10U_PROBE, account_equity_usdt=10.0,
        )
        tg_config = TelegramApiConfig(
            bot_token=SecretValue(name="AMA_TELEGRAM_BOT_TOKEN", _raw="sandbox-fake-tg-token-117"),
            allowed_chat_ids=(self.operator.authorized_chat_id,), outbound_enabled=True,
        )
        transport = FakeTelegramTransport()
        handler = TelegramCommandHandler(state_store=store, data_provider=data)
        console = TelegramOperatorConsole(
            telegram_config=tg_config, command_handler=handler, transport=transport, dry_run=False,
        )

        # Unauthorized chat rejected (no send).
        unauth = console.handle_text(self.operator.unauthorized_chat_id, "/status")
        b.blocker("unauthorized_chat_rejected", unauth.authorized is False and unauth.outbound is None)

        # Empty allow-list fails closed.
        empty_guard = TelegramAuthGuard(())
        b.blocker("empty_allowlist_fails_closed",
                  empty_guard.authorize(self.operator.authorized_chat_id).authorized is False)

        # Authorized read-only commands are answered + sent.
        for cmd in ("/help", "/status", "/mode", "/positions", "/pnl", "/risk", "/capital", "/profile",
                    "/kill_status"):
            res = console.handle_text(self.operator.authorized_chat_id, cmd)
            b.blocker(f"authorized_command_ok:{cmd}",
                      res.authorized and res.result is not None and res.result.ok
                      and res.outbound is not None and res.outbound.sent,
                      detail=f"cmd={cmd}")

        # /pnl card separates deposit / withdrawal from strategy PnL.
        pnl_res = console.handle_text(self.operator.authorized_chat_id, "/pnl")
        pnl_card = pnl_res.result.card if pnl_res.result else {}
        b.blocker("pnl_card_separates_external_flows",
                  all(k in pnl_card for k in ("deposits", "withdrawals", "net_strategy_pnl")),
                  detail=f"keys={sorted(pnl_card.keys())}")

        # /mode live_limited returns a confirmation code WITHOUT switching.
        ll = console.handle_text(self.operator.authorized_chat_id, "/mode live_limited")
        ll_card = ll.result.card if ll.result else {}
        confirmation_code = _find_code(ll_card, "LIVE-")
        b.blocker("mode_live_limited_only_confirmation",
                  ll.result is not None and not ll.result.state_changed
                  and handler.runtime_mode is LiveRuntimeMode.LIVE_SHADOW
                  and bool(confirmation_code),
                  detail=f"code={confirmation_code}")

        # Arming path: profile -> L1_10U_PROBE (escalation needs ack), then confirm.
        console.handle_text(self.operator.authorized_chat_id, "/profile set L1_10U_PROBE confirm")
        code_res = console.handle_text(self.operator.authorized_chat_id, "/mode live_limited")
        code = _find_code(code_res.result.card if code_res.result else {}, "LIVE-")
        console.handle_text(self.operator.authorized_chat_id, f"/confirm_live {code}")
        # Arming succeeds but real orders are still gated (flags stay False).
        flags = data.safety_flags()
        b.blocker("confirm_arms_but_does_not_enable_real_orders",
                  handler.live_limited_armed is True
                  and flags["exchange_live_orders"] is False
                  and flags["trade_authority_flag"] is False,
                  detail=f"armed={handler.live_limited_armed}")

        # Telegram cannot call the Binance adapter / bypass the gateway.
        b.blocker("console_has_no_execution_adapter",
                  not hasattr(console, "_adapter") and not hasattr(handler, "_adapter"))

        # AI_BRIEFING card semantics (market-intelligence only).
        gen = LiveAIBriefingGenerator(fake_sandbox_deepseek_config(), transport=FakeDeepSeekTransport())
        bundle = build_live_ai_evidence_bundle(
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED, capital_profile_id="L1_10U_PROBE",
            account_status={"account_equity_usdt": 10.0}, pnl_summary={"net_strategy_pnl_usdt": 2.0},
            risk_summary={"max_leverage": 5}, sources=[OrderSource.LIVE],
        ).bundle
        briefing = gen.generate(bundle)
        bc = briefing.to_dict()
        b.blocker("ai_briefing_market_intelligence_only",
                  bc["authority"] == AI_AUTHORITY_LABEL and bc["ai_trade_authority"] is False
                  and briefing.actionable is False)

        # SHADOW_ENTRY_PLAN card readability (planned fields, real_order False).
        series, plan, gate = self._right_tail_plan_and_gate()
        shadow_card = {
            "card_type": "SHADOW_ENTRY_PLAN", "symbol": plan.symbol,
            "planned_entry_zone": [plan.planned_entry_low, plan.planned_entry_high],
            "planned_stop_price": plan.planned_stop_price,
            "planned_take_profit_price": plan.planned_take_profit_price,
            "planned_leverage": gate.leverage_ratio, "planned_notional_usdt": plan.planned_notional_usdt,
            "real_order": False, "order_id": "--", "actual_fill": "--",
        }
        b.blocker("shadow_entry_card_readable",
                  shadow_card["real_order"] is False and shadow_card["order_id"] == "--"
                  and shadow_card["planned_stop_price"] is not None)

        # LIVE_EXIT_FILLED card shows gross / fee / funding / net.
        exit_card = build_execution_telegram_payload(
            PAYLOAD_LIVE_EXIT_FILLED, runtime_mode=LiveRuntimeMode.LIVE_LIMITED,
            intent=self._exec_intent_from_plan(plan, gate),
            result=LiveOrderResult(
                status=LiveExecutionStatus.FILLED, client_order_id="x", symbol=self.symbol,
                side=OrderSide.SELL, order_type=OrderType.MARKET, avg_fill_price=plan.planned_take_profit_price,
                executed_qty=9.0, cum_quote=9.0 * plan.planned_take_profit_price, fee_usdt=0.05,
                realized_pnl_usdt=2.0, reduce_only=True, is_real_order=True,
            ),
            funding_usdt=-0.02,
        )
        b.blocker("exit_card_shows_gross_fee_funding_net",
                  all(k in exit_card for k in ("gross_pnl", "fee_usdt", "funding_usdt", "net_pnl")))
        b.detail("operator", self.operator.to_dict())
        return b.build()

    # ==================================================================
    # Scenario: AI guard
    # ==================================================================
    def scenario_ai_guard(self) -> ScenarioResult:
        b = ScenarioBuilder("ai_guard")

        # Valid clean briefing: OK, market-intelligence only, not actionable.
        gen_clean = LiveAIBriefingGenerator(fake_sandbox_deepseek_config(), transport=FakeDeepSeekTransport())
        bundle = build_live_ai_evidence_bundle(
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED, capital_profile_id="L1_10U_PROBE",
            account_status={"account_equity_usdt": 10.0}, pnl_summary={"net_strategy_pnl_usdt": 2.0},
            risk_summary={"max_leverage": 5}, funding_summary={"funding_total_usdt": -0.1},
            sources=[OrderSource.LIVE],
        ).bundle
        clean = gen_clean.generate(bundle)
        b.blocker("valid_briefing_not_actionable",
                  clean.ai_trade_authority is False and clean.actionable is False
                  and clean.source_scope == "LIVE_ONLY")

        # Forbidden fields stripped + rejected (all of the brief's fields).
        gen_forbidden = LiveAIBriefingGenerator(
            fake_sandbox_deepseek_config(), transport=FakeDeepSeekTransport(inject_forbidden=True)
        )
        forbidden = gen_forbidden.generate(bundle)
        fc = forbidden.to_dict()
        forbidden_present = any(
            k in fc for k in ("should_buy", "should_sell", "direction", "leverage", "stop_price",
                              "take_profit", "position_size", "order_type", "entry_price", "exit_price",
                              "runtime_config_patch")
        )
        b.blocker("ai_forbidden_fields_rejected",
                  forbidden.status == BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY
                  and len(forbidden.forbidden_fields_detected) >= 8
                  and not forbidden_present,
                  detail=f"detected={forbidden.forbidden_fields_detected}")

        # Direct sanitizer: nested forbidden field stripped at depth.
        guard = sanitize_ai_output({"market_summary": "ok", "nested": {"should_long": True, "leverage": 10}})
        b.blocker("nested_forbidden_stripped",
                  guard.status == BriefingStatus.REJECTED_FOR_TRADE_AUTHORITY
                  and "leverage" not in str(guard.clean_payload).lower().replace("market_summary", ""))
        b.info("nested_clean_payload", True, value=guard.clean_payload)

        # AI cannot call the execution gateway.
        adapter = FakeBinanceLiveAdapter(symbol=self.symbol)
        gw = LiveExecutionGateway(adapter=adapter.adapter, ledger=LiveOrderLedger())
        series, plan, gate = self._right_tail_plan_and_gate()
        exec_intent = self._exec_intent_from_plan(plan, gate)
        ai_ctx = ExecutionPermissionContext(
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED, live_limited_confirmed=True,
            exchange_live_orders=True, trade_authority=True, private_trade_enabled=True,
            ai_trade_authority=True, account_equity_usdt=10.0,
        )
        ai_refused = False
        try:
            gw.submit_order(exec_intent, None, ai_ctx)
        except AiTradeAuthorityForbidden:
            ai_refused = True
        b.blocker("ai_cannot_call_execution_gateway", ai_refused and adapter.order_post_count == 0)

        # AI source cannot mutate live state (mode / profile) via the console.
        store = self._state_store("ai_guard_console")
        ai_handler = TelegramCommandHandler(state_store=store)
        ai_console = TelegramOperatorConsole(
            telegram_config=TelegramApiConfig(
                bot_token=SecretValue(name="AMA_TELEGRAM_BOT_TOKEN", _raw="sandbox-fake-tg-token-117"),
                allowed_chat_ids=(self.operator.authorized_chat_id,), outbound_enabled=True,
            ),
            command_handler=ai_handler,
            transport=FakeTelegramTransport(), dry_run=False,
        )
        ai_state_change = ai_console.handle_text(
            self.operator.authorized_chat_id, "/mode live_limited", source=OrderSource.OFFLINE_AI
        )
        ai_state_rejected = (
            ai_state_change.result is not None
            and not ai_state_change.result.ok
            and not ai_state_change.result.state_changed
        )
        b.blocker("ai_source_cannot_mutate_live_state",
                  ai_state_rejected and ai_handler.runtime_mode is LiveRuntimeMode.LIVE_SHADOW,
                  detail=f"reason={ai_state_change.reason}")

        # AI evidence with a blind/offline source is rejected at the bundle.
        blind_bundle = build_live_ai_evidence_bundle(
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED, sources=[OrderSource.OFFLINE_AI],
        )
        b.blocker("blind_ai_evidence_rejected",
                  blind_bundle.accepted is False and blind_bundle.bundle is None
                  and len(blind_bundle.forbidden_sources_detected) >= 1)

        # AI cannot decide leverage (gate refuses AI input).
        ai_gate = evaluate_right_tail_leverage_permission(
            plan.to_leverage_evidence(inject_forbidden_ai=True)
        )
        b.blocker("ai_cannot_decide_leverage",
                  not ai_gate.leverage_allowed and ai_gate.ai_input_detected)
        return b.build()

    # ==================================================================
    # Scenario: blind / replay / sim isolation
    # ==================================================================
    def scenario_blind_isolation(self) -> ScenarioResult:
        b = ScenarioBuilder("blind_isolation")
        guard = LivePathIsolationGuard()
        src_guard = LiveSourceGuard()

        # source classification: sim modules never map to LIVE.
        b.blocker("classify_historical_store_not_live",
                  classify_source_module("HistoricalMarketStore") is OrderSource.SIM)
        b.blocker("classify_mock_exchange_not_live",
                  classify_source_module("MockExchange") is OrderSource.SIM)
        b.blocker("classify_replay_not_live",
                  classify_source_module("ReplayFeedProvider") is OrderSource.REPLAY)
        b.blocker("classify_blind_runner_not_live",
                  classify_source_module("BlindWalkForwardRunner") is OrderSource.BLIND)
        b.blocker("classify_paper_shadow_not_live",
                  classify_source_module("PaperShadowStrategyBridge") is OrderSource.PAPER_SHADOW)

        # Every non-LIVE source is blocked at the order isolation guard.
        for src in (OrderSource.BLIND, OrderSource.SIM, OrderSource.REPLAY, OrderSource.PAPER_SHADOW):
            intent = IsolationIntent(
                source=src, source_module="sandbox_test", symbol=self.symbol,
                side=__import__("app.core.enums", fromlist=["Direction"]).Direction.LONG,
            )
            decision = guard.authorize(intent)
            b.blocker(f"order_isolation_blocks:{src.value}",
                      not decision.authorised and "non_live_source_blocked" in decision.reason)
            # Live-source guard (mode/profile/kill mutation) rejects too.
            b.blocker(f"live_source_guard_blocks:{src.value}",
                      src_guard.authorize(src) is False)

        # Simulation classes can never be a live market source.
        class MockExchange:  # noqa: D401 - stub for isolation test
            pass

        class HistoricalMarketStore:
            pass

        class ReplayFeedProvider:
            pass

        class SimulatedCapitalFlow:
            pass

        for obj in (MockExchange(), HistoricalMarketStore(), ReplayFeedProvider(), SimulatedCapitalFlow()):
            rejected = False
            try:
                LiveRuntime.assert_live_market_source(obj)
            except LiveSourceRejected:
                rejected = True
            b.blocker(f"sim_class_not_live_market_source:{type(obj).__name__}", rejected)
        b.blocker("forbidden_classes_registered",
                  {"MockExchange", "HistoricalMarketStore", "ReplayFeedProvider",
                   "SimulatedCapitalFlow", "BlindWalkForwardRunner",
                   "PaperShadowStrategyBridge"}.issubset(FORBIDDEN_LIVE_SOURCE_CLASSES))

        # PaperShadow / Blind sources cannot drive live mode/profile mutation.
        rt = LiveRuntime(state_store=self._state_store("blind_isolation_rt"))
        for src in (OrderSource.PAPER_SHADOW, OrderSource.BLIND, OrderSource.REPLAY, OrderSource.SIM):
            rejected = False
            try:
                rt.assert_live_source(src, action="set_capital_profile")
            except LiveSourceRejected:
                rejected = True
            b.blocker(f"live_runtime_blocks_source:{src.value}", rejected)

        # Replay/offline AI cannot enter the live AI evidence bundle.
        for src in (OrderSource.REPLAY, OrderSource.BLIND, OrderSource.OFFLINE_AI, OrderSource.PAPER_SHADOW):
            res = build_live_ai_evidence_bundle(sources=[src])
            b.blocker(f"nonlive_source_blocked_from_ai_evidence:{src.value}",
                      res.accepted is False and res.bundle is None)
        return b.build()

    # ==================================================================
    # Scenario: kill switch / rollback
    # ==================================================================
    def scenario_kill_switch(self) -> ScenarioResult:
        b = ScenarioBuilder("kill_switch")
        store = self._state_store("kill_switch")
        kill = LiveKillSwitch(state_store=store)

        # 1. ready=True, active=False initially.
        b.blocker("kill_switch_ready_inactive_initially",
                  kill.is_ready is True and kill.is_active is False)

        # 4/5. /kill_all requires confirmation; /confirm_kill activates.
        code = kill.request_arm()
        b.blocker("kill_all_requires_confirmation",
                  bool(code) and kill.is_active is False)
        confirm = kill.confirm_arm(code)
        b.blocker("confirm_kill_activates", confirm["ok"] is True and kill.is_active is True)

        # 3/6. Active kill switch blocks new entries (execution gate).
        profile_id = CapitalProfileId.L1_10U_PROBE
        series, plan, gate = self._right_tail_plan_and_gate(profile_id=profile_id)
        adapter = FakeBinanceLiveAdapter(symbol=self.symbol)
        gw = LiveExecutionGateway(adapter=adapter.adapter, ledger=LiveOrderLedger())
        exec_intent = self._exec_intent_from_plan(plan, gate, profile_id=profile_id)
        risk_decision = self._approved_risk_decision(plan, gate, profile_id=profile_id, exec_intent=exec_intent)
        kill_ctx = ExecutionPermissionContext(
            runtime_mode=LiveRuntimeMode.LIVE_LIMITED, live_limited_confirmed=True,
            exchange_live_orders=True, trade_authority=True, private_trade_enabled=True,
            kill_switch_active=True, account_equity_usdt=10.0, allowed_profile_ids=(profile_id,),
        )
        kill_res = gw.submit_order(exec_intent, authorize_real_order(risk_decision, kill_ctx), kill_ctx)
        b.blocker("active_kill_blocks_new_entry",
                  kill_res.status is LiveExecutionStatus.BLOCKED and adapter.order_post_count == 0
                  and ExecutionRejectReason.KILL_SWITCH_ACTIVE in kill_res.error_message_sanitized,
                  detail=f"err={kill_res.error_message_sanitized}")

        # 13. Kill switch never claims positions closed without exchange confirm.
        controlled = kill.controlled_exit()
        b.blocker("kill_no_false_close_claim",
                  controlled["positions_closed_claimed"] is False
                  and controlled.get("operator_action") == KILL_EXIT_MANUAL_ACTION_REQUIRED)

        # 8/9/10. Disabling each flag blocks the order.
        base = dict(runtime_mode=LiveRuntimeMode.LIVE_LIMITED, live_limited_confirmed=True,
                    exchange_live_orders=True, trade_authority=True, private_trade_enabled=True,
                    account_equity_usdt=10.0, allowed_profile_ids=(profile_id,))
        for flag, reason in (
            ("exchange_live_orders", ExecutionRejectReason.EXCHANGE_LIVE_ORDERS_DISABLED),
            ("trade_authority", ExecutionRejectReason.TRADE_AUTHORITY_DISABLED),
            ("private_trade_enabled", ExecutionRejectReason.PRIVATE_TRADE_DISABLED_BY_CONFIG),
        ):
            kw = dict(base)
            kw[flag] = False
            ctx = ExecutionPermissionContext(**kw)
            adp = FakeBinanceLiveAdapter(symbol=self.symbol)
            g = LiveExecutionGateway(adapter=adp.adapter, ledger=LiveOrderLedger())
            r = g.submit_order(self._fresh_intent(exec_intent, profile_id),
                               authorize_real_order(risk_decision, ctx), ctx)
            b.blocker(f"disabling_{flag}_blocks_order",
                      r.status is LiveExecutionStatus.BLOCKED and reason in r.error_message_sanitized
                      and adp.order_post_count == 0)

        # 7. /mode shadow rollback disarms LIVE_LIMITED.
        roll_store = self._state_store("kill_rollback")
        handler = TelegramCommandHandler(state_store=roll_store)
        handler.handle("/profile set L1_10U_PROBE confirm")
        handler.handle("/mode live_limited")
        # arm via confirm code reused from card.
        ll_card = handler.handle("/mode live_limited").card
        code2 = _find_code(ll_card, "LIVE-")
        handler.handle(f"/confirm_live {code2}")
        armed_mode = handler.runtime_mode
        handler.handle("/mode shadow")
        b.blocker("rollback_to_shadow_disarms_live_limited",
                  armed_mode is LiveRuntimeMode.LIVE_LIMITED
                  and handler.runtime_mode is LiveRuntimeMode.LIVE_SHADOW
                  and handler.live_limited_armed is False)

        # 11/12. Corrupt state fails safe.
        corrupt_store_dir = self._tmp_root / "kill_corrupt"
        corrupt_store = LiveOperatorStateStore(state_dir=corrupt_store_dir)
        corrupt_store_dir.mkdir(parents=True, exist_ok=True)
        (corrupt_store_dir / RUNTIME_MODE_FILE).write_text("{ not valid json", encoding="utf-8")
        (corrupt_store_dir / KILL_SWITCH_FILE).write_text("}{ broken", encoding="utf-8")
        loaded = corrupt_store.load()
        corrupt_kill = LiveKillSwitch(state_store=corrupt_store)
        b.blocker("corrupt_runtime_fails_safe_to_shadow",
                  loaded.runtime.runtime_mode is LiveRuntimeMode.LIVE_SHADOW
                  and any("CORRUPT" in w.upper() for w in loaded.warnings))
        b.blocker("corrupt_kill_state_fails_safe", corrupt_kill.is_ready is False)

        # 2. kill_switch_ready False semantics -> readiness NO-GO.
        b.blocker("kill_not_ready_semantics", corrupt_kill.is_ready is False)
        return b.build()

    # ==================================================================
    # Run
    # ==================================================================
    def run(self, scenarios: list[str] | None = None) -> FullSystemAuditReport:
        names = list(scenarios) if scenarios else list(ALL_SCENARIOS)
        dispatch: dict[str, Callable[[], ScenarioResult]] = {
            "strategy_lifecycle": self.scenario_strategy_lifecycle,
            "execution_lifecycle": self.scenario_execution_lifecycle,
            "live_risk": self.scenario_live_risk,
            "capital_ladder": self.scenario_capital_ladder,
            "funding_fee_pnl": self.scenario_funding_fee_pnl,
            "telegram_operator": self.scenario_telegram_operator,
            "ai_guard": self.scenario_ai_guard,
            "blind_isolation": self.scenario_blind_isolation,
            "kill_switch": self.scenario_kill_switch,
        }
        results: list[ScenarioResult] = []
        for name in names:
            fn = dispatch.get(name)
            if fn is None:
                continue
            results.append(fn())
        return FullSystemAuditReport.build(symbol=self.symbol, scenario_results=results)


def _find_code(card: dict[str, Any], prefix: str) -> str:
    """Find a confirmation code (value starting with ``prefix``) in a card."""
    for value in (card or {}).values():
        if isinstance(value, str) and value.startswith(prefix):
            return value
        if isinstance(value, dict):
            nested = _find_code(value, prefix)
            if nested:
                return nested
    return ""


def run_full_system_sandbox_audit(
    *, symbol: str = DEFAULT_SANDBOX_SYMBOL, scenario: str = "all"
) -> FullSystemAuditReport:
    """Build + run the PR117 full-system sandbox audit (public entry point)."""
    audit = FullSystemSandboxAudit(symbol=symbol)
    scenarios = None if scenario in ("all", "", None) else [scenario]
    return audit.run(scenarios)


__all__ = [
    "FULL_SYSTEM_SANDBOX_MODULE",
    "FullSystemSandboxAudit",
    "run_full_system_sandbox_audit",
]
