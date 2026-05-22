"""Phase 11C.1C-A - Adaptive candidate / regime / strategy data contracts.

Each class below is a frozen Pydantic v2 value object so the payload
shape is JSON-stable across processes and Phase 8.5 export +
Phase 10A replay can round-trip it without ambiguity.

Phase 11C.1C-A boundary
-----------------------

  - The ``strategy_mode`` field is a **paper / virtual** field.
    Selecting ``follow`` does NOT authorise opening a position; it
    only records what the strategy expression *would* be if every
    other Phase 1-11C invariant agreed. The Risk Engine remains
    the single trade-decision gate.
  - The ``label_queue`` is a *queue*, not a runner. It records the
    tracking windows the future MFE / MAE / Tail-label processor
    will consume; Phase 11C.1C-A does NOT implement that processor.
  - The cluster context records peer information; it does NOT
    aggregate position size and does NOT trigger any cross-symbol
    co-execution.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

#: Canonical bucket names for :attr:`MarketRegimeAssessment.regime_name`.
#: ``NEUTRAL`` is the safe default the cheap WS-only classifier returns
#: when there is not enough information to decide. ``RISK_OFF`` /
#: ``NO_TRADE`` are the explicit blocking buckets.
REGIME_BUCKETS: tuple[str, ...] = (
    "MEME_RISK_ON",
    "SECTOR_ROTATION",
    "BTC_ABSORPTION",
    "ALT_RISK_OFF",
    "SYSTEMIC_RISK",
    "RISK_OFF",
    "NO_TRADE",
    "NEUTRAL",
)

#: Canonical candidate-stage labels.
CANDIDATE_STAGES: tuple[str, ...] = (
    "early",
    "mid",
    "late",
    "blowoff",
    "dumped",
)

#: Strategy expression labels. ``reject`` is the explicit no-trade
#: case (paper / virtual; the Risk Engine still evaluates).
STRATEGY_MODES: tuple[str, ...] = (
    "follow",
    "pullback",
    "observe",
    "reject",
)

#: Canonical grade letters in S > A > B > C order.
OPPORTUNITY_GRADES: tuple[str, ...] = ("S", "A", "B", "C")

#: Lower-bound score for each grade. Scores in ``[80, 100]`` -> S;
#: ``[65, 80)`` -> A; ``[50, 65)`` -> B; ``< 50`` -> C.
OPPORTUNITY_GRADE_BOUNDARIES: dict[str, float] = {
    "S": 80.0,
    "A": 65.0,
    "B": 50.0,
    "C": 0.0,
}


# ---------------------------------------------------------------------------
# Market regime assessment
# ---------------------------------------------------------------------------
class MarketRegimeAssessment(BaseModel):
    """Macro-cycle assessment + per-tier risk multiplier.

    Phase 11C.1C-A ships a cheap, deterministic classifier
    (:func:`app.adaptive.regime.assess_market_regime`) that derives
    the bucket from the WS-radar liquidation pulse, the per-batch
    volume rank distribution, and the average price acceleration.
    The classifier is descriptive only - no trade authority.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    regime_name: str = Field(default="NEUTRAL")
    confidence: float = 0.0
    risk_multiplier: float = 1.0
    allowed_strategy_modes: tuple[str, ...] = Field(default_factory=tuple)
    no_trade_reason: tuple[str, ...] = Field(default_factory=tuple)
    notes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("regime_name")
    @classmethod
    def _check_regime(cls, value: str) -> str:
        text = str(value).strip()
        if text not in REGIME_BUCKETS:
            raise ValueError(
                f"regime_name must be one of {REGIME_BUCKETS}; got {value!r}"
            )
        return text

    @field_validator("confidence")
    @classmethod
    def _check_confidence(cls, value: float) -> float:
        v = float(value)
        if not (0.0 <= v <= 1.0):
            raise ValueError(
                f"confidence must be in [0.0, 1.0]; got {value}"
            )
        return v

    @field_validator("risk_multiplier")
    @classmethod
    def _check_risk_multiplier(cls, value: float) -> float:
        v = float(value)
        if not (0.0 <= v <= 1.5):
            raise ValueError(
                f"risk_multiplier must be in [0.0, 1.5]; got {value}"
            )
        return v

    @field_validator("allowed_strategy_modes")
    @classmethod
    def _check_allowed_modes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        out: list[str] = []
        seen: set[str] = set()
        for entry in value:
            text = str(entry).strip()
            if text not in STRATEGY_MODES:
                raise ValueError(
                    f"allowed_strategy_modes must be from {STRATEGY_MODES}; "
                    f"got {entry!r}"
                )
            if text not in seen:
                seen.add(text)
                out.append(text)
        return tuple(out)

    def to_payload(self) -> dict[str, Any]:
        return market_regime_assessment_to_payload(self)


