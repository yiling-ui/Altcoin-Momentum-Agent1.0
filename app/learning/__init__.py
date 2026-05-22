"""Phase 8.5 - Learning-Ready Data Contract (passive, additive).

This package ships the *data contract* that future phases (Replay,
MFE/MAE, Tail Labeling, Dataset Builder, AI Learning) will consume.
It does **NOT** implement:

  - Full AI Learning
  - Feature Store
  - Model training
  - Strategy ordering
  - Live trading
  - Real network access
  - LLM inference
  - Telegram outbound

Public surface
--------------

    OpportunityIdentity              identity object for one candidate
    make_opportunity_id              deterministic UUID-based factory
    make_scan_batch_id               deterministic batch identifier

    signal_snapshot_to_payload       SignalSnapshot -> JSON-safe dict
    payload_to_signal_snapshot       inverse round-trip

    VirtualTradePlan                 virtual entry / stop / TP plan
    virtual_trade_plan_to_payload    serialisation helper
    payload_to_virtual_trade_plan    inverse round-trip

    ConfigVersions                   strategy / risk / scoring / capital
    config_versions_to_payload       serialisation helper
    payload_to_config_versions       inverse round-trip

    RiskRejectedLearningPayload      typed RISK_REJECTED enrichment
    risk_rejected_to_payload         serialisation helper

    LearningReadyContext             top-level aggregator
    attach_learning_ready            mutation-free payload merger
    LEARNING_READY_KEY               event payload key constant ("learning_ready")
    LEARNING_READY_EVENT_TYPES       11 event types that may carry learning_ready

Phase 8.5 boundary
------------------

Every object in this package is a frozen value object or a pure
function. Nothing here:

  - Imports an exchange SDK, an LLM client, a Telegram library, or any
    HTTP / WebSocket client.
  - Reads `os.environ` for credentials.
  - Mutates global state.
  - Calls `EventRepository.append_event` directly.
  - Constructs an `app.core.models.TradeDecision`, an
    `app.execution.fsm.ExecutionFSM` transition, or any order surface.

The `LearningReadyContext.to_event_payload()` helper emits a
deterministic JSON-safe dict so the existing `EventRepository`
substrate persists and replays it byte-for-byte without any schema
change to events.db.
"""

from app.learning.context import (
    ADAPTIVE_LEARNING_READY_EVENT_TYPES,
    LEARNING_READY_EVENT_TYPES,
    LEARNING_READY_KEY,
    LearningReadyContext,
    attach_learning_ready,
)
from app.learning.identity import (
    OpportunityIdentity,
    make_opportunity_id,
    make_scan_batch_id,
)
from app.learning.risk_payload import (
    RiskRejectedLearningPayload,
    risk_rejected_to_payload,
)
from app.learning.signal_snapshot import (
    payload_to_signal_snapshot,
    signal_snapshot_to_payload,
)
from app.learning.versions import (
    ConfigVersions,
    config_versions_to_payload,
    payload_to_config_versions,
)
from app.learning.virtual_trade import (
    VirtualTradePlan,
    payload_to_virtual_trade_plan,
    virtual_trade_plan_to_payload,
)

__all__ = [
    # Identity
    "OpportunityIdentity",
    "make_opportunity_id",
    "make_scan_batch_id",
    # SignalSnapshot serialisation
    "signal_snapshot_to_payload",
    "payload_to_signal_snapshot",
    # VirtualTradePlan
    "VirtualTradePlan",
    "virtual_trade_plan_to_payload",
    "payload_to_virtual_trade_plan",
    # ConfigVersions
    "ConfigVersions",
    "config_versions_to_payload",
    "payload_to_config_versions",
    # Risk learning payload
    "RiskRejectedLearningPayload",
    "risk_rejected_to_payload",
    # LearningReadyContext + plumbing
    "LearningReadyContext",
    "attach_learning_ready",
    "LEARNING_READY_KEY",
    "LEARNING_READY_EVENT_TYPES",
    "ADAPTIVE_LEARNING_READY_EVENT_TYPES",
]
