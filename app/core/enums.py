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
# Phase 5 - Regime Engine sub-states (Spec §15.1, §15.2)
# ---------------------------------------------------------------------------
class BtcTrend(str, Enum):
    """Coarse BTC trend label produced by the Regime Engine.

    Phase 5 only ships the three macro labels Spec §15 actually uses to
    decide ALLOW / BLOCK; finer-grained labels (e.g. SLOW_GRIND vs
    PARABOLIC) belong to Issue #6 / #7 risk-tier work and are not in
    scope here.
    """

    UP = "UP"
    SIDEWAYS = "SIDEWAYS"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


class BtcVolatility(str, Enum):
    """Coarse BTC realised-volatility bucket produced by the Regime Engine."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"
    UNKNOWN = "UNKNOWN"


class AltLiquidity(str, Enum):
    """Coarse altcoin-liquidity bucket produced by the Regime Engine."""

    EXPANDING = "EXPANDING"
    STABLE = "STABLE"
    CONTRACTING = "CONTRACTING"
    DRY = "DRY"
    UNKNOWN = "UNKNOWN"


class RiskPermission(str, Enum):
    """**Regime-cycle permission bit. NOT a trade approval.**

    These four values are the *single permission bit Regime / Universe /
    Liquidity hand to the rest of the system*. They describe what the
    market *cycle* permits at the macro level, nothing more.

    A real opening decision in Phase 7+ MUST be the conjunction of:

      1. ``RegimeSnapshot.risk_permission`` (this enum, Spec §15.3)
      2. ``UniverseDecision.eligible`` (Spec §16)
      3. ``LiquidityDecision.passed`` and
         ``can_exit_position(...).feasible`` (Spec §19)
      4. Pre-anomaly / Anomaly score (Issue #6, Spec §17 / §18)
      5. Real-trade confirmation tier T2+ (Issue #6, Spec §20)
      6. Manipulation level <= M1 / M0 (Issue #6, Spec §21)
      7. ``RiskEngine.evaluate(...)`` final approval (Issue #7, Spec §27)
      8. ``ExecutionFSM`` valid-transition gate (Issue #9, Spec §30)

    A non-blocking value here is a NECESSARY but **NOT sufficient**
    condition. Phase 5 modules MUST NOT treat any of these labels as
    a trade authorisation.

    Semantic ladder (strict, do not collapse):

      - ``ALLOW_ATTACK``
        Macro cycle is risk-on. Higher tiers MAY graduate a candidate
        to a SCOUT or ATTACK trade state - subject to (2)-(8) above.
        Does NOT itself authorise an attack-sized position; does NOT
        authorise right-tail amplification (right_tail_enabled is
        locked False until Issue #7 + the Go/No-Go checklist clears).

      - ``ALLOW_SCOUT``
        Macro cycle is risk-off-with-survivors. Only OBSERVE or a
        very small SCOUT candidate is admissible. Phase 7's Risk
        Engine MUST further restrict: NO ATTACK, NO RIGHT_TAIL_AMPLIFY,
        and SCOUT size capped at the per-trade scout budget. The
        ``ALT_RISK_OFF -> ALLOW_SCOUT`` path is the same: it permits
        observation / minimal scouting, NOT attack-sizing.

      - ``OBSERVE_ONLY``
        No new opening. Existing positions may continue to be managed
        (LOCK_PROFIT / FORCED_EXIT) but no new SCOUT / ATTACK.

      - ``BLOCK_ALL``
        SYSTEMIC_RISK. No new opening of any kind. Reconciliation,
        kill_all and stop-management are still allowed. Phase 5's
        UniverseFilter and LiquidityFilter both list this in their
        ``blocking_risk_permissions`` set by default; Issue #7 will
        additionally route every trade-state transition to
        ``NO_TRADE``.

    Phase 5 ships the labels and the mapping. Phase 7+ translates
    them into concrete TradeState transitions and lever changes;
    Phase 5 does NOT take any trading action on its own.
    """

    ALLOW_ATTACK = "ALLOW_ATTACK"
    ALLOW_SCOUT = "ALLOW_SCOUT"
    OBSERVE_ONLY = "OBSERVE_ONLY"
    BLOCK_ALL = "BLOCK_ALL"


# ---------------------------------------------------------------------------
# Phase 5 - Universe Filter reject reasons (Issue #5 acceptance criterion 4)
# ---------------------------------------------------------------------------
class UniverseRejectReason(str, Enum):
    """Why a symbol failed the Universe Filter.

    A rejected symbol has at least one of these reasons attached. The
    full reject_reasons list is recorded on the UNIVERSE_FILTERED event
    so Issue #6 / #7 / #10 (Reflection) can reproduce the decision from
    events.db alone.
    """

    SPREAD_TOO_WIDE = "spread_too_wide"
    DEPTH_INSUFFICIENT = "depth_insufficient"
    TRADE_DISCONTINUOUS = "trade_discontinuous"
    CONTRACT_NOT_TRADING = "contract_not_trading"
    DATA_RELIABILITY_TOO_LOW = "data_reliability_too_low"
    DATA_DEGRADED = "data_degraded"
    VOLUME_BELOW_MINIMUM = "volume_below_minimum"
    ABNORMAL_DATA_FLAG = "abnormal_data_flag"
    REGIME_BLOCKED = "regime_blocked"


# ---------------------------------------------------------------------------
# Phase 5 - Liquidity Filter reject reasons
# ---------------------------------------------------------------------------
class LiquidityRejectReason(str, Enum):
    """Why a symbol / order failed the Liquidity Filter.

    Same persistence story as UniverseRejectReason: the full list is
    recorded on the LIQUIDITY_CHECKED event.
    """

    SPREAD_TOO_WIDE = "spread_too_wide"
    DEPTH_INSUFFICIENT = "depth_insufficient"
    SLIPPAGE_TOO_HIGH = "slippage_too_high"
    NO_EXIT_CHANNEL = "no_exit_channel"
    EXIT_TOO_SLOW = "exit_too_slow"
    BOOK_MISSING = "book_missing"
    DATA_DEGRADED = "data_degraded"
    REGIME_BLOCKED = "regime_blocked"


# ---------------------------------------------------------------------------
# Phase 6 - Pre-Anomaly Scanner reason tags (Issue #6, Spec §17.3)
# ---------------------------------------------------------------------------
class PreAnomalyReasonTag(str, Enum):
    """Reasons that contributed to a Pre-Anomaly score (Spec §17.2).

    The Pre-Anomaly Scanner emits ONE ``PRE_ANOMALY_DETECTED`` event per
    evaluation; the event's payload carries the full reason-tag list so
    Reflection (Issue #10) and Replay can rebuild the decision from
    events.db alone. Unlike the Phase 5 reject enums, these labels do
    not gate trading by themselves; the Risk Engine consults them
    indirectly through the score.

    Phase 6 ships a deterministic, additive scoring rule so a future
    YAML pull-through can adjust weights without renaming the tags.
    """

    VOLUME_BASE_EXPANSION = "volume_base_expansion"
    SPREAD_COMPRESSION = "spread_compression"
    BUY_PRESSURE_RISING = "buy_pressure_rising"
    OI_SOFT_RISE = "oi_soft_rise"
    FUNDING_NOT_OVERHEATED = "funding_not_overheated"
    MINOR_UPTREND = "minor_uptrend"
    DATA_DEGRADED = "data_degraded"
    REGIME_BLOCKED = "regime_blocked"
    INSUFFICIENT_HISTORY = "insufficient_history"


# ---------------------------------------------------------------------------
# Phase 6 - Anomaly Scanner reason tags (Issue #6, Spec §18.1)
# ---------------------------------------------------------------------------
class AnomalyReasonTag(str, Enum):
    """Reasons that contributed to an Anomaly score (Spec §18.1).

    Same persistence story as :class:`PreAnomalyReasonTag`: the full
    list is recorded on the ``ANOMALY_DETECTED`` event. The Spec §18.2
    weighted-sum formula is applied AFTER the tags are decided so the
    weights are tunable without changing the tag vocabulary.
    """

    OI_SPIKE = "oi_spike"
    CVD_SPIKE = "cvd_spike"
    VOLUME_SPIKE = "volume_spike"
    ATR_EXPANSION = "atr_expansion"
    FUNDING_EXTREME = "funding_extreme"
    LIQUIDATION_SPIKE = "liquidation_spike"
    SWEEP = "sweep"
    MULTI_TIMEFRAME_BREAKOUT = "multi_timeframe_breakout"
    DATA_DEGRADED = "data_degraded"
    REGIME_BLOCKED = "regime_blocked"
    INSUFFICIENT_HISTORY = "insufficient_history"


# ---------------------------------------------------------------------------
# Phase 6 - Real Trade Confirmation reason tags (Issue #6, Spec §20.4)
# ---------------------------------------------------------------------------
class ConfirmationReasonTag(str, Enum):
    """Reasons attached to a :class:`TradeConfirmationLevel` decision
    (Spec §20.4).

    Each fired tag contributes one signal toward the T-tier mapping
    (more signals -> stronger tier). The concrete mapping lives in
    :class:`app.confirmation.real_trade.RealTradeConfirmation`.
    """

    CVD_PRICE_AGREEMENT = "cvd_price_agreement"
    BREAKOUT_HELD = "breakout_held"
    LARGE_TRADE_FOLLOW_THROUGH = "large_trade_follow_through"
    TRADE_EFFICIENCY_HIGH = "trade_efficiency_high"
    VOLUME_UP_PRICE_MOVE = "volume_up_price_move"
    DATA_DEGRADED = "data_degraded"
    REGIME_BLOCKED = "regime_blocked"
    INSUFFICIENT_HISTORY = "insufficient_history"


# ---------------------------------------------------------------------------
# Phase 6 - Manipulation Detector reason tags (Issue #6, Spec §21.2)
# ---------------------------------------------------------------------------
class ManipulationReasonTag(str, Enum):
    """Reasons attached to a :class:`ManipulationLevel` decision
    (Spec §21.2).

    Each fired tag contributes one signal toward the M-tier mapping;
    the more tags fire the higher the manipulation level. Phase 6 hard
    rules (Issue #6):

      - M2 forbids ATTACK / RIGHT_TAIL_AMPLIFY (Risk Engine enforces
        this in :meth:`RiskEngine.evaluate`).
      - M3 forbids any new opening (Risk Engine enforces this).
    """

    CVD_UP_PRICE_FLAT = "cvd_up_price_flat"
    VOLUME_UP_PRICE_NO_MOVE = "volume_up_price_no_move"
    OI_UP_PRICE_FLAT = "oi_up_price_flat"
    FUNDING_HOT_PRICE_WEAK = "funding_hot_price_weak"
    UPPER_WICK_GROWTH = "upper_wick_growth"
    BUY_PRESSURE_NO_PUSH = "buy_pressure_no_push"
    BOOK_WALL_FLICKER = "book_wall_flicker"
    NARRATIVE_AFTER_PUMP = "narrative_after_pump"
    DATA_DEGRADED = "data_degraded"
    REGIME_BLOCKED = "regime_blocked"
    INSUFFICIENT_HISTORY = "insufficient_history"


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
# Phase 7 - Circuit Breaker state (Issue #7, Spec §27.2)
# ---------------------------------------------------------------------------
class CircuitBreakerState(str, Enum):
    """Status of a Phase 7 Risk Engine circuit breaker.

    Phase 7 ships two breakers:

      - ``DailyLossCircuitBreaker`` (daily realised-loss budget,
        Spec §27.2 hard rule "单日回撤达到阈值").
      - ``ConsecutiveLossCircuitBreaker`` (5 consecutive losing
        trades, Spec §27.2 hard rule "连续亏损达到阈值").

    A breaker is ``CLOSED`` while business as usual; it opens once its
    threshold is crossed. ``COOL_DOWN`` is reserved for the operator
    to inspect before manually re-arming. In Phase 7 we ship the
    semantics; Phase 9 (Reconciliation) and Phase 10 (Telegram) will
    surface the breaker state to the operator interface.
    """

    CLOSED = "closed"
    OPEN_DAILY_LOSS = "open_daily_loss"
    OPEN_CONSECUTIVE_LOSS = "open_consecutive_loss"
    COOL_DOWN = "cool_down"

    @property
    def is_open(self) -> bool:
        return self is not CircuitBreakerState.CLOSED


# ---------------------------------------------------------------------------
# Phase 7 - State-machine transition triggers (Issue #7, Spec §26)
# ---------------------------------------------------------------------------
class TradeStateTrigger(str, Enum):
    """Why a TradeState transition was attempted.

    Recorded on every ``STATE_TRANSITION`` event payload so Reflection
    (Issue #10) and Replay can rebuild the trade-state ladder from
    events.db alone. Phase 7 keeps the vocabulary deliberately small;
    Issue #9 / #10 may extend it (e.g. ``RECONCILIATION_FORCED``).
    """

    SIGNAL = "signal"
    PROMOTE = "promote"
    DOWNGRADE = "downgrade"
    TIMEOUT = "timeout"
    LOCK_PROFIT = "lock_profit"
    DISTRIBUTION_ALERT = "distribution_alert"
    FORCED_EXIT = "forced_exit"
    KILL_SWITCH = "kill_switch"
    RESET = "reset"


# ---------------------------------------------------------------------------
# Phase 7 - Typed Risk Engine reject reasons (Issue #7, Spec §27)
# ---------------------------------------------------------------------------
class RiskRejectReason(str, Enum):
    """Typed reason tags emitted by the Phase 7 Risk Engine.

    Issue #7 hard rule: "所有拒绝必须有明确 reason_tags". Phase 7
    therefore promotes the Phase 1 / Phase 6 free-form strings to a
    typed enum so Reflection (Issue #10) can group / count rejects
    without parsing strings. The Phase 1 / Phase 6 string reasons are
    preserved as the enum *value* strings so existing tests and the
    audit trail stay byte-for-byte compatible.
    """

    # Phase 1 hard rejections.
    LIVE_TRADING_DISABLED = "live_trading_disabled"
    RIGHT_TAIL_DISABLED = "right_tail_disabled"
    STOP_UNCONFIRMED = "stop_unconfirmed"
    UNKNOWN_POSITION = "unknown_position"
    TRADING_MODE_INCONSISTENT = "trading_mode_inconsistent"
    # Phase 6 hard rejections.
    MANIPULATION_M3 = "manipulation_m3"
    MANIPULATION_M2_ATTACK = "manipulation_m2_attack"
    TRADE_CONFIRMATION_TOO_LOW_FOR_ATTACK = "trade_confirmation_too_low_for_attack"
    # Phase 7 No-Trade Gate.
    REGIME_BLOCK_ALL = "regime_block_all"
    REGIME_OBSERVE_ONLY_FOR_NEW_OPEN = "regime_observe_only_for_new_open"
    REGIME_SCOUT_ONLY_FOR_ATTACK = "regime_scout_only_for_attack"
    REGIME_SCOUT_ONLY_FOR_RIGHT_TAIL = "regime_scout_only_for_right_tail"
    UNIVERSE_INELIGIBLE = "universe_ineligible"
    LIQUIDITY_REJECTED = "liquidity_rejected"
    NO_EXIT_CHANNEL = "no_exit_channel"
    DATA_DEGRADED = "data_degraded"
    EXCHANGE_DISCONNECTED = "exchange_disconnected"
    DAILY_LOSS_BREAKER_OPEN = "daily_loss_breaker_open"
    CONSECUTIVE_LOSS_BREAKER_OPEN = "consecutive_loss_breaker_open"
    LIQUIDITY_THROUGHPUT_INSUFFICIENT = "liquidity_throughput_insufficient"
    ACCOUNT_TIER_HALT = "account_tier_halt"
    ACCOUNT_TIER_NO_NEW_OPEN = "account_tier_no_new_open"
    ACCOUNT_TIER_NO_RIGHT_TAIL = "account_tier_no_right_tail"
    ACCOUNT_TIER_PAPER_ONLY = "account_tier_paper_only"
    RIGHT_TAIL_FROM_PRINCIPAL_FORBIDDEN = "right_tail_from_principal_forbidden"
    LOSING_POSITION_CANNOT_AMPLIFY = "losing_position_cannot_amplify"


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
