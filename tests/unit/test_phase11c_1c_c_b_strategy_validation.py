"""Phase 11C.1C-C-B-A - Strategy Validation Lab v0 & Cluster
Exposure Control Contracts tests.

Pins every behaviour the brief calls out:

  - Strategy validation sample creation from a Phase 11C.1C-C-A
    LabelTrackingRecord + AdaptiveCandidateContext.
  - aggregate_by_strategy_mode / aggregate_by_candidate_stage /
    aggregate_by_opportunity_score_bucket /
    aggregate_by_early_tail_score_bucket / aggregate_tail_label_distribution.
  - Cluster leader validation + cluster exposure assessment
    (leader_only / observe_followers / reject_cluster / no_action).
  - observe / reject MUST be validated alongside follow / pullback.
  - Strategy validation events flow through Phase 8.5 export +
    Phase 10A replay.
  - Daily-report includes the Strategy Validation Lab v0 section.
  - Safety regression: every Phase 1 safety flag remains False;
    the runtime never emits any ORDER_* / POSITION_* / STOP_* /
    TELEGRAM_MESSAGE_SENT event; Phase 12 remains FORBIDDEN.

No real socket is opened. The runtime is paper / report only.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.adaptive import (
    AdaptiveCandidateContext,
    CandidateStageAssessment,
    LabelQueueRuntime,
    LabelQueueRuntimeConfig,
    LabelTrackingRecord,
    MarketRegimeAssessment,
    OpportunityScore,
    RuntimeCalibrationMetrics,
    StrategyModeDecision,
    TrackingWindowState,
)
from app.adaptive.cluster import build_cluster_context
from app.adaptive.label_queue import build_label_queue_contract
from app.adaptive.strategy_validation import (
    CLUSTER_ACTIONS,
    EARLY_TAIL_SCORE_BUCKET_LABELS,
    OPPORTUNITY_SCORE_BUCKET_LABELS,
    STRATEGY_VALIDATION_SCHEMA_VERSION,
    ClusterExposureAssessment,
    StrategyValidationReport,
    StrategyValidationSample,
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
from app.config.settings import get_settings, load_settings
from app.core.events import Event, EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.exports.service import TestDataExportService
from app.market_data_public.candidate_pool import (
    CANDIDATE_STATE_ACTIVE,
    Candidate,
)
from app.market_data_public.radar import (
    AllMarketRadarSnapshot,
    pre_anomaly_score_light,
)
from app.market_data_public.ws_radar_chain import WSRadarChainDriver
from app.learning.identity import OpportunityIdentity
from app.paper_run.daily_report import DailyReportBuilder
from app.replay.engine import ReplayEngine
from app.risk.engine import RiskEngine


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


def _make_window(
    *,
    name: str,
    mfe_pct: float = 0.0,
    mae_pct: float = 0.0,
    reached_2r: bool = False,
    reached_3r: bool = False,
    reached_5r: bool = False,
    reached_10r: bool = False,
    fake_breakout: bool = False,
    missed_tail: bool = False,
    tail_label: str = "",
) -> TrackingWindowState:
    return TrackingWindowState(
        window_name=name,
        window_seconds=300,
        window_start_ts=1_700_000_000_000,
        window_end_ts=1_700_000_300_000,
        start_price=1.0,
        latest_price=1.0 + mfe_pct,
        mfe_pct=mfe_pct,
        mae_pct=mae_pct,
        mfe_price=1.0 + max(0.0, mfe_pct),
        mae_price=1.0 + min(0.0, mae_pct),
        reached_2r=reached_2r,
        reached_3r=reached_3r,
        reached_5r=reached_5r,
        reached_10r=reached_10r,
        fake_breakout=fake_breakout,
        missed_tail=missed_tail,
        tail_label=tail_label,
        completed=True,
    )


def _make_label_record(
    *,
    opportunity_id: str = "opp-1",
    scan_batch_id: str = "batch-1",
    symbol: str = "EDENUSDT",
    candidate_stage: str = "early",
    strategy_mode: str = "follow",
    early_tail_score: float = 80.0,
    late_chase_risk: float = 10.0,
    opportunity_score: float = 75.0,
    final_tail_label: str = "strong_tail",
    primary_window: TrackingWindowState | None = None,
    extra_windows: list[TrackingWindowState] | None = None,
) -> LabelTrackingRecord:
    if primary_window is None:
        primary_window = _make_window(
            name="5m",
            mfe_pct=0.10,
            mae_pct=-0.01,
            reached_2r=True,
            reached_3r=True,
            reached_5r=True,
            tail_label=final_tail_label,
        )
    windows: list[TrackingWindowState] = [primary_window]
    if extra_windows:
        windows.extend(extra_windows)
    return LabelTrackingRecord(
        tracking_id=f"trk-{opportunity_id}",
        opportunity_id=opportunity_id,
        scan_batch_id=scan_batch_id,
        symbol=symbol,
        candidate_first_seen_ts=1_700_000_000_000,
        first_seen_price=1.0,
        current_price=1.10,
        tracking_started_ts=1_700_000_000_000,
        source_event_id="src-evt",
        early_tail_score=early_tail_score,
        opportunity_score=opportunity_score,
        strategy_mode=strategy_mode,
        candidate_stage=candidate_stage,
        late_chase_risk=late_chase_risk,
        freshness_score=0.9,
        distance_from_first_seen=0.10,
        distance_to_24h_high=0.0,
        virtual_risk_unit_pct=0.01,
        tracking_windows=windows,
        status="completed",
        final_tail_label=final_tail_label,
    )


def _make_adaptive_context(
    *,
    opportunity_id: str = "opp-1",
    scan_batch_id: str = "batch-1",
    symbol: str = "EDENUSDT",
    candidate_stage: str = "early",
    strategy_mode: str = "follow",
    early_tail_score: float = 80.0,
    late_chase_risk: float = 10.0,
    opportunity_score: float = 75.0,
    grade: str = "A",
    cluster_id: str = "USDT",
    cluster_leader: str | None = "EDENUSDT",
) -> AdaptiveCandidateContext:
    return AdaptiveCandidateContext(
        opportunity_id=opportunity_id,
        scan_batch_id=scan_batch_id,
        symbol=symbol,
        timestamp_ms=1_700_000_060_000,
        market_regime=MarketRegimeAssessment(
            regime_name="MEME_RISK_ON",
            confidence=0.7,
            risk_multiplier=1.0,
            allowed_strategy_modes=("follow", "pullback", "observe"),
        ),
        candidate_stage=CandidateStageAssessment(
            stage=candidate_stage,
            freshness=0.9,
            late_chase_risk=min(1.0, late_chase_risk / 100.0),
            blowoff_risk=0.0,
            first_seen_ts=1_700_000_000_000,
            first_seen_price=1.0,
            current_price=1.10,
            distance_from_first_seen=0.10,
            distance_to_24h_high=0.0,
        ),
        opportunity_score=OpportunityScore(
            momentum_strength=70.0,
            volume_expansion=60.0,
            liquidity_quality=50.0,
            regime_fit=70.0,
            freshness=80.0,
            manipulation_risk=10.0,
            late_chase_risk=10.0,
            score=opportunity_score,
            grade=grade,
        ),
        strategy_mode=StrategyModeDecision(
            mode=strategy_mode,
            follow_allowed=(strategy_mode in {"follow", "pullback"}),
            pullback_allowed=(strategy_mode == "pullback"),
            observe_only=(strategy_mode == "observe"),
        ),
        cluster=__import__(
            "app.adaptive.models", fromlist=["ClusterContext"]
        ).ClusterContext(
            cluster_id=cluster_id,
            cluster_leader=cluster_leader,
            cluster_rank=1 if symbol == cluster_leader else 2,
            cluster_size=2,
            cluster_reason=("test_fixture",),
        ),
        label_queue=build_label_queue_contract(
            opportunity_id=opportunity_id,
            scan_batch_id=scan_batch_id,
            symbol=symbol,
            enqueued_at_ms=1_700_000_060_000,
            reference_price=1.10,
        ),
        runtime_calibration=RuntimeCalibrationMetrics(
            candidate_first_seen_ts=1_700_000_000_000,
            candidate_first_seen_price=1.0,
            current_price=1.10,
            price_change_since_first_seen=0.10,
            quote_volume_acceleration_1m=0.0,
            quote_volume_acceleration_5m=0.0,
            price_acceleration_1m=0.0,
            price_acceleration_5m=0.0,
            volume_rank=5,
            volume_rank_jump_5m=4,
            distance_to_24h_high=0.0,
            distance_from_first_seen=0.10,
            freshness_score=0.9,
            late_chase_risk=late_chase_risk,
            early_tail_score=early_tail_score,
        ),
        strategy_version="phase_11c_1c_a.strategy.v1",
        scoring_version="phase_11c_1c_a.scoring.v1",
        risk_config_version="phase_11c_1c_a.risk_config.v1",
        state_machine_version="phase_11c_1c_a.state_machine.v1",
    )


def _sample(
    **overrides,
) -> StrategyValidationSample:
    """Convenience direct constructor for cohort tests."""
    defaults = dict(
        opportunity_id="opp",
        scan_batch_id="batch",
        symbol="X",
        candidate_stage="early",
        strategy_mode="follow",
        opportunity_score=75.0,
        opportunity_grade="A",
        early_tail_score=80.0,
        late_chase_risk=10.0,
        cluster_id="USDT",
        cluster_leader=None,
        is_cluster_leader=False,
        tail_label="unresolved",
        mfe_5m=0.0,
        mae_5m=0.0,
        mfe_15m=0.0,
        mae_15m=0.0,
        mfe_30m=0.0,
        mae_30m=0.0,
        mfe_1h=0.0,
        mae_1h=0.0,
        mfe_4h=0.0,
        mae_4h=0.0,
        reached_2r=False,
        reached_3r=False,
        reached_5r=False,
        reached_10r=False,
        fake_breakout=False,
        missed_tail=False,
        late_chase_failure=False,
    )
    defaults.update(overrides)
    return StrategyValidationSample(**defaults)


def _make_radar_snapshot(
    *,
    symbol: str = "EDENUSDT",
    last_price: float = 1.05,
    timestamp: int = 1_700_000_060_000,
) -> AllMarketRadarSnapshot:
    return AllMarketRadarSnapshot(
        symbol=symbol,
        timestamp=timestamp,
        last_price=last_price,
        price_change_pct_24h=0.05,
        price_acceleration_60s=0.012,
        quote_volume=50_000_000.0,
        quote_volume_delta_60s=1_000_000.0,
        volume_rank=5,
        volume_rank_jump=4,
        bid=last_price - 0.001,
        ask=last_price + 0.001,
        spread_pct=0.002,
        mark_price=last_price,
        funding_rate=0.0001,
    )


def _make_candidate(
    *,
    symbol: str = "EDENUSDT",
    snap: AllMarketRadarSnapshot | None = None,
    first_seen_ts: int = 1_700_000_000_000,
    first_seen_price: float = 1.00,
) -> Candidate:
    snap = snap or _make_radar_snapshot(symbol=symbol)
    score = pre_anomaly_score_light(snap)
    identity = OpportunityIdentity.create(
        symbol=symbol,
        source_phase="phase_11c_1b_ws_first_radar",
        first_seen_ts=first_seen_ts,
    )
    cand = Candidate(
        symbol=symbol,
        state=CANDIDATE_STATE_ACTIVE,
        radar_score=float(score.radar_score),
        reason_tags=tuple(score.reason_tags),
        source_streams=tuple(score.source_streams),
        snapshot=snap,
        identity=identity,
        first_seen_ms=first_seen_ts,
        last_seen_ms=int(snap.timestamp),
        first_seen_price=first_seen_price,
        quote_volume_first_seen=float(snap.quote_volume or 0.0),
        volume_rank_first_seen=int(snap.volume_rank or 0),
    )
    cand.price_history = [
        (first_seen_ts, first_seen_price),
        (first_seen_ts + 60_000, first_seen_price * 1.02),
        (int(snap.timestamp), float(snap.last_price)),
    ]
    cand.quote_volume_history = [
        (first_seen_ts, float(snap.quote_volume or 0.0) * 0.5),
        (first_seen_ts + 60_000, float(snap.quote_volume or 0.0) * 0.7),
        (int(snap.timestamp), float(snap.quote_volume or 0.0)),
    ]
    cand.volume_rank_history = [
        (first_seen_ts, max(1, int(snap.volume_rank or 0) + 5)),
        (int(snap.timestamp), int(snap.volume_rank or 0)),
    ]
    return cand


# ---------------------------------------------------------------------------
# Sample builder + sample-created event
# ---------------------------------------------------------------------------
def test_strategy_validation_sample_created():
    """Build a sample from a Phase 11C.1C-C-A label record + adaptive
    context. The sample must carry every brief-mandated field."""
    label = _make_label_record(
        opportunity_id="opp-A",
        symbol="EDENUSDT",
        candidate_stage="early",
        strategy_mode="follow",
        final_tail_label="strong_tail",
    )
    adaptive = _make_adaptive_context(
        opportunity_id="opp-A",
        symbol="EDENUSDT",
        candidate_stage="early",
        strategy_mode="follow",
        early_tail_score=85.0,
        opportunity_score=82.0,
        grade="S",
        cluster_id="USDT",
        cluster_leader="EDENUSDT",
    )
    sample = build_strategy_validation_sample(
        label_record=label,
        adaptive=adaptive,
        sample_created_ts=1_700_000_060_000,
    )
    assert sample.opportunity_id == "opp-A"
    assert sample.symbol == "EDENUSDT"
    assert sample.candidate_stage == "early"
    assert sample.strategy_mode == "follow"
    assert sample.opportunity_score == pytest.approx(82.0)
    assert sample.opportunity_grade == "S"
    assert sample.early_tail_score == pytest.approx(85.0)
    assert sample.tail_label == "strong_tail"
    assert sample.cluster_id == "USDT"
    assert sample.cluster_leader == "EDENUSDT"
    assert sample.is_cluster_leader is True
    # Per-window MFE/MAE must be populated for the primary 5m window.
    assert sample.mfe_5m == pytest.approx(0.10)
    assert sample.mae_5m == pytest.approx(-0.01)
    assert sample.reached_2r is True
    assert sample.reached_3r is True
    assert sample.reached_5r is True
    assert sample.reached_10r is False
    assert sample.fake_breakout is False
    assert sample.missed_tail is False
    assert sample.late_chase_failure is False
    # Versioning fields preserved.
    assert sample.strategy_version == "phase_11c_1c_a.strategy.v1"
    assert sample.scoring_version == "phase_11c_1c_a.scoring.v1"
    assert sample.risk_config_version == "phase_11c_1c_a.risk_config.v1"
    assert sample.state_machine_version == "phase_11c_1c_a.state_machine.v1"
    assert sample.schema_version == STRATEGY_VALIDATION_SCHEMA_VERSION
    # JSON-safe payload.
    json.dumps(sample.to_payload(), sort_keys=True)


def test_runtime_emits_strategy_validation_sample_created(tmp_path: Path):
    """Driving observe_label_record once must emit exactly one
    STRATEGY_VALIDATION_SAMPLE_CREATED with schema_version stamped."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        label = _make_label_record(opportunity_id="opp-A")
        adaptive = _make_adaptive_context(opportunity_id="opp-A")
        sample = runtime.observe_label_record(
            label_record=label,
            adaptive=adaptive,
            source_event_id="src-evt-1",
            sample_created_ts=1_700_000_060_000,
        )
        assert sample is not None
        events = repo.list_events(
            event_type=EventType.STRATEGY_VALIDATION_SAMPLE_CREATED
        )
        assert len(events) == 1
        ev = events[0]
        assert (
            ev.payload["schema_version"]
            == STRATEGY_VALIDATION_SCHEMA_VERSION
        )
        assert ev.payload["opportunity_id"] == "opp-A"
        assert ev.payload["scan_batch_id"]
        assert ev.payload["timestamp"] > 0
        assert ev.payload["strategy_version"]
        assert ev.payload["scoring_version"]
        assert ev.payload["risk_config_version"]
        assert ev.payload["state_machine_version"]
        # Idempotent: calling again with same opp must NOT re-emit.
        runtime.observe_label_record(
            label_record=label,
            adaptive=adaptive,
            source_event_id="src-evt-2",
        )
        events_after = repo.list_events(
            event_type=EventType.STRATEGY_VALIDATION_SAMPLE_CREATED
        )
        assert len(events_after) == 1
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Cohort aggregators
# ---------------------------------------------------------------------------
def test_aggregate_by_strategy_mode():
    """Aggregator emits stats for every canonical mode (follow /
    pullback / observe / reject) - even when a cohort is empty."""
    samples = [
        _sample(
            strategy_mode="follow",
            mfe_5m=0.10,
            mae_5m=-0.01,
            reached_2r=True,
            reached_3r=True,
            reached_5r=True,
            tail_label="strong_tail",
        ),
        _sample(
            strategy_mode="follow",
            mfe_5m=0.05,
            mae_5m=-0.02,
            reached_2r=True,
            tail_label="weak_tail",
        ),
        _sample(
            strategy_mode="pullback",
            mfe_5m=0.04,
            mae_5m=-0.005,
            reached_2r=True,
            tail_label="moderate_tail",
        ),
        _sample(
            strategy_mode="observe",
            mfe_5m=0.06,
            mae_5m=-0.001,
            tail_label="unresolved",
            missed_tail=True,
        ),
    ]
    out = aggregate_by_strategy_mode(samples)
    # Every canonical mode is present.
    for mode in ("follow", "pullback", "observe", "reject"):
        assert mode in out
    follow = out["follow"]
    assert follow.sample_count == 2
    # Average MFE = (0.10 + 0.05) / 2 = 0.075
    assert follow.avg_mfe == pytest.approx(0.075)
    assert follow.p_reached_2r == pytest.approx(1.0)
    assert follow.p_reached_5r == pytest.approx(0.5)
    assert follow.strong_tail_rate == pytest.approx(0.5)
    assert follow.weak_tail_rate == pytest.approx(0.5)
    # observe must be statisticked too (validates "did the runtime
    # correctly refuse").
    observe = out["observe"]
    assert observe.sample_count == 1
    assert observe.missed_tail_rate == pytest.approx(1.0)
    # reject is empty but still surfaced.
    assert out["reject"].sample_count == 0
    # Window stats present for every primary window plus all
    # secondary windows.
    assert "5m" in follow.window_stats
    assert "1h" in follow.window_stats


