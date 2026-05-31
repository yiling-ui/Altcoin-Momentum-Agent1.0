"""Full-system single-altcoin live sandbox audit CLI (PR117).

The FINAL full-system sandbox audit. It runs the REAL PR110-PR116 live
chain against a single fake altcoin (``RAVEUSDT_SANDBOX``) using fake
transports only. It NEVER sends a real order, NEVER uses a real Binance /
Telegram / DeepSeek transport, and keeps blind / replay / sim isolated.

Examples
--------
    python scripts/live_full_system_sandbox_audit.py --json
    python scripts/live_full_system_sandbox_audit.py --symbol RAVEUSDT_SANDBOX --scenario all --json
    python scripts/live_full_system_sandbox_audit.py --scenario strategy_lifecycle --json
    python scripts/live_full_system_sandbox_audit.py --scenario capital_ladder --json
    python scripts/live_full_system_sandbox_audit.py --scenario funding_fee_pnl --json
    python scripts/live_full_system_sandbox_audit.py --scenario telegram_operator --json
    python scripts/live_full_system_sandbox_audit.py --scenario ai_guard --json
    python scripts/live_full_system_sandbox_audit.py --scenario kill_switch --json
    python scripts/live_full_system_sandbox_audit.py --scenario blind_isolation --json

Output (JSON) includes: overall_status (PASS/WARN/FAIL), scenario_results,
blockers, warnings, every *_chain_ok flag, no_real_order_sent (always
true), fake_transports_used (always true), live_trading / exchange_live_
orders / trade_authority / ai_trade_authority (all false by default), and
ready_for_real_key_validation.

EXIT CODES
----------
  0 = OK   (overall PASS or WARN; nothing sent)
  1 = FAIL (a hard blocker; nothing sent)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.live.full_system_audit_models import (  # noqa: E402
    ALL_SCENARIOS,
    AUDIT_FAIL,
    DEFAULT_SANDBOX_SYMBOL,
)
from app.live.full_system_sandbox import FullSystemSandboxAudit  # noqa: E402

_SCENARIO_CHOICES = ("all",) + ALL_SCENARIOS


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live_full_system_sandbox_audit",
        description=(
            "AMA-RT PR117 full-system single-altcoin live sandbox audit "
            "(fake transports only; never sends a real order)."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument(
        "--symbol", default=DEFAULT_SANDBOX_SYMBOL, help="Sandbox altcoin symbol."
    )
    parser.add_argument(
        "--scenario",
        default="all",
        choices=_SCENARIO_CHOICES,
        help="Scenario to run (default: all).",
    )
    return parser


def _render_text(d: dict) -> str:
    lines = ["=" * 70, "AMA-RT PR117 Full-System Single-Altcoin Live Sandbox Audit", "=" * 70]
    lines.append(f"symbol                         : {d['symbol']}")
    lines.append(f"overall_status                 : {d['overall_status']}")
    lines.append(f"full_system_chain_ok           : {d['full_system_chain_ok']}")
    lines.append(f"strategy_chain_ok              : {d['strategy_chain_ok']}")
    lines.append(f"live_risk_chain_ok             : {d['live_risk_chain_ok']}")
    lines.append(f"execution_chain_ok             : {d['execution_chain_ok']}")
    lines.append(f"capital_ladder_chain_ok        : {d['capital_ladder_chain_ok']}")
    lines.append(f"funding_pnl_chain_ok           : {d['funding_pnl_chain_ok']}")
    lines.append(f"telegram_chain_ok              : {d['telegram_chain_ok']}")
    lines.append(f"ai_chain_ok                    : {d['ai_chain_ok']}")
    lines.append(f"blind_isolation_ok             : {d['blind_isolation_ok']}")
    lines.append(f"kill_switch_chain_ok           : {d['kill_switch_chain_ok']}")
    lines.append("-" * 70)
    lines.append(f"no_real_order_sent             : {d['no_real_order_sent']}")
    lines.append(f"fake_transports_used           : {d['fake_transports_used']}")
    lines.append(f"live_trading                   : {d['live_trading']}")
    lines.append(f"exchange_live_orders           : {d['exchange_live_orders']}")
    lines.append(f"trade_authority                : {d['trade_authority']}")
    lines.append(f"ai_trade_authority             : {d['ai_trade_authority']}")
    lines.append(f"ready_for_real_key_validation  : {d['ready_for_real_key_validation']}")
    lines.append("-" * 70)
    for s in d["scenario_results"]:
        lines.append(f"[{s['status']:>4}] {s['scenario']}")
        for blk in s["blockers"]:
            lines.append(f"        BLOCKER: {blk}")
        for w in s["warnings"]:
            lines.append(f"        WARN:    {w}")
    if d["blockers"]:
        lines.append("-" * 70)
        lines.append("BLOCKERS:")
        for b in d["blockers"]:
            lines.append(f"  - {b}")
    if d["warnings"]:
        lines.append("WARNINGS:")
        for w in d["warnings"]:
            lines.append(f"  - {w}")
    lines.append("=" * 70)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    audit = FullSystemSandboxAudit(symbol=args.symbol)
    scenarios = None if args.scenario == "all" else [args.scenario]
    report = audit.run(scenarios)
    d = report.to_dict()
    if args.json:
        print(json.dumps(d, indent=2, sort_keys=True))
    else:
        print(_render_text(d))
    return 1 if report.overall_status == AUDIT_FAIL else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
