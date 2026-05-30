"""AMA-RT Live Foundation v0 (PR110).

This package builds the SAFETY FOUNDATION for AMA-RT's transition from
large-scale cloud blind testing to a 10U small-capital live-preparation
posture. It is the hard boundary that keeps the historical / blind /
replay / simulated / paper-shadow stack away from any live execution.

================================================================
HARD SAFETY BOUNDARY (PR110)
================================================================

  phase_12_forbidden            = True
  live_trading                  = False   (by default)
  exchange_live_orders          = False   (by default)
  binance_private_api_enabled   = False   (by default)
  telegram_outbound_enabled     = False   (by default)
  ai_trade_authority            = False
  trade_authority               = False   (by default)
  right_tail_live_boost_enabled = False   (by default)

PR110 does NOT:
  - connect the real Binance order / account / position / leverage /
    margin endpoints,
  - place / cancel a real order, change leverage, or change margin mode,
  - enable real Telegram outbound,
  - enable Phase 12,
  - let AI decide direction / size / leverage / stop / target / exit,
  - let a Telegram command bypass the Risk Engine,
  - let any blind / replay / sim module influence live execution,
  - auto-escalate a capital profile, or auto-enter LIVE_LIMITED on a
    restart, or auto-tune from blind / replay results, or let a future
    label / MFE / MAE / completed_tail_label influence a live decision.

What PR110 DOES build:
  1. Live Path Isolation (:mod:`app.live.path_isolation`,
     :mod:`app.live.gateway`).
  2. Runtime Mode Guard - LIVE_SHADOW / LIVE_LIMITED
     (:mod:`app.live.runtime_mode`).
  3. Capital Profile Ladder - 1U .. 10,000,000U
     (:mod:`app.live.capital_profile`).
  4. Capital Event Contract (:mod:`app.live.capital_event`).
  5. Right-tail Leverage Gate - deterministic, profile-bound
     (:mod:`app.live.leverage_gate`).
  6. Telegram Operator Contract
     (:mod:`app.live.telegram_operator_contract`).

LIVE_SHADOW (空盘跑) and LIVE_LIMITED (有资金跑) are DIFFERENT and must
never be confused: the former can never move real capital; the latter
is the only mode that ever could (in a future PR) and only behind the
operator confirmation handshake.
"""

from app.core.enums import LiveRuntimeMode, OrderSource
from app.core.errors import (
    LeverageGateViolation,
    LiveModeViolation,
    LivePathIsolationViolation,
)
from app.live.capital_event import (
    CapitalEventCategory,
    CapitalEventLedger,
    CapitalEventType,
    LiveCapitalEvent,
    classify_capital_event,
)
from app.live.capital_profile import (
    AUTO_ESCALATION_ALLOWED,
    CAPITAL_PROFILE_LADDER,
    CAPITAL_PROFILE_ORDER,
    CapitalProfile,
    CapitalProfileId,
    ProfileChangeRequest,
    ProfileMismatch,
    build_profile_change_request,
    detect_profile_mismatch,
    get_profile,
    suggest_profile_for_equity,
)
from app.live.gateway import LiveExecutionGateway
from app.live.leverage_gate import (
    FORBIDDEN_LEVERAGE_INPUT_FIELDS,
    LeverageDecision,
    RightTailLeverageEvidence,
    RightTailLeverageReason,
    evaluate_right_tail_leverage_permission,
)
from app.live.path_isolation import (
    IsolationDecision,
    LiveOrderIntent,
    LivePathIsolationGuard,
    classify_source_module,
)
from app.live.runtime_mode import (
    PR110_INITIAL_LIVE_LIMITED_PROFILE,
    LiveModeGuard,
    LiveModeState,
    LiveModeSwitchRequest,
    LiveModeSwitchResult,
)
from app.live.telegram_operator_contract import (
    ALL_CARD_TYPES,
    COMMON_FIELDS,
    LIVE_CARD_TYPES,
    LIVE_EXECUTION_ADAPTER_AVAILABLE,
    OPERATOR_COMMANDS,
    PLANNED_FIELDS,
    REAL_ORDER_FIELDS,
    SHADOW_CARD_TYPES,
    OperatorCardType,
    OperatorCommand,
    build_audit_payload,
    build_operator_card,
    parse_operator_command,
    render_operator_card,
)

__all__ = [
    # enums / errors
    "OrderSource",
    "LiveRuntimeMode",
    "LivePathIsolationViolation",
    "LiveModeViolation",
    "LeverageGateViolation",
    # path isolation + gateway
    "LiveOrderIntent",
    "IsolationDecision",
    "LivePathIsolationGuard",
    "classify_source_module",
    "LiveExecutionGateway",
    # runtime mode
    "LiveModeGuard",
    "LiveModeState",
    "LiveModeSwitchRequest",
    "LiveModeSwitchResult",
    "PR110_INITIAL_LIVE_LIMITED_PROFILE",
    # capital profile
    "CapitalProfile",
    "CapitalProfileId",
    "CAPITAL_PROFILE_LADDER",
    "CAPITAL_PROFILE_ORDER",
    "AUTO_ESCALATION_ALLOWED",
    "get_profile",
    "suggest_profile_for_equity",
    "detect_profile_mismatch",
    "ProfileMismatch",
    "ProfileChangeRequest",
    "build_profile_change_request",
    # capital event
    "CapitalEventType",
    "CapitalEventCategory",
    "LiveCapitalEvent",
    "CapitalEventLedger",
    "classify_capital_event",
    # leverage gate
    "RightTailLeverageEvidence",
    "RightTailLeverageReason",
    "LeverageDecision",
    "evaluate_right_tail_leverage_permission",
    "FORBIDDEN_LEVERAGE_INPUT_FIELDS",
    # telegram operator contract
    "OperatorCommand",
    "OPERATOR_COMMANDS",
    "OperatorCardType",
    "SHADOW_CARD_TYPES",
    "LIVE_CARD_TYPES",
    "ALL_CARD_TYPES",
    "COMMON_FIELDS",
    "PLANNED_FIELDS",
    "REAL_ORDER_FIELDS",
    "LIVE_EXECUTION_ADAPTER_AVAILABLE",
    "parse_operator_command",
    "build_operator_card",
    "render_operator_card",
    "build_audit_payload",
]
