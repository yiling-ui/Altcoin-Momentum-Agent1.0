"""Phase 11C.1C-C-B-B-B-E-D - Block C Integrated Checkpoint v0.

Aggregates the simplified outputs of:

    * Phase 11C.1C-C-B-B-B-E-A   Replay Extension for 11C
      Adaptive Events v0 (C1)
    * Phase 11C.1C-C-B-B-B-E-B   Reflection Extension for 11C
      Adaptive Events v0 (C2)
    * Phase 11C.1C-C-B-B-B-E-C   Evidence Contract Baseline v0 (C3)

into a single descriptive **Block C integrated checkpoint report**.
The report is the input to the Block C / Block D decision: did the
Replay + Reflection + Evidence Contract triplet produce enough
evidence to authorise the next allowed phase (the Block D AI /
DeepSeek read-only intelligence-layer prep, AKA *AI Evidence Bundle*
preparation)?

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
``--block-b-dir`` and writes only files under ``--output-dir``.
Phase 12 remains FORBIDDEN. The Risk Engine remains the single
trade-decision gate.

Inputs
------
The runner accepts (all optional; the runner is tolerant of
missing / partial inputs):

  - ``--reports-dir``       data/reports
  - ``--exports-dir``       data/reports/exports
  - ``--block-b-dir``       data/reports/block_b_integrated_evidence
  - ``--output-dir``        data/reports/block_c_integrated_checkpoint
  - ``--reference-window``  60d (descriptive only)

Outputs
-------

  - ``<output-dir>/block_c_integrated_checkpoint_report.json``
  - ``<output-dir>/block_c_integrated_checkpoint_report.md``

Status taxonomy
---------------

  * ``INSUFFICIENT_EVIDENCE``  - no usable Block C input on disk;
    next allowed phase = ``NEEDS_OPERATOR_EVIDENCE``.
  * ``PARTIAL_EVIDENCE``       - Replay / Reflection / Evidence
    Contract are at least partially runnable but missing
    evidence or degraded claims remain; next allowed phase =
    AI Evidence Bundle preparation only (paper / read-only).
  * ``EVIDENCE_GENERATED``     - Replay / Reflection / Evidence
    Contract all produce valid output and no blocker remains;
    next allowed phase = AI Evidence Bundle Builder preparation
    (paper / read-only).

The status taxonomy is intentionally **not** ``ACCEPTED``. The
checkpoint never grants live-trading approval and never grants
auto-tuning approval. A successful Block C checkpoint only
allows the AI read-only evidence-bundle prep (the Block D
front-loaded engineering), not the DeepSeek hot path and not
Phase 12.
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

# Imports from allowed packages only:
#   - app.core.events      (canonical Event / EventType)
#   - app.replay           (C1 replay extension v0)
#   - app.reflection       (C2 reflection extension v0)
#   - app.evidence         (C3 evidence contract baseline v0)
#
# The runner MUST NOT import:
#   - app.risk             (forbidden)
#   - app.execution        (forbidden)
#   - app.exchanges        (forbidden)
#   - app.llm              (forbidden)
#   - app.telegram         (forbidden)
#   - app.config           (forbidden by brief)
from app.core.events import Event, EventType  # noqa: E402
from app.evidence.evidence_contract import (  # noqa: E402
    EVIDENCE_CONTRACT_BASELINE_SCHEMA_VERSION,
    EVIDENCE_CONTRACT_SOURCE_PHASE,
    FORBIDDEN_EVIDENCE_PAYLOAD_KEYS,
    ClaimStatus,
    EvidenceClaimInput,
    EvidenceContractValidator,
)
from app.reflection.adaptive_11c import (  # noqa: E402
    ADAPTIVE_REFLECTION_EVENT_TYPES,
    Reflection11CAdaptiveEngine,
)
from app.replay.adaptive_replay_11c import (  # noqa: E402
    ADAPTIVE_REPLAY_EVENT_TYPES,
    CANDIDATE_LIFECYCLE_EVENT_TYPES,
    DISCOVERY_QUALITY_EVENT_TYPES,
    DISCOVERY_TIMELINE_EVENT_TYPES,
    MOVER_COVERAGE_EVENT_TYPES,
    PAPER_ALPHA_EVENT_TYPES,
    POST_DISCOVERY_OUTCOME_EVENT_TYPES,
    REGIME_CLUSTER_EVENT_TYPES,
    REJECT_ATTRIBUTION_EVENT_TYPES,
    SEVERE_MISS_EVENT_TYPES,
    STRATEGY_VALIDATION_EVENT_TYPES,
    TAIL_OUTCOME_EVENT_TYPES,
    build_candidate_lifecycles,
    build_discovery_quality_cases,
    build_discovery_timelines,
    build_mover_coverage_cases,
    build_post_discovery_outcome_cases,
    build_reject_attribution_cases,
    build_severe_miss_cases,
    build_tail_outcomes,
)


# ---------------------------------------------------------------------------
# Identity / constants
# ---------------------------------------------------------------------------
SOURCE_MODULE: str = "scripts.run_block_c_integrated_checkpoint"

BLOCK_C_INTEGRATED_CHECKPOINT_SCHEMA_VERSION: str = (
    "phase_11c_1c_c_b_b_b_e_d.block_c_integrated_checkpoint.v1"
)
BLOCK_C_INTEGRATED_CHECKPOINT_SOURCE_PHASE: str = (
    "phase_11c_1c_c_b_b_b_e_d_block_c_integrated_checkpoint_v0"
)


INSUFFICIENT_EVIDENCE_STATUS: str = "INSUFFICIENT_EVIDENCE"
PARTIAL_EVIDENCE_STATUS: str = "PARTIAL_EVIDENCE"
EVIDENCE_GENERATED_STATUS: str = "EVIDENCE_GENERATED"


# Per-axis component statuses. None of these is a trade-approval
# label; they roll up into the Block C descriptive status only.
COMPONENT_STATUS_EVIDENCE_GENERATED: str = "EVIDENCE_GENERATED"
COMPONENT_STATUS_PARTIAL_EVIDENCE: str = "PARTIAL_EVIDENCE"
COMPONENT_STATUS_INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"


NEXT_PHASE_AI_EVIDENCE_BUNDLE_PREP: str = (
    "Phase AI-0 / AI Evidence Bundle preparation (paper / read-only)"
)
NEXT_PHASE_NEEDS_OPERATOR_EVIDENCE: str = "NEEDS_OPERATOR_EVIDENCE"


# ---------------------------------------------------------------------------
# Forbidden-payload guard (defensive)
# ---------------------------------------------------------------------------
# Block-C-specific superset of the C3 contract's forbidden vocabulary.
# We re-list the keys here so the runner's guard cannot drift away
# from the C3 module's guard if a downstream regression mutates the
# upstream set.
_FORBIDDEN_BLOCK_C_PAYLOAD_KEYS: frozenset[str] = frozenset(
    set(FORBIDDEN_EVIDENCE_PAYLOAD_KEYS)
    | {
        # Defensive aliases that are not in the C3 contract but the
        # Block C brief explicitly forbids.
        "trading_approved",
        "live_ready",
        "live_trading_allowed",
    }
)


def _assert_no_forbidden_keys(payload: Any, *, context: str) -> None:
    """Raise :class:`ValueError` if any forbidden key appears at any
    nesting depth.
    """

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_str = str(key)
            if key_str in _FORBIDDEN_BLOCK_C_PAYLOAD_KEYS:
                raise ValueError(
                    f"block_c_integrated_checkpoint produced a forbidden "
                    f"payload key {key_str!r} in {context!r}; this is a "
                    "hard violation of Phase 11C.1C-C-B-B-B-E-D boundary."
                )
            _assert_no_forbidden_keys(value, context=context)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            _assert_no_forbidden_keys(item, context=context)


# ---------------------------------------------------------------------------
# Result dataclass
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
# Event-group registry
# ---------------------------------------------------------------------------
# Closed event-group vocabulary the runner reports against. Each
# entry maps a stable group name -> the EventType members the C1
# replay extension consumes for that group.
_BLOCK_C_EVENT_GROUPS: tuple[tuple[str, tuple[EventType, ...]], ...] = (
    ("DISCOVERY_TIMELINE", DISCOVERY_TIMELINE_EVENT_TYPES),
    ("CANDIDATE_LIFECYCLE", CANDIDATE_LIFECYCLE_EVENT_TYPES),
    ("TAIL_OUTCOME", TAIL_OUTCOME_EVENT_TYPES),
    ("MOVER_COVERAGE", MOVER_COVERAGE_EVENT_TYPES),
    ("POST_DISCOVERY_OUTCOME", POST_DISCOVERY_OUTCOME_EVENT_TYPES),
    ("REJECT_ATTRIBUTION", REJECT_ATTRIBUTION_EVENT_TYPES),
    ("SEVERE_MISS", SEVERE_MISS_EVENT_TYPES),
    ("DISCOVERY_QUALITY", DISCOVERY_QUALITY_EVENT_TYPES),
    ("STRATEGY_VALIDATION", STRATEGY_VALIDATION_EVENT_TYPES),
    ("PAPER_ALPHA", PAPER_ALPHA_EVENT_TYPES),
    ("REGIME_CLUSTER", REGIME_CLUSTER_EVENT_TYPES),
)


_GROUP_BY_EVENT_TYPE: dict[EventType, str] = {
    et: name for name, types in _BLOCK_C_EVENT_GROUPS for et in types
}


_REPLAY_EVENT_TYPE_VALUES: frozenset[str] = frozenset(
    et.value for et in ADAPTIVE_REPLAY_EVENT_TYPES
)


_REFLECTION_EVENT_TYPE_VALUES: frozenset[str] = frozenset(
    et.value for et in ADAPTIVE_REFLECTION_EVENT_TYPES
)


_EVENT_TYPE_BY_VALUE: dict[str, EventType] = {
    et.value: et for et in EventType
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value)


def _stable_event_id(row: Mapping[str, Any], index: int) -> str:
    """Return ``row['event_id']`` if present and a non-empty string;
    otherwise a deterministic synthetic id derived from the row's
    event_type, timestamp, and stream index. The synthetic id is
    stable across runs over identical input.
    """

    raw = row.get("event_id")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    et = str(row.get("event_type") or "UNKNOWN")
    ts = _safe_int(row.get("timestamp"), default=0)
    return f"synthetic:{et}:{ts}:{index}"


# ---------------------------------------------------------------------------
# JSONL ingestion
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


def _load_adaptive_events_from_sources(
    sources: Sequence[Path],
) -> list[Event]:
    """Walk ``sources`` and return every JSONL row that maps to a
    known adaptive ``EventType`` as an :class:`Event` instance.

    Rows whose ``event_type`` does not map to a known adaptive type
    are silently skipped. The output is sorted by
    ``(timestamp, event_type, event_id)`` so downstream replay /
    reflection output is deterministic across runs.
    """

    events: list[Event] = []
    seen_ids: set[str] = set()
    global_index = 0
    for source in sources:
        if source is None:
            continue
        for row in _iter_events_jsonl(source):
            global_index += 1
            et_value = row.get("event_type")
            if not isinstance(et_value, str):
                continue
            # Restrict to adaptive event types so the runner does not
            # accidentally pick up unrelated Phase 1 / Phase 8.5 rows.
            if (
                et_value not in _REPLAY_EVENT_TYPE_VALUES
                and et_value not in _REFLECTION_EVENT_TYPE_VALUES
            ):
                continue
            et = _EVENT_TYPE_BY_VALUE.get(et_value)
            if et is None:
                continue

            payload = row.get("payload")
            if not isinstance(payload, dict):
                payload = {}

            event_id = _stable_event_id(row, global_index)
            if event_id in seen_ids:
                continue
            seen_ids.add(event_id)

            symbol = row.get("symbol")
            if symbol is not None and not isinstance(symbol, str):
                symbol = str(symbol)

            position_id = row.get("position_id")
            if position_id is not None and not isinstance(position_id, str):
                position_id = str(position_id)

            order_id = row.get("order_id")
            if order_id is not None and not isinstance(order_id, str):
                order_id = str(order_id)

            timestamp = _safe_int(row.get("timestamp"), default=0)
            source_module = row.get("source_module")
            if not isinstance(source_module, str):
                source_module = "block_c_integrated_checkpoint.import"

            events.append(
                Event(
                    event_type=et,
                    source_module=source_module,
                    payload=payload,
                    symbol=symbol,
                    position_id=position_id,
                    order_id=order_id,
                    timestamp=timestamp,
                    event_id=event_id,
                )
            )

    events.sort(
        key=lambda ev: (int(ev.timestamp), ev.event_type.value, ev.event_id)
    )
    return events


# ---------------------------------------------------------------------------
# Block B checkpoint loader
# ---------------------------------------------------------------------------
def _load_block_b_report(
    block_b_dir: Path | None,
) -> tuple[dict[str, Any] | None, Path | None]:
    """Find the most recent ``block_b_integrated_evidence_report.json``
    under ``block_b_dir`` (recursively) and return ``(payload, path)``.

    Returns ``(None, None)`` when the directory is missing or no
    report can be loaded.
    """

    if block_b_dir is None or not block_b_dir.is_dir():
        return None, None
    candidates = sorted(
        block_b_dir.rglob("block_b_integrated_evidence_report.json"),
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


# ---------------------------------------------------------------------------
# Replay roll-up
# ---------------------------------------------------------------------------
def _build_replay_summary(events: Sequence[Event]) -> dict[str, Any]:
    """Run every C1 builder against ``events`` and return a summary.

    The summary carries per-replay-object counts and a per-group
    event-count map. The C1 builders are pure / deterministic and
    require no :class:`EventRepository`.
    """

    discovery_timelines = build_discovery_timelines(events)
    candidate_lifecycles = build_candidate_lifecycles(events)
    tail_outcomes = build_tail_outcomes(events)
    mover_coverage = build_mover_coverage_cases(events)
    post_discovery = build_post_discovery_outcome_cases(events)
    reject_attribution = build_reject_attribution_cases(events)
    severe_miss = build_severe_miss_cases(events)
    discovery_quality = build_discovery_quality_cases(events)

    per_group_event_counts: dict[str, int] = {
        name: 0 for name, _ in _BLOCK_C_EVENT_GROUPS
    }
    for ev in events:
        group = _GROUP_BY_EVENT_TYPE.get(ev.event_type)
        if group is None:
            continue
        per_group_event_counts[group] += 1

    case_counts: dict[str, int] = {
        "discovery_timeline_count": len(discovery_timelines),
        "candidate_lifecycle_count": len(candidate_lifecycles),
        "tail_outcome_count": len(tail_outcomes),
        "mover_coverage_case_count": len(mover_coverage),
        "post_discovery_outcome_case_count": len(post_discovery),
        "reject_attribution_case_count": len(reject_attribution),
        "severe_miss_case_count": len(severe_miss),
        "discovery_quality_case_count": len(discovery_quality),
    }
    total_replay_cases = sum(case_counts.values())

    return {
        "input_event_count": len(events),
        "total_replay_case_count": total_replay_cases,
        "case_counts": case_counts,
        "per_group_event_counts": per_group_event_counts,
    }


def _derive_replay_status(replay_summary: Mapping[str, Any]) -> str:
    """Map the replay summary to a component status."""

    input_event_count = _safe_int(
        replay_summary.get("input_event_count"), default=0
    )
    total_cases = _safe_int(
        replay_summary.get("total_replay_case_count"), default=0
    )
    if input_event_count <= 0:
        return COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    if total_cases <= 0:
        return COMPONENT_STATUS_PARTIAL_EVIDENCE
    return COMPONENT_STATUS_EVIDENCE_GENERATED


# ---------------------------------------------------------------------------
# Reflection roll-up
# ---------------------------------------------------------------------------
def _build_reflection_summary(
    events: Sequence[Event],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run the C2 reflection engine and return (summary_payload, cases).

    ``cases`` is a list of dicts (one per :class:`AdaptiveReflectionCase`)
    so the runner can fold each case into the C3 evidence-contract
    claim list without reaching into private dataclass fields.
    """

    engine = Reflection11CAdaptiveEngine()
    summary = engine.reflect_events(events)
    summary_payload: dict[str, Any] = {
        "total_input_event_count": int(summary.total_input_event_count),
        "total_case_count": int(summary.total_case_count),
        "skipped_event_count": int(summary.skipped_event_count),
        "tag_counts": dict(sorted(summary.tag_counts.items())),
        "severity_counts": dict(sorted(summary.severity_counts.items())),
        "needs_operator_review_count": int(
            summary.needs_operator_review_count
        ),
        "needs_data_recovery_count": int(summary.needs_data_recovery_count),
        "needs_rule_review_count": int(summary.needs_rule_review_count),
        "auto_tuning_allowed": False,
    }
    case_dicts: list[dict[str, Any]] = []
    for case in summary.cases:
        case_dicts.append(
            {
                "case_id": case.case_id,
                "event_type": case.event_type,
                "tags": list(case.tags),
                "severity": case.severity,
                "evidence_refs": list(case.evidence_refs),
                "needs_operator_review": bool(case.needs_operator_review),
                "needs_data_recovery": bool(case.needs_data_recovery),
                "needs_rule_review": bool(case.needs_rule_review),
            }
        )
    return summary_payload, case_dicts


