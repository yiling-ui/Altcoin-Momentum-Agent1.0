"""Live execution gateway smoke CLI (PR113 - Live Execution v0).

Three modes, NONE of which send a real order by default:

  1. Permission-only (the 15-point gate, no normalization HTTP):

       python scripts/live_execution_smoke.py --permission-check --json

  2. Dry order validation (normalize + validate against exchangeInfo if a
     snapshot is available; never submits):

       python scripts/live_execution_smoke.py --dry-run-order \
           --symbol RAVEUSDT --side BUY --notional 1 --leverage 1 --json

  3. Real order submission - BLOCKED unless EVERY gate is true AND the
     operator passes all three explicit confirmation flags:

       python scripts/live_execution_smoke.py --real-order \
           --i-understand-this-places-real-order --confirm-code <code> ...

SAFETY (enforced by this CLI)
-----------------------------
  - The DEFAULT path NEVER sends an order (``no_real_order_sent=true``).
  - A real order is only ever attempted when ALL of:
      * --real-order AND --i-understand-this-places-real-order AND
        --confirm-code <code> are supplied,
      * the confirm code equals ``AMA_LIVE_EXECUTION_CONFIRM_CODE``,
      * the execution gate allows it (every flag true).
    In PR113 the gate flags default False, so the real-order path stays
    blocked unless the operator has explicitly armed the environment.
  - Secrets are always masked; no key / secret / token / signature
    is printed.

EXIT CODES
----------
  0 = OK (safe; nothing sent)
  1 = WARN (permission denied / real order requested but blocked / missing flags)
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
from app.live.binance_execution_adapter import BinanceExecutionAdapter  # noqa: E402
from app.live.capital_profile import get_profile  # noqa: E402
from app.live.execution_gateway import (  # noqa: E402
    ExecutionPermissionContext,
    LiveExecutionGateway,
    authorize_real_order,
    evaluate_execution_permission,
)
from app.live.execution_models import (  # noqa: E402
    LiveExecutionStatus,
    LiveOrderIntent,
    OrderSide,
    OrderType,
    generate_client_order_id,
)
from app.live.live_risk_engine import (  # noqa: E402
    LiveOrderIntent as RiskIntent,
    evaluate_live_order_risk,
)

# The env var holding the expected real-order confirmation code.
ENV_CONFIRM_CODE = "AMA_LIVE_EXECUTION_CONFIRM_CODE"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live_execution_smoke",
        description=(
            "AMA-RT PR113 live execution gateway smoke (default sends NO real order)."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    parser.add_argument(
        "--permission-check", action="store_true", help="Run the execution gate only."
    )
    parser.add_argument(
        "--dry-run-order",
        action="store_true",
        help="Normalize + validate an order against exchangeInfo (never submits).",
    )
    parser.add_argument(
        "--real-order",
        action="store_true",
        help="Attempt a REAL order (blocked unless all gates + confirmation flags).",
    )
    parser.add_argument(
        "--i-understand-this-places-real-order",
        dest="i_understand",
        action="store_true",
        help="Required acknowledgement flag for --real-order.",
    )
    parser.add_argument(
        "--confirm-code",
        default="",
        help=f"Confirmation code; must equal ${ENV_CONFIRM_CODE}.",
    )
    parser.add_argument("--symbol", default="RAVEUSDT", help="Order symbol.")
    parser.add_argument("--side", default="BUY", choices=["BUY", "SELL"], help="Order side.")
    parser.add_argument("--order-type", default="MARKET", help="Order type.")
    parser.add_argument("--notional", type=float, default=1.0, help="Planned notional (USDT).")
    parser.add_argument("--quantity", type=float, default=0.0, help="Order quantity (base).")
    parser.add_argument("--price", type=float, default=0.0, help="Limit price (0 = none).")
    parser.add_argument("--stop-price", type=float, default=0.0, help="Stop price (0 = none).")
    parser.add_argument("--leverage", type=float, default=1.0, help="Planned leverage.")
    parser.add_argument("--reduce-only", action="store_true", help="Reduce-only order.")
    parser.add_argument(
        "--planned-entry-price", type=float, default=0.0, help="Planned entry price."
    )
    parser.add_argument(
        "--planned-stop-price", type=float, default=0.0, help="Planned stop price."
    )
    parser.add_argument(
        "--planned-take-profit-price", type=float, default=0.0, help="Planned TP price."
    )
    return parser


def _opt_price(value: float) -> float | None:
    return float(value) if value and value > 0 else None


def _build_intent(config: LiveApiConfig, args: argparse.Namespace) -> LiveOrderIntent:
    """Build a LIVE-sourced order intent from CLI args."""
    return LiveOrderIntent(
        symbol=args.symbol,
        side=OrderSide(args.side),
        order_type=OrderType(str(args.order_type).upper()),
        quantity=float(args.quantity),
        notional_usdt=float(args.notional),
        price=_opt_price(args.price),
        stop_price=_opt_price(args.stop_price),
        reduce_only=bool(args.reduce_only),
        planned_entry_price=_opt_price(args.planned_entry_price),
        planned_stop_price=_opt_price(args.planned_stop_price),
        planned_take_profit_price=_opt_price(args.planned_take_profit_price),
        planned_leverage=float(args.leverage),
        exit_plan_present=bool(args.planned_take_profit_price > 0),
        stop_plan_present=bool(args.planned_stop_price > 0),
        client_order_id=generate_client_order_id(),
        source=OrderSource.LIVE,
        runtime_mode=config.live_runtime_mode,
        capital_profile_id=config.capital_profile_id,
        opportunity_id="smoke",
        risk_decision_id="smoke",
    )


def _build_risk_decision(config: LiveApiConfig, args: argparse.Namespace, context):
    """Build a DRY risk decision (PR112). It is real_order_allowed=False until
    explicitly authorised by the fully-armed context."""
    risk_intent = RiskIntent(
        symbol=args.symbol,
        side="LONG" if args.side == "BUY" else "SHORT",
        planned_entry_price=float(args.planned_entry_price or args.price or 0.0),
        planned_notional_usdt=float(args.notional),
        planned_leverage=float(args.leverage),
        planned_stop_price=_opt_price(args.planned_stop_price),
        planned_take_profit_price=_opt_price(args.planned_take_profit_price),
        exit_plan_present=bool(args.planned_take_profit_price > 0),
        stop_plan_present=bool(args.planned_stop_price > 0),
        candidate_stage="smoke",
        runtime_mode=config.live_runtime_mode,
        source=OrderSource.LIVE,
    )
    decision = evaluate_live_order_risk(
        risk_intent,
        None,  # no real account snapshot in the smoke CLI
        get_profile(config.capital_profile_id),
        runtime_mode=config.live_runtime_mode,
    )
    return authorize_real_order(decision, context)


def build_report(
    config: LiveApiConfig,
    args: argparse.Namespace,
    *,
    adapter: BinanceExecutionAdapter | None = None,
    environ: dict | None = None,
) -> dict:
    """Build the read-only smoke report. NEVER sends an order by default."""
    context = ExecutionPermissionContext.from_config(config, environ=environ)
    intent = _build_intent(config, args)
    risk_decision = _build_risk_decision(config, args, context)

    # Order normalization (dry-run mode): only if an exchangeInfo snapshot
    # is available on the adapter. We NEVER fetch over the network here.
    order_normalization_result: dict = {"status": "NOT_REQUESTED"}
    validation = None
    if (args.dry_run_order or args.real_order) and adapter is not None and adapter.exchange_info is not None:
        validation = adapter.validate_order_against_exchange_info(intent)
        order_normalization_result = validation.to_dict()
    elif args.dry_run_order or args.real_order:
        order_normalization_result = {
            "status": "SKIPPED_NO_EXCHANGE_INFO",
            "note": (
                "no exchangeInfo snapshot available offline; the gateway "
                "would fetch + validate before any real submission."
            ),
        }

    decision = evaluate_execution_permission(
        intent, risk_decision, context, validation=validation
    )

    no_real_order_sent = True
    submit_result = None
    real_order_blocked_reason = None

    # ---- Real-order path: triple confirmation + full gate required ----
    if args.real_order:
        env = environ if environ is not None else {}
        import os

        expected_code = (env.get(ENV_CONFIRM_CODE) or os.environ.get(ENV_CONFIRM_CODE) or "").strip()
        confirm_ok = bool(args.confirm_code) and bool(expected_code) and args.confirm_code == expected_code
        flags_ok = bool(args.i_understand) and confirm_ok
        if not flags_ok:
            real_order_blocked_reason = "missing_or_invalid_confirmation_flags"
        elif not decision.allowed:
            real_order_blocked_reason = decision.reject_reason
        elif adapter is None:
            real_order_blocked_reason = "no_adapter_available"
        else:
            # Every gate + every confirmation flag is satisfied. Submit.
            gateway = LiveExecutionGateway(adapter=adapter)
            submit_result = gateway.submit_order(
                intent, risk_decision, context, validation=validation
            )
            no_real_order_sent = not (
                submit_result.is_real_order
                and submit_result.status
                not in (LiveExecutionStatus.BLOCKED, LiveExecutionStatus.FAILED)
            )

    report = {
        "mode": _mode_label(args),
        "execution_permission": decision.allowed,
        "reject_reason": decision.reject_reason,
        "reject_reasons": list(decision.reject_reasons),
        "exchange_live_orders": context.exchange_live_orders,
        "trade_authority": context.trade_authority,
        "ai_trade_authority": context.ai_trade_authority,
        "live_limited_confirmed": context.live_limited_confirmed,
        "kill_switch_active": context.kill_switch_active,
        "runtime_mode": config.live_runtime_mode.value,
        "capital_profile_id": config.capital_profile_id.value,
        "private_trade_enabled": config.binance.enable_private_trade,
        "order_normalization_result": order_normalization_result,
        "client_order_id": intent.client_order_id,
        "no_real_order_sent": no_real_order_sent,
        "real_order_blocked_reason": real_order_blocked_reason,
        "submit_result": submit_result.to_dict() if submit_result is not None else None,
        # PR113 safety markers.
        "phase_12_forbidden": True,
        "binance_private_trade_enabled_by_config": config.binance.enable_private_trade,
    }
    return report


def _mode_label(args: argparse.Namespace) -> str:
    if args.real_order:
        return "real_order"
    if args.dry_run_order:
        return "dry_run_order"
    return "permission_check"


def _render_text(report: dict) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("AMA-RT PR113 Live Execution Gateway Smoke (no real order by default)")
    lines.append("=" * 60)
    lines.append(f"mode                      : {report['mode']}")
    lines.append(f"execution_permission      : {report['execution_permission']}")
    lines.append(f"reject_reason             : {report['reject_reason']}")
    lines.append(f"runtime_mode              : {report['runtime_mode']}")
    lines.append(f"capital_profile_id        : {report['capital_profile_id']}")
    lines.append(f"exchange_live_orders      : {report['exchange_live_orders']}")
    lines.append(f"trade_authority           : {report['trade_authority']}")
    lines.append(f"ai_trade_authority        : {report['ai_trade_authority']}")
    lines.append(f"live_limited_confirmed    : {report['live_limited_confirmed']}")
    lines.append(f"kill_switch_active        : {report['kill_switch_active']}")
    lines.append(f"private_trade_enabled     : {report['private_trade_enabled']}")
    lines.append(f"no_real_order_sent        : {report['no_real_order_sent']}")
    if report.get("real_order_blocked_reason"):
        lines.append(f"real_order_blocked_reason : {report['real_order_blocked_reason']}")
    lines.append("-" * 60)
    lines.append("order_normalization_result:")
    lines.append(json.dumps(report["order_normalization_result"], indent=2, sort_keys=True))
    lines.append("=" * 60)
    return "\n".join(lines)


def _exit_code(report: dict) -> int:
    if report["mode"] == "real_order" and report.get("real_order_blocked_reason"):
        return 1
    if not report["execution_permission"] and report["mode"] != "dry_run_order":
        # permission-check default is expected to be blocked in PR113.
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not (args.permission_check or args.dry_run_order or args.real_order):
        args.permission_check = True
    config = LiveApiConfig.from_env()
    report = build_report(config, args)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_render_text(report))
    return _exit_code(report)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
