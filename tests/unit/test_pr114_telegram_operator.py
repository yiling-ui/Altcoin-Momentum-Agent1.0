"""PR114 - Telegram Operator Console v0 + Live Funding Attribution +
Operator Workflow + Blind/Replay/Sim Isolation hardening.

EVERY test uses a fake Telegram transport + fake live state only. No
real Telegram / Binance API call is ever made and no real order is ever
sent. The numbered tests map to the brief's two "Add tests" lists: the
main operator-console list (1..32) and the isolation list (I1..I13).
"""

from __future__ import annotations

import tempfile

import pytest

from app.core.enums import LiveRuntimeMode, OrderSource
from app.core.errors import LiveSourceRejected, TelegramUnauthorizedCommand
from app.core.events import Event, EventType
from app.live.api_config import LiveApiConfig
from app.live.binance_income import classify_income_rows
from app.live.funding_attribution import (
    FillRef,
    FundingAttributionOutcome,
    PositionInterval,
    attribute_funding_events,
)
from app.live.telegram_auth import LiveSourceGuard, TelegramAuthGuard
from app.live.telegram_commands import (
    LiveConsoleDataProvider,
    TelegramCommandHandler,
    parse_command,
)
from app.live.telegram_formatters import (
    CardType,
    build_capital_event_detected_card,
    build_funding_event_attributed_card,
    build_live_risk_reject_card,
    build_shadow_entry_plan_card,
    build_pnl_card,
)
from app.live.telegram_operator import InboundUpdate, TelegramOperatorConsole
from app.live.telegram_state import (
    CapitalProfileStateRecord,
    ConfirmationState,
    LiveOperatorStateStore,
    RuntimeModeState,
)

SHADOW = LiveRuntimeMode.LIVE_SHADOW
LIMITED = LiveRuntimeMode.LIVE_LIMITED


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------
class FakeEventRepo:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, event: Event) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [e.event_type.value for e in self.events]


