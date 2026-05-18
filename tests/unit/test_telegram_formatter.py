"""Telegram formatter skeleton tests (Issue #10 placeholder coverage)."""

from __future__ import annotations

from app.telegram import formatter

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


def test_all_ten_formatters_exist():
    for name in EXPECTED_FORMATTERS:
        assert hasattr(formatter, name), f"Missing formatter placeholder: {name}"
        assert callable(getattr(formatter, name))


def test_formatters_registry_is_complete():
    assert set(formatter.FORMATTERS.keys()) == {
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


def test_formatters_are_pure_strings_with_skeleton_tag():
    """Every Phase 1 formatter must return a deterministic string tagged
    so accidental leakage to a real channel is recognisable."""
    payload = {"a": 1, "b": "x"}
    for name in EXPECTED_FORMATTERS:
        out = getattr(formatter, name)(payload)
        assert isinstance(out, str)
        assert out.startswith("[PHASE1-SKELETON]")
        assert "a=1" in out and "b=x" in out


def test_formatters_make_no_network_calls():
    """Phase 1 formatters must not perform IO. We verify by ensuring no
    socket / urllib / requests symbol exists in the module namespace."""
    forbidden = {"socket", "urllib", "requests", "httpx", "aiohttp"}
    assert forbidden.isdisjoint(set(vars(formatter).keys()))
