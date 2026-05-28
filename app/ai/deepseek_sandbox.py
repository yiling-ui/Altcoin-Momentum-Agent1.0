"""Phase AI-4 - DeepSeek Offline Sandbox v0.

The AI Layer's first **outbound-capable** runtime artefact.
This module ships:

  - :class:`DeepSeekSandboxConfig` - the closed, disabled-by-
    default configuration carrying every safety gate the
    sandbox honours;
  - :class:`DeepSeekSandboxInput` - the closed input record a
    runner consumes (a frozen Phase AI-1 evidence bundle plus
    a task type plus an operator instruction);
  - :class:`DeepSeekProviderProtocol` - the closed provider
    interface a transport must implement;
  - :class:`FakeDeepSeekProvider` - the deterministic in-memory
    provider used by tests AND by every offline run that has
    ``outbound_enabled=False`` (the default);
  - :class:`OptionalDeepSeekHTTPProvider` - the *refusal-only*
    skeleton for the future real DeepSeek HTTP transport. The
    skeleton imports nothing that opens a socket and never
    reads the process environment for credentials. Calling it
    while ``outbound_enabled=False`` raises
    :class:`DeepSeekOutboundDisabledError`. Even with
    ``outbound_enabled=True`` the v0 skeleton refuses to
    actually reach out - the real transport lands behind a
    later, separately gated PR;
  - :class:`DeepSeekOfflineSandboxRunner` - the deterministic
    offline runner that:

      * scans every input for forbidden / credential-shaped
        keys via the Phase AI-1
        :func:`_scan_for_forbidden_input` guard;
      * builds a redacted, deterministic prompt payload (the
        prompt NEVER carries a raw API key, an API secret, a
        bearer token, a ``listenKey``, a chat history, or a
        previous AI answer);
      * either calls the configured provider (when
        ``outbound_enabled=True`` AND ``sandbox_only=True``)
        or short-circuits to a degraded "outbound disabled"
        result (the default);
      * strips forbidden trade-action / runtime-config-patch
        fields from the model output via
        :func:`strip_forbidden_fields`;
      * validates every model-emitted claim through the
        Phase AI-2 :class:`AIClaimCitationValidator`;
      * cross-verifies every accepted / degraded claim
        through the Phase AI-3 :class:`AIRealityCheckEngine`;
      * emits one :class:`AIIntelligenceOutput` and never
        anything else.

Boundary
========

The runner is paper / report / sandbox-only. It **MUST NOT**:

  - place an order;
  - close a position;
  - change leverage / position size / stop / target;
  - override the Risk Engine;
  - override the Execution FSM;
  - alter runtime configuration (``symbol_limit`` / candidate-
    pool capacity / anomaly thresholds / Regime weights /
    strategy parameters / capital-flow rules / profit-harvest
    rules / rebase rules / redaction rules / safety flags);
  - send a real Telegram outbound message;
  - import :mod:`app.risk`, :mod:`app.execution`,
    :mod:`app.exchanges`, :mod:`app.telegram`, or
    :mod:`app.config`;
  - import :mod:`openai` / :mod:`anthropic` / :mod:`deepseek`
    / :mod:`httpx` / :mod:`requests` / :mod:`aiohttp` /
    :mod:`urllib3` / :mod:`websocket` / :mod:`websockets` /
    :mod:`grpc` / :mod:`boto3` / :mod:`socket`;
  - read or carry an API secret in any logged / exported /
    serialised payload;
  - emit ``buy`` / ``sell`` / ``long`` / ``short`` /
    ``direction`` / ``entry`` / ``exit`` / ``position_size`` /
    ``leverage`` / ``stop`` / ``stop_loss`` / ``target`` /
    ``take_profit`` / ``risk_budget`` / ``order`` /
    ``execution_command`` / ``runtime_config_patch`` /
    ``symbol_limit_patch`` / ``threshold_patch`` /
    ``candidate_pool_patch`` / ``regime_weight_patch`` /
    ``strategy_parameter_patch`` / ``signal_to_trade`` /
    ``should_buy`` / ``should_short``;
  - open Phase 12.

The four AI root constraints from
``docs/AMA_RT_AI_LAYER_ENGINEERING_SPEC.md`` are enforced *in
code* and *in tests*.

This module is paper / report / sandbox-only. It does NOT
authorise live trading, does NOT authorise auto-tuning, does
NOT call DeepSeek live, and does NOT open Phase 12. The Risk
Engine remains the single trade-decision gate.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.ai.claim_contract import (
    AIClaim,
    AIClaimAuthorityLevel,
    AIClaimCitationResult,
    AIClaimCitationValidator,
    AIClaimType,
)
from app.ai.evidence_bundle import (
    FORBIDDEN_AI_OUTPUT_FIELDS,
    LOOKAHEAD_POLICY_FLAGS,
    ForbiddenAIInputError,
    _assert_no_forbidden_fields,
    _scan_for_forbidden_input,
)
from app.ai.intelligence_schema import (
    AI_INTELLIGENCE_OUTPUT_SCHEMA_VERSION,
    AI_INTELLIGENCE_OUTPUT_SOURCE_MODULE,
    AI_INTELLIGENCE_OUTPUT_SOURCE_PHASE,
    AI_SECRET_REDACTED_PLACEHOLDER,
    AIIntelligenceAuthorityLevel,
    AIIntelligenceClaim,
    AIIntelligenceOutput,
    AIIntelligenceStatus,
    AIIntelligenceTaskType,
    FORBIDDEN_INTELLIGENCE_OUTPUT_FIELDS,
    coerce_str_tuple,
    redact_secrets,
    strip_forbidden_fields,
)
from app.ai.reality_check import (
    AIRealityCheckAuthorityLevel,
    AIRealityCheckEngine,
    AIRealityCheckInput,
    AIRealityCheckResult,
    AIRealityCheckStatus,
)


# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------
DEEPSEEK_SANDBOX_SOURCE_PHASE: str = "phase_ai_4"
DEEPSEEK_SANDBOX_SOURCE_MODULE: str = "ai_deepseek_offline_sandbox"
DEEPSEEK_SANDBOX_SCHEMA_VERSION: str = "v0"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class DeepSeekSandboxError(RuntimeError):
    """Base error for the DeepSeek Offline Sandbox.

    Subclasses :class:`RuntimeError` so a calling runner can
    ``except RuntimeError`` if it prefers, but the runner is
    always expected to convert sandbox errors into a degraded
    :class:`AIIntelligenceOutput`, never to crash a hot path.
    """


class DeepSeekOutboundDisabledError(DeepSeekSandboxError):
    """Raised when an HTTP / network provider is invoked while
    ``outbound_enabled=False`` (the default)."""


class DeepSeekProviderTimeoutError(DeepSeekSandboxError):
    """Raised when a provider call exceeds its configured
    ``timeout_seconds`` budget."""


class DeepSeekProviderRateLimitedError(DeepSeekSandboxError):
    """Raised when a provider call returns HTTP 429 (rate
    limited). The runner converts this into a degraded
    :class:`AIIntelligenceOutput`."""


class DeepSeekProviderServerError(DeepSeekSandboxError):
    """Raised when a provider call returns HTTP 5xx. The
    runner converts this into a degraded
    :class:`AIIntelligenceOutput`."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeepSeekSandboxConfig:
    """Closed, disabled-by-default configuration for the
    DeepSeek Offline Sandbox.

    The default values codify the brief's "highest safety
    boundary" - every gate is closed by default, every
    permission is denied by default, every redaction is
    enabled by default. A caller MUST flip a flag *explicitly*
    to relax it; the sandbox NEVER reads the process
    environment to relax a gate.
    """

    enabled: bool = False
    provider: str = "deepseek"
    outbound_enabled: bool = False
    sandbox_only: bool = True
    allow_trade_decision: bool = False
    allow_runtime_config_change: bool = False
    require_evidence_refs: bool = True
    require_reality_check: bool = True
    stateless_inference: bool = True
    feedback_isolation: bool = True
    timeout_seconds: float = 30.0
    max_tokens: int = 2048
    model: str = "deepseek-chat"
    redaction_enabled: bool = True
    schema_version: str = DEEPSEEK_SANDBOX_SCHEMA_VERSION
    source_phase: str = DEEPSEEK_SANDBOX_SOURCE_PHASE
    source_module: str = DEEPSEEK_SANDBOX_SOURCE_MODULE

    def __post_init__(self) -> None:
        # Trade-decision and runtime-config-change gates MUST
        # remain `False` in v0. A misconfigured caller cannot
        # relax them via this dataclass; relaxation is a Phase
        # 12 concern that requires the Spec §41 Go/No-Go
        # checklist.
        if self.allow_trade_decision:
            raise ValueError(
                "DeepSeekSandboxConfig.allow_trade_decision must "
                "be False in v0; trade authority is a Phase 12 "
                "concern that requires the Spec §41 Go/No-Go "
                "checklist."
            )
        if self.allow_runtime_config_change:
            raise ValueError(
                "DeepSeekSandboxConfig.allow_runtime_config_change "
                "must be False in v0; auto-tuning is forbidden by "
                "the AI Layer Engineering Spec."
            )
        if not self.sandbox_only:
            raise ValueError(
                "DeepSeekSandboxConfig.sandbox_only must remain "
                "True in v0; live / hot-path DeepSeek is forbidden."
            )
        if self.timeout_seconds <= 0.0:
            raise ValueError(
                "DeepSeekSandboxConfig.timeout_seconds must be > 0."
            )
        if self.max_tokens <= 0:
            raise ValueError(
                "DeepSeekSandboxConfig.max_tokens must be > 0."
            )
        if not str(self.model).strip():
            raise ValueError(
                "DeepSeekSandboxConfig.model must be a non-empty "
                "string."
            )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of the config.

        The view re-pins the safety invariants at the
        serialisation boundary so a downstream caller cannot
        mutate the dataclass and emit a relaxed view.
        """

        payload = {
            "schema_version": self.schema_version,
            "source_phase": self.source_phase,
            "source_module": self.source_module,
            "enabled": bool(self.enabled),
            "provider": str(self.provider),
            "outbound_enabled": bool(self.outbound_enabled),
            "sandbox_only": True,
            "allow_trade_decision": False,
            "allow_runtime_config_change": False,
            "require_evidence_refs": bool(self.require_evidence_refs),
            "require_reality_check": bool(self.require_reality_check),
            "stateless_inference": bool(self.stateless_inference),
            "feedback_isolation": bool(self.feedback_isolation),
            "timeout_seconds": float(self.timeout_seconds),
            "max_tokens": int(self.max_tokens),
            "model": str(self.model),
            "redaction_enabled": bool(self.redaction_enabled),
        }
        _assert_no_forbidden_fields(
            payload, context="DeepSeekSandboxConfig.to_dict"
        )
        return payload


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeepSeekSandboxInput:
    """Closed input record for one offline DeepSeek sandbox
    run.

    ``evidence_bundle`` is a serialised Phase AI-1
    :class:`AIEvidenceBundle` (the output of
    :meth:`AIEvidenceBundle.to_dict`). The runner NEVER builds
    a fresh bundle from raw runtime state; the bundle MUST be
    constructed externally and handed in as a frozen mapping.
    """

    evidence_bundle: Mapping[str, Any]
    task_type: AIIntelligenceTaskType | str
    operator_instruction: str
    allowed_output_schema: Mapping[str, Any] = field(
        default_factory=dict
    )
    forbidden_fields: tuple[str, ...] = ()
    evidence_refs_required: bool = True
    reality_check_required: bool = True

    def normalised_task_type(self) -> AIIntelligenceTaskType:
        if isinstance(self.task_type, AIIntelligenceTaskType):
            return self.task_type
        try:
            return AIIntelligenceTaskType(str(self.task_type))
        except ValueError as exc:
            raise ValueError(
                f"DeepSeekSandboxInput.task_type={self.task_type!r} "
                "is not a member of the closed "
                "AIIntelligenceTaskType vocabulary."
            ) from exc


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------
@runtime_checkable
class DeepSeekProviderProtocol(Protocol):
    """Closed provider interface a DeepSeek transport must
    implement.

    A provider returns *one* JSON-safe ``Mapping[str, Any]``
    given a deterministic ``prompt`` payload. The provider
    MUST raise on transport / timeout / rate-limit / 5xx
    failure; the runner converts every error into a degraded
    :class:`AIIntelligenceOutput`, never crashing a hot path.
    """

    def generate(
        self,
        *,
        prompt: Mapping[str, Any],
        max_tokens: int,
        timeout_seconds: float,
        model: str,
    ) -> Mapping[str, Any]:
        ...


# ---------------------------------------------------------------------------
# Fake provider (deterministic in-memory)
# ---------------------------------------------------------------------------
class FakeDeepSeekProvider:
    """Deterministic in-memory provider used by tests AND by
    every offline run that has ``outbound_enabled=False``.

    Three construction modes:

      1. ``FakeDeepSeekProvider(payload=...)`` - return the
         same payload for every call.
      2. ``FakeDeepSeekProvider(payload_fn=fn)`` - call
         ``fn(prompt=..., max_tokens=..., ...)`` per call.
         Useful for tests that derive a response from the
         input.
      3. ``FakeDeepSeekProvider(raise_exc=...)`` - raise the
         given exception per call. Useful for tests that
         exercise the runner's degrade path.
    """

    name: str = "fake_deepseek_provider"

    def __init__(
        self,
        *,
        payload: Mapping[str, Any] | None = None,
        payload_fn=None,
        raise_exc: Exception | None = None,
    ) -> None:
        if payload is None and payload_fn is None and raise_exc is None:
            # Default to a minimally-degraded but schema-valid
            # response so a caller that constructs the provider
            # without arguments still gets a deterministic
            # output.
            payload = {
                "summary": (
                    "Empty offline DeepSeek sandbox response - "
                    "evidence-only commentary substrate."
                ),
                "claims": [],
                "contradictions": [],
                "unsupported_claims": [],
                "risk_tags": [],
            }
        self._payload = (
            dict(payload) if isinstance(payload, Mapping) else None
        )
        self._payload_fn = payload_fn
        self._raise_exc = raise_exc
        self._calls = 0
        self._last_prompt: Mapping[str, Any] | None = None

    @property
    def calls(self) -> int:
        return self._calls

    @property
    def last_prompt(self) -> Mapping[str, Any] | None:
        return self._last_prompt

    def generate(
        self,
        *,
        prompt: Mapping[str, Any],
        max_tokens: int,
        timeout_seconds: float,
        model: str,
    ) -> Mapping[str, Any]:
        self._calls += 1
        # Defensive copy so a downstream consumer cannot mutate
        # the captured prompt.
        self._last_prompt = dict(prompt) if isinstance(
            prompt, Mapping
        ) else {}
        if self._raise_exc is not None:
            raise self._raise_exc
        if self._payload_fn is not None:
            response = self._payload_fn(
                prompt=prompt,
                max_tokens=max_tokens,
                timeout_seconds=timeout_seconds,
                model=model,
            )
            if not isinstance(response, Mapping):
                raise DeepSeekProviderServerError(
                    "FakeDeepSeekProvider payload_fn must return a "
                    f"Mapping; got {type(response).__name__}."
                )
            return dict(response)
        assert self._payload is not None  # for type-checker
        return dict(self._payload)


# ---------------------------------------------------------------------------
# Optional HTTP provider (refusal-only skeleton)
# ---------------------------------------------------------------------------
class OptionalDeepSeekHTTPProvider:
    """Refusal-only skeleton for the future real DeepSeek HTTP
    transport.

    Phase AI-4 ships **NO** real network code. This class:

      - imports nothing that opens a socket;
      - reads no process-environment variable for credentials
        (the caller must pass ``credentials_provided=True``
        explicitly);
      - refuses to be invoked when ``outbound_enabled=False``
        (the default);
      - even with ``outbound_enabled=True`` raises
        :class:`DeepSeekOutboundDisabledError` in v0 - the
        real transport lands behind a later, separately gated
        PR.

    The skeleton exists so a future PR can subclass / replace
    :meth:`generate` without changing the runner. The runner
    always treats provider errors as degraded results, never
    as crashes.
    """

    name: str = "optional_deepseek_http_provider"

    def __init__(
        self,
        *,
        outbound_enabled: bool = False,
        credentials_provided: bool = False,
        sandbox_only: bool = True,
    ) -> None:
        # Sandbox-only is permanently True for the v0
        # skeleton; a future real-transport subclass MAY relax
        # this only behind a Spec §41 Go/No-Go checklist.
        if not sandbox_only:
            raise ValueError(
                "OptionalDeepSeekHTTPProvider.sandbox_only must "
                "remain True in v0."
            )
        self._outbound_enabled = bool(outbound_enabled)
        self._credentials_provided = bool(credentials_provided)
        self._sandbox_only = True

    @property
    def outbound_enabled(self) -> bool:
        return self._outbound_enabled

    @property
    def credentials_provided(self) -> bool:
        return self._credentials_provided

    def generate(
        self,
        *,
        prompt: Mapping[str, Any],
        max_tokens: int,
        timeout_seconds: float,
        model: str,
    ) -> Mapping[str, Any]:
        if not self._outbound_enabled:
            raise DeepSeekOutboundDisabledError(
                "OptionalDeepSeekHTTPProvider refused to call "
                "DeepSeek: outbound_enabled=False (default). The "
                "v0 skeleton does not contact the network."
            )
        # Even with outbound_enabled=True the v0 skeleton
        # refuses to actually reach the network. The real
        # transport is a later, separately gated PR.
        raise DeepSeekOutboundDisabledError(
            "OptionalDeepSeekHTTPProvider v0 is a refusal-only "
            "skeleton. The real DeepSeek HTTP transport is gated "
            "behind a later, separately reviewed PR."
        )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
#: Mapping from :class:`AIIntelligenceTaskType` to the matching
#: :class:`AIClaimType` used by the citation validator. Closed
#: vocabulary; adding a new task type requires adding the
#: corresponding claim type at the same time.
_TASK_TO_CLAIM_TYPE: dict[AIIntelligenceTaskType, AIClaimType] = {
    AIIntelligenceTaskType.OPERATOR_BRIEFING_DRAFT: (
        AIClaimType.NARRATIVE
    ),
    AIIntelligenceTaskType.MARKET_INTELLIGENCE_SUMMARY: (
        AIClaimType.NARRATIVE
    ),
    AIIntelligenceTaskType.EVIDENCE_COMPRESSION: (
        AIClaimType.EVIDENCE_QUALITY
    ),
    AIIntelligenceTaskType.REPLAY_REFLECTION_SUMMARY: (
        AIClaimType.REFLECTION_SUMMARY
    ),
    AIIntelligenceTaskType.CONTRADICTION_SUMMARY: (
        AIClaimType.CONTRADICTION
    ),
    AIIntelligenceTaskType.EVIDENCE_QUALITY_ASSESSMENT: (
        AIClaimType.EVIDENCE_QUALITY
    ),
    AIIntelligenceTaskType.COVERAGE_AUDIT_INTERPRETATION: (
        AIClaimType.COVERAGE
    ),
    AIIntelligenceTaskType.POST_DISCOVERY_OUTCOME_SUMMARY: (
        AIClaimType.OUTCOME
    ),
    AIIntelligenceTaskType.REJECT_TO_OUTCOME_SUMMARY: (
        AIClaimType.OUTCOME
    ),
    AIIntelligenceTaskType.SEVERE_MISS_SUMMARY: (
        AIClaimType.OUTCOME
    ),
}


def _bool_flag(value: Any, *, default: bool) -> bool:
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


def _extract_lookahead_policy(
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Extract the lookahead policy from a serialised Phase
    AI-1 bundle. Falls back to the safe default (every
    required flag ``True``) when missing.
    """

    raw = bundle.get("lookahead_policy")
    if isinstance(raw, Mapping):
        return dict(raw)
    return {flag: True for flag in LOOKAHEAD_POLICY_FLAGS}