def _derive_reflection_status(
    reflection_summary: Mapping[str, Any],
) -> str:
    """Map the reflection summary to a component status."""

    inputs = _safe_int(
        reflection_summary.get("total_input_event_count"), default=0
    )
    cases = _safe_int(
        reflection_summary.get("total_case_count"), default=0
    )
    if inputs <= 0:
        return COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    if cases <= 0:
        return COMPONENT_STATUS_PARTIAL_EVIDENCE
    return COMPONENT_STATUS_EVIDENCE_GENERATED


# ---------------------------------------------------------------------------
# Evidence-contract roll-up
# ---------------------------------------------------------------------------
def _build_evidence_claims(
    *,
    events: Sequence[Event],
    reflection_cases: Sequence[Mapping[str, Any]],
    block_b_payload: Mapping[str, Any] | None,
    block_b_path: Path | None,
    per_group_event_counts: Mapping[str, int],
) -> list[EvidenceClaimInput]:
    """Assemble the claim list the C3 validator runs against.

    The claim mix exercises ACCEPTED + DEGRADED + (potentially)
    REJECTED outcomes so the integrated checkpoint surfaces a
    realistic ``accepted_claim_count`` /
    ``degraded_claim_count`` / ``rejected_claim_count`` split.

    Three claim families:

      1. One ``replay_layer_overall`` claim plus one claim per
         **non-empty** replay event group. Each replay claim's
         ``evidence_refs`` is the list of
         ``event:<EVENT_TYPE>:<event_id>`` strings derived from
         the events that landed in that group / overall stream.
         If the event stream is empty, the overall claim is
         degraded (no evidence) and no per-group claims are
         emitted; per-group coverage gaps are surfaced via
         ``unsupported_event_groups`` / ``known_gaps`` instead of
         degraded claims.

      2. One claim per reflection case. ``evidence_refs`` is the
         case's own evidence refs filtered to the canonical
         ``event:<EVENT_TYPE>:<event_id>`` shape with the
         case_id-derived fallback.

      3. One claim for the Block B integrated evidence checkpoint
         report. ``evidence_refs`` carries one ``report:`` ref
         when the report is loadable; the claim is degraded
         otherwise.
    """

    claims: list[EvidenceClaimInput] = []

    # Index events by group so we can attach concrete refs per claim.
    events_by_group: dict[str, list[Event]] = {
        name: [] for name, _ in _BLOCK_C_EVENT_GROUPS
    }
    for ev in events:
        group = _GROUP_BY_EVENT_TYPE.get(ev.event_type)
        if group is None:
            continue
        events_by_group[group].append(ev)

    # Family 1a: replay layer overall claim.
    overall_refs = tuple(
        f"event:{ev.event_type.value}:{ev.event_id}"
        for ev in events[:64]
    )
    claims.append(
        EvidenceClaimInput(
            claim_id="replay_layer_overall",
            claim_type="REPLAY_LAYER_OVERALL",
            text_or_label="Block C replay layer overall coverage",
            evidence_refs=overall_refs,
            confidence_label="medium" if overall_refs else None,
        )
    )

    # Family 1b: one claim per non-empty replay event group.
    # Per-group coverage gaps are intentionally NOT surfaced as
    # degraded claims (which would drag every run with anything
    # less than full 11-group coverage into PARTIAL). They are
    # surfaced via ``unsupported_event_groups`` / ``known_gaps``
    # instead.
    for group_name, _ in _BLOCK_C_EVENT_GROUPS:
        group_events = events_by_group.get(group_name) or []
        if not group_events:
            continue
        capped = group_events[:32]
        refs = tuple(
            f"event:{ev.event_type.value}:{ev.event_id}"
            for ev in capped
        )
        claims.append(
            EvidenceClaimInput(
                claim_id=f"replay_group:{group_name}",
                claim_type="REPLAY_GROUP_COVERAGE",
                text_or_label=(
                    f"Block C replay coverage for event group {group_name}"
                ),
                evidence_refs=refs,
                confidence_label="medium",
            )
        )

    # Family 2: one claim per reflection case.
    for case in reflection_cases:
        case_id = str(case.get("case_id") or "")
        event_type = str(case.get("event_type") or "")
        evidence_refs = tuple(
            ref
            for ref in (case.get("evidence_refs") or ())
            if isinstance(ref, str) and ref.startswith("event:")
        )
        if not evidence_refs and event_type and case_id:
            evidence_refs = (f"event:{event_type}:{case_id}",)
        claims.append(
            EvidenceClaimInput(
                claim_id=f"reflection_case:{case_id or 'anon'}",
                claim_type="REFLECTION_CASE",
                text_or_label=event_type or "reflection_case",
                evidence_refs=evidence_refs,
                confidence_label="medium" if evidence_refs else None,
            )
        )

    # Family 3: Block B integrated evidence checkpoint claim.
    block_b_refs: tuple[str, ...] = ()
    if block_b_payload is not None and block_b_path is not None:
        report_id = block_b_path.stem or "block_b_integrated_evidence_report"
        block_b_refs = (f"report:{report_id}",)
    claims.append(
        EvidenceClaimInput(
            claim_id="block_b_integrated_evidence_report",
            claim_type="BLOCK_B_CHECKPOINT",
            text_or_label="Block B integrated evidence checkpoint loaded",
            evidence_refs=block_b_refs,
            confidence_label="medium" if block_b_refs else None,
        )
    )

    # Suppress unused-arg warnings; ``per_group_event_counts`` is
    # accepted to keep the public signature stable / readable even
    # though the body re-derives the per-group breakdown from the
    # event list.
    _ = per_group_event_counts
    return claims


