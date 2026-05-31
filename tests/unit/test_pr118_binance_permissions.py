"""PR118 - Binance API permission false-positive hotfix.

The bug: the real-key health check reported
``binance_key_has_withdraw_permission`` /
``binance_key_has_deposit_permission`` even when the Binance UI showed
withdraw DISABLED, because the warning was inferred from the FUTURES
account capability (``/fapi/v2/account`` ``canWithdraw`` / ``canDeposit``)
instead of the API-KEY restriction endpoint
(``/sapi/v1/account/apiRestrictions`` ``enableWithdrawals``).

The fix: the withdraw warning is raised ONLY when the raw
``apiRestrictions.enableWithdrawals`` field is explicitly ``True``.
Universal / internal transfer are their own (lower-severity) warnings, not
withdraw warnings. Fields the API does not expose are NOT_REPORTED, never
``True``. No safety gate is weakened and no real order path is touched.

Every test uses a fake transport - no network, no real order.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

import pytest

from app.core.errors import LiveTradeNotEnabled
from app.core.events import Event, EventType
from app.live.api_config import LiveApiConfig, LiveRuntimeMode
from app.live.binance_client import FORBIDDEN_TRADE_ENDPOINTS, BinanceLiveClient
from app.live.binance_models import (
    NOT_REPORTED,
    parse_account,
    parse_api_restrictions,
)
from app.live.binance_permissions import (
    SEVERITY_BLOCKER,
    SEVERITY_INFO,
    SEVERITY_WARN,
    WARNING_WITHDRAW_ENABLED,
    inspect_permissions,
)
from app.live.health import run_unified_health_check
from app.live.status import HealthStatus

FAKE_KEY = "FAKEKEY" + "0" * 57
FAKE_SECRET = "FAKESECRET" + "0" * 54

SAPI_RESTRICTIONS_PATH = "/sapi/v1/account/apiRestrictions"

# A trade-capable, NO-withdraw account (the exact real-key shape from the
# brief: reading enabled, withdraw disabled, futures trade enabled).
SAMPLE_ACCOUNT = {
    "totalWalletBalance": "1000.5",
    "totalUnrealizedProfit": "0",
    "totalMarginBalance": "1000.5",
    "availableBalance": "1000.5",
    "feeTier": 0,
    "canTrade": True,
    "canDeposit": True,
    "canWithdraw": True,  # account-level capability (NOT a key permission!)
    "assets": [{"asset": "USDT", "walletBalance": "1000.5", "availableBalance": "1000.5", "crossUnPnl": "0"}],
    "positions": [],
}

SAMPLE_EXCHANGE_INFO = {
    "serverTime": 1700000000000,
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "status": "TRADING",
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "1000"},
                {"filterType": "MIN_NOTIONAL", "notional": "100"},
            ],
        }
    ],
}

# The UI-confirmed real-key restriction set: reading + futures enabled,
# withdraw disabled, IP whitelist on, universal transfer disabled.
RESTRICTIONS_UI_CONFIRMED = {
    "ipRestrict": True,
    "createTime": 1623840271000,
    "enableReading": True,
    "enableWithdrawals": False,
    "enableInternalTransfer": False,
    "permitsUniversalTransfer": False,
    "enableFutures": True,
    "enableSpotAndMarginTrading": False,
    "tradingAuthorityExpirationTime": 1628985600000,
}


class FakeEventRepo:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, event: Event) -> None:
        self.events.append(event)

    def types(self) -> list[EventType]:
        return [e.event_type for e in self.events]


class FakeBinanceTransport:
    """Routes by URL path. Records every call. Never opens a socket.

    Fails loudly if any forbidden trade / order endpoint is ever requested.
    """

    def __init__(self, responses: dict) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method: str, url: str, headers):
        path = urlsplit(url).path
        self.calls.append((method, path))
        assert path not in FORBIDDEN_TRADE_ENDPOINTS, f"order path called: {path}"
        if path not in self.responses:
            raise AssertionError(f"unexpected path: {path}")
        value = self.responses[path]
        return value(url) if callable(value) else value


def _read_env() -> dict:
    return {
        "AMA_BINANCE_API_KEY": FAKE_KEY,
        "AMA_BINANCE_API_SECRET": FAKE_SECRET,
        "AMA_BINANCE_ENABLE_PRIVATE_READ": "true",
    }


def _client(env: dict, *, transport, runtime_mode=LiveRuntimeMode.LIVE_SHADOW, event_repo=None):
    cfg = LiveApiConfig.from_env(env)
    return BinanceLiveClient(
        cfg.binance,
        runtime_mode=runtime_mode,
        transport=transport,
        event_repo=event_repo,
        clock=lambda: 1700000000000,
    )


def _health_transport(restrictions: dict | None):
    responses = {
        "/fapi/v1/ping": {},
        "/fapi/v1/time": {"serverTime": 1700000000000},
        "/fapi/v1/exchangeInfo": SAMPLE_EXCHANGE_INFO,
        "/fapi/v2/account": SAMPLE_ACCOUNT,
        "/fapi/v1/income": [],
    }
    if restrictions is not None:
        responses[SAPI_RESTRICTIONS_PATH] = restrictions
    return FakeBinanceTransport(responses)


# ===========================================================================
# Test 1: enableWithdrawals=false does NOT emit a withdraw warning.
# ===========================================================================
def test_1_enable_withdrawals_false_no_withdraw_warning():
    restr = parse_api_restrictions(RESTRICTIONS_UI_CONFIRMED)
    perms = inspect_permissions(account=parse_account(SAMPLE_ACCOUNT), restrictions=restr)
    assert perms.withdraw_permission is False
    assert perms.high_risk_permission_warning is False
    assert not any("binance_key_has_withdraw_permission" in w for w in perms.warnings)
    # No deposit warning is ever emitted (PR118 removed it).
    assert not any("binance_key_has_deposit_permission" in w for w in perms.warnings)


# ===========================================================================
# Test 2: enableWithdrawals=true DOES emit a withdraw warning (BLOCKER).
# ===========================================================================
def test_2_enable_withdrawals_true_emits_withdraw_warning():
    restr = parse_api_restrictions({**RESTRICTIONS_UI_CONFIRMED, "enableWithdrawals": True})
    perms = inspect_permissions(account=parse_account(SAMPLE_ACCOUNT), restrictions=restr)
    assert perms.withdraw_permission is True
    assert perms.high_risk_permission_warning is True
    assert any("binance_key_has_withdraw_permission" in w for w in perms.warnings)
    assert (SEVERITY_BLOCKER, WARNING_WITHDRAW_ENABLED) in perms.findings


# ===========================================================================
# Test 3: permitsUniversalTransfer=true -> transfer warning, NOT withdraw.
# ===========================================================================
def test_3_universal_transfer_true_is_transfer_warning_not_withdraw():
    restr = parse_api_restrictions(
        {**RESTRICTIONS_UI_CONFIRMED, "permitsUniversalTransfer": True}
    )
    perms = inspect_permissions(account=parse_account(SAMPLE_ACCOUNT), restrictions=restr)
    assert perms.universal_transfer_permission is True
    assert perms.high_risk_permission_warning is False
    assert any("binance_key_has_universal_transfer_permission" in w for w in perms.warnings)
    assert not any("binance_key_has_withdraw_permission" in w for w in perms.warnings)
    assert any(sev == SEVERITY_WARN for sev, _ in perms.findings)


# ===========================================================================
# Test 4: enableInternalTransfer=true -> internal transfer warning, NOT withdraw.
# ===========================================================================
def test_4_internal_transfer_true_is_internal_warning_not_withdraw():
    restr = parse_api_restrictions(
        {**RESTRICTIONS_UI_CONFIRMED, "enableInternalTransfer": True}
    )
    perms = inspect_permissions(account=parse_account(SAMPLE_ACCOUNT), restrictions=restr)
    assert perms.internal_transfer_permission is True
    assert perms.high_risk_permission_warning is False
    assert any("binance_key_has_internal_transfer_permission" in w for w in perms.warnings)
    assert not any("binance_key_has_withdraw_permission" in w for w in perms.warnings)


# ===========================================================================
# Test 5: account canTrade=true does NOT emit a withdraw warning.
# ===========================================================================
def test_5_account_can_trade_true_no_withdraw_warning():
    # canTrade / canWithdraw / canDeposit are all account-level capabilities;
    # none of them may drive a withdraw warning.
    acct = parse_account(
        {**SAMPLE_ACCOUNT, "canTrade": True, "canWithdraw": True, "canDeposit": True}
    )
    # No restrictions read at all -> everything NOT_REPORTED -> no warning.
    perms = inspect_permissions(account=acct)
    assert perms.can_trade_if_account_reports_it is True
    assert perms.high_risk_permission_warning is False
    assert not any("binance_key_has_withdraw_permission" in w for w in perms.warnings)
    # canTrade is surfaced only as an INFO finding.
    assert any(sev == SEVERITY_INFO for sev, _ in perms.findings)

    # And even with an explicit no-withdraw restriction set, still no warning.
    restr = parse_api_restrictions(RESTRICTIONS_UI_CONFIRMED)
    perms2 = inspect_permissions(account=acct, restrictions=restr)
    assert perms2.high_risk_permission_warning is False


# ===========================================================================
# Test 6: private read still PASS for a UI-confirmed no-withdraw key.
# ===========================================================================
def test_6_private_read_still_pass():
    transport = _health_transport(RESTRICTIONS_UI_CONFIRMED)
    cli = _client(_read_env(), transport=transport)
    result = cli.health_check()
    assert result.public_market_ok is True
    assert result.private_read_ok is True
    assert result.high_risk_permission_warning is False
    assert result.withdraw_permission is False
    assert result.api_restrictions_reported is True
    assert result.status is HealthStatus.PASS

    # Unified report: private read PASS (the false positive is gone).
    cli2 = _client(_read_env(), transport=_health_transport(RESTRICTIONS_UI_CONFIRMED))
    report = run_unified_health_check(
        LiveApiConfig.from_env(_read_env()),
        check_binance=True,
        check_telegram=False,
        binance_client=cli2,
    )
    assert report.binance_private_read_status is HealthStatus.PASS
    assert not any("withdraw" in w for w in report.warnings)


# ===========================================================================
# Test 7: secrets are masked; no key / secret / signature leaks anywhere.
# ===========================================================================
def test_7_secrets_masked_no_leak():
    transport = _health_transport({**RESTRICTIONS_UI_CONFIRMED, "enableWithdrawals": True})
    cli = _client(_read_env(), transport=transport)
    result = cli.health_check()
    blob = json.dumps(result.to_dict())
    assert FAKE_KEY not in blob
    assert FAKE_SECRET not in blob
    assert result.masked_api_key != FAKE_KEY
    # The sanitised debug carries field names + tri-state values only - no
    # secret, no signature, no account id / create time.
    debug = result.permission_debug
    assert "raw_permission_fields_seen" in debug
    assert "createTime" not in debug
    assert "tradingAuthorityExpirationTime" not in debug
    assert FAKE_SECRET not in json.dumps(debug)
    assert "signature" not in json.dumps(debug).lower()


# ===========================================================================
# Test 8: the real-order path is never touched by the permission read.
# ===========================================================================
def test_8_no_real_order_path_affected():
    transport = _health_transport({**RESTRICTIONS_UI_CONFIRMED, "enableWithdrawals": True})
    repo = FakeEventRepo()
    cli = _client(_read_env(), transport=transport, event_repo=repo)
    cli.health_check()
    # No order / leverage / margin endpoint was ever contacted.
    called = {path for _, path in transport.calls}
    assert not (called & FORBIDDEN_TRADE_ENDPOINTS)
    # The SAPI restriction read is a GET, never a POST.
    assert all(method == "GET" for method, _ in transport.calls)
    # Trade surfaces remain blocked regardless of permissions.
    with pytest.raises(LiveTradeNotEnabled):
        cli.create_order(symbol="BTCUSDT", side="BUY", qty=0.01)
    # Even with a withdraw-enabled key, the permission warning event fires
    # but no order is sent.
    assert EventType.BINANCE_PERMISSION_WARNING in repo.types()


# ===========================================================================
# Additional coverage: NOT_REPORTED handling + endpoint-unavailable safety.
# ===========================================================================
def test_not_reported_fields_never_become_true():
    # An empty / partial body must NEVER infer a permission as enabled.
    empty = parse_api_restrictions({})
    assert empty.reported is False
    assert empty.enable_withdrawals is None
    perms = inspect_permissions(account=parse_account(SAMPLE_ACCOUNT), restrictions=empty)
    assert perms.high_risk_permission_warning is False
    assert perms.withdraw_permission is None
    debug = empty.to_debug_dict()
    assert debug["enableWithdrawals"] == NOT_REPORTED
    assert debug["permitsUniversalTransfer"] == NOT_REPORTED


def test_restrictions_endpoint_unavailable_is_not_a_false_positive():
    # When the SAPI endpoint is not exposed by the transport, the read fails
    # gracefully: no withdraw warning, private read still OK, and a sanitised
    # debug note records the classified read error.
    transport = _health_transport(restrictions=None)  # no SAPI route
    cli = _client(_read_env(), transport=transport)
    result = cli.health_check()
    assert result.private_read_ok is True
    assert result.high_risk_permission_warning is False
    assert result.withdraw_permission is None
    assert result.api_restrictions_reported is False
    # The attempt is recorded but never leaks a secret.
    assert "api_restrictions_read" in result.permission_debug
    assert FAKE_SECRET not in json.dumps(result.to_dict())


def test_debug_output_contains_required_fields():
    restr = parse_api_restrictions(RESTRICTIONS_UI_CONFIRMED)
    debug = restr.to_debug_dict()
    for key in (
        "raw_permission_fields_seen",
        "enableWithdrawals",
        "enableInternalTransfer",
        "permitsUniversalTransfer",
        "enableFutures",
        "enableSpotAndMarginTrading",
        "enableReading",
        "ipRestrict",
    ):
        assert key in debug
    # createTime / tradingAuthorityExpirationTime are sensitive -> excluded.
    assert "createTime" not in debug["raw_permission_fields_seen"]
    assert "tradingAuthorityExpirationTime" not in debug["raw_permission_fields_seen"]


def test_health_check_emits_withdraw_warning_only_on_real_restriction():
    # With a withdraw-enabled key, the health check raises the warning and
    # the unified private-read status degrades to WARN (BLOCKER-grade).
    cli = _client(
        _read_env(),
        transport=_health_transport({**RESTRICTIONS_UI_CONFIRMED, "enableWithdrawals": True}),
    )
    report = run_unified_health_check(
        LiveApiConfig.from_env(_read_env()),
        check_binance=True,
        check_telegram=False,
        binance_client=cli,
    )
    assert report.binance is not None
    assert report.binance.high_risk_permission_warning is True
    assert report.binance.withdraw_permission is True
    assert report.binance_private_read_status is HealthStatus.WARN
    assert any("binance_key_has_withdraw_permission" in w for w in report.warnings)
