"""Phase AI-4 - AI Intelligence Output Schema v0.

The AI Layer's *only* allowed write surface for the Phase AI-4
DeepSeek Offline Sandbox. Every offline DeepSeek run must
serialise its result through this schema; nothing else may be
emitted as "AI intelligence". The schema:

  - is **paper / read-only** for the runtime (no member of the
    schema directs the Risk Engine, the Execution FSM, the
    Capital Flow Engine, the Reconciler, or any other
    trade-authority surface);
  - is **stateless** (the schema carries no chat history, no
    previous AI answer, no private account state, no API
    secret);
  - is **JSON-serializable** (``json.dumps(payload)`` succeeds
    without a custom encoder);
  - is **deterministic** (two builds from identical inputs
    produce identical bytes via :meth:`AIIntelligenceOutput.to_dict`);
  - **never** carries a forbidden trade-action /
    runtime-config-patch field at any nesting depth - the
    recursive :func:`_assert_no_forbidden_fields` guard from
    Phase AI-1 refuses to serialise such a payload;
  - **never** authorises live trading - the schema pins
    ``trade_authority=False`` /
    ``auto_tuning_allowed=False`` /
    ``phase_12_forbidden=True`` /
    ``stateless_inference=True`` /
    ``feedback_isolation=True`` at every ``to_dict()``
    boundary even if a downstream caller flips the dataclass
    field via ``object.__setattr__``.

The four AI root constraints from
``docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`` are enforced in
code AND in tests:

  1. **Responsibility Isolation** - claim and result payloads
     are scrubbed of every forbidden trade-action /
     runtime-config-patch field via the recursive
     :func:`_assert_no_forbidden_fields` guard imported from
     :mod:`app.ai.evidence_bundle`. The
     :func:`strip_forbidden_fields` helper records every
     stripped key in
     :attr:`AIIntelligenceOutput.forbidden_fields_stripped`
     so the audit trail is never silent.
  2. **Stateless Inference** - the schema preserves
     ``stateless_inference=True`` at every emission and
     never ships an ``ai_session_history`` /
     ``previous_ai_answer`` / ``chat_history`` field.
  3. **Hard Rule Anchoring** - every claim emitted via this
     schema MUST carry ``evidence_refs``; claims without
     ``evidence_refs`` are demoted to
     :attr:`AIIntelligenceAuthorityLevel.DEGRADED_NO_EVIDENCE`
     and the result's overall authority is downgraded
     accordingly.
  4. **Feedback Isolation** - ``feedback_isolation=True``,
     ``ai_output_is_commentary_only=True``,
     ``ai_output_can_be_training_label=False`` are pinned at
     every ``to_dict()`` boundary so an AI answer can never
     become a training label or a runtime fact.

This module is paper / report / read-only. It does NOT
authorise live trading, does NOT authorise auto-tuning, does
NOT call DeepSeek / any LLM, and does NOT open Phase 12.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.ai.evidence_bundle import (
    CREDENTIAL_LIKE_KEY_TOKENS,
    FORBIDDEN_AI_OUTPUT_FIELDS,
    _assert_no_forbidden_fields,
    _coerce_content,
)


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------
AI_INTELLIGENCE_OUTPUT_SOURCE_PHASE: str = "phase_ai_4"
AI_INTELLIGENCE_OUTPUT_SOURCE_MODULE: str = "ai_intelligence_output"
AI_INTELLIGENCE_OUTPUT_SCHEMA_VERSION: str = "v0"


# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------
class AIIntelligenceTaskType(str, Enum):
    """Closed task-type vocabulary for an offline AI
    intelligence output.

    Every task type matches one of the §2 "Allowed DeepSeek
    first-version outputs" labels in
    ``docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md``. None of the
    task types carries direction / sizing / leverage / stop /
    target / risk-budget semantics. Adding a new task type is
    a deliberate code change AND a brief amendment.
    """

    OPERATOR_BRIEFING_DRAFT = "OPERATOR_BRIEFING_DRAFT"
    MARKET_INTELLIGENCE_SUMMARY = "MARKET_INTELLIGENCE_SUMMARY"
    EVIDENCE_COMPRESSION = "EVIDENCE_COMPRESSION"
    REPLAY_REFLECTION_SUMMARY = "REPLAY_REFLECTION_SUMMARY"
    CONTRADICTION_SUMMARY = "CONTRADICTION_SUMMARY"
    EVIDENCE_QUALITY_ASSESSMENT = "EVIDENCE_QUALITY_ASSESSMENT"
    COVERAGE_AUDIT_INTERPRETATION = "COVERAGE_AUDIT_INTERPRETATION"
    POST_DISCOVERY_OUTCOME_SUMMARY = "POST_DISCOVERY_OUTCOME_SUMMARY"
    REJECT_TO_OUTCOME_SUMMARY = "REJECT_TO_OUTCOME_SUMMARY"
    SEVERE_MISS_SUMMARY = "SEVERE_MISS_SUMMARY"


class AIIntelligenceAuthorityLevel(str, Enum):
    """Closed authority-level vocabulary for one offline AI
    intelligence output.

    No member of this enum grants *trade authority*. The
    maximum authority any output can reach is
    :attr:`SUPPORTED_INTELLIGENCE`, which is *commentary
    substrate* only - it does NOT direct the Risk Engine, the
    Execution FSM, the Capital Flow Engine, the Reconciler, or
    any other trade-authority surface. The Risk Engine remains
    the single trade-decision gate.
    """

    COMMENTARY_ONLY = "COMMENTARY_ONLY"
    SUPPORTED_INTELLIGENCE = "SUPPORTED_INTELLIGENCE"
    DEGRADED_NO_EVIDENCE = "DEGRADED_NO_EVIDENCE"
    DEGRADED_REALITY_CHECK = "DEGRADED_REALITY_CHECK"
    REJECTED = "REJECTED"


class AIIntelligenceStatus(str, Enum):
    """Closed status vocabulary for one offline AI
    intelligence output."""

    OK = "OK"
    DEGRADED_OUTBOUND_DISABLED = "DEGRADED_OUTBOUND_DISABLED"
    DEGRADED_PROVIDER_ERROR = "DEGRADED_PROVIDER_ERROR"
    DEGRADED_REALITY_CHECK = "DEGRADED_REALITY_CHECK"
    DEGRADED_MISSING_EVIDENCE = "DEGRADED_MISSING_EVIDENCE"
    REJECTED_FORBIDDEN_FIELDS = "REJECTED_FORBIDDEN_FIELDS"
    REJECTED_INVALID_INPUT = "REJECTED_INVALID_INPUT"


# ---------------------------------------------------------------------------
# Redaction sentinel
# ---------------------------------------------------------------------------
#: The only allowed placeholder when a credential-shaped value
#: is detected in the prompt or the model output. The sandbox
#: NEVER carries a raw key / secret / token through any
#: serialised payload; it always replaces it with this
#: sentinel.
AI_SECRET_REDACTED_PLACEHOLDER: str = "<REDACTED>"


# ---------------------------------------------------------------------------
# Forbidden output fields (re-exported from Phase AI-1)
# ---------------------------------------------------------------------------
#: Re-exported so consumers of the intelligence schema do not
#: need to import :mod:`app.ai.evidence_bundle` directly. The
#: canonical list lives in :mod:`app.ai.evidence_bundle`.
FORBIDDEN_INTELLIGENCE_OUTPUT_FIELDS: frozenset[str] = (
    FORBIDDEN_AI_OUTPUT_FIELDS
)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AIIntelligenceClaim:
    """A single AI-emitted claim that has cleared (or been
    demoted by) the Phase AI-2 citation contract and the
    Phase AI-3 Reality Check Layer.

    The dataclass is descriptive only - it never carries
    direction / sizing / leverage / stop / target /
    risk-budget fields. The recursive
    :func:`_assert_no_forbidden_fields` guard runs at every
    serialisation boundary.
    """

    claim_id: str
    claim_type: str
    claim_text: str
    evidence_refs: tuple[str, ...]
    truth_layer_fields_used: tuple[str, ...]
    citation_authority_level: str
    reality_check_status: str
    reality_check_authority_level: str
    confidence_raw: float | None
    confidence_reality_checked: float | None
    warnings: tuple[str, ...]
    schema_version: str = AI_INTELLIGENCE_OUTPUT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "claim_id": str(self.claim_id),
            "claim_type": str(self.claim_type),
            "claim_text": str(self.claim_text),
            "evidence_refs": list(self.evidence_refs),
            "truth_layer_fields_used": list(
                self.truth_layer_fields_used
            ),
            "citation_authority_level": str(
                self.citation_authority_level
            ),
            "reality_check_status": str(self.reality_check_status),
            "reality_check_authority_level": str(
                self.reality_check_authority_level
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
            "warnings": list(self.warnings),
        }
        _assert_no_forbidden_fields(
            payload, context="AIIntelligenceClaim.to_dict"
        )
        return payload


@dataclass(frozen=True)
class AIIntelligenceOutput:
    """Frozen, schema-checked, deterministic AI intelligence
    output.

    Every Phase AI-4 DeepSeek Offline Sandbox run emits one
    :class:`AIIntelligenceOutput`. The output is JSON-serializable
    via :meth:`to_dict`. The recursive
    :func:`_assert_no_forbidden_fields` guard refuses to emit
    any payload that contains a trade-action /
    runtime-config-patch key at any nesting depth.
    """

    schema_version: str
    bundle_id: str
    task_type: str
    summary: str
    claims: tuple[AIIntelligenceClaim, ...]
    contradictions: tuple[str, ...]
    unsupported_claims: tuple[str, ...]
    risk_tags: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    reality_check_status: str
    authority_level: AIIntelligenceAuthorityLevel
    status: AIIntelligenceStatus
    forbidden_fields_stripped: tuple[str, ...]
    redacted_secret_count: int
    warnings: tuple[str, ...]
    degraded_reasons: tuple[str, ...]
    source_phase: str = AI_INTELLIGENCE_OUTPUT_SOURCE_PHASE
    source_module: str = AI_INTELLIGENCE_OUTPUT_SOURCE_MODULE
    # Hard-pinned root-constraint flags. Re-pinned at every
    # ``to_dict`` boundary even if a caller flips the dataclass
    # field via ``object.__setattr__``.
    stateless_inference: bool = True
    feedback_isolation: bool = True
    trade_authority: bool = False
    auto_tuning_allowed: bool = False
    phase_12_forbidden: bool = True
    ai_output_is_commentary_only: bool = True
    ai_output_can_be_training_label: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable payload for this output.

        The recursive forbidden-fields guard refuses to emit a
        payload that carries a trade-action /
        runtime-config-patch key at any nesting depth.
        """

        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "source_module": self.source_module,
            "bundle_id": str(self.bundle_id),
            "task_type": str(self.task_type),
            "summary": str(self.summary),
            "claims": [c.to_dict() for c in self.claims],
            "contradictions": list(self.contradictions),
            "unsupported_claims": list(self.unsupported_claims),
            "risk_tags": list(self.risk_tags),
            "evidence_refs": list(self.evidence_refs),
            "reality_check_status": str(self.reality_check_status),
            "authority_level": self.authority_level.value,
            "status": self.status.value,
            "forbidden_fields_stripped": list(
                self.forbidden_fields_stripped
            ),
            "redacted_secret_count": int(self.redacted_secret_count),
            "warnings": list(self.warnings),
            "degraded_reasons": list(self.degraded_reasons),
            # Hard-pinned root-constraint flags - these MUST
            # NEVER be relaxed by a downstream serialiser. We
            # re-emit the safe values here even if the
            # dataclass field has been mutated.
            "stateless_inference": True,
            "feedback_isolation": True,
            "trade_authority": False,
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
                "llm_outbound_enabled": False,
                "sandbox_only": True,
                "telegram_outbound_enabled": False,
                "binance_private_api_enabled": False,
            },
            # Forbidden-field reference list so a downstream
            # consumer can audit the schema without parsing
            # the source.
            "forbidden_fields": sorted(
                FORBIDDEN_INTELLIGENCE_OUTPUT_FIELDS
            ),
        }
        _assert_no_forbidden_fields(
            payload, context="AIIntelligenceOutput.to_dict"
        )
        return payload


