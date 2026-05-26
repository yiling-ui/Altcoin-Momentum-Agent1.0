"""Phase 11C.1C-C-B-B-B-D-A.1 - Historical 60D Mover Reference Store
Builder v0.

This script is the **data preparation** step for the Phase
11C.1C-C-B-B-B-D-A *Historical 60D Mover Coverage Backfill Audit*
(see :mod:`app.adaptive.historical_mover_coverage_backfill`).

It builds a small, local **Historical Market Store** under
``data/historical_market_store/`` that the audit consumes through
:func:`app.adaptive.historical_mover_coverage_backfill.load_historical_market_store`.

What this script IS
-------------------

  - A **public-data-only** historical reference set builder.
  - Consumes Binance USDT-M perpetual futures public REST endpoints
    only (``/fapi/v1/exchangeInfo``, ``/fapi/v1/ticker/24hr``,
    ``/fapi/v1/klines``).
  - Filters the eligible USDT perpetual futures universe via
    ``exchangeInfo``.
  - Computes daily top movers from 1h klines over the trailing
    ``--days`` window.
  - Writes JSONL + manifest artefacts that the existing D-A loader
    can read without modification.
  - Records its public-only invariants in the manifest so the
    closeout PR can audit them at a glance.

What this script IS NOT
-----------------------

  - **NOT** a strategy blind replay.
  - **NOT** a PnL backtest.
  - **NOT** a trading module.
  - **NOT** an AI Learning / parameter-optimisation / reinforcement
    learning surface.
  - **NOT** the small-money live-trading pre-validation gate.
  - **NOT** Phase 12.

Safety boundary (carried verbatim into the manifest + every JSONL
row)
-----------------------------------------------------------------

  - ``mode = paper``
  - ``live_trading = False``
  - ``exchange_live_orders = False``
  - ``right_tail = False``
  - ``llm = False``
  - ``telegram_outbound_enabled = False``
  - ``binance_private_api_enabled = False``
  - No Binance API key. No Binance API secret. No signed endpoint.
    No ``account`` / ``order`` / ``position`` / ``leverage`` /
    ``margin`` endpoint. No private WebSocket. No ``listenKey``.
  - No DeepSeek trade decision. No real Telegram outbound.
  - The reference set is **post-hoc audit reference only**. It
    MUST NEVER drive live radar score, candidate promotion, the
    Risk Engine, the Execution FSM, ``symbol_limit``,
    candidate-pool capacity, anomaly thresholds, Regime weights,
    or any other runtime knob.
  - The Risk Engine remains the single trade-decision gate.
  - Phase 12 remains **FORBIDDEN**.

Lookahead Guard
---------------

The builder consumes only kline closes that already existed at the
time of each window's UTC end. Every emitted row carries
``lookahead_policy = "post_hoc_reference_only"``. Every emitted row
must NOT contain any of
:data:`app.adaptive.historical_mover_coverage_backfill.LOOKAHEAD_FORBIDDEN_FIELDS`.

USAGE
-----

    python -m scripts.build_historical_mover_reference_store \\
        --days 60 --top-n 20

    # Small dry-run smoke (no network, no disk writes)
    python -m scripts.build_historical_mover_reference_store \\
        --days 2 --symbol-limit 3 --top-n 5 --dry-run

    # Network-free deterministic generation (writes files)
    python -m scripts.build_historical_mover_reference_store \\
        --days 2 --symbol-limit 3 --top-n 5 --no-network

The script intentionally uses only ``urllib.request`` for the
default real-network transport so the wider Phase 11C source-tree
audit (no third-party HTTP / WebSocket / exchange / LLM / Telegram
bot libraries) is preserved.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


# ---------------------------------------------------------------------------
# Repository root on sys.path
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:  # pragma: no cover - import-time bootstrap
    sys.path.insert(0, str(ROOT))


from app.adaptive.historical_mover_coverage_backfill import (  # noqa: E402
    HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION,
    LOOKAHEAD_FORBIDDEN_FIELDS,
    HistoricalMoverLookaheadGuardError,
    validate_no_lookahead_fields,
)
from app.exchanges.binance_public import (  # noqa: E402
    ALLOWED_PUBLIC_HOSTS,
    DEFAULT_REST_BASE_URL,
    FORBIDDEN_PRIVATE_ENDPOINTS,
    FORBIDDEN_QUERY_PARAMETERS,
    PUBLIC_MARKET_ENDPOINT_ALLOWLIST,
    assert_public_endpoint_allowed,
)
from app.core.errors import SafeModeViolation  # noqa: E402


logger = logging.getLogger("ama_rt.scripts.build_historical_mover_reference_store")


# ---------------------------------------------------------------------------
# Constants - schema + boundary
# ---------------------------------------------------------------------------

#: Builder version. Bumped only when the on-disk artefact shape
#: changes. The value is stamped into the manifest and into every
#: JSONL row so a downstream consumer can pin a reproducible snapshot.
BUILDER_VERSION: str = "phase_11c_1c_c_b_b_b_d_a_1.historical_60d_mover_reference_store_builder.v0"

#: Reference set source string. Stamped into every emitted JSONL row
#: so downstream consumers can identify the provenance without needing
#: to read the manifest.
REFERENCE_SOURCE: str = "binance_public_futures_klines_1h"

#: Lookahead policy label. Stamped on every JSONL row.
LOOKAHEAD_POLICY: str = "post_hoc_reference_only"

#: Builder-level schema version. Independent from
#: HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION because the
#: builder writes a wider row than the audit ingests.
BUILDER_SCHEMA_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_a_1.historical_60d_mover_reference_store.v0"
)

#: Default output directory (relative to repo root). The audit's
#: ``load_historical_market_store(root)`` call expects exactly this
#: layout.
DEFAULT_OUTPUT_DIR: str = "data/historical_market_store"

#: Default trailing-window length in days, mirroring the audit's
#: :data:`DEFAULT_REFERENCE_WINDOW_DAYS`.
DEFAULT_DAYS: int = 60

#: Default top-N per day. Smaller than the audit's reference cap on
#: purpose so the JSONL stays compact and human-reviewable.
DEFAULT_TOP_N: int = 20

#: Default kline timeframe.
DEFAULT_TIMEFRAME: str = "1h"

#: Allowlist of kline timeframes the builder accepts. Anything else
#: is refused. Keeping a small list also keeps the per-symbol
#: request count bounded.
ALLOWED_TIMEFRAMES: tuple[str, ...] = (
    "1m",
    "3m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "8h",
    "12h",
    "1d",
)

#: Maximum number of klines per request to Binance.
KLINE_BATCH_LIMIT: int = 1000

#: Per-symbol REST sleep so the builder politely shares public REST
#: bandwidth with any other Phase 11C surface running on the same
#: host.
DEFAULT_REQUEST_SLEEP_SECONDS: float = 0.05

#: Names of environment variables that, if present, are a strong
#: signal that the operator is mixing private credentials with what
#: should be a public-only surface. The builder refuses to start if
#: any of them are set, defence-in-depth above the
#: :class:`BinancePublicClient` constructor refusal.
FORBIDDEN_CRED_ENV_VARS: tuple[str, ...] = (
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "BINANCE_KEY",
    "BINANCE_SECRET",
    "BINANCE_TOKEN",
    "BINANCE_PASSPHRASE",
)


# ---------------------------------------------------------------------------
# Public-only safety pre-flight
# ---------------------------------------------------------------------------


def assert_no_credentials_in_env(env: Mapping[str, str] | None = None) -> None:
    """Refuse to start if any forbidden credential env var is set.

    The Phase 11C contract forbids the reference store builder from
    even *seeing* a Binance private credential. This pre-flight is
    defence-in-depth: it does not read the value, it only checks
    presence + non-emptiness.
    """
    e = env if env is not None else os.environ
    leaked = sorted(name for name in FORBIDDEN_CRED_ENV_VARS if e.get(name))
    if leaked:
        raise SafeModeViolation(
            "scripts.build_historical_mover_reference_store: refused to "
            "start with private-credential environment variables present: "
            f"{leaked}. Phase 11C is public-market read-only; remove the "
            "credential from the environment before retrying."
        )


# ---------------------------------------------------------------------------
# Data source
# ---------------------------------------------------------------------------


PublicTransport = Callable[[str], Any]


class PublicEndpointViolation(SafeModeViolation):
    """Raised when the builder tries to reach a non-public endpoint."""


@dataclass(frozen=True)
class PublicCallRecord:
    """Recorded summary of one public REST call.

    Carries the canonical path (querystring stripped) + outcome so
    the manifest can record which endpoints the builder hit. We do
    not log the full URL with querystring to avoid leaking
    operator-specific symbol filters into long-term evidence.
    """

    path: str
    status: str  # "ok" | "error"


class BinanceFuturesPublicSource:
    """Thin public-only data source for the builder.

    The class deliberately inherits NOTHING from
    :class:`app.exchanges.binance_public.BinancePublicClient` because
    the builder does not need the event-emission / health-state /
    governor plumbing. It DOES reuse the shared
    :func:`app.exchanges.binance_public.assert_public_endpoint_allowed`
    allowlist guard so any new endpoint is refused at the same
    boundary as the runtime client.

    The default transport uses :mod:`urllib.request` from the Python
    standard library. Tests inject a deterministic in-process
    callable so no real socket is opened.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_REST_BASE_URL,
        transport: PublicTransport | None = None,
        timeout_seconds: float = 10.0,
        request_sleep_seconds: float = DEFAULT_REQUEST_SLEEP_SECONDS,
        api_key: str | None = None,
        api_secret: str | None = None,
        **forbidden_credentials: Any,
    ) -> None:
        # Defence-in-depth: refuse credential-shaped kwargs.
        if api_key is not None or api_secret is not None:
            raise SafeModeViolation(
                "BinanceFuturesPublicSource: refused api_key / "
                "api_secret. Phase 11C is public-market read-only."
            )
        for name in forbidden_credentials:
            lowered = name.lower()
            if any(
                needle in lowered
                for needle in (
                    "api_key",
                    "api_secret",
                    "apikey",
                    "secret",
                    "token",
                    "signature",
                    "passphrase",
                )
            ):
                raise SafeModeViolation(
                    "BinanceFuturesPublicSource: refused credential-"
                    f"shaped keyword argument {name!r}."
                )
        if forbidden_credentials:
            raise TypeError(
                "BinanceFuturesPublicSource got unexpected keyword "
                f"argument(s): {sorted(forbidden_credentials)}"
            )

        self._base_url = base_url.rstrip("/")
        # Validate the base URL by appending a known-good allowlisted
        # path; misconfiguration fails immediately rather than later.
        assert_public_endpoint_allowed(
            urllib.parse.urlsplit(self._base_url)._replace(
                path="/fapi/v1/exchangeInfo"
            ).geturl()
        )
        self._timeout_seconds = float(timeout_seconds)
        self._request_sleep_seconds = float(request_sleep_seconds)
        self._transport: PublicTransport = (
            transport
            if transport is not None
            else _stdlib_urllib_transport(timeout_seconds=self._timeout_seconds)
        )
        self._call_records: list[PublicCallRecord] = []
        # Defence-in-depth: a curtailed flag the test suite can read
        # to assert no key was ever loaded.
        self._api_key_loaded = False
        self._signed_endpoint_used = False

    # ------------------------------------------------------------------
    # Read-only introspection
    # ------------------------------------------------------------------
    @property
    def call_records(self) -> tuple[PublicCallRecord, ...]:
        return tuple(self._call_records)

    @property
    def api_key_loaded(self) -> bool:
        return False  # Always False; never reads a key.

    @property
    def signed_endpoint_used(self) -> bool:
        return False  # Always False; never signs a request.

    @property
    def base_url(self) -> str:
        return self._base_url

    # ------------------------------------------------------------------
    # Internal request plumbing
    # ------------------------------------------------------------------
    def _request(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Issue a public GET against ``path`` with optional ``params``.

        Validates the path through :func:`assert_public_endpoint_allowed`
        BEFORE building the URL. Any forbidden query parameter
        (``signature`` / ``timestamp`` / ``recvWindow`` / ``apiKey``)
        is rejected.
        """
        canonical = assert_public_endpoint_allowed(path)
        if canonical in FORBIDDEN_PRIVATE_ENDPOINTS:  # pragma: no cover - already raised
            raise PublicEndpointViolation(
                f"refused private endpoint {canonical!r}."
            )
        query_pairs: list[tuple[str, str]] = []
        if params:
            for name, value in params.items():
                if name in FORBIDDEN_QUERY_PARAMETERS:
                    raise SafeModeViolation(
                        f"refused signed-request query parameter {name!r}."
                    )
                if value is None:
                    continue
                query_pairs.append((str(name), str(value)))
        query = urllib.parse.urlencode(query_pairs)
        url = self._base_url + canonical
        if query:
            url = f"{url}?{query}"
        # Re-validate the fully-formed URL.
        assert_public_endpoint_allowed(url)
        try:
            body = self._transport(url)
            self._call_records.append(
                PublicCallRecord(path=canonical, status="ok")
            )
            return body
        except Exception:
            self._call_records.append(
                PublicCallRecord(path=canonical, status="error")
            )
            raise
        finally:
            if self._request_sleep_seconds > 0:
                time.sleep(self._request_sleep_seconds)

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------
    def fetch_exchange_info(self) -> dict[str, Any]:
        """Return the raw ``/fapi/v1/exchangeInfo`` payload."""
        body = self._request("/fapi/v1/exchangeInfo")
        if not isinstance(body, dict):  # pragma: no cover - defensive
            raise RuntimeError(
                "binance public exchangeInfo did not return a JSON object"
            )
        return body

    def fetch_24h_tickers(self) -> list[dict[str, Any]]:
        """Return the raw ``/fapi/v1/ticker/24hr`` payload."""
        body = self._request("/fapi/v1/ticker/24hr")
        if isinstance(body, dict):
            return [body]
        if isinstance(body, list):
            return [r for r in body if isinstance(r, dict)]
        return []

    def fetch_klines(
        self,
        symbol: str,
        *,
        interval: str = DEFAULT_TIMEFRAME,
        start_ms: int,
        end_ms: int,
        limit: int = KLINE_BATCH_LIMIT,
    ) -> list[list[Any]]:
        """Return raw kline rows (Binance returns a list of lists).

        The builder paginates through the requested window in batches
        of ``limit`` rows because Binance caps single requests at
        1000 candles. Each batch carries an explicit ``startTime`` /
        ``endTime`` so duplicates / gaps are deterministic.
        """
        if interval not in ALLOWED_TIMEFRAMES:
            raise ValueError(
                f"interval {interval!r} is not in the builder allowlist; "
                f"allowed: {ALLOWED_TIMEFRAMES}"
            )
        if start_ms >= end_ms:
            return []
        clamped_limit = max(1, min(int(limit), KLINE_BATCH_LIMIT))
        out: list[list[Any]] = []
        cursor = int(start_ms)
        while cursor < end_ms:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": clamped_limit,
            }
            body = self._request("/fapi/v1/klines", params=params)
            if not isinstance(body, list) or not body:
                break
            for row in body:
                if isinstance(row, list) and len(row) >= 7:
                    out.append(row)
            last_open_ms = int(body[-1][0])
            # Each candle is ``interval`` ms wide; advance one beyond
            # the last open to avoid duplicating it on the next page.
            advance_ms = _interval_ms(interval)
            cursor = last_open_ms + advance_ms
            if len(body) < clamped_limit:
                break
        return out


def _stdlib_urllib_transport(*, timeout_seconds: float) -> PublicTransport:
    """Default network transport using :mod:`urllib.request`.

    The transport is intentionally minimal:

      - No third-party library import.
      - No ``Authorization`` header.
      - No credential consumption.
      - Single GET, parses JSON.
    """

    def _fetch(url: str) -> Any:
        req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "User-Agent": (
                    "ama-rt/phase-11c-1c-c-b-b-b-d-a-1 "
                    "(historical-mover-reference-store-builder; "
                    "public-market-readonly)"
                ),
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read()
            if resp.status != 200:
                raise RuntimeError(
                    f"binance_public: HTTP {resp.status} from {url}"
                )
            return json.loads(raw.decode("utf-8"))

    return _fetch


def _interval_ms(interval: str) -> int:
    """Return the millisecond width of one candle for ``interval``."""
    units = {
        "m": 60 * 1000,
        "h": 60 * 60 * 1000,
        "d": 24 * 60 * 60 * 1000,
    }
    if not interval:
        raise ValueError("empty interval")
    head, tail = interval[:-1], interval[-1]
    multiplier = units.get(tail)
    if multiplier is None:
        raise ValueError(f"unsupported interval {interval!r}")
    try:
        amount = int(head)
    except ValueError as exc:
        raise ValueError(f"unsupported interval {interval!r}") from exc
    if amount <= 0:
        raise ValueError(f"unsupported interval {interval!r}")
    return amount * multiplier


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def filter_eligible_usdt_perpetual_universe(
    exchange_info: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return the eligible USDT-perpetual symbol entries from
    ``exchange_info``.

    The filter mirrors :meth:`BinancePublicClient.get_symbols`:

      - ``contractType == "PERPETUAL"``
      - ``quoteAsset == "USDT"``
      - ``status == "TRADING"`` (where present)

    Only the columns the builder needs are kept; the rest of the
    payload is discarded so the on-disk snapshot stays small.
    """
    out: list[dict[str, Any]] = []
    for sym in exchange_info.get("symbols", []) or []:
        if not isinstance(sym, Mapping):
            continue
        if sym.get("contractType") != "PERPETUAL":
            continue
        if sym.get("quoteAsset") != "USDT":
            continue
        status = sym.get("status")
        if status is not None and status != "TRADING":
            continue
        out.append(
            {
                "symbol": str(sym.get("symbol")),
                "base_asset": str(sym.get("baseAsset", "")),
                "quote_asset": "USDT",
                "contract_type": "PERPETUAL",
                "status": str(status or "TRADING"),
            }
        )
    return out


def select_symbols_by_volume(
    *,
    eligible_universe: Sequence[Mapping[str, Any]],
    tickers_24h: Sequence[Mapping[str, Any]],
    symbol_limit: int | None,
) -> list[str]:
    """Return the (possibly truncated) symbol list, ranked by 24h
    quote volume when a limit is provided.

    When ``symbol_limit`` is None or zero or larger than the universe
    size, the full eligible universe is returned in alphabetical
    order. When a positive limit is provided, the top-N by quote
    volume is returned (Binance's ``quoteVolume`` field, fallback to
    0 when missing). Symbols not in the eligible universe are
    discarded.
    """
    eligible = {str(row["symbol"]) for row in eligible_universe if row.get("symbol")}
    if not eligible:
        return []
    if not symbol_limit or symbol_limit <= 0:
        return sorted(eligible)
    # Build a (symbol, quote_volume) ranking from ticker rows.
    volumes: dict[str, float] = {sym: 0.0 for sym in eligible}
    for row in tickers_24h:
        sym = str(row.get("symbol") or "")
        if sym not in eligible:
            continue
        try:
            qv = float(row.get("quoteVolume") or 0.0)
        except (TypeError, ValueError):
            qv = 0.0
        volumes[sym] = qv
    ranked = sorted(volumes.items(), key=lambda kv: (-kv[1], kv[0]))
    return [sym for sym, _ in ranked[: int(symbol_limit)]]


def klines_to_daily_top_movers(
    *,
    klines_by_symbol: Mapping[str, Sequence[Sequence[Any]]],
    days: int,
    top_n: int,
    audit_window_end_ms: int,
    timeframe: str = DEFAULT_TIMEFRAME,
    symbol_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Bucket klines into per-day windows and return the top-N
    movers per day.

    Each input kline row follows Binance's documented shape::

        [open_time, open, high, low, close, volume, close_time,
         quote_asset_volume, num_trades, taker_buy_base, taker_buy_quote, ignore]

    For every UTC day in the trailing window the function:

      * Aggregates all candles whose ``open_time`` falls inside the
        day boundary [day_start, day_end).
      * Computes ``window_gain_pct`` as
        ``(close_last - open_first) / open_first`` (decimal fraction).
      * Computes ``max_24h_gain_pct`` as
        ``(max_high - min_low) / open_first`` (descriptive).
      * Records aggregate quote volume and high/low/open/close.
      * Ranks within the day by ``window_gain_pct`` (desc) and
        keeps the top-N rows.

    The returned rows carry both the loader-required columns and the
    brief-required columns. They never carry any field in
    :data:`LOOKAHEAD_FORBIDDEN_FIELDS`.
    """
    if days <= 0:
        raise ValueError(f"days must be positive, got {days}")
    if top_n <= 0:
        raise ValueError(f"top_n must be positive, got {top_n}")

    day_ms = 24 * 60 * 60 * 1000
    end_ms = int(audit_window_end_ms) - (int(audit_window_end_ms) % day_ms)
    start_ms = end_ms - days * day_ms

    # Per-day buckets keyed by day_start_ms.
    days_index: dict[int, list[dict[str, Any]]] = {
        start_ms + i * day_ms: [] for i in range(days)
    }

    metadata = dict(symbol_metadata or {})

    for symbol, rows in klines_by_symbol.items():
        if not rows:
            continue
        # Group klines by day.
        per_day_rows: dict[int, list[Sequence[Any]]] = {}
        for row in rows:
            if not isinstance(row, Sequence) or len(row) < 7:
                continue
            try:
                open_ms = int(row[0])
            except (TypeError, ValueError):
                continue
            day_start = open_ms - (open_ms % day_ms)
            if day_start < start_ms or day_start >= end_ms:
                continue
            per_day_rows.setdefault(day_start, []).append(row)

        for day_start, day_rows in per_day_rows.items():
            day_rows = sorted(day_rows, key=lambda r: int(r[0]))
            try:
                open_first = float(day_rows[0][1])
                close_last = float(day_rows[-1][4])
            except (TypeError, ValueError):
                continue
            if open_first <= 0.0:
                continue
            highs = [float(r[2]) for r in day_rows]
            lows = [float(r[3]) for r in day_rows]
            try:
                quote_volume_total = sum(float(r[7] or 0.0) for r in day_rows)
            except (TypeError, ValueError, IndexError):
                quote_volume_total = 0.0
            window_gain_pct = (close_last - open_first) / open_first
            max_gain = (max(highs) - open_first) / open_first if highs else 0.0
            min_drawdown = (min(lows) - open_first) / open_first if lows else 0.0
            # ``max_24h_gain_pct`` is intentionally descriptive: the
            # high-side excursion over the same UTC day. It is NOT
            # used as a signal; the Lookahead Guard treats this row
            # as a post-hoc reference only.
            max_24h_gain_pct = max(window_gain_pct, max_gain)
            day_end = day_start + day_ms
            meta = metadata.get(symbol, {})
            row_payload = {
                "symbol": symbol,
                "snapshot_date": _ms_to_iso_date(day_start),
                "reference_timestamp_utc": _ms_to_iso(day_end),
                "reference_timestamp_utc_ms": int(day_end),
                "mover_window_start_utc": _ms_to_iso(day_start),
                "mover_window_start_utc_ms": int(day_start),
                "mover_window_end_utc": _ms_to_iso(day_end),
                "mover_window_end_utc_ms": int(day_end),
                "timeframe": timeframe,
                "open_price": float(open_first),
                "close_price": float(close_last),
                "high_price": float(max(highs)),
                "low_price": float(min(lows)),
                "window_gain_pct": float(window_gain_pct),
                "max_window_gain": float(window_gain_pct),
                "max_24h_gain_pct": float(max_24h_gain_pct),
                "max_24h_gain": float(max_24h_gain_pct),
                "min_window_drawdown_pct": float(min_drawdown),
                "quote_volume": float(quote_volume_total),
                "quote_volume_usdt": float(quote_volume_total),
                "kline_count": int(len(day_rows)),
                "quote_asset": str(meta.get("quote_asset") or "USDT"),
                "contract_type": str(meta.get("contract_type") or "PERPETUAL"),
                "eligible_usdt_perpetual": bool(
                    meta.get("eligible_usdt_perpetual", True)
                ),
                "source": REFERENCE_SOURCE,
                "lookahead_policy": LOOKAHEAD_POLICY,
            }
            days_index[day_start].append(row_payload)

    # Rank per day + take top-N.
    out: list[dict[str, Any]] = []
    for day_start in sorted(days_index.keys()):
        day_rows = sorted(
            days_index[day_start],
            key=lambda r: (-r["window_gain_pct"], r["symbol"]),
        )
        for rank, row in enumerate(day_rows[:top_n], start=1):
            row["top_mover_rank"] = int(rank)
            out.append(row)
    return out


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def _utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _ms_to_iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat(
        timespec="seconds"
    )


def _ms_to_iso_date(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%d"
    )


def _ts_compact(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )


# ---------------------------------------------------------------------------
# Disk writers
# ---------------------------------------------------------------------------


@dataclass
class BuilderArtefacts:
    """Filesystem paths the builder has emitted (or would emit, in
    dry-run mode)."""

    exchange_info_path: Path
    top_movers_path: Path
    manifest_path: Path
    written: bool = False


def write_exchange_info_snapshot(
    *,
    output_root: Path,
    eligible_universe: Sequence[Mapping[str, Any]],
    generated_at_ms: int,
    dry_run: bool,
) -> Path:
    """Write the exchange-info snapshot to
    ``<root>/exchange_info/binance_futures_exchange_info_<ts>.json``
    (the loader's ``exchange_info_subdir`` default).

    The file is a single JSON object with the keys the loader looks
    for:

      - ``symbols``: list of symbol strings (compact form).
      - ``symbol_entries``: list of ``{symbol, base_asset, ...}`` dicts.
    """
    ts = _ts_compact(generated_at_ms)
    path = output_root / "exchange_info" / (
        f"binance_futures_exchange_info_{ts}.json"
    )
    payload = {
        "schema_version": BUILDER_SCHEMA_VERSION,
        "source": REFERENCE_SOURCE,
        "generated_at_utc": _ms_to_iso(generated_at_ms),
        "generated_at_utc_ms": int(generated_at_ms),
        "symbols": sorted({str(r["symbol"]) for r in eligible_universe if r.get("symbol")}),
        "symbol_entries": [dict(r) for r in eligible_universe],
        "public_endpoint_only": True,
        "private_api_used": False,
        "api_key_loaded": False,
        "signed_endpoint_used": False,
        "lookahead_policy": LOOKAHEAD_POLICY,
    }
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        # The loader expects JSONL under exchange_info/ to recover
        # ``symbols`` for downstream universe filtering. Mirror the
        # symbol list into a one-line JSONL file so the loader can
        # consume it without parsing the wider snapshot.
        jsonl_path = output_root / "exchange_info" / (
            f"binance_futures_exchange_info_{ts}.jsonl"
        )
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        jsonl_payload = {
            "snapshot_date": _ms_to_iso_date(generated_at_ms),
            "generated_at_utc_ms": int(generated_at_ms),
            "symbols": payload["symbols"],
            "source": REFERENCE_SOURCE,
            "public_endpoint_only": True,
        }
        jsonl_path.write_text(
            json.dumps(jsonl_payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return path


def write_top_movers_jsonl(
    *,
    output_root: Path,
    rows: Sequence[Mapping[str, Any]],
    days: int,
    generated_at_ms: int,
    dry_run: bool,
) -> Path:
    """Write the per-day top-mover rows to
    ``<root>/top_movers/historical_<days>d_top_movers_<ts>.jsonl``."""
    ts = _ts_compact(generated_at_ms)
    path = output_root / "top_movers" / (
        f"historical_{int(days)}d_top_movers_{ts}.jsonl"
    )
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            for raw in rows:
                row = dict(raw)
                # Defence-in-depth: reject any forbidden lookahead
                # field BEFORE the row is written. The pure helpers
                # already avoid populating these, but a future patch
                # might accidentally smuggle one in.
                validate_no_lookahead_fields(
                    row,
                    context=f"builder.row[{row.get('symbol', '?')}]",
                )
                row.setdefault("schema_version", BUILDER_SCHEMA_VERSION)
                row.setdefault("source", REFERENCE_SOURCE)
                row.setdefault("lookahead_policy", LOOKAHEAD_POLICY)
                row.setdefault(
                    "audit_schema_version",
                    HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION,
                )
                row.setdefault("generated_at_utc_ms", int(generated_at_ms))
                row.setdefault("generated_at_utc", _ms_to_iso(generated_at_ms))
                fh.write(json.dumps(row, sort_keys=True))
                fh.write("\n")
    return path


def write_manifest(
    *,
    output_root: Path,
    days: int,
    timeframe: str,
    top_n: int,
    eligible_symbol_count: int,
    symbols_processed: Sequence[str],
    symbols_failed: Sequence[str],
    top_mover_record_count: int,
    exchange_info_path: Path,
    top_movers_path: Path,
    audit_window_end_ms: int,
    generated_at_ms: int,
    no_network: bool,
    dry_run: bool,
    rest_base_url: str,
    public_call_records: Sequence[PublicCallRecord],
    history_days_observed: int,
) -> Path:
    """Write the run manifest to
    ``<root>/manifests/historical_<days>d_mover_reference_manifest_<ts>.json``.
    """
    ts = _ts_compact(generated_at_ms)
    path = output_root / "manifests" / (
        f"historical_{int(days)}d_mover_reference_manifest_{ts}.json"
    )
    payload = {
        "schema_version": BUILDER_SCHEMA_VERSION,
        "audit_schema_version": HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "source_phase": "phase_11c_1c_c_b_b_b_d_a_1",
        "generated_at_utc": _ms_to_iso(generated_at_ms),
        "generated_at_utc_ms": int(generated_at_ms),
        "audit_window_end_utc": _ms_to_iso(audit_window_end_ms),
        "audit_window_end_utc_ms": int(audit_window_end_ms),
        "days_requested": int(days),
        "timeframe": str(timeframe),
        "top_n": int(top_n),
        "eligible_symbol_count": int(eligible_symbol_count),
        "symbols_processed": list(symbols_processed),
        "symbols_failed": list(symbols_failed),
        "top_mover_record_count": int(top_mover_record_count),
        "history_days_observed": int(history_days_observed),
        "source": REFERENCE_SOURCE,
        "rest_base_url": str(rest_base_url),
        "public_endpoint_allowlist": sorted(PUBLIC_MARKET_ENDPOINT_ALLOWLIST),
        "allowed_public_hosts": sorted(ALLOWED_PUBLIC_HOSTS),
        "forbidden_private_endpoints": sorted(FORBIDDEN_PRIVATE_ENDPOINTS),
        "forbidden_query_parameters": sorted(FORBIDDEN_QUERY_PARAMETERS),
        # ----- Public-only invariants (carry verbatim) -----
        "public_endpoint_only": True,
        "private_api_used": False,
        "api_key_loaded": False,
        "signed_endpoint_used": False,
        "binance_private_api_enabled": False,
        "telegram_outbound_enabled": False,
        "live_trading_enabled": False,
        "exchange_live_order_enabled": False,
        "right_tail_enabled": False,
        "llm_enabled": False,
        "trading_mode": "paper",
        # ----- Lookahead Guard invariant -----
        "lookahead_policy": LOOKAHEAD_POLICY,
        "lookahead_guard": "reference_set_is_post_hoc_audit_only",
        "lookahead_forbidden_fields": list(LOOKAHEAD_FORBIDDEN_FIELDS),
        # ----- Run mode -----
        "no_network_test_mode": bool(no_network),
        "dry_run": bool(dry_run),
        # ----- Output files -----
        "output_files": {
            "exchange_info": str(
                exchange_info_path.relative_to(output_root)
                if _is_under(exchange_info_path, output_root)
                else exchange_info_path
            ),
            "top_movers": str(
                top_movers_path.relative_to(output_root)
                if _is_under(top_movers_path, output_root)
                else top_movers_path
            ),
        },
        "public_calls": [
            {"path": rec.path, "status": rec.status}
            for rec in public_call_records
        ],
        # ----- Boundary statements -----
        "boundary": {
            "is_strategy_blind_replay": False,
            "is_pnl_backtest": False,
            "is_trading_module": False,
            "is_ai_learning": False,
            "is_parameter_optimisation": False,
            "is_reinforcement_learning": False,
            "is_phase_12": False,
            "is_small_money_pre_validation_gate": False,
            "is_post_hoc_audit_reference_only": True,
            "phase_12_remains_forbidden": True,
        },
    }
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return path


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# In-process deterministic data source (used by --no-network)
# ---------------------------------------------------------------------------


def build_no_network_source(
    *,
    audit_window_end_ms: int,
    days: int,
    symbols: Sequence[str] = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"),
    request_sleep_seconds: float = 0.0,
) -> BinanceFuturesPublicSource:
    """Return a deterministic in-process :class:`BinanceFuturesPublicSource`.

    Used by ``--no-network`` smoke tests. No socket is opened. The
    payloads are intentionally tiny but cover every column the
    builder needs to exercise.
    """
    day_ms = 24 * 60 * 60 * 1000
    end_ms = int(audit_window_end_ms) - (int(audit_window_end_ms) % day_ms)
    start_ms = end_ms - max(1, int(days)) * day_ms

    def _ticker_row(idx: int, sym: str) -> dict[str, Any]:
        return {"symbol": sym, "quoteVolume": f"{1_000_000_000.0 - idx * 1_000_000.0:.2f}"}

    def _exchange_info() -> dict[str, Any]:
        return {
            "symbols": [
                {
                    "symbol": sym,
                    "baseAsset": sym.replace("USDT", "") or sym,
                    "quoteAsset": "USDT",
                    "contractType": "PERPETUAL",
                    "status": "TRADING",
                }
                for sym in symbols
            ]
        }

    def _klines(symbol: str, start: int, end: int) -> list[list[Any]]:
        out: list[list[Any]] = []
        # 1h candles spanning [start, end). Price walks deterministically per
        # symbol so ranking is stable across runs.
        sym_idx = symbols.index(symbol) if symbol in symbols else 0
        base_price = 100.0 + 10.0 * sym_idx
        cursor = start
        while cursor < end:
            hour_idx = (cursor // (60 * 60 * 1000)) - (start // (60 * 60 * 1000))
            day_idx = (cursor - start) // day_ms
            day_progress = ((cursor - start) % day_ms) / float(day_ms)
            # Per-symbol per-day deterministic gain pattern.
            day_gain_pct = ((sym_idx + 1) * (day_idx + 1) % 7) / 100.0
            open_p = base_price * (1.0 + day_gain_pct * day_progress)
            close_p = base_price * (1.0 + day_gain_pct * (day_progress + 1.0 / 24.0))
            high_p = max(open_p, close_p) * 1.005
            low_p = min(open_p, close_p) * 0.995
            volume = 100.0 + sym_idx + (hour_idx % 7)
            quote_volume = volume * (open_p + close_p) / 2.0
            close_time = cursor + 60 * 60 * 1000 - 1
            out.append(
                [
                    cursor,
                    f"{open_p:.4f}",
                    f"{high_p:.4f}",
                    f"{low_p:.4f}",
                    f"{close_p:.4f}",
                    f"{volume:.4f}",
                    close_time,
                    f"{quote_volume:.4f}",
                    1,
                    f"{volume / 2.0:.4f}",
                    f"{quote_volume / 2.0:.4f}",
                    "0",
                ]
            )
            cursor += 60 * 60 * 1000
        return out

    def _transport(url: str) -> Any:
        parsed = urllib.parse.urlsplit(url)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)
        if path == "/fapi/v1/exchangeInfo":
            return _exchange_info()
        if path == "/fapi/v1/ticker/24hr":
            return [_ticker_row(i, s) for i, s in enumerate(symbols)]
        if path == "/fapi/v1/klines":
            sym = params.get("symbol", [""])[0]
            try:
                start = int(params.get("startTime", [str(start_ms)])[0])
            except ValueError:
                start = start_ms
            try:
                end = int(params.get("endTime", [str(end_ms)])[0])
            except ValueError:
                end = end_ms
            try:
                limit = max(1, min(int(params.get("limit", [str(KLINE_BATCH_LIMIT)])[0]), KLINE_BATCH_LIMIT))
            except ValueError:
                limit = KLINE_BATCH_LIMIT
            full = _klines(sym, start, end)
            return full[:limit]
        return {}

    return BinanceFuturesPublicSource(
        transport=_transport,
        request_sleep_seconds=request_sleep_seconds,
    )


# ---------------------------------------------------------------------------
# Build orchestrator
# ---------------------------------------------------------------------------


@dataclass
class BuildResult:
    """Returned by :func:`run_build` for tests + the CLI summary."""

    artefacts: BuilderArtefacts
    eligible_universe_size: int
    symbols_processed: list[str]
    symbols_failed: list[str]
    top_mover_record_count: int
    history_days_observed: int
    days: int
    timeframe: str
    top_n: int
    audit_window_end_ms: int
    generated_at_ms: int
    no_network: bool
    dry_run: bool
    public_call_records: list[PublicCallRecord]
    rest_base_url: str
    extra_notes: list[str] = field(default_factory=list)

    def summary_payload(self) -> dict[str, Any]:
        return {
            "builder_version": BUILDER_VERSION,
            "schema_version": BUILDER_SCHEMA_VERSION,
            "audit_schema_version": HISTORICAL_MOVER_COVERAGE_BACKFILL_SCHEMA_VERSION,
            "days_requested": int(self.days),
            "timeframe": str(self.timeframe),
            "top_n": int(self.top_n),
            "eligible_symbol_count": int(self.eligible_universe_size),
            "symbols_processed_count": int(len(self.symbols_processed)),
            "symbols_failed_count": int(len(self.symbols_failed)),
            "symbols_processed": list(self.symbols_processed),
            "symbols_failed": list(self.symbols_failed),
            "top_mover_record_count": int(self.top_mover_record_count),
            "history_days_observed": int(self.history_days_observed),
            "audit_window_end_utc": _ms_to_iso(self.audit_window_end_ms),
            "generated_at_utc": _ms_to_iso(self.generated_at_ms),
            "rest_base_url": str(self.rest_base_url),
            "no_network_test_mode": bool(self.no_network),
            "dry_run": bool(self.dry_run),
            "public_endpoint_only": True,
            "private_api_used": False,
            "api_key_loaded": False,
            "signed_endpoint_used": False,
            "binance_private_api_enabled": False,
            "telegram_outbound_enabled": False,
            "live_trading_enabled": False,
            "exchange_live_order_enabled": False,
            "right_tail_enabled": False,
            "llm_enabled": False,
            "trading_mode": "paper",
            "lookahead_policy": LOOKAHEAD_POLICY,
            "lookahead_guard": "reference_set_is_post_hoc_audit_only",
            "phase_12_remains_forbidden": True,
            "output_files": {
                "exchange_info": str(self.artefacts.exchange_info_path),
                "top_movers": str(self.artefacts.top_movers_path),
                "manifest": str(self.artefacts.manifest_path),
            },
            "extra_notes": list(self.extra_notes),
        }


def run_build(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    days: int = DEFAULT_DAYS,
    timeframe: str = DEFAULT_TIMEFRAME,
    top_n: int = DEFAULT_TOP_N,
    symbol_limit: int | None = None,
    rest_base_url: str = DEFAULT_REST_BASE_URL,
    audit_window_end_ms: int | None = None,
    request_sleep_seconds: float = DEFAULT_REQUEST_SLEEP_SECONDS,
    dry_run: bool = False,
    no_network: bool = False,
    source: BinanceFuturesPublicSource | None = None,
    env: Mapping[str, str] | None = None,
) -> BuildResult:
    """Run the full builder pipeline and return a :class:`BuildResult`.

    The function is the single entry point used by both the CLI and
    the test suite. ``source`` may be a pre-built
    :class:`BinanceFuturesPublicSource` (the test-friendly path);
    when ``None`` the function builds one according to ``no_network``.

    The function NEVER reads a Binance API key, NEVER calls a signed
    endpoint, and NEVER writes to disk when ``dry_run=True``.
    """
    assert_no_credentials_in_env(env)

    if days <= 0:
        raise ValueError(f"days must be positive, got {days}")
    if top_n <= 0:
        raise ValueError(f"top_n must be positive, got {top_n}")
    if timeframe not in ALLOWED_TIMEFRAMES:
        raise ValueError(
            f"timeframe {timeframe!r} is not in the builder allowlist; "
            f"allowed: {ALLOWED_TIMEFRAMES}"
        )

    output_root = Path(output_dir).resolve()

    end_ms = int(
        audit_window_end_ms if audit_window_end_ms is not None else _utc_now_ms()
    )
    day_ms = 24 * 60 * 60 * 1000
    end_ms = end_ms - (end_ms % day_ms)
    start_ms = end_ms - days * day_ms
    generated_at_ms = _utc_now_ms()

    if source is None:
        if no_network:
            source = build_no_network_source(
                audit_window_end_ms=end_ms,
                days=days,
                request_sleep_seconds=request_sleep_seconds,
            )
        else:
            source = BinanceFuturesPublicSource(
                base_url=rest_base_url,
                request_sleep_seconds=request_sleep_seconds,
            )

    extra_notes: list[str] = []

    # 1. Eligible universe.
    exchange_info = source.fetch_exchange_info()
    eligible_universe = filter_eligible_usdt_perpetual_universe(exchange_info)
    extra_notes.append(
        f"eligible_usdt_perpetual_universe_size={len(eligible_universe)}"
    )

    # 2. Optional 24h-volume ranking.
    tickers_24h: list[Mapping[str, Any]] = []
    if symbol_limit and symbol_limit > 0:
        try:
            tickers_24h = source.fetch_24h_tickers()
        except Exception as exc:  # pragma: no cover - defensive
            extra_notes.append(f"ticker_24hr_fetch_failed: {exc!s}")
            tickers_24h = []
    selected_symbols = select_symbols_by_volume(
        eligible_universe=eligible_universe,
        tickers_24h=tickers_24h,
        symbol_limit=symbol_limit,
    )
    extra_notes.append(f"selected_symbol_count={len(selected_symbols)}")

    # 3. Per-symbol kline fetch.
    klines_by_symbol: dict[str, list[list[Any]]] = {}
    symbols_processed: list[str] = []
    symbols_failed: list[str] = []
    for symbol in selected_symbols:
        try:
            rows = source.fetch_klines(
                symbol,
                interval=timeframe,
                start_ms=start_ms,
                end_ms=end_ms,
                limit=KLINE_BATCH_LIMIT,
            )
            if rows:
                klines_by_symbol[symbol] = rows
                symbols_processed.append(symbol)
            else:
                symbols_failed.append(symbol)
        except SafeModeViolation:
            raise
        except Exception as exc:
            symbols_failed.append(symbol)
            extra_notes.append(f"kline_fetch_failed[{symbol}]={exc!s}")

    # 4. Build per-day top-mover rows.
    metadata = {
        str(row["symbol"]): {
            "quote_asset": row.get("quote_asset", "USDT"),
            "contract_type": row.get("contract_type", "PERPETUAL"),
            "eligible_usdt_perpetual": True,
        }
        for row in eligible_universe
    }
    top_mover_rows = klines_to_daily_top_movers(
        klines_by_symbol=klines_by_symbol,
        days=days,
        top_n=top_n,
        audit_window_end_ms=end_ms,
        timeframe=timeframe,
        symbol_metadata=metadata,
    )

    # 5. Write artefacts (or pretend, in --dry-run).
    exchange_info_path = write_exchange_info_snapshot(
        output_root=output_root,
        eligible_universe=eligible_universe,
        generated_at_ms=generated_at_ms,
        dry_run=dry_run,
    )
    top_movers_path = write_top_movers_jsonl(
        output_root=output_root,
        rows=top_mover_rows,
        days=days,
        generated_at_ms=generated_at_ms,
        dry_run=dry_run,
    )

    history_days_observed = len({r["snapshot_date"] for r in top_mover_rows})

    manifest_path = write_manifest(
        output_root=output_root,
        days=days,
        timeframe=timeframe,
        top_n=top_n,
        eligible_symbol_count=len(eligible_universe),
        symbols_processed=symbols_processed,
        symbols_failed=symbols_failed,
        top_mover_record_count=len(top_mover_rows),
        exchange_info_path=exchange_info_path,
        top_movers_path=top_movers_path,
        audit_window_end_ms=end_ms,
        generated_at_ms=generated_at_ms,
        no_network=no_network,
        dry_run=dry_run,
        rest_base_url=source.base_url,
        public_call_records=source.call_records,
        history_days_observed=history_days_observed,
    )

    artefacts = BuilderArtefacts(
        exchange_info_path=exchange_info_path,
        top_movers_path=top_movers_path,
        manifest_path=manifest_path,
        written=not dry_run,
    )

    return BuildResult(
        artefacts=artefacts,
        eligible_universe_size=len(eligible_universe),
        symbols_processed=symbols_processed,
        symbols_failed=symbols_failed,
        top_mover_record_count=len(top_mover_rows),
        history_days_observed=history_days_observed,
        days=days,
        timeframe=timeframe,
        top_n=top_n,
        audit_window_end_ms=end_ms,
        generated_at_ms=generated_at_ms,
        no_network=no_network,
        dry_run=dry_run,
        public_call_records=list(source.call_records),
        rest_base_url=source.base_url,
        extra_notes=extra_notes,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="build_historical_mover_reference_store",
        description=(
            "Phase 11C.1C-C-B-B-B-D-A.1 - build the local Historical 60D "
            "Mover Reference Store from Binance public futures endpoints. "
            "Public-only, no API key, post-hoc audit reference only. "
            "NOT a strategy blind replay. NOT a PnL backtest. NOT a "
            "trading module. NOT live trading. Phase 12 remains FORBIDDEN."
        ),
    )
    p.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"trailing-window length in days (default {DEFAULT_DAYS}).",
    )
    p.add_argument(
        "--timeframe",
        type=str,
        default=DEFAULT_TIMEFRAME,
        choices=ALLOWED_TIMEFRAMES,
        help=f"kline timeframe (default {DEFAULT_TIMEFRAME}).",
    )
    p.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        dest="top_n",
        help=f"top-N movers per day (default {DEFAULT_TOP_N}).",
    )
    p.add_argument(
        "--symbol-limit",
        type=int,
        default=None,
        dest="symbol_limit",
        help=(
            "max number of symbols to process; ranked by 24h quote "
            "volume. Defaults to no cap (all eligible USDT perpetuals)."
        ),
    )
    p.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        dest="output_dir",
        help=(
            "output directory root, relative to repo root. The audit's "
            "``load_historical_market_store(root)`` call expects this "
            "exact layout. Default: data/historical_market_store."
        ),
    )
    p.add_argument(
        "--rest-base-url",
        type=str,
        default=DEFAULT_REST_BASE_URL,
        dest="rest_base_url",
        help="Binance public futures REST base URL.",
    )
    p.add_argument(
        "--audit-window-end-utc-ms",
        type=int,
        default=None,
        dest="audit_window_end_utc_ms",
        help=(
            "explicit UTC ms timestamp for the audit window's end. "
            "Defaults to the current UTC day boundary. Useful for "
            "reproducible smoke tests."
        ),
    )
    p.add_argument(
        "--request-sleep-seconds",
        type=float,
        default=DEFAULT_REQUEST_SLEEP_SECONDS,
        dest="request_sleep_seconds",
        help=(
            "sleep between REST requests, in seconds. Reduces pressure "
            f"on the Phase 11C.1A rate-limit governor (default {DEFAULT_REQUEST_SLEEP_SECONDS}s)."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        default=False,
        help=(
            "compute the artefacts but do NOT write to disk; print a "
            "summary of what would have been written."
        ),
    )
    p.add_argument(
        "--no-network",
        action="store_true",
        dest="no_network",
        default=False,
        help=(
            "use the deterministic in-process data source instead of "
            "the real network. Exists for CI smoke tests and local "
            "development. Equivalent to the brief's "
            "``--no-network-test-mode``."
        ),
    )
    # Compatibility alias for the brief's exact wording.
    p.add_argument(
        "--no-network-test-mode",
        action="store_true",
        dest="no_network",
        default=False,
        help=argparse.SUPPRESS,
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        dest="quiet",
        default=False,
        help="suppress per-symbol log output.",
    )
    return p


def _print_summary(result: BuildResult) -> None:
    summary = result.summary_payload()
    print(json.dumps(summary, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        result = run_build(
            output_dir=args.output_dir,
            days=int(args.days),
            timeframe=str(args.timeframe),
            top_n=int(args.top_n),
            symbol_limit=(
                int(args.symbol_limit)
                if args.symbol_limit is not None and int(args.symbol_limit) > 0
                else None
            ),
            rest_base_url=str(args.rest_base_url),
            audit_window_end_ms=(
                int(args.audit_window_end_utc_ms)
                if args.audit_window_end_utc_ms is not None
                else None
            ),
            request_sleep_seconds=float(args.request_sleep_seconds),
            dry_run=bool(args.dry_run),
            no_network=bool(args.no_network),
        )
    except SafeModeViolation as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except HistoricalMoverLookaheadGuardError as exc:
        print(f"LOOKAHEAD GUARD: {exc}", file=sys.stderr)
        return 3
    except (ValueError, RuntimeError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:  # pragma: no cover - defensive
        print(f"UNEXPECTED ERROR: {exc}", file=sys.stderr)
        return 5

    _print_summary(result)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
