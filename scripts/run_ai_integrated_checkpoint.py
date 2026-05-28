"""Phase AI-CHECKPOINT - AI Integrated Checkpoint v0.

Aggregates the simplified outputs of:

    * Phase AI-1   AI Evidence Bundle Builder
    * Phase AI-2   AI Claim Citation Contract
    * Phase AI-3   Reality Check Layer
    * Phase AI-4   DeepSeek Offline Sandbox / Fake Provider
    * Phase AI-5   Operator Briefing / Evidence Compression
    * Phase AI-6   AI Replay / Reflection Integration

into a single descriptive **AI integrated checkpoint report**.
The report is the input to the AI / Phase-AI-CHECKPOINT decision:
did the AI-1..AI-6 chain produce enough evidence to authorise the
next allowed paper-only step (the *Offline Rule Sandbox Replay v0*
preparation work)?

Boundary
--------

The runner is paper / report / evidence-only. It MUST NOT and
DOES NOT:

  - place an order or close a position;
  - read a private exchange API or sign a request;
  - call a live LLM, a live DeepSeek transport, or a live
    Telegram outbound transport;
  - alter runtime configuration (``symbol_limit`` /
    candidate-pool capacity / anomaly thresholds /
    Regime weights / strategy parameters);
  - automatically tune any parameter on the basis of any
    field it emits;
  - feed AI output back into Risk / Execution / Strategy /
    Config;
  - treat AI output as truth, training label, tail label or
    strategy-validation sample;
  - recommend a direction (long / short / entry / exit / stop
    / target / position size / leverage);
  - open Phase 12.

The runner reads only local files under the supplied
``--evidence-bundle`` / ``--sandbox-output`` /
``--operator-briefing-dir`` / ``--block-c-report`` paths and
writes only files under ``--output-dir``. Phase 12 remains
FORBIDDEN. The Risk Engine remains the single trade-decision
gate.

Inputs
------

  - ``--block-c-report``         data/reports/block_c_integrated_checkpoint/
                                 block_c_integrated_checkpoint_report.json
  - ``--evidence-bundle``        data/reports/ai/evidence_bundle/
                                 ai_evidence_bundle.json
  - ``--sandbox-output``         data/reports/ai/deepseek_sandbox/
                                 deepseek_sandbox_output.json
  - ``--operator-briefing-dir``  data/reports/ai/operator_briefing
  - ``--output-dir``             data/reports/ai/integrated_checkpoint
  - ``--reference-window``       60d (descriptive only)
  - ``--use-fake-provider``      true (descriptive; the runner
                                 NEVER opens the network)

If a key input is absent on disk the runner falls back to a
deterministic minimal fixture derived from the local Phase AI-1
forbidden-fields contract; the resulting payload is marked
``source=fallback_fixture`` and never carries fabricated market
conclusions.

Outputs
-------

  - ``<output-dir>/ai_integrated_checkpoint_report.json``
  - ``<output-dir>/ai_integrated_checkpoint_report.md``

Status taxonomy
---------------

  * ``INSUFFICIENT_EVIDENCE``  - the AI evidence bundle / DeepSeek
    sandbox output / operator briefing are all missing AND no
    fallback can be derived from local reports;
    ``next_allowed_phase = NEEDS_AI_OPERATOR_EVIDENCE``.
  * ``PARTIAL_EVIDENCE``       - the chain runs end-to-end but at
    least one stage uses ``source=fallback_fixture`` or the
    sandbox output carries degraded / unsupported / rejected
    claims; ``next_allowed_phase = Offline Rule Sandbox Replay
    preparation / AI operator evidence run``.
  * ``EVIDENCE_GENERATED``     - the AI-1..AI-6 chain runs end-to-
    end with operator-supplied artefacts and no blocker remains;
    ``next_allowed_phase = Offline Rule Sandbox Replay v0``.

The status taxonomy is intentionally **not** ``ACCEPTED``. The
checkpoint never grants live-trading approval, never grants
auto-tuning approval, never authorises the DeepSeek hot path,
never authorises Telegram live outbound, and never opens Phase
12. A successful AI integrated checkpoint only allows the
*Offline Rule Sandbox Replay v0* preparation work.
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
#   - app.ai.evidence_bundle (Phase AI-1; for the canonical
#     forbidden-fields list)
#   - app.reflection.ai_reflection (Phase AI-6 convenience
#     wrapper that runs replay + reflection in one shot)
#
# The runner MUST NOT import:
#   - app.risk        (forbidden)
#   - app.execution   (forbidden)
#   - app.exchanges   (forbidden)
#   - app.telegram    (forbidden)
#   - app.config      (forbidden by brief)
from app.ai.evidence_bundle import (  # noqa: E402
    FORBIDDEN_AI_OUTPUT_FIELDS,
)
from app.reflection.ai_reflection import (  # noqa: E402
    replay_and_reflect_artefacts,
)


# ---------------------------------------------------------------------------
# Identity / constants
# ---------------------------------------------------------------------------
SOURCE_MODULE: str = "scripts.run_ai_integrated_checkpoint"

AI_INTEGRATED_CHECKPOINT_SCHEMA_VERSION: str = (
    "phase_ai_checkpoint.ai_integrated_checkpoint.v1"
)
AI_INTEGRATED_CHECKPOINT_SOURCE_PHASE: str = (
    "phase_ai_checkpoint_ai_integrated_checkpoint_v0"
)


# Roll-up status taxonomy.
INSUFFICIENT_EVIDENCE_STATUS: str = "INSUFFICIENT_EVIDENCE"
PARTIAL_EVIDENCE_STATUS: str = "PARTIAL_EVIDENCE"
EVIDENCE_GENERATED_STATUS: str = "EVIDENCE_GENERATED"


# Per-component status vocabulary. None of these is a trade-
# approval label; they roll up into the AI checkpoint
# descriptive status only.
COMPONENT_STATUS_PRESENT: str = "PRESENT"
COMPONENT_STATUS_FALLBACK_FIXTURE: str = "FALLBACK_FIXTURE"
COMPONENT_STATUS_MISSING: str = "MISSING"


# Per-axis status (replay / reflection).
COMPONENT_STATUS_EVIDENCE_GENERATED: str = "EVIDENCE_GENERATED"
COMPONENT_STATUS_PARTIAL_EVIDENCE: str = "PARTIAL_EVIDENCE"
COMPONENT_STATUS_INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"


NEXT_PHASE_OFFLINE_RULE_SANDBOX_REPLAY: str = (
    "Offline Rule Sandbox Replay v0 preparation (paper / read-only)"
)
NEXT_PHASE_OFFLINE_RULE_SANDBOX_REPLAY_PREP: str = (
    "Offline Rule Sandbox Replay preparation / AI operator "
    "evidence run (paper / read-only)"
)
NEXT_PHASE_NEEDS_AI_OPERATOR_EVIDENCE: str = (
    "NEEDS_AI_OPERATOR_EVIDENCE"
)


# ---------------------------------------------------------------------------
# Forbidden-payload guard (defensive)
# ---------------------------------------------------------------------------
# AI-checkpoint-specific superset of the AI-1 contract's forbidden
# vocabulary. We re-list a few defensive aliases here so the
# runner's guard cannot drift away from the AI-1 module's guard if
# a downstream regression mutates the upstream set.
_FORBIDDEN_AI_CHECKPOINT_PAYLOAD_KEYS: frozenset[str] = frozenset(
    set(FORBIDDEN_AI_OUTPUT_FIELDS)
    | {
        # Defensive aliases that are not in the AI-1 contract but
        # the AI checkpoint brief explicitly forbids.
        "trading_approved",
        "live_ready",
        "live_trading_allowed",
        "phase_12_allowed",
    }
)


def _assert_no_forbidden_keys(payload: Any, *, context: str) -> None:
    """Raise :class:`ValueError` if any forbidden key appears at any
    nesting depth.
    """

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_str = str(key)
            if key_str in _FORBIDDEN_AI_CHECKPOINT_PAYLOAD_KEYS:
                raise ValueError(
                    f"ai_integrated_checkpoint produced a forbidden "
                    f"payload key {key_str!r} in {context!r}; this is a "
                    "hard violation of Phase AI-CHECKPOINT boundary."
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
    """In-memory result of one AI integrated checkpoint run.

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


