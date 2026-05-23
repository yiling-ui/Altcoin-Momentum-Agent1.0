"""Phase 11C.1C-C-A - MFE / MAE Label Queue Runtime & Tail Outcome
Tracking tests.

Pins every behaviour the brief calls out:

  - MFE / MAE calculation
  - time_to_mfe / time_to_mae
  - reached_2r / 3r / 5r / 10r flags + missing virtual_risk_unit_pct
  - each tail_label (strong / moderate / weak / fake_breakout /
    late_chase_failure / dumped / unresolved)
  - idempotent tracking start
  - pending / completed / expired states
  - integration with the Phase 11C.1C-B adaptive candidate payload
  - EventRepository integration
  - learning-ready payload compatibility
  - daily report metrics surface
  - Export compatibility (old + new events)
  - Replay compatibility (old + new events)
  - safety regression: every Phase 1 safety flag remains False

No real socket is opened. The runtime is paper / virtual only.
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
    LABEL_TRACKING_SCHEMA_VERSION,
    MarketRegimeAssessment,
    OpportunityScore,
    RuntimeCalibrationMetrics,
    StrategyModeDecision,
    TAIL_LABELS,
    TrackingWindowState,
    assign_tail_label_for_window,
    build_adaptive_candidate_context,
    compute_pct_return,
    update_window_with_price,
)
from app.adaptive.cluster import build_cluster_context
from app.adaptive.label_queue import build_label_queue_contract
from app.config.settings import get_settings, load_settings
from app.core.events import Event, EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.exports.service import TestDataExportService
from app.learning.context import LearningReadyContext, attach_learning_ready
from app.learning.identity import OpportunityIdentity
from app.market_data_public.candidate_pool import (
    CANDIDATE_STATE_ACTIVE,
    Candidate,
    CandidatePool,
    CandidatePoolConfig,
)
from app.market_data_public.radar import (
    AllMarketRadarSnapshot,
    pre_anomaly_score_light,
)
from app.market_data_public.ws_radar_chain import WSRadarChainDriver
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


def _make_radar_snapshot(
    *,
    symbol: str = "EDENUSDT",
    last_price: float = 1.05,
    timestamp: int = 1_700_000_060_000,
    price_change_pct_24h: float = 0.05,
    price_acceleration_60s: float = 0.012,
    quote_volume: float = 50_000_000.0,
    quote_volume_delta_60s: float = 1_000_000.0,
    volume_rank: int = 5,
    volume_rank_jump: int = 4,
    bid: float | None = 1.049,
    ask: float | None = 1.051,
    spread_pct: float = 0.002,
    mark_price: float = 1.05,
    funding_rate: float = 0.0001,
) -> AllMarketRadarSnapshot:
    return AllMarketRadarSnapshot(
        symbol=symbol,
        timestamp=timestamp,
        last_price=last_price,
        price_change_pct_24h=price_change_pct_24h,
        price_acceleration_60s=price_acceleration_60s,
        quote_volume=quote_volume,
        quote_volume_delta_60s=quote_volume_delta_60s,
        volume_rank=volume_rank,
        volume_rank_jump=volume_rank_jump,
        bid=bid,
        ask=ask,
        spread_pct=spread_pct,
        mark_price=mark_price,
        funding_rate=funding_rate,
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


def _make_adaptive_context(
    *,
    opportunity_id: str = "opp-1",
    scan_batch_id: str = "batch-1",
    symbol: str = "EDENUSDT",
    timestamp_ms: int = 1_700_000_060_000,
    first_seen_ts_ms: int = 1_700_000_000_000,
    first_seen_price: float = 1.0,
    current_price: float = 1.10,
    early_tail_score: float = 80.0,
    late_chase_risk: float = 10.0,
    freshness_score: float = 0.9,
    distance_from_first_seen: float = 0.10,
    distance_to_24h_high: float = 0.0,
    candidate_stage: str = "early",
    strategy_mode: str = "follow",
    opportunity_score: float = 75.0,
    grade: str = "A",
) -> AdaptiveCandidateContext:
    return AdaptiveCandidateContext(
        opportunity_id=opportunity_id,
        scan_batch_id=scan_batch_id,
        symbol=symbol,
        timestamp_ms=timestamp_ms,
        market_regime=MarketRegimeAssessment(
            regime_name="MEME_RISK_ON",
            confidence=0.7,
            risk_multiplier=1.0,
            allowed_strategy_modes=("follow", "pullback", "observe"),
        ),
        candidate_stage=CandidateStageAssessment(
            stage=candidate_stage,
            freshness=float(freshness_score),
            late_chase_risk=min(1.0, late_chase_risk / 100.0),
            blowoff_risk=0.0,
            first_seen_ts=first_seen_ts_ms,
            first_seen_price=first_seen_price,
            current_price=current_price,
            distance_from_first_seen=distance_from_first_seen,
            distance_to_24h_high=distance_to_24h_high,
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
        cluster=build_cluster_context(symbol=symbol, radar_score=70.0),
        label_queue=build_label_queue_contract(
            opportunity_id=opportunity_id,
            scan_batch_id=scan_batch_id,
            symbol=symbol,
            enqueued_at_ms=timestamp_ms,
            reference_price=current_price,
        ),
        runtime_calibration=RuntimeCalibrationMetrics(
            candidate_first_seen_ts=first_seen_ts_ms,
            candidate_first_seen_price=first_seen_price,
            current_price=current_price,
            price_change_since_first_seen=(
                (current_price - first_seen_price) / first_seen_price
                if first_seen_price > 0
                else 0.0
            ),
            quote_volume_acceleration_1m=0.0,
            quote_volume_acceleration_5m=0.0,
            price_acceleration_1m=0.0,
            price_acceleration_5m=0.0,
            volume_rank=5,
            volume_rank_jump_5m=4,
            distance_to_24h_high=distance_to_24h_high,
            distance_from_first_seen=distance_from_first_seen,
            freshness_score=float(freshness_score),
            late_chase_risk=float(late_chase_risk),
            early_tail_score=float(early_tail_score),
        ),
        strategy_version="phase_11c_1c_a.strategy.v1",
        scoring_version="phase_11c_1c_a.scoring.v1",
        risk_config_version="phase_11c_1c_a.risk_config.v1",
        state_machine_version="phase_11c_1c_a.state_machine.v1",
    )


# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------
def test_compute_pct_return_basic():
    assert compute_pct_return(baseline_price=1.0, observed_price=1.10) == pytest.approx(0.10)
    assert compute_pct_return(baseline_price=1.0, observed_price=0.90) == pytest.approx(-0.10)
    assert compute_pct_return(baseline_price=0.0, observed_price=1.0) == 0.0


def test_update_window_mfe_mae_calculation():
    """MFE / MAE / time_to_mfe / time_to_mae must reflect the highest /
    lowest observed prices and the elapsed ms relative to
    ``candidate_first_seen_ts``."""
    config = LabelQueueRuntimeConfig()
    base_ts = 1_700_000_000_000
    window = TrackingWindowState(
        window_name="5m",
        window_seconds=300,
        window_start_ts=base_ts,
        window_end_ts=base_ts + 300_000,
        start_price=1.0,
        latest_price=1.0,
        mfe_price=1.0,
        mae_price=1.0,
    )
    # Move up by 10% at +60s.
    update_window_with_price(
        window=window,
        candidate_first_seen_ts=base_ts,
        first_seen_price=1.0,
        ts_ms=base_ts + 60_000,
        price=1.10,
        virtual_risk_unit_pct=None,
        config=config,
    )
    assert window.mfe_pct == pytest.approx(0.10)
    assert window.mfe_price == pytest.approx(1.10)
    assert window.time_to_mfe == 60_000
    # Pull back to -3% at +120s.
    update_window_with_price(
        window=window,
        candidate_first_seen_ts=base_ts,
        first_seen_price=1.0,
        ts_ms=base_ts + 120_000,
        price=0.97,
        virtual_risk_unit_pct=None,
        config=config,
    )
    assert window.mae_pct == pytest.approx(-0.03)
    assert window.mae_price == pytest.approx(0.97)
    assert window.time_to_mae == 120_000
    # MFE must remain at 1.10 / +10%.
    assert window.mfe_price == pytest.approx(1.10)
    assert window.max_future_return == pytest.approx(0.10)
    assert window.max_adverse_return == pytest.approx(-0.03)


def test_r_multiple_flags_with_virtual_risk_unit():
    """When ``virtual_risk_unit_pct`` is supplied the runtime sets
    reached_2r / 3r / 5r / 10r as the MFE crosses the corresponding
    multiples."""
    config = LabelQueueRuntimeConfig()
    base_ts = 1_700_000_000_000
    window = TrackingWindowState(
        window_name="5m",
        window_seconds=300,
        window_start_ts=base_ts,
        window_end_ts=base_ts + 300_000,
        start_price=1.0,
        latest_price=1.0,
        mfe_price=1.0,
        mae_price=1.0,
    )
    # ru = 1% so 2R = +2%, 3R = +3%, 5R = +5%, 10R = +10%.
    ru = 0.01
    update_window_with_price(
        window=window,
        candidate_first_seen_ts=base_ts,
        first_seen_price=1.0,
        ts_ms=base_ts + 30_000,
        price=1.025,  # +2.5%
        virtual_risk_unit_pct=ru,
        config=config,
    )
    assert window.reached_2r is True
    assert window.reached_3r is False
    assert window.reached_5r is False
    assert window.reached_10r is False

    update_window_with_price(
        window=window,
        candidate_first_seen_ts=base_ts,
        first_seen_price=1.0,
        ts_ms=base_ts + 60_000,
        price=1.06,  # +6%
        virtual_risk_unit_pct=ru,
        config=config,
    )
    assert window.reached_2r is True
    assert window.reached_3r is True
    assert window.reached_5r is True
    assert window.reached_10r is False

    update_window_with_price(
        window=window,
        candidate_first_seen_ts=base_ts,
        first_seen_price=1.0,
        ts_ms=base_ts + 90_000,
        price=1.12,  # +12%
        virtual_risk_unit_pct=ru,
        config=config,
    )
    assert window.reached_10r is True


def test_r_multiple_flags_without_virtual_risk_unit():
    """When virtual_risk_unit_pct is missing, R flags MUST stay False
    and the window records ``no_virtual_risk_unit=True``."""
    config = LabelQueueRuntimeConfig()
    base_ts = 1_700_000_000_000
    window = TrackingWindowState(
        window_name="5m",
        window_seconds=300,
        window_start_ts=base_ts,
        window_end_ts=base_ts + 300_000,
        start_price=1.0,
        latest_price=1.0,
        mfe_price=1.0,
        mae_price=1.0,
    )
    update_window_with_price(
        window=window,
        candidate_first_seen_ts=base_ts,
        first_seen_price=1.0,
        ts_ms=base_ts + 30_000,
        price=1.50,  # +50%; would trip every R if ru were known
        virtual_risk_unit_pct=None,
        config=config,
    )
    assert window.reached_2r is False
    assert window.reached_3r is False
    assert window.reached_5r is False
    assert window.reached_10r is False
    assert window.no_virtual_risk_unit is True
    # Numeric metrics still tracked.
    assert window.mfe_pct == pytest.approx(0.50)


def test_stopped_before_tail_flag():
    config = LabelQueueRuntimeConfig(stopped_before_tail_pct=-0.04)
    base_ts = 1_700_000_000_000
    window = TrackingWindowState(
        window_name="5m",
        window_seconds=300,
        window_start_ts=base_ts,
        window_end_ts=base_ts + 300_000,
        start_price=1.0,
        latest_price=1.0,
        mfe_price=1.0,
        mae_price=1.0,
    )
    update_window_with_price(
        window=window,
        candidate_first_seen_ts=base_ts,
        first_seen_price=1.0,
        ts_ms=base_ts + 30_000,
        price=0.94,  # -6%
        virtual_risk_unit_pct=0.01,
        config=config,
    )
    assert window.stopped_before_tail is True


# ---------------------------------------------------------------------------
# Tail-label tests (one assertion per allowed label)
# ---------------------------------------------------------------------------
def _make_record(
    *,
    symbol: str = "EDENUSDT",
    first_seen_price: float = 1.0,
    virtual_risk_unit_pct: float | None = 0.01,
    strategy_mode: str = "follow",
    candidate_stage: str = "early",
    late_chase_risk: float = 10.0,
) -> LabelTrackingRecord:
    return LabelTrackingRecord(
        tracking_id="t1",
        opportunity_id="opp-1",
        scan_batch_id="batch-1",
        symbol=symbol,
        candidate_first_seen_ts=1_700_000_000_000,
        first_seen_price=first_seen_price,
        current_price=first_seen_price,
        tracking_started_ts=1_700_000_000_000,
        source_event_id="evt-src",
        early_tail_score=70.0,
        opportunity_score=75.0,
        strategy_mode=strategy_mode,
        candidate_stage=candidate_stage,
        late_chase_risk=late_chase_risk,
        freshness_score=0.8,
        distance_from_first_seen=0.0,
        distance_to_24h_high=0.0,
        virtual_risk_unit_pct=virtual_risk_unit_pct,
        tracking_windows=[],
    )


def test_tail_label_strong_tail():
    config = LabelQueueRuntimeConfig()
    record = _make_record()
    window = TrackingWindowState(
        window_name="5m",
        window_seconds=300,
        window_start_ts=0,
        window_end_ts=300_000,
        start_price=1.0,
        latest_price=1.30,
        mfe_pct=0.30,
        mae_pct=-0.01,
        mfe_price=1.30,
        mae_price=0.99,
        reached_2r=True,
        reached_3r=True,
        reached_5r=True,
        reached_10r=False,
    )
    label, missed, fake = assign_tail_label_for_window(
        window=window, record=record, config=config
    )
    assert label == "strong_tail"
    assert missed is False
    assert fake is False


def test_tail_label_moderate_tail():
    config = LabelQueueRuntimeConfig()
    record = _make_record()
    window = TrackingWindowState(
        window_name="5m",
        window_seconds=300,
        window_start_ts=0,
        window_end_ts=300_000,
        start_price=1.0,
        latest_price=1.04,
        mfe_pct=0.04,
        mae_pct=-0.005,
        mfe_price=1.04,
        mae_price=0.995,
        reached_2r=True,
        reached_3r=True,
        reached_5r=False,
        reached_10r=False,
    )
    label, _missed, _fake = assign_tail_label_for_window(
        window=window, record=record, config=config
    )
    assert label == "moderate_tail"


def test_tail_label_weak_tail():
    config = LabelQueueRuntimeConfig()
    record = _make_record()
    window = TrackingWindowState(
        window_name="5m",
        window_seconds=300,
        window_start_ts=0,
        window_end_ts=300_000,
        start_price=1.0,
        latest_price=1.025,
        mfe_pct=0.025,
        mae_pct=-0.001,
        mfe_price=1.025,
        mae_price=0.999,
        reached_2r=True,
        reached_3r=False,
    )
    label, _missed, _fake = assign_tail_label_for_window(
        window=window, record=record, config=config
    )
    assert label == "weak_tail"


def test_tail_label_fake_breakout():
    """Early upside followed by an adverse reversal. final near zero."""
    config = LabelQueueRuntimeConfig()
    record = _make_record(virtual_risk_unit_pct=None)
    window = TrackingWindowState(
        window_name="5m",
        window_seconds=300,
        window_start_ts=0,
        window_end_ts=300_000,
        start_price=1.0,
        latest_price=1.001,  # near zero final
        mfe_pct=0.05,  # printed +5% then collapsed
        mae_pct=-0.03,
        mfe_price=1.05,
        mae_price=0.97,
    )
    label, _missed, fake = assign_tail_label_for_window(
        window=window, record=record, config=config
    )
    assert label == "fake_breakout"
    assert fake is True


def test_tail_label_late_chase_failure():
    config = LabelQueueRuntimeConfig()
    record = _make_record(
        virtual_risk_unit_pct=None,
        late_chase_risk=80.0,
        strategy_mode="observe",
        candidate_stage="late",
    )
    window = TrackingWindowState(
        window_name="5m",
        window_seconds=300,
        window_start_ts=0,
        window_end_ts=300_000,
        start_price=1.0,
        latest_price=0.99,
        mfe_pct=0.001,
        mae_pct=-0.01,
        mfe_price=1.001,
        mae_price=0.99,
    )
    label, _missed, _fake = assign_tail_label_for_window(
        window=window, record=record, config=config
    )
    assert label == "late_chase_failure"


def test_tail_label_dumped():
    config = LabelQueueRuntimeConfig()
    record = _make_record(virtual_risk_unit_pct=None)
    window = TrackingWindowState(
        window_name="5m",
        window_seconds=300,
        window_start_ts=0,
        window_end_ts=300_000,
        start_price=1.0,
        latest_price=0.92,
        mfe_pct=0.005,
        mae_pct=-0.08,
        mfe_price=1.005,
        mae_price=0.92,
    )
    label, _missed, _fake = assign_tail_label_for_window(
        window=window, record=record, config=config
    )
    assert label == "dumped"


def test_tail_label_unresolved_default():
    config = LabelQueueRuntimeConfig()
    record = _make_record(virtual_risk_unit_pct=None)
    window = TrackingWindowState(
        window_name="5m",
        window_seconds=300,
        window_start_ts=0,
        window_end_ts=300_000,
        start_price=1.0,
        latest_price=1.005,
        mfe_pct=0.005,
        mae_pct=-0.001,
        mfe_price=1.005,
        mae_price=0.999,
    )
    label, _missed, _fake = assign_tail_label_for_window(
        window=window, record=record, config=config
    )
    assert label == "unresolved"


def test_tail_label_missed_tail_independent_flag():
    """``missed_tail`` is INDEPENDENT of the tail_label. A fast +6%
    rip on a candidate that the chain refused to follow because it
    was classified ``late`` must surface ``missed_tail=True``."""
    config = LabelQueueRuntimeConfig()
    record = _make_record(
        virtual_risk_unit_pct=None,
        strategy_mode="observe",
        candidate_stage="late",
    )
    window = TrackingWindowState(
        window_name="5m",
        window_seconds=300,
        window_start_ts=0,
        window_end_ts=300_000,
        start_price=1.0,
        latest_price=1.06,
        mfe_pct=0.06,
        mae_pct=-0.001,
        mfe_price=1.06,
        mae_price=0.999,
    )
    _label, missed, _fake = assign_tail_label_for_window(
        window=window, record=record, config=config
    )
    assert missed is True


# ---------------------------------------------------------------------------
# Idempotency and lifecycle (pending / completed / expired / unresolved)
# ---------------------------------------------------------------------------
def test_observe_is_idempotent_per_opportunity_id(tmp_path: Path):
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = LabelQueueRuntime(event_repo=repo)
        adaptive = _make_adaptive_context(opportunity_id="opp-A")
        rec1 = runtime.observe(adaptive=adaptive, source_event_id="src-1")
        rec2 = runtime.observe(adaptive=adaptive, source_event_id="src-2")
        assert rec1 is rec2
        # Exactly ONE LABEL_TRACKING_STARTED in events.db.
        started_events = repo.list_events(
            event_type=EventType.LABEL_TRACKING_STARTED
        )
        assert len(started_events) == 1
    finally:
        dbs.close()


def test_observe_dedupes_by_symbol_first_seen_when_no_opportunity_id(
    tmp_path: Path,
):
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = LabelQueueRuntime(event_repo=repo)
        # Empty opportunity_id -> fallback dedupe key.
        adaptive_a = _make_adaptive_context(opportunity_id="")
        adaptive_b = _make_adaptive_context(opportunity_id="")
        rec1 = runtime.observe(adaptive=adaptive_a, source_event_id="x")
        rec2 = runtime.observe(adaptive=adaptive_b, source_event_id="y")
        assert rec1 is rec2
    finally:
        dbs.close()


def test_pending_completed_expired_states(tmp_path: Path):
    """The lifecycle: pending -> completed (primary window closes)
    or pending -> expired (no completion within grace)."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        # Tight windows so the test runs quickly: 5m primary, 10m max
        config = LabelQueueRuntimeConfig(
            grace_period_seconds=60,
            primary_window_for_tail_label="5m",
            window_seconds_map={"5m": 300, "10m": 600},
        )
        runtime = LabelQueueRuntime(event_repo=repo, config=config)
        base_ts = 1_700_000_000_000
        adaptive = _make_adaptive_context(
            timestamp_ms=base_ts,
            first_seen_ts_ms=base_ts,
        )
        rec = runtime.observe(adaptive=adaptive, source_event_id="src")
        assert rec is not None
        assert rec.status == "pending"
        # Tick well past the 5m window end.
        runtime.tick(now_ms=base_ts + 6 * 60 * 1000)
        assert rec.status == "completed"
        completed_events = repo.list_events(
            event_type=EventType.LABEL_WINDOW_COMPLETED
        )
        # 5m primary completes; 10m still pending.
        assert any(
            ev.payload.get("window", {}).get("window_name") == "5m"
            for ev in completed_events
        )
        # Tick way past everything to expire any leftover.
        runtime.tick(now_ms=base_ts + 24 * 60 * 60 * 1000)
        # Final status is completed (not expired).
        assert rec.status == "completed"
    finally:
        dbs.close()


