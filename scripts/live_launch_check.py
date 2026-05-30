"""Live launch readiness CLI (PR116 - 10U LIVE_LIMITED Launch Pack v0).

A single end-to-end readiness check. It NEVER sends a real order.

Examples
--------
    python scripts/live_launch_check.py --json
    python scripts/live_launch_check.py --binance --telegram --deepseek --json
    python scripts/live_launch_check.py --pre-live-limited --json
    python scripts/live_launch_check.py --pre-live-limited --require-real-keys --json

Output (JSON) includes: overall_status (PASS/WARN/FAIL), go_for_live_shadow,
go_for_live_limited, blockers, warnings, runtime_mode, capital_profile_id,
account_equity, usable_live_capital, l1_10u_cap_enforced, the per-surface
status flags, and ``no_real_order_sent`` (always true).

EXIT CODES
----------
  0 = OK   (overall PASS or WARN; nothing sent)
  1 = FAIL (a hard blocker / config error; nothing sent)
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
from app.live.live_launch_readiness import LiveLaunchReadinessChecker  # noqa: E402
from app.live.status import HealthStatus  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live_launch_check",
        description="AMA-RT PR116 launch readiness check (never sends a real order).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument("--binance", action="store_true", help="Check Binance APIs.")
    parser.add_argument("--telegram", action="store_true", help="Check Telegram outbound.")
    parser.add_argument("--deepseek", action="store_true", help="Check DeepSeek (optional).")
    parser.add_argument(
        "--pre-live-limited",
        dest="pre_live_limited",
        action="store_true",
        help="Strict mode: missing live-limited gates are FAIL (not WARN).",
    )
    parser.add_argument(
        "--require-real-keys",
        dest="require_real_keys",
        action="store_true",
        help="Require real (non-placeholder) Binance keys; missing keys are FAIL.",
    )
    parser.add_argument("--symbol", default=None, help="Symbol for the DRY order validation.")
    return parser


def _resolve_checks(args: argparse.Namespace) -> tuple[bool, bool, bool]:
    """Default to binance+telegram when no provider flag is given."""
    if not (args.binance or args.telegram or args.deepseek):
        return True, True, False
    return bool(args.binance), bool(args.telegram), bool(args.deepseek)


def _render_text(d: dict) -> str:
    lines = ["=" * 64, "AMA-RT PR116 Live Launch Readiness (no real order)", "=" * 64]
    lines.append(f"overall_status        : {d['overall_status']}")
    lines.append(f"go_for_live_shadow    : {d['go_for_live_shadow']}")
    lines.append(f"go_for_live_limited   : {d['go_for_live_limited']}")
    lines.append(f"runtime_mode          : {d['runtime_mode']}")
    lines.append(f"capital_profile_id    : {d['capital_profile_id']}")
    lines.append(f"account_equity        : {d['account_equity']}")
    lines.append(f"usable_live_capital   : {d['usable_live_capital']}")
    lines.append(f"l1_10u_cap_enforced   : {d['l1_10u_cap_enforced']}")
    lines.append(f"kill_switch_armed     : {d['kill_switch_armed']}")
    lines.append(f"exchange_live_orders  : {d['exchange_live_orders']}")
    lines.append(f"trade_authority       : {d['trade_authority']}")
    lines.append(f"ai_trade_authority    : {d['ai_trade_authority']}")
    lines.append(f"no_real_order_sent    : {d['no_real_order_sent']}")
    lines.append("-" * 64)
    if d["blockers"]:
        lines.append("BLOCKERS:")
        for b in d["blockers"]:
            lines.append(f"  - {b}")
    if d["warnings"]:
        lines.append("WARNINGS:")
        for w in d["warnings"]:
            lines.append(f"  - {w}")
    lines.append("=" * 64)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    check_binance, check_telegram, check_deepseek = _resolve_checks(args)
    config = LiveApiConfig.from_env()
    checker = LiveLaunchReadinessChecker(config)
    report = checker.run(
        pre_live_limited=args.pre_live_limited,
        require_real_keys=args.require_real_keys,
        check_binance=check_binance,
        check_telegram=check_telegram,
        check_deepseek=check_deepseek,
        dry_order_symbol=args.symbol,
    )
    d = report.to_dict()
    if args.json:
        print(json.dumps(d, indent=2, sort_keys=True))
    else:
        print(_render_text(d))
    return 1 if report.overall_status is HealthStatus.FAIL else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