def _read_json_object(path: Path | None) -> dict[str, Any] | None:
    """Read ``path`` and return its top-level JSON object, or
    ``None`` if the file is missing / empty / unreadable / not a
    JSON object.
    """

    if path is None:
        return None
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.strip():
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


# ---------------------------------------------------------------------------
# Fallback fixture builders
# ---------------------------------------------------------------------------
# The fallback fixtures are deliberately minimal: they exercise the
# AI-1..AI-6 chain end-to-end without fabricating real market
# conclusions. Every fixture carries ``source=fallback_fixture``
# and the project-wide safety invariants.
def _fallback_evidence_bundle() -> dict[str, Any]:
    return {
        "schema_version": "v0",
        "source_phase": "phase_ai_1",
        "source_module": "ai_evidence_bundle_builder",
        "source": "fallback_fixture",
        "bundle_id": "fallback_fixture_bundle",
        "created_at_utc": "1970-01-01T00:00:00Z",
        "task_type": "MARKET_INTELLIGENCE_SUMMARY",
        "build_status": "DEGRADED",
        "phase_context": {"phase": "phase_ai_checkpoint"},
        "reference_window": "60d",
        "market_facts": [],
        "system_behavior_facts": [],
        "outcome_facts": [],
        "replay_facts": [],
        "reflection_facts": [],
        "evidence_contract_facts": [],
        "degraded_facts": [],
        "evidence_refs": [],
        "source_reports": [],
        "forbidden_fields": sorted(FORBIDDEN_AI_OUTPUT_FIELDS),
        "lookahead_policy": {
            "frozen_evidence_only": True,
            "no_future_market_data": True,
            "no_training_from_ai_output": True,
            "no_runtime_feedback": True,
            "post_hoc_analysis_only_when_window_closed": True,
        },
        "consumer_contract": {
            "allowed": ["human_operator", "replay_annotation"],
            "forbidden": [
                "RiskEngine",
                "ExecutionFSM",
                "StrategyEngine",
                "ExchangeGateway",
                "RuntimeConfig",
                "TelegramLiveCommand",
            ],
        },
        "warnings": ["fallback_fixture_used"],
        "accepted_fact_count": 0,
        "degraded_fact_count": 0,
        "ai_output_is_commentary_only": True,
        "ai_output_can_be_training_label": False,
        "phase_12_forbidden": True,
        "auto_tuning_allowed": False,
        "safety_flags": _safety_flags_dict(),
    }


def _fallback_sandbox_output(bundle_id: str) -> dict[str, Any]:
    return {
        "schema_version": "v0",
        "source_phase": "phase_ai_4",
        "source_module": "ai_intelligence_output",
        "source": "fallback_fixture",
        "bundle_id": bundle_id,
        "task_type": "MARKET_INTELLIGENCE_SUMMARY",
        "summary": (
            "fallback fixture: no operator-supplied DeepSeek "
            "offline sandbox output was found on disk."
        ),
        "claims": [],
        "contradictions": [],
        "unsupported_claims": [],
        "risk_tags": [],
        "evidence_refs": [],
        "reality_check_status": "INSUFFICIENT",
        "authority_level": "COMMENTARY_SUBSTRATE",
        "status": "DEGRADED",
        "forbidden_fields_stripped": [],
        "redacted_secret_count": 0,
        "warnings": ["fallback_fixture_used"],
        "degraded_reasons": ["fallback_fixture_used"],
        "stateless_inference": True,
        "feedback_isolation": True,
        "trade_authority": False,
        "auto_tuning_allowed": False,
        "phase_12_forbidden": True,
        "ai_output_is_commentary_only": True,
        "ai_output_can_be_training_label": False,
        "safety_flags": _safety_flags_dict(),
        "forbidden_fields": sorted(FORBIDDEN_AI_OUTPUT_FIELDS),
    }


