"""Phase 11C - Offline Rule Sandbox Replay v0.

Paper / report / evidence-only layer. Lets an operator answer
hypothetical questions about how a rule change would have moved
**discovery quality** over a frozen historical reference window:

  - If we lowered the early-tail-score threshold, would the
    severe-miss rate drop?
  - If we tightened the candidate-score cutoff, would the
    late-chase rate rise?
  - If we relaxed a reject rule, would the false-negative reject
    rate fall?
  - If a rule change brings more fake breakouts, is it worth
    advancing?

The engine NEVER trades. It NEVER calls Risk, Execution, the
Exchange Gateway, Telegram outbound, an LLM, or DeepSeek. It
NEVER imports :mod:`app.risk`, :mod:`app.execution`,
:mod:`app.exchanges`, :mod:`app.telegram`, :mod:`app.config`, or
any HTTP / WebSocket / network library. It NEVER writes back
runtime configuration. It NEVER auto-tunes. The Risk Engine
remains the single trade-decision gate. Phase 12 remains
FORBIDDEN.

What the engine does
====================

  - Reads a baseline discovery-quality picture (counters /
    rates) plus optional historical roll-ups
    (post-discovery outcomes, reject attribution, severe miss
    triage, replay summary, reflection summary) from frozen
    JSON files supplied by the runner.
  - Reads an :class:`OfflineRuleSandboxScenario` describing one
    or more :class:`HypotheticalRuleChange` entries. The
    scenario is **hypothetical**, not a runtime patch; we
    intentionally avoid the ``*_patch`` vocabulary.
  - Projects each rule change onto the baseline metrics through
    a small **closed deterministic impact table**, producing
    sandbox metrics + delta metrics. The projection is a
    direction-and-magnitude *hint*, not a prediction of truth;
    every payload labels it as commentary substrate.
  - Surfaces ``likely_benefits`` / ``likely_risks`` /
    ``overfit_warnings`` / ``data_gap_warnings`` /
    ``recommendation_level`` from the closed
    :data:`RECOMMENDATION_LEVELS` vocabulary
    (``REVIEW_ONLY`` / ``INCONCLUSIVE`` /
    ``PROMISING_FOR_PAPER_SHADOW`` / ``RISKY`` /
    ``REJECTED_BY_EVIDENCE``). It NEVER emits ``APPLY`` /
    ``DEPLOY`` / ``ENABLE_LIVE`` / ``TRADE`` /
    ``BUY`` / ``SELL``.
  - Aggregates per-scenario results into one
    :class:`OfflineRuleSandboxReport` and serialises it to JSON
    + Markdown.

Forbidden output keys
=====================

The engine refuses to emit any of the keys in
:data:`FORBIDDEN_SANDBOX_PAYLOAD_KEYS` at any nesting depth -
this includes every direction / sizing / leverage / stop /
target / risk-budget / order / runtime-config-patch /
"signal-to-trade" / "should buy/short" / "apply" / "deploy" /
"enable_live" alias the brief calls out. A defensive recursive
guard (:func:`_assert_no_forbidden_keys`) runs at every payload
serialisation boundary.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Identity / constants
# ---------------------------------------------------------------------------
SANDBOX_SOURCE_PHASE: str = (
    "phase_11c_offline_rule_sandbox_replay_v0"
)
SANDBOX_SCENARIO_SCHEMA_VERSION: str = (
    "phase_11c.offline_rule_sandbox_scenario.v1"
)
SANDBOX_RESULT_SCHEMA_VERSION: str = (
    "phase_11c.offline_rule_sandbox_result.v1"
)
SANDBOX_REPORT_SCHEMA_VERSION: str = (
    "phase_11c.offline_rule_sandbox_report.v1"
)


# Closed report / replay event-name vocabulary (string labels
# only; we do NOT extend ``app.core.events.EventType`` because
# the brief restricts allowed file modifications to the sandbox
# package, the runner, the test, and a handful of docs).
SANDBOX_EVENT_REPLAY_RUN: str = (
    "OFFLINE_RULE_SANDBOX_REPLAY_RUN"
)
SANDBOX_EVENT_SCENARIO_EVALUATED: str = (
    "OFFLINE_RULE_SANDBOX_SCENARIO_EVALUATED"
)
SANDBOX_EVENT_REPORT_GENERATED: str = (
    "OFFLINE_RULE_SANDBOX_REPORT_GENERATED"
)


# ---------------------------------------------------------------------------
# Recommendation vocabulary (CLOSED).
# ---------------------------------------------------------------------------
#: The only legal values for ``OfflineRuleSandboxResult.recommendation_level``.
#: NEVER includes APPLY / DEPLOY / ENABLE_LIVE / TRADE / BUY / SELL.
RECOMMENDATION_REVIEW_ONLY: str = "REVIEW_ONLY"
RECOMMENDATION_INCONCLUSIVE: str = "INCONCLUSIVE"
RECOMMENDATION_PROMISING_FOR_PAPER_SHADOW: str = (
    "PROMISING_FOR_PAPER_SHADOW"
)
RECOMMENDATION_RISKY: str = "RISKY"
RECOMMENDATION_REJECTED_BY_EVIDENCE: str = "REJECTED_BY_EVIDENCE"

RECOMMENDATION_LEVELS: frozenset[str] = frozenset(
    {
        RECOMMENDATION_REVIEW_ONLY,
        RECOMMENDATION_INCONCLUSIVE,
        RECOMMENDATION_PROMISING_FOR_PAPER_SHADOW,
        RECOMMENDATION_RISKY,
        RECOMMENDATION_REJECTED_BY_EVIDENCE,
    }
)


# Per-scenario status taxonomy. None of these is a trade-approval
# label; they describe how the engine evaluated the scenario.
STATUS_EVALUATED: str = "EVALUATED"
STATUS_INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"
STATUS_INCONCLUSIVE: str = "INCONCLUSIVE"
STATUS_REJECTED: str = "REJECTED"


# Next-allowed phase vocabulary (paper / read-only only).
NEXT_PHASE_PAPER_SHADOW_PREP: str = (
    "Paper Shadow Strategy Validation preparation "
    "(paper / read-only)"
)
NEXT_PHASE_NEEDS_OPERATOR_REVIEW: str = (
    "Operator review of sandbox scenario "
    "(paper / read-only)"
)
NEXT_PHASE_NEEDS_MORE_EVIDENCE: str = (
    "Needs more historical evidence before re-running "
    "the sandbox (paper / read-only)"
)


# ---------------------------------------------------------------------------
# Forbidden-payload guard (defensive)
# ---------------------------------------------------------------------------
#: Keys that MUST NEVER appear at any nesting depth in any
#: payload the sandbox emits. Mirrors the project-wide AI-Layer
#: forbidden vocabulary plus the brief's "additive" Offline Rule
#: Sandbox list.
FORBIDDEN_SANDBOX_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        # Direction / trade-decision keys.
        "buy",
        "sell",
        "long",
        "short",
        "direction",
        "side",
        "entry",
        "exit",
        # Sizing / leverage / risk-budget keys.
        "position_size",
        "leverage",
        "stop",
        "stop_loss",
        "stop_price",
        "target",
        "target_price",
        "take_profit",
        "risk_budget",
        "order",
        "order_type",
        "execution_command",
        # Runtime-config patch keys.
        "runtime_config_patch",
        "symbol_limit_patch",
        "threshold_patch",
        "candidate_pool_patch",
        "regime_weight_patch",
        "strategy_parameter_patch",
        # Signal-to-trade / apply / deploy aliases.
        "signal_to_trade",
        "should_buy",
        "should_short",
        "apply_change",
        "deploy_change",
        "enable_live",
        # Defensive aliases.
        "trading_approved",
        "live_ready",
        "live_trading_allowed",
        "phase_12_allowed",
    }
)


def _assert_no_forbidden_keys(payload: Any, *, context: str) -> None:
    """Raise :class:`ValueError` if a forbidden key appears at any
    nesting depth.
    """

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_str = str(key)
            if key_str in FORBIDDEN_SANDBOX_PAYLOAD_KEYS:
                raise ValueError(
                    f"offline_rule_sandbox produced a forbidden payload "
                    f"key {key_str!r} in {context!r}; this is a hard "
                    "violation of the Phase 11C Offline Rule Sandbox "
                    "Replay v0 boundary."
                )
            _assert_no_forbidden_keys(value, context=context)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            _assert_no_forbidden_keys(item, context=context)


# ---------------------------------------------------------------------------
# Safety flags (re-pinned at every serialisation boundary)
# ---------------------------------------------------------------------------
def safety_flags_dict() -> dict[str, Any]:
    """Return the project-wide Phase 11C safety flags the sandbox
    re-pins at every serialisation boundary.
    """

    return {
        "mode": "paper",
        "live_trading": False,
        "exchange_live_orders": False,
        "right_tail": False,
        "llm": False,
        "llm_outbound_enabled": False,
        "sandbox_only": True,
        "allow_trade_decision": False,
        "allow_runtime_config_change": False,
        "auto_tuning_allowed": False,
        "telegram_outbound_enabled": False,
        "binance_private_api_enabled": False,
    }


# ---------------------------------------------------------------------------
# Closed deterministic impact table
# ---------------------------------------------------------------------------
# Each entry maps a rule_name -> the unit-direction the metric
# moves when the rule is *loosened* by one normalised unit. A
# *tightened* change flips the sign. A *no_change* / unknown
# change_type contributes 0 for every metric. The magnitude of
# the projected delta is the unit direction times the
# normalised relative change clipped to [-1, +1].
#
# The metrics are deliberately small-positive numbers in [0, 1]:
# this is a deterministic projection layer, not a real
# simulator. Every payload labels them as commentary substrate.
_LOOSEN_DIRECTIONS: dict[str, dict[str, float]] = {
    # The early-tail-score threshold gates entry into the early
    # candidate pool. Lowering it (loosen) lets more candidates
    # in: coverage UP, severe-miss DOWN, but late-chase /
    # fake-breakout / data-gap UP.
    "early_tail_score_threshold": {
        "coverage_rate": +1.0,
        "usable_discovery_rate": +0.4,
        "severe_miss_rate": -1.0,
        "false_negative_reject_rate": -0.6,
        "late_chase_rate": +0.7,
        "fake_breakout_rate": +0.6,
        "data_gap_rate": +0.3,
        "median_mfe": -0.2,
        "median_mae": +0.4,
    },
    # Candidate-score cutoff gates discovery output. Lowering it
    # (loosen) increases coverage but also late-chase /
    # fake-breakout.
    "candidate_score_cutoff": {
        "coverage_rate": +0.8,
        "usable_discovery_rate": +0.2,
        "severe_miss_rate": -0.7,
        "false_negative_reject_rate": -0.5,
        "late_chase_rate": +0.8,
        "fake_breakout_rate": +0.7,
        "data_gap_rate": +0.2,
        "median_mfe": -0.3,
        "median_mae": +0.5,
    },
    # Reject rule magnitude. Loosening (less strict reject)
    # reduces false-negative-reject but raises fake-breakout /
    # late-chase / data-gap.
    "reject_rule_strictness": {
        "coverage_rate": +0.6,
        "usable_discovery_rate": +0.1,
        "severe_miss_rate": -0.5,
        "false_negative_reject_rate": -1.0,
        "late_chase_rate": +0.5,
        "fake_breakout_rate": +0.6,
        "data_gap_rate": +0.4,
        "median_mfe": -0.1,
        "median_mae": +0.3,
    },
    # Anomaly threshold gates the pre-anomaly path. Lowering it
    # (loosen) increases coverage but also data-gap noise.
    "anomaly_threshold": {
        "coverage_rate": +0.7,
        "usable_discovery_rate": +0.2,
        "severe_miss_rate": -0.6,
        "false_negative_reject_rate": -0.3,
        "late_chase_rate": +0.4,
        "fake_breakout_rate": +0.5,
        "data_gap_rate": +0.6,
        "median_mfe": -0.2,
        "median_mae": +0.3,
    },
    # Liquidity floor. Loosen = lower floor = more candidates
    # but more fake breakouts and data-gap.
    "liquidity_floor": {
        "coverage_rate": +0.5,
        "usable_discovery_rate": -0.1,
        "severe_miss_rate": -0.3,
        "false_negative_reject_rate": -0.2,
        "late_chase_rate": +0.3,
        "fake_breakout_rate": +0.7,
        "data_gap_rate": +0.5,
        "median_mfe": -0.2,
        "median_mae": +0.4,
    },
    # Catch-all generic rule. Conservative directional hint.
    "generic_rule": {
        "coverage_rate": +0.3,
        "usable_discovery_rate": +0.1,
        "severe_miss_rate": -0.2,
        "false_negative_reject_rate": -0.2,
        "late_chase_rate": +0.2,
        "fake_breakout_rate": +0.2,
        "data_gap_rate": +0.1,
        "median_mfe": -0.1,
        "median_mae": +0.1,
    },
}


_METRIC_NAMES: tuple[str, ...] = (
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


_DELTA_FIELD_BY_METRIC: dict[str, str] = {
    "coverage_rate": "coverage_rate_delta",
    "usable_discovery_rate": "usable_discovery_rate_delta",
    "severe_miss_rate": "severe_miss_rate_delta",
    "false_negative_reject_rate": (
        "false_negative_reject_rate_delta"
    ),
    "late_chase_rate": "late_chase_rate_delta",
    "fake_breakout_rate": "fake_breakout_rate_delta",
    "data_gap_rate": "data_gap_rate_delta",
    "median_mfe": "median_mfe_delta",
    "median_mae": "median_mae_delta",
}


# Closed change-type vocabulary.
_CHANGE_LOOSEN: str = "loosen"
_CHANGE_TIGHTEN: str = "tighten"
_CHANGE_NO_CHANGE: str = "no_change"
_VALID_CHANGE_TYPES: frozenset[str] = frozenset(
    {_CHANGE_LOOSEN, _CHANGE_TIGHTEN, _CHANGE_NO_CHANGE}
)


# Per-metric "improvement is..." direction. +1 means HIGHER is
# better, -1 means LOWER is better. Used to classify deltas as
# benefits vs. risks.
_METRIC_IS_GOOD_HIGHER: dict[str, int] = {
    "coverage_rate": +1,
    "usable_discovery_rate": +1,
    "severe_miss_rate": -1,
    "false_negative_reject_rate": -1,
    "late_chase_rate": -1,
    "fake_breakout_rate": -1,
    "data_gap_rate": -1,
    "median_mfe": +1,
    "median_mae": -1,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        if math.isnan(float(value)) or math.isinf(float(value)):
            return default
        return float(value)
    if isinstance(value, str):
        try:
            x = float(value)
        except ValueError:
            return default
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    return default


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return str(value)


def _round6(x: float) -> float:
    """Round to 6 decimal places (deterministic JSON output)."""

    return float(f"{x:.6f}")


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _normalised_change_magnitude(
    *, baseline: float, sandbox: float, change_type: str
) -> float:
    """Return a magnitude in [0, 1] describing how big the rule
    change is, normalised against ``max(|baseline|, |sandbox|)``.

    For ``change_type=no_change`` the magnitude is 0 regardless of
    the numeric values. For unknown / non-numeric values the
    magnitude is 0.5 (a conservative middle).
    """

    if change_type == _CHANGE_NO_CHANGE:
        return 0.0
    base = abs(_safe_float(baseline, default=0.0))
    sand = abs(_safe_float(sandbox, default=0.0))
    denom = max(base, sand)
    if denom <= 0.0:
        # Fall back to a fixed conservative magnitude when both
        # values are zero / non-numeric.
        return 0.5
    diff = abs(sand - base)
    return _clip(diff / denom, 0.0, 1.0)


def _change_sign(change_type: str) -> int:
    """Return +1 for loosen, -1 for tighten, 0 for no_change."""

    if change_type == _CHANGE_LOOSEN:
        return +1
    if change_type == _CHANGE_TIGHTEN:
        return -1
    return 0


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HypotheticalRuleChange:
    """One hypothetical rule change considered by a scenario.

    This is **not** a runtime patch. The field naming intentionally
    avoids the ``*_patch`` vocabulary so the type cannot be
    misread as something the sandbox is allowed to write back to
    the runtime config.
    """

    rule_name: str
    baseline_value: Any
    sandbox_value: Any
    change_type: str
    rationale: str = ""
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "rule_name": str(self.rule_name),
            "baseline_value": self.baseline_value,
            "sandbox_value": self.sandbox_value,
            "change_type": str(self.change_type),
            "rationale": str(self.rationale or ""),
            "evidence_refs": list(self.evidence_refs),
            # Hard pins so a downstream consumer cannot misread
            # this as a runtime patch.
            "is_runtime_patch": False,
            "writes_runtime_config": False,
            "auto_tuning_allowed": False,
        }
        _assert_no_forbidden_keys(
            payload, context="hypothetical_rule_change"
        )
        return payload


@dataclass(frozen=True)
class OfflineRuleSandboxScenario:
    """One scenario the sandbox engine evaluates.

    A scenario is the combination of a baseline label (what the
    operator is comparing against), a list of hypothetical rule
    changes, optional cohort filters, and the source-report list
    the operator wants to anchor the projection on.
    """

    scenario_id: str
    name: str
    reference_window: str
    baseline_label: str
    hypothetical_rule_changes: tuple[HypotheticalRuleChange, ...]
    cohort_filters: tuple[str, ...] = ()
    source_reports: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    source: str = "operator_supplied"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SANDBOX_SCENARIO_SCHEMA_VERSION,
            "source_phase": SANDBOX_SOURCE_PHASE,
            "scenario_id": str(self.scenario_id),
            "name": str(self.name),
            "reference_window": str(self.reference_window),
            "baseline_label": str(self.baseline_label),
            "hypothetical_rule_changes": [
                hrc.to_dict()
                for hrc in self.hypothetical_rule_changes
            ],
            "cohort_filters": list(self.cohort_filters),
            "source_reports": list(self.source_reports),
            "evidence_refs": list(self.evidence_refs),
            "source": str(self.source),
            # Hard pins.
            "sandbox_only": True,
            "writes_runtime_config": False,
            "auto_tuning_allowed": False,
            "trade_authority": False,
            "phase_12_forbidden": True,
        }
        _assert_no_forbidden_keys(
            payload, context="offline_rule_sandbox_scenario"
        )
        return payload


@dataclass(frozen=True)
class OfflineRuleSandboxInput:
    """Frozen input bundle the engine evaluates.

    All fields are mappings of plain JSON-serialisable values
    pulled from local report files by the runner. The engine
    never opens a network socket and never reaches into runtime
    state.
    """

    scenario: OfflineRuleSandboxScenario
    baseline_discovery_quality: Mapping[str, Any] = field(
        default_factory=dict
    )
    post_discovery_outcomes: Mapping[str, Any] = field(
        default_factory=dict
    )
    reject_attributions: Mapping[str, Any] = field(
        default_factory=dict
    )
    severe_miss_triage: Mapping[str, Any] = field(
        default_factory=dict
    )
    replay_summary: Mapping[str, Any] = field(default_factory=dict)
    reflection_summary: Mapping[str, Any] = field(
        default_factory=dict
    )
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "scenario": self.scenario.to_dict(),
            "baseline_discovery_quality": dict(
                self.baseline_discovery_quality or {}
            ),
            "post_discovery_outcomes": dict(
                self.post_discovery_outcomes or {}
            ),
            "reject_attributions": dict(
                self.reject_attributions or {}
            ),
            "severe_miss_triage": dict(
                self.severe_miss_triage or {}
            ),
            "replay_summary": dict(self.replay_summary or {}),
            "reflection_summary": dict(
                self.reflection_summary or {}
            ),
            "evidence_refs": list(self.evidence_refs),
            # Hard pins re-applied at the input boundary too
            # so a downstream consumer cannot misread the input
            # as a runtime patch.
            "sandbox_only": True,
            "writes_runtime_config": False,
            "auto_tuning_allowed": False,
            "trade_authority": False,
            "phase_12_forbidden": True,
        }
        _assert_no_forbidden_keys(
            payload, context="offline_rule_sandbox_input"
        )
        return payload


@dataclass(frozen=True)
class OfflineRuleSandboxResult:
    """One scenario's evaluated result."""

    scenario_id: str
    status: str
    baseline_metrics: Mapping[str, float]
    sandbox_metrics: Mapping[str, float]
    delta_metrics: Mapping[str, float]
    likely_benefits: tuple[str, ...]
    likely_risks: tuple[str, ...]
    overfit_warnings: tuple[str, ...]
    data_gap_warnings: tuple[str, ...]
    recommendation_level: str
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        if self.recommendation_level not in RECOMMENDATION_LEVELS:
            raise ValueError(
                f"recommendation_level "
                f"{self.recommendation_level!r} is not in the "
                f"closed sandbox vocabulary "
                f"{sorted(RECOMMENDATION_LEVELS)!r}"
            )
        payload: dict[str, Any] = {
            "schema_version": SANDBOX_RESULT_SCHEMA_VERSION,
            "source_phase": SANDBOX_SOURCE_PHASE,
            "scenario_id": str(self.scenario_id),
            "status": str(self.status),
            "baseline_metrics": {
                k: _round6(_safe_float(v))
                for k, v in sorted(self.baseline_metrics.items())
            },
            "sandbox_metrics": {
                k: _round6(_safe_float(v))
                for k, v in sorted(self.sandbox_metrics.items())
            },
            "delta_metrics": {
                k: _round6(_safe_float(v))
                for k, v in sorted(self.delta_metrics.items())
            },
            "likely_benefits": list(self.likely_benefits),
            "likely_risks": list(self.likely_risks),
            "overfit_warnings": list(self.overfit_warnings),
            "data_gap_warnings": list(self.data_gap_warnings),
            "recommendation_level": str(self.recommendation_level),
            "notes": list(self.notes),
            # Hard pins.
            "sandbox_only": True,
            "writes_runtime_config": False,
            "auto_tuning_allowed": False,
            "trade_authority": False,
            "phase_12_forbidden": True,
            "ai_output_can_be_truth": False,
            "ai_output_can_be_training_label": False,
            "ai_output_can_be_tail_label": False,
            "ai_output_can_be_strategy_sample": False,
        }
        _assert_no_forbidden_keys(
            payload, context="offline_rule_sandbox_result"
        )
        return payload


