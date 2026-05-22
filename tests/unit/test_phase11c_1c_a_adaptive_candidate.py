"""Phase 11C.1C-A - Adaptive Candidate Regime & Strategy Selector tests.

Pins every behaviour the brief calls out:

  - test_market_regime_assessment_contract
  - test_candidate_stage_classifier_early
  - test_candidate_stage_classifier_late
  - test_candidate_stage_classifier_blowoff
  - test_candidate_stage_classifier_dumped
  - test_opportunity_score_formula
  - test_opportunity_grade_boundaries
  - test_strategy_selector_follow
  - test_strategy_selector_pullback
  - test_strategy_selector_observe_for_late
  - test_strategy_selector_observe_for_blowoff
  - test_strategy_selector_reject_for_high_manipulation
  - test_strategy_selector_reject_for_no_trade_regime
  - test_cluster_context_groups_by_quote_asset
  - test_label_queue_contract_created
  - test_adaptive_candidate_context_payload_round_trips
  - test_adaptive_context_attached_to_learning_ready_payload
  - test_ws_radar_chain_emits_six_adaptive_events
  - test_virtual_trade_plan_contains_adaptive_fields
  - test_daily_report_contains_adaptive_candidate_metrics
  - test_export_replay_reads_adaptive_candidate_events
  - test_no_live_trading_flags_unchanged
  - test_no_real_telegram_outbound_flag_unchanged
  - test_no_binance_api_key_consumed
  - test_phase_12_remains_forbidden
  - test_strategy_mode_does_not_authorise_real_trade

Every test runs in-process. No real socket is opened; the
deterministic in-process pump stands in for the public WebSocket
transport when needed.
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

import pytest

from app.adaptive import (
    ADAPTIVE_LEARNING_READY_KEY,
    AdaptiveCandidateContext,
    AdaptiveScoringVersion,
    AdaptiveStateMachineVersion,
    AdaptiveStrategyVersion,
    CANDIDATE_STAGES,
    CandidateStageAssessment,
    ClusterContext,
    DEFAULT_OPPORTUNITY_SCORE_WEIGHTS,
    DEFAULT_TRACKING_WINDOWS,
    LabelQueueContract,
    MarketRegimeAssessment,
    OPPORTUNITY_GRADES,
    OPPORTUNITY_GRADE_BOUNDARIES,
    OpportunityScore,
    OpportunityScoreInputs,
    REGIME_BUCKETS,
    STRATEGY_MODES,
    StrategyModeDecision,
    assess_market_regime,
    build_adaptive_candidate_context,
    build_cluster_context,
    build_label_queue_contract,
    classify_candidate_stage,
    compute_opportunity_score,
    grade_for_score,
    select_strategy_mode,
)
from app.config.settings import get_settings, load_settings
from app.core.events import EventType
from app.database.connection import DatabaseSet, PHASE2_DATABASES
from app.database.migrations import migrate_database_set
from app.database.repositories import EventRepository
from app.exchanges.base import WRITE_SURFACE_METHODS
from app.exchanges.binance_public import BinancePublicClient
from app.core.errors import SafeModeViolation
from app.exports.service import TestDataExportService
from app.learning import (
    ADAPTIVE_LEARNING_READY_EVENT_TYPES,
    LEARNING_READY_EVENT_TYPES,
    LEARNING_READY_KEY,
    LearningReadyContext,
    OpportunityIdentity,
    VirtualTradePlan,
    attach_learning_ready,
    payload_to_virtual_trade_plan,
    virtual_trade_plan_to_payload,
)
from app.market_data_public.candidate_pool import (
    CANDIDATE_STATE_ACTIVE,
    Candidate,
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


def _make_event_repo(tmp_path: Path) -> tuple[EventRepository, DatabaseSet]:
    dbs = DatabaseSet.open(
        tmp_path / "sqlite",
        wal=False,
        databases=PHASE2_DATABASES,
    )
    migrate_database_set(dbs)
    return EventRepository(dbs.events, capital_conn=dbs.capital), dbs


def _settings():
    get_settings.cache_clear()
    return load_settings()


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
    liquidation_event: bool = False,
    liquidation_notional: float = 0.0,
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
        liquidation_event=liquidation_event,
        liquidation_notional=liquidation_notional,
    )


def _make_candidate(
    *,
    symbol: str = "EDENUSDT",
    snap: AllMarketRadarSnapshot | None = None,
    first_seen_ts: int = 1_700_000_000_000,
    radar_score: float | None = None,
) -> Candidate:
    snap = snap or _make_radar_snapshot(symbol=symbol)
    score = pre_anomaly_score_light(snap)
    radar_score = (
        float(radar_score) if radar_score is not None else float(score.radar_score)
    )
    identity = OpportunityIdentity.create(
        symbol=symbol,
        source_phase="phase_11c_1b_ws_first_radar",
        first_seen_ts=first_seen_ts,
    )
    return Candidate(
        symbol=symbol,
        state=CANDIDATE_STATE_ACTIVE,
        radar_score=radar_score,
        reason_tags=tuple(score.reason_tags),
        source_streams=tuple(score.source_streams),
        snapshot=snap,
        identity=identity,
        first_seen_ms=first_seen_ts,
        last_seen_ms=int(snap.timestamp),
    )


# ---------------------------------------------------------------------------
# 1. Data contracts
# ---------------------------------------------------------------------------


def test_market_regime_assessment_contract():
    """Every brief-mandated field is present, frozen, JSON-safe."""
    a = MarketRegimeAssessment(
        regime_name="MEME_RISK_ON",
        confidence=0.7,
        risk_multiplier=1.0,
        allowed_strategy_modes=("follow", "pullback", "observe"),
        no_trade_reason=(),
        notes=("broad_rally",),
    )
    assert a.regime_name == "MEME_RISK_ON"
    assert a.confidence == 0.7
    assert a.risk_multiplier == 1.0
    assert "follow" in a.allowed_strategy_modes
    payload = a.to_payload()
    for k in (
        "regime_name",
        "confidence",
        "risk_multiplier",
        "allowed_strategy_modes",
        "no_trade_reason",
        "notes",
    ):
        assert k in payload
    json.dumps(payload, sort_keys=True)
    # Frozen
    with pytest.raises((TypeError, ValueError)):
        a.regime_name = "ALT_RISK_OFF"  # type: ignore[misc]
    # Validators
    with pytest.raises(Exception):
        MarketRegimeAssessment(regime_name="BOGUS_REGIME")
    with pytest.raises(Exception):
        MarketRegimeAssessment(confidence=1.5)
    with pytest.raises(Exception):
        MarketRegimeAssessment(risk_multiplier=2.0)
    with pytest.raises(Exception):
        MarketRegimeAssessment(allowed_strategy_modes=("not_a_mode",))


def test_candidate_stage_assessment_contract_field_set():
    """Phase 11C.1C-A field set for the stage assessment."""
    a = CandidateStageAssessment(
        stage="early",
        freshness=0.95,
        late_chase_risk=0.05,
        blowoff_risk=0.0,
        first_seen_ts=1_700_000_000_000,
        first_seen_price=100.0,
        current_price=101.0,
        distance_from_first_seen=0.01,
        distance_to_24h_high=0.05,
        reason_tags=("near_first_seen_price",),
    )
    payload = a.to_payload()
    for k in (
        "stage",
        "freshness",
        "late_chase_risk",
        "blowoff_risk",
        "first_seen_ts",
        "first_seen_price",
        "current_price",
        "distance_from_first_seen",
        "distance_to_24h_high",
        "reason_tags",
    ):
        assert k in payload
    with pytest.raises(Exception):
        CandidateStageAssessment(stage="not_a_stage")
    with pytest.raises(Exception):
        CandidateStageAssessment(freshness=1.5)


def test_opportunity_score_contract_field_set():
    s = OpportunityScore(
        momentum_strength=80.0,
        volume_expansion=70.0,
        liquidity_quality=60.0,
        regime_fit=80.0,
        freshness=90.0,
        manipulation_risk=10.0,
        late_chase_risk=10.0,
        score=72.5,
        grade="A",
        reason_tags=("test",),
    )
    payload = s.to_payload()
    for k in (
        "momentum_strength",
        "volume_expansion",
        "liquidity_quality",
        "regime_fit",
        "freshness",
        "manipulation_risk",
        "late_chase_risk",
        "score",
        "grade",
        "reason_tags",
    ):
        assert k in payload


def test_label_queue_contract_created():
    """Brief: ``mfe_mae_label_pending=True`` + tracking_windows
    5m / 15m / 30m / 1h / 4h + ``future_tail_label_pending=True``."""
    lq = build_label_queue_contract(
        opportunity_id="opp_x",
        scan_batch_id="scan_x",
        symbol="EDENUSDT",
        enqueued_at_ms=1_700_000_000_000,
        reference_price=1.05,
    )
    assert lq.mfe_mae_label_pending is True
    assert lq.future_tail_label_pending is True
    assert lq.tracking_windows == ("5m", "15m", "30m", "1h", "4h")
    assert lq.tracking_windows == DEFAULT_TRACKING_WINDOWS
    payload = lq.to_payload()
    for k in (
        "opportunity_id",
        "scan_batch_id",
        "symbol",
        "enqueued_at_ms",
        "mfe_mae_label_pending",
        "future_tail_label_pending",
        "tracking_windows",
        "reference_price",
    ):
        assert k in payload


def test_cluster_context_groups_by_quote_asset():
    cc = build_cluster_context(symbol="EDENUSDT", radar_score=80.0)
    assert cc.cluster_id == "USDT"
    assert cc.cluster_leader == "EDENUSDT"
    assert cc.cluster_rank == 1
    assert cc.cluster_size == 1
    # Non-ASCII symbols: cluster suffix lookup is case-insensitive
    cc2 = build_cluster_context(symbol="我踏马来了USDT", radar_score=80.0)
    assert cc2.cluster_id == "USDT"


# ---------------------------------------------------------------------------
# 2. Stage classifier
# ---------------------------------------------------------------------------


def test_candidate_stage_classifier_early():
    a = classify_candidate_stage(
        first_seen_ts_ms=1_700_000_000_000,
        first_seen_price=100.0,
        current_price=101.0,  # +1%
        current_ts_ms=1_700_000_060_000,  # 60s elapsed
        price_acceleration_60s=0.005,
    )
    assert a.stage == "early"
    assert 0.0 <= a.late_chase_risk < 0.5
    assert a.blowoff_risk < 0.5
    assert a.freshness > 0.8


def test_candidate_stage_classifier_mid():
    a = classify_candidate_stage(
        first_seen_ts_ms=1_700_000_000_000,
        first_seen_price=100.0,
        current_price=110.0,  # +10%
        current_ts_ms=1_700_000_300_000,  # 5 min elapsed
        price_acceleration_60s=0.01,
    )
    assert a.stage == "mid"


def test_candidate_stage_classifier_late():
    a = classify_candidate_stage(
        first_seen_ts_ms=1_700_000_000_000,
        first_seen_price=100.0,
        current_price=140.0,  # +40%, past late threshold
        current_ts_ms=1_700_000_900_000,
        price_acceleration_60s=0.005,  # slow
    )
    assert a.stage == "late"
    assert a.late_chase_risk > 0.5


def test_candidate_stage_classifier_blowoff():
    a = classify_candidate_stage(
        first_seen_ts_ms=1_700_000_000_000,
        first_seen_price=100.0,
        current_price=125.0,  # +25%
        current_ts_ms=1_700_000_120_000,  # 2 min
        price_acceleration_60s=0.10,  # very fast 60s rip
    )
    assert a.stage == "blowoff"
    assert a.blowoff_risk > 0.5


def test_candidate_stage_classifier_dumped():
    a = classify_candidate_stage(
        first_seen_ts_ms=1_700_000_000_000,
        first_seen_price=100.0,
        current_price=85.0,  # -15%
        current_ts_ms=1_700_000_900_000,
        price_acceleration_60s=-0.05,
    )
    assert a.stage == "dumped"
    assert a.late_chase_risk == 0.0


# ---------------------------------------------------------------------------
# 3. Scoring formula + grade boundaries
# ---------------------------------------------------------------------------


def test_opportunity_score_formula():
    """The Issue brief first-version formula:

        0.25 * momentum_strength
      + 0.20 * volume_expansion
      + 0.15 * liquidity_quality
      + 0.15 * regime_fit
      + 0.15 * freshness
      - 0.20 * manipulation_risk
      - 0.20 * late_chase_risk

    All inputs at 100, no risks -> max positive 90 (still S grade).
    """
    score_max = compute_opportunity_score(
        OpportunityScoreInputs(
            momentum_strength=100.0,
            volume_expansion=100.0,
            liquidity_quality=100.0,
            regime_fit=100.0,
            freshness=100.0,
            manipulation_risk=0.0,
            late_chase_risk=0.0,
        )
    )
    expected = (
        0.25 * 100 + 0.20 * 100 + 0.15 * 100 + 0.15 * 100 + 0.15 * 100
    )
    assert score_max.score == pytest.approx(expected)
    assert score_max.grade == "S"

    # All inputs zero -> score 0, grade C.
    s0 = compute_opportunity_score(OpportunityScoreInputs())
    assert s0.score == 0.0
    assert s0.grade == "C"

    # All risks at 100 -> negative raw, clipped to 0.
    s_bad = compute_opportunity_score(
        OpportunityScoreInputs(
            momentum_strength=0.0,
            volume_expansion=0.0,
            liquidity_quality=0.0,
            regime_fit=0.0,
            freshness=0.0,
            manipulation_risk=100.0,
            late_chase_risk=100.0,
        )
    )
    assert s_bad.score == 0.0
    assert s_bad.grade == "C"

    # Out-of-range inputs are clipped.
    s_clipped = compute_opportunity_score(
        OpportunityScoreInputs(
            momentum_strength=200.0,
            manipulation_risk=-50.0,
        )
    )
    assert s_clipped.momentum_strength == 100.0
    assert s_clipped.manipulation_risk == 0.0


def test_opportunity_grade_boundaries():
    """Brief boundaries: S>=80, A in [65,80), B in [50,65), C<50."""
    assert grade_for_score(80.0) == "S"
    assert grade_for_score(85.0) == "S"
    assert grade_for_score(79.99) == "A"
    assert grade_for_score(65.0) == "A"
    assert grade_for_score(64.99) == "B"
    assert grade_for_score(50.0) == "B"
    assert grade_for_score(49.99) == "C"
    assert grade_for_score(0.0) == "C"
    # OPPORTUNITY_GRADE_BOUNDARIES exposes the canonical lower bounds.
    assert OPPORTUNITY_GRADE_BOUNDARIES["S"] == 80.0
    assert OPPORTUNITY_GRADE_BOUNDARIES["A"] == 65.0
    assert OPPORTUNITY_GRADE_BOUNDARIES["B"] == 50.0
    assert set(OPPORTUNITY_GRADES) == {"S", "A", "B", "C"}


# ---------------------------------------------------------------------------
# 4. Strategy selector
# ---------------------------------------------------------------------------


def _regime(name: str = "MEME_RISK_ON", confidence: float = 0.8) -> MarketRegimeAssessment:
    return assess_market_regime(
        avg_price_acceleration_60s=0.01 if name == "MEME_RISK_ON" else 0.0,
        positive_acceleration_ratio=0.7 if name == "MEME_RISK_ON" else 0.5,
        liquidation_event_rate=0.0,
        data_quality="ok",
        snapshot_count=10,
    )


def test_strategy_selector_follow():
    regime = _regime("MEME_RISK_ON")
    # Make sure follow is an allowed mode in the regime.
    assert "follow" in regime.allowed_strategy_modes
    stage = CandidateStageAssessment(
        stage="early",
        freshness=0.95,
        late_chase_risk=0.1,
        blowoff_risk=0.0,
        first_seen_ts=1, first_seen_price=100.0, current_price=101.0,
        distance_from_first_seen=0.01, distance_to_24h_high=0.05,
    )
    score = OpportunityScore(
        momentum_strength=80.0, volume_expansion=70.0,
        liquidity_quality=70.0, regime_fit=80.0,
        freshness=90.0, manipulation_risk=10.0, late_chase_risk=20.0,
        score=78.0, grade="A",
    )
    decision = select_strategy_mode(
        market_regime=regime, candidate_stage=stage, opportunity_score=score
    )
    assert decision.mode == "follow"
    assert decision.follow_allowed is True
    assert decision.observe_only is False
    assert decision.reject_reason is None


def test_strategy_selector_pullback():
    regime = _regime("MEME_RISK_ON")
    stage = CandidateStageAssessment(
        stage="mid",
        freshness=0.6,
        late_chase_risk=0.7,
        blowoff_risk=0.2,
        first_seen_ts=1, first_seen_price=100.0, current_price=110.0,
        distance_from_first_seen=0.10, distance_to_24h_high=0.02,
    )
    score = OpportunityScore(
        momentum_strength=80.0, volume_expansion=60.0,
        liquidity_quality=50.0, regime_fit=70.0,
        freshness=60.0, manipulation_risk=20.0, late_chase_risk=70.0,
        score=55.0, grade="B",
    )
    decision = select_strategy_mode(
        market_regime=regime, candidate_stage=stage, opportunity_score=score
    )
    assert decision.mode == "pullback"
    assert decision.pullback_allowed is True
    assert decision.follow_allowed is False


def test_strategy_selector_observe_for_late():
    regime = _regime("MEME_RISK_ON")
    stage = CandidateStageAssessment(
        stage="late",
        freshness=0.3,
        late_chase_risk=0.9,
        blowoff_risk=0.4,
        first_seen_ts=1, first_seen_price=100.0, current_price=140.0,
        distance_from_first_seen=0.40, distance_to_24h_high=0.0,
    )
    score = OpportunityScore(
        momentum_strength=80.0, volume_expansion=70.0,
        liquidity_quality=70.0, regime_fit=80.0,
        freshness=30.0, manipulation_risk=20.0, late_chase_risk=90.0,
        score=55.0, grade="B",
    )
    decision = select_strategy_mode(
        market_regime=regime, candidate_stage=stage, opportunity_score=score
    )
    assert decision.mode == "observe"
    assert decision.observe_only is True
    assert decision.follow_allowed is False
    assert "stage_late" in decision.reason_tags


def test_strategy_selector_observe_for_blowoff():
    regime = _regime("MEME_RISK_ON")
    stage = CandidateStageAssessment(
        stage="blowoff",
        freshness=0.3,
        late_chase_risk=0.9,
        blowoff_risk=0.9,
        first_seen_ts=1, first_seen_price=100.0, current_price=140.0,
        distance_from_first_seen=0.40, distance_to_24h_high=0.0,
    )
    score = OpportunityScore(
        momentum_strength=80.0, volume_expansion=70.0,
        liquidity_quality=70.0, regime_fit=80.0,
        freshness=30.0, manipulation_risk=20.0, late_chase_risk=90.0,
        score=55.0, grade="B",
    )
    decision = select_strategy_mode(
        market_regime=regime, candidate_stage=stage, opportunity_score=score
    )
    assert decision.mode == "observe"
    assert "stage_blowoff" in decision.reason_tags


def test_strategy_selector_reject_for_high_manipulation():
    regime = _regime("MEME_RISK_ON")
    stage = CandidateStageAssessment(
        stage="early", freshness=0.9, late_chase_risk=0.0,
        blowoff_risk=0.0, first_seen_ts=1, first_seen_price=100.0,
        current_price=101.0, distance_from_first_seen=0.01,
        distance_to_24h_high=0.05,
    )
    score = OpportunityScore(
        momentum_strength=80.0, volume_expansion=70.0,
        liquidity_quality=70.0, regime_fit=80.0,
        freshness=90.0, manipulation_risk=80.0, late_chase_risk=10.0,
        score=40.0, grade="C",
    )
    decision = select_strategy_mode(
        market_regime=regime, candidate_stage=stage, opportunity_score=score
    )
    assert decision.mode == "reject"
    assert decision.reject_reason == "high_manipulation_risk"
    assert decision.follow_allowed is False
    assert decision.pullback_allowed is False


def test_strategy_selector_reject_for_no_trade_regime():
    """Brief: Risk-Off / No-Trade -> reject."""
    no_trade_regime = MarketRegimeAssessment(
        regime_name="NO_TRADE",
        confidence=1.0,
        risk_multiplier=0.0,
        allowed_strategy_modes=(),
        no_trade_reason=("ws_data_stale",),
    )
    stage = CandidateStageAssessment(
        stage="early", freshness=0.9, late_chase_risk=0.0,
        blowoff_risk=0.0, first_seen_ts=1, first_seen_price=100.0,
        current_price=101.0, distance_from_first_seen=0.01,
        distance_to_24h_high=0.05,
    )
    score = OpportunityScore(
        momentum_strength=80.0, volume_expansion=70.0,
        liquidity_quality=70.0, regime_fit=80.0,
        freshness=90.0, manipulation_risk=10.0, late_chase_risk=10.0,
        score=70.0, grade="A",
    )
    decision = select_strategy_mode(
        market_regime=no_trade_regime,
        candidate_stage=stage,
        opportunity_score=score,
    )
    assert decision.mode == "reject"
    assert decision.reject_reason and "no_trade" in decision.reject_reason

    # SYSTEMIC_RISK -> reject
    sys_risk = MarketRegimeAssessment(
        regime_name="SYSTEMIC_RISK", confidence=1.0, risk_multiplier=0.0
    )
    d2 = select_strategy_mode(
        market_regime=sys_risk, candidate_stage=stage, opportunity_score=score
    )
    assert d2.mode == "reject"


# ---------------------------------------------------------------------------
# 5. Adaptive context orchestrator
# ---------------------------------------------------------------------------


def test_adaptive_candidate_context_payload_round_trips():
    ctx = build_adaptive_candidate_context(
        opportunity_id="opp_a",
        scan_batch_id="scan_a",
        symbol="EDENUSDT",
        timestamp_ms=1_700_000_060_000,
        first_seen_ts_ms=1_700_000_000_000,
        first_seen_price=100.0,
        current_price=102.0,
        price_acceleration_60s=0.01,
        avg_price_acceleration_60s=0.005,
        positive_acceleration_ratio=0.6,
        snapshot_count=10,
        data_quality="ok",
        radar_score=70.0,
    )
    payload = ctx.to_payload()
    json.dumps(payload, sort_keys=True)
    for k in (
        "opportunity_id",
        "scan_batch_id",
        "symbol",
        "timestamp_ms",
        "market_regime",
        "candidate_stage",
        "opportunity_score",
        "strategy_mode",
        "cluster",
        "label_queue",
        "strategy_version",
        "scoring_version",
        "risk_config_version",
        "state_machine_version",
    ):
        assert k in payload
    # Versions are stamped.
    assert payload["strategy_version"] == AdaptiveStrategyVersion
    assert payload["scoring_version"] == AdaptiveScoringVersion
    assert payload["state_machine_version"] == AdaptiveStateMachineVersion


def test_adaptive_context_attached_to_learning_ready_payload(tmp_path: Path):
    """The Phase 8.5 LearningReadyContext carries the adaptive
    sub-block under the canonical key."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        ctx = build_adaptive_candidate_context(
            opportunity_id="opp_x", scan_batch_id="scan_x",
            symbol="EDENUSDT", timestamp_ms=1_700_000_060_000,
            first_seen_ts_ms=1_700_000_000_000, first_seen_price=100.0,
            current_price=101.0, snapshot_count=1,
        )
        lrc = LearningReadyContext(adaptive_candidate=ctx)
        body = lrc.to_event_payload()
        assert ADAPTIVE_LEARNING_READY_KEY == "adaptive_candidate"
        assert "adaptive_candidate" in body
        # Round-trip via attach_learning_ready does not mutate input.
        original = {"reasons": ["x"]}
        merged = attach_learning_ready(original, lrc)
        assert merged["reasons"] == ["x"]
        assert "adaptive_candidate" in merged[LEARNING_READY_KEY]
    finally:
        dbs.close()