def _fallback_operator_briefing(
    bundle_id: str, ai_output_id: str
) -> dict[str, Any]:
    return {
        "schema_version": "v0",
        "source_phase": "phase_ai_5",
        "source_module": "ai_operator_briefing",
        "source": "fallback_fixture",
        "briefing_id": "fallback_fixture_briefing",
        "created_at_utc": "1970-01-01T00:00:00Z",
        "reference_window": "60d",
        "source_bundle_id": bundle_id,
        "source_ai_output_id": ai_output_id,
        "source_block_c_status": "UNKNOWN",
        "source_report_paths": [],
        "sections": [],
        "key_findings": [],
        "unsupported_claims": [],
        "contradictions": [],
        "data_gaps": ["fallback_fixture_used"],
        "operator_review_items": [],
        "evidence_refs": [],
        "notable_symbols": [],
        "risk_tags": ["fallback_fixture"],
        "authority_level": "COMMENTARY_SUBSTRATE",
        "forbidden_fields_stripped": [],
        "redacted_secret_count": 0,
        "warnings": ["fallback_fixture_used"],
        "consumer_contract": {"allowed": ["human_operator"]},
        "trade_authority": False,
        "auto_tuning_allowed": False,
        "phase_12_forbidden": True,
        "stateless_inference": True,
        "feedback_isolation": True,
        "ai_output_is_commentary_only": True,
        "ai_output_can_be_training_label": False,
        "safety_flags": _safety_flags_dict(),
        "forbidden_fields": sorted(FORBIDDEN_AI_OUTPUT_FIELDS),
    }


def _fallback_evidence_compression(
    bundle_id: str, ai_output_id: str
) -> dict[str, Any]:
    return {
        "schema_version": "v0",
        "source_phase": "phase_ai_5",
        "source_module": "ai_evidence_compression_report",
        "source": "fallback_fixture",
        "report_id": "fallback_fixture_compression",
        "created_at_utc": "1970-01-01T00:00:00Z",
        "reference_window": "60d",
        "source_bundle_id": bundle_id,
        "source_ai_output_id": ai_output_id,
        "summary": (
            "fallback fixture: no operator-supplied evidence "
            "compression report was found on disk."
        ),
        "compressed_claims": [],
        "supported_claims": [],
        "degraded_claims": [],
        "rejected_claims": [],
        "contradictions": [],
        "unsupported_claims": [],
        "reality_check_summary": {},
        "evidence_quality_summary": {},
        "data_gap_summary": {},
        "notable_symbols": [],
        "risk_tags": ["fallback_fixture"],
        "evidence_refs": [],
        "forbidden_fields_stripped": [],
        "redacted_secret_count": 0,
        "warnings": ["fallback_fixture_used"],
        "trade_authority": False,
        "auto_tuning_allowed": False,
        "phase_12_forbidden": True,
        "stateless_inference": True,
        "feedback_isolation": True,
        "ai_output_is_commentary_only": True,
        "ai_output_can_be_training_label": False,
        "safety_flags": _safety_flags_dict(),
        "forbidden_fields": sorted(FORBIDDEN_AI_OUTPUT_FIELDS),
    }


def _safety_flags_dict() -> dict[str, Any]:
    return {
        "mode": "paper",
        "live_trading": False,
        "exchange_live_orders": False,
        "right_tail": False,
        "llm": False,
        "llm_outbound_enabled": False,
        "sandbox_only": True,
        "telegram_outbound_enabled": False,
        "binance_private_api_enabled": False,
    }


# ---------------------------------------------------------------------------
# Per-stage status derivation
# ---------------------------------------------------------------------------
def _stage_status(
    *, payload: Mapping[str, Any] | None, source: str
) -> str:
    """Map a per-stage payload + source label to a status string."""

    if payload is None or source == COMPONENT_STATUS_MISSING:
        return COMPONENT_STATUS_MISSING
    if source == COMPONENT_STATUS_FALLBACK_FIXTURE:
        return COMPONENT_STATUS_FALLBACK_FIXTURE
    return COMPONENT_STATUS_PRESENT


def _citation_contract_status(
    sandbox_output: Mapping[str, Any] | None,
    *,
    sandbox_source: str,
) -> str:
    """Derive the AI-2 citation contract status from the AI-4
    sandbox output's ``claims[].citation_authority_level``.
    """

    if sandbox_output is None or sandbox_source == COMPONENT_STATUS_MISSING:
        return COMPONENT_STATUS_MISSING
    if sandbox_source == COMPONENT_STATUS_FALLBACK_FIXTURE:
        return COMPONENT_STATUS_FALLBACK_FIXTURE
    claims = sandbox_output.get("claims") or []
    if not isinstance(claims, list) or not claims:
        return COMPONENT_STATUS_FALLBACK_FIXTURE
    return COMPONENT_STATUS_PRESENT


def _reality_check_status(
    sandbox_output: Mapping[str, Any] | None,
    *,
    sandbox_source: str,
) -> str:
    """Derive the AI-3 reality-check status from the AI-4 sandbox
    output's ``reality_check_status`` (and per-claim
    ``reality_check_status``).
    """

    if sandbox_output is None or sandbox_source == COMPONENT_STATUS_MISSING:
        return COMPONENT_STATUS_MISSING
    if sandbox_source == COMPONENT_STATUS_FALLBACK_FIXTURE:
        return COMPONENT_STATUS_FALLBACK_FIXTURE
    return COMPONENT_STATUS_PRESENT


def _replay_reflection_axis_status(case_count: int) -> str:
    if case_count <= 0:
        return COMPONENT_STATUS_INSUFFICIENT_EVIDENCE
    return COMPONENT_STATUS_EVIDENCE_GENERATED


