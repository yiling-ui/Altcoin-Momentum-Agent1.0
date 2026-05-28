"""Phase 11C.1C-C-B-B-B-E-C - Evidence Contract Baseline v0.

The :mod:`app.evidence` package exposes the project's first
unified ``evidence_refs`` contract for the report / replay /
reflection / discovery-quality / post-discovery / severe-miss /
reject-attribution surfaces.

The Evidence Contract Baseline v0 is paper / report / evidence
only:

  - It does **NOT** authorise live trading.
  - It does **NOT** authorise auto-tuning.
  - It does **NOT** call DeepSeek / any LLM.
  - It does **NOT** consume chat history.
  - It does **NOT** mutate ``events.db`` or any runtime knob.

The package re-exports the public surface of
:mod:`app.evidence.evidence_contract`. See that module's
docstring for the full safety boundary.
"""

from __future__ import annotations

from app.evidence.evidence_contract import (
    EVIDENCE_CONTRACT_BASELINE_SCHEMA_VERSION,
    EVIDENCE_CONTRACT_SOURCE_MODULE,
    EVIDENCE_CONTRACT_SOURCE_PHASE,
    FORBIDDEN_EVIDENCE_PAYLOAD_KEYS,
    ClaimStatus,
    EvidenceClaim,
    EvidenceClaimInput,
    EvidenceContractResult,
    EvidenceContractValidator,
    EvidenceRef,
    EvidenceRefType,
    parse_evidence_ref,
    validate_claims,
)

__all__ = [
    "EVIDENCE_CONTRACT_BASELINE_SCHEMA_VERSION",
    "EVIDENCE_CONTRACT_SOURCE_MODULE",
    "EVIDENCE_CONTRACT_SOURCE_PHASE",
    "FORBIDDEN_EVIDENCE_PAYLOAD_KEYS",
    "ClaimStatus",
    "EvidenceClaim",
    "EvidenceClaimInput",
    "EvidenceContractResult",
    "EvidenceContractValidator",
    "EvidenceRef",
    "EvidenceRefType",
    "parse_evidence_ref",
    "validate_claims",
]
