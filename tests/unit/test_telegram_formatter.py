"""Phase 10D - Telegram formatter tests (Issue #10 Part 4).

Replaces the Phase 1 placeholder tests. The new contract:

  - 10 formatters exist and live under :mod:`app.telegram.formatter`.
  - Every formatter produces a SHORT string (no raw event dump).
  - Every formatter is a pure function (no IO, no network, no
    side-effects).
  - Every output carries the ``mode=PAPER|LIVE_LIMITED|LIVE`` banner
    AND the ``live=on|off`` flag so the operator never confuses a
    paper-mode message with a live-trading audit.
  - Every output is run through the Phase 8.5 redaction layer before
    return; credential-shaped values land as ``[REDACTED]``.
  - The risk-rejection formatter MUST surface six high-priority
    reasons when present: ``stop_unconfirmed``, ``unknown_position``,
    ``rebase_in_progress``, ``manipulation_m3``, ``data_degraded``,
    ``no_exit_channel``.
"""

from __future__ import annotations

import pytest

from app.exports.redaction import REDACTED
from app.telegram import formatter as fmt


EXPECTED_FORMATTERS = {
    "format_system_status",
    "format_market_regime",
    "format_candidate_symbol",
    "format_state_transition",
    "format_order_event",
    "format_risk_rejection",
    "format_profit_lock",
    "format_capital_rebase",
    "format_incident_alert",
    "format_daily_report",
}


HIGH_PRIORITY_REASONS = (
    "stop_unconfirmed",
    "unknown_position",
    "rebase_in_progress",
    "manipulation_m3",
    "data_degraded",
    "no_exit_channel",
)


# ---------------------------------------------------------------------------
# Vocabulary + registry
# ---------------------------------------------------------------------------
def test_all_ten_formatters_exist():
    for name in EXPECTED_FORMATTERS:
        assert hasattr(fmt, name), f"Missing formatter: {name}"
        assert callable(getattr(fmt, name))


def test_formatters_registry_pinned():
    expected_tags = {
        "system_status",
        "market_regime",
        "candidate_symbol",
        "state_transition",
        "order_event",
        "risk_rejection",
        "profit_lock",
        "capital_rebase",
        "incident_alert",
        "daily_report",
    }
    assert set(fmt.FORMATTERS.keys()) == expected_tags
    assert set(fmt.ALL_TAGS) == expected_tags


def test_high_priority_reject_reasons_pinned():
    assert set(fmt.HIGH_PRIORITY_REJECT_REASONS) == set(HIGH_PRIORITY_REASONS)


def test_allowed_trading_modes_pinned():
    assert set(fmt.ALLOWED_TRADING_MODES) == {
        "PAPER",
        "LIVE_LIMITED",
        "LIVE",
    }


# ---------------------------------------------------------------------------
# Banner + tag invariants
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(EXPECTED_FORMATTERS))
def test_every_formatter_carries_banner(name):
    payload = {
        "trading_mode": "paper",
        "live_trading_enabled": False,
        "symbol": "BTCUSDT",
        # Plus a couple of generic fields the formatters look at.
        "status": "running",
        "market_regime": "MEME_RISK_ON",
        "risk_permission": "ALLOW_ATTACK",
        "from": "no_trade",
        "to": "observe",
        "trigger": "test",
        "event": "ORDER_FILLED",
        "side": "buy",
        "intent": "new_open",
        "qty": 0.001,
        "action": "test_action",
        "reasons": ["test_reason"],
        "level": "P1",
        "title": "synthetic",
        "trade_count": 0,
        "risk_approved_count": 0,
        "risk_rejected_count": 0,
        "net_trading_pnl": 0.0,
        "incidents_count": 0,
    }
    text = getattr(fmt, name)(payload)
    assert isinstance(text, str)
    assert text.startswith("[ama-rt:")
    assert "mode=PAPER" in text
    assert "live=off" in text


@pytest.mark.parametrize("name", sorted(EXPECTED_FORMATTERS))
def test_every_formatter_renders_in_under_1024_chars(name):
    """Telegram messages have a hard length limit; every formatter MUST
    return a short line. This test pins it at 1024 chars so a future
    PR cannot accidentally introduce a megabyte payload."""
    payload = {"trading_mode": "paper", "live_trading_enabled": False}
    out = getattr(fmt, name)(payload)
    assert len(out) < 1024


