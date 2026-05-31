"""PR118 - Live Execution Telegram Notifier (independent app.live sender).

Covers the behaviour the brief requires:

  - 空盘 / dry-run plan + reject cards carry real_order=false / order_id=-- /
    actual_*=-- / real_capital_changed=false (planned geometry present).
  - 有资金跑 real order / fill cards carry real_order=true + the real
    order_id / actual fill price / fee / funding / net_pnl.
  - The notifier NEVER sends when outbound is disabled / dry-run.
  - Only allow-listed chat ids ever receive a card.
  - A non-LIVE source (SIM / BLIND / REPLAY / PAPER_SHADOW) is refused.
  - A real order never carries actual_fill_price before it is filled.
  - A retry never double-pushes (dedup by event_id / client_order_id).
  - The gateway forwards blocked / filled payloads to the notifier;
    an AI-authority order never produces a telegram event.

Every test uses a fake transport; no real socket is ever opened and no
real order is ever sent.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.core.enums import LiveRuntimeMode, OrderSource
from app.core.events import Event, EventType
from app.live.api_config import LiveApiConfig, TelegramApiConfig
from app.live.binance_execution_adapter import BinanceExecutionAdapter
from app.live.binance_models import parse_exchange_info
from app.live.capital_profile import CapitalProfileId
from app.live.execution_errors import AiTradeAuthorityForbidden
from app.live.execution_gateway import (
    ExecutionPermissionContext,
    LiveExecutionGateway,
)
from app.live.execution_models import (
    LiveExecutionStatus,
    LiveOrderIntent,
    LiveOrderResult,
    OrderSide,
    OrderType,
)
from app.live.execution_notifier import (
    REASON_DUPLICATE,
    REASON_MISSING_TOKEN,
    REASON_NO_ALLOWED_CHAT,
    REASON_OUTBOUND_DISABLED,
    REASON_SOURCE_NOT_LIVE,
    LiveExecutionNotifier,
)
from app.live.execution_telegram import (
    PAYLOAD_LIVE_EXECUTION_BLOCKED,
    PAYLOAD_LIVE_ORDER_FILLED,
    PAYLOAD_LIVE_ORDER_SUBMITTED,
    PAYLOAD_SHADOW_ENTRY_PLAN,
    build_execution_telegram_payload,
    execution_payload_dedup_key,
)
from app.live.live_risk_engine import LiveRiskDecision
from app.live.order_ledger import LiveOrderLedger
from app.live.secrets import SecretValue

L1 = CapitalProfileId.L1_10U_PROBE
SHADOW = LiveRuntimeMode.LIVE_SHADOW
LIMITED = LiveRuntimeMode.LIVE_LIMITED
PLACEHOLDER = "--"


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------
class FakeEventRepo:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, event: Event) -> None:
        self.events.append(event)

    def types(self) -> list[EventType]:
        return [e.event_type for e in self.events]


class RecordingTransport:
    """Records every (method, body) it is asked to send."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, method, url, body):
        self.calls.append({"method": method, "url": url, "body": dict(body)})
        return {"ok": True, "result": {}}


class RecordingNotifier:
    """Captures the payloads + source the gateway forwards."""

    def __init__(self) -> None:
        self.calls: list[tuple[dict, object]] = []

    def notify(self, payload, *, source=OrderSource.LIVE):
        self.calls.append((dict(payload), source))


def _tg(*, outbound=True, chats=("123",), token="tok") -> TelegramApiConfig:
    return TelegramApiConfig(
        bot_token=SecretValue("AMA_TELEGRAM_BOT_TOKEN", token),
        allowed_chat_ids=tuple(chats),
        outbound_enabled=outbound,
    )


def _shadow_intent(**kw) -> LiveOrderIntent:
    base = dict(
        symbol="RAVEUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=20.0,
        notional_usdt=10.0,
        planned_entry_price=0.5,
        planned_stop_price=0.45,
        planned_take_profit_price=0.7,
        planned_leverage=3.0,
        client_order_id="amart-shadow",
        source=OrderSource.LIVE,
        runtime_mode=SHADOW,
        capital_profile_id=L1,
    )
    base.update(kw)
    return LiveOrderIntent(**base)


def _filled_result(**kw) -> LiveOrderResult:
    base = dict(
        status=LiveExecutionStatus.FILLED,
        client_order_id="amart-fill",
        symbol="RAVEUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        exchange_order_id="987654322",
        avg_fill_price=0.5,
        executed_qty=20.0,
        cum_quote=10.0,
        fee_usdt=0.004,
        realized_pnl_usdt=0.0,
        is_real_order=True,
    )
    base.update(kw)
    return LiveOrderResult(**base)


