"""PR116 - 10U LIVE_LIMITED Launch Pack v0.

End-to-end live readiness, LIVE_SHADOW run, controlled real-order arming,
kill switch, gated 10U smoke, dynamic capital-profile wiring, and
blind/replay/sim isolation.

EVERY test uses fake Binance / fake Telegram / fake DeepSeek transports
only. No real API call is ever made and no real order is ever sent (except
the explicitly-gated smoke that submits through a FAKE adapter transport).

The numbered tests map to the brief's "Tests Required" list (1..40); the
capital-scaling list is C1..C10; the PR110-115-pass requirement (40) is
satisfied by the full suite run.
"""

from __future__ import annotations

import tempfile

import pytest

from app.core.enums import LiveRuntimeMode, OrderSource
from app.core.errors import LiveSourceRejected
from app.core.events import Event
from app.live.api_config import LiveApiConfig
from app.live.binance_execution_adapter import BinanceExecutionAdapter
from app.live.binance_income import classify_income_rows
from app.live.binance_models import parse_account, parse_exchange_info
from app.live.capital_profile import (
    AUTO_ESCALATION_ALLOWED,
    CapitalProfileId,
    detect_profile_mismatch,
    get_profile,
)
from app.live.execution_gateway import (
    ExecutionPermissionContext,
    ExecutionRejectReason,
    evaluate_execution_permission,
)
from app.live.execution_models import (
    LiveOrderIntent,
    OrderSide,
    OrderType,
    generate_client_order_id,
)
from app.live.live_kill_switch import LiveKillSwitch
from app.live.live_launch_readiness import LiveLaunchReadinessChecker
from app.live.live_limited_arming import LiveLimitedSmoke
from app.live.live_risk_engine import (
    LiveOrderIntent as RiskIntent,
    evaluate_live_order_risk,
)
from app.live.live_runtime import LiveRuntime
from app.live.live_shadow_runner import LiveShadowRunner
from app.live.pnl_accounting import build_live_pnl_summary
from app.live.status import HealthStatus
from app.live.telegram_commands import LiveConsoleDataProvider, TelegramCommandHandler
from app.live.telegram_state import (
    CapitalProfileStateRecord,
    ConfirmationState,
    KillSwitchState,
    LiveOperatorStateStore,
    RuntimeModeState,
)

L1 = CapitalProfileId.L1_10U_PROBE
SHADOW = LiveRuntimeMode.LIVE_SHADOW
LIMITED = LiveRuntimeMode.LIVE_LIMITED

FAKE_KEY = "FAKEKEY00000000000000000000000000000000"
FAKE_SECRET = "FAKESECRET0000000000000000000000000000"


# ---------------------------------------------------------------------------
# Fakes / fixtures
# ---------------------------------------------------------------------------
class FakeEventRepo:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, event: Event) -> None:
        self.events.append(event)

    def types(self) -> list[str]:
        return [e.event_type.value for e in self.events]


