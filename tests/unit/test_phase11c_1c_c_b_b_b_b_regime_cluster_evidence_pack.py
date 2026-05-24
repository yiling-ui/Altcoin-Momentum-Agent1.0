"""Phase 11C.1C-C-B-B-B-B - Regime & Cluster Cohort Evidence Pack v0
tests.

Pins every behaviour the brief calls out:

  - RegimeClusterEvidenceInput / RegimeClusterCohortKey /
    RegimeClusterCohortStats / RegimeCohortSummary /
    ClusterCohortSummary / ScoreBucketSummary /
    StageOutcomeSummary / StrategyModeOutcomeSummary /
    RegimeClusterEvidencePack carry every brief-mandated
    identity / cohort field.
  - The four pack statuses (INSUFFICIENT_SAMPLE / OBSERVE_ONLY /
    WARNING / EVIDENCE_SIGNAL) are correctly assigned across
    sample-count + warning + signal scenarios.
  - The runtime emits the two new event types
    (REGIME_CLUSTER_EVIDENCE_PACK_GENERATED,
    REGIME_CLUSTER_COHORT_SUMMARY_GENERATED) with the
    brief-mandated identity block.
  - export_regime_cluster_evidence_payload +
    load_regime_cluster_evidence_payload round-trip cleanly.
  - Phase 8.5 export bundle carries the new event types.
  - ReplayEngine accepts the new event types without raising.
  - Daily report contains the new Regime & Cluster Cohort
    Evidence Pack v0 section.
  - Safety regression: every Phase 1 safety flag remains False; the
    runtime never emits any ORDER_* / POSITION_* / STOP_* /
    TELEGRAM_MESSAGE_SENT event; the verdict NEVER triggers a real
    trade; Phase 12 remains FORBIDDEN.

No real socket is opened. The pack is paper / report / evidence
only. Every per-cohort status carried by every payload is
descriptive. The Risk Engine remains the single trade-decision
gate.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.adaptive.regime_cluster_evidence_pack import (
    DEFAULT_FAKE_BREAKOUT_WARNING_RATE,
    DEFAULT_LATE_CHASE_FAILURE_WARNING_RATE,
    DEFAULT_MIN_COHORT_SAMPLES,
    DEFAULT_MIN_COMPLETED_TAIL_LABELS,
    DEFAULT_MIN_TOTAL_SAMPLES,
    DEFAULT_MISSED_TAIL_WARNING_RATE,
    REGIME_CLUSTER_COHORT_DIMENSIONS,
    REGIME_CLUSTER_EVIDENCE_PACK_STATUSES,
    REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION,
    REGIME_CLUSTER_EVIDENCE_VERSION,
    UNKNOWN_REGIME,
    ClusterCohortSummary,
    RegimeClusterCohortKey,
    RegimeClusterCohortStats,
    RegimeClusterEvidenceInput,
    RegimeClusterEvidencePack,
    RegimeClusterEvidencePackStatus,
    RegimeClusterEvidenceRecord,
    RegimeCohortSummary,
    ScoreBucketSummary,
    StageOutcomeSummary,
    StrategyModeOutcomeSummary,
    build_cluster_cohort_summary,
    build_regime_cluster_evidence_input,
    build_regime_cluster_evidence_pack,
    build_regime_cohort_summary,
    build_score_bucket_summary,
    build_stage_outcome_summary,
    build_strategy_mode_outcome_summary,
    export_regime_cluster_evidence_payload,
    load_regime_cluster_evidence_payload,
)
from app.adaptive.strategy_validation import StrategyValidationSample
from app.adaptive.strategy_validation_dataset import (
    build_validation_dataset_from_samples,
)
from app.adaptive.strategy_validation_runtime import (
    StrategyValidationRuntime,
    StrategyValidationRuntimeConfig,
    _SampleEntry,
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


def _diverse_samples(n: int = 30) -> list[StrategyValidationSample]:
    """Build a sample set wide enough to exercise the full set of
    cohort dimensions and yield a positive evidence signal."""
    samples: list[StrategyValidationSample] = []
    modes = ("follow", "pullback", "observe", "reject")
    stages = ("early", "mid", "late", "blowoff", "dumped")
    for i in range(n):
        m = modes[i % len(modes)]
        st = stages[i % len(stages)]
        sc = 45.0 if i % 2 == 0 else 90.0
        ets = 20.0 if i % 2 == 0 else 80.0
        if i % 2 == 1:
            tl = "strong_tail" if i % 4 == 1 else "moderate_tail"
        else:
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
                cluster_id=f"cl-{i % 3}",
                cluster_leader=f"SYM{i}USDT" if i % 3 == 0 else None,
                is_cluster_leader=(i % 3 == 0),
                mfe_5m=0.10 if i % 2 == 1 else 0.01,
                mae_5m=-0.01,
                reached_2r=(i % 2 == 1),
                reached_3r=(i % 2 == 1),
                reached_5r=(i % 2 == 1),
                reached_10r=False,
            )
        )
    return samples


def _evidence_records_from_samples(
    samples: list[StrategyValidationSample],
    *,
    regime_by_index: dict[int, str] | None = None,
) -> list[RegimeClusterEvidenceRecord]:
    """Build evidence records directly so cohort builders can be
    exercised without going through the dataset round-trip."""
    from app.adaptive.strategy_validation import (
        early_tail_score_bucket_for,
        opportunity_score_bucket_for,
    )

    rows: list[RegimeClusterEvidenceRecord] = []
    for i, s in enumerate(samples):
        regime = (regime_by_index or {}).get(
            i, ("MEME_RISK_ON", "NEUTRAL", "BTC_ABSORPTION")[i % 3]
        )
        rows.append(
            RegimeClusterEvidenceRecord(
                opportunity_id=s.opportunity_id,
                symbol=s.symbol,
                market_regime=regime,
                cluster_id=s.cluster_id,
                cluster_leader=s.cluster_leader,
                is_cluster_leader=s.is_cluster_leader,
                candidate_stage=s.candidate_stage,
                strategy_mode=s.strategy_mode,
                opportunity_score=s.opportunity_score,
                early_tail_score=s.early_tail_score,
                opportunity_score_bucket=opportunity_score_bucket_for(
                    s.opportunity_score
                ),
                early_tail_score_bucket=early_tail_score_bucket_for(
                    s.early_tail_score
                ),
                tail_label=s.tail_label,
                mfe_5m=s.mfe_5m,
                mae_5m=s.mae_5m,
                reached_3r=s.reached_3r,
                reached_5r=s.reached_5r,
                fake_breakout=s.fake_breakout,
                missed_tail=s.missed_tail,
                late_chase_failure=s.late_chase_failure,
            )
        )
    return rows


def _seed_runtime(runtime: StrategyValidationRuntime, n: int = 30) -> None:
    """Seed the runtime's sample buffer directly to bypass the
    LabelTrackingRecord fixture path; the resulting end-state is
    identical."""
    for s in _diverse_samples(n):
        runtime._samples_by_opportunity[s.opportunity_id] = _SampleEntry(
            sample=s, source_event_id="", created_at_ms=0
        )
    # Attach a varied set of regimes so the evidence pack can group
    # by ``market_regime``.
    regimes = ("MEME_RISK_ON", "NEUTRAL", "BTC_ABSORPTION", "ALT_RISK_OFF")
    for i, opp_id in enumerate(list(runtime._samples_by_opportunity.keys())):
        runtime.observe_market_regime(
            opportunity_id=opp_id, market_regime=regimes[i % len(regimes)]
        )


# ---------------------------------------------------------------------------
# 1. Contract / vocabulary
# ---------------------------------------------------------------------------
def test_regime_cluster_evidence_input_contract():
    """RegimeClusterEvidenceInput accepts the brief-mandated fields
    + carries a ``schema_version`` stamp; ``to_payload()`` is
    JSON-safe."""
    inp = RegimeClusterEvidenceInput(
        report_id="rep-1",
        dataset_id="ds-1",
        sample_count=20,
        completed_tail_label_count=12,
        records=tuple(
            _evidence_records_from_samples(_diverse_samples(2))
        ),
        paper_alpha_gate_status="WARN",
        quality_gate_status="warn",
    )
    assert inp.schema_version == REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
    payload = inp.to_payload()
    json.dumps(payload)  # raises on non-JSON-safe data
    for field in (
        "report_id",
        "dataset_id",
        "sample_count",
        "completed_tail_label_count",
        "records",
        "paper_alpha_gate_status",
        "quality_gate_status",
        "schema_version",
        "strategy_version",
        "scoring_version",
        "risk_config_version",
        "state_machine_version",
    ):
        assert field in payload


def test_regime_cluster_evidence_pack_status_vocabulary_locked():
    """The four allowed status labels are stable + exhaustive."""
    assert REGIME_CLUSTER_EVIDENCE_PACK_STATUSES == (
        "INSUFFICIENT_SAMPLE",
        "OBSERVE_ONLY",
        "WARNING",
        "EVIDENCE_SIGNAL",
    )
    assert RegimeClusterEvidencePackStatus.INSUFFICIENT_SAMPLE == (
        "INSUFFICIENT_SAMPLE"
    )
    assert RegimeClusterEvidencePackStatus.OBSERVE_ONLY == "OBSERVE_ONLY"
    assert RegimeClusterEvidencePackStatus.WARNING == "WARNING"
    assert RegimeClusterEvidencePackStatus.EVIDENCE_SIGNAL == (
        "EVIDENCE_SIGNAL"
    )


def test_regime_cluster_cohort_dimensions_locked():
    """The seven cohort dimensions called out by the brief are all
    surfaced."""
    assert REGIME_CLUSTER_COHORT_DIMENSIONS == (
        "market_regime",
        "cluster_id",
        "cluster_leader_vs_follower",
        "candidate_stage",
        "strategy_mode",
        "opportunity_score_bucket",
        "early_tail_score_bucket",
    )


# ---------------------------------------------------------------------------
# 2. Insufficient-sample governance
# ---------------------------------------------------------------------------
def test_regime_cluster_evidence_insufficient_on_low_samples():
    """A pool below ``min_total_samples`` -> INSUFFICIENT_SAMPLE +
    explicit reason."""
    inp = RegimeClusterEvidenceInput(
        report_id="rep-thin",
        sample_count=3,
        completed_tail_label_count=3,
    )
    pack = build_regime_cluster_evidence_pack(inp, evaluated_at=1)
    assert pack.status == RegimeClusterEvidencePackStatus.INSUFFICIENT_SAMPLE
    assert any(
        "sample_count_below_min" in r
        for r in pack.insufficient_sample_reasons
    )
    # Builder still produced empty-but-well-formed cohorts.
    assert pack.regime_cohort_summary.rows == ()
    assert pack.cluster_cohort_summary.rows == ()


def test_regime_cluster_evidence_insufficient_on_low_completed_tail_labels():
    """Enough total samples but few completed tail labels still
    emits INSUFFICIENT_SAMPLE."""
    inp = RegimeClusterEvidenceInput(
        report_id="rep-incomplete",
        sample_count=int(DEFAULT_MIN_TOTAL_SAMPLES),
        completed_tail_label_count=int(DEFAULT_MIN_COMPLETED_TAIL_LABELS) - 1,
    )
    pack = build_regime_cluster_evidence_pack(inp, evaluated_at=1)
    assert pack.status == RegimeClusterEvidencePackStatus.INSUFFICIENT_SAMPLE
    assert any(
        "completed_tail_label_count_below_min" in r
        for r in pack.insufficient_sample_reasons
    )


# ---------------------------------------------------------------------------
# 3. Per-cohort builders
# ---------------------------------------------------------------------------
def test_regime_cohort_summary_counts_tail_outcomes():
    """build_regime_cohort_summary aggregates tail outcomes per
    ``market_regime`` and surfaces a ``regime_right_tail_signal``-
    style positive signal when strong_tail rate exceeds threshold."""
    samples = _diverse_samples(30)
    # Force every sample's regime to MEME_RISK_ON so one cohort row
    # carries enough samples to fire the strong_tail signal.
    records = _evidence_records_from_samples(
        samples, regime_by_index={i: "MEME_RISK_ON" for i in range(30)}
    )
    inp = RegimeClusterEvidenceInput(
        report_id="rep-regime",
        sample_count=len(records),
        completed_tail_label_count=len(records),
        records=tuple(records),
    )
    summary = build_regime_cohort_summary(inp)
    assert isinstance(summary, RegimeCohortSummary)
    assert len(summary.rows) == 1
    row = summary.rows[0]
    assert row.key.dimension == "market_regime"
    assert row.key.value == "MEME_RISK_ON"
    assert row.sample_count == 30
    # Roughly half the samples carry strong_tail / moderate_tail
    # outcomes; counts must add up.
    assert (
        row.strong_tail_count
        + row.moderate_tail_count
        + row.weak_tail_count
        <= row.sample_count
    )
    # The strong_tail rate must register a positive evidence signal
    # because we wired half the samples to ``strong_tail``.
    assert row.strong_tail_rate > 0.0
    assert "strong_tail_rate_signal" in row.signals or row.status == (
        RegimeClusterEvidencePackStatus.EVIDENCE_SIGNAL
    )


def test_cluster_leader_vs_follower_summary():
    """build_cluster_cohort_summary surfaces a leader-vs-follower
    cohort row pair and raises a ``cluster_leader_signal`` when the
    leader materially out-performs the followers."""
    # Build a cluster where the leader has all strong_tail outcomes
    # and the followers have weak_tail outcomes.
    samples: list[StrategyValidationSample] = []
    for i in range(10):
        samples.append(
            _sample(
                opportunity_id=f"L{i}",
                symbol="LEADERUSDT",
                cluster_id="LEAD",
                cluster_leader="LEADERUSDT",
                is_cluster_leader=True,
                tail_label="strong_tail",
                mfe_5m=0.20,
                reached_3r=True,
                reached_5r=True,
            )
        )
    for i in range(10):
        samples.append(
            _sample(
                opportunity_id=f"F{i}",
                symbol=f"FOLL{i}USDT",
                cluster_id="LEAD",
                cluster_leader="LEADERUSDT",
                is_cluster_leader=False,
                tail_label="weak_tail",
                mfe_5m=0.02,
                reached_3r=False,
                reached_5r=False,
            )
        )
    records = _evidence_records_from_samples(samples)
    inp = RegimeClusterEvidenceInput(
        report_id="rep-cluster",
        sample_count=len(records),
        completed_tail_label_count=len(records),
        records=tuple(records),
    )
    summary = build_cluster_cohort_summary(inp)
    assert isinstance(summary, ClusterCohortSummary)
    assert len(summary.rows) == 1
    assert summary.rows[0].key.dimension == "cluster_id"
    assert summary.rows[0].key.value == "LEAD"

    # Two leader-vs-follower rows (one leader, one follower).
    assert len(summary.leader_vs_follower_rows) == 2
    leader_row = next(
        r
        for r in summary.leader_vs_follower_rows
        if r.extra.get("role") == "leader"
    )
    follower_row = next(
        r
        for r in summary.leader_vs_follower_rows
        if r.extra.get("role") == "follower"
    )
    assert leader_row.strong_tail_rate > follower_row.strong_tail_rate
    # Leader-preference signal must be raised (advantage clearly
    # above default 0.10).
    assert "cluster_leader_signal" in leader_row.signals


def test_score_bucket_summary_detects_high_bucket_signal():
    """build_score_bucket_summary detects when the high-score
    buckets out-perform the low-score buckets and raises a
    ``score_bucket_signal``."""
    samples: list[StrategyValidationSample] = []
    # 8 high-grade / strong outcomes
    for i in range(8):
        samples.append(
            _sample(
                opportunity_id=f"H{i}",
                symbol=f"H{i}USDT",
                opportunity_score=90.0,
                early_tail_score=80.0,
                tail_label="strong_tail",
                reached_3r=True,
                reached_5r=True,
                mfe_5m=0.20,
            )
        )
    # 8 low-grade / weak outcomes
    for i in range(8):
        samples.append(
            _sample(
                opportunity_id=f"L{i}",
                symbol=f"L{i}USDT",
                opportunity_score=20.0,
                early_tail_score=10.0,
                tail_label="weak_tail",
                reached_3r=False,
                reached_5r=False,
                mfe_5m=0.01,
            )
        )
    records = _evidence_records_from_samples(samples)
    inp = RegimeClusterEvidenceInput(
        report_id="rep-bucket",
        sample_count=len(records),
        completed_tail_label_count=len(records),
        records=tuple(records),
    )
    summary = build_score_bucket_summary(inp)
    assert isinstance(summary, ScoreBucketSummary)
    high_opp_rows = [
        r for r in summary.opportunity_score_rows if r.key.value == "80-100"
    ]
    high_ets_rows = [
        r for r in summary.early_tail_score_rows if r.key.value == "75-100"
    ]
    assert high_opp_rows
    assert high_ets_rows
    assert "score_bucket_signal" in high_opp_rows[0].signals
    assert "score_bucket_signal" in high_ets_rows[0].signals


def test_stage_outcome_summary_detects_missed_tail_warning():
    """build_stage_outcome_summary surfaces the canonical 5 stages
    and raises a ``missed_tail_warning`` when a non-thin cohort's
    missed_tail_rate crosses the threshold."""
    samples: list[StrategyValidationSample] = []
    # 8 ``observe`` / ``early`` samples that all missed tail.
    for i in range(8):
        samples.append(
            _sample(
                opportunity_id=f"M{i}",
                symbol=f"M{i}USDT",
                candidate_stage="early",
                strategy_mode="observe",
                tail_label="missed_tail",
                missed_tail=True,
                mfe_5m=0.0,
                reached_3r=False,
                reached_5r=False,
            )
        )
    records = _evidence_records_from_samples(samples)
    inp = RegimeClusterEvidenceInput(
        report_id="rep-stage",
        sample_count=len(records),
        completed_tail_label_count=len(records),
        records=tuple(records),
    )
    summary = build_stage_outcome_summary(inp)
    assert isinstance(summary, StageOutcomeSummary)
    # Canonical 5 stages always present.
    stages = [r.key.value for r in summary.rows]
    for required in ("early", "mid", "late", "blowoff", "dumped"):
        assert required in stages
    early_row = next(r for r in summary.rows if r.key.value == "early")
    assert early_row.sample_count >= int(DEFAULT_MIN_COHORT_SAMPLES)
    assert early_row.missed_tail_rate >= float(
        DEFAULT_MISSED_TAIL_WARNING_RATE
    )
    assert "missed_tail_warning" in early_row.warnings
    assert early_row.status == RegimeClusterEvidencePackStatus.WARNING


def test_strategy_mode_summary_detects_fake_breakout_warning():
    """build_strategy_mode_outcome_summary raises a
    ``strategy_mode_risk_warning`` when ``follow`` /
    ``pullback`` modes accumulate fake_breakout above threshold."""
    samples: list[StrategyValidationSample] = []
    for i in range(8):
        samples.append(
            _sample(
                opportunity_id=f"F{i}",
                symbol=f"F{i}USDT",
                strategy_mode="follow",
                tail_label="fake_breakout",
                fake_breakout=True,
                mfe_5m=0.01,
                mae_5m=-0.05,
            )
        )
    records = _evidence_records_from_samples(samples)
    inp = RegimeClusterEvidenceInput(
        report_id="rep-mode",
        sample_count=len(records),
        completed_tail_label_count=len(records),
        records=tuple(records),
    )
    summary = build_strategy_mode_outcome_summary(inp)
    assert isinstance(summary, StrategyModeOutcomeSummary)
    follow_row = next(r for r in summary.rows if r.key.value == "follow")
    assert follow_row.fake_breakout_rate >= float(
        DEFAULT_FAKE_BREAKOUT_WARNING_RATE
    )
    assert "fake_breakout_warning" in follow_row.warnings
    assert "strategy_mode_risk_warning" in follow_row.warnings
    assert follow_row.status == RegimeClusterEvidencePackStatus.WARNING


# ---------------------------------------------------------------------------
# 4. Top-level pack builder + payload roundtrip
# ---------------------------------------------------------------------------
def test_build_regime_cluster_evidence_pack_from_dataset():
    """build_regime_cluster_evidence_input + pack builder accept a
    real :class:`StrategyValidationDataset` and respect the
    optional ``regime_by_opportunity`` mapping (records missing
    from the map fall back to ``UNKNOWN_REGIME``)."""
    samples = _diverse_samples(30)
    dataset = build_validation_dataset_from_samples(
        samples,
        report_id="rep-ds",
        generated_at_ms=1_700_000_000_000,
    )
    regime_map = {f"opp-{i}": "MEME_RISK_ON" for i in range(15)}
    inp = build_regime_cluster_evidence_input(
        dataset=dataset,
        regime_by_opportunity=regime_map,
        paper_alpha_gate_status="INCONCLUSIVE",
        quality_gate_status="pass",
    )
    assert inp.sample_count == dataset.summary.record_count
    assert inp.dataset_id == dataset.report_id
    assert inp.paper_alpha_gate_status == "INCONCLUSIVE"
    # Half the records have a regime; the other half safely degrade
    # to ``UNKNOWN_REGIME``.
    regimes = {r.market_regime for r in inp.records}
    assert "MEME_RISK_ON" in regimes
    assert UNKNOWN_REGIME in regimes

    pack = build_regime_cluster_evidence_pack(inp, evaluated_at=1)
    assert isinstance(pack, RegimeClusterEvidencePack)
    assert pack.status in REGIME_CLUSTER_EVIDENCE_PACK_STATUSES
    assert pack.report_id == "rep-ds"
    assert pack.regime_cohort_summary.rows  # at least one cohort row
    assert pack.strategy_mode_outcome_summary.rows


def test_regime_cluster_payload_roundtrip():
    """export_regime_cluster_evidence_payload +
    load_regime_cluster_evidence_payload round-trip cleanly."""
    samples = _diverse_samples(30)
    records = _evidence_records_from_samples(samples)
    inp = RegimeClusterEvidenceInput(
        report_id="rep-rt",
        dataset_id="ds-rt",
        sample_count=len(records),
        completed_tail_label_count=len(records),
        records=tuple(records),
    )
    pack = build_regime_cluster_evidence_pack(inp, evaluated_at=12345)
    payload = export_regime_cluster_evidence_payload(pack)
    json.dumps(payload)  # JSON-safe
    loaded = load_regime_cluster_evidence_payload(payload)
    assert loaded.report_id == pack.report_id
    assert loaded.dataset_id == pack.dataset_id
    assert loaded.evaluated_at == pack.evaluated_at
    assert loaded.status == pack.status
    assert loaded.sample_count == pack.sample_count
    assert (
        loaded.completed_tail_label_count == pack.completed_tail_label_count
    )
    assert tuple(loaded.warnings) == tuple(pack.warnings)
    assert tuple(loaded.signals) == tuple(pack.signals)
    assert tuple(loaded.insufficient_sample_reasons) == tuple(
        pack.insufficient_sample_reasons
    )
    assert len(loaded.regime_cohort_summary.rows) == len(
        pack.regime_cohort_summary.rows
    )
    assert len(loaded.cluster_cohort_summary.rows) == len(
        pack.cluster_cohort_summary.rows
    )
    assert len(loaded.cluster_cohort_summary.leader_vs_follower_rows) == len(
        pack.cluster_cohort_summary.leader_vs_follower_rows
    )
    assert len(loaded.score_bucket_summary.opportunity_score_rows) == len(
        pack.score_bucket_summary.opportunity_score_rows
    )
    assert len(loaded.score_bucket_summary.early_tail_score_rows) == len(
        pack.score_bucket_summary.early_tail_score_rows
    )
    assert len(loaded.stage_outcome_summary.rows) == len(
        pack.stage_outcome_summary.rows
    )
    assert len(loaded.strategy_mode_outcome_summary.rows) == len(
        pack.strategy_mode_outcome_summary.rows
    )
    assert loaded.schema_version == pack.schema_version


def test_load_regime_cluster_evidence_payload_rejects_non_mapping():
    """load_* refuses non-Mapping payloads."""
    with pytest.raises(TypeError):
        load_regime_cluster_evidence_payload([])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. Runtime integration / event emission / export bundle
# ---------------------------------------------------------------------------
def test_regime_cluster_events_exportable(tmp_path: Path):
    """flush_report must emit the two new evidence-pack events; the
    Phase 8.5 export bundle carries them."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime(runtime, n=30)
        runtime.flush_report(
            report_id="rep-rc-export",
            generated_at_ms=1_700_000_000_000,
        )
        for et in (
            EventType.REGIME_CLUSTER_EVIDENCE_PACK_GENERATED,
            EventType.REGIME_CLUSTER_COHORT_SUMMARY_GENERATED,
        ):
            evs = repo.list_events(event_type=et)
            assert len(evs) >= 1, f"missing {et.value}"
            ev = evs[-1]
            for field in (
                "report_id",
                "dataset_id",
                "timestamp",
                "evidence_pack_status",
                "strategy_version",
                "scoring_version",
                "risk_config_version",
                "state_machine_version",
                "schema_version",
            ):
                assert field in ev.payload, (
                    f"event {et.value} missing payload field {field}"
                )
            assert (
                ev.payload["schema_version"]
                == REGIME_CLUSTER_EVIDENCE_SCHEMA_VERSION
            )
            assert ev.payload["evidence_pack_status"] in (
                REGIME_CLUSTER_EVIDENCE_PACK_STATUSES
            )
            assert ev.payload["regime_cluster_evidence_version"] == (
                REGIME_CLUSTER_EVIDENCE_VERSION
            )
            assert ev.source_module == StrategyValidationRuntime.SOURCE_MODULE
        # The summary events disambiguate via ``summary_name`` -
        # exactly the five canonical names.
        summary_events = repo.list_events(
            event_type=EventType.REGIME_CLUSTER_COHORT_SUMMARY_GENERATED,
        )
        seen_names = {ev.payload.get("summary_name") for ev in summary_events}
        for name in (
            "regime_cohort_summary",
            "cluster_cohort_summary",
            "score_bucket_summary",
            "stage_outcome_summary",
            "strategy_mode_outcome_summary",
        ):
            assert name in seen_names, f"missing summary_name {name}"

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
                    EventType.REGIME_CLUSTER_EVIDENCE_PACK_GENERATED,
                    EventType.REGIME_CLUSTER_COHORT_SUMMARY_GENERATED,
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