def _extract_fact_group(
    bundle: Mapping[str, Any], group: str
) -> dict[str, Any]:
    """Flatten the bundle's ``<group>_facts`` collection into
    a single ``{fact_id: content}`` mapping for the Reality
    Check engine.
    """

    raw = bundle.get(group)
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        return {}
    out: dict[str, Any] = {}
    for fact in raw:
        if not isinstance(fact, Mapping):
            continue
        fact_id = str(fact.get("fact_id", "")).strip()
        content = fact.get("content")
        if not fact_id or not isinstance(content, Mapping):
            continue
        for key, value in content.items():
            # Last writer wins; the bundle builder already
            # deduplicates by fact_id so the loop is
            # deterministic.
            out[str(key)] = value
    return out


@dataclass(frozen=True)
class _RawClaimRecord:
    claim_id: str
    claim_type: str
    claim_text: str
    evidence_refs: tuple[str, ...]
    truth_layer_fields_used: tuple[str, ...]
    confidence_raw: float | None


def _coerce_raw_claims(
    raw_claims: Any,
) -> list[_RawClaimRecord]:
    if not isinstance(raw_claims, Iterable) or isinstance(
        raw_claims, (str, bytes)
    ):
        return []
    out: list[_RawClaimRecord] = []
    for index, item in enumerate(raw_claims):
        if not isinstance(item, Mapping):
            continue
        claim_id = str(
            item.get("claim_id", f"claim_{index}")
        ).strip()
        claim_type = str(item.get("claim_type", "")).strip()
        claim_text = str(item.get("claim_text", "")).strip()
        evidence_refs = coerce_str_tuple(item.get("evidence_refs"))
        truth_fields = coerce_str_tuple(
            item.get("truth_layer_fields_used")
        )
        conf_raw = item.get("confidence_raw")
        try:
            conf = float(conf_raw) if conf_raw is not None else None
        except (TypeError, ValueError):
            conf = None
        out.append(
            _RawClaimRecord(
                claim_id=claim_id or f"claim_{index}",
                claim_type=claim_type,
                claim_text=claim_text,
                evidence_refs=evidence_refs,
                truth_layer_fields_used=truth_fields,
                confidence_raw=conf,
            )
        )
    return out


