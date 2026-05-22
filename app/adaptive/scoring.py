"""Phase 11C.1C-A - Opportunity scoring formula + grade boundaries.

The formula is the Issue contract first version:

    score = (
        0.25 * momentum_strength
      + 0.20 * volume_expansion
      + 0.15 * liquidity_quality
      + 0.15 * regime_fit
      + 0.15 * freshness
      - 0.20 * manipulation_risk
      - 0.20 * late_chase_risk
    )

Inputs are clipped to ``[0.0, 100.0]`` before weighting; the score is
clipped to ``[0.0, 100.0]`` after summing. Grade boundaries:

  - S >= 80
  - A in [65, 80)
  - B in [50, 65)
  - C < 50

Phase 11C.1C-A boundary
-----------------------

  - Pure functions; no I/O, no global state, no side effects.
  - The formula is configurable via :class:`OpportunityScoreWeights`
    so future tuning can land without renaming the inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.adaptive.models import (
    OPPORTUNITY_GRADE_BOUNDARIES,
    OPPORTUNITY_GRADES,
    OpportunityScore,
)


@dataclass(frozen=True)
class OpportunityScoreInputs:
    """Inputs for :func:`compute_opportunity_score`.

    Each field is in ``[0.0, 100.0]``. Values outside that range are
    clipped before weighting.
    """

    momentum_strength: float = 0.0
    volume_expansion: float = 0.0
    liquidity_quality: float = 0.0
    regime_fit: float = 0.0
    freshness: float = 0.0
    manipulation_risk: float = 0.0
    late_chase_risk: float = 0.0


@dataclass(frozen=True)
class OpportunityScoreWeights:
    """Per-input weights for the formula.

    The Issue contract first-version weights are baked in as the
    default; future tuning can override per-call without touching the
    sum-of-weights or the grade boundaries.
    """

    momentum_strength: float = 0.25
    volume_expansion: float = 0.20
    liquidity_quality: float = 0.15
    regime_fit: float = 0.15
    freshness: float = 0.15
    manipulation_risk: float = 0.20
    late_chase_risk: float = 0.20


DEFAULT_OPPORTUNITY_SCORE_WEIGHTS: OpportunityScoreWeights = (
    OpportunityScoreWeights()
)


def _clip_unit_pct(value: float) -> float:
    """Clip ``value`` to ``[0.0, 100.0]``."""
    v = float(value)
    if v < 0.0:
        return 0.0
    if v > 100.0:
        return 100.0
    return v


def grade_for_score(score: float) -> str:
    """Return the grade letter for ``score``.

    Boundaries:
      - S >= 80
      - A in [65, 80)
      - B in [50, 65)
      - C < 50
    """
    s = float(score)
    if s >= OPPORTUNITY_GRADE_BOUNDARIES["S"]:
        return "S"
    if s >= OPPORTUNITY_GRADE_BOUNDARIES["A"]:
        return "A"
    if s >= OPPORTUNITY_GRADE_BOUNDARIES["B"]:
        return "B"
    return "C"


def compute_opportunity_score(
    inputs: OpportunityScoreInputs | dict[str, Any],
    *,
    weights: OpportunityScoreWeights | None = None,
    reason_tags: Iterable[str] | None = None,
) -> OpportunityScore:
    """Compute the weighted-sum opportunity score.

    ``inputs`` accepts either an :class:`OpportunityScoreInputs`
    dataclass or a plain dict for callsite ergonomics. Unknown keys
    on the dict are ignored. Missing keys default to ``0.0``.

    Returns an :class:`OpportunityScore` value object with the
    computed score + grade. ``reason_tags`` is propagated to the
    result and de-duplicated while preserving order.
    """
    w = weights or DEFAULT_OPPORTUNITY_SCORE_WEIGHTS
    if isinstance(inputs, dict):
        ins = OpportunityScoreInputs(
            momentum_strength=_clip_unit_pct(
                inputs.get("momentum_strength", 0.0)
            ),
            volume_expansion=_clip_unit_pct(
                inputs.get("volume_expansion", 0.0)
            ),
            liquidity_quality=_clip_unit_pct(
                inputs.get("liquidity_quality", 0.0)
            ),
            regime_fit=_clip_unit_pct(inputs.get("regime_fit", 0.0)),
            freshness=_clip_unit_pct(inputs.get("freshness", 0.0)),
            manipulation_risk=_clip_unit_pct(
                inputs.get("manipulation_risk", 0.0)
            ),
            late_chase_risk=_clip_unit_pct(
                inputs.get("late_chase_risk", 0.0)
            ),
        )
    else:
        ins = OpportunityScoreInputs(
            momentum_strength=_clip_unit_pct(inputs.momentum_strength),
            volume_expansion=_clip_unit_pct(inputs.volume_expansion),
            liquidity_quality=_clip_unit_pct(inputs.liquidity_quality),
            regime_fit=_clip_unit_pct(inputs.regime_fit),
            freshness=_clip_unit_pct(inputs.freshness),
            manipulation_risk=_clip_unit_pct(inputs.manipulation_risk),
            late_chase_risk=_clip_unit_pct(inputs.late_chase_risk),
        )

    raw = (
        w.momentum_strength * ins.momentum_strength
        + w.volume_expansion * ins.volume_expansion
        + w.liquidity_quality * ins.liquidity_quality
        + w.regime_fit * ins.regime_fit
        + w.freshness * ins.freshness
        - w.manipulation_risk * ins.manipulation_risk
        - w.late_chase_risk * ins.late_chase_risk
    )
    score = max(0.0, min(100.0, raw))
    grade = grade_for_score(score)

    seen: set[str] = set()
    deduped: list[str] = []
    if reason_tags is not None:
        for tag in reason_tags:
            text = str(tag).strip()
            if text and text not in seen:
                seen.add(text)
                deduped.append(text)

    return OpportunityScore(
        momentum_strength=ins.momentum_strength,
        volume_expansion=ins.volume_expansion,
        liquidity_quality=ins.liquidity_quality,
        regime_fit=ins.regime_fit,
        freshness=ins.freshness,
        manipulation_risk=ins.manipulation_risk,
        late_chase_risk=ins.late_chase_risk,
        score=score,
        grade=grade,
        reason_tags=tuple(deduped),
    )


__all__ = [
    "DEFAULT_OPPORTUNITY_SCORE_WEIGHTS",
    "OPPORTUNITY_GRADES",
    "OpportunityScoreInputs",
    "OpportunityScoreWeights",
    "compute_opportunity_score",
    "grade_for_score",
]
