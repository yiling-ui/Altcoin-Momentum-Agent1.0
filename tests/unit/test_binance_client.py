"""Phase 3 (Issue #3) - BinanceClient skeleton contract.

In Phase 3 the BinanceClient must:

  - exist (so Phase 4 has a stable target to extend)
  - import without pulling in any exchange SDK
  - refuse credentials at construction time
  - raise NotImplementedError on every read-only method
  - inherit SafeModeViolation refusal for all four write surfaces
  - never use an outbound HTTP / WebSocket library in its source

These constraints are the only thing that stops a future PR from
accidentally turning Phase 3 into a live trading entrypoint.
"""

from __future__ import annotations

import inspect

import pytest

from app.core.errors import (
    ExchangeError,
    SafeModeViolation,
    SafetyViolation,
)
from app.exchanges.base import (
    READ_ONLY_METHODS,
    WRITE_SURFACE_METHODS,
    ExchangeClientBase,
)
from app.exchanges.binance import BinanceClient


# ---------------------------------------------------------------------------
# Class-level contract
# ---------------------------------------------------------------------------
def test_binance_client_is_a_subclass_of_base():
    assert issubclass(BinanceClient, ExchangeClientBase)


def test_binance_client_name_is_binance():
    client = BinanceClient()
    assert client.name == "binance"


def test_binance_client_is_not_testnet_by_default():
    client = BinanceClient()
    assert client.is_testnet is False


def test_binance_client_can_be_instantiated_with_testnet_flag():
    client = BinanceClient(testnet=True)
    assert client.is_testnet is True


# ---------------------------------------------------------------------------
# Credential refusal (Spec §37 + Issue #3 anti-leak rule)
# ---------------------------------------------------------------------------
def test_binance_client_refuses_api_key():
    with pytest.raises(ExchangeError):
        BinanceClient(api_key="leaked_key")


def test_binance_client_refuses_api_secret():
    with pytest.raises(ExchangeError):
        BinanceClient(api_secret="leaked_secret")


def test_binance_client_refuses_both_credentials():
    with pytest.raises(ExchangeError):
        BinanceClient(api_key="x", api_secret="y")


# ---------------------------------------------------------------------------
# Read-only methods raise NotImplementedError in Phase 3
# ---------------------------------------------------------------------------
def test_binance_get_symbols_raises_not_implemented():
    client = BinanceClient()
    with pytest.raises(NotImplementedError):
        client.get_symbols()


def test_binance_get_orderbook_raises_not_implemented():
    client = BinanceClient()
    with pytest.raises(NotImplementedError):
        client.get_orderbook("BTCUSDT")


def test_binance_get_recent_trades_raises_not_implemented():
    client = BinanceClient()
    with pytest.raises(NotImplementedError):
        client.get_recent_trades("BTCUSDT")


def test_binance_get_funding_rate_raises_not_implemented():
    client = BinanceClient()
    with pytest.raises(NotImplementedError):
        client.get_funding_rate("BTCUSDT")


def test_binance_get_open_interest_raises_not_implemented():
    client = BinanceClient()
    with pytest.raises(NotImplementedError):
        client.get_open_interest("BTCUSDT")


def test_binance_get_account_snapshot_raises_not_implemented():
    client = BinanceClient()
    with pytest.raises(NotImplementedError):
        client.get_account_snapshot()


def test_binance_implements_every_abstract_read_method():
    """BinanceClient is concrete (instantiable) only because it
    overrides every abstract read-only method - even if those overrides
    raise NotImplementedError."""
    BinanceClient()  # must not raise TypeError("can't instantiate ...")
    for name in READ_ONLY_METHODS:
        # Method exists and is defined on BinanceClient itself.
        assert getattr(BinanceClient, name).__qualname__.startswith(
            "BinanceClient."
        ), f"{name} is not overridden on BinanceClient"


# ---------------------------------------------------------------------------
# Write surfaces refuse with SafeModeViolation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fn_name", WRITE_SURFACE_METHODS)
def test_binance_write_surfaces_refuse(fn_name):
    client = BinanceClient()
    fn = getattr(client, fn_name)
    with pytest.raises(SafeModeViolation):
        fn()


def test_binance_write_surfaces_inherit_base_refusal():
    """Phase 3 contract: BinanceClient may not override the write
    surfaces - it must inherit the base-class refusal."""
    for name in WRITE_SURFACE_METHODS:
        assert getattr(BinanceClient, name).__qualname__.startswith(
            "ExchangeClientBase."
        ), f"BinanceClient.{name} must NOT override the base-class refusal"


# ---------------------------------------------------------------------------
# Source must not import any network library or exchange SDK
# ---------------------------------------------------------------------------
def test_binance_module_does_not_import_network_libraries():
    import app.exchanges.binance as binance_mod

    src = inspect.getsource(binance_mod)
    forbidden = (
        "aiohttp",
        "websockets",
        "websocket",
        "requests",
        "httpx",
        "ccxt",
        "binance_connector",
    )
    for line in src.splitlines():
        stripped = line.strip()
        for token in forbidden:
            assert not stripped.startswith(f"import {token}"), (
                f"app.exchanges.binance imports {token}"
            )
            assert not stripped.startswith(f"from {token}"), (
                f"app.exchanges.binance imports from {token}"
            )


def test_safe_mode_violation_inherits_safety_violation():
    """Defence in depth: any code path that catches SafetyViolation
    must continue to catch the Phase 3 SafeModeViolation narrowing."""
    assert issubclass(SafeModeViolation, SafetyViolation)
