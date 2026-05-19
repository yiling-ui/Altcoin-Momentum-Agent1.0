"""Phase 8.5 - Redaction tests (Issue #8.5)."""

from __future__ import annotations

import pytest

from app.exports.redaction import (
    REDACTED,
    SENSITIVE_KEY_SUBSTRINGS,
    assert_no_forbidden_substrings,
    forbidden_substrings,
    redact,
)


def test_redact_replaces_sensitive_keys_at_top_level():
    result = redact({"api_key": "AKIAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                     "symbol": "BTCUSDT"})
    assert result["api_key"] == REDACTED
    assert result["symbol"] == "BTCUSDT"


def test_redact_recurses_into_nested_structures():
    payload = {
        "outer": {
            "telegram_bot_token": "1234567890:abcdefghijklmnopqrstuvwxyz1234567890",
            "trade": {"price": 100.0, "secret": "should_be_redacted"},
        },
        "list": [{"password": "x"}, "regular"],
    }
    result = redact(payload)
    assert result["outer"]["telegram_bot_token"] == REDACTED
    assert result["outer"]["trade"]["price"] == 100.0
    assert result["outer"]["trade"]["secret"] == REDACTED
    assert result["list"][0]["password"] == REDACTED
    assert result["list"][1] == "regular"


def test_redact_does_not_mutate_input():
    payload = {"api_key": "X", "symbol": "BTCUSDT"}
    redact(payload)
    assert payload == {"api_key": "X", "symbol": "BTCUSDT"}


def test_redact_handles_value_patterns_under_safe_keys():
    """A 64-char hex / 40-char [A-Za-z0-9] string under a *neutral*
    key must still be redacted because it pattern-matches a Binance-
    style API key."""
    payload = {"note": "A" * 64}
    out = redact(payload)
    assert out["note"] == REDACTED


def test_redact_strips_filesystem_paths():
    payload = {"banner": "/home/operator/.env"}
    out = redact(payload)
    assert out["banner"] == REDACTED


def test_redact_telegram_token_pattern_matches():
    payload = {"random": "1234567890:abcdefghijklmnopqrstuvwxyz1234567890"}
    out = redact(payload)
    assert out["random"] == REDACTED


def test_redact_sk_token_pattern_matches():
    payload = {"random": "sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890"}
    out = redact(payload)
    assert out["random"] == REDACTED


def test_redact_short_strings_pass_through():
    payload = {"random_short_string": "hello"}
    out = redact(payload)
    assert out["random_short_string"] == "hello"


def test_assert_no_forbidden_substrings_passes_when_clean():
    text = "{'symbol': 'BTCUSDT', 'reasons': ['live_trading_disabled']}"
    assert_no_forbidden_substrings(text)


def test_assert_no_forbidden_substrings_raises_when_dirty():
    text = "BINANCE_API_KEY=ABC"
    with pytest.raises(AssertionError):
        assert_no_forbidden_substrings(text)


def test_forbidden_substrings_covers_required_set():
    needles = forbidden_substrings()
    required = {
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
    }
    for needle in required:
        assert needle in needles


def test_sensitive_key_substrings_includes_addresses_and_tokens():
    must_have = {"api_key", "api_secret", "token", "password",
                 "withdrawal_address", "address", "auth", "private"}
    for needle in must_have:
        assert needle in SENSITIVE_KEY_SUBSTRINGS
