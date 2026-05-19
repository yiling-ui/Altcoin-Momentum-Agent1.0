"""Phase 7 No-Trade Gate (Issue #7, Spec §27.2).

The No-Trade Gate is the *composition* of every defensive condition
listed in Spec §27.2. It is a pure function: it takes a
:class:`NoTradeGateInput` describing the current state of the system
and produces a :class:`NoTradeGateDecision` listing every fired
reason in :class:`RiskRejectReason` form.

The gate does NOT trade. It does NOT call any exchange. It does NOT
amplify a position. It does NOT bypass the Risk Engine - it IS the
core of the Risk Engine's rejection logic. The Risk Engine
(:mod:`app.risk.engine`) wires the Phase 1 hard flags + Phase 6 rules
+ this gate + the Account Tier policy + the Circuit Breakers
together; this module owns the *Phase 5 / Phase 6 input fan-in* so
the Risk Engine surface stays narrow.

Spec §27.2 conditions implemented here:

  - SYSTEMIC_RISK -> BLOCK_ALL.
  - BTC/ETH 快速下跌或高波动 -> RegimeSnapshot.risk_permission already
    encodes this (BLOCK_ALL / OBSERVE_ONLY / ALLOW_SCOUT), Phase 7
    just consumes it.
  - MarketDataBuffer.is_degraded(symbol) -> DATA_DEGRADED reject.
  - UniverseDecision.eligible -> reject when False.
  - LiquidityDecision -> reject when not passed.
  - LiquidityFilter.can_exit_position -> reject when not feasible.
  - **Liquidity throughput conservative discount (Phase 7).** Phase 5
    documents that ``can_exit_position`` returns an UPPER BOUND on
    realisable throughput - ``volume_5m / 300s`` assumes the next 5
    minutes will print at the same pace as the previous 5, that our
    outflow does not crowd its own exit price, and that ATR / OI do
    not expand into the exit window. None of that holds in a thinning
    or panicking tape. The Risk Engine therefore re-checks every new
    opening against the *discounted* exit time
    ``estimated_exit_seconds / throughput_safety_factor`` and
    refuses the request with
    :attr:`RiskRejectReason.LIQUIDITY_THROUGHPUT_INSUFFICIENT` when
    the discounted estimate exceeds ``max_exit_seconds``. The default
    ``throughput_safety_factor`` is ``0.5`` (the Phase 5 throughput
    is halved before being trusted for sizing). Issue #7 hard rule:
    "Phase 7 must apply a conservative discount on top of
    can_exit_position before allowing ATTACK / RIGHT_TAIL_AMPLIFY."
    DATA_DEGRADED still fires first regardless of any feasible
    plan; the discount is a defence-in-depth on top of, not a
    replacement for, the Phase 5 / data-quality gates.
  - ManipulationLevel.M3 -> reject every new opening.
  - ManipulationLevel.M2 + attack_intent -> reject ATTACK / RTA.
  - TradeConfirmationLevel.T0/T1 + attack_intent -> reject attack.
  - stop_unconfirmed -> reject.
  - unknown_position -> reject.
  - Daily-loss / consecutive-loss breaker open -> reject.
  - Exchange link disconnected -> reject.

Phase 7 hard rule: every reject path carries a typed
:class:`RiskRejectReason`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.enums import (
    CircuitBreakerState,
    ExchangeConnectionState,
    ManipulationLevel,
    RiskPermission,
    RiskRejectReason,
    TradeConfirmationLevel,
)
from app.liquidity.models import ExitPlan, LiquidityDecision
from app.regime.models import RegimeSnapshot
from app.universe.models import UniverseDecision


@dataclass(frozen=True)
class NoTradeGateInput:
    """All inputs the No-Trade Gate consults.

    Phase 7 keeps every input optional so the gate degrades gracefully
    when a particular Phase upstream did not run (e.g. paper-mode boot
    drill that hasn't built a UniverseDecision yet). Missing inputs
    are treated as conservatively as possible: a missing regime
    snapshot is "unknown -> ALLOW_SCOUT" via the Phase 5 conservative
    default, a missing universe / liquidity decision is "no opinion".
    The gate never *invents* an approval - if you want to be sure a
    decision was checked, you must pass it in.
    """

    symbol: str | None = None
    attack_intent: bool = False
    right_tail_amplify_intent: bool = False
    is_new_open: bool = True
    stop_unconfirmed: bool = False
    unknown_position: bool = False
    is_data_degraded: bool = False
    exchange_connection_state: ExchangeConnectionState | None = None
    regime_snapshot: RegimeSnapshot | None = None
    universe_decision: UniverseDecision | None = None
    liquidity_decision: LiquidityDecision | None = None
    exit_plan: ExitPlan | None = None
    manipulation_level: ManipulationLevel | None = None
    trade_confirmation_level: TradeConfirmationLevel | None = None
    daily_loss_breaker_state: CircuitBreakerState = CircuitBreakerState.CLOSED
    consecutive_loss_breaker_state: CircuitBreakerState = CircuitBreakerState.CLOSED
    # Phase 7 conservative throughput discount (Issue #7).
    # ``can_exit_position`` returns an UPPER BOUND on realisable
    # throughput; the Risk Engine refuses to trust it directly. The
    # safety factor is multiplicative on throughput - equivalently
    # divisive on ``estimated_exit_seconds`` - so a value of 0.5
    # doubles the exit-time estimate before comparing it to
    # ``max_exit_seconds``. Default 0.5 matches the Phase 7 risk
    # config; tests can override.
    throughput_safety_factor: float = 0.5
    # Maximum acceptable exit time in seconds for the discounted
    # re-check. When ``None`` the Risk Engine derives it from the
    # original :class:`ExitPlan` / :class:`LiquidityDecision`; when
    # both are absent the discount re-check is skipped (the regular
    # NO_EXIT_CHANNEL gate above is still in effect).
    max_exit_seconds: float | None = None


@dataclass(frozen=True)
class NoTradeGateDecision:
    """Output of the No-Trade Gate."""

    allowed: bool
    reasons: tuple[RiskRejectReason, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)


def evaluate_no_trade_gate(
    request: NoTradeGateInput,
) -> NoTradeGateDecision:
    """Walk every Spec §27.2 condition in stable order and return the
    composite decision.

    Phase 7 keeps the order deliberately deterministic so Reflection
    (Issue #10) can group rejects by *first* reason. The "first" tag
    in the returned list is therefore the most severe / earliest
    reason.
    """
    reasons: list[RiskRejectReason] = []
    notes: list[str] = []
    attack = bool(request.attack_intent or request.right_tail_amplify_intent)

    # ------------------------------------------------------------------
    # 1. Exchange link health (Spec §27.2 + §31).
    # ------------------------------------------------------------------
    if (
        request.exchange_connection_state is not None
        and request.exchange_connection_state
        is not ExchangeConnectionState.CONNECTED
        and request.is_new_open
    ):
        reasons.append(RiskRejectReason.EXCHANGE_DISCONNECTED)
        notes.append(
            f"exchange={request.exchange_connection_state.value}"
        )

    # ------------------------------------------------------------------
    # 2. Stop / position state (Spec §4.2 + §27.2 + §31.3).
    # ------------------------------------------------------------------
    if request.stop_unconfirmed and request.is_new_open:
        reasons.append(RiskRejectReason.STOP_UNCONFIRMED)
        notes.append("stop_unconfirmed=true")
    if request.unknown_position and request.is_new_open:
        reasons.append(RiskRejectReason.UNKNOWN_POSITION)
        notes.append("unknown_position=true")

    # ------------------------------------------------------------------
    # 3. Data degraded (Spec §14.2 + §27.2).
    # ------------------------------------------------------------------
    if request.is_data_degraded and request.is_new_open:
        reasons.append(RiskRejectReason.DATA_DEGRADED)
        notes.append("market_data_buffer reports degraded view")

    # ------------------------------------------------------------------
    # 4. Regime gate (Spec §15.3 + §27.2).
    # ------------------------------------------------------------------
    if request.regime_snapshot is not None:
        perm = request.regime_snapshot.risk_permission
        if perm is RiskPermission.BLOCK_ALL and request.is_new_open:
            reasons.append(RiskRejectReason.REGIME_BLOCK_ALL)
            notes.append(
                f"regime={request.regime_snapshot.market_regime.value}"
                f" risk_permission=BLOCK_ALL"
            )
        elif perm is RiskPermission.OBSERVE_ONLY and request.is_new_open:
            reasons.append(RiskRejectReason.REGIME_OBSERVE_ONLY_FOR_NEW_OPEN)
            notes.append(
                f"regime={request.regime_snapshot.market_regime.value}"
                f" risk_permission=OBSERVE_ONLY"
            )
        elif perm is RiskPermission.ALLOW_SCOUT and attack:
            # Issue #7 semantic lock #5: ALLOW_SCOUT does NOT authorise
            # attack-class transitions. Even if every other gate is
            # green, an attack candidate must wait for ALLOW_ATTACK.
            reasons.append(RiskRejectReason.REGIME_SCOUT_ONLY_FOR_ATTACK)
            notes.append(
                f"regime={request.regime_snapshot.market_regime.value}"
                f" risk_permission=ALLOW_SCOUT"
            )
        # ALLOW_ATTACK -> permitted (still subject to every other gate).

    # ------------------------------------------------------------------
    # 5. Universe Filter (Spec §16 + §27.2).
    # ------------------------------------------------------------------
    if (
        request.universe_decision is not None
        and not request.universe_decision.eligible
        and request.is_new_open
    ):
        reasons.append(RiskRejectReason.UNIVERSE_INELIGIBLE)
        notes.append(
            "universe_reject="
            + ",".join(
                r.value for r in request.universe_decision.reject_reasons
            )
        )

    # ------------------------------------------------------------------
    # 6. Liquidity Filter (Spec §19.1 + §27.2).
    # ------------------------------------------------------------------
    if (
        request.liquidity_decision is not None
        and not request.liquidity_decision.passed
        and request.is_new_open
    ):
        reasons.append(RiskRejectReason.LIQUIDITY_REJECTED)
        notes.append(
            "liquidity_reject="
            + ",".join(
                r.value for r in request.liquidity_decision.reject_reasons
            )
        )

    # ------------------------------------------------------------------
    # 7. can_exit_position (Spec §19.2 + §27.2).
    # ------------------------------------------------------------------
    if (
        request.exit_plan is not None
        and not request.exit_plan.feasible
        and request.is_new_open
    ):
        reasons.append(RiskRejectReason.NO_EXIT_CHANNEL)
        notes.append(
            "exit_plan_reject="
            + ",".join(r.value for r in request.exit_plan.reject_reasons)
        )

    # ------------------------------------------------------------------
    # 7b. Phase 7 conservative throughput discount on top of Phase 5's
    # can_exit_position. Issue #7 hard rule: the Risk Engine MUST
    # treat the Phase 5 throughput estimate as an UPPER BOUND and
    # refuse new openings whose discounted exit time exceeds
    # ``max_exit_seconds``. Defence-in-depth on top of the raw plan
    # check above; DATA_DEGRADED / NO_EXIT_CHANNEL / LIQUIDITY_REJECTED
    # already fired first if applicable.
    # ------------------------------------------------------------------
    if (
        request.exit_plan is not None
        and request.is_new_open
        and request.throughput_safety_factor > 0.0
        and request.throughput_safety_factor < 1.0
        and request.exit_plan.estimated_exit_seconds is not None
    ):
        max_secs = _resolve_max_exit_seconds(request)
        if max_secs is not None:
            discounted = (
                request.exit_plan.estimated_exit_seconds
                / request.throughput_safety_factor
            )
            if discounted > max_secs:
                reasons.append(
                    RiskRejectReason.LIQUIDITY_THROUGHPUT_INSUFFICIENT
                )
                notes.append(
                    f"discounted_exit_seconds={discounted:.2f}"
                    f" > max_exit_seconds={max_secs:.2f}"
                    f" (raw={request.exit_plan.estimated_exit_seconds:.2f},"
                    f" safety_factor={request.throughput_safety_factor:.2f})"
                )

    # ------------------------------------------------------------------
    # 8. Phase 6 manipulation hard rules (Spec §21.3).
    # ------------------------------------------------------------------
    if (
        request.manipulation_level is ManipulationLevel.M3
        and request.is_new_open
    ):
        reasons.append(RiskRejectReason.MANIPULATION_M3)
        notes.append("manipulation_level=M3")
    elif (
        request.manipulation_level is ManipulationLevel.M2
        and attack
    ):
        reasons.append(RiskRejectReason.MANIPULATION_M2_ATTACK)
        notes.append("manipulation_level=M2 attack_intent=true")

    # ------------------------------------------------------------------
    # 9. Phase 6 confirmation hard rule (Spec §20).
    # ------------------------------------------------------------------
    if attack and request.trade_confirmation_level in (
        TradeConfirmationLevel.T0,
        TradeConfirmationLevel.T1,
    ):
        reasons.append(RiskRejectReason.TRADE_CONFIRMATION_TOO_LOW_FOR_ATTACK)
        notes.append(
            f"trade_confirmation_level={request.trade_confirmation_level.value}"
        )

    # ------------------------------------------------------------------
    # 10. Circuit breakers (Spec §27.2).
    # ------------------------------------------------------------------
    if request.daily_loss_breaker_state.is_open and request.is_new_open:
        reasons.append(RiskRejectReason.DAILY_LOSS_BREAKER_OPEN)
        notes.append(
            f"daily_loss_breaker={request.daily_loss_breaker_state.value}"
        )
    if (
        request.consecutive_loss_breaker_state.is_open
        and request.is_new_open
    ):
        reasons.append(RiskRejectReason.CONSECUTIVE_LOSS_BREAKER_OPEN)
        notes.append(
            f"consecutive_loss_breaker={request.consecutive_loss_breaker_state.value}"
        )

    return NoTradeGateDecision(
        allowed=not reasons,
        reasons=tuple(reasons),
        notes=tuple(notes),
    )


def _resolve_max_exit_seconds(request: NoTradeGateInput) -> float | None:
    """Resolve the ceiling for the discounted exit-time check.

    Phase 7 prefers the explicit ``max_exit_seconds`` on the request;
    when it is missing we fall back to the Phase 5 LiquidityDecision's
    ``estimated_exit_seconds`` (it was already <=
    ``LiquidityConfig.max_exit_seconds`` for the original plan to be
    feasible, so using it as the ceiling for the discounted re-check
    is conservative). If neither is available the discount re-check
    is skipped - the regular NO_EXIT_CHANNEL gate is still in effect.
    """
    if request.max_exit_seconds is not None:
        return request.max_exit_seconds
    if (
        request.liquidity_decision is not None
        and request.liquidity_decision.estimated_exit_seconds is not None
    ):
        return request.liquidity_decision.estimated_exit_seconds
    return None
