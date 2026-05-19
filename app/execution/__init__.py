"""Execution FSM package.

Phase 1 ships:

  - :class:`ExecutionFSM`       Phase 1 in-memory state machine skeleton.
  - :class:`IllegalTransition`  raised on a forbidden transition.

Phase 9 (Issue #9) adds:

  - :class:`ExecutionFSMDriver`  paper-mode Execution FSM driver.
  - :class:`OrderRequest`        frozen Pydantic v2 order descriptor.
  - :class:`OrderIntent`         vocabulary that decides is_new_open
                                 + reduce_only auto-resolution.
  - :class:`OrderKind`           LIMIT / MARKET / STOP_MARKET / STOP_LIMIT.
  - :class:`OrderSide`           BUY / SELL.
  - :class:`MarginMode`          ISOLATED only (cross margin forbidden).
  - :class:`TimeInForce`         GTC / IOC / FOK.
  - :class:`FillEvent`           one fill applied to a session.
  - :class:`StopEvent`           reduce-only stop attachment descriptor.
  - :class:`ExecutionSession`    per-order lifecycle state (mutable).
  - :class:`ExecutionResult`     return value of submit_order.
  - :class:`PaperLedger`         in-memory paper-mode order/stop/position
                                 store. Phase 9 NEVER touches the four
                                 ExchangeClientBase write surfaces; the
                                 SafeModeViolation refusals on
                                 create_order / cancel_order /
                                 set_leverage / set_margin_mode are
                                 unchanged.
  - :class:`PaperOrder` /
    :class:`PaperStop` /
    :class:`PaperPosition`       paper-mode value objects exposed by
                                 :class:`PaperLedger`.

Phase 9 boundary
----------------

The execution package does NOT:

  - import an exchange SDK or HTTP / WebSocket library
  - open a real network socket
  - call an LLM
  - read os.environ for credentials
  - subclass ExchangeClientBase
  - override the four ExchangeClientBase write surfaces
  - persist trades.db or positions.db rows (those land in a future PR
    behind a real exchange adapter)
"""

from app.execution.fsm import (
    ExecutionFSM,
    ExecutionFSMDriver,
    IllegalTransition,
)
from app.execution.models import (
    ExecutionResult,
    ExecutionSession,
    FillEvent,
    MarginMode,
    NEW_OPEN_INTENTS,
    OrderIntent,
    OrderKind,
    OrderRequest,
    OrderSide,
    REDUCE_ONLY_INTENTS,
    StopEvent,
    TimeInForce,
    TransitionRecord,
    side_for_direction,
)
from app.execution.paper_ledger import (
    PaperEquity,
    PaperLedger,
    PaperOrder,
    PaperPosition,
    PaperStop,
)

__all__ = [
    # Phase 1
    "ExecutionFSM",
    "IllegalTransition",
    # Phase 9 driver
    "ExecutionFSMDriver",
    "ExecutionResult",
    "ExecutionSession",
    "TransitionRecord",
    # Phase 9 order vocabulary
    "OrderRequest",
    "OrderIntent",
    "OrderKind",
    "OrderSide",
    "MarginMode",
    "TimeInForce",
    "FillEvent",
    "StopEvent",
    "NEW_OPEN_INTENTS",
    "REDUCE_ONLY_INTENTS",
    "side_for_direction",
    # Phase 9 paper ledger
    "PaperLedger",
    "PaperOrder",
    "PaperStop",
    "PaperPosition",
    "PaperEquity",
]
