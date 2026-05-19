"""Phase 10C - LLM Guarded Interpreter value objects (Issue #10 Part 3).

Frozen, JSON-safe dataclasses + typed enum vocabularies for the
:class:`app.llm.interpreter.LLMGuardedInterpreter` orchestrator.

Issue #10 Part 10C contract (excerpt):

    LLM 输出只允许包含:
        narrative
        catalyst
        evidence_quality
        source_diversity
        kol_concentration
        bot_risk
        hype_stage
        contradictions
        risk_tags
        confidence

    LLM 输出中禁止出现或保留:
        direction / leverage / position_size / target_price / order_type
        stop_price / take_profit / should_buy / should_short / trade_decision
        entry / exit / liquidation_price / margin_mode / risk_budget /
        order / signal_to_trade

    如果出现这些字段:
        1. 不得进入最终结果
        2. 必须记录为 stripped_fields
        3. 如果字段风险较高, 结果应标记为 degraded
        4. 不得触发任何交易动作

Phase 10C boundary
------------------

Nothing in this module:

  - imports an exchange SDK / HTTP / WebSocket / LLM client / Telegram
    bot library
  - reads ``os.environ`` for credentials
  - opens a socket
  - calls an LLM
  - defines a write surface (``create_order`` / ``cancel_order`` /
    ``set_leverage`` / ``set_margin_mode``)
  - mutates global state
  - calls :meth:`EventRepository.append_event` / ``append_many``

The LLMInterpretationResult is a *closed* schema - any consumer that
reaches into it will only ever see whitelisted intelligence fields
plus the safety-audit fields. There is no path from an
LLMInterpretationResult to a TradeDecision / OrderRequest /
RiskApproval. Phase 10D Telegram outbound (separate PR) will read
``to_payload()`` directly and never call the model itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.clock import now_ms


# ===========================================================================
# Enum vocabularies
# ===========================================================================
class HypeStage(str, Enum):
    """Spec §22.2 ``hype_stage`` vocabulary."""

    EARLY = "early"
    SPREADING = "spreading"
    CLIMAX = "climax"
    DECAY = "decay"
    UNKNOWN = "unknown"


class EvidenceQuality(str, Enum):
    """Spec §22.2 ``evidence_quality`` vocabulary (A > B > C > D).

    The ordering is deliberate so a future consumer can compare via
    the ordinal index. ``UNKNOWN`` is reserved for the degraded case.
    """

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    UNKNOWN = "unknown"


class CatalystStrength(str, Enum):
    """Spec §22.2 ``catalyst`` vocabulary."""

    REAL = "real"
    WEAK = "weak"
    NONE = "none"
    UNKNOWN = "unknown"


class LLMRiskTag(str, Enum):
    """Spec §22.2 ``risk_tags`` vocabulary.

    The Phase 10C interpreter ALSO appends one of these tags
    automatically when the guardrails fire (e.g. a forbidden field was
    stripped, an injection pattern was detected). Free-form risk tags
    from the model are dropped.
    """

    PROMPT_INJECTION_DETECTED = "prompt_injection_detected"
    FORBIDDEN_FIELD_STRIPPED = "forbidden_field_stripped"
    LOW_CONFIDENCE = "low_confidence"
    LOW_SOURCE_DIVERSITY = "low_source_diversity"
    KOL_CONCENTRATION_HIGH = "kol_concentration_high"
    BOT_RISK_HIGH = "bot_risk_high"
    BOT_AMPLIFICATION_RISK = "bot_amplification_risk"
    NARRATIVE_AFTER_PUMP = "narrative_after_pump"
    CONTRADICTIONS_PRESENT = "contradictions_present"
    EVIDENCE_QUALITY_LOW = "evidence_quality_low"
    SCHEMA_VIOLATION = "schema_violation"
    DATA_INSUFFICIENT = "data_insufficient"


class LLMDegradedReason(str, Enum):
    """Why a result was downgraded.

    These are the only admissible degraded labels. The interpreter
    NEVER invents a free-form reason; it picks one of these or a
    short tuple of these.
    """

    LLM_DISABLED = "llm_disabled"
    NO_API_KEY = "no_api_key"
    BELOW_TOKEN_THROTTLE = "below_token_throttle"
    EMPTY_INPUT = "empty_input"
    PROMPT_INJECTION_DETECTED = "prompt_injection_detected"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    FORBIDDEN_FIELD_PRESENT = "forbidden_field_present"
    TIMEOUT = "timeout"
    TRANSPORT_ERROR = "transport_error"
    EXCEPTION = "exception"
    LOW_CONFIDENCE = "low_confidence"
    SAFETY_LOCK = "safety_lock"


class TokenThrottleTier(str, Enum):
    """Spec §22.4 anomaly-score throttle tiers.

    ``SKIP`` means the interpreter does not call the model at all and
    returns a degraded result with reason ``BELOW_TOKEN_THROTTLE``.
    """

    SKIP = "skip"
    LIGHT = "light"
    STANDARD = "standard"
    FULL = "full"


# ===========================================================================
# Input bundle
# ===========================================================================
@dataclass(frozen=True)
class LLMInterpretationInput:
    """Caller-supplied input to :class:`LLMGuardedInterpreter.interpret`.

    Spec §22.1 input contract: post text + signal context. Phase 8.5
    ``learning_ready`` may be passed through; the interpreter never
    mutates it.

    The :attr:`source_text` MUST be the post / signal text the
    interpreter is supposed to compress. The interpreter cleans
    /sanitises it before sending to the model; the caller does NOT
    need to escape it manually but is welcome to.
    """

    source_text: str
    symbol: str | None = None
    opportunity_id: str | None = None
    anomaly_score: float | None = None
    price_change_pct: float | None = None
    oi_change_pct: float | None = None
    funding_change_pct: float | None = None
    sources: tuple[str, ...] = field(default_factory=tuple)
    timestamp: int | None = None
    learning_ready: dict[str, Any] | None = None
    # An opaque correlation id the caller can attach so logs/replay
    # can stitch this interpretation back to the upstream signal.
    correlation_id: str | None = None


# ===========================================================================
# Result
# ===========================================================================
@dataclass(frozen=True)
class LLMInterpretationResult:
    """Final, redacted, JSON-safe result of one interpretation.

    Field set is fixed by Issue #10 Part 10C. The whitelisted
    business fields are :attr:`narrative` ... :attr:`confidence`; the
    safety / audit fields are :attr:`degraded` ... :attr:`generated_at`.

    Read-only invariant
    -------------------

    The interpreter constructs one of these per call and never
    persists it to ``events.db`` directly. The interpreter emits the
    appropriate ``LLM_INTERPRETED`` / ``LLM_DEGRADED`` /
    ``LLM_SCHEMA_REJECTED`` event with the JSON-safe payload from
    :meth:`to_payload`; Phase 10D Telegram outbound is the eventual
    sink, but Phase 10C does not introduce that surface.
    """

    # ---- Whitelisted business fields (Issue contract) ----
    narrative: str
    catalyst: CatalystStrength
    evidence_quality: EvidenceQuality
    source_diversity: int
    kol_concentration: float
    bot_risk: float
    hype_stage: HypeStage
    contradictions: tuple[str, ...]
    risk_tags: tuple[LLMRiskTag, ...]
    confidence: float

    # ---- Safety / audit fields ----
    degraded: bool
    degraded_reasons: tuple[LLMDegradedReason, ...]
    stripped_fields: tuple[str, ...]
    prompt_injection_detected: bool
    source_count: int
    model_name: str
    prompt_version: str
    schema_version: str
    cache_hit: bool
    generated_at: int = field(default_factory=now_ms)
    # Optional pass-through identity for Replay (Phase 10A) - the
    # interpreter copies it from the input bundle.
    opportunity_id: str | None = None
    symbol: str | None = None
    correlation_id: str | None = None

    # ---- Helpers --------------------------------------------------------
    @property
    def is_degraded(self) -> bool:
        return self.degraded

    @property
    def risk_tag_values(self) -> tuple[str, ...]:
        return tuple(t.value for t in self.risk_tags)

    @property
    def degraded_reason_values(self) -> tuple[str, ...]:
        return tuple(r.value for r in self.degraded_reasons)

    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-safe dict representation.

        The payload is *closed*: it carries only the fields above.
        There is no ``direction`` / ``leverage`` / ``order`` / etc. -
        Phase 10C guarantees this at the type level.
        """
        return {
            "narrative": str(self.narrative),
            "catalyst": self.catalyst.value,
            "evidence_quality": self.evidence_quality.value,
            "source_diversity": int(self.source_diversity),
            "kol_concentration": float(self.kol_concentration),
            "bot_risk": float(self.bot_risk),
            "hype_stage": self.hype_stage.value,
            "contradictions": list(self.contradictions),
            "risk_tags": [t.value for t in self.risk_tags],
            "confidence": float(self.confidence),
            "degraded": bool(self.degraded),
            "degraded_reasons": [r.value for r in self.degraded_reasons],
            "stripped_fields": list(self.stripped_fields),
            "prompt_injection_detected": bool(self.prompt_injection_detected),
            "source_count": int(self.source_count),
            "model_name": str(self.model_name),
            "prompt_version": str(self.prompt_version),
            "schema_version": str(self.schema_version),
            "cache_hit": bool(self.cache_hit),
            "generated_at": int(self.generated_at),
            "opportunity_id": self.opportunity_id,
            "symbol": self.symbol,
            "correlation_id": self.correlation_id,
        }


__all__ = [
    "HypeStage",
    "EvidenceQuality",
    "CatalystStrength",
    "LLMRiskTag",
    "LLMDegradedReason",
    "TokenThrottleTier",
    "LLMInterpretationInput",
    "LLMInterpretationResult",
]
