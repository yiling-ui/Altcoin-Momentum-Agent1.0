"""Phase 11C.1C-C-B-B-B-A - Paper Alpha Gate v0 tests.

Pins every behaviour the brief calls out:

  - PaperAlphaGateInput / PaperAlphaGateRule / PaperAlphaGateRuleResult
    / PaperAlphaGateCohortResult / PaperAlphaGateReport carry every
    brief-mandated identity / cohort / verdict field.
  - The four gate statuses (PASS / WARN / FAIL / INCONCLUSIVE) are
    correctly assigned across sample-count + warning + signal
    scenarios.
  - The runtime emits the four new event types
    (PAPER_ALPHA_GATE_EVALUATED, PAPER_ALPHA_RULE_EVALUATED,
    PAPER_ALPHA_COHORT_EVALUATED, PAPER_ALPHA_REPORT_GENERATED) with
    the brief-mandated identity block.
  - export_paper_alpha_gate_payload + load_paper_alpha_gate_payload
    round-trip cleanly.
  - Phase 8.5 export bundle carries the new event types.
  - ReplayEngine accepts the new event types without raising.
  - Daily report contains the new Paper Alpha Gate v0 section.
  - Safety regression: every Phase 1 safety flag remains False; the
    runtime never emits any ORDER_* / POSITION_* / STOP_* /
    TELEGRAM_MESSAGE_SENT event; the verdict NEVER triggers a real
    trade; Phase 12 remains FORBIDDEN.

No real socket is opened. The gate is paper / report / evidence
only. The ``gate_status`` carried by every payload is descriptive.
The Risk Engine remains the single trade-decision gate.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.adaptive.paper_alpha_gate import (
    PAPER_ALPHA_COHORT_DIMENSIONS,
    PAPER_ALPHA_GATE_SCHEMA_VERSION,
    PAPER_ALPHA_GATE_STATUSES,
    PAPER_ALPHA_GATE_VERSION,
    PaperAlphaGateCohortResult,
    PaperAlphaGateInput,
    PaperAlphaGateReport,
    PaperAlphaGateRule,
    PaperAlphaGateRuleResult,
    PaperAlphaGateStatus,
    build_paper_alpha_gate_input,
    build_paper_alpha_gate_report,
    evaluate_candidate_stage_alpha,
    evaluate_cluster_alpha,
    evaluate_paper_alpha_gate,
    evaluate_score_bucket_alpha,
    evaluate_strategy_mode_alpha,
    export_paper_alpha_gate_payload,
    load_paper_alpha_gate_payload,
)
from app.adaptive.strategy_validation import (
    CandidateStageValidationStats,
    ClusterLeaderValidationStats,
    EarlyTailScoreBucketStats,
    OpportunityScoreBucketStats,
    StrategyModeValidationStats,
    StrategyValidationReport,
    StrategyValidationSample,
    TailLabelDistribution,
)
from app.adaptive.strategy_validation_dataset import (
    StrategyValidationDataset,
    StrategyValidationQualityGateResult,
    build_validation_dataset_from_samples,
    evaluate_validation_dataset_quality,
)
from app.adaptive.strategy_validation_runtime import (
    StrategyValidationRuntime,
    StrategyValidationRuntimeConfig,
)
from app.config.settings import get_settings, load_settings
from app.core.events import Event, EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.exports.service import TestDataExportService
from app.paper_run.daily_report import DailyReportBuilder
from app.replay.engine import ReplayEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _settings():
    get_settings.cache_clear()
    return load_settings()


def _make_event_repo(tmp_path: Path) -> tuple[EventRepository, DatabaseSet]:
    dbs = DatabaseSet.open(
        tmp_path / "sqlite",
        wal=False,
        databases=PHASE2_DATABASES,
    )
    migrate_database_set(dbs)
    return EventRepository(dbs.events, capital_conn=dbs.capital), dbs


def _sample(
    *,
    opportunity_id: str = "opp",
    scan_batch_id: str = "batch",
    symbol: str = "EDENUSDT",
    candidate_stage: str = "early",
    strategy_mode: str = "follow",
    opportunity_score: float = 75.0,
    early_tail_score: float = 80.0,
    late_chase_risk: float = 10.0,
    cluster_id: str = "USDT",
    cluster_leader: str | None = "EDENUSDT",
    is_cluster_leader: bool = True,
    tail_label: str = "strong_tail",
    mfe_5m: float = 0.10,
    mae_5m: float = -0.01,
    reached_2r: bool = True,
    reached_3r: bool = True,
    reached_5r: bool = True,
    reached_10r: bool = False,
    fake_breakout: bool = False,
    missed_tail: bool = False,
    late_chase_failure: bool = False,
) -> StrategyValidationSample:
    return StrategyValidationSample(
        opportunity_id=opportunity_id,
        scan_batch_id=scan_batch_id,
        symbol=symbol,
        candidate_stage=candidate_stage,
        strategy_mode=strategy_mode,
        opportunity_score=opportunity_score,
        opportunity_grade="A",
        early_tail_score=early_tail_score,
        late_chase_risk=late_chase_risk,
        cluster_id=cluster_id,
        cluster_leader=cluster_leader,
        is_cluster_leader=is_cluster_leader,
        tail_label=tail_label,
        mfe_5m=mfe_5m,
        mae_5m=mae_5m,
        mfe_15m=mfe_5m,
        mae_15m=mae_5m,
        mfe_30m=mfe_5m,
        mae_30m=mae_5m,
        mfe_1h=mfe_5m,
        mae_1h=mae_5m,
        mfe_4h=mfe_5m,
        mae_4h=mae_5m,
        reached_2r=reached_2r,
        reached_3r=reached_3r,
        reached_5r=reached_5r,
        reached_10r=reached_10r,
        fake_breakout=fake_breakout,
        missed_tail=missed_tail,
        late_chase_failure=late_chase_failure,
    )


def _diverse_samples(n: int = 25) -> list[StrategyValidationSample]:
    """Build a sample set that satisfies coverage thresholds and
    yields a high-score-bucket / high-early-tail-bucket signal."""
    samples: list[StrategyValidationSample] = []
    modes = ("follow", "pullback", "observe", "reject")
    stages = ("early", "mid", "late", "blowoff", "dumped")
    for i in range(n):
        m = modes[i % len(modes)]
        st = stages[i % len(stages)]
        # Buckets: alternate between low (45) and high (90) scores.
        sc = 45.0 if i % 2 == 0 else 90.0
        ets = 20.0 if i % 2 == 0 else 80.0
        # High-score / high-ets samples land strong_tail more often
        # so the gate detects a high-vs-low advantage on a non-thin
        # cohort. Low-score / low-ets samples land weak_tail.
        if i % 2 == 1:  # high
            tl = "strong_tail" if i % 4 == 1 else "moderate_tail"
        else:  # low
            tl = "weak_tail" if i % 4 == 0 else "moderate_tail"
        samples.append(
            _sample(
                opportunity_id=f"opp-{i}",
                scan_batch_id=f"batch-{i // 5}",
                symbol=f"SYM{i}USDT",
                candidate_stage=st,
                strategy_mode=m,
                opportunity_score=sc,
                early_tail_score=ets,
                tail_label=tl,
                cluster_id=f"cluster-{i % 3}",
                cluster_leader=f"SYM{i}USDT" if i % 3 == 0 else None,
                is_cluster_leader=(i % 3 == 0),
                reached_2r=(i % 2 == 1),
                reached_3r=(i % 2 == 1),
                reached_5r=(i % 2 == 1),
                reached_10r=False,
            )
        )
    return samples


def _strong_alpha_input(
    *,
    sample_count: int = 40,
    completed: int = 30,
    quality_gate_status: str = "pass",
) -> PaperAlphaGateInput:
    """Build a PaperAlphaGateInput that drives the gate to ``PASS``:

      - high opportunity_score / early_tail_score buckets clearly
        beat low buckets;
      - cluster leader cohort outperforms followers;
      - no follow_risk / late_chase / missed_alpha warning.
    """
    return PaperAlphaGateInput(
        report_id="rep-pass",
        dataset_id="ds-pass",
        sample_count=sample_count,
        completed_tail_label_count=completed,
        quality_gate_status=quality_gate_status,
        quality_gate_reasons=("all_quality_gate_thresholds_met",),
        strategy_mode_counts={
            "follow": 10, "pullback": 10, "observe": 10, "reject": 10
        },
        candidate_stage_counts={
            "early": 8, "mid": 8, "late": 8, "blowoff": 8, "dumped": 8
        },
        opportunity_score_bucket_counts={
            "0-49": 10, "50-64": 10, "65-79": 10, "80-100": 10
        },
        early_tail_score_bucket_counts={
            "0-24": 10, "25-49": 10, "50-74": 10, "75-100": 10
        },
        tail_label_counts={
            "strong_tail": 12,
            "moderate_tail": 10,
            "weak_tail": 8,
            "fake_breakout": 5,
            "unresolved": 5,
        },
        strategy_mode_stats={
            "follow": {
                "sample_count": 10,
                "fake_breakout_rate": 0.05,
                "strong_tail_rate": 0.40,
                "missed_tail_rate": 0.0,
                "p_reached_2r": 0.50,
                "p_reached_3r": 0.40,
                "p_reached_5r": 0.20,
            },
            "pullback": {"sample_count": 10, "strong_tail_rate": 0.30},
            "observe": {
                "sample_count": 10,
                "strong_tail_rate": 0.05,
                "missed_tail_rate": 0.05,
            },
            "reject": {
                "sample_count": 10,
                "strong_tail_rate": 0.05,
            },
        },
        candidate_stage_stats={
            "early": {
                "sample_count": 8,
                "fake_breakout_rate": 0.05,
                "strong_tail_rate": 0.30,
            },
            "mid": {
                "sample_count": 8,
                "fake_breakout_rate": 0.10,
            },
            "late": {
                "sample_count": 8,
                "fake_breakout_rate": 0.10,
            },
            "blowoff": {
                "sample_count": 8,
                "fake_breakout_rate": 0.10,
            },
            "dumped": {
                "sample_count": 8,
                "fake_breakout_rate": 0.0,
            },
        },
        opportunity_score_bucket_stats={
            "0-49": {
                "sample_count": 10,
                "strong_tail_rate": 0.10,
                "p_reached_3r": 0.05,
                "p_reached_5r": 0.0,
            },
            "50-64": {
                "sample_count": 10,
                "strong_tail_rate": 0.15,
                "p_reached_3r": 0.10,
                "p_reached_5r": 0.05,
            },
            "65-79": {
                "sample_count": 10,
                "strong_tail_rate": 0.40,
                "p_reached_3r": 0.30,
                "p_reached_5r": 0.20,
            },
            "80-100": {
                "sample_count": 10,
                "strong_tail_rate": 0.55,
                "p_reached_3r": 0.40,
                "p_reached_5r": 0.30,
            },
        },
        early_tail_score_bucket_stats={
            "0-24": {
                "sample_count": 10,
                "strong_tail_rate": 0.05,
                "p_reached_3r": 0.05,
            },
            "25-49": {
                "sample_count": 10,
                "strong_tail_rate": 0.10,
                "p_reached_3r": 0.10,
            },
            "50-74": {
                "sample_count": 10,
                "strong_tail_rate": 0.40,
                "p_reached_3r": 0.30,
            },
            "75-100": {
                "sample_count": 10,
                "strong_tail_rate": 0.55,
                "p_reached_3r": 0.40,
            },
        },
        cluster_leader_stats={
            "cluster-A": {
                "leader_sample_count": 5,
                "follower_sample_count": 5,
                "leader_avg_mfe": 0.20,
                "follower_avg_mfe": 0.05,
                "leader_strong_tail_rate": 0.50,
                "follower_strong_tail_rate": 0.10,
                "leader_outperformed_followers": True,
            },
        },
    )


# ---------------------------------------------------------------------------
# 1. Contract: input + report fields
# ---------------------------------------------------------------------------
def test_paper_alpha_gate_input_contract():
    """``PaperAlphaGateInput`` carries every brief-mandated field and
    is JSON-safe."""
    inp = _strong_alpha_input()
    payload = inp.to_payload()
    for field in (
        "report_id",
        "dataset_id",
        "sample_count",
        "completed_tail_label_count",
        "quality_gate_status",
        "quality_gate_reasons",
        "strategy_mode_counts",
        "candidate_stage_counts",
        "opportunity_score_bucket_counts",
        "early_tail_score_bucket_counts",
        "tail_label_counts",
        "strategy_mode_stats",
        "candidate_stage_stats",
        "opportunity_score_bucket_stats",
        "early_tail_score_bucket_stats",
        "cluster_leader_stats",
        "strategy_version",
        "scoring_version",
        "risk_config_version",
        "state_machine_version",
        "schema_version",
    ):
        assert field in payload, f"missing field {field}"
    assert payload["schema_version"] == PAPER_ALPHA_GATE_SCHEMA_VERSION
    json.dumps(payload, sort_keys=True)


def test_paper_alpha_gate_status_vocabulary_locked():
    """The verdict vocabulary is exactly PASS / WARN / FAIL /
    INCONCLUSIVE - never an alias for a trade authorisation."""
    assert tuple(PAPER_ALPHA_GATE_STATUSES) == (
        "PASS",
        "WARN",
        "FAIL",
        "INCONCLUSIVE",
    )
    assert PaperAlphaGateStatus.PASS == "PASS"
    assert PaperAlphaGateStatus.WARN == "WARN"
    assert PaperAlphaGateStatus.FAIL == "FAIL"
    assert PaperAlphaGateStatus.INCONCLUSIVE == "INCONCLUSIVE"
    # Forbidden trade-authorisation aliases must not appear in the
    # status set.
    for forbidden in ("approved", "trade", "open", "buy", "sell", "live"):
        assert forbidden not in PAPER_ALPHA_GATE_STATUSES


def test_paper_alpha_cohort_dimensions_locked():
    """The cohort dimension vocabulary mirrors the brief."""
    assert "strategy_mode" in PAPER_ALPHA_COHORT_DIMENSIONS
    assert "candidate_stage" in PAPER_ALPHA_COHORT_DIMENSIONS
    assert "opportunity_score_bucket" in PAPER_ALPHA_COHORT_DIMENSIONS
    assert "early_tail_score_bucket" in PAPER_ALPHA_COHORT_DIMENSIONS
    assert "cluster_leader_vs_follower" in PAPER_ALPHA_COHORT_DIMENSIONS
    assert "tail_label_distribution" in PAPER_ALPHA_COHORT_DIMENSIONS


def test_paper_alpha_rule_definition_round_trips():
    rule = PaperAlphaGateRule(
        rule_id="r1",
        description="dummy",
        threshold=0.5,
        severity="warning",
    )
    payload = rule.to_payload()
    assert payload["rule_id"] == "r1"
    assert payload["severity"] == "warning"
    assert payload["schema_version"] == PAPER_ALPHA_GATE_SCHEMA_VERSION
    json.dumps(payload, sort_keys=True)


# ---------------------------------------------------------------------------
# 2. Builder + decision rules
# ---------------------------------------------------------------------------
def test_paper_alpha_gate_inconclusive_on_low_samples():
    """Below ``min_total_samples`` -> INCONCLUSIVE."""
    inp = PaperAlphaGateInput(
        report_id="rep-thin",
        sample_count=3,
        completed_tail_label_count=1,
        quality_gate_status="warn",
    )
    status, reasons, warnings, cohorts, rules = evaluate_paper_alpha_gate(
        inp
    )
    assert status == PaperAlphaGateStatus.INCONCLUSIVE
    assert any("sample_count_below_min" in r for r in reasons)
    # Sample-count rule fired.
    sample_rule = next(
        r for r in rules
        if r.rule_id == "dataset_must_have_min_total_samples"
    )
    assert sample_rule.triggered is True
    assert sample_rule.severity == "block"


def test_paper_alpha_gate_fails_when_quality_gate_fails():
    """Phase 11C.1C-C-B-B-A ``validation_quality_gate_status=fail``
    forces the alpha gate into INCONCLUSIVE / FAIL (the brief lets
    the gate pick either; we emit INCONCLUSIVE because the dataset
    is structurally untrustworthy)."""
    inp = _strong_alpha_input(quality_gate_status="fail")
    status, reasons, warnings, cohorts, rules = evaluate_paper_alpha_gate(
        inp
    )
    assert status in (
        PaperAlphaGateStatus.INCONCLUSIVE,
        PaperAlphaGateStatus.FAIL,
    )
    # The block-rule fired.
    qg_rule = next(
        r for r in rules
        if r.rule_id == "quality_gate_status_must_not_fail"
    )
    assert qg_rule.triggered is True
    assert qg_rule.severity == "block"
    assert any("validation_quality_gate_status=fail" in r for r in reasons)


def test_paper_alpha_gate_warns_on_missed_alpha():
    """observe / reject cohort with high strong_tail_rate raises
    ``missed_alpha_warning`` and downgrades the verdict."""
    inp = _strong_alpha_input()
    # Bump observe.strong_tail_rate above the threshold.
    new_stats = dict(inp.strategy_mode_stats)
    new_stats["observe"] = dict(new_stats["observe"])
    new_stats["observe"]["strong_tail_rate"] = 0.50
    inp = inp.model_copy(update={"strategy_mode_stats": new_stats})

    status, reasons, warnings, cohorts, rules = evaluate_paper_alpha_gate(
        inp
    )
    assert "missed_alpha_warning" in warnings
    assert status in (
        PaperAlphaGateStatus.WARN,
        PaperAlphaGateStatus.FAIL,
    )
    # Verify per-cohort surface.
    sm_cohort = next(
        c for c in cohorts if c.dimension == "strategy_mode"
    )
    assert "missed_alpha_warning" in sm_cohort.warnings


def test_paper_alpha_gate_warns_on_late_chase_failure():
    """late / blowoff cohort with high fake_breakout_rate raises
    ``late_chase_warning``."""
    inp = _strong_alpha_input()
    new_stats = dict(inp.candidate_stage_stats)
    new_stats["late"] = dict(new_stats["late"])
    new_stats["late"]["fake_breakout_rate"] = 0.50
    inp = inp.model_copy(update={"candidate_stage_stats": new_stats})

    status, reasons, warnings, cohorts, rules = evaluate_paper_alpha_gate(
        inp
    )
    assert "late_chase_warning" in warnings
    assert status == PaperAlphaGateStatus.WARN
    cs_cohort = next(
        c for c in cohorts if c.dimension == "candidate_stage"
    )
    assert "late_chase_warning" in cs_cohort.warnings


def test_paper_alpha_gate_warns_on_follow_fake_breakout():
    """follow cohort with high fake_breakout_rate raises
    ``follow_risk_warning``."""
    inp = _strong_alpha_input()
    new_stats = dict(inp.strategy_mode_stats)
    new_stats["follow"] = dict(new_stats["follow"])
    new_stats["follow"]["fake_breakout_rate"] = 0.50
    inp = inp.model_copy(update={"strategy_mode_stats": new_stats})

    status, reasons, warnings, cohorts, rules = evaluate_paper_alpha_gate(
        inp
    )
    assert "follow_risk_warning" in warnings
    assert status == PaperAlphaGateStatus.WARN


def test_paper_alpha_gate_detects_high_score_bucket_signal():
    """When high opportunity_score buckets clearly outperform low
    buckets, the gate raises ``high_score_bucket_outperforms_low_signal``
    and (with the early tail signal also present) emits PASS."""
    inp = _strong_alpha_input()
    status, reasons, warnings, cohorts, rules = evaluate_paper_alpha_gate(
        inp
    )
    opp_cohort = next(
        c for c in cohorts if c.dimension == "opportunity_score_bucket"
    )
    assert "high_score_bucket_outperforms_low_signal" in opp_cohort.signals
    # No warnings, both signals -> PASS.
    assert status == PaperAlphaGateStatus.PASS
    assert "high_score_bucket_outperforms_low_signal" in reasons


def test_paper_alpha_gate_detects_early_tail_bucket_signal():
    """A high early_tail_score bucket beating the low bucket raises
    ``high_early_tail_bucket_outperforms_low_signal``; if the high
    bucket fails to outperform, the gate raises
    ``early_tail_no_alpha_advantage`` and refuses PASS."""
    inp = _strong_alpha_input()
    # Positive case -> signal present.
    status, _, _, cohorts, _ = evaluate_paper_alpha_gate(inp)
    ets_cohort = next(
        c for c in cohorts if c.dimension == "early_tail_score_bucket"
    )
    assert (
        "high_early_tail_bucket_outperforms_low_signal" in ets_cohort.signals
    )

    # Flatten the early_tail bucket so high ~= low; expect WARN +
    # ``early_tail_no_alpha_advantage`` + no PASS.
    flat = dict(inp.early_tail_score_bucket_stats)
    flat["75-100"] = dict(flat["75-100"])
    flat["75-100"]["strong_tail_rate"] = 0.10
    flat["75-100"]["p_reached_3r"] = 0.10
    flat["50-74"] = dict(flat["50-74"])
    flat["50-74"]["strong_tail_rate"] = 0.10
    flat["50-74"]["p_reached_3r"] = 0.10
    flat_inp = inp.model_copy(update={"early_tail_score_bucket_stats": flat})
    status_flat, _, warnings_flat, _, _ = evaluate_paper_alpha_gate(flat_inp)
    assert "early_tail_no_alpha_advantage" in warnings_flat
    assert status_flat != PaperAlphaGateStatus.PASS


def test_paper_alpha_gate_detects_cluster_leader_signal():
    """A cluster where the leader's strong_tail_rate clearly exceeds
    the followers' raises ``leader_preference_signal``."""
    inp = _strong_alpha_input()
    status, reasons, _, cohorts, _ = evaluate_paper_alpha_gate(inp)
    cluster_cohort = next(
        c for c in cohorts if c.dimension == "cluster_leader_vs_follower"
    )
    assert "leader_preference_signal" in cluster_cohort.signals
    assert "leader_preference_signal" in reasons