# ---------------------------------------------------------------------------
# Claim count derivation from AI-4 sandbox output
# ---------------------------------------------------------------------------
_SUPPORTED_CITATION_LEVELS: frozenset[str] = frozenset(
    {"SUPPORTED_INTELLIGENCE"}
)
_DEGRADED_CITATION_LEVELS: frozenset[str] = frozenset(
    {"DEGRADED_NO_EVIDENCE", "UNSUPPORTED_INTELLIGENCE"}
)
_REJECTED_CITATION_LEVELS: frozenset[str] = frozenset(
    {"REJECTED_BY_SCHEMA", "REJECTED_INVALID_EVIDENCE"}
)
_REALITY_CHECK_FAILED_STATUSES: frozenset[str] = frozenset(
    {"CONTRADICTED", "INSUFFICIENT", "REJECTED"}
)


def _derive_claim_counts(
    sandbox_output: Mapping[str, Any] | None,
) -> dict[str, int]:
    """Walk ``sandbox_output['claims']`` and return the headline
    AI-2 / AI-3 counters the integrated checkpoint surfaces.

    Returns a dict with the keys
    ``ai_claim_count`` / ``supported_claim_count`` /
    ``degraded_claim_count`` / ``rejected_claim_count`` /
    ``reality_check_failed_count`` /
    ``unsupported_claim_count`` /
    ``forbidden_field_stripped_count``.
    """

    counts: dict[str, int] = {
        "ai_claim_count": 0,
        "supported_claim_count": 0,
        "degraded_claim_count": 0,
        "rejected_claim_count": 0,
        "reality_check_failed_count": 0,
        "unsupported_claim_count": 0,
        "forbidden_field_stripped_count": 0,
    }
    if sandbox_output is None:
        return counts

    forbidden_stripped = sandbox_output.get("forbidden_fields_stripped")
    if isinstance(forbidden_stripped, list):
        counts["forbidden_field_stripped_count"] = len(forbidden_stripped)

    raw_claims = sandbox_output.get("claims")
    if not isinstance(raw_claims, list):
        return counts
    counts["ai_claim_count"] = len(raw_claims)

    for claim in raw_claims:
        if not isinstance(claim, Mapping):
            continue
        citation = _safe_str(claim.get("citation_authority_level")) or ""
        rc = _safe_str(claim.get("reality_check_status")) or ""
        if citation in _SUPPORTED_CITATION_LEVELS:
            counts["supported_claim_count"] += 1
        elif citation in _DEGRADED_CITATION_LEVELS:
            counts["degraded_claim_count"] += 1
            if citation == "UNSUPPORTED_INTELLIGENCE":
                counts["unsupported_claim_count"] += 1
        elif citation in _REJECTED_CITATION_LEVELS:
            counts["rejected_claim_count"] += 1
        if rc.upper() in _REALITY_CHECK_FAILED_STATUSES:
            counts["reality_check_failed_count"] += 1

    # Top-level ``unsupported_claims`` list is authoritative if
    # present (it dedupes across multiple citation paths).
    top_unsupported = sandbox_output.get("unsupported_claims")
    if isinstance(top_unsupported, list) and top_unsupported:
        counts["unsupported_claim_count"] = max(
            counts["unsupported_claim_count"], len(top_unsupported)
        )

    return counts


# ---------------------------------------------------------------------------
# Operator-briefing-dir loader
# ---------------------------------------------------------------------------
def _resolve_operator_briefing_paths(
    operator_briefing_dir: Path | None,
) -> tuple[Path | None, Path | None]:
    """Return ``(briefing_path, compression_path)`` under the
    operator briefing directory, or ``(None, None)`` when the
    directory does not exist.
    """

    if operator_briefing_dir is None:
        return None, None
    if not operator_briefing_dir.is_dir():
        return None, None
    briefing = operator_briefing_dir / "operator_briefing.json"
    compression = operator_briefing_dir / "evidence_compression_report.json"
    return (
        briefing if briefing.is_file() else None,
        compression if compression.is_file() else None,
    )


# ---------------------------------------------------------------------------
# Aggregate status roll-up
# ---------------------------------------------------------------------------
def _aggregate_overall_status(
    *,
    has_any_input: bool,
    any_fallback_used: bool,
    has_blockers: bool,
    sandbox_present: bool,
    degraded_claim_count: int,
    rejected_claim_count: int,
    reality_check_failed_count: int,
    replay_axis: str,
    reflection_axis: str,
) -> str:
    """Roll up the per-component statuses into the AI checkpoint
    integrated status.

    Rule:
      - If there is no usable input (all stages MISSING) ->
        INSUFFICIENT_EVIDENCE.
      - If there is a blocker -> PARTIAL_EVIDENCE (but never
        INSUFFICIENT_EVIDENCE just because the operator-supplied
        artefacts are partial; INSUFFICIENT means *nothing* on
        disk).
      - If any stage used a fallback fixture, or the sandbox
        output carries degraded / rejected / reality-check-failed
        claims, or the replay/reflection axis is anything below
        EVIDENCE_GENERATED -> PARTIAL_EVIDENCE.
      - Otherwise -> EVIDENCE_GENERATED.
    """

    if not has_any_input:
        return INSUFFICIENT_EVIDENCE_STATUS
    if has_blockers:
        return PARTIAL_EVIDENCE_STATUS
    if any_fallback_used:
        return PARTIAL_EVIDENCE_STATUS
    if not sandbox_present:
        return PARTIAL_EVIDENCE_STATUS
    if (
        degraded_claim_count > 0
        or rejected_claim_count > 0
        or reality_check_failed_count > 0
    ):
        return PARTIAL_EVIDENCE_STATUS
    if (
        replay_axis != COMPONENT_STATUS_EVIDENCE_GENERATED
        or reflection_axis != COMPONENT_STATUS_EVIDENCE_GENERATED
    ):
        return PARTIAL_EVIDENCE_STATUS
    return EVIDENCE_GENERATED_STATUS