@dataclass(frozen=True)
class OfflineRuleSandboxReport:
    """Aggregate report covering one or more scenarios."""

    report_id: str
    generated_at_utc: str
    reference_window: str
    scenarios: tuple[OfflineRuleSandboxScenario, ...]
    scenario_results: tuple[OfflineRuleSandboxResult, ...]
    best_review_candidates: tuple[str, ...]
    rejected_scenarios: tuple[str, ...]
    known_gaps: tuple[str, ...]
    next_allowed_phase: str
    inputs_summary: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": SANDBOX_REPORT_SCHEMA_VERSION,
            "source_phase": SANDBOX_SOURCE_PHASE,
            "report_id": str(self.report_id),
            "generated_at_utc": str(self.generated_at_utc),
            "reference_window": str(self.reference_window),
            "scenarios": [s.to_dict() for s in self.scenarios],
            "scenario_results": [
                r.to_dict() for r in self.scenario_results
            ],
            "best_review_candidates": list(
                self.best_review_candidates
            ),
            "rejected_scenarios": list(self.rejected_scenarios),
            "known_gaps": list(self.known_gaps),
            "next_allowed_phase": str(self.next_allowed_phase),
            "inputs_summary": dict(self.inputs_summary or {}),
            # Hard pins (re-pinned at the report boundary too).
            "phase_12_forbidden": True,
            "auto_tuning_allowed": False,
            "writes_runtime_config": False,
            "trade_authority": False,
            "sandbox_only": True,
            "ai_output_can_be_truth": False,
            "ai_output_can_be_training_label": False,
            "ai_output_can_be_tail_label": False,
            "ai_output_can_be_strategy_sample": False,
            "safety_flags": safety_flags_dict(),
            "forbidden_fields": sorted(
                FORBIDDEN_SANDBOX_PAYLOAD_KEYS
            ),
            "recommendation_levels": sorted(
                RECOMMENDATION_LEVELS
            ),
            "event_names": [
                SANDBOX_EVENT_REPLAY_RUN,
                SANDBOX_EVENT_SCENARIO_EVALUATED,
                SANDBOX_EVENT_REPORT_GENERATED,
            ],
        }
        _assert_no_forbidden_keys(
            payload, context="offline_rule_sandbox_report"
        )
        return payload


