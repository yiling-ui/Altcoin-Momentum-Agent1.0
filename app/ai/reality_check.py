"""Phase AI-3 - Reality Check Layer v0.

The AI Layer's *deterministic / statistical* cross-verifier.
Phase AI-1 built the Evidence Bundle (the AI Layer's only
allowed read surface). Phase AI-2 built the claim-level
*citation contract* (every AI claim must cite Truth-Layer
evidence via ``evidence_refs``). Phase AI-3 closes the loop:
having ``evidence_refs`` is necessary but not sufficient; an
AI claim is also cross-checked against the Truth Layer the
``evidence_refs`` point at, plus the market / system-behavior
/ outcome facts pinned in the Phase AI-1 Evidence Bundle.

Reality Check is **not** an LLM. It is **not** a DeepSeek
client. It is **not** a network transport. It is **not** a
prompt template. It is a closed, deterministic, statistical
verifier that runs offline against the bundle's frozen facts:

  - it never calls an LLM / DeepSeek;
  - it never opens a network socket;
  - it never reads or carries API secrets;
  - it never reads private exchange / account state;
  - it never reads previous AI answers, chat history, or
    operator messages;
  - it never produces a trade decision;
  - it never produces a runtime-config patch;
  - it never alters Risk / Execution / Exchange / Telegram /
    Config surfaces.

The four AI root constraints from
``docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`` are enforced in
code AND in tests:

  1. **Responsibility Isolation** - claim and result payloads
     are scrubbed of every forbidden trade-action /
     runtime-config-patch field via the recursive
     :func:`_assert_no_forbidden_fields` guard imported from
     :mod:`app.ai.evidence_bundle`.
  2. **Stateless Inference** - each
     :meth:`AIRealityCheckEngine.check` call is independent;
     no instance state is mutated between calls.
  3. **Hard Rule Anchoring** - a claim with
     ``evidence_refs`` but no Truth-Layer facts to support it
     is demoted to
     :attr:`AIRealityCheckStatus.INSUFFICIENT_EVIDENCE`. A
     claim that contradicts the bundle's market / outcome
     facts is demoted to
     :attr:`AIRealityCheckStatus.CONTRADICTED`. A claim
     written as unverifiable narrative (e.g. "smart money is
     definitely entering") with no computable backing is
     rejected via
     :attr:`AIRealityCheckStatus.REJECTED_UNVERIFIABLE_NARRATIVE`.
     A live claim that depends on a future / unsealed window
     is rejected via
     :attr:`AIRealityCheckStatus.REJECTED_LOOKAHEAD`.
  4. **Feedback Isolation** - every emitted result re-pins
     ``ai_output_is_commentary_only=True``,
     ``ai_output_can_be_training_label=False``,
     ``phase_12_forbidden=True``, ``auto_tuning_allowed=False``
     so AI text never becomes a training label or a runtime
     fact.

This module is paper / report / read-only. It does NOT
authorise live trading, does NOT authorise auto-tuning, does
NOT call DeepSeek / any LLM, and does NOT open Phase 12. A
successful Phase AI-3 only unlocks Phase AI-4 *Offline
Sandbox* (separate later phase, **not** the runtime hot path,
**not** Phase 12).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.ai.evidence_bundle import (
    FORBIDDEN_AI_OUTPUT_FIELDS,
    _assert_no_forbidden_fields,
    _coerce_content,
)


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------
AI_REALITY_CHECK_SOURCE_PHASE: str = "phase_ai_3"
AI_REALITY_CHECK_SOURCE_MODULE: str = "ai_reality_check_layer"
AI_REALITY_CHECK_SCHEMA_VERSION: str = "v0"


# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------
class AIRealityCheckStatus(str, Enum):
    """Closed status vocabulary for one Reality Check run.

    No member of this enum grants *trade authority*. Even
    :attr:`SUPPORTED` is *commentary substrate* only; it does
    NOT direct the Risk Engine, the Execution FSM, the Capital
    Flow Engine, or any other trade-authority surface.
    """

    #: Claim is consistent with the cited Truth-Layer
    #: evidence and with the bundle's market / outcome facts.
    SUPPORTED = "SUPPORTED"

    #: Some support but at least one supporting axis is weak,
    #: incomplete, or invalid. Confidence is downgraded.
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"

    #: Claim asserts something the bundle's market / outcome
    #: facts directly contradict (e.g. "risk appetite
    #: expanding" vs. ``breadth_weak=True`` /
    #: ``data_gap_severe=True`` / ``late_chase_high=True`` /
    #: ``fake_breakout_rising=True`` /
    #: ``funding_overheated=True`` with
    #: ``failed_continuation=True``).
    CONTRADICTED = "CONTRADICTED"

    #: Claim has ``evidence_refs`` but lacks the Truth-Layer
    #: facts (or fact fields) needed to verify it. The claim
    #: is demoted, never silently accepted.
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

    #: Claim relies on a future / unsealed window or
    #: otherwise violates the AI Layer's lookahead policy
    #: (``frozen_evidence_only=False`` /
    #: ``no_future_market_data=False`` /
    #: ``post_hoc_analysis_only_when_window_closed=False``,
    #: or an explicit
    #: ``live_inference_uses_future_outcome=True`` flag).
    REJECTED_LOOKAHEAD = "REJECTED_LOOKAHEAD"

    #: Claim is written as unverifiable narrative ("smart
    #: money is definitely entering", "whales are
    #: accumulating", "faith is returning", "main force
    #: intention is clear") and has no computable backing in
    #: the bundle. The claim is rejected, never silently
    #: accepted.
    REJECTED_UNVERIFIABLE_NARRATIVE = (
        "REJECTED_UNVERIFIABLE_NARRATIVE"
    )


class AIRealityCheckCategory(str, Enum):
    """Closed category vocabulary for the verification axes
    one Reality Check run touches.

    Each category names a *kind of check*; none of the
    categories carry direction / sizing / risk-budget
    semantics.
    """

    #: Check that ``evidence_refs`` and ``evidence_bundle_facts``
    #: are non-empty and statistically referenced by the
    #: claim.
    STATISTICAL_VERIFICATION = "STATISTICAL_VERIFICATION"

    #: Check the bundle's market / system-behavior facts
    #: (breadth, data-gap, late-chase, fake-breakout,
    #: funding) for consistency with the claim.
    MICROSTRUCTURE_VALIDATION = "MICROSTRUCTURE_VALIDATION"

    #: Compare ``confidence_raw`` against the support /
    #: contradiction signals and emit
    #: ``confidence_reality_checked``. The output confidence
    #: is always less than or equal to the input confidence.
    CONFIDENCE_CALIBRATION = "CONFIDENCE_CALIBRATION"

    #: Look for direct contradictions between the claim and
    #: the bundle's market / outcome facts.
    CONTRADICTION_DETECTION = "CONTRADICTION_DETECTION"

    #: Look at outcome facts (``failed_continuation`` /
    #: missed-tail / fake-breakout signals) for adversarial
    #: evidence against the claim.
    ADVERSARIAL_EVIDENCE_CHECK = "ADVERSARIAL_EVIDENCE_CHECK"

    #: Check the lookahead policy and reject claims that
    #: depend on future / unsealed windows.
    LOOKAHEAD_GUARD = "LOOKAHEAD_GUARD"

    #: Reject claims written as unverifiable narrative with
    #: no computable backing.
    NARRATIVE_POLLUTION_GUARD = "NARRATIVE_POLLUTION_GUARD"


class AIRealityCheckAuthorityLevel(str, Enum):
    """Closed authority-level vocabulary emitted by the
    Reality Check Layer.

    No member grants *trade authority*. The maximum any claim
    can reach is :attr:`SUPPORTED_INTELLIGENCE`, which is
    *commentary substrate* only. The Risk Engine remains the
    single trade-decision gate.
    """

    SUPPORTED_INTELLIGENCE = "SUPPORTED_INTELLIGENCE"
    UNSUPPORTED_INTELLIGENCE = "UNSUPPORTED_INTELLIGENCE"
    DEGRADED_NO_EVIDENCE = "DEGRADED_NO_EVIDENCE"
    REJECTED_BY_REALITY_CHECK = "REJECTED_BY_REALITY_CHECK"


# ---------------------------------------------------------------------------
# Lookahead policy guard
# ---------------------------------------------------------------------------
#: Lookahead-policy flags that MUST be ``True`` (or absent
#: with a default of ``True``) for a claim to clear the
#: Lookahead Guard. Mirrors the Phase AI-1
#: ``LOOKAHEAD_POLICY_FLAGS`` invariant.
_REQUIRED_LOOKAHEAD_FLAGS: tuple[str, ...] = (
    "frozen_evidence_only",
    "no_future_market_data",
    "no_training_from_ai_output",
    "no_runtime_feedback",
    "post_hoc_analysis_only_when_window_closed",
)

#: Lookahead-policy flags that, if present and ``True``, are
#: themselves a violation (the producer is admitting a
#: lookahead leak).
_FORBIDDEN_LOOKAHEAD_FLAGS: tuple[str, ...] = (
    "live_inference_uses_future_outcome",
    "uses_unsealed_window",
    "uses_future_market_data",
    "trains_from_ai_output",
)


# ---------------------------------------------------------------------------
# Narrative pollution vocabulary
# ---------------------------------------------------------------------------
#: Substring fragments that mark a claim as *unverifiable
#: narrative*. The check is case-insensitive and uses
#: substring containment; it is **only** applied when the
#: claim has no computable backing (no
#: ``truth_layer_fields_used`` and no fact-level support
#: signals). A legitimate claim that uses one of these
#: phrases AND cites concrete Truth-Layer fields is **not**
#: rejected on this axis.
_UNVERIFIABLE_NARRATIVE_FRAGMENTS: tuple[str, ...] = (
    "smart money is definitely entering",
    "smart money definitely entering",
    "smart money entering",
    "whales are accumulating",
    "whales accumulating",
    "faith is returning",
    "faith returning",
    "main force intention is clear",
    "main force intention",
    "main force is in control",
    "main force in control",
    "the main force",
    "main force",
    "definitely entering",
    "obviously bullish",
    "without a doubt",
    "guaranteed to",
)


#: Substring fragments that mark a claim as asserting an
#: *expansionary / risk-on* thesis. If the claim text
#: matches and the bundle's facts contradict, the claim is
#: demoted to ``CONTRADICTED`` / ``PARTIALLY_SUPPORTED``.
_EXPANSION_FRAGMENTS: tuple[str, ...] = (
    "risk appetite expanding",
    "risk appetite is expanding",
    "risk-on regime",
    "risk on regime",
    "regime expanding",
    "regime is expanding",
    "breadth expanding",
    "breadth is expanding",
    "broad rally",
    "improving rapidly",
    "bullish continuation",
    "bullish breakout",
    "fresh breakout",
    "liquidity expanding",
    "funding is healthy",
    "funding healthy",
)


# ---------------------------------------------------------------------------
# Forbidden output fields (re-exported from Phase AI-1)
# ---------------------------------------------------------------------------
#: Re-exported so consumers of the Reality Check module do
#: not need to import :mod:`app.ai.evidence_bundle` directly.
FORBIDDEN_REALITY_CHECK_FIELDS: frozenset[str] = (
    FORBIDDEN_AI_OUTPUT_FIELDS
)


# ---------------------------------------------------------------------------
# Input record
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AIRealityCheckInput:
    """Caller-supplied claim awaiting reality verification.

    The producer of an AI claim MUST construct one of these
    (or equivalent ``Mapping``) and hand it to the
    :class:`AIRealityCheckEngine`. The engine never invents
    missing fields and never paraphrases ``claim_text``.

    ``evidence_bundle_facts`` is the flattened (or grouped)
    view of the Phase AI-1 Evidence Bundle's facts that the
    claim claims to rely on. The engine treats it as a
    free-form ``Mapping[str, Any]``; the bundle's
    ``market_facts`` / ``system_behavior_facts`` /
    ``outcome_facts`` collections may also be passed
    explicitly via the dedicated fields below for stronger
    contradiction detection.

    ``lookahead_policy`` mirrors the Phase AI-1 bundle's
    ``lookahead_policy`` block: every flag in
    :data:`_REQUIRED_LOOKAHEAD_FLAGS` MUST be ``True``; every
    flag in :data:`_FORBIDDEN_LOOKAHEAD_FLAGS` MUST be absent
    or ``False``.

    ``authority_level`` is the producer-declared current
    authority of the claim (e.g.
    ``AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE``). The
    engine's output ``authority_level_after_check`` is
    independent of this field's value; it is computed from
    the Reality Check status only.
    """

    claim_id: str
    claim_type: str
    claim_text: str
    evidence_refs: tuple[str, ...] = ()
    truth_layer_fields_used: tuple[str, ...] = ()
    authority_level: str = ""
    confidence_raw: float | None = None
    evidence_bundle_facts: Mapping[str, Any] = field(
        default_factory=dict
    )
    market_facts: Mapping[str, Any] = field(default_factory=dict)
    system_behavior_facts: Mapping[str, Any] = field(
        default_factory=dict
    )
    outcome_facts: Mapping[str, Any] = field(default_factory=dict)
    lookahead_policy: Mapping[str, Any] = field(
        default_factory=dict
    )


# ---------------------------------------------------------------------------
# Result record
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AIRealityCheckResult:
    """Aggregate outcome of one Reality Check run.

    The result is JSON-serializable via :meth:`to_dict`. Every
    serialised payload re-pins the project-wide invariants
    (``mode=paper``, ``live_trading=False``,
    ``ai_output_is_commentary_only=True``,
    ``ai_output_can_be_training_label=False``,
    ``phase_12_forbidden=True``, ``auto_tuning_allowed=False``).
    """

    claim_id: str
    status: AIRealityCheckStatus
    categories_checked: tuple[AIRealityCheckCategory, ...]
    supporting_evidence_refs: tuple[str, ...]
    contradicting_evidence_refs: tuple[str, ...]
    confidence_raw: float | None
    confidence_reality_checked: float | None
    authority_level_after_check: AIRealityCheckAuthorityLevel
    degradation_reason: str | None
    warnings: tuple[str, ...]
    schema_version: str = AI_REALITY_CHECK_SCHEMA_VERSION
    source_phase: str = AI_REALITY_CHECK_SOURCE_PHASE
    source_module: str = AI_REALITY_CHECK_SOURCE_MODULE
    # Hard-pinned root-constraint flags. Re-pinned at every
    # ``to_dict`` boundary even if the dataclass field is
    # somehow flipped.
    auto_tuning_allowed: bool = False
    phase_12_forbidden: bool = True
    ai_output_is_commentary_only: bool = True
    ai_output_can_be_training_label: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable payload for this result.

        The recursive forbidden-fields guard refuses to emit a
        payload that carries a trade-action / runtime-config-
        patch key at any nesting depth.
        """

        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "source_module": self.source_module,
            "claim_id": str(self.claim_id),
            "status": self.status.value,
            "categories_checked": [
                c.value for c in self.categories_checked
            ],
            "supporting_evidence_refs": list(
                self.supporting_evidence_refs
            ),
            "contradicting_evidence_refs": list(
                self.contradicting_evidence_refs
            ),
            "confidence_raw": (
                float(self.confidence_raw)
                if self.confidence_raw is not None
                else None
            ),
            "confidence_reality_checked": (
                float(self.confidence_reality_checked)
                if self.confidence_reality_checked is not None
                else None
            ),
            "authority_level_after_check": (
                self.authority_level_after_check.value
            ),
            "degradation_reason": (
                str(self.degradation_reason)
                if self.degradation_reason is not None
                else None
            ),
            "warnings": list(self.warnings),
            "forbidden_fields": sorted(
                FORBIDDEN_REALITY_CHECK_FIELDS
            ),
            # Hard-pinned root-constraint flags - these MUST
            # NEVER be relaxed by a downstream serialiser.
            "auto_tuning_allowed": False,
            "phase_12_forbidden": True,
            "ai_output_is_commentary_only": True,
            "ai_output_can_be_training_label": False,
            # Project-wide safety-flag invariants.
            "safety_flags": {
                "mode": "paper",
                "live_trading": False,
                "exchange_live_orders": False,
                "right_tail": False,
                "llm": False,
                "telegram_outbound_enabled": False,
                "binance_private_api_enabled": False,
            },
        }
        _assert_no_forbidden_fields(
            payload, context="AIRealityCheckResult.to_dict"
        )
        return payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _coerce_str_tuple(value: Any) -> tuple[str, ...]:
    """Coerce ``value`` into a tuple of stripped strings,
    preserving input order. ``None`` becomes ``()``. The
    helper NEVER invents new entries - it only filters out
    blank entries.
    """

    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    if isinstance(value, Sequence):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return tuple(out)
    return ()