def test_adaptive_event_types_distinct_from_phase_8_5_set():
    """Phase 8.5 keeps its 11-type contract; the six adaptive types
    are a separate tuple."""
    assert len(LEARNING_READY_EVENT_TYPES) == 11
    assert len(ADAPTIVE_LEARNING_READY_EVENT_TYPES) == 6
    overlap = set(LEARNING_READY_EVENT_TYPES) & set(
        ADAPTIVE_LEARNING_READY_EVENT_TYPES
    )
    assert overlap == set()
    expected = {
        EventType.MARKET_REGIME_ASSESSED,
        EventType.CANDIDATE_STAGE_CLASSIFIED,
        EventType.OPPORTUNITY_SCORED,
        EventType.STRATEGY_MODE_SELECTED,
        EventType.CLUSTER_CONTEXT_ATTACHED,
        EventType.LABEL_QUEUE_ENQUEUED,
    }
    assert set(ADAPTIVE_LEARNING_READY_EVENT_TYPES) == expected


# ---------------------------------------------------------------------------
# 6. WS-radar chain integration
# ---------------------------------------------------------------------------


def test_ws_radar_chain_emits_six_adaptive_events(tmp_path: Path):
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        chain = WSRadarChainDriver(risk_engine=risk, event_repo=repo)
        candidate = _make_candidate()
        result = chain.drive(candidate)
        assert result.adaptive_context is not None
        # Exactly one of each event type per chain.
        for et in (
            EventType.MARKET_REGIME_ASSESSED,
            EventType.CANDIDATE_STAGE_CLASSIFIED,
            EventType.OPPORTUNITY_SCORED,
            EventType.STRATEGY_MODE_SELECTED,
            EventType.CLUSTER_CONTEXT_ATTACHED,
            EventType.LABEL_QUEUE_ENQUEUED,
        ):
            evs = repo.list_events(event_type=et)
            assert len(evs) == 1, f"{et.value}={len(evs)}"
            payload = evs[0].payload
            assert payload["opportunity_id"] == candidate.identity.opportunity_id
            assert payload["scan_batch_id"] == candidate.identity.scan_batch_id
            assert payload["strategy_version"] == AdaptiveStrategyVersion
            assert payload["scoring_version"] == AdaptiveScoringVersion
            assert payload["risk_config_version"]
            assert payload["state_machine_version"] == AdaptiveStateMachineVersion
            assert "learning_ready" in payload
            assert (
                "adaptive_candidate" in payload["learning_ready"]
            ), f"{et.value} missing adaptive_candidate"
        # Counters
        assert chain.market_regime_assessed_count == 1
        assert chain.candidate_stage_classified_count == 1
        assert chain.opportunity_scored_count == 1
        assert chain.strategy_mode_selected_count == 1
        assert chain.cluster_context_attached_count == 1
        assert chain.label_queue_enqueued_count == 1
    finally:
        dbs.close()


