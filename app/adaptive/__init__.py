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
from app.adaptive.strategy_validation import (
    CLUSTER_ACTIONS,
    DEFAULT_OVEREXPOSURE_WARNING_THRESHOLD,
    EARLY_TAIL_SCORE_BUCKETS,
    EARLY_TAIL_SCORE_BUCKET_LABELS,
    KNOWN_STRATEGY_VALIDATION_SCHEMA_VERSIONS,
    OPPORTUNITY_SCORE_BUCKETS,
    OPPORTUNITY_SCORE_BUCKET_LABELS,
    STRATEGY_VALIDATION_PRIMARY_WINDOW,
    STRATEGY_VALIDATION_SCHEMA_VERSION,
    STRATEGY_VALIDATION_SOURCE_PHASE,
    STRATEGY_VALIDATION_TRACKING_WINDOWS,
    STRATEGY_VALIDATION_VERSION,
    CandidateStageValidationStats,
    ClusterExposureAssessment,
    ClusterLeaderValidationStats,
    EarlyTailScoreBucketStats,
    OpportunityScoreBucketStats,
    StrategyModeValidationStats,
    StrategyValidationReport,
    StrategyValidationSample,
    StrategyValidationWindowStats,
    TailLabelDistribution,
    aggregate_by_candidate_stage,
    aggregate_by_early_tail_score_bucket,
    aggregate_by_opportunity_score_bucket,
    aggregate_by_strategy_mode,
    aggregate_tail_label_distribution,
    assess_cluster_exposure,
    build_strategy_validation_report,
    build_strategy_validation_sample,
    early_tail_score_bucket_for,
    evaluate_cluster_leader_performance,
    opportunity_score_bucket_for,
)
from app.adaptive.strategy_validation_runtime import (
    StrategyValidationRuntime,
    StrategyValidationRuntimeConfig,
)
from app.adaptive.strategy_validation_dataset import (
    CANONICAL_CANDIDATE_STAGES,
    CANONICAL_STRATEGY_MODES,
    COMPLETED_TAIL_LABELS,
    KNOWN_STRATEGY_VALIDATION_DATASET_SCHEMA_VERSIONS,
    QUALITY_GATE_STATUSES,
    REQUIRED_DATASET_RECORD_FIELDS,
    STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION,
    STRATEGY_VALIDATION_DATASET_SOURCE_PHASE,
    STRATEGY_VALIDATION_DATASET_VERSION,
    StrategyValidationDataset,
    StrategyValidationDatasetRecord,
    StrategyValidationDatasetSummary,
    StrategyValidationQualityGate,
    StrategyValidationQualityGateResult,
    build_validation_dataset_from_samples,
    evaluate_validation_dataset_quality,
    export_validation_dataset_payload,
    load_validation_dataset_payload,
    summarize_validation_dataset,
)

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
    # Phase 11C.1C-C-B-A Strategy Validation Lab v0 + Cluster
    # Exposure Control Contracts
    "STRATEGY_VALIDATION_SCHEMA_VERSION",
    "STRATEGY_VALIDATION_VERSION",
    "STRATEGY_VALIDATION_SOURCE_PHASE",
    "STRATEGY_VALIDATION_PRIMARY_WINDOW",
    "STRATEGY_VALIDATION_TRACKING_WINDOWS",
    "KNOWN_STRATEGY_VALIDATION_SCHEMA_VERSIONS",
    "OPPORTUNITY_SCORE_BUCKETS",
    "OPPORTUNITY_SCORE_BUCKET_LABELS",
    "EARLY_TAIL_SCORE_BUCKETS",
    "EARLY_TAIL_SCORE_BUCKET_LABELS",
    "CLUSTER_ACTIONS",
    "DEFAULT_OVEREXPOSURE_WARNING_THRESHOLD",
    "StrategyValidationSample",
    "StrategyValidationWindowStats",
    "StrategyModeValidationStats",
    "CandidateStageValidationStats",
    "OpportunityScoreBucketStats",
    "EarlyTailScoreBucketStats",
    "TailLabelDistribution",
    "ClusterLeaderValidationStats",
    "ClusterExposureAssessment",
    "StrategyValidationReport",
    "build_strategy_validation_sample",
    "aggregate_by_strategy_mode",
    "aggregate_by_candidate_stage",
    "aggregate_by_opportunity_score_bucket",
    "aggregate_by_early_tail_score_bucket",
    "aggregate_tail_label_distribution",
    "evaluate_cluster_leader_performance",
    "assess_cluster_exposure",
    "build_strategy_validation_report",
    "opportunity_score_bucket_for",
    "early_tail_score_bucket_for",
    "StrategyValidationRuntime",
    "StrategyValidationRuntimeConfig",
    # Phase 11C.1C-C-B-B-A Strategy Validation Dataset Builder &
    # Quality Gate v0
    "STRATEGY_VALIDATION_DATASET_SCHEMA_VERSION",
    "STRATEGY_VALIDATION_DATASET_VERSION",
    "STRATEGY_VALIDATION_DATASET_SOURCE_PHASE",
    "KNOWN_STRATEGY_VALIDATION_DATASET_SCHEMA_VERSIONS",
    "QUALITY_GATE_STATUSES",
    "CANONICAL_STRATEGY_MODES",
    "CANONICAL_CANDIDATE_STAGES",
    "COMPLETED_TAIL_LABELS",
    "REQUIRED_DATASET_RECORD_FIELDS",
    "StrategyValidationDatasetRecord",
    "StrategyValidationDatasetSummary",
    "StrategyValidationDataset",
    "StrategyValidationQualityGate",
    "StrategyValidationQualityGateResult",
    "build_validation_dataset_from_samples",
    "summarize_validation_dataset",
    "evaluate_validation_dataset_quality",
    "export_validation_dataset_payload",
    "load_validation_dataset_payload",
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