def test_aggregate_by_candidate_stage():
    """Aggregator emits stats for every canonical stage (early / mid
    / late / blowoff / dumped)."""
    samples = [
        _sample(
            candidate_stage="early",
            mfe_5m=0.10,
            tail_label="strong_tail",
            reached_2r=True,
            reached_3r=True,
            reached_5r=True,
        ),
        _sample(
            candidate_stage="early",
            mfe_5m=0.05,
            tail_label="strong_tail",
            reached_2r=True,
            reached_3r=True,
            reached_5r=True,
        ),
        _sample(
            candidate_stage="late",
            mfe_5m=0.03,
            mae_5m=-0.05,
            tail_label="fake_breakout",
            fake_breakout=True,
        ),
        _sample(
            candidate_stage="blowoff",
            mfe_5m=0.04,
            mae_5m=-0.04,
            tail_label="fake_breakout",
            fake_breakout=True,
        ),
        _sample(
            candidate_stage="dumped",
            mfe_5m=0.005,
            mae_5m=-0.08,
            tail_label="dumped",
        ),
    ]
    out = aggregate_by_candidate_stage(samples)
    for stage in ("early", "mid", "late", "blowoff", "dumped"):
        assert stage in out
    early = out["early"]
    assert early.sample_count == 2
    assert early.strong_tail_rate == pytest.approx(1.0)
    late = out["late"]
    assert late.sample_count == 1
    assert late.fake_breakout_rate == pytest.approx(1.0)
    blowoff = out["blowoff"]
    assert blowoff.sample_count == 1
    assert blowoff.fake_breakout_rate == pytest.approx(1.0)
    dumped = out["dumped"]
    assert dumped.sample_count == 1
    assert dumped.dumped_rate == pytest.approx(1.0)
    # mid is empty but still surfaced.
    assert out["mid"].sample_count == 0