# ---------------------------------------------------------------------------
# Baseline metric extraction
# ---------------------------------------------------------------------------
# The baseline-discovery-quality JSON shape is intentionally
# tolerant: the runner may pass a Phase
# 11C.1C-C-B-B-B-D-D Discovery Quality Scorecard JSON, an AI
# Integrated Checkpoint JSON, a Block C Integrated Checkpoint
# JSON, or a hand-crafted dict. We probe a small list of
# alternative paths for each metric and fall back to 0.0 when
# the metric is absent (the engine then surfaces a
# ``data_gap_warning``).
_METRIC_BASELINE_PATHS: dict[str, tuple[tuple[str, ...], ...]] = {
    "coverage_rate": (
        ("coverage_rate",),
        ("baseline", "coverage_rate"),
        ("metrics", "coverage_rate"),
        ("discovery_quality", "coverage_rate"),
        ("capture_recall_rate",),
    ),
    "usable_discovery_rate": (
        ("usable_discovery_rate",),
        ("baseline", "usable_discovery_rate"),
        ("metrics", "usable_discovery_rate"),
    ),
    "severe_miss_rate": (
        ("severe_miss_rate",),
        ("baseline", "severe_miss_rate"),
        ("metrics", "severe_miss_rate"),
    ),
    "false_negative_reject_rate": (
        ("false_negative_reject_rate",),
        ("baseline", "false_negative_reject_rate"),
        ("metrics", "false_negative_reject_rate"),
    ),
    "late_chase_rate": (
        ("late_chase_rate",),
        ("baseline", "late_chase_rate"),
        ("metrics", "late_chase_rate"),
    ),
    "fake_breakout_rate": (
        ("fake_breakout_rate",),
        ("baseline", "fake_breakout_rate"),
        ("metrics", "fake_breakout_rate"),
    ),
    "data_gap_rate": (
        ("data_gap_rate",),
        ("baseline", "data_gap_rate"),
        ("metrics", "data_gap_rate"),
    ),
    "median_mfe": (
        ("median_mfe",),
        ("baseline", "median_mfe"),
        ("metrics", "median_mfe"),
    ),
    "median_mae": (
        ("median_mae",),
        ("baseline", "median_mae"),
        ("metrics", "median_mae"),
    ),
}


