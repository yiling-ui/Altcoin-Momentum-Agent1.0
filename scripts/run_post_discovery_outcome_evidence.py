"""Phase 11C.1C-C-B-B-B-D-B - Post-Discovery Outcome Metrics v0 evidence runner.

Paper / report / evidence ONLY.

This runner consumes the artefacts produced by Phase
11C.1C-C-B-B-B-D-A (Historical 60D Mover Coverage Backfill Audit
v0) and turns each audited mover into one paper-only
:class:`PostDiscoveryOutcomeRecord` via
:class:`PostDiscoveryOutcomeEvaluator`. It then aggregates the
records into one :class:`PostDiscoveryOutcomeReport` and writes
both:

    POST_DISCOVERY_OUTCOME_EVALUATED          - one event per record
    POST_DISCOVERY_OUTCOME_REPORT_GENERATED   - one event per batch

to ``<output-dir>/events.jsonl`` together with a
``post_discovery_outcome_report.json`` payload and a short
markdown summary ``post_discovery_outcome_report.md``.

Boundary
--------
The runner is paper / report / evidence only. It MUST NOT and
DOES NOT:

  - authorise a real trade,
  - modify a real position,
  - read a private exchange API,
  - sign a request,
  - call an LLM, DeepSeek, or Telegram outbound transport,
  - change ``symbol_limit``, candidate-pool capacity, anomaly
    thresholds, Regime weights, runtime config, or any other
    runtime knob,
  - recommend a direction (long / short / entry / exit /
    stop / target / position size / leverage).

Phase 12 remains FORBIDDEN. The Risk Engine remains the single
trade-decision gate.

Inputs
------
The runner accepts (in priority order):

  1. ``--coverage-payload`` - a single Phase 11C.1C-C-B-B-B-D-A
     ``HistoricalMoverCoverageBackfillReport`` payload, either as
     a one-line JSON file or as a JSONL stream.
  2. ``--export-dir`` - a directory containing one or more
     exported ``events.jsonl`` files. The runner scans each file
     for the most recent
     ``HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED`` event and
     uses its payload.
  3. ``--events-db`` - a SQLite events database; the runner asks
     the :class:`EventRepository` for the most recent
     ``HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED`` event.
  4. ``--historical-store-dir`` - an in-place fallback that asks
     the audit runtime to assemble a fresh report from the local
     Historical Market Store. Requires ``--events-db`` for the
     per-symbol event streams.

If none of the inputs is reachable the runner writes a
``post_discovery_outcome_report.json`` with status
``INSUFFICIENT_EVIDENCE`` / ``NEEDS_OPERATOR_DATA`` and exits
non-zero so a downstream caller can refuse to mark the phase
ACCEPTED.

Optional ``--price-paths-json`` accepts an operator-supplied
JSON file mapping each symbol to a sequence of post-first-seen
price observations::

    {
      "RAVEUSDT": [
        {"timestamp_utc_ms": 1701000000000, "price": 0.012},
        {"timestamp_utc_ms": 1701003600000, "price": 0.018}
      ],
      "STOUSDT": []
    }

When omitted, the runner only emits ``MISSED_STRONG_TAIL`` for
records whose D-A reference recorded a strong tail and falls
back to ``INSUFFICIENT_PRICE_PATH`` for everything else.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# Add project root to path so the runner can be invoked as a script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.adaptive.post_discovery_outcome_metrics import (  # noqa: E402
    POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION,
    POST_DISCOVERY_OUTCOME_METRICS_SOURCE_PHASE,
    HistoricalMoverReferenceSummary,
    PostDiscoveryOutcomeEvaluator,
    PostDiscoveryOutcomeInput,
    PostDiscoveryOutcomeRecord,
    PostDiscoveryOutcomeReport,
    PricePoint,
    assert_payload_has_no_forbidden_keys,
    build_post_discovery_outcome_report,
)
from app.core.events import EventType  # noqa: E402


SOURCE_MODULE = "scripts.run_post_discovery_outcome_evidence"

INSUFFICIENT_EVIDENCE_STATUS = "INSUFFICIENT_EVIDENCE"
NEEDS_OPERATOR_DATA_STATUS = "NEEDS_OPERATOR_DATA"
EVIDENCE_GENERATED_STATUS = "EVIDENCE_GENERATED"
# Phase 11C.1C-C-B-B-B-D-B status emitted when the D-A export does
# contain HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED events but none of
# them can be adapted into a usable PostDiscoveryOutcomeInput by the
# D-B input adapter. Distinct from INSUFFICIENT_EVIDENCE so an
# operator can tell "no D-A export at all" apart from "D-A export is
# present but the D-B adapter rejected every record" (the input-
# adapter gap that used to silently produce evaluated_count=0). The
# CLI returns the same non-zero exit code so a downstream caller
# still refuses to mark the phase ACCEPTED.
INSUFFICIENT_EVALUABLE_RECORDS_STATUS = "INSUFFICIENT_EVALUABLE_RECORDS"

# Warning emitted when D-A RECORD_AUDITED events are present but the
# D-B runner could not adapt any of them into a usable input. The
# warning is intentionally explicit so daily-report / closeout
# tooling does NOT treat the run as a quiet "EVIDENCE_GENERATED"
# success.
WARNING_D_A_RECORDS_PRESENT_BUT_NO_INPUTS = (
    "d_a_records_present_but_no_post_discovery_inputs"
)

DEFAULT_OUTPUT_DIR = Path("data/reports/post_discovery_outcome")
DEFAULT_REFERENCE_WINDOW = "60d"

# D-A event types (string-only - we never import EventType.HISTORICAL_*
# at runtime to keep the runner usable when only an exported JSONL
# is available).
HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED = (
    "HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED"
)
HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED = (
    "HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED"
)


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceRunResult:
    """In-memory result returned by :func:`run_evidence_pipeline`.

    Paper / report / evidence only. No trade-authority field.
    """

    status: str
    evaluated_count: int
    report_generated_count: int
    output_report_path: Path
    output_events_path: Path
    output_summary_path: Path
    label_summary: dict[str, int]
    timing_summary: dict[str, int]
    notable_symbols: dict[str, str]
    warnings: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Input loading
# ---------------------------------------------------------------------------


def _read_first_json_object(path: Path) -> dict[str, Any] | None:
    """Read the first JSON object from a ``.json`` or ``.jsonl`` file.

    Returns ``None`` if the file is missing or empty / invalid.
    """

    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None
    # JSONL: try each non-empty line.
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    # Fallback: full file as one object.
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict):
        return obj
    return None


def _scan_export_dir_for_d_a_payload(
    export_dir: Path,
) -> dict[str, Any] | None:
    """Walk ``export_dir`` for the most recent
    ``HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED`` event payload.
    """

    if not export_dir.is_dir():
        return None

    candidate_files: list[Path] = []
    candidate_files.extend(sorted(export_dir.rglob("events.jsonl")))
    candidate_files.extend(sorted(export_dir.rglob("*.jsonl")))

    latest_payload: dict[str, Any] | None = None
    latest_ts: int = -1

    for path in candidate_files:
        try:
            with path.open("r", encoding="utf-8") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    if (
                        obj.get("event_type")
                        != HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED
                    ):
                        continue
                    payload = obj.get("payload")
                    if not isinstance(payload, dict):
                        continue
                    ts = int(obj.get("timestamp", 0) or 0)
                    if ts >= latest_ts:
                        latest_ts = ts
                        latest_payload = payload
        except OSError:
            continue

    return latest_payload


def _adapt_record_audited_payload(
    payload: Mapping[str, Any] | Any,
    *,
    event_symbol: Any = None,
) -> dict[str, Any] | None:
    """Adapter for a single
    ``HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`` event payload.

    The Phase 11C.1C-C-B-B-B-D-A emitter writes one
    RECORD_AUDITED event per audited mover. Two on-disk shapes are
    supported:

      - **Wrapped:** ``payload['record']`` is the per-mover record
        dict (legacy / test-fixture form).
      - **Flat:**   ``payload`` itself is the per-mover record
        dict (real D-A export emit, observed on the operator
        VPS - keys include ``coverage_status``, ``reference``,
        ``capture_path``, ``miss_reason``, ``miss_reasons``,
        ``first_seen_*``, ``capture_path_depth``,
        ``risk_rejected``, ``reached_*``, ...).

    Symbol resolution priority:

      1. ``record["symbol"]``
      2. ``record["reference"]["symbol"]``
      3. ``record["capture_path"]["symbol"]``
      4. event-level ``symbol`` field (only if the others are
         missing).

    Returns ``None`` when no usable record can be derived. The
    return value is a normalised dict that
    :func:`build_post_discovery_inputs_from_d_a_payload` consumes
    exactly like a Format A
    ``HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED.payload.records``
    entry. All known D-A record fields are preserved.
    """

    if not isinstance(payload, Mapping):
        return None

    inner = payload.get("record")
    if isinstance(inner, Mapping) and inner:
        record_src: Mapping[str, Any] = inner
    else:
        record_src = payload

    symbol = record_src.get("symbol")
    if not symbol:
        ref = record_src.get("reference")
        if isinstance(ref, Mapping):
            symbol = ref.get("symbol")
    if not symbol:
        cap = record_src.get("capture_path")
        if isinstance(cap, Mapping):
            symbol = cap.get("symbol")
    if not symbol and isinstance(event_symbol, str) and event_symbol:
        symbol = event_symbol
    if not symbol:
        return None

    out: dict[str, Any] = dict(record_src)
    out["symbol"] = str(symbol)
    return out


def _scan_export_dir_for_d_a_record_audited_events(
    export_dir: Path,
) -> list[dict[str, Any]]:
    """Walk ``export_dir`` and return every
    ``HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`` event payload as
    an adapted D-A record dict.

    Used as the Format B fallback when the matching
    ``HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED`` event has
    ``payload.records`` missing / ``None``.
    """

    if not export_dir.is_dir():
        return []

    candidate_files: list[Path] = []
    candidate_files.extend(sorted(export_dir.rglob("events.jsonl")))
    candidate_files.extend(sorted(export_dir.rglob("*.jsonl")))

    seen_paths: set[Path] = set()
    records: list[dict[str, Any]] = []

    for path in candidate_files:
        if path in seen_paths:
            continue
        seen_paths.add(path)
        try:
            with path.open("r", encoding="utf-8") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    if (
                        obj.get("event_type")
                        != HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED
                    ):
                        continue
                    payload = obj.get("payload")
                    record = _adapt_record_audited_payload(
                        payload, event_symbol=obj.get("symbol")
                    )
                    if record is not None:
                        records.append(record)
        except OSError:
            continue
    return records


def _load_d_a_record_audited_events_from_db(
    events_db: Path,
) -> list[dict[str, Any]]:
    """Best-effort load of
    ``HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`` event payloads
    from a SQLite events database. Returns an empty list when the
    DB is missing / unreadable.
    """

    if not events_db.is_file():
        return []
    try:
        import sqlite3
    except ImportError:  # pragma: no cover - sqlite3 is stdlib
        return []
    try:
        conn = sqlite3.connect(f"file:{events_db}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT symbol, payload FROM events WHERE event_type = ? "
            "ORDER BY timestamp ASC",
            (HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,),
        )
        rows = cur.fetchall()
    except sqlite3.Error:
        conn.close()
        return []
    conn.close()
    records: list[dict[str, Any]] = []
    for symbol_col, raw in rows:
        if isinstance(raw, bytes):
            raw_text = raw.decode("utf-8", errors="replace")
        elif isinstance(raw, str):
            raw_text = raw
        else:
            continue
        try:
            obj = json.loads(raw_text)
        except json.JSONDecodeError:
            continue
        record = _adapt_record_audited_payload(
            obj, event_symbol=symbol_col
        )
        if record is not None:
            records.append(record)
    return records


def _load_d_a_payload_from_events_db(
    events_db: Path,
) -> dict[str, Any] | None:
    """Best-effort load of the most recent D-A coverage backfill
    payload from a SQLite events database.

    The runner is intentionally tolerant: if the DB is missing or
    the events table does not have the expected columns, returns
    ``None`` so the caller can fall back / declare insufficient
    evidence.
    """

    if not events_db.is_file():
        return None
    try:
        import sqlite3
    except ImportError:  # pragma: no cover - sqlite3 is stdlib
        return None
    try:
        conn = sqlite3.connect(f"file:{events_db}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT payload FROM events WHERE event_type = ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED,),
        )
        row = cur.fetchone()
    except sqlite3.Error:
        conn.close()
        return None
    conn.close()
    if not row:
        return None
    raw = row[0]
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not isinstance(raw, str):
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def load_d_a_coverage_payload(
    *,
    coverage_payload: Path | None = None,
    export_dir: Path | None = None,
    events_db: Path | None = None,
    historical_store_dir: Path | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[str]]:
    """Resolve the D-A coverage backfill payload + any
    ``HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`` fallback records
    from the first available source.

    Returns ``(payload, audited_records, warnings)``:

      - ``payload`` is the most recent
        ``HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED`` payload
        (Format A source), or ``None`` if none was found.
      - ``audited_records`` is the list of D-A record dicts
        recovered from
        ``HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED`` events
        (Format B source). Empty when no such events were
        observed. Used by :func:`run_evidence_pipeline` as the
        fallback when ``payload.records`` is missing / empty,
        which is the real-world shape produced by the operator
        VPS D-A export (300 RECORD_AUDITED events alongside a
        BACKFILL_GENERATED whose ``records`` field is ``None``).
    """

    warnings: list[str] = []
    payload: dict[str, Any] | None = None
    audited_records: list[dict[str, Any]] = []

    if coverage_payload is not None:
        candidate = _read_first_json_object(coverage_payload)
        if candidate is not None and "records" in candidate:
            payload = candidate
        else:
            warnings.append(
                f"coverage_payload_unreadable_or_empty:{coverage_payload}"
            )

    if payload is None and export_dir is not None:
        candidate = _scan_export_dir_for_d_a_payload(export_dir)
        if candidate is not None:
            payload = candidate
        else:
            warnings.append(f"export_dir_no_d_a_payload:{export_dir}")

    if payload is None and events_db is not None:
        candidate = _load_d_a_payload_from_events_db(events_db)
        if candidate is not None:
            payload = candidate
        else:
            warnings.append(f"events_db_no_d_a_payload:{events_db}")

    # RECORD_AUDITED fallback collection. Always attempted from
    # every available source so the Format B path works even when
    # the Format A payload was found but has ``records=None``.
    if export_dir is not None:
        audited_records.extend(
            _scan_export_dir_for_d_a_record_audited_events(export_dir)
        )
    if events_db is not None:
        audited_records.extend(
            _load_d_a_record_audited_events_from_db(events_db)
        )

    if payload is None and not audited_records and historical_store_dir is not None:
        if historical_store_dir.is_dir():
            warnings.append(
                f"historical_store_dir_present_but_no_runner_hook:"
                f"{historical_store_dir}"
            )
        else:
            warnings.append(
                f"historical_store_dir_missing:{historical_store_dir}"
            )

    return payload, audited_records, warnings


# ---------------------------------------------------------------------------
# Price-paths fixture
# ---------------------------------------------------------------------------


def load_price_paths_json(
    path: Path | None,
) -> dict[str, tuple[PricePoint, ...]]:
    """Load operator-supplied per-symbol price paths.

    Returns an empty mapping when ``path`` is ``None`` or the file
    cannot be read; the runner then falls back to
    ``INSUFFICIENT_PRICE_PATH`` / ``MISSED_STRONG_TAIL`` based on
    the D-A reference alone.
    """

    if path is None:
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(obj, dict):
        return {}
    out: dict[str, tuple[PricePoint, ...]] = {}
    for symbol, raw_path in obj.items():
        if not isinstance(symbol, str) or not isinstance(raw_path, list):
            continue
        points: list[PricePoint] = []
        for raw_point in raw_path:
            if not isinstance(raw_point, dict):
                continue
            ts = raw_point.get("timestamp_utc_ms")
            price = raw_point.get("price")
            if ts is None or price is None:
                continue
            try:
                points.append(
                    PricePoint(
                        timestamp_utc_ms=int(ts),
                        price=float(price),
                    )
                )
            except (TypeError, ValueError):
                continue
        out[symbol] = tuple(points)
    return out


# ---------------------------------------------------------------------------
# D-A record -> D-B input adapter
# ---------------------------------------------------------------------------


def build_post_discovery_inputs_from_d_a_payload(
    d_a_payload: Mapping[str, Any],
    *,
    reference_window: str,
    price_paths: Mapping[str, Sequence[PricePoint]] | None = None,
) -> list[PostDiscoveryOutcomeInput]:
    """Map a Phase 11C.1C-C-B-B-B-D-A coverage payload into a list
    of :class:`PostDiscoveryOutcomeInput` rows ready for the
    D-B evaluator.

    Each D-A record contributes exactly one D-B input. The
    historical reference summary is built from the D-A reference
    columns (``mover_window_start_utc_ms``, ``mover_window_end_utc_ms``,
    ``max_window_gain``). Prior-high / reference-peak anchors are
    only populated when the D-A reference carries them (the v0
    audit does not, so they default to ``None``); operator-
    supplied price paths fill the gap when present.
    """

    paths_map: dict[str, tuple[PricePoint, ...]] = {}
    if price_paths is not None:
        for sym, pts in price_paths.items():
            paths_map[str(sym)] = tuple(pts)

    inputs: list[PostDiscoveryOutcomeInput] = []
    raw_records = d_a_payload.get("records") or ()
    if not isinstance(raw_records, (list, tuple)):
        return inputs

    for raw in raw_records:
        if not isinstance(raw, Mapping):
            continue
        capture_path = raw.get("capture_path") or {}
        reference = raw.get("reference") or {}
        if not isinstance(capture_path, Mapping):
            capture_path = {}
        if not isinstance(reference, Mapping):
            reference = {}
        # Symbol resolution priority mirrors the D-A export shape
        # observed on the operator VPS: the top-level ``symbol``
        # may be missing on a flat RECORD_AUDITED-derived record,
        # in which case ``reference.symbol`` / ``capture_path.symbol``
        # carry the same value.
        raw_symbol = raw.get("symbol")
        if not raw_symbol:
            raw_symbol = reference.get("symbol")
        if not raw_symbol:
            raw_symbol = capture_path.get("symbol")
        symbol = str(raw_symbol or "")
        if not symbol:
            continue

        first_seen_time = capture_path.get("first_seen_time_utc_ms")
        first_seen_event = capture_path.get("first_seen_event_type")
        capture_status = str(
            raw.get("coverage_status") or "missed"
        ).lower()
        capture_path_depth = int(capture_path.get("capture_path_depth") or 0)

        # The D-A v0 reference does not carry first_seen_price,
        # prior_high, or reference_peak anchors. Operator-supplied
        # price paths can refine the picture; otherwise the
        # evaluator emits MISSED_STRONG_TAIL when warranted and
        # INSUFFICIENT_PRICE_PATH otherwise.
        first_seen_price: float | None = None
        path_tuple = paths_map.get(symbol, ())
        if path_tuple:
            # When the operator supplies a price path, take the
            # earliest observation as a proxy for first-seen
            # price. Records that already carry an explicit
            # ``first_seen_price`` field via the optional
            # operator override are preserved.
            override = capture_path.get("first_seen_price")
            if override is not None:
                try:
                    first_seen_price = float(override)
                except (TypeError, ValueError):
                    first_seen_price = None
            if first_seen_price is None:
                first_seen_price = float(path_tuple[0].price)

        ref_summary = HistoricalMoverReferenceSummary(
            symbol=symbol,
            reference_window=reference_window,
            mover_window_start_utc_ms=int(
                reference.get("mover_window_start_utc_ms") or 0
            ),
            mover_window_end_utc_ms=int(
                reference.get("mover_window_end_utc_ms") or 0
            ),
            prior_high_time_utc_ms=reference.get("prior_high_time_utc_ms"),
            prior_high_price=reference.get("prior_high_price"),
            reference_peak_price=reference.get("reference_peak_price"),
            reference_peak_time_utc_ms=reference.get(
                "reference_peak_time_utc_ms"
            ),
            reference_max_window_gain_pct=reference.get("max_window_gain"),
            notes=reference.get("notes"),
        )

        inputs.append(
            PostDiscoveryOutcomeInput(
                symbol=symbol,
                reference_window=reference_window,
                first_seen_time_utc_ms=(
                    int(first_seen_time)
                    if first_seen_time is not None
                    else None
                ),
                first_seen_event_type=(
                    str(first_seen_event) if first_seen_event else None
                ),
                first_seen_price=first_seen_price,
                price_path_after_first_seen=path_tuple,
                historical_mover_reference=ref_summary,
                capture_status=capture_status,
                capture_path_depth=capture_path_depth,
                evidence_refs=(
                    f"phase_11c_1c_c_b_b_b_d_a:audit:{symbol}",
                ),
            )
        )

    return inputs


# ---------------------------------------------------------------------------
# Event payload helpers
# ---------------------------------------------------------------------------


def build_evaluated_event_payload(
    record: PostDiscoveryOutcomeRecord,
    *,
    reference_window: str,
) -> dict[str, Any]:
    payload = {
        "event_type": EventType.POST_DISCOVERY_OUTCOME_EVALUATED.value,
        "source_module": SOURCE_MODULE,
        "symbol": record.symbol,
        "payload": {
            "schema_version": POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION,
            "source_phase": POST_DISCOVERY_OUTCOME_METRICS_SOURCE_PHASE,
            "reference_window": reference_window,
            "record": record.to_dict(),
        },
    }
    assert_payload_has_no_forbidden_keys(
        payload["payload"],
        context=f"evaluated_event:{record.symbol}",
    )
    return payload


def build_report_event_payload(
    report: PostDiscoveryOutcomeReport,
) -> dict[str, Any]:
    payload = {
        "event_type": EventType.POST_DISCOVERY_OUTCOME_REPORT_GENERATED.value,
        "source_module": SOURCE_MODULE,
        "symbol": None,
        "payload": {
            "schema_version": POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION,
            "source_phase": POST_DISCOVERY_OUTCOME_METRICS_SOURCE_PHASE,
            "reference_window": report.reference_window,
            "report": report.to_dict(),
        },
    }
    assert_payload_has_no_forbidden_keys(
        payload["payload"],
        context=f"report_event:{report.reference_window}",
    )
    return payload


# ---------------------------------------------------------------------------
# Notable-symbols summary
# ---------------------------------------------------------------------------


NOTABLE_SYMBOL_WATCHLIST: tuple[str, ...] = ("RAVEUSDT", "STOUSDT")


def _summarise_notable_symbols(
    records: Sequence[PostDiscoveryOutcomeRecord],
) -> dict[str, str]:
    """Pick out the operator-watched symbols and surface their
    descriptive outcome label. Symbols that are not present in
    the records are reported as ``ABSENT``.
    """

    by_symbol: dict[str, PostDiscoveryOutcomeRecord] = {
        r.symbol: r for r in records
    }
    out: dict[str, str] = {}
    for symbol in NOTABLE_SYMBOL_WATCHLIST:
        record = by_symbol.get(symbol)
        if record is None:
            out[symbol] = "ABSENT"
        else:
            out[symbol] = (
                f"{record.outcome_label} / {record.detection_timing_label}"
            )
    return out


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, separators=(",", ":"), sort_keys=True))
            fh.write("\n")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _format_markdown_summary(
    *,
    status: str,
    evaluated_count: int,
    report_generated_count: int,
    label_summary: Mapping[str, int],
    timing_summary: Mapping[str, int],
    notable_symbols: Mapping[str, str],
    warnings: Sequence[str],
    output_report_path: Path,
    output_events_path: Path,
    reference_window: str,
) -> str:
    lines: list[str] = []
    lines.append(
        "# Phase 11C.1C-C-B-B-B-D-B Post-Discovery Outcome Metrics v0 Evidence"
    )
    lines.append("")
    lines.append("Paper / report / evidence only. Phase 12 remains FORBIDDEN.")
    lines.append("")
    lines.append(f"- status: {status}")
    lines.append(f"- reference_window: {reference_window}")
    lines.append(f"- evaluated_count: {evaluated_count}")
    lines.append(f"- report_generated_count: {report_generated_count}")
    lines.append(f"- output_report: {output_report_path}")
    lines.append(f"- output_events: {output_events_path}")
    lines.append("")
    lines.append("## Outcome label summary")
    if label_summary:
        for label, count in sorted(label_summary.items()):
            lines.append(f"- {label}: {count}")
    else:
        lines.append("- (no records)")
    lines.append("")
    lines.append("## Detection timing summary")
    if timing_summary:
        for label, count in sorted(timing_summary.items()):
            lines.append(f"- {label}: {count}")
    else:
        lines.append("- (no records)")
    lines.append("")
    lines.append("## Notable symbols")
    for symbol, status_str in notable_symbols.items():
        lines.append(f"- {symbol}: {status_str}")
    lines.append("")
    if warnings:
        lines.append("## Warnings")
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")
    lines.append("## Safety boundary")
    lines.append("")
    lines.append("- D-B does not authorise live trading.")
    lines.append("- D-B does not prove strategy profitability.")
    lines.append("- D-B does not solve direction.")
    lines.append("- D-B does not authorise auto-tuning.")
    lines.append("- D-B does not authorise DeepSeek trade decisions.")
    lines.append("- Phase 12 remains FORBIDDEN.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_evidence_pipeline(
    *,
    coverage_payload: Path | None,
    export_dir: Path | None,
    events_db: Path | None,
    historical_store_dir: Path | None,
    price_paths_json: Path | None,
    output_dir: Path,
    reference_window: str,
) -> EvidenceRunResult:
    """Run the D-B evidence pipeline once and return its
    :class:`EvidenceRunResult`.

    The pipeline is deterministic; every artefact is written to
    ``output_dir`` (created if missing).
    """

    output_dir = Path(output_dir)
    output_events_path = output_dir / "events.jsonl"
    output_report_path = output_dir / "post_discovery_outcome_report.json"
    output_summary_path = output_dir / "post_discovery_outcome_report.md"

    payload, audited_records, warnings = load_d_a_coverage_payload(
        coverage_payload=coverage_payload,
        export_dir=export_dir,
        events_db=events_db,
        historical_store_dir=historical_store_dir,
    )

    # Format A: BACKFILL_GENERATED.payload.records is non-empty.
    # Format B: BACKFILL_GENERATED.payload.records is missing/None
    #           but RECORD_AUDITED events carry one record each
    #           (the real D-A export shape).
    effective_payload: dict[str, Any] | None = None
    if payload is not None:
        payload_records = payload.get("records")
        if (
            isinstance(payload_records, (list, tuple))
            and len(payload_records) > 0
        ):
            effective_payload = dict(payload)
        elif audited_records:
            # Synthesise a payload that re-uses the report-level
            # fields from the BACKFILL_GENERATED payload (so the
            # reference window / counters remain auditable) but
            # populates ``records`` from the RECORD_AUDITED
            # fallback.
            synth = dict(payload)
            synth["records"] = list(audited_records)
            effective_payload = synth
            warnings.append(
                "d_a_backfill_records_missing_using_record_audited_fallback"
            )
    elif audited_records:
        # No BACKFILL_GENERATED payload at all but we still have
        # RECORD_AUDITED events. Build a minimal synthetic payload
        # so downstream code paths stay uniform.
        effective_payload = {"records": list(audited_records)}
        warnings.append(
            "d_a_backfill_payload_absent_using_record_audited_fallback"
        )

    if effective_payload is None:
        # Insufficient evidence path. Write an honest marker.
        marker = {
            "schema_version": POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION,
            "source_phase": POST_DISCOVERY_OUTCOME_METRICS_SOURCE_PHASE,
            "status": INSUFFICIENT_EVIDENCE_STATUS,
            "needs_operator_data": True,
            "reference_window": reference_window,
            "evaluated_count": 0,
            "report_generated_count": 0,
            "warnings": list(warnings)
            + [NEEDS_OPERATOR_DATA_STATUS],
            "generated_at_utc": _now_utc_iso(),
            "notes": (
                "No Phase 11C.1C-C-B-B-B-D-A historical mover coverage "
                "payload reachable. The runner refuses to fabricate "
                "records. Provide --coverage-payload, --export-dir, "
                "--events-db, or --historical-store-dir with a real "
                "D-A artefact and re-run."
            ),
        }
        _write_json(output_report_path, marker)
        _write_jsonl(output_events_path, [])  # empty events file
        summary_md = _format_markdown_summary(
            status=INSUFFICIENT_EVIDENCE_STATUS,
            evaluated_count=0,
            report_generated_count=0,
            label_summary={},
            timing_summary={},
            notable_symbols={s: "ABSENT" for s in NOTABLE_SYMBOL_WATCHLIST},
            warnings=tuple(marker["warnings"]),
            output_report_path=output_report_path,
            output_events_path=output_events_path,
            reference_window=reference_window,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        output_summary_path.write_text(summary_md, encoding="utf-8")
        return EvidenceRunResult(
            status=INSUFFICIENT_EVIDENCE_STATUS,
            evaluated_count=0,
            report_generated_count=0,
            output_report_path=output_report_path,
            output_events_path=output_events_path,
            output_summary_path=output_summary_path,
            label_summary={},
            timing_summary={},
            notable_symbols={s: "ABSENT" for s in NOTABLE_SYMBOL_WATCHLIST},
            warnings=tuple(marker["warnings"]),
        )

    price_paths = load_price_paths_json(price_paths_json)
    inputs = build_post_discovery_inputs_from_d_a_payload(
        effective_payload,
        reference_window=reference_window,
        price_paths=price_paths,
    )

    # Closeout-quality guard: when the D-A export DID carry
    # RECORD_AUDITED events but the D-B input adapter produced
    # zero usable inputs, the run is NOT a quiet success. Flag it
    # explicitly so daily-report / closeout tooling refuses to
    # treat it as ACCEPTED. This is the bug surfaced by the
    # operator-VPS evidence run (300 RECORD_AUDITED events,
    # ``evaluated_count == 0``).
    if not inputs and audited_records:
        warnings.append(WARNING_D_A_RECORDS_PRESENT_BUT_NO_INPUTS)
        marker = {
            "schema_version": POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION,
            "source_phase": POST_DISCOVERY_OUTCOME_METRICS_SOURCE_PHASE,
            "status": INSUFFICIENT_EVALUABLE_RECORDS_STATUS,
            "needs_operator_data": False,
            "reference_window": reference_window,
            "evaluated_count": 0,
            "report_generated_count": 0,
            "record_audited_event_count": len(audited_records),
            "warnings": list(warnings),
            "generated_at_utc": _now_utc_iso(),
            "notes": (
                "Phase 11C.1C-C-B-B-B-D-A export carried "
                f"{len(audited_records)} HISTORICAL_MOVER_COVERAGE_RECORD_"
                "AUDITED events but the D-B input adapter could not "
                "extract any usable PostDiscoveryOutcomeInput. This is "
                "an input-adapter gap, not an EVIDENCE_GENERATED run. "
                "The run is rejected so closeout tooling does not "
                "silently mark the phase ACCEPTED."
            ),
        }
        _write_json(output_report_path, marker)
        _write_jsonl(output_events_path, [])
        summary_md = _format_markdown_summary(
            status=INSUFFICIENT_EVALUABLE_RECORDS_STATUS,
            evaluated_count=0,
            report_generated_count=0,
            label_summary={},
            timing_summary={},
            notable_symbols={s: "ABSENT" for s in NOTABLE_SYMBOL_WATCHLIST},
            warnings=tuple(warnings),
            output_report_path=output_report_path,
            output_events_path=output_events_path,
            reference_window=reference_window,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        output_summary_path.write_text(summary_md, encoding="utf-8")
        return EvidenceRunResult(
            status=INSUFFICIENT_EVALUABLE_RECORDS_STATUS,
            evaluated_count=0,
            report_generated_count=0,
            output_report_path=output_report_path,
            output_events_path=output_events_path,
            output_summary_path=output_summary_path,
            label_summary={},
            timing_summary={},
            notable_symbols={s: "ABSENT" for s in NOTABLE_SYMBOL_WATCHLIST},
            warnings=tuple(warnings),
        )

    evaluator = PostDiscoveryOutcomeEvaluator()
    records = [evaluator.evaluate(inp) for inp in inputs]

    report = build_post_discovery_outcome_report(
        records,
        reference_window=reference_window,
        extra_warnings=tuple(warnings),
    )

    # Build event rows.
    event_rows: list[dict[str, Any]] = []
    for record in records:
        event_rows.append(
            build_evaluated_event_payload(
                record, reference_window=reference_window
            )
        )
    event_rows.append(build_report_event_payload(report))

    _write_jsonl(output_events_path, event_rows)

    full_report_payload: dict[str, Any] = {
        "schema_version": POST_DISCOVERY_OUTCOME_METRICS_SCHEMA_VERSION,
        "source_phase": POST_DISCOVERY_OUTCOME_METRICS_SOURCE_PHASE,
        "status": EVIDENCE_GENERATED_STATUS,
        "reference_window": reference_window,
        "evaluated_count": len(records),
        "report_generated_count": 1,
        "warnings": list(warnings),
        "generated_at_utc": _now_utc_iso(),
        "report": report.to_dict(),
    }
    assert_payload_has_no_forbidden_keys(
        full_report_payload, context="evidence_run_report"
    )
    _write_json(output_report_path, full_report_payload)

    notable = _summarise_notable_symbols(records)

    summary_md = _format_markdown_summary(
        status=EVIDENCE_GENERATED_STATUS,
        evaluated_count=len(records),
        report_generated_count=1,
        label_summary=report.outcome_label_summary,
        timing_summary=report.detection_timing_label_summary,
        notable_symbols=notable,
        warnings=tuple(warnings),
        output_report_path=output_report_path,
        output_events_path=output_events_path,
        reference_window=reference_window,
    )
    output_summary_path.write_text(summary_md, encoding="utf-8")

    return EvidenceRunResult(
        status=EVIDENCE_GENERATED_STATUS,
        evaluated_count=len(records),
        report_generated_count=1,
        output_report_path=output_report_path,
        output_events_path=output_events_path,
        output_summary_path=output_summary_path,
        label_summary=dict(report.outcome_label_summary),
        timing_summary=dict(report.detection_timing_label_summary),
        notable_symbols=notable,
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_post_discovery_outcome_evidence",
        description=(
            "Phase 11C.1C-C-B-B-B-D-B Post-Discovery Outcome Metrics v0 "
            "evidence runner. Paper / report / evidence ONLY. Phase 12 "
            "remains FORBIDDEN."
        ),
    )
    parser.add_argument(
        "--coverage-payload",
        type=Path,
        default=None,
        help=(
            "Path to a Phase 11C.1C-C-B-B-B-D-A coverage backfill payload "
            "(.json or .jsonl). Highest priority input."
        ),
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        default=None,
        help=(
            "Directory containing exported events.jsonl files. The runner "
            "scans for the most recent HISTORICAL_MOVER_COVERAGE_BACKFILL_"
            "GENERATED event."
        ),
    )
    parser.add_argument(
        "--events-db",
        type=Path,
        default=None,
        help=(
            "SQLite events database path (read-only). Used as a fallback "
            "when --coverage-payload / --export-dir are not provided."
        ),
    )
    parser.add_argument(
        "--historical-store-dir",
        type=Path,
        default=None,
        help=(
            "Local Historical Market Store directory. Recorded as a "
            "warning when the runner cannot derive a fresh audit; the "
            "runner does NOT execute the D-A audit by itself."
        ),
    )
    parser.add_argument(
        "--price-paths-json",
        type=Path,
        default=None,
        help=(
            "Optional JSON mapping each symbol to a list of "
            "{timestamp_utc_ms, price} observations after first_seen. "
            "When omitted, MISSED_STRONG_TAIL / INSUFFICIENT_PRICE_PATH "
            "are emitted based on the D-A reference alone."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=(
            "Directory for the runner's outputs (events.jsonl, "
            "post_discovery_outcome_report.json, "
            "post_discovery_outcome_report.md). Default: "
            f"{DEFAULT_OUTPUT_DIR}."
        ),
    )
    parser.add_argument(
        "--reference-window",
        type=str,
        default=DEFAULT_REFERENCE_WINDOW,
        help=(
            "Reference window label, e.g. '60d'. Descriptive only; does "
            "not change any runtime knob."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)

    result = run_evidence_pipeline(
        coverage_payload=args.coverage_payload,
        export_dir=args.export_dir,
        events_db=args.events_db,
        historical_store_dir=args.historical_store_dir,
        price_paths_json=args.price_paths_json,
        output_dir=args.output_dir,
        reference_window=args.reference_window,
    )

    print(
        json.dumps(
            {
                "status": result.status,
                "evaluated_count": result.evaluated_count,
                "report_generated_count": result.report_generated_count,
                "output_report_path": str(result.output_report_path),
                "output_events_path": str(result.output_events_path),
                "output_summary_path": str(result.output_summary_path),
                "outcome_label_summary": result.label_summary,
                "detection_timing_summary": result.timing_summary,
                "notable_symbols": result.notable_symbols,
                "warnings": list(result.warnings),
            },
            indent=2,
            sort_keys=True,
        )
    )

    if result.status in (
        INSUFFICIENT_EVIDENCE_STATUS,
        INSUFFICIENT_EVALUABLE_RECORDS_STATUS,
    ):
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
