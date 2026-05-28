"""Phase AI-2 - Truth Layer / AI Evidence Citation Contract v0.

The AI Layer's *claim-level* citation contract. Every later AI /
DeepSeek / LLM call MUST emit ``AIClaim`` objects whose evidence
is cited via ``evidence_refs`` pointing at the Truth Layer (the
substrate built by Phase AI-1 :mod:`app.ai.evidence_bundle`).

This module:

  - is **paper / read-only** (it never produces direction,
    sizing, leverage, stop, target, risk-budget, or any
    runtime-config-patch field; the recursive
    :func:`_assert_no_forbidden_fields` guard refuses to emit
    such a key at any nesting depth);
  - is **stateless** (the validator carries no instance state
    between calls; it never reads previous AI answers, chat
    history, ``listenKey`` payloads, signed-endpoint payloads,
    or any private exchange / account state);
  - **never** calls an LLM / DeepSeek;
  - **never** opens a network socket;
  - **never** invents a missing ``evidence_refs`` entry - claims
    without ``evidence_refs`` are demoted to
    :attr:`AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE`, never
    silently rewritten;
  - **never** authorises a trade decision - the
    :class:`AIClaimAuthorityLevel` enum has NO trade-authority
    member; the maximum authority any claim can reach is
    :attr:`AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE`, which
    is *commentary substrate* only.

The module enforces the four AI root constraints from
``docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md``:

  1. **Responsibility Isolation** - claims and result payloads
     are scrubbed of every forbidden trade-action /
     runtime-config-patch field via the recursive
     :func:`_assert_no_forbidden_fields` guard imported from
     :mod:`app.ai.evidence_bundle`.
  2. **Stateless Inference** - each
     :meth:`AIClaimCitationValidator.validate` call is
     independent; no instance state is mutated.
  3. **Hard Rule Anchoring** - a claim with no
     ``evidence_refs`` is demoted to
     :attr:`AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE`; a
     claim whose ``evidence_refs`` do not match the supported
     citation grammar is rejected
     (:attr:`AIClaimAuthorityLevel.REJECTED_INVALID_EVIDENCE`)
     in strict mode, or demoted in non-strict mode. **No
     evidence_refs => no accepted AI conclusion.**
  4. **Feedback Isolation** - every emitted result re-pins
     ``ai_output_is_commentary_only=True``,
     ``ai_output_can_be_training_label=False``,
     ``phase_12_forbidden=True``, ``auto_tuning_allowed=False``
     so AI text can never become a training label or a runtime
     fact.

This module is paper / report / evidence-only. It does NOT
authorise live trading, does NOT authorise auto-tuning, does
NOT call DeepSeek / any LLM, and does NOT open Phase 12.

Phase AI-2 only ships the citation contract: schema, validator,
authority levels, supported evidence-ref grammar, tests, docs.
The Reality Check Layer that cross-verifies an AI claim against
the Phase AI-1 Evidence Bundle is a **later, separately gated**
phase. This module never reaches into the bundle to evaluate
claim *truth*; it only validates the *citation contract*.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.ai.evidence_bundle import (
    FORBIDDEN_AI_OUTPUT_FIELDS,
    _assert_no_forbidden_fields,
)


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------
AI_CLAIM_CONTRACT_SOURCE_PHASE: str = "phase_ai_2"
AI_CLAIM_CONTRACT_SOURCE_MODULE: str = "ai_claim_citation_contract"
AI_CLAIM_CONTRACT_SCHEMA_VERSION: str = "v0"


# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------
class AIClaimAuthorityLevel(str, Enum):
    """Closed authority-level vocabulary for one AI claim.

    No member of this enum grants *trade authority*. The
    maximum authority any claim can reach is
    :attr:`SUPPORTED_INTELLIGENCE`, which is *commentary
    substrate* only - it does NOT direct the Risk Engine, the
    Execution FSM, the Capital Flow Engine, the Reconciler, or
    any other trade-authority surface. The Risk Engine remains
    the single trade-decision gate.
    """

    #: Producer flagged the claim as commentary; it stays
    #: commentary regardless of how strong its citations look.
    COMMENTARY_ONLY = "COMMENTARY_ONLY"

    #: The claim cited at least one well-formed Truth-Layer
    #: evidence reference and passed every schema check. The
    #: claim is *commentary substrate*, not trade authority.
    SUPPORTED_INTELLIGENCE = "SUPPORTED_INTELLIGENCE"

    #: Reserved for the later Reality Check Layer: a claim that
    #: passed schema and citation grammar but could not be
    #: positively cross-verified against the Truth Layer cited
    #: in the Evidence Bundle. The validator in this v0 module
    #: never produces this level on its own; it is preserved in
    #: the closed vocabulary so consumers can ship without an
    #: enum migration when the Reality Check Layer lands.
    UNSUPPORTED_INTELLIGENCE = "UNSUPPORTED_INTELLIGENCE"

    #: The claim supplied no ``evidence_refs`` at all (or every
    #: ``evidence_refs`` entry was filtered out in non-strict
    #: mode). The claim is demoted, never silently rewritten.
    DEGRADED_NO_EVIDENCE = "DEGRADED_NO_EVIDENCE"

    #: The claim violated the citation schema (unknown
    #: ``claim_type``, missing ``claim_id`` / ``claim_text``,
    #: forbidden output field smuggled into a payload).
    REJECTED_BY_SCHEMA = "REJECTED_BY_SCHEMA"

    #: At least one ``evidence_refs`` entry did not match the
    #: supported citation grammar AND the validator was running
    #: in strict mode.
    REJECTED_INVALID_EVIDENCE = "REJECTED_INVALID_EVIDENCE"


class AIClaimType(str, Enum):
    """Closed claim-type vocabulary for one AI claim.

    Adding a new claim type is a deliberate code change AND a
    brief amendment. Claim types are descriptive labels for
    *what kind of commentary* the claim is - they NEVER carry
    direction / sizing / leverage / stop / target / risk-budget
    semantics.
    """

    REGIME = "REGIME"
    NARRATIVE = "NARRATIVE"
    LIQUIDITY = "LIQUIDITY"
    RISK = "RISK"
    COVERAGE = "COVERAGE"
    OUTCOME = "OUTCOME"
    CONTRADICTION = "CONTRADICTION"
    REPLAY_SUMMARY = "REPLAY_SUMMARY"
    REFLECTION_SUMMARY = "REFLECTION_SUMMARY"
    EVIDENCE_QUALITY = "EVIDENCE_QUALITY"


# ---------------------------------------------------------------------------
# Supported evidence-ref grammar
# ---------------------------------------------------------------------------
#: Each supported citation prefix maps to a compiled regex. The
#: ``str`` form is exposed via :data:`SUPPORTED_EVIDENCE_REF_FORMATS`
#: so consumers can ship documentation / error messages without
#: cracking the compiled regex.
_EVIDENCE_REF_PATTERNS: dict[str, re.Pattern[str]] = {
    # event:<EVENT_TYPE>:<event_id>
    # EVENT_TYPE is uppercase identifier with underscores.
    # event_id is alphanumeric / underscore / dash.
    "event": re.compile(r"^event:[A-Z][A-Z0-9_]*:[A-Za-z0-9_\-]+$"),
    # symbol:<SYMBOL>
    # SYMBOL is uppercase alphanumeric (e.g. RAVEUSDT, BTCUSDT).
    "symbol": re.compile(r"^symbol:[A-Z][A-Z0-9]*$"),
    # opportunity:<opportunity_id>
    "opportunity": re.compile(r"^opportunity:[A-Za-z0-9_\-]+$"),
    # scan_batch:<scan_batch_id>
    "scan_batch": re.compile(r"^scan_batch:[A-Za-z0-9_\-]+$"),
    # metric:<metric_name>:<window>
    # metric_name and window are alphanumeric / underscore /
    # dash (e.g. metric:capture_recall_rate:60d).
    "metric": re.compile(
        r"^metric:[A-Za-z0-9_\-]+:[A-Za-z0-9_\-]+$"
    ),
    # report:<report_id>
    "report": re.compile(r"^report:[A-Za-z0-9_\-]+$"),
}


#: Human-readable supported citation grammar. Re-exported for
#: documentation, error messages, and downstream consumers.
SUPPORTED_EVIDENCE_REF_FORMATS: tuple[str, ...] = (
    "event:<EVENT_TYPE>:<event_id>",
    "symbol:<SYMBOL>",
    "opportunity:<opportunity_id>",
    "scan_batch:<scan_batch_id>",
    "metric:<metric_name>:<window>",
    "report:<report_id>",
)


#: Sorted tuple of supported citation prefixes. Useful for
#: programmatic checks and operator-facing error messages.
SUPPORTED_EVIDENCE_REF_PREFIXES: tuple[str, ...] = tuple(
    sorted(_EVIDENCE_REF_PATTERNS.keys())
)


def _is_valid_evidence_ref(ref: str) -> bool:
    """Return True if ``ref`` matches one of the supported
    citation patterns. The check is total - an empty string,
    a non-string, or a free-form sentence all return False.
    """

    if not isinstance(ref, str):
        return False
    text = ref.strip()
    if not text or ":" not in text:
        return False
    prefix, _, _ = text.partition(":")
    pattern = _EVIDENCE_REF_PATTERNS.get(prefix)
    if pattern is None:
        return False
    return bool(pattern.match(text))


# ---------------------------------------------------------------------------
# Forbidden output fields (re-exported from Phase AI-1)
# ---------------------------------------------------------------------------
#: Re-exported so consumers of the citation contract module do
#: not need to import :mod:`app.ai.evidence_bundle` directly.
#: Mirrors the brief's "additive" forbidden list and the AI
#: Layer Engineering Spec §3.
FORBIDDEN_CLAIM_FIELDS: frozenset[str] = FORBIDDEN_AI_OUTPUT_FIELDS


# ---------------------------------------------------------------------------
# Claim records
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AIClaimInput:
    """Caller-supplied claim awaiting validation.

    The producer of an AI claim MUST construct one of these
    (or an equivalent ``Mapping``) and hand it to the
    :class:`AIClaimCitationValidator`. The validator never
    invents missing fields - in particular it never invents
    missing ``evidence_refs``.

    ``intended_authority_level`` is the *intent* the producer
    declares for the claim. The validator may downgrade it
    (e.g. demote to ``DEGRADED_NO_EVIDENCE`` when
    ``evidence_refs`` is empty) but never *upgrade* it past
    ``SUPPORTED_INTELLIGENCE``. A producer can opt the claim
    into commentary-only authority by setting
    ``intended_authority_level=COMMENTARY_ONLY``; in that case
    the validator preserves the level even if the citations
    are well-formed.
    """

    claim_id: str
    claim_type: AIClaimType | str
    claim_text: str
    evidence_refs: tuple[str, ...] = ()
    truth_layer_fields_used: tuple[str, ...] = ()
    confidence_raw: float | None = None
    intended_authority_level: AIClaimAuthorityLevel = (
        AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE
    )
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class AIClaim:
    """A claim that has been processed by the validator.

    Every accepted / degraded / rejected claim is represented
    by one of these. The ``content``-shaped fields
    (``claim_text``, ``evidence_refs``,
    ``truth_layer_fields_used``) are preserved verbatim - the
    validator NEVER invents a missing ``evidence_refs`` entry,
    NEVER paraphrases ``claim_text``, NEVER fabricates a
    ``truth_layer_fields_used`` entry.
    """

    claim_id: str
    claim_type: str
    claim_text: str
    evidence_refs: tuple[str, ...]
    truth_layer_fields_used: tuple[str, ...]
    authority_level: AIClaimAuthorityLevel
    confidence_raw: float | None
    warnings: tuple[str, ...]
    schema_version: str = AI_CLAIM_CONTRACT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable payload for this claim.

        The recursive forbidden-fields guard refuses to emit a
        payload carrying a trade-action / runtime-config-patch
        key.
        """

        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "claim_id": str(self.claim_id),
            "claim_type": str(self.claim_type),
            "claim_text": str(self.claim_text),
            "evidence_refs": list(self.evidence_refs),
            "truth_layer_fields_used": list(
                self.truth_layer_fields_used
            ),
            "authority_level": self.authority_level.value,
            "confidence_raw": (
                float(self.confidence_raw)
                if self.confidence_raw is not None
                else None
            ),
            "warnings": list(self.warnings),
        }
        _assert_no_forbidden_fields(payload, context="AIClaim.to_dict")
        return payload


