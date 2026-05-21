"""Phase 11C - BinancePublicClient unit tests.

Covers:

  - test_binance_public_client_requires_no_credentials
  - test_binance_public_client_rejects_private_credentials
  - test_public_endpoint_allowlist_allows_market_data
  - test_public_endpoint_allowlist_rejects_order_endpoint
  - test_public_market_snapshot_serialization
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.core.errors import SafeModeViolation
from app.core.models import MarketSnapshot
from app.exchanges.binance_public import (
    BinancePublicClient,
    DEFAULT_REST_BASE_URL,
    FORBIDDEN_PRIVATE_ENDPOINTS,
    PUBLIC_MARKET_ENDPOINT_ALLOWLIST,
    assert_public_endpoint_allowed,
)


def _make_transport(routes: dict[str, Any]):
    """Tiny transport that returns the fixture body keyed by URL path."""

    def _fetch(url: str) -> Any:
        from urllib.parse import urlsplit

        path = urlsplit(url).path
        if path not in routes:
            raise AssertionError(f"transport got unexpected path {path}")
        return routes[path]

    return _fetch


# ---------------------------------------------------------------------------
# Construction / credentials
# ---------------------------------------------------------------------------
def test_binance_public_client_requires_no_credentials():
    """A vanilla constructor call must succeed and produce a public,
    read-only client. No api_key, no api_secret, no env-var read."""
    client = BinancePublicClient(
        transport=_make_transport({}),
        autostart=False,
    )
    try:
        assert client.name == "binance_public"
        assert client.live_orders_enabled is False
        # The four ExchangeClientBase write surfaces must still refuse.
        for fn_name in (
            "create_order",
            "cancel_order",
            "set_leverage",
            "set_margin_mode",
        ):
            with pytest.raises(SafeModeViolation):
                getattr(client, fn_name)()
        # Public-only invariant.
        client.assert_public_only()
    finally:
        # Don't actually call stop() because the client wasn't started.
        pass


def test_binance_public_client_rejects_private_credentials():
    """Passing api_key / api_secret must raise SafeModeViolation."""
    with pytest.raises(SafeModeViolation):
        BinancePublicClient(api_key="anything", autostart=False)
    with pytest.raises(SafeModeViolation):
        BinancePublicClient(api_secret="anything", autostart=False)
    with pytest.raises(SafeModeViolation):
        BinancePublicClient(api_key="x", api_secret="y", autostart=False)


def test_binance_public_client_rejects_credential_shaped_kwargs():
    """Any **kwargs whose name looks like a credential is refused."""
    for kw in (
        "binance_api_key",
        "BINANCE_API_KEY",
        "auth_token",
        "bearer_token",
        "passphrase",
        "signature",
        "secret",
    ):
        with pytest.raises(SafeModeViolation):
            BinancePublicClient(autostart=False, **{kw: "anything"})


# ---------------------------------------------------------------------------
# Endpoint allowlist
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", sorted(PUBLIC_MARKET_ENDPOINT_ALLOWLIST))
def test_public_endpoint_allowlist_allows_market_data(path: str):
    """Every public market endpoint the runner needs is allowed."""
    canonical = assert_public_endpoint_allowed(path)
    assert canonical == path
    # Bare path with a benign query parameter is also accepted.
    canonical_qs = assert_public_endpoint_allowed(f"{path}?symbol=BTCUSDT&limit=5")
    assert canonical_qs == path
    # Fully-qualified URL on the allowed host is also accepted.
    canonical_full = assert_public_endpoint_allowed(
        f"{DEFAULT_REST_BASE_URL}{path}?symbol=BTCUSDT"
    )
    assert canonical_full == path


@pytest.mark.parametrize(
    "path",
    sorted(FORBIDDEN_PRIVATE_ENDPOINTS),
)
def test_public_endpoint_allowlist_rejects_order_endpoint(path: str):
    """Every order / account / position / leverage / margin endpoint
    is refused with SafeModeViolation."""
    with pytest.raises(SafeModeViolation):
        assert_public_endpoint_allowed(path)
    with pytest.raises(SafeModeViolation):
        assert_public_endpoint_allowed(
            f"{DEFAULT_REST_BASE_URL}{path}?symbol=BTCUSDT"
        )


def test_public_endpoint_allowlist_rejects_unknown_path():
    """A path that is neither private-private nor in the allowlist
    is refused defensively."""
    with pytest.raises(SafeModeViolation):
        assert_public_endpoint_allowed("/fapi/v1/something_new")
    with pytest.raises(SafeModeViolation):
        assert_public_endpoint_allowed("/api/v3/order")  # spot trade endpoint


def test_public_endpoint_allowlist_rejects_signed_query_parameters():
    """A URL whose query carries a signed-request parameter is refused
    even when the path is in the allowlist."""
    for forbidden in ("signature", "timestamp", "recvWindow", "apiKey"):
        with pytest.raises(SafeModeViolation):
            assert_public_endpoint_allowed(
                f"/fapi/v1/depth?symbol=BTCUSDT&{forbidden}=anything"
            )


def test_public_endpoint_allowlist_rejects_non_https_scheme():
    with pytest.raises(SafeModeViolation):
        assert_public_endpoint_allowed("http://fapi.binance.com/fapi/v1/depth")


def test_public_endpoint_allowlist_rejects_unknown_host():
    with pytest.raises(SafeModeViolation):
        assert_public_endpoint_allowed("https://example.com/fapi/v1/depth")


# ---------------------------------------------------------------------------
# Read-only API behaviour
# ---------------------------------------------------------------------------
def test_get_account_snapshot_is_forbidden_in_phase_11c():
    """Account / position data lives behind authenticated endpoints
    that Phase 11C must never call."""
    client = BinancePublicClient(transport=_make_transport({}), autostart=False)
    with pytest.raises(SafeModeViolation):
        client.get_account_snapshot()


def test_get_symbols_filters_to_usdt_perpetual():
    transport = _make_transport(
        {
            "/fapi/v1/exchangeInfo": {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "contractType": "PERPETUAL",
                        "status": "TRADING",
                        "filters": [
                            {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                            {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                            {"filterType": "MIN_NOTIONAL", "notional": "5"},
                        ],
                    },
                    {
                        "symbol": "BTCBUSD",
                        "baseAsset": "BTC",
                        "quoteAsset": "BUSD",
                        "contractType": "PERPETUAL",
                        "status": "TRADING",
                        "filters": [],
                    },
                    {
                        "symbol": "BTCUSDT_240329",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "contractType": "CURRENT_QUARTER",
                        "status": "TRADING",
                        "filters": [],
                    },
                ]
            }
        }
    )
    client = BinancePublicClient(transport=transport)
    try:
        symbols = client.get_symbols()
    finally:
        client.stop()
    assert [s.symbol for s in symbols] == ["BTCUSDT"]
    assert symbols[0].quote_asset == "USDT"
    assert symbols[0].contract_type == "PERPETUAL"
    assert symbols[0].price_tick == 0.10
    assert symbols[0].qty_step == 0.001
    assert symbols[0].min_notional == 5.0


def test_get_top_usdt_perpetual_symbols_sorts_and_clamps():
    transport = _make_transport(
        {
            "/fapi/v1/ticker/24hr": [
                {"symbol": "AAAUSDT", "quoteVolume": "100"},
                {"symbol": "BBBUSDT", "quoteVolume": "300"},
                {"symbol": "CCCUSDT", "quoteVolume": "200"},
                {"symbol": "DOGEBUSD", "quoteVolume": "999"},  # excluded
            ]
        }
    )
    client = BinancePublicClient(transport=transport)
    try:
        ranked = client.get_top_usdt_perpetual_symbols(limit=2)
    finally:
        client.stop()
    assert ranked == ["BBBUSDT", "CCCUSDT"]


def test_get_orderbook_returns_typed_levels():
    transport = _make_transport(
        {
            "/fapi/v1/depth": {
                "E": 1700000000000,
                "T": 1700000000000,
                "bids": [["100.0", "1.0"], ["99.9", "2.0"]],
                "asks": [["100.1", "1.0"], ["100.2", "2.0"]],
            }
        }
    )
    client = BinancePublicClient(transport=transport)
    try:
        book = client.get_orderbook("BTCUSDT", depth=2)
    finally:
        client.stop()
    assert book.symbol == "BTCUSDT"
    assert book.best_bid == 100.0
    assert book.best_ask == 100.1
    assert len(book.bids) == 2
    assert len(book.asks) == 2


def test_get_recent_trades_maps_buyer_maker_flag_correctly():
    transport = _make_transport(
        {
            "/fapi/v1/aggTrades": [
                {"a": "1", "p": "100.0", "q": "0.5", "T": 1700000000000, "m": False},
                {"a": "2", "p": "100.1", "q": "0.3", "T": 1700000000010, "m": True},
            ]
        }
    )
    client = BinancePublicClient(transport=transport)
    try:
        trades = client.get_recent_trades("BTCUSDT", limit=10)
    finally:
        client.stop()
    assert len(trades) == 2
    # m=False -> aggressor was BUYER -> side=BUY, is_buyer_maker=False
    assert trades[0].side.value == "buy"
    assert trades[0].is_buyer_maker is False
    # m=True -> aggressor was SELLER -> side=SELL, is_buyer_maker=True
    assert trades[1].side.value == "sell"
    assert trades[1].is_buyer_maker is True


def test_get_funding_rate_falls_back_to_premium_index_on_empty():
    transport = _make_transport(
        {
            "/fapi/v1/fundingRate": [],  # empty
            "/fapi/v1/premiumIndex": {
                "symbol": "BTCUSDT",
                "lastFundingRate": "0.00012",
                "nextFundingTime": 1700000000000,
                "time": 1699999000000,
            },
        }
    )
    client = BinancePublicClient(transport=transport)
    try:
        rate = client.get_funding_rate("BTCUSDT")
    finally:
        client.stop()
    assert rate.symbol == "BTCUSDT"
    assert rate.rate == pytest.approx(0.00012)


def test_get_mark_price_returns_envelope():
    transport = _make_transport(
        {
            "/fapi/v1/premiumIndex": {
                "symbol": "BTCUSDT",
                "markPrice": "50000.5",
                "indexPrice": "50001.0",
                "lastFundingRate": "0.0001",
                "nextFundingTime": 1700000000000,
                "time": 1699999000000,
            }
        }
    )
    client = BinancePublicClient(transport=transport)
    try:
        mark = client.get_mark_price("BTCUSDT")
    finally:
        client.stop()
    assert mark.symbol == "BTCUSDT"
    assert mark.mark_price == pytest.approx(50000.5)
    assert mark.index_price == pytest.approx(50001.0)


def test_endpoint_call_counts_track_successful_calls():
    transport = _make_transport(
        {
            "/fapi/v1/exchangeInfo": {"symbols": []},
            "/fapi/v1/openInterest": {"time": 0, "openInterest": "0"},
        }
    )
    client = BinancePublicClient(transport=transport)
    try:
        client.get_symbols()
        client.get_open_interest("BTCUSDT")
        client.get_open_interest("BTCUSDT")
    finally:
        client.stop()
    counts = client.endpoint_call_counts
    assert counts["/fapi/v1/exchangeInfo"] == 1
    assert counts["/fapi/v1/openInterest"] == 2
    assert client.total_calls == 3


# ---------------------------------------------------------------------------
# MarketSnapshot serialization (Phase 11C)
# ---------------------------------------------------------------------------
def test_public_market_snapshot_serialization():
    """A MarketSnapshot built from public-market data round-trips
    through JSON cleanly and includes mark_price."""
    snap = MarketSnapshot(
        symbol="BTCUSDT",
        timestamp=1700000000000,
        last_price=50000.0,
        mark_price=50001.0,
        bid=49999.5,
        ask=50000.5,
        spread_pct=0.0001,
        volume_1m=10.0,
        volume_5m=50.0,
        oi=12345.0,
        funding_rate=0.0001,
        cvd_1m=2.0,
        cvd_5m=8.0,
        atr_1m=1.5,
        atr_5m=4.0,
        orderbook_depth_usdt=100000.0,
    )
    payload = snap.model_dump()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)
    assert decoded["symbol"] == "BTCUSDT"
    assert decoded["mark_price"] == 50001.0
    assert decoded["spread_pct"] == 0.0001
    # The Phase 11C contract carries every Phase 1 §11.1 field.
    for key in (
        "last_price",
        "bid",
        "ask",
        "spread_pct",
        "volume_1m",
        "volume_5m",
        "oi",
        "funding_rate",
        "cvd_1m",
        "cvd_5m",
        "atr_1m",
        "atr_5m",
        "orderbook_depth_usdt",
    ):
        assert key in decoded