def test_virtual_trade_plan_contains_adaptive_fields(tmp_path: Path):
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        chain = WSRadarChainDriver(risk_engine=risk, event_repo=repo)
        chain.drive(_make_candidate())
        events = repo.list_events(event_type=EventType.PRE_ANOMALY_DETECTED)
        assert events
        plan = events[0].payload["learning_ready"]["virtual_trade_plan"]
        for k in (
            "opportunity_score",
            "opportunity_grade",
            "candidate_stage",
            "strategy_mode",
            "cluster_id",
            "cluster_leader",
            "label_queue_pending",
            "follow_allowed",
            "pullback_allowed",
            "observe_only",
            "reject_reason",
        ):
            assert k in plan, f"VirtualTradePlan adaptive field missing: {k}"
        # Round-trip through the helper.
        restored = payload_to_virtual_trade_plan(plan)
        assert restored.opportunity_grade in {"S", "A", "B", "C"}
        assert restored.candidate_stage in CANDIDATE_STAGES
        assert restored.strategy_mode in STRATEGY_MODES
        assert restored.label_queue_pending is True
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 7. Daily report
# ---------------------------------------------------------------------------


def test_daily_report_contains_adaptive_candidate_metrics(tmp_path: Path):
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        chain = WSRadarChainDriver(risk_engine=risk, event_repo=repo)
        chain.drive(_make_candidate())
        out_dir = tmp_path / "reports"
        out_dir.mkdir()
        builder = DailyReportBuilder(event_repo=repo, output_dir=out_dir)
        snap = builder.build(
            started_at_ms=1_700_000_000_000,
            finished_at_ms=1_700_000_120_000,
            adaptive_metrics=chain.adaptive_metrics_payload(),
            write_to_disk=True,
        )
        assert snap.market_regime_assessed_count == 1
        assert snap.candidate_stage_classified_count == 1
        assert snap.opportunity_scored_count == 1
        assert snap.strategy_mode_selected_count == 1
        assert snap.cluster_context_attached_count == 1
        assert snap.label_queue_enqueued == 1
        assert snap.market_regime_counts
        assert snap.candidate_stage_counts
        assert snap.strategy_mode_counts
        assert snap.opportunity_grade_counts
        assert snap.top_opportunity_scores
        assert "Phase 11C.1C-A Adaptive Candidate Regime" in snap.markdown
        assert "MARKET_REGIME_ASSESSED count" in snap.markdown
        assert "Strategy modes" in snap.markdown
        assert "paper / virtual only" in snap.markdown
        # Payload is JSON-safe and includes adaptive_metrics.
        payload = snap.to_payload()
        assert "adaptive_metrics" in payload
        json.dumps(payload, sort_keys=True, default=str)
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 8. Export + Replay
# ---------------------------------------------------------------------------