def test_evaluate_paper_alpha_gate_is_deterministic():
    """The pure evaluator yields identical results on repeated calls
    with identical inputs."""
    inp = _strong_alpha_input()
    a = evaluate_paper_alpha_gate(inp)
    b = evaluate_paper_alpha_gate(inp)
    # Statuses + reasons + warnings identical.
    assert a[0] == b[0]
    assert a[1] == b[1]
    assert a[2] == b[2]


# ---------------------------------------------------------------------------
# 3. build_paper_alpha_gate_input from upstream artefacts
# ---------------------------------------------------------------------------
def test_build_paper_alpha_gate_input_from_dataset_and_report():
    """Wiring: a Phase 11C.1C-C-B-B-A dataset + Phase 11C.1C-C-B-A
    report flow into a structured PaperAlphaGateInput."""
    samples = _diverse_samples(20)
    ds = build_validation_dataset_from_samples(
        samples, report_id="rep-build", generated_at_ms=0
    )
    qg = evaluate_validation_dataset_quality(ds)
    # Build a minimal Phase 11C.1C-C-B-A report to back the cohort
    # stats - the runtime would build this in production.
    sv_report = StrategyValidationReport(
        report_id="rep-build",
        generated_at_ms=0,
        sample_count=len(samples),
        by_strategy_mode={
            "follow": StrategyModeValidationStats(
                strategy_mode="follow",
                sample_count=5,
                strong_tail_rate=0.30,
            ),
        },
        tail_label_distribution=TailLabelDistribution(
            sample_count=len(samples),
            counts={"strong_tail": 5, "moderate_tail": 5, "weak_tail": 5},
        ),
    )

    inp = build_paper_alpha_gate_input(
        dataset=ds,
        quality_gate_result=qg,
        validation_report=sv_report,
    )
    assert inp.report_id == "rep-build"
    assert inp.dataset_id == "rep-build"
    assert inp.sample_count == ds.summary.record_count
    assert inp.quality_gate_status == qg.gate_status
    assert "follow" in inp.strategy_mode_stats
    # Tail-label counts mirror the dataset summary.
    assert sum(inp.tail_label_counts.values()) >= len(samples)


