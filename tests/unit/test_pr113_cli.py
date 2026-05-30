"""PR113 - live_execution_smoke CLI tests (no network, never sends an order)."""

from __future__ import annotations

import json

import scripts.live_execution_smoke as cli_mod


def test_cli_permission_check_default_blocked(capsys):
    rc = cli_mod.main(["--permission-check", "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["mode"] == "permission_check"
    assert payload["execution_permission"] is False
    assert payload["exchange_live_orders"] is False
    assert payload["trade_authority"] is False
    assert payload["runtime_mode"] == "LIVE_SHADOW"
    assert payload["private_trade_enabled"] is False
    assert payload["no_real_order_sent"] is True
    assert rc in (0, 1)


# ===========================================================================
# 30: CLI dry-run does not send order
# ===========================================================================
def test_30_cli_dry_run_does_not_send_order(capsys):
    rc = cli_mod.main(
        [
            "--dry-run-order",
            "--symbol",
            "RAVEUSDT",
            "--side",
            "BUY",
            "--notional",
            "1",
            "--leverage",
            "1",
            "--json",
        ]
    )
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["mode"] == "dry_run_order"
    assert payload["no_real_order_sent"] is True
    assert payload["submit_result"] is None
    # Required printed fields are present.
    for key in (
        "execution_permission",
        "reject_reason",
        "exchange_live_orders",
        "trade_authority",
        "runtime_mode",
        "capital_profile_id",
        "private_trade_enabled",
        "order_normalization_result",
    ):
        assert key in payload
    assert rc in (0, 1)


# ===========================================================================
# 31: CLI real-order path blocked unless explicit confirmation + gates true
# ===========================================================================
def test_31_cli_real_order_blocked_without_flags(capsys):
    rc = cli_mod.main(["--real-order", "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["mode"] == "real_order"
    assert payload["no_real_order_sent"] is True
    assert payload["submit_result"] is None
    assert payload["real_order_blocked_reason"] == "missing_or_invalid_confirmation_flags"
    assert rc == 1


def test_31b_cli_real_order_blocked_even_with_flags_when_gates_false(capsys):
    # All three confirmation flags supplied + a matching confirm code, but the
    # execution gate flags default False -> still blocked, no order sent.
    import os

    os.environ["AMA_LIVE_EXECUTION_CONFIRM_CODE"] = "LIVE-XYZ"
    try:
        rc = cli_mod.main(
            [
                "--real-order",
                "--i-understand-this-places-real-order",
                "--confirm-code",
                "LIVE-XYZ",
                "--symbol",
                "RAVEUSDT",
                "--side",
                "BUY",
                "--notional",
                "1",
                "--leverage",
                "1",
                "--json",
            ]
        )
    finally:
        os.environ.pop("AMA_LIVE_EXECUTION_CONFIRM_CODE", None)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["no_real_order_sent"] is True
    assert payload["submit_result"] is None
    # The block reason is now a gate reason (not the confirmation flags).
    assert payload["real_order_blocked_reason"] != "missing_or_invalid_confirmation_flags"
    assert rc == 1


def test_cli_build_report_with_profile_from_env():
    from app.live.api_config import LiveApiConfig

    cfg = LiveApiConfig.from_env({"AMA_LIVE_CAPITAL_PROFILE": "L1_10U_PROBE"})

    class _Args:
        json = True
        permission_check = True
        dry_run_order = False
        real_order = False
        i_understand = False
        confirm_code = ""
        symbol = "RAVEUSDT"
        side = "BUY"
        order_type = "MARKET"
        notional = 1.0
        quantity = 0.0
        price = 0.0
        stop_price = 0.0
        leverage = 1.0
        reduce_only = False
        planned_entry_price = 0.0
        planned_stop_price = 0.0
        planned_take_profit_price = 0.0

    report = cli_mod.build_report(cfg, _Args(), environ={})
    assert report["capital_profile_id"] == "L1_10U_PROBE"
    assert report["no_real_order_sent"] is True
