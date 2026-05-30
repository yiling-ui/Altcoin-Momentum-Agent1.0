"""Live Risk Engine (PR112 - Live Capital / Risk / Funding-Aware PnL v0).

Two deterministic, IO-free decision surfaces layered on top of the
PR110 capital profile ladder + right-tail leverage gate and the PR112
:class:`app.live.capital_state.LiveCapitalState`:

  1. :func:`evaluate_capital_profile_state` - is the real account
     consistent with the *active* capital profile? Detects profile /
     equity mismatch, caps usable capital at the profile's hard cap,
     and raises the conservative flags (daily/total loss, max positions,
     low available balance, risk halt, kill-switch-required). It NEVER
     auto-escalates / auto-downgrades the profile - that is always an
     explicit operator action (PR110 contract).

  2. :func:`evaluate_live_order_risk` - a deterministic *dry* live order
     pre-check. Returns a :class:`LiveRiskDecision`. In PR112 it never
     submits an order: ``real_order_allowed`` is hard-locked ``False``.
     It exists so PR113's real execution gateway has a vetted, audited
     risk decision to consume.

L1_10U_PROBE enforcement (the current small-capital posture):
  - usable account capital is capped at ``max_account_capital_usdt`` (10U);
  - if the account equity exceeds the profile band, a
    ``PROFILE_MISMATCH_EQUITY_ABOVE_RANGE`` is flagged and the operator
    must reselect a profile (no auto-upgrade);
  - if equity falls below a safety floor, ``risk_halt`` is raised.

Nothing here decides direction / size / leverage from AI / Telegram /
blind / replay / future-label input. Leverage permission still comes
only from the PR110 deterministic right-tail leverage gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.clock import now_ms
from app.core.enums import LiveRuntimeMode, OrderSource
from app.live.capital_profile import (
    AUTO_ESCALATION_ALLOWED,
    CapitalProfile,
    CapitalProfileId,
    ProfileMismatch,
    detect_profile_mismatch,
    get_profile,
    suggest_profile_for_equity,
)
from app.live.capital_state import LiveCapitalState
from app.live.leverage_gate import LeverageDecision

# Event types (audit) the PR112 risk engine stamps onto decisions.
LIVE_RISK_AUDIT_APPROVED = "LIVE_RISK_APPROVED_DRY"
LIVE_RISK_AUDIT_REJECTED = "LIVE_RISK_REJECTED_DRY"
LIVE_CAPITAL_PROFILE_AUDIT = "LIVE_CAPITAL_PROFILE_STATE_EVALUATED"


class CapitalProfileStatus:
    """Closed taxonomy of capital-profile / account-state findings."""

    PROFILE_OK = "PROFILE_OK"
    PROFILE_MISMATCH_EQUITY_ABOVE_RANGE = "PROFILE_MISMATCH_EQUITY_ABOVE_RANGE"
    PROFILE_MISMATCH_EQUITY_BELOW_RANGE = "PROFILE_MISMATCH_EQUITY_BELOW_RANGE"
    ACCOUNT_CAPITAL_EXCEEDS_PROFILE_CAP = "ACCOUNT_CAPITAL_EXCEEDS_PROFILE_CAP"
    DAILY_LOSS_LIMIT_REACHED = "DAILY_LOSS_LIMIT_REACHED"
    TOTAL_LOSS_LIMIT_REACHED = "TOTAL_LOSS_LIMIT_REACHED"
    MAX_ACTIVE_POSITIONS_REACHED = "MAX_ACTIVE_POSITIONS_REACHED"
    AVAILABLE_BALANCE_TOO_LOW = "AVAILABLE_BALANCE_TOO_LOW"
    RISK_HALT_ACTIVE = "RISK_HALT_ACTIVE"
    KILL_SWITCH_REQUIRED = "KILL_SWITCH_REQUIRED"


class LiveRiskRejectReason:
    """Closed taxonomy of live order risk-pre-check reject reasons (PR112)."""

    RUNTIME_MODE_SHADOW_NO_REAL_ORDER = "runtime_mode_shadow_no_real_order"
    SOURCE_NOT_LIVE = "source_not_live"
    ACCOUNT_SNAPSHOT_MISSING = "account_snapshot_missing"
    CAPITAL_PROFILE_INVALID = "capital_profile_invalid"
    PROFILE_REAL_ORDERS_NOT_ALLOWED = "profile_real_orders_not_allowed"
    NOTIONAL_NON_POSITIVE = "planned_notional_non_positive"
    NOTIONAL_EXCEEDS_PROFILE_MAX = "planned_notional_exceeds_profile_max"
    ACCOUNT_CAPITAL_EXCEEDS_PROFILE_CAP = "account_capital_exceeds_profile_cap"
    LEVERAGE_NON_POSITIVE = "planned_leverage_non_positive"
    LEVERAGE_EXCEEDS_PROFILE_MAX = "planned_leverage_exceeds_profile_max"
    INSUFFICIENT_AVAILABLE_BALANCE = "insufficient_available_balance"
    MAX_ACTIVE_POSITIONS_REACHED = "max_active_positions_reached"
    DAILY_LOSS_LIMIT_REACHED = "daily_loss_limit_reached"
    TOTAL_LOSS_LIMIT_REACHED = "total_loss_limit_reached"
    RISK_HALT_ACTIVE = "risk_halt_active"
    NO_STOP_PLAN = "no_stop_plan"
    NO_EXIT_PLAN = "no_exit_plan"
    RIGHT_TAIL_LEVERAGE_GATE_REJECTED = "right_tail_leverage_gate_rejected"
    SYMBOL_NOT_TRADABLE = "symbol_not_tradable"


# ---------------------------------------------------------------------------
# 1. Capital profile enforcement
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CapitalProfileState:
    """Result of comparing the real account against the active profile."""

    capital_profile_id: CapitalProfileId
    account_equity_usdt: float
    available_balance_usdt: float
    profile_max_account_capital_usdt: float
    usable_capital_usdt: float
    open_position_count: int
    profile_status: str
    flags: tuple[str, ...]
    risk_halt_active: bool
    kill_switch_required: bool
    requires_operator_action: bool
    suggested_profile_id: CapitalProfileId
    mismatch: ProfileMismatch
    auto_escalation_allowed: bool = AUTO_ESCALATION_ALLOWED

    @property
    def is_ok(self) -> bool:
        return self.profile_status == CapitalProfileStatus.PROFILE_OK and not self.flags

    def to_dict(self) -> dict[str, Any]:
        return {
            "capital_profile_id": self.capital_profile_id.value,
            "account_equity_usdt": self.account_equity_usdt,
            "available_balance_usdt": self.available_balance_usdt,
            "profile_max_account_capital_usdt": self.profile_max_account_capital_usdt,
            "usable_capital_usdt": self.usable_capital_usdt,
            "open_position_count": self.open_position_count,
            "profile_status": self.profile_status,
            "flags": list(self.flags),
            "risk_halt_active": self.risk_halt_active,
            "kill_switch_required": self.kill_switch_required,
            "requires_operator_action": self.requires_operator_action,
            "suggested_profile_id": self.suggested_profile_id.value,
            "mismatch": self.mismatch.to_dict(),
            "auto_escalation_allowed": self.auto_escalation_allowed,
            # PR112 safety markers.
            "real_orders_allowed": False,
            "exchange_live_orders": False,
        }


def _resolve_profile(profile: CapitalProfile | CapitalProfileId | str) -> CapitalProfile:
    if isinstance(profile, CapitalProfile):
        return profile
    return get_profile(profile)


def evaluate_capital_profile_state(
    capital_state: LiveCapitalState,
    profile: CapitalProfile | CapitalProfileId | str,
    *,
    daily_loss_usdt: float = 0.0,
    total_loss_usdt: float = 0.0,
    safety_equity_floor_usdt: float | None = None,
    kill_switch_armed: bool = False,
) -> CapitalProfileState:
    """Enforce the active capital profile against the real account state.

    Conservative by construction: it caps usable capital at the profile
    cap, detects (never fixes) a profile / equity mismatch, and raises
    the loss / position / halt flags. ``daily_loss_usdt`` /
    ``total_loss_usdt`` are positive magnitudes of realised loss the
    caller has measured for the window.
    """

    prof = _resolve_profile(profile)
    equity = float(capital_state.account_equity_usdt)
    available = float(capital_state.available_balance_usdt)

    # Mismatch detection is run against the truthful equity; PR110 helper
    # never auto-applies a change.
    mismatch = detect_profile_mismatch(prof.profile_id, equity)
    suggested = mismatch.suggested_profile_id

    flags: list[str] = []
    profile_status = CapitalProfileStatus.PROFILE_OK

    if mismatch.mismatch:
        if mismatch.direction == "escalate":
            profile_status = CapitalProfileStatus.PROFILE_MISMATCH_EQUITY_ABOVE_RANGE
        elif mismatch.direction == "deescalate":
            profile_status = CapitalProfileStatus.PROFILE_MISMATCH_EQUITY_BELOW_RANGE
        flags.append(profile_status)

    # Usable capital is hard-capped at the profile's account-capital cap,
    # so a large real balance can never be used blindly under a small
    # profile (L1_10U_PROBE caps usable capital at 10U).
    cap = float(prof.max_account_capital_usdt)
    usable_capital = min(equity, cap) if cap > 0 else 0.0
    if cap > 0 and equity > cap:
        flags.append(CapitalProfileStatus.ACCOUNT_CAPITAL_EXCEEDS_PROFILE_CAP)

    # Loss limits (positive magnitudes).
    daily_loss = abs(float(daily_loss_usdt))
    total_loss = abs(float(total_loss_usdt))
    if prof.max_daily_loss_usdt > 0 and daily_loss >= prof.max_daily_loss_usdt:
        flags.append(CapitalProfileStatus.DAILY_LOSS_LIMIT_REACHED)
    total_loss_reached = (
        prof.max_total_loss_usdt > 0 and total_loss >= prof.max_total_loss_usdt
    )
    if total_loss_reached:
        flags.append(CapitalProfileStatus.TOTAL_LOSS_LIMIT_REACHED)

    # Active positions.
    if (
        prof.max_active_positions >= 0
        and capital_state.open_position_count >= prof.max_active_positions
        and prof.max_active_positions > 0
    ):
        flags.append(CapitalProfileStatus.MAX_ACTIVE_POSITIONS_REACHED)

    # Low available balance: below the profile's de-facto minimum to act.
    # Use the profile min equity band as the floor when no explicit floor
    # is supplied (a funded profile with available below its min band can
    # no longer open a sized position).
    if prof.real_orders_allowed and available <= 0:
        flags.append(CapitalProfileStatus.AVAILABLE_BALANCE_TOO_LOW)

    # Safety equity floor -> risk halt.
    risk_halt = False
    if safety_equity_floor_usdt is not None and equity < float(
        safety_equity_floor_usdt
    ):
        risk_halt = True
        flags.append(CapitalProfileStatus.RISK_HALT_ACTIVE)

    # Kill switch is required when a total-loss limit is breached or a
    # risk halt has fired and the operator has not yet armed it.
    kill_switch_required = (total_loss_reached or risk_halt) and not kill_switch_armed
    if kill_switch_required:
        flags.append(CapitalProfileStatus.KILL_SWITCH_REQUIRED)

    requires_operator_action = bool(mismatch.requires_operator_action) or bool(flags)

    # De-duplicate while preserving order.
    seen: set[str] = set()
    ordered_flags = tuple(f for f in flags if not (f in seen or seen.add(f)))

    return CapitalProfileState(
        capital_profile_id=prof.profile_id,
        account_equity_usdt=equity,
        available_balance_usdt=available,
        profile_max_account_capital_usdt=cap,
        usable_capital_usdt=usable_capital,
        open_position_count=capital_state.open_position_count,
        profile_status=profile_status,
        flags=ordered_flags,
        risk_halt_active=risk_halt,
        kill_switch_required=kill_switch_required,
        requires_operator_action=requires_operator_action,
        suggested_profile_id=suggested,
        mismatch=mismatch,
    )


# ---------------------------------------------------------------------------
# 2. Live order intent + risk decision
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LiveOrderIntent:
    """A planned live order (PR112 risk pre-check input).

    This is the *risk-engine* intent, distinct from PR110's
    :class:`app.live.path_isolation.LiveOrderIntent` (which is the
    isolation-guard provenance object). It carries the planned trade
    geometry so the dry risk pre-check can vet it. PR112 NEVER submits
    it; PR113's execution gateway will consume the resulting decision.
    """

    symbol: str
    side: str
    planned_entry_price: float
    planned_notional_usdt: float
    planned_leverage: float
    planned_stop_price: float | None = None
    planned_take_profit_price: float | None = None
    exit_plan_present: bool = False
    stop_plan_present: bool = False
    candidate_stage: str = "unknown"
    opportunity_score: float = 0.0
    runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_SHADOW
    source: OrderSource = OrderSource.LIVE

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "planned_entry_price": self.planned_entry_price,
            "planned_notional_usdt": self.planned_notional_usdt,
            "planned_leverage": self.planned_leverage,
            "planned_stop_price": self.planned_stop_price,
            "planned_take_profit_price": self.planned_take_profit_price,
            "exit_plan_present": self.exit_plan_present,
            "stop_plan_present": self.stop_plan_present,
            "candidate_stage": self.candidate_stage,
            "opportunity_score": self.opportunity_score,
            "runtime_mode": (
                self.runtime_mode.value
                if isinstance(self.runtime_mode, LiveRuntimeMode)
                else self.runtime_mode
            ),
            "source": (
                self.source.value
                if isinstance(self.source, OrderSource)
                else self.source
            ),
        }


@dataclass(frozen=True)
class LiveRiskDecision:
    """Output of the deterministic live order risk pre-check (PR112)."""

    approved: bool
    reject_reason: str | None
    reject_reasons: tuple[str, ...]
    runtime_mode: LiveRuntimeMode
    capital_profile_id: CapitalProfileId
    planned_notional_usdt: float
    max_allowed_notional_usdt: float
    planned_leverage: float
    max_allowed_leverage: float
    account_equity_usdt: float
    available_balance_usdt: float
    risk_halt_active: bool
    evidence_refs: tuple[str, ...]
    audit_event_type: str
    # PR112 hard marker: no real order is ever submitted.
    real_order_allowed: bool = False
    decided_at: int = field(default_factory=now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "reject_reason": self.reject_reason,
            "reject_reasons": list(self.reject_reasons),
            "runtime_mode": self.runtime_mode.value,
            "capital_profile_id": self.capital_profile_id.value,
            "planned_notional_usdt": self.planned_notional_usdt,
            "max_allowed_notional_usdt": self.max_allowed_notional_usdt,
            "planned_leverage": self.planned_leverage,
            "max_allowed_leverage": self.max_allowed_leverage,
            "account_equity_usdt": self.account_equity_usdt,
            "available_balance_usdt": self.available_balance_usdt,
            "risk_halt_active": self.risk_halt_active,
            "evidence_refs": list(self.evidence_refs),
            "audit_event_type": self.audit_event_type,
            "real_order_allowed": self.real_order_allowed,
            "decided_at": self.decided_at,
            # PR112 safety markers.
            "exchange_live_orders": False,
            "trade_authority": False,
            "ai_trade_authority": False,
        }


def evaluate_live_order_risk(
    intent: LiveOrderIntent,
    capital_state: LiveCapitalState | None,
    capital_profile: CapitalProfile | CapitalProfileId | str,
    leverage_gate: LeverageDecision | None = None,
    runtime_mode: LiveRuntimeMode | None = None,
    *,
    daily_loss_usdt: float = 0.0,
    total_loss_usdt: float = 0.0,
    symbol_tradable: bool | None = None,
    profile_state: CapitalProfileState | None = None,
) -> LiveRiskDecision:
    """Deterministically pre-check a planned live order (PR112, dry only).

    Returns a :class:`LiveRiskDecision`. ``real_order_allowed`` is always
    ``False`` in PR112 - even an ``approved`` decision is advisory until
    PR113's execution gateway consumes it.

    ``runtime_mode`` (the live system's current mode) is authoritative
    for the shadow check; it defaults to ``capital_state.runtime_mode``
    (or the intent's mode) when not supplied.
    """

    reasons: list[str] = []
    evidence: list[str] = []

    # Resolve the effective runtime mode.
    mode = runtime_mode
    if mode is None:
        mode = capital_state.runtime_mode if capital_state else intent.runtime_mode

    # Resolve / validate the capital profile.
    try:
        prof = _resolve_profile(capital_profile)
        profile_id = prof.profile_id
    except (KeyError, ValueError):
        prof = None
        profile_id = CapitalProfileId.L0_SHADOW
        reasons.append(LiveRiskRejectReason.CAPITAL_PROFILE_INVALID)

    planned_notional = float(intent.planned_notional_usdt)
    planned_leverage = float(intent.planned_leverage)
    account_equity = float(capital_state.account_equity_usdt) if capital_state else 0.0
    available = float(capital_state.available_balance_usdt) if capital_state else 0.0

    # --- Hard gates that do not need the profile -------------------------
    if mode is LiveRuntimeMode.LIVE_SHADOW:
        reasons.append(LiveRiskRejectReason.RUNTIME_MODE_SHADOW_NO_REAL_ORDER)
    if intent.source is not OrderSource.LIVE:
        reasons.append(LiveRiskRejectReason.SOURCE_NOT_LIVE)
    if capital_state is None or not capital_state.is_real_account_snapshot:
        reasons.append(LiveRiskRejectReason.ACCOUNT_SNAPSHOT_MISSING)
    if not intent.stop_plan_present or intent.planned_stop_price is None:
        reasons.append(LiveRiskRejectReason.NO_STOP_PLAN)
    if not intent.exit_plan_present:
        reasons.append(LiveRiskRejectReason.NO_EXIT_PLAN)
    if symbol_tradable is False:
        reasons.append(LiveRiskRejectReason.SYMBOL_NOT_TRADABLE)

    # Default ceilings (overridden once profile resolves).
    max_allowed_notional = 0.0
    max_allowed_leverage = 0.0
    risk_halt_active = False

    if prof is not None:
        max_allowed_notional = float(prof.max_position_notional_usdt)
        max_allowed_leverage = float(prof.max_leverage)
        # A right-tail leverage grant may raise the ceiling, but only when
        # the deterministic PR110 gate explicitly allowed it.
        if leverage_gate is not None and leverage_gate.leverage_allowed:
            max_allowed_leverage = max(
                max_allowed_leverage, float(leverage_gate.max_allowed_leverage)
            )

        if not prof.real_orders_allowed:
            reasons.append(LiveRiskRejectReason.PROFILE_REAL_ORDERS_NOT_ALLOWED)

        # Notional gates.
        if planned_notional <= 0:
            reasons.append(LiveRiskRejectReason.NOTIONAL_NON_POSITIVE)
        elif planned_notional > max_allowed_notional:
            reasons.append(LiveRiskRejectReason.NOTIONAL_EXCEEDS_PROFILE_MAX)

        # Account capital cap (usable capital is hard-capped at the profile
        # cap; an oversized real balance never unlocks a bigger order).
        if (
            prof.max_account_capital_usdt > 0
            and account_equity > prof.max_account_capital_usdt
        ):
            reasons.append(
                LiveRiskRejectReason.ACCOUNT_CAPITAL_EXCEEDS_PROFILE_CAP
            )

        # Leverage gates.
        if planned_leverage <= 0:
            reasons.append(LiveRiskRejectReason.LEVERAGE_NON_POSITIVE)
        elif planned_leverage > max_allowed_leverage:
            reasons.append(LiveRiskRejectReason.LEVERAGE_EXCEEDS_PROFILE_MAX)

        # Available balance must cover the required initial margin.
        if planned_leverage > 0 and planned_notional > 0:
            required_margin = planned_notional / planned_leverage
            if required_margin > available:
                reasons.append(
                    LiveRiskRejectReason.INSUFFICIENT_AVAILABLE_BALANCE
                )

        # Active position cap.
        if (
            capital_state is not None
            and prof.max_active_positions > 0
            and capital_state.open_position_count >= prof.max_active_positions
        ):
            reasons.append(LiveRiskRejectReason.MAX_ACTIVE_POSITIONS_REACHED)

        # Loss limits + risk halt: reuse the capital-profile-state result
        # if supplied, else derive it deterministically here.
        ps = profile_state
        if ps is None and capital_state is not None:
            ps = evaluate_capital_profile_state(
                capital_state,
                prof,
                daily_loss_usdt=daily_loss_usdt,
                total_loss_usdt=total_loss_usdt,
            )
        if ps is not None:
            risk_halt_active = ps.risk_halt_active
            if CapitalProfileStatus.DAILY_LOSS_LIMIT_REACHED in ps.flags:
                reasons.append(LiveRiskRejectReason.DAILY_LOSS_LIMIT_REACHED)
            if CapitalProfileStatus.TOTAL_LOSS_LIMIT_REACHED in ps.flags:
                reasons.append(LiveRiskRejectReason.TOTAL_LOSS_LIMIT_REACHED)
            if ps.risk_halt_active:
                reasons.append(LiveRiskRejectReason.RISK_HALT_ACTIVE)

    # Right-tail leverage gate result (if a decision was supplied).
    if leverage_gate is not None and not leverage_gate.leverage_allowed:
        reasons.append(LiveRiskRejectReason.RIGHT_TAIL_LEVERAGE_GATE_REJECTED)
        if leverage_gate.reject_reason:
            evidence.append(f"leverage_gate:{leverage_gate.reject_reason}")

    evidence.extend(
        [
            f"profile:{profile_id.value}",
            f"runtime_mode:{mode.value}",
            f"symbol:{intent.symbol}",
            f"candidate_stage:{intent.candidate_stage}",
            f"opportunity_score:{intent.opportunity_score}",
            f"planned_notional:{planned_notional}",
            f"planned_leverage:{planned_leverage}",
            f"account_equity:{account_equity}",
            f"available_balance:{available}",
        ]
    )

    # De-duplicate reasons preserving order.
    seen: set[str] = set()
    ordered = tuple(r for r in reasons if not (r in seen or seen.add(r)))

    approved = len(ordered) == 0
    return LiveRiskDecision(
        approved=approved,
        reject_reason=(ordered[0] if ordered else None),
        reject_reasons=ordered,
        runtime_mode=mode,
        capital_profile_id=profile_id,
        planned_notional_usdt=planned_notional,
        max_allowed_notional_usdt=max_allowed_notional,
        planned_leverage=planned_leverage,
        max_allowed_leverage=max_allowed_leverage,
        account_equity_usdt=account_equity,
        available_balance_usdt=available,
        risk_halt_active=risk_halt_active,
        evidence_refs=tuple(evidence),
        audit_event_type=(
            LIVE_RISK_AUDIT_APPROVED if approved else LIVE_RISK_AUDIT_REJECTED
        ),
        real_order_allowed=False,
    )


__all__ = [
    "LIVE_RISK_AUDIT_APPROVED",
    "LIVE_RISK_AUDIT_REJECTED",
    "LIVE_CAPITAL_PROFILE_AUDIT",
    "CapitalProfileStatus",
    "LiveRiskRejectReason",
    "CapitalProfileState",
    "LiveOrderIntent",
    "LiveRiskDecision",
    "evaluate_capital_profile_state",
    "evaluate_live_order_risk",
    "suggest_profile_for_equity",
]
