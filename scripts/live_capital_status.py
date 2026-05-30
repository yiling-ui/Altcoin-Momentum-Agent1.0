"""Live capital / risk / funding-aware PnL status CLI (PR112).

Reads the REAL Binance account state (when env is configured for private
read), builds a :class:`app.live.capital_state.LiveCapitalState`, computes
a funding-aware :class:`app.live.pnl_accounting.LivePnlSummary`, enforces
the active capital profile, and (optionally) runs a deterministic *dry*
live order risk pre-check. It prints a report (text or JSON).

USAGE
-----

    python scripts/live_capital_status.py --json
    python scripts/live_capital_status.py --pnl --json
    python scripts/live_capital_status.py --risk-check-sample --symbol RAVEUSDT --notional 1 --leverage 1 --json
    python scripts/live_capital_status.py --validate-env --env-file .env.live --json

SAFETY (enforced by this CLI)
-----------------------------

  1. It NEVER places / cancels / modifies an order.
  2. It NEVER switches runtime mode.
  3. It NEVER changes leverage / margin mode.
  4. It NEVER calls a Binance PRIVATE_TRADE endpoint.
  5. It NEVER auto-switches to LIVE_LIMITED and NEVER auto-escalates the
     capital profile.
  6. Secrets are always masked; no API key / secret / token is printed.
  7. The risk-check sample produces a DRY decision only:
     ``real_order_allowed=false`` always in PR112.

EXIT CODES
----------

  0 = OK (no blocking warning)
  1 = WARN (profile mismatch / config warning / placeholder secret / risk reject)
  2 = FAIL (could not read the account when private read was requested)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.enums import OrderSource  # noqa: E402
from app.live.api_config import LiveApiConfig  # noqa: E402
from app.live.binance_client import BinanceLiveClient  # noqa: E402
from app.live.binance_models import BinanceAccountSnapshot  # noqa: E402
from app.live.capital_profile import get_profile  # noqa: E402
from app.live.env_validation import validate_env_file  # noqa: E402
from app.live.live_capital_service import (  # noqa: E402
    LiveCapitalService,
    build_live_risk_reject_payload,
)
from app.live.live_risk_engine import LiveOrderIntent, evaluate_live_order_risk  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live_capital_status",
        description=(
            "AMA-RT PR112 live capital / risk / funding-aware PnL status "
            "(read-only; NO live orders)."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument(
        "--pnl",
        action="store_true",
        help="Include the funding-aware PnL summary (reads income history).",
    )
    parser.add_argument(
        "--risk-check-sample",
        action="store_true",
        help="Run a DRY live order risk pre-check sample (never submits).",
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="Risk-check sample symbol.")
    parser.add_argument(
        "--notional", type=float, default=1.0, help="Risk-check sample planned notional (USDT)."
    )
    parser.add_argument(
        "--leverage", type=float, default=1.0, help="Risk-check sample planned leverage."
    )
    parser.add_argument(
        "--validate-env",
        action="store_true",
        help="Validate an env file's structure (no secret values printed).",
    )
    parser.add_argument(
        "--env-file",
        default=".env.live",
        help="Path to the env file to validate (default .env.live).",
    )
    parser.add_argument(
        "--daily-loss",
        type=float,
        default=0.0,
        help="Realised daily loss magnitude (USDT) to feed the profile check.",
    )
    parser.add_argument(
        "--total-loss",
        type=float,
        default=0.0,
        help="Realised total loss magnitude (USDT) to feed the profile check.",
    )
    return parser


def _read_account(
    config: LiveApiConfig, client: BinanceLiveClient | None
) -> tuple[BinanceAccountSnapshot | None, list, str]:
    """Read account + income via private read when configured.

    Returns ``(account_or_None, income_events, note)``. Never raises; a
    failure is reported via ``note`` so the CLI prints it without crashing.
    """
    binance = config.binance
    if not binance.enable_private_read:
        return None, [], "private_read_disabled_by_config"
    if not binance.has_credentials:
        return None, [], "MISSING_REAL_SECRET"
    if binance.api_key.is_placeholder or binance.api_secret.is_placeholder:
        return None, [], "PLACEHOLDER_SECRET_CONFIGURED"
    cli = client or BinanceLiveClient(binance, runtime_mode=config.live_runtime_mode)
    try:
        account = cli.get_account()
    except Exception as exc:  # secret-free message
        return None, [], f"account_read_failed:{str(exc)[:120]}"
    income = []
    try:
        income = cli.get_income_history(limit=200)
    except Exception as exc:  # income optional
        return account, [], f"income_read_failed:{str(exc)[:120]}"
    return account, income, "ok"


def build_report(
    config: LiveApiConfig,
    args: argparse.Namespace,
    *,
    binance_client: BinanceLiveClient | None = None,
) -> dict:
    """Build the read-only status report dict (no IO when no real creds)."""

    profile_id = config.capital_profile_id
    service = LiveCapitalService(
        runtime_mode=config.live_runtime_mode,
        capital_profile_id=profile_id,
    )

    report: dict = {
        "runtime_mode": config.live_runtime_mode.value,
        "capital_profile_id": profile_id.value,
        "capital_profile_config_error": config.general.capital_profile_error,
        "capital_profile_config_warning": config.general.capital_profile_warning,
        "binance_private_read_enabled": config.binance.enable_private_read,
        "real_order_allowed": False,
        "exchange_live_orders": False,
        "trade_authority": False,
        "ai_trade_authority": False,
        "phase_12_forbidden": True,
    }
    warnings: list[str] = []
    if config.general.capital_profile_warning:
        warnings.append(config.general.capital_profile_warning)

    if args.validate_env:
        report["env_validation"] = validate_env_file(args.env_file).to_dict()
        warnings.extend(report["env_validation"]["warnings"])

    account, income, note = _read_account(config, binance_client)
    report["account_read_note"] = note
    if note in ("PLACEHOLDER_SECRET_CONFIGURED", "MISSING_REAL_SECRET"):
        warnings.append(note)

    if account is not None:
        status = service.build_status_report(
            account,
            income if args.pnl else [],
            daily_loss_usdt=args.daily_loss,
            total_loss_usdt=args.total_loss,
        )
        report["capital_state"] = status["capital_state"]
        report["capital_profile_state"] = status["capital_profile_state"]
        report["telegram_payloads"] = status["telegram_payloads"]
        if args.pnl:
            report["pnl_summary"] = status["pnl_summary"]
        if status["capital_profile_state"]["flags"]:
            warnings.extend(status["capital_profile_state"]["flags"])
    else:
        report["capital_state"] = None
        report["capital_profile_state"] = None

    # Optional dry risk-check sample.
    if args.risk_check_sample:
        capital_state = None
        if account is not None:
            capital_state = service.build_capital_state(account)
        intent = LiveOrderIntent(
            symbol=args.symbol,
            side="LONG",
            planned_entry_price=0.0,
            planned_notional_usdt=float(args.notional),
            planned_leverage=float(args.leverage),
            planned_stop_price=None,
            planned_take_profit_price=None,
            exit_plan_present=False,
            stop_plan_present=False,
            candidate_stage="sample",
            opportunity_score=0.0,
            runtime_mode=config.live_runtime_mode,
            source=OrderSource.LIVE,
        )
        decision = evaluate_live_order_risk(
            intent,
            capital_state,
            get_profile(profile_id),
            runtime_mode=config.live_runtime_mode,
            daily_loss_usdt=args.daily_loss,
            total_loss_usdt=args.total_loss,
        )
        report["risk_check_sample"] = decision.to_dict()
        report["risk_check_sample_payload"] = build_live_risk_reject_payload(decision)
        if not decision.approved:
            warnings.append("risk_check_sample_rejected")

    report["warnings"] = list(dict.fromkeys(warnings))
    return report


def _render_text(report: dict) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("AMA-RT PR112 Live Capital / Risk / PnL Status (read-only)")
    lines.append("=" * 60)
    lines.append(f"runtime_mode              : {report['runtime_mode']}")
    lines.append(f"capital_profile_id        : {report['capital_profile_id']}")
    if report.get("capital_profile_config_error"):
        lines.append(f"capital_profile_error     : {report['capital_profile_config_error']}")
    lines.append(f"binance_private_read      : {report['binance_private_read_enabled']}")
    lines.append(f"account_read_note         : {report.get('account_read_note')}")
    lines.append(f"real_order_allowed        : {report['real_order_allowed']}")
    lines.append(f"exchange_live_orders      : {report['exchange_live_orders']}")
    lines.append(f"ai_trade_authority        : {report['ai_trade_authority']}")

    cs = report.get("capital_state")
    if cs:
        lines.append("-" * 60)
        lines.append("Account:")
        lines.append(f"  account_id_masked       : {cs['account_id_masked']}")
        lines.append(f"  wallet_balance_usdt     : {cs['wallet_balance_usdt']}")
        lines.append(f"  available_balance_usdt  : {cs['available_balance_usdt']}")
        lines.append(f"  account_equity_usdt     : {cs['account_equity_usdt']}")
        lines.append(f"  unrealized_pnl_usdt     : {cs['unrealized_pnl_usdt']}")
        lines.append(f"  used_margin_usdt        : {cs['used_margin_usdt']}")
        lines.append(f"  free_margin_usdt        : {cs['free_margin_usdt']}")
        lines.append(f"  open_position_count     : {cs['open_position_count']}")
        lines.append(f"  open_order_count        : {cs['open_order_count']}")

    ps = report.get("capital_profile_state")
    if ps:
        lines.append("-" * 60)
        lines.append("Capital profile:")
        lines.append(f"  profile_status          : {ps['profile_status']}")
        lines.append(f"  usable_capital_usdt     : {ps['usable_capital_usdt']}")
        lines.append(f"  flags                   : {ps['flags']}")
        lines.append(f"  risk_halt_active        : {ps['risk_halt_active']}")
        lines.append(f"  suggested_profile_id    : {ps['suggested_profile_id']}")
        lines.append(f"  auto_escalation_allowed : {ps['auto_escalation_allowed']}")

    pnl = report.get("pnl_summary")
    if pnl:
        lines.append("-" * 60)
        lines.append("Funding-aware PnL:")
        lines.append(f"  gross_realized_pnl_usdt : {pnl['gross_realized_pnl_usdt']}")
        lines.append(f"  commission_total_usdt   : {pnl['commission_total_usdt']}")
        lines.append(f"  funding_total_usdt      : {pnl['funding_total_usdt']}")
        lines.append(f"  net_strategy_pnl_usdt   : {pnl['net_strategy_pnl_usdt']}")
        lines.append(f"  external_deposit_total  : {pnl['external_deposit_total_usdt']}")
        lines.append(f"  external_withdrawal_tot : {pnl['external_withdrawal_total_usdt']}")
        lines.append(f"  funding_attribution     : {pnl['funding_attribution_status']}")

    rc = report.get("risk_check_sample")
    if rc:
        lines.append("-" * 60)
        lines.append("Dry risk-check sample:")
        lines.append(f"  approved                : {rc['approved']}")
        lines.append(f"  reject_reason           : {rc['reject_reason']}")
        lines.append(f"  planned_notional_usdt   : {rc['planned_notional_usdt']}")
        lines.append(f"  max_allowed_notional    : {rc['max_allowed_notional_usdt']}")
        lines.append(f"  planned_leverage        : {rc['planned_leverage']}")
        lines.append(f"  max_allowed_leverage    : {rc['max_allowed_leverage']}")
        lines.append(f"  real_order_allowed      : {rc['real_order_allowed']}")

    ev = report.get("env_validation")
    if ev:
        lines.append("-" * 60)
        lines.append("Env validation:")
        lines.append(f"  path                    : {ev['path']}")
        lines.append(f"  exists                  : {ev['exists']}")
        lines.append(f"  warnings                : {ev['warnings']}")
        lines.append(f"  suspicious_lines        : {[f['line_number'] for f in ev['findings']]}")

    if report.get("warnings"):
        lines.append("-" * 60)
        lines.append(f"warnings                  : {report['warnings']}")
    lines.append("=" * 60)
    return "\n".join(lines)


def _exit_code(report: dict) -> int:
    note = report.get("account_read_note", "")
    if note.startswith("account_read_failed"):
        return 2
    if report.get("warnings"):
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    config = LiveApiConfig.from_env()
    report = build_report(config, args)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_render_text(report))
    return _exit_code(report)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