def market_regime_assessment_to_payload(
    assessment: MarketRegimeAssessment,
) -> dict[str, Any]:
    return {
        "regime_name": str(assessment.regime_name),
        "confidence": float(assessment.confidence),
        "risk_multiplier": float(assessment.risk_multiplier),
        "allowed_strategy_modes": list(assessment.allowed_strategy_modes),
        "no_trade_reason": list(assessment.no_trade_reason),
        "notes": list(assessment.notes),
    }


# ---------------------------------------------------------------------------
# Candidate stage assessment
# ---------------------------------------------------------------------------
class CandidateStageAssessment(BaseModel):
    """Where the candidate sits in its life cycle.

    The ``stage`` label is one of :data:`CANDIDATE_STAGES`. The other
    fields surface the supporting numerics so Reflection (future
    Phase 11C.1C+ work) can audit the classifier without
    re-deriving them.

    ``freshness`` is in ``[0.0, 1.0]`` where ``1.0`` means "first
    seen this batch" and decays with elapsed wall time. ``late_chase_risk``
    and ``blowoff_risk`` are independent ``[0.0, 1.0]`` risk scores
    (a candidate may carry both).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: str = Field(default="early")
    freshness: float = 0.0
    late_chase_risk: float = 0.0
    blowoff_risk: float = 0.0
    first_seen_ts: int = 0
    first_seen_price: float = 0.0
    current_price: float = 0.0
    distance_from_first_seen: float = 0.0
    distance_to_24h_high: float = 0.0
    reason_tags: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("stage")
    @classmethod
    def _check_stage(cls, value: str) -> str:
        text = str(value).strip()
        if text not in CANDIDATE_STAGES:
            raise ValueError(
                f"stage must be one of {CANDIDATE_STAGES}; got {value!r}"
            )
        return text

    @field_validator("freshness", "late_chase_risk", "blowoff_risk")
    @classmethod
    def _check_unit_range(cls, value: float) -> float:
        v = float(value)
        if not (0.0 <= v <= 1.0):
            raise ValueError(
                f"value must be in [0.0, 1.0]; got {value}"
            )
        return v

    def to_payload(self) -> dict[str, Any]:
        return candidate_stage_assessment_to_payload(self)


def candidate_stage_assessment_to_payload(
    assessment: CandidateStageAssessment,
) -> dict[str, Any]:
    return {
        "stage": str(assessment.stage),
        "freshness": float(assessment.freshness),
        "late_chase_risk": float(assessment.late_chase_risk),
        "blowoff_risk": float(assessment.blowoff_risk),
        "first_seen_ts": int(assessment.first_seen_ts),
        "first_seen_price": float(assessment.first_seen_price),
        "current_price": float(assessment.current_price),
        "distance_from_first_seen": float(assessment.distance_from_first_seen),
        "distance_to_24h_high": float(assessment.distance_to_24h_high),
        "reason_tags": list(assessment.reason_tags),
    }


# ---------------------------------------------------------------------------
# Opportunity score
# ---------------------------------------------------------------------------
class OpportunityScore(BaseModel):
    """Weighted-sum opportunity score + S / A / B / C grade.

    The formula is:

        score = (
            0.25 * momentum_strength
          + 0.20 * volume_expansion
          + 0.15 * liquidity_quality
          + 0.15 * regime_fit
          + 0.15 * freshness
          - 0.20 * manipulation_risk
          - 0.20 * late_chase_risk
        )

    All inputs are in ``[0.0, 100.0]``; the score is clipped to
    ``[0.0, 100.0]``. Grade boundaries: S >= 80, A in [65, 80),
    B in [50, 65), C < 50.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    momentum_strength: float = 0.0
    volume_expansion: float = 0.0
    liquidity_quality: float = 0.0
    regime_fit: float = 0.0
    freshness: float = 0.0
    manipulation_risk: float = 0.0
    late_chase_risk: float = 0.0
    score: float = 0.0
    grade: str = "C"
    reason_tags: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator(
        "momentum_strength",
        "volume_expansion",
        "liquidity_quality",
        "regime_fit",
        "freshness",
        "manipulation_risk",
        "late_chase_risk",
    )
    @classmethod
    def _check_input(cls, value: float) -> float:
        v = float(value)
        if not (0.0 <= v <= 100.0):
            raise ValueError(
                f"opportunity-score input must be in [0.0, 100.0]; "
                f"got {value}"
            )
        return v

    @field_validator("score")
    @classmethod
    def _check_score(cls, value: float) -> float:
        v = float(value)
        if not (0.0 <= v <= 100.0):
            raise ValueError(
                f"score must be in [0.0, 100.0]; got {value}"
            )
        return v

    @field_validator("grade")
    @classmethod
    def _check_grade(cls, value: str) -> str:
        text = str(value).strip().upper()
        if text not in OPPORTUNITY_GRADES:
            raise ValueError(
                f"grade must be one of {OPPORTUNITY_GRADES}; got {value!r}"
            )
        return text

    def to_payload(self) -> dict[str, Any]:
        return opportunity_score_to_payload(self)