def _next_allowed_phase(status: str) -> str:
    if status == EVIDENCE_GENERATED_STATUS:
        return NEXT_PHASE_OFFLINE_RULE_SANDBOX_REPLAY
    if status == PARTIAL_EVIDENCE_STATUS:
        return NEXT_PHASE_OFFLINE_RULE_SANDBOX_REPLAY_PREP
    return NEXT_PHASE_NEEDS_AI_OPERATOR_EVIDENCE


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------
def _format_markdown_summary(payload: Mapping[str, Any]) -> str:
    lines: list[str] = []
    lines.append(
        "# Phase AI-CHECKPOINT - AI Integrated Checkpoint v0"
    )
    lines.append("")
    lines.append(
        "Paper / report / evidence only. Phase 12 remains FORBIDDEN."
    )
    lines.append("")
    lines.append(f"- status: {payload.get('status')}")
    lines.append(f"- reference_window: {payload.get('reference_window')}")
    lines.append(f"- generated_at_utc: {payload.get('generated_at_utc')}")
    lines.append(
        f"- next_allowed_phase: {payload.get('next_allowed_phase')}"
    )
    lines.append(
        f"- phase_12_forbidden: {payload.get('phase_12_forbidden')}"
    )
    lines.append(
        f"- auto_tuning_allowed: {payload.get('auto_tuning_allowed')}"
    )
    lines.append(
        f"- trade_authority: {payload.get('trade_authority')}"
    )
    lines.append("")
    lines.append("## Per-stage statuses")
    lines.append(
        f"- evidence_bundle_status: "
        f"{payload.get('evidence_bundle_status')}"
    )
    lines.append(
        f"- citation_contract_status: "
        f"{payload.get('citation_contract_status')}"
    )
    lines.append(
        f"- reality_check_status: "
        f"{payload.get('reality_check_status')}"
    )
    lines.append(
        f"- deepseek_sandbox_status: "
        f"{payload.get('deepseek_sandbox_status')}"
    )
    lines.append(
        f"- operator_briefing_status: "
        f"{payload.get('operator_briefing_status')}"
    )
    lines.append(
        f"- evidence_compression_status: "
        f"{payload.get('evidence_compression_status')}"
    )
    lines.append(
        f"- ai_replay_status: {payload.get('ai_replay_status')}"
    )
    lines.append(
        f"- ai_reflection_status: "
        f"{payload.get('ai_reflection_status')}"
    )
    lines.append("")
    lines.append("## Counters")
    lines.append(f"- bundle_count: {payload.get('bundle_count')}")
    lines.append(f"- ai_claim_count: {payload.get('ai_claim_count')}")
    lines.append(
        f"- supported_claim_count: "
        f"{payload.get('supported_claim_count')}"
    )
    lines.append(
        f"- degraded_claim_count: "
        f"{payload.get('degraded_claim_count')}"
    )
    lines.append(
        f"- rejected_claim_count: "
        f"{payload.get('rejected_claim_count')}"
    )
    lines.append(
        f"- reality_check_failed_count: "
        f"{payload.get('reality_check_failed_count')}"
    )
    lines.append(
        f"- unsupported_claim_count: "
        f"{payload.get('unsupported_claim_count')}"
    )
    lines.append(
        f"- forbidden_field_stripped_count: "
        f"{payload.get('forbidden_field_stripped_count')}"
    )
    lines.append(
        f"- replay_case_count: {payload.get('replay_case_count')}"
    )
    lines.append(
        f"- reflection_case_count: "
        f"{payload.get('reflection_case_count')}"
    )
    lines.append("")
    lines.append("## AI-output authority pins")
    lines.append(
        f"- ai_output_can_be_truth: "
        f"{payload.get('ai_output_can_be_truth')}"
    )
    lines.append(
        f"- ai_output_can_be_training_label: "
        f"{payload.get('ai_output_can_be_training_label')}"
    )
    lines.append(
        f"- ai_output_can_be_tail_label: "
        f"{payload.get('ai_output_can_be_tail_label')}"
    )
    lines.append(
        f"- ai_output_can_be_strategy_sample: "
        f"{payload.get('ai_output_can_be_strategy_sample')}"
    )
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
    lines.append(
        "- This checkpoint does NOT authorise live trading."
    )
    lines.append(
        "- This checkpoint does NOT authorise auto-tuning."
    )
    lines.append(
        "- This checkpoint does NOT authorise the DeepSeek hot path."
    )
    lines.append(
        "- This checkpoint does NOT authorise Telegram live "
        "outbound."
    )
    lines.append(
        "- AI output is commentary substrate, not truth, not a "
        "training label, not a tail label, not a strategy "
        "validation sample."
    )
    lines.append(
        "- A successful AI integrated checkpoint only allows "
        "the Offline Rule Sandbox Replay v0 preparation work; "
        "it does NOT open Phase 12."
    )
    lines.append("- Phase 12 remains FORBIDDEN.")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def run_checkpoint(
    *,
    block_c_report: Path | None,
    evidence_bundle: Path | None,
    sandbox_output: Path | None,
    operator_briefing_dir: Path | None,
    output_dir: Path,
    reference_window: str,
    use_fake_provider: bool = True,
) -> CheckpointResult:
    """Run the AI integrated checkpoint once.

    The runner is read-only / write-only; it never connects to the
    network. ``use_fake_provider`` is descriptive only - the runner
    re-pins the safety invariants regardless of the flag value.
    """

    output_dir = Path(output_dir)
    output_report_path = output_dir / "ai_integrated_checkpoint_report.json"
    output_summary_path = output_dir / "ai_integrated_checkpoint_report.md"

    # ------------------------------------------------------------------
    # Block C report (optional, descriptive only).
    # ------------------------------------------------------------------
    block_c_payload = _read_json_object(block_c_report)
    block_c_status = (
        _safe_str(block_c_payload.get("status"))
        if block_c_payload is not None
        else None
    )

    # ------------------------------------------------------------------
    # AI-1 Evidence Bundle
    # ------------------------------------------------------------------
    bundle_payload = _read_json_object(evidence_bundle)
    if bundle_payload is None:
        bundle_source = COMPONENT_STATUS_MISSING
    else:
        bundle_source = COMPONENT_STATUS_PRESENT
    if bundle_payload is None:
        bundle_payload = _fallback_evidence_bundle()
        bundle_source = COMPONENT_STATUS_FALLBACK_FIXTURE

    bundle_id = _safe_str(bundle_payload.get("bundle_id")) or (
        "fallback_fixture_bundle"
    )

    # ------------------------------------------------------------------
    # AI-4 DeepSeek Offline Sandbox output
    # ------------------------------------------------------------------
    sandbox_payload = _read_json_object(sandbox_output)
    if sandbox_payload is None:
        sandbox_src = COMPONENT_STATUS_MISSING
    else:
        sandbox_src = COMPONENT_STATUS_PRESENT
    if sandbox_payload is None:
        sandbox_payload = _fallback_sandbox_output(bundle_id=bundle_id)
        sandbox_src = COMPONENT_STATUS_FALLBACK_FIXTURE

    ai_output_id = (
        _safe_str(sandbox_payload.get("output_id"))
        or _safe_str(sandbox_payload.get("id"))
        or f"intel:{bundle_id}"
    )

    # ------------------------------------------------------------------
    # AI-5 Operator Briefing + Evidence Compression
    # ------------------------------------------------------------------
    briefing_path, compression_path = _resolve_operator_briefing_paths(
        operator_briefing_dir
    )
    briefing_payload = _read_json_object(briefing_path)
    if briefing_payload is None:
        briefing_src = COMPONENT_STATUS_MISSING
    else:
        briefing_src = COMPONENT_STATUS_PRESENT
    if briefing_payload is None:
        briefing_payload = _fallback_operator_briefing(
            bundle_id=bundle_id, ai_output_id=ai_output_id
        )
        briefing_src = COMPONENT_STATUS_FALLBACK_FIXTURE

    compression_payload = _read_json_object(compression_path)
    if compression_payload is None:
        compression_src = COMPONENT_STATUS_MISSING
    else:
        compression_src = COMPONENT_STATUS_PRESENT
    if compression_payload is None:
        compression_payload = _fallback_evidence_compression(
            bundle_id=bundle_id, ai_output_id=ai_output_id
        )
        compression_src = COMPONENT_STATUS_FALLBACK_FIXTURE

    # ------------------------------------------------------------------
    # AI-6 Replay + Reflection over the AI-5 artefacts.
    #
    # Phase AI-6 builds replay cases from
    # OperatorBriefing-shaped and EvidenceCompressionReport-shaped
    # JSON dicts; the engine is pure and offline. It accepts
    # AIEvidenceBundle and AIIntelligenceOutput shapes too, so we
    # feed all four artefacts to maximise coverage.
    # ------------------------------------------------------------------
    artefacts: list[Mapping[str, Any]] = [
        bundle_payload,
        sandbox_payload,
        briefing_payload,
        compression_payload,
    ]
    replay_summary, reflection_summary = replay_and_reflect_artefacts(
        artefacts
    )
    replay_case_count = int(replay_summary.total_cases)
    reflection_case_count = int(reflection_summary.total_cases)

    # ------------------------------------------------------------------
    # Counts derived from the AI-4 sandbox output (AI-2/AI-3 axes).
    # ------------------------------------------------------------------
    claim_counts = _derive_claim_counts(sandbox_payload)
    # The replay summary is the canonical source for the
    # forbidden-field-stripped count over all four artefacts.
    forbidden_stripped_total = max(
        int(claim_counts["forbidden_field_stripped_count"]),
        int(replay_summary.forbidden_field_stripped_count),
    )

    # ------------------------------------------------------------------
    # Per-stage statuses.
    # ------------------------------------------------------------------
    evidence_bundle_status = _stage_status(
        payload=bundle_payload, source=bundle_source
    )
    deepseek_sandbox_status = _stage_status(
        payload=sandbox_payload, source=sandbox_src
    )
    operator_briefing_status = _stage_status(
        payload=briefing_payload, source=briefing_src
    )
    evidence_compression_status = _stage_status(
        payload=compression_payload, source=compression_src
    )
    citation_contract_status = _citation_contract_status(
        sandbox_payload, sandbox_source=sandbox_src
    )
    reality_check_status = _reality_check_status(
        sandbox_payload, sandbox_source=sandbox_src
    )
    ai_replay_status = _replay_reflection_axis_status(replay_case_count)
    ai_reflection_status = _replay_reflection_axis_status(
        reflection_case_count
    )

    # ------------------------------------------------------------------
    # Known gaps / blockers.
    # ------------------------------------------------------------------
    known_gaps: list[str] = []
    known_blockers: list[str] = []

    # Per-stage gaps.
    if evidence_bundle_status == COMPONENT_STATUS_MISSING:
        known_blockers.append("evidence_bundle_missing")
    elif evidence_bundle_status == COMPONENT_STATUS_FALLBACK_FIXTURE:
        known_gaps.append("evidence_bundle_fallback_fixture_used")

    if deepseek_sandbox_status == COMPONENT_STATUS_MISSING:
        known_blockers.append("deepseek_sandbox_output_missing")
    elif deepseek_sandbox_status == COMPONENT_STATUS_FALLBACK_FIXTURE:
        known_gaps.append("deepseek_sandbox_fallback_fixture_used")

    if operator_briefing_status == COMPONENT_STATUS_MISSING:
        known_blockers.append("operator_briefing_missing")
    elif operator_briefing_status == COMPONENT_STATUS_FALLBACK_FIXTURE:
        known_gaps.append("operator_briefing_fallback_fixture_used")

    if evidence_compression_status == COMPONENT_STATUS_MISSING:
        known_blockers.append("evidence_compression_report_missing")
    elif evidence_compression_status == COMPONENT_STATUS_FALLBACK_FIXTURE:
        known_gaps.append("evidence_compression_fallback_fixture_used")

    # AI-2 / AI-3 axes: degraded / rejected / reality-check-failed
    # claims become known gaps (they do not block PARTIAL_EVIDENCE
    # but keep EVIDENCE_GENERATED unreachable).
    if claim_counts["degraded_claim_count"] > 0:
        known_gaps.append("ai_claims_degraded_present")
    if claim_counts["rejected_claim_count"] > 0:
        known_gaps.append("ai_claims_rejected_present")
    if claim_counts["reality_check_failed_count"] > 0:
        known_gaps.append("ai_claims_reality_check_failed_present")
    if claim_counts["unsupported_claim_count"] > 0:
        known_gaps.append("ai_claims_unsupported_present")
    if forbidden_stripped_total > 0:
        known_gaps.append("ai_forbidden_fields_stripped_present")

    # AI-6 axes.
    if ai_replay_status == COMPONENT_STATUS_INSUFFICIENT_EVIDENCE:
        known_gaps.append("ai_replay_no_cases_built")
    if ai_reflection_status == COMPONENT_STATUS_INSUFFICIENT_EVIDENCE:
        known_gaps.append("ai_reflection_no_cases_built")

    # Block C report is descriptive only; surface its absence as
    # a gap (never a blocker).
    if block_c_payload is None:
        known_gaps.append("block_c_integrated_checkpoint_report_missing")
    elif block_c_status == INSUFFICIENT_EVIDENCE_STATUS:
        known_gaps.append("block_c_status_insufficient_evidence")

    def _dedup(seq: Iterable[str]) -> list[str]:
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

    # ------------------------------------------------------------------
    # Aggregate roll-up.
    # ------------------------------------------------------------------
    has_any_input = any(
        s == COMPONENT_STATUS_PRESENT
        for s in (
            evidence_bundle_status,
            deepseek_sandbox_status,
            operator_briefing_status,
            evidence_compression_status,
        )
    ) or block_c_payload is not None
    any_fallback_used = any(
        s == COMPONENT_STATUS_FALLBACK_FIXTURE
        for s in (
            evidence_bundle_status,
            deepseek_sandbox_status,
            operator_briefing_status,
            evidence_compression_status,
        )
    )
    has_blockers = bool(known_blockers)

    overall_status = _aggregate_overall_status(
        has_any_input=has_any_input,
        any_fallback_used=any_fallback_used,
        has_blockers=has_blockers,
        sandbox_present=(
            deepseek_sandbox_status == COMPONENT_STATUS_PRESENT
        ),
        degraded_claim_count=int(claim_counts["degraded_claim_count"]),
        rejected_claim_count=int(claim_counts["rejected_claim_count"]),
        reality_check_failed_count=int(
            claim_counts["reality_check_failed_count"]
        ),
        replay_axis=ai_replay_status,
        reflection_axis=ai_reflection_status,
    )
    next_phase = _next_allowed_phase(overall_status)

    # ------------------------------------------------------------------
    # Final payload
    # ------------------------------------------------------------------
    payload: dict[str, Any] = {
        "schema_version": AI_INTEGRATED_CHECKPOINT_SCHEMA_VERSION,
        "source_phase": AI_INTEGRATED_CHECKPOINT_SOURCE_PHASE,
        "source_module": SOURCE_MODULE,
        "reference_window": str(reference_window or "60d"),
        "generated_at_utc": _now_utc_iso(),
        "status": overall_status,
        "next_allowed_phase": next_phase,
        # Per-stage statuses (AI-1..AI-6 axes).
        "evidence_bundle_status": evidence_bundle_status,
        "citation_contract_status": citation_contract_status,
        "reality_check_status": reality_check_status,
        "deepseek_sandbox_status": deepseek_sandbox_status,
        "operator_briefing_status": operator_briefing_status,
        "evidence_compression_status": evidence_compression_status,
        "ai_replay_status": ai_replay_status,
        "ai_reflection_status": ai_reflection_status,
        # Counters.
        "bundle_count": (
            1
            if evidence_bundle_status == COMPONENT_STATUS_PRESENT
            else 0
        ),
        "ai_claim_count": int(claim_counts["ai_claim_count"]),
        "supported_claim_count": int(claim_counts["supported_claim_count"]),
        "degraded_claim_count": int(claim_counts["degraded_claim_count"]),
        "rejected_claim_count": int(claim_counts["rejected_claim_count"]),
        "reality_check_failed_count": int(
            claim_counts["reality_check_failed_count"]
        ),
        "unsupported_claim_count": int(
            claim_counts["unsupported_claim_count"]
        ),
        "forbidden_field_stripped_count": int(forbidden_stripped_total),
        "replay_case_count": int(replay_case_count),
        "reflection_case_count": int(reflection_case_count),
        # AI-output authority pins (Phase AI-CHECKPOINT contract).
        "ai_output_can_be_truth": False,
        "ai_output_can_be_training_label": False,
        "ai_output_can_be_tail_label": False,
        "ai_output_can_be_strategy_sample": False,
        "ai_output_is_commentary_only": True,
        # Project-wide invariants.
        "trade_authority": False,
        "auto_tuning_allowed": False,
        "phase_12_forbidden": True,
        "stateless_inference": True,
        "feedback_isolation": True,
        # Coverage surface.
        "known_gaps": list(known_gaps),
        "known_blockers": list(known_blockers),
        # Inputs.
        "inputs": {
            "block_c_report_path": (
                str(block_c_report) if block_c_report is not None else None
            ),
            "block_c_status": block_c_status,
            "evidence_bundle_path": (
                str(evidence_bundle)
                if evidence_bundle is not None
                else None
            ),
            "evidence_bundle_source": bundle_source,
            "sandbox_output_path": (
                str(sandbox_output) if sandbox_output is not None else None
            ),
            "sandbox_output_source": sandbox_src,
            "operator_briefing_dir": (
                str(operator_briefing_dir)
                if operator_briefing_dir is not None
                else None
            ),
            "operator_briefing_source": briefing_src,
            "evidence_compression_source": compression_src,
            "use_fake_provider": bool(use_fake_provider),
        },
        # Diagnostics: only the small headline summary fields, not
        # the full per-case lists (those live in the AI-6 outputs
        # themselves and are not the responsibility of this
        # roll-up).
        "replay_summary": {
            "total_cases": int(replay_summary.total_cases),
            "evidence_bundle_count": int(
                replay_summary.evidence_bundle_count
            ),
            "ai_intelligence_output_count": int(
                replay_summary.ai_intelligence_output_count
            ),
            "operator_briefing_count": int(
                replay_summary.operator_briefing_count
            ),
            "evidence_compression_count": int(
                replay_summary.evidence_compression_count
            ),
            "supported_claim_count": int(
                replay_summary.supported_claim_count
            ),
            "unsupported_claim_count": int(
                replay_summary.unsupported_claim_count
            ),
            "contradicted_claim_count": int(
                replay_summary.contradicted_claim_count
            ),
            "reality_check_failed_count": int(
                replay_summary.reality_check_failed_count
            ),
            "missing_evidence_count": int(
                replay_summary.missing_evidence_count
            ),
            "forbidden_field_stripped_count": int(
                replay_summary.forbidden_field_stripped_count
            ),
            "degraded_run_count": int(replay_summary.degraded_run_count),
            "redacted_secret_count": int(
                replay_summary.redacted_secret_count
            ),
        },
        "reflection_summary": {
            "total_cases": int(reflection_summary.total_cases),
            "tag_counts": dict(
                sorted(reflection_summary.tag_counts.items())
            ),
            "severity_counts": dict(
                sorted(reflection_summary.severity_counts.items())
            ),
            "needs_operator_review_count": int(
                reflection_summary.needs_operator_review_count
            ),
        },
        # Project-wide safety-flag invariants.
        "safety_flags": _safety_flags_dict(),
        # Forbidden-field reference list so a downstream consumer
        # can audit the schema without parsing the source.
        "forbidden_fields": sorted(FORBIDDEN_AI_OUTPUT_FIELDS),
    }

    # Defensive guard: refuse to emit a payload that contains a
    # forbidden trade-authority / runtime-tuning key.
    _assert_no_forbidden_keys(
        payload, context="ai_integrated_checkpoint"
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
        status=overall_status,
        next_allowed_phase=next_phase,
        output_report_path=output_report_path,
        output_summary_path=output_summary_path,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _parse_bool(value: str) -> bool:
    """argparse helper: accept ``true/false/yes/no/1/0`` (case-
    insensitive)."""

    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1", "on"}:
        return True
    if text in {"false", "no", "n", "0", "off"}:
        return False
    raise argparse.ArgumentTypeError(
        f"could not parse {value!r} as boolean"
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_ai_integrated_checkpoint",
        description=(
            "Phase AI-CHECKPOINT - AI Integrated Checkpoint v0. "
            "Paper / report / evidence only. Phase 12 remains "
            "FORBIDDEN."
        ),
    )
    parser.add_argument(
        "--block-c-report",
        type=Path,
        default=Path(
            "data/reports/block_c_integrated_checkpoint/"
            "block_c_integrated_checkpoint_report.json"
        ),
        help=(
            "Path to the Block C Integrated Checkpoint report "
            "JSON file (descriptive only)."
        ),
    )
    parser.add_argument(
        "--evidence-bundle",
        type=Path,
        default=Path(
            "data/reports/ai/evidence_bundle/ai_evidence_bundle.json"
        ),
        help=(
            "Path to a serialised Phase AI-1 AIEvidenceBundle "
            "JSON file."
        ),
    )
    parser.add_argument(
        "--sandbox-output",
        type=Path,
        default=Path(
            "data/reports/ai/deepseek_sandbox/"
            "deepseek_sandbox_output.json"
        ),
        help=(
            "Path to a serialised Phase AI-4 "
            "AIIntelligenceOutput JSON file."
        ),
    )
    parser.add_argument(
        "--operator-briefing-dir",
        type=Path,
        default=Path("data/reports/ai/operator_briefing"),
        help=(
            "Directory containing operator_briefing.json and "
            "evidence_compression_report.json (Phase AI-5)."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/reports/ai/integrated_checkpoint"),
        help=(
            "Where the AI integrated checkpoint report + "
            "markdown are written."
        ),
    )
    parser.add_argument(
        "--reference-window",
        type=str,
        default="60d",
        help="Audit-window label (descriptive only).",
    )
    parser.add_argument(
        "--use-fake-provider",
        type=_parse_bool,
        default=True,
        help=(
            "Descriptive flag. The runner NEVER opens a network "
            "socket regardless of the value."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = run_checkpoint(
            block_c_report=args.block_c_report,
            evidence_bundle=args.evidence_bundle,
            sandbox_output=args.sandbox_output,
            operator_briefing_dir=args.operator_briefing_dir,
            output_dir=args.output_dir,
            reference_window=args.reference_window,
            use_fake_provider=bool(args.use_fake_provider),
        )
    except ValueError as exc:
        sys.stderr.write(
            "ai_integrated_checkpoint: forbidden key in payload: "
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
    "AI_INTEGRATED_CHECKPOINT_SCHEMA_VERSION",
    "AI_INTEGRATED_CHECKPOINT_SOURCE_PHASE",
    "COMPONENT_STATUS_EVIDENCE_GENERATED",
    "COMPONENT_STATUS_FALLBACK_FIXTURE",
    "COMPONENT_STATUS_INSUFFICIENT_EVIDENCE",
    "COMPONENT_STATUS_MISSING",
    "COMPONENT_STATUS_PARTIAL_EVIDENCE",
    "COMPONENT_STATUS_PRESENT",
    "EVIDENCE_GENERATED_STATUS",
    "INSUFFICIENT_EVIDENCE_STATUS",
    "NEXT_PHASE_NEEDS_AI_OPERATOR_EVIDENCE",
    "NEXT_PHASE_OFFLINE_RULE_SANDBOX_REPLAY",
    "NEXT_PHASE_OFFLINE_RULE_SANDBOX_REPLAY_PREP",
    "PARTIAL_EVIDENCE_STATUS",
    "CheckpointResult",
    "main",
    "run_checkpoint",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
