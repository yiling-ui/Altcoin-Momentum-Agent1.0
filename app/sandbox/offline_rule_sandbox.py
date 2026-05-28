"""Offline Rule Sandbox Replay v0 (Phase 11C).

A strictly offline, deterministic replay engine that lets operators model how
hypothetical rule changes WOULD HAVE affected discovery quality on historical
evidence (Block B / Block C / AI integrated checkpoint reports).

This module exists to safely answer questions such as:
  * If early_tail_score threshold were lowered, would severe miss rate drop?
  * If candidate score cutoff were adjusted, would late chase rise?
  * If a reject rule were relaxed, would false-negative rejects decrease?
  * Would the rule change introduce more fake breakouts than it prevents
    severe misses?

==============================================================================
HARD SAFETY BOUNDARY (Phase 11C / Offline Rule Sandbox Replay v0)
==============================================================================
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
  * import app.risk / app.execution / app.exchanges / app.telegram / app.config
  * write back to runtime config
  * generate runtime_config_patch / threshold_patch / symbol_limit_patch /
    candidate_pool_patch / regime_weight_patch / strategy_parameter_patch
  * emit buy / sell / long / short / direction / entry / exit
  * emit position_size / leverage / stop / target / risk_budget
  * authorize live trading or hot-path execution
  * call DeepSeek / LLM / network
  * enter Phase 12

A "HypotheticalRuleChange" is a *hypothetical*, not a patch. It is never
applied anywhere outside of this in-memory replay.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Constants and enums
# ---------------------------------------------------------------------------

PHASE_NAME = "Phase 11C / Offline Rule Sandbox Replay v0"

# next_allowed_phase after a successful sandbox run is *only* preparation for
# Paper Shadow Strategy Validation. It is not Phase 12 and not live trading.
NEXT_ALLOWED_PHASE = "Paper Shadow Strategy Validation preparation"


class RecommendationLevel:
    """Allowed recommendation levels emitted by the sandbox.

    Note: APPLY / DEPLOY / ENABLE_LIVE / TRADE / BUY / SELL are intentionally
    NOT defined here, and the engine refuses to ever emit them.
    """

    REVIEW_ONLY = "REVIEW_ONLY"
    INCONCLUSIVE = "INCONCLUSIVE"
    PROMISING_FOR_PAPER_SHADOW = "PROMISING_FOR_PAPER_SHADOW"
    RISKY = "RISKY"
    REJECTED_BY_EVIDENCE = "REJECTED_BY_EVIDENCE"

    ALLOWED = frozenset(
        {
            REVIEW_ONLY,
            INCONCLUSIVE,
            PROMISING_FOR_PAPER_SHADOW,
            RISKY,
            REJECTED_BY_EVIDENCE,
        }
    )


class SandboxStatus:
    COMPLETED = "COMPLETED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INCONCLUSIVE = "INCONCLUSIVE"
    DATA_GAP = "DATA_GAP"
    ERROR = "ERROR"


class SandboxEvent:
    """Allowed event types. Strictly report/export/replay scope.

    No trade-action events are defined and none must be added in this phase.
    """

    OFFLINE_RULE_SANDBOX_REPLAY_RUN = "OFFLINE_RULE_SANDBOX_REPLAY_RUN"
    OFFLINE_RULE_SANDBOX_SCENARIO_EVALUATED = (
        "OFFLINE_RULE_SANDBOX_SCENARIO_EVALUATED"
    )
    OFFLINE_RULE_SANDBOX_REPORT_GENERATED = (
        "OFFLINE_RULE_SANDBOX_REPORT_GENERATED"
    )


# Forbidden field names that must NEVER appear (recursively) in any output
# payload produced by this module.
FORBIDDEN_OUTPUT_FIELDS: frozenset = frozenset(
    {
        "buy",
        "sell",
        "long",
        "short",
        "direction",
        "entry",
        "exit",
        "position_size",
        "leverage",
        "stop",
        "stop_loss",
        "target",
        "take_profit",
        "risk_budget",
        "order",
        "execution_command",
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
        "strategy_parameter_patch",
        "signal_to_trade",
        "should_buy",
        "should_short",
        "apply_change",
        "deploy_change",
        "enable_live",
    }
)


# Allowed change_type vocabulary (deterministic, finite).
_ALLOWED_CHANGE_TYPES = frozenset(
    {
        "threshold_decrease",
        "threshold_increase",
        "score_cutoff_decrease",
        "score_cutoff_increase",
        "reject_rule_relax",
        "reject_rule_tighten",
        "cohort_filter_widen",
        "cohort_filter_narrow",
        "noop",
    }
)


# Baseline metric keys the sandbox understands. Missing keys are treated as
# data gaps; they never silently default to a trade-friendly value.
_BASELINE_METRIC_KEYS: Tuple[str, ...] = (
    "coverage_rate",
    "usable_discovery_rate",
    "severe_miss_rate",
    "false_negative_reject_rate",
    "late_chase_rate",
    "fake_breakout_rate",
    "data_gap_rate",
    "median_mfe",
    "median_mae",
)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HypotheticalRuleChange:
    """A hypothetical rule change to be replayed. NOT a runtime patch.

    The fields are intentionally named to make it impossible to confuse this
    object with a runtime_config_patch / threshold_patch / etc.
    """

    rule_name: str
    baseline_value: Any
    sandbox_value: Any
    change_type: str
    rationale: str = ""
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.rule_name, str) or not self.rule_name:
            raise ValueError("rule_name must be a non-empty string")
        if self.change_type not in _ALLOWED_CHANGE_TYPES:
            raise ValueError(
                f"change_type must be one of {_ALLOWED_CHANGE_TYPES}, "
                f"got {self.change_type!r}"
            )
        # Forbid any field-name that smells like a runtime patch.
        for forbidden in FORBIDDEN_OUTPUT_FIELDS:
            if forbidden in self.rule_name.lower():
                # rule_name itself may legitimately contain words like
                # 'threshold', so we only block hard runtime-patch tokens.
                if forbidden in {
                    "runtime_config_patch",
                    "symbol_limit_patch",
                    "threshold_patch",
                    "candidate_pool_patch",
                    "regime_weight_patch",
                    "strategy_parameter_patch",
                }:
                    raise ValueError(
                        f"rule_name must not name a runtime patch: "
                        f"{self.rule_name!r}"
                    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "baseline_value": self.baseline_value,
            "sandbox_value": self.sandbox_value,
            "change_type": self.change_type,
            "rationale": self.rationale,
            "evidence_refs": list(self.evidence_refs),
            # Explicit non-patch markers (defensive; visible to reviewers):
            "is_hypothetical": True,
            "is_runtime_patch": False,
        }


@dataclass(frozen=True)
class OfflineRuleSandboxScenario:
    scenario_id: str
    name: str
    reference_window: str
    baseline_label: str
    hypothetical_rule_changes: Tuple[HypotheticalRuleChange, ...] = field(
        default_factory=tuple
    )
    cohort_filters: Mapping[str, Any] = field(default_factory=dict)
    source_reports: Tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)
    source: str = "operator_supplied"
    sandbox_only: bool = True
    writes_runtime_config: bool = False
    auto_tuning_allowed: bool = False

    def __post_init__(self) -> None:
        # Enforce safety flags at the type level. Operator cannot construct a
        # scenario that claims to write runtime config or auto-tune.
        if self.sandbox_only is not True:
            raise ValueError("sandbox_only must be True in Phase 11C")
        if self.writes_runtime_config is not False:
            raise ValueError(
                "writes_runtime_config must be False in Phase 11C"
            )
        if self.auto_tuning_allowed is not False:
            raise ValueError(
                "auto_tuning_allowed must be False in Phase 11C"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "reference_window": self.reference_window,
            "baseline_label": self.baseline_label,
            "hypothetical_rule_changes": [
                c.to_dict() for c in self.hypothetical_rule_changes
            ],
            "cohort_filters": dict(self.cohort_filters),
            "source_reports": list(self.source_reports),
            "evidence_refs": list(self.evidence_refs),
            "source": self.source,
            "sandbox_only": self.sandbox_only,
            "writes_runtime_config": self.writes_runtime_config,
            "auto_tuning_allowed": self.auto_tuning_allowed,
        }


@dataclass(frozen=True)
class OfflineRuleSandboxInput:
    baseline_discovery_quality: Mapping[str, Any]
    post_discovery_outcomes: Mapping[str, Any]
    reject_attributions: Mapping[str, Any]
    severe_miss_triage: Mapping[str, Any]
    replay_summary: Mapping[str, Any]
    reflection_summary: Mapping[str, Any]
    scenario: OfflineRuleSandboxScenario
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_discovery_quality": dict(self.baseline_discovery_quality),
            "post_discovery_outcomes": dict(self.post_discovery_outcomes),
            "reject_attributions": dict(self.reject_attributions),
            "severe_miss_triage": dict(self.severe_miss_triage),
            "replay_summary": dict(self.replay_summary),
            "reflection_summary": dict(self.reflection_summary),
            "scenario": self.scenario.to_dict(),
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class OfflineRuleSandboxResult:
    scenario_id: str
    status: str
    baseline_metrics: Mapping[str, float]
    sandbox_metrics: Mapping[str, float]
    delta_metrics: Mapping[str, float]
    likely_benefits: Tuple[str, ...] = field(default_factory=tuple)
    likely_risks: Tuple[str, ...] = field(default_factory=tuple)
    overfit_warnings: Tuple[str, ...] = field(default_factory=tuple)
    data_gap_warnings: Tuple[str, ...] = field(default_factory=tuple)
    recommendation_level: str = RecommendationLevel.REVIEW_ONLY

    def __post_init__(self) -> None:
        if self.recommendation_level not in RecommendationLevel.ALLOWED:
            raise ValueError(
                f"recommendation_level must be one of "
                f"{sorted(RecommendationLevel.ALLOWED)}, got "
                f"{self.recommendation_level!r}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "status": self.status,
            "baseline_metrics": dict(self.baseline_metrics),
            "sandbox_metrics": dict(self.sandbox_metrics),
            "delta_metrics": dict(self.delta_metrics),
            "likely_benefits": list(self.likely_benefits),
            "likely_risks": list(self.likely_risks),
            "overfit_warnings": list(self.overfit_warnings),
            "data_gap_warnings": list(self.data_gap_warnings),
            "recommendation_level": self.recommendation_level,
        }


@dataclass(frozen=True)
class OfflineRuleSandboxReport:
    report_id: str
    generated_at_utc: str
    reference_window: str
    scenarios: Tuple[OfflineRuleSandboxScenario, ...]
    scenario_results: Tuple[OfflineRuleSandboxResult, ...]
    best_review_candidates: Tuple[str, ...] = field(default_factory=tuple)
    rejected_scenarios: Tuple[str, ...] = field(default_factory=tuple)
    known_gaps: Tuple[str, ...] = field(default_factory=tuple)
    next_allowed_phase: str = NEXT_ALLOWED_PHASE
    phase_12_forbidden: bool = True
    auto_tuning_allowed: bool = False
    writes_runtime_config: bool = False
    trade_authority: bool = False
    sandbox_only: bool = True
    phase: str = PHASE_NAME

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "generated_at_utc": self.generated_at_utc,
            "reference_window": self.reference_window,
            "phase": self.phase,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "scenario_results": [r.to_dict() for r in self.scenario_results],
            "best_review_candidates": list(self.best_review_candidates),
            "rejected_scenarios": list(self.rejected_scenarios),
            "known_gaps": list(self.known_gaps),
            "next_allowed_phase": self.next_allowed_phase,
            "phase_12_forbidden": self.phase_12_forbidden,
            "auto_tuning_allowed": self.auto_tuning_allowed,
            "writes_runtime_config": self.writes_runtime_config,
            "trade_authority": self.trade_authority,
            "sandbox_only": self.sandbox_only,
        }


# ---------------------------------------------------------------------------
# Forbidden-field guard
# ---------------------------------------------------------------------------


def assert_no_forbidden_fields(payload: Any, _path: str = "$") -> None:
    """Recursively assert that no forbidden field name appears in `payload`.

    Raises ValueError on the first violation. Used as a defensive check on
    every output payload before serialization.
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
# Deterministic sensitivity model
# ---------------------------------------------------------------------------
#
# The replay does not "simulate trades". It applies a fixed, deterministic,
# auditable sensitivity table to baseline historical metrics:
#
#   delta_metric = sum_over_changes( base_vector[change_type] * magnitude )
#
# This is intentionally a transparent first-order model. It exists to flag
# direction-of-effect (does this rule change plausibly help / hurt), not to
# claim a calibrated forecast. Recommendation level is conservative.