def test_opportunity_score_bucket_validation():
    """Buckets are 0-49 / 50-64 / 65-79 / 80-100. High-score cohort
    should have a higher MFE than low-score cohort in the test."""
    samples = [
        _sample(opportunity_score=20.0, mfe_5m=0.005, tail_label="unresolved"),
        _sample(opportunity_score=55.0, mfe_5m=0.02, tail_label="weak_tail"),
        _sample(opportunity_score=70.0, mfe_5m=0.04, tail_label="moderate_tail"),
        _sample(opportunity_score=90.0, mfe_5m=0.10, tail_label="strong_tail",
                reached_2r=True, reached_3r=True, reached_5r=True),
        _sample(opportunity_score=85.0, mfe_5m=0.08, tail_label="strong_tail",
                reached_2r=True, reached_3r=True, reached_5r=True),
    ]
    out = aggregate_by_opportunity_score_bucket(samples)
    for label in OPPORTUNITY_SCORE_BUCKET_LABELS:
        assert label in out
    assert opportunity_score_bucket_for(20.0) == "0-49"
    assert opportunity_score_bucket_for(55.0) == "50-64"
    assert opportunity_score_bucket_for(70.0) == "65-79"
    assert opportunity_score_bucket_for(90.0) == "80-100"
    assert out["0-49"].sample_count == 1
    assert out["50-64"].sample_count == 1
    assert out["65-79"].sample_count == 1
    assert out["80-100"].sample_count == 2
    # The brief asks: do high-grade candidates have higher MFE?
    assert out["80-100"].avg_mfe > out["0-49"].avg_mfe
    assert out["80-100"].strong_tail_rate == pytest.approx(1.0)