# ---------------------------------------------------------------------------
# Result record
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AIClaimCitationResult:
    """Aggregate outcome of validating a batch of AI claims.

    Counts:

      - ``accepted_claim_count`` - claims whose final
        :class:`AIClaimAuthorityLevel` is
        :attr:`AIClaimAuthorityLevel.COMMENTARY_ONLY` or
        :attr:`AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE`.
      - ``degraded_claim_count`` - claims whose final
        :class:`AIClaimAuthorityLevel` is
        :attr:`AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE` or
        :attr:`AIClaimAuthorityLevel.UNSUPPORTED_INTELLIGENCE`.
      - ``rejected_claim_count`` - claims whose final
        :class:`AIClaimAuthorityLevel` is
        :attr:`AIClaimAuthorityLevel.REJECTED_BY_SCHEMA` or
        :attr:`AIClaimAuthorityLevel.REJECTED_INVALID_EVIDENCE`.
      - ``missing_evidence_count`` - claims whose
        ``evidence_refs`` was empty on intake.
      - ``invalid_evidence_count`` - claims that supplied at
        least one ``evidence_refs`` entry that did not match
        the supported citation grammar.

    The result is JSON-serializable via :meth:`to_dict`. Every
    serialised payload re-pins the project-wide invariants
    (``mode=paper``, ``live_trading=False``,
    ``ai_output_is_commentary_only=True``,
    ``ai_output_can_be_training_label=False``,
    ``phase_12_forbidden=True``, ``auto_tuning_allowed=False``).
    """

    claims: tuple[AIClaim, ...]
    accepted_claim_count: int
    degraded_claim_count: int
    rejected_claim_count: int
    missing_evidence_count: int
    invalid_evidence_count: int
    warnings: tuple[str, ...]
    strict: bool
    schema_version: str = AI_CLAIM_CONTRACT_SCHEMA_VERSION
    source_phase: str = AI_CLAIM_CONTRACT_SOURCE_PHASE
    source_module: str = AI_CLAIM_CONTRACT_SOURCE_MODULE
    # Hard-pinned root-constraint flags. Re-pinned at every
    # ``to_dict`` boundary even if the dataclass field is
    # somehow flipped.
    ai_output_is_commentary_only: bool = True
    ai_output_can_be_training_label: bool = False
    phase_12_forbidden: bool = True
    auto_tuning_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable payload for this result.

        The recursive forbidden-fields guard refuses to emit a
        payload carrying a trade-action / runtime-config-patch
        key at any nesting depth.
        """

        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "source_module": self.source_module,
            "strict": bool(self.strict),
            "claims": [c.to_dict() for c in self.claims],
            "accepted_claim_count": int(self.accepted_claim_count),
            "degraded_claim_count": int(self.degraded_claim_count),
            "rejected_claim_count": int(self.rejected_claim_count),
            "missing_evidence_count": int(self.missing_evidence_count),
            "invalid_evidence_count": int(self.invalid_evidence_count),
            "warnings": list(self.warnings),
            "supported_evidence_ref_formats": list(
                SUPPORTED_EVIDENCE_REF_FORMATS
            ),
            "supported_evidence_ref_prefixes": list(
                SUPPORTED_EVIDENCE_REF_PREFIXES
            ),
            "forbidden_fields": sorted(FORBIDDEN_CLAIM_FIELDS),
            # Hard-pinned root-constraint flags - these MUST
            # NEVER be relaxed by a downstream serialiser.
            "ai_output_is_commentary_only": True,
            "ai_output_can_be_training_label": False,
            "phase_12_forbidden": True,
            "auto_tuning_allowed": False,
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
            payload, context="AIClaimCitationResult.to_dict"
        )
        return payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _coerce_str_tuple(value: Any) -> tuple[str, ...]:
    """Coerce ``value`` into a tuple of stripped strings,
    preserving input order. ``None`` becomes ``()``. The
    function NEVER invents new entries - it only filters out
    empty / None entries.
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


