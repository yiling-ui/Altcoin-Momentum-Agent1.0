"""Paper Shadow Strategy Validation v0 (Phase 11C.1D-B).

A strictly paper-only, deterministic cohort-evaluation engine that takes
structured Block B / Block C / Offline Rule Sandbox Replay outputs and
rolls them up into ``PaperShadowSample`` rows, groups those rows into
cohorts, computes cohort-level metrics, and emits a paper shadow
validation report. The report tells the operator which discovery
patterns / regime-cluster cohorts look structurally promising, which
look like noise / late chase / fake breakout / data gap, and which are
RISKY or REJECTED_BY_EVIDENCE on the historical record.

This module exists to safely answer questions such as:

    * Does the "trend regime, leader, EARLY detection, high
      discovery quality" cohort actually leave usable upside on
      paper?
    * Does the "range regime, follower, LATE detection" cohort
      collapse into late chase / fake breakout?
    * Does the "early-tail-score-bucket high, severe-miss
      root-cause early_tail_score_too_high" cohort show usable
      remaining MFE on paper, or is it data-gap-dominated?

================================================================
HARD SAFETY BOUNDARY (Phase 11C.1D-B / Paper Shadow Strategy
Validation v0)
================================================================

  mode                         = paper
  sandbox_only                 = True
  writes_runtime_config        = False
  auto_tuning_allowed          = False
  trade_authority              = False
  live_trading                 = False
  exchange_live_orders         = False
  right_tail                   = False
  llm                          = False
  llm_outbound_enabled         = False
  telegram_outbound_enabled    = False
  binance_private_api_enabled  = False
  phase_12_forbidden           = True

This module MUST NOT:
  * import app.risk / app.execution / app.exchanges / app.telegram /
    app.config
  * write back to runtime config
  * generate runtime_config_patch / threshold_patch /
    symbol_limit_patch / candidate_pool_patch / regime_weight_patch /
    strategy_parameter_patch
  * emit buy / sell / long / short / direction / entry / exit
  * emit position_size / leverage / stop / target / risk_budget
  * authorize live trading or hot-path execution
  * call DeepSeek / LLM / network
  * enter Phase 12

A ``PaperShadowSample`` is a *retrospective evidence row*, not a trade.
A ``PaperShadowCohortEvaluation`` is a *descriptive verdict on a cohort
of evidence rows*, not a trading signal. A
``PaperShadowStrategyValidationReport`` is *commentary substrate that
an auditor can review*, not an authorization for live trading,
auto-tuning, or Phase 12.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Phase / module identity
# ---------------------------------------------------------------------------

PHASE_NAME: str = "Phase 11C.1D-B / Paper Shadow Strategy Validation v0"

# next_allowed_phase after a successful paper shadow validation run is
# *only* preparation for the Risk / Execution / Capital Safety Matrix
# work or strict walk-forward preparation. It is NEVER live trading and
# NEVER Phase 12.
NEXT_ALLOWED_PHASE: str = (
    "Risk / Execution / Capital Safety Matrix preparation "
    "or strict walk-forward preparation (paper / read-only)"
)


# ---------------------------------------------------------------------------
# Allowed event types (report / export / replay scope only)
# ---------------------------------------------------------------------------


class PaperShadowEvent:
    """Allowed event types. Strictly report / export / replay scope.

    No trade-action events are defined and none must be added in this
    phase.
    """

    PAPER_SHADOW_SAMPLE_CREATED: str = "PAPER_SHADOW_SAMPLE_CREATED"
    PAPER_SHADOW_COHORT_EVALUATED: str = "PAPER_SHADOW_COHORT_EVALUATED"
    PAPER_SHADOW_REPORT_GENERATED: str = "PAPER_SHADOW_REPORT_GENERATED"

    ALLOWED: frozenset = frozenset(
        {
            PAPER_SHADOW_SAMPLE_CREATED,
            PAPER_SHADOW_COHORT_EVALUATED,
            PAPER_SHADOW_REPORT_GENERATED,
        }
    )


# ---------------------------------------------------------------------------
# Recommendation level (closed enum)
# ---------------------------------------------------------------------------


class RecommendationLevel:
    """Allowed recommendation levels emitted by paper shadow validation.

    Note: APPLY / DEPLOY / ENABLE_LIVE / TRADE / BUY / SELL / GO_LIVE /
    AUTO_APPLY are intentionally NOT defined here, and the engine
    refuses to ever emit them.
    """

    REVIEW_ONLY: str = "REVIEW_ONLY"
    PROMISING_FOR_FORWARD_TEST: str = "PROMISING_FOR_FORWARD_TEST"
    INCONCLUSIVE: str = "INCONCLUSIVE"
    RISKY: str = "RISKY"
    REJECTED_BY_EVIDENCE: str = "REJECTED_BY_EVIDENCE"

    ALLOWED: frozenset = frozenset(
        {
            REVIEW_ONLY,
            PROMISING_FOR_FORWARD_TEST,
            INCONCLUSIVE,
            RISKY,
            REJECTED_BY_EVIDENCE,
        }
    )


# ---------------------------------------------------------------------------
# Validation status (closed enum)
# ---------------------------------------------------------------------------


class PaperShadowValidationStatus:
    COMPLETED: str = "COMPLETED"
    INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"
    DATA_GAP: str = "DATA_GAP"


# ---------------------------------------------------------------------------
# Forbidden field names that must NEVER appear in any output payload
# ---------------------------------------------------------------------------


FORBIDDEN_OUTPUT_FIELDS: frozenset = frozenset(
    {
        # Direction / side.
        "buy",
        "sell",
        "long",
        "short",
        "direction",
        # Order plumbing.
        "entry",
        "exit",
        "order",
        "execution_command",
        # Sizing / risk.
        "position_size",
        "leverage",
        "stop",
        "stop_loss",
        "target",
        "take_profit",
        "risk_budget",
        # Runtime tuning patches.
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
        "strategy_parameter_patch",
        # Trade-authority signals.
        "signal_to_trade",
        "should_buy",
        "should_short",
        "apply_change",
        "deploy_change",
        "enable_live",
    }
)


def assert_no_forbidden_fields(payload: Any, _path: str = "$") -> None:
    """Recursively assert that no forbidden field name appears in
    ``payload``.

    Raises ValueError on the first violation. Used as a defensive check
    on every output payload before serialization.
    """
    if isinstance(payload, Mapping):
        for k, v in payload.items():
            if isinstance(k, str) and k in FORBIDDEN_OUTPUT_FIELDS:
                raise ValueError(
                    f"forbidden field {k!r} present at {_path}"
                )
            assert_no_forbidden_fields(v, f"{_path}.{k}")
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            assert_no_forbidden_fields(v, f"{_path}[{i}]")
    # Scalars: nothing to check (the check is on field NAMES, not values).


# ---------------------------------------------------------------------------
# Bucket helpers (deterministic, finite vocabulary)
# ---------------------------------------------------------------------------


def _bucket_score(value: Any) -> str:
    """Deterministic bucket label for a [0, 1] score."""
    if value is None:
        return "unknown"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if v != v:  # NaN
        return "unknown"
    if v < 0.20:
        return "very_low"
    if v < 0.40:
        return "low"
    if v < 0.60:
        return "medium"
    if v < 0.80:
        return "high"
    return "very_high"


def _safe_str(value: Any, *, default: str = "unknown") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        s = value.strip()
        return s if s else default
    return str(value)


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "t"}
    return False


def _safe_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        if f != f:  # NaN
            return None
        return f
    return None


# ---------------------------------------------------------------------------
# PaperShadowCohortKey
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperShadowCohortKey:
    """Cohort key used to group ``PaperShadowSample`` rows.

    All fields are descriptive labels. None of them are inputs to a
    trade-decision pipeline, the Risk Engine, the Execution FSM,
    ``symbol_limit``, candidate-pool capacity, anomaly thresholds, or
    Regime weights.
    """

    market_regime: str = "unknown"
    cluster_id: str = "unknown"
    leader_vs_follower: str = "unknown"
    candidate_stage: str = "unknown"
    strategy_mode: str = "unknown"
    opportunity_score_bucket: str = "unknown"
    early_tail_score_bucket: str = "unknown"
    post_discovery_outcome_label: str = "unknown"
    reject_attribution_verdict: str = "unknown"
    severe_miss_root_cause: str = "unknown"
    discovery_quality_bucket: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_regime": self.market_regime,
            "cluster_id": self.cluster_id,
            "leader_vs_follower": self.leader_vs_follower,
            "candidate_stage": self.candidate_stage,
            "strategy_mode": self.strategy_mode,
            "opportunity_score_bucket": self.opportunity_score_bucket,
            "early_tail_score_bucket": self.early_tail_score_bucket,
            "post_discovery_outcome_label": self.post_discovery_outcome_label,
            "reject_attribution_verdict": self.reject_attribution_verdict,
            "severe_miss_root_cause": self.severe_miss_root_cause,
            "discovery_quality_bucket": self.discovery_quality_bucket,
        }

    def cohort_id(self) -> str:
        """Stable, deterministic cohort id derived from key fields."""
        canonical = json.dumps(self.to_dict(), sort_keys=True)
        h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        return f"cohort_{h}"

    def sort_tuple(self) -> Tuple[str, ...]:
        """Stable sort tuple for deterministic cohort ordering."""
        return (
            self.market_regime,
            self.cluster_id,
            self.leader_vs_follower,
            self.candidate_stage,
            self.strategy_mode,
            self.opportunity_score_bucket,
            self.early_tail_score_bucket,
            self.post_discovery_outcome_label,
            self.reject_attribution_verdict,
            self.severe_miss_root_cause,
            self.discovery_quality_bucket,
        )


# ---------------------------------------------------------------------------
# PaperShadowSample
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperShadowSample:
    """A single retrospective paper-shadow evidence row.

    Built from D-B outcome / severe miss / reject attribution /
    discovery quality / sandbox report inputs. NOT a trade. NOT a
    runtime patch.
    """

    sample_id: str
    symbol: str
    reference_window: str
    first_seen_time_utc: str
    cohort_key: PaperShadowCohortKey
    source_event_refs: Tuple[str, ...] = field(default_factory=tuple)
    post_seen_mfe_pct: Optional[float] = None
    post_seen_mae_pct: Optional[float] = None
    remaining_upside_to_peak_pct: Optional[float] = None
    late_chase: bool = False
    fake_breakout: bool = False
    severe_miss: bool = False
    false_negative_reject: bool = False
    data_gap: bool = False
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    source: str = "operator_supplied"

    def __post_init__(self) -> None:
        if not isinstance(self.sample_id, str) or not self.sample_id:
            raise ValueError("sample_id must be a non-empty string")
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("symbol must be a non-empty string")
        if not isinstance(self.cohort_key, PaperShadowCohortKey):
            raise ValueError(
                "cohort_key must be a PaperShadowCohortKey instance"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "symbol": self.symbol,
            "reference_window": self.reference_window,
            "first_seen_time_utc": self.first_seen_time_utc,
            "cohort_key": self.cohort_key.to_dict(),
            "source_event_refs": list(self.source_event_refs),
            "post_seen_mfe_pct": self.post_seen_mfe_pct,
            "post_seen_mae_pct": self.post_seen_mae_pct,
            "remaining_upside_to_peak_pct": (
                self.remaining_upside_to_peak_pct
            ),
            "late_chase": self.late_chase,
            "fake_breakout": self.fake_breakout,
            "severe_miss": self.severe_miss,
            "false_negative_reject": self.false_negative_reject,
            "data_gap": self.data_gap,
            "evidence_refs": list(self.evidence_refs),
            "source": self.source,
            # Defensive non-trade markers (visible to reviewers):
            "is_paper_shadow_sample": True,
            "is_trade": False,
            "is_runtime_patch": False,
        }


# ---------------------------------------------------------------------------
# PaperShadowCohortEvaluation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperShadowCohortEvaluation:
    """Per-cohort evaluation. Descriptive only."""

    cohort_id: str
    cohort_key: PaperShadowCohortKey
    sample_count: int
    usable_discovery_rate: float
    median_mfe_pct: Optional[float]
    median_mae_pct: Optional[float]
    late_chase_rate: float
    fake_breakout_rate: float
    severe_miss_rate: float
    false_negative_reject_rate: float
    data_gap_rate: float
    confidence_bucket: str
    quality_bucket: str
    recommendation_level: str

    def __post_init__(self) -> None:
        if self.recommendation_level not in RecommendationLevel.ALLOWED:
            raise ValueError(
                f"recommendation_level must be one of "
                f"{sorted(RecommendationLevel.ALLOWED)}, got "
                f"{self.recommendation_level!r}"
            )
        if self.sample_count < 0:
            raise ValueError("sample_count must be >= 0")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cohort_id": self.cohort_id,
            "cohort_key": self.cohort_key.to_dict(),
            "sample_count": self.sample_count,
            "usable_discovery_rate": self.usable_discovery_rate,
            "median_mfe_pct": self.median_mfe_pct,
            "median_mae_pct": self.median_mae_pct,
            "late_chase_rate": self.late_chase_rate,
            "fake_breakout_rate": self.fake_breakout_rate,
            "severe_miss_rate": self.severe_miss_rate,
            "false_negative_reject_rate": self.false_negative_reject_rate,
            "data_gap_rate": self.data_gap_rate,
            "confidence_bucket": self.confidence_bucket,
            "quality_bucket": self.quality_bucket,
            "recommendation_level": self.recommendation_level,
        }


# ---------------------------------------------------------------------------
# PaperShadowStrategyValidationReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperShadowStrategyValidationReport:
    report_id: str
    generated_at_utc: str
    reference_window: str
    total_samples: int
    evaluated_cohort_count: int
    cohort_evaluations: Tuple[PaperShadowCohortEvaluation, ...]
    promising_cohorts: Tuple[str, ...] = field(default_factory=tuple)
    rejected_cohorts: Tuple[str, ...] = field(default_factory=tuple)
    inconclusive_cohorts: Tuple[str, ...] = field(default_factory=tuple)
    risky_cohorts: Tuple[str, ...] = field(default_factory=tuple)
    review_only_cohorts: Tuple[str, ...] = field(default_factory=tuple)
    known_gaps: Tuple[str, ...] = field(default_factory=tuple)
    status: str = PaperShadowValidationStatus.COMPLETED
    # Hard-locked safety flags (always present in serialized payload):
    next_allowed_phase: str = NEXT_ALLOWED_PHASE
    phase: str = PHASE_NAME
    phase_12_forbidden: bool = True
    auto_tuning_allowed: bool = False
    trade_authority: bool = False
    writes_runtime_config: bool = False
    sandbox_only: bool = True
    live_trading: bool = False
    exchange_live_orders: bool = False
    right_tail: bool = False
    llm: bool = False
    llm_outbound_enabled: bool = False
    telegram_outbound_enabled: bool = False
    binance_private_api_enabled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "generated_at_utc": self.generated_at_utc,
            "reference_window": self.reference_window,
            "phase": self.phase,
            "status": self.status,
            "total_samples": self.total_samples,
            "evaluated_cohort_count": self.evaluated_cohort_count,
            "cohort_evaluations": [
                c.to_dict() for c in self.cohort_evaluations
            ],
            "promising_cohorts": list(self.promising_cohorts),
            "rejected_cohorts": list(self.rejected_cohorts),
            "inconclusive_cohorts": list(self.inconclusive_cohorts),
            "risky_cohorts": list(self.risky_cohorts),
            "review_only_cohorts": list(self.review_only_cohorts),
            "known_gaps": list(self.known_gaps),
            "next_allowed_phase": self.next_allowed_phase,
            "phase_12_forbidden": self.phase_12_forbidden,
            "auto_tuning_allowed": self.auto_tuning_allowed,
            "trade_authority": self.trade_authority,
            "writes_runtime_config": self.writes_runtime_config,
            "sandbox_only": self.sandbox_only,
            "live_trading": self.live_trading,
            "exchange_live_orders": self.exchange_live_orders,
            "right_tail": self.right_tail,
            "llm": self.llm,
            "llm_outbound_enabled": self.llm_outbound_enabled,
            "telegram_outbound_enabled": self.telegram_outbound_enabled,
            "binance_private_api_enabled": (
                self.binance_private_api_enabled
            ),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


# Thresholds for cohort-level recommendation classification. Conservative
# by design. NOT runtime-tunable. NOT auto-tuned. NOT exposed to the
# Risk Engine, Execution FSM, ``symbol_limit``, candidate-pool capacity,
# anomaly thresholds, or Regime weights.
_MIN_SAMPLES_FOR_VERDICT: int = 5
_MIN_SAMPLES_FOR_PROMISING: int = 8
_DATA_GAP_RATE_HIGH: float = 0.30
_DATA_GAP_RATE_RISKY: float = 0.50
_USABLE_DISCOVERY_RATE_PROMISING: float = 0.55
_LATE_CHASE_RATE_LOW: float = 0.20
_FAKE_BREAKOUT_RATE_LOW: float = 0.15
_SEVERE_MISS_RATE_LOW: float = 0.15
_SEVERE_MISS_RATE_HIGH: float = 0.30
_FAKE_BREAKOUT_RATE_HIGH: float = 0.30
_SEVERE_MISS_RATE_REJECT: float = 0.50
_FAKE_BREAKOUT_RATE_REJECT: float = 0.50


class PaperShadowStrategyValidationEngine:
    """Deterministic paper-shadow cohort validator.

    The engine is pure: same inputs -> same outputs. It does not read
    clocks, files, or environment except via the explicit ``now_utc``
    injection point used only to stamp ``generated_at_utc``.

    The engine MUST NOT and CANNOT:
      - call DeepSeek / LLM / network
      - send Telegram outbound
      - touch the Binance private API
      - write back to runtime config
      - generate any runtime-tuning patch
      - emit any direction / order / sizing / risk / execution field
      - authorize live trading or auto-tuning
      - enter Phase 12
    """

    def __init__(self) -> None:
        # Defensive tripwires: the engine cannot accidentally advertise
        # capabilities it must never have.
        self.sandbox_only: bool = True
        self.writes_runtime_config: bool = False
        self.auto_tuning_allowed: bool = False
        self.trade_authority: bool = False
        self.phase_12_forbidden: bool = True
        self.live_trading: bool = False
        self.exchange_live_orders: bool = False
        self.right_tail: bool = False
        self.llm: bool = False
        self.llm_outbound_enabled: bool = False
        self.telegram_outbound_enabled: bool = False
        self.binance_private_api_enabled: bool = False

    # -- public API ---------------------------------------------------------

    def group_into_cohorts(
        self, samples: Sequence[PaperShadowSample]
    ) -> Dict[PaperShadowCohortKey, List[PaperShadowSample]]:
        """Group samples by cohort key. Deterministic ordering."""
        groups: Dict[PaperShadowCohortKey, List[PaperShadowSample]] = {}
        for s in samples:
            groups.setdefault(s.cohort_key, []).append(s)
        # Deterministic: sort each group's samples by sample_id, and
        # return a dict whose insertion order follows cohort sort_tuple.
        ordered: Dict[
            PaperShadowCohortKey, List[PaperShadowSample]
        ] = {}
        for key in sorted(groups.keys(), key=lambda k: k.sort_tuple()):
            ordered[key] = sorted(groups[key], key=lambda s: s.sample_id)
        return ordered

    def evaluate_cohort(
        self,
        cohort_key: PaperShadowCohortKey,
        samples: Sequence[PaperShadowSample],
    ) -> PaperShadowCohortEvaluation:
        n = len(samples)
        if n == 0:
            return PaperShadowCohortEvaluation(
                cohort_id=cohort_key.cohort_id(),
                cohort_key=cohort_key,
                sample_count=0,
                usable_discovery_rate=0.0,
                median_mfe_pct=None,
                median_mae_pct=None,
                late_chase_rate=0.0,
                fake_breakout_rate=0.0,
                severe_miss_rate=0.0,
                false_negative_reject_rate=0.0,
                data_gap_rate=0.0,
                confidence_bucket="very_low",
                quality_bucket="very_low",
                recommendation_level=RecommendationLevel.INCONCLUSIVE,
            )

        late_chase_rate = sum(1 for s in samples if s.late_chase) / n
        fake_breakout_rate = sum(1 for s in samples if s.fake_breakout) / n
        severe_miss_rate = sum(1 for s in samples if s.severe_miss) / n
        false_negative_reject_rate = (
            sum(1 for s in samples if s.false_negative_reject) / n
        )
        data_gap_rate = sum(1 for s in samples if s.data_gap) / n

        # A sample is "usable" if it has a non-data-gap evidence trail
        # AND was not a late chase / fake breakout / severe miss /
        # false-negative reject. This is intentionally conservative.
        usable = sum(
            1
            for s in samples
            if not s.data_gap
            and not s.late_chase
            and not s.fake_breakout
            and not s.severe_miss
            and not s.false_negative_reject
        )
        usable_discovery_rate = usable / n

        mfe_values = [
            s.post_seen_mfe_pct
            for s in samples
            if isinstance(s.post_seen_mfe_pct, (int, float))
            and not isinstance(s.post_seen_mfe_pct, bool)
        ]
        mae_values = [
            s.post_seen_mae_pct
            for s in samples
            if isinstance(s.post_seen_mae_pct, (int, float))
            and not isinstance(s.post_seen_mae_pct, bool)
        ]
        median_mfe = (
            float(statistics.median(mfe_values)) if mfe_values else None
        )
        median_mae = (
            float(statistics.median(mae_values)) if mae_values else None
        )

        confidence_bucket = self._confidence_bucket(n, data_gap_rate)
        quality_bucket = self._quality_bucket(
            usable_discovery_rate=usable_discovery_rate,
            severe_miss_rate=severe_miss_rate,
            fake_breakout_rate=fake_breakout_rate,
            late_chase_rate=late_chase_rate,
            data_gap_rate=data_gap_rate,
        )

        recommendation = self._recommend(
            sample_count=n,
            usable_discovery_rate=usable_discovery_rate,
            late_chase_rate=late_chase_rate,
            fake_breakout_rate=fake_breakout_rate,
            severe_miss_rate=severe_miss_rate,
            data_gap_rate=data_gap_rate,
        )

        evaluation = PaperShadowCohortEvaluation(
            cohort_id=cohort_key.cohort_id(),
            cohort_key=cohort_key,
            sample_count=n,
            usable_discovery_rate=round(usable_discovery_rate, 6),
            median_mfe_pct=(
                round(median_mfe, 6) if median_mfe is not None else None
            ),
            median_mae_pct=(
                round(median_mae, 6) if median_mae is not None else None
            ),
            late_chase_rate=round(late_chase_rate, 6),
            fake_breakout_rate=round(fake_breakout_rate, 6),
            severe_miss_rate=round(severe_miss_rate, 6),
            false_negative_reject_rate=round(
                false_negative_reject_rate, 6
            ),
            data_gap_rate=round(data_gap_rate, 6),
            confidence_bucket=confidence_bucket,
            quality_bucket=quality_bucket,
            recommendation_level=recommendation,
        )
        # Defensive: refuse to emit cohort evaluations that contain
        # forbidden field names anywhere (e.g., via a hostile cohort key).
        assert_no_forbidden_fields(evaluation.to_dict())
        return evaluation

    def build_report(
        self,
        *,
        reference_window: str,
        samples: Sequence[PaperShadowSample],
        now_utc: Optional[datetime] = None,
        report_id: Optional[str] = None,
        known_gaps: Optional[Sequence[str]] = None,
    ) -> PaperShadowStrategyValidationReport:
        groups = self.group_into_cohorts(samples)
        evaluations: List[PaperShadowCohortEvaluation] = []
        for key, group in groups.items():
            evaluations.append(self.evaluate_cohort(key, group))
        # Deterministic ordering of evaluations: by cohort_id (stable
        # across runs because cohort_id is a sha256 of the canonical
        # cohort key).
        evaluations.sort(key=lambda e: e.cohort_id)

        promising = tuple(
            e.cohort_id
            for e in evaluations
            if e.recommendation_level
            == RecommendationLevel.PROMISING_FOR_FORWARD_TEST
        )
        rejected = tuple(
            e.cohort_id
            for e in evaluations
            if e.recommendation_level
            == RecommendationLevel.REJECTED_BY_EVIDENCE
        )
        inconclusive = tuple(
            e.cohort_id
            for e in evaluations
            if e.recommendation_level == RecommendationLevel.INCONCLUSIVE
        )
        risky = tuple(
            e.cohort_id
            for e in evaluations
            if e.recommendation_level == RecommendationLevel.RISKY
        )
        review_only = tuple(
            e.cohort_id
            for e in evaluations
            if e.recommendation_level == RecommendationLevel.REVIEW_ONLY
        )

        # Aggregate known gaps deterministically.
        gap_set: List[str] = []
        seen: set = set()
        for g in list(known_gaps or []):
            if isinstance(g, str) and g and g not in seen:
                gap_set.append(g)
                seen.add(g)
        if any(s.data_gap for s in samples):
            tag = "samples_contain_data_gap"
            if tag not in seen:
                gap_set.append(tag)
                seen.add(tag)
        if not samples:
            tag = "no_samples_supplied"
            if tag not in seen:
                gap_set.append(tag)
                seen.add(tag)

        if not samples:
            status = PaperShadowValidationStatus.INSUFFICIENT_EVIDENCE
        elif sum(1 for s in samples if s.data_gap) >= max(
            1, int(0.30 * len(samples))
        ):
            status = PaperShadowValidationStatus.DATA_GAP
        else:
            status = PaperShadowValidationStatus.COMPLETED

        generated_at = (
            now_utc if now_utc is not None else datetime.now(timezone.utc)
        )
        # Determinism: caller may inject ``now_utc`` for fully
        # reproducible runs (tests do this).
        generated_at_iso = generated_at.replace(microsecond=0).isoformat()

        if report_id is None:
            report_id = self._derive_report_id(
                reference_window=reference_window,
                evaluations=evaluations,
                generated_at_iso=generated_at_iso,
            )

        report = PaperShadowStrategyValidationReport(
            report_id=report_id,
            generated_at_utc=generated_at_iso,
            reference_window=reference_window,
            total_samples=len(samples),
            evaluated_cohort_count=len(evaluations),
            cohort_evaluations=tuple(evaluations),
            promising_cohorts=promising,
            rejected_cohorts=rejected,
            inconclusive_cohorts=inconclusive,
            risky_cohorts=risky,
            review_only_cohorts=review_only,
            known_gaps=tuple(gap_set),
            status=status,
        )
        # Defensive: refuse to emit reports that contain forbidden field
        # names anywhere.
        assert_no_forbidden_fields(report.to_dict())
        return report

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _confidence_bucket(sample_count: int, data_gap_rate: float) -> str:
        if sample_count < _MIN_SAMPLES_FOR_VERDICT:
            return "very_low"
        if data_gap_rate >= _DATA_GAP_RATE_RISKY:
            return "very_low"
        if sample_count < _MIN_SAMPLES_FOR_PROMISING:
            return "low"
        if data_gap_rate >= _DATA_GAP_RATE_HIGH:
            return "low"
        if sample_count < 16:
            return "medium"
        if sample_count < 32:
            return "high"
        return "very_high"

    @staticmethod
    def _quality_bucket(
        *,
        usable_discovery_rate: float,
        severe_miss_rate: float,
        fake_breakout_rate: float,
        late_chase_rate: float,
        data_gap_rate: float,
    ) -> str:
        # Composite quality score in [0, 1]. Weights are conservative
        # and intentionally not runtime-tunable.
        score = (
            usable_discovery_rate
            - 0.5 * severe_miss_rate
            - 0.5 * fake_breakout_rate
            - 0.25 * late_chase_rate
            - 0.25 * data_gap_rate
        )
        score = max(0.0, min(1.0, score))
        return _bucket_score(score)

    @staticmethod
    def _recommend(
        *,
        sample_count: int,
        usable_discovery_rate: float,
        late_chase_rate: float,
        fake_breakout_rate: float,
        severe_miss_rate: float,
        data_gap_rate: float,
    ) -> str:
        # 1. Sample size too small -> INCONCLUSIVE.
        if sample_count < _MIN_SAMPLES_FOR_VERDICT:
            return RecommendationLevel.INCONCLUSIVE
        # 2. Catastrophic data gap -> RISKY (we cannot trust the rates).
        if data_gap_rate >= _DATA_GAP_RATE_RISKY:
            return RecommendationLevel.RISKY
        # 3. High data gap -> INCONCLUSIVE.
        if data_gap_rate >= _DATA_GAP_RATE_HIGH:
            return RecommendationLevel.INCONCLUSIVE
        # 4. Catastrophic severe miss / fake breakout ->
        #    REJECTED_BY_EVIDENCE.
        if (
            severe_miss_rate >= _SEVERE_MISS_RATE_REJECT
            or fake_breakout_rate >= _FAKE_BREAKOUT_RATE_REJECT
        ):
            return RecommendationLevel.REJECTED_BY_EVIDENCE
        # 5. Elevated severe miss / fake breakout -> RISKY.
        if (
            severe_miss_rate >= _SEVERE_MISS_RATE_HIGH
            or fake_breakout_rate >= _FAKE_BREAKOUT_RATE_HIGH
        ):
            return RecommendationLevel.RISKY
        # 6. Promising path: enough samples, high usable discovery,
        #    low late_chase / fake_breakout / severe_miss.
        if (
            sample_count >= _MIN_SAMPLES_FOR_PROMISING
            and usable_discovery_rate >= _USABLE_DISCOVERY_RATE_PROMISING
            and late_chase_rate <= _LATE_CHASE_RATE_LOW
            and fake_breakout_rate <= _FAKE_BREAKOUT_RATE_LOW
            and severe_miss_rate <= _SEVERE_MISS_RATE_LOW
        ):
            return RecommendationLevel.PROMISING_FOR_FORWARD_TEST
        # 7. Default: REVIEW_ONLY.
        return RecommendationLevel.REVIEW_ONLY

    @staticmethod
    def _derive_report_id(
        *,
        reference_window: str,
        evaluations: Sequence[PaperShadowCohortEvaluation],
        generated_at_iso: str,
    ) -> str:
        h = hashlib.sha256()
        h.update(reference_window.encode("utf-8"))
        h.update(b"|")
        h.update(generated_at_iso.encode("utf-8"))
        for e in evaluations:
            h.update(b"|")
            h.update(
                json.dumps(e.to_dict(), sort_keys=True, default=str).encode(
                    "utf-8"
                )
            )
        return f"paper_shadow_strategy_validation_{h.hexdigest()[:16]}"


# ---------------------------------------------------------------------------
# Sample construction from structured report inputs
# ---------------------------------------------------------------------------


def _safe_section(d: Optional[Mapping[str, Any]], key: str) -> Any:
    if not isinstance(d, Mapping):
        return None
    return d.get(key)


def _iter_records(value: Any) -> List[Mapping[str, Any]]:
    if isinstance(value, list):
        return [v for v in value if isinstance(v, Mapping)]
    if isinstance(value, Mapping):
        out: List[Mapping[str, Any]] = []
        # Common containers: {"records": [...]} or {"items": [...]}.
        for inner_key in ("records", "items", "samples", "rows"):
            inner = value.get(inner_key)
            if isinstance(inner, list):
                out.extend(v for v in inner if isinstance(v, Mapping))
        if out:
            return out
        # Otherwise treat the mapping itself as a single record.
        return [value]
    return []


def _cohort_key_from_record(record: Mapping[str, Any]) -> PaperShadowCohortKey:
    return PaperShadowCohortKey(
        market_regime=_safe_str(record.get("market_regime")),
        cluster_id=_safe_str(record.get("cluster_id")),
        leader_vs_follower=_safe_str(record.get("leader_vs_follower")),
        candidate_stage=_safe_str(record.get("candidate_stage")),
        strategy_mode=_safe_str(record.get("strategy_mode")),
        opportunity_score_bucket=_bucket_score(
            record.get("opportunity_score")
        )
        if "opportunity_score" in record
        else _safe_str(record.get("opportunity_score_bucket")),
        early_tail_score_bucket=_bucket_score(
            record.get("early_tail_score")
        )
        if "early_tail_score" in record
        else _safe_str(record.get("early_tail_score_bucket")),
        post_discovery_outcome_label=_safe_str(
            record.get("post_discovery_outcome_label")
            or record.get("outcome_label")
        ),
        reject_attribution_verdict=_safe_str(
            record.get("reject_attribution_verdict")
            or record.get("attribution_verdict")
        ),
        severe_miss_root_cause=_safe_str(
            record.get("severe_miss_root_cause")
            or record.get("root_cause")
        ),
        discovery_quality_bucket=_safe_str(
            record.get("discovery_quality_bucket")
            or record.get("quality_bucket")
        ),
    )


def build_samples_from_reports(
    *,
    block_b_report: Optional[Mapping[str, Any]] = None,
    block_c_report: Optional[Mapping[str, Any]] = None,
    rule_sandbox_report: Optional[Mapping[str, Any]] = None,
    reference_window: str = "60d",
) -> List[PaperShadowSample]:
    """Pure function: assemble PaperShadowSample rows from report dicts.

    Reports are read for evidence only. Nothing is written back.
    Missing records are tolerated and surface as ``data_gap`` flags
    on individual samples.
    """
    samples: List[PaperShadowSample] = []
    seen_ids: set = set()

    sources: List[Tuple[str, Optional[Mapping[str, Any]]]] = [
        ("block_b", block_b_report),
        ("block_c", block_c_report),
        ("rule_sandbox", rule_sandbox_report),
    ]
    for src_name, src in sources:
        if not isinstance(src, Mapping):
            continue
        # Try several plausible record containers, in priority order.
        candidate_sections: List[Any] = []
        for key in (
            "paper_shadow_samples",
            "post_discovery_outcome_records",
            "post_discovery_outcomes",
            "severe_miss_records",
            "reject_attribution_records",
            "discovery_quality_records",
            "samples",
            "records",
        ):
            section = src.get(key)
            if section is not None:
                candidate_sections.append(section)
        if not candidate_sections:
            continue
        report_id = _safe_str(src.get("report_id") or src.get("id"))

        for section in candidate_sections:
            for idx, record in enumerate(_iter_records(section)):
                raw_id = _safe_str(
                    record.get("sample_id")
                    or record.get("id")
                    or f"{src_name}:{idx}",
                    default=f"{src_name}:{idx}",
                )
                # Deterministic uniqueness: prefix with source if needed.
                sample_id = raw_id
                suffix = 1
                while sample_id in seen_ids:
                    sample_id = f"{raw_id}#{suffix}"
                    suffix += 1
                seen_ids.add(sample_id)

                cohort_key = _cohort_key_from_record(record)
                first_seen = _safe_str(
                    record.get("first_seen_time_utc")
                    or record.get("first_seen_at")
                    or record.get("timestamp_utc"),
                    default="unknown",
                )

                evidence_refs: List[str] = []
                if report_id and report_id != "unknown":
                    evidence_refs.append(f"{src_name}:{report_id}")
                for ref in record.get("evidence_refs", []) or []:
                    if isinstance(ref, str):
                        evidence_refs.append(ref)

                source_event_refs: List[str] = []
                for ref in record.get("source_event_refs", []) or []:
                    if isinstance(ref, str):
                        source_event_refs.append(ref)

                samples.append(
                    PaperShadowSample(
                        sample_id=sample_id,
                        symbol=_safe_str(
                            record.get("symbol"), default="UNKNOWN"
                        ),
                        reference_window=_safe_str(
                            record.get("reference_window"),
                            default=reference_window,
                        ),
                        first_seen_time_utc=first_seen,
                        cohort_key=cohort_key,
                        source_event_refs=tuple(source_event_refs),
                        post_seen_mfe_pct=_safe_float(
                            record.get("post_seen_mfe_pct")
                            or record.get("post_seen_mfe")
                        ),
                        post_seen_mae_pct=_safe_float(
                            record.get("post_seen_mae_pct")
                            or record.get("post_seen_mae")
                        ),
                        remaining_upside_to_peak_pct=_safe_float(
                            record.get("remaining_upside_to_peak_pct")
                            or record.get("remaining_upside_pct")
                        ),
                        late_chase=_safe_bool(record.get("late_chase")),
                        fake_breakout=_safe_bool(
                            record.get("fake_breakout")
                        ),
                        severe_miss=_safe_bool(record.get("severe_miss")),
                        false_negative_reject=_safe_bool(
                            record.get("false_negative_reject")
                        ),
                        data_gap=_safe_bool(record.get("data_gap")),
                        evidence_refs=tuple(evidence_refs),
                        source=_safe_str(
                            record.get("source"),
                            default="operator_supplied",
                        ),
                    )
                )
    return samples


# ---------------------------------------------------------------------------
# Example fixture (deterministic, marked source=example_fixture)
# ---------------------------------------------------------------------------


def example_fixture_samples(
    *, reference_window: str = "60d"
) -> List[PaperShadowSample]:
    """Deterministic example samples. Marked source=example_fixture.

    Used by the runner ONLY when no operator-supplied input report is on
    disk. NEVER claims to be real paper evidence. The shape is designed
    so the engine's recommendation rules each fire at least once,
    making the runner output illustrative.
    """
    samples: List[PaperShadowSample] = []

    # Cohort A: PROMISING — many samples, high usable discovery, low
    # severe miss / late chase / fake breakout.
    cohort_a = PaperShadowCohortKey(
        market_regime="trend",
        cluster_id="cluster_alpha",
        leader_vs_follower="leader",
        candidate_stage="EARLY",
        strategy_mode="continuation",
        opportunity_score_bucket="high",
        early_tail_score_bucket="high",
        post_discovery_outcome_label="EARLY_CONTINUATION",
        reject_attribution_verdict="not_rejected",
        severe_miss_root_cause="none",
        discovery_quality_bucket="high",
    )
    for i in range(10):
        samples.append(
            PaperShadowSample(
                sample_id=f"fixture_a_{i:02d}",
                symbol=f"FIXAUSDT_{i:02d}",
                reference_window=reference_window,
                first_seen_time_utc="2026-04-01T00:00:00+00:00",
                cohort_key=cohort_a,
                source_event_refs=(),
                post_seen_mfe_pct=0.04 + 0.001 * i,
                post_seen_mae_pct=0.012 + 0.0005 * i,
                remaining_upside_to_peak_pct=0.06 + 0.001 * i,
                late_chase=(i == 9),  # 1/10 -> 0.10
                fake_breakout=False,
                severe_miss=False,
                false_negative_reject=False,
                data_gap=False,
                evidence_refs=("phase_11c_1d_b_paper_shadow_v0",),
                source="example_fixture",
            )
        )

    # Cohort B: RISKY / REJECTED — many severe miss + fake breakout.
    cohort_b = PaperShadowCohortKey(
        market_regime="range",
        cluster_id="cluster_beta",
        leader_vs_follower="follower",
        candidate_stage="LATE",
        strategy_mode="breakout",
        opportunity_score_bucket="medium",
        early_tail_score_bucket="low",
        post_discovery_outcome_label="LATE_TOP_CHASE",
        reject_attribution_verdict="reject_correct",
        severe_miss_root_cause="early_tail_score_too_high",
        discovery_quality_bucket="low",
    )
    for i in range(10):
        samples.append(
            PaperShadowSample(
                sample_id=f"fixture_b_{i:02d}",
                symbol=f"FIXBUSDT_{i:02d}",
                reference_window=reference_window,
                first_seen_time_utc="2026-04-02T00:00:00+00:00",
                cohort_key=cohort_b,
                source_event_refs=(),
                post_seen_mfe_pct=0.005,
                post_seen_mae_pct=0.04,
                remaining_upside_to_peak_pct=0.0,
                late_chase=(i % 2 == 0),  # 5/10
                fake_breakout=(i < 6),  # 6/10 -> 0.60 (REJECTED bound)
                severe_miss=(i < 6),  # 6/10
                false_negative_reject=False,
                data_gap=False,
                evidence_refs=("phase_11c_1d_b_paper_shadow_v0",),
                source="example_fixture",
            )
        )

    # Cohort C: INCONCLUSIVE due to small sample count.
    cohort_c = PaperShadowCohortKey(
        market_regime="trend",
        cluster_id="cluster_gamma",
        leader_vs_follower="leader",
        candidate_stage="MID_MOVE",
        strategy_mode="continuation",
        opportunity_score_bucket="medium",
        early_tail_score_bucket="medium",
        post_discovery_outcome_label="NO_CLEAR_EDGE",
        reject_attribution_verdict="not_rejected",
        severe_miss_root_cause="none",
        discovery_quality_bucket="medium",
    )
    for i in range(2):
        samples.append(
            PaperShadowSample(
                sample_id=f"fixture_c_{i:02d}",
                symbol=f"FIXCUSDT_{i:02d}",
                reference_window=reference_window,
                first_seen_time_utc="2026-04-03T00:00:00+00:00",
                cohort_key=cohort_c,
                source_event_refs=(),
                post_seen_mfe_pct=0.02,
                post_seen_mae_pct=0.015,
                remaining_upside_to_peak_pct=0.03,
                late_chase=False,
                fake_breakout=False,
                severe_miss=False,
                false_negative_reject=False,
                data_gap=False,
                evidence_refs=("phase_11c_1d_b_paper_shadow_v0",),
                source="example_fixture",
            )
        )

    # Cohort D: INCONCLUSIVE / RISKY due to high data_gap_rate.
    cohort_d = PaperShadowCohortKey(
        market_regime="chop",
        cluster_id="cluster_delta",
        leader_vs_follower="follower",
        candidate_stage="EARLY",
        strategy_mode="reversion",
        opportunity_score_bucket="low",
        early_tail_score_bucket="low",
        post_discovery_outcome_label="INSUFFICIENT_PRICE_PATH",
        reject_attribution_verdict="not_rejected",
        severe_miss_root_cause="data_gap",
        discovery_quality_bucket="low",
    )
    for i in range(8):
        samples.append(
            PaperShadowSample(
                sample_id=f"fixture_d_{i:02d}",
                symbol=f"FIXDUSDT_{i:02d}",
                reference_window=reference_window,
                first_seen_time_utc="2026-04-04T00:00:00+00:00",
                cohort_key=cohort_d,
                source_event_refs=(),
                post_seen_mfe_pct=None,
                post_seen_mae_pct=None,
                remaining_upside_to_peak_pct=None,
                late_chase=False,
                fake_breakout=False,
                severe_miss=False,
                false_negative_reject=False,
                data_gap=(i < 5),  # 5/8 = 0.625 -> RISKY
                evidence_refs=("phase_11c_1d_b_paper_shadow_v0",),
                source="example_fixture",
            )
        )

    return samples


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def render_report_markdown(
    report: PaperShadowStrategyValidationReport,
) -> str:
    lines: List[str] = []
    lines.append("# Paper Shadow Strategy Validation v0 Report")
    lines.append("")
    lines.append(f"- report_id: `{report.report_id}`")
    lines.append(f"- phase: `{report.phase}`")
    lines.append(f"- status: `{report.status}`")
    lines.append(f"- generated_at_utc: `{report.generated_at_utc}`")
    lines.append(f"- reference_window: `{report.reference_window}`")
    lines.append(f"- total_samples: `{report.total_samples}`")
    lines.append(
        f"- evaluated_cohort_count: `{report.evaluated_cohort_count}`"
    )
    lines.append(f"- next_allowed_phase: `{report.next_allowed_phase}`")
    lines.append("")
    lines.append("## Safety Boundary")
    lines.append("")
    lines.append(f"- sandbox_only: `{report.sandbox_only}`")
    lines.append(
        f"- writes_runtime_config: `{report.writes_runtime_config}`"
    )
    lines.append(
        f"- auto_tuning_allowed: `{report.auto_tuning_allowed}`"
    )
    lines.append(f"- trade_authority: `{report.trade_authority}`")
    lines.append(f"- live_trading: `{report.live_trading}`")
    lines.append(
        f"- exchange_live_orders: `{report.exchange_live_orders}`"
    )
    lines.append(f"- right_tail: `{report.right_tail}`")
    lines.append(f"- llm: `{report.llm}`")
    lines.append(
        f"- llm_outbound_enabled: `{report.llm_outbound_enabled}`"
    )
    lines.append(
        f"- telegram_outbound_enabled: "
        f"`{report.telegram_outbound_enabled}`"
    )
    lines.append(
        f"- binance_private_api_enabled: "
        f"`{report.binance_private_api_enabled}`"
    )
    lines.append(f"- phase_12_forbidden: `{report.phase_12_forbidden}`")
    lines.append("")
    lines.append("## Cohort Evaluations")
    lines.append("")
    if not report.cohort_evaluations:
        lines.append("_no cohorts evaluated_")
    for e in report.cohort_evaluations:
        lines.append(f"### cohort `{e.cohort_id}`")
        lines.append("")
        lines.append(
            f"- recommendation_level: `{e.recommendation_level}`"
        )
        lines.append(f"- sample_count: `{e.sample_count}`")
        lines.append(f"- confidence_bucket: `{e.confidence_bucket}`")
        lines.append(f"- quality_bucket: `{e.quality_bucket}`")
        lines.append(
            f"- usable_discovery_rate: `{e.usable_discovery_rate:.4f}`"
        )
        lines.append(
            f"- median_mfe_pct: `{e.median_mfe_pct}`"
        )
        lines.append(f"- median_mae_pct: `{e.median_mae_pct}`")
        lines.append(f"- late_chase_rate: `{e.late_chase_rate:.4f}`")
        lines.append(
            f"- fake_breakout_rate: `{e.fake_breakout_rate:.4f}`"
        )
        lines.append(f"- severe_miss_rate: `{e.severe_miss_rate:.4f}`")
        lines.append(
            f"- false_negative_reject_rate: "
            f"`{e.false_negative_reject_rate:.4f}`"
        )
        lines.append(f"- data_gap_rate: `{e.data_gap_rate:.4f}`")
        lines.append("- cohort_key:")
        for k, v in sorted(e.cohort_key.to_dict().items()):
            lines.append(f"  - `{k}`: `{v}`")
        lines.append("")
    lines.append("## Promising Cohorts (forward-test candidates)")
    lines.append("")
    if report.promising_cohorts:
        for cid in report.promising_cohorts:
            lines.append(f"- `{cid}`")
    else:
        lines.append("_none_")
    lines.append("")
    lines.append("## Risky Cohorts")
    lines.append("")
    if report.risky_cohorts:
        for cid in report.risky_cohorts:
            lines.append(f"- `{cid}`")
    else:
        lines.append("_none_")
    lines.append("")
    lines.append("## Rejected Cohorts")
    lines.append("")
    if report.rejected_cohorts:
        for cid in report.rejected_cohorts:
            lines.append(f"- `{cid}`")
    else:
        lines.append("_none_")
    lines.append("")
    lines.append("## Inconclusive Cohorts")
    lines.append("")
    if report.inconclusive_cohorts:
        for cid in report.inconclusive_cohorts:
            lines.append(f"- `{cid}`")
    else:
        lines.append("_none_")
    lines.append("")
    lines.append("## Review-Only Cohorts")
    lines.append("")
    if report.review_only_cohorts:
        for cid in report.review_only_cohorts:
            lines.append(f"- `{cid}`")
    else:
        lines.append("_none_")
    lines.append("")
    lines.append("## Known Gaps")
    lines.append("")
    if report.known_gaps:
        for g in report.known_gaps:
            lines.append(f"- {g}")
    else:
        lines.append("_none_")
    lines.append("")
    lines.append(
        "> This report does NOT authorize live trading, does NOT "
        "write runtime config, does NOT auto-tune, and does NOT "
        "enter Phase 12. A `PROMISING_FOR_FORWARD_TEST` "
        "recommendation only marks a cohort as a candidate for the "
        "next allowed paper / read-only preparation step (Risk / "
        "Execution / Capital Safety Matrix preparation or strict "
        "walk-forward preparation)."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level integrity guard
# ---------------------------------------------------------------------------

# These attributes are read by tests to verify the safety contract. They
# must not be flipped without bumping the phase.
SAFETY_CONTRACT: Dict[str, Any] = {
    "phase": PHASE_NAME,
    "sandbox_only": True,
    "writes_runtime_config": False,
    "auto_tuning_allowed": False,
    "trade_authority": False,
    "phase_12_forbidden": True,
    "live_trading": False,
    "exchange_live_orders": False,
    "right_tail": False,
    "llm": False,
    "llm_outbound_enabled": False,
    "telegram_outbound_enabled": False,
    "binance_private_api_enabled": False,
    "next_allowed_phase": NEXT_ALLOWED_PHASE,
}
