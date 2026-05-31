"""Unified live API health check CLI (PR111 - API Integration Pack v0).

Runs a NON-MUTATING health check across the Binance / Telegram /
DeepSeek live APIs and prints a report (text or JSON).

USAGE
-----

    python scripts/live_api_health_check.py --all
    python scripts/live_api_health_check.py --binance
    python scripts/live_api_health_check.py --telegram
    python scripts/live_api_health_check.py --deepseek
    python scripts/live_api_health_check.py --all --json
    python scripts/live_api_health_check.py --telegram --send-telegram-test --chat-id 123

SAFETY (enforced by this CLI)
-----------------------------

  1. Running the health check NEVER places / cancels / modifies an order.
  2. It NEVER switches runtime mode.
  3. It NEVER enables live trading.
  4. It NEVER modifies leverage / margin.
  5. It NEVER sends a Telegram message unless ``--send-telegram-test`` is
     explicitly provided (AND outbound is enabled in config).
  6. It NEVER calls DeepSeek unless ``--deepseek`` or ``--all`` is
     provided.
  7. Secrets are always masked; no API key / secret / token is printed.

EXIT CODES
----------

  0 = overall PASS / SKIPPED
  1 = overall WARN
  2 = overall FAIL
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.live.api_config import LiveApiConfig  # noqa: E402
from app.live.health import (  # noqa: E402
    DEFAULT_CAPITAL_PROFILE_ID,
    LiveApiHealthReport,
    run_unified_health_check,
)
from app.live.status import HealthStatus  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live_api_health_check",
        description="AMA-RT PR111 unified live API health check (read-only).",
    )
    parser.add_argument("--all", action="store_true", help="Check Binance + Telegram + DeepSeek")
    parser.add_argument("--binance", action="store_true", help="Check Binance only")
    parser.add_argument("--telegram", action="store_true", help="Check Telegram only")
    parser.add_argument("--deepseek", action="store_true", help="Check DeepSeek (calls the API)")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument(
        "--send-telegram-test",
        action="store_true",
        help="Send an explicit Telegram test message (requires outbound enabled).",
    )
    parser.add_argument(
        "--chat-id",
        default=None,
        help="Chat id for --send-telegram-test (defaults to first allowed chat id).",
    )
    parser.add_argument(
        "--capital-profile-id",
        default=DEFAULT_CAPITAL_PROFILE_ID,
        help="Capital profile id to record in the report (PR110 handoff).",
    )
    return parser


def _resolve_targets(args: argparse.Namespace) -> tuple[bool, bool, bool]:
    """Return (check_binance, check_telegram, check_deepseek).

    With no provider flag (and not --all), default to Binance + Telegram
    (the read-only, non-API-calling providers). DeepSeek is only checked
    when --deepseek or --all is provided (it calls the real API).
    """
    if args.all:
        return True, True, True
    any_specified = args.binance or args.telegram or args.deepseek
    if not any_specified:
        return True, True, False
    return bool(args.binance), bool(args.telegram), bool(args.deepseek)


def _status_exit_code(status: HealthStatus) -> int:
    if status == HealthStatus.FAIL:
        return 2
    if status == HealthStatus.WARN:
        return 1
    return 0


def _render_text(report: LiveApiHealthReport) -> str:
    d = report.to_dict()
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("AMA-RT PR111 Live API Health Check (read-only)")
    lines.append("=" * 60)
    lines.append(f"overall_status            : {d['overall_status']}")
    lines.append(f"live_runtime_mode         : {d['live_runtime_mode']}")
    lines.append(f"capital_profile_id        : {d['capital_profile_id']}")
    lines.append(f"binance_public_status     : {d['binance_public_status']}")
    lines.append(f"binance_private_read      : {d['binance_private_read_status']}")
    lines.append(f"binance_private_trade     : {d['binance_private_trade_status']}")
    lines.append(f"telegram_status           : {d['telegram_status']}")
    lines.append(f"deepseek_status           : {d['deepseek_status']}")
    lines.append(f"exchange_live_orders      : {d['exchange_live_orders']}")
    lines.append(f"ai_trade_authority        : {d['ai_trade_authority']}")
    lines.append(f"telegram_outbound_enabled : {d['telegram_outbound_enabled']}")
    lines.append(f"secrets_masked            : {d['secrets_masked']}")
    if report.binance is not None:
        b = report.binance.to_dict()
        lines.append("-" * 60)
        lines.append("Binance:")
        lines.append(f"  masked_api_key          : {b['masked_api_key']}")
        lines.append(f"  symbol_count            : {b['symbol_count']}")
        lines.append(f"  can_read_account        : {b['can_read_account']}")
        lines.append(f"  can_read_positions      : {b['can_read_positions']}")
        lines.append(f"  can_read_income         : {b['can_read_income']}")
        lines.append(f"  high_risk_permission    : {b['high_risk_permission_warning']}")
        # PR118: surface the AUTHORITATIVE key-permission view (tri-state;
        # None / NOT_REPORTED means Binance did not expose the field).
        def _perm(v: object) -> str:
            return "NOT_REPORTED" if v is None else str(v)

        lines.append(f"  withdraw_permission     : {_perm(b['withdraw_permission'])} (BLOCKER if True)")
        lines.append(f"  universal_transfer_perm : {_perm(b['universal_transfer_permission'])} (WARN if True)")
        lines.append(f"  internal_transfer_perm  : {_perm(b['internal_transfer_permission'])} (WARN if True)")
        lines.append(f"  futures_trade_permission: {_perm(b['futures_trade_permission'])} (INFO/WARN)")
        lines.append(f"  account_can_trade       : {b['can_trade_if_account_reports_it']} (INFO only)")
        lines.append(f"  api_restrictions_reported: {b['api_restrictions_reported']}")
        if b.get("permission_debug"):
            lines.append("  permission_debug (sanitised; no secret/key/id):")
            for key in (
                "raw_permission_fields_seen",
                "enableWithdrawals",
                "enableInternalTransfer",
                "permitsUniversalTransfer",
                "enableFutures",
                "enableSpotAndMarginTrading",
                "enableReading",
                "ipRestrict",
                "api_restrictions_read",
            ):
                if key in b["permission_debug"]:
                    lines.append(f"    {key:<26}: {b['permission_debug'][key]}")
        if b["warnings"]:
            lines.append(f"  warnings                : {b['warnings']}")
        if b["errors"]:
            lines.append(f"  errors                  : {b['errors']}")
    if report.telegram is not None:
        t = report.telegram.to_dict()
        lines.append("-" * 60)
        lines.append("Telegram:")
        lines.append(f"  bot_token_present       : {t['bot_token_present']}")
        lines.append(f"  masked_bot_token        : {t['masked_bot_token']}")
        lines.append(f"  outbound_enabled        : {t['outbound_enabled']}")
        lines.append(f"  test_message_sent       : {t['test_message_sent']}")
        if t["detail"]:
            lines.append(f"  detail                  : {t['detail']}")
    if report.deepseek is not None:
        s = report.deepseek.to_dict()
        lines.append("-" * 60)
        lines.append("DeepSeek:")
        lines.append(f"  api_key_present         : {s['api_key_present']}")
        lines.append(f"  masked_api_key          : {s['masked_api_key']}")
        lines.append(f"  enabled                 : {s['enabled']}")
        lines.append(f"  briefing_generated      : {s['briefing_generated']}")
        lines.append(f"  ai_trade_authority      : {s['ai_trade_authority']}")
        if s["forbidden_fields_rejected"]:
            lines.append(f"  forbidden_fields_rejected: {s['forbidden_fields_rejected']}")
        if s["detail"]:
            lines.append(f"  detail                  : {s['detail']}")
    lines.append("=" * 60)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    check_binance, check_telegram, check_deepseek = _resolve_targets(args)

    config = LiveApiConfig.from_env()

    report = run_unified_health_check(
        config,
        check_binance=check_binance,
        check_telegram=check_telegram,
        check_deepseek=check_deepseek,
        # DeepSeek API is only actually called when DeepSeek is a target.
        call_deepseek=check_deepseek,
        # Telegram message is only sent when explicitly requested.
        send_telegram_test=bool(args.send_telegram_test),
        test_chat_id=args.chat_id,
        capital_profile_id=args.capital_profile_id,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(_render_text(report))

    return _status_exit_code(report.overall_status)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