def _coerce_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _coerce_input(
    raw: AIRealityCheckInput | Mapping[str, Any],
) -> AIRealityCheckInput:
    if isinstance(raw, AIRealityCheckInput):
        return raw
    if not isinstance(raw, Mapping):
        raise TypeError(
            "AIRealityCheckEngine.check expects an "
            "AIRealityCheckInput or a Mapping; got "
            f"{type(raw).__name__}."
        )

    confidence_raw_value = raw.get("confidence_raw")
    if confidence_raw_value is None:
        confidence_raw: float | None = None
    else:
        try:
            confidence_raw = float(confidence_raw_value)
        except (TypeError, ValueError):
            confidence_raw = None

    return AIRealityCheckInput(
        claim_id=str(raw.get("claim_id", "")).strip(),
        claim_type=str(raw.get("claim_type", "")).strip(),
        claim_text=str(raw.get("claim_text", "")).strip(),
        evidence_refs=_coerce_str_tuple(raw.get("evidence_refs")),
        truth_layer_fields_used=_coerce_str_tuple(
            raw.get("truth_layer_fields_used")
        ),
        authority_level=str(raw.get("authority_level", "")).strip(),
        confidence_raw=confidence_raw,
        evidence_bundle_facts=_coerce_mapping(
            raw.get("evidence_bundle_facts")
        ),
        market_facts=_coerce_mapping(raw.get("market_facts")),
        system_behavior_facts=_coerce_mapping(
            raw.get("system_behavior_facts")
        ),
        outcome_facts=_coerce_mapping(raw.get("outcome_facts")),
        lookahead_policy=_coerce_mapping(
            raw.get("lookahead_policy")
        ),
    )


