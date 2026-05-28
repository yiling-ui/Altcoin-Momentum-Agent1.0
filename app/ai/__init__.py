"""Phase AI-1 - AI Evidence Bundle Builder v0.

The :mod:`app.ai` package exposes the AI Layer's *only* allowed
read surface: a frozen, evidence-cited, deterministic
``AIEvidenceBundle`` constructed from Truth Layer artefacts at
call time.

The package implements the four root constraints of
``docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md``:

  1. **Responsibility Isolation** - the bundle never carries a
     trade-action / direction / sizing / risk-budget / runtime-
     config-patch field.
  2. **Stateless Inference** - every bundle is built from the
     supplied frozen Truth Layer inputs only; it never reads
     previous AI answers, chat history, private account state,
     or API secrets.
  3. **Hard Rule Anchoring** - every accepted fact must carry
     ``evidence_refs``; facts without ``evidence_refs`` are
     degraded and surfaced as warnings, never accepted as fact.
  4. **Feedback Isolation** - the bundle pins
     ``ai_output_is_commentary_only=True`` and
     ``ai_output_can_be_training_label=False`` so AI output can
     never become a training label or a runtime fact.

The package is paper / report / read-only:

  - It does **NOT** authorise live trading.
  - It does **NOT** authorise auto-tuning.
  - It does **NOT** call DeepSeek / any LLM.
  - It does **NOT** open any network socket.
  - It does **NOT** read or carry API secrets, private account
    state, ``listenKey``, signed endpoints, or chat history.
  - It does **NOT** mutate ``events.db`` or any runtime knob.

The package re-exports the public surface of
:mod:`app.ai.evidence_bundle`. See that module's docstring for
the full safety boundary.
"""

from __future__ import annotations

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
]
