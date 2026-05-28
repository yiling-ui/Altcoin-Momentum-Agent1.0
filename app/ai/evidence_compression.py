"""Phase AI-5 - AI Evidence Compression Report v0.

The AI Layer's *operator-facing* compression artefact. Phase
AI-1 built the AI Evidence Bundle (the AI Layer's only allowed
read surface). Phase AI-2 built the AI Evidence Citation
Contract (every claim must cite Truth-Layer evidence via
``evidence_refs``). Phase AI-3 built the deterministic /
statistical Reality Check Layer. Phase AI-4 shipped the
DeepSeek Offline Sandbox runner that emits one schema-checked
:class:`AIIntelligenceOutput`. Phase AI-5 closes the human
loop: the schema-checked AI intelligence output is *compressed*
into a redacted, evidence-cited, claim-classified report that
an operator can read end-to-end.

The :class:`EvidenceCompressionReport`:

  - is **paper / report / read-only** (it never produces
    direction, sizing, leverage, stop, target, risk-budget,
    or any runtime-config-patch field; the recursive
    :func:`_assert_no_forbidden_fields` guard refuses to
    emit such a key at any nesting depth);
  - is **stateless** (the builder carries no instance state
    between calls; it never reads previous AI answers, chat
    history, ``listenKey`` payloads, signed-endpoint
    payloads, or any private exchange / account state);
  - **never** calls an LLM / DeepSeek;
  - **never** opens a network socket;
  - **never** authorises a trade decision - the report's
    :attr:`trade_authority` is ``False`` at every
    :meth:`to_dict` boundary;
  - **never** authorises auto-tuning -
    :attr:`auto_tuning_allowed` is ``False`` at every
    :meth:`to_dict` boundary;
  - **never** opens Phase 12 -
    :attr:`phase_12_forbidden` is ``True`` at every
    :meth:`to_dict` boundary.

The module enforces the four AI root constraints from
``docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md``:

  1. **Responsibility Isolation** - claims and report
     payloads are scrubbed of every forbidden trade-action /
     runtime-config-patch field via the recursive
     :func:`_assert_no_forbidden_fields` guard imported from
     :mod:`app.ai.evidence_bundle`, plus the
     :func:`strip_forbidden_fields` helper from
     :mod:`app.ai.intelligence_schema` that records every
     stripped key in ``forbidden_fields_stripped``.
  2. **Stateless Inference** - each
     :meth:`EvidenceCompressionReportBuilder.build` call is
     independent; the builder carries no instance state.
  3. **Hard Rule Anchoring** - claims that have no
     ``evidence_refs`` are listed in ``degraded_claims`` /
     ``unsupported_claims``; claims that contradict the
     bundle's facts (rejected by Reality Check) are listed
     in ``rejected_claims``; only claims that reached
     ``SUPPORTED_INTELLIGENCE`` after both Phase AI-2 and
     Phase AI-3 are listed in ``supported_claims``.
  4. **Feedback Isolation** - every emitted payload re-pins
     ``ai_output_is_commentary_only=True``,
     ``ai_output_can_be_training_label=False``,
     ``trade_authority=False``,
     ``auto_tuning_allowed=False``,
     ``phase_12_forbidden=True``,
     ``stateless_inference=True``,
     ``feedback_isolation=True`` so AI text can never become
     a training label or a runtime fact.

This module is paper / report / sandbox-only. It does NOT
authorise live trading, does NOT authorise auto-tuning, does
NOT call DeepSeek / any LLM, and does NOT open Phase 12.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.ai.evidence_bundle import (
    FORBIDDEN_AI_OUTPUT_FIELDS,
    _assert_no_forbidden_fields,
)
from app.ai.intelligence_schema import (
    coerce_content,
    coerce_str_tuple,
    redact_secrets,
    strip_forbidden_fields,
)


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------
AI_EVIDENCE_COMPRESSION_SOURCE_PHASE: str = "phase_ai_5"
AI_EVIDENCE_COMPRESSION_SOURCE_MODULE: str = (
    "ai_evidence_compression_report"
)
AI_EVIDENCE_COMPRESSION_SCHEMA_VERSION: str = "v0"


# ---------------------------------------------------------------------------
# Compressed claim record
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CompressedClaim:
    """One AI claim re-rendered for the operator-facing
    compression report.

    The dataclass preserves the producer-supplied
    ``claim_id`` / ``claim_text`` / ``evidence_refs`` /
    ``truth_layer_fields_used`` verbatim and adds the audit-
    trail bookkeeping computed by Phase AI-2 (citation
    authority) and Phase AI-3 (Reality Check status).
    """

    claim_id: str
    claim_type: str
    claim_text: str
    evidence_refs: tuple[str, ...]
    truth_layer_fields_used: tuple[str, ...]
    citation_authority_level: str
    reality_check_status: str
    reality_check_authority_level: str
    classification: str
    confidence_raw: float | None
    confidence_reality_checked: float | None
    warnings: tuple[str, ...]
    schema_version: str = AI_EVIDENCE_COMPRESSION_SCHEMA_VERSION

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
            "classification": str(self.classification),
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
            payload, context="CompressedClaim.to_dict"
        )
        return payload


# ---------------------------------------------------------------------------
# Compression report
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EvidenceCompressionReport:
    """Frozen, evidence-cited, deterministic compression
    report.

    The report is JSON-serializable via :meth:`to_dict`.
    Every serialised payload re-pins the project-wide
    invariants
    (``mode=paper``, ``live_trading=False``,
    ``ai_output_is_commentary_only=True``,
    ``ai_output_can_be_training_label=False``,
    ``trade_authority=False``,
    ``auto_tuning_allowed=False``,
    ``phase_12_forbidden=True``,
    ``stateless_inference=True``,
    ``feedback_isolation=True``).
    """

    report_id: str
    created_at_utc: str
    reference_window: str
    source_bundle_id: str
    source_ai_output_id: str
    summary: str
    compressed_claims: tuple[CompressedClaim, ...]
    supported_claims: tuple[str, ...]
    degraded_claims: tuple[str, ...]
    rejected_claims: tuple[str, ...]
    contradictions: tuple[str, ...]
    unsupported_claims: tuple[str, ...]
    reality_check_summary: Mapping[str, Any]
    evidence_quality_summary: Mapping[str, Any]
    data_gap_summary: Mapping[str, Any]
    notable_symbols: tuple[str, ...]
    risk_tags: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    forbidden_fields_stripped: tuple[str, ...]
    redacted_secret_count: int
    warnings: tuple[str, ...]
    schema_version: str = AI_EVIDENCE_COMPRESSION_SCHEMA_VERSION
    source_phase: str = AI_EVIDENCE_COMPRESSION_SOURCE_PHASE
    source_module: str = AI_EVIDENCE_COMPRESSION_SOURCE_MODULE
    # Hard-pinned root-constraint flags. Re-pinned at every
    # ``to_dict`` boundary even if a downstream caller flips
    # the dataclass field via ``object.__setattr__``.
    trade_authority: bool = False
    auto_tuning_allowed: bool = False
    phase_12_forbidden: bool = True
    stateless_inference: bool = True
    feedback_isolation: bool = True
    ai_output_is_commentary_only: bool = True
    ai_output_can_be_training_label: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable payload for this report.

        The recursive forbidden-fields guard refuses to emit a
        payload that carries a trade-action /
        runtime-config-patch key at any nesting depth.
        """

        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "source_module": self.source_module,
            "report_id": str(self.report_id),
            "created_at_utc": str(self.created_at_utc),
            "reference_window": str(self.reference_window),
            "source_bundle_id": str(self.source_bundle_id),
            "source_ai_output_id": str(self.source_ai_output_id),
            "summary": str(self.summary),
            "compressed_claims": [
                c.to_dict() for c in self.compressed_claims
            ],
            "supported_claims": list(self.supported_claims),
            "degraded_claims": list(self.degraded_claims),
            "rejected_claims": list(self.rejected_claims),
            "contradictions": list(self.contradictions),
            "unsupported_claims": list(self.unsupported_claims),
            "reality_check_summary": coerce_content(
                self.reality_check_summary
            ),
            "evidence_quality_summary": coerce_content(
                self.evidence_quality_summary
            ),
            "data_gap_summary": coerce_content(
                self.data_gap_summary
            ),
            "notable_symbols": list(self.notable_symbols),
            "risk_tags": list(self.risk_tags),
            "evidence_refs": list(self.evidence_refs),
            "forbidden_fields_stripped": list(
                self.forbidden_fields_stripped
            ),
            "redacted_secret_count": int(self.redacted_secret_count),
            "warnings": list(self.warnings),
            # Hard-pinned root-constraint flags - these MUST
            # NEVER be relaxed by a downstream serialiser. We
            # re-emit the safe values here even if the dataclass
            # field has been mutated.
            "trade_authority": False,
            "auto_tuning_allowed": False,
            "phase_12_forbidden": True,
            "stateless_inference": True,
            "feedback_isolation": True,
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
            "forbidden_fields": sorted(FORBIDDEN_AI_OUTPUT_FIELDS),
        }
        _assert_no_forbidden_fields(
            payload, context="EvidenceCompressionReport.to_dict"
        )
        return payload


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
# Closed claim-classification vocabulary used in the
# compression report.
CLAIM_CLASS_SUPPORTED: str = "SUPPORTED"
CLAIM_CLASS_UNSUPPORTED: str = "UNSUPPORTED"
CLAIM_CLASS_DEGRADED_NO_EVIDENCE: str = "DEGRADED_NO_EVIDENCE"
CLAIM_CLASS_REJECTED: str = "REJECTED"
CLAIM_CLASS_CONTRADICTED: str = "CONTRADICTED"
CLAIM_CLASS_COMMENTARY_ONLY: str = "COMMENTARY_ONLY"


