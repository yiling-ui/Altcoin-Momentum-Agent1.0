"""LIVE_LIMITED 10U smoke CLI (PR116 - 10U LIVE_LIMITED Launch Pack v0).

A tiny, heavily-gated real-order smoke. The DEFAULT is ``--dry-run`` which
validates + runs the deterministic execution gate but NEVER submits.

Examples
--------
    # Dry run (no real order):
    python scripts/live_limited_smoke.py --dry-run --symbol RAVEUSDT \
        --notional 1 --leverage 1 --json

    # Real order (only when ALL gates pass + explicit confirmation):
    python scripts/live_limited_smoke.py --real-order --symbol RAVEUSDT \
        --notional 1 --leverage 1 \
        --i-understand-this-places-real-order --confirm-code <code> --json

A real order is only ever attempted when ALL of:
  * --real-order AND --i-understand-this-places-real-order AND
    --confirm-code <code> (== $AMA_LIVE_EXECUTION_CONFIRM_CODE),
  * --max-notional-usdt is within the active profile cap,
  * the runtime is an armed LIVE_LIMITED,
  * exchange_live_orders=true AND trade_authority=true AND private trade
    enabled,
and the LiveExecutionGateway clears every gate. It routes through the
SINGLE execution gateway; it writes the ledger; it never retries.

EXIT CODES
----------
  0 = OK (dry-run, or real order sent + accepted)
  1 = WARN (real order requested but blocked / missing flags)
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
from app.live.binance_client import BinanceLiveClient  # noqa: E402
from app.live.binance_execution_adapter import BinanceExecutionAdapter  # noqa: E402
from app.live.execution_gateway import _env_bool  # noqa: E402
from app.live.execution_notifier import LiveExecutionNotifier  # noqa: E402
from app.live.live_limited_arming import LiveLimitedSmoke  # noqa: E402
from app.live.live_runtime import LiveRuntime  # noqa: E402

ENV_CONFIRM_CODE = "AMA_LIVE_EXECUTION_CONFIRM_CODE"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live_limited_smoke",
        description="AMA-RT PR116 LIVE_LIMITED smoke (default --dry-run; no real order).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Dry run (default).")
    parser.add_argument("--real-order", dest="real_order", action="store_true", help="Attempt a REAL order.")
    parser.add_argument(
        "--send-telegram",
        dest="send_telegram",
        action="store_true",
        help=(
            "Push the execution card to Telegram via the independent app.live "
            "sender (respects outbound + allow-list gating). Dry-run pushes a "
            "real_order=false plan/reject card; real-order pushes the "
            "submitted/filled/rejected/failed/blocked card."
        ),
    )
    parser.add_argument(
        "--i-understand-this-places-real-order",
        dest="i_understand",
        action="store_true",
        help="Required acknowledgement flag for --real-order.",
    )
    parser.add_argument("--confirm-code", default="", help=f"Confirmation code (== ${ENV_CONFIRM_CODE}).")
    parser.add_argument("--symbol", default="RAVEUSDT", help="Order symbol.")
    parser.add_argument("--side", default="BUY", choices=["BUY", "SELL"], help="Order side.")
    parser.add_argument("--notional", type=float, default=1.0, help="Planned notional (USDT).")
    parser.add_argument("--leverage", type=float, default=1.0, help="Planned leverage.")
    parser.add_argument(
        "--max-notional-usdt", type=float, default=None, help="Operator max notional cap."
    )
    parser.add_argument("--planned-entry-price", type=float, default=0.0, help="Planned entry price.")
    parser.add_argument("--planned-stop-price", type=float, default=0.0, help="Planned stop price.")
    parser.add_argument(
        "--planned-take-profit-price", type=float, default=0.0, help="Planned take-profit price."
    )
    return parser


def _opt(value: float) -> float | None:
    return float(value) if value and value > 0 else None


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    real_order = bool(args.real_order)
    config = LiveApiConfig.from_env()
    runtime = LiveRuntime(config)

    # Fetch exchangeInfo (and account if private read) best-effort.
    binance_client = BinanceLiveClient(config.binance, runtime_mode=runtime.runtime_mode())
    exchange_info = None
    account_snapshot = None
    try:
        exchange_info = binance_client.get_exchange_info()
    except Exception:
        exchange_info = None
    if (
        config.binance.enable_private_read
        and config.binance.has_credentials
        and not (config.binance.api_key.is_placeholder or config.binance.api_secret.is_placeholder)
    ):
        try:
            account_snapshot = binance_client.get_account()
        except Exception:
            account_snapshot = None

    adapter = BinanceExecutionAdapter(
        config.binance,
        runtime_mode=runtime.runtime_mode(),
        exchange_info=exchange_info,
    )
    # OPTIONAL live Telegram notifier (independent app.live sender). Wired
    # only when --send-telegram is set; it self-gates on outbound_enabled,
    # the chat allow-list, LIVE source, and dedup, so a missing token /
    # disabled outbound simply suppresses (no network contacted).
    notifier = (
        LiveExecutionNotifier.from_config(config, runtime_mode=runtime.runtime_mode())
        if args.send_telegram
        else None
    )
    smoke = LiveLimitedSmoke(config, runtime=runtime, adapter=adapter, notifier=notifier)

    result = smoke.run(
        symbol=args.symbol,
        notional_usdt=float(args.notional),
        leverage=float(args.leverage),
        side=args.side,
        real_order=real_order,
        send_telegram=bool(args.send_telegram),
        i_understand_this_places_real_order=bool(args.i_understand),
        confirm_code=args.confirm_code,
        max_notional_usdt=args.max_notional_usdt,
        exchange_live_orders=_env_bool("AMA_LIVE_EXCHANGE_LIVE_ORDERS", False, None),
        trade_authority=_env_bool("AMA_LIVE_TRADE_AUTHORITY", False, None),
        ai_trade_authority=_env_bool("AMA_LIVE_AI_TRADE_AUTHORITY", False, None),
        account_snapshot=account_snapshot,
        planned_entry_price=_opt(args.planned_entry_price),
        planned_stop_price=_opt(args.planned_stop_price),
        planned_take_profit_price=_opt(args.planned_take_profit_price),
    )
    d = result.to_dict()
    if args.json:
        print(json.dumps(d, indent=2, sort_keys=True))
    else:
        print(json.dumps(d, indent=2, sort_keys=True))
    if real_order and not result.real_order:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
