"""PR113 - Live Execution Gateway v0.

Binance order execution adapter + order lifecycle + fill ledger + strict
LIVE_LIMITED gate. EVERY test uses a fake Binance transport; no real API
call is ever made and no real order is ever sent.

The numbered tests map to the brief's "Tests Required" list (1..31); the
PR110/PR111/PR112-pass requirement (32) is satisfied by the full suite.
"""

from __future__ import annotations

import dataclasses
from urllib.parse import parse_qs, urlsplit

import pytest

from app.core.enums import LiveRuntimeMode, OrderSource
from app.core.errors import LivePathIsolationViolation
from app.core.events import Event, EventType
from app.live.api_config import LiveApiConfig
from app.live.binance_execution_adapter import (
    ADAPTER_BLOCKED_NOT_AUTHORISED,
    BinanceExecutionAdapter,
)
from app.live.binance_models import parse_exchange_info
from app.live.capital_profile import CapitalProfileId, get_profile
from app.live.execution_errors import AiTradeAuthorityForbidden
from app.live.execution_gateway import (
    ExecutionPermissionContext,
    ExecutionRejectReason,
    LiveExecutionGateway,
    authorize_real_order,
    evaluate_execution_permission,
)
from app.live.execution_models import (
    LiveExecutionStatus,
    LiveFillEvent,
    LiveOrderIntent,
    OrderIntentType,
    OrderSide,
    OrderType,
)
from app.live.execution_telegram import (
    PAYLOAD_LIVE_ORDER_FILLED,
    PAYLOAD_LIVE_ORDER_REJECTED,
    build_execution_telegram_payload,
)
from app.live.live_risk_engine import LiveRiskDecision
from app.live.order_ledger import LiveOrderLedger, compute_net_pnl

L1 = CapitalProfileId.L1_10U_PROBE
SHADOW = LiveRuntimeMode.LIVE_SHADOW
LIMITED = LiveRuntimeMode.LIVE_LIMITED

FAKE_KEY = "FAKEKEY0000000000000000000000000000000000000000000000000000000000"
FAKE_SECRET = "FAKESECRET00000000000000000000000000000000000000000000000000000"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
class FakeEventRepo:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, event: Event) -> None:
        self.events.append(event)

    def types(self) -> list[EventType]:
        return [e.event_type for e in self.events]


class FakeExecutionTransport:
    """Records calls; routes by path; never opens a socket."""

    def __init__(self, responses: dict | None = None, *, fail_if_called: bool = False) -> None:
        self.responses = responses or {}
        self.calls: list[dict] = []
        self.fail_if_called = fail_if_called

    def __call__(self, method: str, url: str, headers):
        if self.fail_if_called:
            raise AssertionError(f"transport must NOT be called: {method} {url}")
        path = urlsplit(url).path
        self.calls.append({"method": method, "url": url, "path": path, "headers": dict(headers)})
        if path not in self.responses:
            raise AssertionError(f"unexpected path: {path}")
        value = self.responses[path]
        return value(url) if callable(value) else value


SAMPLE_EXCHANGE_INFO = {
    "serverTime": 1700000000000,
    "symbols": [
        {
            "symbol": "RAVEUSDT",
            "status": "TRADING",
            "contractType": "PERPETUAL",
            "baseAsset": "RAVE",
            "quoteAsset": "USDT",
            "pricePrecision": 4,
            "quantityPrecision": 0,
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.0001"},
                {"filterType": "LOT_SIZE", "stepSize": "1", "minQty": "1", "maxQty": "1000000"},
                {"filterType": "MIN_NOTIONAL", "notional": "5"},
            ],
        },
        {
            "symbol": "HALTUSDT",
            "status": "BREAK",
            "contractType": "PERPETUAL",
            "baseAsset": "HALT",
            "quoteAsset": "USDT",
            "pricePrecision": 2,
            "quantityPrecision": 3,
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "100"},
                {"filterType": "MIN_NOTIONAL", "notional": "5"},
            ],
        },
    ],
}
EXINFO = parse_exchange_info(SAMPLE_EXCHANGE_INFO)