def _derive_evidence_contract_status(
    *,
    total_claim_count: int,
    accepted_claim_count: int,
    degraded_claim_count: int,
    rejected_claim_count: int,
    missing_evidence_count: int,
    invalid_evidence_count: int,
) -> str:
    """Map the evidence-contract counters to a component status."""

    if total_claim_count <= 0:
        return COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    if accepted_claim_count <= 0:
        return COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    if (
        degraded_claim_count > 0
        or rejected_claim_count > 0
        or missing_evidence_count > 0
        or invalid_evidence_count > 0
    ):
        return COMPONENT_STATUS_PARTIAL_EVIDENCE
    return COMPONENT_STATUS_EVIDENCE_GENERATED


# ---------------------------------------------------------------------------
# Block C status roll-up
# ---------------------------------------------------------------------------
def _aggregate_block_c_status(
    *,
    replay_status: str,
    reflection_status: str,
    evidence_contract_status: str,
    has_any_input: bool,
    has_blockers: bool,
) -> str:
    """Roll up the per-axis component statuses into the Block C
    integrated status.

    Rule:
      - If there is no usable input (no adaptive events AND no
        Block B report) -> INSUFFICIENT_EVIDENCE.
      - If every component is INSUFFICIENT_EVIDENCE ->
        INSUFFICIENT_EVIDENCE.
      - If every component is EVIDENCE_GENERATED AND there is no
        blocker -> EVIDENCE_GENERATED.
      - Otherwise -> PARTIAL_EVIDENCE.
    """

    if not has_any_input:
        return INSUFFICIENT_EVIDENCE_STATUS

    statuses = (
        replay_status,
        reflection_status,
        evidence_contract_status,
    )
    if all(s == COMPONENT_STATUS_INSUFFICIENT_EVIDENCE for s in statuses):
        return INSUFFICIENT_EVIDENCE_STATUS
    if has_blockers:
        return PARTIAL_EVIDENCE_STATUS
    if all(s == COMPONENT_STATUS_EVIDENCE_GENERATED for s in statuses):
        return EVIDENCE_GENERATED_STATUS
    return PARTIAL_EVIDENCE_STATUS