def test_early_tail_score_bucket_validation():
    """Buckets are 0-24 / 25-49 / 50-74 / 75-100. High early_tail
    cohort should be the cohort with the most strong tail rate."""
    samples = [
        _sample(early_tail_score=10.0, mfe_5m=0.005, tail_label="unresolved"),
        _sample(early_tail_score=30.0, mfe_5m=0.01, tail_label="unresolved"),
        _sample(early_tail_score=60.0, mfe_5m=0.04, tail_label="moderate_tail",
                reached_2r=True, reached_3r=True),
        _sample(early_tail_score=80.0, mfe_5m=0.10, tail_label="strong_tail",
                reached_2r=True, reached_3r=True, reached_5r=True),
        _sample(early_tail_score=85.0, mfe_5m=0.12, tail_label="strong_tail",
                reached_2r=True, reached_3r=True, reached_5r=True),
    ]
    out = aggregate_by_early_tail_score_bucket(samples)
    for label in EARLY_TAIL_SCORE_BUCKET_LABELS:
        assert label in out
    assert early_tail_score_bucket_for(10.0) == "0-24"
    assert early_tail_score_bucket_for(30.0) == "25-49"
    assert early_tail_score_bucket_for(60.0) == "50-74"
    assert early_tail_score_bucket_for(80.0) == "75-100"
    assert out["75-100"].sample_count == 2
    assert out["75-100"].strong_tail_rate == pytest.approx(1.0)
    assert out["75-100"].avg_mfe > out["0-24"].avg_mfe


