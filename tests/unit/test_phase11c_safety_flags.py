"""Phase 11C - Safety-flag invariants.

Covers:

  - test_phase11c_safety_flags_remain_false
  - test_no_live_trading_in_phase11c
  - test_no_exchange_live_orders_in_phase11c
  - test_no_llm_trade_decision_in_phase11c
"""

from __future__ import annotations

import pytest

from app.config.settings import get_settings, load_settings
from app.core.errors import SafeModeViolation, SafetyViolation
from app.exchanges.base import WRITE_SURFACE_METHODS
from app.exchanges.binance_public import BinancePublicClient


def _settings():
    get_settings.cache_clear()
    return load_settings()


def test_phase11c_safety_flags_remain_false():
    """The five Phase 1 safety flags + Phase 11C-specific
    ``telegram_outbound_enabled`` must remain False."""
    s = _settings()
    assert s.trading_mode == "paper"
    assert s.live_trading_enabled is False
    assert s.right_tail_enabled is False
    assert s.llm_enabled is False
    assert s.exchange_live_order_enabled is False
    # Telegram outbound is disabled by app/config/defaults.yaml.
    assert s.telegram_outbound_enabled is False
    # Phase 11C-specific safety section asserts EVERY flag remains True
    # (i.e. forbids the corresponding capability).
    safety = s.safety
    for flag in (
        "forbid_private_credentials",
        "forbid_signed_endpoints",
        "forbid_trade_endpoints",
        "forbid_account_endpoints",
        "forbid_position_endpoints",
        "forbid_leverage_endpoints",
        "forbid_margin_endpoints",
        "forbid_live_trading",
        "forbid_right_tail",
        "forbid_llm_trade_decisions",
        "forbid_telegram_outbound",
    ):
        assert getattr(safety, flag) is True, f"safety.{flag} drifted to False"


def test_phase11c_market_data_section_locked_to_public_only():
    s = _settings()
    md = s.market_data
    assert md.provider == "binance_public"
    assert md.read_only is True
    assert md.symbol_limit == 20
    # Schema validators reject every other provider / read_only=False.
    from pydantic import ValidationError

    from app.config.schema import MarketDataConfig

    with pytest.raises(ValidationError):
        MarketDataConfig(provider="binance_private")
    with pytest.raises(ValidationError):
        MarketDataConfig(read_only=False)
    with pytest.raises(ValidationError):
        MarketDataConfig(symbol_limit=0)
    with pytest.raises(ValidationError):
        MarketDataConfig(symbol_limit=999)


def test_phase11c_safety_section_refuses_to_loosen_any_flag():
    """Every ``forbid_*`` flag refuses to be set to False."""
    from pydantic import ValidationError

    from app.config.schema import SafetyConfig

    fields = (
        "forbid_private_credentials",
        "forbid_signed_endpoints",
        "forbid_trade_endpoints",
        "forbid_account_endpoints",
        "forbid_position_endpoints",
        "forbid_leverage_endpoints",
        "forbid_margin_endpoints",
        "forbid_live_trading",
        "forbid_right_tail",
        "forbid_llm_trade_decisions",
        "forbid_telegram_outbound",
    )
    for field in fields:
        with pytest.raises(ValidationError):
            SafetyConfig(**{field: False})


def test_no_live_trading_in_phase11c():
    """The four ExchangeClientBase write surfaces must continue to
    refuse with SafeModeViolation when called on a BinancePublicClient."""
    client = BinancePublicClient(autostart=False)
    for fn_name in WRITE_SURFACE_METHODS:
        fn = getattr(client, fn_name)
        with pytest.raises(SafeModeViolation):
            fn()


def test_no_exchange_live_orders_in_phase11c():
    """``live_orders_enabled`` is False; assert_public_only / assert_read_only
    pass."""
    client = BinancePublicClient(autostart=False)
    assert client.live_orders_enabled is False
    client.assert_public_only()
    client.assert_read_only()


def test_no_llm_trade_decision_in_phase11c():
    """LLM is disabled at boot; the Phase 11C runner does not invoke
    any LLM client. We assert the boot setting + that the chain driver
    does not import a real LLM transport."""
    s = _settings()
    assert s.llm_enabled is False
    # Source-tree check: the Phase 11C event-chain driver does NOT
    # import any real LLM client.
    import inspect

    from app.market_data_public import event_chain as _module

    src = inspect.getsource(_module)
    for forbidden in (
        "DeepSeekClient",
        "openai.",
        "anthropic.",
        "deepseek_client",
        "import openai",
        "import anthropic",
        "import deepseek",
    ):
        assert forbidden not in src, (
            f"event_chain.py must not reference {forbidden}"
        )


def test_no_signed_query_parameter_can_be_smuggled_into_a_request():
    """The ``_request`` plumbing refuses any ``signature`` /
    ``timestamp`` / ``recvWindow`` / ``apiKey`` query parameter even
    when the path is allowlisted."""

    def _fail_transport(_url: str):
        raise AssertionError("transport should not be reached")

    client = BinancePublicClient(transport=_fail_transport, autostart=False)
    with pytest.raises(SafeModeViolation):
        client._request("/fapi/v1/depth", params={"symbol": "BTCUSDT", "signature": "x"})
    with pytest.raises(SafeModeViolation):
        client._request("/fapi/v1/depth", params={"symbol": "BTCUSDT", "timestamp": "1"})
