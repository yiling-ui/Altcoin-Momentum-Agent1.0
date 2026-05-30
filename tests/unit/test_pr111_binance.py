"""PR111 - Binance live client tests (fake transport only, no network)."""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from app.core.errors import LiveTradeNotEnabled
from app.core.events import Event, EventType
from app.live.api_config import LiveApiConfig, LiveRuntimeMode
from app.live.binance_client import BinanceLiveClient
from app.live.binance_income import (
    AttributionStatus,
    classify_income_rows,
    summarise_income_events,
)
from app.live.binance_models import parse_account, parse_exchange_info
from app.live.binance_permissions import inspect_permissions
from app.live.capital_event import CapitalEventType
from app.live.status import TRADE_API_BLOCKED_BY_PR111

FAKE_KEY = "FAKEKEY0000000000000000000000000000000000000000000000000000000000"
FAKE_SECRET = "FAKESECRET00000000000000000000000000000000000000000000000000000"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
class FakeEventRepo:
    """List-based event sink (no DB)."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, event: Event) -> None:
        self.events.append(event)

    def types(self) -> list[EventType]:
        return [e.event_type for e in self.events]


class FakeBinanceTransport:
    """Routes by URL path. Records every call. Never opens a socket."""

    def __init__(self, responses: dict, *, fail_if_called: bool = False) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str]] = []
        self.fail_if_called = fail_if_called

    def __call__(self, method: str, url: str, headers):
        if self.fail_if_called:
            raise AssertionError(f"transport must NOT be called: {method} {url}")
        path = urlsplit(url).path
        self.calls.append((method, path))
        if path not in self.responses:
            raise AssertionError(f"unexpected path: {path}")
        value = self.responses[path]
        return value(url) if callable(value) else value


SAMPLE_EXCHANGE_INFO = {
    "serverTime": 1700000000000,
    "symbols": [
        {
            "symbol": "BTCUSDT",
            "status": "TRADING",
            "contractType": "PERPETUAL",
            "baseAsset": "BTC",
            "quoteAsset": "USDT",
            "pricePrecision": 2,
            "quantityPrecision": 3,
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "1000"},
                {"filterType": "MIN_NOTIONAL", "notional": "100"},
            ],
        },
        {
            "symbol": "HALTUSDT",
            "status": "BREAK",
            "contractType": "PERPETUAL",
            "baseAsset": "HALT",
            "quoteAsset": "USDT",
            "pricePrecision": 4,
            "quantityPrecision": 0,
            "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.0001"},
                {"filterType": "LOT_SIZE", "stepSize": "1", "minQty": "1", "maxQty": "100000"},
                {"filterType": "MIN_NOTIONAL", "notional": "5"},
            ],
        },
    ],
}

SAMPLE_ACCOUNT = {
    "totalWalletBalance": "1000.5",
    "totalUnrealizedProfit": "12.25",
    "totalMarginBalance": "1012.75",
    "availableBalance": "950.0",
    "feeTier": 1,
    "canTrade": True,
    "canDeposit": True,
    "canWithdraw": False,
    "assets": [
        {"asset": "USDT", "walletBalance": "1000.5", "availableBalance": "950.0", "crossUnPnl": "12.25"},
    ],
    "positions": [
        {"symbol": "BTCUSDT", "positionAmt": "0.010", "entryPrice": "60000",
         "unrealizedProfit": "12.25", "leverage": "5", "marginType": "isolated", "positionSide": "BOTH"},
        {"symbol": "ETHUSDT", "positionAmt": "0", "entryPrice": "0",
         "unrealizedProfit": "0", "leverage": "10", "marginType": "isolated", "positionSide": "BOTH"},
    ],
}

SAMPLE_INCOME = [
    {"symbol": "BTCUSDT", "incomeType": "REALIZED_PNL", "income": "25.5", "asset": "USDT", "time": 1700000000000, "tradeId": "t1", "tranId": "1"},
    {"symbol": "BTCUSDT", "incomeType": "REALIZED_PNL", "income": "-10.0", "asset": "USDT", "time": 1700000001000, "tradeId": "t2", "tranId": "2"},
    {"symbol": "BTCUSDT", "incomeType": "COMMISSION", "income": "-0.5", "asset": "USDT", "time": 1700000002000, "tradeId": "t1", "tranId": "3"},
    {"symbol": "BTCUSDT", "incomeType": "FUNDING_FEE", "income": "-1.2", "asset": "USDT", "time": 1700000003000, "tranId": "4"},
    {"symbol": "BTCUSDT", "incomeType": "FUNDING_FEE", "income": "0.8", "asset": "USDT", "time": 1700000004000, "tranId": "5"},
    {"symbol": "", "incomeType": "TRANSFER", "income": "500", "asset": "USDT", "time": 1700000005000, "tranId": "6"},
    {"symbol": "", "incomeType": "SOME_FUTURE_TYPE", "income": "3.3", "asset": "USDT", "time": 1700000006000, "tranId": "7"},
]


def _client(env: dict, *, transport, runtime_mode=LiveRuntimeMode.LIVE_SHADOW, event_repo=None):
    cfg = LiveApiConfig.from_env(env)
    return BinanceLiveClient(
        cfg.binance,
        runtime_mode=runtime_mode,
        transport=transport,
        event_repo=event_repo,
        clock=lambda: 1700000000000,
    )


def _read_env():
    return {
        "AMA_BINANCE_API_KEY": FAKE_KEY,
        "AMA_BINANCE_API_SECRET": FAKE_SECRET,
        "AMA_BINANCE_ENABLE_PRIVATE_READ": "true",
    }


# ---- Test 4: exchangeInfo parser extracts filters -------------------------
def test_exchange_info_parser_extracts_filters():
    snap = parse_exchange_info(SAMPLE_EXCHANGE_INFO)
    assert snap.symbol_count == 2
    btc = snap.get("BTCUSDT")
    assert btc is not None
    assert btc.tick_size == 0.10
    assert btc.step_size == 0.001
    assert btc.min_qty == 0.001
    assert btc.min_notional == 100.0
    assert btc.price_precision == 2
    assert btc.quantity_precision == 3
    assert btc.is_tradable is True
    assert snap.get("HALTUSDT").is_tradable is False


# ---- Test 5: quantity / price normalization works -------------------------
def test_quantity_and_price_normalization():
    transport = FakeBinanceTransport({"/fapi/v1/exchangeInfo": SAMPLE_EXCHANGE_INFO})
    cli = _client({}, transport=transport)
    cli.get_exchange_info()
    # step_size=0.001 -> floor to 3 decimals.
    assert cli.normalize_order_quantity("BTCUSDT", 0.0129) == pytest.approx(0.012)
    # tick_size=0.10 -> round to nearest tick.
    assert cli.normalize_order_price("BTCUSDT", 60000.07) == pytest.approx(60000.10)
    # Unknown symbol -> returns raw.
    assert cli.normalize_order_quantity("NOPEUSDT", 1.2345) == pytest.approx(1.2345)


# ---- Test 6: min notional validation works --------------------------------
def test_min_notional_validation():
    transport = FakeBinanceTransport({"/fapi/v1/exchangeInfo": SAMPLE_EXCHANGE_INFO})
    cli = _client({}, transport=transport)
    cli.get_exchange_info()
    # 60000 * 0.001 = 60 < 100 -> fails.
    assert cli.validate_min_notional("BTCUSDT", 60000, 0.001) is False
    # 60000 * 0.01 = 600 >= 100 -> passes.
    assert cli.validate_min_notional("BTCUSDT", 60000, 0.01) is True
    assert cli.validate_symbol_tradable("BTCUSDT") is True
    assert cli.validate_symbol_tradable("HALTUSDT") is False
    assert cli.validate_symbol_tradable("NOPEUSDT") is False


# ---- Test 7: account snapshot parser works --------------------------------
def test_account_snapshot_parser():
    snap = parse_account(SAMPLE_ACCOUNT, timestamp_ms=123)
    assert snap.total_wallet_balance == 1000.5
    assert snap.available_balance == 950.0
    assert snap.can_trade is True
    assert snap.can_withdraw is False
    assert len(snap.balances) == 1
    assert snap.open_position_count == 1  # only BTCUSDT is open


def test_account_read_via_client_emits_event():
    repo = FakeEventRepo()
    transport = FakeBinanceTransport({"/fapi/v2/account": SAMPLE_ACCOUNT})
    cli = _client(_read_env(), transport=transport, event_repo=repo)
    snap = cli.get_account()
    assert snap.total_wallet_balance == 1000.5
    assert EventType.BINANCE_ACCOUNT_SNAPSHOT_READ in repo.types()


# ---- Test 8/9/10/11: income classification --------------------------------
def test_income_classification_realized_commission_funding_unknown():
    events = classify_income_rows(SAMPLE_INCOME)

    def types_present(et):
        return any(
            e.capital_event is not None and e.capital_event.event_type == et
            for e in events
        )

    # REALIZED_PNL (+) and REALIZED_LOSS (-).
    assert types_present(CapitalEventType.REALIZED_PNL)
    assert types_present(CapitalEventType.REALIZED_LOSS)
    # COMMISSION -> FEE.
    assert types_present(CapitalEventType.FEE)
    # FUNDING_FEE (-) and FUNDING_INCOME (+).
    assert types_present(CapitalEventType.FUNDING_FEE)
    assert types_present(CapitalEventType.FUNDING_INCOME)
    # Unknown income type preserved safely (never mapped to a capital event).
    unknown = [e for e in events if e.is_unmapped]
    assert len(unknown) == 1
    assert unknown[0].raw_income_type == "SOME_FUTURE_TYPE"
    assert unknown[0].info_tag == "UNKNOWN_INCOME_TYPE"
    assert unknown[0].capital_event is None


def test_realized_pnl_preserves_trade_id_attribution():
    events = classify_income_rows(SAMPLE_INCOME)
    realized = [
        e
        for e in events
        if e.capital_event is not None
        and e.capital_event.event_type
        in (CapitalEventType.REALIZED_PNL, CapitalEventType.REALIZED_LOSS)
    ]
    assert all(e.trade_id is not None for e in realized)
    assert all(e.attribution_status == AttributionStatus.ATTRIBUTED for e in realized)


# ---- Test 12/13: funding -> CapitalEvent, no deposit/withdraw pollution ----
def test_funding_and_commission_accounting_separated():
    events = classify_income_rows(SAMPLE_INCOME)
    summary = summarise_income_events(events)
    # gross realized = 25.5 - 10.0 = 15.5
    assert summary.gross_realized_pnl == pytest.approx(15.5)
    # funding = -1.2 + 0.8 = -0.4 (NOT mixed into realized).
    assert summary.funding_total == pytest.approx(-0.4)
    # commission stored as positive magnitude = 0.5
    assert summary.commission_total == pytest.approx(0.5)
    # the +500 TRANSFER is an internal transfer, NOT polluted by funding
    # and NOT counted as an external deposit / strategy PnL.
    assert summary.internal_transfer_total == pytest.approx(500.0)
    assert summary.external_deposit_total == pytest.approx(0.0)
    # net_strategy_pnl = 15.5 - 0.5 + (-0.4) = 14.6
    assert summary.net_strategy_pnl == pytest.approx(14.6)
    # funding without trade_id is account-level pending.
    assert summary.unattributed_funding_count == 2
    # the unknown row is tallied separately, never in the ledger.
    assert summary.unknown_count == 1


def test_income_history_via_client_emits_funding_and_commission_events():
    repo = FakeEventRepo()
    transport = FakeBinanceTransport({"/fapi/v1/income": SAMPLE_INCOME})
    cli = _client(_read_env(), transport=transport, event_repo=repo)
    events = cli.get_income_history(limit=50)
    assert len(events) == len(SAMPLE_INCOME)
    assert EventType.BINANCE_INCOME_HISTORY_READ in repo.types()
    assert EventType.FUNDING_EVENT_DETECTED in repo.types()
    assert EventType.COMMISSION_EVENT_DETECTED in repo.types()


# ---- Test 14: private trade blocked by default, no HTTP order sent ---------
def test_private_trade_blocked_no_http_request():
    # Transport raises if called at all.
    transport = FakeBinanceTransport({}, fail_if_called=True)
    repo = FakeEventRepo()
    cli = _client(_read_env(), transport=transport, event_repo=repo)
    for surface in (cli.create_order, cli.cancel_order, cli.set_leverage, cli.set_margin_mode):
        with pytest.raises(LiveTradeNotEnabled):
            surface(symbol="BTCUSDT", side="BUY", qty=0.01)
    # No HTTP call happened.
    assert transport.calls == []
    # Block events were emitted.
    assert EventType.BINANCE_PRIVATE_TRADE_BLOCKED in repo.types()
    # Non-raising contract returns the sentinel.
    assert cli.trade_blocked_reason() == TRADE_API_BLOCKED_BY_PR111


# ---- Test 15: LIVE_SHADOW blocks trade even with trade key ----------------
def test_live_shadow_blocks_trade_even_with_trade_key():
    env = _read_env()
    env["AMA_BINANCE_ENABLE_PRIVATE_TRADE"] = "true"
    transport = FakeBinanceTransport({}, fail_if_called=True)
    cli = _client(env, transport=transport, runtime_mode=LiveRuntimeMode.LIVE_SHADOW)
    with pytest.raises(LiveTradeNotEnabled):
        cli.create_order(symbol="BTCUSDT", side="BUY", qty=0.01)
    assert transport.calls == []
    # Even a (forbidden) LIVE_LIMITED runtime mode is still blocked in PR111.
    cli2 = _client(env, transport=transport, runtime_mode=LiveRuntimeMode.LIVE_LIMITED)
    with pytest.raises(LiveTradeNotEnabled):
        cli2.create_order(symbol="BTCUSDT", side="BUY", qty=0.01)
    assert transport.calls == []


# ---- permission inspection: high-risk withdraw warning --------------------
def test_permission_high_risk_warning_on_withdraw():
    acct = parse_account({**SAMPLE_ACCOUNT, "canWithdraw": True})
    perms = inspect_permissions(acct)
    assert perms.high_risk_permission_warning is True
    assert any("withdraw" in w for w in perms.warnings)
    # Read-only key (no withdraw) -> no high-risk warning.
    acct2 = parse_account({**SAMPLE_ACCOUNT, "canWithdraw": False, "canDeposit": False})
    perms2 = inspect_permissions(acct2)
    assert perms2.high_risk_permission_warning is False


# ---- public + private read health check (fake transport) ------------------
def test_binance_health_check_public_and_private_read():
    transport = FakeBinanceTransport(
        {
            "/fapi/v1/ping": {},
            "/fapi/v1/time": {"serverTime": 1700000000000},
            "/fapi/v1/exchangeInfo": SAMPLE_EXCHANGE_INFO,
            "/fapi/v2/account": SAMPLE_ACCOUNT,
            "/fapi/v1/income": SAMPLE_INCOME,
        }
    )
    repo = FakeEventRepo()
    cli = _client(_read_env(), transport=transport, event_repo=repo)
    result = cli.health_check()
    assert result.public_market_ok is True
    assert result.private_read_ok is True
    assert result.can_read_account is True
    assert result.can_read_positions is True
    assert result.can_read_income is True
    assert result.private_trade_blocked_by_mode is True
    assert result.masked_api_key != FAKE_KEY  # masked, not raw
    d = result.to_dict()
    assert FAKE_KEY not in str(d)
    assert EventType.BINANCE_PUBLIC_HEALTH_OK in repo.types()
    assert EventType.BINANCE_PRIVATE_READ_OK in repo.types()


def test_binance_health_check_missing_secret_does_not_crash():
    # enable_private_read but no creds -> WARN, no crash, public still runs.
    transport = FakeBinanceTransport(
        {
            "/fapi/v1/ping": {},
            "/fapi/v1/time": {"serverTime": 1},
            "/fapi/v1/exchangeInfo": SAMPLE_EXCHANGE_INFO,
        }
    )
    cli = _client({"AMA_BINANCE_ENABLE_PRIVATE_READ": "true"}, transport=transport)
    result = cli.health_check()
    assert result.public_market_ok is True
    assert result.private_read_ok is False
    assert any("MISSING_SECRET" in w for w in result.warnings)