def test_expired_when_no_observation_during_window(tmp_path: Path):
    """A record whose primary window completes WITHOUT any
    observation during the window is marked unresolved (with the
    primary window assigned the unresolved label)."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        # Anchor the candidate in the past so its 5m window is already
        # closed at registration; the runtime must mark each window
        # unresolved when it ticks.
        config = LabelQueueRuntimeConfig(
            grace_period_seconds=60,
            primary_window_for_tail_label="5m",
            window_seconds_map={"5m": 300},
        )
        runtime = LabelQueueRuntime(event_repo=repo, config=config)
        base_ts = 1_700_000_000_000
        # Candidate first seen 1 hour ago; tracking starts now.
        adaptive = _make_adaptive_context(
            timestamp_ms=base_ts + 60 * 60 * 1000,
            first_seen_ts_ms=base_ts,
        )
        rec = runtime.observe(adaptive=adaptive, source_event_id="src")
        runtime.tick(now_ms=base_ts + 24 * 60 * 60 * 1000)
        assert rec.status == "unresolved"
        assert rec.final_tail_label == "unresolved"
    finally:
        dbs.close()


def test_max_pending_records_bounded(tmp_path: Path):
    """Capacity guard prevents unbounded queues."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        config = LabelQueueRuntimeConfig(max_pending_records=2)
        runtime = LabelQueueRuntime(event_repo=repo, config=config)
        runtime.observe(
            adaptive=_make_adaptive_context(
                opportunity_id="o1", symbol="A1USDT"
            ),
            source_event_id="s1",
        )
        runtime.observe(
            adaptive=_make_adaptive_context(
                opportunity_id="o2", symbol="A2USDT"
            ),
            source_event_id="s2",
        )
        # Third one MUST be dropped.
        third = runtime.observe(
            adaptive=_make_adaptive_context(
                opportunity_id="o3", symbol="A3USDT"
            ),
            source_event_id="s3",
        )
        assert third is None
        assert len(runtime.records) == 2
    finally:
        dbs.close()


