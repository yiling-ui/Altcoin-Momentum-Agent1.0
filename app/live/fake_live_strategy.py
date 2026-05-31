"""Live strategy sandbox harness (PR117 - Full-System Single-Altcoin Live
Sandbox Audit v0).

A MINIMAL, deterministic strategy adapter that turns a fake live market
series (:class:`app.live.fake_live_market.FakeMarketSeries`) into a
strategy plan + the deterministic evidence the rest of the REAL live
chain consumes:

    market frames
      -> opportunity_score (deterministic blend of measured features)
      -> candidate stage + right-tail evidence
      -> planned entry zone / stop / take-profit / leverage request
      -> risk LiveOrderIntent (source=LIVE)
      -> right-tail leverage evidence (deterministic, NO AI fields)

HARD boundaries (the brief):
  * This is a SANDBOX STRATEGY HARNESS, NOT blind / replay / sim.
  * ``source = LIVE`` on every intent.
  * NO future labels, NO ``completed_tail_label``, NO MFE / MAE leakage.
  * AI / LLM / DeepSeek NEVER influences the plan.
  * Leverage is only ever REQUESTED here; the deterministic PR110
    right-tail leverage gate decides the actual permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.enums import LiveRuntimeMode, OrderSource
from app.live.capital_profile import CapitalProfileId, get_profile
from app.live.fake_live_market import FakeMarketSeries, MarketFrame
from app.live.live_risk_engine import LiveOrderIntent as RiskOrderIntent

FAKE_LIVE_STRATEGY_MODULE = "live.fake_live_strategy"


# Strategy decisions (closed taxonomy).
class StrategyDecision:
    NO_ENTRY = "NO_ENTRY"                       # quiet market, no signal
    OBSERVE = "OBSERVE"                          # low-confidence, observe only
    SHADOW_ENTRY_PLAN = "SHADOW_ENTRY_PLAN"      # right-tail breakout plan
    STOP_EXIT = "STOP_EXIT"                      # planned stop / exit fired


# Confidence threshold below which a candidate is observe-only.
OBSERVE_OPP_THRESHOLD = 45.0
# Structure floor below which there is no signal at all (quiet market).
QUIET_STRUCTURE_FLOOR = 0.15
# Structure strength required to call a right-tail breakout.
RIGHT_TAIL_BREAKOUT_FLOOR = 0.6


def opportunity_score_for(frame: MarketFrame) -> float:
    """Deterministic 0..100 opportunity score from measured features only."""
    blend = (
        0.4 * frame.breakout_structure_score
        + 0.3 * frame.volume_expansion_score
        + 0.3 * frame.oi_expansion_score
    )
    return round(100.0 * max(0.0, min(1.0, blend)), 4)


@dataclass(frozen=True)
class StrategyPlan:
    """A deterministic sandbox strategy plan (source=LIVE; no future labels)."""

    symbol: str
    decision: str
    side: str
    candidate_stage: str
    opportunity_score: float
    planned_entry_low: float
    planned_entry_high: float
    planned_entry_price: float
    planned_stop_price: float | None
    planned_take_profit_price: float
    planned_leverage_request: float
    planned_notional_usdt: float
    stop_plan_present: bool
    exit_plan_present: bool
    take_profit_plan_present: bool
    reasons: tuple[str, ...]
    # Deterministic leverage-gate evidence inputs (measured features only).
    liquidity_score: float
    spread_bps: float
    estimated_slippage_bps: float
    volume_expansion_score: float
    oi_expansion_score: float
    breakout_structure_score: float
    market_regime: Any
    systemic_risk_state: bool
    capital_profile_id: CapitalProfileId
    floating_profit_state: float = 0.0
    # Provenance markers (PR117 audit visibility).
    source: str = OrderSource.LIVE.value
    is_sandbox_harness: bool = True
    no_future_labels: bool = True
    completed_tail_label: Any = None
    mfe_pct: Any = None
    mae_pct: Any = None

    @property
    def produces_entry(self) -> bool:
        return self.decision == StrategyDecision.SHADOW_ENTRY_PLAN

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "decision": self.decision,
            "side": self.side,
            "candidate_stage": self.candidate_stage,
            "opportunity_score": self.opportunity_score,
            "planned_entry_zone": [self.planned_entry_low, self.planned_entry_high],
            "planned_entry_price": self.planned_entry_price,
            "planned_stop_price": self.planned_stop_price,
            "planned_take_profit_price": self.planned_take_profit_price,
            "planned_leverage_request": self.planned_leverage_request,
            "planned_notional_usdt": self.planned_notional_usdt,
            "stop_plan_present": self.stop_plan_present,
            "exit_plan_present": self.exit_plan_present,
            "take_profit_plan_present": self.take_profit_plan_present,
            "reasons": list(self.reasons),
            "source": self.source,
            "is_sandbox_harness": self.is_sandbox_harness,
            "no_future_labels": self.no_future_labels,
        }

    # ------------------------------------------------------------------
    # Adapters into the REAL live chain
    # ------------------------------------------------------------------
    def to_risk_intent(
        self,
        *,
        runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_LIMITED,
        drop_stop: bool = False,
        drop_exit: bool = False,
    ) -> RiskOrderIntent:
        """Build the PR112 risk-engine intent (source=LIVE).

        ``drop_stop`` / ``drop_exit`` let the audit prove a plan missing a
        stop / exit plan is rejected by the deterministic risk engine.
        """
        stop_present = self.stop_plan_present and not drop_stop
        exit_present = self.exit_plan_present and not drop_exit
        return RiskOrderIntent(
            symbol=self.symbol,
            side=self.side,
            planned_entry_price=self.planned_entry_price,
            planned_notional_usdt=self.planned_notional_usdt,
            planned_leverage=self.planned_leverage_request,
            planned_stop_price=self.planned_stop_price if stop_present else None,
            planned_take_profit_price=self.planned_take_profit_price,
            exit_plan_present=exit_present,
            stop_plan_present=stop_present,
            candidate_stage=self.candidate_stage,
            opportunity_score=self.opportunity_score,
            runtime_mode=runtime_mode,
            source=OrderSource.LIVE,
        )

    def to_leverage_evidence(
        self,
        *,
        runtime_mode: LiveRuntimeMode = LiveRuntimeMode.LIVE_LIMITED,
        request_boost: bool | None = None,
        requested_leverage: float | None = None,
        inject_forbidden_ai: bool = False,
    ) -> dict[str, Any]:
        """Build the deterministic right-tail leverage-gate evidence mapping.

        A right-tail BOOST is only requested when there is floating profit
        (the constitution: 没有浮盈不准疯狗). At entry there is none, so a
        base-leverage grant is requested by default. ``inject_forbidden_ai``
        is used by the audit to PROVE the gate refuses AI-shaped input.
        """
        boost = (self.floating_profit_state > 0.0) if request_boost is None else bool(request_boost)
        ev: dict[str, Any] = {
            "capital_profile_id": self.capital_profile_id,
            "runtime_mode": runtime_mode,
            "market_regime": self.market_regime,
            "systemic_risk_state": self.systemic_risk_state,
            "risk_halt_state": False,
            "candidate_stage": self.candidate_stage,
            "opportunity_score": self.opportunity_score,
            "liquidity_score": self.liquidity_score,
            "spread_bps": self.spread_bps,
            "estimated_slippage_bps": self.estimated_slippage_bps,
            "volume_expansion_score": self.volume_expansion_score,
            "volatility_state": "high",
            "current_drawdown": 0.0,
            "floating_profit_state": self.floating_profit_state,
            "exit_plan_present": self.exit_plan_present,
            "stop_plan_present": self.stop_plan_present,
            "take_profit_plan_present": self.take_profit_plan_present,
            "symbol_exposure": 0.0,
            "account_exposure": 0.0,
            "oi_expansion_score": self.oi_expansion_score,
            "breakout_structure_score": self.breakout_structure_score,
            "requested_boost": boost,
            "requested_leverage": requested_leverage,
        }
        if inject_forbidden_ai:
            # The gate MUST refuse this with AI_INPUT_FORBIDDEN.
            ev["ai_recommendation"] = "BUY_WITH_20X"
            ev["deepseek_opinion"] = "moon"
        return ev


class LiveStrategySandboxAdapter:
    """Deterministic sandbox strategy adapter (source=LIVE; no AI / no blind)."""

    name = "LiveStrategySandboxAdapter"

    def evaluate(
        self,
        series: FakeMarketSeries,
        *,
        capital_profile_id: CapitalProfileId | str = CapitalProfileId.L1_10U_PROBE,
        account_equity_usdt: float = 10.0,
    ) -> StrategyPlan:
        """Produce a deterministic :class:`StrategyPlan` from ``series``."""
        if isinstance(capital_profile_id, str) and not isinstance(
            capital_profile_id, CapitalProfileId
        ):
            capital_profile_id = CapitalProfileId(capital_profile_id)
        profile = get_profile(capital_profile_id)

        entry_frame = series.entry_frame
        opp = opportunity_score_for(entry_frame)

        # Decision logic (deterministic; measured features only).
        reasons: list[str] = []
        if (
            entry_frame.breakout_structure_score < QUIET_STRUCTURE_FLOOR
            and entry_frame.volume_expansion_score < QUIET_STRUCTURE_FLOOR
        ):
            decision = StrategyDecision.NO_ENTRY
            reasons.append("no_signal_quiet_market")
        elif opp < OBSERVE_OPP_THRESHOLD or entry_frame.breakout_structure_score < RIGHT_TAIL_BREAKOUT_FLOOR:
            decision = StrategyDecision.OBSERVE
            reasons.append("insufficient_right_tail_evidence_low_confidence_observe")
        else:
            decision = StrategyDecision.SHADOW_ENTRY_PLAN
            reasons.append("right_tail_breakout_structure_confirmed")

        entry_price = entry_frame.price
        # Conservative LONG plan geometry.
        stop_price = round(entry_price * 0.9, 8)
        take_profit_price = round(entry_price * 1.3, 8)
        # Notional sized off the profile cap (never a hardcoded 10U).
        planned_notional = round(min(profile.max_position_notional_usdt * 0.5, profile.max_position_notional_usdt), 8)
        if planned_notional <= 0:
            planned_notional = 0.0
        leverage_request = profile.base_leverage

        has_plan = decision == StrategyDecision.SHADOW_ENTRY_PLAN
        return StrategyPlan(
            symbol=series.symbol,
            decision=decision,
            side="LONG",
            candidate_stage="ATTACK" if has_plan else ("OBSERVE" if decision == StrategyDecision.OBSERVE else "NO_TRADE"),
            opportunity_score=opp,
            planned_entry_low=round(entry_price * 0.995, 8),
            planned_entry_high=round(entry_price * 1.005, 8),
            planned_entry_price=entry_price,
            planned_stop_price=stop_price if has_plan else None,
            planned_take_profit_price=take_profit_price,
            planned_leverage_request=leverage_request,
            planned_notional_usdt=planned_notional if has_plan else 0.0,
            stop_plan_present=has_plan,
            exit_plan_present=has_plan,
            take_profit_plan_present=has_plan,
            reasons=tuple(reasons),
            liquidity_score=entry_frame.liquidity_score,
            spread_bps=entry_frame.spread_bps,
            estimated_slippage_bps=entry_frame.estimated_slippage_bps,
            volume_expansion_score=entry_frame.volume_expansion_score,
            oi_expansion_score=entry_frame.oi_expansion_score,
            breakout_structure_score=entry_frame.breakout_structure_score,
            market_regime=entry_frame.market_regime,
            systemic_risk_state=entry_frame.systemic_risk_state,
            capital_profile_id=capital_profile_id,
            floating_profit_state=0.0,
        )

    def evaluate_exit(self, plan: StrategyPlan, series: FakeMarketSeries) -> dict[str, Any]:
        """Decide whether the planned stop / take-profit fired over ``series``.

        Deterministic: a LONG stop fires when the lowest price after entry
        falls to / below the planned stop; the take-profit fires when the
        highest price reaches the planned target.
        """
        if plan.planned_stop_price is None:
            return {"stop_triggered": False, "take_profit_triggered": False, "exit_decision": StrategyDecision.NO_ENTRY}
        # Frames after the entry frame (index 1) define the price path.
        post = series.frames[2:] if len(series.frames) > 2 else series.frames
        low = min(f.price for f in post) if post else plan.planned_entry_price
        high = max(f.price for f in post) if post else plan.planned_entry_price
        stop_triggered = low <= plan.planned_stop_price
        tp_triggered = high >= plan.planned_take_profit_price
        decision = StrategyDecision.STOP_EXIT if (stop_triggered or tp_triggered) else StrategyDecision.SHADOW_ENTRY_PLAN
        return {
            "stop_triggered": stop_triggered,
            "take_profit_triggered": tp_triggered,
            "lowest_price": low,
            "highest_price": high,
            "planned_stop_price": plan.planned_stop_price,
            "planned_take_profit_price": plan.planned_take_profit_price,
            "exit_decision": decision,
        }


__all__ = [
    "FAKE_LIVE_STRATEGY_MODULE",
    "StrategyDecision",
    "OBSERVE_OPP_THRESHOLD",
    "QUIET_STRUCTURE_FLOOR",
    "RIGHT_TAIL_BREAKOUT_FLOOR",
    "opportunity_score_for",
    "StrategyPlan",
    "LiveStrategySandboxAdapter",
]
