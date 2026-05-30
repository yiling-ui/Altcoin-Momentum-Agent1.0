"""Telegram operator console runner CLI (PR114).

Runs the AMA-RT live operator console. The console lets an authorised
operator see the system, switch 空盘跑 (LIVE_SHADOW) / request 有资金跑
(LIVE_LIMITED), view account / positions / PnL / risk, and receive
operator cards via Telegram - WITHOUT ever bypassing the Risk Engine,
the Execution Gateway, the Capital Profile, or the kill switch.

USAGE
-----

    python scripts/live_telegram_operator.py --status-json
    python scripts/live_telegram_operator.py --send-test
    python scripts/live_telegram_operator.py --dry-run --once
    python scripts/live_telegram_operator.py --poll
    python scripts/live_telegram_operator.py --command "/status"

SAFETY (enforced by this CLI)
-----------------------------

  1. It NEVER places / cancels / modifies a real order.
  2. It NEVER calls the Binance execution adapter directly.
  3. It NEVER switches to LIVE_LIMITED without the /confirm_live
     handshake; LIVE_SHADOW is the default.
  4. Only allow-listed chat ids may control the system.
  5. Outbound is disabled unless AMA_TELEGRAM_OUTBOUND_ENABLED=true AND
     --dry-run is not set; otherwise messages are SUPPRESSED.
  6. Secrets are always masked / redacted; no token / key is printed.

EXIT CODES
----------

  0 = OK
  1 = WARN (state fail-safe warning / outbound disabled while sending)
  2 = FAIL (could not poll because no transport / token configured)
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
from app.live.telegram_client import _default_transport  # noqa: E402
from app.live.telegram_operator import TelegramOperatorConsole  # noqa: E402
from app.live.telegram_state import LiveOperatorStateStore  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live_telegram_operator",
        description=(
            "AMA-RT PR114 Telegram operator console runner. Never places a "
            "real order; never bypasses the risk / execution gate."
        ),
    )
    parser.add_argument(
        "--status-json",
        action="store_true",
        help="Print a redacted JSON status snapshot and exit.",
    )
    parser.add_argument(
        "--send-test",
        action="store_true",
        help="Send a single operator test card (respects outbound gates).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Poll one batch of updates, process them, then exit.",
    )
    parser.add_argument(
        "--poll",
        action="store_true",
        help="Long-poll updates in a loop (Ctrl-C to stop).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process commands but NEVER send a real outbound message.",
    )
    parser.add_argument(
        "--command",
        default=None,
        help="Process a single command string locally (no network), e.g. '/status'.",
    )
    parser.add_argument(
        "--chat-id",
        default=None,
        help="Chat id to use for --command / --send-test (default: first allowed).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Seconds between --poll batches (default 2.0).",
    )
    parser.add_argument(
        "--state-dir",
        default=None,
        help="Override the live-state directory (default data/live_state).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    return parser


def _build_console(args: argparse.Namespace, *, with_transport: bool) -> TelegramOperatorConsole:
    config = LiveApiConfig.from_env()
    state_store = LiveOperatorStateStore(args.state_dir) if args.state_dir else LiveOperatorStateStore()
    transport = None
    # A real transport is only built when outbound could actually be used
    # (outbound enabled, not dry-run, token present). Otherwise we keep it
    # None so nothing can contact the network.
    if (
        with_transport
        and config.telegram.outbound_enabled
        and not args.dry_run
        and config.telegram.has_token
    ):
        transport = _default_transport()
    return TelegramOperatorConsole(
        config=config,
        state_store=state_store,
        transport=transport,
        dry_run=bool(args.dry_run),
    )


def _default_chat(console: TelegramOperatorConsole, override: str | None) -> str:
    if override:
        return str(override)
    allowed = console.auth.allowed_chat_ids
    return next(iter(sorted(allowed)), "")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --status-json / --command never need a network transport.
    needs_transport = bool(args.poll or args.once or args.send_test)
    console = _build_console(args, with_transport=needs_transport)

    exit_code = 0

    if args.status_json:
        snapshot = console.status_snapshot()
        print(json.dumps(snapshot, indent=2, sort_keys=True))
        if snapshot.get("state_warnings"):
            exit_code = 1
        return exit_code

    if args.command:
        chat = _default_chat(console, args.chat_id)
        handled = console.handle_text(chat, args.command)
        out = handled.to_dict()
        if args.json:
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(handled.result.text if handled.result else f"unauthorized:{handled.reason}")
        if not handled.authorized or (handled.result and not handled.result.ok):
            exit_code = 1
        return exit_code

    if args.send_test:
        chat = _default_chat(console, args.chat_id)
        result = console.send_test_message(chat)
        out = result.to_dict()
        if args.json:
            print(json.dumps(out, indent=2, sort_keys=True))
        else:
            print(f"send-test: sent={result.sent} suppressed={result.suppressed} detail={result.detail}")
        if result.suppressed:
            exit_code = 1
        return exit_code

    if args.once or args.poll:
        if console.handler is None:  # pragma: no cover - defensive
            return 2
        config = LiveApiConfig.from_env()
        if not config.telegram.has_token:
            print(json.dumps({"error": "MISSING_TOKEN", "no_real_order_sent": True}))
            return 2

        def _run_batch() -> int:
            handled = console.poll_once()
            for h in handled:
                line = h.result.text if (h.authorized and h.result) else f"unauthorized:{h.reason}"
                print(line)
            return len(handled)

        if args.once:
            _run_batch()
            return exit_code

        # --poll loop.
        try:
            while True:
                _run_batch()
                time.sleep(max(0.1, float(args.poll_interval)))
        except KeyboardInterrupt:  # pragma: no cover
            print("operator console stopped.")
        return exit_code

    # Default: print the status snapshot.
    snapshot = console.status_snapshot()
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