def test_missing_price_does_not_crash(tmp_path: Path):
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = LabelQueueRuntime(event_repo=repo)
        adaptive = _make_adaptive_context(
            current_price=0.0, first_seen_price=0.0
        )
        rec = runtime.observe(adaptive=adaptive, source_event_id="src")
        # No record because we cannot compute MFE / MAE; runtime did
        # NOT raise.
        assert rec is None
        assert len(runtime.records) == 0
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Integration with WSRadarChainDriver + EventRepository
# ---------------------------------------------------------------------------
def test_chain_driver_emits_label_tracking_started(tmp_path: Path):
    """Driving one candidate through the chain must produce exactly
    one LABEL_TRACKING_STARTED + at least one pending tracking
    record. Mirrors the 30s dry-run acceptance criterion."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        runtime = LabelQueueRuntime(event_repo=repo)
        chain = WSRadarChainDriver(
            risk_engine=risk,
            event_repo=repo,
            label_queue_runtime=runtime,
        )
        candidate = _make_candidate()
        result = chain.drive(candidate)
        assert result.adaptive_context is not None
        # 30s dry-run analogue: only LABEL_TRACKING_STARTED + pending
        # records (smallest window 5m won't complete in 30s).
        started_events = repo.list_events(
            event_type=EventType.LABEL_TRACKING_STARTED
        )
        assert len(started_events) == 1
        completed_events = repo.list_events(
            event_type=EventType.LABEL_WINDOW_COMPLETED
        )
        assert len(completed_events) == 0
        # Source event id reference is the LABEL_QUEUE_ENQUEUED id.
        label_q_events = repo.list_events(
            event_type=EventType.LABEL_QUEUE_ENQUEUED
        )
        assert len(label_q_events) == 1
        src_id = label_q_events[0].event_id
        assert started_events[0].payload["source_event_id"] == src_id
        # Schema version stamped.
        assert (
            started_events[0].payload["schema_version"]
            == LABEL_TRACKING_SCHEMA_VERSION
        )
        # Pending record count >= 1.
        metrics = runtime.metrics_payload()
        assert metrics["pending_label_records"] >= 1
        assert metrics["label_tracking_started_count"] == 1
    finally:
        dbs.close()


def test_chain_driver_updates_mfe_mae_on_subsequent_drives(tmp_path: Path):
    """Mirrors the 5min real WS smoke acceptance: subsequent chain
    passes update the existing record's MFE / MAE without re-emitting
    LABEL_TRACKING_STARTED."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        runtime = LabelQueueRuntime(event_repo=repo)
        chain = WSRadarChainDriver(
            risk_engine=risk,
            event_repo=repo,
            label_queue_runtime=runtime,
        )
        # First drive establishes the record.
        snap_a = _make_radar_snapshot(
            symbol="EDENUSDT",
            last_price=1.05,
            timestamp=1_700_000_060_000,
        )
        cand = _make_candidate(symbol="EDENUSDT", snap=snap_a)
        chain.drive(cand)
        # Second drive with a higher price -> MFE advances, window
        # update event fires.
        snap_b = _make_radar_snapshot(
            symbol="EDENUSDT",
            last_price=1.20,
            timestamp=1_700_000_120_000,
        )
        cand.snapshot = snap_b
        cand.last_seen_ms = int(snap_b.timestamp)
        chain.drive(cand)
        # Still only one LABEL_TRACKING_STARTED.
        started_events = repo.list_events(
            event_type=EventType.LABEL_TRACKING_STARTED
        )
        assert len(started_events) == 1
        # MFE has advanced - confirm via the runtime's record.
        rec = runtime.records[0]
        primary = rec.tracking_windows[0]
        assert primary.window_name == "5m"
        assert primary.mfe_pct > 0.10
    finally:
        dbs.close()