class FakeTransport:
    """Records (method, body); never opens a socket."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, method, url, body):
        self.calls.append((method, dict(body)))
        return {"ok": True, "result": []}


class StubDataProvider(LiveConsoleDataProvider):
    """A controllable data provider for the status / pnl / risk cards."""

    def __init__(self, **kw) -> None:
        self._d = kw

    def safety_flags(self):
        return {
            "exchange_live_orders": self._d.get("exchange_live_orders", False),
            "trade_authority_flag": self._d.get("trade_authority_flag", False),
            "private_trade_enabled": self._d.get("private_trade_enabled", False),
            "binance_public_status": self._d.get("binance_public_status", "PASS"),
            "binance_private_read_status": self._d.get("binance_private_read_status", "SKIPPED"),
            "telegram_outbound_status": self._d.get("telegram_outbound_status", "DISABLED"),
            "deepseek_status": self._d.get("deepseek_status", "SKIPPED"),
        }

    def account_status(self):
        return self._d.get("account_status", {})

    def positions(self):
        return self._d.get("positions", [])

    def pnl(self):
        return self._d.get("pnl", {})

    def risk(self):
        return self._d.get("risk", {})

    def capital(self):
        return self._d.get("capital", {})

    def account_equity_usdt(self):
        return self._d.get("account_equity_usdt")

    def funding_attribution_status(self):
        return self._d.get("funding_attribution_status")


def _store():
    return LiveOperatorStateStore(tempfile.mkdtemp())


def _handler(*, store=None, provider=None, repo=None, **kw):
    return TelegramCommandHandler(
        state_store=store or _store(),
        data_provider=provider or LiveConsoleDataProvider(),
        event_repo=repo,
        **kw,
    )


def _arm_live_limited(handler: TelegramCommandHandler) -> None:
    """Drive the handler into an armed LIVE_LIMITED on L1_10U_PROBE."""
    handler.handle("/profile set L1_10U_PROBE confirm")
    r = handler.handle("/mode live_limited")
    code = r.card["confirmation_code"]
    handler.handle("/confirm_live " + code)


def _config(**env):
    base = {}
    base.update(env)
    return LiveApiConfig.from_env(base)


# ===========================================================================
# 1: unauthorized chat id rejected
# ===========================================================================
def test_01_unauthorized_chat_rejected():
    repo = FakeEventRepo()
    cfg = _config(AMA_TELEGRAM_ALLOWED_CHAT_IDS="123", AMA_TELEGRAM_BOT_TOKEN="1:tok")
    console = TelegramOperatorConsole(config=cfg, state_store=_store(), event_repo=repo)
    handled = console.handle_text("999", "/status")
    assert handled.authorized is False
    assert handled.reason == "chat_id_not_in_allowlist"
    assert EventType.TELEGRAM_UNAUTHORIZED_COMMAND.value in repo.types()
    # The auth guard itself raises for the hard-stop variant.
    guard = TelegramAuthGuard(["123"])
    with pytest.raises(TelegramUnauthorizedCommand):
        guard.assert_authorized("999")


# ===========================================================================
# 2: authorized /status returns mode/profile/safety state
# ===========================================================================
def test_02_authorized_status_returns_state():
    cfg = _config(AMA_TELEGRAM_ALLOWED_CHAT_IDS="123", AMA_TELEGRAM_BOT_TOKEN="1:tok")
    console = TelegramOperatorConsole(config=cfg, state_store=_store())
    handled = console.handle_text("123", "/status")
    assert handled.authorized is True
    card = handled.result.card
    assert card["card_type"] == CardType.LIVE_ACCOUNT_STATUS
    assert card["runtime_mode"] == "LIVE_SHADOW"
    assert card["capital_profile_id"] == "L0_SHADOW"
    assert card["trade_authority"] is False
    assert card["ai_trade_authority"] is False
    assert card["exchange_live_orders"] is False
    assert card["source_label"] == "LIVE_SHADOW"


# ===========================================================================
# 3: /mode returns LIVE_SHADOW by default
# ===========================================================================
def test_03_mode_default_shadow():
    h = _handler()
    r = h.handle("/mode")
    assert r.card["runtime_mode"] == "LIVE_SHADOW"
    assert r.card["mode_display"] == "空盘跑"
    assert r.card["real_order_allowed"] is False


# ===========================================================================
# 4: /mode shadow disarms LIVE_LIMITED
# ===========================================================================
def test_04_mode_shadow_disarms_live_limited():
    h = _handler()
    _arm_live_limited(h)
    assert h.runtime_mode is LIMITED
    r = h.handle("/mode shadow")
    assert r.ok is True
    assert h.runtime_mode is SHADOW
    assert h.live_limited_armed is False


# ===========================================================================
# 5: /mode live_limited returns code, does not enable real orders
# ===========================================================================
def test_05_mode_live_limited_returns_code_no_real_orders():
    h = _handler()
    h.handle("/profile set L1_10U_PROBE confirm")
    r = h.handle("/mode live_limited")
    assert r.card["card_type"] == CardType.LIVE_MODE_SWITCH_REQUESTED
    assert r.card["confirmation_code"].startswith("LIVE-")
    # Mode is NOT changed by requesting.
    assert h.runtime_mode is SHADOW
    # Real orders are not enabled merely by issuing a code.
    assert r.card["exchange_live_orders"] is False


# ===========================================================================
# 6: /confirm_live wrong code rejected
# ===========================================================================
def test_06_confirm_live_wrong_code_rejected():
    h = _handler()
    h.handle("/profile set L1_10U_PROBE confirm")
    h.handle("/mode live_limited")
    r = h.handle("/confirm_live NOTTHECODE")
    assert r.ok is False
    assert r.reason == "confirmation_code_mismatch"
    assert h.runtime_mode is SHADOW


# ===========================================================================
# 7: /confirm_live correct code arms LIVE_LIMITED but does not bypass gates
# ===========================================================================
def test_07_confirm_live_arms_but_no_gate_bypass():
    # Provider reports exchange flags still OFF.
    provider = StubDataProvider(
        exchange_live_orders=False, trade_authority_flag=False, private_trade_enabled=False
    )
    h = _handler(provider=provider)
    h.handle("/profile set L1_10U_PROBE confirm")
    code = h.handle("/mode live_limited").card["confirmation_code"]
    r = h.handle("/confirm_live " + code)
    assert r.ok is True
    assert h.runtime_mode is LIMITED
    assert h.live_limited_armed is True
    # Armed, but real orders STILL not allowed (flags off).
    assert r.card["real_order_allowed"] is False
    assert h._real_order_allowed() is False  # noqa: SLF001


# ===========================================================================
# 8: state persists after reload
# ===========================================================================
def test_08_state_persists_after_reload():
    store = _store()
    h = _handler(store=store)
    _arm_live_limited(h)
    # A fresh handler over the same dir reloads the armed state.
    h2 = TelegramCommandHandler(state_store=LiveOperatorStateStore(store.state_dir))
    assert h2.runtime_mode is LIMITED
    assert h2.live_limited_armed is True
    assert h2.capital_profile_id.value == "L1_10U_PROBE"


# ===========================================================================
# 9: corrupt state fails safe to LIVE_SHADOW
# ===========================================================================
def test_09_corrupt_state_fails_safe():
    store = _store()
    h = _handler(store=store)
    _arm_live_limited(h)
    # Corrupt the runtime mode file.
    (store.state_dir / "runtime_mode.json").write_text("{not json")
    h2 = TelegramCommandHandler(state_store=LiveOperatorStateStore(store.state_dir))
    assert h2.runtime_mode is SHADOW
    assert any("FAILSAFE" in w for w in h2.load_warnings)


# ===========================================================================
# 10: /pnl includes gross pnl, commission, funding, net pnl
# ===========================================================================
def test_10_pnl_includes_all_components():
    provider = StubDataProvider(
        pnl={
            "gross_realized_pnl_usdt": 10.0,
            "commission_total_usdt": 0.5,
            "funding_total_usdt": -0.3,
            "net_strategy_pnl_usdt": 9.2,
            "funding_attribution_status": "ATTRIBUTED_TO_TRADE",
        }
    )
    h = _handler(provider=provider)
    r = h.handle("/pnl")
    card = r.card
    assert card["gross_realized_pnl"] == pytest.approx(10.0)
    assert card["commission_total"] == pytest.approx(0.5)
    assert card["funding_total"] == pytest.approx(-0.3)
    assert card["net_strategy_pnl"] == pytest.approx(9.2)
    assert card["funding_attribution_status"] == "ATTRIBUTED_TO_TRADE"


# ===========================================================================
# 11: /positions includes funding attribution status
# ===========================================================================
def test_11_positions_include_funding_attribution_status():
    provider = StubDataProvider(
        positions=[
            {
                "symbol": "RAVEUSDT",
                "side": "LONG",
                "position_amt": 20,
                "entry_price": 0.5,
                "mark_price": 0.55,
                "unrealized_pnl": 1.0,
                "notional_usdt": 11.0,
                "leverage": 3,
                "liquidation_price": 0.3,
                "funding_attribution_status": "ATTRIBUTED_TO_POSITION",
            }
        ],
        funding_attribution_status="ATTRIBUTED_TO_POSITION",
    )
    h = _handler(provider=provider)
    r = h.handle("/positions")
    assert r.card["position_count"] == 1
    assert r.card["positions"][0]["funding_attribution_status"] == "ATTRIBUTED_TO_POSITION"


# ===========================================================================
# 12: /risk includes profile limits
# ===========================================================================
def test_12_risk_includes_profile_limits():
    h = _handler()
    h.handle("/profile set L1_10U_PROBE confirm")
    r = h.handle("/risk")
    card = r.card
    assert card["capital_profile_id"] == "L1_10U_PROBE"
    assert card["max_account_capital_usdt"] == pytest.approx(10.0)
    assert card["max_position_notional_usdt"] == pytest.approx(20.0)
    assert card["max_leverage"] == pytest.approx(5.0)
    assert "kill_switch_state" in card


# ===========================================================================
# 13: /capital warns profile mismatch
# ===========================================================================
def test_13_capital_warns_profile_mismatch():
    provider = StubDataProvider(
        capital={
            "wallet_balance_usdt": 10000.0,
            "available_balance_usdt": 10000.0,
            "account_equity_usdt": 10000.0,
            "profile_mismatch_warning": "PROFILE_MISMATCH_EQUITY_ABOVE_RANGE",
        }
    )
    h = _handler(provider=provider)
    r = h.handle("/capital")
    assert r.card["profile_mismatch_warning"] == "PROFILE_MISMATCH_EQUITY_ABOVE_RANGE"


# ===========================================================================
# 14: /profile set invalid rejected
# ===========================================================================
def test_14_profile_set_invalid_rejected():
    h = _handler()
    r = h.handle("/profile set NOT_A_PROFILE")
    assert r.ok is False
    assert r.reason == "profile_not_found"
    assert r.card["card_type"] == CardType.PROFILE_CHANGE_REJECTED


# ===========================================================================
# 15: /pause blocks new entries
# ===========================================================================
def test_15_pause_blocks_new_entries():
    h = _handler()
    r = h.handle("/pause")
    assert r.ok is True
    assert h.paused is True
    assert r.card["card_type"] == CardType.LIVE_PAUSED
    assert "not force-closed" in r.card["note"]


# ===========================================================================
# 16: /resume does not bypass mode gates
# ===========================================================================
def test_16_resume_does_not_bypass_gates():
    h = _handler()
    h.handle("/pause")
    r = h.handle("/resume")
    assert r.ok is True
    assert h.paused is False
    # Resuming did not flip the runtime mode or arm anything.
    assert h.runtime_mode is SHADOW
    assert h.live_limited_armed is False
    assert "NOT bypassed" in r.card["note"]


# ===========================================================================
# 17: /kill_all requires confirmation
# ===========================================================================
def test_17_kill_all_requires_confirmation():
    h = _handler()
    r = h.handle("/kill_all")
    assert r.card["card_type"] == CardType.LIVE_KILL_SWITCH_ARM_REQUESTED
    assert r.card["confirmation_code"].startswith("KILL-")
    # Not armed until confirmed.
    assert h.kill_switch_armed is False
    code = r.card["confirmation_code"]
    r2 = h.handle("/confirm_kill " + code)
    assert r2.ok is True
    assert h.kill_switch_armed is True
    assert h.paused is True


# ===========================================================================
# 18: SHADOW_ENTRY_PLAN card contains planned entry/stop/tp and
#     real_order=false / order_id=--
# ===========================================================================
def test_18_shadow_entry_plan_card():
    card = build_shadow_entry_plan_card(
        {
            "symbol": "RAVEUSDT",
            "side": "LONG",
            "candidate_stage": "ATTACK",
            "opportunity_score": 0.8,
            "planned_entry_zone": "0.49-0.51",
            "planned_entry_price": 0.5,
            "planned_stop_price": 0.45,
            "planned_take_profit_1": 0.6,
            "planned_take_profit_2": 0.7,
            "planned_notional_usdt": 10,
            "planned_leverage": 3,
            "risk_decision": "approved_dry",
            "event_id": "E1",
        }
    )
    assert card["real_order"] is False
    assert card["real_capital_changed"] is False
    assert card["order_id"] == "--"
    assert card["fill_price"] == "--"
    assert card["planned_entry_price"] == pytest.approx(0.5)
    assert card["planned_stop_price"] == pytest.approx(0.45)
    assert card["planned_take_profit_1"] == pytest.approx(0.6)
    assert card["planned_take_profit_2"] == pytest.approx(0.7)
    assert card["planned_leverage"] == 3


# ===========================================================================
# 19: LIVE_ENTRY_FILLED card contains actual entry/order fields
# ===========================================================================
def test_19_live_entry_filled_card():
    import dataclasses

    from app.live.execution_models import (
        LiveExecutionStatus,
        LiveOrderResult,
        OrderSide,
        OrderType,
    )
    from app.live.telegram_formatters import (
        PAYLOAD_LIVE_ORDER_FILLED,
        build_execution_telegram_payload,
    )

    result = LiveOrderResult(
        status=LiveExecutionStatus.FILLED,
        client_order_id="amart-1",
        symbol="RAVEUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        exchange_order_id="987",
        avg_fill_price=0.5,
        executed_qty=20.0,
        cum_quote=10.0,
        fee_usdt=0.004,
        realized_pnl_usdt=0.0,
        is_real_order=True,
    )
    payload = build_execution_telegram_payload(
        PAYLOAD_LIVE_ORDER_FILLED, result=result, runtime_mode=LIMITED
    )
    assert payload["real_order"] is True
    assert payload["actual_entry_price"] == pytest.approx(0.5)
    assert payload["order_id"] == "987"
    assert payload["fee_usdt"] == pytest.approx(0.004)
    assert payload["mode_display"] == "有资金跑"


# ===========================================================================
# 20: LIVE_EXIT_FILLED card contains gross pnl/commission/funding/net pnl
# ===========================================================================
def test_20_live_exit_filled_card_has_pnl_breakdown():
    import dataclasses

    from app.live.execution_models import (
        LiveExecutionStatus,
        LiveOrderResult,
        OrderSide,
        OrderType,
    )
    from app.live.telegram_formatters import (
        PAYLOAD_LIVE_EXIT_FILLED,
        build_execution_telegram_payload,
    )

    result = LiveOrderResult(
        status=LiveExecutionStatus.FILLED,
        client_order_id="amart-exit",
        symbol="RAVEUSDT",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        exchange_order_id="988",
        avg_fill_price=0.6,
        executed_qty=20.0,
        cum_quote=12.0,
        fee_usdt=0.005,
        realized_pnl_usdt=2.0,
        reduce_only=True,
        is_real_order=True,
    )
    payload = build_execution_telegram_payload(
        PAYLOAD_LIVE_EXIT_FILLED, result=result, runtime_mode=LIMITED, funding_usdt=-0.1
    )
    assert payload["gross_pnl"] == pytest.approx(2.0)
    assert payload["fee_usdt"] == pytest.approx(0.005)
    assert payload["funding_usdt"] == pytest.approx(-0.1)
    # net = gross - fee + funding
    assert payload["net_pnl"] == pytest.approx(2.0 - 0.005 + (-0.1))


# ===========================================================================
# 21: LIVE_RISK_REJECT card contains reject reason
# ===========================================================================
def test_21_live_risk_reject_card_has_reason():
    card = build_live_risk_reject_card(
        {
            "symbol": "RAVEUSDT",
            "planned_notional_usdt": 50.0,
            "planned_leverage": 20.0,
            "reject_reason": "order_notional_exceeds_profile_max",
            "reject_reasons": ["order_notional_exceeds_profile_max"],
            "max_allowed_notional_usdt": 20.0,
            "max_allowed_leverage": 5.0,
            "capital_profile_id": "L1_10U_PROBE",
        },
        runtime_mode=LIMITED,
    )
    assert card["reject_reason"] == "order_notional_exceeds_profile_max"
    assert card["max_allowed_notional"] == pytest.approx(20.0)
    assert card["max_allowed_leverage"] == pytest.approx(5.0)
    assert card["real_order"] is False


# ===========================================================================
# 22: CAPITAL_EVENT_DETECTED card marks deposit not strategy pnl
# ===========================================================================
def test_22_capital_event_deposit_not_pnl():
    card = build_capital_event_detected_card(
        {
            "event_type": "EXTERNAL_DEPOSIT",
            "amount_usdt": 9990.0,
            "balance_before": 10.0,
            "balance_after": 10000.0,
            "is_trading_pnl": False,
            "is_external_capital_flow": True,
            "affects_performance_stats": False,
        }
    )
    assert card["is_trading_pnl"] is False
    assert card["is_external_capital_flow"] is True
    assert card["affects_performance_stats"] is False
    assert "NOT strategy profit" in card["explanation"]

    # And a withdrawal is not a loss.
    wcard = build_capital_event_detected_card(
        {"event_type": "EXTERNAL_WITHDRAWAL", "amount_usdt": 100.0}
    )
    assert "NOT strategy loss" in wcard["explanation"]


# ===========================================================================
# 23: funding event inside holding interval attributed
# ===========================================================================
def test_23_funding_inside_interval_attributed():
    rows = [{"incomeType": "FUNDING_FEE", "income": "-0.5", "symbol": "RAVEUSDT", "time": 1500, "asset": "USDT"}]
    evs = classify_income_rows(rows)
    positions = [
        PositionInterval(symbol="RAVEUSDT", entry_time_ms=1000, exit_time_ms=2000, notional_usdt=10.0, position_id="P1")
    ]
    res = attribute_funding_events(evs, positions=positions)
    assert res.rows[0].outcome is FundingAttributionOutcome.ATTRIBUTED_TO_POSITION
    assert res.attributed_funding_usdt == pytest.approx(-0.5)
    assert res.funding_for_position("P1") == pytest.approx(-0.5)


# ===========================================================================
# 24: funding event outside holding interval remains account-level
# ===========================================================================
def test_24_funding_outside_interval_account_level():
    rows = [{"incomeType": "FUNDING_FEE", "income": "-0.3", "symbol": "RAVEUSDT", "time": 9000, "asset": "USDT"}]
    evs = classify_income_rows(rows)
    positions = [
        PositionInterval(symbol="RAVEUSDT", entry_time_ms=1000, exit_time_ms=2000, notional_usdt=10.0, position_id="P1")
    ]
    res = attribute_funding_events(evs, positions=positions)
    assert res.rows[0].outcome is FundingAttributionOutcome.ACCOUNT_LEVEL_ONLY
    assert res.account_level_funding_usdt == pytest.approx(-0.3)
    assert res.attribution_status == "ACCOUNT_LEVEL_ONLY"


# ===========================================================================
# 25: commission event attributed to order/fill
# ===========================================================================
def test_25_commission_attributed_to_order():
    rows = [{"incomeType": "COMMISSION", "income": "-0.004", "symbol": "RAVEUSDT", "time": 1000, "asset": "USDT", "tradeId": "T1"}]
    evs = classify_income_rows(rows)
    fills = [FillRef(symbol="RAVEUSDT", trade_time_ms=1000, trade_id="T1", order_id="O1")]
    res = attribute_funding_events(evs, fills=fills)
    assert res.rows[0].outcome is FundingAttributionOutcome.ATTRIBUTED_TO_ORDER
    assert res.rows[0].attributed_order_id == "O1"
    assert res.attributed_commission_usdt == pytest.approx(0.004)


# ===========================================================================
# 26: ambiguous funding attribution handled safely
# ===========================================================================
def test_26_ambiguous_funding_handled():
    rows = [{"incomeType": "FUNDING_FEE", "income": "-1.0", "symbol": "RAVEUSDT", "time": 1500, "asset": "USDT"}]
    evs = classify_income_rows(rows)
    positions = [
        PositionInterval(symbol="RAVEUSDT", entry_time_ms=1000, exit_time_ms=2000, notional_usdt=10.0, position_id="P1"),
        PositionInterval(symbol="RAVEUSDT", entry_time_ms=1200, exit_time_ms=2200, notional_usdt=30.0, position_id="P2"),
    ]
    res = attribute_funding_events(evs, positions=positions)
    assert res.rows[0].outcome is FundingAttributionOutcome.AMBIGUOUS_MULTIPLE_POSITIONS
    assert res.ambiguous_funding_count == 1
    # Deterministic: the larger-notional position wins the primary link.
    assert res.rows[0].attributed_position_id == "P2"
    # Funding is never dropped: the total is preserved.
    assert res.total_funding_usdt == pytest.approx(-1.0)
    assert res.attribution_status == "AMBIGUOUS_MULTIPLE_POSITIONS"


# ===========================================================================
# 27: Telegram command cannot call Binance adapter directly
# ===========================================================================
def test_27_command_handler_has_no_binance_adapter():
    h = _handler()
    # The handler exposes no execution adapter / no submit path.
    assert not hasattr(h, "_adapter")
    assert not hasattr(h, "submit_order")
    # Even a full arm + status never produces a real order.
    _arm_live_limited(h)
    r = h.handle("/status")
    assert r.card["real_order"] is False
    assert r.card["exchange_live_orders"] is False


# ===========================================================================
# 28: Telegram command cannot call execution gateway without risk/gate path
# ===========================================================================
def test_28_command_cannot_bypass_execution_gate():
    # The console never enables the execution-gate flags. Arming
    # LIVE_LIMITED leaves real_order_allowed False because the data
    # provider reports exchange_live_orders / trade_authority off.
    h = _handler(provider=StubDataProvider())
    _arm_live_limited(h)
    assert h._real_order_allowed() is False  # noqa: SLF001
    # No command exists that flips exchange_live_orders / trade_authority.
    for cmd in ("/status", "/mode", "/pnl", "/risk", "/capital", "/positions"):
        assert h.handle(cmd).card.get("exchange_live_orders", False) in (False, None)


# ===========================================================================
# 29: AI output cannot trigger Telegram order command
# ===========================================================================
def test_29_ai_source_cannot_change_live_state():
    repo = FakeEventRepo()
    h = _handler(repo=repo)
    # OFFLINE_AI is a non-live source; a state-changing command is refused.
    r = h.handle("/mode live_limited", source=OrderSource.OFFLINE_AI)
    assert r.ok is False
    assert r.reason == "live_source_rejected"
    assert EventType.LIVE_SOURCE_REJECTED.value in repo.types()
    # The LiveSourceGuard raises for the hard-stop variant.
    with pytest.raises(LiveSourceRejected):
        LiveSourceGuard().assert_live_source(OrderSource.OFFLINE_AI, action="confirm_live")


# ===========================================================================
# 30: blind/sim source cannot trigger Telegram live execution
# ===========================================================================
@pytest.mark.parametrize(
    "src",
    [
        OrderSource.SIM,
        OrderSource.BLIND,
        OrderSource.REPLAY,
        OrderSource.PAPER_SHADOW,
        OrderSource.BACKTEST,
        OrderSource.TELEGRAM_SANDBOX,
    ],
)
def test_30_non_live_source_cannot_change_state(src):
    h = _handler()
    r = h.handle("/confirm_live ABC", source=src)
    assert r.ok is False
    assert r.reason == "live_source_rejected"
    assert h.runtime_mode is SHADOW


# ===========================================================================
# 31: safety flags default remain false
# ===========================================================================
def test_31_safety_flags_default_false():
    cfg = _config()
    # No live trading flags are set by default anywhere.
    assert cfg.binance.enable_private_trade is False
    assert cfg.live_runtime_mode is SHADOW
    console = TelegramOperatorConsole(config=cfg, state_store=_store())
    snap = console.status_snapshot()
    assert snap["live_trading_flag"] is False
    assert snap["exchange_live_orders_flag"] is False
    assert snap["trade_authority_flag"] is False
    assert snap["ai_trade_authority_flag"] is False
    assert snap["no_real_order_sent"] is True
    assert snap["phase_12_forbidden"] is True


# ===========================================================================
# 32: existing PR110/111/112/113 tests pass -> satisfied by the full suite.
# ===========================================================================
def test_32_marker_existing_suite_unaffected():
    # A light cross-check that the PR110-113 surfaces still import and the
    # PR110 path-isolation LiveOrderIntent is not shadowed by PR114.
    from app.live import LiveOrderIntent

    assert LiveOrderIntent.__module__ == "app.live.path_isolation"


# ===========================================================================
# Outbound gating + dry run
# ===========================================================================
def test_outbound_disabled_suppresses_and_audits():
    repo = FakeEventRepo()
    cfg = _config(AMA_TELEGRAM_ALLOWED_CHAT_IDS="123", AMA_TELEGRAM_BOT_TOKEN="1:tok")
    console = TelegramOperatorConsole(config=cfg, state_store=_store(), event_repo=repo)
    handled = console.handle_text("123", "/status")
    assert handled.outbound.suppressed is True
    assert handled.outbound.detail == "TELEGRAM_OUTBOUND_DISABLED"
    assert EventType.TELEGRAM_OUTBOUND_SUPPRESSED.value in repo.types()


def test_outbound_enabled_sends_via_fake_transport():
    repo = FakeEventRepo()
    transport = FakeTransport()
    cfg = _config(
        AMA_TELEGRAM_ALLOWED_CHAT_IDS="123",
        AMA_TELEGRAM_BOT_TOKEN="1:tok",
        AMA_TELEGRAM_OUTBOUND_ENABLED="true",
    )
    console = TelegramOperatorConsole(
        config=cfg, state_store=_store(), transport=transport, event_repo=repo
    )
    handled = console.handle_text("123", "/status")
    assert handled.outbound.sent is True
    assert any(m == "sendMessage" for m, _ in transport.calls)
    assert EventType.TELEGRAM_OUTBOUND_MESSAGE_SENT.value in repo.types()


def test_dry_run_suppresses_even_when_enabled():
    transport = FakeTransport()
    cfg = _config(
        AMA_TELEGRAM_ALLOWED_CHAT_IDS="123",
        AMA_TELEGRAM_BOT_TOKEN="1:tok",
        AMA_TELEGRAM_OUTBOUND_ENABLED="true",
    )
    console = TelegramOperatorConsole(
        config=cfg, state_store=_store(), transport=transport, dry_run=True
    )
    assert console.outbound_enabled is False
    handled = console.handle_text("123", "/status")
    assert handled.outbound.suppressed is True
    assert transport.calls == []


def test_outbound_message_never_carries_token():
    transport = FakeTransport()
    cfg = _config(
        AMA_TELEGRAM_ALLOWED_CHAT_IDS="123",
        AMA_TELEGRAM_BOT_TOKEN="111111:SECRETBOTTOKENVALUE",
        AMA_TELEGRAM_OUTBOUND_ENABLED="true",
    )
    console = TelegramOperatorConsole(config=cfg, state_store=_store(), transport=transport)
    console.handle_text("123", "/status")
    for _, body in transport.calls:
        assert "SECRETBOTTOKENVALUE" not in body.get("text", "")


# ===========================================================================
# Parsing
# ===========================================================================
def test_parse_command_multiword():
    assert parse_command("/mode shadow").key == "/mode shadow"
    assert parse_command("/mode live_limited").key == "/mode live_limited"
    assert parse_command("/profile set L1_10U_PROBE").key == "/profile set"
    assert parse_command("/profile set L1_10U_PROBE").args == ("L1_10U_PROBE",)
    assert parse_command("/status").key == "/status"
    assert parse_command("/bogus").is_known is False
    assert parse_command("not a command").is_known is False


# ===========================================================================
# Funding attribution: net pnl includes attributed funding;
# unattributed funding still shown in account-level total.
# ===========================================================================
def test_funding_net_includes_attributed_and_unattributed_shown():
    rows = [
        {"incomeType": "FUNDING_FEE", "income": "-0.5", "symbol": "RAVEUSDT", "time": 1500, "asset": "USDT"},
        {"incomeType": "FUNDING_INCOME" if False else "FUNDING_FEE", "income": "0.2", "time": 50, "asset": "USDT"},  # no symbol -> pending
    ]
    evs = classify_income_rows(rows)
    positions = [PositionInterval(symbol="RAVEUSDT", entry_time_ms=1000, exit_time_ms=2000, notional_usdt=10.0, position_id="P1")]
    res = attribute_funding_events(evs, positions=positions)
    # First funding attributed to position; second has no symbol -> pending,
    # but still counted in the total + account-level.
    assert res.attributed_funding_usdt == pytest.approx(-0.5)
    assert res.unattributed_funding_count == 1
    assert res.total_funding_usdt == pytest.approx(-0.3)  # -0.5 + 0.2
    assert res.attribution_status == "UNATTRIBUTED_PENDING_POSITION_LINK"


# ===========================================================================
# I1: BlindWalkForwardRunner cannot call Telegram live operator command path
# ===========================================================================
def test_I1_blind_runner_cannot_run_command():
    repo = FakeEventRepo()
    h = _handler(repo=repo)
    r = h.handle("/kill_all", source=OrderSource.BLIND)
    assert r.ok is False
    assert r.reason == "live_source_rejected"
    assert EventType.LIVE_SOURCE_REJECTED.value in repo.types()


# ===========================================================================
# I2: MockExchange cannot be used by LiveExecutionGateway (PR113 still holds)
# ===========================================================================
def test_I2_mock_exchange_source_blocked_at_gateway():
    from app.live.execution_gateway import (
        ExecutionPermissionContext,
        ExecutionRejectReason,
        evaluate_execution_permission,
    )
    from app.live.execution_models import LiveOrderIntent as ExecIntent, OrderSide, OrderType

    intent = ExecIntent(
        symbol="RAVEUSDT", side=OrderSide.BUY, order_type=OrderType.MARKET, source=OrderSource.SIM
    )
    d = evaluate_execution_permission(intent, None, ExecutionPermissionContext())
    assert d.allowed is False
    assert ExecutionRejectReason.SOURCE_NOT_LIVE in d.reject_reasons


# ===========================================================================
# I3: SimulatedCapitalFlow cannot be used as LiveCapitalState
# ===========================================================================
def test_I3_sim_capital_source_rejected_for_live_mutation():
    guard = LiveSourceGuard()
    assert guard.authorize(OrderSource.SIM, action="set_live_capital_state") is False
    with pytest.raises(LiveSourceRejected):
        guard.assert_live_source(OrderSource.SIM, action="set_live_capital_state")


# ===========================================================================
# I4: PaperShadowStrategyBridge cannot produce real_order=true
# ===========================================================================
def test_I4_paper_shadow_cannot_produce_real_order():
    from app.live.telegram_formatters import (
        PAYLOAD_LIVE_ORDER_FILLED,
        build_execution_telegram_payload,
    )
    from app.live.execution_models import (
        LiveExecutionStatus,
        LiveOrderResult,
        OrderSide,
        OrderType,
    )

    # A result that did NOT leave the system (is_real_order False) can never
    # be real_order=True even on a filled payload.
    result = LiveOrderResult(
        status=LiveExecutionStatus.FILLED,
        client_order_id="x",
        symbol="RAVEUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        avg_fill_price=0.5,
        executed_qty=20,
        is_real_order=False,
    )
    payload = build_execution_telegram_payload(
        PAYLOAD_LIVE_ORDER_FILLED, result=result, runtime_mode=SHADOW
    )
    assert payload["real_order"] is False
    assert payload["order_id"] == "--"


# ===========================================================================
# I5: HistoricalMarketStore source is rejected by live execution gate
# ===========================================================================
def test_I5_historical_store_source_rejected():
    from app.live.path_isolation import LivePathIsolationGuard, classify_source_module

    # HistoricalMarketStore maps to a non-live source (SIM).
    assert classify_source_module("HistoricalMarketStore") is OrderSource.SIM
    guard = LiveSourceGuard()
    assert guard.is_live_source(classify_source_module("HistoricalMarketStore")) is False


# ===========================================================================
# I6: Telegram Sandbox Outbox cannot send real Telegram outbound
# ===========================================================================
def test_I6_telegram_sandbox_source_cannot_change_state():
    h = _handler()
    r = h.handle("/mode live_limited", source=OrderSource.TELEGRAM_SANDBOX)
    assert r.ok is False
    assert r.reason == "live_source_rejected"


# ===========================================================================
# I7: Replay/reflection/evidence bundle cannot change live runtime_mode
# ===========================================================================
def test_I7_replay_cannot_change_runtime_mode():
    h = _handler()
    before = h.runtime_mode
    h.handle("/profile set L1_10U_PROBE confirm")  # this is LIVE by default
    r = h.handle("/mode live_limited", source=OrderSource.REPLAY)
    assert r.ok is False
    assert h.runtime_mode is before


# ===========================================================================
# I8: Replay/reflection/evidence bundle cannot change capital_profile_id
# ===========================================================================
def test_I8_replay_cannot_change_profile():
    h = _handler()
    before = h.capital_profile_id
    r = h.handle("/profile set L1_10U_PROBE confirm", source=OrderSource.REPLAY)
    assert r.ok is False
    assert h.capital_profile_id == before


# ===========================================================================
# I9: AI live briefing rejects blind/replay outcome as current live evidence
#     (modeled: an OFFLINE_AI source cannot drive a live mutation)
# ===========================================================================
def test_I9_offline_ai_cannot_drive_live_mutation():
    guard = LiveSourceGuard()
    assert guard.authorize(OrderSource.OFFLINE_AI, action="live_mutation") is False


# ===========================================================================
# I10: source=SIM/BLIND/REPLAY/PAPER_SHADOW reaching live order path emits
#      LIVE_PATH_BLOCKED (PR110 guard still holds)
# ===========================================================================
@pytest.mark.parametrize(
    "src", [OrderSource.SIM, OrderSource.BLIND, OrderSource.REPLAY, OrderSource.PAPER_SHADOW]
)
def test_I10_non_live_emits_live_path_blocked(src):
    from app.live.path_isolation import LiveOrderIntent as IsoIntent, LivePathIsolationGuard
    from app.core.enums import Direction

    repo = FakeEventRepo()
    guard = LivePathIsolationGuard(event_repo=repo)
    decision = guard.authorize(
        IsoIntent(source=src, source_module="test", symbol="RAVEUSDT", side=Direction.LONG)
    )
    assert decision.authorised is False
    assert EventType.LIVE_PATH_BLOCKED.value in repo.types()


# ===========================================================================
# I11: /status must display current source as LIVE_SHADOW or LIVE_LIMITED,
#      never silently mix with SIM/BLIND
# ===========================================================================
def test_I11_status_source_label_is_live_mode_only():
    h = _handler()
    r = h.handle("/status")
    assert r.card["source_label"] in ("LIVE_SHADOW", "LIVE_LIMITED")
    assert r.card["source_label"] == "LIVE_SHADOW"


# ===========================================================================
# I12: existing PR110 LivePathIsolationGuard tests remain passing
#      (light cross-check; full guarantee is the whole suite)
# ===========================================================================
def test_I12_pr110_isolation_guard_still_admits_live():
    from app.live.path_isolation import LiveOrderIntent as IsoIntent, LivePathIsolationGuard
    from app.core.enums import Direction

    guard = LivePathIsolationGuard()
    decision = guard.authorize(
        IsoIntent(source=OrderSource.LIVE, source_module="live.adapter", symbol="RAVEUSDT", side=Direction.LONG)
    )
    assert decision.authorised is True


# ===========================================================================
# I13: PR113 execution gateway source != LIVE rejection remains passing
# ===========================================================================
def test_I13_pr113_gateway_rejects_non_live_source():
    from app.live.execution_gateway import (
        ExecutionPermissionContext,
        ExecutionRejectReason,
        evaluate_execution_permission,
    )
    from app.live.execution_models import LiveOrderIntent as ExecIntent, OrderSide, OrderType

    intent = ExecIntent(
        symbol="RAVEUSDT", side=OrderSide.BUY, order_type=OrderType.MARKET, source=OrderSource.BLIND
    )
    d = evaluate_execution_permission(intent, None, ExecutionPermissionContext())
    assert ExecutionRejectReason.SOURCE_NOT_LIVE in d.reject_reasons


# ===========================================================================
# Persistent state files exist on disk after a mutation
# ===========================================================================
def test_state_files_written_atomically():
    store = _store()
    h = _handler(store=store)
    h.handle("/pause")
    assert (store.state_dir / "runtime_mode.json").exists()
    h.handle("/profile set L1_10U_PROBE confirm")
    assert (store.state_dir / "capital_profile_state.json").exists()


# ===========================================================================
# FUNDING_EVENT_ATTRIBUTED card roll-up
# ===========================================================================
def test_funding_event_attributed_card():
    rows = [
        {"incomeType": "FUNDING_FEE", "income": "-0.5", "symbol": "RAVEUSDT", "time": 1500, "asset": "USDT"},
    ]
    res = attribute_funding_events(
        classify_income_rows(rows),
        positions=[PositionInterval(symbol="RAVEUSDT", entry_time_ms=1000, exit_time_ms=2000, notional_usdt=10.0, position_id="P1")],
    )
    card = build_funding_event_attributed_card(res.to_dict())
    assert card["card_type"] == CardType.FUNDING_EVENT_ATTRIBUTED
    assert card["attributed_funding_usdt"] == pytest.approx(-0.5)
    assert card["attribution_status"] == "ATTRIBUTED_TO_POSITION"



# ===========================================================================
# /help lists commands + current mode
# ===========================================================================
def test_help_lists_commands_and_mode():
    h = _handler()
    r = h.handle("/help")
    assert r.card["card_type"] == CardType.LIVE_HELP
    assert "/status" in r.card["commands"]
    assert "/confirm_live CODE" in r.card["commands"]
    assert r.card["runtime_mode"] == "LIVE_SHADOW"


# ===========================================================================
# CLI: --status-json / --command / --send-test paths
# ===========================================================================
def test_cli_status_json(capsys):
    import json as _json

    from scripts.live_telegram_operator import main

    rc = main(["--status-json", "--state-dir", tempfile.mkdtemp()])
    out = capsys.readouterr().out
    data = _json.loads(out)
    assert data["no_real_order_sent"] is True
    assert data["runtime_mode"] == "LIVE_SHADOW"
    assert data["trade_authority_flag"] is False
    assert rc == 0


def test_cli_command_unauthorized_when_no_allowed_chat(capsys):
    from scripts.live_telegram_operator import main

    rc = main(["--command", "/status", "--state-dir", tempfile.mkdtemp()])
    out = capsys.readouterr().out
    assert "unauthorized" in out
    assert rc == 1


def test_cli_send_test_suppressed_when_outbound_disabled(capsys, monkeypatch):
    from scripts.live_telegram_operator import main

    monkeypatch.setenv("AMA_TELEGRAM_ALLOWED_CHAT_IDS", "123")
    monkeypatch.setenv("AMA_TELEGRAM_BOT_TOKEN", "1:tok")
    rc = main(["--send-test", "--chat-id", "123", "--state-dir", tempfile.mkdtemp()])
    out = capsys.readouterr().out
    assert "suppressed=True" in out
    assert rc == 1


def test_cli_dry_run_once_without_token_exits_2(capsys):
    from scripts.live_telegram_operator import main

    rc = main(["--dry-run", "--once", "--state-dir", tempfile.mkdtemp()])
    assert rc == 2


# ===========================================================================
# Kill switch blocks arming LIVE_LIMITED
# ===========================================================================
def test_kill_switch_active_blocks_confirm_live():
    h = _handler()
    h.handle("/profile set L1_10U_PROBE confirm")
    # Arm kill switch first.
    kc = h.handle("/kill_all").card["confirmation_code"]
    h.handle("/confirm_kill " + kc)
    assert h.kill_switch_armed is True
    # Now a live_limited confirm must be rejected.
    code = h.handle("/mode live_limited").card["confirmation_code"]
    r = h.handle("/confirm_live " + code)
    assert r.ok is False
    assert r.reason == "kill_switch_active"