def opportunity_score_to_payload(score: OpportunityScore) -> dict[str, Any]:
    return {
        "momentum_strength": float(score.momentum_strength),
        "volume_expansion": float(score.volume_expansion),
        "liquidity_quality": float(score.liquidity_quality),
        "regime_fit": float(score.regime_fit),
        "freshness": float(score.freshness),
        "manipulation_risk": float(score.manipulation_risk),
        "late_chase_risk": float(score.late_chase_risk),
        "score": float(score.score),
        "grade": str(score.grade),
        "reason_tags": list(score.reason_tags),
    }


# ---------------------------------------------------------------------------
# Strategy mode decision
# ---------------------------------------------------------------------------
class StrategyModeDecision(BaseModel):
    """Paper / virtual strategy expression for one candidate.

    The :attr:`mode` is one of :data:`STRATEGY_MODES`. Only ``reject``
    explicitly forbids a paper plan; every other value is descriptive
    (the Risk Engine still evaluates and may refuse).

    The four allow-flags (``follow_allowed`` / ``pullback_allowed`` /
    ``observe_only`` / ``reject_reason``) are the **lever** the Risk
    Engine + future Strategy Validator will consume to gate the
    paper plan.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: str = "observe"
    follow_allowed: bool = False
    pullback_allowed: bool = False
    observe_only: bool = True
    reject_reason: str | None = None
    reason_tags: tuple[str, ...] = Field(default_factory=tuple)
    notes: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("mode")
    @classmethod
    def _check_mode(cls, value: str) -> str:
        text = str(value).strip()
        if text not in STRATEGY_MODES:
            raise ValueError(
                f"mode must be one of {STRATEGY_MODES}; got {value!r}"
            )
        return text

    def to_payload(self) -> dict[str, Any]:
        return strategy_mode_decision_to_payload(self)


def strategy_mode_decision_to_payload(
    decision: StrategyModeDecision,
) -> dict[str, Any]:
    return {
        "mode": str(decision.mode),
        "follow_allowed": bool(decision.follow_allowed),
        "pullback_allowed": bool(decision.pullback_allowed),
        "observe_only": bool(decision.observe_only),
        "reject_reason": (
            str(decision.reject_reason)
            if decision.reject_reason is not None
            else None
        ),
        "reason_tags": list(decision.reason_tags),
        "notes": list(decision.notes),
    }


# ---------------------------------------------------------------------------
# Cluster context
# ---------------------------------------------------------------------------
class ClusterContext(BaseModel):
    """Peer-cluster context for one candidate.

    Phase 11C.1C-A ships the *contract* only - the cheap classifier
    in :func:`app.adaptive.cluster.build_cluster_context` groups
    candidates by quote asset (e.g. every ``*USDT`` symbol is in
    cluster ``"USDT"``) so the Phase 11C.1B WS-radar always has a
    valid value to attach. Smarter cluster classification (sector /
    narrative / leader detection) is reserved for a later PR; this
    PR pins the field set so the daily-report and export contracts
    do not need re-shaping when that work lands.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    cluster_id: str = "unknown"
    cluster_leader: str | None = None
    cluster_rank: int = 0
    cluster_size: int = 0
    cluster_reason: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("cluster_rank")
    @classmethod
    def _check_rank(cls, value: int) -> int:
        v = int(value)
        if v < 0:
            raise ValueError(f"cluster_rank must be >= 0; got {value}")
        return v

    @field_validator("cluster_size")
    @classmethod
    def _check_size(cls, value: int) -> int:
        v = int(value)
        if v < 0:
            raise ValueError(f"cluster_size must be >= 0; got {value}")
        return v

    def to_payload(self) -> dict[str, Any]:
        return cluster_context_to_payload(self)


def cluster_context_to_payload(cluster: ClusterContext) -> dict[str, Any]:
    return {
        "cluster_id": str(cluster.cluster_id),
        "cluster_leader": (
            str(cluster.cluster_leader)
            if cluster.cluster_leader is not None
            else None
        ),
        "cluster_rank": int(cluster.cluster_rank),
        "cluster_size": int(cluster.cluster_size),
        "cluster_reason": list(cluster.cluster_reason),
    }


