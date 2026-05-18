"""Core enumerations for AMA-RT.

Mirrors Spec §46 (附录: 核心枚举) and Issues #1, #5, #6, #7, #9, #10.

Phase 1 ships the full enum vocabulary so that future phases never need to
amend public APIs in `app/core/`. Behavioural code that consumes these
values is intentionally NOT shipped in Phase 1 - those modules are skeletons.
"""

from __future__ import annotations

from enum import Enum


# ---------------------------------------------------------------------------
# Trading mode (Spec §46.5)
# ---------------------------------------------------------------------------
class TradingMode(str, Enum):
    READ_ONLY = "read_only"
    PAPER = "paper"
    MANUAL_CONFIRM = "manual_confirm"
    LIVE_LIMITED = "live_limited"
    LIVE_FULL = "live_full"


# ---------------------------------------------------------------------------
# Trade state machine (Spec §26.1, §46.1)
# ---------------------------------------------------------------------------
class TradeState(str, Enum):
    NO_TRADE = "no_trade"
    OBSERVE = "observe"
    SCOUT = "scout"
    CONFIRM = "confirm"
    ATTACK = "attack"
    RIGHT_TAIL_AMPLIFY = "right_tail_amplify"
    LOCK_PROFIT = "lock_profit"
    DISTRIBUTION_ALERT = "distribution_alert"
    FORCED_EXIT = "forced_exit"


# ---------------------------------------------------------------------------
# Execution FSM (Spec §30.1)
# ---------------------------------------------------------------------------
class ExecutionState(str, Enum):
    IDLE = "idle"
    SIGNAL_RECEIVED = "signal_received"
    RISK_CHECKED = "risk_checked"
    ORDER_SENT = "order_sent"
    ACK_RECEIVED = "ack_received"
    PARTIAL_FILLED = "partial_filled"
    FULL_FILLED = "full_filled"
    STOP_SENT = "stop_sent"
    STOP_CONFIRMED = "stop_confirmed"
    STOP_FAILED = "stop_failed"
    POSITION_OPEN = "position_open"
    EXIT_TRIGGERED = "exit_triggered"
    POSITION_CLOSING = "position_closing"
    POSITION_CLOSED = "position_closed"
    ERROR_PROTECTION = "error_protection"


# ---------------------------------------------------------------------------
# Opportunity grade (Spec §24, §46.2)
# ---------------------------------------------------------------------------
class OpportunityGrade(str, Enum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"
    D = "D"


# ---------------------------------------------------------------------------
# Manipulation level (Spec §21.3, §46.3)
# ---------------------------------------------------------------------------
class ManipulationLevel(str, Enum):
    M0 = "M0"  # no manipulation
    M1 = "M1"  # mild anomaly: observe / scout only
    M2 = "M2"  # clear induction: no attack
    M3 = "M3"  # heavy manipulation: no trading


# ---------------------------------------------------------------------------
# Trade confirmation level (Spec §20.3, §46.4)
# ---------------------------------------------------------------------------
class TradeConfirmationLevel(str, Enum):
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"


# ---------------------------------------------------------------------------
# Market regime (Spec §15.2)
# ---------------------------------------------------------------------------
class MarketRegime(str, Enum):
    MEME_RISK_ON = "MEME_RISK_ON"
    SECTOR_ROTATION = "SECTOR_ROTATION"
    BTC_ABSORPTION = "BTC_ABSORPTION"
    ALT_RISK_OFF = "ALT_RISK_OFF"
    SYSTEMIC_RISK = "SYSTEMIC_RISK"


# ---------------------------------------------------------------------------
# Account life tier (Spec §27.4)
# ---------------------------------------------------------------------------
class AccountLifeTier(str, Enum):
    A = "A"  # >= 1.5x   attack + right-tail allowed
    B = "B"  # 1.0-1.5x  normal
    C = "C"  # 0.7-1.0x  reduce frequency
    D = "D"  # 0.5-0.7x  no right-tail
    E = "E"  # 0.3-0.5x  observe / paper only
    F = "F"  # < 0.3x    halt and review


# ---------------------------------------------------------------------------
# Data reliability (Spec §13.3)
# ---------------------------------------------------------------------------
class DataReliability(str, Enum):
    A = "A"  # raw WS trades / order events
    B = "B"  # exchange REST
    C = "C"  # third-party aggregator
    D = "D"  # text / community / LLM inference

    def is_at_least(self, threshold: "DataReliability") -> bool:
        """Return True if this tier is >= the given threshold.

        A is the strongest, D is the weakest. Spec §13.3 forbids using a
        weak-tier signal alone to trigger an attack-grade decision; the
        Risk Engine in Issue #7 calls this helper when adjudicating.
        Phase 3 ships the helper next to the enum so all later phases
        compare tiers consistently.
        """
        order = {
            DataReliability.A: 4,
            DataReliability.B: 3,
            DataReliability.C: 2,
            DataReliability.D: 1,
        }
        return order[self] >= order[threshold]


# ---------------------------------------------------------------------------
# Exchange connection state (Spec §14.2 - WebSocket / REST health)
# ---------------------------------------------------------------------------
class ExchangeConnectionState(str, Enum):
    """Health of the WebSocket / REST link maintained by an ExchangeClient.

    Phase 3 (Issue #3) introduces this enum. The state is used by:
      - `ExchangeClientBase.health` to expose a single read-only health
        snapshot to upstream modules.
      - `MarketDataBuffer` (Issue #4) to mark data as `DATA_UNRELIABLE`
        when the connection drops below CONNECTED.
      - `RiskEngine` (Issue #7) as a No-Trade Gate input.

    Mapping to data reliability (Spec §13.3):
      CONNECTED      -> WebSocket originated data may be tier A
      DEGRADED       -> only REST tier B is trustworthy
      DISCONNECTED   -> no exchange data is trustworthy at all
      RECONNECTING   -> data is stale until CONNECTED is regained
      UNINITIALISED  -> client has never been started
    """

    UNINITIALISED = "uninitialised"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"

    @property
    def is_trustworthy(self) -> bool:
        """True if data sourced through this state can be considered
        reliable enough to feed downstream decisioning. Only CONNECTED
        is trustworthy in Phase 3."""
        return self is ExchangeConnectionState.CONNECTED


# ---------------------------------------------------------------------------
# Incident level (Spec §38.1, §46.6)
# ---------------------------------------------------------------------------
class IncidentLevel(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


# ---------------------------------------------------------------------------
# Trade direction
# ---------------------------------------------------------------------------
class Direction(str, Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"