@pytest.mark.parametrize(
    "trading_mode,expected",
    [
        ("paper", "PAPER"),
        ("PAPER", "PAPER"),
        ("live_limited", "LIVE_LIMITED"),
        ("LIVE_LIMITED", "LIVE_LIMITED"),
        ("live", "LIVE"),
        ("LIVE", "LIVE"),
        ("nonsense", "PAPER"),
        (None, "PAPER"),
        (12345, "PAPER"),
    ],
)
def test_banner_normalises_trading_mode(trading_mode, expected):
    payload = {"trading_mode": trading_mode, "live_trading_enabled": False}
    text = fmt.format_system_status(payload)
    assert f"mode={expected}" in text


def test_banner_normalises_live_flag():
    on = fmt.format_system_status(
        {"trading_mode": "paper", "live_trading_enabled": True}
    )
    off = fmt.format_system_status(
        {"trading_mode": "paper", "live_trading_enabled": False}
    )
    assert "live=on" in on
    assert "live=off" in off


# ---------------------------------------------------------------------------
# Risk-rejection formatter - MUST surface 6 high-priority reasons
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("reason", HIGH_PRIORITY_REASONS)
def test_risk_rejection_surfaces_each_high_priority_reason(reason):
    text = fmt.format_risk_rejection(
        {
            "trading_mode": "paper",
            "live_trading_enabled": False,
            "symbol": "BTCUSDT",
            "action": "attack",
            "reasons": [reason],
        }
    )
    assert reason in text
    # The "[!]" warning prefix is mandatory per Issue brief.
    assert "[!]" in text


def test_risk_rejection_surfaces_all_six_reasons_together():
    text = fmt.format_risk_rejection(
        {
            "trading_mode": "paper",
            "live_trading_enabled": False,
            "symbol": "PEPEUSDT",
            "action": "right_tail_amplify",
            "reasons": list(HIGH_PRIORITY_REASONS),
        }
    )
    for reason in HIGH_PRIORITY_REASONS:
        assert reason in text
    assert "[!]" in text


def test_risk_rejection_handles_string_reasons_field():
    """Some upstream callers pass ``reasons`` as a comma-separated string."""
    text = fmt.format_risk_rejection(
        {
            "trading_mode": "paper",
            "live_trading_enabled": False,
            "symbol": "BTCUSDT",
            "action": "attack",
            "reasons": "stop_unconfirmed,manipulation_m3",
        }
    )
    assert "stop_unconfirmed" in text
    assert "manipulation_m3" in text
    assert "[!]" in text


def test_risk_rejection_without_high_priority_reason_omits_warning():
    text = fmt.format_risk_rejection(
        {
            "trading_mode": "paper",
            "live_trading_enabled": False,
            "symbol": "BTCUSDT",
            "action": "scout",
            "reasons": ["minor_tilt"],
        }
    )
    assert "[!]" not in text
    assert "minor_tilt" in text


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(EXPECTED_FORMATTERS))
def test_every_formatter_redacts_credential_keys(name):
    """Every formatter MUST run its input through redact() so a
    misconfigured upstream caller cannot leak a credential."""
    payload = {
        "trading_mode": "paper",
        "live_trading_enabled": False,
        "symbol": "BTCUSDT",
        "api_key": "shouldnotleak",
        "api_secret": "shouldnotleak",
        "bot_token": "shouldnotleak",
        "telegram_bot_token": "shouldnotleak",
        "deepseek_api_key": "shouldnotleak",
        "from": "no_trade",
        "to": "observe",
        "trigger": "t",
        "action": "test",
        "event": "test",
        "intent": "new_open",
        "qty": 0.0,
        "level": "P1",
        "title": "x",
        "trade_count": 0,
        "risk_approved_count": 0,
        "risk_rejected_count": 0,
        "net_trading_pnl": 0.0,
        "incidents_count": 0,
        "market_regime": "MEME_RISK_ON",
        "risk_permission": "ALLOW_ATTACK",
    }
    text = getattr(fmt, name)(payload)
    assert "shouldnotleak" not in text