def test_export_replay_reads_adaptive_candidate_events(tmp_path: Path):
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        chain = WSRadarChainDriver(risk_engine=risk, event_repo=repo)
        chain.drive(_make_candidate())
        out_dir = tmp_path / "exports"
        out_dir.mkdir()
        service = TestDataExportService(
            event_repo=repo, trading_mode="paper", output_dir=out_dir
        )
        # The synthetic candidate uses a fixed 2023 timestamp so we
        # use an explicit time range that covers it; the default
        # ``24h`` window is anchored on ``now_ms()`` and would
        # exclude the synthetic events.
        result = service.export(
            range_label="range",
            start_ms=1_699_000_000_000,
            end_ms=2_000_000_000_000,
            type_filter="all",
        )
        with zipfile.ZipFile(result.zip_path) as zf:
            seen_types: set[str] = set()
            for line in zf.read("events.jsonl").decode("utf-8").splitlines():
                row = json.loads(line)
                seen_types.add(row.get("event_type"))
            for et in (
                "MARKET_REGIME_ASSESSED",
                "CANDIDATE_STAGE_CLASSIFIED",
                "OPPORTUNITY_SCORED",
                "STRATEGY_MODE_SELECTED",
                "CLUSTER_CONTEXT_ATTACHED",
                "LABEL_QUEUE_ENQUEUED",
            ):
                assert et in seen_types, f"export missing adaptive event {et}"
        # Replay engine reads RISK_REJECTED events without choking on
        # the new event types.
        eng = ReplayEngine(event_repo=repo)
        rejects = eng.replay_risk_rejections()
        assert rejects, "replay returned no RISK_REJECTED rows"
    finally:
        dbs.close()


