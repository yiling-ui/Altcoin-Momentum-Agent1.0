"""Phase AI-6 - AI Replay Integration v0.

Read-only, deterministic replay reconstruction over Phase AI
artefacts. The Phase AI-1 Evidence Bundle, the Phase AI-4
DeepSeek Sandbox :class:`AIIntelligenceOutput`, the Phase AI-5
:class:`OperatorBriefing`, and the Phase AI-5
:class:`EvidenceCompressionReport` are projected into structural
:class:`AIReplayCase` value objects so a downstream auditor can
walk the AI Layer's commentary substrate, count its supported /
unsupported / contradicted / degraded claims, pin its
``evidence_refs`` provenance, and confirm that no AI text leaked
into Risk / Execution / Strategy / Config surfaces.

Phase AI-6 is **fundamentally** read-only / report-only /
replay-only:

  - opens NO socket;
  - imports NO exchange SDK / HTTP / WebSocket / LLM client /
    Telegram bot library / Risk Engine / Execution FSM /
    DeepSeek transport;
  - reads NO ``os.environ``;
  - defines NO order-creation / order-cancellation /
    leverage-mutation / margin-mode-mutation /
    position-mutation / runtime-config-patch function;
  - mutates NO event row, NO trading state, NO capital state,
    NO risk state, NO runtime parameter;
  - is therefore SAFE to run against any production-grade
    ``events.db`` and against any frozen Phase AI-1 / AI-4 /
    AI-5 JSON artefact.

This module is paper-only / report-only / replay-only. It MUST
NEVER:

  - produce ``buy`` / ``sell`` / ``long`` / ``short`` /
    ``direction`` / ``side`` / ``entry`` / ``exit``;
  - produce ``position_size`` / ``leverage`` / ``stop`` /
    ``stop_loss`` / ``target`` / ``take_profit`` /
    ``risk_budget``;
  - produce ``runtime_config_patch`` / ``symbol_limit_patch``
    / ``threshold_patch`` / ``candidate_pool_patch`` /
    ``regime_weight_patch`` / ``strategy_parameter_patch``;
  - authorise live trading or auto-tuning;
  - trigger Phase 12.

A successful Phase AI-6 acceptance only allows the AI Layer to
record its commentary substrate inside replay / reflection
audits; it does **NOT** authorise live trading, does **NOT**
authorise the real DeepSeek HTTP transport, does **NOT**
authorise auto-tuning, does **NOT** open Phase 12.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.ai.evidence_bundle import (
    FORBIDDEN_AI_OUTPUT_FIELDS,
    _assert_no_forbidden_fields,
    _coerce_content,
)


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------
SOURCE_PHASE: str = "phase_ai_6"
SOURCE_MODULE: str = "ai_replay_integration"
SCHEMA_VERSION: str = "v0"


# ---------------------------------------------------------------------------
# Closed event-type vocabulary for Phase AI-6 replay artefacts
# ---------------------------------------------------------------------------
# These are report / export / replay-class identifiers. They are
# NOT wired into the runtime hot path and NOT registered in
# :class:`app.core.events.EventType`. They mirror the Phase AI-5
# pattern (`AI_OPERATOR_BRIEFING_GENERATED`,
# `AI_EVIDENCE_COMPRESSION_GENERATED`).
AI_REPLAY_CASE_RECONSTRUCTED: str = "AI_REPLAY_CASE_RECONSTRUCTED"
AI_REPLAY_SUMMARY_GENERATED: str = "AI_REPLAY_SUMMARY_GENERATED"


# ---------------------------------------------------------------------------
# Closed source-kind vocabulary
# ---------------------------------------------------------------------------
class AIReplaySourceKind:
    """Closed string set describing which AI artefact a replay
    case was reconstructed from.

    Each constant pins one of the Phase AI-1 / AI-4 / AI-5
    JSON artefact shapes. Adding a new kind is a deliberate
    code change AND a brief amendment.
    """

    EVIDENCE_BUNDLE: str = "evidence_bundle"
    AI_INTELLIGENCE_OUTPUT: str = "ai_intelligence_output"
    OPERATOR_BRIEFING: str = "operator_briefing"
    EVIDENCE_COMPRESSION_REPORT: str = "evidence_compression_report"


_VALID_SOURCE_KINDS: frozenset[str] = frozenset(
    {
        AIReplaySourceKind.EVIDENCE_BUNDLE,
        AIReplaySourceKind.AI_INTELLIGENCE_OUTPUT,
        AIReplaySourceKind.OPERATOR_BRIEFING,
        AIReplaySourceKind.EVIDENCE_COMPRESSION_REPORT,
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _coerce_str_tuple(value: Any) -> tuple[str, ...]:
    """Coerce ``value`` into a tuple of stripped strings,
    preserving input order. ``None`` becomes ``()``. Empty /
    whitespace-only entries are filtered. The function NEVER
    invents new entries.
    """
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    if isinstance(value, Sequence):
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                out.append(text)
        return tuple(out)
    return ()


def _maybe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _maybe_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _claim_iter(payload: Mapping[str, Any], *keys: str) -> Iterable[Any]:
    """Yield items from the first non-empty list value found at
    any of ``keys``. Returns nothing if no key resolves."""
    for key in keys:
        seq = payload.get(key)
        if isinstance(seq, Sequence) and not isinstance(seq, (str, bytes)):
            return seq
    return ()


# ---------------------------------------------------------------------------
# Replay case
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AIReplayCase:
    """One Phase AI-6 replay case, reconstructed from one Phase
    AI-1 / AI-4 / AI-5 JSON artefact.

    The dataclass is descriptive only; it never carries
    direction / sizing / leverage / stop / target / risk-budget
    fields. The :func:`_assert_no_forbidden_fields` guard runs
    at every :meth:`to_dict` boundary. The hard-pinned
    ``trade_authority=False`` / ``auto_tuning_allowed=False`` /
    ``phase_12_forbidden=True`` flags are re-pinned at every
    serialisation boundary, even if a caller flips the
    dataclass field via ``object.__setattr__``.
    """

    case_id: str
    bundle_id: str
    ai_output_id: str
    task_type: str
    source_kind: str
    source_report_paths: tuple[str, ...]
    claim_count: int
    supported_claim_count: int
    unsupported_claim_count: int
    contradicted_claim_count: int
    degraded_claim_count: int
    rejected_claim_count: int
    reality_check_status_summary: Mapping[str, int]
    evidence_refs: tuple[str, ...]
    forbidden_fields_stripped: tuple[str, ...]
    redacted_secret_count: int
    risk_tags: tuple[str, ...]
    notable_symbols: tuple[str, ...]
    warnings: tuple[str, ...]
    degraded_reasons: tuple[str, ...]
    timestamp_utc: str | None = None
    schema_version: str = SCHEMA_VERSION
    source_phase: str = SOURCE_PHASE
    source_module: str = SOURCE_MODULE
    # Hard-pinned root-constraint flags. Re-pinned at every
    # ``to_dict`` boundary even if a caller flips the dataclass
    # field via ``object.__setattr__``.
    trade_authority: bool = False
    auto_tuning_allowed: bool = False
    phase_12_forbidden: bool = True
    ai_output_is_commentary_only: bool = True
    ai_output_can_be_truth: bool = False
    ai_output_can_be_training_label: bool = False
    ai_output_can_be_tail_label: bool = False
    ai_output_can_be_strategy_sample: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "source_module": self.source_module,
            "replay_object": "AIReplayCase",
            "replay_event_type": AI_REPLAY_CASE_RECONSTRUCTED,
            "case_id": str(self.case_id),
            "bundle_id": str(self.bundle_id),
            "ai_output_id": str(self.ai_output_id),
            "task_type": str(self.task_type),
            "source_kind": str(self.source_kind),
            "source_report_paths": list(self.source_report_paths),
            "claim_count": int(self.claim_count),
            "supported_claim_count": int(self.supported_claim_count),
            "unsupported_claim_count": int(self.unsupported_claim_count),
            "contradicted_claim_count": int(self.contradicted_claim_count),
            "degraded_claim_count": int(self.degraded_claim_count),
            "rejected_claim_count": int(self.rejected_claim_count),
            "reality_check_status_summary": dict(
                sorted(self.reality_check_status_summary.items())
            ),
            "evidence_refs": list(self.evidence_refs),
            "forbidden_fields_stripped": list(
                self.forbidden_fields_stripped
            ),
            "redacted_secret_count": int(self.redacted_secret_count),
            "risk_tags": list(self.risk_tags),
            "notable_symbols": list(self.notable_symbols),
            "warnings": list(self.warnings),
            "degraded_reasons": list(self.degraded_reasons),
            "timestamp_utc": self.timestamp_utc,
            # Hard-pinned root-constraint flags. These MUST
            # NEVER be relaxed by a downstream serialiser.
            "trade_authority": False,
            "auto_tuning_allowed": False,
            "phase_12_forbidden": True,
            "ai_output_is_commentary_only": True,
            "ai_output_can_be_truth": False,
            "ai_output_can_be_training_label": False,
            "ai_output_can_be_tail_label": False,
            "ai_output_can_be_strategy_sample": False,
            # Project-wide safety-flag invariants.
            "safety_flags": {
                "mode": "paper",
                "live_trading": False,
                "exchange_live_orders": False,
                "right_tail": False,
                "llm": False,
                "llm_outbound_enabled": False,
                "sandbox_only": True,
                "telegram_outbound_enabled": False,
                "binance_private_api_enabled": False,
            },
            # Forbidden-field reference list so a downstream
            # consumer can audit the contract without parsing
            # the source.
            "forbidden_fields": sorted(FORBIDDEN_AI_OUTPUT_FIELDS),
        }
        _assert_no_forbidden_fields(payload, context="AIReplayCase.to_dict")
        return payload


# ---------------------------------------------------------------------------
# Replay summary
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AIReplaySummary:
    """Aggregate Phase AI-6 replay summary across many cases.

    Every count is derived from the case list; the engine
    NEVER fabricates numbers. ``trade_authority`` /
    ``auto_tuning_allowed`` / ``phase_12_forbidden`` are
    hard-pinned at every :meth:`to_dict` boundary.
    """

    total_cases: int
    evidence_bundle_count: int
    ai_intelligence_output_count: int
    operator_briefing_count: int
    evidence_compression_count: int
    supported_claim_count: int
    unsupported_claim_count: int
    contradicted_claim_count: int
    reality_check_failed_count: int
    missing_evidence_count: int
    forbidden_field_stripped_count: int
    degraded_run_count: int
    redacted_secret_count: int
    evidence_refs: tuple[str, ...]
    notable_symbols: tuple[str, ...]
    warnings: tuple[str, ...]
    cases: tuple[AIReplayCase, ...]
    schema_version: str = SCHEMA_VERSION
    source_phase: str = SOURCE_PHASE
    source_module: str = SOURCE_MODULE
    trade_authority: bool = False
    auto_tuning_allowed: bool = False
    phase_12_forbidden: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "source_module": self.source_module,
            "replay_object": "AIReplaySummary",
            "replay_event_type": AI_REPLAY_SUMMARY_GENERATED,
            "total_cases": int(self.total_cases),
            "evidence_bundle_count": int(self.evidence_bundle_count),
            "ai_intelligence_output_count": int(
                self.ai_intelligence_output_count
            ),
            "operator_briefing_count": int(self.operator_briefing_count),
            "evidence_compression_count": int(
                self.evidence_compression_count
            ),
            "supported_claim_count": int(self.supported_claim_count),
            "unsupported_claim_count": int(self.unsupported_claim_count),
            "contradicted_claim_count": int(self.contradicted_claim_count),
            "reality_check_failed_count": int(
                self.reality_check_failed_count
            ),
            "missing_evidence_count": int(self.missing_evidence_count),
            "forbidden_field_stripped_count": int(
                self.forbidden_field_stripped_count
            ),
            "degraded_run_count": int(self.degraded_run_count),
            "redacted_secret_count": int(self.redacted_secret_count),
            "evidence_refs": list(self.evidence_refs),
            "notable_symbols": list(self.notable_symbols),
            "warnings": list(self.warnings),
            "cases": [c.to_dict() for c in self.cases],
            "trade_authority": False,
            "auto_tuning_allowed": False,
            "phase_12_forbidden": True,
            "ai_output_is_commentary_only": True,
            "ai_output_can_be_truth": False,
            "ai_output_can_be_training_label": False,
            "ai_output_can_be_tail_label": False,
            "ai_output_can_be_strategy_sample": False,
            "safety_flags": {
                "mode": "paper",
                "live_trading": False,
                "exchange_live_orders": False,
                "right_tail": False,
                "llm": False,
                "llm_outbound_enabled": False,
                "sandbox_only": True,
                "telegram_outbound_enabled": False,
                "binance_private_api_enabled": False,
            },
        }
        _assert_no_forbidden_fields(
            payload, context="AIReplaySummary.to_dict"
        )
        return payload


# ---------------------------------------------------------------------------
# Internal extractors
# ---------------------------------------------------------------------------
def _extract_reality_check_status_summary(
    artefact: Mapping[str, Any],
) -> dict[str, int]:
    """Best-effort Reality-Check status histogram.

    Walks the artefact's ``claims`` /
    ``compressed_claims`` arrays and counts each
    ``reality_check_status``. Falls back to the artefact's
    own top-level ``reality_check_status`` /
    ``reality_check_summary`` block when no per-claim list
    exists.
    """
    counts: dict[str, int] = {}
    for key in ("claims", "compressed_claims"):
        seq = artefact.get(key)
        if isinstance(seq, Sequence) and not isinstance(seq, (str, bytes)):
            for entry in seq:
                if not isinstance(entry, Mapping):
                    continue
                status = _maybe_str(entry.get("reality_check_status"))
                if status:
                    counts[status] = counts.get(status, 0) + 1
            if counts:
                return counts
    summary = artefact.get("reality_check_summary")
    if isinstance(summary, Mapping):
        for k, v in summary.items():
            if isinstance(v, int) and not isinstance(v, bool):
                counts[str(k)] = v
        if counts:
            return counts
    overall = _maybe_str(artefact.get("reality_check_status"))
    if overall:
        counts[overall] = 1
    return counts


def _claim_classification_counts(
    artefact: Mapping[str, Any],
) -> tuple[int, int, int, int, int, int]:
    """Return ``(total, supported, unsupported, contradicted,
    degraded, rejected)`` claim counts from one Phase AI-1/4/5
    artefact.

    When the artefact carries a per-claim list (``claims`` /
    ``compressed_claims``) the function tallies each entry's
    ``classification`` / ``citation_authority_level`` /
    ``reality_check_status`` and the **total** is
    ``len(claims)``. Top-level convenience lists
    (``supported_claims`` / ``degraded_claims`` /
    ``rejected_claims`` / ``contradictions`` /
    ``unsupported_claims``) are only consulted when no per-
    claim list exists, since the same claim_id may appear in
    several of those lists by design.
    """
    supported = 0
    unsupported = 0
    contradicted = 0
    degraded = 0
    rejected = 0

    claims_seq = artefact.get("claims") or artefact.get("compressed_claims")
    if isinstance(claims_seq, Sequence) and not isinstance(
        claims_seq, (str, bytes)
    ):
        for entry in claims_seq:
            if not isinstance(entry, Mapping):
                continue
            classification = _maybe_str(entry.get("classification"))
            citation = _maybe_str(entry.get("citation_authority_level"))
            rc_status = _maybe_str(entry.get("reality_check_status"))
            rc_authority = _maybe_str(
                entry.get("reality_check_authority_level")
            )

            # Compression classification takes priority.
            if classification == "SUPPORTED":
                supported += 1
            elif classification == "UNSUPPORTED":
                unsupported += 1
            elif classification == "CONTRADICTED":
                contradicted += 1
            elif classification == "DEGRADED_NO_EVIDENCE":
                degraded += 1
            elif classification == "REJECTED":
                rejected += 1
            elif rc_status == "CONTRADICTED":
                contradicted += 1
            elif rc_status in (
                "REJECTED_LOOKAHEAD",
                "REJECTED_UNVERIFIABLE_NARRATIVE",
            ):
                rejected += 1
            elif rc_status == "INSUFFICIENT_EVIDENCE":
                unsupported += 1
            elif rc_status == "PARTIALLY_SUPPORTED":
                supported += 1  # treat partial support as supported
            elif citation in (
                "DEGRADED_NO_EVIDENCE",
                "UNSUPPORTED_INTELLIGENCE",
            ):
                degraded += 1
            elif citation in (
                "REJECTED_BY_SCHEMA",
                "REJECTED_INVALID_EVIDENCE",
            ):
                rejected += 1
            elif citation == "SUPPORTED_INTELLIGENCE":
                supported += 1
            elif rc_authority == "SUPPORTED_INTELLIGENCE":
                supported += 1
            elif rc_authority in (
                "DEGRADED_NO_EVIDENCE",
                "UNSUPPORTED_INTELLIGENCE",
            ):
                degraded += 1
            else:
                unsupported += 1
        # Reconcile with the top-level convenience lists.
        # Phase AI-5's compression report uses
        # ``unsupported_claims`` / ``contradictions`` /
        # ``rejected_claims`` as **union views** (a single
        # claim_id may legitimately appear in several lists).
        # If the union view counts more entries than the
        # per-claim derivation, prefer the union view so the
        # downstream reflection engine still raises the right
        # tags (UNSUPPORTED / CONTRADICTED / REJECTED).
        top_unsup = len(
            _coerce_str_tuple(artefact.get("unsupported_claims"))
        )
        top_contr = len(_coerce_str_tuple(artefact.get("contradictions")))
        top_rej = len(_coerce_str_tuple(artefact.get("rejected_claims")))
        if top_unsup > unsupported:
            unsupported = top_unsup
        if top_contr > contradicted:
            contradicted = top_contr
        if top_rej > rejected:
            rejected = top_rej
        return (
            len(claims_seq),
            supported,
            unsupported,
            contradicted,
            degraded,
            rejected,
        )

    # No per-claim list - fall back to the top-level
    # convenience lists. The same claim_id may legitimately
    # appear in several lists, so we use the union as the
    # total.
    supported_ids = _coerce_str_tuple(artefact.get("supported_claims"))
    unsupported_ids = _coerce_str_tuple(artefact.get("unsupported_claims"))
    contradicted_ids = _coerce_str_tuple(artefact.get("contradictions"))
    degraded_ids = _coerce_str_tuple(artefact.get("degraded_claims"))
    rejected_ids = _coerce_str_tuple(artefact.get("rejected_claims"))
    union: set[str] = set()
    for seq in (
        supported_ids,
        unsupported_ids,
        contradicted_ids,
        degraded_ids,
        rejected_ids,
    ):
        union.update(seq)
    return (
        len(union),
        len(supported_ids),
        len(unsupported_ids),
        len(contradicted_ids),
        len(degraded_ids),
        len(rejected_ids),
    )


def _detect_source_kind(artefact: Mapping[str, Any]) -> str | None:
    """Best-effort source-kind inference from an artefact JSON."""
    source_module = _maybe_str(artefact.get("source_module")) or ""
    source_module = source_module.lower()
    if "operator_briefing" in source_module:
        return AIReplaySourceKind.OPERATOR_BRIEFING
    if "evidence_compression" in source_module:
        return AIReplaySourceKind.EVIDENCE_COMPRESSION_REPORT
    if "intelligence" in source_module:
        return AIReplaySourceKind.AI_INTELLIGENCE_OUTPUT
    if "evidence_bundle" in source_module:
        return AIReplaySourceKind.EVIDENCE_BUNDLE
    # Shape-based fallback.
    if "compressed_claims" in artefact:
        return AIReplaySourceKind.EVIDENCE_COMPRESSION_REPORT
    if "sections" in artefact and "key_findings" in artefact:
        return AIReplaySourceKind.OPERATOR_BRIEFING
    if "claims" in artefact and "task_type" in artefact:
        return AIReplaySourceKind.AI_INTELLIGENCE_OUTPUT
    if "evidence_contract_facts" in artefact or "lookahead_policy" in artefact:
        return AIReplaySourceKind.EVIDENCE_BUNDLE
    return None


def _extract_bundle_id(artefact: Mapping[str, Any]) -> str:
    for key in ("source_bundle_id", "bundle_id"):
        text = _maybe_str(artefact.get(key))
        if text:
            return text
    return "unknown_bundle"


def _extract_ai_output_id(
    artefact: Mapping[str, Any], *, source_kind: str
) -> str:
    """Return a stable identifier for the AI artefact under
    replay. The function never invents an id; it reads the
    artefact's own identifier fields and falls back to a
    deterministic ``<source_kind>::<bundle_id>::<task_type>``
    form when none is present.
    """
    for key in (
        "source_ai_output_id",
        "ai_output_id",
        "report_id",
        "briefing_id",
    ):
        text = _maybe_str(artefact.get(key))
        if text:
            return text
    bundle_id = _extract_bundle_id(artefact)
    task_type = _maybe_str(artefact.get("task_type")) or "UNKNOWN_TASK"
    return f"{source_kind}::{bundle_id}::{task_type}"


def _extract_evidence_refs(artefact: Mapping[str, Any]) -> tuple[str, ...]:
    """Pull every cited evidence_ref from an artefact JSON,
    preserving input order and de-duplicating. The function
    NEVER invents a missing ref."""
    refs: list[str] = []
    seen: set[str] = set()

    def _push(item: Any) -> None:
        text = _maybe_str(item)
        if text and text not in seen:
            seen.add(text)
            refs.append(text)

    top_level = artefact.get("evidence_refs")
    if isinstance(top_level, Sequence) and not isinstance(
        top_level, (str, bytes)
    ):
        for ref in top_level:
            _push(ref)
    for key in ("claims", "compressed_claims"):
        seq = artefact.get(key)
        if isinstance(seq, Sequence) and not isinstance(seq, (str, bytes)):
            for entry in seq:
                if not isinstance(entry, Mapping):
                    continue
                inner = entry.get("evidence_refs")
                if isinstance(inner, Sequence) and not isinstance(
                    inner, (str, bytes)
                ):
                    for ref in inner:
                        _push(ref)
    return tuple(refs)


def _extract_warnings(artefact: Mapping[str, Any]) -> tuple[str, ...]:
    return _coerce_str_tuple(artefact.get("warnings"))


def _extract_degraded_reasons(
    artefact: Mapping[str, Any],
) -> tuple[str, ...]:
    return _coerce_str_tuple(artefact.get("degraded_reasons"))


def _extract_notable_symbols(
    artefact: Mapping[str, Any],
) -> tuple[str, ...]:
    direct = artefact.get("notable_symbols")
    if isinstance(direct, Sequence) and not isinstance(
        direct, (str, bytes)
    ):
        return _coerce_str_tuple(direct)
    return ()


def _extract_risk_tags(artefact: Mapping[str, Any]) -> tuple[str, ...]:
    return _coerce_str_tuple(artefact.get("risk_tags"))


def _extract_source_report_paths(
    artefact: Mapping[str, Any],
) -> tuple[str, ...]:
    for key in ("source_report_paths", "source_reports"):
        seq = artefact.get(key)
        if isinstance(seq, Sequence) and not isinstance(seq, (str, bytes)):
            return _coerce_str_tuple(seq)
    return ()


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
class AIReplayBuilder:
    """Pure, deterministic builder for Phase AI-6 replay cases.

    The builder is stateless and side-effect-free. Each
    :meth:`replay_artefact` call is independent; each
    :meth:`build_summary` call is independent.
    """

    @staticmethod
    def replay_artefact(
        artefact: Mapping[str, Any] | Any,
        *,
        source_kind: str | None = None,
        case_id: str | None = None,
        source_report_paths: Sequence[str] | None = None,
    ) -> AIReplayCase:
        """Reconstruct one :class:`AIReplayCase` from one Phase
        AI-1 / AI-4 / AI-5 JSON artefact (or from any object
        exposing a ``to_dict`` method that returns such a
        JSON).

        ``source_kind`` is auto-detected if not provided.
        """
        # Accept dataclasses with ``.to_dict()`` for convenience.
        if not isinstance(artefact, Mapping) and hasattr(artefact, "to_dict"):
            artefact = artefact.to_dict()  # type: ignore[assignment]
        if not isinstance(artefact, Mapping):
            raise TypeError(
                "AI replay builder expects a Mapping or an object with "
                f"a .to_dict() method; got {type(artefact).__name__}."
            )

        # Defensive recursive guard - we refuse to build a case
        # over a payload that contains a forbidden trade-action /
        # runtime-config-patch key. Phase AI-1 / AI-4 / AI-5
        # artefacts already enforce this at their own
        # serialisation boundary; running it again at intake is
        # paranoid-by-design.
        _assert_no_forbidden_fields(
            _coerce_content(artefact),
            context="AIReplayBuilder.replay_artefact.intake",
        )

        if source_kind is None:
            source_kind = _detect_source_kind(artefact) or "unknown_kind"
        else:
            source_kind = str(source_kind)
        if source_kind not in _VALID_SOURCE_KINDS and source_kind != "unknown_kind":
            # Accept unknown sources (forward compatibility) but
            # do NOT pretend they are first-class.
            pass

        bundle_id = _extract_bundle_id(artefact)
        ai_output_id = _extract_ai_output_id(artefact, source_kind=source_kind)
        task_type = _maybe_str(artefact.get("task_type")) or (
            "OPERATOR_BRIEFING"
            if source_kind == AIReplaySourceKind.OPERATOR_BRIEFING
            else "EVIDENCE_COMPRESSION"
            if source_kind == AIReplaySourceKind.EVIDENCE_COMPRESSION_REPORT
            else "EVIDENCE_BUNDLE"
            if source_kind == AIReplaySourceKind.EVIDENCE_BUNDLE
            else "UNKNOWN_TASK"
        )

        (
            claim_count,
            supported,
            unsupported,
            contradicted,
            degraded,
            rejected,
        ) = _claim_classification_counts(artefact)

        rc_status_summary = _extract_reality_check_status_summary(artefact)
        evidence_refs = _extract_evidence_refs(artefact)
        forbidden_fields_stripped = _coerce_str_tuple(
            artefact.get("forbidden_fields_stripped")
        )
        redacted_secret_count = _maybe_int(
            artefact.get("redacted_secret_count")
        )
        warnings = _extract_warnings(artefact)
        degraded_reasons = _extract_degraded_reasons(artefact)
        notable_symbols = _extract_notable_symbols(artefact)
        risk_tags = _extract_risk_tags(artefact)
        existing_paths = _extract_source_report_paths(artefact)
        if source_report_paths is not None:
            extra = _coerce_str_tuple(source_report_paths)
            merged: list[str] = list(existing_paths)
            seen = set(merged)
            for p in extra:
                if p not in seen:
                    seen.add(p)
                    merged.append(p)
            existing_paths = tuple(merged)

        timestamp_utc = _maybe_str(artefact.get("created_at_utc"))

        case_id_str = _maybe_str(case_id) or (
            f"ai_replay::{source_kind}::{ai_output_id}"
        )

        return AIReplayCase(
            case_id=case_id_str,
            bundle_id=bundle_id,
            ai_output_id=ai_output_id,
            task_type=task_type,
            source_kind=source_kind,
            source_report_paths=existing_paths,
            claim_count=int(claim_count),
            supported_claim_count=int(supported),
            unsupported_claim_count=int(unsupported),
            contradicted_claim_count=int(contradicted),
            degraded_claim_count=int(degraded),
            rejected_claim_count=int(rejected),
            reality_check_status_summary=dict(rc_status_summary),
            evidence_refs=evidence_refs,
            forbidden_fields_stripped=forbidden_fields_stripped,
            redacted_secret_count=int(redacted_secret_count),
            risk_tags=risk_tags,
            notable_symbols=notable_symbols,
            warnings=warnings,
            degraded_reasons=degraded_reasons,
            timestamp_utc=timestamp_utc,
        )

    @staticmethod
    def replay_many(
        artefacts: Iterable[Mapping[str, Any] | Any],
    ) -> tuple[AIReplayCase, ...]:
        """Reconstruct one :class:`AIReplayCase` per input
        artefact, preserving input order. Skips ``None``."""
        cases: list[AIReplayCase] = []
        for artefact in artefacts:
            if artefact is None:
                continue
            cases.append(AIReplayBuilder.replay_artefact(artefact))
        return tuple(cases)

    @staticmethod
    def build_summary(
        cases: Sequence[AIReplayCase],
    ) -> AIReplaySummary:
        """Aggregate :class:`AIReplayCase` instances into one
        deterministic :class:`AIReplaySummary`.

        Counts are derived from the case list; the engine
        NEVER fabricates numbers.
        """
        evidence_bundle_count = 0
        ai_output_count = 0
        operator_count = 0
        compression_count = 0
        supported_total = 0
        unsupported_total = 0
        contradicted_total = 0
        rc_failed = 0
        missing_evidence = 0
        forbidden_stripped = 0
        degraded_run = 0
        redacted_secret = 0

        all_refs: list[str] = []
        seen_refs: set[str] = set()
        all_symbols: list[str] = []
        seen_symbols: set[str] = set()
        all_warnings: list[str] = []

        for case in cases:
            if case.source_kind == AIReplaySourceKind.EVIDENCE_BUNDLE:
                evidence_bundle_count += 1
            elif case.source_kind == AIReplaySourceKind.AI_INTELLIGENCE_OUTPUT:
                ai_output_count += 1
            elif case.source_kind == AIReplaySourceKind.OPERATOR_BRIEFING:
                operator_count += 1
            elif (
                case.source_kind
                == AIReplaySourceKind.EVIDENCE_COMPRESSION_REPORT
            ):
                compression_count += 1

            supported_total += case.supported_claim_count
            unsupported_total += case.unsupported_claim_count
            contradicted_total += case.contradicted_claim_count

            for status, count in case.reality_check_status_summary.items():
                if status in (
                    "CONTRADICTED",
                    "REJECTED_LOOKAHEAD",
                    "REJECTED_UNVERIFIABLE_NARRATIVE",
                    "INSUFFICIENT_EVIDENCE",
                ):
                    rc_failed += count

            if (
                case.degraded_claim_count > 0
                or (case.claim_count > 0 and not case.evidence_refs)
            ):
                missing_evidence += 1

            if case.forbidden_fields_stripped:
                forbidden_stripped += len(case.forbidden_fields_stripped)

            if case.degraded_reasons:
                degraded_run += 1

            redacted_secret += case.redacted_secret_count

            for ref in case.evidence_refs:
                if ref not in seen_refs:
                    seen_refs.add(ref)
                    all_refs.append(ref)
            for sym in case.notable_symbols:
                if sym not in seen_symbols:
                    seen_symbols.add(sym)
                    all_symbols.append(sym)
            for w in case.warnings:
                all_warnings.append(w)

        return AIReplaySummary(
            total_cases=len(cases),
            evidence_bundle_count=evidence_bundle_count,
            ai_intelligence_output_count=ai_output_count,
            operator_briefing_count=operator_count,
            evidence_compression_count=compression_count,
            supported_claim_count=supported_total,
            unsupported_claim_count=unsupported_total,
            contradicted_claim_count=contradicted_total,
            reality_check_failed_count=rc_failed,
            missing_evidence_count=missing_evidence,
            forbidden_field_stripped_count=forbidden_stripped,
            degraded_run_count=degraded_run,
            redacted_secret_count=redacted_secret,
            evidence_refs=tuple(all_refs),
            notable_symbols=tuple(all_symbols),
            warnings=tuple(all_warnings),
            cases=tuple(cases),
        )


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------
def build_ai_replay_case(
    artefact: Mapping[str, Any] | Any,
    *,
    source_kind: str | None = None,
    case_id: str | None = None,
    source_report_paths: Sequence[str] | None = None,
) -> AIReplayCase:
    """Convenience wrapper around :meth:`AIReplayBuilder.replay_artefact`."""
    return AIReplayBuilder.replay_artefact(
        artefact,
        source_kind=source_kind,
        case_id=case_id,
        source_report_paths=source_report_paths,
    )


def build_ai_replay_summary(
    artefacts: Iterable[Mapping[str, Any] | Any],
) -> AIReplaySummary:
    """Reconstruct cases from ``artefacts`` and aggregate them
    into one :class:`AIReplaySummary`."""
    cases = AIReplayBuilder.replay_many(artefacts)
    return AIReplayBuilder.build_summary(cases)


__all__ = [
    "AI_REPLAY_CASE_RECONSTRUCTED",
    "AI_REPLAY_SUMMARY_GENERATED",
    "AIReplayBuilder",
    "AIReplayCase",
    "AIReplaySourceKind",
    "AIReplaySummary",
    "SCHEMA_VERSION",
    "SOURCE_MODULE",
    "SOURCE_PHASE",
    "build_ai_replay_case",
    "build_ai_replay_summary",
]
