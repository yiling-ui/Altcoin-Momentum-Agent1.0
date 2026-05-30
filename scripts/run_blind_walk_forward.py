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
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

# Allow ``python scripts/run_blind_walk_forward.py`` (not only
# ``python -m scripts.run_blind_walk_forward``) by ensuring the project
# root is importable. Mirrors the sibling run_*.py scripts. This adds
# no runtime authority and imports nothing here.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.sim import (  # noqa: E402
    BlindRunStatus,
    BlindWalkForwardRunner,
    BlindWalkForwardRunnerConfig,
    BlindWalkForwardWindow,
    HistoricalKlineRecord,
    HistoricalMarketRecord,
    HistoricalMarketStore,
    MockExchange,
    PaperShadowStrategyBridge,
    PaperShadowStrategyBridgeConfig,
    ReplayFeedProvider,
    ReplayFeedProviderConfig,
    SimulatedCapitalConfig,
    SimulatedCapitalFlowEngine,
    SimulationClock,
    SymbolStatusRecord,
    TelegramSandboxOutbox,
    TelegramSandboxOutboxConfig,
    assert_no_forbidden_fields,
    blind_walk_forward_safety_payload,
)
from app.sim.paper_shadow_strategy_bridge import (  # noqa: E402
    DEFAULT_BRIDGE_NAME,
)
from app.sim.core_strategy_bridge import (  # noqa: E402
    DEFAULT_CORE_BRIDGE_NAME,
    CoreStrategyBridge,
    CoreStrategyBridgeConfig,
)


PHASE_NAME: str = (
    "Phase 11C.1D-D-I / PR103 / Blind Runner Historical Store "
    "Input Glue"
)

# File names produced by PR101 Historical Data Ingestion under a
# Historical Data Store directory (see
# ``app/sim/historical_data_ingestion.py::write_outputs``).
RECORDS_FILENAME: str = "records.jsonl"
DATA_MANIFEST_FILENAME: str = "historical_data_manifest.json"
UNIVERSE_MANIFEST_FILENAME: str = "universe_manifest.json"


