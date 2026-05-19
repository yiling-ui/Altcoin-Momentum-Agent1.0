"""LearningReadyContext + payload-merge helper (Phase 8.5).

The :class:`LearningReadyContext` bundles every Phase 8.5 contract
into one object so a single emitter (Risk Engine, Scanner,
Confirmation, Manipulation, Universe, Liquidity, State Machine,
Capital Flow) can attach it to its event payload via
:func:`attach_learning_ready` without each emitter re-implementing
the merge logic.

Event types that may carry learning_ready
-----------------------------------------

The Issue contract enumerates 11 event types:

    PRE_ANOMALY_DETECTED
    ANOMALY_DETECTED
    TRADE_CONFIRMED
    MANIPULATION_DETECTED
    UNIVERSE_FILTERED
    LIQUIDITY_CHECKED
    RISK_APPROVED
    RISK_REJECTED
    STATE_TRANSITION
    CAPITAL_REBASE
    RISK_BUDGET_RECALCULATED

Phase 8.5 ships :data:`LEARNING_READY_EVENT_TYPES` as the
authoritative tuple so Issue #10 / future Telegram contract / future
Replay engine can iterate it without re-listing the strings.

Phase 8.5 boundary
------------------

The merge helper is a pure function. It accepts a dict, returns a
new dict, and never mutates either argument in place. The helper
does NOT call ``EventRepository.append_event``; emitters keep using
the existing repository contract unchanged.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.events import EventType
from app.learning.identity import OpportunityIdentity
from app.learning.risk_payload import RiskRejectedLearningPayload
from app.learning.signal_snapshot import signal_snapshot_to_payload
from app.learning.versions import ConfigVersions
from app.learning.virtual_trade import VirtualTradePlan

# The literal key under which every Phase 8.5 enrichment lands on
# an event payload. Keeping this as a single constant means no
# emitter has to hard-code the string and the export/redaction
# layer can index in deterministically.
LEARNING_READY_KEY = "learning_ready"

# Issue contract: the 11 event types that may carry a learning_ready
# enrichment. The set is exposed as a frozenset so callers can `in`-
# test cheaply, and as a tuple so the order is reproducible.
LEARNING_READY_EVENT_TYPES: tuple[EventType, ...] = (
    EventType.PRE_ANOMALY_DETECTED,
    EventType.ANOMALY_DETECTED,
    EventType.TRADE_CONFIRMED,
    EventType.MANIPULATION_DETECTED,
    EventType.UNIVERSE_FILTERED,
    EventType.LIQUIDITY_CHECKED,
    EventType.RISK_APPROVED,
    EventType.RISK_REJECTED,
    EventType.STATE_TRANSITION,
    EventType.CAPITAL_REBASE,
    EventType.RISK_BUDGET_RECALCULATED,
)


class LearningReadyContext(BaseModel):
    """Aggregator bundle for Phase 8.5 learning-ready enrichment.

    Every field is optional so an emitter can attach only the parts
    it knows. The :meth:`to_event_payload` helper renders a
    deterministic JSON-safe dict that is safe to merge into any
    existing event payload (existing keys are preserved).
    """

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=False)

    opportunity: OpportunityIdentity | None = None
    signal_snapshot: Any | None = None  # SignalSnapshot, kept Any to avoid hard import cycle
    virtual_trade_plan: VirtualTradePlan | None = None
    config_versions: ConfigVersions | None = None
    risk_decision: RiskRejectedLearningPayload | None = None
    source_phase: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    def to_event_payload(self) -> dict[str, Any]:
        """Render a JSON-safe dict for the ``learning_ready`` block."""
        out: dict[str, Any] = {}
        if self.opportunity is not None:
            out["opportunity"] = self.opportunity.to_payload()
        if self.signal_snapshot is not None:
            out["signal_snapshot"] = signal_snapshot_to_payload(self.signal_snapshot)
        if self.virtual_trade_plan is not None:
            out["virtual_trade_plan"] = self.virtual_trade_plan.to_payload()
        if self.config_versions is not None:
            out["config_versions"] = self.config_versions.to_payload()
        if self.risk_decision is not None:
            out["risk_decision"] = self.risk_decision.to_payload()
        if self.source_phase is not None:
            out["source_phase"] = str(self.source_phase)
        if self.extra:
            out["extra"] = dict(self.extra)
        return out


def attach_learning_ready(
    payload: dict[str, Any] | None,
    context: LearningReadyContext | None,
    *,
    key: str = LEARNING_READY_KEY,
) -> dict[str, Any]:
    """Return a NEW dict with ``payload`` plus a ``learning_ready`` block.

    Pure function - never mutates ``payload`` in place. If
    ``context`` is ``None`` the original payload is returned (still
    as a fresh shallow copy so the caller can mutate the result
    safely). If ``payload`` is ``None`` an empty dict is used as the
    base.

    Existing keys on ``payload`` are preserved verbatim. The
    ``learning_ready`` key is overwritten if both ``payload`` and
    ``context`` carry it; this is intentional so a Risk Engine
    enrichment always wins over a partial scanner enrichment that
    came earlier.
    """
    base: dict[str, Any] = dict(payload) if payload is not None else {}
    if context is None:
        return base
    base[key] = context.to_event_payload()
    return base


def is_learning_ready_event_type(event_type: EventType) -> bool:
    """True if ``event_type`` is one of the 11 Issue-listed types."""
    return event_type in LEARNING_READY_EVENT_TYPES