# ---------------------------------------------------------------------------
# Forbidden-field stripping
# ---------------------------------------------------------------------------
def _looks_like_credential_key(key: str) -> bool:
    """Return True if the key name looks credential-shaped.

    The check mirrors the Phase AI-1 intake guard: any of the
    bare-token names (``secret`` / ``token``) or any of the
    substring tokens (``api_key`` / ``api_secret`` /
    ``private_key`` / ``deepseek_api`` / ...) marks the key
    as credential-shaped.
    """

    text = str(key).strip().lower()
    if not text:
        return False
    if text in ("secret", "secrets", "token"):
        return True
    return any(token in text for token in CREDENTIAL_LIKE_KEY_TOKENS)


def strip_forbidden_fields(
    payload: Any,
    *,
    forbidden: frozenset[str] | None = None,
) -> tuple[Any, list[str]]:
    """Recursively strip forbidden trade-action /
    runtime-config-patch fields from ``payload``.

    Returns a tuple of ``(clean_payload, stripped_paths)``
    where ``stripped_paths`` is a sorted list of dotted key
    paths that were removed (e.g.
    ``["claims[0].buy", "summary.runtime_config_patch"]``).

    The function NEVER mutates the input. It returns a fresh
    payload so the caller can preserve the original for
    auditing.
    """

    blocked: frozenset[str] = (
        forbidden
        if forbidden is not None
        else FORBIDDEN_INTELLIGENCE_OUTPUT_FIELDS
    )
    stripped: list[str] = []

    def _walk(node: Any, path: str) -> Any:
        if isinstance(node, Mapping):
            out: dict[str, Any] = {}
            for raw_key, value in node.items():
                key = str(raw_key)
                here = f"{path}.{key}" if path else key
                if key in blocked:
                    stripped.append(here)
                    continue
                out[key] = _walk(value, here)
            return out
        if isinstance(node, (list, tuple)):
            new_list: list[Any] = []
            for index, item in enumerate(node):
                here = f"{path}[{index}]"
                new_list.append(_walk(item, here))
            return new_list
        return node

    cleaned = _walk(payload, "")
    return cleaned, sorted(set(stripped))