# PR104: progress logger for the operator entry point. Heartbeats and
# load progress go through ``logging`` (NOT stdout) so the operator JSON
# summary printed at the end stays machine-parseable.
_LOGGER = logging.getLogger("scripts.run_blind_walk_forward")


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_opt_dt(value: Any) -> Optional[datetime]:
    """Parse an optional ISO-8601 timestamp from a records.jsonl field.

    Accepts ``None`` (returns ``None``), an existing ``datetime``, or a
    string (``Z`` suffix is normalised to ``+00:00``). Naive results
    are pinned to UTC. This is a pure parse; it NEVER invents a
    timestamp.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# PR103 - Historical Store input glue (records.jsonl -> store)
# ---------------------------------------------------------------------------


def _record_from_dict(d: Mapping[str, Any]):
    """Reconstruct one PR95 record from its ``to_dict()`` serialisation.

    Dispatch is driven by the explicit ``is_*`` marker emitted by the
    PR95 record ``to_dict()`` (falling back to ``record_type`` if the
    marker is absent). This loader ONLY restores fields that were
    serialised by PR101's ``records.jsonl`` dump; it never fabricates
    OHLCV, timestamps, or symbol metadata. The reconstructed record
    re-runs every PR95 construction-time invariant (e.g. kline
    ``available_at >= close_time``).
    """
    if not isinstance(d, Mapping):
        raise ValueError(
            "each records.jsonl line must decode to a JSON object"
        )
    is_kline = bool(d.get("is_historical_kline_record"))
    is_symbol = bool(d.get("is_symbol_status_record"))
    is_market = bool(d.get("is_historical_market_record"))
    rtype = d.get("record_type")
    if not (is_kline or is_symbol or is_market):
        if rtype in ("KLINE_1M", "KLINE_5M"):
            is_kline = True
        elif rtype in (
            "SYMBOL_STATUS",
            "LISTING_STATUS",
            "DELISTING_STATUS",
        ):
            is_symbol = True
        else:
            is_market = True

    flags = tuple(d.get("data_quality_flags") or ())
    refs = tuple(d.get("evidence_refs") or ())

    if is_kline:
        return HistoricalKlineRecord(
            symbol=d["symbol"],
            interval=d["interval"],
            open_time=_parse_opt_dt(d["open_time"]),
            open=float(d["open"]),
            high=float(d["high"]),
            low=float(d["low"]),
            close=float(d["close"]),
            volume=float(d["volume"]),
            available_at=_parse_opt_dt(d["available_at"]),
            close_time=_parse_opt_dt(d.get("close_time")),
            event_time=_parse_opt_dt(d.get("event_time")),
            ingested_at=_parse_opt_dt(d.get("ingested_at")),
            source=d.get("source"),
            record_id=d.get("record_id"),
            data_quality_flags=flags,
            evidence_refs=refs,
            revision_time=_parse_opt_dt(d.get("revision_time")),
            revised_from_record_id=d.get("revised_from_record_id"),
            late_arrival=bool(d.get("late_arrival", False)),
        )
    if is_symbol:
        return SymbolStatusRecord(
            symbol=d["symbol"],
            market_type=d["market_type"],
            listed_at=_parse_opt_dt(d["listed_at"]),
            status=d["status"],
            available_at=_parse_opt_dt(d["available_at"]),
            delisted_at=_parse_opt_dt(d.get("delisted_at")),
            min_notional=d.get("min_notional"),
            tick_size=d.get("tick_size"),
            step_size=d.get("step_size"),
            contract_type=d.get("contract_type"),
            data_completeness_state=d.get(
                "data_completeness_state", "OK"
            ),
            source=d.get("source"),
            ingested_at=_parse_opt_dt(d.get("ingested_at")),
            record_id=d.get("record_id"),
            event_time=_parse_opt_dt(d.get("event_time")),
            data_quality_flags=flags,
            evidence_refs=refs,
            revision_time=_parse_opt_dt(d.get("revision_time")),
            revised_from_record_id=d.get("revised_from_record_id"),
            late_arrival=bool(d.get("late_arrival", False)),
        )
    return HistoricalMarketRecord(
        record_id=d["record_id"],
        record_type=rtype,
        symbol=d.get("symbol"),
        event_time=_parse_opt_dt(d["event_time"]),
        available_at=_parse_opt_dt(d["available_at"]),
        ingested_at=_parse_opt_dt(d.get("ingested_at")),
        source=d.get("source"),
        interval=d.get("interval"),
        payload=d.get("payload") or {},
        data_quality_flags=flags,
        evidence_refs=refs,
        revision_time=_parse_opt_dt(d.get("revision_time")),
        revised_from_record_id=d.get("revised_from_record_id"),
        late_arrival=bool(d.get("late_arrival", False)),
    )


def load_records_jsonl(
    path: Any,
    *,
    max_available_at: Optional[datetime] = None,
    min_available_at: Optional[datetime] = None,
) -> List[Any]:
    """Load PR95 records from a PR101 ``records.jsonl`` dump.

    Returns a list of reconstructed record objects in file order.
    Blank lines are skipped. Raises :class:`FileNotFoundError` when the
    file is absent (the caller maps this to ``INSUFFICIENT_EVIDENCE`` -
    we never fabricate records for a missing file).

    PR104 - bounded loading. When ``max_available_at`` /
    ``min_available_at`` are supplied, a record is only *materialised*
    (its heavy, fully-validated PR95 dataclass constructed) when its
    ``available_at`` falls inside ``[min_available_at, max_available_at]``.
    The cheap ``available_at`` string is read straight off the decoded
    JSON line first, so records that can never become visible inside the
    replay window (e.g. ~6 days of a 7-day store when only a 1-day blind
    window is replayed) are skipped before they ever allocate a record
    object. This is the load-side half of the fix that kept the blind
    runner's RES from climbing to ~16 GB on a real public 7-day store.

    The bound is applied ONLY to records that actually carry an
    ``available_at``; a record with a missing/None ``available_at`` is
    always kept (we never silently drop data we cannot place in time).
    Both defaults are ``None`` => unbounded => byte-for-byte the legacy
    behaviour.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"records.jsonl not found: {p}")
    bounded = max_available_at is not None or min_available_at is not None
    records: List[Any] = []
    skipped_out_of_window = 0
    seen_lines = 0
    with open(p, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            seen_lines += 1
            d = json.loads(line)
            if bounded:
                av = _parse_opt_dt(d.get("available_at"))
                if av is not None:
                    if (
                        max_available_at is not None
                        and av > max_available_at
                    ):
                        skipped_out_of_window += 1
                        continue
                    if (
                        min_available_at is not None
                        and av < min_available_at
                    ):
                        skipped_out_of_window += 1
                        continue
            records.append(_record_from_dict(d))
    if bounded and skipped_out_of_window:
        _LOGGER.info(
            "bounded record load: kept=%d skipped_out_of_window=%d "
            "(min_available_at=%s max_available_at=%s) source=%s",
            len(records),
            skipped_out_of_window,
            min_available_at.isoformat()
            if min_available_at is not None
            else None,
            max_available_at.isoformat()
            if max_available_at is not None
            else None,
            p,
        )
    return records


def build_historical_store_from_records(
    records: Iterable[Any],
) -> HistoricalMarketStore:
    """Build a :class:`HistoricalMarketStore` and add ``records``.

    The store keeps the PR94 ``TimeWallGuard`` / closed-candle
    visibility guard fully in force. This helper only restores rows; it
    never relaxes the ``available_at <= simulated_time`` gate that the
    PR96 :class:`ReplayFeedProvider` later enforces.
    """
    store = HistoricalMarketStore()
    store.add_records(list(records))
    return store


@dataclass
class HistoricalStoreInput:
    """Result of loading a PR101/PR102 Historical Data Store directory.

    ``status`` is ``None`` on success or
    :data:`BlindRunStatus.INSUFFICIENT_EVIDENCE` when ``records.jsonl``
    is missing or empty (no data is fabricated). ``data_manifest_hash``
    / ``universe_manifest_hash`` are the *real* ``sha256:`` content
    hashes read straight out of the PR101 manifests when present.
    """

    store: HistoricalMarketStore
    record_count: int
    status: Optional[str] = None
    detail: Optional[str] = None
    data_manifest_hash: Optional[str] = None
    universe_manifest_hash: Optional[str] = None
    source_files: Tuple[str, ...] = ()
    record_counts_by_type: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def load_historical_store_dir(
    *,
    store_dir: Optional[str] = None,
    records_path: Optional[str] = None,
    data_manifest_path: Optional[str] = None,
    universe_manifest_path: Optional[str] = None,
    max_available_at: Optional[datetime] = None,
    min_available_at: Optional[datetime] = None,
) -> HistoricalStoreInput:
    """Load a PR101/PR102 Historical Data Store into a
    :class:`HistoricalMarketStore`.

    When ``store_dir`` is given, the standard PR101 layout is assumed:

      * ``<store_dir>/records.jsonl``                  (mandatory)
      * ``<store_dir>/historical_data_manifest.json``  (optional, WARN)
      * ``<store_dir>/universe_manifest.json``         (optional, WARN)

    Any of the three paths may be overridden individually.

    Contract:

      * Missing or empty ``records.jsonl`` ->
        ``status = INSUFFICIENT_EVIDENCE`` (NEVER fabricate data).
      * Missing ``historical_data_manifest.json`` -> WARN; the real
        ``data_manifest_hash`` is simply absent (NEVER fabricated).
      * Missing ``universe_manifest.json`` -> WARN; kline-only short
        smoke is NOT blocked.

    PR104 - bounded loading. ``max_available_at`` / ``min_available_at``
    are forwarded to :func:`load_records_jsonl` so records that can
    never become visible inside the replay window are skipped before
    they allocate a record object. Both default to ``None`` (unbounded,
    legacy behaviour). When a bound filters every record out, the result
    is still ``INSUFFICIENT_EVIDENCE`` (no visible evidence in window) -
    we never fabricate data to fill the gap.
    """
    warnings: List[str] = []
    if store_dir is not None:
        base = Path(store_dir)
        records_path = records_path or str(base / RECORDS_FILENAME)
        data_manifest_path = data_manifest_path or str(
            base / DATA_MANIFEST_FILENAME
        )
        universe_manifest_path = universe_manifest_path or str(
            base / UNIVERSE_MANIFEST_FILENAME
        )
    if records_path is None:
        raise ValueError(
            "load_historical_store_dir requires either store_dir or "
            "records_path"
        )

    # 1) records.jsonl - mandatory.
    rp = Path(records_path)
    if not rp.exists():
        return HistoricalStoreInput(
            store=HistoricalMarketStore(),
            record_count=0,
            status=BlindRunStatus.INSUFFICIENT_EVIDENCE,
            detail=f"records.jsonl missing: {rp}",
            warnings=warnings,
        )
    records = load_records_jsonl(
        rp,
        max_available_at=max_available_at,
        min_available_at=min_available_at,
    )
    if not records:
        bounded = (
            max_available_at is not None or min_available_at is not None
        )
        detail = (
            f"records.jsonl has no records inside replay window: {rp}"
            if bounded
            else f"records.jsonl empty: {rp}"
        )
        return HistoricalStoreInput(
            store=HistoricalMarketStore(),
            record_count=0,
            status=BlindRunStatus.INSUFFICIENT_EVIDENCE,
            detail=detail,
            warnings=warnings,
        )
    store = build_historical_store_from_records(records)

    # 2) historical_data_manifest.json - optional (WARN if missing).
    data_manifest_hash: Optional[str] = None
    source_files: Tuple[str, ...] = ()
    record_counts_by_type: Dict[str, Any] = {}
    dmp = Path(data_manifest_path) if data_manifest_path else None
    if dmp is not None and dmp.exists():
        data_manifest = json.loads(dmp.read_text(encoding="utf-8"))
        h = data_manifest.get("data_manifest_hash")
        if isinstance(h, str) and h.startswith("sha256:"):
            data_manifest_hash = h
        else:
            warnings.append(
                "historical_data_manifest.json present but "
                "data_manifest_hash missing/invalid; not fabricating "
                "a hash"
            )
        source_files = tuple(data_manifest.get("source_files") or ())
        record_counts_by_type = dict(
            data_manifest.get("record_counts_by_type") or {}
        )
    else:
        warnings.append(
            "historical_data_manifest.json missing; data_manifest_hash "
            "left to hash-of-inline-artefact (NOT fabricated)"
        )

    # 3) universe_manifest.json - optional, MUST NOT block kline-only.
    universe_manifest_hash: Optional[str] = None
    ump = (
        Path(universe_manifest_path) if universe_manifest_path else None
    )
    if ump is not None and ump.exists():
        universe_manifest = json.loads(ump.read_text(encoding="utf-8"))
        h = universe_manifest.get("universe_manifest_hash")
        if isinstance(h, str) and h.startswith("sha256:"):
            universe_manifest_hash = h
        else:
            warnings.append(
                "universe_manifest.json present but "
                "universe_manifest_hash missing/invalid; not "
                "fabricating a hash"
            )
    else:
        warnings.append(
            "universe_manifest.json missing; proceeding kline-only "
            "(universe_manifest_hash left to hash-of-inline-artefact)"
        )

    return HistoricalStoreInput(
        store=store,
        record_count=len(records),
        status=None,
        detail=None,
        data_manifest_hash=data_manifest_hash,
        universe_manifest_hash=universe_manifest_hash,
        source_files=source_files,
        record_counts_by_type=record_counts_by_type,
        warnings=warnings,
    )


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
    # ----- PR108: Simulated Capital Safety Floor / Kill Switch -----
    p.add_argument(
        "--capital-floor",
        type=float,
        default=0.0,
        help=(
            "PR108: hard floor (base ccy) below which the simulated "
            "equity can NEVER silently fall. Default 0.0 (no negative "
            "equity). Paper-only; NEVER a live-capital marker."
        ),
    )
    p.add_argument(
        "--max-drawdown-halt-pct",
        type=float,
        default=0.5,
        help=(
            "PR108: hard drawdown kill switch (fraction in (0,1]). When "
            "the marked drawdown reaches this the runner force-exits "
            "every open simulated position and stops accepting new "
            "entries for the rest of the blind window. Default 0.5 "
            "(conservative for a 100 USDT sim). Pass 0 to disable."
        ),
    )
    p.add_argument(
        "--disable-no-negative-equity-guard",
        action="store_true",
        help=(
            "PR108: disable the no-negative-equity guard (NOT "
            "recommended). When set the simulated equity is no longer "
            "clamped at the capital floor. Default OFF (guard ON)."
        ),
    )
    p.add_argument(
        "--min-equity-to-open",
        type=float,
        default=None,
        help=(
            "PR108: minimum free simulated equity required to OPEN a "
            "new position. Default unset => require free equity >= the "
            "position's own notional (no exposure it cannot cover)."
        ),
    )
    p.add_argument(
        "--no-ai-post-window-summary",
        action="store_true",
        help="disable the offline post-window AI commentary template",
    )
    # ----- PR106: Paper Shadow Strategy Bridge (opt-in) -----
    p.add_argument(
        "--enable-paper-shadow-strategy",
        action="store_true",
        help=(
            "PR106: enable the deterministic, paper-only Paper Shadow "
            "Strategy Bridge as the runner's decision path. When set, "
            "the runner can produce SIMULATED entry / exit / fill / "
            "PnL via the MockExchange + Simulated Capital Flow when a "
            "valid as-of signal occurs. Default OFF (substrate-only "
            "v0 behaviour). This NEVER authorises live trading, "
            "auto-tuning, AI trade authority, real Telegram outbound, "
            "the Binance private API, or Phase 12."
        ),
    )
    p.add_argument(
        "--paper-shadow-bridge-name",
        default=DEFAULT_BRIDGE_NAME,
        help=(
            "name recorded into the blind report's "
            "strategy_bridge_name (default deterministic baseline)"
        ),
    )
    p.add_argument(
        "--paper-shadow-timeframe",
        default="1m",
        choices=("1m", "5m"),
        help="closed-candle timeframe the bridge consumes (default 1m)",
    )
    p.add_argument(
        "--paper-shadow-breakout-lookback",
        type=int,
        default=10,
        help="rolling lookback (closed bars) for the breakout trigger",
    )
    p.add_argument(
        "--paper-shadow-volume-multiplier",
        type=float,
        default=1.5,
        help="volume-expansion multiplier vs the rolling mean volume",
    )
    p.add_argument(
        "--paper-shadow-max-hold-bars",
        type=int,
        default=15,
        help="maximum bars to hold a simulated position before exit",
    )
    p.add_argument(
        "--paper-shadow-take-profit-pct",
        type=float,
        default=0.02,
        help="fixed take-profit fraction for the simulated exit",
    )
    p.add_argument(
        "--paper-shadow-stop-loss-pct",
        type=float,
        default=0.01,
        help="fixed stop-loss fraction for the simulated exit",
    )
    p.add_argument(
        "--paper-shadow-position-notional",
        type=float,
        default=20.0,
        help="fixed notional (quote ccy) per simulated entry",
    )
    p.add_argument(
        "--paper-shadow-max-concurrent-positions",
        type=int,
        default=3,
        help="maximum concurrent simulated positions across symbols",
    )
    # ----- PR109: Core Strategy Sim-Live Bridge (opt-in) -----
    p.add_argument(
        "--strategy-profile",
        default="baseline",
        choices=("baseline", "core"),
        help=(
            "PR109: which strategy expresses the blind run's decision "
            "path. 'baseline' = the PR106 baseline_breakout_volume_v0 "
            "paper-shadow rule (requires --enable-paper-shadow-strategy "
            "to actually trade). 'core' = the AMA-RT core strategy "
            "decision lifecycle (market regime -> candidate stage -> "
            "opportunity score -> strategy selector) bridged in via a "
            "CoreStrategyBridge. Selecting 'core' implies the bridge is "
            "built and used. This NEVER authorises live trading, "
            "auto-tuning, AI trade authority, real Telegram outbound, "
            "the Binance private API, or Phase 12."
        ),
    )
    p.add_argument(
        "--enable-core-strategy-sim-live",
        action="store_true",
        help=(
            "PR109: alias for --strategy-profile core. Enable the "
            "AMA-RT core strategy decision lifecycle as the runner's "
            "deterministic, paper-only decision path. Paper-only; "
            "MockExchange + Simulated Capital Flow + PR108 safety floor "
            "only. NEVER live trading / private API / real orders / "
            "real capital / AI trade authority / Phase 12."
        ),
    )
    p.add_argument(
        "--core-bridge-name",
        default=DEFAULT_CORE_BRIDGE_NAME,
        help=(
            "name recorded into the blind report's strategy_bridge_name "
            "when --strategy-profile core (default core strategy v0)"
        ),
    )
    p.add_argument(
        "--core-momentum-lookback",
        type=int,
        default=3,
        help=(
            "core: recent CLOSED-bar window used to measure the "
            "momentum that ignites a follow/pullback entry (must be < "
            "--paper-shadow-breakout-lookback)"
        ),
    )
    p.add_argument(
        "--core-momentum-full-scale-pct",
        type=float,
        default=0.05,
        help=(
            "core: recent return that maps to a full (100) "
            "momentum_strength score input"
        ),
    )
    p.add_argument(
        "--core-volume-full-scale-ratio",
        type=float,
        default=2.0,
        help=(
            "core: volume-vs-rolling-mean ratio that maps to a full "
            "(100) volume_expansion score input"
        ),
    )
    p.add_argument(
        "--core-liquidity-reference-quote-volume",
        type=float,
        default=500_000.0,
        help=(
            "core: quote-volume (close*volume) that maps to a full "
            "(100) liquidity_quality score input"
        ),
    )
    p.add_argument(
        "--core-late-chase-full-scale-pct",
        type=float,
        default=0.20,
        help=(
            "core: total run-up over the rolling window that maps to a "
            "full (100) late_chase_risk score input"
        ),
    )
    p.add_argument(
        "--core-manipulation-wick-scale",
        type=float,
        default=1.0,
        help=(
            "core: upper-wick-fraction multiplier mapped to the "
            "manipulation_risk score input"
        ),
    )
    p.add_argument(
        "--core-min-opportunity-score",
        type=float,
        default=50.0,
        help=(
            "core: minimum opportunity score required to act on a "
            "follow/pullback mode (the core selector still gates the "
            "mode itself)"
        ),
    )
    p.add_argument(
        "--core-no-scale-notional-by-regime",
        action="store_true",
        help=(
            "core: disable scaling the per-entry notional by the regime "
            "risk multiplier (default: scale ON, the core risk path)"
        ),
    )
    # ----- PR103: Historical Store input glue -----
    p.add_argument(
        "--historical-store-dir",
        default=None,
        help=(
            "directory holding a PR101/PR102 Historical Data Store "
            "(reads <dir>/records.jsonl, "
            "<dir>/historical_data_manifest.json, "
            "<dir>/universe_manifest.json). When omitted the runner "
            "uses an empty substrate (v0 behaviour)."
        ),
    )
    p.add_argument(
        "--load-full-store",
        action="store_true",
        help=(
            "PR104: load EVERY record in the store regardless of the "
            "blind window. By default the loader is bounded to records "
            "whose available_at <= --blind-end so a 1-day blind window "
            "over a multi-day store does not materialise (or scan) the "
            "out-of-window tail. Use this flag only for an explicit "
            "full-store smoke; it can re-introduce the large-memory "
            "load on big stores."
        ),
    )
    p.add_argument(
        "--records-path",
        default=None,
        help=(
            "explicit path to records.jsonl (overrides "
            "<historical-store-dir>/records.jsonl)"
        ),
    )
    p.add_argument(
        "--historical-data-manifest-path",
        default=None,
        help=(
            "explicit path to historical_data_manifest.json "
            "(overrides <historical-store-dir>/"
            "historical_data_manifest.json)"
        ),
    )
    p.add_argument(
        "--universe-manifest-path",
        default=None,
        help=(
            "explicit path to universe_manifest.json (overrides "
            "<historical-store-dir>/universe_manifest.json)"
        ),
    )
    return p


def main(argv: List[str] = None) -> int:
    args = _build_argparser().parse_args(argv)
    # PR104: surface runner heartbeats / bounded-load progress at INFO.
    # basicConfig is a no-op if logging is already configured (e.g. by a
    # test harness), so it never clobbers an existing setup and never
    # writes to stdout (default stream is stderr) - the operator JSON
    # summary printed below stays machine-parseable.
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
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

    # PR103: when a Historical Data Store is supplied, load
    # records.jsonl into the store and pin the real data / universe
    # manifest hashes. Otherwise fall back to the v0 empty substrate.
    historical_input: Optional[HistoricalStoreInput] = None
    use_historical = bool(
        args.historical_store_dir
        or args.records_path
        or args.historical_data_manifest_path
        or args.universe_manifest_path
    )
    if use_historical:
        # PR104: bound the loader to the replay window unless the
        # operator explicitly opts into a full-store load. We bound the
        # UPPER edge by blind_end (records whose available_at is after
        # blind_end can never become visible during the blind window).
        # We deliberately do NOT set a lower bound: records available
        # before blind_start (e.g. the as-of symbol-status universe and
        # any warm-up klines) remain visible at the first tick and are
        # still needed.
        load_max_available_at = None if args.load_full_store else blind_end
        historical_input = load_historical_store_dir(
            store_dir=args.historical_store_dir,
            records_path=args.records_path,
            data_manifest_path=args.historical_data_manifest_path,
            universe_manifest_path=args.universe_manifest_path,
            max_available_at=load_max_available_at,
        )
        if (
            historical_input.status
            == BlindRunStatus.INSUFFICIENT_EVIDENCE
        ):
            # No data was fabricated; report and stop before running.
            insufficient = {
                "phase": PHASE_NAME,
                "status": BlindRunStatus.INSUFFICIENT_EVIDENCE,
                "detail": historical_input.detail,
                "historical_store_dir": args.historical_store_dir,
                "records_path": args.records_path,
                "record_count": historical_input.record_count,
                "warnings": list(historical_input.warnings),
                "ran_blind_window": False,
            }
            insufficient.update(blind_walk_forward_safety_payload())
            insufficient["phase"] = PHASE_NAME
            assert_no_forbidden_fields(insufficient)
            print(
                json.dumps(
                    insufficient,
                    sort_keys=True,
                    indent=2,
                    default=str,
                )
            )
            return 3
        store = historical_input.store
    else:
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
            initial_capital=float(args.initial_capital),
            capital_floor=float(args.capital_floor),
            no_negative_equity_guard=(
                not args.disable_no_negative_equity_guard
            ),
            halt_on_capital_exhaustion=True,
            max_drawdown_halt_pct=(
                float(args.max_drawdown_halt_pct)
                if args.max_drawdown_halt_pct
                and float(args.max_drawdown_halt_pct) > 0.0
                else None
            ),
            min_equity_to_open=(
                float(args.min_equity_to_open)
                if args.min_equity_to_open is not None
                else None
            ),
        )
    )
    exchange = MockExchange()

    # PR109: resolve the strategy profile. ``--enable-core-strategy-sim-live``
    # is an alias for ``--strategy-profile core``. The core profile
    # implies a deterministic decision bridge is built and used.
    strategy_profile = (
        "core"
        if (args.enable_core_strategy_sim_live or args.strategy_profile == "core")
        else "baseline"
    )

    # PR106 / PR109: optionally build the deterministic, paper-only
    # decision bridge. For the "core" profile this is the AMA-RT core
    # strategy bridge (regime -> stage -> score -> selector); for the
    # "baseline" profile it is the PR106 baseline_breakout_volume_v0
    # shadow rule. Either bridge is bound to the capital-flow engine so
    # it can reconcile its per-symbol intent against the simulated
    # position book. Both carry NO trade authority, NO AI authority,
    # NO auto-tuning, and NO live path.
    paper_shadow_bridge: Optional[PaperShadowStrategyBridge] = None
    if strategy_profile == "core":
        core_config = CoreStrategyBridgeConfig(
            bridge_name=args.core_bridge_name,
            timeframe=args.paper_shadow_timeframe,
            breakout_lookback=int(args.paper_shadow_breakout_lookback),
            min_history_bars=int(args.paper_shadow_breakout_lookback) + 1,
            max_hold_bars=int(args.paper_shadow_max_hold_bars),
            take_profit_pct=float(args.paper_shadow_take_profit_pct),
            stop_loss_pct=float(args.paper_shadow_stop_loss_pct),
            position_notional=float(args.paper_shadow_position_notional),
            max_concurrent_positions=int(
                args.paper_shadow_max_concurrent_positions
            ),
            momentum_lookback=int(args.core_momentum_lookback),
            momentum_full_scale_pct=float(
                args.core_momentum_full_scale_pct
            ),
            volume_full_scale_ratio=float(
                args.core_volume_full_scale_ratio
            ),
            liquidity_reference_quote_volume=float(
                args.core_liquidity_reference_quote_volume
            ),
            late_chase_full_scale_pct=float(
                args.core_late_chase_full_scale_pct
            ),
            manipulation_wick_scale=float(
                args.core_manipulation_wick_scale
            ),
            min_opportunity_score=float(args.core_min_opportunity_score),
            scale_notional_by_regime=(
                not args.core_no_scale_notional_by_regime
            ),
        )
        paper_shadow_bridge = CoreStrategyBridge(
            config=core_config,
            capital_flow=capital,
        )
        _LOGGER.info(
            "core strategy sim-live bridge enabled: name=%s timeframe=%s "
            "breakout_lookback=%d momentum_lookback=%d "
            "min_opportunity_score=%.2f max_hold_bars=%d "
            "position_notional=%.4f scale_notional_by_regime=%s",
            core_config.bridge_name,
            core_config.timeframe,
            core_config.breakout_lookback,
            core_config.momentum_lookback,
            core_config.min_opportunity_score,
            core_config.max_hold_bars,
            core_config.position_notional,
            core_config.scale_notional_by_regime,
        )
    elif args.enable_paper_shadow_strategy:
        bridge_config = PaperShadowStrategyBridgeConfig(
            bridge_name=args.paper_shadow_bridge_name,
            timeframe=args.paper_shadow_timeframe,
            breakout_lookback=int(args.paper_shadow_breakout_lookback),
            volume_multiplier=float(args.paper_shadow_volume_multiplier),
            min_history_bars=int(args.paper_shadow_breakout_lookback) + 1,
            max_hold_bars=int(args.paper_shadow_max_hold_bars),
            take_profit_pct=float(args.paper_shadow_take_profit_pct),
            stop_loss_pct=float(args.paper_shadow_stop_loss_pct),
            position_notional=float(
                args.paper_shadow_position_notional
            ),
            max_concurrent_positions=int(
                args.paper_shadow_max_concurrent_positions
            ),
        )
        paper_shadow_bridge = PaperShadowStrategyBridge(
            config=bridge_config,
            capital_flow=capital,
        )
        _LOGGER.info(
            "paper shadow strategy bridge enabled: name=%s timeframe=%s "
            "breakout_lookback=%d volume_multiplier=%.3f "
            "max_hold_bars=%d position_notional=%.4f",
            bridge_config.bridge_name,
            bridge_config.timeframe,
            bridge_config.breakout_lookback,
            bridge_config.volume_multiplier,
            bridge_config.max_hold_bars,
            bridge_config.position_notional,
        )

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
            strategy_profile=strategy_profile,
            paper_shadow_strategy_enabled=bool(
                strategy_profile != "core"
                and args.enable_paper_shadow_strategy
            ),
            paper_shadow_strategy_bridge_name=(
                paper_shadow_bridge.bridge_name
                if paper_shadow_bridge is not None
                else None
            ),
            data_manifest_hash=(
                historical_input.data_manifest_hash
                if historical_input is not None
                else None
            ),
            universe_manifest_hash=(
                historical_input.universe_manifest_hash
                if historical_input is not None
                else None
            ),
        ),
        replay_provider=provider,
        capital_flow=capital,
        mock_exchange=exchange,
        telegram_sandbox=telegram,
        paper_shadow_bridge=paper_shadow_bridge,
    )

    result: Dict[str, Any] = runner.run()

    # Operator-facing summary.
    score = result.get("score") or {}
    paths = result.get("paths") or {}
    manifest_out = result.get("manifest") or {}
    # PR106: read back the blind report so the operator summary can
    # surface the paper-shadow aggregates (the runner.run() result only
    # carries manifest / score / paths).
    report_out: Dict[str, Any] = {}
    report_path = paths.get("blind_walk_forward_report.json")
    if report_path:
        try:
            with open(report_path, "r", encoding="utf-8") as fh:
                report_out = json.load(fh)
        except (OSError, ValueError):
            report_out = {}

    # PR103: write a Historical Store input metadata sidecar alongside
    # the report so reviewers can see exactly which store fed the run.
    if historical_input is not None:
        run_dir = (
            Path(
                paths.get("blind_walk_forward_report.json")
            ).parent
            if paths.get("blind_walk_forward_report.json")
            else target_root
        )
        store_meta: Dict[str, Any] = {
            "run_id": manifest_out.get("run_id"),
            "historical_store_dir": args.historical_store_dir,
            "records_path": args.records_path,
            "ingested_record_count": historical_input.record_count,
            "record_counts_by_type": dict(
                historical_input.record_counts_by_type
            ),
            "source_files": list(historical_input.source_files),
            "data_manifest_hash": (
                manifest_out.get("data_manifest_hash")
            ),
            "universe_manifest_hash": (
                manifest_out.get("universe_manifest_hash")
            ),
            "warnings": list(historical_input.warnings),
            "is_blind_walk_forward_payload": True,
        }
        store_meta.update(blind_walk_forward_safety_payload())
        assert_no_forbidden_fields(store_meta)
        meta_path = run_dir / "historical_store_input.json"
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(
                store_meta, fh, sort_keys=True, indent=2, default=str
            )
        paths["historical_store_input.json"] = str(meta_path)

    summary = {
        "phase": PHASE_NAME,
        "run_id": manifest_out.get("run_id"),
        "status": score.get("status"),
        "sample_count": score.get("sample_count"),
        "closed_trade_count": score.get("closed_trade_count"),
        "violations_count": score.get(
            "no_lookahead_violation_count"
        ),
        "failure_ledger_entry_count": score.get(
            "failure_ledger_entry_count"
        ),
        # PR106 - paper shadow strategy operator summary.
        "paper_shadow_strategy_enabled": bool(
            strategy_profile != "core"
            and args.enable_paper_shadow_strategy
        ),
        # PR109 - core strategy sim-live operator summary.
        "strategy_profile": report_out.get(
            "strategy_profile", strategy_profile
        ),
        "core_strategy_enabled": report_out.get(
            "core_strategy_enabled", strategy_profile == "core"
        ),
        "symbols_scanned_count": report_out.get("symbols_scanned_count"),
        "symbols_traded_count": report_out.get("symbols_traded_count"),
        "strategy_bridge_name": (
            paper_shadow_bridge.bridge_name
            if paper_shadow_bridge is not None
            else None
        ),
        "initial_capital": float(args.initial_capital),
        "trade_count": (report_out.get("trade_count")),
        "total_realized_pnl": report_out.get("total_realized_pnl"),
        "max_drawdown": report_out.get("max_drawdown"),
        "win_count": report_out.get("win_count"),
        "loss_count": report_out.get("loss_count"),
        "breakeven_count": report_out.get("breakeven_count"),
        # PR108 - capital-safety operator summary.
        "final_equity": report_out.get("final_equity"),
        "min_equity": report_out.get("min_equity"),
        "max_drawdown_limit": report_out.get("max_drawdown_limit"),
        "capital_floor": report_out.get("capital_floor"),
        "capital_exhausted": report_out.get("capital_exhausted"),
        "halted_by_risk": report_out.get("halted_by_risk"),
        "risk_halt_reason": report_out.get("risk_halt_reason"),
        "forced_exit_count": report_out.get("forced_exit_count"),
        "capital_reject_count": report_out.get("capital_reject_count"),
        "capital_exhaustion_event_count": report_out.get(
            "capital_exhaustion_event_count"
        ),
        "no_negative_equity_guard": report_out.get(
            "no_negative_equity_guard"
        ),
        "no_paper_shadow_signals": report_out.get(
            "no_paper_shadow_signals"
        ),
        "paper_shadow_entry_signal_count": report_out.get(
            "paper_shadow_entry_signal_count"
        ),
        "paper_shadow_exit_signal_count": report_out.get(
            "paper_shadow_exit_signal_count"
        ),
        "paper_shadow_reject_count": report_out.get(
            "paper_shadow_reject_count"
        ),
        "historical_store_dir": args.historical_store_dir,
        "ingested_record_count": (
            historical_input.record_count
            if historical_input is not None
            else 0
        ),
        "data_manifest_hash": manifest_out.get("data_manifest_hash"),
        "universe_manifest_hash": manifest_out.get(
            "universe_manifest_hash"
        ),
        "historical_store_warnings": (
            list(historical_input.warnings)
            if historical_input is not None
            else []
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
