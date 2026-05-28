"""Phase 10B Reflection Engine package (Issue #10 Part 2).

Read-only, deterministic, structured reflection over Phase 10A
:class:`ReplayEngine` outputs and Phase 8.5 ``learning_ready``
payloads. Public surface:

    ReflectionEngine            top-level engine
    ReflectionConfig            tunable thresholds for tag rules
    ReflectionInput             value bundle the engine consumes
    ReflectionResult            one structured reflection result
    QualityScore                HIGH / MEDIUM / LOW / UNKNOWN axis label
    TradeOutcome                WIN / LOSS / BREAKEVEN / PROTECTED / OPEN / UNKNOWN
    UnknownReason               typed "data insufficient" reason vocabulary
    MistakeTag                  structured mistake-tag enum
    ISSUE_REQUIRED_MISTAKE_TAGS  the 12 tags Issue #10 Part 10B mandates
    DIAGNOSTIC_MISTAKE_TAGS     the Phase 10B diagnostic tags

    Metric helpers (deterministic, never fabricate):
        compute_mfe              maximum favourable excursion
        compute_mae              maximum adverse excursion
        compute_tail_contribution
                                 tail PnL attribution
        realized_pnl_for         realised PnL from POSITION_CLOSED
        MetricResult             value-or-unknown metric output

Phase 10B boundary
------------------

Reflection is **fundamentally** read-only. The package:

  - opens NO socket
  - imports NO exchange SDK / HTTP / WebSocket / LLM client / Telegram
    bot library
  - reads NO ``os.environ``
  - defines NO ``create_order`` / ``cancel_order`` / ``set_leverage``
    / ``set_margin_mode``
  - does NOT instantiate :class:`ExecutionFSMDriver`,
    :class:`Reconciler`, :class:`RiskEngine`,
    :class:`CapitalFlowEngine`, :class:`MarketDataBuffer`,
    :class:`MockExchangeClient`, :class:`BinanceClient`,
    :class:`IncidentRepository`, :class:`TelegramCommandCenter`, or
    :class:`RegimeEngine`
  - calls NO ``EventRepository.append_event`` / ``append_many``

Out of scope for Part 10B
-------------------------

Part 10B intentionally does NOT ship:

  - LLM Guarded Interpreter / DeepSeek client (Part 10C)
  - Telegram outbound + Export commands (Part 10D)
  - Real-trade persistence into trades.db / positions.db
  - Any free-form natural-language reflection (Issue brief: 禁止)
"""

from app.reflection.adaptive_11c import (
    ADAPTIVE_REFLECTION_EVENT_TYPES,
    FORBIDDEN_REFLECTION_PAYLOAD_KEYS,
    AdaptiveReflectionCase,
    AdaptiveReflectionForbiddenFieldError,
    AdaptiveReflectionInput,
    AdaptiveReflectionSeverity,
    AdaptiveReflectionSummary,
    AdaptiveReflectionTag,
    Reflection11CAdaptiveEngine,
)
from app.reflection.ai_reflection import (
    AI_REFLECTION_CASE_GENERATED,
    AI_REFLECTION_SUMMARY_GENERATED,
    AIReflectionCase,
    AIReflectionSeverity,
    AIReflectionSummary,
    AIReflectionTag,
    AIReplayReflectionEngine,
    FORBIDDEN_REFLECTION_TAGS,
    reflect_replay_case,
    reflect_replay_cases,
    replay_and_reflect_artefacts,
)
from app.reflection.engine import ReflectionConfig, ReflectionEngine
from app.reflection.metrics import (
    MetricResult,
    compute_mae,
    compute_mfe,
    compute_tail_contribution,
    realized_pnl_for,
)
from app.reflection.models import (
    QualityScore,
    ReflectionInput,
    ReflectionResult,
    TradeOutcome,
    UnknownReason,
)
from app.reflection.tags import (
    DIAGNOSTIC_MISTAKE_TAGS,
    ISSUE_REQUIRED_MISTAKE_TAGS,
    MistakeTag,
)

__all__ = [
    # Engine
    "ReflectionEngine",
    "ReflectionConfig",
    # Value objects
    "ReflectionInput",
    "ReflectionResult",
    "QualityScore",
    "TradeOutcome",
    "UnknownReason",
    # Tag vocabulary
    "MistakeTag",
    "ISSUE_REQUIRED_MISTAKE_TAGS",
    "DIAGNOSTIC_MISTAKE_TAGS",
    # Metric helpers
    "MetricResult",
    "compute_mfe",
    "compute_mae",
    "compute_tail_contribution",
    "realized_pnl_for",
    # Phase 11C.1C-C-B-B-B-E-B Reflection Extension
    "Reflection11CAdaptiveEngine",
    "AdaptiveReflectionTag",
    "AdaptiveReflectionSeverity",
    "AdaptiveReflectionInput",
    "AdaptiveReflectionCase",
    "AdaptiveReflectionSummary",
    "AdaptiveReflectionForbiddenFieldError",
    "ADAPTIVE_REFLECTION_EVENT_TYPES",
    "FORBIDDEN_REFLECTION_PAYLOAD_KEYS",
    # Phase AI-6 - AI Reflection Integration v0
    "AI_REFLECTION_CASE_GENERATED",
    "AI_REFLECTION_SUMMARY_GENERATED",
    "AIReflectionCase",
    "AIReflectionSeverity",
    "AIReflectionSummary",
    "AIReflectionTag",
    "AIReplayReflectionEngine",
    "FORBIDDEN_REFLECTION_TAGS",
    "reflect_replay_case",
    "reflect_replay_cases",
    "replay_and_reflect_artefacts",
]
