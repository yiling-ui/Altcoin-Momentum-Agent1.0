"""Phase 11C - Real Binance public market data read-only paper runner.

Boots a :class:`BinancePublicClient` against the real Binance USDT-M
perpetual public-market endpoints, drives the Phase 11C event chain
through the existing Phase 4 Market Data Buffer + Phase 7 Risk Engine
+ Phase 8.5 learning-ready contract, and writes the daily Markdown
report on graceful shutdown.

USAGE
-----

    python -m scripts.run_public_market_paper --duration 1h --symbol-limit 20
    python -m scripts.run_public_market_paper --duration 6h --symbol-limit 20
    python -m scripts.run_public_market_paper --duration 24h --symbol-limit 20
    python -m scripts.run_public_market_paper --duration 2min --symbol-limit 5
    python -m scripts.run_public_market_paper --duration 30s --dry-run

PHASE 11C BOUNDARY
------------------

  - mode = paper
  - live_trading = False
  - right_tail = False
  - llm = False
  - exchange_live_orders = False
  - telegram_outbound_enabled = False
  - binance_private_api_enabled = False
  - no API key, no API secret, no signed endpoint
  - no /fapi/v1/order, no /fapi/v2/account, no /fapi/v2/positionRisk
  - no /fapi/v1/leverage, no /fapi/v1/marginType
  - the four ExchangeClientBase write surfaces remain refused

The runner refuses to start if any of the above is violated by the
resolved config or by the process environment.
"""

from __future__ import annotations

import argparse
import re
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import get_settings  # noqa: E402
from app.core.clock import now_ms  # noqa: E402
from app.core.errors import ExchangeError, SafeModeViolation, SafetyViolation  # noqa: E402
from app.database.connection import DatabaseSet, PHASE2_DATABASES  # noqa: E402
from app.database.migrations import migrate_database_set  # noqa: E402
from app.database.repositories import EventRepository  # noqa: E402
from app.exchanges.binance_public import (  # noqa: E402
    BinancePublicClient,
    DEFAULT_REST_BASE_URL,
    PublicTransport,
)
from app.exchanges.binance_rate_limit import (  # noqa: E402
    BinancePublicRestGovernor,
    RateLimitBackoffActive,
    RateLimitBudgetExceeded,
    RateLimitProtectionError,
    RestGovernorConfig,
)
from app.exports.service import TestDataExportService  # noqa: E402
from app.incidents.repository import IncidentRepository  # noqa: E402
from app.market_data.buffer import MarketDataBuffer  # noqa: E402
from app.market_data.models import MarketDataBufferConfig  # noqa: E402
from app.market_data_public import (  # noqa: E402
    PaperEventChainDriver,
    PublicMarketIngestor,
)
from app.paper_run.config import (  # noqa: E402
    DEFAULT_FORBIDDEN_CRED_ENV_VARS,
    DEFAULT_INSPECTED_ENV_VARS,
    DEFAULT_PAPER_CLOUD_PATH,
    EnvGuardConfig,
    PaperCloudConfig,
)
from app.paper_run.daily_report import DailyReportBuilder  # noqa: E402
from app.paper_run.env_guard import EnvGuard  # noqa: E402
from app.paper_run.safety_assert import assert_paper_cloud_safety  # noqa: E402
from app.risk.engine import RiskEngine  # noqa: E402

