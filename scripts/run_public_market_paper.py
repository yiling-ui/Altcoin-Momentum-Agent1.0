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
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import get_settings  # noqa: E402
from app.core.clock import now_ms  # noqa: E402
from app.core.errors import ExchangeError, SafeModeViolation, SafetyViolation  # noqa: E402
from app.database.connection import DatabaseSet, PHASE2_DATABASES  # noqa: E402
from app.database.migrations import migrate_database_set  # noqa: E402
from app import __version__  # noqa: E402
from app.database.repositories import EventRepository  # noqa: E402
from app.exchanges.binance_public import (  # noqa: E402
    BinancePublicClient,
    DEFAULT_REST_BASE_URL,
    PublicTransport,
)
from app.exchanges.binance_public_ws import (  # noqa: E402
    BinancePublicWSClient,
    DEFAULT_WS_BASE_URL,
    InProcessWSPump,
    MultiTransportPublicWSManager,
    PublicWSError,
    StdlibPublicWSTransport,
    WSConfig,
    WSMessage,
    WSMessagePump,
    create_real_public_ws_transport,
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
from loguru import logger  # noqa: E402

from app.adaptive.label_runtime import (  # noqa: E402
    LabelQueueRuntime,
    LabelQueueRuntimeConfig,
)
from app.adaptive.strategy_validation_runtime import (  # noqa: E402
    StrategyValidationRuntime,
    StrategyValidationRuntimeConfig,
)

from app.market_data_public import (  # noqa: E402
    AllMarketRadarBuffer,
    CandidatePool,
    CandidatePoolConfig,
    PaperEventChainDriver,
    PublicMarketIngestor,
    RadarScoreConfig,
    SymbolUniverse,
    WSRadarChainDriver,
    pre_anomaly_score_light,
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
# Phase 11C.1B - real public WebSocket transport factory.
#
# The runner calls :func:`_build_real_public_ws_transport` whenever
# the user requests ``--ws-first`` without ``--dry-run``. The default
# implementation returns a :class:`MultiTransportPublicWSManager`
# that owns one routed :class:`StdlibPublicWSTransport` per route
# (PUBLIC + MARKET) so the runner connects to the documented Binance
# routed public-market WebSocket endpoints
# (``wss://fstream.binance.com/public/stream`` and
# ``wss://fstream.binance.com/market/stream``). Tests monkey-patch
# this attribute to inject a deterministic in-process pump
# masquerading as a "real" transport
# (``test_runner_real_ws_first_uses_ws_adapter``) or a refusal
# sentinel (``test_runner_real_ws_first_refuses_if_transport_missing``).
#
# Two failure modes are deliberately distinct:
#
#   * the factory returns ``None``  -> the runner refuses with rc=2
#     ("real public WebSocket transport is required for --ws-first
#     without --dry-run");
#   * the factory raises an exception -> the runner refuses with
#     rc=2 and prints the exception message.
#
# Phase 11C.1B does NOT silently fall back to the PR-A bootstrap-only
# REST path under ``--ws-first``. The fallback path is reachable ONLY
# via an explicit ``--ws-disabled`` flag.
# ---------------------------------------------------------------------------
RealWSTransportFactory = Callable[[WSConfig], WSMessagePump | None]


def _build_real_public_ws_transport(
    config: WSConfig,
) -> WSMessagePump | None:
    """Default factory for the Phase 11C.1B real-network WS pump.

    Returns a :class:`MultiTransportPublicWSManager` bound to the
    supplied configuration. The manager owns one routed
    :class:`StdlibPublicWSTransport` per route (PUBLIC + MARKET) and
    presents them behind a single :class:`WSMessagePump` interface
    so the host :class:`BinancePublicWSClient` and this runner can
    pump the union without any awareness of the underlying
    routed-endpoint topology. Never reads ``BINANCE_API_KEY`` /
    ``BINANCE_API_SECRET``; never accepts a credential-shaped kwarg;
    never opens the routed-private surface.
    """
    return create_real_public_ws_transport(config=config)


def _build_rest_transport(*, dry_run: bool):
    """Module-level REST transport factory.

    Returns the deterministic in-process stub under ``--dry-run`` and
    ``None`` (which makes :class:`BinancePublicClient` use stdlib
    ``urllib``) otherwise. Tests monkey-patch this attribute to swap
    in a fake REST transport so the runner can be exercised without
    real network access.
    """
    return _build_dry_run_transport() if dry_run else None


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
            "24h test. Hard-gated to --dry-run only; the runner will "
            "refuse with rc=2 if combined with a real-network run."
        ),
    )
    # ------------------------------------------------------------------
    # Phase 11C.1B - WebSocket-first all-market radar (PR-B).
    # ------------------------------------------------------------------
    ws_group = p.add_mutually_exclusive_group()
    ws_group.add_argument(
        "--ws-first",
        action="store_true",
        dest="ws_first_explicit",
        default=None,
        help=(
            "Phase 11C.1B: enable the WebSocket-first all-market radar. "
            "Subscribes to the public ALLOWLISTED streams "
            "(!ticker@arr / !miniTicker@arr / !bookTicker / "
            "!markPrice@arr / !forceOrder@arr) over the routed Binance "
            "USDⓈ-M Futures public WebSocket endpoints "
            "(wss://fstream.binance.com/public/stream and "
            "wss://fstream.binance.com/market/stream); feeds the radar "
            "buffer and drives the candidate pool. Default: ON. With "
            "--dry-run the in-process pump is wired (no socket); "
            "without --dry-run the runner uses the real "
            "MultiTransportPublicWSManager (stdlib-only RFC 6455) "
            "and refuses with rc=2 rather than silently falling back "
            "to REST if the routed transport cannot be constructed. "
            "Mutually exclusive with --ws-disabled."
        ),
    )
    ws_group.add_argument(
        "--ws-disabled",
        action="store_true",
        dest="ws_disabled",
        default=False,
        help=(
            "Phase 11C.1B: disable the WebSocket all-market radar. "
            "The runner falls back to the PR-A bootstrap-only REST "
            "path (no per-loop detail REST). Mutually exclusive with "
            "--ws-first. Use this on hosts that cannot reach the "
            "Binance public WS endpoints."
        ),
    )
    p.add_argument(
        "--candidate-pool-size",
        type=int,
        default=None,
        dest="candidate_pool_size",
        help=(
            "Phase 11C.1B: maximum number of candidates the WS-first "
            "candidate pool may hold. Default 20."
        ),
    )
    p.add_argument(
        "--active-detail-limit",
        type=int,
        default=None,
        dest="active_detail_limit",
        help=(
            "Phase 11C.1B: number of top-scoring candidates the runner "
            "drives through the existing Phase 11C event chain "
            "(PRE_ANOMALY_DETECTED -> ANOMALY_DETECTED -> "
            "RISK_REJECTED -> STATE_TRANSITION) on every loop tick. "
            "Default 3."
        ),
    )
    p.add_argument(
        "--ws-staleness-threshold-ms",
        type=int,
        default=None,
        dest="ws_staleness_threshold_ms",
        help=(
            "Phase 11C.1B: maximum allowed gap between WS messages "
            "before the manager emits PUBLIC_WS_STALE and downgrades "
            "data quality. Default 3000ms."
        ),
    )
    p.add_argument(
        "--candidate-ttl-seconds",
        type=int,
        default=None,
        dest="candidate_ttl_seconds",
        help=(
            "Phase 11C.1B: TTL for a candidate after its last fresh "
            "WS-radar update. Default 900s (15 minutes)."
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
    # Phase 11C.1B - WebSocket-first radar metrics snapshot at shutdown.
    ws_first_enabled: bool = False
    ws_metrics: dict[str, Any] = field(default_factory=dict)
    candidate_pool_metrics: dict[str, Any] = field(default_factory=dict)
    # Phase 11C.1C-A - Adaptive Candidate Regime & Strategy Selector
    # metrics. Populated from ``WSRadarChainDriver.adaptive_metrics_payload``
    # on every loop tick that drives a chain.
    adaptive_metrics: dict[str, Any] = field(default_factory=dict)
    # Phase 11C.1C-C-A - MFE / MAE Label Queue Runtime metrics.
    # Populated from :meth:`LabelQueueRuntime.metrics_payload` on
    # every loop tick after the chain drives a candidate.
    label_runtime_metrics: dict[str, Any] = field(default_factory=dict)
    # Phase 11C.1C-C-B-A - Strategy Validation Lab v0 metrics.
    # Populated from
    # :meth:`StrategyValidationRuntime.metrics_payload` on every
    # loop tick after the chain drives a candidate.
    strategy_validation_metrics: dict[str, Any] = field(default_factory=dict)
    ws_chains_emitted: int = 0
    ws_risk_rejected: int = 0
    ws_learning_ready_attached: int = 0
    radar_candidates_seen: int = 0
    candidate_pool_size_max: int = 0
    pre_anomaly_candidates: int = 0
    liquidation_events_seen: int = 0
    radar_score_top_symbols: list[dict[str, Any]] = field(default_factory=list)
    # Phase 11C.1B - data-degraded gate (staleness) counters.
    ws_data_degraded_ticks: int = 0
    ws_real_transport: bool = False


def _push_dry_run_ws_messages(
    pump: InProcessWSPump,
    *,
    symbols: list[str],
    iteration: int,
    clock_ms_fn: Callable[[], int] = now_ms,
) -> None:
    """Push a deterministic burst of in-process WS messages for the
    Phase 11C.1B ``--dry-run`` path.

    The dry-run smoke test runs in roughly one wall-clock second but
    the radar's price-acceleration logic needs at least 30 s of
    synthetic history to score a candidate. We therefore backdate
    the per-iteration messages so the history covers a 90 s window
    ending at ``now``: a baseline ticker 90 s ago, a mid-window
    ticker 60 s ago, and a fresh ticker at ``now`` with a rising
    price + rising quote volume. The result is enough to admit at
    least one candidate into the pool's ACTIVE head and exercise
    every code path (radar -> pool -> WSRadarChainDriver -> Risk
    Engine -> PRE_ANOMALY_DETECTED + ANOMALY_DETECTED +
    STATE_TRANSITION) on a fresh sandbox database.
    """
    ts_now = int(clock_ms_fn())
    ts_60s_ago = ts_now - 60_000
    ts_90s_ago = ts_now - 90_000
    if not symbols:
        return
    # On the FIRST iteration we prime the buffer with synthetic
    # history so the lookback windows have something to compare to.
    if iteration <= 1:
        baseline_tickers = [
            {
                "s": sym,
                "c": f"{100.0 + 10.0 * idx:.4f}",
                "P": "0.10",
                "q": f"{1_000_000.0 + 50_000.0 * idx:.2f}",
            }
            for idx, sym in enumerate(symbols)
        ]
        pump.push(
            WSMessage(
                stream="!ticker@arr",
                data=baseline_tickers,
                received_at_ms=ts_90s_ago,
            )
        )
        # Mid-window sample (~60 s ago) - same price, slightly higher
        # quote volume so the radar sees a small positive trend.
        mid_tickers = [
            {
                "s": sym,
                "c": f"{100.0 + 10.0 * idx:.4f}",
                "P": "0.20",
                "q": f"{1_000_500.0 + 50_000.0 * idx:.2f}",
            }
            for idx, sym in enumerate(symbols)
        ]
        pump.push(
            WSMessage(
                stream="!ticker@arr",
                data=mid_tickers,
                received_at_ms=ts_60s_ago,
            )
        )
    # Every iteration pushes a fresh "spike" sample at ``now``: rising
    # price + meaningfully higher quote volume so
    # ``price_acceleration_60s`` and ``quote_volume_delta_60s`` both
    # cross the radar thresholds.
    spike_tickers = [
        {
            "s": sym,
            "c": f"{(100.0 + 10.0 * idx) * 1.05:.4f}",
            "P": "5.00",
            "q": f"{2_500_000.0 + 100_000.0 * iteration:.2f}",
        }
        for idx, sym in enumerate(symbols)
    ]
    pump.push(
        WSMessage(
            stream="!ticker@arr",
            data=spike_tickers,
            received_at_ms=ts_now,
        )
    )
    # !bookTicker - per-symbol fresh best bid/ask; we push only the
    # head of the symbol list to keep the burst small.
    for idx, sym in enumerate(symbols[: min(2, len(symbols))]):
        ref = (100.0 + 10.0 * idx) * 1.05
        pump.push(
            WSMessage(
                stream="!bookTicker",
                data={
                    "s": sym,
                    "b": f"{ref:.4f}",
                    "a": f"{ref + 0.05:.4f}",
                    "B": "1.0",
                    "A": "1.0",
                },
                received_at_ms=ts_now,
            )
        )
    # !markPrice@arr - mark price aligned with last price + benign funding.
    pump.push(
        WSMessage(
            stream="!markPrice@arr",
            data=[
                {
                    "s": sym,
                    "p": f"{(100.0 + 10.0 * idx) * 1.05:.4f}",
                    "r": "0.0001",
                }
                for idx, sym in enumerate(symbols)
            ],
            received_at_ms=ts_now,
        )
    )


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

    # Phase 11C.1A safety gate.
    #
    # ``--legacy-detail-per-loop`` re-enables the original "fetch every
    # detail endpoint for every symbol every loop" behaviour. That
    # pattern triggered Binance HTTP 429 / 418 in the first 24h test
    # against ``fapi.binance.com``. The flag is therefore reserved for
    # deterministic / dry-run smoke tests only, and the runner refuses
    # to start when it is combined with a real-network run.
    #
    # The help text alone is not load-bearing; this hard gate is.
    if args.legacy_detail_per_loop and not args.dry_run:
        print(
            "[AMA-RT][phase11c] "
            "--legacy-detail-per-loop is allowed only with --dry-run "
            "in Phase 11C.1A",
            file=sys.stderr,
        )
        return 2

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

    transport = _build_rest_transport(dry_run=args.dry_run)
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

    # 7b. Phase 11C.1B - WS-first transport pre-flight refusal.
    #
    # The brief makes this load-bearing: under ``--ws-first`` without
    # ``--dry-run``, the runner MUST refuse with rc=2 if the real
    # public WebSocket transport is unavailable - it does NOT silently
    # fall back to the PR-A bootstrap-only REST path. We run the
    # check HERE (before symbol resolution issues a real REST call)
    # so the refusal is observable on hosts that have no network at
    # all - the failure mode the brief targets.
    _ws_first_default = True
    if args.ws_disabled:
        _ws_first_resolved = False
    elif args.ws_first_explicit is True:
        _ws_first_resolved = True
    else:
        _ws_first_resolved = _ws_first_default
    _ws_staleness_ms_pre = (
        int(args.ws_staleness_threshold_ms)
        if args.ws_staleness_threshold_ms is not None
        else int(market_data_cfg.max_ws_staleness_ms)
    )
    if _ws_staleness_ms_pre <= 0:
        _ws_staleness_ms_pre = 3000
    _ws_pump_preflight: WSMessagePump | None = None
    _ws_pump_preflight_is_in_process: bool = False
    if _ws_first_resolved and not args.dry_run:
        ws_config_preflight = WSConfig(
            staleness_threshold_ms=_ws_staleness_ms_pre
        )
        try:
            _ws_pump_preflight = _build_real_public_ws_transport(
                ws_config_preflight
            )
        except SafeModeViolation as exc:
            print(
                f"[AMA-RT][phase11c.1b] real public WebSocket "
                f"transport refused construction: {exc}",
                file=sys.stderr,
            )
            client.stop(
                reason="phase11c_runner_ws_construction_refused"
            )
            dbs.close()
            return 2
        except Exception as exc:
            print(
                "[AMA-RT][phase11c.1b] real public WebSocket "
                "transport is required for --ws-first without "
                f"--dry-run; factory raised {type(exc).__name__}: "
                f"{exc}",
                file=sys.stderr,
            )
            client.stop(reason="phase11c_runner_ws_factory_error")
            dbs.close()
            return 2
        if _ws_pump_preflight is None:
            print(
                "[AMA-RT][phase11c.1b] real public WebSocket "
                "transport is required for --ws-first without "
                "--dry-run; the factory returned None. Use "
                "--dry-run to exercise the in-process pump or "
                "--ws-disabled to run the REST-only fallback "
                "(NOT the Phase 11C.1B acceptance path).",
                file=sys.stderr,
            )
            client.stop(
                reason="phase11c_runner_no_real_ws_transport"
            )
            dbs.close()
            return 2

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

    # 8b. Phase 11C.1B - WS-first all-market radar.
    #
    # Default: ON. The runner subscribes to the public ALLOWLISTED
    # streams (!ticker@arr / !miniTicker@arr / !bookTicker /
    # !markPrice@arr / !forceOrder@arr) over the Binance routed
    # public-market WebSocket endpoints
    # (wss://fstream.binance.com/public/stream and
    # wss://fstream.binance.com/market/stream), feeds the
    # AllMarketRadarBuffer, scores every symbol with a radar update,
    # and offers the (snapshot, score) pair to the CandidatePool. The
    # candidate pool's active head drives the Phase 11C event chain
    # (PRE_ANOMALY_DETECTED -> ANOMALY_DETECTED -> RISK_REJECTED ->
    # STATE_TRANSITION) - exactly the same chain PR-A drives, but
    # gated on a multi-candidate priority ranking (radar score) rather
    # than a fixed top-N REST cadence.
    #
    # Phase 11C.1B ships a real-network public WS pump built on the
    # Python standard library (:class:`MultiTransportPublicWSManager`
    # owning two routed :class:`StdlibPublicWSTransport` adapters -
    # one PUBLIC, one MARKET). Three execution modes:
    #
    #   1. ``--dry-run`` + ``--ws-first`` (default): the in-process
    #      :class:`InProcessWSPump` is wired and the radar is
    #      exercised against synthetic messages. NO socket is opened.
    #   2. ``--ws-first`` (without ``--dry-run``): the runner calls
    #      :func:`_build_real_public_ws_transport`, which returns a
    #      :class:`MultiTransportPublicWSManager` that opens the
    #      routed public + market endpoints. If the factory returns
    #      ``None`` or raises, the runner refuses with rc=2 - it does
    #      NOT silently fall back to the PR-A bootstrap-only REST
    #      path. The unrouted /stream legacy URL is NOT the
    #      acceptance path.
    #   3. ``--ws-disabled``: the runner falls back to the PR-A
    #      bootstrap-only REST path. Documented as NOT the all-market
    #      demon-radar acceptance path.
    ws_first_default = True
    if args.ws_disabled:
        ws_first = False
    elif args.ws_first_explicit is True:
        ws_first = True
    else:
        ws_first = ws_first_default

    candidate_pool_size = (
        int(args.candidate_pool_size)
        if args.candidate_pool_size is not None
        else 20
    )
    active_detail_limit = (
        int(args.active_detail_limit)
        if args.active_detail_limit is not None
        else max(1, candidate_detail_limit)
    )
    candidate_ttl_seconds = (
        int(args.candidate_ttl_seconds)
        if args.candidate_ttl_seconds is not None
        else 900
    )
    ws_staleness_ms = (
        int(args.ws_staleness_threshold_ms)
        if args.ws_staleness_threshold_ms is not None
        else int(market_data_cfg.max_ws_staleness_ms)
    )
    if ws_staleness_ms <= 0:
        ws_staleness_ms = 3000

    ws_client: BinancePublicWSClient | None = None
    ws_pump: WSMessagePump | None = None
    ws_pump_is_in_process: bool = False
    radar_buffer: AllMarketRadarBuffer | None = None
    candidate_pool: CandidatePool | None = None
    ws_chain: WSRadarChainDriver | None = None
    radar_score_config = RadarScoreConfig()

    if ws_first:
        ws_config = WSConfig(staleness_threshold_ms=ws_staleness_ms)
        if args.dry_run:
            ws_pump = InProcessWSPump()
            ws_pump_is_in_process = True
        else:
            # Pre-flight (step 7b) already vetted the factory and
            # holds the constructed transport. Re-use it instead of
            # rebuilding so the test-injected fake transport (and the
            # real-network handshake state in the production path)
            # is preserved across the symbol-resolution boundary.
            ws_pump = _ws_pump_preflight
            ws_pump_is_in_process = False
            if ws_pump is None:
                # Defensive: should be unreachable because step 7b
                # already returned rc=2 on this branch.
                print(
                    "[AMA-RT][phase11c.1b] real public WebSocket "
                    "transport is required for --ws-first without "
                    "--dry-run; the pre-flight transport handle is "
                    "missing.",
                    file=sys.stderr,
                )
                client.stop(
                    reason="phase11c_runner_no_real_ws_transport"
                )
                dbs.close()
                return 2
        try:
            ws_client = BinancePublicWSClient(
                config=ws_config,
                pump=ws_pump,
                event_repo=event_repo,
            )
            ws_client.connect()
        except SafeModeViolation as exc:
            print(
                f"[AMA-RT][phase11c.1b] BinancePublicWSClient refused "
                f"to start: {exc}",
                file=sys.stderr,
            )
            client.stop(reason="phase11c_runner_ws_refused")
            dbs.close()
            return 2
        except NotImplementedError as exc:
            # The default _RefusalTransport reaches here. Under
            # --ws-first without --dry-run that is a configuration
            # error: the factory must return a real transport.
            print(
                "[AMA-RT][phase11c.1b] real public WebSocket "
                "transport is required for --ws-first without "
                f"--dry-run (refusal transport raised: {exc}). Use "
                "--dry-run to exercise the in-process pump or "
                "--ws-disabled to run the REST-only fallback "
                "(NOT the Phase 11C.1B acceptance path).",
                file=sys.stderr,
            )
            client.stop(reason="phase11c_runner_ws_refusal_transport")
            dbs.close()
            return 2
        except Exception as exc:
            print(
                "[AMA-RT][phase11c.1b] real public WebSocket "
                f"transport failed to connect: {type(exc).__name__}: "
                f"{exc}",
                file=sys.stderr,
            )
            try:
                if ws_client is not None:
                    ws_client.disconnect(
                        reason="phase11c_runner_ws_connect_failed"
                    )
            except Exception:  # pragma: no cover - protective
                pass
            client.stop(reason="phase11c_runner_ws_connect_failed")
            dbs.close()
            return 2
        radar_buffer = AllMarketRadarBuffer()
        # Phase 11C.1B: bootstrap the SymbolUniverse from the public
        # /fapi/v1/exchangeInfo snapshot. The candidate pool consults
        # this set on every offer() and emits WS_SYMBOL_REJECTED for
        # any WS-radar symbol that is NOT in it. We deliberately do
        # NOT use any ASCII-only character-class regex - Binance
        # USDT-M Futures lists non-ASCII contracts (e.g. the
        # documented Chinese-named USDT contracts ``我踏马来了USDT`` /
        # ``币安人生USDT``); refusing them by character class would
        # silently lose discovery on every exotic listing. Under
        # ``--dry-run`` and on bootstrap failure we fall back to the
        # empty universe (admit everything) so existing fixture
        # tests remain green; the runner emits a degraded note
        # instead of a SymbolUniverse rejection in that case.
        symbol_universe = SymbolUniverse.empty()
        if not args.dry_run:
            try:
                exchange_symbols = client.get_symbols()
            except RateLimitProtectionError as exc:
                logger.warning(
                    "[phase11c.1b] SymbolUniverse bootstrap hit "
                    "rate-limit protection; falling back to admit-all "
                    "empty universe: {}",
                    exc,
                )
                exchange_symbols = []
            except Exception as exc:
                logger.warning(
                    "[phase11c.1b] SymbolUniverse bootstrap failed; "
                    "falling back to admit-all empty universe: {}",
                    exc,
                )
                exchange_symbols = []
            if exchange_symbols:
                symbol_universe = SymbolUniverse.from_exchange_info(
                    s.symbol for s in exchange_symbols
                )
                logger.info(
                    "[phase11c.1b] SymbolUniverse bootstrapped from "
                    "exchangeInfo size={}",
                    len(symbol_universe),
                )
        candidate_pool = CandidatePool(
            config=CandidatePoolConfig(
                candidate_pool_size=candidate_pool_size,
                active_detail_limit=active_detail_limit,
                candidate_ttl_seconds=candidate_ttl_seconds,
            ),
            symbol_universe=symbol_universe,
            event_repo=event_repo,
        )
        ws_chain = WSRadarChainDriver(
            risk_engine=risk,
            event_repo=event_repo,
            candidate_pool=candidate_pool,
            label_queue_runtime=LabelQueueRuntime(
                event_repo=event_repo,
                config=LabelQueueRuntimeConfig.from_settings_section(
                    settings.label_queue_runtime
                ),
            ),
            strategy_validation_runtime=StrategyValidationRuntime(
                event_repo=event_repo,
                config=StrategyValidationRuntimeConfig.from_settings_section(
                    settings.strategy_validation
                ),
            ),
        )

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

    stats.ws_first_enabled = bool(ws_first)
    stats.ws_real_transport = bool(
        ws_first
        and ws_pump is not None
        and not ws_pump_is_in_process
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
            ws_first=ws_first,
            ws_real_transport=stats.ws_real_transport,
            ws_staleness_threshold_ms=ws_staleness_ms,
            candidate_pool_size=candidate_pool_size,
            active_detail_limit=active_detail_limit,
        )

    # 10. Main loop.
    #
    # Phase 11C.1B WS-first execution model:
    #
    #   * exchangeInfo / ticker/24hr - bootstrap REST above; never
    #     issued per loop.
    #   * Public WebSocket streams - !ticker@arr / !miniTicker@arr /
    #     !bookTicker / !markPrice@arr / !forceOrder@arr feed the
    #     :class:`AllMarketRadarBuffer`. The radar produces a
    #     deterministic per-symbol :class:`AllMarketRadarSnapshot`
    #     summarising the last few seconds of market activity.
    #   * :func:`pre_anomaly_score_light` returns a numeric
    #     ``radar_score`` + reason tags + source streams. The runner
    #     offers each (snapshot, score) pair to the
    #     :class:`CandidatePool`.
    #   * Per-loop body iterates the candidate pool's active head
    #     (default 3). For each ACTIVE candidate the runner:
    #       1. emits the Phase 11C.1B WS-radar event chain
    #          (PRE_ANOMALY_DETECTED -> ANOMALY_DETECTED ->
    #          STATE_TRANSITION + Phase 8.5 LearningReadyContext
    #          + RISK_REJECTED via the live :class:`RiskEngine`);
    #       2. optionally pulls the per-symbol REST detail through
    #          :class:`PublicMarketIngestor` (so the existing
    #          MARKET_SNAPSHOT / Phase 4 contract continues to fire
    #          for the candidate). The detail call is guarded by the
    #          PR-A rate-limit governor.
    #
    # When ``ws_first`` is False the runner falls back to the PR-A
    # bootstrap-only path; the candidate set is empty and no detail
    # REST is issued unless ``--legacy-detail-per-loop`` is set.
    deadline = time.monotonic() + duration_seconds
    try:
        while not stop_flag["stop"] and time.monotonic() < deadline:
            stats.iterations += 1
            chain.begin_scan_batch()

            # Phase 11C.1B: pump the WS, score the radar, refresh
            # the candidate pool.
            ws_active_symbols: list[str] = []
            if ws_first and ws_client is not None and radar_buffer is not None and candidate_pool is not None:
                if (
                    args.dry_run
                    and ws_pump_is_in_process
                    and isinstance(ws_pump, InProcessWSPump)
                ):
                    _push_dry_run_ws_messages(
                        ws_pump,
                        symbols=symbols,
                        iteration=stats.iterations,
                    )
                try:
                    messages = ws_client.pump_messages(timeout_seconds=0.0)
                except NotImplementedError:
                    # Mid-run regression to refusal-mode; degrade.
                    stats.notes.append("ws_pump_notimplemented")
                    ws_first = False
                    messages = []
                if messages:
                    radar_buffer.ingest_messages(messages)
                # Re-score every symbol that has fresh state and offer
                # to the pool. This is cheap because the buffer caps
                # its history.
                candidate_pool.begin_scan_batch()
                for snap in radar_buffer.all_snapshots():
                    score = pre_anomaly_score_light(
                        snap, config=radar_score_config
                    )
                    candidate_pool.offer(snap, score)
                candidate_pool.expire()
                # Phase 11C.1B: when the WS link is stale, the radar
                # snapshots cannot be trusted to reflect the live
                # market. The DATA_DEGRADED guard SKIPS the active
                # head iteration so no PRE_ANOMALY / ANOMALY /
                # STATE_TRANSITION events fire on stale data. The
                # safety flags are unchanged - this is purely a
                # read-only quality downgrade. The PUBLIC_WS_STALE
                # event is already emitted by the BinancePublicWSClient.
                if ws_client.is_stale:
                    stats.ws_data_degraded_ticks += 1
                else:
                    # Drive the WS-radar event chain on the active head.
                    for cand in candidate_pool.active_head():
                        try:
                            ws_result = ws_chain.drive(cand)
                        except Exception as exc:  # pragma: no cover - defensive
                            stats.notes.append(
                                f"ws_chain_error:{cand.symbol}:"
                                f"{type(exc).__name__}"
                            )
                            continue
                        stats.ws_chains_emitted += 1
                        if not ws_result.risk_approved:
                            stats.ws_risk_rejected += 1
                        if ws_result.learning_ready_attached:
                            stats.ws_learning_ready_attached += 1
                        ws_active_symbols.append(cand.symbol)

            # Phase 11C.1A REST layering: only the candidate pool
            # active head receives detail REST. PR-B routes that head
            # through the existing :class:`PublicMarketIngestor` and
            # the existing PaperEventChainDriver so MARKET_SNAPSHOT /
            # Phase 4 contract / Phase 8.5 export streams keep
            # working unchanged.
            candidates: list[str] = []
            if ws_active_symbols:
                candidates = ws_active_symbols[:candidate_detail_limit]
            elif not rest_layering_enabled:
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
            if ws_client is not None:
                stats.ws_metrics = ws_client.metrics_payload()
            if candidate_pool is not None:
                stats.candidate_pool_metrics = candidate_pool.metrics_payload()
                stats.radar_candidates_seen = (
                    candidate_pool.candidates_seen
                )
                stats.candidate_pool_size_max = (
                    candidate_pool.max_size_observed
                )
                stats.pre_anomaly_candidates = (
                    candidate_pool.candidates_promoted
                )
                stats.radar_score_top_symbols = list(
                    stats.candidate_pool_metrics.get(
                        "candidate_pool_top_symbols", []
                    )
                )
            # Phase 11C.1C-A - copy adaptive metrics from the WS-radar
            # chain driver so the daily report has the latest figures.
            if ws_chain is not None:
                stats.adaptive_metrics = ws_chain.adaptive_metrics_payload()
                # Phase 11C.1C-C-A - tick the label runtime so any
                # window whose end_ts has passed gets finalized, then
                # snapshot its metrics for the daily report.
                if ws_chain.label_queue_runtime is not None:
                    try:
                        ws_chain.label_queue_runtime.tick(
                            now_ms=int(now_ms())
                        )
                        stats.label_runtime_metrics = (
                            ws_chain.label_queue_runtime.metrics_payload()
                        )
                    except Exception as exc:  # pragma: no cover - defensive
                        stats.notes.append(
                            f"label_runtime_tick_error:"
                            f"{type(exc).__name__}"
                        )
                # Phase 11C.1C-C-B-A - snapshot strategy validation
                # metrics every loop tick. The runtime is paper /
                # report only; reading metrics never authorises a
                # real trade.
                if ws_chain.strategy_validation_runtime is not None:
                    try:
                        stats.strategy_validation_metrics = (
                            ws_chain.strategy_validation_runtime.metrics_payload()
                        )
                    except Exception as exc:  # pragma: no cover - defensive
                        stats.notes.append(
                            f"strategy_validation_metrics_error:"
                            f"{type(exc).__name__}"
                        )
            if radar_buffer is not None:
                stats.liquidation_events_seen = (
                    radar_buffer.liquidation_events_seen
                )
            # Pin invariants on every loop tick.
            client.assert_public_only()
            # Hard stop if the governor latched into protection mode.
            if governor.in_protection_mode:
                stats.notes.append("rate_limit_protection_mode")
                break
            # Sleep until the next tick. We use small chunks so Ctrl+C
            # is responsive AND - Phase 11C.1B PR-B fix - we keep
            # pumping the public WebSocket during the wait window so
            # the OS TCP receive buffer drains continuously instead
            # of piling up between ticks. The earlier code called
            # ``ws_client.pump_messages(timeout_seconds=0.0)`` ONCE
            # per tick and then ``time.sleep(poll_interval)``; with
            # the stdlib transport the non-blocking probe never
            # entered ``recv`` and the radar buffer stayed empty
            # (smoke test reproduced ws_messages_received=0). For
            # the real-network transport we now use the WS pump's
            # blocking timeout for the sleep itself: each chunk
            # lets ``select`` block for up to ``sleep_chunk``
            # seconds waiting for socket bytes, then returns
            # whatever frames arrived. The kernel buffer never gets
            # a chance to overflow on long-running deployments.
            #
            # The in-process pump (``--dry-run``) and the legacy
            # back-compat refusal pump don't block on poll, so we
            # fall back to ``time.sleep`` for them - otherwise the
            # sleep window collapses into a tight CPU spin.
            slept = 0.0
            sleep_chunk = 0.5
            ws_pump_blocks_on_poll = bool(
                ws_first
                and ws_client is not None
                and radar_buffer is not None
                and not ws_pump_is_in_process
            )
            while slept < poll_interval and not stop_flag["stop"]:
                chunk = min(sleep_chunk, poll_interval - slept)
                if ws_pump_blocks_on_poll and ws_client.is_connected:
                    try:
                        extra = ws_client.pump_messages(
                            timeout_seconds=chunk
                        )
                    except NotImplementedError:
                        # Mid-run regression to refusal-mode; degrade.
                        stats.notes.append("ws_pump_notimplemented")
                        ws_first = False
                        ws_pump_blocks_on_poll = False
                        time.sleep(chunk)
                        slept += chunk
                        continue
                    except Exception as exc:  # pragma: no cover
                        stats.notes.append(
                            f"ws_pump_sleep_error:{type(exc).__name__}"
                        )
                        time.sleep(chunk)
                        slept += chunk
                        continue
                    if extra:
                        radar_buffer.ingest_messages(extra)
                else:
                    time.sleep(chunk)
                slept += chunk
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
        if ws_client is not None:
            try:
                ws_client.disconnect(reason="phase11c_runner_safe_mode")
            except Exception:  # pragma: no cover - protective
                pass
        dbs.close()
        return 2
    finally:
        stats.finished_at_ms = now_ms()
        stats.governor_metrics = governor.metrics_payload()
        if ws_client is not None:
            stats.ws_metrics = ws_client.metrics_payload()
        if candidate_pool is not None:
            stats.candidate_pool_metrics = candidate_pool.metrics_payload()
            stats.radar_score_top_symbols = list(
                stats.candidate_pool_metrics.get(
                    "candidate_pool_top_symbols", []
                )
            )
        # Phase 11C.1C-A - capture adaptive metrics on shutdown.
        if ws_chain is not None:
            stats.adaptive_metrics = ws_chain.adaptive_metrics_payload()
            # Phase 11C.1C-C-A - tick label runtime once more on
            # shutdown so any window that just closed finalises
            # before the daily-report snapshot runs.
            if ws_chain.label_queue_runtime is not None:
                try:
                    ws_chain.label_queue_runtime.tick(now_ms=int(now_ms()))
                    stats.label_runtime_metrics = (
                        ws_chain.label_queue_runtime.metrics_payload()
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    stats.notes.append(
                        f"label_runtime_shutdown_tick_error:"
                        f"{type(exc).__name__}"
                    )
            # Phase 11C.1C-C-B-A - flush a final
            # :class:`StrategyValidationReport` on shutdown so the
            # daily report gets the complete cohort + cluster
            # aggregates. The runtime is paper / report only; the
            # final flush never authorises a real trade.
            if ws_chain.strategy_validation_runtime is not None:
                try:
                    ws_chain.strategy_validation_runtime.flush_report(
                        generated_at_ms=int(now_ms()),
                        emit_events=True,
                    )
                    stats.strategy_validation_metrics = (
                        ws_chain.strategy_validation_runtime.metrics_payload()
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    stats.notes.append(
                        f"strategy_validation_shutdown_flush_error:"
                        f"{type(exc).__name__}"
                    )
        if radar_buffer is not None:
            stats.liquidation_events_seen = (
                radar_buffer.liquidation_events_seen
            )

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
                    "phase": "11C.1B",
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
                    "ws_first": bool(stats.ws_first_enabled),
                    "ws_real_transport": bool(stats.ws_real_transport),
                    "ws_data_degraded_ticks": int(stats.ws_data_degraded_ticks),
                    "ws_chains_emitted": int(stats.ws_chains_emitted),
                    "ws_risk_rejected": int(stats.ws_risk_rejected),
                    "ws_learning_ready_attached": int(
                        stats.ws_learning_ready_attached
                    ),
                    "candidate_pool_size": int(candidate_pool_size),
                    "active_detail_limit": int(active_detail_limit),
                    "candidate_ttl_seconds": int(candidate_ttl_seconds),
                    "ws_staleness_threshold_ms": int(ws_staleness_ms),
                },
                error_notes=tuple(stats.notes),
                degraded_notes=(),
                rate_limit_metrics=dict(stats.governor_metrics),
                ingestion_errors=int(stats.ingestion_errors),
                ws_metrics=dict(stats.ws_metrics),
                candidate_pool_metrics=dict(stats.candidate_pool_metrics),
                adaptive_metrics=dict(stats.adaptive_metrics),
                label_runtime_metrics=dict(stats.label_runtime_metrics),
                strategy_validation_metrics=dict(
                    stats.strategy_validation_metrics
                ),
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
    if ws_client is not None:
        try:
            ws_client.disconnect(reason="phase11c_runner_shutdown")
        except Exception:  # pragma: no cover - protective
            pass
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
    ws_first: bool = False,
    ws_real_transport: bool = False,
    ws_staleness_threshold_ms: int = 3000,
    candidate_pool_size: int = 20,
    active_detail_limit: int = 3,
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
        "[AMA-RT] Phase 11C.1C-B-IN_REVIEW - Adaptive Candidate Runtime "
        "Calibration & Early Tail Discovery v0 "
        f"v{__version__} "
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
        f"ws_first={ws_first} "
        f"ws_real_transport={ws_real_transport} "
        f"ws_staleness_threshold_ms={ws_staleness_threshold_ms} "
        f"candidate_pool_size={candidate_pool_size} "
        f"active_detail_limit={active_detail_limit} "
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
    ws_metrics = stats.ws_metrics or {}
    print(
        "[AMA-RT] Phase 11C.1C-B-IN_REVIEW run finished "
        f"duration_seconds={duration_s} "
        f"iterations={stats.iterations} "
        f"chains_emitted={stats.chains_emitted} "
        f"ws_chains_emitted={stats.ws_chains_emitted} "
        f"ws_risk_rejected={stats.ws_risk_rejected} "
        f"risk_approved={stats.risk_approved} "
        f"risk_rejected={stats.risk_rejected} "
        f"learning_ready_attached={stats.learning_ready_attached} "
        f"ws_learning_ready_attached={stats.ws_learning_ready_attached} "
        f"snapshots_emitted={stats.snapshots_emitted} "
        f"ingestion_errors={stats.ingestion_errors} "
        f"public_endpoint_calls={client.total_calls} "
        f"ws_messages_received={ws_metrics.get('ws_messages_received', 0)} "
        f"ws_reconnect_count={ws_metrics.get('ws_reconnect_count', 0)} "
        f"ws_staleness_ms_max={ws_metrics.get('ws_staleness_ms_max', 0)} "
        f"ws_stale_count={ws_metrics.get('ws_stale_count', 0)} "
        f"ws_real_transport={stats.ws_real_transport} "
        f"ws_data_degraded_ticks={stats.ws_data_degraded_ticks} "
        f"radar_candidates_seen={stats.radar_candidates_seen} "
        f"candidate_pool_size_max={stats.candidate_pool_size_max} "
        f"liquidation_events_seen={stats.liquidation_events_seen} "
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
