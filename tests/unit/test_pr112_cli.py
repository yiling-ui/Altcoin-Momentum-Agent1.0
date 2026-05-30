"""PR112 - live_capital_status CLI smoke tests (no network, read-only)."""

from __future__ import annotations

import json

import scripts.live_capital_status as cli_mod
from app.live.api_config import LiveApiConfig


def test_cli_default_json_no_creds(capsys):
    rc = cli_mod.main(["--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["runtime_mode"] == "LIVE_SHADOW"
    assert payload["real_order_allowed"] is False
    assert payload["exchange_live_orders"] is False
    assert payload["ai_trade_authority"] is False
    assert payload["phase_12_forbidden"] is True
    assert rc in (0, 1)


def test_cli_risk_check_sample_dry_only(capsys):
    rc = cli_mod.main(
        ["--risk-check-sample", "--symbol", "RAVEUSDT", "--notional", "1", "--leverage", "1", "--json"]
    )
    out = capsys.readouterr().out
    payload = json.loads(out)
    sample = payload["risk_check_sample"]
    # Dry decision only; never authorises a real order in PR112.
    assert sample["real_order_allowed"] is False
    # In LIVE_SHADOW (default) a real-order intent is rejected.
    assert sample["approved"] is False
    assert rc in (0, 1)


def test_cli_pnl_flag_runs_without_network(capsys):
    rc = cli_mod.main(["--pnl", "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    # No creds -> no account read, but the report is still emitted safely.
    assert payload["binance_private_read_enabled"] is False
    assert rc in (0, 1)


def test_cli_validate_env_reports_findings(capsys, tmp_path):
    env_file = tmp_path / ".env.live"
    env_file.write_text(
        "AMA_BINANCE_API_KEY=abc\n"
        "chmod 600 .env.liveALLOWED=false\n",
        encoding="utf-8",
    )
    rc = cli_mod.main(["--validate-env", "--env-file", str(env_file), "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    ev = payload["env_validation"]
    assert ev["exists"] is True
    assert ev["findings"], "expected a suspicious-line finding"
    # secret values never surface.
    assert "abc" not in json.dumps(ev)
    assert rc == 1


def test_cli_builds_report_with_capital_profile_from_env():
    # Direct build_report call with a config that carries L1_10U_PROBE.
    cfg = LiveApiConfig.from_env({"AMA_LIVE_CAPITAL_PROFILE": "L1_10U_PROBE"})

    class _Args:
        json = True
        pnl = False
        risk_check_sample = False
        symbol = "BTCUSDT"
        notional = 1.0
        leverage = 1.0
        validate_env = False
        env_file = ".env.live"
        daily_loss = 0.0
        total_loss = 0.0

    report = cli_mod.build_report(cfg, _Args())
    assert report["capital_profile_id"] == "L1_10U_PROBE"
    assert report["real_order_allowed"] is False
