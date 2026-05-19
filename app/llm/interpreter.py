"""Phase 10C - LLM Guarded Interpreter orchestrator (Issue #10 Part 3).

Top-level orchestrator that ties together the Phase 10C primitives:

  - :class:`app.llm.cache.LLMCache`      (cache)
  - :class:`app.llm.client.LLMClientBase` (transport)
  - :func:`app.llm.guardrails.sanitize_input_text`
  - :func:`app.llm.guardrails.detect_prompt_injection`
  - :func:`app.llm.guardrails.enforce_field_whitelist`
  - :func:`app.llm.guardrails.strip_forbidden_fields`
  - :func:`app.llm.schema.validate_llm_output`
  - :class:`app.llm.models.LLMInterpretationResult`

Public entry point:

    LLMGuardedInterpreter.interpret(LLMInterpretationInput) ->
        LLMInterpretationResult

The orchestrator NEVER raises into the caller. Every transport /
schema / guardrail failure is converted into a degraded result. The
result is recorded on ``events.db`` via the ``LLM_INTERPRETED`` /
``LLM_DEGRADED`` / ``LLM_SCHEMA_REJECTED`` event surface.

Spec §22.4 token throttle:

    anomaly_score < 60   -> SKIP   (no LLM call; degraded result)
    60 <= score < 75     -> LIGHT
    75 <= score < 90     -> STANDARD
    score >= 90          -> FULL

Phase 10C boundary
------------------

The orchestrator NEVER:

  - opens a socket
  - imports an exchange / HTTP / WebSocket / LLM / Telegram client
  - reads ``os.environ``
  - calls ``create_order`` / ``cancel_order`` / ``set_leverage`` /
    ``set_margin_mode``
  - calls Risk Engine ``approve`` / ``evaluate`` (the LLM never
    bypasses the gate)
  - calls Execution FSM
  - mutates Phase 9 paper-ledger state
  - emits a Telegram message

The orchestrator DOES write Phase 10C events to ``events.db``. That
is the ONE write surface Phase 10C exposes; tests assert it is
limited to the three new event types.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from app.core.clock import now_ms
from app.core.events import Event, EventType
from app.database.repositories import EventRepository
from app.llm.cache import LLMCache
from app.llm.client import (
    FakeLLMClient,
    LLMClientBase,
    LLMTimeoutError,
    TransportError,
)
from app.llm.guardrails import (
    DEFAULT_INPUT_MAX_CHARS,
    coerce_string_list,
    detect_prompt_injection,
    enforce_field_whitelist,
    sanitize_input_text,
    strip_forbidden_fields,
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
    build_messages,
)
from app.llm.schema import (
    SCHEMA_VERSION,
    SchemaValidationError,
    validate_llm_output,
)


# ===========================================================================
# Config
# ===========================================================================
@dataclass(frozen=True)
class LLMInterpreterConfig:
    """Tunable thresholds for the interpreter.

    Defaults match the Spec §22.4 brief. Tests override these per case.
    """

    # Spec §22.4 anomaly-score throttle thresholds.
    light_threshold: float = 60.0
    standard_threshold: float = 75.0
    full_threshold: float = 90.0
    # Hard timeout budget for one transport call (ms).
    timeout_ms: int = 5000
    # Max characters of source text fed to the model.
    max_input_chars: int = DEFAULT_INPUT_MAX_CHARS
    # Confidence below this floors `degraded=True` even on a
    # syntactically clean output.
    low_confidence_floor: float = 0.2
    # If True the interpreter writes events. Tests can flip this off
    # to assert no-write semantics.
    emit_events_enabled: bool = True
    # Cache size (LRU).
    cache_max_entries: int = 1024


# ===========================================================================
# Token bucket
# ===========================================================================
class LLMTokenBucket:
    """Spec §22.4 anomaly-score throttle (in-memory, deterministic).

    The bucket maps an ``anomaly_score`` (or ``None``) to a
    :class:`TokenThrottleTier`. The orchestrator consumes the tier;
    callers may also use the bucket directly for monitoring.
    """

    def __init__(self, config: LLMInterpreterConfig | None = None) -> None:
        self._config = config or LLMInterpreterConfig()

    @property
    def config(self) -> LLMInterpreterConfig:
        return self._config

    def classify(self, anomaly_score: float | None) -> TokenThrottleTier:
        if anomaly_score is None:
            return TokenThrottleTier.SKIP
        try:
            score = float(anomaly_score)
        except (TypeError, ValueError):
            return TokenThrottleTier.SKIP
        cfg = self._config
        if score < cfg.light_threshold:
            return TokenThrottleTier.SKIP
        if score < cfg.standard_threshold:
            return TokenThrottleTier.LIGHT
        if score < cfg.full_threshold:
            return TokenThrottleTier.STANDARD
        return TokenThrottleTier.FULL


# ===========================================================================
# Orchestrator
# ===========================================================================
class LLMGuardedInterpreter:
    """Receive-only, schema-validated, sandboxed LLM interpreter.

    Construction
    ------------

        LLMGuardedInterpreter(
            client=...,
            event_repo=...,        # optional
            config=...,            # optional
            cache=...,             # optional
            llm_enabled=...,       # optional, default False
        )

    The interpreter copies ``llm_enabled`` from settings or accepts
    an explicit override; when False the interpreter SHORT-CIRCUITS
    every call to a degraded result with reason
    :data:`LLMDegradedReason.LLM_DISABLED`. The fake client is used
    for the boot self-check; the DeepSeek skeleton refuses by design.
    """

    SOURCE_MODULE = "llm_guarded_interpreter"

    def __init__(
        self,
        *,
        client: LLMClientBase | None = None,
        event_repo: EventRepository | None = None,
        config: LLMInterpreterConfig | None = None,
        cache: LLMCache | None = None,
        llm_enabled: bool = False,
    ) -> None:
        if not isinstance(llm_enabled, bool):
            raise TypeError("llm_enabled must be bool")
        self._config = config or LLMInterpreterConfig()
        self._client = client
        self._event_repo = event_repo
        self._cache = cache or LLMCache(
            max_entries=int(self._config.cache_max_entries)
        )
        self._llm_enabled = bool(llm_enabled)
        self._token_bucket = LLMTokenBucket(self._config)
        # Counters for monitoring / boot banner.
        self._counters = _InterpreterCounters()



    # ------------------------------------------------------------------
    @property
    def config(self) -> LLMInterpreterConfig:
        return self._config

    @property
    def llm_enabled(self) -> bool:
        return self._llm_enabled

    @property
    def cache(self) -> LLMCache:
        return self._cache

    @property
    def counters(self) -> "_InterpreterCounters":
        return self._counters

    @property
    def token_bucket(self) -> LLMTokenBucket:
        return self._token_bucket

    def reset_counters(self) -> None:
        self._counters = _InterpreterCounters()

    # ==================================================================
    # Public entry point
    # ==================================================================
    def interpret(
        self,
        inp: LLMInterpretationInput,
    ) -> LLMInterpretationResult:
        """Compress one input bundle into a structured result.

        NEVER raises. Every internal failure becomes a degraded
        :class:`LLMInterpretationResult`. The orchestrator emits the
        appropriate event AS A SIDE EFFECT (LLM_INTERPRETED on a
        clean call, LLM_DEGRADED on a degraded call,
        LLM_SCHEMA_REJECTED when the schema validator returned a
        non-empty error list). The Risk Engine and the Execution FSM
        are NEVER touched.
        """
        # Defence in depth: synthesise a safe input if the caller
        # passed garbage. The orchestrator must NEVER raise; turning
        # a TypeError into a degraded result preserves the contract.
        if not isinstance(inp, LLMInterpretationInput):
            inp = LLMInterpretationInput(source_text="")
            return self._build_degraded_result(
                inp=inp,
                model_name=self._client_model_name(),
                degraded_reasons=(LLMDegradedReason.EXCEPTION,),
                stripped_fields=(),
                prompt_injection_detected=False,
                cache_hit=False,
                emit=True,
                tags=(LLMRiskTag.DATA_INSUFFICIENT,),
                error_summary="invalid_input_type",
            )
        try:
            return self._interpret_impl(inp)
        except Exception as exc:  # noqa: BLE001 - guard the entry point
            # Defensive: if something still bubbles out (e.g. a future
            # maintainer adds a buggy helper), return a degraded
            # result rather than crash the boot.
            return self._build_degraded_result(
                inp=inp,
                model_name=self._client_model_name(),
                degraded_reasons=(
                    LLMDegradedReason.EXCEPTION,
                ),
                stripped_fields=(),
                prompt_injection_detected=False,
                cache_hit=False,
                # Do not include the exception message in the result
                # since it may carry untrusted text.
                emit=True,
                tags=(LLMRiskTag.DATA_INSUFFICIENT,),
                error_summary=type(exc).__name__,
            )



    # ==================================================================
    # Implementation
    # ==================================================================
    def _interpret_impl(
        self,
        inp: LLMInterpretationInput,
    ) -> LLMInterpretationResult:
        # ``interpret`` already coerces non-LLMInterpretationInput
        # inputs into a degraded result; reaching this point means
        # we have a real input.
        model_name = self._client_model_name()
        cleaned = sanitize_input_text(
            inp.source_text or "",
            max_chars=int(self._config.max_input_chars),
        )
        injection_detected = detect_prompt_injection(inp.source_text or "")

        # 1) llm_enabled must be True. Defence in depth on top of the
        # Phase 1 settings lock - Phase 1 already keeps llm_enabled
        # false at config-load time, so the default boot path is
        # always degraded.
        if not self._llm_enabled:
            self._counters.disabled_skips += 1
            return self._build_degraded_result(
                inp=inp,
                model_name=model_name,
                degraded_reasons=(LLMDegradedReason.LLM_DISABLED,),
                stripped_fields=(),
                prompt_injection_detected=injection_detected,
                cache_hit=False,
                emit=True,
                tags=(
                    (LLMRiskTag.PROMPT_INJECTION_DETECTED,)
                    if injection_detected
                    else ()
                ),
            )

        # 2) Empty input is a no-op.
        if not cleaned:
            self._counters.empty_input_skips += 1
            return self._build_degraded_result(
                inp=inp,
                model_name=model_name,
                degraded_reasons=(LLMDegradedReason.EMPTY_INPUT,),
                stripped_fields=(),
                prompt_injection_detected=injection_detected,
                cache_hit=False,
                emit=True,
            )



        # 3) Spec §22.4 token throttle: scores below the LIGHT
        # threshold do not invoke the model.
        tier = self._token_bucket.classify(inp.anomaly_score)
        if tier is TokenThrottleTier.SKIP:
            self._counters.below_throttle_skips += 1
            return self._build_degraded_result(
                inp=inp,
                model_name=model_name,
                degraded_reasons=(LLMDegradedReason.BELOW_TOKEN_THROTTLE,),
                stripped_fields=(),
                prompt_injection_detected=injection_detected,
                cache_hit=False,
                emit=True,
            )

        # 4) The transport must exist before we attempt a real call.
        if self._client is None:
            self._counters.no_client_skips += 1
            return self._build_degraded_result(
                inp=inp,
                model_name=model_name,
                degraded_reasons=(LLMDegradedReason.LLM_DISABLED,),
                stripped_fields=(),
                prompt_injection_detected=injection_detected,
                cache_hit=False,
                emit=True,
            )

        # 5) Cache lookup - keyed on input + prompt + schema +
        # model + throttle tier + symbol. The cache stores ONLY
        # JSON-safe whitelisted result payloads.
        cache_key = LLMCache.make_key(
            input_text=cleaned,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            model_name=model_name,
            throttle_tier=tier.value,
            symbol=inp.symbol,
        )
        hit = self._cache.get(cache_key)
        if hit is not None:
            self._counters.cache_hits += 1
            return self._result_from_cached_payload(
                inp=inp,
                payload=hit.payload,
                model_name=model_name,
                cache_hit=True,
                injection_detected=injection_detected,
            )



        # 6) Build messages and stage the input on the fake client so
        # response_fn callers can introspect it. (The DeepSeek
        # skeleton ignores stage_input; that's fine.)
        messages = build_messages(
            source_text=cleaned,
            symbol=inp.symbol,
            anomaly_score=inp.anomaly_score,
            price_change_pct=inp.price_change_pct,
            oi_change_pct=inp.oi_change_pct,
            funding_change_pct=inp.funding_change_pct,
            sources=inp.sources,
        )
        if isinstance(self._client, FakeLLMClient):
            self._client.stage_input(inp)

        # 7) Transport call. ANY exception lands as a degraded result;
        # the orchestrator never raises into the caller.
        try:
            raw = self._client.generate(
                messages=messages,
                timeout_ms=int(self._config.timeout_ms),
                seed=None,
            )
        except LLMTimeoutError:
            self._counters.transport_timeouts += 1
            return self._build_degraded_result(
                inp=inp,
                model_name=model_name,
                degraded_reasons=(LLMDegradedReason.TIMEOUT,),
                stripped_fields=(),
                prompt_injection_detected=injection_detected,
                cache_hit=False,
                emit=True,
            )
        except TransportError:
            self._counters.transport_errors += 1
            return self._build_degraded_result(
                inp=inp,
                model_name=model_name,
                degraded_reasons=(LLMDegradedReason.TRANSPORT_ERROR,),
                stripped_fields=(),
                prompt_injection_detected=injection_detected,
                cache_hit=False,
                emit=True,
            )
        except Exception:  # noqa: BLE001
            self._counters.transport_exceptions += 1
            return self._build_degraded_result(
                inp=inp,
                model_name=model_name,
                degraded_reasons=(LLMDegradedReason.EXCEPTION,),
                stripped_fields=(),
                prompt_injection_detected=injection_detected,
                cache_hit=False,
                emit=True,
            )



        # 8) Forbidden-field stripping - run BEFORE schema validation
        # because we need to record the strip even when the rest of
        # the payload is malformed. ALSO drives the
        # `LLM_SCHEMA_REJECTED` event when applied.
        stripped_payload, stripped_fields = strip_forbidden_fields(raw)

        # 9) Field-whitelist enforcement: drop any non-Spec §22.2 key.
        whitelisted, dropped_keys = enforce_field_whitelist(stripped_payload)

        # 10) Schema validation against the closed Spec §22.2 shape.
        validated, errors = validate_llm_output(whitelisted)

        # 11) Decide final state.
        degraded_reasons: list[LLMDegradedReason] = []
        risk_tags: list[LLMRiskTag] = []
        if injection_detected:
            risk_tags.append(LLMRiskTag.PROMPT_INJECTION_DETECTED)
            degraded_reasons.append(LLMDegradedReason.PROMPT_INJECTION_DETECTED)
        if stripped_fields:
            risk_tags.append(LLMRiskTag.FORBIDDEN_FIELD_STRIPPED)
            degraded_reasons.append(LLMDegradedReason.FORBIDDEN_FIELD_PRESENT)
            self._counters.forbidden_field_strips += 1
        if errors or dropped_keys:
            risk_tags.append(LLMRiskTag.SCHEMA_VIOLATION)
            degraded_reasons.append(LLMDegradedReason.SCHEMA_VALIDATION_FAILED)
            self._counters.schema_rejections += 1

        # 12) Build the result. If the schema rejected required
        # fields we synthesise a degraded result rather than guessing
        # values; the caller still gets a well-typed object.
        if errors and any(
            err.code == "missing_required_field" for err in errors
        ):
            return self._build_degraded_result(
                inp=inp,
                model_name=model_name,
                degraded_reasons=tuple(degraded_reasons),
                stripped_fields=tuple(stripped_fields),
                prompt_injection_detected=injection_detected,
                cache_hit=False,
                emit=True,
                tags=tuple(risk_tags),
                schema_errors=errors,
            )



        # 13) Hydrate typed value object from the validated dict.
        narrative = str(validated.get("narrative", "")).strip()
        if not narrative:
            risk_tags.append(LLMRiskTag.DATA_INSUFFICIENT)
            degraded_reasons.append(LLMDegradedReason.SCHEMA_VALIDATION_FAILED)

        catalyst = self._safe_enum(
            validated.get("catalyst"),
            CatalystStrength,
            CatalystStrength.UNKNOWN,
        )
        evidence = self._safe_enum(
            validated.get("evidence_quality"),
            EvidenceQuality,
            EvidenceQuality.UNKNOWN,
        )
        hype = self._safe_enum(
            validated.get("hype_stage"),
            HypeStage,
            HypeStage.UNKNOWN,
        )

        source_diversity = int(validated.get("source_diversity", 0))
        kol_concentration = float(validated.get("kol_concentration", 0.0))
        bot_risk = float(validated.get("bot_risk", 0.0))
        confidence = float(validated.get("confidence", 0.0))

        contradictions = tuple(
            coerce_string_list(validated.get("contradictions"))
        )
        # Free-form risk_tags from the model are coerced into the
        # closed LLMRiskTag vocabulary; unknown strings are dropped
        # silently (with their absence implicit). Defence in depth.
        model_risk_tag_strings = coerce_string_list(
            validated.get("risk_tags")
        )
        for raw_tag in model_risk_tag_strings:
            try:
                risk_tags.append(LLMRiskTag(str(raw_tag)))
            except (ValueError, TypeError):
                # Unknown tag - dropped silently; SCHEMA_VIOLATION
                # already fires above if the model returned a key
                # outside the Spec §22.2 schema.
                continue



        # 14) Confidence floor enforcement.
        if confidence < float(self._config.low_confidence_floor):
            if LLMRiskTag.LOW_CONFIDENCE not in risk_tags:
                risk_tags.append(LLMRiskTag.LOW_CONFIDENCE)
            if LLMDegradedReason.LOW_CONFIDENCE not in degraded_reasons:
                degraded_reasons.append(LLMDegradedReason.LOW_CONFIDENCE)

        # 15) Quality-derived risk tags. These are advisory and never
        # alone trigger degraded.
        if evidence is EvidenceQuality.D or evidence is EvidenceQuality.UNKNOWN:
            if LLMRiskTag.EVIDENCE_QUALITY_LOW not in risk_tags:
                risk_tags.append(LLMRiskTag.EVIDENCE_QUALITY_LOW)
        if source_diversity <= 1:
            if LLMRiskTag.LOW_SOURCE_DIVERSITY not in risk_tags:
                risk_tags.append(LLMRiskTag.LOW_SOURCE_DIVERSITY)
        if kol_concentration >= 0.7:
            if LLMRiskTag.KOL_CONCENTRATION_HIGH not in risk_tags:
                risk_tags.append(LLMRiskTag.KOL_CONCENTRATION_HIGH)
        if bot_risk >= 0.7:
            if LLMRiskTag.BOT_RISK_HIGH not in risk_tags:
                risk_tags.append(LLMRiskTag.BOT_RISK_HIGH)
        if contradictions:
            if LLMRiskTag.CONTRADICTIONS_PRESENT not in risk_tags:
                risk_tags.append(LLMRiskTag.CONTRADICTIONS_PRESENT)

        degraded = bool(degraded_reasons)
        if degraded:
            self._counters.degraded_results += 1
        else:
            self._counters.clean_results += 1

        # 16) Final result + cache write (only when not degraded so
        # the cache never carries a degraded payload).
        result = LLMInterpretationResult(
            narrative=narrative,
            catalyst=catalyst,
            evidence_quality=evidence,
            source_diversity=int(max(0, source_diversity)),
            kol_concentration=float(max(0.0, min(1.0, kol_concentration))),
            bot_risk=float(max(0.0, min(1.0, bot_risk))),
            hype_stage=hype,
            contradictions=contradictions,
            risk_tags=self._dedupe_tags(risk_tags),
            confidence=float(max(0.0, min(1.0, confidence))),
            degraded=degraded,
            degraded_reasons=self._dedupe_reasons(degraded_reasons),
            stripped_fields=tuple(stripped_fields),
            prompt_injection_detected=injection_detected,
            source_count=len(inp.sources),
            model_name=model_name,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            cache_hit=False,
            opportunity_id=inp.opportunity_id,
            symbol=inp.symbol,
            correlation_id=inp.correlation_id,
        )
        if not degraded:
            try:
                self._cache.put(cache_key, result.to_payload())
            except ValueError:
                # The cache refused an apparently-credential payload.
                # Defence in depth - we still return the result; the
                # cache simply won't remember it.
                pass
        # 17) Persist the appropriate audit event.
        self._emit_event(result, schema_errors=errors)
        return result



    # ==================================================================
    # Helpers
    # ==================================================================
    def _client_model_name(self) -> str:
        if self._client is None:
            return "none"
        return str(getattr(self._client, "model_name", "unknown"))

    @staticmethod
    def _safe_enum(value: Any, enum_cls: type, fallback: Any) -> Any:
        if value is None:
            return fallback
        try:
            return enum_cls(value)
        except (ValueError, TypeError):
            return fallback

    @staticmethod
    def _dedupe_tags(tags: list[LLMRiskTag]) -> tuple[LLMRiskTag, ...]:
        seen: set[LLMRiskTag] = set()
        out: list[LLMRiskTag] = []
        for tag in tags:
            if tag in seen:
                continue
            seen.add(tag)
            out.append(tag)
        return tuple(out)

    @staticmethod
    def _dedupe_reasons(
        reasons: list[LLMDegradedReason],
    ) -> tuple[LLMDegradedReason, ...]:
        seen: set[LLMDegradedReason] = set()
        out: list[LLMDegradedReason] = []
        for reason in reasons:
            if reason in seen:
                continue
            seen.add(reason)
            out.append(reason)
        return tuple(out)

    # ------------------------------------------------------------------
    def _build_degraded_result(
        self,
        *,
        inp: LLMInterpretationInput,
        model_name: str,
        degraded_reasons: tuple[LLMDegradedReason, ...],
        stripped_fields: tuple[str, ...],
        prompt_injection_detected: bool,
        cache_hit: bool,
        emit: bool,
        tags: tuple[LLMRiskTag, ...] = (),
        schema_errors: list[SchemaValidationError] | None = None,
        error_summary: str | None = None,
    ) -> LLMInterpretationResult:
        """Produce a safe, low-confidence degraded result.

        Used by every short-circuit path. The result is deterministic
        and JSON-safe; the only variable bits are the
        ``degraded_reasons`` and ``risk_tags`` lists. Tests assert
        the result NEVER carries a forbidden field and ALWAYS has
        ``degraded=True`` plus ``confidence=0``.
        """
        risk_tags = list(tags)
        if prompt_injection_detected and (
            LLMRiskTag.PROMPT_INJECTION_DETECTED not in risk_tags
        ):
            risk_tags.append(LLMRiskTag.PROMPT_INJECTION_DETECTED)
        if (
            LLMDegradedReason.SAFETY_LOCK in degraded_reasons
            or LLMDegradedReason.LLM_DISABLED in degraded_reasons
        ):
            if LLMRiskTag.DATA_INSUFFICIENT not in risk_tags:
                risk_tags.append(LLMRiskTag.DATA_INSUFFICIENT)
        if stripped_fields and (
            LLMRiskTag.FORBIDDEN_FIELD_STRIPPED not in risk_tags
        ):
            risk_tags.append(LLMRiskTag.FORBIDDEN_FIELD_STRIPPED)

        if error_summary:
            # Embed the exception class name in the audit notes so
            # debugging is possible without exposing untrusted text.
            if LLMRiskTag.SCHEMA_VIOLATION not in risk_tags:
                risk_tags.append(LLMRiskTag.SCHEMA_VIOLATION)

        result = LLMInterpretationResult(
            narrative="",
            catalyst=CatalystStrength.UNKNOWN,
            evidence_quality=EvidenceQuality.UNKNOWN,
            source_diversity=0,
            kol_concentration=0.0,
            bot_risk=0.0,
            hype_stage=HypeStage.UNKNOWN,
            contradictions=(),
            risk_tags=self._dedupe_tags(risk_tags),
            confidence=0.0,
            degraded=True,
            degraded_reasons=self._dedupe_reasons(list(degraded_reasons)),
            stripped_fields=tuple(stripped_fields),
            prompt_injection_detected=prompt_injection_detected,
            source_count=len(inp.sources),
            model_name=model_name,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            cache_hit=cache_hit,
            opportunity_id=inp.opportunity_id,
            symbol=inp.symbol,
            correlation_id=inp.correlation_id,
        )
        self._counters.degraded_results += 1
        if emit:
            self._emit_event(result, schema_errors=schema_errors)
        return result



    # ------------------------------------------------------------------
    def _result_from_cached_payload(
        self,
        *,
        inp: LLMInterpretationInput,
        payload: dict[str, Any],
        model_name: str,
        cache_hit: bool,
        injection_detected: bool,
    ) -> LLMInterpretationResult:
        """Reconstruct a result from a cached payload.

        The cache stores ONLY successful, schema-valid payloads (we
        never cache degraded results). We hydrate the typed value
        object from the cached fields and re-attach the per-call
        identity (opportunity_id / symbol / correlation_id /
        cache_hit) so the audit trail is faithful.
        """
        try:
            catalyst = CatalystStrength(payload.get("catalyst", "unknown"))
        except (ValueError, TypeError):
            catalyst = CatalystStrength.UNKNOWN
        try:
            evidence = EvidenceQuality(
                payload.get("evidence_quality", "unknown")
            )
        except (ValueError, TypeError):
            evidence = EvidenceQuality.UNKNOWN
        try:
            hype = HypeStage(payload.get("hype_stage", "unknown"))
        except (ValueError, TypeError):
            hype = HypeStage.UNKNOWN
        risk_tags: list[LLMRiskTag] = []
        for raw in payload.get("risk_tags", ()):
            try:
                risk_tags.append(LLMRiskTag(raw))
            except (ValueError, TypeError):
                continue
        if injection_detected and (
            LLMRiskTag.PROMPT_INJECTION_DETECTED not in risk_tags
        ):
            risk_tags.append(LLMRiskTag.PROMPT_INJECTION_DETECTED)
        result = LLMInterpretationResult(
            narrative=str(payload.get("narrative", "")),
            catalyst=catalyst,
            evidence_quality=evidence,
            source_diversity=int(payload.get("source_diversity", 0)),
            kol_concentration=float(payload.get("kol_concentration", 0.0)),
            bot_risk=float(payload.get("bot_risk", 0.0)),
            hype_stage=hype,
            contradictions=tuple(
                coerce_string_list(payload.get("contradictions", ()))
            ),
            risk_tags=self._dedupe_tags(risk_tags),
            confidence=float(payload.get("confidence", 0.0)),
            degraded=False,
            degraded_reasons=(),
            stripped_fields=(),
            prompt_injection_detected=injection_detected,
            source_count=len(inp.sources),
            model_name=model_name,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            cache_hit=cache_hit,
            opportunity_id=inp.opportunity_id,
            symbol=inp.symbol,
            correlation_id=inp.correlation_id,
        )
        self._counters.clean_results += 1
        self._emit_event(result, schema_errors=None)
        return result



    # ------------------------------------------------------------------
    def _emit_event(
        self,
        result: LLMInterpretationResult,
        *,
        schema_errors: list[SchemaValidationError] | None,
    ) -> None:
        """Write the appropriate audit event for ``result``.

        Phase 10C event vocabulary:

          - LLM_INTERPRETED       clean, schema-valid result
          - LLM_DEGRADED          degraded result (any reason)
          - LLM_SCHEMA_REJECTED   schema validator returned errors

        The event payload is the result's :meth:`to_payload` plus a
        ``schema_errors`` list when present. The payload is closed -
        no API key, no raw secret, no environment variable, no
        forbidden trade-action field.
        """
        if not self._config.emit_events_enabled or self._event_repo is None:
            return
        # Choose the event type. SCHEMA_REJECTED takes precedence over
        # plain DEGRADED so monitoring can fire on schema drift even
        # when other degraded reasons are also present.
        if schema_errors:
            event_type = EventType.LLM_SCHEMA_REJECTED
        elif result.degraded:
            event_type = EventType.LLM_DEGRADED
        else:
            event_type = EventType.LLM_INTERPRETED
        payload = result.to_payload()
        if schema_errors:
            payload["schema_errors"] = [e.to_payload() for e in schema_errors]
        # Attach a hash of the input for replay / dedup - never the
        # raw input.
        payload["input_hash"] = hashlib.sha256(
            (result.symbol or "").encode("utf-8")
            + b"|"
            + (result.correlation_id or "").encode("utf-8")
            + b"|"
            + str(result.generated_at).encode("utf-8")
        ).hexdigest()
        self._event_repo.append_event(
            Event(
                event_type=event_type,
                source_module=self.SOURCE_MODULE,
                payload=payload,
                symbol=result.symbol,
                timestamp=result.generated_at,
            )
        )
        if event_type is EventType.LLM_INTERPRETED:
            self._counters.events_interpreted += 1
        elif event_type is EventType.LLM_DEGRADED:
            self._counters.events_degraded += 1
        else:
            self._counters.events_schema_rejected += 1


# ===========================================================================
# Counters
# ===========================================================================
@dataclass
class _InterpreterCounters:
    """Lightweight counters for monitoring + boot banner."""

    disabled_skips: int = 0
    empty_input_skips: int = 0
    below_throttle_skips: int = 0
    no_client_skips: int = 0
    cache_hits: int = 0
    transport_timeouts: int = 0
    transport_errors: int = 0
    transport_exceptions: int = 0
    schema_rejections: int = 0
    forbidden_field_strips: int = 0
    degraded_results: int = 0
    clean_results: int = 0
    events_interpreted: int = 0
    events_degraded: int = 0
    events_schema_rejected: int = 0


__all__ = [
    "LLMGuardedInterpreter",
    "LLMInterpreterConfig",
    "LLMTokenBucket",
]