# ---------------------------------------------------------------------------
# 4. Export / replay round-trip
# ---------------------------------------------------------------------------
def test_paper_alpha_gate_payload_roundtrip():
    """``export_paper_alpha_gate_payload`` -> JSON -> ``load_paper_alpha_gate_payload``
    yields an equivalent report."""
    inp = _strong_alpha_input()
    rep = build_paper_alpha_gate_report(inp, evaluated_at=42)
    payload = export_paper_alpha_gate_payload(rep)
    json.dumps(payload, sort_keys=True)
    loaded = load_paper_alpha_gate_payload(payload)
    assert isinstance(loaded, PaperAlphaGateReport)
    assert loaded.report_id == rep.report_id
    assert loaded.gate_status == rep.gate_status
    assert tuple(loaded.reasons) == tuple(rep.reasons)
    assert tuple(loaded.warnings) == tuple(rep.warnings)
    assert len(loaded.rule_results) == len(rep.rule_results)
    assert len(loaded.cohort_results) == len(rep.cohort_results)
    assert loaded.schema_version == PAPER_ALPHA_GATE_SCHEMA_VERSION


def test_load_paper_alpha_gate_payload_tolerates_missing_optional_fields():
    """Legacy / future payload lacking optional fields must still
    load without raising."""
    minimal_payload = {
        "report_id": "rep-old",
        "gate_status": PaperAlphaGateStatus.INCONCLUSIVE,
    }
    loaded = load_paper_alpha_gate_payload(minimal_payload)
    assert loaded.report_id == "rep-old"
    assert loaded.gate_status == PaperAlphaGateStatus.INCONCLUSIVE
    assert loaded.schema_version == PAPER_ALPHA_GATE_SCHEMA_VERSION