# ---------------------------------------------------------------------------
# Public credentials env-var allowlist for refusal.
# ---------------------------------------------------------------------------
PHASE_11C_FORBIDDEN_CRED_ENV_VARS: tuple[str, ...] = tuple(
    sorted(set(DEFAULT_FORBIDDEN_CRED_ENV_VARS))
)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _parse_duration(value: str) -> float:
    """Parse a duration like ``"1h"``, ``"6h"``, ``"24h"``, ``"2min"``, ``"30s"``.

    Returns the duration in seconds. Raises ``argparse.ArgumentTypeError``
    on malformed input.
    """
    if value is None:
        raise argparse.ArgumentTypeError("duration is required")
    text = str(value).strip().lower()
    if not text:
        raise argparse.ArgumentTypeError("duration must not be empty")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(ms|s|sec|secs|m|min|mins|h|hour|hours|d|day|days)?", text)
    if match is None:
        raise argparse.ArgumentTypeError(
            f"unrecognised duration {value!r}; examples: 30s, 2min, 1h, 6h, 24h"
        )
    amount = float(match.group(1))
    unit = match.group(2) or "s"
    if unit in {"ms"}:
        seconds = amount / 1000.0
    elif unit in {"s", "sec", "secs"}:
        seconds = amount
    elif unit in {"m", "min", "mins"}:
        seconds = amount * 60.0
    elif unit in {"h", "hour", "hours"}:
        seconds = amount * 3600.0
    elif unit in {"d", "day", "days"}:
        seconds = amount * 86400.0
    else:
        raise argparse.ArgumentTypeError(f"unrecognised duration unit {unit!r}")
    if seconds <= 0:
        raise argparse.ArgumentTypeError("duration must be > 0")
    return seconds


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_public_market_paper",
        description=(
            "Phase 11C - Real Binance public market data read-only paper. "
            "Connects to public market endpoints only. No API key. No "
            "real order. No live trading. No DeepSeek. No Telegram outbound."
        ),
    )
    p.add_argument(
        "--duration",
        type=_parse_duration,
        default=_parse_duration("1h"),
        help="how long to run; e.g. 1h, 6h, 24h, 2min (default 1h).",
    )
    p.add_argument(
        "--symbol-limit",
        type=int,
        default=5,
        dest="symbol_limit",
        help=(
            "number of top USDT-perpetual symbols to track "
            "(default 5; Phase 11C.1A lowered the default from 20 "
            "after the first 24h test triggered Binance HTTP 429/418)."
        ),
    )
    p.add_argument(
        "--rest-base-url",
        type=str,
        default=DEFAULT_REST_BASE_URL,
        dest="rest_base_url",
        help="Binance public-market REST base URL (default fapi.binance.com).",
    )
    p.add_argument(
        "--symbols",
        type=str,
        default=None,
        help=(
            "explicit comma-separated symbol list; overrides "
            "--symbol-limit and the top-USDT-perpetual scan."
        ),
    )
    p.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=None,
        dest="poll_interval_seconds",
        help="REST poll cadence per symbol (defaults to settings.market_data).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help=(
            "do all wiring + refusal probes but do NOT issue any real REST "
            "call. Useful for CI smoke tests."
        ),
    )
    p.add_argument(
        "--no-banner",
        action="store_false",
        dest="emit_banner",
        default=True,
        help="suppress the boot/exit banner.",
    )
    p.add_argument(
        "--no-daily-report",
        action="store_false",
        dest="write_daily_report",
        default=True,
        help="do not build the daily report on shutdown.",
    )
    p.add_argument(
        "--paper-cloud-config",
        type=str,
        default=None,
        dest="paper_cloud_config",
        help=(
            "path to paper_cloud.yaml. Defaults to app/config/paper_cloud.yaml. "
            "Used to share the env-guard configuration with Phase 11B."
        ),
    )
    p.add_argument(
        "--candidate-detail-limit",
        type=int,
        default=None,
        dest="candidate_detail_limit",
        help=(
            "Phase 11C.1A: maximum number of candidate symbols that may "
            "receive per-loop detail REST calls (depth / aggTrades / "
            "openInterest / premiumIndex). Defaults to "
            "settings.market_data.rest_governor.candidate_detail_limit "
            "(3). PR-A ships no candidate ranking yet, so this caps the "
            "*future* candidate-only path; in PR-A no detail REST is "
            "issued per loop unless --legacy-detail-per-loop is set."
        ),
    )
    p.add_argument(
        "--legacy-detail-per-loop",
        action="store_true",
        dest="legacy_detail_per_loop",
        default=False,
        help=(
            "Phase 11C.1A: re-enable the original 'fetch every detail "
            "endpoint for every symbol every loop' behaviour. OFF by "
            "default because it triggered HTTP 429/418 in the first "
            "24h test. Use only with --dry-run."
        ),
    )
    return p


# ---------------------------------------------------------------------------
# Stub transport (dry-run) - used when no real network is desired
# ---------------------------------------------------------------------------