_BASE_VECTORS: Dict[str, Dict[str, float]] = {
    # threshold_decrease (e.g., lower early_tail_score threshold)
    #   -> capture more candidates: coverage up, severe_miss down,
    #      but late_chase up, fake_breakout up.
    "threshold_decrease": {
        "coverage_rate_delta": +0.06,
        "usable_discovery_rate_delta": +0.02,
        "severe_miss_rate_delta": -0.04,
        "false_negative_reject_rate_delta": -0.02,
        "late_chase_rate_delta": +0.03,
        "fake_breakout_rate_delta": +0.04,
        "data_gap_rate_delta": 0.0,
        "median_mfe_delta": -0.01,
        "median_mae_delta": +0.02,
    },
    "threshold_increase": {
        "coverage_rate_delta": -0.06,
        "usable_discovery_rate_delta": -0.02,
        "severe_miss_rate_delta": +0.04,
        "false_negative_reject_rate_delta": +0.02,
        "late_chase_rate_delta": -0.02,
        "fake_breakout_rate_delta": -0.03,
        "data_gap_rate_delta": 0.0,
        "median_mfe_delta": +0.01,
        "median_mae_delta": -0.01,
    },
    "score_cutoff_decrease": {
        "coverage_rate_delta": +0.05,
        "usable_discovery_rate_delta": -0.01,
        "severe_miss_rate_delta": -0.02,
        "false_negative_reject_rate_delta": -0.01,
        "late_chase_rate_delta": +0.04,
        "fake_breakout_rate_delta": +0.05,
        "data_gap_rate_delta": 0.0,
        "median_mfe_delta": -0.02,
        "median_mae_delta": +0.03,
    },
    "score_cutoff_increase": {
        "coverage_rate_delta": -0.05,
        "usable_discovery_rate_delta": +0.02,
        "severe_miss_rate_delta": +0.02,
        "false_negative_reject_rate_delta": +0.01,
        "late_chase_rate_delta": -0.03,
        "fake_breakout_rate_delta": -0.04,
        "data_gap_rate_delta": 0.0,
        "median_mfe_delta": +0.01,
        "median_mae_delta": -0.02,
    },
    "reject_rule_relax": {
        "coverage_rate_delta": +0.04,
        "usable_discovery_rate_delta": +0.01,
        "severe_miss_rate_delta": -0.03,
        "false_negative_reject_rate_delta": -0.05,
        "late_chase_rate_delta": +0.02,
        "fake_breakout_rate_delta": +0.04,
        "data_gap_rate_delta": 0.0,
        "median_mfe_delta": -0.01,
        "median_mae_delta": +0.02,
    },
    "reject_rule_tighten": {
        "coverage_rate_delta": -0.04,
        "usable_discovery_rate_delta": -0.01,
        "severe_miss_rate_delta": +0.03,
        "false_negative_reject_rate_delta": +0.05,
        "late_chase_rate_delta": -0.01,
        "fake_breakout_rate_delta": -0.03,
        "data_gap_rate_delta": 0.0,
        "median_mfe_delta": 0.0,
        "median_mae_delta": -0.01,
    },
    "cohort_filter_widen": {
        "coverage_rate_delta": +0.03,
        "usable_discovery_rate_delta": -0.01,
        "severe_miss_rate_delta": -0.01,
        "false_negative_reject_rate_delta": -0.01,
        "late_chase_rate_delta": +0.01,
        "fake_breakout_rate_delta": +0.02,
        "data_gap_rate_delta": -0.01,
        "median_mfe_delta": 0.0,
        "median_mae_delta": +0.01,
    },
    "cohort_filter_narrow": {
        "coverage_rate_delta": -0.03,
        "usable_discovery_rate_delta": +0.01,
        "severe_miss_rate_delta": +0.01,
        "false_negative_reject_rate_delta": +0.01,
        "late_chase_rate_delta": -0.01,
        "fake_breakout_rate_delta": -0.02,
        "data_gap_rate_delta": +0.01,
        "median_mfe_delta": 0.0,
        "median_mae_delta": 0.0,
    },
    "noop": {
        "coverage_rate_delta": 0.0,
        "usable_discovery_rate_delta": 0.0,
        "severe_miss_rate_delta": 0.0,
        "false_negative_reject_rate_delta": 0.0,
        "late_chase_rate_delta": 0.0,
        "fake_breakout_rate_delta": 0.0,
        "data_gap_rate_delta": 0.0,
        "median_mfe_delta": 0.0,
        "median_mae_delta": 0.0,
    },
}