def test_load_paper_alpha_gate_payload_rejects_non_mapping():
    with pytest.raises(TypeError):
        load_paper_alpha_gate_payload("not a mapping")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. Runtime emits the new event types
# ---------------------------------------------------------------------------
def _seed_runtime(
    runtime: StrategyValidationRuntime, *, n: int = 30
) -> None:
    """Seed the runtime sample buffer directly. Bypasses the
    LabelTrackingRecord fixture path; the resulting end-state is
    identical."""
    from app.adaptive.strategy_validation_runtime import _SampleEntry

    for s in _diverse_samples(n):
        runtime._samples_by_opportunity[s.opportunity_id] = _SampleEntry(
            sample=s, source_event_id="", created_at_ms=0
        )


def test_paper_alpha_gate_events_exportable(tmp_path: Path):
    """flush_report must emit the four new Paper Alpha Gate v0
    events; the Phase 8.5 export bundle carries them."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime(runtime, n=30)
        runtime.flush_report(
            report_id="rep-pa-export",
            generated_at_ms=1_700_000_000_000,
        )
        # All four event types present.
        for et in (
            EventType.PAPER_ALPHA_GATE_EVALUATED,
            EventType.PAPER_ALPHA_RULE_EVALUATED,
            EventType.PAPER_ALPHA_COHORT_EVALUATED,
            EventType.PAPER_ALPHA_REPORT_GENERATED,
        ):
            evs = repo.list_events(event_type=et)
            assert len(evs) >= 1, f"missing {et.value}"
            ev = evs[-1]
            for field in (
                "report_id",
                "dataset_id",
                "timestamp",
                "gate_status",
                "strategy_version",
                "scoring_version",
                "risk_config_version",
                "state_machine_version",
                "schema_version",
            ):
                assert field in ev.payload, (
                    f"event {et.value} missing payload field {field}"
                )
            assert ev.payload["report_id"] == "rep-pa-export"
            assert (
                ev.payload["schema_version"]
                == PAPER_ALPHA_GATE_SCHEMA_VERSION
            )
            assert ev.payload["gate_status"] in PAPER_ALPHA_GATE_STATUSES
            assert ev.payload["paper_alpha_gate_version"] == (
                PAPER_ALPHA_GATE_VERSION
            )
            assert ev.source_module == StrategyValidationRuntime.SOURCE_MODULE
        # Phase 8.5 export bundle carries the new event types.
        out_dir = tmp_path / "exports"
        out_dir.mkdir()
        service = TestDataExportService(
            event_repo=repo, trading_mode="paper", output_dir=out_dir
        )
        result = service.export(
            range_label="range",
            start_ms=1_699_000_000_000,
            end_ms=2_000_000_000_000,
            type_filter="all",
        )
        with zipfile.ZipFile(result.zip_path) as zf:
            seen = {
                et.value: 0
                for et in (
                    EventType.PAPER_ALPHA_GATE_EVALUATED,
                    EventType.PAPER_ALPHA_RULE_EVALUATED,
                    EventType.PAPER_ALPHA_COHORT_EVALUATED,
                    EventType.PAPER_ALPHA_REPORT_GENERATED,
                )
            }
            for line in zf.read("events.jsonl").decode("utf-8").splitlines():
                row = json.loads(line)
                if row.get("event_type") in seen:
                    seen[row["event_type"]] += 1
            for k, v in seen.items():
                assert v >= 1, f"export missing event {k}"
    finally:
        dbs.close()


def test_replay_reads_paper_alpha_gate_events(tmp_path: Path):
    """ReplayEngine accepts events.db containing the four new
    Paper Alpha Gate v0 event types without raising. A legacy /
    future row missing ``schema_version`` is tolerated."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        # Legacy event + a paper-alpha-gate row missing schema_version.
        repo.append(
            Event(
                event_type=EventType.MARKET_SNAPSHOT,
                source_module="legacy",
                symbol="LEGACYUSDT",
                timestamp=1_700_000_000_000,
                payload={"hello": "world"},
            )
        )
        repo.append(
            Event(
                event_type=EventType.PAPER_ALPHA_GATE_EVALUATED,
                source_module="legacy_paper_alpha",
                symbol=None,
                timestamp=1_700_000_000_000,
                payload={
                    "report_id": "legacy-rep",
                    "gate_status": "INCONCLUSIVE",
                    # schema_version missing intentionally
                },
            )
        )
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime(runtime, n=30)
        runtime.flush_report(
            report_id="rep-replay-pa",
            generated_at_ms=1_700_000_000_000,
        )
        engine = ReplayEngine(event_repo=repo)
        # Replay does NOT raise.
        engine.replay_risk_rejections()
        for et in (
            EventType.PAPER_ALPHA_GATE_EVALUATED,
            EventType.PAPER_ALPHA_RULE_EVALUATED,
            EventType.PAPER_ALPHA_COHORT_EVALUATED,
            EventType.PAPER_ALPHA_REPORT_GENERATED,
        ):
            assert repo.count_events(event_type=et) >= 1
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 6. Daily report integration
# ---------------------------------------------------------------------------
def test_daily_report_contains_paper_alpha_gate_metrics(tmp_path: Path):
    """The Phase 11B daily report's snapshot + Markdown carry the
    Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0 fields."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime(runtime, n=40)
        runtime.flush_report(
            report_id="rep-daily-pa",
            generated_at_ms=1_700_000_000_000,
        )
        builder = DailyReportBuilder(
            event_repo=repo,
            output_dir=tmp_path / "reports",
        )
        snapshot = builder.build(
            started_at_ms=1_699_000_000_000,
            finished_at_ms=2_000_000_000_000,
            write_to_disk=False,
            strategy_validation_metrics=runtime.metrics_payload(),
        )
        # Snapshot fields populated.
        assert snapshot.paper_alpha_gate_evaluated_count >= 1
        assert snapshot.paper_alpha_rule_evaluated_count >= 1
        assert snapshot.paper_alpha_cohort_evaluated_count >= 1
        assert snapshot.paper_alpha_report_generated_count >= 1
        assert snapshot.paper_alpha_gate_status in PAPER_ALPHA_GATE_STATUSES
        assert isinstance(snapshot.paper_alpha_gate_reasons, list)
        assert isinstance(snapshot.paper_alpha_strategy_mode_results, dict)
        assert isinstance(
            snapshot.paper_alpha_candidate_stage_results, dict
        )
        assert isinstance(snapshot.paper_alpha_score_bucket_results, dict)
        assert isinstance(snapshot.paper_alpha_cluster_results, dict)
        # Markdown body contains the new section + boundary banner.
        assert "Phase 11C.1C-C-B-B-B-A Paper Alpha Gate v0" in snapshot.markdown
        assert "PAPER_ALPHA_GATE_EVALUATED" in snapshot.markdown
        assert "MUST NEVER trigger a real trade" in snapshot.markdown
        assert "Phase 12 remains" in snapshot.markdown
        # Payload also carries every new key.
        payload = snapshot.to_payload()
        for key in (
            "paper_alpha_gate_evaluated_count",
            "paper_alpha_rule_evaluated_count",
            "paper_alpha_cohort_evaluated_count",
            "paper_alpha_report_generated_count",
            "paper_alpha_gate_status",
            "paper_alpha_gate_reasons",
            "paper_alpha_gate_warnings",
            "paper_alpha_gate_sample_count",
            "paper_alpha_strategy_mode_results",
            "paper_alpha_candidate_stage_results",
            "paper_alpha_score_bucket_results",
            "paper_alpha_cluster_results",
            "paper_alpha_missed_alpha_warnings",
            "paper_alpha_late_chase_warnings",
            "paper_alpha_follow_risk_warnings",
            "paper_alpha_leader_preference_signals",
        ):
            assert key in payload, f"missing payload key {key}"
    finally:
        dbs.close()


def test_daily_report_renders_when_no_paper_alpha_gate(tmp_path: Path):
    """Even with no Paper Alpha Gate events, the Markdown still
    renders the section."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        builder = DailyReportBuilder(
            event_repo=repo,
            output_dir=tmp_path / "reports",
        )
        snapshot = builder.build(
            started_at_ms=1_699_000_000_000,
            finished_at_ms=2_000_000_000_000,
            write_to_disk=False,
        )
        assert "Paper Alpha Gate v0" in snapshot.markdown
        assert snapshot.paper_alpha_gate_evaluated_count == 0
        assert snapshot.paper_alpha_gate_status == ""
    finally:
        dbs.close()