def test_tail_label_distribution():
    samples = [
        _sample(tail_label="strong_tail"),
        _sample(tail_label="strong_tail"),
        _sample(tail_label="moderate_tail"),
        _sample(tail_label="fake_breakout", fake_breakout=True),
        _sample(tail_label="dumped"),
        _sample(tail_label="unresolved"),
    ]
    dist = aggregate_tail_label_distribution(samples)
    assert dist.sample_count == 6
    assert dist.counts["strong_tail"] == 2
    assert dist.counts["moderate_tail"] == 1
    assert dist.counts["fake_breakout"] == 1
    assert dist.counts["dumped"] == 1
    assert dist.counts["unresolved"] == 1
    assert dist.rates["strong_tail"] == pytest.approx(2 / 6)
    assert dist.rates["fake_breakout"] == pytest.approx(1 / 6)


# ---------------------------------------------------------------------------
# Cluster validation + exposure
# ---------------------------------------------------------------------------
def test_cluster_leader_validation():
    """Leader must be compared to followers; the leader's MFE in the
    test exceeds the followers' so leader_outperformed_followers is
    True."""
    samples = [
        _sample(
            symbol="EDENUSDT",
            cluster_id="USDT",
            cluster_leader="EDENUSDT",
            is_cluster_leader=True,
            mfe_5m=0.12,
            tail_label="strong_tail",
        ),
        _sample(
            symbol="ALTUSDT",
            cluster_id="USDT",
            cluster_leader="EDENUSDT",
            is_cluster_leader=False,
            mfe_5m=0.04,
            tail_label="moderate_tail",
        ),
        _sample(
            symbol="NEARUSDT",
            cluster_id="USDT",
            cluster_leader="EDENUSDT",
            is_cluster_leader=False,
            mfe_5m=0.03,
            tail_label="weak_tail",
        ),
    ]
    stats_by_cluster = evaluate_cluster_leader_performance(samples)
    assert "USDT" in stats_by_cluster
    s = stats_by_cluster["USDT"]
    assert s.leader_symbol == "EDENUSDT"
    assert s.leader_sample_count == 1
    assert s.follower_sample_count == 2
    assert s.leader_avg_mfe == pytest.approx(0.12)
    assert s.follower_avg_mfe == pytest.approx(0.035)
    assert s.leader_strong_tail_rate == pytest.approx(1.0)
    assert s.follower_strong_tail_rate == pytest.approx(0.0)
    assert s.leader_outperformed_followers is True


def test_cluster_exposure_assessment_leader_only():
    """Leader strongly outperforms two followers -> action=leader_only."""
    samples = [
        _sample(
            symbol="EDENUSDT",
            cluster_id="USDT",
            cluster_leader="EDENUSDT",
            is_cluster_leader=True,
            mfe_5m=0.15,
            tail_label="strong_tail",
        ),
        _sample(
            symbol="ALTUSDT",
            cluster_id="USDT",
            cluster_leader="EDENUSDT",
            is_cluster_leader=False,
            mfe_5m=0.02,
            tail_label="weak_tail",
        ),
        _sample(
            symbol="NEARUSDT",
            cluster_id="USDT",
            cluster_leader="EDENUSDT",
            is_cluster_leader=False,
            mfe_5m=0.01,
            tail_label="weak_tail",
        ),
    ]
    out = assess_cluster_exposure(samples)
    assert len(out) == 1
    a = out[0]
    assert a.cluster_id == "USDT"
    assert a.leader_symbol == "EDENUSDT"
    assert "ALTUSDT" in a.follower_symbols
    assert "NEARUSDT" in a.follower_symbols
    assert a.cluster_size == 3
    assert a.correlated_candidate_count == 3
    assert a.leader_outperformed_followers is True
    assert a.suggested_cluster_action == "leader_only"
    assert "leader_outperformed" in a.reason_tags
    # 3 correlated candidates triggers overexposure_warning at the
    # default threshold.
    assert a.overexposure_warning is True
    # The action field is one of the canonical values.
    assert a.suggested_cluster_action in CLUSTER_ACTIONS


def test_cluster_exposure_assessment_observe_followers():
    """Followers outperform the leader -> action=observe_followers."""
    samples = [
        _sample(
            symbol="EDENUSDT",
            cluster_id="USDT",
            cluster_leader="EDENUSDT",
            is_cluster_leader=True,
            mfe_5m=0.01,
            tail_label="weak_tail",
        ),
        _sample(
            symbol="ALTUSDT",
            cluster_id="USDT",
            cluster_leader="EDENUSDT",
            is_cluster_leader=False,
            mfe_5m=0.10,
            tail_label="strong_tail",
        ),
        _sample(
            symbol="NEARUSDT",
            cluster_id="USDT",
            cluster_leader="EDENUSDT",
            is_cluster_leader=False,
            mfe_5m=0.08,
            tail_label="strong_tail",
        ),
    ]
    out = assess_cluster_exposure(samples)
    assert len(out) == 1
    a = out[0]
    assert a.suggested_cluster_action == "observe_followers"
    assert "followers_outperformed_leader" in a.reason_tags
    assert a.leader_outperformed_followers is False