def _walk_path(
    root: Mapping[str, Any], path: Sequence[str]
) -> Any | None:
    cursor: Any = root
    for step in path:
        if not isinstance(cursor, Mapping):
            return None
        cursor = cursor.get(step)
    return cursor


def _extract_baseline_metrics(
    *,
    baseline: Mapping[str, Any] | None,
    post_discovery: Mapping[str, Any] | None,
    severe_miss: Mapping[str, Any] | None,
    reject_attribution: Mapping[str, Any] | None,
) -> tuple[dict[str, float], list[str]]:
    """Return ``(metrics, missing_metric_names)`` over the closed
    metric set. Missing metrics fall back to 0.0 and are
    surfaced as data-gap warnings.
    """

    metrics: dict[str, float] = {}
    missing: list[str] = []
    sources: tuple[Mapping[str, Any] | None, ...] = (
        baseline,
        post_discovery,
        severe_miss,
        reject_attribution,
    )

    for metric_name, paths in _METRIC_BASELINE_PATHS.items():
        found: float | None = None
        for source in sources:
            if source is None:
                continue
            for path in paths:
                value = _walk_path(source, path)
                if value is None:
                    continue
                found = _safe_float(value, default=0.0)
                break
            if found is not None:
                break
        if found is None:
            metrics[metric_name] = 0.0
            missing.append(metric_name)
        else:
            metrics[metric_name] = float(found)
    return metrics, missing


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class OfflineRuleSandboxEngine:
    """Deterministic offline sandbox engine.

    The engine carries no mutable state and reaches for nothing
    outside the input payload. Two calls over identical input
    produce identical output (modulo the ``generated_at_utc``
    field, which the runner sets after engine evaluation).
    """

    overfit_change_count_threshold: int = 4
    overfit_relative_change_threshold: float = 0.5
    minimum_evidence_ref_count: int = 1
    insufficient_evidence_metric_threshold: int = 6
    risky_severe_miss_threshold: float = 0.05
    risky_fake_breakout_threshold: float = 0.05
    risky_late_chase_threshold: float = 0.05
    promising_coverage_threshold: float = 0.01
    # Per-unit projection step. A change of magnitude 1.0 with
    # a ``+1.0`` impact direction moves the metric by
    # ``projection_step`` before clipping. The default makes
    # the projection visible without saturating the metric.
    projection_step: float = 0.2

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def evaluate(
        self, sandbox_input: OfflineRuleSandboxInput
    ) -> OfflineRuleSandboxResult:
        """Project ``sandbox_input.scenario`` over the baseline
        metrics and return a :class:`OfflineRuleSandboxResult`.
        """

        baseline_metrics, missing = _extract_baseline_metrics(
            baseline=sandbox_input.baseline_discovery_quality,
            post_discovery=sandbox_input.post_discovery_outcomes,
            severe_miss=sandbox_input.severe_miss_triage,
            reject_attribution=sandbox_input.reject_attributions,
        )

        scenario = sandbox_input.scenario
        rule_changes = list(scenario.hypothetical_rule_changes)

        # Project deltas.
        per_metric_unit_delta: dict[str, float] = {
            m: 0.0 for m in _METRIC_NAMES
        }
        notes: list[str] = []
        any_change = False
        for hrc in rule_changes:
            change_type = hrc.change_type
            if change_type not in _VALID_CHANGE_TYPES:
                notes.append(
                    f"unknown_change_type:{change_type!r}_"
                    f"for_rule:{hrc.rule_name!r}"
                )
                continue
            sign = _change_sign(change_type)
            if sign == 0:
                continue
            magnitude = _normalised_change_magnitude(
                baseline=hrc.baseline_value,
                sandbox=hrc.sandbox_value,
                change_type=change_type,
            )
            if magnitude <= 0.0:
                continue
            any_change = True
            directions = _LOOSEN_DIRECTIONS.get(
                hrc.rule_name, _LOOSEN_DIRECTIONS["generic_rule"]
            )
            for metric, unit in directions.items():
                per_metric_unit_delta[metric] += (
                    sign * magnitude * unit
                )

        # Convert unit-deltas to absolute deltas. The engine is
        # a *projection*, not a simulator: we scale the unit
        # delta by ``projection_step`` and CLIP each metric to
        # a sane range (rates -> [0, 1], median_mfe /
        # median_mae -> [-1, 1]).
        sandbox_metrics: dict[str, float] = {}
        delta_metrics: dict[str, float] = {}
        for metric in _METRIC_NAMES:
            unit = per_metric_unit_delta[metric]
            step = self.projection_step
            raw = baseline_metrics[metric] + unit * step
            if metric in {"median_mfe", "median_mae"}:
                lo, hi = -1.0, 1.0
            else:
                lo, hi = 0.0, 1.0
            sandbox_value = _clip(raw, lo, hi)
            sandbox_metrics[metric] = sandbox_value
            delta_metrics[
                _DELTA_FIELD_BY_METRIC[metric]
            ] = sandbox_value - baseline_metrics[metric]

        # Classify deltas into benefits / risks.
        likely_benefits: list[str] = []
        likely_risks: list[str] = []
        for metric in _METRIC_NAMES:
            delta = delta_metrics[
                _DELTA_FIELD_BY_METRIC[metric]
            ]
            if abs(delta) < 1e-9:
                continue
            sign = _METRIC_IS_GOOD_HIGHER[metric]
            score = sign * delta
            if score > 0:
                likely_benefits.append(
                    f"{metric}_improves_by_{_round6(abs(delta))}"
                )
            else:
                likely_risks.append(
                    f"{metric}_worsens_by_{_round6(abs(delta))}"
                )

        # Data-gap warnings.
        data_gap_warnings: list[str] = []
        for missing_metric in missing:
            data_gap_warnings.append(
                f"baseline_metric_missing:{missing_metric}"
            )
        if not (
            sandbox_input.replay_summary
            or sandbox_input.reflection_summary
            or sandbox_input.post_discovery_outcomes
            or sandbox_input.reject_attributions
            or sandbox_input.severe_miss_triage
        ):
            data_gap_warnings.append(
                "no_historical_summary_supplied"
            )

        # Overfit warnings.
        overfit_warnings: list[str] = []
        if (
            len(rule_changes)
            >= self.overfit_change_count_threshold
        ):
            overfit_warnings.append(
                f"too_many_rule_changes:"
                f"{len(rule_changes)}"
                f">={self.overfit_change_count_threshold}"
            )
        for hrc in rule_changes:
            mag = _normalised_change_magnitude(
                baseline=hrc.baseline_value,
                sandbox=hrc.sandbox_value,
                change_type=hrc.change_type,
            )
            if mag >= self.overfit_relative_change_threshold:
                overfit_warnings.append(
                    f"large_relative_change_for_rule:"
                    f"{hrc.rule_name}:"
                    f"magnitude={_round6(mag)}>="
                    f"{self.overfit_relative_change_threshold}"
                )
        for hrc in rule_changes:
            if (
                len(hrc.evidence_refs)
                < self.minimum_evidence_ref_count
            ):
                overfit_warnings.append(
                    f"rule_change_without_evidence_ref:"
                    f"{hrc.rule_name}"
                )

        # Status / recommendation level.
        evidence_refs_total = sum(
            len(hrc.evidence_refs) for hrc in rule_changes
        )
        evidence_refs_total += len(scenario.evidence_refs)

        if (
            len(missing)
            >= self.insufficient_evidence_metric_threshold
            and not any_change
        ):
            status = STATUS_INSUFFICIENT_EVIDENCE
        elif not any_change:
            status = STATUS_INCONCLUSIVE
        else:
            status = STATUS_EVALUATED

        recommendation_level = self._derive_recommendation_level(
            status=status,
            any_change=any_change,
            sandbox_metrics=sandbox_metrics,
            baseline_metrics=baseline_metrics,
            overfit_warnings=overfit_warnings,
            data_gap_warnings=data_gap_warnings,
            evidence_refs_total=evidence_refs_total,
        )

        return OfflineRuleSandboxResult(
            scenario_id=scenario.scenario_id,
            status=status,
            baseline_metrics=baseline_metrics,
            sandbox_metrics=sandbox_metrics,
            delta_metrics=delta_metrics,
            likely_benefits=tuple(likely_benefits),
            likely_risks=tuple(likely_risks),
            overfit_warnings=tuple(overfit_warnings),
            data_gap_warnings=tuple(data_gap_warnings),
            recommendation_level=recommendation_level,
            notes=tuple(notes),
        )

    def evaluate_many(
        self,
        sandbox_inputs: Iterable[OfflineRuleSandboxInput],
    ) -> list[OfflineRuleSandboxResult]:
        return [self.evaluate(s) for s in sandbox_inputs]

    def build_report(
        self,
        *,
        report_id: str,
        reference_window: str,
        sandbox_inputs: Sequence[OfflineRuleSandboxInput],
        inputs_summary: Mapping[str, Any] | None = None,
        generated_at_utc: str | None = None,
    ) -> OfflineRuleSandboxReport:
        """Run :meth:`evaluate` over every input and assemble a
        :class:`OfflineRuleSandboxReport`.
        """

        results: list[OfflineRuleSandboxResult] = []
        scenarios: list[OfflineRuleSandboxScenario] = []
        for sandbox_input in sandbox_inputs:
            scenarios.append(sandbox_input.scenario)
            results.append(self.evaluate(sandbox_input))

        # Best review candidates: PROMISING_FOR_PAPER_SHADOW
        # first, then REVIEW_ONLY. Stable order = scenario_id
        # alphabetic.
        best_review: list[str] = []
        rejected: list[str] = []
        for r in sorted(
            results, key=lambda r: r.scenario_id
        ):
            if (
                r.recommendation_level
                == RECOMMENDATION_PROMISING_FOR_PAPER_SHADOW
                or r.recommendation_level
                == RECOMMENDATION_REVIEW_ONLY
            ):
                best_review.append(r.scenario_id)
            if (
                r.recommendation_level
                == RECOMMENDATION_REJECTED_BY_EVIDENCE
                or r.recommendation_level
                == RECOMMENDATION_RISKY
            ):
                rejected.append(r.scenario_id)

        # Known gaps roll-up across all scenarios.
        known_gaps: list[str] = []
        for r in results:
            for w in r.data_gap_warnings:
                if w not in known_gaps:
                    known_gaps.append(w)
            for w in r.overfit_warnings:
                if w not in known_gaps:
                    known_gaps.append(w)

        # Next-allowed-phase roll-up.
        if any(
            r.recommendation_level
            == RECOMMENDATION_PROMISING_FOR_PAPER_SHADOW
            for r in results
        ):
            next_phase = NEXT_PHASE_PAPER_SHADOW_PREP
        elif any(
            r.status == STATUS_INSUFFICIENT_EVIDENCE
            for r in results
        ):
            next_phase = NEXT_PHASE_NEEDS_MORE_EVIDENCE
        else:
            next_phase = NEXT_PHASE_NEEDS_OPERATOR_REVIEW

        return OfflineRuleSandboxReport(
            report_id=report_id,
            generated_at_utc=(
                generated_at_utc or _now_utc_iso()
            ),
            reference_window=reference_window,
            scenarios=tuple(scenarios),
            scenario_results=tuple(results),
            best_review_candidates=tuple(best_review),
            rejected_scenarios=tuple(rejected),
            known_gaps=tuple(known_gaps),
            next_allowed_phase=next_phase,
            inputs_summary=dict(inputs_summary or {}),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _derive_recommendation_level(
        self,
        *,
        status: str,
        any_change: bool,
        sandbox_metrics: Mapping[str, float],
        baseline_metrics: Mapping[str, float],
        overfit_warnings: Sequence[str],
        data_gap_warnings: Sequence[str],
        evidence_refs_total: int,
    ) -> str:
        """Closed mapping from internal state to one of
        :data:`RECOMMENDATION_LEVELS`.
        """

        if status == STATUS_INSUFFICIENT_EVIDENCE:
            return RECOMMENDATION_INCONCLUSIVE
        if status == STATUS_INCONCLUSIVE:
            return RECOMMENDATION_INCONCLUSIVE
        # Hard-reject: any of the bad-direction metrics moved
        # past the risky threshold.
        worse_severe = (
            sandbox_metrics["severe_miss_rate"]
            - baseline_metrics["severe_miss_rate"]
        )
        worse_fake = (
            sandbox_metrics["fake_breakout_rate"]
            - baseline_metrics["fake_breakout_rate"]
        )
        worse_late = (
            sandbox_metrics["late_chase_rate"]
            - baseline_metrics["late_chase_rate"]
        )
        if (
            worse_severe >= self.risky_severe_miss_threshold
            or worse_fake
            >= self.risky_fake_breakout_threshold
            or worse_late >= self.risky_late_chase_threshold
        ):
            return RECOMMENDATION_REJECTED_BY_EVIDENCE
        # Overfit / no-evidence -> RISKY.
        if overfit_warnings or evidence_refs_total <= 0:
            return RECOMMENDATION_RISKY
        # Promising: coverage / usable up by a meaningful margin
        # AND no large negative side-effect.
        better_coverage = (
            sandbox_metrics["coverage_rate"]
            - baseline_metrics["coverage_rate"]
        )
        better_usable = (
            sandbox_metrics["usable_discovery_rate"]
            - baseline_metrics["usable_discovery_rate"]
        )
        if (
            better_coverage
            >= self.promising_coverage_threshold
            or better_usable
            >= self.promising_coverage_threshold
        ):
            return (
                RECOMMENDATION_PROMISING_FOR_PAPER_SHADOW
            )
        return RECOMMENDATION_REVIEW_ONLY


# ---------------------------------------------------------------------------
# Example fixture
# ---------------------------------------------------------------------------
def build_example_scenario(
    *, reference_window: str = "60d"
) -> OfflineRuleSandboxScenario:
    """Build a deterministic example scenario.

    The fixture is intentionally **not** marked
    ``operator_supplied``; consumers must read the ``source``
    field as ``example_fixture`` and may not pretend it is an
    operator-approved scenario.
    """

    rule_changes: tuple[HypotheticalRuleChange, ...] = (
        HypotheticalRuleChange(
            rule_name="early_tail_score_threshold",
            baseline_value=0.5,
            sandbox_value=0.45,
            change_type=_CHANGE_LOOSEN,
            rationale=(
                "Hypothetical: lower the early-tail-score "
                "threshold by 10% to test severe-miss recall."
            ),
            evidence_refs=(
                "report:discovery_quality_scorecard",
                "report:severe_missed_tail_triage",
            ),
        ),
    )
    return OfflineRuleSandboxScenario(
        scenario_id="example_loosen_early_tail_score_threshold",
        name=(
            "example: loosen early_tail_score_threshold by 10% "
            "and observe severe-miss recall direction"
        ),
        reference_window=reference_window,
        baseline_label="phase_11c_baseline_60d",
        hypothetical_rule_changes=rule_changes,
        cohort_filters=(),
        source_reports=(
            "discovery_quality_scorecard",
            "severe_missed_tail_triage",
            "post_discovery_outcome_metrics",
            "reject_to_outcome_attribution",
        ),
        evidence_refs=(
            "report:block_b_integrated_evidence",
            "report:block_c_integrated_checkpoint",
            "report:ai_integrated_checkpoint",
        ),
        source="example_fixture",
    )


__all__ = [
    "FORBIDDEN_SANDBOX_PAYLOAD_KEYS",
    "HypotheticalRuleChange",
    "NEXT_PHASE_NEEDS_MORE_EVIDENCE",
    "NEXT_PHASE_NEEDS_OPERATOR_REVIEW",
    "NEXT_PHASE_PAPER_SHADOW_PREP",
    "OfflineRuleSandboxEngine",
    "OfflineRuleSandboxInput",
    "OfflineRuleSandboxReport",
    "OfflineRuleSandboxResult",
    "OfflineRuleSandboxScenario",
    "RECOMMENDATION_INCONCLUSIVE",
    "RECOMMENDATION_LEVELS",
    "RECOMMENDATION_PROMISING_FOR_PAPER_SHADOW",
    "RECOMMENDATION_REJECTED_BY_EVIDENCE",
    "RECOMMENDATION_REVIEW_ONLY",
    "RECOMMENDATION_RISKY",
    "SANDBOX_EVENT_REPORT_GENERATED",
    "SANDBOX_EVENT_REPLAY_RUN",
    "SANDBOX_EVENT_SCENARIO_EVALUATED",
    "SANDBOX_REPORT_SCHEMA_VERSION",
    "SANDBOX_RESULT_SCHEMA_VERSION",
    "SANDBOX_SCENARIO_SCHEMA_VERSION",
    "SANDBOX_SOURCE_PHASE",
    "STATUS_EVALUATED",
    "STATUS_INCONCLUSIVE",
    "STATUS_INSUFFICIENT_EVIDENCE",
    "STATUS_REJECTED",
    "build_example_scenario",
    "safety_flags_dict",
]