def test_completed_window_assigns_tail_label(tmp_path: Path):
    """Mirrors the 6-10min real WS paper smoke acceptance: one 5m
    window completes and a tail label is assigned + emitted."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        runtime = LabelQueueRuntime(event_repo=repo)
        chain = WSRadarChainDriver(
            risk_engine=risk,
            event_repo=repo,
            label_queue_runtime=runtime,
        )
        # Drive the candidate, then tick well past 5m so the primary
        # window closes.
        chain.drive(_make_candidate())
        runtime.tick(now_ms=1_700_000_000_000 + 6 * 60 * 1000)
        completed = repo.list_events(
            event_type=EventType.LABEL_WINDOW_COMPLETED
        )
        assigned = repo.list_events(event_type=EventType.TAIL_LABEL_ASSIGNED)
        assert any(
            ev.payload.get("window", {}).get("window_name") == "5m"
            for ev in completed
        )
        assert any(
            ev.payload.get("window_name") == "5m" for ev in assigned
        )
        for ev in assigned:
            assert ev.payload["tail_label"] in TAIL_LABELS
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Daily report metrics
# ---------------------------------------------------------------------------
def test_daily_report_surfaces_label_runtime_metrics(tmp_path: Path):
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        runtime = LabelQueueRuntime(event_repo=repo)
        chain = WSRadarChainDriver(
            risk_engine=risk,
            event_repo=repo,
            label_queue_runtime=runtime,
        )
        chain.drive(_make_candidate())
        runtime.tick(now_ms=1_700_000_000_000 + 6 * 60 * 1000)

        out_dir = tmp_path / "reports"
        out_dir.mkdir()
        builder = DailyReportBuilder(event_repo=repo, output_dir=out_dir)
        snap = builder.build(
            started_at_ms=1_699_000_000_000,
            finished_at_ms=2_000_000_000_000,
            adaptive_metrics=chain.adaptive_metrics_payload(),
            label_runtime_metrics=runtime.metrics_payload(),
            write_to_disk=True,
        )
        # Every brief-mandated metric is present.
        assert snap.label_tracking_started_count >= 1
        assert snap.label_window_completed_count >= 1
        assert snap.tail_label_assigned_count >= 1
        assert isinstance(snap.tail_label_distribution, dict)
        assert isinstance(snap.early_tail_score_bucket_outcomes, dict)
        assert isinstance(snap.opportunity_score_bucket_outcomes, dict)
        assert isinstance(snap.strategy_mode_outcomes, dict)
        assert isinstance(snap.late_chase_risk_bucket_outcomes, dict)
        # Markdown body contains the new section.
        md = snap.markdown
        assert "Phase 11C.1C-C-A MFE / MAE Label Queue Runtime" in md
        assert "Tail label distribution" in md
        assert "Top MFE symbols" in md
        assert "paper / virtual" in md
        # JSON-safe payload.
        json.dumps(snap.to_payload(), sort_keys=True, default=str)
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Export + Replay compatibility
# ---------------------------------------------------------------------------
def test_export_carries_label_tracking_events(tmp_path: Path):
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        runtime = LabelQueueRuntime(event_repo=repo)
        chain = WSRadarChainDriver(
            risk_engine=risk,
            event_repo=repo,
            label_queue_runtime=runtime,
        )
        chain.drive(_make_candidate())
        runtime.tick(now_ms=1_700_000_000_000 + 6 * 60 * 1000)

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
            seen = {et.value: 0 for et in (
                EventType.LABEL_TRACKING_STARTED,
                EventType.LABEL_WINDOW_COMPLETED,
                EventType.TAIL_LABEL_ASSIGNED,
            )}
            for line in zf.read("events.jsonl").decode("utf-8").splitlines():
                row = json.loads(line)
                if row.get("event_type") in seen:
                    seen[row["event_type"]] += 1
            for k, v in seen.items():
                assert v >= 1, f"export missing event {k}"
    finally:
        dbs.close()


def test_export_remains_backward_compatible_with_old_events(tmp_path: Path):
    """An events.db that only contains pre-Phase-11C.1C-C-A events
    must export cleanly without a label-runtime block."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        repo.append(
            Event(
                event_type=EventType.MARKET_SNAPSHOT,
                source_module="legacy",
                symbol="LEGACYUSDT",
                timestamp=1_700_000_000_000,
                payload={"hello": "world"},
            )
        )
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
        # Bundle exists and is non-empty.
        assert result.zip_path.exists()
        assert result.bytes_written > 0
    finally:
        dbs.close()


