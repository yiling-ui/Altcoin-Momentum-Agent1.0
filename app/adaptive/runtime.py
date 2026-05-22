"""Phase 11C.1C-B - Adaptive Candidate Runtime Calibration helpers.

This module is the *pure-function* engine for the Phase 11C.1C-B
runtime calibration block (:class:`RuntimeCalibrationMetrics`). It
turns a small set of per-candidate runtime inputs (first-seen price /
ts, current price, recent quote-volume + price history, current
volume rank, volume rank ~5 min ago, 24h high) into the fifteen
fields the brief enumerates.

Phase 11C.1C-B boundary
-----------------------

  - Pure functions; no I/O, no global state, no side effects.
  - The values are **descriptive**:
      * ``early_tail_score`` is a paper / virtual signal the
        :class:`CandidatePool` consults to *protect* high-tail
        candidates from capacity eviction. It does NOT authorise a
        real position.
      * ``late_chase_risk`` is a paper / virtual risk score the
        Strategy Selector / Risk Engine read alongside the existing
        ``CandidateStageAssessment.late_chase_risk``. Late /
        blowoff candidates remain observe-only regardless of any
        ``early_tail_score``.
  - Nothing here flips a Phase 1 safety flag, opens a socket,
    imports an exchange SDK, or reads ``os.environ``.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from app.adaptive.models import RuntimeCalibrationMetrics


# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

#: Window lengths used by the cheap accelerator helpers.
_ONE_MIN_MS: int = 60_000
_FIVE_MIN_MS: int = 5 * 60_000

#: Default freshness half-life. ``elapsed_ms == half_life`` -> 0.5.
DEFAULT_FRESHNESS_HALF_LIFE_MS: int = 5 * 60 * 1000  # 5 minutes

#: Default early-tail-score threshold above which the candidate pool
#: protects a candidate from capacity eviction. Tuned conservatively:
#: a 60+ score requires multiple co-occurring signals (volume rank
#: jump + accel + freshness).
DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD: float = 60.0


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


# ---------------------------------------------------------------------------
# Acceleration helpers
# ---------------------------------------------------------------------------
def _value_at_lookback(
    history: Sequence[tuple[int, float]],
    *,
    now_ms: int,
    lookback_ms: int,
) -> float | None:
    """Return the value recorded ~``lookback_ms`` ms before ``now_ms``.

    ``history`` is an ordered (oldest -> newest) sequence of
    ``(ts_ms, value)``. Returns the most recent sample at-or-before
    ``now_ms - lookback_ms``, or ``None`` if no sample is old
    enough but the oldest sample is at least half the lookback old
    (so a short-burst run still produces a useful baseline). When
    no usable baseline exists, returns ``None``.
    """
    if not history:
        return None
    target_ts = int(now_ms) - int(lookback_ms)
    baseline: float | None = None
    for sample_ts, value in history:
        if int(sample_ts) <= target_ts:
            baseline = float(value)
        else:
            break
    if baseline is None:
        oldest_ts, oldest_value = history[0]
        if int(now_ms) - int(oldest_ts) >= int(lookback_ms) // 2:
            baseline = float(oldest_value)
    return baseline


def compute_relative_acceleration(
    history: Sequence[tuple[int, float]],
    *,
    now_ms: int,
    lookback_ms: int,
) -> float:
    """Return ``(latest - baseline) / baseline`` over ``lookback_ms``.

    Returns ``0.0`` when no usable baseline / latest sample exists.
    ``baseline <= 0`` collapses to 0.0 (defensive: avoids division by
    zero on a bad-data symbol).
    """
    if not history:
        return 0.0
    baseline = _value_at_lookback(
        history, now_ms=now_ms, lookback_ms=lookback_ms
    )
    if baseline is None or baseline <= 0:
        return 0.0
    latest = float(history[-1][1])
    if latest <= 0:
        return 0.0
    return float((latest - baseline) / baseline)


def compute_freshness_score(
    *,
    first_seen_ts_ms: int,
    current_ts_ms: int,
    half_life_ms: int = DEFAULT_FRESHNESS_HALF_LIFE_MS,
) -> float:
    """Return a freshness score in ``[0.0, 1.0]``.

    Decay shape: ``half_life / (half_life + elapsed_ms)`` so
    ``elapsed_ms == 0`` -> 1.0 and ``elapsed_ms == half_life`` -> 0.5.
    """
    elapsed = max(0, int(current_ts_ms) - int(first_seen_ts_ms))
    if elapsed <= 0:
        return 1.0
    half = max(1, int(half_life_ms))
    return max(0.0, min(1.0, half / float(half + elapsed)))


# ---------------------------------------------------------------------------
# Early-tail and late-chase scoring (paper / virtual)
# ---------------------------------------------------------------------------
def compute_early_tail_score(
    *,
    quote_volume_acceleration_1m: float = 0.0,
    quote_volume_acceleration_5m: float = 0.0,
    price_acceleration_1m: float = 0.0,
    price_acceleration_5m: float = 0.0,
    volume_rank_jump_5m: int = 0,
    freshness_score: float = 1.0,
    distance_from_first_seen: float = 0.0,
    distance_to_24h_high: float = 0.0,
    candidate_stage: str | None = None,
) -> float:
    """Return an early-tail score in ``[0.0, 100.0]``.

    The score is additive across cheap, brief-mandated signals:

      - ``volume_rank_jump_5m`` (each rank improvement adds points up
        to a cap)
      - quote-volume acceleration (1m + 5m, positive only)
      - price acceleration (1m + 5m, positive only)

    Then **multiplied** by the freshness score so a stale candidate
    cannot rack up a high early-tail score. Late / blowoff / dumped
    candidates are explicitly capped at a low value so they cannot
    qualify for ``early_tail`` retention.

    The function is deterministic; the same inputs always produce
    the same output.
    """
    score = 0.0

    rank_jump = max(0, int(volume_rank_jump_5m))
    if rank_jump > 0:
        score += min(35.0, rank_jump * 5.0)

    qv_1m = max(0.0, float(quote_volume_acceleration_1m))
    if qv_1m > 0:
        # 1.0 (i.e. 100% increase) -> 25 pts; capped.
        score += min(25.0, qv_1m * 25.0)
    qv_5m = max(0.0, float(quote_volume_acceleration_5m))
    if qv_5m > 0:
        score += min(15.0, qv_5m * 15.0)

    pa_1m = max(0.0, float(price_acceleration_1m))
    if pa_1m > 0:
        # 0.05 -> 25 pts; capped.
        score += min(25.0, pa_1m * 500.0)
    pa_5m = max(0.0, float(price_acceleration_5m))
    if pa_5m > 0:
        score += min(15.0, pa_5m * 200.0)

    # Freshness modulates the score: a stale candidate is not "early".
    fresh = max(0.0, min(1.0, float(freshness_score)))
    score *= fresh

    # Stage gating: late / blowoff / dumped cannot be "early tail".
    if candidate_stage in {"late", "blowoff", "dumped"}:
        score = min(score, 25.0)

    # Distance from first-seen above 30% suggests we missed the
    # entry. Soft-cap the score to keep the chain from re-promoting.
    if float(distance_from_first_seen) >= 0.30:
        score = min(score, 30.0)

    return max(0.0, min(100.0, score))


def compute_late_chase_risk_score(
    *,
    distance_from_first_seen: float = 0.0,
    distance_to_24h_high: float = 0.0,
    freshness_score: float = 1.0,
    candidate_stage: str | None = None,
    blowoff_risk: float = 0.0,
) -> float:
    """Return a late-chase risk score in ``[0.0, 100.0]``.

    Late-chase risk is **high** when the candidate has run up a lot
    relative to its first-seen reference, sits near its 24h high,
    has lost freshness, or is already classified as ``late`` /
    ``blowoff``.
    """
    risk = 0.0

    distance = float(distance_from_first_seen)
    if distance > 0:
        # 30% above first seen -> 60 pts; 50% -> 100 pts (capped).
        risk += min(60.0, distance * 200.0)

    high_distance = max(0.0, float(distance_to_24h_high))
    # Sitting on the 24h high adds risk; >5% below adds nothing.
    if high_distance < 0.05:
        risk += (1.0 - high_distance / 0.05) * 20.0

    fresh = max(0.0, min(1.0, float(freshness_score)))
    risk += (1.0 - fresh) * 10.0

    if candidate_stage == "late":
        risk = max(risk, 70.0)
    elif candidate_stage == "blowoff":
        risk = max(risk, 80.0)
    elif candidate_stage == "dumped":
        # ``dumped`` already broke down; chase risk is low (price
        # below first seen). The selector treats dumped as observe.
        risk = min(risk, 40.0)

    # Blowoff risk feeds in directly.
    risk += max(0.0, min(1.0, float(blowoff_risk))) * 20.0

    return max(0.0, min(100.0, risk))


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------
def compute_runtime_calibration(
    *,
    first_seen_ts_ms: int,
    first_seen_price: float,
    current_ts_ms: int,
    current_price: float,
    price_24h_high: float | None = None,
    price_history: Sequence[tuple[int, float]] | None = None,
    quote_volume_history: Sequence[tuple[int, float]] | None = None,
    volume_rank: int = 0,
    volume_rank_5m_ago: int | None = None,
    candidate_stage: str | None = None,
    blowoff_risk: float = 0.0,
    freshness_half_life_ms: int = DEFAULT_FRESHNESS_HALF_LIFE_MS,
) -> RuntimeCalibrationMetrics:
    """Build a :class:`RuntimeCalibrationMetrics` from raw inputs.

    All inputs are optional. Missing inputs collapse to a
    conservative default (``0.0`` / ``0`` / ``None``); the function
    never raises on missing data.
    """
    fs_price = max(0.0, _safe_float(first_seen_price))
    cp = max(0.0, _safe_float(current_price))

    if fs_price > 0 and cp > 0:
        price_change = (cp - fs_price) / fs_price
    else:
        price_change = 0.0

    high = _safe_float(price_24h_high, 0.0)
    if high > 0 and cp > 0:
        distance_to_high = max(0.0, (high - cp) / high)
    else:
        distance_to_high = 0.0

    if fs_price > 0 and cp > 0:
        distance_from_first_seen = (cp - fs_price) / fs_price
    else:
        distance_from_first_seen = 0.0

    freshness = compute_freshness_score(
        first_seen_ts_ms=int(first_seen_ts_ms),
        current_ts_ms=int(current_ts_ms),
        half_life_ms=int(freshness_half_life_ms),
    )

    price_hist: list[tuple[int, float]] = list(price_history or [])
    qv_hist: list[tuple[int, float]] = list(quote_volume_history or [])
    pa_1m = compute_relative_acceleration(
        price_hist, now_ms=int(current_ts_ms), lookback_ms=_ONE_MIN_MS
    )
    pa_5m = compute_relative_acceleration(
        price_hist, now_ms=int(current_ts_ms), lookback_ms=_FIVE_MIN_MS
    )
    qv_1m = compute_relative_acceleration(
        qv_hist, now_ms=int(current_ts_ms), lookback_ms=_ONE_MIN_MS
    )
    qv_5m = compute_relative_acceleration(
        qv_hist, now_ms=int(current_ts_ms), lookback_ms=_FIVE_MIN_MS
    )

    # Volume rank jump: positive when the candidate moved up the
    # leaderboard (smaller rank = better). Negative when it slipped.
    rank_now = max(0, _safe_int(volume_rank))
    rank_old = (
        _safe_int(volume_rank_5m_ago)
        if volume_rank_5m_ago is not None
        else 0
    )
    if rank_old > 0 and rank_now > 0:
        volume_rank_jump_5m = int(rank_old - rank_now)
    else:
        volume_rank_jump_5m = 0

    early_tail = compute_early_tail_score(
        quote_volume_acceleration_1m=qv_1m,
        quote_volume_acceleration_5m=qv_5m,
        price_acceleration_1m=pa_1m,
        price_acceleration_5m=pa_5m,
        volume_rank_jump_5m=volume_rank_jump_5m,
        freshness_score=freshness,
        distance_from_first_seen=distance_from_first_seen,
        distance_to_24h_high=distance_to_high,
        candidate_stage=candidate_stage,
    )
    late_chase = compute_late_chase_risk_score(
        distance_from_first_seen=distance_from_first_seen,
        distance_to_24h_high=distance_to_high,
        freshness_score=freshness,
        candidate_stage=candidate_stage,
        blowoff_risk=blowoff_risk,
    )

    return RuntimeCalibrationMetrics(
        candidate_first_seen_ts=int(first_seen_ts_ms or 0),
        candidate_first_seen_price=float(fs_price),
        current_price=float(cp),
        price_change_since_first_seen=float(price_change),
        quote_volume_acceleration_1m=float(qv_1m),
        quote_volume_acceleration_5m=float(qv_5m),
        price_acceleration_1m=float(pa_1m),
        price_acceleration_5m=float(pa_5m),
        volume_rank=int(rank_now),
        volume_rank_jump_5m=int(volume_rank_jump_5m),
        distance_to_24h_high=float(distance_to_high),
        distance_from_first_seen=float(distance_from_first_seen),
        freshness_score=float(freshness),
        late_chase_risk=float(late_chase),
        early_tail_score=float(early_tail),
    )


__all__ = [
    "DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD",
    "DEFAULT_FRESHNESS_HALF_LIFE_MS",
    "compute_early_tail_score",
    "compute_freshness_score",
    "compute_late_chase_risk_score",
    "compute_relative_acceleration",
    "compute_runtime_calibration",
]