def test_cluster_exposure_assessment_reject_cluster_when_all_dumped():
    """Every sample dumped + no strong tail -> action=reject_cluster."""
    samples = [
        _sample(
            symbol="ZBADUSDT",
            cluster_id="USDT",
            cluster_leader="ZBADUSDT",
            is_cluster_leader=True,
            mfe_5m=0.001,
            mae_5m=-0.10,
            tail_label="dumped",
        ),
        _sample(
            symbol="WBADUSDT",
            cluster_id="USDT",
            cluster_leader="ZBADUSDT",
            is_cluster_leader=False,
            mfe_5m=0.001,
            mae_5m=-0.12,
            tail_label="dumped",
        ),
    ]
    out = assess_cluster_exposure(samples)
    assert len(out) == 1
    assert out[0].suggested_cluster_action == "reject_cluster"
    assert "all_dumped" in out[0].reason_tags


def test_dumped_stage_is_not_a_long_opportunity():
    """The aggregator counts dumped samples but the report's flagged
    findings explicitly state that dumped is not a long opportunity."""
    samples = [
        _sample(candidate_stage="dumped", mfe_5m=0.0, mae_5m=-0.10,
                tail_label="dumped"),
    ]
    report = build_strategy_validation_report(samples, report_id="r1")
    assert report.by_candidate_stage["dumped"].sample_count == 1
    flagged = " ".join(report.flagged_findings)
    assert "dumped_stage_observed" in flagged
    assert "not_a_long_opportunity" in flagged


# ---------------------------------------------------------------------------
# Top-level report
# ---------------------------------------------------------------------------
def test_build_strategy_validation_report_empty_samples():
    """Empty sample list still returns a well-formed report."""
    report = build_strategy_validation_report([], report_id="empty-report")
    assert isinstance(report, StrategyValidationReport)
    assert report.sample_count == 0
    # Every canonical mode / stage / bucket is present, with zero
    # samples.
    for mode in ("follow", "pullback", "observe", "reject"):
        assert mode in report.by_strategy_mode
        assert report.by_strategy_mode[mode].sample_count == 0
    for stage in ("early", "mid", "late", "blowoff", "dumped"):
        assert stage in report.by_candidate_stage
    for bucket in OPPORTUNITY_SCORE_BUCKET_LABELS:
        assert bucket in report.by_opportunity_score_bucket
    for bucket in EARLY_TAIL_SCORE_BUCKET_LABELS:
        assert bucket in report.by_early_tail_score_bucket
    # JSON-safe payload.
    json.dumps(report.to_payload(), sort_keys=True)


def test_observe_and_reject_are_validated_without_trade_authorization(
    tmp_path: Path,
):
    """observe / reject MUST be aggregated AND emitting their cohort
    events MUST NOT cause any trading event (ORDER_*, POSITION_*,
    STOP_*, TELEGRAM_MESSAGE_SENT) to land in events.db."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(event_repo=repo)
        # Build samples that include observe + reject cohorts.
        for opp_id, mode, stage in [
            ("o1", "follow", "early"),
            ("o2", "observe", "late"),
            ("o3", "reject", "blowoff"),
            ("o4", "pullback", "mid"),
        ]:
            label = _make_label_record(
                opportunity_id=opp_id, candidate_stage=stage,
                strategy_mode=mode,
            )
            adaptive = _make_adaptive_context(
                opportunity_id=opp_id, candidate_stage=stage,
                strategy_mode=mode,
            )
            runtime.observe_label_record(
                label_record=label, adaptive=adaptive,
                sample_created_ts=1_700_000_060_000,
            )
        report = runtime.flush_report(generated_at_ms=1_700_000_120_000)
        # Both observe and reject cohorts present.
        assert report.by_strategy_mode["observe"].sample_count == 1
        assert report.by_strategy_mode["reject"].sample_count == 1
        # And STRATEGY_MODE_VALIDATED events for each cohort.
        sm_events = repo.list_events(
            event_type=EventType.STRATEGY_MODE_VALIDATED
        )
        modes_emitted = {ev.payload["strategy_mode"] for ev in sm_events}
        assert {"follow", "pullback", "observe", "reject"} <= modes_emitted
        # NO trading events.
        forbidden = {
            EventType.ORDER_SENT,
            EventType.ORDER_ACK,
            EventType.ORDER_FILLED,
            EventType.ORDER_PARTIAL_FILLED,
            EventType.ORDER_CANCELLED,
            EventType.POSITION_OPENED,
            EventType.POSITION_UPDATED,
            EventType.POSITION_CLOSED,
            EventType.STOP_SENT,
            EventType.STOP_CONFIRMED,
            EventType.TELEGRAM_MESSAGE_SENT,
        }
        for et in forbidden:
            assert (
                repo.count_events(event_type=et) == 0
            ), f"runtime emitted forbidden {et.value}"
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Chain integration + flush
# ---------------------------------------------------------------------------
def _wired_chain(repo: EventRepository) -> tuple[
    WSRadarChainDriver,
    LabelQueueRuntime,
    StrategyValidationRuntime,
]:
    risk = RiskEngine(event_repo=repo)
    label_runtime = LabelQueueRuntime(event_repo=repo)
    sv_runtime = StrategyValidationRuntime(event_repo=repo)
    chain = WSRadarChainDriver(
        risk_engine=risk,
        event_repo=repo,
        label_queue_runtime=label_runtime,
        strategy_validation_runtime=sv_runtime,
    )
    return chain, label_runtime, sv_runtime


def test_chain_driver_wires_strategy_validation(tmp_path: Path):
    """Driving one candidate through the chain produces exactly one
    strategy-validation sample and one ``STRATEGY_VALIDATION_SAMPLE_CREATED``
    event."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        chain, label_runtime, sv_runtime = _wired_chain(repo)
        chain.drive(_make_candidate())
        assert sv_runtime.sample_count == 1
        sample_evts = repo.list_events(
            event_type=EventType.STRATEGY_VALIDATION_SAMPLE_CREATED
        )
        assert len(sample_evts) == 1
        # Schema versioned.
        assert (
            sample_evts[0].payload["schema_version"]
            == STRATEGY_VALIDATION_SCHEMA_VERSION
        )
    finally:
        dbs.close()