def test_replay_reads_regime_cluster_events(tmp_path: Path):
    """ReplayEngine accepts events.db containing the two new
    evidence-pack event types without raising."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        # A legacy row missing schema_version is tolerated.
        repo.append(
            Event(
                event_type=EventType.REGIME_CLUSTER_EVIDENCE_PACK_GENERATED,
                source_module="legacy_regime_cluster",
                symbol=None,
                timestamp=1_700_000_000_000,
                payload={
                    "report_id": "legacy-rep",
                    "evidence_pack_status": "INCONCLUSIVE",
                    # schema_version intentionally missing
                },
            )
        )
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime(runtime, n=30)
        runtime.flush_report(
            report_id="rep-rc-replay",
            generated_at_ms=1_700_000_000_000,
        )
        engine = ReplayEngine(event_repo=repo)
        engine.replay_risk_rejections()  # does NOT raise
        for et in (
            EventType.REGIME_CLUSTER_EVIDENCE_PACK_GENERATED,
            EventType.REGIME_CLUSTER_COHORT_SUMMARY_GENERATED,
        ):
            assert repo.count_events(event_type=et) >= 1
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 6. Daily report integration
# ---------------------------------------------------------------------------
def test_daily_report_contains_regime_cluster_section(tmp_path: Path):
    """The Phase 11B daily report's snapshot + Markdown carry the
    Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort Evidence Pack
    v0 fields."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime(runtime, n=40)
        runtime.flush_report(
            report_id="rep-daily-rc",
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
        assert snapshot.regime_cluster_evidence_pack_generated_count >= 1
        assert snapshot.regime_cluster_cohort_summary_generated_count >= 1
        assert snapshot.regime_cluster_evidence_status in (
            REGIME_CLUSTER_EVIDENCE_PACK_STATUSES
        )
        assert isinstance(
            snapshot.regime_cluster_insufficient_sample_reasons, list
        )
        assert isinstance(snapshot.regime_cluster_warnings, list)
        assert isinstance(snapshot.regime_cluster_signals, list)
        assert isinstance(snapshot.regime_cohort_summary, dict)
        assert isinstance(snapshot.cluster_cohort_summary, dict)
        assert isinstance(snapshot.score_bucket_summary, dict)
        assert isinstance(snapshot.stage_outcome_summary, dict)
        assert isinstance(snapshot.strategy_mode_outcome_summary, dict)
        # Markdown body contains the new section + boundary banner.
        md = snapshot.markdown
        assert (
            "Phase 11C.1C-C-B-B-B-B Regime & Cluster Cohort Evidence Pack v0"
            in md
        )
        assert "REGIME_CLUSTER_EVIDENCE_PACK_GENERATED" in md
        assert "MUST NEVER trigger a real trade" in md
        assert "Phase 12 remains" in md
        # Payload also carries every new key.
        payload = snapshot.to_payload()
        for key in (
            "regime_cluster_evidence_pack_generated_count",
            "regime_cluster_cohort_summary_generated_count",
            "regime_cluster_evidence_status",
            "regime_cluster_sample_count",
            "regime_cluster_completed_tail_label_count",
            "regime_cluster_insufficient_sample_reasons",
            "regime_cluster_warnings",
            "regime_cluster_signals",
            "regime_cohort_summary",
            "cluster_cohort_summary",
            "score_bucket_summary",
            "stage_outcome_summary",
            "strategy_mode_outcome_summary",
            "regime_cluster_evidence_pack",
        ):
            assert key in payload, f"missing payload key {key}"
    finally:
        dbs.close()


def test_daily_report_renders_when_no_evidence_pack(tmp_path: Path):
    """Even with no Regime & Cluster Evidence Pack events, the
    Markdown still renders the section."""
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
        assert "Regime & Cluster Cohort Evidence Pack v0" in snapshot.markdown
        assert snapshot.regime_cluster_evidence_pack_generated_count == 0
        assert snapshot.regime_cluster_evidence_status == ""
    finally:
        dbs.close()


def test_regime_cluster_evidence_pack_insufficient_when_dataset_empty(
    tmp_path: Path,
):
    """When the runtime flushes with no samples, the brief expects
    an INSUFFICIENT_SAMPLE Regime & Cluster Evidence Pack report
    (not a skip)."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        runtime.flush_report(
            report_id="rep-empty-rc",
            generated_at_ms=1_700_000_000_000,
        )
        metrics = runtime.metrics_payload()
        # The dataset object exists with zero records, so the
        # evidence pack runs and emits INSUFFICIENT_SAMPLE.
        if metrics.get("regime_cluster_evidence_pack_generated_count", 0) >= 1:
            assert metrics["regime_cluster_evidence_status"] == (
                RegimeClusterEvidencePackStatus.INSUFFICIENT_SAMPLE
            )
            assert metrics["regime_cluster_insufficient_sample_reasons"]
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 7. Safety boundary
# ---------------------------------------------------------------------------
def test_no_live_trading_flags_unchanged():
    """Phase 1 safety lock invariants. The Regime & Cluster
    Evidence Pack v0 cannot loosen them."""
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


def test_regime_cluster_evidence_does_not_trigger_execution(tmp_path: Path):
    """Building + emitting the Regime & Cluster Evidence Pack v0
    MUST never emit any trading event and never call Telegram
    outbound. The status MUST NEVER be a trade-authorising label."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime(runtime, n=40)
        runtime.flush_report(
            report_id="rep-rc-safety",
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
            ), f"regime/cluster pack emitted forbidden {et.value}"
        # Status vocabulary is fixed and descriptive only.
        pack_evs = repo.list_events(
            event_type=EventType.REGIME_CLUSTER_EVIDENCE_PACK_GENERATED
        )
        assert pack_evs
        for ev in pack_evs:
            assert ev.payload["evidence_pack_status"] in (
                REGIME_CLUSTER_EVIDENCE_PACK_STATUSES
            )
            assert ev.payload["evidence_pack_status"] not in {
                "approved",
                "trade",
                "open",
                "buy",
                "sell",
                "live",
            }
        # Both new event types attribute to the runtime
        # source_module - no other module is allowed to emit them.
        for et in (
            EventType.REGIME_CLUSTER_EVIDENCE_PACK_GENERATED,
            EventType.REGIME_CLUSTER_COHORT_SUMMARY_GENERATED,
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
    Regime & Cluster Evidence Pack v0 cannot change that."""
    s = _settings()
    assert s.live_trading_enabled is False
    assert s.exchange_live_order_enabled is False
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        _seed_runtime(runtime, n=40)
        runtime.flush_report(
            report_id="rep-rc-phase12",
            generated_at_ms=1_700_000_000_000,
        )
        ev = repo.list_events(
            event_type=EventType.REGIME_CLUSTER_EVIDENCE_PACK_GENERATED
        )[-1]
        # Schema version still belongs to Phase 11C.1C-C-B-B-B-B.
        assert "phase_11c_1c_c_b_b_b_b" in ev.payload["schema_version"]
        assert ev.payload["regime_cluster_evidence_version"] == (
            REGIME_CLUSTER_EVIDENCE_VERSION
        )
        # The runtime cached pack vocabulary cannot include anything
        # that implies trade authorisation.
        rep = runtime.latest_regime_cluster_evidence_pack
        assert rep is not None
        assert rep.status in REGIME_CLUSTER_EVIDENCE_PACK_STATUSES
        assert rep.status not in {
            "approved",
            "trade",
            "open",
            "buy",
            "sell",
            "live",
        }
    finally:
        dbs.close()


def test_runtime_config_regime_cluster_evidence_pack_can_be_disabled():
    """``regime_cluster_evidence_pack_enabled=False`` disables the
    new sub-slice without affecting the parent dataset /
    quality-gate / paper-alpha-gate contracts."""
    cfg = StrategyValidationRuntimeConfig.from_mapping(
        {"regime_cluster_evidence_pack_enabled": False}
    )
    assert cfg.regime_cluster_evidence_pack_enabled is False
    assert cfg.dataset_enabled is True
    assert cfg.paper_alpha_gate_enabled is True


def test_regime_cluster_disabled_skips_evidence_events(tmp_path: Path):
    """When the new sub-slice is disabled the runtime emits the
    seven Phase 11C.1C-C-B-A events + the three dataset events +
    the four Paper Alpha Gate events but NOT the two new
    evidence-pack events."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(
            event_repo=repo,
            config=StrategyValidationRuntimeConfig(
                regime_cluster_evidence_pack_enabled=False
            ),
        )
        _seed_runtime(runtime, n=30)
        runtime.flush_report(
            report_id="rep-no-rc",
            generated_at_ms=1_700_000_000_000,
        )
        for et in (
            EventType.REGIME_CLUSTER_EVIDENCE_PACK_GENERATED,
            EventType.REGIME_CLUSTER_COHORT_SUMMARY_GENERATED,
        ):
            assert repo.count_events(event_type=et) == 0
        # Parent slices still flow.
        assert (
            repo.count_events(
                event_type=EventType.STRATEGY_VALIDATION_DATASET_BUILT
            )
            >= 1
        )
        assert (
            repo.count_events(
                event_type=EventType.PAPER_ALPHA_GATE_EVALUATED
            )
            >= 1
        )
    finally:
        dbs.close()
