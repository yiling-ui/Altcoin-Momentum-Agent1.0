"""Phase 11C.1C-A - Candidate stage classifier.

Phase 11C.1C-A pins a deterministic 5-bucket classifier:

  - ``early``    : freshly admitted, price has barely moved off
                   the first-seen reference, fresh in time.
  - ``mid``      : price has moved up a meaningful amount but is
                   still below the late / blowoff thresholds.
  - ``late``     : price has run up significantly off the first-seen
                   reference; chasing now carries elevated risk.
  - ``blowoff``  : extremely fast rip in the last 60s combined with
                   a large distance from the first-seen reference;
                   late_chase + blowoff risks are both high.
  - ``dumped``   : price has rolled over below the first-seen
                   reference (typical post-pump deflate). The
                   selector treats this as observe-only.

Inputs are taken from the candidate's :class:`OpportunityIdentity`
+ the latest :class:`AllMarketRadarSnapshot` (or a generic
``current_price`` / ``price_24h_high`` + acceleration). All
boundaries are tunable via the function arguments so future tuning
can land without renaming the buckets.

Phase 11C.1C-A boundary
-----------------------

Pure function. No I/O, no global state, no side effects.
"""

from __future__ import annotations

from app.adaptive.models import CANDIDATE_STAGES, CandidateStageAssessment


# Fractional distance thresholds. ``early`` covers the first 5%,
# ``mid`` covers 5-15%, ``late`` covers 15-30%, ``blowoff`` is above
# 30% (or above 20% combined with a strong 60s acceleration). The
# Issue brief leaves these tunable; the defaults below are
# documented in ``docs/PHASE_11C_1C_ADAPTIVE_CANDIDATE_REGIME_STRATEGY_SELECTOR.md``.
_DEFAULT_EARLY_DISTANCE = 0.05
_DEFAULT_MID_DISTANCE = 0.15
_DEFAULT_LATE_DISTANCE = 0.30
_DEFAULT_DUMPED_DISTANCE = -0.10
_DEFAULT_BLOWOFF_ACCEL_60S = 0.05
_DEFAULT_FRESHNESS_HALF_LIFE_MS = 5 * 60 * 1000  # 5 minutes


def classify_candidate_stage(
    *,
    first_seen_ts_ms: int,
    first_seen_price: float,
    current_price: float,
    current_ts_ms: int,
    price_24h_high: float | None = None,
    price_acceleration_60s: float | None = None,
    early_distance: float = _DEFAULT_EARLY_DISTANCE,
    mid_distance: float = _DEFAULT_MID_DISTANCE,
    late_distance: float = _DEFAULT_LATE_DISTANCE,
    dumped_distance: float = _DEFAULT_DUMPED_DISTANCE,
    blowoff_accel_60s: float = _DEFAULT_BLOWOFF_ACCEL_60S,
    freshness_half_life_ms: int = _DEFAULT_FRESHNESS_HALF_LIFE_MS,
) -> CandidateStageAssessment:
    """Classify a candidate's life-cycle stage.

    See module docstring for the bucket semantics.
    """
    reasons: list[str] = []
    cp = float(current_price or 0.0)
    fp = float(first_seen_price or 0.0)
    if fp <= 0.0 or cp <= 0.0:
        reasons.append("missing_price")
        return CandidateStageAssessment(
            stage="early",
            freshness=0.5,
            late_chase_risk=0.0,
            blowoff_risk=0.0,
            first_seen_ts=int(first_seen_ts_ms or 0),
            first_seen_price=fp,
            current_price=cp,
            distance_from_first_seen=0.0,
            distance_to_24h_high=0.0,
            reason_tags=tuple(reasons),
        )

    distance = (cp - fp) / fp

    high = float(price_24h_high) if price_24h_high is not None else 0.0
    if high > 0:
        # Distance to 24h high is the gap between current and high
        # as a fraction of the high (positive when below the high).
        distance_to_high = max(0.0, (high - cp) / high)
    else:
        distance_to_high = 0.0

    elapsed_ms = max(0, int(current_ts_ms) - int(first_seen_ts_ms))
    half_life = max(1, int(freshness_half_life_ms))
    # Exponential-style decay capped to [0, 1]. ``elapsed_ms == 0`` ->
    # 1.0 (just admitted); ``elapsed_ms == half_life`` -> 0.5.
    if elapsed_ms <= 0:
        freshness = 1.0
    else:
        freshness = max(0.0, min(1.0, half_life / float(half_life + elapsed_ms)))

    accel_60 = float(price_acceleration_60s) if price_acceleration_60s is not None else 0.0

    # Stage decision tree.
    stage: str
    if distance <= dumped_distance:
        stage = "dumped"
        reasons.append("price_below_first_seen")
    elif distance >= late_distance or (
        distance >= mid_distance and accel_60 >= blowoff_accel_60s
    ):
        # blowoff vs. late: a fast 60s rip combined with a large
        # distance is a blowoff. Otherwise late.
        if accel_60 >= blowoff_accel_60s and distance >= mid_distance:
            stage = "blowoff"
            reasons.append("fast_acceleration_60s")
            reasons.append("large_distance_from_first_seen")
        else:
            stage = "late"
            reasons.append("large_distance_from_first_seen")
    elif distance >= early_distance:
        stage = "mid"
        reasons.append("moderate_distance_from_first_seen")
    else:
        stage = "early"
        reasons.append("near_first_seen_price")

    # late_chase_risk: rises as the candidate moves further from
    # first_seen; max at 1.0 once distance reaches 2 * late_distance.
    if distance <= 0.0:
        late_chase_risk = 0.0
    else:
        denom = max(late_distance * 2.0, 0.01)
        late_chase_risk = max(0.0, min(1.0, distance / denom))

    # blowoff_risk: combines acceleration_60s and distance. Both
    # contribute; capped at 1.0.
    accel_component = max(0.0, accel_60 / max(blowoff_accel_60s * 2.0, 0.01))
    distance_component = max(0.0, distance / max(late_distance * 2.0, 0.01))
    blowoff_risk = max(0.0, min(1.0, 0.6 * accel_component + 0.4 * distance_component))
    if distance <= 0.0:
        blowoff_risk = min(blowoff_risk, 0.0)

    if stage not in CANDIDATE_STAGES:
        stage = "early"

    return CandidateStageAssessment(
        stage=stage,
        freshness=float(freshness),
        late_chase_risk=float(late_chase_risk),
        blowoff_risk=float(blowoff_risk),
        first_seen_ts=int(first_seen_ts_ms or 0),
        first_seen_price=fp,
        current_price=cp,
        distance_from_first_seen=float(distance),
        distance_to_24h_high=float(distance_to_high),
        reason_tags=tuple(reasons),
    )


__all__ = [
    "classify_candidate_stage",
]
