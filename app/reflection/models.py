"""Phase 10B - Reflection Engine value objects (Issue #10 Part 2).

Frozen, JSON-safe value objects produced by
:class:`app.reflection.engine.ReflectionEngine`. Each shape mirrors the
Issue #10 Part 10B contract verbatim:

    ReflectionResult must carry:
        opportunity_id
        client_order_id
        symbol
        setup
        result
        mistake_tags
        mfe
        mae
        tail_contribution
        entry_quality
        exit_quality
        risk_process_quality
        execution_quality
        data_quality_notes
        source_event_ids
        learning_ready
        generated_at

Phase 10B is read-only. Nothing in this module:

  - imports an exchange SDK / HTTP / WebSocket / LLM client / Telegram
    bot library
  - reads ``os.environ`` for credentials
  - opens a socket
  - calls an LLM
  - defines a write surface (``create_order`` / ``cancel_order`` /
    ``set_leverage`` / ``set_margin_mode``)
  - mutates global state
  - calls :meth:`EventRepository.append_event` / ``append_many``

Determinism rules
-----------------

When the underlying data is insufficient to answer a question (e.g.
the events.db window does not contain enough price observations to
compute MFE / MAE) the value is set to ``None`` and the reason is
recorded in ``data_quality_notes`` as a typed
:class:`UnknownReason`. The Reflection Engine NEVER fabricates a
fallback number.

JSON serialisation
------------------

Every value object exposes a ``to_payload()`` method that renders a
JSON-safe dict. Phase 10D Telegram outbound (a separate PR) will
consume these payloads directly; Phase 10B does NOT introduce any
outbound surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.core.clock import now_ms
from app.reflection.tags import MistakeTag


# ===========================================================================
# Per-axis quality scores
# ===========================================================================
class QualityScore(str, Enum):
    """Coarse quality score for one axis of a Reflection result.

    The vocabulary is deliberately narrow so the score is
    structurally comparable across runs. ``UNKNOWN`` is used when the
    Reflection Engine has insufficient data to assign a HIGH /
    MEDIUM / LOW; the corresponding :class:`UnknownReason` lands in
    ``data_quality_notes``.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


# ===========================================================================
# Trade outcome label
# ===========================================================================
class TradeOutcome(str, Enum):
    """Coarse trade-outcome label.

    Determined from the Phase 9 paper-trade lifecycle plus the
    realised PnL on the closing event. ``OPEN`` is used while the
    position has not been closed; ``UNKNOWN`` is used when the
    lifecycle is unreachable (e.g. risk-rejected before ORDER_SENT).
    """

    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    PROTECTED = "protected"
    OPEN = "open"
    UNKNOWN = "unknown"


# ===========================================================================
# Data-quality reason vocabulary
# ===========================================================================
class UnknownReason(str, Enum):
    """Why a Reflection Engine output is ``None`` / ``UNKNOWN``.

    These are the *only* admissible "we don't know" labels. The
    Reflection Engine never invents a free-form reason; it picks one
    of these or, in rare cases, attaches several.
    """

    INSUFFICIENT_PRICE_PATH = "insufficient_price_path"
    NO_FILL_RECORDED = "no_fill_recorded"
    NO_VIRTUAL_TRADE_PLAN = "no_virtual_trade_plan"
    NO_SIGNAL_SNAPSHOT = "no_signal_snapshot"
    NO_RIGHT_TAIL_AMPLIFY_LIFECYCLE = "no_right_tail_amplify_lifecycle"
    NO_OPPORTUNITY_ID = "no_opportunity_id"
    NO_LIFECYCLE_EVENTS = "no_lifecycle_events"
    NO_REALISED_PNL = "no_realised_pnl"
    NO_RISK_DECISION_TRAIL = "no_risk_decision_trail"
    NO_STATE_TRANSITION_TRAIL = "no_state_transition_trail"
    NO_CONFIG_VERSIONS = "no_config_versions"