# ===========================================================================
# Card field contract
# ===========================================================================
def test_shadow_plan_card_has_blank_real_order_fields():
    payload = build_execution_telegram_payload(
        PAYLOAD_SHADOW_ENTRY_PLAN, intent=_shadow_intent(), runtime_mode=SHADOW
    )
    assert payload["real_order"] is False
    assert payload["real_capital_changed"] is False
    assert payload["order_id"] == PLACEHOLDER
    assert payload["actual_entry_price"] == PLACEHOLDER
    assert payload["actual_exit_price"] == PLACEHOLDER
    # Planned geometry IS present.
    assert payload["planned_entry_price"] == 0.5
    assert payload["planned_stop_price"] == 0.45
    assert payload["planned_take_profit_price"] == 0.7
    assert payload["direction"] == "LONG"


def test_live_filled_card_has_real_order_fields():
    intent = _shadow_intent(client_order_id="amart-fill", runtime_mode=LIMITED)
    payload = build_execution_telegram_payload(
        PAYLOAD_LIVE_ORDER_FILLED,
        intent=intent,
        result=_filled_result(),
        runtime_mode=LIMITED,
        funding_usdt=-0.01,
    )
    assert payload["real_order"] is True
    assert payload["real_capital_changed"] is True
    assert payload["order_id"] == "987654322"
    assert payload["actual_entry_price"] == 0.5
    assert payload["fee_usdt"] == 0.004
    assert payload["funding_usdt"] == -0.01
    # net = gross(0) - fee(0.004) + funding(-0.01)
    assert payload["net_pnl"] == pytest.approx(-0.014)


def test_blocked_and_shadow_cards_never_real_order_true():
    for ptype in (
        PAYLOAD_SHADOW_ENTRY_PLAN,
        PAYLOAD_LIVE_EXECUTION_BLOCKED,
    ):
        payload = build_execution_telegram_payload(
            ptype,
            intent=_shadow_intent(runtime_mode=LIMITED),
            reject_reason="exchange_live_orders_disabled",
            runtime_mode=LIMITED,
        )
        assert payload["real_order"] is False
        assert payload["order_id"] == PLACEHOLDER


def test_real_order_unfilled_keeps_actual_price_blank():
    # A SUBMITTED (NEW) real order has no fill yet -> actual price stays "--".
    submitted = LiveOrderResult(
        status=LiveExecutionStatus.NEW,
        client_order_id="amart-new",
        symbol="RAVEUSDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        exchange_order_id="111",
        avg_fill_price=0.0,
        executed_qty=0.0,
        cum_quote=0.0,
        is_real_order=True,
    )
    payload = build_execution_telegram_payload(
        PAYLOAD_LIVE_ORDER_SUBMITTED,
        intent=_shadow_intent(runtime_mode=LIMITED),
        result=submitted,
        runtime_mode=LIMITED,
    )
    assert payload["real_order"] is True
    assert payload["actual_entry_price"] == PLACEHOLDER
    assert payload["actual_exit_price"] == PLACEHOLDER
    assert payload["real_capital_changed"] is False


# ===========================================================================
# Notifier gating
# ===========================================================================
def test_notifier_suppresses_when_outbound_disabled():
    tx = RecordingTransport()
    repo = FakeEventRepo()
    n = LiveExecutionNotifier(telegram_config=_tg(outbound=False), transport=tx, event_repo=repo)
    payload = build_execution_telegram_payload(PAYLOAD_SHADOW_ENTRY_PLAN, intent=_shadow_intent())
    res = n.notify(payload, source=OrderSource.LIVE)
    assert res.sent is False
    assert res.suppressed is True
    assert res.reason == REASON_OUTBOUND_DISABLED
    assert tx.calls == []
    assert EventType.TELEGRAM_OUTBOUND_SUPPRESSED in repo.types()


def test_notifier_suppresses_in_dry_run():
    tx = RecordingTransport()
    n = LiveExecutionNotifier(telegram_config=_tg(outbound=True), transport=tx, dry_run=True)
    payload = build_execution_telegram_payload(PAYLOAD_SHADOW_ENTRY_PLAN, intent=_shadow_intent())
    res = n.notify(payload, source=OrderSource.LIVE)
    assert res.suppressed is True
    assert tx.calls == []


