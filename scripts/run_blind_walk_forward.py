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


def load_records_jsonl(path: Any) -> List[Any]:
    """Load PR95 records from a PR101 ``records.jsonl`` dump.

    Returns a list of reconstructed record objects in file order.
    Blank lines are skipped. Raises :class:`FileNotFoundError` when the
    file is absent (the caller maps this to ``INSUFFICIENT_EVIDENCE`` -
    we never fabricate records for a missing file).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"records.jsonl not found: {p}")
    records: List[Any] = []
    with open(p, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            records.append(_record_from_dict(json.loads(line)))
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
    records = load_records_jsonl(rp)
    if not records:
        return HistoricalStoreInput(
            store=HistoricalMarketStore(),
            record_count=0,
            status=BlindRunStatus.INSUFFICIENT_EVIDENCE,
            detail=f"records.jsonl empty: {rp}",
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
    p.add_argument(
        "--no-ai-post-window-summary",
        action="store_true",
        help="disable the offline post-window AI commentary template",
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
        historical_input = load_historical_store_dir(
            store_dir=args.historical_store_dir,
            records_path=args.records_path,
            data_manifest_path=args.historical_data_manifest_path,
            universe_manifest_path=args.universe_manifest_path,
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
    )

    result: Dict[str, Any] = runner.run()

    # Operator-facing summary.
    score = result.get("score") or {}
    paths = result.get("paths") or {}
    manifest_out = result.get("manifest") or {}

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