def _coerce_claim_input(
    raw: AIClaimInput | Mapping[str, Any],
    *,
    claim_index: int,
) -> AIClaimInput:
    if isinstance(raw, AIClaimInput):
        return raw

    if not isinstance(raw, Mapping):
        raise TypeError(
            "AIClaimCitationValidator expects each claim to be "
            "an AIClaimInput or a Mapping; got "
            f"{type(raw).__name__} at index {claim_index}."
        )

    claim_id = str(
        raw.get("claim_id", f"claim_{claim_index}")
    ).strip()
    claim_type_raw = raw.get("claim_type", "")
    claim_text = str(raw.get("claim_text", "")).strip()
    evidence_refs = _coerce_str_tuple(raw.get("evidence_refs"))
    truth_layer_fields_used = _coerce_str_tuple(
        raw.get("truth_layer_fields_used")
    )
    confidence_raw_value = raw.get("confidence_raw")
    if confidence_raw_value is None:
        confidence_raw: float | None = None
    else:
        try:
            confidence_raw = float(confidence_raw_value)
        except (TypeError, ValueError):
            confidence_raw = None

    intended_raw = raw.get(
        "intended_authority_level",
        AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE,
    )
    if isinstance(intended_raw, AIClaimAuthorityLevel):
        intended = intended_raw
    else:
        try:
            intended = AIClaimAuthorityLevel(str(intended_raw))
        except ValueError:
            # Unknown intended authority level is itself a
            # schema violation - the validator surfaces it via
            # REJECTED_BY_SCHEMA further down the pipeline.
            intended = AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE

    warnings = _coerce_str_tuple(raw.get("warnings"))

    return AIClaimInput(
        claim_id=claim_id,
        claim_type=claim_type_raw,
        claim_text=claim_text,
        evidence_refs=evidence_refs,
        truth_layer_fields_used=truth_layer_fields_used,
        confidence_raw=confidence_raw,
        intended_authority_level=intended,
        warnings=warnings,
    )


