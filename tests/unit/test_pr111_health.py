"""PR111 - unified health check + CLI + audit-event persistence tests."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from app.core.events import Event, EventType
from app.live.api_config import LiveApiConfig, LiveRuntimeMode
from app.live.binance_client import BinanceLiveClient
from app.live.health import build_safety_flags, run_unified_health_check
from app.live.status import TRADE_API_BLOCKED_BY_PR111

import scripts.live_api_health_check as cli_mod

FAKE_KEY = "FAKEKEY" + "0" * 57
FAKE_SECRET = "FAKESECRET" + "0" * 54

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
        }
    ],
}

SAMPLE_ACCOUNT = {
    "totalWalletBalance": "1000.5",
    "totalUnrealizedProfit": "0",
    "totalMarginBalance": "1000.5",
    "availableBalance": "1000.5",
    "feeTier": 0,
    "canTrade": True,
    "canDeposit": False,
    "canWithdraw": False,
    "assets": [{"asset": "USDT", "walletBalance": "1000.5", "availableBalance": "1000.5", "crossUnPnl": "0"}],
    "positions": [],
}

ORDER_PATHS = {
    "/fapi/v1/order",
    "/fapi/v1/batchOrders",
    "/fapi/v1/leverage",
    "/fapi/v1/marginType",
    "/fapi/v1/positionMargin",
}


class FakeEventRepo:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, event: Event) -> None:
        self.events.append(event)

    def types(self):
        return [e.event_type for e in self.events]


class RecordingBinanceTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.responses = {
            "/fapi/v1/ping": {},
            "/fapi/v1/time": {"serverTime": 1700000000000},
            "/fapi/v1/exchangeInfo": SAMPLE_EXCHANGE_INFO,
            "/fapi/v2/account": SAMPLE_ACCOUNT,
            "/fapi/v1/income": [],
        }

    def __call__(self, method, url, headers):
        path = urlsplit(url).path
        self.calls.append(path)
        return self.responses.get(path, {})


def _binance_client(transport, repo=None):
    cfg = LiveApiConfig.from_env({
        "AMA_BINANCE_API_KEY": FAKE_KEY,
        "AMA_BINANCE_API_SECRET": FAKE_SECRET,
        "AMA_BINANCE_ENABLE_PRIVATE_READ": "true",
    })
    return BinanceLiveClient(
        cfg.binance,
        runtime_mode=LiveRuntimeMode.LIVE_SHADOW,
        transport=transport,
        event_repo=repo,
        clock=lambda: 1700000000000,
    )


# ---- Test 23: health report includes Binance/Telegram/DeepSeek sections ---
def test_unified_report_has_all_three_sections():
    cfg = LiveApiConfig.from_env({
        "AMA_BINANCE_API_KEY": FAKE_KEY,
        "AMA_BINANCE_API_SECRET": FAKE_SECRET,
        "AMA_BINANCE_ENABLE_PRIVATE_READ": "true",
        # deepseek disabled -> safe even with call_deepseek True (no network)
    })
    transport = RecordingBinanceTransport()
    cli = _binance_client(transport)
    report = run_unified_health_check(
        cfg,
        check_binance=True,
        check_telegram=True,
        check_deepseek=True,
        call_deepseek=True,  # safe: deepseek disabled -> no network
        binance_client=cli,
    )
    d = report.to_dict()
    assert d["binance"] is not None
    assert d["telegram"] is not None
    assert d["deepseek"] is not None
    assert d["binance_private_trade_status"] == TRADE_API_BLOCKED_BY_PR111
    # JSON serialisable end-to-end.
    blob = json.dumps(d)
    assert FAKE_KEY not in blob
    assert FAKE_SECRET not in blob


# ---- Test 24: health check does not place orders --------------------------
def test_health_check_places_no_orders():
    transport = RecordingBinanceTransport()
    cli = _binance_client(transport)
    cfg = LiveApiConfig.from_env({
        "AMA_BINANCE_API_KEY": FAKE_KEY,
        "AMA_BINANCE_API_SECRET": FAKE_SECRET,
        "AMA_BINANCE_ENABLE_PRIVATE_READ": "true",
    })
    run_unified_health_check(cfg, check_binance=True, check_telegram=False, binance_client=cli)
    # No order / leverage / margin endpoint was ever called.
    assert not (set(transport.calls) & ORDER_PATHS)


# ---- Test 25: safety flags remain locked ----------------------------------
def test_safety_flags_locked():
    cfg = LiveApiConfig.from_env({})
    flags = build_safety_flags(cfg)
    assert flags["phase_12_forbidden"] is True
    assert flags["exchange_live_orders"] is False
    assert flags["live_trading"] is False
    assert flags["ai_trade_authority"] is False
    assert flags["trade_authority"] is False
    assert flags["right_tail"] is False
    assert flags["secrets_masked"] is True

    report = run_unified_health_check(cfg, check_binance=False, check_telegram=True)
    d = report.to_dict()
    assert d["exchange_live_orders"] is False
    assert d["ai_trade_authority"] is False
    assert d["secrets_masked"] is True
    assert d["live_runtime_mode"] == "LIVE_SHADOW"
    assert d["safety_flags"]["phase_12_forbidden"] is True


def test_unified_health_emits_start_and_complete_events():
    repo = FakeEventRepo()
    cfg = LiveApiConfig.from_env({})
    run_unified_health_check(cfg, check_binance=False, check_telegram=True, event_repo=repo)
    assert EventType.API_HEALTH_CHECK_STARTED in repo.types()
    assert EventType.API_HEALTH_CHECK_COMPLETED in repo.types()


# ---- CLI smoke (no network: telegram-only with outbound off) --------------
def test_cli_json_telegram_only(capsys):
    # --telegram only -> no Binance/DeepSeek network. Empty env -> no token,
    # outbound off -> no Telegram network either.
    rc = cli_mod.main(["--telegram", "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "telegram" in payload
    assert payload["binance"] is None  # not checked
    assert payload["exchange_live_orders"] is False
    assert payload["ai_trade_authority"] is False
    assert payload["secrets_masked"] is True
    # Exit code reflects status (WARN=1 due to missing token).
    assert rc in (0, 1)


def test_cli_text_render(capsys):
    rc = cli_mod.main(["--telegram"])
    out = capsys.readouterr().out
    assert "Live API Health Check" in out
    assert "ai_trade_authority" in out
    assert "exchange_live_orders" in out
    assert rc in (0, 1)


# ---- audit events persist in the real EventRepository ---------------------
def test_pr111_event_types_persist_in_repository(events_repo):
    """The real EventRepository accepts the new PR111 event types."""
    events_repo.append(
        Event(
            event_type=EventType.BINANCE_PRIVATE_TRADE_BLOCKED,
            source_module="binance_live",
            payload={"reason": TRADE_API_BLOCKED_BY_PR111},
        )
    )
    events_repo.append(
        Event(
            event_type=EventType.API_HEALTH_CHECK_COMPLETED,
            source_module="live_api_health",
            payload={"overall_status": "PASS"},
        )
    )
    rows = events_repo.list_events(event_type=EventType.BINANCE_PRIVATE_TRADE_BLOCKED)
    assert len(rows) == 1
