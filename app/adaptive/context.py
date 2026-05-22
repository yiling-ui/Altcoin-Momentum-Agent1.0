"""Phase 11C.1C-A - AdaptiveCandidateContext orchestrator.

The :func:`build_adaptive_candidate_context` helper is the single
entry point the Phase 11C.1B WS-radar event-chain driver calls per
ACTIVE candidate. It chains the four cheap classifiers + scorer in
the canonical order:

    1. assess_market_regime        -> MarketRegimeAssessment
    2. classify_candidate_stage    -> CandidateStageAssessment
    3. compute_opportunity_score   -> OpportunityScore
    4. select_strategy_mode        -> StrategyModeDecision
    5. build_cluster_context       -> ClusterContext
    6. build_label_queue_contract  -> LabelQueueContract

and returns a frozen :class:`AdaptiveCandidateContext` whose payload
is JSON-stable so Phase 8.5 export + Phase 10A replay round-trip it
without ambiguity.

Phase 11C.1C-A boundary
-----------------------

  - Pure function. No I/O, no ``EventRepository.append_event``
    call, no LLM, no Telegram outbound.
  - The orchestrator uses ONLY information already present on the
    candidate / radar snapshot or supplied by the caller. It does
    NOT issue any REST call.
  - The strategy_mode + label_queue are paper / virtual fields;
    nothing in this module flips a Phase 1 safety flag.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.adaptive.cluster import build_cluster_context
from app.adaptive.label_queue import (
    DEFAULT_TRACKING_WINDOWS,
    build_label_queue_contract,
)
from app.adaptive.models import (
    AdaptiveCandidateContext,
    CandidateStageAssessment,
    ClusterContext,
    LabelQueueContract,
    MarketRegimeAssessment,
    OpportunityScore,
    StrategyModeDecision,
)
from app.adaptive.regime import assess_market_regime
from app.adaptive.scoring import (
    OpportunityScoreInputs,
    OpportunityScoreWeights,
    compute_opportunity_score,
)
from app.adaptive.selector import select_strategy_mode
from app.adaptive.stage import classify_candidate_stage


# ---------------------------------------------------------------------------
# Canonical version labels for this PR.
#
# The labels deliberately differ from the Phase 8.5 ``ConfigVersions``
# defaults so Reflection can group / split adaptive events by their
# Phase 11C.1C-A "first version" provenance. A future PR that bumps
# the formula or the state machine bumps the label and Reflection
# automatically picks up the change.
# ---------------------------------------------------------------------------
AdaptiveStrategyVersion: str = "phase_11c_1c_a.strategy.v1"
AdaptiveScoringVersion: str = "phase_11c_1c_a.scoring.v1"
AdaptiveStateMachineVersion: str = "phase_11c_1c_a.state_machine.v1"

#: Key under which the adaptive context lands on the Phase 8.5
#: ``learning_ready`` block. The :class:`LearningReadyContext`
#: aggregator carries it through its ``adaptive_candidate`` field
#: (set explicitly so the export / replay layer can index into it
#: deterministically).
ADAPTIVE_LEARNING_READY_KEY: str = "adaptive_candidate"


def build_adaptive_candidate_context(
    *,
    opportunity_id: str,
    scan_batch_id: str,
    symbol: str,
    timestamp_ms: int,
    # Stage classifier inputs.
    first_seen_ts_ms: int,
    first_seen_price: float,
    current_price: float,
    price_24h_high: float | None = None,
    price_acceleration_60s: float | None = None,
    # Regime classifier inputs (caller supplies the aggregate).
    avg_price_acceleration_60s: float | None = None,
    positive_acceleration_ratio: float | None = None,
    liquidation_event_rate: float | None = None,
    data_quality: str | None = None,
    snapshot_count: int = 0,
    # Scoring inputs.
    score_inputs: OpportunityScoreInputs | Mapping[str, Any] | None = None,
    score_weights: OpportunityScoreWeights | None = None,
    # Cluster inputs.
    cluster_id: str | None = None,
    radar_score: float = 0.0,
    peer_scores: Mapping[str, float] | None = None,
    cluster_reason: tuple[str, ...] = (),
    # Label-queue inputs.
    tracking_windows: tuple[str, ...] | None = None,
    label_queue_notes: tuple[str, ...] = (),
    # Versioning + provenance.
    strategy_version: str | None = None,
    scoring_version: str | None = None,
    risk_config_version: str = "phase_11c_1c_a.risk_config.v1",
    state_machine_version: str | None = None,
    source_phase: str = "phase_11c_1c_a_adaptive_candidate",
    notes: tuple[str, ...] = (),
) -> AdaptiveCandidateContext:
    """Build an :class:`AdaptiveCandidateContext` for one candidate.

    All inputs other than the identity tuple (``opportunity_id`` /
    ``scan_batch_id`` / ``symbol`` / ``timestamp_ms``) are optional;
    each cheap classifier returns a conservative default when its
    inputs are missing.
    """
    market_regime: MarketRegimeAssessment = assess_market_regime(
        avg_price_acceleration_60s=avg_price_acceleration_60s,
        positive_acceleration_ratio=positive_acceleration_ratio,
        liquidation_event_rate=liquidation_event_rate,
        data_quality=data_quality,
        snapshot_count=snapshot_count,
    )

    candidate_stage: CandidateStageAssessment = classify_candidate_stage(
        first_seen_ts_ms=int(first_seen_ts_ms),
        first_seen_price=float(first_seen_price or 0.0),
        current_price=float(current_price or 0.0),
        current_ts_ms=int(timestamp_ms),
        price_24h_high=price_24h_high,
        price_acceleration_60s=price_acceleration_60s,
    )

    # If the caller did not supply explicit score inputs, derive
    # conservative ones from the stage + regime so downstream code
    # always sees a non-None OpportunityScore. The derivation only
    # uses information already in scope.
    if score_inputs is None:
        derived_inputs: dict[str, float] = _derive_score_inputs_from_state(
            candidate_stage=candidate_stage,
            market_regime=market_regime,
            radar_score=float(radar_score),
        )
    elif isinstance(score_inputs, Mapping):
        derived_inputs = dict(score_inputs)
    else:
        derived_inputs = {
            "momentum_strength": float(score_inputs.momentum_strength),
            "volume_expansion": float(score_inputs.volume_expansion),
            "liquidity_quality": float(score_inputs.liquidity_quality),
            "regime_fit": float(score_inputs.regime_fit),
            "freshness": float(score_inputs.freshness),
            "manipulation_risk": float(score_inputs.manipulation_risk),
            "late_chase_risk": float(score_inputs.late_chase_risk),
        }

    opportunity_score: OpportunityScore = compute_opportunity_score(
        derived_inputs,
        weights=score_weights,
    )

    strategy_mode: StrategyModeDecision = select_strategy_mode(
        market_regime=market_regime,
        candidate_stage=candidate_stage,
        opportunity_score=opportunity_score,
    )

    cluster: ClusterContext = build_cluster_context(
        symbol=symbol,
        radar_score=float(radar_score),
        cluster_id=cluster_id,
        peer_scores=peer_scores,
        cluster_reason=cluster_reason,
    )

    label_queue: LabelQueueContract = build_label_queue_contract(
        opportunity_id=opportunity_id,
        scan_batch_id=scan_batch_id,
        symbol=symbol,
        enqueued_at_ms=int(timestamp_ms),
        reference_price=float(current_price or 0.0),
        tracking_windows=tracking_windows,
        notes=label_queue_notes,
    )

    return AdaptiveCandidateContext(
        opportunity_id=str(opportunity_id),
        scan_batch_id=str(scan_batch_id),
        symbol=str(symbol),
        timestamp_ms=int(timestamp_ms),
        market_regime=market_regime,
        candidate_stage=candidate_stage,
        opportunity_score=opportunity_score,
        strategy_mode=strategy_mode,
        cluster=cluster,
        label_queue=label_queue,
        strategy_version=str(
            strategy_version or AdaptiveStrategyVersion
        ),
        scoring_version=str(scoring_version or AdaptiveScoringVersion),
        risk_config_version=str(risk_config_version),
        state_machine_version=str(
            state_machine_version or AdaptiveStateMachineVersion
        ),
        source_phase=str(source_phase),
        notes=tuple(notes),
    )


def _derive_score_inputs_from_state(
    *,
    candidate_stage: CandidateStageAssessment,
    market_regime: MarketRegimeAssessment,
    radar_score: float,
) -> dict[str, float]:
    """Derive default score inputs from the cheap classifier outputs.

    The mapping is intentionally conservative so a fresh candidate
    starts in the C-grade band unless the caller supplies richer
    score inputs.

      - momentum_strength : scaled radar_score (0..100)
      - volume_expansion  : scaled radar_score * 0.6
      - liquidity_quality : 50.0 fixed (Phase 11C.1B has no Liquidity
                            Filter on the seam yet; the value lands
                            mid-band).
      - regime_fit        : 100 * regime confidence, capped 50 when
                            regime is observe-only.
      - freshness         : 100 * candidate_stage.freshness
      - manipulation_risk : 0 when stage is early/mid; rises with
                            blowoff_risk for late/blowoff/dumped.
      - late_chase_risk   : 100 * candidate_stage.late_chase_risk
    """
    score_pct = max(0.0, min(100.0, float(radar_score)))
    momentum = score_pct
    volume = max(0.0, min(100.0, score_pct * 0.6))
    liquidity = 50.0
    regime_confidence = max(0.0, min(1.0, float(market_regime.confidence)))
    if "follow" in market_regime.allowed_strategy_modes:
        regime_fit = 100.0 * regime_confidence
    else:
        regime_fit = min(50.0, 100.0 * regime_confidence)
    freshness = 100.0 * float(candidate_stage.freshness)
    blowoff = float(candidate_stage.blowoff_risk)
    if candidate_stage.stage in {"blowoff", "late", "dumped"}:
        manipulation = max(0.0, min(100.0, 60.0 * blowoff + 20.0))
    else:
        manipulation = max(0.0, min(100.0, 30.0 * blowoff))
    late_chase = 100.0 * float(candidate_stage.late_chase_risk)
    return {
        "momentum_strength": momentum,
        "volume_expansion": volume,
        "liquidity_quality": liquidity,
        "regime_fit": regime_fit,
        "freshness": freshness,
        "manipulation_risk": manipulation,
        "late_chase_risk": late_chase,
    }


__all__ = [
    "ADAPTIVE_LEARNING_READY_KEY",
    "AdaptiveScoringVersion",
    "AdaptiveStateMachineVersion",
    "AdaptiveStrategyVersion",
    "build_adaptive_candidate_context",
]