# ===========================================================================
# Reflection input
# ===========================================================================
@dataclass(frozen=True)
class ReflectionInput:
    """Bundle of inputs the Reflection Engine consumes.

    A caller may construct a :class:`ReflectionInput` directly (tests
    do this) or use the :meth:`ReflectionEngine.reflect_paper_trade`
    convenience entry point that builds one from a
    :class:`PaperTradeReplay`.

    Phase 10B does NOT recompute Replay output - we consume it. The
    Replay value objects are themselves read-only.
    """

    # Required: the paper-trade lifecycle being reflected on. A typed
    # forward reference would couple this module to ``app.replay``;
    # we type as Any so import order stays one-way.
    paper_trade: Any
    # Optional: surrounding decision context the Phase 10A engine
    # already reconstructs from events.db. Phase 10B uses these but
    # does not require them - tests can pass empty tuples to exercise
    # the "data insufficient" path.
    risk_decisions: tuple[Any, ...] = field(default_factory=tuple)
    state_transitions: Any | None = None
    incidents: tuple[Any, ...] = field(default_factory=tuple)
    # Phase 8.5 contract: caller-supplied learning_ready dict so the
    # Reflection engine can index into virtual_trade_plan,
    # signal_snapshot, config_versions, opportunity, etc. without
    # re-reading events.db.
    learning_ready: dict[str, Any] | None = None


# ===========================================================================
# Reflection result
# ===========================================================================
@dataclass(frozen=True)
class ReflectionResult:
    """One Reflection result for one paper-trade lifecycle.

    Issue #10 Part 10B contract: the field set is fixed and the
    ``mistake_tags`` are drawn from :class:`MistakeTag`. The shape is
    JSON-safe via :meth:`to_payload`.

    Read-only invariant
    -------------------

    The Reflection Engine constructs one of these per call and never
    persists it to ``events.db`` (or any other database). Phase 10D
    will read this value object and emit a Telegram document; Phase
    10B does not introduce any outbound surface.
    """

    opportunity_id: str | None
    client_order_id: str | None
    symbol: str | None
    setup: str
    result: TradeOutcome
    mistake_tags: tuple[MistakeTag, ...]
    mfe: float | None
    mae: float | None
    tail_contribution: float | None
    entry_quality: QualityScore
    exit_quality: QualityScore
    risk_process_quality: QualityScore
    execution_quality: QualityScore
    data_quality_notes: tuple[UnknownReason, ...]
    source_event_ids: tuple[str, ...]
    learning_ready: dict[str, Any] | None
    generated_at: int = field(default_factory=now_ms)

    # ------------------------------------------------------------------
    @property
    def has_data_quality_notes(self) -> bool:
        return bool(self.data_quality_notes)

    @property
    def mistake_tag_values(self) -> tuple[str, ...]:
        return tuple(t.value for t in self.mistake_tags)

    # ------------------------------------------------------------------
    def to_payload(self) -> dict[str, Any]:
        """Return a JSON-safe dict representation of the result."""
        return {
            "opportunity_id": self.opportunity_id,
            "client_order_id": self.client_order_id,
            "symbol": self.symbol,
            "setup": str(self.setup),
            "result": self.result.value,
            "mistake_tags": [t.value for t in self.mistake_tags],
            "mfe": (float(self.mfe) if self.mfe is not None else None),
            "mae": (float(self.mae) if self.mae is not None else None),
            "tail_contribution": (
                float(self.tail_contribution)
                if self.tail_contribution is not None
                else None
            ),
            "entry_quality": self.entry_quality.value,
            "exit_quality": self.exit_quality.value,
            "risk_process_quality": self.risk_process_quality.value,
            "execution_quality": self.execution_quality.value,
            "data_quality_notes": [
                r.value for r in self.data_quality_notes
            ],
            "source_event_ids": list(self.source_event_ids),
            "learning_ready_present": self.learning_ready is not None,
            "generated_at": int(self.generated_at),
        }


__all__ = [
    "QualityScore",
    "TradeOutcome",
    "UnknownReason",
    "ReflectionInput",
    "ReflectionResult",
]