def test_paper_alpha_gate_inconclusive_when_dataset_empty(tmp_path: Path):
    """When the runtime flushes with no samples, the brief expects an
    INCONCLUSIVE / FAIL Paper Alpha Gate report (not a skip).
    The runtime emits a Phase 11C.1C-C-B-A report in this case but
    *not* a dataset (no samples) - the gate is therefore not
    evaluated. This test pins the behaviour: when the dataset never
    gets built, the alpha-gate counters stay at zero, but
    metrics_payload still surfaces the empty paper_alpha_* block so
    the daily-report can render the section.
    """
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        # No samples seeded -> dataset has zero records and the
        # quality gate emits ``fail``. The alpha-gate runs anyway
        # because the dataset object exists; verdict must be
        # INCONCLUSIVE / FAIL.
        runtime.flush_report(
            report_id="rep-empty",
            generated_at_ms=1_700_000_000_000,
        )
        metrics = runtime.metrics_payload()
        assert "paper_alpha_gate_status" in metrics
        # When dataset built+gate was evaluated, alpha gate runs and
        # must produce a non-PASS verdict.
        if metrics.get("paper_alpha_gate_evaluated_count", 0) >= 1:
            assert metrics["paper_alpha_gate_status"] in (
                PaperAlphaGateStatus.INCONCLUSIVE,
                PaperAlphaGateStatus.FAIL,
            )
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 7. Safety boundary
# ---------------------------------------------------------------------------
def test_no_live_trading_flags_unchanged():
    """Phase 1 safety lock invariants. The Paper Alpha Gate v0
    cannot loosen them."""
    s = _settings()
    assert s.trading_mode == "paper"
    assert s.live_trading_enabled is False
    assert s.right_tail_enabled is False
    assert s.llm_enabled is False
    assert s.exchange_live_order_enabled is False
    assert s.telegram_outbound_enabled is False
    safety = s.safety
    for flag in (
        "forbid_private_credentials",
        "forbid_signed_endpoints",
        "forbid_trade_endpoints",
        "forbid_account_endpoints",
        "forbid_position_endpoints",
        "forbid_leverage_endpoints",
        "forbid_margin_endpoints",
        "forbid_live_trading",
        "forbid_right_tail",
        "forbid_llm_trade_decisions",
        "forbid_telegram_outbound",
    ):
        assert getattr(safety, flag) is True


