"""Operator-facing entry point for Historical Data Ingestion /
Backfill v0 (Phase 11C.1D-D-H / PR101).

This script reads **local files only**, parses them into the PR95
record types, builds the data / universe manifests + coverage / gap
reports, and writes every artefact under ``--output-root``. It NEVER
downloads data, NEVER reaches a network, NEVER contacts the Binance
private API, NEVER places a real order, NEVER publishes to a real
Telegram channel, and NEVER fabricates real market data.

If ``--input-root`` does not exist or carries no data, the runner
returns ``INSUFFICIENT_EVIDENCE`` and writes the corresponding
report - it does NOT invent data. A deterministic fixture is produced
ONLY when ``--fixture-mode`` is passed explicitly, and every fixture
record / output is clearly marked synthetic.

Hard safety boundary (Phase 11C.1D-D-H / PR101):

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
  - ai_trade_authority = False
  - trade_authority = False
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
  - present a coverage report as a strategy-effectiveness conclusion
  - authorise live trading, auto-tuning, the 30D / 60D / 90D / 2Y
    runner, or Phase 12

Usage:

    python -m scripts.run_historical_data_ingestion \
        --input-root data/historical_raw \
        --output-root data/historical_market_store \
        --start-time 2026-05-01T00:00:00Z \
        --end-time   2026-05-03T00:00:00Z \
        --symbols BTCUSDT,ETHUSDT \
        --intervals 1m,5m \
        --source-type MANUAL_FIXTURE_FILE \
        --default-availability-lag-seconds 0

Pass ``--fixture-mode`` to generate a deterministic synthetic dataset
(for smoke / wiring tests only); without it, missing input yields an
``INSUFFICIENT_EVIDENCE`` report and never fake data.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.sim import (
    HistoricalDataIngestion,
    HistoricalDataIngestionConfig,
    HistoricalDataSourceType,
)


def _parse_iso(value: str) -> datetime:
    s = value.strip()
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_historical_data_ingestion",
        description=(
            "Historical Data Ingestion / Backfill v0 "
            "(Phase 11C.1D-D-H / PR101). File-based, sandbox-only, "
            "paper-only, Phase 12 = FORBIDDEN. Reads local files only; "
            "never downloads data; never fabricates real market data."
        ),
    )
    p.add_argument(
        "--input-root",
        default="data/historical_raw",
        help="directory to read historical raw files from",
    )
    p.add_argument(
        "--output-root",
        default="data/historical_market_store",
        help="directory to write manifests / reports / records into",
    )
    p.add_argument("--start-time", required=True, help="ISO-8601 UTC")
    p.add_argument("--end-time", required=True, help="ISO-8601 UTC")
    p.add_argument(
        "--symbols",
        default="",
        help="comma-separated symbols (e.g. BTCUSDT,ETHUSDT)",
    )
    p.add_argument(
        "--intervals",
        default="1m,5m",
        help="comma-separated kline intervals (v0: subset of 1m,5m)",
    )
    p.add_argument(
        "--source-type",
        default=HistoricalDataSourceType.MANUAL_FIXTURE_FILE,
        choices=sorted(HistoricalDataSourceType.ALLOWED),
        help="public / file source type (never a private endpoint)",
    )
    p.add_argument(
        "--default-availability-lag-seconds",
        type=float,
        default=0.0,
        help=(
            "publication lag added to event/close time to derive "
            "available_at (never derived from ingested_at)"
        ),
    )
    p.add_argument(
        "--fixture-mode",
        action="store_true",
        help=(
            "generate a deterministic SYNTHETIC dataset (smoke / "
            "wiring only); NOT real market data"
        ),
    )
    p.add_argument(
        "--no-funding",
        action="store_true",
        help="skip funding-rate ingestion",
    )
    p.add_argument(
        "--no-open-interest",
        action="store_true",
        help="skip open-interest ingestion",
    )
    p.add_argument(
        "--no-ticker-24h",
        action="store_true",
        help="skip 24h ticker ingestion",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_argparser().parse_args(argv)

    config = HistoricalDataIngestionConfig(
        input_root=args.input_root,
        output_root=args.output_root,
        start_time=_parse_iso(args.start_time),
        end_time=_parse_iso(args.end_time),
        symbols=tuple(_parse_csv(args.symbols)),
        intervals=tuple(_parse_csv(args.intervals)) or ("1m", "5m"),
        include_funding=not args.no_funding,
        include_open_interest=not args.no_open_interest,
        include_ticker_24h=not args.no_ticker_24h,
        default_availability_lag_seconds=(
            args.default_availability_lag_seconds
        ),
        source_type=args.source_type,
        fixture_mode=bool(args.fixture_mode),
    )

    engine = HistoricalDataIngestion(config)
    result = engine.write_outputs()

    manifest = result.manifest
    summary: Dict[str, Any] = {
        "phase": (
            "Phase 11C.1D-D-H / PR101 / Historical Data Ingestion / "
            "Backfill v0"
        ),
        "status": result.status,
        "ingested_record_count": result.ingested_record_count,
        "skipped_record_count": result.skipped_record_count,
        "rejected_record_count": result.rejected_record_count,
        "manifest_id": (
            manifest.manifest_id if manifest is not None else None
        ),
        "data_manifest_hash": (
            manifest.data_manifest_hash
            if manifest is not None
            else None
        ),
        "universe_manifest_hash": (
            result.universe_manifest.universe_manifest_hash
            if result.universe_manifest is not None
            else None
        ),
        "fixture_mode": bool(args.fixture_mode),
        "coverage_report_path": result.coverage_report_path,
        "data_gap_report_path": result.data_gap_report_path,
        "records_path": result.records_path,
        "warnings": list(result.warnings),
        "next_allowed_step": result.next_allowed_step,
        # Hard-pinned safety markers:
        "live_trading": False,
        "exchange_live_orders": False,
        "binance_private_api_enabled": False,
        "telegram_outbound_enabled": False,
        "telegram_live_command_authority": False,
        "ai_trade_authority": False,
        "trade_authority": False,
        "auto_tuning_allowed": False,
        "phase_12_forbidden": True,
        "is_strategy_effectiveness_conclusion": False,
        "this_authorises_live_trading": False,
        "this_authorises_auto_tuning": False,
        "this_authorises_real_telegram": False,
        "this_authorises_binance_private_api": False,
        "this_authorises_30d_60d_90d_2y_runner": False,
        "this_authorises_phase_12": False,
    }
    print(json.dumps(summary, sort_keys=True, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