def test_notifier_missing_token_suppresses():
    tx = RecordingTransport()
    n = LiveExecutionNotifier(telegram_config=_tg(token=""), transport=tx)
    res = n.notify(build_execution_telegram_payload(PAYLOAD_SHADOW_ENTRY_PLAN, intent=_shadow_intent()))
    assert res.reason == REASON_MISSING_TOKEN
    assert tx.calls == []


def test_notifier_no_allowed_chat_suppresses():
    tx = RecordingTransport()
    n = LiveExecutionNotifier(telegram_config=_tg(chats=()), transport=tx)
    res = n.notify(build_execution_telegram_payload(PAYLOAD_SHADOW_ENTRY_PLAN, intent=_shadow_intent()))
    assert res.reason == REASON_NO_ALLOWED_CHAT
    assert tx.calls == []


def test_notifier_sends_only_to_allowlisted_chats():
    tx = RecordingTransport()
    n = LiveExecutionNotifier(telegram_config=_tg(chats=("123", "456")), transport=tx)
    payload = build_execution_telegram_payload(
        PAYLOAD_LIVE_ORDER_FILLED,
        intent=_shadow_intent(client_order_id="amart-fill", runtime_mode=LIMITED),
        result=_filled_result(),
        runtime_mode=LIMITED,
    )
    res = n.notify(payload, source=OrderSource.LIVE)
    assert res.sent is True
    assert res.sent_count == 2
    sent_chats = {c["body"]["chat_id"] for c in tx.calls}
    assert sent_chats == {"123", "456"}


@pytest.mark.parametrize(
    "bad_source",
    [OrderSource.SIM, OrderSource.BLIND, OrderSource.REPLAY, OrderSource.PAPER_SHADOW],
)
def test_notifier_refuses_non_live_source(bad_source):
    tx = RecordingTransport()
    repo = FakeEventRepo()
    n = LiveExecutionNotifier(telegram_config=_tg(), transport=tx, event_repo=repo)
    payload = build_execution_telegram_payload(PAYLOAD_SHADOW_ENTRY_PLAN, intent=_shadow_intent())
    res = n.notify(payload, source=bad_source)
    assert res.suppressed is True
    assert res.reason == REASON_SOURCE_NOT_LIVE
    assert tx.calls == []
    assert EventType.LIVE_SOURCE_REJECTED in repo.types()


def test_notifier_dedup_blocks_duplicate_push():
    tx = RecordingTransport()
    n = LiveExecutionNotifier(telegram_config=_tg(), transport=tx)
    payload = build_execution_telegram_payload(
        PAYLOAD_LIVE_ORDER_FILLED,
        intent=_shadow_intent(client_order_id="amart-fill", runtime_mode=LIMITED),
        result=_filled_result(),
        runtime_mode=LIMITED,
        event_id="amart-fill:LIVE_ORDER_FILLED",
    )
    r1 = n.notify(payload, source=OrderSource.LIVE)
    r2 = n.notify(payload, source=OrderSource.LIVE)
    assert r1.sent is True
    assert r2.deduped is True
    assert r2.reason == REASON_DUPLICATE
    assert len(tx.calls) == 1  # only the first push reached the wire


def test_dedup_not_recorded_when_send_suppressed():
    # Outbound disabled -> suppressed; later enabling must still send.
    tx = RecordingTransport()
    payload = build_execution_telegram_payload(
        PAYLOAD_SHADOW_ENTRY_PLAN, intent=_shadow_intent(), event_id="k1"
    )
    off = LiveExecutionNotifier(telegram_config=_tg(outbound=False), transport=tx)
    off.notify(payload, source=OrderSource.LIVE)
    assert tx.calls == []
    on = LiveExecutionNotifier(telegram_config=_tg(outbound=True), transport=tx)
    res = on.notify(payload, source=OrderSource.LIVE)
    assert res.sent is True
    assert len(tx.calls) == 1


def test_dedup_key_distinguishes_lifecycle_steps():
    base = dict(client_order_id="c1")
    submitted = {**base, "payload_type": PAYLOAD_LIVE_ORDER_SUBMITTED, "event_id": PLACEHOLDER}
    filled = {**base, "payload_type": PAYLOAD_LIVE_ORDER_FILLED, "event_id": PLACEHOLDER}
    assert execution_payload_dedup_key(submitted) != execution_payload_dedup_key(filled)