ORDER_NEW_RESPONSE = {
    "orderId": 987654321,
    "symbol": "RAVEUSDT",
    "status": "NEW",
    "clientOrderId": "amart-fixed",
    "price": "0",
    "avgPrice": "0.00000",
    "origQty": "20",
    "executedQty": "0",
    "cumQuote": "0",
    "type": "MARKET",
    "side": "BUY",
    "reduceOnly": False,
    "updateTime": 1700000000123,
}

ORDER_FILLED_RESPONSE = {
    "orderId": 987654322,
    "symbol": "RAVEUSDT",
    "status": "FILLED",
    "clientOrderId": "amart-fill",
    "price": "0",
    "avgPrice": "0.5000",
    "origQty": "20",
    "executedQty": "20",
    "cumQuote": "10.0",
    "type": "MARKET",
    "side": "BUY",
    "reduceOnly": False,
    "updateTime": 1700000000200,
}

ORDER_PARTIAL_RESPONSE = {
    "orderId": 987654323,
    "symbol": "RAVEUSDT",
    "status": "PARTIALLY_FILLED",
    "clientOrderId": "amart-part",
    "price": "0",
    "avgPrice": "0.5000",
    "origQty": "20",
    "executedQty": "10",
    "cumQuote": "5.0",
    "type": "MARKET",
    "side": "BUY",
    "reduceOnly": False,
    "updateTime": 1700000000300,
}

USER_TRADE_ROW = {
    "symbol": "RAVEUSDT",
    "id": 11111,
    "orderId": 987654322,
    "clientOrderId": "amart-fill",
    "price": "0.5",
    "qty": "20",
    "quoteQty": "10.0",
    "commission": "0.004",
    "commissionAsset": "USDT",
    "maker": False,
    "side": "BUY",
    "realizedPnl": "0",
    "time": 1700000000200,
}


def _binance_config(*, private_trade=True, private_read=True):
    env = {
        "AMA_BINANCE_API_KEY": FAKE_KEY,
        "AMA_BINANCE_API_SECRET": FAKE_SECRET,
        "AMA_BINANCE_ENABLE_PRIVATE_READ": "true" if private_read else "false",
        "AMA_BINANCE_ENABLE_PRIVATE_TRADE": "true" if private_trade else "false",
    }
    return LiveApiConfig.from_env(env).binance


def _adapter(transport=None, *, runtime=LIMITED, exchange_info=EXINFO, config=None, event_repo=None):
    return BinanceExecutionAdapter(
        config or _binance_config(),
        runtime_mode=runtime,
        transport=transport or FakeExecutionTransport(),
        exchange_info=exchange_info,
        event_repo=event_repo,
        clock=lambda: 1700000000000,
    )


def _ctx(**kw):
    base = dict(
        runtime_mode=LIMITED,
        live_limited_confirmed=True,
        exchange_live_orders=True,
        trade_authority=True,
        private_trade_enabled=True,
        kill_switch_active=False,
    )
    base.update(kw)
    return ExecutionPermissionContext(**base)


def _intent(**kw):
    base = dict(
        symbol="RAVEUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=20.0,
        notional_usdt=5.0,
        planned_entry_price=0.5,
        planned_stop_price=0.45,
        planned_take_profit_price=0.7,
        planned_leverage=1.0,
        exit_plan_present=True,
        stop_plan_present=True,
        client_order_id="amart-fixed",
        source=OrderSource.LIVE,
        runtime_mode=LIMITED,
        capital_profile_id=L1,
    )
    base.update(kw)
    return LiveOrderIntent(**base)


def _decision(*, approved=True, real_order_allowed=True):
    d = LiveRiskDecision(
        approved=approved,
        reject_reason=None,
        reject_reasons=(),
        runtime_mode=LIMITED,
        capital_profile_id=L1,
        planned_notional_usdt=5.0,
        max_allowed_notional_usdt=20.0,
        planned_leverage=1.0,
        max_allowed_leverage=5.0,
        account_equity_usdt=8.0,
        available_balance_usdt=8.0,
        risk_halt_active=False,
        evidence_refs=(),
        audit_event_type="LIVE_RISK_APPROVED_DRY",
    )
    return dataclasses.replace(d, real_order_allowed=real_order_allowed)


