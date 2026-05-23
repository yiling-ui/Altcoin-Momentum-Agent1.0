"""Phase 11C.1C-A - Adaptive Candidate Regime & Strategy Selector contracts.

This package ships the *first version* of the data contracts the
Phase 11C.1B WebSocket-first all-market radar consumes to:

  - assess the current market regime
  - classify a candidate's life-cycle stage
    (early / mid / late / blowoff / dumped)
  - score a candidate opportunity (S / A / B / C)
  - choose a paper-only strategy expression
    (follow / pullback / observe / reject)
  - record a cluster context (peer leader, peer rank)
  - enqueue future MFE / MAE / Tail-label tracking windows

Phase 11C.1C-A boundary
-----------------------

Every object in this package is a frozen value object or a pure
function. Nothing here:

  - opens a socket
  - imports an exchange SDK / LLM client / Telegram library
  - reads ``os.environ`` for credentials
  - mutates global state
  - calls ``EventRepository.append_event`` directly
  - constructs a real :class:`OrderRequest` / :class:`OrderIntent`
  - flips a Phase 1 safety flag
  - implements a full MFE / MAE processor (the contract is a
    *queue*, not a runner)
  - implements AI Learning (the contract is a *paper plan*, not
    a trade authority)
  - opens a path into Phase 12

The strategy_mode decision below is a **paper / virtual** field.
It records what the strategy expression *would* be if (and only if)
every Phase 1-11C invariant agrees. It does NOT and CANNOT trigger
a real trade; the Risk Engine remains the single trade-decision
gate.

Public surface
--------------

    MarketRegimeAssessment        macro-cycle assessment + risk multiplier
    CandidateStageAssessment      early / mid / late / blowoff / dumped
    OpportunityScore              weighted-sum score + S/A/B/C grade
    StrategyModeDecision          follow / pullback / observe / reject
    ClusterContext                cluster_id + leader + rank
    LabelQueueContract            future MFE/MAE/Tail label queue
    AdaptiveCandidateContext      aggregator bundle for one candidate

    AdaptiveStrategyVersion       canonical version label for this PR
    AdaptiveScoringVersion        scoring-formula version label
    AdaptiveStateMachineVersion   adaptive-state-machine version label

    assess_market_regime          cheap deterministic regime classifier
    classify_candidate_stage      stage classifier (5 buckets)
    compute_opportunity_score     score + grade
    select_strategy_mode          follow / pullback / observe / reject
    build_cluster_context         peer-cluster builder
    build_label_queue_contract    label-queue contract builder
    build_adaptive_candidate_context  one-shot orchestrator

The :func:`build_adaptive_candidate_context` helper is the single
entry point the Phase 11C.1B WS-radar event-chain driver calls per
ACTIVE candidate.
"""