def _resolve_claim_type(
    raw: AIClaimType | str,
) -> tuple[str, bool]:
    """Resolve the producer-supplied claim_type into a string
    label plus a "is-known-vocabulary" flag.
    """

    if isinstance(raw, AIClaimType):
        return raw.value, True
    text = str(raw).strip()
    if not text:
        return "", False
    try:
        return AIClaimType(text).value, True
    except ValueError:
        return text, False


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------
class AIClaimCitationValidator:
    """Pure, deterministic validator for the AI claim citation
    contract.

    The validator:

      - validates every claim has a known
        :class:`AIClaimType` (otherwise rejects via
        :attr:`AIClaimAuthorityLevel.REJECTED_BY_SCHEMA`);
      - validates every ``evidence_refs`` entry against the
        supported citation grammar
        (:data:`SUPPORTED_EVIDENCE_REF_FORMATS`);
      - degrades a claim that supplies no ``evidence_refs`` to
        :attr:`AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE`,
        never silently rewriting it;
      - in **strict** mode rejects a claim with at least one
        invalid ``evidence_refs`` entry via
        :attr:`AIClaimAuthorityLevel.REJECTED_INVALID_EVIDENCE`;
      - in **non-strict** mode filters out invalid
        ``evidence_refs`` entries and demotes the claim if no
        valid entries remain;
      - never invents a missing ``evidence_refs`` entry;
      - never paraphrases ``claim_text``;
      - never fabricates a ``truth_layer_fields_used`` entry;
      - never calls an LLM / DeepSeek;
      - never opens a network socket;
      - never reads or carries API secrets;
      - never reads previous AI answers or chat history;
      - never reads private exchange / account state;
      - never authorises a trade decision.

    The maximum authority any claim can reach is
    :attr:`AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE`, which
    is *commentary substrate* only. The Risk Engine remains
    the single trade-decision gate.
    """

    def __init__(
        self,
        *,
        strict: bool = True,
        source_phase: str | None = None,
    ) -> None:
        self._strict = bool(strict)
        self._source_phase = (
            str(source_phase)
            if source_phase
            else AI_CLAIM_CONTRACT_SOURCE_PHASE
        )

    @property
    def strict(self) -> bool:
        return self._strict

    @property
    def source_phase(self) -> str:
        return self._source_phase

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def validate(
        self,
        claims: Iterable[AIClaimInput | Mapping[str, Any]] | None,
    ) -> AIClaimCitationResult:
        """Validate ``claims`` and return an
        :class:`AIClaimCitationResult` summarising the outcome.
        """

        if claims is None:
            claims_iter: list[AIClaimInput | Mapping[str, Any]] = []
        else:
            claims_iter = list(claims)

        validated: list[AIClaim] = []
        result_warnings: list[str] = []

        accepted = 0
        degraded = 0
        rejected = 0
        missing_evidence = 0
        invalid_evidence = 0

        for index, raw in enumerate(claims_iter):
            normalised = _coerce_claim_input(raw, claim_index=index)
            claim, level = self._validate_one(normalised)
            validated.append(claim)

            # Aggregate counts.
            if level in (
                AIClaimAuthorityLevel.COMMENTARY_ONLY,
                AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE,
            ):
                accepted += 1
            elif level in (
                AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE,
                AIClaimAuthorityLevel.UNSUPPORTED_INTELLIGENCE,
            ):
                degraded += 1
            else:
                rejected += 1

            # Aggregate warnings + reason counters.
            if "missing_evidence_refs" in claim.warnings:
                missing_evidence += 1
                result_warnings.append(
                    f"missing_evidence_refs:{claim.claim_id}"
                )
            if any(
                w.startswith("invalid_evidence_ref:")
                for w in claim.warnings
            ):
                invalid_evidence += 1
                result_warnings.append(
                    f"invalid_evidence_refs:{claim.claim_id}"
                )
            if "rejected_by_schema" in claim.warnings:
                result_warnings.append(
                    f"rejected_by_schema:{claim.claim_id}"
                )

        return AIClaimCitationResult(
            claims=tuple(validated),
            accepted_claim_count=accepted,
            degraded_claim_count=degraded,
            rejected_claim_count=rejected,
            missing_evidence_count=missing_evidence,
            invalid_evidence_count=invalid_evidence,
            warnings=tuple(result_warnings),
            strict=self._strict,
        )

    # ------------------------------------------------------------------
    # Per-claim validation
    # ------------------------------------------------------------------
    def _validate_one(
        self, claim_input: AIClaimInput
    ) -> tuple[AIClaim, AIClaimAuthorityLevel]:
        warnings: list[str] = list(claim_input.warnings)

        claim_id = (
            claim_input.claim_id.strip()
            if claim_input.claim_id
            else ""
        )

        # ------------------------------------------------------------------
        # 0. Schema-level checks
        # ------------------------------------------------------------------
        claim_type_text, claim_type_known = _resolve_claim_type(
            claim_input.claim_type
        )
        claim_text = claim_input.claim_text.strip()
        # Normalise evidence_refs / truth_layer_fields_used so
        # whitespace-only / empty entries are filtered before
        # validation (AIClaimInput dataclass instances may arrive
        # with such entries unfiltered). The validator NEVER
        # invents new entries - it only filters out blank ones.
        evidence_refs = _coerce_str_tuple(claim_input.evidence_refs)
        truth_fields = _coerce_str_tuple(
            claim_input.truth_layer_fields_used
        )

        # Forbidden output fields anywhere in the claim payload
        # mean the claim is rejected by schema. We do not
        # silently strip - a rejected claim is preserved verbatim
        # so the audit trail records exactly what the producer
        # tried to emit.
        forbidden_field_hit = _find_forbidden_field_in_claim(
            claim_input
        )
        if forbidden_field_hit is not None:
            warnings.append(
                f"forbidden_field_in_claim:{forbidden_field_hit}"
            )
            warnings.append("rejected_by_schema")
            level = AIClaimAuthorityLevel.REJECTED_BY_SCHEMA
            return (
                AIClaim(
                    claim_id=claim_id or f"claim_{id(claim_input)}",
                    claim_type=claim_type_text,
                    claim_text=claim_text,
                    evidence_refs=evidence_refs,
                    truth_layer_fields_used=truth_fields,
                    authority_level=level,
                    confidence_raw=claim_input.confidence_raw,
                    warnings=tuple(warnings),
                ),
                level,
            )

        if not claim_id or not claim_text or not claim_type_known:
            if not claim_id:
                warnings.append("missing_claim_id")
            if not claim_text:
                warnings.append("missing_claim_text")
            if not claim_type_known:
                warnings.append(
                    f"unknown_claim_type:{claim_type_text or '<empty>'}"
                )
            warnings.append("rejected_by_schema")
            level = AIClaimAuthorityLevel.REJECTED_BY_SCHEMA
            return (
                AIClaim(
                    claim_id=claim_id or f"claim_{id(claim_input)}",
                    claim_type=claim_type_text,
                    claim_text=claim_text,
                    evidence_refs=evidence_refs,
                    truth_layer_fields_used=truth_fields,
                    authority_level=level,
                    confidence_raw=claim_input.confidence_raw,
                    warnings=tuple(warnings),
                ),
                level,
            )

        # ------------------------------------------------------------------
        # 1. Evidence-citation checks
        # ------------------------------------------------------------------
        # Producer asked for COMMENTARY_ONLY: keep it that way.
        # Even if citations are well-formed, commentary-only
        # never escalates to SUPPORTED_INTELLIGENCE - the
        # producer has the final say in *down*-pinning the
        # authority.
        if (
            claim_input.intended_authority_level
            is AIClaimAuthorityLevel.COMMENTARY_ONLY
        ):
            level = AIClaimAuthorityLevel.COMMENTARY_ONLY
            # Still record any invalid-ref warning so the audit
            # trail is honest, but do not change the level.
            for ref in evidence_refs:
                if not _is_valid_evidence_ref(ref):
                    warnings.append(f"invalid_evidence_ref:{ref}")
            return (
                AIClaim(
                    claim_id=claim_id,
                    claim_type=claim_type_text,
                    claim_text=claim_text,
                    evidence_refs=evidence_refs,
                    truth_layer_fields_used=truth_fields,
                    authority_level=level,
                    confidence_raw=claim_input.confidence_raw,
                    warnings=tuple(warnings),
                ),
                level,
            )

        # Empty evidence_refs => DEGRADED_NO_EVIDENCE.
        if not evidence_refs:
            warnings.append("missing_evidence_refs")
            level = AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE
            return (
                AIClaim(
                    claim_id=claim_id,
                    claim_type=claim_type_text,
                    claim_text=claim_text,
                    evidence_refs=evidence_refs,
                    truth_layer_fields_used=truth_fields,
                    authority_level=level,
                    confidence_raw=claim_input.confidence_raw,
                    warnings=tuple(warnings),
                ),
                level,
            )

        # Per-ref validity check.
        valid_refs: list[str] = []
        for ref in evidence_refs:
            if _is_valid_evidence_ref(ref):
                valid_refs.append(ref)
            else:
                warnings.append(f"invalid_evidence_ref:{ref}")

        all_invalid = not valid_refs
        any_invalid = len(valid_refs) != len(evidence_refs)

        if any_invalid and self._strict:
            warnings.append("rejected_invalid_evidence_strict")
            level = AIClaimAuthorityLevel.REJECTED_INVALID_EVIDENCE
            # In strict mode we keep the original evidence_refs
            # tuple verbatim so the audit trail records exactly
            # what the producer attempted to cite.
            return (
                AIClaim(
                    claim_id=claim_id,
                    claim_type=claim_type_text,
                    claim_text=claim_text,
                    evidence_refs=evidence_refs,
                    truth_layer_fields_used=truth_fields,
                    authority_level=level,
                    confidence_raw=claim_input.confidence_raw,
                    warnings=tuple(warnings),
                ),
                level,
            )

        if all_invalid:
            # Non-strict + every ref invalid: demote to
            # DEGRADED_NO_EVIDENCE rather than reject. The
            # original evidence_refs tuple is preserved so the
            # audit trail records exactly what the producer
            # attempted to cite; the validator NEVER invents a
            # replacement.
            warnings.append("degraded_invalid_evidence_non_strict")
            level = AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE
            return (
                AIClaim(
                    claim_id=claim_id,
                    claim_type=claim_type_text,
                    claim_text=claim_text,
                    evidence_refs=evidence_refs,
                    truth_layer_fields_used=truth_fields,
                    authority_level=level,
                    confidence_raw=claim_input.confidence_raw,
                    warnings=tuple(warnings),
                ),
                level,
            )

        # Otherwise: at least one valid ref. In non-strict mode
        # with some invalid refs we keep the claim but record a
        # warning. The accepted authority level is
        # SUPPORTED_INTELLIGENCE.
        level = AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE
        return (
            AIClaim(
                claim_id=claim_id,
                claim_type=claim_type_text,
                claim_text=claim_text,
                evidence_refs=evidence_refs,
                truth_layer_fields_used=truth_fields,
                authority_level=level,
                confidence_raw=claim_input.confidence_raw,
                warnings=tuple(warnings),
            ),
            level,
        )