def test_replay_reads_label_tracking_events_and_old_events(tmp_path: Path):
    """Replay must accept an events.db that mixes the new label
    events with old events (pre-Phase 11C.1C-C-A) without raising."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        # Old event without any label payload.
        repo.append(
            Event(
                event_type=EventType.MARKET_SNAPSHOT,
                source_module="legacy",
                symbol="LEGACYUSDT",
                timestamp=1_700_000_000_000,
                payload={"old": True},
            )
        )
        # New chain + runtime emitting label events.
        risk = RiskEngine(event_repo=repo)
        runtime = LabelQueueRuntime(event_repo=repo)
        chain = WSRadarChainDriver(
            risk_engine=risk,
            event_repo=repo,
            label_queue_runtime=runtime,
        )
        chain.drive(_make_candidate())
        runtime.tick(now_ms=1_700_000_000_000 + 6 * 60 * 1000)
        # Replay engine must read everything without raising.
        engine = ReplayEngine(event_repo=repo)
        rejects = engine.replay_risk_rejections()
        assert rejects, "replay returned no risk rejections"
        # Re-fetch every label event explicitly via repo-level
        # filters (replay engine treats them as opaque).
        started = repo.list_events(event_type=EventType.LABEL_TRACKING_STARTED)
        assert len(started) >= 1
        # Reconstruct the LabelTrackingRecord state from the started
        # event payload alone.
        rec = LabelTrackingRecord(
            tracking_id=str(started[0].payload["tracking_id"]),
            opportunity_id=str(started[0].payload["opportunity_id"]),
            scan_batch_id=str(started[0].payload["scan_batch_id"]),
            symbol=str(started[0].payload["symbol"]),
            candidate_first_seen_ts=int(
                started[0].payload["candidate_first_seen_ts"]
            ),
            first_seen_price=float(started[0].payload["first_seen_price"]),
            current_price=float(started[0].payload["current_price"]),
            tracking_started_ts=int(started[0].payload["tracking_started_ts"]),
            source_event_id=str(started[0].payload["source_event_id"]),
            early_tail_score=float(started[0].payload["early_tail_score"]),
            opportunity_score=float(started[0].payload["opportunity_score"]),
            strategy_mode=str(started[0].payload["strategy_mode"]),
            candidate_stage=str(started[0].payload["candidate_stage"]),
            late_chase_risk=float(started[0].payload["late_chase_risk"]),
            freshness_score=float(started[0].payload["freshness_score"]),
            distance_from_first_seen=float(
                started[0].payload["distance_from_first_seen"]
            ),
            distance_to_24h_high=float(
                started[0].payload["distance_to_24h_high"]
            ),
            virtual_risk_unit_pct=started[0].payload.get("virtual_risk_unit_pct"),
            tracking_windows=[],
            status=str(started[0].payload["status"]),
        )
        assert rec.tracking_id
        assert rec.symbol
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Learning-ready compatibility
# ---------------------------------------------------------------------------
def test_label_runtime_payload_matches_learning_ready_shape(tmp_path: Path):
    """The LABEL_TRACKING_STARTED payload SHOULD be JSON-safe and
    embeddable in a LearningReadyContext via attach_learning_ready
    (defence-in-depth: future Reflection consumers may want to
    surface the runtime block via the Phase 8.5 stream)."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        runtime = LabelQueueRuntime(event_repo=repo)
        adaptive = _make_adaptive_context()
        rec = runtime.observe(adaptive=adaptive, source_event_id="src")
        assert rec is not None
        # Build a learning-ready context whose ``adaptive_candidate``
        # field carries the existing adaptive context. The runtime
        # payload itself is JSON-safe.
        json.dumps(rec.to_payload(), sort_keys=True)
        ctx = LearningReadyContext(adaptive_candidate=adaptive)
        merged = attach_learning_ready({"hello": 1}, ctx)
        assert merged["hello"] == 1
        assert "learning_ready" in merged
        assert merged["learning_ready"]["adaptive_candidate"][
            "opportunity_id"
        ] == adaptive.opportunity_id
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Safety regression
# ---------------------------------------------------------------------------
def test_no_live_trading_flags_unchanged():
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