def _bool_flag(value: Any, *, default: bool) -> bool:
    """Coerce a flag value to ``bool`` with a default. Strings
    ``"true"`` / ``"false"`` (case-insensitive) are honoured;
    other truthy / falsy values use Python's standard
    semantics.
    """

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "1", "yes", "y"):
            return True
        if text in ("false", "0", "no", "n"):
            return False
        return default
    return bool(value)


def _is_lookahead_violated(
    policy: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    """Return ``(violated, reasons)``. The check is total: a
    missing required flag defaults to ``True`` (the safe
    value); a missing forbidden flag defaults to ``False``
    (the safe value).
    """

    reasons: list[str] = []
    for flag in _REQUIRED_LOOKAHEAD_FLAGS:
        if flag in policy:
            value = _bool_flag(policy[flag], default=True)
            if value is False:
                reasons.append(f"required_flag_false:{flag}")
    for flag in _FORBIDDEN_LOOKAHEAD_FLAGS:
        if flag in policy:
            value = _bool_flag(policy[flag], default=False)
            if value is True:
                reasons.append(f"forbidden_flag_true:{flag}")
    return (bool(reasons), reasons)


def _matches_any_fragment(
    text: str, fragments: Iterable[str]
) -> tuple[bool, str | None]:
    """Case-insensitive substring containment check. Returns
    ``(matched, fragment_or_none)``.
    """

    if not text:
        return (False, None)
    lowered = text.lower()
    for frag in fragments:
        if frag in lowered:
            return (True, frag)
    return (False, None)


# Closed contradiction-signal vocabulary. Each tuple is
# ``(fact_group, fact_key, predicate, reason_label)``. The
# predicate takes the raw value and returns ``True`` if it
# counts as a contradiction signal.
_CONTRADICTION_SIGNALS: tuple[
    tuple[str, str, str, str], ...
] = (
    # (group, key, predicate_kind, reason_label)
    ("market_facts", "breadth_weak", "is_true", "breadth_weak"),
    (
        "market_facts",
        "data_gap_severe",
        "is_true",
        "data_gap_severe",
    ),
    (
        "market_facts",
        "data_gap_rate",
        "ge_0_5",
        "data_gap_rate_ge_0_5",
    ),
    (
        "system_behavior_facts",
        "late_chase_high",
        "is_true",
        "late_chase_high",
    ),
    (
        "system_behavior_facts",
        "late_chase_rate",
        "ge_0_5",
        "late_chase_rate_ge_0_5",
    ),
    (
        "system_behavior_facts",
        "fake_breakout_rising",
        "is_true",
        "fake_breakout_rising",
    ),
    (
        "system_behavior_facts",
        "funding_overheated",
        "is_true",
        "funding_overheated",
    ),
    (
        "outcome_facts",
        "failed_continuation",
        "is_true",
        "failed_continuation",
    ),
    (
        "outcome_facts",
        "missed_strong_tail_rate",
        "ge_0_5",
        "missed_strong_tail_rate_ge_0_5",
    ),
)


def _evaluate_predicate(predicate_kind: str, value: Any) -> bool:
    if value is None:
        return False
    if predicate_kind == "is_true":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return float(value) != 0.0
        if isinstance(value, str):
            text = value.strip().lower()
            return text in ("true", "1", "yes", "y")
        return False
    if predicate_kind == "ge_0_5":
        try:
            return float(value) >= 0.5
        except (TypeError, ValueError):
            return False
    return False


def _detect_contradictions(
    ri: AIRealityCheckInput,
) -> list[str]:
    groups: dict[str, Mapping[str, Any]] = {
        "market_facts": ri.market_facts,
        "system_behavior_facts": ri.system_behavior_facts,
        "outcome_facts": ri.outcome_facts,
    }
    hits: list[str] = []
    for (
        group,
        key,
        predicate_kind,
        reason_label,
    ) in _CONTRADICTION_SIGNALS:
        bag = groups.get(group, {})
        if not isinstance(bag, Mapping):
            continue
        if key not in bag:
            continue
        if _evaluate_predicate(predicate_kind, bag[key]):
            hits.append(reason_label)
    return hits


def _has_any_truth_layer_fact(
    ri: AIRealityCheckInput,
) -> bool:
    """Return True if at least one of the four fact groups
    (``evidence_bundle_facts``, ``market_facts``,
    ``system_behavior_facts``, ``outcome_facts``) is
    non-empty.
    """

    return bool(
        ri.evidence_bundle_facts
        or ri.market_facts
        or ri.system_behavior_facts
        or ri.outcome_facts
    )


def _claim_text_references_truth_fields(
    ri: AIRealityCheckInput,
) -> bool:
    """Return True if the claim has at least one
    ``truth_layer_fields_used`` entry. Used as a coarse
    signal that the claim is computable rather than
    free-form narrative.
    """

    return bool(ri.truth_layer_fields_used)


# ---------------------------------------------------------------------------
# Authority-level mapping
# ---------------------------------------------------------------------------
def _authority_for(
    status: AIRealityCheckStatus,
    *,
    has_partial_warning: bool,
) -> AIRealityCheckAuthorityLevel:
    if status is AIRealityCheckStatus.SUPPORTED:
        return AIRealityCheckAuthorityLevel.SUPPORTED_INTELLIGENCE
    if status is AIRealityCheckStatus.PARTIALLY_SUPPORTED:
        if has_partial_warning:
            return AIRealityCheckAuthorityLevel.UNSUPPORTED_INTELLIGENCE
        return AIRealityCheckAuthorityLevel.SUPPORTED_INTELLIGENCE
    if status is AIRealityCheckStatus.INSUFFICIENT_EVIDENCE:
        return AIRealityCheckAuthorityLevel.DEGRADED_NO_EVIDENCE
    # CONTRADICTED / REJECTED_LOOKAHEAD /
    # REJECTED_UNVERIFIABLE_NARRATIVE.
    return AIRealityCheckAuthorityLevel.REJECTED_BY_REALITY_CHECK


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class AIRealityCheckEngine:
    """Pure, deterministic Reality Check engine.

    The engine:

      - never calls an LLM / DeepSeek;
      - never opens a network socket;
      - never reads or carries API secrets;
      - never reads private exchange / account state;
      - never reads previous AI answers, chat history, or
        operator messages;
      - never produces a trade decision;
      - never produces a runtime-config patch;
      - never alters Risk / Execution / Exchange / Telegram /
        Config surfaces.

    The maximum authority any claim can reach is
    :attr:`AIRealityCheckAuthorityLevel.SUPPORTED_INTELLIGENCE`,
    which is *commentary substrate* only. The Risk Engine
    remains the single trade-decision gate.
    """

    def __init__(
        self,
        *,
        source_phase: str | None = None,
    ) -> None:
        self._source_phase = (
            str(source_phase)
            if source_phase
            else AI_REALITY_CHECK_SOURCE_PHASE
        )

    @property
    def source_phase(self) -> str:
        return self._source_phase

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def check(
        self,
        claim: AIRealityCheckInput | Mapping[str, Any],
    ) -> AIRealityCheckResult:
        ri = _coerce_input(claim)
        return self._check_one(ri)

    def check_many(
        self,
        claims: Iterable[
            AIRealityCheckInput | Mapping[str, Any]
        ]
        | None,
    ) -> tuple[AIRealityCheckResult, ...]:
        if claims is None:
            return ()
        return tuple(self.check(c) for c in claims)

    # ------------------------------------------------------------------
    # Per-claim verification
    # ------------------------------------------------------------------
    def _check_one(
        self, ri: AIRealityCheckInput
    ) -> AIRealityCheckResult:
        warnings: list[str] = []
        categories: list[AIRealityCheckCategory] = []
        supporting: list[str] = []
        contradicting: list[str] = []

        confidence_raw = ri.confidence_raw

        # ------------------------------------------------------------------
        # 1. Lookahead Guard (always run first)
        # ------------------------------------------------------------------
        categories.append(AIRealityCheckCategory.LOOKAHEAD_GUARD)
        violated, reasons = _is_lookahead_violated(
            ri.lookahead_policy
        )
        if violated:
            for r in reasons:
                warnings.append(f"lookahead_violation:{r}")
            return self._build_result(
                ri,
                status=AIRealityCheckStatus.REJECTED_LOOKAHEAD,
                categories=categories,
                supporting=supporting,
                contradicting=contradicting,
                warnings=warnings,
                degradation_reason=(
                    "lookahead_policy_violated:" + ",".join(reasons)
                ),
                confidence_reality_checked=0.0
                if confidence_raw is not None
                else None,
                has_partial_warning=False,
            )

        # ------------------------------------------------------------------
        # 2. Narrative Pollution Guard
        # ------------------------------------------------------------------
        # The narrative guard runs BEFORE the insufficient-
        # evidence check so a claim that smuggles
        # unverifiable narrative ("smart money is definitely
        # entering") with no computable backing is rejected
        # as REJECTED_UNVERIFIABLE_NARRATIVE rather than the
        # more lenient INSUFFICIENT_EVIDENCE. A narrative
        # phrase paired with computable backing
        # (truth_layer_fields_used, market / system-behavior
        # / outcome facts) is recorded as a warning and
        # processed normally.
        categories.append(
            AIRealityCheckCategory.NARRATIVE_POLLUTION_GUARD
        )
        has_narrative, frag = _matches_any_fragment(
            ri.claim_text, _UNVERIFIABLE_NARRATIVE_FRAGMENTS
        )
        has_computable_backing = (
            _claim_text_references_truth_fields(ri)
            or bool(ri.market_facts)
            or bool(ri.system_behavior_facts)
            or bool(ri.outcome_facts)
        )
        if has_narrative and not has_computable_backing:
            warnings.append(
                f"unverifiable_narrative_fragment:{frag}"
            )
            return self._build_result(
                ri,
                status=(
                    AIRealityCheckStatus
                    .REJECTED_UNVERIFIABLE_NARRATIVE
                ),
                categories=categories,
                supporting=supporting,
                contradicting=contradicting,
                warnings=warnings,
                degradation_reason=(
                    "unverifiable_narrative_without_facts"
                ),
                confidence_reality_checked=(
                    0.0 if confidence_raw is not None else None
                ),
                has_partial_warning=False,
            )
        if has_narrative and has_computable_backing:
            warnings.append(
                "narrative_phrase_present_but_facts_supplied"
            )

        # ------------------------------------------------------------------
        # 3. Statistical Verification (evidence_refs +
        #    evidence_bundle_facts)
        # ------------------------------------------------------------------
        categories.append(
            AIRealityCheckCategory.STATISTICAL_VERIFICATION
        )
        no_refs = not ri.evidence_refs
        no_facts = not _has_any_truth_layer_fact(ri)

        if no_refs or no_facts:
            if no_refs:
                warnings.append("missing_evidence_refs")
            if no_facts:
                warnings.append("missing_evidence_bundle_facts")
            return self._build_result(
                ri,
                status=AIRealityCheckStatus.INSUFFICIENT_EVIDENCE,
                categories=categories,
                supporting=supporting,
                contradicting=contradicting,
                warnings=warnings,
                degradation_reason="insufficient_evidence",
                confidence_reality_checked=(
                    0.0 if confidence_raw is not None else None
                ),
                has_partial_warning=False,
            )

        # ------------------------------------------------------------------
        # 4. Contradiction Detection +
        #    Microstructure Validation +
        #    Adversarial Evidence Check
        # ------------------------------------------------------------------
        categories.append(
            AIRealityCheckCategory.CONTRADICTION_DETECTION
        )
        categories.append(
            AIRealityCheckCategory.MICROSTRUCTURE_VALIDATION
        )
        categories.append(
            AIRealityCheckCategory.ADVERSARIAL_EVIDENCE_CHECK
        )

        contradiction_hits = _detect_contradictions(ri)
        is_expansion_claim, _ = _matches_any_fragment(
            ri.claim_text, _EXPANSION_FRAGMENTS
        )

        if contradiction_hits:
            for hit in contradiction_hits:
                warnings.append(f"contradiction_signal:{hit}")
            # Use the cited evidence_refs as the
            # "contradicting" axis from the claim's own
            # citations - the cited evidence is what the
            # contradiction was found against.
            for ref in ri.evidence_refs:
                if ref not in contradicting:
                    contradicting.append(ref)

            if is_expansion_claim:
                # Strong contradiction: an expansion thesis
                # while microstructure is contracting.
                return self._build_result(
                    ri,
                    status=AIRealityCheckStatus.CONTRADICTED,
                    categories=categories,
                    supporting=supporting,
                    contradicting=contradicting,
                    warnings=warnings,
                    degradation_reason=(
                        "expansion_claim_contradicted_by_facts"
                    ),
                    confidence_reality_checked=(
                        0.0
                        if confidence_raw is not None
                        else None
                    ),
                    has_partial_warning=False,
                )

            # Non-expansion claim with at least one
            # contradicting microstructure signal: demote to
            # PARTIALLY_SUPPORTED with contradiction warning.
            partial_conf = self._calibrate_confidence(
                confidence_raw, factor=0.5
            )
            for ref in ri.evidence_refs:
                if ref not in supporting:
                    supporting.append(ref)
            categories.append(
                AIRealityCheckCategory.CONFIDENCE_CALIBRATION
            )
            return self._build_result(
                ri,
                status=(
                    AIRealityCheckStatus.PARTIALLY_SUPPORTED
                ),
                categories=categories,
                supporting=supporting,
                contradicting=contradicting,
                warnings=warnings,
                degradation_reason=(
                    "partial_support_with_contradiction_signal"
                ),
                confidence_reality_checked=partial_conf,
                has_partial_warning=True,
            )

        # ------------------------------------------------------------------
        # 5. Supported / Partially Supported (no contradiction)
        # ------------------------------------------------------------------
        categories.append(
            AIRealityCheckCategory.CONFIDENCE_CALIBRATION
        )

        # Treat the cited evidence_refs as the supporting
        # axis when at least one of the explicit fact groups
        # is non-empty.
        for ref in ri.evidence_refs:
            if ref not in supporting:
                supporting.append(ref)

        # Heuristic for partial support:
        #   - claim has truth_layer_fields_used referencing
        #     fact groups that are EMPTY in the input, OR
        #   - market_facts / system_behavior_facts /
        #     outcome_facts are all empty (only
        #     evidence_bundle_facts supplied).
        partial = False
        if ri.truth_layer_fields_used:
            for ref in ri.truth_layer_fields_used:
                root = ref.split(".", 1)[0]
                bag = {
                    "market_facts": ri.market_facts,
                    "system_behavior_facts": (
                        ri.system_behavior_facts
                    ),
                    "outcome_facts": ri.outcome_facts,
                    "evidence_bundle_facts": (
                        ri.evidence_bundle_facts
                    ),
                }.get(root)
                if bag is None or not bag:
                    partial = True
                    warnings.append(
                        f"truth_field_group_empty:{root}"
                    )

        if not (
            ri.market_facts
            or ri.system_behavior_facts
            or ri.outcome_facts
        ):
            partial = True
            warnings.append(
                "no_market_or_system_behavior_or_outcome_facts"
            )

        if partial:
            partial_conf = self._calibrate_confidence(
                confidence_raw, factor=0.7
            )
            return self._build_result(
                ri,
                status=(
                    AIRealityCheckStatus.PARTIALLY_SUPPORTED
                ),
                categories=categories,
                supporting=supporting,
                contradicting=contradicting,
                warnings=warnings,
                degradation_reason=(
                    "partial_support_without_full_fact_coverage"
                ),
                confidence_reality_checked=partial_conf,
                has_partial_warning=False,
            )

        # Fully supported.
        full_conf = self._calibrate_confidence(
            confidence_raw, factor=1.0
        )
        return self._build_result(
            ri,
            status=AIRealityCheckStatus.SUPPORTED,
            categories=categories,
            supporting=supporting,
            contradicting=contradicting,
            warnings=warnings,
            degradation_reason=None,
            confidence_reality_checked=full_conf,
            has_partial_warning=False,
        )

    # ------------------------------------------------------------------
    # Confidence calibration
    # ------------------------------------------------------------------
    @staticmethod
    def _calibrate_confidence(
        confidence_raw: float | None, *, factor: float
    ) -> float | None:
        if confidence_raw is None:
            return None
        try:
            raw = float(confidence_raw)
        except (TypeError, ValueError):
            return None
        # Clamp the input to [0.0, 1.0] so a producer cannot
        # smuggle confidence > 1.0.
        if raw < 0.0:
            raw = 0.0
        if raw > 1.0:
            raw = 1.0
        # ``factor`` is in [0.0, 1.0]; the calibrated value
        # is therefore guaranteed <= the clamped raw value.
        if factor < 0.0:
            factor = 0.0
        if factor > 1.0:
            factor = 1.0
        return raw * factor

    # ------------------------------------------------------------------
    # Result construction (single boundary so every path
    # runs the recursive forbidden-fields guard)
    # ------------------------------------------------------------------
    def _build_result(
        self,
        ri: AIRealityCheckInput,
        *,
        status: AIRealityCheckStatus,
        categories: list[AIRealityCheckCategory],
        supporting: list[str],
        contradicting: list[str],
        warnings: list[str],
        degradation_reason: str | None,
        confidence_reality_checked: float | None,
        has_partial_warning: bool,
    ) -> AIRealityCheckResult:
        authority = _authority_for(
            status, has_partial_warning=has_partial_warning
        )
        # Defensive: confidence_reality_checked MUST be <=
        # confidence_raw whenever both are set.
        if (
            ri.confidence_raw is not None
            and confidence_reality_checked is not None
            and confidence_reality_checked > ri.confidence_raw
        ):
            confidence_reality_checked = float(ri.confidence_raw)
        result = AIRealityCheckResult(
            claim_id=ri.claim_id,
            status=status,
            categories_checked=tuple(categories),
            supporting_evidence_refs=tuple(supporting),
            contradicting_evidence_refs=tuple(contradicting),
            confidence_raw=ri.confidence_raw,
            confidence_reality_checked=confidence_reality_checked,
            authority_level_after_check=authority,
            degradation_reason=degradation_reason,
            warnings=tuple(warnings),
        )
        # Run the recursive forbidden-fields guard at the
        # serialisation boundary so a forbidden key smuggled
        # via a downstream override is caught here.
        _ = result.to_dict()
        return result


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------
def reality_check_claim(
    claim: AIRealityCheckInput | Mapping[str, Any],
) -> AIRealityCheckResult:
    """Convenience wrapper around
    :class:`AIRealityCheckEngine`.

    Equivalent to::

        AIRealityCheckEngine().check(claim)
    """

    return AIRealityCheckEngine().check(claim)


__all__ = [
    "AI_REALITY_CHECK_SCHEMA_VERSION",
    "AI_REALITY_CHECK_SOURCE_MODULE",
    "AI_REALITY_CHECK_SOURCE_PHASE",
    "AIRealityCheckAuthorityLevel",
    "AIRealityCheckCategory",
    "AIRealityCheckEngine",
    "AIRealityCheckInput",
    "AIRealityCheckResult",
    "AIRealityCheckStatus",
    "FORBIDDEN_REALITY_CHECK_FIELDS",
    "reality_check_claim",
]
