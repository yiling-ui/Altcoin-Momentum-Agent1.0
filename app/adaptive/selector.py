"""Phase 11C.1C-A - Strategy mode selector.

The selector chooses ONE of:

  - ``follow``    : early + high regime_fit + high momentum + high
                    volume_expansion + low late_chase_risk
  - ``pullback``  : mid + strong momentum but stretched (high
                    late_chase_risk)
  - ``observe``   : late or blowoff
  - ``reject``    : high manipulation_risk OR Risk-Off / No-Trade
                    regime

Phase 11C.1C-A boundary
-----------------------

The ``mode`` is a **paper / virtual** field. ``follow`` does NOT
authorise opening a position; the Risk Engine remains the single
trade-decision gate.

Pure function. No I/O, no global state, no side effects.
"""

from __future__ import annotations

from app.adaptive.models import (
    CandidateStageAssessment,
    MarketRegimeAssessment,
    OpportunityScore,
    StrategyModeDecision,
)


# ---------------------------------------------------------------------------
# Tunable thresholds
# ---------------------------------------------------------------------------
_HIGH_MANIPULATION_RISK = 60.0       # >= 60 -> reject
_HIGH_LATE_CHASE_RISK = 60.0         # late_chase score 0..100
_HIGH_MOMENTUM = 60.0
_HIGH_VOLUME_EXPANSION = 50.0
_HIGH_REGIME_FIT = 60.0
_LOW_LATE_CHASE_RISK = 40.0
_BLOWOFF_RISK_THRESHOLD = 0.6        # CandidateStageAssessment.blowoff_risk


def select_strategy_mode(
    *,
    market_regime: MarketRegimeAssessment,
    candidate_stage: CandidateStageAssessment,
    opportunity_score: OpportunityScore,
) -> StrategyModeDecision:
    """Return the strategy expression for the candidate.

    The selector is deterministic and side-effect free. Decision
    flow (in priority order):

      1. ``manipulation_risk >= 60`` -> reject
      2. regime is RISK_OFF / NO_TRADE / SYSTEMIC_RISK -> reject
      3. stage is ``dumped`` -> observe
      4. stage is ``blowoff`` -> observe
      5. stage is ``late`` -> observe
      6. stage is ``mid`` AND momentum is high AND late_chase_risk
         is high -> pullback
      7. stage is ``early`` AND every "follow" condition holds ->
         follow (and the regime allows it)
      8. otherwise -> observe
    """
    reasons: list[str] = []
    notes: list[str] = []

    # ---- 1. Manipulation veto -----------------------------------
    if float(opportunity_score.manipulation_risk) >= _HIGH_MANIPULATION_RISK:
        reasons.append("high_manipulation_risk")
        return StrategyModeDecision(
            mode="reject",
            follow_allowed=False,
            pullback_allowed=False,
            observe_only=False,
            reject_reason="high_manipulation_risk",
            reason_tags=tuple(reasons),
            notes=tuple(notes),
        )

    # ---- 2. Regime veto -----------------------------------------
    regime_name = str(market_regime.regime_name).strip()
    if regime_name in {"RISK_OFF", "NO_TRADE", "SYSTEMIC_RISK", "ALT_RISK_OFF"}:
        reasons.append(f"regime_{regime_name.lower()}")
        for r in market_regime.no_trade_reason:
            reasons.append(str(r))
        # ALT_RISK_OFF still allows observe-only for reflection;
        # NO_TRADE / SYSTEMIC_RISK / RISK_OFF reject outright.
        if regime_name == "ALT_RISK_OFF":
            return StrategyModeDecision(
                mode="observe",
                follow_allowed=False,
                pullback_allowed=False,
                observe_only=True,
                reject_reason=None,
                reason_tags=tuple(reasons),
                notes=tuple(notes),
            )
        return StrategyModeDecision(
            mode="reject",
            follow_allowed=False,
            pullback_allowed=False,
            observe_only=False,
            reject_reason=f"regime_{regime_name.lower()}",
            reason_tags=tuple(reasons),
            notes=tuple(notes),
        )

    stage = str(candidate_stage.stage)

    # ---- 3..5. Late / blowoff / dumped -> observe ---------------
    if stage in {"late", "blowoff", "dumped"}:
        reasons.append(f"stage_{stage}")
        if float(candidate_stage.blowoff_risk) >= _BLOWOFF_RISK_THRESHOLD:
            reasons.append("high_blowoff_risk")
        return StrategyModeDecision(
            mode="observe",
            follow_allowed=False,
            pullback_allowed=False,
            observe_only=True,
            reject_reason=None,
            reason_tags=tuple(reasons),
            notes=tuple(notes),
        )

    momentum_strong = (
        float(opportunity_score.momentum_strength) >= _HIGH_MOMENTUM
    )
    volume_strong = (
        float(opportunity_score.volume_expansion) >= _HIGH_VOLUME_EXPANSION
    )
    regime_fit_strong = (
        float(opportunity_score.regime_fit) >= _HIGH_REGIME_FIT
    )
    late_chase_high = (
        float(opportunity_score.late_chase_risk) >= _HIGH_LATE_CHASE_RISK
    )
    late_chase_low = (
        float(opportunity_score.late_chase_risk) <= _LOW_LATE_CHASE_RISK
    )
    follow_allowed_by_regime = "follow" in market_regime.allowed_strategy_modes

    # ---- 6. Mid + stretched -> pullback ------------------------
    if stage == "mid" and momentum_strong and late_chase_high:
        reasons.append("stage_mid")
        reasons.append("strong_momentum_stretched")
        return StrategyModeDecision(
            mode="pullback",
            follow_allowed=False,
            pullback_allowed=True,
            observe_only=False,
            reject_reason=None,
            reason_tags=tuple(reasons),
            notes=tuple(notes),
        )

    # ---- 7. Early + every follow condition -> follow -----------
    if (
        stage == "early"
        and momentum_strong
        and volume_strong
        and regime_fit_strong
        and late_chase_low
        and follow_allowed_by_regime
    ):
        reasons.append("stage_early")
        reasons.append("high_regime_fit")
        reasons.append("high_momentum")
        reasons.append("high_volume_expansion")
        reasons.append("low_late_chase_risk")
        return StrategyModeDecision(
            mode="follow",
            follow_allowed=True,
            pullback_allowed=True,
            observe_only=False,
            reject_reason=None,
            reason_tags=tuple(reasons),
            notes=tuple(notes),
        )

    # ---- 8. Default -> observe ---------------------------------
    if stage == "early":
        reasons.append("stage_early")
    elif stage == "mid":
        reasons.append("stage_mid")
    if not momentum_strong:
        reasons.append("momentum_not_high_enough")
    if not volume_strong:
        reasons.append("volume_not_high_enough")
    if not regime_fit_strong:
        reasons.append("regime_fit_not_high_enough")
    if not follow_allowed_by_regime:
        reasons.append("follow_not_allowed_by_regime")

    return StrategyModeDecision(
        mode="observe",
        follow_allowed=False,
        pullback_allowed=False,
        observe_only=True,
        reject_reason=None,
        reason_tags=tuple(reasons),
        notes=tuple(notes),
    )


__all__ = [
    "select_strategy_mode",
]
