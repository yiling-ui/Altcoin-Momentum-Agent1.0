"""Phase AI-6 - AI Reflection Integration v0.

Read-only, deterministic, structured reflection over Phase
AI-6 :class:`AIReplayCase` objects. Each case is reflected
into one :class:`AIReflectionCase` carrying a sorted tuple of
:class:`AIReflectionTag` values, a closed
:class:`AIReflectionSeverity` label, the case's preserved
``evidence_refs``, and the brief-mandated
``ai_output_can_be_truth=False`` /
``ai_output_can_be_training_label=False`` /
``ai_output_can_be_tail_label=False`` /
``ai_output_can_be_strategy_sample=False`` /
``trade_authority=False`` / ``auto_tuning_allowed=False`` /
``phase_12_forbidden=True`` flags.

Phase AI-6 is **fundamentally** read-only / report-only /
reflection-only:

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
  - is therefore SAFE to run against any frozen Phase AI-1 /
    AI-4 / AI-5 JSON artefact.

This module is paper-only / report-only / reflection-only. It
MUST NEVER:

  - turn AI text into a Truth Layer fact;
  - turn AI text into a training label;
  - turn AI text into a tail label;
  - turn AI text into a strategy validation sample;
  - produce a trade-action or runtime-config-patch field;
  - authorise live trading or auto-tuning;
  - trigger Phase 12.

A successful Phase AI-6 acceptance only allows the AI
*Replay / Reflection Integration* commentary substrate to be
audited. It does **NOT** authorise the AI Layer's involvement
in Risk / Execution / Strategy / Config surfaces.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.ai.evidence_bundle import (
    FORBIDDEN_AI_OUTPUT_FIELDS,
    _assert_no_forbidden_fields,
)
from app.replay.ai_replay import (
    AIReplayBuilder,
    AIReplayCase,
    AIReplaySourceKind,
    AIReplaySummary,
)


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------
SOURCE_PHASE: str = "phase_ai_6"
SOURCE_MODULE: str = "ai_reflection_integration"
SCHEMA_VERSION: str = "v0"


# ---------------------------------------------------------------------------
# Closed event-type vocabulary
# ---------------------------------------------------------------------------
AI_REFLECTION_CASE_GENERATED: str = "AI_REFLECTION_CASE_GENERATED"
AI_REFLECTION_SUMMARY_GENERATED: str = "AI_REFLECTION_SUMMARY_GENERATED"


# ---------------------------------------------------------------------------
# Severity vocabulary
# ---------------------------------------------------------------------------
class AIReflectionSeverity(str, Enum):
    """Closed severity vocabulary for an AI reflection case.

    Severity is a descriptive label only; it never authorises a
    trade or a runtime change.
    """

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


_SEVERITY_RANK: dict[str, int] = {
    AIReflectionSeverity.UNKNOWN.value: 0,
    AIReflectionSeverity.INFO.value: 1,
    AIReflectionSeverity.LOW.value: 2,
    AIReflectionSeverity.MEDIUM.value: 3,
    AIReflectionSeverity.HIGH.value: 4,
}


# ---------------------------------------------------------------------------
# Reflection tag vocabulary
# ---------------------------------------------------------------------------
class AIReflectionTag(str, Enum):
    """Closed reflection-tag vocabulary for the AI commentary
    substrate.

    Adding a new tag is a deliberate code change AND a brief
    amendment. The vocabulary intentionally **omits** any tag
    that would imply trade direction (``ai_said_buy`` /
    ``ai_said_long`` / ``ai_target_hit`` /
    ``ai_direction_correct`` / ``ai_trade_signal_correct``).
    Those tags are explicitly forbidden by the Phase AI-6
    brief and are absent here by design.
    """

    AI_HELPFUL_EXPLANATION = "ai_helpful_explanation"
    AI_UNSUPPORTED_CLAIM = "ai_unsupported_claim"
    AI_CONTRADICTED_BY_TRUTH_LAYER = "ai_contradicted_by_truth_layer"
    AI_REALITY_CHECK_FAILED = "ai_reality_check_failed"
    AI_EVIDENCE_MISSING = "ai_evidence_missing"
    AI_NARRATIVE_POLLUTION_RISK = "ai_narrative_pollution_risk"
    AI_FORBIDDEN_FIELD_STRIPPED = "ai_forbidden_field_stripped"
    AI_DEGRADED_OUTPUT = "ai_degraded_output"
    AI_OPERATOR_BRIEFING_GENERATED = "ai_operator_briefing_generated"
    AI_EVIDENCE_COMPRESSION_GENERATED = "ai_evidence_compression_generated"


#: Tags that are **explicitly forbidden** by the Phase AI-6
#: brief. Exposed as a frozenset so tests / downstream auditors
#: can assert none of these strings ever escape the reflection
#: engine. The engine never produces these strings; this
#: constant is the canonical reference list.
FORBIDDEN_REFLECTION_TAGS: frozenset[str] = frozenset(
    {
        "ai_said_buy",
        "ai_said_long",
        "ai_target_hit",
        "ai_direction_correct",
        "ai_trade_signal_correct",
    }
)


# ---------------------------------------------------------------------------
# Reflection case
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AIReflectionCase:
    """One reflection case for one Phase AI-6 replay case.

    The case carries:

      - ``case_id``: identifier of the source replay case so
        the reflection is byte-stable and unambiguous;
      - ``bundle_id`` / ``ai_output_id``: best-effort identity
        propagated from the replay case;
      - ``tags``: a sorted tuple of :class:`AIReflectionTag`
        string values;
      - ``severity``: the closed
        :class:`AIReflectionSeverity` label;
      - ``evidence_refs``: preserved verbatim from the replay
        case so a downstream auditor can pin the reflection to
        its source artefact;
      - ``needs_operator_review``: actionable boolean;
      - ``ai_output_can_be_truth`` /
        ``ai_output_can_be_training_label`` /
        ``ai_output_can_be_tail_label`` /
        ``ai_output_can_be_strategy_sample``: hard-pinned to
        ``False`` at every :meth:`to_dict` boundary (the
        hard rules from §§1.1 / 1.4 of the AI Layer
        Engineering Spec);
      - ``trade_authority`` / ``auto_tuning_allowed``: hard-
        pinned to ``False``;
      - ``phase_12_forbidden``: hard-pinned to ``True``;
      - ``warnings``: a tuple of descriptive strings drawn
        from the replay case + a fixed, internal vocabulary.
    """

    case_id: str
    bundle_id: str
    ai_output_id: str
    source_kind: str
    tags: tuple[str, ...]
    severity: str
    evidence_refs: tuple[str, ...]
    needs_operator_review: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)
    schema_version: str = SCHEMA_VERSION
    source_phase: str = SOURCE_PHASE
    source_module: str = SOURCE_MODULE
    # Hard-pinned root-constraint flags. Re-pinned at every
    # :meth:`to_dict` boundary even if a caller flips the
    # dataclass field via ``object.__setattr__``.
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
            "reflection_object": "AIReflectionCase",
            "reflection_event_type": AI_REFLECTION_CASE_GENERATED,
            "case_id": str(self.case_id),
            "bundle_id": str(self.bundle_id),
            "ai_output_id": str(self.ai_output_id),
            "source_kind": str(self.source_kind),
            "tags": list(self.tags),
            "severity": str(self.severity),
            "evidence_refs": list(self.evidence_refs),
            "needs_operator_review": bool(self.needs_operator_review),
            "warnings": list(self.warnings),
            # Hard-pinned root-constraint flags.
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
            "forbidden_fields": sorted(FORBIDDEN_AI_OUTPUT_FIELDS),
            "forbidden_reflection_tags": sorted(FORBIDDEN_REFLECTION_TAGS),
        }
        _assert_no_forbidden_fields(
            payload, context="AIReflectionCase.to_dict"
        )
        # Defence in depth: refuse to emit any forbidden tag.
        for tag in payload["tags"]:
            if tag in FORBIDDEN_REFLECTION_TAGS:
                raise ValueError(
                    f"AI Reflection produced a forbidden tag {tag!r}; "
                    "this is a hard violation of the Phase AI-6 brief."
                )
        return payload


# ---------------------------------------------------------------------------
# Reflection summary
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AIReflectionSummary:
    """Aggregate Phase AI-6 reflection summary across many
    cases.

    Counts are derived from the case list; the engine NEVER
    fabricates numbers. ``trade_authority`` /
    ``auto_tuning_allowed`` / ``phase_12_forbidden`` are hard-
    pinned at every :meth:`to_dict` boundary.
    """

    total_cases: int
    tag_counts: Mapping[str, int]
    severity_counts: Mapping[str, int]
    needs_operator_review_count: int
    evidence_refs: tuple[str, ...]
    warnings: tuple[str, ...]
    cases: tuple[AIReflectionCase, ...]
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
            "reflection_object": "AIReflectionSummary",
            "reflection_event_type": AI_REFLECTION_SUMMARY_GENERATED,
            "total_cases": int(self.total_cases),
            "tag_counts": dict(sorted(self.tag_counts.items())),
            "severity_counts": dict(sorted(self.severity_counts.items())),
            "needs_operator_review_count": int(
                self.needs_operator_review_count
            ),
            "evidence_refs": list(self.evidence_refs),
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
            "forbidden_reflection_tags": sorted(FORBIDDEN_REFLECTION_TAGS),
        }
        _assert_no_forbidden_fields(
            payload, context="AIReflectionSummary.to_dict"
        )
        return payload


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _max_severity(severities: Iterable[AIReflectionSeverity]) -> str:
    rank = -1
    chosen = AIReflectionSeverity.UNKNOWN.value
    for sev in severities:
        sev_value = sev.value if isinstance(sev, AIReflectionSeverity) else str(
            sev
        )
        r = _SEVERITY_RANK.get(sev_value, 0)
        if r > rank:
            rank = r
            chosen = sev_value
    return chosen


_TAG_DEFAULT_SEVERITY: dict[AIReflectionTag, AIReflectionSeverity] = {
    AIReflectionTag.AI_REALITY_CHECK_FAILED: AIReflectionSeverity.HIGH,
    AIReflectionTag.AI_CONTRADICTED_BY_TRUTH_LAYER: AIReflectionSeverity.HIGH,
    AIReflectionTag.AI_FORBIDDEN_FIELD_STRIPPED: AIReflectionSeverity.HIGH,
    AIReflectionTag.AI_NARRATIVE_POLLUTION_RISK: AIReflectionSeverity.MEDIUM,
    AIReflectionTag.AI_UNSUPPORTED_CLAIM: AIReflectionSeverity.MEDIUM,
    AIReflectionTag.AI_EVIDENCE_MISSING: AIReflectionSeverity.MEDIUM,
    AIReflectionTag.AI_DEGRADED_OUTPUT: AIReflectionSeverity.LOW,
    AIReflectionTag.AI_HELPFUL_EXPLANATION: AIReflectionSeverity.INFO,
    AIReflectionTag.AI_OPERATOR_BRIEFING_GENERATED: AIReflectionSeverity.INFO,
    AIReflectionTag.AI_EVIDENCE_COMPRESSION_GENERATED: (
        AIReflectionSeverity.INFO
    ),
}


_REVIEW_TRIGGERING_TAGS: frozenset[AIReflectionTag] = frozenset(
    {
        AIReflectionTag.AI_REALITY_CHECK_FAILED,
        AIReflectionTag.AI_CONTRADICTED_BY_TRUTH_LAYER,
        AIReflectionTag.AI_UNSUPPORTED_CLAIM,
        AIReflectionTag.AI_FORBIDDEN_FIELD_STRIPPED,
        AIReflectionTag.AI_NARRATIVE_POLLUTION_RISK,
        AIReflectionTag.AI_EVIDENCE_MISSING,
    }
)


_NARRATIVE_POLLUTION_REASON_TOKENS: tuple[str, ...] = (
    "narrative",
    "unverifiable",
    "smart_money",
    "smart money",
    "main force",
    "whales",
    "whale",
    "definitely",
    "guaranteed",
    "obviously",
)


def _detect_narrative_pollution(case: AIReplayCase) -> bool:
    """Return True if the case carries any narrative-pollution
    signal in its degraded reasons / warnings."""
    for token in (case.warnings + case.degraded_reasons):
        text = token.lower()
        for needle in _NARRATIVE_POLLUTION_REASON_TOKENS:
            if needle in text:
                return True
    rc = case.reality_check_status_summary
    if isinstance(rc, Mapping):
        if rc.get("REJECTED_UNVERIFIABLE_NARRATIVE"):
            return True
    return False


def _detect_lookahead_rejection(case: AIReplayCase) -> bool:
    rc = case.reality_check_status_summary
    if isinstance(rc, Mapping) and rc.get("REJECTED_LOOKAHEAD"):
        return True
    return False


# ---------------------------------------------------------------------------
# Reflection engine
# ---------------------------------------------------------------------------
class AIReplayReflectionEngine:
    """Read-only Phase AI-6 reflection engine.

    Public surface:

      - :meth:`reflect_replay_case`      - reflect on one
        :class:`AIReplayCase`, return one
        :class:`AIReflectionCase`.
      - :meth:`reflect_replay_cases`     - reflect on many
        :class:`AIReplayCase` instances, return one
        :class:`AIReflectionSummary`.
      - :meth:`replay_and_reflect`       - one-shot wrapper
        that takes the raw Phase AI-1 / AI-4 / AI-5 JSON
        artefacts, builds replay cases, then reflects on
        them. Returns ``(AIReplaySummary, AIReflectionSummary)``.

    The engine is stateless and side-effect-free. It NEVER
    opens a socket, NEVER imports a Risk / Execution /
    Exchange / LLM / Telegram module, and NEVER produces a
    runtime-config patch.
    """

    def __init__(self) -> None:
        # No mutable state - the engine is intentionally inert.
        self._replay_builder = AIReplayBuilder()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def reflect_replay_case(
        self, case: AIReplayCase
    ) -> AIReflectionCase:
        """Reflect on one :class:`AIReplayCase` and return one
        deterministic :class:`AIReflectionCase`."""
        if not isinstance(case, AIReplayCase):
            raise TypeError(
                "AI reflection engine expects an AIReplayCase; got "
                f"{type(case).__name__}."
            )

        tags: list[AIReflectionTag] = []
        severities: list[AIReflectionSeverity] = []
        warnings: list[str] = list(case.warnings)

        # Source-kind acknowledgement tags.
        if case.source_kind == AIReplaySourceKind.OPERATOR_BRIEFING:
            tags.append(AIReflectionTag.AI_OPERATOR_BRIEFING_GENERATED)
        if (
            case.source_kind
            == AIReplaySourceKind.EVIDENCE_COMPRESSION_REPORT
        ):
            tags.append(AIReflectionTag.AI_EVIDENCE_COMPRESSION_GENERATED)

        # Forbidden-field stripping (defence in depth).
        if case.forbidden_fields_stripped:
            tags.append(AIReflectionTag.AI_FORBIDDEN_FIELD_STRIPPED)
            warnings.append(
                f"forbidden_fields_stripped_count={len(case.forbidden_fields_stripped)}"
            )

        # Reality-check failure (CONTRADICTED / REJECTED_*).
        rc = case.reality_check_status_summary
        if isinstance(rc, Mapping):
            if rc.get("CONTRADICTED"):
                tags.append(AIReflectionTag.AI_CONTRADICTED_BY_TRUTH_LAYER)
            failed_count = (
                int(rc.get("CONTRADICTED", 0) or 0)
                + int(rc.get("REJECTED_LOOKAHEAD", 0) or 0)
                + int(rc.get("REJECTED_UNVERIFIABLE_NARRATIVE", 0) or 0)
                + int(rc.get("INSUFFICIENT_EVIDENCE", 0) or 0)
            )
            if failed_count > 0:
                tags.append(AIReflectionTag.AI_REALITY_CHECK_FAILED)

        # Contradicted claim count is the structural fallback.
        if case.contradicted_claim_count > 0:
            tags.append(AIReflectionTag.AI_CONTRADICTED_BY_TRUTH_LAYER)
            tags.append(AIReflectionTag.AI_REALITY_CHECK_FAILED)

        # Unsupported claims.
        if case.unsupported_claim_count > 0:
            tags.append(AIReflectionTag.AI_UNSUPPORTED_CLAIM)

        # Missing evidence: degraded claims OR claims-with-no-refs.
        if case.degraded_claim_count > 0 or (
            case.claim_count > 0 and not case.evidence_refs
        ):
            tags.append(AIReflectionTag.AI_EVIDENCE_MISSING)

        # Narrative pollution.
        if _detect_narrative_pollution(case) or _detect_lookahead_rejection(
            case
        ):
            tags.append(AIReflectionTag.AI_NARRATIVE_POLLUTION_RISK)

        # Degraded run.
        if case.degraded_reasons:
            tags.append(AIReflectionTag.AI_DEGRADED_OUTPUT)

        # Helpful explanation: at least one supported claim and
        # no critical anomaly tag attached so far. The tag is
        # additive and is intentionally informational.
        critical_already = any(
            t in tags
            for t in (
                AIReflectionTag.AI_CONTRADICTED_BY_TRUTH_LAYER,
                AIReflectionTag.AI_REALITY_CHECK_FAILED,
                AIReflectionTag.AI_FORBIDDEN_FIELD_STRIPPED,
                AIReflectionTag.AI_NARRATIVE_POLLUTION_RISK,
            )
        )
        if case.supported_claim_count > 0 and not critical_already:
            tags.append(AIReflectionTag.AI_HELPFUL_EXPLANATION)

        # De-duplicate while preserving deterministic order.
        unique_tags: list[AIReflectionTag] = []
        seen: set[AIReflectionTag] = set()
        for t in tags:
            if t in seen:
                continue
            seen.add(t)
            unique_tags.append(t)

        # If somehow no tag attached (e.g. an unknown source
        # kind with zero claims), fall back to INFO + helpful
        # explanation marker. The engine never raises.
        if not unique_tags:
            unique_tags.append(AIReflectionTag.AI_HELPFUL_EXPLANATION)

        # Severity is the max severity among attached tags.
        for t in unique_tags:
            severities.append(
                _TAG_DEFAULT_SEVERITY.get(t, AIReflectionSeverity.INFO)
            )
        severity_value = _max_severity(severities)

        needs_review = any(t in _REVIEW_TRIGGERING_TAGS for t in unique_tags)

        # Sort tags for deterministic emission.
        tag_strings = tuple(sorted(t.value for t in unique_tags))

        # Defence in depth: assert no forbidden tag escaped.
        for t in tag_strings:
            if t in FORBIDDEN_REFLECTION_TAGS:
                raise ValueError(
                    f"AI Reflection engine attempted to emit forbidden "
                    f"tag {t!r}; this is a hard violation of the Phase "
                    "AI-6 brief."
                )

        # De-duplicate warnings while preserving order.
        unique_warnings: list[str] = []
        seen_w: set[str] = set()
        for w in warnings:
            if w not in seen_w:
                seen_w.add(w)
                unique_warnings.append(w)

        return AIReflectionCase(
            case_id=case.case_id,
            bundle_id=case.bundle_id,
            ai_output_id=case.ai_output_id,
            source_kind=case.source_kind,
            tags=tag_strings,
            severity=severity_value,
            evidence_refs=case.evidence_refs,
            needs_operator_review=needs_review,
            warnings=tuple(unique_warnings),
        )

    def reflect_replay_cases(
        self,
        cases: Iterable[AIReplayCase],
    ) -> AIReflectionSummary:
        """Reflect on many :class:`AIReplayCase` instances."""
        case_list = [c for c in cases if c is not None]
        reflections: list[AIReflectionCase] = [
            self.reflect_replay_case(c) for c in case_list
        ]

        tag_counts: dict[str, int] = {}
        severity_counts: dict[str, int] = {}
        review_count = 0
        all_refs: list[str] = []
        seen_refs: set[str] = set()
        all_warnings: list[str] = []

        for r in reflections:
            severity_counts[r.severity] = (
                severity_counts.get(r.severity, 0) + 1
            )
            for tag in r.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            if r.needs_operator_review:
                review_count += 1
            for ref in r.evidence_refs:
                if ref not in seen_refs:
                    seen_refs.add(ref)
                    all_refs.append(ref)
            for w in r.warnings:
                all_warnings.append(w)

        return AIReflectionSummary(
            total_cases=len(reflections),
            tag_counts=tag_counts,
            severity_counts=severity_counts,
            needs_operator_review_count=review_count,
            evidence_refs=tuple(all_refs),
            warnings=tuple(all_warnings),
            cases=tuple(reflections),
        )

    def replay_and_reflect(
        self,
        artefacts: Iterable[Mapping[str, Any] | Any],
    ) -> tuple[AIReplaySummary, AIReflectionSummary]:
        """One-shot helper: build replay cases then reflect."""
        cases = AIReplayBuilder.replay_many(artefacts)
        replay_summary = AIReplayBuilder.build_summary(cases)
        reflection_summary = self.reflect_replay_cases(cases)
        return replay_summary, reflection_summary


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------
def reflect_replay_case(case: AIReplayCase) -> AIReflectionCase:
    """Convenience wrapper around
    :meth:`AIReplayReflectionEngine.reflect_replay_case`."""
    return AIReplayReflectionEngine().reflect_replay_case(case)


def reflect_replay_cases(
    cases: Iterable[AIReplayCase],
) -> AIReflectionSummary:
    """Convenience wrapper around
    :meth:`AIReplayReflectionEngine.reflect_replay_cases`."""
    return AIReplayReflectionEngine().reflect_replay_cases(cases)


def replay_and_reflect_artefacts(
    artefacts: Iterable[Mapping[str, Any] | Any],
) -> tuple[AIReplaySummary, AIReflectionSummary]:
    """Convenience wrapper around
    :meth:`AIReplayReflectionEngine.replay_and_reflect`."""
    return AIReplayReflectionEngine().replay_and_reflect(artefacts)


__all__ = [
    "AI_REFLECTION_CASE_GENERATED",
    "AI_REFLECTION_SUMMARY_GENERATED",
    "AIReflectionCase",
    "AIReflectionSeverity",
    "AIReflectionSummary",
    "AIReflectionTag",
    "AIReplayReflectionEngine",
    "FORBIDDEN_REFLECTION_TAGS",
    "SCHEMA_VERSION",
    "SOURCE_MODULE",
    "SOURCE_PHASE",
    "reflect_replay_case",
    "reflect_replay_cases",
    "replay_and_reflect_artefacts",
]