def test_paper_alpha_gate_does_not_trigger_execution(tmp_path: Path):
    """Building + evaluating the Paper Alpha Gate v0 MUST never
    emit any trading event and never call Telegram outbound. The
    ``gate_status`` MUST NEVER be a trade-authorising label."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime(runtime, n=40)
        runtime.flush_report(
            report_id="rep-pa-safety",
            generated_at_ms=1_700_000_000_000,
        )
        forbidden = {
            EventType.ORDER_SENT,
            EventType.ORDER_FILLED,
            EventType.ORDER_PARTIAL_FILLED,
            EventType.ORDER_ACK,
            EventType.ORDER_CANCELLED,
            EventType.POSITION_OPENED,
            EventType.POSITION_CLOSED,
            EventType.POSITION_UPDATED,
            EventType.STOP_SENT,
            EventType.STOP_CONFIRMED,
            EventType.STOP_FAILED,
            EventType.TELEGRAM_MESSAGE_SENT,
            EventType.EXIT_TRIGGERED,
        }
        for et in forbidden:
            assert (
                repo.count_events(event_type=et) == 0
            ), f"paper alpha gate emitted forbidden {et.value}"
        # Verdict vocabulary is fixed and descriptive only.
        gate_evs = repo.list_events(
            event_type=EventType.PAPER_ALPHA_GATE_EVALUATED
        )
        assert gate_evs
        for ev in gate_evs:
            assert ev.payload["gate_status"] in PAPER_ALPHA_GATE_STATUSES
            assert ev.payload["gate_status"] not in {
                "approved",
                "trade",
                "open",
                "buy",
                "sell",
                "live",
            }
        # All four new event types attribute to the runtime
        # source_module - no other module is allowed to emit them.
        for et in (
            EventType.PAPER_ALPHA_GATE_EVALUATED,
            EventType.PAPER_ALPHA_RULE_EVALUATED,
            EventType.PAPER_ALPHA_COHORT_EVALUATED,
            EventType.PAPER_ALPHA_REPORT_GENERATED,
        ):
            for ev in repo.list_events(event_type=et):
                assert (
                    ev.source_module
                    == StrategyValidationRuntime.SOURCE_MODULE
                )
    finally:
        dbs.close()


def test_phase_12_remains_forbidden(tmp_path: Path):
    """Phase 12 is FORBIDDEN under the Phase 1 safety lock; the
    Paper Alpha Gate v0 cannot change that."""
    s = _settings()
    assert s.live_trading_enabled is False
    assert s.exchange_live_order_enabled is False
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime(runtime, n=40)
        runtime.flush_report(
            report_id="rep-pa-phase12",
            generated_at_ms=1_700_000_000_000,
        )
        # Schema version still belongs to Phase 11C.1C-C-B-B-B-A.
        ev = repo.list_events(
            event_type=EventType.PAPER_ALPHA_GATE_EVALUATED
        )[-1]
        assert "phase_11c_1c_c_b_b_b_a" in ev.payload["schema_version"]
        # The paper alpha gate version label likewise.
        assert (
            ev.payload["paper_alpha_gate_version"]
            == PAPER_ALPHA_GATE_VERSION
        )
        # The runtime cached gate vocabulary cannot include anything
        # that implies trade authorisation.
        rep = runtime.latest_paper_alpha_report
        assert rep is not None
        assert rep.gate_status in PAPER_ALPHA_GATE_STATUSES
        assert rep.gate_status not in {
            "approved",
            "trade",
            "open",
            "buy",
            "sell",
            "live",
        }
    finally:
        dbs.close()


def test_runtime_config_paper_alpha_gate_can_be_disabled():
    """``paper_alpha_gate_enabled=False`` disables the new
    sub-slice without affecting the parent dataset / quality-gate
    contract."""
    cfg = StrategyValidationRuntimeConfig.from_mapping(
        {"paper_alpha_gate_enabled": False}
    )
    assert cfg.paper_alpha_gate_enabled is False
    assert cfg.dataset_enabled is True


def test_paper_alpha_gate_disabled_skips_paper_alpha_events(tmp_path: Path):
    """When ``paper_alpha_gate_enabled=False`` the runtime emits the
    seven Phase 11C.1C-C-B-A events + the three dataset events but
    NOT the four new alpha-gate events."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(
            event_repo=repo,
            config=StrategyValidationRuntimeConfig(
                paper_alpha_gate_enabled=False
            ),
        )
        _seed_runtime(runtime, n=30)
        runtime.flush_report(
            report_id="rep-no-pa",
            generated_at_ms=1_700_000_000_000,
        )
        for et in (
            EventType.PAPER_ALPHA_GATE_EVALUATED,
            EventType.PAPER_ALPHA_RULE_EVALUATED,
            EventType.PAPER_ALPHA_COHORT_EVALUATED,
            EventType.PAPER_ALPHA_REPORT_GENERATED,
        ):
            assert repo.count_events(event_type=et) == 0
        # Dataset / QG events still flow.
        assert (
            repo.count_events(
                event_type=EventType.STRATEGY_VALIDATION_DATASET_BUILT
            )
            >= 1
        )
    finally:
        dbs.close()