def _evaluate(intent=None, decision=None, ctx=None, **kw):
    return evaluate_execution_permission(
        intent or _intent(),
        decision if decision is not None else _decision(),
        ctx or _ctx(),
        profile=get_profile(L1),
        **kw,
    )


# ===========================================================================
# 1: rejects by default
# ===========================================================================
def test_01_gateway_rejects_by_default():
    # Default context + no risk decision + default (L0_SHADOW) intent profile.
    intent = LiveOrderIntent(
        symbol="RAVEUSDT", side=OrderSide.BUY, order_type=OrderType.MARKET, source=OrderSource.LIVE
    )
    decision = evaluate_execution_permission(intent, None, ExecutionPermissionContext())
    assert decision.allowed is False
    assert ExecutionRejectReason.RUNTIME_MODE_NOT_LIVE_LIMITED in decision.reject_reasons
    assert ExecutionRejectReason.EXCHANGE_LIVE_ORDERS_DISABLED in decision.reject_reasons
    assert ExecutionRejectReason.TRADE_AUTHORITY_DISABLED in decision.reject_reasons
    assert decision.audit_event == EventType.LIVE_EXECUTION_BLOCKED.value


# ===========================================================================
# 2: LIVE_SHADOW rejects real order
# ===========================================================================
def test_02_live_shadow_rejects():
    d = _evaluate(ctx=_ctx(runtime_mode=SHADOW))
    assert d.allowed is False
    assert ExecutionRejectReason.RUNTIME_MODE_NOT_LIVE_LIMITED in d.reject_reasons


# ===========================================================================
# 3: exchange_live_orders=false rejects
# ===========================================================================
def test_03_exchange_live_orders_false_rejects():
    d = _evaluate(ctx=_ctx(exchange_live_orders=False))
    assert d.allowed is False
    assert ExecutionRejectReason.EXCHANGE_LIVE_ORDERS_DISABLED in d.reject_reasons


# ===========================================================================
# 4: trade_authority=false rejects
# ===========================================================================
def test_04_trade_authority_false_rejects():
    d = _evaluate(ctx=_ctx(trade_authority=False))
    assert d.allowed is False
    assert ExecutionRejectReason.TRADE_AUTHORITY_DISABLED in d.reject_reasons


# ===========================================================================
# 5: source != LIVE rejects
# ===========================================================================
def test_05_source_not_live_rejects():
    d = _evaluate(intent=_intent(source=OrderSource.SIM))
    assert d.allowed is False
    assert ExecutionRejectReason.SOURCE_NOT_LIVE in d.reject_reasons


# ===========================================================================
# 6: risk_decision.approved=false rejects
# ===========================================================================
def test_06_risk_decision_not_approved_rejects():
    d = _evaluate(decision=_decision(approved=False, real_order_allowed=False))
    assert d.allowed is False
    assert ExecutionRejectReason.RISK_DECISION_NOT_APPROVED in d.reject_reasons


# ===========================================================================
# 7: real_order_allowed=false rejects
# ===========================================================================
def test_07_real_order_not_allowed_rejects():
    d = _evaluate(decision=_decision(approved=True, real_order_allowed=False))
    assert d.allowed is False
    assert ExecutionRejectReason.REAL_ORDER_NOT_ALLOWED in d.reject_reasons


# ===========================================================================
# 8: missing client_order_id rejects
# ===========================================================================
def test_08_missing_client_order_id_rejects():
    d = _evaluate(intent=_intent(client_order_id=None))
    assert d.allowed is False
    assert ExecutionRejectReason.MISSING_CLIENT_ORDER_ID in d.reject_reasons


# ===========================================================================
# 9: missing stop/exit plan rejects entry order
# ===========================================================================
def test_09_missing_stop_exit_plan_rejects_entry():
    d = _evaluate(intent=_intent(stop_plan_present=False, exit_plan_present=False))
    assert d.allowed is False
    assert ExecutionRejectReason.MISSING_STOP_OR_EXIT_PLAN in d.reject_reasons


def test_09b_emergency_exception_waives_stop_exit_plan():
    d = _evaluate(
        intent=_intent(stop_plan_present=False, exit_plan_present=False, emergency_exception=True)
    )
    assert ExecutionRejectReason.MISSING_STOP_OR_EXIT_PLAN not in d.reject_reasons