# ---------------------------------------------------------------------------
# Forbidden-field detection
# ---------------------------------------------------------------------------
def _find_forbidden_field_in_claim(
    claim_input: AIClaimInput,
) -> str | None:
    """Return the first forbidden field name detected anywhere
    in the claim payload, or ``None``.

    Detection is performed on:

      - ``claim_id`` exact match;
      - ``claim_type`` exact match;
      - any ``truth_layer_fields_used`` entry exact match;
      - any ``evidence_refs`` entry exact match;
      - the ``claim_text`` whole string exact match (we do
        NOT do substring scanning of free-form prose - only
        whole-string matches against forbidden field names so
        a legitimate narrative containing the word ``buy`` in
        a sentence is not rejected).
    """

    candidates: list[str] = [
        claim_input.claim_id,
        str(claim_input.claim_type),
        claim_input.claim_text,
    ]
    candidates.extend(claim_input.truth_layer_fields_used)
    candidates.extend(claim_input.evidence_refs)

    for value in candidates:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if text in FORBIDDEN_CLAIM_FIELDS:
            return text

    return None


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------
def validate_ai_claims(
    claims: Iterable[AIClaimInput | Mapping[str, Any]] | None,
    *,
    strict: bool = True,
) -> AIClaimCitationResult:
    """Convenience wrapper around
    :class:`AIClaimCitationValidator`.

    Equivalent to::

        AIClaimCitationValidator(strict=strict).validate(claims)
    """

    return AIClaimCitationValidator(strict=strict).validate(claims)


__all__ = [
    "AI_CLAIM_CONTRACT_SCHEMA_VERSION",
    "AI_CLAIM_CONTRACT_SOURCE_MODULE",
    "AI_CLAIM_CONTRACT_SOURCE_PHASE",
    "AIClaim",
    "AIClaimAuthorityLevel",
    "AIClaimCitationResult",
    "AIClaimCitationValidator",
    "AIClaimInput",
    "AIClaimType",
    "FORBIDDEN_CLAIM_FIELDS",
    "SUPPORTED_EVIDENCE_REF_FORMATS",
    "SUPPORTED_EVIDENCE_REF_PREFIXES",
    "validate_ai_claims",
]
