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


def test_redact_strips_sandbox_and_dev_paths():
    """Phase 8.5 self-check #2: server / sandbox absolute paths must
    never land in an export bundle. Cover the prefix list explicitly
    so a regression on any one of them fails this test."""
    cases = [
        "/home/operator/secret.db",
        "/root/.ssh/id_rsa",
        "/Users/alice/Documents/secret",
        "/projects/sandbox/Altcoin-Momentum-Agent1.0/data/sqlite/events.db",
        "/data/operator/state",
        "/tmp/ama-rt-cache/secret",
        "/var/lib/ama/state",
        "/etc/secrets/api.yaml",
        "/usr/local/etc/ama.conf",
        "/opt/ama/runtime",
        "/srv/exports/private",
        "/mnt/data/state",
        "/private/var/db/secret",
        "/workspace/dev/key",
        "/app/runtime/state",
        "C:\\Users\\Alice\\AppData\\config",
        "C:/Users/Alice/AppData/config",
        "D:\\Users\\Alice\\state",
        "E:/private/path",
        "~/secrets/key",
        "~\\AppData\\config",
        "\\\\fileserver\\share\\secret",
    ]
    for raw in cases:
        out = redact({"some_path": raw})
        assert out["some_path"] == REDACTED, (
            f"redaction did not strip absolute path candidate: {raw!r}"
        )


def test_redact_does_not_overstrip_non_paths():
    """Strings that merely *look* like they could touch the path
    namespace (without the prefix shape) must not be redacted."""
    safe_cases = [
        "BTCUSDT",
        "PEPEUSDT",
        "live_trading_disabled",
        "phase8_5_boot",
        "ALLOW_ATTACK",
        "data/sqlite/events.db",  # relative, not absolute
        "events.jsonl",
        "v1.4.0a8.5",
    ]
    for raw in safe_cases:
        out = redact({"label": raw})
        assert out["label"] == raw, f"redaction over-stripped {raw!r}"


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