def _next_allowed_phase(status: str) -> str:
    if status in (EVIDENCE_GENERATED_STATUS, PARTIAL_EVIDENCE_STATUS):
        return NEXT_PHASE_AI_EVIDENCE_BUNDLE_PREP
    return NEXT_PHASE_NEEDS_OPERATOR_EVIDENCE


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------
def _format_markdown_summary(payload: Mapping[str, Any]) -> str:
    lines: list[str] = []
    lines.append(
        "# Phase 11C.1C-C-B-B-B-E-D Block C Integrated Checkpoint v0"
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
    lines.append(
        f"- auto_tuning_allowed: {payload.get('auto_tuning_allowed')}"
    )
    lines.append("")
    lines.append("## Per-component statuses")
    lines.append(f"- replay_status: {payload.get('replay_status')}")
    lines.append(f"- reflection_status: {payload.get('reflection_status')}")
    lines.append(
        f"- evidence_contract_status: "
        f"{payload.get('evidence_contract_status')}"
    )
    lines.append("")
    lines.append("## Counters")
    lines.append(f"- replay_case_count: {payload.get('replay_case_count')}")
    lines.append(
        f"- reflection_case_count: {payload.get('reflection_case_count')}"
    )
    lines.append(
        f"- evidence_claim_count: {payload.get('evidence_claim_count')}"
    )
    lines.append(
        f"- accepted_claim_count: {payload.get('accepted_claim_count')}"
    )
    lines.append(
        f"- degraded_claim_count: {payload.get('degraded_claim_count')}"
    )
    lines.append(
        f"- rejected_claim_count: {payload.get('rejected_claim_count')}"
    )
    lines.append(
        f"- missing_evidence_count: "
        f"{payload.get('missing_evidence_count')}"
    )
    lines.append(
        f"- invalid_evidence_count: "
        f"{payload.get('invalid_evidence_count')}"
    )
    lines.append("")
    lines.append("## Supported event groups")
    for group in payload.get("supported_event_groups") or []:
        lines.append(f"- {group}")
    if not payload.get("supported_event_groups"):
        lines.append("- (none)")
    lines.append("")
    lines.append("## Unsupported event groups")
    for group in payload.get("unsupported_event_groups") or []:
        lines.append(f"- {group}")
    if not payload.get("unsupported_event_groups"):
        lines.append("- (none)")
    lines.append("")
    lines.append("## Known gaps")
    for item in payload.get("known_gaps") or []:
        lines.append(f"- {item}")
    if not payload.get("known_gaps"):
        lines.append("- (none)")
    lines.append("")
    lines.append("## Known blockers")
    for item in payload.get("known_blockers") or []:
        lines.append(f"- {item}")
    if not payload.get("known_blockers"):
        lines.append("- (none)")
    lines.append("")
    lines.append("## Safety boundary")
    lines.append("")
    lines.append("- This checkpoint does NOT authorise live trading.")
    lines.append("- This checkpoint does NOT authorise auto-tuning.")
    lines.append("- This checkpoint does NOT call DeepSeek / any LLM.")
    lines.append(
        "- A successful Block C checkpoint only allows the AI "
        "Evidence Bundle preparation (paper / read-only); it does "
        "NOT authorise the DeepSeek hot path and it does NOT "
        "authorise Phase 12."
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
    block_b_dir: Path | None,
) -> list[Path]:
    """Return a deduplicated list of directories the runner walks."""

    sources: list[Path] = []
    seen: set[Path] = set()
    for candidate in (reports_dir, exports_dir, block_b_dir):
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


def run_checkpoint(
    *,
    reports_dir: Path | None,
    exports_dir: Path | None,
    block_b_dir: Path | None,
    output_dir: Path,
    reference_window: str,
) -> CheckpointResult:
    """Run the Block C integrated checkpoint once."""

    output_dir = Path(output_dir)
    output_report_path = (
        output_dir / "block_c_integrated_checkpoint_report.json"
    )
    output_summary_path = (
        output_dir / "block_c_integrated_checkpoint_report.md"
    )

    sources = _resolve_event_sources(
        reports_dir=reports_dir,
        exports_dir=exports_dir,
        block_b_dir=block_b_dir,
    )

    events = _load_adaptive_events_from_sources(sources)
    block_b_payload, block_b_path = _load_block_b_report(block_b_dir)

    # ------------------------------------------------------------------
    # Replay layer (C1)
    # ------------------------------------------------------------------
    replay_summary = _build_replay_summary(events)
    replay_status = _derive_replay_status(replay_summary)
    replay_case_count = _safe_int(
        replay_summary.get("total_replay_case_count"), default=0
    )

    # ------------------------------------------------------------------
    # Reflection layer (C2)
    # ------------------------------------------------------------------
    reflection_summary, reflection_cases = _build_reflection_summary(events)
    reflection_status = _derive_reflection_status(reflection_summary)
    reflection_case_count = _safe_int(
        reflection_summary.get("total_case_count"), default=0
    )

    # ------------------------------------------------------------------
    # Evidence-contract layer (C3)
    # ------------------------------------------------------------------
    claims = _build_evidence_claims(
        events=events,
        reflection_cases=reflection_cases,
        block_b_payload=block_b_payload,
        block_b_path=block_b_path,
        per_group_event_counts=replay_summary.get("per_group_event_counts")
        or {},
    )
    validator = EvidenceContractValidator(
        source_phase=BLOCK_C_INTEGRATED_CHECKPOINT_SOURCE_PHASE
    )
    evidence_result = validator.validate(claims)
    evidence_payload = evidence_result.to_dict()

    accepted_claim_count = int(evidence_result.accepted_claim_count)
    degraded_claim_count = int(evidence_result.degraded_claim_count)
    rejected_claim_count = int(evidence_result.rejected_claim_count)
    partial_claim_count = int(evidence_result.partial_claim_count)
    missing_evidence_count = int(evidence_result.missing_evidence_count)
    invalid_evidence_count = int(evidence_result.invalid_evidence_count)
    total_claim_count = int(evidence_result.total_claim_count)

    evidence_contract_status = _derive_evidence_contract_status(
        total_claim_count=total_claim_count,
        accepted_claim_count=accepted_claim_count,
        degraded_claim_count=degraded_claim_count,
        rejected_claim_count=rejected_claim_count,
        missing_evidence_count=missing_evidence_count,
        invalid_evidence_count=invalid_evidence_count,
    )

    # ------------------------------------------------------------------
    # Supported / unsupported event groups
    # ------------------------------------------------------------------
    supported_event_groups: list[str] = []
    unsupported_event_groups: list[str] = []
    per_group = replay_summary.get("per_group_event_counts") or {}
    for group_name, _ in _BLOCK_C_EVENT_GROUPS:
        count = _safe_int(per_group.get(group_name), default=0)
        if count > 0:
            supported_event_groups.append(group_name)
        else:
            unsupported_event_groups.append(group_name)

    # ------------------------------------------------------------------
    # Known gaps / blockers
    # ------------------------------------------------------------------
    known_gaps: list[str] = []
    known_blockers: list[str] = []

    if block_b_payload is None:
        known_blockers.append("block_b_integrated_evidence_report_missing")
    else:
        b_status = _safe_str(block_b_payload.get("status"))
        if b_status == INSUFFICIENT_EVIDENCE_STATUS:
            known_blockers.append("block_b_status_insufficient_evidence")
        elif b_status == PARTIAL_EVIDENCE_STATUS:
            known_gaps.append("block_b_status_partial_evidence")

    if replay_status == COMPONENT_STATUS_INSUFFICIENT_EVIDENCE:
        known_blockers.append("replay_layer_no_adaptive_events")
    elif replay_status == COMPONENT_STATUS_PARTIAL_EVIDENCE:
        known_gaps.append("replay_layer_no_replay_cases_built")

    if reflection_status == COMPONENT_STATUS_INSUFFICIENT_EVIDENCE:
        known_blockers.append("reflection_layer_no_adaptive_events")
    elif reflection_status == COMPONENT_STATUS_PARTIAL_EVIDENCE:
        known_gaps.append("reflection_layer_no_reflection_cases_built")

    if evidence_contract_status == COMPONENT_STATUS_INSUFFICIENT_EVIDENCE:
        known_blockers.append("evidence_contract_no_accepted_claims")
    elif evidence_contract_status == COMPONENT_STATUS_PARTIAL_EVIDENCE:
        if degraded_claim_count > 0:
            known_gaps.append("evidence_contract_degraded_claims_present")
        if rejected_claim_count > 0:
            known_gaps.append("evidence_contract_rejected_claims_present")
        if missing_evidence_count > 0:
            known_gaps.append("evidence_contract_missing_evidence_present")
        if invalid_evidence_count > 0:
            known_gaps.append("evidence_contract_invalid_evidence_present")

    if unsupported_event_groups:
        known_gaps.append("replay_event_group_coverage_partial")

    # De-duplicate while keeping first-seen order.
    def _dedup(seq: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in seq:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out

    known_gaps = _dedup(known_gaps)
    known_blockers = _dedup(known_blockers)

    has_any_input = bool(events) or block_b_payload is not None
    has_blockers = bool(known_blockers)

    block_c_status = _aggregate_block_c_status(
        replay_status=replay_status,
        reflection_status=reflection_status,
        evidence_contract_status=evidence_contract_status,
        has_any_input=has_any_input,
        has_blockers=has_blockers,
    )
    next_phase = _next_allowed_phase(block_c_status)

    # ------------------------------------------------------------------
    # Final payload
    # ------------------------------------------------------------------
    payload: dict[str, Any] = {
        "schema_version": BLOCK_C_INTEGRATED_CHECKPOINT_SCHEMA_VERSION,
        "source_phase": BLOCK_C_INTEGRATED_CHECKPOINT_SOURCE_PHASE,
        "source_module": SOURCE_MODULE,
        "reference_window": str(reference_window or "60d"),
        "generated_at_utc": _now_utc_iso(),
        "status": block_c_status,
        "next_allowed_phase": next_phase,
        "phase_12_forbidden": True,
        "auto_tuning_allowed": False,
        # Component statuses
        "replay_status": replay_status,
        "reflection_status": reflection_status,
        "evidence_contract_status": evidence_contract_status,
        # Counters
        "replay_case_count": replay_case_count,
        "reflection_case_count": reflection_case_count,
        "evidence_claim_count": total_claim_count,
        "accepted_claim_count": accepted_claim_count,
        "degraded_claim_count": degraded_claim_count,
        "rejected_claim_count": rejected_claim_count,
        "partial_claim_count": partial_claim_count,
        "missing_evidence_count": missing_evidence_count,
        "invalid_evidence_count": invalid_evidence_count,
        # Coverage surface
        "supported_event_groups": list(supported_event_groups),
        "unsupported_event_groups": list(unsupported_event_groups),
        "known_gaps": list(known_gaps),
        "known_blockers": list(known_blockers),
        # Diagnostics
        "replay_summary": replay_summary,
        "reflection_summary": reflection_summary,
        "evidence_contract_overall_status": evidence_payload.get(
            "overall_status"
        ),
        "evidence_contract_warnings": evidence_payload.get("warnings", []),
        "block_b_report_path": (
            str(block_b_path) if block_b_path is not None else None
        ),
        "block_b_status": (
            _safe_str(block_b_payload.get("status"))
            if block_b_payload is not None
            else None
        ),
        # Schema versions
        "schema_versions": {
            "evidence_contract": EVIDENCE_CONTRACT_BASELINE_SCHEMA_VERSION,
        },
        "source_phases": {
            "evidence_contract": EVIDENCE_CONTRACT_SOURCE_PHASE,
        },
    }

    # Defensive guard: refuse to emit a payload that contains a
    # forbidden trade-authority / runtime-tuning key.
    _assert_no_forbidden_keys(
        payload,
        context="block_c_integrated_checkpoint",
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
        status=block_c_status,
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
            "Phase 11C.1C-C-B-B-B-E-D - Block C Integrated Checkpoint v0. "
            "Paper / report / evidence only. Phase 12 remains FORBIDDEN."
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
        "--block-b-dir",
        type=Path,
        default=Path("data/reports/block_b_integrated_evidence"),
        help="Block B integrated evidence checkpoint directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/reports/block_c_integrated_checkpoint"),
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
            block_b_dir=args.block_b_dir,
            output_dir=args.output_dir,
            reference_window=args.reference_window,
        )
    except ValueError as exc:
        sys.stderr.write(
            "block_c_integrated_checkpoint: forbidden key in payload: "
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


# Re-export some names for use in tests.
__all__ = [
    "BLOCK_C_INTEGRATED_CHECKPOINT_SCHEMA_VERSION",
    "BLOCK_C_INTEGRATED_CHECKPOINT_SOURCE_PHASE",
    "COMPONENT_STATUS_EVIDENCE_GENERATED",
    "COMPONENT_STATUS_INSUFFICIENT_EVIDENCE",
    "COMPONENT_STATUS_PARTIAL_EVIDENCE",
    "EVIDENCE_GENERATED_STATUS",
    "INSUFFICIENT_EVIDENCE_STATUS",
    "NEXT_PHASE_AI_EVIDENCE_BUNDLE_PREP",
    "NEXT_PHASE_NEEDS_OPERATOR_EVIDENCE",
    "PARTIAL_EVIDENCE_STATUS",
    "ClaimStatus",
    "CheckpointResult",
    "main",
    "run_checkpoint",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