# ===========================================================================
# 10: kill switch active rejects
# ===========================================================================
def test_10_kill_switch_active_rejects():
    d = _evaluate(ctx=_ctx(kill_switch_active=True))
    assert d.allowed is False
    assert ExecutionRejectReason.KILL_SWITCH_ACTIVE in d.reject_reasons


# ===========================================================================
# 11: profile notional cap rejects oversized order
# ===========================================================================
def test_11_profile_notional_cap_rejects():
    d = _evaluate(intent=_intent(notional_usdt=50.0))  # L1 max = 20
    assert d.allowed is False
    assert ExecutionRejectReason.NOTIONAL_EXCEEDS_PROFILE_MAX in d.reject_reasons


# ===========================================================================
# 12: leverage cap rejects oversized leverage
# ===========================================================================
def test_12_leverage_cap_rejects():
    d = _evaluate(intent=_intent(planned_leverage=20.0))  # L1 boost max = 10
    assert d.allowed is False
    assert ExecutionRejectReason.LEVERAGE_EXCEEDS_PROFILE_MAX in d.reject_reasons


# ===========================================================================
# 13: minNotional validation works
# ===========================================================================
def test_13_min_notional_validation():
    adapter = _adapter()
    # qty 2 @ planned 0.5 -> notional 1.0 < minNotional 5 -> fail.
    bad = adapter.validate_order_against_exchange_info(_intent(quantity=2.0))
    assert bad.ok is False
    assert "min_notional_not_met" in bad.reasons
    # qty 20 @ 0.5 -> 10 >= 5 -> ok.
    good = adapter.validate_order_against_exchange_info(_intent(quantity=20.0))
    assert good.ok is True, good.reasons
    assert good.min_notional == pytest.approx(5.0)


# ===========================================================================
# 14: tickSize / stepSize normalization works
# ===========================================================================
def test_14_tick_step_normalization():
    adapter = _adapter()
    # stepSize=1, quantityPrecision=0 -> floor 20.7 to 20.
    intent = _intent(order_type=OrderType.LIMIT, quantity=20.7, price=0.50007)
    qty, price, stop = adapter.normalize_order(intent)
    assert qty == pytest.approx(20.0)
    # tickSize=0.0001 -> round 0.50007 to 0.5001.
    assert price == pytest.approx(0.5001)


# ===========================================================================
# 15: PRIVATE_TRADE adapter does not send HTTP when blocked
# ===========================================================================
def test_15_adapter_no_http_when_blocked():
    repo = FakeEventRepo()
    transport = FakeExecutionTransport(fail_if_called=True)
    # Private trade DISABLED + SHADOW runtime -> blocked regardless of flag.
    adapter = BinanceExecutionAdapter(
        _binance_config(private_trade=False),
        runtime_mode=SHADOW,
        transport=transport,
        exchange_info=EXINFO,
        event_repo=repo,
        clock=lambda: 1700000000000,
    )
    validation = adapter.validate_order_against_exchange_info(_intent())
    request = adapter.build_order_request(_intent(), validation, real_order_allowed=True, dry_run=False)
    result = adapter.submit_order(request, real_order_allowed=True)
    assert result.status is LiveExecutionStatus.BLOCKED
    assert result.is_real_order is False
    assert result.error_code == ADAPTER_BLOCKED_NOT_AUTHORISED
    assert transport.calls == []  # no socket was opened
    assert EventType.LIVE_ORDER_ADAPTER_BLOCKED in repo.types()