def redact_secrets(
    payload: Any,
) -> tuple[Any, int]:
    """Recursively redact credential-shaped *keys* from
    ``payload``.

    Returns a tuple of ``(clean_payload, redacted_count)``.

    The function NEVER inspects string values for
    credential-shaped substrings - inspecting the value would
    require carrying the candidate secret in memory and risk
    leaking it back through a log line. Only KEY names are
    redacted; the matching value is replaced with
    :data:`AI_SECRET_REDACTED_PLACEHOLDER`.
    """

    redacted_count = 0

    def _walk(node: Any) -> Any:
        nonlocal redacted_count
        if isinstance(node, Mapping):
            out: dict[str, Any] = {}
            for raw_key, value in node.items():
                key = str(raw_key)
                if _looks_like_credential_key(key):
                    redacted_count += 1
                    out[key] = AI_SECRET_REDACTED_PLACEHOLDER
                else:
                    out[key] = _walk(value)
            return out
        if isinstance(node, (list, tuple)):
            return [_walk(item) for item in node]
        return node

    cleaned = _walk(payload)
    return cleaned, redacted_count


# ---------------------------------------------------------------------------
# Helpers re-used by the runner / tests
# ---------------------------------------------------------------------------
def coerce_str_tuple(value: Any) -> tuple[str, ...]:
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
        for item in value:
            if item is None:
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return tuple(out)
    return ()


def coerce_content(payload: Any) -> Any:
    """Re-export of the Phase AI-1 ``_coerce_content`` helper.

    Recursively coerce ``payload`` into a JSON-serializable
    form. Mappings become ``dict``, sequences become ``list``,
    enums become their ``value``. The recursive
    forbidden-fields guard runs at the serialisation boundary
    of the consumer (not here).
    """

    return _coerce_content(payload)


__all__ = [
    "AI_INTELLIGENCE_OUTPUT_SCHEMA_VERSION",
    "AI_INTELLIGENCE_OUTPUT_SOURCE_MODULE",
    "AI_INTELLIGENCE_OUTPUT_SOURCE_PHASE",
    "AI_SECRET_REDACTED_PLACEHOLDER",
    "AIIntelligenceAuthorityLevel",
    "AIIntelligenceClaim",
    "AIIntelligenceOutput",
    "AIIntelligenceStatus",
    "AIIntelligenceTaskType",
    "FORBIDDEN_INTELLIGENCE_OUTPUT_FIELDS",
    "coerce_content",
    "coerce_str_tuple",
    "redact_secrets",
    "strip_forbidden_fields",
]