def test_flush_report_emits_all_event_types(tmp_path: Path):
    """flush_report MUST emit each of the seven new event types at
    least once when there is at least one sample."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        chain, label_runtime, sv_runtime = _wired_chain(repo)
        chain.drive(_make_candidate(symbol="EDENUSDT"))
        chain.drive(_make_candidate(symbol="ALTUSDT"))
        report = sv_runtime.flush_report(generated_at_ms=1_700_001_000_000)
        assert report.sample_count == 2
        for et in (
            EventType.STRATEGY_VALIDATION_SAMPLE_CREATED,
            EventType.STRATEGY_VALIDATION_REPORT_GENERATED,
            EventType.STRATEGY_MODE_VALIDATED,
            EventType.CANDIDATE_STAGE_VALIDATED,
            EventType.SCORE_BUCKET_VALIDATED,
            EventType.CLUSTER_EXPOSURE_ASSESSED,
            EventType.CLUSTER_LEADER_VALIDATED,
        ):
            assert (
                repo.count_events(event_type=et) >= 1
            ), f"flush did not emit any {et.value}"
        # Identity / version block on every emitted event.
        report_evts = repo.list_events(
            event_type=EventType.STRATEGY_VALIDATION_REPORT_GENERATED
        )
        for ev in report_evts:
            payload = ev.payload
            for f in (
                "schema_version",
                "report_id",
                "timestamp",
                "strategy_version",
                "scoring_version",
                "risk_config_version",
                "state_machine_version",
                "validation_version",
                "source_phase",
            ):
                assert f in payload, f"missing {f} on report event"
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Daily report
# ---------------------------------------------------------------------------
def test_daily_report_contains_strategy_validation_metrics(tmp_path: Path):
    repo, dbs = _make_event_repo(tmp_path)
    try:
        chain, label_runtime, sv_runtime = _wired_chain(repo)
        chain.drive(_make_candidate(symbol="EDENUSDT"))
        chain.drive(_make_candidate(symbol="ALTUSDT"))
        sv_runtime.flush_report(generated_at_ms=1_700_001_000_000)

        out_dir = tmp_path / "reports"
        out_dir.mkdir()
        builder = DailyReportBuilder(event_repo=repo, output_dir=out_dir)
        snap = builder.build(
            started_at_ms=1_699_000_000_000,
            finished_at_ms=2_000_000_000_000,
            adaptive_metrics=chain.adaptive_metrics_payload(),
            label_runtime_metrics=label_runtime.metrics_payload(),
            strategy_validation_metrics=sv_runtime.metrics_payload(),
            write_to_disk=True,
        )
        # Every brief-mandated metric is present on the snapshot.
        assert snap.strategy_validation_sample_count >= 2
        assert snap.strategy_validation_sample_created_count >= 2
        assert snap.strategy_validation_report_generated_count >= 1
        assert snap.strategy_mode_validated_count >= 1
        assert snap.candidate_stage_validated_count >= 1
        assert snap.score_bucket_validated_count >= 1
        assert snap.cluster_exposure_assessed_count >= 1
        assert snap.cluster_leader_validated_count >= 1
        assert isinstance(snap.strategy_mode_validation, dict)
        assert isinstance(snap.candidate_stage_validation, dict)
        assert isinstance(snap.opportunity_score_bucket_validation, dict)
        assert isinstance(snap.early_tail_score_bucket_validation, dict)
        assert isinstance(snap.strategy_validation_tail_label_distribution, dict)
        assert isinstance(snap.top_strategy_validation_symbols, list)
        assert isinstance(snap.cluster_exposure_assessments, list)
        assert isinstance(snap.cluster_leader_validation, dict)
        # Markdown contains the new section.
        md = snap.markdown
        assert (
            "Phase 11C.1C-C-B-A Strategy Validation Lab v0" in md
        )
        assert "Cluster Exposure Control Contracts" in md
        assert "paper / report only" in md
        assert "Strategy mode validation" in md
        assert "Candidate stage validation" in md
        assert "Opportunity score bucket validation" in md
        assert "Early tail score bucket validation" in md
        assert "Cluster exposure assessments" in md
        assert "Cluster leader validation" in md
        # JSON-safe payload.
        json.dumps(snap.to_payload(), sort_keys=True, default=str)
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Export + Replay compatibility
# ---------------------------------------------------------------------------
def test_strategy_validation_events_exportable(tmp_path: Path):
    """Phase 8.5 export bundle must contain every Phase 11C.1C-C-B-A
    event type that landed in events.db."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        chain, label_runtime, sv_runtime = _wired_chain(repo)
        chain.drive(_make_candidate(symbol="EDENUSDT"))
        sv_runtime.flush_report(generated_at_ms=1_700_001_000_000)

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
                    EventType.STRATEGY_VALIDATION_SAMPLE_CREATED,
                    EventType.STRATEGY_VALIDATION_REPORT_GENERATED,
                    EventType.STRATEGY_MODE_VALIDATED,
                    EventType.CANDIDATE_STAGE_VALIDATED,
                    EventType.SCORE_BUCKET_VALIDATED,
                    EventType.CLUSTER_EXPOSURE_ASSESSED,
                    EventType.CLUSTER_LEADER_VALIDATED,
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