EXCHANGE_INFO_BODY = {
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
EXINFO = parse_exchange_info(EXCHANGE_INFO_BODY)


def _account_body(equity: str = "10", available: str = "10", positions=None):
    return {
        "totalWalletBalance": equity,
        "totalUnrealizedProfit": "0",
        "totalMarginBalance": equity,
        "availableBalance": available,
        "feeTier": 0,
        "canTrade": True,
        "canDeposit": False,
        "canWithdraw": False,
        "assets": [
            {"asset": "USDT", "walletBalance": equity, "availableBalance": available, "crossUnPnl": "0"}
        ],
        "positions": positions or [],
    }


def _fake_binance_transport(account_body=None, *, fail_account=False):
    """Public + private-read fake transport for BinanceLiveClient."""
    from urllib.parse import urlsplit

    def _t(method, url, headers):
        path = urlsplit(url).path
        if path == "/fapi/v1/ping":
            return {}
        if path == "/fapi/v1/time":
            return {"serverTime": 1700000000000}
        if path == "/fapi/v1/exchangeInfo":
            return EXCHANGE_INFO_BODY
        if path == "/fapi/v2/account":
            if fail_account:
                from app.core.errors import LiveApiError

                raise LiveApiError("binance: HTTP error 401 from /fapi/v2/account")
            return account_body if account_body is not None else _account_body()
        if path == "/fapi/v1/income":
            return []
        return {}

    return _t


def _binance_client(config, account_body=None, *, fail_account=False, mode=SHADOW):
    from app.live.binance_client import BinanceLiveClient

    return BinanceLiveClient(
        config.binance,
        runtime_mode=mode,
        transport=_fake_binance_transport(account_body, fail_account=fail_account),
    )


def _store(tmp_path=None) -> LiveOperatorStateStore:
    return LiveOperatorStateStore(tmp_path or tempfile.mkdtemp())


def _arm_store(store: LiveOperatorStateStore, profile=L1) -> None:
    """Persist a fully-armed LIVE_LIMITED + confirmed state.

    The kill switch is READY (available) but NOT active: a funded launch
    requires the kill switch to be ready and NOT active (an active kill
    switch is an emergency halt that blocks every new entry).
    """
    store.save_runtime_mode(RuntimeModeState(runtime_mode=LIMITED, live_limited_armed=True))
    store.save_confirmation(ConfirmationState(live_limited_confirmed=True))
    store.save_kill_switch(KillSwitchState(armed=False))
    store.save_capital_profile(CapitalProfileStateRecord(capital_profile_id=profile))


def _armed_env(**overrides):
    env = {
        "AMA_BINANCE_API_KEY": FAKE_KEY,
        "AMA_BINANCE_API_SECRET": FAKE_SECRET,
        "AMA_BINANCE_ENABLE_PRIVATE_READ": "true",
        "AMA_BINANCE_ENABLE_PRIVATE_TRADE": "true",
        "AMA_TELEGRAM_BOT_TOKEN": "123456:realtokenABCDEF",
        "AMA_TELEGRAM_ALLOWED_CHAT_IDS": "111222",
        "AMA_TELEGRAM_OUTBOUND_ENABLED": "true",
        "AMA_LIVE_EXCHANGE_LIVE_ORDERS": "true",
        "AMA_LIVE_TRADE_AUTHORITY": "true",
        "AMA_LIVE_CAPITAL_PROFILE_ID": "L1_10U_PROBE",
    }
    env.update(overrides)
    return env


def _armed_report(env_overrides=None, *, account_body=None, exchange_info=EXINFO,
                  dry_symbol="RAVEUSDT", profile=L1, pre=True, require_real_keys=False,
                  store=None):
    """Run a readiness check for a fully-armed scenario (GO=limited by default)."""
    env = _armed_env(**(env_overrides or {}))
    env["AMA_LIVE_CAPITAL_PROFILE_ID"] = profile.value
    config = LiveApiConfig.from_env(env)
    st = store or _store()
    _arm_store(st, profile=profile)
    runtime = LiveRuntime(config, state_store=st)
    client = _binance_client(config, account_body or _account_body(), mode=LIMITED)
    checker = LiveLaunchReadinessChecker(config, runtime=runtime, state_store=st)
    flags = ExecutionPermissionContext.from_config(config, environ=env)
    return checker.check(
        pre_live_limited=pre,
        require_real_keys=require_real_keys,
        check_binance=True,
        check_telegram=False,
        binance_client=client,
        exchange_info=exchange_info,
        account_snapshot=parse_account(account_body or _account_body()),
        dry_order_symbol=dry_symbol,
        execution_flags=flags,
    )


# ===========================================================================
# 1-11: launch readiness checker
# ===========================================================================
def test_01_launch_check_default_no_real_order_sent():
    config = LiveApiConfig.from_env({})
    st = _store()
    rt = LiveRuntime(config, state_store=st, capital_profile_id="L1_10U_PROBE")
    client = _binance_client(config)
    checker = LiveLaunchReadinessChecker(config, runtime=rt, state_store=st)
    rep = checker.check(check_telegram=False, binance_client=client, exchange_info=EXINFO)
    assert rep.no_real_order_sent is True
    assert rep.to_dict()["no_real_order_sent"] is True


def test_02_launch_check_missing_keys_warns_safely():
    config = LiveApiConfig.from_env({})  # no keys
    st = _store()
    rt = LiveRuntime(config, state_store=st, capital_profile_id="L1_10U_PROBE")
    client = _binance_client(config)
    checker = LiveLaunchReadinessChecker(config, runtime=rt, state_store=st)
    rep = checker.check(check_telegram=False, binance_client=client, exchange_info=EXINFO)
    # Missing keys WARN, never a hard FAIL (Phase A).
    assert rep.overall_status is not HealthStatus.FAIL
    assert rep.go_for_live_limited is False


def test_03_launch_check_placeholder_secret_fails_clearly():
    env = {"AMA_BINANCE_API_KEY": "put_your_key_here", "AMA_BINANCE_API_SECRET": "changeme"}
    config = LiveApiConfig.from_env(env)
    st = _store()
    rt = LiveRuntime(config, state_store=st)
    client = _binance_client(config)
    checker = LiveLaunchReadinessChecker(config, runtime=rt, state_store=st)
    rep = checker.check(check_telegram=False, binance_client=client, exchange_info=EXINFO)
    assert rep.overall_status is HealthStatus.FAIL
    assert "no_placeholder_secret" in rep.blockers


def test_04_launch_check_requires_private_read_for_live_limited():
    base = _armed_report()
    assert base.go_for_live_limited is True
    # Disable private read -> private_read not PASS -> blocker.
    broken = _armed_report({"AMA_BINANCE_ENABLE_PRIVATE_READ": "false"})
    assert broken.go_for_live_limited is False
    assert "binance_private_read_ok" in broken.blockers


def test_05_launch_check_requires_telegram_allowed_chat():
    broken = _armed_report({"AMA_TELEGRAM_ALLOWED_CHAT_IDS": ""})
    assert broken.go_for_live_limited is False
    assert "telegram_allowed_chat_ok" in broken.blockers


def test_06_launch_check_requires_funded_profile():
    # L0_SHADOW is not a funded profile.
    st = _store()
    broken = _armed_report(profile=CapitalProfileId.L0_SHADOW, store=st)
    assert broken.go_for_live_limited is False
    assert "capital_profile_funded" in broken.blockers
    # An approved funded profile (L2) still GOes.
    ok = _armed_report(
        {"AMA_LIVE_CAPITAL_PROFILE_ID": "L2_25U_50U_SCOUT"},
        account_body=_account_body(equity="40", available="40"),
        profile=CapitalProfileId.L2_25U_50U_SCOUT,
    )
    assert ok.go_for_live_limited is True


def test_07_launch_check_caps_usable_capital_at_10u():
    rep = _armed_report(account_body=_account_body(equity="10", available="10"))
    assert rep.usable_live_capital_usdt == 10.0
    assert rep.l1_10u_cap_enforced is True
    assert rep.capital_cap_enforced is True


def test_08_launch_check_equity_above_10u_no_auto_upgrade():
    rep = _armed_report(account_body=_account_body(equity="100", available="100"))
    # Capped at 10U; profile NOT auto-upgraded.
    assert rep.usable_live_capital_usdt == 10.0
    assert rep.capital_profile_id == "L1_10U_PROBE"
    assert rep.capital_profile_mismatch is True
    assert rep.go_for_live_limited is False  # unacknowledged mismatch
    assert AUTO_ESCALATION_ALLOWED is False


def test_09_launch_check_go_when_kill_switch_ready_and_not_active():
    # Correct LIVE_LIMITED posture: kill switch READY (available) and NOT
    # active. This must be a GO (a previous bug required it to be ACTIVE).
    rep = _armed_report()
    assert rep.kill_switch_ready is True
    assert rep.kill_switch_active is False
    assert rep.go_for_live_limited is True
    assert "kill_switch_ready" not in rep.blockers
    assert "kill_switch_not_active" not in rep.blockers


def test_09a_launch_check_no_go_when_kill_switch_not_ready():
    # If the kill-switch subsystem is NOT ready (unavailable), it is NO-GO.
    st = _store()
    _arm_store(st)
    env = _armed_env()
    config = LiveApiConfig.from_env(env)
    rt = LiveRuntime(config, state_store=st)
    client = _binance_client(config, _account_body(), mode=LIMITED)
    checker = LiveLaunchReadinessChecker(config, runtime=rt, state_store=st)
    rep = checker.check(
        pre_live_limited=True, check_telegram=False, binance_client=client,
        exchange_info=EXINFO, account_snapshot=parse_account(_account_body()),
        kill_switch_ready=False, kill_switch_active=False,
        execution_flags=ExecutionPermissionContext.from_config(config, environ=env),
    )
    assert rep.go_for_live_limited is False
    assert "kill_switch_ready" in rep.blockers
    assert rep.kill_switch_ready is False


def test_09b_launch_check_no_go_when_kill_switch_active():
    # An ACTIVE kill switch (emergency halt) is NO-GO: it blocks new entries
    # and can never be a launch requirement.
    st = _store()
    _arm_store(st)
    st.save_kill_switch(KillSwitchState(armed=True, armed_by="operator"))  # ACTIVE
    env = _armed_env()
    config = LiveApiConfig.from_env(env)
    rt = LiveRuntime(config, state_store=st)
    client = _binance_client(config, _account_body(), mode=LIMITED)
    checker = LiveLaunchReadinessChecker(config, runtime=rt, state_store=st)
    rep = checker.check(
        pre_live_limited=True, check_telegram=False, binance_client=client,
        exchange_info=EXINFO, account_snapshot=parse_account(_account_body()),
        execution_flags=ExecutionPermissionContext.from_config(config, environ=env),
    )
    assert rep.go_for_live_limited is False
    assert "kill_switch_not_active" in rep.blockers
    assert rep.kill_switch_active is True
    assert rep.kill_switch_ready is True  # the subsystem is still available


def test_09c_readiness_report_exposes_ready_and_active_clearly():
    rep = _armed_report()
    d = rep.to_dict()
    # Both distinct states are exposed (not a single ambiguous flag).
    assert d["kill_switch_ready"] is True
    assert d["kill_switch_active"] is False
    # The old key is kept ONLY as a backward-compatible alias of active.
    assert d["kill_switch_armed"] == d["kill_switch_active"]


def test_10_launch_check_requires_exchange_info_precision():
    broken = _armed_report(exchange_info=None)
    assert broken.order_precision_ok is False
    assert broken.go_for_live_limited is False
    assert "order_precision_ok" in broken.blockers


def test_11_launch_check_requires_dry_order_validation():
    # A symbol not in exchangeInfo cannot be validated.
    broken = _armed_report(dry_symbol="NOSUCHUSDT")
    assert broken.dry_order_validation_ok is False
    assert broken.go_for_live_limited is False
    assert "dry_order_validation_ok" in broken.blockers


# ===========================================================================
# 12-14: LIVE_SHADOW runner
# ===========================================================================
def _shadow_runner(env=None, store=None, sender=None, repo=None):
    config = LiveApiConfig.from_env(env or {})
    st = store or _store()
    rt = LiveRuntime(config, state_store=st, capital_profile_id="L1_10U_PROBE")
    client = _binance_client(config, _account_body())
    return LiveShadowRunner(
        config, runtime=rt, state_store=st, binance_client=client,
        telegram_sender=sender, event_repo=repo,
    )


def test_12_live_shadow_once_never_sends_order():
    runner = _shadow_runner()
    result = runner.run_once(account_snapshot=parse_account(_account_body()))
    assert result.real_order is False
    assert result.no_real_order_sent is True


def test_13_live_shadow_card_real_order_false():
    runner = _shadow_runner()
    result = runner.run_once(account_snapshot=parse_account(_account_body()))
    assert result.cards, "shadow run should produce cards"
    for card in result.cards:
        assert card.get("real_order", False) is False


def test_14_live_shadow_telegram_only_when_outbound_and_chat():
    sent_cards = []

    def sender(card):
        sent_cards.append(card)
        return True

    # Outbound disabled -> suppressed, never sent.
    runner = _shadow_runner(env={}, sender=sender)
    r1 = runner.run_once(send_telegram=True, account_snapshot=parse_account(_account_body()))
    assert r1.telegram_sent_count == 0
    assert r1.telegram_suppressed_count > 0
    assert not sent_cards

    # Outbound enabled + chat authorised -> sent.
    env = {
        "AMA_TELEGRAM_BOT_TOKEN": "123:tok",
        "AMA_TELEGRAM_ALLOWED_CHAT_IDS": "111",
        "AMA_TELEGRAM_OUTBOUND_ENABLED": "true",
    }
    runner2 = _shadow_runner(env=env, sender=sender)
    r2 = runner2.run_once(send_telegram=True, account_snapshot=parse_account(_account_body()))
    assert r2.telegram_sent_count > 0
    assert sent_cards


# ===========================================================================
# 15-18: arming
# ===========================================================================
def _handler(store=None, **kw):
    return TelegramCommandHandler(
        state_store=store or _store(), data_provider=LiveConsoleDataProvider(), **kw
    )


def test_15_live_limited_cannot_arm_without_confirmation():
    st = _store()
    st.save_capital_profile(CapitalProfileStateRecord(capital_profile_id=L1))
    st.save_kill_switch(KillSwitchState(armed=False))  # kill not active blocks confirm? no: must NOT be active
    handler = _handler(store=st)
    # /confirm_live with no pending switch -> rejected, stays SHADOW.
    res = handler.handle("/confirm_live BOGUS")
    assert res.ok is False
    assert handler.runtime_mode is SHADOW
    assert handler.live_limited_armed is False


def test_16_armed_cannot_order_if_exchange_live_orders_false():
    r = _smoke_real(exchange_live_orders=False, trade_authority=True)
    assert r.real_order is False
    assert r.no_real_order_sent is True


def test_17_armed_cannot_order_if_trade_authority_false():
    r = _smoke_real(exchange_live_orders=True, trade_authority=False)
    assert r.real_order is False
    assert r.no_real_order_sent is True


def test_18_armed_cannot_order_if_private_trade_false():
    r = _smoke_real(exchange_live_orders=True, trade_authority=True, private_trade=False)
    assert r.real_order is False
    assert r.no_real_order_sent is True


# ===========================================================================
# 19-27: live limited smoke
# ===========================================================================
ORDER_FILLED = {
    "orderId": 99,
    "symbol": "RAVEUSDT",
    "status": "FILLED",
    "clientOrderId": "x",
    "avgPrice": "1.0",
    "executedQty": "6",
    "cumQuote": "6.0",
    "type": "MARKET",
    "side": "BUY",
    "updateTime": 1700000000200,
}


def _smoke(env=None, *, profile=L1, store=None, repo=None, fill=True):
    from urllib.parse import urlsplit

    env = _armed_env(**(env or {}))
    config = LiveApiConfig.from_env(env)
    st = store or _store()
    _arm_store(st, profile=profile)
    st.save_kill_switch(KillSwitchState(armed=False))  # kill must NOT be active to order
    rt = LiveRuntime(config, state_store=st)

    def transport(method, url, headers):
        if urlsplit(url).path == "/fapi/v1/order" and method == "POST":
            return ORDER_FILLED
        return {}

    adapter = BinanceExecutionAdapter(
        config.binance, runtime_mode=LIMITED, transport=transport, exchange_info=EXINFO,
        event_repo=repo,
    )
    return LiveLimitedSmoke(config, runtime=rt, adapter=adapter, event_repo=repo)


def _smoke_real(*, exchange_live_orders=True, trade_authority=True, private_trade=True,
                notional=6.0, leverage=1.0, with_plan=True, confirm="CODE",
                expected="CODE", i_understand=True, max_notional=20.0, repo=None):
    env = {} if private_trade else {"AMA_BINANCE_ENABLE_PRIVATE_TRADE": "false"}
    smoke = _smoke(env=env, repo=repo)
    return smoke.run(
        symbol="RAVEUSDT", notional_usdt=notional, leverage=leverage, real_order=True,
        i_understand_this_places_real_order=i_understand, confirm_code=confirm,
        expected_confirm_code=expected, max_notional_usdt=max_notional,
        exchange_live_orders=exchange_live_orders, trade_authority=trade_authority,
        account_snapshot=parse_account(_account_body()),
        planned_entry_price=1.0 if with_plan else None,
        planned_stop_price=0.9 if with_plan else None,
        planned_take_profit_price=1.2 if with_plan else None,
    )


def test_19_smoke_dry_run_no_real_order():
    smoke = _smoke()
    r = smoke.run(
        symbol="RAVEUSDT", notional_usdt=6, leverage=1,
        account_snapshot=parse_account(_account_body()),
        planned_entry_price=1.0, planned_stop_price=0.9, planned_take_profit_price=1.2,
    )
    assert r.dry_run is True
    assert r.real_order is False
    assert r.no_real_order_sent is True


def test_20_smoke_real_blocked_without_flags():
    smoke = _smoke()
    r = smoke.run(
        symbol="RAVEUSDT", notional_usdt=6, leverage=1, real_order=True,
        i_understand_this_places_real_order=False, confirm_code="CODE",
        expected_confirm_code="CODE", max_notional_usdt=20,
        exchange_live_orders=True, trade_authority=True,
        account_snapshot=parse_account(_account_body()),
        planned_entry_price=1.0, planned_stop_price=0.9, planned_take_profit_price=1.2,
    )
    assert r.real_order is False
    assert r.blocked_reason == "missing_i_understand_flag"


def test_21_smoke_real_blocked_without_confirmation_code():
    smoke = _smoke()
    r = smoke.run(
        symbol="RAVEUSDT", notional_usdt=6, leverage=1, real_order=True,
        i_understand_this_places_real_order=True, confirm_code="WRONG",
        expected_confirm_code="CODE", max_notional_usdt=20,
        exchange_live_orders=True, trade_authority=True,
        account_snapshot=parse_account(_account_body()),
        planned_entry_price=1.0, planned_stop_price=0.9, planned_take_profit_price=1.2,
    )
    assert r.real_order is False
    assert r.blocked_reason == "invalid_or_missing_confirmation_code"


def test_22_smoke_real_uses_execution_gateway():
    smoke = _smoke()
    r = smoke.run(
        symbol="RAVEUSDT", notional_usdt=6, leverage=1, real_order=True,
        i_understand_this_places_real_order=True, confirm_code="CODE",
        expected_confirm_code="CODE", max_notional_usdt=20,
        exchange_live_orders=True, trade_authority=True,
        account_snapshot=parse_account(_account_body()),
        planned_entry_price=1.0, planned_stop_price=0.9, planned_take_profit_price=1.2,
    )
    assert r.real_order is True
    assert r.order_status == "FILLED"
    assert r.exchange_order_id == "99"
    assert smoke.gateway is not None and len(smoke.gateway.ledger) >= 1


def test_23_smoke_rejects_no_stop_exit_plan():
    smoke = _smoke()
    # Dry-run exposes the full gate reason list.
    r = smoke.run(
        symbol="RAVEUSDT", notional_usdt=6, leverage=1,
        account_snapshot=parse_account(_account_body()),
    )  # no planned prices -> no stop/exit plan
    assert ExecutionRejectReason.MISSING_STOP_OR_EXIT_PLAN in r.reject_reasons


def test_24_smoke_rejects_oversized_notional():
    smoke = _smoke()
    r = smoke.run(
        symbol="RAVEUSDT", notional_usdt=50, leverage=1,  # profile max 20
        account_snapshot=parse_account(_account_body()),
        planned_entry_price=1.0, planned_stop_price=0.9, planned_take_profit_price=1.2,
    )
    assert ExecutionRejectReason.NOTIONAL_EXCEEDS_PROFILE_MAX in r.reject_reasons


def test_25_smoke_rejects_leverage_above_profile():
    smoke = _smoke()
    r = smoke.run(
        symbol="RAVEUSDT", notional_usdt=6, leverage=99,  # profile max 5 (rt 10)
        account_snapshot=parse_account(_account_body()),
        planned_entry_price=1.0, planned_stop_price=0.9, planned_take_profit_price=1.2,
    )
    assert ExecutionRejectReason.LEVERAGE_EXCEEDS_PROFILE_MAX in r.reject_reasons


def test_26_ledger_records_smoke_order():
    repo = FakeEventRepo()
    smoke = _smoke(repo=repo)
    r = smoke.run(
        symbol="RAVEUSDT", notional_usdt=6, leverage=1, real_order=True,
        i_understand_this_places_real_order=True, confirm_code="CODE",
        expected_confirm_code="CODE", max_notional_usdt=20,
        exchange_live_orders=True, trade_authority=True,
        account_snapshot=parse_account(_account_body()),
        planned_entry_price=1.0, planned_stop_price=0.9, planned_take_profit_price=1.2,
    )
    assert r.ledger_recorded is True
    assert len(smoke.gateway.ledger) >= 1
    row = smoke.gateway.ledger.rows[-1]
    assert row.is_real_order is True


def test_27_smoke_result_card_has_fee_funding_netpnl_fields():
    smoke = _smoke()
    r = smoke.run(
        symbol="RAVEUSDT", notional_usdt=6, leverage=1, real_order=True,
        i_understand_this_places_real_order=True, confirm_code="CODE",
        expected_confirm_code="CODE", max_notional_usdt=20,
        exchange_live_orders=True, trade_authority=True,
        account_snapshot=parse_account(_account_body()),
        planned_entry_price=1.0, planned_stop_price=0.9, planned_take_profit_price=1.2,
    )
    card = r.telegram_result_card()
    for key in ("fee", "funding_status", "net_pnl", "order_id", "real_order"):
        assert key in card


# ===========================================================================
# 28-29: kill switch / rollback
# ===========================================================================
def test_28_kill_switch_blocks_new_entries():
    st = _store()
    ks = LiveKillSwitch(state_store=st)
    ks.arm(by="operator")
    status = ks.status()
    assert status.armed is True
    assert status.blocks_new_entries is True
    # The execution context built with kill switch active blocks orders.
    config = LiveApiConfig.from_env(_armed_env())
    rt = LiveRuntime(config, state_store=st)
    ctx = rt.build_execution_context(
        exchange_live_orders=True, trade_authority=True, account_equity_usdt=10.0
    )
    assert ctx.kill_switch_active is True


def test_29_mode_shadow_rollback_disarms_live_limited():
    st = _store()
    st.save_capital_profile(CapitalProfileStateRecord(capital_profile_id=L1))
    handler = _handler(store=st)
    handler.handle("/mode live_limited")
    # confirm with the issued pending code.
    pending = handler._confirmation.pending_code  # type: ignore[attr-defined]
    handler.handle(f"/confirm_live {pending}")
    assert handler.runtime_mode is LIMITED
    assert handler.live_limited_armed is True
    # Roll back.
    handler.handle("/mode shadow")
    assert handler.runtime_mode is SHADOW
    assert handler.live_limited_armed is False


def test_28b_smoke_rejects_when_kill_switch_active():
    # An ACTIVE kill switch must block a fully-flagged real-order smoke.
    st = _store()
    smoke = _smoke(store=st)
    st.save_kill_switch(KillSwitchState(armed=True, armed_by="operator"))  # ACTIVATE
    r = smoke.run(
        symbol="RAVEUSDT", notional_usdt=6, leverage=1, real_order=True,
        i_understand_this_places_real_order=True, confirm_code="CODE",
        expected_confirm_code="CODE", max_notional_usdt=20,
        exchange_live_orders=True, trade_authority=True,
        account_snapshot=parse_account(_account_body()),
        planned_entry_price=1.0, planned_stop_price=0.9, planned_take_profit_price=1.2,
    )
    assert r.real_order is False
    assert r.no_real_order_sent is True
    assert r.blocked_reason == ExecutionRejectReason.KILL_SWITCH_ACTIVE


def test_28c_smoke_not_rejected_merely_because_kill_switch_ready():
    # Kill switch READY (available) but NOT active must NOT block ordering.
    # The dry-run exposes the full gate reason list; KILL_SWITCH_ACTIVE
    # must not appear when the switch is merely ready.
    smoke = _smoke()  # _arm_store leaves the kill switch ready, not active
    r = smoke.run(
        symbol="RAVEUSDT", notional_usdt=6, leverage=1,
        account_snapshot=parse_account(_account_body()),
        planned_entry_price=1.0, planned_stop_price=0.9, planned_take_profit_price=1.2,
    )
    assert ExecutionRejectReason.KILL_SWITCH_ACTIVE not in r.reject_reasons


def test_28d_confirm_kill_sets_active_and_blocks_new_entries():
    # /kill_all -> /confirm_kill activates the kill switch + blocks entries.
    st = _store()
    st.save_capital_profile(CapitalProfileStateRecord(capital_profile_id=L1))
    handler = _handler(store=st)
    r1 = handler.handle("/kill_all")
    code = r1.card["confirmation_code"]
    r2 = handler.handle("/confirm_kill " + code)
    assert r2.ok is True
    assert handler.kill_switch_armed is True  # active (alias)
    # /kill_status surfaces the split state + blocks_new_entries.
    ks = handler.handle("/kill_status")
    assert ks.card["kill_switch_active"] is True
    assert ks.card["kill_switch_ready"] is True
    assert ks.card["blocks_new_entries"] is True
    # The execution context built afterwards reports the active halt.
    config = LiveApiConfig.from_env(_armed_env())
    rt = LiveRuntime(config, state_store=st)
    ctx = rt.build_execution_context(exchange_live_orders=True, trade_authority=True)
    assert ctx.kill_switch_active is True


def test_28e_kill_switch_status_card_split_states():
    # The LiveKillSwitch status card clearly carries ready / active /
    # blocks_new_entries (PR116 hotfix disambiguation).
    st = _store()
    ks = LiveKillSwitch(state_store=st)
    ready_status = ks.status()
    assert ready_status.ready is True
    assert ready_status.active is False
    assert ready_status.blocks_new_entries is False
    card = ready_status.telegram_card()
    assert card["kill_switch_ready"] is True
    assert card["kill_switch_active"] is False
    # Activate -> active + blocks new entries.
    ks.arm(by="operator")
    active_status = ks.status()
    assert active_status.active is True
    assert active_status.ready is True
    assert active_status.blocks_new_entries is True


def test_28f_arming_status_rejects_only_on_active_not_ready():
    # evaluate_arming: an ACTIVE kill switch is a missing gate; a READY
    # (not active) kill switch is NOT a blocker for arming.
    from app.live.live_limited_arming import evaluate_arming

    env = _armed_env()
    config = LiveApiConfig.from_env(env)
    st = _store()
    _arm_store(st)  # ready, not active
    rt = LiveRuntime(config, state_store=st)
    armed = evaluate_arming(
        config, rt, exchange_live_orders=True, trade_authority=True
    )
    assert armed.kill_switch_ready is True
    assert armed.kill_switch_active is False
    assert "kill_switch_active" not in armed.missing_gates()
    assert armed.fully_armed is True
    # Activate -> kill_switch_active becomes a missing gate.
    st.save_kill_switch(KillSwitchState(armed=True, armed_by="operator"))
    armed2 = evaluate_arming(
        config, rt, exchange_live_orders=True, trade_authority=True
    )
    assert armed2.kill_switch_active is True
    assert "kill_switch_active" in armed2.missing_gates()
    assert armed2.fully_armed is False


# ===========================================================================
# 30-34: blind/replay/sim isolation
# ===========================================================================
@pytest.mark.parametrize("src", [OrderSource.BLIND, OrderSource.REPLAY, OrderSource.SIM])
def test_30_31_32_nonlive_source_rejected_from_live_launch(src):
    with pytest.raises(LiveSourceRejected):
        LiveRuntime.assert_live_source(src, action="live_launch")
    # And the launch readiness self-check confirms isolation holds.
    rep = _armed_report()
    assert rep.live_path_isolation_ok is True
    assert rep.blind_sim_isolation_ok is True


def test_33_mock_exchange_cannot_be_injected_into_live_runtime():
    class MockExchange:  # name matches the forbidden set
        pass

    with pytest.raises(LiveSourceRejected):
        LiveRuntime.assert_live_market_source(MockExchange(), action="live_market_source")


def test_34_historical_market_store_cannot_be_live_source():
    class HistoricalMarketStore:
        pass

    with pytest.raises(LiveSourceRejected):
        LiveRuntime.assert_live_market_source(HistoricalMarketStore())


# ===========================================================================
# 35: AI has no launch/execute authority
# ===========================================================================
def test_35_ai_briefing_cannot_trigger_launch_or_execute():
    repo = FakeEventRepo()
    runner = _shadow_runner(repo=repo)
    result = runner.run_once(
        with_ai_briefing=True, ai_dry_run=True,
        account_snapshot=parse_account(_account_body()),
    )
    # The AI briefing is informational only; no order, no authority.
    assert result.no_real_order_sent is True
    ai_cards = [c for c in result.cards if c.get("card_type") == "LIVE_AI_BRIEFING"]
    for c in ai_cards:
        assert c.get("ai_trade_authority") is False


# ===========================================================================
# 36-38: funding-aware PnL
# ===========================================================================
def test_36_deposit_not_counted_as_profit():
    rows = [
        {"incomeType": "REALIZED_PNL", "income": "5", "asset": "USDT"},
        {"incomeType": "TRANSFER", "income": "100", "asset": "USDT"},  # deposit
    ]
    pnl = build_live_pnl_summary(classify_income_rows(rows))
    assert pnl.transfer_in_total_usdt == 100.0
    # net strategy pnl excludes the external deposit.
    assert pnl.net_strategy_pnl_usdt == 5.0


def test_37_withdrawal_not_counted_as_loss():
    rows = [
        {"incomeType": "REALIZED_PNL", "income": "5", "asset": "USDT"},
        {"incomeType": "TRANSFER", "income": "-30", "asset": "USDT"},  # withdrawal
    ]
    pnl = build_live_pnl_summary(classify_income_rows(rows))
    assert pnl.transfer_out_total_usdt == 30.0
    assert pnl.net_strategy_pnl_usdt == 5.0  # withdrawal is not a loss


def test_38_funding_included_in_net_pnl():
    rows = [
        {"incomeType": "REALIZED_PNL", "income": "10", "asset": "USDT"},
        {"incomeType": "COMMISSION", "income": "-1", "asset": "USDT"},
        {"incomeType": "FUNDING_FEE", "income": "-2", "asset": "USDT"},
    ]
    pnl = build_live_pnl_summary(classify_income_rows(rows))
    # net = realized(10) - commission(1) + funding(-2) = 7
    assert pnl.funding_total_usdt == -2.0
    assert pnl.net_strategy_pnl_usdt == 7.0


# ===========================================================================
# 39: safety defaults remain safe
# ===========================================================================
def test_39_safety_defaults_remain_safe():
    config = LiveApiConfig.from_env({})
    assert config.live_runtime_mode is SHADOW
    ctx = ExecutionPermissionContext.from_config(config, environ={})
    assert ctx.exchange_live_orders is False
    assert ctx.trade_authority is False
    assert ctx.ai_trade_authority is False
    assert ctx.fully_armed is False
    rt = LiveRuntime(config, state_store=_store())
    assert rt.runtime_mode() is SHADOW
    assert rt.kill_switch_armed() is False
    from app.live.live_launch_models import launch_safety_markers

    m = launch_safety_markers()
    assert m["real_order"] is False and m["no_real_order_sent"] is True
    assert m["trade_authority"] is False and m["ai_trade_authority"] is False


# ===========================================================================
# 40: existing PR110-115 modules still import / interop
# ===========================================================================
def test_40_existing_pr110_115_modules_import():
    import app.live.runtime_mode  # noqa: F401
    import app.live.path_isolation  # noqa: F401
    import app.live.capital_profile  # noqa: F401
    import app.live.capital_state  # noqa: F401
    import app.live.execution_gateway  # noqa: F401
    import app.live.ai_live_briefing  # noqa: F401
    # The launch pack reuses them without redefining their contracts.
    assert get_profile(L1).max_account_capital_usdt == 10.0


# ===========================================================================
# C1-C10: capital scaling without a new PR
# ===========================================================================
def test_C1_10u_profile_caps_usable_capital_at_10u():
    from app.live.capital_state import LiveCapitalState
    from app.live.live_risk_engine import evaluate_capital_profile_state

    state = LiveCapitalState.from_account_snapshot(
        parse_account(_account_body(equity="50", available="50")),
        capital_profile_id=L1,
    )
    ps = evaluate_capital_profile_state(state, L1)
    assert ps.usable_capital_usdt == 10.0


def test_C2_50u_profile_differs_from_10u():
    p1 = get_profile(L1)
    p2 = get_profile(CapitalProfileId.L2_25U_50U_SCOUT)
    assert p2.max_account_capital_usdt != p1.max_account_capital_usdt
    assert p2.max_position_notional_usdt != p1.max_position_notional_usdt
    assert p2.max_active_positions != p1.max_active_positions


def test_C3_1000u_profile_differs_from_10u():
    p1 = get_profile(L1)
    p4 = get_profile(CapitalProfileId.L4_1K_GROWTH)
    assert p4.max_account_capital_usdt == 1000.0
    assert p4.max_position_notional_usdt != p1.max_position_notional_usdt
    assert p4.max_position_pct_of_equity != p1.max_position_pct_of_equity


def test_C4_10000u_profile_does_not_reuse_10u_limits():
    p1 = get_profile(L1)
    p5 = get_profile(CapitalProfileId.L5_10K_PROFIT_PROTECTION)
    assert p5.max_account_capital_usdt == 10000.0
    assert p5.max_leverage <= p1.max_leverage
    assert p5.max_daily_loss_usdt != p1.max_daily_loss_usdt
    assert p5.profit_harvest_enabled is True


def test_C5_profile_mismatch_does_not_auto_upgrade():
    mm = detect_profile_mismatch(L1, 10000.0)
    assert mm.mismatch is True
    assert mm.direction == "escalate"
    assert mm.suggested_profile_id is not L1
    assert mm.requires_operator_action is True
    assert AUTO_ESCALATION_ALLOWED is False


def test_C6_operator_profile_switch_changes_caps_without_code_change():
    config = LiveApiConfig.from_env({})
    st = _store()
    rt = LiveRuntime(config, state_store=st, capital_profile_id="L1_10U_PROBE")
    caps_10u = rt.profile_caps()
    assert caps_10u.max_account_capital_usdt == 10.0
    # Operator switches profile -> caps change, no code change.
    rt.set_capital_profile("L4_1K_GROWTH", by="operator")
    caps_1k = rt.profile_caps()
    assert caps_1k.max_account_capital_usdt == 1000.0
    assert caps_1k.max_position_notional_usdt != caps_10u.max_position_notional_usdt
    assert rt.active_capital_profile_id() is CapitalProfileId.L4_1K_GROWTH


def test_C7_deposit_not_strategy_profit():
    rows = [{"incomeType": "TRANSFER", "income": "500", "asset": "USDT"}]
    pnl = build_live_pnl_summary(classify_income_rows(rows))
    assert pnl.net_strategy_pnl_usdt == 0.0
    assert pnl.transfer_in_total_usdt == 500.0


def test_C8_withdrawal_not_strategy_loss():
    rows = [{"incomeType": "TRANSFER", "income": "-200", "asset": "USDT"}]
    pnl = build_live_pnl_summary(classify_income_rows(rows))
    assert pnl.net_strategy_pnl_usdt == 0.0
    assert pnl.transfer_out_total_usdt == 200.0


def test_C9_live_risk_decision_uses_active_profile_dynamically():
    from app.live.capital_state import LiveCapitalState

    state = LiveCapitalState.from_account_snapshot(
        parse_account(_account_body(equity="40", available="40")),
        runtime_mode=LIMITED,
        capital_profile_id=CapitalProfileId.L2_25U_50U_SCOUT,
    )
    intent = RiskIntent(
        symbol="RAVEUSDT", side="LONG", planned_entry_price=1.0,
        planned_notional_usdt=60.0, planned_leverage=2.0,
        planned_stop_price=0.9, exit_plan_present=True, stop_plan_present=True,
        runtime_mode=LIMITED, source=OrderSource.LIVE,
    )
    d_l1 = evaluate_live_order_risk(intent, state, L1, runtime_mode=LIMITED)
    d_l2 = evaluate_live_order_risk(
        intent, state, CapitalProfileId.L2_25U_50U_SCOUT, runtime_mode=LIMITED
    )
    # The notional ceiling differs by profile (L1=20, L2=100).
    assert d_l1.max_allowed_notional_usdt == 20.0
    assert d_l2.max_allowed_notional_usdt == 100.0


def test_C10_live_execution_gateway_uses_active_profile_dynamically():
    # Notional 50: allowed under L2 (max 100), rejected under L1 (max 20).
    ctx = ExecutionPermissionContext(
        runtime_mode=LIMITED, live_limited_confirmed=True, exchange_live_orders=True,
        trade_authority=True, private_trade_enabled=True,
    )
    intent = LiveOrderIntent(
        symbol="RAVEUSDT", side=OrderSide.BUY, order_type=OrderType.MARKET,
        quantity=50, notional_usdt=50.0, planned_entry_price=1.0,
        planned_stop_price=0.9, planned_take_profit_price=1.2, planned_leverage=2.0,
        exit_plan_present=True, stop_plan_present=True,
        client_order_id=generate_client_order_id(), source=OrderSource.LIVE,
        runtime_mode=LIMITED, capital_profile_id=L1,
    )
    d_l1 = evaluate_execution_permission(intent, None, ctx, profile=get_profile(L1))
    d_l2 = evaluate_execution_permission(
        intent, None, ctx, profile=get_profile(CapitalProfileId.L2_25U_50U_SCOUT)
    )
    assert ExecutionRejectReason.NOTIONAL_EXCEEDS_PROFILE_MAX in d_l1.reject_reasons
    assert ExecutionRejectReason.NOTIONAL_EXCEEDS_PROFILE_MAX not in d_l2.reject_reasons