class DeepSeekOfflineSandboxRunner:
    """Pure, deterministic runner for the DeepSeek Offline
    Sandbox.

    The runner:

      - reads a frozen Phase AI-1 evidence bundle (handed in
        as a ``Mapping``) and an operator instruction;
      - scans every input for forbidden / credential-shaped
        keys via the Phase AI-1
        :func:`_scan_for_forbidden_input` guard;
      - constructs a deterministic prompt payload
        (the prompt NEVER carries a raw API key, an API
        secret, a bearer token, a ``listenKey``, a chat
        history, or a previous AI answer);
      - either calls the configured provider (when
        ``config.outbound_enabled=True`` AND
        ``config.sandbox_only=True``) or short-circuits to a
        degraded "outbound disabled" result (the default);
      - strips forbidden trade-action / runtime-config-patch
        fields from the model output via
        :func:`strip_forbidden_fields`;
      - validates every model-emitted claim through the
        Phase AI-2 :class:`AIClaimCitationValidator`;
      - cross-verifies every accepted / degraded claim
        through the Phase AI-3 :class:`AIRealityCheckEngine`;
      - emits one :class:`AIIntelligenceOutput`;
      - never crashes a hot path - every provider error /
        timeout / 429 / 5xx is converted into a degraded
        result.

    The runner NEVER:

      - sends a real Telegram outbound message;
      - calls a Risk / Execution / Exchange / Config surface;
      - reads a private exchange API key / secret;
      - emits a trade-action / runtime-config-patch field;
      - opens Phase 12.
    """

    def __init__(
        self,
        *,
        config: DeepSeekSandboxConfig | None = None,
        provider: DeepSeekProviderProtocol | None = None,
        citation_validator: AIClaimCitationValidator | None = None,
        reality_check_engine: AIRealityCheckEngine | None = None,
    ) -> None:
        self._config = config or DeepSeekSandboxConfig()
        self._provider: DeepSeekProviderProtocol | None = provider
        self._citation_validator = (
            citation_validator
            or AIClaimCitationValidator(strict=False)
        )
        self._reality_check_engine = (
            reality_check_engine or AIRealityCheckEngine()
        )

    @property
    def config(self) -> DeepSeekSandboxConfig:
        return self._config

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(
        self,
        sandbox_input: DeepSeekSandboxInput,
    ) -> AIIntelligenceOutput:
        """Run one offline DeepSeek sandbox cycle.

        Returns one deterministic :class:`AIIntelligenceOutput`.
        """

        warnings: list[str] = []
        degraded_reasons: list[str] = []

        # 1. Validate input shape (closed task type, mapping
        #    bundle, no forbidden / credential-shaped keys).
        try:
            task_type_enum = sandbox_input.normalised_task_type()
        except ValueError as exc:
            return self._reject_invalid_input(
                bundle_id="<unknown>",
                task_type=str(sandbox_input.task_type),
                reason=f"invalid_task_type:{exc}",
            )

        if not isinstance(sandbox_input.evidence_bundle, Mapping):
            return self._reject_invalid_input(
                bundle_id="<unknown>",
                task_type=task_type_enum.value,
                reason="evidence_bundle_not_mapping",
            )
        bundle: Mapping[str, Any] = sandbox_input.evidence_bundle
        bundle_id = str(bundle.get("bundle_id", "<unknown>"))

        # 2. Scan EVERY input for forbidden / credential-shaped
        #    keys. The scan runs against the bundle, the
        #    operator instruction container, and the allowed
        #    output schema.
        try:
            _scan_for_forbidden_input(
                bundle, context="evidence_bundle"
            )
            _scan_for_forbidden_input(
                {"operator_instruction": str(
                    sandbox_input.operator_instruction
                )},
                context="operator_instruction_container",
            )
            _scan_for_forbidden_input(
                dict(sandbox_input.allowed_output_schema),
                context="allowed_output_schema",
            )
        except ForbiddenAIInputError as exc:
            return self._reject_invalid_input(
                bundle_id=bundle_id,
                task_type=task_type_enum.value,
                reason=f"forbidden_input:{exc}",
            )

        # 3. If the sandbox is disabled, short-circuit to a
        #    degraded "outbound disabled" result. The runner
        #    NEVER reaches the provider when the master gate
        #    is closed.
        if not self._config.enabled:
            warnings.append("sandbox_disabled")
            degraded_reasons.append("sandbox_disabled")
            return self._build_degraded_output(
                bundle_id=bundle_id,
                task_type=task_type_enum.value,
                summary=(
                    "DeepSeek Offline Sandbox is disabled "
                    "(config.enabled=False); no provider call "
                    "was made."
                ),
                status=AIIntelligenceStatus.DEGRADED_OUTBOUND_DISABLED,
                authority_level=AIIntelligenceAuthorityLevel.DEGRADED_NO_EVIDENCE,
                warnings=tuple(warnings),
                degraded_reasons=tuple(degraded_reasons),
            )

        # 4. Build the deterministic prompt payload. The prompt
        #    NEVER carries a raw API key, an API secret, a
        #    bearer token, a listenKey, a chat history, or a
        #    previous AI answer. Redaction is applied to every
        #    container before the prompt is constructed.
        prompt_payload = self._build_prompt(
            bundle=bundle,
            task_type=task_type_enum,
            operator_instruction=str(
                sandbox_input.operator_instruction
            ),
            allowed_output_schema=dict(
                sandbox_input.allowed_output_schema
            ),
        )
        # Redaction smoke check: the prompt must not contain
        # any credential-shaped key. ``redact_secrets`` returns
        # the count; in a well-formed prompt the count is 0.
        _, prompt_redacted = redact_secrets(prompt_payload)
        if prompt_redacted > 0:
            # Defensive belt-and-braces: if the redactor still
            # finds a credential-shaped key (i.e. the prompt
            # builder regressed), re-redact and degrade the
            # output. This branch is unreachable in normal flow
            # because ``_build_prompt`` already redacts; it is
            # kept as an in-depth safety net.
            warnings.append(
                f"prompt_redaction_count:{prompt_redacted}"
            )
            prompt_payload, _ = redact_secrets(prompt_payload)

        # 5. Choose the provider. When ``outbound_enabled`` is
        #    False we ALWAYS use the fake provider, regardless
        #    of what the caller passed in. This is the
        #    "outbound disabled => safe degrade" rule.
        outbound = bool(self._config.outbound_enabled)
        provider_used: DeepSeekProviderProtocol
        if not outbound:
            warnings.append("outbound_disabled_using_fake_provider")
            provider_used = FakeDeepSeekProvider(
                payload={
                    "summary": (
                        "Offline sandbox echo: outbound disabled - "
                        "no DeepSeek call was made; the offline "
                        "fake provider returned a schema-valid "
                        "empty intelligence skeleton."
                    ),
                    "claims": [],
                    "contradictions": [],
                    "unsupported_claims": [],
                    "risk_tags": [],
                }
            )
        else:
            if self._provider is None:
                # The caller asked for outbound but didn't wire
                # a provider. Degrade safely instead of
                # crashing.
                warnings.append("outbound_enabled_but_no_provider")
                degraded_reasons.append(
                    "outbound_enabled_but_no_provider"
                )
                return self._build_degraded_output(
                    bundle_id=bundle_id,
                    task_type=task_type_enum.value,
                    summary=(
                        "DeepSeek Offline Sandbox refused to call "
                        "an unconfigured provider; outbound was "
                        "enabled but no DeepSeekProviderProtocol "
                        "implementation was supplied."
                    ),
                    status=AIIntelligenceStatus.DEGRADED_OUTBOUND_DISABLED,
                    authority_level=AIIntelligenceAuthorityLevel.DEGRADED_NO_EVIDENCE,
                    warnings=tuple(warnings),
                    degraded_reasons=tuple(degraded_reasons),
                )
            provider_used = self._provider

        # 6. Call the provider. The runner converts every
        #    transport error into a degraded result.
        try:
            raw_response = provider_used.generate(
                prompt=prompt_payload,
                max_tokens=int(self._config.max_tokens),
                timeout_seconds=float(self._config.timeout_seconds),
                model=str(self._config.model),
            )
        except DeepSeekOutboundDisabledError as exc:
            warnings.append("provider_outbound_disabled")
            degraded_reasons.append(
                f"provider_outbound_disabled:{exc}"
            )
            return self._build_degraded_output(
                bundle_id=bundle_id,
                task_type=task_type_enum.value,
                summary=(
                    "DeepSeek provider refused the call: outbound "
                    "is disabled."
                ),
                status=AIIntelligenceStatus.DEGRADED_OUTBOUND_DISABLED,
                authority_level=AIIntelligenceAuthorityLevel.DEGRADED_NO_EVIDENCE,
                warnings=tuple(warnings),
                degraded_reasons=tuple(degraded_reasons),
            )
        except DeepSeekProviderTimeoutError as exc:
            warnings.append("provider_timeout")
            degraded_reasons.append(f"provider_timeout:{exc}")
            return self._build_degraded_output(
                bundle_id=bundle_id,
                task_type=task_type_enum.value,
                summary=(
                    "DeepSeek provider call exceeded the "
                    "configured timeout; degraded result emitted."
                ),
                status=AIIntelligenceStatus.DEGRADED_PROVIDER_ERROR,
                authority_level=AIIntelligenceAuthorityLevel.DEGRADED_NO_EVIDENCE,
                warnings=tuple(warnings),
                degraded_reasons=tuple(degraded_reasons),
            )
        except DeepSeekProviderRateLimitedError as exc:
            warnings.append("provider_rate_limited_429")
            degraded_reasons.append(f"provider_rate_limited:{exc}")
            return self._build_degraded_output(
                bundle_id=bundle_id,
                task_type=task_type_enum.value,
                summary=(
                    "DeepSeek provider returned HTTP 429; "
                    "degraded result emitted."
                ),
                status=AIIntelligenceStatus.DEGRADED_PROVIDER_ERROR,
                authority_level=AIIntelligenceAuthorityLevel.DEGRADED_NO_EVIDENCE,
                warnings=tuple(warnings),
                degraded_reasons=tuple(degraded_reasons),
            )
        except DeepSeekProviderServerError as exc:
            warnings.append("provider_server_error_5xx")
            degraded_reasons.append(f"provider_server_error:{exc}")
            return self._build_degraded_output(
                bundle_id=bundle_id,
                task_type=task_type_enum.value,
                summary=(
                    "DeepSeek provider returned HTTP 5xx; degraded "
                    "result emitted."
                ),
                status=AIIntelligenceStatus.DEGRADED_PROVIDER_ERROR,
                authority_level=AIIntelligenceAuthorityLevel.DEGRADED_NO_EVIDENCE,
                warnings=tuple(warnings),
                degraded_reasons=tuple(degraded_reasons),
            )
        except Exception as exc:  # noqa: BLE001 - defensive degrade
            warnings.append("provider_unexpected_error")
            degraded_reasons.append(
                f"provider_unexpected_error:{type(exc).__name__}"
            )
            return self._build_degraded_output(
                bundle_id=bundle_id,
                task_type=task_type_enum.value,
                summary=(
                    "DeepSeek provider call raised an unexpected "
                    "exception; degraded result emitted."
                ),
                status=AIIntelligenceStatus.DEGRADED_PROVIDER_ERROR,
                authority_level=AIIntelligenceAuthorityLevel.DEGRADED_NO_EVIDENCE,
                warnings=tuple(warnings),
                degraded_reasons=tuple(degraded_reasons),
            )

        if not isinstance(raw_response, Mapping):
            warnings.append("provider_returned_non_mapping")
            degraded_reasons.append("provider_returned_non_mapping")
            return self._build_degraded_output(
                bundle_id=bundle_id,
                task_type=task_type_enum.value,
                summary=(
                    "DeepSeek provider returned a non-Mapping "
                    "response; degraded result emitted."
                ),
                status=AIIntelligenceStatus.DEGRADED_PROVIDER_ERROR,
                authority_level=AIIntelligenceAuthorityLevel.DEGRADED_NO_EVIDENCE,
                warnings=tuple(warnings),
                degraded_reasons=tuple(degraded_reasons),
            )

        # 7. Strip forbidden trade-action / runtime-config-patch
        #    fields from the model output. The stripped paths
        #    are recorded in
        #    ``forbidden_fields_stripped`` so the audit trail
        #    is never silent.
        cleaned_response, stripped_paths = strip_forbidden_fields(
            dict(raw_response)
        )
        # Merge any caller-supplied additional forbidden fields.
        extra_forbidden = frozenset(
            sandbox_input.forbidden_fields
        ) | FORBIDDEN_INTELLIGENCE_OUTPUT_FIELDS
        cleaned_response, extra_stripped = strip_forbidden_fields(
            cleaned_response, forbidden=extra_forbidden
        )
        all_stripped = sorted(set(stripped_paths) | set(extra_stripped))
        if all_stripped:
            warnings.append(
                f"forbidden_fields_stripped:{len(all_stripped)}"
            )
            degraded_reasons.append("forbidden_fields_stripped")

        # 8. Redact credential-shaped keys from the model
        #    output. The redactor returns the count of redacted
        #    keys; the runner records the count and emits a
        #    matching warning so the audit trail is honest.
        cleaned_response, redacted_count = redact_secrets(
            cleaned_response
        )
        if redacted_count > 0:
            warnings.append(
                f"secrets_redacted_in_output:{redacted_count}"
            )

        # 9. Validate every model-emitted claim through the
        #    Phase AI-2 citation contract.
        raw_claims = _coerce_raw_claims(cleaned_response.get("claims"))
        default_claim_type = _TASK_TO_CLAIM_TYPE.get(
            task_type_enum, AIClaimType.NARRATIVE
        ).value
        citation_inputs: list[Mapping[str, Any]] = []
        for raw in raw_claims:
            citation_inputs.append(
                {
                    "claim_id": raw.claim_id,
                    "claim_type": (
                        raw.claim_type or default_claim_type
                    ),
                    "claim_text": raw.claim_text,
                    "evidence_refs": list(raw.evidence_refs),
                    "truth_layer_fields_used": list(
                        raw.truth_layer_fields_used
                    ),
                    "confidence_raw": raw.confidence_raw,
                }
            )
        citation_result: AIClaimCitationResult = (
            self._citation_validator.validate(citation_inputs)
        )

        # 10. Cross-verify every accepted / degraded claim
        #     through the Phase AI-3 Reality Check engine.
        lookahead = _extract_lookahead_policy(bundle)
        market = _extract_fact_group(bundle, "market_facts")
        sysbeh = _extract_fact_group(bundle, "system_behavior_facts")
        outcome = _extract_fact_group(bundle, "outcome_facts")
        bundle_facts: dict[str, Any] = {
            "bundle_id": bundle_id,
            "reference_window": str(
                bundle.get("reference_window", "")
            ),
        }

        intel_claims: list[AIIntelligenceClaim] = []
        all_evidence_refs: list[str] = []
        seen_refs: set[str] = set()
        contradictions: list[str] = []
        unsupported: list[str] = []
        accepted_evidence_count = 0

        for claim in citation_result.claims:
            # Build the Reality Check input for this claim.
            ri = AIRealityCheckInput(
                claim_id=claim.claim_id,
                claim_type=claim.claim_type,
                claim_text=claim.claim_text,
                evidence_refs=claim.evidence_refs,
                truth_layer_fields_used=claim.truth_layer_fields_used,
                authority_level=claim.authority_level.value,
                confidence_raw=claim.confidence_raw,
                evidence_bundle_facts=bundle_facts,
                market_facts=market,
                system_behavior_facts=sysbeh,
                outcome_facts=outcome,
                lookahead_policy=lookahead,
            )
            rc: AIRealityCheckResult = (
                self._reality_check_engine.check(ri)
            )

            # If reality check is required and the claim does
            # not reach SUPPORTED_INTELLIGENCE, demote.
            authority_after = rc.authority_level_after_check
            if (
                self._config.require_reality_check
                and authority_after
                is not AIRealityCheckAuthorityLevel.SUPPORTED_INTELLIGENCE
            ):
                if rc.status is AIRealityCheckStatus.CONTRADICTED:
                    contradictions.append(claim.claim_id)
                else:
                    unsupported.append(claim.claim_id)

            # If evidence_refs are required and the claim has
            # none, mark as unsupported (the citation validator
            # already demoted to DEGRADED_NO_EVIDENCE; we just
            # surface the bookkeeping).
            if (
                self._config.require_evidence_refs
                and not claim.evidence_refs
            ):
                unsupported.append(claim.claim_id)

            if (
                authority_after
                is AIRealityCheckAuthorityLevel.SUPPORTED_INTELLIGENCE
                and claim.authority_level
                is AIClaimAuthorityLevel.SUPPORTED_INTELLIGENCE
            ):
                accepted_evidence_count += 1

            for ref in claim.evidence_refs:
                if ref not in seen_refs:
                    seen_refs.add(ref)
                    all_evidence_refs.append(ref)

            intel_claims.append(
                AIIntelligenceClaim(
                    claim_id=claim.claim_id,
                    claim_type=claim.claim_type,
                    claim_text=claim.claim_text,
                    evidence_refs=claim.evidence_refs,
                    truth_layer_fields_used=claim.truth_layer_fields_used,
                    citation_authority_level=claim.authority_level.value,
                    reality_check_status=rc.status.value,
                    reality_check_authority_level=authority_after.value,
                    confidence_raw=claim.confidence_raw,
                    confidence_reality_checked=rc.confidence_reality_checked,
                    warnings=tuple(claim.warnings)
                    + tuple(rc.warnings),
                )
            )

        # 11. Compute the overall status / authority level.
        summary_text = str(cleaned_response.get("summary", "")).strip()
        if not summary_text:
            summary_text = (
                "DeepSeek Offline Sandbox returned no summary "
                "text; commentary substrate degraded."
            )

        contradictions_list = coerce_str_tuple(
            cleaned_response.get("contradictions")
        )
        if contradictions:
            contradictions_list = contradictions_list + tuple(
                contradictions
            )
        unsupported_list = coerce_str_tuple(
            cleaned_response.get("unsupported_claims")
        )
        if unsupported:
            unsupported_list = unsupported_list + tuple(unsupported)
        risk_tags = coerce_str_tuple(
            cleaned_response.get("risk_tags")
        )

        # Status.
        if all_stripped:
            status = AIIntelligenceStatus.REJECTED_FORBIDDEN_FIELDS
            authority_level = AIIntelligenceAuthorityLevel.REJECTED
            degraded_reasons.append("forbidden_fields_present_in_model_output")
        elif (
            self._config.require_evidence_refs
            and citation_result.missing_evidence_count > 0
        ):
            status = AIIntelligenceStatus.DEGRADED_MISSING_EVIDENCE
            authority_level = (
                AIIntelligenceAuthorityLevel.DEGRADED_NO_EVIDENCE
            )
            degraded_reasons.append(
                f"missing_evidence_refs:{citation_result.missing_evidence_count}"
            )
        elif self._config.require_reality_check and (
            contradictions or unsupported
        ):
            status = AIIntelligenceStatus.DEGRADED_REALITY_CHECK
            authority_level = (
                AIIntelligenceAuthorityLevel.DEGRADED_REALITY_CHECK
            )
            degraded_reasons.append(
                "reality_check_failed_or_unsupported"
            )
        elif accepted_evidence_count == 0 and intel_claims:
            # Every claim was demoted somewhere (e.g. all
            # commentary-only); downgrade authority.
            status = AIIntelligenceStatus.OK
            authority_level = (
                AIIntelligenceAuthorityLevel.COMMENTARY_ONLY
            )
        elif intel_claims:
            status = AIIntelligenceStatus.OK
            authority_level = (
                AIIntelligenceAuthorityLevel.SUPPORTED_INTELLIGENCE
            )
        else:
            # No claims at all - the model returned a summary
            # only. This is allowed (e.g. EVIDENCE_COMPRESSION
            # may produce only a summary), but it never reaches
            # SUPPORTED_INTELLIGENCE.
            status = AIIntelligenceStatus.OK
            authority_level = (
                AIIntelligenceAuthorityLevel.COMMENTARY_ONLY
            )

        reality_check_status = self._aggregate_reality_check_status(
            intel_claims
        )

        return AIIntelligenceOutput(
            schema_version=AI_INTELLIGENCE_OUTPUT_SCHEMA_VERSION,
            bundle_id=bundle_id,
            task_type=task_type_enum.value,
            summary=summary_text,
            claims=tuple(intel_claims),
            contradictions=contradictions_list,
            unsupported_claims=unsupported_list,
            risk_tags=risk_tags,
            evidence_refs=tuple(all_evidence_refs),
            reality_check_status=reality_check_status,
            authority_level=authority_level,
            status=status,
            forbidden_fields_stripped=tuple(all_stripped),
            redacted_secret_count=int(redacted_count),
            warnings=tuple(warnings),
            degraded_reasons=tuple(degraded_reasons),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _build_prompt(
        self,
        *,
        bundle: Mapping[str, Any],
        task_type: AIIntelligenceTaskType,
        operator_instruction: str,
        allowed_output_schema: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Construct the deterministic prompt payload.

        The prompt NEVER carries a raw API key, an API secret,
        a bearer token, a ``listenKey``, a chat history, or a
        previous AI answer. Redaction is applied to every
        container before the prompt is constructed.
        """

        redacted_bundle, _ = redact_secrets(dict(bundle))
        redacted_schema, _ = redact_secrets(
            dict(allowed_output_schema)
        )

        prompt: dict[str, Any] = {
            "schema_version": DEEPSEEK_SANDBOX_SCHEMA_VERSION,
            "task_type": task_type.value,
            "operator_instruction": str(operator_instruction),
            "evidence_bundle": redacted_bundle,
            "allowed_output_schema": redacted_schema,
            "constraints": {
                "stateless_inference": True,
                "feedback_isolation": True,
                "allow_trade_decision": False,
                "allow_runtime_config_change": False,
                "require_evidence_refs": bool(
                    self._config.require_evidence_refs
                ),
                "require_reality_check": bool(
                    self._config.require_reality_check
                ),
                "forbidden_output_fields": sorted(
                    FORBIDDEN_AI_OUTPUT_FIELDS
                ),
            },
        }
        # Defensive guard: a prompt MUST NOT contain a forbidden
        # trade-action / runtime-config-patch key even before the
        # model has seen it.
        _assert_no_forbidden_fields(
            prompt, context="DeepSeekOfflineSandboxRunner._build_prompt"
        )
        return prompt

    def _aggregate_reality_check_status(
        self,
        intel_claims: Iterable[AIIntelligenceClaim],
    ) -> str:
        statuses = [c.reality_check_status for c in intel_claims]
        if not statuses:
            return AIRealityCheckStatus.INSUFFICIENT_EVIDENCE.value
        if all(
            s == AIRealityCheckStatus.SUPPORTED.value for s in statuses
        ):
            return AIRealityCheckStatus.SUPPORTED.value
        if any(
            s == AIRealityCheckStatus.CONTRADICTED.value
            for s in statuses
        ):
            return AIRealityCheckStatus.CONTRADICTED.value
        if any(
            s == AIRealityCheckStatus.REJECTED_LOOKAHEAD.value
            for s in statuses
        ):
            return AIRealityCheckStatus.REJECTED_LOOKAHEAD.value
        if any(
            s
            == AIRealityCheckStatus.REJECTED_UNVERIFIABLE_NARRATIVE.value
            for s in statuses
        ):
            return AIRealityCheckStatus.REJECTED_UNVERIFIABLE_NARRATIVE.value
        if all(
            s == AIRealityCheckStatus.SUPPORTED.value
            or s == AIRealityCheckStatus.PARTIALLY_SUPPORTED.value
            for s in statuses
        ):
            return AIRealityCheckStatus.PARTIALLY_SUPPORTED.value
        return AIRealityCheckStatus.INSUFFICIENT_EVIDENCE.value

    # ------------------------------------------------------------------
    # Output factories
    # ------------------------------------------------------------------
    def _build_degraded_output(
        self,
        *,
        bundle_id: str,
        task_type: str,
        summary: str,
        status: AIIntelligenceStatus,
        authority_level: AIIntelligenceAuthorityLevel,
        warnings: tuple[str, ...],
        degraded_reasons: tuple[str, ...],
    ) -> AIIntelligenceOutput:
        return AIIntelligenceOutput(
            schema_version=AI_INTELLIGENCE_OUTPUT_SCHEMA_VERSION,
            bundle_id=str(bundle_id),
            task_type=str(task_type),
            summary=str(summary),
            claims=(),
            contradictions=(),
            unsupported_claims=(),
            risk_tags=(),
            evidence_refs=(),
            reality_check_status=(
                AIRealityCheckStatus.INSUFFICIENT_EVIDENCE.value
            ),
            authority_level=authority_level,
            status=status,
            forbidden_fields_stripped=(),
            redacted_secret_count=0,
            warnings=warnings,
            degraded_reasons=degraded_reasons,
        )

    def _reject_invalid_input(
        self,
        *,
        bundle_id: str,
        task_type: str,
        reason: str,
    ) -> AIIntelligenceOutput:
        return AIIntelligenceOutput(
            schema_version=AI_INTELLIGENCE_OUTPUT_SCHEMA_VERSION,
            bundle_id=str(bundle_id),
            task_type=str(task_type),
            summary=(
                "DeepSeek Offline Sandbox refused the input: "
                f"{reason}"
            ),
            claims=(),
            contradictions=(),
            unsupported_claims=(),
            risk_tags=(),
            evidence_refs=(),
            reality_check_status=(
                AIRealityCheckStatus.INSUFFICIENT_EVIDENCE.value
            ),
            authority_level=AIIntelligenceAuthorityLevel.REJECTED,
            status=AIIntelligenceStatus.REJECTED_INVALID_INPUT,
            forbidden_fields_stripped=(),
            redacted_secret_count=0,
            warnings=(reason,),
            degraded_reasons=(reason,),
        )


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------
def run_deepseek_offline_sandbox(
    *,
    sandbox_input: DeepSeekSandboxInput,
    config: DeepSeekSandboxConfig | None = None,
    provider: DeepSeekProviderProtocol | None = None,
    citation_validator: AIClaimCitationValidator | None = None,
    reality_check_engine: AIRealityCheckEngine | None = None,
) -> AIIntelligenceOutput:
    """Convenience wrapper that constructs a runner and calls
    :meth:`DeepSeekOfflineSandboxRunner.run`.

    The wrapper is provided so a caller does not need to
    instantiate the runner directly. Behavior is identical to
    the runner.
    """

    runner = DeepSeekOfflineSandboxRunner(
        config=config,
        provider=provider,
        citation_validator=citation_validator,
        reality_check_engine=reality_check_engine,
    )
    return runner.run(sandbox_input)


__all__ = [
    "DEEPSEEK_SANDBOX_SCHEMA_VERSION",
    "DEEPSEEK_SANDBOX_SOURCE_MODULE",
    "DEEPSEEK_SANDBOX_SOURCE_PHASE",
    "DeepSeekOfflineSandboxRunner",
    "DeepSeekOutboundDisabledError",
    "DeepSeekProviderProtocol",
    "DeepSeekProviderRateLimitedError",
    "DeepSeekProviderServerError",
    "DeepSeekProviderTimeoutError",
    "DeepSeekSandboxConfig",
    "DeepSeekSandboxError",
    "DeepSeekSandboxInput",
    "FakeDeepSeekProvider",
    "OptionalDeepSeekHTTPProvider",
    "run_deepseek_offline_sandbox",
]
