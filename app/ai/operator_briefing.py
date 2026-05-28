"""Phase AI-5 - Operator Briefing v0.

The AI Layer's *human-readable* briefing artefact. Phase AI-1
built the AI Evidence Bundle (the AI Layer's only allowed read
surface). Phase AI-2 built the AI Evidence Citation Contract
(every claim must cite Truth-Layer evidence via
``evidence_refs``). Phase AI-3 built the deterministic /
statistical Reality Check Layer. Phase AI-4 shipped the
DeepSeek Offline Sandbox runner that emits one schema-checked
:class:`AIIntelligenceOutput`. Phase AI-5 closes the human
loop: the schema-checked AI intelligence output, the
Phase AI-1 evidence bundle, and the Block C Integrated
Checkpoint summary are *compressed* into a redacted,
evidence-cited, claim-classified briefing an operator can read
end-to-end.

The :class:`OperatorBriefing`:

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
  - **never** authorises a trade decision -
    :attr:`trade_authority` is ``False`` at every
    :meth:`to_dict` boundary;
  - **never** authorises auto-tuning -
    :attr:`auto_tuning_allowed` is ``False`` at every
    :meth:`to_dict` boundary;
  - **never** opens Phase 12 -
    :attr:`phase_12_forbidden` is ``True`` at every
    :meth:`to_dict` boundary.

The four AI root constraints from
``docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`` are enforced *in
code* and *in tests*:

  1. **Responsibility Isolation** - claims and briefing
     payloads are scrubbed of every forbidden trade-action /
     runtime-config-patch field via the recursive
     :func:`_assert_no_forbidden_fields` guard imported from
     :mod:`app.ai.evidence_bundle`, plus the
     :func:`strip_forbidden_fields` helper from
     :mod:`app.ai.intelligence_schema` that records every
     stripped key in ``forbidden_fields_stripped``.
  2. **Stateless Inference** - each
     :meth:`OperatorBriefingBuilder.build` call is
     independent; the builder carries no instance state.
  3. **Hard Rule Anchoring** - claims that have no
     ``evidence_refs`` are listed in ``unsupported_claims``,
     never in ``key_findings``; claims that contradict the
     bundle's facts are listed in ``contradictions`` and
     surfaced via the ``CONTRADICTIONS`` section, never in
     ``key_findings``; claims that the AI-4 runner rejected
     are surfaced via the ``UNSUPPORTED_CLAIMS`` section
     only.
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
from enum import Enum
from typing import Any

from app.ai.evidence_bundle import (
    ALLOWED_CONSUMERS,
    FORBIDDEN_AI_OUTPUT_FIELDS,
    FORBIDDEN_CONSUMERS,
    LOOKAHEAD_POLICY_FLAGS,
    _assert_no_forbidden_fields,
)
from app.ai.evidence_compression import (
    AI_EVIDENCE_COMPRESSION_SCHEMA_VERSION,
    CLAIM_CLASS_COMMENTARY_ONLY,
    CLAIM_CLASS_CONTRADICTED,
    CLAIM_CLASS_DEGRADED_NO_EVIDENCE,
    CLAIM_CLASS_REJECTED,
    CLAIM_CLASS_SUPPORTED,
    CLAIM_CLASS_UNSUPPORTED,
    CompressedClaim,
    EvidenceCompressionReport,
    EvidenceCompressionReportBuilder,
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
AI_OPERATOR_BRIEFING_SOURCE_PHASE: str = "phase_ai_5"
AI_OPERATOR_BRIEFING_SOURCE_MODULE: str = "ai_operator_briefing"
AI_OPERATOR_BRIEFING_SCHEMA_VERSION: str = "v0"


# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------
class OperatorBriefingSection(str, Enum):
    """Closed section vocabulary for the operator briefing.

    Adding a new section is a deliberate code change AND a
    brief amendment. Sections are *descriptive labels* for
    *what part of the briefing* the entry belongs to - they
    NEVER carry direction / sizing / leverage / stop / target
    / risk-budget semantics.
    """

    EXECUTIVE_SUMMARY = "EXECUTIVE_SUMMARY"
    MARKET_INTELLIGENCE = "MARKET_INTELLIGENCE"
    DISCOVERY_QUALITY = "DISCOVERY_QUALITY"
    COVERAGE_AUDIT = "COVERAGE_AUDIT"
    POST_DISCOVERY_OUTCOME = "POST_DISCOVERY_OUTCOME"
    REJECT_ATTRIBUTION = "REJECT_ATTRIBUTION"
    SEVERE_MISS_TRIAGE = "SEVERE_MISS_TRIAGE"
    REPLAY_REFLECTION = "REPLAY_REFLECTION"
    CONTRADICTIONS = "CONTRADICTIONS"
    UNSUPPORTED_CLAIMS = "UNSUPPORTED_CLAIMS"
    DATA_GAPS = "DATA_GAPS"
    OPERATOR_ACTION_ITEMS = "OPERATOR_ACTION_ITEMS"


class OperatorBriefingAuthorityLevel(str, Enum):
    """Closed authority-level vocabulary for one operator
    briefing.

    No member of this enum grants *trade authority*. The
    maximum authority any briefing can reach is
    :attr:`COMMENTARY_SUBSTRATE` - the briefing is a
    *commentary substrate* an operator can read; it does NOT
    direct the Risk Engine, the Execution FSM, the Capital
    Flow Engine, or any other trade-authority surface.
    """

    COMMENTARY_SUBSTRATE = "COMMENTARY_SUBSTRATE"
    DEGRADED_PARTIAL_EVIDENCE = "DEGRADED_PARTIAL_EVIDENCE"
    DEGRADED_NO_EVIDENCE = "DEGRADED_NO_EVIDENCE"
    REJECTED = "REJECTED"


# ---------------------------------------------------------------------------
# Briefing event identifiers
# ---------------------------------------------------------------------------
#: Closed event-type vocabulary for Phase AI-5. None of these
#: are wired into the runtime hot path; they are emitted by
#: report / export / replay artefacts only.
AI_OPERATOR_BRIEFING_GENERATED: str = "AI_OPERATOR_BRIEFING_GENERATED"
AI_EVIDENCE_COMPRESSION_GENERATED: str = (
    "AI_EVIDENCE_COMPRESSION_GENERATED"
)
AI_UNSUPPORTED_CLAIMS_SUMMARIZED: str = (
    "AI_UNSUPPORTED_CLAIMS_SUMMARIZED"
)


# ---------------------------------------------------------------------------
# Section / finding records
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OperatorBriefingFinding:
    """One human-readable finding pinned to a closed section.

    The dataclass is descriptive only - it never carries
    direction / sizing / leverage / stop / target /
    risk-budget fields. The recursive forbidden-fields guard
    runs at every serialisation boundary.

    ``review_only`` is hard-pinned to ``True`` at every
    :meth:`to_dict` boundary. The flag exists so a downstream
    consumer can programmatically assert that the finding is
    a review-only operator action item, never a trade
    instruction.
    """

    finding_id: str
    section: OperatorBriefingSection
    headline: str
    detail: str
    classification: str
    evidence_refs: tuple[str, ...]
    related_claim_ids: tuple[str, ...]
    review_only: bool = True
    schema_version: str = AI_OPERATOR_BRIEFING_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "finding_id": str(self.finding_id),
            "section": self.section.value,
            "headline": str(self.headline),
            "detail": str(self.detail),
            "classification": str(self.classification),
            "evidence_refs": list(self.evidence_refs),
            "related_claim_ids": list(self.related_claim_ids),
            "review_only": True,
        }
        _assert_no_forbidden_fields(
            payload, context="OperatorBriefingFinding.to_dict"
        )
        return payload


@dataclass(frozen=True)
class OperatorBriefingSectionRecord:
    """One section of the operator briefing.

    A section is a deterministic grouping of findings. The
    grouping is fixed by the closed
    :class:`OperatorBriefingSection` vocabulary; the order of
    sections in the briefing is the enum's declaration order.
    """

    section: OperatorBriefingSection
    title: str
    body: str
    findings: tuple[OperatorBriefingFinding, ...]
    schema_version: str = AI_OPERATOR_BRIEFING_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "section": self.section.value,
            "title": str(self.title),
            "body": str(self.body),
            "findings": [f.to_dict() for f in self.findings],
        }
        _assert_no_forbidden_fields(
            payload, context="OperatorBriefingSectionRecord.to_dict"
        )
        return payload


# ---------------------------------------------------------------------------
# Operator briefing
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OperatorBriefing:
    """Frozen, evidence-cited, deterministic operator
    briefing.

    The briefing is JSON-serializable via :meth:`to_dict`.
    Every serialised payload re-pins the project-wide
    invariants (``mode=paper``, ``live_trading=False``,
    ``ai_output_is_commentary_only=True``,
    ``ai_output_can_be_training_label=False``,
    ``trade_authority=False``,
    ``auto_tuning_allowed=False``,
    ``phase_12_forbidden=True``,
    ``stateless_inference=True``,
    ``feedback_isolation=True``).
    """

    briefing_id: str
    created_at_utc: str
    reference_window: str
    source_bundle_id: str
    source_ai_output_id: str
    source_block_c_status: str
    source_report_paths: tuple[str, ...]
    sections: tuple[OperatorBriefingSectionRecord, ...]
    key_findings: tuple[str, ...]
    unsupported_claims: tuple[str, ...]
    contradictions: tuple[str, ...]
    data_gaps: tuple[str, ...]
    operator_review_items: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    notable_symbols: tuple[str, ...]
    risk_tags: tuple[str, ...]
    authority_level: OperatorBriefingAuthorityLevel
    forbidden_fields_stripped: tuple[str, ...]
    redacted_secret_count: int
    warnings: tuple[str, ...]
    consumer_contract: Mapping[str, Any]
    schema_version: str = AI_OPERATOR_BRIEFING_SCHEMA_VERSION
    source_phase: str = AI_OPERATOR_BRIEFING_SOURCE_PHASE
    source_module: str = AI_OPERATOR_BRIEFING_SOURCE_MODULE
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
        """Return a JSON-serializable payload for this briefing.

        The recursive forbidden-fields guard refuses to emit a
        payload that carries a trade-action /
        runtime-config-patch key at any nesting depth.
        """

        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "source_module": self.source_module,
            "briefing_id": str(self.briefing_id),
            "created_at_utc": str(self.created_at_utc),
            "reference_window": str(self.reference_window),
            "source_bundle_id": str(self.source_bundle_id),
            "source_ai_output_id": str(
                self.source_ai_output_id
            ),
            "source_block_c_status": str(
                self.source_block_c_status
            ),
            "source_report_paths": list(self.source_report_paths),
            "sections": [s.to_dict() for s in self.sections],
            "key_findings": list(self.key_findings),
            "unsupported_claims": list(self.unsupported_claims),
            "contradictions": list(self.contradictions),
            "data_gaps": list(self.data_gaps),
            "operator_review_items": list(
                self.operator_review_items
            ),
            "evidence_refs": list(self.evidence_refs),
            "notable_symbols": list(self.notable_symbols),
            "risk_tags": list(self.risk_tags),
            "authority_level": self.authority_level.value,
            "forbidden_fields_stripped": list(
                self.forbidden_fields_stripped
            ),
            "redacted_secret_count": int(
                self.redacted_secret_count
            ),
            "warnings": list(self.warnings),
            "consumer_contract": coerce_content(
                self.consumer_contract
            ),
            # Hard-pinned root-constraint flags.
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
            payload, context="OperatorBriefing.to_dict"
        )
        return payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _section_title(section: OperatorBriefingSection) -> str:
    """Closed mapping from section enum to operator-facing
    title."""

    titles: dict[OperatorBriefingSection, str] = {
        OperatorBriefingSection.EXECUTIVE_SUMMARY: (
            "Executive summary"
        ),
        OperatorBriefingSection.MARKET_INTELLIGENCE: (
            "Market intelligence"
        ),
        OperatorBriefingSection.DISCOVERY_QUALITY: (
            "Discovery quality"
        ),
        OperatorBriefingSection.COVERAGE_AUDIT: (
            "Coverage audit interpretation"
        ),
        OperatorBriefingSection.POST_DISCOVERY_OUTCOME: (
            "Post-discovery outcome"
        ),
        OperatorBriefingSection.REJECT_ATTRIBUTION: (
            "Reject-to-outcome attribution"
        ),
        OperatorBriefingSection.SEVERE_MISS_TRIAGE: (
            "Severe missed-tail triage"
        ),
        OperatorBriefingSection.REPLAY_REFLECTION: (
            "Replay / reflection summary"
        ),
        OperatorBriefingSection.CONTRADICTIONS: (
            "Contradictions"
        ),
        OperatorBriefingSection.UNSUPPORTED_CLAIMS: (
            "Unsupported claims"
        ),
        OperatorBriefingSection.DATA_GAPS: "Data gaps",
        OperatorBriefingSection.OPERATOR_ACTION_ITEMS: (
            "Operator review items (review-only)"
        ),
    }
    return titles.get(section, section.value)


def _section_for_claim_type(claim_type: str) -> OperatorBriefingSection:
    """Map a claim type string (Phase AI-2 :class:`AIClaimType`)
    to the most appropriate briefing section. Unknown / empty
    types default to ``MARKET_INTELLIGENCE`` so the operator
    can still see them.
    """

    text = str(claim_type or "").strip().upper()
    mapping: dict[str, OperatorBriefingSection] = {
        "REGIME": OperatorBriefingSection.MARKET_INTELLIGENCE,
        "NARRATIVE": OperatorBriefingSection.MARKET_INTELLIGENCE,
        "LIQUIDITY": OperatorBriefingSection.MARKET_INTELLIGENCE,
        "RISK": OperatorBriefingSection.DATA_GAPS,
        "COVERAGE": OperatorBriefingSection.COVERAGE_AUDIT,
        "OUTCOME": OperatorBriefingSection.POST_DISCOVERY_OUTCOME,
        "CONTRADICTION": OperatorBriefingSection.CONTRADICTIONS,
        "REPLAY_SUMMARY": OperatorBriefingSection.REPLAY_REFLECTION,
        "REFLECTION_SUMMARY": (
            OperatorBriefingSection.REPLAY_REFLECTION
        ),
        "EVIDENCE_QUALITY": (
            OperatorBriefingSection.DISCOVERY_QUALITY
        ),
    }
    return mapping.get(
        text, OperatorBriefingSection.MARKET_INTELLIGENCE
    )


def _resolve_authority_level(
    classification_counts: Mapping[str, int],
    *,
    has_block_c_blockers: bool,
    block_c_phase_12_forbidden: bool,
) -> OperatorBriefingAuthorityLevel:
    """Pick the briefing-level authority level.

    The level is **conservative** - it never escalates past
    what the underlying claims support. Specifically:

      - ``REJECTED`` if Block C reports a phase 12 leak
        (defensive: should never happen in v0);
      - ``DEGRADED_NO_EVIDENCE`` if every claim is rejected
        / contradicted / degraded / commentary-only;
      - ``DEGRADED_PARTIAL_EVIDENCE`` if some claims are
        supported but others are rejected / contradicted /
        degraded / no-evidence;
      - ``COMMENTARY_SUBSTRATE`` if every claim is supported
        AND no Block C blocker is present.

    The level NEVER grants trade authority - the briefing's
    ``trade_authority`` is hard-pinned to ``False`` at every
    :meth:`to_dict` boundary.
    """

    if not block_c_phase_12_forbidden:
        return OperatorBriefingAuthorityLevel.REJECTED
    supported = int(
        classification_counts.get(CLAIM_CLASS_SUPPORTED, 0)
    )
    rejected = int(
        classification_counts.get(CLAIM_CLASS_REJECTED, 0)
    )
    contradicted = int(
        classification_counts.get(CLAIM_CLASS_CONTRADICTED, 0)
    )
    degraded = int(
        classification_counts.get(
            CLAIM_CLASS_DEGRADED_NO_EVIDENCE, 0
        )
    )
    unsupported = int(
        classification_counts.get(CLAIM_CLASS_UNSUPPORTED, 0)
    )
    commentary = int(
        classification_counts.get(
            CLAIM_CLASS_COMMENTARY_ONLY, 0
        )
    )
    total = (
        supported
        + rejected
        + contradicted
        + degraded
        + unsupported
        + commentary
    )
    if total == 0:
        return OperatorBriefingAuthorityLevel.DEGRADED_NO_EVIDENCE
    if has_block_c_blockers:
        return OperatorBriefingAuthorityLevel.DEGRADED_PARTIAL_EVIDENCE
    if supported == 0:
        return OperatorBriefingAuthorityLevel.DEGRADED_NO_EVIDENCE
    if (
        rejected
        + contradicted
        + degraded
        + unsupported
        > 0
    ):
        return OperatorBriefingAuthorityLevel.DEGRADED_PARTIAL_EVIDENCE
    return OperatorBriefingAuthorityLevel.COMMENTARY_SUBSTRATE


def _build_section_findings(
    compressed_claims: Iterable[CompressedClaim],
) -> dict[
    OperatorBriefingSection, list[OperatorBriefingFinding]
]:
    """Group compressed claims into briefing sections.

    The grouping is deterministic: sections appear in the
    closed enum's declaration order; findings within a
    section appear in claim-id order so a deterministic
    builder produces deterministic bytes.
    """

    sections: dict[
        OperatorBriefingSection, list[OperatorBriefingFinding]
    ] = {section: [] for section in OperatorBriefingSection}

    for claim in compressed_claims:
        # Always surface unsupported / degraded / rejected /
        # contradicted claims in their dedicated sections so
        # a downstream consumer never misreads a demoted
        # claim as a key finding.
        if claim.classification == CLAIM_CLASS_CONTRADICTED:
            primary_section = OperatorBriefingSection.CONTRADICTIONS
        elif claim.classification == CLAIM_CLASS_REJECTED:
            primary_section = (
                OperatorBriefingSection.UNSUPPORTED_CLAIMS
            )
        elif claim.classification == CLAIM_CLASS_DEGRADED_NO_EVIDENCE:
            primary_section = (
                OperatorBriefingSection.UNSUPPORTED_CLAIMS
            )
        elif claim.classification == CLAIM_CLASS_UNSUPPORTED:
            primary_section = (
                OperatorBriefingSection.UNSUPPORTED_CLAIMS
            )
        elif claim.classification == CLAIM_CLASS_COMMENTARY_ONLY:
            primary_section = _section_for_claim_type(
                claim.claim_type
            )
        else:
            primary_section = _section_for_claim_type(
                claim.claim_type
            )

        finding = OperatorBriefingFinding(
            finding_id=f"finding:{claim.claim_id}",
            section=primary_section,
            headline=claim.claim_text,
            detail=(
                f"classification={claim.classification}; "
                f"citation_authority={claim.citation_authority_level}; "
                f"reality_check={claim.reality_check_status} "
                f"({claim.reality_check_authority_level})"
            ),
            classification=claim.classification,
            evidence_refs=claim.evidence_refs,
            related_claim_ids=(claim.claim_id,),
        )
        sections[primary_section].append(finding)

    return sections


def _build_data_gap_findings(
    data_gap_summary: Mapping[str, Any],
) -> list[OperatorBriefingFinding]:
    """Convert the compression report's data-gap summary into
    briefing findings."""

    findings: list[OperatorBriefingFinding] = []
    flagged = data_gap_summary.get("flagged", []) or []
    surfaced = data_gap_summary.get("surfaced_signals", {}) or {}
    if not isinstance(flagged, Sequence) or isinstance(
        flagged, (str, bytes)
    ):
        flagged_iter: list[str] = []
    else:
        flagged_iter = [str(f) for f in flagged]
    for index, key in enumerate(flagged_iter):
        value = surfaced.get(key) if isinstance(surfaced, Mapping) else None
        finding = OperatorBriefingFinding(
            finding_id=f"data_gap:{index}",
            section=OperatorBriefingSection.DATA_GAPS,
            headline=f"Data-gap signal flagged: {key}",
            detail=f"value={value}",
            classification="DATA_GAP",
            evidence_refs=(),
            related_claim_ids=(),
        )
        findings.append(finding)

    degraded_fact_count = int(
        data_gap_summary.get("degraded_fact_count", 0) or 0
    )
    if degraded_fact_count > 0:
        findings.append(
            OperatorBriefingFinding(
                finding_id="data_gap:degraded_fact_count",
                section=OperatorBriefingSection.DATA_GAPS,
                headline=(
                    f"Evidence bundle contains "
                    f"{degraded_fact_count} degraded fact(s)"
                ),
                detail=(
                    "Degraded facts were demoted by the Phase "
                    "AI-1 builder because they lacked "
                    "evidence_refs. They never appear in the "
                    "accepted *_facts collections."
                ),
                classification="DATA_GAP",
                evidence_refs=(),
                related_claim_ids=(),
            )
        )
    return findings


def _build_block_c_findings(
    block_c_report: Mapping[str, Any] | None,
) -> tuple[
    list[OperatorBriefingFinding], list[str], str, bool, bool
]:
    """Convert the Block C Integrated Checkpoint report into
    briefing findings.

    Returns ``(findings, operator_review_items, status,
    has_blockers, phase_12_forbidden_flag)``.
    """

    findings: list[OperatorBriefingFinding] = []
    review_items: list[str] = []
    if not isinstance(block_c_report, Mapping):
        return findings, review_items, "<missing>", False, True

    status = str(
        block_c_report.get("status", "<unknown>")
    ).strip()
    replay_status = str(
        block_c_report.get("replay_status", "")
    ).strip()
    reflection_status = str(
        block_c_report.get("reflection_status", "")
    ).strip()
    evidence_contract_status = str(
        block_c_report.get("evidence_contract_status", "")
    ).strip()
    accepted_claims_raw = block_c_report.get(
        "accepted_claim_count"
    )
    try:
        accepted_claims = (
            int(accepted_claims_raw)
            if accepted_claims_raw is not None
            else 0
        )
    except (TypeError, ValueError):
        accepted_claims = 0

    known_blockers_raw = block_c_report.get("known_blockers", [])
    if isinstance(known_blockers_raw, Sequence) and not isinstance(
        known_blockers_raw, (str, bytes)
    ):
        known_blockers = [str(b) for b in known_blockers_raw]
    else:
        known_blockers = []

    phase_12_forbidden_flag = bool(
        block_c_report.get("phase_12_forbidden", True)
    )
    auto_tuning_allowed_flag = bool(
        block_c_report.get("auto_tuning_allowed", False)
    )

    findings.append(
        OperatorBriefingFinding(
            finding_id="block_c:integrated_status",
            section=OperatorBriefingSection.EXECUTIVE_SUMMARY,
            headline=(
                f"Block C Integrated Checkpoint: status={status}"
            ),
            detail=(
                f"replay_status={replay_status}; "
                f"reflection_status={reflection_status}; "
                f"evidence_contract_status={evidence_contract_status}; "
                f"accepted_claim_count={accepted_claims}; "
                f"phase_12_forbidden={phase_12_forbidden_flag}; "
                f"auto_tuning_allowed={auto_tuning_allowed_flag}"
            ),
            classification="BLOCK_C_STATUS",
            evidence_refs=("report:block_c_integrated_checkpoint_report",),
            related_claim_ids=(),
        )
    )
    if replay_status:
        findings.append(
            OperatorBriefingFinding(
                finding_id="block_c:replay_status",
                section=OperatorBriefingSection.REPLAY_REFLECTION,
                headline=(
                    f"Replay status: {replay_status}"
                ),
                detail=(
                    "Replay component of Block C Integrated "
                    "Checkpoint."
                ),
                classification="REPLAY_STATUS",
                evidence_refs=(
                    "report:block_c_integrated_checkpoint_report",
                ),
                related_claim_ids=(),
            )
        )
    if reflection_status:
        findings.append(
            OperatorBriefingFinding(
                finding_id="block_c:reflection_status",
                section=OperatorBriefingSection.REPLAY_REFLECTION,
                headline=(
                    f"Reflection status: {reflection_status}"
                ),
                detail=(
                    "Reflection component of Block C "
                    "Integrated Checkpoint."
                ),
                classification="REFLECTION_STATUS",
                evidence_refs=(
                    "report:block_c_integrated_checkpoint_report",
                ),
                related_claim_ids=(),
            )
        )
    if evidence_contract_status:
        findings.append(
            OperatorBriefingFinding(
                finding_id="block_c:evidence_contract_status",
                section=OperatorBriefingSection.DISCOVERY_QUALITY,
                headline=(
                    "Evidence contract status: "
                    f"{evidence_contract_status}"
                ),
                detail=(
                    "Evidence-contract baseline component of "
                    "Block C Integrated Checkpoint."
                ),
                classification="EVIDENCE_CONTRACT_STATUS",
                evidence_refs=(
                    "report:block_c_integrated_checkpoint_report",
                ),
                related_claim_ids=(),
            )
        )

    for blocker in known_blockers:
        review_items.append(f"block_c_blocker:{blocker}")
        findings.append(
            OperatorBriefingFinding(
                finding_id=f"block_c:blocker:{blocker}",
                section=OperatorBriefingSection.OPERATOR_ACTION_ITEMS,
                headline=(
                    f"Block C known blocker: {blocker}"
                ),
                detail=(
                    "Reported by the Block C Integrated "
                    "Checkpoint as an open blocker; review-"
                    "only operator action item, NOT a trade "
                    "instruction."
                ),
                classification="BLOCK_C_BLOCKER",
                evidence_refs=(
                    "report:block_c_integrated_checkpoint_report",
                ),
                related_claim_ids=(),
            )
        )

    has_blockers = bool(known_blockers)
    return (
        findings,
        review_items,
        status,
        has_blockers,
        phase_12_forbidden_flag,
    )


def _build_data_gap_strings(
    data_gap_summary: Mapping[str, Any],
) -> list[str]:
    """Surface flagged data gaps as a flat string list (used
    by ``OperatorBriefing.data_gaps``)."""

    flagged = data_gap_summary.get("flagged", []) or []
    if not isinstance(flagged, Sequence) or isinstance(
        flagged, (str, bytes)
    ):
        return []
    out: list[str] = []
    surfaced = data_gap_summary.get("surfaced_signals", {}) or {}
    for key in flagged:
        text = str(key)
        value = (
            surfaced.get(text)
            if isinstance(surfaced, Mapping)
            else None
        )
        out.append(f"{text}={value}")
    degraded_fact_count = int(
        data_gap_summary.get("degraded_fact_count", 0) or 0
    )
    if degraded_fact_count > 0:
        out.append(
            f"degraded_fact_count={degraded_fact_count}"
        )
    return out


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
class OperatorBriefingBuilder:
    """Pure, deterministic builder for the
    :class:`OperatorBriefing`.

    The builder:

      - reads a serialised Phase AI-1 evidence bundle, a
        serialised Phase AI-4 :class:`AIIntelligenceOutput`,
        and an optional Block C Integrated Checkpoint
        report;
      - delegates claim classification to the Phase AI-5
        :class:`EvidenceCompressionReportBuilder`;
      - groups findings into the closed
        :class:`OperatorBriefingSection` vocabulary;
      - never invents a missing ``evidence_refs`` entry;
      - never paraphrases ``claim_text``;
      - strips any forbidden trade-action /
        runtime-config-patch field (defence in depth);
      - redacts any credential-shaped key (defence in depth);
      - never calls an LLM / DeepSeek;
      - never opens a network socket;
      - never reads or carries API secrets;
      - never reads private exchange / account state;
      - never authorises a trade decision;
      - never authorises auto-tuning.
    """

    def __init__(
        self,
        *,
        source_phase: str | None = None,
        compression_builder: (
            EvidenceCompressionReportBuilder | None
        ) = None,
    ) -> None:
        self._source_phase = (
            str(source_phase)
            if source_phase
            else AI_OPERATOR_BRIEFING_SOURCE_PHASE
        )
        self._compression_builder = (
            compression_builder
            or EvidenceCompressionReportBuilder()
        )

    @property
    def source_phase(self) -> str:
        return self._source_phase

    def build(
        self,
        *,
        briefing_id: str,
        created_at_utc: str,
        evidence_bundle: Mapping[str, Any],
        ai_intelligence_output: Mapping[str, Any],
        block_c_report: Mapping[str, Any] | None = None,
        reference_window: str | None = None,
        source_report_paths: Iterable[str] | None = None,
        warnings: Iterable[str] | None = None,
    ) -> tuple[OperatorBriefing, EvidenceCompressionReport]:
        """Build one :class:`OperatorBriefing` and the
        underlying :class:`EvidenceCompressionReport`.

        Returns a tuple ``(briefing, compression_report)``.
        Both artefacts are paper / report / read-only.
        """

        if not isinstance(evidence_bundle, Mapping):
            raise TypeError(
                "OperatorBriefingBuilder.build expects "
                "evidence_bundle to be a Mapping; got "
                f"{type(evidence_bundle).__name__}."
            )
        if not isinstance(ai_intelligence_output, Mapping):
            raise TypeError(
                "OperatorBriefingBuilder.build expects "
                "ai_intelligence_output to be a Mapping; got "
                f"{type(ai_intelligence_output).__name__}."
            )
        if block_c_report is not None and not isinstance(
            block_c_report, Mapping
        ):
            raise TypeError(
                "OperatorBriefingBuilder.build expects "
                "block_c_report to be a Mapping or None; got "
                f"{type(block_c_report).__name__}."
            )

        briefing_id_str = str(briefing_id).strip()
        if not briefing_id_str:
            raise ValueError(
                "OperatorBriefingBuilder.build requires a "
                "non-empty briefing_id."
            )
        created_at_utc_str = str(created_at_utc).strip()
        if not created_at_utc_str:
            raise ValueError(
                "OperatorBriefingBuilder.build requires a "
                "non-empty created_at_utc string."
            )

        # ------------------------------------------------------------------
        # 1. Build the underlying compression report
        # ------------------------------------------------------------------
        compression = self._compression_builder.build(
            report_id=f"compression:{briefing_id_str}",
            created_at_utc=created_at_utc_str,
            evidence_bundle=evidence_bundle,
            ai_intelligence_output=ai_intelligence_output,
            reference_window=reference_window,
            warnings=warnings,
        )

        # ------------------------------------------------------------------
        # 2. Aggregate counts for authority resolution
        # ------------------------------------------------------------------
        classification_counts: dict[str, int] = {}
        for claim in compression.compressed_claims:
            classification_counts[claim.classification] = (
                classification_counts.get(claim.classification, 0)
                + 1
            )

        # ------------------------------------------------------------------
        # 3. Block C interpretation
        # ------------------------------------------------------------------
        (
            block_c_findings,
            block_c_review_items,
            block_c_status,
            has_block_c_blockers,
            block_c_phase_12_forbidden_flag,
        ) = _build_block_c_findings(block_c_report)

        # ------------------------------------------------------------------
        # 4. Section assembly
        # ------------------------------------------------------------------
        section_findings = _build_section_findings(
            compression.compressed_claims
        )
        # Block C findings are merged into their target sections.
        for finding in block_c_findings:
            section_findings.setdefault(
                finding.section, []
            ).append(finding)

        # Data-gap findings come from the compression report's
        # data_gap_summary.
        data_gap_findings = _build_data_gap_findings(
            compression.data_gap_summary
        )
        for finding in data_gap_findings:
            section_findings.setdefault(
                finding.section, []
            ).append(finding)

        # Build executive summary findings - one for each of
        # the supported / unsupported / contradicted /
        # data_gaps headline counts.
        exec_findings: list[OperatorBriefingFinding] = []
        exec_findings.append(
            OperatorBriefingFinding(
                finding_id="executive_summary:claim_counts",
                section=OperatorBriefingSection.EXECUTIVE_SUMMARY,
                headline=(
                    f"Claim breakdown: "
                    f"supported={len(compression.supported_claims)}; "
                    f"degraded={len(compression.degraded_claims)}; "
                    f"rejected={len(compression.rejected_claims)}; "
                    f"contradicted={len(compression.contradictions)}; "
                    f"unsupported={len(compression.unsupported_claims)}"
                ),
                detail=(
                    "Claim classifications computed by the "
                    "Phase AI-5 EvidenceCompressionReportBuilder "
                    "from the Phase AI-2 citation authority and "
                    "the Phase AI-3 Reality Check status. The "
                    "claim text is preserved verbatim; the "
                    "classifications are conservative (a claim "
                    "never escalates past its strongest input "
                    "axis)."
                ),
                classification="EXECUTIVE_SUMMARY",
                evidence_refs=tuple(compression.evidence_refs),
                related_claim_ids=(),
            )
        )
        section_findings[
            OperatorBriefingSection.EXECUTIVE_SUMMARY
        ] = (
            exec_findings
            + list(
                section_findings.get(
                    OperatorBriefingSection.EXECUTIVE_SUMMARY, []
                )
            )
        )

        # Build section records in enum-declaration order.
        sections: list[OperatorBriefingSectionRecord] = []
        for section in OperatorBriefingSection:
            findings = section_findings.get(section, [])
            # Deterministic ordering inside each section.
            findings_sorted = tuple(
                sorted(findings, key=lambda f: f.finding_id)
            )
            body = self._render_section_body(
                section=section,
                findings=findings_sorted,
                compression=compression,
                block_c_status=block_c_status,
            )
            sections.append(
                OperatorBriefingSectionRecord(
                    section=section,
                    title=_section_title(section),
                    body=body,
                    findings=findings_sorted,
                )
            )

        # ------------------------------------------------------------------
        # 5. Top-level lists
        # ------------------------------------------------------------------
        # Key findings: ONLY supported claims. Unsupported /
        # degraded / rejected / contradicted claims NEVER
        # appear here.
        key_findings = tuple(
            sorted(set(compression.supported_claims))
        )
        unsupported_claims = tuple(
            sorted(set(compression.unsupported_claims))
        )
        contradictions = tuple(
            sorted(set(compression.contradictions))
        )
        data_gaps = tuple(
            _build_data_gap_strings(compression.data_gap_summary)
        )

        operator_review_items: list[str] = []
        # Operator action items are review-only annotations:
        # any unsupported / contradicted / rejected claim is
        # surfaced; any data-gap signal is surfaced; any
        # Block C blocker is surfaced.
        for cid in unsupported_claims:
            operator_review_items.append(
                f"review_unsupported_claim:{cid}"
            )
        for cid in contradictions:
            operator_review_items.append(
                f"review_contradiction:{cid}"
            )
        for gap in data_gaps:
            operator_review_items.append(
                f"review_data_gap:{gap}"
            )
        for item in block_c_review_items:
            operator_review_items.append(item)
        # Defensive: dedupe while preserving order.
        deduped: list[str] = []
        seen: set[str] = set()
        for item in operator_review_items:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        operator_review_items = deduped

        authority_level = _resolve_authority_level(
            classification_counts,
            has_block_c_blockers=has_block_c_blockers,
            block_c_phase_12_forbidden=(
                block_c_phase_12_forbidden_flag
            ),
        )

        # ------------------------------------------------------------------
        # 6. Defence-in-depth strip + redact at the briefing
        #    boundary too. The compression builder already did
        #    this; we re-run the helpers against the AI output
        #    here so the briefing's audit trail is complete.
        # ------------------------------------------------------------------
        _, briefing_stripped_paths = strip_forbidden_fields(
            dict(ai_intelligence_output)
        )
        _, briefing_redacted_count = redact_secrets(
            dict(ai_intelligence_output)
        )

        # ------------------------------------------------------------------
        # 7. Source paths
        # ------------------------------------------------------------------
        paths_list: list[str] = []
        if source_report_paths is not None:
            for p in source_report_paths:
                if p is None:
                    continue
                text = str(p).strip()
                if text:
                    paths_list.append(text)
        # Add an implicit reference to the Block C report path
        # name if a block C report was supplied.
        if block_c_report is not None and not any(
            "block_c_integrated_checkpoint_report" in p
            for p in paths_list
        ):
            paths_list.append(
                "report:block_c_integrated_checkpoint_report"
            )

        # ------------------------------------------------------------------
        # 8. Aggregate warnings
        # ------------------------------------------------------------------
        all_warnings: list[str] = list(compression.warnings)
        if briefing_stripped_paths:
            all_warnings.append(
                "forbidden_fields_stripped_in_briefing:"
                f"{len(briefing_stripped_paths)}"
            )
        if briefing_redacted_count > 0:
            all_warnings.append(
                f"secrets_redacted_in_briefing:"
                f"{briefing_redacted_count}"
            )

        consumer_contract = {
            "allowed_consumers": list(ALLOWED_CONSUMERS),
            "forbidden_consumers": list(FORBIDDEN_CONSUMERS),
            "lookahead_policy_flags": list(LOOKAHEAD_POLICY_FLAGS),
        }

        briefing = OperatorBriefing(
            briefing_id=briefing_id_str,
            created_at_utc=created_at_utc_str,
            reference_window=compression.reference_window,
            source_bundle_id=compression.source_bundle_id,
            source_ai_output_id=compression.source_ai_output_id,
            source_block_c_status=block_c_status,
            source_report_paths=tuple(paths_list),
            sections=tuple(sections),
            key_findings=key_findings,
            unsupported_claims=unsupported_claims,
            contradictions=contradictions,
            data_gaps=data_gaps,
            operator_review_items=tuple(operator_review_items),
            evidence_refs=compression.evidence_refs,
            notable_symbols=compression.notable_symbols,
            risk_tags=compression.risk_tags,
            authority_level=authority_level,
            forbidden_fields_stripped=tuple(
                briefing_stripped_paths
            ),
            redacted_secret_count=int(briefing_redacted_count),
            warnings=tuple(all_warnings),
            consumer_contract=consumer_contract,
        )
        return briefing, compression

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _render_section_body(
        self,
        *,
        section: OperatorBriefingSection,
        findings: tuple[OperatorBriefingFinding, ...],
        compression: EvidenceCompressionReport,
        block_c_status: str,
    ) -> str:
        if section is OperatorBriefingSection.EXECUTIVE_SUMMARY:
            return (
                "Executive summary of the AI-5 operator "
                f"briefing for bundle "
                f"{compression.source_bundle_id} (reference "
                f"window {compression.reference_window}). "
                f"Block C Integrated Checkpoint status="
                f"{block_c_status}. AI intelligence summary: "
                f"{compression.summary}"
            )
        if section is OperatorBriefingSection.MARKET_INTELLIGENCE:
            return (
                "Market-intelligence claims emitted by the "
                "Phase AI-4 sandbox runner that cleared the "
                "Phase AI-2 citation contract and the Phase "
                "AI-3 Reality Check engine. Each entry is "
                "commentary substrate only."
            )
        if section is OperatorBriefingSection.DISCOVERY_QUALITY:
            return (
                "Discovery-quality observations sourced from "
                "the Phase AI-1 evidence bundle and the "
                "evidence-contract status reported by the "
                "Block C Integrated Checkpoint."
            )
        if section is OperatorBriefingSection.COVERAGE_AUDIT:
            return (
                "Coverage-audit interpretation - sourced from "
                "Phase 11C.1C-C-B-B-B-D historical mover "
                "coverage backfill and the Phase 11C.1C-C-B-B-B-D "
                "mover capture recall audit. Read-only."
            )
        if section is OperatorBriefingSection.POST_DISCOVERY_OUTCOME:
            return (
                "Post-discovery outcome - sourced from "
                "Phase 11C.1C-C-B-B-B-D-B post-discovery "
                "outcome metrics. Read-only."
            )
        if section is OperatorBriefingSection.REJECT_ATTRIBUTION:
            return (
                "Reject-to-outcome attribution - sourced from "
                "Phase 11C.1C-C-B-B-B-D-C-A reject-to-outcome "
                "attribution. Read-only."
            )
        if section is OperatorBriefingSection.SEVERE_MISS_TRIAGE:
            return (
                "Severe missed-tail triage - sourced from "
                "Phase 11C.1C-C-B-B-B-D-C-B severe missed tail "
                "triage. Read-only."
            )
        if section is OperatorBriefingSection.REPLAY_REFLECTION:
            return (
                "Replay / reflection summary - sourced from "
                "the Block C Integrated Checkpoint's replay "
                "and reflection components."
            )
        if section is OperatorBriefingSection.CONTRADICTIONS:
            return (
                "Claims that contradict the Phase AI-1 "
                "evidence bundle's frozen facts. These are "
                "NEVER promoted to key findings."
            )
        if section is OperatorBriefingSection.UNSUPPORTED_CLAIMS:
            return (
                "Claims that did not reach SUPPORTED_INTELLIGENCE "
                "after Phase AI-2 citation validation and "
                "Phase AI-3 Reality Check. These are NEVER "
                "promoted to key findings."
            )
        if section is OperatorBriefingSection.DATA_GAPS:
            return (
                "Data-gap signals surfaced by the Phase AI-1 "
                "bundle. Read-only operator annotations."
            )
        if section is OperatorBriefingSection.OPERATOR_ACTION_ITEMS:
            return (
                "Review-only operator action items. NOT "
                "trade actions. NOT runtime-config patches. "
                "NOT auto-tuning instructions. The Risk "
                "Engine remains the single trade-decision "
                "gate."
            )
        return ""


def build_operator_briefing(
    *,
    briefing_id: str,
    created_at_utc: str,
    evidence_bundle: Mapping[str, Any],
    ai_intelligence_output: Mapping[str, Any],
    block_c_report: Mapping[str, Any] | None = None,
    reference_window: str | None = None,
    source_report_paths: Iterable[str] | None = None,
    warnings: Iterable[str] | None = None,
) -> tuple[OperatorBriefing, EvidenceCompressionReport]:
    """Convenience wrapper that constructs a builder and calls
    :meth:`OperatorBriefingBuilder.build`.
    """

    return OperatorBriefingBuilder().build(
        briefing_id=briefing_id,
        created_at_utc=created_at_utc,
        evidence_bundle=evidence_bundle,
        ai_intelligence_output=ai_intelligence_output,
        block_c_report=block_c_report,
        reference_window=reference_window,
        source_report_paths=source_report_paths,
        warnings=warnings,
    )


def render_operator_briefing_markdown(
    briefing: OperatorBriefing,
) -> str:
    """Render a deterministic Markdown view of the briefing.

    The Markdown is paper / report / read-only. It NEVER
    contains a trade-action / runtime-config-patch field; the
    recursive forbidden-fields guard runs at the underlying
    :meth:`OperatorBriefing.to_dict` boundary.
    """

    payload = briefing.to_dict()
    lines: list[str] = []
    lines.append("# AI Operator Briefing v0")
    lines.append("")
    lines.append(
        "> **Status:** paper / report / sandbox-only. **NOT** "
        "live trading. **NOT** trade authority. **NOT** "
        "auto-tuning. **NOT** Phase 12. **NOT** real Telegram "
        "outbound."
    )
    lines.append("")
    lines.append(
        f"- **briefing_id:** `{payload['briefing_id']}`"
    )
    lines.append(
        f"- **created_at_utc:** `{payload['created_at_utc']}`"
    )
    lines.append(
        f"- **reference_window:** "
        f"`{payload['reference_window']}`"
    )
    lines.append(
        f"- **source_bundle_id:** "
        f"`{payload['source_bundle_id']}`"
    )
    lines.append(
        f"- **source_ai_output_id:** "
        f"`{payload['source_ai_output_id']}`"
    )
    lines.append(
        f"- **source_block_c_status:** "
        f"`{payload['source_block_c_status']}`"
    )
    lines.append(
        f"- **authority_level:** "
        f"`{payload['authority_level']}`"
    )
    lines.append("")

    for section_payload in payload["sections"]:
        section_value = section_payload["section"]
        lines.append(f"## {section_payload['title']}")
        lines.append("")
        if section_payload["body"]:
            lines.append(section_payload["body"])
            lines.append("")
        if not section_payload["findings"]:
            lines.append("_No findings in this section._")
            lines.append("")
            continue
        for finding in section_payload["findings"]:
            lines.append(
                f"- **{finding['finding_id']}** — "
                f"{finding['headline']}"
            )
            lines.append(f"  - section: `{section_value}`")
            lines.append(
                f"  - classification: "
                f"`{finding['classification']}`"
            )
            lines.append(
                f"  - evidence_refs: "
                f"`{', '.join(finding['evidence_refs'])}`"
            )
            lines.append(
                f"  - related_claim_ids: "
                f"`{', '.join(finding['related_claim_ids'])}`"
            )
            lines.append(
                f"  - review_only: `{finding['review_only']}`"
            )
            lines.append(f"  - detail: {finding['detail']}")
        lines.append("")

    lines.append("## Top-level summaries")
    lines.append("")
    lines.append(
        f"- **key_findings (supported claim ids):** "
        f"`{payload['key_findings']}`"
    )
    lines.append(
        f"- **unsupported_claims:** "
        f"`{payload['unsupported_claims']}`"
    )
    lines.append(
        f"- **contradictions:** `{payload['contradictions']}`"
    )
    lines.append(
        f"- **data_gaps:** `{payload['data_gaps']}`"
    )
    lines.append(
        f"- **operator_review_items (review-only):** "
        f"`{payload['operator_review_items']}`"
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
        f"`{payload['forbidden_fields_stripped']}`"
    )
    lines.append(
        f"- **redacted_secret_count:** "
        f"`{payload['redacted_secret_count']}`"
    )
    lines.append(
        f"- **warnings:** `{payload['warnings']}`"
    )
    lines.append("")
    lines.append("## Consumer contract")
    lines.append("")
    contract = payload["consumer_contract"]
    lines.append(
        f"- **allowed_consumers:** "
        f"`{contract.get('allowed_consumers', [])}`"
    )
    lines.append(
        f"- **forbidden_consumers:** "
        f"`{contract.get('forbidden_consumers', [])}`"
    )
    lines.append(
        f"- **lookahead_policy_flags:** "
        f"`{contract.get('lookahead_policy_flags', [])}`"
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
        "The Risk Engine remains the single trade-decision "
        "gate."
    )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "AI_EVIDENCE_COMPRESSION_GENERATED",
    "AI_OPERATOR_BRIEFING_GENERATED",
    "AI_OPERATOR_BRIEFING_SCHEMA_VERSION",
    "AI_OPERATOR_BRIEFING_SOURCE_MODULE",
    "AI_OPERATOR_BRIEFING_SOURCE_PHASE",
    "AI_UNSUPPORTED_CLAIMS_SUMMARIZED",
    "OperatorBriefing",
    "OperatorBriefingAuthorityLevel",
    "OperatorBriefingBuilder",
    "OperatorBriefingFinding",
    "OperatorBriefingSection",
    "OperatorBriefingSectionRecord",
    "build_operator_briefing",
    "render_operator_briefing_markdown",
]