# ===========================================================================
# 16: all gates true -> order submit request formed correctly
# ===========================================================================
def test_16_all_gates_true_request_formed_correctly():
    repo = FakeEventRepo()
    transport = FakeExecutionTransport({"/fapi/v1/order": ORDER_NEW_RESPONSE})
    adapter = _adapter(transport, event_repo=repo)
    gateway = LiveExecutionGateway(adapter=adapter, event_repo=repo)

    result = gateway.submit_order(_intent(), _decision(), _ctx())
    assert result.is_real_order is True
    assert result.status is LiveExecutionStatus.NEW
    assert result.exchange_order_id == "987654321"
    # Exactly one HTTP call, a signed POST to the order endpoint.
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/fapi/v1/order"
    qs = parse_qs(urlsplit(call["url"]).query)
    assert qs["symbol"] == ["RAVEUSDT"]
    assert qs["side"] == ["BUY"]
    assert qs["type"] == ["MARKET"]
    assert qs["quantity"] == ["20"] or qs["quantity"] == ["20.0"]
    assert qs["newClientOrderId"] == ["amart-fixed"]
    assert "signature" in qs
    # Secret never appears in the URL; key only travels in the header.
    assert FAKE_SECRET not in call["url"]
    assert FAKE_KEY not in call["url"]
    assert call["headers"].get("X-MBX-APIKEY") == FAKE_KEY
    # Ledger wrote an ENTRY row.
    assert len(gateway.ledger.rows_of_intent(OrderIntentType.ENTRY)) == 1
    assert EventType.LIVE_ORDER_SUBMITTED in repo.types()


# ===========================================================================
# 17: cancel requires same gates or reduce/emergency exception
# ===========================================================================
def test_17_cancel_requires_gates_or_emergency():
    transport = FakeExecutionTransport(
        {"/fapi/v1/order": {"orderId": 5, "symbol": "RAVEUSDT", "status": "CANCELED", "clientOrderId": "amart-fixed", "side": "BUY", "type": "MARKET"}}
    )
    adapter = _adapter(transport)
    gateway = LiveExecutionGateway(adapter=adapter)

    # Armed context -> cancel proceeds.
    res_ok = gateway.cancel_order(_intent(), _decision(), _ctx())
    assert res_ok.status is LiveExecutionStatus.CANCELED
    assert res_ok.is_real_order is True

    # Unarmed (shadow) context, no emergency -> blocked, no extra HTTP.
    transport_blocked = FakeExecutionTransport(fail_if_called=True)
    adapter2 = _adapter(transport_blocked, runtime=SHADOW)
    gateway2 = LiveExecutionGateway(adapter=adapter2)
    res_blocked = gateway2.cancel_order(
        _intent(), _decision(), _ctx(runtime_mode=SHADOW, exchange_live_orders=False, trade_authority=False, private_trade_enabled=False),
        reduce_or_emergency=False,
    )
    assert res_blocked.status is LiveExecutionStatus.BLOCKED
    assert transport_blocked.calls == []


# ===========================================================================
# 18: order status parse works
# ===========================================================================
def test_18_order_status_parse():
    adapter = _adapter()
    result = adapter.parse_order_response(ORDER_FILLED_RESPONSE)
    assert result.status is LiveExecutionStatus.FILLED
    assert result.executed_qty == pytest.approx(20.0)
    assert result.avg_fill_price == pytest.approx(0.5)
    assert result.cum_quote == pytest.approx(10.0)
    assert result.raw_status == "FILLED"


# ===========================================================================
# 19: partial fill parse works
# ===========================================================================
def test_19_partial_fill_parse():
    adapter = _adapter()
    result = adapter.parse_order_response(ORDER_PARTIAL_RESPONSE)
    assert result.status is LiveExecutionStatus.PARTIALLY_FILLED
    assert result.executed_qty == pytest.approx(10.0)
    assert result.is_partial is True


# ===========================================================================
# 20: fill event includes fee
# ===========================================================================
def test_20_fill_event_includes_fee():
    fill = LiveFillEvent.from_user_trade(USER_TRADE_ROW)
    assert fill.fee_usdt == pytest.approx(0.004)
    assert fill.fee_asset == "USDT"
    assert fill.quantity == pytest.approx(20.0)
    assert fill.liquidity_side == "TAKER"
    # via adapter.get_user_trades (fake transport)
    transport = FakeExecutionTransport({"/fapi/v1/userTrades": [USER_TRADE_ROW]})
    adapter = _adapter(transport)
    fills = adapter.get_user_trades("RAVEUSDT")
    assert len(fills) == 1
    assert fills[0].fee_usdt == pytest.approx(0.004)


# ===========================================================================
# 21: order ledger writes entry row
# ===========================================================================
def test_21_ledger_writes_entry_row():
    adapter = _adapter()
    result = adapter.parse_order_response(ORDER_NEW_RESPONSE, is_real_order=True)
    ledger = LiveOrderLedger()
    row = ledger.record_order(_intent(), result)
    assert len(ledger) == 1
    assert row.intent_type == OrderIntentType.ENTRY.value
    assert row.client_order_id == "amart-fixed"
    assert row.is_real_order is True


