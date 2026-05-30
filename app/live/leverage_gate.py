"""Right-tail Leverage Gate (PR110 - Live Foundation v0).

AMA-RT targets short-horizon right-tail capture. On a high-conviction
right-tail structure (RAVE-like) it is acceptable to relax leverage
*somewhat* - but ONLY when a deterministic evidence gate + the capital
profile + the risk state all permit it. Leverage is NEVER decided by
AI, Telegram, blind-test results, future labels, or a human override.

Core constitution (PR110):
  - 没有浮盈不准疯狗   - no floating profit, no dog-pile boost.
  - 没有退出通道不准重拳 - no exit channel, no heavy fist.
  - 没有结构确认不准幻想 - no structure confirmation, no fantasy.
  - AI 不得决定杠杆      - AI must not decide leverage.

:func:`evaluate_right_tail_leverage_permission` is a pure, deterministic
function. Its only inputs are deterministic evidence + the capital
profile + the runtime mode + the risk state. Any AI / LLM / Telegram /
blind / future-label field in the input is refused with
``AI_INPUT_FORBIDDEN``.

PR110 boundary: this gate produces a *permission decision* only. It
does NOT place an order, change leverage on any exchange, or flip a
Phase 1 safety flag. ``right_tail_live_boost_enabled`` remains False by
default; even a granted decision is advisory until a future live
adapter + Risk Engine consume it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.core.enums import LiveRuntimeMode, MarketRegime
from app.live.capital_profile import CapitalProfile, CapitalProfileId, get_profile

# Field names that must NEVER influence a leverage decision. Their mere
# presence in the evidence mapping is a hard reject (AI_INPUT_FORBIDDEN).
FORBIDDEN_LEVERAGE_INPUT_FIELDS: frozenset[str] = frozenset(
    {
        "ai",
        "ai_opinion",
        "ai_recommendation",
        "ai_decision",
        "ai_confidence",
        "ai_leverage",
        "ai_trade_authority",
        "llm",
        "llm_opinion",
        "llm_recommendation",
        "llm_score",
        "deepseek",
        "deepseek_opinion",
        "deepseek_recommendation",
        "telegram_command",
        "operator_override",
        "manual_leverage_override",
        "blind_result",
        "blind_score",
        "replay_result",
        "future_label",
        "completed_tail_label",
        "mfe",
        "mae",
        "mfe_pct",
        "mae_pct",
    }
)


class RightTailLeverageReason:
    """Closed taxonomy of leverage-gate reject / grant reasons."""

    GRANTED_DETERMINISTIC_EVIDENCE = "granted_deterministic_evidence"
    GRANTED_BASE_NO_BOOST = "granted_base_no_boost"
    AI_INPUT_FORBIDDEN = "ai_input_forbidden"
    NO_EXIT_PLAN = "no_exit_plan"
    NO_STOP_PLAN = "no_stop_plan"
    NO_TAKE_PROFIT_PLAN = "no_take_profit_plan"
    NO_LIQUIDITY_EVIDENCE = "no_liquidity_evidence"
    REGIME_RISK_OFF = "regime_risk_off"
    SYSTEMIC_RISK_ACTIVE = "systemic_risk_active"
    ACCOUNT_DRAWDOWN_WARNING = "account_drawdown_warning"
    RISK_HALT_ACTIVE = "risk_halt_active"
    PROFILE_DISALLOWS_BOOST = "profile_disallows_right_tail_boost"
    NO_FLOATING_PROFIT_FOR_BOOST = "no_floating_profit_for_boost"
    SLIPPAGE_OR_SPREAD_TOO_HIGH = "slippage_or_spread_too_high"
    SYMBOL_EXPOSURE_TOO_HIGH = "symbol_exposure_too_high"
    ACCOUNT_EXPOSURE_TOO_HIGH = "account_exposure_too_high"
    LEVERAGE_EXCEEDS_PROFILE_MAX = "leverage_exceeds_profile_max"
    WEAK_RIGHT_TAIL_STRUCTURE = "weak_right_tail_structure"


# Market regimes that forbid any right-tail boost.
_RISK_OFF_REGIMES = frozenset(
    {MarketRegime.ALT_RISK_OFF, MarketRegime.SYSTEMIC_RISK}
)


@dataclass(frozen=True)
class RightTailLeverageEvidence:
    """Deterministic evidence bundle consumed by the leverage gate.

    Every field is a deterministic measurement or a deterministic state
    flag. The ``extra`` mapping is scanned for forbidden AI fields and
    must be empty of them.
    """

    capital_profile_id: CapitalProfileId
    runtime_mode: LiveRuntimeMode
    market_regime: MarketRegime
    systemic_risk_state: bool
    risk_halt_state: bool
    candidate_stage: str
    opportunity_score: float
    liquidity_score: float | None
    spread_bps: float
    estimated_slippage_bps: float
    volume_expansion_score: float
    volatility_state: str
    current_drawdown: float
    floating_profit_state: float
    exit_plan_present: bool
    stop_plan_present: bool
    take_profit_plan_present: bool
    symbol_exposure: float
    account_exposure: float
    oi_expansion_score: float | None = None
    breakout_structure_score: float | None = None
    requested_boost: bool = True
    requested_leverage: float | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "RightTailLeverageEvidence":
        """Build evidence from a mapping; AI fields are kept in ``extra``.

        Any key not part of the deterministic schema lands in ``extra``
        so the gate's forbidden-field scan can refuse AI-shaped input.
        """
        known = {
            "capital_profile_id",
            "runtime_mode",
            "market_regime",
            "systemic_risk_state",
            "risk_halt_state",
            "candidate_stage",
            "opportunity_score",
            "liquidity_score",
            "spread_bps",
            "estimated_slippage_bps",
            "volume_expansion_score",
            "volatility_state",
            "current_drawdown",
            "floating_profit_state",
            "exit_plan_present",
            "stop_plan_present",
            "take_profit_plan_present",
            "symbol_exposure",
            "account_exposure",
            "oi_expansion_score",
            "breakout_structure_score",
            "requested_boost",
            "requested_leverage",
        }
        extra = {k: v for k, v in data.items() if k not in known}
        profile_id = data.get("capital_profile_id", CapitalProfileId.L1_10U_PROBE)
        if isinstance(profile_id, str) and not isinstance(profile_id, CapitalProfileId):
            profile_id = CapitalProfileId(profile_id)
        regime = data.get("market_regime", MarketRegime.MEME_RISK_ON)
        if isinstance(regime, str) and not isinstance(regime, MarketRegime):
            regime = MarketRegime(regime)
        mode = data.get("runtime_mode", LiveRuntimeMode.LIVE_SHADOW)
        if isinstance(mode, str) and not isinstance(mode, LiveRuntimeMode):
            mode = LiveRuntimeMode(mode)
        return cls(
            capital_profile_id=profile_id,
            runtime_mode=mode,
            market_regime=regime,
            systemic_risk_state=bool(data.get("systemic_risk_state", False)),
            risk_halt_state=bool(data.get("risk_halt_state", False)),
            candidate_stage=str(data.get("candidate_stage", "unknown")),
            opportunity_score=float(data.get("opportunity_score", 0.0)),
            liquidity_score=data.get("liquidity_score"),
            spread_bps=float(data.get("spread_bps", 0.0)),
            estimated_slippage_bps=float(data.get("estimated_slippage_bps", 0.0)),
            volume_expansion_score=float(data.get("volume_expansion_score", 0.0)),
            volatility_state=str(data.get("volatility_state", "normal")),
            current_drawdown=float(data.get("current_drawdown", 0.0)),
            floating_profit_state=float(data.get("floating_profit_state", 0.0)),
            exit_plan_present=bool(data.get("exit_plan_present", False)),
            stop_plan_present=bool(data.get("stop_plan_present", False)),
            take_profit_plan_present=bool(data.get("take_profit_plan_present", False)),
            symbol_exposure=float(data.get("symbol_exposure", 0.0)),
            account_exposure=float(data.get("account_exposure", 0.0)),
            oi_expansion_score=data.get("oi_expansion_score"),
            breakout_structure_score=data.get("breakout_structure_score"),
            requested_boost=bool(data.get("requested_boost", True)),
            requested_leverage=data.get("requested_leverage"),
            extra=extra,
        )


@dataclass(frozen=True)
class LeverageDecision:
    """Output of the deterministic right-tail leverage gate."""

    leverage_allowed: bool
    leverage_ratio: float
    max_allowed_leverage: float
    reject_reason: str | None
    reject_reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    requires_operator_ack: bool
    ai_input_detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "leverage_allowed": self.leverage_allowed,
            "leverage_ratio": self.leverage_ratio,
            "max_allowed_leverage": self.max_allowed_leverage,
            "reject_reason": self.reject_reason,
            "reject_reasons": list(self.reject_reasons),
            "evidence_refs": list(self.evidence_refs),
            "requires_operator_ack": self.requires_operator_ack,
            "ai_input_detected": self.ai_input_detected,
            # PR110 safety markers:
            "ai_trade_authority": False,
            "right_tail_live_boost_enabled": False,
            "decided_by": "deterministic_gate",
        }


def _scan_forbidden(mapping: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    for key in mapping.keys():
        if not isinstance(key, str):
            continue
        lowered = key.lower()
        if lowered in FORBIDDEN_LEVERAGE_INPUT_FIELDS:
            found.append(lowered)
            continue
        if (
            lowered.startswith("ai_")
            or lowered.startswith("llm_")
            or lowered.startswith("deepseek_")
        ):
            found.append(lowered)
    return sorted(set(found))


def _evidence_strength(ev: RightTailLeverageEvidence) -> float:
    """Deterministic 0..1 right-tail structure strength.

    Weighted blend of opportunity / volume / OI / breakout / liquidity.
    Missing optional inputs contribute their neutral share so the score
    never depends on an undefined field.
    """

    def _clamp01(x: float) -> float:
        return max(0.0, min(1.0, x))

    opp = _clamp01(ev.opportunity_score / 100.0 if ev.opportunity_score > 1.0 else ev.opportunity_score)
    vol = _clamp01(ev.volume_expansion_score / 100.0 if ev.volume_expansion_score > 1.0 else ev.volume_expansion_score)
    oi = (
        _clamp01(ev.oi_expansion_score / 100.0 if ev.oi_expansion_score > 1.0 else ev.oi_expansion_score)
        if ev.oi_expansion_score is not None
        else 0.5
    )
    brk = (
        _clamp01(
            ev.breakout_structure_score / 100.0
            if ev.breakout_structure_score > 1.0
            else ev.breakout_structure_score
        )
        if ev.breakout_structure_score is not None
        else 0.5
    )
    liq = _clamp01(ev.liquidity_score) if ev.liquidity_score is not None else 0.0
    return _clamp01(0.35 * opp + 0.2 * vol + 0.15 * oi + 0.15 * brk + 0.15 * liq)


def evaluate_right_tail_leverage_permission(
    evidence: RightTailLeverageEvidence | Mapping[str, Any],
    *,
    drawdown_warning_ratio: float = 0.6,
    min_structure_strength_for_boost: float = 0.6,
) -> LeverageDecision:
    """Deterministically decide right-tail leverage permission.

    Returns a :class:`LeverageDecision`. The leverage is decided ONLY
    from the supplied deterministic evidence + the capital profile + the
    risk state. AI / LLM / Telegram / blind / future-label fields are
    refused outright.
    """
    # --- 0. Forbidden (AI) input detection. -------------------------------
    if isinstance(evidence, RightTailLeverageEvidence):
        forbidden = _scan_forbidden(evidence.extra)
        ev = evidence
    else:
        forbidden = _scan_forbidden(evidence)
        ev = RightTailLeverageEvidence.from_mapping(evidence)

    profile: CapitalProfile = get_profile(ev.capital_profile_id)
    base = profile.base_leverage

    if forbidden:
        return LeverageDecision(
            leverage_allowed=False,
            leverage_ratio=base,
            max_allowed_leverage=base,
            reject_reason=RightTailLeverageReason.AI_INPUT_FORBIDDEN,
            reject_reasons=(RightTailLeverageReason.AI_INPUT_FORBIDDEN,),
            evidence_refs=tuple(f"forbidden_input:{k}" for k in forbidden),
            requires_operator_ack=False,
            ai_input_detected=True,
        )

    reasons: list[str] = []

    # --- 1. Deterministic hard gates. -------------------------------------
    if not ev.exit_plan_present:
        reasons.append(RightTailLeverageReason.NO_EXIT_PLAN)
    if not ev.stop_plan_present:
        reasons.append(RightTailLeverageReason.NO_STOP_PLAN)
    if not ev.take_profit_plan_present:
        reasons.append(RightTailLeverageReason.NO_TAKE_PROFIT_PLAN)
    if ev.liquidity_score is None or ev.liquidity_score < profile.min_exit_liquidity_score:
        reasons.append(RightTailLeverageReason.NO_LIQUIDITY_EVIDENCE)
    if ev.market_regime in _RISK_OFF_REGIMES:
        reasons.append(RightTailLeverageReason.REGIME_RISK_OFF)
    if ev.systemic_risk_state:
        reasons.append(RightTailLeverageReason.SYSTEMIC_RISK_ACTIVE)
    if ev.risk_halt_state:
        reasons.append(RightTailLeverageReason.RISK_HALT_ACTIVE)
    # Drawdown warning fires at a fraction of the kill-switch drawdown.
    drawdown_warn_level = profile.kill_switch_drawdown_pct * drawdown_warning_ratio
    if drawdown_warn_level > 0 and ev.current_drawdown >= drawdown_warn_level:
        reasons.append(RightTailLeverageReason.ACCOUNT_DRAWDOWN_WARNING)
    if not profile.right_tail_boost_allowed:
        reasons.append(RightTailLeverageReason.PROFILE_DISALLOWS_BOOST)
    if (
        ev.requested_boost
        and profile.require_floating_profit_for_boost
        and ev.floating_profit_state <= 0.0
    ):
        reasons.append(RightTailLeverageReason.NO_FLOATING_PROFIT_FOR_BOOST)
    if (
        ev.spread_bps > profile.max_slippage_bps
        or ev.estimated_slippage_bps > profile.max_slippage_bps
    ):
        reasons.append(RightTailLeverageReason.SLIPPAGE_OR_SPREAD_TOO_HIGH)
    if ev.symbol_exposure > profile.max_symbol_exposure_pct:
        reasons.append(RightTailLeverageReason.SYMBOL_EXPOSURE_TOO_HIGH)
    if ev.account_exposure > 1.0:
        reasons.append(RightTailLeverageReason.ACCOUNT_EXPOSURE_TOO_HIGH)
    if (
        ev.requested_leverage is not None
        and ev.requested_leverage > profile.right_tail_max_leverage
    ):
        reasons.append(RightTailLeverageReason.LEVERAGE_EXCEEDS_PROFILE_MAX)

    evidence_refs = (
        f"profile:{ev.capital_profile_id.value}",
        f"regime:{ev.market_regime.value}",
        f"stage:{ev.candidate_stage}",
        f"opportunity_score:{ev.opportunity_score}",
        f"liquidity_score:{ev.liquidity_score}",
        f"floating_profit_state:{ev.floating_profit_state}",
        f"current_drawdown:{ev.current_drawdown}",
        f"spread_bps:{ev.spread_bps}",
        f"estimated_slippage_bps:{ev.estimated_slippage_bps}",
        f"symbol_exposure:{ev.symbol_exposure}",
    )

    if reasons:
        return LeverageDecision(
            leverage_allowed=False,
            leverage_ratio=base,
            max_allowed_leverage=base,
            reject_reason=reasons[0],
            reject_reasons=tuple(reasons),
            evidence_refs=evidence_refs,
            requires_operator_ack=False,
        )

    # --- 2. Structure-strength gate for the boost. ------------------------
    strength = _evidence_strength(ev)
    if ev.requested_boost and strength < min_structure_strength_for_boost:
        # All hard gates passed, but the structure is not strong enough
        # to justify a boost: grant base leverage, deny the boost.
        return LeverageDecision(
            leverage_allowed=False,
            leverage_ratio=base,
            max_allowed_leverage=profile.max_leverage,
            reject_reason=RightTailLeverageReason.WEAK_RIGHT_TAIL_STRUCTURE,
            reject_reasons=(RightTailLeverageReason.WEAK_RIGHT_TAIL_STRUCTURE,),
            evidence_refs=evidence_refs + (f"structure_strength:{strength:.4f}",),
            requires_operator_ack=False,
        )

    # --- 3. Grant. --------------------------------------------------------
    if not ev.requested_boost:
        # No boost requested: base leverage is permitted under profile max.
        granted = min(base, profile.max_leverage)
        return LeverageDecision(
            leverage_allowed=True,
            leverage_ratio=granted,
            max_allowed_leverage=profile.max_leverage,
            reject_reason=None,
            reject_reasons=(),
            evidence_refs=evidence_refs + (f"structure_strength:{strength:.4f}",),
            requires_operator_ack=False,
        )

    # Boost granted: interpolate between base and the profile's right-tail
    # max according to structure strength, then clamp.
    rt_max = profile.right_tail_max_leverage
    granted = base + strength * (rt_max - base)
    granted = max(base, min(granted, rt_max))
    if ev.requested_leverage is not None:
        granted = min(granted, ev.requested_leverage)
    return LeverageDecision(
        leverage_allowed=True,
        leverage_ratio=round(granted, 4),
        max_allowed_leverage=rt_max,
        reject_reason=None,
        reject_reasons=(),
        evidence_refs=evidence_refs + (f"structure_strength:{strength:.4f}",),
        requires_operator_ack=True,
    )


__all__ = [
    "FORBIDDEN_LEVERAGE_INPUT_FIELDS",
    "RightTailLeverageReason",
    "RightTailLeverageEvidence",
    "LeverageDecision",
    "evaluate_right_tail_leverage_permission",
]