def test_replay_reads_strategy_validation_events(tmp_path: Path):
    """Replay engine must accept events.db containing the new events
    (mixed with old events) without raising."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        # Append an old, opaque event first.
        repo.append(
            Event(
                event_type=EventType.MARKET_SNAPSHOT,
                source_module="legacy",
                symbol="LEGACYUSDT",
                timestamp=1_700_000_000_000,
                payload={"hello": "world"},
            )
        )
        chain, label_runtime, sv_runtime = _wired_chain(repo)
        chain.drive(_make_candidate())
        sv_runtime.flush_report(generated_at_ms=1_700_001_000_000)

        engine = ReplayEngine(event_repo=repo)
        # Smoke: replay_risk_rejections walks every event without
        # raising on the new types.
        rejects = engine.replay_risk_rejections()
        assert isinstance(rejects, list)
        # And the new event types are queryable through the
        # repository.
        for et in (
            EventType.STRATEGY_VALIDATION_SAMPLE_CREATED,
            EventType.STRATEGY_VALIDATION_REPORT_GENERATED,
            EventType.CLUSTER_EXPOSURE_ASSESSED,
        ):
            assert repo.count_events(event_type=et) >= 1
    finally:
        dbs.close()


def test_replay_handles_missing_schema_version_field(tmp_path: Path):
    """A future event row without a schema_version field must NOT
    crash the replay engine."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        repo.append(
            Event(
                event_type=EventType.STRATEGY_VALIDATION_SAMPLE_CREATED,
                source_module="legacy_strategy_validation",
                symbol="LEGACYUSDT",
                timestamp=1_700_000_000_000,
                payload={
                    "opportunity_id": "legacy-opp",
                    "symbol": "LEGACYUSDT",
                    # schema_version intentionally missing
                },
            )
        )
        rows = repo.list_events(
            event_type=EventType.STRATEGY_VALIDATION_SAMPLE_CREATED
        )
        assert len(rows) == 1
        engine = ReplayEngine(event_repo=repo)
        engine.replay_risk_rejections()
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Safety boundary
# ---------------------------------------------------------------------------
def test_no_live_trading_flags_unchanged():
    """Phase 1 safety lock invariants - a regression test that mirrors
    the Phase 11C.1C-C-A safety check so a future PR cannot loosen
    them while passing the validation lab tests."""
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


def test_strategy_validation_does_not_trigger_execution(tmp_path: Path):
    """The runtime + chain integration must NEVER emit any of the
    trading event types (ORDER_*, POSITION_*, STOP_*) and never call
    Telegram outbound."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        chain, label_runtime, sv_runtime = _wired_chain(repo)
        chain.drive(_make_candidate(symbol="EDENUSDT"))
        chain.drive(_make_candidate(symbol="ALTUSDT"))
        sv_runtime.flush_report(generated_at_ms=1_700_001_000_000)
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
            ), f"strategy validation runtime emitted forbidden {et.value}"
        # Cluster action is one of the descriptive paper-only values.
        for ev in repo.list_events(
            event_type=EventType.CLUSTER_EXPOSURE_ASSESSED
        ):
            cluster = ev.payload["cluster"]
            assert cluster["suggested_cluster_action"] in CLUSTER_ACTIONS
        # SOURCE_MODULE attribution for every new event is the
        # validation runtime.
        for et in (
            EventType.STRATEGY_VALIDATION_SAMPLE_CREATED,
            EventType.STRATEGY_VALIDATION_REPORT_GENERATED,
            EventType.STRATEGY_MODE_VALIDATED,
            EventType.CANDIDATE_STAGE_VALIDATED,
            EventType.SCORE_BUCKET_VALIDATED,
            EventType.CLUSTER_EXPOSURE_ASSESSED,
            EventType.CLUSTER_LEADER_VALIDATED,
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
    validation lab cannot change that. Even after a flush_report,
    every Phase 1 safety flag must still be False AND no live trade
    can be authorised."""
    s = _settings()
    # Phase 1 safety flags from settings unchanged.
    assert s.live_trading_enabled is False
    assert s.exchange_live_order_enabled is False
    # The repository never sees a trading event after a full flush.
    repo, dbs = _make_event_repo(tmp_path)
    try:
        chain, label_runtime, sv_runtime = _wired_chain(repo)
        chain.drive(_make_candidate())
        sv_runtime.flush_report(generated_at_ms=1_700_001_000_000)
        # The cluster_action vocabulary cannot include anything that
        # implies trade authorisation.
        for action in CLUSTER_ACTIONS:
            assert action in {
                "leader_only",
                "observe_followers",
                "reject_cluster",
                "no_action",
            }
        # And the runtime's metrics_payload schema_version is the
        # Phase 11C.1C-C-B-A version label - confirming we have
        # NOT bumped to Phase 12.
        metrics = sv_runtime.metrics_payload()
        assert metrics["schema_version"] == STRATEGY_VALIDATION_SCHEMA_VERSION
        assert "phase_11c_1c_c_b_a" in metrics["schema_version"]
    finally:
        dbs.close()


def test_runtime_disabled_returns_none(tmp_path: Path):
    """Disabling the runtime by config must short-circuit every
    observe call."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(
            event_repo=repo,
            config=StrategyValidationRuntimeConfig(enabled=False),
        )
        adaptive = _make_adaptive_context()
        label = _make_label_record()
        result = runtime.observe_label_record(
            label_record=label, adaptive=adaptive,
        )
        assert result is None
        assert runtime.sample_count == 0
        assert (
            repo.count_events(
                event_type=EventType.STRATEGY_VALIDATION_SAMPLE_CREATED
            )
            == 0
        )
    finally:
        dbs.close()


def test_max_samples_capacity_bounded(tmp_path: Path):
    """Capacity guard prevents unbounded sample buffers."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = StrategyValidationRuntime(
            event_repo=repo,
            config=StrategyValidationRuntimeConfig(max_samples=2),
        )
        for opp in ("o1", "o2", "o3"):
            adaptive = _make_adaptive_context(opportunity_id=opp, symbol=opp)
            label = _make_label_record(opportunity_id=opp, symbol=opp)
            runtime.observe_label_record(
                label_record=label, adaptive=adaptive,
            )
        assert runtime.sample_count == 2
    finally:
        dbs.close()