# ===========================================================================
# 22: order ledger writes fill row
# ===========================================================================
def test_22_ledger_writes_fill_row():
    ledger = LiveOrderLedger()
    fill = LiveFillEvent.from_user_trade(USER_TRADE_ROW)
    row = ledger.record_fill(fill, intent=_intent())
    assert len(ledger) == 1
    assert row.status == LiveExecutionStatus.FILLED.value
    assert row.filled_qty == pytest.approx(20.0)
    assert row.avg_fill_price == pytest.approx(0.5)
    assert row.fee_usdt == pytest.approx(0.004)


# ===========================================================================
# 23: net pnl includes fee and funding placeholder field
# ===========================================================================
def test_23_net_pnl_includes_fee_and_funding_placeholder():
    ledger = LiveOrderLedger()
    fill = dataclasses.replace(
        LiveFillEvent.from_user_trade(USER_TRADE_ROW), realized_pnl_usdt=10.0, fee_usdt=0.5
    )
    row = ledger.record_fill(fill, intent=_intent(), funding_usdt_attributed=0.2)
    # net = realized(10) - fee(0.5) + funding(0.2) = 9.7
    assert row.net_pnl_usdt == pytest.approx(9.7)
    assert row.funding_usdt_attributed == pytest.approx(0.2)
    assert row.funding_attribution_status == "UNATTRIBUTED_PENDING_POSITION_LINK"
    # Direct helper check.
    assert compute_net_pnl(10.0, 0.5, 0.2) == pytest.approx(9.7)


# ===========================================================================
# 24: Telegram LIVE_ORDER_REJECTED payload contains planned/actual + reason
# ===========================================================================
def test_24_telegram_rejected_payload():
    intent = _intent()
    blocked_result = None
    payload = build_execution_telegram_payload(
        PAYLOAD_LIVE_ORDER_REJECTED,
        intent=intent,
        result=blocked_result,
        reject_reason="exchange_live_orders_disabled",
        runtime_mode=LIMITED,
    )
    assert payload["payload_type"] == PAYLOAD_LIVE_ORDER_REJECTED
    assert payload["planned_entry_price"] == pytest.approx(0.5)
    assert payload["planned_stop_price"] == pytest.approx(0.45)
    assert payload["planned_take_profit_price"] == pytest.approx(0.7)
    assert payload["actual_entry_price"] == "--"
    assert payload["reject_reason"] == "exchange_live_orders_disabled"
    assert payload["real_order"] is False
    assert payload["order_id"] == "--"


# ===========================================================================
# 25: Telegram LIVE_ORDER_FILLED payload contains entry/exit/fee/net pnl
# ===========================================================================
def test_25_telegram_filled_payload():
    adapter = _adapter()
    result = adapter.parse_order_response(ORDER_FILLED_RESPONSE, is_real_order=True)
    result = dataclasses.replace(result, fee_usdt=0.004, realized_pnl_usdt=2.0)
    payload = build_execution_telegram_payload(
        PAYLOAD_LIVE_ORDER_FILLED,
        intent=_intent(),
        result=result,
        runtime_mode=LIMITED,
        funding_usdt=0.0,
    )
    assert payload["real_order"] is True
    assert payload["real_capital_changed"] is True
    assert payload["actual_entry_price"] == pytest.approx(0.5)
    assert payload["fee_usdt"] == pytest.approx(0.004)
    assert payload["gross_pnl"] == pytest.approx(2.0)
    # net = gross - fee + funding
    assert payload["net_pnl"] == pytest.approx(2.0 - 0.004)
    assert payload["order_id"] == "987654322"


# ===========================================================================
# 26: 空盘 payload has real_order=false and order_id=--
# ===========================================================================
def test_26_shadow_payload_no_real_order():
    adapter = _adapter(runtime=SHADOW)
    result = adapter.parse_order_response(ORDER_FILLED_RESPONSE, is_real_order=False)
    payload = build_execution_telegram_payload(
        PAYLOAD_LIVE_ORDER_FILLED,
        intent=_intent(runtime_mode=SHADOW),
        result=result,
        runtime_mode=SHADOW,
    )
    assert payload["mode_display"] == "空盘跑"
    assert payload["real_order"] is False
    assert payload["real_capital_changed"] is False
    assert payload["order_id"] == "--"
    assert payload["actual_entry_price"] == "--"