# Citation-authority strings the AI-2 contract emits. We do not
# import the enum directly because the AI-4 sandbox output is
# already serialised - the strings on the wire are what we get.
_CITATION_LEVEL_SUPPORTED: frozenset[str] = frozenset(
    {"SUPPORTED_INTELLIGENCE"}
)
_CITATION_LEVEL_DEGRADED: frozenset[str] = frozenset(
    {"DEGRADED_NO_EVIDENCE", "UNSUPPORTED_INTELLIGENCE"}
)
_CITATION_LEVEL_REJECTED: frozenset[str] = frozenset(
    {"REJECTED_BY_SCHEMA", "REJECTED_INVALID_EVIDENCE"}
)
_CITATION_LEVEL_COMMENTARY_ONLY: frozenset[str] = frozenset(
    {"COMMENTARY_ONLY"}
)

# Reality-check status strings the AI-3 layer emits.
_RC_STATUS_SUPPORTED: frozenset[str] = frozenset({"SUPPORTED"})
_RC_STATUS_PARTIAL: frozenset[str] = frozenset(
    {"PARTIALLY_SUPPORTED"}
)
_RC_STATUS_CONTRADICTED: frozenset[str] = frozenset(
    {"CONTRADICTED"}
)
_RC_STATUS_INSUFFICIENT: frozenset[str] = frozenset(
    {"INSUFFICIENT_EVIDENCE"}
)
_RC_STATUS_REJECTED: frozenset[str] = frozenset(
    {"REJECTED_LOOKAHEAD", "REJECTED_UNVERIFIABLE_NARRATIVE"}
)


