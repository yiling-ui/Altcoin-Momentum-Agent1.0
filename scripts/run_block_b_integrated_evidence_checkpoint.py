"""Phase 11C.1C-C-B-B-B-D-E - Block B Integrated Evidence Checkpoint v0.

Aggregates the simplified outputs of:

    * Phase 11C.1C-C-B-B-B-D-A   Historical 60D Mover Coverage
      Backfill Audit (D-A)
    * Phase 11C.1C-C-B-B-B-D-B   Post-Discovery Outcome Metrics (D-B)
    * Phase 11C.1C-C-B-B-B-D-B.1 Historical Price Path / Kline Path
      Adapter (B1.1)
    * Phase 11C.1C-C-B-B-B-D-C-A Reject-to-Outcome Attribution (B2-A)
    * Phase 11C.1C-C-B-B-B-D-C-B Severe Missed Tail Triage (B2-B)
    * Phase 11C.1C-C-B-B-B-D-D   Discovery Quality Scorecard (B3)

into a single **Block B integrated evidence report**. The report is
the input to the Block B / Block C decision: did Block B produce
enough evidence to authorise the next allowed phase
(*Replay / Reflection extension for 11C Adaptive Events*)?

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
  - automatically tune any parameter on the basis of any field
    it emits,
  - recommend a direction (long / short / entry / exit / stop /
    target / position size / leverage),
  - open Phase 12.

The runner does not connect to the network. It reads only local
files under ``--reports-dir`` / ``--exports-dir`` /
``--post-discovery-dir`` and writes only files under
``--output-dir``. Phase 12 remains FORBIDDEN. The Risk Engine
remains the single trade-decision gate.

Inputs
------
The runner accepts (all optional; the runner is tolerant of
missing / partial inputs):

  - ``--reports-dir``              data/reports
  - ``--exports-dir``              data/reports/exports
  - ``--post-discovery-dir``       data/reports/post_discovery_outcome
  - ``--output-dir``               data/reports/block_b_integrated_evidence
  - ``--reference-window``         60d (descriptive only)

Outputs
-------

  - ``<output-dir>/block_b_integrated_evidence_report.json``
  - ``<output-dir>/block_b_integrated_evidence_report.md``

Status taxonomy
---------------

  * ``INSUFFICIENT_EVIDENCE``  - no usable Block B evidence on disk;
    next allowed phase = ``NEEDS_OPERATOR_EVIDENCE``.
  * ``PARTIAL_EVIDENCE``       - some evidence is present but the
    data-gap counter is high or no D-B post-discovery report can
    be loaded; next allowed phase = the Block C Replay /
    Reflection extension (paper-only).
  * ``EVIDENCE_GENERATED``     - D-B post-discovery report can be
    loaded and a discovery-quality bucket is computable; next
    allowed phase = the Block C Replay / Reflection extension
    (paper-only).

The status taxonomy is intentionally **not** ``ACCEPTED``. The
checkpoint never grants live-trading approval and never grants
auto-tuning approval. Use ``ACCEPTED`` only on the per-phase
closeout PRs whose docs explicitly read
``ACCEPTED_TOOLCHAIN`` / ``PARTIAL_QUALITY`` /
``BLOCK_B_CHECKPOINT_ONLY``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# Add project root to path so the runner can be invoked as a script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.adaptive.discovery_quality_scorecard import (  # noqa: E402
    DISCOVERY_QUALITY_SCORECARD_FORBIDDEN_PAYLOAD_KEYS,
    DISCOVERY_QUALITY_SCORECARD_SCHEMA_VERSION,
    DISCOVERY_QUALITY_SCORECARD_SOURCE_PHASE,
    DiscoveryQualityBucket,
    DiscoveryQualityScorecardForbiddenFieldError,
    DiscoveryQualityScorecardInput,
    assert_payload_has_no_forbidden_keys,
    build_discovery_quality_scorecard,
)


# ---------------------------------------------------------------------------
# Identity / constants
# ---------------------------------------------------------------------------


SOURCE_MODULE = "scripts.run_block_b_integrated_evidence_checkpoint"

BLOCK_B_INTEGRATED_EVIDENCE_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_e.block_b_integrated_evidence_checkpoint.v0"
)
BLOCK_B_INTEGRATED_EVIDENCE_SCHEMA_VERSION: str = (
    "phase_11c_1c_c_b_b_b_d_e.block_b_integrated_evidence_checkpoint.v1"
)
BLOCK_B_INTEGRATED_EVIDENCE_SOURCE_PHASE: str = (
    "phase_11c_1c_c_b_b_b_d_e_block_b_integrated_evidence_checkpoint_v0"
)


INSUFFICIENT_EVIDENCE_STATUS: str = "INSUFFICIENT_EVIDENCE"
PARTIAL_EVIDENCE_STATUS: str = "PARTIAL_EVIDENCE"
EVIDENCE_GENERATED_STATUS: str = "EVIDENCE_GENERATED"


NEXT_PHASE_REPLAY_REFLECTION: str = (
    "Phase 11C.1C-C-B-B-B-E-A Replay Extension for 11C Adaptive Events v0"
)
NEXT_PHASE_NEEDS_OPERATOR_EVIDENCE: str = "NEEDS_OPERATOR_EVIDENCE"


# Per-axis component statuses. None of these is a trade-approval
# label; they roll up into the Block B descriptive status only.
COMPONENT_STATUS_EVIDENCE_GENERATED: str = "EVIDENCE_GENERATED"
COMPONENT_STATUS_PARTIAL_EVIDENCE: str = "PARTIAL_EVIDENCE"
COMPONENT_STATUS_INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"


# Default thresholds used when rolling up data_gap_count into the
# Block B status. Descriptive only - changing them does NOT and
# CANNOT change any runtime knob.
DEFAULT_DATA_GAP_PARTIAL_RATE: float = 0.30
DEFAULT_DATA_GAP_HIGH_ABSOLUTE: int = 100


# Notable symbols pulled from the brief.
NOTABLE_SYMBOL_WATCHLIST: tuple[str, ...] = ("RAVEUSDT", "STOUSDT")


# Event-type strings (string-only - never imported from EventType so
# the runner stays usable when only an exported JSONL is available).
HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED = (
    "HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED"
)
HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED = (
    "HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED"
)
MOVER_CAPTURE_RECALL_AUDIT_GENERATED = "MOVER_CAPTURE_RECALL_AUDIT_GENERATED"
MOVER_CAPTURE_PATH_AUDITED = "MOVER_CAPTURE_PATH_AUDITED"
POST_DISCOVERY_OUTCOME_EVALUATED = "POST_DISCOVERY_OUTCOME_EVALUATED"
POST_DISCOVERY_OUTCOME_REPORT_GENERATED = (
    "POST_DISCOVERY_OUTCOME_REPORT_GENERATED"
)
REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED = (
    "REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED"
)
REJECT_TO_OUTCOME_CASE_ATTRIBUTED = "REJECT_TO_OUTCOME_CASE_ATTRIBUTED"
FALSE_NEGATIVE_REJECT_DETECTED = "FALSE_NEGATIVE_REJECT_DETECTED"
CORRECT_PROTECTIVE_REJECT_CONFIRMED = "CORRECT_PROTECTIVE_REJECT_CONFIRMED"
SEVERE_MISSED_TAIL_TRIAGE_GENERATED = "SEVERE_MISSED_TAIL_TRIAGE_GENERATED"
SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED = (
    "SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED"
)
SEVERE_MISS_ESCALATION_REQUIRED = "SEVERE_MISS_ESCALATION_REQUIRED"
DISCOVERY_QUALITY_SCORECARD_GENERATED = "DISCOVERY_QUALITY_SCORECARD_GENERATED"
DISCOVERY_QUALITY_BUCKET_EVALUATED = "DISCOVERY_QUALITY_BUCKET_EVALUATED"


_BLOCK_B_EVENT_TYPES: frozenset[str] = frozenset(
    {
        HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED,
        HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED,
        MOVER_CAPTURE_RECALL_AUDIT_GENERATED,
        MOVER_CAPTURE_PATH_AUDITED,
        POST_DISCOVERY_OUTCOME_EVALUATED,
        POST_DISCOVERY_OUTCOME_REPORT_GENERATED,
        REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED,
        REJECT_TO_OUTCOME_CASE_ATTRIBUTED,
        FALSE_NEGATIVE_REJECT_DETECTED,
        CORRECT_PROTECTIVE_REJECT_CONFIRMED,
        SEVERE_MISSED_TAIL_TRIAGE_GENERATED,
        SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED,
        SEVERE_MISS_ESCALATION_REQUIRED,
        DISCOVERY_QUALITY_SCORECARD_GENERATED,
        DISCOVERY_QUALITY_BUCKET_EVALUATED,
    }
)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckpointResult:
    """In-memory result of one checkpoint run.

    Paper / report / evidence only. No trade-authority field.
    """

    status: str
    next_allowed_phase: str
    output_report_path: Path
    output_summary_path: Path
    payload: Mapping[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_int(value: Any, *, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _iter_events_jsonl(root: Path) -> Iterable[dict[str, Any]]:
    """Yield each JSON-decoded event row from every events.jsonl /
    *.jsonl file under ``root``. Tolerates missing / unreadable
    files by skipping silently (the runner is read-only / tolerant).
    """

    if root is None or not root.is_dir():
        return
    seen: set[Path] = set()
    candidate_files: list[Path] = []
    candidate_files.extend(sorted(root.rglob("events.jsonl")))
    candidate_files.extend(sorted(root.rglob("*.jsonl")))
    for path in candidate_files:
        if path in seen:
            continue
        seen.add(path)
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
                    if isinstance(obj, dict):
                        yield obj
        except OSError:
            continue


def _count_events_by_type(
    sources: Sequence[Path],
) -> dict[str, int]:
    """Walk every ``events.jsonl`` / ``*.jsonl`` file under each
    ``sources`` directory and count Block B event types.
    """

    counts: dict[str, int] = {evt: 0 for evt in _BLOCK_B_EVENT_TYPES}
    for source in sources:
        if source is None:
            continue
        for obj in _iter_events_jsonl(source):
            event_type = obj.get("event_type")
            if not isinstance(event_type, str):
                continue
            if event_type in _BLOCK_B_EVENT_TYPES:
                counts[event_type] += 1
    return counts


def _load_latest_post_discovery_report(
    post_discovery_dir: Path | None,
) -> tuple[dict[str, Any] | None, Path | None]:
    """Find the most recent ``post_discovery_outcome_report.json``
    under ``post_discovery_dir`` (recursively) and return
    ``(payload, path)``.

    Returns ``(None, None)`` when the directory is missing or no
    report is reachable.
    """

    if post_discovery_dir is None or not post_discovery_dir.is_dir():
        return None, None
    candidates = sorted(
        post_discovery_dir.rglob("post_discovery_outcome_report.json"),
        key=lambda p: p.stat().st_mtime if p.is_file() else 0.0,
        reverse=True,
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not text.strip():
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj, path
    return None, None


def _load_latest_d_a_payload(
    sources: Sequence[Path],
) -> dict[str, Any] | None:
    """Walk ``sources`` for the most recent
    ``HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED`` event payload.
    """

    latest_payload: dict[str, Any] | None = None
    latest_ts: int = -1
    for source in sources:
        if source is None:
            continue
        for obj in _iter_events_jsonl(source):
            if (
                obj.get("event_type")
                != HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED
            ):
                continue
            payload = obj.get("payload")
            if not isinstance(payload, dict):
                continue
            ts = _safe_int(obj.get("timestamp"), default=-1)
            if ts >= latest_ts:
                latest_ts = ts
                latest_payload = payload
    return latest_payload


# ---------------------------------------------------------------------------
# Component status derivation
# ---------------------------------------------------------------------------


def _derive_d_a_status(
    *,
    d_a_payload: Mapping[str, Any] | None,
    record_audited_count: int,
) -> tuple[str, dict[str, Any]]:
    """Derive D-A component status + diagnostic block.

    The D-A audit is paper / report / evidence only. ``ACCEPTED``
    is intentionally NOT used here; the integrated checkpoint's
    rule is to surface evidence presence, not grant acceptance.
    """

    if d_a_payload is None and record_audited_count <= 0:
        return COMPONENT_STATUS_INSUFFICIENT_EVIDENCE, {
            "coverage_record_count": 0,
            "record_audited_event_count": 0,
        }

    coverage_record_count = 0
    if d_a_payload is not None:
        records = d_a_payload.get("records")
        if isinstance(records, (list, tuple)):
            coverage_record_count = len(records)
        else:
            coverage_record_count = _safe_int(
                d_a_payload.get("top_mover_count"), default=0
            )

    if coverage_record_count <= 0:
        coverage_record_count = record_audited_count

    if coverage_record_count <= 0:
        status = COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    else:
        status = COMPONENT_STATUS_EVIDENCE_GENERATED

    diag: dict[str, Any] = {
        "coverage_record_count": coverage_record_count,
        "record_audited_event_count": record_audited_count,
    }
    if d_a_payload is not None:
        diag["window_start_utc_ms"] = _safe_int(
            d_a_payload.get("window_start_utc_ms"), default=0
        )
        diag["window_end_utc_ms"] = _safe_int(
            d_a_payload.get("window_end_utc_ms"), default=0
        )
        diag["captured_top_mover_count"] = _safe_int(
            d_a_payload.get("captured_top_mover_count"), default=0
        )
        diag["missed_top_mover_count"] = _safe_int(
            d_a_payload.get("missed_top_mover_count"), default=0
        )
    return status, diag


def _derive_d_b_status(
    *,
    post_discovery_payload: Mapping[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """Derive D-B component status + diagnostic block."""

    if post_discovery_payload is None:
        return COMPONENT_STATUS_INSUFFICIENT_EVIDENCE, {
            "post_discovery_record_count": 0,
            "post_discovery_status": None,
        }
    raw_status = _safe_str(post_discovery_payload.get("status")) or ""
    evaluated = _safe_int(
        post_discovery_payload.get("evaluated_count"), default=0
    )
    diag: dict[str, Any] = {
        "post_discovery_record_count": evaluated,
        "post_discovery_status": raw_status or None,
        "post_discovery_report_generated_count": _safe_int(
            post_discovery_payload.get("report_generated_count"), default=0
        ),
    }
    if raw_status == "EVIDENCE_GENERATED" and evaluated > 0:
        return COMPONENT_STATUS_EVIDENCE_GENERATED, diag
    if raw_status in ("INSUFFICIENT_EVIDENCE", "INSUFFICIENT_EVALUABLE_RECORDS"):
        return COMPONENT_STATUS_INSUFFICIENT_EVIDENCE, diag
    if evaluated > 0:
        return COMPONENT_STATUS_PARTIAL_EVIDENCE, diag
    return COMPONENT_STATUS_INSUFFICIENT_EVIDENCE, diag


def _derive_b1_1_price_path_status(
    *,
    post_discovery_payload: Mapping[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    """Derive B1.1 component status + diagnostic block."""

    if post_discovery_payload is None:
        return COMPONENT_STATUS_INSUFFICIENT_EVIDENCE, {
            "price_path_records_loaded": 0,
            "price_path_records_missing": 0,
            "kline_interval_used": None,
        }
    loaded = _safe_int(
        post_discovery_payload.get("price_path_records_loaded"), default=0
    )
    missing = _safe_int(
        post_discovery_payload.get("price_path_records_missing"), default=0
    )
    interval = _safe_str(post_discovery_payload.get("kline_interval_used"))
    diag: dict[str, Any] = {
        "price_path_records_loaded": loaded,
        "price_path_records_missing": missing,
        "kline_interval_used": interval,
        "price_path_source_summary": dict(
            post_discovery_payload.get("price_path_source_summary") or {}
        ),
        "price_path_missing_reason_summary": dict(
            post_discovery_payload.get("price_path_missing_reason_summary")
            or {}
        ),
    }
    if loaded <= 0 and missing <= 0:
        return COMPONENT_STATUS_INSUFFICIENT_EVIDENCE, diag
    if loaded > 0 and missing == 0:
        return COMPONENT_STATUS_EVIDENCE_GENERATED, diag
    return COMPONENT_STATUS_PARTIAL_EVIDENCE, diag


def _derive_event_axis_status(
    *,
    generated_count: int,
    case_count: int,
) -> str:
    """Map event-emission counts to a component status.

    A component is :data:`COMPONENT_STATUS_EVIDENCE_GENERATED` when
    at least one report event was emitted; :data:`COMPONENT_STATUS_PARTIAL_EVIDENCE`
    when only case-level events were emitted (the report itself is
    missing); :data:`COMPONENT_STATUS_INSUFFICIENT_EVIDENCE` otherwise.
    """

    if generated_count > 0:
        return COMPONENT_STATUS_EVIDENCE_GENERATED
    if case_count > 0:
        return COMPONENT_STATUS_PARTIAL_EVIDENCE
    return COMPONENT_STATUS_INSUFFICIENT_EVIDENCE


def _build_notable_symbols_summary(
    *,
    post_discovery_payload: Mapping[str, Any] | None,
) -> dict[str, dict[str, str]]:
    """Build a compact notable-symbols summary, one entry per symbol
    in :data:`NOTABLE_SYMBOL_WATCHLIST`.
    """

    out: dict[str, dict[str, str]] = {}
    notable_block: Mapping[str, Any] = {}
    if post_discovery_payload is not None:
        raw = post_discovery_payload.get("notable_symbol_price_path_summary")
        if isinstance(raw, Mapping):
            notable_block = raw
    for symbol in NOTABLE_SYMBOL_WATCHLIST:
        info = notable_block.get(symbol) if isinstance(notable_block, Mapping) else None
        if isinstance(info, Mapping):
            out[symbol] = {
                "source": str(info.get("source", "")),
                "missing_reason": str(info.get("missing_reason", "")),
                "loaded": str(info.get("loaded", "")),
                "record_count": str(info.get("record_count", "")),
                "loaded_record_count": str(info.get("loaded_record_count", "")),
            }
        else:
            out[symbol] = {
                "source": "absent",
                "missing_reason": "no_post_discovery_payload",
                "loaded": "false",
                "record_count": "0",
                "loaded_record_count": "0",
            }
    return out


# ---------------------------------------------------------------------------
# Block B status roll-up
# ---------------------------------------------------------------------------


def _aggregate_block_b_status(
    *,
    component_statuses: Mapping[str, str],
    coverage_record_count: int,
    post_discovery_record_count: int,
    data_gap_count: int,
    discovery_quality_bucket: str | None,
    data_gap_partial_rate: float = DEFAULT_DATA_GAP_PARTIAL_RATE,
    data_gap_high_absolute: int = DEFAULT_DATA_GAP_HIGH_ABSOLUTE,
) -> str:
    """Roll up the per-axis component statuses into the Block B
    integrated status.

    Rule:
      - If every component is INSUFFICIENT_EVIDENCE -> INSUFFICIENT_EVIDENCE.
      - If D-B post-discovery is missing OR data-gap rate is high
        OR the discovery-quality bucket is unavailable / INSUFFICIENT
        -> PARTIAL_EVIDENCE.
      - Otherwise -> EVIDENCE_GENERATED.
    """

    has_any_evidence = any(
        s != COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
        for s in component_statuses.values()
    )
    if not has_any_evidence:
        return INSUFFICIENT_EVIDENCE_STATUS

    d_b_status = component_statuses.get("d_b_status")
    if d_b_status != COMPONENT_STATUS_EVIDENCE_GENERATED:
        return PARTIAL_EVIDENCE_STATUS

    if post_discovery_record_count <= 0:
        return PARTIAL_EVIDENCE_STATUS

    if data_gap_count >= max(0, int(data_gap_high_absolute)):
        return PARTIAL_EVIDENCE_STATUS
    if coverage_record_count > 0:
        if (data_gap_count / float(coverage_record_count)) >= float(
            data_gap_partial_rate
        ):
            return PARTIAL_EVIDENCE_STATUS

    if discovery_quality_bucket in (
        None,
        "",
        DiscoveryQualityBucket.INSUFFICIENT_EVIDENCE,
    ):
        return PARTIAL_EVIDENCE_STATUS

    return EVIDENCE_GENERATED_STATUS


def _next_allowed_phase(status: str) -> str:
    if status in (EVIDENCE_GENERATED_STATUS, PARTIAL_EVIDENCE_STATUS):
        return NEXT_PHASE_REPLAY_REFLECTION
    return NEXT_PHASE_NEEDS_OPERATOR_EVIDENCE


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------


def _format_markdown_summary(payload: Mapping[str, Any]) -> str:
    lines: list[str] = []
    lines.append(
        "# Phase 11C.1C-C-B-B-B-D-E Block B Integrated Evidence Checkpoint v0"
    )
    lines.append("")
    lines.append(
        "Paper / report / evidence only. Phase 12 remains FORBIDDEN."
    )
    lines.append("")
    lines.append(f"- status: {payload.get('status')}")
    lines.append(f"- reference_window: {payload.get('reference_window')}")
    lines.append(f"- generated_at_utc: {payload.get('generated_at_utc')}")
    lines.append(f"- next_allowed_phase: {payload.get('next_allowed_phase')}")
    lines.append(f"- phase_12_forbidden: {payload.get('phase_12_forbidden')}")
    lines.append(f"- auto_tuning_allowed: {payload.get('auto_tuning_allowed')}")
    lines.append("")
    lines.append("## Per-component statuses")
    lines.append(f"- d_a_status: {payload.get('d_a_status')}")
    lines.append(f"- d_b_status: {payload.get('d_b_status')}")
    lines.append(
        f"- b1_1_price_path_status: {payload.get('b1_1_price_path_status')}"
    )
    lines.append(
        f"- reject_attribution_status: "
        f"{payload.get('reject_attribution_status')}"
    )
    lines.append(
        f"- severe_miss_triage_status: "
        f"{payload.get('severe_miss_triage_status')}"
    )
    lines.append(
        f"- discovery_quality_scorecard_status: "
        f"{payload.get('discovery_quality_scorecard_status')}"
    )
    lines.append("")
    lines.append("## Counters")
    lines.append(f"- evaluated_count: {payload.get('evaluated_count')}")
    lines.append(
        f"- coverage_record_count: {payload.get('coverage_record_count')}"
    )
    lines.append(
        f"- post_discovery_record_count: "
        f"{payload.get('post_discovery_record_count')}"
    )
    lines.append(
        f"- price_path_records_loaded: "
        f"{payload.get('price_path_records_loaded')}"
    )
    lines.append(
        f"- price_path_records_missing: "
        f"{payload.get('price_path_records_missing')}"
    )
    lines.append(f"- severe_miss_count: {payload.get('severe_miss_count')}")
    lines.append(
        f"- false_negative_reject_count: "
        f"{payload.get('false_negative_reject_count')}"
    )
    lines.append(f"- data_gap_count: {payload.get('data_gap_count')}")
    lines.append(
        f"- discovery_quality_bucket: "
        f"{payload.get('discovery_quality_bucket')}"
    )
    lines.append("")
    lines.append("## Notable symbols")
    notable = payload.get("notable_symbols") or {}
    if isinstance(notable, Mapping):
        for symbol, info in sorted(notable.items()):
            if isinstance(info, Mapping):
                lines.append(
                    f"- {symbol}: source={info.get('source','')}, "
                    f"missing_reason={info.get('missing_reason','')}, "
                    f"loaded={info.get('loaded','')}, "
                    f"record_count={info.get('record_count','')}, "
                    f"loaded_record_count="
                    f"{info.get('loaded_record_count','')}"
                )
            else:
                lines.append(f"- {symbol}: {info}")
    lines.append("")
    blockers = payload.get("known_blockers") or []
    lines.append("## Known blockers")
    if blockers:
        for item in blockers:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    lines.append("")
    gaps = payload.get("known_non_blocking_gaps") or []
    lines.append("## Known non-blocking gaps")
    if gaps:
        for item in gaps:
            lines.append(f"- {item}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Block B event counts")
    event_counts = payload.get("block_b_event_counts") or {}
    if isinstance(event_counts, Mapping) and event_counts:
        for name, count in sorted(event_counts.items()):
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Safety boundary")
    lines.append("")
    lines.append(
        "- This checkpoint does NOT authorise live trading."
    )
    lines.append(
        "- This checkpoint does NOT authorise auto-tuning."
    )
    lines.append(
        "- This checkpoint does NOT prove strategy profitability."
    )
    lines.append(
        "- This is a Block B checkpoint, not a per-phase ACCEPTED gate."
    )
    lines.append(
        "- A successful checkpoint authorises only the Block C "
        "Replay / Reflection extension (paper / evidence only)."
    )
    lines.append("- Phase 12 remains FORBIDDEN.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _resolve_event_sources(
    *,
    reports_dir: Path | None,
    exports_dir: Path | None,
    post_discovery_dir: Path | None,
) -> list[Path]:
    """Return a deduplicated list of directories the runner should
    walk for Block B events. Missing directories are tolerated."""

    sources: list[Path] = []
    seen: set[Path] = set()
    for candidate in (reports_dir, exports_dir, post_discovery_dir):
        if candidate is None:
            continue
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        sources.append(candidate)
    return sources


def _build_discovery_quality_scorecard_payload(
    *,
    reference_window: str,
    coverage_record_count: int,
    post_discovery_payload: Mapping[str, Any] | None,
    severe_miss_count: int,
    false_negative_reject_count: int,
    correct_protective_reject_count: int,
    data_gap_count: int,
    insufficient_price_path_count: int,
    evidence_refs: Sequence[str],
) -> tuple[str | None, dict[str, Any] | None, dict[str, Any]]:
    """Compute a Discovery Quality Scorecard from the aggregated
    counts and return ``(bucket, scorecard_dict, derived_counts)``.

    ``coverage_record_count == 0`` -> bucket = ``INSUFFICIENT_EVIDENCE``.
    """

    captured = 0
    usable_discovery = 0
    early_discovery = 0
    late_chase = 0
    if post_discovery_payload is not None:
        report = post_discovery_payload.get("report")
        if isinstance(report, Mapping):
            label_summary = report.get("outcome_label_summary") or {}
            timing_summary = report.get("detection_timing_label_summary") or {}
            if isinstance(label_summary, Mapping):
                usable_discovery = (
                    _safe_int(label_summary.get("USABLE_UPSIDE"))
                    + _safe_int(label_summary.get("EARLY_DISCOVERY"))
                )
                early_discovery = _safe_int(label_summary.get("EARLY_DISCOVERY"))
                late_chase = _safe_int(label_summary.get("LATE_CHASE"))
                captured = max(
                    0,
                    coverage_record_count
                    - _safe_int(label_summary.get("MISSED_STRONG_TAIL"))
                    - _safe_int(label_summary.get("INSUFFICIENT_PRICE_PATH")),
                )
            elif isinstance(timing_summary, Mapping):
                captured = max(
                    0,
                    coverage_record_count
                    - _safe_int(timing_summary.get("MISSED"))
                    - _safe_int(timing_summary.get("INSUFFICIENT_DATA")),
                )

    derived = {
        "captured_count": captured,
        "usable_discovery_count": usable_discovery,
        "early_discovery_count": early_discovery,
        "late_chase_count": late_chase,
    }

    scorecard_input = DiscoveryQualityScorecardInput(
        reference_window=reference_window,
        coverage_total_count=max(0, coverage_record_count),
        captured_count=captured,
        missed_count=max(0, coverage_record_count - captured),
        usable_discovery_count=usable_discovery,
        early_discovery_count=early_discovery,
        late_chase_count=late_chase,
        severe_miss_count=max(0, severe_miss_count),
        insufficient_price_path_count=max(0, insufficient_price_path_count),
        false_negative_reject_count=max(0, false_negative_reject_count),
        correct_protective_reject_count=max(0, correct_protective_reject_count),
        data_gap_count=max(0, data_gap_count),
        evidence_refs=tuple(str(r) for r in evidence_refs if r),
    )
    scorecard = build_discovery_quality_scorecard(scorecard_input)
    sc_dict = scorecard.to_dict()
    bucket = sc_dict.get("quality_bucket")
    return (
        bucket if isinstance(bucket, str) else None,
        sc_dict,
        derived,
    )


def run_checkpoint(
    *,
    reports_dir: Path | None,
    exports_dir: Path | None,
    post_discovery_dir: Path | None,
    output_dir: Path,
    reference_window: str,
) -> CheckpointResult:
    """Run the Block B integrated evidence checkpoint once."""

    output_dir = Path(output_dir)
    output_report_path = (
        output_dir / "block_b_integrated_evidence_report.json"
    )
    output_summary_path = (
        output_dir / "block_b_integrated_evidence_report.md"
    )

    sources = _resolve_event_sources(
        reports_dir=reports_dir,
        exports_dir=exports_dir,
        post_discovery_dir=post_discovery_dir,
    )

    event_counts = _count_events_by_type(sources)
    d_a_payload = _load_latest_d_a_payload(sources)
    post_discovery_payload, post_discovery_path = (
        _load_latest_post_discovery_report(post_discovery_dir)
    )

    record_audited_count = event_counts.get(
        HISTORICAL_MOVER_COVERAGE_RECORD_AUDITED, 0
    )
    d_a_status, d_a_diag = _derive_d_a_status(
        d_a_payload=d_a_payload,
        record_audited_count=record_audited_count,
    )
    d_b_status, d_b_diag = _derive_d_b_status(
        post_discovery_payload=post_discovery_payload
    )
    b1_1_status, b1_1_diag = _derive_b1_1_price_path_status(
        post_discovery_payload=post_discovery_payload
    )
    reject_attribution_status = _derive_event_axis_status(
        generated_count=event_counts.get(
            REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED, 0
        ),
        case_count=event_counts.get(REJECT_TO_OUTCOME_CASE_ATTRIBUTED, 0),
    )
    severe_miss_status = _derive_event_axis_status(
        generated_count=event_counts.get(
            SEVERE_MISSED_TAIL_TRIAGE_GENERATED, 0
        ),
        case_count=event_counts.get(
            SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED, 0
        ),
    )
    discovery_quality_status = _derive_event_axis_status(
        generated_count=event_counts.get(
            DISCOVERY_QUALITY_SCORECARD_GENERATED, 0
        ),
        case_count=event_counts.get(DISCOVERY_QUALITY_BUCKET_EVALUATED, 0),
    )

    coverage_record_count = _safe_int(
        d_a_diag.get("coverage_record_count"), default=0
    )
    post_discovery_record_count = _safe_int(
        d_b_diag.get("post_discovery_record_count"), default=0
    )
    severe_miss_count = event_counts.get(
        SEVERE_MISSED_TAIL_ROOT_CAUSE_ASSIGNED, 0
    )
    false_negative_reject_count = event_counts.get(
        FALSE_NEGATIVE_REJECT_DETECTED, 0
    )
    correct_protective_reject_count = event_counts.get(
        CORRECT_PROTECTIVE_REJECT_CONFIRMED, 0
    )
    insufficient_price_path_count = _safe_int(
        b1_1_diag.get("price_path_records_missing"), default=0
    )

    # Data-gap accounting: in the absence of a single canonical
    # data-gap counter on disk, fall back to the conservative sum of
    # B1.1 missing-price-path records and any explicit data_gap
    # reasons surfaced by D-A.
    data_gap_count = insufficient_price_path_count
    if d_a_payload is not None:
        miss_summary = d_a_payload.get("miss_reason_summary")
        if isinstance(miss_summary, Mapping):
            for key, value in miss_summary.items():
                if not isinstance(key, str):
                    continue
                if "data" in key.lower() and "gap" in key.lower():
                    data_gap_count += _safe_int(value, default=0)

    evidence_refs: list[str] = []
    if d_a_payload is not None and coverage_record_count > 0:
        evidence_refs.append(
            f"evt://{HISTORICAL_MOVER_COVERAGE_BACKFILL_GENERATED}"
        )
    if post_discovery_payload is not None and post_discovery_record_count > 0:
        evidence_refs.append(f"evt://{POST_DISCOVERY_OUTCOME_REPORT_GENERATED}")
    if event_counts.get(SEVERE_MISSED_TAIL_TRIAGE_GENERATED, 0) > 0:
        evidence_refs.append(f"evt://{SEVERE_MISSED_TAIL_TRIAGE_GENERATED}")
    if event_counts.get(REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED, 0) > 0:
        evidence_refs.append(
            f"evt://{REJECT_TO_OUTCOME_ATTRIBUTION_GENERATED}"
        )
    if event_counts.get(DISCOVERY_QUALITY_SCORECARD_GENERATED, 0) > 0:
        evidence_refs.append(f"evt://{DISCOVERY_QUALITY_SCORECARD_GENERATED}")

    discovery_quality_bucket, discovery_quality_scorecard, derived_counts = (
        _build_discovery_quality_scorecard_payload(
            reference_window=reference_window,
            coverage_record_count=coverage_record_count,
            post_discovery_payload=post_discovery_payload,
            severe_miss_count=severe_miss_count,
            false_negative_reject_count=false_negative_reject_count,
            correct_protective_reject_count=correct_protective_reject_count,
            data_gap_count=data_gap_count,
            insufficient_price_path_count=insufficient_price_path_count,
            evidence_refs=evidence_refs,
        )
    )

    component_statuses = {
        "d_a_status": d_a_status,
        "d_b_status": d_b_status,
        "b1_1_price_path_status": b1_1_status,
        "reject_attribution_status": reject_attribution_status,
        "severe_miss_triage_status": severe_miss_status,
        "discovery_quality_scorecard_status": discovery_quality_status,
    }

    block_b_status = _aggregate_block_b_status(
        component_statuses=component_statuses,
        coverage_record_count=coverage_record_count,
        post_discovery_record_count=post_discovery_record_count,
        data_gap_count=data_gap_count,
        discovery_quality_bucket=discovery_quality_bucket,
    )
    next_phase = _next_allowed_phase(block_b_status)

    notable_symbols = _build_notable_symbols_summary(
        post_discovery_payload=post_discovery_payload
    )

    # Block B descriptive surface for known blockers / non-blocking
    # gaps. Both lists are descriptive only and never authorise a
    # rule change.
    known_blockers: list[str] = []
    known_non_blocking_gaps: list[str] = []

    if d_a_status == COMPONENT_STATUS_INSUFFICIENT_EVIDENCE:
        known_blockers.append("d_a_historical_mover_coverage_audit_missing")
    if d_b_status == COMPONENT_STATUS_INSUFFICIENT_EVIDENCE:
        known_blockers.append("d_b_post_discovery_outcome_metrics_missing")

    if (
        b1_1_status == COMPONENT_STATUS_PARTIAL_EVIDENCE
        and insufficient_price_path_count > 0
    ):
        known_non_blocking_gaps.append(
            "b1_1_price_path_partial_daily_bucket_only"
        )
    if reject_attribution_status == COMPONENT_STATUS_INSUFFICIENT_EVIDENCE:
        known_non_blocking_gaps.append(
            "b2_a_reject_attribution_no_paper_evidence_yet"
        )
    if severe_miss_status == COMPONENT_STATUS_INSUFFICIENT_EVIDENCE:
        known_non_blocking_gaps.append(
            "b2_b_severe_miss_triage_no_paper_evidence_yet"
        )
    if discovery_quality_status == COMPONENT_STATUS_INSUFFICIENT_EVIDENCE:
        known_non_blocking_gaps.append(
            "b3_discovery_quality_scorecard_no_paper_evidence_yet"
        )

    payload: dict[str, Any] = {
        "schema_version": BLOCK_B_INTEGRATED_EVIDENCE_SCHEMA_VERSION,
        "source_phase": BLOCK_B_INTEGRATED_EVIDENCE_SOURCE_PHASE,
        "source_module": SOURCE_MODULE,
        "reference_window": str(reference_window or "60d"),
        "generated_at_utc": _now_utc_iso(),
        "status": block_b_status,
        "next_allowed_phase": next_phase,
        "phase_12_forbidden": True,
        "auto_tuning_allowed": False,
        # Per-component statuses
        "d_a_status": d_a_status,
        "d_b_status": d_b_status,
        "b1_1_price_path_status": b1_1_status,
        "reject_attribution_status": reject_attribution_status,
        "severe_miss_triage_status": severe_miss_status,
        "discovery_quality_scorecard_status": discovery_quality_status,
        # Counters
        "evaluated_count": post_discovery_record_count,
        "coverage_record_count": coverage_record_count,
        "post_discovery_record_count": post_discovery_record_count,
        "price_path_records_loaded": _safe_int(
            b1_1_diag.get("price_path_records_loaded"), default=0
        ),
        "price_path_records_missing": insufficient_price_path_count,
        "severe_miss_count": severe_miss_count,
        "false_negative_reject_count": false_negative_reject_count,
        "correct_protective_reject_count": correct_protective_reject_count,
        "data_gap_count": data_gap_count,
        "discovery_quality_bucket": discovery_quality_bucket,
        # Per-component diagnostics + notable surface
        "d_a_diagnostics": d_a_diag,
        "d_b_diagnostics": d_b_diag,
        "b1_1_diagnostics": b1_1_diag,
        "discovery_quality_scorecard": discovery_quality_scorecard,
        "derived_counts": derived_counts,
        "notable_symbols": notable_symbols,
        "block_b_event_counts": event_counts,
        "evidence_refs": list(evidence_refs),
        # Source paths (descriptive only)
        "post_discovery_report_path": (
            str(post_discovery_path) if post_discovery_path else None
        ),
        # Operator routing surfaces
        "known_blockers": known_blockers,
        "known_non_blocking_gaps": known_non_blocking_gaps,
        "schema_versions": {
            "discovery_quality_scorecard": (
                DISCOVERY_QUALITY_SCORECARD_SCHEMA_VERSION
            ),
        },
        "source_phases": {
            "discovery_quality_scorecard": (
                DISCOVERY_QUALITY_SCORECARD_SOURCE_PHASE
            ),
        },
    }

    # Defensive: refuse to emit a payload that contains a forbidden
    # trade-authority / runtime-tuning key.
    assert_payload_has_no_forbidden_keys(
        payload,
        context="block_b_integrated_evidence_checkpoint",
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_report_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    output_summary_path.write_text(
        _format_markdown_summary(payload), encoding="utf-8"
    )

    return CheckpointResult(
        status=block_b_status,
        next_allowed_phase=next_phase,
        output_report_path=output_report_path,
        output_summary_path=output_summary_path,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 11C.1C-C-B-B-B-D-E - Block B Integrated Evidence "
            "Checkpoint v0. Paper / report / evidence only. "
            "Phase 12 remains FORBIDDEN."
        )
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("data/reports"),
        help="Root reports directory (default: data/reports).",
    )
    parser.add_argument(
        "--exports-dir",
        type=Path,
        default=Path("data/reports/exports"),
        help="Phase 8.5 export bundle directory.",
    )
    parser.add_argument(
        "--post-discovery-dir",
        type=Path,
        default=Path("data/reports/post_discovery_outcome"),
        help="D-B post-discovery outcome report directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/reports/block_b_integrated_evidence"),
        help="Where the checkpoint report + markdown are written.",
    )
    parser.add_argument(
        "--reference-window",
        type=str,
        default="60d",
        help="Audit-window label (descriptive only).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = run_checkpoint(
            reports_dir=args.reports_dir,
            exports_dir=args.exports_dir,
            post_discovery_dir=args.post_discovery_dir,
            output_dir=args.output_dir,
            reference_window=args.reference_window,
        )
    except DiscoveryQualityScorecardForbiddenFieldError as exc:
        # Surface the failure but never collapse silently.
        sys.stderr.write(
            "block_b_integrated_evidence_checkpoint: forbidden key in payload: "
            f"{exc}\n"
        )
        return 2
    sys.stdout.write(
        json.dumps(
            {
                "status": result.status,
                "next_allowed_phase": result.next_allowed_phase,
                "output_report": str(result.output_report_path),
                "output_summary": str(result.output_summary_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    sys.stdout.write("\n")
    if result.status == INSUFFICIENT_EVIDENCE_STATUS:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