# ===========================================================================
# Gateway wiring
# ===========================================================================
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
        }
    ],
}
EXINFO = parse_exchange_info(SAMPLE_EXCHANGE_INFO)

ORDER_FILLED_RESPONSE = {
    "orderId": 987654322,
    "symbol": "RAVEUSDT",
    "status": "FILLED",
    "clientOrderId": "amart-fixed",
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

FAKE_KEY = "FAKEKEY00000000000000000000000000000000000000000000000000000000"
FAKE_SECRET = "FAKESECRET000000000000000000000000000000000000000000000000000"


class FakeExecutionTransport:
    def __init__(self, responses=None, *, fail_if_called=False):
        self.responses = responses or {}
        self.calls: list[dict] = []
        self.fail_if_called = fail_if_called

    def __call__(self, method, url, headers):
        from urllib.parse import urlsplit

        if self.fail_if_called:
            raise AssertionError(f"transport must NOT be called: {method} {url}")
        path = urlsplit(url).path
        self.calls.append({"method": method, "path": path})
        if path not in self.responses:
            raise AssertionError(f"unexpected path: {path}")
        value = self.responses[path]
        return value(url) if callable(value) else value


def _binance_config():
    env = {
        "AMA_BINANCE_API_KEY": FAKE_KEY,
        "AMA_BINANCE_API_SECRET": FAKE_SECRET,
        "AMA_BINANCE_ENABLE_PRIVATE_READ": "true",
        "AMA_BINANCE_ENABLE_PRIVATE_TRADE": "true",
    }
    return LiveApiConfig.from_env(env).binance


def _adapter(transport, *, runtime=LIMITED):
    return BinanceExecutionAdapter(
        _binance_config(),
        runtime_mode=runtime,
        transport=transport,
        exchange_info=EXINFO,
        clock=lambda: 1700000000000,
    )


def _gateway_intent(**kw) -> LiveOrderIntent:
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


def _armed_ctx(**kw) -> ExecutionPermissionContext:
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


def _approved_decision():
    d = LiveRiskDecision(
        approved=True,
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
    return dataclasses.replace(d, real_order_allowed=True)


def test_gateway_pushes_filled_card_real_order_true():
    notifier = RecordingNotifier()
    transport = FakeExecutionTransport({"/fapi/v1/order": ORDER_FILLED_RESPONSE})
    gw = LiveExecutionGateway(
        adapter=_adapter(transport), ledger=LiveOrderLedger(), notifier=notifier
    )
    result = gw.submit_order(_gateway_intent(), _approved_decision(), _armed_ctx())
    assert result.status is LiveExecutionStatus.FILLED
    assert len(notifier.calls) == 1
    payload, source = notifier.calls[0]
    assert source is OrderSource.LIVE
    assert payload["payload_type"] == PAYLOAD_LIVE_ORDER_FILLED
    assert payload["real_order"] is True
    assert payload["order_id"] == "987654322"


def test_gateway_pushes_blocked_card_real_order_false():
    notifier = RecordingNotifier()
    # Default (unarmed) context -> the 15-gate blocks; transport never used.
    transport = FakeExecutionTransport(fail_if_called=True)
    gw = LiveExecutionGateway(
        adapter=_adapter(transport), ledger=LiveOrderLedger(), notifier=notifier
    )
    result = gw.submit_order(_gateway_intent(), None, ExecutionPermissionContext())
    assert result.status is LiveExecutionStatus.BLOCKED
    assert len(notifier.calls) == 1
    payload, _ = notifier.calls[0]
    assert payload["payload_type"] == PAYLOAD_LIVE_EXECUTION_BLOCKED
    assert payload["real_order"] is False
    assert payload["order_id"] == PLACEHOLDER


def test_gateway_ai_authority_never_notifies():
    notifier = RecordingNotifier()
    transport = FakeExecutionTransport(fail_if_called=True)
    gw = LiveExecutionGateway(
        adapter=_adapter(transport), ledger=LiveOrderLedger(), notifier=notifier
    )
    with pytest.raises(AiTradeAuthorityForbidden):
        gw.submit_order(
            _gateway_intent(), _approved_decision(), _armed_ctx(ai_trade_authority=True)
        )
    assert notifier.calls == []


def test_notifier_exposes_no_order_surface():
    # Telegram path can never reach Binance: the notifier only sends text.
    n = LiveExecutionNotifier(telegram_config=_tg())
    assert not hasattr(n, "submit_order")
    assert not hasattr(n, "cancel_order")
