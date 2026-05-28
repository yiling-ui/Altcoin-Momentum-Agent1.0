"""AMA-RT AI Layer - paper / read-only.

The :mod:`app.ai` package exposes the AI Layer's *only*
allowed read surface and its *only* allowed claim-citation
contract:

  - **Phase AI-1** :mod:`app.ai.evidence_bundle` - the
    deterministic, evidence-cited, JSON-serializable
    ``AIEvidenceBundle`` constructed from Truth-Layer
    artefacts at call time. Every later AI / DeepSeek / LLM
    call MUST receive a freshly built bundle and infer ONLY
    from that bundle.
  - **Phase AI-2** :mod:`app.ai.claim_contract` - the
    claim-level *evidence citation contract*. Every AI claim
    MUST cite Truth-Layer evidence via
    :data:`SUPPORTED_EVIDENCE_REF_FORMATS`; claims without
    ``evidence_refs`` are demoted to
    :attr:`AIClaimAuthorityLevel.DEGRADED_NO_EVIDENCE`;
    claims with invalid ``evidence_refs`` are rejected
    (strict mode) or demoted (non-strict mode); the maximum
    authority any claim can reach is
    :attr:`AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE`,
    which is *commentary substrate* only.
  - **Phase AI-3** :mod:`app.ai.reality_check` - the
    *deterministic / statistical* Reality Check Layer that
    cross-verifies an AI claim against the Phase AI-1
    Evidence Bundle's frozen facts. Having ``evidence_refs``
    is necessary but not sufficient; a claim must also be
    supported by the bundle's market / system-behavior /
    outcome facts. Reality Check produces a closed
    :class:`AIRealityCheckStatus` and a downgraded
    :class:`AIRealityCheckAuthorityLevel`, never invokes an
    LLM, never opens a network socket, and never authorises
    a trade decision or auto-tuning. The maximum authority a
    claim can reach after Reality Check is
    :attr:`AIRealityCheckAuthorityLevel.SUPPORTED_INTELLIGENCE`,
    which is *commentary substrate* only.

Both phases enforce the four AI root constraints from
``docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md``:

  1. **Responsibility Isolation** - no trade-action /
     direction / sizing / risk-budget / runtime-config-patch
     field is ever emitted.
  2. **Stateless Inference** - every call is independent;
     previous AI answers, chat history, private account
     state, and API secrets are rejected at intake.
  3. **Hard Rule Anchoring** - no ``evidence_refs`` => no
     accepted AI conclusion. Claims without citations are
     demoted; claims with malformed citations are rejected.
  4. **Feedback Isolation** - AI output is *commentary*,
     never truth, never a training label.

This package is paper / report / read-only:

  - It does **NOT** authorise live trading.
  - It does **NOT** authorise auto-tuning.
  - It does **NOT** call DeepSeek / any LLM.
  - It does **NOT** open any network socket.
  - It does **NOT** read or carry API secrets, private
    account state, ``listenKey``, signed endpoints, or chat
    history.
  - It does **NOT** mutate ``events.db`` or any runtime knob.
  - **Phase 12 remains FORBIDDEN.**

The Risk Engine remains the single trade-decision gate.
"""

from __future__ import annotations

from app.ai.claim_contract import (
    AI_CLAIM_CONTRACT_SCHEMA_VERSION,
    AI_CLAIM_CONTRACT_SOURCE_MODULE,
    AI_CLAIM_CONTRACT_SOURCE_PHASE,
    FORBIDDEN_CLAIM_FIELDS,
    SUPPORTED_EVIDENCE_REF_FORMATS,
    SUPPORTED_EVIDENCE_REF_PREFIXES,
    AIClaim,
    AIClaimAuthorityLevel,
    AIClaimCitationResult,
    AIClaimCitationValidator,
    AIClaimInput,
    AIClaimType,
    validate_ai_claims,
)
from app.ai.reality_check import (
    AI_REALITY_CHECK_SCHEMA_VERSION,
    AI_REALITY_CHECK_SOURCE_MODULE,
    AI_REALITY_CHECK_SOURCE_PHASE,
    FORBIDDEN_REALITY_CHECK_FIELDS,
    AIRealityCheckAuthorityLevel,
    AIRealityCheckCategory,
    AIRealityCheckEngine,
    AIRealityCheckInput,
    AIRealityCheckResult,
    AIRealityCheckStatus,
    reality_check_claim,
)
from app.ai.evidence_bundle import (
    AI_EVIDENCE_BUNDLE_SCHEMA_VERSION,
    AI_EVIDENCE_BUNDLE_SOURCE_MODULE,
    AI_EVIDENCE_BUNDLE_SOURCE_PHASE,
    ALLOWED_CONSUMERS,
    CREDENTIAL_LIKE_KEY_TOKENS,
    FORBIDDEN_AI_OUTPUT_FIELDS,
    FORBIDDEN_CONSUMERS,
    FORBIDDEN_INPUT_KEYS,
    LOOKAHEAD_POLICY_FLAGS,
    AIEvidenceBundle,
    AIEvidenceBundleBuilder,
    AIEvidenceBundleBuildStatus,
    AIEvidenceBundleFact,
    AIEvidenceBundleFactInput,
    AIEvidenceBundleTaskType,
    ForbiddenAIInputError,
    build_ai_evidence_bundle,
)
__all__ = [
    # Phase AI-1 - AI Evidence Bundle Builder v0.
    "AI_EVIDENCE_BUNDLE_SCHEMA_VERSION",
    "AI_EVIDENCE_BUNDLE_SOURCE_MODULE",
    "AI_EVIDENCE_BUNDLE_SOURCE_PHASE",
    "ALLOWED_CONSUMERS",
    "CREDENTIAL_LIKE_KEY_TOKENS",
    "FORBIDDEN_AI_OUTPUT_FIELDS",
    "FORBIDDEN_CONSUMERS",
    "FORBIDDEN_INPUT_KEYS",
    "LOOKAHEAD_POLICY_FLAGS",
    "AIEvidenceBundle",
    "AIEvidenceBundleBuilder",
    "AIEvidenceBundleBuildStatus",
    "AIEvidenceBundleFact",
    "AIEvidenceBundleFactInput",
    "AIEvidenceBundleTaskType",
    "ForbiddenAIInputError",
    "build_ai_evidence_bundle",
    # Phase AI-2 - Truth Layer / AI Evidence Citation Contract v0.
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
    # Phase AI-3 - Reality Check Layer v0.
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