@pytest.mark.parametrize("name", sorted(EXPECTED_FORMATTERS))
def test_every_formatter_blocks_forbidden_substrings(name):
    """Even if the upstream input contains the literal env-var
    fragment (``BINANCE_API_KEY=`` etc.) the formatter MUST NOT
    emit it. The keys themselves are sensitive substrings, so the
    redactor replaces the value with [REDACTED]; the substring
    BINANCE_API_KEY= remains in a separate `note` field but the
    redactor wipes any value-shaped credential it sees."""
    payload = {
        "trading_mode": "paper",
        "live_trading_enabled": False,
        "symbol": "BTCUSDT",
        "from": "no_trade",
        "to": "observe",
        "trigger": "t",
        "action": "test",
        "event": "test",
        "intent": "new_open",
        "qty": 0.0,
        "level": "P1",
        "title": "x",
        "trade_count": 0,
        "risk_approved_count": 0,
        "risk_rejected_count": 0,
        "net_trading_pnl": 0.0,
        "incidents_count": 0,
        "market_regime": "MEME_RISK_ON",
        "risk_permission": "ALLOW_ATTACK",
        # 64-char hex string the redactor recognises as Binance-style.
        "extra_field": "a" * 64,
    }
    text = getattr(fmt, name)(payload)
    # The 64-char string should not appear; it should be redacted.
    assert "a" * 64 not in text


def test_redacted_marker_propagates_through_formatter():
    """When the redactor replaces a value the formatter still
    renders cleanly with the [REDACTED] marker rather than crashing."""
    text = fmt.format_system_status(
        {
            "trading_mode": "paper",
            "live_trading_enabled": False,
            "api_key": "should_not_appear",
            "status": "running",
        }
    )
    # The api_key value is gone from the rendered output.
    assert "should_not_appear" not in text


# ---------------------------------------------------------------------------
# Pure function: no IO, no state mutation
# ---------------------------------------------------------------------------
def test_formatters_are_pure_no_input_mutation():
    payload = {"trading_mode": "paper", "live_trading_enabled": False}
    snapshot = dict(payload)
    fmt.format_system_status(payload)
    assert payload == snapshot


def test_formatters_module_does_not_expose_network_symbols():
    """No socket / urllib / requests / httpx / aiohttp / telegram
    bot-library symbol exists in the formatter module namespace."""
    forbidden = {
        "socket",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
        "python_telegram_bot",
        "telebot",
        "aiogram",
    }
    assert forbidden.isdisjoint(set(vars(fmt).keys()))


# ---------------------------------------------------------------------------
# Specific formatters - shape pins
# ---------------------------------------------------------------------------
def test_market_regime_surfaces_systemic_risk_warning():
    text = fmt.format_market_regime(
        {
            "trading_mode": "paper",
            "live_trading_enabled": False,
            "market_regime": "SYSTEMIC_RISK",
            "risk_permission": "BLOCK_ALL",
        }
    )
    assert "SYSTEMIC_RISK" in text
    assert "[!]" in text


def test_market_regime_surfaces_alt_risk_off_warning():
    text = fmt.format_market_regime(
        {
            "trading_mode": "paper",
            "live_trading_enabled": False,
            "market_regime": "ALT_RISK_OFF",
            "risk_permission": "ALLOW_SCOUT",
        }
    )
    assert "ALT_RISK_OFF" in text
    assert "[!]" in text


def test_incident_alert_promotes_p0_and_p1():
    p0 = fmt.format_incident_alert(
        {
            "trading_mode": "paper",
            "live_trading_enabled": False,
            "level": "P0",
            "title": "ghost_position",
        }
    )
    assert "[!] P0" in p0

    p1 = fmt.format_incident_alert(
        {
            "trading_mode": "paper",
            "live_trading_enabled": False,
            "level": "P1",
            "title": "ws_drop",
        }
    )
    assert "[!] P1" in p1


def test_capital_rebase_carries_lifetime_and_pnl():
    text = fmt.format_capital_rebase(
        {
            "trading_mode": "paper",
            "live_trading_enabled": False,
            "event": "CAPITAL_REBASE",
            "trading_capital": 120.0,
            "exchange_equity": 120.0,
            "withdrawn_profit": 80.0,
            "lifetime_equity": 200.0,
            "net_trading_pnl": 20.0,
        }
    )
    assert "trading_capital=120" in text
    assert "lifetime_equity=200" in text
    # The hard rule: a withdrawal is NOT a loss; net_trading_pnl is
    # surfaced so the operator sees the correct number.
    assert "net_trading_pnl=20" in text


def test_state_transition_carries_from_to():
    text = fmt.format_state_transition(
        {
            "trading_mode": "paper",
            "live_trading_enabled": False,
            "symbol": "BTCUSDT",
            "from": "scout",
            "to": "confirm",
            "trigger": "promote",
            "reasons": ["cvd_aligned"],
        }
    )
    assert "scout->confirm" in text
    assert "cvd_aligned" in text
