"""LIVE_SHADOW runner CLI (PR116 - 10U LIVE_LIMITED Launch Pack v0).

Runs the real-market shadow loop (*空盘跑*). It reads live Binance public +
private-read data, builds operator cards (+ optional AI briefing), and can
push them to Telegram. It NEVER places a real order.

Examples
--------
    python scripts/live_shadow_run.py --once --json
    python scripts/live_shadow_run.py --loop --interval-seconds 60
    python scripts/live_shadow_run.py --once --send-telegram

Every run carries ``real_order=false`` and ``no_real_order_sent=true``.

EXIT CODES
----------
  0 = OK (shadow ran; nothing sent)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.live.api_config import LiveApiConfig  # noqa: E402
from app.live.binance_client import BinanceLiveClient  # noqa: E402
from app.live.live_runtime import LiveRuntime  # noqa: E402
from app.live.live_shadow_runner import LiveShadowRunner  # noqa: E402
from app.live.telegram_client import TelegramLiveClient  # noqa: E402
from app.live.telegram_formatters import render_card  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live_shadow_run",
        description="AMA-RT PR116 LIVE_SHADOW runner (空盘跑; never sends a real order).",
    )
    parser.add_argument("--once", action="store_true", help="Run one shadow iteration.")
    parser.add_argument("--loop", action="store_true", help="Run repeatedly until interrupted.")
    parser.add_argument(
        "--interval-seconds", type=int, default=60, help="Loop interval (default 60s)."
    )
    parser.add_argument(
        "--max-iterations", type=int, default=0, help="Loop iteration cap (0 = unlimited)."
    )
    parser.add_argument("--send-telegram", action="store_true", help="Push cards to Telegram.")
    parser.add_argument("--with-ai-briefing", action="store_true", help="Build a DeepSeek briefing.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser


def _build_telegram_sender(config: LiveApiConfig):
    """Build a card sender that respects every outbound gate; or None."""
    tg = config.telegram
    if not (tg.outbound_enabled and tg.has_token and tg.allowed_chat_ids):
        return None
    client = TelegramLiveClient(tg)
    chat_id = tg.allowed_chat_ids[0]

    def _send(card: dict) -> bool:
        result = client.send_test_message(chat_id, render_card(card))
        return bool(getattr(result, "sent", False))

    return _send


def _render_text(d: dict) -> str:
    lines = ["=" * 60, "AMA-RT PR116 LIVE_SHADOW run (空盘跑)", "=" * 60]
    lines.append(f"runtime_mode        : {d['runtime_mode']}")
    lines.append(f"capital_profile_id  : {d['capital_profile_id']}")
    lines.append(f"account_equity      : {d['account_equity_usdt']}")
    lines.append(f"usable_live_capital : {d['usable_live_capital_usdt']}")
    lines.append(f"open_positions      : {d['open_position_count']}")
    lines.append(f"ai_briefing_status  : {d['ai_briefing_status']}")
    lines.append(f"telegram_sent       : {d['telegram_sent_count']}")
    lines.append(f"telegram_suppressed : {d['telegram_suppressed_count']}")
    lines.append(f"real_order          : {d['real_order']}")
    lines.append(f"no_real_order_sent  : {d['no_real_order_sent']}")
    if d["warnings"]:
        lines.append(f"warnings            : {d['warnings']}")
    lines.append("=" * 60)
    return "\n".join(lines)


def _run_once(runner: LiveShadowRunner, args: argparse.Namespace) -> dict:
    result = runner.run_once(
        send_telegram=args.send_telegram,
        with_ai_briefing=args.with_ai_briefing,
        ai_dry_run=True,
    )
    return result.to_dict()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not (args.once or args.loop):
        args.once = True
    config = LiveApiConfig.from_env()
    runtime = LiveRuntime(config)
    binance_client = BinanceLiveClient(config.binance, runtime_mode=runtime.runtime_mode())
    runner = LiveShadowRunner(
        config,
        runtime=runtime,
        binance_client=binance_client,
        telegram_sender=_build_telegram_sender(config) if args.send_telegram else None,
    )

    if args.loop:
        iterations = 0
        try:
            while True:
                d = _run_once(runner, args)
                print(json.dumps(d, sort_keys=True) if args.json else _render_text(d))
                iterations += 1
                if args.max_iterations and iterations >= args.max_iterations:
                    break
                time.sleep(max(1, int(args.interval_seconds)))
        except KeyboardInterrupt:  # pragma: no cover
            print("shadow loop interrupted; exiting cleanly.")
        return 0

    d = _run_once(runner, args)
    print(json.dumps(d, indent=2, sort_keys=True) if args.json else _render_text(d))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