_DELTA_KEYS: Tuple[str, ...] = tuple(_BASE_VECTORS["noop"].keys())


def _magnitude(change: HypotheticalRuleChange) -> float:
    """Deterministic magnitude scalar in [0.25, 2.0].

    For numeric baseline/sandbox values, magnitude scales with relative
    change. For non-numeric values, magnitude is fixed at 1.0.
    Capped to keep first-order linearization defensible.
    """
    b = change.baseline_value
    s = change.sandbox_value
    if isinstance(b, (int, float)) and isinstance(s, (int, float)):
        denom = abs(float(b)) if abs(float(b)) > 1e-9 else 1.0
        rel = abs(float(s) - float(b)) / denom
        # Map rel in [0, +inf) to [0.25, 2.0] with saturation.
        m = 0.25 + min(rel, 1.0) * 1.75
        return round(m, 6)
    return 1.0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class OfflineRuleSandboxEngine:
    """Deterministic offline replay engine.

    The engine is pure: same inputs -> same outputs. It does not read clocks,
    files, or environment except via the explicit `now_utc` injection point
    used only to stamp generated_at_utc.
    """

    def __init__(self, *, clip_metrics: bool = True) -> None:
        self._clip = clip_metrics
        # Defensive tripwires: guarantee the engine cannot accidentally
        # advertise capabilities it must never have.
        self.sandbox_only = True
        self.writes_runtime_config = False
        self.auto_tuning_allowed = False
        self.trade_authority = False
        self.phase_12_forbidden = True

    # -- public API ---------------------------------------------------------

    def evaluate_scenario(
        self, sandbox_input: OfflineRuleSandboxInput
    ) -> OfflineRuleSandboxResult:
        baseline = self._extract_baseline(sandbox_input)
        data_gap_warnings = self._collect_data_gap_warnings(sandbox_input)

        # Determine status from evidence completeness.
        missing_keys = [
            k for k in _BASELINE_METRIC_KEYS if k not in baseline
        ]
        if len(missing_keys) >= max(3, len(_BASELINE_METRIC_KEYS) // 2):
            return self._inconclusive_result(
                sandbox_input.scenario.scenario_id,
                baseline,
                data_gap_warnings,
                reason=(
                    f"insufficient_evidence: missing baseline keys="
                    f"{sorted(missing_keys)}"
                ),
            )

        deltas = self._compute_deltas(sandbox_input.scenario)
        sandbox_metrics = self._apply_deltas(baseline, deltas)

        likely_benefits, likely_risks = self._classify_effects(deltas)
        overfit_warnings = self._collect_overfit_warnings(
            sandbox_input.scenario, baseline
        )

        recommendation = self._recommend(
            deltas=deltas,
            data_gap_warnings=data_gap_warnings,
            overfit_warnings=overfit_warnings,
            missing_keys=missing_keys,
        )

        status = (
            SandboxStatus.INCONCLUSIVE
            if recommendation == RecommendationLevel.INCONCLUSIVE
            else SandboxStatus.COMPLETED
        )

        result = OfflineRuleSandboxResult(
            scenario_id=sandbox_input.scenario.scenario_id,
            status=status,
            baseline_metrics=baseline,
            sandbox_metrics=sandbox_metrics,
            delta_metrics=deltas,
            likely_benefits=tuple(likely_benefits),
            likely_risks=tuple(likely_risks),
            overfit_warnings=tuple(overfit_warnings),
            data_gap_warnings=tuple(data_gap_warnings),
            recommendation_level=recommendation,
        )
        # Defensive: refuse to emit results that contain forbidden field
        # names anywhere (e.g., via a hostile baseline payload).
        assert_no_forbidden_fields(result.to_dict())
        return result

    def build_report(
        self,
        *,
        reference_window: str,
        sandbox_inputs: Sequence[OfflineRuleSandboxInput],
        now_utc: Optional[datetime] = None,
        report_id: Optional[str] = None,
    ) -> OfflineRuleSandboxReport:
        results = tuple(self.evaluate_scenario(si) for si in sandbox_inputs)
        scenarios = tuple(si.scenario for si in sandbox_inputs)

        best_review = tuple(
            r.scenario_id
            for r in results
            if r.recommendation_level
            == RecommendationLevel.PROMISING_FOR_PAPER_SHADOW
        )
        rejected = tuple(
            r.scenario_id
            for r in results
            if r.recommendation_level
            == RecommendationLevel.REJECTED_BY_EVIDENCE
        )
        known_gaps = tuple(
            sorted(
                {
                    w
                    for r in results
                    for w in r.data_gap_warnings
                }
            )
        )

        generated_at = (
            now_utc if now_utc is not None else datetime.now(timezone.utc)
        )
        # Determinism: caller may inject `now_utc` for fully reproducible
        # runs (tests do this).
        generated_at_iso = generated_at.replace(microsecond=0).isoformat()

        if report_id is None:
            report_id = self._derive_report_id(
                reference_window=reference_window,
                results=results,
                generated_at_iso=generated_at_iso,
            )

        report = OfflineRuleSandboxReport(
            report_id=report_id,
            generated_at_utc=generated_at_iso,
            reference_window=reference_window,
            scenarios=scenarios,
            scenario_results=results,
            best_review_candidates=best_review,
            rejected_scenarios=rejected,
            known_gaps=known_gaps,
        )
        assert_no_forbidden_fields(report.to_dict())
        return report

    # -- internal helpers ---------------------------------------------------

    def _extract_baseline(
        self, sandbox_input: OfflineRuleSandboxInput
    ) -> Dict[str, float]:
        """Read baseline metric keys from baseline_discovery_quality only.

        Other inputs (post_discovery_outcomes, reject_attributions, ...) are
        kept available for warning checks but are NOT silently combined into
        a fictional baseline.
        """
        bdq = sandbox_input.baseline_discovery_quality or {}
        out: Dict[str, float] = {}
        for k in _BASELINE_METRIC_KEYS:
            v = bdq.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out[k] = float(v)
        return out

    def _collect_data_gap_warnings(
        self, sandbox_input: OfflineRuleSandboxInput
    ) -> List[str]:
        warns: List[str] = []
        if not sandbox_input.baseline_discovery_quality:
            warns.append("baseline_discovery_quality_empty")
        if not sandbox_input.post_discovery_outcomes:
            warns.append("post_discovery_outcomes_empty")
        if not sandbox_input.reject_attributions:
            warns.append("reject_attributions_empty")
        if not sandbox_input.severe_miss_triage:
            warns.append("severe_miss_triage_empty")
        if not sandbox_input.replay_summary:
            warns.append("replay_summary_empty")

        # Surface explicit data_gap_rate from baseline as a warning if high.
        bdq = sandbox_input.baseline_discovery_quality or {}
        gap = bdq.get("data_gap_rate")
        if isinstance(gap, (int, float)) and gap >= 0.10:
            warns.append(f"baseline_data_gap_rate_high={float(gap):.3f}")

        # Surface caller-provided warnings if present.
        for src_name, src in (
            ("baseline_discovery_quality", sandbox_input.baseline_discovery_quality),
            ("replay_summary", sandbox_input.replay_summary),
            ("reflection_summary", sandbox_input.reflection_summary),
        ):
            if isinstance(src, Mapping):
                w = src.get("data_gap_warnings")
                if isinstance(w, (list, tuple)):
                    for item in w:
                        warns.append(f"{src_name}:{item}")
        # Deterministic, deduped order.
        seen = set()
        out: List[str] = []
        for w in warns:
            if w not in seen:
                seen.add(w)
                out.append(w)
        return out

    def _compute_deltas(
        self, scenario: OfflineRuleSandboxScenario
    ) -> Dict[str, float]:
        deltas: Dict[str, float] = {k: 0.0 for k in _DELTA_KEYS}
        for change in scenario.hypothetical_rule_changes:
            vec = _BASE_VECTORS[change.change_type]
            mag = _magnitude(change)
            for k, v in vec.items():
                deltas[k] = round(deltas[k] + v * mag, 6)
        return deltas

    def _apply_deltas(
        self,
        baseline: Mapping[str, float],
        deltas: Mapping[str, float],
    ) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for k in _BASELINE_METRIC_KEYS:
            if k not in baseline:
                continue
            delta_key = f"{k}_delta"
            d = deltas.get(delta_key, 0.0)
            v = baseline[k] + d
            if self._clip and k.endswith("_rate"):
                v = max(0.0, min(1.0, v))
            out[k] = round(v, 6)
        return out

    def _classify_effects(
        self, deltas: Mapping[str, float]
    ) -> Tuple[List[str], List[str]]:
        benefits: List[str] = []
        risks: List[str] = []

        # Beneficial directions:
        if deltas.get("coverage_rate_delta", 0.0) > 0:
            benefits.append("coverage_rate_increases")
        if deltas.get("usable_discovery_rate_delta", 0.0) > 0:
            benefits.append("usable_discovery_rate_increases")
        if deltas.get("severe_miss_rate_delta", 0.0) < 0:
            benefits.append("severe_miss_rate_decreases")
        if deltas.get("false_negative_reject_rate_delta", 0.0) < 0:
            benefits.append("false_negative_reject_rate_decreases")

        # Risk directions:
        if deltas.get("late_chase_rate_delta", 0.0) > 0:
            risks.append("late_chase_rate_increases")
        if deltas.get("fake_breakout_rate_delta", 0.0) > 0:
            risks.append("fake_breakout_rate_increases")
        if deltas.get("median_mae_delta", 0.0) > 0:
            risks.append("median_mae_increases")
        if deltas.get("data_gap_rate_delta", 0.0) > 0:
            risks.append("data_gap_rate_increases")

        return benefits, risks

    def _collect_overfit_warnings(
        self,
        scenario: OfflineRuleSandboxScenario,
        baseline: Mapping[str, float],
    ) -> List[str]:
        warns: List[str] = []
        # Heuristic: many simultaneous large changes => overfit risk.
        if len(scenario.hypothetical_rule_changes) >= 4:
            warns.append("many_simultaneous_rule_changes")
        # Heuristic: sandbox_value differs from baseline_value by >50% on
        # numeric rules.
        for c in scenario.hypothetical_rule_changes:
            if isinstance(c.baseline_value, (int, float)) and isinstance(
                c.sandbox_value, (int, float)
            ):
                b = float(c.baseline_value)
                s = float(c.sandbox_value)
                denom = abs(b) if abs(b) > 1e-9 else 1.0
                if abs(s - b) / denom > 0.5:
                    warns.append(
                        f"large_relative_change:{c.rule_name}"
                    )
        # Heuristic: short reference window
        rw = scenario.reference_window or ""
        m = re.match(r"^\s*(\d+)\s*([dwhDWH])\s*$", rw)
        if m:
            n = int(m.group(1))
            unit = m.group(2).lower()
            days = n if unit == "d" else (n * 7 if unit == "w" else n / 24.0)
            if days < 14:
                warns.append("short_reference_window")
        return warns

    def _recommend(
        self,
        *,
        deltas: Mapping[str, float],
        data_gap_warnings: Sequence[str],
        overfit_warnings: Sequence[str],
        missing_keys: Sequence[str],
    ) -> str:
        # Conservative rules:
        # 1. If we have no usable baseline at all -> INCONCLUSIVE.
        if missing_keys and len(missing_keys) >= len(_BASELINE_METRIC_KEYS) - 2:
            return RecommendationLevel.INCONCLUSIVE
        # 2. If many data gaps -> INCONCLUSIVE.
        if len(data_gap_warnings) >= 3:
            return RecommendationLevel.INCONCLUSIVE
        # 3. If risks dominate clearly -> REJECTED_BY_EVIDENCE.
        risk_score = (
            max(0.0, deltas.get("fake_breakout_rate_delta", 0.0))
            + max(0.0, deltas.get("late_chase_rate_delta", 0.0))
            + max(0.0, deltas.get("median_mae_delta", 0.0))
        )
        benefit_score = (
            max(0.0, deltas.get("coverage_rate_delta", 0.0))
            + max(0.0, deltas.get("usable_discovery_rate_delta", 0.0))
            + max(0.0, -deltas.get("severe_miss_rate_delta", 0.0))
            + max(0.0, -deltas.get("false_negative_reject_rate_delta", 0.0))
        )
        if risk_score >= benefit_score + 0.05 and risk_score >= 0.05:
            return RecommendationLevel.REJECTED_BY_EVIDENCE
        if risk_score > 0 and risk_score >= benefit_score - 0.02:
            return RecommendationLevel.RISKY
        # 4. Promising path: clear benefit, modest risk, no severe overfit.
        if (
            benefit_score >= risk_score + 0.04
            and benefit_score >= 0.04
            and "many_simultaneous_rule_changes" not in overfit_warnings
        ):
            return RecommendationLevel.PROMISING_FOR_PAPER_SHADOW
        # 5. Default: REVIEW_ONLY.
        return RecommendationLevel.REVIEW_ONLY

    def _inconclusive_result(
        self,
        scenario_id: str,
        baseline: Mapping[str, float],
        data_gap_warnings: Sequence[str],
        reason: str,
    ) -> OfflineRuleSandboxResult:
        return OfflineRuleSandboxResult(
            scenario_id=scenario_id,
            status=SandboxStatus.INSUFFICIENT_EVIDENCE,
            baseline_metrics=dict(baseline),
            sandbox_metrics={},
            delta_metrics={k: 0.0 for k in _DELTA_KEYS},
            likely_benefits=tuple(),
            likely_risks=tuple(),
            overfit_warnings=tuple(),
            data_gap_warnings=tuple(list(data_gap_warnings) + [reason]),
            recommendation_level=RecommendationLevel.INCONCLUSIVE,
        )

    def _derive_report_id(
        self,
        *,
        reference_window: str,
        results: Sequence[OfflineRuleSandboxResult],
        generated_at_iso: str,
    ) -> str:
        h = hashlib.sha256()
        h.update(reference_window.encode("utf-8"))
        h.update(b"|")
        h.update(generated_at_iso.encode("utf-8"))
        for r in results:
            h.update(b"|")
            h.update(
                json.dumps(r.to_dict(), sort_keys=True, default=str).encode(
                    "utf-8"
                )
            )
        return f"offline_rule_sandbox_{h.hexdigest()[:16]}"


# ---------------------------------------------------------------------------
# Example / fixture scenario
# ---------------------------------------------------------------------------


def example_fixture_scenario(
    *, reference_window: str = "60d"
) -> OfflineRuleSandboxScenario:
    """Deterministic example scenario. Marked source=example_fixture.

    Used by the runner ONLY when the operator does not supply a scenario file.
    Never claims to be operator-approved.
    """
    changes = (
        HypotheticalRuleChange(
            rule_name="early_tail_score_threshold",
            baseline_value=0.65,
            sandbox_value=0.55,
            change_type="threshold_decrease",
            rationale="probe whether lower threshold reduces severe miss",
            evidence_refs=("block_b:severe_miss_triage",),
        ),
        HypotheticalRuleChange(
            rule_name="candidate_score_cutoff",
            baseline_value=0.70,
            sandbox_value=0.68,
            change_type="score_cutoff_decrease",
            rationale="probe sensitivity of late chase to mild cutoff drop",
            evidence_refs=("block_c:reject_attributions",),
        ),
    )
    return OfflineRuleSandboxScenario(
        scenario_id="example_fixture_v0",
        name="example fixture: lower thresholds slightly",
        reference_window=reference_window,
        baseline_label="block_b_block_c_ai_checkpoint",
        hypothetical_rule_changes=changes,
        cohort_filters={},
        source_reports=(
            "block_b_integrated_evidence_report.json",
            "block_c_integrated_checkpoint_report.json",
            "ai_integrated_checkpoint_report.json",
        ),
        evidence_refs=("phase_11c_offline_rule_sandbox_replay_v0",),
        source="example_fixture",
    )


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def render_report_markdown(report: OfflineRuleSandboxReport) -> str:
    lines: List[str] = []
    lines.append(f"# Offline Rule Sandbox Replay v0 Report")
    lines.append("")
    lines.append(f"- report_id: `{report.report_id}`")
    lines.append(f"- phase: `{report.phase}`")
    lines.append(f"- generated_at_utc: `{report.generated_at_utc}`")
    lines.append(f"- reference_window: `{report.reference_window}`")
    lines.append(f"- next_allowed_phase: `{report.next_allowed_phase}`")
    lines.append("")
    lines.append("## Safety Boundary")
    lines.append("")
    lines.append(f"- sandbox_only: `{report.sandbox_only}`")
    lines.append(f"- writes_runtime_config: `{report.writes_runtime_config}`")
    lines.append(f"- auto_tuning_allowed: `{report.auto_tuning_allowed}`")
    lines.append(f"- trade_authority: `{report.trade_authority}`")
    lines.append(f"- phase_12_forbidden: `{report.phase_12_forbidden}`")
    lines.append("")
    lines.append("## Scenario Results")
    lines.append("")
    if not report.scenario_results:
        lines.append("_no scenarios evaluated_")
    for r in report.scenario_results:
        lines.append(f"### scenario `{r.scenario_id}`")
        lines.append("")
        lines.append(f"- status: `{r.status}`")
        lines.append(f"- recommendation_level: `{r.recommendation_level}`")
        if r.delta_metrics:
            lines.append("- delta_metrics:")
            for k in sorted(r.delta_metrics.keys()):
                lines.append(f"  - `{k}`: `{r.delta_metrics[k]:+.6f}`")
        if r.likely_benefits:
            lines.append("- likely_benefits:")
            for b in r.likely_benefits:
                lines.append(f"  - {b}")
        if r.likely_risks:
            lines.append("- likely_risks:")
            for x in r.likely_risks:
                lines.append(f"  - {x}")
        if r.overfit_warnings:
            lines.append("- overfit_warnings:")
            for w in r.overfit_warnings:
                lines.append(f"  - {w}")
        if r.data_gap_warnings:
            lines.append("- data_gap_warnings:")
            for w in r.data_gap_warnings:
                lines.append(f"  - {w}")
        lines.append("")
    lines.append("## Best Review Candidates")
    lines.append("")
    if report.best_review_candidates:
        for sid in report.best_review_candidates:
            lines.append(f"- `{sid}`")
    else:
        lines.append("_none_")
    lines.append("")
    lines.append("## Rejected Scenarios")
    lines.append("")
    if report.rejected_scenarios:
        for sid in report.rejected_scenarios:
            lines.append(f"- `{sid}`")
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
        "> This report does NOT authorize live trading, does NOT write "
        "runtime config, and does NOT enter Phase 12."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scenario / input parsing helpers (used by runner; pure functions)
# ---------------------------------------------------------------------------


def parse_scenario_dict(payload: Mapping[str, Any]) -> OfflineRuleSandboxScenario:
    raw_changes = payload.get("hypothetical_rule_changes", []) or []
    changes: List[HypotheticalRuleChange] = []
    for c in raw_changes:
        changes.append(
            HypotheticalRuleChange(
                rule_name=str(c["rule_name"]),
                baseline_value=c.get("baseline_value"),
                sandbox_value=c.get("sandbox_value"),
                change_type=str(c["change_type"]),
                rationale=str(c.get("rationale", "")),
                evidence_refs=tuple(c.get("evidence_refs", []) or []),
            )
        )
    return OfflineRuleSandboxScenario(
        scenario_id=str(payload["scenario_id"]),
        name=str(payload.get("name", payload["scenario_id"])),
        reference_window=str(payload.get("reference_window", "")),
        baseline_label=str(payload.get("baseline_label", "")),
        hypothetical_rule_changes=tuple(changes),
        cohort_filters=dict(payload.get("cohort_filters", {}) or {}),
        source_reports=tuple(payload.get("source_reports", []) or []),
        evidence_refs=tuple(payload.get("evidence_refs", []) or []),
        source=str(payload.get("source", "operator_supplied")),
    )


def build_input_from_reports(
    *,
    scenario: OfflineRuleSandboxScenario,
    block_b_report: Mapping[str, Any] | None,
    block_c_report: Mapping[str, Any] | None,
    ai_checkpoint_report: Mapping[str, Any] | None,
) -> OfflineRuleSandboxInput:
    """Pure function: assemble OfflineRuleSandboxInput from report dicts.

    Reports are read for evidence only. Nothing is written back. Missing
    fields are tolerated and surface as data_gap_warnings downstream.
    """

    def _safe_section(d: Mapping[str, Any] | None, key: str) -> Mapping[str, Any]:
        if not isinstance(d, Mapping):
            return {}
        v = d.get(key)
        return v if isinstance(v, Mapping) else {}

    bdq: Dict[str, Any] = {}
    bdq.update(_safe_section(block_b_report, "discovery_quality"))
    bdq.update(_safe_section(block_c_report, "discovery_quality"))
    bdq.update(_safe_section(ai_checkpoint_report, "discovery_quality"))

    pdo = dict(_safe_section(block_b_report, "post_discovery_outcomes"))
    pdo.update(_safe_section(block_c_report, "post_discovery_outcomes"))

    rej = dict(_safe_section(block_b_report, "reject_attributions"))
    rej.update(_safe_section(block_c_report, "reject_attributions"))

    smt = dict(_safe_section(block_b_report, "severe_miss_triage"))
    smt.update(_safe_section(block_c_report, "severe_miss_triage"))

    rep = dict(_safe_section(block_b_report, "replay_summary"))
    rep.update(_safe_section(block_c_report, "replay_summary"))

    refl = dict(_safe_section(ai_checkpoint_report, "reflection_summary"))

    evidence_refs: List[str] = []
    for name, src in (
        ("block_b", block_b_report),
        ("block_c", block_c_report),
        ("ai_checkpoint", ai_checkpoint_report),
    ):
        if isinstance(src, Mapping):
            rid = src.get("report_id") or src.get("id")
            if rid:
                evidence_refs.append(f"{name}:{rid}")

    return OfflineRuleSandboxInput(
        baseline_discovery_quality=bdq,
        post_discovery_outcomes=pdo,
        reject_attributions=rej,
        severe_miss_triage=smt,
        replay_summary=rep,
        reflection_summary=refl,
        scenario=scenario,
        evidence_refs=tuple(evidence_refs),
    )


# ---------------------------------------------------------------------------
# Module-level integrity guards
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