# ---------------------------------------------------------------------------
# 9. Safety invariants
# ---------------------------------------------------------------------------


def test_no_live_trading_flags_unchanged():
    """The five Phase 1 safety flags + telegram_outbound +
    binance_private_api + every safety.forbid_* flag remain at their
    locked values."""
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


def test_no_real_telegram_outbound_flag_unchanged():
    s = _settings()
    assert s.telegram_outbound_enabled is False


def test_no_binance_api_key_consumed():
    """The public client refuses any credential-shaped construction."""
    with pytest.raises(SafeModeViolation):
        BinancePublicClient(api_key="x", autostart=False)
    with pytest.raises(SafeModeViolation):
        BinancePublicClient(api_secret="x", autostart=False)


def test_phase_12_remains_forbidden():
    """The four ExchangeClientBase write surfaces must still refuse."""
    client = BinancePublicClient(autostart=False)
    for fn_name in WRITE_SURFACE_METHODS:
        with pytest.raises(SafeModeViolation):
            getattr(client, fn_name)()


def test_strategy_mode_does_not_authorise_real_trade(tmp_path: Path):
    """Even when the selector returns ``follow``, the chain's Risk
    Engine call still has stop_unconfirmed=True so the engine
    rejects every new-open path. The strategy_mode is paper /
    virtual only."""
    repo, dbs = _make_event_repo(tmp_path)
    try:
        risk = RiskEngine(event_repo=repo)
        chain = WSRadarChainDriver(risk_engine=risk, event_repo=repo)
        # Drive a candidate where the selector might pick "follow"
        # (it usually does not on a fresh candidate, but the test
        # asserts the SAFETY invariant either way).
        result = chain.drive(_make_candidate())
        # Risk Engine refused the new-open path: every chain emits
        # RISK_REJECTED (stop_unconfirmed locks it in).
        assert result.risk_approved is False
        # The reject reasons include stop_unconfirmed.
        assert "stop_unconfirmed" in result.reject_reasons
    finally:
        dbs.close()


def test_adaptive_module_does_not_import_third_party_network_libs():
    """Source-tree audit on ``app/adaptive/``: pure-stdlib + pydantic
    only (no exchange / LLM / Telegram / HTTP / WS clients)."""
    import ast

    forbidden_top_level = {
        "ccxt",
        "binance",
        "binance_connector",
        "python_binance",
        "aiohttp",
        "websockets",
        "websocket",
        "websocket_client",
        "requests",
        "httpx",
        "urllib3",
        "openai",
        "anthropic",
        "deepseek",
        "telegram",
        "python_telegram_bot",
        "telebot",
        "aiogram",
    }
    adaptive_dir = (
        Path(__file__).resolve().parent.parent.parent / "app" / "adaptive"
    )
    files = sorted(adaptive_dir.glob("*.py"))
    assert files, "adaptive package empty"
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    head = alias.name.split(".")[0]
                    assert head not in forbidden_top_level, (
                        f"{path.name} imports forbidden module {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    head = node.module.split(".")[0]
                    assert head not in forbidden_top_level, (
                        f"{path.name} imports forbidden module {node.module}"
                    )