# ---------------------------------------------------------------------------
# Label queue contract
# ---------------------------------------------------------------------------
class LabelQueueContract(BaseModel):
    """Future MFE / MAE / Tail label queue for one candidate.

    Phase 11C.1C-A does NOT implement the MFE/MAE processor. The
    contract below is purely descriptive: it records the candidate's
    identity + the tracking windows the future processor must
    evaluate. ``mfe_mae_label_pending`` and ``future_tail_label_pending``
    both default to ``True`` because no labels have been produced
    yet.

    ``tracking_windows`` is a tuple of human-readable window labels
    (``"5m"`` / ``"15m"`` / ``"30m"`` / ``"1h"`` / ``"4h"``).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_id: str
    scan_batch_id: str
    symbol: str
    enqueued_at_ms: int = 0
    mfe_mae_label_pending: bool = True
    future_tail_label_pending: bool = True
    tracking_windows: tuple[str, ...] = Field(default_factory=tuple)
    reference_price: float = 0.0
    notes: tuple[str, ...] = Field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return label_queue_contract_to_payload(self)


def label_queue_contract_to_payload(
    contract: LabelQueueContract,
) -> dict[str, Any]:
    return {
        "opportunity_id": str(contract.opportunity_id),
        "scan_batch_id": str(contract.scan_batch_id),
        "symbol": str(contract.symbol),
        "enqueued_at_ms": int(contract.enqueued_at_ms),
        "mfe_mae_label_pending": bool(contract.mfe_mae_label_pending),
        "future_tail_label_pending": bool(contract.future_tail_label_pending),
        "tracking_windows": list(contract.tracking_windows),
        "reference_price": float(contract.reference_price),
        "notes": list(contract.notes),
    }


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------
class AdaptiveCandidateContext(BaseModel):
    """Bundle every Phase 11C.1C-A sub-block for one candidate.

    The Phase 11C.1B WS-radar event-chain driver builds one of these
    per ACTIVE candidate, attaches it to the Phase 8.5
    :class:`LearningReadyContext` (under the ``adaptive_candidate``
    block), and emits the six new typed events
    (``MARKET_REGIME_ASSESSED`` / ``CANDIDATE_STAGE_CLASSIFIED`` /
    ``OPPORTUNITY_SCORED`` / ``STRATEGY_MODE_SELECTED`` /
    ``CLUSTER_CONTEXT_ATTACHED`` / ``LABEL_QUEUE_ENQUEUED``) carrying
    the corresponding sub-block.

    Every ``...version`` field is recorded on every event payload so
    Reflection can group by (strategy_version, scoring_version,
    state_machine_version) without parsing free-form audit dicts.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    opportunity_id: str
    scan_batch_id: str
    symbol: str
    timestamp_ms: int = 0
    market_regime: MarketRegimeAssessment
    candidate_stage: CandidateStageAssessment
    opportunity_score: OpportunityScore
    strategy_mode: StrategyModeDecision
    cluster: ClusterContext
    label_queue: LabelQueueContract
    strategy_version: str
    scoring_version: str
    risk_config_version: str
    state_machine_version: str
    source_phase: str = "phase_11c_1c_a_adaptive_candidate"
    notes: tuple[str, ...] = Field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return {
            "opportunity_id": str(self.opportunity_id),
            "scan_batch_id": str(self.scan_batch_id),
            "symbol": str(self.symbol),
            "timestamp_ms": int(self.timestamp_ms),
            "market_regime": self.market_regime.to_payload(),
            "candidate_stage": self.candidate_stage.to_payload(),
            "opportunity_score": self.opportunity_score.to_payload(),
            "strategy_mode": self.strategy_mode.to_payload(),
            "cluster": self.cluster.to_payload(),
            "label_queue": self.label_queue.to_payload(),
            "strategy_version": str(self.strategy_version),
            "scoring_version": str(self.scoring_version),
            "risk_config_version": str(self.risk_config_version),
            "state_machine_version": str(self.state_machine_version),
            "source_phase": str(self.source_phase),
            "notes": list(self.notes),
        }


__all__ = [
    "REGIME_BUCKETS",
    "CANDIDATE_STAGES",
    "STRATEGY_MODES",
    "OPPORTUNITY_GRADES",
    "OPPORTUNITY_GRADE_BOUNDARIES",
    "MarketRegimeAssessment",
    "CandidateStageAssessment",
    "OpportunityScore",
    "StrategyModeDecision",
    "ClusterContext",
    "LabelQueueContract",
    "AdaptiveCandidateContext",
    "candidate_stage_assessment_to_payload",
    "cluster_context_to_payload",
    "label_queue_contract_to_payload",
    "market_regime_assessment_to_payload",
    "opportunity_score_to_payload",
    "strategy_mode_decision_to_payload",
]
