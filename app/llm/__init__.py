"""Phase 10C - LLM Guarded Interpreter package (Issue #10 Part 3).

A receive-only, schema-validated, sandboxed LLM intelligence layer.
The interpreter compresses community / narrative / catalyst text into
a small, **strictly typed** intelligence payload (Spec §22). The
output is *informational only*: it never carries a trade direction, a
leverage, a target price, an order, a stop, or any other field that
could move money. The Risk Engine remains the single gate.

Public surface
--------------

    LLMGuardedInterpreter        top-level orchestrator
    LLMInterpreterConfig         tunable thresholds
    LLMInterpretationInput       caller input bundle
    LLMInterpretationResult      result value object (JSON-safe)
    HypeStage / EvidenceQuality / CatalystStrength / LLMRiskTag
                                 typed enum vocabularies
    LLMDegradedReason            typed degraded-reason vocabulary
    LLMTokenBucket               Spec §22.4 anomaly-score throttle

    LLMClientBase                ABC for an LLM transport
    FakeLLMClient                deterministic in-memory client used
                                 by tests + the boot self-check
    DeepSeekClient               skeleton transport (refuses without
                                 explicit env-var key + llm_enabled=True)
    TransportError / TimeoutError / SchemaRejection
                                 typed transport-level errors

    LLMCache                     in-memory cache keyed on
                                 (input_hash, prompt_version,
                                  schema_version, model_name)

    SYSTEM_PROMPT_TEMPLATE       fixed system prompt
    PROMPT_VERSION               version constant
    SCHEMA_VERSION               JSON schema version constant
    LLM_OUTPUT_WHITELIST         frozenset of allowed output fields
    LLM_FORBIDDEN_FIELDS         frozenset of fields that must be
                                 stripped if a model returns them

    validate_llm_output          schema validator
    sanitize_input_text          prompt-injection-aware input cleaner
    detect_prompt_injection      pure-function injection sniffer
    enforce_field_whitelist      remove non-whitelisted keys
    strip_forbidden_fields       remove + record trade-action fields

Phase 10C boundary (every clause enforced by tests)
---------------------------------------------------

1. **No real network call by default.** The default transport is
   :class:`FakeLLMClient`. The :class:`DeepSeekClient` skeleton has no
   socket / SDK / HTTP code paths and refuses to start unless
   ``llm_enabled=True`` AND a non-empty API key is supplied **at
   call-time** by the caller. Phase 10C ships no production transport.
2. **No write surface.** No file under ``app/llm/`` defines
   ``create_order`` / ``cancel_order`` / ``set_leverage`` /
   ``set_margin_mode``.
3. **No LLM-driven trade action.** The interpreter never returns a
   ``direction`` / ``leverage`` / ``position_size`` / ``target_price``
   / ``order_type`` / ``stop_price`` / ``take_profit`` /
   ``should_buy`` / ``should_short`` / ``trade_decision`` /
   ``entry`` / ``exit`` / ``liquidation_price`` / ``margin_mode`` /
   ``risk_budget`` / ``order`` / ``signal_to_trade``. If a model emits
   any of those, the field is stripped, recorded in
   ``stripped_fields``, and the result is degraded.
4. **No state-mutating component import.** The package does NOT
   import :class:`RiskEngine`, :class:`ExecutionFSMDriver`,
   :class:`Reconciler`, :class:`CapitalFlowEngine`,
   :class:`IncidentRepository`, :class:`MockExchangeClient`,
   :class:`BinanceClient`, :class:`MarketDataBuffer`,
   :class:`TelegramCommandCenter`, :class:`RegimeEngine`, or any
   Telegram outbound surface (Phase 10D owns that).
5. **No ``os.environ`` reads.** Credentials must be passed in
   explicitly by the caller. The package is a library, not an
   environment consumer.
6. **No hard-coded secret.** No ``api_key`` / ``api_secret`` /
   ``bot_token`` parameter or concrete literal lives anywhere under
   ``app/llm/``.
7. **No exception escapes.** The interpreter wraps every transport /
   schema / guardrail failure in a degraded result; it NEVER raises
   into the caller.
8. **No Telegram outbound.** Phase 10D owns Telegram outbound. The
   only Phase 10C event surface is ``EventRepository.append_event``
   for ``LLM_INTERPRETED`` / ``LLM_DEGRADED`` / ``LLM_SCHEMA_REJECTED``.
9. **No Issue #10 Part 10D work.** No export commands, no
   document outbound, no operator-allow-list bot.
10. **The Phase 1 safety lock remains in force.** The five flags
    stay locked at config-load time. Phase 10C is configuration-aware
    but never flips a flag itself.

Spec references
---------------

- Spec §22.1 Input contract
- Spec §22.2 Output JSON Schema
- Spec §22.3 LLM Guardrails
- Spec §22.4 Token throttle (anomaly_score thresholds)
"""

from app.llm.cache import LLMCache, LLMCacheEntry
from app.llm.client import (
    DeepSeekClient,
    FakeLLMClient,
    LLMClientBase,
    LLMTimeoutError,
    SchemaRejection,
    TransportError,
)
from app.llm.guardrails import (
    LLM_FORBIDDEN_FIELDS,
    LLM_OUTPUT_WHITELIST,
    detect_prompt_injection,
    enforce_field_whitelist,
    sanitize_input_text,
    strip_forbidden_fields,
)
from app.llm.interpreter import (
    LLMGuardedInterpreter,
    LLMInterpreterConfig,
    LLMTokenBucket,
)
from app.llm.models import (
    CatalystStrength,
    EvidenceQuality,
    HypeStage,
    LLMDegradedReason,
    LLMInterpretationInput,
    LLMInterpretationResult,
    LLMRiskTag,
    TokenThrottleTier,
)
from app.llm.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT_TEMPLATE,
    build_user_prompt,
)
from app.llm.schema import (
    LLM_OUTPUT_SCHEMA,
    SCHEMA_VERSION,
    SchemaValidationError,
    validate_llm_output,
)

__all__ = [
    # Engine
    "LLMGuardedInterpreter",
    "LLMInterpreterConfig",
    "LLMTokenBucket",
    # Value objects
    "LLMInterpretationInput",
    "LLMInterpretationResult",
    # Vocabularies
    "HypeStage",
    "EvidenceQuality",
    "CatalystStrength",
    "LLMRiskTag",
    "LLMDegradedReason",
    "TokenThrottleTier",
    # Transport
    "LLMClientBase",
    "FakeLLMClient",
    "DeepSeekClient",
    "TransportError",
    "LLMTimeoutError",
    "SchemaRejection",
    # Cache
    "LLMCache",
    "LLMCacheEntry",
    # Guardrails / prompts / schema
    "LLM_OUTPUT_WHITELIST",
    "LLM_FORBIDDEN_FIELDS",
    "LLM_OUTPUT_SCHEMA",
    "PROMPT_VERSION",
    "SCHEMA_VERSION",
    "SYSTEM_PROMPT_TEMPLATE",
    "build_user_prompt",
    "sanitize_input_text",
    "detect_prompt_injection",
    "enforce_field_whitelist",
    "strip_forbidden_fields",
    "validate_llm_output",
    "SchemaValidationError",
]