# ===========================================================================
# 27: safety flags remain false by default
# ===========================================================================
def test_27_safety_flags_false_by_default():
    ctx = ExecutionPermissionContext()
    assert ctx.exchange_live_orders is False
    assert ctx.trade_authority is False
    assert ctx.ai_trade_authority is False
    assert ctx.fully_armed is False
    # default Binance config: private trade disabled.
    cfg = LiveApiConfig.from_env({}).binance
    assert cfg.enable_private_trade is False
    # A default permission decision is blocked.
    intent = LiveOrderIntent(
        symbol="RAVEUSDT", side=OrderSide.BUY, order_type=OrderType.MARKET, source=OrderSource.LIVE
    )
    d = evaluate_execution_permission(intent, None, ctx)
    assert d.allowed is False


# ===========================================================================
# 28: AI cannot call execution gateway
# ===========================================================================
def test_28_ai_cannot_call_gateway():
    transport = FakeExecutionTransport(fail_if_called=True)
    adapter = _adapter(transport)
    gateway = LiveExecutionGateway(adapter=adapter)
    with pytest.raises(AiTradeAuthorityForbidden):
        gateway.submit_order(_intent(), _decision(), _ctx(ai_trade_authority=True))
    assert transport.calls == []


def test_28b_ai_trade_authority_rejected_in_permission():
    d = _evaluate(ctx=_ctx(ai_trade_authority=True))
    assert d.allowed is False
    assert ExecutionRejectReason.AI_TRADE_AUTHORITY_FORBIDDEN in d.reject_reasons


# ===========================================================================
# 29: blind/sim source cannot call execution gateway
# ===========================================================================
@pytest.mark.parametrize("src", [OrderSource.SIM, OrderSource.BLIND, OrderSource.REPLAY, OrderSource.PAPER_SHADOW])
def test_29_blind_sim_source_cannot_call_gateway(src):
    transport = FakeExecutionTransport(fail_if_called=True)
    adapter = _adapter(transport)
    gateway = LiveExecutionGateway(adapter=adapter)
    with pytest.raises(LivePathIsolationViolation):
        gateway.submit_order(_intent(source=src), _decision(), _ctx())
    assert transport.calls == []


# ===========================================================================
# Extra: authorize_real_order only flips when fully armed
# ===========================================================================
def test_authorize_real_order_requires_fully_armed():
    dry = _decision(approved=True, real_order_allowed=False)
    # Not armed -> stays False.
    not_armed = ExecutionPermissionContext()
    assert authorize_real_order(dry, not_armed).real_order_allowed is False
    # Armed -> flips True.
    assert authorize_real_order(dry, _ctx()).real_order_allowed is True
    # Approved=False never flips even when armed.
    rejected = _decision(approved=False, real_order_allowed=False)
    assert authorize_real_order(rejected, _ctx()).real_order_allowed is False


def test_full_happy_path_emits_filled_and_writes_ledger():
    repo = FakeEventRepo()
    transport = FakeExecutionTransport({"/fapi/v1/order": ORDER_FILLED_RESPONSE})
    adapter = _adapter(transport, event_repo=repo)
    gateway = LiveExecutionGateway(adapter=adapter, event_repo=repo)
    intent = _intent(client_order_id="amart-fill")
    result = gateway.submit_order(intent, _decision(), _ctx())
    assert result.status is LiveExecutionStatus.FILLED
    assert result.is_real_order is True
    assert EventType.LIVE_ORDER_FILLED in repo.types()
    assert len(gateway.ledger) >= 1


def test_set_leverage_and_margin_mode_forbidden():
    from app.core.errors import SafeModeViolation

    adapter = _adapter()
    with pytest.raises(SafeModeViolation):
        adapter.set_leverage("RAVEUSDT", 5)
    with pytest.raises(SafeModeViolation):
        adapter.set_margin_mode("RAVEUSDT", "ISOLATED")