def classify_claim(
    *,
    citation_authority_level: str,
    reality_check_status: str,
    reality_check_authority_level: str,
    has_evidence_refs: bool,
) -> str:
    """Classify one AI claim into the closed compression
    vocabulary.

    The classification is **conservative** - a claim never
    "graduates" past what Phase AI-2 / AI-3 already gave it.
    Specifically:

      - ``REJECTED`` if either the citation contract rejected
        it (``REJECTED_BY_SCHEMA`` /
        ``REJECTED_INVALID_EVIDENCE``) or Reality Check
        rejected it (``REJECTED_LOOKAHEAD`` /
        ``REJECTED_UNVERIFIABLE_NARRATIVE``);
      - ``CONTRADICTED`` if Reality Check returned
        ``CONTRADICTED``;
      - ``DEGRADED_NO_EVIDENCE`` if the citation contract
        demoted the claim or no ``evidence_refs`` survived;
      - ``COMMENTARY_ONLY`` if the producer pinned the claim
        as commentary-only;
      - ``UNSUPPORTED`` if Reality Check returned anything
        other than ``SUPPORTED`` (and the claim was not
        already classified above);
      - ``SUPPORTED`` if both the citation contract and the
        Reality Check engine returned a supported authority
        level.
    """

    cit = str(citation_authority_level or "").strip()
    rc_status = str(reality_check_status or "").strip()
    rc_auth = str(reality_check_authority_level or "").strip()

    # Hard rejections come first.
    if cit in _CITATION_LEVEL_REJECTED:
        return CLAIM_CLASS_REJECTED
    if rc_status in _RC_STATUS_REJECTED:
        return CLAIM_CLASS_REJECTED
    if rc_auth == "REJECTED_BY_REALITY_CHECK":
        # CONTRADICTED is a more specific rejection.
        if rc_status in _RC_STATUS_CONTRADICTED:
            return CLAIM_CLASS_CONTRADICTED
        return CLAIM_CLASS_REJECTED
    if rc_status in _RC_STATUS_CONTRADICTED:
        return CLAIM_CLASS_CONTRADICTED

    # Degraded-no-evidence next.
    if not has_evidence_refs:
        return CLAIM_CLASS_DEGRADED_NO_EVIDENCE
    if cit in _CITATION_LEVEL_DEGRADED:
        return CLAIM_CLASS_DEGRADED_NO_EVIDENCE

    # Producer-pinned commentary-only.
    if cit in _CITATION_LEVEL_COMMENTARY_ONLY:
        return CLAIM_CLASS_COMMENTARY_ONLY

    # Insufficient evidence from RC, or any non-supported RC.
    if rc_status in _RC_STATUS_INSUFFICIENT:
        return CLAIM_CLASS_UNSUPPORTED
    if rc_status in _RC_STATUS_PARTIAL:
        # Partial support is still not full support; we
        # surface it as UNSUPPORTED in the compression
        # vocabulary so the operator knows not to read it as
        # a supported finding.
        if rc_auth == "SUPPORTED_INTELLIGENCE":
            return CLAIM_CLASS_SUPPORTED
        return CLAIM_CLASS_UNSUPPORTED
    if rc_status in _RC_STATUS_SUPPORTED:
        if (
            cit in _CITATION_LEVEL_SUPPORTED
            and rc_auth == "SUPPORTED_INTELLIGENCE"
        ):
            return CLAIM_CLASS_SUPPORTED
        return CLAIM_CLASS_UNSUPPORTED

    # Unknown / empty status: degrade to unsupported. The
    # builder NEVER promotes a claim past its strongest input
    # axis.
    return CLAIM_CLASS_UNSUPPORTED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _coerce_str_tuple(value: Any) -> tuple[str, ...]:
    return coerce_str_tuple(value)