from app.adaptive.cluster import build_cluster_context
from app.adaptive.context import (
    ADAPTIVE_LEARNING_READY_KEY,
    AdaptiveScoringVersion,
    AdaptiveStateMachineVersion,
    AdaptiveStrategyVersion,
    build_adaptive_candidate_context,
)
from app.adaptive.label_queue import (
    DEFAULT_TRACKING_WINDOWS,
    build_label_queue_contract,
)
from app.adaptive.label_runtime import (
    DEFAULT_PRIMARY_WINDOW,
    DEFAULT_TRACKING_WINDOW_SECONDS,
    KNOWN_LABEL_TRACKING_SCHEMA_VERSIONS,
    LABEL_TRACKING_SCHEMA_VERSION,
    LABEL_TRACKING_STATUSES,
    LabelQueueRuntime,
    LabelQueueRuntimeConfig,
    LabelTrackingRecord,
    TAIL_LABELS,
    TrackingWindowState,
    assign_tail_label_for_window,
    compute_pct_return,
    update_window_with_price,
)
from app.adaptive.models import (
    AdaptiveCandidateContext,
    CANDIDATE_STAGES,
    CandidateStageAssessment,
    ClusterContext,
    LabelQueueContract,
    MarketRegimeAssessment,
    OPPORTUNITY_GRADES,
    OPPORTUNITY_GRADE_BOUNDARIES,
    OpportunityScore,
    REGIME_BUCKETS,
    RuntimeCalibrationMetrics,
    STRATEGY_MODES,
    StrategyModeDecision,
    candidate_stage_assessment_to_payload,
    cluster_context_to_payload,
    label_queue_contract_to_payload,
    market_regime_assessment_to_payload,
    opportunity_score_to_payload,
    runtime_calibration_metrics_to_payload,
    strategy_mode_decision_to_payload,
)
from app.adaptive.regime import assess_market_regime
from app.adaptive.runtime import (
    DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD,
    DEFAULT_FRESHNESS_HALF_LIFE_MS,
    compute_early_tail_score,
    compute_freshness_score,
    compute_late_chase_risk_score,
    compute_relative_acceleration,
    compute_runtime_calibration,
)
from app.adaptive.scoring import (
    DEFAULT_OPPORTUNITY_SCORE_WEIGHTS,
    OpportunityScoreInputs,
    OpportunityScoreWeights,
    compute_opportunity_score,
    grade_for_score,
)
from app.adaptive.selector import select_strategy_mode
from app.adaptive.stage import classify_candidate_stage

__all__ = [
    # Models / value objects
    "MarketRegimeAssessment",
    "CandidateStageAssessment",
    "OpportunityScore",
    "StrategyModeDecision",
    "ClusterContext",
    "LabelQueueContract",
    "RuntimeCalibrationMetrics",
    "AdaptiveCandidateContext",
    # Constants
    "ADAPTIVE_LEARNING_READY_KEY",
    "CANDIDATE_STAGES",
    "DEFAULT_EARLY_TAIL_PROTECT_THRESHOLD",
    "DEFAULT_FRESHNESS_HALF_LIFE_MS",
    "DEFAULT_TRACKING_WINDOWS",
    "DEFAULT_PRIMARY_WINDOW",
    "DEFAULT_TRACKING_WINDOW_SECONDS",
    "KNOWN_LABEL_TRACKING_SCHEMA_VERSIONS",
    "LABEL_TRACKING_SCHEMA_VERSION",
    "LABEL_TRACKING_STATUSES",
    "TAIL_LABELS",
    "OPPORTUNITY_GRADES",
    "OPPORTUNITY_GRADE_BOUNDARIES",
    "REGIME_BUCKETS",
    "STRATEGY_MODES",
    # Versions
    "AdaptiveStrategyVersion",
    "AdaptiveScoringVersion",
    "AdaptiveStateMachineVersion",
    # Pure functions
    "assess_market_regime",
    "classify_candidate_stage",
    "compute_opportunity_score",
    "compute_early_tail_score",
    "compute_freshness_score",
    "compute_late_chase_risk_score",
    "compute_relative_acceleration",
    "compute_runtime_calibration",
    "grade_for_score",
    "select_strategy_mode",
    "build_cluster_context",
    "build_label_queue_contract",
    "build_adaptive_candidate_context",
    # Phase 11C.1C-C-A label-tracking runtime
    "LabelQueueRuntime",
    "LabelQueueRuntimeConfig",
    "LabelTrackingRecord",
    "TrackingWindowState",
    "assign_tail_label_for_window",
    "compute_pct_return",
    "update_window_with_price",
    # Payload helpers
    "candidate_stage_assessment_to_payload",
    "cluster_context_to_payload",
    "label_queue_contract_to_payload",
    "market_regime_assessment_to_payload",
    "opportunity_score_to_payload",
    "runtime_calibration_metrics_to_payload",
    "strategy_mode_decision_to_payload",
    # Scoring helpers
    "OpportunityScoreInputs",
    "OpportunityScoreWeights",
    "DEFAULT_OPPORTUNITY_SCORE_WEIGHTS",
]
