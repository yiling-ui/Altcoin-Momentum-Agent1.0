"""Phase 10A Replay Engine package (Issue #10 Part 1).

Read-only replay over events.db. Public surface:

    ReplayEngine                   top-level engine
    PaperTradeReplay               one paper trade lifecycle
    CapitalRebaseReplay            one capital rebase event timeline
    RiskDecisionReplay             one RISK_APPROVED / RISK_REJECTED
    IncidentReplay                 one incident lifecycle (open / resolve)
    StateTransitionReplay          one symbol's TradeState ladder
    TelegramCommandReplay          one TELEGRAM_COMMAND_RECEIVED row
    LearningReadyReplay            Phase 8.5 learning-ready payload reader
    P0LatchedPauseInvariantReport  audit over reconciliation passes

    DiffEntry                      one row of a structural diff
    DiffKind                       MATCH / MISSING / EXTRA / REORDERED
    ReplayDiffReport               compare_event_chains() result
    compare_event_chains           pure-function chain diff

    Loader helpers (read-only, no side effects):
        load_all_events
        stream_events
        load_events_for_order
        load_events_for_symbol
        load_events_for_position
        load_events_for_opportunity
        load_capital_flow_events
        load_risk_decision_events
        load_incident_lifecycle_events
        load_state_transition_events
        load_telegram_command_events
        load_reconciliation_events
        has_learning_ready
        extract_learning_ready
        opportunity_id_for
        pair_reconciliation_passes

Phase 10A boundary
------------------

Replay is **fundamentally** read-only. The package:

  - opens NO socket
  - imports NO exchange SDK / HTTP / WebSocket / LLM client / Telegram
    bot library
  - reads NO ``os.environ``
  - defines NO ``create_order`` / ``cancel_order`` / ``set_leverage``
    / ``set_margin_mode``
  - does NOT instantiate :class:`ExecutionFSMDriver`,
    :class:`Reconciler`, :class:`RiskEngine`,
    :class:`CapitalFlowEngine`, :class:`MarketDataBuffer`,
    :class:`MockExchangeClient`, or any other state-mutating component
  - is therefore SAFE to run against a production-grade events.db
    without any risk of mutating trading / capital / risk state

Out of scope for Part 10A
-------------------------

Part 10A intentionally does NOT ship:

  - LLM Guarded Interpreter / DeepSeek client (Part 10C)
  - Telegram outbound + Export commands (Part 10D)
  - Reflection Engine + mistake_tags (Part 10B)

Each of those parts will land in a separate PR with its own boundary
audit. Issue #10 will be closed by Part 10D.
"""

from app.replay.diff import (
    DiffEntry,
    DiffKind,
    ReplayDiffReport,
    compare_event_chains,
)
from app.replay.engine import (
    CANONICAL_CLOSED_PAPER_TRADE_CHAIN,
    CANONICAL_OPEN_PAPER_TRADE_CHAIN,
    CAPITAL_FLOW_EVENT_TYPES,
    CapitalRebaseReplay,
    INCIDENT_LIFECYCLE_EVENT_TYPES,
    IncidentReplay,
    LearningReadyReplay,
    P0LatchedPauseInvariantReport,
    PAPER_LIFECYCLE_EVENT_TYPES,
    PaperTradeReplay,
    RECONCILIATION_EVENT_TYPES,
    RISK_DECISION_EVENT_TYPES,
    ReplayEngine,
    RiskDecisionReplay,
    StateTransitionReplay,
    TelegramCommandReplay,
)
from app.replay.loaders import (
    extract_learning_ready,
    has_learning_ready,
    load_all_events,
    load_capital_flow_events,
    load_events_for_opportunity,
    load_events_for_order,
    load_events_for_position,
    load_events_for_symbol,
    load_incident_lifecycle_events,
    load_reconciliation_events,
    load_risk_decision_events,
    load_state_transition_events,
    load_telegram_command_events,
    opportunity_id_for,
    pair_reconciliation_passes,
    stream_events,
)

__all__ = [
    # Engine
    "ReplayEngine",
    # Replay value objects
    "PaperTradeReplay",
    "CapitalRebaseReplay",
    "RiskDecisionReplay",
    "IncidentReplay",
    "StateTransitionReplay",
    "TelegramCommandReplay",
    "LearningReadyReplay",
    "P0LatchedPauseInvariantReport",
    # Diff
    "DiffEntry",
    "DiffKind",
    "ReplayDiffReport",
    "compare_event_chains",
    # Loaders
    "load_all_events",
    "stream_events",
    "load_events_for_order",
    "load_events_for_symbol",
    "load_events_for_position",
    "load_events_for_opportunity",
    "load_capital_flow_events",
    "load_risk_decision_events",
    "load_incident_lifecycle_events",
    "load_state_transition_events",
    "load_telegram_command_events",
    "load_reconciliation_events",
    "has_learning_ready",
    "extract_learning_ready",
    "opportunity_id_for",
    "pair_reconciliation_passes",
    # Constants
    "CANONICAL_CLOSED_PAPER_TRADE_CHAIN",
    "CANONICAL_OPEN_PAPER_TRADE_CHAIN",
    "PAPER_LIFECYCLE_EVENT_TYPES",
    "CAPITAL_FLOW_EVENT_TYPES",
    "INCIDENT_LIFECYCLE_EVENT_TYPES",
    "RECONCILIATION_EVENT_TYPES",
    "RISK_DECISION_EVENT_TYPES",
]