def _coerce_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_market_facts(
    bundle: Mapping[str, Any], group: str
) -> dict[str, Any]:
    """Flatten a bundle's ``<group>`` collection into a single
    ``{key: value}`` mapping so the compression report can
    surface the facts the operator cares about (data gaps,
    breadth, late-chase rates, etc.) without re-parsing the
    bundle on the operator side.
    """

    raw = bundle.get(group)
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        return {}
    out: dict[str, Any] = {}
    for fact in raw:
        if not isinstance(fact, Mapping):
            continue
        content = fact.get("content")
        if not isinstance(content, Mapping):
            continue
        for key, value in content.items():
            out[str(key)] = value
    return out


def _build_data_gap_summary(
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Surface the bundle's data-gap-shaped facts so the
    operator briefing can list them as ``data_gaps`` without
    re-parsing the bundle.

    The summary is descriptive only - it never directs Risk /
    Execution / Strategy / Config.
    """

    market = _extract_market_facts(bundle, "market_facts")
    sysbeh = _extract_market_facts(bundle, "system_behavior_facts")
    outcome = _extract_market_facts(bundle, "outcome_facts")

    data_gap_keys = (
        ("market_facts.data_gap_severe", market.get("data_gap_severe")),
        ("market_facts.data_gap_rate", market.get("data_gap_rate")),
        ("market_facts.breadth_weak", market.get("breadth_weak")),
        (
            "system_behavior_facts.late_chase_high",
            sysbeh.get("late_chase_high"),
        ),
        (
            "system_behavior_facts.late_chase_rate",
            sysbeh.get("late_chase_rate"),
        ),
        (
            "system_behavior_facts.fake_breakout_rising",
            sysbeh.get("fake_breakout_rising"),
        ),
        (
            "system_behavior_facts.funding_overheated",
            sysbeh.get("funding_overheated"),
        ),
        (
            "outcome_facts.failed_continuation",
            outcome.get("failed_continuation"),
        ),
        (
            "outcome_facts.missed_strong_tail_rate",
            outcome.get("missed_strong_tail_rate"),
        ),
    )

    surfaced: dict[str, Any] = {}
    flagged: list[str] = []
    for key, value in data_gap_keys:
        if value is None:
            continue
        surfaced[key] = value
        # Flag the operator-facing concerns.
        if isinstance(value, bool) and value is True:
            flagged.append(key)
        elif isinstance(value, (int, float)):
            try:
                if float(value) >= 0.5:
                    flagged.append(key)
            except (TypeError, ValueError):
                continue

    # Bundle-level ``degraded_facts`` count if present.
    degraded = bundle.get("degraded_facts")
    degraded_count = (
        len(degraded)
        if isinstance(degraded, Sequence)
        and not isinstance(degraded, (str, bytes))
        else 0
    )
    return {
        "flagged": flagged,
        "surfaced_signals": surfaced,
        "degraded_fact_count": int(degraded_count),
    }


def _summarise_reality_check(
    ai_output: Mapping[str, Any],
    classification_counts: Mapping[str, int],
) -> dict[str, Any]:
    """Build the reality-check summary block."""

    return {
        "overall_status": str(
            ai_output.get("reality_check_status", "")
        ),
        "overall_authority_level": str(
            ai_output.get("authority_level", "")
        ),
        "supported_claim_count": int(
            classification_counts.get(CLAIM_CLASS_SUPPORTED, 0)
        ),
        "unsupported_claim_count": int(
            classification_counts.get(CLAIM_CLASS_UNSUPPORTED, 0)
        ),
        "degraded_claim_count": int(
            classification_counts.get(
                CLAIM_CLASS_DEGRADED_NO_EVIDENCE, 0
            )
        ),
        "rejected_claim_count": int(
            classification_counts.get(CLAIM_CLASS_REJECTED, 0)
        ),
        "contradicted_claim_count": int(
            classification_counts.get(CLAIM_CLASS_CONTRADICTED, 0)
        ),
        "commentary_only_claim_count": int(
            classification_counts.get(
                CLAIM_CLASS_COMMENTARY_ONLY, 0
            )
        ),
    }


def _summarise_evidence_quality(
    bundle: Mapping[str, Any],
    ai_output: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the evidence-quality summary block."""

    accepted = bundle.get("accepted_fact_count")
    degraded = bundle.get("degraded_fact_count")
    return {
        "bundle_build_status": str(
            bundle.get("build_status", "")
        ),
        "bundle_accepted_fact_count": int(accepted)
        if isinstance(accepted, (int, float))
        else 0,
        "bundle_degraded_fact_count": int(degraded)
        if isinstance(degraded, (int, float))
        else 0,
        "ai_output_status": str(ai_output.get("status", "")),
        "ai_output_authority_level": str(
            ai_output.get("authority_level", "")
        ),
        "forbidden_fields_stripped_in_ai_output": list(
            coerce_str_tuple(
                ai_output.get("forbidden_fields_stripped")
            )
        ),
        "redacted_secret_count_in_ai_output": int(
            ai_output.get("redacted_secret_count") or 0
        ),
    }


def _extract_notable_symbols(
    evidence_refs: Iterable[str],
) -> tuple[str, ...]:
    """Pull the ``symbol:<SYMBOL>`` references out of the
    evidence_refs list, preserving input order. The function
    NEVER invents new symbols.
    """

    seen: set[str] = set()
    out: list[str] = []
    for ref in evidence_refs:
        text = str(ref).strip()
        if not text.startswith("symbol:"):
            continue
        symbol = text[len("symbol:") :].strip()
        if not symbol:
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        out.append(symbol)
    return tuple(out)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
class EvidenceCompressionReportBuilder:
    """Pure, deterministic builder for the
    :class:`EvidenceCompressionReport`.

    The builder:

      - reads a serialised Phase AI-1 evidence bundle and a
        serialised Phase AI-4 :class:`AIIntelligenceOutput`;
      - re-classifies every claim into the closed compression
        vocabulary;
      - never invents a missing ``evidence_refs`` entry;
      - never paraphrases ``claim_text``;
      - strips any forbidden trade-action /
        runtime-config-patch field that may have leaked
        through (defence in depth);
      - redacts any credential-shaped key in the model output
        (defence in depth);
      - never calls an LLM / DeepSeek;
      - never opens a network socket;
      - never reads or carries API secrets;
      - never reads private exchange / account state;
      - never authorises a trade decision;
      - never authorises auto-tuning.
    """

    def __init__(
        self, *, source_phase: str | None = None
    ) -> None:
        self._source_phase = (
            str(source_phase)
            if source_phase
            else AI_EVIDENCE_COMPRESSION_SOURCE_PHASE
        )

    @property
    def source_phase(self) -> str:
        return self._source_phase

    def build(
        self,
        *,
        report_id: str,
        created_at_utc: str,
        evidence_bundle: Mapping[str, Any],
        ai_intelligence_output: Mapping[str, Any],
        reference_window: str | None = None,
        warnings: Iterable[str] | None = None,
    ) -> EvidenceCompressionReport:
        """Build one :class:`EvidenceCompressionReport`.

        ``evidence_bundle`` is the serialised view of the
        Phase AI-1 :class:`AIEvidenceBundle`. ``ai_intelligence_output``
        is the serialised view of the Phase AI-4
        :class:`AIIntelligenceOutput` (or any structurally
        compatible offline / fake intelligence payload).
        """

        if not isinstance(evidence_bundle, Mapping):
            raise TypeError(
                "EvidenceCompressionReportBuilder.build expects "
                "evidence_bundle to be a Mapping; got "
                f"{type(evidence_bundle).__name__}."
            )
        if not isinstance(ai_intelligence_output, Mapping):
            raise TypeError(
                "EvidenceCompressionReportBuilder.build expects "
                "ai_intelligence_output to be a Mapping; got "
                f"{type(ai_intelligence_output).__name__}."
            )

        report_id_str = str(report_id).strip()
        if not report_id_str:
            raise ValueError(
                "EvidenceCompressionReportBuilder.build requires "
                "a non-empty report_id; deterministic identifiers "
                "must be supplied by the caller."
            )
        created_at_utc_str = str(created_at_utc).strip()
        if not created_at_utc_str:
            raise ValueError(
                "EvidenceCompressionReportBuilder.build requires "
                "a non-empty created_at_utc string."
            )

        # Defensive forbidden-field strip + secret redaction on
        # the AI output. Both helpers are pure and never mutate
        # their input.
        cleaned_ai_output, stripped_paths = strip_forbidden_fields(
            dict(ai_intelligence_output)
        )
        cleaned_ai_output, redacted_count = redact_secrets(
            cleaned_ai_output
        )

        bundle_id = str(
            evidence_bundle.get("bundle_id", "<unknown>")
        )
        ai_output_id = str(
            cleaned_ai_output.get("bundle_id", bundle_id)
        )

        ref_window = (
            str(reference_window).strip()
            if reference_window is not None
            and str(reference_window).strip()
            else str(
                evidence_bundle.get(
                    "reference_window", "unspecified"
                )
            )
        )

        # Extract claims from the AI output.
        raw_claims = cleaned_ai_output.get("claims")
        compressed: list[CompressedClaim] = []
        classification_counts: dict[str, int] = {}
        supported_ids: list[str] = []
        degraded_ids: list[str] = []
        rejected_ids: list[str] = []
        contradicted_ids: list[str] = []
        unsupported_ids: list[str] = []
        all_evidence_refs: list[str] = []
        seen_refs: set[str] = set()

        if isinstance(raw_claims, Iterable) and not isinstance(
            raw_claims, (str, bytes)
        ):
            for index, claim in enumerate(raw_claims):
                if not isinstance(claim, Mapping):
                    continue
                claim_id = str(
                    claim.get("claim_id", f"claim_{index}")
                ).strip()
                if not claim_id:
                    claim_id = f"claim_{index}"
                claim_type = str(
                    claim.get("claim_type", "")
                ).strip()
                claim_text = str(
                    claim.get("claim_text", "")
                ).strip()
                evidence_refs = _coerce_str_tuple(
                    claim.get("evidence_refs")
                )
                truth_fields = _coerce_str_tuple(
                    claim.get("truth_layer_fields_used")
                )
                cit_level = str(
                    claim.get("citation_authority_level", "")
                ).strip()
                rc_status = str(
                    claim.get("reality_check_status", "")
                ).strip()
                rc_auth = str(
                    claim.get("reality_check_authority_level", "")
                ).strip()
                conf_raw = _safe_float(claim.get("confidence_raw"))
                conf_rc = _safe_float(
                    claim.get("confidence_reality_checked")
                )
                claim_warnings = _coerce_str_tuple(
                    claim.get("warnings")
                )

                classification = classify_claim(
                    citation_authority_level=cit_level,
                    reality_check_status=rc_status,
                    reality_check_authority_level=rc_auth,
                    has_evidence_refs=bool(evidence_refs),
                )
                classification_counts[classification] = (
                    classification_counts.get(classification, 0)
                    + 1
                )

                if classification == CLAIM_CLASS_SUPPORTED:
                    supported_ids.append(claim_id)
                elif classification == CLAIM_CLASS_DEGRADED_NO_EVIDENCE:
                    degraded_ids.append(claim_id)
                    unsupported_ids.append(claim_id)
                elif classification == CLAIM_CLASS_REJECTED:
                    rejected_ids.append(claim_id)
                    unsupported_ids.append(claim_id)
                elif classification == CLAIM_CLASS_CONTRADICTED:
                    contradicted_ids.append(claim_id)
                    rejected_ids.append(claim_id)
                    unsupported_ids.append(claim_id)
                elif classification == CLAIM_CLASS_COMMENTARY_ONLY:
                    # Commentary-only claims are NOT supported
                    # findings; they are not unsupported either,
                    # they are read-only annotations.
                    pass
                else:
                    # CLAIM_CLASS_UNSUPPORTED.
                    unsupported_ids.append(claim_id)

                for ref in evidence_refs:
                    if ref not in seen_refs:
                        seen_refs.add(ref)
                        all_evidence_refs.append(ref)

                compressed.append(
                    CompressedClaim(
                        claim_id=claim_id,
                        claim_type=claim_type,
                        claim_text=claim_text,
                        evidence_refs=evidence_refs,
                        truth_layer_fields_used=truth_fields,
                        citation_authority_level=cit_level,
                        reality_check_status=rc_status,
                        reality_check_authority_level=rc_auth,
                        classification=classification,
                        confidence_raw=conf_raw,
                        confidence_reality_checked=conf_rc,
                        warnings=claim_warnings,
                    )
                )

        # Surface AI-output-level contradictions / unsupported
        # claim ids that may not have been included in the
        # claims iteration (e.g. when the runner appended ids
        # directly).
        for cid in coerce_str_tuple(
            cleaned_ai_output.get("contradictions")
        ):
            if cid not in contradicted_ids:
                contradicted_ids.append(cid)
            if cid not in rejected_ids:
                rejected_ids.append(cid)
            if cid not in unsupported_ids:
                unsupported_ids.append(cid)
        for cid in coerce_str_tuple(
            cleaned_ai_output.get("unsupported_claims")
        ):
            if cid not in unsupported_ids:
                unsupported_ids.append(cid)

        # Top-level evidence_refs from the AI output - merge.
        for ref in coerce_str_tuple(
            cleaned_ai_output.get("evidence_refs")
        ):
            if ref not in seen_refs:
                seen_refs.add(ref)
                all_evidence_refs.append(ref)

        notable_symbols = _extract_notable_symbols(
            all_evidence_refs
        )
        risk_tags = coerce_str_tuple(
            cleaned_ai_output.get("risk_tags")
        )

        reality_check_summary = _summarise_reality_check(
            cleaned_ai_output, classification_counts
        )
        evidence_quality_summary = _summarise_evidence_quality(
            evidence_bundle, cleaned_ai_output
        )
        data_gap_summary = _build_data_gap_summary(evidence_bundle)

        # Build a compact summary string. We never paraphrase the
        # AI's summary; we surface a deterministic operator-
        # readable header instead.
        bundle_status = str(
            evidence_bundle.get("build_status", "")
        )
        ai_status = str(cleaned_ai_output.get("status", ""))
        ai_summary = str(cleaned_ai_output.get("summary", "")).strip()
        summary_text = (
            f"Evidence compression report for bundle "
            f"{bundle_id} (build_status={bundle_status}); "
            f"AI intelligence status={ai_status}; "
            f"compressed_claims={len(compressed)}; "
            f"supported={len(supported_ids)}; "
            f"degraded={len(degraded_ids)}; "
            f"rejected={len(rejected_ids)}; "
            f"contradicted={len(contradicted_ids)}; "
            f"reference_window={ref_window}."
        )
        if ai_summary:
            summary_text = summary_text + " " + ai_summary

        # Aggregate warnings.
        all_warnings: list[str] = []
        if warnings is not None:
            for w in warnings:
                if w is None:
                    continue
                text = str(w).strip()
                if text:
                    all_warnings.append(text)
        for w in coerce_str_tuple(cleaned_ai_output.get("warnings")):
            all_warnings.append(f"ai_output_warning:{w}")
        for w in coerce_str_tuple(
            cleaned_ai_output.get("degraded_reasons")
        ):
            all_warnings.append(f"ai_output_degraded_reason:{w}")
        for w in coerce_str_tuple(evidence_bundle.get("warnings")):
            all_warnings.append(f"evidence_bundle_warning:{w}")
        if stripped_paths:
            all_warnings.append(
                f"forbidden_fields_stripped_in_compression:"
                f"{len(stripped_paths)}"
            )
        if redacted_count > 0:
            all_warnings.append(
                f"secrets_redacted_in_compression:{redacted_count}"
            )

        return EvidenceCompressionReport(
            report_id=report_id_str,
            created_at_utc=created_at_utc_str,
            reference_window=ref_window,
            source_bundle_id=bundle_id,
            source_ai_output_id=ai_output_id,
            summary=summary_text,
            compressed_claims=tuple(compressed),
            supported_claims=tuple(supported_ids),
            degraded_claims=tuple(degraded_ids),
            rejected_claims=tuple(rejected_ids),
            contradictions=tuple(contradicted_ids),
            unsupported_claims=tuple(unsupported_ids),
            reality_check_summary=reality_check_summary,
            evidence_quality_summary=evidence_quality_summary,
            data_gap_summary=data_gap_summary,
            notable_symbols=notable_symbols,
            risk_tags=risk_tags,
            evidence_refs=tuple(all_evidence_refs),
            forbidden_fields_stripped=tuple(stripped_paths),
            redacted_secret_count=int(redacted_count),
            warnings=tuple(all_warnings),
        )


def build_evidence_compression_report(
    *,
    report_id: str,
    created_at_utc: str,
    evidence_bundle: Mapping[str, Any],
    ai_intelligence_output: Mapping[str, Any],
    reference_window: str | None = None,
    warnings: Iterable[str] | None = None,
) -> EvidenceCompressionReport:
    """Convenience wrapper that constructs a builder and calls
    :meth:`EvidenceCompressionReportBuilder.build`.
    """

    return EvidenceCompressionReportBuilder().build(
        report_id=report_id,
        created_at_utc=created_at_utc,
        evidence_bundle=evidence_bundle,
        ai_intelligence_output=ai_intelligence_output,
        reference_window=reference_window,
        warnings=warnings,
    )


def render_evidence_compression_report_markdown(
    report: EvidenceCompressionReport,
) -> str:
    """Render a deterministic Markdown view of the report.

    The Markdown is paper / report / read-only. It NEVER
    contains a trade-action / runtime-config-patch field; the
    recursive forbidden-fields guard runs at the underlying
    :meth:`to_dict` boundary.
    """

    payload = report.to_dict()
    lines: list[str] = []
    lines.append("# AI Evidence Compression Report v0")
    lines.append("")
    lines.append(
        "> **Status:** paper / report / sandbox-only. **NOT** "
        "live trading. **NOT** trade authority. **NOT** "
        "auto-tuning. **NOT** Phase 12."
    )
    lines.append("")
    lines.append(
        f"- **report_id:** `{payload['report_id']}`"
    )
    lines.append(
        f"- **created_at_utc:** `{payload['created_at_utc']}`"
    )
    lines.append(
        f"- **reference_window:** `{payload['reference_window']}`"
    )
    lines.append(
        f"- **source_bundle_id:** `{payload['source_bundle_id']}`"
    )
    lines.append(
        f"- **source_ai_output_id:** "
        f"`{payload['source_ai_output_id']}`"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(payload["summary"])
    lines.append("")
    lines.append("## Reality check summary")
    lines.append("")
    for key, value in payload["reality_check_summary"].items():
        lines.append(f"- `{key}` = `{value}`")
    lines.append("")
    lines.append("## Evidence quality summary")
    lines.append("")
    for key, value in payload["evidence_quality_summary"].items():
        lines.append(f"- `{key}` = `{value}`")
    lines.append("")
    lines.append("## Data gap summary")
    lines.append("")
    flagged = payload["data_gap_summary"].get("flagged", [])
    lines.append(f"- **flagged signals:** `{flagged}`")
    surfaced = payload["data_gap_summary"].get(
        "surfaced_signals", {}
    )
    for key, value in surfaced.items():
        lines.append(f"  - `{key}` = `{value}`")
    lines.append(
        "- **bundle_degraded_fact_count:** "
        f"`{payload['data_gap_summary'].get('degraded_fact_count', 0)}`"
    )
    lines.append("")
    lines.append("## Compressed claims")
    lines.append("")
    if not payload["compressed_claims"]:
        lines.append("_No claims emitted._")
    for claim in payload["compressed_claims"]:
        lines.append(f"- **{claim['claim_id']}** ")
        lines.append(
            f"  - claim_type: `{claim['claim_type']}`"
        )
        lines.append(
            f"  - classification: "
            f"`{claim['classification']}`"
        )
        lines.append(
            f"  - citation_authority_level: "
            f"`{claim['citation_authority_level']}`"
        )
        lines.append(
            f"  - reality_check_status: "
            f"`{claim['reality_check_status']}`"
        )
        lines.append(
            f"  - reality_check_authority_level: "
            f"`{claim['reality_check_authority_level']}`"
        )
        lines.append(
            f"  - evidence_refs: "
            f"`{', '.join(claim['evidence_refs'])}`"
        )
        lines.append(
            f"  - claim_text: {claim['claim_text']}"
        )
    lines.append("")
    lines.append("## Buckets")
    lines.append("")
    lines.append(
        f"- **supported_claims:** `{payload['supported_claims']}`"
    )
    lines.append(
        f"- **degraded_claims:** `{payload['degraded_claims']}`"
    )
    lines.append(
        f"- **rejected_claims:** `{payload['rejected_claims']}`"
    )
    lines.append(
        f"- **contradictions:** `{payload['contradictions']}`"
    )
    lines.append(
        f"- **unsupported_claims:** "
        f"`{payload['unsupported_claims']}`"
    )
    lines.append(
        f"- **notable_symbols:** "
        f"`{payload['notable_symbols']}`"
    )
    lines.append(
        f"- **risk_tags:** `{payload['risk_tags']}`"
    )
    lines.append("")
    lines.append("## Audit")
    lines.append("")
    lines.append(
        f"- **forbidden_fields_stripped:** "
        f"`{len(payload['forbidden_fields_stripped'])}`"
    )
    lines.append(
        f"- **redacted_secret_count:** "
        f"`{payload['redacted_secret_count']}`"
    )
    lines.append(
        f"- **warnings:** `{payload['warnings']}`"
    )
    lines.append("")
    lines.append("## Safety boundary (held end-to-end)")
    lines.append("")
    safety = payload["safety_flags"]
    for key, value in safety.items():
        lines.append(f"- `{key}` = `{value}`")
    lines.append(
        f"- `trade_authority` = `{payload['trade_authority']}`"
    )
    lines.append(
        f"- `auto_tuning_allowed` = "
        f"`{payload['auto_tuning_allowed']}`"
    )
    lines.append(
        f"- `phase_12_forbidden` = "
        f"`{payload['phase_12_forbidden']}`"
    )
    lines.append("")
    lines.append(
        "The Risk Engine remains the single trade-decision gate."
    )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "AI_EVIDENCE_COMPRESSION_SCHEMA_VERSION",
    "AI_EVIDENCE_COMPRESSION_SOURCE_MODULE",
    "AI_EVIDENCE_COMPRESSION_SOURCE_PHASE",
    "CLAIM_CLASS_COMMENTARY_ONLY",
    "CLAIM_CLASS_CONTRADICTED",
    "CLAIM_CLASS_DEGRADED_NO_EVIDENCE",
    "CLAIM_CLASS_REJECTED",
    "CLAIM_CLASS_SUPPORTED",
    "CLAIM_CLASS_UNSUPPORTED",
    "CompressedClaim",
    "EvidenceCompressionReport",
    "EvidenceCompressionReportBuilder",
    "build_evidence_compression_report",
    "classify_claim",
    "render_evidence_compression_report_markdown",
]