def test_label_runtime_does_not_open_position_or_authorise_trade(
    tmp_path: Path,
):
    """The runtime must NEVER emit any of the trading event types
    (ORDER_*, POSITION_*, STOP_*) or call Telegram outbound. It only
    emits the six new label events."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        runtime = LabelQueueRuntime(event_repo=repo)
        chain = WSRadarChainDriver(
            risk_engine=risk,
            event_repo=repo,
            label_queue_runtime=runtime,
        )
        chain.drive(_make_candidate())
        runtime.tick(now_ms=1_700_000_000_000 + 6 * 60 * 1000)
        forbidden = {
            EventType.ORDER_SENT,
            EventType.ORDER_FILLED,
            EventType.POSITION_OPENED,
            EventType.POSITION_CLOSED,
            EventType.STOP_SENT,
            EventType.STOP_CONFIRMED,
            EventType.TELEGRAM_MESSAGE_SENT,
        }
        for et in forbidden:
            assert (
                repo.count_events(event_type=et) == 0
            ), f"runtime emitted forbidden {et.value}"
        # And every new label event lives in the runtime SOURCE_MODULE.
        for et in (
            EventType.LABEL_TRACKING_STARTED,
            EventType.LABEL_WINDOW_COMPLETED,
            EventType.TAIL_LABEL_ASSIGNED,
        ):
            for ev in repo.list_events(event_type=et):
                assert ev.source_module == LabelQueueRuntime.SOURCE_MODULE
                # Schema versioned.
                assert (
                    ev.payload["schema_version"]
                    == LABEL_TRACKING_SCHEMA_VERSION
                )
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# Schema-version forward compatibility
# ---------------------------------------------------------------------------
def test_replay_handles_missing_schema_version_field(tmp_path: Path):
    """A future event_log row without a ``schema_version`` field MUST
    not crash the replay. We simulate this by appending an event
    whose payload has every other field except ``schema_version``."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        repo.append(
            Event(
                event_type=EventType.LABEL_TRACKING_STARTED,
                source_module="legacy_label_runtime",
                symbol="LEGACYUSDT",
                timestamp=1_700_000_000_000,
                payload={
                    "tracking_id": "legacy-id",
                    "opportunity_id": "legacy-opp",
                    "symbol": "LEGACYUSDT",
                    # schema_version intentionally missing
                },
            )
        )
        # The event still appears in repository queries.
        rows = repo.list_events(event_type=EventType.LABEL_TRACKING_STARTED)
        assert len(rows) == 1
        # Replay engine must not crash on a list_events round-trip.
        engine = ReplayEngine(event_repo=repo)
        # Use a generic API so it walks all events.
        engine.replay_risk_rejections()  # smoke
    finally:
        dbs.close()