def _build_dry_run_transport() -> PublicTransport:
    """Return a deterministic, network-free transport.

    The transport answers every allowlisted public endpoint with a tiny
    static payload. It is the test/CI substitute for the stdlib urllib
    default, and lets the runner be exercised end-to-end without any
    real socket.
    """
    from urllib.parse import urlsplit, parse_qs

    def _fetch(url: str) -> Any:
        parts = urlsplit(url)
        path = parts.path
        params = parse_qs(parts.query)
        sym = (params.get("symbol", [None]) or [None])[0]
        ts = now_ms()
        if path == "/fapi/v1/exchangeInfo":
            return {
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "contractType": "PERPETUAL",
                        "status": "TRADING",
                        "filters": [
                            {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                            {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                            {"filterType": "MIN_NOTIONAL", "notional": "5"},
                        ],
                    },
                    {
                        "symbol": "ETHUSDT",
                        "baseAsset": "ETH",
                        "quoteAsset": "USDT",
                        "contractType": "PERPETUAL",
                        "status": "TRADING",
                        "filters": [
                            {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                            {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                            {"filterType": "MIN_NOTIONAL", "notional": "5"},
                        ],
                    },
                ]
            }
        if path == "/fapi/v1/ticker/24hr":
            return [
                {"symbol": "BTCUSDT", "quoteVolume": "1000000000.0"},
                {"symbol": "ETHUSDT", "quoteVolume": "500000000.0"},
            ]
        if path == "/fapi/v1/ticker/bookTicker":
            return {
                "symbol": sym or "BTCUSDT",
                "bidPrice": "100.0",
                "askPrice": "100.1",
                "time": ts,
            }
        if path == "/fapi/v1/depth":
            return {
                "E": ts,
                "T": ts,
                "bids": [["100.0", "1.0"], ["99.9", "2.0"], ["99.8", "3.0"]],
                "asks": [["100.1", "1.0"], ["100.2", "2.0"], ["100.3", "3.0"]],
            }
        if path == "/fapi/v1/aggTrades":
            return [
                {"a": "1", "p": "100.05", "q": "0.5", "T": ts - 1000, "m": False},
                {"a": "2", "p": "100.10", "q": "0.4", "T": ts - 500, "m": True},
            ]
        if path == "/fapi/v1/fundingRate":
            return [{"fundingTime": ts, "fundingRate": "0.0001"}]
        if path == "/fapi/v1/openInterest":
            return {"time": ts, "openInterest": "12345.0"}
        if path == "/fapi/v1/premiumIndex":
            return {
                "symbol": sym or "BTCUSDT",
                "markPrice": "100.05",
                "indexPrice": "100.04",
                "lastFundingRate": "0.0001",
                "nextFundingTime": ts + 8 * 60 * 60 * 1000,
                "time": ts,
            }
        if path == "/fapi/v1/klines":
            return [
                [ts - 60_000, "100.0", "100.2", "99.9", "100.1", "10.0"],
                [ts, "100.1", "100.3", "100.0", "100.2", "12.0"],
            ]
        return {}

    return _fetch


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


@dataclass
class _Phase11CRunStats:
    started_at_ms: int = 0
    finished_at_ms: int = 0
    symbols_tracked: tuple[str, ...] = ()
    iterations: int = 0
    chains_emitted: int = 0
    risk_approved: int = 0
    risk_rejected: int = 0
    learning_ready_attached: int = 0
    snapshots_emitted: int = 0
    ingestion_errors: int = 0
    endpoint_call_counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    # Phase 11C.1A - governor metrics snapshot at shutdown.
    governor_metrics: dict[str, Any] = field(default_factory=dict)
    rate_limit_protection_triggered: bool = False
    rate_limit_ban: bool = False


def _resolve_symbols(
    args: argparse.Namespace,
    *,
    market_data_cfg,
    client: BinancePublicClient,
) -> list[str]:
    """Resolve the symbol set from CLI args + config.

    1. ``--symbols`` wins outright.
    2. ``settings.market_data.explicit_symbols`` next.
    3. Otherwise top-USDT-perpetual via ``client.get_top_usdt_perpetual_symbols``.
    """
    if args.symbols:
        return [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if market_data_cfg.explicit_symbols:
        return [str(s).strip().upper() for s in market_data_cfg.explicit_symbols]
    limit = max(1, int(args.symbol_limit))
    return client.get_top_usdt_perpetual_symbols(limit=limit)


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    settings = get_settings()
    market_data_cfg = settings.market_data
    safety_cfg = settings.safety

    # 1. Phase 1 + Phase 11B safety lock -- assert before doing anything.
    paper_cloud = PaperCloudConfig.load(args.paper_cloud_config)
    safety_report = assert_paper_cloud_safety(
        settings=settings,
        paper_cloud=paper_cloud,
        exchange_client=None,
    )
    if not safety_report.passed:
        print(
            "[AMA-RT][phase11c] safety assertion did not pass; refusing.",
            file=sys.stderr,
        )
        return 2

    # 2. Phase 11C extra safety: market_data + safety sections.
    if not market_data_cfg.read_only:
        raise SafetyViolation(
            "Phase 11C refuses to start: market_data.read_only must be True."
        )
    if market_data_cfg.provider != "binance_public":
        raise SafetyViolation(
            f"Phase 11C refuses to start: market_data.provider must be "
            f"'binance_public'; got {market_data_cfg.provider!r}."
        )
    for flag in (
        "forbid_private_credentials",
        "forbid_signed_endpoints",
        "forbid_trade_endpoints",
        "forbid_account_endpoints",
        "forbid_position_endpoints",
        "forbid_leverage_endpoints",
        "forbid_margin_endpoints",
        "forbid_live_trading",
        "forbid_right_tail",
        "forbid_llm_trade_decisions",
        "forbid_telegram_outbound",
    ):
        if not getattr(safety_cfg, flag):
            raise SafetyViolation(
                f"Phase 11C refuses to start: safety.{flag} must remain True."
            )

    # 3. Env-guard: refuse if any forbidden credential env-var is set.
    env_guard = EnvGuard(
        config=EnvGuardConfig(
            enabled=True,
            refuse_on_dangerous_value=True,
            inspected_env_vars=DEFAULT_INSPECTED_ENV_VARS,
            forbidden_credential_env_vars=PHASE_11C_FORBIDDEN_CRED_ENV_VARS,
        )
    )
    env_report = env_guard.assert_safe()

    # 4. Resolve durations + cadences.
    duration_seconds = float(args.duration)
    poll_interval = (
        float(args.poll_interval_seconds)
        if args.poll_interval_seconds is not None
        else float(market_data_cfg.rest_poll_interval_seconds)
    )
    if poll_interval <= 0:
        poll_interval = 5.0

    # 5. Open the Phase 2 databases + the event repository.
    settings.sqlite_dir.mkdir(parents=True, exist_ok=True)
    dbs = DatabaseSet.open(
        settings.sqlite_dir,
        wal=settings.defaults.database.wal_mode,
        databases=PHASE2_DATABASES,
    )
    migrate_database_set(dbs)
    event_repo = EventRepository(dbs.events, capital_conn=dbs.capital)
    incidents = IncidentRepository(
        incidents_conn=dbs.incidents,
        event_repo=event_repo,
    )

    # 6. Build the rate-limit governor + the public client.
    governor_section = market_data_cfg.rest_governor
    candidate_detail_limit = (
        int(args.candidate_detail_limit)
        if args.candidate_detail_limit is not None
        else int(governor_section.candidate_detail_limit)
    )
    if candidate_detail_limit < 0:
        candidate_detail_limit = 0
    governor = BinancePublicRestGovernor(
        config=RestGovernorConfig(
            weight_budget_per_minute=int(
                governor_section.weight_budget_per_minute
            ),
            soft_weight_ratio=float(governor_section.soft_weight_ratio),
            hard_weight_ratio=float(governor_section.hard_weight_ratio),
            retry_after_default_seconds=int(
                governor_section.retry_after_default_seconds
            ),
            on_429=str(governor_section.on_429),
            on_418=str(governor_section.on_418),
            enabled=bool(governor_section.enabled),
        ),
        event_repo=event_repo,
        protection_hook=incidents,
    )

    transport = _build_dry_run_transport() if args.dry_run else None
    try:
        client = BinancePublicClient(
            rest_base_url=args.rest_base_url,
            transport=transport,
            request_timeout_seconds=float(market_data_cfg.request_timeout_seconds),
            event_repo=event_repo,
            governor=governor,
        )
    except SafeModeViolation as exc:
        print(
            f"[AMA-RT][phase11c] BinancePublicClient refused to start: {exc}",
            file=sys.stderr,
        )
        dbs.close()
        return 2
    client.assert_public_only()
    client.assert_read_only()

    # 7. Build the buffer, ingestor, risk engine, and event-chain driver.
    buffer = MarketDataBuffer(
        exchange=client,
        event_repo=event_repo,
        config=MarketDataBufferConfig(
            market_snapshot_event_emit_enabled=False,
        ),
        source_module="market_data_public.buffer",
    )
    ingestor = PublicMarketIngestor(
        client=client,
        buffer=buffer,
        event_repo=event_repo,
        depth_limit=10,
        trades_limit=100,
        emit_market_snapshot_event=True,
    )
    risk = RiskEngine(settings=settings, event_repo=event_repo)
    chain = PaperEventChainDriver(
        risk_engine=risk,
        event_repo=event_repo,
        public_client=client,
    )

    # 8. Resolve symbols (REST bootstrap: ticker/24hr or exchangeInfo
    #    via the top-USDT-perpetual scan; one-shot, NOT per loop).
    rest_layering_enabled = (
        bool(governor_section.rest_layering_enabled)
        and not bool(args.legacy_detail_per_loop)
    )
    try:
        symbols = _resolve_symbols(
            args, market_data_cfg=market_data_cfg, client=client
        )
    except RateLimitProtectionError as exc:
        print(
            f"[AMA-RT][phase11c] rate-limit protection during bootstrap: {exc}",
            file=sys.stderr,
        )
        client.stop(reason="phase11c_runner_protection_during_bootstrap")
        dbs.close()
        return 2
    except ExchangeError as exc:
        print(
            f"[AMA-RT][phase11c] symbol resolution failed: {exc}",
            file=sys.stderr,
        )
        dbs.close()
        return 1
    if not symbols:
        print(
            "[AMA-RT][phase11c] no symbols resolved; refusing to run.",
            file=sys.stderr,
        )
        dbs.close()
        return 1
    for sym in symbols:
        buffer.track(sym)

    # 9. Set up signal handling for graceful shutdown.
    stop_flag = {"stop": False}

    def _request_stop(signum, frame):  # pragma: no cover - signal handler
        stop_flag["stop"] = True

    try:
        signal.signal(signal.SIGINT, _request_stop)
        signal.signal(signal.SIGTERM, _request_stop)
    except Exception:  # pragma: no cover - some envs disallow signal install
        pass

    stats = _Phase11CRunStats(
        started_at_ms=now_ms(),
        symbols_tracked=tuple(symbols),
    )

    if args.emit_banner:
        _print_banner(
            settings=settings,
            client=client,
            symbols=symbols,
            duration_seconds=duration_seconds,
            poll_interval=poll_interval,
            dry_run=args.dry_run,
            env_report_passed=env_report.passed,
            governor=governor,
            rest_layering_enabled=rest_layering_enabled,
            candidate_detail_limit=candidate_detail_limit,
        )

    # 10. Main loop.
    #
    # Phase 11C.1A REST layering:
    #
    #   * exchangeInfo / ticker/24hr: bootstrap above; not pulled per loop.
    #   * depth / aggTrades / openInterest / premiumIndex / bookTicker:
    #     gated on a candidate ranking. PR-A ships an empty candidate
    #     set so no detail REST call lands per loop. The governor is
    #     wired but its budget should remain near-zero in steady state
    #     (only the bootstrap weight is consumed).
    #
    # ``--legacy-detail-per-loop`` re-enables the original behaviour
    # (every detail endpoint for every symbol every tick). It is OFF
    # by default because that pattern triggered Binance HTTP 429/418
    # in the first 24h test.
    deadline = time.monotonic() + duration_seconds
    try:
        while not stop_flag["stop"] and time.monotonic() < deadline:
            stats.iterations += 1
            chain.begin_scan_batch()

            # PR-A: candidate ranking lands in PR-B. We expose the
            # extension point so the runner shape matches the brief;
            # the empty set keeps detail REST silent.
            candidates: list[str] = []
            if not rest_layering_enabled:
                # Legacy path: behave like Phase 11C pre-1A. Used only
                # for back-compat smoke tests under --dry-run.
                candidates = list(symbols[: candidate_detail_limit or len(symbols)])

            if candidates:
                try:
                    results = ingestor.ingest_many(candidates)
                except RateLimitProtectionError as exc:
                    stats.notes.append(f"rate_limit_protection:{exc}")
                    stats.rate_limit_protection_triggered = True
                    stats.rate_limit_ban = True
                    print(
                        f"[AMA-RT][phase11c] rate-limit protection latched: {exc}",
                        file=sys.stderr,
                    )
                    break
                except (RateLimitBackoffActive, RateLimitBudgetExceeded) as exc:
                    stats.notes.append(f"rate_limit_backoff:{type(exc).__name__}")
                    results = []
                for sym_snap in results:
                    try:
                        chain_result = chain.drive(sym_snap)
                    except Exception as exc:  # pragma: no cover - defensive
                        stats.notes.append(
                            f"chain_error:{sym_snap.symbol}:{type(exc).__name__}"
                        )
                        continue
                    stats.chains_emitted += 1
                    if chain_result.risk_approved:
                        stats.risk_approved += 1
                    else:
                        stats.risk_rejected += 1
                    if chain_result.learning_ready_attached:
                        stats.learning_ready_attached += 1

            stats.snapshots_emitted = ingestor.snapshots_emitted
            stats.ingestion_errors = ingestor.ingestion_errors
            stats.endpoint_call_counts = dict(client.endpoint_call_counts)
            stats.governor_metrics = governor.metrics_payload()
            stats.rate_limit_protection_triggered = (
                bool(governor.in_protection_mode)
                or stats.rate_limit_protection_triggered
            )
            stats.rate_limit_ban = (
                bool(governor.rate_limit_ban) or stats.rate_limit_ban
            )
            # Pin invariants on every loop tick.
            client.assert_public_only()
            # Hard stop if the governor latched into protection mode.
            if governor.in_protection_mode:
                stats.notes.append("rate_limit_protection_mode")
                break
            # Sleep until the next tick. We use small chunks so Ctrl+C
            # is responsive.
            slept = 0.0
            while slept < poll_interval and not stop_flag["stop"]:
                time.sleep(min(0.5, poll_interval - slept))
                slept += 0.5
    except KeyboardInterrupt:  # pragma: no cover - rare
        stats.notes.append("keyboard_interrupt")
    except RateLimitProtectionError as exc:
        stats.notes.append(f"rate_limit_protection:{exc}")
        stats.rate_limit_protection_triggered = True
        stats.rate_limit_ban = True
        print(
            f"[AMA-RT][phase11c] RateLimitProtectionError in main loop: {exc}",
            file=sys.stderr,
        )
    except SafeModeViolation as exc:
        stats.notes.append(f"safe_mode_violation:{exc}")
        print(
            f"[AMA-RT][phase11c] SafeModeViolation in main loop: {exc}",
            file=sys.stderr,
        )
        dbs.close()
        return 2
    finally:
        stats.finished_at_ms = now_ms()
        stats.governor_metrics = governor.metrics_payload()

    # 11. Build the daily report on shutdown.
    daily_report_path = None
    if args.write_daily_report:
        try:
            daily_dir = settings.data_dir / "reports/phase11c"
            daily_dir.mkdir(parents=True, exist_ok=True)
            builder = DailyReportBuilder(
                event_repo=event_repo,
                output_dir=daily_dir,
                filename_template="{date}-phase11c-public-market.md",
            )
            snapshot = builder.build(
                started_at_ms=stats.started_at_ms,
                finished_at_ms=stats.finished_at_ms,
                safety_summary={
                    "trading_mode_paper": settings.trading_mode == "paper",
                    "live_trading_enabled": bool(settings.live_trading_enabled),
                    "right_tail_enabled": bool(settings.right_tail_enabled),
                    "llm_enabled": bool(settings.llm_enabled),
                    "exchange_live_order_enabled": bool(
                        settings.exchange_live_order_enabled
                    ),
                },
                paper_cloud_summary={
                    "phase": "11C.1A",
                    "provider": "binance_public",
                    "rest_base_url": client.rest_base_url,
                    "symbol_limit": int(args.symbol_limit),
                    "symbols_count": len(symbols),
                    "duration_seconds": float(duration_seconds),
                    "iterations": int(stats.iterations),
                    "chains_emitted": int(stats.chains_emitted),
                    "risk_approved": int(stats.risk_approved),
                    "risk_rejected": int(stats.risk_rejected),
                    "learning_ready_attached": int(stats.learning_ready_attached),
                    "snapshots_emitted": int(stats.snapshots_emitted),
                    "ingestion_errors": int(stats.ingestion_errors),
                    "endpoint_call_counts": dict(stats.endpoint_call_counts),
                    "dry_run": bool(args.dry_run),
                    "rest_layering_enabled": bool(rest_layering_enabled),
                    "candidate_detail_limit": int(candidate_detail_limit),
                },
                error_notes=tuple(stats.notes),
                degraded_notes=(),
                rate_limit_metrics=dict(stats.governor_metrics),
                ingestion_errors=int(stats.ingestion_errors),
            )
            daily_report_path = (
                daily_dir / f"{snapshot.date}-phase11c-public-market.md"
            )
        except Exception as exc:  # pragma: no cover - defensive
            print(
                f"[AMA-RT][phase11c] daily report build failed: {exc}",
                file=sys.stderr,
            )

    # 12. Emit a closing banner with the results.
    if args.emit_banner:
        _print_exit_banner(
            stats=stats,
            client=client,
            daily_report_path=daily_report_path,
        )

    client.stop(reason="phase11c_runner_shutdown")
    dbs.close()
    return 2 if stats.rate_limit_protection_triggered else 0


# ---------------------------------------------------------------------------
# Banner helpers
# ---------------------------------------------------------------------------


def _print_banner(
    *,
    settings,
    client: BinancePublicClient,
    symbols: list[str],
    duration_seconds: float,
    poll_interval: float,
    dry_run: bool,
    env_report_passed: bool,
    governor: BinancePublicRestGovernor | None = None,
    rest_layering_enabled: bool = True,
    candidate_detail_limit: int = 0,
) -> None:
    governor_summary = "off"
    if governor is not None:
        cfg = governor.config
        governor_summary = (
            f"on(budget={cfg.weight_budget_per_minute}/min "
            f"soft={cfg.soft_weight_ratio} hard={cfg.hard_weight_ratio} "
            f"on_429={cfg.on_429} on_418={cfg.on_418} "
            f"retry_after_default={cfg.retry_after_default_seconds}s)"
        )
    print(
        "[AMA-RT] Phase 11C - Real Binance Public Market Data Read-Only Paper "
        f"v1.4.0a11c.1a "
        f"mode={settings.trading_mode} "
        f"live_trading={settings.live_trading_enabled} "
        f"right_tail={settings.right_tail_enabled} "
        f"llm={settings.llm_enabled} "
        f"exchange_live_orders={settings.exchange_live_order_enabled} "
        f"telegram_outbound_enabled={settings.telegram_outbound_enabled} "
        f"binance_private_api_enabled=False "
        f"provider=binance_public "
        f"rest_base_url={client.rest_base_url} "
        f"symbols={len(symbols)} "
        f"duration_seconds={int(duration_seconds)} "
        f"poll_interval_seconds={poll_interval} "
        f"rest_layering_enabled={rest_layering_enabled} "
        f"candidate_detail_limit={candidate_detail_limit} "
        f"governor={governor_summary} "
        f"dry_run={dry_run} "
        f"env_guard_passed={env_report_passed}"
    )


def _print_exit_banner(
    *,
    stats: _Phase11CRunStats,
    client: BinancePublicClient,
    daily_report_path: Path | None,
) -> None:
    duration_s = max(
        0, int((stats.finished_at_ms - stats.started_at_ms) // 1000)
    )
    metrics = stats.governor_metrics or {}
    print(
        "[AMA-RT] Phase 11C run finished "
        f"duration_seconds={duration_s} "
        f"iterations={stats.iterations} "
        f"chains_emitted={stats.chains_emitted} "
        f"risk_approved={stats.risk_approved} "
        f"risk_rejected={stats.risk_rejected} "
        f"learning_ready_attached={stats.learning_ready_attached} "
        f"snapshots_emitted={stats.snapshots_emitted} "
        f"ingestion_errors={stats.ingestion_errors} "
        f"public_endpoint_calls={client.total_calls} "
        f"rate_limit_429_count={metrics.get('rate_limit_429_count', 0)} "
        f"rate_limit_418_count={metrics.get('rate_limit_418_count', 0)} "
        f"used_weight_1m_max={metrics.get('used_weight_1m_max', 0)} "
        f"rate_limit_protection_triggered={stats.rate_limit_protection_triggered} "
        f"rate_limit_ban={stats.rate_limit_ban} "
        f"daily_report={daily_report_path or '-'} "
        f"notes={','.join(stats.notes) or '-'}"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
