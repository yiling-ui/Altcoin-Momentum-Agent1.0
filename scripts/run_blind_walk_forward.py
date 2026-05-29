"""Operator-facing entry point for the strict blind walk-forward
runner v0 (Phase 11C.1D-D-G / PR100).

This script wires PR94..PR99 substrate together and runs the strict
blind walk-forward orchestrator end-to-end, writing every required
artefact under ``data/reports/blind_walk_forward/<run_id>/``.

Hard safety boundary (Phase 11C.1D-D-G / PR100):

  - mode = historical_blind_sim_live
  - sandbox_only = True
  - simulated_only = True
  - no_live_order = True
  - live_trading = False
  - exchange_live_orders = False
  - binance_private_api_enabled = False
  - signed_endpoint_reachable = False
  - private_websocket_reachable = False
  - account_endpoint_reachable = False
  - order_endpoint_reachable = False
  - position_endpoint_reachable = False
  - leverage_endpoint_reachable = False
  - margin_endpoint_reachable = False
  - real_exchange_order_path = False
  - real_capital = False
  - telegram_outbound_enabled = False
  - telegram_live_command_authority = False
  - telegram_production_channel_enabled = False
  - ai_trade_authority = False
  - trade_authority = False
  - auto_tuning_inside_blind_window = False
  - auto_tuning_allowed = False
  - phase_12_forbidden = True

This script MUST NOT and CANNOT:

  - import app.risk / app.execution / app.exchanges / app.telegram /
    app.config
  - call DeepSeek / LLM / Telegram / Binance private API / any
    network
  - place a real exchange order
  - publish to a real Telegram channel
  - patch any runtime config / threshold / symbol limit / candidate
    pool / regime weight / strategy parameter
  - authorise live trading, auto-tuning, or Phase 12

Usage:

    python -m scripts.run_blind_walk_forward \
        --train-start 2026-01-01T00:00:00+00:00 \
        --train-end   2026-01-08T00:00:00+00:00 \
        --blind-start 2026-01-08T00:00:00+00:00 \
        --blind-end   2026-01-15T00:00:00+00:00 \
        --reference-window 60d \
        --report-root data/reports/blind_walk_forward \
        --code-commit "$(git rev-parse HEAD)"

The script is **strategy-less** at v0: it ships no decision callback
and no AI hot path. The ledger is therefore typically empty and the
score taxonomy resolves to ``INSUFFICIENT_EVIDENCE`` — exactly the
contract for a substrate-only orchestrator. Downstream operator
checkpoint runs may inject a deterministic decision callback via the
public Python API; doing so is **not** the responsibility of PR100.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.sim import (
    BlindWalkForwardRunner,
    BlindWalkForwardRunnerConfig,
    BlindWalkForwardWindow,
    HistoricalMarketStore,
    MockExchange,
    ReplayFeedProvider,
    ReplayFeedProviderConfig,
    SimulatedCapitalConfig,
    SimulatedCapitalFlowEngine,
    SimulationClock,
    TelegramSandboxOutbox,
    TelegramSandboxOutboxConfig,
)


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_blind_walk_forward",
        description=(
            "Strict blind walk-forward runner v0 "
            "(Phase 11C.1D-D-G / PR100). Paper-only, sandbox-only, "
            "Phase 12 = FORBIDDEN."
        ),
    )
    p.add_argument(
        "--train-start", required=True, help="ISO-8601 UTC"
    )
    p.add_argument("--train-end", required=True, help="ISO-8601 UTC")
    p.add_argument(
        "--blind-start", required=True, help="ISO-8601 UTC"
    )
    p.add_argument("--blind-end", required=True, help="ISO-8601 UTC")
    p.add_argument(
        "--reference-window",
        default="60d",
        help="descriptive reference window (default '60d')",
    )
    p.add_argument(
        "--report-root",
        default="data/reports/blind_walk_forward",
        help="directory to write report artefacts under",
    )
    p.add_argument(
        "--run-id",
        default=None,
        help="optional fixed run_id (otherwise auto-derived)",
    )
    p.add_argument(
        "--code-commit",
        default="unknown",
        help="git commit / build id to pin onto the manifest",
    )
    p.add_argument(
        "--base-clock-step",
        default="1m",
        help=(
            "base simulation clock step (default '1m'); v0 must be "
            ">= 1m"
        ),
    )
    p.add_argument(
        "--initial-capital",
        type=float,
        default=10_000.0,
        help="simulated initial capital",
    )
    p.add_argument(
        "--no-ai-post-window-summary",
        action="store_true",
        help="disable the offline post-window AI commentary template",
    )
    return p


def main(argv: List[str] = None) -> int:
    args = _build_argparser().parse_args(argv)
    train_start = _parse_iso(args.train_start)
    train_end = _parse_iso(args.train_end)
    blind_start = _parse_iso(args.blind_start)
    blind_end = _parse_iso(args.blind_end)

    window = BlindWalkForwardWindow(
        train_start=train_start,
        train_end=train_end,
        blind_start=blind_start,
        blind_end=blind_end,
        reference_window=args.reference_window,
    )

    # Build empty substrate. Downstream operator runs that want to
    # populate the store / pin a real strategy callback should invoke
    # the Python API directly; this entry point exposes the v0
    # substrate-only orchestration loop.
    store = HistoricalMarketStore()
    clock = SimulationClock(
        start_time_utc=blind_start,
        end_time_utc=blind_end,
        monotonic_forward_only=True,
    )
    provider = ReplayFeedProvider(
        store=store,
        clock=clock,
        config=ReplayFeedProviderConfig(
            start_time=blind_start,
            end_time=blind_end,
            step_interval=timedelta(seconds=60),
            allow_reemit=False,
            include_asof_universe=True,
        ),
    )
    capital = SimulatedCapitalFlowEngine(
        config=SimulatedCapitalConfig(
            initial_capital=float(args.initial_capital)
        )
    )
    exchange = MockExchange()
    target_root = Path(args.report_root)
    target_root.mkdir(parents=True, exist_ok=True)
    telegram = TelegramSandboxOutbox(
        config=TelegramSandboxOutboxConfig(
            output_jsonl_path=str(
                target_root / "telegram_sandbox.jsonl"
            ),
            output_markdown_path=str(
                target_root / "telegram_sandbox.md"
            ),
        )
    )

    runner = BlindWalkForwardRunner(
        config=BlindWalkForwardRunnerConfig(
            window=window,
            base_clock_step=args.base_clock_step,
            code_commit=args.code_commit,
            run_id=args.run_id,
            report_root=str(target_root),
            ai_post_window_summary_enabled=(
                not args.no_ai_post_window_summary
            ),
        ),
        replay_provider=provider,
        capital_flow=capital,
        mock_exchange=exchange,
        telegram_sandbox=telegram,
    )

    result: Dict[str, Any] = runner.run()

    # Operator-facing summary.
    score = result.get("score") or {}
    paths = result.get("paths") or {}
    summary = {
        "phase": "Phase 11C.1D-D-G / PR100 / Blind Walk-forward Runner v0",
        "run_id": (result.get("manifest") or {}).get("run_id"),
        "status": score.get("status"),
        "sample_count": score.get("sample_count"),
        "closed_trade_count": score.get("closed_trade_count"),
        "violations_count": score.get(
            "no_lookahead_violation_count"
        ),
        "failure_ledger_entry_count": score.get(
            "failure_ledger_entry_count"
        ),
        "live_trading": False,
        "exchange_live_orders": False,
        "binance_private_api_enabled": False,
        "telegram_outbound_enabled": False,
        "telegram_live_command_authority": False,
        "ai_trade_authority": False,
        "trade_authority": False,
        "auto_tuning_inside_blind_window": False,
        "auto_tuning_allowed": False,
        "phase_12_forbidden": True,
        "next_allowed_step": (
            "blind_walk_forward_operator_evidence_run_or_checkpoint"
        ),
        "this_authorises_live_trading": False,
        "this_authorises_auto_tuning": False,
        "this_authorises_real_telegram": False,
        "this_authorises_binance_private_api": False,
        "this_authorises_phase_12": False,
        "paths": paths,
    }
    print(json.dumps(summary, sort_keys=True, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
